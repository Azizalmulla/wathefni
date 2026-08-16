#!/usr/bin/env python3
"""Reconcile Leave decision after BrowserStack mutation (DB/API truth).

Reads leave IDs from env / fixture file. Never prints tokens or passwords.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_secrets import load_secrets, _parse_env_file  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ENV = Path.home() / ".config" / "wathefni" / "e2e-fixtures.env"


def login() -> tuple[str, str]:
    load_secrets()
    if FIXTURE_ENV.exists():
        for k, v in _parse_env_file(FIXTURE_ENV).items():
            os.environ.setdefault(k, v)
    base = os.environ.get("MOBILE_E2E_API_BASE", "https://api.wathefni.ai").rstrip("/")
    email = os.environ.get("MOBILE_E2E_HR_EMAIL") or os.environ.get("MAESTRO_HR_EMAIL")
    password = os.environ.get("MOBILE_E2E_HR_PASSWORD") or os.environ.get("MAESTRO_HR_PASSWORD")
    company = os.environ.get("MOBILE_E2E_HR_COMPANY") or os.environ.get("MAESTRO_HR_COMPANY") or "WATHEFNI"
    if not email or not password:
        raise SystemExit("missing HR credentials")
    body = json.dumps({"company_code": company, "email": email, "password": password}).encode()
    req = urllib.request.Request(
        f"{base}/dashboard/mobile/auth/login",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    token = data.get("access_token") or data.get("access") or ""
    if not token:
        raise SystemExit("login_no_token")
    return base, token


def leave_detail(base: str, token: str, leave_id: str) -> dict:
    req = urllib.request.Request(
        f"{base}/dashboard/mobile/leave/{leave_id}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    req_obj = data.get("request") or data
    return {
        "leave_id": leave_id,
        "status": req_obj.get("status"),
        "decision_note": req_obj.get("decision_note"),
        "allowed_actions": req_obj.get("allowed_actions") or [],
        "employee_key": (req_obj.get("employee") or {}).get("employee_key"),
        "start_date": req_obj.get("start_date"),
        "leave_type": req_obj.get("leave_type"),
        "reason": (req_obj.get("reason") or "")[:120],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve-id", default="")
    parser.add_argument("--reject-id", default="")
    parser.add_argument("--expect-approve", default="approved")
    parser.add_argument("--expect-reject", default="rejected")
    parser.add_argument("--evidence", default="")
    args = parser.parse_args()
    load_secrets()
    if FIXTURE_ENV.exists():
        for k, v in _parse_env_file(FIXTURE_ENV).items():
            os.environ.setdefault(k, v)

    approve_id = args.approve_id or os.environ.get("MAESTRO_LEAVE_ID") or os.environ.get("MOBILE_E2E_LEAVE_APPROVE_ID") or ""
    reject_id = args.reject_id or os.environ.get("MAESTRO_LEAVE_REJECT_ID") or os.environ.get("MOBILE_E2E_LEAVE_REJECT_ID") or ""

    evid = Path(args.evidence) if args.evidence else ROOT / "ops" / "evidence" / f"mobile-e2e-leave-reconcile-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    evid.mkdir(parents=True, exist_ok=True)

    base, token = login()
    report: dict = {"checks": {}}
    ok = True
    if approve_id:
        detail = leave_detail(base, token, approve_id)
        passed = detail["status"] == args.expect_approve and detail["allowed_actions"] == []
        report["checks"]["approve"] = {"pass": passed, "expect": args.expect_approve, **detail}
        ok = ok and passed
    if reject_id:
        detail = leave_detail(base, token, reject_id)
        passed = detail["status"] == args.expect_reject and detail["allowed_actions"] == []
        # rejection reason should persist when present
        note_ok = True
        if args.expect_reject == "rejected":
            note = (detail.get("decision_note") or "").strip()
            note_ok = bool(note)
            report["checks"]["reject_reason_persisted"] = bool(note)
        report["checks"]["reject"] = {"pass": passed and note_ok, "expect": args.expect_reject, **detail}
        ok = ok and passed and note_ok

    report["ok"] = ok
    report["rule"] = "API/DB reconcile supports MOBILE_PASS but cannot replace it"
    (evid / "leave-reconcile.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
