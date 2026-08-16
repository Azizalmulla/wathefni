#!/usr/bin/env python3
"""Static frontend endpoint ↔ FastAPI route / permission / audit inventory."""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVID = Path(os.environ["INTERACTION_AUDIT_EVID"])
ORCHESTRATOR = ROOT / "wathefni-orchestrator"
BACKEND_FILES = [
    file
    for file in ORCHESTRATOR.rglob("*.py")
    if ".venv" not in file.parts
    and "__pycache__" not in file.parts
    and not file.name.startswith("test_")
]
FRONTEND_ROOTS = [
    ROOT / "apps/wathefni-dashboard/src",
    ROOT / "apps/wathefni-employee-mobile",
]
FRONTEND_FILES = [
    file
    for frontend_root in FRONTEND_ROOTS
    for file in frontend_root.rglob("*")
    if file.suffix in {".ts", ".tsx", ".js", ".jsx"}
    and not any(part in {"node_modules", "dist", ".expo"} for part in file.parts)
    and not re.search(r"\.(?:test|spec)\.[jt]sx?$", file.name)
]


def normalize_route(route: str) -> str:
    route = route.split("?")[0]
    route = re.sub(r"\$\{[^}]+\}", "{param}", route)
    route = re.sub(r"\{[^}]+\}", "{param}", route)
    route = re.sub(r"/+", "/", route)
    return route.rstrip("/") or "/"


backend: list[dict] = []

for backend_file in BACKEND_FILES:
    source = backend_file.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        continue
    lines = source.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            method = dec.func.attr.upper()
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            if not dec.args or not isinstance(dec.args[0], ast.Constant) or not isinstance(dec.args[0].value, str):
                continue
            route = dec.args[0].value
            if not route.startswith("/"):
                continue
            fn_source = "\n".join(lines[node.lineno - 1 : (node.end_lineno or node.lineno)])
            mutation = method != "GET"
            permission_markers = re.findall(
                r"(?:require_[a-zA-Z0-9_]+|dashboard_context_has_permission|require_entitlement)\s*\([^)]*",
                fn_source,
            )
            audit_markers = re.findall(
                r"(?:record_admin_audit|record_company_activity|audit_[a-zA-Z0-9_]+|_audit)\s*\(",
                fn_source,
            )
            idempotency = bool(re.search(r"idempoten|row_version|expected_updated_at|FOR UPDATE|pending_key|busy", fn_source, re.I))
            context_auth = bool(re.search(r"Depends\(", fn_source)) or bool(permission_markers)
            raw_errors = []
            for match in re.finditer(r"detail\s*=\s*\{([^{}]{0,500})\}", fn_source, re.S):
                body = match.group(1)
                if '"error"' in body or "'error'" in body:
                    if '"message"' not in body and "'message'" not in body:
                        raw_errors.append(body.strip()[:220])
            relative_file = backend_file.relative_to(ROOT)
            backend.append(
                {
                    "method": method,
                    "route": route,
                    "normalized_route": normalize_route(route),
                    "function": node.name,
                    "line": node.lineno,
                    "mutation": mutation,
                    "context_auth": context_auth,
                    "permission_markers": permission_markers,
                    "audit_markers": audit_markers,
                    "idempotency_or_lock": idempotency,
                    "raw_error_candidates": raw_errors,
                    "exact_fix_location": f"{relative_file}:{node.lineno}",
                }
            )

frontend: list[dict] = []
endpoint_re = re.compile(r"""(?P<quote>['"`])(?P<route>/(?:dashboard|app)/[^'"`\s]+)(?P=quote)""")
for file in FRONTEND_FILES:
    text = file.read_text()
    for match in endpoint_re.finditer(text):
        route = match.group("route")
        line = text.count("\n", 0, match.start()) + 1
        before = text[max(0, match.start() - 500) : match.start()]
        method_match = re.findall(r"method\s*:\s*['\"](GET|POST|PUT|PATCH|DELETE)['\"]", before)
        method = method_match[-1] if method_match else "GET_OR_WRAPPER"
        frontend.append(
            {
                "file": str(file.relative_to(ROOT)),
                "line": line,
                "route": route,
                "normalized_route": normalize_route(route),
                "method_hint": method,
                "exact_fix_location": f"{file.relative_to(ROOT)}:{line}",
            }
        )

backend_norm = {row["normalized_route"] for row in backend}
unmatched = [
    row for row in frontend
    if row["normalized_route"] not in backend_norm
    and not row["normalized_route"].endswith("/{param}")
]

mutation_risks = []
for row in backend:
    if not row["mutation"]:
        continue
    status = "unproven"
    severity = "P3"
    issues = []
    if row["route"].startswith("/dashboard/") and not row["context_auth"]:
        issues.append("No direct auth dependency in route function; may authenticate inline or through a mounted wrapper.")
        severity = "P1"
    if not row["permission_markers"] and row["route"].startswith("/dashboard/"):
        issues.append("No direct permission marker in route function; may delegate.")
        severity = min(severity, "P1")
    if not row["audit_markers"]:
        issues.append("No direct audit marker in route function; may delegate.")
    if not row["idempotency_or_lock"]:
        issues.append("No direct idempotency/concurrency marker; may delegate.")
    if row["raw_error_candidates"]:
        issues.append("Raw error-code response candidate without message.")
    if issues:
        mutation_risks.append(
            {
                "screen": row["route"],
                "control": f"{row['method']} mutation endpoint",
                "expected_behavior": "Authenticated/authorized, concurrency-safe, audited mutation with calm errors.",
                "actual_result": " ".join(issues),
                "status": status,
                "severity": severity,
                "exact_fix_location": row["exact_fix_location"],
                "route": row,
            }
        )

summary = {
    "backend_routes": len(backend),
    "backend_mutations": sum(1 for row in backend if row["mutation"]),
    "frontend_endpoint_literals": len(frontend),
    "unmatched_frontend_candidates": len(unmatched),
    "mutation_risk_candidates": len(mutation_risks),
    "raw_error_route_candidates": sum(bool(row["raw_error_candidates"]) for row in backend),
}

(EVID / "static").mkdir(parents=True, exist_ok=True)
(EVID / "static" / "backend-routes.json").write_text(json.dumps(backend, indent=2) + "\n")
(EVID / "static" / "frontend-endpoints.json").write_text(json.dumps(frontend, indent=2) + "\n")
(EVID / "static" / "unmatched-endpoint-candidates.json").write_text(json.dumps(unmatched, indent=2) + "\n")
(EVID / "static" / "mutation-risk-candidates.json").write_text(json.dumps(mutation_risks, indent=2) + "\n")
(EVID / "static" / "route-permission-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary))
