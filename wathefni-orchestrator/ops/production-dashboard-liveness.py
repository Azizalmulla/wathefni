#!/usr/bin/env python3
"""Read-only production dashboard liveness probe after Setup Console V2 enablement."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8010"


def load_dashboard_token() -> str | None:
    paths = list(Path("/etc/systemd/system/wathefni-orchestrator.service.d").glob("*.conf"))
    paths.extend([
        Path("/root/.openclaw/secrets/postgres.env"),
        Path("/root/.openclaw/secrets/wathefni-dashboard.env"),
    ])
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text()
        match = re.search(r"WATHEFNI_DASHBOARD_TOKEN=([^\n]+)", text)
        if match:
            return match.group(1).strip().strip('"').strip("'")
        for _, env_path in re.findall(r"EnvironmentFile=(-?)([^\s]+)", text):
            env_file = Path(env_path)
            if not env_file.exists():
                continue
            match = re.search(r"WATHEFNI_DASHBOARD_TOKEN=([^\n]+)", env_file.read_text())
            if match:
                return match.group(1).strip().strip('"').strip("'")
    return None


def req(path: str, headers: dict | None = None):
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(BASE + path, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:
            return resp.status, resp.headers.get("content-type", ""), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("content-type", ""), exc.read().decode("utf-8", "replace")


def main() -> int:
    token = load_dashboard_token()
    print(f"token_found={bool(token)}")
    status, content_type, body = req("/dashboard")
    print(
        "dashboard_shell",
        status,
        content_type,
        f"has_root={('id=\"root\"' in body)}",
        f"has_asset={('dashboard-' in body)}",
    )
    if not token:
        return 1
    headers = {
        "Authorization": f"Bearer {token}",
        "X-HR-Phone": "96599338566",
        "X-Company-Code": "WATHEFNI",
    }
    for path in ("/dashboard/auth/me", "/dashboard/prehire/summary", "/dashboard/team", "/dashboard/posthire/attendance?start_date=2026-07-01&end_date=2026-07-11"):
        status, content_type, body = req(path, headers)
        snippet = body.replace("\n", " ")[:100]
        print(path, status, content_type.split(";")[0], snippet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
