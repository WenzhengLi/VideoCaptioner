param(
    [string]$DeployRoot = "D:\Dev\dify-deploy",
    [string]$BackupRoot = "D:\Dev\dify-deploy\backups"
)
$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyyMMddTHHmmss"
$dest = Join-Path $BackupRoot $stamp
New-Item -ItemType Directory -Force -Path $dest | Out-Null

# Official compose primarily uses bind mounts under repo/docker/volumes/.
$bindVolumes = Join-Path $DeployRoot "repo\docker\volumes"
if (Test-Path $bindVolumes) {
    Write-Host "Archiving bind-mount volumes from $bindVolumes"
    tar -czf (Join-Path $dest "docker-volumes-bind.tar.gz") -C (Split-Path $bindVolumes -Parent) "volumes"
} else {
    Write-Host "No bind-mount volumes dir at $bindVolumes"
}

# Also archive any named Docker volumes matching dify/docker_ (rarely used by default).
$volumes = docker volume ls --format "{{.Name}}" | Where-Object { $_ -match "dify|docker_" }
$volumes | Set-Content -Encoding utf8 (Join-Path $dest "named-volumes.txt")
foreach ($v in $volumes) {
    Write-Host "Archiving named volume $v"
    docker run --rm -v "${v}:/volume:ro" -v "${dest}:/backup" alpine tar czf "/backup/${v}.tar.gz" -C /volume .
}
Write-Host "Backup written to $dest"
Write-Host "Also copy docker/.env manually to a secrets-safe location (not git)."
