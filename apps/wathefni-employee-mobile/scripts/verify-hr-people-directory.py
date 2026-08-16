#!/usr/bin/env python3
"""HR People directory contract — search-first, exceptional chips only."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
view = (ROOT / "src/hr/features/people/HRPeopleDirectoryView.tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/people/peopleComposition.ts").read_text(encoding="utf-8")
api = (ROOT / "src/hr/api/mobile.ts").read_text(encoding="utf-8")
norm = (ROOT / "src/hr/api/normalize.ts").read_text(encoding="utf-8")
tab = (ROOT / "app/hr/(tabs)/people.tsx").read_text(encoding="utf-8")
backend = Path(
    ROOT.parents[1] / "wathefni-orchestrator" / "operator_mobile_data.py"
).read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("People tab uses directory view", "HRPeopleDirectoryView" in tab)
check("Wordmark + EditorialHeading", "Wordmark" in view and "EditorialHeading" in view)
check("search is primary control", "searchPlaceholder" in view and "TextInput" in view)
check("dense ListRow not ActionableCard", "ListRow" in view and "ActionableCard" not in view)
check("exception chips via composition", "peopleExceptionChip" in view and "peopleExceptionChip" in comp)
check("row always opens employee profile", "`/employees/${encodeURIComponent(item.employee_key)}`" in view or '/employees/${encodeURIComponent(item.employee_key)}' in view)
check("onboarding chip separate path", "onOnboardingPress" in view and "`/onboarding/${encodeURIComponent(item.employee_key)}`" in view)
check("row does not hijack to onboarding", "openOnboarding\n                      ? `/onboarding/" not in view and "openOnboarding ?" not in view)
check("no Active chip for normal employees", "chipActive" not in comp and "'left' | 'onboarding'" in comp)
check("default status filter active", "PeopleStatusFilter" in comp and "'active'" in comp)
check("no attendance states on People", "present" not in comp and "absent" not in comp and "late" not in comp)
check("API search+paging", "search" in api and "offset" in api and "limit" in api)
check("onboarding_status normalized", "onboarding_status" in norm)
check(
    "backend forwards onboarding_status",
    '"onboarding_status": card.get("onboarding_status")' in backend,
)
keys = [
    "hrPeople.heading",
    "hrPeople.searchPlaceholder",
    "hrPeople.chipOnboarding",
    "hrPeople.chipLeft",
    "hrPeople.filterAll",
    "hrPeople.filterDepartment",
    "hrPeople.filterMore",
]
check("hrPeople keys EN+AR", all(k in en and k in ar for k in keys))
print("hr-people-directory: GREEN")
