# AgriGuard AI — Functional Requirements

Each requirement uses ID prefix `FR-<module>-<n>` and is written as testable acceptance criteria
so it can be traced directly into the Test Plan (Phase 7).

## FR-AUTH — Authentication & Account Management
- **FR-AUTH-1**: The system shall allow a new user to register with email, password, and full
  name. Passwords shall be hashed (bcrypt/argon2) and never stored in plaintext.
- **FR-AUTH-2**: The system shall allow a registered user to log in and receive a JWT access
  token and refresh token.
- **FR-AUTH-3**: The system shall support three roles: `farmer` (default), `agronomist`, `admin`.
- **FR-AUTH-4**: The system shall allow password reset via a time-limited, single-use reset token
  sent to the user's registered email.
- **FR-AUTH-5**: The system shall invalidate refresh tokens on logout and support token rotation.

## FR-SCAN — Plant Scanning
- **FR-SCAN-1**: The system shall allow a user to capture a photo via device camera or upload an
  existing image file (JPEG/PNG/WEBP, max configurable size, default 15MB).
- **FR-SCAN-2**: The system shall validate that an uploaded file is a genuine, decodable image
  before submitting it to the AI pipeline, rejecting corrupt or non-image files with a clear
  error.
- **FR-SCAN-3**: The system shall strip EXIF GPS metadata from uploaded images by default unless
  the user explicitly opts in to attaching location data to the scan.
- **FR-SCAN-4**: The system shall display a processing status while the AI pipeline executes and
  shall not block the UI thread.

## FR-AI — AI Diagnostic Pipeline
- **FR-AI-1**: The system shall identify the plant species from the submitted image as Step 1 of
  the pipeline, prior to disease classification.
- **FR-AI-2**: The system shall classify the disease (or "Healthy") for the identified plant
  species as Step 2.
- **FR-AI-3**: The system shall detect pests (e.g., Red Palm Weevil evidence) as Step 3,
  independently of the disease classification result.
- **FR-AI-4**: The system shall localize the affected region on the image (bounding box and/or
  segmentation mask) as Step 4.
- **FR-AI-5**: The system shall compute a numeric severity estimate (percentage affected area,
  mapped to a severity band: Mild / Moderate / Severe) as Step 5.
- **FR-AI-6**: The system shall compute and expose a confidence score (0–100%) for the primary
  disease classification as Step 6.
- **FR-AI-7**: The system shall generate an explainability visualization (heatmap overlay) as
  Step 7, showing which image regions most influenced the classification.
- **FR-AI-8**: The system shall retrieve treatment recommendations from the knowledge base as
  Step 8, keyed by the diagnosed disease.
- **FR-AI-9**: The system shall retrieve current weather conditions for the user's provided
  location as Step 9.
- **FR-AI-10**: The system shall generate an agricultural recommendation (irrigation/spraying/
  fertilizer guidance) combining diagnosis + weather as Step 10.
- **FR-AI-11**: The system shall generate a downloadable PDF report summarizing Steps 1–10 as
  Step 11.
- **FR-AI-12**: If plant identification confidence is below threshold, the system shall halt the
  pipeline after Step 1 and return an "unrecognized plant" result rather than guessing a disease
  for an unidentified species.

## FR-RESULT — Results Presentation
- **FR-RESULT-1**: The system shall display, at minimum: plant name, disease name, disease type,
  confidence score, severity level, affected area %, healthy area %, highlighted disease region,
  disease description, symptoms, causes, transmission method, organic treatment, chemical
  treatment, preventive advice, weather recommendation, and diagnosis date.
- **FR-RESULT-2**: The system shall display recovery probability and estimated recovery time
  **only** when such data exists in the knowledge base for the diagnosed condition; otherwise
  these fields shall be omitted from the results view entirely (not shown as blank/zero).

## FR-TREAT — Treatment & Prevention
- **FR-TREAT-1**: The system shall present organic, chemical, and (where available) biological
  treatment options separately.
- **FR-TREAT-2**: The system shall present application instructions and safety notes alongside
  any chemical treatment.
