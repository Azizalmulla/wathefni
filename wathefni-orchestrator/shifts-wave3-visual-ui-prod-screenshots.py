#!/usr/bin/env python3
"""Shifts Visual Wave 3 — production UI screenshots (EN/AR × desktop/mobile).

Read-only capture against live dashboard. Does not mutate scheduling data.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

COMPANY = "WATHEFNI"
OUT = pathlib.Path(os.environ.get("SHW3_UI_SHOTS") or "/tmp/shifts-wave3-shots")
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("DASHBOARD_BASE") or "http://127.0.0.1:8010/dashboard"
PHASE = os.environ.get("SHW3_SHOT_PHASE") or "after"
ORCH = os.environ.get("ORCH_PATH") or "/opt/wathefni/orchestrator"


def mint() -> str:
    sys.path.insert(0, ORCH)
    import production_data_safety as _r3_data_safety
    _r3_data_safety.require_explicit_environment()
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
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


def inject_session(page, token: str, *, lang: str) -> None:
    page.add_init_script(
        f"""
        localStorage.setItem('wathefni_dashboard_token', {json.dumps(token)});
        localStorage.setItem('wathefni_company_code', 'WATHEFNI');
        localStorage.setItem('wathefni_dashboard_email', 'wave3-shots@example.invalid');
        localStorage.setItem('wathefni_recruiting_locale', {json.dumps(lang)});
        localStorage.setItem('wathefni_locale', {json.dumps(lang)});
        localStorage.setItem('i18nextLng', {json.dumps(lang)});
        document.documentElement.lang = {json.dumps(lang)};
        document.documentElement.dir = {json.dumps('rtl' if lang == 'ar' else 'ltr')};
        """
    )


def shot(page, name: str) -> None:
    path = OUT / f"{PHASE}-{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print("SHOT", path)


def wait_shifts(page) -> None:
    page.wait_for_selector("[data-testid='shifts-workspace']", timeout=45000)
    page.wait_for_timeout(900)


def capture(browser, token: str, *, lang: str, mobile: bool) -> None:
    label = f"{'mobile' if mobile else 'desktop'}-{lang}"
    opts: dict = {
        "viewport": {"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900},
        "locale": "ar" if lang == "ar" else "en-US",
    }
    if mobile:
        opts["is_mobile"] = True
        opts["has_touch"] = True
    context = browser.new_context(**opts)
    page = context.new_page()
    inject_session(page, token, lang=lang)
    page.goto(f"{BASE}/?page=shifts&lang={lang}", wait_until="networkidle", timeout=120000)
    wait_shifts(page)
    # Prefer week on desktop for hero board
    if not mobile:
        try:
            page.locator("[data-shifts-date-chrome] button", has_text="Week").first.click(timeout=2500)
            page.wait_for_timeout(500)
        except Exception:  # noqa: BLE001
            try:
                page.locator("[data-shifts-date-chrome] button", has_text="أسبوع").first.click(timeout=2500)
                page.wait_for_timeout(500)
            except Exception:  # noqa: BLE001
                pass
    shot(page, f"schedule-{label}")
    # Requests surface (calmer)
    try:
        page.locator('button[data-surface="requests"]').first.click(timeout=4000)
        page.wait_for_timeout(700)
        shot(page, f"requests-{label}")
    except Exception as exc:  # noqa: BLE001
        print("requests_skip", label, exc)
    context.close()


def main() -> int:
    token = mint()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for lang in ("en", "ar"):
            for mobile in (False, True):
                capture(browser, token, lang=lang, mobile=mobile)
        browser.close()
    print("SHOTS_DIR", OUT)
    print("SHIFTS_WAVE3_SHOTS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
