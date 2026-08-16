#!/usr/bin/env python3
"""Bank ESS — employee self-service bank details as a governed change request.

Layered authority (never collapsed into one mutable field)
----------------------------------------------------------
  1. employee_submitted   employee_ess_requests.proposed_values (SEALED ciphertext)
  2. hr_verified          employee_bank_verified — stamped when every approval
                          stage approved; proves who verified what, and when
  3. payroll_effective    employee_bank_effective — effective-dated history;
                          the ONLY layer payroll may read

Employee input is a change request. It never mutates verified payroll truth.
Approval is atomic and idempotent. History is append-only.

Sensitive-data rules enforced here
----------------------------------
* Full IBAN / account number are never stored in `proposed_values`; only a
  sealed ciphertext blob plus a masked display projection and a fingerprint.
* Nothing sensitive is returned unmasked without an explicit unmask permission,
  and every reveal is logged.
* Errors raised from this module never echo a full account value.
* Evidence is stored by private storage ref only — never a public URL.

Account-format neutrality
-------------------------
`validate_account` is a registry keyed by country/scheme. Kuwait IBAN is one
entry, not the model. Adding salary-transfer requirements or a payroll
integration means adding a validator/consumer, not reshaping these tables.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Mapping

CONTRACT_VERSION = "bank_ess_v1_p2_production_workflow"

# Fields the employee may propose. Everything else is ignored, not stored.
PROPOSABLE_FIELDS = ("iban", "bank_name", "account_holder", "account_number", "swift", "branch")
SENSITIVE_PROPOSABLE = frozenset({"iban", "account_number"})

SEALED_KEY = "__sealed_bank"

# Employee-facing submission states, derived from the underlying request state.
SUBMISSION_NONE = "none"
SUBMISSION_DRAFT = "draft"
SUBMISSION_PENDING_HR = "pending_hr"
SUBMISSION_PENDING_PAYROLL = "pending_payroll"
SUBMISSION_PENDING_REVIEW = "pending_review"  # legacy alias; prefer pending_hr
SUBMISSION_APPROVED = "approved"
SUBMISSION_APPLIED = "applied"
SUBMISSION_REJECTED = "rejected"
SUBMISSION_NEEDS_CORRECTION = "needs_correction"
SUBMISSION_WITHDRAWN = "withdrawn"

# Underlying Wave 5 request states that still occupy the single active slot.
ACTIVE_REQUEST_STATES = (
    "draft",
    "submitted",
    "needs_information",
    "needs_review",
    "pending_manager",
    "pending_hr",
    "pending_payroll",
    "approved",
)

_ON = frozenset({"1", "true", "yes", "on", "enabled"})


def bank_ess_enabled(company_code: str | None = None) -> bool:
    if (os.environ.get("WATHEFNI_BANK_ESS_V1") or "").strip().lower() not in _ON:
        return False
    companies = {
        c.strip().upper()
        for c in (os.environ.get("WATHEFNI_BANK_ESS_V1_COMPANIES") or "WATHEFNI").split(",")
        if c.strip()
    }
    if company_code and str(company_code).upper() not in companies:
        return False
    return True


def bank_ess_employee_allowlist() -> set[str]:
    return {
        k.strip()
        for k in (os.environ.get("WATHEFNI_BANK_ESS_V1_EMPLOYEE_ALLOWLIST") or "").split(",")
        if k.strip()
    }


def bank_ess_eligibility(
    company_code: str | None,
    employee_key: str | None,
    *,
    ess_v5_enabled: bool | None = None,
) -> dict[str, Any]:
    """Single authority for whether an employee may use Bank ESS surfaces.

    Used by `/app/bank`, `/app/me` feature projection, and onboarding checklist
    actions so no surface can advertise `open_bank` while `/app/bank` refuses.
    """
    company = str(company_code or "").strip().upper()
    key = str(employee_key or "").strip()
    if not bank_ess_enabled(company):
        return {
            "eligible": False,
            "reason": "bank_ess_disabled",
            "company_code": company or None,
            "employee_key": key or None,
            "contract_version": CONTRACT_VERSION,
        }
    if ess_v5_enabled is None:
        try:
            import employee_selfservice_wave5 as _w5

            ess_v5_enabled = bool(_w5.ess_v5_enabled(company))
        except Exception:
            ess_v5_enabled = False
    if not ess_v5_enabled:
        return {
            "eligible": False,
            "reason": "ess_v5_disabled",
            "company_code": company or None,
            "employee_key": key or None,
            "contract_version": CONTRACT_VERSION,
        }
    allow = bank_ess_employee_allowlist()
    if allow and key not in allow:
        return {
            "eligible": False,
            "reason": "bank_ess_not_allowlisted",
            "company_code": company or None,
            "employee_key": key or None,
            "contract_version": CONTRACT_VERSION,
        }
    return {
        "eligible": True,
        "reason": None,
        "company_code": company or None,
        "employee_key": key or None,
        "contract_version": CONTRACT_VERSION,
    }


# ---------------------------------------------------------------------------
# Masking helpers — the only way sensitive bank values leave this module
# ---------------------------------------------------------------------------
def mask_account(value: str | None, *, keep: int = 4) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) <= keep:
        return "*" * len(raw)
    return "*" * (len(raw) - keep) + raw[-keep:]


def fingerprint(value: str | None) -> str | None:
    raw = re.sub(r"\s+", "", str(value or "")).upper()
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def display_projection(values: Mapping[str, Any] | None) -> dict[str, Any]:
    """Masked, safe-to-log projection of bank values."""
    data = dict(values or {})
    out: dict[str, Any] = {}
    for field in PROPOSABLE_FIELDS:
        raw = data.get(field)
        if raw in (None, ""):
            continue
        if field in SENSITIVE_PROPOSABLE:
            out[field] = mask_account(raw)
            out[f"{field}_masked"] = True
            out[f"{field}_last4"] = str(raw).strip()[-4:]
        else:
            out[field] = str(raw).strip()
    return out


# ---------------------------------------------------------------------------
# Account validation registry — format-neutral by design
# ---------------------------------------------------------------------------
def _iban_checksum_ok(iban: str) -> bool:
    s = re.sub(r"\s+", "", iban).upper()
    if len(s) < 5:
        return False
    rearranged = s[4:] + s[:4]
    digits = ""
    for ch in rearranged:
        if ch.isdigit():
            digits += ch
        elif ch.isalpha():
            digits += str(ord(ch) - 55)
        else:
            return False
    try:
        return int(digits) % 97 == 1
    except Exception:
        return False


def _validate_kw_iban(values: Mapping[str, Any]) -> dict[str, Any]:
    raw = re.sub(r"\s+", "", str(values.get("iban") or "")).upper()
    account = re.sub(r"[\s-]+", "", str(values.get("account_number") or "")).upper()
    problems: list[str] = []
    if not raw:
        if not account:
            problems.append("account_identifier_required")
        elif not re.fullmatch(r"[A-Z0-9]{4,34}", account):
            problems.append("account_number_format_invalid")
    else:
        if not raw.startswith("KW"):
            problems.append("iban_country_not_kw")
        if len(raw) != 30:
            problems.append("iban_length_invalid")
        if not re.fullmatch(r"[A-Z0-9]+", raw):
            problems.append("iban_charset_invalid")
        if not problems and not _iban_checksum_ok(raw):
            problems.append("iban_checksum_invalid")
    return {
        "scheme": "kw_iban",
        "ok": not problems,
        # Never echo the value itself in problem output.
        "problems": problems,
    }


def _validate_generic(values: Mapping[str, Any]) -> dict[str, Any]:
    iban = re.sub(r"\s+", "", str(values.get("iban") or "")).upper()
    account = re.sub(r"[\s-]+", "", str(values.get("account_number") or "")).upper()
    problems: list[str] = []
    if not iban and not account:
        problems.append("account_identifier_required")
    if iban:
        # ISO 13616 structure + checksum; country-specific length remains a
        # registry concern. This rejects punctuation without hardcoding a bank.
        if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", iban):
            problems.append("iban_format_invalid")
        elif not _iban_checksum_ok(iban):
            problems.append("iban_checksum_invalid")
    if account and not re.fullmatch(r"[A-Z0-9]{4,34}", account):
        problems.append("account_number_format_invalid")
    return {"scheme": "generic", "ok": not problems, "problems": problems}


VALIDATORS: dict[str, Any] = {
    "kw_iban": _validate_kw_iban,
    "generic": _validate_generic,
}


def default_scheme(company_code: str | None = None) -> str:
    raw = (os.environ.get("WATHEFNI_BANK_ESS_SCHEME") or "").strip().lower()
    if raw in VALIDATORS:
        return raw
    return "kw_iban"


def validate_account(values: Mapping[str, Any], *, scheme: str | None = None) -> dict[str, Any]:
    key = str(scheme or default_scheme()).lower()
    fn = VALIDATORS.get(key) or _validate_generic
    result = fn(values)
    env_enforce = (os.environ.get("WATHEFNI_BANK_ESS_ENFORCE_VALIDATION") or "").strip().lower() in _ON
    # Kuwait IBAN is always enforced at submit so invalid accounts cannot pass HR/payroll
    # and only fail at Apply. Other schemes remain advisory unless the flag is on.
    result["enforced"] = True if key == "kw_iban" else env_enforce
    result["scheme"] = key
    return result


def validation_error_detail(validation: Mapping[str, Any]) -> dict[str, Any]:
    """Localized, non-sensitive correction copy for a rejected bank format."""
    problems = [str(item) for item in validation.get("problems") or []]
    if "iban_country_not_kw" in problems:
        en = "Enter a Kuwait IBAN beginning with KW."
        ar = "أدخل رقم آيبان كويتي يبدأ بـ KW."
    elif "iban_length_invalid" in problems:
        en = "A Kuwait IBAN must contain 30 letters and numbers."
        ar = "يجب أن يتكون الآيبان الكويتي من 30 حرفًا ورقمًا."
    elif "iban_charset_invalid" in problems or "iban_format_invalid" in problems:
        en = "Use letters and numbers only in the IBAN."
        ar = "استخدم الحروف والأرقام فقط في الآيبان."
    elif "iban_checksum_invalid" in problems:
        en = "Check the IBAN. Its checksum is not valid."
        ar = "تحقق من الآيبان؛ رقم التحقق غير صحيح."
    elif "account_number_format_invalid" in problems:
        en = "Use 4–34 letters and numbers for the account number."
        ar = "استخدم من 4 إلى 34 حرفًا ورقمًا لرقم الحساب."
    else:
        en = "Check the IBAN or account number and try again."
        ar = "تحقق من الآيبان أو رقم الحساب وحاول مرة أخرى."
    return {
        "error": "bank_account_invalid",
        "message": en,
        "message_en": en,
        "message_ar": ar,
        "scheme": validation.get("scheme"),
        "problems": problems,
        "fields": problem_fields(problems),
    }


# ---------------------------------------------------------------------------
# Sealed proposals — plaintext bank values never rest in proposed_values
# ---------------------------------------------------------------------------
def seal_proposal(wave5: Any, legacy: Any, values: Mapping[str, Any]) -> dict[str, Any]:
    """Encrypt sensitive proposal fields; return a storable, masked envelope."""
    clean = {
        f: str(values.get(f)).strip()
        for f in PROPOSABLE_FIELDS
        if values.get(f) not in (None, "")
    }
    if not clean.get("iban") and not clean.get("account_number"):
        raise legacy.HTTPException(
            status_code=422, detail={"error": "account_identifier_required"}
        )
    cipher = wave5._encrypt_bank_payload(legacy, dict(clean))
    ident = clean.get("iban") or clean.get("account_number")
    envelope = {
        SEALED_KEY: cipher,
        "display": display_projection(clean),
        "fingerprint": fingerprint(ident),
        "fields_proposed": sorted(clean.keys()),
        "contract_version": CONTRACT_VERSION,
        "sealed": True,
        "plaintext_forbidden": True,
    }
    return envelope


def is_sealed(proposed: Mapping[str, Any] | None) -> bool:
    return bool((proposed or {}).get("sealed")) and SEALED_KEY in (proposed or {})


def unseal_proposal(wave5: Any, legacy: Any, proposed: Mapping[str, Any] | None) -> dict[str, Any]:
    """Decrypt a sealed proposal for the apply step only."""
    data = dict(proposed or {})
    if not is_sealed(data):
        # Legacy pre-seal rows carried plaintext; accept for backward compatibility.
        return {f: data[f] for f in PROPOSABLE_FIELDS if data.get(f) not in (None, "")}
    return wave5._decrypt_bank_blob(legacy, dict(data.get(SEALED_KEY) or {}))


def safe_request_projection(
    proposed: Mapping[str, Any] | None, *, can_unmask: bool = False
) -> dict[str, Any]:
    """What HR/employee surfaces may see. Sealed ciphertext is never returned."""
    data = dict(proposed or {})
    display = dict(data.get("display") or {})
    if not display:
        display = display_projection(data)
    out: dict[str, Any] = {
        "display": display,
        "fingerprint": data.get("fingerprint"),
        "fields_proposed": data.get("fields_proposed") or sorted(display.keys()),
        "sealed": is_sealed(data),
        "masked": True,
    }
    # Backward compatibility: pre-sealing clients read masked field values at the
    # top level with the `<field>__masked` marker. Keep that shape so older HR
    # surfaces don't render blanks, while new surfaces read `display`.
    for field, value in display.items():
        if field in out or field.endswith("_masked"):
            continue
        out[field] = value
        if field in SENSITIVE_PROPOSABLE and isinstance(value, str) and "*" in value:
            out[f"{field}__masked"] = True
    if can_unmask:
        out["reveal_available"] = True
    return out


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def ensure_bank_ess_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_bank_verified (
          company_code text NOT NULL,
          employee_key text NOT NULL,
          request_id uuid NOT NULL,
          fingerprint text,
          display jsonb NOT NULL DEFAULT '{}'::jsonb,
          verified_by_user_id text,
          verified_by_stage text,
          verified_at timestamptz NOT NULL DEFAULT now(),
          validation jsonb NOT NULL DEFAULT '{}'::jsonb,
          PRIMARY KEY (company_code, employee_key, request_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_bank_effective (
          effective_id bigserial PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          request_id uuid,
          fingerprint text,
          display jsonb NOT NULL DEFAULT '{}'::jsonb,
          bank_profile_version bigint,
          effective_from date NOT NULL,
          superseded_at timestamptz,
          payroll_period_status text,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS employee_bank_effective_current_idx
        ON employee_bank_effective (company_code, employee_key)
        WHERE superseded_at IS NULL
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_bank_evidence (
          evidence_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          request_id uuid,
          storage_ref text NOT NULL,
          filename text,
          mime_type text,
          byte_size bigint,
          content_sha256 text,
          uploaded_by_employee_key text,
          uploaded_at timestamptz NOT NULL DEFAULT now(),
          deleted_at timestamptz,
          deletion_reason text,
          retention_until date
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS employee_bank_evidence_req_idx
        ON employee_bank_evidence (company_code, employee_key, request_id)
        """
    )
    cur.execute(
        "ALTER TABLE employee_bank_evidence ADD COLUMN IF NOT EXISTS purged_at timestamptz"
    )
    # Soft-revoke for verified rows: audit stays, current projection ignores them.
    cur.execute(
        "ALTER TABLE employee_bank_verified ADD COLUMN IF NOT EXISTS revoked_at timestamptz"
    )
    cur.execute(
        "ALTER TABLE employee_bank_verified ADD COLUMN IF NOT EXISTS revocation_reason text"
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS employee_bank_evidence_purge_idx
        ON employee_bank_evidence (retention_until)
        WHERE purged_at IS NULL
        """
    )
    # P1: non-authoritative OCR proposal next to evidence (never verified/effective).
    cur.execute(
        "ALTER TABLE employee_bank_evidence ADD COLUMN IF NOT EXISTS extraction_json jsonb NOT NULL DEFAULT '{}'::jsonb"
    )
    cur.execute(
        "ALTER TABLE employee_bank_evidence ADD COLUMN IF NOT EXISTS extraction_status text"
    )
    cur.execute(
        "ALTER TABLE employee_bank_evidence ADD COLUMN IF NOT EXISTS extraction_confidence double precision"
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_bank_notifications (
          notification_id bigserial PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          dedup_key text NOT NULL,
          audience text NOT NULL,
          event text NOT NULL,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS employee_bank_notifications_dedup_idx
        ON employee_bank_notifications (company_code, dedup_key)
        """
    )
    _ensure_employee_cascade(cur)


