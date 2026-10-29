# AgriGuard AI

A plant-health assistant for farmers. It analyses a photo of a leaf or plant part, suggests likely diseases with **calibrated confidence**, says plainly when it is not sure, tracks each plant over time, and answers questions from a curated knowledge base with citations. It is available in Arabic (RTL) and English.

> AgriGuard's results are **model suggestions that support, not replace, expert advice**. Every result shows its decision status, its confidence, where its thresholds came from, and its limitations.

## What works today

| Capability | Status | Details |
|---|---|---|
| Image-quality gate (blur, exposure, resolution, blank or non-plant hints, format, size, decompression bombs) | **Implemented and tested** | `ai/quality/`, [AI reliability](docs/AI_RELIABILITY.md) |
| Disease classifier: PlantWild v2, 115 classes on 34 plant types, EfficientNet-B0 | **Implemented, trained and evaluated** on held-out web photos (top-1 60.7 %, top-3 82.2 %; confident answers 88 % correct on 32 % of photos); not field-validated | [AI reliability](docs/AI_RELIABILITY.md) |
| Calibrated confidence, statuses (confident / uncertain / inconclusive), validation-selected thresholds | **Implemented and tested** | `ai/inference/calibration.py`, `ai/inference/decision.py` |
| Grad-CAM "model attention" next to the original photo | **Implemented and tested** (labelled as attention, not a lesion map) | `ai/explainability/` |
| Reproducible evaluation (metrics, calibration, risk–coverage, leakage check, latency) | **Implemented and run** | `evaluate.py` |
| Leaf/lesion segmentation and affected-area % | **Pipeline implemented; blocked by missing pixel annotations** (shown as "not measured") | [Segmentation](docs/SEGMENTATION.md) |
| Plant profiles, observation timeline, notes, careful comparison | **Implemented and tested** | [Plant tracking](docs/PLANT_TRACKING_AND_DIFFERENTIAL.md) |
| Differential diagnosis (candidates, look-alikes the model cannot detect, follow-up questions) | **Implemented and tested**; the taxonomy is unreviewed | same |
| Agricultural assistant (RAG with Gemini, citations, AR/EN) | **Implemented and tested with fakes**; live Gemini and a real corpus not yet validated | [Assistant](docs/ASSISTANT_RAG.md) |
| Early disease-risk prediction | **Deferred by design** | [Future](docs/FUTURE_EARLY_WARNING.md) |

The model cannot recognise healthy plants, pests, nutrient deficiencies, water or heat stress, or diseases outside its 115 training classes. The UI states this on every result.

## Repository layout

```
ai/         training, calibration, evaluation, inference, quality gate, segmentation, knowledge
backend/    FastAPI app (clean architecture: domain / application / infrastructure / interface)
frontend/   React + TypeScript + Tailwind (AR/EN, RTL)
docker/     compose stack, nginx, Dockerfiles
docs/       planning, system design, and the guides linked above
train.py · calibrate.py · evaluate.py · predict.py · inference.py
```

## Setup

### 1. Python environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -r ai/requirements.txt
```

### 2. Dataset

PlantWild v2 is stored with Git LFS:

```bash
git lfs pull
```

### 3. Train, calibrate and evaluate

```bash
# ImageNet weights: timm downloads them from Hugging Face; on hosts without access, use the GitHub release:
#   curl -L -o artifacts/pretrained/efficientnet_b0_ra-3dd342df.pth \
#     https://github.com/huggingface/pytorch-image-models/releases/download/v0.1-weights/efficientnet_b0_ra-3dd342df.pth
export AGRIGUARD_PRETRAINED_WEIGHTS=artifacts/pretrained/efficientnet_b0_ra-3dd342df.pth
python train.py            # dedup → split manifest → train → test metrics → calibrate on VALIDATION
python evaluate.py         # full held-out report → artifacts/runs/<run>/evaluation_test/report.md
python -m ai.quality.calibrate_quality   # optional: quality-gate behaviour on your own images
```

### 4. Backend

```bash
cd backend
cp ../.env.example .env    # set DATABASE_URL, JWT_SECRET_KEY, optional GEMINI_API_KEY
alembic upgrade head       # migrations 0001–0003 (0003 is additive; existing rows are preserved)
PYTHONPATH=.. uvicorn app.main:app --reload
```

### 5. Frontend

```bash
cd frontend && npm install && npm run dev
```

### 6. Assistant corpus (optional)

See [docs/ASSISTANT_RAG.md](docs/ASSISTANT_RAG.md):

```bash
cd backend && python scripts/ingest_knowledge.py --manifest ../knowledge/manifest.json
```

### Docker

```bash
cd docker && docker compose up --build
```

Migrations run automatically. Mount trained artifacts into the `artifacts_data` volume.

## Tests and quality gates

```bash
cd backend && pytest                      # API, services, repositories, RAG, authorisation
cd .. && pytest ai/tests                  # calibration, quality gate, segmentation, inference
cd frontend && npm run typecheck && npm run lint && npm run build
```

## Security notes

- **Uploaded photos and generated images** are served only through **signed, expiring URLs**. There is no public `/storage` path. PDF reports require authentication.
- **Every plant, observation, note and assistant-context request** is ownership-checked on the server.
- **Uploads** are validated by their decoded content (format allow-list, pixel limit).
- **Per-client rate limits** use the real client IP behind nginx. The backend port is bound to loopback, and nginx overwrites `X-Forwarded-For`.
- **Assistant input** (retrieved text, notes, chat history) is treated as untrusted. See the threat table in [docs/ASSISTANT_RAG.md](docs/ASSISTANT_RAG.md).
