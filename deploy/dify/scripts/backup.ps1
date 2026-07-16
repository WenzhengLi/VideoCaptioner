param(
    [string]$DeployRoot = "D:\Dev\dify-deploy",
    [string]$BackupRoot = "D:\Dev\dify-deploy\backups"
)
$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyyMMddTHHmmss"
$dest = Join-Path $BackupRoot $stamp
New-Item -ItemType Directory -Force -Path $dest | Out-Null

# Prefer named volumes from official compose; list and archive via docker run.
$volumes = docker volume ls --format "{{.Name}}" | Where-Object { $_ -match "dify|docker_" }
$volumes | Set-Content -Encoding utf8 (Join-Path $dest "volumes.txt")
foreach ($v in $volumes) {
    Write-Host "Archiving volume $v"
    docker run --rm -v "${v}:/volume:ro" -v "${dest}:/backup" alpine tar czf "/backup/${v}.tar.gz" -C /volume .
}
Write-Host "Backup written to $dest"
Write-Host "Also copy docker/.env manually to a secrets-safe location (not git)."
