"""Smoke test: HR onboarding dashboard upgrade (detail + start/restart + mark item).

The onboarding HR mutations (start_onboarding, onboarding_mark_item) are
dark-launched behind WATHEFNI_ONBOARDING_HR_MUTATE and must ride the SAME
registry + dashboard harness as every other post-hire action, so they inherit
company scoping, RBAC, confirmation, and audit. This test pins:

  - both actions are registered under the onboarding module with onboarding.manage,
    require confirmation (sensitive money/lifecycle change), have a preflight, and
    are reachable through the dashboard harness + orchestrator gating
  - RBAC: owner/hr_manager manage; viewer is read-only (denied manage)
  - the arg whitelist keeps employee_key/item_id/item_status and drops scope/actor spoofing
  - the dark-launch flag defaults OFF, flips ON via env, and the executors hard-fail
    (feature_disabled) while the flag is OFF — no DB mutation can sneak through
  - behaviour (staging DB): mark received flips an outstanding item + recomputes the
    employee rollup; waive drops a required item out of the outstanding count;
    the detail summary + list counts reflect both; unknown item/employee fail safe;
    find_employee_by_key is tenant-scoped (no cross-company resolution)

Run (staging has psycopg2): python3 smoke-test-onboarding-dashboard.py
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
ITEM_RECV = f"zz_recv_{SUFFIX}"
ITEM_WAIVE = f"zz_waive_{SUFFIX}"


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    onboarding dashboard upgrade — registry + RBAC + flag gate + behaviour")
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise
    import action_registry as registry
    import tool_call_orchestrator as tco

    ACTIONS = ("start_onboarding", "onboarding_mark_item")

    # --- 1) registry specs ---------------------------------------------------
    for name in ACTIONS:
        spec = registry.spec_for(name)
        check(f"{name} is registered", spec is not None)
        if spec:
            check(f"{name} module is onboarding", getattr(spec, "module", None) == "onboarding")
            check(f"{name} has an executor", bool(getattr(spec, "executor", None)))
            check(f"{name} requires confirmation", getattr(spec, "requires_confirmation", False) is True)
            check(f"{name} has a confirm preflight", getattr(spec, "preflight", None) is not None)
            check(f"{name} is marked sensitive", getattr(spec, "sensitive", False) is True)

    # --- 2) reachable through the dashboard harness + orchestrator gating ----
    check("onboarding is a dashboard post-hire module", "onboarding" in app.POSTHIRE_DASHBOARD_MODULES)
    check("onboarding is a gated tool-call module", "onboarding" in tco.TOOLCALL_GATED_MODULES)
    for name in ACTIONS:
        check(f"{name} maps to onboarding.manage", tco.TOOL_PERMISSION_MAP.get(name) == "onboarding.manage")
        check(f"harness resolves the onboarding module for {name}", app.posthire_action_module(name) == "onboarding")

    # --- 3) RBAC -------------------------------------------------------------
    check("owner has onboarding.manage", "onboarding.manage" in app.hr_role_permissions("owner"))
    check("hr_manager has onboarding.manage", "onboarding.manage" in app.hr_role_permissions("hr_manager"))
    check("viewer has no onboarding.manage", "onboarding.manage" not in app.hr_role_permissions("viewer"))

    # --- 4) arg whitelist blocks scope/actor spoofing ------------------------
    dirty = {"employee_key": "emp-1", "item_id": "civil_id", "item_status": "received", "company_code": "EVILCO", "actor_role": "owner", "stray": 1}
    safe = app.posthire_whitelisted_args("onboarding_mark_item", dirty)
    check("whitelist keeps employee_key/item_id/item_status", safe == {"employee_key": "emp-1", "item_id": "civil_id", "item_status": "received"})
    for forbidden in ("company_code", "actor_role", "stray"):
        check(f"whitelist drops {forbidden}", forbidden not in safe)

    # --- 5) dark-launch flag defaults OFF and flips ON -----------------------
    orig_flag = os.environ.get("WATHEFNI_ONBOARDING_HR_MUTATE")
    os.environ.pop("WATHEFNI_ONBOARDING_HR_MUTATE", None)
    check("flag defaults OFF when unset", app.onboarding_hr_mutate_enabled() is False)
    os.environ["WATHEFNI_ONBOARDING_HR_MUTATE"] = "off"
    check("flag stays OFF for 'off'", app.onboarding_hr_mutate_enabled() is False)
    os.environ["WATHEFNI_ONBOARDING_HR_MUTATE"] = "on"
    check("flag flips ON for 'on'", app.onboarding_hr_mutate_enabled() is True)

    # executor hard-fails while the flag is OFF (no DB touched)
    class _Req:
        sender_phone = "96599338566"
        account_id = "WATHEFNI"

    def _ctx(action):
        return registry.ExecutionContext(request=_Req(), action=dict(action), state={}, graph_state={}, intent={}, legacy=app)

    os.environ["WATHEFNI_ONBOARDING_HR_MUTATE"] = "off"
    gated = registry._onboarding_mark_item_executor(_ctx({"employee_key": "nope", "item_id": ITEM_RECV, "item_status": "received"}))
    check("mark executor blocked while flag OFF", isinstance(gated, dict) and gated.get("error") == "feature_disabled" and gated.get("success") is False)
    original_resolve = app.resolve_employee_for_direct_action
    try:
        app.resolve_employee_for_direct_action = lambda *a, **k: {
            "employee_key": "WATHEFNI-ONBOARDING-GATE-SMOKE",
            "company_code": "WATHEFNI",
            "name": "Onboarding Gate Smoke",
        }
        gated_start = registry._onboarding_start_executor(_ctx({"employee_key": "WATHEFNI-ONBOARDING-GATE-SMOKE"}))
    finally:
        app.resolve_employee_for_direct_action = original_resolve
    check("start executor blocked while flag OFF", isinstance(gated_start, dict) and gated_start.get("error") == "feature_disabled")
    os.environ["WATHEFNI_ONBOARDING_HR_MUTATE"] = "on"

    # --- 6) behaviour against the DB ----------------------------------------
    real_emp: dict | None = None
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT employee_key, name, phone, company_code FROM employees WHERE employee_key <> '' LIMIT 1")
            row = cur.fetchone()
            if row:
                real_emp = dict(row)
    if not real_emp:
        print("    (no employees on this DB — skipping behaviour checks)")
    else:
        emp_key = str(real_emp["employee_key"])
        company = real_emp.get("company_code")
        Json = app.Json
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO onboarding_items (employee_key, item_id, label, item_type, required, document_type, status, raw_json)
                    VALUES (%s,%s,'ZZ Received Doc','document',true,%s,'pending',%s),
                           (%s,%s,'ZZ Waive Doc','document',true,%s,'pending',%s)
                    """,
                    (emp_key, ITEM_RECV, ITEM_RECV, Json({"smoke": True}),
                     emp_key, ITEM_WAIVE, ITEM_WAIVE, Json({"smoke": True})),
                )
                app.recompute_employee_onboarding_counts(cur, emp_key)
            conn.commit()
        try:
            # tenant scoping: a bogus company must not resolve the key
            cross = app.find_employee_by_key(emp_key, company_code="DEFINITELY_NOT_A_COMPANY")
            check("find_employee_by_key is tenant-scoped", cross is None)
            check("find_employee_by_key resolves in-tenant", (app.find_employee_by_key(emp_key, company_code=company) or {}).get("employee_key") == emp_key)

            # mark received
            recv = app.mark_onboarding_item({"employee_key": emp_key, "item_id": ITEM_RECV, "item_status": "received"}, company_code=company, created_by_phone="96599338566")
            check("mark received reports ok", isinstance(recv, dict) and recv.get("ok") is True)
            check("mark received reports the new status", recv.get("item_status") == "received")

            # waive
            waive = app.mark_onboarding_item({"employee_key": emp_key, "item_id": ITEM_WAIVE, "item_status": "waived"}, company_code=company, created_by_phone="96599338566")
            check("waive reports ok", isinstance(waive, dict) and waive.get("ok") is True)
            check("waive reports the new status", waive.get("item_status") == "waived")

            # the summary reflects both: received item counted, waived item dropped
            summary = app.employee_onboarding_summary(app.find_employee_by_key(emp_key, company_code=company))
            pending_ids = {str(i.get("item_id")) for i in summary.get("pending", [])}
            received_ids = {str(i.get("item_id")) for i in summary.get("received", [])}
            check("received item leaves the pending bucket", ITEM_RECV not in pending_ids)
            check("received item is in the received bucket", ITEM_RECV in received_ids)
            check("waived item is no longer outstanding", ITEM_WAIVE not in pending_ids)
            check("waived item is not faked as received", ITEM_WAIVE not in received_ids)

            # the list rollup picks up the received item too
            counts = app.onboarding_counts_by_employee(company)
            check("list counts include the employee", emp_key in counts)

            # fail-safe paths
            missing_item = app.mark_onboarding_item({"employee_key": emp_key, "item_id": f"ghost_{SUFFIX}", "item_status": "received"}, company_code=company, created_by_phone="96599338566")
            check("unknown item fails safe", isinstance(missing_item, dict) and missing_item.get("ok") is False and missing_item.get("error") == "item_not_found")
            missing_emp = app.mark_onboarding_item({"employee_key": f"ghost_{SUFFIX}", "item_id": ITEM_RECV, "item_status": "received"}, company_code=company, created_by_phone="96599338566")
            check("unknown employee fails safe", isinstance(missing_emp, dict) and missing_emp.get("ok") is False and missing_emp.get("error") == "employee_not_found")
        finally:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM onboarding_items WHERE item_id IN (%s,%s) AND employee_key=%s", (ITEM_RECV, ITEM_WAIVE, emp_key))
                    app.recompute_employee_onboarding_counts(cur, emp_key)
                conn.commit()

    if orig_flag is None:
        os.environ.pop("WATHEFNI_ONBOARDING_HR_MUTATE", None)
    else:
        os.environ["WATHEFNI_ONBOARDING_HR_MUTATE"] = orig_flag

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    ONBOARDING DASHBOARD: FAILURES")
        return 1
    print("    ONBOARDING DASHBOARD: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
