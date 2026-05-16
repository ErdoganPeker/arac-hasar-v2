# HF Spaces entrypoint — repo-root Dockerfile that delegates to the
# actual backend image built from services/backend/.
#
# HF Spaces requires Dockerfile + README.md at repo root, with the
# README front-matter declaring `sdk: docker` and `app_port: 7860`.
# This file mirrors services/backend/Dockerfile but adjusts COPY paths
# to repo-root build context, and binds uvicorn to $PORT (HF sets it
# to 7860 by default; container also respects PORT env override).

# syntax=docker/dockerfile:1.6

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

COPY services/backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip wheel && \
    pip wheel --wheel-dir=/build/wheels \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        torch==2.3.1+cpu torchvision==0.18.1+cpu && \
    pip wheel --wheel-dir=/build/wheels -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONOPTIMIZE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860 \
    MODEL_DIR=/app/models \
    ML_DEVICE=cpu \
    UVICORN_WORKERS=1 \
    ML_WARMUP_ON_STARTUP=0 \
    ML_UNLOAD_AFTER_INFERENCE=0 \
    YOLO_CONFIG_DIR=/tmp/Ultralytics \
    HF_HOME=/tmp/.huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
        libpq5 curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --gid 1000 app && \
    useradd  --uid 1000 --gid app --create-home --shell /bin/bash app

WORKDIR /app

COPY --from=builder /build/wheels /tmp/wheels
COPY --chown=app:app services/backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-index --find-links=/tmp/wheels \
        torch==2.3.1+cpu torchvision==0.18.1+cpu && \
    pip install --no-index --find-links=/tmp/wheels -r requirements.txt && \
    rm -rf /tmp/wheels

# Backend source (all .py files at services/backend/)
COPY --chown=app:app services/backend/*.py            ./
COPY --chown=app:app services/backend/cost_table.yaml ./
COPY --chown=app:app services/backend/alembic.ini     ./
COPY --chown=app:app services/backend/migrations      ./migrations
COPY --chown=app:app services/backend/scripts         ./scripts

# ML pipeline modules (also needed by ml_service.py)
COPY --chown=app:app services/backend/pipeline.py            ./
COPY --chown=app:app services/backend/cost_engine.py         ./
COPY --chown=app:app services/backend/severity_classifier.py ./
COPY --chown=app:app services/backend/output_formatter.py    ./
COPY --chown=app:app services/backend/parts.yaml             ./
COPY --chown=app:app services/backend/model_manager.py       ./
COPY --chown=app:app services/backend/pretrained_registry.py ./

COPY --chown=app:app services/backend/scripts/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh && \
    mkdir -p ${MODEL_DIR} /app/pretrained /tmp/Ultralytics /tmp/.huggingface && \
    chown -R app:app ${MODEL_DIR} /app/pretrained /tmp/Ultralytics /tmp/.huggingface

USER app

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl --fail http://localhost:${PORT}/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers ${UVICORN_WORKERS:-1}"]
