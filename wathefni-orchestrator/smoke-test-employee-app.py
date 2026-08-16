"""Employee App / Portal harness (staging).

Exercises the /app/* surface end to end against the staging DB: the dark-launch
flag gate, HR-provisioned activation (code verify + attempt lockout), opaque
sessions (rotate + revoke), the self-scope guard on every read/write (an employee
only ever sees/touches their OWN data), push token register/unregister, and the
offboarding kill switch (terminating an employee instantly revokes sessions +
push tokens).

Run on a host with the orchestrator venv + (staging) database:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-employee-app.py

NEVER point this at the production database: it writes and deletes a company.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

try:
    import app
    import employee_app_access as access
    from psycopg2.extras import Json
except ModuleNotFoundError as exc:
    if exc.name in {"psycopg2", "app"} or (exc.name or "").startswith("psycopg2"):
        print("SKIP: psycopg2 not available locally; full run happens on staging.")
        sys.exit(0)
    raise

COMPANY = "EMPAPPTESTCO"
MARKER = "temporary_employee_app_harness"
MODULES = ["onboarding", "leave", "compliance", "employee_app"]

EMP_A = f"empapp-a-{COMPANY}"
EMP_B = f"empapp-b-{COMPANY}"
# Canonical Kuwait 965 + 8 digits. The local-8 alias check below only resolves when the
# fixture is a real-shaped number, so these must stay 11 digits.
PHONE_A = "96559990701"
PHONE_B = "96559990702"


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:
            self.failed.append(f"{label} -> raised {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def report(self) -> int:
        for label in self.passed:
            print(f"  PASS  {label}")
        for label in self.failed:
            print(f"  FAIL  {label}")
        print(f"\n{len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def _flag(on: bool) -> None:
    if on:
        app.os.environ["WATHEFNI_EMPLOYEE_APP"] = "on"
    else:
        app.os.environ.pop("WATHEFNI_EMPLOYEE_APP", None)


_ALLOWLIST_ENV = "WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"
_ORIGINAL_ALLOWLIST: str | None = None


def _allowlist_fixtures() -> None:
    """Controlled rollout stays fail-closed; scope the allowlist to our own keys."""
    global _ORIGINAL_ALLOWLIST
    _ORIGINAL_ALLOWLIST = app.os.environ.get(_ALLOWLIST_ENV)
    current = {k for k in (_ORIGINAL_ALLOWLIST or "").split(",") if k.strip()}
    app.os.environ[_ALLOWLIST_ENV] = ",".join(sorted(current | {EMP_A, EMP_B}))


def _restore_allowlist() -> None:
    if _ORIGINAL_ALLOWLIST is None:
        app.os.environ.pop(_ALLOWLIST_ENV, None)
    else:
        app.os.environ[_ALLOWLIST_ENV] = _ORIGINAL_ALLOWLIST


def _push_flag(on: bool) -> None:
    if on:
        app.os.environ["WATHEFNI_PUSH_NOTIFICATIONS"] = "on"
    else:
        app.os.environ.pop("WATHEFNI_PUSH_NOTIFICATIONS", None)


def _columns(cur: Any, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    return {r["column_name"] for r in cur.fetchall()}


def _exec(sql: str, params: tuple) -> None:
    with app.db_connect() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()


def _insert_employee(cur: Any, columns: set[str], emp_key: str, phone: str, name: str) -> None:
    desired: dict[str, Any] = {
        "company_code": COMPANY, "phone": phone, "name": name,
        "email": f"{emp_key}@example.com", "employee_key": emp_key,
        "onboarding_status": "in_progress", "employment_status": "active",
        "raw_json": Json({"smoke": MARKER}), "profile": Json({"smoke": MARKER}),
    }
    cols = [c for c in desired if c in columns]
    cur.execute(f"INSERT INTO employees ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})", [desired[c] for c in cols])


def _purge() -> None:
    keys = [EMP_A, EMP_B]
    for sql, params in [
        ("DELETE FROM employee_app_invites WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM employee_sessions WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM employee_push_tokens WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM employee_notification_reads WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM file_registry WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM file_registry WHERE subject_key = ANY(%s)", (keys,)),
        ("DELETE FROM leave_requests WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM leave_events WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM onboarding_items WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM onboarding_items WHERE employee_key = ANY(%s)", (keys,)),
        ("DELETE FROM company_modules WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM employees WHERE company_code=%s", (COMPANY,)),
    ]:
        _exec(sql, params)


def setup() -> None:
    _purge()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO UPDATE SET metadata=EXCLUDED.metadata",
                (COMPANY, "Employee App Harness", Json({"smoke": MARKER, "modules": MODULES}), Json({"smoke": MARKER})),
            )
            for mod in MODULES:
                cur.execute(
                    "INSERT INTO company_modules (company_code, module_key, enabled, source) VALUES (%s,%s,TRUE,%s) "
                    "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=TRUE",
                    (COMPANY, mod, MARKER),
                )
            emp_cols = _columns(cur, "employees")
            _insert_employee(cur, emp_cols, EMP_A, PHONE_A, "App User A")
            _insert_employee(cur, emp_cols, EMP_B, PHONE_B, "App User B")
            # One pending onboarding item for A so the onboarding read has content.
            item_cols = _columns(cur, "onboarding_items")
            desired = {
                "company_code": COMPANY, "employee_key": EMP_A, "item_id": "civil_id",
                "label": "Civil ID", "item_type": "document", "document_type": "civil_id",
                "required": True, "status": "pending",
            }
            cols = [c for c in desired if c in item_cols]
            cur.execute(f"INSERT INTO onboarding_items ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})", [desired[c] for c in cols])
            # A stored document owned by B (for the cross-employee 404 guard).
            cur.execute(
                """
                INSERT INTO file_registry
                  (company_code, subject_type, subject_key, file_kind, document_type,
                   original_filename, storage_provider, storage_status, storage_url, metadata)
                VALUES (%s,'employee',%s,'onboarding_document','civil_id','b-civil.pdf','local','stored','local://nope', %s)
                RETURNING file_id
                """,
                (COMPANY, EMP_B, Json({"item_id": "civil_id", "label": "Civil ID"})),
            )
            globals()["_FILE_B"] = str(cur.fetchone()["file_id"])
            access.ensure_access_schema(cur)
        conn.commit()
    _grant_app_access()


def _hr_context() -> dict[str, Any]:
    return {
        "company_code": COMPANY,
        "user_id": "employee-app-harness",
        "actor_user_id": "employee-app-harness",
        "email": "employee-app-harness@wathefni.ai",
        "permissions": ["employees.manage", "onboarding.manage"],
    }


def _grant_app_access() -> None:
    """Employee App access is an explicit HR grant, never implied by employment.

    The harness activates real invites, so it must go through the canonical grant
    instead of writing the flag: that keeps this suite honest about the frozen
    access policy while still exercising activation, session and self-scope paths.
    """
    _flag(True)
    _allowlist_fixtures()
    access.set_company_app_access_policy(
        app, _hr_context(), module_enabled=True, access_mode="selected", sync_invites=False
    )
    for key in (EMP_A, EMP_B):
        access.set_employee_app_access(
            app,
            _hr_context(),
            employee_key=key,
            enabled=True,
            reason="employee-app-harness",
            deliver_invite=False,
        )


def teardown() -> None:
    _purge()
    _exec("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
    _flag(False)
    _push_flag(False)
    _restore_allowlist()


def _ctx(token: str) -> dict[str, Any]:
    return app.employee_app_context(authorization=f"Bearer {token}")


def _denied(fn: Callable[[], Any], status_code: int) -> bool:
    try:
        fn()
        return False
    except app.HTTPException as exc:
        return exc.status_code == status_code


def _denied_with_error(fn: Callable[[], Any], status_code: int, error: str) -> bool:
    try:
        fn()
        return False
    except app.HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return exc.status_code == status_code and detail.get("error") == error


def run_checks(checks: Checks) -> None:
    # --- Flag gate -----------------------------------------------------------
    _flag(False)
    checks.check("flag defaults OFF", lambda: app.employee_app_enabled() is False)
    checks.check("anonymous context fails auth before flag disclosure (401)", lambda: _denied(lambda: app.employee_app_context(authorization="Bearer nope"), 401))

    _flag(True)
    checks.check("flag flips ON", lambda: app.employee_app_enabled() is True)
    checks.check("bad token rejected (401)", lambda: _denied(lambda: app.employee_app_context(authorization="Bearer nope"), 401))

    employee_a = app.find_employee_by_key(EMP_A, company_code=COMPANY)

    # --- Activation: wrong code, lockout, then success -----------------------
    _invite1, _code1 = app.create_employee_app_invite(COMPANY, employee_a)
    checks.check("wrong code fails generically (401)", lambda: _denied(lambda: app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_A, code="000000")), 401))

    # Fresh invite: exactly MAX wrong attempts bring it to the threshold WITHOUT
    # locking (each saw attempts < MAX); the NEXT call (even a correct code) trips
    # the lockout and returns 429.
    _invite2, code2 = app.create_employee_app_invite(COMPANY, employee_a)
    for _ in range(app._EMPLOYEE_APP_MAX_CODE_ATTEMPTS):
        try:
            app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_A, code="111111"))
        except app.HTTPException:
            pass
    checks.check("locked invite rejects even the correct code (429)", lambda: _denied(lambda: app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_A, code=code2)), 429))

    # Fresh invite -> correct code activates.
    _invite3, code3 = app.create_employee_app_invite(COMPANY, employee_a)
    activated = app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_A, code=code3))
    checks.check("correct code activates + returns tokens", lambda: bool(activated.get("token")) and bool(activated.get("refresh_token")))
    checks.check("activation employee is self-scoped", lambda: activated["employee"]["employee_key"] == EMP_A)
    token_a = activated["token"]
    refresh_a = activated["refresh_token"]

    # Activate B too (separate employee, same company).
    _ib, code_b = app.create_employee_app_invite(COMPANY, app.find_employee_by_key(EMP_B, company_code=COMPANY))
    activated_b = app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_B, code=code_b))
    token_b = activated_b["token"]

    # --- Session lifecycle ---------------------------------------------------
    checks.check("session resolves to the right employee", lambda: app.employee_by_session(token_a)["employee_key"] == EMP_A)
    rotated = app.rotate_employee_session(refresh_a)
    checks.check("refresh rotates the session", lambda: bool(rotated and rotated.get("token") and rotated["token"] != token_a))
    checks.check("old access token dead after rotation", lambda: app.employee_by_session(token_a) is None)
    # HTTP refresh path (Wave 1 freeze) must match helper rotation.
    http_rotated = app.app_auth_refresh(app.EmployeeAppRefreshRequest(refresh_token=rotated["refresh_token"]))
    checks.check(
        "HTTP /app/auth/refresh rotates tokens",
        lambda: bool(http_rotated.get("token")) and http_rotated["token"] != rotated["token"],
    )
    token_a = http_rotated["token"]
    refresh_a = http_rotated["refresh_token"]

    # Kuwait local-8 activate against invite stored as 965… (Wave 1 freeze).
    local8 = PHONE_A[-8:]
    _invite_alias, code_alias = app.create_employee_app_invite(COMPANY, employee_a)
    activated_alias = app.app_auth_activate(app.EmployeeAppActivateRequest(phone=local8, code=code_alias))
    checks.check(
        "Kuwait local-8 activate matches 965 invite",
        lambda: bool(activated_alias.get("token")) and activated_alias["employee"]["employee_key"] == EMP_A,
    )
    checks.check(
        "new-device activate revokes prior session",
        lambda: app.employee_by_session(token_a) is None,
    )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT revoked_reason FROM employee_sessions
                WHERE company_code=%s AND employee_key=%s AND status='revoked'
                ORDER BY revoked_at DESC NULLS LAST
                LIMIT 1
                """,
                (COMPANY, EMP_A),
            )
            row = dict(cur.fetchone() or {})
    checks.check(
        "new-device revoke reason is reactivated_via_invite",
        lambda: row.get("revoked_reason") == "reactivated_via_invite",
    )
    token_a = activated_alias["token"]
    refresh_a = activated_alias["refresh_token"]

    # Logout (Wave 1 freeze).
    logged_out = app.app_auth_logout(authorization=f"Bearer {token_a}")
    checks.check("HTTP /app/auth/logout returns ok", lambda: logged_out.get("ok") is True)
    checks.check("access token dead after logout", lambda: app.employee_by_session(token_a) is None)
    checks.check(
        "refresh dead after logout session revoke",
        lambda: app.rotate_employee_session(refresh_a) is None,
    )

    # Re-activate for remaining checks.
    _invite_re, code_re = app.create_employee_app_invite(COMPANY, employee_a)
    reactivated = app.app_auth_activate(app.EmployeeAppActivateRequest(phone=PHONE_A, code=code_re))
    token_a = reactivated["token"]
    refresh_a = reactivated["refresh_token"]

    # request-code is always generic and never self-registers strangers.
    rc = app.app_auth_request_code(app.EmployeeAppRequestCodeRequest(phone=PHONE_A))
    checks.check("request-code returns generic ok", lambda: rc.get("ok") is True and "registered" in str(rc.get("message") or "").lower())
    stranger = app.app_auth_request_code(app.EmployeeAppRequestCodeRequest(phone="96550009999999"))
    checks.check(
        "request-code silent for unknown phone",
        lambda: stranger.get("ok") is True and stranger.get("message") == rc.get("message"),
    )

    # --- Current account/platform state remains authoritative ----------------
    _exec("UPDATE companies SET status='disabled' WHERE company_code=%s", (COMPANY,))
    checks.check(
        "disabled company returns explicit account state",
        lambda: _denied_with_error(lambda: _ctx(token_a), 403, "company_disabled"),
    )
    _exec("UPDATE companies SET status='active' WHERE company_code=%s", (COMPANY,))
    _exec("UPDATE company_modules SET enabled=FALSE WHERE company_code=%s AND module_key='employee_app'", (COMPANY,))
    checks.check(
        "employee_app removal returns explicit account state",
        lambda: _denied_with_error(lambda: _ctx(token_a), 403, "employee_app_not_enabled_for_company"),
    )
    _exec("UPDATE company_modules SET enabled=TRUE WHERE company_code=%s AND module_key='employee_app'", (COMPANY,))

    # --- /app reads honor self-scope ----------------------------------------
    ctx_a = _ctx(token_a)
    ctx_b = _ctx(token_b)
    checks.check("context identity is the session employee", lambda: ctx_a["employee_key"] == EMP_A)
    onboarding = app.app_onboarding(ctx_a)
    checks.check("onboarding read returns own pending item", lambda: any(i.get("item_id") == "civil_id" for i in onboarding.get("pending", [])))
    leave = app.app_leave(ctx_a)
    checks.check("leave read returns own (empty) list", lambda: leave.get("ok") is True and isinstance(leave.get("requests"), list))
    docs_a = app.app_documents(ctx_a)
    checks.check("A's document list excludes B's document", lambda: all(d.get("file_id") != _FILE_B for d in docs_a.get("documents", [])))
    checks.check("A cannot open B's document (404)", lambda: _denied(lambda: app.app_document_file(_FILE_B, context=ctx_a), 404))

    # --- Leave write self-scope ---------------------------------------------
    res = app.app_leave_request(app.EmployeeLeaveRequestBody(start_date="2099-01-10", end_date="2099-01-12", leave_type="annual"), context=ctx_a)
    checks.check("A can request leave for self", lambda: res.get("ok") is True and bool((res.get("leave") or {}).get("leave_id")))
    leave_id = str((res.get("leave") or {}).get("leave_id"))
    checks.check("B cannot cancel A's leave (404)", lambda: _denied(lambda: app.app_leave_cancel(leave_id, context=ctx_b), 404))
    cancelled = app.app_leave_cancel(leave_id, context=ctx_a)
    checks.check("A can cancel own leave", lambda: cancelled.get("ok") is True)

    # --- Push register / unregister -----------------------------------------
    _push_flag(False)
    checks.check(
        "push registration denied while push capability OFF",
        lambda: _denied(
            lambda: app.app_push_register(
                app.EmployeePushRegisterBody(push_token="ExponentPushToken[SMOKE-DENIED]", platform="ios"),
                context=ctx_a,
            ),
            403,
        ),
    )
    _push_flag(True)
    app.app_push_register(app.EmployeePushRegisterBody(push_token="ExponentPushToken[SMOKE-A]", platform="ios"), context=ctx_a)
    checks.check("push token registered + active", lambda: "ExponentPushToken[SMOKE-A]" in app.active_push_tokens_for(COMPANY, EMP_A))
    app.app_push_unregister(app.EmployeePushUnregisterBody(push_token="ExponentPushToken[SMOKE-A]"), context=ctx_a)
    checks.check("push token deactivated on unregister", lambda: "ExponentPushToken[SMOKE-A]" not in app.active_push_tokens_for(COMPANY, EMP_A))

    # --- Offboarding kill switch --------------------------------------------
    app.app_push_register(app.EmployeePushRegisterBody(push_token="ExponentPushToken[SMOKE-A2]", platform="ios"), context=ctx_a)
    app.set_employee_employment_status(COMPANY, EMP_A, "left")
    checks.check("offboarding revokes the session", lambda: app.employee_by_session(token_a) is None)
    checks.check(
        "offboarded token returns explicit inactive state",
        lambda: _denied_with_error(lambda: _ctx(token_a), 403, "account_inactive"),
    )
    checks.check("offboarding deactivates push tokens", lambda: app.active_push_tokens_for(COMPANY, EMP_A) == [])
    # Reinstate so teardown is clean (and prove reactivation path doesn't auto-restore access).
    app.set_employee_employment_status(COMPANY, EMP_A, "active")
    checks.check("revoked session stays dead after reactivation", lambda: app.employee_by_session(token_a) is None)


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"employee app harness — company {COMPANY} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nEMPLOYEE APP: FAILURES PRESENT")
    else:
        print("\nEMPLOYEE APP: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
