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
$p04Complete = Join-Path $batchDir "cursor-p04-knowledge-v002-complete.json"
$statusPath = Join-Path $batchDir "cursor-p05-knowledge-v002-status.jsonl"
$failurePath = Join-Path $batchDir "cursor-p05-knowledge-v002-failures.jsonl"

function Add-JsonLine {
    param([string]$Path, [hashtable]$Value)
    Add-Content -LiteralPath $Path -Encoding utf8 -Value ($Value | ConvertTo-Json -Compress -Depth 8)
}

while (-not (Test-Path $p04Complete)) { Start-Sleep -Seconds $PollSeconds }
$marker = Get-Content -Raw -Encoding utf8 $p04Complete | ConvertFrom-Json
if ($marker.status -ne "complete") { throw "P04 batch marker is not complete" }

$failedCases = @()
for ($ordinal = $StartCourse; $ordinal -le $EndCourse; $ordinal++) {
    $courseId = "C{0:D3}" -f $ordinal
    $p03 = Join-Path $DataRoot "courses\$courseId\03_cases\P03-knowledge-v002.json"
    if (-not (Test-Path $p03)) { $failedCases += "${courseId}:*"; continue }
    $cases = (Get-Content -Raw -Encoding utf8 $p03 | ConvertFrom-Json).cases
    foreach ($case in $cases) {
        $caseId = [string]$case.case_id
        $caseInput = Join-Path $DataRoot "courses\$courseId\04_knowledge\P04-input-knowledge-v002\$caseId.json"
        $p04 = Join-Path $DataRoot "courses\$courseId\04_knowledge\P04-knowledge-v002\$caseId.json"
        $inputDir = Join-Path $DataRoot "courses\$courseId\04_knowledge\P05-input-knowledge-v002"
        $outputDir = Join-Path $DataRoot "courses\$courseId\04_knowledge\P05-knowledge-v002"
        New-Item -ItemType Directory -Force -Path $inputDir, $outputDir | Out-Null
        $input = Join-Path $inputDir "$caseId.json"
        $output = Join-Path $outputDir "$caseId.json"
        $qaOutput = Join-Path $DataRoot "courses\$courseId\qa\P05-$caseId-knowledge-v002-qa.json"
        if ((Test-Path $output) -and (Test-Path $qaOutput)) {
            try {
                if ((Get-Content -Raw -Encoding utf8 $qaOutput | ConvertFrom-Json).status -eq "pass") { continue }
            } catch {}
        }
        if (-not (Test-Path $input)) {
            & $PythonExe -m course_video_analyzer.knowledge.cli build-p05-input `
                $courseId $caseId $caseInput $p04 $input
            if ($LASTEXITCODE -ne 0) { $failedCases += $caseId; continue }
        }
        if (Test-Path $output) {
            $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
            Move-Item $output "$output.invalid-$stamp"
        }
        $succeeded = $false
        for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
            Add-JsonLine $statusPath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                case_id = $caseId; attempt = $attempt; status = "started"
            }
            & $PythonExe -m course_video_analyzer.knowledge.cli cursor-stage `
                $courseId P05 $input $output --workspace $Workspace --model auto `
                --prompt-root prompts\knowledge-v002 --timeout-seconds 1800 `
                --finish-on-stable-output --output-stability-seconds 30
            if ($LASTEXITCODE -ne 0) { continue }
            & $PythonExe -m course_video_analyzer.knowledge.cli qa-p05 `
                $courseId $caseId $input $output $qaOutput
            if ($LASTEXITCODE -eq 0 -and (
                Get-Content -Raw -Encoding utf8 $qaOutput | ConvertFrom-Json
            ).status -eq "pass") {
                $succeeded = $true
                Add-JsonLine $statusPath @{
                    at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                    case_id = $caseId; attempt = $attempt; status = "succeeded"
                }
                break
            }
            if (Test-Path $output) {
                $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
                Move-Item $output "$output.invalid-$stamp"
            }
        }
        if (-not $succeeded) {
            $failedCases += $caseId
            Add-JsonLine $failurePath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                case_id = $caseId; error = "P05 failed after retries"
            }
        }
    }
}

@{
    schema_version = "1.0"; stage = "P05-review"; prompt_version = "knowledge-v002-p05"
    status = $(if ($failedCases.Count -eq 0) { "complete" } else { "needs_review" })
    failed_cases = $failedCases; completed_at = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (
    Join-Path $batchDir "cursor-p05-knowledge-v002-complete.json"
)
