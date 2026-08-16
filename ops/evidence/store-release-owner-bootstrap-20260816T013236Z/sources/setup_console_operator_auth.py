"""Setup Console operator session auth (access + refresh).

Internal Wathefni operators authenticate once with the existing allowlisted
operator token + phone. The backend issues opaque access/refresh session tokens
(same pattern as employee sessions / dashboard sessions — not a new account system).

Phases 1–5 product surfaces are untouched; this only replaces browser
sessionStorage reuse of the long-lived operator secret.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

PHASE = "setup_console_operator_auth"
CONTRACT_VERSION = "setup_operator_session_v1"

# Short-lived access; longer refresh for persistent browser restarts.
ACCESS_TTL = timedelta(hours=8)
REFRESH_TTL = timedelta(days=30)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def token_hash(token: str | None) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


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


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def session_public(row: dict[str, Any], *, access_token: str | None = None, refresh_token: str | None = None) -> dict[str, Any]:
    payload = {
        "ok": True,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "token_type": "bearer",
        "phone": str(row.get("actor_phone") or ""),
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


def create_session(cur: Any, *, actor_phone: str) -> dict[str, Any]:
    ensure_schema(cur)
    phone = str(actor_phone or "").strip()
    access = secrets.token_urlsafe(32)
    refresh = secrets.token_urlsafe(48)
    now = now_utc()
    expires_at = now + ACCESS_TTL
    refresh_expires_at = now + REFRESH_TTL
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
            '{"auth":"operator_token","contract":"setup_operator_session_v1"}',
        ),
    )
    row = dict(cur.fetchone())
    return session_public(row, access_token=access, refresh_token=refresh)


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
    # Keep absolute refresh window from original mint unless near expiry — extend on successful use.
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
    return session_public(updated, access_token=access, refresh_token=refresh)


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
