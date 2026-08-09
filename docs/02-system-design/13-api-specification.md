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
