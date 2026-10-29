# AgriGuard AI — REST API Specification

**Base URL**: `https://api.agriguard.ai/api/v1` (production) / `http://localhost:8000/api/v1` (dev)
**Format**: JSON request/response bodies (except file upload/download endpoints).
**Auth**: Bearer JWT (`Authorization: Bearer <access_token>`), except where marked `Public`.

## 1. Conventions

### 1.1 Standard Error Response
Every non-2xx response returns this shape:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable description",
    "details": [ { "field": "email", "issue": "must be a valid email address" } ]
  },
  "request_id": "a1b2c3d4-..."
}
```

### 1.2 Standard Status Codes
| Code | Meaning | Used for |
|---|---|---|
| 200 | OK | Successful GET/PUT/PATCH |
| 201 | Created | Successful POST creating a resource |
| 204 | No Content | Successful DELETE |
| 400 | Bad Request | Malformed request body/params |
| 401 | Unauthorized | Missing/invalid/expired JWT |
| 403 | Forbidden | Valid JWT, insufficient role (BR3/BR4) |
| 404 | Not Found | Resource does not exist or not visible to requester |
| 409 | Conflict | Duplicate email on register, etc. |
| 422 | Unprocessable Entity | Semantically invalid input (e.g., corrupt image, FR-SCAN-2) |
| 429 | Too Many Requests | Rate limit exceeded (NFR-SEC-5) |
| 500 | Internal Server Error | Unhandled server fault |
| 503 | Service Unavailable | Dependency (DB/AI service) unreachable |

### 1.3 Pagination
List endpoints accept `?page=1&page_size=20` (max `page_size=100`) and return:
```json
{ "items": [...], "page": 1, "page_size": 20, "total": 137, "total_pages": 7 }
```

---

## 2. Auth — `/auth`

### POST `/auth/register`  — Public — FR-AUTH-1
**Request**
```json
{ "email": "farmer@example.com", "password": "S3cur3P@ss!", "full_name": "Youssef Amrani" }
```
**Response `201`**
```json
{ "id": "uuid", "email": "farmer@example.com", "full_name": "Youssef Amrani", "role": "farmer" }
```
**Errors**: `409 EMAIL_ALREADY_EXISTS`, `400 VALIDATION_ERROR` (weak password / malformed email)

### POST `/auth/login` — Public — FR-AUTH-2
**Request**: `{ "email": "...", "password": "..." }`
**Response `200`**
```json
{ "access_token": "eyJ...", "refresh_token": "eyJ...", "token_type": "bearer", "expires_in": 900,
  "user": { "id": "uuid", "role": "farmer", "full_name": "Youssef Amrani" } }
```
**Errors**: `401 INVALID_CREDENTIALS`

### POST `/auth/refresh` — Public (requires valid refresh token) — FR-AUTH-2, NFR-SEC-3
**Request**: `{ "refresh_token": "eyJ..." }`
**Response `200`**: new `{ access_token, refresh_token, expires_in }`
**Errors**: `401 INVALID_OR_REVOKED_TOKEN`

### POST `/auth/logout` — Auth required — FR-AUTH-5
**Request**: `{ "refresh_token": "eyJ..." }`
**Response `204`**

### POST `/auth/password-reset/request` — Public — FR-AUTH-4
**Request**: `{ "email": "..." }`
**Response `202`**: `{ "message": "If the email exists, a reset link has been sent." }`
(Always returns 202 regardless of whether the email exists, to prevent user enumeration.)

### POST `/auth/password-reset/confirm` — Public — FR-AUTH-4
**Request**: `{ "token": "...", "new_password": "..." }`
**Response `200`**: `{ "message": "Password updated." }`
**Errors**: `400 INVALID_OR_EXPIRED_TOKEN`

---

## 3. Scans & Diagnoses — `/scans`, `/diagnoses`

### POST `/scans` — Auth required (role: farmer) — FR-SCAN, FR-AI, UC-03
**Request**: `multipart/form-data`
- `image`: file (jpeg/png/webp, ≤15MB)
- `latitude`: float, optional
- `longitude`: float, optional
- `attach_location`: boolean, default `false` (FR-SCAN-3)

**Response `201`** (successful full diagnosis)
```json
{
  "diagnosis_id": "uuid",
  "status": "completed",
  "plant": { "name": "Date Palm", "scientific_name": "Phoenix dactylifera" },
  "disease": {
    "name": "Red Palm Weevil", "type": "pest_infestation",
    "description": "...", "symptoms": ["..."], "causes": ["..."],
    "transmission_method": "..."
  },
  "confidence_score": 92.4,
  "severity_level": "severe",
  "affected_area_pct": 34.2,
  "healthy_area_pct": 65.8,
  "roi_image_url": "https://.../roi/abc.png",
  "heatmap_image_url": "https://.../heatmap/abc.png",
  "low_confidence_flag": false,
  "pests_detected": [ { "name": "Red Palm Weevil", "confidence": 92.4, "bbox": [x, y, w, h] } ],
  "treatment": {
    "organic": { "instructions": "...", "safety_notes": "..." },
    "chemical": { "instructions": "...", "safety_notes": "...", "source_citation": "..." },
    "biological": null
  },
  "prevention_advice": ["...", "..."],
  "recovery_probability": null,
  "estimated_recovery_time": null,
  "weather": { "temperature_c": 34.1, "humidity_pct": 28, "wind_speed_kmh": 12,
               "rain_probability_pct": 5, "uv_index": 8.2 },
  "recommendation": { "irrigation_advice": "...", "spraying_advice": "...", "fertilizer_advice": "..." },
  "report_url": "https://.../reports/abc.pdf",
  "diagnosed_at": "2026-08-06T10:15:00Z"
}
```
**Response `200`** (unrecognized plant — Alt Flow A1)
```json
{ "diagnosis_id": "uuid", "status": "unrecognized_plant",
  "message": "We could not confidently identify this plant. Please retake the photo with clearer framing." }
