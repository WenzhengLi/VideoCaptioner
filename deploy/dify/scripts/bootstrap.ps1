param(
    [string]$DeployRoot = "D:\Dev\dify-deploy",
    [string]$GitTag = "1.15.0",
    [string]$RepoUrl = "https://github.com/langgenius/dify.git"
)

$ErrorActionPreference = "Stop"
$repoDir = Join-Path $DeployRoot "repo"
$dockerDir = Join-Path $repoDir "docker"

New-Item -ItemType Directory -Force -Path $DeployRoot | Out-Null

if (-not (Test-Path (Join-Path $repoDir ".git"))) {
    Write-Host "Cloning $RepoUrl @ $GitTag ..."
    git clone --branch $GitTag --depth 1 $RepoUrl $repoDir
} else {
    Write-Host "Repo exists: $repoDir"
    Push-Location $repoDir
    try {
        git fetch --tags --depth 1 origin $GitTag
        git checkout $GitTag
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path (Join-Path $dockerDir ".env"))) {
    Copy-Item (Join-Path $dockerDir ".env.example") (Join-Path $dockerDir ".env")
    Write-Host "Created docker/.env from official .env.example — edit secrets locally."
} else {
    Write-Host "docker/.env already present; not overwriting."
}

$exampleSrc = Join-Path $PSScriptRoot "..\.env.example"
$exampleDst = Join-Path $DeployRoot "videocaptioner.env.example"
Copy-Item -Force $exampleSrc $exampleDst
Write-Host "Bootstrap complete. Next: edit $dockerDir\.env then run up.ps1"
Write-Host "Pinned tag: $GitTag"
