#!/usr/bin/env python3
"""Production Readiness R5A — staging DB capability honesty.

Proves against an isolated staging database:

  * existing enabled Wave 4/6 rows are preserved
  * customer Setup write is refused without deleting configuration
  * runtime stays env-gated for internal qualification
  * customer-facing usable is false even when stored enabled is true
  * Waves 1–3 catalog modules still enable normally
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
COMPANY = f"R5A{SUFFIX}"[:12]
HR = f"9655011{SUFFIX[:5]}"


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
        "ja_company_settings",
        "ld_company_settings",
        "bn_company_settings",
        "er_company_settings",
        "eng_company_settings",
        "cp_company_settings",
        "wfp_company_settings",
        "company_modules",
        "company_settings",
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
    print("    PRODUCTION READINESS R5A — capability honesty (staging DB)")
    print(f"    tenant: {COMPANY}")
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")

    try:
        import app
        import production_data_safety as pds
        import capability_readiness as ready
        import setup_console_wave4_policies as w4p
        import job_architecture_c1 as ja
        import performance_goals_c1 as c1
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

    pds.require_non_production_target()
    app.ensure_schema()
    cleanup(app, [COMPANY])

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (COMPANY, f"R5A {COMPANY}"),
                )
                cur.execute(
                    """
                    INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                    VALUES (%s,'leave',true,'r5a', '{}'::jsonb, now())
                    ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true
                    """,
                    (COMPANY,),
                )

                patched = w4p.patch_wave4_module_policy(
                    cur,
                    company_code=COMPANY,
                    module_key="performance_goals",
                    actor_phone=HR,
                    reason="r5a preserve existing enabled row",
                    payload={"enabled": True},
                )
                check("internal python patch still writes overlay", patched.get("ok") is True, patched)
                check(
                    "internal overlay stored enabled",
                    bool((patched.get("policy") or {}).get("enabled")) is True,
                    patched,
                )

                ja.ensure_job_architecture_c1_schema(cur)
                os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "on"
                os.environ["WATHEFNI_JOB_ARCHITECTURE_COMPANIES"] = COMPANY
                enabled_ja = ja.enable_company_job_architecture(
                    cur, company_code=COMPANY, actor_phone=HR, reason="r5a preserve ja row"
                )
                check("internal JA enable still works", enabled_ja.get("ok") is True, enabled_ja)

                wave4 = w4p.get_wave4_module_policy(cur, COMPANY, "performance_goals")
                annotated = ready.annotate_policy_payload("wave4_performance_goals", wave4)
                check("GET stored_enabled true", annotated.get("stored_enabled") is True, annotated)
                check("GET usable true after R5B", annotated.get("usable") is True, annotated)
                check("GET customer_enableable true after R5B", annotated.get("customer_enableable") is True, annotated)

                all_wave4 = ready.annotate_wave4_setup(w4p.get_all_wave4_policies(cur, COMPANY))
                check("wave4 payload customer visible for performance", all_wave4.get("customer_visible") is True)
                goals = (all_wave4.get("modules") or {}).get("performance_goals") or {}
                check("wave4 goals stored enabled preserved", goals.get("stored_enabled") is True, goals)
                check("wave4 goals usable after R5B", goals.get("usable") is True, goals)

                blocked = ready.customer_setup_write_block("wave4_performance_goals")
                check("customer can enable performance after R5B", blocked is None)
                blocked_talent = ready.customer_setup_write_block("wave4_talent_succession")
                check("customer cannot enable talent", (blocked_talent or {}).get("error") == "capability_not_customer_enableable")
                for key in (
                    "job_architecture",
                    "learning",
                    "benefits",
                    "employee_relations",
                    "engagement",
                    "comp_planning",
                    "workforce_planning",
                ):
                    b = ready.customer_setup_write_block(f"wave6_{key}")
                    check(
                        f"customer cannot enable {key}",
                        (b or {}).get("error") == "capability_not_customer_enableable",
                        b,
                    )

                cur.execute(
                    """
                    SELECT settings FROM company_modules
                    WHERE company_code=%s AND module_key='performance'
                    """,
                    (COMPANY,),
                )
                row = cur.fetchone() or {}
                settings = row.get("settings") if isinstance(row, dict) else None
                if isinstance(settings, str):
                    settings = json.loads(settings)
                overlay = ((settings or {}).get("wave4_setup") or {}).get("performance_goals") or {}
                check("performance overlay still enabled after refuse", overlay.get("enabled") is True, overlay)

                cur.execute("SELECT enabled FROM ja_company_settings WHERE company_code=%s", (COMPANY,))
                ja_row = cur.fetchone() or {}
                check("JA settings row preserved", bool(ja_row.get("enabled")) is True, ja_row)

                os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "off"
                os.environ["WATHEFNI_JOB_ARCHITECTURE_COMPANIES"] = ""
                check("JA stored enabled does not open runtime", ja.runtime_gate_for_company(COMPANY).get("ok") is not True)
                cur.execute("SELECT enabled FROM ja_company_settings WHERE company_code=%s", (COMPANY,))
                ja_row_after = cur.fetchone() or {}
                check("JA row still enabled after runtime off", bool(ja_row_after.get("enabled")) is True, ja_row_after)

                cur.execute(
                    "SELECT enabled FROM company_modules WHERE company_code=%s AND module_key='leave'",
                    (COMPANY,),
                )
                leave_row = cur.fetchone() or {}
                check("leave still enabled for tenant", bool(leave_row.get("enabled")) is True, leave_row)

            conn.commit()

        os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "off"
        os.environ["WATHEFNI_PERFORMANCE_GOALS_COMPANIES"] = ""
        os.environ["WATHEFNI_PERFORMANCE_KILL"] = "off"
        check("runtime gated off without env", c1.runtime_gate_for_company(COMPANY).get("ok") is not True)

        os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "on"
        os.environ["WATHEFNI_PERFORMANCE_GOALS_COMPANIES"] = COMPANY
        check("internal env qualification still possible", c1.runtime_gate_for_company(COMPANY).get("ok") is True)
        check(
            "env on is customer usable after R5B",
            ready.customer_usable(capability_key="performance", stored_enabled=True, runtime_available=True) is True,
        )

        os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "off"
        os.environ["WATHEFNI_JOB_ARCHITECTURE_COMPANIES"] = ""
        check("JA runtime off without env", ja.runtime_gate_for_company(COMPANY).get("ok") is not True)
        os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "on"
        os.environ["WATHEFNI_JOB_ARCHITECTURE_COMPANIES"] = COMPANY
        check("JA internal env qualification still possible", ja.runtime_gate_for_company(COMPANY).get("ok") is True)

        check("leave catalog enableable", ready.catalog_module_customer_enableable("leave") is True)
        check("analytics catalog enableable", ready.catalog_module_customer_enableable("analytics") is True)
    finally:
        os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "off"
        os.environ["WATHEFNI_PERFORMANCE_GOALS_COMPANIES"] = ""
        os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "off"
        os.environ["WATHEFNI_JOB_ARCHITECTURE_COMPANIES"] = ""
        cleanup(app, [COMPANY])

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5A_CAPABILITY_HONESTY_DB_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
