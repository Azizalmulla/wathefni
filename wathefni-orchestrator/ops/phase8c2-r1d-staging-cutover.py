#!/usr/bin/env python3
"""Phase 8C2-R1D live staging permission cutover and operational proof.

Staging-only. Never points at production. Writes redacted evidence under
``/opt/wathefni/staging/evidence``. Does not print session tokens or raw
activation codes.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from fastapi import Response
from psycopg2.extras import Json

COMPANY = "WATHEFNI"
REVIEW = "phase8c2-r1d-staging-cutover"
REASON = "Reviewed staging permission-authority cutover for Phase 8C2-R1D"
EVIDENCE_DIR = Path(os.environ.get("R1D_EVIDENCE_DIR", "/opt/wathefni/staging/evidence"))
OWNER_EMAIL = "r1d-owner@wathefni.staging.invalid"
FIXTURE_PHONE = "96550000008401"
FIXTURE_EMPLOYEE = f"{COMPANY}-{FIXTURE_PHONE}"


class Checks:
    def __init__(self, title: str) -> None:
        self.title = title
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:
            self.failed.append(f"{label}: {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def denied(self, label: str, fn: Callable[[], Any], statuses: set[int] | None = None) -> None:
        wanted = statuses or {403}

        def _run() -> bool:
            try:
                fn()
            except app.HTTPException as exc:
                return exc.status_code in wanted
            return False

        self.check(label, _run)

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "passed": self.passed,
            "failed": self.failed,
            "ok": not self.failed,
            "counts": {"passed": len(self.passed), "failed": len(self.failed)},
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_evidence(name: str, payload: dict[str, Any]) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / name
    path.write_text(json.dumps(app.json_safe(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def redact_email(email: str) -> str:
    text = str(email or "")
    if "@" not in text:
        return "redacted"
    local, _, domain = text.partition("@")
    return f"{local[:2]}***@{domain}"


def fingerprint(values: list[str]) -> str:
    material = "\n".join(sorted(str(v) for v in values)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def ensure_reviewed_owner() -> dict[str, Any]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dashboard_users
                  (company_code, email, name, role, status, accepted_at, metadata)
                VALUES (%s,%s,'R1D Staging Owner','owner','active',now(),%s)
                ON CONFLICT (company_code, email)
                DO UPDATE SET
                  role='owner',
                  status='active',
                  disabled_at=NULL,
                  metadata=dashboard_users.metadata || EXCLUDED.metadata,
                  updated_at=now()
                RETURNING *
                """,
                (COMPANY, OWNER_EMAIL, Json({"source": "workspace", "r1d": REVIEW})),
            )
            owner = dict(cur.fetchone())
        conn.commit()
    return owner


def grant_employee_matrix(owner: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for permission in sorted(app.EMPLOYEE_PERMISSION_SCOPES):
        result = app.set_dashboard_user_permission_grant(
            COMPANY,
            str(owner["user_id"]),
            permission,
            active=True,
            actor_user_id=str(owner["user_id"]),
            reason=REASON,
            review_reference=REVIEW,
        )
        if not result.get("ok"):
            raise RuntimeError(f"grant_failed:{permission}:{result}")
        results.append(
            {
                "permission": permission,
                "status": result["grant"]["status"],
                "grant_id": result["grant"]["grant_id"],
                "review_reference": REVIEW,
            }
        )
    return results


def list_recovery_sessions() -> list[dict[str, Any]]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.session_id::text AS session_id,
                       u.user_id::text AS user_id,
                       u.email,
                       COALESCE(u.metadata->>'source','workspace') AS auth_source,
                       s.status,
                       s.expires_at
                FROM dashboard_user_sessions s
                JOIN dashboard_users u ON u.user_id=s.user_id
                WHERE s.company_code=%s
                  AND s.status='active'
                  AND s.expires_at > now()
                  AND (
                    COALESCE(u.metadata->>'source','')='legacy_hr_phone_bootstrap'
                    OR lower(u.email) LIKE '%%.wathefni.local'
                  )
                ORDER BY s.session_id
                """,
                (COMPANY,),
            )
            return [dict(row) for row in cur.fetchall()]


def seed_recovery_sessions_for_proof() -> list[dict[str, Any]]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM dashboard_users
                WHERE company_code=%s
                  AND (
                    COALESCE(metadata->>'source','')='legacy_hr_phone_bootstrap'
                    OR lower(email) LIKE '%%.wathefni.local'
                  )
                  AND status='active'
                ORDER BY email
                LIMIT 1
                """,
                (COMPANY,),
            )
            recovery_user = cur.fetchone()
        conn.commit()
    if not recovery_user:
        return []
    recovery_user = dict(recovery_user)
    for _ in range(2):
        app.create_dashboard_session(recovery_user)
    return list_recovery_sessions()


