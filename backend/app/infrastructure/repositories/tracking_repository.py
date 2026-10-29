"""SQLAlchemy repositories for plant profiles and observation notes.

Ownership is enforced at the query level: every read that takes a user id filters by
owner, so a handler cannot accidentally return another user's records by passing a
foreign id (insecure direct object reference). Observation notes are append-only —
there is deliberately no update or delete method.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.domain.entities.tracking import ObservationNote, PlantProfile
from app.infrastructure.db.models.diagnosis_model import DiagnosisModel
from app.infrastructure.db.models.tracking_model import ObservationNoteModel, PlantProfileModel

_EDITABLE_FIELDS = ("name", "crop_type", "variety", "planting_date", "location_label",
                    "growing_environment", "notes")


def _profile_entity(m: PlantProfileModel, count: int = 0, last_at=None, last_status=None,
                    last_label=None) -> PlantProfile:
    return PlantProfile(
        id=m.id, owner_user_id=m.owner_user_id, name=m.name, crop_type=m.crop_type, variety=m.variety,
        planting_date=m.planting_date, location_label=m.location_label,
        growing_environment=m.growing_environment, notes=m.notes, archived_at=m.archived_at,
        created_at=m.created_at, updated_at=m.updated_at, observation_count=int(count or 0),
        last_observed_at=last_at, last_decision_status=last_status, last_predicted_label=last_label,
    )


def _note_entity(m: ObservationNoteModel) -> ObservationNote:
    return ObservationNote(id=m.id, diagnosis_id=m.diagnosis_id, author_user_id=m.author_user_id,
                           note_type=m.note_type, body=m.body, data=m.data_json or {}, created_at=m.created_at)


class SqlAlchemyPlantProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, profile: PlantProfile) -> PlantProfile:
        model = PlantProfileModel(
            owner_user_id=profile.owner_user_id, name=profile.name, crop_type=profile.crop_type,
            variety=profile.variety, planting_date=profile.planting_date, location_label=profile.location_label,
            growing_environment=profile.growing_environment, notes=profile.notes,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return _profile_entity(model)

    def get_owned(self, profile_id: UUID, owner_user_id: UUID) -> Optional[PlantProfile]:
        model = self.db.execute(
            select(PlantProfileModel).where(PlantProfileModel.id == profile_id,
                                            PlantProfileModel.owner_user_id == owner_user_id)
        ).scalar_one_or_none()
        return self._with_stats(model) if model else None

    def get_any(self, profile_id: UUID) -> Optional[PlantProfile]:
        """Unscoped lookup — only for admin read access, checked by the caller."""
        model = self.db.get(PlantProfileModel, profile_id)
        return self._with_stats(model) if model else None

    def _with_stats(self, model: PlantProfileModel) -> PlantProfile:
        count, last_at = self.db.execute(
            select(func.count(DiagnosisModel.id), func.max(DiagnosisModel.diagnosed_at))
            .where(DiagnosisModel.plant_profile_id == model.id)
        ).one()
        last = self.db.execute(
            select(DiagnosisModel.decision_status, DiagnosisModel.predicted_label)
            .where(DiagnosisModel.plant_profile_id == model.id)
            .order_by(DiagnosisModel.diagnosed_at.desc()).limit(1)
        ).first()
        return _profile_entity(model, count, last_at, last[0] if last else None, last[1] if last else None)

    def list_for_owner(self, owner_user_id: UUID, search: Optional[str] = None, include_archived: bool = False,
                       last_status: Optional[str] = None, page: int = 1,
                       page_size: int = 20) -> Tuple[List[PlantProfile], int]:
        stats = (
            select(DiagnosisModel.plant_profile_id.label("pid"),
                   func.count(DiagnosisModel.id).label("cnt"),
                   func.max(DiagnosisModel.diagnosed_at).label("last_at"))
            .where(DiagnosisModel.plant_profile_id.isnot(None))
            .group_by(DiagnosisModel.plant_profile_id)
            .subquery()
        )
        stmt = (
            select(PlantProfileModel, stats.c.cnt, stats.c.last_at)
            .outerjoin(stats, stats.c.pid == PlantProfileModel.id)
            .where(PlantProfileModel.owner_user_id == owner_user_id)
        )
        if not include_archived:
            stmt = stmt.where(PlantProfileModel.archived_at.is_(None))
        if search:
            term = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            stmt = stmt.where(PlantProfileModel.name.ilike(term, escape="\\")
                              | PlantProfileModel.crop_type.ilike(term, escape="\\"))
        if last_status:
            latest = (
                select(DiagnosisModel.plant_profile_id.label("pid"), DiagnosisModel.decision_status.label("st"))
                .join(stats, and_(stats.c.pid == DiagnosisModel.plant_profile_id,
                                  stats.c.last_at == DiagnosisModel.diagnosed_at))
                .subquery()
            )
            stmt = stmt.join(latest, latest.c.pid == PlantProfileModel.id).where(latest.c.st == last_status)

        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = self.db.execute(
            stmt.order_by(func.coalesce(stats.c.last_at, PlantProfileModel.created_at).desc())
            .offset((page - 1) * page_size).limit(page_size)
        ).all()
        items = []
        for model, cnt, last_at in rows:
            last = self.db.execute(
                select(DiagnosisModel.decision_status, DiagnosisModel.predicted_label)
                .where(DiagnosisModel.plant_profile_id == model.id)
                .order_by(DiagnosisModel.diagnosed_at.desc()).limit(1)
            ).first()
            items.append(_profile_entity(model, cnt, last_at, last[0] if last else None, last[1] if last else None))
        return items, total

    def update(self, profile_id: UUID, owner_user_id: UUID, changes: dict) -> Optional[PlantProfile]:
        model = self.db.execute(
            select(PlantProfileModel).where(PlantProfileModel.id == profile_id,
                                            PlantProfileModel.owner_user_id == owner_user_id)
        ).scalar_one_or_none()
        if model is None:
            return None
        for key, value in changes.items():
            if key in _EDITABLE_FIELDS:
                setattr(model, key, value)
        model.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(model)
        return self._with_stats(model)

    def set_archived(self, profile_id: UUID, owner_user_id: UUID, archived: bool) -> Optional[PlantProfile]:
        model = self.db.execute(
            select(PlantProfileModel).where(PlantProfileModel.id == profile_id,
                                            PlantProfileModel.owner_user_id == owner_user_id)
        ).scalar_one_or_none()
        if model is None:
            return None
        model.archived_at = datetime.now(timezone.utc) if archived else None
        self.db.commit()
        self.db.refresh(model)
        return self._with_stats(model)


class SqlAlchemyObservationNoteRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, note: ObservationNote) -> ObservationNote:
        model = ObservationNoteModel(diagnosis_id=note.diagnosis_id, author_user_id=note.author_user_id,
                                     note_type=note.note_type, body=note.body, data_json=note.data or None)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return _note_entity(model)

    def list_for_diagnosis(self, diagnosis_id: UUID, limit: int = 200) -> List[ObservationNote]:
        rows = self.db.execute(
            select(ObservationNoteModel).where(ObservationNoteModel.diagnosis_id == diagnosis_id)
            .order_by(ObservationNoteModel.created_at.asc()).limit(limit)
        ).scalars().all()
        return [_note_entity(m) for m in rows]

    def list_for_diagnoses(self, diagnosis_ids: List[UUID]) -> dict:
        if not diagnosis_ids:
            return {}
        rows = self.db.execute(
            select(ObservationNoteModel).where(ObservationNoteModel.diagnosis_id.in_(diagnosis_ids))
            .order_by(ObservationNoteModel.created_at.asc())
        ).scalars().all()
        out: dict = {}
        for m in rows:
            out.setdefault(m.diagnosis_id, []).append(_note_entity(m))
        return out
