#!/usr/bin/env python3
"""Prove Bank ESS eligibility identical across /app/me, /app/onboarding, /app/bank."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

for line in Path("/tmp/orch-environ.env").read_text(errors="replace").splitlines():
    if "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k, v)

sys.path.insert(0, "/opt/wathefni/orchestrator")
import app as A  # noqa: E402
import employee_bank_ess as bank  # noqa: E402

COMPANY = "WATHEFNI"
# Disabled canary (employee-app allowed, Bank ESS allowlist excludes)
DISABLED = "WATHEFNI-96599338566"
# Enabled synthetic Bank ESS allowlist key
ENABLED = "WATHEFNI-9655497001"
BASE = "http://127.0.0.1:8010"
results: list[dict] = []


def note(name: str, ok: bool, detail=None) -> None:
    results.append({"case": name, "ok": bool(ok), "detail": detail})
    print(("PASS" if ok else "FAIL"), name, json.dumps(detail, default=str)[:300] if detail is not None else "")


def http(method: str, path: str, token: str | None = None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw[:500]}
        return e.code, body


def phone_for(key: str) -> str:
    with A.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT phone FROM employees WHERE employee_key=%s", (key,))
            row = cur.fetchone()
    if not row:
        raise SystemExit(f"missing employee {key}")
    return row["phone"] if isinstance(row, dict) else row[0]


def ensure_enabled_employee() -> None:
    with A.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT employee_key FROM employees WHERE employee_key=%s", (ENABLED,))
            if cur.fetchone():
                conn.commit()
                return
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name,
                                       onboarding_status, employment_status, created_at, updated_at)
                VALUES (%s,%s,%s,%s,'in_progress','active',now(),now())
                """,
                (COMPANY, ENABLED, "9655497001", "BANK-ESS-ELIG|enabled"),
            )
            cur.execute(
                """
                INSERT INTO onboarding_items (
                  employee_key, item_id, label, item_type, required, status,
                  collection_mode, authority, owner, created_at, updated_at
                ) VALUES (%s,'bank_details','Bank details','bank',true,'pending',
                          'ess_encrypted','ess','employee',now(),now())
                ON CONFLICT DO NOTHING
                """,
                (ENABLED,),
            )
        conn.commit()


def ensure_disabled_has_bank_item() -> None:
    with A.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT item_id FROM onboarding_items
                WHERE employee_key=%s AND item_id='bank_details'
                """,
                (DISABLED,),
            )
            if cur.fetchone():
                conn.commit()
                return
            cur.execute(
                """
                INSERT INTO onboarding_items (
                  employee_key, item_id, label, item_type, required, status,
                  collection_mode, authority, owner, created_at, updated_at
                ) VALUES (%s,'bank_details','Bank details','bank',true,'pending',
                          'ess_encrypted','ess','employee',now(),now())
                """,
                (DISABLED,),
            )
        conn.commit()


def token_for(key: str) -> str:
    sess = A.create_employee_session(COMPANY, key, phone_for(key))
    return str(sess["token"] if isinstance(sess, dict) else sess[0])


def assert_surface_alignment(key: str, *, expect_eligible: bool) -> None:
    helper = bank.bank_ess_eligibility(COMPANY, key)
    note(f"{key}_helper", helper.get("eligible") is expect_eligible, helper)
    tok = token_for(key)
    code_me, me = http("GET", "/app/me", tok)
    bank_feat = ((me.get("features") or {}).get("bank") or {}) if isinstance(me, dict) else {}
    me_elig = bool(bank_feat.get("enabled"))
    me_reason = bank_feat.get("reason")
    bank_ess_me = me.get("bank_ess") if isinstance(me, dict) else None
    note(
        f"{key}_me",
        code_me == 200 and me_elig is expect_eligible,
        {"code": code_me, "enabled": me_elig, "reason": me_reason, "bank_ess": bank_ess_me},
    )

    code_onb, onb = http("GET", "/app/onboarding?locale=en", tok)
    onb_ess = (onb.get("bank_ess") or {}) if isinstance(onb, dict) else {}
    items = list(onb.get("items") or []) + list(onb.get("your_actions") or [])
    bank_items = [
        i
        for i in items
        if str(i.get("item_id") or "") == "bank_details"
        or str(i.get("collection_mode") or "").lower() == "ess_encrypted"
    ]
    open_actions = any("open_bank" in (i.get("actions") or []) for i in bank_items)
    note(
        f"{key}_onboarding",
        code_onb == 200
        and bool(onb_ess.get("eligible")) is expect_eligible
        and open_actions is expect_eligible,
        {
            "code": code_onb,
            "bank_ess": onb_ess,
            "bank_items": [
                {"item_id": i.get("item_id"), "actions": i.get("actions"), "eligible": i.get("bank_ess_eligible")}
                for i in bank_items
            ],
            "open_bank_present": open_actions,
        },
    )

    code_bank, body_bank = http("GET", "/app/bank?locale=en", tok)
    if expect_eligible:
        note(f"{key}_bank", code_bank == 200 and isinstance(body_bank, dict), {"code": code_bank, "keys": list(body_bank)[:12] if isinstance(body_bank, dict) else body_bank})
    else:
        err = (body_bank.get("detail") or body_bank) if isinstance(body_bank, dict) else body_bank
        err_code = err.get("error") if isinstance(err, dict) else None
        note(
            f"{key}_bank",
            code_bank == 403 and err_code == "bank_ess_not_allowlisted",
            {"code": code_bank, "error": err_code},
        )

    # Cross-surface identity
    note(
        f"{key}_aligned",
        helper.get("eligible") is expect_eligible
        and me_elig is expect_eligible
        and bool(onb_ess.get("eligible")) is expect_eligible
        and open_actions is expect_eligible
        and ((code_bank == 200) is expect_eligible),
        {
            "helper": helper.get("eligible"),
            "me": me_elig,
            "onboarding": onb_ess.get("eligible"),
            "open_bank": open_actions,
            "bank_http_ok": code_bank == 200,
        },
    )

    # AR smoke for onboarding payload
    code_ar, onb_ar = http("GET", "/app/onboarding?locale=ar", tok)
    note(f"{key}_onboarding_ar", code_ar == 200 and isinstance(onb_ar, dict), {"code": code_ar})


def main() -> int:
    ensure_enabled_employee()
    ensure_disabled_has_bank_item()
    assert_surface_alignment(DISABLED, expect_eligible=False)
    assert_surface_alignment(ENABLED, expect_eligible=True)
    failed = [r for r in results if not r["ok"]]
    print("SUMMARY", "PASS" if not failed else "FAIL", f"passed={len(results)-len(failed)} failed={len(failed)}")
    print(json.dumps({"results": results, "failed": failed}, default=str))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
