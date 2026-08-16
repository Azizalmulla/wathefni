#!/usr/bin/env python3
"""Live unauthorized probe for every private mounted API operation.

Only routes carrying a canonical auth dependency are probed. Public capability,
login/refresh, callback, telemetry, and static routes are deliberately excluded
rather than being mislabeled as covered. A route passes only with an explicit
401/403; validation, not-found, rate-limit, and readiness errors do not count as
authentication proof.
"""
from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LEDGER = Path(__file__).resolve().parent / "functional-coverage-ledger.json"
BASE = os.environ.get("WATHEFNI_CANARY_BASE", "http://127.0.0.1:8011").rstrip("/")
# Keep this functional proof below the deliberately small production DB pool.
# Higher concurrency turns an auth contract check into an accidental load test
# and can create transient PoolError 500s unrelated to route fail-closed logic.
WORKERS = max(1, min(int(os.environ.get("WATHEFNI_API_PROBE_WORKERS", "2")), 4))
CANONICAL_AUTH = {
    "dashboard_context",
    "prehire_dashboard_context",
    "workspace_dashboard_context",
    "assistant_dashboard_context",
    "assessments_dashboard_context",
    "superadmin_context",
    "operator_mobile_context",
    "employee_app_context",
    "require_internal_access",
    "require_internal_principal",
}


def placeholder(name: str) -> str:
    key = name.split(":", 1)[0].lower()
    if key == "kind":
        return "pifss"
    if key == "action":
        return "add"
    if "date" in key:
        return "2026-08-16"
    if key in {"module_key", "module"}:
        return "leave"
    if key in {"company_code", "company"}:
        return "API_PROBE"
    if key.endswith("_id") or key.endswith("_key") or key in {"id", "token", "code"}:
        return "00000000-0000-4000-8000-000000000000"
    if key == "asset_path":
        return "probe"
    return "probe"


def concretize(path: str) -> str:
    return re.sub(r"\{([^}]+)\}", lambda match: placeholder(match.group(1)), path)


def hit(row: dict) -> tuple[str, int, str]:
    method = str(row.get("action") or "GET").upper()
    path = concretize(str(row.get("route") or ""))
    request = Request(BASE + path, method=method, headers={"Accept": "application/json"})
    if method in {"POST", "PATCH", "PUT", "DELETE"}:
        request.data = b"{}"
        request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read(500).decode("utf-8", errors="replace")
            return f"{method} {row.get('route')}", int(response.status), body
    except HTTPError as exc:
        body = exc.read(500).decode("utf-8", errors="replace")
        return f"{method} {row.get('route')}", int(exc.code), body
    except URLError as exc:
        return f"{method} {row.get('route')}", 0, str(exc.reason)
    except Exception as exc:
        return f"{method} {row.get('route')}", 0, f"{type(exc).__name__}:{exc}"


def main() -> int:
    payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    rows = [
        row
        for row in payload.get("records", [])
        if row.get("surface") == "api"
        and set(row.get("auth_dependencies") or []) & CANONICAL_AUTH
    ]
    print(f"    API FAIL-CLOSED  {len(rows)} private operations against {BASE} workers={WORKERS}")
    failures: list[tuple[str, int, str]] = []
    passed = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(hit, row) for row in rows]
        for future in as_completed(futures):
            label, code, body = future.result()
            if code in {401, 403}:
                passed += 1
            else:
                failures.append((label, code, body[:200]))

    for label, code, body in sorted(failures)[:80]:
        print(f"      FAIL  unauth {label} -> {code} :: {body}")
    print(f"      private={len(rows)} passed={passed} failed={len(failures)}")
    print(f"\n    API_FAIL_CLOSED_{'PASS' if not failures else 'FAIL'}  {passed} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
