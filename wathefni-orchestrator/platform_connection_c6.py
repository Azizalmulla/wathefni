"""Calendar C6 — enterprise + OAuth connection modes on platform integrations.

Modes:
  microsoft_365:
    - enterprise_app  — Entra app-only (client secret or certificate)
    - oauth_delegated — admin OAuth for smaller companies
  google_workspace:
    - enterprise_dwd  — service account + domain-wide delegation + impersonation
    - oauth_delegated — company-admin OAuth for smaller companies

No refresh-token paste in product UX — OAuth uses authorize/callback;
enterprise modes use guided IT credential forms (secret/cert/SA JSON).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence
from uuid import uuid4

import platform_integrations as pi

MODE_ENTERPRISE_APP = "enterprise_app"
MODE_ENTERPRISE_DWD = "enterprise_dwd"
MODE_OAUTH_DELEGATED = "oauth_delegated"

CONNECTION_MODES = frozenset({MODE_ENTERPRISE_APP, MODE_ENTERPRISE_DWD, MODE_OAUTH_DELEGATED})

# Application permissions for Graph app-only Calendar + Teams.
MICROSOFT_365_APP_SCOPES = (
    "https://graph.microsoft.com/.default",
)
MICROSOFT_365_APP_PERMISSIONS = (
    # Calendar CRUD is granted via Exchange RBACfA (Application Calendars.ReadWrite + AU),
    # not tenant-wide Calendars.ReadWrite Graph app role.
    "OnlineMeetings.ReadWrite.All",
)

GOOGLE_DWD_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
)

SECRET_REFRESH = "refresh_token"
SECRET_CLIENT = "client_secret"
SECRET_CERT = "certificate_pem"
SECRET_SA = "service_account_json"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(legacy: Any, value: Any) -> Any:
    if hasattr(legacy, "Json"):
        return legacy.Json(value if value is not None else {})
    return value if value is not None else {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_c6_schema(cur: Any) -> None:
    """Additive columns for C6 connection modes + reliability.

    Caller must already have created base platform_company_integrations tables
    (via platform_integrations.ensure_schema DDL portion).
    """
    cur.execute(
        """
        ALTER TABLE IF EXISTS platform_company_integrations
          ADD COLUMN IF NOT EXISTS connection_mode text,
          ADD COLUMN IF NOT EXISTS impersonation_email text,
          ADD COLUMN IF NOT EXISTS credential_expires_at timestamptz,
          ADD COLUMN IF NOT EXISTS reconnect_required boolean NOT NULL DEFAULT false,
          ADD COLUMN IF NOT EXISTS setup_progress jsonb NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS last_health_at timestamptz,
          ADD COLUMN IF NOT EXISTS expiry_notified_at timestamptz;
        """
    )
    # Expand status check to include reconnect_required (idempotent).
    try:
        cur.execute(
            """
            SELECT pg_get_constraintdef(oid) AS def
            FROM pg_constraint
            WHERE conrelid = 'platform_company_integrations'::regclass
              AND conname = 'platform_integrations_status_chk'
            LIMIT 1
            """
        )
        row = cur.fetchone()
        defn = str((row["def"] if isinstance(row, dict) else (row[0] if row else "")) or "")
        if "reconnect_required" not in defn:
            cur.execute("ALTER TABLE platform_company_integrations DROP CONSTRAINT IF EXISTS platform_integrations_status_chk")
            cur.execute(
                """
                ALTER TABLE platform_company_integrations
                  ADD CONSTRAINT platform_integrations_status_chk CHECK (
                    status IN ('not_connected','connected','error','disconnected','consent_required','reconnect_required')
                  )
                """
            )
    except Exception:
        pass
    # Expand status check to include reconnect_required (idempotent).
    cur.execute(
        """
        SELECT pg_get_constraintdef(oid) AS def
        FROM pg_constraint
        WHERE conrelid = 'platform_company_integrations'::regclass
          AND conname = 'platform_integrations_status_chk'
        LIMIT 1
        """
    )
    row = cur.fetchone()
    defn = str((row["def"] if isinstance(row, dict) else (row[0] if row else "")) or "")
    if "reconnect_required" not in defn:
        cur.execute("ALTER TABLE platform_company_integrations DROP CONSTRAINT IF EXISTS platform_integrations_status_chk")
        cur.execute(
            """
            ALTER TABLE platform_company_integrations
              ADD CONSTRAINT platform_integrations_status_chk CHECK (
                status IN ('not_connected','connected','error','disconnected','consent_required','reconnect_required')
              )
            """
        )


def connection_mode_catalog() -> dict[str, Any]:
    return {
        "providers": {
            pi.PROVIDER_MICROSOFT_365: {
                "label": "Microsoft 365",
                "modes": [
                    {
                        "mode": MODE_ENTERPRISE_APP,
                        "label": "Enterprise IT-managed connection",
                        "description": "Admin-consented Entra application. App-only Graph access — no employee must stay signed in.",
                        "auth": "client_credentials",
                        "credential_options": ["client_secret", "certificate"],
                    },
                    {
                        "mode": MODE_OAUTH_DELEGATED,
                        "label": "Simple OAuth connection",
                        "description": "Company admin signs in once with Microsoft. Best for smaller companies.",
                        "auth": "authorization_code",
                    },
                ],
            },
            pi.PROVIDER_GOOGLE_WORKSPACE: {
                "label": "Google Workspace",
                "modes": [
                    {
                        "mode": MODE_ENTERPRISE_DWD,
                        "label": "Enterprise IT-managed connection",
                        "description": "Service account with domain-wide delegation. Impersonates an approved calendar identity (e.g. hr@company.com). The service account does not own customer calendar data.",
                        "auth": "service_account_dwd",
                    },
                    {
                        "mode": MODE_OAUTH_DELEGATED,
                        "label": "Simple OAuth connection",
                        "description": "Company admin consents Google Calendar + Meet. Best for smaller companies.",
                        "auth": "authorization_code",
                    },
                ],
            },
        },
        "oauth_ready": {
            "google_workspace": google_oauth_ready(),
            "microsoft_365": microsoft_oauth_ready(),
        },
        "enterprise_ready": {
            "microsoft_365_app": True,  # company supplies tenant + client credentials
            "google_workspace_dwd": True,
        },
    }


def setup_checklist(*, provider_key: str, mode: str) -> dict[str, Any]:
    provider = _text(provider_key).lower()
    m = _text(mode).lower()
    if provider == pi.PROVIDER_MICROSOFT_365 and m == MODE_ENTERPRISE_APP:
        return {
            "provider_key": provider,
            "mode": m,
            "required_admin_role": "Global Administrator or Application Administrator (Microsoft Entra)",
            "steps": [
                {"id": "create_app", "title": "Register Wathefni enterprise app in Entra ID", "required": True},
                {
                    "id": "app_permissions",
                    "title": "Grant application permissions",
                    "detail": ", ".join(MICROSOFT_365_APP_PERMISSIONS),
                    "required": True,
                },
                {"id": "admin_consent", "title": "Grant tenant-wide admin consent", "required": True},
                {
                    "id": "credential",
                    "title": "Create client secret or upload certificate",
                    "detail": "Prefer certificate rotation for production.",
                    "required": True,
                },
                {
                    "id": "calendar_identity",
                    "title": "Choose mailbox / calendar identity (UPN)",
                    "detail": "e.g. hr@company.com — app acts as this user via Graph /users/{upn}",
                    "required": True,
                },
                {"id": "tenant_id", "title": "Confirm Microsoft tenant ID (Directory ID)", "required": True},
                {"id": "validate", "title": "Validate connection health in Wathefni", "required": True},
            ],
            "permissions": list(MICROSOFT_365_APP_PERMISSIONS),
            "scopes": list(MICROSOFT_365_APP_SCOPES),
        }
    if provider == pi.PROVIDER_MICROSOFT_365 and m == MODE_OAUTH_DELEGATED:
        return {
            "provider_key": provider,
            "mode": m,
            "required_admin_role": "Company Microsoft 365 admin (or user with Calendar + Meetings consent)",
            "steps": [
                {"id": "start_oauth", "title": "Click Connect with Microsoft", "required": True},
                {"id": "consent", "title": "Approve Calendar and Teams meeting permissions", "required": True},
                {"id": "validate", "title": "Wathefni verifies token and calendar access", "required": True},
            ],
            "permissions": list(pi.MICROSOFT_365_CALENDAR_SCOPES),
            "scopes": list(pi.MICROSOFT_365_CALENDAR_SCOPES),
        }
    if provider == pi.PROVIDER_GOOGLE_WORKSPACE and m == MODE_ENTERPRISE_DWD:
        return {
            "provider_key": provider,
            "mode": m,
            "required_admin_role": "Google Workspace Super Admin",
            "steps": [
                {"id": "create_sa", "title": "Create a Google Cloud service account for Wathefni", "required": True},
                {
                    "id": "enable_dwd",
                    "title": "Enable domain-wide delegation on the service account",
                    "required": True,
                },
                {
                    "id": "admin_console",
                    "title": "In Google Admin → Security → API controls → Domain-wide delegation, add the SA client ID",
                    "detail": f"OAuth scopes: {' '.join(GOOGLE_DWD_SCOPES)}",
                    "required": True,
                },
                {
                    "id": "impersonation",
                    "title": "Choose approved calendar identity to impersonate",
                    "detail": "e.g. hr@company.com — SA never owns customer calendars",
                    "required": True,
                },
                {"id": "upload_json", "title": "Upload service account JSON key in Wathefni", "required": True},
                {"id": "validate", "title": "Validate connection health in Wathefni", "required": True},
            ],
            "permissions": list(GOOGLE_DWD_SCOPES),
            "scopes": list(GOOGLE_DWD_SCOPES),
        }
    if provider == pi.PROVIDER_GOOGLE_WORKSPACE and m == MODE_OAUTH_DELEGATED:
        return {
            "provider_key": provider,
            "mode": m,
            "required_admin_role": "Google Workspace admin or calendar owner",
            "steps": [
                {"id": "start_oauth", "title": "Click Connect with Google", "required": True},
                {"id": "consent", "title": "Approve Google Calendar + Meet scopes", "required": True},
                {"id": "validate", "title": "Wathefni verifies token and calendar access", "required": True},
            ],
            "permissions": list(pi.GOOGLE_WORKSPACE_CALENDAR_SCOPES),
            "scopes": list(pi.GOOGLE_WORKSPACE_CALENDAR_SCOPES),
        }
    raise pi.PlatformIntegrationError("unsupported_mode", f"No checklist for {provider}/{m}")


def google_oauth_ready() -> bool:
    cfg = pi.google_workspace_oauth_config()
    return bool(cfg.get("client_id") and cfg.get("client_secret") and cfg.get("redirect_uri"))


def microsoft_oauth_ready() -> bool:
    cfg = pi.microsoft_365_oauth_config()
    return bool(cfg.get("client_id") and cfg.get("client_secret") and cfg.get("redirect_uri"))


def _store_secret(
    cur: Any,
    legacy: Any,
    *,
    company_code: str,
    integration_id: str,
    secret_type: str,
    plaintext: str,
    meta: Mapping[str, Any] | None = None,
) -> None:
    if not hasattr(legacy, "encrypt_sensitive_text"):
        raise pi.PlatformIntegrationError("encryption_unavailable", "Credential encryption is not configured.", http_status=503)
    enc = legacy.encrypt_sensitive_text(plaintext)
    cur.execute(
        """
        INSERT INTO platform_company_integration_credentials
          (credential_id, integration_id, company_code, secret_type, ciphertext, key_version, alg, token_meta, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now())
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
            secret_type,
            enc["ciphertext"],
            enc["key_version"],
            enc.get("alg") or "fernet",
            _json(legacy, dict(meta or {})),
        ),
    )


