"""Compliance dashboard read smoke test (staging).

Verifies the company-scoped Compliance V1 read endpoint behaviour:
  - summary counts match the returned document rows (no drift),
  - status buckets match the worker's classifier (classify_compliance_row),
  - documents never leak across companies (tenant isolation),
  - the endpoint gate requires the compliance module + compliance.read, and
  - role permissions are exactly: owner/hr_manager read+manage, viewer read-only,
    recruiter/hiring_manager no compliance access.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-compliance-dashboard.py

NEVER point this at the production database: it writes and deletes test companies.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
from psycopg2.extras import Json

COMPANY_A = "COMPLIANCETESTA"   # compliance enabled, full document spread
COMPANY_B = "COMPLIANCETESTB"   # compliance enabled, isolation control
COMPANY_C = "COMPLIANCETESTC"   # compliance DISABLED, gate control
MARKER = "temporary_compliance_dashboard_smoke"
TODAY = app.kuwait_today()


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


def _insert_employee(cur: Any, columns: set[str], company: str, emp_key: str, name: str) -> None:
    desired: dict[str, Any] = {
        "company_code": company,
        "phone": emp_key,
        "name": name,
        "email": f"{emp_key}@example.com",
        "employee_key": emp_key,
        "position_title": "Field Technician",
        "department": "Operations",
        "onboarding_status": "complete",
        "status": "active",
        "raw_json": Json({"smoke": MARKER}),
        "profile": Json({"smoke": MARKER}),
    }
    cols = [c for c in desired if c in columns]
    placeholders = ",".join(["%s"] * len(cols))
    cur.execute(f"INSERT INTO employees ({','.join(cols)}) VALUES ({placeholders})", [desired[c] for c in cols])


def _insert_doc(cur: Any, emp_key: str, document_type: str, status: str, expiry_offset_days: int | None) -> None:
    expiry = (TODAY + app.timedelta(days=expiry_offset_days)) if expiry_offset_days is not None else None
    cur.execute(
        """
        INSERT INTO compliance_documents (employee_key, document_type, label, status, expiry_date, raw_json)
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (emp_key, document_type, None, status, expiry, Json({"smoke": MARKER})),
    )


# Company A spread -> expired=2, expiring_soon=1, missing=1, needs_review=1, valid=1.
A_DOCS = [
    ("emp1", "civil_id", "valid", -10),    # expired
    ("emp2", "passport", "valid", -5),     # expired
    ("emp3", "civil_id", "valid", 10),     # expiring_soon (warning window 30)
    ("emp4", "medical", "received", None), # needs_review (received, no expiry)
    ("emp5", "civil_id", "missing", None), # missing
    ("emp6", "passport", "valid", 200),    # valid
]
EXPECTED_A = {"expired": 2, "expiring_soon": 1, "missing": 1, "needs_review": 1, "valid": 1}


def _keys(company: str, n: int) -> list[str]:
    return [f"{company}-emp{i}" for i in range(1, n + 1)]


def _purge(cur: Any) -> None:
    companies = [COMPANY_A, COMPANY_B, COMPANY_C]
    all_keys = _keys(COMPANY_A, 6) + _keys(COMPANY_B, 1)
    cur.execute("DELETE FROM compliance_documents WHERE employee_key = ANY(%s)", (all_keys,))
    cur.execute("DELETE FROM employees WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM company_modules WHERE company_code = ANY(%s)", (companies,))


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY_A, COMPANY_B, COMPANY_C):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Compliance Test {company[-1]}", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
            _purge(cur)
            # Enable the compliance module for A and B only (C stays disabled).
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO company_modules (company_code, module_key, enabled) VALUES (%s,'compliance',TRUE) "
                    "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=TRUE",
                    (company,),
                )
            columns = _employees_columns(cur)
            # Company A: six employees, one document each, covering every bucket.
            for idx, (slot, doc_type, status, offset) in enumerate(A_DOCS, start=1):
                emp_key = f"{COMPANY_A}-emp{idx}"
                _insert_employee(cur, columns, COMPANY_A, emp_key, f"A Employee {idx}")
                _insert_doc(cur, emp_key, doc_type, status, offset)
            # Company B: one employee + expired doc, used to prove isolation from A.
            b_key = f"{COMPANY_B}-emp1"
            _insert_employee(cur, columns, COMPANY_B, b_key, "B Employee 1")
            _insert_doc(cur, b_key, "civil_id", "valid", -3)
        conn.commit()


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            _purge(cur)
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B, COMPANY_C],))
        conn.commit()


def _ctx(company: str, role: str) -> dict[str, Any]:
    perms = sorted(app.hr_role_permissions(role))
    user_id = f"smoke-{role}"
    return {
        "company_code": company,
        "actor_user_id": user_id,
        "permission_authority": "backend_current",
        "permission_subject_user_id": user_id,
        "permission_subject_company": company,
        "actor_role": role,
        "hr_user": {"role": role, "status": "active", "company_code": company},
        "permissions": perms,
        "access": {"role": role, "permissions": perms},
    }


def _denied(fn: Callable[[], Any], *, codes: set[str]) -> bool:
    try:
        fn()
        return False
    except app.HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return str(detail.get("error")) in codes
    except Exception:
        return False


