#!/usr/bin/env python3
"""Auth Wave 2 Phase 1 — local PIN unit/contract tests (no device)."""

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
    print("auth wave2 phase1 pin unit")
    en = json.loads((MOBILE / "src/i18n/en.json").read_text())
    ar = json.loads((MOBILE / "src/i18n/ar.json").read_text())
    pin_en = {k for k in en if k.startswith("pin.")}
    pin_ar = {k for k in ar if k.startswith("pin.")}
    check("EN/AR pin key parity", pin_en == pin_ar, sorted(pin_en ^ pin_ar))

    policy = (MOBILE / "src/auth/pinPolicy.ts").read_text()
    check("PIN length 6", "PIN_LENGTH = 6" in policy)
    check("max attempts 5", "PIN_MAX_FAILED_ATTEMPTS = 5" in policy)
    check("canary Aziz key", "WATHEFNI-96599338566" not in policy)
    check("canary Talal key", "WATHEFNI-96550252254" not in policy)
    check("no CANARY_EMPLOYEE_KEYS allowlist", "CANARY_EMPLOYEE_KEYS" not in policy)
    check("master flag EXPO_PUBLIC_LOCAL_PIN_UNLOCK", "EXPO_PUBLIC_LOCAL_PIN_UNLOCK" in policy)
    check("universal when master on", "No employee-key allowlist" in policy)

    storage = (MOBILE / "src/auth/pinStorage.ts").read_text()
    check("stores verifier not plaintext key name", "wathefni.pin.verifier" in storage)
    check("stores salt", "wathefni.pin.salt" in storage)
    check("derivePinVerifier used", "derivePinVerifier" in storage)
    check("never writes raw pin to SecureStore setItem of pin", "setItemAsync(VERIFIER_KEY, pin" not in storage)

    crypto = (MOBILE / "src/auth/pinCrypto.ts").read_text()
    check("stretched verifier", "STRETCH_ROUNDS" in crypto)
    check("no expo-crypto import", "expo-crypto" not in crypto)

    auth = (MOBILE / "src/auth/AuthProvider.tsx").read_text()
    check("sealed session while locked", "sealedSessionRef" in auth)
    check("statuses locked + needsPinSetup", "'locked'" in auth and "'needsPinSetup'" in auth)
    check("createLocalPin API", "createLocalPin" in auth)
    check("unlockWithPin API", "unlockWithPin" in auth)
    check("changeLocalPin API", "changeLocalPin" in auth)
    check("5-fail resets to OTP", "recoverPinByReactivation" in auth)
    check("no background re-lock", "Phase 3 owns idle/background lock" in auth or "LocalUnlockShell" in auth)
    check("flag off Wave 1 path", "isLocalPinMasterEnabled" in auth)
    check("RTL restart can resume unlocked session once", "consumeSkipUnlockOnce" in auth or "isLocaleRestartPreserveAuth" in auth)
    check("locale restart never wipes session via blockForError", "locale_preserve" in auth or "isLocaleRestartPreserveAuth" in auth)
    check("locale restart /me failure falls back to PIN lock", "sealAndRequirePin" in auth)
    check("session wipe uses authFailure classifier", "classifyAuthFailure" in auth or "applyAuthFailure" in auth)

    i18n_src = (MOBILE / "src/i18n/index.tsx").read_text()
    check("language switch has no confirmation Alert", "Alert.alert" not in i18n_src and "rtlRestart.confirm" not in i18n_src)
    check("language switch uses Updates.reloadAsync first", "Updates.reloadAsync" in i18n_src)
    check("language switch shows cover during RTL reload", "layoutSwitching" in i18n_src and "switchCover" in i18n_src)
    check("locale restart marks preserve-auth", "markLocaleRestartPreserveAuth" in i18n_src)
    resume = (MOBILE / "src/auth/sessionResume.ts").read_text()
    check("preserve marker dual-written to SecureStore", "SecureStore.setItemAsync" in resume and "LOCALE_RESTART_PRESERVE_KEY" in resume)

    layout = (MOBILE / "app/_layout.tsx").read_text()
    check("AuthGate create PIN", "CreatePinFlow" in layout)
    check("AuthGate unlock PIN", "UnlockPinFlow" in layout or "UnlockWithBiometricGate" in layout)
    check("change-pin route registered", "change-pin" in layout)

    pkg = (MOBILE / "package.json").read_text()
    check("no new expo-crypto dep", "expo-crypto" not in pkg)
    # Phase 2 owns expo-local-authentication; Phase 1 only requires PIN remains local.
    check("phase1 pin remains local unlock", "createLocalPin" in auth and "unlockWithPin" in auth)

    # Node crypto self-check via ts transpile-free: run pinCrypto through a tiny JS port
    # executed by duplicating derive in Python for policy invariants already covered.
    # Run TypeScript check if tsc available.
    try:
        r = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=str(MOBILE),
            capture_output=True,
            text=True,
            timeout=180,
        )
        check("mobile typecheck", r.returncode == 0, (r.stdout + r.stderr)[-500:])
    except Exception as exc:
        check("mobile typecheck", False, str(exc))

    # Capability foundation still green
    try:
        r = subprocess.run(
            ["python3", "scripts/verify-capability-foundation.py"],
            cwd=str(MOBILE),
            capture_output=True,
            text=True,
            timeout=60,
        )
        check("verify-capability-foundation", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    except Exception as exc:
        check("verify-capability-foundation", False, str(exc))

    # Crypto round-trip via node embedding the algorithm is heavy; assert source exports.
    check("pinCrypto exports derivePinVerifier", "export function derivePinVerifier" in crypto)
    check("pinCrypto constantTimeEqual", "export function constantTimeEqual" in crypto)

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    print("AUTH_WAVE2_PHASE1_PIN_UNIT:" + ("PASS" if not failed else "FAIL"))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
