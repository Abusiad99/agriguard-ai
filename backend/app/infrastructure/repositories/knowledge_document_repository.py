"""Repository for the assistant's retrieval corpus (kb_documents / kb_chunks) and
per-user assistant usage accounting."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.services.rag.retrieval import IndexedChunk
from app.application.services.rag.text import Chunk
from app.infrastructure.db.models.knowledge_document_model import AssistantUsageModel, KbChunkModel, KbDocumentModel

SOURCE_TYPES = ("government", "university_extension", "research_institution", "pathology_society",
                "pesticide_label", "regulatory", "agriguard_knowledge_base", "other")


@dataclass
class DocumentMeta:
    title: str
    organization: str
    source_type: str
    source_url: Optional[str] = None
    language: str = "en"
    published_date: Optional[date] = None
    revised_date: Optional[date] = None
    retrieved_at: Optional[datetime] = None
    crops: Tuple[str, ...] = ()
    diseases: Tuple[str, ...] = ()
    license_note: Optional[str] = None


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SqlAlchemyKnowledgeDocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    # --- ingestion ---------------------------------------------------------
    def find_by_hash(self, sha: str) -> Optional[KbDocumentModel]:
        return self.db.execute(select(KbDocumentModel).where(KbDocumentModel.content_sha256 == sha)).scalar_one_or_none()

    def add_document(self, meta: DocumentMeta, full_text: str, chunks: List[Chunk],
                     embeddings: Optional[List[List[float]]] = None, embedding_model: Optional[str] = None,
                     created_by: Optional[UUID] = None) -> Tuple[KbDocumentModel, bool]:
        if meta.source_type not in SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {SOURCE_TYPES}")
        sha = content_hash(full_text)
        existing = self.find_by_hash(sha)
        if existing is not None:
            return existing, False
        doc = KbDocumentModel(
            title=meta.title[:300], organization=meta.organization[:200], source_url=meta.source_url,
            source_type=meta.source_type, language=meta.language[:5], published_date=meta.published_date,
            revised_date=meta.revised_date, retrieved_at=meta.retrieved_at,
            crops_json=[c.lower() for c in meta.crops], diseases_json=[d.lower() for d in meta.diseases],
            license_note=meta.license_note, content_sha256=sha, created_by=created_by,
        )
        self.db.add(doc)
        self.db.flush()
        for i, ch in enumerate(chunks):
            self.db.add(KbChunkModel(
                document_id=doc.id, chunk_index=ch.index, section=ch.section, text=ch.text,
                token_count=len(ch.text.split()),
                embedding_json=embeddings[i] if embeddings and i < len(embeddings) else None,
                embedding_model=embedding_model if embeddings else None,
            ))
        self.db.commit()
        self.db.refresh(doc)
        return doc, True

    def deactivate_by_source_type(self, source_type: str) -> int:
        docs = self.db.execute(select(KbDocumentModel).where(KbDocumentModel.source_type == source_type,
                                                             KbDocumentModel.is_active.is_(True))).scalars().all()
        for d in docs:
            d.is_active = False
        self.db.commit()
        return len(docs)

    def set_active(self, document_id: UUID, active: bool) -> bool:
        doc = self.db.get(KbDocumentModel, document_id)
        if doc is None:
            return False
        doc.is_active = active
        self.db.commit()
        return True

    # --- retrieval ---------------------------------------------------------
    def index_signature(self) -> tuple:
        n_docs, last = self.db.execute(
            select(func.count(KbDocumentModel.id), func.max(KbDocumentModel.created_at))
            .where(KbDocumentModel.is_active.is_(True))).one()
        n_chunks = self.db.execute(
            select(func.count(KbChunkModel.id)).join(KbDocumentModel)
            .where(KbDocumentModel.is_active.is_(True))).scalar_one()
        return int(n_docs or 0), int(n_chunks or 0), str(last)

    def load_index_chunks(self) -> List[IndexedChunk]:
        rows = self.db.execute(
            select(KbChunkModel, KbDocumentModel).join(KbDocumentModel)
            .where(KbDocumentModel.is_active.is_(True))
            .order_by(KbDocumentModel.created_at, KbChunkModel.chunk_index)
        ).all()
        out = []
        for ch, doc in rows:
            out.append(IndexedChunk(
                chunk_id=str(ch.id), document_id=str(doc.id), text=ch.text, section=ch.section, title=doc.title,
                organization=doc.organization, source_url=doc.source_url, source_type=doc.source_type,
                language=doc.language,
                published_date=doc.published_date.isoformat() if doc.published_date else None,
                revised_date=doc.revised_date.isoformat() if doc.revised_date else None,
                crops=list(doc.crops_json or []), diseases=list(doc.diseases_json or []),
                embedding=ch.embedding_json, embedding_model=ch.embedding_model,
            ))
        return out

    def list_documents(self, page: int = 1, page_size: int = 50, active_only: bool = True):
        stmt = select(KbDocumentModel)
        if active_only:
            stmt = stmt.where(KbDocumentModel.is_active.is_(True))
        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        docs = self.db.execute(stmt.order_by(KbDocumentModel.title).offset((page - 1) * page_size)
                               .limit(page_size)).scalars().all()
        counts = dict(self.db.execute(
            select(KbChunkModel.document_id, func.count(KbChunkModel.id)).group_by(KbChunkModel.document_id)).all())
        return docs, total, counts

    def get_document(self, document_id: UUID) -> Optional[KbDocumentModel]:
        return self.db.get(KbDocumentModel, document_id)

    # --- usage accounting --------------------------------------------------
    def record_usage(self, user_id: UUID, mode: str, llm_called: bool, retrieved: int, input_chars: int,
                     output_chars: int) -> None:
        self.db.add(AssistantUsageModel(user_id=user_id, mode=mode, llm_called=llm_called,
                                        retrieved_chunks=retrieved, input_chars=input_chars,
                                        output_chars=output_chars))
        self.db.commit()

    def llm_calls_since(self, user_id: UUID, hours: int = 24) -> int:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        return int(self.db.execute(
            select(func.count(AssistantUsageModel.id)).where(
                AssistantUsageModel.user_id == user_id, AssistantUsageModel.llm_called.is_(True),
                AssistantUsageModel.created_at >= since)).scalar_one())
