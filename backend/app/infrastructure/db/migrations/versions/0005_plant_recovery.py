"""plant recovery monitoring: tracked plants, scan links, treatments, reminders,
assessments, timeline

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-03 00:00:00.000000

Additive only. Every table hangs off `tracked_plants.owner_id` (cascade on user
delete). Diagnoses are referenced, never copied: a diagnosis can belong to at most one
tracked plant (`uq_tracked_plant_scans_diagnosis`), and deleting a link never deletes
the diagnosis. Treatment records are what the user recorded — they are never generated.

Downgrade drops these tables (their data is lost; diagnoses are untouched).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE_SQL = r"""
CREATE TABLE tracked_plants (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id                UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name                    VARCHAR(120) NOT NULL,
    crop                    VARCHAR(100),
    species                 VARCHAR(150),
    location_lat            NUMERIC(9,6),
    location_lon            NUMERIC(9,6),
    notes                   TEXT,
    status                  VARCHAR(20) NOT NULL DEFAULT 'active',
    initial_diagnosis_id    UUID REFERENCES diagnoses (id) ON DELETE SET NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_tracked_plants_status CHECK (status IN ('active', 'archived')),
    CONSTRAINT ck_tracked_plants_location CHECK ((location_lat IS NULL) = (location_lon IS NULL))
);
CREATE INDEX idx_tracked_plants_owner ON tracked_plants (owner_id, created_at DESC);

CREATE TABLE tracked_plant_scans (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tracked_plant_id        UUID NOT NULL REFERENCES tracked_plants (id) ON DELETE CASCADE,
    diagnosis_id            UUID NOT NULL REFERENCES diagnoses (id) ON DELETE CASCADE,
    treatment_stage         VARCHAR(30) NOT NULL DEFAULT 'unknown',
    notes                   TEXT,
    associated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_tracked_plant_scans_diagnosis UNIQUE (diagnosis_id),
    CONSTRAINT ck_tracked_plant_scans_stage CHECK (
        treatment_stage IN ('before_treatment', 'during_treatment', 'after_treatment', 'unknown'))
);
CREATE INDEX idx_tracked_plant_scans_plant ON tracked_plant_scans (tracked_plant_id);

CREATE TABLE treatment_records (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tracked_plant_id        UUID NOT NULL REFERENCES tracked_plants (id) ON DELETE CASCADE,
    name                    VARCHAR(200) NOT NULL,
    category                VARCHAR(20) NOT NULL,
    applied_on              DATE NOT NULL,
    application_notes       TEXT,
    dosage_text             VARCHAR(500),
    documentation_ref       VARCHAR(500),
    follow_up_on            DATE,
    user_notes              TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_treatment_records_category CHECK (
        category IN ('organic', 'chemical', 'biological', 'cultural', 'other'))
);
CREATE INDEX idx_treatment_records_plant ON treatment_records (tracked_plant_id, applied_on DESC);

CREATE TABLE follow_up_reminders (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tracked_plant_id        UUID NOT NULL REFERENCES tracked_plants (id) ON DELETE CASCADE,
    kind                    VARCHAR(30) NOT NULL,
    due_on                  DATE NOT NULL,
    status                  VARCHAR(20) NOT NULL DEFAULT 'pending',
    treatment_record_id     UUID REFERENCES treatment_records (id) ON DELETE SET NULL,
    note                    VARCHAR(500),
    completed_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_follow_up_reminders_kind CHECK (kind IN ('next_scan', 'treatment_follow_up')),
    CONSTRAINT ck_follow_up_reminders_status CHECK (status IN ('pending', 'completed', 'dismissed'))
);
CREATE INDEX idx_follow_up_reminders_plant ON follow_up_reminders (tracked_plant_id, status, due_on);

CREATE TABLE recovery_assessments (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tracked_plant_id        UUID NOT NULL REFERENCES tracked_plants (id) ON DELETE CASCADE,
    status                  VARCHAR(20) NOT NULL,
    method_version          VARCHAR(30) NOT NULL,
    baseline_diagnosis_id   UUID REFERENCES diagnoses (id) ON DELETE SET NULL,
    latest_diagnosis_id     UUID REFERENCES diagnoses (id) ON DELETE SET NULL,
    indicators_json         JSONB,
    limitations_json        JSONB,
    area_series_json        JSONB,
    summary                 TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_recovery_assessments_status CHECK (
        status IN ('improving', 'stable', 'worsening', 'inconclusive', 'insufficient_data'))
);
CREATE INDEX idx_recovery_assessments_plant ON recovery_assessments (tracked_plant_id, created_at DESC);

CREATE TABLE plant_timeline_events (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tracked_plant_id        UUID NOT NULL REFERENCES tracked_plants (id) ON DELETE CASCADE,
    event_type              VARCHAR(40) NOT NULL,
    occurred_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    diagnosis_id            UUID REFERENCES diagnoses (id) ON DELETE SET NULL,
    treatment_record_id     UUID REFERENCES treatment_records (id) ON DELETE SET NULL,
    reminder_id             UUID REFERENCES follow_up_reminders (id) ON DELETE SET NULL,
    assessment_id           UUID REFERENCES recovery_assessments (id) ON DELETE SET NULL,
    details_json            JSONB
);
CREATE INDEX idx_plant_timeline_events_plant ON plant_timeline_events (tracked_plant_id, occurred_at DESC);
"""

DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS plant_timeline_events;
DROP TABLE IF EXISTS recovery_assessments;
DROP TABLE IF EXISTS follow_up_reminders;
DROP TABLE IF EXISTS treatment_records;
DROP TABLE IF EXISTS tracked_plant_scans;
DROP TABLE IF EXISTS tracked_plants;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
