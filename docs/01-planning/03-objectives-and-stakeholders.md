# AgriGuard AI — Objectives, Stakeholders & User Personas

## 1. Project Objectives

### 1.1 Primary Objectives
1. **O1 — Accurate Diagnosis**: Deliver plant species identification and disease/pest
   classification with high accuracy across the 17 supported plant species, validated on a
   held-out test split with per-class precision/recall/F1 reporting.
2. **O2 — Actionable Guidance**: For every diagnosis, provide organic/chemical/biological
   treatment guidance and prevention advice a non-expert can act on immediately.
3. **O3 — Explainability**: Make every AI diagnosis visually explainable (highlighted region of
   interest) so the user can sanity-check the model's reasoning rather than trust a black box.
4. **O4 — Early Detection of Date Palm Threats**: Specifically prioritize early detection of Red
   Palm Weevil and other date palm diseases, given their capacity for irreversible tree loss.
5. **O5 — Context-Aware Recommendations**: Incorporate live weather data into irrigation and
   spraying recommendations rather than issuing generic, context-free advice.
6. **O6 — Reproducible Automated Training**: Provide a single-command (`python train.py`)
   training pipeline that automatically adapts to whatever subset of supported datasets the user
   provides, with no hardcoded paths or manual preprocessing steps.
7. **O7 — Auditable History**: Persist every diagnosis so farmers and administrators can track
   disease trends over time per field/user.
8. **O8 — Production Readiness**: Ship a system that is secure, containerized, documented, and
   deployable without additional undocumented engineering work.

### 1.2 Secondary Objectives
9. **O9 — Extensibility**: New plant species or disease classes should be addable by adding
   correctly-labeled data to `datasets/` and re-running training — not by editing pipeline code.
10. **O10 — Administrative Control**: Give non-developer staff a UI to maintain the disease and
    treatment knowledge base.

## 2. Stakeholders

| Stakeholder | Role / Interest |
|---|---|
| **Farmers / Growers** | Primary end users; need fast, low-friction, trustworthy diagnosis and treatment guidance in the field. |
| **Agricultural Cooperative Managers** | Oversee multiple farmers/fields; need aggregate analytics and disease-trend visibility across a region. |
| **Agronomists / Plant Pathologists** | Domain experts who validate/curate the disease-treatment knowledge base via the admin panel; ultimate authority overriding AI suggestions. |
| **System Administrators** | Manage users, monitor system health, manage infrastructure and deployments. |
| **Academic Evaluators / Instructors** | Assess the project against the Rapid Systems Integration / CS421-style course rubric: completeness of SDLC artifacts, technical correctness, and engineering quality. |
| **Dataset Providers / Original Researchers** | Indirect stakeholders whose licensing terms constrain downstream use and redistribution of trained models. |
| **Developers / Maintainers** | Maintain and extend the codebase; require clean architecture, documentation, and test coverage to work efficiently. |

## 3. User Personas

### Persona 1 — "Farmer Youssef" (Primary User)
- **Age**: 42, smallholder date palm and vegetable farmer.
- **Tech comfort**: Owns a smartphone, uses WhatsApp and basic apps daily; not tech-savvy beyond that.
- **Goal**: Point his phone at a suspicious leaf or palm trunk and get an immediate, plain-language
  answer: what's wrong, how bad is it, and what should he do today.
- **Pain point addressed**: No agricultural extension officer is available nearby; by the time one
  arrives, the disease may have spread.
- **Key features used**: Scan Plant, Results Page, Treatment Recommendation, Weather-based
  spraying advice.

### Persona 2 — "Cooperative Manager Amal"
- **Age**: 35, manages a 40-farmer date palm cooperative.
- **Goal**: Understand disease trends across all member farms to prioritize where the
  cooperative's limited agronomist visits should go.
- **Key features used**: Dashboard, Palm Disease Statistics, Monthly Reports, History search
  across multiple users.

### Persona 3 — "Agronomist Dr. Karim"
- **Age**: 51, plant pathology PhD, consults for the cooperative.
- **Goal**: Periodically review and correct the treatment knowledge base so AI recommendations
  stay aligned with current best practice; spot-check flagged low-confidence diagnoses.
- **Key features used**: Admin Panel (Manage Diseases, Manage Treatments), Analytics Dashboard.

### Persona 4 — "System Administrator Sara"
- **Age**: 29, IT administrator for the cooperative's regional office.
- **Goal**: Keep the system online, manage user accounts, monitor error rates and model
  performance drift, apply updates safely.
- **Key features used**: Admin Panel (Manage Users, Manage Reports), deployment/monitoring
  tooling, logs.

### Persona 5 — "Evaluator / Instructor"
- **Age**: N/A, academic reviewer.
- **Goal**: Verify the project satisfies a complete, professional SDLC: requirements traceable to
  design, design traceable to code, code traceable to tests, and a working deployable artifact.
- **Key features used**: Full documentation set, README, test suite, architecture diagrams.
