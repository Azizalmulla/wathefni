#!/usr/bin/env python3
"""HR Web Surface Census — smoke contract (no screenshots, no live browser).

Fails when a new Page / App nav item / PostHire case / ?page= destination is
missing from hrWebSurfaceRegistry.ts and is not an intentional exclusion.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PASS = 0
FAIL = 0
ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "apps" / "wathefni-dashboard" / "src"
REGISTRY = DASH / "lib" / "hrWebSurfaceRegistry.ts"
APP = DASH / "App.tsx"
TYPES = DASH / "types.ts"
POSTHIRE = DASH / "posthire" / "PostHire.tsx"
CAPABILITY = DASH / "lib" / "workspaceCapability.ts"
CENSUS = DASH / "lib" / "hrWebSurfaceCensus.ts"
CONTRACT = DASH / "lib" / "hrWebSurfaceRegistry.contract.test.ts"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def page_union() -> list[str]:
    text = TYPES.read_text(encoding="utf-8")
    block = text[text.find("export type Page =") : text.find("export type ChatMessage")]
    return re.findall(r"'([a-z0-9-]+)'", block)


def nav_ids() -> list[str]:
    text = (DASH / "lib" / "hrWebNavCatalog.ts").read_text(encoding="utf-8")
    start = text.find("const PAGE_ICONS")
    end = text.find("export const DASHBOARD_NAV_CATALOG")
    return re.findall(r"^\s+'?([a-z0-9-]+)'?: ", text[start:end], flags=re.M)


def posthire_cases() -> list[str]:
    text = (DASH / "posthire" / "PostHireDispatcher.tsx").read_text(encoding="utf-8")
    start = text.find("switch (page)")
    return re.findall(r"case '([a-z0-9-]+)':", text[start : start + 8000])


def query_pages() -> set[str]:
    found: set[str] = set()
    for path in DASH.rglob("*.ts*"):
        if any(part in {"node_modules", "dist"} for part in path.parts):
            continue
        if path.name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
            continue
        text = path.read_text(encoding="utf-8")
        found.update(re.findall(r"[?&]page=([a-z0-9-]+)", text))
        found.update(re.findall(r"opsHref: '/dashboard\?page=([a-z0-9-]+)", text))
    return found


def main() -> int:
    print("    E2E HR Web surface census")
    check("surface registry exists", REGISTRY.is_file())
    check("static census helper exists", CENSUS.is_file())
    check("coverage contract test exists", CONTRACT.is_file())

    registry = REGISTRY.read_text(encoding="utf-8")
    exclusions_block = registry[registry.find("HR_WEB_SURFACE_EXCLUSIONS") :]
    pages = page_union()
    check("Page union parsed", len(pages) >= 20, pages)

    for page in pages:
        check(
            f"registry covers page.{page}",
            f"page.{page}" in registry or f"page: '{page}'" in registry,
            page,
        )

    for nav in nav_ids():
        check(
            f"registry covers nav {nav}",
            f"page.{nav}" in registry or f"page: '{nav}'" in registry,
            nav,
        )

    for case in posthire_cases():
        check(
            f"registry covers PostHire case {case}",
            f"page.{case}" in registry or f"page: '{case}'" in registry,
            case,
        )

    for dest in sorted(query_pages()):
        covered = (
            f"page.{dest}" in registry
            or f"page={dest}" in registry
            or dest in exclusions_block
        )
        check(f"registry or exclusion covers ?page={dest}", covered, dest)

    check("employee_app stays excluded", "employee_app" in exclusions_block)
    check("sidebar gap list is explicit", "HR_WEB_SIDEBAR_COVERAGE_GAPS" in registry)
    check("capability file still owns offerable nav", CAPABILITY.is_file())

    css = (DASH / "index.css").read_text(encoding="utf-8")
    check("semantic canvas token is an alias", "--color-semantic-canvas: var(" in css)
    check("semantic accent token is an alias", "--color-semantic-accent: var(" in css)

    print(f"\n    HR_WEB_SURFACE_CENSUS_{'PASS' if not FAIL else 'FAIL'}  {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
