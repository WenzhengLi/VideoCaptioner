param(
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [string]$Workspace = "D:\Dev\VideoCaptioner",
    [string]$BatchId = "BATCH-20260715-001",
    [string]$WaveId = "",
    [int]$StartCourse = 1,
    [int]$EndCourse = 5,
    [int]$PollSeconds = 30,
    [int]$MaxAttempts = 2,
    [string]$OutputVersion = "knowledge-v002",
    [string]$PromptRoot = "prompts\knowledge-v002",
    [string]$CompactPromptRoot = "prompts\knowledge-v002-compact"
)

$ErrorActionPreference = "Stop"
$batchDir = Join-Path $DataRoot "batches\$BatchId"
$waveSuffix = if ([string]::IsNullOrWhiteSpace($WaveId)) { "" } else { "-$WaveId" }
$p01Complete = Join-Path $batchDir "cursor-p01-${OutputVersion}-p01$waveSuffix-complete.json"
$statusPath = Join-Path $batchDir "cursor-p02-${OutputVersion}$waveSuffix-status.jsonl"
$failurePath = Join-Path $batchDir "cursor-p02-${OutputVersion}$waveSuffix-failures.jsonl"

function Add-JsonLine {
    param([string]$Path, [hashtable]$Value)
    Add-Content -LiteralPath $Path -Encoding utf8 -Value (
        $Value | ConvertTo-Json -Compress -Depth 8
    )
}

while (-not (Test-Path -LiteralPath $p01Complete)) {
    Start-Sleep -Seconds $PollSeconds
}
$p01Marker = Get-Content -Raw -Encoding utf8 -LiteralPath $p01Complete | ConvertFrom-Json
if ($p01Marker.status -and $p01Marker.status -ne "complete") { throw "P01 wave marker is not complete" }

$failedCourses = @()
for ($ordinal = $StartCourse; $ordinal -le $EndCourse; $ordinal++) {
    $courseId = "C{0:D3}" -f $ordinal
    $courseSucceeded = $false
    $p01 = Join-Path $DataRoot "courses\$courseId\02_normalized\P01-${OutputVersion}.json"
    $p01QaCandidates = @(
        (Join-Path $DataRoot "courses\$courseId\qa\P01-${OutputVersion}-qa.json"),
        (Join-Path $DataRoot "courses\$courseId\qa\P01-${OutputVersion}.json")
    )
    $p01Qa = $p01QaCandidates | Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
    if (-not (Test-Path -LiteralPath $p01) -or -not $p01Qa) {
        Add-JsonLine $failurePath @{
            at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
            error = "P01 output or QA missing"
        }
        $failedCourses += $courseId
        continue
    }
    if ((Get-Content -Raw -Encoding utf8 -LiteralPath $p01Qa | ConvertFrom-Json).status -ne "pass") {
        Add-JsonLine $failurePath @{
            at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
            error = "P01 QA did not pass"
        }
        $failedCourses += $courseId
        continue
    }

    $baseline = Join-Path $DataRoot "courses\$courseId\02_normalized\P02-baseline-${OutputVersion}.json"
    if (-not (Test-Path -LiteralPath $baseline)) {
        & $PythonExe -m course_video_analyzer.knowledge.cli classify-p02 `
            $courseId $p01 $baseline `
            --prompt-version "${OutputVersion}-p02-baseline"
        if ($LASTEXITCODE -ne 0) {
            Add-JsonLine $failurePath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                error = "P02 baseline failed"
            }
            $failedCourses += $courseId
            continue
        }
    }

    $output = Join-Path $DataRoot "courses\$courseId\02_normalized\P02-${OutputVersion}.json"
    if (Test-Path -LiteralPath $output) {
        try {
            Get-Content -Raw -Encoding utf8 -LiteralPath $output |
                ConvertFrom-Json -ErrorAction Stop | Out-Null
            $courseSucceeded = $true
            continue
        } catch {
            $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
            Move-Item -LiteralPath $output -Destination "$output.invalid-$stamp"
        }
    }

    $reviewPack = Join-Path $DataRoot "courses\$courseId\02_normalized\P02-review-pack-${OutputVersion}.json"
    if (-not (Test-Path -LiteralPath $reviewPack)) {
        & $PythonExe -m course_video_analyzer.knowledge.cli build-p02-review `
            $courseId $baseline $reviewPack
        if ($LASTEXITCODE -ne 0) {
            Add-JsonLine $failurePath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                error = "P02 compact review pack failed"
            }
            $failedCourses += $courseId
            continue
        }
    }
    $reviewDecision = Join-Path $DataRoot "courses\$courseId\02_normalized\P02-review-decisions-${OutputVersion}.json"

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
            --prompt-root $CompactPromptRoot --timeout-seconds 1200 `
            --finish-on-stable-output --output-stability-seconds 30
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
        $qaOutput = Join-Path $DataRoot "courses\$courseId\qa\P02-${OutputVersion}-qa.json"
        & $PythonExe -m course_video_analyzer.knowledge.cli qa-p02 `
            $courseId $p01 $output $qaOutput `
            --prompt-version "${OutputVersion}-p02"
        if ($LASTEXITCODE -eq 0 -and (
            Get-Content -Raw -Encoding utf8 -LiteralPath $qaOutput |
                ConvertFrom-Json
            ).status -eq "pass") {
            Add-JsonLine $statusPath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                attempt = $attempt; status = "succeeded"
            }
            $courseSucceeded = $true
            break
        }
    }
    if (-not $courseSucceeded) { $failedCourses += $courseId }
}

@{
    schema_version = "1.0"
    stage = "P02-review"
    prompt_version = "${OutputVersion}-p02"
    wave_id = $WaveId
    status = if ($failedCourses.Count -eq 0) { "complete" } else { "needs_review" }
    failed_courses = @($failedCourses | Select-Object -Unique)
    completed_at = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 -LiteralPath (
    Join-Path $batchDir "cursor-p02-${OutputVersion}$waveSuffix-complete.json"
)
