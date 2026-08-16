#!/usr/bin/env python3
"""Prove rapid week navigation soft-keep on production Shifts."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

COMPANY = "WATHEFNI"
OUT = pathlib.Path(os.environ.get("SHIFTS_NAV_SHOTS") or "/tmp/shifts-nav-soft-keep")
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("DASHBOARD_BASE") or "http://127.0.0.1:8010/dashboard"
ORCH = os.environ.get("ORCH_PATH") or "/opt/wathefni/orchestrator"


def mint() -> str:
    sys.path.insert(0, ORCH)
    os.environ.setdefault("WATHEFNI_ENV", "production")
    os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
    os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
    os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")
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


def main() -> int:
    token = mint()
    events: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 980}, device_scale_factor=1)
        page.add_init_script(
            f"""
            localStorage.setItem('wathefni_dashboard_token', {json.dumps(token)});
            localStorage.setItem('wathefni_company_code', 'WATHEFNI');
            localStorage.setItem('wathefni_recruiting_locale', 'en');
            localStorage.setItem('wathefni_locale', 'en');
            """
        )
        page.goto(f"{BASE}/?page=shifts&lang=en", wait_until="networkidle", timeout=120000)
        page.wait_for_selector("[data-testid='shifts-workspace'][data-shifts-range-soft-keep]", timeout=45000)
        page.locator("[data-shifts-date-chrome] button", has_text="Week").first.click(timeout=3000)
        page.wait_for_timeout(400)
        # Land on a populated week first
        for _ in range(8):
            if page.locator("[data-testid='shift-block']").count() > 0:
                break
            page.locator("[data-shifts-date-chrome] button[aria-label='next']").click()
            page.wait_for_timeout(500)
        assert page.locator("[data-testid='shift-block']").count() > 0, "need populated starting week"
        page.screenshot(path=str(OUT / "01-start-populated.png"))
        start_blocks = page.locator("[data-testid='shift-block']").count()
        events.append({"step": "start", "blocks": start_blocks, "empty": page.locator("[data-shifts-empty]").count()})

        # Rapid next clicks — board must not blank between commits
        blank_during_nav = 0
        for i in range(1, 7):
            page.locator("[data-shifts-date-chrome] button[aria-label='next']").click()
            page.wait_for_timeout(120)
            blocks = page.locator("[data-testid='shift-block']").count()
            empty = page.locator("[data-shifts-empty]:visible").count()
            pending = page.get_attribute("[data-testid='shifts-board']", "data-shifts-range-pending")
            if blocks == 0 or empty > 0:
                blank_during_nav += 1
            page.screenshot(path=str(OUT / f"0{i + 1}-after-next-{i}.png"))
            events.append({"step": f"next-{i}", "blocks": blocks, "empty": empty, "pending": pending})

        # Settle
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "08-settled.png"))
        final_blocks = page.locator("[data-testid='shift-block']").count()
        events.append({"step": "settled", "blocks": final_blocks, "empty": page.locator("[data-shifts-empty]").count()})

        # Rapid prev back
        for i in range(1, 5):
            page.locator("[data-shifts-date-chrome] button[aria-label='prev']").click()
            page.wait_for_timeout(100)
            blocks = page.locator("[data-testid='shift-block']").count()
            empty = page.locator("[data-shifts-empty]:visible").count()
            if blocks == 0 or empty > 0:
                blank_during_nav += 1
            page.screenshot(path=str(OUT / f"09-prev-{i}.png"))
            events.append({"step": f"prev-{i}", "blocks": blocks, "empty": empty})

        page.wait_for_timeout(1200)
        page.screenshot(path=str(OUT / "10-final.png"))
        browser.close()

    report = {
        "blank_during_nav": blank_during_nav,
        "events": events,
        "soft_keep_ok": blank_during_nav == 0,
    }
    (OUT / "nav-race-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if blank_during_nav:
        raise SystemExit(f"BLANK_DURING_NAV {blank_during_nav}")
    print("NAV_SOFT_KEEP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
