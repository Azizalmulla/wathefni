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

import math
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

# --- Two-tone ambient rule ---------------------------------------------------
# Colour intensity is inversely proportional to the area it covers. A fill may
# tint a whole card, so it has to stay close to the page; an accent may only
# ever be a mark the size of an icon tile, so it has to be strong enough to see.
# Without the ceiling, the palette drifts back to mid-chroma everywhere, which
# is the exact failure the two-tone split was introduced to fix.
# Brand fills stay in the HR Workspace yellow / pink / green family, refined for
# phone: warmer butter yellow, adult rose, livelier pistachio. FILL_CEILING 2.0
# keeps neon out while admitting this richer Home pilot.
FILL_CEILING = 2.0  # max contrast a large fill may have against the page
MARK_VISIBILITY = 1.4  # min contrast an accent needs against fill and page
FILL_SEPARATION = 4.0  # distinct brand fills must stay distinguishable

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


def parse_ambient() -> dict[str, dict[str, str]]:
    """The two-tone `ambient` block: one fill and one accent per module."""
    source = THEME.read_text(encoding="utf-8")
    block = re.search(r"export const ambient = \{(.*?)\n\} as const", source, re.S)
    if not block:
        raise SystemExit("could not find `export const ambient` in src/theme.ts")
    return {
        name: {"fill": fill, "accent": accent}
        for name, fill, accent in re.findall(
            r"(\w+):\s*\{\s*fill:\s*'(#[0-9A-Fa-f]{6})',\s*accent:\s*'(#[0-9A-Fa-f]{6})'\s*\}",
            block.group(1),
        )
    }


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


def chroma(hex_value: str) -> float:
    """Distance from the neutral axis in Lab — how much colour a value carries."""
    _, a, b = lab(hex_value)
    return math.hypot(a, b)


def delta_e(a: str, b: str) -> float:
    la, aa, ba = lab(a)
    lb, ab, bb = lab(b)
    return ((la - lb) ** 2 + (aa - ab) ** 2 + (ba - bb) ** 2) ** 0.5