def _load_secret(cur: Any, legacy: Any, *, company_code: str, integration_id: str, secret_type: str) -> str | None:
    cur.execute(
        """
        SELECT ciphertext, token_meta FROM platform_company_integration_credentials
        WHERE company_code=%s AND integration_id=%s AND secret_type=%s
        LIMIT 1
        """,
        (_text(company_code).upper(), integration_id, secret_type),
    )
    row = cur.fetchone()
    if not row or not hasattr(legacy, "decrypt_sensitive_text"):
        return None
    return legacy.decrypt_sensitive_text(row["ciphertext"])


def _load_secret_meta(cur: Any, *, company_code: str, integration_id: str, secret_type: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT token_meta FROM platform_company_integration_credentials
        WHERE company_code=%s AND integration_id=%s AND secret_type=%s
        LIMIT 1
        """,
        (_text(company_code).upper(), integration_id, secret_type),
    )
    row = cur.fetchone()
    if not row:
        return {}
    meta = row["token_meta"] if isinstance(row, dict) else row[0]
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    return dict(meta or {}) if isinstance(meta, dict) else {}


def _upsert_integration_row(
    cur: Any,
    legacy: Any,
    *,
    company: str,
    provider: str,
    mode: str,
    account_email: str,
    actor_user_id: str | None,
    external_tenant_id: str | None,
    display_name: str | None,
    impersonation_email: str | None,
    scopes: Sequence[str],
    caps: Sequence[str],
    health: Mapping[str, Any],
    credential_expires_at: datetime | None,
    setup_progress: Mapping[str, Any] | None,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT integration_id FROM platform_company_integrations
        WHERE company_code=%s AND provider_key=%s
          AND status IN ('connected','error','not_connected','consent_required','reconnect_required')
        ORDER BY updated_at DESC LIMIT 1
        """,
        (company, provider),
    )
    existing = cur.fetchone()
    email = _text(account_email).lower()
    if existing:
        integration_id = str(existing["integration_id"])
        cur.execute(
            """
            UPDATE platform_company_integrations
            SET status='connected', connection_mode=%s, account_email=%s, external_tenant_id=%s,
                display_name=%s, impersonation_email=%s,
                granted_scopes=%s::jsonb, capabilities=%s::jsonb,
                consent_at=now(), consent_actor_user_id=%s,
                last_error=NULL, disconnected_at=NULL, reconnect_required=false,
                last_verified_at=now(), last_health_at=now(),
                health=%s::jsonb, credential_expires_at=%s,
                setup_progress=%s::jsonb, updated_at=now()
            WHERE company_code=%s AND integration_id=%s
            RETURNING *
            """,
            (
                mode,
                email,
                _text(external_tenant_id) or None,
                display_name or email,
                _text(impersonation_email).lower() or None,
                _json(legacy, list(scopes)),
                _json(legacy, list(caps)),
                actor_user_id,
                _json(legacy, dict(health)),
                credential_expires_at,
                _json(legacy, dict(setup_progress or {})),
                company,
                integration_id,
            ),
        )
        return dict(cur.fetchone())
    integration_id = str(uuid4())
    cur.execute(
        """
        INSERT INTO platform_company_integrations
          (integration_id, company_code, provider_key, status, connection_mode, account_email,
           external_tenant_id, display_name, impersonation_email, granted_scopes, capabilities,
           consent_at, consent_actor_user_id, health, last_verified_at, last_health_at,
           credential_expires_at, setup_progress, reconnect_required)
        VALUES (%s,%s,%s,'connected',%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,now(),%s,%s::jsonb,now(),now(),%s,%s::jsonb,false)
        RETURNING *
        """,
        (
            integration_id,
            company,
            provider,
            mode,
            email,
            _text(external_tenant_id) or None,
            display_name or email,
            _text(impersonation_email).lower() or None,
            _json(legacy, list(scopes)),
            _json(legacy, list(caps)),
            actor_user_id,
            _json(legacy, dict(health)),
            credential_expires_at,
            _json(legacy, dict(setup_progress or {})),
        ),
    )
    return dict(cur.fetchone())


