#!/usr/bin/env python3
"""Debug production bootstrap auth (read-only)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8010"
PHONE = "96599338566"


def load_dashboard_token() -> tuple[str, str]:
    candidates: list[Path] = [Path("/root/.openclaw/secrets/postgres.env")]
    candidates.extend(Path("/etc/systemd/system/wathefni-orchestrator.service.d").glob("*.conf"))
    for path in candidates:
        if not path.exists():
            continue
        text = path.read_text()
        match = re.search(r"WATHEFNI_DASHBOARD_TOKEN=([^\n]+)", text)
        if match:
            return match.group(1).strip().strip('"').strip("'"), str(path)
        for _, env_path in re.findall(r"EnvironmentFile=(-?)([^\s]+)", text):
            env_file = Path(env_path)
            if env_file.exists():
                match = re.search(r"WATHEFNI_DASHBOARD_TOKEN=([^\n]+)", env_file.read_text())
                if match:
                    return match.group(1).strip().strip('"').strip("'"), str(env_file)
    raise SystemExit("dashboard token not found")


def req(path: str, headers: dict) -> None:
    request = urllib.request.Request(BASE + path, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
            print(f"{path} -> {resp.status} {raw[:400]}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        print(f"{path} -> {exc.code} {raw[:500]}")


def main() -> None:
    tok, src = load_dashboard_token()
    print(f"token_src={src} len={len(tok)} prefix={tok[:6]}...")
    headers = {
        "Authorization": f"Bearer {tok}",
        "X-HR-Phone": PHONE,
        "X-Company-Code": "WATHEFNI",
        "Content-Type": "application/json",
    }
    for path in (
        "/dashboard/auth/me",
        "/dashboard/bootstrap",
        "/dashboard/team",
        "/dashboard/prehire/summary",
        "/dashboard/posthire/attendance?start_date=2026-07-01&end_date=2026-07-11",
    ):
        req(path, headers)

    # Try legacy login with shared token to get a session.
    body = json.dumps(
        {
            "company_code": "WATHEFNI",
            "hr_phone": PHONE,
            "token": tok,
        }
    ).encode()
    request = urllib.request.Request(
        BASE + "/dashboard/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
            print("login ->", resp.status, {k: payload.get(k) for k in ("company_code", "access_token", "token", "user") if k in payload or True})
            print("login_keys", sorted(payload.keys()))
            session = payload.get("access_token") or payload.get("token") or ""
            if session:
                sh = {
                    "Authorization": f"Bearer {session}",
                    "X-Company-Code": "WATHEFNI",
                    "Content-Type": "application/json",
                }
                req("/dashboard/bootstrap", sh)
                req("/dashboard/auth/me", sh)
    except urllib.error.HTTPError as exc:
        print("login ->", exc.code, exc.read().decode()[:500])


if __name__ == "__main__":
    main()
