"""Platform company integrations — shared connection authority (C5).

Owns company-level connections for Google Workspace and Microsoft 365:
connection, credential, consent scopes, account, health, audit.

Calendar is the first consumer (calendar.events + meetings.create).
Future capabilities (SSO, directory, email, files) are reserved in the
capability registry but not implemented here.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from uuid import uuid4

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PROVIDER_GOOGLE_WORKSPACE = "google_workspace"
PROVIDER_MICROSOFT_365 = "microsoft_365"

PROVIDERS = frozenset({PROVIDER_GOOGLE_WORKSPACE, PROVIDER_MICROSOFT_365})

# Implemented in this wave (Calendar consumer).
CAPABILITY_CALENDAR_EVENTS = "calendar.events"
CAPABILITY_MEETINGS_CREATE = "meetings.create"

# Reserved for future modules — registered but never granted/executed in C5.
CAPABILITY_SSO = "identity.sso"
CAPABILITY_DIRECTORY = "directory.read"
CAPABILITY_EMAIL = "email.send"
CAPABILITY_FILES = "files.readwrite"

IMPLEMENTED_CAPABILITIES = frozenset({CAPABILITY_CALENDAR_EVENTS, CAPABILITY_MEETINGS_CREATE})
RESERVED_CAPABILITIES = frozenset({CAPABILITY_SSO, CAPABILITY_DIRECTORY, CAPABILITY_EMAIL, CAPABILITY_FILES})
ALL_CAPABILITIES = IMPLEMENTED_CAPABILITIES | RESERVED_CAPABILITIES

GOOGLE_WORKSPACE_CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
    "openid",
    "email",
    "profile",
)

# Graph application scopes for calendar + Teams online meetings (delegated).
MICROSOFT_365_CALENDAR_SCOPES = (
    "offline_access",
    "openid",
    "profile",
    "email",
    "Calendars.ReadWrite",
    "OnlineMeetings.ReadWrite.All",
    "User.Read",
)

DEFAULT_CAPABILITIES_BY_PROVIDER = {
    PROVIDER_GOOGLE_WORKSPACE: [CAPABILITY_CALENDAR_EVENTS, CAPABILITY_MEETINGS_CREATE],
    PROVIDER_MICROSOFT_365: [CAPABILITY_CALENDAR_EVENTS, CAPABILITY_MEETINGS_CREATE],
}


class PlatformIntegrationError(Exception):
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


def ensure_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_company_integrations (
          integration_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          provider_key text NOT NULL,
          status text NOT NULL DEFAULT 'not_connected',
          account_email text,
          external_tenant_id text,
          display_name text,
          granted_scopes jsonb NOT NULL DEFAULT '[]'::jsonb,
          capabilities jsonb NOT NULL DEFAULT '[]'::jsonb,
          consent_at timestamptz,
          consent_actor_user_id text,
          health jsonb NOT NULL DEFAULT '{}'::jsonb,
          last_error text,
          last_verified_at timestamptz,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          disconnected_at timestamptz,
          CONSTRAINT platform_integrations_provider_chk CHECK (
            provider_key IN ('google_workspace','microsoft_365')
          ),
          CONSTRAINT platform_integrations_status_chk CHECK (
            status IN ('not_connected','connected','error','disconnected','consent_required')
          )
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_platform_integrations_active
          ON platform_company_integrations (company_code, provider_key)
          WHERE status <> 'disconnected';
        CREATE INDEX IF NOT EXISTS idx_platform_integrations_company
          ON platform_company_integrations (company_code, status);

        CREATE TABLE IF NOT EXISTS platform_company_integration_credentials (
          credential_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          integration_id uuid NOT NULL REFERENCES platform_company_integrations(integration_id) ON DELETE CASCADE,
          company_code text NOT NULL,
          secret_type text NOT NULL DEFAULT 'refresh_token',
          ciphertext text NOT NULL,
          key_version text NOT NULL,
          alg text NOT NULL DEFAULT 'fernet',
          token_meta jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (integration_id, secret_type)
        );
        CREATE INDEX IF NOT EXISTS idx_platform_integration_creds_company
          ON platform_company_integration_credentials (company_code, integration_id);

        CREATE TABLE IF NOT EXISTS platform_company_integration_audit (
          audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          integration_id uuid,
          actor_user_id text,
          action text NOT NULL,
          before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          after_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_platform_integration_audit_company
          ON platform_company_integration_audit (company_code, created_at DESC);
        """
    )
    # Calendar sync link to platform authority (additive).
    cur.execute(
        """
        ALTER TABLE IF EXISTS calendar_sync_connections
          ADD COLUMN IF NOT EXISTS platform_integration_id uuid;
        CREATE INDEX IF NOT EXISTS idx_calendar_sync_conn_platform
          ON calendar_sync_connections (platform_integration_id)
          WHERE platform_integration_id IS NOT NULL;
        """
    )
    try:
        import platform_connection_c6 as c6

        c6.ensure_c6_schema(cur)
    except Exception:
        pass


