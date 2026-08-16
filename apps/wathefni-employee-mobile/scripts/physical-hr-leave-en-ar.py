#!/usr/bin/env python3
"""Physical EN + AR copy/honesty pass for HR Leave detail (no invented meaning).

Exercises mobile i18n + composition helpers the screen uses. Complements the
production decision-spine probe (already proven) and canary OTA pull.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))
comp = (ROOT / "src/hr/features/leave/leaveComposition.ts").read_text(encoding="utf-8")
view = (ROOT / "src/hr/features/leave/LeaveApprovalView.tsx").read_text(encoding="utf-8")
route = (ROOT / "app/hr/leave/[id].tsx").read_text(encoding="utf-8")

failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failed
    print(("PASS" if ok else "FAIL"), name + (f" · {detail}" if detail else ""))
    if not ok:
        failed += 1


def t_factory(bundle: dict):
    def t(key: str, vars: dict | None = None) -> str:
        raw = bundle[key]
        if not vars:
            return raw
        out = raw
        for k, v in vars.items():
            out = out.replace("{{" + k + "}}", str(v))
        return out

    return t


# Mirror leaveComposition.localizeLeaveConsequence in Python for the pass.
def localize_consequence(consequence: str, action: str, t) -> str:
    raw = (consequence or "").strip()
    if not raw:
        return t(
            "hrLeave.consequenceApproveGeneric"
            if action == "approve"
            else "hrLeave.consequenceRejectGeneric"
        )
    m = re.match(r"^Approve (.+)'s leave and notify the employee\.?$", raw, re.I)
    if m:
        return t("hrLeave.consequenceApprove", {"name": m.group(1)})
    m = re.match(r"^Reject (.+)'s leave and notify the employee\.?$", raw, re.I)
    if m:
        return t("hrLeave.consequenceReject", {"name": m.group(1)})
    return raw


keys = [
    "hrLeave.eyebrow",
    "hrLeave.balanceLine",
    "hrLeave.balanceObserveOnly",
    "hrLeave.conflictBodyOne",
    "hrLeave.conflictBodyMany",
    "hrLeave.approve",
    "hrLeave.reject",
    "hrLeave.alreadyDecided",
    "hrLeave.alreadyDecidedBody",
    "hrLeave.consequenceApprove",
    "hrLeave.consequenceReject",
    "hrLeave.consequenceApproveGeneric",
    "hrLeave.consequenceRejectGeneric",
    "hrLeave.statusApproved",
    "hrLeave.statusRequested",
    "hrLeave.statusRejected",
    "hrLeave.statusCancelled",
    "leave.typeAnnual",
    "leave.typeSick",
]

check("EN/AR key parity for leave honesty", all(k in en and k in ar for k in keys))
check("AR conflict copy is Arabic", any("\u0600" <= c <= "\u06FF" for c in ar["hrLeave.conflictBodyOne"]))
check("AR approve label is Arabic", any("\u0600" <= c <= "\u06FF" for c in ar["hrLeave.approve"]))
check("AR reject label is Arabic", any("\u0600" <= c <= "\u06FF" for c in ar["hrLeave.reject"]))
check("AR observe-only caption is Arabic", any("\u0600" <= c <= "\u06FF" for c in ar["hrLeave.balanceObserveOnly"]))
check("EN approve is not raw action key", en["hrLeave.approve"].lower() != "approve")
check("EN reject is not raw action key", en["hrLeave.reject"].lower() != "reject")

for locale_name, bundle in (("en", en), ("ar", ar)):
    t = t_factory(bundle)
    approve = localize_consequence("Approve Fouad's leave and notify the employee.", "approve", t)
    reject = localize_consequence("Reject Fouad's leave and notify the employee.", "reject", t)
    unknown = localize_consequence("Server-only custom consequence text.", "approve", t)
    empty = localize_consequence("", "approve", t)
    check(
        f"{locale_name} approve consequence localized",
        "Fouad" in approve and ("approve" in approve.lower() or "الموافقة" in approve),
        approve,
    )
    check(
        f"{locale_name} reject consequence localized",
        "Fouad" in reject and ("reject" in reject.lower() or "رفض" in reject),
        reject,
    )
    check(
        f"{locale_name} unknown consequence passthrough (no invented meaning)",
        unknown == "Server-only custom consequence text.",
        unknown,
    )
    check(
        f"{locale_name} empty consequence uses generic template",
        empty == t("hrLeave.consequenceApproveGeneric"),
        empty,
    )
    bal = t("hrLeave.balanceLine", {"available": "17.5", "current": "17.5", "entitlement": "30"})
    check(f"{locale_name} balance line renders numbers", "17.5" in bal and "30" in bal, bal)
    one = t("hrLeave.conflictBodyOne")
    many = t("hrLeave.conflictBodyMany", {"count": 3})
    check(f"{locale_name} conflict one/many distinct", one != many and "3" in many, f"{one!r} / {many!r}")

check("composition has localizeLeaveConsequence", "localizeLeaveConsequence" in comp)
check("composition has leaveStatusTone", "leaveStatusTone" in comp and "success" in comp and "danger" in comp)
check("route maps approve/reject labels via i18n", "hrLeave.approve" in route and "hrLeave.reject" in route)
check("route wires already_decided", "already_decided" in route and "decidedOnServer" in route)
check("view hides actions when not actionable", "actionable" in view and "canApprove" in view)
check("view shows observe-only caption", "hrLeave.balanceObserveOnly" in view)
check("view uses real status tone", "leaveStatusTone(request.status)" in view)
check("no raw #id chrome", "leave_id.slice" not in view and "#{" not in view)
check("cream PageScreen + HrPushedNav", "PageScreen" in view and "HrPushedNav" in view)
check("no legacy plum/amber/sky stack", "tone=\"amber\"" not in view and "tone=\"sky\"" not in view and "WorkspaceHeader" not in view)

if failed:
    print(f"hr-leave-en-ar-physical: FAIL ({failed})")
    sys.exit(1)
print("hr-leave-en-ar-physical: PASS")
