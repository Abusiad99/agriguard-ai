"""disease localization: diagnosis_segmentations + diagnoses.image_quality_json

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-03 00:00:00.000000

Additive only. `diagnosis_segmentations` is 1:1 with a diagnosis (cascade-deleted
with it) and records the segmentation model's output — or why there was none
(status = not_trained, dataset_unavailable, failed, ...). `artifact_dir` is a private
storage key (served only through the authenticated diagnosis endpoint, never exposed).
`diagnoses.image_quality_json` holds the per-scan image quality checks; NULL for scans
made before this revision.

Downgrade drops the table and the column (their data is lost; nothing else changes).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE_SQL = r"""
ALTER TABLE diagnoses ADD COLUMN image_quality_json JSONB;

CREATE TABLE diagnosis_segmentations (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    diagnosis_id                UUID NOT NULL REFERENCES diagnoses (id) ON DELETE CASCADE,
    status                      VARCHAR(30) NOT NULL,
    model_name                  VARCHAR(100),
    model_version               VARCHAR(150),
    image_width                 INTEGER,
    image_height                INTEGER,
    mask_width                  INTEGER,
    mask_height                 INTEGER,
    affected_pixels             BIGINT,
    plant_pixels                BIGINT,
    affected_area_pct           NUMERIC(5,2),
    area_basis                  VARCHAR(30),
    area_unavailable_reason     VARCHAR(60),
    class_pixels_json           JSONB,
    regions_json                JSONB,
    classes_json                JSONB,
    mean_confidence             NUMERIC(5,4),
    mean_uncertainty            NUMERIC(5,4),
    inference_ms                INTEGER,
    artifact_dir                VARCHAR(500),
    message                     TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_diagnosis_segmentations_diagnosis UNIQUE (diagnosis_id),
    CONSTRAINT ck_diagnosis_segmentations_pct CHECK (
        affected_area_pct IS NULL OR (affected_area_pct >= 0 AND affected_area_pct <= 100)),
    CONSTRAINT ck_diagnosis_segmentations_pct_needs_basis CHECK (
        affected_area_pct IS NULL OR (plant_pixels IS NOT NULL AND plant_pixels > 0))
);
"""

DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS diagnosis_segmentations;
ALTER TABLE diagnoses DROP COLUMN IF EXISTS image_quality_json;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
