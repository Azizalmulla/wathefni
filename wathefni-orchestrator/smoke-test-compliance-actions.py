"""Smoke test: Compliance V1.1 actions (send reminder / mark reviewed).

These are the first mutating compliance actions. They must run through the SAME
registry + dashboard harness as every other post-hire action, so they inherit
company scoping, RBAC, and audit. This test pins:

  - both actions are registered under the compliance module with compliance.manage,
    no surprise confirmation, and are reachable via the dashboard harness
    (POSTHIRE_DASHBOARD_MODULES + TOOL_PERMISSION_MAP + gated modules)
  - RBAC: owner/hr_manager manage; viewer is read-only (denied manage)
  - the dashboard harness whitelists args (no company/actor spoofing), maps a
    completed outcome to an audited result, and a permission_denied outcome to 403
  - behaviour (staging DB): mark_compliance_reviewed clears a 'needs review'
    document; send_compliance_reminder bumps reminder bookkeeping on a successful
    send and reports 'nothing outstanding' when there is nothing to chase

Run (staging has psycopg2): python3 smoke-test-compliance-actions.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0
TEST_DOC = f"zz_test_{uuid.uuid4().hex[:8]}"


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    compliance V1.1 actions — registry + RBAC + harness + behaviour")
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

    # --- 1) registry specs ---------------------------------------------------
    for name in ("compliance_send_reminder", "compliance_mark_reviewed"):
        spec = registry.spec_for(name)
        check(f"{name} is registered", spec is not None)
        if spec:
            check(f"{name} module is compliance", getattr(spec, "module", None) == "compliance")
            check(f"{name} has an executor", bool(getattr(spec, "executor", None)))
            check(f"{name} does not force confirmation", getattr(spec, "requires_confirmation", False) is False)

    # --- 2) reachable through the dashboard harness + orchestrator gating ----
    check("compliance is a dashboard post-hire module", "compliance" in app.POSTHIRE_DASHBOARD_MODULES)
    check("compliance is a gated tool-call module", "compliance" in tco.TOOLCALL_GATED_MODULES)
    check("send reminder maps to compliance.manage", tco.TOOL_PERMISSION_MAP.get("compliance_send_reminder") == "compliance.manage")
    check("mark reviewed maps to compliance.manage", tco.TOOL_PERMISSION_MAP.get("compliance_mark_reviewed") == "compliance.manage")
    check("harness resolves the compliance module", app.posthire_action_module("compliance_send_reminder") == "compliance")

    # --- 3) RBAC -------------------------------------------------------------
    check("owner has compliance.manage", "compliance.manage" in app.hr_role_permissions("owner"))
    check("hr_manager has compliance.manage", "compliance.manage" in app.hr_role_permissions("hr_manager"))
    check("viewer is read-only on compliance", "compliance.read" in app.hr_role_permissions("viewer") and "compliance.manage" not in app.hr_role_permissions("viewer"))

    # --- 4) arg whitelist blocks scope/actor spoofing ------------------------
    dirty = {"employee_name": "Sara", "document_type": "civil_id", "company_code": "EVILCO", "actor_role": "owner", "stray": 1}
    safe = app.posthire_whitelisted_args("compliance_send_reminder", dirty)
    check("whitelist keeps employee_name + document_type", safe == {"employee_name": "Sara", "document_type": "civil_id"})
    for forbidden in ("company_code", "actor_role", "stray"):
        check(f"whitelist drops {forbidden}", forbidden not in safe)

    # --- 5) harness outcome mapping (stub orchestrator + audit, no DB) -------
    def ctx(role: str = "hr_manager", company: str = "WATHEFNI"):
        perms = sorted(app.hr_role_permissions(role))
        return {
            "company_code": company,
            "hr_phone": "96599338566",
            "hr_user": {"role": role, "status": "active", "company_code": company, "user_id": f"smoke-{role}"},
            "access": {"role": role, "permissions": perms},
            "permissions": perms,
            "actor_user_id": f"smoke-{role}",
            "permission_authority": "backend_current",
            "permission_subject_user_id": f"smoke-{role}",
            "permission_subject_company": company,
            "actor_email": f"{role}@example.com",
            "actor_role": role,
        }

    captured: dict = {}
    audited: list = []
    orig_execute = tco._execute_tool
    orig_audit = app.dashboard_record_action_result

    def fake_execute(tool_name, args, request, state, graph_state, scope):  # noqa: ANN001
        captured["tool_name"] = tool_name
        captured["args"] = dict(args)
        captured["scope_company"] = scope.get("company_id")
        return captured["outcome"]

    def fake_audit(action_type, status, result_payload, reply):  # noqa: ANN001
        audited.append({"action_type": action_type, "status": status, "company": result_payload.get("company_code")})
        return {"result_id": "audit-1"}

    tco._execute_tool = fake_execute  # type: ignore[assignment]
    app.dashboard_record_action_result = fake_audit  # type: ignore[assignment]
    try:
        captured["outcome"] = {"status": "completed", "result": {"safe_user_message": "Compliance reminder sent to Sara."}}
        resp = app.run_posthire_dashboard_action(ctx(), "compliance_send_reminder", {"employee_name": "Sara", "document_type": "civil_id", "company_code": "EVILCO"})
        check("completed reminder returns ok", resp.get("ok") is True and resp.get("status") == "completed")
        check("orchestrator never receives client company", "company_code" not in captured["args"])
        check("company comes from the session scope", captured.get("scope_company") == "WATHEFNI")
        check("completed action is audited", bool(audited) and audited[-1]["status"] == "completed" and audited[-1]["company"] == "WATHEFNI")

        captured["outcome"] = {"status": "permission_denied", "required_permission": "compliance.manage", "message": "internal"}
        denied = False
        try:
            app.run_posthire_dashboard_action(ctx(), "compliance_mark_reviewed", {"employee_name": "Sara", "document_type": "civil_id"})
        except app.HTTPException as exc:
            denied = exc.status_code == 403 and "do not have access" in str(exc.detail.get("message", "")).lower()
        check("permission_denied maps to a 403 with HR-safe copy", denied)
    finally:
        tco._execute_tool = orig_execute  # type: ignore[assignment]
        app.dashboard_record_action_result = orig_audit  # type: ignore[assignment]

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
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO compliance_documents (employee_key, document_type, label, status, raw_json, company_code)
                    VALUES (%s,%s,%s,'received','{}'::jsonb,%s)
                    """,
                    (emp_key, TEST_DOC, "ZZ Test Document", real_emp.get("company_code")),
                )
            conn.commit()
        orig_send = app.send_octopus_whatsapp
        try:
            docs = app.compliance_outstanding_docs(emp_key, TEST_DOC)
            check("a received doc with no expiry is classified needs_review", bool(docs) and docs[0].get("_bucket") == "needs_review")

            app.send_octopus_whatsapp = lambda **kwargs: {"ok": True, "dry_run": True}  # type: ignore[assignment]
            result = app.send_compliance_reminder(real_emp, TEST_DOC, None)
            check("send_compliance_reminder reports ok", isinstance(result, dict) and result.get("ok") is True)
            after = app.compliance_outstanding_docs(emp_key, TEST_DOC)
            check("reminder bumps reminder_count", bool(after) and int(after[0].get("reminder_count") or 0) >= 1)

            reviewed = app.mark_compliance_reviewed(real_emp, TEST_DOC)
            check("mark_compliance_reviewed reports ok", isinstance(reviewed, dict) and reviewed.get("ok") is True)
            post = app.compliance_outstanding_docs(emp_key, TEST_DOC)
            check("a reviewed doc leaves the needs_review bucket", bool(post) and post[0].get("_bucket") == "valid")

            nothing = app.send_compliance_reminder(real_emp, TEST_DOC, None)
            check("reminder reports nothing outstanding once reviewed", isinstance(nothing, dict) and nothing.get("error") == "nothing_outstanding")
        finally:
            app.send_octopus_whatsapp = orig_send  # type: ignore[assignment]
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM compliance_documents WHERE document_type=%s AND employee_key=%s", (TEST_DOC, emp_key))
                conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    COMPLIANCE ACTIONS: FAILURES")
        return 1
    print("    COMPLIANCE ACTIONS: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
