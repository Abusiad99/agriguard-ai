"""Knowledge-base references: structured sources an agronomist attaches to diseases,
treatments, rules, guidance or methods, with the claim each one supports.

Rules:
- a reference needs a title, an http(s) URL and a source type; the URL is unique;
- a claim states what the source supports, in the words of the person who read it;
- disease claims attach to "<plant>/<disease name>" (survives knowledge-base versions);
  treatment claims attach to one treatment version (a revised treatment needs its
  source checked again);
- references are deactivated, never deleted, so stored reports stay traceable;
- every change is written to the audit log.
"""
from __future__ import annotations

import re
from datetime import date
from typing import List, Optional
from uuid import UUID

from app.application.reporting.references import SOURCE_TYPES, SUBJECT_TYPES, load_catalog
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.entities.user import User
from app.infrastructure.db.models.knowledge_reference_model import KnowledgeReferenceClaimModel, KnowledgeReferenceModel

_KEY = re.compile(r"^[a-z0-9_./:\-]{1,200}$")
_FIELDS = ("title", "authors", "organization", "url", "doi", "publication_date", "source_type", "language", "notes",
           "verified_on")
_LIMITS = {"title": 500, "authors": 500, "organization": 300, "url": 1000, "doi": 200, "publication_date": 60,
           "language": 8, "notes": 4000}


def disease_key(plant: Optional[str], disease: Optional[str]) -> Optional[str]:
    if not plant or not disease:
        return None
    return f"{plant.strip().lower()}/{disease.strip().lower()}"


def reference_to_dict(row: KnowledgeReferenceModel) -> dict:
    return {"id": str(row.id), "title": row.title, "authors": row.authors, "organization": row.organization,
            "url": row.url, "doi": row.doi, "publication_date": row.publication_date, "source_type": row.source_type,
            "language": row.language, "notes": row.notes,
            "verified_on": row.verified_on.isoformat() if row.verified_on else None,
            "is_active": row.is_active,
            "claims": [{"id": str(c.id), "subject_type": c.subject_type, "subject_key": c.subject_key,
                        "subject_id": str(c.subject_id) if c.subject_id else None, "claim": c.claim} for c in row.claims]}


