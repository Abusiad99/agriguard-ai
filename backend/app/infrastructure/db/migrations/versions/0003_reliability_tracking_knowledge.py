"""reliability metadata, plant profiles & observations, knowledge documents (RAG)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29 00:00:00.000000

Additive migration — no existing column, row, or constraint is dropped or rewritten:

1. plant_profiles: user-owned plant records (a specific plant/bed/tree the user
   tracks over time). Distinct from the existing `plants` table, which is the
   species catalogue of the knowledge base.
2. diagnoses (each diagnosis is a time-stamped health OBSERVATION): new nullable
   columns recording which plant profile it belongs to and the provenance needed to
   interpret it later — decision status, candidates, image-quality report,
   explanation and segmentation metadata, severity method, model & pipeline
   versions. Existing rows are backfilled with decision_status='legacy' and, where
   they carry an affected-area value, severity_method='legacy_gradcam_threshold', so
   the UI can label those old numbers as NOT being segmentation measurements.
3. observation_notes: append-only notes/feedback attached to an observation (user
   notes, follow-up answers, treatment applied, expert feedback, corrections). A
   correction never edits the original diagnosis row; it is a new note.
4. kb_documents / kb_chunks: source documents with provenance metadata and their
   retrievable chunks for the assistant's retrieval-augmented generation.
5. assistant_usage: per-request accounting used for per-user rate/cost limits.
6. mv_dashboard_monthly_stats is recreated so "healthy" no longer means "no disease
   record was found" (a knowledge-base gap) but a confident healthy prediction.

PostgreSQL-specific (like 0001/0002); the test suite builds the schema from the ORM
models on SQLite instead.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UPGRADE_SQL = r"""
-- ---------------------------------------------------------------------
-- PLANT PROFILES (user-owned, longitudinal tracking)
-- ---------------------------------------------------------------------
CREATE TABLE plant_profiles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id       UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name                VARCHAR(100) NOT NULL,
    crop_type           VARCHAR(100),
    variety             VARCHAR(100),
    planting_date       DATE,
    location_label      VARCHAR(200),
    growing_environment VARCHAR(20),
    notes               TEXT,
    archived_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_plant_profiles_name CHECK (length(btrim(name)) > 0),
    CONSTRAINT ck_plant_profiles_env CHECK (
        growing_environment IS NULL OR
        growing_environment IN ('field', 'greenhouse', 'indoor', 'orchard', 'nursery', 'other')
    )
);
CREATE INDEX idx_plant_profiles_owner ON plant_profiles (owner_user_id, archived_at);

CREATE TRIGGER plant_profiles_set_updated_at
    BEFORE UPDATE ON plant_profiles
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- ---------------------------------------------------------------------
-- DIAGNOSES -> observation provenance (all nullable; legacy rows backfilled)
-- ---------------------------------------------------------------------
ALTER TABLE diagnoses
    ADD COLUMN plant_profile_id          UUID REFERENCES plant_profiles (id) ON DELETE SET NULL,
    ADD COLUMN decision_status           VARCHAR(20),
    ADD COLUMN predicted_label           VARCHAR(200),
    ADD COLUMN candidates_json           JSONB,
    ADD COLUMN decision_json             JSONB,
    ADD COLUMN image_quality_json        JSONB,
    ADD COLUMN explanation_json          JSONB,
    ADD COLUMN segmentation_json         JSONB,
    ADD COLUMN segmentation_mask_ref     VARCHAR(500),
    ADD COLUMN segmentation_overlay_ref  VARCHAR(500),
    ADD COLUMN severity_method           VARCHAR(50),
    ADD COLUMN model_version             VARCHAR(150),
    ADD COLUMN pipeline_version          VARCHAR(20),
    ADD COLUMN differential_json         JSONB,
    ADD CONSTRAINT ck_diagnoses_decision_status CHECK (
        decision_status IS NULL OR
        decision_status IN ('confident', 'uncertain', 'inconclusive', 'legacy')
    );

