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

    # Hugging Face Hub fetch path (public model repo, no auth needed).
    # Set HF_MODEL_REPO env to use this branch; otherwise falls back to S3.
    if [[ -n "${HF_MODEL_REPO:-}" ]]; then
        local hf_branch="${HF_MODEL_BRANCH:-main}"
        log "Fetching weights from https://huggingface.co/${HF_MODEL_REPO}/resolve/${hf_branch}/ -> ${MODEL_DIR}/"
        mkdir -p "${MODEL_DIR}"
        for w in "${REQUIRED_WEIGHTS[@]}"; do
            local dst="${MODEL_DIR}/${w}"
            if [[ -f "${dst}" ]]; then
                log "  ${w} already cached, skipping."
                continue
            fi
            local url="https://huggingface.co/${HF_MODEL_REPO}/resolve/${hf_branch}/${w}?download=true"
            log "  downloading ${url}"
            if ! curl --fail --silent --show-error --location \
                      --retry 5 --retry-delay 3 --max-time 600 \
                      --output "${dst}.tmp" "${url}"; then
                log "ERROR: curl failed for ${url}"
                rm -f "${dst}.tmp"
                exit 1
            fi
            mv "${dst}.tmp" "${dst}"
        done
        log "All weights fetched from Hugging Face."
        # ---- Pretrained Ultralytics COCO weights (Ultralytics CDN, public) ----
        # PRETRAINED_DIR'a yolo11m-seg.pt indir. is_available() file-exists
        # checki bunu bulamayinca pretrained_ultralytics_yolo11m 400 doner.
        local pre_dir="${PRETRAINED_DIR:-/app/pretrained}"
        local ultra_base="${ULTRALYTICS_BASE:-https://github.com/ultralytics/assets/releases/download/v8.3.0}"
        local ultra_weights=("yolo11m-seg.pt")
        mkdir -p "${pre_dir}" || true
        for w in "${ultra_weights[@]}"; do
            local dst="${pre_dir}/${w}"
            if [[ -f "${dst}" ]]; then
                log "  pretrained ${w} cached, skip."
                continue
            fi
            log "  downloading pretrained ${ultra_base}/${w}"
            if curl --fail --silent --show-error --location \
                    --retry 3 --retry-delay 3 --max-time 300 \
                    --output "${dst}.tmp" "${ultra_base}/${w}"; then
                mv "${dst}.tmp" "${dst}"
                log "  pretrained ${w} OK"
            else
                log "WARN: pretrained ${w} fetch fail; UI will show 'unavailable' but core custom model unaffected"
                rm -f "${dst}.tmp" || true
            fi
        done
        return 0
    fi

    if [[ -z "${MODEL_S3_BUCKET:-}" ]]; then
        log "ERROR: HF_MODEL_REPO and MODEL_S3_BUCKET both unset and weights missing."
        log "       Set HF_MODEL_REPO=owner/repo (preferred) or MODEL_S3_BUCKET."
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

# IMPORTANT: boto3 s3.download_file() and s3.upload_file() call HeadObject
# under the hood. B2 + bucket-scoped Application Keys ("List All Bucket
# Names" disabled) return 403 on HeadObject even when GetObject succeeds.
# Use get_object directly + stream to disk; it skips the HeadObject.
config = Config(
    retries={"max_attempts": 5, "mode": "standard"},
    signature_version="s3v4",
    s3={"addressing_style": "virtual"},
)
s3 = boto3.client("s3", config=config, **kwargs)
os.makedirs(target, exist_ok=True)
for w in weights:
    dst = os.path.join(target, w)
    if os.path.isfile(dst):
        print(f"[entrypoint]   {w} already cached, skipping.", file=sys.stderr)
        continue
    key = f"{prefix}/{w}"
    print(f"[entrypoint]   downloading s3://{bucket}/{key} -> {dst}", file=sys.stderr)
    resp = s3.get_object(Bucket=bucket, Key=key)
    tmp = dst + ".tmp"
    body = resp["Body"]
    with open(tmp, "wb") as f:
        for chunk in iter(lambda: body.read(8 * 1024 * 1024), b""):
            f.write(chunk)
    os.replace(tmp, dst)
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
