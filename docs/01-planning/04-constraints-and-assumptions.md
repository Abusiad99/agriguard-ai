# AgriGuard AI — Constraints, Assumptions & Business Rules

## 1. Constraints

### 1.1 Technical Constraints
- **C1**: Training must run via a single entry point, `python train.py`, with no hardcoded
  dataset paths or dataset-name assumptions in code.
- **C2**: The system must not fabricate datasets — the pipeline must fail with a clear diagnostic
  message if `datasets/` is empty or contains no recognizable image data, never silently proceed
  with synthetic stand-ins.
- **C3**: The system must operate on both GPU and CPU-only environments (with reduced throughput
  on CPU), since deployment hardware is not guaranteed.
- **C4**: The frontend must be responsive down to common smartphone viewport widths (~360px),
  since the primary capture device is a phone.
- **C5**: All chemical treatment dosage information must be traceable to a cited source in the
  knowledge base; where no verified source exists, the system must direct the user to local
  agricultural authorities instead of inventing a dosage.

### 1.2 Organizational / Course Constraints
- **C6**: The project follows a strict Waterfall SDLC — each phase's artifacts are finalized
  (documented here) before downstream phases are built, mirroring the rubric expectations of a
  Rapid Systems Integration course.
- **C7**: Deliverables must be free of placeholders, TODOs, or stubbed-out incomplete logic in
  any single delivered phase; each phase is complete in itself even though the overall project is
  delivered across multiple responses/sessions.

### 1.3 Resource Constraints
- **C8**: Dataset acquisition and storage is the user's responsibility; the system only consumes
  data placed under `datasets/` and never downloads datasets itself (no network calls in the data
  pipeline).
- **C9**: Model training compute is bounded by whatever hardware the user runs `train.py` on; the
  pipeline must expose configuration (batch size, image size, epochs) so it can be tuned to
  available resources rather than assuming a fixed high-end GPU.

## 2. Assumptions
- **A1**: The user will place one or more of the six named dataset families (or compatible
  ImageFolder-style labeled image data) under `datasets/<dataset-name>/...` before running
  `train.py`.
- **A2**: Each dataset, regardless of internal structure, associates each image with a discoverable
  class label (via folder name, filename convention, or an accompanying CSV/JSON/XML annotation
  file).
- **A3**: Internet connectivity is available at inference time for weather-API calls; if
  unavailable, weather-dependent recommendations are gracefully omitted rather than blocking the
  core diagnosis.
- **A4**: End users have access to a camera-capable smartphone or a device with an image upload
  capability and a modern web browser (Chrome/Safari/Firefox, last 2 major versions).
- **A5**: The organization deploying AgriGuard AI will independently confirm dataset/model license
  compatibility with its intended distribution model before commercial use.
- **A6**: A PostgreSQL instance and Redis instance are provisioned (via Docker Compose in
  development, or managed services in production) and reachable by the backend.

## 3. Business Rules
- **BR1**: A diagnosis is only presented to the user once a confidence score is computed; if
  confidence falls below the configured minimum threshold, the result is labeled "Low Confidence —
  Recommend Manual Expert Review" rather than presented as a definitive diagnosis.
- **BR2**: Every completed diagnosis is automatically saved to the requesting user's history; there
  is no "discard" option that skips persistence, since historical trend data is a core product
  objective (O7).
- **BR3**: Only users with the `admin` role may access the Admin Panel routes (Manage Users,
  Manage Diseases, Manage Treatments, Manage Reports).
- **BR4**: Only users with the `agronomist` or `admin` role may edit the disease/treatment
  knowledge base; standard farmer accounts have read-only access to knowledge-base content
  surfaced through diagnosis results.
- **BR5**: A PDF report can be generated only for a diagnosis that has completed the full pipeline
  (through Step 11); partial/failed pipeline runs cannot produce a report.
- **BR6**: Chemical treatment dosage text is only shown if it carries a `source_citation` field in
  the knowledge base; otherwise the UI shows the "consult local agricultural authority" fallback
  copy defined in the content guidelines.
- **BR7**: Weather-based recommendations (e.g., "delay spraying — rain expected") are only shown
  if a successful weather API response was obtained within the last configured freshness window
  (default 3 hours); stale or failed weather data is omitted, not guessed.
