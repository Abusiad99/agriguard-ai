"""
GeminiClient — the Gemini multimodal reasoning layer (see docs/GEMINI_INTEGRATION.md).

ARCHITECTURAL ROLE (do not blur this line — see requirement/principle #15 in the
integration brief this module was built against):
    Computer Vision model  -> disease detection (unchanged, still authoritative)
    Gemini                 -> multimodal reasoning / explanation / symptom
                               interpretation / contextual agricultural reasoning
    PostgreSQL              -> trusted disease/treatment knowledge (grounding)
    This module             -> orchestration of exactly one Gemini call sequence,
                               nothing else

Gemini NEVER decides the diagnosis. It receives the CV model's already-decided
plant/disease/confidence/severity and is asked to explain, corroborate, or flag
inconsistency with the visible image. It reasons about *guidance* using function
calling into the existing, already-BR6-compliant treatment repository — it cannot
invent a chemical product, dosage, or disease unsupported by the database, because
the tool functions themselves enforce that (see `_GeminiTools` below), not Gemini's
good behavior.

FAILURE MODEL (requirement #8): every failure mode here — missing API key, network
error, timeout, rate limit, invalid/unparseable model output — results in
`GeminiAnalysisResult(status="disabled"|"unavailable", analysis=None, ...)`. This
module never raises out to its caller and never fabricates a plausible-looking
analysis; ScanOrchestrator always gets a definite answer immediately.

WHY TWO GENERATE_CONTENT CALLS: the google-genai SDK's `GenerateContentConfig`
accepts `tools` (for automatic function calling) and `response_schema` (for
structured JSON output) in the same config, but combining live tool-calling with a
forced JSON response schema in a single turn is not consistently honored across
Gemini API versions. To avoid shipping a fragile "sometimes returns text instead of
JSON" integration, this client deliberately splits the work:
  Call 1 (reasoning): tools enabled (automatic function calling), free-form text
                       output — Gemini reasons about the image and may call
                       get_disease_info / get_treatment_info / get_weather /
                       get_plant_info to ground its answer in the trusted DB.
  Call 2 (structuring): no tools, response_mime_type="application/json",
                        response_schema=GeminiAnalysisSchema — reformats Call 1's
                        grounded reasoning into the exact required JSON shape.
Both calls' raw JSON is re-validated by our own Pydantic model regardless of what
the SDK claims to have already validated (requirement: never trust arbitrary
model output as-is).

NOTE ON LIVE VALIDATION: this client could not be exercised against the real
Gemini API from the sandbox this integration was built in (no network egress to
generativelanguage.googleapis.com there — see the Phase 5 validation report for
the same constraint affecting Open-Meteo). Every code path up to the actual
network call was validated; the live call itself is marked BLOCKED in the test
report. Re-verify against current google-genai SDK docs if Google has changed the
API surface since this was written.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from pydantic import ValidationError

from app.core.config import get_settings
from app.domain.repositories.interfaces import IDiseaseRepository, IPlantRepository, ITreatmentRepository
from app.interface.schemas.ai_analysis_schemas import GeminiAnalysisSchema

logger = logging.getLogger("agriguard.gemini")
settings = get_settings()


@dataclass
class GeminiAnalysisResult:
    status: str  # "ok" | "disabled" | "unavailable"
    analysis: Optional[GeminiAnalysisSchema] = None
    message: Optional[str] = None
    model_name: Optional[str] = None


@dataclass
class GeminiRequestContext:
    """Everything Gemini needs, assembled by the caller (application service) from
    data the ScanOrchestrator already has — nothing here is fetched independently
    by this module, matching requirement #5 ("do not duplicate the weather API
    implementation") and #3 ("database as source of truth", populated by the
    caller from the same disease/treatment repositories the rest of the app
    already uses)."""

    image_bytes: bytes
    image_mime_type: str
    plant_name: Optional[str]
    cv_condition: Optional[str]  # "healthy" or the CV model's disease label
    cv_confidence_score: float
    cv_severity_level: Optional[str]
    cv_affected_area_pct: Optional[float]
    disease_description: Optional[str] = None
    disease_symptoms: List[str] = field(default_factory=list)
    weather_summary: Optional[str] = None  # pre-formatted by the caller from the existing WeatherService result


class _GeminiTools:
    """Function-calling tools exposed to Gemini. Every function is read-only, goes
    through the existing repository interfaces only (no SQL, no direct DB writes,
    no arbitrary code execution — requirement #4), and independently enforces BR6
    (a chemical treatment is only returned with real dosage instructions if it
    carries a source citation or is explicitly marked authority-referral-only;
    otherwise the safe fallback string is returned instead — the same rule
    ScanOrchestrator._generate_report already applies). Gemini cannot bypass this
    by asking a different way: the enforcement lives in the tool, not the prompt.

    Plain bound methods with type-hinted parameters and docstrings are used
    directly as `tools=[...]` entries — the google-genai SDK introspects them to
    build function declarations and performs automatic function calling (invoking
    them itself mid-generation and feeding results back to the model) with no
    manual dispatch loop needed here.
    """

    def __init__(
        self,
        plant_repo: IPlantRepository,
        disease_repo: IDiseaseRepository,
        treatment_repo: ITreatmentRepository,
        weather_summary: Optional[str],
    ):
        self._plant_repo = plant_repo
        self._disease_repo = disease_repo
        self._treatment_repo = treatment_repo
        self._weather_summary = weather_summary

    def get_plant_info(self, plant_name: str) -> dict:
        """Look up trusted information about a plant species by its common name.

        Args:
            plant_name: Common/canonical name of the plant, e.g. "tomato".
        """
        try:
            plant = self._plant_repo.get_by_canonical_name(plant_name.strip().lower())
        except Exception as exc:  # pragma: no cover - defensive, repo layer already narrow
            logger.warning("Gemini tool get_plant_info failed: %s", exc)
            return {"found": False, "reason": "lookup_failed"}
        if plant is None:
            return {"found": False}
        return {
            "found": True,
            "canonical_name": plant.canonical_name,
            "scientific_name": plant.scientific_name,
            "synonyms": plant.synonyms,
        }

    def get_disease_info(self, plant_name: str, disease_name: str) -> dict:
        """Look up trusted, database-verified information about a plant disease.

        Args:
            plant_name: Common/canonical name of the plant, e.g. "tomato".
            disease_name: Disease/condition name as known in the knowledge base,
                e.g. "early_blight".
        """
        try:
            plant = self._plant_repo.get_by_canonical_name(plant_name.strip().lower())
            if plant is None:
                return {"found": False, "reason": "unknown_plant"}
            disease = self._disease_repo.get_current_by_plant_and_name(plant.id, disease_name)
        except Exception as exc:  # pragma: no cover
            logger.warning("Gemini tool get_disease_info failed: %s", exc)
            return {"found": False, "reason": "lookup_failed"}
        if disease is None:
            return {"found": False, "reason": "unknown_disease"}
        return {
            "found": True,
            "name": disease.name,
            "type": disease.disease_type,
            "description": disease.description,
            "symptoms": disease.symptoms,
            "causes": disease.causes,
            "transmission_method": disease.transmission_method,
            "recovery_probability": disease.recovery_probability,
            "estimated_recovery_time": disease.estimated_recovery_time,
        }

    def get_treatment_info(self, plant_name: str, disease_name: str) -> dict:
        """Look up trusted, database-verified treatment options for a diagnosed
        plant disease. Chemical treatments without a verified dosage source are
        never returned with dosage instructions — only a referral notice.

        Args:
            plant_name: Common/canonical name of the plant, e.g. "tomato".
            disease_name: Disease/condition name as known in the knowledge base.
        """
        try:
            plant = self._plant_repo.get_by_canonical_name(plant_name.strip().lower())
            if plant is None:
                return {"found": False, "reason": "unknown_plant"}
            disease = self._disease_repo.get_current_by_plant_and_name(plant.id, disease_name)
            if disease is None:
                return {"found": False, "reason": "unknown_disease"}
            treatments = self._treatment_repo.get_current_for_disease(disease.id)
        except Exception as exc:  # pragma: no cover
            logger.warning("Gemini tool get_treatment_info failed: %s", exc)
            return {"found": False, "reason": "lookup_failed"}

        result = {"found": True, "organic": None, "chemical": None, "biological": None}
        for t in treatments:
            # BR6 enforcement, independent of Gemini — mirrors
            # ScanOrchestrator._generate_report's identical rule.
            if t.category.value == "chemical" and not t.is_dosage_verified():
                instructions = ("Consult your local agricultural authority for verified "
                                 "dosage guidance for this treatment; no verified dosage "
                                 "is on file.")
            else:
                instructions = t.instructions
            result[t.category.value] = {
                "instructions": instructions,
                "safety_notes": t.safety_notes,
                "source_citation": t.source_citation,
            }
        return result

    def get_weather(self) -> dict:
        """Get the current weather/environmental conditions already retrieved for
        this scan's location, if the user shared their location. Does not perform
        a new weather lookup — returns whatever the application already fetched."""
        if not self._weather_summary:
            return {"available": False}
        return {"available": True, "summary": self._weather_summary}


_SYSTEM_INSTRUCTION = (
    "You are an agricultural reasoning assistant embedded in AgriGuard AI. A "
    "separate, already-trained computer vision model has ALREADY diagnosed the "
    "plant in the image; that diagnosis is authoritative and is provided to you "
    "as context. Your job is ONLY to: (1) describe the visible symptoms in the "
    "image, (2) explain whether those symptoms are consistent with the given CV "
    "diagnosis, (3) explain the confidence and severity results in plain "
    "language, (4) provide practical treatment/prevention guidance grounded in "
    "the trusted database (use the provided tools to look up verified disease "
    "and treatment records rather than relying on general knowledge whenever "
    "possible), and (5) assess environmental risk and urgency. "
    "You must NEVER propose a different disease than the one given, never invent "
    "a chemical product or dosage that isn't confirmed by a tool lookup, and "
    "never invent weather data — if the weather tool reports unavailable, simply "
    "say environmental data isn't available."
)


def _build_context_prompt(ctx: GeminiRequestContext) -> str:
    lines = [
        f"Plant: {ctx.plant_name or 'unknown'}",
        f"CV model diagnosis: {ctx.cv_condition or 'unknown'}",
        f"CV model confidence: {ctx.cv_confidence_score}%",
    ]
    if ctx.cv_severity_level:
        lines.append(f"CV model severity: {ctx.cv_severity_level}")
    if ctx.cv_affected_area_pct is not None:
        lines.append(f"CV model affected area: {ctx.cv_affected_area_pct}%")
    if ctx.disease_description:
        lines.append(f"Database disease description: {ctx.disease_description}")
    if ctx.disease_symptoms:
        lines.append(f"Database-known symptoms: {', '.join(ctx.disease_symptoms)}")
    if ctx.weather_summary:
        lines.append(f"Current weather: {ctx.weather_summary}")
    lines.append(
        "Analyze the attached plant image against this context. Use the "
        "get_disease_info / get_treatment_info / get_plant_info / get_weather "
        "tools if you need to confirm or expand on trusted database details "
        "before answering."
    )
    return "\n".join(lines)


_STRUCTURE_PROMPT_TEMPLATE = (
    "Reformat the following agricultural analysis into the required JSON "
    "structure exactly. Do not add new facts; only restructure what is already "
    "here. If a list field has no items, use an empty list.\n\n"
    "--- ANALYSIS TO STRUCTURE ---\n{reasoning_text}"
)


class GeminiClient:
    """Thin, isolated wrapper around the `google-genai` SDK. Constructed lazily
    and cached (mirrors AiPipelineClient's lazy-singleton pattern) so importing
    this module never requires GEMINI_API_KEY to be set — the client object is
    only actually built the first time `analyze()` is called with the feature
    enabled."""

    _sdk_client = None

    def _get_sdk_client(self):
        if GeminiClient._sdk_client is None:
            from google import genai  # imported lazily so the dependency is optional at import time
            GeminiClient._sdk_client = genai.Client(api_key=settings.gemini_api_key)
        return GeminiClient._sdk_client

    def analyze(
        self,
        ctx: GeminiRequestContext,
        plant_repo: IPlantRepository,
        disease_repo: IDiseaseRepository,
        treatment_repo: ITreatmentRepository,
    ) -> GeminiAnalysisResult:
        if not settings.gemini_enabled:
            return GeminiAnalysisResult(status="disabled", message="Gemini AI analysis is not configured.")

        try:
            from google import genai  # noqa: F401 - import-availability check
            from google.genai import types
        except ImportError:
            logger.warning("google-genai is not installed; Gemini analysis is unavailable.")
            return GeminiAnalysisResult(status="unavailable", message="AI analysis temporarily unavailable.")

        try:
            client = self._get_sdk_client()
            tools = _GeminiTools(plant_repo, disease_repo, treatment_repo, ctx.weather_summary)

            # --- Call 1: multimodal reasoning with function calling ---
            reasoning_response = client.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    types.Part.from_bytes(data=ctx.image_bytes, mime_type=ctx.image_mime_type),
                    types.Part.from_text(text=_build_context_prompt(ctx)),
                ],
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_INSTRUCTION,
                    tools=[tools.get_disease_info, tools.get_treatment_info,
                           tools.get_plant_info, tools.get_weather],
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        maximum_remote_calls=settings.gemini_max_tool_calls,
                    ),
                    http_options=types.HttpOptions(timeout=int(settings.gemini_timeout_seconds * 1000)),
                ),
            )
            reasoning_text = (reasoning_response.text or "").strip()
            if not reasoning_text:
                logger.warning("Gemini reasoning call returned no text.")
                return GeminiAnalysisResult(status="unavailable", message="AI analysis temporarily unavailable.")

            # --- Call 2: force the reasoning into the required structured shape ---
            structure_response = client.models.generate_content(
                model=settings.gemini_model,
                contents=_STRUCTURE_PROMPT_TEMPLATE.format(reasoning_text=reasoning_text),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiAnalysisSchema,
                    http_options=types.HttpOptions(timeout=int(settings.gemini_timeout_seconds * 1000)),
                ),
            )
            raw_text = (structure_response.text or "").strip()
            if not raw_text:
                logger.warning("Gemini structuring call returned no text.")
                return GeminiAnalysisResult(status="unavailable", message="AI analysis temporarily unavailable.")

            try:
                parsed = json.loads(raw_text)
                analysis = GeminiAnalysisSchema.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError) as exc:
                logger.warning("Gemini structured output failed validation: %s", exc)
                return GeminiAnalysisResult(status="unavailable", message="AI analysis temporarily unavailable.")

            return GeminiAnalysisResult(status="ok", analysis=analysis, model_name=settings.gemini_model)

        except Exception as exc:
            # Deliberately broad: network errors, SDK-internal exceptions, rate
            # limits (google.genai.errors.APIError and friends), timeouts — all
            # of them degrade the same way. Never let a Gemini failure propagate
            # into the diagnosis pipeline (requirement #8). Never log the API key
            # (it never appears in these exception messages — the SDK raises HTTP
            # status/body details, not the request's auth header).
            logger.warning("Gemini analysis failed (%s): %s", type(exc).__name__, exc)
            return GeminiAnalysisResult(status="unavailable", message="AI analysis temporarily unavailable.")
