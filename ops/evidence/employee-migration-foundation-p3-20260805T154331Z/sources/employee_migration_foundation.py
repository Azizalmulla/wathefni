"""Employee Migration Foundation P0–P3 — roster import + safe existing updates.

Create path stays create-only for new people. P3 adds controlled updates for
matched existing employees (name/email/title/department/start date/manager via
assignment history). Match: source_system+external_employee_id, else phone;
never name alone. No messages · no auto-onboarding · no compliance seed · no
deactivation · no leave/docs/shifts/payroll.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import schema_contract

CONTRACT = "employee_migration_foundation_p0p3"
CONTRACT_VERSION = "1.1.0"
DOMAIN = "employee_roster"
SCHEMA_LOCK_ID = 770_911_221

BATCH_STATUSES = frozenset(
    {"draft", "previewed", "committing", "committed", "partial", "failed", "rolled_back"}
)
ROW_STATUSES = frozenset(
    {
        "pending",
        "will_create",
        "will_update",
        "skipped",
        "conflict",
        "invalid",
        "created",
        "updated",
        "failed",
        "rolled_back",
    }
)
# HR-facing totals. Deactivate stays 0 in P3.
TOTAL_KEYS = ("create", "update", "skip", "review", "invalid", "warnings")
SAFE_UPDATE_FIELDS = ("name", "email", "position_title", "department", "start_date")

HEADER_ALIASES = {
    "name": "name",
    "full_name": "name",
    "employee_name": "name",
    "fullname": "name",
    "phone": "phone",
    "mobile": "phone",
    "whatsapp": "phone",
    "phone_number": "phone",
    "whatsapp_number": "phone",
    "mobile_number": "phone",
    "contact": "phone",
    "email": "email",
    "email_address": "email",
    "e_mail": "email",
    "mail": "email",
    "email_id": "email",
    "work_email": "email",
    "personal_email": "email",
    "job_title": "position_title",
    "title": "position_title",
    "position": "position_title",
    "position_title": "position_title",
    "role": "position_title",
    "designation": "position_title",
    "department": "department",
    "team": "department",
    "dept": "department",
    "division": "department",
    "start_date": "start_date",
    "hire_date": "start_date",
    "joining_date": "start_date",
    "start": "start_date",
    "external_employee_id": "external_employee_id",
    "external_id": "external_employee_id",
    "employee_id": "external_employee_id",
    "emp_id": "external_employee_id",
    "source_employee_id": "external_employee_id",
    "ats_id": "external_employee_id",
    "payroll_id": "payroll_id",
    "payroll_employee_id": "payroll_id",
    "pay_id": "payroll_id",
    "source_system": "source_system",
    "source": "source_system",
    "system": "source_system",
    "hris": "source_system",
    "manager_phone": "manager_phone",
    "manager": "manager_phone",
    "manager_mobile": "manager_phone",
    "reports_to": "manager_phone",
    "reports_to_phone": "manager_phone",
    "line_manager": "manager_phone",
    "line_manager_phone": "manager_phone",
}

REQUIRED_TABLES = [
    "employee_import_batches",
    "employee_import_rows",
    "employee_source_mappings",
]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS employee_import_batches (
  batch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  domain text NOT NULL DEFAULT 'employee_roster',
  contract text NOT NULL DEFAULT 'employee_migration_foundation_p0p2',
  contract_version text NOT NULL DEFAULT '1.0.0',
  status text NOT NULL DEFAULT 'draft',
  filename text,
  content_sha256 text NOT NULL,
  idempotency_key text NOT NULL,
  source_system text,
  total_rows integer NOT NULL DEFAULT 0,
  totals jsonb NOT NULL DEFAULT '{}'::jsonb,
  options jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  committed_at timestamptz,
  rolled_back_at timestamptz,
  UNIQUE (company_code, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_employee_import_batches_company
  ON employee_import_batches(company_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_employee_import_batches_sha
  ON employee_import_batches(company_code, content_sha256);

CREATE TABLE IF NOT EXISTS employee_import_rows (
  row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id uuid NOT NULL REFERENCES employee_import_batches(batch_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  row_number integer NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  name text,
  phone text,
  email text,
  position_title text,
  department text,
  start_date text,
  external_employee_id text,
  payroll_id text,
  source_system text,
  employee_key text,
  reason text,
  raw jsonb NOT NULL DEFAULT '{}'::jsonb,
  normalized jsonb NOT NULL DEFAULT '{}'::jsonb,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (batch_id, row_number)
);
CREATE INDEX IF NOT EXISTS idx_employee_import_rows_batch_status
  ON employee_import_rows(batch_id, status);
CREATE INDEX IF NOT EXISTS idx_employee_import_rows_company
  ON employee_import_rows(company_code, batch_id);

CREATE TABLE IF NOT EXISTS employee_source_mappings (
  mapping_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  source_system text NOT NULL,
  external_employee_id text,
  payroll_id text,
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  batch_id uuid,
  row_id uuid,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_employee_source_mappings_employee
  ON employee_source_mappings(company_code, employee_key)
  WHERE active;
CREATE UNIQUE INDEX IF NOT EXISTS uq_employee_source_ext_id
  ON employee_source_mappings(company_code, source_system, external_employee_id)
  WHERE active AND external_employee_id IS NOT NULL AND btrim(external_employee_id) <> '';
CREATE UNIQUE INDEX IF NOT EXISTS uq_employee_source_payroll_id
  ON employee_source_mappings(company_code, source_system, payroll_id)
  WHERE active AND payroll_id IS NOT NULL AND btrim(payroll_id) <> '';
"""


def _flag_on(name: str, default: str = "") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def foundation_enabled(company_code: str | None = None) -> bool:
    if not _flag_on("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION"):
        return False
    company = str(company_code or "").strip().upper()
    if not company:
        return True
    return company_allowed(company)


def allowed_companies() -> set[str] | None:
    raw = (os.environ.get("WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION_COMPANIES") or "").strip()
    if not raw:
        return None
    return {c.strip().upper() for c in raw.split(",") if c.strip()}


def company_allowed(company_code: str) -> bool:
    allowed = allowed_companies()
    if allowed is None:
        return True
    return str(company_code or "").strip().upper() in allowed


def honesty_payload() -> dict[str, Any]:
    return {
        "contract": CONTRACT,
        "version": CONTRACT_VERSION,
        "domain": DOMAIN,
        "create_only_for_new": True,
        "controlled_updates": True,
        "no_messages": True,
        "no_auto_onboarding": True,
        "no_auto_compliance_seed_on_import": True,
        "no_deactivation": True,
        "no_documents_balances_shifts": True,
        "no_erp_sftp": True,
        "match_priority": ["source_system+external_employee_id", "phone_alias"],
        "never_match_by_name_alone": True,
        "safe_update_fields": list(SAFE_UPDATE_FIELDS) + ["manager"],
        "source_mapping_model": True,
        "allowed_companies": sorted(allowed_companies() or []),
    }


def _status_to_total_key(status: str) -> str | None:
    if status in {"will_create", "created"}:
        return "create"
    if status in {"will_update", "updated"}:
        return "update"
    if status == "skipped":
        return "skip"
    if status == "conflict":
        return "review"
    if status in {"invalid", "failed"}:
        return "invalid"
    return None


def _legacy_bucket(status: str) -> str:
    if status in {"will_create", "created"}:
        return "created"
    if status in {"will_update", "updated"}:
        return "updated"
    if status == "skipped":
        return "skipped"
    if status == "conflict":
        return "needs_review"
    return "failed"


def _hr_outcome(status: str) -> str:
    return {
        "will_create": "Will be added",
        "created": "Added",
        "will_update": "Will be updated",
        "updated": "Updated",
        "skipped": "Will be skipped",
        "conflict": "Needs review",
        "invalid": "Will be skipped",
        "failed": "Could not apply",
        "rolled_back": "Undone",
    }.get(status, status)


def ensure_schema(cur: Any, *, force: bool = False) -> None:
    del force
    # Do not pass lock_id: schema_contract.apply_sql rolls back the connection in
    # its unlock finally-block, which would undo CREATE TABLE. Caller commits.
    schema_contract.ensure_sql(
        cur,
        SCHEMA_SQL,
        required_tables=REQUIRED_TABLES,
        module="employee_migration_foundation",
        lock_id=None,
    )


def _normalize_header(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def content_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw or b"").hexdigest()


