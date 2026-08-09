-- =====================================================================
-- AgriGuard AI — PostgreSQL Schema (Phase 2 Deliverable)
-- Traceability: implements ERD (docs/02-system-design/12-erd.mermaid)
-- and supports FR-AUTH, FR-SCAN, FR-AI, FR-RESULT, FR-TREAT, FR-WEATHER,
-- FR-REPORT, FR-HIST, FR-DASH, FR-ADMIN, and NFR-DATA-1/2.
-- Target: PostgreSQL 14+
-- =====================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- for fast text search on names

-- ---------------------------------------------------------------------
-- ENUM TYPES
-- ---------------------------------------------------------------------
CREATE TYPE user_role AS ENUM ('farmer', 'agronomist', 'admin');
CREATE TYPE severity_level AS ENUM ('mild', 'moderate', 'severe');
CREATE TYPE treatment_category AS ENUM ('organic', 'chemical', 'biological');
CREATE TYPE locale_code AS ENUM ('en', 'ar');

-- ---------------------------------------------------------------------
-- USERS  (FR-AUTH-1..5, BR3, BR4)
-- ---------------------------------------------------------------------
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               VARCHAR(255) NOT NULL,
    password_hash       VARCHAR(255) NOT NULL,
    full_name           VARCHAR(255) NOT NULL,
    role                user_role NOT NULL DEFAULT 'farmer',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    preferred_locale    locale_code NOT NULL DEFAULT 'en',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT ck_users_email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);
CREATE INDEX idx_users_role ON users (role);
CREATE INDEX idx_users_active ON users (is_active);

-- ---------------------------------------------------------------------
-- REFRESH TOKENS  (FR-AUTH-2, FR-AUTH-5, NFR-SEC-3)
-- ---------------------------------------------------------------------
CREATE TABLE refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash      VARCHAR(255) NOT NULL,
    revoked         BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_refresh_tokens_hash UNIQUE (token_hash)
);
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens (user_id);
CREATE INDEX idx_refresh_tokens_expiry ON refresh_tokens (expires_at) WHERE revoked = FALSE;

-- ---------------------------------------------------------------------
-- PASSWORD RESET TOKENS (FR-AUTH-4)
-- ---------------------------------------------------------------------
CREATE TABLE password_reset_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash      VARCHAR(255) NOT NULL,
    used            BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_password_reset_hash UNIQUE (token_hash)
);
CREATE INDEX idx_password_reset_user ON password_reset_tokens (user_id);

-- ---------------------------------------------------------------------
-- PLANTS  (17 supported species; extensible per FR-DATA-2/O9)
-- ---------------------------------------------------------------------
CREATE TABLE plants (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name      VARCHAR(100) NOT NULL,
    scientific_name     VARCHAR(150),
    synonyms_json       JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_plants_canonical_name UNIQUE (canonical_name)
);
CREATE INDEX idx_plants_name_trgm ON plants USING gin (canonical_name gin_trgm_ops);

