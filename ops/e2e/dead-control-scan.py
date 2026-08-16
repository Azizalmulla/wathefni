#!/usr/bin/env python3
"""Fail on production controls that look clickable but have no action."""
from __future__ import annotations

import re
import sys
from pathlib import Path

PASS = 0
FAIL = 0
ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "apps" / "wathefni-dashboard" / "src"
MOBILE = ROOT / "apps" / "wathefni-employee-mobile"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


BUTTON_RE = re.compile(r"<Button\b([^>]*)>", re.S)
PRESSABLE_RE = re.compile(r"<(?:Pressable|TouchableOpacity|TouchableHighlight)\b([^>]*)>", re.S)
DEAD_HINTS = (
    "TODO: wire",
    "Not implemented in this phase",
    'title="Not implemented"',
    "onPress={() => undefined}",
    "onClick={() => undefined}",
)


def actionable(attrs: str) -> bool:
    return bool(
        re.search(r"\bon(?:Click|Press|Submit)\s*=", attrs)
        or re.search(r"\b(?:href|to|onPressIn)\s*=", attrs)
        or "disabled" in attrs
        or "accessibilityRole" in attrs and "disabled" in attrs
    )


def scan_tsx(root: Path, skip_hr: bool = False) -> list[str]:
    dead: list[str] = []
    for path in root.rglob("*.tsx"):
        if any(part in {"node_modules", "dist", "__tests__", ".expo"} for part in path.parts):
            continue
        if path.name.endswith(".test.tsx"):
            continue
        if skip_hr and "/hr/" in str(path):
            continue
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(ROOT))
        for hint in DEAD_HINTS:
            if hint in text:
                dead.append(f"{rel}: {hint}")
        for match in BUTTON_RE.finditer(text):
            attrs = match.group(1)
            if "disabled" in attrs or 'type="submit"' in attrs or "pending" in attrs:
                continue
            start = match.start()
            window = text[max(0, start - 250) : start + 400]
            if "<form" in text[max(0, start - 500) : start] and "</form>" not in text[max(0, start - 500) : start]:
                continue
            if not actionable(attrs) and not re.search(r"\bon(?:Click|Press|Submit)\s*=", window) and "href=" not in window and " to=" not in window:
                dead.append(f"{rel}: unwired Button near {text[start:start+80]!r}")
    return dead


def main() -> int:
    print("    DEAD CONTROL SCAN")
    web_dead = scan_tsx(DASH)
    # Ignore story/demo folders if any remain.
    web_dead = [row for row in web_dead if "/demo/" not in row and "/__fixtures__/" not in row]
    check("HR Web has no Not implemented / empty-handler controls", web_dead == [], web_dead[:12])
    emp_dead = scan_tsx(MOBILE / "app", skip_hr=True)
    emp_src = scan_tsx(MOBILE / "src")
    check("Employee mobile has no empty-handler production controls", emp_dead + emp_src == [], (emp_dead + emp_src)[:12])
    hr_dead = scan_tsx(MOBILE / "app" / "hr")
    check("HR mobile has no empty-handler production controls", hr_dead == [], hr_dead[:12])
    print(f"\n    DEAD_CONTROL_{'PASS' if not FAIL else 'FAIL'}  {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
