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
    [string]$PromptRoot = "prompts\knowledge-v002"
)

$ErrorActionPreference = "Stop"
$batchDir = Join-Path $DataRoot "batches\$BatchId"
$waveSuffix = if ([string]::IsNullOrWhiteSpace($WaveId)) { "" } else { "-$WaveId" }
$p03Complete = Join-Path $batchDir "cursor-p03-${OutputVersion}$waveSuffix-complete.json"
$statusPath = Join-Path $batchDir "cursor-p04-${OutputVersion}$waveSuffix-status.jsonl"
$failurePath = Join-Path $batchDir "cursor-p04-${OutputVersion}$waveSuffix-failures.jsonl"

function Add-JsonLine {
    param([string]$Path, [hashtable]$Value)
    Add-Content -LiteralPath $Path -Encoding utf8 -Value (
        $Value | ConvertTo-Json -Compress -Depth 8
    )
}

while (-not (Test-Path -LiteralPath $p03Complete)) {
    Start-Sleep -Seconds $PollSeconds
}

$p03Marker = Get-Content -Raw -Encoding utf8 -LiteralPath $p03Complete | ConvertFrom-Json
if ($p03Marker.status -ne "complete") {
    throw "P03 batch marker is not complete"
}

$failedCases = @()
for ($ordinal = $StartCourse; $ordinal -le $EndCourse; $ordinal++) {
    $courseId = "C{0:D3}" -f $ordinal
    $p02 = Join-Path $DataRoot "courses\$courseId\02_normalized\P02-${OutputVersion}.json"
    $p03 = Join-Path $DataRoot "courses\$courseId\03_cases\P03-${OutputVersion}.json"
    $p03Qa = Join-Path $DataRoot "courses\$courseId\qa\P03-${OutputVersion}-qa.json"
    if (-not (Test-Path $p02) -or -not (Test-Path $p03) -or -not (Test-Path $p03Qa)) {
        Add-JsonLine $failurePath @{
            at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
            error = "P02/P03/P03 QA missing"
        }
        $failedCases += "${courseId}:*"
        continue
    }
    if ((Get-Content -Raw -Encoding utf8 $p03Qa | ConvertFrom-Json).status -ne "pass") {
        Add-JsonLine $failurePath @{
            at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
            error = "P03 QA did not pass"
        }
        $failedCases += "${courseId}:*"
        continue
    }
    $p03Data = Get-Content -Raw -Encoding utf8 $p03 | ConvertFrom-Json
    foreach ($case in $p03Data.cases) {
        $caseId = [string]$case.case_id
        $caseDir = Join-Path $DataRoot "courses\$courseId\04_knowledge\P04-${OutputVersion}"
        $inputDir = Join-Path $DataRoot "courses\$courseId\04_knowledge\P04-input-${OutputVersion}"
        New-Item -ItemType Directory -Force -Path $caseDir, $inputDir | Out-Null
        $caseInput = Join-Path $inputDir "$caseId.json"
        $output = Join-Path $caseDir "$caseId.json"
        $qaOutput = Join-Path $DataRoot "courses\$courseId\qa\P04-$caseId-${OutputVersion}-qa.json"
        if ((Test-Path $output) -and (Test-Path $qaOutput)) {
            try {
                if ((Get-Content -Raw -Encoding utf8 $qaOutput | ConvertFrom-Json).status -eq "pass") {
                    Add-JsonLine $statusPath @{
                        at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                        case_id = $caseId; status = "skipped_existing_valid"
                    }
                    continue
                }
            } catch {
            }
        }
        if (-not (Test-Path $caseInput)) {
            & $PythonExe -m course_video_analyzer.knowledge.cli build-p04-input `
                $courseId $caseId $p02 $p03 $caseInput
            if ($LASTEXITCODE -ne 0) {
                $failedCases += $caseId
                Add-JsonLine $failurePath @{
                    at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                    case_id = $caseId; error = "P04 case input build failed"
                }
                continue
            }
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
                $courseId P04 $caseInput $output `
                --workspace $Workspace --model auto `
                --prompt-root $PromptRoot --timeout-seconds 1800 `
                --finish-on-stable-output --output-stability-seconds 60
            if ($LASTEXITCODE -ne 0) {
                Add-JsonLine $failurePath @{
                    at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                    case_id = $caseId; attempt = $attempt; error = "Cursor P04 extraction failed"
                }
                continue
            }
            & $PythonExe -m course_video_analyzer.knowledge.cli qa-p04 `
                $courseId $caseId $caseInput $output $qaOutput `
                --prompt-version "${OutputVersion}-p04"
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
            Add-JsonLine $failurePath @{
                at = [DateTime]::UtcNow.ToString("o"); course_id = $courseId
                case_id = $caseId; attempt = $attempt; error = "P04 QA did not pass"
            }
            if (Test-Path $output) {
                $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
                Move-Item $output "$output.invalid-$stamp"
            }
        }
        if (-not $succeeded) {
            $failedCases += $caseId
        }
    }
}

@{
    schema_version = "1.0"
    stage = "P04-extract"
    prompt_version = "${OutputVersion}-p04"
    status = $(if ($failedCases.Count -eq 0) { "complete" } else { "needs_review" })
    failed_cases = $failedCases
    completed_at = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 -LiteralPath (
    Join-Path $batchDir "cursor-p04-${OutputVersion}$waveSuffix-complete.json"
)
