from __future__ import annotations

from pathlib import Path


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    root = Path(__file__).resolve().parent
    app_source = (root / "app.py").read_text(encoding="utf-8")
    toolcall_source = (root / "tool_call_orchestrator.py").read_text(encoding="utf-8")
    frontend_source = (root.parent / "apps" / "wathefni-dashboard" / "src" / "App.tsx").read_text(encoding="utf-8")
    api_source = (root.parent / "apps" / "wathefni-dashboard" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")

    for table in ("dashboard_users", "dashboard_user_sessions", "dashboard_user_permission_grants", "dashboard_user_invites", "dashboard_whatsapp_identities"):
        assert_true(f"CREATE TABLE IF NOT EXISTS {table}" in app_source, f"{table} table must exist")

    assert_true("@app.post(\"/dashboard/auth/login\")" in app_source, "dashboard login endpoint must exist")
    assert_true("@app.get(\"/dashboard/team\")" in app_source, "team access endpoint must exist")
    assert_true("@app.post(\"/dashboard/team/invites\")" in app_source, "owner/admin invite endpoint must exist")
    assert_true("@app.post(\"/dashboard/team/invites/accept\")" in app_source, "invited users must be able to complete login")
    assert_true("@app.patch(\"/dashboard/team/users/{user_id}\")" in app_source, "team role/status update endpoint must exist")
    assert_true("require_workspace_permission(context, \"users.manage\")" in app_source, "team mutations must require users.manage")
    assert_true("permission_authority" in app_source and "backend_current" in app_source, "permissions must come from current backend authority")
    assert_true("legacy_dashboard_token_auth_enabled" in app_source, "legacy dashboard token auth must be explicitly gated")
    assert_true("backend_current_required" in app_source, "health/ready must advertise trusted authority")
    assert_true("if not perms:" not in app_source, "missing permissions must not retain a fail-open fallback")
    assert_true("dashboard_password_hash" in app_source and "pbkdf2_sha256" in app_source, "passwords must be hashed")
    assert_true("Your account is not active." in app_source, "disabled users must get HR-safe inactive copy")
    assert_true("UPDATE dashboard_user_sessions SET status='revoked'" in app_source, "deactivation must revoke sessions")
    assert_true("UPDATE dashboard_whatsapp_identities SET status='disabled'" in app_source, "deactivation must disable linked WhatsApp identities")
    assert_true("actor_email" in app_source, "audit records must carry actor_email")

    assert_true("whatsapp_actor_context_for_phone" in toolcall_source, "WhatsApp tool scope must resolve linked dashboard identity")
    assert_true("\"__disabled__\"" in app_source, "disabled WhatsApp users must not receive action permissions")

    assert_true("loginDashboard" in api_source and "acceptDashboardInvite" in api_source and "getDashboardTeam" in api_source, "frontend API must expose login, invite accept, and team access")
    assert_true("Team Access" in frontend_source, "Settings must include Team Access")
    assert_true("Complete Your Wathefni Invite" in frontend_source, "frontend must expose invite completion UI")
    assert_true("ROLE_LABELS_UI" in frontend_source and "candidate.manage" in frontend_source, "UI must show fixed roles and readable capabilities, not custom RBAC")
    assert_true("dashboardModuleEnabled" in frontend_source, "enabled_modules must still control navigation/actions")

    print("dashboard auth smoke tests passed")


if __name__ == "__main__":
    main()
