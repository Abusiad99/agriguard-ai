"""
Domain entity: User. Framework-independent (no SQLAlchemy/Pydantic imports) per
NFR-MAINT-1 (Clean Architecture) — the domain layer must not depend on infrastructure.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID


class UserRole(str, Enum):
    FARMER = "farmer"
    AGRONOMIST = "agronomist"
    ADMIN = "admin"


class Locale(str, Enum):
    EN = "en"
    AR = "ar"


@dataclass
class User:
    id: Optional[UUID]
    email: str
    password_hash: str
    full_name: str
    role: UserRole
    is_active: bool = True
    preferred_locale: Locale = Locale.EN
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    def can_edit_knowledge_base(self) -> bool:
        """BR4: only agronomist or admin roles may edit the KB."""
        return self.role in (UserRole.AGRONOMIST, UserRole.ADMIN)

    def can_access_admin_panel(self) -> bool:
        """BR3: admin-only routes."""
        return self.role == UserRole.ADMIN
