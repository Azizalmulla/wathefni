#!/usr/bin/env python3
"""Auth Wave 1 freeze — live prove for Aziz + Talal (production canary).

Proves activate (Kuwait local-8), reopen (/app/me), refresh, logout, and
new-device revocation without delivering OTP WhatsApp messages.
Restores a usable session afterward so mobile canary continues.
Confirms Bank ESS + onboarding completion snapshots are unchanged.

Run on orchestrator host with live DB + env:
  cd /opt/wathefni/orchestrator && ./.venv/bin/python ops-prove-auth-wave1-freeze-live.py
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

OUT = Path(os.environ.get("AUTH_WAVE1_FREEZE_OUT", "/tmp/auth-wave1-freeze-live.json"))
API = os.environ.get("AUTH_WAVE1_FREEZE_API", "http://127.0.0.1:8010").rstrip("/")
COMPANY = "WATHEFNI"
CANARIES = (
    {"key": "WATHEFNI-96599338566", "label": "Aziz"},
    {"key": "WATHEFNI-96550252254", "label": "Talal"},
)

R: dict[str, Any] = {
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "checks": [],
    "failed": 0,
    "employees": {},
}


def check(name: str, ok: bool, detail: Any = None) -> bool:
    R["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    if not ok:
        R["failed"] += 1
    print(("PASS" if ok else "FAIL"), name, "::", json.dumps(detail, default=str)[:400])
    return bool(ok)


def http(method: str, path: str, *, token: str | None = None, body: dict | None = None) -> tuple[int, Any]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"{API}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:300]}


def load_env() -> None:
    env_path = Path("/tmp/orch-environ.env")
    if not env_path.exists():
        return
    for line in env_path.read_text(errors="replace").splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k, v)


def snapshot(A: Any, B: Any, key: str) -> dict[str, Any]:
    emp = A.find_employee_by_key(key, company_code=COMPANY)
    token = str(A.create_employee_session(COMPANY, key, str(emp.get("phone")))["token"])
    code_b, bank = http("GET", "/app/bank", token=token)
    code_o, onb = http("GET", "/app/onboarding", token=token)
    code_p, prof = http("GET", "/app/profile", token=token)
    # Drop the snapshot session immediately — not part of the auth proof path.
    http("POST", "/app/auth/logout", token=token, body={})
    bank_payload: dict[str, Any]
    if code_b == 403 and isinstance(bank, dict):
        detail = bank.get("detail") if isinstance(bank.get("detail"), dict) else bank
        bank_payload = {
            "http": code_b,
            "error": (detail or {}).get("error"),
            "denied": True,
        }
    else:
        disp = ((bank.get("verified") or {}).get("display") if isinstance(bank, dict) else None) or {}
        pe = (bank.get("payroll_effective") if isinstance(bank, dict) else None) or {}
        with A.db_connect() as conn:
            with conn.cursor() as cur:
                B.ensure_bank_ess_schema(cur)
                cur.execute(
                    """
                    SELECT fingerprint FROM employee_bank_effective
                    WHERE company_code=%s AND employee_key=%s AND superseded_at IS NULL
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (COMPANY, key),
                )
                row = cur.fetchone()
                fp = dict(row).get("fingerprint") if row else None
            conn.commit()
        bank_payload = {
            "http": code_b,
            "has_verified_bank": (bank or {}).get("has_verified_bank") if isinstance(bank, dict) else None,
            "iban_last4": disp.get("iban_last4"),
            "bank_name": disp.get("bank_name"),
            "submission_state": (bank or {}).get("submission_state") if isinstance(bank, dict) else None,
            "effective_fp": fp,
            "payroll_effective_present": bool(pe.get("display")) if isinstance(pe, dict) else False,
            "denied": False,
        }
    comp = (onb.get("completion") if isinstance(onb, dict) else None) or {}
    return {
        "http": {"bank": code_b, "onboarding": code_o, "profile": code_p},
        "bank": bank_payload,
        "onboarding": {
            "state": comp.get("state"),
            "satisfied": comp.get("satisfied_count"),
            "required": comp.get("required_total"),
            "owner": ((comp.get("next_action") or {}).get("owner")),
        },
        "profile_completion_state": ((prof.get("onboarding") or {}).get("completion_state") if isinstance(prof, dict) else None),
    }


