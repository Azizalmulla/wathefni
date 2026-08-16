#!/usr/bin/env python3
"""Auth Wave 2 Phase 4 — simple PIN recovery (Forgot PIN + 5-fail same path)."""

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
    print("auth wave2 phase4 pin recovery unit")
    en = json.loads((MOBILE / "src/i18n/en.json").read_text())
    ar = json.loads((MOBILE / "src/i18n/ar.json").read_text())
    keys = {
        "pin.forgot",
        "pin.forgotTitle",
        "pin.forgotConfirm",
        "pin.forgotConfirmAction",
    }
    check("EN forgot keys present", keys <= set(en))
    check("AR forgot keys present", keys <= set(ar))
    check("EN/AR pin key parity", {k for k in en if k.startswith("pin.")} == {k for k in ar if k.startswith("pin.")})
    check(
        "EN confirm copy exact",
        en.get("pin.forgotConfirm") == "You'll need to activate the app again and create a new PIN.",
    )

    auth = (MOBILE / "src/auth/AuthProvider.tsx").read_text()
    check("recoverPinByReactivation exported", "recoverPinByReactivation" in auth)
    check("recover clears PIN material", "clearPinMaterial()" in auth.split("recoverPinByReactivation")[1].split("createLocalPin")[0] or "clearLocalAuthMaterial" in auth.split("recoverPinByReactivation")[1].split("createLocalPin")[0])
    check("recover clears via clearLocalAuthMaterial", "clearLocalAuthMaterial" in auth.split("const recoverPinByReactivation")[1].split("const createLocalPin")[0])
    check("recover sets signedOut", "setStatus('signedOut')" in auth.split("const recoverPinByReactivation")[1].split("const createLocalPin")[0])
    check("recover in-flight guard", "recoverInFlightRef" in auth)
    unlock_fn = auth.split("const unlockWithPin = useCallback")[1].split("const unlockWithBiometric")[0]
    check("5-fail unlock uses recover", "recoverPinByReactivation" in unlock_fn and "result.lockedOut" in unlock_fn)
    change_fn = auth.split("const changeLocalPin = useCallback")[1].split("const signOut")[0]
    check("5-fail changePin uses recover", "recoverPinByReactivation" in change_fn)
    check("no new backend auth routes", "/app/auth/recover" not in auth and "/app/auth/forgot" not in auth)
    check("network soft-fail does not recover", "lockedOut: false, failedAttempts: 0" in auth)

    policy = (MOBILE / "src/auth/pinPolicy.ts").read_text()
    check("max attempts still 5", "PIN_MAX_FAILED_ATTEMPTS = 5" in policy)

    clear_body = auth.split("const clearLocalAuthMaterial")[1].split("const refreshBiometricState")[0]
    check("clear disables biometric preference", "clearBiometricPreference" in clear_body)
    check("clear clears session", "clearSession()" in clear_body)

    flows = (MOBILE / "src/features/pin/PinFlows.tsx").read_text()
    check("Forgot PIN confirmation Alert", "pin.forgotConfirm" in flows and "Alert.alert" in flows)
    check("UnlockPinFlow accepts onForgotPin", "onForgotPin" in flows)

    view = (MOBILE / "src/features/pin/PinView.tsx").read_text()
    check("PinView shows Forgot on unlock", "pin.forgot" in view and "mode === 'unlock'" in view)

    gate = (MOBILE / "src/features/pin/UnlockWithBiometricGate.tsx").read_text()
    check("gate forwards onForgotPin", "onForgotPin" in gate)

    layout = (MOBILE / "app/_layout.tsx").read_text()
    check("AuthGate wires Forgot PIN", "recoverPinByReactivation" in layout and "onForgotPin" in layout)

    overlay = (MOBILE / "src/features/pin/LocalUnlockOverlay.tsx").read_text()
    check("overlay Forgot + 5-fail recover", "recoverPinByReactivation" in overlay)
    check("overlay lockedOut recovers", "result.lockedOut" in overlay and "recoverPinByReactivation" in overlay)

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
