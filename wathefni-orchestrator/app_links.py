"""HTTPS App Link / Universal Link destinations for Wathefni mobile.

Installed-app intercept happens on the device. These routes serve:
  * association documents (AASA / Digital Asset Links)
  * a registered destination map
  * browser fallback when the app is not installed
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

BUNDLE_ID = "ai.wathefni.employee"
LINK_HOST = "api.wathefni.ai"
CUSTOM_SCHEME = "wathefni"
STORE_IOS = "https://apps.apple.com/app/wathefni/id0000000000"
STORE_ANDROID = "https://play.google.com/store/apps/details?id=ai.wathefni.employee"

# Explicit production destinations. Keep in lockstep with employee APP_ROUTES
# plus HR workspace roots. Unknown slugs fail closed to Home fallback.
EMPLOYEE_DESTINATIONS: dict[str, dict[str, str]] = {
    "": {"app_path": "/", "module": "core", "surface": "employee"},
    "home": {"app_path": "/", "module": "core", "surface": "employee"},
    "inbox": {"app_path": "/notifications", "module": "core", "surface": "employee"},
    "notifications": {"app_path": "/notifications", "module": "core", "surface": "employee"},
    "profile": {"app_path": "/profile", "module": "core", "surface": "employee"},
    "settings": {"app_path": "/settings", "module": "core", "surface": "employee"},
    "leave": {"app_path": "/leave", "module": "leave", "surface": "employee"},
    "leave/request": {"app_path": "/leave/request", "module": "leave", "surface": "employee"},
    "leave/history": {"app_path": "/leave/history", "module": "leave", "surface": "employee"},
    "schedule": {"app_path": "/schedule", "module": "attendance", "surface": "employee"},
    "shifts": {"app_path": "/schedule", "module": "shifts", "surface": "employee"},
    "attendance": {"app_path": "/schedule", "module": "attendance", "surface": "employee"},
    "documents": {"app_path": "/documents", "module": "documents", "surface": "employee"},
    "onboarding": {"app_path": "/onboarding", "module": "onboarding", "surface": "employee"},
    "preboarding": {"app_path": "/preboarding", "module": "onboarding", "surface": "employee"},
    "probation": {"app_path": "/probation", "module": "onboarding", "surface": "employee"},
    "payslips": {"app_path": "/payslips", "module": "payroll", "surface": "employee"},
    "bank": {"app_path": "/bank", "module": "payroll", "surface": "employee"},
    "performance": {"app_path": "/performance", "module": "performance", "surface": "employee"},
    "talent": {"app_path": "/talent", "module": "talent", "surface": "employee"},
    "learning": {"app_path": "/learning", "module": "learning", "surface": "employee"},
    "benefits": {"app_path": "/benefits", "module": "benefits", "surface": "employee"},
    "engagement": {"app_path": "/engagement", "module": "engagement", "surface": "employee"},
}

HR_DESTINATIONS: dict[str, dict[str, str]] = {
    "": {"app_path": "/hr", "module": "core", "surface": "hr"},
    "inbox": {"app_path": "/hr/inbox", "module": "core", "surface": "hr"},
    "people": {"app_path": "/hr/people", "module": "employees", "surface": "hr"},
    "employees": {"app_path": "/hr/people", "module": "employees", "surface": "hr"},
    "leave": {"app_path": "/hr", "module": "leave", "surface": "hr"},
    "hiring": {"app_path": "/hr/hiring", "module": "recruiting", "surface": "hr"},
    "candidates": {"app_path": "/hr/candidates", "module": "recruiting", "surface": "hr"},
    "interviews": {"app_path": "/hr/interviews", "module": "recruiting", "surface": "hr"},
    "jobs": {"app_path": "/hr/jobs", "module": "recruiting", "surface": "hr"},
    "onboarding": {"app_path": "/hr/onboarding", "module": "onboarding", "surface": "hr"},
    "attendance": {"app_path": "/hr/attendance", "module": "attendance", "surface": "hr"},
    "shifts": {"app_path": "/hr/shifts", "module": "shifts", "surface": "hr"},
    "documents": {"app_path": "/hr/documents", "module": "documents", "surface": "hr"},
    "performance": {"app_path": "/hr/performance", "module": "performance", "surface": "hr"},
    "settings": {"app_path": "/hr/settings", "module": "setup", "surface": "hr"},
}

router = APIRouter()


def ios_app_id() -> str:
    return str(os.environ.get("WATHEFNI_IOS_APP_ID") or "").strip()


def android_sha256_certs() -> list[str]:
    raw = str(os.environ.get("WATHEFNI_ANDROID_SHA256_CERTS") or "").strip()
    return [part.strip().upper().replace(":", "") for part in raw.split(",") if part.strip()]


def registered_destinations() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for slug, meta in EMPLOYEE_DESTINATIONS.items():
        path = f"/l/{slug}" if slug else "/l"
        rows.append({"https": f"https://{LINK_HOST}{path}", "slug": slug or "home", **meta})
    for slug, meta in HR_DESTINATIONS.items():
        path = f"/l/hr/{slug}" if slug else "/l/hr"
        rows.append({"https": f"https://{LINK_HOST}{path}", "slug": f"hr/{slug}" if slug else "hr", **meta})
    return rows


def resolve_slug(parts: list[str]) -> dict[str, str] | None:
    if parts and parts[0] == "hr":
        slug = "/".join(parts[1:])
        return HR_DESTINATIONS.get(slug)
    slug = "/".join(parts)
    return EMPLOYEE_DESTINATIONS.get(slug)


def aasa_document() -> dict[str, Any]:
    app_id = ios_app_id()
    details = []
    if app_id:
        details.append({"appID": app_id, "paths": ["/l", "/l/*"]})
    return {"applinks": {"apps": [], "details": details}}


def assetlinks_document() -> list[dict[str, Any]]:
    fps = android_sha256_certs()
    if not fps:
        return []
    return [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": BUNDLE_ID,
                "sha256_cert_fingerprints": [
                    ":".join(fp[i : i + 2] for i in range(0, len(fp), 2)) if ":" not in fp else fp
                    for fp in fps
                ],
            },
        }
    ]


@router.get("/.well-known/apple-app-site-association")
@router.get("/apple-app-site-association")
def apple_app_site_association():
    return JSONResponse(aasa_document(), media_type="application/json")


@router.get("/.well-known/assetlinks.json")
def android_assetlinks():
    return JSONResponse(assetlinks_document(), media_type="application/json")


def _fallback_html(dest: dict[str, str] | None, *, missing: bool) -> str:
    title = "Open in OctoHR"
    if missing:
        title = "Link not found"
    app_path = (dest or {}).get("app_path") or "/"
    scheme = f"{CUSTOM_SCHEME}://{app_path.lstrip('/')}"
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
</head><body>
<h1>{title}</h1>
<p>If OctoHR is installed it should open automatically.</p>
<p><a href="{scheme}">Open the app</a></p>
<p><a href="{STORE_IOS}">App Store</a> · <a href="{STORE_ANDROID}">Google Play</a></p>
</body></html>"""


@router.get("/l/registry.json")
def https_app_link_registry():
    return {
        "host": LINK_HOST,
        "scheme": CUSTOM_SCHEME,
        "bundle_id": BUNDLE_ID,
        "destinations": registered_destinations(),
        "aasa_configured": bool(ios_app_id()),
        "assetlinks_configured": bool(android_sha256_certs()),
    }


@router.get("/l")
@router.get("/l/{path:path}")
def https_app_link(path: str = ""):
    parts = [p for p in str(path or "").split("/") if p]
    dest = resolve_slug(parts)
    if dest is None and parts:
        return HTMLResponse(_fallback_html(None, missing=True), status_code=404)
    resolved = dest or EMPLOYEE_DESTINATIONS[""]
    return HTMLResponse(_fallback_html(resolved, missing=False), status_code=200)
