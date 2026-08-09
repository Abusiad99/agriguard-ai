# AgriGuard AI — Database Design

## 1. Files
- `01-schema.sql` — full DDL: extensions, enum types, tables, constraints, indexes, a
  materialized view for dashboard performance (NFR-PERF-3), and a trigger for `updated_at`
  maintenance. Wrapped in a single transaction (`BEGIN`/`COMMIT`) so it applies atomically.

## 2. Applying the Schema
```bash
createdb agriguard
psql -d agriguard -f database/01-schema.sql
```
Or, via Docker Compose (see Phase 9 deployment docs), the schema is mounted into the Postgres
container's `/docker-entrypoint-initdb.d/` on first boot.

## 3. Design Notes & Deviations from the Conceptual ERD
The ERD (`docs/02-system-design/12-erd.mermaid`) models `TREATMENT_CATEGORIES` as a lookup
entity for readability. In the physical schema this is implemented as a native PostgreSQL
`ENUM` type (`treatment_category`) rather than a separate table, because the category set
(organic/chemical/biological) is fixed by the functional requirements (FR-TREAT-1) and not
user-extensible — an ENUM gives the same referential guarantee with less join overhead. If a
future requirement makes treatment categories admin-editable, this should be migrated to a
proper lookup table via an Alembic migration (see NFR-DATA-2).

## 4. Key Design Decisions Traced to Requirements
| Decision | Requirement |
|---|---|
| `diagnoses` has no `UPDATE`-oriented workflow; corrections are new rows linked via `supersedes_diagnosis_id` | NFR-DATA-1 (immutability/audit trail), State Diagram `Superseded` state |
| `diseases` and `treatments` are versioned (`version`, `is_current`) rather than mutated in place | NFR-DATA-1, UC-09/UC-10 |
| `treatments` has a CHECK constraint enforcing `source_citation` (or explicit `authority_referral_only`) for chemical treatments | BR6, FR-TREAT-3 |
| `diseases.recovery_probability` / `estimated_recovery_time` are nullable with no default | FR-RESULT-2 — only shown when present, never fabricated |
| `diagnoses.confidence_score` and area percentages are constrained to [0,100] | Data integrity for FR-AI-5/6 |
| `mv_dashboard_monthly_stats` materialized view | NFR-PERF-3 — sub-1s dashboard queries at scale |
| Composite index `idx_diagnoses_user_date` | FR-HIST-2 — history search/filter performance |
| `pg_trgm` GIN indexes on plant/disease names | Fast fuzzy search in admin panel and knowledge base lookups |
| `audit_logs` table, generic `entity_type`/`entity_id` | UC-11 (user mgmt actions), UC-09/10 (KB edit trail) |
| `refresh_tokens` with `revoked` flag + expiry index | FR-AUTH-5, NFR-SEC-3 (token rotation/revocation) |

## 5. Indexing Strategy Summary
- **Primary keys**: all `UUID` via `gen_random_uuid()` (pgcrypto), avoiding sequential-ID
  enumeration attacks and simplifying multi-instance inserts (NFR-SCALE-1).
- **Foreign keys**: every relationship in the ERD is enforced at the database level, not only in
  application code, with `ON DELETE` behavior chosen per entity semantics (`CASCADE` for
  strictly-owned child records like tokens/pest detections/weather/reports; `RESTRICT` for
  reference data like plants/diseases that must not be silently deleted out from under historical
  diagnoses).
- **Partial indexes** (`WHERE is_current = TRUE`, `WHERE revoked = FALSE`, `WHERE
  low_confidence_flag = TRUE`) keep hot-path indexes small and fast for the queries that actually
  drive the UI (current KB entries, active tokens, review queue).
- **GIN trigram indexes** support `ILIKE '%term%'` style search used by admin KB search and
  history search without requiring a separate search engine for this project's scale.

## 6. Migration Strategy
Per NFR-DATA-2, all schema evolution after this initial DDL is managed via **Alembic**
migrations (Python), versioned in `backend/app/infrastructure/db/migrations/`, generated in
Phase 4 (Backend Implementation). `01-schema.sql` represents migration `0001_initial` in DDL form
for direct review; the Alembic migration is the source of truth once the backend is implemented.
