#!/usr/bin/env python3
"""Setup first-owner bootstrap grants — unit contracts (no DB)."""
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
    sys.path.insert(0, str(ROOT))
    import setup_owner_bootstrap as boot
    import app

    print("    SETUP OWNER BOOTSTRAP — unit")
    check("bundle version is explicit", boot.BUNDLE_VERSION == "setup_owner_bootstrap_v1")
    check("employees.read is in the bundle", "employees.read" in boot.OWNER_BOOTSTRAP_PERMISSIONS)
    check("employees.manage is in the bundle", "employees.manage" in boot.OWNER_BOOTSTRAP_PERMISSIONS)
    check("bundle does not infer from role", "employees.manage" not in app.ROLE_PERMISSIONS["owner"])
    check("employees.manage remains grant-only", "employees.manage" in app.EMPLOYEE_PERMISSION_SCOPES)
    for forbidden in boot.FORBIDDEN_BOOTSTRAP_PERMISSIONS:
        check(f"bundle excludes {forbidden}", forbidden not in boot.OWNER_BOOTSTRAP_PERMISSIONS)
    check("bootstrap_permissions() validates", set(boot.bootstrap_permissions()) == set(boot.OWNER_BOOTSTRAP_PERMISSIONS))
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("Setup owner seed writes bootstrap grants", "apply_owner_bootstrap_grants" in src)
    check("invite accept writes bootstrap grants for owner", src.count("apply_owner_bootstrap_grants") >= 2)
    check("bootstrap grants are audited", src.count("setup_owner_bootstrap_grants") >= 3)
    check("seed still does not grant payroll.export via bootstrap", "payroll.export" not in (ROOT / "setup_owner_bootstrap.py").read_text(encoding="utf-8").split("FORBIDDEN")[0])

    print(f"\n    SETUP_OWNER_BOOTSTRAP_UNIT_{'PASS' if not FAIL else 'FAIL'}")
    print(f"    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
