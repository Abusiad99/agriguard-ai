# AgriGuard AI — Phase 2: System Design Overview & Traceability

## 1. Purpose
This document indexes every design artifact produced in Phase 2 and maps each one back to the
Functional (FR-*) and Non-Functional (NFR-*) requirements from Phase 1, and forward to the Use
Cases (UC-*). No design element in this phase exists without a requirement driving it.

## 2. Artifact Index
| # | Artifact | File |
|---|---|---|
| 1 | Context Diagram | `01-context-diagram.mermaid` |
| 2 | DFD Level 0 | `02-dfd-level-0.mermaid` |
| 3 | DFD Level 1 | `03-dfd-level-1.mermaid` |
| 4 | DFD Level 2 (AI Pipeline) | `04-dfd-level-2.mermaid` |
| 5 | Use Case Diagram | `05-use-case-diagram.mermaid` |
| 6a | Activity Diagram — Scan Plant | `06a-activity-scan-plant.mermaid` |
| 6b | Activity Diagram — Train AI Models | `06b-activity-train-models.mermaid` |
| 6c | Activity Diagram — Manage Knowledge Base | `06c-activity-manage-knowledge-base.mermaid` |
| 7a | Sequence Diagram — Scan Plant (full pipeline) | `07a-sequence-scan-plant.mermaid` |
| 7b | Sequence Diagram — Authentication | `07b-sequence-auth-login.mermaid` |
| 7c | Sequence Diagram — PDF Report Download | `07c-sequence-report-download.mermaid` |
| 8 | Class Diagram | `08-class-diagram.mermaid` |
| 9 | State Diagram — Diagnosis Lifecycle | `09-state-diagram.mermaid` |
| 10 | Component Diagram | `10-component-diagram.mermaid` |
| 11 | Deployment Diagram | `11-deployment-diagram.mermaid` |
| 12 | Entity Relationship Diagram | `12-erd.mermaid` |
| 13 | REST API Specification | `13-api-specification.md` |

Database DDL lives under `/database/01-schema.sql` (see `/database/README.md`).

## 3. Traceability Matrix (Requirement → Design Artifact)

| Requirement | Design Artifact(s) |
|---|---|
| FR-AUTH-1..5 | Sequence: Authentication; Class: `User`, `AuthService`; ERD: `users`, `refresh_tokens`; API §Auth |
| FR-SCAN-1..4 | Context Diagram; DFD L1 (Process 1); Activity: Scan Plant; Sequence: Scan Plant; API §Scans |
| FR-AI-1..12 | DFD L2 (AI Pipeline); Sequence: Scan Plant; Class: `AIPipeline`, `PlantIdentifier`, `DiseaseClassifier`, `PestDetector`, `Localizer`, `SeverityEstimator`, `Explainer`; State Diagram (Diagnosis) |
| FR-RESULT-1..2 | Class: `DiagnosisResult`; ERD: `diagnoses`; API §Diagnoses |
| FR-TREAT-1..4 | DFD L1 (Process 1, Treatment Lookup); Class: `Treatment`, `KnowledgeBaseService`; ERD: `treatments`, `diseases`; API §Knowledge Base |
| FR-WEATHER-1..3 | DFD L1 (Process 2); Class: `WeatherService`; Component Diagram (external Weather API); API §Weather |
| FR-REPORT-1..2 | Sequence: PDF Report Download; Class: `ReportGenerator`; ERD: `reports`; API §Reports |
| FR-HIST-1..3 | ERD: `diagnoses` (immutable, indexed by user+date); API §History |
| FR-DASH-1..3 | DFD L1 (Process 4); ERD: aggregation views; API §Dashboard |
| FR-ADMIN-1..4 | Use Case Diagram (Admin/Agronomist actors); Activity: Manage Knowledge Base; API §Admin |
| FR-DATA-1..8 | DFD L2 (Data/Training Pipeline extension, see Phase 3 companion); Activity: Train AI Models; Component Diagram (Training Service) |
| NFR-PERF-*, NFR-SCALE-* | Deployment Diagram (replica sets, load balancer); Component Diagram (separated inference service) |
| NFR-SEC-* | Sequence: Authentication (JWT); Deployment Diagram (TLS termination at NGINX); Security Design doc (Phase 8) |
| NFR-MAINT-1..2 | Class Diagram (layered packages: domain/application/infrastructure); Component Diagram |
| NFR-DATA-1..2 | State Diagram (append-only diagnosis correction flow); ERD (`diagnosis_corrections`) |
| NFR-OBS-1..3 | Deployment Diagram (log aggregation sidecar); API §Health |

Every requirement from Phase 1 has at least one corresponding design element above; no FR/NFR is
undesigned, and no diagram element exists that does not trace back to a requirement or an
architecturally necessary supporting concern (e.g., token refresh, which implements NFR-SEC-3).

## 4. Notation
All diagrams are authored in **Mermaid** syntax (`.mermaid` files), chosen because it is
plain-text, version-controllable, renders natively in the delivery environment, and is readable
without specialized tooling — while still being convertible to PlantUML/image form by any
standard Mermaid renderer if the evaluator's toolchain prefers that.
