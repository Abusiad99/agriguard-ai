"""Domain entities: Plant, Disease, Treatment (knowledge base)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID


@dataclass
class Plant:
    id: Optional[UUID]
    canonical_name: str
    scientific_name: Optional[str] = None
    synonyms: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None


@dataclass
class Disease:
    id: Optional[UUID]
    plant_id: UUID
    name: str
    disease_type: Optional[str]
    description: str
    symptoms: List[str] = field(default_factory=list)
    causes: List[str] = field(default_factory=list)
    transmission_method: Optional[str] = None
    recovery_probability: Optional[float] = None       # FR-RESULT-2: only if supported
    estimated_recovery_time: Optional[str] = None       # FR-RESULT-2: only if supported
    version: int = 1
    is_current: bool = True
    created_by: Optional[UUID] = None
    created_at: Optional[datetime] = None

    def has_recovery_data(self) -> bool:
        return self.recovery_probability is not None or self.estimated_recovery_time is not None


class TreatmentCategory(str, Enum):
    ORGANIC = "organic"
    CHEMICAL = "chemical"
    BIOLOGICAL = "biological"


@dataclass
class Treatment:
    id: Optional[UUID]
    disease_id: UUID
    category: TreatmentCategory
    instructions: str
    safety_notes: Optional[str] = None
    source_citation: Optional[str] = None
    authority_referral_only: bool = False
    version: int = 1
    is_current: bool = True
    created_by: Optional[UUID] = None
    created_at: Optional[datetime] = None

    def is_dosage_verified(self) -> bool:
        """BR6: a chemical treatment must carry a source citation unless explicitly
        marked authority-referral-only."""
        if self.category != TreatmentCategory.CHEMICAL:
            return True
        return self.authority_referral_only or bool(self.source_citation)

    def may_display_instructions(self) -> bool:
        """BR6, display side: chemical instructions may be shown to users (API, PDF,
        Gemini tools) only when source-cited and not authority-referral-only.
        is_dosage_verified() is the save-time validity rule and is True for
        referral-only treatments, so it must not be used to gate display."""
        if self.category != TreatmentCategory.CHEMICAL:
            return True
        return bool(self.source_citation) and not self.authority_referral_only
