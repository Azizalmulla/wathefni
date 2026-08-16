#!/usr/bin/env python3
"""Compliance Wave 1 freeze regression — hard gates for future Compliance / post-hire PRs."""

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
        OPS / "COMPLIANCE_WAVE1_FINDINGS_FREEZE.md",
        Path("/opt/wathefni/ops/COMPLIANCE_WAVE1_FINDINGS_FREEZE.md"),
        Path("/Users/azizalmulla/Desktop/claw/ops/COMPLIANCE_WAVE1_FINDINGS_FREEZE.md"),
    ]
    freeze = next((p for p in freeze_candidates if p.is_file()), None)
    check("compliance wave1 freeze doc present", freeze is not None, str(freeze_candidates[0]))
    if freeze is not None:
        txt = freeze.read_text(encoding="utf-8")
        for needle in (
            "SYNTHETIC_ONLY",
            "document compliance",
            "government_verified",
            "legal-compliance",
            "Alerts",
            "NO-GO",
            "CFW1",
            "Analytics",
            "Onboarding",
            "Employees",
            "fine",
            "money_authority",
        ):
            check(f"freeze doc mentions {needle}", needle.lower() in txt.lower(), needle)

    w1 = read("compliance_findings_wave1.py")
    appsrc = read("app.py")
    canary = read("canary-prod-compliance-findings-wave1b.py")
    anw1 = read("analytics_attention_wave1.py")

    check("findings module present", bool(w1.strip()))
    check("contract constant", 'COMPLIANCE_WAVE1_CONTRACT = "compliance_findings_wave1"' in w1)
    check("synthetic_only helper", "def compliance_wave1_synthetic_only" in w1)
    check("honesty never gov", '"government_verified": False' in w1)
    check("honesty no legal claims", '"legal_compliance_claims": False' in w1)
    check("honesty no fines", '"fine_calculations": False' in w1)
    check("honesty no AI", '"ai": False' in w1)
    check("alerts own reminders", '"alerts_delivery_owns_reminders": True' in w1)
    check("analytics excludes compliance flag", '"analytics_excludes_compliance": True' in w1)
    check("canonical residence", 'CANONICAL_RESIDENCE = "residence"' in w1)
    check("dashboard findings wired", "build_compliance_findings" in appsrc)
    check("seed never iqama", "Never seed legacy residency_iqama" in appsrc or "residency_iqama" in appsrc)
    check("prod canary present", bool(canary.strip()))
    check("canary residual cleanup", "residual_synthetic_acks" in canary and "cleanup_canary_acks" in canary)
    check("canary synthetic_only assert", "compliance_wave1_synthetic_only" in canary)
    check("analytics still excludes compliance metrics", '"compliance_metrics": False' in anw1)

    for name in (
        "EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "ANALYTICS_WAVE1_ATTENTION_FREEZE.md",
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
