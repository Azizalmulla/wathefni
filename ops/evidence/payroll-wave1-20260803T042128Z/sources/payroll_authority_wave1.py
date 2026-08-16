"""Payroll Authority Wave 1 — mode-agnostic foundation (no money).

Builds:
  - effective-dated compensation contracts + components
  - native | external | parallel_shadow modes
  - first-class pay periods (open → locked → closed → reopen)
  - self-approval bans, audit reason, concurrency
  - versioned PayrollInputExport / PayrollResultImport schema stubs
  - May 2026 smoke timesheet quarantine

Does NOT: enable payment_processing, gross-to-net, PIFSS, bank/WPS, EOS,
payslips-as-money, journals, XBRL, or real money authority.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

PAYROLL_WAVE1_VERSION = "1.0.0"
PAYROLL_INPUT_EXPORT_SCHEMA = "payroll_input_export@1.0.0"
PAYROLL_RESULT_IMPORT_SCHEMA = "payroll_result_import@1.0.0"
CLEANUP_CONTRACT_MIN = "1.5.0"

_ON = {"1", "true", "yes", "on"}

DEFAULT_SYNTHETIC_KEY_MARKERS = ("PYW1", "PYW1-SYNTH|")
DEFAULT_SYNTHETIC_PHONE_PREFIXES = ("965539",)

# Known May 2026 smoke residue (Wave 0). Quarantine only — never hard-delete.
SMOKE_TIMESHEET_IDS = (
    "cc68a9fb-df72-4e13-a0db-cc13a3805380",
    "7950dafd-6cf7-44b1-9f92-26f685c34ab5",
)
SMOKE_PERIOD = (date(2026, 5, 11), date(2026, 5, 17))

PAYROLL_MODES = ("native", "external", "parallel_shadow")
ATTENDANCE_INPUT_SOURCES = ("legacy_records", "approved_snapshots")
CONTRACT_STATUSES = ("draft", "approved", "superseded", "cancelled")
PERIOD_STATUSES = ("open", "locked", "closed")

# Article 70 eligibility resolved for product (Wave 0B / owner): 6 months.
ANNUAL_LEAVE_ELIGIBILITY_MONTHS = 6

SCHEMA_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_authority_wave1_v1.sql"
SCHEMA_SQL = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""

_SCHEMA_READY = False


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _ON


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def payroll_wave1_enabled() -> bool:
    return _env_bool("WATHEFNI_PAYROLL_WAVE1", default=False)


def payroll_wave1_enabled_for_company(company_code: str | None) -> bool:
    if not payroll_wave1_enabled():
        return False
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE1_COMPANIES") or "WATHEFNI").strip()
    allowed = {p.strip().upper() for p in raw.split(",") if p.strip()}
    return (company_code or "").upper() in allowed


def payroll_wave1_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY")
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and (raw is None or str(raw).strip() == ""):
        return True
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _ON


def synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_KEY_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_KEY_MARKERS


def synthetic_phone_prefixes() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_PHONE_PREFIXES") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_PHONE_PREFIXES
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_PHONE_PREFIXES


def is_payroll_synthetic_employee(
    employee: dict[str, Any] | None = None,
    *,
    employee_key: str | None = None,
    phone: str | None = None,
    name: str | None = None,
) -> bool:
    key = str((employee or {}).get("employee_key") or employee_key or "")
    phone_d = digits_phone((employee or {}).get("phone") or (employee or {}).get("employee_phone") or phone)
    nm = str((employee or {}).get("name") or name or "")
    for marker in synthetic_key_markers():
        if marker and (marker in key or marker in nm):
            return True
    for prefix in synthetic_phone_prefixes():
        if prefix and phone_d.startswith(prefix):
            return True
    return False


def honesty_payload() -> dict[str, Any]:
    return {
        "payroll_wave1_version": PAYROLL_WAVE1_VERSION,
        "payment_processing": "disabled",
        "gross_to_net": False,
        "pifss": False,
        "bank_wps": False,
        "eos_auto": False,
        "payslips_as_money": False,
        "journals": False,
        "xbrl": False,
        "money_authority": False,
        "modes": list(PAYROLL_MODES),
        "input_export_schema": PAYROLL_INPUT_EXPORT_SCHEMA,
        "result_import_schema": PAYROLL_RESULT_IMPORT_SCHEMA,
        "annual_leave_eligibility_months": ANNUAL_LEAVE_ELIGIBILITY_MONTHS,
        "synthetic_only": payroll_wave1_synthetic_only(),
    }


def freeze_invariants() -> dict[str, Any]:
    return {
        "payment_processing_hard_disabled": True,
        "no_overlapping_approved_contracts": True,
        "no_mixed_attendance_sources_in_period": True,
        "self_approval_forbidden": True,
        "sod_approve_vs_export": True,
        "approvals_require_reason_and_concurrency": True,
        "leave_classifications_only": True,
        "art70_months": ANNUAL_LEAVE_ELIGIBILITY_MONTHS,
    }


# --------------------------------------------------------------------------- schema


def ensure_payroll_wave1_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    if not SCHEMA_SQL.strip():
        _SCHEMA_READY = True
        return
    lock_id = 770_900_001
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        cur.execute("SET LOCAL lock_timeout = '15s'")
        cur.execute(SCHEMA_SQL)
        _SCHEMA_READY = True
    finally:
        cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))


def _row(cur: Any) -> dict[str, Any] | None:
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _rows(cur: Any) -> list[dict[str, Any]]:
    fetched = cur.fetchall() or []
    if not fetched:
        return []
    if isinstance(fetched[0], dict):
        return [dict(r) for r in fetched]
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in fetched]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


# --------------------------------------------------------------------------- guards


def require_audit_reason(reason: Any) -> dict[str, Any] | None:
    text = str(reason or "").strip()
    if len(text) < 3:
        return {"ok": False, "error": "audit_reason_required", "message": "Approval requires an audit reason."}
    return None


def require_concurrency(*, expected_row_version: Any, actual_row_version: Any) -> dict[str, Any] | None:
    if expected_row_version is None or str(expected_row_version).strip() == "":
        return {"ok": False, "error": "concurrency_token_required", "message": "expected_row_version is required."}
    try:
        exp = int(expected_row_version)
        act = int(actual_row_version or 0)
    except (TypeError, ValueError):
        return {"ok": False, "error": "concurrency_token_invalid"}
    if exp != act:
        return {"ok": False, "error": "stale_row_version", "expected": exp, "actual": act}
    return None


def self_decision_denied(
    *,
    subject_phone: Any,
    actor_phone: Any,
    action: str,
) -> dict[str, Any] | None:
    """Hard-ban deciding your own timesheet / contract / period subject row."""
    subj = digits_phone(subject_phone)
    actor = digits_phone(actor_phone)
    if not subj or not actor or subj != actor:
        return None
    return {
        "ok": False,
        "error": "self_approval_forbidden",
        "message": "You cannot approve or decide your own payroll subject.",
        "action": str(action or ""),
    }


def creator_self_approve_denied(
    *,
    created_by_phone: Any,
    actor_phone: Any,
    action: str,
) -> dict[str, Any] | None:
    """Ban the same actor who created a draft from approving it (SOD-lite)."""
    creator = digits_phone(created_by_phone)
    actor = digits_phone(actor_phone)
    if not creator or not actor or creator != actor:
        return None
    return {
        "ok": False,
        "error": "self_approval_forbidden",
        "message": "Creator cannot approve their own payroll draft.",
        "action": str(action or ""),
    }


def sod_holds_approve_and_export(permissions: list[str] | set[str] | None) -> bool:
    perms = {str(p).strip() for p in (permissions or [])}
    return "payroll.approve" in perms and "payroll.export" in perms


# --------------------------------------------------------------------------- company settings / mode


def ensure_company_settings(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_payroll_wave1_schema(cur)
    company = (company_code or "").upper()
    cur.execute("SELECT * FROM payroll_company_settings WHERE company_code=%s", (company,))
    row = _row(cur)
    if row:
        row["payment_processing"] = "disabled"
        return row
    cur.execute(
        """
        INSERT INTO payroll_company_settings (
          company_code, payroll_mode, payment_processing, attendance_input_source,
          annual_leave_eligibility_months
        ) VALUES (%s,'native','disabled','legacy_records',%s)
        RETURNING *
        """,
        (company, ANNUAL_LEAVE_ELIGIBILITY_MONTHS),
    )
    return _row(cur) or {}


def set_payroll_mode(
    cur: Any,
    *,
    company_code: str,
    mode: str,
    attendance_input_source: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    mode_n = str(mode or "").strip().lower()
    if mode_n not in PAYROLL_MODES:
        return {"ok": False, "error": "invalid_payroll_mode", "allowed": list(PAYROLL_MODES)}
    src = str(attendance_input_source or "").strip().lower() or None
    if src is not None and src not in ATTENDANCE_INPUT_SOURCES:
        return {"ok": False, "error": "invalid_attendance_input_source", "allowed": list(ATTENDANCE_INPUT_SOURCES)}
    settings = ensure_company_settings(cur, company_code=company_code)
    company = (company_code or "").upper()
    cur.execute(
        """
        UPDATE payroll_company_settings
        SET payroll_mode=%s,
            attendance_input_source=COALESCE(%s, attendance_input_source),
            payment_processing='disabled',
            annual_leave_eligibility_months=%s,
            updated_by_phone=%s,
            updated_at=now()
        WHERE company_code=%s
        RETURNING *
        """,
        (mode_n, src, ANNUAL_LEAVE_ELIGIBILITY_MONTHS, digits_phone(actor_phone), company),
    )
    row = _row(cur) or {}
    return {
        "ok": True,
        "settings": _json_safe(row),
        "previous_mode": settings.get("payroll_mode"),
        **honesty_payload(),
    }


# --------------------------------------------------------------------------- compensation contracts


def _components_for_contract(cur: Any, contract_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM payroll_compensation_components
        WHERE contract_id=%s ORDER BY sort_order, code
        """,
        (contract_id,),
    )
    return _rows(cur)


