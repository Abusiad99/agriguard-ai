"""
API v1 router aggregator. All routers are mounted under `settings.api_prefix`
(`/api/v1`) here — API versioning (requirement #23) is achieved by this single prefix
point: a future `/api/v2` would be a sibling module assembled the same way in
main.py, without touching v1's routes.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.interface.api.v1.admin_router import router as admin_router
from app.interface.api.v1.auth_router import router as auth_router
from app.interface.api.v1.dashboard_router import router as dashboard_router
from app.interface.api.v1.diseases_router import router as diseases_router
from app.interface.api.v1.reports_router import router as reports_router
from app.interface.api.v1.scans_router import router as scans_router
from app.interface.api.v1.treatments_router import router as treatments_router
from app.interface.api.v1.weather_router import router as weather_router

# Note: health_router is intentionally NOT included here. Per the API spec
# (docs/02-system-design/13-api-specification.md §9), GET /health is a public,
# top-level endpoint (not versioned under /api/v1), since orchestration liveness/
# readiness probes should not need to track API version changes. It is mounted
# directly on the app in main.py.
api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(scans_router)
api_v1_router.include_router(reports_router)
api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(diseases_router)
api_v1_router.include_router(treatments_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(weather_router)
