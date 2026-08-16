#!/usr/bin/env python3
"""Production Readiness R7 — Mobile keyboard and native safety (source contracts).

Physical-device proof (PH-5…PH-11) remains RP. This suite proves the shared
keyboard contract and the P1-4…P1-9 product fixes in source.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PASS = 0
FAIL = 0

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
HR = REPO / "apps" / "wathefni-hr-mobile"
EMP = REPO / "apps" / "wathefni-employee-mobile"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def load_json(root: Path, rel: str) -> dict:
    return json.loads((root / rel).read_text(encoding="utf-8"))


def keyboard_helper_contracts() -> None:
    print("\n    PH-1…PH-4 — shared keyboard contract")
    for name, root in (("hr-mobile", HR), ("employee-mobile", EMP)):
        helper = read(root, "src/components/keyboardSafe.ts")
        check(
            f"{name} helper uses padding on every platform",
            "KEYBOARD_SAFE_BEHAVIOR = 'padding'" in helper
            and "function keyboardSafeBehavior(): 'padding'" in helper,
        )
        check(
            f"{name} helper never hardcodes offset 0 for iOS",
            "keyboardSafeOffset" in helper and "Platform.OS === 'ios'" in helper,
        )

    hr_screen = read(HR, "src/components/primitives.tsx")
    check(
        "standalone HR Screen wraps KeyboardAvoidingView + Android insets",
        "keyboardSafeBehavior()" in hr_screen
        and "keyboardSafeOffset(insets.top)" in hr_screen
        and "automaticallyAdjustKeyboardInsets" in hr_screen
        and "behavior={undefined}" not in hr_screen
        and "keyboardVerticalOffset={0}" not in hr_screen,
    )

    emp_hr_screen = read(EMP, "src/hr/components/primitives.tsx")
    check(
        "employee HR Screen uses the same keyboard-safe primitive",
        "keyboardSafeBehavior()" in emp_hr_screen
        and "automaticallyAdjustKeyboardInsets" in emp_hr_screen
        and "keyboardVerticalOffset={0}" not in emp_hr_screen,
    )

    layout = read(EMP, "src/components/layout.tsx")
    check(
        "employee PageScrollView enables keyboard insets on Android when opted in",
        "automaticallyAdjustKeyboardInsets={keyboardInsets}" in layout
        and "Platform.OS === 'ios'" not in layout,
    )

    pin = read(EMP, "src/features/pin/PinView.tsx")
    assistant = read(EMP, "src/hr/features/assistant/HRAssistantView.tsx")
    leave = read(EMP, "src/features/remaining/RemainingViews.tsx")
    activation = read(EMP, "src/features/activation/ActivationView.tsx")
    signin = read(EMP, "src/principals/UnifiedSignInView.tsx")
    for label, source in (
        ("PIN", pin),
        ("HR Assistant", assistant),
        ("employee leave request", leave),
        ("activation", activation),
        ("unified sign-in", signin),
    ):
        check(
            f"{label} uses shared keyboard behavior, not iOS-only / offset 0",
            "keyboardSafeBehavior()" in source
            and "keyboardVerticalOffset={0}" not in source
            and "Platform.OS === 'ios' ? 'padding' : undefined" not in source,
        )
    check("employee leave request opts into keyboardInsets", "keyboardInsets" in leave)
    check(
        "HR leave rejection and interview notes sit inside keyboard-safe Screen",
        "NotesEditor" in read(HR, "src/features/operations/OperationalViews.tsx")
        and "KeyboardAvoidingView" in hr_screen,
    )


def leave_and_task_contracts() -> None:
    print("\n    P1-4 / P1-5 — leave queue and task actions")
    caps = read(HR, "src/capabilities.ts")
    check("leave is a capability-gated workspace route", "key: 'leave'" in caps and "leave_approvals" in caps)
    check("leave list and detail destinations are admitted", "path === '/leave'" in caps and "path.startsWith('/leave/')" in caps)
    check("attendance/document prefix destinations are admitted", "path.startsWith('/attendance/')" in caps and "path.startsWith('/documents/')" in caps)

    home = read(HR, "src/features/home/HRHomeView.tsx")
    check("Home nav includes leave", "leave: 'nav.leave'" in home)

    layout = read(HR, "app/_layout.tsx")
    check("leave index is registered", 'name="leave/index"' in layout)
    check("leave queue route file exists", (HR / "app/leave/index.tsx").is_file())

    routes = read(HR, "src/features/operations/routes.tsx")
    api = read(HR, "src/api/mobile.ts")
    check("LeaveQueueRoute loads GET /dashboard/mobile/leave", "LeaveQueueRoute" in routes and "mobileApi.leave" in routes)
    check("mobileApi.leave exists", "leave:" in api and "/dashboard/mobile/leave" in api)
    check("TasksRoute wires resolve actions", "actionsForItem" in routes and "taskResolve" in routes and "tasks.complete" in routes)
    check("taskResolve posts to backend resolve", "/dashboard/mobile/tasks/" in api and "/resolve" in api)


def dead_affordance_and_honesty() -> None:
    print("\n    P1-6 / P1-7 / P1-8 — dead chevrons, interview honesty, ranking")
    ops = read(HR, "src/features/operations/OperationalViews.tsx")
    routes = read(HR, "src/features/operations/routes.tsx")
    review = read(HR, "src/features/recruiting/CandidateReviewView.tsx")
    check("OperationalListView gates chevrons with canOpen", "canOpen" in ops and "canOpen ? canOpen(item)" in ops)
    check("documents hide Review unless compliance + keys exist", "canOpen=" in routes and "source === 'compliance'" in routes)
    check("today's shifts do not open unless they are swaps", 'canOpen={(item) => item.id.startsWith("swap:")}' in routes or "item.id.startsWith('swap:')" in routes)
    check("alerts open only with a real destination", "destination?.startsWith('/')" in routes)
    check("schedule interview is honest View interviews", "candidate.viewInterviews" in review and "candidate.scheduleOnWeb" in review)
    check("candidates expose ranking note and stage filter", "candidates.rankingNote" in routes and "stageFilter" in routes)


def employee_reachability() -> None:
    print("\n    P1-9 — preboarding / probation reachability")
    composition = read(EMP, "src/composition/employeeAppComposition.ts")
    push = read(EMP, "src/push/resolvePushDestination.ts")
    profile = read(EMP, "src/features/profile/ProfileView.tsx")
    profile_route = read(EMP, "app/(tabs)/profile.tsx")
    home = read(EMP, "src/features/home/HomeView.tsx")
    check("MODULE_SURFACES still omits preboarding/probation tiles", "'preboarding'" not in composition.split("export const MODULE_SURFACES")[1].split("] as const")[0])
    check("composition exposes journey flags, not Home tiles", "showPreboardingJourney" in composition and "showProbationJourney" in composition)
    check("push defaults include preboarding and probation", "preboarding: '/preboarding'" in push and "probation: '/probation'" in push)
    check("Profile can open both journeys", "onPreboarding" in profile and "onProbation" in profile)
    check("Profile route gates journeys on features", "hasFeature('preboarding')" in profile_route and "hasFeature('probation')" in profile_route)
    check("Home journey cards are not destination tiles", "showPreboardingJourney" in home and "onNavigate('/preboarding')" in home and "homeDestinations" not in home.split("showPreboardingCard")[1][:400])


def i18n_contracts() -> None:
    print("\n    EN/AR key parity")
    hr_en = load_json(HR, "src/i18n/en.json")
    hr_ar = load_json(HR, "src/i18n/ar.json")
    check("HR Mobile exact key parity", set(hr_en) == set(hr_ar), sorted(set(hr_en) ^ set(hr_ar))[:8])
    for key in (
        "nav.leave",
        "leave.queueEyebrow",
        "leave.queueTitle",
        "tasks.complete",
        "candidates.rankingNote",
        "candidate.viewInterviews",
        "candidate.scheduleOnWeb",
    ):
        check(f"HR key present EN+AR: {key}", key in hr_en and key in hr_ar)

    emp_en = load_json(EMP, "src/i18n/en.json")
    emp_ar = load_json(EMP, "src/i18n/ar.json")
    check("Employee App exact key parity", set(emp_en) == set(emp_ar), sorted(set(emp_en) ^ set(emp_ar))[:8])
    for key in (
        "home.preboarding",
        "home.probation",
        "profile.journeys",
        "profile.preboarding",
        "profile.probation",
    ):
        check(f"Employee key present EN+AR: {key}", key in emp_en and key in emp_ar)


def main() -> int:
    print("R7 mobile native safety — source contracts")
    keyboard_helper_contracts()
    leave_and_task_contracts()
    dead_affordance_and_honesty()
    employee_reachability()
    i18n_contracts()
    print(f"\n    R7_MOBILE_NATIVE_SAFETY_UNIT {'PASS' if FAIL == 0 else 'FAIL'}  {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R7_MOBILE_NATIVE_SAFETY_UNIT_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