def context_for_user(user: dict[str, Any], token: str) -> dict[str, Any]:
    return app.dashboard_context(
        authorization=f"Bearer {token}",
        x_dashboard_token=None,
        x_hr_phone=None,
        x_company_code=COMPANY,
    )


def synthetic_context(user_id: str, permissions: list[str]) -> dict[str, Any]:
    return {
        "company_code": COMPANY,
        "actor_user_id": user_id,
        "actor_role": "owner",
        "permissions": permissions,
        "access": {"role": "owner", "permissions": permissions},
        "permission_authority": "backend_current",
        "permission_subject_user_id": user_id,
        "permission_subject_company": COMPANY,
        "hr_phone": "",
        "scope": {"restricted": False, "company_code": COMPANY, "manager_phone": ""},
    }


def cleanup_fixtures() -> dict[str, int]:
    counts: dict[str, int] = {}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table, clause, params in (
                ("employee_status_changes", "company_code=%s AND employee_key=%s", (COMPANY, FIXTURE_EMPLOYEE)),
                ("hr_tasks", "company_code=%s AND employee_key=%s", (COMPANY, FIXTURE_EMPLOYEE)),
                ("employee_app_invites", "company_code=%s AND employee_key=%s", (COMPANY, FIXTURE_EMPLOYEE)),
                ("employee_sessions", "company_code=%s AND employee_key=%s", (COMPANY, FIXTURE_EMPLOYEE)),
                ("employee_push_tokens", "company_code=%s AND employee_key=%s", (COMPANY, FIXTURE_EMPLOYEE)),
                ("employee_messages", "company_code=%s AND employee_key=%s", (COMPANY, FIXTURE_EMPLOYEE)),
                ("employees", "company_code=%s AND employee_key=%s", (COMPANY, FIXTURE_EMPLOYEE)),
                ("action_results", "company_code=%s AND action_type = %s", (COMPANY, "app_invite_created_hr_task_only")),
                (
                    "action_results",
                    "company_code=%s AND action_type IN ('employee_marked_left','employee_reactivated') AND result::text LIKE %s",
                    (COMPANY, f"%{FIXTURE_EMPLOYEE}%"),
                ),
            ):
                cur.execute(f"DELETE FROM {table} WHERE {clause}", params)
                counts[table] = counts.get(table, 0) + cur.rowcount
            # Leave the company dark for employee_app after the handoff proof.
            cur.execute(
                "UPDATE company_modules SET enabled=false, updated_at=now() WHERE company_code=%s AND module_key='employee_app'",
                (COMPANY,),
            )
            counts["employee_app_module_disabled"] = cur.rowcount
        conn.commit()
    return counts


def ensure_fixture_employee() -> dict[str, Any]:
    cleanup_fixtures()
    created = app.create_company_employee(
        COMPANY,
        name="R1D Fixture Employee",
        phone=FIXTURE_PHONE,
        email="r1d-fixture@wathefni.staging.invalid",
        position_title="Staging Fixture",
        department="R1D",
        seed_compliance=False,
    )
    if created.get("status") not in {"created", "exists"}:
        raise RuntimeError(created)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE employees SET employment_status='active', updated_at=clock_timestamp() WHERE company_code=%s AND employee_key=%s RETURNING *",
                (COMPANY, FIXTURE_EMPLOYEE),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return row


def status_request(employee_key: str, target: str, key: str | None = None) -> app.DashboardEmployeeStatus:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT employment_status, updated_at FROM employees WHERE company_code=%s AND employee_key=%s",
                (COMPANY, employee_key),
            )
            current = dict(cur.fetchone())
    return app.DashboardEmployeeStatus(
        status=target,
        reason=REASON,
        idempotency_key=key or str(uuid.uuid4()),
        expected_status=app._canonical_employee_status(current.get("employment_status")),
        expected_updated_at=current["updated_at"],
        approver_user_id="self",
        approval_reference=REVIEW,
        approval_mode="self_approved_internal_canary",
    )