def default_idempotency_key(
    *,
    company_code: str,
    content_sha: str,
    source_system: str | None = None,
) -> str:
    company = str(company_code or "").strip().upper()
    src = str(source_system or "").strip().lower() or "unspecified"
    material = f"{company}|{DOMAIN}|{CONTRACT_VERSION}|{content_sha}|{src}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def empty_totals() -> dict[str, int]:
    return {k: 0 for k in TOTAL_KEYS}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def parse_employee_import_rows(raw: bytes, filename: str) -> tuple[list[dict[str, str]], str | None]:
    """Parse CSV/XLSX into normalized field dicts. Preserves roster aliases + ID fields."""
    name = str(filename or "").lower()
    try:
        if name.endswith(".xlsx") or name.endswith(".xlsm"):
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            ws = wb.active
            if ws is None:
                return [], "We couldn't read this spreadsheet."
            iterator = ws.iter_rows(values_only=True)
            try:
                header = next(iterator)
            except StopIteration:
                return [], "The file is empty."
            mapped = [HEADER_ALIASES.get(_normalize_header(h)) for h in header]
            if "name" not in mapped or "phone" not in mapped:
                return [], "The file needs a 'name' and a 'phone' column."
            rows: list[dict[str, str]] = []
            for values in iterator:
                if not values:
                    continue
                rec: dict[str, str] = {}
                for key, val in zip(mapped, values):
                    if not key or val is None:
                        continue
                    if isinstance(val, float) and val.is_integer():
                        val = int(val)
                    text = str(val).strip()
                    if text:
                        rec[key] = text
                if rec:
                    rows.append(rec)
            return rows, None

        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return [], "The file is empty."
        field_map = {fn: HEADER_ALIASES.get(_normalize_header(fn)) for fn in reader.fieldnames}
        if "name" not in field_map.values() or "phone" not in field_map.values():
            return [], "The file needs a 'name' and a 'phone' column."
        rows = []
        for raw_rec in reader:
            rec: dict[str, str] = {}
            for fn, key in field_map.items():
                if not key:
                    continue
                value = str(raw_rec.get(fn) or "").strip()
                if value:
                    rec[key] = value
            if rec:
                rows.append(rec)
        return rows, None
    except Exception:
        return [], "We couldn't read this file. Please upload a CSV or XLSX with name and phone columns."


def _manager_warning(manager_phone: str) -> str:
    return (
        f"Manager phone {manager_phone} was not found in the workforce or earlier rows in this file — "
        "manager will be left unset."
    )


def _resolve_manager_preview(
    legacy: Any,
    *,
    company: str,
    manager_phone_raw: Any,
    earlier_batch: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Resolve manager_phone against tenant + earlier will_create rows in this batch.

    Returns None when no manager column value was provided.
    """
    raw = str(manager_phone_raw or "").strip()
    if not raw:
        return None
    phone = legacy.canonical_employee_phone(raw)
    if not phone:
        return {
            "manager_phone": raw,
            "resolved": False,
            "manager_employee_key": None,
            "source": None,
            "warning": f"Manager phone '{raw}' is invalid — manager will be left unset.",
        }
    existing = legacy.find_employee_by_phone(phone, company_code=company)
    if existing and existing.get("employee_key"):
        return {
            "manager_phone": phone,
            "resolved": True,
            "manager_employee_key": str(existing["employee_key"]),
            "source": "tenant",
            "warning": None,
        }
    earlier = earlier_batch.get(phone)
    if earlier:
        return {
            "manager_phone": phone,
            "resolved": True,
            "manager_employee_key": str(earlier.get("employee_key") or f"{company}-{phone}"),
            "source": "batch_earlier",
            "warning": None,
            "batch_row": earlier.get("row_number"),
        }
    return {
        "manager_phone": phone,
        "resolved": False,
        "manager_employee_key": None,
        "source": None,
        "warning": _manager_warning(phone),
    }


def _current_manager_key(legacy: Any, company: str, employee_key: str) -> str | None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT manager_employee_key
                FROM employee_org_assignment_history
                WHERE company_code=%s AND employee_key=%s AND effective_to IS NULL
                ORDER BY effective_from DESC, created_at DESC
                LIMIT 1
                """,
                (company, employee_key),
            )
            hit = cur.fetchone()
            if hit:
                key = (hit["manager_employee_key"] if isinstance(hit, dict) else hit[0]) or None
                if key:
                    conn.commit()
                    return str(key)
            cur.execute(
                "SELECT raw_json FROM employees WHERE company_code=%s AND employee_key=%s LIMIT 1",
                (company, employee_key),
            )
            row = cur.fetchone()
            conn.commit()
            if not row:
                return None
            raw = row["raw_json"] if isinstance(row, dict) else row[0]
            if isinstance(raw, str):
                raw = json.loads(raw)
            if isinstance(raw, dict) and raw.get("manager_employee_key"):
                return str(raw["manager_employee_key"])
    return None


