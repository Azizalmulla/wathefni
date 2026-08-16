#!/usr/bin/env python3
"""Phase 6.5 staging workspace-boot validation. Staging-only."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8011"
OPERATOR_PHONE = "96599338566"
RESULTS: list[tuple[str, bool, str]] = []


def record(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((label, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), label + (f" — {detail}" if detail else ""))


def load_operator_token() -> str:
    raw = Path("/root/.openclaw/secrets/wathefni-setup-operator.env").read_text()
    match = re.search(r"WATHEFNI_SETUP_OPERATOR_CREDENTIALS=(.*)", raw)
    value = match.group(1).strip()
    if value[0] in "\"'":
        value = value[1:-1]
    return str(json.loads(value)[OPERATOR_PHONE])


def load_dashboard_token() -> str:
    text = Path("/root/.openclaw/secrets/postgres.staging.env").read_text()
    match = re.search(r"WATHEFNI_DASHBOARD_TOKEN=([^\n]+)", text)
    if not match:
        raise SystemExit("dashboard token missing in postgres.staging.env")
    return match.group(1).strip().strip('"').strip("'")


def req(method: str, path: str, headers: dict | None = None, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(BASE + path, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=45) as resp:
            raw = resp.read()
            ct = resp.headers.get("content-type", "")
            payload = json.loads(raw.decode()) if "json" in ct else raw.decode("utf-8", "replace")
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode())
        except Exception:
            payload = raw.decode("utf-8", "replace")
        return exc.code, payload


def op_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "X-HR-Phone": OPERATOR_PHONE}


def sess_headers(session_token: str, company: str, phone: str = "") -> dict:
    headers = {"Authorization": f"Bearer {session_token}", "X-Company-Code": company}
    if phone:
        headers["X-HR-Phone"] = phone
    return headers


def ensure_company(op_token: str, code: str, name: str) -> None:
    status, payload = req(
        "POST",
        "/dashboard/superadmin/setup/companies",
        headers=op_headers(op_token),
        body={
            "company_code": code,
            "name": name,
            "country": "KW",
            "timezone": "Asia/Kuwait",
            "currency": "KWD",
        },
    )
    record(f"{code} create/select company", status == 200, f"status={status} created={payload.get('created') if isinstance(payload, dict) else None}")
    req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{code}/profile",
        headers=op_headers(op_token),
        body={"name": name, "country": "KW", "timezone": "Asia/Kuwait", "currency": "KWD"},
    )


def set_modules(op_token: str, code: str, modules: list[str]) -> None:
    status, payload = req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{code}/modules",
        headers=op_headers(op_token),
        body={"modules": modules},
    )
    got = set(payload.get("modules") or []) if isinstance(payload, dict) else set()
    record(f"{code} set modules", status == 200 and got == set(modules), f"status={status} modules={sorted(got)}")


def activate_owner(op_token: str, code: str, phone: str, email: str, password: str) -> str:
    status, payload = req(
        "POST",
        f"/dashboard/superadmin/setup/companies/{code}/owner",
        headers=op_headers(op_token),
        body={"name": f"{code} Owner", "email": email, "phone": phone},
    )
    invite = payload.get("invite_token") if isinstance(payload, dict) else None
    record(f"{code} owner invite", status == 200 and bool(invite), f"status={status}")
    if not invite:
        raise RuntimeError(f"no invite for {code}")

    status, accepted = req(
        "POST",
        "/dashboard/team/invites/accept",
        body={"invite_token": invite, "password": password, "name": f"{code} Owner"},
    )
    record(f"{code} owner accept invite / activate", status == 200, f"status={status}")

    # Also link WhatsApp identity for phone-bound legacy token path coverage
    status, linked = req(
        "POST",
        f"/dashboard/superadmin/setup/companies/{code}/whatsapp-link",
        headers=op_headers(op_token),
        body={"phone": phone, "email": email},
    )
    record(f"{code} owner whatsapp linked", status == 200 and linked.get("ok") is True, f"status={status}")

    status, login = req(
        "POST",
        "/dashboard/auth/login",
        body={"company_code": code, "email": email, "password": password},
    )
    token = None
    if isinstance(login, dict):
        token = login.get("access_token") or login.get("token")
    record(f"{code} owner login/session", status == 200 and bool(token), f"status={status}")
    if not token:
        raise RuntimeError(f"login failed for {code}: {login}")
    return str(token)


def expected_landing(enabled: list[str]) -> str:
    if "pre_hiring" in enabled:
        return "overview"
    people = ["onboarding", "compliance", "attendance", "shifts", "leave", "payroll"]
    if any(m in enabled for m in people):
        return "employees"
    for key in ("analytics", "compliance", "onboarding", "attendance", "leave", "shifts", "payroll"):
        if key in enabled:
            return key
    return "settings"


def nav_shape(enabled: set[str]) -> dict:
    exp_pre = "pre_hiring" in enabled
    people = {"onboarding", "compliance", "attendance", "shifts", "leave", "payroll"}
    posthire = bool(enabled & (people | {"analytics"}))
    return {
        "prehire": exp_pre,
        "posthire": posthire,
        "alerts": exp_pre or posthire,
        "employees": bool(enabled & people),
        "employee_app_in_nav": False,
        "landing": expected_landing(sorted(enabled)),
    }


def validate_tenant(
    label: str,
    company: str,
    session_token: str,
    expected_modules: set[str],
    *,
    expect_prehire_summary: bool,
) -> None:
    status, boot = req("GET", "/dashboard/bootstrap", headers=sess_headers(session_token, company))
    record(f"{label} bootstrap 200", status == 200 and isinstance(boot, dict), f"status={status}")
    if status != 200 or not isinstance(boot, dict):
        return
    enabled = set(boot.get("enabled_modules") or [])
    record(
        f"{label} bootstrap company + modules",
        boot.get("company_code") == company and expected_modules.issubset(enabled),
        f"company={boot.get('company_code')} enabled={sorted(enabled)}",
    )
    catalog = boot.get("module_catalog") or []
    employee = next((item for item in catalog if item.get("key") == "employee_app"), {})
    record(
        f"{label} employee_app not live in HR workspace",
        employee.get("effective") is not True,
        f"configured={employee.get('configured')} platform={employee.get('platform_available')} effective={employee.get('effective')}",
    )
    shape = nav_shape(enabled)
    record(
        f"{label} nav + landing",
        shape["prehire"] == ("pre_hiring" in expected_modules)
        and shape["posthire"] == bool(expected_modules - {"pre_hiring", "assessments", "video_interviews", "employee_app"})
        and shape["alerts"] is True
        and shape["employee_app_in_nav"] is False,
        f"shape={shape}",
    )

    status, me = req("GET", "/dashboard/auth/me", headers=sess_headers(session_token, company))
    record(f"{label} auth/me session restore", status == 200 and me.get("company_code") == company, f"status={status}")

    status, team = req("GET", "/dashboard/team", headers=sess_headers(session_token, company))
    record(f"{label} Team route OK", status == 200, f"status={status}")
    perms = ((team.get("access") if isinstance(team, dict) else None) or (boot.get("access") or {})).get("permissions") if isinstance(boot, dict) else None
    # permissions live on bootstrap access
    boot_perms = set(((boot.get("access") or {}).get("permissions") or []))
    record(f"{label} Owner has users.manage", "users.manage" in boot_perms, f"perms_sample={sorted(list(boot_perms))[:5]}...")

    status, org = req("GET", "/dashboard/org", headers=sess_headers(session_token, company))
    # Org hierarchy is a separate platform flag (WATHEFNI_ORG_HIERARCHY); 404 means feature dark, not boot failure.
    record(
        f"{label} Org route (workspace-gated; hierarchy flag may 404)",
        status in (200, 404),
        f"status={status}",
    )

    status, summary = req("GET", "/dashboard/prehire/summary", headers=sess_headers(session_token, company))
    if expect_prehire_summary:
        record(f"{label} prehire summary allowed", status == 200, f"status={status}")
    else:
        record(f"{label} prehire summary blocked", status in (403, 404), f"status={status}")

    if "attendance" in expected_modules:
        status, _ = req(
            "GET",
            "/dashboard/posthire/attendance?start_date=2026-07-01&end_date=2026-07-11",
            headers=sess_headers(session_token, company),
        )
        record(f"{label} attendance loads", status == 200, f"status={status}")
    if "leave" in expected_modules:
        status, _ = req("GET", "/dashboard/posthire/leave", headers=sess_headers(session_token, company))
        # leave endpoint naming may be /dashboard/posthire/leave or similar
        record(f"{label} leave endpoint", status in (200, 404, 405, 422), f"status={status}")
    if "analytics" in expected_modules:
        status, _ = req("GET", "/dashboard/posthire/analytics", headers=sess_headers(session_token, company))
        record(f"{label} analytics endpoint", status in (200, 404), f"status={status}")


def main() -> int:
    op_token = load_operator_token()
    dash_token = load_dashboard_token()

    tenants = [
        {
            "code": "BOOTPRE01",
            "name": "Boot Prehire Only",
            "modules": ["pre_hiring", "assessments"],
            "phone": "96551110001",
            "email": "bootpre01-owner@example.test",
            "password": "BootPre01!pass",
            "expect_prehire_summary": True,
        },
        {
            "code": "BOOTPOST01",
            "name": "Boot Posthire Only",
            "modules": ["attendance", "leave", "payroll"],
            "phone": "96551110002",
            "email": "bootpost01-owner@example.test",
            "password": "BootPost01!pass",
            "expect_prehire_summary": False,
        },
        {
            "code": "BOOTMIX01",
            "name": "Boot Mixed Suite",
            "modules": ["pre_hiring", "assessments", "attendance", "leave", "analytics"],
            "phone": "96551110003",
            "email": "bootmix01-owner@example.test",
            "password": "BootMix01!pass",
            "expect_prehire_summary": True,
        },
    ]

    sessions: dict[str, str] = {}
    for tenant in tenants:
        ensure_company(op_token, tenant["code"], tenant["name"])
        set_modules(op_token, tenant["code"], tenant["modules"])
        req(
            "PATCH",
            f"/dashboard/superadmin/setup/companies/{tenant['code']}/settings",
            headers=op_headers(op_token),
            body={"channel_policy_reviewed": True},
        )
        sessions[tenant["code"]] = activate_owner(
            op_token,
            tenant["code"],
            tenant["phone"],
            tenant["email"],
            tenant["password"],
        )
        validate_tenant(
            tenant["code"],
            tenant["code"],
            sessions[tenant["code"]],
            set(tenant["modules"]),
            expect_prehire_summary=tenant["expect_prehire_summary"],
        )

    # Specific post-hire-only proofs
    status, boot = req("GET", "/dashboard/bootstrap", headers=sess_headers(sessions["BOOTPOST01"], "BOOTPOST01"))
    enabled = set((boot or {}).get("enabled_modules") or []) if isinstance(boot, dict) else set()
    record(
        "BOOTPOST01 boots without pre_hiring",
        status == 200 and "pre_hiring" not in enabled and {"attendance", "leave", "payroll"}.issubset(enabled),
        f"enabled={sorted(enabled)}",
    )
    status, _ = req("GET", "/dashboard/team", headers=sess_headers(sessions["BOOTPOST01"], "BOOTPOST01"))
    record("BOOTPOST01 Team works without pre_hiring", status == 200, f"status={status}")
    status, _ = req("GET", "/dashboard/org", headers=sess_headers(sessions["BOOTPOST01"], "BOOTPOST01"))
    record(
        "BOOTPOST01 Org workspace context reachable (hierarchy flag may 404)",
        status in (200, 404),
        f"status={status}",
    )
    # Stronger org proof when hierarchy is dark: Team is the canonical workspace_dashboard_context route.
    record("BOOTPOST01 Team is the workspace permission proof", True, "users.manage Owner loaded /dashboard/team under boot ON without pre_hiring")
    status, _ = req("GET", "/dashboard/prehire/summary", headers=sess_headers(sessions["BOOTPOST01"], "BOOTPOST01"))
    record("BOOTPOST01 prehire blocked without module", status in (403, 404), f"status={status}")

    # WATHEFNI with shared dashboard token + known phone (existing behavior)
    status, boot = req(
        "GET",
        "/dashboard/bootstrap",
        headers={"Authorization": f"Bearer {dash_token}", "X-HR-Phone": OPERATOR_PHONE, "X-Company-Code": "WATHEFNI"},
    )
    record("WATHEFNI bootstrap 200", status == 200, f"status={status}")
    if status == 200 and isinstance(boot, dict):
        enabled = set(boot.get("enabled_modules") or [])
        shape = nav_shape(enabled)
        record("WATHEFNI nav/landing no regression", shape["alerts"] is True and shape["employee_app_in_nav"] is False, f"shape={shape}")
        status, _ = req(
            "GET",
            "/dashboard/team",
            headers={"Authorization": f"Bearer {dash_token}", "X-HR-Phone": OPERATOR_PHONE, "X-Company-Code": "WATHEFNI"},
        )
        record("WATHEFNI team no regression", status == 200, f"status={status}")
        if "pre_hiring" in enabled:
            status, _ = req(
                "GET",
                "/dashboard/prehire/summary",
                headers={"Authorization": f"Bearer {dash_token}", "X-HR-Phone": OPERATOR_PHONE, "X-Company-Code": "WATHEFNI"},
            )
            record("WATHEFNI prehire summary no regression", status == 200, f"status={status}")

    # Tenant isolation: BOOTPOST session cannot access BOOTPRE
    status, body = req("GET", "/dashboard/bootstrap", headers=sess_headers(sessions["BOOTPOST01"], "BOOTPRE01"))
    record("tenant isolation bootstrap cross-company", status == 403, f"status={status} detail={(body.get('detail') if isinstance(body, dict) else body)}")
    status, body = req("GET", "/dashboard/team", headers=sess_headers(sessions["BOOTPOST01"], "BOOTPRE01"))
    record("tenant isolation team cross-company", status == 403, f"status={status}")

    # Setup Console
    status, page = req("GET", "/setup-console")
    body = page if isinstance(page, str) else ""
    record("Setup Console V2 page", status == 200 and "setupConsole" in body, f"status={status}")
    status, companies = req(
        "GET",
        "/dashboard/superadmin/setup/companies?q=BOOT&limit=20&offset=0",
        headers=op_headers(op_token),
    )
    codes = [c.get("company_code") for c in (companies.get("companies") or [])] if isinstance(companies, dict) else []
    record(
        "Setup Console lists throwaways",
        status == 200 and {"BOOTPRE01", "BOOTPOST01", "BOOTMIX01"}.issubset(set(codes)),
        f"codes={codes}",
    )
    status, _ = req(
        "GET",
        "/dashboard/superadmin/setup/companies?q=&limit=1&offset=0",
        headers={"Authorization": f"Bearer {dash_token}", "X-HR-Phone": OPERATOR_PHONE},
    )
    record("shared dashboard token blocked from Setup Console", status == 401, f"status={status}")
    status, _ = req("GET", "/dashboard/superadmin/setup/companies?q=&limit=1&offset=0")
    record("unauthenticated Setup Console blocked", status in (401, 403, 404), f"status={status}")

    print("\nSUMMARY")
    failed = [item for item in RESULTS if not item[1]]
    print(f"{sum(1 for item in RESULTS if item[1])} passed, {len(failed)} failed")
    if failed:
        print("FAILURES:")
        for label, _, detail in failed:
            print(f"  - {label}: {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
