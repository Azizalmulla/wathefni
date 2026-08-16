"""Wathefni Calendar C5 — provider-neutral external sync authority.

Wathefni Calendar remains source of truth. Providers are one-way mirrors.
Google-specific logic lives only in calendar_sync_google.py.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from uuid import uuid4

import calendar_schema
from calendar_sync_adapter import get_adapter

DEFAULT_SYNC_EVENT_TYPES = (
    "meeting",
    "interview",
    "personal_block",
    "hold",
    "out_of_office",
    "deadline",
    "other",
)


class CalendarSyncError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 422, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = dict(details or {})

    def envelope(self) -> dict[str, Any]:
        return {"ok": False, "error": self.code, "message": self.message, **self.details}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(legacy: Any, value: Any) -> Any:
    if hasattr(legacy, "Json"):
        return legacy.Json(value if value is not None else {})
    return value if value is not None else {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_schema(legacy: Any) -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
        conn.commit()


def _audit(cur: Any, legacy: Any, **kwargs: Any) -> None:
    cur.execute(
        """
        INSERT INTO calendar_sync_audit
          (audit_id, company_code, connection_id, event_id, actor_user_id, action, before_json, after_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            str(uuid4()),
            _text(kwargs.get("company_code")).upper(),
            kwargs.get("connection_id"),
            kwargs.get("event_id"),
            kwargs.get("actor_user_id"),
            _text(kwargs.get("action")),
            _json(legacy, kwargs.get("before") or {}),
            _json(legacy, kwargs.get("after") or {}),
        ),
    )


def calendar_policy(legacy: Any, company_code: str) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    try:
        settings = dict(legacy.get_company_settings(company_code) or {})
    except Exception:
        settings = {}
    policy = settings.get("calendar_policy") if isinstance(settings.get("calendar_policy"), dict) else {}
    return {
        "sync_include_candidate_name": bool(policy.get("sync_include_candidate_name", False)),
        "external_delete_policy": _text(policy.get("external_delete_policy") or "ignore") or "ignore",
        "sync_event_types": list(policy.get("sync_event_types") or DEFAULT_SYNC_EVENT_TYPES),
    }


def serialize_connection(row: Mapping[str, Any] | None, *, has_credentials: bool = False) -> dict[str, Any] | None:
    if not row:
        return None
    platform_id = _text(row.get("platform_integration_id")) or None
    return {
        "connection_id": str(row.get("connection_id")),
        "company_code": _text(row.get("company_code")).upper(),
        "provider_key": _text(row.get("provider_key")),
        "mode": _text(row.get("mode")),
        "status": _text(row.get("status")),
        "account_email": _text(row.get("account_email")) or None,
        "external_calendar_id": _text(row.get("external_calendar_id")) or "primary",
        "display_name": _text(row.get("display_name")) or None,
        "sync_event_types": row.get("sync_event_types") if isinstance(row.get("sync_event_types"), list) else DEFAULT_SYNC_EVENT_TYPES,
        "sync_include_candidate_name": bool(row.get("sync_include_candidate_name")),
        "with_meet_default": bool(row.get("with_meet_default")),
        "platform_integration_id": platform_id,
        "last_sync_at": row.get("last_sync_at").isoformat() if hasattr(row.get("last_sync_at"), "isoformat") else row.get("last_sync_at"),
        "last_error": _text(row.get("last_error")) or None,
        "health": row.get("health") if isinstance(row.get("health"), dict) else {},
        "has_credentials": bool(has_credentials) or _text(row.get("mode")) == "legacy_operator",
        "disconnected_at": row.get("disconnected_at").isoformat() if hasattr(row.get("disconnected_at"), "isoformat") else row.get("disconnected_at"),
        "created_at": row.get("created_at").isoformat() if hasattr(row.get("created_at"), "isoformat") else row.get("created_at"),
        "updated_at": row.get("updated_at").isoformat() if hasattr(row.get("updated_at"), "isoformat") else row.get("updated_at"),
    }


def serialize_binding(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "binding_id": str(row.get("binding_id")),
        "company_code": _text(row.get("company_code")).upper(),
        "event_id": str(row.get("event_id")),
        "connection_id": str(row.get("connection_id")),
        "provider_event_id": _text(row.get("provider_event_id")) or None,
        "provider_calendar_id": _text(row.get("provider_calendar_id")) or None,
        "external_html_link": _text(row.get("external_html_link")) or None,
        "sync_status": _text(row.get("sync_status")),
        "last_pushed_version": row.get("last_pushed_version"),
        "last_synced_at": row.get("last_synced_at").isoformat() if hasattr(row.get("last_synced_at"), "isoformat") else row.get("last_synced_at"),
        "last_error": _text(row.get("last_error")) or None,
    }


