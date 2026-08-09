"""SQLAlchemy implementation of IRefreshTokenRepository."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.repositories.interfaces import IRefreshTokenRepository
from app.infrastructure.db.models.user_model import RefreshTokenModel


class SqlAlchemyRefreshTokenRepository(IRefreshTokenRepository):
    def __init__(self, db: Session):
        self.db = db

    def store(self, user_id: UUID, token_hash: str, expires_at: datetime) -> None:
        model = RefreshTokenModel(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.db.add(model)
        self.db.commit()

    def is_valid(self, token_hash: str) -> Optional[UUID]:
        stmt = select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        model = self.db.execute(stmt).scalar_one_or_none()
        if model is None or model.revoked:
            return None
        expires_at = model.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            return None
        return model.user_id

    def revoke(self, token_hash: str) -> None:
        stmt = select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        model = self.db.execute(stmt).scalar_one_or_none()
        if model:
            model.revoked = True
            self.db.commit()

    def revoke_all_for_user(self, user_id: UUID) -> None:
        stmt = select(RefreshTokenModel).where(RefreshTokenModel.user_id == user_id, RefreshTokenModel.revoked == False)  # noqa: E712
        for model in self.db.execute(stmt).scalars().all():
            model.revoked = True
        self.db.commit()
