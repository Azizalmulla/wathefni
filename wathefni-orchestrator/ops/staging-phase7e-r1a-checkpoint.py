#!/usr/bin/env python3
"""Focused Phase 7E-R1A staging checkpoint.

Uses only P7ESTG01/P7ESTG02 synthetic fixtures and mocked/no outbound delivery.
Production is read-only snapshotted before/after. Protected service flags remain off.
"""

from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import threading
from typing import Any


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "phase7e_verifier",
    HERE / "staging-phase7e-employee-app-verify.py",
)
if SPEC is None or SPEC.loader is None:
    raise SystemExit("unable to load Phase 7E verifier helpers")
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)
app = v.app

REPORT_PATH = Path(
    os.environ.get(
        "WATHEFNI_PHASE7E_R1A_REPORT",
        str(HERE / "reports" / "phase7e-r1a-checkpoint-report.json"),
    )
)

checks: list[dict[str, Any]] = []


def record(case_id: str, title: str, passed: bool, observed: Any) -> None:
    checks.append(
        {
            "case_id": case_id,
            "title": title,
            "passed": bool(passed),
            "observed": v.json_safe(observed),
        }
    )
    print(f"{'PASS' if passed else 'FAIL'} {case_id} {title}")


def one(sql: str, params: tuple[Any, ...]) -> dict[str, Any]:
    rows = v.exec_sql(sql, params)
    return dict(rows[0]) if rows else {}


def invite_state(invite_id: str) -> str | None:
    return v.scalar(
        "SELECT status FROM employee_app_invites WHERE invite_id=%s",
        (invite_id,),
    )


def session_state(session_id: str) -> dict[str, Any]:
    return one(
        "SELECT session_id, status, refresh_hash, revoked_reason FROM employee_sessions WHERE session_id=%s",
        (session_id,),
    )


def active_session_count(employee_key: str) -> int:
    return int(
        v.scalar(
            "SELECT count(*) FROM employee_sessions WHERE company_code=%s AND employee_key=%s AND status='active'",
            (v.COMPANY, employee_key),
        )
        or 0
    )


def latest_session(employee_key: str) -> dict[str, Any]:
    return one(
        """
        SELECT session_id, status, token_hash, refresh_hash
        FROM employee_sessions
        WHERE company_code=%s AND employee_key=%s
        ORDER BY created_at DESC LIMIT 1
        """,
        (v.COMPANY, employee_key),
    )


def superadmin() -> dict[str, Any]:
    return {
        "actor_user_id": f"{v.MARKER}:superadmin",
        "actor_role": "superadmin",
        "actor_phone": "96555557000",
        "actor_email": "phase7e-r1a@synthetic.invalid",
        "hr_phone": "96555557000",
        "hr_user": {"role": "superadmin", "company_code": v.COMPANY},
    }


def set_employee_status(employee_key: str, status: str) -> None:
    v.exec_sql(
        "UPDATE employees SET employment_status=%s, updated_at=now() WHERE company_code=%s AND employee_key=%s",
        (status, v.COMPANY, employee_key),
    )


