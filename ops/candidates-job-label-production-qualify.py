#!/usr/bin/env python3
"""Qualify Candidates list multi-application Job label fix (UI-only)."""
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
MARKER = "candidates_job_label_fix_v1"
BASE = os.environ.get("DASHBOARD_BASE") or "https://api.wathefni.ai/dashboard"
OUT = pathlib.Path(os.environ.get("CANDIDATES_JOB_LABEL_SHOTS") or "/tmp/candidates-job-label-shots")
PREFIX = os.environ.get("CANDIDATES_JOB_LABEL_PREFIX") or ("CLJL" + uuid.uuid4().hex[:6].upper())


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
        "has_applications_plural": " applications" in text,
        "has_no_job_assigned": "No job assigned" in text,
        "has_ar_no_job": "غير مرتبط بوظيفة" in text,
        "has_ar_dual": "طلبان" in text,
        "absent_plus_jobs": "+1 jobs" not in text and "+3 jobs" not in text,
        "js": [p.name for p in www.joinpath("assets").glob("dashboard-*.js")],
    }
    checks["ok"] = all(v for k, v in checks.items() if k != "js")
    return checks


def seed() -> dict[str, Any]:
    email = f"cljl.shared.{PREFIX.lower()}@example.invalid"
    keys = {
        "multi_a": f"{PREFIX}-A",
        "multi_b": f"{PREFIX}-B",
        "one": f"{PREFIX}-ONE",
        "zero": f"{PREFIX}-ZERO",
    }
    with db() as conn:
        with conn.cursor() as cur:
            for phone, name, em in [
                (f"cljl-{PREFIX.lower()}-a", "CLJL Multi Person", email),
                (f"cljl-{PREFIX.lower()}-b", "CLJL Multi Person", email),
                (f"cljl-{PREFIX.lower()}-one", "CLJL One Job", f"cljl.one.{PREFIX.lower()}@example.invalid"),
                (f"imp-cljl-{PREFIX.lower()}-zero", "CLJL Zero Job", f"cljl.zero.{PREFIX.lower()}@example.invalid"),
            ]:
                cur.execute(
                    """
                    INSERT INTO candidates(phone, name, email, profile, raw_json)
                    VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                    ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, email=EXCLUDED.email, updated_at=now()
                    """,
                    (phone, name, em, Json({"marker": MARKER}), Json({"marker": MARKER})),
                )
            rows = [
                (keys["multi_a"], f"cljl-{PREFIX.lower()}-a", "interview", "CLJL_HR", "HR",
                 {"marker": MARKER, "intake": {"source": "email"}, "grounded_contacts": {"email": email}, "candidate_email": email}),
                (keys["multi_b"], f"cljl-{PREFIX.lower()}-b", "shortlisted", "CLJL_FIN", "Finance",
                 {"marker": MARKER, "intake": {"source": "whatsapp"}, "grounded_contacts": {"email": email}, "candidate_email": email}),
                (keys["one"], f"cljl-{PREFIX.lower()}-one", "ready_for_review", "CLJL_HR", "HR",
                 {"marker": MARKER, "intake": {"source": "job_application"}}),
                (keys["zero"], f"imp-cljl-{PREFIX.lower()}-zero", "needs_role", "", "",
                 {"marker": MARKER, "record_state": "talent_pool", "intake": {"source": "recruiting_email"},
                  "candidate_email": f"cljl.zero.{PREFIX.lower()}@example.invalid"}),
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
    return {"prefix": PREFIX, "keys": keys}


def cleanup(prefix: str) -> dict[str, int]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM applications WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{prefix}%"))
            apps = cur.rowcount
            cur.execute(
                "DELETE FROM candidates WHERE phone LIKE %s OR phone LIKE %s OR email LIKE %s",
                (f"cljl-{prefix.lower()}%", f"imp-cljl-{prefix.lower()}%", f"%{prefix.lower()}@example.invalid"),
            )
            cands = cur.rowcount
        conn.commit()
    return {"applications_deleted": apps, "candidates_deleted": cands}


def open_candidates(page) -> None:
    page.goto(f"{BASE}/", wait_until="networkidle", timeout=120000)
    page.wait_for_timeout(1200)
    cand = page.get_by_role("button", name="Candidates")
    if cand.count() == 0:
        cand = page.get_by_text("Candidates", exact=True)
    cand.first.click()
    page.wait_for_timeout(2200)


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
                localStorage.setItem('wathefni_dashboard_email', 'cljl.owner@example.invalid');
                """
            )
            open_candidates(page)
            if args.phase == "after":
                page.get_by_placeholder(re.compile(r"Search|بحث", re.I)).first.fill("CLJL")
                page.get_by_role("button", name=re.compile(r"Apply|تطبيق", re.I)).first.click()
                page.wait_for_timeout(2000)

            shot = phase_dir / f"{args.phase}-candidates-desktop.png"
            page.screenshot(path=str(shot), full_page=True)
            result["shots"].append(str(shot))
            body = page.locator('[data-testid="unified-candidates-page"]').inner_text()
            result["assertions"]["snippet"] = body[:2500]

            if args.phase == "before":
                result["assertions"]["has_plus_jobs"] = bool(re.search(r"\+\d+\s*jobs", body, re.I))
            else:
                result["assertions"]["zero_no_job"] = "CLJL Zero Job" in body and "No job assigned" in body
                result["assertions"]["one_job_title"] = "CLJL One Job" in body and re.search(r"CLJL One Job[\s\S]{0,80}\bHR\b", body) is not None
                result["assertions"]["multi_count_only"] = "CLJL Multi Person" in body and "2 applications" in body
                result["assertions"]["absent_plus_jobs"] = not re.search(r"\+\d+\s*jobs", body, re.I)
                result["assertions"]["absent_hr_plus"] = "HR +1" not in body and "HR +3" not in body

                lang = page.get_by_role("button", name=re.compile(r"العربية|English|Language|اللغة", re.I))
                if lang.count():
                    lang.first.click()
                    page.wait_for_timeout(1200)
                ar_body = page.locator('[data-testid="unified-candidates-page"]').inner_text()
                result["assertions"]["rtl"] = page.locator('[data-testid="unified-candidates-page"]').get_attribute("dir") == "rtl"
                result["assertions"]["ar_no_job"] = "غير مرتبط بوظيفة" in ar_body
                result["assertions"]["ar_dual_or_plural"] = ("طلبان" in ar_body) or ("طلبات" in ar_body)
                ar = phase_dir / f"{args.phase}-candidates-ar.png"
                page.screenshot(path=str(ar), full_page=True)
                result["shots"].append(str(ar))

            browser.close()

        if args.phase == "after":
            a = result["assertions"]
            hard = [a.get("zero_no_job"), a.get("one_job_title"), a.get("multi_count_only"),
                    a.get("absent_plus_jobs"), a.get("absent_hr_plus"), a.get("rtl"),
                    a.get("ar_no_job"), a.get("ar_dual_or_plural")]
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
