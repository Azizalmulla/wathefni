#!/usr/bin/env python3
"""Employee App colour-system gate.

Proves the three colour roles stay separable and legible:

  ground   cream + ink, the dominant surface of every screen
  ambient  brand pastels carrying module identity
  semantic status and interaction colour

The palette that shipped before this phase failed on exactly this: `pastelSage`
and `successSoft` measured dE 1.7 apart, so a decorative card and an "approved"
status were the same colour. Everything below is checked against the tokens as
they are actually written in src/theme.ts, not against a copy of them.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "src" / "theme.ts"

# WCAG 2.1
AA_TEXT = 4.5
AA_LARGE = 3.0
# dE76 rule of thumb: <3 indistinguishable, 3-6 barely, >10 clearly different.
ROLE_SEPARATION = 10.0
AMBIENT_SEPARATION = 8.0

failures: list[str] = []
checks = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    suffix = f" ({detail})" if detail else ""
    if ok:
        print(f"PASS  {label}{suffix}")
    else:
        print(f"FAIL  {label}{suffix}")
        failures.append(label)


def parse_tokens() -> dict[str, str]:
    source = THEME.read_text(encoding="utf-8")
    block = re.search(r"export const colors = \{(.*?)\n\}", source, re.S)
    if not block:
        raise SystemExit("could not find `export const colors` in src/theme.ts")
    return {m.group(1): m.group(2) for m in re.finditer(r"(\w+):\s*'(#[0-9A-Fa-f]{6})'", block.group(1))}


def rgb(hex_value: str) -> tuple[float, float, float]:
    h = hex_value.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def luminance(hex_value: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb(hex_value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def lab(hex_value: str) -> tuple[float, float, float]:
    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb(hex_value))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: str, b: str) -> float:
    la, aa, ba = lab(a)
    lb, ab, bb = lab(b)
    return ((la - lb) ** 2 + (aa - ab) ** 2 + (ba - bb) ** 2) ** 0.5


def main() -> None:
    colors = parse_tokens()

    GROUND = ["bg", "surface", "surfaceMuted", "border", "ink", "subtle", "primary", "primaryText"]
    AMBIENT = ["butter", "pink", "olive", "sky", "lilac"]
    SEMANTIC = ["success", "warning", "danger", "accent"]
    RETIRED = ["chip", "skeleton", "accentSoft", "successSoft", "warningSoft", "dangerSoft",
               "pastelButter", "pastelBlush", "pastelSage", "pastelSky", "pastelLilac"]

    check("every palette role is defined", all(k in colors for k in GROUND + AMBIENT + SEMANTIC),
          f"{len(colors)} tokens")
    check("redundant neutral and soft-status tokens are gone",
          not [k for k in RETIRED if k in colors],
          f"retired={[k for k in RETIRED if k in colors] or 'none'}")

    # --- Ground legibility -------------------------------------------------
    fills = {name: colors[name] for name in ["bg", "surface", "surfaceMuted"] + AMBIENT}
    for name, value in fills.items():
        ratio = contrast(colors["ink"], value)
        check(f"ink on {name} is AA for body text", ratio >= AA_TEXT, f"{ratio:.1f}:1")
    for name, value in fills.items():
        ratio = contrast(colors["subtle"], value)
        check(f"muted text on {name} is AA for body text", ratio >= AA_TEXT, f"{ratio:.1f}:1")

    # --- Semantic legibility ----------------------------------------------
    # Status is always drawn on `surface`, never on an ambient fill, so `surface`
    # is the only background a semantic colour has to survive.
    for name in SEMANTIC:
        ratio = contrast(colors[name], colors["surface"])
        check(f"{name} text on surface is AA", ratio >= AA_TEXT, f"{ratio:.1f}:1")
        check(f"{name} border on surface is AA for UI", ratio >= AA_LARGE, f"{ratio:.1f}:1")
    check("primary button label on ink is AA",
          contrast(colors["primaryText"], colors["primary"]) >= AA_TEXT,
          f"{contrast(colors['primaryText'], colors['primary']):.1f}:1")

    # --- Role separation ---------------------------------------------------
    worst = min(
        ((delta_e(colors[a], colors[s]), a, s) for a in AMBIENT for s in SEMANTIC),
        key=lambda item: item[0],
    )
    check("no ambient tone can be mistaken for a semantic colour",
          worst[0] >= ROLE_SEPARATION, f"closest {worst[1]}/{worst[2]} dE {worst[0]:.1f}")

    closest_ambient = min(
        ((delta_e(colors[a], colors[b]), a, b)
         for i, a in enumerate(AMBIENT) for b in AMBIENT[i + 1 :]),
        key=lambda item: item[0],
    )
    check("ambient tones are distinguishable from each other",
          closest_ambient[0] >= AMBIENT_SEPARATION,
          f"closest {closest_ambient[1]}/{closest_ambient[2]} dE {closest_ambient[0]:.1f}")

    closest_semantic = min(
        ((delta_e(colors[a], colors[b]), a, b)
         for i, a in enumerate(SEMANTIC) for b in SEMANTIC[i + 1 :]),
        key=lambda item: item[0],
    )
    check("semantic colours are distinguishable from each other",
          closest_semantic[0] >= ROLE_SEPARATION,
          f"closest {closest_semantic[1]}/{closest_semantic[2]} dE {closest_semantic[0]:.1f}")

    # --- Usage discipline --------------------------------------------------
    sources = list((ROOT / "src").rglob("*.tsx")) + list((ROOT / "app").rglob("*.tsx"))
    index_colour = [
        f"{p.relative_to(ROOT)}:{n}"
        for p in sources
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"(index|idx|i)\s*%\s*2\s*\?", line)
    ]
    check("no list-position-driven colour assignment", not index_colour, str(index_colour or "none"))

    raw_colour = [
        f"{p.relative_to(ROOT)}:{n}"
        for p in sources
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"(rgba?\(|#[0-9A-Fa-f]{6})", line) and "colors." not in line
    ]
    check("no untokenised colour literals in screens", not raw_colour, str(raw_colour or "none"))

    print("---")
    if failures:
        print(f"FAIL {len(failures)} of {checks} colour-system checks: {failures}")
        sys.exit(1)
    print(f"PASS employee app colour system ({checks} checks)")


if __name__ == "__main__":
    main()
