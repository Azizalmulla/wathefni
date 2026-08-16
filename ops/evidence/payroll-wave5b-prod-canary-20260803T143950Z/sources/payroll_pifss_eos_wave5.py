"""Payroll Wave 5 — PIFSS + EOS review worksheets (staging).

Counsel-gated statutory rule tables and non-authoritative review worksheets.

Does NOT: remittance, statutory filing, automatic legal-compliance claims,
automatic payable instructions, bank/WPS/AS'HAL, payment_processing, AI,
or mutate Wave 1–4 flows. Native remains non-authoritative; external remains money authority.
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

PAYROLL_WAVE5_VERSION = "1.0.0"
PIFSS_WORKSHEET_SCHEMA = "payroll_pifss_worksheet@1.0.0"
EOS_WORKSHEET_SCHEMA = "payroll_eos_worksheet@1.0.0"

_ON = {"1", "true", "yes", "on"}
MONEY_Q = Decimal("0.001")

DEFAULT_SYNTHETIC_KEY_MARKERS = (
    "PYW5",
    "PYW5-SYNTH|",
    "PYW4",
    "PYW4-SYNTH|",
    "PYW3",
    "PYW3-SYNTH|",
    "PYW1",
    "PYW1-SYNTH|",
    "W5",
)
DEFAULT_SYNTHETIC_PHONE_PREFIXES = ("965541", "965540", "965539")

CATEGORIES = ("kuwaiti_national", "gcc_national", "expatriate")
RULE_DOMAINS = ("pifss", "eos")
COUNSEL_STATUSES = ("pending", "approved", "revoked", "unsupported")
ART_STATUSES = ("resolved", "unresolved_blocked", "counsel_required", "not_applicable")
ACTIVE_WS_STATUSES = (
    "draft",
    "in_review",
    "exception",
    "approved",
    "unsupported",
    "counsel_required",
)

KIND_PIFSS = "pifss"
KIND_EOS = "eos"
KIND_RULE = "rule_table"

SCHEMA_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_pifss_eos_wave5_v1.sql"
SCHEMA_SQL = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
_SCHEMA_READY = False


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _ON


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def payroll_wave5_enabled() -> bool:
    return _env_bool("WATHEFNI_PAYROLL_WAVE5", default=False)


def payroll_wave5_enabled_for_company(company_code: str | None) -> bool:
    if not payroll_wave5_enabled():
        return False
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE5_COMPANIES") or "WATHEFNI").strip()
    allowed = {p.strip().upper() for p in raw.split(",") if p.strip()}
    return (company_code or "").upper() in allowed


def payroll_wave5_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_ONLY")
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and (raw is None or str(raw).strip() == ""):
        return True
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _ON


def synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_KEY_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_KEY_MARKERS


def synthetic_phone_prefixes() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_PHONE_PREFIXES") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_PHONE_PREFIXES
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_PHONE_PREFIXES


def is_wave5_synthetic_employee(*, employee_key: str | None = None, phone: str | None = None) -> bool:
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
        "payroll_wave5_version": PAYROLL_WAVE5_VERSION,
        "pifss_worksheet_schema": PIFSS_WORKSHEET_SCHEMA,
        "eos_worksheet_schema": EOS_WORKSHEET_SCHEMA,
        "payment_processing": "disabled",
        "posts_payment": False,
        "remittance": False,
        "statutory_filing": False,
        "automatic_legal_compliance_claim": False,
        "pifss_worksheets": True,
        "pifss_remittance": False,
        "eos_worksheets": True,
        "eos_auto_payable": False,
        "bank_files": False,
        "wps": False,
        "ashal": False,
        "ai_calculations": False,
        "native_results_authoritative": False,
        "external_payroll_authority": "external",
        "wave1_flows_unchanged": True,
        "wave2a_flows_unchanged": True,
        "wave2b_flows_unchanged": True,
        "wave3_flows_unchanged": True,
        "wave4_flows_unchanged": True,
        "synthetic_only": payroll_wave5_synthetic_only(),
    }


def freeze_invariants() -> dict[str, Any]:
    return {
        "payment_processing_hard_disabled": True,
        "category_separation": True,
        "missing_rule_fail_closed": True,
        "effective_dated_rules": True,
        "dual_approval_override": True,
        "approved_history_immutable": True,
        "no_silent_unresolved_calc": True,
        "no_remittance": True,
        "no_auto_payable": True,
        "no_statutory_filing": True,
        "no_automatic_legal_compliance_claim": True,
        "no_bank_wps_ashal": True,
        "no_ai": True,
        "native_non_authoritative": True,
        "external_authority_retained": True,
        "wave1_ddl_untouched": True,
        "wave2a_ddl_untouched": True,
        "wave2b_ddl_untouched": True,
        "wave3_ddl_untouched": True,
        "wave4_ddl_untouched": True,
    }


def ensure_payroll_wave5_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    if not SCHEMA_SQL.strip():
        _SCHEMA_READY = True
        return
    lock_id = 770_900_006
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        cur.execute("SET LOCAL lock_timeout = '15s'")
        pyw1.ensure_payroll_wave1_schema(cur)
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


def _phones_equal(a: Any, b: Any) -> bool:
    da, db = digits_phone(a), digits_phone(b)
    return bool(da) and bool(db) and da == db


def _refuse_nonsynthetic(
    *,
    employee_key: str,
    phone: str | None = None,
    allowed_employee_keys: list[str] | None = None,
) -> dict[str, Any] | None:
    if not payroll_wave5_synthetic_only():
        return None
    if allowed_employee_keys is not None:
        allowed = {str(k) for k in allowed_employee_keys}
        if str(employee_key) not in allowed:
            return {"ok": False, "error": "payroll_wave5_synthetic_only", "employee_key": employee_key}
    if not is_wave5_synthetic_employee(employee_key=employee_key, phone=phone):
        return {"ok": False, "error": "payroll_wave5_synthetic_only", "employee_key": employee_key}
    return None


def _record_event(
    cur: Any,
    *,
    company_code: str,
    worksheet_kind: str,
    worksheet_id: str | None,
    event_type: str,
    payload: dict[str, Any],
    actor_phone: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO payroll_statutory_worksheet_events (
          company_code, worksheet_kind, worksheet_id, event_type, payload, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s::jsonb,%s)
        """,
        (
            (company_code or "").upper(),
            worksheet_kind,
            worksheet_id,
            event_type,
            json.dumps(_json_safe(payload)),
            digits_phone(actor_phone),
        ),
    )


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _normalize_category(category: Any) -> str:
    return str(category or "").strip().lower()


def _normalize_domain(domain: Any) -> str:
    return str(domain or "").strip().lower()


def _ws_table(kind: str) -> str | None:
    k = str(kind or "").strip().lower()
    if k == KIND_PIFSS:
        return "payroll_pifss_worksheets"
    if k == KIND_EOS:
        return "payroll_eos_worksheets"
    return None


# --------------------------------------------------------------------------- rule tables


