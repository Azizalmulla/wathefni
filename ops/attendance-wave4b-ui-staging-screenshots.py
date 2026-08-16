#!/usr/bin/env python3
"""Attendance Wave 4B — authenticated staging screenshots with seeded daily board.

Expects seed-and-prove-attendance-wave4b.py to have run (or seeds via import).
EN/AR × desktop/mobile; expands day detail; visits ops corrections.
No real ingest / devices / production deploy.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

PREFIX = "ATTW4BUI" + uuid.uuid4().hex[:6].upper()
COMPANY = "WATHEFNI"
OUT = pathlib.Path(os.environ.get("ATTW4B_UI_SHOTS") or f"/tmp/{PREFIX.lower()}-shots")
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("DASHBOARD_BASE") or "http://127.0.0.1:8011/dashboard"
API = os.environ.get("API_BASE") or "http://127.0.0.1:8011"
KUWAIT = ZoneInfo("Asia/Kuwait")
TODAY = (os.environ.get("ATTW4B_WORK_DATE") or datetime.now(KUWAIT).date().isoformat())


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


def wait_attendance(page) -> None:
    for sel in (
        "[data-testid='attendance-daily-table']",
        "[data-testid='attendance-page']",
        "[data-testid='attendance-ops']",
        "text=/AttW4B|Attendance operations|عمليات الحضور/i",
    ):
        try:
            page.wait_for_selector(sel, timeout=10000)
            return
        except Exception:  # noqa: BLE001
            continue
    page.wait_for_timeout(2000)


def main() -> int:
    import urllib.request

    for _ in range(90):
        try:
            with urllib.request.urlopen(f"{API}/health", timeout=2) as resp:
                if resp.status == 200:
                    break
        except Exception:  # noqa: BLE001
            time.sleep(1)
    else:
        print("HEALTH_TIMEOUT")
        return 2

    token = mint()
    st, att = http("GET", f"/dashboard/posthire/attendance?start_date={TODAY}&end_date={TODAY}&limit=200", token)
    rows = (att or {}).get("attendance") or [] if isinstance(att, dict) else []
    attw4b = [r for r in rows if "ATTW4B-" in str(r.get("employee_key") or "") or "AttW4B" in str(r.get("employee_name") or "")]
    st2, ops = http("GET", "/dashboard/attendance/ops/exceptions", token)
    notes = {
        "attendance_status": st,
        "attendance_rows": len(rows),
        "attw4b_rows": len(attw4b),
        "ops_status": st2,
        "ops_count": (ops or {}).get("count") if isinstance(ops, dict) else None,
        "ops_case_count": (ops or {}).get("case_count") if isinstance(ops, dict) else None,
        "work_date": TODAY,
    }
    (OUT / "seed-notes.json").write_text(json.dumps(notes, indent=2), encoding="utf-8")
    print("SEED_NOTES", json.dumps(notes))
    if len(attw4b) < 5:
        print("INSUFFICIENT_DAILY_BOARD_ROWS", notes)
        return 2

    # Capture connector seed (non-blocking)
    http("POST", "/dashboard/posthire/attendance/capture-ops/seed-synthetic", token, {"tag": PREFIX})

    viewports = {
        "desktop": {"width": 1440, "height": 900},
        "mobile": {"width": 390, "height": 844},
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for lang in ("en", "ar"):
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
                url = f"{BASE}/?page=attendance&lang={lang}&start_date={TODAY}&end_date={TODAY}"
                page.goto(url, wait_until="networkidle", timeout=120000)
                page.evaluate(
                    """({lang, start, end}) => {
                      document.documentElement.lang = lang;
                      document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
                      localStorage.setItem('wathefni_recruiting_locale', lang);
                      localStorage.setItem('wathefni_locale', lang);
                      // Force date range via UI inputs if present
                      const inputs = Array.from(document.querySelectorAll('input[type=date]'));
                      if (inputs[0]) {
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        setter.call(inputs[0], start);
                        inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
                        inputs[0].dispatchEvent(new Event('change', { bubbles: true }));
                      }
                      if (inputs[1]) {
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        setter.call(inputs[1], end);
                        inputs[1].dispatchEvent(new Event('input', { bubbles: true }));
                        inputs[1].dispatchEvent(new Event('change', { bubbles: true }));
                      }
                    }""",
                    {"lang": lang, "start": TODAY, "end": TODAY},
                )
                page.wait_for_timeout(1200)
                wait_attendance(page)
                shot(page, f"daily-board-{lang}-{device}")

                # Expand day detail
                for label in ("Day detail", "تفاصيل اليوم"):
                    try:
                        page.get_by_text(label, exact=False).first.click(timeout=2500)
                        page.wait_for_timeout(500)
                        shot(page, f"day-detail-{lang}-{device}")
                        break
                    except Exception:  # noqa: BLE001
                        pass

                for label in ("Attendance operations", "عمليات الحضور", "Exception queue", "طابور الاستثناءات"):
                    try:
                        page.get_by_text(label, exact=False).first.scroll_into_view_if_needed(timeout=2500)
                    except Exception:  # noqa: BLE001
                        pass
                shot(page, f"ops-queue-{lang}-{device}")

                for label in ("Corrections", "التصحيحات"):
                    try:
                        page.get_by_text(label, exact=True).first.click(timeout=2000)
                        page.wait_for_timeout(600)
                        shot(page, f"ops-corrections-{lang}-{device}")
                        break
                    except Exception:  # noqa: BLE001
                        pass

                for label in ("Disputes", "النزاعات"):
                    try:
                        page.get_by_text(label, exact=True).first.click(timeout=2000)
                        page.wait_for_timeout(400)
                        shot(page, f"ops-disputes-{lang}-{device}")
                        break
                    except Exception:  # noqa: BLE001
                        pass

                for label in ("Connector health", "صحة الموصلات"):
                    try:
                        page.get_by_text(label, exact=False).first.scroll_into_view_if_needed(timeout=2500)
                        page.wait_for_timeout(400)
                        shot(page, f"connector-health-{lang}-{device}")
                        break
                    except Exception:  # noqa: BLE001
                        pass
                context.close()
        browser.close()

    shots = sorted(p.name for p in OUT.glob("*.png"))
    board = [s for s in shots if s.startswith("daily-board-")]
    detail = [s for s in shots if s.startswith("day-detail-")]
    manifest = {
        "prefix": PREFIX,
        "company": COMPANY,
        "work_date": TODAY,
        "shots": shots,
        "authenticated": True,
        "fixture_screenshots": False,
        "attw4b_rows": len(attw4b),
        "ingest_enabled": False,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    if len(board) < 4:
        return 1
    if len(detail) < 2:
        print("WARN_DAY_DETAIL_SHOTS", len(detail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