def exercise_non_consumption() -> None:
    # Identity mismatch.
    code = "741001"
    invite_id = v.insert_invite(v.COMPANY, v.EMP_A, v.PHONE_D, code)
    before = active_session_count(v.EMP_D)
    result = v.invoke(
        lambda: app.app_auth_activate(
            app.EmployeeAppActivateRequest(phone=v.PHONE_D, code=code)
        )
    )
    record(
        "R1A-I1",
        "identity mismatch is generic and leaves invite/session unchanged",
        v.denied(result, {401})
        and invite_state(invite_id) == "pending"
        and active_session_count(v.EMP_D) == before,
        {
            "response": result,
            "invite_status": invite_state(invite_id),
            "active_sessions_before": before,
            "active_sessions_after": active_session_count(v.EMP_D),
        },
    )

    # Direct lifecycle-state denials prove activation does not mutate the invite.
    for case_id, status, key, phone, code in (
        ("R1A-L1", "disabled", v.EMP_E, v.PHONE_E, "741002"),
        ("R1A-L2", "archived", v.EMP_F, v.PHONE_F, "741003"),
    ):
        invite_id = v.insert_invite(v.COMPANY, key, phone, code)
        v.set_company_status(v.COMPANY, status)
        result = v.invoke(
            lambda phone=phone, code=code: app.app_auth_activate(
                app.EmployeeAppActivateRequest(phone=phone, code=code)
            )
        )
        record(
            case_id,
            f"{status} activation denial leaves invite pending",
            v.denied(result, {401})
            and invite_state(invite_id) == "pending"
            and active_session_count(key) == 0,
            {
                "response": result,
                "invite_status": invite_state(invite_id),
                "active_sessions": active_session_count(key),
            },
        )
        v.set_company_status(v.COMPANY, "active")

    # Direct module denial proves no consumption before the transition hook.
    code = "741004"
    invite_id = v.insert_invite(v.COMPANY, v.EMP_E, v.PHONE_E, code)
    v.set_module(v.COMPANY, "employee_app", False)
    result = v.invoke(
        lambda: app.app_auth_activate(
            app.EmployeeAppActivateRequest(phone=v.PHONE_E, code=code)
        )
    )
    record(
        "R1A-M1",
        "module denial leaves invite pending",
        v.denied(result, {401})
        and invite_state(invite_id) == "pending"
        and active_session_count(v.EMP_E) == 0,
        {"response": result, "invite_status": invite_state(invite_id)},
    )
    v.set_module(v.COMPANY, "employee_app", True)

    # Employee eligibility denial.
    code = "741005"
    invite_id = v.insert_invite(v.COMPANY, v.EMP_E, v.PHONE_E, code)
    set_employee_status(v.EMP_E, "terminated")
    result = v.invoke(
        lambda: app.app_auth_activate(
            app.EmployeeAppActivateRequest(phone=v.PHONE_E, code=code)
        )
    )
    record(
        "R1A-E1",
        "ineligible employee denial leaves invite pending",
        v.denied(result, {401})
        and invite_state(invite_id) == "pending"
        and active_session_count(v.EMP_E) == 0,
        {"response": result, "invite_status": invite_state(invite_id)},
    )
    set_employee_status(v.EMP_E, "active")


def exercise_concurrent_activation() -> tuple[str, str]:
    employee = app.find_employee_by_key(v.EMP_A, company_code=v.COMPANY)
    invite, code = app.create_employee_app_invite(v.COMPANY, employee)
    barrier = threading.Barrier(2)

    def activate() -> dict[str, Any]:
        barrier.wait(timeout=10)
        return v.invoke(
            lambda: app.app_auth_activate(
                app.EmployeeAppActivateRequest(phone=v.PHONE_A, code=code)
            )
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=30) for future in (pool.submit(activate), pool.submit(activate))]
    successes = [item for item in results if item.get("returned") and item.get("status_code") == 200]
    denied = [item for item in results if not item.get("returned")]
    session_count = active_session_count(v.EMP_A)
    state = invite_state(str(invite["invite_id"]))
    record(
        "R1A-C1",
        "concurrent double activation yields one success and one session",
        len(successes) == 1
        and len(denied) == 1
        and session_count == 1
        and state == "redeemed",
        {
            "statuses": [item.get("status_code") for item in results],
            "successes": len(successes),
            "active_sessions": session_count,
            "invite_status": state,
        },
    )
    if not successes:
        raise RuntimeError("concurrent activation did not produce a usable session")
    return (
        str(successes[0]["body"]["token"]),
        str(successes[0]["body"]["refresh_token"]),
    )


def exercise_repeated_activation() -> str:
    employee = app.find_employee_by_key(v.EMP_A, company_code=v.COMPANY)
    invite, code = app.create_employee_app_invite(v.COMPANY, employee)
    before = active_session_count(v.EMP_A)
    result = v.invoke(
        lambda: app.app_auth_activate(
            app.EmployeeAppActivateRequest(phone=v.PHONE_A, code=code)
        )
    )
    record(
        "R1A-A1",
        "already activated returns deterministic 409 without consuming invite",
        v.denied(result, {409})
        and (result.get("body") or {}).get("error") == "already_activated"
        and active_session_count(v.EMP_A) == before
        and invite_state(str(invite["invite_id"])) == "pending",
        {
            "response": result,
            "active_sessions_before": before,
            "active_sessions_after": active_session_count(v.EMP_A),
            "invite_status": invite_state(str(invite["invite_id"])),
        },
    )
    return str(invite["invite_id"])


