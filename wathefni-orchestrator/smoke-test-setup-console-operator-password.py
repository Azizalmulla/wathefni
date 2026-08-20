#!/usr/bin/env python3
"""Setup Console operator email/password login — source and hash contracts (no DB)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PASS = 0
FAIL = 0

ROOT = Path(__file__).resolve().parent
DASH = ROOT.parent / "apps" / "wathefni-dashboard" / "src" / "setup-console"


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
    import setup_console_operator_auth as auth

    print("    SETUP CONSOLE operator email/password")

    secret = "Unit-operator-password-not-production"
    hashed = auth.password_hash(secret)
    check("password hash uses pbkdf2_sha256", hashed.startswith("pbkdf2_sha256$180000$"))
    check("plain password is not stored in the hash", secret not in hashed)
    check("matching password verifies", auth.password_ok(secret, hashed) is True)
    check("wrong password is rejected", auth.password_ok("other-password-value", hashed) is False)
    check("dummy hash is not a usable shortcut", auth.password_ok(secret, auth.DUMMY_PASSWORD_HASH) is False)
    check("email is normalized", auth.normalize_email("  AzizAlmulla16@Gmail.COM ") == "azizalmulla16@gmail.com")

    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    login_start = app_source.index("def setup_console_operator_login")
    login_end = app_source.index("def setup_console_operator_refresh")
    login_fn = app_source[login_start:login_end]
    check("login reads setup_console_operators", "lookup_operator_by_email" in login_fn)
    check("login does not query dashboard_users", "dashboard_users" not in login_fn)
    check("login still requires platform-admin allowlist", "platform_admin_phones()" in login_fn)
    check("login still requires operator credential map", "setup_operator_credentials()" in login_fn)
    check("login issues existing operator session", "create_session" in login_fn)
    check("legacy operator token is no longer the login body", "operator_token" not in login_fn)
    check("login does not auto-create an operator", "maybe_bootstrap_from_env" not in login_fn)
    check("app.py does not auto-create an operator", "maybe_bootstrap_from_env" not in app_source)
    check("auto-bootstrap helper is gone", "def maybe_bootstrap_from_env" not in (ROOT / "setup_console_operator_auth.py").read_text(encoding="utf-8"))

    try:
        auth.require_canonical_operator_email("other@example.com")
        check("non-canonical operator email is rejected", False)
    except ValueError:
        check("non-canonical operator email is rejected", True)
    check(
        "canonical operator email is pinned",
        auth.require_canonical_operator_email("  AzizAlmulla16@Gmail.COM ") == "azizalmulla16@gmail.com",
    )
    try:
        auth.require_production_confirmation(
            environment="production",
            database_name="wathefni",
            confirm_flag="",
            confirm_env="",
        )
        check("production provision without confirmation is refused", False)
    except ValueError:
        check("production provision without confirmation is refused", True)
    try:
        auth.require_production_confirmation(
            environment="production",
            database_name="wathefni",
            confirm_flag=auth.PRODUCTION_CONFIRM_PHRASE,
            confirm_env="",
        )
        check("production provision requires env confirmation too", False)
    except ValueError:
        check("production provision requires env confirmation too", True)
    auth.require_production_confirmation(
        environment="production",
        database_name="wathefni",
        confirm_flag=auth.PRODUCTION_CONFIRM_PHRASE,
        confirm_env=auth.PRODUCTION_CONFIRM_PHRASE,
    )
    check("matching production confirmation is accepted", True)
    try:
        auth.require_production_confirmation(
            environment="staging",
            database_name="wathefni_staging",
            confirm_flag=auth.PRODUCTION_CONFIRM_PHRASE,
            confirm_env=auth.PRODUCTION_CONFIRM_PHRASE,
        )
        check("production confirmation is refused on staging", False)
    except ValueError:
        check("production confirmation is refused on staging", True)
    auth.require_production_confirmation(
        environment="staging",
        database_name="wathefni_staging",
        confirm_flag="",
        confirm_env="",
    )
    check("staging provision does not need production confirmation", True)

    provisioner = (ROOT / "ops" / "provision-setup-console-operator.py").read_text(encoding="utf-8")
    check("provisioner pins the single operator email", "azizalmulla16@gmail.com" in provisioner)
    check("provisioner has no password CLI flag", "--password" not in provisioner)
    check("provisioner reads a secret password", "read_operator_password_secret" in provisioner)
    check("provisioner never prints the password", "print(" not in provisioner.lower() or "password" not in "".join(
        line for line in provisioner.splitlines() if "print(" in line
    ).lower())
    check("provisioner requires production confirmation helpers", "require_production_confirmation" in provisioner)
    check("provisioner preserves phone allowlist binding", "operator_phone_not_in_platform_admin_allowlist" in provisioner)

    os.environ.pop("WATHEFNI_SETUP_OPERATOR_PASSWORD", None)
    os.environ.pop("WATHEFNI_SETUP_OPERATOR_PASSWORD_FILE", None)
    check("password secret is not read from empty env", auth.read_operator_password_secret() == "")
    os.environ["WATHEFNI_SETUP_OPERATOR_PASSWORD"] = "env-only-operator-secret"
    check("password secret is read from env", auth.read_operator_password_secret() == "env-only-operator-secret")
    os.environ.pop("WATHEFNI_SETUP_OPERATOR_PASSWORD", None)

    session_ts = (DASH / "session.ts").read_text(encoding="utf-8")
    setup_app = (DASH / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
    login_helper_start = session_ts.index("export async function loginWithOperatorPassword")
    login_helper_end = session_ts.index("export async function refreshSetupSession")
    login_helper = session_ts[login_helper_start:login_helper_end]
    check("browser login posts email and password", "email: input.email.trim()" in login_helper and "password: input.password" in login_helper)
    check("browser does not send operator_token", "operator_token" not in login_helper)
    check("admin sign-in copy is clean", "Admin sign-in" in setup_app)
    check("token/phone fields are gone from the screen", "Operator token" not in setup_app and "Authorised operator phone" not in setup_app)
    check("frontend login helper is password-based", "loginWithOperatorPassword" in setup_app)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("SETUP_CONSOLE_OPERATOR_PASSWORD_FAIL")
        return 1
    print("SETUP_CONSOLE_OPERATOR_PASSWORD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
