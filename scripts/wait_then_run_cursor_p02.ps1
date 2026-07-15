param(
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [string]$Workspace = "D:\Dev\VideoCaptioner",
    [string]$BatchId = "BATCH-20260715-001",
    [int]$StartCourse = 1,
    [int]$EndCourse = 5,
    [int]$PollSeconds = 30,
    [int]$MaxAttempts = 2
)

$ErrorActionPreference = "Stop"
$batchDir = Join-Path $DataRoot "batches\$BatchId"
$p01Complete = Join-Path $batchDir "cursor-p01-knowledge-v002-p01-complete.json"
$statusPath = Join-Path $batchDir "cursor-p02-knowledge-v002-status.jsonl"
$failurePath = Join-Path $batchDir "cursor-p02-knowledge-v002-failures.jsonl"

function Add-JsonLine {
    param([string]$Path, [hashtable]$Value)
    Add-Content -LiteralPath $Path -Encoding utf8 -Value (
        $Value | ConvertTo-Json -Compress -Depth 8
    )
}

while (-not (Test-Path -LiteralPath $p01Complete)) {
    Start-Sleep -Seconds $PollSeconds
}

for ($ordinal = $StartCourse; $ordinal -le $EndCourse; $ordinal++) {
    $courseId = "C{0:D3}" -f $ordinal
    $p01 = Join-Path $DataRoot "courses\$courseId\02_normalized\P01-knowledge-v002.json"
    $p01QaCandidates = @(
        (Join-Path $DataRoot "courses\$courseId\qa\P01-knowledge-v002-qa.json"),
        (Join-Path $DataRoot "courses\$courseId\qa\P01-knowledge-v002.json")
    )
    $p01Qa = $p01QaCandidates | Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
    if (-not (Test-Path -LiteralPath $p01) -or -not $p01Qa) {
        Add-JsonLine $failurePath @{
            at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
            error = "P01 output or QA missing"
        }
        continue
    }
    if ((Get-Content -Raw -Encoding utf8 -LiteralPath $p01Qa | ConvertFrom-Json).status -ne "pass") {
        Add-JsonLine $failurePath @{
            at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
            error = "P01 QA did not pass"
        }
        continue
    }

    $baseline = Join-Path $DataRoot "courses\$courseId\02_normalized\P02-baseline-knowledge-v002.json"
    if (-not (Test-Path -LiteralPath $baseline)) {
        & $PythonExe -m course_video_analyzer.knowledge.cli classify-p02 `
            $courseId $p01 $baseline `
            --prompt-version knowledge-v002-p02-baseline
        if ($LASTEXITCODE -ne 0) {
            Add-JsonLine $failurePath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                error = "P02 baseline failed"
            }
            continue
        }
    }

    $output = Join-Path $DataRoot "courses\$courseId\02_normalized\P02-knowledge-v002.json"
    if (Test-Path -LiteralPath $output) {
        try {
            Get-Content -Raw -Encoding utf8 -LiteralPath $output |
                ConvertFrom-Json -ErrorAction Stop | Out-Null
            continue
        } catch {
            $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
            Move-Item -LiteralPath $output -Destination "$output.invalid-$stamp"
        }
    }

    $reviewPack = Join-Path $DataRoot "courses\$courseId\02_normalized\P02-review-pack-knowledge-v002.json"
    if (-not (Test-Path -LiteralPath $reviewPack)) {
        & $PythonExe -m course_video_analyzer.knowledge.cli build-p02-review `
            $courseId $baseline $reviewPack
        if ($LASTEXITCODE -ne 0) {
            Add-JsonLine $failurePath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                error = "P02 compact review pack failed"
            }
            continue
        }
    }
    $reviewDecision = Join-Path $DataRoot "courses\$courseId\02_normalized\P02-review-decisions-knowledge-v002.json"

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        Add-JsonLine $statusPath @{
            at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
            attempt = $attempt; status = "started"
        }
        if (Test-Path -LiteralPath $reviewDecision) {
            $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
            Move-Item -LiteralPath $reviewDecision -Destination "$reviewDecision.invalid-$stamp"
        }
        & $PythonExe -m course_video_analyzer.knowledge.cli cursor-stage `
            $courseId P02 $reviewPack $reviewDecision `
            --workspace $Workspace --model auto `
            --prompt-root prompts\knowledge-v002-compact --timeout-seconds 1200
        if ($LASTEXITCODE -ne 0) {
            Add-JsonLine $failurePath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                attempt = $attempt; error = "Cursor P02 review failed"
            }
            continue
        }
        & $PythonExe -m course_video_analyzer.knowledge.cli apply-p02-review `
            $courseId $baseline $reviewPack $reviewDecision $output
        if ($LASTEXITCODE -ne 0) {
            Add-JsonLine $failurePath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                attempt = $attempt; error = "P02 compact review apply failed"
            }
            continue
        }
        $qaOutput = Join-Path $DataRoot "courses\$courseId\qa\P02-knowledge-v002-qa.json"
        & $PythonExe -m course_video_analyzer.knowledge.cli qa-p02 `
            $courseId $p01 $output $qaOutput `
            --prompt-version knowledge-v002-p02
        if ($LASTEXITCODE -eq 0 -and (
            Get-Content -Raw -Encoding utf8 -LiteralPath $qaOutput |
                ConvertFrom-Json
            ).status -eq "pass") {
            Add-JsonLine $statusPath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                attempt = $attempt; status = "succeeded"
            }
            break
        }
    }
}

@{
    schema_version = "1.0"
    stage = "P02-review"
    prompt_version = "knowledge-v002-p02"
    completed_at = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath (
    Join-Path $batchDir "cursor-p02-knowledge-v002-complete.json"
)
