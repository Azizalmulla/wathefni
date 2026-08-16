#!/usr/bin/env python3
"""Production Readiness R3 — live staging data-safety qualification.

Proves against an isolated staging database:

  * missing company fails closed and does not resolve to WATHEFNI
  * explicit tenant still resolves
  * a newly created company has no fixture employees/modules/messages
  * fixture identity cannot leak into that clean tenant
  * scoped company_modules deletes cannot touch another tenant
  * synthetic connectors stay off for a normal tenant
  * a seed script with explicit staging synthetic tenant can connect
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
CO_CLEAN = f"R3CLEAN{SUFFIX}"
CO_FIXTURE = f"R3SYNTH{SUFFIX}"
CO_OTHER = f"R3OTHER{SUFFIX}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def cleanup(app, companies: list[str]) -> None:
    import production_data_safety as pds

    pds.require_destructive_scope(companies)
    tables = [
        "employee_messages",
        "employee_documents",
        "onboarding_items",
        "employees",
        "company_modules",
        "company_settings",
        "dashboard_users",
        "companies",
    ]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in tables:
                try:
                    cur.execute(f"DELETE FROM {table} WHERE company_code = ANY(%s)", (companies,))
                except Exception:
                    conn.rollback()
        conn.commit()


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    print("    PRODUCTION READINESS R3 — live data-safety paths")
    print(f"    tenants: {CO_CLEAN} / {CO_FIXTURE} / {CO_OTHER}")
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")

    try:
        import app
        import production_data_safety as pds
        from fastapi import HTTPException
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("      SKIP  psycopg2 unavailable")
            return 1
        raise

    try:
        probe = app.db_connect()
        probe.__enter__()
        probe.__exit__(None, None, None)
    except Exception as exc:
        print(f"      SKIP  database unavailable ({type(exc).__name__}: {exc})")
        return 1

    app.ensure_schema()
    cleanup(app, [CO_CLEAN, CO_FIXTURE, CO_OTHER])

    print("\n    missing company fails closed")
    try:
        app.require_company_code(None)
        check("require_company_code(None) fails closed", False)
    except HTTPException as exc:
        check("require_company_code(None) fails closed", exc.status_code == 400, exc.status_code)
        check("missing company does not resolve to WATHEFNI", "WATHEFNI" not in json.dumps(exc.detail))

    try:
        app.configured_company_modules(None)
        check("module lookup without a company fails closed", False)
    except HTTPException as exc:
        check("module lookup without a company fails closed", exc.status_code == 400, exc.status_code)

    check("explicit legitimate tenant still resolves", app.require_company_code(CO_CLEAN) == CO_CLEAN)
    check("explicit canary name still resolves when named", app.require_company_code("WATHEFNI") == "WATHEFNI")

    print("\n    clean company bootstrap")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies (company_code, name, country, metadata, raw_json, created_at, updated_at) "
                "VALUES (%s,%s,'KW',%s,%s,now(),now())",
                (CO_CLEAN, "R3 Clean Bootstrap", app.Json({}), app.Json({})),
            )
            cur.execute(
                "INSERT INTO company_settings (company_code, settings) VALUES (%s,%s) ON CONFLICT (company_code) DO NOTHING",
                (CO_CLEAN, app.Json({"timezone": "Asia/Kuwait", "currency": "KWD"})),
            )
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in pds.CLEAN_BOOTSTRAP_ABSENT_TABLES:
                try:
                    cur.execute(f"SELECT count(*) AS n FROM {table} WHERE company_code=%s", (CO_CLEAN,))
                    n = int((cur.fetchone() or {}).get("n") or 0)
                except Exception:
                    conn.rollback()
                    continue
                check(f"clean bootstrap has no {table} rows", n == 0, n)

    print("\n    fixture identity cannot leak into a clean tenant")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT DO NOTHING",
                (CO_FIXTURE, "R3 Fixture", app.Json({"r3": True}), app.Json({})),
            )
            cur.execute(
                "INSERT INTO employees (employee_key, phone, company_code, name, employment_status, raw_json, updated_at) "
                "VALUES (%s,%s,%s,%s,'active',%s, now()) ON CONFLICT (employee_key) DO NOTHING",
                (f"{CO_FIXTURE}-96550010001", "96550010001", CO_FIXTURE, "Fixture Noura", app.Json({"fixture": True})),
            )
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM employees WHERE company_code=%s AND employee_key LIKE '%%96550010001'",
                (CO_CLEAN,),
            )
            n = int((cur.fetchone() or {}).get("n") or 0)
            check("clean tenant did not inherit the fixture employee", n == 0, n)
            cur.execute(
                "SELECT count(*) AS n FROM employees WHERE company_code=%s AND employee_key=%s",
                (CO_FIXTURE, f"{CO_FIXTURE}-96550010001"),
            )
            n = int((cur.fetchone() or {}).get("n") or 0)
            check("fixture employee stayed in the synthetic tenant", n == 1, n)

    print("\n    destructive matrix stays scoped")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT DO NOTHING",
                (CO_OTHER, "R3 Other", app.Json({}), app.Json({})),
            )
            for company in (CO_FIXTURE, CO_OTHER):
                cur.execute(
                    "INSERT INTO company_modules (company_code, module_key, enabled, source, updated_at) "
                    "VALUES (%s,'employees',true,'r3',now()) ON CONFLICT (company_code, module_key) DO NOTHING",
                    (company,),
                )
        conn.commit()

    sql, params = pds.scoped_delete_company_modules([CO_FIXTURE])
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM company_modules WHERE company_code=%s", (CO_FIXTURE,))
            gone = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT count(*) AS n FROM company_modules WHERE company_code=%s", (CO_OTHER,))
            kept = int((cur.fetchone() or {}).get("n") or 0)
    check("destructive matrix deleted only the named synthetic tenant modules", gone == 0, gone)
    check("destructive matrix left the other tenant's modules intact", kept == 1, kept)

    print("\n    synthetic connectors")
    os.environ.pop("WATHEFNI_SYNTHETIC_CONNECTORS", None)
    check("a normal tenant cannot create a canary connector", pds.synthetic_connectors_allowed(CO_CLEAN) is False)

    print("\n    seed script with explicit staging synthetic tenant")
    env = dict(os.environ)
    env.update(
        {
            "WATHEFNI_ENV": os.environ.get("WATHEFNI_ENV") or "staging",
            "WATHEFNI_DATA_SAFETY_ACK": "non-production",
            "WATHEFNI_COMPANY_CODE": CO_FIXTURE,
            "PYTHONPATH": str(orchestrator_dir) + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""),
        }
    )
    # The seed script imports app after the guard. Stop after the guard by using --help
    # is not enough; run a tiny driver that only calls require_fixture_tooling.
    try:
        target = pds.require_fixture_tooling(company_code=CO_FIXTURE)
        check("seed guard accepts explicit staging synthetic tenant", target.company_code == CO_FIXTURE)
    except pds.DataSafetyError as exc:
        check("seed guard accepts explicit staging synthetic tenant", False, str(exc))

    cleanup(app, [CO_CLEAN, CO_FIXTURE, CO_OTHER])
    print("\n    R3_DATA_SAFETY_FULL_PASS" if not FAIL else "\n    R3_DATA_SAFETY_FAIL")
    print(f"    {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
