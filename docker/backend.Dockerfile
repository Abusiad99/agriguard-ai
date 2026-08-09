# AgriGuard AI — Backend API Dockerfile
# Multi-stage build: a builder stage compiles/installs Python dependencies into a
# virtualenv, and the runtime stage copies only that venv + application source,
# keeping the final image free of build toolchains (smaller attack surface, NFR-SEC).

# ---------------------------------------------------------------------------
# Stage 1: builder
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt /build/backend-requirements.txt
COPY ai/requirements.txt /build/ai-requirements.txt

# Install backend deps + the AI pipeline's deps (the backend imports `ai.inference`
# in-process — see backend/app/infrastructure/external/ai_pipeline_client.py — so
# both dependency sets must be present in the same image/venv).
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r backend-requirements.txt && \
    pip install --no-cache-dir -r ai-requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r agriguard && useradd -r -g agriguard -m -d /home/agriguard agriguard

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# Copy the AI package (imported in-process by the backend) and the backend app.
# Datasets are intentionally NOT copied into the image (C8: dataset acquisition is
# the operator's responsibility, never baked into the image); trained model
# artifacts are mounted as a volume at runtime (see docker-compose.yml).
COPY ai/ /app/ai/
COPY backend/app /app/app
COPY backend/alembic.ini /app/alembic.ini
COPY database/01-schema.sql /app/database/01-schema.sql

RUN mkdir -p /app/storage /app/logs /app/artifacts && \
    chown -R agriguard:agriguard /app

COPY docker/scripts/backend-entrypoint.sh /usr/local/bin/backend-entrypoint.sh
RUN chmod +x /usr/local/bin/backend-entrypoint.sh

USER agriguard

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["backend-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
