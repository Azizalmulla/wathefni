"""Migration & Sync P2 — three-layer field model.

Layers:
  1) Canonical Wathefni fields (domain writers + authority)
  2) Company custom field definitions/values
  3) Raw source payload / provenance (never silently discard)

Mapping profiles are reusable per (company, source_system).
Custom fields must not hold bank/identity/lifecycle/compliance concepts.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import schema_contract

CONTRACT = "employee_migration_sync_p2_field_model"
CONTRACT_VERSION = "2.0.0"
SCHEMA_LOCK_ID = 770_911_222

DISPOSITIONS = frozenset({"canonical", "custom", "create_custom", "source_only", "ignore"})

# Canonical registry — field_key -> metadata
CANONICAL_FIELDS: dict[str, dict[str, Any]] = {
    # Roster (P1)
    "name": {"domain": "roster", "authority": "roster_safe", "sensitivity": "pii", "aliases": ["full_name", "employee_name", "اسم"]},
    "phone": {"domain": "roster", "authority": "roster_safe", "sensitivity": "pii", "aliases": ["mobile", "whatsapp", "phone_number", "mobile_number"]},
    "email": {"domain": "roster", "authority": "roster_safe", "sensitivity": "pii", "aliases": ["email_address", "work_email", "e_mail"]},
    "position_title": {"domain": "roster", "authority": "roster_safe", "sensitivity": "public", "aliases": ["job_title", "title", "position", "role", "designation"]},
    "department": {"domain": "roster", "authority": "roster_safe", "sensitivity": "public", "aliases": ["team", "dept", "division"]},
    "start_date": {"domain": "roster", "authority": "roster_safe", "sensitivity": "public", "aliases": ["hire_date", "joining_date", "start"]},
    "manager_phone": {"domain": "roster", "authority": "roster_safe", "sensitivity": "pii", "aliases": ["manager", "reports_to", "line_manager", "manager_mobile"]},
    "external_employee_id": {"domain": "roster", "authority": "roster_safe", "sensitivity": "public", "aliases": ["external_id", "employee_id", "emp_id", "ats_id", "source_employee_id"]},
    "payroll_id": {"domain": "roster", "authority": "roster_safe", "sensitivity": "public", "aliases": ["payroll_employee_id", "pay_id"]},
    "source_system": {"domain": "roster", "authority": "roster_safe", "sensitivity": "public", "aliases": ["source", "system", "hris"]},
    # Identity (P2) — never custom
    "civil_id": {"domain": "identity", "authority": "imported_non_authoritative", "sensitivity": "sensitive_id", "aliases": ["civil_id_number", "national_id", "kuwait_civil_id", "cid"]},
    "passport_number": {"domain": "identity", "authority": "imported_non_authoritative", "sensitivity": "sensitive_id", "aliases": ["passport", "passport_no"]},
    "nationality": {"domain": "identity", "authority": "imported_non_authoritative", "sensitivity": "pii", "aliases": ["nationality_country_code", "nationality_code", "country_of_nationality"]},
    "employee_category": {"domain": "identity", "authority": "needs_review_if_conflict", "sensitivity": "public", "aliases": ["category", "worker_category"]},
    # Contacts
    "address_line1": {"domain": "contacts", "authority": "imported_non_authoritative", "sensitivity": "pii", "aliases": ["address", "street", "address1"]},
    "address_line2": {"domain": "contacts", "authority": "imported_non_authoritative", "sensitivity": "pii", "aliases": ["address2", "street2"]},
    "city": {"domain": "contacts", "authority": "imported_non_authoritative", "sensitivity": "pii", "aliases": ["town"]},
    "governorate": {"domain": "contacts", "authority": "imported_non_authoritative", "sensitivity": "pii", "aliases": ["state", "province", "area"]},
    "country": {"domain": "contacts", "authority": "imported_non_authoritative", "sensitivity": "pii", "aliases": ["country_code", "country_name"]},
    "postal_code": {"domain": "contacts", "authority": "imported_non_authoritative", "sensitivity": "pii", "aliases": ["zip", "zip_code", "postcode"]},
    "emergency_contact_name": {"domain": "contacts", "authority": "imported_non_authoritative", "sensitivity": "pii", "aliases": ["emergency_name", "next_of_kin"]},
    "emergency_contact_phone": {"domain": "contacts", "authority": "imported_non_authoritative", "sensitivity": "pii", "aliases": ["emergency_phone", "emergency_mobile"]},
    "emergency_contact_relation": {"domain": "contacts", "authority": "imported_non_authoritative", "sensitivity": "pii", "aliases": ["emergency_relation", "relationship"]},
    # Employment
    "employment_status": {"domain": "employment", "authority": "lifecycle_review_only", "sensitivity": "public", "aliases": ["status", "employee_status", "hr_status"]},
    # Bank — proposed only
    "bank_iban": {"domain": "bank", "authority": "bank_proposed_only", "sensitivity": "bank", "aliases": ["iban"]},
    "bank_name": {"domain": "bank", "authority": "bank_proposed_only", "sensitivity": "bank", "aliases": ["bank"]},
    "bank_account_holder": {"domain": "bank", "authority": "bank_proposed_only", "sensitivity": "bank", "aliases": ["account_holder", "beneficiary_name"]},
    "bank_swift": {"domain": "bank", "authority": "bank_proposed_only", "sensitivity": "bank", "aliases": ["swift", "bic", "swift_code"]},
    "bank_account_number": {"domain": "bank", "authority": "bank_proposed_only", "sensitivity": "bank", "aliases": ["account_number", "account_no"]},
    # Documents / compliance metadata
    "document_type": {"domain": "documents", "authority": "imported_non_authoritative", "sensitivity": "public", "aliases": ["doc_type"]},
    "document_number": {"domain": "documents", "authority": "imported_non_authoritative", "sensitivity": "pii", "aliases": ["doc_number"]},
    "document_issue_date": {"domain": "documents", "authority": "imported_non_authoritative", "sensitivity": "public", "aliases": ["issue_date", "doc_issue_date"]},
    "document_expiry": {"domain": "documents", "authority": "imported_non_authoritative", "sensitivity": "public", "aliases": ["expiry_date", "doc_expiry", "document_expiry_date"]},
    "compliance_doc_type": {"domain": "compliance", "authority": "imported_non_authoritative", "sensitivity": "public", "aliases": ["compliance_type"]},
    "compliance_status": {"domain": "compliance", "authority": "imported_non_authoritative", "sensitivity": "public", "aliases": []},
    "compliance_expiry": {"domain": "compliance", "authority": "imported_non_authoritative", "sensitivity": "public", "aliases": ["compliance_expiry_date"]},
    # Onboarding migration (P3) — canonical only; never custom
    "onboarding_migration_disposition": {
        "domain": "onboarding",
        "authority": "imported_non_authoritative",
        "sensitivity": "public",
        "aliases": ["onboarding_disposition", "migration_onboarding_state"],
    },
    "onboarding_status": {
        "domain": "onboarding",
        "authority": "imported_non_authoritative",
        "sensitivity": "public",
        "aliases": ["onboarding_state", "hr_onboarding_status"],
    },
    "onboarding_completed_at": {
        "domain": "onboarding",
        "authority": "imported_non_authoritative",
        "sensitivity": "public",
        "aliases": ["onboarding_completion_date", "onboarded_at", "onboarding_date"],
    },
    "onboarding_history": {
        "domain": "onboarding",
        "authority": "imported_non_authoritative",
        "sensitivity": "public",
        "aliases": ["onboarding_tasks", "onboarding_checklist_history"],
    },
    "onboarding_start_after_import": {
        "domain": "onboarding",
        "authority": "lifecycle_review_only",
        "sensitivity": "public",
        "aliases": ["start_onboarding_after_import", "start_wathefni_onboarding"],
    },
}

# P4 cutover fields merge into the canonical registry (same 3-layer model).
try:
    import employee_migration_cutover as _cutover

    for _k, _meta in _cutover.CUTOVER_CANONICAL_FIELDS.items():
        CANONICAL_FIELDS.setdefault(_k, _meta)
except Exception:
    pass

RESERVED_CUSTOM_KEYS = frozenset(CANONICAL_FIELDS.keys()) | frozenset(
    {
        "iban",
        "civil_id_number",
        "national_id",
        "passport",
        "leave_balance",
        "onboarding_status",
        "salary",
        "basic_salary",
        "monthly_salary",
        "leave_opening_balance",
        "shift_assignments",
    }
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS employee_custom_field_definitions (
  field_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  field_key text NOT NULL,
  label_en text NOT NULL,
  label_ar text,
  value_type text NOT NULL DEFAULT 'text',
  enum_values jsonb NOT NULL DEFAULT '[]'::jsonb,
  description text,
  active boolean NOT NULL DEFAULT true,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, field_key),
  CHECK (field_key ~ '^[a-z][a-z0-9_]{0,63}$'),
  CHECK (value_type = ANY (ARRAY['text','number','date','boolean','enum']))
);
CREATE INDEX IF NOT EXISTS idx_employee_custom_field_defs_company
  ON employee_custom_field_definitions(company_code, active);

CREATE TABLE IF NOT EXISTS employee_custom_field_values (
  company_code text NOT NULL,
  employee_key text NOT NULL,
  field_id uuid NOT NULL REFERENCES employee_custom_field_definitions(field_id) ON DELETE CASCADE,
  value_text text,
  value_json jsonb,
  authority text NOT NULL DEFAULT 'imported',
  source_system text,
  source_batch_id uuid,
  source_row_id uuid,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, employee_key, field_id)
);
CREATE INDEX IF NOT EXISTS idx_employee_custom_field_values_batch
  ON employee_custom_field_values(source_batch_id);

CREATE TABLE IF NOT EXISTS employee_import_source_payloads (
  payload_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  batch_id uuid NOT NULL REFERENCES employee_import_batches(batch_id) ON DELETE CASCADE,
  row_id uuid,
  row_number integer NOT NULL,
  source_system text,
  external_employee_id text,
  headers jsonb NOT NULL DEFAULT '[]'::jsonb,
  values jsonb NOT NULL DEFAULT '{}'::jsonb,
  received_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (batch_id, row_number)
);
CREATE INDEX IF NOT EXISTS idx_employee_import_source_payloads_batch
  ON employee_import_source_payloads(batch_id);

CREATE TABLE IF NOT EXISTS employee_import_mapping_profiles (
  profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  source_system text NOT NULL,
  name text,
  status text NOT NULL DEFAULT 'draft',
  version integer NOT NULL DEFAULT 1,
  mappings jsonb NOT NULL DEFAULT '[]'::jsonb,
  unmapped_policy text NOT NULL DEFAULT 'retain_source_only',
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  confirmed_at timestamptz,
  UNIQUE (company_code, source_system, version),
  CHECK (status = ANY (ARRAY['draft','active','archived'])),
  CHECK (unmapped_policy = ANY (ARRAY['retain_source_only','ignore']))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_employee_import_mapping_profiles_active
  ON employee_import_mapping_profiles(company_code, source_system)
  WHERE status = 'active';

CREATE TABLE IF NOT EXISTS employee_migration_imported_bank (
  import_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  batch_id uuid NOT NULL,
  row_id uuid,
  proposed_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  authority text NOT NULL DEFAULT 'imported_proposed',
  source_system text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, employee_key, batch_id)
);
CREATE INDEX IF NOT EXISTS idx_employee_migration_imported_bank_emp
  ON employee_migration_imported_bank(company_code, employee_key);

CREATE TABLE IF NOT EXISTS employee_migration_imported_compliance (
  import_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  batch_id uuid NOT NULL,
  row_id uuid,
  doc_type text,
  status text,
  expiry_date text,
  authority text NOT NULL DEFAULT 'imported_evidence',
  source_system text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_employee_migration_imported_compliance_batch
  ON employee_migration_imported_compliance(batch_id);
"""

