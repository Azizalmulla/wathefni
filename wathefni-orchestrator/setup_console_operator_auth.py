"""Setup Console operator session auth (access + refresh).

Platform operators sign in with a private email + password stored only as a
password hash in `setup_console_operators`. This table is not the HR dashboard
user directory. After a successful login the backend issues the existing opaque
access/refresh Setup Console session, still bound to an allowlisted operator
phone so superadmin/operator authorization stays fail-closed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PHASE = "setup_console_operator_auth"
CONTRACT_VERSION = "setup_operator_session_v1"
AUTH_METHOD = "operator_password"
CANONICAL_OPERATOR_EMAIL = "azizalmulla16@gmail.com"
CANONICAL_OPERATOR_PHONE = "96599338566"
PRODUCTION_CONFIRM_PHRASE = "SETUP_CONSOLE_OPERATOR_PRODUCTION"
PRODUCTION_DATABASES = frozenset({"wathefni", "wathefni_prod", "wathefni_production"})

# Short-lived access; longer refresh for persistent browser restarts.
ACCESS_TTL = timedelta(hours=8)
REFRESH_TTL = timedelta(days=30)
PASSWORD_ITERATIONS = 180_000

# Valid PBKDF2 value used only to keep unknown-email verification timing close
# to known-email verification. It is not a usable operator credential.
DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$180000$00000000000000000000000000000000$"
    "481f50a7dbf97d9df1710a10c0e1337d65cc61d7f7218cdeecff3970e20a6823"
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def token_hash(token: str | None) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def normalize_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest}"


def password_ok(password: str | None, stored: str | None) -> bool:
    if not password or not stored:
        return False
    try:
        scheme, iterations_text, salt, digest = str(stored).split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations_text),
        ).hex()
        return hmac.compare_digest(expected, digest)
    except Exception:
        return False


def digits(value: str | None) -> str:
    return re.sub(r"\D+", "", value or "")


def operator_phone_from_env() -> str:
    explicit = digits(os.environ.get("WATHEFNI_SETUP_OPERATOR_PHONE"))
    if explicit:
        return explicit
    raw_creds = (os.environ.get("WATHEFNI_SETUP_OPERATOR_CREDENTIALS") or "").strip()
    if raw_creds:
        try:
            parsed = json.loads(raw_creds)
        except Exception:
            parsed = {}
        if isinstance(parsed, dict):
            for key in parsed:
                phone = digits(key)
                if phone:
                    return phone
    admins = os.environ.get("WATHEFNI_PLATFORM_ADMINS") or os.environ.get("WATHEFNI_PLATFORM_ADMIN_PHONES") or ""
    for part in re.split(r"[,\s]+", admins):
        phone = digits(part)
        if phone:
            return phone
    return ""


def ensure_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS setup_console_operator_sessions (
          session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          actor_phone text NOT NULL,
          access_token_hash text NOT NULL UNIQUE,
          refresh_token_hash text NOT NULL UNIQUE,
          status text NOT NULL DEFAULT 'active',
          created_at timestamptz NOT NULL DEFAULT now(),
          last_seen_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          refresh_expires_at timestamptz NOT NULL,
          revoked_at timestamptz,
          revoked_reason text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_setup_console_operator_sessions_phone
          ON setup_console_operator_sessions (actor_phone, status, expires_at DESC)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS setup_console_operators (
          operator_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          email text NOT NULL UNIQUE,
          password_hash text NOT NULL,
          actor_phone text NOT NULL,
          display_name text NOT NULL DEFAULT 'OctoHR Platform Admin',
          status text NOT NULL DEFAULT 'active',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          last_login_at timestamptz
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_setup_console_operators_phone
          ON setup_console_operators (actor_phone, status)
        """
    )


def is_production_target(*, environment: str | None, database_name: str | None) -> bool:
    env = str(environment or "").strip().lower()
    db = str(database_name or "").strip().lower()
    return env == "production" or db in PRODUCTION_DATABASES


def require_canonical_operator_email(email: str | None) -> str:
    normalized = normalize_email(email)
    if normalized != CANONICAL_OPERATOR_EMAIL:
        raise ValueError("setup_console_operator_must_be_canonical")
    return normalized


