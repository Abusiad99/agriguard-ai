"""References behind report statements.

Two sources, never mixed up:
- the built-in catalog (configs/reports/references.json): verified sources for the claims
  AgriGuard's own rules make (methods, monitoring, spraying conditions, general prevention);
- knowledge-base references (tables knowledge_references / knowledge_reference_claims,
  migration 0008): sources an agronomist attached to a disease or a treatment.

A report cites a reference only through a *claim*: a short statement of what that source
supports. `Citations` collects the claims a report actually uses and numbers the
references in order of first use. Nothing here generates a reference; an LLM is never a
source.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Dict, Iterable, List, Optional

from app.application.reporting.i18n import t
from app.core.config import CONFIGS_DIR

CATALOG_PATH = CONFIGS_DIR / "reports" / "references.json"
SOURCE_TYPES = ("agricultural_authority", "university_extension", "research_institute", "peer_reviewed",
                "international_organization", "educational_resource", "other")
SUBJECT_TYPES = ("disease", "treatment", "rule", "guidance", "method")


class CatalogError(ValueError):
    pass


def validate_catalog(data: dict) -> List[str]:
    problems, ids, urls = [], set(), set()
    for ref in data.get("references", []):
        rid = ref.get("id")
        if not rid or rid in ids:
            problems.append(f"missing or duplicate id {rid!r}")
        ids.add(rid)
        for field in ("title", "url", "organization", "source_type", "verified_on"):
            if not ref.get(field):
                problems.append(f"{rid}: {field} is required")
        if not str(ref.get("url", "")).startswith("https://"):
            problems.append(f"{rid}: url must be https")
        if ref.get("url") in urls:
            problems.append(f"{rid}: duplicate url")
        urls.add(ref.get("url"))
        if ref.get("source_type") not in SOURCE_TYPES:
            problems.append(f"{rid}: unknown source_type {ref.get('source_type')!r}")
        if not ref.get("claims"):
            problems.append(f"{rid}: no claims")
        for claim in ref.get("claims", []):
            subject = str(claim.get("subject", ""))
            if subject.split(":", 1)[0] not in SUBJECT_TYPES or ":" not in subject:
                problems.append(f"{rid}: claim subject {subject!r} must be '<type>:<key>'")
            if not claim.get("en") or not claim.get("ar"):
                problems.append(f"{rid}: claim {subject} needs English and Arabic text")
    return problems


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    problems = validate_catalog(data)
    if problems:
        raise CatalogError("; ".join(problems))
    return data


def catalog_version() -> str:
    return load_catalog().get("catalog_version", "references")


def _public_fields(ref: dict) -> dict:
    return {k: ref.get(k) for k in ("title", "authors", "organization", "url", "doi", "publication_date",
                                    "source_type", "language", "verified_on")}


class Citations:
    """The references one report cites, numbered in order of first use."""

    def __init__(self, locale: str, kb_references: Optional[Iterable[dict]] = None):
        self.locale = locale
        self._entries: Dict[str, dict] = {}
        self._catalog = load_catalog()["references"]
        # Knowledge-base references: {"id", fields..., "claims": [{"subject", "claim"}]}
        self._kb = list(kb_references or [])

    def _add(self, ref_id: str, fields: dict, origin: str, claim_text: str) -> str:
        entry = self._entries.get(ref_id)
        if entry is None:
            entry = {"id": ref_id, "n": len(self._entries) + 1, "origin": origin, **fields,
                     "source_type_label": t(self.locale, f"refsrc.{fields.get('source_type') or 'other'}"),
                     "claims": []}
            self._entries[ref_id] = entry
        if claim_text and claim_text not in entry["claims"]:
            entry["claims"].append(claim_text)
        return ref_id

    def cite(self, subject: str) -> List[str]:
        """Catalog references supporting `subject` (e.g. "guidance:scouting"). Empty when
        nothing in the catalog supports it, so callers fall back to "general guidance"."""
        out = []
        for ref in self._catalog:
            for claim in ref["claims"]:
                if claim["subject"] == subject:
                    out.append(self._add(ref["id"], _public_fields(ref), "catalog",
                                         claim.get(self.locale) or claim["en"]))
        return out

    def cite_kb(self, subject: str) -> List[str]:
        """Knowledge-base references attached to `subject` ("disease:<plant>/<name>" or
        "treatment:<uuid>"). Their claims are shown as entered, in the language entered."""
        out = []
        for ref in self._kb:
            for claim in ref.get("claims", []):
                if claim.get("subject") == subject:
                    out.append(self._add(f"kb-{ref['id']}", _public_fields(ref), "knowledge_base", claim.get("claim", "")))
        return out

    def ids(self) -> set:
        return set(self._entries)

    def to_list(self) -> List[dict]:
        return sorted(self._entries.values(), key=lambda e: e["n"])


def number_map(references: List[dict]) -> Dict[str, int]:
    return {r["id"]: r["n"] for r in references}
