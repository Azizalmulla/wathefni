"""Payroll Authority P1 — Kuwait-first canonical sealed money snapshot.

Authority modes:
  Mode A (wathefni) — foundation only in P1; seal path refuses native preview.
  Mode B (external) — import → seal_from_external_import → payslip/PDF consume sealed.

Rules (frozen):
  preview = preview forever (Wave 2B stays preview_non_authoritative)
  money_authority ∈ {wathefni, external} on sealed snapshots only
  sealed monetary values never silently mutate
  corrections = replace (new sealed version) preserving prior history
  one current sealed snapshot per (company, employee, period)
  period close ≠ money seal
  payment_processing=disabled; no invented payment_date
  SYNTHETIC_ONLY remains
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import payroll_authority_wave1 as pyw1
import payroll_external_adapter_wave2a as w2a
import payroll_payslip_wave3 as w3

PAYROLL_AUTHORITY_P1_VERSION = "1.0.0"
AUTHORITY_SNAPSHOT_SCHEMA = "wathefni.payroll_authority_snapshot.v1"
MONEY_WATHEFNI = "wathefni"
MONEY_EXTERNAL = "external"
STATUS_SEALED = "sealed"
STATUS_REPLACED = "replaced"
STATUS_REVOKED = "revoked"
SOURCE_EXTERNAL = "external_import"
SOURCE_NATIVE_AUTH = "native_authoritative"
SOURCE_NATIVE_REFUSED = "native_preview_refused"
MODE_B = "mode_b_external"
MODE_A = "mode_a_wathefni"
MODE_A_REFUSED = "mode_a_foundation_refused"

SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_authority_snapshot_p1_v1.sql"
SCHEMA_SQL = SCHEMA_SQL_PATH.read_text(encoding="utf-8") if SCHEMA_SQL_PATH.exists() else ""

_SCHEMA_READY = False
DEFAULT_SYNTHETIC_KEY_MARKERS = ("PYW2A", "PYW2A-SYNTH|", "PYW1", "PYW1-SYNTH|", "PYW3", "PYW3-SYNTH|", "PYAUTH", "PYP1")
DEFAULT_SYNTHETIC_PHONE_PREFIXES = ("965539", "965540", "965541")
_ON = ("1", "true", "yes", "on")


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _ON


def payroll_authority_p1_enabled() -> bool:
    return _env_bool("WATHEFNI_PAYROLL_AUTHORITY_P1", default=True)


def payroll_authority_p1_enabled_for_company(company_code: str | None) -> bool:
    if not payroll_authority_p1_enabled():
        return False
    raw = str(os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P1_COMPANIES") or "WATHEFNI").strip()
    allowed = {p.strip().upper() for p in raw.split(",") if p.strip()}
    return (company_code or "").upper() in allowed


def payroll_authority_p1_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P1_SYNTHETIC_ONLY")
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and (raw is None or str(raw).strip() == ""):
        return True
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _ON


def synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P1_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_KEY_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_KEY_MARKERS


def is_p1_synthetic_employee(*, employee_key: str | None = None) -> bool:
    key = str(employee_key or "")
    for marker in synthetic_key_markers():
        if marker and marker in key:
            return True
    # Reuse wave3 markers when present
    try:
        return bool(w3.is_wave3_synthetic_employee(employee_key=key))
    except Exception:
        return False


def honesty_payload() -> dict[str, Any]:
    return {
        "payroll_authority_p1_version": PAYROLL_AUTHORITY_P1_VERSION,
        "authority_snapshot_schema": AUTHORITY_SNAPSHOT_SCHEMA,
        "money_authority_modes": [MONEY_WATHEFNI, MONEY_EXTERNAL],
        "mode_a_wathefni_seal_unlocked": False,
        "mode_b_external_seal_unlocked": True,
        "native_preview_authoritative": False,
        "preview_remains_preview": True,
        "period_close_is_money_seal": False,
        "payment_processing": "disabled",
        "posts_payment": False,
        "payment_date_invented": False,
        "statutory_formulas_implemented": False,
        "counsel_gated_statutory": True,
        "synthetic_only": payroll_authority_p1_synthetic_only(),
        "kuwait_first": True,
        "gcc_extensible": True,
    }


def freeze_invariants() -> dict[str, Any]:
    return {
        "sealed_monetary_values_immutable": True,
        "corrections_create_replacement_version": True,
        "history_never_deleted": True,
        "one_current_sealed_per_employee_period": True,
        "seal_idempotent": True,
        "stale_source_cannot_overwrite": True,
        "period_close_alone_no_money_authority": True,
        "native_preview_cannot_seal_as_wathefni": True,
        "official_pdf_requires_sealed_external": True,
    }


def ensure_payroll_authority_snapshot_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    if not SCHEMA_SQL.strip():
        _SCHEMA_READY = True
        return
    lock_id = 770_900_011
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        cur.execute("SET LOCAL lock_timeout = '15s'")
        pyw1.ensure_payroll_wave1_schema(cur)
        w2a.ensure_payroll_wave2a_schema(cur)
        w3.ensure_payroll_wave3_schema(cur)
        cur.execute(SCHEMA_SQL)
        _SCHEMA_READY = True
    finally:
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
        except Exception:
            pass


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


def require_audit_reason(reason: str | None) -> dict[str, Any] | None:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    return None


def _refuse_nonsynthetic(employee_key: str) -> dict[str, Any] | None:
    if payroll_authority_p1_synthetic_only() and not is_p1_synthetic_employee(employee_key=employee_key):
        return {"ok": False, "error": "payroll_authority_p1_synthetic_only", "employee_key": employee_key}
    return None


def _record_event(
    cur: Any,
    *,
    company_code: str,
    authority_snapshot_id: str | None,
    event_type: str,
    payload: dict[str, Any],
    actor_phone: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO payroll_authority_snapshot_events
          (authority_snapshot_id, company_code, event_type, payload, created_by_phone)
        VALUES (%s,%s,%s,%s::jsonb,%s)
        """,
        (
            authority_snapshot_id,
            (company_code or "").upper(),
            event_type,
            json.dumps(_json_safe(payload)),
            digits_phone(actor_phone),
        ),
    )


