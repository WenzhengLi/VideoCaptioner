param(
    [Parameter(Mandatory = $true)][string]$WaitJobDir,
    [Parameter(Mandatory = $true)][string]$CourseId,
    [Parameter(Mandatory = $true)][string]$RunId,
    [Parameter(Mandatory = $true)][string]$BatchId,
    [Parameter(Mandatory = $true)][int]$StartCourse,
    [Parameter(Mandatory = $true)][int]$EndCourse,
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string]$FfmpegBin,
    [string]$DataRoot = "data",
    [string]$JobsRoot = "jobs\batch",
    [int]$PollSeconds = 30
)

$ErrorActionPreference = "Stop"
$jobJson = Join-Path $WaitJobDir "job.json"

while ($true) {
    if (-not (Test-Path -LiteralPath $jobJson)) {
        throw "等待任务不存在: $jobJson"
    }
    $state = Get-Content -Raw -Encoding utf8 -LiteralPath $jobJson | ConvertFrom-Json
    $failed = $state.stages.PSObject.Properties |
        Where-Object { $_.Value.status -eq "failed" } |
        Select-Object -First 1
    if ($failed) {
        throw "等待任务失败: $($failed.Name): $($failed.Value.error)"
    }
    if ($state.stages.export.status -eq "completed") {
        break
    }
    Start-Sleep -Seconds $PollSeconds
}

& $PythonExe -m course_video_analyzer.knowledge.cli qa-run $CourseId $RunId `
    --data-root $DataRoot
if ($LASTEXITCODE -ne 0) {
    throw "QA 失败: $CourseId / $RunId"
}

& $PythonExe -m course_video_analyzer.knowledge.cli run-batch $BatchId `
    --data-root $DataRoot `
    --jobs-root $JobsRoot `
    --start $StartCourse `
    --end $EndCourse `
    --run-version V001 `
    --processing-profile complete-v1 `
    --timeout-seconds 14400 `
    --max-attempts 2 `
    --ffmpeg-bin $FfmpegBin
if ($LASTEXITCODE -ne 0) {
    throw "批次运行失败: $BatchId"
}
