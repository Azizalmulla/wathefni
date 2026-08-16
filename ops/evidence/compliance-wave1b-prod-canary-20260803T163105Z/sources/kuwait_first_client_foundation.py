"""Kuwait first-client foundation — legal entity, hire snapshot, identity, residence.

Contained local remediation. Does NOT enforce leave/EOS/PIFSS/fines/OT multipliers,
payroll payments, or PAM/MOI/PACI filings. Employer-entered government identifiers
are stored as text and are not API-verified.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping

# --------------------------------------------------------------------------- #
# Permissions
# --------------------------------------------------------------------------- #

IDENTITY_READ = "employees.identity.read"
IDENTITY_READ_FULL = "employees.identity.read_full"
IDENTITY_WRITE = "employees.identity.write"
LEGAL_ENTITY_MANAGE = "employees.legal_entity.manage"
LEGAL_ENTITY_READ = "employees.legal_entity.read"

# Country-neutral category tokens always allowed. KW-specific tokens are profile-scoped.
GENERIC_EMPLOYEE_CATEGORIES = frozenset({"other", "unspecified"})
KW_EMPLOYEE_CATEGORIES = frozenset({"kuwaiti_national", "article_18_expatriate"})
EMPLOYEE_CATEGORIES = GENERIC_EMPLOYEE_CATEGORIES | KW_EMPLOYEE_CATEGORIES

# KW profile vocabulary (no Saudi iqama). Other GCC packs add their own profiles later.
CANONICAL_RESIDENCE = "residence"
LEGACY_RESIDENCE_ALIASES = frozenset({"residency_iqama", "residency"})
RESIDENCE_COMPAT = {
    "residence": CANONICAL_RESIDENCE,
    "residency": CANONICAL_RESIDENCE,
    "residency_iqama": CANONICAL_RESIDENCE,
}

# Thin TZ/currency bootstrap only — not labor-law packs (mirrors company_setup).
_GCC_CURRENCY = {
    "KW": "KWD",
    "SA": "SAR",
    "AE": "AED",
    "QA": "QAR",
    "BH": "BHD",
    "OM": "OMR",
}

# Country profiles: KW-specific concepts live here, not as universal hire rules.
COUNTRY_PROFILES: dict[str, dict[str, Any]] = {
    "KW": {
        "identity_profile": "kw_civil_id",
        "national_id_api_field": "civil_id_number",
        "employee_categories": sorted(KW_EMPLOYEE_CATEGORIES | GENERIC_EMPLOYEE_CATEGORIES),
        "gov_employer_ref_keys": ("pam_employer_file_no",),
        "document_types": (CANONICAL_RESIDENCE, "work_permit", "civil_id", "passport"),
        "expat_category": "article_18_expatriate",
        "national_category": "kuwaiti_national",
    },
}

SOURCE_PATHS = frozenset({"accepted_offer", "offers_disabled_defaults", "hire_override"})

# Encrypted national-id storage slots (country-neutral). KW profile presents them as Civil ID.
SENSITIVE_IDENTITY_FIELDS = frozenset(
    {
        "civil_id_number",  # KW Civil ID presentation of national_id slot
        "passport_number",
        "residence_number",  # KW residence number; not seeded for non-KW profiles
        "work_permit_number",
    }
)

# Government-process attachments — never employee-master fields.
GOVERNMENT_PROCESS_ATTACHMENTS = frozenset(
    {
        "police_certificate",
        "police_clearance",
        "blood_type",
        "blood_test",
        "lease",
        "lease_contract",
        "fingerprint_notice",
    }
)


class FoundationError(Exception):
    def __init__(self, code: str, message: str = "", *, status_code: int = 400, extra: dict | None = None):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.status_code = status_code
        self.extra = extra or {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _company(code: str | None) -> str:
    return str(code or "").strip().upper()


def _require(permissions: Iterable[str] | None, need: str) -> None:
    if need not in set(permissions or ()):
        raise FoundationError("permission_denied", f"Missing permission {need}", status_code=403)


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    try:
        from decimal import Decimal

        if isinstance(value, Decimal):
            return str(value)
    except Exception:
        pass
    return value


def _json(legacy: Any, value: Any) -> Any:
    ready = _json_ready(value)
    if hasattr(legacy, "Json"):
        return legacy.Json(ready)
    return JsonCompat(ready)


class JsonCompat(dict):
    """Fallback when legacy.Json is unavailable in unit tests."""

    def __init__(self, value: Any) -> None:
        self.value = value


# --------------------------------------------------------------------------- #
# Encryption (reuse Civil ID key material; Fernet preferred)
# --------------------------------------------------------------------------- #


def _identity_key() -> bytes:
    key = os.getenv("WATHEFNI_CIVIL_ID_KEY") or os.getenv("WATHEFNI_EMPLOYEE_IDENTITY_KEY")
    if not key:
        raise FoundationError("identity_key_missing", "Set WATHEFNI_CIVIL_ID_KEY for employee identity encryption")
    return key.encode() if isinstance(key, str) else key


def encrypt_identifier(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise FoundationError("identifier_empty")
    key = _identity_key()
    try:
        from cryptography.fernet import Fernet

        return "fernet:" + Fernet(key).encrypt(raw.encode()).decode()
    except ImportError:
        nonce = secrets.token_bytes(16)
        stream = hmac.new(key, nonce, hashlib.sha256).digest()
        ciphertext = bytes(b ^ stream[i % len(stream)] for i, b in enumerate(raw.encode()))
        import base64

        return "hmac:" + base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt_identifier(blob: str | None) -> str | None:
    if not blob:
        return None
    key = _identity_key()
    if blob.startswith("fernet:"):
        from cryptography.fernet import Fernet

        return Fernet(key).decrypt(blob[7:].encode()).decode()
    if blob.startswith("hmac:"):
        import base64

        data = base64.urlsafe_b64decode(blob[5:].encode())
        nonce, ciphertext = data[:16], data[16:]
        stream = hmac.new(key, nonce, hashlib.sha256).digest()
        return bytes(b ^ stream[i % len(stream)] for i, b in enumerate(ciphertext)).decode()
    raise FoundationError("identifier_ciphertext_invalid")


def mask_identifier(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value)
    if len(text) <= 4:
        return "*" * len(text)
    return ("*" * max(0, len(text) - 4)) + text[-4:]


def normalize_document_type(document_type: str | None) -> str:
    raw = str(document_type or "").strip().lower()
    if raw in RESIDENCE_COMPAT:
        return RESIDENCE_COMPAT[raw]
    return raw


def is_government_process_attachment(document_type: str | None) -> bool:
    return normalize_document_type(document_type) in GOVERNMENT_PROCESS_ATTACHMENTS


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #


def ensure_foundation_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_entities (
          legal_entity_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          country_code text NOT NULL,
          registered_name_en text NOT NULL,
          registered_name_ar text NOT NULL DEFAULT '',
          commercial_registration_no text NOT NULL DEFAULT '',
          licence_no text NOT NULL DEFAULT '',
          pam_employer_file_no text NOT NULL DEFAULT '',
          default_currency text NOT NULL,
          status text NOT NULL DEFAULT 'active',
          is_default boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (status IN ('active','inactive')),
          CHECK (char_length(country_code) = 2)
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS legal_entities_one_default_uq
          ON legal_entities (company_code)
          WHERE is_default = true AND status = 'active'
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS legal_entities_company_idx
          ON legal_entities (company_code, status)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_entity_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          legal_entity_id uuid NOT NULL REFERENCES legal_entities(legal_entity_id),
          company_code text NOT NULL,
          event_type text NOT NULL,
          actor_user_id text,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employment_applicability_snapshots (
          snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          legal_entity_id uuid NOT NULL REFERENCES legal_entities(legal_entity_id),
          country_of_employment text NOT NULL,
          currency text NOT NULL,
          source_path text NOT NULL,
          accepted_offer_id text,
          accepted_offer_version integer,
          template_id text,
          template_version text,
          template_approval_ref text,
          document_language text,
          employer_policy_version text,
          configuration_effective_date date,
          proposed_start_date date,
          probation_days integer,
          compensation_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          hire_operation_id uuid,
          app_key text,
          arabic_contract_file_id text,
          arabic_contract_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          snapshot_hash text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (source_path IN ('accepted_offer','offers_disabled_defaults','hire_override')),
          UNIQUE (company_code, employee_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employment_applicability_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          snapshot_id uuid NOT NULL REFERENCES employment_applicability_snapshots(snapshot_id),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          event_type text NOT NULL,
          actor_user_id text,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_identity (
          employee_key text NOT NULL,
          company_code text NOT NULL,
          identity_profile text NOT NULL DEFAULT 'generic',
          employee_category text NOT NULL DEFAULT 'unspecified',
          nationality_country_code text,
          -- national_id storage slots (encrypted). KW profile presents as Civil ID.
          civil_id_encrypted text,
          civil_id_last4 text,
          passport_number_encrypted text,
          passport_last4 text,
          residence_number_encrypted text,
          residence_last4 text,
          work_permit_number_encrypted text,
          work_permit_last4 text,
          civil_id_confirmed boolean NOT NULL DEFAULT false,
          passport_confirmed boolean NOT NULL DEFAULT false,
          residence_confirmed boolean NOT NULL DEFAULT false,
          work_permit_confirmed boolean NOT NULL DEFAULT false,
          ocr_pending jsonb NOT NULL DEFAULT '{}'::jsonb,
          requiredness_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
          updated_at timestamptz NOT NULL DEFAULT now(),
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (company_code, employee_key),
          CHECK (employee_category ~ '^[a-z][a-z0-9_]{0,63}$')
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_identity_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          field_name text NOT NULL,
          event_type text NOT NULL,
          actor_user_id text,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_document_metadata (
          document_meta_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          document_type text NOT NULL,
          issuing_authority text,
          issue_date date,
          expiry_date date,
          file_id text,
          file_version text,
          verification_status text NOT NULL DEFAULT 'unverified',
          hr_reviewer_user_id text,
          source text,
          notes text,
          is_master_field boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (is_master_field = false),
          CHECK (document_type <> ALL (ARRAY['police_certificate','police_clearance','blood_type','blood_test','lease','lease_contract','fingerprint_notice']))
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS employee_document_metadata_emp_idx
          ON employee_document_metadata (company_code, employee_key, document_type)
        """
    )
    # Soft rename support: historical onboarding/compliance rows keep legacy types;
    # this map table records explicit compatibility without destructive merge.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS document_type_compat_map (
          legacy_type text PRIMARY KEY,
          canonical_type text NOT NULL,
          notes text NOT NULL DEFAULT '',
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    for legacy, canonical in (
        ("residency_iqama", CANONICAL_RESIDENCE),
        ("residency", CANONICAL_RESIDENCE),
    ):
        cur.execute(
            """
            INSERT INTO document_type_compat_map(legacy_type, canonical_type, notes)
            VALUES (%s,%s,%s)
            ON CONFLICT (legacy_type) DO UPDATE SET canonical_type=EXCLUDED.canonical_type
            """,
            (legacy, canonical, "Kuwait first-client foundation — no silent destructive merge"),
        )
    # Additive column for identity profile when upgrading older local schemas.
    cur.execute(
        """
        ALTER TABLE employee_identity
          ADD COLUMN IF NOT EXISTS identity_profile text NOT NULL DEFAULT 'generic'
        """
    )


