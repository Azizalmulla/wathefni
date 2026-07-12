"""Phase 8C2-R1B durable employee-status workflow checkpoint.

Uses one synthetic company and removes all rows in ``finally``. Never run
against production.
"""

from __future__ import annotations

import concurrent.futures
import sys
import uuid
from datetime import timedelta
from typing import Any, Callable

import app
from psycopg2.extras import Json

COMPANY = "R1BSTATUSTEST"
EMPLOYEE = "r1b-status-employee"
REVIEW = "phase8c2-r1b-smoke"
REASON = "synthetic durable status verification"


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

    def denied(self, label: str, fn: Callable[[], Any], statuses: set[int]) -> None:
        def _run() -> bool:
            try:
                fn()
            except app.HTTPException as exc:
                return exc.status_code in statuses
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
            for table in (
                "employee_status_changes",
                "employee_push_tokens",
                "employee_sessions",
                "employee_app_invites",
                "employees",
                "company_modules",
                "dashboard_user_permission_grants",
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
                INSERT INTO companies (company_code,name,status,metadata,raw_json,created_at,updated_at)
                VALUES (%s,%s,'active',%s,%s,now(),now())
                """,
                (COMPANY, "R1B Status Test", Json({"smoke": REVIEW}), Json({"smoke": REVIEW})),
            )
            cur.execute(
                "INSERT INTO company_modules (company_code,module_key,enabled,source) VALUES (%s,'onboarding',true,%s)",
                (COMPANY, REVIEW),
            )
            users: dict[str, Any] = {}
            for key, email, role in (
                ("owner", "owner@r1b.invalid", "owner"),
                ("viewer", "viewer@r1b.invalid", "viewer"),
            ):
                cur.execute(
                    """
                    INSERT INTO dashboard_users
                      (company_code,email,name,role,status,accepted_at,metadata)
                    VALUES (%s,%s,%s,%s,'active',now(),%s)
                    RETURNING *
                    """,
                    (COMPANY, email, key.title(), role, Json({"smoke": REVIEW})),
                )
                users[key] = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO employees
                  (company_code,employee_key,name,phone,email,employment_status,
                   onboarding_status,profile,raw_json,created_at,updated_at)
                VALUES (%s,%s,'R1B Employee','96550000008201','employee@r1b.invalid',
                        'active','not_started',%s,%s,now(),clock_timestamp())
                """,
                (COMPANY, EMPLOYEE, Json({"smoke": REVIEW}), Json({"smoke": REVIEW})),
            )
        conn.commit()
    users["owner_token"], _ = app.create_dashboard_session(users["owner"])
    users["viewer_token"], _ = app.create_dashboard_session(users["viewer"])
    for permission in sorted(app.EMPLOYEE_PERMISSION_SCOPES):
        result = app.set_dashboard_user_permission_grant(
            COMPANY,
            str(users["owner"]["user_id"]),
            permission,
            active=True,
            actor_user_id=str(users["owner"]["user_id"]),
            reason=REASON,
            review_reference=REVIEW,
        )
        assert result.get("ok"), result
    return users


def context(token: str) -> dict[str, Any]:
    return app.dashboard_context(
        authorization=f"Bearer {token}",
        x_dashboard_token=None,
        x_hr_phone=None,
        x_company_code=COMPANY,
    )


def employee_row() -> dict[str, Any]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM employees WHERE company_code=%s AND employee_key=%s", (COMPANY, EMPLOYEE))
            return dict(cur.fetchone())


def request(status: str, *, key: str | None = None) -> app.DashboardEmployeeStatus:
    row = employee_row()
    return app.DashboardEmployeeStatus(
        status=status,
        reason=REASON,
        idempotency_key=key or str(uuid.uuid4()),
        expected_status=app._canonical_employee_status(row.get("employment_status")),
        expected_updated_at=row["updated_at"],
        approver_user_id="self",
        approval_reference=REVIEW,
        approval_mode="self_approved_internal_canary",
    )


def audit_count() -> int:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM action_results WHERE company_code=%s AND action_type IN ('employee_marked_left','employee_reactivated')",
                (COMPANY,),
            )
            return int(cur.fetchone()["n"])


def ledger_rows() -> list[dict[str, Any]]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM employee_status_changes WHERE company_code=%s ORDER BY committed_at", (COMPANY,))
            return [dict(row) for row in cur.fetchall()]


def reset_active() -> None:
    result = app.set_employee_employment_status(COMPANY, EMPLOYEE, "active")
    assert result.get("status") == "ok", result


