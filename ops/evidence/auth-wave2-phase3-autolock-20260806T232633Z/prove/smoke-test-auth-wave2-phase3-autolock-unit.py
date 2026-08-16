#!/usr/bin/env python3
"""Auth Wave 2 Phase 3 — smart auto-lock unit/contract tests (no device)."""

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


def should_auto_lock(elapsed_ms: int, timeout_ms: int | None, device_was_locked: bool) -> bool:
    """Mirror of autoLockPolicy.shouldAutoLockOnResume."""
    if device_was_locked:
        return True
    if timeout_ms is None:
        return False
    return elapsed_ms >= timeout_ms


def main() -> int:
    print("auth wave2 phase3 auto-lock unit")
    en = json.loads((MOBILE / "src/i18n/en.json").read_text())
    ar = json.loads((MOBILE / "src/i18n/ar.json").read_text())
    auto_en = {k for k in en if k.startswith("autoLock.")}
    auto_ar = {k for k in ar if k.startswith("autoLock.")}
    check("EN/AR autoLock key parity", auto_en == auto_ar, sorted(auto_en ^ auto_ar))
    required = {
        "autoLock.settings",
        "autoLock.settingsSubtitle",
        "autoLock.immediate",
        "autoLock.seconds30",
        "autoLock.minute1",
        "autoLock.minutes5",
        "autoLock.never",
    }
    check("required autoLock EN keys", required <= auto_en, sorted(required - auto_en))

    policy = (MOBILE / "src/auth/autoLockPolicy.ts").read_text()
    check("master flag EXPO_PUBLIC_LOCAL_AUTO_LOCK", "EXPO_PUBLIC_LOCAL_AUTO_LOCK" in policy)
    check("inherits PIN master when unset", "isLocalPinMasterEnabled" in policy)
    check("canary Aziz key", "WATHEFNI-96599338566" in policy)
    check("canary Talal key", "WATHEFNI-96550252254" in policy)
    check("default 30s", "AUTO_LOCK_DEFAULT_TIMEOUT_MS: AutoLockTimeoutMs = 30_000" in policy)
    check("never option supported", "null" in policy and "autoLock.never" in policy)
    check("company may disable never", "EXPO_PUBLIC_LOCAL_AUTO_LOCK_ALLOW_NEVER" in policy)
    check("device lock always locks", "if (opts.deviceWasLocked) return true" in policy)
    check("never skips time lock", "if (opts.timeoutMs == null) return false" in policy)

    storage = (MOBILE / "src/auth/autoLockStorage.ts").read_text()
    check("timeout SecureStore key", "wathefni.autolock.timeout_ms" in storage)
    check("WHEN_UNLOCKED", "WHEN_UNLOCKED" in storage)

    device = (MOBILE / "src/auth/deviceLock.ts").read_text()
    check("lazy screen detector require", "require('expo-screen-detector')" in device)
    check("falls back false without native", "return false" in device)

    auth = (MOBILE / "src/auth/AuthProvider.tsx").read_text()
    check("AppState auto-lock wiring", "shouldAutoLockOnResume" in auth)
    check("seals without clearing PIN", "Local seal only — never clear SecureStore session or PIN" in auth)
    check("setAutoLockTimeout API", "setAutoLockTimeout" in auth)
    check("autoLockEnabled context", "autoLockEnabled" in auth)
    check("no OTP on auto-lock path", "clearPinMaterial" not in auth.split("Local seal only")[1].split("Soft refresh while unlocked")[0])
    check("does not clearSession on auto-lock", "clearSession(" not in auth.split("Local seal only")[1].split("Soft refresh while unlocked")[0])
    check("biometric unlock still present", "unlockWithBiometric" in auth)
    check("PIN unlock still present", "unlockWithPin" in auth)

    settings = (MOBILE / "app/settings.tsx").read_text()
    check("settings auto-lock wiring", "setAutoLockTimeout" in settings and "canManageAutoLock" in settings)

    views = (MOBILE / "src/features/remaining/RemainingViews.tsx").read_text()
    check("settings UI timeout options", "listAutoLockTimeoutOptions" in views and "autoLock.settings" in views)

    eas = json.loads((MOBILE / "eas.json").read_text())
    prod_env = eas["build"]["production"]["env"]
    check("production PIN flag", prod_env.get("EXPO_PUBLIC_LOCAL_PIN_UNLOCK") == "1")
    check("production biometric flag", prod_env.get("EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK") == "1")
    check("production auto-lock flag", prod_env.get("EXPO_PUBLIC_LOCAL_AUTO_LOCK") == "1")

    pkg = json.loads((MOBILE / "package.json").read_text())
    check("expo-screen-detector dependency", "expo-screen-detector" in pkg.get("dependencies", {}))

    # Behavioral matrix (mirrors TS policy)
    check("bg <30s default → stay", not should_auto_lock(29_999, 30_000, False))
    check("bg >=30s default → lock", should_auto_lock(30_000, 30_000, False))
    check("immediate locks at 0ms", should_auto_lock(0, 0, False))
    check("1m threshold", not should_auto_lock(59_999, 60_000, False) and should_auto_lock(60_000, 60_000, False))
    check("5m threshold", not should_auto_lock(299_999, 300_000, False) and should_auto_lock(300_000, 300_000, False))
    check("never: long bg stays unlocked", not should_auto_lock(999_999, None, False))
    check("device lock overrides never", should_auto_lock(100, None, True))
    check("device lock overrides short bg", should_auto_lock(1_000, 30_000, True))

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
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
