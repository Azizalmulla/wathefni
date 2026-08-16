"""Wave 1C hygiene — staging/local DB smoke (synthetic only).

Creates synthetic null-status employee + synthetic orphan messages, applies
dry-run → apply → rollback, and asserts integrity. Never touches known prod keys.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def main() -> int:
    os.environ.setdefault("WATHEFNI_ENV", os.environ.get("WATHEFNI_ENV", "staging"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import app
    import employee_hygiene_wave1c as hygiene

    company = "WATHEFNI"
    tag = uuid.uuid4().hex[:10]
    phone = f"965599{tag[:5]}" if len(tag) >= 5 else f"965599{tag}"
    phone = ("965599" + tag)[:11]
    # ensure 965 + 8 digits
    phone = "9655" + tag[:7]
    emp_key = f"{company}-{phone}"
    orphan_key = f"{company}-P0-DUP-W1C-{tag}"
    status_idem = f"wave1c-smoke-status:{emp_key}"
    orphan_idem = f"wave1c-smoke-orphan:{orphan_key}"

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                hygiene.ensure_hygiene_schema(cur)
                cur.execute("DELETE FROM employee_messages WHERE company_code=%s AND employee_key IN (%s,%s)", (company, emp_key, orphan_key))
                cur.execute("DELETE FROM employee_messages_quarantine WHERE company_code=%s AND employee_key IN (%s,%s)", (company, emp_key, orphan_key))
                cur.execute("DELETE FROM employee_hygiene_remediation_journal WHERE company_code=%s AND idempotency_key IN (%s,%s)", (company, status_idem, orphan_idem))
                cur.execute("DELETE FROM employee_status_changes WHERE employee_key=%s", (emp_key,))
                cur.execute("DELETE FROM employees WHERE employee_key=%s", (emp_key,))
            conn.commit()

    cleanup()
    try:
        # Seed synthetic null-status employee with hired-like evidence fields
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO employees (
                      employee_key, phone, company_code, name, onboarding_status, employment_status
                    ) VALUES (%s,%s,%s,%s,'in_progress',NULL)
                    """,
                    (emp_key, phone, company, f"W1C Smoke {tag}"),
                )
                # three orphan messages
                for i in range(3):
                    cur.execute(
                        """
                        INSERT INTO employee_messages (
                          company_code, employee_key, flow, template_key, status, body_preview, dedupe_key
                        ) VALUES (%s,%s,'shift','shift_assigned','failed',%s,%s)
                        """,
                        (company, orphan_key, f"synthetic orphan {tag} #{i}", f"w1c:{orphan_key}:{i}"),
                    )
            conn.commit()

        evidence = {
            "employee": {
                "employment_status": None,
                "app_key": f"{phone}-{company}-SMOKE",
                "onboarding_status": "in_progress",
            },
            "applications": [{"status": "hired"}],
            "attendance_records": {"count": 2},
            "shift_assignments": {"count": 1},
            "leave_requests": {"count": 0},
            "employee_messages": {"count": 0},
            "employee_status_changes": {"count": 0},
        }

        dry = hygiene.remediate_null_employment_status(
            app,
            company_code=company,
            employee_key=emp_key,
            evidence=evidence,
            reason="wave1c smoke: hired+activity evidence",
            idempotency_key=status_idem + ":dry",
            dry_run=True,
        )
        check("status dry-run", dry.get("status") == "dry_run")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (emp_key,))
                still = dict(cur.fetchone())["employment_status"]
        check("dry-run leaves null", still is None)

        applied = hygiene.remediate_null_employment_status(
            app,
            company_code=company,
            employee_key=emp_key,
            evidence=evidence,
            reason="wave1c smoke: hired+activity evidence",
            idempotency_key=status_idem,
            dry_run=False,
        )
        check("status applied", applied.get("status") == "applied")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (emp_key,))
                now = dict(cur.fetchone())["employment_status"]
        check("status now active", now == "active")

        replay = hygiene.remediate_null_employment_status(
            app,
            company_code=company,
            employee_key=emp_key,
            evidence=evidence,
            reason="wave1c smoke: hired+activity evidence",
            idempotency_key=status_idem,
            dry_run=False,
        )
        check("status idempotent replay", replay.get("status") == "idempotent")

        # Refuse without evidence
        refused = hygiene.remediate_null_employment_status(
            app,
            company_code=company,
            employee_key=emp_key,
            evidence={"employee": {"employment_status": None}},
            reason="should refuse",
            idempotency_key=status_idem + ":refuse",
            dry_run=False,
        )
        check("refuse guess", refused.get("status") == "refused")

        # Orphan quarantine
        qdry = hygiene.quarantine_orphan_employee_messages(
            app,
            company_code=company,
            employee_key=orphan_key,
            reason="wave1c smoke synthetic orphan",
            idempotency_key=orphan_idem + ":dry",
            dry_run=True,
        )
        check("orphan dry-run", qdry.get("status") == "dry_run" and qdry.get("count") == 3)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM employee_messages WHERE employee_key=%s", (orphan_key,))
                live_n = int(dict(cur.fetchone())["n"])
        check("dry-run keeps live messages", live_n == 3)

        qapply = hygiene.quarantine_orphan_employee_messages(
            app,
            company_code=company,
            employee_key=orphan_key,
            reason="wave1c smoke synthetic orphan",
            idempotency_key=orphan_idem,
            dry_run=False,
        )
        check("orphan quarantined", qapply.get("status") == "applied" and qapply.get("count") == 3)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM employee_messages WHERE employee_key=%s", (orphan_key,))
                live_n = int(dict(cur.fetchone())["n"])
                cur.execute("SELECT count(*) AS n FROM employee_messages_quarantine WHERE employee_key=%s AND restored_at IS NULL", (orphan_key,))
                q_n = int(dict(cur.fetchone())["n"])
        check("live messages removed", live_n == 0)
        check("quarantine archive has 3", q_n == 3)

        # Integrity: no orphans for this synthetic key
        scan = app.workspace_integrity_scan(company)
        orphan_samples = (scan.get("tables") or {}).get("employee_messages", {}).get("samples") or []
        check(
            "integrity no longer lists smoke orphan key",
            all(s.get("employee_key") != orphan_key for s in orphan_samples),
            orphan_samples,
        )

        # Rollback orphan then status
        restore = hygiene.restore_quarantined_employee_messages(app, company_code=company, idempotency_key=orphan_idem)
        check("orphan restore", restore.get("status") == "rolled_back" and restore.get("restored") == 3)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM employee_messages WHERE employee_key=%s", (orphan_key,))
                live_n = int(dict(cur.fetchone())["n"])
        check("messages restored to live", live_n == 3)

        rb = hygiene.rollback_null_employment_status(app, company_code=company, idempotency_key=status_idem)
        check("status rollback", rb.get("status") == "rolled_back")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (emp_key,))
                back = dict(cur.fetchone())["employment_status"]
        check("status restored to null", back is None)

        # Migration map
        mp = hygiene.build_migration_readiness_map(
            [{"company_code": company, "employee_key": emp_key, "phone": phone}],
            synthetic_orphan_keys=[orphan_key],
        )
        check("map mints person for real employee", bool(mp["employees"][0]["person_id"]))
        check("map skips orphan person", mp["synthetic_orphans_excluded_from_person_mint"][0]["person_id"] is None)

    finally:
        cleanup()

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