def main() -> int:
    app.ensure_schema(force=True)
    checks = Checks()
    users = setup()
    owner_context = context(users["owner_token"])
    viewer_context = context(users["viewer_token"])
    try:
        checks.check(
            "invalid status is rejected by request validation",
            lambda: _model_rejected({"status": "terminated"}),
        )
        checks.check(
            "missing reason/idempotency/version are rejected",
            lambda: _model_rejected({"status": "left"}),
        )
        checks.denied(
            "wrong permission is denied",
            lambda: app.dashboard_posthire_set_employee_status(EMPLOYEE, request("left"), viewer_context),
            {403},
        )
        wrong_company = {**owner_context, "company_code": "WRONGCO", "permission_subject_company": "WRONGCO"}
        checks.denied(
            "wrong company is denied",
            lambda: app.transition_employee_employment_status(wrong_company, EMPLOYEE, request("left")),
            {403, 404},
        )

        before = employee_row()
        before_audits = audit_count()
        real_write_audit = app.write_admin_audit
        app.write_admin_audit = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("synthetic_audit_failure"))
        try:
            try:
                app.transition_employee_employment_status(owner_context, EMPLOYEE, request("left"))
            except RuntimeError:
                pass
        finally:
            app.write_admin_audit = real_write_audit
        after_audit_failure = employee_row()
        checks.check(
            "audit failure rolls back employee mutation",
            lambda: after_audit_failure["employment_status"] == before["employment_status"]
            and after_audit_failure["updated_at"] == before["updated_at"]
            and audit_count() == before_audits,
        )

        missing_before = audit_count()
        checks.denied(
            "employee failure creates no audit result",
            lambda: app.transition_employee_employment_status(owner_context, "missing-employee", request("left")),
            {404},
        )
        checks.check("missing employee left audit count unchanged", lambda: audit_count() == missing_before)

        concurrent_request_a = request("left")
        concurrent_request_b = app.DashboardEmployeeStatus(
            **{
                **(
                    concurrent_request_a.model_dump()
                    if hasattr(concurrent_request_a, "model_dump")
                    else concurrent_request_a.dict()
                ),
                "idempotency_key": str(uuid.uuid4()),
            }
        )

        def run_transition(req: app.DashboardEmployeeStatus) -> tuple[str, Any]:
            try:
                return "ok", app.transition_employee_employment_status(owner_context, EMPLOYEE, req)
            except app.HTTPException as exc:
                return "http", exc.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(run_transition, (concurrent_request_a, concurrent_request_b)))
        checks.check(
            "concurrent conflicting change returns one success and one 409",
            lambda: sorted(kind if kind == "ok" else f"http:{value}" for kind, value in outcomes) == ["http:409", "ok"],
        )
        checks.check("authoritative eligibility updates immediately", lambda: app._employee_app_employee_eligible(employee_row()) is False)

        reset_active()
        concurrent_duplicate = request("left")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            duplicate_outcomes = list(pool.map(run_transition, (concurrent_duplicate, concurrent_duplicate)))
        duplicate_results = [value for kind, value in duplicate_outcomes if kind == "ok"]
        checks.check(
            "concurrent identical retry retrieves one committed result",
            lambda: len(duplicate_results) == 2
            and duplicate_results[0]["result_id"] == duplicate_results[1]["result_id"]
            and len([row for row in ledger_rows() if row["idempotency_key"] == concurrent_duplicate.idempotency_key]) == 1,
        )

        reset_active()
        duplicate_key = str(uuid.uuid4())
        pending_request = request("left", key=duplicate_key)
        real_verify = app._verify_committed_employee_status_change
        app._verify_committed_employee_status_change = lambda company, key, change: app._employee_status_change_response(
            {**change, "verification_status": "pending"}
        )
        try:
            first = app.transition_employee_employment_status(owner_context, EMPLOYEE, pending_request)
        finally:
            app._verify_committed_employee_status_change = real_verify
        second = app.transition_employee_employment_status(owner_context, EMPLOYEE, pending_request)
        matching = [row for row in ledger_rows() if row["idempotency_key"] == duplicate_key]
        checks.check(
            "verification-pending retry returns same durable result without duplicate mutation",
            lambda: first["status"] == "committed_verification_pending"
            and first["result_id"] == second["result_id"]
            and len(matching) == 1,
        )

        reset_active()
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO employee_sessions
                      (company_code,employee_key,phone,token_hash,refresh_hash,status,
                       expires_at,refresh_expires_at)
                    VALUES (%s,%s,'96550000008201',%s,%s,'active',%s,%s)
                    """,
                    (
                        COMPANY,
                        EMPLOYEE,
                        app._app_token_hash("r1b-access"),
                        app._app_token_hash("r1b-refresh"),
                        app.now_utc() + timedelta(days=1),
                        app.now_utc() + timedelta(days=2),
                    ),
                )
            conn.commit()
        left_result = app.transition_employee_employment_status(owner_context, EMPLOYEE, request("left"))
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS n FROM employee_sessions WHERE company_code=%s AND employee_key=%s AND status='active'",
                    (COMPANY, EMPLOYEE),
                )
                active_sessions = int(cur.fetchone()["n"])
        checks.check("left transition cannot leave usable sessions", lambda: left_result["verified"] and active_sessions == 0)

        rows = ledger_rows()
        latest = rows[-1]
        forbidden_columns = {"name", "phone", "email", "before_snapshot", "after_snapshot", "profile", "raw_json"}
        checks.check("ledger duplicates no employee PII or full snapshots", lambda: forbidden_columns.isdisjoint(latest.keys()))
        checks.check("ledger changed fields are limited", lambda: set(latest["changed_fields"]) == {"employment_status", "updated_at"})
        checks.check("durable action result ID is returned and linked", lambda: left_result["result_id"] == str(latest["action_result_id"]))
        checks.check("before/after status and versions are recorded", lambda: bool(latest["previous_status"] and latest["requested_status"] and latest["previous_updated_at"] and latest["resulting_updated_at"]))
        return checks.report()
    finally:
        purge()


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
    if set(overrides) == {"status"} and overrides["status"] == "left":
        payload = {"status": "left"}
    try:
        app.DashboardEmployeeStatus(**payload)
    except Exception:
        return True
    return False


if __name__ == "__main__":
    sys.exit(main())
