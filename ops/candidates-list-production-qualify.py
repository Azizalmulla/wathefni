#!/usr/bin/env python3
"""Qualify Candidates list simplification on production dashboard (UI-only).

Modes:
  --phase before   Capture current production Candidates UI (no fixtures required).
  --phase after    Seed representative synthetic rows, capture screenshots, assert DOM,
                   then cleanup. Does not mutate non-synthetic candidate data.
  --phase assert-bundle  Assert deployed JS markers only.

Requires Playwright Chromium on the host that runs this script.
"""
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
MARKER = "candidates_list_simp_prod_qual_v1"
BASE = os.environ.get("DASHBOARD_BASE") or "https://api.wathefni.ai/dashboard"
OUT = pathlib.Path(os.environ.get("CANDIDATES_LIST_SHOTS") or "/tmp/candidates-list-shots")
PREFIX = os.environ.get("CANDIDATES_LIST_PREFIX") or ("CLSQ" + uuid.uuid4().hex[:6].upper())

REQUIRED_HEADERS = ["Candidate", "Expertise", "Job", "Stage", "Received"]
FORBIDDEN_HEADERS = [
    "Entry method",
    "Recruiter owner",
    "CV processing",
    "Assessment",
    "Communication",
    "Status",
]
FORBIDDEN_ROW_TEXT = [
    "Talent Pool",
    "Advisory",
    "Career area",
    "Likely role",
    "Not linked",
    "needs_role",
    "Open Intake Operations",
    "bulk_import",
    "Source not recorded",
    "Recruiting email",
]


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
    if not user:
        raise RuntimeError("no active owner dashboard user for WATHEFNI")
    token, _ = app.create_dashboard_session(dict(user))
    return token


def assert_bundle(www: pathlib.Path) -> dict[str, Any]:
    js_files = sorted(www.joinpath("assets").glob("dashboard-*.js"))
    if not js_files:
        raise RuntimeError("no dashboard-*.js under /var/www")
    text = "\n".join(p.read_text(errors="ignore") for p in js_files)
    checks = {
        "has_no_job_assigned": "No job assigned" in text,
        "has_cvs_need_attention": "CVs need attention" in text,
        "has_review_identity": "Review identity" in text,
        "has_expertise_col": "Expertise" in text,
        "has_received_col": "Received" in text,
        "has_manual_upload": "Manual upload" in text,
        "absent_open_intake_ops_cta": "Open Intake Operations" not in text,
        # Talent Pool may still exist in profile/nav copy; row badge wording for list pills is "No job assigned".
        "has_with_a_job_pill": "With a job" in text,
    }
    checks["ok"] = all(checks.values())
    checks["js"] = [p.name for p in js_files]
    return checks


