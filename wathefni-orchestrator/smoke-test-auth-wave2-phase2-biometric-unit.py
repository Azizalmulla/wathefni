#!/usr/bin/env python3
"""Auth Wave 2 Phase 2 — biometric unlock unit/contract tests (no device)."""

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


def main() -> int:
    print("auth wave2 phase2 biometric unit")
    en = json.loads((MOBILE / "src/i18n/en.json").read_text())
    ar = json.loads((MOBILE / "src/i18n/ar.json").read_text())
    bio_en = {k for k in en if k.startswith("biometric.")}
    bio_ar = {k for k in ar if k.startswith("biometric.")}
    check("EN/AR biometric key parity", bio_en == bio_ar, sorted(bio_en ^ bio_ar))
    required = {
        "biometric.optInTitle",
        "biometric.optInTitleFace",
        "biometric.optInTitleFingerprint",
        "biometric.optInSubtitle",
        "biometric.enable",
        "biometric.enableFace",
        "biometric.enableFingerprint",
        "biometric.notNow",
        "biometric.settings",
        "biometric.unlockPrompt",
        "biometric.unavailable",
    }
    check("required biometric EN keys", required <= bio_en, sorted(required - bio_en))

    policy = (MOBILE / "src/auth/biometricPolicy.ts").read_text()
    check("master flag EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK", "EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK" in policy)
    check("requires PIN master", "isLocalPinMasterEnabled" in policy)
    check("no employee-key allowlist", "WATHEFNI-96599338566" not in policy and "CANARY_EMPLOYEE_KEYS" not in policy)

    storage = (MOBILE / "src/auth/biometricStorage.ts").read_text()
    check("preference SecureStore key", "wathefni.biometric.enabled" in storage)
    check("stores enrolled level", "wathefni.biometric.enrolled_level" in storage)
    check("WHEN_UNLOCKED", "WHEN_UNLOCKED" in storage)

    auth_bio = (MOBILE / "src/auth/biometricAuth.ts").read_text()
    check("uses expo-local-authentication", "expo-local-authentication" in auth_bio)
    check("disableDeviceFallback to keep PIN canonical", "disableDeviceFallback: true" in auth_bio)
    check("clears preference when enrollment drops", "disableBiometricPreference" in auth_bio or "clearBiometricPreference" in auth_bio)
    check("hardware+enrolled usable gate", "hardware && enrolled" in auth_bio)
    check("authenticate supports strong", "biometricsSecurityLevel: 'strong'" in auth_bio)

    auth = (MOBILE / "src/auth/AuthProvider.tsx").read_text()
    check("needsBiometricOptIn status", "needsBiometricOptIn" in auth)
    check("unlockWithBiometric API", "unlockWithBiometric" in auth)
    check("finishBiometricOptIn API", "finishBiometricOptIn" in auth)
    check("opt-in resume never forces OTP on missing me", "resumeAfterBiometricOptIn" in auth)
    check("opt-in does not signedOut on !me", "if (!me) {\n        setStatus('signedOut')" not in auth)
    check("setBiometricUnlockEnabled API", "setBiometricUnlockEnabled" in auth)
    check("clears biometric on logout/OTP wipe", "clearBiometricPreference" in auth)
    # Phase 3 shipped the overlay controller in LocalUnlockShell. The invariant here is
    # that AuthProvider itself still owns no AppState-driven lock.
    check(
        "no idle/background re-lock inside AuthProvider (Phase 3 owns it)",
        "Phase 3 AppState auto-lock removed from AuthProvider" in auth
        and "AppState.addEventListener" not in auth,
    )
    check("biometric never hits backend routes", "/app/auth/biometric" not in auth)
    check("PIN still unlock path", "unlockWithPin" in auth)

    layout = (MOBILE / "app/_layout.tsx").read_text()
    check("AuthGate biometric opt-in", "BiometricOptInView" in layout)
    check("AuthGate biometric unlock gate", "UnlockWithBiometricGate" in layout)
    check("PIN fallback still present", "UnlockWithBiometricGate" in layout and "unlockWithPin" in layout)

    app_json = json.loads((MOBILE / "app.json").read_text())
    expo = app_json["expo"]
    check("NSFaceIDUsageDescription", "NSFaceIDUsageDescription" in expo["ios"]["infoPlist"])
    plugins = expo.get("plugins") or []
    plugin_names = []
    for p in plugins:
        if isinstance(p, str):
            plugin_names.append(p)
        elif isinstance(p, list) and p:
            plugin_names.append(p[0])
    check("expo-local-authentication plugin", "expo-local-authentication" in plugin_names)
    perms = set(expo["android"].get("permissions") or [])
    check("Android USE_BIOMETRIC", "android.permission.USE_BIOMETRIC" in perms)
    check("Android USE_FINGERPRINT", "android.permission.USE_FINGERPRINT" in perms)

    eas = json.loads((MOBILE / "eas.json").read_text())
    prod_env = eas["build"]["production"]["env"]
    check("production PIN flag", prod_env.get("EXPO_PUBLIC_LOCAL_PIN_UNLOCK") == "1")
    check("production biometric flag", prod_env.get("EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK") == "1")

    pkg = json.loads((MOBILE / "package.json").read_text())
    check("expo-local-authentication dependency", "expo-local-authentication" in pkg.get("dependencies", {}))

    settings = (MOBILE / "app/settings.tsx").read_text()
    check("settings biometric toggle", "setBiometricUnlockEnabled" in settings and "canManageBiometric" in settings)

    # Frozen Wave 1 contract files untouched by this phase's biometric modules.
    frozen = (ROOT / "ops" / "AUTH_WAVE1_FROZEN_CONTRACT.md").read_text()
    check("Wave 1 frozen contract still present", "session_epoch" in frozen and "SecureStore" in frozen)

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
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
