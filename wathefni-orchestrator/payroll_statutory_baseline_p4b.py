"""Payroll Authority P4B — Wathefni-owned Kuwait public statutory baseline.

Activates OFFICIAL_CLEAR rules from authoritative public Kuwait sources into
effective-dated statutory policy versions. Ambiguous/special-regime cases stay
review-gated and do not block normal private-sector payroll for activated families.

Does NOT: unlock Mode A · remove SYNTHETIC_ONLY · enable native PDF · enable payments
· invent payment_date · guess unresolved interpretations · start P5.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import payroll_statutory_architecture_p4a as p4a

PAYROLL_AUTHORITY_P4B_VERSION = "1.0.0"
BASELINE_SCHEMA = "wathefni.payroll_statutory_baseline.v1"
POLICY_VERSION = "KW_PUBLIC_BASELINE_v1.0.0"
PACKAGE_CODE = "KW_PUBLIC_BASELINE"
AUTHORITY_KIND = "wathefni_public_baseline"
MONEY_PREVIEW = "preview_non_authoritative"
COUNTRY_KW = "KW"

CLASSIFICATION_PATH = (
    Path(__file__).resolve().parents[1] / "ops" / "payroll_authority_p4b_public_baseline_classification_v1.json"
)
# Prefer repo ops/ when running from orchestrator tree
_ALT_CLASS = Path(__file__).resolve().parents[2] / "ops" / "payroll_authority_p4b_public_baseline_classification_v1.json"
SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_statutory_baseline_p4b_v1.sql"
SCHEMA_SQL = SCHEMA_SQL_PATH.read_text(encoding="utf-8") if SCHEMA_SQL_PATH.exists() else ""
_SCHEMA_READY = False
_ON = ("1", "true", "yes", "on")

MANDATORY_STATUTORY_FAMILIES = (
    "pifss",
    "ot_ordinary",
    "rest_day_work",
    "public_holiday_work",
    "sick_leave_fractions",
    "eos_indemnity",
)

GATED_BLOCKERS = {
    "pifss_wage_base_classification_required": {
        "code": "pifss_wage_base_classification_required",
        "message": "PIFSS rates are active, but insurable wage base must be company/statutory-classified — OctoHR salary is not auto-assumed as PIFSS base.",
    },
    "pifss_category_classification_required": {
        "code": "pifss_category_classification_required",
        "message": "Employee statutory category required (kuwaiti_national / gcc_national / expatriate).",
    },
    "gcc_extension_review_required": {
        "code": "gcc_extension_review_required",
        "message": "GCC extension-of-protection rates are not in the Kuwait public baseline — Needs Review.",
    },
    "eos_remuneration_base_classification_required": {
        "code": "eos_remuneration_base_classification_required",
        "message": "EOS formula is active, but last remuneration input must be classified — basic-only is not auto-assumed.",
    },
    "eos_pifss_interaction_review_required": {
        "code": "eos_pifss_interaction_review_required",
        "message": "Kuwaiti EOS × PIFSS / Law 17/2018 interaction remains review-gated.",
    },
    "company_cannot_override_kuwait_statutory_baseline": {
        "code": "company_cannot_override_kuwait_statutory_baseline",
        "message": "Company payroll policy cannot redefine mandatory Kuwait statutory baseline rules.",
    },
}


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _ON


def payroll_authority_p4b_enabled() -> bool:
    return _env_bool("WATHEFNI_PAYROLL_AUTHORITY_P4B", default=True)


def payroll_authority_p4b_enabled_for_company(company_code: str | None) -> bool:
    if not payroll_authority_p4b_enabled():
        return False
    raw = str(os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P4B_COMPANIES") or "WATHEFNI").strip()
    return (company_code or "").upper() in {p.strip().upper() for p in raw.split(",") if p.strip()}


def payroll_authority_p4b_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P4B_SYNTHETIC_ONLY")
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and (raw is None or str(raw).strip() == ""):
        return True
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _ON


def money(value: Any, rounding: str = "HALF_UP") -> Decimal:
    q = Decimal("0.001")
    d = Decimal(str(value or 0))
    return d.quantize(q, rounding=ROUND_HALF_UP if rounding == "HALF_UP" else ROUND_HALF_UP)


def fingerprint_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def honesty_payload() -> dict[str, Any]:
    return {
        "payroll_authority_p4b_version": PAYROLL_AUTHORITY_P4B_VERSION,
        "baseline_schema": BASELINE_SCHEMA,
        "policy_version": POLICY_VERSION,
        "authority_kind": AUTHORITY_KIND,
        "money_authority": MONEY_PREVIEW,
        "mode_a_wathefni_seal_unlocked": False,
        "native_official_pdf_unlocked": False,
        "payment_processing": "disabled",
        "posts_payment": False,
        "payment_date_invented": False,
        "synthetic_only": payroll_authority_p4b_synthetic_only(),
        "official_clear_may_activate": True,
        "ambiguous_cases_remain_gated": True,
        "company_cannot_override_mandatory_statutory": True,
        "p1_p2_p3_p4a_preserved": True,
    }


def load_classification_pack() -> dict[str, Any]:
    path = CLASSIFICATION_PATH if CLASSIFICATION_PATH.exists() else _ALT_CLASS
    if not path.exists():
        # Try ops next to repo root from /opt
        for candidate in (
            Path("/opt/wathefni/ops/payroll_authority_p4b_public_baseline_classification_v1.json"),
            Path("/Users/azizalmulla/Desktop/claw/ops/payroll_authority_p4b_public_baseline_classification_v1.json"),
        ):
            if candidate.exists():
                path = candidate
                break
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_payroll_statutory_baseline_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    p4a.ensure_payroll_statutory_architecture_schema(cur, force=force)
    if SCHEMA_SQL.strip():
        lock_id = 770_900_015
        cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
        try:
            cur.execute("SET LOCAL lock_timeout = '15s'")
            cur.execute(SCHEMA_SQL)
        finally:
            try:
                cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
            except Exception:
                pass
    _SCHEMA_READY = True


def _row(cur: Any) -> dict[str, Any] | None:
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    return dict(zip([d[0] for d in cur.description], row))


def _json_safe(obj: Any) -> Any:
    return p4a._json_safe(obj)  # noqa: SLF001


def refuse_company_statutory_override(
    *,
    company_code: str | None,
    rule_family: str,
    legal_claim: bool = False,
    authority_kind: str | None = None,
) -> dict[str, Any] | None:
    """Company may configure policy, never redefine mandatory Kuwait statutory baseline."""
    if not company_code:
        return None
    if rule_family not in MANDATORY_STATUTORY_FAMILIES:
        return None
    if legal_claim or authority_kind == AUTHORITY_KIND:
        return {
            "ok": False,
            "error": "company_cannot_override_kuwait_statutory_baseline",
            "blocker": GATED_BLOCKERS["company_cannot_override_kuwait_statutory_baseline"],
            **honesty_payload(),
        }
    return None


def rule_applies_to_context(
    rule: dict[str, Any],
    *,
    employee_category: str | None = None,
    sector: str | None = None,
    pay_frequency: str | None = None,
    contract_type: str | None = None,
    termination: str | None = None,
) -> bool:
    appl = rule.get("applicability") or {}
    if isinstance(appl, str):
        try:
            appl = json.loads(appl)
        except Exception:
            appl = {}
    checks = {
        "employee_category": employee_category,
        "sector": sector,
        "pay_frequency": pay_frequency,
        "contract_type": contract_type,
        "termination": termination,
    }
    for key, value in checks.items():
        allowed = appl.get(key)
        if not allowed:
            continue
        if value is None:
            return False
        if str(value) not in {str(x) for x in allowed}:
            return False
    return True


def resolve_public_baseline_rule(
    cur: Any,
    *,
    rule_family: str,
    as_of: str | date,
    country_code: str = COUNTRY_KW,
    employee_category: str | None = None,
    sector: str | None = "private",
    pay_frequency: str | None = None,
    contract_type: str | None = None,
    termination: str | None = None,
) -> dict[str, Any] | None:
    """Country-level Wathefni public baseline only — never company override."""
    ensure_payroll_statutory_baseline_schema(cur)
    as_of_d = p4a._parse_date(as_of)  # noqa: SLF001
    if not as_of_d:
        return None
    cur.execute(
        """
        SELECT * FROM payroll_statutory_rule_versions
        WHERE country_code=%s AND rule_family=%s
          AND company_code IS NULL
          AND authority_kind=%s
          AND approval_status='approved'
          AND legal_claim=true
          AND counsel_signed=true
          AND is_architecture_fixture=false
          AND source_classification='OFFICIAL_CLEAR'
          AND effective_from <= %s
          AND (effective_to IS NULL OR effective_to >= %s)
        ORDER BY effective_from DESC, created_at DESC
        """,
        ((country_code or COUNTRY_KW).upper(), rule_family, AUTHORITY_KIND, as_of_d, as_of_d),
    )
    rows = cur.fetchall()
    if not rows:
        return None
    cols = [d[0] for d in cur.description]
    for raw in rows:
        rule = dict(raw) if isinstance(raw, dict) else dict(zip(cols, raw))
        if rule_applies_to_context(
            rule,
            employee_category=employee_category,
            sector=sector,
            pay_frequency=pay_frequency,
            contract_type=contract_type,
            termination=termination,
        ):
            return rule
    return None


def _insert_activated_rule(
    cur: Any,
    *,
    package_id: str,
    rule_family: str,
    output_class: str,
    version_label: str,
    effective_from: str,
    rate_payload: dict[str, Any],
    multiplier: Any = None,
    fraction_payload: dict[str, Any] | None = None,
    applicability: dict[str, Any] | None = None,
    official_source_ref: str,
    actor_phone: str | None,
    reason: str,
    decision_note: str,
) -> dict[str, Any]:
    denied = refuse_company_statutory_override(
        company_code=None, rule_family=rule_family, legal_claim=True, authority_kind=AUTHORITY_KIND
    )
    # None company always allowed for baseline
    ef = p4a._parse_date(effective_from)  # noqa: SLF001
    payload = {
        "rule_family": rule_family,
        "output_class": output_class,
        "version_label": version_label,
        "rate_payload": rate_payload,
        "multiplier": float(multiplier) if multiplier is not None else None,
        "fraction_payload": fraction_payload or {},
        "authority_kind": AUTHORITY_KIND,
        "source_classification": "OFFICIAL_CLEAR",
        "policy_version": POLICY_VERSION,
        "legal_claim": True,
    }
    fp = fingerprint_payload(payload)
    cur.execute(
        """
        INSERT INTO payroll_statutory_rule_versions (
          package_id, country_code, company_code, rule_family, output_class,
          approval_status, legal_claim, is_architecture_fixture, version_label,
          effective_from, rate_payload, multiplier, fraction_payload,
          counsel_signed, counsel_note, content_fingerprint, provenance,
          decision_note, created_by_phone, validated_by_phone, validated_at,
          source_classification, authority_kind, applicability, official_source_ref, policy_version
        ) VALUES (
          %s,'KW',NULL,%s,%s,
          'approved',true,false,%s,
          %s,%s::jsonb,%s,%s::jsonb,
          true,%s,%s,%s::jsonb,
          %s,%s,%s,now(),
          'OFFICIAL_CLEAR',%s,%s::jsonb,%s,%s
        )
        RETURNING *
        """,
        (
            package_id,
            rule_family,
            output_class,
            version_label,
            ef,
            json.dumps(rate_payload),
            float(multiplier) if multiplier is not None else None,
            json.dumps(fraction_payload or {}),
            "OctoHR public statutory baseline attestation (OFFICIAL_CLEAR) — not Mode A seal",
            fp,
            json.dumps(
                {
                    "phase": "p4b",
                    "authority_kind": AUTHORITY_KIND,
                    "source_classification": "OFFICIAL_CLEAR",
                    "policy_version": POLICY_VERSION,
                    "legal_claim": True,
                    "mode_a_unlocked": False,
                }
            ),
            decision_note,
            digits_phone(actor_phone),
            digits_phone(actor_phone),
            AUTHORITY_KIND,
            json.dumps(applicability or {}),
            official_source_ref,
            POLICY_VERSION,
        ),
    )
    return _row(cur) or {}


def activate_kuwait_public_baseline(
    cur: Any,
    *,
    actor_phone: str | None,
    reason: str | None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Idempotently activate OFFICIAL_CLEAR Kuwait public baseline (country-level)."""
    if not reason or not str(reason).strip():
        return {"ok": False, "error": "audit_reason_required"}
    ensure_payroll_statutory_baseline_schema(cur, force=True)
    pack = load_classification_pack()
    activated: list[dict[str, Any]] = []
    gated: list[dict[str, Any]] = []

    for item in pack.get("classifications") or []:
        if not item.get("activate") or item.get("classification") != "OFFICIAL_CLEAR":
            gated.append(
                {
                    "rule_id": item.get("rule_id"),
                    "rule_family": item.get("rule_family"),
                    "classification": item.get("classification"),
                    "gate": item.get("gate"),
                    "reason": item.get("reason"),
                }
            )

    # Existing package?
    cur.execute(
        """
        SELECT * FROM payroll_statutory_packages
        WHERE country_code='KW' AND company_code IS NULL AND package_code=%s
          AND authority_kind=%s AND approval_status='approved' AND legal_claim=true
        ORDER BY version_number DESC LIMIT 1
        """,
        (PACKAGE_CODE, AUTHORITY_KIND),
    )
    existing_pkg = _row(cur)
    if existing_pkg and not force_refresh:
        cur.execute(
            """
            SELECT rule_family, rule_version_id::text, version_label, multiplier,
                   source_classification, authority_kind, policy_version, official_source_ref,
                   legal_claim, counsel_signed, approval_status
            FROM payroll_statutory_rule_versions
            WHERE package_id=%s AND approval_status='approved' AND legal_claim=true
            ORDER BY rule_family, version_label
            """,
            (existing_pkg.get("package_id"),),
        )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        activated = [dict(r) if isinstance(r, dict) else dict(zip(cols, r)) for r in rows]
        return {
            "ok": True,
            "already_active": True,
            "package": _json_safe(existing_pkg),
            "activated_rules": _json_safe(activated),
            "still_gated": gated,
            **honesty_payload(),
        }

    # Create package
    cur.execute(
        """
        SELECT COALESCE(MAX(version_number),0)+1 AS n
        FROM payroll_statutory_packages
        WHERE country_code='KW' AND COALESCE(company_code,'')='' AND package_code=%s
        """,
        (PACKAGE_CODE,),
    )
    ver = int(dict(cur.fetchone())["n"])
    pkg_payload = {
        "package_code": PACKAGE_CODE,
        "version_number": ver,
        "policy_version": POLICY_VERSION,
        "authority_kind": AUTHORITY_KIND,
    }
    fp = fingerprint_payload(pkg_payload)
    cur.execute(
        """
        INSERT INTO payroll_statutory_packages (
          country_code, company_code, package_code, version_number, approval_status,
          legal_claim, is_architecture_fixture, effective_from, title_en, title_ar,
          content_fingerprint, provenance, decision_note, created_by_phone,
          validated_by_phone, validated_at, authority_kind, policy_version
        ) VALUES (
          'KW',NULL,%s,%s,'approved',
          true,false,'2010-02-21',
          'Kuwait public statutory baseline (OctoHR-owned OFFICIAL_CLEAR)',
          'خط الأساس النظامي الكويتي العام — قواعد واضحة من مصادر رسمية',
          %s,%s::jsonb,%s,%s,
          %s,now(),%s,%s
        )
        RETURNING *
        """,
        (
            PACKAGE_CODE,
            ver,
            fp,
            json.dumps({"phase": "p4b", "pack_id": pack.get("pack_id"), "mode_a_unlocked": False}),
            str(reason).strip(),
            digits_phone(actor_phone),
            digits_phone(actor_phone),
            AUTHORITY_KIND,
            POLICY_VERSION,
        ),
    )
    package = _row(cur) or {}
    package_id = str(package.get("package_id"))

    # --- Time-pay + sick + EOS activated rules ---
    ot = _insert_activated_rule(
        cur,
        package_id=package_id,
        rule_family="ot_ordinary",
        output_class="A_employee_net",
        version_label="law6_2010_art66_public_baseline",
        effective_from="2010-02-21",
        multiplier=1.25,
        rate_payload={
            "premium_percent": 25,
            "pay_base": "original_remuneration",
            "requires_written_order": True,
            "max_hours_per_day": 2,
            "max_hours_per_year": 180,
            "max_days_per_week": 3,
            "max_days_per_year": 90,
            "article": "66",
            "law": "Law No. 6/2010",
            "night_premium_encoded": False,
            "divisor_convention": "NOT_IN_BASELINE_review_required",
        },
        applicability={"sector": ["private"], "law": ["Law No. 6/2010"]},
        official_source_ref="Kuwait Law No. 6/2010 Article 66",
        actor_phone=actor_phone,
        reason=str(reason),
        decision_note="OFFICIAL_CLEAR Art.66 ordinary OT premium",
    )
    activated.append(ot)

    rest = _insert_activated_rule(
        cur,
        package_id=package_id,
        rule_family="rest_day_work",
        output_class="A_employee_net",
        version_label="law6_2010_art67_public_baseline",
        effective_from="2010-02-21",
        multiplier=1.5,
        rate_payload={
            "formula": "original_remuneration + at_least_50_percent + compensatory_day_off",
            "weekly_rest_minimum_hours": 24,
            "distinct_from_ordinary_ot": True,
            "article": "67",
            "law": "Law No. 6/2010",
            "divisor_convention": "NOT_IN_BASELINE_review_required",
        },
        applicability={"sector": ["private"], "law": ["Law No. 6/2010"]},
        official_source_ref="Kuwait Law No. 6/2010 Article 67",
        actor_phone=actor_phone,
        reason=str(reason),
        decision_note="OFFICIAL_CLEAR Art.67 rest-day work",
    )
    activated.append(rest)

    ph = _insert_activated_rule(
        cur,
        package_id=package_id,
        rule_family="public_holiday_work",
        output_class="A_employee_net",
        version_label="law6_2010_art68_public_baseline",
        effective_from="2010-02-21",
        multiplier=2.0,
        rate_payload={
            "formula": "double_remuneration + additional_day_off",
            "distinct_from_ordinary_ot": True,
            "distinct_from_rest_day": True,
            "statutory_holidays_art68": [
                "hegeira_new_year",
                "isra_miraj",
                "eid_al_fitr_3",
                "waqfat_arafat",
                "eid_al_adha_3",
                "prophet_birthday",
                "national_day",
                "gregorian_new_year",
            ],
            "article": "68",
            "law": "Law No. 6/2010",
            "calendar_extras": "NOT_IN_BASELINE_review_required",
        },
        applicability={"sector": ["private"], "law": ["Law No. 6/2010"]},
        official_source_ref="Kuwait Law No. 6/2010 Article 68",
        actor_phone=actor_phone,
        reason=str(reason),
        decision_note="OFFICIAL_CLEAR Art.68 public-holiday work premium",
    )
    activated.append(ph)

    sick = _insert_activated_rule(
        cur,
        package_id=package_id,
        rule_family="sick_leave_fractions",
        output_class="A_employee_net",
        version_label="law6_2010_art69_public_baseline",
        effective_from="2010-02-21",
        multiplier=None,
        fraction_payload={
            "bands": [
                {"order": 1, "days": 15, "pay_fraction": 1.0},
                {"order": 2, "days": 10, "pay_fraction": 0.75},
                {"order": 3, "days": 10, "pay_fraction": 0.5},
                {"order": 4, "days": 10, "pay_fraction": 0.25},
                {"order": 5, "days": 30, "pay_fraction": 0.0},
            ],
            "total_days": 75,
            "year_basis": "NOT_IN_BASELINE_review_required",
            "pay_base": "NOT_IN_BASELINE_review_required",
            "medical_report_required": True,
            "article": "69",
            "law": "Law No. 6/2010",
        },
        rate_payload={"article": "69", "law": "Law No. 6/2010", "bands_activated": True},
        applicability={"sector": ["private"], "law": ["Law No. 6/2010"]},
        official_source_ref="Kuwait Law No. 6/2010 Article 69",
        actor_phone=actor_phone,
        reason=str(reason),
        decision_note="OFFICIAL_CLEAR Art.69 sick-leave day bands",
    )
    activated.append(sick)

    eos = _insert_activated_rule(
        cur,
        package_id=package_id,
        rule_family="eos_indemnity",
        output_class="C_settlement",
        version_label="law6_2010_art51_53_public_baseline",
        effective_from="2010-02-21",
        multiplier=None,
        rate_payload={
            "monthly_paid": {
                "first_5_years_days_per_year": 15,
                "after_5_years_days_per_year": 30,
                "cap_years_of_remuneration": 1.5,
            },
            "daily_weekly_hourly_piece": {
                "first_5_years_days_per_year": 10,
                "after_5_years_days_per_year": 15,
                "cap_years_of_remuneration": 1.0,
            },
            "fraction_of_year_pro_rata": True,
            "full_entitlement_events_art52": [
                "employer_terminates",
                "fixed_term_expires_unrenewed",
                "termination_arts_48_49_50",
                "female_resigns_within_1_year_of_marriage",
            ],
            "resignation_indefinite_art53": [
                {"service_years_min": 0, "service_years_max_exclusive": 3, "fraction": 0.0},
                {"service_years_min": 3, "service_years_max_exclusive": 5, "fraction": 0.5},
                {"service_years_min": 5, "service_years_max_exclusive": 10, "fraction": 0.6666667},
                {"service_years_min": 10, "service_years_max_exclusive": None, "fraction": 1.0},
            ],
            "law_17_2018_kuwaiti_pifss_interaction": "NOT_IN_BASELINE_review_required",
            "remuneration_base": "NOT_IN_BASELINE_classification_required",
            "article": "51/52/53",
            "law": "Law No. 6/2010",
        },
        applicability={"sector": ["private"], "law": ["Law No. 6/2010"]},
        official_source_ref="Kuwait Law No. 6/2010 Arts 51–53",
        actor_phone=actor_phone,
        reason=str(reason),
        decision_note="OFFICIAL_CLEAR Arts 51–53 EOS structure; Law17/remuneration base gated",
    )
    activated.append(eos)

    # --- PIFSS package rule + specs ---
    pifss_rule = _insert_activated_rule(
        cur,
        package_id=package_id,
        rule_family="pifss",
        output_class="mixed_pifss_pack",
        version_label="pifss_faq_public_baseline",
        effective_from="2010-02-21",
        multiplier=None,
        rate_payload={
            "wage_base_mapping": "NOT_IN_BASELINE_classification_required",
            "financial_remuneration": "NOT_IN_BASELINE_review_required",
            "gcc_extension": "NOT_IN_BASELINE_review_required",
            "expatriate": "NOT_IN_BASELINE_review_required",
            "primary_source_url": "https://www.pifss.gov.kw/sites/En/Pages/PensionSocialSecuritySector/FAQ.aspx",
        },
        applicability={"employee_category": ["kuwaiti_national"]},
        official_source_ref="PIFSS official FAQ contribution ratios",
        actor_phone=actor_phone,
        reason=str(reason),
        decision_note="OFFICIAL_CLEAR PIFSS contribution ratios; wage mapping gated",
    )
    activated.append(pifss_rule)
    pifss_id = str(pifss_rule.get("rule_version_id"))

    pifss_specs = [
        ("basic", "employee_deduction", 5.0, 1500.0, "2010-02-21", "pifss_basic_insured_salary"),
        ("basic", "employer_contribution", 10.0, 1500.0, "2010-02-21", "pifss_basic_insured_salary"),
        ("supplementary", "employee_deduction", 5.0, 1250.0, "2010-02-21", "pifss_supplementary_insured_salary"),
        ("supplementary", "employer_contribution", 10.0, 1250.0, "2010-02-21", "pifss_supplementary_insured_salary"),
        ("pension_increase", "employee_deduction", 2.5, 2750.0, "2010-02-21", "pifss_pension_increase_salary"),
        ("pension_increase", "employer_contribution", 1.0, 2750.0, "2010-02-21", "pifss_pension_increase_salary"),
        ("unemployment_private_oil", "employee_deduction", 0.5, 2750.0, "2013-05-01", "pifss_unemployment_salary"),
        ("unemployment_private_oil", "employer_contribution", 0.5, 2750.0, "2013-05-01", "pifss_unemployment_salary"),
        ("aggregate_remittance", "remittance_obligation", None, None, "2010-02-21", "sum_of_applicable_funds"),
    ]
    side_to_class = {
        "employee_deduction": "A_employee_net",
        "employer_contribution": "B_employer_liability",
        "remittance_obligation": "D_remittance_reporting",
    }
    for fund, side, pct, cap, _ef, base in pifss_specs:
        cur.execute(
            """
            INSERT INTO payroll_pifss_contribution_specs (
              rule_version_id, country_code, employee_category, contribution_side, output_class,
              fund_code, base_definition, cap_definition, rate_percent,
              rate_is_architecture_fixture, rate_awaiting_legal_validation,
              eligibility_notes, remittance_notes, metadata,
              source_classification, official_source_ref
            ) VALUES (
              %s,'KW','kuwaiti_national',%s,%s,
              %s,%s,%s,%s,
              false,false,
              %s,%s,%s::jsonb,
              'OFFICIAL_CLEAR',%s
            )
            ON CONFLICT (rule_version_id, employee_category, contribution_side, fund_code) DO UPDATE
              SET rate_percent=EXCLUDED.rate_percent,
                  source_classification='OFFICIAL_CLEAR',
                  official_source_ref=EXCLUDED.official_source_ref,
                  metadata=EXCLUDED.metadata
            RETURNING *
            """,
            (
                pifss_id,
                side,
                side_to_class[side],
                fund,
                base,
                f"cap_kwd_{cap}" if cap is not None else None,
                float(pct) if pct is not None else None,
                "Kuwaiti insured; wage base must be classified separately",
                "Remittance prep only — not payment processing" if side == "remittance_obligation" else None,
                json.dumps(
                    {
                        "legal_claim": True,
                        "authority_kind": AUTHORITY_KIND,
                        "policy_version": POLICY_VERSION,
                        "fund": fund,
                        "effective_hint": _ef,
                    }
                ),
                "PIFSS official FAQ contribution ratios",
            ),
        )
        activated.append({"pifss_spec": _json_safe(_row(cur))})

    return {
        "ok": True,
        "already_active": False,
        "package": _json_safe(package),
        "activated_rules": _json_safe(
            [
                {
                    "rule_family": r.get("rule_family"),
                    "rule_version_id": r.get("rule_version_id"),
                    "version_label": r.get("version_label"),
                    "multiplier": r.get("multiplier"),
                    "official_source_ref": r.get("official_source_ref"),
                    "policy_version": r.get("policy_version"),
                    "legal_claim": r.get("legal_claim"),
                    "authority_kind": r.get("authority_kind"),
                }
                for r in activated
                if isinstance(r, dict) and r.get("rule_family")
            ]
        ),
        "activated_pifss_specs": len(pifss_specs),
        "still_gated": gated,
        **honesty_payload(),
    }


