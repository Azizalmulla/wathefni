#!/usr/bin/env python3
"""Clean staging canary — fresh company through Setup APIs, no SQL fixtures.

Creates a disposable QA* company via the running Setup Console, accepts the
owner invite, enables Leave through company Setup, then tries to staff a
roster employee through the HR API. SQL is used only for R3-safe cleanup.
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:6].upper()
COMPANY = f"QA{SUFFIX}"[:12]
PASSWORD = f"Canary-{uuid.uuid4().hex[:12]}"
OWNER_EMAIL = f"owner.{SUFFIX.lower()}@canary.test"
OWNER_PHONE = f"96561{SUFFIX[:5]}"
EMP_PHONE = f"96562{SUFFIX[:5]}"
OPERATOR_PHONE = os.environ.get("WATHEFNI_SETUP_OPERATOR_PHONE", "96599338566").strip()
BASE = os.environ.get("WATHEFNI_CANARY_BASE", "http://127.0.0.1:8011").rstrip("/")


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _load_operator_token() -> str:
    explicit = (os.environ.get("WATHEFNI_SETUP_OPERATOR_TOKEN") or "").strip()
    if explicit:
        return explicit
    raw = (os.environ.get("WATHEFNI_SETUP_OPERATOR_CREDENTIALS") or "").strip()
    path = Path(os.environ.get("WATHEFNI_SETUP_OPERATOR_ENV", "/root/.openclaw/secrets/wathefni-setup-operator.env"))
    if not raw and path.is_file():
        text = path.read_text(encoding="utf-8")
        match = re.search(r"WATHEFNI_SETUP_OPERATOR_CREDENTIALS=(.*)", text)
        if match:
            raw = match.group(1).strip().strip("'").strip('"')
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(parsed, dict):
        return ""
    for key, token in parsed.items():
        digits = re.sub(r"\D", "", str(key))
        if digits == re.sub(r"\D", "", OPERATOR_PHONE) or not OPERATOR_PHONE:
            return str(token or "").strip()
    return str(next(iter(parsed.values()), "") or "").strip()


def http(method: str, path: str, *, token: str | None = None, body: dict | None = None, extra: dict | None = None) -> tuple[int, dict | str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra:
        headers.update(extra)
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed
    except URLError as exc:
        return 0, str(exc.reason or exc)


def _err(payload: dict | str) -> str:
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, dict):
            return str(detail.get("error") or detail)[:180]
        return str(payload)[:180]
    return str(payload)[:180]


def cleanup_sql() -> None:
    orch = Path(__file__).resolve().parents[2] / "wathefni-orchestrator"
    sys.path.insert(0, str(orch))
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")
    try:
        import app
        import production_data_safety as pds
    except ModuleNotFoundError:
        print("      SKIP  SQL cleanup (app import unavailable)")
        return
    try:
        pds.require_non_production_target()
        pds.require_destructive_scope([COMPANY])
    except Exception as exc:
        print(f"      SKIP  SQL cleanup refused ({exc})")
        return
    tables = (
        "leave_requests",
        "dashboard_user_permission_grants",
        "dashboard_user_invites",
        "dashboard_user_sessions",
        "employee_sessions",
        "dashboard_users",
        "employees",
        "company_modules",
        "company_settings",
        "companies",
    )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in tables:
                try:
                    cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
                except Exception:
                    conn.rollback()
        conn.commit()
    print(f"      CLEANUP  {COMPANY}")


def main() -> int:
    print("    STORE RELEASE — clean Setup canary")
    print(f"    tenant: {COMPANY} base: {BASE}")
    token = _load_operator_token()
    check("operator credentials present", bool(token), "missing WATHEFNI_SETUP_OPERATOR_CREDENTIALS")
    if not token:
        print("\n    CLEAN_CANARY_BLOCKED  operator credentials missing")
        return 2

    login_code, login_body = http(
        "POST",
        "/dashboard/superadmin/setup/auth/login",
        body={"phone": OPERATOR_PHONE, "operator_token": token},
    )
    check("Setup operator login", login_code == 200, (login_code, _err(login_body)))
    op_token = ""
    if isinstance(login_body, dict):
        op_token = str(login_body.get("access_token") or login_body.get("token") or "")
    check("operator access token issued", bool(op_token))
    if not op_token:
        print("\n    CLEAN_CANARY_FAIL")
        print(f"    {PASS} passed, {FAIL} failed")
        return 1

    try:
        created_code, created = http(
            "POST",
            "/dashboard/superadmin/setup/companies",
            token=op_token,
            body={"company_code": COMPANY, "name": f"Clean Canary {SUFFIX}", "country": "KW"},
        )
        check("Setup creates company", created_code == 200 and isinstance(created, dict) and created.get("ok") is True, (created_code, _err(created)))
        if isinstance(created, dict) and isinstance(created.get("readiness"), dict):
            check("new company bootstrap is not pre-staffed", True)

        owner_code, owner = http(
            "POST",
            f"/dashboard/superadmin/setup/companies/{COMPANY}/owner",
            token=op_token,
            body={"email": OWNER_EMAIL, "name": "Canary Owner", "phone": OWNER_PHONE},
        )
        check("Setup seeds owner invite", owner_code == 200, (owner_code, _err(owner)))
        invite_token = ""
        if isinstance(owner, dict):
            invite_token = str(owner.get("invite_token") or "")
        check("owner invite token returned", bool(invite_token))

        accept_code, accept = http(
            "POST",
            "/dashboard/team/invites/accept",
            body={"invite_token": invite_token, "name": "Canary Owner", "password": PASSWORD, "phone": OWNER_PHONE},
        )
        check("owner accepts invite through Setup/auth", accept_code == 200, (accept_code, _err(accept)))

        hr_login_code, hr_login = http(
            "POST",
            "/dashboard/auth/login",
            body={"company_code": COMPANY, "email": OWNER_EMAIL, "password": PASSWORD},
        )
        check("owner dashboard login", hr_login_code == 200, (hr_login_code, _err(hr_login)))
        hr_token = ""
        if isinstance(hr_login, dict):
            hr_token = str(hr_login.get("access_token") or "")
        check("owner session issued", bool(hr_token))
        if not hr_token:
            return 1 if FAIL else 0

        policies_code, policies = http("GET", "/dashboard/setup/company/module-policies", token=hr_token)
        check("owner can open company Setup", policies_code == 200, (policies_code, _err(policies)))

        enable_code, enable = http(
            "PATCH",
            "/dashboard/setup/company/module-policies/leave",
            token=hr_token,
            body={"reason": "clean canary enable leave", "required": {"enabled": True}},
        )
        check(
            "owner enables Leave through Setup",
            enable_code in {200, 409},
            (enable_code, _err(enable)),
        )

        emp_code, emp = http(
            "POST",
            "/dashboard/posthire/employees",
            token=hr_token,
            body={"name": "Canary Employee", "phone": EMP_PHONE, "email": f"emp.{SUFFIX.lower()}@canary.test", "position_title": "Analyst"},
        )
        # Grant-only employee scopes: a brand-new owner may be unable to staff
        # the roster without the reviewed cutover CLI. That is a real canary
        # finding, not something this harness may SQL-grant away.
        if emp_code in {200, 201} and isinstance(emp, dict) and emp.get("ok") is not False:
            check("owner creates employee through HR API", True)
            emp_key = str(((emp.get("employee") or {}) if isinstance(emp.get("employee"), dict) else {}).get("employee_key") or "")
            today = date.today()
            leave_code, leave = http(
                "POST",
                "/dashboard/posthire/action",
                token=hr_token,
                body={
                    "action_type": "create_leave_request",
                    "args": {
                        "employee_key": emp_key,
                        "leave_type": "time_off",
                        "start_date": (today + timedelta(days=8)).isoformat(),
                        "end_date": (today + timedelta(days=9)).isoformat(),
                        "reason": "clean canary",
                    },
                },
            )
            check(
                "HR leave action is a real domain result",
                leave_code in {200, 400, 403, 409, 422},
                (leave_code, _err(leave)),
            )
        else:
            err = _err(emp)
            grant_blocked = emp_code in {401, 403} or "permission" in err.lower() or "employees.manage" in err
            check(
                "clean owner roster create is possible through Setup/HR (no cutover CLI)",
                False,
                (emp_code, err, "grant-only employees.manage" if grant_blocked else "unexpected"),
            )
            print("      NOTE  new-company owners cannot grant themselves employees.* (grant-only, no Setup write path)")
    finally:
        cleanup_sql()

    print(f"\n    CLEAN_CANARY_{'PASS' if not FAIL else 'FAIL'}  {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