def upsert_rule_table(
    cur: Any,
    *,
    company_code: str,
    rule_domain: str,
    rule_code: str,
    employee_category: str,
    version_label: str,
    effective_from: Any,
    effective_to: Any = None,
    counsel_status: str = "pending",
    source_citation: str,
    provenance: dict[str, Any] | None = None,
    rule_payload: dict[str, Any] | None = None,
    actor: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave5_schema(cur)
    company = (company_code or "").upper()
    domain = _normalize_domain(rule_domain)
    category = _normalize_category(employee_category)
    status = str(counsel_status or "pending").strip().lower()
    code = str(rule_code or "").strip()
    version = str(version_label or "").strip()
    citation = str(source_citation or "").strip()
    actor_p = digits_phone(actor_phone or actor)
    if domain not in RULE_DOMAINS:
        return {"ok": False, "error": "invalid_rule_domain"}
    if category not in CATEGORIES and category != "any":
        return {"ok": False, "error": "invalid_employee_category"}
    if status not in COUNSEL_STATUSES:
        return {"ok": False, "error": "invalid_counsel_status"}
    if not code or not version or not citation:
        return {"ok": False, "error": "rule_fields_required"}
    eff_from = _as_date(effective_from)
    eff_to = _as_date(effective_to)
    if not eff_from:
        return {"ok": False, "error": "effective_from_required"}
    if eff_to is not None and eff_to < eff_from:
        return {"ok": False, "error": "invalid_effective_dates"}

    payload = dict(rule_payload or {})
    prov = dict(provenance or {})
    prov.setdefault("upsert_reason", str(reason).strip())
    prov.setdefault("actor_phone", actor_p)

    cur.execute(
        """
        INSERT INTO payroll_statutory_rule_tables (
          company_code, rule_domain, rule_code, employee_category, version_label,
          effective_from, effective_to, counsel_status, source_citation,
          provenance, rule_payload, decision_note, created_by_phone
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s
        )
        ON CONFLICT (company_code, rule_domain, rule_code, employee_category, version_label)
        DO UPDATE SET
          effective_from=EXCLUDED.effective_from,
          effective_to=EXCLUDED.effective_to,
          counsel_status=EXCLUDED.counsel_status,
          source_citation=EXCLUDED.source_citation,
          provenance=EXCLUDED.provenance,
          rule_payload=EXCLUDED.rule_payload,
          decision_note=EXCLUDED.decision_note,
          row_version=payroll_statutory_rule_tables.row_version+1,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            domain,
            code,
            category,
            version,
            eff_from,
            eff_to,
            status,
            citation,
            json.dumps(_json_safe(prov)),
            json.dumps(_json_safe(payload)),
            str(reason).strip(),
            actor_p,
        ),
    )
    row = _row(cur) or {}
    _record_event(
        cur,
        company_code=company,
        worksheet_kind=KIND_RULE,
        worksheet_id=str(row.get("rule_table_id")),
        event_type="rule_table_upserted",
        payload={
            "reason": reason,
            "rule_domain": domain,
            "rule_code": code,
            "employee_category": category,
            "version_label": version,
            "counsel_status": status,
        },
        actor_phone=actor_p,
    )
    return {"ok": True, "rule_table": _json_safe(row), **honesty_payload()}


def counsel_approve_rule_table(
    cur: Any,
    *,
    company_code: str,
    rule_table_id: str,
    actor: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
    actor_permissions: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    perms = set(actor_permissions or [])
    if perms and "payroll.approve" not in perms and "payroll.manage" not in perms:
        return {"ok": False, "error": "payroll_manage_or_approve_required"}
    ensure_payroll_wave5_schema(cur)
    company = (company_code or "").upper()
    actor_p = digits_phone(actor_phone or actor)
    cur.execute(
        "SELECT * FROM payroll_statutory_rule_tables WHERE company_code=%s AND rule_table_id=%s",
        (company, rule_table_id),
    )
    row = _row(cur)
    if not row:
        return {"ok": False, "error": "rule_table_not_found"}
    if str(row.get("counsel_status")) == "revoked":
        return {"ok": False, "error": "rule_table_revoked"}
    if str(row.get("counsel_status")) == "unsupported":
        return {"ok": False, "error": "rule_table_unsupported"}
    cur.execute(
        """
        UPDATE payroll_statutory_rule_tables
        SET counsel_status='approved',
            counsel_approved_by_phone=%s,
            counsel_approved_at=now(),
            decision_note=%s,
            row_version=row_version+1,
            updated_at=now()
        WHERE company_code=%s AND rule_table_id=%s
          AND counsel_status IN ('pending','approved')
        RETURNING *
        """,
        (actor_p, str(reason).strip(), company, rule_table_id),
    )
    updated = _row(cur)
    if not updated:
        return {"ok": False, "error": "counsel_approve_failed"}
    _record_event(
        cur,
        company_code=company,
        worksheet_kind=KIND_RULE,
        worksheet_id=str(rule_table_id),
        event_type="rule_table_counsel_approved",
        payload={"reason": reason},
        actor_phone=actor_p,
    )
    return {"ok": True, "rule_table": _json_safe(updated), **honesty_payload()}


def resolve_rule_table(
    cur: Any,
    *,
    company_code: str,
    rule_domain: str,
    employee_category: str,
    as_of_date: Any,
    rule_code: str | None = None,
) -> dict[str, Any] | None:
    ensure_payroll_wave5_schema(cur)
    company = (company_code or "").upper()
    domain = _normalize_domain(rule_domain)
    category = _normalize_category(employee_category)
    as_of = _as_date(as_of_date) or date.today()
    code = str(rule_code or "").strip() or None
    cur.execute(
        """
        SELECT * FROM payroll_statutory_rule_tables
        WHERE company_code=%s
          AND rule_domain=%s
          AND employee_category=%s
          AND counsel_status='approved'
          AND effective_from <= %s
          AND (effective_to IS NULL OR effective_to >= %s)
          AND (%s::text IS NULL OR rule_code=%s)
        ORDER BY effective_from DESC, created_at DESC
        LIMIT 1
        """,
        (company, domain, category, as_of, as_of, code, code),
    )
    row = _row(cur)
    return _json_safe(row) if row else None


def list_rule_tables(
    cur: Any,
    *,
    company_code: str,
    rule_domain: str | None = None,
    employee_category: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    ensure_payroll_wave5_schema(cur)
    company = (company_code or "").upper()
    domain = _normalize_domain(rule_domain) if rule_domain else None
    category = _normalize_category(employee_category) if employee_category else None
    cur.execute(
        """
        SELECT * FROM payroll_statutory_rule_tables
        WHERE company_code=%s
          AND (%s::text IS NULL OR rule_domain=%s)
          AND (%s::text IS NULL OR employee_category=%s)
        ORDER BY effective_from DESC, created_at DESC
        LIMIT %s
        """,
        (
            company,
            domain,
            domain,
            category,
            category,
            max(1, min(int(limit or 50), 200)),
        ),
    )
    return _json_safe(_rows(cur))


# --------------------------------------------------------------------------- PIFSS calc helpers


def _pifss_input_fingerprint(
    *,
    company: str,
    employee_key: str,
    employee_category: str,
    period_start: date,
    period_end: date,
    contributory_salary: Decimal,
) -> str:
    return fingerprint_payload(
        {
            "company_code": company,
            "employee_key": employee_key,
            "employee_category": employee_category,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "contributory_salary": str(contributory_salary),
        }
    )


def _compute_pifss_review(
    *,
    contributory_salary: Decimal,
    rule: dict[str, Any],
) -> dict[str, Any]:
    payload = rule.get("rule_payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    employer_rate = Decimal(str(payload.get("employer_rate") or 0))
    employee_rate = Decimal(str(payload.get("employee_rate") or 0))
    ceiling = money3(payload.get("ceiling_kwd") or payload.get("ceiling") or 0)
    currency = str(payload.get("currency") or "KWD")
    salary = money3(contributory_salary)
    capped = salary if ceiling <= 0 else min(salary, ceiling)
    employer_amt = money3(capped * employer_rate)
    employee_amt = money3(capped * employee_rate)
    return {
        "posture": "review_only",
        "not_remittance": True,
        "not_compliance_claim": True,
        "currency": currency,
        "contributory_salary": salary,
        "ceiling_kwd": ceiling,
        "capped_salary": capped,
        "employer_rate": float(employer_rate),
        "employee_rate": float(employee_rate),
        "provisional_employer_contribution": employer_amt,
        "provisional_employee_contribution": employee_amt,
        "provisional_total": money3(employer_amt + employee_amt),
        "label": "REVIEW_ONLY_NOT_REMITTANCE_NOT_COMPLIANCE_CLAIM",
        "rule_version_label": rule.get("version_label"),
        "source_citation": rule.get("source_citation"),
        "rule_table_id": str(rule.get("rule_table_id")),
    }


def generate_pifss_worksheet(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    employee_category: str,
    period_start: Any,
    period_end: Any,
    contributory_salary: Any,
    actor: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
    inputs_provenance: dict[str, Any] | None = None,
    allowed_employee_keys: list[str] | None = None,
    rule_code: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    refused = _refuse_nonsynthetic(
        employee_key=employee_key,
        phone=actor_phone or actor,
        allowed_employee_keys=allowed_employee_keys,
    )
    if refused:
        return refused
    ensure_payroll_wave5_schema(cur)
    company = (company_code or "").upper()
    category = _normalize_category(employee_category)
    actor_p = digits_phone(actor_phone or actor)
    ek = str(employee_key or "").strip()
    if category not in CATEGORIES:
        return {"ok": False, "error": "invalid_employee_category", "allowed": list(CATEGORIES)}
    ps = _as_date(period_start)
    pe = _as_date(period_end)
    if not ps or not pe or pe < ps:
        return {"ok": False, "error": "invalid_period"}
    salary = money3(contributory_salary)
    input_fp = _pifss_input_fingerprint(
        company=company,
        employee_key=ek,
        employee_category=category,
        period_start=ps,
        period_end=pe,
        contributory_salary=salary,
    )

    # Idempotent active worksheet with same input fingerprint
    cur.execute(
        """
        SELECT * FROM payroll_pifss_worksheets
        WHERE company_code=%s AND employee_key=%s AND period_start=%s AND period_end=%s
          AND status = ANY(%s) AND input_fingerprint=%s
        ORDER BY created_at DESC LIMIT 1
        """,
        (company, ek, ps, pe, list(ACTIVE_WS_STATUSES), input_fp),
    )
    existing = _row(cur)
    if existing:
        return {
            "ok": True,
            "idempotent": True,
            "worksheet": _json_safe(existing),
            **honesty_payload(),
        }

    # Conflict: different fingerprint already active for same period key
    cur.execute(
        """
        SELECT * FROM payroll_pifss_worksheets
        WHERE company_code=%s AND employee_key=%s AND period_start=%s AND period_end=%s
          AND status = ANY(%s)
        ORDER BY created_at DESC LIMIT 1
        """,
        (company, ek, ps, pe, list(ACTIVE_WS_STATUSES)),
    )
    active = _row(cur)
    if active and str(active.get("input_fingerprint")) != input_fp:
        return {
            "ok": False,
            "error": "active_worksheet_exists",
            "hint": "use recalculate_pifss",
            "worksheet": _json_safe(active),
            **honesty_payload(),
        }

    honesty = {
        "money_authority": "review_non_authoritative",
        "payment_processing": "disabled",
        "posts_payment": False,
        "remittance": False,
        "statutory_filing": False,
        "automatic_legal_compliance_claim": False,
        "authoritative_label": "review_worksheet_only",
    }
    provenance = {
        "inputs": {
            "employee_key": ek,
            "employee_category": category,
            "period_start": ps.isoformat(),
            "period_end": pe.isoformat(),
            "contributory_salary": str(salary),
        },
        "input_fingerprint": input_fp,
        "caller_provenance": dict(inputs_provenance or {}),
        "honesty": honesty_payload(),
    }

    status = "draft"
    rule = None
    worksheet_payload: dict[str, Any] = {
        "schema": PIFSS_WORKSHEET_SCHEMA,
        "posture": "review_only",
        "not_remittance": True,
        "not_compliance_claim": True,
        "employee_category": category,
    }
    error: str | None = None

    if category == "expatriate":
        status = "unsupported"
        worksheet_payload.update(
            {
                "explanation": "No Kuwait PIFSS contribution applies to expatriate (non-GCC) employees.",
                "pifss_applicable": False,
                "provisional_employer_contribution": money3(0),
                "provisional_employee_contribution": money3(0),
            }
        )
        provenance["category_separation"] = "expatriate_no_pifss"
        error = "expatriate_no_pifss"
    elif category == "gcc_national":
        rule = resolve_rule_table(
            cur,
            company_code=company,
            rule_domain=KIND_PIFSS,
            employee_category=category,
            as_of_date=pe,
            rule_code=rule_code,
        )
        if not rule:
            status = "counsel_required"
            worksheet_payload.update(
                {
                    "explanation": "GCC-national PIFSS/home-scheme rates require counsel-approved rule table.",
                    "pifss_applicable": True,
                    "counsel_required": True,
                }
            )
            provenance["missing_rule"] = True
            error = "counsel_required_rule"
        else:
            worksheet_payload.update(_compute_pifss_review(contributory_salary=salary, rule=rule))
            provenance["rule"] = {
                "rule_table_id": rule.get("rule_table_id"),
                "version_label": rule.get("version_label"),
                "source_citation": rule.get("source_citation"),
            }
    else:  # kuwaiti_national
        rule = resolve_rule_table(
            cur,
            company_code=company,
            rule_domain=KIND_PIFSS,
            employee_category=category,
            as_of_date=pe,
            rule_code=rule_code,
        )
        if not rule:
            status = "counsel_required"
            worksheet_payload.update(
                {
                    "explanation": "Kuwaiti PIFSS rates require counsel-approved effective-dated rule table.",
                    "pifss_applicable": True,
                    "counsel_required": True,
                }
            )
            provenance["missing_rule"] = True
            error = "counsel_required_rule"
        else:
            worksheet_payload.update(_compute_pifss_review(contributory_salary=salary, rule=rule))
            provenance["rule"] = {
                "rule_table_id": rule.get("rule_table_id"),
                "version_label": rule.get("version_label"),
                "source_citation": rule.get("source_citation"),
            }

    content_fp = fingerprint_payload(worksheet_payload)
    cur.execute(
        """
        INSERT INTO payroll_pifss_worksheets (
          company_code, employee_key, employee_category, period_start, period_end,
          status, rule_table_id, rule_version_label, input_fingerprint, content_fingerprint,
          source_provenance, worksheet_payload, decision_note, created_by_phone
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s
        ) RETURNING *
        """,
        (
            company,
            ek,
            category,
            ps,
            pe,
            status,
            (rule or {}).get("rule_table_id"),
            (rule or {}).get("version_label"),
            input_fp,
            content_fp,
            json.dumps(_json_safe(provenance)),
            json.dumps(_json_safe(worksheet_payload)),
            str(reason).strip(),
            actor_p,
        ),
    )
    row = _row(cur) or {}
    _record_event(
        cur,
        company_code=company,
        worksheet_kind=KIND_PIFSS,
        worksheet_id=str(row.get("worksheet_id")),
        event_type="pifss_worksheet_generated",
        payload={"reason": reason, "status": status, "error": error, "input_fingerprint": input_fp},
        actor_phone=actor_p,
    )
    result: dict[str, Any] = {
        "ok": error is None and status in ("draft", "unsupported"),
        "worksheet": _json_safe(row),
        **honesty_payload(),
    }
    # unsupported is a successful create of an explanatory worksheet
    if status == "unsupported":
        result["ok"] = True
        result["error"] = error
    elif error:
        result["ok"] = False
        result["error"] = error
    return result


# --------------------------------------------------------------------------- EOS calc helpers


def _service_years(service_start: date, service_end: date) -> Decimal:
    days = (service_end - service_start).days + 1
    return (Decimal(days) / Decimal("365.25")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _compute_eos_art51_review(
    *,
    monthly_wage: Decimal,
    pay_type: str,
    service_start: date,
    service_end: date,
    rule: dict[str, Any],
) -> dict[str, Any]:
    payload = rule.get("rule_payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    days_first = Decimal(str(payload.get("days_first_5_years") or (15 if pay_type == "monthly" else 10)))
    days_after = Decimal(
        str(
            payload.get("days_after_5_years")
            or payload.get("days_thereafter")
            or (30 if pay_type == "monthly" else 15)
        )
    )
    cap_years = Decimal(str(payload.get("cap_years_wage") or payload.get("cap_years") or (1.5 if pay_type == "monthly" else 1)))
    years = _service_years(service_start, service_end)
    first = min(years, Decimal("5"))
    thereafter = max(years - Decimal("5"), Decimal("0"))
    daily_wage = money3(monthly_wage / Decimal("30"))
    indemnity_days = (first * days_first) + (thereafter * days_after)
    provisional = money3(daily_wage * indemnity_days)
    cap_amount = money3(monthly_wage * cap_years)
    if provisional > cap_amount:
        provisional = cap_amount
    return {
        "posture": "review_only",
        "not_payable_instruction": True,
        "automatic_payable_instruction": False,
        "pay_type": pay_type,
        "monthly_wage": monthly_wage,
        "daily_wage": daily_wage,
        "service_years": float(years),
        "years_first_5": float(first),
        "years_thereafter": float(thereafter),
        "days_first_5_years": float(days_first),
        "days_after_5_years": float(days_after),
        "indemnity_days": float(indemnity_days),
        "cap_years_wage": float(cap_years),
        "cap_amount": cap_amount,
        "provisional_eos_amount": provisional,
        "label": "REVIEW_ONLY_NOT_PAYABLE_INSTRUCTION",
        "rule_version_label": rule.get("version_label"),
        "source_citation": rule.get("source_citation"),
        "rule_table_id": str(rule.get("rule_table_id")),
        "art_basis": "art_51_structure_provisional",
    }


def _eos_input_fingerprint(
    *,
    company: str,
    employee_key: str,
    employee_category: str,
    termination_date: date,
    termination_reason: str,
    service_start: date,
    service_end: date,
    monthly_wage: Decimal,
    pay_type: str,
    art_51_53_status: str,
    law_17_2018_status: str,
) -> str:
    return fingerprint_payload(
        {
            "company_code": company,
            "employee_key": employee_key,
            "employee_category": employee_category,
            "termination_date": termination_date.isoformat(),
            "termination_reason": termination_reason,
            "service_start": service_start.isoformat(),
            "service_end": service_end.isoformat(),
            "monthly_wage": str(monthly_wage),
            "pay_type": pay_type,
            "art_51_53_status": art_51_53_status,
            "law_17_2018_status": law_17_2018_status,
        }
    )


def generate_eos_worksheet(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    employee_category: str,
    termination_date: Any,
    termination_reason: str,
    service_start: Any,
    service_end: Any,
    monthly_wage: Any,
    pay_type: str = "monthly",
    art_51_53_status: str = "unresolved_blocked",
    law_17_2018_status: str = "unresolved_blocked",
    actor: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
    inputs_provenance: dict[str, Any] | None = None,
    allowed_employee_keys: list[str] | None = None,
    rule_code: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    refused = _refuse_nonsynthetic(
        employee_key=employee_key,
        phone=actor_phone or actor,
        allowed_employee_keys=allowed_employee_keys,
    )
    if refused:
        return refused
    ensure_payroll_wave5_schema(cur)
    company = (company_code or "").upper()
    category = _normalize_category(employee_category)
    actor_p = digits_phone(actor_phone or actor)
    ek = str(employee_key or "").strip()
    if category not in CATEGORIES:
        return {"ok": False, "error": "invalid_employee_category", "allowed": list(CATEGORIES)}
    term_d = _as_date(termination_date)
    svc_start = _as_date(service_start)
    svc_end = _as_date(service_end)
    if not term_d or not svc_start or not svc_end or svc_end < svc_start:
        return {"ok": False, "error": "invalid_service_or_termination_dates"}
    pt = str(pay_type or "monthly").strip().lower()
    if pt not in ("monthly", "daily"):
        return {"ok": False, "error": "invalid_pay_type"}
    art = str(art_51_53_status or "unresolved_blocked").strip().lower()
    law17 = str(law_17_2018_status or "unresolved_blocked").strip().lower()
    if art not in ART_STATUSES or law17 not in ART_STATUSES:
        return {"ok": False, "error": "invalid_art_or_law_status"}
    term_reason = str(termination_reason or "").strip()
    if not term_reason:
        return {"ok": False, "error": "termination_reason_required"}
    wage = money3(monthly_wage)
    input_fp = _eos_input_fingerprint(
        company=company,
        employee_key=ek,
        employee_category=category,
        termination_date=term_d,
        termination_reason=term_reason,
        service_start=svc_start,
        service_end=svc_end,
        monthly_wage=wage,
        pay_type=pt,
        art_51_53_status=art,
        law_17_2018_status=law17,
    )

    cur.execute(
        """
        SELECT * FROM payroll_eos_worksheets
        WHERE company_code=%s AND employee_key=%s AND termination_date=%s
          AND status = ANY(%s) AND input_fingerprint=%s
        ORDER BY created_at DESC LIMIT 1
        """,
        (company, ek, term_d, list(ACTIVE_WS_STATUSES), input_fp),
    )
    existing = _row(cur)
    if existing:
        return {
            "ok": True,
            "idempotent": True,
            "worksheet": _json_safe(existing),
            **honesty_payload(),
        }

    cur.execute(
        """
        SELECT * FROM payroll_eos_worksheets
        WHERE company_code=%s AND employee_key=%s AND termination_date=%s
          AND status = ANY(%s)
        ORDER BY created_at DESC LIMIT 1
        """,
        (company, ek, term_d, list(ACTIVE_WS_STATUSES)),
    )
    active = _row(cur)
    if active and str(active.get("input_fingerprint")) != input_fp:
        return {
            "ok": False,
            "error": "active_worksheet_exists",
            "hint": "use recalculate_eos",
            "worksheet": _json_safe(active),
            **honesty_payload(),
        }

    service_evidence = {
        "service_start": svc_start.isoformat(),
        "service_end": svc_end.isoformat(),
        "termination_date": term_d.isoformat(),
        "termination_reason": term_reason,
        "service_years": float(_service_years(svc_start, svc_end)),
        "evidence_source": dict(inputs_provenance or {}),
    }
    provenance = {
        "inputs": {
            "employee_key": ek,
            "employee_category": category,
            "monthly_wage": str(wage),
            "pay_type": pt,
            "art_51_53_status": art,
            "law_17_2018_status": law17,
        },
        "input_fingerprint": input_fp,
        "service_period_evidence": service_evidence,
        "honesty": honesty_payload(),
    }
    worksheet_payload: dict[str, Any] = {
        "schema": EOS_WORKSHEET_SCHEMA,
        "posture": "review_only",
        "not_payable_instruction": True,
        "automatic_payable_instruction": False,
        "employee_category": category,
        "termination_reason": term_reason,
    }
    status = "draft"
    rule = None
    error: str | None = None
    blocked = False

    # Block unresolved Art 51/53
    if art in ("unresolved_blocked", "counsel_required"):
        blocked = True
    # Kuwaiti + Law 17/2018 unresolved
    if category == "kuwaiti_national" and law17 in ("unresolved_blocked", "counsel_required"):
        blocked = True
    # Expatriate resignation without resolved Art 53
    reason_l = term_reason.lower()
    is_resignation = "resign" in reason_l
    if category == "expatriate" and is_resignation and art != "resolved":
        blocked = True

    if blocked:
        status = "counsel_required" if art == "counsel_required" or (
            category == "kuwaiti_national" and law17 == "counsel_required"
        ) else "counsel_required"
        # Prefer counsel_required; use unsupported only when explicitly marked unsupported path
        if art == "not_applicable" and category == "expatriate" and is_resignation:
            status = "unsupported"
        worksheet_payload.update(
            {
                "blocked": True,
                "explanation": "Unresolved Art. 51/53 and/or Law 17/2018 — no EOS payable computation.",
                "art_51_53_status": art,
                "law_17_2018_status": law17,
            }
        )
        provenance["blocked_unresolved_eos_case"] = True
        error = "blocked_unresolved_eos_case"
    else:
        rule = resolve_rule_table(
            cur,
            company_code=company,
            rule_domain=KIND_EOS,
            employee_category=category,
            as_of_date=term_d,
            rule_code=rule_code,
        )
        if not rule:
            status = "counsel_required"
            worksheet_payload.update(
                {
                    "blocked": True,
                    "explanation": "EOS Art. 51 structure requires counsel-approved effective-dated rule table.",
                    "counsel_required": True,
                }
            )
            provenance["missing_rule"] = True
            error = "counsel_required_rule"
        else:
            worksheet_payload.update(
                _compute_eos_art51_review(
                    monthly_wage=wage,
                    pay_type=pt,
                    service_start=svc_start,
                    service_end=svc_end,
                    rule=rule,
                )
            )
            provenance["rule"] = {
                "rule_table_id": rule.get("rule_table_id"),
                "version_label": rule.get("version_label"),
                "source_citation": rule.get("source_citation"),
            }

    content_fp = fingerprint_payload(worksheet_payload)
    cur.execute(
        """
        INSERT INTO payroll_eos_worksheets (
          company_code, employee_key, employee_category, termination_date, termination_reason,
          service_start, service_end, status, rule_table_id, rule_version_label,
          art_51_53_status, law_17_2018_status, input_fingerprint, content_fingerprint,
          source_provenance, service_period_evidence, worksheet_payload,
          decision_note, created_by_phone
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s
        ) RETURNING *
        """,
        (
            company,
            ek,
            category,
            term_d,
            term_reason,
            svc_start,
            svc_end,
            status,
            (rule or {}).get("rule_table_id"),
            (rule or {}).get("version_label"),
            art,
            law17,
            input_fp,
            content_fp,
            json.dumps(_json_safe(provenance)),
            json.dumps(_json_safe(service_evidence)),
            json.dumps(_json_safe(worksheet_payload)),
            str(reason).strip(),
            actor_p,
        ),
    )
    row = _row(cur) or {}
    _record_event(
        cur,
        company_code=company,
        worksheet_kind=KIND_EOS,
        worksheet_id=str(row.get("worksheet_id")),
        event_type="eos_worksheet_generated",
        payload={"reason": reason, "status": status, "error": error, "input_fingerprint": input_fp},
        actor_phone=actor_p,
    )
    result: dict[str, Any] = {"ok": error is None, "worksheet": _json_safe(row), **honesty_payload()}
    if error:
        result["ok"] = False
        result["error"] = error
    return result


# --------------------------------------------------------------------------- get / list


def get_worksheet(
    cur: Any,
    *,
    company_code: str,
    kind: str,
    worksheet_id: str,
) -> dict[str, Any] | None:
    ensure_payroll_wave5_schema(cur)
    table = _ws_table(kind)
    if not table:
        return None
    cur.execute(
        f"SELECT * FROM {table} WHERE company_code=%s AND worksheet_id=%s",
        ((company_code or "").upper(), worksheet_id),
    )
    row = _row(cur)
    return _json_safe(row) if row else None


def list_pifss_worksheets(
    cur: Any,
    *,
    company_code: str,
    employee_key: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    ensure_payroll_wave5_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        """
        SELECT * FROM payroll_pifss_worksheets
        WHERE company_code=%s AND (%s::text IS NULL OR employee_key=%s)
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (company, employee_key, employee_key, max(1, min(int(limit or 50), 200))),
    )
    return _json_safe(_rows(cur))


def list_eos_worksheets(
    cur: Any,
    *,
    company_code: str,
    employee_key: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    ensure_payroll_wave5_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        """
        SELECT * FROM payroll_eos_worksheets
        WHERE company_code=%s AND (%s::text IS NULL OR employee_key=%s)
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (company, employee_key, employee_key, max(1, min(int(limit or 50), 200))),
    )
    return _json_safe(_rows(cur))


def list_events(
    cur: Any,
    *,
    company_code: str,
    worksheet_kind: str | None = None,
    worksheet_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    ensure_payroll_wave5_schema(cur)
    company = (company_code or "").upper()
    kind = str(worksheet_kind or "").strip().lower() or None
    cur.execute(
        """
        SELECT event_id::text, worksheet_kind, worksheet_id::text, event_type,
               payload, created_by_phone, created_at
        FROM payroll_statutory_worksheet_events
        WHERE company_code=%s
          AND (%s::text IS NULL OR worksheet_kind=%s)
          AND (%s::uuid IS NULL OR worksheet_id=%s::uuid)
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (
            company,
            kind,
            kind,
            worksheet_id,
            worksheet_id,
            max(1, min(int(limit or 100), 500)),
        ),
    )
    return _json_safe(_rows(cur))


# --------------------------------------------------------------------------- review / approve


def submit_worksheet_for_review(
    cur: Any,
    *,
    kind: str,
    company_code: str,
    worksheet_id: str,
    actor: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
    expected_row_version: Any = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    table = _ws_table(kind)
    if not table:
        return {"ok": False, "error": "invalid_worksheet_kind"}
    ws = get_worksheet(cur, company_code=company_code, kind=kind, worksheet_id=worksheet_id)
    if not ws:
        return {"ok": False, "error": "worksheet_not_found"}
    if str(ws.get("status")) == "approved":
        return {"ok": False, "error": "approved_worksheet_immutable", "worksheet_id": worksheet_id}
    if str(ws.get("status")) != "draft":
        return {"ok": False, "error": "invalid_worksheet_transition", "status": ws.get("status")}
    if expected_row_version is not None:
        conc = pyw1.require_concurrency(
            expected_row_version=expected_row_version, actual_row_version=ws.get("row_version")
        )
        if conc:
            return conc
    company = (company_code or "").upper()
    actor_p = digits_phone(actor_phone or actor)
    rv = int(expected_row_version) if expected_row_version is not None else int(ws.get("row_version") or 1)
    cur.execute(
        f"""
        UPDATE {table}
        SET status='in_review', submitted_by_phone=%s, submitted_at=now(),
            decision_note=%s, row_version=row_version+1, updated_at=now()
        WHERE company_code=%s AND worksheet_id=%s AND status='draft' AND row_version=%s
        RETURNING *
        """,
        (actor_p, str(reason).strip(), company, worksheet_id, rv),
    )
    updated = _row(cur)
    if not updated:
        return {"ok": False, "error": "stale_row_version_or_bad_status"}
    _record_event(
        cur,
        company_code=company,
        worksheet_kind=str(kind).strip().lower(),
        worksheet_id=worksheet_id,
        event_type="submitted_for_review",
        payload={"reason": reason},
        actor_phone=actor_p,
    )
    return {"ok": True, "worksheet": _json_safe(updated), **honesty_payload()}


def approve_worksheet(
    cur: Any,
    *,
    kind: str,
    company_code: str,
    worksheet_id: str,
    actor: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
    expected_row_version: Any = None,
    actor_permissions: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    perms = set(actor_permissions or [])
    if perms and "payroll.approve" not in perms:
        return {"ok": False, "error": "payroll_approve_required"}
    table = _ws_table(kind)
    if not table:
        return {"ok": False, "error": "invalid_worksheet_kind"}
    ws = get_worksheet(cur, company_code=company_code, kind=kind, worksheet_id=worksheet_id)
    if not ws:
        return {"ok": False, "error": "worksheet_not_found"}
    if str(ws.get("status")) == "approved":
        return {"ok": False, "error": "approved_worksheet_immutable", "worksheet_id": worksheet_id}
    if str(ws.get("status")) != "in_review":
        return {"ok": False, "error": "invalid_worksheet_transition", "status": ws.get("status")}
    actor_p = digits_phone(actor_phone or actor)
    if _phones_equal(actor_p, ws.get("created_by_phone")) or _phones_equal(actor_p, ws.get("submitted_by_phone")):
        return {"ok": False, "error": "self_approval_forbidden"}
    if expected_row_version is not None:
        conc = pyw1.require_concurrency(
            expected_row_version=expected_row_version, actual_row_version=ws.get("row_version")
        )
        if conc:
            return conc
    company = (company_code or "").upper()
    rv = int(expected_row_version) if expected_row_version is not None else int(ws.get("row_version") or 1)
    cur.execute(
        f"""
        UPDATE {table}
        SET status='approved', approved_by_phone=%s, approved_at=now(),
            decision_note=%s, row_version=row_version+1, updated_at=now()
        WHERE company_code=%s AND worksheet_id=%s AND status='in_review' AND row_version=%s
        RETURNING *
        """,
        (actor_p, str(reason).strip(), company, worksheet_id, rv),
    )
    updated = _row(cur)
    if not updated:
        return {"ok": False, "error": "stale_row_version_or_bad_status"}
    _record_event(
        cur,
        company_code=company,
        worksheet_kind=str(kind).strip().lower(),
        worksheet_id=worksheet_id,
        event_type="approved",
        payload={"reason": reason},
        actor_phone=actor_p,
    )
    return {"ok": True, "worksheet": _json_safe(updated), **honesty_payload()}


def mutate_approved_forbidden(
    cur: Any,
    *,
    kind: str,
    company_code: str,
    worksheet_id: str,
) -> dict[str, Any]:
    """Explicit fail-closed probe for approved worksheet immutability."""
    ws = get_worksheet(cur, company_code=company_code, kind=kind, worksheet_id=worksheet_id)
    if not ws:
        return {"ok": False, "error": "worksheet_not_found"}
    if str(ws.get("status")) != "approved":
        return {"ok": False, "error": "not_approved", "status": ws.get("status")}
    return {
        "ok": False,
        "error": "approved_worksheet_immutable",
        "worksheet_id": worksheet_id,
        **honesty_payload(),
    }


# --------------------------------------------------------------------------- dual-control override


def initiate_manual_override(
    cur: Any,
    *,
    kind: str,
    company_code: str,
    worksheet_id: str,
    actor: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
    exception_code: str | None = None,
    exception_evidence: dict[str, Any] | None = None,
    actor_permissions: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    perms = set(actor_permissions or [])
    if perms and "payroll.approve" not in perms and "payroll.manage" not in perms:
        return {"ok": False, "error": "payroll_manage_or_approve_required"}
    k = str(kind or "").strip().lower()
    if k not in (KIND_PIFSS, KIND_EOS):
        return {"ok": False, "error": "invalid_worksheet_kind"}
    ws = get_worksheet(cur, company_code=company_code, kind=k, worksheet_id=worksheet_id)
    if not ws:
        return {"ok": False, "error": "worksheet_not_found"}
    if str(ws.get("status")) == "approved":
        return {"ok": False, "error": "approved_worksheet_immutable"}
    company = (company_code or "").upper()
    actor_p = digits_phone(actor_phone or actor)
    if not actor_p:
        return {"ok": False, "error": "actor_phone_required"}
    cur.execute(
        """
        UPDATE payroll_statutory_dual_control
        SET status='cancelled'
        WHERE company_code=%s AND worksheet_kind=%s AND worksheet_id=%s AND status='pending_second'
        """,
        (company, k, worksheet_id),
    )
    payload = {
        "reason": reason,
        "exception_code": exception_code or "manual_exception",
        "exception_evidence": dict(exception_evidence or {}),
        "does_not_auto_approve_remittance": True,
    }
    cur.execute(
        """
        INSERT INTO payroll_statutory_dual_control (
          company_code, worksheet_kind, worksheet_id, action_kind, status,
          initiated_by_phone, payload
        ) VALUES (%s,%s,%s,'manual_override_exception','pending_second',%s,%s::jsonb)
        RETURNING *
        """,
        (company, k, worksheet_id, actor_p, json.dumps(_json_safe(payload))),
    )
    dual = _row(cur) or {}
    _record_event(
        cur,
        company_code=company,
        worksheet_kind=k,
        worksheet_id=worksheet_id,
        event_type="manual_override_initiated",
        payload={"reason": reason, "action_id": str(dual.get("action_id"))},
        actor_phone=actor_p,
    )
    return {
        "ok": True,
        "dual_control": _json_safe(dual),
        "worksheet": ws,
        "awaiting_second_approver": True,
        "remittance": False,
        **honesty_payload(),
    }


def confirm_manual_override(
    cur: Any,
    *,
    kind: str,
    company_code: str,
    worksheet_id: str,
    actor: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
    dual_action_id: str | None = None,
    actor_permissions: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    perms = set(actor_permissions or [])
    if perms and "payroll.approve" not in perms and "payroll.manage" not in perms:
        return {"ok": False, "error": "payroll_manage_or_approve_required"}
    k = str(kind or "").strip().lower()
    table = _ws_table(k)
    if not table:
        return {"ok": False, "error": "invalid_worksheet_kind"}
    company = (company_code or "").upper()
    actor_p = digits_phone(actor_phone or actor)
    if not actor_p:
        return {"ok": False, "error": "actor_phone_required"}
    if dual_action_id:
        cur.execute(
            """
            SELECT * FROM payroll_statutory_dual_control
            WHERE action_id=%s AND company_code=%s AND worksheet_kind=%s
              AND worksheet_id=%s AND status='pending_second'
            LIMIT 1
            """,
            (dual_action_id, company, k, worksheet_id),
        )
    else:
        cur.execute(
            """
            SELECT * FROM payroll_statutory_dual_control
            WHERE company_code=%s AND worksheet_kind=%s AND worksheet_id=%s
              AND status='pending_second'
            ORDER BY created_at DESC LIMIT 1
            """,
            (company, k, worksheet_id),
        )
    dual = _row(cur)
    if not dual:
        return {"ok": False, "error": "dual_control_not_found"}
    if _phones_equal(dual.get("initiated_by_phone"), actor_p):
        return {"ok": False, "error": "dual_control_same_actor"}

    dual_payload = dual.get("payload") or {}
    if isinstance(dual_payload, str):
        dual_payload = json.loads(dual_payload)
    exception_code = str(dual_payload.get("exception_code") or "manual_exception")
    exception_evidence = dict(dual_payload.get("exception_evidence") or {})
    exception_evidence["confirmed_reason"] = str(reason).strip()
    exception_evidence["initiated_by"] = dual.get("initiated_by_phone")
    exception_evidence["confirmed_by"] = actor_p
    exception_evidence["does_not_auto_approve_remittance"] = True

    cur.execute(
        """
        UPDATE payroll_statutory_dual_control
        SET status='confirmed', confirmed_by_phone=%s, confirmed_at=now()
        WHERE action_id=%s
        RETURNING *
        """,
        (actor_p, dual.get("action_id")),
    )
    dual_upd = _row(cur) or dual
    cur.execute(
        f"""
        UPDATE {table}
        SET status='exception',
            exception_code=%s,
            exception_evidence=%s::jsonb,
            decision_note=%s,
            row_version=row_version+1,
            updated_at=now()
        WHERE company_code=%s AND worksheet_id=%s
          AND status IN ('draft','in_review','counsel_required','unsupported','exception')
        RETURNING *
        """,
        (
            exception_code,
            json.dumps(_json_safe(exception_evidence)),
            str(reason).strip(),
            company,
            worksheet_id,
        ),
    )
    updated = _row(cur)
    if not updated:
        return {"ok": False, "error": "override_confirm_failed"}
    _record_event(
        cur,
        company_code=company,
        worksheet_kind=k,
        worksheet_id=worksheet_id,
        event_type="manual_override_confirmed",
        payload={
            "reason": reason,
            "action_id": str(dual.get("action_id")),
            "exception_code": exception_code,
            "remittance": False,
        },
        actor_phone=actor_p,
    )
    return {
        "ok": True,
        "dual_control": _json_safe(dual_upd),
        "worksheet": _json_safe(updated),
        "remittance": False,
        "auto_approved_remittance": False,
        **honesty_payload(),
    }


# --------------------------------------------------------------------------- recalculate / supersede


def recalculate_pifss(
    cur: Any,
    *,
    company_code: str,
    worksheet_id: str,
    contributory_salary: Any | None = None,
    actor: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
    inputs_provenance: dict[str, Any] | None = None,
    allowed_employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    prior = get_worksheet(cur, company_code=company_code, kind=KIND_PIFSS, worksheet_id=worksheet_id)
    if not prior:
        return {"ok": False, "error": "worksheet_not_found"}
    if str(prior.get("status")) == "approved":
        # Approved history retained as a superseded row (payload untouched); new draft supersedes.
        pass
    if str(prior.get("status")) == "superseded":
        return {"ok": False, "error": "worksheet_already_superseded"}

    salary = money3(contributory_salary if contributory_salary is not None else (
        (prior.get("worksheet_payload") or {}).get("contributory_salary")
        if isinstance(prior.get("worksheet_payload"), dict)
        else 0
    ))
    # Prefer explicit salary; fall back to provenance inputs
    if contributory_salary is None:
        prov = prior.get("source_provenance") or {}
        if isinstance(prov, str):
            prov = json.loads(prov)
        inputs = prov.get("inputs") or {}
        if inputs.get("contributory_salary") is not None:
            salary = money3(inputs.get("contributory_salary"))

    company = (company_code or "").upper()
    new_fp = _pifss_input_fingerprint(
        company=company,
        employee_key=str(prior.get("employee_key")),
        employee_category=str(prior.get("employee_category")),
        period_start=_as_date(prior.get("period_start")) or date.today(),
        period_end=_as_date(prior.get("period_end")) or date.today(),
        contributory_salary=salary,
    )
    if new_fp == str(prior.get("input_fingerprint") or "") and str(prior.get("status")) in ACTIVE_WS_STATUSES:
        # Same inputs: still regenerate when prior was blocked pending counsel/rules.
        if str(prior.get("status")) not in ("counsel_required", "unsupported", "exception"):
            return {
                "ok": True,
                "idempotent": True,
                "unchanged": True,
                "worksheet": prior,
                **honesty_payload(),
            }

    prior_id = str(prior.get("worksheet_id") or worksheet_id)
    if str(prior.get("status")) in ACTIVE_WS_STATUSES:
        cur.execute(
            """
            UPDATE payroll_pifss_worksheets
            SET status='superseded', row_version=row_version+1, updated_at=now()
            WHERE company_code=%s AND worksheet_id=%s AND status = ANY(%s)
            RETURNING *
            """,
            (company, prior_id, list(ACTIVE_WS_STATUSES)),
        )
        _row(cur)

    created = generate_pifss_worksheet(
        cur,
        company_code=company,
        employee_key=str(prior.get("employee_key")),
        employee_category=str(prior.get("employee_category")),
        period_start=prior.get("period_start"),
        period_end=prior.get("period_end"),
        contributory_salary=salary,
        actor=actor,
        actor_phone=actor_phone,
        reason=reason,
        inputs_provenance={
            **dict(inputs_provenance or {}),
            "recalculated_from": prior_id,
            "prior_input_fingerprint": prior.get("input_fingerprint"),
        },
        allowed_employee_keys=allowed_employee_keys,
    )
    if created.get("worksheet") and not created.get("idempotent"):
        new_id = str(created["worksheet"].get("worksheet_id"))
        cur.execute(
            """
            UPDATE payroll_pifss_worksheets
            SET supersedes_worksheet_id=%s, row_version=row_version+1, updated_at=now()
            WHERE worksheet_id=%s
            RETURNING *
            """,
            (prior_id, new_id),
        )
        created["worksheet"] = _json_safe(_row(cur) or created["worksheet"])
        cur.execute(
            """
            UPDATE payroll_pifss_worksheets
            SET superseded_by=%s, updated_at=now()
            WHERE worksheet_id=%s
            """,
            (new_id, prior_id),
        )
        _record_event(
            cur,
            company_code=company,
            worksheet_kind=KIND_PIFSS,
            worksheet_id=new_id,
            event_type="pifss_recalculated",
            payload={"prior_worksheet_id": prior_id, "reason": reason},
            actor_phone=digits_phone(actor_phone or actor),
        )
    return created


def recalculate_eos(
    cur: Any,
    *,
    company_code: str,
    worksheet_id: str,
    monthly_wage: Any | None = None,
    actor: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
    inputs_provenance: dict[str, Any] | None = None,
    allowed_employee_keys: list[str] | None = None,
    art_51_53_status: str | None = None,
    law_17_2018_status: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    prior = get_worksheet(cur, company_code=company_code, kind=KIND_EOS, worksheet_id=worksheet_id)
    if not prior:
        return {"ok": False, "error": "worksheet_not_found"}
    if str(prior.get("status")) == "superseded":
        return {"ok": False, "error": "worksheet_already_superseded"}

    prov = prior.get("source_provenance") or {}
    if isinstance(prov, str):
        prov = json.loads(prov)
    inputs = prov.get("inputs") or {}
    wage = money3(
        monthly_wage
        if monthly_wage is not None
        else inputs.get("monthly_wage")
        or (prior.get("worksheet_payload") or {}).get("monthly_wage")
        or 0
    )
    art = str(art_51_53_status or prior.get("art_51_53_status") or "unresolved_blocked")
    law17 = str(law_17_2018_status or prior.get("law_17_2018_status") or "unresolved_blocked")
    pt = str(inputs.get("pay_type") or (prior.get("worksheet_payload") or {}).get("pay_type") or "monthly")

    company = (company_code or "").upper()
    new_fp = _eos_input_fingerprint(
        company=company,
        employee_key=str(prior.get("employee_key")),
        employee_category=str(prior.get("employee_category")),
        termination_date=_as_date(prior.get("termination_date")) or date.today(),
        termination_reason=str(prior.get("termination_reason") or ""),
        service_start=_as_date(prior.get("service_start")) or date.today(),
        service_end=_as_date(prior.get("service_end")) or date.today(),
        monthly_wage=wage,
        pay_type=pt,
        art_51_53_status=art,
        law_17_2018_status=law17,
    )
    if new_fp == str(prior.get("input_fingerprint") or "") and str(prior.get("status")) in ACTIVE_WS_STATUSES:
        # Same inputs: still regenerate when prior was blocked pending counsel/rules.
        if str(prior.get("status")) not in ("counsel_required", "unsupported", "exception"):
            return {
                "ok": True,
                "idempotent": True,
                "unchanged": True,
                "worksheet": prior,
                **honesty_payload(),
            }

    prior_id = str(prior.get("worksheet_id") or worksheet_id)
    if str(prior.get("status")) in ACTIVE_WS_STATUSES:
        cur.execute(
            """
            UPDATE payroll_eos_worksheets
            SET status='superseded', row_version=row_version+1, updated_at=now()
            WHERE company_code=%s AND worksheet_id=%s AND status = ANY(%s)
            RETURNING *
            """,
            (company, prior_id, list(ACTIVE_WS_STATUSES)),
        )
        _row(cur)

    created = generate_eos_worksheet(
        cur,
        company_code=company,
        employee_key=str(prior.get("employee_key")),
        employee_category=str(prior.get("employee_category")),
        termination_date=prior.get("termination_date"),
        termination_reason=str(prior.get("termination_reason") or ""),
        service_start=prior.get("service_start"),
        service_end=prior.get("service_end"),
        monthly_wage=wage,
        pay_type=pt,
        art_51_53_status=art,
        law_17_2018_status=law17,
        actor=actor,
        actor_phone=actor_phone,
        reason=reason,
        inputs_provenance={
            **dict(inputs_provenance or {}),
            "recalculated_from": prior_id,
        },
        allowed_employee_keys=allowed_employee_keys,
    )
    if created.get("worksheet") and not created.get("idempotent"):
        new_id = str(created["worksheet"].get("worksheet_id"))
        cur.execute(
            """
            UPDATE payroll_eos_worksheets
            SET supersedes_worksheet_id=%s, row_version=row_version+1, updated_at=now()
            WHERE worksheet_id=%s
            RETURNING *
            """,
            (prior_id, new_id),
        )
        created["worksheet"] = _json_safe(_row(cur) or created["worksheet"])
        cur.execute(
            """
            UPDATE payroll_eos_worksheets
            SET superseded_by=%s, updated_at=now()
            WHERE worksheet_id=%s
            """,
            (new_id, prior_id),
        )
        _record_event(
            cur,
            company_code=company,
            worksheet_kind=KIND_EOS,
            worksheet_id=new_id,
            event_type="eos_recalculated",
            payload={"prior_worksheet_id": prior_id, "reason": reason},
            actor_phone=digits_phone(actor_phone or actor),
        )
    return created


# --------------------------------------------------------------------------- bootstrap


def workspace_bootstrap(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_payroll_wave5_schema(cur)
    return {
        "ok": True,
        "rule_tables": list_rule_tables(cur, company_code=company_code, limit=40),
        "pifss_worksheets": list_pifss_worksheets(cur, company_code=company_code, limit=40),
        "eos_worksheets": list_eos_worksheets(cur, company_code=company_code, limit=40),
        "events": list_events(cur, company_code=company_code, limit=40),
        "freeze_invariants": freeze_invariants(),
        **honesty_payload(),
    }


# Smoke-seed payload examples (documentation constants for tests)
SMOKE_PIFSS_KUWAITI_PAYLOAD = {
    "employer_rate": 0.115,
    "employee_rate": 0.08,
    "ceiling_kwd": 2750,
    "currency": "KWD",
    "posture": "review_only",
    "not_remittance": True,
}
SMOKE_EOS_MONTHLY_ART51_PAYLOAD = {
    "pay_type": "monthly",
    "days_first_5_years": 15,
    "days_after_5_years": 30,
    "cap_years_wage": 1.5,
    "posture": "review_only",
    "not_payable_instruction": True,
}
