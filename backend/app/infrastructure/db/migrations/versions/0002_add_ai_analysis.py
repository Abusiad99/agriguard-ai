"""add ai_analyses table (Gemini multimodal reasoning layer)

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-10 00:00:00.000000

Adds a single new table, `ai_analyses`, 1:1 with `diagnoses` and cascade-deleted
with it — the same shape as the existing `weather_snapshots` and `recommendations`
tables (see 0001_initial_schema.py). This is an additive, optional table: existing
diagnoses continue to work identically with no row here at all, and the Gemini
reasoning layer can be fully disabled (no GEMINI_API_KEY configured) without this
table ever being written to. No existing table, column, or constraint is modified.

See docs/GEMINI_INTEGRATION.md and
backend/app/interface/schemas/ai_analysis_schemas.py for what each field holds.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UPGRADE_SQL = r"""
-- ---------------------------------------------------------------------
-- AI_ANALYSES  (Gemini multimodal reasoning layer — additive/optional)
-- ---------------------------------------------------------------------
CREATE TABLE ai_analyses (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    diagnosis_id                UUID NOT NULL REFERENCES diagnoses (id) ON DELETE CASCADE,
    status                      VARCHAR(20) NOT NULL,        -- 'ok' | 'unavailable'
    diagnosis_explanation       TEXT,
    observed_symptoms_json      JSONB,
    cv_consistency              VARCHAR(30),                 -- consistent | partially_consistent | inconsistent | uncertain
    confidence_assessment       TEXT,
    severity_explanation        TEXT,
    treatment_guidance_json     JSONB,
    prevention_guidance_json    JSONB,
    environmental_risk          TEXT,
    urgency                     VARCHAR(10),                 -- low | medium | high
    model_name                  VARCHAR(100),
    message                     TEXT,
    generated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_ai_analyses_diagnosis UNIQUE (diagnosis_id),
    CONSTRAINT chk_ai_analyses_status CHECK (status IN ('ok', 'unavailable'))
);
CREATE INDEX idx_ai_analyses_diagnosis ON ai_analyses (diagnosis_id);
"""

DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS ai_analyses;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
