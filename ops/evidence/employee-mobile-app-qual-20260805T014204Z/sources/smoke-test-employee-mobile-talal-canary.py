#!/usr/bin/env python3
"""Read-only Talal canary probe for employee /app/* APIs (no allowlist expansion)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

TALAL = "WATHEFNI-96550252254"
API = os.environ.get("DASHBOARD_API", "http://127.0.0.1:8010").rstrip("/")


def http(method: str, path: str, token: str | None = None, body: dict | None = None) -> tuple[int, dict | str]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{API}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw) if raw else {}
            except Exception:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if hasattr(e, "read") else ""
        try:
            return int(e.code), json.loads(raw) if raw else {}
        except Exception:
            return int(e.code), raw[:400]


def ok(name: str, cond: bool, detail: object = "") -> None:
    print(("PASS" if cond else "FAIL"), name, detail if detail != "" else "")
    if not cond:
        raise SystemExit(1)


def main() -> int:
    sys.path.insert(0, "/opt/wathefni/orchestrator")
    os.environ.setdefault("WATHEFNI_ENV", "production")
    os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
    os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
    os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")

    # Inherit projection/employee flags from systemd environ for allowlist helpers
    import app

    # Non-allowlisted subject must fail closed
    try:
        app.assert_employee_app_allowlisted("WATHEFNI-NOT-ALLOWLISTED")
        ok("non_allowlisted_denied", False, "expected raise")
    except Exception as exc:  # noqa: BLE001
        detail = getattr(exc, "detail", None) or str(exc)
        err = detail.get("error") if isinstance(detail, dict) else str(detail)
        ok("non_allowlisted_denied", err == "employee_app_not_allowlisted" or "employee_app_not_allowlisted" in str(detail), detail)

    app.assert_employee_app_allowlisted(TALAL)
    ok("talal_allowlisted", True)

    # Mint server session for Talal (canary read; does not expand allowlist)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT phone FROM employees WHERE employee_key=%s", (TALAL,))
            phone = (cur.fetchone() or {}).get("phone")
    session = app.create_employee_session("WATHEFNI", TALAL, phone)
    token = session.get("access_token") or session.get("token")
    ok("session_minted", bool(token), {k: session.get(k) for k in ("employee_key", "expires_at") if k in session or True})

    st, me = http("GET", "/app/me", token)
    ok("me_200", st == 200, type(me))
    assert isinstance(me, dict)
    ok("me_employee_key", str(me.get("employee", {}).get("employee_key") or me.get("employee_key") or "") == TALAL, me.get("employee"))
    features = me.get("features") or {}
    ok("features_present", isinstance(features, dict) and "home" in features)
    # No payslip money surface enabled
    payslips = features.get("payslips") or {}
    ok("payslips_disabled", not bool(payslips.get("enabled")), payslips)

    for path, name in [
        ("/app/notifications?limit=10", "notifications"),
        ("/app/onboarding", "onboarding"),
        ("/app/documents", "documents"),
        ("/app/attendance", "attendance"),
        ("/app/leave", "leave"),
        ("/app/shifts/today", "shifts_today"),
        ("/app/shifts/upcoming", "shifts_upcoming"),
        ("/app/profile", "profile"),
    ]:
        st, body = http("GET", path, token)
        # 200 or feature-disabled 403 are both valid under capability contract
        if st == 403 and isinstance(body, dict) and body.get("error") == "employee_feature_disabled":
            ok(f"{name}_gated", True, body.get("feature"))
        else:
            ok(f"{name}_ok", st == 200, st)

    # Foreign/invalid token fail-closed
    st, _ = http("GET", "/app/me", "invalid-employee-token")
    ok("invalid_token_closed", st in {401, 403}, st)

    print("TALAL_EMPLOYEE_APP_CANARY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
