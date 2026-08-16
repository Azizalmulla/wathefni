#!/usr/bin/env python3
"""Full-web E2E — production API read probes + tenant isolation (no mutations)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("DASHBOARD_API", "https://api.wathefni.ai").rstrip("/")
SESSION = Path(os.environ.get("FULL_WEB_E2E_SESSION", "/tmp/full-web-e2e.session"))
EVID = Path(os.environ["FULL_WEB_E2E_EVID"])
OUT = EVID / "verify" / "api-results.json"

ROUTES = [
    ("overview", "GET", "/dashboard/prehire/summary"),
    ("jobs", "GET", "/dashboard/prehire/positions"),
    ("candidates", "GET", "/dashboard/prehire/applications?limit=5"),
    ("interviews", "GET", "/dashboard/prehire/interviews?limit=5"),
    ("assessments", "GET", "/dashboard/prehire/assessments?tab=reports&limit=5"),
    ("calendar", "GET", "/dashboard/calendar/events?start=2026-08-01T00:00:00%2B03:00&end=2026-08-31T23:59:59%2B03:00"),
    ("employees", "GET", "/dashboard/posthire/employees?limit=5"),
    ("onboarding", "GET", "/dashboard/posthire/onboarding"),
    ("attendance", "GET", "/dashboard/posthire/attendance"),
    ("leave", "GET", "/dashboard/posthire/leave"),
    ("shifts", "GET", "/dashboard/posthire/shifts"),
    ("payroll", "GET", "/dashboard/posthire/payroll"),
    ("analytics", "GET", "/dashboard/posthire/analytics"),
    ("compliance", "GET", "/dashboard/posthire/compliance"),
    ("needs_attention", "GET", "/dashboard/posthire/action-inbox"),
    ("alerts_delivery", "GET", "/dashboard/prehire/notifications?limit=5"),
    ("activity", "GET", "/dashboard/activity?limit=5"),
    ("settings", "GET", "/dashboard/prehire/import/settings"),
    ("employee_profile", "GET", "/dashboard/posthire/employees/WATHEFNI-96550252254"),
]


def load_token() -> str:
    return SESSION.read_text().strip().splitlines()[0].strip()


def http(method: str, path: str, token: str | None, company: str | None = "WATHEFNI") -> tuple[int, str]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if company:
        headers["X-Company-Code"] = company
        headers["X-Wathefni-Company"] = company
    req = urllib.request.Request(f"{API}{path}", method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.status, resp.read().decode()[:800]
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:800] if hasattr(e, "read") else ""
        return int(e.code), body
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def main() -> int:
    (EVID / "verify").mkdir(parents=True, exist_ok=True)
    (EVID / "failures").mkdir(parents=True, exist_ok=True)
    token = load_token()
    results = []

    for module, method, path in ROUTES:
        status, body = http(method, path, token)
        # 200 OK, or 403/404 for module-disabled / not found without 500
        ok = status in {200, 403, 404} or (module == "settings" and status in {200, 404})
        # Soft: some posthire paths may 400 without query dates — still not 500
        if status == 400 and module in {"attendance", "leave", "shifts", "payroll", "calendar"}:
            ok = True
        row = {
            "id": f"API_{module}",
            "module": module,
            "title": f"{method} {path}",
            "result": "PASS" if ok else "FAIL",
            "severity": status,
            "detail": body[:240],
        }
        if not ok:
            (EVID / "failures" / f"{row['id']}.json").write_text(json.dumps(row, indent=2) + "\n")
        results.append(row)
        print(f"{row['result']} {row['id']} status={status}")

    # Tenant isolation: invalid token
    st, _ = http("GET", "/dashboard/prehire/summary", "invalid-token-full-web-e2e")
    iso1 = {"id": "API_tenant_invalid_token", "module": "cross", "title": "Invalid token fail-closed", "result": "PASS" if st in {401, 403} else "FAIL", "severity": st}
    if iso1["result"] == "FAIL":
        (EVID / "failures" / f"{iso1['id']}.json").write_text(json.dumps(iso1, indent=2) + "\n")
    results.append(iso1)
    print(f"{iso1['result']} {iso1['id']} status={st}")

    # Foreign company header must not widen
    st2, body2 = http("GET", "/dashboard/posthire/employees?limit=1", token, company="ACME_NOT_REAL")
    # Expect 403/404 or forced WATHEFNI — never leak ACME data
    leak = "ACME" in body2 and '"company_code":"ACME' in body2
    iso2_ok = st2 in {200, 403, 404} and not leak
    if st2 == 200:
        # Must still be WATHEFNI scoped
        iso2_ok = '"company_code":"WATHEFNI"' in body2 or "WATHEFNI" in body2
    iso2 = {
        "id": "API_tenant_foreign_company",
        "module": "cross",
        "title": "Foreign X-Company-Code closed",
        "result": "PASS" if iso2_ok else "FAIL",
        "severity": st2,
        "detail": body2[:200],
    }
    if iso2["result"] == "FAIL":
        (EVID / "failures" / f"{iso2['id']}.json").write_text(json.dumps(iso2, indent=2) + "\n")
    results.append(iso2)
    print(f"{iso2['result']} {iso2['id']} status={st2}")

    summary = {
        "total": len(results),
        "pass": sum(1 for r in results if r["result"] == "PASS"),
        "fail": sum(1 for r in results if r["result"] == "FAIL"),
        "results": results,
    }
    OUT.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"API_SUMMARY pass={summary['pass']} fail={summary['fail']} total={summary['total']}")
    return 1 if summary["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