def prove_employee(A: Any, entry: dict[str, str]) -> None:
    key = entry["key"]
    label = entry["label"]
    emp = A.find_employee_by_key(key, company_code=COMPANY)
    phone_full = A.digits(emp.get("phone"))
    local8 = phone_full[-8:] if phone_full else ""
    bucket: dict[str, Any] = {"employee_key": key, "phone_full": phone_full, "local8": local8}
    R["employees"][label] = bucket

    check(f"{label} employee found", bool(emp and phone_full and local8), {"key": key, "phone": phone_full})

    # Activate with Kuwait local-8 against invite stored as full digits.
    invite, code = A.create_employee_app_invite(COMPANY, emp)
    bucket["invite_id"] = str(invite.get("invite_id"))
    st, activated = http("POST", "/app/auth/activate", body={"phone": local8, "code": code})
    ok_act = st == 200 and isinstance(activated, dict) and activated.get("token") and activated.get("refresh_token")
    check(
        f"{label} activate via Kuwait local-8",
        ok_act and str((activated.get("employee") or {}).get("employee_key")) == key,
        {"http": st, "employee_key": (activated.get("employee") or {}).get("employee_key") if isinstance(activated, dict) else None},
    )
    if not ok_act:
        return
    token = str(activated["token"])
    refresh = str(activated["refresh_token"])

    # Reopen = session still works for /app/me (SecureStore reopen equivalent).
    st_me, me = http("GET", "/app/me", token=token)
    check(
        f"{label} reopen /app/me",
        st_me == 200 and str((me.get("employee") or me).get("employee_key") if isinstance(me, dict) else "") == key,
        {"http": st_me, "employee_key": (me.get("employee") or {}).get("employee_key") if isinstance(me, dict) else None},
    )

    # Refresh rotates both tokens.
    st_r, rotated = http("POST", "/app/auth/refresh", body={"refresh_token": refresh})
    ok_r = st_r == 200 and isinstance(rotated, dict) and rotated.get("token") and rotated.get("refresh_token")
    check(
        f"{label} refresh rotates tokens",
        ok_r and rotated["token"] != token and rotated["refresh_token"] != refresh,
        {"http": st_r},
    )
    if not ok_r:
        return
    old_token, old_refresh = token, refresh
    token, refresh = str(rotated["token"]), str(rotated["refresh_token"])
    st_old, _ = http("GET", "/app/me", token=old_token)
    check(f"{label} old access dead after refresh", st_old == 401, {"http": st_old})

    # New-device: second activate revokes current session.
    _invite2, code2 = A.create_employee_app_invite(COMPANY, emp)
    st2, activated2 = http("POST", "/app/auth/activate", body={"phone": phone_full, "code": code2})
    ok2 = st2 == 200 and isinstance(activated2, dict) and activated2.get("token")
    check(f"{label} new-device re-activate", ok2, {"http": st2})
    st_rev, _ = http("GET", "/app/me", token=token)
    check(f"{label} prior session revoked on new-device activate", st_rev == 401, {"http": st_rev})
    with A.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT revoked_reason FROM employee_sessions
                WHERE company_code=%s AND employee_key=%s AND revoked_reason='reactivated_via_invite'
                ORDER BY revoked_at DESC NULLS LAST LIMIT 1
                """,
                (COMPANY, key),
            )
            reason_row = cur.fetchone()
        conn.commit()
    check(
        f"{label} revoke reason reactivated_via_invite",
        bool(reason_row),
        dict(reason_row) if reason_row else None,
    )
    if not ok2:
        return
    token = str(activated2["token"])
    refresh = str(activated2["refresh_token"])

    # Logout.
    st_l, logged = http("POST", "/app/auth/logout", token=token, body={})
    check(f"{label} logout", st_l == 200 and isinstance(logged, dict) and logged.get("ok") is True, {"http": st_l})
    st_dead, _ = http("GET", "/app/me", token=token)
    check(f"{label} token dead after logout", st_dead == 401, {"http": st_dead})
    st_rf, _ = http("POST", "/app/auth/refresh", body={"refresh_token": refresh})
    check(f"{label} refresh dead after logout", st_rf == 401, {"http": st_rf})

    # request-code remains generic (no disclosure).
    st_rc, rc = http("POST", "/app/auth/request-code", body={"phone": local8})
    check(
        f"{label} request-code generic ok",
        st_rc == 200 and isinstance(rc, dict) and rc.get("ok") is True,
        {"http": st_rc, "message": (rc or {}).get("message") if isinstance(rc, dict) else None},
    )

    # Restore canary session for continued app use (not part of Wave 1 product path).
    restored = A.create_employee_session(COMPANY, key, phone_full)
    st_rest, me_rest = http("GET", "/app/me", token=str(restored["token"]))
    check(
        f"{label} canary session restored",
        st_rest == 200 and str((me_rest.get("employee") or {}).get("employee_key")) == key,
        {"http": st_rest},
    )
    bucket["restored"] = True


def main() -> int:
    load_env()
    import app as A
    import employee_bank_ess as B

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for entry in CANARIES:
        before[entry["label"]] = snapshot(A, B, entry["key"])

    for entry in CANARIES:
        prove_employee(A, entry)

    for entry in CANARIES:
        after[entry["label"]] = snapshot(A, B, entry["key"])
        b, a = before[entry["label"]], after[entry["label"]]
        check(
            f"{entry['label']} Bank ESS snapshot unchanged",
            b["bank"] == a["bank"],
            {"before": b["bank"], "after": a["bank"]},
        )
        check(
            f"{entry['label']} onboarding completion unchanged",
            b["onboarding"] == a["onboarding"] and b["profile_completion_state"] == a["profile_completion_state"],
            {"before": b["onboarding"], "after": a["onboarding"], "profile": [b["profile_completion_state"], a["profile_completion_state"]]},
        )

    R["before"] = before
    R["after"] = after
    R["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    R["verdict"] = "PASS" if R["failed"] == 0 else "FAIL"
    OUT.write_text(json.dumps(R, indent=2, default=str))
    print("AUTH_WAVE1_FREEZE_LIVE:" + R["verdict"])
    print("failed", R["failed"], "of", len(R["checks"]))
    print("wrote", OUT)
    return 0 if R["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
