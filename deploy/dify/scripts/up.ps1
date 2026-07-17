param(
    [string]$DeployRoot = "D:\Dev\dify-deploy",
    [string]$ProjectName = "dify"
)
$ErrorActionPreference = "Stop"
$env:COMPOSE_PROJECT_NAME = $ProjectName
$dockerDir = Join-Path $DeployRoot "repo\docker"
if (-not (Test-Path (Join-Path $dockerDir "docker-compose.yaml")) -and -not (Test-Path (Join-Path $dockerDir "docker-compose.yml"))) {
    throw "Missing official compose under $dockerDir — run bootstrap.ps1 first."
}
# Do not touch unrelated containers (e.g. cpa). Scope strictly to this compose project.
Push-Location $dockerDir
try {
    docker compose -p $ProjectName up -d
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up failed with exit code $LASTEXITCODE"
    }
    docker compose -p $ProjectName ps
} finally {
    Pop-Location
}