# Bank authority rows must never outlive the employee they describe: an orphan
# row is retained sensitive data nobody can see or reach. Cascade guarantees that
# regardless of which code path removes the employee. Evidence blobs are swept
# separately (purge_bank_evidence_bytes with include_orphans).
_CASCADE_TABLES = (
    "employee_bank_verified",
    "employee_bank_effective",
    "employee_bank_evidence",
    "employee_bank_notifications",
)


def _ensure_employee_cascade(cur: Any) -> None:
    for table in _CASCADE_TABLES:
        constraint = f"{table}_employee_fk"
        try:
            cur.execute("SAVEPOINT bank_fk_step")
            cur.execute(
                """
                SELECT 1 FROM pg_constraint
                WHERE conname=%s AND conrelid=%s::regclass
                """,
                (constraint, table),
            )
            if cur.fetchone():
                cur.execute("RELEASE SAVEPOINT bank_fk_step")
                continue
            cur.execute(f"DELETE FROM {table} WHERE employee_key NOT IN (SELECT employee_key FROM employees)")
            cur.execute(
                f"""
                ALTER TABLE {table}
                ADD CONSTRAINT {constraint}
                FOREIGN KEY (employee_key) REFERENCES employees (employee_key)
                ON DELETE CASCADE
                """
            )
            cur.execute("RELEASE SAVEPOINT bank_fk_step")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT bank_fk_step")