def map_external_component_code(code: str) -> dict[str, Any]:
    """Map opaque external codes into catalog-compatible identity without inventing statutory meaning."""
    raw = str(code or "").strip() or "EXTERNAL.OPAQUE"
    upper = raw.upper()
    catalog = "EXTERNAL.OPAQUE"
    category = "external_opaque"
    line_kind_hint = None
    if upper in ("BASIC", "BASIC_SALARY", "BASE"):
        catalog = "BASIC"
        category = "earning_basic"
        line_kind_hint = "earning"
    elif upper.startswith("ALLOWANCE") or upper in ("TRANSPORT", "HOUSING"):
        catalog = "ALLOWANCE.TRANSPORT" if "TRANSPORT" in upper else (
            "ALLOWANCE.HOUSING" if "HOUSING" in upper else "ALLOWANCE.ONE_OFF"
        )
        category = "earning_allowance_recurring"
        line_kind_hint = "earning"
    elif upper.startswith("DEDUCTION"):
        catalog = "DEDUCTION.RECURRING"
        category = "deduction_recurring"
        line_kind_hint = "deduction"
    return {
        "component_code": raw,
        "catalog_code": catalog,
        "category": category,
        "line_kind_hint": line_kind_hint,
        "label_en": raw,
        "label_ar": raw,
        "source": "external_import",
        "policy_version": None,
        "taxable_treatment": None,
        "statutory_treatment": None,
    }


