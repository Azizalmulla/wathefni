#!/usr/bin/env python3
"""Setup Console P2–P4 — catalog/HTTP honesty, policies IA, no WATHEFNI enablement.

Live HTTP uses the disposable local test API only. Production databases and
WATHEFNI module entitlement writes are refused.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib import error, request

PASS = 0
FAIL = 0

ROOT = Path(__file__).resolve().parent
DASH = ROOT.parent / "apps" / "wathefni-dashboard" / "src" / "setup-console"
LOGIN_FILE = Path("/tmp/wathefni-setup-console-op-qual.login")
API_BASE = os.environ.get("WATHEFNI_API_BASE", "http://127.0.0.1:8010").rstrip("/")
SYNTHETIC = f"P2P4{uuid.uuid4().hex[:6].upper()}"[:12]
PROTECTED = {"WATHEFNI", "OCTOHR", "OCTOHR-STORE-REVIEW"}
PRODUCTION_DATABASES = {"wathefni", "wathefni_prod", "wathefni_production"}
ENTERPRISE_HTTP = (
    "/dashboard/performance",
    "/dashboard/talent",
    "/dashboard/job-architecture",
    "/dashboard/learning",
    "/dashboard/benefits",
    "/dashboard/employee-relations",
    "/dashboard/engagement",
    "/dashboard/compensation-planning",
    "/dashboard/workforce-planning",
)
CATALOG_ENTERPRISE = (
    "performance",
    "talent",
    "learning",
    "benefits",
    "employee_relations",
    "engagement",
    "comp_planning",
    "workforce_planning",
    "analytics",
)


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {str(detail)[:240]}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _parse_login(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        out[key.strip().upper()] = value.strip()
    return out


def _req(
    method: str,
    path: str,
    *,
    token: str = "",
    phone: str = "",
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if phone:
        headers["X-HR-Phone"] = phone
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = request.Request(API_BASE + path, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            payload: Any
            try:
                payload = json.loads(raw) if raw else {}
            except Exception:
                payload = {"raw": raw[:300]}
            return resp.status, payload
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"raw": raw[:300]}
        return exc.code, payload
    except Exception as exc:
        return 0, {"error": type(exc).__name__, "message": str(exc)[:200]}


def source_checks() -> None:
    print("    SETUP CONSOLE P2–P4 — source")
    catalog = (ROOT / "module_catalog.py").read_text(encoding="utf-8")
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    eff = (ROOT / "setup_console_effective_state.py").read_text(encoding="utf-8")
    setup_app = (DASH / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
    modules_card = (DASH / "ModulesAccessCard.tsx").read_text(encoding="utf-8")
    policies = (DASH / "PoliciesWorkflowsPage.tsx").read_text(encoding="utf-8")
    url_state = (DASH / "urlState.ts").read_text(encoding="utf-8")
    sys.path.insert(0, str(ROOT))
    import module_catalog as catalog_mod

    for key in CATALOG_ENTERPRISE:
        check(f"git catalog includes {key}", f'"{key}"' in catalog and key in catalog_mod.MODULE_KEYS)
    check("JA is not a catalog SKU", "job_architecture" not in catalog_mod.MODULE_KEYS)
    check("app registers performance HTTP", "register_performance_http" in app_src)
    check("app registers JA HTTP", "register_job_architecture_http" in app_src)
    check("app registers ER HTTP", "register_employee_relations_http" in app_src)
    check("app registers comp planning HTTP", "register_compensation_planning_http" in app_src)
    check("app registers WFP HTTP", "register_workforce_planning_http" in app_src)
    check("PATCH refuses unusable enables", "cannot_enable_unusable" in app_src)
    check("company GET uses annotate_setup_catalog", "annotate_setup_catalog" in app_src)
    check("last module change uses action_results", "setup_console_last_module_change" in app_src)
    check("effective-state is the honesty authority", "annotate_catalog_module" in eff)
    check("policies is a workspace view", "'policies'" in url_state)
    check("wave hashes open policies, not classic", "classic-wave" in url_state and "return 'policies'" in url_state)
    check("Modules & Access confirms before apply", "Apply module changes?" in modules_card)
    check("Modules & Access shows last change", "last-module-change" in modules_card)
    check("Policies page gates Wave 4–6", "isPolicySurfaceReady" in policies)
    check("Classic no longer mounts Wave 4 cards", "Wave4PerformancePoliciesCard" not in setup_app)
    check("Policies page is the Wave 4 host", "Wave4PerformancePoliciesCard" in policies)
    check("WATHEFNI allowlist is not edited here", "OCTOHR-STORE-REVIEW" in (ROOT / "smoke-test-setup-console-p0-p1.py").read_text(encoding="utf-8"))


def live_checks() -> None:
    print("    SETUP CONSOLE P2–P4 — live disposable API")
    db_name = (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "").strip().lower()
    env_name = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    check("live target is not a production database name", db_name not in PRODUCTION_DATABASES, db_name)
    check("live target env is test", env_name in {"test", "local", "dev", ""}, env_name)
    if db_name in PRODUCTION_DATABASES:
        check("refusing live mutations against production", False, db_name)
        return

    health_status, health = _req("GET", "/health")
    check("local API health", health_status == 200, health)
    unauth_status, _unauth = _req("GET", "/dashboard/superadmin/setup/companies")
    check("operator API without auth is 401", unauth_status == 401, unauth_status)
    hr_status, _hr = _req(
        "GET",
        "/dashboard/superadmin/setup/companies",
        token="not-an-operator-token",
        phone="96550000000",
    )
    check("HR-shaped credentials are rejected", hr_status in {401, 403}, hr_status)

    for prefix in ENTERPRISE_HTTP:
        status, _payload = _req("GET", prefix + "/workspace")
        check(f"{prefix} is registered (not 404)", status in {200, 401, 403, 405, 422}, status)

    creds = _parse_login(LOGIN_FILE)
    if not creds.get("EMAIL") or not creds.get("PASSWORD"):
        check("disposable operator login file present", False, str(LOGIN_FILE))
        return
    login_status, login = _req(
        "POST",
        "/dashboard/superadmin/setup/auth/login",
        body={"email": creds["EMAIL"], "password": creds["PASSWORD"]},
    )
    check("operator password login", login_status == 200 and bool(login.get("access_token")), login_status)
    access = str(login.get("access_token") or "")
    phone = str(login.get("phone") or creds.get("PHONE") or "")
    if not access:
        return

    search_status, search = _req(
        "GET",
        "/dashboard/superadmin/setup/companies?q=WATHEFNI&limit=20&offset=0",
        token=access,
        phone=phone,
    )
    codes = [str(item.get("company_code") or "").upper() for item in (search.get("companies") or [])]
    check("search q=WATHEFNI succeeds", search_status == 200, search_status)
    check("search finds WATHEFNI", "WATHEFNI" in codes, codes[:8])

    detail_status, detail = _req(
        "GET",
        "/dashboard/superadmin/setup/companies/WATHEFNI",
        token=access,
        phone=phone,
    )
    check("GET WATHEFNI company succeeds", detail_status == 200, detail_status)
    modules = {str(item.get("key")): item for item in (detail.get("available_modules") or [])}
    import module_catalog as catalog_mod

    check("GET catalog keys match git MODULE_KEYS", set(modules) == set(catalog_mod.MODULE_KEYS), sorted(set(modules) ^ set(catalog_mod.MODULE_KEYS)))
    for key in CATALOG_ENTERPRISE:
        check(f"WATHEFNI catalog includes {key}", key in modules)
    perf = modules.get("performance") or {}
    perf_state = (perf.get("effective_state") or {}).get("effective_state")
    check("WATHEFNI performance is not enabled_usable", perf_state != "enabled_usable", perf_state)
    check("WATHEFNI performance cannot_enable", perf.get("can_enable") is not True, perf.get("can_enable"))
    check("WATHEFNI last_module_change key present", "last_module_change" in detail)

    policies_status, policies = _req(
        "GET",
        "/dashboard/superadmin/setup/companies/WATHEFNI/module-policies",
        token=access,
        phone=phone,
    )
    check("Wave 4–6 GET module-policies does not 500", policies_status == 200, {"status": policies_status, "error": (policies or {}).get("error") or (policies or {}).get("detail")})
    check("wave4 payload present", isinstance(policies.get("wave4"), dict), list((policies.get("wave4") or {}).keys())[:8] if isinstance(policies.get("wave4"), dict) else policies_status)
    check("wave6 payload present", isinstance(policies.get("wave6"), dict), policies_status)
    check("wave5 payload present", isinstance(policies.get("wave5"), dict), policies_status)

    launch_status, launch = _req(
        "GET",
        "/dashboard/superadmin/setup/companies/WATHEFNI/launch-readiness",
        token=access,
        phone=phone,
    )
    check("Launch Readiness GET is not 422", launch_status != 422, {"status": launch_status, "detail": (launch or {}).get("detail")})
    check("Launch Readiness GET succeeds", launch_status == 200, launch_status)

    create_status, created = _req(
        "POST",
        "/dashboard/superadmin/setup/companies",
        token=access,
        phone=phone,
        body={"company_code": SYNTHETIC, "name": "P2P4 Qual", "country": "KW", "timezone": "Asia/Kuwait", "currency": "KWD"},
    )
    check("synthetic company create", create_status == 200 and SYNTHETIC not in PROTECTED, {"status": create_status, "company": SYNTHETIC})
    if create_status != 200:
        return

    leave_status, leave_body = _req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{SYNTHETIC}/modules",
        token=access,
        phone=phone,
        body={"modules": ["leave"]},
    )
    check("synthetic leave enable is allowed", leave_status == 200, {"status": leave_status, "detail": leave_body.get("detail")})
    dual = (leave_body.get("control_plane") or {}) if isinstance(leave_body, dict) else {}
    check("module save returns dual-write control plane", "dual_write" in dual or leave_status != 200, dual)

    after_status, after = _req(
        "GET",
        f"/dashboard/superadmin/setup/companies/{SYNTHETIC}",
        token=access,
        phone=phone,
    )
    after_modules = {str(item.get("key")): item for item in ((after or {}).get("available_modules") or [])}
    check("synthetic GET after leave", after_status == 200)
    check("leave stored on synthetic company", bool((after_modules.get("leave") or {}).get("configured")), after_modules.get("leave"))
    check("synthetic last change recorded", bool(((after or {}).get("last_module_change") or {}).get("at")), (after or {}).get("last_module_change"))

    perf_patch_status, perf_patch = _req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{SYNTHETIC}/modules",
        token=access,
        phone=phone,
        body={"modules": ["leave", "performance"]},
    )
    detail_obj = perf_patch.get("detail") if isinstance(perf_patch, dict) else None
    if not isinstance(detail_obj, dict):
        detail_obj = perf_patch if isinstance(perf_patch, dict) else {}
    check(
        "synthetic performance enable is 409 cannot_enable_unusable",
        perf_patch_status == 409 and detail_obj.get("error") == "cannot_enable_unusable",
        {"status": perf_patch_status, "detail": detail_obj},
    )

    comp_status, comp_body = _req(
        "PATCH",
        f"/dashboard/superadmin/setup/companies/{SYNTHETIC}/modules",
        token=access,
        phone=phone,
        body={"modules": ["leave", "comp_planning"]},
    )
    comp_detail = comp_body.get("detail") if isinstance(comp_body, dict) else None
    if not isinstance(comp_detail, dict):
        comp_detail = comp_body if isinstance(comp_body, dict) else {}
    check(
        "comp planning without JA is blocked",
        comp_status in {409, 422},
        {"status": comp_status, "detail": comp_detail},
    )

    wathefni_modules = sorted(key for key, item in modules.items() if item.get("configured") or item.get("stored_enabled"))
    check("WATHEFNI stored modules were not rewritten", "performance" not in wathefni_modules, wathefni_modules)
    check("synthetic code is not WATHEFNI", SYNTHETIC not in PROTECTED, SYNTHETIC)


def main() -> int:
    os.environ.setdefault("WATHEFNI_PERFORMANCE_GOALS_COMPANIES", "OCTOHR-STORE-REVIEW")
    source_checks()
    live_checks()
    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("SETUP_CONSOLE_P2_P4_FAIL")
        return 1
    print("SETUP_CONSOLE_P2_P4_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