def _lookup_by_external_id(
    legacy: Any,
    *,
    company: str,
    source_system: str,
    external_employee_id: str,
) -> dict[str, Any] | None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT employee_key FROM employee_source_mappings
                WHERE company_code=%s AND source_system=%s AND external_employee_id=%s AND active
                LIMIT 1
                """,
                (company, source_system, external_employee_id),
            )
            hit = cur.fetchone()
            if not hit:
                conn.commit()
                return None
            ek = str(hit["employee_key"] if isinstance(hit, dict) else hit[0])
            cur.execute(
                "SELECT * FROM employees WHERE company_code=%s AND employee_key=%s LIMIT 1",
                (company, ek),
            )
            emp = cur.fetchone()
            conn.commit()
            return dict(emp) if emp else None


def _hub_field_snapshot(emp: dict[str, Any]) -> dict[str, Any]:
    profile = emp.get("profile") if isinstance(emp.get("profile"), dict) else {}
    start = emp.get("start_date")
    if hasattr(start, "isoformat"):
        start = start.isoformat()
    return {
        "name": str(emp.get("name") or "").strip() or None,
        "email": str(emp.get("email") or "").strip() or None,
        "position_title": str(emp.get("position_title") or "").strip() or None,
        "department": str(profile.get("department") or emp.get("department") or "").strip() or None,
        "start_date": str(start)[:10] if start else None,
        "phone": str(emp.get("phone") or "").strip() or None,
        "updated_at": emp.get("updated_at").isoformat() if hasattr(emp.get("updated_at"), "isoformat") else emp.get("updated_at"),
    }


def _diff_safe_fields(
    *,
    before: dict[str, Any],
    normalized: dict[str, Any],
    before_manager: str | None,
    after_manager: str | None,
) -> dict[str, dict[str, Any]]:
    changes: dict[str, dict[str, Any]] = {}
    for field in SAFE_UPDATE_FIELDS:
        old = before.get(field)
        new = normalized.get(field)
        # Normalize empty strings to None for comparison
        old_n = str(old).strip() if old not in (None, "") else None
        new_n = str(new).strip() if new not in (None, "") else None
        if field == "start_date":
            old_n = (old_n or "")[:10] or None
            new_n = (new_n or "")[:10] or None
        if old_n != new_n:
            # Only include fields supplied in the file (normalized has value or explicit clear?)
            # For import: update when incoming value is present and differs; ignore omitted empty
            # except we always have name. For optional fields, empty incoming means no change.
            if field != "name" and new_n is None:
                continue
            changes[field] = {"before": old_n, "after": new_n}
    if (before_manager or None) != (after_manager or None):
        # Manager change only when incoming manager_phone was provided (resolved or unresolved)
        changes["manager_employee_key"] = {"before": before_manager, "after": after_manager}
    return changes


def _classify_row(
    legacy: Any,
    *,
    company: str,
    row_number: int,
    rec: dict[str, str],
    seen_phones: dict[str, int],
    batch_source_system: str | None,
    earlier_batch: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    clean_name = str(rec.get("name") or "").strip()
    phone_digits = legacy.canonical_employee_phone(rec.get("phone"))
    row_label = clean_name or str(rec.get("phone") or "").strip() or f"Row {row_number}"
    source_system = str(rec.get("source_system") or batch_source_system or "").strip() or None
    external_employee_id = str(rec.get("external_employee_id") or "").strip() or None
    payroll_id = str(rec.get("payroll_id") or "").strip() or None
    manager_phone_raw = str(rec.get("manager_phone") or "").strip() or None
    manager = _resolve_manager_preview(
        legacy,
        company=company,
        manager_phone_raw=manager_phone_raw,
        earlier_batch=earlier_batch,
    )
    normalized = {
        "name": clean_name,
        "phone": phone_digits or str(rec.get("phone") or "").strip(),
        "email": str(rec.get("email") or "").strip() or None,
        "position_title": str(rec.get("position_title") or "").strip() or None,
        "department": str(rec.get("department") or "").strip() or None,
        "start_date": str(rec.get("start_date") or "").strip() or None,
        "external_employee_id": external_employee_id,
        "payroll_id": payroll_id,
        "source_system": source_system,
        "manager_phone": (manager or {}).get("manager_phone") or manager_phone_raw,
        "manager_employee_key": (manager or {}).get("manager_employee_key") if manager and manager.get("resolved") else None,
    }
    detail: dict[str, Any] = {"match": None, "changes": {}}
    warnings: list[str] = []
    if manager:
        detail["manager"] = {
            "manager_phone": manager.get("manager_phone"),
            "resolved": bool(manager.get("resolved")),
            "manager_employee_key": manager.get("manager_employee_key"),
            "source": manager.get("source"),
            "batch_row": manager.get("batch_row"),
        }
        if manager.get("warning"):
            warnings.append(str(manager["warning"]))
    if warnings:
        detail["warnings"] = warnings

    if not phone_digits:
        return {
            "status": "invalid",
            "reason": "Missing or invalid phone number.",
            "name": row_label,
            "phone": None,
            "normalized": normalized,
            "detail": detail,
        }
    if not clean_name:
        return {
            "status": "invalid",
            "reason": "Missing name.",
            "name": row_label,
            "phone": phone_digits,
            "normalized": normalized,
            "detail": detail,
        }
    if phone_digits in seen_phones:
        return {
            "status": "conflict",
            "reason": f"Duplicate phone in this file (also row {seen_phones[phone_digits]}).",
            "name": row_label,
            "phone": phone_digits,
            "normalized": normalized,
            "detail": detail,
        }
    seen_phones[phone_digits] = row_number

    # Match priority: source_system + external_employee_id, else phone/alias. Never name alone.
    mapped_emp = None
    phone_emp = legacy.find_employee_by_phone(phone_digits, company_code=company)
    if source_system and external_employee_id:
        mapped_emp = _lookup_by_external_id(
            legacy,
            company=company,
            source_system=source_system,
            external_employee_id=external_employee_id,
        )

    existing = None
    match_via = None
    if mapped_emp and phone_emp:
        map_key = str(mapped_emp.get("employee_key") or "")
        phone_key = str(phone_emp.get("employee_key") or "")
        if map_key != phone_key:
            return {
                "status": "conflict",
                "reason": (
                    f"Needs review: external ID maps to {map_key} but phone matches {phone_key}."
                ),
                "name": row_label,
                "phone": phone_digits,
                "employee_key": map_key,
                "normalized": normalized,
                "detail": {
                    **detail,
                    "match": {
                        "via": "ambiguous",
                        "mapped_employee_key": map_key,
                        "phone_employee_key": phone_key,
                    },
                },
            }
        # Same person — but phone on file must match hub phone (phone is not an auto-update field)
        hub_phone = legacy.canonical_employee_phone(mapped_emp.get("phone"))
        if hub_phone and hub_phone != phone_digits:
            return {
                "status": "conflict",
                "reason": (
                    f"Needs review: external ID matches {map_key} but phone differs from the record."
                ),
                "name": row_label,
                "phone": phone_digits,
                "employee_key": map_key,
                "normalized": normalized,
                "detail": {**detail, "match": {"via": "external_id_phone_mismatch", "employee_key": map_key}},
            }
        existing = mapped_emp
        match_via = "external_id"
    elif mapped_emp:
        existing = mapped_emp
        match_via = "external_id"
        hub_phone = legacy.canonical_employee_phone(mapped_emp.get("phone"))
        if hub_phone and phone_digits and hub_phone != phone_digits:
            return {
                "status": "conflict",
                "reason": (
                    f"Needs review: external ID matches {existing.get('employee_key')} but phone differs from the record."
                ),
                "name": row_label,
                "phone": phone_digits,
                "employee_key": existing.get("employee_key"),
                "normalized": normalized,
                "detail": {
                    **detail,
                    "match": {"via": "external_id_phone_mismatch", "employee_key": existing.get("employee_key")},
                },
            }
    elif phone_emp:
        existing = phone_emp
        match_via = "phone"

    if existing:
        ek = str(existing.get("employee_key") or "")
        before = _hub_field_snapshot(existing)
        before_mgr = _current_manager_key(legacy, company, ek)
        # Manager auto-update only when resolved; unresolved phone → warning, keep current manager.
        if manager_phone_raw and manager and manager.get("resolved") and manager.get("manager_employee_key"):
            after_mgr = str(manager["manager_employee_key"])
        else:
            after_mgr = before_mgr
        changes = _diff_safe_fields(
            before=before,
            normalized=normalized,
            before_manager=before_mgr,
            after_manager=after_mgr,
        )
        if not (manager_phone_raw and manager and manager.get("resolved") and manager.get("manager_employee_key")):
            changes.pop("manager_employee_key", None)
        detail["match"] = {"via": match_via, "employee_key": ek}
        detail["before"] = before
        detail["before_manager_employee_key"] = before_mgr
        detail["changes"] = changes
        detail["expected_updated_at"] = before.get("updated_at")
        if not changes:
            return {
                "status": "skipped",
                "reason": "Will be skipped — already up to date.",
                "name": row_label,
                "phone": phone_digits,
                "employee_key": ek,
                "normalized": normalized,
                "detail": detail,
            }
        change_labels = ", ".join(sorted(changes.keys()))
        reason = f"Will be updated ({change_labels})."
        if warnings:
            reason = f"{reason} {warnings[0]}"
        return {
            "status": "will_update",
            "reason": reason,
            "name": row_label,
            "phone": phone_digits,
            "employee_key": ek,
            "normalized": normalized,
            "detail": detail,
        }

    reason = "Will be added."
    if warnings:
        reason = f"Will be added. {warnings[0]}"
    detail["match"] = {"via": "none"}
    return {
        "status": "will_create",
        "reason": reason,
        "name": row_label,
        "phone": phone_digits,
        "normalized": normalized,
        "detail": detail,
    }


def _row_entry(row: dict[str, Any]) -> dict[str, Any]:
    detail = row.get("detail") or {}
    if isinstance(detail, str):
        detail = json.loads(detail)
    norm = row.get("normalized") or {}
    if isinstance(norm, str):
        norm = json.loads(norm)
    manager = detail.get("manager") if isinstance(detail, dict) else None
    warnings = detail.get("warnings") if isinstance(detail, dict) else None
    changes = detail.get("changes") if isinstance(detail, dict) else None
    status = str(row.get("status") or "")
    return {
        "row": int(row.get("row_number") or 0),
        "name": row.get("name") or f"Row {row.get('row_number')}",
        "reason": row.get("reason"),
        "status": status,
        "outcome": _hr_outcome(status),
        "employee_key": row.get("employee_key"),
        "phone": row.get("phone") or norm.get("phone"),
        "external_employee_id": row.get("external_employee_id") or norm.get("external_employee_id"),
        "payroll_id": row.get("payroll_id") or norm.get("payroll_id"),
        "source_system": row.get("source_system") or norm.get("source_system"),
        "manager_phone": (manager or {}).get("manager_phone") if manager else norm.get("manager_phone"),
        "manager_employee_key": (manager or {}).get("manager_employee_key") if manager else None,
        "manager_resolved": (manager or {}).get("resolved") if manager else None,
        "manager_source": (manager or {}).get("source") if manager else None,
        "warnings": warnings or [],
        "changes": changes or {},
        "detail": detail,
    }


def _parse_expected_updated_at(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _stamp_manager_on_employee(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    manager_employee_key: str | None,
    manager_phone: str | None,
    batch_id: str,
    unresolved: bool = False,
) -> None:
    payload: dict[str, Any] = {
        "manager_phone": manager_phone,
        "employee_migration_manager_batch_id": str(batch_id),
    }
    if unresolved:
        payload["manager_unresolved"] = True
        payload["manager_employee_key"] = None
    elif manager_employee_key:
        payload["manager_employee_key"] = manager_employee_key
        payload["manager_unresolved"] = False
    cur.execute(
        """
        UPDATE employees
        SET raw_json = COALESCE(raw_json, '{}'::jsonb) || %s::jsonb,
            updated_at=now()
        WHERE company_code=%s AND employee_key=%s
        """,
        (json.dumps(payload), company, employee_key),
    )


def _apply_manager_authoritative(
    legacy: Any,
    context: dict[str, Any],
    *,
    employee_key: str,
    manager_employee_key: str,
    manager_phone: str | None,
    batch_id: str,
    position_title: str | None = None,
) -> dict[str, Any]:
    """Persist manager via Wave4 assignment history (canonical) + hub stamp.

    Preview/raw_json alone is not enough for Employee Profile assignment history.
    """
    from datetime import date as _date

    import employee_org_wave4 as _w4

    company = str(context.get("company_code") or "").upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            _stamp_manager_on_employee(
                cur,
                company=company,
                employee_key=employee_key,
                manager_employee_key=manager_employee_key,
                manager_phone=manager_phone,
                batch_id=str(batch_id),
                unresolved=False,
            )
            conn.commit()

    if not _w4.org_v4_enabled(company):
        return {"ok": False, "error": "org_v4_disabled", "hub_stamped": True}

    try:
        out = _w4.apply_assignment_change(
            legacy,
            context,
            employee_key=employee_key,
            effective_from=_date.today(),
            change_type="migration",
            reason=f"employee migration foundation batch {batch_id}",
            manager_employee_key=manager_employee_key,
            position_title=position_title,
            batch_id=str(batch_id),
            provenance={
                "foundation_batch_id": str(batch_id),
                "source": "employee_migration_foundation",
                "manager_phone": manager_phone,
            },
        )
        return {"ok": True, "hub_stamped": True, "assignment": out}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:240], "hub_stamped": True}


def repair_foundation_batch_side_effects(
    legacy: Any,
    context: dict[str, Any],
    *,
    batch_id: str,
) -> dict[str, Any]:
    """One-shot repair for committed foundation batches:

    - Wire resolved managers into org assignment history when missing
    - Remove auto-seeded missing civil_id/passport created by import (no campaign yet)
    """
    company = legacy.require_employee_roster_admin(context)
    if not foundation_enabled(company):
        raise legacy.HTTPException(status_code=403, detail={"error": "employee_migration_foundation_disabled"})

    managers_applied = 0
    managers_skipped = 0
    managers_failed: list[dict[str, Any]] = []
    compliance_removed = 0

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT employee_key, raw_json, position_title
                FROM employees
                WHERE company_code=%s
                  AND raw_json->>%s = %s
                  AND COALESCE((raw_json->>'employee_migration_hub_created')::boolean, false) = true
                """,
                (company, "employee_migration_batch_id", str(batch_id)),
            )
            employees = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()

    for emp in employees:
        ek = str(emp.get("employee_key") or "")
        raw_json = emp.get("raw_json") or {}
        if isinstance(raw_json, str):
            raw_json = json.loads(raw_json)
        mgr = str(raw_json.get("manager_employee_key") or "").strip() or None
        if not mgr:
            managers_skipped += 1
        else:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT count(*) AS c FROM employee_org_assignment_history
                        WHERE company_code=%s AND employee_key=%s
                          AND manager_employee_key=%s
                        """,
                        (company, ek, mgr),
                    )
                    hit = cur.fetchone()
                    already = int((hit["c"] if isinstance(hit, dict) else hit[0]) or 0)
                    conn.commit()
            if already:
                managers_skipped += 1
            else:
                result = _apply_manager_authoritative(
                    legacy,
                    context,
                    employee_key=ek,
                    manager_employee_key=mgr,
                    manager_phone=raw_json.get("manager_phone"),
                    batch_id=str(batch_id),
                    position_title=emp.get("position_title"),
                )
                if result.get("ok"):
                    managers_applied += 1
                else:
                    managers_failed.append({"employee_key": ek, "error": result.get("error")})

        # Remove import-auto-seeded missing checklist rows (campaign not approved).
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM compliance_documents
                    WHERE company_code=%s AND employee_key=%s
                      AND status='missing'
                      AND document_type IN ('civil_id','passport')
                    """,
                    (company, ek),
                )
                compliance_removed += int(cur.rowcount or 0)
                conn.commit()

    return {
        "ok": True,
        "batch_id": str(batch_id),
        "employees": len(employees),
        "managers_applied": managers_applied,
        "managers_skipped": managers_skipped,
        "managers_failed": managers_failed,
        "compliance_missing_removed": compliance_removed,
        "honesty": {
            **honesty_payload(),
            "no_auto_compliance_seed_on_import": True,
            "manager_via_assignment_history": True,
        },
    }


