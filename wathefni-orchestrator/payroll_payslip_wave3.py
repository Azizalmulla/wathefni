"""Payroll Payslip Wave 3 — display payslips (staging).

Sources (frozen, read-only):
  - native_preview: Wave 2B preview results → non-authoritative payslip documents
  - external_import: Wave 2A import lines → external-authority mirror payslips

Does NOT: enable payment_processing, bank/WPS, PIFSS, EOS, journals, payments,
AI calculations, or mutate Wave 1/2A/2B contracts or frozen flows.
History is never deleted (replace/revoke only).
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
import base64
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import payroll_authority_wave1 as pyw1
import payroll_external_adapter_wave2a as w2a
import payroll_native_preview_wave2b as w2b
import payroll_payslip_official_pdf as official_pdf

PAYROLL_WAVE3_VERSION = "1.3.0"
PAYSLIP_DOCUMENT_SCHEMA = "payroll_payslip_document@1.3.0"

_ON = {"1", "true", "yes", "on"}

DEFAULT_SYNTHETIC_KEY_MARKERS = (
    "PYW3",
    "PYW3-SYNTH|",
    "PYW2B",
    "PYW2B-SYNTH|",
    "PYW2A",
    "PYW2ACB",
    "PYW1",
    "PYW1-SYNTH|",
    "W2BB",
)
DEFAULT_SYNTHETIC_PHONE_PREFIXES = ("965539", "965540", "965541")

SOURCE_NATIVE = "native_preview"
SOURCE_EXTERNAL = "external_import"
SOURCE_NATIVE_AUTH = "native_authoritative"
STATUS_ACTIVE = "active"
STATUS_REPLACED = "replaced"
STATUS_REVOKED = "revoked"
EMP_VIS_NOT_RELEASED = "not_released"
EMP_VIS_RELEASED = "released"

SCHEMA_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_payslip_wave3_v1.sql"
RELEASE_SCHEMA_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_payslip_employee_release_v1.sql"
OFFICIAL_PDF_SCHEMA_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_payslip_official_pdf_v1.sql"
SCHEMA_SQL = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
RELEASE_SCHEMA_SQL = RELEASE_SCHEMA_PATH.read_text(encoding="utf-8") if RELEASE_SCHEMA_PATH.exists() else ""
OFFICIAL_PDF_SCHEMA_SQL = (
    OFFICIAL_PDF_SCHEMA_PATH.read_text(encoding="utf-8") if OFFICIAL_PDF_SCHEMA_PATH.exists() else ""
)
_SCHEMA_READY = False


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _ON


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def payroll_wave3_enabled() -> bool:
    return _env_bool("WATHEFNI_PAYROLL_WAVE3", default=False)


def payroll_wave3_enabled_for_company(company_code: str | None) -> bool:
    if not payroll_wave3_enabled():
        return False
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE3_COMPANIES") or "WATHEFNI").strip()
    allowed = {p.strip().upper() for p in raw.split(",") if p.strip()}
    return (company_code or "").upper() in allowed


def payroll_wave3_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_ONLY")
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and (raw is None or str(raw).strip() == ""):
        return True
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _ON


def synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_KEY_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_KEY_MARKERS


def synthetic_phone_prefixes() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_PHONE_PREFIXES") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_PHONE_PREFIXES
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_PHONE_PREFIXES


def is_wave3_synthetic_employee(*, employee_key: str | None = None, phone: str | None = None) -> bool:
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
        "payroll_wave3_version": PAYROLL_WAVE3_VERSION,
        "payslip_document_schema": PAYSLIP_DOCUMENT_SCHEMA,
        "payment_processing": "disabled",
        "posts_payment": False,
        "payslip_documents": True,
        "payslips_as_money": False,
        "native_payslips_authoritative": False,
        "external_payslips_authority": "external",
        "employee_release_gate": True,
        "employee_visible_requires": "status=active AND employee_visibility=released",
        "period_status_never_implies_employee_visibility": True,
        "official_employee_pdf": True,
        # Mode A (native_authoritative + sealed wathefni) is eligible alongside Mode B.
        # Authority itself lives in payroll_payslip_official_pdf.is_official_pdf_eligible.
        "official_employee_pdf_requires": (
            "sealed authority snapshot: (Mode B) source_kind=external_import AND money_authority=external "
            "OR (Mode A) source_kind=native_authoritative AND money_authority=wathefni"
        ),
        "native_preview_never_official_pdf": True,
        "bank_files": False,
        "wps": False,
        "pifss": False,
        "eos": False,
        "journals": False,
        "ai_calculations": False,
        "wave1_contracts_unchanged": True,
        "wave2a_flows_unchanged": True,
        "wave2b_flows_unchanged": True,
        "synthetic_only": payroll_wave3_synthetic_only(),
    }


def employee_facing_state(doc: dict[str, Any] | None) -> str:
    """HR/employee projection: not_released | released | replaced | revoked."""
    if not doc:
        return EMP_VIS_NOT_RELEASED
    status = str(doc.get("status") or "").lower()
    if status == STATUS_REVOKED:
        return STATUS_REVOKED
    if status == STATUS_REPLACED:
        return STATUS_REPLACED
    vis = str(doc.get("employee_visibility") or EMP_VIS_NOT_RELEASED).lower()
    if status == STATUS_ACTIVE and vis == EMP_VIS_RELEASED:
        return EMP_VIS_RELEASED
    return EMP_VIS_NOT_RELEASED


def employee_can_view(doc: dict[str, Any] | None) -> bool:
    return employee_facing_state(doc) == EMP_VIS_RELEASED


def freeze_invariants() -> dict[str, Any]:
    return {
        "payment_processing_hard_disabled": True,
        "native_payslips_non_authoritative": True,
        "external_authority_retained": True,
        "history_never_deleted": True,
        "no_bank_files": True,
        "no_ai": True,
        "wave1_ddl_untouched": True,
        "wave2a_ddl_untouched": True,
        "wave2b_ddl_untouched": True,
    }


def ensure_payroll_wave3_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    if not SCHEMA_SQL.strip():
        _SCHEMA_READY = True
        return
    lock_id = 770_900_004
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        cur.execute("SET LOCAL lock_timeout = '15s'")
        pyw1.ensure_payroll_wave1_schema(cur)
        w2a.ensure_payroll_wave2a_schema(cur)
        w2b.ensure_payroll_wave2b_schema(cur)
        # Base Wave 3 DDL (CREATE IF NOT EXISTS is a no-op when table already exists).
        cur.execute(SCHEMA_SQL)
        # P5: allow native_authoritative + wathefni on payslip documents (idempotent alters)
        for stmt in (
            "ALTER TABLE payroll_payslip_documents DROP CONSTRAINT IF EXISTS payroll_payslip_source_kind_chk",
            """ALTER TABLE payroll_payslip_documents
                 ADD CONSTRAINT payroll_payslip_source_kind_chk
                 CHECK (source_kind IN ('native_preview', 'external_import', 'native_authoritative'))""",
            "ALTER TABLE payroll_payslip_documents DROP CONSTRAINT IF EXISTS payroll_payslip_money_authority_chk",
            """ALTER TABLE payroll_payslip_documents
                 ADD CONSTRAINT payroll_payslip_money_authority_chk
                 CHECK (money_authority IN ('preview_non_authoritative', 'external', 'wathefni'))""",
        ):
            try:
                cur.execute(stmt)
            except Exception:
                pass
        # Additive employee release columns/index for existing installs.
        if RELEASE_SCHEMA_SQL.strip():
            cur.execute(RELEASE_SCHEMA_SQL)
        if OFFICIAL_PDF_SCHEMA_SQL.strip():
            cur.execute(OFFICIAL_PDF_SCHEMA_SQL)
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
    if payroll_wave3_synthetic_only() and not is_wave3_synthetic_employee(employee_key=employee_key):
        return {"ok": False, "error": "payroll_wave3_synthetic_only", "employee_key": employee_key}
    return None


def _scope_allows(employee_key: str, allowed_employee_keys: set[str] | None) -> bool:
    if allowed_employee_keys is None:
        return True
    return employee_key in allowed_employee_keys


def _record_event(
    cur: Any,
    *,
    company_code: str,
    payslip_id: str | None,
    event_type: str,
    payload: dict[str, Any],
    actor_phone: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO payroll_payslip_events (payslip_id, company_code, event_type, payload, created_by_phone)
        VALUES (%s,%s,%s,%s::jsonb,%s)
        """,
        (
            payslip_id,
            (company_code or "").upper(),
            event_type,
            json.dumps(_json_safe(payload)),
            digits_phone(actor_phone),
        ),
    )


