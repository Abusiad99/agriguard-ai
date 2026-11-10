"""add diagnoses.predicted_condition

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02 00:00:00.000000

Stores the CV model's raw condition label (e.g. "late_blight") on every diagnosis.
Before this, a predicted disease with no matching knowledge-base row was saved with
disease_id NULL and the label was discarded, so it was indistinguishable from — and
reported as — a healthy result. Nullable: rows saved before this migration keep the
old disease_id-based meaning (see Diagnosis.is_healthy()).

The dashboard materialized view is rebuilt with the same healthy/diseased rule as
SqlAlchemyDiagnosisRepository.dashboard_summary().
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_MV_TEMPLATE = r"""
CREATE MATERIALIZED VIEW mv_dashboard_monthly_stats AS
SELECT
    d.user_id,
    date_trunc('month', d.diagnosed_at)                             AS month,
    p.canonical_name                                                AS plant_name,
    COUNT(*)                                                        AS total_scans,
    COUNT(*) FILTER (WHERE {healthy})                               AS healthy_count,
    COUNT(*) FILTER (WHERE {diseased})                              AS diseased_count,
    COUNT(*) FILTER (WHERE p.canonical_name ILIKE 'date palm')      AS palm_scan_count
FROM diagnoses d
LEFT JOIN plants p ON p.id = d.plant_id
GROUP BY d.user_id, date_trunc('month', d.diagnosed_at), p.canonical_name;

CREATE UNIQUE INDEX idx_mv_dashboard_unique
    ON mv_dashboard_monthly_stats (user_id, month, plant_name);
"""

_PREDICTED_HEALTHY = "(d.predicted_condition IS NULL OR d.predicted_condition = 'healthy')"

UPGRADE_SQL = r"""
ALTER TABLE diagnoses ADD COLUMN predicted_condition VARCHAR(150);

DROP MATERIALIZED VIEW IF EXISTS mv_dashboard_monthly_stats;
""" + _MV_TEMPLATE.format(
    healthy=f"d.disease_id IS NULL AND d.unrecognized_plant = FALSE AND {_PREDICTED_HEALTHY}",
    diseased=f"d.unrecognized_plant = FALSE AND (d.disease_id IS NOT NULL OR NOT {_PREDICTED_HEALTHY})",
)

DOWNGRADE_SQL = r"""
DROP MATERIALIZED VIEW IF EXISTS mv_dashboard_monthly_stats;
""" + _MV_TEMPLATE.format(
    healthy="d.disease_id IS NULL AND d.unrecognized_plant = FALSE",
    diseased="d.disease_id IS NOT NULL",
) + r"""
ALTER TABLE diagnoses DROP COLUMN predicted_condition;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
