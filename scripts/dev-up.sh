#!/usr/bin/env bash
# scripts/dev-up.sh
# ---------------------------------------------------------------------------
# Smoke up + health verification for the local docker compose stack.
#
# Usage (from repo root):
#   ./scripts/dev-up.sh
#   ./scripts/dev-up.sh --rebuild       # force --build
#   ./scripts/dev-up.sh --infra-only    # only postgres/redis/minio
#
# What it does:
#   1. Pre-flight: docker daemon, port collisions (5432/6379/9000/9001/8000),
#      ML model snapshot directory.
#   2. docker compose up -d (infra first, then backend + worker).
#   3. Poll health endpoints (postgres / redis / minio / backend).
#   4. Print summary URLs.
# ---------------------------------------------------------------------------
set -euo pipefail

REBUILD=0
INFRA_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --rebuild)    REBUILD=1 ;;
        --infra-only) INFRA_ONLY=1 ;;
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

c_cyan='\033[36m'; c_grn='\033[32m'; c_ylw='\033[33m'; c_red='\033[31m'; c_off='\033[0m'
section() { printf "\n${c_cyan}=== %s ===${c_off}\n" "$*"; }
ok()      { printf "  ${c_grn}ok:${c_off} %s\n" "$*"; }
warn()    { printf "  ${c_ylw}warn:${c_off} %s\n" "$*"; }
fail()    { printf "  ${c_red}FAIL:${c_off} %s\n" "$*"; }

port_free() {
    local p="$1"
    if command -v ss >/dev/null 2>&1; then
        ! ss -ltn "( sport = :$p )" 2>/dev/null | grep -q ":$p"
    elif command -v lsof >/dev/null 2>&1; then
        ! lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1
    else
        return 0
    fi
}

# ---------- 1. Pre-flight ----------
section "Pre-flight checks"

if ! docker info --format "{{.ServerVersion}}" >/dev/null 2>&1; then
    fail "docker daemon not reachable. Start Docker / Docker Desktop."
    exit 1
fi
ok "docker daemon reachable"

for p in 5432 6379 9000 9001 8000; do
    if port_free "$p"; then
        ok "port $p free"
    else
        warn "port $p is already in use on the host"
    fi
done

DEFAULT_SNAPSHOT="$REPO_ROOT/services/ml/runs/bundles/full_20260515_044630/_SNAPSHOT_FOR_BUILD"
SNAPSHOT="${MODEL_SNAPSHOT_DIR:-$DEFAULT_SNAPSHOT}"
if [[ ! -d "$SNAPSHOT" ]]; then
    warn "ML snapshot dir missing: $SNAPSHOT"
    BUNDLE_ROOT="$REPO_ROOT/services/ml/runs/bundles"
    if [[ -d "$BUNDLE_ROOT" ]]; then
        CANDIDATE="$(find "$BUNDLE_ROOT" -maxdepth 1 -type d -name 'full_*' -printf '%T@ %p\n' 2>/dev/null \
                     | sort -nr | head -n1 | awk '{ $1=""; sub(/^ /, ""); print }')"
        if [[ -n "${CANDIDATE:-}" && -d "$CANDIDATE/_SNAPSHOT_FOR_BUILD" ]]; then
            export MODEL_SNAPSHOT_DIR="$CANDIDATE/_SNAPSHOT_FOR_BUILD"
            ok "fallback snapshot dir set: $MODEL_SNAPSHOT_DIR"
        else
            warn "no _SNAPSHOT_FOR_BUILD under bundles/; backend will start without ML weights"
        fi
    fi
else
    ok "model snapshot dir: $SNAPSHOT"
fi

# ---------- 2. Compose up ----------
section "docker compose up (infrastructure)"
docker compose up -d postgres redis minio minio-init
ok "infra services started"

if [[ "$INFRA_ONLY" -eq 0 ]]; then
    section "docker compose up (backend + worker)"
    if [[ "$REBUILD" -eq 1 ]]; then
        docker compose up -d --build backend worker
    else
        docker compose up -d backend worker
    fi
    ok "backend + worker started"
fi

# ---------- 3. Health checks ----------
section "Health checks"

wait_for() {
    local name="$1"; local timeout="$2"; shift 2
    local deadline=$(( $(date +%s) + timeout ))
    while [[ "$(date +%s)" -lt "$deadline" ]]; do
        if "$@" >/dev/null 2>&1; then
            ok "$name healthy"
            return 0
        fi
        sleep 2
    done
    fail "$name did not become healthy within ${timeout}s"
    return 1
}

all_healthy=0

wait_for "postgres" 60 docker exec hasarui-postgres pg_isready -U postgres -d arac_hasar || all_healthy=1
wait_for "redis"    30 bash -c 'test "$(docker exec hasarui-redis redis-cli ping)" = "PONG"' || all_healthy=1
wait_for "minio"    45 curl -fsS http://localhost:9000/minio/health/live || all_healthy=1

if [[ "$INFRA_ONLY" -eq 0 ]]; then
    wait_for "backend /health" 180 curl -fsS http://localhost:8000/health || all_healthy=1
fi

# ---------- 4. Summary ----------
section "Summary"
docker compose ps
printf "\n${c_cyan}URLs:${c_off}\n"
echo  "  API health    -> http://localhost:8000/health"
echo  "  API docs      -> http://localhost:8000/docs"
echo  "  MinIO console -> http://localhost:9001  (minioadmin / minioadmin)"
echo  "  Postgres      -> postgresql://postgres:postgres@localhost:5432/arac_hasar"
echo
echo  "Next: pnpm --filter @arac-hasar/web dev   # http://localhost:3000"

exit "$all_healthy"
