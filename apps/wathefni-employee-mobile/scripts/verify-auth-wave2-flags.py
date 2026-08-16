#!/usr/bin/env python3
"""Verify Auth Wave 2 master flags cannot silently drop from canary OTAs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "EXPO_PUBLIC_LOCAL_PIN_UNLOCK": "1",
    "EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK": "1",
    "EXPO_PUBLIC_LOCAL_AUTO_LOCK": "1",
    "EXPO_PUBLIC_LOCAL_AUTO_LOCK_BIOMETRIC": "1",
}


def check(label: str, ok: bool, detail: object = None) -> None:
    print(("PASS  " if ok else "FAIL  ") + label + (f" :: {detail}" if detail is not None and not ok else ""))
    if not ok:
        raise SystemExit(1)


def preflight() -> None:
    cfg = (ROOT / "app.config.js").read_text()
    for key in REQUIRED:
        check(f"app.config.js defaults {key}", key in cfg)
    check("app.config.js forces defaults when unset", "AUTH_WAVE2_DEFAULTS" in cfg)
    check("app.config.js asserts flags", "assertAuthWave2Flags" in cfg)

    env_example = ROOT / ".env.example"
    check(".env.example exists", env_example.is_file())
    example_text = env_example.read_text()
    for key, value in REQUIRED.items():
        check(f".env.example has {key}={value}", f"{key}={value}" in example_text)

    env_path = ROOT / ".env"
    if env_path.is_file():
        env_text = env_path.read_text()
        for key, value in REQUIRED.items():
            check(f".env has {key}={value}", f"{key}={value}" in env_text)
    else:
        print("WARN  .env absent locally (gitignored) — app.config.js defaults still apply")

    eas = json.loads((ROOT / "eas.json").read_text())
    prod_env = eas["build"]["production"]["env"]
    for key, value in REQUIRED.items():
        check(f"eas.json production.env {key}", prod_env.get(key) == value)

    publish = ROOT / "scripts" / "publish-canary-ota.sh"
    check("publish-canary-ota.sh exists", publish.is_file())
    pub = publish.read_text()
    check("publish script uses --environment production", "--environment production" in pub)
    check("publish script exports PIN flag", "EXPO_PUBLIC_LOCAL_PIN_UNLOCK" in pub)

    pin = (ROOT / "src/auth/pinPolicy.ts").read_text()
    bio = (ROOT / "src/auth/biometricPolicy.ts").read_text()
    auto = (ROOT / "src/auth/autoLockPolicy.ts").read_text()
    for path, text in (("pinPolicy", pin), ("biometricPolicy", bio), ("autoLockPolicy", auto)):
        check(
            f"{path} has no employee-key allowlist",
            "WATHEFNI-96599338566" not in text
            and "WATHEFNI-96550252254" not in text
            and "CANARY_EMPLOYEE_KEYS" not in text,
        )
    check("PIN enabled for any session key when master on", "No employee-key allowlist" in pin)


def verify_dist() -> None:
    ios = ROOT / "dist" / "_expo" / "static" / "js" / "ios"
    hbcs = list(ios.glob("*.hbc")) if ios.is_dir() else []
    check("dist iOS bundle exists", bool(hbcs), ios)
    blob = b"".join(p.read_bytes() for p in hbcs)
    # Hermes may keep both ternary string literals in the table; requiring :on is the proof.
    check("bundle contains pin-unlock-effective:on", b"pin-unlock-effective:on" in blob)
    check("bundle contains bio-unlock-effective:on", b"bio-unlock-effective:on" in blob)
    check("bundle contains al-lock-effective:on", b"al-lock-effective:on" in blob)
    # Hermes may retain both ternary literals; requiring :on is the bake proof.
    check("pin effective-on present (Auth Wave 2 live)", b"pin-unlock-effective:on" in blob)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--dist", action="store_true")
    args = parser.parse_args()
    if not args.preflight and not args.dist:
        args.preflight = True
    if args.preflight:
        preflight()
        print("auth-wave2 flags preflight: GREEN")
    if args.dist:
        verify_dist()
        print("auth-wave2 flags dist: GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
