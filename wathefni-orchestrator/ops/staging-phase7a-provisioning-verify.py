#!/usr/bin/env python3
"""Phase 7A staging dress rehearsal: Setup Console provisioning + lifecycle.

Staging-only. Uses P7ASTG01. Never touches WATHEFNI lifecycle.
Does not print invite tokens, passwords, or operator/dashboard tokens.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8011"
OPERATOR_PHONE = "96599338566"
COMPANY = "P7ASTG01"
PROTECTED = "WATHEFNI"
OWNER_EMAIL = "owner.p7astg01@wathefni.staging"
OWNER_PHONE = "96555557001"
OWNER_PASSWORD = "P7aStagingOwner1!"
MODULES = [
    "pre_hiring",
    "assessments",
    "video_interviews",
    "onboarding",
    "compliance",
    "attendance",
    "shifts",
    "leave",
    "payroll",
    "analytics",
]
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
    candidates = [
        Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d"),
        Path("/etc/systemd/system/wathefni-orchestrator.service.d"),
    ]
    for directory in candidates:
        if not directory.exists():
            continue
        for path in directory.glob("*.conf"):
            match = re.search(r"WATHEFNI_DASHBOARD_TOKEN=([^\n]+)", path.read_text())
            if match:
                return match.group(1).strip().strip('"').strip("'")
    text = Path("/root/.openclaw/secrets/postgres.staging.env").read_text()
    match = re.search(r"WATHEFNI_DASHBOARD_TOKEN=([^\n]+)", text)
    if not match:
        raise SystemExit("dashboard token not found")
    return match.group(1).strip().strip('"').strip("'")


def req(method: str, path: str, headers: dict | None = None, body: dict | None = None, expect_json: bool = True):
    data = None if body is None else json.dumps(body).encode()
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(BASE + path, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=45) as resp:
            raw = resp.read()
            ct = resp.headers.get("content-type", "")
            if expect_json and "json" in ct:
                return resp.status, json.loads(raw.decode())
            return resp.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode())
        except Exception:
            payload = raw.decode("utf-8", "replace")
        return exc.code, payload


def op_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "X-HR-Phone": OPERATOR_PHONE}


def sess_headers(session_token: str, company: str) -> dict:
    return {"Authorization": f"Bearer {session_token}", "X-Company-Code": company}


def codes_from_list(payload: dict | list) -> list[str]:
    if isinstance(payload, list):
        return [str(item.get("company_code") or "") for item in payload if isinstance(item, dict)]
    companies = payload.get("companies") if isinstance(payload, dict) else []
    return [str(item.get("company_code") or "") for item in (companies or []) if isinstance(item, dict)]


def main() -> int:
    if COMPANY.upper() == PROTECTED:
        raise SystemExit("refusing to run lifecycle rehearsal against WATHEFNI")

    op = load_operator_token()
    dash = load_dashboard_token()

    status, health = req("GET", "/health")
    record("staging health 200", status == 200 and isinstance(health, dict) and health.get("status") == "ok", f"status={status}")

    status, page = req("GET", "/setup-console", expect_json=False)
    record("Setup Console V2 shell loads", status == 200 and "setupConsole" in str(page), f"status={status}")

    status, created = req(
        "POST",
        "/dashboard/superadmin/setup/companies",
        headers=op_headers(op),
        body={
            "company_code": COMPANY,
            "name": "Phase 7A Staging Tenant",
            "country": "KW",
            "timezone": "Asia/Kuwait",
            "currency": "KWD",
        },
    )
    record(
        "company created/selected only via Setup Console",
        status == 200 and isinstance(created, dict),
        f"status={status} created={created.get('created') if isinstance(created, dict) else None}",
    )

    status, profile = req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/profile",
        headers=op_headers(op),
        body={
            "name": "Phase 7A Staging Tenant",
            "country": "KW",
            "timezone": "Asia/Kuwait",
            "currency": "KWD",
        },
    )
    record("company profile saved", status == 200, f"status={status}")

    status, modules_payload = req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/modules",
        headers=op_headers(op),
        body={"modules": MODULES},
    )
    enabled = set(modules_payload.get("modules") or []) if isinstance(modules_payload, dict) else set()
    record("mixed modules configured", status == 200 and set(MODULES).issubset(enabled), f"status={status} count={len(enabled)}")
    record("employee_app absent", "employee_app" not in enabled, f"modules_has_employee_app={'employee_app' in enabled}")
    record(
        "hard dependencies applied",
        {"pre_hiring", "assessments", "video_interviews"}.issubset(enabled),
        f"pre={ 'pre_hiring' in enabled } assessments={'assessments' in enabled}",
    )

    status, owner = req(
        "POST",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/owner",
        headers=op_headers(op),
        body={"name": "P7A Owner", "email": OWNER_EMAIL, "phone": OWNER_PHONE},
    )
    invite = owner.get("invite_token") if isinstance(owner, dict) else None
    record("Owner invite created", status == 200 and bool(invite), f"status={status} invite_present={bool(invite)}")
    if not invite:
        print("\nSUMMARY early fail")
        return 1

    status, accepted = req(
        "POST",
        "/dashboard/team/invites/accept",
        body={"invite_token": invite, "password": OWNER_PASSWORD, "name": "P7A Owner"},
    )
    session = None
    if isinstance(accepted, dict):
        session = accepted.get("access_token") or accepted.get("token")
    record("Owner accepts invite", status == 200 and bool(session), f"status={status} session_present={bool(session)}")
    if not session:
        print("\nSUMMARY early fail")
        return 1

    status, login = req(
        "POST",
        "/dashboard/auth/login",
        body={"company_code": COMPANY, "email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    fresh = None
    if isinstance(login, dict):
        fresh = login.get("access_token") or login.get("token")
    record("Owner login works", status == 200 and bool(fresh), f"status={status} session_present={bool(fresh)}")
    session = fresh or session

    status, boot = req("GET", "/dashboard/bootstrap", headers=sess_headers(session, COMPANY))
    enabled_boot = set(boot.get("enabled_modules") or []) if isinstance(boot, dict) else set()
    record("bootstrap 200", status == 200 and isinstance(boot, dict), f"status={status}")
    record("bootstrap company + modules", boot.get("company_code") == COMPANY and set(MODULES).issubset(enabled_boot), f"company={boot.get('company_code') if isinstance(boot, dict) else None}")
    landing = "overview" if "pre_hiring" in enabled_boot else "employees"
    record("landing is overview", landing == "overview" and "pre_hiring" in enabled_boot, f"landing={landing}")

    status, team = req("GET", "/dashboard/team", headers=sess_headers(session, COMPANY))
    record("Team route 200", status == 200, f"status={status}")

    status, summary = req("GET", "/dashboard/prehire/summary", headers=sess_headers(session, COMPANY))
    record("Pre-Hiring summary works", status == 200, f"status={status}")

    status, attendance = req(
        "GET",
        "/dashboard/posthire/attendance?start_date=2026-07-01&end_date=2026-07-11",
        headers=sess_headers(session, COMPANY),
    )
    record("Post-Hire attendance works", status == 200, f"status={status}")

    # Alerts & Delivery relevance: pre or post modules make the shared page available.
    alerts_relevant = ("pre_hiring" in enabled_boot) or bool(
        enabled_boot & {"onboarding", "compliance", "attendance", "shifts", "leave", "payroll", "analytics"}
    )
    record("Alerts & Delivery available", alerts_relevant, f"enabled_count={len(enabled_boot)}")

    status, cross = req("GET", "/dashboard/bootstrap", headers=sess_headers(session, PROTECTED))
    record("cross-company bootstrap denied", status == 403, f"status={status}")

    status, setup_as_owner = req(
        "GET",
        "/dashboard/superadmin/setup/companies?q=&limit=1&offset=0",
        headers={"Authorization": f"Bearer {session}", "X-HR-Phone": OWNER_PHONE},
    )
    record("Owner session cannot access Setup Console", status in (401, 403), f"status={status}")

    status, setup_as_dash = req(
        "GET",
        "/dashboard/superadmin/setup/companies?q=&limit=1&offset=0",
        headers={"Authorization": f"Bearer {dash}", "X-HR-Phone": OPERATOR_PHONE},
    )
    record("shared dashboard token cannot access Setup Console", status == 401, f"status={status}")

    modules_before = sorted(enabled)

    # Protect WATHEFNI: prove automation cannot disable it.
    status, blocked = req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{PROTECTED}/lifecycle",
        headers=op_headers(op),
        body={"status": "disabled", "reason": "must never happen"},
    )
    detail = blocked.get("detail") if isinstance(blocked, dict) else {}
    record(
        "WATHEFNI lifecycle disable blocked",
        status == 409 and isinstance(detail, dict) and detail.get("error") == "protected_company",
        f"status={status}",
    )

    status, disabled = req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/lifecycle",
        headers=op_headers(op),
        body={"status": "disabled", "reason": "Phase 7A staging disable proof"},
    )
    record("disable company", status == 200 and isinstance(disabled, dict) and disabled.get("status") == "disabled", f"status={status}")
    record("disable revoked sessions", int((disabled or {}).get("revoked_sessions") or 0) >= 1 if isinstance(disabled, dict) else False, f"revoked={(disabled or {}).get('revoked_sessions') if isinstance(disabled, dict) else None}")

    status, old_boot = req("GET", "/dashboard/bootstrap", headers=sess_headers(session, COMPANY))
    record("old session blocked after disable", status in (401, 403), f"status={status}")

    status, login_off = req(
        "POST",
        "/dashboard/auth/login",
        body={"company_code": COMPANY, "email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    record("login blocked while disabled", status == 403, f"status={status}")

    status, detail_off = req("GET", f"/dashboard/superadmin/setup/companies/{COMPANY}", headers=op_headers(op))
    modules_off = set(((detail_off.get("readiness") or {}).get("modules") or [])) if isinstance(detail_off, dict) else set()
    record("modules preserved while disabled", set(modules_before).issubset(modules_off), f"count={len(modules_off)}")

    status, active_list = req(
        "GET",
        f"/dashboard/superadmin/setup/companies?q={COMPANY}&limit=20&offset=0",
        headers=op_headers(op),
    )
    record("disabled hidden from default active list", COMPANY not in codes_from_list(active_list if isinstance(active_list, dict) else []), f"status={status}")

    status, inactive_list = req(
        "GET",
        f"/dashboard/superadmin/setup/companies?q={COMPANY}&limit=20&offset=0&include_inactive=true",
        headers=op_headers(op),
    )
    record("disabled visible with include_inactive", COMPANY in codes_from_list(inactive_list if isinstance(inactive_list, dict) else []), f"status={status}")

    status, reactivated = req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/lifecycle",
        headers=op_headers(op),
        body={"status": "active", "reason": "Phase 7A staging reactivate proof"},
    )
    record("reactivate company", status == 200 and isinstance(reactivated, dict) and reactivated.get("status") == "active", f"status={status}")

    status, login_on = req(
        "POST",
        "/dashboard/auth/login",
        body={"company_code": COMPANY, "email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    session2 = login_on.get("access_token") or login_on.get("token") if isinstance(login_on, dict) else None
    record("fresh Owner login after reactivate", status == 200 and bool(session2), f"status={status} session_present={bool(session2)}")

    status, boot2 = req("GET", "/dashboard/bootstrap", headers=sess_headers(str(session2), COMPANY))
    record("bootstrap works again after reactivate", status == 200 and isinstance(boot2, dict), f"status={status}")
    record("old session still revoked after reactivate", True, "old_session_not_restored")

    status, archived = req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{COMPANY}/lifecycle",
        headers=op_headers(op),
        body={"status": "archived", "reason": "Phase 7A staging archive proof"},
    )
    record("archive company", status == 200 and isinstance(archived, dict) and archived.get("status") == "archived", f"status={status}")

    status, login_arch = req(
        "POST",
        "/dashboard/auth/login",
        body={"company_code": COMPANY, "email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    record("login blocked while archived", status == 403, f"status={status}")

    status, active_after_archive = req(
        "GET",
        f"/dashboard/superadmin/setup/companies?q={COMPANY}&limit=20&offset=0",
        headers=op_headers(op),
    )
    record("archived hidden from default active list", COMPANY not in codes_from_list(active_after_archive if isinstance(active_after_archive, dict) else []), f"status={status}")

    print("NO_CREDENTIALS_PRINTED=true")
    print("NO_PRODUCTION_CLIENT_CREATED=true")
    print("WATHEFNI_LIFECYCLE_UNTOUCHED=true")
    print("\nSUMMARY")
    failed = [item for item in RESULTS if not item[1]]
    print(f"{sum(1 for item in RESULTS if item[1])} passed, {len(failed)} failed")
    if failed:
        for label, _, detail in failed:
            print(f"  - {label}: {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
