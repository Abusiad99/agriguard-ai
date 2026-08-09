# AgriGuard AI — Non-Functional Requirements (NFRs)

## NFR-PERF — Performance
- **NFR-PERF-1**: End-to-end inference (Steps 1–8, excluding external weather call) shall complete
  in under 5 seconds on a mid-range GPU (e.g., NVIDIA T4 class) and under 20 seconds on CPU-only
  inference, for a single image at the model's native input resolution.
- **NFR-PERF-2**: The API shall support at least 50 concurrent diagnosis requests under horizontal
  scaling (multiple backend replicas behind NGINX) without error-rate degradation beyond 1%.
- **NFR-PERF-3**: Dashboard analytics queries shall return in under 1 second for accounts with up
  to 100,000 historical scans, achieved via appropriate database indexing and, where needed,
  pre-aggregated summary tables refreshed on a schedule.

## NFR-SCALE — Scalability
- **NFR-SCALE-1**: The backend shall be stateless with respect to application logic (session state
  in Redis/JWT, not in-process memory) so it can scale horizontally behind a load balancer.
- **NFR-SCALE-2**: The AI inference component shall be separable into its own service/process pool
  so it can be scaled independently from the API/business-logic layer under high load.

## NFR-AVAIL — Availability & Reliability
- **NFR-AVAIL-1**: The production deployment shall target 99.5% monthly uptime for the API and
  frontend.
- **NFR-AVAIL-2**: The system shall degrade gracefully: if the weather API is unreachable, the
  diagnosis pipeline shall still complete and return results, omitting only weather-dependent
  fields (per BR7).
- **NFR-AVAIL-3**: All external calls (weather API) shall be wrapped with timeouts and retries
  with exponential backoff, bounded to a maximum total wait that does not stall the pipeline
  beyond NFR-PERF-1's budget.

## NFR-SEC — Security
- **NFR-SEC-1**: All API traffic shall be served over HTTPS/TLS in production (terminated at
  NGINX).
- **NFR-SEC-2**: Passwords shall be hashed with a modern adaptive hash (bcrypt or argon2) with a
  per-user salt.
- **NFR-SEC-3**: All endpoints except authentication and public health-check shall require a valid
  JWT; role-gated endpoints shall enforce role checks server-side, not only in the frontend.
- **NFR-SEC-4**: All user-supplied input (including image files and form fields) shall be
  validated and sanitized server-side; file uploads shall be validated by content-sniffing, not
  by trusting the file extension or client-provided MIME type.
- **NFR-SEC-5**: The system shall apply rate limiting to authentication and scan-submission
  endpoints to mitigate brute-force and abuse.
- **NFR-SEC-6**: Full details are specified in the Security Design document (Phase/doc
  `05-security`).

## NFR-USAB — Usability
- **NFR-USAB-1**: The core "scan → result" flow shall be completable in 3 taps/clicks or fewer
  from the home screen.
- **NFR-USAB-2**: The frontend shall be responsive from ~360px mobile viewports up through desktop
  widths.
- **NFR-USAB-3**: The system shall present results using plain, non-technical language as the
  primary copy, with technical detail (confidence score, model name) available but not
  foregrounded, given the primary persona (Farmer Youssef) is not a technical user.
- **NFR-USAB-4**: The frontend shall support English and Arabic UI copy given the project's
  bilingual usage context, with correct RTL layout when Arabic is active.

## NFR-MAINT — Maintainability
- **NFR-MAINT-1**: The backend shall follow Clean Architecture layering (domain / application /
  infrastructure / interface) so business logic is independent of framework and database details.
- **NFR-MAINT-2**: The codebase shall adhere to SOLID principles, with dependency inversion used
  for the database layer, AI model layer, and external API integrations (mirroring the
  Dependency-Inversion pattern already used for the DeepShield Firestore backend).
- **NFR-MAINT-3**: All modules shall have unit test coverage for core business logic; integration
  tests shall cover full pipeline flows (see Test Plan).
- **NFR-MAINT-4**: Configuration (paths, thresholds, API keys, batch sizes) shall be externalized
  to environment variables / a config file, never hardcoded in source.

## NFR-PORT — Portability
- **NFR-PORT-1**: The entire system shall be deployable via `docker compose up` on any Docker-
  compatible host (Linux/macOS/Windows with WSL2), with no host-OS-specific code paths.
- **NFR-PORT-2**: The AI training pipeline shall run on both CUDA-enabled GPUs and CPU-only
  machines without code changes, auto-detecting the available device.

## NFR-DATA — Data Integrity & Auditability
- **NFR-DATA-1**: Every diagnosis record shall be immutable once created (append-only for
  corrections — a correction creates a new linked record rather than overwriting history), to
  preserve audit trails for O7.
- **NFR-DATA-2**: Database migrations shall be version-controlled and reproducible (Alembic).

## NFR-I18N — Internationalization
- **NFR-I18N-1**: All user-facing strings shall be externalized into locale resource files
  (English/Arabic at minimum) rather than hardcoded in components, consistent with the bilingual
  usage pattern already established in this project's other deliverables.

## NFR-OBS — Observability
- **NFR-OBS-1**: The backend shall emit structured (JSON) logs with correlation IDs per request,
  centrally collectible (stdout, consumable by any log aggregator).
- **NFR-OBS-2**: The system shall expose a `/health` endpoint reporting database, cache, and model-
  loading status for use by container orchestration liveness/readiness probes.
- **NFR-OBS-3**: Model inference shall log input image hash, predicted class, and confidence for
  every request (excluding raw image bytes) to support later drift analysis, without storing
  personally identifying information beyond what the user record already contains.
