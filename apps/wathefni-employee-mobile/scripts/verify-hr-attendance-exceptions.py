#!/usr/bin/env python3
"""HR Attendance — exception-first queue contract (Today + Unresolved, honest actions)."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
queue = (ROOT / "src/hr/features/attendance/HRAttendanceQueueView.tsx").read_text(encoding="utf-8")
detail = (ROOT / "src/hr/features/attendance/HRAttendanceDetailView.tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/attendance/attendanceComposition.ts").read_text(encoding="utf-8")
demo = (ROOT / "src/hr/features/attendance/attendanceDemoData.ts").read_text(encoding="utf-8")
gate = (ROOT / "src/hr/features/attendance/attendanceDemoGate.ts").read_text(encoding="utf-8")
index = (ROOT / "app/hr/attendance/index.tsx").read_text(encoding="utf-8")
detail_route = (ROOT / "app/hr/attendance/[attendanceId].tsx").read_text(encoding="utf-8")
config = (ROOT / "app.config.js").read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))
hr_en = json.loads((ROOT / "src/hr/i18n/en.json").read_text(encoding="utf-8"))
hr_ar = json.loads((ROOT / "src/hr/i18n/ar.json").read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail_msg: str = "") -> None:
    print(("PASS" if ok else "FAIL"), name + (f" — {detail_msg}" if detail_msg and not ok else ""))
    if not ok:
        raise SystemExit(1)


check("queue route wired", "HRAttendanceQueueView" in index)
check("detail route wired", "HRAttendanceDetailView" in detail_route)
# Cream queue chrome: PageScreen + EditorialHeading. Wordmark is legacy optional.
check(
    "cream queue chrome (PageScreen + EditorialHeading)",
    "PageScreen" in queue and "EditorialHeading" in queue,
)
check("Today + Unresolved tabs", "hrAttendance.tabToday" in queue and "hrAttendance.tabUnresolved" in queue)
check("status=exceptions filter", "status: 'exceptions'" in queue)
check("filters is_exception client-side", "onlyExceptions" in queue and "is_exception" in queue)
check("92-day unresolved lookback", "UNRESOLVED_LOOKBACK_DAYS = 92" in comp)
check("canonical Ops kinds", all(
    k in comp
    for k in ("absence", "lateness", "early_leave", "missing_check_in", "missing_check_out", "incomplete_session")
))
check("no invented exception_type", "exception_type" not in queue and "exception_type" not in detail and "exception_type" not in comp)
check("honest request_correction labels", "hrAttendance.requestCorrection" in detail or "requestCorrectionSub" in detail)
check("actionsHint pending review", "hrAttendance.actionsHint" in detail)
check("no Resolve as day-fixed label", not re.search(r"['\"]Resolve['\"]", detail))
check("demo gated + prefixed", "attendanceDemoEnabled" in gate and "__demo_att__" in gate)
check("demo kinds covered", all(
    k in demo
    for k in ("lateness", "absence", "missing_check_out", "early_leave", "missing_check_in", "incomplete_session")
))
check("app.config attendanceDemo", "attendanceDemo:" in config and "EXPO_PUBLIC_HR_ATTENDANCE_DEMO" in config)
check("no attendance.excuse in HR i18n", "attendance.excuse" not in hr_en and "attendance.excuse" not in hr_ar)

keys = [
    "hrAttendance.title",
    "hrAttendance.tabToday",
    "hrAttendance.tabUnresolved",
    "hrAttendance.actionsTitle",
    "hrAttendance.request.present",
    "hrAttendance.kindAbsence",
    "hrAttendance.kindLateness",
]
check("hrAttendance keys EN+AR", all(k in en and k in ar for k in keys))
print("hr-attendance-exceptions: GREEN")