```
**Errors**: `422 INVALID_IMAGE`, `413 FILE_TOO_LARGE`, `429 RATE_LIMITED`, `503 AI_SERVICE_UNAVAILABLE`

### GET `/diagnoses/{id}` — Auth required (owner or admin) — FR-RESULT
**Response `200`**: same shape as the `/scans` `201` response body.
**Errors**: `403 FORBIDDEN` (not owner, not admin), `404 NOT_FOUND`

### GET `/diagnoses` — Auth required — FR-HIST-2, UC-06
**Query params**: `plant`, `disease`, `date_from`, `date_to`, `page`, `page_size`
**Response `200`**: paginated list of diagnosis summaries (id, plant, disease, severity,
confidence, thumbnail_url, diagnosed_at).

### GET `/diagnoses/compare?a={id}&b={id}` — Auth required (owner of both, or admin) — FR-HIST-3, UC-07
**Response `200`**:
```json
{ "a": { "...diagnosis summary..." }, "b": { "...diagnosis summary..." },
  "delta": { "confidence_change": 3.1, "severity_change": "moderate_to_severe" } }
```
**Errors**: `403 FORBIDDEN`, `404 NOT_FOUND` (either id)

---

## 4. Reports — `/reports`

### GET `/reports/{diagnosis_id}` — Auth required (owner or admin) — FR-REPORT-2, BR5
**Response `200`**: `application/pdf` binary stream.
**Errors**: `403 FORBIDDEN`, `404 NOT_FOUND` (diagnosis has no completed report, per BR5)

---

## 5. Dashboard — `/dashboard`

### GET `/dashboard/me` — Auth required — FR-DASH-1/2/3, UC-08
**Response `200`**
```json
{
  "total_scans": 128, "healthy_count": 71, "diseased_count": 57,
  "palm_disease_stats": { "total_palm_scans": 20, "red_palm_weevil_incidents": 4 },
  "most_common_diseases": [ { "name": "Early Blight", "count": 18 }, ... ],
  "monthly_trend": [ { "month": "2026-06", "scan_count": 40 }, ... ]
}
```

### GET `/dashboard/system` — Auth required (role: admin, agronomist) — FR-ADMIN-4, UC-12
**Response `200`**: same shape, aggregated system-wide.
**Errors**: `403 FORBIDDEN` (role farmer)

---

## 6. Knowledge Base — `/diseases`, `/treatments`

### GET `/diseases` — Auth required — FR-RESULT, browse
**Query params**: `plant_id`, `search`, `page`, `page_size`
**Response `200`**: paginated list of current disease entries.

### POST `/diseases` — Auth required (role: agronomist, admin) — FR-ADMIN-2, UC-09
**Request**
```json
{ "plant_id": "uuid", "name": "Bayoud Disease", "disease_type": "fungal",
  "description": "...", "symptoms": ["..."], "causes": ["..."],
  "transmission_method": "...", "recovery_probability": null, "estimated_recovery_time": null }
```
**Response `201`**: created disease entry (version 1).
**Errors**: `403 FORBIDDEN` (role farmer), `400 VALIDATION_ERROR`

### PUT `/diseases/{id}` — Auth required (role: agronomist, admin) — FR-ADMIN-2, UC-09
Creates a new version, marks prior version `is_current = false` (NFR-DATA-1). Same request/response
shape as POST. **Errors**: `403 FORBIDDEN`, `404 NOT_FOUND`

### GET `/treatments?disease_id={id}` — Auth required — FR-TREAT
**Response `200`**: current treatment entries for the disease, grouped by category.

### POST `/treatments` — Auth required (role: agronomist, admin) — FR-ADMIN-3, UC-10
**Request**
```json
{ "disease_id": "uuid", "category": "chemical", "instructions": "...", "safety_notes": "...",
  "source_citation": "FAO Pesticide Guideline 2023, p.14", "authority_referral_only": false }
