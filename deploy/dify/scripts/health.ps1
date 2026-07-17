param(
    [string]$DeployRoot = "D:\Dev\dify-deploy",
    [string]$BaseUrl = "http://127.0.0.1:3080",
    [string]$ProjectName = "dify"
)
$ErrorActionPreference = "Stop"
$env:COMPOSE_PROJECT_NAME = $ProjectName
Write-Host "=== docker compose ps (project=$ProjectName) ==="
$dockerDir = Join-Path $DeployRoot "repo\docker"
if (Test-Path $dockerDir) {
    Push-Location $dockerDir
    try {
        docker compose -p $ProjectName ps
    } finally {
        Pop-Location
    }
} else {
    Write-Host "Missing $dockerDir — run bootstrap.ps1 first."
}
Write-Host "=== docker ps (all) - ensure cpa still present ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}"
$cpa = docker ps --format "{{.Names}}" | Where-Object { $_ -eq "cpa" }
if (-not $cpa) {
    Write-Host "WARNING: cpa container not found in docker ps"
} else {
    Write-Host "cpa: present"
}
Write-Host "=== HTTP probe $BaseUrl ==="
try {
    $resp = Invoke-WebRequest -Uri $BaseUrl -UseBasicParsing -TimeoutSec 15
    Write-Host "HTTP $($resp.StatusCode)"
} catch {
    # /install may redirect or return non-200 before admin setup; still treat reachability.
    $msg = $_.Exception.Message
    if ($_.Exception.Response) {
        Write-Host "HTTP $([int]$_.Exception.Response.StatusCode) (reachable)"
    } else {
        Write-Host "HTTP probe failed (expected if not started): $msg"
        exit 1
    }
}
Write-Host "=== health.ps1 complete ==="

