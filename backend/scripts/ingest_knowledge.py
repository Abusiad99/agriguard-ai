#!/usr/bin/env python3
"""
Ingest trusted agricultural documents into the assistant's retrieval corpus.

Run from backend/ (uses the app's DATABASE_URL):

    python scripts/ingest_knowledge.py --manifest ../knowledge/manifest.json [--embed]
    python scripts/ingest_knowledge.py --sync-knowledge-base
    python scripts/ingest_knowledge.py --list
    python scripts/ingest_knowledge.py --deactivate <document-id>

Manifest (JSON) — every document MUST carry provenance; entries without a title,
organization, or allowed source_type are rejected:

    {"documents": [{
        "path": "sources/tomato_early_blight.html",    # relative to the manifest
        "title": "Early blight of tomato and potato",
        "organization": "<publishing institution>",
        "source_type": "university_extension",         # see SOURCE_TYPES
        "url": "https://...",                          # where it was obtained
        "language": "en",
        "published_date": "2021-05-01", "revised_date": null,
        "retrieved_at": "2026-10-29",
        "crops": ["tomato", "potato"], "diseases": ["early_blight"],
        "license_note": "Reproduced for internal retrieval under ..."
    }]}

The operator is responsible for obtaining documents from the stated organization
and for respecting their licence; this script never downloads or invents content.
Identical content (same SHA-256) is skipped. --embed adds Gemini embeddings when
GEMINI_API_KEY is configured; without it, retrieval is lexical (BM25) only.

--sync-knowledge-base indexes the admin-curated disease/treatment records already in
the database as documents of type "agriguard_knowledge_base" (organization
"AgriGuard knowledge base (curated by administrators)"), so the assistant can cite
them — labelled as internal curated records, not external publications.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.application.services.rag.text import chunk_text, clean_text, extract_text  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.infrastructure.db.session import SessionLocal  # noqa: E402
from app.infrastructure.repositories.knowledge_document_repository import (  # noqa: E402
    SOURCE_TYPES,
    DocumentMeta,
    SqlAlchemyKnowledgeDocumentRepository,
    content_hash,
)


def _date(value):
    return date.fromisoformat(value) if value else None


def _embed(chunks):
    from app.infrastructure.external.gemini_client import GeminiClient

    settings = get_settings()
    if not settings.gemini_enabled:
        print("  (embeddings skipped: GEMINI_API_KEY not configured)")
        return None, None
    client = GeminiClient()
    vectors = []
    for i in range(0, len(chunks), 50):
        batch = client.embed_texts([c.text for c in chunks[i:i + 50]], task_type="RETRIEVAL_DOCUMENT")
        if batch is None:
            print("  (embeddings failed; document indexed lexically only)")
            return None, None
        vectors.extend(batch)
    return vectors, settings.gemini_embedding_model


def ingest_manifest(repo, manifest_path: Path, embed: bool) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    added = 0
    for entry in manifest.get("documents", []):
        missing = [k for k in ("path", "title", "organization", "source_type") if not entry.get(k)]
        if missing or entry["source_type"] not in SOURCE_TYPES:
            print(f"REJECTED {entry.get('path')}: missing {missing} or invalid source_type")
            continue
        path = (manifest_path.parent / entry["path"]).resolve()
        if not path.is_file():
            print(f"REJECTED {entry['path']}: file not found")
            continue
        text = clean_text(extract_text(path))
        if len(text) < 200:
            print(f"REJECTED {entry['path']}: too little extractable text ({len(text)} chars)")
            continue
        chunks = chunk_text(text)
        vectors, model = _embed(chunks) if embed else (None, None)
        meta = DocumentMeta(
            title=entry["title"], organization=entry["organization"], source_type=entry["source_type"],
            source_url=entry.get("url"), language=entry.get("language", "en"),
            published_date=_date(entry.get("published_date")), revised_date=_date(entry.get("revised_date")),
            retrieved_at=datetime.fromisoformat(entry["retrieved_at"]).replace(tzinfo=timezone.utc)
            if entry.get("retrieved_at") else None,
            crops=tuple(entry.get("crops", [])), diseases=tuple(entry.get("diseases", [])),
            license_note=entry.get("license_note"),
        )
        doc, created = repo.add_document(meta, text, chunks, vectors, model)
        print(f"{'ADDED  ' if created else 'SKIPPED'} {doc.title} ({len(chunks)} chunks){'' if created else ' — identical content already indexed'}")
        added += int(created)
    return added


def sync_knowledge_base(db, repo, embed: bool) -> int:
    from sqlalchemy import select

    from app.infrastructure.db.models.knowledge_base_model import DiseaseModel, PlantModel, TreatmentModel

    retired = repo.deactivate_by_source_type("agriguard_knowledge_base")
    rows = db.execute(select(DiseaseModel, PlantModel).join(PlantModel)
                      .where(DiseaseModel.is_current.is_(True))).all()
    added = 0
    for disease, plant in rows:
        treatments = db.execute(select(TreatmentModel).where(TreatmentModel.disease_id == disease.id,
                                                             TreatmentModel.is_current.is_(True))).scalars().all()
        lines = [f"# {plant.canonical_name.replace('_', ' ').title()} — {disease.name}", disease.description]
        if disease.symptoms_json:
            lines.append("# Symptoms\n" + "\n".join(f"- {s}." for s in disease.symptoms_json))
        if disease.causes_json:
            lines.append("# Causes\n" + "\n".join(f"- {c}." for c in disease.causes_json))
        if disease.transmission_method:
            lines.append(f"# Transmission\n{disease.transmission_method}")
        for t in treatments:
            if t.category == "chemical" and not (t.source_citation or t.authority_referral_only):
                continue  # BR6: unverified chemical guidance is never indexed
            citation = f" (source: {t.source_citation})" if t.source_citation else ""
            lines.append(f"# {t.category.title()} management\n{t.instructions}{citation}")
        text = clean_text("\n\n".join(lines))
        existing = repo.find_by_hash(content_hash(text))
        if existing is not None:
            repo.set_active(existing.id, True)
            continue
        chunks = chunk_text(text)
        vectors, model = _embed(chunks) if embed else (None, None)
        repo.add_document(DocumentMeta(
            title=f"AgriGuard knowledge base: {plant.canonical_name.replace('_', ' ')} — {disease.name}",
            organization="AgriGuard knowledge base (curated by administrators)",
            source_type="agriguard_knowledge_base", language="en",
            crops=(plant.canonical_name,), diseases=(disease.name.lower().replace(" ", "_"),),
            license_note="Internal curated record; see per-treatment source citations.",
        ), text, chunks, vectors, model)
        added += 1
    print(f"Knowledge-base sync: {added} record(s) indexed ({retired} previous version(s) retired).")
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest")
    ap.add_argument("--embed", action="store_true")
    ap.add_argument("--sync-knowledge-base", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--deactivate")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        repo = SqlAlchemyKnowledgeDocumentRepository(db)
        if args.manifest:
            ingest_manifest(repo, Path(args.manifest).resolve(), args.embed)
        if args.sync_knowledge_base:
            sync_knowledge_base(db, repo, args.embed)
        if args.deactivate:
            from uuid import UUID
            print("deactivated" if repo.set_active(UUID(args.deactivate), False) else "not found")
        if args.list or not (args.manifest or args.sync_knowledge_base or args.deactivate):
            docs, total, counts = repo.list_documents(1, 500, active_only=False)
            print(f"{total} document(s):")
            for d in docs:
                print(f"  [{'active' if d.is_active else 'inactive'}] {d.id}  {d.title}  — {d.organization} "
                      f"({d.source_type}, {counts.get(d.id, 0)} chunks)")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