def seed() -> dict[str, Any]:
    email_shared = f"clsq.shared.{PREFIX.lower()}@example.invalid"
    phone_a = f"clsq-{PREFIX.lower()}-a"
    phone_b = f"clsq-{PREFIX.lower()}-b"
    phone_wa = f"clsq-{PREFIX.lower()}-wa"
    phone_gen = f"imp-clsq-{PREFIX.lower()}-gen"
    phone_dup1 = f"clsq-{PREFIX.lower()}-dup1"
    phone_dup2 = f"clsq-{PREFIX.lower()}-dup2"
    keys = {
        "job_app": f"{PREFIX}-JOB",
        "multi_a": f"{PREFIX}-MULTI-A",
        "multi_b": f"{PREFIX}-MULTI-B",
        "wa": f"{PREFIX}-WA",
        "general_email": f"{PREFIX}-GEN-EMAIL",
        "dup1": f"{PREFIX}-DUP1",
        "dup2": f"{PREFIX}-DUP2",
    }
    with db() as conn:
        with conn.cursor() as cur:
            # Confirmed person with two applications (same email)
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, email=EXCLUDED.email, updated_at=now()
                """,
                (phone_a, "CLSQ Multi Person", email_shared,
                 Json({"skills": ["Excel"], "marker": MARKER}),
                 Json({"marker": MARKER, "synthetic": True})),
            )
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, email=EXCLUDED.email, updated_at=now()
                """,
                (phone_b, "CLSQ Multi Person", email_shared,
                 Json({"skills": ["Finance"], "marker": MARKER}),
                 Json({"marker": MARKER, "synthetic": True})),
            )
            # WhatsApp applicant
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, updated_at=now()
                """,
                (phone_wa, "CLSQ WhatsApp Candidate", f"clsq.wa.{PREFIX.lower()}@example.invalid",
                 Json({"skills": ["Sales"], "marker": MARKER}),
                 Json({"marker": MARKER, "synthetic": True})),
            )
            # General email (held)
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, email=EXCLUDED.email, updated_at=now()
                """,
                (phone_gen, "CLSQ General Email", f"clsq.gen.{PREFIX.lower()}@example.invalid",
                 Json({"skills": ["Accounting"], "marker": MARKER}),
                 Json({"marker": MARKER, "synthetic": True})),
            )
            # Uncertain name-only duplicates (distinct phones, no shared grounded email)
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, updated_at=now()
                """,
                (phone_dup1, "CLSQ Same Name Uncertain", None,
                 Json({"marker": MARKER}), Json({"marker": MARKER, "synthetic": True})),
            )
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, updated_at=now()
                """,
                (phone_dup2, "CLSQ Same Name Uncertain", None,
                 Json({"marker": MARKER}), Json({"marker": MARKER, "synthetic": True})),
            )
            # Job applicant
            cur.execute(
                """
                INSERT INTO candidates(phone, name, email, profile, raw_json)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, email=EXCLUDED.email, updated_at=now()
                """,
                (f"clsq-{PREFIX.lower()}-job", "CLSQ Job Applicant", f"clsq.job.{PREFIX.lower()}@example.invalid",
                 Json({"skills": ["Engineering"], "marker": MARKER}),
                 Json({"marker": MARKER, "synthetic": True})),
            )

            apps = [
                (
                    keys["job_app"], f"clsq-{PREFIX.lower()}-job", "ready_for_review",
                    "CLSQ_JOB", "CLSQ Finance Manager",
                    {"marker": MARKER, "intake": {"source": "job_application"},
                     "classification_chip": "Advisory: Technology · Software Engineering",
                     "cv": {"processing": {"status": "ready"}}},
                ),
                (
                    keys["multi_a"], phone_a, "shortlisted",
                    "CLSQ_JOB", "CLSQ Finance Manager",
                    {"marker": MARKER, "intake": {"source": "email"},
                     "candidate_email": email_shared,
                     "grounded_contacts": {"email": email_shared},
                     "classification_chip": "Accounting",
                     "cv": {"processing": {"status": "ready"}}},
                ),
                (
                    keys["multi_b"], phone_b, "interview",
                    "CLSQ_JOB_B", "CLSQ Sales Lead",
                    {"marker": MARKER, "intake": {"source": "dashboard"},
                     "candidate_email": email_shared,
                     "grounded_contacts": {"email": email_shared},
                     "classification_chip": "Sales",
                     "cv": {"processing": {"status": "ready"}}},
                ),
                (
                    keys["wa"], phone_wa, "ready_for_review",
                    "CLSQ_JOB", "CLSQ Finance Manager",
                    {"marker": MARKER, "intake": {"source": "whatsapp"},
                     "classification_chip": "Sales",
                     "cv": {"processing": {"status": "ready"}}},
                ),
                (
                    keys["general_email"], phone_gen, "needs_role",
                    "", "",
                    {"marker": MARKER, "record_state": "talent_pool",
                     "intake": {"source": "recruiting_email", "sender_email": "sender@example.invalid"},
                     "candidate_email": f"clsq.gen.{PREFIX.lower()}@example.invalid",
                     "classification_chip": "Accounting",
                     "cv": {"processing": {"status": "ready", "profile_parsed": True}}},
                ),
                (
                    keys["dup1"], phone_dup1, "ready_for_review",
                    "CLSQ_JOB", "CLSQ Finance Manager",
                    {"marker": MARKER, "intake": {"source": "manual_upload"},
                     "classification_chip": "Marketing",
                     "cv": {"processing": {"status": "ready"}}},
                ),
                (
                    keys["dup2"], phone_dup2, "shortlisted",
                    "CLSQ_JOB_B", "CLSQ Sales Lead",
                    {"marker": MARKER, "intake": {"source": "bulk_import"},
                     "classification_chip": "Marketing",
                     "cv": {"processing": {"status": "ready"}}},
                ),
            ]
            for app_key, phone, status, pcode, ptitle, raw in apps:
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
                    (COMPANY, app_key, phone, status, pcode, ptitle, Json(raw)),
                )
        conn.commit()
    return {"prefix": PREFIX, "keys": keys, "email_shared": email_shared}


