#!/usr/bin/env bash
# scripts/setup/dev.sh
# One-command dev setup for arac-hasar-v2 on macOS / Linux / WSL.
#
# Usage:
#   bash scripts/setup/dev.sh
#
# What it does:
#   1. Verify prereqs: pnpm, python 3.11, docker
#   2. pnpm install at repo root (workspace install)
#   3. docker compose up -d postgres redis minio minio-init
#   4. Create Python venv at services/backend/.venv, install requirements
#   5. Run Alembic migrations against the dockerized postgres
#   6. Print the URLs developers need
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/services/backend"

section() { printf "\n\033[36m=== %s ===\033[0m\n" "$*"; }
ok()      { printf "  \033[32mok:\033[0m %s\n" "$*"; }
warn()    { printf "  \033[33mWARN:\033[0m %s\n" "$*"; }
die()     { printf "  \033[31mFAIL:\033[0m %s\n" "$*" >&2; exit 1; }

check_cmd() {
    local name="$1" hint="$2"
    if command -v "$name" >/dev/null 2>&1; then
        ok "$name -> $(command -v "$name")"
    else
        die "Missing $name. $hint"
    fi
}

# ---------- 1. Prereqs ----------
section "Checking prerequisites"
check_cmd pnpm   "Install with: npm i -g pnpm@9"
check_cmd python3 "Install Python 3.11 (https://www.python.org/downloads/)"
check_cmd docker "Install Docker (https://docs.docker.com/get-docker/)"

PY_VER="$(python3 --version 2>&1 || true)"
if [[ "${PY_VER}" != *"3.11"* ]]; then
    warn "${PY_VER} (3.11.x recommended)"
else
    ok "${PY_VER}"
fi

docker info >/dev/null 2>&1 || die "Docker daemon not reachable. Is the engine running?"

# ---------- 2. pnpm install ----------
section "pnpm install (workspace)"
( cd "${REPO_ROOT}" && pnpm install --frozen-lockfile )

# ---------- 3. Docker dev stack ----------
section "Starting docker compose: postgres + redis + minio"
( cd "${REPO_ROOT}" && docker compose up -d postgres redis minio minio-init )

# ---------- 4. Backend venv + deps ----------
section "Setting up backend venv at services/backend/.venv"
cd "${BACKEND_DIR}"
if [[ ! -d ".venv" ]]; then
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip wheel
pip install --extra-index-url https://download.pytorch.org/whl/cpu \
    "torch==2.3.1+cpu" "torchvision==0.18.1+cpu"
pip install -r requirements.txt

if [[ ! -f ".env" && -f ".env.example" ]]; then
    cp .env.example .env
    warn "Copied .env.example -> .env (review before running)"
fi

# ---------- 5. Alembic migrations ----------
section "Running Alembic migrations"
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/arac_hasar"
# Wait for postgres
for _ in $(seq 1 30); do
    if docker exec hasarui-postgres pg_isready -U postgres -d arac_hasar >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
alembic upgrade head || warn "alembic upgrade failed (fix migrations and rerun)."

# ---------- 6. Summary ----------
section "Dev environment ready"
cat <<EOF

Endpoints:
  Web (Next.js)    -> http://localhost:3000     (pnpm --filter web dev)
  API (FastAPI)    -> http://localhost:8000/docs
  MinIO console    -> http://localhost:9001     (minioadmin / minioadmin)
  MinIO S3 API     -> http://localhost:9000
  Postgres         -> postgresql://postgres:postgres@localhost:5432/arac_hasar
  Redis            -> redis://localhost:6379/0

Next steps:
  1. Start backend (host):
       cd services/backend
       source .venv/bin/activate
       uvicorn main:app --reload
     or run dockerized:
       docker compose up backend worker

  2. Start web:
       pnpm --filter @arac-hasar/web dev

  3. Start desktop:
       pnpm --filter @arac-hasar/desktop tauri dev

  4. Start mobile (Expo):
       pnpm --filter @arac-hasar/mobile start

EOF
