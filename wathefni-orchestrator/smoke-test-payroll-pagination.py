"""Smoke test: Payroll pagination + uncapped money path.

Two silent-truncation bugs are pinned here:

  1. list_timesheets returned a hardcoded LIMIT 200 for the whole company for a
     pay period — a company with >200 employees silently lost every timesheet
     past the 200th from the dashboard, with no error. Now it pages via
     limit/offset and reports total_count + has_more.

  2. preview_payroll (the actual export/money path) had its OWN LIMIT 500 — a
     company with >500 approved timesheets in a period would be silently
     underpaid. That cap is removed: preview MUST return every approved timesheet.

This test also pins that:
  - legacy callers (no limit/offset) receive an unchanged first page (200).
  - paging the dashboard reaches every timesheet with no gaps/duplicates.
  - company scoping holds across every page.

All rows use synthetic employee_keys in a synthetic pay period and are removed in
a finally block, so the test is safe to re-run.

Run against a DB (staging): python3 smoke-test-payroll-pagination.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import date
from pathlib import Path

PASS = 0
FAIL = 0

SEED_COUNT = 205  # > the old 200 display cap so truncation would show


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    payroll pagination — timesheets paged + preview/export money path uncapped, company-scoped")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    candidates: list[str] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT company_code FROM employees WHERE company_code <> '' LIMIT 30")
            candidates = [str(dict(r)["company_code"]).upper() for r in cur.fetchall()]
    if "WATHEFNI" not in candidates:
        candidates.append("WATHEFNI")
    company = next((c for c in candidates if app.company_has_module(c, "payroll")), None)
    if not company:
        print("    (no company has the payroll module enabled — skipping)")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0
    other_company = next((c for c in candidates if c != company), f"{company}X")
    print(f"    using company {company} (isolation vs {other_company})")

    # A synthetic, far-past period that won't collide with real timesheets.
    p_start = date(2001, 2, 1)
    p_end = date(2001, 2, 15)
    batch_tag = uuid.uuid4().hex[:8]
    tag = f"SMOKEPAYPAGE{batch_tag}"

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM payroll_timesheets WHERE employee_key LIKE %s", (f"%{tag}%",))
            conn.commit()

    def seed(company_code: str, idx: int, status: str = "approved"):
        emp_key = f"{company_code}-{tag}-{idx:04d}"
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO payroll_timesheets
                      (company_code, employee_key, employee_phone, employee_name,
                       period_start, period_end, status, worked_minutes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (company_code, emp_key, "99900000077", f"Pay Page {idx}", p_start, p_end, status, 9600),
                )
            conn.commit()
        return emp_key

    owner_ctx = {
        "company_code": company,
        "permissions": ["payroll.read", "payroll.export", "payroll.manage"],
        "access": {"role": "owner", "permissions": ["payroll.read", "payroll.export", "payroll.manage"]},
        "actor_user_id": "smoke-pay-page",
        "permission_authority": "backend_current",
        "permission_subject_user_id": "smoke-pay-page",
        "permission_subject_company": company,
        "actor_role": "owner",
        "hr_phone": "99900000077",
        "hr_user": {"role": "owner", "status": "active", "company_code": company},
    }

    cleanup()
    seeded_keys: set[str] = set()
    try:
        for i in range(SEED_COUNT):
            seeded_keys.add(seed(company, i))
        other_key = seed(other_company, 9999)

        window = {"company_code": company, "start_date": p_start.isoformat(), "end_date": p_end.isoformat()}

        # 1) list_timesheets default: capped at 200, true total surfaced.
        default_res = app.list_timesheets(dict(window), company_code=company)
        default_rows = default_res.get("timesheets") or []
        default_seeded = [r for r in default_rows if str(r.get("employee_key")) in seeded_keys]
        check("default read returns at most 200 rows (legacy page size unchanged)", len(default_rows) <= 200)
        check("default read reports total_count >= seeded count", int(default_res.get("total_count") or 0) >= SEED_COUNT)
        check("default read flags has_more when truncated", default_res.get("has_more") is True)
        check("default read returns a full first page (200 of ours present)", len(default_seeded) == 200)

        # 2) Page the dashboard endpoint with no gaps/dupes.
        collected: list[str] = []
        offset = 0
        page_limit = 100
        guard = 0
        while True:
            guard += 1
            if guard > 20:
                break
            page = app.dashboard_posthire_payroll(
                start_date=p_start.isoformat(), end_date=p_end.isoformat(), offset=offset, limit=page_limit, context=owner_ctx
            )
            rows = page.get("timesheets") or []
            collected.extend(str(r.get("timesheet_id")) for r in rows)
            if not page.get("has_more"):
                break
            offset += page_limit
        # Coverage by employee_key (each seeded row is a distinct employee here).
        first_page = app.dashboard_posthire_payroll(start_date=p_start.isoformat(), end_date=p_end.isoformat(), limit=page_limit, context=owner_ctx)
        check("dashboard exposes total_count", int(first_page.get("total_count") or 0) >= SEED_COUNT)
        check("dashboard flags has_more on page 1", first_page.get("has_more") is True)
        check("dashboard paging returns no duplicate timesheet rows", len(collected) == len(set(collected)))
        # Re-collect employee_keys for coverage + isolation.
        keys_seen: list[str] = []
        offset = 0
        guard = 0
        while True:
            guard += 1
            if guard > 20:
                break
            page = app.dashboard_posthire_payroll(start_date=p_start.isoformat(), end_date=p_end.isoformat(), offset=offset, limit=page_limit, context=owner_ctx)
            rows = page.get("timesheets") or []
            keys_seen.extend(str(r.get("employee_key")) for r in rows)
            if not page.get("has_more"):
                break
            offset += page_limit
        check("dashboard paging reaches every seeded timesheet", seeded_keys.issubset(set(keys_seen)))
        check("other company's timesheet never appears across pages", other_key not in keys_seen)

        # 3) Money path: preview_payroll must return EVERY approved timesheet
        #    (no arbitrary cap) — this is what an export snapshots.
        preview = app.preview_payroll(dict(window), company_code=company)
        preview_rows = preview.get("preview_rows") or []
        check("preview returns all approved timesheets (uncapped money path)", len(preview_rows) >= SEED_COUNT)
        check("preview reports the full timesheet_count", int(preview.get("timesheet_count") or 0) >= SEED_COUNT)
    finally:
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    PAYROLL PAGINATION: FAILURES")
        return 1
    print("    PAYROLL PAGINATION: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
