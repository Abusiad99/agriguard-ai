"""SQLAlchemy implementations of IPlantRepository, IDiseaseRepository, ITreatmentRepository."""
from __future__ import annotations

from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.entities.disease import Disease, Plant, Treatment, TreatmentCategory
from app.domain.repositories.interfaces import IDiseaseRepository, IPlantRepository, ITreatmentRepository
from app.infrastructure.db.models.knowledge_base_model import DiseaseModel, PlantModel, TreatmentModel


def _plant_to_entity(m: PlantModel) -> Plant:
    return Plant(id=m.id, canonical_name=m.canonical_name, scientific_name=m.scientific_name,
                 synonyms=m.synonyms_json or [], created_at=m.created_at)


def _disease_to_entity(m: DiseaseModel) -> Disease:
    return Disease(
        id=m.id, plant_id=m.plant_id, name=m.name, disease_type=m.disease_type,
        description=m.description, symptoms=m.symptoms_json or [], causes=m.causes_json or [],
        transmission_method=m.transmission_method,
        recovery_probability=float(m.recovery_probability) if m.recovery_probability is not None else None,
        estimated_recovery_time=m.estimated_recovery_time, version=m.version, is_current=m.is_current,
        created_by=m.created_by, created_at=m.created_at,
    )


def _treatment_to_entity(m: TreatmentModel) -> Treatment:
    return Treatment(
        id=m.id, disease_id=m.disease_id, category=TreatmentCategory(m.category),
        instructions=m.instructions, safety_notes=m.safety_notes, source_citation=m.source_citation,
        authority_referral_only=m.authority_referral_only, version=m.version, is_current=m.is_current,
        created_by=m.created_by, created_at=m.created_at,
    )


class SqlAlchemyPlantRepository(IPlantRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_by_canonical_name(self, canonical_name: str) -> Optional[Plant]:
        stmt = select(PlantModel).where(PlantModel.canonical_name == canonical_name)
        model = self.db.execute(stmt).scalar_one_or_none()
        return _plant_to_entity(model) if model else None

    def get_or_create(self, canonical_name: str) -> Plant:
        existing = self.get_by_canonical_name(canonical_name)
        if existing:
            return existing
        model = PlantModel(canonical_name=canonical_name, synonyms_json=[])
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return _plant_to_entity(model)

    def list(self) -> List[Plant]:
        models = self.db.execute(select(PlantModel).order_by(PlantModel.canonical_name)).scalars().all()
        return [_plant_to_entity(m) for m in models]


class SqlAlchemyDiseaseRepository(IDiseaseRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_current_by_plant_and_name(self, plant_id: UUID, name: str) -> Optional[Disease]:
        stmt = select(DiseaseModel).where(
            DiseaseModel.plant_id == plant_id, DiseaseModel.name == name, DiseaseModel.is_current == True  # noqa: E712
        )
        model = self.db.execute(stmt).scalar_one_or_none()
        return _disease_to_entity(model) if model else None

    def get_by_id(self, disease_id: UUID) -> Optional[Disease]:
        model = self.db.get(DiseaseModel, disease_id)
        return _disease_to_entity(model) if model else None

    def create_version(self, disease: Disease) -> Disease:
        # Supersede prior current version(s) for this plant+name (append-only, NFR-DATA-1).
        stmt = select(DiseaseModel).where(
            DiseaseModel.plant_id == disease.plant_id, DiseaseModel.name == disease.name,
            DiseaseModel.is_current == True,  # noqa: E712
        )
        prior = self.db.execute(stmt).scalar_one_or_none()
        next_version = 1
        if prior:
            prior.is_current = False
            next_version = prior.version + 1

        model = DiseaseModel(
            plant_id=disease.plant_id, name=disease.name, disease_type=disease.disease_type,
            description=disease.description, symptoms_json=disease.symptoms, causes_json=disease.causes,
            transmission_method=disease.transmission_method, recovery_probability=disease.recovery_probability,
            estimated_recovery_time=disease.estimated_recovery_time, version=next_version, is_current=True,
            created_by=disease.created_by,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return _disease_to_entity(model)

    def list(self, plant_id: Optional[UUID], search: Optional[str],
              page: int, page_size: int) -> Tuple[List[Disease], int]:
        stmt = select(DiseaseModel).where(DiseaseModel.is_current == True)  # noqa: E712
        if plant_id:
            stmt = stmt.where(DiseaseModel.plant_id == plant_id)
        if search:
            stmt = stmt.where(DiseaseModel.name.ilike(f"%{search}%"))
        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        stmt = stmt.order_by(DiseaseModel.name).offset((page - 1) * page_size).limit(page_size)
        models = self.db.execute(stmt).scalars().all()
        return [_disease_to_entity(m) for m in models], total


class SqlAlchemyTreatmentRepository(ITreatmentRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_current_for_disease(self, disease_id: UUID) -> List[Treatment]:
        stmt = select(TreatmentModel).where(
            TreatmentModel.disease_id == disease_id, TreatmentModel.is_current == True  # noqa: E712
        )
        models = self.db.execute(stmt).scalars().all()
        return [_treatment_to_entity(m) for m in models]

    def get_by_id(self, treatment_id: UUID) -> Optional[Treatment]:
        model = self.db.get(TreatmentModel, treatment_id)
        return _treatment_to_entity(model) if model else None

    def create_version(self, treatment: Treatment) -> Treatment:
        if not treatment.is_dosage_verified():
            raise ValueError(
                "DOSAGE_SOURCE_REQUIRED: a chemical treatment requires a source_citation "
                "unless authority_referral_only=True (BR6)."
            )
        stmt = select(TreatmentModel).where(
            TreatmentModel.disease_id == treatment.disease_id,
            TreatmentModel.category == treatment.category.value,
            TreatmentModel.is_current == True,  # noqa: E712
        )
        prior = self.db.execute(stmt).scalar_one_or_none()
        next_version = 1
        if prior:
            prior.is_current = False
            next_version = prior.version + 1

        model = TreatmentModel(
            disease_id=treatment.disease_id, category=treatment.category.value,
            instructions=treatment.instructions, safety_notes=treatment.safety_notes,
            source_citation=treatment.source_citation, authority_referral_only=treatment.authority_referral_only,
            version=next_version, is_current=True, created_by=treatment.created_by,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return _treatment_to_entity(model)
