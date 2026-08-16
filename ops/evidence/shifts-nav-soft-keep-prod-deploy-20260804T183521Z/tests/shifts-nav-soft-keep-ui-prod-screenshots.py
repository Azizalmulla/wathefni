#!/usr/bin/env python3
"""Prove Shifts week/day navigation soft-keep + request-race integrity on production."""
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
API_DELAY_MS = int(os.environ.get("SHIFTS_NAV_API_DELAY_MS") or "900")


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
    board = page.locator("[data-testid='shifts-board']")
    box = board.bounding_box() or {}
    return {
        "blocks": page.locator("[data-testid='shift-block']").count(),
        "empty": page.locator("[data-shifts-empty]:visible").count(),
        "pending": board.get_attribute("data-shifts-range-pending"),
        "committed_week": board.get_attribute("data-shifts-committed-week"),
        "target_week": board.get_attribute("data-shifts-target-week"),
        "committed_anchor": board.get_attribute("data-shifts-committed-anchor"),
        "label": (page.locator("[data-shifts-range-label]").inner_text() or "").strip(),
        "soft_keep": page.locator("[data-testid='shifts-workspace'][data-shifts-range-soft-keep]").count(),
        "updating": page.locator("[data-shifts-updating]").count(),
        "board_h": box.get("height"),
    }


def install_fetch_delay(page, delay_ms: int) -> None:
    page.evaluate(
        """(delayMs) => {
          if (window.__wathefniShiftsFetchDelayInstalled) {
            window.__wathefniShiftsFetchDelayMs = delayMs;
            return;
          }
          window.__wathefniShiftsFetchDelayInstalled = true;
          window.__wathefniShiftsFetchDelayMs = delayMs;
          window.__wathefniShiftsDelayedGets = 0;
          const orig = window.fetch.bind(window);
          window.fetch = async (...args) => {
            const input = args[0];
            const url = typeof input === 'string' ? input : (input && input.url) || '';
            const method = (
              (args[1] && args[1].method) ||
              (typeof input !== 'string' && input && input.method) ||
              'GET'
            ).toUpperCase();
            if (method === 'GET' && /\\/dashboard\\/posthire\\/shifts(\\?|$)/.test(url)) {
              window.__wathefniShiftsDelayedGets += 1;
              await new Promise((resolve) => setTimeout(resolve, window.__wathefniShiftsFetchDelayMs || 0));
            }
            return orig(...args);
          };
        }""",
        delay_ms,
    )


def delayed_get_count(page) -> int:
    return int(page.evaluate("() => window.__wathefniShiftsDelayedGets || 0") or 0)


def sample_until(page, predicate, timeout_ms: int = 2000, interval_ms: int = 40):
    deadline = time.time() + timeout_ms / 1000.0
    last = board_snapshot(page)
    while time.time() < deadline:
        last = board_snapshot(page)
        if predicate(last):
            return last
        page.wait_for_timeout(interval_ms)
    return last


