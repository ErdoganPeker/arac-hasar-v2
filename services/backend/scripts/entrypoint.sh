#!/usr/bin/env bash
# services/backend/scripts/entrypoint.sh
# ----------------------------------------------------------------------
# Container entrypoint for hasarui-api / hasarui-worker.
# Responsibilities:
#   1. If models are not already present in $MODEL_DIR, download them
#      from S3 ($MODEL_S3_BUCKET / $MODEL_S3_PREFIX).
#      Skip entirely when SKIP_MODEL_FETCH=1 (Dockerfile.embedded).
#   2. Run Alembic migrations (web service only — controlled by
#      RUN_MIGRATIONS=1; workers should set RUN_MIGRATIONS=0).
#   3. exec "$@" — replace shell with the actual CMD (uvicorn / celery).
# ----------------------------------------------------------------------
set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/app/models}"
REQUIRED_WEIGHTS=("damage_best.pt" "parts_best.pt" "severity_best.pt")

log() { echo "[entrypoint] $*" >&2; }

# -------- 1. Model fetch --------
fetch_models() {
    if [[ "${SKIP_MODEL_FETCH:-0}" == "1" ]]; then
        log "SKIP_MODEL_FETCH=1 — assuming weights baked into image at ${MODEL_DIR}"
        return 0
    fi

    local missing=0
    for w in "${REQUIRED_WEIGHTS[@]}"; do
        if [[ ! -f "${MODEL_DIR}/${w}" ]]; then
            missing=1
            break
        fi
    done

    if [[ "${missing}" == "0" ]]; then
        log "All weights already present in ${MODEL_DIR}, skipping fetch."
        return 0
    fi

    if [[ -z "${MODEL_S3_BUCKET:-}" ]]; then
        log "ERROR: MODEL_S3_BUCKET not set and weights missing. Cannot start."
        log "       Set MODEL_S3_BUCKET + MODEL_S3_PREFIX, or rebuild with Dockerfile.embedded."
        exit 1
    fi

    local prefix="${MODEL_S3_PREFIX:-models/full_20260515_044630}"
    log "Fetching weights from s3://${MODEL_S3_BUCKET}/${prefix}/ -> ${MODEL_DIR}/"

    python - <<PYEOF
import os, sys, boto3
from botocore.config import Config

bucket  = os.environ["MODEL_S3_BUCKET"]
prefix  = os.environ.get("MODEL_S3_PREFIX", "models/full_20260515_044630").rstrip("/")
target  = os.environ.get("MODEL_DIR", "/app/models")
weights = ["damage_best.pt", "parts_best.pt", "severity_best.pt"]

kwargs = {}
if os.environ.get("S3_ENDPOINT"):
    kwargs["endpoint_url"] = os.environ["S3_ENDPOINT"]
if os.environ.get("S3_REGION"):
    kwargs["region_name"] = os.environ["S3_REGION"]
if os.environ.get("S3_ACCESS_KEY"):
    kwargs["aws_access_key_id"] = os.environ["S3_ACCESS_KEY"]
    kwargs["aws_secret_access_key"] = os.environ["S3_SECRET_KEY"]

s3 = boto3.client("s3", config=Config(retries={"max_attempts": 5, "mode": "standard"}), **kwargs)
os.makedirs(target, exist_ok=True)
for w in weights:
    dst = os.path.join(target, w)
    if os.path.isfile(dst):
        print(f"[entrypoint]   {w} already cached, skipping.", file=sys.stderr)
        continue
    key = f"{prefix}/{w}"
    print(f"[entrypoint]   downloading s3://{bucket}/{key} -> {dst}", file=sys.stderr)
    s3.download_file(bucket, key, dst)
print("[entrypoint] All weights fetched.", file=sys.stderr)
PYEOF
}

# -------- 2. DB migrations --------
run_migrations() {
    if [[ "${RUN_MIGRATIONS:-0}" != "1" ]]; then
        return 0
    fi
    if [[ ! -f "alembic.ini" ]]; then
        log "RUN_MIGRATIONS=1 but no alembic.ini found, skipping."
        return 0
    fi
    log "Running Alembic migrations..."
    alembic upgrade head || {
        log "Alembic upgrade failed."
        exit 1
    }
}

# -------- main --------
fetch_models
run_migrations

log "Boot complete. exec: $*"
exec "$@"