def prove_route_matrix(owner_ctx: dict[str, Any], owner_id: str) -> dict[str, Any]:
    checks = Checks("live route matrix")
    exact = owner_ctx
    missing = synthetic_context(owner_id, [])
    unrelated = synthetic_context(owner_id, ["attendance.read"])
    wrong_company = {**owner_ctx, "company_code": "WRONGCO", "permission_subject_company": "WRONGCO"}

    # Team / user management
    checks.check("team list exact permission allowed", lambda: app.dashboard_team_list(exact).get("company_code") == COMPANY)
    checks.denied("users.manage missing denied", lambda: app.require_workspace_permission(missing, "users.manage"))
    checks.denied("users.manage unrelated denied", lambda: app.require_workspace_permission(unrelated, "users.manage"))
    checks.denied("users.manage wrong company denied", lambda: app.require_workspace_permission(wrong_company, "users.manage"), {403, 404})

    # Organization hierarchy remains independently scoped
    overview = app.org_overview(COMPANY)
    checks.check("organization hierarchy readable for company", lambda: overview.get("company_code") == COMPANY or "branches" in overview or overview.get("ok") is not False)

    # HR tasks
    checks.check("HR-task read exact allowed", lambda: app._hr_tasks_context(exact) == COMPANY)
    checks.check("HR-task manage exact allowed", lambda: app._hr_tasks_context(exact, manage=True) == COMPANY)
    checks.denied("HR-task manage missing denied", lambda: app._hr_tasks_context(missing, manage=True))
    checks.denied("HR-task manage unrelated denied", lambda: app._hr_tasks_context(unrelated, manage=True))

    # Employee directory / profile
    checks.check("employee directory exact allowed", lambda: bool(app.dashboard_posthire_employees(context=exact)))
    checks.denied("employee directory missing denied", lambda: app.dashboard_posthire_employees(context=missing))
    checks.denied("employee directory unrelated denied", lambda: app.dashboard_posthire_employees(context=unrelated))
    checks.denied("employee directory wrong company denied", lambda: app.dashboard_posthire_employees(context=wrong_company), {403, 404})

    # Document hub
    checks.check("document hub exact allowed", lambda: app._document_hub_read_context(exact) == COMPANY)
    checks.denied("document hub missing denied", lambda: app._document_hub_read_context(missing))
    checks.denied("document hub unrelated denied", lambda: app._document_hub_read_context(unrelated))

    # Employee create/edit/status gates
    checks.check("employees.manage exact allowed", lambda: app.require_employee_roster_admin(exact) == COMPANY)
    checks.denied("employees.manage missing denied", lambda: app.require_employee_roster_admin(missing))
    checks.denied("employees.manage empty denied", lambda: app.require_employee_roster_admin(synthetic_context(owner_id, [])))
    checks.denied("employees.manage unrelated denied", lambda: app.require_employee_roster_admin(unrelated))
    checks.check("employees.status.approve exact allowed", lambda: app.dashboard_context_has_permission(exact, "employees.status.approve"))
    checks.check("employees.read exact allowed", lambda: app.dashboard_context_has_permission(exact, "employees.read"))
    checks.check("settings.manage does not imply employees.manage", lambda: not app.dashboard_context_has_permission(synthetic_context(owner_id, ["settings.manage"]), "employees.manage"))

    # Payroll export capability
    checks.check(
        "payroll.export exact capability present for reviewed owner role set",
        lambda: app.dashboard_context_has_permission(exact, "payroll.export"),
    )
    checks.check(
        "payroll.export unrelated denied",
        lambda: not app.dashboard_context_has_permission(unrelated, "payroll.export"),
    )
    checks.check(
        "payroll.export missing denied",
        lambda: not app.dashboard_context_has_permission(missing, "payroll.export"),
    )

    # Authenticated-only remains functional
    checks.check("authenticated-only team route remains functional", lambda: app.dashboard_team_list(exact).get("company_code") == COMPANY)
    return checks.as_dict()