def ensure_schema_tx(legacy: Any) -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
        conn.commit()


def _audit(cur: Any, legacy: Any, **kwargs: Any) -> None:
    cur.execute(
        """
        INSERT INTO platform_company_integration_audit
          (audit_id, company_code, integration_id, actor_user_id, action, before_json, after_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            str(uuid4()),
            _text(kwargs.get("company_code")).upper(),
            kwargs.get("integration_id"),
            kwargs.get("actor_user_id"),
            _text(kwargs.get("action")),
            _json(legacy, kwargs.get("before") or {}),
            _json(legacy, kwargs.get("after") or {}),
        ),
    )


def serialize_integration(row: Mapping[str, Any] | None, *, has_credentials: bool = False) -> dict[str, Any] | None:
    if not row:
        return None
    caps = row.get("capabilities")
    if isinstance(caps, str):
        try:
            caps = json.loads(caps)
        except Exception:
            caps = []
    scopes = row.get("granted_scopes")
    if isinstance(scopes, str):
        try:
            scopes = json.loads(scopes)
        except Exception:
            scopes = []
    return {
        "integration_id": str(row.get("integration_id")),
        "company_code": _text(row.get("company_code")).upper(),
        "provider_key": _text(row.get("provider_key")),
        "status": _text(row.get("status")),
        "account_email": _text(row.get("account_email")) or None,
        "external_tenant_id": _text(row.get("external_tenant_id")) or None,
        "display_name": _text(row.get("display_name")) or None,
        "granted_scopes": list(scopes or []),
        "capabilities": list(caps or []),
        "implemented_capabilities": sorted(IMPLEMENTED_CAPABILITIES & set(caps or [])),
        "reserved_capabilities_noted": sorted(RESERVED_CAPABILITIES),
        "consent_at": row.get("consent_at").isoformat() if hasattr(row.get("consent_at"), "isoformat") else row.get("consent_at"),
        "health": row.get("health") if isinstance(row.get("health"), dict) else {},
        "last_error": _text(row.get("last_error")) or None,
        "last_verified_at": row.get("last_verified_at").isoformat() if hasattr(row.get("last_verified_at"), "isoformat") else row.get("last_verified_at"),
        "has_credentials": bool(has_credentials),
        "disconnected_at": row.get("disconnected_at").isoformat() if hasattr(row.get("disconnected_at"), "isoformat") else row.get("disconnected_at"),
        "created_at": row.get("created_at").isoformat() if hasattr(row.get("created_at"), "isoformat") else row.get("created_at"),
        "updated_at": row.get("updated_at").isoformat() if hasattr(row.get("updated_at"), "isoformat") else row.get("updated_at"),
    }


def capability_registry() -> dict[str, Any]:
    return {
        "implemented": sorted(IMPLEMENTED_CAPABILITIES),
        "reserved_future": sorted(RESERVED_CAPABILITIES),
        "providers": {
            PROVIDER_GOOGLE_WORKSPACE: {
                "label": "Google Workspace",
                "default_capabilities": DEFAULT_CAPABILITIES_BY_PROVIDER[PROVIDER_GOOGLE_WORKSPACE],
                "calendar": "Google Calendar",
                "meetings": "Google Meet",
            },
            PROVIDER_MICROSOFT_365: {
                "label": "Microsoft 365",
                "default_capabilities": DEFAULT_CAPABILITIES_BY_PROVIDER[PROVIDER_MICROSOFT_365],
                "calendar": "Outlook / Microsoft Graph Calendar",
                "meetings": "Microsoft Teams",
            },
        },
    }


def list_integrations(legacy: Any, *, company_code: str) -> list[dict[str, Any]]:
    company = _text(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT i.*,
                       EXISTS(
                         SELECT 1 FROM platform_company_integration_credentials c
                         WHERE c.integration_id=i.integration_id
                       ) AS has_credentials
                FROM platform_company_integrations i
                WHERE i.company_code=%s
                ORDER BY i.created_at ASC
                """,
                (company,),
            )
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    return [serialize_integration(r, has_credentials=bool(r.get("has_credentials"))) or {} for r in rows]