def _labels_for_source(source_kind: str) -> dict[str, str]:
    if source_kind == SOURCE_NATIVE:
        return {
            "money_authority": "preview_non_authoritative",
            "authoritative_label": "preview_non_authoritative",
            "label_en": "Native preview payslip — not payment authority",
            "label_ar": "قسيمة راتب معاينة محلية — ليست سلطة دفع",
            "authority_banner_en": "Preview only. Not authoritative. Payment processing disabled.",
            "authority_banner_ar": "معاينة فقط. غير ملزمة. معالجة الدفع معطّلة.",
        }
    if source_kind == SOURCE_NATIVE_AUTH:
        return {
            "money_authority": "wathefni",
            "authoritative_label": "wathefni",
            "label_en": "Wathefni authoritative payslip",
            "label_ar": "قسيمة راتب معتمدة من وظّفني",
            "authority_banner_en": "Authoritative Wathefni payroll obligation. Payment processing disabled.",
            "authority_banner_ar": "التزام رواتب معتمد من وظّفني. معالجة الدفع معطّلة.",
        }
    return {
        "money_authority": "external",
        "authoritative_label": "external",
        "label_en": "External payroll payslip — external system is money authority",
        "label_ar": "قسيمة راتب خارجية — النظام الخارجي هو سلطة المال",
        "authority_banner_en": "Imported mirror. External system remains money authority. Payment processing disabled.",
        "authority_banner_ar": "مرآة مستوردة. النظام الخارجي يبقى سلطة المال. معالجة الدفع معطّلة.",
    }


def _build_native_snapshot(
    cur: Any,
    *,
    company_code: str,
    preview_run_id: str,
    employee_key: str,
) -> dict[str, Any]:
    run = w2b.get_preview_run(cur, company_code=company_code, preview_run_id=preview_run_id)
    if not run:
        return {"ok": False, "error": "preview_run_not_found"}
    if str(run.get("status") or "") != "calculated":
        return {"ok": False, "error": "preview_run_not_calculated", "status": run.get("status")}
    employees = w2b.list_preview_employee_results(cur, company_code=company_code, preview_run_id=preview_run_id)
    emp = next((e for e in employees if str(e.get("employee_key") or "") == employee_key), None)
    if not emp:
        return {"ok": False, "error": "employee_not_in_preview_run"}
    if str(emp.get("status") or "") not in ("ok", "partial"):
        return {"ok": False, "error": "preview_employee_blocked", "employee_status": emp.get("status")}
    all_lines = w2b.list_preview_lines(cur, company_code=company_code, preview_run_id=preview_run_id)
    lines = [ln for ln in all_lines if str(ln.get("employee_key") or "") == employee_key]
    labels = _labels_for_source(SOURCE_NATIVE)
    slip_lines = []
    for i, ln in enumerate(lines):
        code = str(ln.get("code") or ln.get("line_kind") or f"L{i}")
        slip_lines.append(
            {
                "line_kind": str(ln.get("line_kind") or "earning"),
                "code": code,
                "label_en": str(ln.get("label_en") or code),
                "label_ar": str(ln.get("label_ar") or ln.get("label_en") or code),
                "amount": float(Decimal(str(ln.get("amount") or 0))),
                "currency": str(ln.get("currency") or "KWD"),
                "sort_order": int(ln.get("sort_order") or i),
                "calc_notes": ln.get("calc_notes") or {},
            }
        )
    payload = {
        "schema": PAYSLIP_DOCUMENT_SCHEMA,
        "source_kind": SOURCE_NATIVE,
        "source_run_id": preview_run_id,
        "employee_key": employee_key,
        "period_start": str(run.get("period_start") or "")[:10],
        "period_end": str(run.get("period_end") or "")[:10],
        "currency": str(run.get("currency") or emp.get("currency") or "KWD"),
        "totals_earnings": float(Decimal(str(emp.get("totals_earnings") or 0))),
        "totals_deductions": float(Decimal(str(emp.get("totals_deductions") or 0))),
        "totals_net": float(Decimal(str(emp.get("totals_net_preview") or 0))),
        "lines": slip_lines,
        "labels": labels,
        "preview_policy_version": run.get("policy_version"),
        "input_fingerprint": run.get("input_fingerprint"),
        "calculation_fingerprint": run.get("calculation_fingerprint"),
        "payment_processing": "disabled",
        "posts_payment": False,
        "authoritative": False,
    }
    return {"ok": True, "payload": payload, "labels": labels, "run": run}