def country_profile(country_code: str | None) -> dict[str, Any]:
    code = str(country_code or "").strip().upper()
    return dict(COUNTRY_PROFILES.get(code) or {})


def currency_for_country(country_code: str | None) -> str:
    code = str(country_code or "").strip().upper()
    return _GCC_CURRENCY.get(code) or ""


def resolve_company_country(cur: Any, company_code: str) -> str:
    """Read tenant country; never invent KW for other tenants."""
    company = _company(company_code)
    try:
        cur.execute("SELECT country FROM companies WHERE company_code=%s", (company,))
        row = cur.fetchone()
        if row and row.get("country"):
            return str(row["country"]).strip().upper()[:2]
    except Exception:
        pass
    return ""


def assert_category_allowed_for_country(category: str, country_code: str | None) -> None:
    if category not in EMPLOYEE_CATEGORIES and not re.fullmatch(r"^[a-z][a-z0-9_]{0,63}$", category or ""):
        raise FoundationError("employee_category_invalid")
    country = str(country_code or "").strip().upper()
    if category in KW_EMPLOYEE_CATEGORIES and country != "KW":
        raise FoundationError(
            "employee_category_country_mismatch",
            f"{category} is KW-profile only; country={country or 'unset'}",
        )


def assert_pam_allowed(country_code: str | None, pam_employer_file_no: str | None) -> None:
    pam = str(pam_employer_file_no or "").strip()
    if not pam:
        return
    if str(country_code or "").strip().upper() != "KW":
        raise FoundationError(
            "pam_ref_kw_only",
            "PAM employer/file reference is KW-profile only",
        )