CREATE INDEX idx_diagnoses_profile_date ON diagnoses (plant_profile_id, diagnosed_at DESC);
CREATE INDEX idx_diagnoses_user_status ON diagnoses (user_id, decision_status);

UPDATE diagnoses
   SET decision_status = 'legacy',
       pipeline_version = '1.x',
       severity_method = CASE WHEN affected_area_pct IS NOT NULL THEN 'legacy_gradcam_threshold' ELSE NULL END
 WHERE decision_status IS NULL;

-- ---------------------------------------------------------------------
-- OBSERVATION NOTES (append-only audit trail)
-- ---------------------------------------------------------------------
CREATE TABLE observation_notes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    diagnosis_id    UUID NOT NULL REFERENCES diagnoses (id) ON DELETE CASCADE,
    author_user_id  UUID REFERENCES users (id) ON DELETE SET NULL,
    note_type       VARCHAR(30) NOT NULL,
    body            TEXT NOT NULL DEFAULT '',
    data_json       JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_observation_notes_type CHECK (note_type IN (
        'user_note', 'follow_up', 'treatment_applied', 'expert_feedback', 'correction', 'plant_link_change'
    )),
    CONSTRAINT ck_observation_notes_body_len CHECK (length(body) <= 4000)
);
CREATE INDEX idx_observation_notes_diagnosis ON observation_notes (diagnosis_id, created_at);

-- ---------------------------------------------------------------------
-- KNOWLEDGE DOCUMENTS & CHUNKS (retrieval-augmented assistant)
-- ---------------------------------------------------------------------
CREATE TABLE kb_documents (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title            VARCHAR(300) NOT NULL,
    organization     VARCHAR(200) NOT NULL,
    source_url       VARCHAR(1000),
    source_type      VARCHAR(40) NOT NULL,
    language         VARCHAR(5) NOT NULL DEFAULT 'en',
    published_date   DATE,
    revised_date     DATE,
    retrieved_at     TIMESTAMPTZ,
    crops_json       JSONB NOT NULL DEFAULT '[]'::jsonb,
    diseases_json    JSONB NOT NULL DEFAULT '[]'::jsonb,
    license_note     VARCHAR(300),
    content_sha256   CHAR(64) NOT NULL,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_by       UUID REFERENCES users (id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_kb_documents_sha UNIQUE (content_sha256),
    CONSTRAINT ck_kb_documents_source_type CHECK (source_type IN (
        'government', 'university_extension', 'research_institution', 'pathology_society',
        'pesticide_label', 'regulatory', 'agriguard_knowledge_base', 'other'
    ))
);
CREATE INDEX idx_kb_documents_active ON kb_documents (is_active);

CREATE TABLE kb_chunks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id      UUID NOT NULL REFERENCES kb_documents (id) ON DELETE CASCADE,
    chunk_index      INTEGER NOT NULL,
    section          VARCHAR(300),
    text             TEXT NOT NULL,
    token_count      INTEGER NOT NULL DEFAULT 0,
    embedding_json   JSONB,
    embedding_model  VARCHAR(100),

    CONSTRAINT uq_kb_chunks_doc_idx UNIQUE (document_id, chunk_index)
);
CREATE INDEX idx_kb_chunks_document ON kb_chunks (document_id);

