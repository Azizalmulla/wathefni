"""Smoke test: Setup Console (B) — client-facing Owner readiness checklist.

The readiness endpoint is company-scoped, read-only guidance ("what should I do
next to get my workspace ready, and why?"). This pins its behaviour:

  - module-aware: post-hire/compliance steps only appear when those modules are
    enabled; a pre-hiring-only company never sees an employee/compliance step
  - data-driven: each step flips to done once the company has the real data
    (a job, an employee, a tracked document)
  - tenant-scoped: another company's jobs/employees never count toward this one
  - readiness: ready becomes true only once every REQUIRED step is done (the two
    recommendations — team + WhatsApp — are optional and never block)

Run (staging has psycopg2): WATHEFNI_DELIVERY_MODE=dry_run python3 smoke-test-setup-readiness.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PASS = 0
FAIL = 0
TEST_CO = "SETUPREADYTEST"
OTHER_CO = "SETUPREADYOTHER"


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def steps_by_key(payload: dict) -> dict:
    return {s["key"]: s for s in payload.get("steps", [])}


def main() -> int:
    print("    setup readiness (B) — module-aware, data-driven, tenant-scoped, owner checklist")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise
    from psycopg2.extras import Json

    def cleanup() -> None:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for company in (TEST_CO, OTHER_CO):
                    cur.execute("DELETE FROM compliance_documents WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM employees WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM positions WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM company_modules WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM companies WHERE company_code=%s", (company,))
            conn.commit()

    def create_company(cur, company) -> None:
        cur.execute(
            "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
            "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
            (company, company.title(), Json({}), Json({})),
        )

    def enable_modules(cur, company, module_keys) -> None:
        for key in module_keys:
            cur.execute(
                "INSERT INTO company_modules (company_code, module_key, enabled, source, updated_at) "
                "VALUES (%s,%s,true,'smoke',now()) ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true",
                (company, key),
            )

    def add_position(cur, company, code) -> None:
        cur.execute(
            "INSERT INTO positions (company_code, position_code, title, status, updated_at) "
            "VALUES (%s,%s,%s,'open',now()) ON CONFLICT (company_code, position_code) DO UPDATE SET status='open'",
            (company, code, f"{code} role"),
        )

    def add_employee(cur, company, key) -> None:
        cur.execute(
            "INSERT INTO employees (employee_key, phone, company_code, name, onboarding_status, documents_pending, documents_complete, raw_json) "
            "VALUES (%s,%s,%s,%s,'in_progress',0,0,%s) ON CONFLICT (employee_key) DO NOTHING",
            (key, f"965{abs(hash(key)) % 9000000 + 1000000}", company, "Readiness Smoke Employee", Json({"smoke": True})),
        )

    def add_doc(cur, company, emp_key) -> None:
        cur.execute(
            "INSERT INTO compliance_documents (employee_key, document_type, label, status, raw_json, company_code) "
            "VALUES (%s,%s,%s,'received','{}'::jsonb,%s)",
            (emp_key, "civil_id", "Civil ID", company),
        )

    try:
        cleanup()
        # TEST_CO has pre-hiring + compliance; OTHER_CO is pre-hiring only.
        # Seed OTHER_CO with a job AND an employee so it acts as cross-tenant noise.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                create_company(cur, TEST_CO)
                create_company(cur, OTHER_CO)
                enable_modules(cur, TEST_CO, ["pre_hiring", "compliance"])
                enable_modules(cur, OTHER_CO, ["pre_hiring"])
                add_position(cur, OTHER_CO, "OTHERJOB")
                add_employee(cur, OTHER_CO, "setupready-other-emp")
            conn.commit()

        ctx = {"company_code": TEST_CO}
        r0 = app.dashboard_setup_readiness(ctx)
        s0 = steps_by_key(r0)
        check("compliance company shows first_job step", "first_job" in s0)
        check("compliance company shows first_employee step", "first_employee" in s0)
        check("compliance company shows compliance_docs step", "compliance_docs" in s0)
        check("team + whatsapp recommendations are optional", s0.get("team", {}).get("optional") and s0.get("whatsapp", {}).get("optional"))
        check("nothing seeded yet -> first_job not done", s0["first_job"]["done"] is False)
        check("cross-tenant employee does NOT count (first_employee not done)", s0["first_employee"]["done"] is False)
        check("no docs yet -> compliance_docs not done", s0["compliance_docs"]["done"] is False)
        check("workspace not ready yet", r0["ready"] is False)
        check("each step explains why + offers an action", all(st["why"] and st["action_label"] and st["action_page"] for st in r0["steps"]))

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                add_position(cur, TEST_CO, "TESTJOB")
            conn.commit()
        check("after posting a job -> first_job done", app.dashboard_setup_readiness(ctx)["steps"] and steps_by_key(app.dashboard_setup_readiness(ctx))["first_job"]["done"] is True)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                add_employee(cur, TEST_CO, "setupready-test-emp")
            conn.commit()
        check("after adding an employee -> first_employee done", steps_by_key(app.dashboard_setup_readiness(ctx))["first_employee"]["done"] is True)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                add_doc(cur, TEST_CO, "setupready-test-emp")
            conn.commit()
        rf = app.dashboard_setup_readiness(ctx)
        check("after tracking a document -> compliance_docs done", steps_by_key(rf)["compliance_docs"]["done"] is True)
        check("all required steps done -> workspace ready", rf["ready"] is True)

        # Module-awareness: pre-hiring-only company never sees post-hire steps.
        ro = app.dashboard_setup_readiness({"company_code": OTHER_CO})
        so = steps_by_key(ro)
        check("pre-hiring-only company has NO first_employee step", "first_employee" not in so)
        check("pre-hiring-only company has NO compliance_docs step", "compliance_docs" not in so)
        check("pre-hiring-only company first_job done (its own job)", so["first_job"]["done"] is True)
    finally:
        try:
            cleanup()
        except Exception:
            print("    (warning: cleanup failed)")

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    SETUP READINESS: FAILURES")
        return 1
    print("    SETUP READINESS: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
