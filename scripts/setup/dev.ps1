# scripts/setup/dev.ps1
# One-command dev setup for arac-hasar-v2 on Windows / PowerShell.
#
# Usage:
#   pwsh -File scripts/setup/dev.ps1
# Or (from repo root):
#   .\scripts\setup\dev.ps1
#
# What it does:
#   1. Verify prereqs: pnpm, python 3.11, docker
#   2. pnpm install at repo root (workspace install)
#   3. docker compose up -d postgres redis minio minio-init
#   4. Create Python venv at services/backend/.venv, install requirements
#   5. Run Alembic migrations against the dockerized postgres
#   6. Print the URLs developers need

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path

function Section($msg) {
    Write-Host ""
    Write-Host "=== $msg ===" -ForegroundColor Cyan
}

function Check-Cmd($name, $hint) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-Host "MISSING: $name" -ForegroundColor Red
        Write-Host "        $hint" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  ok: $name ($($cmd.Source))" -ForegroundColor Green
}

# ---------- 1. Prereqs ----------
Section "Checking prerequisites"
Check-Cmd "pnpm"   "Install: npm i -g pnpm@9"
Check-Cmd "python" "Install Python 3.11 from python.org (must be on PATH)"
Check-Cmd "docker" "Install Docker Desktop and ensure the engine is running"

$pyVersion = (& python --version) 2>&1
if ($pyVersion -notmatch "3\.11") {
    Write-Host "WARN: $pyVersion (3.11.x recommended)" -ForegroundColor Yellow
} else {
    Write-Host "  ok: $pyVersion" -ForegroundColor Green
}

# Ensure docker daemon responds
try {
    docker info --format "{{.ServerVersion}}" | Out-Null
} catch {
    Write-Host "Docker daemon is not reachable. Start Docker Desktop." -ForegroundColor Red
    exit 1
}

# ---------- 2. pnpm install ----------
Section "pnpm install (workspace)"
Push-Location $RepoRoot
try {
    pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw "pnpm install failed" }
} finally {
    Pop-Location
}

# ---------- 3. Docker dev stack ----------
Section "Starting docker compose: postgres + redis + minio"
Push-Location $RepoRoot
try {
    docker compose up -d postgres redis minio minio-init
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }
} finally {
    Pop-Location
}

# ---------- 4. Backend venv + deps ----------
Section "Setting up backend venv at services/backend/.venv"
$BackendDir = Join-Path $RepoRoot "services\backend"
Push-Location $BackendDir
try {
    if (-not (Test-Path ".venv")) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
    }
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip wheel
    & .\.venv\Scripts\python.exe -m pip install `
        --extra-index-url https://download.pytorch.org/whl/cpu `
        "torch==2.3.1+cpu" "torchvision==0.18.1+cpu"
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
            Write-Host "  Copied .env.example -> .env (review before running)" -ForegroundColor Yellow
        }
    }
} finally {
    Pop-Location
}

# ---------- 5. Alembic migrations ----------
Section "Running Alembic migrations"
Push-Location $BackendDir
try {
    $env:DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/arac_hasar"
    # Wait briefly for postgres to be ready
    $tries = 0
    while ($tries -lt 30) {
        $ok = docker exec hasarui-postgres pg_isready -U postgres -d arac_hasar 2>&1
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 1
        $tries++
    }
    & .\.venv\Scripts\alembic.exe upgrade head
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARN: alembic upgrade failed (continuing — fix and rerun)." -ForegroundColor Yellow
    }
} finally {
    Pop-Location
}

# ---------- 6. Summary ----------
Section "Dev environment ready"
Write-Host ""
Write-Host "Endpoints:" -ForegroundColor Cyan
Write-Host "  Web (Next.js)    -> http://localhost:3000     (pnpm --filter web dev)"
Write-Host "  API (FastAPI)    -> http://localhost:8000/docs"
Write-Host "  MinIO console    -> http://localhost:9001     (minioadmin / minioadmin)"
Write-Host "  MinIO S3 API     -> http://localhost:9000"
Write-Host "  Postgres         -> postgresql://postgres:postgres@localhost:5432/arac_hasar"
Write-Host "  Redis            -> redis://localhost:6379/0"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Start backend (host):"
Write-Host "       cd services\backend"
Write-Host "       .\.venv\Scripts\Activate.ps1"
Write-Host "       uvicorn main:app --reload"
Write-Host "     or run dockerized:"
Write-Host "       docker compose up backend worker"
Write-Host ""
Write-Host "  2. Start web:"
Write-Host "       pnpm --filter @arac-hasar/web dev"
Write-Host ""
Write-Host "  3. Start desktop:"
Write-Host "       pnpm --filter @arac-hasar/desktop tauri dev"
Write-Host ""
Write-Host "  4. Start mobile (Expo):"
Write-Host "       pnpm --filter @arac-hasar/mobile start"
Write-Host ""
