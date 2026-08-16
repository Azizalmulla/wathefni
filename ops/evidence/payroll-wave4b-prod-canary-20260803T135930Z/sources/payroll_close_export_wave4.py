"""Payroll Wave 4 — close + finance export foundation (staging).

Controlled review → approve → close with immutable snapshot.
Generic journal drafts (account/cost-centre mappings) + bank-export contract validation only.

Does NOT: enable payment_processing, real bank formats/connections, WPS/AS'HAL,
PIFSS, EOS, ERP journal posting, payments, or AI.
Native results remain preview/non-authoritative; external payroll remains money authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import payroll_authority_wave1 as pyw1
import payroll_external_adapter_wave2a as w2a
import payroll_native_preview_wave2b as w2b

PAYROLL_WAVE4_VERSION = "1.0.0"
BANK_EXPORT_CONTRACT_SCHEMA = "payroll_bank_export_contract@1.0.0"
JOURNAL_DRAFT_SCHEMA = "payroll_journal_draft@1.0.0"

_ON = {"1", "true", "yes", "on"}
MONEY_Q = Decimal("0.001")

DEFAULT_SYNTHETIC_KEY_MARKERS = (
    "PYW4",
    "PYW4-SYNTH|",
    "PYW3",
    "PYW3-SYNTH|",
    "PYW2B",
    "PYW2B-SYNTH|",
    "PYW2A",
    "PYW2ACB",
    "PYW1",
    "PYW1-SYNTH|",
    "W2BB",
    "W3B",
    "W4",
)
DEFAULT_SYNTHETIC_PHONE_PREFIXES = ("965539", "965540", "965541")

SOURCE_NATIVE = "native_preview"
SOURCE_EXTERNAL = "external_import"

STATUS_DRAFT = "draft"
STATUS_IN_REVIEW = "in_review"
STATUS_APPROVED = "approved"
STATUS_CLOSED = "closed"
STATUS_REOPENED = "reopened"

SCHEMA_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_close_export_wave4_v1.sql"
SCHEMA_SQL = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
_SCHEMA_READY = False


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _ON


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def payroll_wave4_enabled() -> bool:
    return _env_bool("WATHEFNI_PAYROLL_WAVE4", default=False)


def payroll_wave4_enabled_for_company(company_code: str | None) -> bool:
    if not payroll_wave4_enabled():
        return False
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE4_COMPANIES") or "WATHEFNI").strip()
    allowed = {p.strip().upper() for p in raw.split(",") if p.strip()}
    return (company_code or "").upper() in allowed


def payroll_wave4_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_ONLY")
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and (raw is None or str(raw).strip() == ""):
        return True
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _ON


def synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_KEY_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_KEY_MARKERS


def synthetic_phone_prefixes() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_PHONE_PREFIXES") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_PHONE_PREFIXES
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_PHONE_PREFIXES


def is_wave4_synthetic_employee(*, employee_key: str | None = None, phone: str | None = None) -> bool:
    key = str(employee_key or "")
    for marker in synthetic_key_markers():
        if marker and marker in key:
            return True
    phone_d = digits_phone(phone)
    for prefix in synthetic_phone_prefixes():
        if prefix and phone_d.startswith(prefix):
            return True
    return False


def honesty_payload() -> dict[str, Any]:
    return {
        "payroll_wave4_version": PAYROLL_WAVE4_VERSION,
        "journal_draft_schema": JOURNAL_DRAFT_SCHEMA,
        "bank_export_contract_schema": BANK_EXPORT_CONTRACT_SCHEMA,
        "payment_processing": "disabled",
        "posts_payment": False,
        "close_export_foundation": True,
        "journal_drafts": True,
        "journals": False,
        "bank_export_contract": True,
        "bank_files": False,
        "bank_connection": False,
        "wps": False,
        "ashal": False,
        "pifss": False,
        "eos": False,
        "ai_calculations": False,
        "native_results_authoritative": False,
        "external_payroll_authority": "external",
        "wave1_contracts_unchanged": True,
        "wave2a_flows_unchanged": True,
        "wave2b_flows_unchanged": True,
        "wave3_flows_unchanged": True,
        "synthetic_only": payroll_wave4_synthetic_only(),
    }


def freeze_invariants() -> dict[str, Any]:
    return {
        "payment_processing_hard_disabled": True,
        "closed_runs_immutable": True,
        "reopen_requires_dual_approval": True,
        "sod_approve_close_export": True,
        "journal_must_balance": True,
        "invalid_mappings_fail_closed": True,
        "bank_contract_validation_only": True,
        "no_real_bank_format": True,
        "no_wps_ashal": True,
        "no_pifss_eos": True,
        "no_ai": True,
        "native_non_authoritative": True,
        "external_authority_retained": True,
        "wave1_ddl_untouched": True,
        "wave2a_ddl_untouched": True,
        "wave2b_ddl_untouched": True,
        "wave3_ddl_untouched": True,
    }


def ensure_payroll_wave4_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    if not SCHEMA_SQL.strip():
        _SCHEMA_READY = True
        return
    lock_id = 770_900_005
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        cur.execute("SET LOCAL lock_timeout = '15s'")
        pyw1.ensure_payroll_wave1_schema(cur)
        w2a.ensure_payroll_wave2a_schema(cur)
        w2b.ensure_payroll_wave2b_schema(cur)
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
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def fingerprint_payload(payload: Any) -> str:
    raw = json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def money3(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def require_audit_reason(reason: str | None) -> dict[str, Any] | None:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    return None


def sod_holds_approve_and_export(permissions: list[str] | set[str] | None) -> bool:
    return pyw1.sod_holds_approve_and_export(permissions)


def _phones_equal(a: Any, b: Any) -> bool:
    da, db = digits_phone(a), digits_phone(b)
    return bool(da) and bool(db) and da == db


def _refuse_nonsynthetic_keys(employee_keys: list[str]) -> dict[str, Any] | None:
    if not payroll_wave4_synthetic_only():
        return None
    for key in employee_keys:
        if not is_wave4_synthetic_employee(employee_key=key):
            return {"ok": False, "error": "payroll_wave4_synthetic_only", "employee_key": key}
    return None


def _record_event(
    cur: Any,
    *,
    company_code: str,
    close_run_id: str | None,
    event_type: str,
    payload: dict[str, Any],
    actor_phone: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO payroll_close_run_events (close_run_id, company_code, event_type, payload, created_by_phone)
        VALUES (%s,%s,%s,%s::jsonb,%s)
        """,
        (
            close_run_id,
            (company_code or "").upper(),
            event_type,
            json.dumps(_json_safe(payload)),
            digits_phone(actor_phone),
        ),
    )


def get_close_run(cur: Any, *, company_code: str, close_run_id: str) -> dict[str, Any] | None:
    ensure_payroll_wave4_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_close_runs WHERE company_code=%s AND close_run_id=%s",
        ((company_code or "").upper(), close_run_id),
    )
    row = _row(cur)
    return _json_safe(row) if row else None


