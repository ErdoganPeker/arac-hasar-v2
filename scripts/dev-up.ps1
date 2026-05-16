# scripts/dev-up.ps1
# ---------------------------------------------------------------------------
# Smoke up + health verification for the local docker compose stack.
#
# Usage (from repo root):
#   pwsh -File scripts/dev-up.ps1
#   pwsh -File scripts/dev-up.ps1 -Rebuild      # force --build
#   pwsh -File scripts/dev-up.ps1 -InfraOnly    # only postgres/redis/minio
#
# What it does:
#   1. Pre-flight: docker daemon, port collisions (5432/6379/9000/9001/8000),
#      ML model snapshot directory.
#   2. docker compose up -d (infra first, then backend + worker).
#   3. Poll health endpoints:
#        - postgres pg_isready
#        - redis PING
#        - minio /minio/health/live
#        - backend http://localhost:8000/health
#   4. Print summary URLs.
# ---------------------------------------------------------------------------
[CmdletBinding()]
param(
    [switch]$Rebuild,
    [switch]$InfraOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
Push-Location $RepoRoot

function Section($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function OK($msg)      { Write-Host "  ok: $msg" -ForegroundColor Green }
function Warn($msg)    { Write-Host "  warn: $msg" -ForegroundColor Yellow }
function Fail($msg)    { Write-Host "  FAIL: $msg" -ForegroundColor Red }

function Test-Port($port) {
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
        $listener.Start()
        return $true   # free
    } catch {
        return $false  # in use
    } finally {
        if ($listener) { $listener.Stop() }
    }
}

# ---------- 1. Pre-flight ----------
Section "Pre-flight checks"

try { docker info --format "{{.ServerVersion}}" | Out-Null; OK "docker daemon reachable" }
catch { Fail "docker daemon not reachable. Start Docker Desktop."; Pop-Location; exit 1 }

$ports = @(5432, 6379, 9000, 9001, 8000)
$collisions = @()
foreach ($p in $ports) {
    if (-not (Test-Port $p)) {
        $collisions += $p
        Warn "port $p is already in use on the host"
    } else {
        OK "port $p free"
    }
}
if ($collisions.Count -gt 0) {
    Warn "Port collisions: $($collisions -join ', '). 'docker compose up' will fail to bind these."
    Warn "Stop the conflicting process or edit docker-compose.yml port mappings."
}

# Model snapshot dir check (override via MODEL_SNAPSHOT_DIR)
$defaultSnapshot = Join-Path $RepoRoot "services\ml\runs\bundles\full_20260515_044630\_SNAPSHOT_FOR_BUILD"
$snapshot = if ($env:MODEL_SNAPSHOT_DIR) { $env:MODEL_SNAPSHOT_DIR } else { $defaultSnapshot }
if (-not (Test-Path $snapshot)) {
    Warn "ML snapshot dir missing: $snapshot"
    # Try fallback: most recent bundle under services/ml/runs/bundles/
    $bundleRoot = Join-Path $RepoRoot "services\ml\runs\bundles"
    if (Test-Path $bundleRoot) {
        $candidate = Get-ChildItem $bundleRoot -Directory -Filter "full_*" |
                     Sort-Object LastWriteTime -Descending |
                     Select-Object -First 1
        if ($candidate) {
            $fallback = Join-Path $candidate.FullName "_SNAPSHOT_FOR_BUILD"
            if (Test-Path $fallback) {
                $env:MODEL_SNAPSHOT_DIR = $fallback
                OK "fallback snapshot dir set: $fallback"
            } else {
                Warn "No _SNAPSHOT_FOR_BUILD under $($candidate.FullName). Backend will start without ML weights."
            }
        }
    }
} else {
    OK "model snapshot dir: $snapshot"
}

# ---------- 2. Compose up ----------
Section "docker compose up (infrastructure)"
$buildFlag = if ($Rebuild) { "--build" } else { "" }

# Infra first so dependencies resolve cleanly.
$infraServices = @("postgres", "redis", "minio", "minio-init")
& docker compose up -d @infraServices
if ($LASTEXITCODE -ne 0) { Fail "docker compose up (infra) failed"; Pop-Location; exit 1 }
OK "infra services started"

if (-not $InfraOnly) {
    Section "docker compose up (backend + worker)"
    $appServices = @("backend", "worker")
    if ($Rebuild) {
        & docker compose up -d --build @appServices
    } else {
        & docker compose up -d @appServices
    }
    if ($LASTEXITCODE -ne 0) { Fail "docker compose up (app) failed"; Pop-Location; exit 1 }
    OK "backend + worker started"
}

# ---------- 3. Health checks ----------
Section "Health checks"

function Wait-For($name, [ScriptBlock]$probe, [int]$timeoutSec = 90) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            if (& $probe) { OK "$name healthy"; return $true }
        } catch { }
        Start-Sleep -Seconds 2
    }
    Fail "$name did not become healthy within ${timeoutSec}s"
    return $false
}

$allHealthy = $true

$allHealthy = (Wait-For "postgres" {
    docker exec hasarui-postgres pg_isready -U postgres -d arac_hasar 2>&1 | Out-Null
    $LASTEXITCODE -eq 0
} 60) -and $allHealthy

$allHealthy = (Wait-For "redis" {
    (docker exec hasarui-redis redis-cli ping 2>&1).Trim() -eq "PONG"
} 30) -and $allHealthy

$allHealthy = (Wait-For "minio" {
    try {
        $r = Invoke-WebRequest "http://localhost:9000/minio/health/live" -UseBasicParsing -TimeoutSec 3
        $r.StatusCode -eq 200
    } catch { $false }
} 45) -and $allHealthy

if (-not $InfraOnly) {
    $allHealthy = (Wait-For "backend /health" {
        try {
            $r = Invoke-WebRequest "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 3
            $r.StatusCode -eq 200
        } catch { $false }
    } 180) -and $allHealthy
}

# ---------- 4. Summary ----------
Section "Summary"
docker compose ps
Write-Host ""
Write-Host "URLs:" -ForegroundColor Cyan
Write-Host "  API health   -> http://localhost:8000/health"
Write-Host "  API docs     -> http://localhost:8000/docs"
Write-Host "  MinIO console -> http://localhost:9001  (minioadmin / minioadmin)"
Write-Host "  Postgres     -> postgresql://postgres:postgres@localhost:5432/arac_hasar"
Write-Host ""
Write-Host "Next: pnpm --filter @arac-hasar/web dev   # http://localhost:3000"

Pop-Location
if (-not $allHealthy) { exit 1 }
