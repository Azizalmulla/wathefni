#!/usr/bin/env python3
"""Verify the four fixed store-review identities through production APIs.

Credentials are read from an owner-only file. Passwords and bearer tokens are
never included in output. This proves server-side identity, tenant, principal,
and representative-data isolation; it does not claim physical-device UI PASS.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import requests


COMPANY = "OCTOHR-STORE-REVIEW"
EXPECTED = {
    ("apple", "employee"),
    ("apple", "hr"),
    ("google", "employee"),
    ("google", "hr"),
}


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://api.octo-hr.com")
    parser.add_argument("--owner-file", type=Path, required=True)
    return parser.parse_args()


def _body(response: requests.Response) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {"items": value}


def _has_data(value: Any) -> bool:
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return any(
            _has_data(item)
            for key, item in value.items()
            if key not in {"ok", "success", "review_access"}
        )
    return value not in (None, "", 0, False)


def _error_code(payload: dict[str, Any]) -> str | None:
    detail = payload.get("detail")
    if isinstance(detail, dict):
        return str(detail.get("error") or "") or None
    return str(payload.get("error") or "") or None


def _company(payload: dict[str, Any]) -> str:
    return str(
        payload.get("company_code")
        or (payload.get("user") or {}).get("company_code")
        or (payload.get("me") or {}).get("company_code")
        or (payload.get("principal") or {}).get("company_code")
        or (payload.get("employee") or {}).get("company_code")
        or ""
    ).upper()


def _subject(payload: dict[str, Any]) -> str:
    return str(
        payload.get("employee_key")
        or payload.get("user_id")
        or (payload.get("user") or {}).get("user_id")
        or (payload.get("me") or {}).get("user_id")
        or (payload.get("principal") or {}).get("user_id")
        or (payload.get("principal") or {}).get("employee_key")
        or (payload.get("employee") or {}).get("employee_key")
        or ""
    )


def _identity_rows(owner: dict[str, Any]) -> list[dict[str, str]]:
    rows = owner.get("identities") if isinstance(owner, dict) else None
    if owner.get("company_code") != COMPANY or not isinstance(rows, list):
        raise SystemExit("invalid owner credential file")
    normalized: list[dict[str, str]] = []
    for item in rows:
        row = item if isinstance(item, dict) else {}
        normalized.append(
            {
                "store": str(row.get("store") or "").lower(),
                "principal": str(row.get("principal") or "").lower(),
                "username": str(row.get("username") or row.get("email") or "").lower(),
                "password": str(row.get("password") or ""),
            }
        )
    matrix = {(row["store"], row["principal"]) for row in normalized}
    if matrix != EXPECTED or any(not row["username"] or not row["password"] for row in normalized):
        raise SystemExit("invalid reviewer identity matrix")
    return normalized


def main() -> int:
    args = _args()
    identities = _identity_rows(json.loads(args.owner_file.read_text(encoding="utf-8")))
    base = args.base_url.rstrip("/")
    availability = requests.get(f"{base}/auth/store-review-availability", timeout=30)
    availability_payload = _body(availability)
    sessions: list[dict[str, Any]] = []
    subject_ids: set[str] = set()
    employee_headers: dict[str, str] | None = None
    hr_headers: dict[str, str] | None = None

    for row in identities:
        principal = row["principal"]
        prefix = "/app" if principal == "employee" else "/dashboard/mobile"
        login = requests.post(
            f"{base}{prefix}/auth/store-review-login",
            json={"username": row["username"], "password": row["password"], "platform": row["store"]},
            timeout=30,
        )
        payload = _body(login)
        token = str(payload.get("token") or payload.get("access_token") or "")
        headers = {"Authorization": f"Bearer {token}"}
        me = requests.get(f"{base}{prefix}/me", headers=headers, timeout=30) if token else None
        me_payload = _body(me) if me is not None else {}
        subject = _subject(me_payload) or _subject(payload)
        if subject:
            subject_ids.add(subject)
        wrong_prefix = "/dashboard/mobile" if principal == "employee" else "/app"
        wrong = requests.post(
            f"{base}{wrong_prefix}/auth/store-review-login",
            json={"username": row["username"], "password": row["password"], "platform": row["store"]},
            timeout=30,
        )
        sessions.append(
            {
                "store": row["store"],
                "principal": principal,
                "login_status": login.status_code,
                "review_access": payload.get("review_access") is True,
                "me_status": me.status_code if me is not None else 0,
                "tenant_bound": _company(me_payload) == COMPANY,
                "subject_present": bool(subject),
                "wrong_principal_denied": wrong.status_code in {401, 403},
            }
        )
        if token and principal == "employee" and employee_headers is None:
            employee_headers = headers
        if token and principal == "hr" and hr_headers is None:
            hr_headers = headers

    arbitrary = requests.post(
        f"{base}/app/auth/store-review-login",
        json={"username": "unknown@review.octo-hr.com", "password": "not-a-valid-review-password"},
        timeout=30,
    )
    employee_endpoints = (
        ("home", "/app/home"),
        ("schedule", "/app/schedule/history"),
        ("attendance", "/app/attendance"),
        ("leave", "/app/leave"),
        ("payslips", "/app/payslips"),
        ("documents", "/app/documents"),
        ("onboarding", "/app/onboarding"),
        ("performance", "/app/performance"),
        ("talent", "/app/talent"),
        ("learning", "/app/learning"),
        ("benefits", "/app/benefits"),
        ("engagement", "/app/engagement"),
    )
    hr_endpoints = (
        ("home_inbox", "/dashboard/mobile/priorities"),
        ("attendance", "/dashboard/mobile/attendance"),
        ("leave", "/dashboard/mobile/leave"),
        ("shifts", "/dashboard/mobile/shifts"),
        ("onboarding", "/dashboard/mobile/onboarding"),
        ("documents", "/dashboard/mobile/documents"),
        ("tasks", "/dashboard/mobile/tasks"),
        ("performance", "/dashboard/mobile/performance"),
    )
    surfaces: dict[str, dict[str, Any]] = {}
    for principal, headers, endpoints in (
        ("employee", employee_headers, employee_endpoints),
        ("hr", hr_headers, hr_endpoints),
    ):
        for label, path in endpoints:
            response = requests.get(f"{base}{path}", headers=headers or {}, timeout=45)
            payload = _body(response)
            surfaces[f"{principal}.{label}"] = {
                "status": response.status_code,
                "has_data": _has_data(payload),
                "error_code": _error_code(payload),
            }

    sessions_ok = all(
        row["login_status"] == 200
        and row["review_access"]
        and row["me_status"] == 200
        and row["tenant_bound"]
        and row["subject_present"]
        and row["wrong_principal_denied"]
        for row in sessions
    )
    surfaces_ok = all(row["status"] == 200 and row["has_data"] for row in surfaces.values())
    result = {
        "ok": (
            availability.status_code == 200
            and availability_payload.get("available") is True
            and sessions_ok
            and len(subject_ids) == 4
            and arbitrary.status_code in {401, 403}
            and surfaces_ok
        ),
        "kill_switch_on": availability_payload.get("available") is True,
        "identity_count": len(sessions),
        "identity_login_pass": sum(row["login_status"] == 200 for row in sessions),
        "identity_me_pass": sum(row["me_status"] == 200 for row in sessions),
        "tenant_bound_pass": sum(row["tenant_bound"] for row in sessions),
        "wrong_principal_denied_pass": sum(row["wrong_principal_denied"] for row in sessions),
        "distinct_subject_count": len(subject_ids),
        "arbitrary_identity_denied": arbitrary.status_code in {401, 403},
        "surfaces": surfaces,
        "physical_exact_binary_claimed": False,
        "passwords_printed": False,
        "tokens_printed": False,
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