def list_close_runs(cur: Any, *, company_code: str, limit: int = 50) -> list[dict[str, Any]]:
    ensure_payroll_wave4_schema(cur)
    cur.execute(
        """
        SELECT close_run_id::text, source_kind, source_run_id::text, status, period_start, period_end,
               money_authority, authoritative_label, totals_earnings, totals_deductions, totals_net,
               employee_count, snapshot_fingerprint, snapshot_immutable, payment_processing,
               created_by_phone, approved_by_phone, closed_by_phone, reopen_pending, row_version,
               created_at
        FROM payroll_close_runs
        WHERE company_code=%s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        ((company_code or "").upper(), max(1, min(int(limit or 50), 200))),
    )
    return _json_safe(_rows(cur))


def list_close_events(
    cur: Any, *, company_code: str, close_run_id: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    ensure_payroll_wave4_schema(cur)
    cur.execute(
        """
        SELECT event_id::text, close_run_id::text, event_type, payload, created_by_phone, created_at
        FROM payroll_close_run_events
        WHERE company_code=%s AND (%s::uuid IS NULL OR close_run_id=%s::uuid)
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (
            (company_code or "").upper(),
            close_run_id,
            close_run_id,
            max(1, min(int(limit or 100), 500)),
        ),
    )
    return _json_safe(_rows(cur))


def _assert_mutable(run: dict[str, Any]) -> dict[str, Any] | None:
    if str(run.get("status")) == STATUS_CLOSED and bool(run.get("snapshot_immutable")):
        return {"ok": False, "error": "closed_run_immutable", "close_run_id": run.get("close_run_id")}
    return None


def _build_native_snapshot(cur: Any, *, company_code: str, preview_run_id: str) -> dict[str, Any]:
    run = w2b.get_preview_run(cur, company_code=company_code, preview_run_id=preview_run_id)
    if not run or not run.get("preview_run_id"):
        return {"ok": False, "error": "preview_run_not_found"}
    if str(run.get("status")) not in ("calculated", "superseded"):
        # allow calculated primarily
        if str(run.get("status")) != "calculated":
            return {"ok": False, "error": "preview_run_not_ready", "status": run.get("status")}
    employees = w2b.list_preview_employee_results(cur, company_code=company_code, preview_run_id=preview_run_id)
    lines = w2b.list_preview_lines(cur, company_code=company_code, preview_run_id=preview_run_id)
    keys = [str(e.get("employee_key") or "") for e in employees if e.get("employee_key")]
    refused = _refuse_nonsynthetic_keys(keys)
    if refused:
        return refused
    snapshot = {
        "source_kind": SOURCE_NATIVE,
        "source_run_id": str(run.get("preview_run_id")),
        "period_id": str(run.get("period_id") or "") or None,
        "period_start": run.get("period_start"),
        "period_end": run.get("period_end"),
        "money_authority": "preview_non_authoritative",
        "authoritative_label": "preview_non_authoritative",
        "currency": run.get("currency") or "KWD",
        "totals_earnings": money3(run.get("totals_earnings")),
        "totals_deductions": money3(run.get("totals_deductions")),
        "totals_net": money3(run.get("totals_net_preview")),
        "employee_count": int(run.get("employee_count") or len(employees)),
        "employees": employees,
        "lines": [
            {
                "employee_key": ln.get("employee_key"),
                "component_code": ln.get("code") or ln.get("component_code"),
                "component_kind": ln.get("line_kind") or ln.get("component_kind"),
                "amount": money3(ln.get("amount")),
                "currency": ln.get("currency") or "KWD",
            }
            for ln in lines
        ],
        "source_fingerprint": run.get("calculation_fingerprint") or run.get("input_fingerprint") or "",
    }
    return {"ok": True, "snapshot": snapshot}


def _build_external_snapshot(cur: Any, *, company_code: str, import_run_id: str) -> dict[str, Any]:
    run = w2a.get_import_run(cur, company_code=company_code, import_run_id=import_run_id)
    if not run or not run.get("import_run_id"):
        return {"ok": False, "error": "import_run_not_found"}
    lines = w2a.list_import_lines(cur, company_code=company_code, import_run_id=import_run_id)
    matched = [ln for ln in lines if str(ln.get("line_status") or "matched") == "matched"]
    keys = sorted({str(ln.get("employee_key") or "") for ln in matched if ln.get("employee_key")})
    refused = _refuse_nonsynthetic_keys(keys)
    if refused:
        return refused
    earnings = money3(0)
    deductions = money3(0)
    emp_nets: dict[str, Decimal] = {}
    norm_lines: list[dict[str, Any]] = []
    for ln in matched:
        amt = money3(ln.get("opaque_amount") or ln.get("amount") or 0)
        code = str(ln.get("component_code") or ln.get("code") or "COMP").upper()
        # External opaque amounts are mirrored components; treat known deduction codes as deductions.
        kind = "deduction" if code in {"DED", "DEDUCTION", "LOAN", "GOSI"} or code.endswith("_DED") else "earning"
        ek = str(ln.get("employee_key") or "")
        if kind == "deduction":
            deductions += abs(amt)
            emp_nets[ek] = emp_nets.get(ek, money3(0)) - abs(amt)
        else:
            earnings += abs(amt)
            emp_nets[ek] = emp_nets.get(ek, money3(0)) + abs(amt)
        norm_lines.append(
            {
                "employee_key": ek,
                "component_code": code,
                "component_kind": kind,
                "amount": amt,
                "currency": ln.get("currency") or "KWD",
            }
        )
    net = sum(emp_nets.values(), money3(0))
    period_start = None
    period_end = None
    period_id = None
    export_id = run.get("export_run_id")
    if export_id:
        cur.execute(
            """
            SELECT period_id, period_start, period_end
            FROM payroll_adapter_export_runs WHERE export_run_id=%s
            """,
            (export_id,),
        )
        er = _row(cur) or {}
        period_start = er.get("period_start")
        period_end = er.get("period_end")
        period_id = er.get("period_id")
    currency = "KWD"
    for ln in matched:
        if ln.get("currency"):
            currency = str(ln.get("currency") or "KWD")
            break
    if not period_start or not period_end:
        return {"ok": False, "error": "import_period_missing"}
    snapshot = {
        "source_kind": SOURCE_EXTERNAL,
        "source_run_id": str(run.get("import_run_id")),
        "period_id": str(period_id or "") or None,
        "period_start": period_start,
        "period_end": period_end,
        "money_authority": "external",
        "authoritative_label": "external",
        "currency": currency,
        "totals_earnings": earnings,
        "totals_deductions": deductions,
        "totals_net": net,
        "employee_count": len(keys),
        "employees": [{"employee_key": k, "net": emp_nets.get(k, money3(0))} for k in keys],
        "lines": norm_lines,
        "source_fingerprint": run.get("result_fingerprint") or fingerprint_payload(norm_lines),
    }
    return {"ok": True, "snapshot": snapshot}


