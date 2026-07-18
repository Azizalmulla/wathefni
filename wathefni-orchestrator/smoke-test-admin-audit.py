"""Smoke test: admin/config mutations leave an audit trail.

For serious private companies, every config change must be traceable to an actor
and company. This test pins:

  - record_admin_audit writes into the shared action_results store with the right
    action_type, status, company, and actor context
  - the audit summary is HR-safe (no raw permission tokens / internal codes)
  - auditing is BEST-EFFORT: if the underlying recorder raises, the config change
    is NOT rolled back and no exception escapes
  - every admin/config endpoint that mutates state actually wires an audit call
    (source-level guard so coverage cannot silently regress)

Run: python3 smoke-test-admin-audit.py
"""

from __future__ import annotations

import re
import sys
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


# Action types we expect to be emitted by the admin/config endpoints. These string
# literals only appear inside record_admin_audit(...) calls, so their presence in
# the source is a reliable coverage guard.
EXPECTED_ACTION_TYPES = [
    "team_member_invited",
    "team_member_deactivated",
    "team_member_reactivated",
    "team_member_role_changed",
    "team_member_updated",
    "team_whatsapp_linked",
    "mailbox_connection_started",
    "mailbox_settings_updated",
    "mailbox_disconnected",
    "intake_address_created",
    "intake_address_deleted",
    "import_settings_updated",
    "import_candidate_assigned",
    "import_bulk_action",
]

# Endpoint functions that mutate admin/config state and must call record_admin_audit.
ENDPOINTS_REQUIRING_AUDIT = [
    "dashboard_team_invite_user",
    "dashboard_team_update_user",
    "dashboard_team_link_whatsapp",
    "dashboard_mailbox_connect",
    "dashboard_mailbox_update",
    "dashboard_mailbox_disconnect",
    "dashboard_intake_create",
    "dashboard_intake_delete",
    "dashboard_prehire_import_settings_update",
    "dashboard_prehire_import_assign",
    "dashboard_prehire_import_bulk",
]


def _function_body(source: str, name: str) -> str:
    """Return the source slice for a top-level function, from its def line to the
    next top-level def/decorator."""
    start = source.find(f"def {name}(")
    if start == -1:
        return ""
    rest = source[start:]
    # The function ends at the next top-level `@app.` decorator or `def ` at column 0.
    end = len(rest)
    for marker in ("\n@app.", "\n@router.", "\ndef "):
        idx = rest.find(marker, 1)
        if idx != -1:
            end = min(end, idx)
    return rest[:end]


def main() -> int:
    print("    admin/config audit smoke — every config change is traceable")

    source = Path(app.__file__).with_suffix(".py").read_text(encoding="utf-8")

    # --- coverage guard: each endpoint wires an audit call --------------------
    for fn in ENDPOINTS_REQUIRING_AUDIT:
        body = _function_body(source, fn)
        check(f"{fn} calls record_admin_audit", "record_admin_audit(" in body)

    # --- each expected action type is emitted somewhere -----------------------
    for action_type in EXPECTED_ACTION_TYPES:
        check(f"action type '{action_type}' is wired", f'"{action_type}"' in source)

    # --- behavior: record_admin_audit records the right row -------------------
    captured: list[dict] = []

    def fake_recorder(action_type, status, payload, final_reply):
        captured.append({"action_type": action_type, "status": status, "payload": payload, "reply": final_reply})
        return {"result_id": "test"}

    original = app.dashboard_record_action_result
    app.dashboard_record_action_result = fake_recorder  # type: ignore[assignment]
    try:
        ctx = {
            "company_code": "ACME",
            "actor_user_id": "user-123",
            "permission_authority": "backend_current",
            "permission_subject_user_id": "user-123",
            "permission_subject_company": "ACME",
            "actor_email": "hr@acme.com",
            "actor_phone": "96599999999",
            "actor_role": "owner",
            "hr_user": {"user_id": "user-123", "role": "owner", "email": "hr@acme.com"},
        }
        app.record_admin_audit(
            ctx,
            "team_member_role_changed",
            summary="Updated hr@acme.com: role \u2192 hr_manager.",
            target_type="team_member",
            target="hr@acme.com",
            details={"role": "hr_manager"},
        )
        check("audit wrote exactly one row", len(captured) == 1)
        row = captured[0] if captured else {}
        payload = row.get("payload") or {}
        check("audit action_type is preserved", row.get("action_type") == "team_member_role_changed")
        check("audit status defaults to completed", row.get("status") == "completed")
        check("audit payload carries company_code", payload.get("company_code") == "ACME")
        check("audit payload carries actor_user_id", payload.get("actor_user_id") == "user-123")
        check("audit payload action.type matches", (payload.get("action") or {}).get("type") == "team_member_role_changed")
        check("audit payload action.target_type set", (payload.get("action") or {}).get("target_type") == "team_member")
        check("audit summary has no raw permission tokens", not re.search(r"\b[a-z_]+\.(manage|read|export|decide|import)\b", str(payload.get("summary") or "")))

        # --- best-effort: a recorder failure must NOT escape ------------------
        def boom(*args, **kwargs):
            raise RuntimeError("audit store unavailable")

        app.dashboard_record_action_result = boom  # type: ignore[assignment]
        raised = False
        try:
            app.record_admin_audit(ctx, "team_member_deactivated", summary="Deactivated a teammate.")
        except Exception:
            raised = True
        check("audit failure never escapes into the request path", not raised)
    finally:
        app.dashboard_record_action_result = original  # type: ignore[assignment]

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    ADMIN AUDIT: FAILURES")
        return 1
    print("    ADMIN AUDIT: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
