param(
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [string]$Workspace = "D:\Dev\VideoCaptioner",
    [string]$BatchId = "BATCH-20260715-001",
    [int]$PollSeconds = 30
)

$ErrorActionPreference = "Stop"
$batchDir = Join-Path $DataRoot "batches\$BatchId"
$p06Complete = Join-Path $batchDir "cursor-p06-knowledge-v002-complete.json"
while (-not (Test-Path $p06Complete)) { Start-Sleep -Seconds $PollSeconds }
$marker = Get-Content -Raw -Encoding utf8 $p06Complete | ConvertFrom-Json
if ($marker.status -ne "complete") { throw "P06 batch marker is not complete" }

$tidyDir = Join-Path $DataRoot "tidy"
New-Item -ItemType Directory -Force -Path $tidyDir | Out-Null
$database = Join-Path $tidyDir "knowledge.db"
& $PythonExe -m course_video_analyzer.knowledge.cli index-tidy `
    --data-root $DataRoot --database $database
if ($LASTEXITCODE -ne 0) { throw "Tidy index failed" }

$answer = Join-Path $tidyDir "smoke-answer.json"
if (Test-Path $answer) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    Move-Item $answer "$answer.previous-$stamp"
}
$query = Get-Content -Raw -Encoding utf8 (
    Join-Path $Workspace "prompts\knowledge-v002\smoke-query.txt"
)
& $PythonExe -m course_video_analyzer.knowledge.cli answer-tidy `
    $query `
    $answer --database $database --workspace $Workspace --limit 8
if ($LASTEXITCODE -ne 0) { throw "Knowledge answer smoke test failed" }

Push-Location $Workspace
try {
    & $PythonExe -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Full pytest failed" }
} finally {
    Pop-Location
}

@{
    schema_version = "1.0"
    status = "complete"
    database = $database
    smoke_answer = $answer
    completed_at = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (
    Join-Path $batchDir "knowledge-pipeline-complete.json"
)