class ReferenceService:
    def __init__(self, repo, plant_repo, disease_repo, treatment_repo, audit_repo):
        self.repo, self.plant_repo, self.disease_repo = repo, plant_repo, disease_repo
        self.treatment_repo, self.audit_repo = treatment_repo, audit_repo

    # ------------------------------------------------------------------ references
    def list(self, **filters):
        return self.repo.list(**filters)

    def get(self, reference_id: UUID) -> KnowledgeReferenceModel:
        row = self.repo.get(reference_id)
        if row is None:
            raise NotFoundError("Reference not found.")
        return row

    @staticmethod
    def catalog() -> dict:
        return load_catalog()

    def _clean(self, data: dict, partial: bool) -> dict:
        out = {}
        for field in _FIELDS:
            if field not in data:
                continue
            value = data[field]
            if isinstance(value, str):
                value = value.strip() or None
            if field in _LIMITS and value is not None and len(str(value)) > _LIMITS[field]:
                raise ValidationError(f"{field} is too long (max {_LIMITS[field]}).")
            out[field] = value
        if not partial:
            for field in ("title", "url", "source_type"):
                if not out.get(field):
                    raise ValidationError(f"{field} is required.")
        if "url" in out and out["url"] is not None and not re.match(r"^https?://[^\s]+$", out["url"]):
            raise ValidationError("url must start with http:// or https:// and contain no spaces.")
        if "source_type" in out and out["source_type"] not in SOURCE_TYPES:
            raise ValidationError(f"source_type must be one of {', '.join(SOURCE_TYPES)}.")
        if out.get("verified_on") and not isinstance(out["verified_on"], date):
            try:
                out["verified_on"] = date.fromisoformat(str(out["verified_on"]))
            except ValueError:
                raise ValidationError("verified_on must be YYYY-MM-DD.")
        if out.get("verified_on") and out["verified_on"] > date.today():
            raise ValidationError("verified_on cannot be in the future.")
        return out

    def create(self, actor: User, data: dict) -> KnowledgeReferenceModel:
        values = self._clean(data, partial=False)
        if self.repo.by_url(values["url"]) is not None:
            raise ConflictError("A reference with this URL already exists.")
        row = KnowledgeReferenceModel(**values, language=values.get("language") or "en", created_by=actor.id,
                                      verified_by=actor.id if values.get("verified_on") else None)
        row = self.repo.add(row)
        self.audit_repo.log(actor.id, "create_reference", "knowledge_reference", row.id, {"url": row.url})
        return row

    def update(self, actor: User, reference_id: UUID, data: dict) -> KnowledgeReferenceModel:
        row = self.get(reference_id)
        values = self._clean(data, partial=True)
        if values.get("url") and values["url"] != row.url:
            other = self.repo.by_url(values["url"])
            if other is not None and other.id != row.id:
                raise ConflictError("A reference with this URL already exists.")
        for field in ("title", "url", "source_type"):
            if field in values and not values[field]:
                raise ValidationError(f"{field} cannot be empty.")
        for key, value in values.items():
            setattr(row, key, value)
        if "verified_on" in values:
            row.verified_by = actor.id if values["verified_on"] else None
        if "is_active" in data:
            row.is_active = bool(data["is_active"])
        row = self.repo.save(row)
        self.audit_repo.log(actor.id, "update_reference", "knowledge_reference", row.id, {"fields": sorted(values)})
        return row

    def deactivate(self, actor: User, reference_id: UUID) -> KnowledgeReferenceModel:
        row = self.get(reference_id)
        row.is_active = False
        row = self.repo.save(row)
        self.audit_repo.log(actor.id, "deactivate_reference", "knowledge_reference", row.id, {})
        return row

    # ---------------------------------------------------------------------- claims
    def add_claim(self, actor: User, reference_id: UUID, subject_type: str, claim: str,
                  subject_key: Optional[str] = None, subject_id: Optional[str] = None) -> KnowledgeReferenceClaimModel:
        row = self.get(reference_id)
        if subject_type not in SUBJECT_TYPES:
            raise ValidationError(f"subject_type must be one of {', '.join(SUBJECT_TYPES)}.")
        claim = (claim or "").strip()
        if not claim or len(claim) > 1000:
            raise ValidationError("claim is required (at most 1000 characters): say what this source supports.")
        key, sid = None, None
        if subject_type == "disease":
            plant, _, name = (subject_key or "").strip().lower().partition("/")
            plant_row = self.plant_repo.get_by_canonical_name(plant) if plant else None
            disease = self.disease_repo.get_current_by_plant_and_name(plant_row.id, name) if plant_row and name else None
            if disease is None:
                raise ValidationError("subject_key must be '<plant>/<disease name>' of a disease in the knowledge base.")
            key = disease_key(plant, name)
        elif subject_type == "treatment":
            try:
                sid = UUID(str(subject_id))
            except (TypeError, ValueError):
                raise ValidationError("subject_id must be the id of a treatment.")
            if self.treatment_repo.get_by_id(sid) is None:
                raise ValidationError("subject_id must be the id of a treatment in the knowledge base.")
        else:
            key = (subject_key or "").strip().lower()
            if not _KEY.match(key):
                raise ValidationError("subject_key must be 1-200 characters: lowercase letters, digits and _ . / : -")
        model = KnowledgeReferenceClaimModel(reference_id=row.id, subject_type=subject_type, subject_key=key,
                                             subject_id=sid, claim=claim, created_by=actor.id)
        model = self.repo.add(model)
        self.audit_repo.log(actor.id, "add_reference_claim", "knowledge_reference", row.id,
                            {"claim_id": str(model.id), "subject_type": subject_type, "subject": key or str(sid)})
        return model

    def remove_claim(self, actor: User, reference_id: UUID, claim_id: UUID) -> None:
        claim = self.repo.get_claim(reference_id, claim_id)
        if claim is None:
            raise NotFoundError("Claim not found.")
        self.repo.delete(claim)
        self.audit_repo.log(actor.id, "remove_reference_claim", "knowledge_reference", reference_id, {"claim_id": str(claim_id)})

    # ------------------------------------------------------------------ for reports
    def for_report(self, disease: Optional[dict], treatment_ids: List[str]) -> List[dict]:
        """References (with their claims) attached to a knowledge-base disease and its
        treatments, in the shape reporting.references.Citations expects."""
        subjects = []
        key = disease_key((disease or {}).get("plant"), (disease or {}).get("name"))
        if key:
            subjects.append(("disease", key, None))
        for tid in treatment_ids:
            subjects.append(("treatment", None, UUID(tid)))
        refs = {}
        for claim in self.repo.claims_for(subjects):
            ref = claim.reference
            entry = refs.setdefault(str(ref.id), {"id": str(ref.id), "title": ref.title, "authors": ref.authors,
                                                  "organization": ref.organization, "url": ref.url, "doi": ref.doi,
                                                  "publication_date": ref.publication_date, "source_type": ref.source_type,
                                                  "language": ref.language,
                                                  "verified_on": ref.verified_on.isoformat() if ref.verified_on else None,
                                                  "claims": []})
            subject = f"disease:{claim.subject_key}" if claim.subject_type == "disease" else f"treatment:{claim.subject_id}"
            entry["claims"].append({"subject": subject, "claim": claim.claim})
        return list(refs.values())
