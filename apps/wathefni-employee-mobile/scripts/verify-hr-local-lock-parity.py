#!/usr/bin/env python3
"""HR Local Lock parity — Employee Auth Wave 2 Phases 0–5, separate operator authority."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

auth = (ROOT / "src/hr/auth/AuthProvider.tsx").read_text(encoding="utf-8")
pin_store = (ROOT / "src/hr/auth/localLock/hrPinStorage.ts").read_text(encoding="utf-8")
bio_store = (ROOT / "src/hr/auth/localLock/hrBiometricStorage.ts").read_text(encoding="utf-8")
auto_store = (ROOT / "src/hr/auth/localLock/hrAutoLockStorage.ts").read_text(encoding="utf-8")
policy = (ROOT / "src/hr/auth/localLock/hrPolicy.ts").read_text(encoding="utf-8")
principal = (ROOT / "src/hr/auth/localLock/principalKey.ts").read_text(encoding="utf-8")
crypto = (ROOT / "src/hr/auth/localLock/hrPinCrypto.ts").read_text(encoding="utf-8")
shell = (ROOT / "src/hr/features/local-lock/HRLocalUnlockShell.tsx").read_text(encoding="utf-8")
overlay = (ROOT / "src/hr/features/local-lock/HRLocalUnlockOverlay.tsx").read_text(encoding="utf-8")
layout = (ROOT / "app/hr/_layout.tsx").read_text(encoding="utf-8")
settings = (ROOT / "src/hr/features/settings/SettingsView.tsx").read_text(encoding="utf-8")
settings_route = (ROOT / "app/hr/settings.tsx").read_text(encoding="utf-8")
change_pin = (ROOT / "app/hr/change-pin.tsx").read_text(encoding="utf-8")
emp_session = (ROOT / "src/auth/session.ts").read_text(encoding="utf-8")
hr_session = (ROOT / "src/hr/auth/session.ts").read_text(encoding="utf-8")
gate = (ROOT / "src/features/pin/UnlockWithBiometricGate.tsx").read_text(encoding="utf-8")
flows = (ROOT / "src/features/pin/PinFlows.tsx").read_text(encoding="utf-8")
root_layout = (ROOT / "app/_layout.tsx").read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


# Storage isolation
check("HR PIN keys namespaced", "wathefni.hr.pin.verifier" in pin_store and "wathefni.hr.pin.principal_key" in pin_store)
check("no employee pin keys in HR store", "wathefni.pin.verifier" not in pin_store and "employee_key" not in pin_store)
check("HR bio keys namespaced", "wathefni.hr.biometric.enabled" in bio_store)
check("HR autolock key namespaced", "wathefni.hr.autolock.timeout_ms" in auto_store)
check("HR pepper distinct", "wathefni.hr.local.pin.v1" in crypto and "wathefni.local.pin.v1" not in crypto)
check("principal = company:user_id", "company_code" in principal and "user_id" in principal)
check("session stores still separate", "wathefni.session.token" in emp_session and "wathefni.hr.access_token" in hr_session)

# Auth provider parity surface
check("HR statuses include lock/setup/bio", all(s in auth for s in ("'locked'", "'needsPinSetup'", "'needsBiometricOptIn'")))
check("sealed session model", "sealedSessionRef" in auth)
check("create/unlock/change PIN", all(k in auth for k in ("createLocalPin", "unlockWithPin", "changeLocalPin")))
check("biometric opt-in + settings toggle", "finishBiometricOptIn" in auth and "setBiometricUnlockEnabled" in auth)
check("recovery is operator re-auth", "recoverLocalLockByReauth" in auth and "/dashboard/mobile/auth/logout" in auth)
check("recovery not employee OTP", "/app/auth/" not in auth)
check("login endpoint operator", "/dashboard/mobile/auth/login" in auth)

# Shell mount
check("HRLocalUnlockShell in layout", "HRLocalUnlockShell" in layout)
check("AccessGate lock UI", "needsPinSetup" in layout and "UnlockWithBiometricGate" in layout)
check("change-pin route registered", "change-pin" in layout and "changeLocalPin" in change_pin)
check("overlay uses HR verifyPin", "verifyHrPin" in overlay)
check("bio cancel→PIN injectors", "shouldAttemptHrBiometricUnlock" in overlay and "shouldAttempt" in gate)
check("forgot copy override", "forgotConfirmKey" in flows and "hrPin.forgotConfirm" in overlay)

# Mode independence
check("Employee shell only in EmployeeShell", "LocalUnlockShell" in root_layout and "shell.kind === 'hr'" in root_layout)
check("HR shell not in EmployeeShell", "HRLocalUnlockShell" not in root_layout)

# Settings device security
check("Settings device security section", "sectionDeviceSecurity" in settings and "autoLock.settings" in settings)
check("Settings wires bio + autolock + change pin", "setBiometricUnlockEnabled" in settings_route and "setAutoLockTimeout" in settings_route and "change-pin" in settings_route)

# i18n
keys = ["hrPin.forgotConfirm", "hrPin.tooManyAttempts", "hrSettings.sectionDeviceSecurity", "pin.createTitle", "biometric.settings", "autoLock.settings"]
check("EN+AR keys", all(k in en and k in ar for k in keys))
check("HR forgot mentions email/password", "password" in en["hrPin.forgotConfirm"].lower() or "email" in en["hrPin.forgotConfirm"].lower())

# No Phase 6
check("no device screen-lock phase 6", "isDeviceScreenLocked" not in shell and "deviceLock" not in auth)

print("hr-local-lock-parity: GREEN")