def _resolve_manager_at_commit(
    legacy: Any,
    cur: Any,
    *,
    company: str,
    batch_id: str,
    manager_phone: str | None,
    preview_manager: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if preview_manager and preview_manager.get("resolved") and preview_manager.get("manager_employee_key"):
        # Re-validate key still exists (or was created earlier in this batch).
        key = str(preview_manager["manager_employee_key"])
        cur.execute(
            "SELECT employee_key FROM employees WHERE company_code=%s AND employee_key=%s LIMIT 1",
            (company, key),
        )
        if cur.fetchone():
            return {
                "manager_phone": preview_manager.get("manager_phone") or manager_phone,
                "resolved": True,
                "manager_employee_key": key,
                "source": preview_manager.get("source") or "preview",
            }
    phone = legacy.canonical_employee_phone(manager_phone) if manager_phone else None
    if not phone and preview_manager:
        phone = legacy.canonical_employee_phone(preview_manager.get("manager_phone"))
    if not phone:
        return preview_manager
    existing = legacy.find_employee_by_phone(phone, company_code=company)
    if existing and existing.get("employee_key"):
        return {
            "manager_phone": phone,
            "resolved": True,
            "manager_employee_key": str(existing["employee_key"]),
            "source": "tenant",
        }
    cur.execute(
        """
        SELECT employee_key FROM employee_import_rows
        WHERE batch_id=%s AND company_code=%s AND phone=%s AND status='created'
        ORDER BY row_number LIMIT 1
        """,
        (batch_id, company, phone),
    )
    hit = cur.fetchone()
    if hit:
        key = hit["employee_key"] if isinstance(hit, dict) else hit[0]
        return {
            "manager_phone": phone,
            "resolved": True,
            "manager_employee_key": str(key),
            "source": "batch_earlier",
        }
    return {
        "manager_phone": phone,
        "resolved": False,
        "manager_employee_key": None,
        "source": None,
        "warning": _manager_warning(phone),
    }


def _upsert_source_mapping(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    source_system: str | None,
    external_employee_id: str | None,
    payroll_id: str | None,
    batch_id: str,
    row_id: str,
) -> None:
    system = str(source_system or "").strip()
    ext = str(external_employee_id or "").strip() or None
    pay = str(payroll_id or "").strip() or None
    if not system or (not ext and not pay):
        return
    attrs = json.dumps({"contract": CONTRACT, "version": CONTRACT_VERSION})
    # Look up existing active mapping for this system+id (partial unique indexes).
    existing = None
    if ext:
        cur.execute(
            """
            SELECT mapping_id FROM employee_source_mappings
            WHERE company_code=%s AND source_system=%s AND external_employee_id=%s AND active
            LIMIT 1
            """,
            (company, system, ext),
        )
        existing = cur.fetchone()
    if not existing and pay:
        cur.execute(
            """
            SELECT mapping_id FROM employee_source_mappings
            WHERE company_code=%s AND source_system=%s AND payroll_id=%s AND active
            LIMIT 1
            """,
            (company, system, pay),
        )
        existing = cur.fetchone()
    if existing:
        mid = existing["mapping_id"] if isinstance(existing, dict) else existing[0]
        cur.execute(
            """
            UPDATE employee_source_mappings
            SET employee_key=%s,
                external_employee_id=COALESCE(%s, external_employee_id),
                payroll_id=COALESCE(%s, payroll_id),
                batch_id=%s, row_id=%s, attributes=%s::jsonb, updated_at=now(), active=true
            WHERE mapping_id=%s
            """,
            (employee_key, ext, pay, batch_id, row_id, attrs, mid),
        )
        return
    cur.execute(
        """
        INSERT INTO employee_source_mappings (
          company_code, employee_key, source_system, external_employee_id, payroll_id,
          attributes, batch_id, row_id, active, updated_at
        ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,true,now())
        """,
        (company, employee_key, system, ext, pay, attrs, batch_id, row_id),
    )


def _batch_payload(batch: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    totals = batch.get("totals") or {}
    if isinstance(totals, str):
        totals = json.loads(totals)
    # Prefer P3 keys; tolerate older batches that stored "conflict" instead of "review".
    review_count = int(totals.get("review") if totals.get("review") is not None else totals.get("conflict") or 0)
    update_count = int(totals.get("update") or 0)
    legacy_counts = {
        "created": int(totals.get("create") or 0),
        "updated": update_count,
        "skipped": int(totals.get("skip") or 0),
        "needs_review": review_count,
        "failed": int(totals.get("invalid") or 0),
    }
    results = {
        "created": [],
        "updated": [],
        "skipped": [],
        "needs_review": [],
        "failed": [],
    }
    if rows is not None:
        for row in rows:
            bucket = _legacy_bucket(str(row.get("status") or ""))
            results.setdefault(bucket, []).append(_row_entry(row))
    return {
        "ok": True,
        "foundation": True,
        "honesty": honesty_payload(),
        "batch_id": str(batch.get("batch_id")),
        "status": batch.get("status"),
        "idempotency_key": batch.get("idempotency_key"),
        "content_sha256": batch.get("content_sha256"),
        "source_system": batch.get("source_system"),
        "filename": batch.get("filename"),
        "dry_run": batch.get("status") == "previewed",
        "total_rows": int(batch.get("total_rows") or 0),
        "totals": {
            "create": int(totals.get("create") or 0),
            "update": update_count,
            "skip": int(totals.get("skip") or 0),
            "review": review_count,
            # Alias for older UI; same as review.
            "conflict": review_count,
            "invalid": int(totals.get("invalid") or 0),
            "warnings": int(totals.get("warnings") or 0),
            "deactivate": 0,
        },
        "counts": legacy_counts,
        "results": results,
        "labels": {
            "create": "Will be added",
            "update": "Will be updated",
            "skip": "Will be skipped",
            "review": "Needs review",
            "invalid": "Will be skipped",
            "deactivate": "Will be deactivated",
        },
        "batch": _jsonable(batch),
    }


def preview_or_replay_import(
    legacy: Any,
    context: dict[str, Any],
    *,
    raw: bytes,
    filename: str,
    source_system: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    if not foundation_enabled(company):
        raise legacy.HTTPException(status_code=403, detail={"error": "employee_migration_foundation_disabled"})

    rows_in, parse_error = parse_employee_import_rows(raw, filename)
    if parse_error:
        raise legacy.HTTPException(status_code=422, detail={"error": "unreadable_file", "message": parse_error})
    if len(rows_in) > int(getattr(legacy, "EMPLOYEE_IMPORT_MAX_ROWS", 1000)):
        raise legacy.HTTPException(
            status_code=422,
            detail={
                "error": "too_many_rows",
                "message": f"Please import up to {legacy.EMPLOYEE_IMPORT_MAX_ROWS} employees per file.",
            },
        )

    content_sha = content_sha256(raw)
    batch_source = str(source_system or "").strip() or None
    key = str(idempotency_key or "").strip() or default_idempotency_key(
        company_code=company, content_sha=content_sha, source_system=batch_source
    )
    actor = str(context.get("user_id") or context.get("email") or "").strip() or None

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT * FROM employee_import_batches
                WHERE company_code=%s AND idempotency_key=%s
                LIMIT 1
                """,
                (company, key),
            )
            existing = cur.fetchone()
            if existing:
                batch = dict(existing)
                # Committed outcomes are immutable replays. Previewed batches refresh so
                # classification fixes (e.g. manager warnings) apply on re-upload.
                if batch.get("status") in {"committed", "partial", "rolled_back", "committing"}:
                    cur.execute(
                        "SELECT * FROM employee_import_rows WHERE batch_id=%s AND company_code=%s ORDER BY row_number",
                        (batch["batch_id"], company),
                    )
                    rows = [dict(r) for r in (cur.fetchall() or [])]
                    conn.commit()
                    out = _batch_payload(batch, rows)
                    out["replayed"] = True
                    out["dry_run"] = False
                    return out

            seen_phones: dict[str, int] = {}
            earlier_batch: dict[str, dict[str, Any]] = {}
            classified: list[dict[str, Any]] = []
            totals = empty_totals()
            for idx, rec in enumerate(rows_in, start=1):
                # Prefer batch-level source_system when row omits it.
                if batch_source and not rec.get("source_system"):
                    rec = {**rec, "source_system": batch_source}
                item = _classify_row(
                    legacy,
                    company=company,
                    row_number=idx,
                    rec=rec,
                    seen_phones=seen_phones,
                    batch_source_system=batch_source,
                    earlier_batch=earlier_batch,
                )
                classified.append({"row_number": idx, "raw": rec, **item})
                total_key = _status_to_total_key(item["status"])
                if total_key:
                    totals[total_key] += 1
                detail = item.get("detail") or {}
                if detail.get("warnings"):
                    totals["warnings"] += 1
                if item.get("status") == "will_create" and item.get("phone"):
                    earlier_batch[str(item["phone"])] = {
                        "row_number": idx,
                        "employee_key": f"{company}-{item['phone']}",
                        "name": item.get("name"),
                    }

            if existing:
                batch_id = dict(existing)["batch_id"]
                cur.execute("DELETE FROM employee_import_rows WHERE batch_id=%s AND company_code=%s", (batch_id, company))
                cur.execute(
                    """
                    UPDATE employee_import_batches
                    SET status='previewed', filename=%s, content_sha256=%s, source_system=%s,
                        total_rows=%s, totals=%s::jsonb, updated_at=now(),
                        metadata=%s::jsonb
                    WHERE batch_id=%s AND company_code=%s
                    RETURNING *
                    """,
                    (
                        filename,
                        content_sha,
                        batch_source,
                        len(classified),
                        json.dumps(totals),
                        json.dumps({"replay_refreshed": True}),
                        batch_id,
                        company,
                    ),
                )
                batch = dict(cur.fetchone())
            else:
                cur.execute(
                    """
                    INSERT INTO employee_import_batches (
                      company_code, domain, contract, contract_version, status, filename,
                      content_sha256, idempotency_key, source_system, total_rows, totals,
                      options, metadata, created_by
                    ) VALUES (
                      %s,%s,%s,%s,'previewed',%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s
                    )
                    RETURNING *
                    """,
                    (
                        company,
                        DOMAIN,
                        CONTRACT,
                        CONTRACT_VERSION,
                        filename,
                        content_sha,
                        key,
                        batch_source,
                        len(classified),
                        json.dumps(totals),
                        json.dumps({"create_only": True, "no_messages": True}),
                        json.dumps({}),
                        actor,
                    ),
                )
                batch = dict(cur.fetchone())

            for item in classified:
                norm = item.get("normalized") or {}
                cur.execute(
                    """
                    INSERT INTO employee_import_rows (
                      batch_id, company_code, row_number, status, name, phone, email,
                      position_title, department, start_date, external_employee_id, payroll_id,
                      source_system, employee_key, reason, raw, normalized, detail
                    ) VALUES (
                      %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb
                    )
                    """,
                    (
                        batch["batch_id"],
                        company,
                        item["row_number"],
                        item["status"],
                        item.get("name"),
                        item.get("phone") or norm.get("phone"),
                        norm.get("email"),
                        norm.get("position_title"),
                        norm.get("department"),
                        norm.get("start_date"),
                        norm.get("external_employee_id"),
                        norm.get("payroll_id"),
                        norm.get("source_system"),
                        item.get("employee_key"),
                        item.get("reason"),
                        json.dumps(item.get("raw") or {}),
                        json.dumps(norm),
                        json.dumps(item.get("detail") or {}),
                    ),
                )
            conn.commit()
            cur.execute(
                "SELECT * FROM employee_import_rows WHERE batch_id=%s AND company_code=%s ORDER BY row_number",
                (batch["batch_id"], company),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
    out = _batch_payload(batch, rows)
    out["replayed"] = False
    out["dry_run"] = True
    return out


def commit_import_batch(
    legacy: Any,
    context: dict[str, Any],
    *,
    batch_id: str | None = None,
    raw: bytes | None = None,
    filename: str | None = None,
    source_system: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    if not foundation_enabled(company):
        raise legacy.HTTPException(status_code=403, detail={"error": "employee_migration_foundation_disabled"})

    # Allow confirm-with-file: resolve/create preview first when batch_id omitted.
    if not batch_id:
        if raw is None:
            raise legacy.HTTPException(status_code=422, detail={"error": "batch_id_or_file_required"})
        preview = preview_or_replay_import(
            legacy,
            context,
            raw=raw,
            filename=filename or "import.csv",
            source_system=source_system,
            idempotency_key=idempotency_key,
        )
        batch_id = preview["batch_id"]

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT * FROM employee_import_batches
                WHERE company_code=%s AND batch_id=%s
                FOR UPDATE
                """,
                (company, batch_id),
            )
            batch_row = cur.fetchone()
            if not batch_row:
                raise legacy.HTTPException(status_code=404, detail={"error": "batch_not_found"})
            batch = dict(batch_row)
            if batch.get("status") == "rolled_back":
                raise legacy.HTTPException(status_code=409, detail={"error": "batch_rolled_back"})
            if batch.get("status") in {"committed", "partial"}:
                cur.execute(
                    "SELECT * FROM employee_import_rows WHERE batch_id=%s AND company_code=%s ORDER BY row_number",
                    (batch_id, company),
                )
                rows = [dict(r) for r in (cur.fetchall() or [])]
                conn.commit()
                out = _batch_payload(batch, rows)
                out["replayed"] = True
                out["dry_run"] = False
                return out
            if batch.get("status") not in {"previewed", "committing", "failed"}:
                raise legacy.HTTPException(
                    status_code=409,
                    detail={"error": "batch_not_committable", "status": batch.get("status")},
                )
            cur.execute(
                """
                UPDATE employee_import_batches
                SET status='committing', updated_at=now()
                WHERE batch_id=%s AND company_code=%s
                """,
                (batch_id, company),
            )
            cur.execute(
                """
                SELECT * FROM employee_import_rows
                WHERE batch_id=%s AND company_code=%s
                ORDER BY row_number
                FOR UPDATE
                """,
                (batch_id, company),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()

    created = 0
    updated = 0
    failed = 0
    for row in rows:
        status = str(row.get("status") or "")
        if status not in {"will_create", "will_update"}:
            continue
        norm = row.get("normalized") or {}
        if isinstance(norm, str):
            norm = json.loads(norm)
        detail = row.get("detail") or {}
        if isinstance(detail, str):
            detail = json.loads(detail)

        if status == "will_update":
            employee_key = str(row.get("employee_key") or detail.get("match", {}).get("employee_key") or "").strip()
            changes = detail.get("changes") if isinstance(detail, dict) else {}
            if not isinstance(changes, dict):
                changes = {}
            if not employee_key or not changes:
                with legacy.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE employee_import_rows
                            SET status='failed', reason=%s, updated_at=now()
                            WHERE row_id=%s AND company_code=%s
                            """,
                            ("Update preview missing employee or changes.", row["row_id"], company),
                        )
                        failed += 1
                        conn.commit()
                continue
            try:
                fields: dict[str, Any] = {}
                for field, ch in changes.items():
                    if field == "manager_employee_key":
                        continue
                    if not isinstance(ch, dict):
                        continue
                    fields[field] = ch.get("after")
                expected = _parse_expected_updated_at(
                    (detail or {}).get("expected_updated_at") if isinstance(detail, dict) else None
                )
                result = (
                    legacy.update_company_employee(
                        company,
                        employee_key,
                        fields=fields,
                        expected_updated_at=expected,
                    )
                    if fields
                    else {"status": "noop"}
                )
                upd_status = result.get("status")
                if upd_status == "conflict":
                    with legacy.db_connect() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                UPDATE employee_import_rows
                                SET status='failed', reason=%s, updated_at=now(),
                                    detail = COALESCE(detail, '{}'::jsonb) || %s::jsonb
                                WHERE row_id=%s AND company_code=%s
                                """,
                                (
                                    "Could not update — this person changed after preview. Needs review.",
                                    json.dumps({"commit_conflict": True}),
                                    row["row_id"],
                                    company,
                                ),
                            )
                            failed += 1
                            conn.commit()
                    continue
                if upd_status in {"not_found", "failed", "duplicate"}:
                    with legacy.db_connect() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                UPDATE employee_import_rows
                                SET status='failed', reason=%s, updated_at=now()
                                WHERE row_id=%s AND company_code=%s
                                """,
                                (result.get("reason") or "Could not be updated.", row["row_id"], company),
                            )
                            failed += 1
                            conn.commit()
                    continue
                if fields and upd_status not in {"updated", "noop"}:
                    with legacy.db_connect() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                UPDATE employee_import_rows
                                SET status='failed', reason=%s, updated_at=now()
                                WHERE row_id=%s AND company_code=%s
                                """,
                                (result.get("reason") or f"Unexpected update status: {upd_status}", row["row_id"], company),
                            )
                            failed += 1
                            conn.commit()
                    continue

                # Manager via canonical assignment history when included in changes.
                mgr_change = changes.get("manager_employee_key")
                applied_manager = None
                if isinstance(mgr_change, dict) and mgr_change.get("after"):
                    try:
                        applied_manager = _apply_manager_authoritative(
                            legacy,
                            context,
                            employee_key=employee_key,
                            manager_employee_key=str(mgr_change["after"]),
                            manager_phone=norm.get("manager_phone"),
                            batch_id=str(batch_id),
                            position_title=norm.get("position_title") or row.get("position_title"),
                        )
                    except Exception as mgr_exc:
                        with legacy.db_connect() as conn:
                            with conn.cursor() as cur:
                                next_detail = dict(detail) if isinstance(detail, dict) else {}
                                next_detail["manager_apply_error"] = str(mgr_exc)[:240]
                                cur.execute(
                                    """
                                    UPDATE employee_import_rows
                                    SET status='failed', reason=%s, updated_at=now(), detail=%s::jsonb
                                    WHERE row_id=%s AND company_code=%s
                                    """,
                                    (
                                        "Updated fields but manager could not be applied. Needs review.",
                                        json.dumps(next_detail),
                                        row["row_id"],
                                        company,
                                    ),
                                )
                                failed += 1
                                conn.commit()
                        continue

                with legacy.db_connect() as conn:
                    with conn.cursor() as cur:
                        stamp = {
                            "employee_migration_batch_id": str(batch_id),
                            "employee_migration_row_id": str(row["row_id"]),
                            "employee_migration_hub_updated": True,
                            "source_system": norm.get("source_system") or batch.get("source_system"),
                        }
                        cur.execute(
                            """
                            UPDATE employees
                            SET raw_json = COALESCE(raw_json, '{}'::jsonb) || %s::jsonb,
                                updated_at=now()
                            WHERE company_code=%s AND employee_key=%s
                            """,
                            (json.dumps(stamp), company, employee_key),
                        )
                        next_detail = dict(detail) if isinstance(detail, dict) else {}
                        next_detail["applied_changes"] = changes
                        if applied_manager is not None:
                            next_detail["manager_applied"] = True
                        cur.execute(
                            """
                            UPDATE employee_import_rows
                            SET status='updated', employee_key=%s, reason=%s, updated_at=now(),
                                detail=%s::jsonb
                            WHERE row_id=%s AND company_code=%s
                            """,
                            (
                                employee_key,
                                f"Updated ({', '.join(sorted(changes.keys()))}).",
                                json.dumps(next_detail),
                                row["row_id"],
                                company,
                            ),
                        )
                        conn.commit()
                try:
                    with legacy.db_connect() as conn2:
                        with conn2.cursor() as cur2:
                            _upsert_source_mapping(
                                cur2,
                                company=company,
                                employee_key=employee_key,
                                source_system=norm.get("source_system") or batch.get("source_system"),
                                external_employee_id=norm.get("external_employee_id")
                                or row.get("external_employee_id"),
                                payroll_id=norm.get("payroll_id") or row.get("payroll_id"),
                                batch_id=str(batch_id),
                                row_id=str(row["row_id"]),
                            )
                            conn2.commit()
                except Exception:
                    pass
                updated += 1
            except Exception as exc:
                failed += 1
                with legacy.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE employee_import_rows
                            SET status='failed', reason=%s, updated_at=now(),
                                detail=%s::jsonb
                            WHERE row_id=%s AND company_code=%s
                            """,
                            (
                                "Could not be updated right now.",
                                json.dumps({"error": str(exc)[:240]}),
                                row["row_id"],
                                company,
                            ),
                        )
                        conn.commit()
            continue

        # will_create
        try:
            result = legacy.create_company_employee(
                company,
                name=norm.get("name") or row.get("name"),
                phone=norm.get("phone") or row.get("phone"),
                email=norm.get("email") or row.get("email"),
                position_title=norm.get("position_title") or row.get("position_title"),
                department=norm.get("department") or row.get("department"),
                start_date=norm.get("start_date") or row.get("start_date"),
                # Existing-workforce import must not auto-open a compliance gap campaign.
                # HR enables a reconciliation campaign later; nationality/role drive applicability then.
                seed_compliance=False,
                start_onboarding=False,
            )
            status_c = result.get("status")
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    if status_c == "created":
                        employee_key = str(result.get("employee_key") or "")
                        preview_manager = detail.get("manager") if isinstance(detail, dict) else None
                        manager = _resolve_manager_at_commit(
                            legacy,
                            cur,
                            company=company,
                            batch_id=str(batch_id),
                            manager_phone=norm.get("manager_phone"),
                            preview_manager=preview_manager,
                        )
                        stamp = {
                            "employee_migration_batch_id": str(batch_id),
                            "employee_migration_row_id": str(row["row_id"]),
                            "employee_migration_hub_created": True,
                            "source_system": norm.get("source_system") or batch.get("source_system"),
                        }
                        if manager and manager.get("resolved") and manager.get("manager_employee_key"):
                            stamp["manager_employee_key"] = manager["manager_employee_key"]
                            stamp["manager_phone"] = manager.get("manager_phone")
                            stamp["manager_unresolved"] = False
                        elif manager and manager.get("manager_phone"):
                            stamp["manager_phone"] = manager.get("manager_phone")
                            stamp["manager_unresolved"] = True
                            stamp["manager_employee_key"] = None
                        cur.execute(
                            """
                            UPDATE employees
                            SET raw_json = COALESCE(raw_json, '{}'::jsonb) || %s::jsonb,
                                updated_at=now()
                            WHERE company_code=%s AND employee_key=%s
                            """,
                            (json.dumps(stamp), company, employee_key),
                        )
                        next_detail = dict(detail) if isinstance(detail, dict) else {}
                        if manager:
                            next_detail["manager"] = {
                                "manager_phone": manager.get("manager_phone"),
                                "resolved": bool(manager.get("resolved")),
                                "manager_employee_key": manager.get("manager_employee_key"),
                                "source": manager.get("source"),
                            }
                            if manager.get("warning"):
                                next_detail["warnings"] = list(next_detail.get("warnings") or []) + [
                                    str(manager["warning"])
                                ]
                        reason = "Added."
                        if manager and not manager.get("resolved") and manager.get("manager_phone"):
                            reason = f"Added. {_manager_warning(str(manager.get('manager_phone')))}"
                        cur.execute(
                            """
                            UPDATE employee_import_rows
                            SET status='created', employee_key=%s, reason=%s, updated_at=now(),
                                detail = %s::jsonb
                            WHERE row_id=%s AND company_code=%s
                            """,
                            (
                                employee_key,
                                reason,
                                json.dumps(next_detail),
                                row["row_id"],
                                company,
                            ),
                        )
                        conn.commit()
                        # Best-effort side effects — never roll back hub create/stamp.
                        try:
                            with legacy.db_connect() as conn2:
                                with conn2.cursor() as cur2:
                                    _upsert_source_mapping(
                                        cur2,
                                        company=company,
                                        employee_key=employee_key,
                                        source_system=norm.get("source_system") or batch.get("source_system"),
                                        external_employee_id=norm.get("external_employee_id")
                                        or row.get("external_employee_id"),
                                        payroll_id=norm.get("payroll_id") or row.get("payroll_id"),
                                        batch_id=str(batch_id),
                                        row_id=str(row["row_id"]),
                                    )
                                    conn2.commit()
                        except Exception:
                            pass
                        if manager and manager.get("resolved") and manager.get("manager_employee_key"):
                            try:
                                _apply_manager_authoritative(
                                    legacy,
                                    context,
                                    employee_key=employee_key,
                                    manager_employee_key=str(manager["manager_employee_key"]),
                                    manager_phone=manager.get("manager_phone"),
                                    batch_id=str(batch_id),
                                    position_title=norm.get("position_title") or row.get("position_title"),
                                )
                            except Exception:
                                pass
                        created += 1
                    elif status_c == "exists":
                        cur.execute(
                            """
                            UPDATE employee_import_rows
                            SET status='skipped', employee_key=%s, reason=%s, updated_at=now()
                            WHERE row_id=%s AND company_code=%s
                            """,
                            (
                                result.get("employee_key"),
                                "Already in the workforce.",
                                row["row_id"],
                                company,
                            ),
                        )
                        conn.commit()
                    else:
                        cur.execute(
                            """
                            UPDATE employee_import_rows
                            SET status='failed', reason=%s, updated_at=now()
                            WHERE row_id=%s AND company_code=%s
                            """,
                            (result.get("reason") or "Could not be added.", row["row_id"], company),
                        )
                        failed += 1
                        conn.commit()
        except Exception as exc:
            failed += 1
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE employee_import_rows
                        SET status='failed', reason=%s, updated_at=now(),
                            detail=%s::jsonb
                        WHERE row_id=%s AND company_code=%s
                        """,
                        (
                            "Could not be added right now.",
                            json.dumps({"error": str(exc)[:240]}),
                            row["row_id"],
                            company,
                        ),
                    )
                    conn.commit()

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM employee_import_rows WHERE batch_id=%s AND company_code=%s ORDER BY row_number",
                (batch_id, company),
            )
            final_rows = [dict(r) for r in (cur.fetchall() or [])]
            totals = empty_totals()
            for row in final_rows:
                key = _status_to_total_key(str(row.get("status") or ""))
                if key:
                    totals[key] += 1
                detail = row.get("detail") or {}
                if isinstance(detail, str):
                    detail = json.loads(detail)
                if detail.get("warnings") or (
                    isinstance(detail.get("manager"), dict) and detail["manager"].get("resolved") is False
                ):
                    totals["warnings"] += 1
            applied = created + updated
            final_status = "partial" if failed else "committed"
            if applied == 0 and failed > 0:
                final_status = "failed"
            cur.execute(
                """
                UPDATE employee_import_batches
                SET status=%s, totals=%s::jsonb, committed_at=now(), updated_at=now()
                WHERE batch_id=%s AND company_code=%s
                RETURNING *
                """,
                (final_status, json.dumps(totals), batch_id, company),
            )
            batch = dict(cur.fetchone())
            conn.commit()

    if created or updated:
        legacy.record_admin_audit(
            context,
            "employees_imported",
            summary=(
                f"Migration batch {batch_id}: added {created}, updated {updated}."
            ),
            target_type="company",
            target=company,
            details={
                "batch_id": str(batch_id),
                "created": created,
                "updated": updated,
                "failed": failed,
                "totals": totals,
            },
        )
    out = _batch_payload(batch, final_rows)
    out["replayed"] = False
    out["dry_run"] = False
    return out


