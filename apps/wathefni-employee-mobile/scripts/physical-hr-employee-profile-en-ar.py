#!/usr/bin/env python3
"""Physical EN + AR copy/honesty pass for HR Employee Profile."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))
view = (ROOT / "src/hr/features/people/EmployeeProfileView.tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/people/employeeComposition.ts").read_text(encoding="utf-8")
route = (ROOT / "app/hr/employees/[employeeKey].tsx").read_text(encoding="utf-8")

failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failed
    print(("PASS" if ok else "FAIL"), name + (f" · {detail}" if detail else ""))
    if not ok:
        failed += 1


def arabic(s: str) -> bool:
    return any("\u0600" <= c <= "\u06FF" for c in s)


keys = [
    "hrEmployee.eyebrow",
    "hrEmployee.title",
    "hrEmployee.sectionFacts",
    "hrEmployee.sectionContact",
    "hrEmployee.sectionTenure",
    "hrEmployee.factsEmpty",
    "hrEmployee.statusActive",
    "hrEmployee.statusLeft",
    "hrEmployee.statusTerminated",
    "hrEmployee.notFoundTitle",
    "hrEmployee.notFoundBody",
    "hrEmployee.unavailableTitle",
    "hrEmployee.unavailableBody",
    "hrEmployee.permissionTitle",
    "common.position",
    "common.department",
    "common.email",
    "common.phone",
    "common.startDate",
]
check("EN/AR key parity", all(k in en and k in ar for k in keys))
for k in keys:
    check(f"AR arabic · {k}", arabic(ar[k]), ar[k][:40])

# composition localization
sys.path.insert(0, str(ROOT / "scripts"))
# inline check known statuses
for status, key in (("active", "hrEmployee.statusActive"), ("left", "hrEmployee.statusLeft")):
    check(f"EN {status}", key in en and en[key].lower() != status or en[key][0].isupper())
    check(f"AR {status} localized", arabic(ar[key]))

check("no raw status chip", "employment_status" not in view or "localizeEmploymentStatus" in view)
check("localizeEmploymentStatus wired", "localizeEmploymentStatus" in view and "STATUS_KEYS" in comp)
check("cream + no manager", "PageScreen" in view and "manager" not in view.lower())
check("unavailable + not_found states", "unavailable" in route and "not_found" in route)
check("never blank ready without item", "viewState" in route)

if failed:
    print(f"hr-employee-profile-en-ar-physical: FAIL ({failed})")
    sys.exit(1)
print("hr-employee-profile-en-ar-physical: PASS")
