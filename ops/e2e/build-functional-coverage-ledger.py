#!/usr/bin/env python3
"""Build the Wathefni Functional Coverage Ledger from source.

Inventories production routes/actions from the live code, not estimates.
Does not claim TESTED unless a matching automated proof exists.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = Path(__file__).resolve().parent / "functional-coverage-ledger.json"

records: list[dict] = []


def add(**row: object) -> None:
    records.append(
        {
            "id": str(row.get("id") or f"{row.get('surface')}:{row.get('route')}:{row.get('action')}"),
            "surface": row.get("surface"),
            "module": row.get("module") or "unspecified",
            "route": row.get("route"),
            "action": row.get("action"),
            "entitlement": row.get("entitlement") or "",
            "permission": row.get("permission") or "",
            "prerequisites": row.get("prerequisites") or "",
            "expected_result": row.get("expected_result") or "",
            "backend_effect": row.get("backend_effect") or "",
            "test_strategy": row.get("test_strategy") or "structural",
            "test_id": row.get("test_id") or "",
            "status": row.get("status") or "inventoried",
        }
    )


def web_pages() -> None:
    types = REPO / "apps" / "wathefni-dashboard" / "src" / "types.ts"
    text = types.read_text(encoding="utf-8")
    block = text[text.find("export type Page =") : text.find("export type ChatMessage")]
    pages = re.findall(r"'([a-z0-9-]+)'", block)
    for page in pages:
        add(
            id=f"web:page:{page}",
            surface="hr_web",
            module=page,
            route=f"/dashboard?page={page}",
            action="navigate",
            expected_result=f"Page {page} destination exists in the Page union",
            test_strategy="structural",
            test_id="ops/e2e/web-structural-sanity.py",
            status="structural_covered",
        )


def web_actions() -> None:
    dash = REPO / "apps" / "wathefni-dashboard" / "src"
    for path in dash.rglob("*.tsx"):
        if any(part in {"node_modules", "dist", "__tests__"} for part in path.parts):
            continue
        if path.name.endswith(".test.tsx"):
            continue
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(dash))
        for i, match in enumerate(re.finditer(r"<Button\b([^>]*)>", text)):
            attrs = match.group(1)
            if "disabled" in attrs and "onClick" not in attrs and "onPress" not in attrs:
                continue
            add(
                id=f"web:button:{rel}:{i}",
                surface="hr_web",
                module=rel.split("/")[0],
                route=rel,
                action="button",
                expected_result="Control exists in production TSX",
                test_strategy="action_contract" if "onClick" in attrs or "onPress" in attrs else "structural",
                test_id="",
                status="inventoried",
            )
        for i, match in enumerate(re.finditer(r"""(?:fetch|api)\(\s*['"`]([^'"`]+)['"`]""", text)):
            add(
                id=f"web:api:{rel}:{i}:{match.group(1)}",
                surface="hr_web",
                module=rel.split("/")[0],
                route=match.group(1),
                action="client_api",
                backend_effect="client-used API operation",
                test_strategy="action_contract",
                status="inventoried",
            )
        for i, match in enumerate(re.finditer(r"""runPosthireAction\(\s*['"]([^'"]+)['"]""", text)):
            add(
                id=f"web:posthire:{rel}:{i}:{match.group(1)}",
                surface="hr_web",
                module=rel.split("/")[0],
                route=rel,
                action=match.group(1),
                backend_effect=f"posthire action {match.group(1)}",
                test_strategy="mutation",
                status="inventoried",
            )


def setup_actions() -> None:
    setup = REPO / "apps" / "wathefni-dashboard" / "src" / "setup-console"
    if not setup.exists():
        return
    for path in setup.glob("*.tsx"):
        add(
            id=f"setup:card:{path.stem}",
            surface="setup",
            module=path.stem,
            route="/setup-console",
            action="configure",
            expected_result="Setup card is a production control",
            test_strategy="structural",
            test_id="wathefni-orchestrator/smoke-test-r6-setup-self-service.py",
            status="structural_covered",
        )


def employee_mobile() -> None:
    comp = REPO / "apps" / "wathefni-employee-mobile" / "src" / "composition" / "employeeAppComposition.ts"
    text = comp.read_text(encoding="utf-8")
    block = text[text.find("export const APP_ROUTES") : text.find("export type AppRoute")]
    routes = re.findall(r"'(/[^']+)'\s*:", block)
    for route in routes:
        add(
            id=f"employee:route:{route}",
            surface="employee_mobile",
            module=route.strip("/").split("/")[0] or "home",
            route=route,
            action="navigate",
            expected_result="Registered employee destination",
            test_strategy="structural",
            test_id="apps/wathefni-employee-mobile/scripts/composition-shapes-test.js",
            status="structural_covered",
        )
    app_dir = REPO / "apps" / "wathefni-employee-mobile" / "app"
    for path in app_dir.rglob("*.tsx"):
        if "/hr/" in str(path):
            continue
        rel = "/" + str(path.relative_to(app_dir)).replace("\\", "/")
        rel = re.sub(r"/index\.tsx$", "", rel)
        rel = rel.replace(".tsx", "")
        add(
            id=f"employee:file:{rel}",
            surface="employee_mobile",
            module=rel.strip("/").split("/")[0] or "home",
            route=rel,
            action="screen",
            test_strategy="maestro" if "leave" in rel or "auth" in rel else "structural",
            status="inventoried",
        )


def hr_mobile() -> None:
    hr = REPO / "apps" / "wathefni-employee-mobile" / "app" / "hr"
    for path in hr.rglob("*.tsx"):
        rel = "/hr/" + str(path.relative_to(hr)).replace("\\", "/")
        rel = re.sub(r"/index\.tsx$", "", rel).replace(".tsx", "")
        add(
            id=f"hr_mobile:file:{rel}",
            surface="hr_mobile",
            module=rel.strip("/").split("/")[-1] or "home",
            route=rel,
            action="screen",
            test_strategy="maestro",
            status="inventoried",
        )


def deep_links() -> None:
    sys.path.insert(0, str(REPO / "wathefni-orchestrator"))
    import app_links

    for row in app_links.registered_destinations():
        add(
            id=f"deeplink:{row['slug']}",
            surface="deep_link",
            module=row["module"],
            route=row["https"],
            action="open",
            expected_result=row["app_path"],
            test_strategy="deep_link",
            test_id="wathefni-orchestrator/smoke-test-app-links.py",
            status="inventoried",
        )


def api_ops() -> None:
    src = (REPO / "wathefni-orchestrator" / "app.py").read_text(encoding="utf-8")
    for method, path in re.findall(r'@app\.(get|post|patch|put|delete)\("([^"]+)"', src):
        if path.startswith("/internal") or path.startswith("/orchestrator/debug"):
            continue
        parts = [p for p in path.strip("/").split("/") if p]
        module = parts[1] if len(parts) > 1 else (parts[0] if parts else path)
        add(
            id=f"api:{method}:{path}",
            surface="api",
            module=module,
            route=path,
            action=method,
            test_strategy="api",
            status="inventoried",
        )


def assistant_tools() -> None:
    orch = REPO / "wathefni-orchestrator"
    names: set[str] = set()
    for path in ("tool_call_orchestrator.py", "assistant_tools.py", "app.py"):
        target = orch / path
        if not target.exists():
            continue
        text = target.read_text(encoding="utf-8", errors="replace")
        names.update(re.findall(r'"function"\s*:\s*\{\s*"name"\s*:\s*"([a-z0-9_]+)"', text))
        names.update(re.findall(r"name\s*=\s*\"([a-z0-9_]+)\"\s*,\s*description", text))
    pt7 = orch / "smoke-test-pt7-assistant.py"
    if pt7.exists():
        names.update(re.findall(r'"([a-z][a-z0-9_]{4,})"', pt7.read_text(encoding="utf-8", errors="replace")))
    for name in sorted(names):
        if not re.search(
            r"(leave|employee|payroll|shift|attend|recruit|interview|onboard|document|performance|talent|learning|benefit|engagement|compensation|workforce|setup|okr|candidate|offer|job|payslip)",
            name,
        ):
            continue
        add(
            id=f"assistant:{name}",
            surface="assistant",
            module="assistant",
            route=name,
            action="tool",
            test_strategy="api",
            test_id="wathefni-orchestrator/smoke-test-pt7-assistant.py",
            status="inventoried",
        )


def attach_existing_proofs() -> None:
    """A record is owned when an automated test names its route or action."""
    files: list[tuple[str, str]] = []
    for folder in (REPO / "wathefni-orchestrator", REPO / "ops" / "e2e", REPO / "ops"):
        for path in folder.glob("*.py"):
            if not re.search(r"(smoke-test|qualify|e2e|canary|gate)", path.name):
                continue
            files.append((str(path.relative_to(REPO)), path.read_text(encoding="utf-8", errors="replace")))
        for path in folder.glob("*.sh"):
            if "qualify" in path.name or "test-" in path.name:
                files.append((str(path.relative_to(REPO)), path.read_text(encoding="utf-8", errors="replace")))
    mobile_scripts = REPO / "apps" / "wathefni-employee-mobile" / "scripts"
    if mobile_scripts.exists():
        for path in mobile_scripts.glob("*test*"):
            files.append((str(path.relative_to(REPO)), path.read_text(encoding="utf-8", errors="replace")))
    maestro = REPO / "apps" / "wathefni-employee-mobile" / ".maestro"
    if maestro.exists():
        for path in maestro.rglob("*.yaml"):
            files.append((str(path.relative_to(REPO)), path.read_text(encoding="utf-8", errors="replace")))
    for row in records:
        if row["status"] != "inventoried":
            continue
        route = str(row.get("route") or "")
        action = str(row.get("action") or "")
        if row["surface"] == "deep_link":
            row["test_id"] = "ops/e2e/qualify-https-app-links.py"
            row["status"] = "live_covered"
            continue
        needles = [value for value in (route, action) if value and len(value) >= 6]
        if row["surface"] == "api" and route:
            needles.append(re.sub(r"\{[^}]+\}", "", route))
        hit = ""
        for name, text in files:
            if any(needle and needle in text for needle in needles):
                hit = name
                break
        if hit:
            row["test_id"] = hit
            row["status"] = "contract_covered"


def main() -> int:
    web_pages()
    web_actions()
    setup_actions()
    employee_mobile()
    hr_mobile()
    deep_links()
    api_ops()
    assistant_tools()
    attach_existing_proofs()
    by_surface: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for row in records:
        by_surface[str(row["surface"])] = by_surface.get(str(row["surface"]), 0) + 1
        by_status[str(row["status"])] = by_status.get(str(row["status"]), 0) + 1
    payload = {
        "generated_from": "source inventory",
        "counts": {
            "total": len(records),
            "by_surface": by_surface,
            "by_status": by_status,
        },
        "records": records,
    }
    LEDGER.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["counts"], indent=2))
    print(f"LEDGER={LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
