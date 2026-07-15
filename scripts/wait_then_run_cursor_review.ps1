param(
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [string]$Workspace = "D:\Dev\VideoCaptioner",
    [string]$BatchId = "BATCH-20260715-001",
    [int]$StartCourse = 3,
    [int]$EndCourse = 5,
    [int]$PollSeconds = 30,
    [int]$MaxAttempts = 2
)

$ErrorActionPreference = "Stop"
$runs = [ordered]@{
    C001 = "RUN-20260715-BASELINE"
    C002 = "RUN-20260715-V001"
    C003 = "RUN-20260715-001-V001"
    C004 = "RUN-20260715-001-V001"
    C005 = "RUN-20260715-001-V001"
}
$batchDir = Join-Path $DataRoot "batches\$BatchId"
$statusPath = Join-Path $batchDir "cursor-p01-review-v002-status.jsonl"
$failurePath = Join-Path $batchDir "cursor-p01-review-v002-failures.jsonl"

function Add-JsonLine {
    param([string]$Path, [hashtable]$Value)
    Add-Content -LiteralPath $Path -Encoding utf8 -Value (
        $Value | ConvertTo-Json -Compress -Depth 8
    )
}

foreach ($entry in $runs.GetEnumerator()) {
    $courseId = $entry.Key
    $ordinal = [int]$courseId.Substring(1)
    if ($ordinal -lt $StartCourse -or $ordinal -gt $EndCourse) {
        continue
    }
    $runId = $entry.Value
    $transcript = Join-Path $DataRoot "courses\$courseId\01_raw\$runId\transcript.txt"
    $rawQa = Join-Path $DataRoot "courses\$courseId\qa\$runId.json"
    while (-not (Test-Path -LiteralPath $transcript) -or -not (Test-Path -LiteralPath $rawQa)) {
        Start-Sleep -Seconds $PollSeconds
    }
    if ((Get-Content -Raw -Encoding utf8 -LiteralPath $rawQa | ConvertFrom-Json).status -ne "pass") {
        Add-JsonLine $failurePath @{
            at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
            error = "raw QA did not pass"
        }
        continue
    }

    $baseline = Join-Path $DataRoot "courses\$courseId\02_normalized\P01-baseline-knowledge-v002.json"
    if (-not (Test-Path -LiteralPath $baseline)) {
        & $PythonExe -m course_video_analyzer.knowledge.cli normalize-p01 `
            $courseId $transcript $baseline `
            --prompt-version knowledge-v002-p01-baseline
        if ($LASTEXITCODE -ne 0) {
            Add-JsonLine $failurePath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                error = "deterministic baseline failed"
            }
            continue
        }
    }

    $output = Join-Path $DataRoot "courses\$courseId\02_normalized\P01-knowledge-v002.json"
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

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        Add-JsonLine $statusPath @{
            at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
            attempt = $attempt; status = "started"
        }
        & $PythonExe -m course_video_analyzer.knowledge.cli cursor-stage `
            $courseId P01 $baseline $output `
            --workspace $Workspace --model auto `
            --prompt-root prompts\knowledge-v002 --timeout-seconds 3600
        if ($LASTEXITCODE -ne 0) {
            Add-JsonLine $failurePath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                attempt = $attempt; error = "cursor review failed"
            }
            continue
        }
        $qaOutput = Join-Path $DataRoot "courses\$courseId\qa\P01-knowledge-v002-qa.json"
        & $PythonExe -m course_video_analyzer.knowledge.cli qa-p01 `
            $courseId $transcript $output $qaOutput `
            --prompt-version knowledge-v002-p01
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
    stage = "P01-review"
    prompt_version = "knowledge-v002-p01"
    completed_at = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath (
    Join-Path $batchDir "cursor-p01-review-v002-complete.json"
)
