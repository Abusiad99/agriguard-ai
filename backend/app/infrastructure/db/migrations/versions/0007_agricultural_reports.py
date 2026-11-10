"""agricultural reports: stored, versioned report snapshots, share links, top predictions

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-04 00:00:00.000000

Additive only.
- diagnoses.top_predictions_json: the classifier's top-3 (plant, condition, confidence)
  for new scans, so reports can list alternative diagnoses. NULL for older scans.
- generated_reports: one immutable row per generated report version (diagnosis, plant
  progress or outbreak area). content_json is the full structured report; sources_json
  names every record it was built from and data_hash fingerprints that input, so a report
  can be traced and reproduced. Regenerating adds a new version; old ones are kept.
- report_shares: expiring, revocable read-only links. Only a SHA-256 hash of the token
  is stored.

The existing `reports` table (per-scan PDF from the scan pipeline) is unchanged.
Downgrade drops the new tables and column.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE_SQL = r"""
ALTER TABLE diagnoses ADD COLUMN top_predictions_json JSONB;

CREATE TABLE generated_reports (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id            UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    report_type         VARCHAR(30) NOT NULL,
    subject_id          UUID NOT NULL,
    version             INTEGER NOT NULL,
    supersedes_id       UUID REFERENCES generated_reports (id) ON DELETE SET NULL,
    title               VARCHAR(300) NOT NULL,
    locale              VARCHAR(5) NOT NULL,
    crop                VARCHAR(100),
    disease             VARCHAR(150),
    status_summary      VARCHAR(40),
    period_start        DATE,
    period_end          DATE,
    schema_version      VARCHAR(40) NOT NULL,
    generator_version   VARCHAR(40) NOT NULL,
    content_json        JSONB NOT NULL,
    sources_json        JSONB NOT NULL,
    data_hash           VARCHAR(64) NOT NULL,
    narrative_source    VARCHAR(20) NOT NULL,
    narrative_model     VARCHAR(100),
    pdf_refs_json       JSONB,
    created_by          UUID REFERENCES users (id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_generated_reports_type CHECK (report_type IN ('diagnosis', 'plant_progress', 'outbreak_area')),
    CONSTRAINT ck_generated_reports_locale CHECK (locale IN ('en', 'ar')),
    CONSTRAINT ck_generated_reports_narrative CHECK (narrative_source IN ('llm', 'template')),
    CONSTRAINT uq_generated_reports_version UNIQUE (owner_id, report_type, subject_id, version)
);
CREATE INDEX idx_generated_reports_owner ON generated_reports (owner_id, created_at DESC);
CREATE INDEX idx_generated_reports_subject ON generated_reports (report_type, subject_id, version DESC);

CREATE TABLE report_shares (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id           UUID NOT NULL REFERENCES generated_reports (id) ON DELETE CASCADE,
    token_hash          VARCHAR(64) NOT NULL,
    created_by          UUID REFERENCES users (id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at          TIMESTAMPTZ NOT NULL,
    revoked_at          TIMESTAMPTZ,
    last_accessed_at    TIMESTAMPTZ,
    access_count        INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_report_shares_token UNIQUE (token_hash)
);
CREATE INDEX idx_report_shares_report ON report_shares (report_id);
"""

DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS report_shares;
DROP TABLE IF EXISTS generated_reports;
ALTER TABLE diagnoses DROP COLUMN IF EXISTS top_predictions_json;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
