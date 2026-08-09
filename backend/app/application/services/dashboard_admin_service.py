"""
DashboardService (FR-DASH-1..3, UC-08) and AdminService (FR-ADMIN-1/4, UC-11, UC-12).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.domain.entities.user import User, UserRole
from app.domain.repositories.interfaces import IDiagnosisRepository, IUserRepository


class DashboardService:
    def __init__(self, diagnosis_repo: IDiagnosisRepository):
        self.diagnosis_repo = diagnosis_repo

    def get_my_dashboard(self, user_id: UUID) -> dict:
        return self.diagnosis_repo.dashboard_summary(user_id=user_id)

    def get_system_dashboard(self, actor: User) -> dict:
        if actor.role not in (UserRole.ADMIN, UserRole.AGRONOMIST):
            raise AuthorizationError("Only admins and agronomists may view system-wide analytics.")
        return self.diagnosis_repo.dashboard_summary(user_id=None)


class AdminService:
    def __init__(self, user_repo: IUserRepository, audit_repo=None):
        self.user_repo = user_repo
        self.audit_repo = audit_repo

    def list_users(self, actor: User, role: Optional[str], is_active: Optional[bool],
                    search: Optional[str], page: int, page_size: int):
        self._require_admin(actor)
        return self.user_repo.list(role, is_active, search, page, page_size)

    def update_user(self, actor: User, target_user_id: UUID, new_role: Optional[str],
                     new_is_active: Optional[bool]) -> User:
        self._require_admin(actor)

        if target_user_id == actor.id and (new_role is not None or new_is_active is False):
            raise ValidationError("An admin cannot modify their own role or deactivate their own account.")

        target = self.user_repo.get_by_id(target_user_id)
        if target is None:
            raise NotFoundError("User not found.")

        if new_role is not None:
            target.role = UserRole(new_role)
        if new_is_active is not None:
            target.is_active = new_is_active

        updated = self.user_repo.update(target)
        if self.audit_repo:
            self.audit_repo.log(actor.id, "update_user", "user", target_user_id,
                                 {"new_role": new_role, "new_is_active": new_is_active})
        return updated

    def _require_admin(self, actor: User) -> None:
        if not actor.can_access_admin_panel():
            raise AuthorizationError("Admin role required.")