def evaluate_pifss_with_baseline(
    cur: Any,
    *,
    as_of: str | date,
    employee_category: str | None,
    pifss_wage_by_fund: dict[str, Any] | None,
    sector: str | None = "private",
) -> dict[str, Any]:
    """Compute PIFSS A/B/D lines only when category + classified wage bases are provided."""
    ensure_payroll_statutory_baseline_schema(cur)
    if not employee_category:
        return {"ok": False, "blocker": GATED_BLOCKERS["pifss_category_classification_required"], **honesty_payload()}
    if employee_category == "gcc_national":
        return {"ok": False, "blocker": GATED_BLOCKERS["gcc_extension_review_required"], **honesty_payload()}
    if employee_category != "kuwaiti_national":
        return {
            "ok": False,
            "blocker": {
                "code": "pifss_expatriate_or_other_review_required",
                "message": "Non-Kuwaiti PIFSS applicability remains review-gated in public baseline v1.",
            },
            **honesty_payload(),
        }
    rule = resolve_public_baseline_rule(
        cur, rule_family="pifss", as_of=as_of, employee_category=employee_category, sector=sector
    )
    if not rule:
        return {"ok": False, "error": "pifss_baseline_missing", **honesty_payload()}
    if not pifss_wage_by_fund:
        return {"ok": False, "blocker": GATED_BLOCKERS["pifss_wage_base_classification_required"], **honesty_payload()}

    cur.execute(
        """
        SELECT * FROM payroll_pifss_contribution_specs
        WHERE rule_version_id=%s AND employee_category='kuwaiti_national'
          AND source_classification='OFFICIAL_CLEAR'
        ORDER BY fund_code, contribution_side
        """,
        (rule.get("rule_version_id"),),
    )
    specs = cur.fetchall()
    cols = [d[0] for d in cur.description]
    lines_a: list[dict[str, Any]] = []
    lines_b: list[dict[str, Any]] = []
    lines_d: list[dict[str, Any]] = []
    for raw in specs:
        spec = dict(raw) if isinstance(raw, dict) else dict(zip(cols, raw))
        fund = str(spec.get("fund_code") or "")
        side = str(spec.get("contribution_side") or "")
        if side == "remittance_obligation":
            lines_d.append(
                {
                    "fund_code": fund,
                    "output_class": "D_remittance_reporting",
                    "note": spec.get("remittance_notes"),
                    "is_payment_processing": False,
                }
            )
            continue
        wage = pifss_wage_by_fund.get(fund)
        if wage is None:
            # Unemployment may be absent pre-2013-05-01; other funds required when wage map present
            if fund == "unemployment_private_oil":
                as_of_d = p4a._parse_date(as_of)  # noqa: SLF001
                if as_of_d and as_of_d < date(2013, 5, 1):
                    continue
            return {
                "ok": False,
                "blocker": GATED_BLOCKERS["pifss_wage_base_classification_required"],
                "missing_fund": fund,
                **honesty_payload(),
            }
        rate = Decimal(str(spec.get("rate_percent") or 0))
        cap_def = str(spec.get("cap_definition") or "")
        cap = None
        if cap_def.startswith("cap_kwd_"):
            try:
                cap = Decimal(cap_def.replace("cap_kwd_", ""))
            except Exception:
                cap = None
        base = min(Decimal(str(wage)), cap) if cap is not None else Decimal(str(wage))
        amount = money(base * rate / Decimal("100"))
        line = {
            "fund_code": fund,
            "contribution_side": side,
            "output_class": spec.get("output_class"),
            "rate_percent": float(rate),
            "wage_base": float(base),
            "amount": float(amount),
            "employee_net_impact": side == "employee_deduction",
            "rule_version_id": str(rule.get("rule_version_id")),
            "policy_version": POLICY_VERSION,
            "official_source_ref": rule.get("official_source_ref"),
        }
        if side == "employee_deduction":
            lines_a.append(line)
        else:
            lines_b.append(line)

    return {
        "ok": True,
        "A_employee_net": lines_a,
        "B_employer_liability": lines_b,
        "D_remittance_reporting": lines_d,
        "policy_version": POLICY_VERSION,
        "rule_version_id": str(rule.get("rule_version_id")),
        **honesty_payload(),
    }


