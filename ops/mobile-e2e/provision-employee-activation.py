#!/usr/bin/env python3
"""Provision one safe Employee activation credential for mobile release E2E.

Only the existing WATHEFNI 965549700x synthetic canaries are allowed. The
one-time code is written to the established local mode-0600 e2e.env file and
is never printed or placed in repository evidence.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_secrets import load_secrets  # noqa: E402

SECRET_FILE = Path.home() / ".config" / "wathefni" / "e2e.env"
COMPANY = "WATHEFNI"
SAFE_TARGETS = {
    "WATHEFNI-9655497001": "9655497001",
    "WATHEFNI-9655497002": "9655497002",
    "WATHEFNI-9655497003": "9655497003",
}


def api_base() -> str:
    return os.environ.get("MOBILE_E2E_API_BASE", "https://api.wathefni.ai").rstrip("/")


def ssh_host() -> str:
    return os.environ.get("MOBILE_E2E_SSH_HOST", "root@76.13.63.68")


def request_json(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    bearer: str | None = None,
) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    req = urllib.request.Request(api_base() + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": "non_json_response", "status": exc.code}
        return exc.code, payload


def detail(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("detail")
    return value if isinstance(value, dict) else payload


def replace_secret_values(updates: dict[str, str]) -> None:
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    original = SECRET_FILE.read_text(encoding="utf-8") if SECRET_FILE.is_file() else ""
    lines = original.splitlines()
    output: list[str] = []
    written: set[str] = set()
    for line in lines:
        stripped = line.strip()
        candidate = stripped[len("export ") :].strip() if stripped.startswith("export ") else stripped
        key = candidate.partition("=")[0].strip() if "=" in candidate else ""
        if key in updates:
            if key not in written:
                output.append(f"{key}={updates[key]}")
                written.add(key)
            continue
        output.append(line)
    if output and output[-1].strip():
        output.append("")
    for key, value in updates.items():
        if key not in written:
            output.append(f"{key}={value}")
    content = "\n".join(output).rstrip() + "\n"
    fd, temporary = tempfile.mkstemp(prefix="e2e.env.", dir=str(SECRET_FILE.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, SECRET_FILE)
        SECRET_FILE.chmod(0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def provision(employee_key: str) -> dict[str, Any]:
    load_secrets()
    email = os.environ.get("MOBILE_E2E_HR_EMAIL", "").strip()
    password = os.environ.get("MOBILE_E2E_HR_PASSWORD", "").strip()
    if not email or not password:
        raise RuntimeError("MOBILE_E2E_HR_EMAIL and MOBILE_E2E_HR_PASSWORD are required")
    status, login = request_json(
        "POST",
        "/dashboard/auth/login",
        body={"company_code": COMPANY, "email": email, "password": password},
    )
    bearer = str(login.get("access_token") or "")
    if status != 200 or not bearer:
        raise RuntimeError(f"HR dashboard login failed with HTTP {status}")
    permissions = {
        str(value)
        for value in ((login.get("access") or {}).get("permissions") or [])
        if str(value).strip()
    }
    required = {"employees.manage", "onboarding.manage"}
    missing = sorted(required - permissions)
    if missing:
        raise RuntimeError(
            "HR dashboard E2E account lacks required reviewed permission(s): "
            + ", ".join(missing)
            + ". Apply the existing setup_owner_bootstrap_v1 grant bundle or use an authorized owner account."
        )

    request_body: dict[str, Any] = {
        "delivery_mode": "hr_task_only",
        "idempotency_key": str(uuid.uuid4()),
        "reason": "Automated mobile store-release activation on an existing synthetic canary.",
    }
    path = f"/dashboard/posthire/employees/{employee_key}/app-invite"
    status, invited = request_json("POST", path, body=request_body, bearer=bearer)
    invite_detail = detail(invited)
    if status == 409 and invite_detail.get("error") == "pending_activation_invite_exists":
        pending = str(invite_detail.get("pending_invite_id") or "")
        if not pending:
            raise RuntimeError("pending invite response omitted pending_invite_id")
        request_body["idempotency_key"] = str(uuid.uuid4())
        request_body["supersede_invite_id"] = pending
        status, invited = request_json("POST", path, body=request_body, bearer=bearer)
    code = str(invited.get("activation_code") or "").strip()
    phone = SAFE_TARGETS[employee_key]
    if status != 200 or not invited.get("ok") or invited.get("employee_key") != employee_key:
        raise RuntimeError(f"synthetic Employee invite failed with HTTP {status}: {detail(invited).get('error', 'unknown_error')}")
    if len(code) != 6 or not code.isdigit():
        raise RuntimeError("invite response did not contain a valid six-digit one-time code")
    replace_secret_values(
        {
            "MOBILE_E2E_EMPLOYEE_PHONE": phone,
            "MOBILE_E2E_EMPLOYEE_CODE": code,
        }
    )
    return {
        "ok": True,
        "employee_key": employee_key,
        "invite_id": invited.get("invite_id"),
        "expires_at": invited.get("expires_at"),
        "secret_file": str(SECRET_FILE),
        "secret_file_mode": oct(SECRET_FILE.stat().st_mode & 0o777),
        "activation_code_disclosed": False,
    }


def verify(employee_key: str) -> dict[str, Any]:
    load_secrets()
    remote = r"""
set -euo pipefail
export ORCH_PID=$(systemctl show -p MainPID --value wathefni-orchestrator.service)
cd /opt/wathefni/orchestrator
/opt/wathefni/orchestrator/.venv/bin/python - "$1" <<'PY'
import json, os, sys
employee_key = sys.argv[1]
pid = os.environ['ORCH_PID']
with open(f'/proc/{pid}/environ', 'rb') as fh:
    for item in fh.read().split(b'\0'):
        if item and b'=' in item:
            key, value = item.split(b'=', 1)
            os.environ[key.decode()] = value.decode(errors='replace')
sys.path.insert(0, '.')
import app
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute('''
          SELECT status, redeemed_at, expires_at
          FROM employee_app_invites
          WHERE company_code='WATHEFNI' AND employee_key=%s
          ORDER BY created_at DESC LIMIT 1
        ''', (employee_key,))
        invite = dict(cur.fetchone() or {})
        cur.execute('''
          SELECT status, metadata->>'platform' AS platform, created_at, last_seen_at
          FROM employee_sessions
          WHERE company_code='WATHEFNI' AND employee_key=%s
          ORDER BY created_at DESC LIMIT 1
        ''', (employee_key,))
        session = dict(cur.fetchone() or {})
print(json.dumps({'employee_key': employee_key, 'invite': invite, 'session': session}, default=str))
PY
"""
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=25", ssh_host(), "bash", "-s", "--", employee_key],
        input=remote,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"activation verification failed with SSH rc={proc.returncode}")
    rows = [line for line in proc.stdout.splitlines() if line.strip().startswith("{")]
    if not rows:
        raise RuntimeError("activation verification produced no JSON")
    payload = json.loads(rows[-1])
    payload["ok"] = payload.get("invite", {}).get("status") == "redeemed" and payload.get("session", {}).get("status") == "active"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--employee-key", choices=sorted(SAFE_TARGETS), default="WATHEFNI-9655497001")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    result = verify(args.employee_key) if args.verify_only else provision(args.employee_key)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
