# AgriGuard AI — Training Pipeline Dockerfile
#
# A separate image from the backend API (docker/backend.Dockerfile) because the
# training pipeline has a heavier dependency footprint (torch/torchvision/timm
# with CUDA support) and runs as an on-demand batch job, not a long-running service
# in the request path (see docs/02-system-design/11-deployment-diagram.mermaid's
# note on the Training Service). Not included in the default `docker compose up`
# stack; run explicitly via the `training` profile — see docker-compose.yml.
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r agriguard && useradd -r -g agriguard -m -d /home/agriguard agriguard

WORKDIR /app

COPY ai/requirements.txt /app/ai-requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r ai-requirements.txt

COPY ai/ /app/ai/
COPY train.py evaluate.py predict.py inference.py /app/

# datasets/ and artifacts/ are bind-mounted at runtime (see docker-compose.yml
# `training` service) — never baked into the image (C8).
RUN mkdir -p /app/datasets /app/artifacts /app/logs /app/.cache && \
    chown -R agriguard:agriguard /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AGRIGUARD_DATASETS_DIR=/app/datasets \
    AGRIGUARD_ARTIFACTS_DIR=/app/artifacts

USER agriguard

ENTRYPOINT ["python"]
CMD ["train.py"]
