#!/usr/bin/env python3
"""HR Employee Profile cream + honesty freeze contracts."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
view = (ROOT / "src/hr/features/people/EmployeeProfileView.tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/people/employeeComposition.ts").read_text(encoding="utf-8")
route = (ROOT / "app/hr/employees/[employeeKey].tsx").read_text(encoding="utf-8")
types = (ROOT / "src/hr/api/types.ts").read_text(encoding="utf-8")
norm = (ROOT / "src/hr/api/normalize.ts").read_text(encoding="utf-8")
people = (ROOT / "src/hr/features/people/HRPeopleDirectoryView.tsx").read_text(encoding="utf-8")
ops = (ROOT / "src/hr/features/operations/routes.tsx").read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("route uses EmployeeProfileView", "EmployeeProfileView" in route)
check("cream PageScreen + HrPushedNav", "PageScreen" in view and "HrPushedNav" in view)
check("no OperationalDetailView on employee route", "OperationalDetailView" not in route and "EmployeeDetailRoute" not in ops)
check("no manager_name anywhere client employee path", "manager_name" not in view and "manager_name" not in route)
check("types drop manager_name", "manager_name" not in types.split("export type EmployeeSummary")[1].split("export type")[0])
check("normalize drops manager_name", "manager_name" not in norm.split("export function normalizeEmployee")[1].split("export function")[0])
check("empty key → unavailable", "unavailable" in route and "!key" in route)
check("404 → not_found", "not_found" in route and "employee_not_found" in route)
check("status localized via composition", "localizeEmploymentStatus" in view and "employmentStatusLabelKey" in comp)
check("facts-only (no module cards)", "attendance" not in view.lower() and "onboarding" not in view.lower() and "AmbientCard" not in view)
check("People still opens profile", "/employees/${encodeURIComponent(item.employee_key)}" in people or "/employees/" in people)
check("safe-back used", "useHrSafeBack" in route)

keys = [
    "hrEmployee.eyebrow",
    "hrEmployee.statusActive",
    "hrEmployee.statusLeft",
    "hrEmployee.notFoundTitle",
    "hrEmployee.unavailableTitle",
    "hrEmployee.permissionTitle",
    "hrEmployee.sectionContact",
    "hrEmployee.sectionTenure",
    "common.department",
    "common.phone",
    "common.startDate",
]
check("EN+AR keys", all(k in en and k in ar for k in keys))
check("AR active is Arabic", any("\u0600" <= c <= "\u06FF" for c in ar["hrEmployee.statusActive"]))
check("filled Wathefni status tones", "'green'" in comp and "'yellow'" in comp and "'pink'" in comp)
check("no boxed Fact surface cards", "colors.surface" not in view or "backgroundColor: colors.surface" not in view)
check("editorial lead composed", "composeLead" in view)

print("hr-employee-profile: GREEN")