def list_import_batches(
    legacy: Any,
    context: dict[str, Any],
    *,
    limit: int = 25,
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    if not foundation_enabled(company):
        raise legacy.HTTPException(status_code=403, detail={"error": "employee_migration_foundation_disabled"})
    limit = max(1, min(int(limit or 25), 100))
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT batch_id, company_code, status, filename, content_sha256, idempotency_key,
                       source_system, total_rows, totals, created_by, created_at, updated_at,
                       committed_at, rolled_back_at
                FROM employee_import_batches
                WHERE company_code=%s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (company, limit),
            )
            batches = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
    return {"ok": True, "batches": _jsonable(batches), "honesty": honesty_payload()}


def list_review_items(
    legacy: Any,
    context: dict[str, Any],
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """Open Needs review rows from recent batches (conflict / unresolved identity)."""
    company = legacy.require_employee_roster_admin(context)
    if not foundation_enabled(company):
        raise legacy.HTTPException(status_code=403, detail={"error": "employee_migration_foundation_disabled"})
    limit = max(1, min(int(limit or 100), 500))
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT r.*, b.filename, b.status AS batch_status, b.created_at AS batch_created_at
                FROM employee_import_rows r
                JOIN employee_import_batches b ON b.batch_id = r.batch_id AND b.company_code = r.company_code
                WHERE r.company_code=%s
                  AND r.status IN ('conflict', 'invalid')
                  AND b.status IN ('previewed', 'committed', 'partial', 'failed')
                ORDER BY b.created_at DESC, r.row_number ASC
                LIMIT %s
                """,
                (company, limit),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
    items = []
    for row in rows:
        entry = _row_entry(row)
        entry["batch_id"] = str(row.get("batch_id"))
        entry["filename"] = row.get("filename")
        entry["batch_status"] = row.get("batch_status")
        entry["batch_created_at"] = (
            row.get("batch_created_at").isoformat()
            if hasattr(row.get("batch_created_at"), "isoformat")
            else row.get("batch_created_at")
        )
        items.append(entry)
    return {
        "ok": True,
        "items": items,
        "count": len(items),
        "honesty": honesty_payload(),
        "deactivate_enabled": False,
    }


def get_import_batch(legacy: Any, context: dict[str, Any], *, batch_id: str) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    if not foundation_enabled(company):
        raise legacy.HTTPException(status_code=403, detail={"error": "employee_migration_foundation_disabled"})
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                "SELECT * FROM employee_import_batches WHERE company_code=%s AND batch_id=%s LIMIT 1",
                (company, batch_id),
            )
            batch = cur.fetchone()
            if not batch:
                raise legacy.HTTPException(status_code=404, detail={"error": "batch_not_found"})
            batch = dict(batch)
            cur.execute(
                "SELECT * FROM employee_import_rows WHERE batch_id=%s AND company_code=%s ORDER BY row_number",
                (batch_id, company),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
    out = _batch_payload(batch, rows)
    out["dry_run"] = batch.get("status") == "previewed"
    return out


def exception_csv(legacy: Any, context: dict[str, Any], *, batch_id: str) -> tuple[str, str]:
    """Return (filename, csv_text) for non-create outcomes."""
    company = legacy.require_employee_roster_admin(context)
    if not foundation_enabled(company):
        raise legacy.HTTPException(status_code=403, detail={"error": "employee_migration_foundation_disabled"})
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                "SELECT batch_id FROM employee_import_batches WHERE company_code=%s AND batch_id=%s LIMIT 1",
                (company, batch_id),
            )
            if not cur.fetchone():
                raise legacy.HTTPException(status_code=404, detail={"error": "batch_not_found"})
            cur.execute(
                """
                SELECT row_number, status, name, phone, email, external_employee_id, payroll_id,
                       source_system, employee_key, reason, detail, normalized
                FROM employee_import_rows
                WHERE batch_id=%s AND company_code=%s
                  AND (
                    status IN ('skipped','conflict','invalid','failed','rolled_back')
                    OR COALESCE(detail->'warnings', '[]'::jsonb) <> '[]'::jsonb
                    OR COALESCE(detail->'manager'->>'resolved', 'true') = 'false'
                  )
                ORDER BY row_number
                """,
                (batch_id, company),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=[
            "row_number",
            "status",
            "name",
            "phone",
            "email",
            "external_employee_id",
            "payroll_id",
            "source_system",
            "manager_phone",
            "manager_resolved",
            "manager_employee_key",
            "employee_key",
            "reason",
            "warnings",
        ],
    )
    writer.writeheader()
    for row in rows:
        detail = row.get("detail") or {}
        if isinstance(detail, str):
            detail = json.loads(detail)
        norm = row.get("normalized") or {}
        if isinstance(norm, str):
            norm = json.loads(norm)
        manager = detail.get("manager") if isinstance(detail, dict) else {}
        warnings = detail.get("warnings") if isinstance(detail, dict) else []
        writer.writerow(
            {
                "row_number": row.get("row_number"),
                "status": row.get("status"),
                "name": row.get("name"),
                "phone": row.get("phone"),
                "email": row.get("email"),
                "external_employee_id": row.get("external_employee_id"),
                "payroll_id": row.get("payroll_id"),
                "source_system": row.get("source_system"),
                "manager_phone": (manager or {}).get("manager_phone") or norm.get("manager_phone"),
                "manager_resolved": (manager or {}).get("resolved"),
                "manager_employee_key": (manager or {}).get("manager_employee_key"),
                "employee_key": row.get("employee_key"),
                "reason": row.get("reason"),
                "warnings": " | ".join(warnings or []),
            }
        )
    return f"employee-import-exceptions-{batch_id}.csv", buf.getvalue()


def rollback_import_batch(
    legacy: Any,
    context: dict[str, Any],
    *,
    batch_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    company = legacy.require_employee_roster_admin(context)
    if not foundation_enabled(company):
        raise legacy.HTTPException(status_code=403, detail={"error": "employee_migration_foundation_disabled"})
    rollback_key = str(idempotency_key or "").strip()
    if not rollback_key:
        raise legacy.HTTPException(status_code=422, detail={"error": "idempotency_key_required"})

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT * FROM employee_import_batches
                WHERE company_code=%s AND batch_id=%s
                FOR UPDATE
                """,
                (company, batch_id),
            )
            batch_row = cur.fetchone()
            if not batch_row:
                raise legacy.HTTPException(status_code=404, detail={"error": "batch_not_found"})
            batch = dict(batch_row)
            meta = batch.get("metadata") or {}
            if isinstance(meta, str):
                meta = json.loads(meta)
            prior = meta.get("rollback")
            if prior and prior.get("idempotency_key") == rollback_key:
                conn.commit()
                return {
                    "ok": True,
                    "replayed": True,
                    "batch_id": str(batch_id),
                    "status": batch.get("status"),
                    "removed": int(prior.get("removed") or 0),
                    "blocked": prior.get("blocked") or [],
                }
            if batch.get("status") == "rolled_back":
                conn.commit()
                return {"ok": True, "replayed": True, "batch_id": str(batch_id), "status": "rolled_back", "removed": 0, "blocked": []}
            if batch.get("status") not in {"committed", "partial", "failed"}:
                raise legacy.HTTPException(
                    status_code=409,
                    detail={"error": "batch_not_rollbackable", "status": batch.get("status")},
                )

            cur.execute(
                """
                SELECT * FROM employee_import_rows
                WHERE batch_id=%s AND company_code=%s AND status IN ('created', 'updated')
                ORDER BY row_number
                FOR UPDATE
                """,
                (batch_id, company),
            )
            applied_rows = [dict(r) for r in (cur.fetchall() or [])]
            removed = 0
            reverted = 0
            skipped_fields: list[dict[str, Any]] = []
            blocked: list[dict[str, Any]] = []
            for row in applied_rows:
                employee_key = str(row.get("employee_key") or "").strip()
                if not employee_key:
                    continue
                row_status = str(row.get("status") or "")

                if row_status == "updated":
                    detail = row.get("detail") or {}
                    if isinstance(detail, str):
                        detail = json.loads(detail)
                    changes = detail.get("changes") or detail.get("applied_changes") or {}
                    if not isinstance(changes, dict) or not changes:
                        cur.execute(
                            """
                            UPDATE employee_import_rows
                            SET status='rolled_back', reason=%s, updated_at=now()
                            WHERE row_id=%s
                            """,
                            ("No field changes to undo.", row["row_id"]),
                        )
                        reverted += 1
                        continue
                    cur.execute(
                        "SELECT * FROM employees WHERE company_code=%s AND employee_key=%s FOR UPDATE",
                        (company, employee_key),
                    )
                    emp = cur.fetchone()
                    if not emp:
                        cur.execute(
                            """
                            UPDATE employee_import_rows
                            SET status='rolled_back', reason=%s, updated_at=now()
                            WHERE row_id=%s
                            """,
                            ("Employee already absent.", row["row_id"]),
                        )
                        reverted += 1
                        continue
                    emp = dict(emp)
                    current = _hub_field_snapshot(emp)
                    revert_fields: dict[str, Any] = {}
                    field_notes: list[str] = []
                    for field, ch in changes.items():
                        if field == "manager_employee_key":
                            continue
                        if not isinstance(ch, dict):
                            continue
                        after = ch.get("after")
                        before = ch.get("before")
                        cur_val = current.get(field)
                        # Normalize for comparison
                        cur_n = str(cur_val).strip() if cur_val not in (None, "") else None
                        after_n = str(after).strip() if after not in (None, "") else None
                        if field == "start_date":
                            cur_n = (cur_n or "")[:10] or None
                            after_n = (after_n or "")[:10] or None
                        if cur_n == after_n:
                            revert_fields[field] = before
                        else:
                            field_notes.append(field)
                            skipped_fields.append(
                                {
                                    "employee_key": employee_key,
                                    "field": field,
                                    "reason": "changed_after_batch",
                                    "current": cur_n,
                                    "batch_after": after_n,
                                }
                            )
                    if revert_fields:
                        # Apply in-place within this transaction via SQL (avoid nested connections).
                        set_parts = []
                        params: list[Any] = []
                        profile = emp.get("profile") if isinstance(emp.get("profile"), dict) else {}
                        for col, val in revert_fields.items():
                            if col == "department":
                                profile = {**profile}
                                if val:
                                    profile["department"] = val
                                else:
                                    profile.pop("department", None)
                                set_parts.append("profile=%s::jsonb")
                                params.append(json.dumps(profile))
                            else:
                                set_parts.append(f"{col}=%s")
                                params.append(val)
                        set_parts.append("updated_at=now()")
                        params.extend([employee_key, company])
                        cur.execute(
                            f"UPDATE employees SET {', '.join(set_parts)} WHERE employee_key=%s AND company_code=%s",
                            params,
                        )
                    # Manager undo concurrency-safe
                    mgr_ch = changes.get("manager_employee_key")
                    if isinstance(mgr_ch, dict):
                        cur_mgr = None
                        cur.execute(
                            """
                            SELECT manager_employee_key
                            FROM employee_org_assignment_history
                            WHERE company_code=%s AND employee_key=%s AND effective_to IS NULL
                            ORDER BY effective_from DESC, created_at DESC
                            LIMIT 1
                            """,
                            (company, employee_key),
                        )
                        hit = cur.fetchone()
                        if hit:
                            cur_mgr = (hit["manager_employee_key"] if isinstance(hit, dict) else hit[0]) or None
                            if cur_mgr:
                                cur_mgr = str(cur_mgr)
                        after_mgr = mgr_ch.get("after")
                        before_mgr = mgr_ch.get("before")
                        if (cur_mgr or None) == (str(after_mgr) if after_mgr else None):
                            # Defer assignment restore outside FOR UPDATE loop via note; apply after commit below
                            detail["_undo_manager"] = {"before": before_mgr, "after": after_mgr}
                        else:
                            skipped_fields.append(
                                {
                                    "employee_key": employee_key,
                                    "field": "manager_employee_key",
                                    "reason": "changed_after_batch",
                                    "current": cur_mgr,
                                    "batch_after": after_mgr,
                                }
                            )
                            field_notes.append("manager_employee_key")
                    reason = "Update undone."
                    if field_notes:
                        reason = (
                            f"Update partially undone (left alone: {', '.join(field_notes)} — changed after this batch)."
                        )
                    next_detail = dict(detail) if isinstance(detail, dict) else {}
                    next_detail["undo"] = {
                        "reverted_fields": list(revert_fields.keys()),
                        "skipped_fields": field_notes,
                    }
                    cur.execute(
                        """
                        UPDATE employee_import_rows
                        SET status='rolled_back', reason=%s, updated_at=now(), detail=%s::jsonb
                        WHERE row_id=%s
                        """,
                        (reason, json.dumps(next_detail), row["row_id"]),
                    )
                    reverted += 1
                    continue

                # created → remove if stamped and no progress
                cur.execute(
                    """
                    SELECT employee_key, raw_json, onboarding_status
                    FROM employees
                    WHERE company_code=%s AND employee_key=%s
                    FOR UPDATE
                    """,
                    (company, employee_key),
                )
                emp = cur.fetchone()
                if not emp:
                    cur.execute(
                        """
                        UPDATE employee_import_rows
                        SET status='rolled_back', reason=%s, updated_at=now()
                        WHERE row_id=%s
                        """,
                        ("Hub row already absent.", row["row_id"]),
                    )
                    removed += 1
                    continue
                emp = dict(emp)
                raw_json = emp.get("raw_json") or {}
                if isinstance(raw_json, str):
                    raw_json = json.loads(raw_json)
                stamped = str(raw_json.get("employee_migration_batch_id") or "") == str(batch_id)
                hub_created = bool(raw_json.get("employee_migration_hub_created"))
                onboarding = str(emp.get("onboarding_status") or "").lower()
                if not stamped or not hub_created or onboarding not in {"", "not_started", "pending"}:
                    blocked.append(
                        {
                            "employee_key": employee_key,
                            "reason": "employee_has_progress_or_missing_stamp",
                        }
                    )
                    continue
                cur.execute(
                    """
                    UPDATE employee_source_mappings
                    SET active=false, updated_at=now()
                    WHERE company_code=%s AND employee_key=%s AND batch_id=%s
                    """,
                    (company, employee_key, batch_id),
                )
                cur.execute(
                    "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                    (company, employee_key),
                )
                cur.execute(
                    """
                    UPDATE employee_import_rows
                    SET status='rolled_back', reason=%s, updated_at=now()
                    WHERE row_id=%s
                    """,
                    ("Rolled back.", row["row_id"]),
                )
                removed += 1

            meta["rollback"] = {
                "idempotency_key": rollback_key,
                "removed": removed,
                "reverted": reverted,
                "skipped_fields": skipped_fields,
                "blocked": blocked,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            cur.execute(
                """
                UPDATE employee_import_batches
                SET status='rolled_back', rolled_back_at=now(), updated_at=now(), metadata=%s::jsonb
                WHERE batch_id=%s AND company_code=%s
                RETURNING *
                """,
                (json.dumps(meta), batch_id, company),
            )
            batch = dict(cur.fetchone())
            # Collect manager undos that need assignment history restore
            cur.execute(
                """
                SELECT row_id, employee_key, detail FROM employee_import_rows
                WHERE batch_id=%s AND company_code=%s AND status='rolled_back'
                """,
                (batch_id, company),
            )
            undo_mgr_rows = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()

    # Restore managers outside the batch lock (Wave4 uses its own connections).
    for row in undo_mgr_rows:
        detail = row.get("detail") or {}
        if isinstance(detail, str):
            detail = json.loads(detail)
        undo_mgr = detail.get("_undo_manager") if isinstance(detail, dict) else None
        if not undo_mgr or not undo_mgr.get("before"):
            continue
        try:
            _apply_manager_authoritative(
                legacy,
                context,
                employee_key=str(row.get("employee_key")),
                manager_employee_key=str(undo_mgr["before"]),
                manager_phone=None,
                batch_id=str(batch_id),
            )
        except Exception:
            skipped_fields.append(
                {
                    "employee_key": row.get("employee_key"),
                    "field": "manager_employee_key",
                    "reason": "manager_restore_failed",
                }
            )

    legacy.record_admin_audit(
        context,
        "employees_import_rolled_back",
        summary=(
            f"Rolled back employee import batch {batch_id} "
            f"({removed} removed, {reverted} updates undone)."
        ),
        target_type="company",
        target=company,
        details={
            "batch_id": str(batch_id),
            "removed": removed,
            "reverted": reverted,
            "skipped_fields": skipped_fields,
            "blocked": blocked,
            "idempotency_key": rollback_key,
        },
    )
    return {
        "ok": True,
        "replayed": False,
        "batch_id": str(batch_id),
        "status": "rolled_back",
        "removed": removed,
        "reverted": reverted,
        "skipped_fields": skipped_fields,
        "blocked": blocked,
        "honesty": honesty_payload(),
    }
