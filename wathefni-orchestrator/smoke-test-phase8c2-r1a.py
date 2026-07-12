"""Phase 8C2-R1A fail-closed permission-authority checkpoint.

Writes only a synthetic company and removes it in ``finally``. Never run against
production.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
from psycopg2.extras import Json

COMPANY = "R1APERMTEST"
REVIEW = "phase8c2-r1a-smoke"
REASON = "synthetic permission-authority verification"


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:
            self.failed.append(f"{label}: {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def denied(self, label: str, fn: Callable[[], Any], status: int = 403) -> None:
        def _run() -> bool:
            try:
                fn()
            except app.HTTPException as exc:
                return exc.status_code == status
            return False

        self.check(label, _run)

    def report(self) -> int:
        for label in self.passed:
            print(f"  PASS  {label}")
        for label in self.failed:
            print(f"  FAIL  {label}")
        print(f"\n{len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def purge() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM manager_scope_members WHERE scope_id IN (SELECT scope_id FROM manager_scopes WHERE company_code=%s)", (COMPANY,))
            for table in (
                "manager_scopes",
                "employee_org_assignments",
                "company_teams",
                "company_branches",
                "employees",
                "company_modules",
                "dashboard_user_permission_grants",
                "dashboard_user_invites",
                "dashboard_whatsapp_identities",
                "dashboard_user_sessions",
                "dashboard_users",
                "action_results",
            ):
                cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
        conn.commit()


def setup() -> dict[str, Any]:
    purge()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO companies (company_code, name, status, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'active',%s,%s,now(),now())
                """,
                (COMPANY, "R1A Permission Test", Json({"smoke": REVIEW}), Json({"smoke": REVIEW})),
            )
            cur.execute(
                "INSERT INTO company_modules (company_code,module_key,enabled,source) VALUES (%s,'onboarding',true,%s)",
                (COMPANY, REVIEW),
            )
            users: dict[str, dict[str, Any]] = {}
            for key, email, role, phone, metadata in (
                ("owner", "owner@r1a.invalid", "owner", "96550000008101", {}),
                ("viewer", "viewer@r1a.invalid", "viewer", "96550000008102", {}),
                ("manager", "manager@r1a.invalid", "manager", "96550000008103", {}),
                ("recovery", "recovery@r1apermtest.wathefni.local", "owner", "96550000008104", {"source": "legacy_hr_phone_bootstrap"}),
            ):
                cur.execute(
                    """
                    INSERT INTO dashboard_users
                      (company_code,email,name,phone,role,status,accepted_at,metadata)
                    VALUES (%s,%s,%s,%s,%s,'active',now(),%s)
                    RETURNING *
                    """,
                    (COMPANY, email, key.title(), phone, role, Json(metadata)),
                )
                users[key] = dict(cur.fetchone())
        conn.commit()

    users["owner_token"], _ = app.create_dashboard_session(users["owner"])
    users["viewer_token"], _ = app.create_dashboard_session(users["viewer"])
    users["manager_token"], _ = app.create_dashboard_session(users["manager"])
    users["recovery_token_1"], _ = app.create_dashboard_session(users["recovery"])
    users["recovery_token_2"], _ = app.create_dashboard_session(users["recovery"])
    return users


def context(token: str, company: str = COMPANY) -> dict[str, Any]:
    return app.dashboard_context(
        authorization=f"Bearer {token}",
        x_dashboard_token=None,
        x_hr_phone=None,
        x_company_code=company,
    )


def grant(users: dict[str, Any], target: str, permission: str, active: bool = True) -> dict[str, Any]:
    return app.set_dashboard_user_permission_grant(
        COMPANY,
        str(users[target]["user_id"]),
        permission,
        active=active,
        actor_user_id=str(users["owner"]["user_id"]),
        reason=REASON,
        review_reference=REVIEW,
    )


def setup_manager_scope(users: dict[str, Any]) -> tuple[str, str]:
    a = app.create_company_employee(COMPANY, name="Scoped A", phone="96550000008111")
    b = app.create_company_employee(COMPANY, name="Scoped B", phone="96550000008112")
    branch = app.org_key(COMPANY, "branch", "HQ")
    team = app.org_key(COMPANY, "team", "Scoped")
    assert app.upsert_org_branch(COMPANY, name="HQ", branch_key=branch)["ok"]
    assert app.upsert_org_team(COMPANY, name="Scoped", branch_key=branch, team_key=team)["ok"]
    assert app.set_employee_org_assignment(COMPANY, employee_key=a["employee_key"], team_key=team)["ok"]
    assert app.upsert_manager_scope(
        COMPANY,
        manager_phone=users["manager"]["phone"],
        scope_type="team",
        team_key=team,
    )["ok"]
    return str(a["employee_key"]), str(b["employee_key"])


