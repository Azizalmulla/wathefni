#!/usr/bin/env python3
"""Analytics Wave 1 freeze regression — hard gates for future Analytics / post-hire PRs."""

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
        OPS / "ANALYTICS_WAVE1_ATTENTION_FREEZE.md",
        Path("/opt/wathefni/ops/ANALYTICS_WAVE1_ATTENTION_FREEZE.md"),
        Path("/Users/azizalmulla/Desktop/claw/ops/ANALYTICS_WAVE1_ATTENTION_FREEZE.md"),
    ]
    freeze = next((p for p in freeze_candidates if p.is_file()), None)
    check("analytics wave1 freeze doc present", freeze is not None, str(freeze_candidates[0]))
    if freeze is not None:
        txt = freeze.read_text(encoding="utf-8")
        for needle in (
            "SYNTHETIC_ONLY",
            "read-only",
            "money_authority",
            "Hiring Reports",
            "Alerts",
            "NO-GO",
            "ANW1",
            "Payroll",
            "Attendance",
            "Leave",
            "Shifts",
            "Employees",
        ):
            check(f"freeze doc mentions {needle}", needle.lower() in txt.lower(), needle)

    w1 = read("analytics_attention_wave1.py")
    appsrc = read("app.py")
    catalog = read("assistant_capability_catalog.py")
    canary = read("canary-prod-analytics-attention-wave1b.py")

    check("attention module present", bool(w1.strip()))
    check("contract constant", 'ANALYTICS_WAVE1_CONTRACT = "analytics_attention_wave1"' in w1)
    check("synthetic_only helper", "def analytics_wave1_synthetic_only" in w1)
    check("honesty money false", '"money_authority": False' in w1)
    check("honesty ai false", '"ai": False' in w1)
    check("no overtime risk label", "Overtime risk" not in w1 or "Hours above schedule" in w1)
    check("hours above schedule", "Hours above schedule" in w1)
    check("best attendance omitted from patterns", "intentionally omitted" in w1.lower())
    check("dashboard identity keys", "viewer_user_id" in appsrc and "dashboard_posthire_analytics" in appsrc)
    check("actor_role on analytics route", "actor_role" in appsrc[appsrc.find("def dashboard_posthire_analytics"): appsrc.find("def dashboard_posthire_analytics") + 900])
    check("assistant chip not headcount", "Headcount summary" not in catalog)
    check("assistant attention chip", "Workforce attention summary" in catalog or "ملخص ما يحتاج انتباهاً" in catalog)
    check("prod canary present", bool(canary.strip()))
    check("canary residual cleanup", "residual_synthetic_acks" in canary and "cleanup_canary_acks" in canary)
    check("canary synthetic_only assert", "analytics_wave1_synthetic_only" in canary)

    for name in (
        "EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
    ):
        path = OPS / name
        if not path.exists():
            path = Path("/opt/wathefni/ops") / name
        check(f"frozen module doc intact {name}", path.is_file(), str(path))

    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
