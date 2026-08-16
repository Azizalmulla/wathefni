#!/usr/bin/env python3
"""Static gate: Employee App semantic native feedback layer (haptics only)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
APP = ROOT / "app"
failures: list[str] = []
passed = 0


def ok(msg: str) -> None:
    global passed
    passed += 1
    print(f"PASS  {msg}")


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"FAIL  {msg}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    haptics = ROOT / "src" / "native" / "haptics.ts"
    if not haptics.exists():
        fail("src/native/haptics.ts missing")
        return 1
    body = read(haptics)

    for kind in ("selection", "weekSnap", "tab", "lightImpact", "success", "warning", "error"):
        if f"'{kind}'" not in body and f'"{kind}"' not in body:
            fail(f"FeedbackKind missing {kind}")
        else:
            ok(f"kind {kind}")

    for fn in (
        "selectionFeedback",
        "weekSnapFeedback",
        "tabFeedback",
        "lightImpactFeedback",
        "successFeedback",
        "warningFeedback",
        "errorFeedback",
    ):
        if f"export function {fn}" not in body:
            fail(f"export missing {fn}")
        else:
            ok(f"export {fn}")

    if "MIN_INTERVAL_MS" not in body or "canFire" not in body:
        fail("throttle/dedupe missing")
    else:
        ok("per-kind throttle present")

    if "void work()" not in body and "void work().catch" not in body:
        fail("feedback must be fire-and-forget (void)")
    else:
        ok("fire-and-forget (non-blocking)")

    if "ImpactFeedbackStyle.Soft" not in body:
        fail("selection should use Soft impact (stronger than selectionAsync)")
    else:
        ok("selection uses Soft impact")

    if "ImpactFeedbackStyle.Medium" not in body:
        fail("week snap / warning should use Medium")
    else:
        ok("Medium impact present for snap/warning")

    # In-app must be haptics-only — no expo-av / UI tone playback.
    for banned in ("expo-av", "playSound", "SOUND_MODULES", "Audio.Sound", "require('../../assets/feedback"):
        if banned in body:
            fail(f"in-app UI audio remnant in haptics.ts: {banned}")
        else:
            ok(f"no {banned}")

    for name in ("snap.wav", "success.wav", "warning.wav", "error.wav"):
        path = ROOT / "assets" / "feedback" / name
        if path.exists():
            fail(f"unused in-app UI tone still present: {name}")
        else:
            ok(f"removed in-app UI tone {name}")

    # Push sound must remain intact (separate system).
    push_wav = ROOT / "assets" / "sounds" / "push" / "wathefni_default.wav"
    if not push_wav.exists():
        fail("push wathefni_default.wav missing")
    else:
        ok("push wathefni_default.wav preserved")

    pkg = read(ROOT / "package.json")
    if '"expo-av"' in pkg:
        fail("expo-av still in package.json (unused after UI sound removal)")
    else:
        ok("expo-av removed from package.json")

    app_json = read(ROOT / "app.json")
    if '"expo-av"' in app_json:
        fail("expo-av still listed in app.json plugins")
    else:
        ok("expo-av not in app.json plugins")
    if "wathefni_default.wav" not in app_json:
        fail("push sound must remain in expo-notifications.sounds")
    else:
        ok("push sound still in expo-notifications.sounds")

    offenders: list[str] = []
    for path in list(SRC.rglob("*.ts")) + list(SRC.rglob("*.tsx")) + list(APP.rglob("*.ts")) + list(APP.rglob("*.tsx")):
        if path.resolve() == haptics.resolve():
            continue
        text = read(path)
        if re.search(r"from ['\"]expo-haptics['\"]", text) or "Haptics." in text:
            offenders.append(str(path.relative_to(ROOT)))
        if re.search(r"from ['\"]expo-av['\"]", text) or "Audio.Sound" in text:
            offenders.append(str(path.relative_to(ROOT)))
    if offenders:
        fail(f"raw haptics/audio outside haptics.ts: {', '.join(offenders)}")
    else:
        ok("no raw expo-haptics/expo-av outside central layer")

    premium = read(ROOT / "src" / "components" / "premium.tsx")
    if "lightImpactFeedback" not in premium:
        fail("PremiumButton primary press should fire lightImpactFeedback")
    else:
        ok("PremiumButton primary CTA light impact on press")
    if "if (!secondary" not in premium:
        fail("CTA haptic must skip secondary buttons")
    else:
        ok("CTA haptic gated to primary")

    strip = read(ROOT / "src" / "features" / "schedule" / "ScheduleWeekStrip.tsx")
    if "selectionFeedback()" not in strip or "weekSnapFeedback()" not in strip:
        fail("ScheduleWeekStrip must split day selection vs week snap")
    else:
        ok("ScheduleWeekStrip day vs week snap split")

    tabs = read(ROOT / "app" / "(tabs)" / "_layout.tsx")
    if "tabFeedback" not in tabs or "tabPress" not in tabs:
        fail("tab selection feedback missing")
    else:
        ok("bottom tabs use tabFeedback")

    required_sites = {
        "app/onboarding.tsx": ("successFeedback", "errorFeedback", "warningFeedback"),
        "app/documents.tsx": ("successFeedback", "errorFeedback"),
        "app/bank.tsx": ("successFeedback", "errorFeedback", "warningFeedback"),
        "app/(tabs)/leave.tsx": ("successFeedback", "errorFeedback", "warningFeedback"),
        "app/leave/request.tsx": ("successFeedback", "errorFeedback"),
        "app/(tabs)/payslips.tsx": ("successFeedback", "errorFeedback"),
        "app/settings.tsx": ("selectionFeedback", "successFeedback", "warningFeedback", "errorFeedback"),
        "app/change-pin.tsx": ("successFeedback", "errorFeedback"),
    }
    for rel, needs in required_sites.items():
        text = read(ROOT / rel)
        missing = [n for n in needs if n not in text]
        if missing:
            fail(f"{rel} missing {', '.join(missing)}")
        else:
            ok(f"{rel} wired")

    if failures:
        print(f"FAIL semantic feedback: {len(failures)} — {', '.join(failures)}")
        return 1
    print(f"PASS semantic feedback ({passed} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
