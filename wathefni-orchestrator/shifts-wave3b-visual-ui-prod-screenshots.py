#!/usr/bin/env python3
"""Read-only Wave 3B production captures: EN/AR, desktop/mobile, board/drawer."""
from __future__ import annotations

import json
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

COMPANY = "WATHEFNI"
OUT = pathlib.Path(os.environ.get("SHW3B_UI_SHOTS") or "/tmp/shifts-wave3b-shots")
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("DASHBOARD_BASE") or "http://127.0.0.1:8010/dashboard"
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


def inject_session(page, token: str, lang: str) -> None:
    page.add_init_script(
        f"""
        localStorage.setItem('wathefni_dashboard_token', {json.dumps(token)});
        localStorage.setItem('wathefni_company_code', 'WATHEFNI');
        localStorage.setItem('wathefni_dashboard_email', 'wave3b-shots@example.invalid');
        localStorage.setItem('wathefni_recruiting_locale', {json.dumps(lang)});
        localStorage.setItem('wathefni_locale', {json.dumps(lang)});
        localStorage.setItem('i18nextLng', {json.dumps(lang)});
        document.documentElement.lang = {json.dumps(lang)};
        document.documentElement.dir = {json.dumps('rtl' if lang == 'ar' else 'ltr')};
        """
    )


def shot(page, name: str) -> None:
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print("SHOT", path)


def capture(browser, token: str, lang: str, mobile: bool) -> None:
    mode = "mobile" if mobile else "desktop"
    label = f"{mode}-{lang}"
    options: dict = {
        "viewport": {"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900},
        "locale": "ar" if lang == "ar" else "en-US",
    }
    if mobile:
        options["is_mobile"] = True
        options["has_touch"] = True
    context = browser.new_context(**options)
    page = context.new_page()
    inject_session(page, token, lang)
    page.goto(f"{BASE}/?page=shifts&lang={lang}", wait_until="networkidle", timeout=120000)
    page.wait_for_selector("[data-testid='shifts-workspace'][data-shifts-visual-wave3b]", timeout=45000)
    page.wait_for_timeout(900)

    if not mobile:
        week = "أسبوع" if lang == "ar" else "Week"
        try:
            page.locator("[data-shifts-date-chrome] button", has_text=week).first.click(timeout=3000)
            page.wait_for_timeout(500)
        except Exception:  # noqa: BLE001
            pass
    shot(page, f"schedule-{label}")

    page.locator("[data-testid='shifts-add']").click(timeout=5000)
    page.wait_for_selector("[data-shifts-aside-sheet]", timeout=5000)
    page.wait_for_timeout(300)
    shot(page, f"create-drawer-{label}")
    page.locator("[data-testid='shifts-aside'] button[aria-label]").first.click(timeout=3000)
    page.wait_for_timeout(250)

    page.locator('button[data-surface="requests"]').first.click(timeout=4000)
    page.wait_for_timeout(600)
    shot(page, f"requests-{label}")
    context.close()


def main() -> int:
    token = mint()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for lang in ("en", "ar"):
            for mobile in (False, True):
                capture(browser, token, lang, mobile)
        browser.close()
    print("SHOTS_DIR", OUT)
    print("SHIFTS_WAVE3B_SHOTS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