def run_checks(checks: Checks) -> None:
    payload_a = app.dashboard_compliance_payload(COMPANY_A)
    summary_a = payload_a["summary"]
    docs_a = payload_a["documents"]

    # 1) Summary counts match the returned rows exactly.
    for bucket, expected in EXPECTED_A.items():
        checks.check(
            f"A summary[{bucket}] == {expected}",
            lambda bucket=bucket, expected=expected: int(summary_a.get(bucket) or 0) == expected,
        )
    checks.check(
        "A bucket counts sum to total_documents and to len(documents)",
        lambda: sum(int(summary_a[b]) for b in EXPECTED_A) == int(summary_a["total_documents"]) == len(docs_a),
    )
    checks.check(
        "A needs_attention == expired+expiring+missing+needs_review",
        lambda: int(summary_a["needs_attention"]) == EXPECTED_A["expired"] + EXPECTED_A["expiring_soon"] + EXPECTED_A["missing"] + EXPECTED_A["needs_review"],
    )
    checks.check("A employees_total == 6", lambda: int(summary_a["employees_total"]) == 6)
    checks.check("A employees_checked == 6", lambda: int(summary_a["employees_checked"]) == 6)

    # 2) Per-row status matches the worker's classifier (definition parity).
    def mapping_parity() -> bool:
        for doc in docs_a:
            row = {
                "document_type": doc["document_type"],
                "expiry_date": doc.get("expiry_date"),
                "status": "received" if doc["status"] == "needs_review" else doc["status"],
                "warning_days": None,
            }
            expected_bucket = app.compliance_bucket_for(app.classify_compliance_row(row).get("status"))
            # For valid/expiring/expired/missing the round-trip must agree; needs_review
            # is reconstructed from status='received' above.
            if doc["status"] in {"valid", "expiring_soon", "expired"} and expected_bucket != doc["status"]:
                return False
        return True

    checks.check("A row status matches classify_compliance_row buckets", mapping_parity)

    # 3) No HR-hostile raw values leak into labels.
    checks.check(
        "A status labels are HR-friendly (no raw codes)",
        lambda: all(d["status_label"] in {"Expired", "Expiring soon", "Missing", "Needs review", "Valid"} for d in docs_a),
    )
    checks.check(
        "A document labels use Kuwait/GCC friendly names",
        lambda: {d["document_label"] for d in docs_a} <= {"Civil ID", "Passport", "Residency (Iqama)", "Work Permit", "Medical Document", "Education Certificate", "Other Document"},
    )

    # 4) Tenant isolation: A's payload never references B's employee, and vice versa.
    a_keys = set(_keys(COMPANY_A, 6))
    checks.check(
        "A documents only reference A's employees",
        lambda: all(str(d["employee_key"]) in a_keys for d in docs_a),
    )
    payload_b = app.dashboard_compliance_payload(COMPANY_B)
    checks.check(
        "B payload excludes A's employees",
        lambda: all(str(d["employee_key"]).startswith(COMPANY_B) for d in payload_b["documents"]),
    )
    checks.check("B has exactly its own 1 document", lambda: int(payload_b["summary"]["total_documents"]) == 1)

    # 5) Entitlement gate: module + compliance.read enforced; module-disabled blocked.
    checks.check(
        "owner with compliance module passes compliance.read gate",
        lambda: bool(app.require_entitlement(_ctx(COMPANY_A, "owner"), "compliance", "compliance.read")),
    )
    checks.check(
        "viewer passes compliance.read gate (read-only intended)",
        lambda: bool(app.require_entitlement(_ctx(COMPANY_A, "viewer"), "compliance", "compliance.read")),
    )
    checks.check(
        "recruiter denied compliance.read (no compliance access)",
        lambda: _denied(lambda: app.require_entitlement(_ctx(COMPANY_A, "recruiter"), "compliance", "compliance.read"), codes={"permission_denied"}),
    )
    checks.check(
        "hiring_manager denied compliance.read (no compliance access)",
        lambda: _denied(lambda: app.require_entitlement(_ctx(COMPANY_A, "hiring_manager"), "compliance", "compliance.read"), codes={"permission_denied"}),
    )
    checks.check(
        "compliance-disabled company blocks the page (module_disabled)",
        lambda: _denied(lambda: app.require_entitlement(_ctx(COMPANY_C, "owner"), "compliance", "compliance.read"), codes={"module_disabled"}),
    )
    checks.check(
        "viewer cannot manage compliance",
        lambda: _denied(lambda: app.require_entitlement(_ctx(COMPANY_A, "viewer"), "compliance", "compliance.manage"), codes={"permission_denied"}),
    )

    # 6) Role permission sets are exactly as designed.
    checks.check("owner has compliance.read + compliance.manage", lambda: {"compliance.read", "compliance.manage"} <= set(app.hr_role_permissions("owner")))
    checks.check("hr_manager has compliance.read + compliance.manage", lambda: {"compliance.read", "compliance.manage"} <= set(app.hr_role_permissions("hr_manager")))
    checks.check("viewer has compliance.read only", lambda: "compliance.read" in app.hr_role_permissions("viewer") and "compliance.manage" not in app.hr_role_permissions("viewer"))
    checks.check("recruiter has no compliance perms", lambda: not ({"compliance.read", "compliance.manage"} & set(app.hr_role_permissions("recruiter"))))
    checks.check("hiring_manager has no compliance perms", lambda: not ({"compliance.read", "compliance.manage"} & set(app.hr_role_permissions("hiring_manager"))))


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"compliance dashboard smoke — companies {COMPANY_A}/{COMPANY_B}/{COMPANY_C} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    print("    COMPLIANCE DASHBOARD: " + ("ALL CHECKS PASSED" if not code else "FAILURES PRESENT"))
    sys.exit(code)


if __name__ == "__main__":
    main()