def list_connections(legacy: Any, *, company_code: str) -> list[dict[str, Any]]:
    company = _text(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            cur.execute(
                """
                SELECT c.*,
                       (
                         EXISTS(
                           SELECT 1 FROM calendar_sync_credentials cr
                           WHERE cr.connection_id=c.connection_id
                         )
                         OR (
                           c.platform_integration_id IS NOT NULL
                           AND EXISTS(
                             SELECT 1 FROM platform_company_integration_credentials pc
                             WHERE pc.integration_id=c.platform_integration_id
                           )
                         )
                       ) AS has_credentials
                FROM calendar_sync_connections c
                WHERE c.company_code=%s
                ORDER BY c.created_at ASC
                """,
                (company,),
            )
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    return [serialize_connection(r, has_credentials=bool(r.get("has_credentials"))) or {} for r in rows]


def get_connection(cur: Any, *, company_code: str, connection_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT c.*,
               (
                 EXISTS(
                   SELECT 1 FROM calendar_sync_credentials cr WHERE cr.connection_id=c.connection_id
                 )
                 OR (
                   c.platform_integration_id IS NOT NULL
                   AND EXISTS(
                     SELECT 1 FROM platform_company_integration_credentials pc
                     WHERE pc.integration_id=c.platform_integration_id
                   )
                 )
               ) AS has_credentials
        FROM calendar_sync_connections c
        WHERE c.company_code=%s AND c.connection_id=%s
        LIMIT 1
        """,
        (_text(company_code).upper(), connection_id),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _store_refresh_token(cur: Any, legacy: Any, *, company_code: str, connection_id: str, refresh_token: str) -> None:
    if not hasattr(legacy, "encrypt_sensitive_text"):
        raise CalendarSyncError("encryption_unavailable", "Credential encryption is not configured.", http_status=503)
    enc = legacy.encrypt_sensitive_text(refresh_token)
    cur.execute(
        """
        INSERT INTO calendar_sync_credentials
          (credential_id, connection_id, company_code, secret_type, ciphertext, key_version, alg, updated_at)
        VALUES (%s,%s,%s,'refresh_token',%s,%s,%s,now())
        ON CONFLICT (connection_id, secret_type) DO UPDATE
          SET ciphertext=EXCLUDED.ciphertext,
              key_version=EXCLUDED.key_version,
              alg=EXCLUDED.alg,
              updated_at=now()
        """,
        (
            str(uuid4()),
            connection_id,
            _text(company_code).upper(),
            enc["ciphertext"],
            enc["key_version"],
            enc.get("alg") or "fernet",
        ),
    )


def _load_refresh_token(cur: Any, legacy: Any, *, company_code: str, connection_id: str) -> str | None:
    cur.execute(
        """
        SELECT ciphertext FROM calendar_sync_credentials
        WHERE company_code=%s AND connection_id=%s AND secret_type='refresh_token'
        LIMIT 1
        """,
        (_text(company_code).upper(), connection_id),
    )
    row = cur.fetchone()
    if not row:
        return None
    if not hasattr(legacy, "decrypt_sensitive_text"):
        return None
    return legacy.decrypt_sensitive_text(row["ciphertext"])


def connect_google_company(
    legacy: Any,
    *,
    company_code: str,
    account_email: str,
    refresh_token: str,
    actor_user_id: str | None = None,
    external_calendar_id: str = "primary",
    display_name: str | None = None,
    sync_event_types: Sequence[str] | None = None,
    sync_include_candidate_name: bool | None = None,
    with_meet_default: bool = False,
) -> dict[str, Any]:
    """Create/reconnect Google sync via platform google_workspace integration authority."""
    import platform_integrations as pi

    company = _text(company_code).upper()
    # Platform connection is the credential authority.
    platform = pi.connect_provider(
        legacy,
        company_code=company,
        provider_key=pi.PROVIDER_GOOGLE_WORKSPACE,
        account_email=account_email,
        refresh_token=refresh_token,
        actor_user_id=actor_user_id,
        display_name=display_name,
        capabilities=[pi.CAPABILITY_CALENDAR_EVENTS, pi.CAPABILITY_MEETINGS_CREATE],
    )
    integration_id = (platform.get("integration") or {}).get("integration_id")
    attached = pi.attach_calendar_sync_connection(
        legacy,
        company_code=company,
        integration_id=str(integration_id),
        actor_user_id=actor_user_id,
        external_calendar_id=external_calendar_id or "primary",
        with_meet_default=bool(with_meet_default),
    )
    # Apply optional sync policy overrides on the calendar connection.
    connection_id = (attached.get("connection") or {}).get("connection_id")
    if connection_id and (
        sync_event_types is not None or sync_include_candidate_name is not None or display_name is not None
    ):
        update_connection_settings(
            legacy,
            company_code=company,
            connection_id=str(connection_id),
            actor_user_id=actor_user_id,
            sync_event_types=sync_event_types,
            sync_include_candidate_name=sync_include_candidate_name,
            display_name=display_name,
            with_meet_default=with_meet_default,
        )
        # reload
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                calendar_schema.ensure_calendar_schema(cur)
                row = get_connection(cur, company_code=company, connection_id=str(connection_id))
            conn.commit()
        return {
            "ok": True,
            "connection": serialize_connection(row, has_credentials=True),
            "integration": platform.get("integration"),
        }
    return {"ok": True, "connection": attached.get("connection"), "integration": platform.get("integration")}


def connect_microsoft_company(
    legacy: Any,
    *,
    company_code: str,
    account_email: str,
    refresh_token: str,
    actor_user_id: str | None = None,
    external_calendar_id: str = "calendar",
    display_name: str | None = None,
    external_tenant_id: str | None = None,
    with_meet_default: bool = True,
) -> dict[str, Any]:
    """Create/reconnect Outlook/Teams sync via platform microsoft_365 integration."""
    import platform_integrations as pi

    platform = pi.connect_provider(
        legacy,
        company_code=company_code,
        provider_key=pi.PROVIDER_MICROSOFT_365,
        account_email=account_email,
        refresh_token=refresh_token,
        actor_user_id=actor_user_id,
        display_name=display_name,
        external_tenant_id=external_tenant_id,
        capabilities=[pi.CAPABILITY_CALENDAR_EVENTS, pi.CAPABILITY_MEETINGS_CREATE],
    )
    integration_id = (platform.get("integration") or {}).get("integration_id")
    attached = pi.attach_calendar_sync_connection(
        legacy,
        company_code=company_code,
        integration_id=str(integration_id),
        actor_user_id=actor_user_id,
        external_calendar_id=external_calendar_id or "calendar",
        with_meet_default=bool(with_meet_default),
    )
    return {"ok": True, "connection": attached.get("connection"), "integration": platform.get("integration")}


def ensure_legacy_operator_connection(
    legacy: Any,
    *,
    company_code: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Represent platform GOG_ACCOUNT as mode=legacy_operator for this tenant (transitional)."""
    company = _text(company_code).upper()
    account = ""
    try:
        account = _text((legacy.openclaw_env() or {}).get("GOG_ACCOUNT"))
    except Exception:
        account = _text(os.environ.get("GOG_ACCOUNT"))
    if not account and _text(os.environ.get("CALENDAR_SYNC_DRY_RUN")).lower() not in {"1", "true", "yes", "on"}:
        # Still allow creating the row so migration tooling can attach; mark error if no account.
        pass
    policy = calendar_policy(legacy, company)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            cur.execute(
                """
                SELECT * FROM calendar_sync_connections
                WHERE company_code=%s AND provider_key='google' AND mode='legacy_operator'
                ORDER BY created_at ASC LIMIT 1
                """,
                (company,),
            )
            existing = cur.fetchone()
            status = "connected" if account or _text(os.environ.get("CALENDAR_SYNC_DRY_RUN")).lower() in {"1", "true", "yes", "on"} else "error"
            if existing:
                cur.execute(
                    """
                    UPDATE calendar_sync_connections
                    SET status=%s, account_email=%s, credentials_ref='platform:GOG_ACCOUNT',
                        sync_event_types=%s::jsonb, sync_include_candidate_name=%s,
                        last_error=%s, disconnected_at=NULL, updated_at=now()
                    WHERE connection_id=%s AND company_code=%s
                    RETURNING *
                    """,
                    (
                        status,
                        account or None,
                        _json(legacy, policy["sync_event_types"]),
                        bool(policy["sync_include_candidate_name"]),
                        None if status == "connected" else "gog_account_missing",
                        str(existing["connection_id"]),
                        company,
                    ),
                )
                row = dict(cur.fetchone())
            else:
                cur.execute(
                    """
                    INSERT INTO calendar_sync_connections
                      (connection_id, company_code, provider_key, mode, status, credentials_ref,
                       account_email, external_calendar_id, display_name, sync_event_types,
                       sync_include_candidate_name, last_error)
                    VALUES (%s,%s,'google','legacy_operator',%s,'platform:GOG_ACCOUNT',%s,'primary',
                            'Legacy operator Google',%s::jsonb,%s,%s)
                    RETURNING *
                    """,
                    (
                        str(uuid4()),
                        company,
                        status,
                        account or None,
                        _json(legacy, policy["sync_event_types"]),
                        bool(policy["sync_include_candidate_name"]),
                        None if status == "connected" else "gog_account_missing",
                    ),
                )
                row = dict(cur.fetchone())
            _audit(
                cur,
                legacy,
                company_code=company,
                connection_id=str(row["connection_id"]),
                actor_user_id=actor_user_id,
                action="legacy_operator_ensured",
                before={},
                after={"account_email": account or None, "status": status},
            )
        conn.commit()
    return {"ok": True, "connection": serialize_connection(row, has_credentials=True)}


def disconnect_connection(
    legacy: Any,
    *,
    company_code: str,
    connection_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    company = _text(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            cur.execute(
                """
                UPDATE calendar_sync_connections
                SET status='disconnected', disconnected_at=now(), updated_at=now()
                WHERE company_code=%s AND connection_id=%s
                RETURNING *
                """,
                (company, connection_id),
            )
            row = cur.fetchone()
            if not row:
                raise CalendarSyncError("connection_not_found", "Sync connection not found.", http_status=404)
            # Cancel pending outbox for this connection — Wathefni events untouched.
            cur.execute(
                """
                UPDATE calendar_sync_outbox
                SET status='cancelled', updated_at=now(), last_error='connection_disconnected'
                WHERE company_code=%s AND connection_id=%s
                  AND status IN ('queued','failed','processing')
                """,
                (company, connection_id),
            )
            _audit(
                cur,
                legacy,
                company_code=company,
                connection_id=connection_id,
                actor_user_id=actor_user_id,
                action="connection_disconnected",
                before={},
                after={"status": "disconnected"},
            )
        conn.commit()
    return {"ok": True, "connection": serialize_connection(dict(row))}


def reconnect_connection(
    legacy: Any,
    *,
    company_code: str,
    connection_id: str,
    actor_user_id: str | None = None,
    refresh_token: str | None = None,
) -> dict[str, Any]:
    company = _text(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            row = get_connection(cur, company_code=company, connection_id=connection_id)
            if not row:
                raise CalendarSyncError("connection_not_found", "Sync connection not found.", http_status=404)
            if _text(row.get("mode")) == "company" and refresh_token:
                _store_refresh_token(cur, legacy, company_code=company, connection_id=connection_id, refresh_token=_text(refresh_token))
            cur.execute(
                """
                UPDATE calendar_sync_connections
                SET status='connected', disconnected_at=NULL, last_error=NULL, updated_at=now()
                WHERE company_code=%s AND connection_id=%s
                RETURNING *
                """,
                (company, connection_id),
            )
            updated = dict(cur.fetchone())
            _audit(
                cur,
                legacy,
                company_code=company,
                connection_id=connection_id,
                actor_user_id=actor_user_id,
                action="connection_reconnected",
                before={"status": row.get("status")},
                after={"status": "connected"},
            )
        conn.commit()
    # Repair: requeue current versions for existing bindings (no duplicate provider ids).
    repair = repair_connection_bindings(legacy, company_code=company, connection_id=connection_id)
    return {"ok": True, "connection": serialize_connection(updated, has_credentials=True), "repair": repair}


def update_connection_settings(
    legacy: Any,
    *,
    company_code: str,
    connection_id: str,
    actor_user_id: str | None = None,
    sync_event_types: Sequence[str] | None = None,
    sync_include_candidate_name: bool | None = None,
    external_calendar_id: str | None = None,
    with_meet_default: bool | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    company = _text(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            row = get_connection(cur, company_code=company, connection_id=connection_id)
            if not row:
                raise CalendarSyncError("connection_not_found", "Sync connection not found.", http_status=404)
            types = list(sync_event_types) if sync_event_types is not None else row.get("sync_event_types")
            include_name = (
                bool(sync_include_candidate_name)
                if sync_include_candidate_name is not None
                else bool(row.get("sync_include_candidate_name"))
            )
            cal_id = _text(external_calendar_id) if external_calendar_id is not None else _text(row.get("external_calendar_id")) or "primary"
            meet = bool(with_meet_default) if with_meet_default is not None else bool(row.get("with_meet_default"))
            name = display_name if display_name is not None else row.get("display_name")
            cur.execute(
                """
                UPDATE calendar_sync_connections
                SET sync_event_types=%s::jsonb, sync_include_candidate_name=%s,
                    external_calendar_id=%s, with_meet_default=%s, display_name=%s, updated_at=now()
                WHERE company_code=%s AND connection_id=%s
                RETURNING *
                """,
                (_json(legacy, types), include_name, cal_id, meet, name, company, connection_id),
            )
            updated = dict(cur.fetchone())
            _audit(
                cur,
                legacy,
                company_code=company,
                connection_id=connection_id,
                actor_user_id=actor_user_id,
                action="connection_settings_updated",
                before={},
                after={"sync_event_types": types, "sync_include_candidate_name": include_name},
            )
        conn.commit()
    return {"ok": True, "connection": serialize_connection(updated, has_credentials=bool(updated.get("has_credentials")))}


def _active_connections(cur: Any, company_code: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM calendar_sync_connections
        WHERE company_code=%s AND status='connected'
        """,
        (_text(company_code).upper(),),
    )
    return [dict(r) for r in cur.fetchall()]


def _event_eligible(event: Mapping[str, Any], connection: Mapping[str, Any]) -> bool:
    et = _text(event.get("event_type")).lower()
    allowed = connection.get("sync_event_types")
    if isinstance(allowed, str):
        try:
            import json

            allowed = json.loads(allowed)
        except Exception:
            allowed = list(DEFAULT_SYNC_EVENT_TYPES)
    if not isinstance(allowed, list):
        allowed = list(DEFAULT_SYNC_EVENT_TYPES)
    return et in {str(x).lower() for x in allowed}


def build_external_event_payload(
    legacy: Any,
    *,
    company_code: str,
    event: Mapping[str, Any],
    connection: Mapping[str, Any],
    guests: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Privacy-safe external projection. Candidate names hidden by default."""
    include_name = bool(connection.get("sync_include_candidate_name"))
    title = _text(event.get("title")) or "OctoHR event"
    et = _text(event.get("event_type")).lower()
    if et == "interview" and not include_name:
        # Strip guest display names; use limited title.
        title = _text(event.get("title_ar")) and title  # keep role/title as stored if already limited
        # Prefer generic label when guest names present in title — callers should store limited titles;
        # additionally force a safe prefix when guests exist.
        if guests:
            title = "Interview" if not include_name else title
            # If title looks like it embeds a person name from ensure, still allow stored title when
            # sync_include_candidate_name false only for interview type → use limited form.
            meta = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
            role_title = _text(meta.get("job_title") or meta.get("role_title"))
            title = role_title or "Interview"
    start = event.get("start_at")
    end = event.get("end_at")
    start_iso = start.isoformat() if hasattr(start, "isoformat") else _text(start)
    end_iso = end.isoformat() if hasattr(end, "isoformat") else _text(end)
    return {
        "event_id": str(event.get("event_id")),
        "summary": title,
        "description": _text(event.get("description")) if include_name else _text(event.get("description"))[:500],
        "location": _text(event.get("location")) or None,
        "start": start_iso,
        "end": end_iso,
        "timezone": _text(event.get("timezone")) or "Asia/Kuwait",
        "all_day": bool(event.get("all_day")),
        "with_meet": bool(connection.get("with_meet_default")) or bool(_text(event.get("meeting_url"))),
        "version": int(event.get("version") or 1),
    }


def enqueue_sync_for_event(
    cur: Any,
    legacy: Any,
    *,
    company_code: str,
    event_id: str,
    operation: str = "upsert",
) -> dict[str, Any]:
    """Enqueue sync intents for all active connections. Never mutates event truth."""
    company = _text(company_code).upper()
    op = _text(operation).lower()
    if op not in {"upsert", "cancel", "repair"}:
        op = "upsert"
    cur.execute(
        "SELECT * FROM calendar_events WHERE company_code=%s AND event_id=%s",
        (company, event_id),
    )
    event = cur.fetchone()
    if not event:
        return {"ok": False, "error": "event_not_found", "enqueued": 0}
    event = dict(event)
    version = int(event.get("version") or 1)
    if _text(event.get("status")).lower() == "cancelled":
        op = "cancel"
    connections = _active_connections(cur, company)
    enqueued = 0
    for conn in connections:
        if op != "cancel" and not _event_eligible(event, conn):
            continue
        connection_id = str(conn["connection_id"])
        # Coalesce: suppress older queued versions for same connection+event.
        cur.execute(
            """
            UPDATE calendar_sync_outbox
            SET status='suppressed', updated_at=now(), last_error='coalesced_newer_version'
            WHERE company_code=%s AND connection_id=%s AND event_id=%s
              AND status='queued' AND event_version < %s
            """,
            (company, connection_id, event_id, version),
        )
        key = f"sync:{connection_id}:{event_id}:{op}:v{version}"
        cur.execute(
            """
            INSERT INTO calendar_sync_outbox
              (outbox_id, company_code, connection_id, event_id, operation, event_version,
               idempotency_key, payload, status, next_attempt_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'queued',now())
            ON CONFLICT (company_code, idempotency_key) DO NOTHING
            RETURNING outbox_id
            """,
            (
                str(uuid4()),
                company,
                connection_id,
                event_id,
                op,
                version,
                key,
                _json(legacy, {"event_version": version}),
            ),
        )
        if cur.fetchone():
            enqueued += 1
            # Upsert binding status queued
            cur.execute(
                """
                INSERT INTO calendar_sync_bindings
                  (binding_id, company_code, event_id, connection_id, sync_status, last_pushed_version)
                VALUES (%s,%s,%s,%s,'queued',NULL)
                ON CONFLICT (connection_id, event_id) DO UPDATE
                  SET sync_status='queued', updated_at=now(),
                      last_error=NULL
                """,
                (str(uuid4()), company, event_id, connection_id),
            )
    return {"ok": True, "enqueued": enqueued, "operation": op, "event_version": version}


def enqueue_sync_for_event_tx(legacy: Any, *, company_code: str, event_id: str, operation: str = "upsert") -> dict[str, Any]:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            result = enqueue_sync_for_event(cur, legacy, company_code=company_code, event_id=event_id, operation=operation)
        conn.commit()
    return result


def claim_next_sync(cur: Any, *, worker_id: str, lease_seconds: int = 120) -> dict[str, Any] | None:
    cur.execute(
        """
        UPDATE calendar_sync_outbox
        SET status='queued', lease_owner=NULL, lease_expires_at=NULL, updated_at=now()
        WHERE status='processing' AND lease_expires_at IS NOT NULL AND lease_expires_at < now()
        """
    )
    cur.execute(
        """
        WITH next AS (
          SELECT outbox_id FROM calendar_sync_outbox
          WHERE status='queued' AND next_attempt_at <= now()
          ORDER BY next_attempt_at ASC
          FOR UPDATE SKIP LOCKED
          LIMIT 1
        )
        UPDATE calendar_sync_outbox o
        SET status='processing',
            lease_owner=%s,
            lease_expires_at=now() + make_interval(secs => %s),
            updated_at=now()
        FROM next
        WHERE o.outbox_id=next.outbox_id
        RETURNING o.*
        """,
        (worker_id, lease_seconds),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _prepare_connection_runtime(cur: Any, legacy: Any, connection: dict[str, Any]) -> dict[str, Any]:
    out = dict(connection)
    out["_legacy"] = legacy
    if _text(connection.get("mode")) == "legacy_operator":
        try:
            out["_legacy_account"] = _text((legacy.openclaw_env() or {}).get("GOG_ACCOUNT")) or _text(os.environ.get("GOG_ACCOUNT"))
        except Exception:
            out["_legacy_account"] = _text(os.environ.get("GOG_ACCOUNT"))
        return out

    # Prefer platform integration authority when linked.
    platform_id = _text(connection.get("platform_integration_id"))
    if platform_id:
        try:
            import platform_integrations as pi

            integ = pi.get_integration(cur, company_code=str(connection.get("company_code")), integration_id=platform_id)
            if integ and _text(integ.get("status")) == "connected":
                out["has_credentials"] = bool(integ.get("has_credentials"))
                out["_platform_integration"] = integ
                out["_connection_mode"] = _text(integ.get("connection_mode"))
                out["_impersonation_email"] = _text(integ.get("impersonation_email") or integ.get("account_email"))
                dry_run = _text(os.environ.get("CALENDAR_SYNC_DRY_RUN")).lower() in {"1", "true", "yes", "on"}
                if not dry_run:
                    try:
                        import platform_connection_c6 as c6

                        access = c6.mint_access_c6(legacy, cur, integ)
                        out["_access_token"] = access
                    except Exception:
                        try:
                            access = pi.mint_access_for_integration(legacy, cur, integ)
                            out["_access_token"] = access
                        except Exception as exc:
                            out["_token_error"] = str(exc)[:200]
                if _text(integ.get("provider_key")) == pi.PROVIDER_GOOGLE_WORKSPACE:
                    out["_refresh_token"] = pi.load_refresh_token(
                        cur, legacy, company_code=str(connection.get("company_code")), integration_id=platform_id
                    )
                return out
        except Exception as exc:
            out["_platform_error"] = str(exc)[:200]

    token = _load_refresh_token(cur, legacy, company_code=str(connection["company_code"]), connection_id=str(connection["connection_id"]))
    out["_refresh_token"] = token
    out["has_credentials"] = bool(token)
    return out


def _mint_access(legacy: Any, refresh_token: str | None) -> str | None:
    if not refresh_token:
        return None
    if hasattr(legacy, "mint_google_access_token"):
        return legacy.mint_google_access_token(refresh_token)
    return None


def process_sync_item(legacy: Any, cur: Any, item: Mapping[str, Any]) -> dict[str, Any]:
    """Process one sync outbox row. Provider failures never mutate Wathefni event rows."""
    outbox_id = str(item.get("outbox_id"))
    company = _text(item.get("company_code")).upper()
    connection_id = str(item.get("connection_id"))
    event_id = str(item.get("event_id"))
    operation = _text(item.get("operation"))
    event_version = int(item.get("event_version") or 0)

    conn_row = get_connection(cur, company_code=company, connection_id=connection_id)
    if not conn_row or _text(conn_row.get("status")) != "connected":
        cur.execute(
            """
            UPDATE calendar_sync_outbox
            SET status='cancelled', last_error='connection_not_active', updated_at=now(),
                lease_owner=NULL, lease_expires_at=NULL
            WHERE outbox_id=%s
            """,
            (outbox_id,),
        )
        return {"ok": True, "cancelled": True, "reason": "connection_not_active"}

    # Suppress stale: if a newer version was already queued/delivered, skip.
    cur.execute(
        """
        SELECT 1 FROM calendar_sync_outbox
        WHERE company_code=%s AND connection_id=%s AND event_id=%s
          AND event_version > %s
          AND status IN ('queued','processing','delivered')
        LIMIT 1
        """,
        (company, connection_id, event_id, event_version),
    )
    if cur.fetchone():
        cur.execute(
            """
            UPDATE calendar_sync_outbox
            SET status='suppressed', last_error='stale_version', updated_at=now(),
                lease_owner=NULL, lease_expires_at=NULL
            WHERE outbox_id=%s
            """,
            (outbox_id,),
        )
        return {"ok": True, "suppressed": True}

    cur.execute("SELECT * FROM calendar_events WHERE company_code=%s AND event_id=%s", (company, event_id))
    event = cur.fetchone()
    if not event:
        cur.execute(
            "UPDATE calendar_sync_outbox SET status='dead', last_error='event_missing', updated_at=now() WHERE outbox_id=%s",
            (outbox_id,),
        )
        return {"ok": False, "error": "event_missing"}
    event = dict(event)
    # Current event version may have moved; cancel ops still proceed.
    if operation != "cancel" and int(event.get("version") or 0) > event_version:
        cur.execute(
            """
            UPDATE calendar_sync_outbox
            SET status='suppressed', last_error='superseded_by_event_version', updated_at=now(),
                lease_owner=NULL, lease_expires_at=NULL
            WHERE outbox_id=%s
            """,
            (outbox_id,),
        )
        return {"ok": True, "suppressed": True}

    cur.execute(
        "SELECT * FROM calendar_sync_bindings WHERE company_code=%s AND connection_id=%s AND event_id=%s",
        (company, connection_id, event_id),
    )
    binding = cur.fetchone()
    binding = dict(binding) if binding else None

    cur.execute(
        "SELECT * FROM calendar_guests WHERE company_code=%s AND event_id=%s",
        (company, event_id),
    )
    guests = [dict(g) for g in cur.fetchall()]

    runtime_conn = _prepare_connection_runtime(cur, legacy, conn_row)
    adapter = get_adapter(_text(conn_row.get("provider_key")))
    access = runtime_conn.get("_access_token")
    dry_run = _text(os.environ.get("CALENDAR_SYNC_DRY_RUN")).lower() in {"1", "true", "yes", "on"}
    if _text(conn_row.get("mode")) == "company" and not access:
        # Prefer live token mint; dry-run adapters do not require a real access token.
        if runtime_conn.get("_token_error") and not dry_run:
            return _fail_sync(
                cur,
                legacy,
                item=item,
                binding=binding,
                error=f"token_refresh_failed:{runtime_conn.get('_token_error')}",
                company=company,
            )
        if not dry_run:
            try:
                access = _mint_access(legacy, runtime_conn.get("_refresh_token"))
            except Exception as exc:
                return _fail_sync(cur, legacy, item=item, binding=binding, error=f"token_refresh_failed:{exc}", company=company)
    # Microsoft uses bearer access_token; Google gog uses GOG_ACCESS_TOKEN via mint below.
    if _text(conn_row.get("provider_key")) in {"google", "google_workspace"} and runtime_conn.get("_refresh_token") and not access:
        try:
            access = _mint_access(legacy, runtime_conn.get("_refresh_token"))
        except Exception:
            access = None

    try:
        if operation == "cancel" or _text(event.get("status")).lower() == "cancelled":
            if not binding or not binding.get("provider_event_id"):
                # Nothing external to cancel.
                cur.execute(
                    """
                    UPDATE calendar_sync_outbox
                    SET status='delivered', updated_at=now(), lease_owner=NULL, lease_expires_at=NULL
                    WHERE outbox_id=%s
                    """,
                    (outbox_id,),
                )
                if binding:
                    cur.execute(
                        """
                        UPDATE calendar_sync_bindings
                        SET sync_status='synced', last_error=NULL, last_synced_at=now(), updated_at=now()
                        WHERE binding_id=%s
                        """,
                        (str(binding["binding_id"]),),
                    )
                return {"ok": True, "delivered": True, "skipped": True}
            result = adapter.cancel_event(connection=runtime_conn, binding=binding, legacy=legacy, access_token=access)  # type: ignore[call-arg]
        else:
            external = build_external_event_payload(
                legacy, company_code=company, event=event, connection=conn_row, guests=guests
            )
            result = adapter.upsert_event(  # type: ignore[call-arg]
                connection=runtime_conn,
                binding=binding,
                external_event=external,
                legacy=legacy,
                access_token=access,
            )
    except Exception as exc:
        return _fail_sync(cur, legacy, item=item, binding=binding, error=str(exc)[:300], company=company)

    if not result.get("ok"):
        return _fail_sync(
            cur,
            legacy,
            item=item,
            binding=binding,
            error=_text(result.get("error")) or "provider_failed",
            company=company,
        )

    provider_event_id = _text(result.get("provider_event_id")) or (binding or {}).get("provider_event_id")
    html_link = _text(result.get("external_html_link")) or (binding or {}).get("external_html_link")
    if binding:
        cur.execute(
            """
            UPDATE calendar_sync_bindings
            SET provider_event_id=%s, provider_calendar_id=%s, external_html_link=%s,
                sync_status='synced', last_pushed_version=%s, last_synced_at=now(),
                last_error=NULL, updated_at=now()
            WHERE binding_id=%s AND company_code=%s
            """,
            (
                provider_event_id,
                _text(conn_row.get("external_calendar_id")) or "primary",
                html_link,
                int(event.get("version") or event_version),
                str(binding["binding_id"]),
                company,
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO calendar_sync_bindings
              (binding_id, company_code, event_id, connection_id, provider_event_id,
               provider_calendar_id, external_html_link, sync_status, last_pushed_version, last_synced_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'synced',%s,now())
            ON CONFLICT (connection_id, event_id) DO UPDATE
              SET provider_event_id=COALESCE(EXCLUDED.provider_event_id, calendar_sync_bindings.provider_event_id),
                  external_html_link=COALESCE(EXCLUDED.external_html_link, calendar_sync_bindings.external_html_link),
                  sync_status='synced', last_pushed_version=EXCLUDED.last_pushed_version,
                  last_synced_at=now(), last_error=NULL, updated_at=now()
            """,
            (
                str(uuid4()),
                company,
                event_id,
                connection_id,
                provider_event_id,
                _text(conn_row.get("external_calendar_id")) or "primary",
                html_link,
                int(event.get("version") or event_version),
            ),
        )
    cur.execute(
        """
        UPDATE calendar_sync_outbox
        SET status='delivered', updated_at=now(), lease_owner=NULL, lease_expires_at=NULL, last_error=NULL
        WHERE outbox_id=%s
        """,
        (outbox_id,),
    )
    cur.execute(
        """
        UPDATE calendar_sync_connections
        SET last_sync_at=now(), last_error=NULL, health=%s::jsonb, updated_at=now()
        WHERE connection_id=%s AND company_code=%s
        """,
        (_json(legacy, {"ok": True, "last_outbox_id": outbox_id}), connection_id, company),
    )
    _audit(
        cur,
        legacy,
        company_code=company,
        connection_id=connection_id,
        event_id=event_id,
        action="sync_delivered",
        before={},
        after={"provider_event_id": provider_event_id, "operation": operation, "dry_run": bool(result.get("dry_run"))},
    )
    return {"ok": True, "delivered": True, "provider_event_id": provider_event_id, "dry_run": bool(result.get("dry_run"))}


def _fail_sync(
    cur: Any,
    legacy: Any,
    *,
    item: Mapping[str, Any],
    binding: Mapping[str, Any] | None,
    error: str,
    company: str,
) -> dict[str, Any]:
    outbox_id = str(item.get("outbox_id"))
    attempts = int(item.get("attempt_count") or 0) + 1
    dead = attempts >= 8
    delay = min(7200, 30 * (2 ** min(attempts, 6)))
    cur.execute(
        """
        UPDATE calendar_sync_outbox
        SET status=%s, attempt_count=%s, last_error=%s,
            next_attempt_at=now() + make_interval(secs => %s),
            lease_owner=NULL, lease_expires_at=NULL, updated_at=now()
        WHERE outbox_id=%s
        """,
        ("dead" if dead else "queued", attempts, error[:500], 0 if dead else delay, outbox_id),
    )
    if binding:
        cur.execute(
            """
            UPDATE calendar_sync_bindings
            SET sync_status='failed', last_error=%s, updated_at=now()
            WHERE binding_id=%s
            """,
            (error[:500], str(binding["binding_id"])),
        )
    cur.execute(
        """
        UPDATE calendar_sync_connections
        SET last_error=%s, health=%s::jsonb, updated_at=now()
        WHERE connection_id=%s AND company_code=%s
        """,
        (
            error[:500],
            _json(legacy, {"ok": False, "error": error[:200]}),
            str(item.get("connection_id")),
            company,
        ),
    )
    # Critical: do not touch calendar_events.
    return {"ok": False, "error": error, "dead": dead}


def run_sync_once(legacy: Any, *, limit: int = 50, worker_id: str | None = None) -> dict[str, Any]:
    wid = worker_id or f"calendar-sync:{os.getpid()}"
    processed = 0
    results: list[dict[str, Any]] = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            for _ in range(max(1, int(limit))):
                item = claim_next_sync(cur, worker_id=wid)
                if not item:
                    break
                results.append(process_sync_item(legacy, cur, item))
                processed += 1
                conn.commit()
        conn.commit()
    return {"ok": True, "processed": processed, "results": results}


def bindings_for_event(legacy: Any, *, company_code: str, event_id: str) -> list[dict[str, Any]]:
    company = _text(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            cur.execute(
                """
                SELECT b.*, c.provider_key, c.mode, c.status AS connection_status, c.account_email
                FROM calendar_sync_bindings b
                JOIN calendar_sync_connections c ON c.connection_id=b.connection_id
                WHERE b.company_code=%s AND b.event_id=%s
                ORDER BY b.updated_at DESC
                """,
                (company, event_id),
            )
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    out = []
    for r in rows:
        base = serialize_binding(r) or {}
        base["provider_key"] = _text(r.get("provider_key"))
        base["connection_mode"] = _text(r.get("mode"))
        base["connection_status"] = _text(r.get("connection_status"))
        base["account_email"] = _text(r.get("account_email")) or None
        out.append(base)
    return out


def public_event_sync_status(bindings: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Customer-facing sync status — no provider keys, errors, links, or IDs."""
    statuses = [_text(b.get("sync_status")).lower() for b in (bindings or []) if isinstance(b, Mapping)]
    if any(s == "synced" for s in statuses):
        customer_status = "synced"
    elif any(s in {"queued", "pending", "syncing"} for s in statuses):
        customer_status = "pending"
    elif statuses:
        customer_status = "unavailable"
    else:
        customer_status = None
    return {"customer_status": customer_status}


def retry_binding(
    legacy: Any,
    *,
    company_code: str,
    event_id: str,
    connection_id: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    company = _text(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            result = enqueue_sync_for_event(cur, legacy, company_code=company, event_id=event_id, operation="upsert")
            if connection_id:
                # If specific connection requested, still ok — enqueue filters active.
                pass
            _audit(
                cur,
                legacy,
                company_code=company,
                connection_id=connection_id,
                event_id=event_id,
                actor_user_id=actor_user_id,
                action="sync_retry_requested",
                before={},
                after=result,
            )
        conn.commit()
    return {"ok": True, **result}


def repair_connection_bindings(legacy: Any, *, company_code: str, connection_id: str) -> dict[str, Any]:
    """Requeue upsert for all bindings on reconnect — same provider_event_id, no duplicates."""
    company = _text(company_code).upper()
    repaired = 0
    event_ids: list[str] = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            cur.execute(
                """
                SELECT event_id FROM calendar_sync_bindings
                WHERE company_code=%s AND connection_id=%s
                """,
                (company, connection_id),
            )
            event_ids = [str(r["event_id"]) for r in cur.fetchall()]
            for eid in event_ids:
                r = enqueue_sync_for_event(cur, legacy, company_code=company, event_id=eid, operation="repair")
                repaired += int(r.get("enqueued") or 0)
        conn.commit()
    return {"ok": True, "repaired": repaired, "events": len(event_ids)}


def backfill_legacy_google_bindings(
    legacy: Any,
    *,
    company_code: str,
    dry_run: bool = True,
    limit: int = 200,
    resume_after_event_id: str | None = None,
) -> dict[str, Any]:
    """Tenant-scoped, resumable backfill of legacy Google IDs into sync bindings.

    Sources:
    - calendar_events.metadata.legacy_operator_calendar.provider_event_id
    - candidate_interviews.calendar_event_id when linked to native calendar events
    Does not create duplicate external events; only records bindings.
    """
    company = _text(company_code).upper()
    ensured = ensure_legacy_operator_connection(legacy, company_code=company)
    connection_id = (ensured.get("connection") or {}).get("connection_id")
    if not connection_id:
        return {"ok": False, "error": "legacy_connection_missing"}
    scanned = 0
    bound = 0
    skipped = 0
    last_id = resume_after_event_id
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            params: list[Any] = [company]
            clause = ""
            if resume_after_event_id:
                clause = " AND e.event_id > %s"
                params.append(resume_after_event_id)
            params.append(int(limit))
            cur.execute(
                f"""
                SELECT e.event_id, e.metadata, e.version
                FROM calendar_events e
                WHERE e.company_code=%s {clause}
                ORDER BY e.event_id ASC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = [dict(r) for r in cur.fetchall()]
            for row in rows:
                scanned += 1
                last_id = str(row["event_id"])
                meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                legacy_blob = meta.get("legacy_operator_calendar") if isinstance(meta.get("legacy_operator_calendar"), dict) else {}
                provider_event_id = _text(legacy_blob.get("provider_event_id"))
                if not provider_event_id:
                    # Try interview link
                    cur.execute(
                        """
                        SELECT i.calendar_event_id
                        FROM calendar_event_links l
                        JOIN candidate_interviews i
                          ON i.interview_id::text = l.source_record_id
                         AND i.company_code = l.company_code
                        WHERE l.company_code=%s AND l.event_id=%s AND l.source_workflow='interview'
                          AND l.link_status='active'
                        LIMIT 1
                        """,
                        (company, str(row["event_id"])),
                    )
                    ir = cur.fetchone()
                    if ir:
                        provider_event_id = _text(ir.get("calendar_event_id"))
                        # Skip if it looks like a UUID (native) rather than Google id
                        if len(provider_event_id) == 36 and provider_event_id.count("-") == 4:
                            provider_event_id = ""
                if not provider_event_id:
                    skipped += 1
                    continue
                if dry_run:
                    bound += 1
                    continue
                cur.execute(
                    """
                    INSERT INTO calendar_sync_bindings
                      (binding_id, company_code, event_id, connection_id, provider_event_id,
                       provider_calendar_id, sync_status, last_pushed_version, last_synced_at, metadata)
                    VALUES (%s,%s,%s,%s,%s,'primary','synced',%s,now(),%s::jsonb)
                    ON CONFLICT (connection_id, event_id) DO UPDATE
                      SET provider_event_id=COALESCE(calendar_sync_bindings.provider_event_id, EXCLUDED.provider_event_id),
                          sync_status='synced', updated_at=now()
                    """,
                    (
                        str(uuid4()),
                        company,
                        str(row["event_id"]),
                        connection_id,
                        provider_event_id,
                        int(row.get("version") or 1),
                        _json(legacy, {"source": "legacy_backfill"}),
                    ),
                )
                bound += 1
            if not dry_run:
                _audit(
                    cur,
                    legacy,
                    company_code=company,
                    connection_id=connection_id,
                    action="legacy_backfill",
                    before={},
                    after={"scanned": scanned, "bound": bound, "skipped": skipped, "resume_after": last_id},
                )
        conn.commit()
    return {
        "ok": True,
        "dry_run": dry_run,
        "company_code": company,
        "connection_id": connection_id,
        "scanned": scanned,
        "bound": bound,
        "skipped": skipped,
        "resume_after_event_id": last_id,
    }
