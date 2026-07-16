param(
    [string]$Workspace = "D:\Dev\VideoCaptioner",
    [string]$DataRoot = "D:\Dev\VideoCaptioner\data",
    [string]$PythonExe = "D:\Dev\VideoCaptioner\.venv\Scripts\python.exe",
    [string]$BatchId = "BATCH-20260715-001",
    [Parameter(Mandatory = $true)][string]$WaveId,
    [Parameter(Mandatory = $true)][int]$StartCourse,
    [Parameter(Mandatory = $true)][int]$EndCourse,
    [string]$OutputVersion = "knowledge-v003",
    [string]$PromptRoot = "prompts\knowledge-v003",
    [ValidateSet("P01", "P02", "P03", "P04")]
    [string]$ThroughStage = "P04",
    [string]$RunVersion = "V001"
)

<#
.SYNOPSIS
  Start an evidence-only knowledge wave that never launches P05/P06/finalizer.

.DESCRIPTION
  Starts resumable watchers for P01..ThroughStage only. Completion marker:
  data/batches/<BatchId>/evidence-pipeline-<WaveId>-complete.json
#>

$ErrorActionPreference = "Stop"
$batchDir = Join-Path $DataRoot "batches\$BatchId"
New-Item -ItemType Directory -Force -Path $batchDir | Out-Null
$stamp = Get-Date -Format "yyyyMMddTHHmmss"
$scripts = Join-Path $Workspace "scripts"

$stageOrder = @("P01", "P02", "P03", "P04")
$throughIndex = [array]::IndexOf($stageOrder, $ThroughStage)
if ($throughIndex -lt 0) {
    throw "ThroughStage must be one of P01/P02/P03/P04"
}
$enabled = $stageOrder[0..$throughIndex]

function Start-WaveWatcher {
    param(
        [string]$Name,
        [string]$ScriptPath,
        [string[]]$ScriptArgs
    )
    $stdout = Join-Path $batchDir "wave-$WaveId-$Name.$stamp.stdout.log"
    $stderr = Join-Path $batchDir "wave-$WaveId-$Name.$stamp.stderr.log"
    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $ScriptPath
    ) + $ScriptArgs
    $proc = Start-Process -FilePath "powershell.exe" `
        -PassThru `
        -WindowStyle Hidden `
        -ArgumentList $argList `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr
    [pscustomobject]@{
        name = $Name
        pid = $proc.Id
        stdout = $stdout
        stderr = $stderr
        script = $ScriptPath
    }
}

$common = @(
    "-DataRoot", $DataRoot,
    "-PythonExe", $PythonExe,
    "-Workspace", $Workspace,
    "-BatchId", $BatchId,
    "-WaveId", $WaveId,
    "-StartCourse", "$StartCourse",
    "-EndCourse", "$EndCourse",
    "-OutputVersion", $OutputVersion,
    "-PromptRoot", $PromptRoot
)

$started = @()
if ($enabled -contains "P01") {
    $started += Start-WaveWatcher -Name "p01" `
        -ScriptPath (Join-Path $scripts "wait_then_run_cursor_review.ps1") `
        -ScriptArgs ($common + @("-RunVersion", $RunVersion))
}
if ($enabled -contains "P02") {
    $started += Start-WaveWatcher -Name "p02" `
        -ScriptPath (Join-Path $scripts "wait_then_run_cursor_p02.ps1") `
        -ScriptArgs $common
}
if ($enabled -contains "P03") {
    $started += Start-WaveWatcher -Name "p03" `
        -ScriptPath (Join-Path $scripts "wait_then_run_cursor_p03.ps1") `
        -ScriptArgs $common
}
if ($enabled -contains "P04") {
    $started += Start-WaveWatcher -Name "p04" `
        -ScriptPath (Join-Path $scripts "wait_then_run_cursor_p04.ps1") `
        -ScriptArgs $common
}

# Evidence finalizer waits on the last enabled stage and never touches P05/P06.
$started += Start-WaveWatcher -Name "evidence-final" `
    -ScriptPath (Join-Path $scripts "wait_then_finalize_evidence.ps1") `
    -ScriptArgs @(
        "-DataRoot", $DataRoot,
        "-PythonExe", $PythonExe,
        "-Workspace", $Workspace,
        "-BatchId", $BatchId,
        "-WaveId", $WaveId,
        "-StartCourse", "$StartCourse",
        "-EndCourse", "$EndCourse",
        "-OutputVersion", $OutputVersion,
        "-ThroughStage", $ThroughStage
    )

$report = Join-Path $batchDir "wave-$WaveId-evidence-watchers-$stamp.json"
@{
    schema_version = "1.0"
    wave_id = $WaveId
    through_stage = $ThroughStage
    enabled_stages = $enabled
    output_version = $OutputVersion
    prompt_root = $PromptRoot
    started = $started
    forbidden_stages = @("P05", "P06", "finalizer")
} | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 -LiteralPath $report

$started | Format-Table -AutoSize
Write-Host "Evidence watcher report: $report"
Write-Host "Enabled stages: $($enabled -join ', ')"
Write-Host "Forbidden: P05, P06, knowledge finalizer"
