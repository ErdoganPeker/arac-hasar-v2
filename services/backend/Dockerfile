# syntax=docker/dockerfile:1.6
#
# services/backend/Dockerfile
# ------------------------------------------------------------------
# Default backend image for Render and Docker Compose dev.
# This is a CPU-only, slim image — model weights are pulled from S3
# at boot (see scripts/entrypoint.sh). Mirrors Dockerfile.fetch.
#
# For an image with weights baked in, see Dockerfile.embedded.
# For local GPU dev with CUDA, see Dockerfile.cuda (TODO if needed).
# ------------------------------------------------------------------

# ---------- Stage 1: builder ----------
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc libpq-dev curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip wheel && \
    pip wheel --wheel-dir=/build/wheels \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        torch==2.3.1+cpu torchvision==0.18.1+cpu && \
    pip wheel --wheel-dir=/build/wheels -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    MODEL_DIR=/app/models \
    ML_DEVICE=cpu

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
        libpq5 curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --gid 1000 app && \
    useradd  --uid 1000 --gid app --create-home --shell /bin/bash app

WORKDIR /app

COPY --from=builder /build/wheels /tmp/wheels
COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-index --find-links=/tmp/wheels \
        torch==2.3.1+cpu torchvision==0.18.1+cpu && \
    pip install --no-index --find-links=/tmp/wheels -r requirements.txt && \
    rm -rf /tmp/wheels

COPY --chown=app:app *.py            ./
COPY --chown=app:app cost_table.yaml ./
COPY --chown=app:app alembic.ini     ./
COPY --chown=app:app migrations      ./migrations
COPY --chown=app:app scripts         ./scripts

# ML pipeline module — backend imports `from pipeline import DamagePipeline`.
# Build context is `services/backend/`; we shim pipeline.py + supporting
# YAMLs into the image via a build-time prepare step (compose mounts the
# real services/ml/ tree in dev). For production image bake, the CI step
# copies services/ml/pipeline.py + parts.yaml into services/backend/ before
# `docker build` (see scripts/prepare-ml-shim.sh).
COPY --chown=app:app pipeline.py            ./
COPY --chown=app:app cost_engine.py         ./
COPY --chown=app:app severity_classifier.py ./
COPY --chown=app:app output_formatter.py    ./
COPY --chown=app:app parts.yaml             ./

COPY --chown=app:app scripts/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh && \
    mkdir -p ${MODEL_DIR} && chown -R app:app ${MODEL_DIR}

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl --fail http://localhost:${PORT}/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 2"]
