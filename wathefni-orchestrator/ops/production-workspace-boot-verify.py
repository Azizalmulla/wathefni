#!/usr/bin/env python3
"""Phase 6.5 production workspace-boot verification. Read-only; no company/invite creation."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8010"
PHONE = "96599338566"
RESULTS: list[tuple[str, bool, str]] = []


def record(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((label, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), label + (f" — {detail}" if detail else ""))


def load_dashboard_token() -> str:
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


def load_operator_token() -> str:
    raw = Path("/root/.openclaw/secrets/wathefni-setup-operator.env").read_text()
    value = re.search(r"WATHEFNI_SETUP_OPERATOR_CREDENTIALS=(.*)", raw).group(1).strip()
    if value[0] in "\"'":
        value = value[1:-1]
    return str(json.loads(value)[PHONE])


def req(method: str, path: str, headers: dict | None = None, body: dict | None = None, expect_json: bool = True):
    data = None if body is None else json.dumps(body).encode()
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(BASE + path, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            raw = resp.read()
            ct = resp.headers.get("content-type", "")
            if expect_json and "json" in ct:
                return resp.status, json.loads(raw.decode())
            return resp.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode())
        except Exception:
            payload = raw.decode("utf-8", "replace")
        return exc.code, payload


def dash_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "X-HR-Phone": PHONE, "X-Company-Code": "WATHEFNI"}


def expected_landing(enabled: set[str]) -> str:
    if "pre_hiring" in enabled:
        return "overview"
    people = {"onboarding", "compliance", "attendance", "shifts", "leave", "payroll"}
    if enabled & people:
        return "employees"
    return "settings"


def main() -> int:
    dash = load_dashboard_token()
    op = load_operator_token()

    status, health = req("GET", "/health")
    record("health 200", status == 200 and isinstance(health, dict) and health.get("status") == "ok", f"status={status}")

    status, boot = req("GET", "/dashboard/bootstrap", headers=dash_headers(dash))
    record("bootstrap 200 for WATHEFNI", status == 200 and isinstance(boot, dict), f"status={status}")
    if status != 200 or not isinstance(boot, dict):
        print("\nSUMMARY early fail")
        return 1

    enabled = set(boot.get("enabled_modules") or [])
    record("bootstrap company WATHEFNI", boot.get("company_code") == "WATHEFNI", f"company={boot.get('company_code')}")
    record("bootstrap has modules", len(enabled) > 0, f"enabled={sorted(enabled)}")
    catalog = boot.get("module_catalog") or []
    employee = next((item for item in catalog if item.get("key") == "employee_app"), {})
    record(
        "employee_app not effective / absent from HR nav",
        employee.get("effective") is not True,
        f"configured={employee.get('configured')} platform={employee.get('platform_available')} effective={employee.get('effective')}",
    )
    landing = expected_landing(enabled)
    prehire = "pre_hiring" in enabled
    posthire = bool(enabled & {"onboarding", "compliance", "attendance", "shifts", "leave", "payroll", "analytics"})
    alerts = prehire or posthire
    record(
        "nav/landing correct for WATHEFNI",
        prehire and posthire and alerts and landing == "overview",
        f"prehire={prehire} posthire={posthire} alerts={alerts} landing={landing}",
    )

    status, shell = req("GET", "/dashboard", expect_json=False)
    record(
        "existing dashboard shell loads",
        status == 200 and ('id="root"' in shell or "dashboard-" in shell),
        f"status={status}",
    )

    status, me = req("GET", "/dashboard/auth/me", headers=dash_headers(dash))
    record("auth/me loads", status == 200 and me.get("company_code") == "WATHEFNI", f"status={status}")

    status, _ = req("GET", "/dashboard/prehire/summary", headers=dash_headers(dash))
    record("Pre-Hiring summary works", status == 200, f"status={status}")

    status, _ = req(
        "GET",
        "/dashboard/posthire/attendance?start_date=2026-07-01&end_date=2026-07-11",
        headers=dash_headers(dash),
    )
    record("Post-Hire attendance works", status == 200, f"status={status}")

    status, _ = req("GET", "/dashboard/team", headers=dash_headers(dash))
    record("Team route works", status == 200, f"status={status}")

    status, page = req("GET", "/setup-console", expect_json=False)
    record("Setup Console V2 works", status == 200 and "setupConsole" in page, f"status={status}")

    status, companies = req(
        "GET",
        "/dashboard/superadmin/setup/companies?q=&limit=5&offset=0",
        headers={"Authorization": f"Bearer {op}", "X-HR-Phone": PHONE},
    )
    total = companies.get("total_count") if isinstance(companies, dict) else None
    codes = [c.get("company_code") for c in (companies.get("companies") or [])] if isinstance(companies, dict) else []
    record("Setup Console operator list works", status == 200, f"status={status} total={total} codes={codes}")
    record("no throwaway companies created", "BOOTPRE01" not in codes and "BOOTPOST01" not in codes and "BOOTMIX01" not in codes, f"codes={codes}")

    status, _ = req(
        "GET",
        "/dashboard/superadmin/setup/companies?q=&limit=1&offset=0",
        headers={"Authorization": f"Bearer {dash}", "X-HR-Phone": PHONE},
    )
    record("shared dashboard token blocked from Setup Console", status == 401, f"status={status}")

    print("NO_COMPANY_CREATED=true")
    print("NO_OWNER_INVITE_CREATED=true")
    print("\nSUMMARY")
    failed = [item for item in RESULTS if not item[1]]
    print(f"{sum(1 for item in RESULTS if item[1])} passed, {len(failed)} failed")
    if failed:
        for label, _, detail in failed:
            print(f"  - {label}: {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
