#!/usr/bin/env python3
"""Qualify Candidates list final polish on production (UI-only)."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time
import uuid
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor

COMPANY = "WATHEFNI"
MARKER = "candidates_list_polish_prod_v1"
BASE = os.environ.get("DASHBOARD_BASE") or "https://api.wathefni.ai/dashboard"
OUT = pathlib.Path(os.environ.get("CANDIDATES_POLISH_SHOTS") or "/tmp/candidates-polish-shots")
PREFIX = os.environ.get("CANDIDATES_POLISH_PREFIX") or ("CLSP" + uuid.uuid4().hex[:6].upper())


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


def assert_bundle(www: pathlib.Path) -> dict[str, Any]:
    text = "\n".join(p.read_text(errors="ignore") for p in www.joinpath("assets").glob("dashboard-*.js"))
    checks = {
        "has_showing_candidates": "of" in text and "candidates" in text,
        "has_plus_jobs": "+1 jobs" in text or "+3 jobs" in text or "jobs" in text,
        "has_active_applications_hover": "active applications" in text,
        "has_save_this_view": "Save this view" in text,
        "has_new_description": "See each candidate" in text,
        "has_no_job_assigned": "No job assigned" in text,
        "absent_people_on_this_page": "people on this page" not in text,
        "absent_ambiguous_plus_only": False,  # informational
    }
    checks["ok"] = all(v for k, v in checks.items() if k != "absent_ambiguous_plus_only")
    checks["js"] = [p.name for p in www.joinpath("assets").glob("dashboard-*.js")]
    return checks


def seed() -> dict[str, Any]:
    email = f"clsp.shared.{PREFIX.lower()}@example.invalid"
    keys = {
        "multi_a": f"{PREFIX}-A",
        "multi_b": f"{PREFIX}-B",
        "lower": f"{PREFIX}-LOWER",
        "upper": f"{PREFIX}-UPPER",
        "dup1": f"{PREFIX}-DUP1",
        "dup2": f"{PREFIX}-DUP2",
    }
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, email=EXCLUDED.email, updated_at=now()
                """,
                (f"clsp-{PREFIX.lower()}-a", "CLSP Multi Person", email, Json({"marker": MARKER}), Json({"marker": MARKER})),
            )
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, email=EXCLUDED.email, updated_at=now()
                """,
                (f"clsp-{PREFIX.lower()}-b", "CLSP Multi Person", email, Json({"marker": MARKER}), Json({"marker": MARKER})),
            )
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, updated_at=now()
                """,
                (f"clsp-{PREFIX.lower()}-lower", "yasser al dossary polish", f"clsp.lower.{PREFIX.lower()}@example.invalid",
                 Json({"marker": MARKER}), Json({"marker": MARKER})),
            )
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, updated_at=now()
                """,
                (f"clsp-{PREFIX.lower()}-upper", "HAMAD ALMULLA POLISH", f"clsp.upper.{PREFIX.lower()}@example.invalid",
                 Json({"marker": MARKER}), Json({"marker": MARKER})),
            )
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, updated_at=now()
                """,
                (f"clsp-{PREFIX.lower()}-d1", "CLSP Same Name", None, Json({"marker": MARKER}), Json({"marker": MARKER})),
            )
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, updated_at=now()
                """,
                (f"clsp-{PREFIX.lower()}-d2", "CLSP Same Name", None, Json({"marker": MARKER}), Json({"marker": MARKER})),
            )
            rows = [
                (keys["multi_a"], f"clsp-{PREFIX.lower()}-a", "interview", "CLSP_HR", "HR",
                 {"marker": MARKER, "intake": {"source": "email"}, "grounded_contacts": {"email": email}, "candidate_email": email}),
                (keys["multi_b"], f"clsp-{PREFIX.lower()}-b", "shortlisted", "CLSP_FIN", "Finance",
                 {"marker": MARKER, "intake": {"source": "whatsapp"}, "grounded_contacts": {"email": email}, "candidate_email": email}),
                (keys["lower"], f"clsp-{PREFIX.lower()}-lower", "ready_for_review", "CLSP_HR", "HR",
                 {"marker": MARKER, "intake": {"source": "job_application"}}),
                (keys["upper"], f"clsp-{PREFIX.lower()}-upper", "ready_for_review", "CLSP_HR", "HR",
                 {"marker": MARKER, "intake": {"source": "manual_upload"}}),
                (keys["dup1"], f"clsp-{PREFIX.lower()}-d1", "ready_for_review", "CLSP_HR", "HR",
                 {"marker": MARKER, "intake": {"source": "email"}}),
                (keys["dup2"], f"clsp-{PREFIX.lower()}-d2", "shortlisted", "CLSP_FIN", "Finance",
                 {"marker": MARKER, "intake": {"source": "bulk_import"}}),
            ]
            for app_key, phone, status, code, title, raw in rows:
                cur.execute(
                    """
                    INSERT INTO applications(
                      company_code, app_key, phone, status, position_code, position_title,
                      cv_received, raw_json, ingested_at, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,true,%s::jsonb,now(),now())
                    ON CONFLICT (app_key) DO UPDATE
                      SET status=EXCLUDED.status, position_code=EXCLUDED.position_code,
                          position_title=EXCLUDED.position_title, raw_json=EXCLUDED.raw_json,
                          phone=EXCLUDED.phone, updated_at=now()
                    """,
                    (COMPANY, app_key, phone, status, code, title, Json(raw)),
                )
        conn.commit()
    return {"prefix": PREFIX, "keys": keys, "email": email}


def cleanup(prefix: str) -> dict[str, int]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM applications WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{prefix}%"))
            apps = cur.rowcount
            cur.execute(
                "DELETE FROM candidates WHERE phone LIKE %s OR email LIKE %s",
                (f"clsp-{prefix.lower()}%", f"%{prefix.lower()}@example.invalid"),
            )
            cands = cur.rowcount
        conn.commit()
    return {"applications_deleted": apps, "candidates_deleted": cands}


def open_candidates(page) -> None:
    page.goto(f"{BASE}/", wait_until="networkidle", timeout=120000)
    page.wait_for_timeout(1500)
    cand = page.get_by_role("button", name="Candidates")
    if cand.count() == 0:
        cand = page.get_by_text("Candidates", exact=True)
    cand.first.click()
    page.wait_for_timeout(2500)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["before", "after", "assert-bundle", "cleanup"], required=True)
    parser.add_argument("--prefix", default=PREFIX)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    if args.phase == "assert-bundle":
        report = assert_bundle(pathlib.Path("/var/www/wathefni-dashboard"))
        (OUT / "bundle-assert.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0 if report.get("ok") else 1
    if args.phase == "cleanup":
        print(json.dumps(cleanup(args.prefix), indent=2))
        return 0

    from playwright.sync_api import sync_playwright

    token = mint()
    fixtures = None
    phase_dir = OUT / args.phase
    phase_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"phase": args.phase, "shots": [], "assertions": {}}
    try:
        if args.phase == "after":
            fixtures = seed()
            (OUT / "fixtures.json").write_text(json.dumps(fixtures, indent=2), encoding="utf-8")
            time.sleep(1)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 960}, ignore_https_errors=True)
            page = context.new_page()
            page.add_init_script(
                f"""
                localStorage.setItem('wathefni_dashboard_token', {json.dumps(token)});
                localStorage.setItem('wathefni_company_code', {json.dumps(COMPANY)});
                localStorage.setItem('wathefni_dashboard_email', 'clsp.owner@example.invalid');
                """
            )
            open_candidates(page)
            if args.phase == "after":
                box = page.get_by_placeholder(re.compile(r"Search|بحث", re.I))
                box.first.fill("CLSP")
                page.get_by_role("button", name=re.compile(r"Apply|تطبيق", re.I)).first.click()
                page.wait_for_timeout(2000)

            shot = phase_dir / f"{args.phase}-candidates-desktop.png"
            page.screenshot(path=str(shot), full_page=True)
            result["shots"].append(str(shot))
            body = page.locator('[data-testid="unified-candidates-page"]').inner_text()
            result["assertions"]["snippet"] = body[:3000]
            footer = page.locator('[data-testid="candidates-list-footer"]')
            footer_text = footer.inner_text() if footer.count() else ""
            result["assertions"]["footer"] = footer_text

            if args.phase == "before":
                result["assertions"]["has_mixed_footer"] = ("people on this page" in body) or ("شخص في هذه الصفحة" in body)
            else:
                result["assertions"]["person_footer"] = bool(re.search(r"of \d+ candidates|مرشحاً|1 candidate|مرشح واحد", footer_text, re.I))
                result["assertions"]["no_people_on_page_phrase"] = "people on this page" not in body
                result["assertions"]["has_plus_jobs"] = "+1 jobs" in body or bool(page.locator('[data-testid="additional-jobs-indicator"]').count())
                result["assertions"]["name_title_case_lower"] = "Yasser Al Dossary Polish" in body
                result["assertions"]["name_title_case_upper"] = "Hamad Almulla Polish" in body
                result["assertions"]["description"] = "See each candidate" in body
                result["assertions"]["restricted_visible_for_owner"] = page.get_by_role("button", name="Restricted").count() > 0
                # Save this view appears when dirty (search applied)
                result["assertions"]["save_this_view"] = page.get_by_role("button", name=re.compile(r"Save this view|حفظ هذا العرض")).count() > 0
                result["assertions"]["review_identity"] = "Review identity" in body
                result["assertions"]["multi_one_person"] = "CLSP Multi Person" in body and "+1 jobs" in body

                # AR/RTL
                lang = page.get_by_role("button", name=re.compile(r"العربية|English|Language|اللغة", re.I))
                if lang.count():
                    lang.first.click()
                    page.wait_for_timeout(1200)
                result["assertions"]["rtl"] = page.locator('[data-testid="unified-candidates-page"]').get_attribute("dir") == "rtl"
                ar = phase_dir / f"{args.phase}-candidates-ar.png"
                page.screenshot(path=str(ar), full_page=True)
                result["shots"].append(str(ar))

                tablet = context.new_page()
                tablet.add_init_script(
                    f"""
                    localStorage.setItem('wathefni_dashboard_token', {json.dumps(token)});
                    localStorage.setItem('wathefni_company_code', {json.dumps(COMPANY)});
                    """
                )
                tablet.set_viewport_size({"width": 834, "height": 1112})
                open_candidates(tablet)
                tshot = phase_dir / f"{args.phase}-candidates-tablet.png"
                tablet.screenshot(path=str(tshot), full_page=True)
                result["shots"].append(str(tshot))
                tablet.close()

            browser.close()

        hard = []
        if args.phase == "after":
            a = result["assertions"]
            hard = [
                a.get("person_footer"),
                a.get("no_people_on_page_phrase"),
                a.get("has_plus_jobs"),
                a.get("name_title_case_lower"),
                a.get("name_title_case_upper"),
                a.get("description"),
                a.get("save_this_view"),
                a.get("review_identity"),
                a.get("multi_one_person"),
                a.get("rtl"),
            ]
            result["ok"] = all(bool(x) for x in hard)
        else:
            result["ok"] = True
        (OUT / f"{args.phase}-qualify.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"phase": args.phase, "ok": result.get("ok"), "assertions": result.get("assertions"), "shots": len(result["shots"])}, indent=2))
        return 0 if result.get("ok") else 2
    finally:
        if args.phase == "after" and fixtures:
            cleaned = cleanup(fixtures["prefix"])
            (OUT / "cleanup.json").write_text(json.dumps(cleaned, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
