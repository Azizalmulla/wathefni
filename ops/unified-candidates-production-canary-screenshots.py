#!/usr/bin/env python3
"""Capture production canary before/after UI screenshots (synthetic fixtures only).

Requires:
- Playwright Chromium
- Dashboard dist with Unified Candidates UI deployed to /var/www/wathefni-dashboard
- Canary tenant override ON for WATHEFNI (master OFF)
- Short-lived synthetic fixtures present (or seeded here)
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import uuid
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor

COMPANY = "WATHEFNI"
MARKER = "unified_candidates_prod_canary_ui_v1"
PREFIX = "UCCYUI" + uuid.uuid4().hex[:6].upper()
OUT = pathlib.Path(os.environ.get("CANARY_SHOTS") or "/tmp/uc-canary-shots")
BASE = os.environ.get("DASHBOARD_BASE") or "https://api.wathefni.ai/dashboard"


def db():
    vals: dict[str, str] = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return psycopg2.connect(vals["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor)


def mint() -> str:
    sys.path.insert(0, "/opt/wathefni/orchestrator")
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


def seed() -> dict[str, str]:
    keys = {
        "active": f"{PREFIX}-ACTIVE",
        "held": f"{PREFIX}-HELD",
    }
    phone = f"uccanary-{PREFIX.lower()}-ui"
    held_phone = f"imp-{PREFIX.lower()}-ui"
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, updated_at=now()
                """,
                (phone, "Canary UI Active Candidate", "canary.ui.active@example.invalid",
                 Json({"skills": ["Excel"]}), Json({"marker": MARKER, "synthetic": True})),
            )
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, updated_at=now()
                """,
                (held_phone, "Canary UI Held Candidate", "canary.ui.held@example.invalid",
                 Json({"skills": []}), Json({"marker": MARKER, "synthetic": True})),
            )
            cur.execute(
                """
                INSERT INTO applications(
                  company_code, app_key, phone, status, position_code, position_title,
                  cv_received, raw_json, ingested_at, updated_at
                ) VALUES
                (%s,%s,%s,'ready_for_review','UI_CANARY_JOB','Canary UI Job',true,%s::jsonb,now(),now()),
                (%s,%s,%s,'needs_role','','',true,%s::jsonb,now(),now())
                ON CONFLICT (app_key) DO UPDATE
                  SET status=EXCLUDED.status, raw_json=EXCLUDED.raw_json, updated_at=now()
                """,
                (
                    COMPANY, keys["active"], phone,
                    Json({"marker": MARKER, "intake": {"source": "whatsapp"}, "cv": {"processing": {"status": "ready"}}}),
                    COMPANY, keys["held"], held_phone,
                    Json({
                        "marker": MARKER,
                        "candidate_email": "canary.ui.held@example.invalid",
                        "intake": {"source": "email", "sender_email": "sender.ui@example.invalid"},
                        "cv": {"processing": {"status": "ready", "profile_parsed": True}},
                    }),
                ),
            )
        conn.commit()
    return keys

def cleanup(keys: dict[str, str]) -> None:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM applications WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%"))
            cur.execute(
                "DELETE FROM candidates WHERE phone LIKE %s OR phone LIKE %s",
                (f"uccanary-{PREFIX.lower()}%", f"imp-{PREFIX.lower()}%"),
            )
        conn.commit()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    token = mint()
    keys = seed()
    (OUT / "fixtures.json").write_text(json.dumps({"prefix": PREFIX, "keys": keys}, indent=2), encoding="utf-8")

    shots: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 960},
            ignore_https_errors=True,
        )
        page = context.new_page()
        page.add_init_script(
            f"""
            localStorage.setItem('wathefni_dashboard_token', {json.dumps(token)});
            localStorage.setItem('wathefni_company_code', {json.dumps(COMPANY)});
            localStorage.setItem('wathefni_dashboard_email', 'canary.owner@example.invalid');
            """
        )
        # Land on dashboard shell, then click Candidates nav (SPA does not deep-link pages).
        page.goto(f"{BASE}/", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2000)
        cand = page.get_by_role("button", name="Candidates")
        if cand.count() == 0:
            cand = page.get_by_text("Candidates", exact=True)
        if cand.count():
            cand.first.click()
            page.wait_for_timeout(2500)
        path = OUT / "after-unified-candidates-table.png"
        page.screenshot(path=str(path), full_page=True)
        shots.append({"name": "after-unified-candidates-table", "path": str(path)})

        # Talent pool filter if present
        for label in ["Talent Pool", "All", "Active applications"]:
            loc = page.get_by_text(label, exact=True)
            if loc.count():
                loc.first.click()
                page.wait_for_timeout(1200)
        path = OUT / "after-unified-candidates-filters.png"
        page.screenshot(path=str(path), full_page=True)
        shots.append({"name": "after-unified-candidates-filters", "path": str(path)})

        # Open held profile if visible
        held = page.get_by_text("Canary UI Held Candidate")
        if held.count():
            held.first.click()
            page.wait_for_timeout(2000)
            path = OUT / "after-held-governed-profile.png"
            page.screenshot(path=str(path), full_page=True)
            shots.append({"name": "after-held-governed-profile", "path": str(path)})

        # Intake operations
        intake = page.get_by_text("Intake Operations", exact=True)
        if intake.count():
            intake.first.click()
            page.wait_for_timeout(2000)
        path = OUT / "after-intake-operations.png"
        page.screenshot(path=str(path), full_page=True)
        shots.append({"name": "after-intake-operations", "path": str(path)})
        browser.close()

    cleanup(keys)
    (OUT / "INDEX.md").write_text(
        "# Production canary screenshots\n\n"
        + "\n".join(f"- `{s['name']}` → `{pathlib.Path(s['path']).name}`" for s in shots)
        + "\n",
        encoding="utf-8",
    )
    (OUT / "shots.json").write_text(json.dumps(shots, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "shots": shots, "out": str(OUT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
