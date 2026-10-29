"""Domain entities: PlantProfile (a user's tracked plant) and ObservationNote
(append-only note/feedback attached to a diagnosis observation)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from uuid import UUID

GROWING_ENVIRONMENTS = ("field", "greenhouse", "indoor", "orchard", "nursery", "other")
NOTE_TYPES = ("user_note", "follow_up", "treatment_applied", "expert_feedback", "correction", "plant_link_change")


@dataclass
class PlantProfile:
    id: Optional[UUID]
    owner_user_id: UUID
    name: str
    crop_type: Optional[str] = None
    variety: Optional[str] = None
    planting_date: Optional[date] = None
    location_label: Optional[str] = None
    growing_environment: Optional[str] = None
    notes: Optional[str] = None
    archived_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Aggregates filled by list queries (not stored columns).
    observation_count: int = 0
    last_observed_at: Optional[datetime] = None
    last_decision_status: Optional[str] = None
    last_predicted_label: Optional[str] = None


@dataclass
class ObservationNote:
    id: Optional[UUID]
    diagnosis_id: UUID
    author_user_id: Optional[UUID]
    note_type: str
    body: str = ""
    data: dict = field(default_factory=dict)
    created_at: Optional[datetime] = None
