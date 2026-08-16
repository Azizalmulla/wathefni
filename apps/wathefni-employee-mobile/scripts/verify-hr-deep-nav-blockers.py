#!/usr/bin/env python3
"""Release-blocker contract: principal isolation + destination truth + fail-closed APIs.

Static smokes for:
  1. Employee shell never mounts /hr (no Stack.Screen name=hr; sync Redirect deny)
  2. Backend never emits /ranking or filtered /candidates?… destinations
  3. Hiring (+ Delivery Alerts) gate opens with destinationAvailable
  4. Leave + Candidate mobile adapters require _require_mobile_feature_action
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
LAYOUT = (ROOT / "app/_layout.tsx").read_text(encoding="utf-8")
HIRING = (ROOT / "src/hr/features/hiring/HRHiringHomeView.tsx").read_text(encoding="utf-8")
ALERTS = (
    ROOT / "src/hr/features/delivery-alerts/HRDeliveryAlertsMonitorView.tsx"
).read_text(encoding="utf-8")
CAPS = (ROOT / "src/hr/capabilities.ts").read_text(encoding="utf-8")
DATA = (REPO / "wathefni-orchestrator/operator_mobile_data.py").read_text(encoding="utf-8")
CAND_ROUTE = (ROOT / "app/hr/candidates/[appKey].tsx").read_text(encoding="utf-8")
LEAVE_ROUTE = (ROOT / "app/hr/leave/[id].tsx").read_text(encoding="utf-8")


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


# --- 1. Principal isolation ---
check("Employee Stack does not register hr screen", 'name="hr"' not in LAYOUT and "name='hr'" not in LAYOUT)
check(
    "ModeRedirect sync hard-deny /hr for employee",
    "synchronous hard-deny of /hr" in LAYOUT
    or ("shell.kind === 'employee'" not in LAYOUT and "segments[0] === 'hr'" in LAYOUT and "Redirect href=\"/(tabs)\"" in LAYOUT),
)
check("AuthGate redirects employee away from /hr", "segments[0] === 'hr'" in LAYOUT and "router.replace('/(tabs)')" in LAYOUT)
check("No async hrWorkspaceEnabled employee/hr bounce", "hrWorkspaceEnabled" not in LAYOUT)

# --- 2. Destination truth (backend) ---
check("no /ranking destination emit", "/ranking?" not in DATA and 'f"/ranking' not in DATA)
for dead in (
    "/candidates?follow_up=",
    "/candidates?review_status=",
    "/candidates?assessment_status=",
):
    check(f"no soft-dead emit {dead}", dead not in DATA)
check("prehire priorities use /candidates", '"destination": "/candidates"' in DATA)

# --- 3. Client destination gate ---
check("destinationAvailable helper exists", "export function destinationAvailable" in CAPS)
check("Hiring open uses destinationAvailable", "destinationAvailable(me, destination)" in HIRING)
check("Hiring filters priority sections by destinationAvailable", "destinationAvailable(me, item.destination)" in HIRING)
check(
    "Delivery Alerts open uses destinationAvailable",
    "destinationAvailable(me, item.destination" in ALERTS,
)

# --- 4. Direct deep-link route permission surfaces ---
check("candidate detail gates routeAvailable", "routeAvailable(me, 'candidates')" in CAND_ROUTE)
check("leave detail surfaces permission state", "'permission'" in LEAVE_ROUTE)

# --- 5. Fail-closed APIs ---
check(
    "leave list requires mobile feature action",
    '_require_mobile_feature_action(app_mod, context, "hr", "leave_approvals", "read")' in DATA,
)
check(
    "leave detail requires mobile feature action",
    DATA.count('_require_mobile_feature_action(app_mod, context, "hr", "leave_approvals", "read")')
    >= 2,
)
check(
    "leave decision requires approve/reject feature action",
    '_require_mobile_feature_action(app_mod, context, "hr", "leave_approvals", action)' in DATA,
)
check(
    "candidate rankings requires feature action",
    '_require_mobile_feature_action(app_mod, context, "recruiting", "candidate_rankings", "read")'
    in DATA,
)
check(
    "candidate detail requires feature action",
    '_require_mobile_feature_action(app_mod, context, "recruiting", "candidate_summary", "read")'
    in DATA,
)
check(
    "candidate CV requires feature action",
    '_require_mobile_feature_action(app_mod, context, "recruiting", "candidate_cv", "view")' in DATA,
)
check(
    "candidate decision maps to feature actions",
    '"candidate_shortlist"' in DATA and '"candidate_reject"' in DATA and '"candidate_hire"' in DATA,
)

print("hr-deep-nav-blockers: GREEN")