def main() -> int:
    app.ensure_schema(force=True)
    checks = Checks()
    users = setup()
    previous_workspace_boot = app.os.environ.get("WATHEFNI_WORKSPACE_BOOT")
    app.os.environ["WATHEFNI_WORKSPACE_BOOT"] = "on"
    try:
        owner_id = str(users["owner"]["user_id"])

        checks.check(
            "supplied owner role/permission claims are not authoritative",
            lambda: not app.dashboard_context_has_permission(
                {"company_code": COMPANY, "actor_user_id": owner_id, "actor_role": "owner", "permissions": ["employees.manage"]},
                "employees.manage",
            ),
        )
        base = {
            "company_code": COMPANY,
            "actor_user_id": owner_id,
            "permission_authority": "backend_current",
            "permission_subject_user_id": owner_id,
            "permission_subject_company": COMPANY,
        }
        checks.check("missing permissions deny", lambda: not app.dashboard_context_has_permission(base, "employees.manage"))
        checks.check("empty permissions deny", lambda: not app.dashboard_context_has_permission({**base, "permissions": []}, "employees.manage"))
        checks.check(
            "unrelated permissions deny",
            lambda: not app.dashboard_context_has_permission({**base, "permissions": ["employees.read"]}, "employees.manage"),
        )

        for permission in sorted(app.EMPLOYEE_PERMISSION_SCOPES):
            checks.check(f"reviewed {permission} grant succeeds", lambda permission=permission: grant(users, "owner", permission).get("ok"))
        owner_context = context(users["owner_token"])
        checks.check(
            "exact current backend grant allows",
            lambda: app.dashboard_context_has_permission(owner_context, "employees.manage"),
        )
        checks.check(
            "users.manage call sites retain explicit authority",
            lambda: app.require_workspace_permission(owner_context, "users.manage")["company_code"] == COMPANY,
        )
        checks.check(
            "HR-task read/manage call sites retain explicit authority",
            lambda: app._hr_tasks_context(owner_context) == COMPANY and app._hr_tasks_context(owner_context, manage=True) == COMPANY,
        )
        checks.check(
            "employee profile requires employees.read plus module read",
            lambda: app.employee_profile_accessible_modules(owner_context, COMPANY) == ["onboarding"],
        )
        checks.check(
            "document hub retains module read authority",
            lambda: app._document_hub_read_context(owner_context) == COMPANY,
        )
        checks.check(
            "payroll export capability uses exact backend permission",
            lambda: app.dashboard_context_has_permission(owner_context, "payroll.export"),
        )
        checks.check(
            "status transition authority is separate from roster management",
            lambda: app.dashboard_context_has_permission(owner_context, "employees.status.approve"),
        )
        checks.check(
            "owner can administer employee reads and writes",
            lambda: app.require_employee_roster_admin(owner_context) == COMPANY
            and bool(app.dashboard_posthire_employees(context=owner_context)),
        )
        settings_only = {
            **base,
            "permissions": ["settings.manage"],
        }
        checks.denied(
            "settings.manage no longer grants employee management",
            lambda: app.require_employee_roster_admin(settings_only),
        )

        viewer_context = context(users["viewer_token"])
        checks.denied("revoked viewer has no employee-management access", lambda: app.require_employee_roster_admin(viewer_context))
        checks.denied("viewer cannot read employee directory without employees.read", lambda: app.dashboard_posthire_employees(context=viewer_context))
        checks.check("authenticated-only team route remains functional", lambda: app.dashboard_team_list(viewer_context).get("company_code") == COMPANY)
        checks.denied(
            "wrong-company session context denied",
            lambda: context(users["owner_token"], "NOT" + COMPANY),
        )

        checks.check("manager employees.read grant succeeds", lambda: grant(users, "manager", "employees.read").get("ok"))
        scoped_key, other_key = setup_manager_scope(users)
        manager_context = context(users["manager_token"])
        directory = app.dashboard_posthire_employees(context=manager_context)
        visible = {str(row.get("employee_key")) for row in directory.get("employees") or []}
        checks.check("manager scope retained on employee directory", lambda: scoped_key in visible and other_key not in visible)

        checks.check("revoking current grant succeeds", lambda: grant(users, "owner", "employees.manage", active=False).get("ok"))
        same_session_context = context(users["owner_token"])
        checks.denied(
            "revocation affects an already-open session",
            lambda: app.require_employee_roster_admin(same_session_context),
        )
        checks.check("regrant restores reviewed owner access", lambda: grant(users, "owner", "employees.manage").get("ok"))

        preflight = app.permission_authority_preflight(COMPANY)
        checks.check("cutover preflight finds reviewed normal owner matrix", lambda: preflight.get("ok") is True)
        checks.check("preflight detects active recovery sessions", lambda: int(preflight.get("active_recovery_sessions") or 0) == 2)
        revoked = app.revoke_dashboard_recovery_sessions(
            COMPANY,
            actor_user_id=owner_id,
            reason=REASON,
            review_reference=REVIEW,
        )
        checks.check("cutover revokes all active recovery sessions", lambda: revoked.get("revoked_count") == 2)
        checks.denied("revoked recovery session requires reauthentication", lambda: context(users["recovery_token_1"]), status=401)
        final_preflight = app.permission_authority_preflight(COMPANY)
        checks.check("no active recovery session remains", lambda: final_preflight.get("active_recovery_sessions") == 0)
        checks.check(
            "no role fallback remains",
            lambda: app.context_permissions({"company_code": COMPANY, "actor_user_id": owner_id}, "owner") == set(),
        )
        return checks.report()
    finally:
        if previous_workspace_boot is None:
            app.os.environ.pop("WATHEFNI_WORKSPACE_BOOT", None)
        else:
            app.os.environ["WATHEFNI_WORKSPACE_BOOT"] = previous_workspace_boot
        purge()


if __name__ == "__main__":
    raise SystemExit(main())
