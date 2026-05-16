#!/usr/bin/env bash
# scripts/prepare-ml-shim.sh
# -----------------------------------------------------------
# Copies ML inference modules that the backend image needs to
# import at runtime into services/backend/ so that
# `docker build services/backend` includes them.
#
# Run this BEFORE building the backend Docker image (CI step,
# or manually in dev when services/ml/pipeline.py changes).
#
# This is a build-time shim, not a code dependency: in dev,
# docker-compose mounts ./services/backend:/app so the local
# tree is used directly.
# -----------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/services/ml"
DST="$ROOT/services/backend"

for f in pipeline.py cost_engine.py severity_classifier.py output_formatter.py parts.yaml; do
    if [[ ! -f "$SRC/$f" ]]; then
        echo "ERROR: $SRC/$f missing" >&2
        exit 1
    fi
    cp -f "$SRC/$f" "$DST/$f"
    echo "  copied: $f"
done

echo "ML shim ready in $DST"
