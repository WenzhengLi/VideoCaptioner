param(
    [string]$DeployRoot = "D:\Dev\dify-deploy",
    [string]$BaseUrl = "http://127.0.0.1:3080",
    [string]$ProjectName = "dify",
    [string]$RepoRoot = ""
)
$ErrorActionPreference = "Stop"
$env:COMPOSE_PROJECT_NAME = $ProjectName

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
}
$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

function Write-Check([string]$Name, [bool]$Ok, [string]$Detail = "") {
    $mark = if ($Ok) { "PASS" } else { "FAIL" }
    if ($Detail) {
        Write-Host "[$mark] $Name — $Detail"
    } else {
        Write-Host "[$mark] $Name"
    }
}

Write-Host "=== smoke-test.ps1 (no secrets printed) ==="

# 1) Docker health for dify project only
$dockerDir = Join-Path $DeployRoot "repo\docker"
$difyOk = $false
if (Test-Path $dockerDir) {
    Push-Location $dockerDir
    try {
        $ps = docker compose -p $ProjectName ps --format json 2>$null
        $difyOk = $LASTEXITCODE -eq 0
    } finally {
        Pop-Location
    }
}
Write-Check "docker_project_dify" $difyOk

# 2) cpa untouched
$cpa = docker ps --format "{{.Names}}" | Where-Object { $_ -eq "cpa" }
Write-Check "cpa_8317_present" ([bool]$cpa)

# 3) HTTP + setup
$setupFinished = $false
try {
    $setup = Invoke-RestMethod -Uri "$BaseUrl/console/api/setup" -Method GET -TimeoutSec 20
    $setupFinished = ($setup.step -eq "finished")
    Write-Check "http_setup" $true "step=$($setup.step)"
} catch {
    Write-Check "http_setup" $false $_.Exception.Message
}

# 4) Admin / dataset / API credential files (existence only)
$adminEnv = Join-Path $DeployRoot "secrets\admin.env"
$runtimeEnv = Join-Path $DeployRoot "secrets\dify-runtime.env"
Write-Check "admin_env_present" (Test-Path $adminEnv)
Write-Check "runtime_env_present" (Test-Path $runtimeEnv)

$datasetApiOk = $false
$docsSynced = $false
$indexingNote = "not_checked"
$workflowPresent = Test-Path (Join-Path $RepoRoot "deploy\dify\workflows\afeng-chatflow.yml")
$retrieveNote = "not_checked"

if (Test-Path $runtimeEnv) {
    # Load env into process without printing values
    Get-Content $runtimeEnv | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
        $k, $v = $_.Split('=', 2)
        Set-Item -Path "Env:$($k.Trim())" -Value $v.Trim()
    }
    if ($env:DIFY_BASE_URL -and $env:DIFY_API_KEY -and $env:DIFY_DATASET_ID) {
        $code = @"
import json, os, urllib.request
base = os.environ['DIFY_BASE_URL'].rstrip('/')
key = os.environ['DIFY_API_KEY']
ds = os.environ['DIFY_DATASET_ID']
req = urllib.request.Request(
    f'{base}/datasets/{ds}',
    headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json'},
    method='GET',
)
with urllib.request.urlopen(req, timeout=30) as resp:
    body = json.loads(resp.read().decode('utf-8'))
print('dataset_ok', bool(body.get('id')))
print('doc_count', body.get('document_count') or body.get('app_count') or 0)
req2 = urllib.request.Request(
    f'{base}/datasets/{ds}/documents?page=1&limit=5',
    headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json'},
    method='GET',
)
with urllib.request.urlopen(req2, timeout=30) as resp2:
    docs = json.loads(resp2.read().decode('utf-8'))
items = docs.get('data') or []
print('documents_listed', len(items))
statuses = sorted({str(i.get('indexing_status') or i.get('display_status') or '') for i in items})
print('indexing_statuses', ','.join(statuses) if statuses else 'none')
# keyword retrieve probe (no embedding required)
payload = json.dumps({
    'query': 'C001',
    'retrieval_model': {
        'search_method': 'keyword_search',
        'reranking_enable': False,
        'top_k': 3,
        'score_threshold_enabled': False,
    },
}).encode('utf-8')
req3 = urllib.request.Request(
    f'{base}/datasets/{ds}/retrieve',
    data=payload,
    method='POST',
    headers={
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    },
)
with urllib.request.urlopen(req3, timeout=60) as resp3:
    retrieved = json.loads(resp3.read().decode('utf-8'))
hits = retrieved.get('records') or retrieved.get('data') or []
print('keyword_retrieve_ok', True)
print('keyword_hits', len(hits) if isinstance(hits, list) else 0)
"@
        $out = & $python -X utf8 -c $code 2>&1
        if ($LASTEXITCODE -eq 0) {
            $datasetApiOk = ($out | Select-String 'dataset_ok True') -ne $null
            $docsSynced = ($out | Select-String 'documents_listed').Line -match 'documents_listed [1-9]'
            $indexingNote = (($out | Select-String 'indexing_statuses').Line -replace 'indexing_statuses ', '')
            $hitLine = ($out | Select-String 'keyword_hits').Line
            $hitCount = 0
            if ($hitLine -match 'keyword_hits (\d+)') { $hitCount = [int]$Matches[1] }
            $retrieveNote = if (($out | Select-String 'keyword_retrieve_ok True')) { "keyword_hits=$hitCount" } else { "failed" }
            Write-Check "dataset_api" $datasetApiOk
            Write-Check "documents_present" $docsSynced
            Write-Host "[INFO] indexing_sample_statuses=$indexingNote"
            Write-Check "keyword_retrieve" (
                (($out | Select-String 'keyword_retrieve_ok True') -ne $null) -and ($hitCount -gt 0)
            ) "hits=$hitCount"
        } else {
            Write-Check "dataset_api" $false "query_failed"
            $retrieveNote = "query_failed"
        }
    } else {
        Write-Check "dataset_api" $false "runtime env incomplete"
    }
} else {
    Write-Check "dataset_api" $false "runtime env missing"
}

Write-Check "workflow_dsl_present" $workflowPresent "deploy/dify/workflows/afeng-chatflow.yml"
Write-Host "[INFO] retrieve_acceptance=$retrieveNote (semantic may require embedding provider)"
Write-Host "=== smoke-test complete ==="
if (-not ($difyOk -and $cpa -and $setupFinished -and (Test-Path $adminEnv))) {
    exit 1
}
exit 0
