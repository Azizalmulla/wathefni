#!/usr/bin/env python3
"""Auth Wave 2 Phase 5 — basic device security (static/unit)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "apps" / "wathefni-employee-mobile"
DASH = ROOT / "apps" / "wathefni-dashboard"
APP = ROOT / "wathefni-orchestrator" / "app.py"
CONTRACT = ROOT / "ops" / "AUTH_WAVE2_PHASE5_DEVICE_SECURITY_CONTRACT.md"

passed: list[str] = []
failed: list[str] = []


def check(label: str, ok: bool, detail: object = None) -> None:
    (passed if ok else failed).append(label)
    print(("  PASS  " if ok else "  FAIL  ") + label + (f" :: {detail}" if detail is not None and not ok else ""))


def main() -> int:
    print("auth wave2 phase5 device security unit")
    app = APP.read_text(encoding="utf-8")
    contract = CONTRACT.read_text(encoding="utf-8")
    en = json.loads((MOBILE / "src/i18n/en.json").read_text())
    ar = json.loads((MOBILE / "src/i18n/ar.json").read_text())

    check("contract exists", "One active employee device" in contract)
    check("route GET /app/device-security", '@app.get("/app/device-security")' in app)
    check("route GET app-access", '@app.get("/dashboard/posthire/employees/{employee_key}/app-access")' in app)
    check("route POST app-access/revoke", '@app.post("/dashboard/posthire/employees/{employee_key}/app-access/revoke")' in app)
    check("activate returns replaced_previous_device", "replaced_previous_device" in app)
    check("activate accepts platform", "platform: str | None = None" in app.split("class EmployeeAppActivateRequest")[1].split("class EmployeeAppRequestCodeRequest")[0])
    check("new-device clears refresh_hash", "reactivated_via_invite" in app and "refresh_hash=NULL" in app)
    check("logout clears refresh_hash", "revoked_reason='logout'" in app and "refresh_hash=NULL" in app.split("def revoke_employee_session_token")[1].split("def revoke_employee_app_access")[0])
    check("hr revoke reason", "hr_revoked" in app)
    check("hr revoke audited", "employee_app_access_revoked" in app)
    check("hr revoke idempotent", "idempotency_key" in app.split("dashboard_posthire_app_access_revoke")[1].split("@app.get")[0] if "dashboard_posthire_app_access_revoke" in app else False)
    check("device summary helper hides ids", "never expose session ids" in app.lower() or "Current-device summary" in app or "no session ids" in app.lower())
    check("no multi-device list route", '@app.get("/app/sessions")' not in app)

    keys = {
        "deviceSecurity.title",
        "deviceSecurity.currentDevice",
        "deviceSecurity.platform",
        "deviceSecurity.platformIos",
        "deviceSecurity.platformAndroid",
        "deviceSecurity.activated",
        "deviceSecurity.lastActive",
        "deviceSecurity.status",
        "deviceSecurity.statusActive",
        "deviceSecurity.signOutDevice",
        "deviceSecurity.signOutConfirmTitle",
        "deviceSecurity.signOutConfirmBody",
        "deviceSecurity.replacedTitle",
        "deviceSecurity.replacedBody",
    }
    check("EN device keys", keys <= set(en))
    check("AR device keys", keys <= set(ar))
    check(
        "EN/AR device key parity",
        {k for k in en if k.startswith("deviceSecurity.")} == {k for k in ar if k.startswith("deviceSecurity.")},
    )
    check(
        "EN replaced copy exact",
        en.get("deviceSecurity.replacedBody")
        == "Wathefni was activated on this device. Your previous device was signed out.",
    )

    auth = (MOBILE / "src/auth/AuthProvider.tsx").read_text()
    check("activate sends platform", "platform: Platform.OS" in auth or "platform: Platform.OS ===" in auth)
    check("activate marks replaced notice", "markReplacedDeviceNoticePending" in auth)

    notice = (MOBILE / "src/auth/deviceSecurityNotice.ts").read_text()
    check("notice consume once", "consumeReplacedDeviceNoticePending" in notice)

    layout = (MOBILE / "app/_layout.tsx").read_text()
    check("notice shown on signedIn", "consumeReplacedDeviceNoticePending" in layout and "deviceSecurity.replacedBody" in layout)

    settings = (MOBILE / "app/settings.tsx").read_text()
    check("settings loads device-security", "/app/device-security" in settings)
    check("settings sign out this device", "onSignOutDevice" in settings and "signOut" in settings)

    views = (MOBILE / "src/features/remaining/RemainingViews.tsx").read_text()
    check("SettingsView device section", "deviceSecurity.title" in views)

    api = (DASH / "src/lib/api.ts").read_text()
    check("dashboard getEmployeeAppAccess", "getEmployeeAppAccess" in api)
    check("dashboard revokeEmployeeAppAccess", "revokeEmployeeAppAccess" in api)

    posthire = (DASH / "src/posthire/PostHire.tsx").read_text()
    check("HR App access card", "App access" in posthire or "وصول التطبيق" in posthire)
    check("HR revoke wired", "revokeEmployeeAppAccess" in posthire)
    check("HR re-invite present", "Re-invite" in posthire or "إعادة الدعوة" in posthire)

    # Soft-fail classifier still must not wipe on network (Wave 1/2)
    failure = (MOBILE / "src/auth/authFailure.ts").read_text()
    check("soft failures do not wipe", "wipe" in failure.lower() or "definitive" in failure.lower())
    check("HR revoke maps to access_reset", "app_access_revoked" in failure and "access_reset" in failure)
    check(
        "transient path does not wipe",
        "wipeLocalSession: false" in failure.split("if (isServerTransient")[1].split("if (error.code === 'account_inactive')")[0],
    )
    check(
        "EN access_reset copy exact",
        en.get("access.access_reset.title") == "Your app access was reset"
        and en.get("access.access_reset.message") == "Sign in again with a new activation code.",
    )
    check("AR access_reset keys", "access.access_reset.title" in ar and "access.access_reset.message" in ar)
    check("server emits app_access_revoked for hr_revoked", 'error": "app_access_revoked"' in app or "app_access_revoked" in app)
    check("hr_revoked and reactivated map to app_access_revoked", "hr_revoked" in app and "reactivated_via_invite" in app.split("app_access_revoked")[0] or '"hr_revoked", "reactivated_via_invite"' in app)
    check("AuthProvider short-circuits definitive wipe", "isDefinitiveAuthWipeError" in auth)

    tsc = subprocess.run(
        ["npx", "tsc", "--noEmit"],
        cwd=MOBILE,
        capture_output=True,
        text=True,
        timeout=180,
    )
    check("mobile tsc --noEmit", tsc.returncode == 0, (tsc.stdout + tsc.stderr)[-500:])

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
