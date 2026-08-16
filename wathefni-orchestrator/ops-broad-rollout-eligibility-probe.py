#!/usr/bin/env python3
"""Stage eligibility probe after allowlist expansion."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
for line in Path("/tmp/orch-environ.env").read_text(errors="replace").splitlines():
    if "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k, v)

import app as A

COMPANY = "WATHEFNI"
OUT = Path(os.environ.get("OUT_PATH") or "/tmp/broad-eligibility.json")
RESULTS = {"checks": [], "failed": 0}


def check(name, ok, detail=None):
    RESULTS["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    if not ok:
        RESULTS["failed"] += 1
    print(("PASS" if ok else "FAIL"), name, "::", json.dumps(detail, default=str)[:300])


def mint(key):
    emp = A.find_employee_by_key(key, company_code=COMPANY)
    return str(A.create_employee_session(COMPANY, key, str(emp.get("phone")))["token"])


def http(path, token):
    req = urllib.request.Request(
        f"http://127.0.0.1:8010{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def bank_probe(key):
    token = mint(key)
    code, body = http("/app/bank", token)
    code_m, me = http("/app/me", token)
    feat = ((me.get("features") or {}).get("bank") if isinstance(me, dict) else None)
    code_o, onb = http("/app/onboarding", token)
    open_bank = False
    if isinstance(onb, dict):
        for g in ("your_actions", "being_reviewed", "handled_by_others", "completed"):
            for item in onb.get(g) or []:
                if item.get("item_id") == "bank_details" and "open_bank" in (item.get("actions") or []):
                    open_bank = True
    return {
        "key": key,
        "bank_http": code,
        "me_http": code_m,
        "bank_enabled": bool((feat or {}).get("enabled")) if isinstance(feat, dict) else None,
        "open_bank": open_bank,
        "bank_error": (
            ((body.get("detail") or {}).get("error") if isinstance(body.get("detail"), dict) else None)
            if isinstance(body, dict)
            else None
        ),
    }


def main():
    expect_ok = [
        "WATHEFNI-96599338566",  # Aziz
        "WATHEFNI-96566363363",  # Fouad stage1
        "WATHEFNI-96550010001",  # Noura stage1
    ]
    expect_403 = [
        "WATHEFNI-96550252254",  # Talal forever
    ]
    # Optional stage-gated denial (only if the key can mint an app session).
    optional_403 = os.environ.get("EXPECT_BANK_DENIED_KEYS", "").split(",")
    optional_403 = [k.strip() for k in optional_403 if k.strip()]
    RESULTS["probes"] = []
    for key in expect_ok:
        p = bank_probe(key)
        RESULTS["probes"].append(p)
        check(f"{key} bank enabled", p["bank_http"] == 200 and p["bank_enabled"] is True, p)
    for key in expect_403 + optional_403:
        try:
            p = bank_probe(key)
        except Exception as e:
            RESULTS["probes"].append({"key": key, "mint_error": str(e)})
            check(f"{key} bank denied", False, {"mint_error": str(e)})
            continue
        RESULTS["probes"].append(p)
        check(
            f"{key} bank denied",
            p["bank_http"] == 403 and p["open_bank"] is False and p["bank_enabled"] is False,
            p,
        )
    OUT.write_text(json.dumps(RESULTS, indent=2, default=str))
    print("ELIGIBILITY_OK" if RESULTS["failed"] == 0 else "ELIGIBILITY_FAILED")
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
