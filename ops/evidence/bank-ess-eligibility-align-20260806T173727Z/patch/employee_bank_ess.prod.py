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

CONTRACT_VERSION = "bank_ess_v1"

# Fields the employee may propose. Everything else is ignored, not stored.
PROPOSABLE_FIELDS = ("iban", "bank_name", "account_holder", "account_number", "swift", "branch")
SENSITIVE_PROPOSABLE = frozenset({"iban", "account_number"})

SEALED_KEY = "__sealed_bank"

# Employee-facing submission states, derived from the underlying request state.
SUBMISSION_NONE = "none"
SUBMISSION_DRAFT = "draft"
SUBMISSION_PENDING_REVIEW = "pending_review"
SUBMISSION_APPROVED = "approved"
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
    problems: list[str] = []
    if not raw:
        problems.append("iban_required")
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
    raw = str(values.get("iban") or values.get("account_number") or "").strip()
    problems = [] if raw else ["account_identifier_required"]
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
    # Advisory by default so a new bank format cannot lock employees out.
    result["enforced"] = (os.environ.get("WATHEFNI_BANK_ESS_ENFORCE_VALIDATION") or "").strip().lower() in _ON
    return result


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
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS employee_bank_evidence_purge_idx
        ON employee_bank_evidence (retention_until)
        WHERE purged_at IS NULL
        """
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
            },
        )


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
) -> None:
    """Idempotent: the same request verifying twice does not duplicate history."""
    ensure_bank_ess_schema(cur)
    safe = safe_request_projection(proposed)
    cur.execute(
        """
        INSERT INTO employee_bank_verified (
          company_code, employee_key, request_id, fingerprint, display,
          verified_by_user_id, verified_by_stage, validation
        ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb)
        ON CONFLICT (company_code, employee_key, request_id) DO NOTHING
        """,
        (
            str(company_code).upper(),
            employee_key,
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


def list_evidence(
    cur: Any, *, company_code: str, employee_key: str, request_id: str | None = None
) -> list[dict[str, Any]]:
    try:
        if request_id:
            cur.execute(
                """
                SELECT evidence_id, filename, mime_type, byte_size, uploaded_at,
                       retention_until, deleted_at
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
                       retention_until, deleted_at
                FROM employee_bank_evidence
                WHERE company_code=%s AND employee_key=%s AND deleted_at IS NULL
                ORDER BY uploaded_at DESC
                """,
                (str(company_code).upper(), employee_key),
            )
        return [dict(r) for r in (cur.fetchall() or [])]
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
    if state in {"needs_information", "needs_review"}:
        return SUBMISSION_NEEDS_CORRECTION
    if state in {"submitted", "pending_manager", "pending_hr", "pending_payroll"}:
        return SUBMISSION_PENDING_REVIEW
    if state in {"approved", "applied"}:
        return SUBMISSION_APPROVED
    if state == "rejected":
        return SUBMISSION_REJECTED
    if state == "withdrawn":
        return SUBMISSION_WITHDRAWN
    if state == "failed":
        return SUBMISSION_NEEDS_CORRECTION
    return SUBMISSION_PENDING_REVIEW


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


def next_step(submission: str, *, has_verified: bool, locale: str = "en") -> dict[str, Any]:
    is_ar = str(locale).lower().startswith("ar")
    table = {
        SUBMISSION_NONE: (
            "employee",
            "Add your bank details so salary can be paid to you."
            if not has_verified
            else "Your bank details are verified. Submit a change if anything is different.",
            "أضف بيانات حسابك البنكي لاستلام الراتب."
            if not has_verified
            else "بيانات حسابك البنكي موثقة. أرسل تغييرًا إذا اختلف أي شيء.",
        ),
        SUBMISSION_DRAFT: (
            "employee",
            "Your draft is saved but not submitted. Submit it for HR review.",
            "تم حفظ المسودة ولم تُرسل بعد. أرسلها لمراجعة الموارد البشرية.",
        ),
        SUBMISSION_PENDING_REVIEW: (
            "hr",
            "HR is reviewing your submission. Your verified details have not changed yet.",
            "الموارد البشرية تراجع طلبك. لم تتغير بياناتك الموثقة بعد.",
        ),
        SUBMISSION_NEEDS_CORRECTION: (
            "employee",
            "HR asked for a correction. Update the details and resubmit.",
            "طلبت الموارد البشرية تصحيحًا. حدّث البيانات وأعد الإرسال.",
        ),
        SUBMISSION_REJECTED: (
            "employee",
            "Your submission was rejected. Review the reason, correct it and resubmit.",
            "تم رفض طلبك. راجع السبب، صححه وأعد الإرسال.",
        ),
        SUBMISSION_APPROVED: (
            "none",
            "Your new bank details were approved and are now used for payroll.",
            "تمت الموافقة على بياناتك البنكية الجديدة وسيتم استخدامها للرواتب.",
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
        WHERE company_code=%s AND employee_key=%s
        ORDER BY verified_at DESC
        LIMIT 1
        """,
        (company, employee_key),
    )
    verified = dict(cur.fetchone() or {}) or None

    request = active_request(cur, company_code=company, employee_key=employee_key)
    if not request:
        states = ", ".join("'" + s + "'" for s in ("rejected", "withdrawn", "applied", "failed"))
        cur.execute(
            f"""
            SELECT * FROM employee_ess_requests
            WHERE company_code=%s AND employee_key=%s
              AND request_type='bank_detail_change' AND state IN ({states})
            ORDER BY updated_at DESC NULLS LAST, created_at DESC
            LIMIT 1
            """,
            (company, employee_key),
        )
        row = cur.fetchone()
        request = dict(row) if row else None

    submission = _submission_state(request)
    has_verified = bool(verified or effective)

    submitted_block = None
    if request:
        submitted_block = {
            "request_id": str(request.get("request_id")),
            "state": request.get("state"),
            "submission_state": submission,
            "submitted_at": request.get("created_at"),
            "updated_at": request.get("updated_at"),
            "proposed": safe_request_projection(
                request.get("proposed_values"), can_unmask=can_unmask
            ),
            "rejection_reason": _latest_decision_reason(request)
            if submission in {SUBMISSION_REJECTED, SUBMISSION_NEEDS_CORRECTION}
            else None,
            "can_withdraw": submission in {SUBMISSION_DRAFT, SUBMISSION_PENDING_REVIEW},
            "can_resubmit": submission
            in {SUBMISSION_REJECTED, SUBMISSION_NEEDS_CORRECTION, SUBMISSION_WITHDRAWN},
            "evidence": list_evidence(
                cur,
                company_code=company,
                employee_key=employee_key,
                request_id=str(request.get("request_id")),
            ),
        }

    return {
        "contract_version": CONTRACT_VERSION,
        "employee_key": employee_key,
        "has_verified_bank": has_verified,
        # What is currently verified?
        "verified": {
            "display": (verified or {}).get("display") or (effective or {}).get("display") or {},
            "fingerprint": (verified or {}).get("fingerprint") or (effective or {}).get("fingerprint"),
            "verified_at": (verified or {}).get("verified_at"),
            "verified_by_stage": (verified or {}).get("verified_by_stage"),
        }
        if has_verified
        else None,
        # What payroll actually uses.
        "payroll_effective": {
            "display": (effective or {}).get("display") or {},
            "effective_from": (effective or {}).get("effective_from"),
            "bank_profile_version": (effective or {}).get("bank_profile_version"),
        }
        if effective
        else None,
        # Is a change under review? What did the employee submit? Why rejected?
        "submission": submitted_block,
        "submission_state": submission,
        "change_under_review": submission
        in {SUBMISSION_PENDING_REVIEW, SUBMISSION_DRAFT, SUBMISSION_NEEDS_CORRECTION},
        # What should happen next?
        "next_step": next_step(submission, has_verified=has_verified, locale=locale),
        "can_submit_new": submission
        in {SUBMISSION_NONE, SUBMISSION_APPROVED, SUBMISSION_REJECTED, SUBMISSION_WITHDRAWN},
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
               verified_by_stage, verified_at, validation
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
def sync_onboarding_bank_item(cur: Any, *, employee_key: str, applied: bool) -> None:
    """Bank ESS apply closes the `bank_details` checklist item.

    Without this the item stays open forever and onboarding can never complete.
    """
    if not applied:
        return
    try:
        import onboarding_lifecycle_wave2a as _lc

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