def require_production_confirmation(
    *,
    environment: str | None,
    database_name: str | None,
    confirm_flag: str | None,
    confirm_env: str | None,
) -> None:
    """Fail closed unless production writes present the exact confirmation phrase twice."""
    flag = str(confirm_flag or "").strip()
    env_confirm = str(confirm_env or "").strip()
    if is_production_target(environment=environment, database_name=database_name):
        if flag != PRODUCTION_CONFIRM_PHRASE or env_confirm != PRODUCTION_CONFIRM_PHRASE:
            raise ValueError("production_operator_provisioning_requires_explicit_confirmation")
        return
    if flag or env_confirm:
        raise ValueError("production_confirmation_refused_for_non_production")


def read_operator_password_secret() -> str:
    """Read the operator password from env or a secret file. Never from argv."""
    secret = os.environ.get("WATHEFNI_SETUP_OPERATOR_PASSWORD") or ""
    if secret:
        return secret
    path_raw = (os.environ.get("WATHEFNI_SETUP_OPERATOR_PASSWORD_FILE") or "").strip()
    if path_raw:
        path = Path(path_raw)
        if not path.is_file() or path.is_symlink():
            raise ValueError("operator_password_file_unusable")
        secret = path.read_text(encoding="utf-8").strip()
        if secret:
            return secret
    return ""