def _build_external_snapshot(
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
    labels = _labels_for_source(SOURCE_EXTERNAL)
    slip_lines = []
    tot_earn = Decimal("0")
    tot_ded = Decimal("0")
    for i, ln in enumerate(emp_lines):
        code = str(ln.get("component_code") or f"C{i}")
        amount = Decimal(str(ln.get("opaque_amount") or 0))
        # Opaque external amounts treated as earnings lines by default;
        # negative opaque treated as deductions for display.
        if amount < 0:
            line_kind = "deduction"
            tot_ded += abs(amount)
            display_amount = abs(amount)
        else:
            line_kind = "earning"
            tot_earn += amount
            display_amount = amount
        slip_lines.append(
            {
                "line_kind": line_kind,
                "code": code,
                "label_en": code,
                "label_ar": code,
                "amount": float(display_amount),
                "currency": str(ln.get("currency") or "KWD"),
                "sort_order": i,
                "calc_notes": {"source": "external_import", "line_status": ln.get("line_status")},
            }
        )
    period_start = str(imp.get("period_start") or "")[:10]
    period_end = str(imp.get("period_end") or "")[:10]
    if not period_start or not period_end:
        # Fall back from linked export if present
        export_id = str(imp.get("export_run_id") or "")
        if export_id:
            exp = w2a.get_export_run(cur, company_code=company_code, export_run_id=export_id)
            if exp:
                period_start = str(exp.get("period_start") or period_start)[:10]
                period_end = str(exp.get("period_end") or period_end)[:10]
    if not period_start or not period_end:
        return {"ok": False, "error": "import_period_missing"}
    payload = {
        "schema": PAYSLIP_DOCUMENT_SCHEMA,
        "source_kind": SOURCE_EXTERNAL,
        "source_run_id": import_run_id,
        "employee_key": employee_key,
        "period_start": period_start,
        "period_end": period_end,
        "currency": str(emp_lines[0].get("currency") or "KWD"),
        "totals_earnings": float(tot_earn),
        "totals_deductions": float(tot_ded),
        "totals_net": float(tot_earn - tot_ded),
        "lines": slip_lines,
        "labels": labels,
        "external_run_id": imp.get("external_run_id"),
        "payment_processing": "disabled",
        "posts_payment": False,
        "authoritative_in_wathefni": False,
        "money_authority": "external",
    }
    return {"ok": True, "payload": payload, "labels": labels, "import_run": imp}


def _find_active(
    cur: Any,
    *,
    company_code: str,
    source_kind: str,
    source_run_id: str,
    employee_key: str,
) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM payroll_payslip_documents
        WHERE company_code=%s AND source_kind=%s AND source_run_id=%s
          AND employee_key=%s AND status='active'
        ORDER BY version_number DESC LIMIT 1
        """,
        ((company_code or "").upper(), source_kind, source_run_id, employee_key),
    )
    return _row(cur)


def _insert_payslip(
    cur: Any,
    *,
    company_code: str,
    source_kind: str,
    source_run_id: str,
    snapshot: dict[str, Any],
    actor_phone: str | None,
    reason: str,
    version_number: int = 1,
    replaces_payslip_id: str | None = None,
) -> dict[str, Any]:
    payload = snapshot["payload"]
    labels = snapshot["labels"]
    fp = fingerprint_payload(payload)
    company = (company_code or "").upper()
    cur.execute(
        """
        INSERT INTO payroll_payslip_documents (
          company_code, source_kind, source_run_id, employee_key,
          period_start, period_end, version_number, status,
          replaces_payslip_id, content_fingerprint,
          money_authority, authoritative_label, payment_processing, posts_payment,
          currency, totals_earnings, totals_deductions, totals_net,
          document_payload, locale_default, decision_note, created_by_phone
        ) VALUES (
          %s,%s,%s,%s,
          %s,%s,%s,'active',
          %s,%s,
          %s,%s,'disabled',false,
          %s,%s,%s,%s,
          %s::jsonb,'en',%s,%s
        )
        RETURNING *
        """,
        (
            company,
            source_kind,
            source_run_id,
            payload["employee_key"],
            payload["period_start"],
            payload["period_end"],
            version_number,
            replaces_payslip_id,
            fp,
            labels["money_authority"],
            labels["authoritative_label"],
            payload["currency"],
            payload["totals_earnings"],
            payload["totals_deductions"],
            payload["totals_net"],
            json.dumps(_json_safe(payload)),
            reason,
            digits_phone(actor_phone),
        ),
    )
    doc = _row(cur) or {}
    payslip_id = str(doc.get("payslip_id"))
    for ln in payload.get("lines") or []:
        cur.execute(
            """
            INSERT INTO payroll_payslip_lines (
              payslip_id, company_code, employee_key, line_kind, code,
              label_en, label_ar, amount, currency, sort_order, calc_notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                payslip_id,
                company,
                payload["employee_key"],
                ln.get("line_kind"),
                ln.get("code"),
                ln.get("label_en"),
                ln.get("label_ar"),
                ln.get("amount"),
                ln.get("currency") or "KWD",
                int(ln.get("sort_order") or 0),
                json.dumps(_json_safe(ln.get("calc_notes") or {})),
            ),
        )
    _record_event(
        cur,
        company_code=company,
        payslip_id=payslip_id,
        event_type="payslip_generated",
        payload={
            "source_kind": source_kind,
            "source_run_id": source_run_id,
            "employee_key": payload["employee_key"],
            "version_number": version_number,
            "content_fingerprint": fp,
            "money_authority": labels["money_authority"],
            "reason": reason,
        },
        actor_phone=actor_phone,
    )
    return doc