-- ---------------------------------------------------------------------
-- DISEASES  (versioned/append-only per NFR-DATA-1, UC-09)
-- ---------------------------------------------------------------------
CREATE TABLE diseases (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plant_id                UUID NOT NULL REFERENCES plants (id) ON DELETE RESTRICT,
    name                    VARCHAR(150) NOT NULL,
    disease_type            VARCHAR(100),
    description              TEXT NOT NULL,
    symptoms_json           JSONB NOT NULL DEFAULT '[]'::jsonb,
    causes_json             JSONB NOT NULL DEFAULT '[]'::jsonb,
    transmission_method     VARCHAR(255),
    recovery_probability    NUMERIC(5,2),      -- nullable: only if supported (FR-RESULT-2)
    estimated_recovery_time VARCHAR(100),       -- nullable: only if supported (FR-RESULT-2)
    version                 INTEGER NOT NULL DEFAULT 1,
    is_current              BOOLEAN NOT NULL DEFAULT TRUE,
    created_by              UUID REFERENCES users (id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_diseases_recovery_prob CHECK (recovery_probability IS NULL OR (recovery_probability >= 0 AND recovery_probability <= 100)),
    CONSTRAINT uq_diseases_plant_name_version UNIQUE (plant_id, name, version)
);
CREATE INDEX idx_diseases_plant ON diseases (plant_id);
CREATE INDEX idx_diseases_current ON diseases (is_current) WHERE is_current = TRUE;
CREATE INDEX idx_diseases_name_trgm ON diseases USING gin (name gin_trgm_ops);

-- ---------------------------------------------------------------------
-- TREATMENTS  (BR6: chemical dosage requires source_citation unless
-- authority_referral_only; versioned per UC-10)
-- ---------------------------------------------------------------------
CREATE TABLE treatments (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    disease_id                  UUID NOT NULL REFERENCES diseases (id) ON DELETE RESTRICT,
    category                    treatment_category NOT NULL,
    instructions                TEXT NOT NULL,
    safety_notes                TEXT,
    source_citation             VARCHAR(500),
    authority_referral_only     BOOLEAN NOT NULL DEFAULT FALSE,
    version                     INTEGER NOT NULL DEFAULT 1,
    is_current                  BOOLEAN NOT NULL DEFAULT TRUE,
    created_by                  UUID REFERENCES users (id),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_treatments_dosage_source CHECK (
        category <> 'chemical'
        OR authority_referral_only = TRUE
        OR source_citation IS NOT NULL
    )
);
CREATE INDEX idx_treatments_disease ON treatments (disease_id);
CREATE INDEX idx_treatments_current ON treatments (is_current) WHERE is_current = TRUE;
CREATE INDEX idx_treatments_category ON treatments (category);

-- ---------------------------------------------------------------------
-- DIAGNOSES  (immutable/append-only per NFR-DATA-1, BR2; core of FR-AI)
-- ---------------------------------------------------------------------
CREATE TABLE diagnoses (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                     UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    plant_id                    UUID REFERENCES plants (id),              -- nullable if unrecognized
    disease_id                  UUID REFERENCES diseases (id),            -- nullable if unrecognized/healthy
    confidence_score            NUMERIC(5,2) NOT NULL,
    severity_level              severity_level,
    affected_area_pct           NUMERIC(5,2),
    healthy_area_pct            NUMERIC(5,2),
    original_image_ref          VARCHAR(500) NOT NULL,
    roi_image_ref               VARCHAR(500),
    heatmap_image_ref           VARCHAR(500),
    low_confidence_flag         BOOLEAN NOT NULL DEFAULT FALSE,
    unrecognized_plant          BOOLEAN NOT NULL DEFAULT FALSE,
    location_lat                NUMERIC(9,6),
    location_lon                NUMERIC(9,6),
    supersedes_diagnosis_id     UUID REFERENCES diagnoses (id),
    diagnosed_at                TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_diagnoses_confidence CHECK (confidence_score >= 0 AND confidence_score <= 100),
    CONSTRAINT ck_diagnoses_area_pct CHECK (
        (affected_area_pct IS NULL OR (affected_area_pct >= 0 AND affected_area_pct <= 100)) AND
        (healthy_area_pct IS NULL OR (healthy_area_pct >= 0 AND healthy_area_pct <= 100))
    ),
    CONSTRAINT ck_diagnoses_unrecognized_consistency CHECK (
        (unrecognized_plant = FALSE) OR (disease_id IS NULL AND severity_level IS NULL)
    )
);
CREATE INDEX idx_diagnoses_user ON diagnoses (user_id);
CREATE INDEX idx_diagnoses_plant ON diagnoses (plant_id);
CREATE INDEX idx_diagnoses_disease ON diagnoses (disease_id);
CREATE INDEX idx_diagnoses_date ON diagnoses (diagnosed_at DESC);
CREATE INDEX idx_diagnoses_user_date ON diagnoses (user_id, diagnosed_at DESC);   -- FR-HIST-2 search
CREATE INDEX idx_diagnoses_low_confidence ON diagnoses (low_confidence_flag) WHERE low_confidence_flag = TRUE;

-- ---------------------------------------------------------------------
-- PEST DETECTIONS  (FR-AI-3)
-- ---------------------------------------------------------------------
CREATE TABLE pest_detections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    diagnosis_id    UUID NOT NULL REFERENCES diagnoses (id) ON DELETE CASCADE,
    pest_name       VARCHAR(150) NOT NULL,
    confidence      NUMERIC(5,2) NOT NULL,
    bbox_json       JSONB NOT NULL,

    CONSTRAINT ck_pest_detections_confidence CHECK (confidence >= 0 AND confidence <= 100)
);
CREATE INDEX idx_pest_detections_diagnosis ON pest_detections (diagnosis_id);
CREATE INDEX idx_pest_detections_name ON pest_detections (pest_name);

