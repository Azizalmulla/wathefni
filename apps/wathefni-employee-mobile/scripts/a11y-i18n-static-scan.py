#!/usr/bin/env python3
"""Static accessibility + EN/AR/RTL completion scan for Employee App Phase 4.

Claims code-level wiring only — not physical VoiceOver / Dynamic Type judgment.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
APP = ROOT / "app"


def main() -> int:
    failures: list[str] = []
    passed = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal passed
        if ok:
            passed += 1
            print(f"PASS  {name}")
        else:
            failures.append(name)
            print(f"FAIL  {name}{(' — ' + detail) if detail else ''}")

    en = json.loads((SRC / "i18n" / "en.json").read_text(encoding="utf-8"))
    ar = json.loads((SRC / "i18n" / "ar.json").read_text(encoding="utf-8"))
    check("EN/AR key parity", set(en) == set(ar), f"en-only={sorted(set(en)-set(ar))[:5]} ar-only={sorted(set(ar)-set(en))[:5]}")

    surfaces = [
        "home.",
        "schedule.",
        "leave.",
        "documents.",
        "payslips.",
        "profile.",
        "notifications.",
        "settings.",
        "onboarding.",
        "bank.",
        "feature.unavailable",
        "pin.",
        "biometric.",
    ]
    for prefix in surfaces:
        keys = [k for k in en if k.startswith(prefix)]
        check(f"surface keys present: {prefix.rstrip('.')}", len(keys) > 0, f"count={len(keys)}")

    motion = (SRC / "motion.ts").read_text(encoding="utf-8")
    check("reduced-motion handling exists", "isReduceMotionEnabled" in motion and "reduceMotionChanged" in motion)

    # Scan TSX for common a11y gaps on interactive controls we own.
    touch_ok = True
    label_hits = 0
    min44_hits = 0
    for path in list(SRC.rglob("*.tsx")) + list(APP.rglob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        label_hits += text.count("accessibilityLabel")
        # `layout.touchTarget` is the 44pt token; screens migrated to it still
        # declare a compliant target, so both spellings count.
        min44_hits += len(re.findall(r"(?:minHeight|width|height):\s*(?:44\b|layout\.touchTarget)", text))
        # Pressable without role is a soft signal only when clearly interactive primary buttons.
    check("accessibilityLabel used across app surfaces", label_hits >= 40, f"count={label_hits}")
    check("44pt touch targets declared in styles", min44_hits >= 12, f"count={min44_hits}")

    touch_target = re.compile(r"minHeight:\s*(?:44\b|layout\.touchTarget)")
    states = (SRC / "components" / "States.tsx").read_text(encoding="utf-8")
    access = (SRC / "components" / "AccessStates.tsx").read_text(encoding="utf-8")
    check("ErrorState retry is labeled and 44pt+", "accessibilityLabel" in states and bool(touch_target.search(states)))
    check("FeatureUnavailable secondary action is Pressable 44pt+", "secondaryPress" in access and bool(touch_target.search(access)))
    check("Editorial headings default to header role", "accessibilityRole = 'header'" in (SRC / "components" / "premium.tsx").read_text(encoding="utf-8"))

    # HR free text must not be auto-translated client-side for notification bodies.
    remaining = (SRC / "features" / "remaining" / "RemainingViews.tsx").read_text(encoding="utf-8")
    check(
        "Inbox preserves server title/body (no client fake-translate of HR text)",
        "item.title" in remaining and "item.body" in remaining and "t(item.title)" not in remaining,
    )

    print("---")
    if failures:
        print(f"FAIL count={len(failures)}: {', '.join(failures)}")
        return 1
    print(f"PASS a11y+i18n static scan ({passed} checks) — not a physical QA pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
