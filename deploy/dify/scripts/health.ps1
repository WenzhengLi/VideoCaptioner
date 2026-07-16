param(
    [string]$DeployRoot = "D:\Dev\dify-deploy",
    [string]$BaseUrl = "http://127.0.0.1:3080"
)
$ErrorActionPreference = "Stop"
Write-Host "=== docker compose ps ==="
$dockerDir = Join-Path $DeployRoot "repo\docker"
if (Test-Path $dockerDir) {
    Push-Location $dockerDir
    try { docker compose ps } finally { Pop-Location }
}
Write-Host "=== docker ps (all) — ensure cpa still present ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
Write-Host "=== HTTP probe $BaseUrl ==="
try {
    $resp = Invoke-WebRequest -Uri $BaseUrl -UseBasicParsing -TimeoutSec 10
    Write-Host "HTTP $($resp.StatusCode)"
} catch {
    Write-Host "HTTP probe failed (expected if not started): $($_.Exception.Message)"
}