def cleanup(prefix: str) -> dict[str, int]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM applications WHERE company_code=%s AND app_key LIKE %s",
                (COMPANY, f"{prefix}%"),
            )
            apps = cur.rowcount
            cur.execute(
                "DELETE FROM candidates WHERE phone LIKE %s OR phone LIKE %s OR email LIKE %s",
                (f"clsq-{prefix.lower()}%", f"imp-clsq-{prefix.lower()}%", f"%{prefix.lower()}@example.invalid"),
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
    if cand.count():
        cand.first.click()
        page.wait_for_timeout(2500)


def capture(phase: str, token: str, search: str | None = None) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    phase_dir = OUT / phase
    phase_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"phase": phase, "shots": [], "assertions": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 960}, ignore_https_errors=True)
        page = context.new_page()
        page.add_init_script(
            f"""
            localStorage.setItem('wathefni_dashboard_token', {json.dumps(token)});
            localStorage.setItem('wathefni_company_code', {json.dumps(COMPANY)});
            localStorage.setItem('wathefni_dashboard_email', 'clsq.owner@example.invalid');
            """
        )
        open_candidates(page)
        if search:
            box = page.get_by_placeholder(re.compile(r"Search|بحث", re.I))
            if box.count():
                box.first.fill(search)
                apply = page.get_by_role("button", name=re.compile(r"Apply|تطبيق", re.I))
                if apply.count():
                    apply.first.click()
                page.wait_for_timeout(2000)

        shot = phase_dir / f"{phase}-candidates-desktop.png"
        page.screenshot(path=str(shot), full_page=True)
        result["shots"].append(str(shot))

        # Tablet viewport
        page.set_viewport_size({"width": 834, "height": 1112})
        page.wait_for_timeout(800)
        shot_t = phase_dir / f"{phase}-candidates-tablet.png"
        page.screenshot(path=str(shot_t), full_page=True)
        result["shots"].append(str(shot_t))
        page.set_viewport_size({"width": 1440, "height": 960})

        headers = page.locator("thead th").all_inner_texts()
        # CSS uppercase tracking can yield CANDIDATE / EXPERTISE; compare casefold.
        headers_norm = [h.strip() for h in headers if h.strip()]
        headers_fold = [h.casefold() for h in headers_norm]
        result["assertions"]["headers"] = headers_norm

        body_text = page.locator('[data-testid="unified-candidates-page"]').inner_text()
        result["assertions"]["page_snippet"] = body_text[:2500]

        if phase == "before":
            result["assertions"]["has_entry_method"] = any("entry method" in h for h in headers_fold)
            result["assertions"]["has_recruiter_owner"] = any("recruiter" in h for h in headers_fold)
        else:
            required_fold = [h.casefold() for h in REQUIRED_HEADERS]
            result["assertions"]["five_columns"] = headers_fold[:5] == required_fold or set(required_fold).issubset(set(headers_fold))
            forbidden_fold = [h.casefold() for h in FORBIDDEN_HEADERS if h != "Status"]
            result["assertions"]["no_forbidden_headers"] = not any(h in headers_fold for h in forbidden_fold)
            # Status header must not appear as a column title when we have Stage
            result["assertions"]["has_stage_not_status"] = ("stage" in headers_fold) and ("status" not in headers_fold)
            for bad in FORBIDDEN_ROW_TEXT:
                result["assertions"][f"absent::{bad}"] = bad not in body_text

            # Filters button exists; classification bar not visible until Filters opened
            filters_btn = page.get_by_role("button", name=re.compile(r"^Filters|^مرشحات", re.I))
            result["assertions"]["filters_button_visible"] = filters_btn.count() > 0
            class_bar = page.locator('[data-testid="classification-filter-bar"]')
            result["assertions"]["classification_hidden_by_default"] = class_bar.count() == 0 or not class_bar.first.is_visible()
            if filters_btn.count():
                filters_btn.first.click()
                page.wait_for_timeout(800)
                class_bar = page.locator('[data-testid="classification-filter-bar"]')
                result["assertions"]["classification_visible_in_filters"] = class_bar.count() > 0 and class_bar.first.is_visible()
                shot_f = phase_dir / f"{phase}-candidates-filters-open.png"
                page.screenshot(path=str(shot_f), full_page=True)
                result["shots"].append(str(shot_f))
                filters_btn.first.click()
                page.wait_for_timeout(400)

            # Representative row checks via search
            def search_and_shot(label: str, query: str, expect_substrings: list[str]) -> None:
                box = page.get_by_placeholder(re.compile(r"Search|بحث", re.I))
                box.first.fill(query)
                apply = page.get_by_role("button", name=re.compile(r"Apply|تطبيق", re.I))
                apply.first.click()
                page.wait_for_timeout(1800)
                txt = page.locator('[data-testid="unified-candidates-page"]').inner_text()
                ok = all(s in txt for s in expect_substrings)
                result["assertions"][f"row::{label}"] = {"ok": ok, "expect": expect_substrings, "snippet": txt[:1200]}
                path = phase_dir / f"{phase}-{label}.png"
                page.screenshot(path=str(path), full_page=True)
                result["shots"].append(str(path))

            search_and_shot("general-email", "CLSQ General Email", ["CLSQ General Email", "No job assigned"])
            search_and_shot("whatsapp", "CLSQ WhatsApp Candidate", ["CLSQ WhatsApp Candidate", "WhatsApp"])
            search_and_shot("job-applicant", "CLSQ Job Applicant", ["CLSQ Job Applicant", "CLSQ Finance Manager", "Ready for review"])
            search_and_shot("multi-person", "CLSQ Multi Person", ["CLSQ Multi Person", "+1"])
            search_and_shot("uncertain-dup", "CLSQ Same Name Uncertain", ["CLSQ Same Name Uncertain", "Review identity"])

            # Arabic / RTL
            lang = page.get_by_role("button", name=re.compile(r"العربية|English|Language|اللغة", re.I))
            if lang.count() == 0:
                lang = page.get_by_text(re.compile(r"العربية|English"), exact=False)
            if lang.count():
                lang.first.click()
                page.wait_for_timeout(1500)
                dir_attr = page.locator('[data-testid="unified-candidates-page"]').get_attribute("dir")
                ar_headers = page.locator("thead th").all_inner_texts()
                result["assertions"]["rtl_dir"] = dir_attr == "rtl"
                result["assertions"]["ar_headers"] = [h.strip() for h in ar_headers]
                shot_ar = phase_dir / f"{phase}-candidates-ar-rtl.png"
                page.screenshot(path=str(shot_ar), full_page=True)
                result["shots"].append(str(shot_ar))

        browser.close()
    return result


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
        cleaned = cleanup(args.prefix)
        print(json.dumps(cleaned, indent=2))
        return 0

    token = mint()
    fixtures = None
    try:
        if args.phase == "after":
            fixtures = seed()
            (OUT / "fixtures.json").write_text(json.dumps(fixtures, indent=2), encoding="utf-8")
            time.sleep(1)
            result = capture("after", token, search="CLSQ")
            result["fixtures"] = fixtures
        else:
            result = capture("before", token)
        (OUT / f"{args.phase}-qualify.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"phase": args.phase, "shots": len(result.get("shots", [])), "assertions": result.get("assertions")}, indent=2))
        if args.phase == "after":
            asserts = result.get("assertions") or {}
            hard = [
                asserts.get("five_columns"),
                asserts.get("has_stage_not_status"),
                asserts.get("filters_button_visible"),
                asserts.get("classification_hidden_by_default"),
                asserts.get("classification_visible_in_filters"),
                (asserts.get("row::general-email") or {}).get("ok"),
                (asserts.get("row::whatsapp") or {}).get("ok"),
                (asserts.get("row::job-applicant") or {}).get("ok"),
                (asserts.get("row::multi-person") or {}).get("ok"),
                (asserts.get("row::uncertain-dup") or {}).get("ok"),
            ]
            # Forbidden strings
            hard.extend(v for k, v in asserts.items() if k.startswith("absent::"))
            ok = all(bool(x) for x in hard)
            result["ok"] = ok
            (OUT / "after-qualify.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            return 0 if ok else 2
        return 0
    finally:
        if args.phase == "after" and fixtures:
            cleaned = cleanup(fixtures["prefix"])
            (OUT / "cleanup.json").write_text(json.dumps(cleaned, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