def main() -> None:
    colors = parse_tokens()

    GROUND = [
        "bg", "surface", "surfaceMuted", "border", "ink", "subtle",
        "navMuted", "primary", "primaryText",
    ]
    AMBIENT = ["butter", "pink", "olive", "sky", "lilac"]
    BRAND = ["butter", "pink", "olive"]
    SEMANTIC = ["success", "warning", "danger", "accent"]
    RETIRED = ["chip", "skeleton", "accentSoft", "successSoft", "warningSoft", "dangerSoft",
               "pastelButter", "pastelBlush", "pastelSage", "pastelSky", "pastelLilac"]

    check("every palette role is defined", all(k in colors for k in GROUND + AMBIENT + SEMANTIC),
          f"{len(colors)} tokens")
    check("redundant neutral and soft-status tokens are gone",
          not [k for k in RETIRED if k in colors],
          f"retired={[k for k in RETIRED if k in colors] or 'none'}")
    check("legacy sky/lilac aliases lock to the HR yellow and pink",
          colors["sky"] == colors["butter"] and colors["lilac"] == colors["pink"],
          f"sky={colors['sky']} lilac={colors['lilac']}")

    # --- Ground legibility -------------------------------------------------
    cream = {name: colors[name] for name in ["bg", "surface", "surfaceMuted"]}
    brand_fills = {name: colors[name] for name in BRAND}
    for name, value in {**cream, **brand_fills}.items():
        ratio = contrast(colors["ink"], value)
        check(f"ink on {name} is AA for body text", ratio >= AA_TEXT, f"{ratio:.1f}:1")
    # Muted text is for cream surfaces only. Brand fills match the HR dashboard
    # and are too strong for `subtle` — copy on those cards uses ink.
    for name, value in cream.items():
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
    check("inactive tab labels remain AA on the black navigation bar",
          contrast(colors["navMuted"], colors["ink"]) >= AA_TEXT,
          f"{contrast(colors['navMuted'], colors['ink']):.1f}:1")

    # --- Role separation ---------------------------------------------------
    worst = min(
        ((delta_e(colors[a], colors[s]), a, s) for a in BRAND for s in SEMANTIC),
        key=lambda item: item[0],
    )
    check("no ambient tone can be mistaken for a semantic colour",
          worst[0] >= ROLE_SEPARATION, f"closest {worst[1]}/{worst[2]} dE {worst[0]:.1f}")

    closest_ambient = min(
        ((delta_e(colors[a], colors[b]), a, b)
         for i, a in enumerate(BRAND) for b in BRAND[i + 1 :]),
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

    # --- Two-tone ambient: intensity belongs to the mark, not the surface ----
    modules = parse_ambient()

    for name, tone in modules.items():
        fill, accent = tone["fill"], tone["accent"]

        ratio = contrast(fill, colors["bg"])
        check(f"{name} fill stays close to the page", ratio <= FILL_CEILING, f"{ratio:.2f}:1")

        ratio = contrast(colors["ink"], fill)
        check(f"ink on {name} fill is AA for body text", ratio >= AA_TEXT, f"{ratio:.1f}:1")
        # Brand fills match the HR dashboard and are too strong for muted text.
        # Supporting copy on these surfaces uses ink (optionally at reduced
        # opacity), never `subtle`.

        ratio = contrast(colors["ink"], accent)
        check(f"an icon on the {name} accent is AA for UI", ratio >= AA_LARGE, f"{ratio:.1f}:1")

        on_fill = contrast(accent, fill)
        on_page = contrast(accent, colors["bg"])
        check(f"the {name} accent is visible on both its fill and the page",
              min(on_fill, on_page) >= MARK_VISIBILITY,
              f"fill {on_fill:.2f}:1, page {on_page:.2f}:1")

        check(f"the {name} accent carries more chroma than its fill",
              chroma(accent) > chroma(fill),
              f"accent {chroma(accent):.0f} vs fill {chroma(fill):.0f}")

    # Identity has to survive the desaturation. Fills are deliberately quiet, so
    # the accents are what an employee actually recognises a module by.
    names = list(modules)
    closest_accent = min(
        ((delta_e(modules[a]["accent"], modules[b]["accent"]), a, b)
         for i, a in enumerate(names) for b in names[i + 1 :]
         if modules[a]["accent"] != modules[b]["accent"]),
        key=lambda item: item[0],
        default=(999.0, "", ""),
    )
    check("module accents are distinguishable from each other",
          closest_accent[0] >= AMBIENT_SEPARATION,
          f"closest {closest_accent[1]}/{closest_accent[2]} dE {closest_accent[0]:.1f}")

    # Modules may share a brand fill (yellow for schedule + payslips). Separation
    # is measured across distinct fill hexes only — inventing a fourth pastel
    # just to pass this check would undo the HR colour lock.
    distinct_fills = sorted({tone["fill"] for tone in modules.values()})
    if len(distinct_fills) >= 2:
        closest_fill = min(
            ((delta_e(a, b), a, b)
             for i, a in enumerate(distinct_fills) for b in distinct_fills[i + 1 :]),
            key=lambda item: item[0],
        )
        check("module fills are not interchangeable",
              closest_fill[0] >= FILL_SEPARATION,
              f"closest {closest_fill[1]}/{closest_fill[2]} dE {closest_fill[0]:.1f}")
    else:
        check("module fills are not interchangeable", True, "single brand fill")

    # Home brand lock — same yellow / pink / green family as HR Workspace,
    # tuned for a premium employee phone surface (not a flat dashboard sample).
    brand = {
        "yellow": "#F0D065",
        "pink": "#E5A6CB",
        "green": "#B8CE7F",
    }
    used_fills = {tone["fill"].upper() for tone in modules.values()}
    check(
        "Home ambient fills are the refined yellow, pink and green",
        used_fills == {v.upper() for v in brand.values()},
        f"fills={sorted(used_fills)}",
    )
    check(
        "Documents launcher wears green, not pink",
        modules["documents"]["fill"].upper() == brand["green"].upper(),
        modules["documents"]["fill"],
    )
    check(
        "workday / schedule wears pink",
        modules["schedule"]["fill"].upper() == brand["pink"].upper(),
        modules["schedule"]["fill"],
    )
    check(
        "attention / onboarding work wears yellow",
        modules["onboarding"]["fill"].upper() == brand["yellow"].upper(),
        modules["onboarding"]["fill"],
    )
    home_src = (ROOT / "src" / "features" / "home" / "HomeView.tsx").read_text(encoding="utf-8")
    leave_pill = home_src.split("function RequestLeavePill", 1)[-1].split("function DestinationLink", 1)[0]
    check(
        "Request leave uses Home composition blue with ink (not white-on-blue)",
        "homeComposition.requestLeave.fill" in home_src
        and "color={colors.ink}" in leave_pill
        and "requestLeaveLabel: {\n    color: colors.ink," in home_src
        and "colors.primaryText" not in leave_pill,
    )
    # Home composition blue is deliberately outside ambient module identity.
    home_comp_block = re.search(
        r"export const homeComposition = \{(.*?)\n\} as const",
        THEME.read_text(encoding="utf-8"),
        re.S,
    )
    check("Home declares a composition-only Request Leave blue", bool(home_comp_block))
    if home_comp_block:
        leave_action = re.search(
            r"requestLeave:\s*\{\s*fill:\s*'(#[0-9A-Fa-f]{6})',\s*accent:\s*'(#[0-9A-Fa-f]{6})'",
            home_comp_block.group(1),
        )
        check(
            "Request Leave composition blue is soft and ink-legible",
            bool(leave_action)
            and leave_action.group(1).upper() == "#A9C0E4"
            and contrast(colors["ink"], leave_action.group(1)) >= AA_TEXT,
            leave_action.group(1) if leave_action else "missing",
        )
    check(
        "Home ambient fills do not use blue or lilac",
        all(
            not (int(f[5:7], 16) > int(f[1:3], 16) + 20 and int(f[5:7], 16) > int(f[3:5], 16))
            for f in used_fills
        ),
        f"fills={sorted(used_fills)}",
    )

    worst_ambient_semantic = min(
        ((delta_e(modules[m][tone], colors[s]), f"{m}.{tone}", s)
         for m in modules for tone in ("fill", "accent") for s in SEMANTIC),
        key=lambda item: item[0],
    )
    check("no two-tone ambient value can be mistaken for a semantic colour",
          worst_ambient_semantic[0] >= ROLE_SEPARATION,
          f"closest {worst_ambient_semantic[1]}/{worst_ambient_semantic[2]} "
          f"dE {worst_ambient_semantic[0]:.1f}")

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
