"""knowledge references: structured sources and the claims they support

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-07 00:00:00.000000

Additive only.
- knowledge_references: one row per source (title, authors, organization, URL, DOI,
  publication date as published, source type, verification date). URLs are unique.
  Rows are deactivated, never deleted, so reports that cited them stay traceable.
- knowledge_reference_claims: what a reference supports, attached to a knowledge-base
  disease (stable key "<plant>/<disease name>", survives new versions), a treatment
  (its row id: a revised treatment needs its source re-checked), or an AgriGuard rule,
  guidance item or method.

Existing tables, including treatments.source_citation (free text), are unchanged.
Downgrade drops the two new tables.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE_SQL = r"""
CREATE TABLE knowledge_references (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title               VARCHAR(500) NOT NULL,
    authors             VARCHAR(500),
    organization        VARCHAR(300),
    url                 VARCHAR(1000) NOT NULL,
    doi                 VARCHAR(200),
    publication_date    VARCHAR(60),
    source_type         VARCHAR(40) NOT NULL,
    language            VARCHAR(8) NOT NULL DEFAULT 'en',
    notes               TEXT,
    verified_on         DATE,
    verified_by         UUID REFERENCES users (id) ON DELETE SET NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_by          UUID REFERENCES users (id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_knowledge_references_url UNIQUE (url),
    CONSTRAINT ck_knowledge_references_url CHECK (url LIKE 'https://%' OR url LIKE 'http://%'),
    CONSTRAINT ck_knowledge_references_type CHECK (source_type IN (
        'agricultural_authority', 'university_extension', 'research_institute', 'peer_reviewed',
        'international_organization', 'educational_resource', 'other'))
);

CREATE TABLE knowledge_reference_claims (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reference_id        UUID NOT NULL REFERENCES knowledge_references (id) ON DELETE CASCADE,
    subject_type        VARCHAR(20) NOT NULL,
    subject_key         VARCHAR(200),
    subject_id          UUID,
    claim               TEXT NOT NULL,
    created_by          UUID REFERENCES users (id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_reference_claims_type CHECK (subject_type IN ('disease', 'treatment', 'rule', 'guidance', 'method')),
    CONSTRAINT ck_reference_claims_subject CHECK (subject_key IS NOT NULL OR subject_id IS NOT NULL)
);
CREATE INDEX idx_reference_claims_key ON knowledge_reference_claims (subject_type, subject_key);
CREATE INDEX idx_reference_claims_id ON knowledge_reference_claims (subject_type, subject_id);
CREATE INDEX idx_reference_claims_reference ON knowledge_reference_claims (reference_id);
"""

DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS knowledge_reference_claims;
DROP TABLE IF EXISTS knowledge_references;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