def _build_external_seal_payload(
    cur: Any,
    *,
    company_code: str,
    import_run_id: str,
    employee_key: str,
) -> dict[str, Any]:
    imp = w2a.get_import_run(cur, company_code=company_code, import_run_id=import_run_id)
    if not imp:
        return {"ok": False, "error": "import_run_not_found"}
    if str(imp.get("status") or "") in ("rolled_back",):
        return {"ok": False, "error": "import_run_not_active", "status": imp.get("status")}
    lines = w2a.list_import_lines(cur, company_code=company_code, import_run_id=import_run_id)
    emp_lines = [
        ln
        for ln in lines
        if str(ln.get("employee_key") or "") == employee_key and str(ln.get("line_status") or "") == "matched"
    ]
    if not emp_lines:
        return {"ok": False, "error": "employee_not_in_import_run"}

    slip_lines: list[dict[str, Any]] = []
    tot_earn = Decimal("0")
    tot_ded = Decimal("0")
    for i, ln in enumerate(emp_lines):
        code = str(ln.get("component_code") or f"C{i}")
        amount = Decimal(str(ln.get("opaque_amount") or 0))
        mapped = map_external_component_code(code)
        if amount < 0:
            line_kind = "deduction"
            tot_ded += abs(amount)
            display_amount = abs(amount)
        else:
            line_kind = mapped.get("line_kind_hint") or "earning"
            if line_kind == "deduction":
                tot_ded += amount
            else:
                tot_earn += amount
            display_amount = amount
        slip_lines.append(
            {
                "component_code": mapped["component_code"],
                "catalog_code": mapped["catalog_code"],
                "line_kind": line_kind,
                "category": mapped["category"],
                "label_en": mapped["label_en"],
                "label_ar": mapped["label_ar"],
                "amount": float(display_amount),
                "currency": str(ln.get("currency") or "KWD"),
                "source": "external_import",
                "policy_version": None,
                "taxable_treatment": None,
                "statutory_treatment": None,
                "sort_order": i,
                "provenance": {
                    "import_line_status": ln.get("line_status"),
                    "opaque_amount": float(amount),
                    "import_run_id": import_run_id,
                },
            }
        )

    period_start = str(imp.get("period_start") or "")[:10]
    period_end = str(imp.get("period_end") or "")[:10]
    if not period_start or not period_end:
        export_id = str(imp.get("export_run_id") or "")
        if export_id:
            exp = w2a.get_export_run(cur, company_code=company_code, export_run_id=export_id)
            if exp:
                period_start = str(exp.get("period_start") or period_start)[:10]
                period_end = str(exp.get("period_end") or period_end)[:10]
    if not period_start or not period_end:
        return {"ok": False, "error": "import_period_missing"}

    gross = tot_earn
    net = tot_earn - tot_ded
    source_fp = str(imp.get("result_fingerprint") or "")
    if not source_fp:
        return {"ok": False, "error": "import_source_fingerprint_missing"}

    content = {
        "schema": AUTHORITY_SNAPSHOT_SCHEMA,
        "company_code": (company_code or "").upper(),
        "employee_key": employee_key,
        "period_start": period_start,
        "period_end": period_end,
        "currency": "KWD",
        "money_authority": MONEY_EXTERNAL,
        "source_kind": SOURCE_EXTERNAL,
        "source_mode": MODE_B,
        "import_run_id": import_run_id,
        "external_run_id": imp.get("external_run_id"),
        "source_fingerprint": source_fp,
        "calculation_policy_version": None,
        "compensation_source": "external_import",
        "compensation_version": str(imp.get("external_run_id") or import_run_id),
        "totals_earnings": float(tot_earn),
        "totals_deductions": float(tot_ded),
        "totals_gross": float(gross),
        "totals_net": float(net),
        "lines": slip_lines,
        "payment_processing": "disabled",
        "posts_payment": False,
        "authoritative_in_wathefni": False,
        "wathefni_calculated": False,
    }
    content_fp = fingerprint_payload(content)
    return {
        "ok": True,
        "content": content,
        "content_fingerprint": content_fp,
        "source_fingerprint": source_fp,
        "import_run": imp,
        "period_start": period_start,
        "period_end": period_end,
        "lines": slip_lines,
        "totals": {
            "earnings": float(tot_earn),
            "deductions": float(tot_ded),
            "gross": float(gross),
            "net": float(net),
        },
    }


def get_current_sealed_snapshot(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    period_start: str | date,
    period_end: str | date,
) -> dict[str, Any] | None:
    ensure_payroll_authority_snapshot_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_authority_snapshots
        WHERE company_code=%s AND employee_key=%s
          AND period_start=%s AND period_end=%s AND status='sealed'
        ORDER BY sealed_at DESC LIMIT 1
        """,
        ((company_code or "").upper(), employee_key, str(period_start)[:10], str(period_end)[:10]),
    )
    return _row(cur)


def get_sealed_snapshot_by_id(
    cur: Any, *, company_code: str, authority_snapshot_id: str
) -> dict[str, Any] | None:
    ensure_payroll_authority_snapshot_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_authority_snapshots
        WHERE company_code=%s AND authority_snapshot_id=%s
        """,
        ((company_code or "").upper(), authority_snapshot_id),
    )
    return _row(cur)