ALTER_SQL = """
ALTER TABLE employee_import_batches
  ADD COLUMN IF NOT EXISTS mapping_profile_id uuid,
  ADD COLUMN IF NOT EXISTS mapping_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE employee_import_rows
  ADD COLUMN IF NOT EXISTS source_payload jsonb NOT NULL DEFAULT '{}'::jsonb;
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def normalize_header(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "_", text).strip("_")
    return text


def slugify_field_key(value: Any) -> str:
    base = normalize_header(value)
    if not base:
        return ""
    if base[0].isdigit():
        base = f"f_{base}"
    return base[:64]


_FIELD_SCHEMA_READY = False


def ensure_field_model_schema(cur: Any, *, force: bool = False) -> None:
    global _FIELD_SCHEMA_READY
    if _FIELD_SCHEMA_READY and not force:
        return
    schema_contract.ensure_sql(
        cur,
        SCHEMA_SQL,
        required_tables=[
            "employee_custom_field_definitions",
            "employee_custom_field_values",
            "employee_import_source_payloads",
            "employee_import_mapping_profiles",
            "employee_migration_imported_bank",
            "employee_migration_imported_compliance",
        ],
        module="employee_migration_field_model",
        lock_id=None,
    )
    # Additive alters — CREATE TABLE IF NOT EXISTS alone would skip new columns.
    for stmt in ALTER_SQL.strip().split(";"):
        sql = stmt.strip()
        if sql:
            cur.execute(sql)
    _FIELD_SCHEMA_READY = True


def honesty_payload() -> dict[str, Any]:
    return {
        "contract": CONTRACT,
        "version": CONTRACT_VERSION,
        "layers": ["canonical", "company_custom", "raw_source_payload"],
        "mapping_profiles": True,
        "unmapped_retains_source": True,
        "no_silent_ambiguous_map": True,
        "custom_fields_not_for_bank_identity_lifecycle": True,
        "bank_proposed_only": True,
        "identity_imported_non_authoritative": True,
        "no_invites": True,
        "no_auto_onboarding": True,
        "no_auto_compliance_seed": True,
        "canonical_fields": sorted(CANONICAL_FIELDS.keys()),
    }


def _alias_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for key, meta in CANONICAL_FIELDS.items():
        idx[normalize_header(key)] = key
        for alias in meta.get("aliases") or []:
            idx[normalize_header(alias)] = key
    return idx


ALIAS_TO_CANONICAL = _alias_index()


def suggest_mapping_for_headers(
    headers: list[str],
    *,
    existing_custom_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Auto-suggest dispositions. Ambiguous/low-confidence stays source_only unconfirmed."""
    custom_keys = {normalize_header(k) for k in (existing_custom_keys or set())}
    seen_canonical: set[str] = set()
    rules: list[dict[str, Any]] = []
    for header in headers:
        original = str(header or "").strip()
        if not original:
            continue
        norm = normalize_header(original)
        canonical = ALIAS_TO_CANONICAL.get(norm)
        confidence = 0.0
        disposition = "source_only"
        custom_key = None
        confirmed = False
        suggested = False
        if canonical and canonical not in seen_canonical:
            # Exact alias match is high confidence but still editable by HR.
            confidence = 0.98 if norm == normalize_header(canonical) else 0.92
            if confidence >= 0.9:
                disposition = "canonical"
                suggested = True
                confirmed = True  # high-confidence prefilled; HR can change before save
                seen_canonical.add(canonical)
            else:
                canonical = None
                disposition = "source_only"
        elif norm in custom_keys:
            disposition = "custom"
            custom_key = norm
            confidence = 0.9
            suggested = True
            confirmed = False
            canonical = None
        else:
            canonical = None
        rules.append(
            {
                "source_header": original,
                "source_header_normalized": norm,
                "disposition": disposition,
                "canonical_field": canonical,
                "custom_field_key": custom_key,
                "custom_field_label_en": original if disposition in {"custom", "create_custom"} else None,
                "custom_field_label_ar": None,
                "custom_value_type": "text",
                "suggested": suggested,
                "suggestion_confidence": confidence,
                "confirmed": confirmed,
            }
        )
    return rules


