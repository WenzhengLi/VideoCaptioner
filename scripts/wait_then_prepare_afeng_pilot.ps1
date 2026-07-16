param(
    [string]$Workspace = "D:\Dev\VideoCaptioner",
    [string]$Baseline = "data\catalog\evidence-baseline-C001-C015.json",
    [string]$PilotId = "C003-C006-C010-baseline-v001",
    [string]$Courses = "C003,C006,C010",
    [string]$OutputRoot = "data\afeng\pilots",
    [int]$PollSeconds = 30,
    [int]$TimeoutSeconds = 43200
)

$ErrorActionPreference = "Stop"
$workspacePath = (Resolve-Path -LiteralPath $Workspace).Path
$baselinePath = Join-Path $workspacePath $Baseline
$python = Join-Path $workspacePath ".venv\Scripts\python.exe"
$script = Join-Path $workspacePath "scripts\prepare_afeng_pilot.py"
$started = Get-Date

while (-not (Test-Path -LiteralPath $baselinePath)) {
    if (((Get-Date) - $started).TotalSeconds -ge $TimeoutSeconds) {
        throw "Timed out waiting for evidence baseline: $baselinePath"
    }
    Start-Sleep -Seconds $PollSeconds
}

& $python $script `
    --data-root (Join-Path $workspacePath "data") `
    --baseline $baselinePath `
    --courses $Courses `
    --pilot-id $PilotId `
    --output-root (Join-Path $workspacePath $OutputRoot) `
    --external-segment-profile evidence_focused `
    --external-context-window 1

if ($LASTEXITCODE -ne 0) {
    throw "Afeng pilot preparation failed with exit code $LASTEXITCODE"
}