def lookup_operator_by_email(cur: Any, email: str | None) -> dict[str, Any] | None:
    normalized = normalize_email(email)
    if not normalized or "@" not in normalized:
        return None
    ensure_schema(cur)
    cur.execute(
        """
        SELECT * FROM setup_console_operators
        WHERE email=%s
        LIMIT 1
        """,
        (normalized,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def list_operator_emails(cur: Any) -> list[str]:
    ensure_schema(cur)
    cur.execute("SELECT email FROM setup_console_operators ORDER BY email")
    return [normalize_email(row["email"] if isinstance(row, dict) else row[0]) for row in cur.fetchall()]


def upsert_operator(
    cur: Any,
    *,
    email: str,
    password: str,
    actor_phone: str,
    display_name: str = "OctoHR Platform Admin",
) -> dict[str, Any]:
    """Store or rotate an operator password hash. Plaintext is never persisted."""
    normalized = normalize_email(email)
    phone = digits(actor_phone)
    secret = str(password or "")
    if not normalized or "@" not in normalized:
        raise ValueError("operator_email_invalid")
    if len(secret) < 8:
        raise ValueError("operator_password_too_short")
    if not phone:
        raise ValueError("operator_phone_required")
    ensure_schema(cur)
    hashed = password_hash(secret)
    cur.execute(
        """
        INSERT INTO setup_console_operators
          (email, password_hash, actor_phone, display_name, status, updated_at)
        VALUES (%s,%s,%s,%s,'active', now())
        ON CONFLICT (email) DO UPDATE
          SET password_hash=EXCLUDED.password_hash,
              actor_phone=EXCLUDED.actor_phone,
              display_name=EXCLUDED.display_name,
              status='active',
              updated_at=now()
        RETURNING operator_id, email, actor_phone, display_name, status
        """,
        (normalized, hashed, phone, str(display_name or "OctoHR Platform Admin").strip() or "OctoHR Platform Admin"),
    )
    return dict(cur.fetchone())


def mark_operator_login(cur: Any, operator_id: Any) -> None:
    cur.execute(
        """
        UPDATE setup_console_operators
        SET last_login_at=now(), updated_at=now()
        WHERE operator_id=%s
        """,
        (operator_id,),
    )


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("metadata")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def session_public(
    row: dict[str, Any],
    *,
    access_token: str | None = None,
    refresh_token: str | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    metadata = _metadata(row)
    payload = {
        "ok": True,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "token_type": "bearer",
        "phone": str(row.get("actor_phone") or ""),
        "email": normalize_email(email) or normalize_email(metadata.get("email") if isinstance(metadata, dict) else ""),
        "session_id": str(row.get("session_id") or ""),
        "expires_at": _iso(row.get("expires_at")),
        "refresh_expires_at": _iso(row.get("refresh_expires_at")),
        "access_ttl_seconds": int(ACCESS_TTL.total_seconds()),
        "refresh_ttl_seconds": int(REFRESH_TTL.total_seconds()),
    }
    if access_token:
        payload["access_token"] = access_token
    if refresh_token:
        payload["refresh_token"] = refresh_token
    return payload


def create_session(cur: Any, *, actor_phone: str, actor_email: str = "") -> dict[str, Any]:
    ensure_schema(cur)
    phone = digits(actor_phone) or str(actor_phone or "").strip()
    email = normalize_email(actor_email)
    access = secrets.token_urlsafe(32)
    refresh = secrets.token_urlsafe(48)
    now = now_utc()
    expires_at = now + ACCESS_TTL
    refresh_expires_at = now + REFRESH_TTL
    metadata = json.dumps(
        {
            "auth": AUTH_METHOD,
            "contract": CONTRACT_VERSION,
            "email": email,
        }
    )
    cur.execute(
        """
        INSERT INTO setup_console_operator_sessions
          (actor_phone, access_token_hash, refresh_token_hash, expires_at, refresh_expires_at, metadata)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        RETURNING *
        """,
        (
            phone,
            token_hash(access),
            token_hash(refresh),
            expires_at,
            refresh_expires_at,
            metadata,
        ),
    )
    row = dict(cur.fetchone())
    return session_public(row, access_token=access, refresh_token=refresh, email=email)


def lookup_by_access(cur: Any, access_token: str | None) -> dict[str, Any] | None:
    if not access_token:
        return None
    ensure_schema(cur)
    cur.execute(
        """
        SELECT * FROM setup_console_operator_sessions
        WHERE access_token_hash=%s
          AND status='active'
          AND expires_at > now()
        LIMIT 1
        """,
        (token_hash(access_token),),
    )
    row = cur.fetchone()
    if not row:
        return None
    sess = dict(row)
    cur.execute(
        "UPDATE setup_console_operator_sessions SET last_seen_at=now() WHERE session_id=%s",
        (sess["session_id"],),
    )
    return sess


def rotate_session(cur: Any, refresh_token: str | None) -> dict[str, Any] | None:
    if not refresh_token:
        return None
    ensure_schema(cur)
    presented = token_hash(refresh_token)
    cur.execute(
        """
        SELECT * FROM setup_console_operator_sessions
        WHERE refresh_token_hash=%s
        LIMIT 1
        FOR UPDATE
        """,
        (presented,),
    )
    row = cur.fetchone()
    if not row:
        return None
    sess = dict(row)
    if str(sess.get("status") or "") != "active":
        return None
    refresh_expires = sess.get("refresh_expires_at")
    if refresh_expires is None:
        return None
    if getattr(refresh_expires, "tzinfo", None) is None:
        refresh_expires = refresh_expires.replace(tzinfo=timezone.utc)
    if refresh_expires <= now_utc():
        cur.execute(
            """
            UPDATE setup_console_operator_sessions
            SET status='revoked', revoked_at=now(), revoked_reason='refresh_expired'
            WHERE session_id=%s AND status='active'
            """,
            (sess["session_id"],),
        )
        return None

    access = secrets.token_urlsafe(32)
    refresh = secrets.token_urlsafe(48)
    now = now_utc()
    expires_at = now + ACCESS_TTL
    refresh_expires_at = now + REFRESH_TTL
    cur.execute(
        """
        UPDATE setup_console_operator_sessions
        SET access_token_hash=%s,
            refresh_token_hash=%s,
            expires_at=%s,
            refresh_expires_at=%s,
            last_seen_at=now()
        WHERE session_id=%s
        RETURNING *
        """,
        (token_hash(access), token_hash(refresh), expires_at, refresh_expires_at, sess["session_id"]),
    )
    updated = dict(cur.fetchone())
    metadata = _metadata(updated)
    email = metadata.get("email") if isinstance(metadata, dict) else ""
    return session_public(updated, access_token=access, refresh_token=refresh, email=str(email or ""))


def revoke_session(
    cur: Any,
    *,
    access_token: str | None = None,
    refresh_token: str | None = None,
    reason: str = "logout",
) -> bool:
    ensure_schema(cur)
    if access_token:
        cur.execute(
            """
            UPDATE setup_console_operator_sessions
            SET status='revoked', revoked_at=now(), revoked_reason=%s
            WHERE access_token_hash=%s AND status='active'
            """,
            (reason, token_hash(access_token)),
        )
        if cur.rowcount:
            return True
    if refresh_token:
        cur.execute(
            """
            UPDATE setup_console_operator_sessions
            SET status='revoked', revoked_at=now(), revoked_reason=%s
            WHERE refresh_token_hash=%s AND status='active'
            """,
            (reason, token_hash(refresh_token)),
        )
        return bool(cur.rowcount)
    return False
