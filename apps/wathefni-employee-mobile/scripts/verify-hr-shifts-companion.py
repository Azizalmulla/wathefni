#!/usr/bin/env python3
"""HR Shifts — decision-first companion contract (Needs Attention + Today)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
home = (ROOT / "src/hr/features/shifts/HRShiftsHomeView.tsx").read_text(encoding="utf-8")
detail = (ROOT / "src/hr/features/shifts/HRShiftSwapDetailView.tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/shifts/shiftsComposition.ts").read_text(encoding="utf-8")
gate = (ROOT / "src/hr/features/shifts/shiftsDemoGate.ts").read_text(encoding="utf-8")
index = (ROOT / "app/hr/shifts.tsx").read_text(encoding="utf-8")
swap_route = (ROOT / "app/hr/shift-swaps/[swapId].tsx").read_text(encoding="utf-8")
config = (ROOT / "app.config.js").read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))
norm = (ROOT / "src/hr/api/normalize.ts").read_text(encoding="utf-8")


def check(name: str, ok: bool, detail_msg: str = "") -> None:
    print(("PASS" if ok else "FAIL"), name + (f" — {detail_msg}" if detail_msg and not ok else ""))
    if not ok:
        raise SystemExit(1)


check("home route wired", "HRShiftsHomeView" in index)
check("swap detail route wired", "HRShiftSwapDetailView" in swap_route)
check("Needs Attention + Today tabs", "needs_attention" in home and "hrShifts.tabToday" in home)
check("kuwaitToday for schedule day", "kuwaitToday" in home and "toISOString" not in home)
check("requested swaps filter", "status: 'requested'" in home or "status: \"requested\"" in home)
check("permission states for splits", "swapsUnavailable" in home and "todayUnavailable" in home)
today_panel = home.split("function TodayPanel")[1].split("function TabChip")[0] if "function TodayPanel" in home else ""
check(
    "Today rows read-only",
    "hrShifts.readOnly" in today_panel and "router.push" not in today_panel and "onOpen" not in today_panel,
)
check("both sides on detail", "sectionRequesterShift" in detail and "sectionTargetShift" in detail)
swap_norm = norm.split("export function normalizeSwap")[1].split("export function normalizeEmployee")[0]
check("no invented pending default", "pending" not in swap_norm and "requested" in swap_norm)
check("demo gated", "shiftsDemoEnabled" in gate and "__demo_swap__" in gate)
check("app.config shiftsDemo", "shiftsDemo:" in config and "EXPO_PUBLIC_HR_SHIFTS_DEMO" in config)
check("extensible attention kind", "ShiftsAttentionKind" in comp and "shift_swap" in comp)

keys = [
    "hrShifts.title",
    "hrShifts.tabNeedsAttention",
    "hrShifts.tabToday",
    "hrShifts.statusRequested",
    "hrShifts.approve",
    "hrShifts.sectionRequesterShift",
]
check("hrShifts keys EN+AR", all(k in en and k in ar for k in keys))
print("hr-shifts-companion: GREEN")