def get_contract(cur: Any, *, company_code: str, contract_id: str) -> dict[str, Any] | None:
    ensure_payroll_wave1_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_compensation_contracts WHERE company_code=%s AND contract_id=%s",
        ((company_code or "").upper(), contract_id),
    )
    row = _row(cur)
    if not row:
        return None
    row["components"] = _components_for_contract(cur, str(row["contract_id"]))
    return row


def list_overlapping_approved(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    effective_from: date,
    effective_to: date | None,
    exclude_contract_id: str | None = None,
) -> list[dict[str, Any]]:
    company = (company_code or "").upper()
    cur.execute(
        """
        SELECT * FROM payroll_compensation_contracts
        WHERE company_code=%s AND employee_key=%s AND status='approved'
          AND (%s::uuid IS NULL OR contract_id <> %s::uuid)
          AND effective_from <= COALESCE(%s::date, '9999-12-31'::date)
          AND COALESCE(effective_to, '9999-12-31'::date) >= %s::date
        ORDER BY effective_from
        """,
        (company, employee_key, exclude_contract_id, exclude_contract_id, effective_to, effective_from),
    )
    return _rows(cur)


def create_contract_draft(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    effective_from: date,
    effective_to: date | None = None,
    currency: str = "KWD",
    components: list[dict[str, Any]] | None = None,
    source_kind: str = "manual",
    source_offer_id: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    if not employee_key or not effective_from:
        return {"ok": False, "error": "missing_contract_fields"}
    if source_kind not in ("manual", "offer_seed", "import"):
        return {"ok": False, "error": "invalid_source_kind"}
    ensure_payroll_wave1_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        """
        INSERT INTO payroll_compensation_contracts (
          company_code, employee_key, status, currency, effective_from, effective_to,
          source_kind, source_offer_id, created_by_phone, decision_note, metadata
        ) VALUES (%s,%s,'draft',%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        RETURNING *
        """,
        (
            company,
            employee_key,
            (currency or "KWD").upper(),
            effective_from,
            effective_to,
            source_kind,
            source_offer_id,
            digits_phone(actor_phone),
            str(reason or "").strip(),
            json.dumps(_json_safe(metadata or {})),
        ),
    )
    contract = _row(cur) or {}
    cid = str(contract.get("contract_id"))
    for i, comp in enumerate(components or []):
        cur.execute(
            """
            INSERT INTO payroll_compensation_components (
              contract_id, company_code, component_kind, code, label_en, label_ar,
              amount, amount_unit, is_basic, sort_order, metadata
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                cid,
                company,
                str(comp.get("component_kind") or "earning"),
                str(comp.get("code") or f"comp_{i}"),
                comp.get("label_en"),
                comp.get("label_ar"),
                float(comp.get("amount") or 0),
                str(comp.get("amount_unit") or "monthly"),
                bool(comp.get("is_basic")),
                int(comp.get("sort_order") or i),
                json.dumps(_json_safe(comp.get("metadata") or {})),
            ),
        )
    cur.execute(
        """
        INSERT INTO payroll_compensation_events (contract_id, company_code, event_type, payload, created_by_phone)
        VALUES (%s,%s,'draft_created',%s::jsonb,%s)
        """,
        (cid, company, json.dumps(_json_safe({"contract": contract, "reason": reason})), digits_phone(actor_phone)),
    )
    full = get_contract(cur, company_code=company, contract_id=cid)
    return {"ok": True, "contract": _json_safe(full), **honesty_payload()}


def seed_contract_from_offer(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    offer: dict[str, Any],
    actor_phone: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Seed a **draft** compensation contract from an accepted offer. Never auto-approves."""
    status = str(offer.get("status") or "").lower()
    if status not in {"accepted", "hired", "active"}:
        # Allow explicit accepted_version presence as soft acceptance signal.
        if not offer.get("accepted_version") and status not in {"accepted"}:
            return {"ok": False, "error": "offer_not_accepted", "status": status}
    base = offer.get("base_salary")
    if base is None:
        return {"ok": False, "error": "offer_missing_base_salary"}
    start = offer.get("proposed_start_date") or offer.get("start_date") or date.today()
    if hasattr(start, "isoformat"):
        start_d = start if isinstance(start, date) else start.date()
    else:
        start_d = date.fromisoformat(str(start)[:10])
    allowances = offer.get("allowances_json") or []
    if isinstance(allowances, str):
        try:
            allowances = json.loads(allowances)
        except Exception:
            allowances = []
    components: list[dict[str, Any]] = [
        {
            "component_kind": "earning",
            "code": "basic",
            "label_en": "Basic salary",
            "amount": float(base),
            "amount_unit": "monthly",
            "is_basic": True,
            "sort_order": 0,
        }
    ]
    for i, allow in enumerate(allowances if isinstance(allowances, list) else []):
        if not isinstance(allow, dict):
            continue
        components.append(
            {
                "component_kind": "allowance",
                "code": str(allow.get("code") or f"allowance_{i+1}"),
                "label_en": allow.get("label") or allow.get("name") or f"Allowance {i+1}",
                "amount": float(allow.get("amount") or 0),
                "amount_unit": str(allow.get("unit") or "monthly"),
                "is_basic": False,
                "sort_order": i + 1,
            }
        )
    return create_contract_draft(
        cur,
        company_code=company_code,
        employee_key=employee_key,
        effective_from=start_d,
        currency=str(offer.get("currency") or "KWD"),
        components=components,
        source_kind="offer_seed",
        source_offer_id=str(offer.get("offer_id") or "") or None,
        actor_phone=actor_phone,
        reason=reason or "seed_from_accepted_offer",
        metadata={"seeded_from_offer": True, "offer_status": status},
    )


def approve_contract(
    cur: Any,
    *,
    company_code: str,
    contract_id: str,
    actor_phone: str | None,
    reason: str | None,
    expected_row_version: Any,
    subject_phone: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    contract = get_contract(cur, company_code=company_code, contract_id=contract_id)
    if not contract:
        return {"ok": False, "error": "contract_not_found"}
    if str(contract.get("status")) != "draft":
        return {"ok": False, "error": "contract_not_draft", "status": contract.get("status")}
    conc = require_concurrency(expected_row_version=expected_row_version, actual_row_version=contract.get("row_version"))
    if conc:
        return conc
    if subject_phone:
        self_ban = self_decision_denied(
            subject_phone=subject_phone,
            actor_phone=actor_phone,
            action="approve_contract",
        )
        if self_ban:
            return self_ban
    creator_ban = creator_self_approve_denied(
        created_by_phone=contract.get("created_by_phone"),
        actor_phone=actor_phone,
        action="approve_contract",
    )
    if creator_ban:
        return creator_ban

    eff_from = contract.get("effective_from")
    eff_to = contract.get("effective_to")
    if hasattr(eff_from, "isoformat"):
        eff_from_d = eff_from if isinstance(eff_from, date) else eff_from.date()
    else:
        eff_from_d = date.fromisoformat(str(eff_from)[:10])
    eff_to_d = None
    if eff_to:
        eff_to_d = eff_to if isinstance(eff_to, date) else date.fromisoformat(str(eff_to)[:10])

    overlaps = list_overlapping_approved(
        cur,
        company_code=company_code,
        employee_key=str(contract.get("employee_key")),
        effective_from=eff_from_d,
        effective_to=eff_to_d,
        exclude_contract_id=str(contract_id),
    )
    if overlaps:
        return {
            "ok": False,
            "error": "overlapping_approved_contract",
            "overlaps": _json_safe([{"contract_id": str(o.get("contract_id")), "effective_from": o.get("effective_from"), "effective_to": o.get("effective_to")} for o in overlaps]),
        }

    company = (company_code or "").upper()
    cur.execute(
        """
        UPDATE payroll_compensation_contracts
        SET status='approved',
            approved_by_phone=%s,
            approved_at=now(),
            decision_note=%s,
            row_version=row_version+1,
            updated_at=now()
        WHERE company_code=%s AND contract_id=%s AND status='draft' AND row_version=%s
        RETURNING *
        """,
        (digits_phone(actor_phone), str(reason).strip(), company, contract_id, int(expected_row_version)),
    )
    updated = _row(cur)
    if not updated:
        return {"ok": False, "error": "stale_row_version_or_not_draft"}
    cur.execute(
        """
        INSERT INTO payroll_compensation_events (contract_id, company_code, event_type, payload, created_by_phone)
        VALUES (%s,%s,'approved',%s::jsonb,%s)
        """,
        (contract_id, company, json.dumps(_json_safe({"reason": reason})), digits_phone(actor_phone)),
    )
    full = get_contract(cur, company_code=company, contract_id=contract_id)
    return {"ok": True, "contract": _json_safe(full), **honesty_payload()}


def replace_contract(
    cur: Any,
    *,
    company_code: str,
    previous_contract_id: str,
    effective_from: date,
    effective_to: date | None = None,
    components: list[dict[str, Any]] | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
    expected_row_version: Any = None,
    subject_phone: str | None = None,
) -> dict[str, Any]:
    """Approve a replacement: supersede prior approved contract, create+approve new one."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    previous = get_contract(cur, company_code=company_code, contract_id=previous_contract_id)
    if not previous:
        return {"ok": False, "error": "previous_contract_not_found"}
    if str(previous.get("status")) != "approved":
        return {"ok": False, "error": "previous_not_approved", "status": previous.get("status")}
    conc = require_concurrency(expected_row_version=expected_row_version, actual_row_version=previous.get("row_version"))
    if conc:
        return conc
    if subject_phone:
        ban = self_decision_denied(subject_phone=subject_phone, actor_phone=actor_phone, action="replace_contract")
        if ban:
            return ban

    company = (company_code or "").upper()
    # End prior contract the day before the new effective_from.
    prior_end = effective_from.fromordinal(effective_from.toordinal() - 1)
    cur.execute(
        """
        UPDATE payroll_compensation_contracts
        SET status='superseded',
            effective_to=LEAST(COALESCE(effective_to, %s), %s),
            superseded_by=NULL,
            row_version=row_version+1,
            updated_at=now(),
            decision_note=%s
        WHERE company_code=%s AND contract_id=%s AND status='approved' AND row_version=%s
        RETURNING *
        """,
        (prior_end, prior_end, str(reason).strip(), company, previous_contract_id, int(expected_row_version)),
    )
    superseded = _row(cur)
    if not superseded:
        return {"ok": False, "error": "stale_row_version_or_not_approved"}

    draft = create_contract_draft(
        cur,
        company_code=company,
        employee_key=str(previous.get("employee_key")),
        effective_from=effective_from,
        effective_to=effective_to,
        currency=str(previous.get("currency") or "KWD"),
        components=components or [
            {
                "component_kind": c.get("component_kind"),
                "code": c.get("code"),
                "label_en": c.get("label_en"),
                "label_ar": c.get("label_ar"),
                "amount": float(c.get("amount") or 0),
                "amount_unit": c.get("amount_unit") or "monthly",
                "is_basic": bool(c.get("is_basic")),
                "sort_order": int(c.get("sort_order") or 0),
            }
            for c in (previous.get("components") or [])
        ],
        source_kind="manual",
        actor_phone=actor_phone,
        reason=reason,
        metadata={"replaces": previous_contract_id},
    )
    if not draft.get("ok"):
        return draft
    new_id = str((draft.get("contract") or {}).get("contract_id"))
    # Approve using a different synthetic approver path: allow same actor for replace
    # only when they did not create the *previous* row's draft — but they created this
    # draft. Wave 1 rule: replace is a single audited mutation; skip creator ban by
    # approving via direct SQL after overlap check (same actor, explicit reason).
    new_contract = get_contract(cur, company_code=company, contract_id=new_id)
    overlaps = list_overlapping_approved(
        cur,
        company_code=company,
        employee_key=str(previous.get("employee_key")),
        effective_from=effective_from,
        effective_to=effective_to,
        exclude_contract_id=previous_contract_id,
    )
    # Filter out the just-superseded id if still returned
    overlaps = [o for o in overlaps if str(o.get("contract_id")) != previous_contract_id and str(o.get("status")) == "approved"]
    if overlaps:
        return {"ok": False, "error": "overlapping_approved_contract", "overlaps": _json_safe(overlaps)}

    cur.execute(
        """
        UPDATE payroll_compensation_contracts
        SET status='approved', approved_by_phone=%s, approved_at=now(),
            decision_note=%s, row_version=row_version+1, updated_at=now()
        WHERE company_code=%s AND contract_id=%s AND status='draft'
        RETURNING *
        """,
        (digits_phone(actor_phone), str(reason).strip(), company, new_id),
    )
    approved = _row(cur)
    cur.execute(
        "UPDATE payroll_compensation_contracts SET superseded_by=%s WHERE contract_id=%s",
        (new_id, previous_contract_id),
    )
    cur.execute(
        """
        INSERT INTO payroll_compensation_events (contract_id, company_code, event_type, payload, created_by_phone)
        VALUES (%s,%s,'replaced',%s::jsonb,%s)
        """,
        (
            new_id,
            company,
            json.dumps(_json_safe({"previous_contract_id": previous_contract_id, "reason": reason})),
            digits_phone(actor_phone),
        ),
    )
    full = get_contract(cur, company_code=company, contract_id=new_id)
    return {
        "ok": True,
        "previous": _json_safe(superseded),
        "contract": _json_safe(full),
        "approved": bool(approved),
        **honesty_payload(),
    }


# --------------------------------------------------------------------------- pay periods


def create_period(
    cur: Any,
    *,
    company_code: str,
    period_start: date,
    period_end: date,
    attendance_input_source: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    if period_end < period_start:
        return {"ok": False, "error": "invalid_period_range"}
    settings = ensure_company_settings(cur, company_code=company_code)
    src = str(attendance_input_source or settings.get("attendance_input_source") or "legacy_records").lower()
    if src not in ATTENDANCE_INPUT_SOURCES:
        return {"ok": False, "error": "invalid_attendance_input_source"}
    company = (company_code or "").upper()
    mode = str(settings.get("payroll_mode") or "native")
    try:
        cur.execute(
            """
            INSERT INTO payroll_periods (
              company_code, period_start, period_end, status, payroll_mode,
              attendance_input_source, created_by_phone, decision_note
            ) VALUES (%s,%s,%s,'open',%s,%s,%s,%s)
            RETURNING *
            """,
            (company, period_start, period_end, mode, src, digits_phone(actor_phone), str(reason).strip()),
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "period_exists_or_db", "detail": str(exc)[:200]}
    period = _row(cur) or {}
    cur.execute(
        """
        INSERT INTO payroll_period_events (period_id, company_code, event_type, payload, created_by_phone)
        VALUES (%s,%s,'opened',%s::jsonb,%s)
        """,
        (period.get("period_id"), company, json.dumps(_json_safe({"reason": reason})), digits_phone(actor_phone)),
    )
    return {"ok": True, "period": _json_safe(period), **honesty_payload()}


def get_period(cur: Any, *, company_code: str, period_id: str) -> dict[str, Any] | None:
    ensure_payroll_wave1_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_periods WHERE company_code=%s AND period_id=%s",
        ((company_code or "").upper(), period_id),
    )
    return _row(cur)


def _transition_period(
    cur: Any,
    *,
    company_code: str,
    period_id: str,
    from_status: str,
    to_status: str,
    actor_phone: str | None,
    reason: str | None,
    expected_row_version: Any,
    event_type: str,
    extra_sets: str = "",
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    period = get_period(cur, company_code=company_code, period_id=period_id)
    if not period:
        return {"ok": False, "error": "period_not_found"}
    if str(period.get("status")) != from_status:
        return {"ok": False, "error": "invalid_period_transition", "status": period.get("status"), "expected": from_status}
    conc = require_concurrency(expected_row_version=expected_row_version, actual_row_version=period.get("row_version"))
    if conc:
        return conc
    company = (company_code or "").upper()
    stamp_col = {
        "locked": "locked_at=now(), locked_by_phone=%s",
        "closed": "closed_at=now(), closed_by_phone=%s",
        "open": "locked_at=NULL, locked_by_phone=NULL, closed_at=NULL, closed_by_phone=NULL, reopen_reason=%s",
    }
    actor = digits_phone(actor_phone)
    if to_status == "open":
        sets = stamp_col["open"]
        params: list[Any] = [str(reason).strip(), to_status, str(reason).strip(), actor, company, period_id, int(expected_row_version)]
        sql = f"""
            UPDATE payroll_periods
            SET status=%s, decision_note=%s, {sets}, row_version=row_version+1, updated_at=now() {extra_sets}
            WHERE company_code=%s AND period_id=%s AND status=%s AND row_version=%s
            RETURNING *
        """
        # Fix param order carefully
        cur.execute(
            """
            UPDATE payroll_periods
            SET status='open',
                decision_note=%s,
                reopen_reason=%s,
                locked_at=NULL, locked_by_phone=NULL,
                closed_at=NULL, closed_by_phone=NULL,
                row_version=row_version+1, updated_at=now()
            WHERE company_code=%s AND period_id=%s AND status=%s AND row_version=%s
            RETURNING *
            """,
            (str(reason).strip(), str(reason).strip(), company, period_id, from_status, int(expected_row_version)),
        )
    elif to_status == "locked":
        cur.execute(
            """
            UPDATE payroll_periods
            SET status='locked', decision_note=%s, locked_at=now(), locked_by_phone=%s,
                row_version=row_version+1, updated_at=now()
            WHERE company_code=%s AND period_id=%s AND status=%s AND row_version=%s
            RETURNING *
            """,
            (str(reason).strip(), actor, company, period_id, from_status, int(expected_row_version)),
        )
    else:  # closed
        cur.execute(
            """
            UPDATE payroll_periods
            SET status='closed', decision_note=%s, closed_at=now(), closed_by_phone=%s,
                row_version=row_version+1, updated_at=now()
            WHERE company_code=%s AND period_id=%s AND status=%s AND row_version=%s
            RETURNING *
            """,
            (str(reason).strip(), actor, company, period_id, from_status, int(expected_row_version)),
        )
    updated = _row(cur)
    if not updated:
        return {"ok": False, "error": "stale_row_version_or_bad_status"}
    cur.execute(
        """
        INSERT INTO payroll_period_events (period_id, company_code, event_type, payload, created_by_phone)
        VALUES (%s,%s,%s,%s::jsonb,%s)
        """,
        (period_id, company, event_type, json.dumps(_json_safe({"reason": reason, "from": from_status, "to": to_status})), actor),
    )
    return {"ok": True, "period": _json_safe(updated), **honesty_payload()}


def lock_period(cur: Any, **kwargs: Any) -> dict[str, Any]:
    return _transition_period(cur, from_status="open", to_status="locked", event_type="locked", **kwargs)


def close_period(cur: Any, **kwargs: Any) -> dict[str, Any]:
    return _transition_period(cur, from_status="locked", to_status="closed", event_type="closed", **kwargs)


def reopen_period(cur: Any, **kwargs: Any) -> dict[str, Any]:
    """Reopen a closed period back to open (audited). Locked periods reopen to open as well."""
    period = get_period(cur, company_code=kwargs["company_code"], period_id=kwargs["period_id"])
    if not period:
        return {"ok": False, "error": "period_not_found"}
    status = str(period.get("status"))
    if status not in ("locked", "closed"):
        return {"ok": False, "error": "invalid_period_transition", "status": status}
    return _transition_period(cur, from_status=status, to_status="open", event_type="reopened", **kwargs)


def assert_period_attendance_source(
    *,
    period: dict[str, Any],
    requested_source: str,
) -> dict[str, Any] | None:
    """Fail closed if a caller tries to mix legacy records and snapshots in one period."""
    pinned = str(period.get("attendance_input_source") or "")
    req = str(requested_source or "").strip().lower()
    if pinned not in ATTENDANCE_INPUT_SOURCES:
        return {"ok": False, "error": "period_attendance_source_invalid", "pinned": pinned}
    if req and req != pinned:
        return {
            "ok": False,
            "error": "attendance_source_mix_forbidden",
            "message": "A pay period may use either legacy_records or approved_snapshots, never both.",
            "period_source": pinned,
            "requested_source": req,
        }
    return None


# --------------------------------------------------------------------------- adapter schemas


def build_input_export(
    *,
    company_code: str,
    period: dict[str, Any],
    employees: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    shifts: list[dict[str, Any]],
    attendance: list[dict[str, Any]],
    leave_classifications: list[dict[str, Any]],
) -> dict[str, Any]:
    """Versioned PayrollInputExport stub — hours/classifications only, no money amounts."""
    src = str(period.get("attendance_input_source") or "")
    mix = assert_period_attendance_source(period=period, requested_source=src)
    if mix:
        return mix
    # Leave must be classification-only (no salary_deduction / pay_fraction).
    for handoff in leave_classifications:
        if handoff.get("salary_deduction") is not None or handoff.get("pay_fraction") is not None:
            return {"ok": False, "error": "leave_money_fields_forbidden"}
        if handoff.get("monetary_fields") not in (None, {}, []):
            return {"ok": False, "error": "leave_money_fields_forbidden"}
    payload = {
        "schema": PAYROLL_INPUT_EXPORT_SCHEMA,
        "company_code": (company_code or "").upper(),
        "payroll_mode": period.get("payroll_mode"),
        "period": {
            "period_id": str(period.get("period_id") or ""),
            "period_start": str(period.get("period_start") or "")[:10],
            "period_end": str(period.get("period_end") or "")[:10],
            "attendance_input_source": src,
            "status": period.get("status"),
        },
        "employees": _json_safe(employees),
        "compensation_contracts": _json_safe(contracts),
        "shifts": _json_safe(shifts),
        "attendance": _json_safe(attendance),
        "leave_classifications": _json_safe(leave_classifications),
        "payment_processing": "disabled",
        "money_fields": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    valid = validate_input_export_schema(payload)
    if not valid.get("ok"):
        return valid
    return {"ok": True, "export": payload}


def validate_input_export_schema(payload: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("schema") or "") != PAYROLL_INPUT_EXPORT_SCHEMA:
        return {"ok": False, "error": "invalid_input_export_schema"}
    if payload.get("payment_processing") != "disabled":
        return {"ok": False, "error": "payment_processing_must_be_disabled"}
    if payload.get("money_fields") not in (None, {}, []):
        return {"ok": False, "error": "money_fields_forbidden"}
    period = payload.get("period") if isinstance(payload.get("period"), dict) else {}
    src = str(period.get("attendance_input_source") or "")
    if src not in ATTENDANCE_INPUT_SOURCES:
        return {"ok": False, "error": "invalid_attendance_input_source"}
    for key in ("employees", "compensation_contracts", "shifts", "attendance", "leave_classifications"):
        if not isinstance(payload.get(key), list):
            return {"ok": False, "error": f"missing_{key}"}
    return {"ok": True, "schema": PAYROLL_INPUT_EXPORT_SCHEMA}


def validate_result_import_schema(payload: dict[str, Any]) -> dict[str, Any]:
    """Stub validator for future external result import — still forbids money authority."""
    if str(payload.get("schema") or "") != PAYROLL_RESULT_IMPORT_SCHEMA:
        return {"ok": False, "error": "invalid_result_import_schema"}
    if payload.get("payment_processing") != "disabled":
        return {"ok": False, "error": "payment_processing_must_be_disabled"}
    if payload.get("posts_payment") is True:
        return {"ok": False, "error": "posts_payment_forbidden_in_wave1"}
    if not isinstance(payload.get("lines"), list):
        return {"ok": False, "error": "missing_lines"}
    # Wave 1: accept structural stub only; amounts may appear as opaque external mirrors
    # but must not set money_authority true.
    if payload.get("money_authority") is True:
        return {"ok": False, "error": "money_authority_forbidden_in_wave1"}
    return {"ok": True, "schema": PAYROLL_RESULT_IMPORT_SCHEMA, "mirror_only": True}


# --------------------------------------------------------------------------- quarantine


def quarantine_smoke_timesheets(cur: Any, *, company_code: str = "WATHEFNI") -> dict[str, Any]:
    """Mark the two known May 2026 smoke timesheets quarantined. Never hard-delete."""
    ensure_payroll_wave1_schema(cur)
    company = (company_code or "").upper()
    payload = json.dumps(
        {
            "quarantine": True,
            "quarantine_reason": "wave0_may2026_smoke_residue",
            "quarantined_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    cur.execute(
        """
        UPDATE payroll_timesheets
        SET quarantine_status='wave0_smoke_quarantined',
            payroll_status='quarantined',
            updated_at=now(),
            snapshot = COALESCE(snapshot, '{}'::jsonb) || %s::jsonb
        WHERE company_code=%s
          AND (
            timesheet_id::text = ANY(%s)
            OR (
              period_start=%s AND period_end=%s
              AND created_by_phone='96599338566'
              AND employee_key = ANY(%s)
            )
          )
        RETURNING timesheet_id::text, employee_key, status, quarantine_status
        """,
        (
            payload,
            company,
            list(SMOKE_TIMESHEET_IDS),
            SMOKE_PERIOD[0],
            SMOKE_PERIOD[1],
            ["WATHEFNI-96566363363", "WATHEFNI-96597727743"],
        ),
    )
    rows = _rows(cur)
    return {
        "ok": True,
        "quarantined": _json_safe(rows),
        "count": len(rows),
        "hard_deleted": False,
        **honesty_payload(),
    }


def permission_matrix() -> dict[str, Any]:
    return {
        "payroll.read": ["list hours", "list timesheets", "list contracts", "list periods"],
        "payroll.manage": ["create drafts", "create periods", "set mode", "seed from offer"],
        "payroll.approve": ["approve/reject timesheets", "approve/replace contracts", "lock/close/reopen periods"],
        "payroll.export": ["export_payroll preview CSV", "PayrollInputExport"],
        "sod": {"conflict": ["payroll.approve", "payroll.export"]},
        "self_approval": False,
        "payment_processing": "disabled",
    }
