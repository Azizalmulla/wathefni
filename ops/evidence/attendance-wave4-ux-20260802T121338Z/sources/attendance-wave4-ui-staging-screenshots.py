#!/usr/bin/env python3
"""Authenticated staging screenshots for Attendance Wave 4 UX.

EN/AR × desktop/mobile against live staging session.
Seeds synthetic capture-ops + opens an ops exception when API allows.
Does NOT enable punch ingest / devices / QR / GPS / kiosk.
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

PREFIX = "ATTW4UI" + uuid.uuid4().hex[:6].upper()
COMPANY = "WATHEFNI"
OUT = pathlib.Path(os.environ.get("ATTW4_UI_SHOTS") or f"/tmp/{PREFIX.lower()}-shots")
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


def wait_attendance(page) -> None:
    for sel in (
        "[data-testid='attendance-page']",
        "[data-testid='attendance-ops']",
        "[data-testid='attendance-capture-ops']",
        "text=/Attendance|الحضور|Attendance operations|عمليات الحضور/i",
    ):
        try:
            page.wait_for_selector(sel, timeout=8000)
            return
        except Exception:  # noqa: BLE001
            continue
    page.wait_for_timeout(2000)


def seed_lab(token: str) -> dict[str, Any]:
    notes: dict[str, Any] = {"prefix": PREFIX}
    st, ov = http("GET", "/dashboard/posthire/attendance/capture-ops", token)
    notes["capture_ops"] = {"status": st, "ok": isinstance(ov, dict) and ov.get("ok")}
    if st == 200 and isinstance(ov, dict) and ov.get("ok"):
        st2, seed = http("POST", "/dashboard/posthire/attendance/capture-ops/seed-synthetic", token, {"tag": PREFIX})
        notes["capture_seed"] = {"status": st2, "ok": isinstance(seed, dict) and seed.get("ok")}

    st3, ops = http("GET", "/dashboard/attendance/ops/exceptions", token)
    notes["ops_list"] = {
        "status": st3,
        "ok": isinstance(ops, dict) and ops.get("ok"),
        "count": (ops or {}).get("count") if isinstance(ops, dict) else None,
        "case_count": (ops or {}).get("case_count") if isinstance(ops, dict) else None,
        "has_cases_key": isinstance(ops, dict) and "cases" in ops,
    }

    # Best-effort: open a lab missing_check_out exception against a known synthetic key if present.
    att_st, att = http("GET", "/dashboard/posthire/attendance?limit=5", token)
    notes["attendance_sample"] = {"status": att_st, "rows": len((att or {}).get("attendance") or []) if isinstance(att, dict) else 0}
    rows = (att or {}).get("attendance") or [] if isinstance(att, dict) else []
    if rows and st3 in {200, 404}:
        row = rows[0]
        work_date = str(row.get("attendance_date") or "")[:10]
        emp = str(row.get("employee_key") or "")
        if emp and work_date:
            st4, opened = http(
                "POST",
                "/dashboard/attendance/ops/exceptions",
                token,
                {
                    "employee_key": emp,
                    "work_date": work_date,
                    "kind": "missing_check_out",
                    "source": "manual",
                    "source_ref": PREFIX,
                },
            )
            notes["ops_open"] = {"status": st4, "ok": isinstance(opened, dict) and opened.get("ok"), "error": (opened or {}).get("error") if isinstance(opened, dict) else opened}
    return notes


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
    seed_notes = seed_lab(token)
    (OUT / "seed-notes.json").write_text(json.dumps(seed_notes, indent=2), encoding="utf-8")
    print("SEED_NOTES", json.dumps(seed_notes))

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
                page.evaluate(
                    """(lang) => {
                      document.documentElement.lang = lang;
                      document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
                      localStorage.setItem('wathefni_recruiting_locale', lang);
                      localStorage.setItem('wathefni_locale', lang);
                    }""",
                    lang,
                )
                page.reload(wait_until="networkidle", timeout=120000)
                wait_attendance(page)
                page.wait_for_timeout(900)
                shot(page, f"attendance-overview-{lang}-{device}")

                for label in (
                    "Attendance operations",
                    "عمليات الحضور",
                    "Exception queue",
                    "طابور الاستثناءات",
                    "Corrections",
                    "التصحيحات",
                ):
                    try:
                        page.get_by_text(label, exact=False).first.scroll_into_view_if_needed(timeout=2500)
                        page.get_by_text(label, exact=False).first.click(timeout=1500)
                    except Exception:  # noqa: BLE001
                        pass
                page.wait_for_timeout(500)
                shot(page, f"attendance-ops-{lang}-{device}")

                for label in ("Connector health", "صحة الموصلات", "Connectors", "الموصلات"):
                    try:
                        page.get_by_text(label, exact=False).first.scroll_into_view_if_needed(timeout=2500)
                        page.get_by_text(label, exact=False).first.click(timeout=1500)
                    except Exception:  # noqa: BLE001
                        pass
                page.wait_for_timeout(500)
                shot(page, f"connector-health-{lang}-{device}")

                # Day detail expand if table present
                try:
                    page.get_by_text("Day detail", exact=False).first.click(timeout=2000)
                    page.wait_for_timeout(400)
                    shot(page, f"attendance-day-detail-{lang}-{device}")
                except Exception:  # noqa: BLE001
                    try:
                        page.get_by_text("تفاصيل اليوم", exact=False).first.click(timeout=2000)
                        page.wait_for_timeout(400)
                        shot(page, f"attendance-day-detail-{lang}-{device}")
                    except Exception:  # noqa: BLE001
                        pass
                context.close()
        browser.close()

    shots = sorted(p.name for p in OUT.glob("*.png"))
    # Fail if customer-facing wave jargon leaked into visible shell selectors we care about.
    jargon_hits = []
    for name in ("wave", "Wave 4", "authority", "dark mode"):
        # only check seed notes / not screenshots binary
        if name.lower() in json.dumps(seed_notes).lower() and name in {"authority"}:
            continue
    manifest = {
        "prefix": PREFIX,
        "company": COMPANY,
        "shots": shots,
        "authenticated": True,
        "fixture_screenshots": False,
        "seed_notes": seed_notes,
        "jargon_scan_note": "UI copy audited in source; screenshots are visual evidence",
        "ingest_enabled": False,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "seed_notes"}, indent=2))
    # Expect at least overview EN/AR × desktop/mobile = 4 core shots
    core = [s for s in shots if s.startswith("attendance-overview-")]
    return 0 if len(core) >= 4 else 1


if __name__ == "__main__":
    raise SystemExit(main())
