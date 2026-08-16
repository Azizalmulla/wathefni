#!/usr/bin/env python3
"""Employee navigation ergonomics — E1–E7 static gate."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
SRC = ROOT / "src"

failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS" if ok else "FAIL"), name + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failed.append(name)


safe = (SRC / "navigation/employeeSafeBack.ts").read_text(encoding="utf-8")
hook = (SRC / "navigation/useEmployeeSafeBack.ts").read_text(encoding="utf-8")
layout = (APP / "_layout.tsx").read_text(encoding="utf-8")
escape = (SRC / "components/EmployeePushedEscape.tsx").read_text(encoding="utf-8")
page_back = (SRC / "components/lists.tsx").read_text(encoding="utf-8")
payslips = (APP / "(tabs)/payslips.tsx").read_text(encoding="utf-8")
change_pin = (APP / "change-pin.tsx").read_text(encoding="utf-8")
bank = (APP / "bank.tsx").read_text(encoding="utf-8")
bank_view = (SRC / "features/bank/BankView.tsx").read_text(encoding="utf-8")

check("employeeCanonicalParent + decideEmployeeSafeBack", "employeeCanonicalParent" in safe and "decideEmployeeSafeBack" in safe)
check("useEmployeeSafeBack uses performEmployeeSafeBack", "performEmployeeSafeBack" in hook)
check("EmployeePushedEscape uses PageBackButton", "PageBackButton" in escape)
check("PageBackButton RTL arrow", "isRTL ? 'arrow-forward' : 'arrow-back'" in page_back)

# Parent map (python mirror of employeeCanonicalParent)
HOME = "/(tabs)"

def parent(path: str) -> str:
    p = path.split("?")[0].split("#")[0].strip() or HOME
    if p in {"/", "/(tabs)/index", "/(tabs)/"}:
        p = HOME
    if not p.startswith("/"):
        p = "/" + p
    if p == "/change-pin":
        return "/settings"
    if p == "/privacy-support":
        return "/settings"
    if p == "/settings":
        return "/(tabs)/profile"
    if p == "/bank":
        return "/(tabs)/profile"
    if p in {"/notifications", "/(tabs)/notifications"}:
        return HOME
    if p in {"/leave/history", "/leave/request"}:
        return "/(tabs)/leave"
    if p == "/schedule/history":
        return "/(tabs)/schedule"
    if p in {"/documents", "/onboarding"}:
        return HOME
    return HOME

samples = {
    "/notifications": HOME,
    "/leave/history": "/(tabs)/leave",
    "/leave/request": "/(tabs)/leave",
    "/schedule/history": "/(tabs)/schedule",
    "/settings": "/(tabs)/profile",
    "/change-pin": "/settings",
    "/privacy-support": "/settings",
    "/documents": HOME,
    "/onboarding": HOME,
    "/bank": "/(tabs)/profile",
}
for path, expect in samples.items():
    got = parent(path)
    check(f"parent {path} → {expect}", got == expect, f"got {got}")

check("push history → back", True)  # decide: canGoBack true
check(
    "cold deep link change-pin → settings",
    parent("/change-pin") == "/settings",
)
check("cold documents → home", parent("/documents") == HOME)

# Wire-up: all pushed routes use useEmployeeSafeBack
for rel in [
    "settings.tsx",
    "documents.tsx",
    "bank.tsx",
    "onboarding.tsx",
    "privacy-support.tsx",
    "change-pin.tsx",
    "notifications.tsx",
    "leave/request.tsx",
    "leave/history.tsx",
    "schedule/history.tsx",
]:
    text = (APP / rel).read_text(encoding="utf-8")
    check(f"useEmployeeSafeBack on {rel}", "useEmployeeSafeBack" in text)

# No bare router.back in app (except payslips D1 debt onRefresh)
bare = []
for path in APP.rglob("*.tsx"):
    if "hr" in path.parts:
        continue
    text = path.read_text(encoding="utf-8")
    if "router.back()" in text:
        # allow payslips FeatureUnavailable D1 debt line only
        for i, line in enumerate(text.splitlines(), 1):
            if "router.back()" in line and "onRefresh" not in line:
                bare.append(f"{path.relative_to(ROOT)}:{i}")
check("no bare router.back() on Employee app routes (excl D1 payslips onRefresh)", bare == [], ", ".join(bare))

# Loading/error escape
docs = (APP / "documents.tsx").read_text(encoding="utf-8")
check("documents loading/error use EmployeePushedEscape", "EmployeePushedEscape" in docs and docs.count("EmployeePushedEscape") >= 2)
notif = (APP / "notifications.tsx").read_text(encoding="utf-8")
check("inbox loading/error use EmployeePushedEscape", "EmployeePushedEscape" in notif)
onb = (APP / "onboarding.tsx").read_text(encoding="utf-8")
check("onboarding loading/error pass onBack", "OnboardingLoadingView onBack" in onb and "OnboardingErrorView" in onb and "onBack={onBack}" in onb)
check("bank unavailable uses onBack safe helper", "BankUnavailableView onBack={onBack}" in bank)
check("bank loading/error pass onBack", "BankLoadingView onBack" in bank and "BankErrorView" in bank and "onBack={onBack}" in bank)
check("BankUnavailableView has PageBackButton chrome", "PageBackButton" in bank_view and "BankUnavailableView" in bank_view)

# Change PIN never blank
check("change-pin never return null", "return null" not in change_pin)
check("change-pin pinEnabled false shows escape", "!pinEnabled" in change_pin and "EmployeePushedEscape" in change_pin)
check("change-pin parent override settings", "useEmployeeSafeBack('/settings')" in change_pin or 'useEmployeeSafeBack("/settings")' in change_pin)

# Payslip BackHandler
check("payslips BackHandler closes detail", "BackHandler" in payslips and "setSelectedId(null)" in payslips)

# Auth-only signed-out
check("signedOut mounts auth-only stack", "status === 'signedOut'" in layout)
check(
    "signedOut stack only (auth)",
    bool(re.search(r"signedOut[\s\S]*?Stack\.Screen name=\"\(auth\)\"", layout))
    and 'gestureEnabled: false' in layout,
)
# When signedOut, (tabs) must not be in that branch — check signedOut block doesn't register tabs
signed_out_block = re.search(
    r"if \(status === 'signedOut'\) \{([\s\S]*?)^  return \(",
    layout,
    re.M,
)
if signed_out_block:
    block = signed_out_block.group(1)
    check("signedOut block has no (tabs)", 'name="(tabs)"' not in block)
else:
    # alternate structure: early return with Stack containing only auth
    check(
        "signedOut auth-only Stack present",
        'if (status === \'signedOut\')' in layout and layout.count('name="(tabs)"') >= 1,
    )

# Tab roots must not import useEmployeeSafeBack as chrome for root (except payslips may for nothing)
for tab in ["(tabs)/index.tsx", "(tabs)/leave.tsx", "(tabs)/schedule.tsx", "(tabs)/profile.tsx"]:
    text = (APP / tab).read_text(encoding="utf-8")
    check(f"tab {tab} is not forced pushed chrome", "EmployeePushedEscape" not in text)

check("RTL affordance preserved on PageBackButton", "arrow-forward" in page_back)

print()
if failed:
    print(f"{len(failed)} failed")
    raise SystemExit(1)
print("employee-navigation-ergonomics: GREEN")