```
**Response `201`**: created treatment entry.
**Errors**: `422 DOSAGE_SOURCE_REQUIRED` — returned if `category=chemical` and neither
`source_citation` nor `authority_referral_only=true` is provided (BR6, mirrors the DB CHECK
constraint so the error is caught early with a clear message rather than surfacing as a raw DB
error).

### PUT `/treatments/{id}` — Auth required (role: agronomist, admin) — FR-ADMIN-3, UC-10
Same versioning semantics as disease updates.

---

## 7. Admin — `/admin`

### GET `/admin/users` — Auth required (role: admin) — FR-ADMIN-1, UC-11
**Query params**: `role`, `is_active`, `search`, `page`, `page_size`
**Response `200`**: paginated user list.

### PATCH `/admin/users/{id}` — Auth required (role: admin) — FR-ADMIN-1, UC-11
**Request**: `{ "role": "agronomist" }` or `{ "is_active": false }`
**Response `200`**: updated user record. Logged to `audit_logs` with acting admin's ID.
**Errors**: `403 FORBIDDEN`, `404 NOT_FOUND`, `400 CANNOT_MODIFY_SELF_ROLE` (guard against an
admin locking themselves out)

### GET `/admin/reports/export` — Auth required (role: admin) — FR-ADMIN-4, UC-12
**Query params**: `date_from`, `date_to`, `format=csv|json`
**Response `200`**: `text/csv` or `application/json` export stream.

---

## 8. Weather — `/weather`

### GET `/weather?lat={lat}&lon={lon}` — Auth required — FR-WEATHER-1
**Response `200`**
```json
{ "temperature_c": 34.1, "humidity_pct": 28, "wind_speed_kmh": 12,
  "rain_probability_pct": 5, "uv_index": 8.2, "retrieved_at": "2026-08-06T10:12:00Z" }
```
**Response `200` (degraded, NFR-AVAIL-2/BR7)**
```json
{ "available": false, "reason": "weather_provider_unreachable" }
```
(Never a 5xx for weather unavailability — the contract guarantees callers a well-formed response
they can branch on, since a downstream scan must still complete without weather data.)

---

## 9. System

### GET `/health` — Public — NFR-OBS-2
**Response `200`**
```json
{ "status": "ok", "database": "ok", "cache": "ok", "ai_service": "ok" }
```
**Response `503`**: same shape with any subsystem marked `"degraded"` or `"down"`.

---

## 10. Rate Limits (NFR-SEC-5)
| Endpoint group | Limit |
|---|---|
| `/auth/login`, `/auth/register` | 10 requests / 5 min / IP |
| `/scans` (POST) | 30 requests / hour / user |
| All other authenticated endpoints | 300 requests / 5 min / user |

## 11. Authentication Details
- Access tokens: JWT, HS256 or RS256, 15-minute TTL, contain `sub` (user id), `role`, `exp`, `iat`.
- Refresh tokens: opaque random string, hashed at rest (`refresh_tokens.token_hash`), 30-day TTL,
  rotated on every use (old token revoked, new token issued) per NFR-SEC-3.
- Role checks (BR3/BR4) are enforced server-side on every role-gated route via a dependency/
  middleware, never trusted from client-supplied data.

---

## 12. Pipeline 2.0 additions (reliability, plant tracking, differential, assistant)

All endpoints below require authentication. Every request is ownership-checked on the server: a resource that belongs to another user returns **404** for plants and **403** for diagnoses (as before). Request-validation failures use the standard `400 VALIDATION_ERROR` envelope.

### 12.1 Changes to `POST /scans`

**New optional form fields:**
- `plant_profile_id`, or `new_plant_name` (sending both is a 400);
- `note` (≤ 4000 characters).

**Validation.** The upload is validated by its *decoded* content:
- JPEG, PNG or WebP only (otherwise **415** `UNSUPPORTED_MEDIA_TYPE`);
- at most 50 megapixels;
- the size limit is enforced while streaming.

**Image-quality gate.** The gate runs before anything is stored. An unusable photo returns `201` with:

```json
{ "status": "rejected_image_quality", "message": "...",
  "quality": { "status": "rejected", "issues": [{ "code": "too_blurry", "severity": "reject",
               "message": "...", "hint": "...", "metric": 3.1, "threshold": 12.0 }], "metrics": {...} } }
