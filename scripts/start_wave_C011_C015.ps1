param(
    [string]$Workspace = "D:\Dev\VideoCaptioner",
    [string]$DataRoot = "D:\Dev\VideoCaptioner\data",
    [string]$PythonExe = "D:\Dev\VideoCaptioner\.venv\Scripts\python.exe",
    [string]$BatchId = "BATCH-20260715-001",
    [string]$WaveId = "C011-C015",
    [int]$StartCourse = 11,
    [int]$EndCourse = 15
)

$ErrorActionPreference = "Stop"
$batchDir = Join-Path $DataRoot "batches\$BatchId"
$stamp = Get-Date -Format "yyyyMMddTHHmmss"
$scripts = Join-Path $Workspace "scripts"

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
    "-EndCourse", "$EndCourse"
)

$started = @()
$started += Start-WaveWatcher -Name "p01" -ScriptPath (Join-Path $scripts "wait_then_run_cursor_review.ps1") -ScriptArgs ($common + @("-RunVersion", "V001"))
$started += Start-WaveWatcher -Name "p02" -ScriptPath (Join-Path $scripts "wait_then_run_cursor_p02.ps1") -ScriptArgs $common
$started += Start-WaveWatcher -Name "p03" -ScriptPath (Join-Path $scripts "wait_then_run_cursor_p03.ps1") -ScriptArgs $common
$started += Start-WaveWatcher -Name "p04" -ScriptPath (Join-Path $scripts "wait_then_run_cursor_p04.ps1") -ScriptArgs $common
$started += Start-WaveWatcher -Name "p05" -ScriptPath (Join-Path $scripts "wait_then_run_cursor_p05.ps1") -ScriptArgs $common
$started += Start-WaveWatcher -Name "p06" -ScriptPath (Join-Path $scripts "wait_then_run_cursor_p06.ps1") -ScriptArgs $common
$started += Start-WaveWatcher -Name "final" -ScriptPath (Join-Path $scripts "wait_then_finalize_knowledge.ps1") -ScriptArgs @(
    "-DataRoot", $DataRoot,
    "-PythonExe", $PythonExe,
    "-Workspace", $Workspace,
    "-BatchId", $BatchId,
    "-WaveId", $WaveId
)

$report = Join-Path $batchDir "wave-$WaveId-watchers-$stamp.json"
$started | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 -LiteralPath $report
$started | Format-Table -AutoSize
Write-Host "Watcher report: $report"