# ---------------------------------------------------------------------------
# Duplicate active request prevention
# ---------------------------------------------------------------------------
def active_request(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any] | None:
    states = ", ".join("'" + s + "'" for s in ACTIVE_REQUEST_STATES)
    cur.execute(
        f"""
        SELECT * FROM employee_ess_requests
        WHERE company_code=%s AND employee_key=%s
          AND request_type='bank_detail_change'
          AND state IN ({states})
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (str(company_code).upper(), employee_key),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def assert_no_duplicate_active(
    legacy: Any, cur: Any, *, company_code: str, employee_key: str
) -> None:
    """One active bank change request per employee. Resubmission replaces it."""
    existing = active_request(cur, company_code=company_code, employee_key=employee_key)
    if existing:
        raise legacy.HTTPException(
            status_code=409,
            detail={
                "error": "bank_request_already_active",
                "request_id": str(existing.get("request_id")),
                "state": existing.get("state"),
                "message": "A bank change request is already in progress. Withdraw or complete it first.",
                "message_en": "A bank change request is already in progress. Withdraw or wait for HR, then try again.",
                "message_ar": "يوجد طلب تغيير بنكي قيد المعالجة. اسحب الطلب أو انتظر الموارد البشرية ثم حاول مرة أخرى.",
            },
        )


# Correction/resubmit may reuse the open request instead of opening a second slot.
# needs_review is a recoverable overlay conflict — employee must be able to replace.
REPLACEABLE_ACTIVE_STATES = frozenset({"draft", "needs_information", "needs_review"})


def problem_fields(problems: list[str] | None) -> list[str]:
    """Map registry problem codes to employee form fields."""
    fields: list[str] = []
    for problem in problems or []:
        code = str(problem)
        if code.startswith("iban_") or code == "account_identifier_required":
            if "iban" not in fields:
                fields.append("iban")
        elif code.startswith("account_number_"):
            if "account_number" not in fields:
                fields.append("account_number")
        elif code.startswith("swift_"):
            if "swift" not in fields:
                fields.append("swift")
    return fields


# ---------------------------------------------------------------------------
# Payroll safety
# ---------------------------------------------------------------------------
def payroll_lock_state(cur: Any, *, company_code: str) -> dict[str, Any]:
    """Is payroll processing underway? Determines the effective date, not a block."""
    company = str(company_code).upper()
    try:
        cur.execute(
            """
            SELECT status, period_start, period_end
            FROM payroll_periods
            WHERE company_code=%s AND status IN ('locked','open')
            ORDER BY period_start DESC
            LIMIT 1
            """,
            (company,),
        )
        row = dict(cur.fetchone() or {})
    except Exception:
        return {"locked": False, "reason": "payroll_periods_unavailable"}
    status = str(row.get("status") or "")
    if status == "locked":
        return {
            "locked": True,
            "reason": "payroll_period_locked",
            "period_end": row.get("period_end"),
            "period_status": status,
        }
    return {"locked": False, "period_status": status or None, "period_end": row.get("period_end")}


def resolve_effective_from(cur: Any, *, company_code: str) -> tuple[date, dict[str, Any]]:
    """Never retroactively change a bank account inside a locked payroll run."""
    lock = payroll_lock_state(cur, company_code=company_code)
    today = datetime.now(timezone.utc).date()
    if not lock.get("locked"):
        return today, lock
    period_end = lock.get("period_end")
    try:
        if period_end is not None:
            end = period_end if hasattr(period_end, "toordinal") else date.fromisoformat(str(period_end)[:10])
            from datetime import timedelta

            return end + timedelta(days=1), lock
    except Exception:
        pass
    return today, lock


# ---------------------------------------------------------------------------
# Verified + payroll-effective transitions
# ---------------------------------------------------------------------------
def revoke_verified(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    reason: str,
    request_ids: list[str] | None = None,
    fingerprint: str | None = None,
) -> list[dict[str, Any]]:
    """Soft-revoke verified rows so they stop projecting as current bank truth.

    Rows stay for audit. Current reads filter `revoked_at IS NULL`.
    """
    ensure_bank_ess_schema(cur)
    company = str(company_code).upper()
    key = str(employee_key or "").strip()
    why = str(reason or "verified_revoked").strip() or "verified_revoked"
    sql = """
        UPDATE employee_bank_verified
        SET revoked_at=now(), revocation_reason=%s
        WHERE company_code=%s AND employee_key=%s AND revoked_at IS NULL
    """
    params: list[Any] = [why, company, key]
    if request_ids:
        sql += " AND request_id::text = ANY(%s)"
        params.append([str(r) for r in request_ids])
    if fingerprint:
        sql += " AND fingerprint=%s"
        params.append(str(fingerprint))
    sql += " RETURNING request_id::text, fingerprint, verified_at, revocation_reason"
    cur.execute(sql, tuple(params))
    return [dict(r) for r in (cur.fetchall() or [])]


def restore_superseded_verified(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
) -> dict[str, Any] | None:
    """Re-project the latest HR-superseded verified row after a later request dies.

    Soft-revoke history stays intact; only the current projection is restored.
    """
    ensure_bank_ess_schema(cur)
    company = str(company_code).upper()
    key = str(employee_key or "").strip()
    cur.execute(
        """
        WITH latest AS (
          SELECT request_id
          FROM employee_bank_verified
          WHERE company_code=%s AND employee_key=%s
            AND revocation_reason='superseded_by_hr_approval'
          ORDER BY verified_at DESC NULLS LAST
          LIMIT 1
        )
        UPDATE employee_bank_verified v
        SET revoked_at=NULL, revocation_reason=NULL
        FROM latest
        WHERE v.request_id = latest.request_id
          AND v.company_code=%s AND v.employee_key=%s
        RETURNING v.request_id::text, v.fingerprint, v.verified_at, v.verified_by_stage
        """,
        (company, key, company, key),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def record_verified(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    request_id: str,
    proposed: Mapping[str, Any],
    verified_by_user_id: str | None,
    verified_by_stage: str | None,
    validation: Mapping[str, Any] | None = None,
    supersede_previous: bool = False,
) -> None:
    """Idempotent: the same request verifying twice does not duplicate history.

    When ``supersede_previous`` is true (HR approval of a new proposal), soft-revoke
    other current verified rows so history is preserved but only one current stamp
    projects. Does not touch payroll-effective rows.
    """
    ensure_bank_ess_schema(cur)
    company = str(company_code).upper()
    key = str(employee_key or "").strip()
    if supersede_previous:
        cur.execute(
            """
            UPDATE employee_bank_verified
            SET revoked_at=now(), revocation_reason=%s
            WHERE company_code=%s AND employee_key=%s AND revoked_at IS NULL
              AND request_id::text <> %s
            """,
            ("superseded_by_hr_approval", company, key, str(request_id)),
        )
    safe = safe_request_projection(proposed)
    cur.execute(
        """
        INSERT INTO employee_bank_verified (
          company_code, employee_key, request_id, fingerprint, display,
          verified_by_user_id, verified_by_stage, validation
        ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb)
        ON CONFLICT (company_code, employee_key, request_id) DO UPDATE SET
          fingerprint=EXCLUDED.fingerprint,
          display=EXCLUDED.display,
          verified_by_user_id=COALESCE(EXCLUDED.verified_by_user_id, employee_bank_verified.verified_by_user_id),
          verified_by_stage=EXCLUDED.verified_by_stage,
          validation=EXCLUDED.validation,
          verified_at=now(),
          revoked_at=NULL,
          revocation_reason=NULL
        """,
        (
            company,
            key,
            request_id,
            safe.get("fingerprint"),
            json.dumps(safe.get("display") or {}),
            verified_by_user_id,
            verified_by_stage,
            json.dumps(dict(validation or {})),
        ),
    )


def record_effective(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    request_id: str,
    proposed: Mapping[str, Any],
    bank_profile_version: int | None,
) -> dict[str, Any]:
    """Atomic payroll-effective transition with effective dating.

    Idempotent on request_id: replaying apply does not create a second row.
    """
    ensure_bank_ess_schema(cur)
    company = str(company_code).upper()
    cur.execute(
        """
        SELECT effective_id, effective_from FROM employee_bank_effective
        WHERE company_code=%s AND employee_key=%s AND request_id=%s
        LIMIT 1
        """,
        (company, employee_key, request_id),
    )
    already = cur.fetchone()
    if already:
        row = dict(already)
        return {
            "idempotent": True,
            "effective_id": row.get("effective_id"),
            "effective_from": row.get("effective_from"),
        }

    effective_from, lock = resolve_effective_from(cur, company_code=company)
    safe = safe_request_projection(proposed)
    cur.execute(
        """
        UPDATE employee_bank_effective
        SET superseded_at=now()
        WHERE company_code=%s AND employee_key=%s AND superseded_at IS NULL
        """,
        (company, employee_key),
    )
    cur.execute(
        """
        INSERT INTO employee_bank_effective (
          company_code, employee_key, request_id, fingerprint, display,
          bank_profile_version, effective_from, payroll_period_status
        ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
        RETURNING effective_id, effective_from
        """,
        (
            company,
            employee_key,
            request_id,
            safe.get("fingerprint"),
            json.dumps(safe.get("display") or {}),
            int(bank_profile_version) if bank_profile_version is not None else None,
            effective_from,
            str(lock.get("period_status") or "") or None,
        ),
    )
    row = dict(cur.fetchone() or {})
    return {
        "idempotent": False,
        "effective_id": row.get("effective_id"),
        "effective_from": row.get("effective_from"),
        "deferred_for_payroll_lock": bool(lock.get("locked")),
        "payroll_lock": lock,
    }


def current_effective(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any] | None:
    """The single value payroll may read. Masked display only."""
    try:
        cur.execute(
            """
            SELECT request_id, fingerprint, display, bank_profile_version,
                   effective_from, created_at
            FROM employee_bank_effective
            WHERE company_code=%s AND employee_key=%s AND superseded_at IS NULL
            LIMIT 1
            """,
            (str(company_code).upper(), employee_key),
        )
        row = cur.fetchone()
    except Exception:
        return None
    return dict(row) if row else None


def effective_history(
    cur: Any, *, company_code: str, employee_key: str, limit: int = 25
) -> list[dict[str, Any]]:
    try:
        cur.execute(
            """
            SELECT request_id, fingerprint, display, bank_profile_version,
                   effective_from, superseded_at, created_at
            FROM employee_bank_effective
            WHERE company_code=%s AND employee_key=%s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (str(company_code).upper(), employee_key, int(limit)),
        )
        return [dict(r) for r in (cur.fetchall() or [])]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Evidence — private storage refs only
# ---------------------------------------------------------------------------
def register_evidence(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    request_id: str | None,
    filename: str | None,
    mime_type: str | None,
    byte_size: int | None,
    content_sha256: str | None,
    uploaded_by_employee_key: str | None,
    retention_days: int = 2555,
) -> dict[str, Any]:
    ensure_bank_ess_schema(cur)
    evidence_id = str(uuid.uuid4())
    # Private, unguessable ref. Never a public URL.
    storage_ref = f"ess-bank/{str(company_code).upper()}/{employee_key}/{evidence_id}"
    cur.execute(
        """
        INSERT INTO employee_bank_evidence (
          evidence_id, company_code, employee_key, request_id, storage_ref,
          filename, mime_type, byte_size, content_sha256, uploaded_by_employee_key,
          retention_until
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, (now() + (%s || ' days')::interval)::date)
        RETURNING evidence_id, storage_ref, uploaded_at, retention_until
        """,
        (
            evidence_id,
            str(company_code).upper(),
            employee_key,
            request_id,
            storage_ref,
            filename,
            mime_type,
            int(byte_size) if byte_size is not None else None,
            content_sha256,
            uploaded_by_employee_key,
            int(retention_days),
        ),
    )
    return dict(cur.fetchone() or {})


def bank_ocr_enabled(*, company_code: str | None = None) -> bool:
    """Document-first OCR for Bank ESS P1. Fail-open to manual when off."""
    raw = (os.environ.get("WATHEFNI_BANK_ESS_OCR_V1") or "on").strip().lower()
    if raw in {"off", "0", "false", "no", "kill", "disabled"}:
        return False
    companies = {
        c.strip().upper()
        for c in (os.environ.get("WATHEFNI_BANK_ESS_OCR_V1_COMPANIES") or "WATHEFNI").split(",")
        if c.strip()
    }
    if company_code and str(company_code).upper() not in companies:
        return False
    return True


BANK_EXTRACT_FIELDS = (
    "iban",
    "account_number",
    "bank_name",
    "account_holder",
    "branch",
    "swift",
)


def _field_value(cell: Any) -> Any:
    if isinstance(cell, dict):
        return cell.get("value")
    return cell


def _field_confidence(cell: Any) -> float | None:
    if isinstance(cell, dict) and cell.get("confidence") is not None:
        try:
            return float(cell.get("confidence"))
        except Exception:
            return None
    return None


def sanitize_bank_extraction(
    raw: Mapping[str, Any] | None, *, mask_sensitive: bool = False
) -> dict[str, Any]:
    """Employee/HR-safe extraction projection. Never elevates authority.

    When ``mask_sensitive`` is True (default for list/review surfaces without
    unmask permission), IBAN and account number are masked like other bank
    display projections. Upload confirm/correct may pass mask_sensitive=False.
    """
    data = dict(raw or {})
    fields_in = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    # Prefer already-sanitized proposed when re-projecting stored JSON.
    existing_proposed = data.get("proposed") if isinstance(data.get("proposed"), dict) else None
    proposed: dict[str, Any] = {}
    field_confidence: dict[str, float] = {}
    source_fields = fields_in or (
        {k: {"value": v} for k, v in (existing_proposed or {}).items()} if existing_proposed else {}
    )
    for key in BANK_EXTRACT_FIELDS:
        cell = source_fields.get(key)
        value = _field_value(cell) if cell is not None else (existing_proposed or {}).get(key)
        if value in (None, ""):
            continue
        text = str(value).strip()
        if not text:
            continue
        if key == "iban":
            text = "".join(ch for ch in text.upper() if ch.isalnum())
        if mask_sensitive and key in SENSITIVE_PROPOSABLE:
            text = mask_account(text) or text
        proposed[key] = text
        conf = _field_confidence(cell) if isinstance(cell, dict) else None
        if conf is not None:
            field_confidence[key] = conf
    # Preserve field_confidence from prior sanitize when re-masking.
    if not field_confidence and isinstance(data.get("field_confidence"), dict):
        field_confidence = {
            str(k): float(v)
            for k, v in data["field_confidence"].items()
            if v is not None
        }
    status = str(data.get("extraction_status") or data.get("status") or "unknown")
    try:
        confidence = float(data.get("confidence") if data.get("confidence") is not None else 0.0)
    except Exception:
        confidence = 0.0
    warnings = [str(w) for w in (data.get("warnings") or []) if str(w).strip()]
    # Document-type / IBAN hints from annotation (never authoritative).
    doc_type_raw = _field_value(source_fields.get("document_type")) or data.get("document_type")
    doc_type = str(doc_type_raw or "bank_certificate").strip().lower() or "bank_certificate"
    bank_doc_types = {"bank_certificate", "iban_letter", "unknown"}
    wrong_document_type = bool(doc_type) and doc_type not in bank_doc_types
    if wrong_document_type and "wrong_document_type" not in warnings:
        warnings.append("wrong_document_type")
    missing_iban = "iban" not in proposed
    if not proposed and status in {"extracted", "partial", "low_confidence"}:
        status = "failed"
    needs_manual = status in {"failed", "needs_review", "disabled", "error", "unknown"} or not proposed
    uncertain = status in {"partial", "low_confidence"} or (0 < confidence < 0.55)
    return {
        "status": status,
        "confidence": confidence,
        "field_confidence": field_confidence,
        "proposed": proposed,
        "warnings": warnings,
        "unreadable_reason": data.get("unreadable_reason") or data.get("extraction_error"),
        "needs_manual_fallback": needs_manual,
        "uncertain": uncertain,
        "missing_iban": bool(missing_iban),
        "wrong_document_type": wrong_document_type,
        "authoritative": False,
        "provider": data.get("provider"),
        "model": data.get("model"),
        "document_type": doc_type,
        "masked": bool(mask_sensitive),
    }


def store_evidence_extraction(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    evidence_id: str,
    extraction: Mapping[str, Any],
) -> dict[str, Any]:
    ensure_bank_ess_schema(cur)
    safe = sanitize_bank_extraction(extraction)
    payload = {
        **dict(extraction or {}),
        "sanitized": safe,
        "authoritative": False,
        "bank_ess_layer": "proposed_only",
        "contract_version": CONTRACT_VERSION,
    }
    cur.execute(
        """
        UPDATE employee_bank_evidence
        SET extraction_json=%s::jsonb,
            extraction_status=%s,
            extraction_confidence=%s
        WHERE company_code=%s AND employee_key=%s AND evidence_id=%s
        RETURNING evidence_id::text, extraction_status, extraction_confidence, extraction_json
        """,
        (
            json.dumps(payload, default=str),
            safe.get("status"),
            safe.get("confidence"),
            str(company_code).upper(),
            employee_key,
            evidence_id,
        ),
    )
    row = cur.fetchone()
    return dict(row) if row else {"evidence_id": evidence_id, **safe}


def extract_bank_certificate_from_path(
    *,
    path: str,
    company_code: str,
    employee_key: str,
    mime_type: str | None = None,
) -> dict[str, Any]:
    """Run shared Kuwait/GCC Mistral path for a bank certificate. Non-authoritative."""
    if not bank_ocr_enabled(company_code=company_code):
        return {
            "ok": False,
            "extraction_status": "disabled",
            "extraction_error": "bank_ocr_disabled",
            "authoritative": False,
            "fields": {},
            "confidence": 0.0,
            "needs_manual_fallback": True,
        }
    try:
        from kuwait_gcc_document_intelligence.intake import shared_channel_extraction
    except Exception as exc:
        return {
            "ok": False,
            "extraction_status": "error",
            "extraction_error": f"intake_unavailable:{exc}",
            "authoritative": False,
            "fields": {},
            "confidence": 0.0,
            "needs_manual_fallback": True,
        }
    result = shared_channel_extraction(
        document_type="bank_certificate",
        media={"path": path, "mime_type": mime_type or "application/octet-stream"},
        company_code=company_code,
        subject_key=employee_key,
        channel="ess_bank",
        expected_item="bank_certificate",
        mode="extract",
        country_code="KW",
    )
    out = dict(result or {})
    out.setdefault("authoritative", False)
    out["confidence"] = float(out.get("confidence") or 0.0)
    warnings: list[str] = []
    fields = out.get("fields") if isinstance(out.get("fields"), dict) else {}
    warn_cell = fields.get("warnings") if isinstance(fields, dict) else None
    if isinstance(warn_cell, dict) and isinstance(warn_cell.get("value"), list):
        warnings.extend(str(w) for w in warn_cell["value"] if str(w).strip())
    unread = fields.get("unreadable_reason") if isinstance(fields, dict) else None
    if isinstance(unread, dict) and unread.get("value"):
        out["unreadable_reason"] = unread.get("value")
    out["warnings"] = warnings
    if not out.get("extraction_status"):
        out["extraction_status"] = "needs_review" if not out.get("ok") else "extracted"
    return out


def list_evidence(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    request_id: str | None = None,
    can_unmask: bool = False,
) -> list[dict[str, Any]]:
    try:
        if request_id:
            cur.execute(
                """
                SELECT evidence_id, filename, mime_type, byte_size, uploaded_at,
                       retention_until, deleted_at, extraction_status, extraction_confidence,
                       extraction_json
                FROM employee_bank_evidence
                WHERE company_code=%s AND employee_key=%s AND request_id=%s
                  AND deleted_at IS NULL
                ORDER BY uploaded_at DESC
                """,
                (str(company_code).upper(), employee_key, request_id),
            )
        else:
            cur.execute(
                """
                SELECT evidence_id, filename, mime_type, byte_size, uploaded_at,
                       retention_until, deleted_at, extraction_status, extraction_confidence,
                       extraction_json
                FROM employee_bank_evidence
                WHERE company_code=%s AND employee_key=%s AND deleted_at IS NULL
                ORDER BY uploaded_at DESC
                """,
                (str(company_code).upper(), employee_key),
            )
        rows = []
        for r in cur.fetchall() or []:
            row = dict(r)
            raw = row.pop("extraction_json", None) or {}
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = {}
            if not isinstance(raw, dict):
                raw = {}
            # Re-project every time so HR/default views never inherit plaintext
            # IBAN from a previously stored sanitized blob.
            source = raw
            if not isinstance(raw.get("fields"), dict) and isinstance(raw.get("sanitized"), dict):
                source = dict(raw.get("sanitized") or {})
            # Extraction proposals are masked by default on review surfaces.
            # `can_unmask` only signals that an audited reveal is available —
            # it must not dump plaintext IBAN into the bank review payload.
            _ = can_unmask
            row["extraction"] = sanitize_bank_extraction(source, mask_sensitive=True)
            rows.append(row)
        return rows
    except Exception:
        return []


def delete_evidence(
    cur: Any, *, company_code: str, employee_key: str, evidence_id: str, reason: str
) -> bool:
    """Soft delete: retention metadata is kept, payload access is revoked."""
    cur.execute(
        """
        UPDATE employee_bank_evidence
        SET deleted_at=now(), deletion_reason=%s
        WHERE company_code=%s AND employee_key=%s AND evidence_id=%s AND deleted_at IS NULL
        RETURNING evidence_id
        """,
        (reason, str(company_code).upper(), employee_key, evidence_id),
    )
    return bool(cur.fetchone())


# Retention: evidence bytes live on private storage until `retention_until`
# (see EVIDENCE_RETENTION_DAYS). Soft delete revokes access immediately; the
# purge below is what actually destroys the bytes, so a soft-deleted or expired
# row can never leave a readable blob behind.
def purgeable_evidence(
    cur: Any, *, company_code: str | None = None, employee_keys: list[str] | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Rows whose bytes should be destroyed: expired, or soft-deleted."""
    where = ["purged_at IS NULL"]
    params: list[Any] = []
    if employee_keys:
        where.append("employee_key = ANY(%s)")
        params.append(list(employee_keys))
    else:
        where.append("(retention_until <= current_date OR deleted_at IS NOT NULL)")
    if company_code:
        where.append("company_code=%s")
        params.append(str(company_code).upper())
    params.append(int(limit))
    cur.execute(
        f"""
        SELECT evidence_id, company_code, employee_key, storage_ref
        FROM employee_bank_evidence
        WHERE {' AND '.join(where)}
        ORDER BY uploaded_at
        LIMIT %s
        """,
        tuple(params),
    )
    return [dict(r) for r in (cur.fetchall() or [])]


def mark_evidence_purged(cur: Any, evidence_ids: list[str]) -> int:
    if not evidence_ids:
        return 0
    cur.execute(
        """
        UPDATE employee_bank_evidence
        SET purged_at=now(),
            deleted_at=COALESCE(deleted_at, now()),
            deletion_reason=COALESCE(deletion_reason, 'retention_purge')
        WHERE evidence_id = ANY(%s::uuid[]) AND purged_at IS NULL
        """,
        (list(evidence_ids),),
    )
    return int(cur.rowcount or 0)


# ---------------------------------------------------------------------------
# Notifications — channel-agnostic and deduplicated
# ---------------------------------------------------------------------------
def enqueue_notification(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    audience: str,
    event: str,
    dedup_key: str,
    payload: Mapping[str, Any] | None = None,
) -> bool:
    """Returns True when newly enqueued, False when deduplicated.

    Payload must already be masked — this row is readable by notification workers.
    """
    ensure_bank_ess_schema(cur)
    safe_payload = {
        k: v
        for k, v in dict(payload or {}).items()
        if k not in SENSITIVE_PROPOSABLE and k != SEALED_KEY
    }
    cur.execute(
        """
        INSERT INTO employee_bank_notifications (
          company_code, employee_key, dedup_key, audience, event, payload
        ) VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (company_code, dedup_key) DO NOTHING
        RETURNING notification_id
        """,
        (
            str(company_code).upper(),
            employee_key,
            dedup_key,
            audience,
            event,
            json.dumps(safe_payload, default=str),
        ),
    )
    return bool(cur.fetchone())


# ---------------------------------------------------------------------------
# Employee-facing status view — answers the five UX questions
# ---------------------------------------------------------------------------
def _submission_state(request: Mapping[str, Any] | None) -> str:
    if not request:
        return SUBMISSION_NONE
    state = str(request.get("state") or "").lower()
    if state == "draft":
        return SUBMISSION_DRAFT
    if state in {"needs_information", "needs_review", "failed"}:
        return SUBMISSION_NEEDS_CORRECTION
    if state in {"submitted", "pending_manager", "pending_hr"}:
        return SUBMISSION_PENDING_HR
    if state == "pending_payroll":
        return SUBMISSION_PENDING_PAYROLL
    if state == "approved":
        return SUBMISSION_APPROVED
    if state == "applied":
        return SUBMISSION_APPLIED
    if state == "rejected":
        return SUBMISSION_REJECTED
    if state == "withdrawn":
        return SUBMISSION_WITHDRAWN
    return SUBMISSION_PENDING_HR


def _latest_decision_reason(request: Mapping[str, Any] | None) -> str | None:
    comments = (request or {}).get("comments") or []
    if isinstance(comments, str):
        try:
            comments = json.loads(comments)
        except Exception:
            comments = []
    for entry in reversed(list(comments or [])):
        if isinstance(entry, dict) and entry.get("text"):
            return str(entry.get("text"))
    return None


def next_step(
    submission: str,
    *,
    has_verified: bool,
    locale: str = "en",
    workflow_state: str | None = None,
) -> dict[str, Any]:
    is_ar = str(locale).lower().startswith("ar")
    exact = str(workflow_state or "").lower()
    # Prefer exact workflow state for truthful employee/HR copy.
    if exact == "pending_hr" or (not exact and submission == SUBMISSION_PENDING_HR):
        en = "HR is reviewing your submission. Nothing else is needed from you."
        ar = "الموارد البشرية تراجع طلبك. لا يلزم شيء آخر منك."
        return {
            "owner": "hr",
            "message": ar if is_ar else en,
            "message_en": en,
            "message_ar": ar,
        }
    if exact == "pending_payroll" or submission == SUBMISSION_PENDING_PAYROLL:
        en = "HR verified your details. Payroll is reviewing them before they become effective."
        ar = "تحققت الموارد البشرية من بياناتك. الرواتب تراجعها قبل أن تصبح سارية."
        return {
            "owner": "payroll",
            "message": ar if is_ar else en,
            "message_en": en,
            "message_ar": ar,
        }
    if exact == "approved" or submission == SUBMISSION_APPROVED:
        en = "Payroll approved the change. It is not payroll-effective until payroll applies it."
        ar = "وافقت الرواتب على التغيير. لن يصبح ساريًا للرواتب حتى تطبقه الرواتب."
        return {
            "owner": "payroll",
            "message": ar if is_ar else en,
            "message_en": en,
            "message_ar": ar,
        }
    if exact == "applied" or submission == SUBMISSION_APPLIED:
        en = "Your approved bank details are now used for payroll."
        ar = "بياناتك البنكية المعتمدة مستخدمة الآن للرواتب."
        return {
            "owner": "none",
            "message": ar if is_ar else en,
            "message_en": en,
            "message_ar": ar,
        }
    table = {
        SUBMISSION_NONE: (
            "employee",
            "Add your bank details so salary can be paid to you."
            if not has_verified
            else "Your bank details are verified. Submit a change if anything is different.",
            "أضف بياناتك البنكية ليتم دفع الراتب إليك."
            if not has_verified
            else "بياناتك البنكية موثّقة. أرسل تغييرًا إذا اختلف شيء.",
        ),
        SUBMISSION_DRAFT: (
            "employee",
            "Your draft is saved but not submitted. Submit it for HR review.",
            "مسودتك محفوظة ولم تُرسل بعد. أرسلها لمراجعة الموارد البشرية.",
        ),
        SUBMISSION_PENDING_REVIEW: (
            "hr",
            "HR is reviewing your submission. Nothing else is needed from you.",
            "الموارد البشرية تراجع طلبك. لا يلزم شيء آخر منك.",
        ),
        SUBMISSION_REJECTED: (
            "employee",
            "Your submission was rejected. Review the reason, correct it and resubmit.",
            "تم رفض طلبك. راجع السبب، صححه وأعد الإرسال.",
        ),
        SUBMISSION_NEEDS_CORRECTION: (
            "employee",
            "HR asked for a correction. Update the details and resubmit.",
            "طلبت الموارد البشرية تصحيحًا. حدّث البيانات وأعد الإرسال.",
        ),
        SUBMISSION_WITHDRAWN: (
            "employee",
            "You withdrew your last request. Submit a new change when ready.",
            "لقد سحبت طلبك السابق. أرسل تغييرًا جديدًا عند الحاجة.",
        ),
    }
    owner, en, ar = table.get(submission, table[SUBMISSION_PENDING_REVIEW])
    return {"owner": owner, "message": ar if is_ar else en, "message_en": en, "message_ar": ar}


def employee_bank_status(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    can_unmask: bool = False,
    locale: str = "en",
) -> dict[str, Any]:
    """Complete employee-facing bank state. Verified and submitted stay separate."""
    ensure_bank_ess_schema(cur)
    company = str(company_code).upper()

    effective = current_effective(cur, company_code=company, employee_key=employee_key)
    cur.execute(
        """
        SELECT request_id, fingerprint, display, verified_by_stage, verified_at
        FROM employee_bank_verified
        WHERE company_code=%s AND employee_key=%s AND revoked_at IS NULL
        ORDER BY verified_at DESC
        LIMIT 1
        """,
        (company, employee_key),
    )
    verified = dict(cur.fetchone() or {}) or None

    request = active_request(cur, company_code=company, employee_key=employee_key)
    has_verified = bool(verified)
    has_effective = bool(effective)
    has_bank_of_record = has_verified or has_effective
    if not request:
        # Surface the latest terminal attempt so first-time reject/withdraw is not a
        # dead end that looks like "never submitted". With a bank of record, only
        # show terminal attempts newer than that record.
        states = ", ".join("'" + s + "'" for s in ("rejected", "withdrawn", "failed"))
        params: list[Any] = [company, employee_key]
        cutoff_sql = ""
        if has_bank_of_record:
            cutoff = (verified or {}).get("verified_at") or (effective or {}).get("created_at")
            if cutoff is not None:
                cutoff_sql = " AND coalesce(updated_at, created_at) > %s"
                params.append(cutoff)
        cur.execute(
            f"""
            SELECT * FROM employee_ess_requests
            WHERE company_code=%s AND employee_key=%s
              AND request_type='bank_detail_change' AND state IN ({states})
              {cutoff_sql}
            ORDER BY updated_at DESC NULLS LAST, created_at DESC
            LIMIT 1
            """,
            tuple(params),
        )
        row = cur.fetchone()
        request = dict(row) if row else None

    submission = _submission_state(request)
    workflow_state = str((request or {}).get("state") or "").lower()

    withdrawable_submissions = {
        SUBMISSION_DRAFT,
        SUBMISSION_PENDING_HR,
        SUBMISSION_PENDING_PAYROLL,
        SUBMISSION_PENDING_REVIEW,
        SUBMISSION_NEEDS_CORRECTION,
    }
    resubmittable_submissions = {
        SUBMISSION_REJECTED,
        SUBMISSION_NEEDS_CORRECTION,
        SUBMISSION_WITHDRAWN,
    }
    under_review_submissions = {
        SUBMISSION_DRAFT,
        SUBMISSION_PENDING_HR,
        SUBMISSION_PENDING_PAYROLL,
        SUBMISSION_PENDING_REVIEW,
        SUBMISSION_NEEDS_CORRECTION,
        SUBMISSION_APPROVED,
    }

    submitted_block = None
    if request:
        submitted_block = {
            "request_id": str(request.get("request_id")),
            "state": request.get("state"),
            "submission_state": submission,
            "concurrency_version": request.get("concurrency_version"),
            "submitted_at": request.get("created_at"),
            "updated_at": request.get("updated_at"),
            "proposed": safe_request_projection(
                request.get("proposed_values"), can_unmask=can_unmask
            ),
            "rejection_reason": _latest_decision_reason(request)
            if submission in {SUBMISSION_REJECTED, SUBMISSION_NEEDS_CORRECTION}
            else None,
            "can_withdraw": submission in withdrawable_submissions
            and workflow_state
            in {
                "draft",
                "submitted",
                "needs_information",
                "needs_review",
                "pending_manager",
                "pending_hr",
                "pending_payroll",
            },
            "can_resubmit": submission in resubmittable_submissions
            or workflow_state in {"needs_review", "failed"},
            "evidence": list_evidence(
                cur,
                company_code=company,
                employee_key=employee_key,
                request_id=str(request.get("request_id")),
                can_unmask=can_unmask,
            ),
        }

    return {
        "contract_version": CONTRACT_VERSION,
        "employee_key": employee_key,
        "has_verified_bank": has_verified,
        "has_payroll_effective_bank": has_effective,
        # What is currently verified? Never infer from payroll-effective.
        "verified": {
            "display": (verified or {}).get("display") or {},
            "fingerprint": (verified or {}).get("fingerprint"),
            "verified_at": (verified or {}).get("verified_at"),
            "verified_by_stage": (verified or {}).get("verified_by_stage"),
        }
        if has_verified
        else None,
        # What payroll actually uses — distinct from verified.
        "payroll_effective": {
            "display": (effective or {}).get("display") or {},
            "fingerprint": (effective or {}).get("fingerprint"),
            "effective_from": (effective or {}).get("effective_from"),
            "bank_profile_version": (effective or {}).get("bank_profile_version"),
        }
        if has_effective
        else None,
        # Is a change under review? What did the employee submit? Why rejected?
        "submission": submitted_block,
        "submission_state": submission,
        "change_under_review": submission in under_review_submissions,
        # What should happen next?
        "next_step": next_step(
            submission,
            has_verified=has_verified,
            locale=locale,
            workflow_state=workflow_state,
        ),
        "can_submit_new": submission
        in {
            SUBMISSION_NONE,
            SUBMISSION_REJECTED,
            SUBMISSION_WITHDRAWN,
            SUBMISSION_NEEDS_CORRECTION,
            SUBMISSION_APPLIED,
        }
        or workflow_state in {"applied", "needs_review", "failed"},
        "masking": {
            "masked_by_default": True,
            "reveal_requires_permission": "employees.ess.unmask",
            "reveal_is_audited": True,
        },
        "validation_scheme": default_scheme(company),
    }


def hr_bank_review(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    can_unmask: bool = False,
    locale: str = "en",
) -> dict[str, Any]:
    """HR review payload: current verified vs proposed, plus decision history."""
    status = employee_bank_status(
        cur,
        company_code=company_code,
        employee_key=employee_key,
        can_unmask=can_unmask,
        locale=locale,
    )
    company = str(company_code).upper()

    cur.execute(
        """
        SELECT request_id, fingerprint, display, verified_by_user_id,
               verified_by_stage, verified_at, validation,
               revoked_at, revocation_reason
        FROM employee_bank_verified
        WHERE company_code=%s AND employee_key=%s
        ORDER BY verified_at DESC
        LIMIT 25
        """,
        (company, employee_key),
    )
    verified_history = [dict(r) for r in (cur.fetchall() or [])]

    events: list[dict[str, Any]] = []
    try:
        cur.execute(
            """
            SELECT e.request_id, e.action, e.from_state, e.to_state,
                   e.actor_user_id, e.actor_employee_key, e.detail, e.created_at
            FROM employee_ess_request_events e
            JOIN employee_ess_requests r ON r.request_id = e.request_id
            WHERE r.company_code=%s AND r.employee_key=%s
              AND r.request_type='bank_detail_change'
            ORDER BY e.created_at DESC
            LIMIT 100
            """,
            (company, employee_key),
        )
        events = [dict(r) for r in (cur.fetchall() or [])]
    except Exception:
        events = []

    proposed = ((status.get("submission") or {}).get("proposed") or {}).get("display") or {}
    verified_display = (status.get("verified") or {}).get("display") or {}
    changed_fields = sorted(
        {
            f
            for f in set(proposed) | set(verified_display)
            if not f.endswith("_masked") and not f.endswith("_last4")
            and proposed.get(f) != verified_display.get(f)
        }
    )

    status["comparison"] = {
        "current_verified": verified_display,
        "proposed": proposed,
        "changed_fields": changed_fields,
        "is_first_submission": not status.get("has_verified_bank"),
    }
    status["verified_history"] = verified_history
    status["effective_history"] = effective_history(
        cur, company_code=company, employee_key=employee_key
    )
    status["decision_history"] = events
    status["payroll_lock"] = payroll_lock_state(cur, company_code=company)
    return status


# ---------------------------------------------------------------------------
# Onboarding checklist sync
# ---------------------------------------------------------------------------
def sync_onboarding_bank_item(
    cur: Any,
    *,
    employee_key: str,
    applied: bool = False,
    phase: str | None = None,
    rejection_reason: str | None = None,
    has_payroll_effective: bool | None = None,
) -> None:
    """Keep `bank_details` aligned with the Bank ESS request state machine.

    - submitted / pending review → checklist `processing` (Needs HR)
    - rejected / needs correction / needs_review → `replacement_required`
    - withdrawn → accepted if payroll-effective exists, else pending
    - applied → `accepted` (Completed)

    Without submit sync, HR only sees a generic Pending/Waive row while a real
    request sits under review. Without apply sync, onboarding never completes.
    Without withdraw sync, the checklist can stay stuck in processing.
    """
    try:
        import onboarding_lifecycle_wave2a as _lc
    except Exception:
        return

    resolved = str(phase or ("applied" if applied else "")).strip().lower()
    if not resolved:
        return
    try:
        if resolved in {
            "submitted",
            "pending_review",
            "pending_hr",
            "pending_manager",
            "pending_payroll",
            "approved",
        }:
            _lc.set_item_lifecycle(
                cur,
                employee_key=employee_key,
                item_id="bank_details",
                new_status=_lc.STATE_PROCESSING,
                clear_rejection=True,
                meta_patch={
                    "phase": "bank_ess_pending_review",
                    "source": "bank_ess_sync",
                    "authority": "ess",
                    "ess_phase": resolved,
                },
            )
            _lc.sync_completion_contract(cur, employee_key=employee_key, actor="bank_ess_submit")
            return
        if resolved in {
            "rejected",
            "needs_correction",
            "needs_information",
            "needs_review",
            "failed",
        }:
            _lc.set_item_lifecycle(
                cur,
                employee_key=employee_key,
                item_id="bank_details",
                new_status=_lc.STATE_REPLACEMENT_REQUIRED,
                rejection_reason=str(rejection_reason or "").strip() or None,
                meta_patch={
                    "phase": "bank_ess_needs_correction",
                    "source": "bank_ess_sync",
                    "authority": "ess",
                    "ess_phase": resolved,
                },
            )
            _lc.sync_completion_contract(cur, employee_key=employee_key, actor="bank_ess_reject")
            return
        if resolved in {"withdrawn", "withdraw"}:
            if has_payroll_effective:
                _lc.set_item_lifecycle(
                    cur,
                    employee_key=employee_key,
                    item_id="bank_details",
                    new_status=_lc.STATE_ACCEPTED,
                    clear_rejection=True,
                    meta_patch={
                        "phase": "accepted",
                        "source": "bank_ess_withdraw",
                        "authority": "ess",
                        "ess_phase": "withdrawn",
                    },
                )
                _lc.sync_completion_contract(cur, employee_key=employee_key, actor="bank_ess_withdraw")
                return
            _lc.set_item_lifecycle(
                cur,
                employee_key=employee_key,
                item_id="bank_details",
                new_status=_lc.STATE_PENDING,
                clear_rejection=True,
                meta_patch={
                    "phase": "bank_ess_withdrawn",
                    "source": "bank_ess_sync",
                    "authority": "ess",
                    "ess_phase": "withdrawn",
                },
            )
            _lc.sync_completion_contract(cur, employee_key=employee_key, actor="bank_ess_withdraw")
            return
        if resolved in {"applied", "accepted"} or applied:
            _lc.set_item_lifecycle(
                cur,
                employee_key=employee_key,
                item_id="bank_details",
                new_status=_lc.STATE_ACCEPTED,
                clear_rejection=True,
                meta_patch={"phase": "accepted", "source": "bank_ess_apply", "authority": "ess"},
            )
            _lc.sync_completion_contract(cur, employee_key=employee_key, actor="bank_ess_apply")
    except Exception:
        pass


# Which Bank ESS request states can still drive the checklist item. A request
# outside these is history and must never outrank the current bank of record.
BANK_OPEN_REVIEW_STATES = frozenset(
    {"submitted", "pending_hr", "pending_manager", "pending_payroll", "approved"}
)
BANK_OPEN_CORRECTION_STATES = frozenset({"needs_information", "needs_review", "failed"})
BANK_OPEN_STATES = BANK_OPEN_REVIEW_STATES | BANK_OPEN_CORRECTION_STATES


def _decision_reason(comments: Any) -> str | None:
    """Last reject / return-for-information note on one request."""
    if isinstance(comments, str):
        try:
            import json as _json

            comments = _json.loads(comments)
        except Exception:
            return None
    if not isinstance(comments, list):
        return None
    for entry in reversed(comments):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("action") or "") in {"reject", "return_for_information"} and entry.get("text"):
            return str(entry.get("text"))
    return None


def desired_onboarding_bank_state(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
) -> dict[str, Any] | None:
    """Canonical `bank_details` checklist state, from one authority order.

    1. An open request (only one can be open) owns the item: under review → HR,
       needs information → employee.
    2. Otherwise the bank of record decides: a live `employee_bank_effective`
       row means payroll is paying that account, so the item is satisfied.
    3. Only with no open request and no bank of record does terminal history
       (a rejection) speak.

    Ordering matters: an older `rejected` request used to outrank a newer
    `applied` one, so every HR read reverted a completed Bank item.
    """
    company = str(company_code or "").strip().upper()
    key = str(employee_key or "").strip()
    if not company or not key:
        return None
    try:
        cur.execute(
            """
            SELECT request_id::text, state, comments, updated_at
            FROM employee_ess_requests
            WHERE company_code=%s
              AND employee_key=%s
              AND request_type='bank_detail_change'
            ORDER BY updated_at DESC NULLS LAST, created_at DESC
            """,
            (company, key),
        )
        rows = [dict(r) for r in cur.fetchall() or []]
    except Exception:
        return None

    def _state(row: dict[str, Any]) -> str:
        return str(row.get("state") or "").strip().lower()

    open_req = next((r for r in rows if _state(r) in BANK_OPEN_STATES), None)
    if open_req is not None:
        state = _state(open_req)
        if state in BANK_OPEN_REVIEW_STATES:
            return {
                "phase": "pending_review",
                "request_id": open_req.get("request_id"),
                "request_state": state,
                "rejection_reason": None,
            }
        return {
            "phase": "needs_correction",
            "request_id": open_req.get("request_id"),
            "request_state": state,
            "rejection_reason": _decision_reason(open_req.get("comments")),
        }

    try:
        cur.execute(
            """
            SELECT request_id::text
            FROM employee_bank_effective
            WHERE company_code=%s AND employee_key=%s AND superseded_at IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (company, key),
        )
        effective = cur.fetchone()
    except Exception:
        effective = None
    if effective:
        return {
            "phase": "applied",
            "request_id": dict(effective).get("request_id"),
            "request_state": "applied",
            "rejection_reason": None,
        }

    latest = rows[0] if rows else None
    if latest is None:
        return None
    state = _state(latest)
    if state in {"withdrawn", "cancelled"}:
        # Withdrawn with no payroll-effective bank must clear checklist processing.
        return {
            "phase": "withdrawn",
            "request_id": latest.get("request_id"),
            "request_state": state,
            "rejection_reason": None,
        }
    if state == "applied":
        # Applied with no live effective row is still satisfied when the ESS bank
        # profile remains (payroll deferred / lock). A soft-deleted profile means
        # the bank of record was intentionally cleared — do not resurrect the
        # checklist item from applied history alone.
        try:
            cur.execute(
                """
                SELECT 1 FROM employee_ess_bank_profiles
                WHERE company_code=%s AND employee_key=%s AND deleted_at IS NULL
                LIMIT 1
                """,
                (company, key),
            )
            profile_live = cur.fetchone() is not None
        except Exception:
            profile_live = False
        if not profile_live:
            return None
        return {
            "phase": "applied",
            "request_id": latest.get("request_id"),
            "request_state": state,
            "rejection_reason": None,
        }
    if state == "rejected":
        return {
            "phase": "rejected",
            "request_id": latest.get("request_id"),
            "request_state": state,
            "rejection_reason": _decision_reason(latest.get("comments")),
        }
    # draft / withdrawn / cancelled: nothing has been asked of anyone yet.
    return None


def reconcile_onboarding_bank_item(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
) -> dict[str, Any] | None:
    """Align `bank_details` with the canonical Bank ESS authority.

    Safe to call on any read: it writes only when the checklist disagrees, so
    reads never churn `updated_at`, completion history, or audit trails.
    """
    desired = desired_onboarding_bank_state(
        cur, company_code=company_code, employee_key=employee_key
    )
    if not desired:
        return None
    key = str(employee_key or "").strip()
    phase = str(desired.get("phase") or "")
    reason = desired.get("rejection_reason")

    try:
        import onboarding_lifecycle_wave2a as _lc

        target_status = {
            "pending_review": _lc.STATE_PROCESSING,
            "needs_correction": _lc.STATE_REPLACEMENT_REQUIRED,
            "rejected": _lc.STATE_REPLACEMENT_REQUIRED,
            "applied": _lc.STATE_ACCEPTED,
            "withdrawn": _lc.STATE_PENDING,
        }.get(phase)
        if target_status is None:
            return None
        # Withdrawn while payroll still has an effective bank → accepted, not pending.
        if phase == "withdrawn":
            try:
                cur.execute(
                    """
                    SELECT 1 FROM employee_bank_effective
                    WHERE company_code=%s AND employee_key=%s AND superseded_at IS NULL
                    LIMIT 1
                    """,
                    (str(company_code or "").upper(), key),
                )
                if cur.fetchone():
                    target_status = _lc.STATE_ACCEPTED
            except Exception:
                pass
        cur.execute(
            "SELECT status, rejection_reason FROM onboarding_items WHERE employee_key=%s AND item_id='bank_details'",
            (key,),
        )
        current = cur.fetchone()
    except Exception:
        return None
    if current is None:
        return None
    current = dict(current)
    same_status = _lc.normalize_status(current.get("status")) == target_status
    same_reason = (str(current.get("rejection_reason") or "").strip() or None) == (
        str(reason or "").strip() or None
    )
    if same_status and same_reason:
        return {
            "request_id": desired.get("request_id"),
            "state": desired.get("request_state"),
            "changed": False,
        }

    if phase == "applied":
        sync_onboarding_bank_item(cur, employee_key=key, applied=True, phase="applied")
    elif phase == "withdrawn":
        sync_onboarding_bank_item(
            cur,
            employee_key=key,
            phase="withdrawn",
            has_payroll_effective=(target_status == _lc.STATE_ACCEPTED),
        )
    else:
        sync_onboarding_bank_item(
            cur, employee_key=key, phase=phase, rejection_reason=reason
        )
    return {
        "request_id": desired.get("request_id"),
        "state": desired.get("request_state"),
        "changed": True,
    }
