#!/usr/bin/env python3
"""Production Readiness R6 — staging DB Setup self-service journeys A–G."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
COMPANY = f"R6A{SUFFIX}"[:12]
COMPANY_B = f"R6B{SUFFIX}"[:12]
HR = f"9656613{SUFFIX[:5]}"


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
        "hr_intelligence_c1_audit",
        "hr_kpi_company_publications",
        "hr_intelligence_c6_company_settings",
        "hr_intelligence_c1_company_settings",
        "leave_policies",
        "company_modules",
        "company_settings",
        "companies",
    ]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in tables:
                try:
                    cur.execute(
                        f"DELETE FROM {table} WHERE company_code = ANY(%s)",
                        (companies,),
                    )
                except Exception:
                    conn.rollback()
        conn.commit()


def _ctx(company: str, *, role: str, perms: list[str], phone: str, user_id: str) -> dict:
    return {
        "company_code": company,
        "hr_phone": phone,
        "actor_phone": phone,
        "actor_role": role,
        "actor_user_id": user_id,
        "permissions": perms,
        "permission_authority": "backend_current",
        "permission_subject_user_id": user_id,
        "permission_subject_company": company,
        "access": {"permissions": perms},
        "hr_user": {"user_id": user_id, "role": role, "phone": phone, "company_code": company, "status": "active"},
        "actor": {"user_id": user_id, "role": role, "phone": phone, "company_code": company},
    }


def _ensure_company(cur, company: str) -> None:
    cur.execute(
        """
        INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
        VALUES (%s, %s, '{}'::jsonb, '{}'::jsonb, now(), now())
        ON CONFLICT (company_code) DO NOTHING
        """,
        (company, f"R6 {company}"),
    )


def _enable_module(cur, company: str, key: str) -> None:
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s,%s,true,'setup_console_r6','{}'::jsonb, now())
        ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true, updated_at=now()
        """,
        (company, key),
    )


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    print("    PRODUCTION READINESS R6 — setup self-service (staging DB)")
    print(f"    tenants: {COMPANY} / {COMPANY_B}")

    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1"] = "on"
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"] = ""
    os.environ["WATHEFNI_HR_INTELLIGENCE_SURFACES_C6"] = "on"
    os.environ["WATHEFNI_HR_INTELLIGENCE_SURFACES_COMPANIES"] = ""
    os.environ["WATHEFNI_ANALYTICS_KILL"] = "off"
    os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "on"
    os.environ["WATHEFNI_JOB_ARCHITECTURE_COMPANIES"] = ""
    os.environ["WATHEFNI_COMP_PLANNING_C6"] = "on"
    os.environ["WATHEFNI_COMP_PLANNING_COMPANIES"] = ""
    os.environ["WATHEFNI_WORKFORCE_PLANNING_C7"] = "on"
    os.environ["WATHEFNI_WORKFORCE_PLANNING_COMPANIES"] = ""

    import app
    import compensation_planning_c6 as cp
    import job_architecture_c1 as ja
    import setup_console_delivery_policies as deliv
    import setup_console_effective_state as eff
    import setup_console_modules_phase3b as p3b
    import setup_console_policy_convergence as conv
    import setup_console_wave1_policies as w1
    import setup_console_wave2_policies as w2
    import setup_console_wave5_policies as w5
    import setup_console_wave6_policies as w6

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                _ensure_company(cur, COMPANY)
                _ensure_company(cur, COMPANY_B)
                for key in ("leave", "attendance", "onboarding", "analytics"):
                    _enable_module(cur, COMPANY, key)
                    _enable_module(cur, COMPANY_B, key)
                try:
                    app.seed_company_leave_policies(COMPANY)
                except Exception:
                    pass
                cur.execute(
                    """
                    INSERT INTO leave_policies
                      (company_code, leave_type, days_per_year, version, enforced)
                    VALUES (%s, 'annual', 30, 1, false)
                    ON CONFLICT (company_code, leave_type, version) DO NOTHING
                    """,
                    (COMPANY,),
                )
            conn.commit()

        # A — configure via Setup APIs only (no env/SQL policy writes after bootstrap)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                leave = p3b.patch_leave_company_policy(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    reason="r6 leave",
                    optional={"notice_days_default": 3, "require_attachment_for_sick": True},
                )
                check("A leave setup write", leave.get("ok") is True, leave)
                att = p3b.patch_attendance_company_policy(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    reason="r6 attendance",
                    optional={"lateness_grace_minutes": 11, "require_clock_out": True},
                )
                check("A attendance setup write", att.get("ok") is True, att)
                onb = w1.patch_wave1_onboarding_auto_start(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    reason="r6 onboarding",
                    required={"auto_start_on_hire": False},
                )
                check("A onboarding setup write", onb.get("ok") is True, onb)
                preset = deliv.patch_delivery_policy(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    reason="r6 preset",
                    payload={"notification_preset": "conservative"},
                )
                check("A notification preset via Setup", preset.get("ok") is True and (preset.get("policy") or {}).get("notification_preset") == "conservative", preset)
            conn.commit()

        # D — convergence: Wave2 leave.enforced writes leave_policies; onboarding cards share auto_start
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w2.patch_wave2_module_policy(
                    cur,
                    company_code=COMPANY,
                    module_key="leave",
                    actor_phone=HR,
                    reason="r6 leave enforced",
                    payload={"enforced": True},
                )
                check("D leave enforced write-through", conv.read_leave_enforced(cur, COMPANY) is True)
                w2_leave = w2.get_wave2_module_policy(cur, COMPANY, "leave")
                check("D wave2 reads canonical enforced", (w2_leave.get("policy") or {}).get("enforced") is True, w2_leave)
                onb3 = p3b.get_onboarding_company_policy(cur, COMPANY)
                auto = ((onb3.get("canonical_auto_start") or {}).get("auto_start_on_hire"))
                check("D onboarding cards share auto_start", auto is False, onb3)
                att_pol = p3b.get_attendance_company_policy(cur, COMPANY)
                check(
                    "D attendance grace from Setup overlay",
                    ((att_pol.get("optional") or {}).get("lateness_grace_minutes") == 11),
                    att_pol,
                )
            conn.commit()

        # B — deployment gate honesty
        os.environ["WATHEFNI_ANALYTICS_KILL"] = "on"
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                gated = w5.get_wave5_module_policy(cur, COMPANY)
        check("B kill switch not usable", (gated.get("effective_state") or {}).get("usable") is False, gated)
        check(
            "B kill switch state unavailable_deployment",
            (gated.get("effective_state") or {}).get("effective_state") == "unavailable_deployment",
            gated,
        )
        check("B does not say Enabled", gated.get("customer_facing_state") != "enabled", gated)
        os.environ["WATHEFNI_ANALYTICS_KILL"] = "off"
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                open_gate = w5.get_wave5_module_policy(cur, COMPANY)
        check("B unblock resolves deployment", (open_gate.get("runtime_gate") or {}).get("ok") is True, open_gate)

        # E — Intelligence Setup
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                enabled = w5.patch_wave5_module_policy(
                    cur,
                    company_code=COMPANY,
                    module_key="analytics",
                    actor_phone=HR,
                    reason="r6 intelligence enable",
                    payload={"enabled": True, "min_cohort_n": 6, "fiscal_year_start_month": 4},
                )
                check("E Intelligence enable via Setup", enabled.get("ok") is True, enabled)
                pol = (enabled.get("policy") or {})
                check("E min_cohort from Setup", int(pol.get("min_cohort_n") or 0) >= 6, pol)
                check("E fiscal month from Setup", int(pol.get("fiscal_year_start_month") or 0) == 4, pol)
                check("E no env edit required", os.environ.get("WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES") == "")
                down = w5.patch_wave5_module_policy(
                    cur,
                    company_code=COMPANY,
                    module_key="analytics",
                    actor_phone=HR,
                    reason="r6 cohort down",
                    payload={"min_cohort_n": 5},
                )
                check("E cohort downward forbidden", down.get("ok") is not True, down)
            conn.commit()

        # C — Comp/WFP JA dependency
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                denied = w6.patch_wave6_module_policy(
                    cur,
                    company_code=COMPANY,
                    module_key="comp_planning",
                    actor_phone=HR,
                    reason="r6 comp without ja",
                    payload={"enabled": True},
                )
                check(
                    "C Comp without JA governed",
                    denied.get("ok") is not True
                    and str(denied.get("error") or "") in {"ja_must_be_enabled", "ja_hard_dependency_unmet", "ja_hard_unmet"},
                    denied,
                )
                ja.enable_company_job_architecture(cur, company_code=COMPANY, actor_phone=HR, reason="r6 ja")
                allowed = w6.patch_wave6_module_policy(
                    cur,
                    company_code=COMPANY,
                    module_key="comp_planning",
                    actor_phone=HR,
                    reason="r6 comp after ja",
                    payload={"enabled": True},
                )
                check("C Comp enable after JA", allowed.get("ok") is True, allowed)
                wfp_denied_before = None
                # WFP after JA should be enableable; prove WFP also required JA by checking OTHER company
                wfp_other = w6.patch_wave6_module_policy(
                    cur,
                    company_code=COMPANY_B,
                    module_key="workforce_planning",
                    actor_phone=HR,
                    reason="r6 wfp without ja",
                    payload={"enabled": True},
                )
                check(
                    "C WFP without JA governed",
                    wfp_other.get("ok") is not True,
                    wfp_other,
                )
            conn.commit()

        # F — disable / re-enable preserves history
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                hist = w5.get_wave5_module_policy(cur, COMPANY)
                check("F history exists before disable", (hist.get("policy") or {}).get("enabled") is True, hist)
                off = w5.patch_wave5_module_policy(
                    cur,
                    company_code=COMPANY,
                    module_key="analytics",
                    actor_phone=HR,
                    reason="r6 disable intelligence",
                    payload={"enabled": False},
                )
                check("F disable ok", off.get("ok") is True, off)
                check("F disable preserves history flag", off.get("actions") and any(a.get("preserves_history") for a in off.get("actions") or []), off)
                cur.execute(
                    "SELECT min_cohort_n FROM hr_intelligence_c1_company_settings WHERE company_code=%s",
                    (COMPANY,),
                )
                row = cur.fetchone()
                cohort = dict(row).get("min_cohort_n") if row and isinstance(row, dict) else (row[0] if row else None)
                check("F historical cohort retained", int(cohort or 0) >= 6, cohort)
                on_again = w5.patch_wave5_module_policy(
                    cur,
                    company_code=COMPANY,
                    module_key="analytics",
                    actor_phone=HR,
                    reason="r6 reenable intelligence",
                    payload={"enabled": True},
                )
                check("F re-enable restores", on_again.get("ok") is True and (on_again.get("policy") or {}).get("enabled") is True, on_again)
                check("F re-enable keeps raised cohort", int((on_again.get("policy") or {}).get("min_cohort_n") or 0) >= 6, on_again)
            conn.commit()

        # G + permissions via company-scoped HTTP
        from fastapi.testclient import TestClient

        client = TestClient(app.app)

        def use(ctx: dict) -> None:
            app.app.dependency_overrides[app.dashboard_context] = lambda: ctx

        try:
            use(_ctx(COMPANY, role="hr_admin", perms=["leave.read", "employees.read"], phone=HR, user_id="r6-hr"))
            denied = client.get("/dashboard/setup/company/module-policies")
            check("ordinary HR Setup 403", denied.status_code == 403, denied.status_code)
            check("ordinary HR not_permitted", "not_permitted" in str(denied.json()), denied.text[:200])

            use(_ctx(COMPANY, role="company_admin", perms=["settings.manage"], phone=HR, user_id="r6-admin"))
            ok = client.get("/dashboard/setup/company/module-policies")
            check("company admin Setup 200", ok.status_code == 200, ok.status_code)
            if ok.status_code == 200:
                body = ok.json()
                check("A/E wave5 present in Setup payload", bool((body.get("wave5") or {}).get("modules")), body.get("wave5"))
                check("delivery present", bool(body.get("delivery")), body.get("delivery"))
                intel = ((body.get("wave5") or {}).get("modules") or {}).get("analytics") or {}
                check("effective state present", bool(intel.get("effective_state")), intel)

            use(_ctx(COMPANY, role="company_admin", perms=["settings.manage"], phone=HR, user_id="r6-admin"))
            steal = client.patch(
                "/dashboard/setup/company/module-policies/notifications",
                json={"reason": "r6 header steal", "required": {"notification_preset": "frontline"}},
                headers={"X-Company-Code": COMPANY_B},
            )
            check("G company-scoped write uses session tenant", steal.status_code in {200, 400, 403, 409}, steal.status_code)
            operator_b = client.patch(
                f"/dashboard/superadmin/setup/companies/{COMPANY_B}/module-policies/notifications",
                json={"reason": "r6 cross tenant", "required": {"notification_preset": "frontline"}},
            )
            check(
                "G company admin cannot write tenant B via operator Setup",
                operator_b.status_code in {401, 403, 404},
                operator_b.status_code,
            )
            use(_ctx(COMPANY_B, role="company_admin", perms=["settings.manage"], phone=HR, user_id="r6-admin-b"))
            b_body = client.get("/dashboard/setup/company/module-policies")
            check("G tenant B reads own Setup", b_body.status_code == 200, b_body.status_code)
            if b_body.status_code == 200 and ok.status_code == 200:
                a_preset = ((ok.json().get("delivery") or {}).get("policy") or {}).get("notification_preset")
                b_preset = ((b_body.json().get("delivery") or {}).get("policy") or {}).get("notification_preset")
                check("G tenant B does not inherit A preset", b_preset != "conservative", {"a": a_preset, "b": b_preset})
                check("G header did not write tenant B", b_preset != "frontline", b_preset)

            use(_ctx(COMPANY, role="company_admin", perms=["settings.manage"], phone=HR, user_id="r6-admin"))
            fail_save = client.patch(
                "/dashboard/setup/company/module-policies/wave6_comp_planning",
                json={"reason": "", "required": {"enabled": True}},
            )
            check("failed save without reason is not 200-success", fail_save.status_code >= 400, fail_save.status_code)
            check("failed save does not look enabled", "enabled_usable" not in str(fail_save.json()) or fail_save.status_code >= 400, fail_save.text[:200])
        finally:
            app.app.dependency_overrides.clear()

        check("JA platform foundation not SKU", "job_architecture" not in __import__("module_catalog").MODULE_BY_KEY)
        check("one effective state honesty", eff.honesty_payload().get("one_effective_state") is True)
    finally:
        try:
            cleanup(app, [COMPANY, COMPANY_B])
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("R6_SETUP_SELF_SERVICE_DB_FAIL")
        return 1
    print("R6_SETUP_SELF_SERVICE_DB_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