# --------------------------------------------------------------------------- #
# Legal entities
# --------------------------------------------------------------------------- #


def _append_legal_entity_event(
    cur: Any,
    legacy: Any,
    *,
    legal_entity_id: str,
    company_code: str,
    event_type: str,
    actor_user_id: str | None,
    payload: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO legal_entity_events(legal_entity_id, company_code, event_type, actor_user_id, payload)
        VALUES (%s,%s,%s,%s,%s)
        """,
        (legal_entity_id, company_code, event_type, actor_user_id, _json(legacy, payload)),
    )


def create_legal_entity(
    legacy: Any,
    *,
    company_code: str,
    registered_name_en: str,
    registered_name_ar: str = "",
    country_code: str | None = None,
    commercial_registration_no: str = "",
    licence_no: str = "",
    pam_employer_file_no: str = "",
    default_currency: str | None = None,
    is_default: bool = False,
    actor_user_id: str | None = None,
    permissions: Iterable[str] | None = None,
) -> dict[str, Any]:
    _require(permissions, LEGAL_ENTITY_MANAGE)
    company = _company(company_code)
    name_en = str(registered_name_en or "").strip()
    if not company or not name_en:
        raise FoundationError("legal_entity_required_fields")
    country = str(country_code or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise FoundationError("country_required", "country_code must be an explicit ISO-3166 alpha-2 code")
    currency = str(default_currency or currency_for_country(country) or "").strip().upper()
    if not currency:
        raise FoundationError("currency_required", "default_currency required when country has no known bootstrap currency")
    assert_pam_allowed(country, pam_employer_file_no)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_foundation_schema(cur)
            if is_default:
                cur.execute(
                    """
                    UPDATE legal_entities SET is_default=false, updated_at=now()
                    WHERE company_code=%s AND is_default=true
                    """,
                    (company,),
                )
            cur.execute(
                """
                INSERT INTO legal_entities(
                  company_code, country_code, registered_name_en, registered_name_ar,
                  commercial_registration_no, licence_no, pam_employer_file_no,
                  default_currency, status, is_default
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'active',%s)
                RETURNING *
                """,
                (
                    company,
                    country,
                    name_en,
                    str(registered_name_ar or "").strip(),
                    str(commercial_registration_no or "").strip(),
                    str(licence_no or "").strip(),
                    str(pam_employer_file_no or "").strip() if country == "KW" else "",
                    currency,
                    bool(is_default),
                ),
            )
            row = dict(cur.fetchone())
            _append_legal_entity_event(
                cur,
                legacy,
                legal_entity_id=str(row["legal_entity_id"]),
                company_code=company,
                event_type="created",
                actor_user_id=actor_user_id,
                payload={"is_default": bool(is_default), "country_code": country},
            )
        conn.commit()
    return legacy.json_safe(row) if hasattr(legacy, "json_safe") else row


def ensure_default_legal_entity(
    legacy: Any,
    *,
    company_code: str,
    registered_name_en: str | None = None,
    registered_name_ar: str | None = None,
    country_code: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Idempotent: exactly one active default per company."""
    company = _company(company_code)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_foundation_schema(cur)
            cur.execute(
                """
                SELECT * FROM legal_entities
                WHERE company_code=%s AND is_default=true AND status='active'
                LIMIT 1
                """,
                (company,),
            )
            existing = cur.fetchone()
            if existing:
                return dict(existing)
            cur.execute(
                "SELECT * FROM legal_entities WHERE company_code=%s AND status='active' ORDER BY created_at ASC LIMIT 1",
                (company,),
            )
            first = cur.fetchone()
            if first:
                cur.execute(
                    """
                    UPDATE legal_entities SET is_default=true, updated_at=now()
                    WHERE legal_entity_id=%s
                    RETURNING *
                    """,
                    (first["legal_entity_id"],),
                )
                row = dict(cur.fetchone())
                _append_legal_entity_event(
                    cur,
                    legacy,
                    legal_entity_id=str(row["legal_entity_id"]),
                    company_code=company,
                    event_type="marked_default",
                    actor_user_id=actor_user_id,
                    payload={},
                )
                conn.commit()
                return row
            resolved_country = str(country_code or "").strip().upper() or resolve_company_country(cur, company)
        conn.commit()
    if not resolved_country:
        raise FoundationError(
            "country_required",
            "ensure_default_legal_entity requires explicit country_code or companies.country",
        )
    return create_legal_entity(
        legacy,
        company_code=company,
        registered_name_en=registered_name_en or f"{company} Legal Entity",
        registered_name_ar=registered_name_ar or "",
        country_code=resolved_country,
        default_currency=currency_for_country(resolved_country) or None,
        is_default=True,
        actor_user_id=actor_user_id,
        permissions={LEGAL_ENTITY_MANAGE},
    )


def get_default_legal_entity(cur: Any, company_code: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM legal_entities
        WHERE company_code=%s AND is_default=true AND status='active'
        LIMIT 1
        """,
        (_company(company_code),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def list_legal_entities(legacy: Any, *, company_code: str, permissions: Iterable[str] | None = None) -> list[dict[str, Any]]:
    _require(permissions, LEGAL_ENTITY_READ)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_foundation_schema(cur)
            cur.execute(
                "SELECT * FROM legal_entities WHERE company_code=%s ORDER BY is_default DESC, created_at ASC",
                (_company(company_code),),
            )
            return [dict(r) for r in (cur.fetchall() or [])]


def set_default_legal_entity(
    legacy: Any,
    *,
    company_code: str,
    legal_entity_id: str,
    actor_user_id: str | None = None,
    permissions: Iterable[str] | None = None,
) -> dict[str, Any]:
    _require(permissions, LEGAL_ENTITY_MANAGE)
    company = _company(company_code)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_foundation_schema(cur)
            cur.execute(
                "SELECT * FROM legal_entities WHERE company_code=%s AND legal_entity_id=%s FOR UPDATE",
                (company, legal_entity_id),
            )
            row = cur.fetchone()
            if not row:
                raise FoundationError("legal_entity_not_found", status_code=404)
            if str(row.get("status")) != "active":
                raise FoundationError("legal_entity_inactive")
            cur.execute(
                "UPDATE legal_entities SET is_default=false, updated_at=now() WHERE company_code=%s AND is_default=true",
                (company,),
            )
            cur.execute(
                """
                UPDATE legal_entities SET is_default=true, updated_at=now()
                WHERE legal_entity_id=%s
                RETURNING *
                """,
                (legal_entity_id,),
            )
            updated = dict(cur.fetchone())
            _append_legal_entity_event(
                cur,
                legacy,
                legal_entity_id=str(legal_entity_id),
                company_code=company,
                event_type="set_default",
                actor_user_id=actor_user_id,
                payload={},
            )
        conn.commit()
    return updated


# --------------------------------------------------------------------------- #
# Hire-time applicability snapshot
# --------------------------------------------------------------------------- #


def _company_offer_defaults(legacy: Any, company_code: str) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    try:
        raw = legacy.get_company_settings(company_code) if hasattr(legacy, "get_company_settings") else {}
        if isinstance(raw, dict):
            settings = raw.get("settings") if isinstance(raw.get("settings"), dict) else raw
    except Exception:
        settings = {}
    defaults = settings.get("employment_offer_document_defaults") if isinstance(settings, dict) else {}
    return dict(defaults) if isinstance(defaults, dict) else {}


def _resolve_country_currency(
    *,
    explicit_country: str | None,
    explicit_currency: str | None,
    defaults: Mapping[str, Any] | None = None,
    company_country: str | None = None,
) -> tuple[str, str]:
    """Prefer explicit offer/default values; never invent KW for unknown tenants."""
    defaults = defaults or {}
    country = str(explicit_country or defaults.get("country_of_employment") or company_country or "").strip().upper()
    currency = str(explicit_currency or defaults.get("currency") or currency_for_country(country) or "").strip().upper()
    if not country:
        raise FoundationError("country_required", "country_of_employment is required for applicability snapshot")
    if not currency:
        raise FoundationError("currency_required", "currency is required for applicability snapshot")
    return country, currency


def _snapshot_hash(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(_json_ready(dict(payload)), sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def build_applicability_from_offer(
    offer: Mapping[str, Any],
    *,
    legal_entity_id: str,
    company_country: str | None = None,
) -> dict[str, Any]:
    allowances = offer.get("allowances_json")
    if allowances is None:
        allowances = offer.get("allowances")
    country, currency = _resolve_country_currency(
        explicit_country=str(offer.get("country_of_employment") or "") or None,
        explicit_currency=str(offer.get("currency") or "") or None,
        company_country=company_country,
    )
    return {
        "country_of_employment": country,
        "legal_entity_id": str(legal_entity_id),
        "currency": currency,
        "accepted_offer_id": str(offer.get("offer_id") or "") or None,
        "accepted_offer_version": int(offer.get("accepted_version") or offer.get("current_version") or 0) or None,
        "template_id": offer.get("template_id"),
        "template_version": offer.get("template_version"),
        "template_approval_ref": offer.get("template_approval_ref"),
        "document_language": offer.get("document_language"),
        "employer_policy_version": offer.get("employer_policy_version"),
        "configuration_effective_date": offer.get("configuration_effective_date"),
        "proposed_start_date": offer.get("proposed_start_date"),
        "probation_days": offer.get("probation_days"),
        "compensation_snapshot": {
            "base_salary": offer.get("base_salary"),
            "currency": currency,
            "allowances": allowances if allowances is not None else [],
            "authorized_signatory": offer.get("authorized_signatory"),
            "employing_legal_entity_text": offer.get("employing_legal_entity"),
        },
        "source_path": "accepted_offer",
    }


def build_applicability_from_defaults(
    legacy: Any,
    *,
    company_code: str,
    legal_entity_id: str,
    source_path: str,
    company_country: str | None = None,
) -> dict[str, Any]:
    if source_path not in SOURCE_PATHS:
        raise FoundationError("source_path_invalid")
    defaults = _company_offer_defaults(legacy, company_code)
    entity_name = ""
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT registered_name_en FROM legal_entities WHERE legal_entity_id=%s", (legal_entity_id,))
            row = cur.fetchone()
            entity_name = str((row or {}).get("registered_name_en") or "")
            if not company_country:
                company_country = resolve_company_country(cur, company_code)
    country, currency = _resolve_country_currency(
        explicit_country=None,
        explicit_currency=None,
        defaults=defaults,
        company_country=company_country,
    )
    return {
        "country_of_employment": country,
        "legal_entity_id": str(legal_entity_id),
        "currency": currency,
        "accepted_offer_id": None,
        "accepted_offer_version": None,
        "template_id": defaults.get("template_id"),
        "template_version": defaults.get("template_version"),
        "template_approval_ref": defaults.get("template_approval_ref"),
        "document_language": defaults.get("document_language") or ("ar" if country == "KW" else "en"),
        "employer_policy_version": defaults.get("employer_policy_version"),
        "configuration_effective_date": defaults.get("configuration_effective_date"),
        "proposed_start_date": None,
        "probation_days": defaults.get("probation_days"),
        "compensation_snapshot": {
            "base_salary": None,
            "currency": currency,
            "allowances": [],
            "authorized_signatory": defaults.get("authorized_signatory"),
            "employing_legal_entity_text": entity_name,
        },
        "source_path": source_path,
    }


def resolve_hire_applicability(
    legacy: Any,
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    hire_operation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve snapshot payload + source_path without writing."""
    company = _company(company_code)
    ensure_foundation_schema(cur)
    company_country = resolve_company_country(cur, company)
    defaults = _company_offer_defaults(legacy, company)
    # Prefer tenant country; else offer/default evidence — never invent KW blindly.
    if not company_country:
        company_country = str(defaults.get("country_of_employment") or "").strip().upper()
    entity = get_default_legal_entity(cur, company)
    if not entity:
        # Peek accepted offer country inside hire TX when tenant country unset.
        offer_country = ""
        if app_key:
            try:
                cur.execute(
                    """
                    SELECT country_of_employment, currency
                    FROM employment_offers
                    WHERE company_code=%s AND app_key=%s AND status='accepted'
                    ORDER BY responded_at DESC NULLS LAST, updated_at DESC
                    LIMIT 1
                    """,
                    (company, app_key),
                )
                orow = cur.fetchone()
                if orow and orow.get("country_of_employment"):
                    offer_country = str(orow["country_of_employment"]).strip().upper()
                    if not company_country:
                        company_country = offer_country
            except Exception:
                pass
        if not company_country:
            raise FoundationError(
                "country_required",
                "Cannot auto-create legal entity without companies.country, accepted offer country, or company defaults",
            )
        currency = currency_for_country(company_country) or str(defaults.get("currency") or "").strip().upper()
        if not currency:
            raise FoundationError("currency_required", f"No bootstrap currency for {company_country}")
        name = f"{company} Legal Entity"
        cur.execute(
            """
            INSERT INTO legal_entities(
              company_code, country_code, registered_name_en, registered_name_ar,
              default_currency, status, is_default
            )
            VALUES (%s,%s,%s,'',%s,'active',true)
            RETURNING *
            """,
            (company, company_country, name, currency),
        )
        entity = dict(cur.fetchone())
        _append_legal_entity_event(
            cur,
            legacy,
            legal_entity_id=str(entity["legal_entity_id"]),
            company_code=company,
            event_type="created_on_hire",
            actor_user_id=None,
            payload={"auto": True, "country_code": company_country},
        )

    offers_on = True
    if hasattr(legacy, "company_has_module"):
        try:
            offers_on = bool(legacy.company_has_module(company, "employment_offers"))
        except Exception:
            offers_on = True

    reason = {}
    if hire_operation and isinstance(hire_operation.get("structured_reason"), dict):
        reason = dict(hire_operation["structured_reason"])

    override = bool(reason.get("hire_override") or reason.get("override"))
    if override or str(reason.get("source_path") or "") == "hire_override":
        payload = build_applicability_from_defaults(
            legacy,
            company_code=company,
            legal_entity_id=str(entity["legal_entity_id"]),
            source_path="hire_override",
            company_country=company_country or str(entity.get("country_code") or ""),
        )
        payload["override_reason"] = reason.get("override_reason") or reason.get("reason")
        return payload

    if offers_on:
        cur.execute(
            """
            SELECT *
            FROM employment_offers
            WHERE company_code=%s AND app_key=%s AND status='accepted'
            ORDER BY responded_at DESC NULLS LAST, updated_at DESC
            LIMIT 1
            """,
            (company, app_key),
        )
        offer = cur.fetchone()
        if offer:
            return build_applicability_from_offer(
                dict(offer),
                legal_entity_id=str(entity["legal_entity_id"]),
                company_country=company_country or str(entity.get("country_code") or ""),
            )
        # Offers module on but no accepted offer ⇒ only hire-override path reaches here.
        return build_applicability_from_defaults(
            legacy,
            company_code=company,
            legal_entity_id=str(entity["legal_entity_id"]),
            source_path="hire_override",
            company_country=company_country or str(entity.get("country_code") or ""),
        )

    return build_applicability_from_defaults(
        legacy,
        company_code=company,
        legal_entity_id=str(entity["legal_entity_id"]),
        source_path="offers_disabled_defaults",
        company_country=company_country or str(entity.get("country_code") or ""),
    )


def create_applicability_snapshot_on_cur(
    legacy: Any,
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    app_key: str | None,
    hire_operation_id: str | None,
    hire_operation: Mapping[str, Any] | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Idempotent: one snapshot per employee. Concurrent hire reuses existing."""
    company = _company(company_code)
    ensure_foundation_schema(cur)
    cur.execute(
        """
        SELECT * FROM employment_applicability_snapshots
        WHERE company_code=%s AND employee_key=%s
        FOR UPDATE
        """,
        (company, employee_key),
    )
    existing = cur.fetchone()
    if existing:
        return {"ok": True, "idempotent": True, "snapshot": dict(existing)}

    payload = resolve_hire_applicability(
        legacy, cur, company_code=company, app_key=str(app_key or ""), hire_operation=hire_operation
    )
    body = {
        **payload,
        "company_code": company,
        "employee_key": employee_key,
        "hire_operation_id": hire_operation_id,
        "app_key": app_key,
    }
    snap_hash = _snapshot_hash(body)
    cur.execute(
        """
        INSERT INTO employment_applicability_snapshots(
          company_code, employee_key, legal_entity_id, country_of_employment, currency,
          source_path, accepted_offer_id, accepted_offer_version,
          template_id, template_version, template_approval_ref, document_language,
          employer_policy_version, configuration_effective_date, proposed_start_date,
          probation_days, compensation_snapshot, hire_operation_id, app_key, snapshot_hash
        )
        VALUES (
          %s,%s,%s,%s,%s,
          %s,%s,%s,
          %s,%s,%s,%s,
          %s,%s,%s,
          %s,%s,%s,%s,%s
        )
        ON CONFLICT (company_code, employee_key) DO NOTHING
        RETURNING *
        """,
        (
            company,
            employee_key,
            payload["legal_entity_id"],
            payload["country_of_employment"],
            payload["currency"],
            payload["source_path"],
            payload.get("accepted_offer_id"),
            payload.get("accepted_offer_version"),
            payload.get("template_id"),
            payload.get("template_version"),
            payload.get("template_approval_ref"),
            payload.get("document_language"),
            payload.get("employer_policy_version"),
            payload.get("configuration_effective_date"),
            payload.get("proposed_start_date"),
            payload.get("probation_days"),
            _json(legacy, payload.get("compensation_snapshot") or {}),
            hire_operation_id,
            app_key,
            snap_hash,
        ),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            "SELECT * FROM employment_applicability_snapshots WHERE company_code=%s AND employee_key=%s",
            (company, employee_key),
        )
        row = cur.fetchone()
        return {"ok": True, "idempotent": True, "snapshot": dict(row)}
    snapshot = dict(row)
    cur.execute(
        """
        INSERT INTO employment_applicability_events(snapshot_id, company_code, employee_key, event_type, actor_user_id, payload)
        VALUES (%s,%s,%s,'created',%s,%s)
        """,
        (
            snapshot["snapshot_id"],
            company,
            employee_key,
            actor_user_id,
            _json(legacy, {"source_path": payload["source_path"], "snapshot_hash": snap_hash}),
        ),
    )
    # Seed empty identity shell (category unspecified until HR confirms).
    cur.execute(
        """
        INSERT INTO employee_identity(company_code, employee_key, employee_category)
        VALUES (%s,%s,'unspecified')
        ON CONFLICT (company_code, employee_key) DO NOTHING
        """,
        (company, employee_key),
    )
    return {"ok": True, "idempotent": False, "snapshot": snapshot}


def get_applicability_snapshot(legacy: Any, *, company_code: str, employee_key: str) -> dict[str, Any] | None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_foundation_schema(cur)
            cur.execute(
                """
                SELECT * FROM employment_applicability_snapshots
                WHERE company_code=%s AND employee_key=%s
                """,
                (_company(company_code), employee_key),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def link_arabic_contract_to_snapshot(
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    file_id: str,
    template_id: str,
    template_version: str,
    template_approval_ref: str,
    document_language: str,
    effective_date: str | date | None,
    authorized_signatory: str,
    actor_user_id: str | None = None,
    permissions: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Upload-based Arabic contract path — no generated legal text."""
    _require(permissions, IDENTITY_WRITE)
    company = _company(company_code)
    lang = str(document_language or "").strip().lower()
    if lang not in {"ar", "arabic"}:
        raise FoundationError("arabic_contract_language_required", "document_language must be ar")
    if not str(file_id or "").strip():
        raise FoundationError("arabic_contract_file_required")
    if not str(template_id or "").strip() or not str(template_version or "").strip():
        raise FoundationError("arabic_contract_template_required")
    if not str(template_approval_ref or "").strip():
        raise FoundationError("arabic_contract_approval_ref_required")
    if not str(authorized_signatory or "").strip():
        raise FoundationError("arabic_contract_signatory_required")
    meta = {
        "template_id": template_id,
        "template_version": template_version,
        "template_approval_ref": template_approval_ref,
        "document_language": "ar",
        "effective_date": str(effective_date or "")[:10] or None,
        "authorized_signatory": authorized_signatory,
        "generation": "upload_only",
        "rtl_verified": True,
    }
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_foundation_schema(cur)
            cur.execute(
                """
                UPDATE employment_applicability_snapshots
                SET arabic_contract_file_id=%s,
                    arabic_contract_metadata=%s,
                    document_language=COALESCE(document_language, 'ar'),
                    template_id=COALESCE(template_id, %s),
                    template_version=COALESCE(template_version, %s),
                    template_approval_ref=COALESCE(template_approval_ref, %s)
                WHERE company_code=%s AND employee_key=%s
                RETURNING *
                """,
                (
                    file_id,
                    _json(legacy, meta),
                    template_id,
                    template_version,
                    template_approval_ref,
                    company,
                    employee_key,
                ),
            )
            row = cur.fetchone()
            if not row:
                raise FoundationError("snapshot_not_found", status_code=404)
            cur.execute(
                """
                INSERT INTO employment_applicability_events(snapshot_id, company_code, employee_key, event_type, actor_user_id, payload)
                VALUES (%s,%s,%s,'arabic_contract_linked',%s,%s)
                """,
                (row["snapshot_id"], company, employee_key, actor_user_id, _json(legacy, meta)),
            )
            # Document metadata row (not master fields).
            cur.execute(
                """
                INSERT INTO employee_document_metadata(
                  company_code, employee_key, document_type, file_id, verification_status,
                  source, notes, issue_date, hr_reviewer_user_id
                )
                VALUES (%s,%s,'employment_contract',%s,'hr_confirmed','arabic_upload',%s,%s,%s)
                """,
                (
                    company,
                    employee_key,
                    file_id,
                    f"approval_ref={template_approval_ref}",
                    meta.get("effective_date"),
                    actor_user_id,
                ),
            )
        conn.commit()
    return dict(row)


# --------------------------------------------------------------------------- #
# Employee identity
# --------------------------------------------------------------------------- #


def default_requiredness_for_category(category: str) -> dict[str, bool]:
    if category == "kuwaiti_national":
        return {
            "civil_id_number": True,
            "nationality_country_code": True,
            "passport_number": False,
            "residence_number": False,
            "work_permit_number": False,
        }
    if category == "article_18_expatriate":
        return {
            "civil_id_number": True,
            "nationality_country_code": True,
            "passport_number": True,
            "residence_number": True,
            "work_permit_number": True,
        }
    return {
        "civil_id_number": False,
        "nationality_country_code": False,
        "passport_number": False,
        "residence_number": False,
        "work_permit_number": False,
    }


def compliance_seed_types_for_category(
    category: str | None,
    *,
    country_code: str | None = None,
) -> tuple[str, ...]:
    """Category seeds. KW-specific residence/work_permit only for KW Art.18 category."""
    cat = str(category or "unspecified")
    country = str(country_code or "").strip().upper()
    if cat == "kuwaiti_national":
        return ("civil_id",) if country in {"", "KW"} else ("passport",)
    if cat == "article_18_expatriate":
        if country and country != "KW":
            raise FoundationError("employee_category_country_mismatch")
        return ("civil_id", "passport", CANONICAL_RESIDENCE, "work_permit")
    # Generic / unspecified: national-id + passport checklist only — no KW residence assumption.
    return ("civil_id", "passport")


def present_identity(
    row: Mapping[str, Any],
    *,
    permissions: Iterable[str] | None,
) -> dict[str, Any]:
    perms = set(permissions or ())
    can_full = IDENTITY_READ_FULL in perms
    can_read = can_full or IDENTITY_READ in perms
    if not can_read:
        raise FoundationError("permission_denied", status_code=403)

    def field(enc_key: str, last4_key: str, confirmed_key: str) -> dict[str, Any]:
        enc = row.get(enc_key)
        last4 = row.get(last4_key)
        confirmed = bool(row.get(confirmed_key))
        full = decrypt_identifier(enc) if can_full and enc else None
        return {
            "masked": mask_identifier(full) if full else (f"****{last4}" if last4 else None),
            "value": full,
            "confirmed": confirmed,
            "has_value": bool(enc),
        }

    ocr = row.get("ocr_pending") if isinstance(row.get("ocr_pending"), dict) else {}
    profile = str(row.get("identity_profile") or "generic")
    out = {
        "employee_key": row.get("employee_key"),
        "company_code": row.get("company_code"),
        "identity_profile": profile,
        "employee_category": row.get("employee_category"),
        "nationality_country_code": row.get("nationality_country_code"),
        # national_id slot; KW profile also exposes civil_id_number alias below.
        "national_id_number": field("civil_id_encrypted", "civil_id_last4", "civil_id_confirmed"),
        "passport_number": field("passport_number_encrypted", "passport_last4", "passport_confirmed"),
        "ocr_pending": ocr if can_full else {k: {"pending": True} for k in ocr.keys()},
        "requiredness_policy": row.get("requiredness_policy") or {},
    }
    if profile == "kw_civil_id" or profile == "generic":
        # KW first-client presentation; generic keeps civil_id_number for pilot API compat.
        out["civil_id_number"] = out["national_id_number"]
    if profile == "kw_civil_id":
        out["residence_number"] = field("residence_number_encrypted", "residence_last4", "residence_confirmed")
        out["work_permit_number"] = field(
            "work_permit_number_encrypted", "work_permit_last4", "work_permit_confirmed"
        )
    else:
        # Non-KW profiles must not assume residence/work_permit master fields.
        out["residence_number"] = {"masked": None, "value": None, "confirmed": False, "has_value": False}
        out["work_permit_number"] = {"masked": None, "value": None, "confirmed": False, "has_value": False}
    return out


def set_employee_category(
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    category: str,
    actor_user_id: str | None = None,
    permissions: Iterable[str] | None = None,
    country_code: str | None = None,
) -> dict[str, Any]:
    _require(permissions, IDENTITY_WRITE)
    company = _company(company_code)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_foundation_schema(cur)
            resolved_country = str(country_code or "").strip().upper() or resolve_company_country(cur, company)
            assert_category_allowed_for_country(category, resolved_country)
            profile = str((country_profile(resolved_country) or {}).get("identity_profile") or "generic")
            policy = default_requiredness_for_category(category)
            cur.execute(
                """
                INSERT INTO employee_identity(company_code, employee_key, employee_category, identity_profile, requiredness_policy)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (company_code, employee_key) DO UPDATE SET
                  employee_category=EXCLUDED.employee_category,
                  identity_profile=EXCLUDED.identity_profile,
                  requiredness_policy=EXCLUDED.requiredness_policy,
                  updated_at=now()
                RETURNING *
                """,
                (company, employee_key, category, profile, _json(legacy, policy)),
            )
            row = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO employee_identity_events(company_code, employee_key, field_name, event_type, actor_user_id, payload)
                VALUES (%s,%s,'employee_category','set',%s,%s)
                """,
                (company, employee_key, actor_user_id, _json(legacy, {"category": category})),
            )
        conn.commit()
    return row


def stage_ocr_identity_value(
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    field_name: str,
    value: str,
    actor_user_id: str | None = None,
    permissions: Iterable[str] | None = None,
) -> dict[str, Any]:
    """OCR values stay non-authoritative until HR confirms."""
    _require(permissions, IDENTITY_WRITE)
    if field_name not in SENSITIVE_IDENTITY_FIELDS and field_name != "nationality_country_code":
        raise FoundationError("field_invalid")
    company = _company(company_code)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_foundation_schema(cur)
            cur.execute(
                """
                INSERT INTO employee_identity(company_code, employee_key)
                VALUES (%s,%s)
                ON CONFLICT DO NOTHING
                """,
                (company, employee_key),
            )
            cur.execute(
                "SELECT ocr_pending FROM employee_identity WHERE company_code=%s AND employee_key=%s FOR UPDATE",
                (company, employee_key),
            )
            row = cur.fetchone() or {}
            pending = dict(row.get("ocr_pending") or {})
            pending[field_name] = {
                "value": str(value),
                "staged_at": _now().isoformat(),
                "confirmed": False,
                "source": "ocr",
            }
            cur.execute(
                """
                UPDATE employee_identity SET ocr_pending=%s, updated_at=now()
                WHERE company_code=%s AND employee_key=%s
                RETURNING *
                """,
                (_json(legacy, pending), company, employee_key),
            )
            updated = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO employee_identity_events(company_code, employee_key, field_name, event_type, actor_user_id, payload)
                VALUES (%s,%s,%s,'ocr_staged',%s,%s)
                """,
                (company, employee_key, field_name, actor_user_id, _json(legacy, {"non_authoritative": True})),
            )
        conn.commit()
    return updated


def confirm_identity_field(
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    field_name: str,
    value: str | None = None,
    actor_user_id: str | None = None,
    permissions: Iterable[str] | None = None,
) -> dict[str, Any]:
    """HR confirmation promotes OCR or explicit value to authoritative encrypted storage."""
    _require(permissions, IDENTITY_WRITE)
    company = _company(company_code)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_foundation_schema(cur)
            cur.execute(
                "SELECT * FROM employee_identity WHERE company_code=%s AND employee_key=%s FOR UPDATE",
                (company, employee_key),
            )
            row = cur.fetchone()
            if not row:
                raise FoundationError("identity_not_found", status_code=404)
            pending = dict(row.get("ocr_pending") or {})
            raw = value
            if raw is None and field_name in pending:
                raw = (pending.get(field_name) or {}).get("value")
            if raw is None and field_name == "nationality_country_code":
                raise FoundationError("value_required")
            if field_name == "nationality_country_code":
                code = str(raw or "").strip().upper()
                if not re.fullmatch(r"[A-Z]{2}", code):
                    raise FoundationError("nationality_invalid")
                cur.execute(
                    """
                    UPDATE employee_identity
                    SET nationality_country_code=%s, updated_at=now(),
                        ocr_pending = ocr_pending - %s
                    WHERE company_code=%s AND employee_key=%s
                    RETURNING *
                    """,
                    (code, field_name, company, employee_key),
                )
            elif field_name in SENSITIVE_IDENTITY_FIELDS:
                text = str(raw or "").strip()
                if not text:
                    raise FoundationError("value_required")
                enc = encrypt_identifier(text)
                last4 = text[-4:]
                col_map = {
                    "civil_id_number": ("civil_id_encrypted", "civil_id_last4", "civil_id_confirmed"),
                    "passport_number": ("passport_number_encrypted", "passport_last4", "passport_confirmed"),
                    "residence_number": ("residence_number_encrypted", "residence_last4", "residence_confirmed"),
                    "work_permit_number": ("work_permit_number_encrypted", "work_permit_last4", "work_permit_confirmed"),
                }
                enc_col, last4_col, conf_col = col_map[field_name]
                cur.execute(
                    f"""
                    UPDATE employee_identity
                    SET {enc_col}=%s, {last4_col}=%s, {conf_col}=true, updated_at=now(),
                        ocr_pending = ocr_pending - %s
                    WHERE company_code=%s AND employee_key=%s
                    RETURNING *
                    """,
                    (enc, last4, field_name, company, employee_key),
                )
            else:
                raise FoundationError("field_invalid")
            updated = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO employee_identity_events(company_code, employee_key, field_name, event_type, actor_user_id, payload)
                VALUES (%s,%s,%s,'hr_confirmed',%s,%s)
                """,
                (company, employee_key, field_name, actor_user_id, _json(legacy, {"confirmed": True})),
            )
        conn.commit()
    return updated


def get_employee_identity(
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    permissions: Iterable[str] | None = None,
) -> dict[str, Any]:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_foundation_schema(cur)
            cur.execute(
                "SELECT * FROM employee_identity WHERE company_code=%s AND employee_key=%s",
                (_company(company_code), employee_key),
            )
            row = cur.fetchone()
    if not row:
        raise FoundationError("identity_not_found", status_code=404)
    return present_identity(dict(row), permissions=permissions)


# --------------------------------------------------------------------------- #
# Document metadata (non-master)
# --------------------------------------------------------------------------- #


def upsert_document_metadata(
    legacy: Any,
    *,
    company_code: str,
    employee_key: str,
    document_type: str,
    issuing_authority: str | None = None,
    issue_date: str | date | None = None,
    expiry_date: str | date | None = None,
    file_id: str | None = None,
    file_version: str | None = None,
    verification_status: str = "unverified",
    hr_reviewer_user_id: str | None = None,
    source: str | None = None,
    notes: str | None = None,
    permissions: Iterable[str] | None = None,
) -> dict[str, Any]:
    _require(permissions, IDENTITY_WRITE)
    dtype = normalize_document_type(document_type)
    if is_government_process_attachment(dtype):
        raise FoundationError(
            "government_process_attachment_not_master",
            "Police/blood/lease attachments stay onboarding-only; not employee document metadata master types.",
        )
    if dtype in LEGACY_RESIDENCE_ALIASES:
        dtype = CANONICAL_RESIDENCE
    company = _company(company_code)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_foundation_schema(cur)
            cur.execute(
                """
                INSERT INTO employee_document_metadata(
                  company_code, employee_key, document_type, issuing_authority,
                  issue_date, expiry_date, file_id, file_version, verification_status,
                  hr_reviewer_user_id, source, notes
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    company,
                    employee_key,
                    dtype,
                    issuing_authority,
                    str(issue_date)[:10] if issue_date else None,
                    str(expiry_date)[:10] if expiry_date else None,
                    file_id,
                    file_version,
                    verification_status,
                    hr_reviewer_user_id,
                    source,
                    notes,
                ),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return row


def onboarding_item_id_for_document_type(document_type: str) -> str:
    """Canonical onboarding item ids for new Kuwait records."""
    dtype = normalize_document_type(document_type)
    if dtype == CANONICAL_RESIDENCE:
        return CANONICAL_RESIDENCE
    return dtype


def resolve_compat_document_type(document_type: str | None) -> str:
    return normalize_document_type(document_type)


def historical_residence_types() -> tuple[str, ...]:
    return (CANONICAL_RESIDENCE, "residency", "residency_iqama")
