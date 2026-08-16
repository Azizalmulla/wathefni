#!/usr/bin/env python3
"""Provision disposable Leave fixtures for BrowserStack / Maestro mobile E2E.

Creates two requested leaves for the canary employee (Talal) under WATHEFNI:
  - approve fixture → MOBILE_E2E_LEAVE_APPROVE_ID / MAESTRO_LEAVE_ID
  - reject fixture  → MOBILE_E2E_LEAVE_REJECT_ID / MAESTRO_LEAVE_REJECT_ID

Runs against production orchestrator over SSH (same path as leave qualification).
Never prints credentials. Fixture IDs are written to a local env file (gitignored).

Usage:
  python3 ops/mobile-e2e/provision-leave-fixture.py
  python3 ops/mobile-e2e/provision-leave-fixture.py --verify-only
  python3 ops/mobile-e2e/provision-leave-fixture.py --cleanup
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_secrets import load_secrets  # noqa: E402

SSH_HOST = os.environ.get("MOBILE_E2E_SSH_HOST", "root@76.13.63.68")
COMPANY = "WATHEFNI"
SUBJECT_KEY = "WATHEFNI-96550252254"  # Talal canary — preferred disposable subject
MARKER = "wathefni_mobile_e2e_leave_fixture_v1"
LOCAL_FIXTURE_ENV = Path.home() / ".config" / "wathefni" / "e2e-fixtures.env"


REMOTE_SCRIPT = r'''
import os, sys, uuid, json
from datetime import date, timedelta

pid = os.environ["ORCH_PID"]
with open(f"/proc/{pid}/environ", "rb") as f:
    for item in f.read().split(b"\0"):
        if not item or b"=" not in item:
            continue
        k, v = item.split(b"=", 1)
        os.environ[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")

os.chdir("/opt/wathefni/orchestrator")
sys.path.insert(0, ".")
import app

COMPANY = "WATHEFNI"
SUBJECT = "WATHEFNI-96550252254"
MARKER = "wathefni_mobile_e2e_leave_fixture_v1"
MODE = os.environ.get("FIXTURE_MODE", "provision")

def stamp(purpose: str) -> str:
    return f"[{MARKER}:{purpose}] disposable BrowserStack leave fixture — safe to decide/cleanup"

with app.db_connect() as conn:
    with conn.cursor() as cur:
        if MODE == "cleanup":
            cur.execute(
                """
                UPDATE leave_requests
                   SET status='cancelled',
                       decision_note=COALESCE(decision_note,'') || ' | e2e_cleanup',
                       updated_at=now()
                 WHERE company_code=%s
                   AND employee_key=%s
                   AND status='requested'
                   AND reason LIKE %s
                """,
                (COMPANY, SUBJECT, f"%{MARKER}%"),
            )
            cleaned = cur.rowcount
            conn.commit()
            print(json.dumps({"ok": True, "mode": "cleanup", "cancelled": cleaned}))
            raise SystemExit(0)

        # Cancel prior unused e2e requested fixtures (idempotent reset)
        cur.execute(
            """
            UPDATE leave_requests
               SET status='cancelled',
                   decision_note=COALESCE(decision_note,'') || ' | e2e_reset',
                   updated_at=now()
             WHERE company_code=%s
               AND employee_key=%s
               AND status='requested'
               AND reason LIKE %s
            """,
            (COMPANY, SUBJECT, f"%{MARKER}%"),
        )

        base = date.today() + timedelta(days=21)
        # Keep dates free of weekend collisions loosely; use weekdays further out
        approve_start = base
        while approve_start.weekday() >= 5:
            approve_start += timedelta(days=1)
        reject_start = approve_start + timedelta(days=7)
        while reject_start.weekday() >= 5:
            reject_start += timedelta(days=1)

        approve_id = str(uuid.uuid4())
        reject_id = str(uuid.uuid4())
        for leave_id, start, purpose in (
            (approve_id, approve_start, "approve"),
            (reject_id, reject_start, "reject"),
        ):
            cur.execute(
                """
                INSERT INTO leave_requests (
                  leave_id, company_code, employee_key, leave_type, status,
                  start_date, end_date, reason, requested_at, updated_at, metadata
                ) VALUES (
                  %s, %s, %s, 'annual', 'requested',
                  %s, %s, %s, now(), now(),
                  %s::jsonb
                )
                """,
                (
                    leave_id,
                    COMPANY,
                    SUBJECT,
                    start,
                    start,
                    stamp(purpose),
                    json.dumps({"qa": MARKER, "purpose": purpose, "suite": "browserstack_mobile_e2e"}),
                ),
            )
        conn.commit()

        # Sanity: visible to mobile leave list path for an owner
        print(json.dumps({
            "ok": True,
            "mode": "provision",
            "company": COMPANY,
            "subject_employee_key": SUBJECT,
            "approve_leave_id": approve_id,
            "reject_leave_id": reject_id,
            "approve_start": str(approve_start),
            "reject_start": str(reject_start),
            "marker": MARKER,
        }))
'''


def ssh_run(mode: str) -> dict[str, Any]:
    remote = f"""
