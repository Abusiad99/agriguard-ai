"""outbreak prediction: grid areas, disease observations, weather cache, predictions

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-03 00:00:00.000000

Additive only.
- geo_areas: grid cells (ai/outbreak/grid.py); observations are aggregated to cells
  so no individual location is ever stored here or shown.
- disease_observations: one row per located, opted-in scan (source app_scan, linked to
  its diagnosis — not a copy of it) or per imported survey record (source dataset).
- weather_observations: daily weather cache per cell ('observed' or 'forecast').
  Missing values stay NULL.
- outbreak_predictions: every stored risk result with its model version, score kind
  (calibrated_probability vs risk_score), data completeness, factors and limitations.

Downgrade drops these tables (their data is lost; diagnoses are untouched).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE_SQL = r"""
CREATE TABLE geo_areas (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grid_key            VARCHAR(40) NOT NULL,
    resolution_deg      NUMERIC(6,3) NOT NULL,
    lat_index           INTEGER NOT NULL,
    lon_index           INTEGER NOT NULL,
    south               NUMERIC(9,6) NOT NULL,
    west                NUMERIC(9,6) NOT NULL,
    north               NUMERIC(9,6) NOT NULL,
    east                NUMERIC(9,6) NOT NULL,
    center_lat          NUMERIC(9,6) NOT NULL,
    center_lon          NUMERIC(9,6) NOT NULL,
    name                VARCHAR(150),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_geo_areas_grid_key UNIQUE (grid_key)
);
CREATE INDEX idx_geo_areas_center ON geo_areas (center_lat, center_lon);

CREATE TABLE disease_observations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    area_id             UUID NOT NULL REFERENCES geo_areas (id) ON DELETE CASCADE,
    source              VARCHAR(20) NOT NULL,
    diagnosis_id        UUID REFERENCES diagnoses (id) ON DELETE CASCADE,
    dataset_version     VARCHAR(40),
    crop                VARCHAR(100) NOT NULL,
    disease             VARCHAR(150) NOT NULL,
    is_positive         BOOLEAN NOT NULL,
    inspected_count     INTEGER NOT NULL DEFAULT 1,
    positive_count      INTEGER NOT NULL DEFAULT 0,
    observed_on         DATE NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_disease_observations_diagnosis UNIQUE (diagnosis_id),
    CONSTRAINT ck_disease_observations_source CHECK (
        (source = 'app_scan' AND diagnosis_id IS NOT NULL) OR (source = 'dataset' AND diagnosis_id IS NULL)),
    CONSTRAINT ck_disease_observations_counts CHECK (
        inspected_count >= 1 AND positive_count >= 0 AND positive_count <= inspected_count)
);
CREATE INDEX idx_disease_observations_area ON disease_observations (area_id, crop, observed_on);
CREATE INDEX idx_disease_observations_lookup ON disease_observations (crop, disease, observed_on);

CREATE TABLE weather_observations (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    area_id                     UUID NOT NULL REFERENCES geo_areas (id) ON DELETE CASCADE,
    day                         DATE NOT NULL,
    kind                        VARCHAR(12) NOT NULL,
    source                      VARCHAR(40) NOT NULL,
    temperature_mean_c          NUMERIC(5,2),
    temperature_min_c           NUMERIC(5,2),
    temperature_max_c           NUMERIC(5,2),
    relative_humidity_mean_pct  NUMERIC(5,2),
    rh_hours_ge_90              NUMERIC(4,1),
    precipitation_mm            NUMERIC(7,2),
    retrieved_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_weather_observations UNIQUE (area_id, day, kind),
    CONSTRAINT ck_weather_observations_kind CHECK (kind IN ('observed', 'forecast'))
);

CREATE TABLE outbreak_predictions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    area_id             UUID NOT NULL REFERENCES geo_areas (id) ON DELETE CASCADE,
    crop                VARCHAR(100) NOT NULL,
    disease             VARCHAR(150) NOT NULL,
    horizon_days        INTEGER NOT NULL,
    as_of               DATE NOT NULL,
    forecast_start      DATE NOT NULL,
    forecast_end        DATE NOT NULL,
    status              VARCHAR(30) NOT NULL,
    risk_level          VARCHAR(20) NOT NULL,
    score               NUMERIC(6,4),
    score_kind          VARCHAR(30),
    confidence_level    VARCHAR(10),
    data_completeness   NUMERIC(4,3),
    model_name          VARCHAR(100),
    model_version       VARCHAR(150),
    factors_json        JSONB,
    features_json       JSONB,
    suitability_json    JSONB,
    limitations_json    JSONB,
    requested_by        UUID REFERENCES users (id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_outbreak_predictions_horizon CHECK (horizon_days BETWEEN 1 AND 16),
    CONSTRAINT ck_outbreak_predictions_status CHECK (status IN ('ok', 'insufficient_data')),
    CONSTRAINT ck_outbreak_predictions_score CHECK (score IS NULL OR (score >= 0 AND score <= 1))
);
CREATE INDEX idx_outbreak_predictions_area ON outbreak_predictions (area_id, crop, disease, created_at DESC);
"""

DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS outbreak_predictions;
DROP TABLE IF EXISTS weather_observations;
DROP TABLE IF EXISTS disease_observations;
DROP TABLE IF EXISTS geo_areas;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
