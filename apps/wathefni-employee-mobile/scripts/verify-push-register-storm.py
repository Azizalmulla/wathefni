#!/usr/bin/env python3
"""Regression gate: push registration must not storm /app/push/register."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUSH_LIFECYCLE = (ROOT / "src/push/PushLifecycle.tsx").read_text(encoding="utf-8")
AUTH_FAILURE = (ROOT / "src/auth/authFailure.ts").read_text(encoding="utf-8")


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    if not ok:
        raise SystemExit(1)


def main() -> None:
    check(
        "requestRef avoids unstable request dep",
        "requestRef" in PUSH_LIFECYCLE and "requestRef.current" in PUSH_LIFECYCLE,
    )
    check(
        "registration effect does not depend on request",
        "}, [registrationEnabled])" in PUSH_LIFECYCLE
        and "}, [registrationEnabled, request])" not in PUSH_LIFECYCLE,
    )
    check(
        "single-flight / lastHandledToken present",
        "inFlight" in PUSH_LIFECYCLE and "lastHandledToken" in PUSH_LIFECYCLE,
    )
    check(
        "token claimed before server POST",
        "lastHandledToken = tokenValue" in PUSH_LIFECYCLE
        and PUSH_LIFECYCLE.index("lastHandledToken = tokenValue")
        < PUSH_LIFECYCLE.index("'/app/push/register'"),
    )
    check(
        "listener uses knownToken without getExpoPushTokenAsync loop",
        "knownToken: next" in PUSH_LIFECYCLE,
    )
    check(
        "token listener never re-asks permission",
        "requestPermission: false" in PUSH_LIFECYCLE
        and "addPushTokenListener" in PUSH_LIFECYCLE,
    )
    check(
        "askedPermission gates OS prompt once",
        "askedPermission" in PUSH_LIFECYCLE,
    )
    check(
        "soft access codes do not blockApp on api phase",
        "blockApp: effectivePhase !== 'api'" in AUTH_FAILURE
        and "employee_app_not_enabled_for_company" in AUTH_FAILURE,
    )
    print("GREEN push-register-storm gate")


if __name__ == "__main__":
    main()
