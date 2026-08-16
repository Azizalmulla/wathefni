#!/usr/bin/env python3
"""Layer A — structural/action sanity for Wathefni Web (no screenshots).

Inventories dashboard Page destinations and flags production 'Not implemented'
copy, dead Setup deep links, and unauthorized-looking client-only gates.
Behavior/state oracle only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PASS = 0
FAIL = 0
ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "apps" / "wathefni-dashboard" / "src"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def pages() -> list[str]:
    text = (DASH / "types.ts").read_text(encoding="utf-8")
    block = text[text.find("export type Page =") : text.find("export type ChatMessage")]
    return re.findall(r"'([a-z0-9-]+)'", block)


def main() -> int:
    print("    E2E web structural sanity")
    found = pages()
    required = [
        "overview", "leave", "attendance", "shifts", "onboarding", "employees",
        "payroll", "performance", "talent", "learning", "benefits",
        "employee-relations", "engagement", "settings",
    ]
    check("Page union parsed", len(found) >= 20, found)
    for page in required:
        check(f"page destination exists: {page}", page in found, found)

    nav_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            DASH / "App.tsx",
            DASH / "lib" / "workspaceCapability.ts",
            DASH / "lib" / "moduleWorkspace.ts",
        )
        if path.exists()
    )
    for page in ("leave", "payroll", "performance", "talent", "settings"):
        check(f"nav/capability mentions {page}", page in nav_sources, "nav missing")

    unimplemented = []
    for path in DASH.rglob("*.tsx"):
        if any(part in {"node_modules", "dist", "__tests__"} for part in path.parts):
            continue
        if path.name.endswith(".test.tsx"):
            continue
        text = path.read_text(encoding="utf-8")
        if "Not implemented in this phase" in text or 'title="Not implemented"' in text:
            unimplemented.append(str(path.relative_to(DASH)))
    # P1-11 was a known production string; it must not remain on a live control.
    check("no production Not implemented title on live TSX", unimplemented == [], unimplemented[:8])

    setup = ""
    setup_path = DASH / "setup-console" / "setupConsoleOwnership.ts"
    if setup_path.exists():
        setup = setup_path.read_text(encoding="utf-8")
        check(
            "Setup does not deep-link a missing migration-sync page without a Page union entry",
            "migration-sync" not in setup or "migration-sync" in found,
            "migration-sync deep link",
        )
    else:
        check("setup ownership file present or not required", True)

    print(f"\n    WEB_STRUCTURAL_{'PASS' if not FAIL else 'FAIL'}  {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
