"""Payroll Authority P4A — Kuwait statutory architecture + counsel-gated packaging.

Builds effective-dated statutory packages for PIFSS / OT / rest-day / PH / sick / EOS
with explicit A/B/C/D output classes. Does NOT invent Kuwait legal rates.

Fixtures: is_architecture_fixture=true AND legal_claim=false only.
Payroll legal money path consumes approval_status=approved AND legal_claim=true only.

Preserves: P1–P3 · preview_non_authoritative · SYNTHETIC_ONLY · no payments · no native PDF.
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

import payroll_components_policy_p3 as p3
import payroll_input_snapshot_p2 as p2

PAYROLL_AUTHORITY_P4A_VERSION = "1.0.0"
STATUTORY_SCHEMA = "wathefni.payroll_statutory_architecture.v1"
MONEY_PREVIEW = "preview_non_authoritative"
COUNTRY_KW = "KW"

RULE_FAMILIES = (
    "pifss",
    "ot_ordinary",
    "rest_day_work",
    "public_holiday_work",
    "sick_leave_fractions",
    "eos_indemnity",
)
TIME_PAY_FAMILIES = ("ot_ordinary", "rest_day_work", "public_holiday_work", "sick_leave_fractions")
OUTPUT_CLASSES = (
    "A_employee_net",
    "B_employer_liability",
    "C_settlement",
    "D_remittance_reporting",
)
APPROVAL_STATUSES = (
    "draft",
    "awaiting_legal_validation",
    "approved",
    "superseded",
    "cancelled",
)

SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_statutory_architecture_p4a_v1.sql"
SCHEMA_SQL = SCHEMA_SQL_PATH.read_text(encoding="utf-8") if SCHEMA_SQL_PATH.exists() else ""
P4B_SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_statutory_baseline_p4b_v1.sql"
P4B_SCHEMA_SQL = P4B_SCHEMA_SQL_PATH.read_text(encoding="utf-8") if P4B_SCHEMA_SQL_PATH.exists() else ""
_SCHEMA_READY = False
_ON = ("1", "true", "yes", "on")
DEFAULT_SYNTHETIC_KEY_MARKERS = (
    "PYW1", "PYW2A", "PYW3", "PYAUTH", "PYP1", "PYP2", "PYP3", "PYP4A", "PYINPUT", "PYCALC", "PYSTAT",
)


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _ON


def payroll_authority_p4a_enabled() -> bool:
    return _env_bool("WATHEFNI_PAYROLL_AUTHORITY_P4A", default=True)


def payroll_authority_p4a_enabled_for_company(company_code: str | None) -> bool:
    if not payroll_authority_p4a_enabled():
        return False
    raw = str(os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P4A_COMPANIES") or "WATHEFNI").strip()
    return (company_code or "").upper() in {p.strip().upper() for p in raw.split(",") if p.strip()}


def payroll_authority_p4a_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P4A_SYNTHETIC_ONLY")
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and (raw is None or str(raw).strip() == ""):
        return True
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _ON


def synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P4A_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_KEY_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_KEY_MARKERS


def is_p4a_synthetic_employee(*, employee_key: str | None = None) -> bool:
    key = str(employee_key or "")
    return any(m and m in key for m in synthetic_key_markers())


def honesty_payload() -> dict[str, Any]:
    return {
        "payroll_authority_p4a_version": PAYROLL_AUTHORITY_P4A_VERSION,
        "statutory_schema": STATUTORY_SCHEMA,
        "money_authority": MONEY_PREVIEW,
        "mode_a_wathefni_seal_unlocked": False,
        "native_official_pdf_unlocked": False,
        "kuwait_statutory_rates_invented": False,
        "kuwait_legal_claim": False,
        "pifss_eos_rates_legally_approved": False,
        "ot_sick_ph_rates_counsel_gated": True,
        "payment_processing": "disabled",
        "posts_payment": False,
        "payment_date_invented": False,
        "remittance_is_not_payment": True,
        "eos_auto_payable": False,
        "synthetic_only": payroll_authority_p4a_synthetic_only(),
        "kuwait_first": True,
        "gcc_extensible_via_country_code": True,
        "speculative_gcc_rules_implemented": False,
        "p1_p2_p3_preserved": True,
        "output_classes": list(OUTPUT_CLASSES),
        "rule_families": list(RULE_FAMILIES),
    }


def freeze_invariants() -> dict[str, Any]:
    return {
        "preview_non_authoritative": True,
        "legal_money_requires_approved_legal_claim": True,
        "architecture_fixtures_never_legal_claim": True,
        "fail_closed_missing_approved_rule": True,
        "superseded_not_selectable_for_new_period": True,
        "pifss_ee_er_remittance_distinct": True,
        "ot_rest_ph_sick_families_distinct": True,
        "eos_is_settlement_not_monthly_line": True,
        "no_invented_kuwait_rates": True,
    }


def output_class_boundary() -> dict[str, Any]:
    return {
        "A_employee_net": {
            "affects_employee_net_pay": True,
            "examples": ["PIFSS employee deduction", "OT earning when legally approved", "sick-leave pay fraction"],
        },
        "B_employer_liability": {
            "affects_employee_net_pay": False,
            "examples": ["PIFSS employer contribution"],
        },
        "C_settlement": {
            "affects_employee_net_pay": False,
            "monthly_g2n": False,
            "examples": ["EOS / indemnity settlement snapshot"],
        },
        "D_remittance_reporting": {
            "affects_employee_net_pay": False,
            "is_payment_processing": False,
            "examples": ["PIFSS remittance obligation worksheet / reporting prep"],
        },
        "never_mix": "Do not collapse A/B/C/D into a single gross-to-net line model.",
    }


def ensure_payroll_statutory_architecture_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    if not SCHEMA_SQL.strip():
        _SCHEMA_READY = True
        return
    lock_id = 770_900_014
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        cur.execute("SET LOCAL lock_timeout = '15s'")
        p3.ensure_payroll_components_policy_schema(cur)
        cur.execute(SCHEMA_SQL)
        if P4B_SCHEMA_SQL.strip():
            cur.execute(P4B_SCHEMA_SQL)
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
    return dict(zip([d[0] for d in cur.description], row))


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


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _record_event(
    cur: Any,
    *,
    country_code: str,
    company_code: str | None,
    entity_kind: str,
    entity_id: str | None,
    event_type: str,
    payload: dict[str, Any],
    actor_phone: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO payroll_statutory_events (
          company_code, country_code, entity_kind, entity_id, event_type, payload, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)
        """,
        (
            (company_code or "").upper() or None,
            (country_code or COUNTRY_KW).upper(),
            entity_kind,
            entity_id,
            event_type,
            json.dumps(_json_safe(payload)),
            digits_phone(actor_phone),
        ),
    )


