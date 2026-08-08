#!/usr/bin/env python3
"""RTL must be mirrored once, by the engine — never a second time by us.

Arabic reaches Yoga as `Direction::RTL` two ways: the root view sets
`direction: 'rtl'`, and `I18nManager.forceRTL` sets it natively. Yoga then mirrors
row layout on its own:

    react-native/ReactCommon/yoga/yoga/algorithm/FlexDirection.h
      resolveDirection(): under Direction::RTL, Row -> RowReverse
                                                RowReverse -> Row

so a hand-written `flexDirection: 'row-reverse'` for Arabic resolves back to `Row`
and puts an Arabic row into Latin order.

iOS mirrors text the same way:

    react-native/Libraries/Text/RCTTextAttributes.mm
      effectiveParagraphStyle(): when the layout direction is RTL,
                                 NSTextAlignmentRight <-> NSTextAlignmentLeft

so `textAlign: isRTL ? 'right' : 'left'` is swapped to left and pins Arabic against
the wrong edge.

Both were shipped in the canary bundle and fixed together. This gate keeps them
fixed. Direction-dependent *content* — which way a chevron points, which arrow glyph
to use — is not layout and is deliberately still allowed to branch on `isRTL`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"node_modules", ".expo", "dist", ".git", "scripts"}

FORBIDDEN = [
    (
        re.compile(r"row-reverse"),
        "manual `row-reverse`: Yoga already mirrors `row` under RTL, so this flips Arabic back to Latin order",
    ),
    (
        re.compile(r"textAlign:\s*isRTL\s*\?"),
        "manual RTL textAlign: iOS swaps left/right itself — use readingEdgeAlign()/trailingEdgeAlign()",
    ),
    (
        re.compile(r"I18nManager\.forceRTL\s*\(\s*false\s*\)"),
        "native RTL must not be disabled to hide a downstream layout bug",
    ),
]

# The helpers themselves hold the only literal alignments in the app.
ALLOWED_LITERAL_ALIGN = {Path("src/i18n/index.tsx")}


def sources() -> list[Path]:
    out = []
    for path in ROOT.rglob("*.ts*"):
        if any(part in SKIP for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix in {".ts", ".tsx"}:
            out.append(path)
    return sorted(out)


def main() -> int:
    failures: list[str] = []
    checks = 0

    files = sources()
    if not files:
        print("FAIL: no sources scanned")
        return 1

    for path in files:
        rel = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8")
        for pattern, why in FORBIDDEN:
            checks += 1
            for match in pattern.finditer(text):
                line = text[: match.start()].count("\n") + 1
                failures.append(f"{rel}:{line} — {why}")

    # The shared helpers must exist and must read the direction actually in force,
    # not the selected locale: those differ when an RTL reload did not happen.
    i18n = (ROOT / "src/i18n/index.tsx").read_text(encoding="utf-8")
    for helper in ("readingEdgeAlign", "trailingEdgeAlign"):
        checks += 1
        if f"export function {helper}" not in i18n:
            failures.append(f"src/i18n/index.tsx — missing shared helper {helper}()")
            continue
        body = i18n.split(f"export function {helper}", 1)[1][:220]
        checks += 1
        if "I18nManager.isRTL" not in body:
            failures.append(
                f"src/i18n/index.tsx — {helper}() must key off I18nManager.isRTL "
                "(the direction in force), not the locale"
            )

    # Icon/glyph direction is content, not layout, and must stay branchable.
    checks += 1
    icon_flips = sum(
        len(re.findall(r"isRTL \? '(?:chevron|arrow)", p.read_text(encoding="utf-8")))
        for p in files
    )
    if icon_flips == 0:
        failures.append(
            "no direction-aware chevrons/arrows found — icon direction is content "
            "and should still follow the locale"
        )

    if failures:
        print(f"FAIL RTL single-source ({len(failures)} problems)")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"PASS RTL mirrored once ({checks} checks, {len(files)} files, {icon_flips} icon flips kept)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
