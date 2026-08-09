"""
Repository interfaces (abstract base classes) — the domain layer's contract that
infrastructure implementations must satisfy (NFR-MAINT-2, Dependency Inversion,
mirroring the pattern already used for DeepShield's Firestore backend).

Application-layer services depend only on these interfaces, never on
SQLAlchemy/Postgres directly, so the persistence technology can be swapped (or
mocked in unit tests) without touching business logic.
"""
from __future__ import annotations

import abc
from datetime import date
from typing import List, Optional, Tuple
from uuid import UUID

from app.domain.entities.diagnosis import Diagnosis
from app.domain.entities.disease import Disease, Plant, Treatment
from app.domain.entities.user import User


class IUserRepository(abc.ABC):
    @abc.abstractmethod
    def create(self, user: User) -> User: ...

    @abc.abstractmethod
    def get_by_id(self, user_id: UUID) -> Optional[User]: ...

    @abc.abstractmethod
    def get_by_email(self, email: str) -> Optional[User]: ...

    @abc.abstractmethod
    def update(self, user: User) -> User: ...

    @abc.abstractmethod
    def list(self, role: Optional[str], is_active: Optional[bool], search: Optional[str],
              page: int, page_size: int) -> Tuple[List[User], int]: ...


class IRefreshTokenRepository(abc.ABC):
    @abc.abstractmethod
    def store(self, user_id: UUID, token_hash: str, expires_at) -> None: ...

    @abc.abstractmethod
    def is_valid(self, token_hash: str) -> Optional[UUID]:
        """Return the associated user_id if the token is valid & unrevoked, else None."""
        ...

    @abc.abstractmethod
    def revoke(self, token_hash: str) -> None: ...

    @abc.abstractmethod
    def revoke_all_for_user(self, user_id: UUID) -> None: ...


class IPlantRepository(abc.ABC):
    @abc.abstractmethod
    def get_by_canonical_name(self, canonical_name: str) -> Optional[Plant]: ...

    @abc.abstractmethod
    def get_or_create(self, canonical_name: str) -> Plant: ...

    @abc.abstractmethod
    def list(self) -> List[Plant]: ...


class IDiseaseRepository(abc.ABC):
    @abc.abstractmethod
    def get_current_by_plant_and_name(self, plant_id: UUID, name: str) -> Optional[Disease]: ...

    @abc.abstractmethod
    def get_by_id(self, disease_id: UUID) -> Optional[Disease]: ...

    @abc.abstractmethod
    def create_version(self, disease: Disease) -> Disease: ...

    @abc.abstractmethod
    def list(self, plant_id: Optional[UUID], search: Optional[str],
              page: int, page_size: int) -> Tuple[List[Disease], int]: ...


class ITreatmentRepository(abc.ABC):
    @abc.abstractmethod
    def get_current_for_disease(self, disease_id: UUID) -> List[Treatment]: ...

    @abc.abstractmethod
    def get_by_id(self, treatment_id: UUID) -> Optional[Treatment]: ...

    @abc.abstractmethod
    def create_version(self, treatment: Treatment) -> Treatment: ...


class IDiagnosisRepository(abc.ABC):
    @abc.abstractmethod
    def create(self, diagnosis: Diagnosis) -> Diagnosis: ...

    @abc.abstractmethod
    def get_by_id(self, diagnosis_id: UUID) -> Optional[Diagnosis]: ...

    @abc.abstractmethod
    def list_for_user(self, user_id: UUID, plant: Optional[str], disease: Optional[str],
                       date_from: Optional[date], date_to: Optional[date],
                       page: int, page_size: int) -> Tuple[List[Diagnosis], int]: ...

    @abc.abstractmethod
    def dashboard_summary(self, user_id: Optional[UUID]) -> dict:
        """user_id=None => system-wide summary (FR-ADMIN-4)."""
        ...

    @abc.abstractmethod
    def attach_report(self, diagnosis_id: UUID, file_ref: str, qr_code_ref: str):
        """Attach a Report record to an already-persisted diagnosis (BR5: reports are
        generated after the diagnosis exists, since the PDF embeds the diagnosis id)."""
        ...


class IAuditLogRepository(abc.ABC):
    @abc.abstractmethod
    def log(self, actor_user_id: Optional[UUID], action: str, entity_type: str,
             entity_id: Optional[UUID], metadata: dict) -> None: ...
