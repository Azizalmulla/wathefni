#!/usr/bin/env python3
"""HR Settings — operator + device + local Device Security contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
view = (ROOT / "src/hr/features/settings/SettingsView.tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/settings/settingsComposition.ts").read_text(encoding="utf-8")
route = (ROOT / "app/hr/settings.tsx").read_text(encoding="utf-8")
more = (ROOT / "src/hr/features/more/HRMoreLauncherView.tsx").read_text(encoding="utf-8")
probe = ROOT / "src/hr/features/settings/HrSessionQueueProbe.tsx"
employee_settings = (ROOT / "src/features/remaining/RemainingViews.tsx").read_text(encoding="utf-8")
employee_settings_route = (ROOT / "app/settings.tsx").read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("cream PageScreen/ListRow", "PageScreen" in view and "ListRow" in view)
check("no WorkspaceHeader locale chip", "WorkspaceHeader" not in view)
check("no raw permission_authority", "permission_authority" not in view)
check("no scope.binding / configuration_error UI", "configuration_error" not in view and "scope.binding" not in view)
check("role humanized", "operatorRoleLabel" in comp)
check("refresh /me", "onRefresh" in view and "refreshMe" in route)
check("customer diagnostics removed", not probe.exists() and "HrSessionQueueProbe" not in view)
check(
    "no API/session/OTA/queue diagnostics",
    all(token not in view for token in ("sectionProbe", "probeHint", "sectionAccess", "accessHint")),
)
check("sign-out confirms Settings", "signOutConfirmTitle" in view and "signOutAllConfirmTitle" in view)
check("sign-out confirm More", "signOutConfirmTitle" in more and "Alert.alert" in more)
check("web note", "hrSettings.webNote" in view)
check("device security section present", "sectionDeviceSecurity" in view and "biometric.settings" in view and "autoLock.settings" in view)
check("no push registration invent", "push" not in view.lower() or "Push" not in view)
check("no settings write API invent", "/mobile/settings" not in route and "settings/" not in route.split("SettingsView")[0])
check("switch employee optional", "onSwitchEmployee" in view and "employeeSession" in route)
check("change pin wired", "change-pin" in route and "pin.change" in view)
check("notifications opens device settings", "onOpenNotificationSettings" in view and "Linking.openSettings" in route)
check("privacy and support use approved URLs", "onOpenPrivacy" in view and "PRIVACY_URL" in route and "SUPPORT_URL" in route)
check("About OctoHR version", "hrSettings.aboutTitle" in view and "expoConfig?.version" in route)
check(
    "unified release settings expose no auto-lock diagnostics",
    "autoLockDiagnostics" not in employee_settings and "autoLockDiagnostics" not in employee_settings_route,
)
check(
    "OctoHR customer branding EN+AR",
    all(token not in json.dumps({"en": en, "ar": ar}, ensure_ascii=False) for token in ("Wathefni", "WATHEFNI", "وظفني", "وثفني")),
)

keys = [
    "hrSettings.title",
    "hrSettings.webNote",
    "hrSettings.signOutAllConfirmBody",
    "hrSettings.notifications",
    "hrSettings.sectionPrivacySupport",
    "hrSettings.sectionAbout",
    "hrSettings.sectionDeviceSecurity",
    "hrMore.settingsBody",
]
check("hrSettings keys EN+AR", all(k in en and k in ar for k in keys))
check(
    "More body describes production Settings",
    "profile" in en.get("hrMore.settingsBody", "").lower()
    and "security" in en.get("hrMore.settingsBody", "").lower(),
)
print("hr-settings-operator-device: GREEN")
