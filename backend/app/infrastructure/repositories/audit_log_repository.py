"""SQLAlchemy implementation of IAuditLogRepository (UC-11 admin action trail,
UC-09/10 knowledge-base edit trail)."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.repositories.interfaces import IAuditLogRepository
from app.infrastructure.db.models.diagnosis_model import AuditLogModel


class SqlAlchemyAuditLogRepository(IAuditLogRepository):
    def __init__(self, db: Session):
        self.db = db

    def log(self, actor_user_id: Optional[UUID], action: str, entity_type: str,
             entity_id: Optional[UUID], metadata: dict) -> None:
        model = AuditLogModel(
            actor_user_id=actor_user_id, action=action, entity_type=entity_type,
            entity_id=entity_id, metadata_json=metadata or {},
        )
        self.db.add(model)
        self.db.commit()