def evaluate_eos_settlement_baseline(
    cur: Any,
    *,
    as_of: str | date,
    pay_frequency: str,
    termination: str,
    contract_type: str,
    service_years: float,
    remuneration_for_eos: Any | None,
    employee_category: str | None = None,
    sector: str = "private",
) -> dict[str, Any]:
    """EOS is settlement (C), never monthly G2N. Remuneration base + Law17 remain gated."""
    ensure_payroll_statutory_baseline_schema(cur)
    if remuneration_for_eos is None:
        return {"ok": False, "blocker": GATED_BLOCKERS["eos_remuneration_base_classification_required"], **honesty_payload()}
    if employee_category == "kuwaiti_national":
        return {
            "ok": False,
            "blocker": GATED_BLOCKERS["eos_pifss_interaction_review_required"],
            "message": "Formula baseline exists, but Kuwaiti × PIFSS / Law 17/2018 path stays review-gated.",
            "formula_available": True,
            **honesty_payload(),
        }
    rule = resolve_public_baseline_rule(
        cur,
        rule_family="eos_indemnity",
        as_of=as_of,
        sector=sector,
        pay_frequency=pay_frequency if pay_frequency in ("daily", "weekly", "hourly", "piece") else "monthly",
        contract_type=contract_type,
        termination=termination,
    )
    if not rule:
        # Fall back: rule may have only sector applicability
        rule = resolve_public_baseline_rule(cur, rule_family="eos_indemnity", as_of=as_of, sector=sector)
    if not rule:
        return {"ok": False, "error": "eos_baseline_missing", **honesty_payload()}

    payload = rule.get("rate_payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    monthly = pay_frequency == "monthly"
    band = payload.get("monthly_paid") if monthly else payload.get("daily_weekly_hourly_piece")
    rem = Decimal(str(remuneration_for_eos))
    years = Decimal(str(service_years))
    first = min(years, Decimal("5"))
    after = max(years - Decimal("5"), Decimal("0"))
    days_first = Decimal(str(band["first_5_years_days_per_year"]))
    days_after = Decimal(str(band["after_5_years_days_per_year"]))
    # Convert days to months of remuneration: days/30
    amount = (first * days_first + after * days_after) / Decimal("30") * rem
    cap_years = Decimal(str(band["cap_years_of_remuneration"]))
    amount = min(amount, cap_years * rem)

    fraction = Decimal("1")
    if termination == "employee_resignation" and contract_type == "indefinite":
        for tier in payload.get("resignation_indefinite_art53") or []:
            mn = Decimal(str(tier.get("service_years_min") or 0))
            mx = tier.get("service_years_max_exclusive")
            if years >= mn and (mx is None or years < Decimal(str(mx))):
                fraction = Decimal(str(tier.get("fraction") or 0))
                break
        amount = amount * fraction

    return {
        "ok": True,
        "output_class": "C_settlement",
        "monthly_g2n": False,
        "auto_payable": False,
        "payment_processing": "disabled",
        "provisional_amount": float(money(amount)),
        "resignation_fraction": float(fraction),
        "rule_version_id": str(rule.get("rule_version_id")),
        "policy_version": POLICY_VERSION,
        "official_source_ref": rule.get("official_source_ref"),
        **honesty_payload(),
    }


def setup_console_ownership_matrix() -> dict[str, Any]:
    """Wathefni-owned vs company-provided inputs for future Setup Console."""
    return {
        "wathefni_owned_kuwait_statutory_baseline": [
            "Ordinary OT premium (Art.66 +25%)",
            "Rest-day work premium (Art.67 ≥50% + compensatory day)",
            "Public-holiday work premium (Art.68 double + day off)",
            "Sick-leave statutory day bands (Art.69)",
            "EOS indemnity structure Arts 51–53 (settlement)",
            "PIFSS Kuwaiti contribution % and caps (FAQ table)",
            "PIFSS remittance timing notes (reporting prep)",
            "Statutory policy version + source provenance",
        ],
        "company_provided_never_kuwait_law": [
            "Payroll operating mode (preview / synthetic / future modes)",
            "Employee statutory classification (kuwaiti / gcc / expatriate)",
            "PIFSS insurable wage base by fund (classified components — not auto BASIC)",
            "Salary/allowance structures and custom earnings/deductions",
            "OT eligibility groups / who may be ordered OT",
            "Attendance-pay and lateness policy",
            "Payroll cut-off and period settings",
            "Approval workflow",
            "Working-day calendar / weekly rest definition for divisor operations",
            "Annual public-holiday calendar additions beyond Art.68 list",
            "Sick-leave year basis choice when required by operations",
            "EOS last-remuneration classified input",
            "Special regime flags (oil / GCC extension / Law17 interaction resolution)",
        ],
        "never_ask_company": [
            "What is Kuwait OT premium?",
            "What is Kuwait sick-leave band table?",
            "What are Kuwaiti PIFSS contribution percentages?",
        ],
        "review_gated_exception_layer": [
            "GCC extension home-scheme rates",
            "Oil/special-sector regimes",
            "PIFSS wage-element mapping disputes",
            "EOS × PIFSS Law 17/2018",
            "Night OT +50% (unsupported in baseline)",
            "Financial remuneration 2.5% eligibility",
        ],
    }


def workspace_bootstrap(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_payroll_statutory_baseline_schema(cur)
    company = (company_code or "").upper()
    as_of = date.today()
    families = {}
    for fam in MANDATORY_STATUTORY_FAMILIES:
        rule = resolve_public_baseline_rule(cur, rule_family=fam, as_of=as_of, sector="private")
        families[fam] = {
            "baseline_active": bool(rule),
            "rule_version_id": str(rule.get("rule_version_id")) if rule else None,
            "policy_version": rule.get("policy_version") if rule else None,
            "official_source_ref": rule.get("official_source_ref") if rule else None,
            "multiplier": float(rule["multiplier"]) if rule and rule.get("multiplier") is not None else None,
        }
    return {
        "ok": True,
        "company_code": company,
        "p4b_enabled": payroll_authority_p4b_enabled_for_company(company),
        "families": families,
        "setup_matrix": setup_console_ownership_matrix(),
        "classification_pack_id": load_classification_pack().get("pack_id"),
        **honesty_payload(),
        **p4a.honesty_payload(),
    }