def connect_microsoft_enterprise_app(
    legacy: Any,
    *,
    company_code: str,
    tenant_id: str,
    client_id: str,
    calendar_identity: str,
    actor_user_id: str | None = None,
    client_secret: str | None = None,
    certificate_pem: str | None = None,
    certificate_thumbprint: str | None = None,
    display_name: str | None = None,
    credential_expires_at: str | None = None,
    validate: bool = True,
    dry_run_accept: bool = False,
) -> dict[str, Any]:
    """Entra app-only connection. Does not depend on an employee remaining signed in."""
    company = _text(company_code).upper()
    tenant = _text(tenant_id)
    cid = _text(client_id)
    identity = _text(calendar_identity).lower()
    secret = _text(client_secret)
    cert = _text(certificate_pem)
    if not (company and tenant and cid and identity):
        raise pi.PlatformIntegrationError("missing_fields", "tenant_id, client_id, and calendar_identity are required.")
    if not secret and not cert:
        raise pi.PlatformIntegrationError("missing_credential", "Provide client_secret or certificate_pem.")
    if not hasattr(legacy, "encrypt_sensitive_text"):
        raise pi.PlatformIntegrationError("encryption_unavailable", "Set WATHEFNI_MAILBOX_SECRET_KEY.", http_status=503)

    expires = None
    if credential_expires_at:
        try:
            expires = datetime.fromisoformat(credential_expires_at.replace("Z", "+00:00"))
        except Exception:
            expires = _now() + timedelta(days=180)
    elif secret:
        expires = _now() + timedelta(days=180)  # default warning horizon for secrets

    access = None
    verified = False
    if validate and not dry_run_accept:
        try:
            access = mint_microsoft_app_token(tenant_id=tenant, client_id=cid, client_secret=secret or None, certificate_pem=cert or None)
            verified = bool(access)
        except pi.PlatformIntegrationError:
            if not dry_run_accept:
                raise
    elif dry_run_accept:
        verified = False

    caps = [pi.CAPABILITY_CALENDAR_EVENTS, pi.CAPABILITY_MEETINGS_CREATE]
    checklist = setup_checklist(provider_key=pi.PROVIDER_MICROSOFT_365, mode=MODE_ENTERPRISE_APP)
    progress = {s["id"]: "done" for s in checklist["steps"]}

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_c6_schema(cur)
            row = _upsert_integration_row(
                cur,
                legacy,
                company=company,
                provider=pi.PROVIDER_MICROSOFT_365,
                mode=MODE_ENTERPRISE_APP,
                account_email=identity,
                actor_user_id=actor_user_id,
                external_tenant_id=tenant,
                display_name=display_name or f"M365 enterprise ({identity})",
                impersonation_email=identity,
                scopes=MICROSOFT_365_APP_SCOPES,
                caps=caps,
                health={
                    "ok": True,
                    "verified": verified,
                    "mode": MODE_ENTERPRISE_APP,
                    "auth": "client_credentials",
                    "calendar_identity": identity,
                    "credential_kind": "certificate" if cert else "client_secret",
                },
                credential_expires_at=expires,
                setup_progress=progress,
            )
            integration_id = str(row["integration_id"])
            # Store platform client id in metadata (non-secret); secret/cert encrypted.
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            meta = dict(meta or {})
            meta.update({"entra_client_id": cid, "certificate_thumbprint": _text(certificate_thumbprint) or None})
            if cert:
                try:
                    cert_meta = microsoft_certificate_metadata(cert)
                    meta["certificate_thumbprint"] = _text(certificate_thumbprint) or cert_meta.get("thumbprint_sha1_hex")
                    meta["certificate_x5t"] = cert_meta.get("x5t")
                    meta["certificate_x5t_s256"] = cert_meta.get("x5t#S256")
                    meta["certificate_subject"] = cert_meta.get("subject")
                    meta["certificate_not_valid_after"] = cert_meta.get("not_valid_after")
                except pi.PlatformIntegrationError:
                    if validate and not dry_run_accept:
                        raise
                    # dry_run_accept may use placeholder PEM; skip metadata
                    pass
            cur.execute(
                "UPDATE platform_company_integrations SET metadata=%s::jsonb, updated_at=now() WHERE integration_id=%s",
                (_json(legacy, meta), integration_id),
            )
            if secret:
                _store_secret(
                    cur,
                    legacy,
                    company_code=company,
                    integration_id=integration_id,
                    secret_type=SECRET_CLIENT,
                    plaintext=json.dumps({"client_id": cid, "client_secret": secret, "tenant_id": tenant}),
                    meta={"kind": "client_secret", "expires_at": expires.isoformat() if expires else None},
                )
            if cert:
                _store_secret(
                    cur,
                    legacy,
                    company_code=company,
                    integration_id=integration_id,
                    secret_type=SECRET_CERT,
                    plaintext=json.dumps(
                        {
                            "client_id": cid,
                            "tenant_id": tenant,
                            "certificate_pem": cert,
                            "thumbprint": meta.get("certificate_thumbprint") or _text(certificate_thumbprint),
                        }
                    ),
                    meta={
                        "kind": "certificate",
                        "expires_at": expires.isoformat() if expires else None,
                        "thumbprint": meta.get("certificate_thumbprint"),
                        "x5t": meta.get("certificate_x5t"),
                    },
                )
            pi._audit(
                cur,
                legacy,
                company_code=company,
                integration_id=integration_id,
                actor_user_id=actor_user_id,
                action="microsoft_enterprise_app_connected",
                before={},
                after={"mode": MODE_ENTERPRISE_APP, "tenant_id": tenant, "identity": identity, "verified": verified},
            )
            cur.execute("SELECT * FROM platform_company_integrations WHERE integration_id=%s", (integration_id,))
            row = dict(cur.fetchone())
        conn.commit()

    attached = pi.attach_calendar_sync_connection(
        legacy,
        company_code=company,
        integration_id=str(row["integration_id"]),
        actor_user_id=actor_user_id,
        external_calendar_id="calendar",
        with_meet_default=True,
    )
    return {
        "ok": True,
        "integration": serialize_c6(row, has_credentials=True),
        "connection": attached.get("connection"),
        "checklist": checklist,
    }


