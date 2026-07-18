"""Smoke test: Leave pagination (no silent truncation at scale).

Before this, the active leave view returned a hardcoded LIMIT 50 per section for
the whole company — a company with >50 pending or upcoming requests (easy during
a holiday season) silently lost every request past the 50th, with no error. This
test pins the fix:

  - list_leave_requests default (no offset): still returns at most the default
    page (50) AND now reports an accurate total_count + has_more.
  - legacy callers (no limit/offset) are unchanged in the rows they receive.
  - the active dashboard view pages the pending section via section=pending +
    offset with no gaps and no duplicates — every request is reachable.
  - the history view pages the same way.
  - company scoping holds across every page (another company's requests never
    appear), the same WHERE-before-LIMIT mechanism that enforces manager scope.

All rows use synthetic employee_keys and are removed in a finally block, so the
test is safe to re-run.

Run against a DB (staging): python3 smoke-test-leave-pagination.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import timedelta
from pathlib import Path

PASS = 0
FAIL = 0

SEED_COUNT = 55  # deliberately > the default 50 page so truncation would show


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    leave pagination — full result set reachable, company-scoped, legacy default unchanged")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    today = app.kuwait_today()

    candidates: list[str] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT company_code FROM employees WHERE company_code <> '' LIMIT 30")
            candidates = [str(dict(r)["company_code"]).upper() for r in cur.fetchall()]
    if "WATHEFNI" not in candidates:
        candidates.append("WATHEFNI")
    company = next((c for c in candidates if app.company_has_module(c, "leave")), None)
    if not company:
        print("    (no company has the leave module enabled — skipping)")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0
    other_company = next((c for c in candidates if c != company), f"{company}X")
    print(f"    using company {company} (isolation vs {other_company})")

    batch_tag = uuid.uuid4().hex[:8]
    tag = f"SMOKELEAVEPAGE{batch_tag}"

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM leave_requests WHERE employee_key LIKE %s", (f"%{tag}%",))
            conn.commit()

    def seed(company_code: str, idx: int, status: str = "requested"):
        emp_key = f"{company_code}-{tag}-{idx:04d}"
        start = (today + timedelta(days=5)).isoformat()
        end = (today + timedelta(days=6)).isoformat()
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO leave_requests
                      (company_code, employee_key, employee_phone, employee_name,
                       start_date, end_date, leave_type, status, reason, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,'annual',%s,'smoke',%s)
                    """,
                    (company_code, emp_key, "99900000088", f"Leave Page {idx}",
                     start, end, status, app.Json({})),
                )
            conn.commit()
        return emp_key

    owner_ctx = {
        "company_code": company,
        "permissions": ["leave.read", "leave.request", "leave.decide"],
        "access": {"role": "owner", "permissions": ["leave.read", "leave.request", "leave.decide"]},
        "actor_user_id": "smoke-leave-page",
        "permission_authority": "backend_current",
        "permission_subject_user_id": "smoke-leave-page",
        "permission_subject_company": company,
        "actor_role": "owner",
        "hr_phone": "99900000088",
        "hr_user": {"role": "owner", "status": "active", "company_code": company},
    }

    cleanup()
    seeded_keys: set[str] = set()
    try:
        for i in range(SEED_COUNT):
            seeded_keys.add(seed(company, i))
        other_key = seed(other_company, 9999)

        # 1) list_leave_requests default (no offset): capped at 50, true total.
        window_start = (today - timedelta(days=7)).isoformat()
        window_end = (today + timedelta(days=60)).isoformat()
        default_res = app.list_leave_requests(
            {"company_code": company, "status": "requested", "start_date": window_start, "end_date": window_end},
            company_code=company,
        )
        default_rows = default_res.get("leave_requests") or []
        check("default read returns at most 50 rows (legacy page size unchanged)", len(default_rows) <= 50)
        check("default read reports total_count >= seeded count", int(default_res.get("total_count") or 0) >= SEED_COUNT)
        check("default read flags has_more when truncated", default_res.get("has_more") is True)
        # total >= 55 > the 50 page, so the first page must be full. (We assert a
        # full page rather than "50 of *ours*": a pending/awaiting-decision read is
        # intentionally NOT bounded by the date window anymore — a request awaiting
        # HR must never be hidden by when its dates fall — so the company's other
        # pending rows can legitimately share the page. Full reachability of the
        # seeded set is proven by the paging loop below.)
        check("default read returns a full first page (50 rows)", len(default_rows) == 50)

        # 2) Active dashboard view pages the pending section with no gaps/dupes.
        # Row identity is leave_id (an employee can legitimately have several
        # requests); employee_key is only used to confirm our seeded set is fully
        # reachable and that the other company never leaks in.
        first = app.dashboard_posthire_leave(view="active", context=owner_ctx)
        collected_ids = [str(r.get("leave_id")) for r in (first.get("pending") or [])]
        collected_keys = [str(r.get("employee_key")) for r in (first.get("pending") or [])]
        check("active initial pending page respects limit", len(first.get("pending") or []) <= 50)
        check("active view exposes pending_total", int(first.get("pending_total") or 0) >= SEED_COUNT)
        check("active view flags pending_has_more", first.get("pending_has_more") is True)
        offset = len(first.get("pending") or [])
        guard = 0
        while True:
            guard += 1
            if guard > 40:
                break
            page = app.dashboard_posthire_leave(view="active", section="pending", offset=offset, context=owner_ctx)
            rows = page.get("pending") or []
            collected_ids.extend(str(r.get("leave_id")) for r in rows)
            collected_keys.extend(str(r.get("employee_key")) for r in rows)
            offset += len(rows)
            if not page.get("pending_has_more"):
                break
        check("paging reaches every seeded pending request (no silent truncation)", seeded_keys.issubset(set(collected_keys)))
        check("paging returns no duplicate rows", len(collected_ids) == len(set(collected_ids)))
        check("other company's request never appears across pages", other_key not in collected_keys)

        # 3) History view paginates the same way (all statuses in the window).
        # History legitimately has many rows per employee, so uniqueness is on
        # leave_id (the row PK), not employee_key.
        h_first = app.dashboard_posthire_leave(view="history", context=owner_ctx)
        check("history exposes history_total", int(h_first.get("history_total") or 0) >= SEED_COUNT)
        hist_ids = [str(r.get("leave_id")) for r in (h_first.get("history") or [])]
        hist_keys = [str(r.get("employee_key")) for r in (h_first.get("history") or [])]
        has_more = bool(h_first.get("history_has_more"))
        h_offset = len(h_first.get("history") or [])
        guard = 0
        while has_more and guard <= 60:
            guard += 1
            hp = app.dashboard_posthire_leave(view="history", offset=h_offset, context=owner_ctx)
            hrows = hp.get("history") or []
            hist_ids.extend(str(r.get("leave_id")) for r in hrows)
            hist_keys.extend(str(r.get("employee_key")) for r in hrows)
            h_offset += len(hrows)
            has_more = bool(hp.get("history_has_more"))
        check("history paging reaches every seeded row", seeded_keys.issubset(set(hist_keys)))
        check("history paging has no duplicate rows (by leave_id)", len(hist_ids) == len(set(hist_ids)))
    finally:
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    LEAVE PAGINATION: FAILURES")
        return 1
    print("    LEAVE PAGINATION: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
