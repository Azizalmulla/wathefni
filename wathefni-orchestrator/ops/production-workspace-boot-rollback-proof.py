#!/usr/bin/env python3
"""Prove production workspace boot OFF rollback (legacy fallback)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8010"
PHONE = "96599338566"


def dash_token() -> str:
    # Prefer live systemd drop-ins over postgres.env (which may hold a stale token).
    candidates: list[Path] = list(Path("/etc/systemd/system/wathefni-orchestrator.service.d").glob("*.conf"))
    candidates.extend(
        [
            Path("/root/.openclaw/secrets/postgres.env"),
            Path("/root/.openclaw/secrets/wathefni-dashboard.env"),
        ]
    )
    for path in candidates:
        if not path.exists():
            continue
        text = path.read_text()
        match = re.search(r"WATHEFNI_DASHBOARD_TOKEN=([^\n]+)", text)
        if match:
            return match.group(1).strip().strip('"').strip("'")
        for _, env_path in re.findall(r"EnvironmentFile=(-?)([^\s]+)", text):
            env_file = Path(env_path)
            if env_file.exists():
                match = re.search(r"WATHEFNI_DASHBOARD_TOKEN=([^\n]+)", env_file.read_text())
                if match:
                    return match.group(1).strip().strip('"').strip("'")
    raise SystemExit("dashboard token not found")


def req(path: str, headers: dict):
    request = urllib.request.Request(BASE + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def main() -> None:
    token = dash_token()
    headers = {"Authorization": f"Bearer {token}", "X-HR-Phone": PHONE, "X-Company-Code": "WATHEFNI"}
    status, body = req("/dashboard/bootstrap", headers)
    print("bootstrap_off", status, body if status != 200 else "UNEXPECTED_200")
    assert status == 404, status
    status, body = req("/dashboard/prehire/summary", headers)
    print("legacy_summary", status, "modules=", body.get("enabled_modules") if isinstance(body, dict) else body)
    assert status == 200, status
    status, _ = req("/dashboard/team", headers)
    print("team_off", status)
    assert status == 200, status
    print("ROLLBACK_OFF_PROOF_OK")


if __name__ == "__main__":
    main()
