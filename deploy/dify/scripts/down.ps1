param([string]$DeployRoot = "D:\Dev\dify-deploy")
$ErrorActionPreference = "Stop"
$dockerDir = Join-Path $DeployRoot "repo\docker"
Push-Location $dockerDir
try {
    docker compose down
} finally {
    Pop-Location
}
Write-Host "Dify compose stopped. Other containers (e.g. cpa) were not targeted."
