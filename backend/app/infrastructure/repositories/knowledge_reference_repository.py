"""Persistence for knowledge-base references and claims (migration 0008)."""
from __future__ import annotations

from typing import Iterable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.infrastructure.db.models.knowledge_reference_model import KnowledgeReferenceClaimModel, KnowledgeReferenceModel


class SqlAlchemyKnowledgeReferenceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, reference_id: UUID) -> Optional[KnowledgeReferenceModel]:
        return self.db.execute(select(KnowledgeReferenceModel).options(selectinload(KnowledgeReferenceModel.claims))
                               .where(KnowledgeReferenceModel.id == reference_id)).scalar_one_or_none()

    def by_url(self, url: str) -> Optional[KnowledgeReferenceModel]:
        return self.db.execute(select(KnowledgeReferenceModel).where(KnowledgeReferenceModel.url == url)).scalar_one_or_none()

    def list(self, q: Optional[str], subject_type: Optional[str], subject_key: Optional[str], subject_id: Optional[UUID],
             include_inactive: bool, page: int, page_size: int) -> Tuple[List[KnowledgeReferenceModel], int]:
        stmt = select(KnowledgeReferenceModel).options(selectinload(KnowledgeReferenceModel.claims))
        if not include_inactive:
            stmt = stmt.where(KnowledgeReferenceModel.is_active.is_(True))
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(or_(func.lower(KnowledgeReferenceModel.title).like(like),
                                  func.lower(KnowledgeReferenceModel.organization).like(like),
                                  func.lower(KnowledgeReferenceModel.authors).like(like)))
        if subject_type or subject_key or subject_id:
            claim = select(KnowledgeReferenceClaimModel.reference_id)
            if subject_type:
                claim = claim.where(KnowledgeReferenceClaimModel.subject_type == subject_type)
            if subject_key:
                claim = claim.where(KnowledgeReferenceClaimModel.subject_key == subject_key)
            if subject_id:
                claim = claim.where(KnowledgeReferenceClaimModel.subject_id == subject_id)
            stmt = stmt.where(KnowledgeReferenceModel.id.in_(claim))
        total = self.db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
        rows = self.db.execute(stmt.order_by(KnowledgeReferenceModel.created_at.desc())
                               .offset((page - 1) * page_size).limit(page_size)).scalars().all()
        return list(rows), int(total)

    def claims_for(self, subjects: Iterable[Tuple[str, Optional[str], Optional[UUID]]]) -> List[KnowledgeReferenceClaimModel]:
        """Claims of active references for any of the given (type, key, id) subjects."""
        conditions = []
        for subject_type, key, sid in subjects:
            if key:
                conditions.append((KnowledgeReferenceClaimModel.subject_type == subject_type)
                                  & (KnowledgeReferenceClaimModel.subject_key == key))
            if sid:
                conditions.append((KnowledgeReferenceClaimModel.subject_type == subject_type)
                                  & (KnowledgeReferenceClaimModel.subject_id == sid))
        if not conditions:
            return []
        stmt = (select(KnowledgeReferenceClaimModel).options(selectinload(KnowledgeReferenceClaimModel.reference))
                .join(KnowledgeReferenceModel).where(KnowledgeReferenceModel.is_active.is_(True)).where(or_(*conditions))
                .order_by(KnowledgeReferenceClaimModel.created_at))
        return list(self.db.execute(stmt).scalars().all())

    def get_claim(self, reference_id: UUID, claim_id: UUID) -> Optional[KnowledgeReferenceClaimModel]:
        return self.db.execute(select(KnowledgeReferenceClaimModel).where(KnowledgeReferenceClaimModel.id == claim_id)
                               .where(KnowledgeReferenceClaimModel.reference_id == reference_id)).scalar_one_or_none()

    def add(self, row):
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def save(self, row):
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, row) -> None:
        self.db.delete(row)
        self.db.commit()
