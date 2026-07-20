"""Smoke test: Pre-Hiring registry migration (Phase 2b/2c).

The five native Pre-Hiring dashboard buttons (shortlist / hire / notify / send
assessment / send video interview) can be routed through the SAME action-registry
path the Wathefni Assistant uses, behind WATHEFNI_PREHIRE_VIA_REGISTRY. This test
pins the safety contract for that migration:

  - flag parsing: default OFF; "all"/"1"/true on; comma list enables per action
  - registry parity: hire runs the dedicated executor that ALSO calls
    transition_hire (so the Assistant and the dashboard both create the employee),
    and every action resolves to an allowed Pre-Hiring registry module
  - RBAC parity: TOOL_PERMISSION_MAP matches the legacy require_entitlement
    permissions; viewer cannot manage/decide
  - arg whitelist blocks company/actor spoofing but keeps app_key
  - hire executor: stubbed legacy proves update_application_status AND
    transition_hire are both invoked, and success requires both
  - dashboard harness mechanics (stubbed orchestrator + audit):
      * completed  -> ok, audited as an APPLICATION action (never employee),
        company comes from the session (never the client), refreshed application
        returned for the UI to patch
      * needs_confirmation -> auto-confirmed (the button click is the
        confirmation): the orchestrator is re-invoked once and the action runs
      * permission_denied -> 403 with HR-safe copy
      * unknown / non-pre-hire module -> 404
  - dry-run delivery is safe in this environment
  - behaviour (staging DB): a real shortlist via the registry harness flips the
    application to shortlisted, returns the refreshed application + an audit row,
    and a repeated submit is idempotent (original status restored afterwards)

Run (staging has psycopg2): WATHEFNI_DELIVERY_MODE=dry_run python3 smoke-test-prehire-registry-parity.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")

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


def main() -> int:
    print("    pre-hire registry migration — flag + parity + harness + behaviour")
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

    ACTIONS = ("shortlist_candidate", "hire_candidate", "notify_candidate", "send_assessment", "send_video_interview")

    # --- 1) flag parsing -----------------------------------------------------
    orig_flag = os.environ.get("WATHEFNI_PREHIRE_VIA_REGISTRY")

    def set_flag(value: str | None) -> None:
        if value is None:
            os.environ.pop("WATHEFNI_PREHIRE_VIA_REGISTRY", None)
        else:
            os.environ["WATHEFNI_PREHIRE_VIA_REGISTRY"] = value

    try:
        set_flag(None)
        check("flag unset -> all actions disabled (legacy path)", all(not app._prehire_registry_enabled(a) for a in ACTIONS))
        set_flag("off")
        check("flag 'off' -> disabled", not app._prehire_registry_enabled("shortlist_candidate"))
        set_flag("all")
        check("flag 'all' -> every action enabled", all(app._prehire_registry_enabled(a) for a in ACTIONS))
        set_flag("1")
        check("flag '1' -> enabled", app._prehire_registry_enabled("send_assessment"))
        set_flag("send_assessment,shortlist_candidate")
        check("comma list enables only the named actions", app._prehire_registry_enabled("send_assessment") and app._prehire_registry_enabled("shortlist_candidate"))
        check("comma list leaves unnamed actions disabled", not app._prehire_registry_enabled("hire_candidate"))
    finally:
        set_flag(orig_flag)

    # --- 2) registry parity --------------------------------------------------
    for name in ACTIONS:
        spec = registry.spec_for(name)
        check(f"{name} is registered", spec is not None)
        if spec:
            module = getattr(spec, "module", None)
            check(f"{name} module is a Pre-Hiring registry module", module in app.PREHIRE_DASHBOARD_REGISTRY_MODULES)
            check(f"{name} resolves through the harness module check", app.posthire_action_module(name) in app.PREHIRE_DASHBOARD_REGISTRY_MODULES)
    check("PREHIRE_DASHBOARD_REGISTRY_MODULES is the three Pre-Hiring modules", set(app.PREHIRE_DASHBOARD_REGISTRY_MODULES) == {"pre_hiring", "assessments", "video_interviews"})

    hire_spec = registry.spec_for("hire_candidate")
    check("hire uses the dedicated employee-creating executor", getattr(hire_spec, "executor", None) is registry._hire_candidate_executor)
    check("hire keeps posthire in result_keys", "posthire" in (getattr(hire_spec, "result_keys", ()) or ()))
    check("shortlist still uses the status-only executor", registry.spec_for("shortlist_candidate").executor is not registry._hire_candidate_executor)

    # --- 3) RBAC parity ------------------------------------------------------
    expected_perms = {
        "shortlist_candidate": "candidate.manage",
        "hire_candidate": "candidate.decide",
        "notify_candidate": "candidate.manage",
        "send_assessment": "assessment.manage",
        "send_video_interview": "interview.manage",
    }
    for name, perm in expected_perms.items():
        check(f"{name} maps to {perm}", tco.TOOL_PERMISSION_MAP.get(name) == perm)
    viewer = app.hr_role_permissions("viewer")
    check("viewer cannot manage candidates", "candidate.manage" not in viewer)
    check("viewer cannot decide (hire)", "candidate.decide" not in viewer)

    # --- 4) arg whitelist blocks spoofing ------------------------------------
    safe = app.posthire_whitelisted_args("shortlist_candidate", {"app_key": "APP-1", "company_code": "EVILCO", "actor_role": "owner", "stray": 1})
    check("whitelist keeps app_key", safe.get("app_key") == "APP-1")
    for forbidden in ("company_code", "actor_role", "stray"):
        check(f"whitelist drops {forbidden}", forbidden not in safe)

    # --- 5) hire executor parity (stubbed legacy: must call transition_hire) --
    class FakeLegacy:
        def __init__(self, update_ok: bool = True, transition_ok: bool = True):
            self.update_ok = update_ok
            self.transition_ok = transition_ok
            self.calls: list[str] = []

        def resolve_application_for_action(self, action, allow_latest=False):  # noqa: ANN001
            return {"app_key": action.get("app_key"), "candidate_name": "Test Candidate", "status": "review_pending", "company_code": "WATHEFNI"}

        def update_application_status(self, app_row, status):  # noqa: ANN001
            self.calls.append(f"update:{status}")
            return {"ok": self.update_ok}

        def transition_hire(self, app_row):  # noqa: ANN001
            self.calls.append("transition_hire")
            return {"ok": self.transition_ok}

        def json_safe(self, value):  # noqa: ANN001
            return value

    def run_hire(update_ok: bool, transition_ok: bool):
        legacy = FakeLegacy(update_ok=update_ok, transition_ok=transition_ok)
        request = type(
            "Req",
            (),
            {
                "metadata": {
                    "company_code": "WATHEFNI",
                    "dashboard": True,
                    "permissions": ["candidate.decide", "candidate.manage", "prehire.read"],
                    "actor_type": "human",
                    "actor_user_id": "smoke-hire",
                },
                "sender_role": "hr_admin",
                "sender_phone": "96599338566",
            },
        )()
        ctx = registry.ExecutionContext(
            request=request,
            action={"action_type": "hire_candidate", "app_key": "APP-HIRE", "subject_name": "Test Candidate"},
            state={},
            graph_state={},
            intent={},
            legacy=legacy,
        )
        return legacy, registry.execute("hire_candidate", ctx)

    legacy_ok, hire_ok = run_hire(True, True)
    check("hire executor marks application hired", "update:hired" in legacy_ok.calls)
    check("hire executor runs transition_hire (creates employee)", "transition_hire" in legacy_ok.calls)
    check("hire succeeds only when both steps succeed", hire_ok.get("status") == "completed" and hire_ok.get("success") is True)
    check("hire result carries the posthire outcome for audit", isinstance(hire_ok.get("posthire"), dict))

    _, hire_partial = run_hire(True, False)
    check("hire fails when transition_hire fails (no silent half-hire)", hire_partial.get("success") is False)

    legacy_noupdate, hire_noupdate = run_hire(False, True)
    check("hire skips transition_hire if the status update fails", "transition_hire" not in legacy_noupdate.calls)
    check("hire reports failure if the status update fails", hire_noupdate.get("success") is False)

    # --- 6) dashboard harness mechanics (stubbed orchestrator + audit) -------
    def ctx(role: str = "owner", company: str = "WATHEFNI"):
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
    orig_find = app.find_application_by_key
    orig_summary = app.prehire_application_summary

    def fake_audit(action_type, status, result_payload, reply):  # noqa: ANN001
        audited.append({"action_type": action_type, "status": status, "company": result_payload.get("company_code"), "target_type": (result_payload.get("action") or {}).get("target_type"), "via": result_payload.get("via")})
        return {"result_id": "audit-1"}

    app.dashboard_record_action_result = fake_audit  # type: ignore[assignment]
    app.find_application_by_key = lambda app_key, company_code=None: {"app_key": app_key}  # type: ignore[assignment]
    app.prehire_application_summary = lambda row, **kw: {"app_key": row.get("app_key"), "summary": True}  # type: ignore[assignment]
    try:
        # completed
        captured.clear()
        calls = {"n": 0}

        def fake_execute_completed(tool_name, args, request, state, graph_state, scope):  # noqa: ANN001
            calls["n"] += 1
            captured["args"] = dict(args)
            captured["scope_company"] = scope.get("company_id")
            return {"status": "completed", "result": {"safe_user_message": "Test Candidate is shortlisted."}}

        tco._execute_tool = fake_execute_completed  # type: ignore[assignment]
        resp = app.run_prehire_registry_action(ctx(), "shortlist_candidate", {"company_code": "EVILCO"}, app_key="APP-1")
        check("completed action returns ok", resp.get("ok") is True and resp.get("status") == "completed")
        check("response returns the refreshed application for the UI", isinstance(resp.get("application"), dict) and resp["application"].get("summary") is True)
        check("orchestrator never receives the client company", "company_code" not in captured.get("args", {}))
        check("company comes from the session scope", captured.get("scope_company") == "WATHEFNI")
        check("audited as an APPLICATION action (not employee)", bool(audited) and audited[-1]["target_type"] == "application")
        check("audit records the registry source", audited[-1]["via"] == "registry")
        check("audit company is the session company", audited[-1]["company"] == "WATHEFNI")

        # auto-confirm: needs_confirmation on the first call, completed on the second
        calls["n"] = 0

        def fake_execute_confirm(tool_name, args, request, state, graph_state, scope):  # noqa: ANN001
            calls["n"] += 1
            if calls["n"] == 1:
                return {"status": "needs_confirmation", "action_hash": "h", "preflight_plan": {"confirmation_text": "Confirm?"}}
            return {"status": "completed", "result": {"safe_user_message": "Done."}}

        tco._execute_tool = fake_execute_confirm  # type: ignore[assignment]
        resp = app.run_prehire_registry_action(ctx(), "shortlist_candidate", {}, app_key="APP-2")
        check("auto-confirm re-invokes the orchestrator exactly once", calls["n"] == 2)
        check("auto-confirmed action completes (no modal returned)", resp.get("ok") is True and resp.get("status") == "completed")

        # permission_denied -> 403
        tco._execute_tool = lambda *a, **k: {"status": "permission_denied", "required_permission": "candidate.manage", "message": "internal"}  # type: ignore[assignment]
        denied = False
        try:
            app.run_prehire_registry_action(ctx(role="viewer"), "shortlist_candidate", {}, app_key="APP-3")
        except app.HTTPException as exc:
            denied = exc.status_code == 403 and "do not have access" in str(exc.detail.get("message", "")).lower()
        check("permission_denied maps to a 403 with HR-safe copy", denied)

        # unknown / non-pre-hire module -> 404
        not_found = False
        try:
            app.run_prehire_registry_action(ctx(), "mark_attendance_absent", {}, app_key="APP-4")
        except app.HTTPException as exc:
            not_found = exc.status_code == 404
        check("an action outside the Pre-Hiring modules is rejected with 404", not_found)
    finally:
        tco._execute_tool = orig_execute  # type: ignore[assignment]
        app.dashboard_record_action_result = orig_audit  # type: ignore[assignment]
        app.find_application_by_key = orig_find  # type: ignore[assignment]
        app.prehire_application_summary = orig_summary  # type: ignore[assignment]

    # --- 7) dry-run delivery is safe ----------------------------------------
    check("delivery is in dry-run for this test", app.delivery_is_dry_run() is True)
    dry = app.send_octopus_whatsapp(account_id="WATHEFNI", phone="96599338566", text="parity smoke", subject_type="candidate", subject_key="APP-SMOKE")
    check("send returns a simulated dry-run result (no real send)", isinstance(dry, dict) and dry.get("ok") is True and dry.get("dry_run") is True)

    # --- 8) behaviour against the DB: real shortlist via the registry harness -
    real_app: dict | None = None
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT a.app_key, a.company_code, a.status
                    FROM applications a
                    JOIN candidates c ON c.phone = a.phone
                    WHERE a.app_key <> '' AND a.company_code IS NOT NULL
                    ORDER BY a.updated_at DESC NULLS LAST
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                if row:
                    real_app = dict(row)
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"    (could not read applications: {exc} — skipping DB behaviour)")

    if not real_app:
        print("    (no applications on this DB — skipping DB behaviour checks)")
    else:
        app_key = str(real_app["app_key"])
        company = str(real_app["company_code"]).upper()
        original_status = real_app.get("status")
        real_ctx = {
            "company_code": company,
            "hr_phone": "96599338566",
            "hr_user": {"role": "owner", "status": "active", "company_code": company, "user_id": "smoke-owner"},
            "access": {"role": "owner", "permissions": sorted(app.hr_role_permissions("owner"))},
            "permissions": sorted(app.hr_role_permissions("owner")),
            "actor_user_id": "smoke-owner",
            "permission_authority": "backend_current",
            "permission_subject_user_id": "smoke-owner",
            "permission_subject_company": company,
            "actor_email": "owner@example.com",
            "actor_role": "owner",
        }
        try:
            resp = app.run_prehire_registry_action(real_ctx, "shortlist_candidate", {}, app_key=app_key)
            check("real shortlist via registry completes", resp.get("ok") is True and resp.get("status") == "completed")
            check("real shortlist returns the refreshed application", isinstance(resp.get("application"), dict) and resp["application"].get("app_key") == app_key)
            check("real shortlist writes an audit row", bool(resp.get("audit")))
            refreshed = app.find_application_by_key(app_key, company_code=company) or {}
            check("application is now shortlisted in the DB", str(refreshed.get("status") or "").lower() == "shortlisted")

            resp2 = app.run_prehire_registry_action(real_ctx, "shortlist_candidate", {}, app_key=app_key)
            check("repeated submit is idempotent / safe", resp2.get("ok") is True and resp2.get("status") == "completed")
        finally:
            if original_status:
                try:
                    restore = app.find_application_by_key(app_key, company_code=company)
                    if restore:
                        app.update_application_status(restore, str(original_status))
                except Exception:
                    print("    (warning: could not restore original application status)")

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    PRE-HIRE REGISTRY PARITY: FAILURES")
        return 1
    print("    PRE-HIRE REGISTRY PARITY: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
