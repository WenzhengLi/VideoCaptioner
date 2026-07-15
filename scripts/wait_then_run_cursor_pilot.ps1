param(
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [string]$Workspace = "D:\Dev\VideoCaptioner",
    [string]$BatchId = "BATCH-20260715-001",
    [int]$PollSeconds = 60,
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
$statusPath = Join-Path $batchDir "cursor-p01-status.jsonl"
$failurePath = Join-Path $batchDir "cursor-p01-failures.jsonl"

function Add-JsonLine {
    param([string]$Path, [hashtable]$Value)
    $line = $Value | ConvertTo-Json -Compress -Depth 8
    Add-Content -LiteralPath $Path -Encoding utf8 -Value $line
}

foreach ($entry in $runs.GetEnumerator()) {
    $courseId = $entry.Key
    $runId = $entry.Value
    $inputPath = Join-Path $DataRoot "courses\$courseId\01_raw\$runId\transcript.txt"
    $qaPath = Join-Path $DataRoot "courses\$courseId\qa\$runId.json"
    while (-not (Test-Path -LiteralPath $inputPath) -or -not (Test-Path -LiteralPath $qaPath)) {
        Start-Sleep -Seconds $PollSeconds
    }
    $qa = Get-Content -Raw -Encoding utf8 -LiteralPath $qaPath | ConvertFrom-Json
    if ($qa.status -ne "pass") {
        Add-JsonLine -Path $failurePath -Value @{
            at = [DateTime]::UtcNow.ToString("o")
            course_id = $courseId
            stage = "P01"
            error = "raw transcript QA did not pass"
        }
        continue
    }

    $outputPath = Join-Path $DataRoot "courses\$courseId\02_normalized\P01-knowledge-v001.json"
    if (Test-Path -LiteralPath $outputPath) {
        try {
            Get-Content -Raw -Encoding utf8 -LiteralPath $outputPath |
                ConvertFrom-Json -ErrorAction Stop | Out-Null
            Add-JsonLine -Path $statusPath -Value @{
                at = [DateTime]::UtcNow.ToString("o")
                course_id = $courseId
                stage = "P01"
                status = "skipped_existing_valid"
            }
            continue
        } catch {
            $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
            Move-Item -LiteralPath $outputPath -Destination "$outputPath.invalid-$stamp"
        }
    }

    $succeeded = $false
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        Add-JsonLine -Path $statusPath -Value @{
            at = [DateTime]::UtcNow.ToString("o")
            course_id = $courseId
            stage = "P01"
            status = "started"
            attempt = $attempt
        }
        & $PythonExe -m course_video_analyzer.knowledge.cli cursor-stage `
            $courseId P01 $inputPath $outputPath `
            --workspace $Workspace `
            --model auto `
            --timeout-seconds 7200
        if ($LASTEXITCODE -eq 0) {
            $qaOutputPath = Join-Path $DataRoot "courses\$courseId\qa\P01-knowledge-v001.json"
            & $PythonExe -m course_video_analyzer.knowledge.cli qa-p01 `
                $courseId $inputPath $outputPath $qaOutputPath
            if ($LASTEXITCODE -ne 0) {
                Add-JsonLine -Path $failurePath -Value @{
                    at = [DateTime]::UtcNow.ToString("o")
                    course_id = $courseId
                    stage = "P01"
                    attempt = $attempt
                    error = "P01 deterministic QA command failed"
                }
                continue
            }
            $qaResult = Get-Content -Raw -Encoding utf8 -LiteralPath $qaOutputPath |
                ConvertFrom-Json
            if ($qaResult.status -ne "pass") {
                Add-JsonLine -Path $failurePath -Value @{
                    at = [DateTime]::UtcNow.ToString("o")
                    course_id = $courseId
                    stage = "P01"
                    attempt = $attempt
                    error = "P01 deterministic QA needs review"
                }
                continue
            }
            $succeeded = $true
            Add-JsonLine -Path $statusPath -Value @{
                at = [DateTime]::UtcNow.ToString("o")
                course_id = $courseId
                stage = "P01"
                status = "succeeded"
                attempt = $attempt
            }
            break
        }
        Add-JsonLine -Path $failurePath -Value @{
            at = [DateTime]::UtcNow.ToString("o")
            course_id = $courseId
            stage = "P01"
            attempt = $attempt
            error = "cursor-stage exited with code $LASTEXITCODE"
        }
    }
    if (-not $succeeded) {
        continue
    }
}

@{
    schema_version = "1.0"
    batch_id = $BatchId
    stage = "P01"
    completed_at = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $batchDir "cursor-p01-complete.json") -Encoding utf8
