#!/usr/bin/env python3
"""Browser-level staging screenshots for complete Talent Pool Classification UI.

Runs on staging VPS against http://127.0.0.1:8011 (staging dashboard-dist).
Synthetic fixtures only; cleaned at end. Does not touch /var/www.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from playwright.sync_api import sync_playwright

PREFIX = "TPCSHOT" + uuid.uuid4().hex[:6].upper()
MARKER = "talent_pool_classification_complete_ui_shots_v1"
COMPANY = "WATHEFNI"
OUT = pathlib.Path(os.environ.get("TPC_UI_SHOTS") or f"/tmp/{PREFIX.lower()}-shots")
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("DASHBOARD_BASE") or "http://127.0.0.1:8011/dashboard"


def db():
    vals: dict[str, str] = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.staging.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return psycopg2.connect(vals["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor)


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
        f"http://127.0.0.1:8011{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Wathefni-Company": COMPANY,
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


def seed(token: str) -> dict[str, str]:
    keys = {
        "tech": f"{PREFIX}-TECH",
        "finance": f"{PREFIX}-FIN",
    }
    fixtures = {
        "tech": "Senior Software Engineer, 6 years. Python SQL FastAPI AWS. Computer Science. Banking technology Kuwait.",
        "finance": "Accountant with Excel and financial reporting. Bachelor in Accounting. Audit and treasury.",
    }
    with db() as conn:
        with conn.cursor() as cur:
            for slug, app_key in keys.items():
                phone = f"imp-{PREFIX.lower()}-{slug}"
                text = fixtures[slug]
                cur.execute(
                    """
                    INSERT INTO candidates(phone, name, email, profile, raw_json)
                    VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                    ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, raw_json=EXCLUDED.raw_json, updated_at=now()
                    """,
                    (
                        phone,
                        f"TPC Shot {slug}",
                        f"{slug}.{PREFIX.lower()}@example.invalid",
                        Json({"skills": []}),
                        Json({"marker": MARKER, "normalized_cv_text": text, "synthetic": True}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO applications(
                      company_code, app_key, phone, status, position_code, position_title,
                      cv_received, raw_json, ingested_at, updated_at
                    ) VALUES (%s,%s,%s,'needs_role','','',true,%s::jsonb,now(),now())
                    ON CONFLICT (app_key) DO UPDATE SET raw_json=EXCLUDED.raw_json, updated_at=now()
                    """,
                    (
                        COMPANY,
                        app_key,
                        phone,
                        Json({"marker": MARKER, "normalized_cv_text": text, "cv_text": text, "synthetic": True}),
                    ),
                )
            conn.commit()
    for slug, app_key in keys.items():
        http("POST", f"/dashboard/prehire/applications/{app_key}/classification/run", token, {})
    return keys


def cleanup() -> int:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM candidate_classification_review_events WHERE app_key LIKE %s", (f"{PREFIX}%",))
            cur.execute("DELETE FROM candidate_classification_suggestions WHERE app_key LIKE %s", (f"{PREFIX}%",))
            cur.execute("DELETE FROM candidate_classification_runs WHERE app_key LIKE %s", (f"{PREFIX}%",))
            cur.execute("DELETE FROM talent_pool_classification_jobs WHERE app_key LIKE %s", (f"{PREFIX}%",))
            cur.execute("DELETE FROM candidate_saved_views WHERE name LIKE %s", (f"{PREFIX}%",))
            cur.execute("DELETE FROM applications WHERE app_key LIKE %s", (f"{PREFIX}%",))
            cur.execute("DELETE FROM candidates WHERE phone LIKE %s", (f"imp-{PREFIX.lower()}%",))
            cur.execute("SELECT count(*) AS c FROM applications WHERE app_key LIKE %s", (f"{PREFIX}%",))
            left = int(cur.fetchone()["c"])
            conn.commit()
    return left


def set_flags(*, tenants: str, ui: str, manual: str = "on") -> None:
    conf = pathlib.Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf")
    conf.write_text(
        "[Service]\n"
        "Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION=off\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS={tenants}\n"
        "Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA=on\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL={manual}\n"
        "Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_UI={ui}\n",
        encoding="utf-8",
    )
    os.system("systemctl daemon-reload && systemctl restart wathefni-orchestrator-staging.service")
    for _ in range(90):
        if os.system("curl -sf http://127.0.0.1:8011/health >/dev/null") == 0:
            return
        time.sleep(1)
    raise RuntimeError("health failed")


def inject_session(page, token: str) -> None:
    page.add_init_script(
        f"""
        localStorage.setItem('wathefni_dashboard_token', {json.dumps(token)});
        localStorage.setItem('wathefni_company_code', 'WATHEFNI');
        localStorage.setItem('wathefni_dashboard_email', 'staging-owner@example.invalid');
        """
    )


def shot(page, name: str) -> None:
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print("SHOT", path)