-- ---------------------------------------------------------------------
-- ASSISTANT USAGE (rate / cost control)
-- ---------------------------------------------------------------------
CREATE TABLE assistant_usage (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    mode              VARCHAR(20) NOT NULL,
    llm_called        BOOLEAN NOT NULL DEFAULT FALSE,
    retrieved_chunks  INTEGER NOT NULL DEFAULT 0,
    input_chars       INTEGER NOT NULL DEFAULT 0,
    output_chars      INTEGER NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_assistant_usage_user_date ON assistant_usage (user_id, created_at DESC);

-- ---------------------------------------------------------------------
-- DASHBOARD MATERIALIZED VIEW: healthy = confident healthy prediction
-- ---------------------------------------------------------------------
DROP MATERIALIZED VIEW IF EXISTS mv_dashboard_monthly_stats;
CREATE MATERIALIZED VIEW mv_dashboard_monthly_stats AS
SELECT
    d.user_id,
    date_trunc('month', d.diagnosed_at)                             AS month,
    p.canonical_name                                                AS plant_name,
    COUNT(*)                                                        AS total_scans,
    COUNT(*) FILTER (WHERE d.decision_status = 'confident'
                       AND d.predicted_label LIKE '%\_\_\_healthy' ESCAPE '\') AS healthy_count,
    COUNT(*) FILTER (WHERE d.disease_id IS NOT NULL
                        OR (d.decision_status = 'confident'
                            AND d.predicted_label NOT LIKE '%\_\_\_healthy' ESCAPE '\')) AS diseased_count,
    COUNT(*) FILTER (WHERE d.decision_status IN ('uncertain', 'inconclusive')) AS uncertain_count,
    COUNT(*) FILTER (WHERE p.canonical_name ILIKE 'date palm')      AS palm_scan_count
FROM diagnoses d
LEFT JOIN plants p ON p.id = d.plant_id
GROUP BY d.user_id, date_trunc('month', d.diagnosed_at), p.canonical_name;

CREATE UNIQUE INDEX idx_mv_dashboard_unique
    ON mv_dashboard_monthly_stats (user_id, month, plant_name);
"""

DOWNGRADE_SQL = r"""
DROP MATERIALIZED VIEW IF EXISTS mv_dashboard_monthly_stats;
CREATE MATERIALIZED VIEW mv_dashboard_monthly_stats AS
SELECT
    d.user_id,
    date_trunc('month', d.diagnosed_at)                             AS month,
    p.canonical_name                                                AS plant_name,
    COUNT(*)                                                        AS total_scans,
    COUNT(*) FILTER (WHERE d.disease_id IS NULL AND d.unrecognized_plant = FALSE) AS healthy_count,
    COUNT(*) FILTER (WHERE d.disease_id IS NOT NULL)                AS diseased_count,
    COUNT(*) FILTER (WHERE p.canonical_name ILIKE 'date palm')      AS palm_scan_count
FROM diagnoses d
LEFT JOIN plants p ON p.id = d.plant_id
GROUP BY d.user_id, date_trunc('month', d.diagnosed_at), p.canonical_name;
CREATE UNIQUE INDEX idx_mv_dashboard_unique
    ON mv_dashboard_monthly_stats (user_id, month, plant_name);

DROP TABLE IF EXISTS assistant_usage;
DROP TABLE IF EXISTS kb_chunks;
DROP TABLE IF EXISTS kb_documents;
DROP TABLE IF EXISTS observation_notes;

DROP INDEX IF EXISTS idx_diagnoses_user_status;
DROP INDEX IF EXISTS idx_diagnoses_profile_date;
ALTER TABLE diagnoses
    DROP CONSTRAINT IF EXISTS ck_diagnoses_decision_status,
    DROP COLUMN IF EXISTS differential_json,
    DROP COLUMN IF EXISTS pipeline_version,
    DROP COLUMN IF EXISTS model_version,
    DROP COLUMN IF EXISTS severity_method,
    DROP COLUMN IF EXISTS segmentation_overlay_ref,
    DROP COLUMN IF EXISTS segmentation_mask_ref,
    DROP COLUMN IF EXISTS segmentation_json,
    DROP COLUMN IF EXISTS explanation_json,
    DROP COLUMN IF EXISTS image_quality_json,
    DROP COLUMN IF EXISTS decision_json,
    DROP COLUMN IF EXISTS candidates_json,
    DROP COLUMN IF EXISTS predicted_label,
    DROP COLUMN IF EXISTS decision_status,
    DROP COLUMN IF EXISTS plant_profile_id;

DROP TRIGGER IF EXISTS plant_profiles_set_updated_at ON plant_profiles;
DROP TABLE IF EXISTS plant_profiles;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