def exercise_refresh_denials(token: str, refresh: str) -> None:
    # Direct module state denial: no transition mutation, so hashes must be byte-for-byte unchanged.
    before = latest_session(v.EMP_A)
    v.set_module(v.COMPANY, "employee_app", False)
    result = v.invoke(
        lambda: app.app_auth_refresh(app.EmployeeAppRefreshRequest(refresh_token=refresh))
    )
    after = session_state(str(before["session_id"]))
    record(
        "R1A-R1",
        "module-denied refresh creates no replacement hash or credentials",
        v.denied(result, {401, 403})
        and after.get("refresh_hash") == before.get("refresh_hash")
        and active_session_count(v.EMP_A) == 1,
        {
            "response": result,
            "refresh_hash_unchanged": after.get("refresh_hash") == before.get("refresh_hash"),
            "active_sessions": active_session_count(v.EMP_A),
        },
    )
    v.set_module(v.COMPANY, "employee_app", True)

    for case_id, status in (("R1A-R2", "disabled"), ("R1A-R3", "archived")):
        before = latest_session(v.EMP_A)
        v.set_company_status(v.COMPANY, status)
        result = v.invoke(
            lambda: app.app_auth_refresh(
                app.EmployeeAppRefreshRequest(refresh_token=refresh)
            )
        )
        after = session_state(str(before["session_id"]))
        record(
            case_id,
            f"{status} refresh creates no replacement hash or credentials",
            v.denied(result, {401, 403})
            and after.get("refresh_hash") == before.get("refresh_hash")
            and active_session_count(v.EMP_A) == 1,
            {
                "response": result,
                "refresh_hash_unchanged": after.get("refresh_hash") == before.get("refresh_hash"),
            },
        )
        v.set_company_status(v.COMPANY, "active")

    before = latest_session(v.EMP_A)
    set_employee_status(v.EMP_A, "terminated")
    result = v.invoke(
        lambda: app.app_auth_refresh(app.EmployeeAppRefreshRequest(refresh_token=refresh))
    )
    after = session_state(str(before["session_id"]))
    record(
        "R1A-R4",
        "employee-ineligible refresh creates no replacement hash or credentials",
        v.denied(result, {401, 403})
        and after.get("refresh_hash") == before.get("refresh_hash"),
        {
            "response": result,
            "refresh_hash_unchanged": after.get("refresh_hash") == before.get("refresh_hash"),
        },
    )
    set_employee_status(v.EMP_A, "active")

    # The original bearer remains usable until an actual transition revokes it.
    record(
        "R1A-R5",
        "pre-transition bearer still maps to exactly one employee",
        v.invoke(lambda: app.employee_app_context(authorization=f"Bearer {token}")).get("returned") is True,
        {"active_sessions": active_session_count(v.EMP_A)},
    )


def exercise_module_transition(token: str, refresh: str, pending_invite_id: str) -> None:
    before = latest_session(v.EMP_A)
    result = app.setup_console_set_modules(
        v.COMPANY,
        app.SetupModulesRequest(modules=["onboarding", "leave"]),
        superadmin(),
    )
    after = session_state(str(before["session_id"]))
    record(
        "R1A-M2",
        "module removal revokes sessions/refresh and supersedes pending invites",
        after.get("status") == "revoked"
        and after.get("refresh_hash") is None
        and invite_state(pending_invite_id) == "superseded"
        and int(result.get("revoked_employee_app_sessions") or 0) >= 1
        and int(result.get("superseded_employee_app_invites") or 0) >= 1,
        {
            "transition": result,
            "session_status": after.get("status"),
            "refresh_hash_cleared": after.get("refresh_hash") is None,
            "invite_status": invite_state(pending_invite_id),
        },
    )
    denied_bearer = v.invoke(
        lambda: app.employee_app_context(authorization=f"Bearer {token}")
    )
    denied_refresh = v.invoke(
        lambda: app.app_auth_refresh(app.EmployeeAppRefreshRequest(refresh_token=refresh))
    )
    app.setup_console_set_modules(
        v.COMPANY,
        app.SetupModulesRequest(modules=["employee_app", "onboarding", "leave"]),
        superadmin(),
    )
    record(
        "R1A-M3",
        "module re-addition does not revive old sessions, refresh, or invites",
        v.denied(denied_bearer, {401, 403})
        and v.denied(denied_refresh, {401, 403})
        and v.denied(v.invoke(lambda: app.employee_app_context(authorization=f"Bearer {token}")), {401, 403})
        and v.denied(
            v.invoke(
                lambda: app.app_auth_refresh(
                    app.EmployeeAppRefreshRequest(refresh_token=refresh)
                )
            ),
            {401, 403},
        )
        and invite_state(pending_invite_id) == "superseded",
        {
            "session": session_state(str(before["session_id"])),
            "invite_status": invite_state(pending_invite_id),
        },
    )