set -euo pipefail
export ORCH_PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
export FIXTURE_MODE={mode}
cd /opt/wathefni/orchestrator
/opt/wathefni/orchestrator/.venv/bin/python - <<'PY'
{REMOTE_SCRIPT}
PY
"""
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=25", SSH_HOST, "bash", "-s"],
        input=remote,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"SSH fixture failed rc={proc.returncode}: {proc.stderr[-800:]}")
    # Last JSON line
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        raise RuntimeError(f"No JSON from fixture SSH. stdout={proc.stdout[-500:]!r}")
    return json.loads(lines[-1])


def write_fixture_env(payload: dict[str, Any]) -> Path:
    LOCAL_FIXTURE_ENV.parent.mkdir(parents=True, exist_ok=True)
    approve = payload["approve_leave_id"]
    reject = payload["reject_leave_id"]
    content = f"""# Auto-generated by provision-leave-fixture.py — DO NOT COMMIT
# Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
MOBILE_E2E_LEAVE_APPROVE_ID={approve}
MOBILE_E2E_LEAVE_REJECT_ID={reject}
MOBILE_E2E_LEAVE_ID={approve}
MAESTRO_LEAVE_ID={approve}
MAESTRO_LEAVE_REJECT_ID={reject}
MOBILE_E2E_LEAVE_SUBJECT={SUBJECT_KEY}
MOBILE_E2E_LEAVE_MARKER={MARKER}
"""
    LOCAL_FIXTURE_ENV.write_text(content)
    LOCAL_FIXTURE_ENV.chmod(0o600)
    # Also merge into process env for callers
    os.environ["MOBILE_E2E_LEAVE_APPROVE_ID"] = approve
    os.environ["MOBILE_E2E_LEAVE_REJECT_ID"] = reject
    os.environ["MOBILE_E2E_LEAVE_ID"] = approve
    os.environ["MAESTRO_LEAVE_ID"] = approve
    os.environ["MAESTRO_LEAVE_REJECT_ID"] = reject
    return LOCAL_FIXTURE_ENV


def api_verify(leave_id: str, *, expect_status: str = "requested") -> dict[str, Any]:
    """Login as E2E HR via operator_mobile channel and fetch leave detail (sanitized)."""
    import urllib.request
    import urllib.error

    load_secrets()
    base = os.environ.get("MOBILE_E2E_API_BASE", "https://api.wathefni.ai").rstrip("/")
    email = os.environ.get("MOBILE_E2E_HR_EMAIL") or os.environ.get("MAESTRO_HR_EMAIL")
    password = os.environ.get("MOBILE_E2E_HR_PASSWORD") or os.environ.get("MAESTRO_HR_PASSWORD")
    company = os.environ.get("MOBILE_E2E_HR_COMPANY") or os.environ.get("MAESTRO_HR_COMPANY") or COMPANY
    if not email or not password:
        return {"ok": False, "error": "missing_hr_credentials"}
    login_body = json.dumps({"company_code": company, "email": email, "password": password}).encode()
    req = urllib.request.Request(
        f"{base}/dashboard/mobile/auth/login",
        data=login_body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            login = json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        return {"ok": False, "error": "mobile_login_failed", "status": err.code}
    token = login.get("access_token") or login.get("access") or ""
    if not token:
        return {"ok": False, "error": "login_no_token"}
    detail_req = urllib.request.Request(
        f"{base}/dashboard/mobile/leave/{leave_id}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(detail_req, timeout=30) as resp:
            detail = json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        return {"ok": False, "error": "leave_detail_failed", "status": err.code, "leave_id": leave_id}
    req_obj = detail.get("request") or detail
    status = req_obj.get("status")
    actions = req_obj.get("allowed_actions") or []
    return {
        "ok": status == expect_status,
        "leave_id": leave_id,
        "status": status,
        "allowed_actions": actions,
        "employee_key": (req_obj.get("employee") or {}).get("employee_key"),
        "start_date": req_obj.get("start_date"),
        "expect_status": expect_status,
        "channel": "operator_mobile",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--evidence", type=str, default="")
    args = parser.parse_args()
    load_secrets()

    evid = Path(args.evidence) if args.evidence else ROOT / "ops" / "evidence" / f"mobile-e2e-fixtures-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    evid.mkdir(parents=True, exist_ok=True)

    if args.cleanup:
        result = ssh_run("cleanup")
        (evid / "cleanup.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"phase": "cleanup", **{k: v for k, v in result.items() if k != "password"}}, indent=2))
        return 0 if result.get("ok") else 2

    if args.verify_only:
        load_secrets()
        approve = os.environ.get("MAESTRO_LEAVE_ID") or os.environ.get("MOBILE_E2E_LEAVE_APPROVE_ID")
        reject = os.environ.get("MAESTRO_LEAVE_REJECT_ID") or os.environ.get("MOBILE_E2E_LEAVE_REJECT_ID")
        if not approve or not reject:
            # also try fixture env
            if LOCAL_FIXTURE_ENV.exists():
                load_secrets()
                from load_secrets import _parse_env_file

                for k, v in _parse_env_file(LOCAL_FIXTURE_ENV).items():
                    os.environ.setdefault(k, v)
                approve = os.environ.get("MAESTRO_LEAVE_ID") or os.environ.get("MOBILE_E2E_LEAVE_APPROVE_ID")
                reject = os.environ.get("MAESTRO_LEAVE_REJECT_ID") or os.environ.get("MOBILE_E2E_LEAVE_REJECT_ID")
        checks = {
            "approve": api_verify(approve) if approve else {"ok": False, "error": "missing_approve_id"},
            "reject": api_verify(reject) if reject else {"ok": False, "error": "missing_reject_id"},
        }
        (evid / "verify.json").write_text(json.dumps(checks, indent=2) + "\n")
        print(json.dumps(checks, indent=2))
        return 0 if checks["approve"].get("ok") and checks["reject"].get("ok") else 2

    result = ssh_run("provision")
    path = write_fixture_env(result)
    verify = {
        "approve": api_verify(result["approve_leave_id"]),
        "reject": api_verify(result["reject_leave_id"]),
    }
    out = {
        "provision": {k: v for k, v in result.items()},
        "fixture_env": str(path),
        "api_verify": verify,
        "credentials_source": "~/.config/wathefni/e2e.env (not printed)",
    }
    (evid / "provision.json").write_text(json.dumps(out, indent=2) + "\n")
    # sanitized stdout
    print(
        json.dumps(
            {
                "ok": bool(result.get("ok")) and verify["approve"].get("ok") and verify["reject"].get("ok"),
                "approve_leave_id": result.get("approve_leave_id"),
                "reject_leave_id": result.get("reject_leave_id"),
                "approve_start": result.get("approve_start"),
                "reject_start": result.get("reject_start"),
                "subject_employee_key": result.get("subject_employee_key"),
                "fixture_env": str(path),
                "api_verify_ok": {
                    "approve": verify["approve"].get("ok"),
                    "reject": verify["reject"].get("ok"),
                    "approve_status": verify["approve"].get("status"),
                    "reject_status": verify["reject"].get("status"),
                    "approve_actions": verify["approve"].get("allowed_actions"),
                    "reject_actions": verify["reject"].get("allowed_actions"),
                },
                "evidence": str(evid),
            },
            indent=2,
        )
    )
    return 0 if out["api_verify"]["approve"].get("ok") and out["api_verify"]["reject"].get("ok") else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
