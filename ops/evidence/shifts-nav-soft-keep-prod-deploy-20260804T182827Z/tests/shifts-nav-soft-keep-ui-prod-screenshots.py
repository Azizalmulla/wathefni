#!/usr/bin/env python3
"""Prove Shifts week/day navigation soft-keep + request-race integrity on production."""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time

from playwright.sync_api import Route, sync_playwright

COMPANY = "WATHEFNI"
OUT = pathlib.Path(os.environ.get("SHIFTS_NAV_SHOTS") or "/tmp/shifts-nav-soft-keep")
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("DASHBOARD_BASE") or "http://127.0.0.1:8010/dashboard"
ORCH = os.environ.get("ORCH_PATH") or "/opt/wathefni/orchestrator"
API_DELAY_MS = int(os.environ.get("SHIFTS_NAV_API_DELAY_MS") or "800")


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


def board_snapshot(page) -> dict:
    return {
        "blocks": page.locator("[data-testid='shift-block']").count(),
        "empty": page.locator("[data-shifts-empty]:visible").count(),
        "pending": page.get_attribute("[data-testid='shifts-board']", "data-shifts-range-pending"),
        "label": (page.locator("[data-shifts-range-label]").inner_text() or "").strip(),
        "soft_keep": page.locator("[data-testid='shifts-workspace'][data-shifts-range-soft-keep]").count(),
        "updating": page.locator("[data-shifts-updating]").count(),
        "board_h": page.locator("[data-testid='shifts-board']").bounding_box() or {},
    }


def main() -> int:
    token = mint()
    events: list[dict] = []
    soft_keep_blank = 0
    pending_seen = 0
    delayed_gets = 0

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
        for _ in range(10):
            if page.locator("[data-testid='shift-block']").count() > 0:
                break
            page.locator("[data-shifts-date-chrome] button[aria-label='next']").click()
            page.wait_for_timeout(450)

        start = board_snapshot(page)
        events.append({"phase": "A-start", **start})
        assert start["blocks"] > 0, "need populated starting week"
        assert start["soft_keep"] == 1
        page.screenshot(path=str(OUT / "01-start-populated.png"), full_page=False)
        held_blocks = start["blocks"]
        start_h = float((start.get("board_h") or {}).get("height") or 0)

        def delay_board_get(route: Route) -> None:
            nonlocal delayed_gets
            req = route.request
            url = req.url
            # Only delay the week board list GET, not nested resources.
            if req.method.upper() == "GET" and re.search(r"/dashboard/posthire/shifts(\\?|$)", url):
                if "/shifts/" in url.split("/dashboard/posthire/shifts", 1)[-1].split("?", 1)[0]:
                    route.continue_()
                    return
                delayed_gets += 1
                time.sleep(API_DELAY_MS / 1000.0)
            route.continue_()

        page.route(re.compile(r".*/dashboard/posthire/shifts.*"), delay_board_get)

        # Clear client week cache so the next navigations must hit the delayed network.
        page.locator("button[aria-label='Refresh'], button[aria-label='refresh']").first.click(timeout=3000)
        page.wait_for_timeout(200)
        refresh_mid = board_snapshot(page)
        events.append({"phase": "A-refresh-mid", **refresh_mid})
        # Same week refresh must soft-keep tiles (not cold-empty).
        if refresh_mid["blocks"] == 0 or refresh_mid["empty"] > 0:
            soft_keep_blank += 1
        page.wait_for_timeout(API_DELAY_MS + 400)
        after_refresh = board_snapshot(page)
        events.append({"phase": "A-after-refresh", **after_refresh})
        page.screenshot(path=str(OUT / "02-after-cache-clear.png"), full_page=False)
        held_blocks = after_refresh["blocks"]

        # Rapid next under delay: board must retain prior tiles while pending.
        for i in range(1, 7):
            page.locator("[data-shifts-date-chrome] button[aria-label='next']").click()
            page.wait_for_timeout(120)
            mid = board_snapshot(page)
            events.append({"phase": f"B-rapid-next-{i}", **mid})
            page.screenshot(path=str(OUT / f"{2 + i:02d}-rapid-next-{i}.png"), full_page=False)
            if mid["pending"] == "true":
                pending_seen += 1
                if mid["blocks"] != held_blocks or mid["empty"] > 0:
                    soft_keep_blank += 1
                mid_h = float((mid.get("board_h") or {}).get("height") or 0)
                if start_h and mid_h and abs(mid_h - start_h) > 120:
                    # Soft-kept board should not collapse while pending.
                    soft_keep_blank += 1

        # Settle — only the latest request may commit.
        page.wait_for_timeout(API_DELAY_MS * 4 + 1000)
        settled = board_snapshot(page)
        events.append({"phase": "B-settled", **settled})
        page.screenshot(path=str(OUT / "09-settled.png"), full_page=False)
        race_ok = settled["pending"] == "false" and settled["soft_keep"] == 1

        # Prev burst — still no pending blanks.
        held_blocks = settled["blocks"] if settled["blocks"] > 0 else held_blocks
        for i in range(1, 5):
            page.locator("[data-shifts-date-chrome] button[aria-label='prev']").click()
            page.wait_for_timeout(100)
            mid = board_snapshot(page)
            events.append({"phase": f"C-prev-{i}", **mid})
            page.screenshot(path=str(OUT / f"{9 + i:02d}-prev-{i}.png"), full_page=False)
            if mid["pending"] == "true":
                pending_seen += 1
                if mid["blocks"] == 0 or mid["empty"] > 0:
                    # If previous settled board was empty, soft-keep of empty is OK;
                    # only flag blanking when we were holding a populated board.
                    if held_blocks > 0:
                        soft_keep_blank += 1
                else:
                    # Populated soft-keep: tile count must stay until commit.
                    if mid["blocks"] != held_blocks and held_blocks > 0:
                        soft_keep_blank += 1

        page.wait_for_timeout(API_DELAY_MS * 3 + 800)
        end = board_snapshot(page)
        events.append({"phase": "C-end", **end})
        page.screenshot(path=str(OUT / "14-end.png"), full_page=False)
        browser.close()

    report = {
        "api_delay_ms": API_DELAY_MS,
        "delayed_gets": delayed_gets,
        "pending_seen": pending_seen,
        "soft_keep_blank": soft_keep_blank,
        "race_ok": race_ok,
        "events": events,
        "soft_keep_ok": soft_keep_blank == 0 and pending_seen > 0 and race_ok and delayed_gets > 0,
    }
    (OUT / "nav-race-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if soft_keep_blank:
        raise SystemExit(f"SOFT_KEEP_BLANK {soft_keep_blank}")
    if delayed_gets < 1:
        raise SystemExit("NO_DELAYED_GETS")
    if pending_seen < 1:
        raise SystemExit("PENDING_NEVER_OBSERVED")
    if not race_ok:
        raise SystemExit("RACE_SETTLE_FAILED")
    print("NAV_SOFT_KEEP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