def exercise_lifecycle_transition(status: str, case_prefix: str) -> None:
    session = app.create_employee_session(v.COMPANY, v.EMP_E, v.PHONE_E)
    session_row = latest_session(v.EMP_E)
    invite_id = v.insert_invite(v.COMPANY, v.EMP_E, v.PHONE_E, f"74200{1 if status == 'disabled' else 2}")
    result = app.setup_console_set_company_lifecycle(
        v.COMPANY,
        app.SetupCompanyLifecycleRequest(status=status, reason=f"{v.MARKER}:{status}"),
        superadmin(),
    )
    after = session_state(str(session_row["session_id"]))
    record(
        f"{case_prefix}1",
        f"{status} transition revokes employee sessions/refresh and supersedes invites",
        after.get("status") == "revoked"
        and after.get("refresh_hash") is None
        and invite_state(invite_id) == "superseded"
        and int(result.get("revoked_employee_app_sessions") or 0) >= 1
        and int(result.get("superseded_employee_app_invites") or 0) >= 1,
        {
            "transition": result,
            "session_status": after.get("status"),
            "refresh_hash_cleared": after.get("refresh_hash") is None,
            "invite_status": invite_state(invite_id),
        },
    )
    app.setup_console_set_company_lifecycle(
        v.COMPANY,
        app.SetupCompanyLifecycleRequest(status="active", reason=f"{v.MARKER}:reactivate"),
        superadmin(),
    )
    old_bearer = v.invoke(
        lambda: app.employee_app_context(authorization=f"Bearer {session['token']}")
    )
    old_refresh = v.invoke(
        lambda: app.app_auth_refresh(
            app.EmployeeAppRefreshRequest(refresh_token=session["refresh_token"])
        )
    )
    record(
        f"{case_prefix}2",
        f"reactivation after {status} does not revive credentials or invite",
        v.denied(old_bearer, {401, 403})
        and v.denied(old_refresh, {401, 403})
        and invite_state(invite_id) == "superseded",
        {
            "bearer": old_bearer,
            "refresh": old_refresh,
            "invite_status": invite_state(invite_id),
        },
    )


def main() -> int:
    production_before = v.production_snapshot()
    protected_before = v.staging_protected_snapshot()
    try:
        v.setup()
        v.set_flag("WATHEFNI_EMPLOYEE_APP", True)
        v.set_flag("WATHEFNI_COMPANY_CHANNEL_ACCOUNTS", False)
        v.set_flag("WATHEFNI_ONBOARDING_SEED", False)
        v.set_flag("WATHEFNI_PUSH_NOTIFICATIONS", False)
        v.set_module(v.COMPANY, "employee_app", True)
        v.set_module(v.OTHER_COMPANY, "employee_app", True)

        exercise_non_consumption()
        token, refresh = exercise_concurrent_activation()
        pending_invite_id = exercise_repeated_activation()
        exercise_refresh_denials(token, refresh)
        exercise_module_transition(token, refresh, pending_invite_id)
        exercise_lifecycle_transition("disabled", "R1A-D")
        exercise_lifecycle_transition("archived", "R1A-X")
    finally:
        v.set_flag("WATHEFNI_EMPLOYEE_APP", False)
        v.set_flag("WATHEFNI_COMPANY_CHANNEL_ACCOUNTS", False)
        v.set_flag("WATHEFNI_ONBOARDING_SEED", False)
        v.set_flag("WATHEFNI_PUSH_NOTIFICATIONS", False)
        v.cleanup()

    production_after = v.production_snapshot()
    protected_after = v.staging_protected_snapshot()
    flags = v.systemd_flags("wathefni-orchestrator-staging.service")
    record(
        "R1A-S1",
        "production and protected staging snapshots remain unchanged",
        production_before.get("sha256") == production_after.get("sha256")
        and protected_before.get("sha256") == protected_after.get("sha256"),
        {
            "production_unchanged": production_before.get("sha256") == production_after.get("sha256"),
            "staging_protected_unchanged": protected_before.get("sha256") == protected_after.get("sha256"),
        },
    )
    record(
        "R1A-S2",
        "protected staging service flags remain off",
        all(v.flag_is_off(flags.get(flag, "unset")) for flag in v.PROTECTED_FLAGS),
        flags,
    )
    passed = sum(1 for check in checks if check["passed"])
    report = {
        "phase": "7E-R1A",
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": checks,
        "recommendation": "r1a-green" if passed == len(checks) else "r1a-blocked",
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    print(f"PHASE 7E-R1A: {passed}/{len(checks)} passed")
    print(f"report={REPORT_PATH}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
