#!/usr/bin/env python3
"""Attendance freeze regression — hard gates for future modules.

Fails if punch immutability, synthetic-only, ingest-off, approval/apply separation,
manager self-denial, payroll snapshot locks, tenant isolation, or freeze docs weaken.
"""
from __future__ import annotations

import os
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
    freeze = OPS / "ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md"
    check("attendance freeze doc present", freeze.is_file(), str(freeze))
    if freeze.is_file():
        txt = freeze.read_text(encoding="utf-8")
        for needle in (
            "CAPTURE_INGEST",
            "SYNTHETIC_ONLY",
            "punch immutability",
            "approve",
            "apply",
            "manager self",
            "payroll",
            "Employees 360",
            "Onboarding",
            "NO-GO",
        ):
            check(f"freeze doc mentions {needle}", needle.lower() in txt.lower() or needle in txt, needle)

    auth = (ROOT / "attendance_authority_wave1.py").read_text(encoding="utf-8")
    ops = (ROOT / "attendance_ops_wave3.py").read_text(encoding="utf-8")
    check("authority has synthetic-only gate", "attendance_authority_synthetic_only" in auth or "SYNTHETIC_ONLY" in auth)
    check("authority punch append path present", "append_punch" in auth)
    check("ops has manager_self_correction_denied", "manager_self_correction_denied" in ops)
    check("ops has employee_outside_manager_scope", "employee_outside_manager_scope" in ops)
    check("ops has payroll_period_locked", "payroll_period_locked" in ops)
    check("ops separates approve/apply", "approve_reject_apply_separated" in ops or "apply_case" in ops and "review_case" in ops)
    check("ops dual approval", "dual_approval" in ops or "pending_dual_approval" in ops)
    check("ops stale_row_version", "stale_row_version" in ops)

    # Ingest default must not be on in drop-in templates if present locally
    for name in (
        "ops/deploy-attendance-final-prod.sh",
        "ops/deploy-attendance-wave3-prod-synthetic.sh",
    ):
        p = ROOT / name
        if not p.exists():
            p = ROOT.parent / name
        if p.exists():
            t = p.read_text(encoding="utf-8")
            check(f"{p.name} keeps CAPTURE_INGEST=off", "CAPTURE_INGEST=off" in t)
            check(f"{p.name} keeps OPS_SYNTHETIC_ONLY", "OPS_SYNTHETIC_ONLY=on" in t or "SYNTHETIC_ONLY=on" in t)

    # E360 / Onboarding freeze docs must still exist
    check("E360 freeze doc present", (OPS / "EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md").is_file())
    check("Onboarding freeze doc present", (OPS / "ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md").is_file())

    # Cursor rule (repo or host ops checkout)
    rule_candidates = [
        ROOT.parent / ".cursor" / "rules" / "attendance-freeze.mdc",
        Path("/opt/wathefni/.cursor/rules/attendance-freeze.mdc"),
        Path("/opt/wathefni/ops") / ".." / ".cursor" / "rules" / "attendance-freeze.mdc",
    ]
    evidence_candidates = [
        OPS / "evidence",
        Path("/opt/wathefni/ops/evidence"),
    ]
    check(
        "attendance freeze cursor rule present or evidence copy",
        any(p.is_file() for p in rule_candidates) or any(p.exists() for p in evidence_candidates),
        [str(p) for p in rule_candidates],
    )

    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
