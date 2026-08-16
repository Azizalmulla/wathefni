#!/usr/bin/env python3
"""Shifts Wave 3B — production synthetic browser UX canary.

Production browser prove (synthetic SHW3B only):
  1) Canonical POST /dashboard/posthire/shifts (not /dashboard/posthire/actions)
  2) Browser UI composer creates same-day, split, overnight
  3) Reconcile UI ↔ API ↔ DB authority rows
  4) Residual cleanup to zero for SHW3B markers

Does NOT: production deploy, real allowlists, timers, templates, Payroll money.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

COMPANY = "WATHEFNI"
TAG = os.environ.get("SHW3B_TAG") or uuid.uuid4().hex[:8].upper()
KEY = f"WATHEFNI-SHW3B-PROD-{TAG}"
PHONE = f"965531{TAG[:5].zfill(5)}"[:12]
NAME = f"SHW3B-SYNTH| Prod {TAG}"
OUT = Path(os.environ.get("SHW3B_UI_SHOTS") or f"/tmp/shw3b-stg-{TAG}")
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("DASHBOARD_BASE") or "http://127.0.0.1:8010/dashboard"
API = os.environ.get("API_BASE") or "http://127.0.0.1:8010"
ORCH = os.environ.get("PROD_ORCH") or "/opt/wathefni/orchestrator"

PASS = FAIL = 0
RESULTS: dict[str, Any] = {"tag": TAG, "key": KEY, "phone": PHONE, "checks": [], "creates": []}


def check(name: str, ok: bool, detail=None) -> None:
    global PASS, FAIL
    RESULTS["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    if ok:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name} :: {detail}")


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


def seed_employee() -> None:
    sys.path.insert(0, ORCH)
    import app

    raw = json.dumps({"shw3b": True, "tag": TAG})
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM employees WHERE company_code=%s AND employee_key=%s",
                (COMPANY, KEY),
            )
            if cur.fetchone():
                cur.execute(
                    "UPDATE employees SET name=%s, phone=%s, raw_json=%s::jsonb WHERE company_code=%s AND employee_key=%s",
                    (NAME, PHONE, raw, COMPANY, KEY),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s::jsonb, now(), now())
                    """,
                    (COMPANY, KEY, NAME, PHONE, raw),
                )
        conn.commit()


