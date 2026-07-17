param(
    [string]$DeployRoot = "D:\Dev\dify-deploy",
    [string]$BaseUrl = "http://127.0.0.1:3080",
    [string]$DatasetName = "",
    [string]$IndexingTechnique = "economy",
    [string]$ProjectName = "dify"
)
$ErrorActionPreference = "Stop"
$env:COMPOSE_PROJECT_NAME = $ProjectName

if ($IndexingTechnique -notin @("economy", "high_quality")) {
    throw "IndexingTechnique must be economy or high_quality"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..\..")
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$pyArgs = @(
    (Join-Path $scriptDir "dify_init_lib.py"),
    "--deploy-root", $DeployRoot,
    "--base-url", $BaseUrl,
    "dataset",
    "--indexing-technique", $IndexingTechnique
)
if ($DatasetName) {
    $pyArgs += @("--name", $DatasetName)
}

Write-Host "initialize-dataset: indexing=$IndexingTechnique"
& $python @pyArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "initialize-dataset: done"