```

**Completed scans** return `DiagnosisResponse` with these additional fields:

| field | meaning |
|---|---|
| `decision_status` | `confident` \| `uncertain` \| `inconclusive` \| `legacy` |
| `decision` | top-1 probability, margin, normalised entropy, plant probability mass, `thresholds {confident, reject, plant_mass, source: validation\|env_override\|unvalidated_default, temperature, calibrated}` |
| `predicted_label` / `predicted_display_name` | model top-1 class (null when inconclusive) |
| `differential` | `model_candidates[]` (label, probability %, cause type, parts, patterns, regulated, `has_knowledge_base_entry`), `also_consider[]`, `not_assessable_by_model[]`, `follow_up_questions[]`, `answers`, `hints[]`, `expert_review_recommended`, `expert_review_reasons[]` |
| `image_quality` | quality report (warnings for accepted photos) |
| `original_image_url`, `heatmap_image_url`, `explanation.image_url` | **signed, expiring** `/api/v1/media/...` URLs |
| `explanation` | `{method: "grad_cam", available, reason, target_label}` — model attention, not a lesion map |
| `segmentation` | `{status: measured\|unavailable, reason, method, model_version, measurement{affected_area_pct, leaf/lesion pixels & regions}, severity{level, basis}, overlay_url, mask_url}` |
| `measurement_basis` | `segmentation` \| `legacy_attention_estimate` \| null |
| `model_version`, `pipeline_version`, `plant_profile{id,name}`, `limitations[]`, `is_legacy` | provenance |

**Other behaviour:**
- `disease`, `treatment` and `prevention_advice` are only filled for **confident** results that have a knowledge-base record.
- `ai_analysis` (Gemini) is only produced for confident results.
- Spraying advice is only given for a confident disease result.

### 12.2 Diagnoses

| Method & path | Purpose |
|---|---|
| `GET /diagnoses?decision_status=&plant_profile_id=&unassigned=` | Existing list endpoint with new filters (`date_to` is inclusive of the whole day) |
| `GET /diagnoses/compare?a=&b=` | Now returns `{a, b, comparison}`. `comparison.summary` is one of `visible_area_increased`, `visible_area_decreased`, `no_clear_change_in_measurement`, `change_cannot_be_established`. A different prediction is never presented as a health change. |
| `GET /diagnoses/{id}/notes` · `POST /diagnoses/{id}/notes` | Append-only notes: `user_note`, `treatment_applied`, `correction` (owner); `expert_feedback` (admin) |
| `POST /diagnoses/{id}/follow-up` | `{answers: {question_id: option \| [options]}}`, validated against the question catalogue. Returns the updated `differential`. Probabilities are unchanged. |
| `PUT /diagnoses/{id}/plant` | `{plant_profile_id \| null}`. Writes a `plant_link_change` audit note. |
| `GET /model/info` | Supported classes and plants, `has_healthy_class`, threshold provenance, whether segmentation is available, the follow-up question catalogue |
| `GET /media/{ref}?exp=&sig=` | Signed image delivery (HMAC-SHA256, expiring). Only `scans/`, `heatmaps/` and `segmentation/` references are valid. There is no public `/storage` path any more. |

### 12.3 Plants — `/plants`

| Method & path | Purpose |
|---|---|
| `POST /plants` | Create (`name` required; `crop_type`, `variety`, `planting_date`, `location_label`, `growing_environment`, `notes` optional) |
| `GET /plants?search=&include_archived=&last_status=&page=&page_size≤100` | List own plants with observation count and latest status |
| `GET /plants/{id}` · `PATCH /plants/{id}` · `DELETE /plants/{id}` | Read, update (including `archived: true/false`), archive (soft delete; observations kept) |
| `GET /plants/{id}/timeline?date_from=&date_to=&decision_status=&page=` | Observations oldest-first with notes, `measurement_series` (genuine segmentation measurements only), `measurement_series_note`, `observations_without_measurement` |
| `GET /plants/{id}/compare?a=&b=` | Comparison restricted to observations of this plant |

### 12.4 Assistant — `/assistant`

| Method & path | Purpose |
|---|---|
| `POST /assistant/chat` | `{message ≤ 2000, language: en\|ar, history ≤ 20 (last 6 used), diagnosis_id?, plant_profile_id?}` → `{mode: llm\|retrieval_only\|no_sources, answer, citations[], sources[], evidence_sufficient, recommends_expert, notices[], context_used}` |
| `GET /assistant/sources` · `GET /assistant/sources/{id}` | Active corpus documents with provenance |

### 12.5 Rate limits added

- `POST /assistant/chat`: 20 requests per 5 minutes per IP (app) and 10 per minute (nginx edge).
- 50 LLM-written answers per user per day (counted in the database).
