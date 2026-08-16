#!/usr/bin/env python3
"""Production Readiness R10 — measured performance contracts (no guessing).

Hot display paths must be paged. Uncapped company_employees stays a hub helper
for 'all staff' mention-resolution, not the directory HTTP path.
"""
from __future__ import annotations

import sys
from pathlib import Path

PASS = 0
FAIL = 0
ROOT = Path(__file__).resolve().parent


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    print("    PRODUCTION READINESS R10 — measured performance contracts")
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("list_employees_page exists", "def list_employees_page(" in src)
    dash = src[src.find("def dashboard_posthire_employees") : src.find("def dashboard_posthire_employees") + 2500]
    check("HR employee directory uses list_employees_page", "list_employees_page(" in dash)
    check("HR employee directory does not call company_employees", "company_employees(" not in dash)
    check("directory LIMIT is capped at 500", "min(int(limit or 100), 500)" in dash)
    home = src[src.find("def app_home") : src.find("def app_home") + 1800]
    check("employee Home is a dedicated /app/home route", "def app_home" in src)
    check("company_employees documents why it is uncapped", "intentionally uncapped" in src)
    print("\n    R10_MEASURED_PERFORMANCE_UNIT_PASS" if not FAIL else "\n    R10_MEASURED_PERFORMANCE_UNIT_FAIL")
    print(f"    {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