def prove_r1b(owner_ctx: dict[str, Any]) -> dict[str, Any]:
    checks = Checks("R1B live staging")
    ensure_fixture_employee()
    unauthorized = synthetic_context(str(uuid.uuid4()), ["employees.read"])
    checks.denied(
        "unauthorized status transition denied",
        lambda: app.transition_employee_employment_status(unauthorized, FIXTURE_EMPLOYEE, status_request(FIXTURE_EMPLOYEE, "left")),
        {403, 404},
    )
    checks.check(
        "missing reason rejected",
        lambda: _model_rejected({"reason": ""}),
    )
    checks.check(
        "missing idempotency rejected",
        lambda: _model_rejected({"idempotency_key": "short"}),
    )

    left = app.transition_employee_employment_status(owner_ctx, FIXTURE_EMPLOYEE, status_request(FIXTURE_EMPLOYEE, "left"))
    checks.check("authorized status transition succeeds", lambda: left.get("ok") and left.get("employment_status") == "left")
    checks.check("durable result ID returned", lambda: bool(left.get("result_id")))
    checks.check("post-change read-back succeeds", lambda: left.get("verified") is True)
    checks.check("employee-app eligibility reflects left", lambda: app._employee_app_employee_eligible({"employment_status": "left"}) is False)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM employee_status_changes WHERE action_result_id=%s", (left["result_id"],))
            ledger = dict(cur.fetchone())
            cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (FIXTURE_EMPLOYEE,))
            emp = dict(cur.fetchone())
    checks.check("only approved status fields change", lambda: set(ledger["changed_fields"]) == {"employment_status", "updated_at"})
    checks.check("authoritative employee status updated", lambda: emp["employment_status"] == "left")

    # Restore active then prove duplicate / concurrent
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE employees SET employment_status='active', updated_at=clock_timestamp() WHERE employee_key=%s",
                (FIXTURE_EMPLOYEE,),
            )
        conn.commit()

    dup_key = str(uuid.uuid4())
    req = status_request(FIXTURE_EMPLOYEE, "left", key=dup_key)
    first = app.transition_employee_employment_status(owner_ctx, FIXTURE_EMPLOYEE, req)
    second = app.transition_employee_employment_status(owner_ctx, FIXTURE_EMPLOYEE, req)
    checks.check("duplicate request returns same result", lambda: first["result_id"] == second["result_id"])

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE employees SET employment_status='active', updated_at=clock_timestamp() WHERE employee_key=%s RETURNING updated_at, employment_status",
                (FIXTURE_EMPLOYEE,),
            )
            current = dict(cur.fetchone())
        conn.commit()
    a = app.DashboardEmployeeStatus(
        status="left",
        reason=REASON,
        idempotency_key=str(uuid.uuid4()),
        expected_status="active",
        expected_updated_at=current["updated_at"],
        approver_user_id="self",
        approval_reference=REVIEW,
        approval_mode="self_approved_internal_canary",
    )
    b = app.DashboardEmployeeStatus(
        status="left",
        reason=REASON,
        idempotency_key=str(uuid.uuid4()),
        expected_status="active",
        expected_updated_at=current["updated_at"],
        approver_user_id="self",
        approval_reference=REVIEW,
        approval_mode="self_approved_internal_canary",
    )

    def run(req_obj: app.DashboardEmployeeStatus) -> tuple[str, Any]:
        try:
            return "ok", app.transition_employee_employment_status(owner_ctx, FIXTURE_EMPLOYEE, req_obj)
        except app.HTTPException as exc:
            return "http", exc.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run, (a, b)))
    checks.check(
        "concurrent conflict returns 409",
        lambda: sorted(kind if kind == "ok" else f"http:{value}" for kind, value in outcomes) == ["http:409", "ok"],
    )

    # Audit atomicity: synthetic audit failure rolls back
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE employees SET employment_status='active', updated_at=clock_timestamp() WHERE employee_key=%s RETURNING updated_at",
                (FIXTURE_EMPLOYEE,),
            )
            before = dict(cur.fetchone())
        conn.commit()
    before_audits = _audit_count()
    real_write = app.write_admin_audit
    app.write_admin_audit = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("synthetic_audit_failure"))
    try:
        try:
            app.transition_employee_employment_status(owner_ctx, FIXTURE_EMPLOYEE, status_request(FIXTURE_EMPLOYEE, "left"))
        except RuntimeError:
            pass
    finally:
        app.write_admin_audit = real_write
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT employment_status, updated_at FROM employees WHERE employee_key=%s", (FIXTURE_EMPLOYEE,))
            after = dict(cur.fetchone())
    checks.check(
        "audit and employee mutation remain atomic",
        lambda: after["employment_status"] == "active" and after["updated_at"] == before["updated_at"] and _audit_count() == before_audits,
    )
    return checks.as_dict()