def generate_native_payslip(
    cur: Any,
    *,
    company_code: str,
    preview_run_id: str,
    employee_key: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    allowed_employee_keys: set[str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave3_schema(cur)
    key = str(employee_key or "")
    synth = _refuse_nonsynthetic(key)
    if synth:
        return synth
    if not _scope_allows(key, allowed_employee_keys):
        return {"ok": False, "error": "employee_outside_manager_scope", "employee_key": key}
    snap = _build_native_snapshot(
        cur, company_code=company_code, preview_run_id=preview_run_id, employee_key=key
    )
    if not snap.get("ok"):
        return snap
    existing = _find_active(
        cur,
        company_code=company_code,
        source_kind=SOURCE_NATIVE,
        source_run_id=preview_run_id,
        employee_key=key,
    )
    if existing:
        fp = fingerprint_payload(snap["payload"])
        if str(existing.get("content_fingerprint") or "") == fp:
            return {
                "ok": True,
                "idempotent": True,
                "payslip": _json_safe(existing),
                **honesty_payload(),
            }
        return {
            "ok": False,
            "error": "active_payslip_exists",
            "message": "Active payslip exists with different content; use replace.",
            "payslip_id": str(existing.get("payslip_id")),
            **honesty_payload(),
        }
    doc = _insert_payslip(
        cur,
        company_code=company_code,
        source_kind=SOURCE_NATIVE,
        source_run_id=preview_run_id,
        snapshot=snap,
        actor_phone=actor_phone,
        reason=str(reason).strip(),
    )
    return {"ok": True, "idempotent": False, "payslip": _json_safe(doc), **honesty_payload()}


def _maybe_link_external_authority_snapshot(
    cur: Any,
    *,
    company_code: str,
    import_run_id: str,
    employee_key: str,
    payslip_id: str,
    inherit_authority_snapshot_id: str | None = None,
) -> dict[str, Any] | None:
    """Link payslip to sealed Mode B authority when present (P1). Lazy-import to avoid cycles."""
    snap_id = str(inherit_authority_snapshot_id or "").strip() or None
    try:
        import payroll_authority_snapshot_p1 as p1

        p1.ensure_payroll_authority_snapshot_schema(cur)
        if not snap_id:
            sealed = p1.get_sealed_for_import_employee(
                cur,
                company_code=company_code,
                import_run_id=import_run_id,
                employee_key=employee_key,
            )
            if sealed and str(sealed.get("status") or "") == "sealed":
                snap_id = str(sealed.get("authority_snapshot_id") or "") or None
        if not snap_id:
            return None
        linked = p1.link_payslip_to_authority_snapshot(
            cur,
            company_code=company_code,
            payslip_id=payslip_id,
            authority_snapshot_id=snap_id,
        )
        if linked.get("ok"):
            return linked.get("payslip")
    except Exception:
        return None
    return None


def generate_external_payslip(
    cur: Any,
    *,
    company_code: str,
    import_run_id: str,
    employee_key: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    allowed_employee_keys: set[str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave3_schema(cur)
    key = str(employee_key or "")
    synth = _refuse_nonsynthetic(key)
    if synth:
        return synth
    if not _scope_allows(key, allowed_employee_keys):
        return {"ok": False, "error": "employee_outside_manager_scope", "employee_key": key}
    snap = _build_external_snapshot(
        cur, company_code=company_code, import_run_id=import_run_id, employee_key=key
    )
    if not snap.get("ok"):
        return snap
    existing = _find_active(
        cur,
        company_code=company_code,
        source_kind=SOURCE_EXTERNAL,
        source_run_id=import_run_id,
        employee_key=key,
    )
    if existing:
        fp = fingerprint_payload(snap["payload"])
        if str(existing.get("content_fingerprint") or "") == fp:
            return {
                "ok": True,
                "idempotent": True,
                "payslip": _json_safe(existing),
                **honesty_payload(),
            }
        return {
            "ok": False,
            "error": "active_payslip_exists",
            "message": "Active payslip exists with different content; use replace.",
            "payslip_id": str(existing.get("payslip_id")),
            **honesty_payload(),
        }
    doc = _insert_payslip(
        cur,
        company_code=company_code,
        source_kind=SOURCE_EXTERNAL,
        source_run_id=import_run_id,
        snapshot=snap,
        actor_phone=actor_phone,
        reason=str(reason).strip(),
    )
    linked = _maybe_link_external_authority_snapshot(
        cur,
        company_code=company_code,
        import_run_id=import_run_id,
        employee_key=key,
        payslip_id=str(doc.get("payslip_id") or ""),
    )
    if linked:
        doc = linked
    return {"ok": True, "idempotent": False, "payslip": _json_safe(doc), **honesty_payload()}


def generate_wathefni_payslip_from_authority_snapshot(
    cur: Any,
    *,
    company_code: str,
    authority_snapshot_id: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    allowed_employee_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Mode A: payslip from sealed money_authority=wathefni snapshot (exact monetary match)."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave3_schema(cur)
    import payroll_authority_snapshot_p1 as p1

    snap = p1.get_sealed_snapshot_by_id(
        cur, company_code=company_code, authority_snapshot_id=authority_snapshot_id
    )
    if not snap:
        return {"ok": False, "error": "authority_snapshot_not_found"}
    if str(snap.get("status") or "") != "sealed":
        return {"ok": False, "error": "authority_snapshot_not_sealed", "status": snap.get("status")}
    if str(snap.get("money_authority") or "") != "wathefni":
        return {"ok": False, "error": "payslip_requires_wathefni_money_authority"}
    key = str(snap.get("employee_key") or "")
    synth = _refuse_nonsynthetic(key)
    if synth:
        return synth
    if not _scope_allows(key, allowed_employee_keys):
        return {"ok": False, "error": "employee_outside_manager_scope", "employee_key": key}

    cur.execute(
        """
        SELECT * FROM payroll_authority_snapshot_lines
        WHERE company_code=%s AND authority_snapshot_id=%s
        ORDER BY sort_order, component_code
        """,
        ((company_code or "").upper(), authority_snapshot_id),
    )
    snap_lines = _rows(cur)
    labels = _labels_for_source(SOURCE_NATIVE_AUTH)
    slip_lines = []
    for i, ln in enumerate(snap_lines):
        slip_lines.append(
            {
                "line_kind": str(ln.get("line_kind") or "earning"),
                "code": str(ln.get("component_code") or f"L{i}"),
                "label_en": str(ln.get("label_en") or ln.get("component_code") or f"L{i}"),
                "label_ar": str(ln.get("label_ar") or ln.get("label_en") or ln.get("component_code") or ""),
                "amount": float(Decimal(str(ln.get("amount") or 0))),
                "currency": str(ln.get("currency") or "KWD"),
                "sort_order": int(ln.get("sort_order") or i),
                "calc_notes": {"authority_line_id": str(ln.get("line_id") or "")},
            }
        )
    payload = {
        "schema": PAYSLIP_DOCUMENT_SCHEMA,
        "source_kind": SOURCE_NATIVE_AUTH,
        "source_run_id": authority_snapshot_id,
        "employee_key": key,
        "period_start": str(snap.get("period_start") or "")[:10],
        "period_end": str(snap.get("period_end") or "")[:10],
        "currency": "KWD",
        "totals_earnings": float(Decimal(str(snap.get("totals_earnings") or 0))),
        "totals_deductions": float(Decimal(str(snap.get("totals_deductions") or 0))),
        "totals_net": float(Decimal(str(snap.get("totals_net") or 0))),
        "lines": slip_lines,
        "labels": labels,
        "authority_snapshot_id": authority_snapshot_id,
        "content_fingerprint_authority": snap.get("content_fingerprint"),
        "payment_processing": "disabled",
        "posts_payment": False,
        "authoritative": True,
        "money_authority": "wathefni",
    }
    snapshot = {"ok": True, "payload": payload, "labels": labels}
    existing = _find_active(
        cur,
        company_code=company_code,
        source_kind=SOURCE_NATIVE_AUTH,
        source_run_id=authority_snapshot_id,
        employee_key=key,
    )
    if existing:
        fp = fingerprint_payload(payload)
        if str(existing.get("content_fingerprint") or "") == fp:
            return {
                "ok": True,
                "idempotent": True,
                "payslip": _json_safe(existing),
                "authority_snapshot_id": authority_snapshot_id,
                **honesty_payload(),
            }
        return {
            "ok": False,
            "error": "active_payslip_exists_with_different_content",
            "payslip_id": str(existing.get("payslip_id")),
            **honesty_payload(),
        }
    doc = _insert_payslip(
        cur,
        company_code=company_code,
        source_kind=SOURCE_NATIVE_AUTH,
        source_run_id=authority_snapshot_id,
        snapshot=snapshot,
        actor_phone=actor_phone,
        reason=str(reason).strip(),
    )
    payslip_id = str(doc.get("payslip_id") or "")
    if payslip_id:
        p1.link_payslip_to_authority_snapshot(
            cur,
            company_code=company_code,
            payslip_id=payslip_id,
            authority_snapshot_id=authority_snapshot_id,
        )
        cur.execute(
            "SELECT * FROM payroll_payslip_documents WHERE company_code=%s AND payslip_id=%s",
            ((company_code or "").upper(), payslip_id),
        )
        doc = _row(cur) or doc
    return {
        "ok": True,
        "idempotent": False,
        "payslip": _json_safe(doc),
        "authority_snapshot_id": authority_snapshot_id,
        **honesty_payload(),
    }


def replace_payslip(
    cur: Any,
    *,
    company_code: str,
    payslip_id: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    allowed_employee_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Re-generate from the same source into a new version; keep prior as replaced."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave3_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        "SELECT * FROM payroll_payslip_documents WHERE company_code=%s AND payslip_id=%s",
        (company, payslip_id),
    )
    prior = _row(cur)
    if not prior:
        return {"ok": False, "error": "payslip_not_found"}
    if str(prior.get("status") or "") != STATUS_ACTIVE:
        return {"ok": False, "error": "payslip_not_active", "status": prior.get("status")}
    key = str(prior.get("employee_key") or "")
    if not _scope_allows(key, allowed_employee_keys):
        return {"ok": False, "error": "employee_outside_manager_scope", "employee_key": key}
    source_kind = str(prior.get("source_kind") or "")
    source_run_id = str(prior.get("source_run_id") or "")
    if source_kind == SOURCE_NATIVE:
        snap = _build_native_snapshot(
            cur, company_code=company, preview_run_id=source_run_id, employee_key=key
        )
    elif source_kind == SOURCE_EXTERNAL:
        snap = _build_external_snapshot(
            cur, company_code=company, import_run_id=source_run_id, employee_key=key
        )
    else:
        return {"ok": False, "error": "invalid_source_kind"}
    if not snap.get("ok"):
        return snap
    new_version = int(prior.get("version_number") or 1) + 1
    # Mark prior replaced first (history retained)
    cur.execute(
        """
        UPDATE payroll_payslip_documents
        SET status='replaced', updated_at=now(), row_version=row_version+1,
            decision_note=COALESCE(decision_note,'') || ' | replaced:' || %s
        WHERE company_code=%s AND payslip_id=%s AND status='active'
        RETURNING *
        """,
        (str(reason).strip(), company, payslip_id),
    )
    replaced = _row(cur)
    if not replaced:
        return {"ok": False, "error": "payslip_replace_race"}
    doc = _insert_payslip(
        cur,
        company_code=company,
        source_kind=source_kind,
        source_run_id=source_run_id,
        snapshot=snap,
        actor_phone=actor_phone,
        reason=str(reason).strip(),
        version_number=new_version,
        replaces_payslip_id=payslip_id,
    )
    new_id = str(doc.get("payslip_id"))
    if source_kind == SOURCE_EXTERNAL:
        linked = _maybe_link_external_authority_snapshot(
            cur,
            company_code=company,
            import_run_id=source_run_id,
            employee_key=key,
            payslip_id=new_id,
            inherit_authority_snapshot_id=str(prior.get("authority_snapshot_id") or "") or None,
        )
        if linked:
            doc = linked
    cur.execute(
        """
        UPDATE payroll_payslip_documents
        SET superseded_by=%s, updated_at=now()
        WHERE company_code=%s AND payslip_id=%s
        """,
        (new_id, company, payslip_id),
    )
    _record_event(
        cur,
        company_code=company,
        payslip_id=payslip_id,
        event_type="payslip_replaced",
        payload={"replaced_by": new_id, "reason": reason},
        actor_phone=actor_phone,
    )
    return {
        "ok": True,
        "payslip": _json_safe(doc),
        "replaced_payslip": _json_safe(replaced),
        **honesty_payload(),
    }


def revoke_payslip(
    cur: Any,
    *,
    company_code: str,
    payslip_id: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    allowed_employee_keys: set[str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave3_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        "SELECT * FROM payroll_payslip_documents WHERE company_code=%s AND payslip_id=%s",
        (company, payslip_id),
    )
    prior = _row(cur)
    if not prior:
        return {"ok": False, "error": "payslip_not_found"}
    if str(prior.get("status") or "") != STATUS_ACTIVE:
        return {"ok": False, "error": "payslip_not_active", "status": prior.get("status")}
    key = str(prior.get("employee_key") or "")
    if not _scope_allows(key, allowed_employee_keys):
        return {"ok": False, "error": "employee_outside_manager_scope", "employee_key": key}
    cur.execute(
        """
        UPDATE payroll_payslip_documents
        SET status='revoked', updated_at=now(), row_version=row_version+1,
            decision_note=COALESCE(decision_note,'') || ' | revoked:' || %s
        WHERE company_code=%s AND payslip_id=%s AND status='active'
        RETURNING *
        """,
        (str(reason).strip(), company, payslip_id),
    )
    updated = _row(cur)
    if not updated:
        return {"ok": False, "error": "payslip_revoke_race"}
    _record_event(
        cur,
        company_code=company,
        payslip_id=payslip_id,
        event_type="payslip_revoked",
        payload={"reason": reason, "history_retained": True},
        actor_phone=actor_phone,
    )
    return {"ok": True, "payslip": _json_safe(updated), **honesty_payload()}


def release_payslip_to_employee(
    cur: Any,
    *,
    company_code: str,
    payslip_id: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    allowed_employee_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Explicit employee release. Never inferred from period open/locked/closed."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave3_schema(cur)
    doc = get_payslip(cur, company_code=company_code, payslip_id=payslip_id)
    if not doc:
        return {"ok": False, "error": "payslip_not_found"}
    key = str(doc.get("employee_key") or "")
    synth = _refuse_nonsynthetic(key)
    if synth:
        return synth
    if not _scope_allows(key, allowed_employee_keys):
        return {"ok": False, "error": "employee_outside_manager_scope", "employee_key": key}
    if str(doc.get("status") or "") != STATUS_ACTIVE:
        return {
            "ok": False,
            "error": "payslip_not_active",
            "status": doc.get("status"),
            "employee_facing_state": employee_facing_state(doc),
        }
    if str(doc.get("employee_visibility") or "") == EMP_VIS_RELEASED:
        return {
            "ok": True,
            "idempotent": True,
            "payslip": _annotate_payslip(doc),
            "employee_facing_state": EMP_VIS_RELEASED,
            **honesty_payload(),
        }
    cur.execute(
        """
        UPDATE payroll_payslip_documents
        SET employee_visibility=%s,
            employee_released_at=now(),
            employee_released_by_phone=%s,
            employee_release_note=%s,
            updated_at=now(),
            row_version=row_version+1
        WHERE company_code=%s AND payslip_id=%s AND status='active' AND employee_visibility=%s
        RETURNING *
        """,
        (
            EMP_VIS_RELEASED,
            digits_phone(actor_phone),
            str(reason or "").strip(),
            (company_code or "").upper(),
            payslip_id,
            EMP_VIS_NOT_RELEASED,
        ),
    )
    updated = _row(cur)
    if not updated:
        # Concurrent release — re-read
        again = get_payslip(cur, company_code=company_code, payslip_id=payslip_id)
        if again and str(again.get("employee_visibility") or "") == EMP_VIS_RELEASED:
            return {
                "ok": True,
                "idempotent": True,
                "payslip": _annotate_payslip(again),
                "employee_facing_state": EMP_VIS_RELEASED,
                **honesty_payload(),
            }
        return {"ok": False, "error": "release_conflict"}
    _record_event(
        cur,
        company_code=company_code,
        payslip_id=payslip_id,
        event_type="payslip_released_to_employee",
        payload={"reason": reason, "employee_key": key},
        actor_phone=actor_phone,
    )
    annotated = _annotate_payslip(updated)
    pdf_jobs: list[dict[str, Any]] = []
    if official_pdf.is_official_pdf_eligible(updated):
        # Generate both locales from the immutable snapshot at release time.
        for loc in ("en", "ar"):
            try:
                pdf_jobs.append(
                    official_pdf.ensure_official_pdf_for_payslip(
                        cur,
                        company_code=company_code,
                        payslip_id=payslip_id,
                        locale=loc,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                pdf_jobs.append({"ok": False, "locale": loc, "error": type(exc).__name__, "detail": str(exc)[:200]})
    return {
        "ok": True,
        "idempotent": False,
        "payslip": annotated,
        "employee_facing_state": EMP_VIS_RELEASED,
        "notify_employee": True,
        "official_pdf": pdf_jobs,
        **honesty_payload(),
    }


def unrelease_payslip_from_employee(
    cur: Any,
    *,
    company_code: str,
    payslip_id: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    allowed_employee_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Withdraw employee visibility without revoking the HR document."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave3_schema(cur)
    doc = get_payslip(cur, company_code=company_code, payslip_id=payslip_id)
    if not doc:
        return {"ok": False, "error": "payslip_not_found"}
    key = str(doc.get("employee_key") or "")
    if not _scope_allows(key, allowed_employee_keys):
        return {"ok": False, "error": "employee_outside_manager_scope", "employee_key": key}
    if str(doc.get("status") or "") != STATUS_ACTIVE:
        return {"ok": False, "error": "payslip_not_active", "status": doc.get("status")}
    if str(doc.get("employee_visibility") or "") != EMP_VIS_RELEASED:
        return {
            "ok": True,
            "idempotent": True,
            "payslip": _annotate_payslip(doc),
            "employee_facing_state": employee_facing_state(doc),
            **honesty_payload(),
        }
    cur.execute(
        """
        UPDATE payroll_payslip_documents
        SET employee_visibility=%s,
            employee_released_at=NULL,
            employee_released_by_phone=NULL,
            employee_release_note=%s,
            updated_at=now(),
            row_version=row_version+1
        WHERE company_code=%s AND payslip_id=%s AND status='active' AND employee_visibility=%s
        RETURNING *
        """,
        (
            EMP_VIS_NOT_RELEASED,
            str(reason or "").strip(),
            (company_code or "").upper(),
            payslip_id,
            EMP_VIS_RELEASED,
        ),
    )
    updated = _row(cur)
    if not updated:
        again = get_payslip(cur, company_code=company_code, payslip_id=payslip_id)
        return {
            "ok": True,
            "idempotent": True,
            "payslip": _annotate_payslip(again or doc),
            "employee_facing_state": employee_facing_state(again or doc),
            **honesty_payload(),
        }
    _record_event(
        cur,
        company_code=company_code,
        payslip_id=payslip_id,
        event_type="payslip_unreleased_from_employee",
        payload={"reason": reason, "employee_key": key},
        actor_phone=actor_phone,
    )
    return {
        "ok": True,
        "idempotent": False,
        "payslip": _annotate_payslip(updated),
        "employee_facing_state": EMP_VIS_NOT_RELEASED,
        **honesty_payload(),
    }


def _annotate_payslip(doc: dict[str, Any] | None) -> dict[str, Any]:
    if not doc:
        return {}
    out = _json_safe(doc) or {}
    out["employee_facing_state"] = employee_facing_state(doc)
    out["employee_visible"] = employee_can_view(doc)
    # Never invent payment_date.
    out["payment_date"] = None
    eligible = official_pdf.is_official_pdf_eligible(doc)
    out["official_pdf_eligible"] = eligible
    # Official document only once released AND eligible (external authority snapshot).
    out["official_document"] = bool(employee_can_view(doc) and eligible)
    out["download_available"] = bool(out["official_document"])
    out["download_kind"] = "official_pdf" if out["download_available"] else None
    return out


def encode_employee_payslip_list_cursor(row: dict[str, Any]) -> str:
    """Opaque keyset cursor for employee payslip list (period_end, created_at, id)."""
    payload = {
        "v": 1,
        "pe": str(row.get("period_end") or ""),
        "ca": str(row.get("created_at") or ""),
        "id": str(row.get("payslip_id") or ""),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_employee_payslip_list_cursor(token: str | None) -> dict[str, str] | None:
    """Return cursor fields or None when blank. Raises ValueError when malformed."""
    text = str(token or "").strip()
    if not text:
        return None
    pad = "=" * (-len(text) % 4)
    try:
        raw = base64.urlsafe_b64decode(text + pad)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid_cursor") from exc
    if not isinstance(payload, dict) or int(payload.get("v") or 0) != 1:
        raise ValueError("invalid_cursor")
    pe = str(payload.get("pe") or "").strip()
    ca = str(payload.get("ca") or "").strip()
    pid = str(payload.get("id") or "").strip()
    if not pe or not ca or not pid:
        raise ValueError("invalid_cursor")
    return {"pe": pe, "ca": ca, "id": pid}


def list_employee_released_payslips_page(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    limit: int = 24,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Keyset page of released payslips for one employee.

    Ordered ``period_end DESC, created_at DESC, payslip_id DESC``. Fetches
    ``limit + 1`` to set ``has_more`` honestly — never a raised hard ceiling that
    pretends the full history arrived in one shot.
    """
    ensure_payroll_wave3_schema(cur)
    page_size = max(1, min(int(limit or 24), 50))
    decoded = decode_employee_payslip_list_cursor(cursor)
    params: list[Any] = [(company_code or "").upper(), employee_key]
    keyset_sql = ""
    if decoded:
        keyset_sql = """
          AND (
            period_end < %s::date
            OR (period_end = %s::date AND created_at < %s::timestamptz)
            OR (
              period_end = %s::date
              AND created_at = %s::timestamptz
              AND payslip_id::text < %s
            )
          )
        """
        params.extend(
            [
                decoded["pe"],
                decoded["pe"],
                decoded["ca"],
                decoded["pe"],
                decoded["ca"],
                decoded["id"],
            ]
        )
    params.append(page_size + 1)
    cur.execute(
        f"""
        SELECT payslip_id::text, source_kind, employee_key,
               period_start, period_end, version_number, status,
               employee_visibility, employee_released_at,
               money_authority, authoritative_label,
               currency, totals_earnings, totals_deductions, totals_net,
               created_at, updated_at
        FROM payroll_payslip_documents
        WHERE company_code=%s
          AND employee_key=%s
          AND status='active'
          AND employee_visibility='released'
          {keyset_sql}
        ORDER BY period_end DESC, created_at DESC, payslip_id::text DESC
        LIMIT %s
        """,
        tuple(params),
    )
    fetched = [_annotate_payslip(r) for r in _rows(cur)]
    has_more = len(fetched) > page_size
    page_rows = fetched[:page_size]
    next_cursor = encode_employee_payslip_list_cursor(page_rows[-1]) if has_more and page_rows else None
    return {
        "payslips": page_rows,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "limit": page_size,
    }


def list_employee_released_payslips(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    limit: int = 24,
    cursor: str | None = None,
) -> list[dict[str, Any]]:
    """Self-scoped employee list: active + released only.

    Backward-compatible wrapper over :func:`list_employee_released_payslips_page`
    for Home and older callers that only need the row list.
    """
    page = list_employee_released_payslips_page(
        cur,
        company_code=company_code,
        employee_key=employee_key,
        limit=limit,
        cursor=cursor,
    )
    return list(page.get("payslips") or [])


def get_employee_released_payslip(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    payslip_id: str,
) -> dict[str, Any] | None:
    ensure_payroll_wave3_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_payslip_documents
        WHERE company_code=%s AND payslip_id=%s AND employee_key=%s
        LIMIT 1
        """,
        ((company_code or "").upper(), payslip_id, employee_key),
    )
    doc = _row(cur)
    if not doc or not employee_can_view(doc):
        return None
    return _annotate_payslip(doc)


def employee_payslip_summary(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    payslip_id: str,
    locale: str = "en",
) -> dict[str, Any]:
    """Employee-safe detail: no approval workflow, no calc debug dumps."""
    doc = get_employee_released_payslip(
        cur, company_code=company_code, employee_key=employee_key, payslip_id=payslip_id
    )
    if not doc:
        return {"ok": False, "error": "payslip_not_found"}
    lines = list_payslip_lines(cur, company_code=company_code, payslip_id=payslip_id)
    loc = "ar" if str(locale or "").lower().startswith("ar") else "en"
    safe_lines = []
    for ln in lines:
        kind = str(ln.get("line_kind") or "")
        safe_lines.append(
            {
                "line_kind": kind,
                "code": ln.get("code"),
                "label": ln.get("label_ar" if loc == "ar" else "label_en") or ln.get("code"),
                "amount": ln.get("amount"),
                "currency": ln.get("currency") or doc.get("currency") or "KWD",
            }
        )
    earnings = [x for x in safe_lines if x["line_kind"] in ("earning", "allowance", "basic", "one_time_earning")]
    deductions = [x for x in safe_lines if "deduct" in x["line_kind"] or x["line_kind"] == "deduction"]
    # Fallback grouping if kinds vary
    if not earnings and not deductions:
        earnings = [x for x in safe_lines if float(x.get("amount") or 0) >= 0]
        deductions = [x for x in safe_lines if float(x.get("amount") or 0) < 0]
    return {
        "ok": True,
        "payslip": {
            "payslip_id": doc.get("payslip_id"),
            "period_start": doc.get("period_start"),
            "period_end": doc.get("period_end"),
            "version_number": doc.get("version_number"),
            "status": employee_facing_state(doc),
            "released_at": doc.get("employee_released_at"),
            "currency": doc.get("currency"),
            "totals": {
                "earnings": doc.get("totals_earnings"),
                "deductions": doc.get("totals_deductions"),
                "net": doc.get("totals_net"),
            },
            "payment_date": None,
            "money_authority": doc.get("money_authority"),
            "official_document": bool(doc.get("official_document")),
            "official_pdf_eligible": bool(doc.get("official_pdf_eligible")),
            "download_available": bool(doc.get("download_available")),
            "download_kind": doc.get("download_kind"),
            # Source-neutral: the employee is told this is the authoritative released
            # record, not which internal authority mode produced it. Mode A and Mode B
            # both reach here; source authority stays in server metadata and audit.
            "honesty": {
                "en": (
                    "This payslip is released for your records. The PDF is generated from the "
                    "authoritative released payroll record for this version."
                    if doc.get("official_document")
                    else "This payslip summary is released for viewing. An official PDF is not "
                    "available for this payslip."
                ),
                "ar": (
                    "تم إصدار كشف الراتب لسجلاتك. يتم إنشاء ملف PDF من سجل الرواتب المُصدَر "
                    "والمُعتمد لهذه النسخة."
                    if doc.get("official_document")
                    else "تم إصدار ملخص كشف الراتب للعرض. ملف PDF الرسمي غير متاح لهذا الكشف."
                ),
            },
        },
        "lines": safe_lines,
        "earnings": earnings,
        "deductions": deductions,
        "locale": loc,
        **honesty_payload(),
    }


def get_payslip(cur: Any, *, company_code: str, payslip_id: str) -> dict[str, Any] | None:
    ensure_payroll_wave3_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_payslip_documents WHERE company_code=%s AND payslip_id=%s",
        ((company_code or "").upper(), payslip_id),
    )
    return _json_safe(_row(cur) or {}) or None


def list_payslip_lines(cur: Any, *, company_code: str, payslip_id: str) -> list[dict[str, Any]]:
    ensure_payroll_wave3_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_payslip_lines
        WHERE company_code=%s AND payslip_id=%s
        ORDER BY sort_order, code
        """,
        ((company_code or "").upper(), payslip_id),
    )
    return _json_safe(_rows(cur))


def list_payslips(
    cur: Any,
    *,
    company_code: str,
    employee_key: str | None = None,
    source_kind: str | None = None,
    include_history: bool = False,
    allowed_employee_keys: set[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    ensure_payroll_wave3_schema(cur)
    company = (company_code or "").upper()
    statuses = ("active", "replaced", "revoked") if include_history else ("active",)
    cur.execute(
        """
        SELECT payslip_id::text, source_kind, source_run_id::text, employee_key,
               period_start, period_end, version_number, status,
               employee_visibility, employee_released_at, employee_released_by_phone,
               money_authority, authoritative_label, payment_processing,
               currency, totals_earnings, totals_deductions, totals_net,
               content_fingerprint, created_at, updated_at, replaces_payslip_id::text,
               superseded_by::text
        FROM payroll_payslip_documents
        WHERE company_code=%s
          AND status = ANY(%s)
          AND (%s::text IS NULL OR employee_key=%s)
          AND (%s::text IS NULL OR source_kind=%s)
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (
            company,
            list(statuses),
            employee_key,
            employee_key,
            source_kind,
            source_kind,
            max(1, min(int(limit or 50), 200)),
        ),
    )
    rows = _json_safe(_rows(cur))
    if allowed_employee_keys is not None:
        rows = [r for r in rows if str(r.get("employee_key") or "") in allowed_employee_keys]
    return [_annotate_payslip(r) for r in rows]


def list_payslip_history(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    allowed_employee_keys: set[str] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if not _scope_allows(employee_key, allowed_employee_keys):
        return []
    return list_payslips(
        cur,
        company_code=company_code,
        employee_key=employee_key,
        include_history=True,
        allowed_employee_keys=allowed_employee_keys,
        limit=limit,
    )


def list_payslip_events(
    cur: Any,
    *,
    company_code: str,
    payslip_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    ensure_payroll_wave3_schema(cur)
    cur.execute(
        """
        SELECT event_id::text, payslip_id::text, event_type, payload, created_by_phone, created_at
        FROM payroll_payslip_events
        WHERE company_code=%s AND (%s::uuid IS NULL OR payslip_id=%s::uuid)
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (
            (company_code or "").upper(),
            payslip_id,
            payslip_id,
            max(1, min(int(limit or 100), 500)),
        ),
    )
    return _json_safe(_rows(cur))


def download_payslip_document(
    cur: Any,
    *,
    company_code: str,
    payslip_id: str,
    locale: str = "en",
    allowed_employee_keys: set[str] | None = None,
) -> dict[str, Any]:
    doc = get_payslip(cur, company_code=company_code, payslip_id=payslip_id)
    if not doc:
        return {"ok": False, "error": "payslip_not_found"}
    key = str(doc.get("employee_key") or "")
    if not _scope_allows(key, allowed_employee_keys):
        return {"ok": False, "error": "employee_outside_manager_scope"}
    lines = list_payslip_lines(cur, company_code=company_code, payslip_id=payslip_id)
    loc = "ar" if str(locale or "").lower().startswith("ar") else "en"
    payload = doc.get("document_payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    labels = (payload.get("labels") if isinstance(payload, dict) else None) or _labels_for_source(
        str(doc.get("source_kind") or "")
    )
    banner = labels.get("authority_banner_ar" if loc == "ar" else "authority_banner_en")
    title = labels.get("label_ar" if loc == "ar" else "label_en")
    text_lines = [
        title,
        banner,
        f"Employee: {key}",
        f"Period: {doc.get('period_start')} → {doc.get('period_end')}",
        f"Status: {doc.get('status')} · v{doc.get('version_number')}",
        f"Money authority: {doc.get('money_authority')}",
        f"Payment processing: {doc.get('payment_processing')}",
        "",
        "Lines:",
    ]
    for ln in lines:
        label = ln.get("label_ar" if loc == "ar" else "label_en") or ln.get("code")
        text_lines.append(f"  - {ln.get('line_kind')}: {label} = {ln.get('amount')} {ln.get('currency')}")
    text_lines.extend(
        [
            "",
            f"Earnings: {doc.get('totals_earnings')} {doc.get('currency')}",
            f"Deductions: {doc.get('totals_deductions')} {doc.get('currency')}",
            f"Net: {doc.get('totals_net')} {doc.get('currency')}",
            "",
            "This document does not authorize payment.",
        ]
    )
    return {
        "ok": True,
        "payslip": doc,
        "lines": lines,
        "locale": loc,
        "filename": f"payslip-{key}-{doc.get('period_start')}-v{doc.get('version_number')}-{loc}.txt",
        "content_type": "text/plain; charset=utf-8",
        "body": "\n".join(text_lines),
        "json_document": _json_safe({"payslip": doc, "lines": lines, "labels": labels}),
        **honesty_payload(),
    }


def workspace_bootstrap(
    cur: Any,
    *,
    company_code: str,
    allowed_employee_keys: set[str] | None = None,
) -> dict[str, Any]:
    ensure_payroll_wave3_schema(cur)
    payslips = list_payslips(
        cur,
        company_code=company_code,
        include_history=False,
        allowed_employee_keys=allowed_employee_keys,
        limit=40,
    )
    events = list_payslip_events(cur, company_code=company_code, limit=30)
    preview_runs = []
    import_runs = []
    try:
        if w2b.payroll_wave2b_enabled_for_company(company_code):
            preview_runs = w2b.list_preview_runs(cur, company_code=company_code, limit=20)
    except Exception:  # noqa: BLE001
        preview_runs = []
    try:
        if w2a.payroll_wave2a_enabled_for_company(company_code):
            import_runs = w2a.list_import_runs(cur, company_code=company_code, limit=20)
    except Exception:  # noqa: BLE001
        import_runs = []
    return {
        "ok": True,
        "payslips": payslips,
        "events": events,
        "preview_runs": preview_runs,
        "import_runs": import_runs,
        "manager_scoped": allowed_employee_keys is not None,
        **honesty_payload(),
    }
