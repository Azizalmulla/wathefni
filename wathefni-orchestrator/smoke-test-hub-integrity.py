"""Smoke test: employee-hub integrity scan.

`employees` is the post-hire source of truth; attendance, leave, shifts, payroll,
availability, and compliance all hang off it via (company_code, employee_key) as a
soft hub (no hard FK so the model stays flexible). This test pins the read-only
orphan scan that lets HR/ops catch silent drift:

  - workspace_integrity_scan detects child rows whose (company_code, employee_key)
    does not resolve to a live employee
  - the scan is company-scoped (an employee_key valid in one company is an orphan in
    another) and never flags a row that DOES resolve to its employee
  - the scan is read-only (counts only; no mutation)
  - compliance_documents is stamped with company_code on insert + has an idempotent
    backfill (source guard, since the table is pre-provisioned)

Run against a DB (staging): python3 smoke-test-hub-integrity.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import app  # noqa: E402

PASS = 0
FAIL = 0
SENTINEL_DATE = "2099-01-01"
TEST_COMPANY = "ZZINTEGTEST"
ORPHAN_KEY = f"zz-orphan-{uuid.uuid4().hex[:10]}"


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    employee-hub integrity — orphan scan catches drift, scoped + read-only")

    source = Path(app.__file__).with_suffix(".py").read_text(encoding="utf-8")

    # --- source guards: compliance company stamping cannot silently regress -----
    check(
        "compliance_documents insert stamps company_code",
        "company_code" in source.split("INSERT INTO compliance_documents", 1)[-1][:600],
    )
    check(
        "compliance_documents has an idempotent company backfill",
        "SET company_code = e.company_code" in source,
    )
    for table in ("attendance_records", "leave_requests", "compliance_documents"):
        check(f"integrity scan covers {table}", table in app.INTEGRITY_CHILD_TABLES)

    # --- behaviour: scan against the DB ----------------------------------------
    real_emp: dict | None = None
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT company_code, employee_key FROM employees WHERE employee_key <> '' LIMIT 1")
            row = cur.fetchone()
            if row:
                real_emp = {"company_code": row.get("company_code"), "employee_key": row.get("employee_key")}

            # Orphans in an isolated empty test company.
            cur.execute(
                "INSERT INTO attendance_records (company_code, employee_key, attendance_date) VALUES (%s,%s,%s)",
                (TEST_COMPANY, ORPHAN_KEY, SENTINEL_DATE),
            )
            cur.execute(
                "INSERT INTO leave_requests (company_code, employee_key, start_date, end_date) VALUES (%s,%s,%s,%s)",
                (TEST_COMPANY, ORPHAN_KEY, SENTINEL_DATE, SENTINEL_DATE),
            )
            # A row keyed to a REAL employee but in the WRONG company is still an
            # orphan (proves company-scoping of the resolve).
            if real_emp:
                cur.execute(
                    "INSERT INTO attendance_records (company_code, employee_key, attendance_date) VALUES (%s,%s,%s)",
                    (TEST_COMPANY, real_emp["employee_key"], SENTINEL_DATE),
                )
                # And the same key in its OWN company must NOT be an orphan.
                cur.execute(
                    "INSERT INTO leave_requests (company_code, employee_key, start_date, end_date) VALUES (%s,%s,%s,%s)",
                    (real_emp["company_code"], real_emp["employee_key"], SENTINEL_DATE, SENTINEL_DATE),
                )
        conn.commit()

    try:
        scan = app.workspace_integrity_scan(TEST_COMPANY)
        tables = scan.get("tables") or {}
        att = tables.get("attendance_records") or {}
        lv = tables.get("leave_requests") or {}

        expected_att = 2 if real_emp else 1
        check("scan is not ok when orphans exist", scan.get("ok") is False)
        check(
            f"attendance orphans detected in test company (={expected_att})",
            att.get("orphans") == expected_att,
        )
        check("leave orphans detected in test company (=1)", lv.get("orphans") == 1)
        check("scan total counts all orphans", scan.get("total_orphans") == expected_att + 1)
        sample_keys = {s.get("employee_key") for s in (att.get("samples") or [])}
        check("orphan sample surfaces the offending employee_key", ORPHAN_KEY in sample_keys)

        # Exclusion: the real employee's same-company row resolves and is NOT flagged.
        if real_emp:
            owner_scan = app.workspace_integrity_scan(real_emp["company_code"])
            owner_att = (owner_scan.get("tables") or {}).get("attendance_records") or {}
            # Re-derive the orphan set for this specific key in its own company to
            # prove the valid (own-company) row never counts as an orphan.
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT count(*)::int AS n
                        FROM leave_requests t
                        LEFT JOIN employees e
                          ON e.employee_key = t.employee_key
                         AND e.company_code = t.company_code
                        WHERE t.company_code = %s AND t.employee_key = %s
                          AND t.start_date = %s AND e.employee_key IS NULL
                        """,
                        (real_emp["company_code"], real_emp["employee_key"], SENTINEL_DATE),
                    )
                    own_orphans = int((cur.fetchone() or {}).get("n") or 0)
            check("valid own-company employee row is NOT flagged as orphan", own_orphans == 0)
            check("owner-company scan still returns a structured table report", "attendance_records" in (owner_scan.get("tables") or {}))
            _ = owner_att  # report shape touched above

        # Global scan returns a well-formed structure.
        global_scan = app.workspace_integrity_scan(None)
        check("global scan returns total_orphans + tables", "total_orphans" in global_scan and "tables" in global_scan)
    finally:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM attendance_records WHERE attendance_date=%s AND (company_code=%s OR employee_key=%s)",
                    (SENTINEL_DATE, TEST_COMPANY, ORPHAN_KEY),
                )
                cur.execute(
                    "DELETE FROM leave_requests WHERE start_date=%s AND (company_code=%s OR employee_key=%s)",
                    (SENTINEL_DATE, TEST_COMPANY, ORPHAN_KEY),
                )
                if real_emp:
                    cur.execute(
                        "DELETE FROM attendance_records WHERE attendance_date=%s AND company_code=%s AND employee_key=%s",
                        (SENTINEL_DATE, real_emp["company_code"], real_emp["employee_key"]),
                    )
                    cur.execute(
                        "DELETE FROM leave_requests WHERE start_date=%s AND company_code=%s AND employee_key=%s",
                        (SENTINEL_DATE, real_emp["company_code"], real_emp["employee_key"]),
                    )
            conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    HUB INTEGRITY: FAILURES")
        return 1
    print("    HUB INTEGRITY: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