def connect_google_enterprise_dwd(
    legacy: Any,
    *,
    company_code: str,
    service_account_json: str | Mapping[str, Any],
    impersonation_email: str,
    actor_user_id: str | None = None,
    display_name: str | None = None,
    validate: bool = True,
    dry_run_accept: bool = False,
) -> dict[str, Any]:
    """Google Workspace DWD — impersonate approved calendar identity; SA does not own data."""
    company = _text(company_code).upper()
    identity = _text(impersonation_email).lower()
    if not company or not identity:
        raise pi.PlatformIntegrationError("missing_fields", "impersonation_email is required.")
    if isinstance(service_account_json, Mapping):
        sa_obj = dict(service_account_json)
        sa_text = json.dumps(sa_obj)
    else:
        sa_text = _text(service_account_json)
        try:
            sa_obj = json.loads(sa_text)
        except Exception as exc:
            raise pi.PlatformIntegrationError("invalid_service_account_json", "Service account JSON is invalid.") from exc
    if not sa_obj.get("client_email") or not sa_obj.get("private_key"):
        raise pi.PlatformIntegrationError("invalid_service_account_json", "JSON must include client_email and private_key.")
    if not hasattr(legacy, "encrypt_sensitive_text"):
        raise pi.PlatformIntegrationError("encryption_unavailable", "Set WATHEFNI_MAILBOX_SECRET_KEY.", http_status=503)

    verified = False
    if validate and not dry_run_accept:
        access = mint_google_dwd_token(sa_obj, impersonation_email=identity)
        verified = bool(access)
    elif dry_run_accept:
        verified = False

    caps = [pi.CAPABILITY_CALENDAR_EVENTS, pi.CAPABILITY_MEETINGS_CREATE]
    checklist = setup_checklist(provider_key=pi.PROVIDER_GOOGLE_WORKSPACE, mode=MODE_ENTERPRISE_DWD)
    progress = {s["id"]: "done" for s in checklist["steps"]}

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_c6_schema(cur)
            row = _upsert_integration_row(
                cur,
                legacy,
                company=company,
                provider=pi.PROVIDER_GOOGLE_WORKSPACE,
                mode=MODE_ENTERPRISE_DWD,
                account_email=identity,
                actor_user_id=actor_user_id,
                external_tenant_id=_text(sa_obj.get("project_id")) or None,
                display_name=display_name or f"Google Workspace ({identity})",
                impersonation_email=identity,
                scopes=GOOGLE_DWD_SCOPES,
                caps=caps,
                health={
                    "ok": True,
                    "verified": verified,
                    "mode": MODE_ENTERPRISE_DWD,
                    "auth": "service_account_dwd",
                    "impersonation_email": identity,
                    "service_account_email": sa_obj.get("client_email"),
                    "owns_customer_data": False,
                },
                credential_expires_at=None,  # SA keys typically long-lived; rotation is manual
                setup_progress=progress,
            )
            integration_id = str(row["integration_id"])
            meta = dict(row.get("metadata") or {}) if isinstance(row.get("metadata"), dict) else {}
            meta.update(
                {
                    "service_account_email": sa_obj.get("client_email"),
                    "sa_client_id": sa_obj.get("client_id"),
                    "owns_customer_data": False,
                }
            )
            cur.execute(
                "UPDATE platform_company_integrations SET metadata=%s::jsonb, updated_at=now() WHERE integration_id=%s",
                (_json(legacy, meta), integration_id),
            )
            _store_secret(
                cur,
                legacy,
                company_code=company,
                integration_id=integration_id,
                secret_type=SECRET_SA,
                plaintext=sa_text,
                meta={"kind": "service_account_json", "client_email": sa_obj.get("client_email")},
            )
            pi._audit(
                cur,
                legacy,
                company_code=company,
                integration_id=integration_id,
                actor_user_id=actor_user_id,
                action="google_enterprise_dwd_connected",
                before={},
                after={"mode": MODE_ENTERPRISE_DWD, "impersonation_email": identity, "verified": verified},
            )
            cur.execute("SELECT * FROM platform_company_integrations WHERE integration_id=%s", (integration_id,))
            row = dict(cur.fetchone())
        conn.commit()

    attached = pi.attach_calendar_sync_connection(
        legacy,
        company_code=company,
        integration_id=str(row["integration_id"]),
        actor_user_id=actor_user_id,
        external_calendar_id="primary",
        with_meet_default=True,
    )
    return {
        "ok": True,
        "integration": serialize_c6(row, has_credentials=True),
        "connection": attached.get("connection"),
        "checklist": checklist,
    }


