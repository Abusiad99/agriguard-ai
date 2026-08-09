# AgriGuard AI — Feasibility Study

## 1. Purpose
This study evaluates whether AgriGuard AI is viable from technical, operational, economic,
schedule, and legal perspectives before committing to full-scale design and implementation.

## 2. Technical Feasibility

### 2.1 Availability of Building Blocks
- **Model architectures**: YOLOv11, EfficientNet, ConvNeXt, ViT, SAM2, and MobileNetV4 all have
  mature, open-source, well-documented implementations (Ultralytics, `timm`, `torchvision`,
  Meta's SAM2 repository). No novel architecture research is required; the engineering task is
  architecture *selection, adaptation, and integration*, which is tractable.
- **Datasets**: PlantVillage, PlantDoc, the Kaggle "New Plant Diseases Dataset", IP102, and
  published Date Palm / Red Palm Weevil datasets are all publicly documented dataset families
  with known (if inconsistent) folder/label conventions. Because conventions differ across
  sources, the pipeline is designed as a **structure-agnostic ingestion layer** (auto-detection
  of image/label pairing patterns) rather than a fixed parser — this is the single highest
  technical-risk component of the project and is treated accordingly (see Risk Register).
- **Weather data**: Multiple production-grade weather APIs (e.g., OpenWeatherMap, WeatherAPI,
  Open-Meteo) provide the required temperature/humidity/wind/rain/UV fields via simple REST
  calls, so this integration is low-risk.
- **PDF generation, QR codes, background jobs, caching**: All solved problems with mature Python
  libraries (`reportlab`/`weasyprint`, `qrcode`, Celery-style workers or FastAPI `BackgroundTasks`,
  Redis).

### 2.2 Technical Risk Register
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Heterogeneous dataset folder structures break auto-ingestion | High | High | Pluggable "dataset adapter" pattern with a generic fallback scanner (ImageFolder-style) plus format-specific adapters; adapters are auto-selected by structural fingerprinting, not hardcoded paths |
| Class taxonomy collisions across datasets (e.g., "healthy" meaning different things per crop) | High | Medium | Canonical label schema `"{plant}___{condition}"`, with a normalization/synonym table |
| Class imbalance after merge | High | Medium | Class-balancing via weighted sampling + augmentation-only-on-minority strategy, documented in preprocessing spec |
| Insufficient/no dataset present at first run | Medium | Low | `train.py` performs a pre-flight dataset audit and fails fast with a clear, actionable message rather than a stack trace |
| GPU unavailability in some deployment environments | Medium | Medium | All training/inference code is device-agnostic (`torch.device` auto-detection with CPU fallback); documented expected throughput difference |
| Explainability (Grad-CAM) not well-defined for transformer backbones | Medium | Low | Attention-rollout method used for ViT; Grad-CAM for CNN backbones; abstracted behind a common `Explainer` interface |
| Unverified pesticide dosage data leading to unsafe recommendations | Medium | High | Knowledge base ships only with dosage data traceable to a cited trusted agricultural source; otherwise the system defers to local agricultural authorities, per project requirement |

### 2.3 Conclusion
**Technically feasible.** All required components exist as mature open-source tools; the primary
engineering challenge (heterogeneous dataset ingestion) is addressed architecturally through an
adapter pattern rather than assumed away.

## 3. Operational Feasibility
- The target users (farmers, agricultural technicians, cooperative managers, and administrators)
  require only a camera-capable device and a browser — no specialized hardware or training beyond
  a short onboarding flow.
- The admin panel gives non-engineering staff (agronomists, cooperative admins) the ability to
  maintain the treatment/disease knowledge base without code changes.
- **Conclusion: Operationally feasible**, assuming basic internet connectivity at the point of use
  (offline-first capture with delayed sync is listed as a future enhancement).

## 4. Economic Feasibility
- All core software components (frameworks, model architectures, libraries) are open-source and
  free to use commercially under permissive or copyleft-compatible licenses (verify SAM2/YOLOv11
  license terms before commercial redistribution — see Legal Feasibility).
- Primary recurring costs at production scale: cloud compute for training (one-time/periodic),
  inference hosting (GPU or optimized CPU inference), managed PostgreSQL/Redis, and weather API
  quota (most providers offer a sufficient free tier for pilot deployments).
- **Conclusion: Economically feasible** for a pilot/academic/competition deployment at near-zero
  marginal cost; production scaling costs are dominated by inference hosting, which is
  well-understood and budgetable.

## 5. Schedule Feasibility
Given the Waterfall structure and the breadth of the requirement set, the project is planned as a
multi-phase delivery (see Project Scope §9) rather than a single delivery. Each phase produces a
reviewable, versioned artifact set. This phased structure is itself the schedule-risk mitigation:
no phase blocks indefinitely on another, and partial system value (e.g., documentation and data
pipeline) is available before full-system integration completes.

## 6. Legal & Ethical Feasibility
- Public datasets (PlantVillage, PlantDoc, IP102, etc.) are widely used in academic research;
  their individual licenses must be reviewed by the deploying party before any commercial
  redistribution of derived model weights, since licenses vary by source and are not unified by
  this project.
- The system explicitly avoids generating unverified chemical dosage instructions, reducing
  liability exposure and aligning with agronomic safety best practice.
- User-submitted images may contain incidental location metadata (EXIF GPS); the system strips or
  explicitly requests consent for such metadata per the Security Design document.
- **Conclusion: Feasible**, subject to the deploying organization independently confirming dataset
  license compatibility with its specific distribution model.

## 7. Overall Recommendation
**Proceed.** The project is technically, operationally, economically, and legally feasible under
the constraints and mitigations documented above. The highest-risk item — heterogeneous dataset
ingestion — is addressed structurally in the system design (see the Data Pipeline design in
Phase 3) rather than deferred.
