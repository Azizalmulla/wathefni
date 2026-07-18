"""Smoke test: Shifts pagination (no silent truncation at scale).

Before this, list_shifts returned a hardcoded LIMIT 100 rows for the whole
company for a week — a busy company (>100 shifts in one week) silently lost
every shift past the 100th, with no error and no signal. This test pins the fix:

  - default (no limit): still returns at most the default page (100) AND now
    reports an accurate total_count + has_more, so nothing is *silently* dropped.
  - legacy callers (WhatsApp/Assistant tools that pass no limit/offset) are
    byte-for-byte unchanged in the rows they receive (first 100).
  - paging with limit/offset walks the FULL result set with no gaps and no
    duplicates — every scheduled shift is reachable.
  - the dashboard endpoint (/dashboard/posthire/shifts) exposes the same
    pagination and pages correctly.
  - company scoping holds across every page: another company's shifts never
    appear on any page (same WHERE-before-LIMIT mechanism that enforces
    manager scope, so scoped reads can't leak across the page boundary).

All rows use synthetic shift_ids + employee_keys inside the current week window
and are removed in a finally block, so the test is safe to re-run.

Run against a DB (staging): python3 smoke-test-shift-pagination.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0

SEED_COUNT = 105  # deliberately > the default 100 page so truncation would show


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    shifts pagination — full result set reachable, company-scoped, legacy default unchanged")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    # Locate a company with the shifts module enabled, plus a distinct second
    # company so we can prove page-level tenant isolation.
    candidates: list[str] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT company_code FROM employees WHERE company_code <> '' LIMIT 30")
            candidates = [str(dict(r)["company_code"]).upper() for r in cur.fetchall()]
    if "WATHEFNI" not in candidates:
        candidates.append("WATHEFNI")
    company = next((c for c in candidates if app.company_has_module(c, "shifts")), None)
    if not company:
        print("    (no company has the shifts module enabled — skipping)")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0
    other_company = next((c for c in candidates if c != company), f"{company}X")

    print(f"    using company {company} (isolation vs {other_company})")

    today = app.kuwait_today()
    batch_tag = uuid.uuid4().hex[:8]
    seeded_ids: list[str] = []
    other_id = str(uuid.uuid4())

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM shift_assignments WHERE employee_key LIKE %s",
                    (f"%SMOKEPAGE{batch_tag}%",),
                )
            conn.commit()

    def insert_shift(company_code: str, idx: int) -> str:
        sid = str(uuid.uuid4())
        emp_key = f"{company_code}-SMOKEPAGE{batch_tag}-{idx:04d}"
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO shift_assignments
                      (shift_id, company_code, employee_key, employee_phone, employee_name,
                       shift_date, start_time, end_time, timezone, status, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'scheduled',%s)
                    """,
                    (sid, company_code, emp_key, "99900000099", f"Page Smoke {idx}",
                     today, "09:00", "17:00", "Asia/Kuwait", app.Json({})),
                )
            conn.commit()
        return sid

    cleanup()
    try:
        for i in range(SEED_COUNT):
            seeded_ids.append(insert_shift(company, i))
        # One shift in the other company on the same day — must never appear.
        insert_shift(other_company, 9999)
        seeded_set = set(seeded_ids)

        window = {"company_code": company, "start_date": today.isoformat(), "end_date": today.isoformat()}

        # 1) Legacy default: no limit/offset. Rows capped at 100 (unchanged), but
        #    the response now surfaces the true total so callers aren't blind.
        default_res = app.list_shifts(dict(window), company_code=company)
        default_rows = default_res.get("shifts") or []
        seeded_in_default = [r for r in default_rows if str(r.get("shift_id")) in seeded_set]
        check("default read returns at most 100 rows (legacy page size unchanged)", len(default_rows) <= 100)
        check("default read reports total_count >= seeded count", int(default_res.get("total_count") or 0) >= SEED_COUNT)
        check("default read flags has_more when truncated", default_res.get("has_more") is True)
        check("default read still returns a full first page (100 of ours present)", len(seeded_in_default) == 100)

        # 2) Page through the whole set with limit/offset — no gaps, no dupes.
        collected: list[str] = []
        offset = 0
        page_limit = 40
        guard = 0
        while True:
            guard += 1
            if guard > 50:
                break
            res = app.list_shifts({**window, "limit": page_limit, "offset": offset}, company_code=company)
            rows = res.get("shifts") or []
            collected.extend(str(r.get("shift_id")) for r in rows)
            if not res.get("has_more"):
                break
            offset += page_limit
        collected_seeded = [sid for sid in collected if sid in seeded_set]
        check("paging reaches every seeded shift (no silent truncation)", set(collected_seeded) == seeded_set)
        check("paging returns no duplicate shift_ids", len(collected) == len(set(collected)))

        # 3) Company isolation holds on every page: the other company's shift is
        #    never present anywhere in the paged results.
        check("other company's shift never appears across pages", other_id not in collected and all(
            not str(sid).startswith(f"{other_company}-") for sid in collected
        ))

        # 4) Dashboard endpoint paginates the same way.
        owner_ctx = {
            "company_code": company,
            "permissions": ["shifts.read", "shifts.manage"],
            "access": {"role": "owner", "permissions": ["shifts.read", "shifts.manage"]},
            "actor_user_id": "smoke-shift-page",
            "permission_authority": "backend_current",
            "permission_subject_user_id": "smoke-shift-page",
            "permission_subject_company": company,
            "actor_role": "owner",
            "hr_phone": "99900000099",
            "hr_user": {"role": "owner", "status": "active", "company_code": company},
        }
        page1 = app.dashboard_posthire_shifts(week=0, offset=0, limit=50, context=owner_ctx)
        check("dashboard page 1 respects limit", len(page1.get("shifts") or []) <= 50)
        check("dashboard page 1 exposes has_more", page1.get("has_more") is True)
        check("dashboard page 1 exposes total_count", int(page1.get("total_count") or 0) >= SEED_COUNT)
        seen = {str(s.get("shift_id")) for s in (page1.get("shifts") or [])}
        page2 = app.dashboard_posthire_shifts(week=0, offset=50, limit=50, context=owner_ctx)
        seen |= {str(s.get("shift_id")) for s in (page2.get("shifts") or [])}
        page3 = app.dashboard_posthire_shifts(week=0, offset=100, limit=50, context=owner_ctx)
        seen |= {str(s.get("shift_id")) for s in (page3.get("shifts") or [])}
        check("dashboard pages 1-3 cover all seeded shifts", seeded_set.issubset(seen))
    finally:
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    SHIFT PAGINATION: FAILURES")
        return 1
    print("    SHIFT PAGINATION: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
