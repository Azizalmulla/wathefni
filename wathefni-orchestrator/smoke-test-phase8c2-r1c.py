"""Phase 8C2-R1C secure ``hr_task_only`` activation checkpoint.

Uses one synthetic company and removes every row in ``finally``. The verifier
never prints activation material. Never run against production.
"""

from __future__ import annotations

import logging
import sys
import uuid
from typing import Any, Callable

import app
from fastapi import Response
from psycopg2.extras import Json

COMPANY = "R1CHANDOFFTEST"
EMPLOYEE = "r1c-handoff-employee"
REVIEW = "phase8c2-r1c-smoke"
REASON = "synthetic secure handoff verification"


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

    def report(self) -> int:
        for label in self.passed:
            print(f"  PASS  {label}")
        for label in self.failed:
            print(f"  FAIL  {label}")
        print(f"\n{len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(self.format(record))


def purge() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in (
                "employee_status_changes",
                "hr_tasks",
                "employee_messages",
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
                (COMPANY, "R1C Handoff Test", Json({"smoke": REVIEW}), Json({"smoke": REVIEW})),
            )
            for module in ("onboarding", "employee_app"):
                cur.execute(
                    "INSERT INTO company_modules (company_code,module_key,enabled,source) VALUES (%s,%s,true,%s)",
                    (COMPANY, module, REVIEW),
                )
            cur.execute(
                """
                INSERT INTO dashboard_users
                  (company_code,email,name,phone,role,status,accepted_at,metadata)
                VALUES (%s,'owner@r1c.invalid','R1C Owner','96550000008301',
                        'owner','active',now(),%s)
                RETURNING *
                """,
                (COMPANY, Json({"smoke": REVIEW})),
            )
            owner = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO employees
                  (company_code,employee_key,name,phone,email,employment_status,
                   onboarding_status,profile,raw_json,created_at,updated_at)
                VALUES (%s,%s,'R1C Employee','96550000008302','employee@r1c.invalid',
                        'active','not_started',%s,%s,now(),now())
                """,
                (COMPANY, EMPLOYEE, Json({"smoke": REVIEW}), Json({"smoke": REVIEW})),
            )
        conn.commit()
    token, _ = app.create_dashboard_session(owner)
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
        assert result.get("ok"), result
    return {"owner": owner, "token": token}


def context(token: str) -> dict[str, Any]:
    return app.dashboard_context(
        authorization=f"Bearer {token}",
        x_dashboard_token=None,
        x_hr_phone=None,
        x_company_code=COMPANY,
    )


def request(*, supersede: str | None = None, key: str | None = None) -> app.DashboardEmployeeAppInviteRequest:
    return app.DashboardEmployeeAppInviteRequest(
        delivery_mode="hr_task_only",
        idempotency_key=key or str(uuid.uuid4()),
        reason=REASON,
        supersede_invite_id=supersede,
    )


def counts() -> dict[str, int]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM employee_app_invites WHERE company_code=%s", (COMPANY,))
            invites = int(cur.fetchone()["n"])
            cur.execute("SELECT count(*) AS n FROM hr_tasks WHERE company_code=%s AND task_type='app_activation_handoff'", (COMPANY,))
            tasks = int(cur.fetchone()["n"])
            cur.execute("SELECT count(*) AS n FROM action_results WHERE company_code=%s AND action_type='app_invite_created_hr_task_only'", (COMPANY,))
            audits = int(cur.fetchone()["n"])
    return {"invites": invites, "tasks": tasks, "audits": audits}


def raw_absent_from_persistence(raw_code: str) -> bool:
    tables = ("employee_app_invites", "hr_tasks", "action_results", "employee_messages")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in tables:
                cur.execute(f"SELECT count(*) AS n FROM {table} t WHERE row_to_json(t)::text LIKE %s", (f"%{raw_code}%",))
                if int(cur.fetchone()["n"]):
                    return False
    return True


def expect_conflict(fn: Callable[[], Any], code: str) -> dict[str, Any] | None:
    try:
        fn()
    except app.HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return detail if exc.status_code == 409 and detail.get("error") == code else None
    return None


def main() -> int:
    previous_flag = app.os.environ.get("WATHEFNI_EMPLOYEE_APP")
    app.os.environ["WATHEFNI_EMPLOYEE_APP"] = "on"
    app.ensure_schema(force=True)
    checks = Checks()
    fixture = setup()
    ctx = context(fixture["token"])
    capture = Capture()
    app.logger.addHandler(capture)
    provider_calls: list[str] = []
    patched: list[tuple[Any, str, Any]] = []

    def block_provider(name: str):
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
            setattr(owner, name, block_provider(name))

    try:
        first_request = request()
        response = Response()
        first = app.dashboard_posthire_app_invite(EMPLOYEE, first_request, response, ctx)
        first_code = str(first["activation_code"])
        first_counts = counts()
        checks.check("exactly one metadata-only HR task is created", lambda: first_counts == {"invites": 1, "tasks": 1, "audits": 1})
        checks.check("no external provider is invoked", lambda: provider_calls == [])
        checks.check("response is marked no-store", lambda: response.headers.get("cache-control") == "no-store")

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM employee_app_invites WHERE invite_id=%s", (first["invite_id"],))
                invite = dict(cur.fetchone())
                cur.execute("SELECT * FROM hr_tasks WHERE related_invite_id=%s", (first["invite_id"],))
                task = dict(cur.fetchone())
        checks.check(
            "only the activation hash is persisted",
            lambda: invite["code_hash"] == app._app_code_hash(COMPANY, invite["phone"], first_code)
            and invite["code_hash"] != first_code,
        )
        checks.check("raw code is absent from persistence", lambda: raw_absent_from_persistence(first_code))
        checks.check("raw code is absent from captured logs", lambda: all(first_code not in message for message in capture.messages))
        checks.check(
            "authorized HR owner is assigned the task",
            lambda: str(task["assigned_to_user_id"]) == str(fixture["owner"]["user_id"])
            and task["metadata"].get("contains_activation_secret") is False,
        )

        replay = expect_conflict(
            lambda: app.dashboard_posthire_app_invite(EMPLOYEE, first_request, Response(), ctx),
            "activation_code_already_disclosed",
        )
        checks.check("the raw response cannot be replayed", lambda: bool(replay))
        pending = expect_conflict(
            lambda: app.dashboard_posthire_app_invite(EMPLOYEE, request(), Response(), ctx),
            "pending_activation_invite_exists",
        )
        checks.check("lost response requires explicit supersede", lambda: pending and pending.get("pending_invite_id") == first["invite_id"])

        second_response = Response()
        second = app.dashboard_posthire_app_invite(
            EMPLOYEE,
            request(supersede=first["invite_id"]),
            second_response,
            ctx,
        )
        second_code = str(second["activation_code"])
        checks.check("explicit supersede-and-reissue creates one new task", lambda: counts() == {"invites": 2, "tasks": 2, "audits": 2})
        checks.check("reissued code also stays out of persistence and logs", lambda: raw_absent_from_persistence(second_code) and all(second_code not in message for message in capture.messages))

        before_failure = counts()
        real_audit = app.write_admin_audit
        app.write_admin_audit = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("synthetic_audit_failure"))
        try:
            try:
                app.dashboard_posthire_app_invite(
                    EMPLOYEE,
                    request(supersede=second["invite_id"]),
                    Response(),
                    ctx,
                )
            except RuntimeError:
                pass
        finally:
            app.write_admin_audit = real_audit
        checks.check("audit failure rolls back invite and task atomically", lambda: counts() == before_failure)
        return checks.report()
    finally:
        for owner, name, original in patched:
            setattr(owner, name, original)
        app.logger.removeHandler(capture)
        purge()
        if previous_flag is None:
            app.os.environ.pop("WATHEFNI_EMPLOYEE_APP", None)
        else:
            app.os.environ["WATHEFNI_EMPLOYEE_APP"] = previous_flag


if __name__ == "__main__":
    sys.exit(main())