def serialize_c6(row: Mapping[str, Any] | None, *, has_credentials: bool = False) -> dict[str, Any] | None:
    base = pi.serialize_integration(row, has_credentials=has_credentials)
    if not base or not row:
        return base
    expires = row.get("credential_expires_at")
    expires_iso = expires.isoformat() if hasattr(expires, "isoformat") else expires
    days_left = None
    warning = None
    if expires is not None and hasattr(expires, "tzinfo"):
        delta = expires - _now()
        days_left = int(delta.total_seconds() // 86400)
        if days_left <= 14:
            warning = "credential_expiring_soon"
        if days_left < 0:
            warning = "credential_expired"
    base.update(
        {
            "connection_mode": _text(row.get("connection_mode")) or None,
            "impersonation_email": _text(row.get("impersonation_email")) or None,
            "reconnect_required": bool(row.get("reconnect_required")) or _text(row.get("status")) == "reconnect_required",
            "credential_expires_at": expires_iso,
            "credential_days_remaining": days_left,
            "expiry_warning": warning,
            "setup_progress": row.get("setup_progress") if isinstance(row.get("setup_progress"), dict) else {},
            "last_health_at": row.get("last_health_at").isoformat()
            if hasattr(row.get("last_health_at"), "isoformat")
            else row.get("last_health_at"),
        }
    )
    return base


# ---------------------------------------------------------------------------
# Token mint — app-only / DWD
# ---------------------------------------------------------------------------


def mint_microsoft_app_token(
    *,
    tenant_id: str,
    client_id: str,
    client_secret: str | None = None,
    certificate_pem: str | None = None,
) -> str:
    tenant = _text(tenant_id) or "common"
    token_uri = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    if certificate_pem:
        # Certificate JWT client assertion — require cryptography if available.
        assertion = _microsoft_cert_assertion(tenant_id=tenant, client_id=client_id, certificate_pem=certificate_pem)
        form = {
            "client_id": client_id,
            "scope": " ".join(MICROSOFT_365_APP_SCOPES),
            "grant_type": "client_credentials",
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": assertion,
        }
    else:
        if not client_secret:
            raise pi.PlatformIntegrationError("m365_secret_missing", "client_secret required for app-only secret auth.")
        form = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": " ".join(MICROSOFT_365_APP_SCOPES),
            "grant_type": "client_credentials",
        }
    body = urllib.parse.urlencode(form).encode("ascii")
    req = urllib.request.Request(token_uri, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise pi.PlatformIntegrationError("m365_app_token_failed", f"microsoft_app_token_failed:{exc.code}", http_status=502) from exc
    except Exception as exc:
        raise pi.PlatformIntegrationError("m365_app_token_error", str(exc)[:200], http_status=502) from exc
    token = data.get("access_token")
    if not token:
        raise pi.PlatformIntegrationError("m365_app_token_missing", "Microsoft app access token missing.", http_status=502)
    return str(token)


def _b64url_json(obj: Any) -> str:
    raw = json.dumps(obj, separators=(",", ":")).encode("utf-8") if not isinstance(obj, (bytes, bytearray)) else obj
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_bytes(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def parse_microsoft_certificate_pem(certificate_pem: str) -> dict[str, Any]:
    """Parse a Wathefni Microsoft cert bundle.

    Required PEM contents (either order):
      - one X.509 public certificate (BEGIN CERTIFICATE)
      - one unencrypted private key (BEGIN PRIVATE KEY / RSA PRIVATE KEY / EC PRIVATE KEY)

    Public-only .cer/.crt must never be uploaded here — Entra gets the public cert;
    Wathefni stores the private key + matching public cert so client assertions can
    include Microsoft-required ``x5t`` / ``x5t#S256`` thumbprints.
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
    except Exception as exc:
        raise pi.PlatformIntegrationError("cryptography_unavailable", "Certificate auth requires cryptography package.", http_status=503) from exc

    pem = _text(certificate_pem)
    if not pem:
        raise pi.PlatformIntegrationError("certificate_pem_missing", "certificate_pem is required.")

    # Extract first certificate block.
    cert = None
    if "BEGIN CERTIFICATE" in pem:
        try:
            cert = x509.load_pem_x509_certificate(pem.encode("utf-8"))
        except Exception as exc:
            raise pi.PlatformIntegrationError("certificate_pem_invalid", "Could not parse X.509 certificate from PEM.", http_status=422) from exc
    if cert is None:
        raise pi.PlatformIntegrationError(
            "certificate_public_missing",
            "certificate_pem must include the public X.509 certificate (BEGIN CERTIFICATE) so Wathefni can set x5t/x5t#S256.",
            http_status=422,
        )

    try:
        key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    except Exception as exc:
        raise pi.PlatformIntegrationError(
            "certificate_private_missing",
            "certificate_pem must include an unencrypted private key matching the public certificate.",
            http_status=422,
        ) from exc

    # Ensure key matches certificate public key (prevent wrong-bundle mistakes).
    try:
        cert_pub = cert.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        key_pub = key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        if cert_pub != key_pub:
            raise pi.PlatformIntegrationError(
                "certificate_key_mismatch",
                "Private key does not match the public certificate in certificate_pem.",
                http_status=422,
            )
    except pi.PlatformIntegrationError:
        raise
    except Exception as exc:
        raise pi.PlatformIntegrationError("certificate_key_check_failed", str(exc)[:200], http_status=422) from exc

    der = cert.public_bytes(serialization.Encoding.DER)
    sha1 = hashes.Hash(hashes.SHA1())
    sha1.update(der)
    sha1_digest = sha1.finalize()
    sha256 = hashes.Hash(hashes.SHA256())
    sha256.update(der)
    sha256_digest = sha256.finalize()
    return {
        "certificate": cert,
        "private_key": key,
        "der": der,
        "x5t": _b64url_bytes(sha1_digest),
        "x5t_s256": _b64url_bytes(sha256_digest),
        "thumbprint_sha1_hex": sha1_digest.hex().upper(),
        "thumbprint_sha256_hex": sha256_digest.hex().upper(),
        "not_valid_before": cert.not_valid_before_utc.isoformat() if hasattr(cert, "not_valid_before_utc") else None,
        "not_valid_after": cert.not_valid_after_utc.isoformat() if hasattr(cert, "not_valid_after_utc") else None,
        "subject": cert.subject.rfc4514_string(),
    }


def microsoft_certificate_metadata(certificate_pem: str) -> dict[str, Any]:
    """Safe metadata for audits/UI — never includes private key material."""
    parsed = parse_microsoft_certificate_pem(certificate_pem)
    return {
        "x5t": parsed["x5t"],
        "x5t#S256": parsed["x5t_s256"],
        "thumbprint_sha1_hex": parsed["thumbprint_sha1_hex"],
        "thumbprint_sha256_hex": parsed["thumbprint_sha256_hex"],
        "not_valid_before": parsed.get("not_valid_before"),
        "not_valid_after": parsed.get("not_valid_after"),
        "subject": parsed.get("subject"),
    }


def _microsoft_cert_assertion(*, tenant_id: str, client_id: str, certificate_pem: str) -> str:
    """Build an Entra client_assertion JWT for certificate credentials.

    Microsoft identity platform requires a certificate thumbprint in the JWT header
    (``x5t`` and/or ``x5t#S256``). Assertions without these are rejected.
    Signing uses RS256 + PKCS#1 v1.5, matching MSAL / Azure.Identity CertificateCredential.
    """
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
    except Exception as exc:
        raise pi.PlatformIntegrationError("cryptography_unavailable", "Certificate auth requires cryptography package.", http_status=503) from exc

    parsed = parse_microsoft_certificate_pem(certificate_pem)
    key = parsed["private_key"]
    now = int(time.time())
    # Include both legacy SHA-1 x5t (widely required) and SHA-256 x5t#S256 (current docs).
    header = {
        "alg": "RS256",
        "typ": "JWT",
        "x5t": parsed["x5t"],
        "x5t#S256": parsed["x5t_s256"],
    }
    payload = {
        "aud": f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        "iss": client_id,
        "sub": client_id,
        "jti": str(uuid4()),
        "nbf": now,
        "iat": now,
        "exp": now + 600,
    }

    signing_input = f"{_b64url_json(header)}.{_b64url_json(payload)}".encode("ascii")
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input.decode('ascii')}.{_b64url_bytes(signature)}"

def mint_google_dwd_token(sa: Mapping[str, Any], *, impersonation_email: str, scopes: Sequence[str] | None = None) -> str:
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except Exception as exc:
        raise pi.PlatformIntegrationError("cryptography_unavailable", "DWD requires cryptography package.", http_status=503) from exc

    email = _text(impersonation_email).lower()
    client_email = _text(sa.get("client_email"))
    private_key_pem = _text(sa.get("private_key"))
    if not (email and client_email and private_key_pem):
        raise pi.PlatformIntegrationError("dwd_incomplete", "Service account and impersonation email required.")
    scope = " ".join(scopes or GOOGLE_DWD_SCOPES)
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claim = {
        "iss": client_email,
        "sub": email,
        "scope": scope,
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    segments = b64url(json.dumps(header, separators=(",", ":")).encode()) + "." + b64url(json.dumps(claim, separators=(",", ":")).encode())
    key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    sig = key.sign(segments.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    assertion = segments + "." + b64url(sig)
    body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}).encode("ascii")
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise pi.PlatformIntegrationError("google_dwd_token_failed", f"google_dwd_failed:{exc.code}", http_status=502) from exc
    token = data.get("access_token")
    if not token:
        raise pi.PlatformIntegrationError("google_dwd_token_missing", "Google DWD access token missing.", http_status=502)
    return str(token)


def mint_access_c6(legacy: Any, cur: Any, integration: Mapping[str, Any]) -> str | None:
    """Mint access for any C6 connection mode."""
    mode = _text(integration.get("connection_mode")) or MODE_OAUTH_DELEGATED
    provider = _text(integration.get("provider_key"))
    company = str(integration.get("company_code"))
    iid = str(integration.get("integration_id"))

    if provider == pi.PROVIDER_MICROSOFT_365 and mode == MODE_ENTERPRISE_APP:
        blob = _load_secret(cur, legacy, company_code=company, integration_id=iid, secret_type=SECRET_CLIENT)
        if blob:
            data = json.loads(blob)
            return mint_microsoft_app_token(
                tenant_id=data.get("tenant_id") or integration.get("external_tenant_id"),
                client_id=data.get("client_id"),
                client_secret=data.get("client_secret"),
            )
        cert_blob = _load_secret(cur, legacy, company_code=company, integration_id=iid, secret_type=SECRET_CERT)
        if cert_blob:
            data = json.loads(cert_blob)
            return mint_microsoft_app_token(
                tenant_id=data.get("tenant_id") or integration.get("external_tenant_id"),
                client_id=data.get("client_id"),
                certificate_pem=data.get("certificate_pem"),
            )
        return None

    if provider == pi.PROVIDER_GOOGLE_WORKSPACE and mode == MODE_ENTERPRISE_DWD:
        sa_text = _load_secret(cur, legacy, company_code=company, integration_id=iid, secret_type=SECRET_SA)
        if not sa_text:
            return None
        sa = json.loads(sa_text)
        return mint_google_dwd_token(sa, impersonation_email=_text(integration.get("impersonation_email") or integration.get("account_email")))

    # Delegated OAuth — reuse C5 refresh path.
    return pi.mint_access_for_integration(legacy, cur, integration)


# ---------------------------------------------------------------------------
# OAuth start / complete (no refresh-token paste)
# ---------------------------------------------------------------------------


def _oauth_state_secret() -> bytes:
    keys = []
    if os.environ.get("WATHEFNI_MAILBOX_SECRET_KEY"):
        keys.append(os.environ["WATHEFNI_MAILBOX_SECRET_KEY"].split(",")[0].strip())
    base = keys[0] if keys else (os.environ.get("WATHEFNI_SECRET_KEY") or "wathefni-platform-oauth")
    return hashlib.sha256(("platform-oauth-state:" + base).encode("utf-8")).digest()


def sign_oauth_state(payload: dict[str, Any]) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii").rstrip("=")
    sig = hmac.new(_oauth_state_secret(), raw.encode("ascii"), hashlib.sha256).hexdigest()[:32]
    return f"{raw}.{sig}"


def verify_oauth_state(state: str) -> dict[str, Any] | None:
    try:
        raw, sig = str(state or "").split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(_oauth_state_secret(), raw.encode("ascii"), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        pad = "=" * (-len(raw) % 4)
        data = json.loads(base64.urlsafe_b64decode((raw + pad).encode("ascii")).decode("utf-8"))
    except Exception:
        return None
    if int(data.get("exp", 0)) < int(time.time()):
        return None
    return data


def start_oauth(
    legacy: Any,
    *,
    company_code: str,
    provider_key: str,
    actor_user_id: str | None = None,
    attach_calendar: bool = True,
) -> dict[str, Any]:
    provider = _text(provider_key).lower()
    company = _text(company_code).upper()
    state = sign_oauth_state(
        {
            "company_code": company,
            "provider_key": provider,
            "actor_user_id": actor_user_id,
            "attach_calendar": bool(attach_calendar),
            "exp": int(time.time()) + 900,
            "nonce": str(uuid4()),
        }
    )
    if provider == pi.PROVIDER_GOOGLE_WORKSPACE:
        if not google_oauth_ready():
            raise pi.PlatformIntegrationError(
                "google_oauth_not_configured",
                "Google Workspace OAuth client is not configured. Ask platform ops to set WATHEFNI_GOOGLE_WORKSPACE_CLIENT_* (or Gmail OAuth fallback).",
                http_status=503,
            )
        cfg = pi.google_workspace_oauth_config()
        # Prefer dedicated redirect; else derived platform callback.
        redirect = cfg.get("redirect_uri") or ""
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": " ".join(pi.GOOGLE_WORKSPACE_CALENDAR_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "false",
            "state": state,
        }
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
        return {"ok": True, "authorize_url": url, "provider_key": provider, "mode": MODE_OAUTH_DELEGATED, "checklist": setup_checklist(provider_key=provider, mode=MODE_OAUTH_DELEGATED)}

    if provider == pi.PROVIDER_MICROSOFT_365:
        if not microsoft_oauth_ready():
            raise pi.PlatformIntegrationError(
                "m365_oauth_not_configured",
                "Microsoft 365 OAuth client is not configured. Ask platform ops to set WATHEFNI_M365_CLIENT_*.",
                http_status=503,
            )
        cfg = pi.microsoft_365_oauth_config()
        params = {
            "client_id": cfg["client_id"],
            "response_type": "code",
            "redirect_uri": cfg["redirect_uri"],
            "response_mode": "query",
            "scope": " ".join(pi.MICROSOFT_365_CALENDAR_SCOPES),
            "state": state,
        }
        url = cfg["auth_uri"] + "?" + urllib.parse.urlencode(params)
        return {"ok": True, "authorize_url": url, "provider_key": provider, "mode": MODE_OAUTH_DELEGATED, "checklist": setup_checklist(provider_key=provider, mode=MODE_OAUTH_DELEGATED)}

    raise pi.PlatformIntegrationError("unsupported_provider", f"Provider {provider} unsupported for OAuth.")


def complete_oauth(
    legacy: Any,
    *,
    state: str,
    code: str,
) -> dict[str, Any]:
    payload = verify_oauth_state(state)
    if not payload:
        raise pi.PlatformIntegrationError("invalid_oauth_state", "OAuth state is invalid or expired.", http_status=400)
    company = _text(payload.get("company_code")).upper()
    provider = _text(payload.get("provider_key")).lower()
    actor = payload.get("actor_user_id")
    attach = bool(payload.get("attach_calendar", True))
    code_s = _text(code)
    if not code_s:
        raise pi.PlatformIntegrationError("missing_code", "Authorization code missing.", http_status=400)

    if provider == pi.PROVIDER_GOOGLE_WORKSPACE:
        tokens = _exchange_google_code(code_s)
        result = pi.connect_provider(
            legacy,
            company_code=company,
            provider_key=provider,
            account_email=tokens.get("email") or "unknown@google",
            refresh_token=tokens["refresh_token"],
            actor_user_id=actor,
            access_token=tokens.get("access_token"),
            granted_scopes=pi.GOOGLE_WORKSPACE_CALENDAR_SCOPES,
        )
    elif provider == pi.PROVIDER_MICROSOFT_365:
        tokens = _exchange_microsoft_code(code_s)
        result = pi.connect_provider(
            legacy,
            company_code=company,
            provider_key=provider,
            account_email=tokens.get("email") or "unknown@microsoft",
            refresh_token=tokens["refresh_token"],
            actor_user_id=actor,
            access_token=tokens.get("access_token"),
            external_tenant_id=tokens.get("tenant_id"),
            granted_scopes=pi.MICROSOFT_365_CALENDAR_SCOPES,
        )
    else:
        raise pi.PlatformIntegrationError("unsupported_provider", provider)

    # Stamp connection_mode=oauth_delegated
    integ = result.get("integration") or {}
    iid = integ.get("integration_id")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_c6_schema(cur)
            cur.execute(
                """
                UPDATE platform_company_integrations
                SET connection_mode=%s, reconnect_required=false, updated_at=now()
                WHERE company_code=%s AND integration_id=%s
                RETURNING *
                """,
                (MODE_OAUTH_DELEGATED, company, iid),
            )
            row = dict(cur.fetchone() or {})
        conn.commit()

    connection = None
    if attach and iid:
        attached = pi.attach_calendar_sync_connection(
            legacy,
            company_code=company,
            integration_id=str(iid),
            actor_user_id=actor,
            external_calendar_id="primary" if provider == pi.PROVIDER_GOOGLE_WORKSPACE else "calendar",
            with_meet_default=True,
        )
        connection = attached.get("connection")
    return {"ok": True, "integration": serialize_c6(row or integ, has_credentials=True), "connection": connection}


def _exchange_google_code(code: str) -> dict[str, Any]:
    cfg = pi.google_workspace_oauth_config()
    body = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uri": cfg["redirect_uri"],
            "grant_type": "authorization_code",
        }
    ).encode("ascii")
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise pi.PlatformIntegrationError("google_code_exchange_failed", str(exc)[:160], http_status=502) from exc
    refresh = data.get("refresh_token")
    access = data.get("access_token")
    if not refresh:
        raise pi.PlatformIntegrationError("google_no_refresh_token", "Google did not return a refresh token. Re-consent with prompt=consent.")
    email = None
    if access:
        try:
            ureq = urllib.request.Request("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {access}"})
            with urllib.request.urlopen(ureq, timeout=20) as resp:
                email = (json.loads(resp.read().decode("utf-8")) or {}).get("email")
        except Exception:
            email = None
    return {"refresh_token": refresh, "access_token": access, "email": email}


def _exchange_microsoft_code(code: str) -> dict[str, Any]:
    cfg = pi.microsoft_365_oauth_config()
    body = urllib.parse.urlencode(
        {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "code": code,
            "redirect_uri": cfg["redirect_uri"],
            "grant_type": "authorization_code",
            "scope": " ".join(pi.MICROSOFT_365_CALENDAR_SCOPES),
        }
    ).encode("ascii")
    req = urllib.request.Request(cfg["token_uri"], data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise pi.PlatformIntegrationError("m365_code_exchange_failed", str(exc)[:160], http_status=502) from exc
    refresh = data.get("refresh_token")
    access = data.get("access_token")
    if not refresh:
        raise pi.PlatformIntegrationError("m365_no_refresh_token", "Microsoft did not return a refresh token.")
    email = None
    tenant_id = None
    if access:
        try:
            ureq = urllib.request.Request("https://graph.microsoft.com/v1.0/me", headers={"Authorization": f"Bearer {access}"})
            with urllib.request.urlopen(ureq, timeout=20) as resp:
                me = json.loads(resp.read().decode("utf-8")) or {}
                email = me.get("mail") or me.get("userPrincipalName")
        except Exception:
            email = None
    return {"refresh_token": refresh, "access_token": access, "email": email, "tenant_id": tenant_id}


# ---------------------------------------------------------------------------
# Health / expiry / reconnect / rotation
# ---------------------------------------------------------------------------


def mark_reconnect_required(legacy: Any, *, company_code: str, integration_id: str, reason: str) -> dict[str, Any]:
    company = _text(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_c6_schema(cur)
            cur.execute(
                """
                UPDATE platform_company_integrations
                SET status='reconnect_required', reconnect_required=true,
                    last_error=%s, health=%s::jsonb, updated_at=now()
                WHERE company_code=%s AND integration_id=%s
                RETURNING *
                """,
                (
                    _text(reason)[:300],
                    _json(legacy, {"ok": False, "reconnect_required": True, "reason": _text(reason)[:200]}),
                    company,
                    integration_id,
                ),
            )
            row = cur.fetchone()
            if not row:
                raise pi.PlatformIntegrationError("integration_not_found", "Integration not found.", http_status=404)
            pi._audit(
                cur,
                legacy,
                company_code=company,
                integration_id=integration_id,
                action="reconnect_required",
                before={},
                after={"reason": reason},
            )
        conn.commit()
    return {"ok": True, "integration": serialize_c6(dict(row), has_credentials=True)}


def rotate_microsoft_secret(
    legacy: Any,
    *,
    company_code: str,
    integration_id: str,
    client_secret: str | None = None,
    certificate_pem: str | None = None,
    certificate_thumbprint: str | None = None,
    credential_expires_at: str | None = None,
    actor_user_id: str | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    """Safe credential rotation without disconnecting Calendar bindings."""
    company = _text(company_code).upper()
    secret = _text(client_secret)
    cert = _text(certificate_pem)
    if not secret and not cert:
        raise pi.PlatformIntegrationError("missing_credential", "Provide client_secret or certificate_pem.")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_c6_schema(cur)
            integ = pi.get_integration(cur, company_code=company, integration_id=integration_id)
            if not integ:
                raise pi.PlatformIntegrationError("integration_not_found", "Integration not found.", http_status=404)
            if _text(integ.get("connection_mode")) != MODE_ENTERPRISE_APP:
                raise pi.PlatformIntegrationError("wrong_mode", "Rotation applies to enterprise_app mode.")
            meta = integ.get("metadata") if isinstance(integ.get("metadata"), dict) else {}
            client_id = _text(meta.get("entra_client_id"))
            tenant = _text(integ.get("external_tenant_id"))
            if validate:
                mint_microsoft_app_token(tenant_id=tenant, client_id=client_id, client_secret=secret or None, certificate_pem=cert or None)
            expires = None
            if credential_expires_at:
                try:
                    expires = datetime.fromisoformat(credential_expires_at.replace("Z", "+00:00"))
                except Exception:
                    expires = _now() + timedelta(days=180)
            if secret:
                _store_secret(
                    cur,
                    legacy,
                    company_code=company,
                    integration_id=integration_id,
                    secret_type=SECRET_CLIENT,
                    plaintext=json.dumps({"client_id": client_id, "client_secret": secret, "tenant_id": tenant}),
                    meta={"kind": "client_secret", "rotated_at": _now().isoformat()},
                )
            if cert:
                _store_secret(
                    cur,
                    legacy,
                    company_code=company,
                    integration_id=integration_id,
                    secret_type=SECRET_CERT,
                    plaintext=json.dumps(
                        {"client_id": client_id, "tenant_id": tenant, "certificate_pem": cert, "thumbprint": _text(certificate_thumbprint)}
                    ),
                    meta={"kind": "certificate", "rotated_at": _now().isoformat()},
                )
            cur.execute(
                """
                UPDATE platform_company_integrations
                SET status='connected', reconnect_required=false, last_error=NULL,
                    credential_expires_at=%s, last_verified_at=now(), last_health_at=now(),
                    health=%s::jsonb, updated_at=now(), expiry_notified_at=NULL
                WHERE company_code=%s AND integration_id=%s
                RETURNING *
                """,
                (
                    expires,
                    _json(legacy, {"ok": True, "verified": True, "rotated": True, "mode": MODE_ENTERPRISE_APP}),
                    company,
                    integration_id,
                ),
            )
            row = dict(cur.fetchone())
            pi._audit(
                cur,
                legacy,
                company_code=company,
                integration_id=integration_id,
                actor_user_id=actor_user_id,
                action="credential_rotated",
                before={},
                after={"mode": MODE_ENTERPRISE_APP},
            )
        conn.commit()
    return {"ok": True, "integration": serialize_c6(row, has_credentials=True)}


def healthcheck_integration(legacy: Any, *, company_code: str, integration_id: str) -> dict[str, Any]:
    company = _text(company_code).upper()
    dry = _text(os.environ.get("CALENDAR_SYNC_DRY_RUN")).lower() in {"1", "true", "yes", "on"}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_c6_schema(cur)
            integ = pi.get_integration(cur, company_code=company, integration_id=integration_id)
            if not integ:
                raise pi.PlatformIntegrationError("integration_not_found", "Integration not found.", http_status=404)
            try:
                token = mint_access_c6(legacy, cur, integ) if not dry else "dry_run"
                ok = bool(token)
                health = {
                    "ok": ok,
                    "verified": ok and not dry,
                    "dry_run": dry,
                    "mode": _text(integ.get("connection_mode")),
                    "checked_at": _now().isoformat(),
                }
                cur.execute(
                    """
                    UPDATE platform_company_integrations
                    SET health=%s::jsonb, last_health_at=now(), last_verified_at=now(),
                        last_error=NULL, reconnect_required=false,
                        status=CASE WHEN status='reconnect_required' THEN 'connected' ELSE status END,
                        updated_at=now()
                    WHERE company_code=%s AND integration_id=%s
                    RETURNING *
                    """,
                    (_json(legacy, health), company, integration_id),
                )
                row = dict(cur.fetchone())
            except Exception as exc:
                health = {"ok": False, "error": str(exc)[:200], "checked_at": _now().isoformat()}
                cur.execute(
                    """
                    UPDATE platform_company_integrations
                    SET health=%s::jsonb, last_health_at=now(), last_error=%s,
                        status='reconnect_required', reconnect_required=true, updated_at=now()
                    WHERE company_code=%s AND integration_id=%s
                    RETURNING *
                    """,
                    (_json(legacy, health), str(exc)[:300], company, integration_id),
                )
                row = dict(cur.fetchone())
                ok = False
        conn.commit()
    return {"ok": ok, "integration": serialize_c6(row, has_credentials=True), "health": health}


def scan_expiring_credentials(legacy: Any, *, within_days: int = 14) -> dict[str, Any]:
    """Find credentials nearing expiry and flag for admin notification."""
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_c6_schema(cur)
            cur.execute(
                """
                SELECT * FROM platform_company_integrations
                WHERE status IN ('connected','reconnect_required','error')
                  AND credential_expires_at IS NOT NULL
                  AND credential_expires_at <= now() + make_interval(days => %s)
                ORDER BY credential_expires_at ASC
                LIMIT 200
                """,
                (int(within_days),),
            )
            rows = [dict(r) for r in cur.fetchall()]
            notified = []
            for row in rows:
                if row.get("expiry_notified_at"):
                    continue
                cur.execute(
                    """
                    UPDATE platform_company_integrations
                    SET expiry_notified_at=now(),
                        health = COALESCE(health, '{}'::jsonb) || %s::jsonb,
                        updated_at=now()
                    WHERE integration_id=%s
                    RETURNING company_code, integration_id, credential_expires_at, account_email, provider_key
                    """,
                    (
                        _json(legacy, {"expiry_warning": True, "expiry_notified_at": _now().isoformat()}),
                        str(row["integration_id"]),
                    ),
                )
                notified.append(dict(cur.fetchone()))
                pi._audit(
                    cur,
                    legacy,
                    company_code=row["company_code"],
                    integration_id=str(row["integration_id"]),
                    action="credential_expiry_warning",
                    before={},
                    after={"credential_expires_at": str(row.get("credential_expires_at"))},
                )
        conn.commit()
    return {"ok": True, "expiring": len(rows), "newly_notified": len(notified), "items": [serialize_c6(r) for r in rows]}


def list_integrations_c6(legacy: Any, *, company_code: str) -> list[dict[str, Any]]:
    company = _text(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_c6_schema(cur)
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
    return [serialize_c6(r, has_credentials=bool(r.get("has_credentials"))) or {} for r in rows]
