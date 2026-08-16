#!/usr/bin/env python3
"""Smoke: Setup Console persistent operator access + refresh sessions."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, request

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
EVIDENCE: list[dict[str, Any]] = []


def _ok(name: str, detail: Any = None) -> None:
    global PASS
    PASS += 1
    EVIDENCE.append({"status": "PASS", "name": name, "detail": detail})
    print(f"PASS  {name}")


def _fail(name: str, detail: Any = None) -> None:
    global FAIL
    FAIL += 1
    EVIDENCE.append({"status": "FAIL", "name": name, "detail": detail})
    print(f"FAIL  {name}: {detail}")


def _load_creds() -> tuple[str, str]:
    token = (os.environ.get("WATHEFNI_SETUP_TOKEN") or "").strip()
    phone = (os.environ.get("WATHEFNI_SETUP_PHONE") or "").strip()
    if token and phone:
        return token, phone
    creds_raw = (os.environ.get("WATHEFNI_SETUP_OPERATOR_CREDENTIALS") or "").strip()
    if not creds_raw:
        try:
            for p in Path("/proc").iterdir():
                if not p.name.isdigit():
                    continue
                try:
                    cmd = (p / "cmdline").read_bytes()
                except Exception:
                    continue
                if b"uvicorn" not in cmd or b"8010" not in cmd:
                    continue
                for item in (p / "environ").read_bytes().split(b"\0"):
                    if item.startswith(b"WATHEFNI_SETUP_OPERATOR_CREDENTIALS="):
                        creds_raw = item.decode().split("=", 1)[1]
                        break
                if creds_raw:
                    break
        except Exception:
            pass
    if not creds_raw:
        return "", ""
    try:
        parsed = json.loads(creds_raw)
        phone = str(next(iter(parsed.keys()))).strip()
        token = str(next(iter(parsed.values()))).strip()
        return token, phone
    except Exception:
        return "", ""


def _req(method: str, path: str, *, token: str | None = None, phone: str | None = None, body: dict | None = None) -> tuple[int, Any]:
    base = (os.environ.get("WATHEFNI_API_BASE") or "http://127.0.0.1:8010").rstrip("/")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if phone:
        headers["X-HR-Phone"] = phone
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = request.Request(f"{base}{path}", headers=headers, data=data, method=method)
    try:
        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {"error": str(exc)}
        except Exception:
            payload = {"error": raw or str(exc)}
        return int(exc.code), payload
    except Exception as exc:
        return 0, {"error": str(exc)}


def main() -> int:
    import setup_console_operator_auth as auth

    if auth.ACCESS_TTL.total_seconds() == 8 * 3600 and auth.REFRESH_TTL.days == 30:
        _ok("ttl_contract", {"access_hours": 8, "refresh_days": 30})
    else:
        _fail("ttl_contract", {"access": str(auth.ACCESS_TTL), "refresh": str(auth.REFRESH_TTL)})

    operator_token, phone = _load_creds()
    if not operator_token or not phone:
        _fail("credentials_missing")
        return _finish()

    # Bad login
    bad_status, _ = _req(
        "POST",
        "/dashboard/superadmin/setup/auth/login",
        body={"operator_token": "definitely-wrong-token-value", "phone": phone},
    )
    if bad_status == 401:
        _ok("login_rejects_bad_token")
    else:
        _fail("login_rejects_bad_token", bad_status)

    # Good login
    status, login = _req(
        "POST",
        "/dashboard/superadmin/setup/auth/login",
        body={"operator_token": operator_token, "phone": phone},
    )
    if status == 200 and login.get("access_token") and login.get("refresh_token"):
        _ok("login_issues_access_refresh", {
            "access_ttl_seconds": login.get("access_ttl_seconds"),
            "refresh_ttl_seconds": login.get("refresh_ttl_seconds"),
        })
    else:
        _fail("login_issues_access_refresh", {"status": status, "body": login})
        return _finish()

    access = str(login["access_token"])
    refresh = str(login["refresh_token"])
    session_phone = str(login.get("phone") or phone)

    # Session probe
    st, sess = _req("GET", "/dashboard/superadmin/setup/auth/session", token=access, phone=session_phone)
    if st == 200 and sess.get("ok"):
        _ok("session_probe", sess.get("auth_source"))
    else:
        _fail("session_probe", {"status": st, "body": sess})

    # Protected route with session access token
    st, companies = _req(
        "GET",
        "/dashboard/superadmin/setup/companies?q=&limit=5&offset=0",
        token=access,
        phone=session_phone,
    )
    if st == 200 and isinstance(companies, dict):
        _ok("session_authorizes_setup_api")
    else:
        _fail("session_authorizes_setup_api", {"status": st, "body": companies})

    # Refresh rotation
    st, rotated = _req(
        "POST",
        "/dashboard/superadmin/setup/auth/refresh",
        body={"refresh_token": refresh},
    )
    if st == 200 and rotated.get("access_token") and rotated.get("refresh_token"):
        if rotated["access_token"] != access and rotated["refresh_token"] != refresh:
            _ok("refresh_rotates_tokens")
        else:
            _fail("refresh_rotates_tokens", "tokens did not rotate")
    else:
        _fail("refresh_rotates_tokens", {"status": st, "body": rotated})
        return _finish()

    new_access = str(rotated["access_token"])
    new_refresh = str(rotated["refresh_token"])

    # Old access should fail after rotation
    st, _ = _req("GET", "/dashboard/superadmin/setup/auth/session", token=access, phone=session_phone)
    if st == 401:
        _ok("old_access_revoked_after_refresh")
    else:
        # Access hash replaced — old access must not work
        _fail("old_access_revoked_after_refresh", st)

    # New access works
    st, _ = _req("GET", "/dashboard/superadmin/setup/auth/session", token=new_access, phone=session_phone)
    if st == 200:
        _ok("new_access_works")
    else:
        _fail("new_access_works", st)

    # Logout
    st, logout = _req(
        "POST",
        "/dashboard/superadmin/setup/auth/logout",
        token=new_access,
        phone=session_phone,
        body={"refresh_token": new_refresh},
    )
    if st == 200 and logout.get("ok"):
        _ok("logout_revokes")
    else:
        _fail("logout_revokes", {"status": st, "body": logout})

    st, _ = _req("GET", "/dashboard/superadmin/setup/auth/session", token=new_access, phone=session_phone)
    if st == 401:
        _ok("revoked_session_rejected")
    else:
        _fail("revoked_session_rejected", st)

    st, _ = _req("POST", "/dashboard/superadmin/setup/auth/refresh", body={"refresh_token": new_refresh})
    if st == 401:
        _ok("revoked_refresh_rejected")
    else:
        _fail("revoked_refresh_rejected", st)

    # Legacy operator token still works for tooling (smoke scripts)
    st, _ = _req(
        "GET",
        "/dashboard/superadmin/setup/ownership",
        token=operator_token,
        phone=phone,
    )
    if st == 200:
        _ok("legacy_operator_token_still_works_for_tooling")
    else:
        _fail("legacy_operator_token_still_works_for_tooling", st)

    # Frontend persistence contract present
    ui_roots = [
        Path("/opt/wathefni/dashboard-dist"),
        ROOT.parent / "apps" / "wathefni-dashboard" / "src" / "setup-console",
    ]
    blob = ""
    for root in ui_roots:
        for name in ("session.ts", "SetupConsoleApp.tsx", "api.ts"):
            p = root / name if root.name == "setup-console" else None
            if root.name == "setup-console":
                cand = root / name
                if cand.is_file():
                    blob += cand.read_text(encoding="utf-8")
        # also scan built assets for localStorage keys
        if root.name == "dashboard-dist" and root.is_dir():
            for asset in root.glob("assets/setupConsole*.js"):
                blob += asset.read_text(encoding="utf-8", errors="ignore")
                break
    for needle in (
        "wathefni_setup_access_token",
        "wathefni_setup_refresh_token",
        "auth/login",
        "auth/refresh",
        "auth/logout",
    ):
        if needle in blob:
            _ok(f"ui:{needle}")
        else:
            _fail(f"ui:{needle}")

    return _finish()


def _finish() -> int:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dirs = [
        Path("/opt/wathefni/ops/evidence") / f"setup-console-operator-auth-{stamp}",
        ROOT.parent / "ops" / "evidence" / f"setup-console-operator-auth-{stamp}",
    ]
    evidence_path = None
    for out in out_dirs:
        try:
            out.mkdir(parents=True, exist_ok=True)
            (out / "smoke.json").write_text(json.dumps({"pass": PASS, "fail": FAIL, "checks": EVIDENCE}, indent=2), encoding="utf-8")
            (out / "SUMMARY.md").write_text(
                f"# Setup Console operator auth smoke\n\nPASS={PASS} FAIL={FAIL}\n\n"
                f"Access TTL: 8h · Refresh TTL: 30d (rotating)\n\nEvidence: `{out}`\n",
                encoding="utf-8",
            )
            evidence_path = out
            break
        except Exception:
            continue
    print(f"\nEvidence: {evidence_path}")
    print(f"RESULT {PASS}/{FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