-- ---------------------------------------------------------------------
-- WEATHER SNAPSHOTS  (FR-WEATHER-1, BR7 freshness)
-- ---------------------------------------------------------------------
CREATE TABLE weather_snapshots (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    diagnosis_id            UUID NOT NULL REFERENCES diagnoses (id) ON DELETE CASCADE,
    temperature_c           NUMERIC(5,2),
    humidity_pct            NUMERIC(5,2),
    wind_speed_kmh          NUMERIC(6,2),
    rain_probability_pct    NUMERIC(5,2),
    uv_index                NUMERIC(4,1),
    retrieved_at            TIMESTAMPTZ NOT NULL,

    CONSTRAINT uq_weather_snapshots_diagnosis UNIQUE (diagnosis_id)
);
CREATE INDEX idx_weather_snapshots_diagnosis ON weather_snapshots (diagnosis_id);

-- ---------------------------------------------------------------------
-- RECOMMENDATIONS  (FR-AI-10, FR-WEATHER-2)
-- ---------------------------------------------------------------------
CREATE TABLE recommendations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    diagnosis_id        UUID NOT NULL REFERENCES diagnoses (id) ON DELETE CASCADE,
    irrigation_advice   TEXT,
    spraying_advice     TEXT,
    fertilizer_advice   TEXT,

    CONSTRAINT uq_recommendations_diagnosis UNIQUE (diagnosis_id)
);
CREATE INDEX idx_recommendations_diagnosis ON recommendations (diagnosis_id);

-- ---------------------------------------------------------------------
-- REPORTS  (FR-REPORT-1/2, BR5)
-- ---------------------------------------------------------------------
CREATE TABLE reports (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    diagnosis_id        UUID NOT NULL REFERENCES diagnoses (id) ON DELETE CASCADE,
    file_ref            VARCHAR(500) NOT NULL,
    qr_code_ref         VARCHAR(500) NOT NULL,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_reports_diagnosis UNIQUE (diagnosis_id)
);
CREATE INDEX idx_reports_diagnosis ON reports (diagnosis_id);

-- ---------------------------------------------------------------------
-- AUDIT LOGS  (UC-11 admin actions, NFR-OBS, knowledge-base edit trail)
-- ---------------------------------------------------------------------
CREATE TABLE audit_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id       UUID REFERENCES users (id),
    action              VARCHAR(100) NOT NULL,
    entity_type         VARCHAR(100) NOT NULL,
    entity_id           UUID,
    metadata_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_logs_actor ON audit_logs (actor_user_id);
CREATE INDEX idx_audit_logs_entity ON audit_logs (entity_type, entity_id);
CREATE INDEX idx_audit_logs_date ON audit_logs (created_at DESC);

-- ---------------------------------------------------------------------
-- MATERIALIZED VIEW: DASHBOARD SUMMARY (FR-DASH, NFR-PERF-3)
-- Refreshed on a schedule (see Deployment/Maintenance Plan, Phase 9).
-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- TRIGGER: keep users.updated_at current
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_set_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

COMMIT;
