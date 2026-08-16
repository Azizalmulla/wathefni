#!/usr/bin/env python3
"""Shifts Wave 3A — staging UI screenshots (Calendar-aligned workspace).

Captures EN desktop + AR mobile RTL against staging dashboard-dist (:8011).
Does not mutate production. Synthetic seed is best-effort via API create when allowed.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import uuid
from datetime import date, timedelta
from typing import Any

from playwright.sync_api import sync_playwright

PREFIX = "SHW3AUI" + uuid.uuid4().hex[:6].upper()
COMPANY = "WATHEFNI"
OUT = pathlib.Path(os.environ.get("SHW3A_UI_SHOTS") or f"/tmp/{PREFIX.lower()}-shots")
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("DASHBOARD_BASE") or "http://127.0.0.1:8011/dashboard"
API = os.environ.get("API_BASE") or "http://127.0.0.1:8011"


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
        f"{API}{path}",
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
        localStorage.setItem('wathefni_recruiting_locale', {json.dumps(lang)});
        localStorage.setItem('wathefni_locale', {json.dumps(lang)});
        localStorage.setItem('i18nextLng', {json.dumps(lang)});
        document.documentElement.lang = {json.dumps(lang)};
        document.documentElement.dir = {json.dumps('rtl' if lang == 'ar' else 'ltr')};
        """
    )


def shot(page, name: str) -> None:
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print("SHOT", path)


def wait_shifts(page) -> None:
    for sel in (
        "[data-testid='shifts-workspace']",
        "[data-testid='shifts-board']",
        "text=/Shifts|الورديات/i",
    ):
        try:
            page.wait_for_selector(sel, timeout=10000)
            return
        except Exception:  # noqa: BLE001
            continue
    page.wait_for_timeout(2500)


def seed_shift(token: str) -> dict[str, Any]:
    day = (date.today() + timedelta(days=2)).isoformat()
    notes: dict[str, Any] = {"prefix": PREFIX, "day": day}
    # Prefer posthire action if route exists
    st, body = http(
        "POST",
        "/dashboard/posthire/actions",
        token,
        {
            "action_type": "create_shift_assignment",
            "args": {
                "employee_name": f"SHW2B-SYNTH| {PREFIX}",
                "employee_key": f"WATHEFNI-SHW2B-W3AUI-{PREFIX}",
                "employee_phone": f"965530{PREFIX[-5:]}",
                "shift_date": day,
                "start_time": "09:00",
                "end_time": "17:00",
                "reason": f"w3a ui shot {PREFIX}",
                "site_key": "W3A-UI",
            },
        },
    )
    notes["create"] = {"status": st, "ok": isinstance(body, dict) and (body.get("ok") or body.get("status") == "ok"), "body": body if isinstance(body, dict) else str(body)[:200]}
    st2, listing = http("GET", "/dashboard/posthire/shifts?week=0&limit=50", token)
    notes["list"] = {
        "status": st2,
        "wave3": (listing or {}).get("wave3") if isinstance(listing, dict) else None,
        "count": len((listing or {}).get("shifts") or []) if isinstance(listing, dict) else 0,
    }
    return notes


def main() -> int:
    token = mint()
    seed = seed_shift(token)
    (OUT / "seed.json").write_text(json.dumps(seed, indent=2, default=str))
    print("SEED", json.dumps(seed, default=str)[:500])

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # EN desktop — week roster board
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        page = context.new_page()
        inject_session(page, token, lang="en")
        page.goto(f"{BASE}/?page=shifts&lang=en", wait_until="networkidle", timeout=120000)
        wait_shifts(page)
        page.wait_for_timeout(1200)
        shot(page, "shifts-wave3a-desktop-board")
        # Open composer if button present
        try:
            page.click("[data-testid='shifts-add']", timeout=3000)
            page.wait_for_timeout(600)
            shot(page, "shifts-wave3a-desktop-composer")
        except Exception:  # noqa: BLE001
            print("composer_click_skipped")
        context.close()

        # AR mobile RTL — day agenda
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            locale="ar",
            is_mobile=True,
            has_touch=True,
        )
        page = context.new_page()
        inject_session(page, token, lang="ar")
        page.goto(f"{BASE}/?page=shifts&lang=ar", wait_until="networkidle", timeout=120000)
        wait_shifts(page)
        page.wait_for_timeout(1200)
        shot(page, "shifts-wave3a-mobile-rtl")
        context.close()
        browser.close()

    print("SHOTS_DIR", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