def main() -> int:
    set_flags(tenants="WATHEFNI", ui="on", manual="on")
    token = mint()
    keys = seed(token)
    st, tax = http("GET", "/dashboard/prehire/classification/taxonomy", token)
    career_nodes = next((d["nodes"] for d in (tax.get("dimensions") or []) if d["dimension"] == "career_area"), [])
    tech_node = next((n["node_id"] for n in career_nodes if "tech" in str(n.get("node_id")).lower() or "Technolog" in str(n.get("label_en") or "")), None)
    finance_node = next((n["node_id"] for n in career_nodes if "finance" in str(n.get("node_id")).lower()), None)

    outcomes: dict[str, Any] = {"prefix": PREFIX, "shots": [], "checks": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        page = context.new_page()
        inject_session(page, token)
        page.goto(f"{BASE}/", wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(2000)
        cand = page.get_by_role("button", name="Candidates")
        if cand.count() == 0:
            cand = page.get_by_text("Candidates", exact=True)
        if cand.count() == 0:
            raise RuntimeError("candidates_nav_missing")
        cand.first.click()
        page.wait_for_timeout(2500)
        page.wait_for_selector('input[placeholder="Search candidates"]', timeout=60000)
        # Ensure candidates loaded
        page.fill('input[placeholder="Search candidates"]', PREFIX)
        page.get_by_role("button", name="Apply").click()
        page.wait_for_timeout(2000)
        chip = page.locator('[data-testid="classification-compact-chip"]')
        outcomes["checks"]["table_chip_visible"] = chip.count() > 0
        shot(page, "01-table-chip")

        bar = page.locator('[data-testid="classification-filter-bar"]')
        outcomes["checks"]["filter_bar_visible"] = bar.count() == 1
        for dim in ["career_area", "likely_role", "skill", "industry", "seniority", "experience_band"]:
            loc = page.locator(f'[data-testid="classification-filter-{dim}"]')
            outcomes["checks"][f"filter_{dim}"] = loc.count() == 1
            if loc.count():
                shot(page, f"02-filter-{dim}")

        # Combined filters via UI selectors if tech node known
        if tech_node:
            page.locator('[data-testid="classification-filter-career_area"] select').select_option(tech_node)
            page.wait_for_timeout(400)
            page.get_by_role("button", name="Apply").click()
            page.wait_for_timeout(1500)
            shot(page, "03-combined-filters")

        # Save view
        page.fill('input[placeholder="Save current view as…"]', f"{PREFIX}-view")
        page.get_by_role("button", name="Save view").click()
        page.wait_for_timeout(1500)
        shot(page, "04-saved-view")

        # Open tech candidate profile / drawer
        page.fill('input[placeholder="Search candidates"]', keys["tech"])
        page.get_by_role("button", name="Apply").click()
        page.wait_for_timeout(1500)
        page.locator("text=TPC Shot tech").first.click()
        page.wait_for_timeout(2000)
        section = page.locator('[data-testid="candidate-classification-section"]')
        outcomes["checks"]["profile_section"] = section.count() == 1
        shot(page, "05-profile-current")

        if page.get_by_role("button", name="Show classification history").count():
            page.get_by_role("button", name="Show classification history").click()
            page.wait_for_timeout(800)
            shot(page, "06-immutable-run-history")

        # Confirm dialog path: click Confirm on first suggestion if present
        confirm_btn = page.locator('[data-testid="classification-ai-suggested"] button', has_text="Confirm")
        if confirm_btn.count():
            confirm_btn.first.click()
            page.wait_for_timeout(500)
            shot(page, "07-hr-confirm-dialog")
            # dismiss dialog cancel to avoid mutating if possible — click Confirm in dialog for proof
            dialog_confirm = page.get_by_role("button", name="Confirm").last
            if dialog_confirm.count():
                dialog_confirm.click()
                page.wait_for_timeout(1000)
                shot(page, "08-hr-confirm-done")

        add_select = page.locator('[data-testid="classification-add-correct"] select')
        if add_select.count() and add_select.locator("option").count() > 1:
            value = add_select.locator("option").nth(1).get_attribute("value")
            if value:
                add_select.select_option(value)
                page.get_by_role("button", name="Add").click()
                page.wait_for_timeout(400)
                shot(page, "09-hr-add-dialog")
                page.get_by_role("button", name="Confirm").last.click()
                page.wait_for_timeout(800)

        # Reject path screenshot if available
        reject_btn = page.locator('[data-testid="classification-ai-suggested"] button', has_text="Reject")
        if reject_btn.count():
            reject_btn.first.click()
            page.wait_for_timeout(400)
            shot(page, "10-hr-reject-dialog")
            page.get_by_role("button", name="Cancel").last.click()

        browser.close()

    # Feature OFF hide
    set_flags(tenants="", ui="off", manual="off")
    token_off = mint()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        inject_session(page, token_off)
        page.goto(f"{BASE}/", wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(2000)
        cand = page.get_by_role("button", name="Candidates")
        if cand.count() == 0:
            cand = page.get_by_text("Candidates", exact=True)
        if cand.count():
            cand.first.click()
            page.wait_for_timeout(2500)
        outcomes["checks"]["feature_off_hides_bar"] = page.locator('[data-testid="classification-filter-bar"]').count() == 0
        shot(page, "11-feature-off")
        browser.close()

    # restore staging enablement
    set_flags(tenants="WATHEFNI", ui="on", manual="on")
    left = cleanup()
    outcomes["residue"] = left
    outcomes["shots"] = sorted(p.name for p in OUT.glob("*.png"))
    OUT.joinpath("shots-outcomes.json").write_text(json.dumps(outcomes, indent=2), encoding="utf-8")
    print(json.dumps(outcomes, indent=2))
    return 0 if left == 0 and outcomes["checks"].get("filter_bar_visible") and outcomes["checks"].get("feature_off_hides_bar") else 1


if __name__ == "__main__":
    raise SystemExit(main())
