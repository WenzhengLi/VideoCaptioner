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
$p02Complete = Join-Path $batchDir "cursor-p02-knowledge-v002-complete.json"
$statusPath = Join-Path $batchDir "cursor-p03-knowledge-v002-status.jsonl"
$failurePath = Join-Path $batchDir "cursor-p03-knowledge-v002-failures.jsonl"

function Add-JsonLine {
    param([string]$Path, [hashtable]$Value)
    Add-Content -LiteralPath $Path -Encoding utf8 -Value (
        $Value | ConvertTo-Json -Compress -Depth 8
    )
}

while (-not (Test-Path -LiteralPath $p02Complete)) {
    Start-Sleep -Seconds $PollSeconds
}

$failedCourses = @()
for ($ordinal = $StartCourse; $ordinal -le $EndCourse; $ordinal++) {
    $courseId = "C{0:D3}" -f $ordinal
    $p02 = Join-Path $DataRoot "courses\$courseId\02_normalized\P02-knowledge-v002.json"
    $p02Qa = Join-Path $DataRoot "courses\$courseId\qa\P02-knowledge-v002-qa.json"
    if (-not (Test-Path -LiteralPath $p02) -or -not (Test-Path -LiteralPath $p02Qa)) {
        $failedCourses += $courseId
        Add-JsonLine $failurePath @{
            at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
            error = "P02 output or QA missing"
        }
        continue
    }
    if ((Get-Content -Raw -Encoding utf8 -LiteralPath $p02Qa | ConvertFrom-Json).status -ne "pass") {
        $failedCourses += $courseId
        Add-JsonLine $failurePath @{
            at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
            error = "P02 QA did not pass"
        }
        continue
    }

    $outputDir = Join-Path $DataRoot "courses\$courseId\03_cases"
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
    $output = Join-Path $outputDir "P03-knowledge-v002.json"
    $qaOutput = Join-Path $DataRoot "courses\$courseId\qa\P03-knowledge-v002-qa.json"
    if ((Test-Path -LiteralPath $output) -and (Test-Path -LiteralPath $qaOutput)) {
        try {
            $existingQa = Get-Content -Raw -Encoding utf8 -LiteralPath $qaOutput |
                ConvertFrom-Json -ErrorAction Stop
            if ($existingQa.status -eq "pass") {
                Add-JsonLine $statusPath @{
                    at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                    status = "skipped_existing_valid"
                }
                continue
            }
        } catch {
        }
    }
    if (Test-Path -LiteralPath $output) {
        $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
        Move-Item -LiteralPath $output -Destination "$output.invalid-$stamp"
    }

    $succeeded = $false
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        Add-JsonLine $statusPath @{
            at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
            attempt = $attempt; status = "started"
        }
        & $PythonExe -m course_video_analyzer.knowledge.cli cursor-stage `
            $courseId P03 $p02 $output `
            --workspace $Workspace --model auto `
            --prompt-root prompts\knowledge-v002 --timeout-seconds 3600
        if ($LASTEXITCODE -ne 0) {
            Add-JsonLine $failurePath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                attempt = $attempt; error = "Cursor P03 segmentation failed"
            }
            continue
        }
        & $PythonExe -m course_video_analyzer.knowledge.cli qa-p03 `
            $courseId $p02 $output $qaOutput `
            --prompt-version knowledge-v002-p03
        if ($LASTEXITCODE -eq 0 -and (
            Get-Content -Raw -Encoding utf8 -LiteralPath $qaOutput |
                ConvertFrom-Json
            ).status -eq "pass") {
            $succeeded = $true
            Add-JsonLine $statusPath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                attempt = $attempt; status = "succeeded"
            }
            break
        }
        Add-JsonLine $failurePath @{
            at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
            attempt = $attempt; error = "P03 deterministic QA did not pass"
        }
        if (Test-Path -LiteralPath $output) {
            $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
            Move-Item -LiteralPath $output -Destination "$output.invalid-$stamp"
        }
    }
    if (-not $succeeded) {
        $failedCourses += $courseId
    }
}

@{
    schema_version = "1.0"
    stage = "P03-segment"
    prompt_version = "knowledge-v002-p03"
    status = $(if ($failedCourses.Count -eq 0) { "complete" } else { "needs_review" })
    failed_courses = $failedCourses
    completed_at = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 -LiteralPath (
    Join-Path $batchDir "cursor-p03-knowledge-v002-complete.json"
)
