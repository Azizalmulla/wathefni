"""Compliance search + pagination smoke test (staging).

Verifies the company-scoped Compliance read endpoint under scale:
  - `summary` bucket counts are ALWAYS computed over the full classified set,
    regardless of bucket filter / search / paging (chips stay accurate),
  - opt-in pagination (limit/offset) returns bounded, non-overlapping pages that
    reassemble to `filtered_total` with correct `has_more`,
  - the bucket filter narrows `documents` (and `filtered_total`) to one bucket,
  - free-text search matches employee name, document label, and department,
  - documents never leak across companies (tenant isolation), and
  - the legacy no-arg call still returns the full document list unchanged.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-compliance-search.py

NEVER point this at the production database: it writes and deletes test companies.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
from psycopg2.extras import Json

COMPANY_A = "COMPLIANCESEARCHA"   # scale + search subject
COMPANY_B = "COMPLIANCESEARCHB"   # isolation control
MARKER = "temporary_compliance_search_smoke"
TODAY = app.kuwait_today()

BULK_EMPLOYEES = 250              # all expired civil_id -> one big bucket to page
ZEBRA_COUNT = 3                   # unique searchable name
FALCON_COUNT = 4                  # unique searchable department
TOTAL_A = BULK_EMPLOYEES + ZEBRA_COUNT + FALCON_COUNT


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:
            self.failed.append(f"{label} -> raised {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def report(self) -> int:
        for label in self.passed:
            print(f"      PASS  {label}")
        for label in self.failed:
            print(f"      FAIL  {label}")
        print(f"\n    {len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def _employees_columns(cur: Any) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='employees'")
    return {row["column_name"] for row in cur.fetchall()}


def _insert_employee(cur: Any, columns: set[str], company: str, emp_key: str, name: str, department: str) -> None:
    desired: dict[str, Any] = {
        "company_code": company,
        "phone": emp_key,
        "name": name,
        "email": f"{emp_key}@example.com",
        "employee_key": emp_key,
        "position_title": "Field Technician",
        "department": department,
        "onboarding_status": "complete",
        "status": "active",
        "raw_json": Json({"smoke": MARKER, "department": department}),
        "profile": Json({"smoke": MARKER, "department": department}),
    }
    cols = [c for c in desired if c in columns]
    placeholders = ",".join(["%s"] * len(cols))
    cur.execute(f"INSERT INTO employees ({','.join(cols)}) VALUES ({placeholders})", [desired[c] for c in cols])


def _insert_doc(cur: Any, emp_key: str, document_type: str, expiry_offset_days: int) -> None:
    expiry = TODAY + app.timedelta(days=expiry_offset_days)
    cur.execute(
        """
        INSERT INTO compliance_documents (employee_key, document_type, label, status, expiry_date, raw_json)
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (emp_key, document_type, None, "valid", expiry, Json({"smoke": MARKER})),
    )


def _all_a_keys() -> list[str]:
    keys = [f"{COMPANY_A}-bulk{i}" for i in range(BULK_EMPLOYEES)]
    keys += [f"{COMPANY_A}-zebra{i}" for i in range(ZEBRA_COUNT)]
    keys += [f"{COMPANY_A}-falcon{i}" for i in range(FALCON_COUNT)]
    return keys


