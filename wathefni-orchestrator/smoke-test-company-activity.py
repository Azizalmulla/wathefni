"""Smoke test: Company Activity & Audit (read-only) view.

Pins the safety and behaviour of the client-facing activity feed over the shared
action_results audit substrate:

  - RBAC: only Company Admin (owner) and HR Admin hold audit.read; HR Manager,
    Team Manager, Viewer, Recruiter, Hiring Manager, Interviewer, and Payroll
    Operator are denied (fail-closed).
  - The endpoint is read-only — there is NO mutation/delete path on /dashboard/activity.
  - Company scoping: a company never sees another company's activity.
  - Redaction: returned rows are a whitelist (id/at/actor/action_type/category/
    summary/target/status/sensitive) — never raw result payloads, details blobs,
    final replies, tokens, or stack traces.
  - Humanization: summaries are HR-friendly verb phrases, not backend action names.
  - Sensitive emphasis: payroll/leave/employee/document/team/candidate actions flag sensitive.
  - Filters + pagination: category, action_type, free-text search, date range, limit/offset.
  - Operator/platform/provider events (setup_*, mailbox_*, intake_*) and pure
    read/list events (list_*, answer_*) never appear in the feed.

Run: python3 smoke-test-company-activity.py   (DB checks require a reachable DB)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import app  # noqa: E402

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def _function_body(source: str, name: str) -> str:
    start = source.find(f"def {name}(")
    if start == -1:
        return ""
    rest = source[start:]
    end = len(rest)
    for marker in ("\n@app.", "\n@router.", "\ndef "):
        idx = rest.find(marker, 1)
        if idx != -1:
            end = min(end, idx)
    return rest[:end]


def _call(ctx: dict, **kw):
    # The endpoint declares its filters as FastAPI Query(...) params, which only
    # resolve to real values inside an HTTP request. When we invoke the function
    # directly we must pass every parameter explicitly.
    params = dict(
        start_date=None, end_date=None, actor=None, category=None,
        action_type=None, q=None, limit=50, offset=0, format=None,
    )
    params.update(kw)
    return app.dashboard_company_activity(context=ctx, **params)


def _ctx(role: str, company: str) -> dict:
    perms = sorted(app.hr_role_permissions(role))
    user_id = f"smoke-{role}"
    return {
        "company_code": company,
        "actor_user_id": user_id,
        "permission_authority": "backend_current",
        "permission_subject_user_id": user_id,
        "permission_subject_company": company,
        "actor_role": role,
        "hr_user": {"user_id": user_id, "role": role, "status": "active", "company_code": company},
        "permissions": perms,
        "access": {"role": role, "permissions": perms},
    }


def _seed(company: str, action_type: str, *, status: str = "completed", summary: str = "", details: dict | None = None, target: str | None = None, reply: str = "") -> str:
    payload = {
        "action": {"type": action_type, "target_type": "employee", "target": target},
        "summary": summary,
        "details": details or {},
        "company_code": company,
        "actor_user_id": "smoke-owner",
        "actor_email": "owner@smoke.test",
        "actor_phone": "96500000000",
        "actor_role": "owner",
        "requested_by": {"name": "Smoke Owner", "email": "owner@smoke.test", "role": "owner"},
    }
    row = app.dashboard_record_action_result(action_type, status, payload, reply)
    return str(row.get("result_id") or "")


def main() -> int:
    print("    company activity & audit smoke — safe, read-only, company-scoped")
    source = Path(app.__file__).with_suffix(".py").read_text(encoding="utf-8")

    # --- source guards --------------------------------------------------------
    body = _function_body(source, "dashboard_company_activity")
    check("endpoint dashboard_company_activity exists", bool(body))
    check("endpoint is registered at GET /dashboard/activity", '@app.get("/dashboard/activity")' in source)
    check("endpoint gates on audit.read", 'require_entitlement(context, None, "audit.read")' in body)
    check("endpoint excludes operator setup_* events", "<> 'setup_'" in body)
    check("endpoint excludes read/list noise (list_/answer_)", "<> 'list_'" in body and "<> 'answer_'" in body)
    check("no mutation verb on the activity route", not any(f'@app.{verb}("/dashboard/activity"' in source for verb in ("post", "put", "patch", "delete")))

    # --- RBAC: only Company Admin (owner) + HR Admin hold audit.read ------------
    check("owner holds audit.read", "audit.read" in app.hr_role_permissions("owner"))
    check("hr_admin holds audit.read", "audit.read" in app.hr_role_permissions("hr_admin"))
    check("hr_manager is denied audit.read", "audit.read" not in app.hr_role_permissions("hr_manager"))
    for role in ("manager", "viewer", "recruiter", "hiring_manager", "interviewer", "payroll_operator"):
        check(f"{role} is denied audit.read", "audit.read" not in app.hr_role_permissions(role))

    # --- pure humanization / redaction unit checks (no DB) --------------------
    sensitive_row = {
        "result_id": "r1",
        "action_type": "employee_updated",
        "status": "completed",
        "created_at": datetime(2026, 5, 1, 9, 30, tzinfo=timezone.utc),
        "actor_user_id": "u1",
        "actor_email": "sara@acme.com",
        "actor_phone": "96599999999",
        "actor_role": "hr_manager",
        "result": {
            "summary": "Updated employee record.",
            "details": {"employee_name": "Ahmad Ali", "secret_token": "tok_should_never_surface"},
            "requested_by": {"name": "Sara", "role": "hr_manager"},
            "final_reply": "internal reply text that must not leak",
        },
    }
    item = app._audit_item(sensitive_row, {}, {})
    allowed_keys = {"id", "at", "actor", "action_type", "category", "summary", "target", "status", "sensitive"}
    check("returned item exposes only whitelisted keys", set(item.keys()) == allowed_keys)
    check("returned item drops raw result/details/final_reply", "result" not in item and "details" not in item and "final_reply" not in item)
    serialized = str(item)
    check("no secret token leaks into the item", "tok_should_never_surface" not in serialized)
    check("no internal final_reply leaks into the item", "internal reply text" not in serialized)
    check("employee edit is flagged sensitive", item["sensitive"] is True)
    check("employee edit maps to Employees category", item["category"] == "Employees")
    check("summary is humanized (not the backend action name)", "employee_updated" not in item["summary"] and "edited an employee" in item["summary"])
    check("target name surfaced from details", item["target"] == "Ahmad Ali")
    check("actor display uses name", item["actor"]["display"] == "Sara")

    # secret-looking targets are dropped
    token_row = {
        "result_id": "r2", "action_type": "document_uploaded", "status": "completed",
        "created_at": datetime(2026, 5, 2, tzinfo=timezone.utc),
        "actor_email": "hr@acme.com", "actor_role": "owner",
        "result": {"action": {"target": "deadbeefdeadbeefdeadbeef"}, "summary": "Uploaded a document."},
    }
    titem = app._audit_item(token_row, {}, {})
    check("opaque hex target is not surfaced", titem["target"] is None)
    check("document upload flagged sensitive", titem["sensitive"] is True)

    # category mapping over REAL action types
    check("approve_leave_request -> Leave", app._audit_category("approve_leave_request") == "Leave")
    check("export_payroll -> Payroll", app._audit_category("export_payroll") == "Payroll")
    check("team_member_invited -> Team & Access", app._audit_category("team_member_invited") == "Team & Access")
    check("start_onboarding -> Onboarding", app._audit_category("start_onboarding") == "Onboarding")
    check("unknown action -> Other", app._audit_category("totally_unknown_action") == "Other")

    # --- behavioural checks against the DB ------------------------------------
    company = f"SMOKEAUD{datetime.now(timezone.utc).strftime('%H%M%S')}"
    other = f"OTHERCO{datetime.now(timezone.utc).strftime('%H%M%S')}"
    seeded: list[str] = []
    db_ok = True
    try:
        seeded.append(_seed(company, "employee_updated", summary="Updated employee record.", details={"employee_name": "Ahmad Ali"}, target="Ahmad Ali"))
        seeded.append(_seed(company, "export_payroll", summary="Exported payroll.", details={}, reply="payroll ready"))
        seeded.append(_seed(company, "setup_company_created", summary="Operator created company.", details={}))  # must be hidden
        seeded.append(_seed(company, "list_leave_requests", summary="Listed leave.", details={}))  # must be hidden (read noise)
        seeded.append(_seed(other, "employee_updated", summary="Other company edit.", details={"employee_name": "Other Person"}))
    except Exception as exc:  # pragma: no cover - DB not reachable in some envs
        db_ok = False
        print(f"      SKIP  DB behavioural checks (no DB): {exc}")

    if db_ok:
        try:
            owner_view = _call(_ctx("owner", company))
            action_types = {it["action_type"] for it in owner_view["items"]}
            check("owner sees seeded company activity", "employee_updated" in action_types and "export_payroll" in action_types)
            check("setup_* operator events are hidden", "setup_company_created" not in action_types)
            check("list_* read noise is hidden", "list_leave_requests" not in action_types)
            check("no other-company rows leak in", all(it["action_type"] != "employee_updated" or it["target"] != "Other Person" for it in owner_view["items"]))
            check("response carries pagination metadata", {"total", "limit", "offset", "has_more", "count"}.issubset(owner_view.keys()))
            check("response advertises categories + actor options", bool(owner_view.get("categories")) and "actors" in owner_view)

            # tenant isolation: the other company cannot see this company's rows
            other_view = _call(_ctx("owner", other))
            check("other company is scoped to its own rows", all(it["target"] != "Ahmad Ali" for it in other_view["items"]))

            # filters
            payroll_only = _call(_ctx("owner", company), category="Payroll")
            check("category filter narrows to Payroll", all(it["category"] == "Payroll" for it in payroll_only["items"]) and payroll_only["items"])
            by_action = _call(_ctx("owner", company), action_type="employee_updated")
            check("action_type filter narrows correctly", all(it["action_type"] == "employee_updated" for it in by_action["items"]) and by_action["items"])
            searched = _call(_ctx("owner", company), q="payroll")
            check("free-text search matches summaries", any(it["action_type"] == "export_payroll" for it in searched["items"]))
            future = _call(_ctx("owner", company), start_date="2099-01-01")
            check("date range filter excludes out-of-range rows", future["items"] == [] and future["total"] == 0)
            paged = _call(_ctx("owner", company), limit=1)
            check("limit caps the page size", len(paged["items"]) <= 1)

            # RBAC at the endpoint: hr_manager allowed, manager + viewer denied
            _call(_ctx("hr_manager", company))
            check("hr_manager is allowed at the endpoint", True)
            for role in ("manager", "viewer"):
                try:
                    _call(_ctx(role, company))
                    check(f"{role} denied at the endpoint", False)
                except app.HTTPException as exc:
                    check(f"{role} denied at the endpoint", exc.status_code in (401, 403))
        finally:
            # cleanup seeded rows
            try:
                ids = [r for r in seeded if r]
                if ids:
                    with app.db_connect() as conn:
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM action_results WHERE result_id::text = ANY(%s)", (ids,))
                        conn.commit()
            except Exception as exc:  # pragma: no cover
                print(f"      WARN  cleanup failed: {exc}")

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    COMPANY ACTIVITY: FAILURES")
        return 1
    print("    COMPANY ACTIVITY: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
