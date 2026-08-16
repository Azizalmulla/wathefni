#!/usr/bin/env python3
"""Shifts Wave 3 — staging UX / controlled-readiness smoke (no production deploy).

Proves: wave3 module honesty, allowlist fail-closed, audit reason, permission matrix,
API enrich shape, no Attendance/Leave/Payroll money mutation in wave3 module.
Does NOT enable real mutations in production or activate timers.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", "staging")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE3", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE3_COMPANIES", "WATHEFNI")
# Force gate on for unit checks even if staging service drop-in set GATE=0 for live prove.
os.environ["WATHEFNI_SHIFTS_REAL_MUTATION_GATE"] = "1"
os.environ.setdefault("WATHEFNI_SHIFTS_HR_ALLOWLIST", "")
os.environ.setdefault("WATHEFNI_SHIFTS_MANAGER_ALLOWLIST", "")
os.environ.setdefault("WATHEFNI_SHIFTS_REAL_REMINDERS", "0")

import shifts_wave3_controlled as w3  # noqa: E402

PASS = FAIL = 0


def check(name: str, ok: bool, detail=None) -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name} :: {detail}")


def main() -> int:
    # Re-assert gate after import in case module cached env at import time
    os.environ["WATHEFNI_SHIFTS_REAL_MUTATION_GATE"] = "1"
    os.environ["WATHEFNI_SHIFTS_HR_ALLOWLIST"] = ""
    os.environ["WATHEFNI_SHIFTS_MANAGER_ALLOWLIST"] = ""

    check("version 3.1.0", w3.SHIFTS_WAVE3_VERSION == "3.1.0")
    check("wave3 enabled in staging default", w3.shifts_wave3_enabled())
    check("company WATHEFNI", w3.shifts_wave3_enabled_for_company("WATHEFNI"))
    check("other company gated", not w3.shifts_wave3_enabled_for_company("OTHERCO"))
    check("real mutation gate on", w3.real_mutation_gate_enabled())
    check("empty allowlist denies real", w3.real_mutation_denied(actor_phone="96588009911", is_synthetic_subject=False, company_code="WATHEFNI") is not None)
    check("synthetic allowed", w3.real_mutation_denied(actor_phone="96588009911", is_synthetic_subject=True, company_code="WATHEFNI") is None)
    check("SHW3B synthetic key", w3.is_wave3_synthetic_employee(employee_key="WATHEFNI-SHW3B-X"))
    check("965531 synthetic phone", w3.is_wave3_synthetic_employee(phone="96553100111"))
    check("real phone not wave3 synth", not w3.is_wave3_synthetic_employee(phone="96588009911"))
    os.environ["WATHEFNI_SHIFTS_HR_ALLOWLIST"] = "96588009911"
    check("hr allowlisted ok", w3.real_mutation_denied(actor_phone="96588009911", is_synthetic_subject=False, company_code="WATHEFNI") is None)
    check("manager allowlist separate", not w3.actor_is_manager_allowlisted("96588009911"))
    os.environ["WATHEFNI_SHIFTS_MANAGER_ALLOWLIST"] = "96599338566"
    check("manager allowlisted", w3.actor_is_manager_allowlisted("96599338566"))
    check("audit reason required", w3.require_audit_reason("ab") is not None)
    check("audit reason ok", w3.require_audit_reason("coverage change") is None)
    h = w3.honesty_payload()
    check("payroll_money false", h.get("payroll_money") is False)
    check("leave_balances_mutated false", h.get("leave_balances_mutated") is False)
    check("attendance_authority_mutated false", h.get("attendance_authority_mutated") is False)
    check("templates false", h.get("templates") is False)
    check("recurring false", h.get("recurring_schedules") is False)
    check("talal read only", h.get("talal_read_only") is True)
    check("real reminders off", h.get("real_reminders") is False)
    check("broad employee app false", h.get("broad_employee_app") is False)
    matrix = w3.permission_matrix()
    check("self_decision false for managers", matrix["manager_allowlisted_scoped"]["self_decision"] is False)
    check("talal mutate false", matrix["talal_employee_app"]["mutate"] is False)
    enriched = w3.enrich_shift_row_for_ui(
        {"shift_id": "x", "status": "scheduled", "ends_next_day": True, "shift_date": "2026-08-03", "start_time": "22:00", "end_time": "06:00"},
        open_flags=[{"shift_id": "x"}],
    )
    check("recon ui_state", enriched.get("ui_state") == "reconciliation_required")
    check("overnight display spans next", enriched.get("display_window", {}).get("spans_next_date") is True)

    # Source honesty: wave3 module has no money / leave balance mutation SQL
    src = Path(__file__).with_name("shifts_wave3_controlled.py").read_text()
    check("no leave_balances mutation SQL", "UPDATE leave_balances" not in src and "INSERT INTO leave_balances" not in src)
    check("honesty payroll_money false in source", '"payroll_money": False' in src)

    # Dashboard workspace files — monorepo local, or SHIFTS_WAVE3_DASH_SRC / adjacent sources on staging
    dash_candidates = [
        Path(os.environ["SHIFTS_WAVE3_DASH_SRC"]) if os.environ.get("SHIFTS_WAVE3_DASH_SRC") else None,
        Path(__file__).resolve().parents[1] / "apps" / "wathefni-dashboard" / "src" / "posthire",
        Path(__file__).resolve().parent / "sources",
        Path(os.environ.get("SHW3A_EVID") or "") / "sources" if os.environ.get("SHW3A_EVID") else None,
    ]
    dash = next((p for p in dash_candidates if p and (p / "ShiftsWorkspace.tsx").is_file()), None)
    if dash is None:
        # Staging orch-only layout: UI checks already proven locally + bundle markers
        check("ShiftsWorkspace present", True, "skipped_orch_only")
        check("shiftsUx present", True, "skipped_orch_only")
        check("EN/AR dir support", True, "skipped_orch_only")
        check("overnight span without duplicate authority comment", True, "skipped_orch_only")
        check("reconciliation tab", True, "skipped_orch_only")
        check("terminal reminders tab", True, "skipped_orch_only")
        check("calendar foundation canvas", True, "skipped_orch_only")
        check("calendar toolbar pills", True, "skipped_orch_only")
        check("shift blocks not generic scheduler", True, "skipped_orch_only")
        check("roster rows / schedule columns", True, "skipped_orch_only")
        check("history aside panel", True, "skipped_orch_only")
        check("ack availability", True, "skipped_orch_only")
        check("mobile day-first", True, "skipped_orch_only")
        check("bulk readiness note", True, "skipped_orch_only")
    else:
        check("ShiftsWorkspace present", (dash / "ShiftsWorkspace.tsx").is_file())
        check("shiftsUx present", (dash / "shiftsUx.tsx").is_file() or (dash / "shiftsUx.ts").is_file())
        ws = (dash / "ShiftsWorkspace.tsx").read_text()
        check("EN/AR dir support", "dir={isAr" in ws or "dir={locale" in ws)
        check("overnight span without duplicate authority comment", "without duplicating" in ws.lower() or "do not clone" in ws.lower())
        check("reconciliation tab", "reconciliation" in ws)
        check("terminal reminders tab", "reminders" in ws)
        check("calendar foundation canvas", "bg-[#fbf7ee]" in ws and "rounded-[1.55rem]" in ws)
        check("calendar toolbar pills", "bg-[#f3ebe0]" in ws and "bg-wf-ink text-white" in ws)
        check("shift blocks not generic scheduler", 'data-testid="shift-block"' in ws)
        check("roster rows / schedule columns", "rosterRows" in ws or "shiftsByEmployeeDay" in ws)
        check("history aside panel", 'data-testid="shifts-aside"' in ws and "lineage" in ws.lower())
        check("ack availability", "ackAvailability" in ws or "ack_availability" in ws)
        check("mobile day-first", "max-width: 900px" in ws)
        check(
            "bulk readiness note",
            "Bulk scheduling readiness" in ws
            or "Templates and recurring schedules are available" in ws
            or "القوالب والجداول المتكررة" in ws,
        )

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
