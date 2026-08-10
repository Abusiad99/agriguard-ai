# Gemini AI Reasoning Layer

This document explains the Gemini multimodal reasoning integration added on top
of AgriGuard AI's existing, unchanged Computer Vision diagnosis pipeline.

## 1. Why this exists, and what it is not

AgriGuard AI's Computer Vision model remains the **sole authority** for disease
detection. Nothing about that changed. Gemini is an **additional, optional
reasoning and explanation layer** that runs *after* the CV model has already
produced its diagnosis, confidence score, and severity result. Gemini:

- **Does** explain the visible symptoms in plain language.
- **Does** say whether those symptoms look consistent with the CV model's result.
- **Does** explain the confidence/severity numbers in plain language.
- **Does** produce treatment/prevention guidance — grounded in the trusted
  PostgreSQL knowledge base via function calling, not invented.
- **Does not** decide the diagnosis. It cannot override, replace, or introduce a
  different disease than what the CV model already produced.
- **Does not** invent a chemical product, a dosage, or a fact not present in the
  database or the tool results it receives.
- **Does not** block, slow past its own timeout, or ever cause the CV diagnosis
  to fail. If Gemini is unavailable for any reason, the rest of the diagnosis is
  returned exactly as it always was.

```
User uploads plant image
        |
Existing Computer Vision model  (unchanged — still authoritative)
        |
Disease + confidence + severity
        |
Gemini multimodal reasoning      (optional, additive, best-effort)
        |
Gemini analyzes the SAME image + the CV result + trusted DB context
        |
Gemini produces structured agricultural reasoning (validated JSON)
        |
Backend combines the result with trusted database information
        |
Existing Diagnosis Result page displays the enhanced result
```

## 2. Architecture

| Layer | Responsibility |
|---|---|
| Computer Vision model (`ai/`, `AiPipelineClient`) | Disease detection — unchanged |
| **Gemini** (`gemini_client.py`, `gemini_analysis_service.py`) | Multimodal reasoning, explanation, symptom interpretation, contextual agricultural reasoning |
| PostgreSQL (disease/treatment repositories) | Trusted disease/treatment knowledge — the only source of chemical dosage facts |
| Weather API (`weather_client.py`) | Environmental context — fetched once, reused as context for Gemini, never re-fetched by Gemini |
| Backend (`ScanOrchestrator`) | Orchestration, validation, security, business rules |
| Frontend (`DiagnosisResultPage`, `AiAnalysisSection`) | User experience |

### New files

- `backend/app/interface/schemas/ai_analysis_schemas.py` — the structured-output
  contract (`GeminiAnalysisSchema`) and the status wrapper (`AiAnalysisSchema`)
  used in the API response.
- `backend/app/infrastructure/external/gemini_client.py` — the `google-genai`
  SDK wrapper: request construction, function-calling tools, structured output
  parsing, and every failure path.
- `backend/app/application/services/gemini_analysis_service.py` — thin
  application-layer glue that turns a client result into the `AiAnalysis`
  domain entity `ScanOrchestrator` and the repositories work with.
- `backend/app/infrastructure/db/migrations/versions/0002_add_ai_analysis.py` —
  adds the single new table, `ai_analyses`.

### Modified files (all additive — see the Phase-report for the exact diff)

`config.py` (settings), `diagnosis.py` (domain entity), `interfaces.py`
(repository contract), `diagnosis_model.py` (SQLAlchemy model), `diagnosis_repository.py`
(persistence), `scan_service.py` (orchestration integration point),
`dependencies.py` (DI wiring), `diagnosis_schemas.py` + `scans_router.py` (API
response), `requirements.txt`, `.env.example`, `docker-compose.yml`, and the
frontend files listed in section 5.

## 3. Multimodal analysis and structured output

Gemini receives, for every scan (see `GeminiRequestContext` in `gemini_client.py`):

- The original uploaded plant image (same bytes stored for the diagnosis record).
- The plant species (if identified).
- The CV model's condition, confidence score, severity level, and affected area.
- The database's own description/symptoms for that disease, if on file.
- A weather summary, if the user shared their location — reusing the existing
  `WeatherService` result, never a second weather API call.

The output is validated against `GeminiAnalysisSchema` (Pydantic):

```json
{
  "diagnosis_explanation": "...",
  "observed_symptoms": ["..."],
  "cv_consistency": "consistent | partially_consistent | inconsistent | uncertain",
  "confidence_assessment": "...",
  "severity_explanation": "...",
  "treatment_guidance": ["..."],
  "prevention_guidance": ["..."],
  "environmental_risk": "...",
  "urgency": "low | medium | high"
}
```

**Why two `generate_content` calls instead of one.** The `google-genai` SDK
accepts `tools` (function calling) and `response_schema` (structured JSON
output) in the same request config, but combining live tool-calling with a
forced JSON schema in a single turn is not consistently honored across Gemini
API versions. Rather than ship an integration that sometimes silently returns
prose instead of JSON, `GeminiClient.analyze()` deliberately splits the work:

1. **Reasoning call** — tools enabled, free-form text output. Gemini reasons
   about the image and may call `get_disease_info` / `get_treatment_info` /
   `get_plant_info` / `get_weather` to ground its answer.
2. **Structuring call** — no tools, `response_mime_type="application/json"`,
   `response_schema=GeminiAnalysisSchema`. Reformats call 1's already-grounded
   reasoning into the exact required JSON shape.

Both calls' raw JSON is re-validated by our own Pydantic model regardless of
what the SDK claims to have already validated — arbitrary model output is never
trusted directly (see section 6).

