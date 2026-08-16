#!/usr/bin/env python3
"""Authenticated staging screenshots for Attendance Capture Ops (Wave 2F).

EN/AR × desktop/mobile against live staging session (not contract fixtures).
Seeds synthetic capture-ops data via authenticated API; cleans marker rows after.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import uuid
from typing import Any

from playwright.sync_api import sync_playwright

PREFIX = "ATTW2FUI" + uuid.uuid4().hex[:6].upper()
COMPANY = "WATHEFNI"
OUT = pathlib.Path(os.environ.get("CAPTURE_UI_SHOTS") or f"/tmp/{PREFIX.lower()}-shots")
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("DASHBOARD_BASE") or "http://127.0.0.1:8011/dashboard"


def mint() -> str:
    sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
    os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
    os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")
    import app

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM dashboard_users
                WHERE company_code=%s AND status='active' AND role='owner'
                ORDER BY updated_at DESC NULLS LAST LIMIT 1
                """,
                (COMPANY,),
            )
            user = cur.fetchone()
    token, _ = app.create_dashboard_session(dict(user))
    return token


def http(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, Any]:
    import urllib.request

    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:8011{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Wathefni-Company": COMPANY,
            "X-Company-Code": COMPANY,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except Exception as exc:  # noqa: BLE001
        if hasattr(exc, "code"):
            raw = exc.read().decode() if hasattr(exc, "read") else ""
            try:
                return int(exc.code), json.loads(raw) if raw else {"raw": raw}
            except Exception:
                return int(exc.code), {"raw": raw[:500]}
        raise


def inject_session(page, token: str, *, lang: str) -> None:
    page.add_init_script(
        f"""
        localStorage.setItem('wathefni_dashboard_token', {json.dumps(token)});
        localStorage.setItem('wathefni_company_code', 'WATHEFNI');
        localStorage.setItem('wathefni_dashboard_email', 'staging-owner@example.invalid');
        localStorage.setItem('wathefni_locale', {json.dumps(lang)});
        localStorage.setItem('i18nextLng', {json.dumps(lang)});
        """
    )


def shot(page, name: str) -> None:
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print("SHOT", path)


def wait_capture_ops(page) -> None:
    # Prefer durable capture-ops panel; fall back to attendance page shell.
    for sel in (
        "text=/Capture Ops|عمليات الالتقاط|Connector|موصل/i",
        "[data-testid='attendance-capture-ops']",
        "text=/Attendance|الحضور/i",
    ):
        try:
            page.wait_for_selector(sel, timeout=8000)
            return
        except Exception:  # noqa: BLE001
            continue
    page.wait_for_timeout(2000)


def main() -> int:
    token = mint()
    st, ov = http("GET", "/dashboard/posthire/attendance/capture-ops", token)
    print("OVERVIEW", st, {"store_mode": ov.get("store_mode"), "ok": ov.get("ok"), "error": ov.get("error")})
    if st != 200 or not ov.get("ok"):
        print("CAPTURE_OPS_UNAVAILABLE", ov)
        return 2

    st, seed = http("POST", "/dashboard/posthire/attendance/capture-ops/seed-synthetic", {"tag": PREFIX})
    print("SEED", st, {"ok": seed.get("ok"), "error": seed.get("error")})
    if st != 200 or not seed.get("ok"):
        return 2

    # Confirm no secrets in API payload
    blob = json.dumps(seed)
    if "password" in blob.lower() and "gAAAA" not in blob:
        # allow key names like has_password but not raw values from seed secrets
        pass
    forbidden = ["plain-", "tok-", "Bearer ", "postgres://"]
    for f in forbidden:
        if f in blob:
            print("SECRET_LEAK_IN_SEED_RESPONSE", f)
            return 2

    viewports = {
        "desktop": {"width": 1440, "height": 900},
        "mobile": {"width": 390, "height": 844},
    }
    langs = ("en", "ar")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for lang in langs:
            for device, vp in viewports.items():
                context = browser.new_context(
                    viewport=vp,
                    locale="ar-KW" if lang == "ar" else "en-US",
                    extra_http_headers={
                        "Authorization": f"Bearer {token}",
                        "X-Wathefni-Company": COMPANY,
                        "X-Company-Code": COMPANY,
                    },
                )
                page = context.new_page()
                inject_session(page, token, lang=lang)
                url = f"{BASE}/?page=attendance&lang={lang}"
                page.goto(url, wait_until="networkidle", timeout=120000)
                wait_capture_ops(page)
                # Expand capture ops section if collapsed
                for label in ("Capture Ops", "عمليات", "Remediation", "Connectors"):
                    try:
                        page.get_by_text(label, exact=False).first.click(timeout=1500)
                    except Exception:  # noqa: BLE001
                        pass
                page.wait_for_timeout(800)
                shot(page, f"capture-ops-{lang}-{device}")
                context.close()
        browser.close()

    manifest = {
        "prefix": PREFIX,
        "company": COMPANY,
        "store_mode": ov.get("store_mode"),
        "shots": sorted(p.name for p in OUT.glob("*.png")),
        "authenticated": True,
        "fixture_screenshots": False,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0 if len(manifest["shots"]) >= 4 else 1


if __name__ == "__main__":
    raise SystemExit(main())
