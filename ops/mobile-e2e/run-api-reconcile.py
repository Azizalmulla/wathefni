#!/usr/bin/env python3
"""API/DB reconciliation spine for the mobile E2E release gate.

This proves backend truth for canary tenants. It never stamps MOBILE_PASS.
UI MOBILE_PASS rows come only from Maestro (or another real-device driver).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_secrets import load_secrets  # noqa: E402

load_secrets()

API_BASE = os.environ.get("MOBILE_E2E_API_BASE", "https://api.wathefni.ai").rstrip("/")
OUT_DIR = Path(os.environ.get("MOBILE_E2E_EVID", ".")).resolve()
HR_EMAIL = os.environ.get("MOBILE_E2E_HR_EMAIL", "").strip()
HR_PASSWORD = os.environ.get("MOBILE_E2E_HR_PASSWORD", "").strip()
HR_COMPANY = os.environ.get("MOBILE_E2E_HR_COMPANY", os.environ.get("MAESTRO_HR_COMPANY", "WATHEFNI")).strip().upper()
EMPLOYEE_BEARER = os.environ.get("MOBILE_E2E_EMPLOYEE_BEARER", "").strip()


def req(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any, dict[str, str]]:
    url = f"{API_BASE}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            return resp.status, parsed, dict(resp.headers)
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
        return err.code, parsed, dict(err.headers)
    except Exception as exc:  # network / DNS
        return 0, {"error": str(exc)}, {}


def row(id_: str, surface: str, verdict: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": id_,
        "surface": surface,
        "verdict": verdict,
        "detail": detail,
        **extra,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    rows: list[dict[str, Any]] = []

    code, health, _ = req("GET", "/healthz")
    rows.append(
        row(
            "API.health",
            "api",
            "API_SPINE" if code == 200 else "FAIL",
            f"GET /healthz → {code}",
            http=code,
        )
    )

    hr_token = None
    if HR_EMAIL and HR_PASSWORD:
        code, body, _ = req(
            "POST",
            "/dashboard/mobile/auth/login",
            body={"email": HR_EMAIL, "password": HR_PASSWORD, "company_code": HR_COMPANY},
        )
        if code == 200 and isinstance(body, dict) and body.get("access_token"):
            hr_token = body["access_token"]
            rows.append(
                row(
                    "API.hr.login",
                    "api",
                    "API_SPINE",
                    f"HR login OK company={HR_COMPANY}",
                    http=code,
                )
            )
        else:
            rows.append(
                row(
                    "API.hr.login",
                    "api",
                    "FAIL",
                    f"HR login failed → {code} {body}",
                    http=code,
                )
            )
    else:
        rows.append(
            row(
                "API.hr.login",
                "api",
                "BLOCKED",
                "Set MOBILE_E2E_HR_EMAIL + MOBILE_E2E_HR_PASSWORD to run HR API spine",
            )
        )

    if hr_token:
        for path, rid in (
            ("/dashboard/mobile/me", "API.hr.me"),
            ("/dashboard/mobile/priorities", "API.hr.priorities"),
            ("/dashboard/mobile/leave?status=requested&limit=5", "API.hr.leave.requested"),
            ("/dashboard/mobile/assistant/capabilities", "API.hr.assistant.capabilities"),
        ):
            code, body, _ = req("GET", path, token=hr_token)
            ok = code == 200
            rows.append(
                row(
                    rid,
                    "api",
                    "API_SPINE" if ok else "FAIL",
                    f"GET {path} → {code}",
                    http=code,
                )
            )

    if EMPLOYEE_BEARER:
        for path, rid in (
            ("/app/me", "API.employee.me"),
            ("/app/home", "API.employee.home"),
            ("/app/workday", "API.employee.workday"),
            ("/app/leave", "API.employee.leave"),
            ("/app/notifications?limit=5", "API.employee.notifications"),
        ):
            code, body, _ = req("GET", path, token=EMPLOYEE_BEARER)
            ok = code == 200
            rows.append(
                row(
                    rid,
                    "api",
                    "API_SPINE" if ok else "FAIL",
                    f"GET {path} → {code}",
                    http=code,
                )
            )
    else:
        rows.append(
            row(
                "API.employee.session",
                "api",
                "BLOCKED",
                "Set MOBILE_E2E_EMPLOYEE_BEARER (from activate) for employee API spine",
            )
        )

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    summary = {
        "stamp": stamp,
        "api_base": API_BASE,
        "counts": counts,
        "mobile_pass": 0,
        "note": "This script never emits MOBILE_PASS. UI driver must open the app.",
        "rows": rows,
    }
    (OUT_DIR / "api-reconcile.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"stamp": stamp, "counts": counts, "rows": len(rows)}, indent=2))
    fails = counts.get("FAIL", 0)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
