param([string]$DeployRoot = "D:\Dev\dify-deploy")
$ErrorActionPreference = "Stop"
$dockerDir = Join-Path $DeployRoot "repo\docker"
if (-not (Test-Path (Join-Path $dockerDir "docker-compose.yaml")) -and -not (Test-Path (Join-Path $dockerDir "docker-compose.yml"))) {
    throw "Missing official compose under $dockerDir — run bootstrap.ps1 first."
}
# Do not touch unrelated containers (e.g. cpa).
Push-Location $dockerDir
try {
    docker compose up -d
    docker compose ps
} finally {
    Pop-Location
}
