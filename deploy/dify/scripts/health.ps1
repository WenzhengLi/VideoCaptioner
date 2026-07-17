param(
    [string]$DeployRoot = "D:\Dev\dify-deploy",
    [string]$BaseUrl = "http://127.0.0.1:3080",
    [string]$ProjectName = "dify"
)
$ErrorActionPreference = "Stop"
$env:COMPOSE_PROJECT_NAME = $ProjectName

Write-Host "=== docker compose ps (project=$ProjectName only) ==="
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
    exit 1
}

Write-Host "=== cpa guard (must remain on 8317) ==="
$cpa = docker ps --format "{{.Names}}\t{{.Ports}}" | Where-Object { $_ -match '^cpa\b' }
if (-not $cpa) {
    Write-Host "WARNING: cpa container not found"
} else {
    Write-Host "cpa: present — $cpa"
}

Write-Host "=== HTTP probe $BaseUrl ==="
try {
    $resp = Invoke-WebRequest -Uri $BaseUrl -UseBasicParsing -TimeoutSec 15
    Write-Host "HTTP $($resp.StatusCode)"
} catch {
    if ($_.Exception.Response) {
        Write-Host "HTTP $([int]$_.Exception.Response.StatusCode) (reachable)"
    } else {
        Write-Host "HTTP probe failed: $($_.Exception.Message)"
        exit 1
    }
}

Write-Host "=== setup status ==="
try {
    $setup = Invoke-RestMethod -Uri "$BaseUrl/console/api/setup" -Method GET -TimeoutSec 15
    Write-Host "setup.step=$($setup.step)"
} catch {
    Write-Host "setup probe failed: $($_.Exception.Message)"
    exit 1
}

Write-Host "=== local init markers (no secret values) ==="
$checks = @(
    @{ Name = "admin_env"; Path = (Join-Path $DeployRoot "secrets\admin.env") },
    @{ Name = "runtime_env"; Path = (Join-Path $DeployRoot "secrets\dify-runtime.env") },
    @{ Name = "bootstrap_status"; Path = (Join-Path $DeployRoot "bootstrap-status.json") }
)
foreach ($item in $checks) {
    if (Test-Path $item.Path) {
        Write-Host "$($item.Name)=present"
    } else {
        Write-Host "$($item.Name)=missing"
    }
}

Write-Host "=== health.ps1 complete ==="
