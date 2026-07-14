"""HR-0: disable legacy_untrusted dashboard authentication.

Run: python3 smoke-test-hr0-legacy-dashboard-auth.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    HR-0 legacy_untrusted dashboard auth disabled")
    root = Path(__file__).resolve().parent
    source = (root / "app.py").read_text(encoding="utf-8")

    check("legacy gate helper exists", "def legacy_dashboard_token_auth_enabled" in source)
    check("startup assert exists", "assert_legacy_dashboard_auth_safe_at_startup" in source)
    check("dashboard_context blocks non-harness legacy path", "permission_authority_required" in source)
    check("health advertises backend_current_required", '"permission_authority": "backend_current_required"' in source)
    check("ready endpoint exists", '@app.get("/ready")' in source)
    check("login shared-token requires harness gate", "and legacy_dashboard_token_auth_enabled()" in source)
    check("context_permissions rejects non-backend_current", 'if authority != "backend_current"' in source)

    sys.path.insert(0, str(root))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2" or (exc.name or "").startswith("psycopg2"):
            print("NOTE: runtime checks skipped (psycopg2 unavailable locally).")
            print(f"\n{PASS} passed, {FAIL} failed")
            return 1 if FAIL else 0
        raise

    os.environ.pop("WATHEFNI_ALLOW_LEGACY_DASHBOARD_TOKEN_AUTH", None)
    os.environ.pop("WATHEFNI_ENV", None)
    os.environ.pop("PYTEST_CURRENT_TEST", None)
    check("default legacy auth disabled", app.legacy_dashboard_token_auth_enabled() is False)

    os.environ["WATHEFNI_ALLOW_LEGACY_DASHBOARD_TOKEN_AUTH"] = "1"
    os.environ["WATHEFNI_ENV"] = "production"
    check("production cannot enter legacy_untrusted", app.legacy_dashboard_token_auth_enabled() is False)
    try:
        app.assert_legacy_dashboard_auth_safe_at_startup()
        check("startup refuses production+flag", False)
    except RuntimeError:
        check("startup refuses production+flag", True)

    os.environ["WATHEFNI_ENV"] = "staging"
    check("staging cannot enter legacy_untrusted", app.legacy_dashboard_token_auth_enabled() is False)

    os.environ["WATHEFNI_ENV"] = "test"
    check("test harness can enable legacy path", app.legacy_dashboard_token_auth_enabled() is True)
    try:
        app.assert_legacy_dashboard_auth_safe_at_startup()
        check("startup allows explicit test harness", True)
    except RuntimeError:
        check("startup allows explicit test harness", False)

    forged = {
        "company_code": "FORGEDCO",
        "actor_user_id": "forged-user",
        "permission_authority": "legacy_untrusted",
        "permission_subject_user_id": "forged-user",
        "permission_subject_company": "FORGEDCO",
        "permissions": ["prehire.read", "users.manage", "attendance.read"],
        "actor_role": "owner",
    }
    check("forged legacy_untrusted permissions are empty", app.context_permissions(forged) == set())

    missing_subject = {
        "company_code": "FORGEDCO",
        "actor_user_id": "forged-user",
        "permission_authority": "backend_current",
        "permissions": ["prehire.read"],
        "actor_role": "owner",
    }
    check("forged claims without subject user id fail", app.context_permissions(missing_subject) == set())

    mismatched_company = {
        "company_code": "FORGEDCO",
        "actor_user_id": "u1",
        "permission_authority": "backend_current",
        "permission_subject_user_id": "u1",
        "permission_subject_company": "OTHERCO",
        "permissions": ["prehire.read"],
    }
    check("forged company mismatch fails", app.context_permissions(mismatched_company) == set())

    os.environ.pop("WATHEFNI_ALLOW_LEGACY_DASHBOARD_TOKEN_AUTH", None)
    os.environ["WATHEFNI_ENV"] = "production"
    os.environ["WATHEFNI_DASHBOARD_TOKEN"] = "shared-secret"
    with patch.object(app, "dashboard_user_by_session", return_value=None):
        with patch.object(app, "ensure_schema", return_value=None):
            try:
                app.dashboard_context(
                    authorization="Bearer shared-secret",
                    x_dashboard_token=None,
                    x_hr_phone="96555500000",
                    x_company_code="FORGEDCO",
                )
                check("shared token + forged phone rejected in production", False)
            except app.HTTPException as exc:
                check("shared token + forged phone rejected in production", exc.status_code == 401)
                detail = exc.detail if isinstance(exc.detail, dict) else {}
                check(
                    "rejection requires backend_current",
                    detail.get("permission_authority_required") == "backend_current",
                )

    for key in (
        "WATHEFNI_ALLOW_LEGACY_DASHBOARD_TOKEN_AUTH",
        "WATHEFNI_ENV",
        "WATHEFNI_DASHBOARD_TOKEN",
        "PYTEST_CURRENT_TEST",
    ):
        os.environ.pop(key, None)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