def validate_mapping_rules(rules: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    cleaned: list[dict[str, Any]] = []
    used_canonical: set[str] = set()
    for raw in rules or []:
        rule = dict(raw or {})
        disposition = str(rule.get("disposition") or "source_only").strip()
        if disposition not in DISPOSITIONS:
            errors.append(f"invalid disposition: {disposition}")
            continue
        header = str(rule.get("source_header") or "").strip()
        if not header:
            errors.append("mapping rule missing source_header")
            continue
        norm = str(rule.get("source_header_normalized") or normalize_header(header))
        canonical = rule.get("canonical_field")
        custom_key = slugify_field_key(rule.get("custom_field_key") or "")
        if disposition == "canonical":
            if not canonical or canonical not in CANONICAL_FIELDS:
                errors.append(f"{header}: canonical_field required")
                continue
            if canonical in used_canonical:
                errors.append(f"{header}: canonical field {canonical} already mapped")
                continue
            used_canonical.add(str(canonical))
            custom_key = None
        elif disposition in {"custom", "create_custom"}:
            if not custom_key:
                custom_key = slugify_field_key(header)
            if not custom_key:
                errors.append(f"{header}: custom_field_key required")
                continue
            if custom_key in RESERVED_CUSTOM_KEYS:
                errors.append(f"{header}: '{custom_key}' is reserved for canonical Wathefni fields")
                continue
            canonical = None
        else:
            canonical = None
            custom_key = None
        cleaned.append(
            {
                "source_header": header,
                "source_header_normalized": norm,
                "disposition": disposition,
                "canonical_field": canonical,
                "custom_field_key": custom_key,
                "custom_field_label_en": rule.get("custom_field_label_en") or header,
                "custom_field_label_ar": rule.get("custom_field_label_ar"),
                "custom_value_type": rule.get("custom_value_type") or "text",
                "suggested": bool(rule.get("suggested")),
                "suggestion_confidence": float(rule.get("suggestion_confidence") or 0),
                "confirmed": bool(rule.get("confirmed")),
            }
        )
    return cleaned, errors


def mapping_summary(rules: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {d: 0 for d in DISPOSITIONS}
    unmapped: list[str] = []
    for rule in rules:
        d = str(rule.get("disposition") or "source_only")
        counts[d] = counts.get(d, 0) + 1
        if d in {"source_only", "ignore"} or not rule.get("confirmed"):
            if d in {"source_only", "ignore"}:
                unmapped.append(str(rule.get("source_header")))
    return {
        "counts": counts,
        "unmapped_headers": unmapped,
        "unmapped_count": len(unmapped),
        "total_headers": len(rules),
    }


def apply_mapping_to_source_values(
    values: dict[str, Any],
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    """Split one row's source values into canonical / custom / source_only buckets."""
    by_header = {str(k): ("" if v is None else str(v).strip()) for k, v in (values or {}).items()}
    canonical: dict[str, str] = {}
    custom: list[dict[str, Any]] = []
    source_only: dict[str, str] = {}
    for rule in rules:
        header = str(rule.get("source_header") or "")
        raw_val = by_header.get(header, "")
        if not raw_val:
            # Missing = not supplied
            continue
        disposition = rule.get("disposition")
        if disposition == "canonical" and rule.get("confirmed") and rule.get("canonical_field"):
            canonical[str(rule["canonical_field"])] = raw_val
        elif disposition in {"custom", "create_custom"} and rule.get("confirmed"):
            custom.append(
                {
                    "field_key": rule.get("custom_field_key"),
                    "label_en": rule.get("custom_field_label_en"),
                    "label_ar": rule.get("custom_field_label_ar"),
                    "value_type": rule.get("custom_value_type") or "text",
                    "create": disposition == "create_custom",
                    "value": raw_val,
                    "source_header": header,
                }
            )
        else:
            source_only[header] = raw_val
    return {"canonical": canonical, "custom": custom, "source_only": source_only}


def list_custom_field_keys(cur: Any, company: str) -> set[str]:
    cur.execute(
        """
        SELECT field_key FROM employee_custom_field_definitions
        WHERE company_code=%s AND active IS TRUE
        """,
        (company,),
    )
    return {str(r["field_key"] if isinstance(r, dict) else r[0]) for r in (cur.fetchall() or [])}


def get_active_mapping_profile(cur: Any, company: str, source_system: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM employee_import_mapping_profiles
        WHERE company_code=%s AND source_system=%s AND status='active'
        LIMIT 1
        """,
        (company, source_system),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def save_mapping_profile(
    legacy: Any,
    context: dict[str, Any],
    *,
    source_system: str,
    mappings: list[dict[str, Any]],
    name: str | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    source = str(source_system or "").strip() or "csv"
    cleaned, errors = validate_mapping_rules(mappings)
    if errors:
        raise legacy.HTTPException(status_code=422, detail={"error": "invalid_mapping", "messages": errors})
    actor = str(context.get("user_id") or context.get("email") or context.get("actor") or "")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_field_model_schema(cur)
            cur.execute(
                """
                SELECT COALESCE(MAX(version), 0) AS v
                FROM employee_import_mapping_profiles
                WHERE company_code=%s AND source_system=%s
                """,
                (company, source),
            )
            next_version = int((cur.fetchone() or {}).get("v") or 0) + 1
            if activate:
                cur.execute(
                    """
                    UPDATE employee_import_mapping_profiles
                    SET status='archived', updated_at=now()
                    WHERE company_code=%s AND source_system=%s AND status='active'
                    """,
                    (company, source),
                )
            cur.execute(
                """
                INSERT INTO employee_import_mapping_profiles (
                  company_code, source_system, name, status, version, mappings,
                  unmapped_policy, created_by, confirmed_at
                ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,'retain_source_only',%s, CASE WHEN %s THEN now() ELSE NULL END)
                RETURNING *
                """,
                (
                    company,
                    source,
                    name or f"{source} mapping",
                    "active" if activate else "draft",
                    next_version,
                    json.dumps(cleaned),
                    actor,
                    bool(activate),
                ),
            )
            row = dict(cur.fetchone())
            conn.commit()
    return {
        "ok": True,
        "profile": _jsonable(row),
        "summary": mapping_summary(cleaned),
        "honesty": honesty_payload(),
    }


def suggest_mapping_profile(
    legacy: Any,
    context: dict[str, Any],
    *,
    headers: list[str],
    source_system: str | None = None,
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    source = str(source_system or "").strip() or "csv"
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_field_model_schema(cur)
            existing = get_active_mapping_profile(cur, company, source)
            custom_keys = list_custom_field_keys(cur, company)
            conn.commit()
    if existing and existing.get("mappings"):
        rules = existing.get("mappings") or []
        if isinstance(rules, str):
            rules = json.loads(rules)
        # Merge any new headers as source_only suggestions
        known = {str(r.get("source_header")) for r in rules}
        for h in headers:
            if h not in known:
                rules.extend(suggest_mapping_for_headers([h], existing_custom_keys=custom_keys))
        return {
            "ok": True,
            "source_system": source,
            "from_saved_profile": True,
            "profile_id": str(existing.get("profile_id")),
            "mappings": _jsonable(rules),
            "summary": mapping_summary(rules),
            "honesty": honesty_payload(),
        }
    rules = suggest_mapping_for_headers(headers, existing_custom_keys=custom_keys)
    return {
        "ok": True,
        "source_system": source,
        "from_saved_profile": False,
        "profile_id": None,
        "mappings": _jsonable(rules),
        "summary": mapping_summary(rules),
        "honesty": honesty_payload(),
    }


def upsert_custom_value(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    field_key: str,
    label_en: str,
    label_ar: str | None,
    value_type: str,
    value: str,
    create: bool,
    source_system: str | None,
    batch_id: str,
    row_id: str,
    actor: str | None,
) -> dict[str, Any]:
    key = slugify_field_key(field_key)
    if key in RESERVED_CUSTOM_KEYS:
        return {"ok": False, "error": "reserved_custom_key", "field_key": key}
    cur.execute(
        """
        SELECT field_id, active FROM employee_custom_field_definitions
        WHERE company_code=%s AND field_key=%s
        """,
        (company, key),
    )
    existing = cur.fetchone()
    if not existing:
        if not create:
            return {"ok": False, "error": "custom_field_missing", "field_key": key}
        cur.execute(
            """
            INSERT INTO employee_custom_field_definitions (
              company_code, field_key, label_en, label_ar, value_type, created_by
            ) VALUES (%s,%s,%s,%s,%s,%s)
            RETURNING field_id
            """,
            (company, key, label_en or key, label_ar, value_type or "text", actor),
        )
        field_id = str((cur.fetchone() or {})["field_id"])
    else:
        field_id = str(existing["field_id"] if isinstance(existing, dict) else existing[0])
    cur.execute(
        """
        INSERT INTO employee_custom_field_values (
          company_code, employee_key, field_id, value_text, value_json,
          authority, source_system, source_batch_id, source_row_id, updated_at
        ) VALUES (%s,%s,%s,%s,%s::jsonb,'imported',%s,%s,%s,now())
        ON CONFLICT (company_code, employee_key, field_id) DO UPDATE SET
          value_text=EXCLUDED.value_text,
          value_json=EXCLUDED.value_json,
          authority='imported',
          source_system=EXCLUDED.source_system,
          source_batch_id=EXCLUDED.source_batch_id,
          source_row_id=EXCLUDED.source_row_id,
          updated_at=now()
        """,
        (
            company,
            employee_key,
            field_id,
            value,
            json.dumps({"value": value, "type": value_type or "text"}),
            source_system,
            batch_id,
            row_id,
        ),
    )
    return {"ok": True, "field_id": field_id, "field_key": key}


def persist_source_payload(
    cur: Any,
    *,
    company: str,
    batch_id: str,
    row_id: str | None,
    row_number: int,
    source_system: str | None,
    external_employee_id: str | None,
    headers: list[str],
    values: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO employee_import_source_payloads (
          company_code, batch_id, row_id, row_number, source_system,
          external_employee_id, headers, values
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
        ON CONFLICT (batch_id, row_number) DO UPDATE SET
          row_id=EXCLUDED.row_id,
          source_system=EXCLUDED.source_system,
          external_employee_id=EXCLUDED.external_employee_id,
          headers=EXCLUDED.headers,
          values=EXCLUDED.values,
          received_at=now()
        """,
        (
            company,
            batch_id,
            row_id,
            row_number,
            source_system,
            external_employee_id,
            json.dumps(headers),
            json.dumps(values),
        ),
    )


def _mask_iban(value: str) -> str:
    text = re.sub(r"\s+", "", str(value or "").upper())
    if len(text) < 8:
        return "••••"
    return f"{text[:4]}…{text[-4:]}"


def apply_deep_canonical_fields(
    legacy: Any,
    cur: Any,
    *,
    company: str,
    employee_key: str,
    canonical: dict[str, str],
    batch_id: str,
    row_id: str,
    source_system: str | None,
    actor: str | None,
) -> dict[str, Any]:
    """Apply P2 canonical deep fields with authority gates. Returns review/applied notes."""
    applied: list[str] = []
    review: list[dict[str, Any]] = []
    skipped: list[str] = []

    # --- Identity (stage non-authoritative) ---
    identity_pending: dict[str, Any] = {}
    if canonical.get("civil_id"):
        identity_pending["civil_id_number"] = canonical["civil_id"]
    if canonical.get("passport_number"):
        identity_pending["passport_number"] = canonical["passport_number"]
    if canonical.get("nationality"):
        identity_pending["nationality_country_code"] = canonical["nationality"].strip().upper()[:2]

    if identity_pending:
        try:
            import kuwait_first_client_foundation as kff

            cur.execute(
                """
                INSERT INTO employee_identity(company_code, employee_key)
                VALUES (%s,%s)
                ON CONFLICT DO NOTHING
                """,
                (company, employee_key),
            )
            cur.execute(
                """
                SELECT civil_id_confirmed, passport_confirmed, nationality_country_code, ocr_pending
                FROM employee_identity
                WHERE company_code=%s AND employee_key=%s
                FOR UPDATE
                """,
                (company, employee_key),
            )
            row = cur.fetchone() or {}
            pending = dict(row.get("ocr_pending") or {})
            if "civil_id_number" in identity_pending:
                if row.get("civil_id_confirmed"):
                    review.append(
                        {
                            "field": "civil_id",
                            "reason": "Civil ID already verified in Wathefni — import will not overwrite.",
                        }
                    )
                else:
                    pending["civil_id_number"] = {
                        "value": identity_pending["civil_id_number"],
                        "staged_at": _now().isoformat(),
                        "confirmed": False,
                        "source": "migration_import",
                        "batch_id": batch_id,
                        "row_id": row_id,
                    }
                    applied.append("civil_id_staged")
            if "passport_number" in identity_pending:
                if row.get("passport_confirmed"):
                    review.append(
                        {
                            "field": "passport_number",
                            "reason": "Passport already verified — import will not overwrite.",
                        }
                    )
                else:
                    pending["passport_number"] = {
                        "value": identity_pending["passport_number"],
                        "staged_at": _now().isoformat(),
                        "confirmed": False,
                        "source": "migration_import",
                        "batch_id": batch_id,
                        "row_id": row_id,
                    }
                    applied.append("passport_staged")
            if "nationality_country_code" in identity_pending:
                code = identity_pending["nationality_country_code"]
                existing_nat = str(row.get("nationality_country_code") or "").strip().upper()
                if existing_nat and existing_nat != code:
                    review.append(
                        {
                            "field": "nationality",
                            "reason": f"Nationality already set to {existing_nat} — import differs ({code}).",
                        }
                    )
                elif not existing_nat and re.fullmatch(r"[A-Z]{2}", code):
                    cur.execute(
                        """
                        UPDATE employee_identity
                        SET nationality_country_code=%s, updated_at=now()
                        WHERE company_code=%s AND employee_key=%s
                        """,
                        (code, company, employee_key),
                    )
                    applied.append("nationality")
                elif not re.fullmatch(r"[A-Z]{2}", code):
                    review.append({"field": "nationality", "reason": "Nationality must be a 2-letter country code."})
            cur.execute(
                """
                UPDATE employee_identity SET ocr_pending=%s::jsonb, updated_at=now()
                WHERE company_code=%s AND employee_key=%s
                """,
                (json.dumps(pending), company, employee_key),
            )
            cur.execute(
                """
                INSERT INTO employee_identity_events(
                  company_code, employee_key, field_name, event_type, actor_user_id, payload
                ) VALUES (%s,%s,'migration_import','staged',%s,%s::jsonb)
                """,
                (
                    company,
                    employee_key,
                    actor,
                    json.dumps({"batch_id": batch_id, "fields": sorted(identity_pending.keys()), "non_authoritative": True}),
                ),
            )
            del kff  # imported for side-effect availability / future encrypt helpers
        except Exception as exc:
            review.append({"field": "identity", "reason": f"Identity import deferred: {str(exc)[:160]}"})

    if canonical.get("employee_category"):
        # Do not invent categories; stamp for review if present
        review.append(
            {
                "field": "employee_category",
                "reason": "Employee category supplied — confirm against Wathefni category policy before applying.",
                "value": canonical["employee_category"],
            }
        )

    # --- Contacts / emergency via ESS personal profiles ---
    address_keys = ("address_line1", "address_line2", "city", "governorate", "country", "postal_code")
    emergency_keys = ("emergency_contact_name", "emergency_contact_phone", "emergency_contact_relation")
    profile_patch = {k: canonical[k] for k in address_keys if canonical.get(k)}
    emergency_patch = {}
    if canonical.get("emergency_contact_name"):
        emergency_patch["name"] = canonical["emergency_contact_name"]
    if canonical.get("emergency_contact_phone"):
        emergency_patch["phone"] = canonical["emergency_contact_phone"]
    if canonical.get("emergency_contact_relation"):
        emergency_patch["relation"] = canonical["emergency_contact_relation"]
    if profile_patch or emergency_patch:
        try:
            cur.execute(
                """
                SELECT profile_json, emergency_json, version
                FROM employee_ess_personal_profiles
                WHERE company_code=%s AND employee_key=%s
                FOR UPDATE
                """,
                (company, employee_key),
            )
            prow = cur.fetchone()
            profile = dict((prow or {}).get("profile_json") or {})
            emergency = dict((prow or {}).get("emergency_json") or {})
            version = int((prow or {}).get("version") or 0) + 1
            for k, v in profile_patch.items():
                if profile.get(k):
                    if str(profile.get(k)).strip() != str(v).strip():
                        review.append({"field": k, "reason": "Contact field already set in Wathefni — needs review."})
                    else:
                        skipped.append(k)
                else:
                    profile[k] = v
                    applied.append(k)
            for k, v in emergency_patch.items():
                if emergency.get(k):
                    if str(emergency.get(k)).strip() != str(v).strip():
                        review.append({"field": f"emergency_{k}", "reason": "Emergency contact already set — needs review."})
                    else:
                        skipped.append(f"emergency_{k}")
                else:
                    emergency[k] = v
                    applied.append(f"emergency_{k}")
            profile["_migration"] = {
                "batch_id": batch_id,
                "row_id": row_id,
                "authority": "imported",
                "source_system": source_system,
            }
            cur.execute(
                """
                INSERT INTO employee_ess_personal_profiles (
                  company_code, employee_key, profile_json, emergency_json, version, updated_at
                ) VALUES (%s,%s,%s::jsonb,%s::jsonb,%s,now())
                ON CONFLICT (company_code, employee_key) DO UPDATE SET
                  profile_json=EXCLUDED.profile_json,
                  emergency_json=EXCLUDED.emergency_json,
                  version=EXCLUDED.version,
                  updated_at=now()
                """,
                (company, employee_key, json.dumps(profile), json.dumps(emergency), version),
            )
        except Exception as contact_exc:
            review.append({"field": "contacts", "reason": f"Contacts import deferred: {str(contact_exc)[:160]}"})

    # --- Employment status: never deactivate ---
    if canonical.get("employment_status"):
        status_raw = canonical["employment_status"].strip().lower()
        if status_raw in {"terminated", "inactive", "leaved", "leaver", "dismissed", "resigned"}:
            review.append(
                {
                    "field": "employment_status",
                    "reason": "Leaver/inactive status from source requires explicit lifecycle review (no auto-deactivation).",
                    "value": canonical["employment_status"],
                }
            )
        else:
            cur.execute(
                """
                UPDATE employees
                SET raw_json = COALESCE(raw_json, '{}'::jsonb) || %s::jsonb, updated_at=now()
                WHERE company_code=%s AND employee_key=%s
                """,
                (
                    json.dumps(
                        {
                            "employment_status_imported": canonical["employment_status"],
                            "employment_status_imported_batch_id": batch_id,
                        }
                    ),
                    company,
                    employee_key,
                ),
            )
            applied.append("employment_status_imported")

    # --- Bank proposed-only staging (never verified/effective) ---
    bank_keys = ("bank_iban", "bank_name", "bank_account_holder", "bank_swift", "bank_account_number")
    bank_vals = {k: canonical[k] for k in bank_keys if canonical.get(k)}
    if bank_vals:
        proposed = {
            "iban_masked": _mask_iban(bank_vals["bank_iban"]) if bank_vals.get("bank_iban") else None,
            "iban_last4": (re.sub(r"\s+", "", bank_vals.get("bank_iban") or "")[-4:] or None),
            "bank_name": bank_vals.get("bank_name"),
            "account_holder": bank_vals.get("bank_account_holder"),
            "swift": bank_vals.get("bank_swift"),
            "account_number_last4": (re.sub(r"\s+", "", bank_vals.get("bank_account_number") or "")[-4:] or None),
            # Full IBAN stored sealed-style in proposed_json for HR Bank ESS handoff — not payroll-effective
            "iban": bank_vals.get("bank_iban"),
            "account_number": bank_vals.get("bank_account_number"),
            "authority": "imported_proposed",
            "batch_id": batch_id,
            "row_id": row_id,
        }
        cur.execute(
            """
            INSERT INTO employee_migration_imported_bank (
              company_code, employee_key, batch_id, row_id, proposed_json, source_system
            ) VALUES (%s,%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT (company_code, employee_key, batch_id) DO UPDATE SET
              proposed_json=EXCLUDED.proposed_json,
              row_id=EXCLUDED.row_id,
              source_system=EXCLUDED.source_system
            """,
            (company, employee_key, batch_id, row_id, json.dumps(proposed), source_system),
        )
        applied.append("bank_imported_proposed")
        review.append(
            {
                "field": "bank",
                "reason": "Bank details imported as proposed only — HR must verify via Bank ESS before payroll-effective.",
                "iban_masked": proposed.get("iban_masked"),
            }
        )

            # --- Documents metadata (unverified) ---
    if canonical.get("document_type") or canonical.get("document_expiry"):
        try:
            cur.execute(
                """
                INSERT INTO employee_document_metadata (
                  company_code, employee_key, document_type, issue_date, expiry_date,
                  verification_status, source, notes
                ) VALUES (
                  %s,%s,%s,
                  NULLIF(%s,'')::date,
                  NULLIF(%s,'')::date,
                  'unverified',
                  %s,
                  %s
                )
                """,
                (
                    company,
                    employee_key,
                    canonical.get("document_type") or "other",
                    canonical.get("document_issue_date") or "",
                    canonical.get("document_expiry") or "",
                    f"migration:{source_system or 'csv'}",
                    json.dumps(
                        {
                            "batch_id": batch_id,
                            "row_id": row_id,
                            "document_number": canonical.get("document_number"),
                            "authority": "imported_unverified",
                        }
                    ),
                ),
            )
            applied.append("document_metadata_unverified")
        except Exception as doc_exc:
            review.append({"field": "document", "reason": f"Document metadata deferred: {str(doc_exc)[:160]}"})

    # --- Compliance evidence import (no campaign seed) ---
    if canonical.get("compliance_doc_type") or canonical.get("compliance_status") or canonical.get("compliance_expiry"):
        cur.execute(
            """
            INSERT INTO employee_migration_imported_compliance (
              company_code, employee_key, batch_id, row_id, doc_type, status, expiry_date, source_system, payload
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                company,
                employee_key,
                batch_id,
                row_id,
                canonical.get("compliance_doc_type"),
                canonical.get("compliance_status"),
                canonical.get("compliance_expiry"),
                source_system,
                json.dumps({"authority": "imported_evidence", "batch_id": batch_id}),
            ),
        )
        applied.append("compliance_evidence_imported")
        review.append(
            {
                "field": "compliance",
                "reason": "Compliance evidence imported for review — no campaign documents were auto-seeded.",
            }
        )

    # P4 opening balances / current-state (leave, payroll draft, assignment, shifts planning).
    # Compliance expiry/status remain on the P2 staging insert above; P4 records opening provenance.
    cutover_keys = {
        k: v
        for k, v in canonical.items()
        if k
        in {
            "cutover_date",
            "leave_type",
            "leave_opening_balance",
            "leave_entitlement_days",
            "salary_basic_monthly",
            "salary_currency",
            "current_assignment_title",
            "current_assignment_department",
            "shift_template_code",
            "compliance_current_state",
            "compliance_doc_type",
            "compliance_status",
            "compliance_expiry",
        }
    }
    # Avoid double-writing compliance staging: P2 already inserted when doc/status/expiry present.
    # P4 still stamps opening_balances provenance for compliance_current_state / expiry summary.
    if cutover_keys:
        try:
            import employee_migration_cutover as _p4

            cur.execute("SAVEPOINT p4_cutover_apply")
            cut = _p4.apply_cutover_from_canonical(
                legacy,
                cur,
                company=company,
                employee_key=employee_key,
                canonical=cutover_keys,
                batch_id=batch_id,
                row_id=row_id,
                source_system=source_system,
                external_employee_id=canonical.get("external_employee_id"),
                actor=actor,
            )
            cur.execute("RELEASE SAVEPOINT p4_cutover_apply")
            applied.extend([f"cutover:{x}" for x in (cut.get("applied") or [])])
            for item in cut.get("review") or []:
                review.append(item if isinstance(item, dict) else {"field": "cutover", "reason": str(item)})
            for item in cut.get("skipped") or []:
                if isinstance(item, dict) and item.get("reason") == "not_supplied":
                    skipped.append(str(item.get("field") or "cutover"))
        except Exception as cut_exc:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT p4_cutover_apply")
            except Exception:
                pass
            review.append({"field": "cutover", "reason": f"Cutover import deferred: {str(cut_exc)[:160]}"})

    return {"applied": applied, "review": review, "skipped": skipped}


def rollback_field_model_for_batch(cur: Any, *, company: str, batch_id: str) -> dict[str, int]:
    cur.execute(
        "DELETE FROM employee_custom_field_values WHERE company_code=%s AND source_batch_id=%s",
        (company, batch_id),
    )
    custom_n = cur.rowcount or 0
    cur.execute(
        "DELETE FROM employee_migration_imported_bank WHERE company_code=%s AND batch_id=%s",
        (company, batch_id),
    )
    bank_n = cur.rowcount or 0
    cur.execute(
        "DELETE FROM employee_migration_imported_compliance WHERE company_code=%s AND batch_id=%s",
        (company, batch_id),
    )
    compliance_n = cur.rowcount or 0
    cur.execute(
        """
        DELETE FROM employee_document_metadata
        WHERE company_code=%s
          AND notes::text LIKE %s
        """,
        (company, f"%{batch_id}%"),
    )
    docs_n = cur.rowcount or 0
    # Clear migration-staged identity pending entries for this batch
    cur.execute(
        """
        SELECT employee_key, ocr_pending FROM employee_identity
        WHERE company_code=%s
          AND ocr_pending::text LIKE %s
        """,
        (company, f"%{batch_id}%"),
    )
    identity_n = 0
    for row in cur.fetchall() or []:
        pending = dict(row.get("ocr_pending") or {})
        changed = False
        for key in list(pending.keys()):
            cell = pending.get(key) or {}
            if str(cell.get("batch_id") or "") == str(batch_id) and cell.get("source") == "migration_import":
                pending.pop(key, None)
                changed = True
        if changed:
            cur.execute(
                """
                UPDATE employee_identity SET ocr_pending=%s::jsonb, updated_at=now()
                WHERE company_code=%s AND employee_key=%s
                """,
                (json.dumps(pending), company, row["employee_key"]),
            )
            identity_n += 1
    cur.execute(
        "DELETE FROM employee_import_source_payloads WHERE company_code=%s AND batch_id=%s",
        (company, batch_id),
    )
    payload_n = cur.rowcount or 0
    cutover_n: dict[str, Any] = {}
    try:
        import employee_migration_cutover as _p4

        cutover_n = _p4.rollback_cutover_for_batch(cur, company=company, batch_id=batch_id)
    except Exception:
        cutover_n = {}
    return {
        "custom_values": custom_n,
        "bank_imports": bank_n,
        "compliance_imports": compliance_n,
        "document_metadata": docs_n,
        "identity_staged": identity_n,
        "source_payloads": payload_n,
        "cutover": cutover_n,
    }
