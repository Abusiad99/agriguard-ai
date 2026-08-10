"""
AI Agricultural Analysis schemas — the Gemini multimodal reasoning layer's
structured output contract.

IMPORTANT ARCHITECTURAL NOTE (see docs/GEMINI_INTEGRATION.md): Gemini is a
*reasoning and explanation* layer on top of the existing Computer Vision
diagnosis, never a replacement for it. Gemini receives the CV model's already-
decided disease/confidence/severity and is asked to explain, corroborate, or flag
inconsistencies with the visible image — it does not get to invent a different
disease. Any treatment/dosage facts Gemini's `treatment_guidance` mentions are
expected to be grounded in the trusted application database (via function
calling into the existing disease/treatment repositories, see
infrastructure/external/gemini_client.py), not fabricated chemistry — BR6
(verified-dosage-only chemical guidance) is enforced independently by the
existing treatment repository/service layer regardless of what Gemini says.

`GeminiAnalysisSchema` mirrors the exact JSON shape requested from the model
(response_mime_type="application/json", response_schema=GeminiAnalysisSchema),
and is re-validated here on the way back — the model's raw JSON is never trusted
directly; if it fails Pydantic validation the whole analysis is treated as
unavailable (see AiAnalysisStatus.UNAVAILABLE), never fabricated or partially
trusted.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class CvConsistency(str, Enum):
    CONSISTENT = "consistent"
    PARTIALLY_CONSISTENT = "partially_consistent"
    INCONSISTENT = "inconsistent"
    UNCERTAIN = "uncertain"


class AnalysisUrgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GeminiAnalysisSchema(BaseModel):
    """The exact structured output requested from Gemini for one diagnosis.
    Every field is required in the response_schema sent to the model; Pydantic
    re-validates the model's JSON against this same shape on the way back."""

    diagnosis_explanation: str = Field(
        description="Plain-language explanation of the visible symptoms and whether "
                     "they are consistent with the CV model's diagnosis."
    )
    observed_symptoms: List[str] = Field(default_factory=list, description="Symptoms Gemini can see in the image.")
    cv_consistency: CvConsistency = Field(
        description="Whether the visible symptoms support the CV model's condition."
    )
    confidence_assessment: str = Field(
        description="Gemini's plain-language commentary on the CV model's confidence score."
    )
    severity_explanation: str = Field(description="Plain-language explanation of the severity/affected-area result.")
    treatment_guidance: List[str] = Field(
        default_factory=list,
        description="Practical guidance framed around the database-sourced treatment options provided in context; "
                     "Gemini must not invent chemical products or dosages not present in that context.",
    )
    prevention_guidance: List[str] = Field(default_factory=list)
    environmental_risk: str = Field(description="Risk commentary given the weather/environmental context, if any.")
    urgency: AnalysisUrgency


class AiAnalysisStatus(str, Enum):
    OK = "ok"
    DISABLED = "disabled"       # GEMINI_API_KEY not configured — feature intentionally off
    UNAVAILABLE = "unavailable"  # attempted but failed (timeout, network, invalid response, rate limit, etc.)


class AiAnalysisSchema(BaseModel):
    """Wraps GeminiAnalysisSchema with a status so the frontend can distinguish
    "feature disabled" from "attempted but temporarily unavailable" from "ok" —
    the CV diagnosis above this is always present and complete regardless of
    which of these three applies (requirement: Gemini failure never blocks the
    existing diagnosis)."""

    status: AiAnalysisStatus
    analysis: Optional[GeminiAnalysisSchema] = None
    message: Optional[str] = None