def get_integration(cur: Any, *, company_code: str, integration_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT i.*,
               EXISTS(
                 SELECT 1 FROM platform_company_integration_credentials c
                 WHERE c.integration_id=i.integration_id
               ) AS has_credentials
        FROM platform_company_integrations i
        WHERE i.company_code=%s AND i.integration_id=%s
        LIMIT 1
        """,
        (_text(company_code).upper(), integration_id),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def get_active_integration(cur: Any, *, company_code: str, provider_key: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT i.*,
               EXISTS(
                 SELECT 1 FROM platform_company_integration_credentials c
                 WHERE c.integration_id=i.integration_id
               ) AS has_credentials
        FROM platform_company_integrations i
        WHERE i.company_code=%s AND i.provider_key=%s AND i.status='connected'
        ORDER BY i.updated_at DESC LIMIT 1
        """,
        (_text(company_code).upper(), _text(provider_key)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _store_refresh_token(cur: Any, legacy: Any, *, company_code: str, integration_id: str, refresh_token: str, meta: Mapping[str, Any] | None = None) -> None:
    if not hasattr(legacy, "encrypt_sensitive_text"):
        raise PlatformIntegrationError("encryption_unavailable", "Credential encryption is not configured.", http_status=503)
    enc = legacy.encrypt_sensitive_text(refresh_token)
    cur.execute(
        """
        INSERT INTO platform_company_integration_credentials
          (credential_id, integration_id, company_code, secret_type, ciphertext, key_version, alg, token_meta, updated_at)
        VALUES (%s,%s,%s,'refresh_token',%s,%s,%s,%s,now())
        ON CONFLICT (integration_id, secret_type) DO UPDATE
          SET ciphertext=EXCLUDED.ciphertext,
              key_version=EXCLUDED.key_version,
              alg=EXCLUDED.alg,
              token_meta=EXCLUDED.token_meta,
              updated_at=now()
        """,
        (
            str(uuid4()),
            integration_id,
            _text(company_code).upper(),
            enc["ciphertext"],
            enc["key_version"],
            enc.get("alg") or "fernet",
            _json(legacy, dict(meta or {})),
        ),
    )


def load_refresh_token(cur: Any, legacy: Any, *, company_code: str, integration_id: str) -> str | None:
    cur.execute(
        """
        SELECT ciphertext FROM platform_company_integration_credentials
        WHERE company_code=%s AND integration_id=%s AND secret_type='refresh_token'
        LIMIT 1
        """,
        (_text(company_code).upper(), integration_id),
    )
    row = cur.fetchone()
    if not row or not hasattr(legacy, "decrypt_sensitive_text"):
        return None
    return legacy.decrypt_sensitive_text(row["ciphertext"])


def _normalize_capabilities(provider_key: str, capabilities: Sequence[str] | None) -> list[str]:
    requested = [ _text(c) for c in (capabilities or DEFAULT_CAPABILITIES_BY_PROVIDER.get(provider_key) or []) if _text(c) ]
    # Never silently grant reserved future capabilities.
    return [c for c in requested if c in IMPLEMENTED_CAPABILITIES]


def connect_provider(
    legacy: Any,
    *,
    company_code: str,
    provider_key: str,
    account_email: str,
    refresh_token: str,
    actor_user_id: str | None = None,
    granted_scopes: Sequence[str] | None = None,
    capabilities: Sequence[str] | None = None,
    external_tenant_id: str | None = None,
    display_name: str | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Upsert a company-owned provider connection. Credentials never leave ciphertext store."""
    company = _text(company_code).upper()
    provider = _text(provider_key).lower()
    email = _text(account_email).lower()
    token = _text(refresh_token)
    if provider not in PROVIDERS:
        raise PlatformIntegrationError("unsupported_provider", f"Provider {provider} is not supported.")
    if not company or not email or not token:
        raise PlatformIntegrationError("missing_fields", "account_email and refresh_token are required.")
    if not hasattr(legacy, "encrypt_sensitive_text"):
        raise PlatformIntegrationError("encryption_unavailable", "Set WATHEFNI_MAILBOX_SECRET_KEY before connecting.", http_status=503)

    caps = _normalize_capabilities(provider, capabilities)
    scopes = list(granted_scopes or (
        GOOGLE_WORKSPACE_CALENDAR_SCOPES if provider == PROVIDER_GOOGLE_WORKSPACE else MICROSOFT_365_CALENDAR_SCOPES
    ))

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT integration_id FROM platform_company_integrations
                WHERE company_code=%s AND provider_key=%s AND status IN ('connected','error','not_connected','consent_required')
                ORDER BY updated_at DESC LIMIT 1
                """,
                (company, provider),
            )
            existing = cur.fetchone()
            if existing:
                integration_id = str(existing["integration_id"])
                cur.execute(
                    """
                    UPDATE platform_company_integrations
                    SET status='connected', account_email=%s, external_tenant_id=%s, display_name=%s,
                        granted_scopes=%s::jsonb, capabilities=%s::jsonb,
                        consent_at=now(), consent_actor_user_id=%s,
                        last_error=NULL, disconnected_at=NULL, last_verified_at=now(),
                        health=%s::jsonb, updated_at=now()
                    WHERE company_code=%s AND integration_id=%s
                    RETURNING *
                    """,
                    (
                        email,
                        _text(external_tenant_id) or None,
                        display_name or email,
                        _json(legacy, scopes),
                        _json(legacy, caps),
                        actor_user_id,
                        _json(legacy, {"ok": True, "verified": bool(access_token)}),
                        company,
                        integration_id,
                    ),
                )
                row = dict(cur.fetchone())
            else:
                integration_id = str(uuid4())
                cur.execute(
                    """
                    INSERT INTO platform_company_integrations
                      (integration_id, company_code, provider_key, status, account_email, external_tenant_id,
                       display_name, granted_scopes, capabilities, consent_at, consent_actor_user_id,
                       health, last_verified_at)
                    VALUES (%s,%s,%s,'connected',%s,%s,%s,%s::jsonb,%s::jsonb,now(),%s,%s::jsonb,now())
                    RETURNING *
                    """,
                    (
                        integration_id,
                        company,
                        provider,
                        email,
                        _text(external_tenant_id) or None,
                        display_name or email,
                        _json(legacy, scopes),
                        _json(legacy, caps),
                        actor_user_id,
                        _json(legacy, {"ok": True, "verified": bool(access_token)}),
                    ),
                )
                row = dict(cur.fetchone())
            _store_refresh_token(
                cur,
                legacy,
                company_code=company,
                integration_id=integration_id,
                refresh_token=token,
                meta={"provider": provider, "scopes": scopes},
            )
            _audit(
                cur,
                legacy,
                company_code=company,
                integration_id=integration_id,
                actor_user_id=actor_user_id,
                action="integration_connected",
                before={},
                after={"provider_key": provider, "account_email": email, "capabilities": caps},
            )
        conn.commit()
    return {"ok": True, "integration": serialize_integration(row, has_credentials=True)}


def disconnect_integration(
    legacy: Any,
    *,
    company_code: str,
    integration_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    company = _text(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                UPDATE platform_company_integrations
                SET status='disconnected', disconnected_at=now(), updated_at=now()
                WHERE company_code=%s AND integration_id=%s
                RETURNING *
                """,
                (company, integration_id),
            )
            row = cur.fetchone()
            if not row:
                raise PlatformIntegrationError("integration_not_found", "Integration not found.", http_status=404)
            # Detach calendar sync connections that pointed here (stop pushes; keep Wathefni truth).
            cur.execute(
                """
                UPDATE calendar_sync_connections
                SET status='disconnected', disconnected_at=now(), updated_at=now(), last_error='platform_integration_disconnected'
                WHERE company_code=%s AND platform_integration_id=%s AND status='connected'
                """,
                (company, integration_id),
            )
            _audit(
                cur,
                legacy,
                company_code=company,
                integration_id=integration_id,
                actor_user_id=actor_user_id,
                action="integration_disconnected",
                before={},
                after={"status": "disconnected"},
            )
        conn.commit()
    return {"ok": True, "integration": serialize_integration(dict(row))}


def has_capability(integration: Mapping[str, Any], capability: str) -> bool:
    caps = integration.get("capabilities") or []
    if isinstance(caps, str):
        try:
            caps = json.loads(caps)
        except Exception:
            caps = []
    return _text(capability) in {str(c) for c in caps} and _text(capability) in IMPLEMENTED_CAPABILITIES


# ---------------------------------------------------------------------------
# OAuth config + token mint
# ---------------------------------------------------------------------------


def google_workspace_oauth_config() -> dict[str, str]:
    # Prefer dedicated workspace client; fall back to Gmail OAuth client.
    return {
        "client_id": (
            _text(os.environ.get("WATHEFNI_GOOGLE_WORKSPACE_CLIENT_ID"))
            or _text(os.environ.get("WATHEFNI_GMAIL_CLIENT_ID"))
        ),
        "client_secret": (
            _text(os.environ.get("WATHEFNI_GOOGLE_WORKSPACE_CLIENT_SECRET"))
            or _text(os.environ.get("WATHEFNI_GMAIL_CLIENT_SECRET"))
        ),
        "redirect_uri": (
            _text(os.environ.get("WATHEFNI_GOOGLE_WORKSPACE_REDIRECT_URI"))
            or _text(os.environ.get("WATHEFNI_GMAIL_REDIRECT_URI"))
        ),
    }


def microsoft_365_oauth_config() -> dict[str, str]:
    tenant = _text(os.environ.get("WATHEFNI_M365_TENANT_ID")) or "common"
    return {
        "client_id": _text(os.environ.get("WATHEFNI_M365_CLIENT_ID")),
        "client_secret": _text(os.environ.get("WATHEFNI_M365_CLIENT_SECRET")),
        "redirect_uri": _text(os.environ.get("WATHEFNI_M365_REDIRECT_URI")),
        "tenant_id": tenant,
        "token_uri": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        "auth_uri": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
    }


def mint_google_workspace_access_token(legacy: Any, refresh_token: str) -> str:
    if hasattr(legacy, "mint_google_access_token"):
        # Reuses same Google token endpoint; client must match the refresh token issuer.
        return legacy.mint_google_access_token(refresh_token)
    cfg = google_workspace_oauth_config()
    if not (cfg["client_id"] and cfg["client_secret"]):
        raise PlatformIntegrationError("google_oauth_not_configured", "Google OAuth client is not configured.", http_status=503)
    body = urllib.parse.urlencode(
        {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("ascii")
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise PlatformIntegrationError("google_token_failed", str(exc)[:200], http_status=502) from exc
    token = data.get("access_token")
    if not token:
        raise PlatformIntegrationError("google_token_missing", "Google access token missing.", http_status=502)
    return str(token)


def mint_microsoft_365_access_token(refresh_token: str) -> str:
    cfg = microsoft_365_oauth_config()
    if not (cfg["client_id"] and cfg["client_secret"]):
        raise PlatformIntegrationError("m365_oauth_not_configured", "Microsoft 365 OAuth client is not configured.", http_status=503)
    body = urllib.parse.urlencode(
        {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": " ".join(MICROSOFT_365_CALENDAR_SCOPES),
        }
    ).encode("ascii")
    req = urllib.request.Request(cfg["token_uri"], data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise PlatformIntegrationError("m365_token_failed", f"microsoft_token_failed:{exc.code}", http_status=502) from exc
    except Exception as exc:
        raise PlatformIntegrationError("m365_token_error", str(exc)[:200], http_status=502) from exc
    token = data.get("access_token")
    if not token:
        raise PlatformIntegrationError("m365_token_missing", "Microsoft access token missing.", http_status=502)
    return str(token)


def mint_access_for_integration(legacy: Any, cur: Any, integration: Mapping[str, Any]) -> str | None:
    mode = _text(integration.get("connection_mode"))
    if mode in {"enterprise_app", "enterprise_dwd"}:
        import platform_connection_c6 as c6

        return c6.mint_access_c6(legacy, cur, integration)
    provider = _text(integration.get("provider_key"))
    token = load_refresh_token(
        cur,
        legacy,
        company_code=str(integration.get("company_code")),
        integration_id=str(integration.get("integration_id")),
    )
    if not token:
        return None
    if provider == PROVIDER_GOOGLE_WORKSPACE:
        return mint_google_workspace_access_token(legacy, token)
    if provider == PROVIDER_MICROSOFT_365:
        return mint_microsoft_365_access_token(token)
    return None


def attach_calendar_sync_connection(
    legacy: Any,
    *,
    company_code: str,
    integration_id: str,
    actor_user_id: str | None = None,
    external_calendar_id: str = "primary",
    with_meet_default: bool = True,
) -> dict[str, Any]:
    """Create/link a calendar_sync_connections row that consumes this platform integration."""
    import calendar_schema
    import calendar_sync as csync

    company = _text(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            calendar_schema.ensure_calendar_schema(cur)
            integ = get_integration(cur, company_code=company, integration_id=integration_id)
            if not integ or _text(integ.get("status")) != "connected":
                raise PlatformIntegrationError("integration_not_connected", "Platform integration must be connected.", http_status=409)
            if not has_capability(integ, CAPABILITY_CALENDAR_EVENTS):
                raise PlatformIntegrationError("capability_missing", "calendar.events capability is required.")

            provider = _text(integ.get("provider_key"))
            sync_provider = "google" if provider == PROVIDER_GOOGLE_WORKSPACE else "microsoft"
            meet = bool(with_meet_default) and has_capability(integ, CAPABILITY_MEETINGS_CREATE)
            policy = csync.calendar_policy(legacy, company)

            cur.execute(
                """
                SELECT connection_id FROM calendar_sync_connections
                WHERE company_code=%s AND platform_integration_id=%s
                ORDER BY updated_at DESC LIMIT 1
                """,
                (company, integration_id),
            )
            existing = cur.fetchone()
            if existing:
                connection_id = str(existing["connection_id"])
                cur.execute(
                    """
                    UPDATE calendar_sync_connections
                    SET status='connected', provider_key=%s, mode='company',
                        account_email=%s, external_calendar_id=%s,
                        display_name=%s, sync_event_types=%s::jsonb,
                        sync_include_candidate_name=%s, with_meet_default=%s,
                        credentials_ref=%s, last_error=NULL, disconnected_at=NULL, updated_at=now()
                    WHERE company_code=%s AND connection_id=%s
                    RETURNING *
                    """,
                    (
                        sync_provider,
                        integ.get("account_email"),
                        _text(external_calendar_id) or "primary",
                        integ.get("display_name") or integ.get("account_email"),
                        _json(legacy, policy["sync_event_types"]),
                        bool(policy["sync_include_candidate_name"]),
                        meet,
                        f"platform:{integration_id}",
                        company,
                        connection_id,
                    ),
                )
                row = dict(cur.fetchone())
            else:
                connection_id = str(uuid4())
                cur.execute(
                    """
                    INSERT INTO calendar_sync_connections
                      (connection_id, company_code, provider_key, mode, status, credentials_ref,
                       account_email, external_calendar_id, display_name, sync_event_types,
                       sync_include_candidate_name, with_meet_default, platform_integration_id)
                    VALUES (%s,%s,%s,'company','connected',%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                    RETURNING *
                    """,
                    (
                        connection_id,
                        company,
                        sync_provider,
                        f"platform:{integration_id}",
                        integ.get("account_email"),
                        _text(external_calendar_id) or "primary",
                        integ.get("display_name") or integ.get("account_email"),
                        _json(legacy, policy["sync_event_types"]),
                        bool(policy["sync_include_candidate_name"]),
                        meet,
                        integration_id,
                    ),
                )
                row = dict(cur.fetchone())
            _audit(
                cur,
                legacy,
                company_code=company,
                integration_id=integration_id,
                actor_user_id=actor_user_id,
                action="calendar_sync_attached",
                before={},
                after={"connection_id": connection_id, "provider_key": sync_provider},
            )
        conn.commit()
    return {"ok": True, "connection": csync.serialize_connection(row, has_credentials=True), "integration_id": integration_id}
