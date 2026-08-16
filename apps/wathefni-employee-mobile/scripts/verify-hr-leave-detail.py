#!/usr/bin/env python3
"""HR Leave detail honesty + cream migration contracts."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
view = (ROOT / "src/hr/features/leave/LeaveApprovalView.tsx").read_text(encoding="utf-8")
route = (ROOT / "app/hr/leave/[id].tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/leave/leaveComposition.ts").read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("cream PageScreen + HrPushedNav", "PageScreen" in view and "HrPushedNav" in view)
check("no legacy WorkspaceHeader/plum stack", "WorkspaceHeader" not in view and "plum" not in view.lower() and "tone=\"amber\"" not in view and "tone=\"sky\"" not in view)
check("real balance rendering", "parseLeaveBalances" in view and "hrLeave.balanceLine" in view and "hrLeave.balanceObserveOnly" in view)
check("no fake balance placeholder", "Authoritative balance context is available" not in view)
check("localized conflict copy", "hrLeave.conflictBodyOne" in view and "hrLeave.conflictBodyMany" in view)
check("no raw request id chrome", "leave_id.slice" not in view and "#{" not in view)
check("status tone from real status", "leaveStatusTone" in view and 'tone="attention"' not in view)
check("already_decided wired in route", "already_decided" in route and "decidedOnServer" in route)
check("confirm action localized", "hrLeave.approve" in route and "localizeLeaveConsequence" in route)
check("priorities + leave invalidate", "mobile-priorities" in route and "['leave', id]" in route)
check("safe-back preserved", "useHrSafeBack" in route)
check("confirm error surface", "confirmError" in view and "confirm.errorGeneric" in view)
check(
    "sheet outside scroll",
    view.rfind("</PageScrollView>") < view.rfind("<ConfirmationSheet")
    and view.rfind("<ConfirmationSheet") < view.rfind("</PageScreen>"),
)
check("post-success refresh non-blocking", "void Promise.all" in route)

keys = [
    "hrLeave.eyebrow",
    "hrLeave.balanceLine",
    "hrLeave.balanceObserveOnly",
    "hrLeave.conflictBodyOne",
    "hrLeave.conflictBodyMany",
    "hrLeave.approve",
    "hrLeave.reject",
    "hrLeave.alreadyDecided",
    "hrLeave.consequenceApprove",
    "hrLeave.consequenceReject",
    "hrLeave.statusApproved",
    "hrLeave.statusRequested",
]
check("hrLeave keys EN+AR", all(k in en and k in ar for k in keys))
check("composition helpers present", "localizeLeaveConsequence" in comp and "leaveStatusTone" in comp)

print("hr-leave-detail: GREEN")
