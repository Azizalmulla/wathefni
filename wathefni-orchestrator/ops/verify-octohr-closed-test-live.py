#!/usr/bin/env python3
"""Verify the synthetic closed-test tenant through public production APIs.

Passwords and tokens are read from an owner-only file and are never printed.
The JSON result contains only status/count/isolation evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import requests


COMPANY = "OCTOHR-CLOSED-TEST"
OTHER_TENANT = "OCTOHR-STORE-REVIEW"


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
        return any(_has_data(item) for key, item in value.items() if key not in {"ok", "success"})
    return value not in (None, "", 0, False)


def main() -> int:
    args = _args()
    owner = json.loads(args.owner_file.read_text(encoding="utf-8"))
    identities = owner.get("identities") if isinstance(owner, dict) else None
    if owner.get("company_code") != COMPANY or not isinstance(identities, list) or len(identities) != 15:
        raise SystemExit("invalid owner credential file")
    base = args.base_url.rstrip("/")
    sessions = []
    for row in identities:
        login = requests.post(
            f"{base}/dashboard/mobile/auth/login",
            json={"company_code": COMPANY, "email": row["email"], "password": row["password"]},
            timeout=30,
        )
        payload = _body(login)
        token = str(payload.get("access_token") or "")
        me = requests.get(
            f"{base}/dashboard/mobile/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        ) if token else None
        me_payload = _body(me) if me is not None else {}
        company = str(
            me_payload.get("company_code")
            or (me_payload.get("user") or {}).get("company_code")
            or (me_payload.get("me") or {}).get("company_code")
            or (me_payload.get("principal") or {}).get("company_code")
            or ""
        ).upper()
        sessions.append({
            "login_status": login.status_code,
            "me_status": me.status_code if me is not None else 0,
            "tenant_bound": company == COMPANY,
            "token_present": bool(token),
        })
    first = identities[0]
    wrong_tenant = requests.post(
        f"{base}/dashboard/mobile/auth/login",
        json={"company_code": OTHER_TENANT, "email": first["email"], "password": first["password"]},
        timeout=30,
    )
    review_adapter = requests.post(
        f"{base}/dashboard/mobile/auth/store-review-login",
        json={"username": first["email"], "password": first["password"], "principal": "hr"},
        timeout=30,
    )
    first_login = requests.post(
        f"{base}/dashboard/mobile/auth/login",
        json={"company_code": COMPANY, "email": first["email"], "password": first["password"]},
        timeout=30,
    )
    token = str(_body(first_login).get("access_token") or "")
    headers = {"Authorization": f"Bearer {token}"}
    endpoints = (
        ("home_inbox", "/dashboard/mobile/priorities"),
        ("people", "/dashboard/mobile/employees"),
        ("hiring", "/dashboard/mobile/positions"),
        ("attendance", "/dashboard/mobile/attendance"),
        ("leave", "/dashboard/mobile/leave"),
        ("shifts", "/dashboard/mobile/shifts"),
        ("onboarding", "/dashboard/mobile/onboarding"),
        ("documents", "/dashboard/mobile/documents"),
        ("tasks", "/dashboard/mobile/tasks"),
        ("performance", "/dashboard/mobile/performance"),
    )
    surfaces: dict[str, dict[str, Any]] = {}
    for label, path in endpoints:
        response = requests.get(f"{base}{path}", headers=headers, timeout=45)
        payload = _body(response)
        surfaces[label] = {"status": response.status_code, "has_data": _has_data(payload)}
    role_permissions = requests.get(f"{base}/dashboard/mobile/me", headers=headers, timeout=30)
    permission_payload = _body(role_permissions)
    permissions = set(permission_payload.get("permissions") or (permission_payload.get("user") or {}).get("permissions") or [])
    result = {
        "ok": (
            all(row["login_status"] == 200 and row["me_status"] == 200 and row["tenant_bound"] for row in sessions)
            and wrong_tenant.status_code in {401, 403}
            and review_adapter.status_code in {401, 403}
            and all(row["status"] == 200 and row["has_data"] for row in surfaces.values())
            and "settings.manage" not in permissions
            and "users.manage" not in permissions
        ),
        "identity_count": len(sessions),
        "identity_login_pass": sum(row["login_status"] == 200 for row in sessions),
        "identity_me_pass": sum(row["me_status"] == 200 for row in sessions),
        "tenant_bound_pass": sum(row["tenant_bound"] for row in sessions),
        "wrong_tenant_denied": wrong_tenant.status_code in {401, 403},
        "store_review_adapter_denied": review_adapter.status_code in {401, 403},
        "settings_manage": "settings.manage" in permissions,
        "users_manage": "users.manage" in permissions,
        "surfaces": surfaces,
        "passwords_printed": False,
        "tokens_printed": False,
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
