#!/usr/bin/env python3
"""Action Inbox Wave 1 freeze regression — hard gates for future differentiation PRs."""

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


def read(name: str) -> str:
    p = ROOT / name
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def main() -> int:
    freeze_candidates = [
        OPS / "ACTION_INBOX_WAVE1_FREEZE.md",
        Path("/opt/wathefni/ops/ACTION_INBOX_WAVE1_FREEZE.md"),
        Path("/Users/azizalmulla/Desktop/claw/ops/ACTION_INBOX_WAVE1_FREEZE.md"),
    ]
    freeze = next((p for p in freeze_candidates if p.is_file()), None)
    check("action inbox wave1 freeze doc present", freeze is not None, str(freeze_candidates[0]))
    if freeze is not None:
        txt = freeze.read_text(encoding="utf-8")
        for needle in (
            "SYNTHETIC_ONLY",
            "read-only",
            "composes",
            "Alerts",
            "Hiring Reports",
            "NO-GO",
            "AIW1",
            "Analytics",
            "Compliance",
            "Payroll",
            "Attendance",
            "Shifts",
            "mutates",
            "Wave 2",
        ):
            check(f"freeze doc mentions {needle}", needle.lower() in txt.lower(), needle)

    w1 = read("action_inbox_wave1.py")
    appsrc = read("app.py")
    canary = read("canary-prod-action-inbox-wave1b.py")

    check("inbox module present", bool(w1.strip()))
    check("contract constant", 'ACTION_INBOX_WAVE1_CONTRACT = "action_inbox_wave1"' in w1)
    check("synthetic_only helper", "def action_inbox_wave1_synthetic_only" in w1)
    check("honesty mutates false", '"mutates_records": False' in w1)
    check("honesty ai false", '"ai": False' in w1)
    check("honesty hiring reports", '"hiring_reports_separate": True' in w1)
    check("honesty alerts", '"alerts_delivery_owns_notifications": True' in w1)
    check("honesty no compliance wave2", '"compliance_wave2": False' in w1)
    check("honesty no analytics wave2", '"analytics_wave2": False' in w1)
    check("honesty no payroll money", '"payroll_money": False' in w1)
    check("ack schema helper", "def ensure_action_inbox_wave1_schema" in w1)
    check("ack cleanup helper", "def cleanup_canary_acks" in w1)
    check("dashboard inbox wired", "build_action_inbox" in appsrc)
    check("dashboard route present", "action-inbox" in appsrc)
    check("manager scope in e360 helper", "manager_scope_employee_keys" in appsrc)
    check("prod canary present", bool(canary.strip()))
    check("canary residual cleanup", "residual_synthetic_acks" in canary and "cleanup_canary_acks" in canary)
    check("canary synthetic_only assert", "action_inbox_wave1_synthetic_only" in canary)

    for name in (
        "EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "ANALYTICS_WAVE1_ATTENTION_FREEZE.md",
        "COMPLIANCE_WAVE1_FINDINGS_FREEZE.md",
    ):
        p = OPS / name
        alt = Path("/opt/wathefni/ops") / name
        check(f"frozen module doc intact {name}", p.is_file() or alt.is_file())

    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