def create_statutory_package(
    cur: Any,
    *,
    country_code: str = COUNTRY_KW,
    company_code: str | None = None,
    package_code: str,
    effective_from: str | date,
    title_en: str,
    actor_phone: str | None,
    reason: str | None,
    title_ar: str | None = None,
    is_architecture_fixture: bool = False,
    approval_status: str = "draft",
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_statutory_architecture_schema(cur)
    status = str(approval_status or "draft")
    if status not in APPROVAL_STATUSES:
        return {"ok": False, "error": "invalid_approval_status"}
    if status == "approved" and not is_architecture_fixture:
        return {
            "ok": False,
            "error": "legal_approval_refused_in_p4a",
            "message": "P4A refuses marking packages as legally approved; use awaiting_legal_validation or architecture fixtures.",
        }
    if is_architecture_fixture and status == "approved":
        # Architecture-qualified packaging only — never legal_claim
        pass
    elif status == "approved":
        return {"ok": False, "error": "legal_approval_refused_in_p4a"}

    ef = _parse_date(effective_from)
    if not ef:
        return {"ok": False, "error": "invalid_effective_from"}
    country = (country_code or COUNTRY_KW).upper()
    company = (company_code or "").upper() or None
    cur.execute(
        """
        SELECT COALESCE(MAX(version_number),0)+1 AS n
        FROM payroll_statutory_packages
        WHERE country_code=%s AND COALESCE(company_code,'')=%s AND package_code=%s
        """,
        (country, company or "", package_code),
    )
    ver = int(dict(cur.fetchone())["n"])
    payload = {
        "country_code": country,
        "company_code": company,
        "package_code": package_code,
        "version_number": ver,
        "effective_from": str(ef),
        "is_architecture_fixture": bool(is_architecture_fixture),
        "legal_claim": False,
    }
    fp = fingerprint_payload(payload)
    cur.execute(
        """
        INSERT INTO payroll_statutory_packages (
          country_code, company_code, package_code, version_number, approval_status,
          legal_claim, is_architecture_fixture, effective_from, title_en, title_ar,
          content_fingerprint, provenance, decision_note, created_by_phone
        ) VALUES (
          %s,%s,%s,%s,%s,
          false,%s,%s,%s,%s,
          %s,%s::jsonb,%s,%s
        )
        RETURNING *
        """,
        (
            country,
            company,
            package_code,
            ver,
            status if not (is_architecture_fixture and status == "approved") else "approved",
            bool(is_architecture_fixture),
            ef,
            title_en,
            title_ar,
            fp,
            json.dumps({"phase": "p4a", "legal_claim": False}),
            str(reason).strip(),
            digits_phone(actor_phone),
        ),
    )
    row = _row(cur)
    _record_event(
        cur,
        country_code=country,
        company_code=company,
        entity_kind="package",
        entity_id=str((row or {}).get("package_id")),
        event_type="package_created",
        payload={"approval_status": status, "architecture_fixture": bool(is_architecture_fixture)},
        actor_phone=actor_phone,
    )
    return {"ok": True, "package": _json_safe(row), **honesty_payload()}


def submit_package_for_legal_validation(
    cur: Any,
    *,
    package_id: str,
    actor_phone: str | None,
    reason: str | None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_statutory_architecture_schema(cur)
    cur.execute(
        """
        UPDATE payroll_statutory_packages
        SET approval_status='awaiting_legal_validation', updated_at=now(), row_version=row_version+1,
            decision_note=COALESCE(decision_note,'') || ' | ' || %s
        WHERE package_id=%s AND approval_status IN ('draft','awaiting_legal_validation')
          AND legal_claim=false
        RETURNING *
        """,
        (str(reason).strip(), package_id),
    )
    row = _row(cur)
    if not row:
        return {"ok": False, "error": "package_submit_failed"}
    return {"ok": True, "package": _json_safe(row), **honesty_payload()}


def refuse_legal_approve_package(
    cur: Any,
    *,
    package_id: str,
    actor_phone: str | None,
    reason: str | None,
) -> dict[str, Any]:
    """Hard refuse: P4A never grants legal_claim=true."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    return {
        "ok": False,
        "error": "legal_approval_reserved_for_p4b",
        "message": "Verified Kuwait rates/counsel sign-off are P4B. P4A architecture fixtures only.",
        "package_id": package_id,
        **honesty_payload(),
    }


def create_rule_version(
    cur: Any,
    *,
    package_id: str,
    rule_family: str,
    output_class: str,
    version_label: str,
    effective_from: str | date,
    actor_phone: str | None,
    reason: str | None,
    rate_payload: dict[str, Any] | None = None,
    multiplier: Any = None,
    fraction_payload: dict[str, Any] | None = None,
    is_architecture_fixture: bool = False,
    approval_status: str = "draft",
    company_code: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_statutory_architecture_schema(cur)
    if rule_family not in RULE_FAMILIES:
        return {"ok": False, "error": "invalid_rule_family"}
    if output_class not in OUTPUT_CLASSES and output_class != "mixed_pifss_pack":
        return {"ok": False, "error": "invalid_output_class"}
    if rule_family in TIME_PAY_FAMILIES and output_class != "A_employee_net":
        return {"ok": False, "error": "time_pay_must_be_A_employee_net"}
    if rule_family == "eos_indemnity" and output_class != "C_settlement":
        return {"ok": False, "error": "eos_must_be_C_settlement"}
    status = str(approval_status or "draft")
    if status not in APPROVAL_STATUSES:
        return {"ok": False, "error": "invalid_approval_status"}
    # Allow numeric candidates only as architecture fixtures OR awaiting_legal_validation (never legal_claim).
    if (
        not is_architecture_fixture
        and multiplier is not None
        and status != "awaiting_legal_validation"
    ):
        return {
            "ok": False,
            "error": "numeric_rate_refused_without_architecture_fixture",
            "message": "P4A refuses inventing Kuwait statutory rates outside architecture fixtures or awaiting_legal_validation candidates.",
        }
    if status == "approved" and not is_architecture_fixture:
        return {"ok": False, "error": "legal_approval_refused_in_p4a"}
    if is_architecture_fixture and status == "approved":
        status = "approved"

    cur.execute("SELECT * FROM payroll_statutory_packages WHERE package_id=%s", (package_id,))
    pkg = _row(cur)
    if not pkg:
        return {"ok": False, "error": "package_not_found"}

    ef = _parse_date(effective_from)
    if not ef:
        return {"ok": False, "error": "invalid_effective_from"}
    payload = {
        "rule_family": rule_family,
        "output_class": output_class,
        "version_label": version_label,
        "rate_payload": rate_payload or {},
        "multiplier": float(multiplier) if multiplier is not None else None,
        "fraction_payload": fraction_payload or {},
        "is_architecture_fixture": bool(is_architecture_fixture),
        "legal_claim": False,
    }
    fp = fingerprint_payload(payload)
    company = (company_code or pkg.get("company_code") or "") or None
    if company:
        company = company.upper()
    cur.execute(
        """
        INSERT INTO payroll_statutory_rule_versions (
          package_id, country_code, company_code, rule_family, output_class,
          approval_status, legal_claim, is_architecture_fixture, version_label,
          effective_from, rate_payload, multiplier, fraction_payload,
          counsel_signed, counsel_note, content_fingerprint, provenance,
          decision_note, created_by_phone
        ) VALUES (
          %s,%s,%s,%s,%s,
          %s,false,%s,%s,
          %s,%s::jsonb,%s,%s::jsonb,
          false,%s,%s,%s::jsonb,
          %s,%s
        )
        RETURNING *
        """,
        (
            package_id,
            str(pkg.get("country_code") or COUNTRY_KW).upper(),
            company,
            rule_family,
            output_class,
            status,
            bool(is_architecture_fixture),
            version_label,
            ef,
            json.dumps(rate_payload or {"note": "no_legal_rate"}),
            float(multiplier) if multiplier is not None else None,
            json.dumps(fraction_payload or {}),
            (
                "Architecture fixture only — not Kuwait counsel-signed law"
                if is_architecture_fixture
                else (
                    "P4B prep candidate — awaiting_legal_validation; legal_claim=false"
                    if status == "awaiting_legal_validation"
                    else "Awaiting counsel-signed Kuwait table"
                )
            ),
            fp,
            json.dumps(
                {
                    "phase": "p4b_prep" if status == "awaiting_legal_validation" else "p4a",
                    "legal_claim": False,
                    "counsel_signed": False,
                }
            ),
            str(reason).strip(),
            digits_phone(actor_phone),
        ),
    )
    row = _row(cur)
    # Bridge counsel_required P3 placeholder remains; architecture fixtures optionally sync to P3 for engine tests
    # Never sync awaiting_legal_validation candidates into P3 as approved/counsel_signed.
    if is_architecture_fixture and rule_family in TIME_PAY_FAMILIES and multiplier is not None and company:
        p3_row = _sync_architecture_rate_to_p3(
            cur,
            company_code=company,
            rule_family=rule_family,
            multiplier=multiplier,
            effective_from=ef,
            actor_phone=actor_phone,
            rule_version_id=str((row or {}).get("rule_version_id")),
        )
        if p3_row and row:
            cur.execute(
                "UPDATE payroll_statutory_rule_versions SET p3_rate_table_id=%s WHERE rule_version_id=%s RETURNING *",
                (p3_row.get("rate_table_id"), row.get("rule_version_id")),
            )
            row = _row(cur) or row
    _record_event(
        cur,
        country_code=str(pkg.get("country_code") or COUNTRY_KW),
        company_code=company,
        entity_kind="rule_version",
        entity_id=str((row or {}).get("rule_version_id")),
        event_type="rule_version_created",
        payload={"rule_family": rule_family, "architecture_fixture": bool(is_architecture_fixture)},
        actor_phone=actor_phone,
    )
    return {"ok": True, "rule_version": _json_safe(row), **honesty_payload()}


def _sync_architecture_rate_to_p3(
    cur: Any,
    *,
    company_code: str,
    rule_family: str,
    multiplier: Any,
    effective_from: date,
    actor_phone: str | None,
    rule_version_id: str,
) -> dict[str, Any] | None:
    """Write architecture-only approved P3 rate row (counsel_signed=false, fixture marker)."""
    p3.ensure_payroll_components_policy_schema(cur)
    company = company_code.upper()
    payload = {
        "rule_family": rule_family,
        "status": "approved",
        "multiplier": float(multiplier),
        "architecture_fixture": True,
        "legal_claim": False,
        "p4a_rule_version_id": rule_version_id,
    }
    fp = fingerprint_payload(payload)
    # Supersede prior architecture fixture approved rows for this family
    cur.execute(
        """
        UPDATE payroll_rate_tables
        SET status='superseded'
        WHERE company_code=%s AND rule_family=%s AND status='approved'
          AND counsel_signed=false
          AND (
            counsel_note ILIKE %s
            OR version_label LIKE %s
          )
        """,
        (company, rule_family, "%architecture fixture%", "p4a_architecture_%"),
    )
    cur.execute(
        """
        INSERT INTO payroll_rate_tables (
          company_code, rule_family, status, version_label, effective_from,
          multiplier, counsel_signed, counsel_note, content_fingerprint, created_by_phone
        ) VALUES (
          %s,%s,'approved',%s,%s,
          %s,false,%s,%s,%s
        )
        RETURNING *
        """,
        (
            company,
            rule_family,
            f"p4a_architecture_{rule_family}",
            effective_from,
            float(multiplier),
            "ARCHITECTURE FIXTURE ONLY — not counsel-signed Kuwait law; legal_claim=false",
            fp,
            digits_phone(actor_phone),
        ),
    )
    return _row(cur)


def add_pifss_contribution_spec(
    cur: Any,
    *,
    rule_version_id: str,
    employee_category: str,
    contribution_side: str,
    actor_phone: str | None,
    reason: str | None,
    rate_percent: Any = None,
    rate_is_architecture_fixture: bool = False,
    rate_awaiting_legal_validation: bool = False,
    fund_code: str = "unspecified",
    base_definition: str = "contributory_wage",
    cap_definition: str | None = None,
    eligibility_notes: str | None = None,
    remittance_notes: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_statutory_architecture_schema(cur)
    side_to_class = {
        "employee_deduction": "A_employee_net",
        "employer_contribution": "B_employer_liability",
        "remittance_obligation": "D_remittance_reporting",
    }
    if contribution_side not in side_to_class:
        return {"ok": False, "error": "invalid_contribution_side"}
    awaiting = bool(rate_awaiting_legal_validation)
    fixture = bool(rate_is_architecture_fixture)
    if rate_percent is not None and not fixture and not awaiting:
        return {
            "ok": False,
            "error": "pifss_rate_requires_architecture_fixture_or_awaiting_legal_flag",
            "message": "PIFSS numeric rates require architecture fixture or awaiting_legal_validation candidate flag.",
        }
    if fixture and awaiting:
        return {"ok": False, "error": "pifss_rate_flags_mutually_exclusive"}
    cur.execute("SELECT * FROM payroll_statutory_rule_versions WHERE rule_version_id=%s", (rule_version_id,))
    rule = _row(cur)
    if not rule or str(rule.get("rule_family")) != "pifss":
        return {"ok": False, "error": "pifss_rule_version_required"}
    fund = (fund_code or "unspecified").strip() or "unspecified"
    meta = {
        "legal_claim": False,
        "counsel_signed": False,
        "phase": "p4b_prep" if awaiting else "p4a",
        "fund_code": fund,
        **(metadata or {}),
    }
    cur.execute(
        """
        INSERT INTO payroll_pifss_contribution_specs (
          rule_version_id, country_code, employee_category, contribution_side, output_class,
          fund_code, base_definition, cap_definition, rate_percent,
          rate_is_architecture_fixture, rate_awaiting_legal_validation,
          eligibility_notes, remittance_notes, metadata
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (rule_version_id, employee_category, contribution_side, fund_code) DO UPDATE
          SET rate_percent=EXCLUDED.rate_percent,
              rate_is_architecture_fixture=EXCLUDED.rate_is_architecture_fixture,
              rate_awaiting_legal_validation=EXCLUDED.rate_awaiting_legal_validation,
              base_definition=EXCLUDED.base_definition,
              cap_definition=EXCLUDED.cap_definition,
              eligibility_notes=EXCLUDED.eligibility_notes,
              remittance_notes=EXCLUDED.remittance_notes,
              metadata=EXCLUDED.metadata
        RETURNING *
        """,
        (
            rule_version_id,
            str(rule.get("country_code") or COUNTRY_KW),
            employee_category,
            contribution_side,
            side_to_class[contribution_side],
            fund,
            base_definition,
            cap_definition,
            float(rate_percent) if rate_percent is not None else None,
            fixture,
            awaiting,
            eligibility_notes,
            remittance_notes or "Remittance prep only — not payment processing",
            json.dumps(meta),
        ),
    )
    return {"ok": True, "spec": _json_safe(_row(cur)), **honesty_payload()}


def resolve_rule_version(
    cur: Any,
    *,
    country_code: str = COUNTRY_KW,
    company_code: str | None,
    rule_family: str,
    as_of: str | date,
    require_legal_claim: bool = True,
    allow_architecture_fixture: bool = False,
) -> dict[str, Any] | None:
    """Select applicable approved rule version. Superseded excluded. Fail closed if none."""
    ensure_payroll_statutory_architecture_schema(cur)
    as_of_d = _parse_date(as_of)
    if not as_of_d:
        return None
    country = (country_code or COUNTRY_KW).upper()
    company = (company_code or "").upper() or None
    if require_legal_claim and not allow_architecture_fixture:
        # Prefer Wathefni country-level public baseline over any company overlay.
        # Companies must not redefine mandatory Kuwait statutory rules.
        cur.execute(
            """
            SELECT * FROM payroll_statutory_rule_versions
            WHERE country_code=%s AND rule_family=%s
              AND approval_status='approved'
              AND legal_claim=true
              AND counsel_signed=true
              AND is_architecture_fixture=false
              AND effective_from <= %s
              AND (effective_to IS NULL OR effective_to >= %s)
              AND (company_code IS NULL OR company_code=%s)
            ORDER BY
              CASE
                WHEN COALESCE(authority_kind,'') = 'wathefni_public_baseline' AND company_code IS NULL THEN 0
                WHEN company_code IS NULL THEN 1
                WHEN company_code = %s THEN 2
                ELSE 3
              END,
              effective_from DESC, created_at DESC
            LIMIT 1
            """,
            (country, rule_family, as_of_d, as_of_d, company, company),
        )
        return _row(cur)
    if allow_architecture_fixture:
        cur.execute(
            """
            SELECT * FROM payroll_statutory_rule_versions
            WHERE country_code=%s AND rule_family=%s
              AND approval_status='approved'
              AND legal_claim=false
              AND is_architecture_fixture=true
              AND effective_from <= %s
              AND (effective_to IS NULL OR effective_to >= %s)
              AND (company_code IS NULL OR company_code=%s)
            ORDER BY
              CASE WHEN company_code=%s THEN 0 ELSE 1 END,
              effective_from DESC, created_at DESC
            LIMIT 1
            """,
            (country, rule_family, as_of_d, as_of_d, company, company),
        )
        return _row(cur)
    return None


def require_rule_or_blocker(
    cur: Any,
    *,
    company_code: str,
    rule_family: str,
    as_of: date,
    require_legal_claim: bool = True,
    allow_architecture_fixture: bool = False,
) -> dict[str, Any]:
    rule = resolve_rule_version(
        cur,
        company_code=company_code,
        rule_family=rule_family,
        as_of=as_of,
        require_legal_claim=require_legal_claim,
        allow_architecture_fixture=allow_architecture_fixture,
    )
    if rule:
        return {"ok": True, "rule_version": rule}
    return {
        "ok": False,
        "error": "counsel_rate_required" if rule_family in TIME_PAY_FAMILIES or rule_family == "pifss" else "statutory_rule_required",
        "rule_family": rule_family,
        "blocker": {
            "code": "missing_approved_statutory_rule",
            "rule_family": rule_family,
            "message": f"No approved applicable {rule_family} rule for {as_of.isoformat()}",
            "legal_claim_required": require_legal_claim,
        },
    }


def supersede_rule_version(
    cur: Any,
    *,
    rule_version_id: str,
    actor_phone: str | None,
    reason: str | None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_statutory_architecture_schema(cur)
    cur.execute(
        """
        UPDATE payroll_statutory_rule_versions
        SET approval_status='superseded', updated_at=now(),
            decision_note=COALESCE(decision_note,'') || ' | superseded:' || %s
        WHERE rule_version_id=%s AND approval_status IN ('approved','awaiting_legal_validation','draft')
        RETURNING *
        """,
        (str(reason).strip(), rule_version_id),
    )
    row = _row(cur)
    if not row:
        return {"ok": False, "error": "supersede_failed"}
    # Also supersede bridged P3 architecture rate if present
    if row.get("p3_rate_table_id"):
        cur.execute(
            "UPDATE payroll_rate_tables SET status='superseded' WHERE rate_table_id=%s AND counsel_signed=false",
            (row.get("p3_rate_table_id"),),
        )
    return {"ok": True, "rule_version": _json_safe(row), **honesty_payload()}


def get_approved_rate_for_p3(
    cur: Any,
    *,
    company_code: str,
    rule_family: str,
    as_of: date,
    allow_architecture_fixture: bool = False,
) -> dict[str, Any] | None:
    """P3 bridge: legal claim rates first; architecture fixtures only when explicitly allowed."""
    # Legal path via P4A
    legal = resolve_rule_version(
        cur,
        company_code=company_code,
        rule_family=rule_family,
        as_of=as_of,
        require_legal_claim=True,
        allow_architecture_fixture=False,
    )
    frac = legal.get("fraction_payload") if legal else None
    if isinstance(frac, str):
        try:
            frac = json.loads(frac)
        except Exception:
            frac = {}
    has_frac = bool(frac) if isinstance(frac, dict) else False
    if legal and (legal.get("multiplier") is not None or has_frac):
        return {
            "multiplier": legal.get("multiplier"),
            "fraction_payload": frac or {},
            "rate_table_id": legal.get("p3_rate_table_id") or legal.get("rule_version_id"),
            "legal_claim": True,
            "is_architecture_fixture": False,
            "rule_version_id": str(legal.get("rule_version_id")),
            "policy_version": legal.get("policy_version"),
            "authority_kind": legal.get("authority_kind"),
            "official_source_ref": legal.get("official_source_ref"),
            "source_classification": legal.get("source_classification"),
            "source": (
                "p4b_public_baseline"
                if str(legal.get("authority_kind") or "") == "wathefni_public_baseline"
                else "p4a_legal"
            ),
        }
    # Existing P3 legal-signed path
    p3_legal = None
    cur.execute(
        """
        SELECT * FROM payroll_rate_tables
        WHERE company_code=%s AND rule_family=%s AND status='approved'
          AND counsel_signed=true AND effective_from <= %s
          AND (effective_to IS NULL OR effective_to >= %s)
          AND multiplier IS NOT NULL
        ORDER BY effective_from DESC LIMIT 1
        """,
        ((company_code or "").upper(), rule_family, as_of, as_of),
    )
    p3_legal = _row(cur)
    if p3_legal:
        return {**p3_legal, "legal_claim": True, "is_architecture_fixture": False, "source": "p3_counsel_signed"}

    if not allow_architecture_fixture:
        return None

    arch = resolve_rule_version(
        cur,
        company_code=company_code,
        rule_family=rule_family,
        as_of=as_of,
        require_legal_claim=False,
        allow_architecture_fixture=True,
    )
    if arch and arch.get("multiplier") is not None:
        return {
            "multiplier": arch.get("multiplier"),
            "rate_table_id": arch.get("p3_rate_table_id") or arch.get("rule_version_id"),
            "legal_claim": False,
            "is_architecture_fixture": True,
            "rule_version_id": str(arch.get("rule_version_id")),
            "source": "p4a_architecture_fixture",
        }
    return None


def evaluate_sick_leave_from_p2_facts(
    *,
    input_lines: list[dict[str, Any]],
    rule_version: dict[str, Any],
    daily_rate: Decimal,
) -> dict[str, Any]:
    """Consume P2 sick_leave facts with fraction engine — architecture or legal fractions."""
    fractions = rule_version.get("fraction_payload") or {}
    if isinstance(fractions, str):
        try:
            fractions = json.loads(fractions)
        except Exception:
            fractions = {}
    default_frac = Decimal(str(fractions.get("default_fraction") or fractions.get("day_1_to_15") or 0))
    lines = []
    for ln in input_lines:
        if ln.get("line_kind") != "leave_interval":
            continue
        if str(ln.get("classification") or "") != "sick_leave":
            continue
        days = float(ln.get("chargeable_days") or 0)
        if days <= 0:
            fs = _parse_date(ln.get("fact_date"))
            fe = _parse_date(ln.get("fact_end_date")) or fs
            days = float((fe - fs).days + 1) if fs and fe else 0
        # Architecture: fraction applies as pay retained; deduction = (1-frac)*days*daily
        retained = money(daily_rate * Decimal(str(days)) * default_frac)
        deduction = money(daily_rate * Decimal(str(days)) * (Decimal("1") - default_frac))
        lines.append(
            {
                "rule_family": "sick_leave_fractions",
                "output_class": "A_employee_net",
                "component_code": "SICK_LEAVE",
                "amount": float(deduction),
                "calc_notes": {
                    "chargeable_days": days,
                    "fraction": float(default_frac),
                    "retained": float(retained),
                    "daily_rate": float(daily_rate),
                    "architecture_fixture": bool(rule_version.get("is_architecture_fixture")),
                    "legal_claim": False,
                },
                "provenance": {
                    "input_line_id": str(ln.get("line_id") or ""),
                    "leave_id": ln.get("leave_id"),
                    "rule_version_id": str(rule_version.get("rule_version_id")),
                    "source": "p2_sick_leave_fact",
                },
            }
        )
    return {"ok": True, "lines": lines}


def create_eos_settlement_snapshot(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    service_start: str | date,
    service_end: str | date,
    actor_phone: str | None,
    reason: str | None,
    termination_reason: str | None = None,
    compensation_basis: dict[str, Any] | None = None,
    termination_context: dict[str, Any] | None = None,
    allow_architecture_fixture: bool = False,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    if payroll_authority_p4a_synthetic_only() and not is_p4a_synthetic_employee(employee_key=employee_key):
        return {"ok": False, "error": "payroll_authority_p4a_synthetic_only"}
    ensure_payroll_statutory_architecture_schema(cur)
    company = (company_code or "").upper()
    ss = _parse_date(service_start)
    se = _parse_date(service_end)
    if not ss or not se or se < ss:
        return {"ok": False, "error": "invalid_service_period"}

    req = require_rule_or_blocker(
        cur,
        company_code=company,
        rule_family="eos_indemnity",
        as_of=se,
        require_legal_claim=not allow_architecture_fixture,
        allow_architecture_fixture=allow_architecture_fixture,
    )
    blockers = []
    rule = None
    provisional = None
    status = "awaiting_legal_validation"
    if not req.get("ok"):
        blockers.append(req.get("blocker") or {"code": "missing_approved_statutory_rule"})
        status = "awaiting_legal_validation"
    else:
        rule = req["rule_version"]
        if allow_architecture_fixture and rule.get("is_architecture_fixture"):
            status = "architecture_qualified"
            # Architecture-only provisional: years * monthly * fixture factor (NOT Kuwait law)
            years = Decimal(str((se - ss).days + 1)) / Decimal("365")
            monthly = money((compensation_basis or {}).get("monthly_basic") or 0)
            factor = Decimal(str((rule.get("rate_payload") or {}).get("architecture_factor") or rule.get("multiplier") or 0))
            provisional = money(years * monthly * factor)
        else:
            status = "awaiting_legal_validation"
            blockers.append(
                {
                    "code": "eos_legal_rate_required",
                    "message": "EOS structure ready; verified Kuwait rates required (P4B)",
                }
            )

    input_fp = fingerprint_payload(
        {
            "employee_key": employee_key,
            "service_start": str(ss),
            "service_end": str(se),
            "termination_reason": termination_reason,
            "compensation_basis": compensation_basis or {},
        }
    )
    result = {
        "schema": "wathefni.eos_settlement.v1",
        "output_class": "C_settlement",
        "provisional_amount": float(provisional) if provisional is not None else None,
        "legal_claim": False,
        "auto_payable": False,
        "rule_version_id": str((rule or {}).get("rule_version_id") or "") or None,
        "blockers": blockers,
    }
    content_fp = fingerprint_payload(result)
    cur.execute(
        """
        INSERT INTO payroll_eos_settlement_snapshots (
          company_code, country_code, employee_key, service_start, service_end,
          termination_reason, termination_context, compensation_basis,
          rule_version_id, package_id, approval_status, legal_claim, is_architecture_fixture,
          provisional_amount, input_fingerprint, content_fingerprint, result_payload,
          blockers, warnings, provenance, decision_note, created_by_phone
        ) VALUES (
          %s,'KW',%s,%s,%s,
          %s,%s::jsonb,%s::jsonb,
          %s,%s,%s,false,%s,
          %s,%s,%s,%s::jsonb,
          %s::jsonb,'[]'::jsonb,%s::jsonb,%s,%s
        )
        RETURNING *
        """,
        (
            company,
            employee_key,
            ss,
            se,
            termination_reason,
            json.dumps(termination_context or {}),
            json.dumps(compensation_basis or {}),
            (rule or {}).get("rule_version_id"),
            (rule or {}).get("package_id"),
            status,
            bool((rule or {}).get("is_architecture_fixture")),
            float(provisional) if provisional is not None else None,
            input_fp,
            content_fp,
            json.dumps(_json_safe(result)),
            json.dumps(_json_safe(blockers)),
            json.dumps(
                {
                    "output_class": "C_settlement",
                    "not_monthly_g2n": True,
                    "payment_processing": "disabled",
                }
            ),
            str(reason).strip(),
            digits_phone(actor_phone),
        ),
    )
    row = _row(cur)
    _record_event(
        cur,
        country_code=COUNTRY_KW,
        company_code=company,
        entity_kind="eos_settlement",
        entity_id=str((row or {}).get("settlement_id")),
        event_type="eos_settlement_created",
        payload={"status": status, "legal_claim": False},
        actor_phone=actor_phone,
    )
    return {
        "ok": True if not blockers or status == "architecture_qualified" else True,
        "settlement": _json_safe(row),
        "blocked": bool(blockers) and status != "architecture_qualified",
        **honesty_payload(),
    }


def evaluate_statutory_period(
    cur: Any,
    *,
    company_code: str,
    period_start: str | date,
    period_end: str | date,
    actor_phone: str | None,
    reason: str | None,
    input_snapshot_id: str | None = None,
    employee_keys: list[str] | None = None,
    allow_architecture_fixture: bool = False,
    require_families: list[str] | None = None,
) -> dict[str, Any]:
    """Architecture evaluation producing classified A/B/C/D lines. legal_claim always false."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    if not payroll_authority_p4a_enabled_for_company(company_code):
        return {"ok": False, "error": "payroll_authority_p4a_disabled_for_company"}
    ensure_payroll_statutory_architecture_schema(cur)
    company = (company_code or "").upper()
    p_start = _parse_date(period_start)
    p_end = _parse_date(period_end)
    if not p_start or not p_end:
        return {"ok": False, "error": "invalid_period"}

    families = require_families or ["pifss", "ot_ordinary", "rest_day_work", "public_holiday_work", "sick_leave_fractions"]
    blockers: list[dict[str, Any]] = []
    resolved: dict[str, Any] = {}
    for fam in families:
        req = require_rule_or_blocker(
            cur,
            company_code=company,
            rule_family=fam,
            as_of=p_start,
            require_legal_claim=not allow_architecture_fixture,
            allow_architecture_fixture=allow_architecture_fixture,
        )
        if not req.get("ok"):
            blockers.append(req.get("blocker") or {"code": "missing_approved_statutory_rule", "rule_family": fam})
        else:
            resolved[fam] = req["rule_version"]

    lines: list[dict[str, Any]] = []
    # PIFSS EE/ER/remittance distinct
    if "pifss" in resolved:
        cur.execute(
            "SELECT * FROM payroll_pifss_contribution_specs WHERE rule_version_id=%s ORDER BY contribution_side",
            (resolved["pifss"].get("rule_version_id"),),
        )
        for spec in _rows(cur):
            lines.append(
                {
                    "rule_family": "pifss",
                    "output_class": spec.get("output_class"),
                    "component_code": {
                        "employee_deduction": "PIFSS_EE",
                        "employer_contribution": "PIFSS_ER",
                        "remittance_obligation": "PIFSS_REMITTANCE",
                    }.get(str(spec.get("contribution_side")), "PIFSS"),
                    "amount": float(spec.get("rate_percent") or 0) if allow_architecture_fixture else None,
                    "amount_is_architecture_fixture": bool(spec.get("rate_is_architecture_fixture")),
                    "legal_claim": False,
                    "rule_version_id": str(resolved["pifss"].get("rule_version_id")),
                    "calc_notes": {
                        "contribution_side": spec.get("contribution_side"),
                        "employee_category": spec.get("employee_category"),
                        "base_definition": spec.get("base_definition"),
                        "remittance_is_not_payment": True,
                    },
                    "provenance": {"spec_id": str(spec.get("spec_id")), "source": "pifss_contribution_specs"},
                }
            )

    # Time-pay families stay distinct
    for fam in TIME_PAY_FAMILIES:
        if fam not in resolved:
            continue
        rule = resolved[fam]
        lines.append(
            {
                "rule_family": fam,
                "output_class": "A_employee_net",
                "component_code": {
                    "ot_ordinary": "OT_ORDINARY",
                    "rest_day_work": "OT_REST_DAY",
                    "public_holiday_work": "OT_PUBLIC_HOLIDAY",
                    "sick_leave_fractions": "SICK_LEAVE",
                }[fam],
                "amount": float(rule.get("multiplier") or 0) if fam != "sick_leave_fractions" else None,
                "amount_is_architecture_fixture": bool(rule.get("is_architecture_fixture")),
                "legal_claim": False,
                "rule_version_id": str(rule.get("rule_version_id")),
                "calc_notes": {
                    "multiplier": float(rule.get("multiplier")) if rule.get("multiplier") is not None else None,
                    "fraction_payload": rule.get("fraction_payload"),
                    "families_not_collapsed": True,
                },
                "provenance": {"source": "payroll_statutory_rule_versions", "rule_family": fam},
            }
        )

    # Optional: consume P2 sick facts when snapshot provided
    if input_snapshot_id and "sick_leave_fractions" in resolved:
        snap = p2.get_input_snapshot_by_id(cur, company_code=company, input_snapshot_id=input_snapshot_id)
        if snap:
            all_lines = p2.list_input_snapshot_lines(cur, company_code=company, input_snapshot_id=input_snapshot_id)
            if employee_keys:
                keys = set(employee_keys)
                all_lines = [ln for ln in all_lines if str(ln.get("employee_key")) in keys]
            sick = evaluate_sick_leave_from_p2_facts(
                input_lines=all_lines,
                rule_version=resolved["sick_leave_fractions"],
                daily_rate=money(10),  # architecture placeholder daily — not Kuwait law
            )
            for sl in sick.get("lines") or []:
                sl["amount_is_architecture_fixture"] = True
                sl["legal_claim"] = False
                lines.append(sl)

    content = {
        "schema": STATUTORY_SCHEMA,
        "company_code": company,
        "period_start": str(p_start),
        "period_end": str(p_end),
        "resolved_families": {k: str(v.get("rule_version_id")) for k, v in resolved.items()},
        "lines": _json_safe(lines),
        "blockers": blockers,
        "legal_claim": False,
        "money_authority": MONEY_PREVIEW,
        "output_class_boundary": output_class_boundary(),
    }
    content_fp = fingerprint_payload(content)
    status = "blocked" if blockers and not allow_architecture_fixture else ("blocked" if blockers and not resolved else "evaluated")
    if allow_architecture_fixture and resolved and not blockers:
        status = "evaluated"
    if blockers and not resolved:
        status = "blocked"
    if blockers and resolved and allow_architecture_fixture:
        # partial
        status = "evaluated"

    cur.execute(
        """
        INSERT INTO payroll_statutory_eval_runs (
          company_code, country_code, period_start, period_end, input_snapshot_id,
          content_fingerprint, status, result_payload, blockers, decision_note, created_by_phone
        ) VALUES (%s,'KW',%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
        RETURNING *
        """,
        (
            company,
            p_start,
            p_end,
            input_snapshot_id,
            content_fp,
            status,
            json.dumps(_json_safe(content)),
            json.dumps(_json_safe(blockers)),
            str(reason).strip(),
            digits_phone(actor_phone),
        ),
    )
    run = _row(cur)
    run_id = str((run or {}).get("eval_run_id"))
    for ln in lines:
        cur.execute(
            """
            INSERT INTO payroll_statutory_eval_lines (
              eval_run_id, company_code, employee_key, rule_family, output_class,
              component_code, amount, amount_is_architecture_fixture, legal_claim,
              rule_version_id, calc_notes, provenance
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,false,%s,%s::jsonb,%s::jsonb)
            """,
            (
                run_id,
                company,
                ln.get("employee_key"),
                ln.get("rule_family"),
                ln.get("output_class"),
                ln.get("component_code"),
                ln.get("amount"),
                bool(ln.get("amount_is_architecture_fixture", True)),
                ln.get("rule_version_id"),
                json.dumps(_json_safe(ln.get("calc_notes") or {})),
                json.dumps(_json_safe(ln.get("provenance") or {})),
            ),
        )
    return {
        "ok": True,
        "eval_run": _json_safe(run),
        "lines": _json_safe(lines),
        "blockers": blockers,
        "resolved_families": list(resolved.keys()),
        **honesty_payload(),
    }


def workspace_bootstrap(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_payroll_statutory_architecture_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        """
        SELECT * FROM payroll_statutory_packages
        WHERE country_code='KW' AND (company_code=%s OR company_code IS NULL)
        ORDER BY created_at DESC LIMIT 20
        """,
        (company,),
    )
    packages = _rows(cur)
    cur.execute(
        """
        SELECT rule_family, approval_status, legal_claim, is_architecture_fixture,
               version_label, effective_from, rule_version_id::text, multiplier
        FROM payroll_statutory_rule_versions
        WHERE country_code='KW' AND (company_code=%s OR company_code IS NULL)
        ORDER BY created_at DESC LIMIT 50
        """,
        (company,),
    )
    rules = _rows(cur)
    cur.execute(
        """
        SELECT settlement_id::text, employee_key, approval_status, legal_claim,
               provisional_amount, created_at
        FROM payroll_eos_settlement_snapshots
        WHERE company_code=%s
        ORDER BY created_at DESC LIMIT 20
        """,
        (company,),
    )
    eos = _rows(cur)
    return {
        "ok": True,
        "packages": _json_safe(packages),
        "rule_versions": _json_safe(rules),
        "eos_settlements": _json_safe(eos),
        "output_class_boundary": output_class_boundary(),
        "p4b_required_inputs": p4b_required_legal_inputs(),
        **honesty_payload(),
    }


def p4b_required_legal_inputs() -> dict[str, Any]:
    return {
        "note": "P4B must supply counsel-signed Kuwait legal tables. P4A only provides architecture.",
        "required": [
            {
                "rule_family": "pifss",
                "needs": [
                    "Kuwaiti / GCC / expatriate eligibility rules",
                    "employee contribution percent(s) and wage base/caps",
                    "employer contribution percent(s) and wage base/caps",
                    "remittance reporting field mapping (not payment rails)",
                ],
            },
            {
                "rule_family": "ot_ordinary",
                "needs": ["verified ordinary overtime multiplier(s) / hour rules", "effective dates"],
            },
            {
                "rule_family": "rest_day_work",
                "needs": ["verified rest-day work pay rule (distinct from ordinary OT)"],
            },
            {
                "rule_family": "public_holiday_work",
                "needs": ["verified public-holiday work pay rule (distinct from rest-day)"],
            },
            {
                "rule_family": "sick_leave_fractions",
                "needs": ["verified sick-leave pay fractions by day bands (Art. reference as counsel cites)"],
            },
            {
                "rule_family": "eos_indemnity",
                "needs": [
                    "verified EOS indemnity calculation basis",
                    "termination-reason variations counsel confirms",
                    "service-year banding / ceilings if any",
                ],
            },
        ],
        "approval_requirements": [
            "approval_status=approved",
            "legal_claim=true",
            "counsel_signed=true",
            "is_architecture_fixture=false",
            "source citation / counsel attestation in provenance",
        ],
    }
