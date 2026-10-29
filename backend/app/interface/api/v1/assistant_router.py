"""Agricultural assistant (retrieval-augmented generation) routes."""
from __future__ import annotations

import math
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.application.services.assistant_service import AssistantService, ChatTurn
from app.core.exceptions import NotFoundError
from app.domain.entities.user import User
from app.interface.api.v1.dependencies import get_assistant_service, get_current_user, get_knowledge_document_repository

router = APIRouter(prefix="/assistant", tags=["Assistant"])


class ChatTurnSchema(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    language: Literal["en", "ar"] = "en"
    history: List[ChatTurnSchema] = Field(default_factory=list, max_length=20)
    diagnosis_id: Optional[UUID] = None
    plant_profile_id: Optional[UUID] = None


class SourceSchema(BaseModel):
    id: str
    document_id: str
    title: str
    organization: str
    url: Optional[str] = None
    source_type: str
    language: Optional[str] = None
    published_date: Optional[str] = None
    revised_date: Optional[str] = None
    section: Optional[str] = None
    excerpt: str
    score: Optional[float] = None


class ContextUsedSchema(BaseModel):
    diagnosis_id: Optional[str] = None
    plant_profile_id: Optional[str] = None
    model_result: List[str] = []
    user_observations: List[str] = []


class ChatResponse(BaseModel):
    mode: Literal["llm", "retrieval_only", "no_sources"]
    language: str
    answer: Optional[str] = None
    citations: List[str] = []
    sources: List[SourceSchema] = []
    evidence_sufficient: bool = False
    recommends_expert: bool = True
    notices: List[str] = []
    context_used: ContextUsedSchema


class KnowledgeDocumentSchema(BaseModel):
    id: str
    title: str
    organization: str
    source_url: Optional[str] = None
    source_type: str
    language: str
    published_date: Optional[str] = None
    revised_date: Optional[str] = None
    retrieved_at: Optional[str] = None
    crops: List[str] = []
    diseases: List[str] = []
    license_note: Optional[str] = None
    chunk_count: int = 0


class PaginatedDocumentsResponse(BaseModel):
    items: List[KnowledgeDocumentSchema]
    page: int
    page_size: int
    total: int
    total_pages: int


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, current_user: User = Depends(get_current_user),
               service: AssistantService = Depends(get_assistant_service)):
    # Retrieval and the LLM call are blocking; keep them off the event loop.
    result = await run_in_threadpool(
        service.chat, current_user.id, payload.message, payload.language,
        [ChatTurn(role=t.role, content=t.content) for t in payload.history],
        payload.diagnosis_id, payload.plant_profile_id,
    )
    return ChatResponse(**result)


def _doc_schema(d, chunk_count: int = 0) -> KnowledgeDocumentSchema:
    return KnowledgeDocumentSchema(
        id=str(d.id), title=d.title, organization=d.organization, source_url=d.source_url,
        source_type=d.source_type, language=d.language,
        published_date=d.published_date.isoformat() if d.published_date else None,
        revised_date=d.revised_date.isoformat() if d.revised_date else None,
        retrieved_at=d.retrieved_at.isoformat() if d.retrieved_at else None,
        crops=list(d.crops_json or []), diseases=list(d.diseases_json or []), license_note=d.license_note,
        chunk_count=chunk_count,
    )


@router.get("/sources", response_model=PaginatedDocumentsResponse)
def list_sources(page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100),
                 current_user: User = Depends(get_current_user),
                 repo=Depends(get_knowledge_document_repository)):
    """The documents the assistant can cite (active corpus), with provenance."""
    docs, total, counts = repo.list_documents(page, page_size)
    return PaginatedDocumentsResponse(items=[_doc_schema(d, counts.get(d.id, 0)) for d in docs], page=page,
                                      page_size=page_size, total=total,
                                      total_pages=max(1, math.ceil(total / page_size)))


@router.get("/sources/{document_id}", response_model=KnowledgeDocumentSchema)
def get_source(document_id: UUID, current_user: User = Depends(get_current_user),
               repo=Depends(get_knowledge_document_repository)):
    doc = repo.get_document(document_id)
    if doc is None or not doc.is_active:
        raise NotFoundError("Source not found.")
    return _doc_schema(doc, len(doc.chunks))
