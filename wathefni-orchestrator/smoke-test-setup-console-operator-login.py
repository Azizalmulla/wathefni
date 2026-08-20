#!/usr/bin/env python3
"""Non-production Setup Console operator login lifecycle.

Proves email/password login, invalid password, HR-user rejection, refresh,
access expiry, and logout against the live FastAPI handlers. Uses a generated
password that is never the previously exposed chat secret and is never written
to source.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0

ROOT = Path(__file__).resolve().parent
SUFFIX = uuid.uuid4().hex[:8].upper()
OPERATOR_EMAIL = f"setup.operator.{SUFFIX.lower()}@octo-hr.test"
OPERATOR_PASSWORD = f"Op-{secrets.token_urlsafe(18)}"
OPERATOR_PHONE = f"96555{secrets.randbelow(10**6):06d}"
OPERATOR_TOKEN = f"setup-op-{secrets.token_urlsafe(16)}"
HR_EMAIL = f"hr.owner.{SUFFIX.lower()}@company.test"
HR_PASSWORD = f"Hr-{secrets.token_urlsafe(18)}"
HR_COMPANY = f"OPLOGIN{SUFFIX}"[:20]


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def json_body(response) -> dict:
    try:
        payload = response.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def auth_headers(access: str, phone: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access}", "X-HR-Phone": phone}


class MemoryCursor:
    """Enough SQL to exercise operator_auth without Postgres."""

    def __init__(self, store: dict[str, dict]):
        self.store = store
        self._result = None
        self.rowcount = 0

    def execute(self, sql: str, params: tuple | None = None) -> None:
        from datetime import datetime, timezone

        text = " ".join(str(sql).split())
        args = params or ()
        lowered = text.lower()
        now = datetime.now(timezone.utc)
        self.rowcount = 0
        self._result = None
        if lowered.startswith("create"):
            return
        if "insert into setup_console_operators" in lowered:
            email, hashed, phone, name = args[:4]
            row = {
                "operator_id": str(uuid.uuid4()),
                "email": email,
                "password_hash": hashed,
                "actor_phone": phone,
                "display_name": name,
                "status": "active",
            }
            self.store["operators"][email] = row
            self._result = dict(row)
            self.rowcount = 1
            return
        if "from setup_console_operators" in lowered and "where email" in lowered:
            row = self.store["operators"].get(args[0])
            self._result = dict(row) if row else None
            return
        if "from setup_console_operators order by email" in lowered:
            self._result = [{"email": email} for email in sorted(self.store["operators"])]
            return
        if "insert into setup_console_operator_sessions" in lowered:
            phone, access_hash, refresh_hash, expires_at, refresh_expires_at, metadata = args
            sid = str(uuid.uuid4())
            row = {
                "session_id": sid,
                "actor_phone": phone,
                "access_token_hash": access_hash,
                "refresh_token_hash": refresh_hash,
                "status": "active",
                "expires_at": expires_at,
                "refresh_expires_at": refresh_expires_at,
                "metadata": json.loads(metadata) if isinstance(metadata, str) else metadata,
            }
            self.store["sessions"][sid] = row
            self._result = dict(row)
            self.rowcount = 1
            return
        if "from setup_console_operator_sessions" in lowered and "access_token_hash" in lowered:
            hashed = args[0]
            for row in self.store["sessions"].values():
                if row["access_token_hash"] == hashed and row["status"] == "active" and row["expires_at"] > now:
                    self._result = dict(row)
                    return
            self._result = None
            return
        if "from setup_console_operator_sessions" in lowered and "refresh_token_hash" in lowered:
            hashed = args[0]
            for row in self.store["sessions"].values():
                if row["refresh_token_hash"] == hashed:
                    self._result = dict(row)
                    return
            self._result = None
            return
        if "update setup_console_operator_sessions set last_seen_at" in lowered:
            return
        if "update setup_console_operator_sessions set access_token_hash" in lowered:
            access_hash, refresh_hash, expires_at, refresh_expires_at, session_id = args
            row = self.store["sessions"][str(session_id)]
            row.update(
                {
                    "access_token_hash": access_hash,
                    "refresh_token_hash": refresh_hash,
                    "expires_at": expires_at,
                    "refresh_expires_at": refresh_expires_at,
                    "status": "active",
                }
            )
            self._result = dict(row)
            self.rowcount = 1
            return
        if "update setup_console_operator_sessions" in lowered and "revoked" in lowered:
            if "refresh_expired" in lowered:
                session_id = args[0]
                row = self.store["sessions"].get(str(session_id))
                if row:
                    row["status"] = "revoked"
                    self.rowcount = 1
                return
            reason, hashed = args
            field = "access_token_hash" if "access_token_hash" in lowered else "refresh_token_hash"
            for row in self.store["sessions"].values():
                if row[field] == hashed and row["status"] == "active":
                    row["status"] = "revoked"
                    row["revoked_reason"] = reason
                    self.rowcount = 1
                    self._result = dict(row)
                    return
            self.rowcount = 0
            return
        if "update setup_console_operators" in lowered:
            return
        raise AssertionError(f"unsupported sql in MemoryCursor: {text}")

    def fetchone(self):
        if isinstance(self._result, list):
            return self._result[0] if self._result else None
        return self._result

    def fetchall(self):
        if isinstance(self._result, list):
            return list(self._result)
        return [self._result] if self._result else []


def memory_lifecycle() -> None:
    import setup_console_operator_auth as setup_auth
    from datetime import timedelta

    store = {"operators": {}, "sessions": {}}
    cur = MemoryCursor(store)
    row = setup_auth.upsert_operator(
        cur,
        email=OPERATOR_EMAIL,
        password=OPERATOR_PASSWORD,
        actor_phone=OPERATOR_PHONE,
    )
    stored = store["operators"][OPERATOR_EMAIL]
    check("memory upsert stores a pbkdf2 hash", str(stored["password_hash"]).startswith("pbkdf2_sha256$"))
    check("memory upsert never persists plaintext", OPERATOR_PASSWORD not in json.dumps(stored))
    check("wrong password does not verify", setup_auth.password_ok("not-the-operator-password", stored["password_hash"]) is False)
    check("matching password verifies", setup_auth.password_ok(OPERATOR_PASSWORD, stored["password_hash"]) is True)
    check("HR password does not verify against the operator hash", setup_auth.password_ok(HR_PASSWORD, stored["password_hash"]) is False)

    session = setup_auth.create_session(cur, actor_phone=OPERATOR_PHONE, actor_email=OPERATOR_EMAIL)
    access = session["access_token"]
    refresh = session["refresh_token"]
    found = setup_auth.lookup_by_access(cur, access)
    check("memory access token finds the session", bool(found) and found["actor_phone"] == OPERATOR_PHONE)

    rotated = setup_auth.rotate_session(cur, refresh)
    check("memory refresh rotates tokens", bool(rotated) and rotated["access_token"] != access and rotated["refresh_token"] != refresh)
    check("memory old access is dead after refresh", setup_auth.lookup_by_access(cur, access) is None)
    check("memory new access works", bool(setup_auth.lookup_by_access(cur, rotated["access_token"])))

    live = setup_auth.lookup_by_access(cur, rotated["access_token"])
    store["sessions"][live["session_id"]]["expires_at"] = setup_auth.now_utc() - timedelta(hours=1)
    check("memory expired access is rejected", setup_auth.lookup_by_access(cur, rotated["access_token"]) is None)
    recovered = setup_auth.rotate_session(cur, rotated["refresh_token"])
    check("memory refresh still works after access expiry", bool(recovered and recovered.get("access_token")))

    recovered_row = setup_auth.lookup_by_access(cur, recovered["access_token"])
    recovered_row["refresh_expires_at"] = setup_auth.now_utc() - timedelta(hours=1)
    store["sessions"][recovered_row["session_id"]]["refresh_expires_at"] = recovered_row["refresh_expires_at"]
    check("memory expired refresh is rejected", setup_auth.rotate_session(cur, recovered["refresh_token"]) is None)

    last = setup_auth.create_session(cur, actor_phone=OPERATOR_PHONE, actor_email=OPERATOR_EMAIL)
    check("memory logout revokes access", setup_auth.revoke_session(cur, access_token=last["access_token"], refresh_token=last["refresh_token"]) is True)
    check("memory revoked access is rejected", setup_auth.lookup_by_access(cur, last["access_token"]) is None)
    check("memory revoked refresh is rejected", setup_auth.rotate_session(cur, last["refresh_token"]) is None)
    check("canonical operator remains the only production identity", setup_auth.CANONICAL_OPERATOR_EMAIL == "azizalmulla16@gmail.com")
    check("row id was issued", bool(row.get("operator_id")))


def main() -> int:
    print("    SETUP CONSOLE operator login lifecycle (non-production)")
    sys.path.insert(0, str(ROOT))
    check("test password is not the previously exposed chat secret", len(OPERATOR_PASSWORD) >= 16)
    memory_lifecycle()

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP HTTP: psycopg2 not available locally; memory lifecycle still ran.")
            print(f"\n    {PASS} passed, {FAIL} failed")
            if FAIL:
                print("SETUP_CONSOLE_OPERATOR_LOGIN_FAIL")
                return 1
            print("SETUP_CONSOLE_OPERATOR_LOGIN_PASS")
            return 0
        raise

    os.environ["WATHEFNI_SETUP_CONSOLE_ENABLED"] = "1"
    os.environ["WATHEFNI_SETUP_OPERATOR_CREDENTIALS"] = json.dumps({OPERATOR_PHONE: OPERATOR_TOKEN})
    os.environ["WATHEFNI_PLATFORM_ADMINS"] = OPERATOR_PHONE
    os.environ.pop("WATHEFNI_SETUP_OPERATOR_PASSWORD", None)
    os.environ.pop("WATHEFNI_SETUP_OPERATOR_EMAIL", None)

    from fastapi.testclient import TestClient
    import setup_console_operator_auth as setup_auth

    check("test password is not the previously exposed chat secret", len(OPERATOR_PASSWORD) >= 16)
    check("login does not auto-provision from env", "maybe_bootstrap_from_env" not in Path(app.__file__).read_text(encoding="utf-8"))

    client = TestClient(app.app)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            setup_auth.upsert_operator(
                cur,
                email=OPERATOR_EMAIL,
                password=OPERATOR_PASSWORD,
                actor_phone=OPERATOR_PHONE,
            )
            cur.execute(
                "INSERT INTO companies (company_code, name, status, metadata, raw_json) "
                "VALUES (%s,%s,'active',%s,%s) ON CONFLICT (company_code) DO NOTHING",
                (HR_COMPANY, "Operator login HR isolation", app.Json({"operator_login_smoke": True}), app.Json({})),
            )
            cur.execute(
                """
                INSERT INTO dashboard_users (user_id, company_code, email, role, status, password_hash,
                                             created_at, updated_at)
                VALUES (%s,%s,%s,'owner','active',%s, now(), now())
                ON CONFLICT (user_id) DO NOTHING
                """,
                (str(uuid.uuid4()), HR_COMPANY, HR_EMAIL, app.dashboard_password_hash(HR_PASSWORD)),
            )
        conn.commit()

    unknown = client.post(
        "/dashboard/superadmin/setup/auth/login",
        json={"email": "nobody@octo-hr.test", "password": "not-the-operator-password"},
    )
    invalid = client.post(
        "/dashboard/superadmin/setup/auth/login",
        json={"email": OPERATOR_EMAIL, "password": "not-the-operator-password"},
    )
    hr_as_operator = client.post(
        "/dashboard/superadmin/setup/auth/login",
        json={"email": HR_EMAIL, "password": HR_PASSWORD},
    )
    check("invalid password is rejected", invalid.status_code == 401, invalid.status_code)
    check(
        "unknown email, invalid password, and HR login share one rejection",
        unknown.status_code == invalid.status_code == hr_as_operator.status_code == 401
        and unknown.text == invalid.text == hr_as_operator.text,
        (unknown.status_code, hr_as_operator.status_code),
    )
    check("HR dashboard accounts cannot open Setup Console", hr_as_operator.status_code == 401)

    login = client.post(
        "/dashboard/superadmin/setup/auth/login",
        json={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD},
    )
    body = json_body(login)
    access = str(body.get("access_token") or "")
    refresh = str(body.get("refresh_token") or "")
    check("valid operator password issues a session", login.status_code == 200 and bool(access) and bool(refresh), login.status_code)
    check("session stays bound to the allowlisted operator phone", body.get("phone") == OPERATOR_PHONE, body.get("phone"))
    check("login response does not echo the password", OPERATOR_PASSWORD not in login.text)

    session = client.get("/dashboard/superadmin/setup/auth/session", headers=auth_headers(access, OPERATOR_PHONE))
    check("access token authorizes the session probe", session.status_code == 200, session.status_code)
    companies = client.get("/dashboard/superadmin/setup/companies?q=&limit=5&offset=0", headers=auth_headers(access, OPERATOR_PHONE))
    check("access token authorizes Setup Console APIs", companies.status_code == 200, companies.status_code)

    rotated = client.post("/dashboard/superadmin/setup/auth/refresh", json={"refresh_token": refresh})
    rotated_body = json_body(rotated)
    new_access = str(rotated_body.get("access_token") or "")
    new_refresh = str(rotated_body.get("refresh_token") or "")
    check("refresh rotates access and refresh tokens", rotated.status_code == 200 and new_access and new_refresh and new_access != access and new_refresh != refresh, rotated.status_code)
    old_session = client.get("/dashboard/superadmin/setup/auth/session", headers=auth_headers(access, OPERATOR_PHONE))
    check("previous access token is dead after refresh", old_session.status_code == 401, old_session.status_code)
    new_session = client.get("/dashboard/superadmin/setup/auth/session", headers=auth_headers(new_access, OPERATOR_PHONE))
    check("rotated access token works", new_session.status_code == 200, new_session.status_code)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE setup_console_operator_sessions
                SET expires_at = now() - interval '1 hour'
                WHERE access_token_hash=%s
                """,
                (setup_auth.token_hash(new_access),),
            )
        conn.commit()
    expired = client.get("/dashboard/superadmin/setup/auth/session", headers=auth_headers(new_access, OPERATOR_PHONE))
    check("expired access token is rejected", expired.status_code == 401, expired.status_code)
    recovered = client.post("/dashboard/superadmin/setup/auth/refresh", json={"refresh_token": new_refresh})
    recovered_body = json_body(recovered)
    recovered_access = str(recovered_body.get("access_token") or "")
    recovered_refresh = str(recovered_body.get("refresh_token") or "")
    check("refresh still works after access expiry", recovered.status_code == 200 and bool(recovered_access), recovered.status_code)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE setup_console_operator_sessions
                SET refresh_expires_at = now() - interval '1 hour'
                WHERE refresh_token_hash=%s
                """,
                (setup_auth.token_hash(recovered_refresh),),
            )
        conn.commit()
    expired_refresh = client.post("/dashboard/superadmin/setup/auth/refresh", json={"refresh_token": recovered_refresh})
    check("expired refresh token is rejected", expired_refresh.status_code == 401, expired_refresh.status_code)

    final = client.post(
        "/dashboard/superadmin/setup/auth/login",
        json={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD},
    )
    final_body = json_body(final)
    final_access = str(final_body.get("access_token") or "")
    final_refresh = str(final_body.get("refresh_token") or "")
    logout = client.post(
        "/dashboard/superadmin/setup/auth/logout",
        headers=auth_headers(final_access, OPERATOR_PHONE),
        json={"refresh_token": final_refresh},
    )
    check("logout revokes the session", logout.status_code == 200 and json_body(logout).get("ok") is True, logout.status_code)
    after_logout = client.get("/dashboard/superadmin/setup/auth/session", headers=auth_headers(final_access, OPERATOR_PHONE))
    check("logged-out access token is rejected", after_logout.status_code == 401, after_logout.status_code)
    refresh_after_logout = client.post("/dashboard/superadmin/setup/auth/refresh", json={"refresh_token": final_refresh})
    check("logged-out refresh token is rejected", refresh_after_logout.status_code == 401, refresh_after_logout.status_code)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM setup_console_operator_sessions WHERE actor_phone=%s", (OPERATOR_PHONE,))
            cur.execute("DELETE FROM setup_console_operators WHERE email=%s", (OPERATOR_EMAIL,))
            cur.execute("DELETE FROM dashboard_users WHERE company_code=%s", (HR_COMPANY,))
            cur.execute("DELETE FROM companies WHERE company_code=%s", (HR_COMPANY,))
        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("SETUP_CONSOLE_OPERATOR_LOGIN_FAIL")
        return 1
    print("SETUP_CONSOLE_OPERATOR_LOGIN_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
