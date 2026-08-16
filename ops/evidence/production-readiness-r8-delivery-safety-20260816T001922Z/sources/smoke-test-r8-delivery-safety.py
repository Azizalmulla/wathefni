#!/usr/bin/env python3
"""Production Readiness R8 — observability / CI / migration safety (no DB)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PASS = 0
FAIL = 0

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
HR = REPO / "apps" / "wathefni-hr-mobile"
EMP = REPO / "apps" / "wathefni-employee-mobile"
DASH = REPO / "apps" / "wathefni-dashboard"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def redaction_contracts() -> None:
    import observability
    import security_rate_limit as rl

    print("\n    P1-23 — structured / redacted logging")
    dirty = {
        "password": "hunter2",
        "token": "abcd",
        "secret": "s3cret",
        "authorization": "Bearer xyz",
        "note": "call +965 5000 1111 or ceo@acme.test",
        "nested": {"operator_token": "tok", "ok": "keep"},
    }
    r2 = rl.safe_detail(dirty)
    check("R2 safe_detail still redacts password", r2["password"] == "[redacted]")
    check("R2 safe_detail still redacts token", r2["token"] == "[redacted]")
    check("R2 safe_detail still redacts nested operator_token", r2["nested"]["operator_token"] == "[redacted]")
    out = observability.redact_detail(dirty)
    check("R8 keeps R2 secret redaction", out["password"] == "[redacted]" and out["token"] == "[redacted]")
    check("R8 redacts email in remaining strings", "[redacted-email]" in out["note"])
    check("R8 redacts phone in remaining strings", "[redacted-phone]" in out["note"])
    check("R8 does not weaken diagnostic keys", out["nested"]["ok"] == "keep")
    check("unknown surface normalizes", observability.normalize_surface("wathefni-hr") == "backend")
    check("known surface kept", observability.normalize_surface("hr_mobile") == "hr_mobile")


def migration_contracts() -> None:
    import migration_framework as mf
    import schema_contract

    print("\n    migrations — versioned forward ledger")
    files = mf.list_migration_files()
    check("at least one numbered SQL file exists", bool(files), [path.name for path in files])
    check("first file is 0001", files and files[0].name.startswith("0001_"))
    check("file sequence is contiguous from 1", mf.file_sequence_errors() == [])
    sql = (ROOT / "migrations" / "0001_r8_delivery_safety.sql").read_text(encoding="utf-8")
    check("0001 creates error events table", "CREATE TABLE IF NOT EXISTS wathefni_error_events" in sql)
    check("0001 does not invent down SQL", "DROP TABLE" not in sql.upper())
    os.environ.pop("WATHEFNI_SCHEMA_APPLY", None)
    check("runtime apply is forbidden by default", schema_contract.schema_apply_allowed() is False)
    try:
        mf.apply_pending(object())
        check("apply_pending refuses without WATHEFNI_SCHEMA_APPLY", False)
    except RuntimeError as exc:
        check("apply_pending refuses without WATHEFNI_SCHEMA_APPLY", "schema_apply_forbidden" in str(exc), exc)
    rollback = mf.rollback_procedure()
    check("rollback is restore-from-backup", rollback["mode"] == "restore_from_backup")
    check("rollback points at RESTORE_RUNBOOK", "RESTORE_RUNBOOK.md" in rollback["runbook"])
    runbook = read(ROOT / "ops" / "RESTORE_RUNBOOK.md")
    check("runbook documents R8 forward-only restore", "forward-only" in runbook and "wathefni_forward_migrations" in runbook)


def http_and_health_contracts() -> None:
    print("\n    health / ingest / failed-job visibility")
    app_src = read(ROOT / "app.py")
    http_src = read(ROOT / "observability_http.py")
    health = app_src[app_src.index("def health()") : app_src.index("def ready()")]
    ready = app_src[app_src.index("def ready()") : app_src.index("def orchestrator_debug_prompt_context")]
    check("health is liveness-only (no ensure_schema)", "ensure_schema()" not in health)
    check("health does not leak legacy auth flags", "legacy_dashboard_token_auth" not in health)
    check("ready includes delivery snapshot", "delivery_snapshot" in ready and '"delivery"' in ready)
    check("ready returns 503 when migrations are not ok", "status_code=503" in ready)
    check("ready still carries R2 link_signing", "link_signing" in ready)
    for route in (
        "/dashboard/telemetry/error",
        "/dashboard/mobile/telemetry/error",
        "/app/telemetry/error",
        "/dashboard/ops/delivery",
    ):
        check(f"ingest/ops route registered: {route}", route in http_src)
    check("client ingest is rate-limited", "client_error_report" in http_src)
    check("R2 denial hook is wired", "register_telemetry_hook" in http_src)
    check("backend exception ingest exists", "r8_unhandled_exception" in http_src and "record_error_event" in http_src)
    import security_rate_limit as rl

    check("client_error_report policy is additive", "client_error_report" in {row["policy"] for row in rl.policy_matrix()})
    check("R2 login policy still present", rl.policy("dashboard_login").limit == 8)


def client_and_ci_contracts() -> None:
    print("\n    P1-23/P1-24 — clients, CI, deploy gate")
    dash_helper = read(DASH / "src/lib/reportClientError.ts")
    dash_main = read(DASH / "src/main.tsx")
    setup_main = read(DASH / "src/setup-console/main.tsx")
    hr_helper = read(HR / "src/lib/reportClientError.ts")
    hr_boundary = read(HR / "src/components/AppErrorBoundary.tsx")
    emp_helper = read(EMP / "src/lib/reportClientError.ts")
    emp_boundary = read(EMP / "src/components/AppErrorBoundary.tsx")
    emp_hr_helper = read(EMP / "src/hr/lib/reportClientError.ts")
    emp_hr_boundary = read(EMP / "src/hr/components/AppErrorBoundary.tsx")
    check("dashboard helper redacts before POST", "redactClientText" in dash_helper and "/dashboard/telemetry/error" in dash_helper)
    check("dashboard boundary reports", "reportClientError(error, 'hr_web')" in dash_main)
    check("setup console boundary reports", "reportClientError(error, 'setup_console')" in setup_main)
    check("HR mobile uses allowlisted telemetry path", "/dashboard/mobile/telemetry/error" in hr_helper)
    check("HR mobile boundary reports redacted payload", "reportClientError(error)" in hr_boundary)
    check("employee helper uses /app/telemetry/error", "/app/telemetry/error" in emp_helper)
    check("employee boundary still logs and reports", "console.error" in emp_boundary and "reportClientError(error)" in emp_boundary)
    check("employee HR helper uses mobile telemetry path", "/dashboard/mobile/telemetry/error" in emp_hr_helper)
    check("employee HR boundary reports", "reportClientError(error)" in emp_hr_boundary)
    ci = REPO / ".github/workflows/delivery-safety.yml"
    gate = REPO / "ops/gate-wathefni-deploy.sh"
    check("CI workflow exists", ci.is_file())
    if ci.is_file():
        ci_text = read(ci)
        check("CI runs R8 unit", "smoke-test-r8-delivery-safety.py" in ci_text)
        check("CI runs R7 unit", "smoke-test-r7-mobile-native-safety.py" in ci_text)
        check("CI runs R2 unit", "smoke-test-r2-security.py" in ci_text)
        check("CI does not SSH to the VPS", "76.13.63.68" not in ci_text and "ssh " not in ci_text.lower())
    check("deploy gate script exists", gate.is_file() and os.access(gate, os.X_OK) or gate.is_file())
    if gate.is_file():
        gate_text = read(gate)
        check("deploy gate runs R8 unit", "smoke-test-r8-delivery-safety.py" in gate_text)
        check("deploy gate runs R7 unit", "smoke-test-r7-mobile-native-safety.py" in gate_text)


def main() -> int:
    sys.path.insert(0, str(ROOT))
    print("    PRODUCTION READINESS R8 — delivery safety unit contracts")
    redaction_contracts()
    migration_contracts()
    http_and_health_contracts()
    client_and_ci_contracts()
    print("\n    R8_DELIVERY_SAFETY_UNIT_PASS")
    print(f"    {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
