#!/usr/bin/env python3
"""Audit ownership and security scope for every mounted client API operation.

This is intentionally not a browser suite. It combines the mounted FastAPI
table, canonical dependency graph, route-specific domain proof ownership, and
client source references. Live unauthenticated behavior is checked separately
by api-fail-closed-probe.py; the owned suites exercise authorized state/result.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
ORCH = REPO / "wathefni-orchestrator"
LEDGER = Path(__file__).resolve().parent / "functional-coverage-ledger.json"
REQUIRED_DIMENSIONS = {
    "authorized_domain",
    "permission_module",
    "tenant_scope",
    "state_result",
    "unauthorized_fail_closed",
}
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
PREAUTH_EXACT = {
    ("POST", "/dashboard/auth/login"),
    ("POST", "/dashboard/auth/logout"),
    ("POST", "/dashboard/mobile/auth/login"),
    ("POST", "/dashboard/mobile/auth/refresh"),
    ("POST", "/dashboard/mobile/auth/logout"),
    ("POST", "/dashboard/telemetry/error"),
    ("POST", "/dashboard/mobile/telemetry/error"),
    ("POST", "/app/telemetry/error"),
    ("POST", "/dashboard/team/invites/accept"),
    ("POST", "/dashboard/superadmin/setup/auth/login"),
    ("POST", "/dashboard/superadmin/setup/auth/refresh"),
    ("POST", "/dashboard/superadmin/setup/auth/logout"),
    ("GET", "/dashboard/platform/integrations/oauth/callback"),
    ("GET", "/dashboard/prehire/integrations/mailbox/callback"),
    ("POST", "/app/auth/activate"),
    ("POST", "/app/auth/request-code"),
    ("POST", "/app/auth/refresh"),
    ("POST", "/app/auth/logout"),
}
PUBLIC_PREFIXES = (
    "/health",
    "/ready",
    "/setup-console",
    "/calendar/guest/",
    "/assessment/",
    "/video-interview/",
    "/offer/",
    "/webhook/",
    "/telemetry/",
    "/l",
    "/.well-known/",
    "/apple-app-site-association",
)
PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        suffix = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{suffix}")


def dependency_names(route: Any) -> set[str]:
    names: set[str] = set()
    stack = list(getattr(getattr(route, "dependant", None), "dependencies", []) or [])
    while stack:
        dependency = stack.pop()
        call = getattr(dependency, "call", None)
        name = getattr(call, "__name__", "")
        if name:
            names.add(name)
        stack.extend(getattr(dependency, "dependencies", []) or [])
    return names


def public_or_preauth(method: str, path: str) -> bool:
    if (method, path) in PREAUTH_EXACT:
        return True
    if path in {"/dashboard", "/dashboard/"} or path == "/dashboard/{asset_path:path}":
        return True
    return path.startswith(PUBLIC_PREFIXES)


def route_pattern(path: str) -> re.Pattern[str]:
    escaped = re.escape(path)
    escaped = re.sub(r"\\\{[^}]+:path\\\}", ".+", escaped)
    escaped = re.sub(r"\\\{[^}]+\\\}", "[^/]+", escaped)
    return re.compile(f"^{escaped}$")


def client_literal_paths() -> set[str]:
    roots = [
        REPO / "apps" / "wathefni-dashboard" / "src" / "lib",
        REPO / "apps" / "wathefni-dashboard" / "src" / "setup-console",
        REPO / "apps" / "wathefni-employee-mobile",
        REPO / "apps" / "wathefni-hr-mobile" / "src",
    ]
    found: set[str] = set()
    literal = re.compile(r'''["'`](/(?:dashboard|app|assessment|video-interview|calendar|offer)/[^"'`\s]*)''')
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix not in {".ts", ".tsx", ".js", ".jsx"} or ".test." in path.name or any(part in {"node_modules", "dist", "dist-preview"} for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in literal.finditer(text):
                value = match.group(1).split("?", 1)[0]
                value = re.sub(r"\$\{[^}]+\}", "probe", value)
                if value and "*" not in value:
                    found.add(value)
    return found


def main() -> int:
    print("    client API contract coverage — mounted routes + proof ownership")
    sys.path.insert(0, str(ORCH))
    import app

    schema = app.app.openapi()
    check("OpenAPI schema builds without unresolved route annotations", bool(schema.get("paths")))

    mounted: dict[tuple[str, str], dict[str, Any]] = {}
    duplicates: dict[tuple[str, str], list[str]] = defaultdict(list)
    for route in app.app.routes:
        path = str(getattr(route, "path", "") or "")
        if not path or path.startswith(("/internal", "/orchestrator/debug", "/openapi", "/docs", "/redoc")):
            continue
        for method in sorted(getattr(route, "methods", set()) or set()):
            if method in {"HEAD", "OPTIONS"}:
                continue
            key = (method, path)
            name = str(getattr(route, "name", "") or "")
            duplicates[key].append(name)
            mounted.setdefault(
                key,
                {
                    "endpoint": name,
                    "source_module": str(getattr(getattr(route, "endpoint", None), "__module__", "") or ""),
                    "auth_dependencies": dependency_names(route),
                },
            )

    duplicate_conflicts = {
        f"{method} {path}": names
        for (method, path), names in duplicates.items()
        if len(names) > 1
    }
    check("mounted route keys are unambiguous", not duplicate_conflicts, duplicate_conflicts)

    payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    api_rows = [row for row in payload.get("records", []) if row.get("surface") == "api"]
    ledger = {(str(row.get("action") or "").upper(), str(row.get("route") or "")): row for row in api_rows}
    check("ledger has one row per mounted operation", set(ledger) == set(mounted), {"mounted": len(mounted), "ledger": len(ledger), "missing": len(set(mounted) - set(ledger)), "stale": len(set(ledger) - set(mounted))})

    auth_failures: list[str] = []
    ownership_failures: list[str] = []
    metadata_failures: list[str] = []
    owners: set[str] = set()
    for key, details in mounted.items():
        method, path = key
        deps = set(details["auth_dependencies"])
        if not public_or_preauth(method, path) and not (deps & CANONICAL_AUTH):
            auth_failures.append(f"{method} {path} deps={sorted(deps)}")
        row = ledger.get(key) or {}
        owner = str(row.get("test_id") or "")
        if not owner or not (REPO / owner).is_file():
            ownership_failures.append(f"{method} {path} owner={owner!r}")
        else:
            owners.add(owner)
        if set(row.get("proof_dimensions") or []) != REQUIRED_DIMENSIONS:
            metadata_failures.append(f"{method} {path}: proof_dimensions")
        if str(row.get("source_module") or "") != str(details["source_module"]):
            metadata_failures.append(f"{method} {path}: source_module")
        if str(row.get("endpoint") or "") != str(details["endpoint"]):
            metadata_failures.append(f"{method} {path}: endpoint")
        if row.get("status") not in {"contract_covered", "live_covered"}:
            metadata_failures.append(f"{method} {path}: status={row.get('status')}")

    check("every private operation has canonical auth scope", not auth_failures, auth_failures[:20])
    check("every operation has an executable domain proof owner", not ownership_failures, ownership_failures[:20])
    check("every operation carries all five proof dimensions", not metadata_failures, metadata_failures[:20])

    weak_owners = []
    for owner in sorted(owners):
        text = (REPO / owner).read_text(encoding="utf-8", errors="replace")
        if not re.search(r"check|assert|expect", text, re.I) or not re.search(r"PASS|passed|pytest|vitest", text, re.I):
            weak_owners.append(owner)
    check("domain proof owners contain executable assertions", not weak_owners, weak_owners)

    patterns = [route_pattern(path) for _method, path in mounted]
    client_paths = client_literal_paths()
    unmatched_client = sorted(path for path in client_paths if not any(pattern.match(path) for pattern in patterns))
    check("literal production client API paths resolve to mounted routes", not unmatched_client, unmatched_client[:30])

    assistant_rows = [row for row in payload.get("records", []) if row.get("surface") == "assistant"]
    check("assistant tools are fully owned", len(assistant_rows) == 28 and all(row.get("status") == "contract_covered" for row in assistant_rows), {"count": len(assistant_rows), "unowned": [row.get("route") for row in assistant_rows if row.get("status") != "contract_covered"]})

    print(f"      mounted_operations={len(mounted)} proof_owners={len(owners)} literal_client_paths={len(client_paths)}")
    print(f"\n    API_CONTRACT_COVERAGE_{'PASS' if not FAIL else 'FAIL'}  {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
