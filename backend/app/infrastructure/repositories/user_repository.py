"""SQLAlchemy implementation of IUserRepository."""
from __future__ import annotations

from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.entities.user import Locale, User, UserRole
from app.domain.repositories.interfaces import IUserRepository
from app.infrastructure.db.models.user_model import UserModel


def _to_entity(m: UserModel) -> User:
    return User(
        id=m.id, email=m.email, password_hash=m.password_hash, full_name=m.full_name,
        role=UserRole(m.role), is_active=m.is_active, preferred_locale=Locale(m.preferred_locale),
        created_at=m.created_at, updated_at=m.updated_at,
    )


class SqlAlchemyUserRepository(IUserRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, user: User) -> User:
        model = UserModel(
            email=user.email, password_hash=user.password_hash, full_name=user.full_name,
            role=user.role.value, is_active=user.is_active, preferred_locale=user.preferred_locale.value,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return _to_entity(model)

    def get_by_id(self, user_id: UUID) -> Optional[User]:
        model = self.db.get(UserModel, user_id)
        return _to_entity(model) if model else None

    def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(UserModel).where(func.lower(UserModel.email) == email.lower())
        model = self.db.execute(stmt).scalar_one_or_none()
        return _to_entity(model) if model else None

    def update(self, user: User) -> User:
        model = self.db.get(UserModel, user.id)
        if model is None:
            raise ValueError(f"User {user.id} not found")
        model.full_name = user.full_name
        model.role = user.role.value
        model.is_active = user.is_active
        model.preferred_locale = user.preferred_locale.value
        model.password_hash = user.password_hash
        self.db.commit()
        self.db.refresh(model)
        return _to_entity(model)

    def list(self, role: Optional[str], is_active: Optional[bool], search: Optional[str],
              page: int, page_size: int) -> Tuple[List[User], int]:
        stmt = select(UserModel)
        if role:
            stmt = stmt.where(UserModel.role == role)
        if is_active is not None:
            stmt = stmt.where(UserModel.is_active == is_active)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(UserModel.email.ilike(like), UserModel.full_name.ilike(like)))

        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        stmt = stmt.order_by(UserModel.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        models = self.db.execute(stmt).scalars().all()
        return [_to_entity(m) for m in models], total