def get_sealed_for_import_employee(
    cur: Any, *, company_code: str, import_run_id: str, employee_key: str
) -> dict[str, Any] | None:
    ensure_payroll_authority_snapshot_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_authority_snapshots
        WHERE company_code=%s AND import_run_id=%s AND employee_key=%s AND status='sealed'
        ORDER BY sealed_at DESC LIMIT 1
        """,
        ((company_code or "").upper(), import_run_id, employee_key),
    )
    return _row(cur)


def list_authority_snapshot_lines(
    cur: Any, *, company_code: str, authority_snapshot_id: str
) -> list[dict[str, Any]]:
    ensure_payroll_authority_snapshot_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_authority_snapshot_lines
        WHERE company_code=%s AND authority_snapshot_id=%s
        ORDER BY sort_order ASC, created_at ASC
        """,
        ((company_code or "").upper(), authority_snapshot_id),
    )
    return _rows(cur)


def list_authority_snapshot_history(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    period_start: str | date | None = None,
    period_end: str | date | None = None,
) -> list[dict[str, Any]]:
    ensure_payroll_authority_snapshot_schema(cur)
    company = (company_code or "").upper()
    if period_start and period_end:
        cur.execute(
            """
            SELECT * FROM payroll_authority_snapshots
            WHERE company_code=%s AND employee_key=%s
              AND period_start=%s AND period_end=%s
            ORDER BY sealed_at DESC, created_at DESC
            """,
            (company, employee_key, str(period_start)[:10], str(period_end)[:10]),
        )
    else:
        cur.execute(
            """
            SELECT * FROM payroll_authority_snapshots
            WHERE company_code=%s AND employee_key=%s
            ORDER BY sealed_at DESC, created_at DESC
            """,
            (company, employee_key),
        )
    return _rows(cur)


def list_authority_snapshot_events(
    cur: Any, *, company_code: str, limit: int = 50
) -> list[dict[str, Any]]:
    ensure_payroll_authority_snapshot_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_authority_snapshot_events
        WHERE company_code=%s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        ((company_code or "").upper(), max(1, min(int(limit), 500))),
    )
    return _rows(cur)


