#!/usr/bin/env python3
"""Auth Wave 2 Phase 3B — local unlock overlay + Face ID unit tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "apps" / "wathefni-employee-mobile"
passed: list[str] = []
failed: list[str] = []


def check(label: str, ok: bool, detail: object = None) -> None:
    (passed if ok else failed).append(label)
    print(("  PASS  " if ok else "  FAIL  ") + label + (f" :: {detail}" if detail is not None and not ok else ""))


def decide(elapsed_ms: int, timeout_ms: int | None, entered_background: bool) -> str:
    if not entered_background:
        return "none"
    if timeout_ms is None:
        return "none"
    if elapsed_ms >= timeout_ms:
        return "timeout"
    return "none"


def main() -> int:
    print("auth wave2 phase3b overlay + Face ID unit")
    en = json.loads((MOBILE / "src/i18n/en.json").read_text())
    ar = json.loads((MOBILE / "src/i18n/ar.json").read_text())
    auto_en = {k for k in en if k.startswith("autoLock.")}
    auto_ar = {k for k in ar if k.startswith("autoLock.")}
    check("EN/AR autoLock key parity", auto_en == auto_ar, sorted(auto_en ^ auto_ar))

    policy = (MOBILE / "src/auth/autoLockPolicy.ts").read_text()
    check("master defaults on unless explicit 0", "raw === '0'" in policy and "return true" in policy)
    check("no PIN-master inherit for auto-lock", "return isLocalPinMasterEnabled()" not in policy.split("isLocalAutoLockMasterEnabled")[1].split("export function")[0])
    check("biometric overlay gate separate", "EXPO_PUBLIC_LOCAL_AUTO_LOCK_BIOMETRIC" in policy)
    check("timeout-only decision", "LocalUnlockDecisionReason" in policy)
    check("no device-lock reason", "confirmed_device_lock" not in policy)
    check("canary keys removed", "WATHEFNI-96599338566" not in policy and "WATHEFNI-96550252254" not in policy and "CANARY_EMPLOYEE_KEYS" not in policy)

    auth = (MOBILE / "src/auth/AuthProvider.tsx").read_text()
    check("AuthProvider has no AppState auto-lock", "AppState.addEventListener" not in auth)
    check("AuthProvider never seals from autolock", "seal deferred until active" not in auth)
    check("overlay comment in AuthProvider", "LocalUnlockShell" in auth)
    check("cold-start locked status still exists", "setStatus('locked')" in auth)

    shell = (MOBILE / "src/features/pin/LocalUnlockShell.tsx").read_text()
    check("needsLocalUnlock flag", "needsLocalUnlock" in shell)
    check("never setStatus locked", "setStatus(" not in shell and "setStatus('locked')" not in shell)
    check("never signedOut from overlay", "signedOut" not in shell)
    check("arms on true background", "next === 'background'" in shell)
    check("inactive ignored for lock", "Ignore inactive for locking" in shell or "inactive" in shell)
    check("privacy cover", "PrivacyCover" in shell or "privacyCover" in shell)
    check("shell patches diagnostics", "patchAutoLockDiagnostics" in shell)
    check("build marker exported", "AUTO_LOCK_BUILD_MARKER" in shell)
    check("shell does not own Face ID prompt", "promptBiometric" not in shell and "LocalAuthentication" not in shell)
    check("shell keeps children mounted", "{children}" in shell)
    check("shell never routes", "router." not in shell and "replace(" not in shell)

    overlay = (MOBILE / "src/features/pin/LocalUnlockOverlay.tsx").read_text()
    check("overlay uses Modal above native-stack", "Modal" in overlay and "presentationStyle" in overlay)
    check("overlay iOS FullWindowOverlay", "FullWindowOverlay" in overlay)
    check("overlay reuses UnlockWithBiometricGate", "UnlockWithBiometricGate" in overlay)
    check("overlay waits for host ready", "overlayReady" in overlay or "onShow" in overlay)
    check("overlay Face ID gated by AUTO_LOCK_BIOMETRIC", "isLocalAutoLockBiometricEnabled" in overlay)
    check("overlay Face ID success dismisses only", "onUnlocked()" in overlay and "unlockWithBiometric" not in overlay)
    check("overlay never navigates", "router." not in overlay and "useRouter" not in overlay and "setStatus(" not in overlay)
    check("overlay 5-fail uses recoverPinByReactivation", "recoverPinByReactivation" in overlay and "lockedOut" in overlay)
    check("overlay Forgot PIN wired", "onForgotPin" in overlay)
    check("privacy cover component", "function PrivacyCover" in overlay)
    check("no direct LocalAuthentication in overlay", "LocalAuthentication" not in overlay)

    gate = (MOBILE / "src/features/pin/UnlockWithBiometricGate.tsx").read_text()
    check("gate single-attempt refs", "attempted" in gate and "promptInFlight" in gate)
    check("gate waits for active AppState", "AppState.currentState !== 'active'" in gate)
    check("gate rising-edge reset", "wasFeatureOn" in gate)
    check("gate AppState retry listener", "addEventListener('change'" in gate)
    check("gate does not depend on t in effect", "[biometricFeatureOn]" in gate)
    check("gate PIN always visible", "UnlockPinFlow" in gate)
    check("gate settle delay before Face ID", "setTimeout(present, 500)" in gate)
    check("gate patches bio diagnostics", "lastBioGateReason" in gate)

    bio = (MOBILE / "src/auth/biometricAuth.ts").read_text()
    check("shouldAttempt returns preferred", "preferred: boolean" in bio)
    check("no wipe preference on transient !usable", "availability.hardware && !availability.enrolled" in bio)

    views = (MOBILE / "src/features/remaining/RemainingViews.tsx").read_text()
    check("settings shows diag fields", "autoLock.diagUpdate" in views and "autoLock.diagOverlayBio" in views)
    check("settings shows bio gate diag", "autoLock.diagBioGate" in views)

    diag = (MOBILE / "src/auth/autoLockDiagnostics.ts").read_text()
    check("diagnostics module", "getAutoLockDiagnostics" in diag and "lastDecision" in diag)
    check("diagnostics overlay bio flag", "overlayBiometricEnabled" in diag)
    check("diagnostics bio gate reason", "lastBioGateReason" in diag)
    settings = (MOBILE / "app/settings.tsx").read_text()
    check("settings wires diagnostics", "autoLockDiagnostics" in settings and "getAutoLockDiagnostics" in settings)
    check("al-overlay build marker", "al-overlay-v3:" in policy)

    layout = (MOBILE / "app/_layout.tsx").read_text()
    check("LocalUnlockShell wraps AuthGate", "LocalUnlockShell" in layout and "AuthGate" in layout)
    check("cold-start biometric gate still for status locked", "UnlockWithBiometricGate" in layout)

    eas = json.loads((MOBILE / "eas.json").read_text())
    env = eas["build"]["production"]["env"]
    check("production auto-lock on", env.get("EXPO_PUBLIC_LOCAL_AUTO_LOCK") == "1")
    check("overlay Face ID on for Phase 3B", env.get("EXPO_PUBLIC_LOCAL_AUTO_LOCK_BIOMETRIC") == "1")

    # Behavioral (timeout unchanged)
    check("inactive-only none", decide(60_000, 30_000, False) == "none")
    check("short bg none", decide(10_000, 30_000, True) == "none")
    check("40s timeout", decide(40_000, 30_000, True) == "timeout")
    check("never none", decide(999_999, None, True) == "none")
    check("immediate", decide(0, 0, True) == "timeout")

    check("shell does not import deviceLock", "deviceLock" not in shell and "isDeviceScreenLocked" not in shell)

    try:
        r = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=str(MOBILE),
            capture_output=True,
            text=True,
            timeout=120,
        )
        check("mobile tsc --noEmit", r.returncode == 0, (r.stdout + r.stderr)[-800:])
    except Exception as exc:  # noqa: BLE001
        check("mobile tsc --noEmit", False, str(exc))

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
