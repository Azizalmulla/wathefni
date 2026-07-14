"""
AI Recruiter by AI Octopus — LEGACY PROTOTYPE (quarantined).

This service is NOT the Wathefni dashboard AI Recruiter module.
Do not reuse its auth or /internal/* endpoints for Wathefni HR.
"""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.database import Base, engine
from app.routers import internal, webhook

# Create all tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Recruiter (legacy prototype — quarantined)",
    description="Legacy WhatsApp-native hiring prototype. Not Wathefni HR.",
    version="0.1.0-quarantined",
)


def _internal_routes_enabled() -> bool:
    return os.environ.get("LEGACY_AI_RECRUITER_INTERNAL_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def require_legacy_internal_token(
    authorization: str | None = Header(default=None),
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> dict:
    """Fail-closed gate for the legacy /internal surface."""
    expected = str(os.environ.get("LEGACY_AI_RECRUITER_INTERNAL_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "legacy_internal_not_configured",
                "message": "Legacy /internal routes are enabled but no internal token is configured.",
            },
        )
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    elif x_internal_token:
        provided = str(x_internal_token).strip()
    if not provided or provided != expected:
        raise HTTPException(
            status_code=401,
            detail={"error": "legacy_internal_auth_failed", "message": "Unauthorized."},
        )
    return {"ok": True, "legacy_internal": True}


@app.middleware("http")
async def quarantine_internal_routes(request: Request, call_next):
    if request.url.path.startswith("/internal") and not _internal_routes_enabled():
        return JSONResponse(
            status_code=404,
            content={
                "detail": {
                    "error": "legacy_internal_disabled",
                    "message": "Legacy /internal routes are disabled. This is not Wathefni HR.",
                }
            },
        )
    return await call_next(request)


# Mount public webhook only. /internal/* is opt-in and token-gated.
app.include_router(webhook.router)

if _internal_routes_enabled():
    app.include_router(internal.router, dependencies=[Depends(require_legacy_internal_token)])


@app.get("/")
def root():
    return {
        "name": "AI Recruiter (legacy prototype — quarantined)",
        "version": "0.1.0-quarantined",
        "status": "running",
        "wathefni_hr": False,
        "internal_routes_enabled": _internal_routes_enabled(),
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "legacy_prototype": True,
        "internal_routes_enabled": _internal_routes_enabled(),
    }