def _insert_sealed_snapshot(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    built: dict[str, Any],
    actor_phone: str | None,
    reason: str,
    replaces_snapshot_id: str | None = None,
    approval_actor_chain: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    company = (company_code or "").upper()
    content = built["content"]
    lines = built["lines"]
    totals = built["totals"]
    snap_id = str(uuid.uuid4())
    chain = approval_actor_chain or [
        {
            "actor_phone": digits_phone(actor_phone),
            "action": "seal",
            "reason": reason,
            "at": datetime.utcnow().isoformat() + "Z",
        }
    ]
    provenance = {
        "import_run_id": content.get("import_run_id"),
        "external_run_id": content.get("external_run_id"),
        "source_fingerprint": built["source_fingerprint"],
        "money_authority": MONEY_EXTERNAL,
        "sealed_from": "seal_from_external_import",
        "period_close_required": False,
        "wathefni_calculated": False,
    }
    cur.execute(
        """
        INSERT INTO payroll_authority_snapshots (
          authority_snapshot_id, company_code, employee_key, period_id,
          period_start, period_end, currency, money_authority, source_kind, source_mode,
          status, import_run_id, preview_run_id, close_run_id, external_run_id,
          source_fingerprint, content_fingerprint, calculation_policy_version,
          compensation_source, compensation_version,
          totals_earnings, totals_deductions, totals_gross, totals_net,
          payment_processing, posts_payment, snapshot_payload, provenance,
          replaces_snapshot_id, sealed_by_phone, finalized_by_phone,
          approval_actor_chain, decision_note
        ) VALUES (
          %s,%s,%s,NULL,
          %s,%s,'KWD',%s,%s,%s,
          'sealed',%s,NULL,NULL,%s,
          %s,%s,NULL,
          %s,%s,
          %s,%s,%s,%s,
          'disabled',false,%s::jsonb,%s::jsonb,
          %s,%s,%s,
          %s::jsonb,%s
        )
        RETURNING *
        """,
        (
            snap_id,
            company,
            employee_key,
            built["period_start"],
            built["period_end"],
            MONEY_EXTERNAL,
            SOURCE_EXTERNAL,
            MODE_B,
            content.get("import_run_id"),
            content.get("external_run_id"),
            built["source_fingerprint"],
            built["content_fingerprint"],
            content.get("compensation_source"),
            content.get("compensation_version"),
            totals["earnings"],
            totals["deductions"],
            totals["gross"],
            totals["net"],
            json.dumps(_json_safe(content)),
            json.dumps(_json_safe(provenance)),
            replaces_snapshot_id,
            digits_phone(actor_phone),
            digits_phone(actor_phone),
            json.dumps(_json_safe(chain)),
            reason,
        ),
    )
    row = _row(cur)
    for ln in lines:
        cur.execute(
            """
            INSERT INTO payroll_authority_snapshot_lines (
              authority_snapshot_id, company_code, employee_key,
              component_code, catalog_code, line_kind, category,
              label_en, label_ar, amount, currency, source, policy_version,
              taxable_treatment, statutory_treatment, sort_order, provenance
            ) VALUES (
              %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb
            )
            """,
            (
                snap_id,
                company,
                employee_key,
                ln["component_code"],
                ln.get("catalog_code"),
                ln["line_kind"],
                ln.get("category"),
                ln.get("label_en"),
                ln.get("label_ar"),
                ln["amount"],
                ln.get("currency") or "KWD",
                ln.get("source") or "external_import",
                ln.get("policy_version"),
                ln.get("taxable_treatment"),
                ln.get("statutory_treatment"),
                int(ln.get("sort_order") or 0),
                json.dumps(_json_safe(ln.get("provenance") or {})),
            ),
        )
    _record_event(
        cur,
        company_code=company,
        authority_snapshot_id=snap_id,
        event_type="authority_snapshot_sealed",
        payload={
            "money_authority": MONEY_EXTERNAL,
            "content_fingerprint": built["content_fingerprint"],
            "source_fingerprint": built["source_fingerprint"],
            "replaces_snapshot_id": replaces_snapshot_id,
            "reason": reason,
        },
        actor_phone=actor_phone,
    )
    return row or {}


def seal_from_external_import(
    cur: Any,
    *,
    company_code: str,
    import_run_id: str,
    employee_key: str,
    actor_phone: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Mode B: seal authoritative external import result into immutable snapshot."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    if not payroll_authority_p1_enabled_for_company(company_code):
        return {"ok": False, "error": "payroll_authority_p1_disabled_for_company"}
    ensure_payroll_authority_snapshot_schema(cur)
    key = str(employee_key or "")
    synth = _refuse_nonsynthetic(key)
    if synth:
        return synth

    built = _build_external_seal_payload(
        cur, company_code=company_code, import_run_id=import_run_id, employee_key=key
    )
    if not built.get("ok"):
        return built

    existing_import = get_sealed_for_import_employee(
        cur, company_code=company_code, import_run_id=import_run_id, employee_key=key
    )
    if existing_import:
        if str(existing_import.get("content_fingerprint") or "") == built["content_fingerprint"]:
            return {
                "ok": True,
                "idempotent": True,
                "authority_snapshot": _json_safe(existing_import),
                **honesty_payload(),
            }
        return {
            "ok": False,
            "error": "active_sealed_snapshot_exists",
            "message": "Sealed snapshot exists for this import/employee with different content; use replace.",
            "authority_snapshot_id": str(existing_import.get("authority_snapshot_id")),
            **honesty_payload(),
        }

    current = get_current_sealed_snapshot(
        cur,
        company_code=company_code,
        employee_key=key,
        period_start=built["period_start"],
        period_end=built["period_end"],
    )
    if current:
        # Same content from different import path → idempotent reuse
        if str(current.get("content_fingerprint") or "") == built["content_fingerprint"]:
            return {
                "ok": True,
                "idempotent": True,
                "authority_snapshot": _json_safe(current),
                **honesty_payload(),
            }
        # Stale source: refuse overwrite of newer sealed authority
        cur_source_fp = str(current.get("source_fingerprint") or "")
        incoming_source_fp = built["source_fingerprint"]
        if cur_source_fp and cur_source_fp != incoming_source_fp:
            return {
                "ok": False,
                "error": "stale_source_cannot_overwrite_sealed",
                "message": (
                    "A newer/current sealed authority already exists for this employee/period. "
                    "Corrections must use replace_authority_snapshot; silent mutate is refused."
                ),
                "current_authority_snapshot_id": str(current.get("authority_snapshot_id")),
                "current_source_fingerprint": cur_source_fp,
                "incoming_source_fingerprint": incoming_source_fp,
                "current_sealed_at": _json_safe(current.get("sealed_at")),
                **honesty_payload(),
            }
        return {
            "ok": False,
            "error": "active_sealed_snapshot_exists",
            "message": "Sealed snapshot exists for this employee/period; use replace.",
            "authority_snapshot_id": str(current.get("authority_snapshot_id")),
            **honesty_payload(),
        }

    row = _insert_sealed_snapshot(
        cur,
        company_code=company_code,
        employee_key=key,
        built=built,
        actor_phone=actor_phone,
        reason=str(reason).strip(),
    )
    return {
        "ok": True,
        "idempotent": False,
        "authority_snapshot": _json_safe(row),
        **honesty_payload(),
    }


def replace_authority_snapshot(
    cur: Any,
    *,
    company_code: str,
    authority_snapshot_id: str,
    import_run_id: str,
    actor_phone: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Correction: seal a new external version; prior sealed becomes replaced (history retained)."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_authority_snapshot_schema(cur)
    company = (company_code or "").upper()
    prior = get_sealed_snapshot_by_id(
        cur, company_code=company, authority_snapshot_id=authority_snapshot_id
    )
    if not prior:
        return {"ok": False, "error": "authority_snapshot_not_found"}
    if str(prior.get("status") or "") != STATUS_SEALED:
        return {"ok": False, "error": "authority_snapshot_not_sealed", "status": prior.get("status")}
    if str(prior.get("money_authority") or "") != MONEY_EXTERNAL:
        return {"ok": False, "error": "replace_only_supported_for_external_in_p1"}

    key = str(prior.get("employee_key") or "")
    synth = _refuse_nonsynthetic(key)
    if synth:
        return synth

    built = _build_external_seal_payload(
        cur, company_code=company, import_run_id=import_run_id, employee_key=key
    )
    if not built.get("ok"):
        return built

    # Period must match
    if (
        str(built["period_start"])[:10] != str(prior.get("period_start") or "")[:10]
        or str(built["period_end"])[:10] != str(prior.get("period_end") or "")[:10]
    ):
        return {"ok": False, "error": "replace_period_mismatch"}

    chain = list(prior.get("approval_actor_chain") or [])
    if isinstance(chain, str):
        try:
            chain = json.loads(chain)
        except Exception:
            chain = []
    chain = list(chain) if isinstance(chain, list) else []
    chain.append(
        {
            "actor_phone": digits_phone(actor_phone),
            "action": "replace",
            "reason": str(reason).strip(),
            "prior_authority_snapshot_id": str(authority_snapshot_id),
            "at": datetime.utcnow().isoformat() + "Z",
        }
    )

    cur.execute(
        """
        UPDATE payroll_authority_snapshots
        SET status='replaced', updated_at=now(), row_version=row_version+1,
            decision_note=COALESCE(decision_note,'') || ' | replaced:' || %s
        WHERE company_code=%s AND authority_snapshot_id=%s AND status='sealed'
        RETURNING *
        """,
        (str(reason).strip(), company, authority_snapshot_id),
    )
    replaced = _row(cur)
    if not replaced:
        return {"ok": False, "error": "authority_snapshot_replace_race"}

    new_row = _insert_sealed_snapshot(
        cur,
        company_code=company,
        employee_key=key,
        built=built,
        actor_phone=actor_phone,
        reason=str(reason).strip(),
        replaces_snapshot_id=str(authority_snapshot_id),
        approval_actor_chain=chain,
    )
    new_id = str(new_row.get("authority_snapshot_id") or "")
    cur.execute(
        """
        UPDATE payroll_authority_snapshots
        SET superseded_by=%s, updated_at=now()
        WHERE company_code=%s AND authority_snapshot_id=%s
        """,
        (new_id, company, authority_snapshot_id),
    )
    _record_event(
        cur,
        company_code=company,
        authority_snapshot_id=str(authority_snapshot_id),
        event_type="authority_snapshot_replaced",
        payload={
            "superseded_by": new_id,
            "reason": str(reason).strip(),
            "prior_content_fingerprint": prior.get("content_fingerprint"),
            "new_content_fingerprint": built["content_fingerprint"],
        },
        actor_phone=actor_phone,
    )
    return {
        "ok": True,
        "authority_snapshot": _json_safe(new_row),
        "replaced_snapshot": _json_safe(replaced),
        **honesty_payload(),
    }


def revoke_authority_snapshot(
    cur: Any,
    *,
    company_code: str,
    authority_snapshot_id: str,
    actor_phone: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_authority_snapshot_schema(cur)
    company = (company_code or "").upper()
    prior = get_sealed_snapshot_by_id(
        cur, company_code=company, authority_snapshot_id=authority_snapshot_id
    )
    if not prior:
        return {"ok": False, "error": "authority_snapshot_not_found"}
    if str(prior.get("status") or "") != STATUS_SEALED:
        return {"ok": False, "error": "authority_snapshot_not_sealed", "status": prior.get("status")}
    cur.execute(
        """
        UPDATE payroll_authority_snapshots
        SET status='revoked', updated_at=now(), row_version=row_version+1,
            decision_note=COALESCE(decision_note,'') || ' | revoked:' || %s
        WHERE company_code=%s AND authority_snapshot_id=%s AND status='sealed'
        RETURNING *
        """,
        (str(reason).strip(), company, authority_snapshot_id),
    )
    revoked = _row(cur)
    if not revoked:
        return {"ok": False, "error": "authority_snapshot_revoke_race"}
    _record_event(
        cur,
        company_code=company,
        authority_snapshot_id=str(authority_snapshot_id),
        event_type="authority_snapshot_revoked",
        payload={"reason": str(reason).strip()},
        actor_phone=actor_phone,
    )
    return {"ok": True, "authority_snapshot": _json_safe(revoked), **honesty_payload()}


def refuse_mutate_sealed_snapshot(
    cur: Any, *, company_code: str, authority_snapshot_id: str
) -> dict[str, Any]:
    """Prove immutability: direct monetary UPDATE is refused by application policy."""
    ensure_payroll_authority_snapshot_schema(cur)
    snap = get_sealed_snapshot_by_id(
        cur, company_code=company_code, authority_snapshot_id=authority_snapshot_id
    )
    if not snap:
        return {"ok": False, "error": "authority_snapshot_not_found"}
    if str(snap.get("status") or "") != STATUS_SEALED:
        return {"ok": False, "error": "authority_snapshot_not_sealed"}
    return {
        "ok": False,
        "error": "sealed_snapshot_immutable",
        "message": "Sealed monetary values cannot be mutated; use replace_authority_snapshot.",
        "authority_snapshot_id": str(authority_snapshot_id),
        "content_fingerprint": snap.get("content_fingerprint"),
        **honesty_payload(),
    }


def seal_from_native_preview(
    cur: Any,
    *,
    company_code: str,
    preview_run_id: str,
    employee_key: str,
    actor_phone: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Mode A foundation: refuse sealing native preview as wathefni authority in P1."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_authority_snapshot_schema(cur)
    _record_event(
        cur,
        company_code=company_code,
        authority_snapshot_id=None,
        event_type="mode_a_seal_refused",
        payload={
            "preview_run_id": preview_run_id,
            "employee_key": employee_key,
            "reason": str(reason or "").strip(),
            "money_authority_requested": MONEY_WATHEFNI,
            "refused_because": "native_preview_non_authoritative_until_authoritative_finalize",
        },
        actor_phone=actor_phone,
    )
    return {
        "ok": False,
        "error": "mode_a_wathefni_seal_not_unlocked",
        "message": (
            "P1 Mode A foundation only: native preview cannot become money_authority=wathefni. "
            "Wave 2B remains preview_non_authoritative until a future authoritative-finalize path."
        ),
        "money_authority": None,
        "preview_run_id": preview_run_id,
        "employee_key": employee_key,
        "source_kind": SOURCE_NATIVE_REFUSED,
        "source_mode": MODE_A_REFUSED,
        **honesty_payload(),
    }


def period_close_grants_money_authority() -> bool:
    """Explicit: Wave 4 period close never grants money authority."""
    return False


def link_payslip_to_authority_snapshot(
    cur: Any,
    *,
    company_code: str,
    payslip_id: str,
    authority_snapshot_id: str,
) -> dict[str, Any]:
    ensure_payroll_authority_snapshot_schema(cur)
    company = (company_code or "").upper()
    snap = get_sealed_snapshot_by_id(
        cur, company_code=company, authority_snapshot_id=authority_snapshot_id
    )
    if not snap or str(snap.get("status") or "") != STATUS_SEALED:
        return {"ok": False, "error": "authority_snapshot_not_sealed"}
    cur.execute(
        """
        UPDATE payroll_payslip_documents
        SET authority_snapshot_id=%s, updated_at=now(), row_version=row_version+1
        WHERE company_code=%s AND payslip_id=%s
        RETURNING *
        """,
        (authority_snapshot_id, company, payslip_id),
    )
    doc = _row(cur)
    if not doc:
        return {"ok": False, "error": "payslip_not_found"}
    cur.execute(
        """
        UPDATE payroll_authority_snapshots
        SET payslip_id=%s, updated_at=now()
        WHERE company_code=%s AND authority_snapshot_id=%s
        """,
        (payslip_id, company, authority_snapshot_id),
    )
    return {"ok": True, "payslip": _json_safe(doc), "authority_snapshot": _json_safe(snap)}


def generate_external_payslip_from_sealed(
    cur: Any,
    *,
    company_code: str,
    authority_snapshot_id: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    allowed_employee_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Generate Wave 3 external payslip projection from a sealed Mode B snapshot."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_authority_snapshot_schema(cur)
    snap = get_sealed_snapshot_by_id(
        cur, company_code=company_code, authority_snapshot_id=authority_snapshot_id
    )
    if not snap:
        return {"ok": False, "error": "authority_snapshot_not_found"}
    if str(snap.get("status") or "") != STATUS_SEALED:
        return {"ok": False, "error": "authority_snapshot_not_sealed", "status": snap.get("status")}
    if str(snap.get("money_authority") or "") != MONEY_EXTERNAL:
        return {"ok": False, "error": "payslip_requires_external_money_authority_in_p1"}
    import_run_id = str(snap.get("import_run_id") or "")
    employee_key = str(snap.get("employee_key") or "")
    if not import_run_id or not employee_key:
        return {"ok": False, "error": "authority_snapshot_missing_import_provenance"}

    gen = w3.generate_external_payslip(
        cur,
        company_code=company_code,
        import_run_id=import_run_id,
        employee_key=employee_key,
        actor_phone=actor_phone,
        reason=reason,
        allowed_employee_keys=allowed_employee_keys,
    )
    if not gen.get("ok"):
        return gen
    payslip = gen.get("payslip") or {}
    payslip_id = str(payslip.get("payslip_id") or "")
    if payslip_id:
        link_payslip_to_authority_snapshot(
            cur,
            company_code=company_code,
            payslip_id=payslip_id,
            authority_snapshot_id=authority_snapshot_id,
        )
        # Refresh payslip row after link
        cur.execute(
            "SELECT * FROM payroll_payslip_documents WHERE company_code=%s AND payslip_id=%s",
            ((company_code or "").upper(), payslip_id),
        )
        payslip = _row(cur) or payslip
    return {
        "ok": True,
        "idempotent": bool(gen.get("idempotent")),
        "payslip": _json_safe(payslip),
        "authority_snapshot_id": authority_snapshot_id,
        **honesty_payload(),
    }


def seal_and_generate_external_payslip(
    cur: Any,
    *,
    company_code: str,
    import_run_id: str,
    employee_key: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    allowed_employee_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Mode B convenience: seal (idempotent) then generate payslip from sealed authority."""
    sealed = seal_from_external_import(
        cur,
        company_code=company_code,
        import_run_id=import_run_id,
        employee_key=employee_key,
        actor_phone=actor_phone,
        reason=reason,
    )
    if not sealed.get("ok"):
        return sealed
    snap = sealed.get("authority_snapshot") or {}
    snap_id = str(snap.get("authority_snapshot_id") or "")
    gen = generate_external_payslip_from_sealed(
        cur,
        company_code=company_code,
        authority_snapshot_id=snap_id,
        actor_phone=actor_phone,
        reason=reason,
        allowed_employee_keys=allowed_employee_keys,
    )
    if not gen.get("ok"):
        return gen
    return {
        "ok": True,
        "seal_idempotent": bool(sealed.get("idempotent")),
        "payslip_idempotent": bool(gen.get("idempotent")),
        "authority_snapshot": snap,
        "payslip": gen.get("payslip"),
        **honesty_payload(),
    }