## 4. Function calling

Four read-only tools are exposed to Gemini via the `google-genai` SDK's
automatic function calling (plain Python bound methods with type hints and
docstrings — the SDK introspects them and executes them itself mid-generation;
there is no manual dispatch loop in this codebase):

| Tool | Backs onto | Notes |
|---|---|---|
| `get_plant_info` | `IPlantRepository.get_by_canonical_name` | Read-only lookup |
| `get_disease_info` | `IDiseaseRepository.get_current_by_plant_and_name` | Read-only lookup |
| `get_treatment_info` | `ITreatmentRepository.get_current_for_disease` | **Enforces BR6 itself** — see below |
| `get_weather` | Reuses the already-fetched `WeatherSnapshot` | Never a new network call; reports unavailable rather than inventing data |

Every tool is implemented in `_GeminiTools` (`gemini_client.py`) as a thin
wrapper over the **existing** repository interfaces — no SQL, no new database
access path, no arbitrary code execution, and no write access. Gemini cannot
modify the database through these tools; they are strictly read-only.

## 5. Database grounding and BR6

`get_treatment_info` is the enforcement point for BR6 (a chemical treatment's
dosage instructions may only be returned if source-cited or explicitly marked
authority-referral-only). It applies **the exact same rule** used elsewhere in
the codebase:

```python
if t.category == "chemical" and not t.is_dosage_verified():
    instructions = "Consult your local agricultural authority for verified dosage guidance..."
else:
    instructions = t.instructions
```

This means Gemini cannot obtain an unverified dosage by asking a different way,
by rephrasing, or by not calling the tool at all — the substitution happens
inside the tool's return value, not in a prompt instruction Gemini could ignore.
See `tests/unit/test_gemini_analysis_service.py::TestGeminiToolsEnforceBr6` for
the two tests proving this (a verified-citation treatment returns real
instructions; an unverified one returns only the referral message).

## 6. Failure handling — Gemini is never a single point of failure

Every one of these degrades to the same outcome — the CV diagnosis is returned
unaffected, and `ai_analysis` in the API response reflects what happened:

| Situation | `ai_analysis` value |
|---|---|
| `GEMINI_API_KEY` not set | `null` (omitted from the UI entirely — not an error state) |
| Network error / timeout / rate limit / any SDK exception | `{"status": "unavailable", "message": "AI analysis temporarily unavailable."}` |
| Gemini returns empty text | same as above |
| Gemini returns malformed JSON | same as above (rejected by `json.loads`) |
| Gemini returns valid JSON that violates the schema (wrong enum, missing field) | same as above (rejected by Pydantic `model_validate`) |
| An unexpected exception anywhere in the Gemini call chain | same as above — caught a second time in `ScanOrchestrator._run_gemini_analysis` as a belt-and-suspenders guard |

The Gemini step in `ScanOrchestrator.process_scan` runs *after* the CV
diagnosis, disease lookup, and weather have already succeeded, and its own
exceptions are caught locally — a bug in the Gemini integration can never
prevent a diagnosis from being saved. See
`tests/unit/test_scan_service.py::TestGeminiIntegrationInScanFlow` for the four
tests covering disabled / success / reported-unavailable / unexpected-exception
paths at the orchestration level, and
`tests/unit/test_gemini_analysis_service.py` for the client/service-level tests
of the same failure modes plus invalid-response handling.

## 7. Database changes

One new table, `ai_analyses` — 1:1 with `diagnoses`, cascade-deleted with it,
following the exact same shape as the pre-existing `weather_snapshots` and
`recommendations` tables. No existing table, column, or constraint was
modified. See migration `0002_add_ai_analysis.py`. A disabled Gemini feature
(`GEMINI_API_KEY` unset) never writes a row to this table at all.

## 8. Environment configuration

```bash
# .env — leave GEMINI_API_KEY empty to disable the feature entirely
GEMINI_API_KEY=                  # get one at https://aistudio.google.com/apikey — never commit a real key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TIMEOUT_SECONDS=20.0
GEMINI_MAX_TOOL_CALLS=6
```

The key is read server-side only (`app/core/config.py`), is never included in
any API response schema, and is never logged (`gemini_client.py`'s exception
handler logs `type(exc).__name__` and the exception message, neither of which
the `google-genai` SDK populates with the request's auth header).

## 9. Running the system

No change to how the system is run. `docker compose up` (or the manual
uvicorn/Postgres setup already documented in the main README) works
identically whether or not `GEMINI_API_KEY` is set — with it unset, every
diagnosis behaves exactly as it did before this integration existed, just
without the "AI Agricultural Analysis" section appearing on the results page.

## 10. Live validation status

This integration was built and tested against the real `google-genai` SDK
(v2.17.0) — the SDK's `Client`, `GenerateContentConfig`, `Part.from_bytes`,
`AutomaticFunctionCallingConfig`, and structured-output (`response_schema`)
surfaces were all inspected directly against the installed package to confirm
the request shapes used here are valid for that SDK version.

**What was not, and could not be, exercised**: an actual network call to
`generativelanguage.googleapis.com`. This sandbox's network egress is
restricted to an allowlist (package registries, GitHub, Anthropic's own API)
that does not include Google's Generative Language API — the same constraint
that affected live Open-Meteo weather calls during this project's earlier
Phase 5 validation. Every code path up to that network call was exercised for
real, with the SDK client itself mocked at the boundary
(`tests/unit/test_gemini_analysis_service.py`). If Google has changed the
`google-genai` request/response shape since this was written, re-verify against
current SDK docs before relying on this in production.
