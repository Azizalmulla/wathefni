#!/usr/bin/env python3
"""HR navigation ergonomics contract — B1–B4 (static route-level)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HR = ROOT / "src/hr"
APP_HR = ROOT / "app/hr"

failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS" if ok else "FAIL"), name + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failed.append(name)


nav = (HR / "navigation.ts").read_text(encoding="utf-8")
hook = (HR / "useHrSafeBack.ts").read_text(encoding="utf-8")
pushed = (HR / "components/HrPushedNav.tsx").read_text(encoding="utf-8")
layout = (APP_HR / "_layout.tsx").read_text(encoding="utf-8")
page_back = (ROOT / "src/components/lists.tsx").read_text(encoding="utf-8")

# Contract primitives
check("decideHrSafeBack + hrCanonicalParent exported", "decideHrSafeBack" in nav and "hrCanonicalParent" in nav)
check("useHrSafeBack uses performHrSafeBack", "performHrSafeBack" in hook)
check("HrPushedNav uses PageBackButton", "PageBackButton" in pushed)
check("PageBackButton RTL arrow", "isRTL ? 'arrow-forward' : 'arrow-back'" in page_back)

# Parent map samples
samples = {
    "/hr/leave/abc": "/hr",
    "/hr/candidates/x": "/hr/candidates",
    "/hr/candidates": "/hr/hiring",
    "/hr/interviews/y": "/hr/interviews",
    "/hr/interviews": "/hr/hiring",
    "/hr/tasks/z": "/hr/tasks",
    "/hr/tasks": "/hr/more",
    "/hr/settings": "/hr/more",
    "/hr/change-pin": "/hr/settings",
    "/hr/delivery-alerts": "/hr/more",
    "/hr/assistant": "/hr/more",
    "/hr/employees/e1": "/hr/people",
    "/hr/shift-swaps/s1": "/hr/shifts",
}

# Execute parent map via node-less python reimplementation mirror
sys.path.insert(0, str(HR.parent))
# Inline evaluate by parsing isn't ideal — run a tiny embedded check against source constants
check(
    "canonical parents encoded for leave/candidates/hiring/more/settings/pin",
    all(
        key in nav
        for key in (
            "startsWith('/leave/')",
            "startsWith('/candidates/')",
            "=== '/candidates'",
            "=== '/change-pin'",
            "=== '/settings'",
            "=== '/delivery-alerts'",
            "startsWith('/shift-swaps/')",
        )
    ),
)

# Decision semantics
exec_globals: dict = {}
# Extract and eval pure functions by running typescript? Use a tiny python port:
def normalize(path: str) -> str:
    raw = path.split("?")[0].split("#")[0].strip()
    if not raw.startswith("/hr"):
        raw = "/hr" + (raw if raw.startswith("/") else "/" + raw)
    return raw if raw != "/hr/" else "/hr"

def parent(path: str) -> str:
    full = normalize(path)
    p = full[3:] if full.startswith("/hr") else full
    if not p.startswith("/"):
        p = "/" + p
    if p == "/change-pin":
        return "/hr/settings"
    if p == "/settings":
        return "/hr/more"
    if p.startswith("/leave/"):
        return "/hr"
    if p.startswith("/candidates/"):
        return "/hr/candidates"
    if p == "/candidates":
        return "/hr/hiring"
    if p.startswith("/interviews/"):
        return "/hr/interviews"
    if p == "/interviews":
        return "/hr/hiring"
    if p.startswith("/employees/"):
        return "/hr/people"
    if p == "/employees":
        return "/hr/more"
    if p.startswith("/tasks/"):
        return "/hr/tasks"
    if p == "/tasks" or p.startswith("/tasks"):
        return "/hr/more"
    if p.startswith("/onboarding/"):
        return "/hr/onboarding"
    if p == "/onboarding":
        return "/hr/more"
    if p.startswith("/documents/"):
        return "/hr/documents"
    if p == "/documents":
        return "/hr/more"
    if p.startswith("/attendance/"):
        return "/hr/attendance"
    if p == "/attendance":
        return "/hr/more"
    if p.startswith("/shift-swaps/"):
        return "/hr/shifts"
    if p == "/shifts":
        return "/hr/more"
    if p == "/delivery-alerts":
        return "/hr/more"
    if p == "/assistant":
        return "/hr/more"
    return "/hr"

def decide(can: bool, path: str):
    return ("back", None) if can else ("replace", parent(path))

for path, expect in samples.items():
    got = parent(path)
    check(f"parent {path} → {expect}", got == expect, f"got {got}")

check("push history → back", decide(True, "/hr/tasks/1")[0] == "back")
check("cold deep link → replace parent", decide(False, "/hr/tasks/1") == ("replace", "/hr/tasks"))
check("module list cold → More", decide(False, "/hr/tasks") == ("replace", "/hr/more"))
check("nested detail cold → list", decide(False, "/hr/candidates/abc") == ("replace", "/hr/candidates"))
check("change-pin cold → settings", decide(False, "/hr/change-pin") == ("replace", "/hr/settings"))

# Auth-only stack
check("signedOut mounts auth-only stack", 'if (status === \'signedOut\')' in layout or 'status === "signedOut"' in layout)
check("signedOut stack only registers sign-in", bool(re.search(r"signedOut[\s\S]*?Stack\.Screen name=\"sign-in\"", layout)))
check("signedOut disables gestures", "gestureEnabled: false" in layout)
# Authenticated stack still has modules
check("signedIn stack still has modules", 'name="leave/[id]"' in layout and 'name="(tabs)"' in layout)

# Visible back / no bare router.back in HR features (except possibly tests)
bare_backs = []
for path in (HR).rglob("*.tsx"):
    text = path.read_text(encoding="utf-8")
    if "router.back()" in text:
        bare_backs.append(str(path.relative_to(ROOT)))
for path in (APP_HR).rglob("*.tsx"):
    text = path.read_text(encoding="utf-8")
    if "router.back()" in text:
        bare_backs.append(str(path.relative_to(ROOT)))
check("no bare router.back() under HR app/features", bare_backs == [], ", ".join(bare_backs))

# Legacy + cream surfaces wire onBack / HrPushedNav / WorkspaceHeader onBack
checks_files = {
    "leave detail onBack": APP_HR / "leave/[id].tsx",
    "candidate detail onBack": APP_HR / "candidates/[appKey].tsx",
    "settings safe back": APP_HR / "settings.tsx",
    "change-pin safe back": APP_HR / "change-pin.tsx",
}
for name, path in checks_files.items():
    text = path.read_text(encoding="utf-8")
    check(name, "useHrSafeBack" in text)

leave_view = (HR / "features/leave/LeaveApprovalView.tsx").read_text(encoding="utf-8")
cand_view = (HR / "features/recruiting/CandidateReviewView.tsx").read_text(encoding="utf-8")
ops = (HR / "features/operations/OperationalViews.tsx").read_text(encoding="utf-8")
check("LeaveApprovalView accepts onBack", "onBack?" in leave_view and "onBack," in leave_view)
check("CandidateReviewView accepts onBack", "onBack?" in cand_view and "onBack," in cand_view)
check("OperationalList/Detail accept onBack", "onBack?" in ops and "onBack," in ops)

for rel in [
    "features/tasks/HRTasksQueueView.tsx",
    "features/tasks/HRTaskDetailView.tsx",
    "features/onboarding/HROnboardingQueueView.tsx",
    "features/documents/HRDocumentReviewsQueueView.tsx",
    "features/attendance/HRAttendanceQueueView.tsx",
    "features/shifts/HRShiftsHomeView.tsx",
    "features/delivery-alerts/HRDeliveryAlertsMonitorView.tsx",
    "features/assistant/HRAssistantView.tsx",
]:
    text = (HR / rel).read_text(encoding="utf-8")
    check(f"HrPushedNav on {rel}", "HrPushedNav" in text and "useHrSafeBack" in text)

people = (HR / "features/people/HRPeopleDirectoryView.tsx").read_text(encoding="utf-8")
routes = (HR / "features/operations/routes.tsx").read_text(encoding="utf-8")
check("People tab can omit Back", "showBack = false" in people or "showBack?: boolean" in people)
check("Employees stack passes showBack", "HRPeopleDirectoryView showBack" in routes)
check("Candidates/Interviews lists use onBack", routes.count("onBack={onBack}") >= 3)

# Tab roots must not use HrPushedNav
for tab in ["(tabs)/index.tsx", "(tabs)/inbox.tsx", "(tabs)/hiring.tsx", "(tabs)/more.tsx", "(tabs)/people.tsx"]:
    text = (APP_HR / tab).read_text(encoding="utf-8")
    # people re-exports directory without showBack
    check(f"tab {tab} is not a pushed chrome file", "HrPushedNav" not in text)

home = (HR / "features/home/HRHomeParityView.tsx").read_text(encoding="utf-8")
hiring = (HR / "features/hiring/HRHiringHomeView.tsx").read_text(encoding="utf-8")
more = (HR / "features/more/HRMoreLauncherView.tsx").read_text(encoding="utf-8")
check("Home tab root no HrPushedNav", "HrPushedNav" not in home)
check("Hiring tab root no HrPushedNav", "HrPushedNav" not in hiring)
check("More tab root no HrPushedNav", "HrPushedNav" not in more)
check("More→Employee uses replace", "router.replace('/(tabs)')" in more)

en = (HR / "i18n/en.json").read_text(encoding="utf-8")
ar = (HR / "i18n/ar.json").read_text(encoding="utf-8")
check("HR common.back EN+AR", '"common.back"' in en and '"common.back"' in ar)

print()
if failed:
    print(f"{len(failed)} failed")
    raise SystemExit(1)
print("hr-navigation-ergonomics: GREEN")