- **FR-TREAT-3**: Per BR6, the system shall substitute a "consult local agricultural authority"
  message for any treatment lacking a verified dosage source citation.
- **FR-TREAT-4**: The system shall present prevention guidance (irrigation, ventilation, humidity
  control, pruning, crop rotation, leaf removal, field sanitation) relevant to the diagnosed
  condition.

## FR-WEATHER — Weather Integration
- **FR-WEATHER-1**: The system shall retrieve temperature, humidity, wind speed, rain probability,
  and UV index from a configured weather API for the user's location.
- **FR-WEATHER-2**: The system shall generate at least one actionable recommendation derived from
  weather + diagnosis (e.g., suitable spraying day, delay irrigation, high humidity warning).
- **FR-WEATHER-3**: Per BR7, the system shall omit weather-based recommendations if weather data
  could not be freshly retrieved.

## FR-REPORT — PDF Reporting
- **FR-REPORT-1**: The system shall generate a PDF containing the plant image, plant name, disease
  name, description, highlighted infection area, severity, confidence, treatment, prevention,
  weather summary, diagnosis date, and a QR code linking back to the online report.
- **FR-REPORT-2**: The system shall allow the user to download the PDF on demand from the results
  page and from history.

## FR-HIST — History
- **FR-HIST-1**: The system shall persist every completed diagnosis to the user's history
  automatically (BR2).
- **FR-HIST-2**: The system shall allow the user to view, search (by plant/disease/date range),
  and download past reports.
- **FR-HIST-3**: The system shall allow the user to select two past scans and view a side-by-side
  comparison (severity/confidence/date).

## FR-DASH — Dashboard
- **FR-DASH-1**: The system shall display, per user, total scans, count of healthy vs. diseased
  results, and a breakdown of the most common diagnosed diseases.
- **FR-DASH-2**: The system shall display date-palm-specific statistics (e.g., Red Palm Weevil
  incidence) as a distinct panel given the elevated risk this pest represents.
- **FR-DASH-3**: The system shall display monthly aggregated report charts (scan volume, disease
  frequency trend).

## FR-ADMIN — Admin Panel
- **FR-ADMIN-1**: The system shall allow an `admin` to list, view, deactivate, and change the role
  of any user account.
- **FR-ADMIN-2**: The system shall allow an `admin` or `agronomist` to create, edit, and archive
  disease knowledge-base entries (description, symptoms, causes, transmission, severity mapping).
- **FR-ADMIN-3**: The system shall allow an `admin` or `agronomist` to create, edit, and archive
  treatment entries, including the mandatory `source_citation` field for any dosage information.
- **FR-ADMIN-4**: The system shall allow an `admin` to view and export system-wide reports and
  analytics across all users.

## FR-DATA — Data & Training Pipeline
- **FR-DATA-1**: The system shall automatically scan `datasets/` for recognizable image datasets
  without requiring the user to specify dataset names or paths.
- **FR-DATA-2**: The system shall automatically infer class labels from each discovered dataset
  using a chain of adapters (folder-name convention, filename convention, CSV/JSON/XML
  annotations) and normalize them to the canonical `"{plant}___{condition}"` schema.
- **FR-DATA-3**: The system shall merge all discovered datasets into a single unified labeled
  image index, removing exact and near-duplicate images (perceptual hashing).
- **FR-DATA-4**: The system shall split the unified dataset into train/validation/test partitions
  using a configurable ratio (default 70/15/15), stratified by class.
- **FR-DATA-5**: The system shall apply data augmentation only to the training partition.
- **FR-DATA-6**: The system shall address class imbalance via weighted sampling and/or class
  weighting in the loss function.
- **FR-DATA-7**: The system shall train, validate, and persist all required models with a single
  command, `python train.py`, requiring no manual intervention beyond placing datasets in
  `datasets/` and, optionally, editing a config file.
- **FR-DATA-8**: The system shall save, per training run: trained model weights, the label
  encoder, preprocessing/normalization parameters, evaluation metrics (accuracy, precision,
  recall, F1, per-class breakdown), a confusion matrix image, and loss/accuracy training curve
  images, all under a timestamped run directory.