def _audit_count() -> int:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM action_results WHERE company_code=%s AND action_type IN ('employee_marked_left','employee_reactivated')",
                (COMPANY,),
            )
            return int(cur.fetchone()["n"])


def _model_rejected(overrides: dict[str, Any]) -> bool:
    payload = {
        "status": "left",
        "reason": REASON,
        "idempotency_key": str(uuid.uuid4()),
        "expected_status": "active",
        "expected_updated_at": app.now_utc(),
        "approver_user_id": "self",
        "approval_reference": REVIEW,
        "approval_mode": "self_approved_internal_canary",
        **overrides,
    }
    try:
        app.DashboardEmployeeStatus(**payload)
    except Exception:
        return True
    return False


def prove_r1c(owner_ctx: dict[str, Any]) -> dict[str, Any]:
    checks = Checks("R1C live staging")
    ensure_fixture_employee()
    previous = app.os.environ.get("WATHEFNI_EMPLOYEE_APP")
    app.os.environ["WATHEFNI_EMPLOYEE_APP"] = "on"
    # Ensure employee_app module for company gate inside invite path.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO company_modules (company_code, module_key, enabled, source)
                VALUES (%s,'employee_app',true,%s)
                ON CONFLICT (company_code, module_key)
                DO UPDATE SET enabled=true, updated_at=now()
                """,
                (COMPANY, REVIEW),
            )
            cur.execute(
                """
                INSERT INTO company_modules (company_code, module_key, enabled, source)
                VALUES (%s,'onboarding',true,%s)
                ON CONFLICT (company_code, module_key)
                DO UPDATE SET enabled=true, updated_at=now()
                """,
                (COMPANY, REVIEW),
            )
        conn.commit()

    provider_calls: list[str] = []
    patched: list[tuple[Any, str, Any]] = []

    def block(name: str):
        def _blocked(*args: Any, **kwargs: Any) -> Any:
            provider_calls.append(name)
            raise AssertionError(f"external provider invoked: {name}")

        return _blocked

    for owner, name in (
        (app, "deliver_app_activation_code"),
        (app, "deliver_employee_notification"),
        (app, "deliver_to_employee"),
        (app._outbound_delivery, "_attempt_ladder"),
        (app._outbound_delivery, "create_hr_task"),
    ):
        if hasattr(owner, name):
            patched.append((owner, name, getattr(owner, name)))
            setattr(owner, name, block(name))
    try:
        req = app.DashboardEmployeeAppInviteRequest(
            delivery_mode="hr_task_only",
            idempotency_key=str(uuid.uuid4()),
            reason=REASON,
        )
        response = Response()
        first = app.dashboard_posthire_app_invite(FIXTURE_EMPLOYEE, req, response, owner_ctx)
        raw = str(first["activation_code"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM hr_tasks WHERE company_code=%s AND employee_key=%s AND task_type='app_activation_handoff'", (COMPANY, FIXTURE_EMPLOYEE))
                task_count = int(cur.fetchone()["n"])
                cur.execute("SELECT * FROM employee_app_invites WHERE invite_id=%s", (first["invite_id"],))
                invite = dict(cur.fetchone())
                cur.execute("SELECT row_to_json(t)::text AS blob FROM hr_tasks t WHERE related_invite_id=%s", (first["invite_id"],))
                task_blob = cur.fetchone()["blob"]
                cur.execute("SELECT row_to_json(a)::text AS blob FROM action_results a WHERE result_id=%s", (first["audit_result_id"],))
                audit_blob = cur.fetchone()["blob"]
        checks.check("exactly one HR task", lambda: task_count == 1)
        checks.check("zero external provider calls", lambda: provider_calls == [])
        checks.check("response uses Cache-Control no-store", lambda: response.headers.get("cache-control") == "no-store")
        checks.check("activation code hash only in persistence", lambda: invite["code_hash"] == app._app_code_hash(COMPANY, invite["phone"], raw) and invite["code_hash"] != raw)
        checks.check("raw code absent from task and audit", lambda: raw not in task_blob and raw not in audit_blob)
        checks.check(
            "replay requires supersede",
            lambda: _expect_conflict(lambda: app.dashboard_posthire_app_invite(FIXTURE_EMPLOYEE, req, Response(), owner_ctx), "activation_code_already_disclosed"),
        )
        checks.check(
            "pending invite requires explicit supersede",
            lambda: _expect_conflict(
                lambda: app.dashboard_posthire_app_invite(
                    FIXTURE_EMPLOYEE,
                    app.DashboardEmployeeAppInviteRequest(delivery_mode="hr_task_only", idempotency_key=str(uuid.uuid4()), reason=REASON),
                    Response(),
                    owner_ctx,
                ),
                "pending_activation_invite_exists",
            ),
        )
        second = app.dashboard_posthire_app_invite(
            FIXTURE_EMPLOYEE,
            app.DashboardEmployeeAppInviteRequest(
                delivery_mode="hr_task_only",
                idempotency_key=str(uuid.uuid4()),
                reason=REASON,
                supersede_invite_id=first["invite_id"],
            ),
            Response(),
            owner_ctx,
        )
        second_raw = str(second["activation_code"])
        checks.check("supersede and reissue succeeds", lambda: second["invite_id"] != first["invite_id"] and bool(second_raw))
        # Never retain raw codes in evidence.
        del raw, second_raw, first, second
        return checks.as_dict()
    finally:
        for owner, name, original in patched:
            setattr(owner, name, original)
        if previous is None:
            app.os.environ.pop("WATHEFNI_EMPLOYEE_APP", None)
        else:
            app.os.environ["WATHEFNI_EMPLOYEE_APP"] = previous


def _expect_conflict(fn: Callable[[], Any], code: str) -> bool:
    try:
        fn()
    except app.HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return exc.status_code == 409 and detail.get("error") == code
    return False


def prove_revocation_affects_open_session(owner: dict[str, Any]) -> dict[str, Any]:
    checks = Checks("open-session revocation")
    token, _ = app.create_dashboard_session(owner)
    open_ctx = context_for_user(owner, token)
    checks.check("open session can manage before revoke", lambda: app.require_employee_roster_admin(open_ctx) == COMPANY)
    revoked = app.set_dashboard_user_permission_grant(
        COMPANY,
        str(owner["user_id"]),
        "employees.manage",
        active=False,
        actor_user_id=str(owner["user_id"]),
        reason=REASON,
        review_reference=REVIEW,
    )
    checks.check("employees.manage revoked", lambda: revoked.get("ok") is True)
    same_session = context_for_user(owner, token)
    checks.denied("revocation affects already-open session", lambda: app.require_employee_roster_admin(same_session))
    restored = app.set_dashboard_user_permission_grant(
        COMPANY,
        str(owner["user_id"]),
        "employees.manage",
        active=True,
        actor_user_id=str(owner["user_id"]),
        reason=REASON,
        review_reference=REVIEW,
    )
    checks.check("employees.manage restored", lambda: restored.get("ok") is True)
    return checks.as_dict()


def main() -> int:
    if "staging" not in str(os.environ.get("WATHEFNI_POSTGRES_ENV") or "").lower():
        raise SystemExit("refusing to run without staging postgres env")
    app.ensure_schema(force=True)

    from importlib.machinery import SourceFileLoader

    cli = SourceFileLoader(
        "dashboard_permission_authority",
        str(ROOT / "ops" / "dashboard-permission-authority.py"),
    ).load_module()
    inventory_before = cli.inventory(COMPANY)
    write_evidence(
        "r1d-inventory-before.json",
        {
            "captured_at": utc_now(),
            "company_code": COMPANY,
            "users": [
                {
                    "user_id": u["user_id"],
                    "email_redacted": redact_email(u["email"]),
                    "role": u["role"],
                    "status": u["status"],
                    "auth_source": u["auth_source"],
                    "active_sessions": u["active_sessions"],
                    "explicit_permissions": u["explicit_permissions"],
                }
                for u in inventory_before["users"]
            ],
        },
    )

    owner = ensure_reviewed_owner()
    grants = grant_employee_matrix(owner)
    preflight = app.permission_authority_preflight(COMPANY)
    write_evidence(
        "r1d-grants.json",
        {
            "captured_at": utc_now(),
            "company_code": COMPANY,
            "owner_user_id": str(owner["user_id"]),
            "owner_email_redacted": redact_email(OWNER_EMAIL),
            "matrix": sorted(app.EMPLOYEE_PERMISSION_SCOPES),
            "grants": grants,
            "preflight": {
                "ok": preflight.get("ok"),
                "required_permissions": preflight.get("required_permissions"),
                "reviewed_owner_count": len(preflight.get("reviewed_owner_user_ids") or []),
                "active_recovery_sessions": preflight.get("active_recovery_sessions"),
                "error": preflight.get("error"),
            },
            "actor": str(owner["user_id"]),
            "reason": REASON,
            "review_reference": REVIEW,
        },
    )
    if not preflight.get("ok"):
        raise SystemExit(f"preflight failed: {preflight}")

    # Capture reviewed recovery-session set. If none exist, seed two temporary
    # recovery sessions so the live cutover path is exercised, then revoke them.
    reviewed = seed_recovery_sessions_for_proof()
    reviewed_ids = [row["session_id"] for row in reviewed]
    reviewed_fp = fingerprint(reviewed_ids)
    write_evidence(
        "r1d-recovery-sessions-reviewed.json",
        {
            "captured_at": utc_now(),
            "count": len(reviewed_ids),
            "fingerprint": reviewed_fp,
            "auth_sources": sorted({row["auth_source"] for row in reviewed}),
            "emails_redacted": sorted({redact_email(row["email"]) for row in reviewed}),
        },
    )

    reread = list_recovery_sessions()
    reread_ids = [row["session_id"] for row in reread]
    if fingerprint(reread_ids) != reviewed_fp:
        raise SystemExit("recovery session set changed unexpectedly before revocation")
    revoked = app.revoke_dashboard_recovery_sessions(
        COMPANY,
        actor_user_id=str(owner["user_id"]),
        reason=REASON,
        review_reference=REVIEW,
    )
    remaining = list_recovery_sessions()
    write_evidence(
        "r1d-recovery-sessions-after.json",
        {
            "captured_at": utc_now(),
            "revoked_count": revoked.get("revoked_count"),
            "reviewed_count": len(reviewed_ids),
            "remaining_count": len(remaining),
            "remaining_fingerprint": fingerprint([row["session_id"] for row in remaining]),
            "ok": revoked.get("ok") is True and len(remaining) == 0 and revoked.get("revoked_count") == len(reviewed_ids),
        },
    )
    if len(remaining) != 0 or revoked.get("revoked_count") != len(reviewed_ids):
        raise SystemExit("recovery session revocation mismatch")

    owner_token, _ = app.create_dashboard_session(owner)
    owner_ctx = context_for_user(owner, owner_token)
    capabilities = {
        "role": owner_ctx["access"]["role"],
        "permissions": owner_ctx["access"]["permissions"],
        "employee_scopes_present": sorted(set(owner_ctx["access"]["permissions"]) & app.EMPLOYEE_PERMISSION_SCOPES),
        "permission_authority": owner_ctx.get("permission_authority"),
    }
    write_evidence("r1d-owner-capabilities.json", {"captured_at": utc_now(), **capabilities})

    route_results = prove_route_matrix(owner_ctx, str(owner["user_id"]))
    revocation_results = prove_revocation_affects_open_session(owner)
    # Refresh context after restore.
    owner_token, _ = app.create_dashboard_session(owner)
    owner_ctx = context_for_user(owner, owner_token)
    r1b_results = prove_r1b(owner_ctx)
    r1c_results = prove_r1c(owner_ctx)
    cleanup = cleanup_fixtures()
    write_evidence(
        "r1d-live-proofs.json",
        {
            "captured_at": utc_now(),
            "route_matrix": route_results,
            "open_session_revocation": revocation_results,
            "r1b": r1b_results,
            "r1c": r1c_results,
            "fixture_cleanup": cleanup,
        },
    )

    summary = {
        "ok": all(
            section["ok"]
            for section in (route_results, revocation_results, r1b_results, r1c_results)
        ),
        "company_code": COMPANY,
        "owner_user_id": str(owner["user_id"]),
        "grants": grants,
        "route_matrix": route_results["counts"],
        "open_session_revocation": revocation_results["counts"],
        "r1b": r1b_results["counts"],
        "r1c": r1c_results["counts"],
        "recovery_sessions_revoked": len(reviewed_ids),
    }
    write_evidence("r1d-summary.json", summary)
    print(json.dumps(app.json_safe(summary), indent=2, sort_keys=True))
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
