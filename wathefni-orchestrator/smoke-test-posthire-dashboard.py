"""Smoke test for the post-hire dashboard action wiring.

The dashboard's native post-hire buttons must be exactly as safe as the AI
Recruiter, because they run through the SAME action registry path
(tool_call_orchestrator._execute_tool). This test pins the security-critical
glue in app.py:

  * posthire_whitelisted_args drops anything the client should not control —
    company_code, actor_* fields, viewer_phone, and any stray keys — keeping
    only the registry-declared fields. This blocks company-boundary / actor
    spoofing from the browser.
  * posthire_action_module resolves the owning module and refuses non-post-hire
    or unknown actions (so the dashboard endpoint cannot drive pre-hiring tools).
  * posthire_dashboard_scope sources the company, actor, role, and permissions
    from the authenticated session — never from request args.
  * run_posthire_dashboard_action faithfully maps the orchestrator outcomes:
      - needs_confirmation  -> a clean confirmation payload (no internals),
                               re-sending only the whitelisted args
      - permission_denied / module_disabled -> 403 with HR-safe copy
      - completed           -> ok + audited via dashboard_record_action_result
    and the args that reach the orchestrator carry no client-supplied company.

It stubs tool_call_orchestrator._execute_tool and app.dashboard_record_action_result
so nothing touches the database; the orchestrator's real RBAC/confirmation logic
is covered by smoke-test-posthire-registry.py.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))

    try:
        import app  # noqa: F401
    except ModuleNotFoundError as exc:
        # Local dev boxes without psycopg2 cannot import the full app; the
        # staging venv can, and that is the gate that matters.
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full app import only runs on staging.")
            return 0
        raise

    import tool_call_orchestrator as tco

    def check(condition: bool, message: str) -> None:
        if not condition:
            raise AssertionError(message)

    def context(role: str = "hr_manager", company: str = "WATHEFNI", permissions=None):
        perms = permissions if permissions is not None else sorted(app.hr_role_permissions(role))
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

    # 1) Arg whitelist blocks company / actor / scope spoofing and stray keys.
    dirty = {
        "employee_name": "Sara",
        "date": "2026-06-04",
        "company_code": "EVILCO",
        "actor_user_id": "attacker",
        "actor_role": "owner",
        "viewer_phone": "0000",
        "permissions": ["payroll.export"],
        "subject_key": "x",
        "totally_unknown": 1,
    }
    safe = app.posthire_whitelisted_args("mark_attendance_absent", dirty)
    check(safe == {"employee_name": "Sara", "date": "2026-06-04"}, f"whitelist must keep only declared fields, got {safe}")
    for forbidden in ("company_code", "actor_user_id", "actor_role", "viewer_phone", "permissions", "totally_unknown"):
        check(forbidden not in safe, f"whitelist must drop {forbidden}")
    check(app.posthire_whitelisted_args("does_not_exist", {"a": 1}) == {}, "unknown action whitelists to nothing")

    # 2) Module resolution: post-hire actions map to their module; pre-hiring /
    #    unknown actions are not dashboard post-hire actions.
    check(app.posthire_action_module("mark_attendance_absent") == "attendance", "attendance action module")
    check(app.posthire_action_module("export_payroll") == "payroll", "payroll action module")
    check(app.posthire_action_module("approve_leave_request") == "leave", "leave action module")
    check(app.posthire_action_module("shortlist_candidate") == "pre_hiring", "pre-hiring action still reports its module")
    check(app.posthire_action_module("does_not_exist") is None, "unknown action has no module")

    # 3) Scope is sourced from the session, never the client.
    scope = app.posthire_dashboard_scope(context(role="hr_manager"), "conv-1")
    check(scope["company_id"] == "WATHEFNI", "scope company comes from context")
    check(scope["channel"] == "web_dashboard", "scope channel is web_dashboard")
    check(scope["role_scope"] == "hr_manager", "scope role from context")
    check(scope["permissions"] == sorted(scope["permissions"]), "scope permissions sorted")

    # --- stub the orchestrator + audit so nothing hits the DB ---------------
    captured: dict = {}

    def fake_execute(tool_name, args, request, state, graph_state, scope):  # noqa: ANN001
        captured["tool_name"] = tool_name
        captured["args"] = dict(args)
        captured["scope_company"] = scope.get("company_id")
        return captured["outcome"]

    audited: list = []

    def fake_audit(action_type, status, result_payload, reply):  # noqa: ANN001
        audited.append({"action_type": action_type, "status": status, "company": result_payload.get("company_code")})
        return {"result_id": "audit-1"}

    tco._execute_tool = fake_execute  # type: ignore[assignment]
    app.dashboard_record_action_result = fake_audit  # type: ignore[assignment]

    ctx = context(role="hr_manager")

    # 4a) needs_confirmation -> clean confirmation payload; orchestrator never
    #     receives a client-supplied company.
    captured["outcome"] = {
        "status": "needs_confirmation",
        "action_hash": "hash-123",
        "preflight_plan": {"confirmation_text": "Mark Sara absent for 2026-06-04?"},
        "result": {},
    }
    resp = app.run_posthire_dashboard_action(ctx, "mark_attendance_absent", {"employee_name": "Sara", "date": "2026-06-04", "company_code": "EVILCO"})
    check(resp["ok"] is False and resp["status"] == "needs_confirmation", "sensitive action must ask for confirmation")
    check(resp["confirmation"] and resp["confirmation"]["action_type"] == "mark_attendance_absent", "confirmation echoes action")
    check("company_code" not in resp["confirmation"]["args"], "confirmation args carry no client company")
    check("company_code" not in captured["args"], "orchestrator must not receive client company in args")
    check(captured["scope_company"] == "WATHEFNI", "orchestrator company comes from session scope")
    check(not audited, "needs_confirmation is not audited as a terminal action")

    # 4b) completed -> ok + audited.
    captured["outcome"] = {"status": "completed", "result": {"safe_user_message": "Sara is marked absent."}}
    resp = app.run_posthire_dashboard_action(ctx, "mark_attendance_absent", {"employee_name": "Sara", "date": "2026-06-04"})
    check(resp["ok"] is True and resp["status"] == "completed", "completed action returns ok")
    check(resp["message"] == "Sara is marked absent.", "HR-safe message surfaced")
    check(audited and audited[-1]["status"] == "completed" and audited[-1]["company"] == "WATHEFNI", "completed action is audited for the company")

    # 4c) permission_denied -> 403 with safe copy, no internals leaked.
    captured["outcome"] = {"status": "permission_denied", "required_permission": "attendance.manage", "message": "internal"}
    try:
        app.run_posthire_dashboard_action(ctx, "mark_attendance_absent", {"employee_name": "Sara"})
        raise SystemExit("permission_denied should raise")
    except app.HTTPException as exc:
        check(exc.status_code == 403, "permission_denied -> 403")
        check("permission" not in str(exc.detail.get("message", "")).lower() or "do not have access" in str(exc.detail.get("message", "")).lower(), "denied copy is HR-safe")

    # 4d) module_disabled -> 403.
    captured["outcome"] = {"status": "module_disabled", "required_module": "attendance", "message": "internal"}
    try:
        app.run_posthire_dashboard_action(ctx, "mark_attendance_absent", {"employee_name": "Sara"})
        raise SystemExit("module_disabled should raise")
    except app.HTTPException as exc:
        check(exc.status_code == 403, "module_disabled -> 403")

    # 5) A pre-hiring (non post-hire) action cannot be driven via this endpoint.
    try:
        app.run_posthire_dashboard_action(ctx, "shortlist_candidate", {"app_key": "abc"})
        raise SystemExit("pre-hiring action should be rejected")
    except app.HTTPException as exc:
        check(exc.status_code == 404, "non post-hire action -> 404")

    print("post-hire dashboard action wiring checks passed (whitelist, module gate, scope, confirmation, audit, RBAC mapping).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
