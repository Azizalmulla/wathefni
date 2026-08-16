#!/usr/bin/env python3
"""Authenticated production screenshots for Attendance final UX promote.

EN/AR × desktop/mobile on :8010. Seeds synthetic daily board via seed-and-prove
(if ATTW_FINAL_SEED=1) or expects recent canary residues cleaned — prefer calling
after a dedicated seed that leaves rows for the shot window, then cleanup.

Default: run lightweight HTTP seed via importing seed script with short-lived tag
written to OUT/seed-tag.txt for post-shot cleanup by canary.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

PREFIX = "ATTWFINUI" + uuid.uuid4().hex[:6].upper()
COMPANY = "WATHEFNI"
OUT = pathlib.Path(os.environ.get("ATTW_FINAL_UI_SHOTS") or f"/tmp/{PREFIX.lower()}-shots")
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("DASHBOARD_BASE") or "http://127.0.0.1:8010/dashboard"
API = os.environ.get("API_BASE") or "http://127.0.0.1:8010"
KUWAIT = ZoneInfo("Asia/Kuwait")
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
        localStorage.setItem('wathefni_dashboard_email', 'prod-owner@example.invalid');
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

    # Seed board for screenshots (leave rows until cleanup by qualify)
    seed_dir = OUT / "seed"
    seed_dir.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "ATTW4B_EVID": str(seed_dir),
            "ATTW4B_USE_APP": "1",
            "ATTW4B_COMPANY": "WATHEFNI",
            "WATHEFNI_ENV": "production",
            "WATHEFNI_POSTGRES_ENV": "/root/.openclaw/secrets/postgres.env",
            "WATHEFNI_WORKSPACE": "/root/.openclaw/workspaces/company-wathefni",
            "WATHEFNI_EXPECTED_DATABASE_NAME": "wathefni",
            "WATHEFNI_DATABASE_ENVIRONMENT_MARKER": "wathefni-production-isolation-v1",
        }
    )
    py = os.environ.get("ORCH_PYTHON") or f"{ORCH}/.venv/bin/python"
    subprocess.run([py, f"{ORCH}/seed-and-prove-attendance-wave4b.py"], cwd=ORCH, env=env, check=False)
    summary = {}
    if (seed_dir / "summary.json").exists():
        summary = json.loads((seed_dir / "summary.json").read_text())
    work_date = summary.get("work_date") or datetime.now(KUWAIT).date().isoformat()
    tag = summary.get("tag") or ""
    (OUT / "seed-tag.txt").write_text(f"{tag}\n{work_date}\n", encoding="utf-8")

    token = mint()
    st, att = http("GET", f"/dashboard/posthire/attendance?start_date={work_date}&end_date={work_date}&limit=200", token)
    rows = [r for r in ((att or {}).get("attendance") or []) if "ATTW4B-" in str(r.get("employee_key") or "")]
    notes = {"attendance_status": st, "attw4b_rows": len(rows), "work_date": work_date, "tag": tag}
    (OUT / "seed-notes.json").write_text(json.dumps(notes, indent=2), encoding="utf-8")
    print("SEED_NOTES", json.dumps(notes))
    if len(rows) < 5:
        print("INSUFFICIENT_ROWS", notes)
        return 2

    http("POST", "/dashboard/posthire/attendance/capture-ops/seed-synthetic", token, {"tag": PREFIX})

    viewports = {"desktop": {"width": 1440, "height": 900}, "mobile": {"width": 390, "height": 844}}
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
                page.goto(f"{BASE}/?page=attendance&lang={lang}", wait_until="networkidle", timeout=120000)
                page.evaluate(
                    """(lang) => {
                      document.documentElement.lang = lang;
                      document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
                      localStorage.setItem('wathefni_recruiting_locale', lang);
                    }""",
                    lang,
                )
                page.wait_for_timeout(1500)
                shot(page, f"daily-board-{lang}-{device}")
                for label in ("Day detail", "تفاصيل اليوم"):
                    try:
                        page.get_by_text(label, exact=False).first.click(timeout=2500)
                        page.wait_for_timeout(400)
                        shot(page, f"day-detail-{lang}-{device}")
                        break
                    except Exception:
                        pass
                for label in ("Attendance operations", "عمليات الحضور"):
                    try:
                        page.get_by_text(label, exact=False).first.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                shot(page, f"ops-{lang}-{device}")
                for label in ("Connector health", "صحة الموصلات"):
                    try:
                        page.get_by_text(label, exact=False).first.scroll_into_view_if_needed(timeout=2000)
                        page.wait_for_timeout(300)
                        shot(page, f"connector-{lang}-{device}")
                        break
                    except Exception:
                        pass
                context.close()
        browser.close()

    shots = sorted(p.name for p in OUT.glob("*.png"))
    manifest = {
        "prefix": PREFIX,
        "company": COMPANY,
        "work_date": work_date,
        "tag": tag,
        "shots": shots,
        "authenticated": True,
        "attw4b_rows": len(rows),
        "ingest_enabled": False,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0 if len([s for s in shots if s.startswith("daily-board-")]) >= 4 else 1


if __name__ == "__main__":
    raise SystemExit(main())
