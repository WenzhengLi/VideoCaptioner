param(
    [string]$DeployRoot = "D:\Dev\dify-deploy",
    [string]$BaseUrl = "http://127.0.0.1:3080",
    [string]$ProjectName = "dify"
)
$ErrorActionPreference = "Stop"
$env:COMPOSE_PROJECT_NAME = $ProjectName

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..\..")
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

Write-Host "initialize-admin: DeployRoot=$DeployRoot BaseUrl=$BaseUrl"
& $python (Join-Path $scriptDir "dify_init_lib.py") --deploy-root $DeployRoot --base-url $BaseUrl admin
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "initialize-admin: done (secrets under DeployRoot\secrets\admin.env; values not printed)"