def _purge(cur: Any) -> None:
    all_keys = _all_a_keys() + [f"{COMPANY_B}-emp0"]
    cur.execute("DELETE FROM compliance_documents WHERE employee_key = ANY(%s)", (all_keys,))
    cur.execute("DELETE FROM employees WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
    cur.execute("DELETE FROM company_modules WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Compliance Search {company[-1]}", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
                cur.execute(
                    "INSERT INTO company_modules (company_code, module_key, enabled) VALUES (%s,'compliance',TRUE) "
                    "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=TRUE",
                    (company,),
                )
            _purge(cur)
            columns = _employees_columns(cur)
            # Bulk: all expired civil_id (one big "expired" bucket to page through).
            for i in range(BULK_EMPLOYEES):
                key = f"{COMPANY_A}-bulk{i}"
                _insert_employee(cur, columns, COMPANY_A, key, f"A Employee {i}", "Operations")
                _insert_doc(cur, key, "civil_id", -10)
            # Searchable by name: "Zebra Uniquename".
            for i in range(ZEBRA_COUNT):
                key = f"{COMPANY_A}-zebra{i}"
                _insert_employee(cur, columns, COMPANY_A, key, f"Zebra Uniquename {i}", "Operations")
                _insert_doc(cur, key, "civil_id", -10)
            # Searchable by department: "Falcon Wing".
            for i in range(FALCON_COUNT):
                key = f"{COMPANY_A}-falcon{i}"
                _insert_employee(cur, columns, COMPANY_A, key, f"A Falconer {i}", "Falcon Wing")
                _insert_doc(cur, key, "civil_id", -10)
            # Company B: one expired doc, used to prove isolation from A.
            b_key = f"{COMPANY_B}-emp0"
            _insert_employee(cur, columns, COMPANY_B, b_key, "B Employee 0", "Operations")
            _insert_doc(cur, b_key, "civil_id", -10)
        conn.commit()


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            _purge(cur)
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
        conn.commit()


def _page_keys(company: str, *, bucket: str = "", search: str = "", limit: int = 100) -> tuple[list[tuple[str, str]], int]:
    """Collect every (employee_key, document_type) across paged calls, plus filtered_total."""
    seen: list[tuple[str, str]] = []
    offset = 0
    filtered_total = 0
    for _ in range(1000):  # generous upper bound; test data is small
        payload = app.dashboard_compliance_payload(company, bucket_filter=bucket, search=search, offset=offset, limit=limit)
        filtered_total = int(payload["filtered_total"])
        docs = payload["documents"]
        seen.extend((str(d["employee_key"]), str(d["document_type"])) for d in docs)
        if not payload["has_more"] or not docs:
            break
        offset += len(docs)
    return seen, filtered_total


def run_checks(checks: Checks) -> None:
    # 1) Legacy no-arg call is unchanged: full document list, summary over full set.
    legacy = app.dashboard_compliance_payload(COMPANY_A)
    checks.check("legacy call returns full document list", lambda: len(legacy["documents"]) == TOTAL_A)
    checks.check("legacy summary.total_documents == TOTAL_A", lambda: int(legacy["summary"]["total_documents"]) == TOTAL_A)
    checks.check("legacy summary.expired == TOTAL_A (all expired)", lambda: int(legacy["summary"]["expired"]) == TOTAL_A)

    # 2) Default page is bounded and reports the true filtered total + has_more.
    first = app.dashboard_compliance_payload(COMPANY_A, limit=100)
    checks.check("default page caps at limit=100", lambda: len(first["documents"]) == 100)
    checks.check("filtered_total == TOTAL_A when unfiltered", lambda: int(first["filtered_total"]) == TOTAL_A)
    checks.check("has_more True when more remain", lambda: first["has_more"] is True)
    checks.check("summary stays full even on a bounded page", lambda: int(first["summary"]["total_documents"]) == TOTAL_A)

    # 3) Pagination reassembles to the full set with no duplicates.
    seen, total = _page_keys(COMPANY_A, limit=100)
    checks.check("paging reports filtered_total == TOTAL_A", lambda: total == TOTAL_A)
    checks.check("paging visits every document once", lambda: len(seen) == TOTAL_A)
    checks.check("paging has no duplicate rows", lambda: len(set(seen)) == TOTAL_A)

    # 4) Bucket filter narrows documents + filtered_total (summary still full).
    expired = app.dashboard_compliance_payload(COMPANY_A, bucket_filter="expired", limit=100)
    checks.check("bucket=expired filtered_total == TOTAL_A", lambda: int(expired["filtered_total"]) == TOTAL_A)
    checks.check("bucket=expired summary still full", lambda: int(expired["summary"]["total_documents"]) == TOTAL_A)
    valid = app.dashboard_compliance_payload(COMPANY_A, bucket_filter="valid", limit=100)
    checks.check("bucket=valid filtered_total == 0 (none valid)", lambda: int(valid["filtered_total"]) == 0)
    checks.check("bucket=valid returns no rows", lambda: len(valid["documents"]) == 0)
    checks.check("bucket=valid summary still full", lambda: int(valid["summary"]["total_documents"]) == TOTAL_A)

    # 5) Free-text search matches name and department; summary stays full.
    zebra = app.dashboard_compliance_payload(COMPANY_A, search="zebra", limit=100)
    checks.check("search 'zebra' matches name -> ZEBRA_COUNT", lambda: int(zebra["filtered_total"]) == ZEBRA_COUNT)
    checks.check("search 'zebra' rows all Zebra", lambda: all("Zebra" in str(d["employee_name"]) for d in zebra["documents"]))
    falcon = app.dashboard_compliance_payload(COMPANY_A, search="falcon wing", limit=100)
    checks.check("search 'falcon wing' matches department -> FALCON_COUNT", lambda: int(falcon["filtered_total"]) == FALCON_COUNT)
    civ = app.dashboard_compliance_payload(COMPANY_A, search="civil", limit=100)
    checks.check("search 'civil' matches document label -> TOTAL_A", lambda: int(civ["filtered_total"]) == TOTAL_A)
    none = app.dashboard_compliance_payload(COMPANY_A, search="no-such-person-xyz", limit=100)
    checks.check("search miss -> filtered_total 0", lambda: int(none["filtered_total"]) == 0 and len(none["documents"]) == 0)
    checks.check("search miss summary still full", lambda: int(none["summary"]["total_documents"]) == TOTAL_A)

    # 6) Bucket + search combine.
    combo = app.dashboard_compliance_payload(COMPANY_A, bucket_filter="expired", search="zebra", limit=100)
    checks.check("bucket+search combine -> ZEBRA_COUNT", lambda: int(combo["filtered_total"]) == ZEBRA_COUNT)

    # 7) Tenant isolation: A never sees B; B only sees its own.
    a_keys = set(_all_a_keys())
    checks.check("A documents only reference A employees", lambda: all(str(d["employee_key"]) in a_keys for d in legacy["documents"]))
    payload_b = app.dashboard_compliance_payload(COMPANY_B)
    checks.check("B payload excludes A employees", lambda: all(str(d["employee_key"]).startswith(COMPANY_B) for d in payload_b["documents"]))
    checks.check("B has exactly its own 1 document", lambda: int(payload_b["summary"]["total_documents"]) == 1)


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"compliance search smoke — companies {COMPANY_A}/{COMPANY_B} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    print("    COMPLIANCE SEARCH: " + ("ALL CHECKS PASSED" if not code else "FAILURES PRESENT"))
    sys.exit(code)


if __name__ == "__main__":
    main()
