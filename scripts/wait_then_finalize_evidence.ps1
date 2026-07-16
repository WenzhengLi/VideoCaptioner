param(
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [string]$Workspace = "D:\Dev\VideoCaptioner",
    [string]$BatchId = "BATCH-20260715-001",
    [Parameter(Mandatory = $true)][string]$WaveId,
    [Parameter(Mandatory = $true)][int]$StartCourse,
    [Parameter(Mandatory = $true)][int]$EndCourse,
    [string]$OutputVersion = "knowledge-v003",
    [ValidateSet("P01", "P02", "P03", "P04")]
    [string]$ThroughStage = "P04",
    [int]$PollSeconds = 30
)

$ErrorActionPreference = "Stop"
$batchDir = Join-Path $DataRoot "batches\$BatchId"
$waveSuffix = "-$WaveId"

$stageCompleteMap = @{
    P01 = "cursor-p01-${OutputVersion}-p01$waveSuffix-complete.json"
    P02 = "cursor-p02-${OutputVersion}$waveSuffix-complete.json"
    P03 = "cursor-p03-${OutputVersion}$waveSuffix-complete.json"
    P04 = "cursor-p04-${OutputVersion}$waveSuffix-complete.json"
}

$waitFile = Join-Path $batchDir $stageCompleteMap[$ThroughStage]
while (-not (Test-Path -LiteralPath $waitFile)) {
    Start-Sleep -Seconds $PollSeconds
}
$marker = Get-Content -Raw -Encoding utf8 -LiteralPath $waitFile | ConvertFrom-Json
if ($marker.status -ne "complete") {
    throw "Upstream stage marker is not complete: $waitFile"
}

& $PythonExe -m course_video_analyzer.knowledge.cli finalize-evidence-wave `
    --data-root $DataRoot `
    --batch-id $BatchId `
    --wave-id $WaveId `
    --start $StartCourse `
    --end $EndCourse `
    --output-version $OutputVersion `
    --through-stage $ThroughStage
if ($LASTEXITCODE -ne 0) {
    throw "finalize-evidence-wave failed"
}
