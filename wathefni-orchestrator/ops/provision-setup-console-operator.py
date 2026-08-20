#!/usr/bin/env python3
"""One-time Setup Console operator provisioner.

Pins the single operator to azizalmulla16@gmail.com. Reads the password only
from WATHEFNI_SETUP_OPERATOR_PASSWORD, WATHEFNI_SETUP_OPERATOR_PASSWORD_FILE,
or a hidden prompt. Stores a PBKDF2 hash. Never logs or persists plaintext.

Production writes require the confirmation phrase on both the CLI flag and
WATHEFNI_SETUP_OPERATOR_PRODUCTION_CONFIRM. This never runs as a side effect
of Setup Console login.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import setup_console_operator_auth as setup_auth  # noqa: E402

CANONICAL_EMAIL = setup_auth.CANONICAL_OPERATOR_EMAIL
CONFIRM_PHRASE = setup_auth.PRODUCTION_CONFIRM_PHRASE


def _die(code: str) -> None:
    raise SystemExit(code)


def _read_password() -> str:
    secret = setup_auth.read_operator_password_secret()
    if not secret and sys.stdin.isatty():
        secret = getpass.getpass("Setup Console operator password: ")
    if len(secret) < 8:
        _die("operator_password_missing_or_too_short")
    return secret


def _bound_phone() -> str:
    phone = setup_auth.operator_phone_from_env() or setup_auth.CANONICAL_OPERATOR_PHONE
    phone = setup_auth.digits(phone)
    if not phone:
        _die("operator_phone_binding_missing")
    return phone


def _current_database(cur) -> str:
    cur.execute("SELECT current_database()")
    row = cur.fetchone()
    if isinstance(row, dict):
        return str(row.get("current_database") or "")
    return str(row[0] if row else "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision the single Setup Console operator hash")
    parser.add_argument(
        "--confirm-production",
        default="",
        help=f"Must equal {CONFIRM_PHRASE} for production writes",
    )
    parser.add_argument(
        "--rotate-password",
        action="store_true",
        help="Replace the stored hash for the canonical operator if it already exists",
    )
    args = parser.parse_args()

    try:
        email = setup_auth.require_canonical_operator_email(CANONICAL_EMAIL)
    except ValueError as exc:
        _die(str(exc))

    password = _read_password()
    existing = None
    row = None
    try:
        phone = _bound_phone()
        environment = (os.environ.get("WATHEFNI_ENV") or os.environ.get("WATHEFNI_APP_ENVIRONMENT") or "").strip().lower()
        confirm_env = os.environ.get("WATHEFNI_SETUP_OPERATOR_PRODUCTION_CONFIRM") or ""

        import app as legacy

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                setup_auth.ensure_schema(cur)
                database_name = _current_database(cur)
                try:
                    setup_auth.require_production_confirmation(
                        environment=environment,
                        database_name=database_name,
                        confirm_flag=args.confirm_production,
                        confirm_env=confirm_env,
                    )
                except ValueError as exc:
                    conn.rollback()
                    _die(str(exc))

                existing_emails = setup_auth.list_operator_emails(cur)
                others = [item for item in existing_emails if item and item != email]
                if others:
                    conn.rollback()
                    _die("setup_console_refuses_additional_operators")

                existing = setup_auth.lookup_operator_by_email(cur, email)
                if existing and not args.rotate_password:
                    conn.rollback()
                    _die("setup_console_operator_already_provisioned")

                credentials = legacy.setup_operator_credentials() if hasattr(legacy, "setup_operator_credentials") else {}
                allow = legacy.platform_admin_phones() if hasattr(legacy, "platform_admin_phones") else set()
                production = setup_auth.is_production_target(environment=environment, database_name=database_name)
                if production:
                    if not credentials or phone not in credentials:
                        conn.rollback()
                        _die("operator_phone_not_in_credential_allowlist")
                    if not allow or phone not in allow:
                        conn.rollback()
                        _die("operator_phone_not_in_platform_admin_allowlist")
                else:
                    if credentials and phone not in credentials:
                        conn.rollback()
                        _die("operator_phone_not_in_credential_allowlist")
                    if allow and phone not in allow:
                        conn.rollback()
                        _die("operator_phone_not_in_platform_admin_allowlist")

                row = setup_auth.upsert_operator(
                    cur,
                    email=email,
                    password=password,
                    actor_phone=phone,
                    display_name="OctoHR Platform Admin",
                )
            conn.commit()
    finally:
        password = ""

    action = "rotated" if existing else "created"
    print(
        "setup console operator "
        f"{action} email={row.get('email')} phone={row.get('actor_phone')} "
        f"operator_id={row.get('operator_id')} status={row.get('status')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
