#!/usr/bin/env python3
"""Prove workspace boot OFF rollback, then caller restores ON."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8011"


def dash_token() -> str:
    text = Path("/root/.openclaw/secrets/postgres.staging.env").read_text()
    return re.search(r"WATHEFNI_DASHBOARD_TOKEN=([^\n]+)", text).group(1).strip().strip('"').strip("'")


def req(method: str, path: str, headers: dict | None = None, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    request = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def main() -> None:
    token = dash_token()
    status, body = req(
        "GET",
        "/dashboard/bootstrap",
        {"Authorization": f"Bearer {token}", "X-HR-Phone": "96599338566", "X-Company-Code": "WATHEFNI"},
    )
    print("bootstrap_off", status, body if status != 200 else "UNEXPECTED_200")
    assert status == 404, status

    status, body = req(
        "GET",
        "/dashboard/prehire/summary",
        {"Authorization": f"Bearer {token}", "X-HR-Phone": "96599338566", "X-Company-Code": "WATHEFNI"},
    )
    print("legacy_summary", status, "modules=", body.get("enabled_modules") if isinstance(body, dict) else body)
    assert status == 200, status

    status, _ = req(
        "GET",
        "/dashboard/team",
        {"Authorization": f"Bearer {token}", "X-HR-Phone": "96599338566", "X-Company-Code": "WATHEFNI"},
    )
    print("wathefni_team_off", status)
    assert status == 200, status

    status, login = req(
        "POST",
        "/dashboard/auth/login",
        body={"company_code": "BOOTPOST01", "email": "bootpost01-owner@example.test", "password": "BootPost01!pass"},
    )
    sess = login.get("access_token") if isinstance(login, dict) else None
    assert status == 200 and sess, login

    status, _ = req("GET", "/dashboard/bootstrap", {"Authorization": f"Bearer {sess}", "X-Company-Code": "BOOTPOST01"})
    print("bootpost_bootstrap_off", status)
    assert status == 404, status

    status, body = req("GET", "/dashboard/team", {"Authorization": f"Bearer {sess}", "X-Company-Code": "BOOTPOST01"})
    print("bootpost_team_off", status, body if status != 200 else "UNEXPECTED_200")
    assert status in (403, 404), status
    print("ROLLBACK_OFF_PROOF_OK")


if __name__ == "__main__":
    main()