def main() -> int:
    token = mint()
    events: list[dict] = []
    soft_keep_blank = 0
    pending_seen = 0
    pending_frames: list[dict] = []

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
        page.wait_for_selector("[data-testid='shifts-board'][data-shifts-committed-week]", timeout=45000)
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
        assert start["committed_week"] not in (None, "")
        page.screenshot(path=str(OUT / "01-start-populated.png"), full_page=False)

        install_fetch_delay(page, API_DELAY_MS)

        # Clear client cache, then immediately race ahead of delayed fetches/prefetch.
        page.get_by_role("button", name="Refresh").click(timeout=3000)
        page.wait_for_timeout(80)
        refresh_mid = board_snapshot(page)
        events.append({"phase": "A-refresh-mid", **refresh_mid})
        if refresh_mid["blocks"] == 0 or refresh_mid["empty"] > 0:
            soft_keep_blank += 1
        page.screenshot(path=str(OUT / "02-refresh-soft-keep.png"), full_page=False)

        # Burst next clicks while delayed requests are still in flight.
        for i in range(1, 8):
            page.locator("[data-shifts-date-chrome] button[aria-label='next']").click()
            page.wait_for_timeout(45)

        # Capture soft-keep while the latest (far) week is still loading.
        pending = sample_until(page, lambda s: s["pending"] == "true", timeout_ms=API_DELAY_MS + 200)
        events.append({"phase": "B-pending-after-burst", **pending, "delayed_gets": delayed_get_count(page)})
        page.screenshot(path=str(OUT / "03-pending-after-burst.png"), full_page=False)
        if pending["pending"] == "true":
            pending_seen += 1
            pending_frames.append(pending)
            # Soft-keep: chrome target moved; committed board identity unchanged mid-flight.
            if pending["target_week"] == pending["committed_week"]:
                soft_keep_blank += 1
            if pending["updating"] < 1:
                soft_keep_blank += 1
            # Must not cold-blank: empty state with zero tiles while still pending is only
            # allowed when the soft-kept commit itself was already an empty week.
            if pending["empty"] > 0 and pending["blocks"] == 0:
                # If committed week is still the populated start week, this is a blank flash.
                if pending["committed_week"] == start["committed_week"] and start["blocks"] > 0:
                    soft_keep_blank += 1
            if (
                pending["committed_week"] == start["committed_week"]
                and start["blocks"] > 0
                and pending["blocks"] != start["blocks"]
            ):
                soft_keep_blank += 1
            # Chrome label must stay with the soft-kept board (no stale week mismatch).
            if start["label"] and pending["label"] and pending["committed_week"] == start["committed_week"]:
                if pending["label"] != start["label"]:
                    soft_keep_blank += 1
        else:
            # Fallback: poll a single next under delay after settle of burst.
            page.wait_for_timeout(API_DELAY_MS * 3)
            before = board_snapshot(page)
            page.locator("[data-shifts-date-chrome] button[aria-label='next']").click()
            pending = sample_until(page, lambda s: s["pending"] == "true", timeout_ms=API_DELAY_MS)
            events.append({"phase": "B-pending-single", **pending, "before": before})
            page.screenshot(path=str(OUT / "03b-pending-single.png"), full_page=False)
            if pending["pending"] != "true":
                raise SystemExit("PENDING_NEVER_OBSERVED")
            pending_seen += 1
            pending_frames.append(pending)
            if pending["blocks"] != before["blocks"] or pending["committed_week"] != before["committed_week"]:
                soft_keep_blank += 1
            if pending["empty"] > 0 and before["blocks"] > 0:
                soft_keep_blank += 1
            if pending["target_week"] == pending["committed_week"]:
                soft_keep_blank += 1

        page.wait_for_timeout(API_DELAY_MS * 5 + 1500)
        settled = board_snapshot(page)
        events.append({"phase": "B-settled", **settled, "delayed_gets": delayed_get_count(page)})
        page.screenshot(path=str(OUT / "04-settled.png"), full_page=False)
        race_ok = (
            settled["pending"] == "false"
            and settled["committed_week"] == settled["target_week"]
            and settled["committed_week"] not in (None, "")
        )

        # Rapid prev race under delay.
        before_prev = settled
        for i in range(1, 6):
            page.locator("[data-shifts-date-chrome] button[aria-label='prev']").click()
            page.wait_for_timeout(40)
        pending_prev = sample_until(page, lambda s: s["pending"] == "true", timeout_ms=API_DELAY_MS + 200)
        events.append({"phase": "C-pending-prev-burst", **pending_prev})
        page.screenshot(path=str(OUT / "05-pending-prev-burst.png"), full_page=False)
        if pending_prev["pending"] == "true":
            pending_seen += 1
            pending_frames.append(pending_prev)
            if pending_prev["committed_week"] != before_prev["committed_week"]:
                soft_keep_blank += 1
            if before_prev["blocks"] > 0 and (
                pending_prev["blocks"] != before_prev["blocks"] or pending_prev["empty"] > 0
            ):
                soft_keep_blank += 1
            if pending_prev["target_week"] == pending_prev["committed_week"]:
                soft_keep_blank += 1
        else:
            # Adjacent may be cached; force one uncached step with refresh+prev.
            page.get_by_role("button", name="Refresh").click(timeout=3000)
            page.wait_for_timeout(API_DELAY_MS + 400)
            before_prev = board_snapshot(page)
            page.locator("[data-shifts-date-chrome] button[aria-label='prev']").click()
            pending_prev = sample_until(page, lambda s: s["pending"] == "true", timeout_ms=API_DELAY_MS)
            events.append({"phase": "C-pending-prev-single", **pending_prev})
            page.screenshot(path=str(OUT / "05b-pending-prev-single.png"), full_page=False)
            if pending_prev["pending"] == "true":
                pending_seen += 1
                pending_frames.append(pending_prev)
                if pending_prev["blocks"] != before_prev["blocks"]:
                    soft_keep_blank += 1
                if pending_prev["target_week"] == pending_prev["committed_week"]:
                    soft_keep_blank += 1

        page.wait_for_timeout(API_DELAY_MS * 4 + 1200)
        end = board_snapshot(page)
        events.append({"phase": "C-end", **end, "delayed_gets": delayed_get_count(page)})
        page.screenshot(path=str(OUT / "06-end.png"), full_page=False)
        end_ok = end["pending"] == "false" and end["committed_week"] == end["target_week"]

        # Sequential frames for visual evidence of rapid next without blanking.
        page.locator("[data-shifts-date-chrome] button[aria-label='next']").click()
        page.wait_for_timeout(60)
        page.screenshot(path=str(OUT / "07-seq-1.png"), full_page=False)
        page.locator("[data-shifts-date-chrome] button[aria-label='next']").click()
        page.wait_for_timeout(60)
        page.screenshot(path=str(OUT / "08-seq-2.png"), full_page=False)
        page.locator("[data-shifts-date-chrome] button[aria-label='next']").click()
        page.wait_for_timeout(60)
        page.screenshot(path=str(OUT / "09-seq-3.png"), full_page=False)
        page.wait_for_timeout(API_DELAY_MS * 2 + 500)
        page.screenshot(path=str(OUT / "10-seq-settled.png"), full_page=False)

        browser.close()

    delayed_gets = 0
    for ev in events:
        if isinstance(ev.get("delayed_gets"), int):
            delayed_gets = max(delayed_gets, int(ev["delayed_gets"]))

    report = {
        "api_delay_ms": API_DELAY_MS,
        "delayed_gets": delayed_gets,
        "pending_seen": pending_seen,
        "soft_keep_blank": soft_keep_blank,
        "race_ok": race_ok and end_ok,
        "pending_frames": pending_frames,
        "events": events,
        "soft_keep_ok": soft_keep_blank == 0 and pending_seen > 0 and race_ok and end_ok and delayed_gets > 0,
    }
    (OUT / "nav-race-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if soft_keep_blank:
        raise SystemExit(f"SOFT_KEEP_BLANK {soft_keep_blank}")
    if delayed_gets < 1:
        raise SystemExit("NO_DELAYED_GETS")
    if pending_seen < 1:
        raise SystemExit("PENDING_NEVER_OBSERVED")
    if not (race_ok and end_ok):
        raise SystemExit("RACE_SETTLE_FAILED")
    print("NAV_SOFT_KEEP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
