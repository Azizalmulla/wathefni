#!/usr/bin/env python3
"""OpenAPI-driven role/error/repeat safety probes for dashboard item mutations."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = os.environ.get("DASHBOARD_API", "https://api.wathefni.ai").rstrip("/")
EVID = Path(os.environ["INTERACTION_AUDIT_EVID"])
SESSION_DIR = Path(os.environ["INTERACTION_AUDIT_SESSIONS"])
ROLES = ("owner", "hr_manager", "viewer")
OPENAPI_FILE = os.environ.get("INTERACTION_AUDIT_OPENAPI_FILE", "").strip()
OUTPUT_SUFFIX = os.environ.get("INTERACTION_AUDIT_OUTPUT_SUFFIX", "").strip()
OUTPUT_SUFFIX = f"-{re.sub(r'[^a-zA-Z0-9_-]', '', OUTPUT_SUFFIX)}" if OUTPUT_SUFFIX else ""


def request(
    method: str,
    route: str,
    token: str | None = None,
    body: object | None = None,
    timeout: int = 30,
) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json", "X-Company-Code": "WATHEFNI", "X-Wathefni-Company": "WATHEFNI"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + route, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode(errors="replace")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except Exception:
                return resp.status, {"raw": raw[:500]}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw else {}
        except Exception:
            return int(exc.code), {"raw": raw[:500]}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": "network_error", "message": str(exc)}


def resolve(schema: dict, spec: dict) -> dict:
    seen = set()
    current = schema or {}
    while "$ref" in current:
        ref = current["$ref"]
        if ref in seen:
            return {}
        seen.add(ref)
        value: object = spec
        for part in ref.lstrip("#/").split("/"):
            value = value[part]  # type: ignore[index]
        current = value if isinstance(value, dict) else {}
    if "allOf" in current:
        merged: dict = {}
        for part in current["allOf"]:
            merged.update(resolve(part, spec))
        current = {**current, **merged}
    if "oneOf" in current and current["oneOf"]:
        current = {**current, **resolve(current["oneOf"][0], spec)}
    if "anyOf" in current and current["anyOf"]:
        options = [part for part in current["anyOf"] if resolve(part, spec).get("type") != "null"]
        if options:
            current = {**current, **resolve(options[0], spec)}
    return current


def sample(schema: dict, spec: dict, name: str = "") -> object:
    schema = resolve(schema, spec)
    if "default" in schema:
        return schema["default"]
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    kind = schema.get("type")
    fmt = schema.get("format")
    if kind == "object" or "properties" in schema:
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        return {key: sample(value, spec, key) for key, value in props.items() if key in required}
    if kind == "array":
        count = int(schema.get("minItems") or 0)
        return [sample(schema.get("items") or {}, spec, name) for _ in range(count)]
    if kind == "boolean":
        return False
    if kind == "integer":
        return int(schema.get("minimum") or 0)
    if kind == "number":
        return float(schema.get("minimum") or 0)
    if fmt == "uuid" or "uuid" in name.lower() or name.lower().endswith("_id"):
        return "00000000-0000-0000-0000-000000000000"
    if fmt == "date":
        return "2099-01-01"
    if fmt == "date-time":
        return "2099-01-01T00:00:00Z"
    if fmt == "email" or "email" in name.lower():
        return "interaction-audit@wathefni.invalid"
    if "phone" in name.lower():
        return "96500000000"
    if "company" in name.lower():
        return "WATHEFNI"
    minimum = int(schema.get("minLength") or 1)
    return ("interaction-audit-" + name)[: max(minimum, 32)].ljust(minimum, "x")


def calm(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    detail = payload.get("detail", payload)
    if isinstance(detail, list):
        # Framework validation is structured and not a raw internal code.
        return True
    if not isinstance(detail, dict):
        return False
    code = str(detail.get("error") or "")
    message = str(detail.get("message") or "")
    if not code:
        return True
    return bool(message) and message != code and not re.fullmatch(r"[a-z][a-z0-9_]+", message)


if OPENAPI_FILE:
    spec = json.loads(Path(OPENAPI_FILE).read_text())
else:
    st, spec_obj = request("GET", "/openapi.json")
    if st != 200 or not isinstance(spec_obj, dict):
        raise SystemExit(f"openapi unavailable status={st}")
    spec = spec_obj
sessions = {role: json.loads((SESSION_DIR / f"{role}.json").read_text()) for role in ROLES}
rows = []

for route_template, operations in sorted((spec.get("paths") or {}).items()):
    if not route_template.startswith("/dashboard/") or "{" not in route_template:
        continue
    for method_lower, operation in operations.items():
        method = method_lower.upper()
        if method not in {"POST", "PUT", "PATCH", "DELETE"} or not isinstance(operation, dict):
            continue
        route = route_template
        params = operation.get("parameters") or []
        query = {}
        for param in params:
            param = resolve(param, spec)
            name = str(param.get("name") or "")
            location = param.get("in")
            value = sample(param.get("schema") or {}, spec, name)
            if location == "path":
                route = route.replace("{" + name + "}", urllib.parse.quote(str(value), safe=""))
            elif location == "query" and param.get("required"):
                query[name] = str(value)
        if query:
            route += "?" + urllib.parse.urlencode(query)
        body_schema = (
            ((operation.get("requestBody") or {}).get("content") or {})
            .get("application/json", {})
            .get("schema")
        )
        body = sample(body_schema, spec) if isinstance(body_schema, dict) else None
        statuses = {}
        payloads = {}
        for role in ROLES:
            status, payload = request(method, route, sessions[role]["token"], body)
            statuses[role] = status
            payloads[role] = payload
        owner_status = statuses["owner"]
        repeated_status = None
        # Repeat only a failed/no-op request; never repeat a successful live mutation.
        if owner_status >= 400 or owner_status == 0:
            repeated_status, _ = request(method, route, sessions["owner"]["token"], body)
        raw_roles = [
            role for role in ROLES
            if statuses[role] >= 400 and not calm(payloads[role])
        ]
        status = "pass"
        severity = None
        actual = f"owner={statuses['owner']} hr_manager={statuses['hr_manager']} viewer={statuses['viewer']}"
        if any(code >= 500 or code == 0 for code in statuses.values()):
            status, severity = "broken", "P1"
            actual += "; server/network failure"
        elif repeated_status is not None and repeated_status != owner_status:
            status, severity = "broken", "P1"
            actual += f"; repeated failed probe changed {owner_status}->{repeated_status}"
        elif statuses["viewer"] < 400:
            status, severity = "permission mismatch", "P1"
            actual += "; restricted viewer mutation was accepted"
        elif statuses["viewer"] not in {401, 403, 404}:
            # Validation can run before route-level authorization. A 400/422 does
            # not prove the viewer can mutate, but it also does not prove the
            # permission gate. Keep this explicit instead of recording a pass.
            status, severity = "unproven", "P1"
            actual += "; viewer permission denial not reached with generated fixture"
        elif raw_roles:
            status, severity = "broken", "P2"
            actual += f"; raw/unclear errors for {','.join(raw_roles)}"
        rows.append(
            {
                "screen": route_template,
                "control": operation.get("summary") or operation.get("operationId") or f"{method} action",
                "expected_behavior": "Fail safely for a nonexistent target; permission and error behavior are consistent by role; repeated failed clicks are stable.",
                "actual_result": actual,
                "status": status,
                "severity": severity,
                "exact_fix_location": f"wathefni-orchestrator/app.py:{operation.get('operationId') or route_template}",
                "method": method,
                "route_template": route_template,
                "probe_route": route,
                "statuses": statuses,
                "repeated_owner_status": repeated_status,
                "raw_error_roles": raw_roles,
            }
        )
        print(status.upper(), method, route_template, actual)

summary = {
    "probes": len(rows),
    "status_counts": {
        name: sum(row["status"] == name for row in rows)
        for name in sorted({row["status"] for row in rows})
    },
    "server_failures": sum(any(code >= 500 or code == 0 for code in row["statuses"].values()) for row in rows),
    "raw_error_candidates": sum(bool(row["raw_error_roles"]) for row in rows),
}
(EVID / "inventory").mkdir(parents=True, exist_ok=True)
(EVID / "verify").mkdir(parents=True, exist_ok=True)
(EVID / "inventory" / f"dashboard-role-api-controls{OUTPUT_SUFFIX}.json").write_text(json.dumps(rows, indent=2) + "\n")
(EVID / "verify" / f"dashboard-role-api-summary{OUTPUT_SUFFIX}.json").write_text(json.dumps(summary, indent=2) + "\n")
print("DASHBOARD_ROLE_API_AUDIT", json.dumps(summary))