def create_close_run(
    cur: Any,
    *,
    company_code: str,
    source_kind: str,
    source_run_id: str,
    actor_phone: str | None,
    reason: str | None,
    actor_permissions: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave4_schema(cur)
    company = (company_code or "").upper()
    kind = str(source_kind or "").strip().lower()
    if kind not in (SOURCE_NATIVE, SOURCE_EXTERNAL):
        return {"ok": False, "error": "invalid_source_kind"}
    if kind == SOURCE_NATIVE:
        built = _build_native_snapshot(cur, company_code=company, preview_run_id=source_run_id)
    else:
        built = _build_external_snapshot(cur, company_code=company, import_run_id=source_run_id)
    if not built.get("ok"):
        return built
    snap = built["snapshot"]
    # Idempotent active run for same source
    cur.execute(
        """
        SELECT * FROM payroll_close_runs
        WHERE company_code=%s AND source_kind=%s AND source_run_id=%s
          AND status IN ('draft','in_review','approved','closed')
        ORDER BY created_at DESC LIMIT 1
        """,
        (company, kind, source_run_id),
    )
    existing = _row(cur)
    if existing:
        return {
            "ok": True,
            "idempotent": True,
            "close_run": _json_safe(existing),
            **honesty_payload(),
        }
    src_fp = str(snap.get("source_fingerprint") or fingerprint_payload(snap))
    cur.execute(
        """
        INSERT INTO payroll_close_runs (
          company_code, period_id, period_start, period_end, source_kind, source_run_id,
          status, money_authority, authoritative_label, payment_processing, posts_payment,
          currency, totals_earnings, totals_deductions, totals_net, employee_count,
          source_fingerprint, created_by_phone, decision_note
        ) VALUES (
          %s,%s,%s,%s,%s,%s,
          'draft',%s,%s,'disabled',false,
          %s,%s,%s,%s,%s,
          %s,%s,%s
        ) RETURNING *
        """,
        (
            company,
            snap.get("period_id"),
            snap.get("period_start"),
            snap.get("period_end"),
            kind,
            source_run_id,
            snap.get("money_authority"),
            snap.get("authoritative_label"),
            snap.get("currency") or "KWD",
            money3(snap.get("totals_earnings")),
            money3(snap.get("totals_deductions")),
            money3(snap.get("totals_net")),
            int(snap.get("employee_count") or 0),
            src_fp,
            digits_phone(actor_phone),
            str(reason).strip(),
        ),
    )
    row = _row(cur) or {}
    _record_event(
        cur,
        company_code=company,
        close_run_id=str(row.get("close_run_id")),
        event_type="close_run_created",
        payload={"reason": reason, "source_kind": kind, "source_run_id": source_run_id},
        actor_phone=actor_phone,
    )
    return {"ok": True, "close_run": _json_safe(row), "permissions": list(actor_permissions or []), **honesty_payload()}


def submit_close_run_for_review(
    cur: Any,
    *,
    company_code: str,
    close_run_id: str,
    actor_phone: str | None,
    reason: str | None,
    expected_row_version: Any,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    run = get_close_run(cur, company_code=company_code, close_run_id=close_run_id)
    if not run:
        return {"ok": False, "error": "close_run_not_found"}
    immutable = _assert_mutable(run)
    if immutable:
        return immutable
    if str(run.get("status")) != STATUS_DRAFT:
        return {"ok": False, "error": "invalid_close_transition", "status": run.get("status")}
    conc = pyw1.require_concurrency(expected_row_version=expected_row_version, actual_row_version=run.get("row_version"))
    if conc:
        return conc
    company = (company_code or "").upper()
    cur.execute(
        """
        UPDATE payroll_close_runs
        SET status='in_review', submitted_by_phone=%s, submitted_at=now(),
            decision_note=%s, row_version=row_version+1, updated_at=now()
        WHERE company_code=%s AND close_run_id=%s AND status='draft' AND row_version=%s
        RETURNING *
        """,
        (digits_phone(actor_phone), str(reason).strip(), company, close_run_id, int(expected_row_version)),
    )
    updated = _row(cur)
    if not updated:
        return {"ok": False, "error": "stale_row_version_or_bad_status"}
    _record_event(
        cur,
        company_code=company,
        close_run_id=close_run_id,
        event_type="submitted_for_review",
        payload={"reason": reason},
        actor_phone=actor_phone,
    )
    return {"ok": True, "close_run": _json_safe(updated), **honesty_payload()}


def approve_close_run(
    cur: Any,
    *,
    company_code: str,
    close_run_id: str,
    actor_phone: str | None,
    reason: str | None,
    expected_row_version: Any,
    actor_permissions: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    perms = set(actor_permissions or [])
    if perms and "payroll.approve" not in perms:
        return {"ok": False, "error": "payroll_approve_required"}
    if sod_holds_approve_and_export(perms):
        return {"ok": False, "error": "sod_approve_export_conflict"}
    run = get_close_run(cur, company_code=company_code, close_run_id=close_run_id)
    if not run:
        return {"ok": False, "error": "close_run_not_found"}
    immutable = _assert_mutable(run)
    if immutable:
        return immutable
    if str(run.get("status")) != STATUS_IN_REVIEW:
        return {"ok": False, "error": "invalid_close_transition", "status": run.get("status")}
    if _phones_equal(actor_phone, run.get("created_by_phone")) or _phones_equal(actor_phone, run.get("submitted_by_phone")):
        return {"ok": False, "error": "self_approval_forbidden"}
    conc = pyw1.require_concurrency(expected_row_version=expected_row_version, actual_row_version=run.get("row_version"))
    if conc:
        return conc
    company = (company_code or "").upper()
    cur.execute(
        """
        UPDATE payroll_close_runs
        SET status='approved', approved_by_phone=%s, approved_at=now(),
            decision_note=%s, row_version=row_version+1, updated_at=now()
        WHERE company_code=%s AND close_run_id=%s AND status='in_review' AND row_version=%s
        RETURNING *
        """,
        (digits_phone(actor_phone), str(reason).strip(), company, close_run_id, int(expected_row_version)),
    )
    updated = _row(cur)
    if not updated:
        return {"ok": False, "error": "stale_row_version_or_bad_status"}
    _record_event(
        cur,
        company_code=company,
        close_run_id=close_run_id,
        event_type="approved",
        payload={"reason": reason},
        actor_phone=actor_phone,
    )
    return {"ok": True, "close_run": _json_safe(updated), **honesty_payload()}


def close_payroll_run(
    cur: Any,
    *,
    company_code: str,
    close_run_id: str,
    actor_phone: str | None,
    reason: str | None,
    expected_row_version: Any,
    actor_permissions: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Seal immutable snapshot. SOD: closer must hold approve (not export), ≠ creator/submitter."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    perms = set(actor_permissions or [])
    if perms and "payroll.approve" not in perms:
        return {"ok": False, "error": "payroll_approve_required"}
    if perms and "payroll.export" in perms:
        return {"ok": False, "error": "sod_close_export_conflict"}
    if sod_holds_approve_and_export(perms):
        return {"ok": False, "error": "sod_approve_export_conflict"}
    run = get_close_run(cur, company_code=company_code, close_run_id=close_run_id)
    if not run:
        return {"ok": False, "error": "close_run_not_found"}
    if str(run.get("status")) == STATUS_CLOSED:
        return {"ok": False, "error": "closed_run_immutable", "close_run_id": close_run_id}
    if str(run.get("status")) != STATUS_APPROVED:
        return {"ok": False, "error": "invalid_close_transition", "status": run.get("status")}
    if (
        _phones_equal(actor_phone, run.get("created_by_phone"))
        or _phones_equal(actor_phone, run.get("submitted_by_phone"))
    ):
        return {"ok": False, "error": "self_close_forbidden"}
    conc = pyw1.require_concurrency(expected_row_version=expected_row_version, actual_row_version=run.get("row_version"))
    if conc:
        return conc
    company = (company_code or "").upper()
    kind = str(run.get("source_kind"))
    source_run_id = str(run.get("source_run_id"))
    if kind == SOURCE_NATIVE:
        built = _build_native_snapshot(cur, company_code=company, preview_run_id=source_run_id)
    else:
        built = _build_external_snapshot(cur, company_code=company, import_run_id=source_run_id)
    if not built.get("ok"):
        return built
    snap = built["snapshot"]
    snap_fp = fingerprint_payload(snap)
    cur.execute(
        """
        UPDATE payroll_close_runs
        SET status='closed',
            snapshot_payload=%s::jsonb,
            snapshot_fingerprint=%s,
            snapshot_immutable=true,
            totals_earnings=%s, totals_deductions=%s, totals_net=%s,
            employee_count=%s,
            source_fingerprint=%s,
            closed_by_phone=%s, closed_at=now(),
            decision_note=%s, row_version=row_version+1, updated_at=now()
        WHERE company_code=%s AND close_run_id=%s AND status='approved' AND row_version=%s
        RETURNING *
        """,
        (
            json.dumps(_json_safe(snap)),
            snap_fp,
            money3(snap.get("totals_earnings")),
            money3(snap.get("totals_deductions")),
            money3(snap.get("totals_net")),
            int(snap.get("employee_count") or 0),
            str(snap.get("source_fingerprint") or ""),
            digits_phone(actor_phone),
            str(reason).strip(),
            company,
            close_run_id,
            int(expected_row_version),
        ),
    )
    updated = _row(cur)
    if not updated:
        return {"ok": False, "error": "stale_row_version_or_bad_status"}
    _record_event(
        cur,
        company_code=company,
        close_run_id=close_run_id,
        event_type="closed",
        payload={"reason": reason, "snapshot_fingerprint": snap_fp},
        actor_phone=actor_phone,
    )
    return {"ok": True, "close_run": _json_safe(updated), **honesty_payload()}


def mutate_closed_run_forbidden(cur: Any, *, company_code: str, close_run_id: str) -> dict[str, Any]:
    """Explicit fail-closed probe for immutability proofs."""
    run = get_close_run(cur, company_code=company_code, close_run_id=close_run_id)
    if not run:
        return {"ok": False, "error": "close_run_not_found"}
    if str(run.get("status")) != STATUS_CLOSED:
        return {"ok": False, "error": "not_closed"}
    return {"ok": False, "error": "closed_run_immutable", "close_run_id": close_run_id, **honesty_payload()}


def initiate_reopen(
    cur: Any,
    *,
    company_code: str,
    close_run_id: str,
    actor_phone: str | None,
    reason: str | None,
    actor_permissions: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    perms = set(actor_permissions or [])
    if perms and "payroll.approve" not in perms:
        return {"ok": False, "error": "payroll_approve_required"}
    if sod_holds_approve_and_export(perms):
        return {"ok": False, "error": "sod_approve_export_conflict"}
    run = get_close_run(cur, company_code=company_code, close_run_id=close_run_id)
    if not run:
        return {"ok": False, "error": "close_run_not_found"}
    if str(run.get("status")) != STATUS_CLOSED:
        return {"ok": False, "error": "invalid_reopen_state", "status": run.get("status")}
    company = (company_code or "").upper()
    actor = digits_phone(actor_phone)
    if not actor:
        return {"ok": False, "error": "actor_phone_required"}
    cur.execute(
        """
        UPDATE payroll_close_dual_control
        SET status='cancelled'
        WHERE company_code=%s AND close_run_id=%s AND status='pending_second'
        """,
        (company, close_run_id),
    )
    cur.execute(
        """
        INSERT INTO payroll_close_dual_control (
          company_code, close_run_id, action_kind, status, initiated_by_phone, payload
        ) VALUES (%s,%s,'reopen_closed_run','pending_second',%s,%s::jsonb)
        RETURNING *
        """,
        (company, close_run_id, actor, json.dumps(_json_safe({"reason": reason}))),
    )
    dual = _row(cur) or {}
    cur.execute(
        """
        UPDATE payroll_close_runs
        SET reopen_pending=true, row_version=row_version+1, updated_at=now()
        WHERE company_code=%s AND close_run_id=%s
        RETURNING *
        """,
        (company, close_run_id),
    )
    updated = _row(cur) or run
    _record_event(
        cur,
        company_code=company,
        close_run_id=close_run_id,
        event_type="reopen_initiated",
        payload={"reason": reason, "action_id": str(dual.get("action_id"))},
        actor_phone=actor_phone,
    )
    return {
        "ok": True,
        "dual_control": _json_safe(dual),
        "close_run": _json_safe(updated),
        "awaiting_second_approver": True,
        **honesty_payload(),
    }


def confirm_reopen(
    cur: Any,
    *,
    company_code: str,
    close_run_id: str,
    actor_phone: str | None,
    reason: str | None,
    dual_action_id: str | None = None,
    actor_permissions: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    perms = set(actor_permissions or [])
    if perms and "payroll.approve" not in perms:
        return {"ok": False, "error": "payroll_approve_required"}
    if sod_holds_approve_and_export(perms):
        return {"ok": False, "error": "sod_approve_export_conflict"}
    company = (company_code or "").upper()
    actor = digits_phone(actor_phone)
    if not actor:
        return {"ok": False, "error": "actor_phone_required"}
    if dual_action_id:
        cur.execute(
            """
            SELECT * FROM payroll_close_dual_control
            WHERE action_id=%s AND company_code=%s AND close_run_id=%s AND status='pending_second'
            LIMIT 1
            """,
            (dual_action_id, company, close_run_id),
        )
    else:
        cur.execute(
            """
            SELECT * FROM payroll_close_dual_control
            WHERE company_code=%s AND close_run_id=%s AND status='pending_second'
            ORDER BY created_at DESC LIMIT 1
            """,
            (company, close_run_id),
        )
    dual = _row(cur)
    if not dual:
        return {"ok": False, "error": "dual_control_not_found"}
    if _phones_equal(dual.get("initiated_by_phone"), actor):
        return {"ok": False, "error": "dual_control_same_actor"}
    run = get_close_run(cur, company_code=company, close_run_id=close_run_id)
    if not run or str(run.get("status")) != STATUS_CLOSED:
        return {"ok": False, "error": "invalid_reopen_state", "status": (run or {}).get("status")}
    # Preserve historical snapshot payload but mark reopened (no silent rewrite)
    cur.execute(
        """
        UPDATE payroll_close_dual_control
        SET status='confirmed', confirmed_by_phone=%s, confirmed_at=now()
        WHERE action_id=%s
        RETURNING *
        """,
        (actor, dual.get("action_id")),
    )
    dual_upd = _row(cur) or dual
    cur.execute(
        """
        UPDATE payroll_close_runs
        SET status='reopened',
            reopen_pending=false,
            snapshot_immutable=false,
            decision_note=%s,
            row_version=row_version+1,
            updated_at=now()
        WHERE company_code=%s AND close_run_id=%s AND status='closed'
        RETURNING *
        """,
        (str(reason).strip(), company, close_run_id),
    )
    updated = _row(cur)
    if not updated:
        return {"ok": False, "error": "reopen_failed"}
    _record_event(
        cur,
        company_code=company,
        close_run_id=close_run_id,
        event_type="reopened",
        payload={
            "reason": reason,
            "initiated_by": dual.get("initiated_by_phone"),
            "confirmed_by": actor,
            "prior_snapshot_fingerprint": run.get("snapshot_fingerprint"),
        },
        actor_phone=actor_phone,
    )
    return {"ok": True, "dual_control": _json_safe(dual_upd), "close_run": _json_safe(updated), **honesty_payload()}


# --------------------------------------------------------------------------- account mappings


def upsert_account_mapping(
    cur: Any,
    *,
    company_code: str,
    component_code: str,
    component_kind: str,
    account_code: str,
    journal_side: str,
    cost_centre: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave4_schema(cur)
    company = (company_code or "").upper()
    code = str(component_code or "").strip().upper()
    kind = str(component_kind or "").strip().lower()
    acct = str(account_code or "").strip()
    side = str(journal_side or "").strip().lower()
    if not code or kind not in ("earning", "allowance", "deduction", "employer_cost", "net_payable", "clearing"):
        return {"ok": False, "error": "invalid_mapping_component"}
    if side not in ("debit", "credit"):
        return {"ok": False, "error": "invalid_journal_side"}
    if not acct or len(acct) < 2:
        return {"ok": False, "error": "invalid_account_code"}
    cur.execute(
        """
        UPDATE payroll_account_mappings
        SET active=false, updated_at=now(), row_version=row_version+1
        WHERE company_code=%s AND component_code=%s AND active=true
        """,
        (company, code),
    )
    cur.execute(
        """
        INSERT INTO payroll_account_mappings (
          company_code, component_code, component_kind, account_code, cost_centre,
          journal_side, active, decision_note, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,true,%s,%s)
        RETURNING *
        """,
        (
            company,
            code,
            kind,
            acct,
            (str(cost_centre).strip() if cost_centre else None),
            side,
            str(reason).strip(),
            digits_phone(actor_phone),
        ),
    )
    row = _row(cur) or {}
    return {"ok": True, "mapping": _json_safe(row), **honesty_payload()}


def list_account_mappings(cur: Any, *, company_code: str, active_only: bool = True) -> list[dict[str, Any]]:
    ensure_payroll_wave4_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_account_mappings
        WHERE company_code=%s AND (%s=false OR active=true)
        ORDER BY component_code
        """,
        ((company_code or "").upper(), active_only),
    )
    return _json_safe(_rows(cur))


def _active_mapping_map(cur: Any, *, company_code: str) -> dict[str, dict[str, Any]]:
    rows = list_account_mappings(cur, company_code=company_code, active_only=True)
    return {str(r.get("component_code") or "").upper(): r for r in rows}


# --------------------------------------------------------------------------- journal drafts


def generate_journal_draft(
    cur: Any,
    *,
    company_code: str,
    close_run_id: str,
    actor_phone: str | None,
    reason: str | None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave4_schema(cur)
    company = (company_code or "").upper()
    run = get_close_run(cur, company_code=company, close_run_id=close_run_id)
    if not run:
        return {"ok": False, "error": "close_run_not_found"}
    if str(run.get("status")) != STATUS_CLOSED or not run.get("snapshot_immutable"):
        return {"ok": False, "error": "close_run_not_closed"}
    snap = run.get("snapshot_payload") or {}
    if isinstance(snap, str):
        snap = json.loads(snap)
    lines_in = list(snap.get("lines") or [])
    mappings = _active_mapping_map(cur, company_code=company)
    mapping_fp = fingerprint_payload(sorted(
        [
            {
                "component_code": m.get("component_code"),
                "account_code": m.get("account_code"),
                "cost_centre": m.get("cost_centre"),
                "journal_side": m.get("journal_side"),
            }
            for m in mappings.values()
        ],
        key=lambda x: str(x.get("component_code") or ""),
    ))

    # Aggregate by component
    by_code: dict[str, Decimal] = {}
    by_kind: dict[str, str] = {}
    for ln in lines_in:
        code = str(ln.get("component_code") or "").upper()
        if not code:
            continue
        by_code[code] = by_code.get(code, money3(0)) + money3(ln.get("amount"))
        by_kind[code] = str(ln.get("component_kind") or "earning").lower()

    missing: list[str] = []
    journal_lines: list[dict[str, Any]] = []
    total_debit = money3(0)
    total_credit = money3(0)
    line_no = 0
    for code, amount in sorted(by_code.items()):
        amt = abs(money3(amount))
        if amt == 0:
            continue
        mapping = mappings.get(code)
        if not mapping:
            missing.append(code)
            continue
        side = str(mapping.get("journal_side"))
        debit = amt if side == "debit" else money3(0)
        credit = amt if side == "credit" else money3(0)
        total_debit += debit
        total_credit += credit
        line_no += 1
        journal_lines.append(
            {
                "line_no": line_no,
                "account_code": mapping.get("account_code"),
                "cost_centre": mapping.get("cost_centre"),
                "component_code": code,
                "description": f"{code} ({by_kind.get(code)})",
                "debit": debit,
                "credit": credit,
                "currency": run.get("currency") or "KWD",
            }
        )

    if missing:
        return {
            "ok": False,
            "error": "invalid_mapping_fail_closed",
            "missing_component_codes": missing,
            **honesty_payload(),
        }

    # Ensure net payable balancing line if needed
    if total_debit != total_credit:
        net_map = mappings.get("NET_PAYABLE") or mappings.get("CLEARING")
        if not net_map:
            return {
                "ok": False,
                "error": "unbalanced_journal_missing_net_mapping",
                "total_debit": float(total_debit),
                "total_credit": float(total_credit),
                **honesty_payload(),
            }
        diff = abs(total_debit - total_credit)
        if total_debit > total_credit:
            debit, credit = money3(0), diff
            total_credit += diff
        else:
            debit, credit = diff, money3(0)
            total_debit += diff
        line_no += 1
        journal_lines.append(
            {
                "line_no": line_no,
                "account_code": net_map.get("account_code"),
                "cost_centre": net_map.get("cost_centre"),
                "component_code": str(net_map.get("component_code")),
                "description": "Net payable / clearing",
                "debit": debit,
                "credit": credit,
                "currency": run.get("currency") or "KWD",
            }
        )

    balanced = total_debit == total_credit
    if not balanced:
        return {
            "ok": False,
            "error": "journal_not_balanced",
            "total_debit": float(total_debit),
            "total_credit": float(total_credit),
            **honesty_payload(),
        }

    content = {
        "close_run_id": close_run_id,
        "lines": journal_lines,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "source_snapshot_fingerprint": run.get("snapshot_fingerprint"),
        "mapping_fingerprint": mapping_fp,
    }
    content_fp = fingerprint_payload(content)

    # Idempotent: same fingerprint active draft
    cur.execute(
        """
        SELECT * FROM payroll_journal_drafts
        WHERE company_code=%s AND close_run_id=%s AND content_fingerprint=%s
          AND status IN ('draft','validated','approved')
        ORDER BY created_at DESC LIMIT 1
        """,
        (company, close_run_id, content_fp),
    )
    existing = _row(cur)
    if existing:
        return {
            "ok": True,
            "idempotent": True,
            "journal_draft": _json_safe(existing),
            "lines": list_journal_lines(cur, company_code=company, journal_draft_id=str(existing.get("journal_draft_id"))),
            **honesty_payload(),
        }

    # Supersede prior drafts for same close run
    cur.execute(
        """
        UPDATE payroll_journal_drafts
        SET status='superseded', updated_at=now(), row_version=row_version+1
        WHERE company_code=%s AND close_run_id=%s AND status IN ('draft','validated')
        """,
        (company, close_run_id),
    )
    cur.execute(
        """
        INSERT INTO payroll_journal_drafts (
          company_code, close_run_id, status, currency, total_debit, total_credit, balanced,
          content_fingerprint, source_snapshot_fingerprint, mapping_fingerprint,
          posts_to_erp, payment_processing, decision_note, created_by_phone
        ) VALUES (
          %s,%s,'validated',%s,%s,%s,true,
          %s,%s,%s,
          false,'disabled',%s,%s
        ) RETURNING *
        """,
        (
            company,
            close_run_id,
            run.get("currency") or "KWD",
            total_debit,
            total_credit,
            content_fp,
            run.get("snapshot_fingerprint"),
            mapping_fp,
            str(reason).strip(),
            digits_phone(actor_phone),
        ),
    )
    draft = _row(cur) or {}
    jid = str(draft.get("journal_draft_id"))
    for jl in journal_lines:
        cur.execute(
            """
            INSERT INTO payroll_journal_lines (
              journal_draft_id, company_code, line_no, account_code, cost_centre,
              component_code, description, debit, credit, currency
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                jid,
                company,
                jl["line_no"],
                jl["account_code"],
                jl.get("cost_centre"),
                jl.get("component_code"),
                jl.get("description"),
                jl["debit"],
                jl["credit"],
                jl.get("currency") or "KWD",
            ),
        )
    _record_event(
        cur,
        company_code=company,
        close_run_id=close_run_id,
        event_type="journal_draft_generated",
        payload={"journal_draft_id": jid, "content_fingerprint": content_fp, "balanced": True},
        actor_phone=actor_phone,
    )
    return {
        "ok": True,
        "journal_draft": _json_safe(draft),
        "lines": journal_lines,
        **honesty_payload(),
    }


def list_journal_lines(cur: Any, *, company_code: str, journal_draft_id: str) -> list[dict[str, Any]]:
    ensure_payroll_wave4_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_journal_lines
        WHERE company_code=%s AND journal_draft_id=%s
        ORDER BY line_no
        """,
        ((company_code or "").upper(), journal_draft_id),
    )
    return _json_safe(_rows(cur))


def get_journal_draft(cur: Any, *, company_code: str, journal_draft_id: str) -> dict[str, Any] | None:
    ensure_payroll_wave4_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_journal_drafts WHERE company_code=%s AND journal_draft_id=%s",
        ((company_code or "").upper(), journal_draft_id),
    )
    row = _row(cur)
    return _json_safe(row) if row else None


# --------------------------------------------------------------------------- bank export contract (validation only)


def _validate_bank_contract_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if str(payload.get("schema") or "") != BANK_EXPORT_CONTRACT_SCHEMA:
        errors.append("invalid_schema")
    if str(payload.get("payment_processing") or "") != "disabled":
        errors.append("payment_processing_must_be_disabled")
    if payload.get("real_bank_format") is not False:
        errors.append("real_bank_format_forbidden")
    if payload.get("bank_connection") is not False:
        errors.append("bank_connection_forbidden")
    if payload.get("wps_submission") is not False:
        errors.append("wps_submission_forbidden")
    if payload.get("posts_payment") is not False:
        errors.append("posts_payment_forbidden")
    employees = payload.get("employees")
    if not isinstance(employees, list) or not employees:
        errors.append("employees_required")
        return errors
    for i, emp in enumerate(employees):
        if not isinstance(emp, dict):
            errors.append(f"employee_{i}_invalid")
            continue
        if not str(emp.get("employee_key") or "").strip():
            errors.append(f"employee_{i}_key_required")
        try:
            amt = money3(emp.get("net_amount"))
            if amt < 0:
                errors.append(f"employee_{i}_negative_net")
        except Exception:  # noqa: BLE001
            errors.append(f"employee_{i}_net_invalid")
        # IBAN is optional placeholder only — must not claim bank format
        iban = emp.get("iban_placeholder")
        if iban is not None and not isinstance(iban, str):
            errors.append(f"employee_{i}_iban_placeholder_invalid")
    return errors


def generate_bank_export_contract(
    cur: Any,
    *,
    company_code: str,
    close_run_id: str,
    actor_phone: str | None,
    reason: str | None,
    employee_iban_placeholders: dict[str, str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave4_schema(cur)
    company = (company_code or "").upper()
    run = get_close_run(cur, company_code=company, close_run_id=close_run_id)
    if not run:
        return {"ok": False, "error": "close_run_not_found"}
    if str(run.get("status")) != STATUS_CLOSED or not run.get("snapshot_immutable"):
        return {"ok": False, "error": "close_run_not_closed"}
    snap = run.get("snapshot_payload") or {}
    if isinstance(snap, str):
        snap = json.loads(snap)
    ibans = employee_iban_placeholders or {}
    employees = []
    for emp in snap.get("employees") or []:
        ek = str(emp.get("employee_key") or "")
        net = money3(
            emp.get("net")
            if emp.get("net") is not None
            else emp.get("totals_net_preview")
            if emp.get("totals_net_preview") is not None
            else emp.get("totals_net")
            if emp.get("totals_net") is not None
            else emp.get("net_pay")
            if emp.get("net_pay") is not None
            else 0
        )
        employees.append(
            {
                "employee_key": ek,
                "net_amount": float(net),
                "currency": run.get("currency") or "KWD",
                "iban_placeholder": ibans.get(ek),
            }
        )
    # If employees lack nets, derive from lines
    if employees and all(money3(e.get("net_amount")) == 0 for e in employees):
        nets: dict[str, Decimal] = {}
        for ln in snap.get("lines") or []:
            ek = str(ln.get("employee_key") or "")
            kind = str(ln.get("component_kind") or "").lower()
            amt = money3(ln.get("amount"))
            if "deduct" in kind:
                nets[ek] = nets.get(ek, money3(0)) - abs(amt)
            else:
                nets[ek] = nets.get(ek, money3(0)) + abs(amt)
        employees = [
            {
                "employee_key": ek,
                "net_amount": float(nets.get(ek, money3(0))),
                "currency": run.get("currency") or "KWD",
                "iban_placeholder": ibans.get(ek),
            }
            for ek in sorted(nets.keys())
        ]

    payload = {
        "schema": BANK_EXPORT_CONTRACT_SCHEMA,
        "company_code": company,
        "close_run_id": close_run_id,
        "period_start": run.get("period_start"),
        "period_end": run.get("period_end"),
        "currency": run.get("currency") or "KWD",
        "payment_processing": "disabled",
        "posts_payment": False,
        "real_bank_format": False,
        "bank_connection": False,
        "wps_submission": False,
        "money_authority": run.get("money_authority"),
        "employees": employees,
        "totals_net": float(money3(run.get("totals_net"))),
    }
    errors = _validate_bank_contract_payload(payload)
    content_fp = fingerprint_payload(payload)
    status = "validated" if not errors else "invalid"

    cur.execute(
        """
        SELECT * FROM payroll_bank_export_drafts
        WHERE company_code=%s AND close_run_id=%s AND content_fingerprint=%s
          AND status IN ('draft','validated','approved')
        ORDER BY created_at DESC LIMIT 1
        """,
        (company, close_run_id, content_fp),
    )
    existing = _row(cur)
    if existing and not errors:
        return {
            "ok": True,
            "idempotent": True,
            "bank_export": _json_safe(existing),
            **honesty_payload(),
        }

    if errors:
        cur.execute(
            """
            INSERT INTO payroll_bank_export_drafts (
              company_code, close_run_id, status, contract_schema, currency,
              employee_count, totals_net, content_fingerprint, source_snapshot_fingerprint,
              contract_payload, validation_errors, decision_note, created_by_phone
            ) VALUES (
              %s,%s,'invalid',%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s
            ) RETURNING *
            """,
            (
                company,
                close_run_id,
                BANK_EXPORT_CONTRACT_SCHEMA,
                run.get("currency") or "KWD",
                len(employees),
                money3(run.get("totals_net")),
                content_fp,
                run.get("snapshot_fingerprint"),
                json.dumps(_json_safe(payload)),
                json.dumps(errors),
                str(reason).strip(),
                digits_phone(actor_phone),
            ),
        )
        row = _row(cur) or {}
        return {
            "ok": False,
            "error": "bank_contract_validation_failed",
            "validation_errors": errors,
            "bank_export": _json_safe(row),
            **honesty_payload(),
        }

    cur.execute(
        """
        UPDATE payroll_bank_export_drafts
        SET status='superseded', updated_at=now(), row_version=row_version+1
        WHERE company_code=%s AND close_run_id=%s AND status IN ('draft','validated')
        """,
        (company, close_run_id),
    )
    cur.execute(
        """
        INSERT INTO payroll_bank_export_drafts (
          company_code, close_run_id, status, contract_schema, currency,
          employee_count, totals_net, content_fingerprint, source_snapshot_fingerprint,
          contract_payload, validation_errors, decision_note, created_by_phone
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'[]'::jsonb,%s,%s
        ) RETURNING *
        """,
        (
            company,
            close_run_id,
            status,
            BANK_EXPORT_CONTRACT_SCHEMA,
            run.get("currency") or "KWD",
            len(employees),
            money3(run.get("totals_net")),
            content_fp,
            run.get("snapshot_fingerprint"),
            json.dumps(_json_safe(payload)),
            str(reason).strip(),
            digits_phone(actor_phone),
        ),
    )
    row = _row(cur) or {}
    _record_event(
        cur,
        company_code=company,
        close_run_id=close_run_id,
        event_type="bank_contract_validated",
        payload={"bank_export_id": str(row.get("bank_export_id")), "content_fingerprint": content_fp},
        actor_phone=actor_phone,
    )
    return {"ok": True, "bank_export": _json_safe(row), **honesty_payload()}


def get_bank_export(cur: Any, *, company_code: str, bank_export_id: str) -> dict[str, Any] | None:
    ensure_payroll_wave4_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_bank_export_drafts WHERE company_code=%s AND bank_export_id=%s",
        ((company_code or "").upper(), bank_export_id),
    )
    row = _row(cur)
    return _json_safe(row) if row else None


# --------------------------------------------------------------------------- finance export history / approvals / recon


def record_finance_export(
    cur: Any,
    *,
    company_code: str,
    close_run_id: str,
    export_kind: str,
    artifact_id: str,
    actor_phone: str | None,
    reason: str | None,
    actor_permissions: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Record export history. Requires payroll.export; SOD vs approve/close actors."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    perms = set(actor_permissions or [])
    if perms and "payroll.export" not in perms:
        return {"ok": False, "error": "payroll_export_required"}
    if perms and "payroll.approve" in perms:
        return {"ok": False, "error": "sod_approve_export_conflict"}
    ensure_payroll_wave4_schema(cur)
    company = (company_code or "").upper()
    kind = str(export_kind or "").strip().lower()
    if kind not in ("journal_draft", "bank_contract"):
        return {"ok": False, "error": "invalid_export_kind"}
    run = get_close_run(cur, company_code=company, close_run_id=close_run_id)
    if not run:
        return {"ok": False, "error": "close_run_not_found"}
    if str(run.get("status")) != STATUS_CLOSED:
        return {"ok": False, "error": "close_run_not_closed"}
    # SOD: exporter ≠ closer / approver
    if _phones_equal(actor_phone, run.get("closed_by_phone")) or _phones_equal(actor_phone, run.get("approved_by_phone")):
        return {"ok": False, "error": "sod_close_export_same_actor"}

    if kind == "journal_draft":
        art = get_journal_draft(cur, company_code=company, journal_draft_id=artifact_id)
        if not art:
            return {"ok": False, "error": "journal_draft_not_found"}
        content_fp = str(art.get("content_fingerprint") or "")
        src_fp = str(art.get("source_snapshot_fingerprint") or "")
        if src_fp != str(run.get("snapshot_fingerprint") or ""):
            recon = "drift"
            status = "quarantined"
            drift = {"error": "fingerprint_drift", "artifact_fp": src_fp, "run_fp": run.get("snapshot_fingerprint")}
        else:
            recon = "unmatched"
            status = "recorded"
            drift = {}
    else:
        art = get_bank_export(cur, company_code=company, bank_export_id=artifact_id)
        if not art:
            return {"ok": False, "error": "bank_export_not_found"}
        if str(art.get("status")) not in ("validated", "approved"):
            return {"ok": False, "error": "bank_export_not_validated", "status": art.get("status")}
        content_fp = str(art.get("content_fingerprint") or "")
        src_fp = str(art.get("source_snapshot_fingerprint") or "")
        if src_fp != str(run.get("snapshot_fingerprint") or ""):
            recon = "drift"
            status = "quarantined"
            drift = {"error": "fingerprint_drift", "artifact_fp": src_fp, "run_fp": run.get("snapshot_fingerprint")}
        else:
            recon = "unmatched"
            status = "recorded"
            drift = {}

    # Idempotent same fingerprint
    cur.execute(
        """
        SELECT * FROM payroll_finance_exports
        WHERE company_code=%s AND export_kind=%s AND content_fingerprint=%s
          AND status IN ('recorded','approved')
        ORDER BY created_at DESC LIMIT 1
        """,
        (company, kind, content_fp),
    )
    existing = _row(cur)
    if existing and status != "quarantined":
        return {
            "ok": True,
            "idempotent": True,
            "finance_export": _json_safe(existing),
            **honesty_payload(),
        }

    cur.execute(
        """
        INSERT INTO payroll_finance_exports (
          company_code, close_run_id, export_kind, artifact_id, status,
          content_fingerprint, source_snapshot_fingerprint, reconciliation_status,
          exported_by_phone, decision_note, drift_detail
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        RETURNING *
        """,
        (
            company,
            close_run_id,
            kind,
            artifact_id,
            status,
            content_fp,
            run.get("snapshot_fingerprint"),
            recon,
            digits_phone(actor_phone),
            str(reason).strip(),
            json.dumps(_json_safe(drift)),
        ),
    )
    row = _row(cur) or {}
    _record_event(
        cur,
        company_code=company,
        close_run_id=close_run_id,
        event_type="finance_export_recorded",
        payload={
            "finance_export_id": str(row.get("finance_export_id")),
            "export_kind": kind,
            "reconciliation_status": recon,
            "status": status,
        },
        actor_phone=actor_phone,
    )
    if status == "quarantined":
        return {
            "ok": False,
            "error": "fingerprint_drift",
            "finance_export": _json_safe(row),
            **honesty_payload(),
        }
    return {"ok": True, "finance_export": _json_safe(row), **honesty_payload()}


def approve_finance_export(
    cur: Any,
    *,
    company_code: str,
    finance_export_id: str,
    actor_phone: str | None,
    reason: str | None,
    actor_permissions: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    perms = set(actor_permissions or [])
    # Export approval still uses export permission (not approve) to preserve SOD
    if perms and "payroll.export" not in perms:
        return {"ok": False, "error": "payroll_export_required"}
    if perms and "payroll.approve" in perms:
        return {"ok": False, "error": "sod_approve_export_conflict"}
    ensure_payroll_wave4_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        "SELECT * FROM payroll_finance_exports WHERE company_code=%s AND finance_export_id=%s",
        (company, finance_export_id),
    )
    row = _row(cur)
    if not row:
        return {"ok": False, "error": "finance_export_not_found"}
    if str(row.get("status")) == "quarantined" or str(row.get("reconciliation_status")) == "drift":
        return {"ok": False, "error": "fingerprint_drift"}
    if str(row.get("status")) not in ("recorded",):
        return {"ok": False, "error": "invalid_export_status", "status": row.get("status")}
    if _phones_equal(actor_phone, row.get("exported_by_phone")):
        return {"ok": False, "error": "self_approval_forbidden"}
    cur.execute(
        """
        UPDATE payroll_finance_exports
        SET status='approved', approved_by_phone=%s, approved_at=now(),
            reconciliation_status='matched', decision_note=%s, updated_at=now()
        WHERE company_code=%s AND finance_export_id=%s AND status='recorded'
        RETURNING *
        """,
        (digits_phone(actor_phone), str(reason).strip(), company, finance_export_id),
    )
    updated = _row(cur)
    if not updated:
        return {"ok": False, "error": "approve_failed"}
    return {"ok": True, "finance_export": _json_safe(updated), **honesty_payload()}


def list_finance_exports(cur: Any, *, company_code: str, close_run_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    ensure_payroll_wave4_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_finance_exports
        WHERE company_code=%s AND (%s::uuid IS NULL OR close_run_id=%s::uuid)
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (
            (company_code or "").upper(),
            close_run_id,
            close_run_id,
            max(1, min(int(limit or 50), 200)),
        ),
    )
    return _json_safe(_rows(cur))


def detect_export_fingerprint_drift(
    cur: Any,
    *,
    company_code: str,
    close_run_id: str,
    export_kind: str,
    artifact_id: str,
) -> dict[str, Any]:
    """Compare artifact source fingerprint to current closed-run snapshot fingerprint."""
    run = get_close_run(cur, company_code=company_code, close_run_id=close_run_id)
    if not run:
        return {"ok": False, "error": "close_run_not_found"}
    kind = str(export_kind or "").strip().lower()
    if kind == "journal_draft":
        art = get_journal_draft(cur, company_code=company_code, journal_draft_id=artifact_id)
    elif kind == "bank_contract":
        art = get_bank_export(cur, company_code=company_code, bank_export_id=artifact_id)
    else:
        return {"ok": False, "error": "invalid_export_kind"}
    if not art:
        return {"ok": False, "error": "artifact_not_found"}
    src_fp = str(art.get("source_snapshot_fingerprint") or "")
    run_fp = str(run.get("snapshot_fingerprint") or "")
    drifted = bool(src_fp and run_fp and src_fp != run_fp)
    return {
        "ok": True,
        "drifted": drifted,
        "artifact_source_fingerprint": src_fp,
        "run_snapshot_fingerprint": run_fp,
        "reconciliation_status": "drift" if drifted else "matched",
        **honesty_payload(),
    }


def workspace_bootstrap(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_payroll_wave4_schema(cur)
    return {
        "ok": True,
        "close_runs": list_close_runs(cur, company_code=company_code, limit=40),
        "account_mappings": list_account_mappings(cur, company_code=company_code, active_only=True),
        "finance_exports": list_finance_exports(cur, company_code=company_code, limit=40),
        "preview_runs": w2b.list_preview_runs(cur, company_code=company_code, limit=20),
        "import_runs": w2a.list_import_runs(cur, company_code=company_code, limit=20),
        **honesty_payload(),
    }
