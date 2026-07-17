param(
    [string]$DeployRoot = "D:\Dev\dify-deploy",
    [string]$ProjectName = "dify"
)
$ErrorActionPreference = "Stop"
$env:COMPOSE_PROJECT_NAME = $ProjectName
$dockerDir = Join-Path $DeployRoot "repo\docker"
Push-Location $dockerDir
try {
    # Volumes are preserved (no -v). Never targets unrelated projects such as cpa.
    docker compose -p $ProjectName down
} finally {
    Pop-Location
}
Write-Host "Dify compose project '$ProjectName' stopped. Other containers (e.g. cpa) were not targeted."

