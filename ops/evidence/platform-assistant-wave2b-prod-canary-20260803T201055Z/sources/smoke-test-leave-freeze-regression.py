#!/usr/bin/env python3
"""Leave freeze regression — hard gates for future modules.

Fails if self-approval bans, lifecycle gates, policy versions, ledger idempotency,
attachment privacy, Attendance reversal safety, or freeze docs weaken.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OPS = ROOT.parent / "ops"
if not OPS.exists():
    OPS = Path("/opt/wathefni/ops")
RESULTS: list[tuple[str, bool, object]] = []


def check(name: str, ok: bool, detail: object = None) -> None:
    RESULTS.append((name, bool(ok), detail if not ok else None))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" :: {detail}" if not ok and detail is not None else ""))


def main() -> int:
    freeze_candidates = [
        OPS / "LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        Path("/opt/wathefni/ops/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md"),
        Path("/Users/azizalmulla/Desktop/claw/ops/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md"),
    ]
    freeze = next((p for p in freeze_candidates if p.is_file()), None)
    check("leave freeze doc present", freeze is not None, str(freeze_candidates[0]))
    if freeze is not None:
        txt = freeze.read_text(encoding="utf-8")
        for needle in (
            "self_approval",
            "SYNTHETIC_ONLY",
            "enforced=false",
            "legal_reviewed=false",
            "ledger",
            "attachment",
            "Attendance",
            "Employees 360",
            "Onboarding",
            "Payroll",
            "NO-GO",
            "REAL_DECISION",
        ):
            check(f"freeze doc mentions {needle}", needle.lower() in txt.lower() or needle in txt, needle)

    w1 = (ROOT / "leave_authority_wave1.py").read_text(encoding="utf-8")
    w2 = (ROOT / "leave_policy_wave2.py").read_text(encoding="utf-8")
    w3 = (ROOT / "leave_workflow_wave3.py").read_text(encoding="utf-8")
    w4 = (ROOT / "leave_wave4_controlled.py").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    check("self_decision_denied present", "def self_decision_denied" in w1)
    check("self_approval_forbidden string", "self_approval_forbidden" in w1)
    check("synthetic_only gate", "leave_authority_synthetic_only" in w1 or "SYNTHETIC_ONLY" in w1)
    check("lifecycle_gate present", "def lifecycle_gate" in w1)
    check("policy pack version 2.1.0", "2.1.0" in w2)
    check("enforced false in pack", '"enforced": False' in w2 or "'enforced': False" in w2)
    check("ledger reservation idempotency index", "idx_leave_ledger_reservation_idem" in w2 or "ON CONFLICT (leave_id, entry_kind)" in w2)
    check("unpaid payroll_boundary", "payroll_boundary" in w2 and "unpaid" in w2)
    check("attachment mask helper", "mask_attachment_for_viewer" in w3)
    check("assert_handoff_has_no_money", "assert_handoff_has_no_money" in w3)
    check("wave4 real decision gate", "real_decision_denied" in w4)
    check("wave4 dual control", "leave_dual_control" in w4)
    check("wave4 kill switch", "WATHEFNI_LEAVE_WAVE4_KILL" in w4)
    check("app wires wave4 gate on approve", "real_decision_denied" in app)
    check("app attendance reverse event-before-delete", "leave_derived_reversed" in app)
    check("app does not set enforced=true for leave policies in wave4", "enforced=true" not in w4.lower())

    # UX presence (repo / known local / staged evidence copy). On orch-only hosts,
    # leave_wave4 enrich + freeze doc are the authoritative gates.
    candidates = [
        ROOT.parent / "apps" / "wathefni-dashboard" / "src" / "posthire" / "LeaveWorkspace.tsx",
        Path("/Users/azizalmulla/Desktop/claw/apps/wathefni-dashboard/src/posthire/LeaveWorkspace.tsx"),
        Path("/opt/wathefni/apps/wathefni-dashboard/src/posthire/LeaveWorkspace.tsx"),
    ]
    ux_file = next((p for p in candidates if p.is_file()), None)
    if ux_file is not None:
        check("LeaveWorkspace present", True, str(ux_file))
        check("leaveUx present", (ux_file.parent / "leaveUx.ts").is_file())
    else:
        # Orchestrator-only deploy: require wave4 enrich hooks used by UI payloads.
        check(
            "LeaveWorkspace present (orch enrich fallback)",
            "def enrich_leave_row_for_ui" in w4 and "def holiday_year_status_payload" in w4,
        )

    cursor_candidates = [
        ROOT.parent / ".cursor" / "rules" / "leave-freeze.mdc",
        Path("/Users/azizalmulla/Desktop/claw/.cursor/rules/leave-freeze.mdc"),
        Path("/opt/wathefni/ops/leave-freeze.mdc"),
    ]
    cursor = next((p for p in cursor_candidates if p.is_file()), None)
    check("leave freeze cursor rule present", cursor is not None, str(cursor_candidates[0]))

    # Cross-freeze docs intact (repo ops or /opt/wathefni/ops)
    for name in (
        "EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
    ):
        paths = [
            OPS / name,
            Path("/opt/wathefni/ops") / name,
            Path("/Users/azizalmulla/Desktop/claw/ops") / name,
        ]
        p = next((c for c in paths if c.is_file()), None)
        check(f"frozen module doc intact {name}", p is not None, str(paths[0]))

    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
