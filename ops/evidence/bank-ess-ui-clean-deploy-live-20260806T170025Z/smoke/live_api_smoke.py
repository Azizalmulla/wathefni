#!/usr/bin/env python3
"""Basic live API smoke for Bank ESS UI deploy — no bank submit."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _load_orchestrator_environ() -> None:
    """Copy live uvicorn env without shell-sourcing (commas break `. env`)."""
    pid_path = Path("/tmp/orch-environ.env")
    if not pid_path.exists():
        # fallback: discover MainPID
        import subprocess

        pid = subprocess.check_output(
            ["systemctl", "show", "-p", "MainPID", "--value", "wathefni-orchestrator"],
            text=True,
        ).strip()
        raw = Path(f"/proc/{pid}/environ").read_bytes()
        pid_path.write_bytes(b"\n".join(raw.split(b"\0")))
    for line in pid_path.read_text(errors="replace").splitlines():
        if not line or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k and k not in os.environ:
            os.environ[k] = v


_load_orchestrator_environ()
sys.path.insert(0, "/opt/wathefni/orchestrator")
sys.path.insert(0, ".")
import app as A  # noqa: E402

COMPANY = "WATHEFNI"
# Prefer a real roster employee for HR profile/bank/completion GETs.
HR_PROBE_KEYS = [
    "WATHEFNI-96550010003",  # Mariam Almulla
    "WATHEFNI-96550010002",
    "WATHEFNI-96550010005",
]
# Bank ESS employee allowlist phones (create disposable row if missing).
ALLOWLIST_KEY = "WATHEFNI-9655497001"
ALLOWLIST_PHONE = "9655497001"
BASE = "http://127.0.0.1:8010"
results: list[dict] = []


def http(method: str, path: str, token: str | None = None, dashboard: bool = False):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        if dashboard:
            headers["X-Dashboard-Token"] = token
    req = urllib.request.Request(BASE + path, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                body = json.loads(raw)
            except Exception:
                body = {"raw": raw[:500]}
            return resp.status, body
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw[:500]}
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)}


def note(name: str, ok: bool, detail=None) -> None:
    results.append({"case": name, "ok": bool(ok), "detail": detail})
    mark = "PASS" if ok else "FAIL"
    print(mark, name, json.dumps(detail, default=str)[:280] if detail is not None else "")


def session_token(sess):
    if isinstance(sess, str):
        return sess
    if isinstance(sess, (list, tuple)):
        return sess[0]
    if isinstance(sess, dict):
        for k in ("access_token", "token", "session_token", "jwt", "access"):
            if sess.get(k):
                return sess[k]
    raise RuntimeError(f"unknown session shape: {type(sess)} {sess!r}"[:200])


def main() -> int:
    code, body = http("GET", "/health")
    note(
        "health",
        code == 200,
        {"code": code, "status": body.get("status") if isinstance(body, dict) else None},
    )

    with A.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM dashboard_users
                WHERE company_code=%s
                  AND lower(coalesce(role,'')) IN ('owner','admin','hr_admin','hr','hr_manager')
                ORDER BY created_at
                LIMIT 1
                """,
                (COMPANY,),
            )
            row = cur.fetchone()
        conn.commit()

    if not row:
        note("hr_user", False, {"users": []})
        print(json.dumps({"results": results}, default=str))
        return 1

    hr_user = dict(row)
    tok, _meta = A.create_dashboard_session(hr_user)
    note("hr_session_minted", bool(tok), {"role": hr_user.get("role"), "email": hr_user.get("email")})

    # Resolve an existing employee for HR GETs
    hr_emp = None
    with A.db_connect() as conn:
        with conn.cursor() as cur:
            for k in HR_PROBE_KEYS:
                cur.execute(
                    "SELECT employee_key, phone, name FROM employees WHERE employee_key=%s",
                    (k,),
                )
                row = cur.fetchone()
                if row:
                    hr_emp = dict(row)
                    break
            if hr_emp is None:
                cur.execute(
                    "SELECT employee_key, phone, name FROM employees WHERE company_code=%s ORDER BY updated_at DESC LIMIT 1",
                    (COMPANY,),
                )
                row = cur.fetchone()
                hr_emp = dict(row) if row else None
    if not hr_emp:
        note("hr_employee", False, {})
        print(json.dumps({"results": results}, default=str))
        return 1
    note("hr_employee", True, hr_emp)
    emp_key = hr_emp["employee_key"]

    code, body = http("GET", f"/dashboard/posthire/employees/{emp_key}/bank")
    note("bank_review_unauth_denied", code in (401, 403), {"code": code})

    code, body = http("GET", f"/dashboard/posthire/employees/{emp_key}/bank?locale=en", token=tok, dashboard=True)
    note(
        "bank_review_hr_loads",
        code == 200 and isinstance(body, dict),
        {"code": code, "keys": list(body)[:24] if isinstance(body, dict) else body},
    )
    code, body = http("GET", f"/dashboard/posthire/employees/{emp_key}/bank?locale=ar", token=tok, dashboard=True)
    note("bank_review_hr_ar", code == 200, {"code": code})

    code, body = http("GET", f"/dashboard/posthire/employees/{emp_key}", token=tok, dashboard=True)
    note(
        "employee_profile_loads",
        code == 200 and isinstance(body, dict),
        {"code": code, "keys": list(body)[:20] if isinstance(body, dict) else None},
    )

    code, body = http(
        "GET",
        f"/dashboard/posthire/employees/{emp_key}/onboarding-completion?locale=en",
        token=tok,
        dashboard=True,
    )
    note(
        "onboarding_completion_hr",
        code == 200 and isinstance(body, dict) and ("state" in body or "completion" in body or "is_complete" in body),
        {"code": code, "body": body if isinstance(body, dict) else None},
    )
    code, body = http(
        "GET",
        f"/dashboard/posthire/employees/{emp_key}/onboarding-completion?locale=ar",
        token=tok,
        dashboard=True,
    )
    note("onboarding_completion_hr_ar", code == 200, {"code": code, "body": body if isinstance(body, dict) else None})

    for label, path in [
        ("compliance", "/dashboard/posthire/compliance"),
    ]:
        code, body = http("GET", path, token=tok, dashboard=True)
        ok = code == 200 and isinstance(body, dict) and ("findings" in body or "documents" in body or "summary" in body)
        note(
            f"compliance_{label}",
            ok,
            {
                "code": code,
                "has_findings": isinstance(body, dict) and "findings" in body,
                "has_documents": isinstance(body, dict) and "documents" in body,
                "has_summary": isinstance(body, dict) and "summary" in body,
            },
        )

    # OCR / documents for profile
    code, body = http("GET", f"/dashboard/posthire/employees/{emp_key}/documents", token=tok, dashboard=True)
    note("employee_documents", code in (200, 404), {"code": code, "keys": list(body)[:12] if isinstance(body, dict) else None})

    # Disposable allowlisted employee for /app/bank GET (no submit)
    created_temp = False
    with A.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT employee_key, phone FROM employees WHERE employee_key=%s", (ALLOWLIST_KEY,))
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, phone, name,
                                           onboarding_status, employment_status, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,'not_started','active',now(),now())
                    ON CONFLICT (employee_key) DO UPDATE
                    SET phone=EXCLUDED.phone, updated_at=now()
                    """,
                    (COMPANY, ALLOWLIST_KEY, ALLOWLIST_PHONE, "BANK-ESS-UI-SMOKE|temp"),
                )
                created_temp = True
            else:
                row = dict(row)
                # ensure phone matches allowlist key convention
        conn.commit()
    note("allowlist_employee_ready", True, {"employee_key": ALLOWLIST_KEY, "created_temp": created_temp})

    sess = A.create_employee_session(COMPANY, ALLOWLIST_KEY, ALLOWLIST_PHONE)
    emp_tok = session_token(sess if not isinstance(sess, dict) else sess)
    if isinstance(sess, dict):
        emp_tok = str(sess.get("token") or session_token(sess))
    note("employee_session_minted", bool(emp_tok), {"employee_key": ALLOWLIST_KEY})

    code, body = http("GET", "/app/bank?locale=en", token=emp_tok)
    note(
        "employee_bank_en",
        code == 200,
        {
            "code": code,
            "keys": list(body)[:20] if isinstance(body, dict) else body,
        },
    )

    code, body = http("GET", "/app/bank?locale=ar", token=emp_tok)
    note("employee_bank_ar", code == 200, {"code": code})

    code, body = http("GET", "/app/onboarding?locale=en", token=emp_tok)
    comp = body.get("completion") if isinstance(body, dict) else None
    note(
        "employee_onboarding_en",
        code == 200,
        {
            "code": code,
            "has_completion": comp is not None,
            "completion": comp
            if not isinstance(comp, dict)
            else {k: comp.get(k) for k in list(comp)[:12]},
        },
    )

    code, body = http("GET", "/app/onboarding?locale=ar", token=emp_tok)
    note(
        "employee_onboarding_ar",
        code == 200 and isinstance(body, dict) and body.get("completion") is not None,
        {"code": code, "completion": body.get("completion") if isinstance(body, dict) else None},
    )

    for path in ["/app/me", "/app/documents", "/app/leave"]:
        code, body = http("GET", path, token=emp_tok)
        note(
            f"employee_{path.strip('/').replace('/', '_')}",
            code in (200, 403, 404),
            {"code": code},
        )

    if created_temp:
        with A.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM employee_sessions WHERE employee_key=%s", (ALLOWLIST_KEY,))
                cur.execute("DELETE FROM employees WHERE employee_key=%s", (ALLOWLIST_KEY,))
            conn.commit()
        note("temp_canary_cleaned", True, {"employee_key": ALLOWLIST_KEY})

    failed = [r for r in results if not r["ok"]]
    print(
        "SUMMARY",
        "PASS" if not failed else "FAIL",
        f"passed={len(results) - len(failed)} failed={len(failed)}",
    )
    print(json.dumps({"results": results, "failed": failed}, default=str))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
