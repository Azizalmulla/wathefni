#!/usr/bin/env python3
"""Production Readiness R3 — data-safety unit contracts (no DB).

Covers the parts of the R3 blocker set that are pure logic:

  P0-6  fixture/seed/matrix tooling refuses missing env, refuses production-shaped
        targets, requires an explicit synthetic company and a non-production ack
  implicit WATHEFNI fallback  missing company never resolves to the canary tenant
  demo/build guard            production release + demo flag is rejected in source
  synthetic connectors        off by default; isolated test capability only
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PASS = 0
FAIL = 0

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _clear(*names: str) -> None:
    for name in names:
        os.environ.pop(name, None)


def _staging_env() -> None:
    os.environ["WATHEFNI_ENV"] = "staging"
    os.environ["WATHEFNI_EXPECTED_DATABASE_NAME"] = "wathefni_staging"
    os.environ["WATHEFNI_DATABASE_ENVIRONMENT_MARKER"] = "wathefni-staging-hr2-isolation-v1"
    os.environ["WATHEFNI_POSTGRES_ENV"] = "/root/.openclaw/secrets/postgres.staging.env"
    os.environ["WATHEFNI_DATA_SAFETY_ACK"] = "non-production"
    os.environ.pop("WATHEFNI_ALLOW_CANARY_FIXTURES", None)
    os.environ.pop("WATHEFNI_SYNTHETIC_CONNECTORS", None)
    os.environ.pop("WATHEFNI_SYNTHETIC_CONNECTOR_COMPANIES", None)
    os.environ.pop("WATHEFNI_SYNTHETIC_COMPANIES", None)
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("WATHEFNI_DATABASE_URL", None)
    os.environ.pop("PGDATABASE", None)


def guard_contracts() -> None:
    import production_data_safety as pds

    print("\n    P0-6 — fixture tooling fails closed")
    _clear(
        "WATHEFNI_ENV",
        "WATHEFNI_EXPECTED_DATABASE_NAME",
        "WATHEFNI_DATABASE_ENVIRONMENT_MARKER",
        "WATHEFNI_POSTGRES_ENV",
        "WATHEFNI_DATA_SAFETY_ACK",
        "DATABASE_URL",
        "PGDATABASE",
    )

    try:
        pds.require_explicit_environment()
        check("seed script with no environment refuses", False)
    except pds.DataSafetyError as exc:
        check("seed script with no environment refuses", exc.reason == "environment_required", exc.reason)

    os.environ["WATHEFNI_ENV"] = "production"
    os.environ["WATHEFNI_EXPECTED_DATABASE_NAME"] = "wathefni"
    os.environ["WATHEFNI_DATABASE_ENVIRONMENT_MARKER"] = "wathefni-production-isolation-v1"
    os.environ["WATHEFNI_POSTGRES_ENV"] = "/root/.openclaw/secrets/postgres.env"
    os.environ["WATHEFNI_DATA_SAFETY_ACK"] = "non-production"
    try:
        pds.require_fixture_tooling(company_code="R3SYNTHAA")
        check("seed script pointed at production-shaped target refuses", False)
    except pds.DataSafetyError as exc:
        check(
            "seed script pointed at production-shaped target refuses",
            exc.reason in {"production_blocked", "production_shaped_target"},
            exc.reason,
        )

    _staging_env()
    try:
        pds.require_fixture_tooling(company_code=None)
        check("missing company refuses rather than defaulting", False)
    except pds.DataSafetyError as exc:
        check("missing company refuses rather than defaulting", exc.reason == "company_required", exc.reason)

    try:
        pds.require_fixture_tooling(company_code="WATHEFNI")
        check("WATHEFNI is not an inferred fixture tenant", False)
    except pds.DataSafetyError as exc:
        check("WATHEFNI is not an inferred fixture tenant", exc.reason == "synthetic_company_required", exc.reason)

    target = pds.require_fixture_tooling(company_code="R3SYNTHAA")
    check("explicit staging synthetic tenant is accepted", target.company_code == "R3SYNTHAA")

    os.environ["WATHEFNI_ALLOW_CANARY_FIXTURES"] = "1"
    canary = pds.require_fixture_tooling(company_code="WATHEFNI")
    check("explicit canary fixtures stay opt-in on non-production", canary.company_code == "WATHEFNI")
    os.environ.pop("WATHEFNI_ALLOW_CANARY_FIXTURES", None)

    _staging_env()
    os.environ.pop("WATHEFNI_DATA_SAFETY_ACK", None)
    try:
        pds.require_fixture_tooling(company_code="R3SYNTHAA")
        check("missing non-production ack refuses", False)
    except pds.DataSafetyError as exc:
        check("missing non-production ack refuses", exc.reason == "non_production_ack_required", exc.reason)

    _staging_env()
    try:
        pds.require_destructive_scope(["*"])
        check("wildcard tenant deletion is refused", False)
    except pds.DataSafetyError as exc:
        check("wildcard tenant deletion is refused", exc.reason == "wildcard_tenant_forbidden", exc.reason)

    try:
        pds.require_destructive_scope(["WATHEFNI"])
        check("destructive matrix cannot target the canary tenant", False)
    except pds.DataSafetyError as exc:
        check(
            "destructive matrix cannot target the canary tenant",
            exc.reason in {"synthetic_company_required", "wildcard_tenant_forbidden"},
            exc.reason,
        )

    sql, params = pds.scoped_delete_company_modules(["R3SYNTHAA", "R3SYNTHBB"])
    check("scoped company_modules delete names company_code", "company_code" in sql and "ANY" in sql)
    check("scoped company_modules delete carries only named tenants", params[0] == ["R3SYNTHAA", "R3SYNTHBB"])
    check(
        "unscoped DELETE FROM company_modules is detected",
        pds.looks_like_unscoped_company_modules_delete("DELETE FROM company_modules"),
    )
    check(
        "scoped DELETE FROM company_modules is not flagged unscoped",
        not pds.looks_like_unscoped_company_modules_delete(
            "DELETE FROM company_modules WHERE company_code = ANY(%s)"
        ),
    )

    try:
        pds.refuse_protected_identities(employee_keys=["WATHEFNI-96599338566"])
        check("Aziz qualification identity cannot be mutated by fixtures", False)
    except pds.DataSafetyError as exc:
        check("Aziz qualification identity cannot be mutated by fixtures", exc.reason == "protected_identity", exc.reason)

    try:
        pds.require_production_maintenance(operation="fix-identity")
        check("production maintenance without the named ack refuses", False)
    except pds.DataSafetyError as exc:
        check(
            "production maintenance without the named ack refuses",
            exc.reason in {"maintenance_not_production", "maintenance_operation_required", "maintenance_ack_required"},
            exc.reason,
        )

    os.environ["WATHEFNI_ENV"] = "production"
    os.environ["WATHEFNI_PRODUCTION_MAINTENANCE_OPERATION"] = "fix-identity"
    os.environ["WATHEFNI_PRODUCTION_MAINTENANCE_ACK"] = pds.PRODUCTION_MAINTENANCE_ACK
    pds.require_production_maintenance(operation="fix-identity")
    check("named production maintenance with the deliberate ack is accepted", True)
    _clear("WATHEFNI_PRODUCTION_MAINTENANCE_OPERATION", "WATHEFNI_PRODUCTION_MAINTENANCE_ACK")

    _staging_env()
    pds.require_non_production_ops(company_code="R3SYNTHAA")
    check("mutating ops tooling accepts explicit staging synthetic tenant", True)
    os.environ["WATHEFNI_ENV"] = "production"
    try:
        pds.require_non_production_ops(company_code="R3SYNTHAA")
        check("mutating ops tooling pointed at production refuses", False)
    except pds.DataSafetyError as exc:
        check(
            "mutating ops tooling pointed at production refuses",
            exc.reason == "production_blocked",
            exc.reason,
        )
    _staging_env()
    try:
        pds.require_non_production_ops(company_code="WATHEFNI")
        check("mutating ops tooling does not treat WATHEFNI as an inferred tenant", False)
    except pds.DataSafetyError as exc:
        check(
            "mutating ops tooling does not treat WATHEFNI as an inferred tenant",
            exc.reason == "synthetic_company_required",
            exc.reason,
        )


def company_resolution_contracts() -> None:
    import production_data_safety as pds

    print("\n    implicit WATHEFNI company authority")
    try:
        pds.require_company_code(None)
        check("missing company code fails closed", False)
    except pds.MissingCompanyCode as exc:
        check("missing company code fails closed", exc.error == "company_required", exc.error)

    try:
        pds.require_company_code("")
        check("empty company code fails closed", False)
    except pds.MissingCompanyCode:
        check("empty company code fails closed", True)

    check("explicit legitimate tenant still resolves", pds.require_company_code("acme") == "ACME")
    check("explicit canary tenant still resolves when named", pds.require_company_code("WATHEFNI") == "WATHEFNI")
    check("missing company does not resolve to WATHEFNI", pds.normalize_company_code(None) is None)
    check("WATHEFNI is classified as canary identity, not a default", pds.CANARY_COMPANY == "WATHEFNI")
    check(
        "or-WATHEFNI snippets classify as implicit fallback",
        pds.classify_wathefni_fallback('company = (company_code or "WATHEFNI").upper()')
        == "implicit_canary_fallback",
    )


def connector_contracts() -> None:
    import production_data_safety as pds

    print("\n    synthetic connector / fixture entry points")
    _staging_env()
    check(
        "synthetic connectors are off by default",
        pds.synthetic_connectors_allowed("R3SYNTHAA") is False,
    )
    try:
        pds.require_synthetic_connector_kind("R3SYNTHAA", "deterministic_canary")
        check("creating a canary connector without the isolated capability refuses", False)
    except pds.DataSafetyError as exc:
        check(
            "creating a canary connector without the isolated capability refuses",
            exc.reason == "synthetic_connector_forbidden",
            exc.reason,
        )
    pds.require_synthetic_connector_kind("R3SYNTHAA", "sftp")
    check("non-synthetic connector kinds are unaffected", True)

    os.environ["WATHEFNI_SYNTHETIC_CONNECTORS"] = "1"
    check("isolated synthetic tenant can use the test capability", pds.synthetic_connectors_allowed("R3SYNTHAA"))
    check("WATHEFNI still cannot, even with the flag", pds.synthetic_connectors_allowed("WATHEFNI") is False)
    os.environ["WATHEFNI_SYNTHETIC_CONNECTOR_COMPANIES"] = "WATHEFNI"
    check("an explicit allowlist is required to use WATHEFNI as a test tenant", pds.synthetic_connectors_allowed("WATHEFNI"))


def process_contracts() -> None:
    import subprocess

    print("\n    live process refusals")
    seed = ROOT / "ops-seed-inbox-visual-fixture.py"
    env = {k: v for k, v in os.environ.items() if not k.startswith("WATHEFNI_")}
    env["PATH"] = os.environ.get("PATH", "")
    env["PYTHONPATH"] = str(ROOT)
    r = subprocess.run([sys.executable, str(seed)], capture_output=True, text=True, env=env)
    blob = (r.stdout or "") + (r.stderr or "")
    check("seed script with no environment refuses", r.returncode != 0 and "environment_required" in blob, blob[-400:])

    env2 = dict(env)
    env2.update(
        {
            "WATHEFNI_ENV": "production",
            "WATHEFNI_EXPECTED_DATABASE_NAME": "wathefni",
            "WATHEFNI_DATABASE_ENVIRONMENT_MARKER": "wathefni-production-isolation-v1",
            "WATHEFNI_POSTGRES_ENV": "/root/.openclaw/secrets/postgres.env",
            "WATHEFNI_DATA_SAFETY_ACK": "non-production",
            "WATHEFNI_COMPANY_CODE": "R3SYNTHAA",
        }
    )
    r = subprocess.run(
        [sys.executable, str(seed), "--company", "R3SYNTHAA", "--ack-non-production", "non-production"],
        capture_output=True,
        text=True,
        env=env2,
    )
    blob = (r.stdout or "") + (r.stderr or "")
    check(
        "seed script pointed at production-shaped target refuses (process)",
        r.returncode != 0 and ("production_blocked" in blob or "production_shaped_target" in blob),
        blob[-400:],
    )

    mobile = REPO / "apps" / "wathefni-employee-mobile"
    node = subprocess.run(
        [
            "node",
            "-e",
            "process.env.EXPO_PUBLIC_WATHEFNI_PRODUCTION_RELEASE='1';"
            "process.env.EXPO_PUBLIC_HR_HIRING_DEMO='1';"
            "try { require('./app.config.js'); console.log('LOADED'); process.exit(0); }"
            "catch (e) { console.log(String(e.message||e)); process.exit(2); }",
        ],
        cwd=str(mobile),
        capture_output=True,
        text=True,
    )
    check(
        "production mobile build cannot bake demo flags",
        node.returncode != 0 and "cannot bake demo flags" in (node.stdout + node.stderr),
        (node.stdout + node.stderr)[-400:],
    )
    node_ok = subprocess.run(
        [
            "node",
            "-e",
            "process.env.EXPO_PUBLIC_HR_HIRING_DEMO='1';"
            "try { require('./app.config.js'); console.log('LOADED'); process.exit(0); }"
            "catch (e) { console.log(String(e.message||e)); process.exit(2); }",
        ],
        cwd=str(mobile),
        capture_output=True,
        text=True,
    )
    check(
        "development preview can still enable demo flags",
        node_ok.returncode == 0 and "LOADED" in node_ok.stdout,
        (node_ok.stdout + node_ok.stderr)[-400:],
    )


def source_contracts() -> None:
    print("\n    R3 — source-level regressions that must not come back")
    live_roots = [ROOT, REPO / "ops", REPO / "apps" / "wathefni-employee-mobile", REPO / "apps" / "wathefni-hr-mobile"]
    skip_parts = {"evidence", "node_modules", ".venv", "dist", "dist-preview"}
    production_defaults = 0
    wathefni_fallback = 0
    demo_guard_files = 0
    app_config = (REPO / "apps" / "wathefni-employee-mobile" / "app.config.js").read_text(encoding="utf-8")
    check(
        "employee-mobile app.config.js fails the build when a production release bakes demo flags",
        "production release cannot bake demo flags" in app_config or "R3 data safety" in app_config,
    )
    check(
        "employee-mobile production EAS profile stamps a production-release marker",
        "EXPO_PUBLIC_WATHEFNI_PRODUCTION_RELEASE" in (REPO / "apps" / "wathefni-employee-mobile" / "eas.json").read_text(encoding="utf-8"),
    )

    app_py = (ROOT / "app.py").read_text(encoding="utf-8")
    check(
        "app.py no longer uses company_code or WATHEFNI as tenant authority",
        'company_code or "WATHEFNI"' not in app_py,
    )
    check(
        "app.py no longer uses WATHEFNI_DEFAULT_COMPANY as a routing fallback",
        "WATHEFNI_DEFAULT_COMPANY" not in app_py,
    )
    check("app.py requires company context through require_company_code", "require_company_code(" in app_py)

    for path in ROOT.glob("ops-seed-*.py"):
        text = path.read_text(encoding="utf-8")
        check(
            f"{path.name} no longer defaults WATHEFNI_ENV to production",
            'setdefault("WATHEFNI_ENV", "production")' not in text,
        )
        check(
            f"{path.name} activates the fixture guard before importing app",
            "activate_fixture_tooling_from_argv" in text or "require_fixture_tooling" in text,
        )

    matrix = ROOT / "ops" / "kuwait-pilot-document-journey-production-matrix.py"
    if matrix.exists():
        text = matrix.read_text(encoding="utf-8")
        check(
            "kuwait production matrix no longer defaults to the production database",
            'setdefault("WATHEFNI_ENV", "production")' not in text
            and 'setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")' not in text,
        )
        check(
            "kuwait production matrix uses the data-safety guard",
            "require_fixture_tooling" in text or "activate_fixture_tooling_from_argv" in text,
        )

    for root in live_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".sh", ".js", ".ts", ".tsx"}:
                continue
            if any(part in skip_parts for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            if path.name in {
                "production_data_safety.py",
                "smoke-test-r3-data-safety.py",
                "r3-data-safety-inventory.py",
            }:
                continue
            if 'os.environ.setdefault("WATHEFNI_ENV", "production")' in text or "os.environ.setdefault('WATHEFNI_ENV', 'production')" in text:
                production_defaults += 1
            if path.name == "app.py" and 'or "WATHEFNI"' in text:
                wathefni_fallback += 1
            if "demoAllowedInThisBuild" in text or "assertDemoFlagsSafe" in text:
                demo_guard_files += 1

    check("no live script setdefault WATHEFNI_ENV to production", production_defaults == 0, production_defaults)
    canary = (ROOT / "canary-prod-payroll-final.py").read_text(encoding="utf-8")
    check(
        "production-named canary scripts are hard-blocked against production",
        "require_non_production_ops" in canary and 'setdefault("WATHEFNI_ENV", "production")' not in canary,
    )
    check("app.py has no remaining or-WATHEFNI tenant fallbacks", wathefni_fallback == 0, wathefni_fallback)
    check("demo production guard is present in mobile source", demo_guard_files >= 1, demo_guard_files)


def main() -> int:
    sys.path.insert(0, str(ROOT))
    print("    PRODUCTION READINESS R3 — data-safety unit contracts")
    guard_contracts()
    company_resolution_contracts()
    connector_contracts()
    process_contracts()
    source_contracts()
    print("\n    R3_DATA_SAFETY_UNIT_PASS" if not FAIL else "\n    R3_DATA_SAFETY_UNIT_FAIL")
    print(f"    {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
