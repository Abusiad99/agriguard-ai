# AgriGuard AI — Project Scope

## 1. Project Title
**AgriGuard AI: AI-Powered Smart Agriculture & Date Palm Disease Detection System**

## 2. Purpose
AgriGuard AI is an end-to-end agricultural decision-support platform that uses deep learning
and computer vision to identify plant species, diagnose diseases and pests from photographs,
estimate disease severity, explain its reasoning, recommend treatment and prevention actions,
factor in live weather conditions, and produce a professional diagnostic report. The system is
designed to function as a substitute for the immediate, first-line judgment of an agricultural
extension officer — not as a replacement for a licensed agronomist, but as a triage and
decision-support tool that shortens the time between symptom onset and corrective action.

## 3. Scope Statement
The project scope covers the design, implementation, testing, and deployment of a complete
software system consisting of:

1. A **mobile-responsive web frontend** (React + TypeScript + Tailwind + Vite) that allows a
   user to capture or upload a plant image, view diagnostic results, browse history, view a
   dashboard, and download PDF reports.
2. A **backend API service** (FastAPI/Python) that exposes REST endpoints for authentication,
   image submission, diagnosis retrieval, history management, dashboard analytics, weather
   integration, and administrative operations.
3. An **AI inference pipeline** composed of chained models responsible for plant identification,
   disease classification, pest detection, disease localization (segmentation/bounding boxes),
   severity estimation, confidence scoring, and explainability (Grad-CAM/attention visualization).
4. A **data engineering pipeline** that automatically discovers, parses, merges, cleans,
   deduplicates, balances, augments, and splits heterogeneous datasets placed by the user into a
   `datasets/` folder, with zero hardcoded paths or dataset-specific assumptions beyond what is
   necessary to normalize class taxonomies.
5. A **training pipeline** (`train.py`) that trains, validates, evaluates, and persists all
   required models, along with all preprocessing artifacts (label encoders, normalization
   statistics, image transforms) and all training telemetry (metrics, confusion matrices, loss/
   accuracy curves, training history).
6. A **PostgreSQL relational database** for persistent storage of users, scans, diagnoses,
   treatments, reports, and administrative data, and **Redis** for caching and background job
   coordination.
7. A **PDF report generation subsystem** producing downloadable, shareable diagnostic reports
   with embedded QR codes.
8. An **admin panel** for managing users, disease knowledge base entries, treatments, and
   viewing system-wide analytics.
9. Complete **software engineering documentation** (requirements, diagrams, database design,
   API documentation, security design, test plan, deployment plan, and user/developer manuals).
10. **Containerized deployment** via Docker and NGINX, suitable for on-premise or cloud hosting.

## 4. In Scope
- Support for the 17 named plant species and their associated disease/pest classes, expandable
  automatically as new labeled classes are discovered in the user-supplied datasets.
- Automatic, structure-agnostic ingestion of the six named public dataset families (PlantVillage,
  PlantDoc, New Plant Diseases Dataset, IP102, Date Palm Disease Dataset, Red Palm Weevil
  Dataset), or any subset of them the user actually places in `datasets/`.
- A model-comparison and selection methodology across YOLOv11, EfficientNet, ConvNeXt, ViT,
  SAM2, and MobileNetV4, with a justified final architecture recommendation per sub-task.
- Explainable AI output (visual heatmap over the diagnosed region).
- Weather-API-informed spraying/irrigation guidance.
- Treatment guidance limited to organic/chemical/biological categories and general application
  guidance; the system explicitly defers to local agricultural authorities for exact chemical
  dosages when a verified trusted source is not available in the knowledge base.
- Full user-facing history, dashboard, and admin analytics.
- Dockerized deployment with an NGINX reverse proxy.

## 5. Out of Scope
- Physical IoT sensor hardware (soil moisture probes, drone integration, autonomous sprayers) —
  the system is designed with extensible interfaces for these but does not include hardware
  procurement, firmware, or physical installation.
- Legal responsibility for pesticide application outcomes. The system is a decision-support tool;
  the end user and/or a licensed agronomist retains responsibility for final treatment decisions.
- Real-time video stream diagnosis (the system operates on discrete captured/uploaded images in
  v1; a real-time inference mode is listed as a future enhancement).
- Multi-tenant SaaS billing infrastructure (the system is scoped as a single-organization
  deployable product; commercial multi-tenancy is a future enhancement).
- Native mobile applications (iOS/Android app store binaries). The frontend is a responsive web
  application usable on mobile browsers; native wrappers are a future enhancement.

## 6. Deliverables
| # | Deliverable | Format |
|---|---|---|
| 1 | Software Requirements Specification (functional + non-functional) | Markdown/PDF |
| 2 | Full UML & structured analysis diagram set | Markdown + Mermaid source |
| 3 | Database design & schema (DDL) | SQL + ERD |
| 4 | REST API specification | OpenAPI/Markdown |
| 5 | AI data pipeline & training pipeline (`train.py`) | Python source |
| 6 | Trained model artifacts, metrics, confusion matrices, training curves | `.pt`/`.json`/`.png` |
| 7 | Backend service | Python/FastAPI source |
| 8 | Frontend application | React/TypeScript source |
| 9 | Admin panel | React/TypeScript source (part of frontend) |
| 10 | PDF report generator | Python source |
| 11 | Docker/NGINX deployment configuration | Dockerfiles + compose + nginx.conf |
| 12 | Security design document | Markdown/PDF |
| 13 | Test plan & automated test suite | Markdown + pytest |
| 14 | Deployment & maintenance plan | Markdown/PDF |
| 15 | User manual & developer manual | Markdown/PDF |
| 16 | README | Markdown |

## 7. Success Criteria
- `python train.py` completes end-to-end on any valid subset of the named datasets placed in
  `datasets/`, with no code edits required, and produces deployable model artifacts.
- The backend serves a diagnosis end-to-end (image in → structured diagnosis + PDF report out)
  within an acceptable latency budget (see NFRs).
- The frontend supports the full workflow: capture/upload → processing → results → history →
  dashboard → report download.
- All documentation deliverables above are produced without placeholders.
- The system builds and runs via `docker compose up` with no manual post-build steps beyond
  environment variable configuration.

## 8. Project Constraints
See `04-constraints-and-assumptions.md` for the full constraints and assumptions register.

## 9. Timeline Structure (SDLC Phases)
This project follows a strict **Waterfall** model. Each phase is completed and reviewed before
the next begins:

1. Requirements & Planning (this document set)
2. System & Database Design (diagrams, schema, API spec)
3. AI Data & Training Pipeline Implementation
4. Backend Implementation
5. Frontend Implementation
6. Integration
7. Testing & QA
8. Security Hardening
9. Deployment
10. Documentation Finalization & Maintenance Planning