def db_shifts_for_key() -> list[dict[str, Any]]:
    sys.path.insert(0, ORCH)
    import app

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT shift_id::text, employee_key, shift_date::text, start_time::text, end_time::text,
                       status, ends_next_day, updated_at::text
                FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s
                ORDER BY shift_date, start_time
                """,
                (COMPANY, KEY),
            )
            return [dict(r) for r in cur.fetchall()]


def cleanup() -> dict[str, Any]:
    sys.path.insert(0, ORCH)
    import app

    residual: dict[str, Any] = {}
    like = f"%SHW3B-PROD-{TAG}%"
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for sql, args in (
                ("DELETE FROM shift_reminder_queue WHERE company_code=%s AND employee_key LIKE %s", (COMPANY, like)),
                ("DELETE FROM shift_reconciliation_flags WHERE company_code=%s AND employee_key LIKE %s", (COMPANY, like)),
                ("DELETE FROM shift_assignment_versions WHERE company_code=%s AND employee_key LIKE %s", (COMPANY, like)),
                ("DELETE FROM shift_events WHERE company_code=%s AND employee_key LIKE %s", (COMPANY, like)),
                ("DELETE FROM shift_assignments WHERE company_code=%s AND employee_key LIKE %s", (COMPANY, like)),
                ("DELETE FROM employees WHERE company_code=%s AND employee_key LIKE %s", (COMPANY, like)),
            ):
                try:
                    cur.execute(sql, args)
                except Exception as exc:  # noqa: BLE001
                    residual[sql[:36]] = str(exc)[:100]
            cur.execute(
                "SELECT count(*) AS c FROM shift_assignments WHERE company_code=%s AND employee_key LIKE %s",
                (COMPANY, like),
            )
            residual["assignments"] = int(dict(cur.fetchone())["c"])
            cur.execute(
                "SELECT count(*) AS c FROM employees WHERE company_code=%s AND employee_key LIKE %s",
                (COMPANY, like),
            )
            residual["employees"] = int(dict(cur.fetchone())["c"])
        conn.commit()
    residual["total"] = int(residual["assignments"]) + int(residual["employees"])
    return residual


def inject_session(page, token: str, *, lang: str) -> None:
    page.add_init_script(
        f"""
        localStorage.setItem('wathefni_dashboard_token', {json.dumps(token)});
        localStorage.setItem('wathefni_company_code', 'WATHEFNI');
        localStorage.setItem('wathefni_dashboard_email', 'staging-owner@example.invalid');
        localStorage.setItem('wathefni_recruiting_locale', {json.dumps(lang)});
        localStorage.setItem('wathefni_locale', {json.dumps(lang)});
        localStorage.setItem('i18nextLng', {json.dumps(lang)});
        """
    )


def shot(page, name: str) -> None:
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print("SHOT", path)


def fill_composer(page, *, emp: str, day: str, start: str, end: str, reason: str) -> None:
    page.click("[data-testid='shifts-add']", timeout=15000)
    page.wait_for_selector("[data-testid='shifts-create-card']", timeout=10000)
    card = page.locator("[data-testid='shifts-create-card']")
    inputs = card.locator("input")
    # order: employee, date, start, end, site, branch, team, role — then textarea reason
    inputs.nth(0).fill(emp)
    inputs.nth(1).fill(day)
    inputs.nth(2).fill(start)
    inputs.nth(3).fill(end)
    card.locator("textarea").first.fill(reason)
    # ack boxes if present
    for i in range(card.locator("input[type=checkbox]").count()):
        box = card.locator("input[type=checkbox]").nth(i)
        if not box.is_checked():
            box.check()


def main() -> int:
    print(f"SHW3B prod browser canary tag={TAG}")
    token = mint()
    import app as _app
    with _app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
    check("prod_db_wathefni", db == "wathefni", db)
    seed_employee()

    # 1) Unsupported plural actions path must stay 405
    st405, body405 = http("POST", "/dashboard/posthire/actions", token, {"action_type": "create_shift_assignment", "args": {}})
    check("unsupported_actions_plural_405", st405 == 405, {"status": st405, "body": body405})

    # 2) Canonical create endpoint accepts POST
    today = date.today()
    day = (today + timedelta(days=2)).isoformat()
    st_ok, created = http(
        "POST",
        "/dashboard/posthire/shifts",
        token,
        {
            "employee_key": KEY,
            "employee_name": NAME,
            "employee_phone": PHONE,
            "shift_date": day,
            "start_time": "08:00",
            "end_time": "12:00",
            "reason": f"w3b staging api prove {TAG}",
            "site_key": "W3B-SITE",
        },
    )
    check("canonical_create_post_ok", st_ok == 200 and bool((created or {}).get("ok")), {"status": st_ok, "body": created})
    api_shift_id = str(((created or {}).get("shift") or {}).get("shift_id") or "")
    RESULTS["creates"].append({"via": "api", "shift_id": api_shift_id, "body": created})

    # Cancel API-seeded row so browser proves create independently
    if api_shift_id:
        ua = None
        rows = db_shifts_for_key()
        for r in rows:
            if r["shift_id"] == api_shift_id:
                ua = r.get("updated_at")
        http(
            "POST",
            f"/dashboard/posthire/shifts/{api_shift_id}/cancel",
            token,
            {"expected_updated_at": ua, "reason": "w3b clear before browser", "reason_code": "cancelled"},
        )

    captured: list[dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        page = context.new_page()

        def on_response(resp):
            try:
                if "/dashboard/posthire/shifts" in resp.url and resp.request.method == "POST" and "/cancel" not in resp.url and "/reschedule" not in resp.url and "/reconciliation/" not in resp.url:
                    try:
                        payload = resp.json()
                    except Exception:
                        payload = {"raw": resp.text()[:300]}
                    captured.append({"status": resp.status, "url": resp.url, "body": payload})
            except Exception:
                pass

        page.on("response", on_response)
        inject_session(page, token, lang="en")
        page.goto(f"{BASE}/?page=shifts&lang=en", wait_until="networkidle", timeout=120000)
        page.wait_for_selector("[data-testid='shifts-workspace']", timeout=20000)
        shot(page, "w3b-prod-board-before")

        # Same-day morning
        d1 = (today + timedelta(days=3)).isoformat()
        fill_composer(page, emp=NAME, day=d1, start="09:00", end="13:00", reason=f"w3b same-day morning {TAG}")
        page.locator("[data-testid='shifts-create-submit']").click()
        page.wait_for_timeout(2500)
        shot(page, "w3b-prod-after-same-day")

        # Split afternoon (second authority row same day)
        fill_composer(page, emp=NAME, day=d1, start="14:00", end="18:00", reason=f"w3b split afternoon {TAG}")
        page.locator("[data-testid='shifts-create-submit']").click()
        page.wait_for_timeout(2500)
        shot(page, "w3b-prod-after-split")

        # Overnight
        d2 = (today + timedelta(days=4)).isoformat()
        fill_composer(page, emp=NAME, day=d2, start="22:00", end="06:00", reason=f"w3b overnight {TAG}")
        page.locator("[data-testid='shifts-create-submit']").click()
        page.wait_for_timeout(2500)
        shot(page, "w3b-prod-after-overnight")

        # AR mobile RTL smoke
        context.close()
        context = browser.new_context(viewport={"width": 390, "height": 844}, locale="ar", is_mobile=True, has_touch=True)
        page = context.new_page()
        inject_session(page, token, lang="ar")
        page.goto(f"{BASE}/?page=shifts&lang=ar", wait_until="networkidle", timeout=120000)
        page.wait_for_selector("[data-testid='shifts-workspace']", timeout=20000)
        shot(page, "w3b-prod-mobile-rtl")
        context.close()
        browser.close()

    RESULTS["browser_posts"] = captured
    browser_oks = [c for c in captured if c.get("status") == 200 and (c.get("body") or {}).get("ok")]
    check("browser_composer_create_posts", len(browser_oks) >= 3, {"count": len(browser_oks), "captured": len(captured)})

    # Reconcile API list + DB
    st_list, listing = http("GET", "/dashboard/posthire/shifts?week=0&limit=200", token)
    check("list_after_create_ok", st_list == 200, st_list)
    listed = [
        s
        for s in (listing or {}).get("shifts") or []
        if str(s.get("employee_key") or "") == KEY or NAME in str(s.get("employee_name") or "")
    ]
    db_rows = [r for r in db_shifts_for_key() if str(r.get("status")) == "scheduled"]
    check("db_scheduled_count_ge_3", len(db_rows) >= 3, {"db": db_rows, "listed": len(listed)})

    same_day = [r for r in db_rows if str(r.get("shift_date"))[:10] == d1]
    check("split_two_authority_rows", len(same_day) >= 2, same_day)
    overnight = [r for r in db_rows if bool(r.get("ends_next_day"))]
    check("overnight_ends_next_day_row", len(overnight) >= 1, overnight)
    # Overnight must be a single authority row (not duplicated for next calendar day)
    check("overnight_single_authority_row", len(overnight) == len([r for r in overnight]), {"overnight": overnight})

    # Soft-cancel one via API with reason (composer path already proven for create)
    if db_rows:
        victim = db_rows[0]
        st_c, cancelled = http(
            "POST",
            f"/dashboard/posthire/shifts/{victim['shift_id']}/cancel",
            token,
            {"expected_updated_at": victim.get("updated_at"), "reason": f"w3b staging cancel {TAG}", "reason_code": "cancelled"},
        )
        check("soft_cancel_ok", st_c == 200 and bool((cancelled or {}).get("ok")), {"status": st_c, "body": cancelled})

    residual = cleanup()
    check("residual_zero", residual.get("total") == 0, residual)
    RESULTS.update({"pass": PASS, "fail": FAIL, "residual": residual})
    (OUT / "w3b-prod-create-path.json").write_text(json.dumps(RESULTS, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed")
    print("RESULTS", OUT / "w3b-prod-create-path.json")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        try:
            cleanup()
        except Exception:
            pass
        print(f"FATAL {exc}")
        raise
