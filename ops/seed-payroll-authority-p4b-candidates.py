#!/usr/bin/env python3
"""Seed P4B-prep Kuwait statutory candidates into P4A tables.

Loads ops/payroll_authority_p4b_candidate_records_v1.json as:
  approval_status=awaiting_legal_validation
  legal_claim=false
  counsel_signed=false
  is_architecture_fixture=false

Does NOT approve, activate P4B, unlock Mode A, enable PDF/payments, or set legal_claim.
Dry-run (default): validate payload only. Use --apply to insert.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = ROOT / "ops" / "payroll_authority_p4b_candidate_records_v1.json"
ORCH_CANDIDATES = [
    ROOT / "wathefni-orchestrator",
    Path("/opt/wathefni/orchestrator"),
    ROOT / "orchestrator",
    ROOT,
]
ORCH = next(
    (p for p in ORCH_CANDIDATES if (p / "payroll_statutory_architecture_p4a.py").exists()),
    ORCH_CANDIDATES[0],
)
sys.path.insert(0, str(ORCH))

FORBIDDEN_STATUS = {"approved"}
REQUIRED_DEFAULTS = {
    "approval_status": "awaiting_legal_validation",
    "legal_claim": False,
    "counsel_signed": False,
    "is_architecture_fixture": False,
}


def load_candidates() -> dict[str, Any]:
    data = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    defaults = data.get("defaults") or {}
    for key, expected in REQUIRED_DEFAULTS.items():
        if defaults.get(key) != expected:
            raise SystemExit(f"Candidate defaults.{key} must be {expected!r}, got {defaults.get(key)!r}")
    if not data.get("activation_forbidden"):
        raise SystemExit("activation_forbidden must be true")
    return data


def validate_only(data: dict[str, Any]) -> None:
    pkg = data.get("package") or {}
    assert pkg.get("package_code"), "package_code required"
    pifss = data.get("pifss_contribution_specs") or []
    time_pay = data.get("time_pay_rule_tables") or []
    eos = data.get("eos_rule_tables") or []
    print(f"pack_id={data.get('pack_id')}")
    print(f"pifss_specs={len(pifss)} time_pay={len(time_pay)} eos={len(eos)}")
    for row in pifss + time_pay + eos:
        status = row.get("counsel_status") or ""
        if status.lower().replace(" ", "_") in ("approved", "legal_claim"):
            raise SystemExit(f"Forbidden counsel_status on candidate: {row}")
    print("validation_ok — awaiting_legal_validation only; legal_claim=false")


def apply_seed(data: dict[str, Any], *, company_code: str | None, actor: str) -> dict[str, Any]:
    import payroll_statutory_architecture_p4a as p4a

    # Match P4A smoke env defaults when running against canary.
    os.environ.setdefault("WATHEFNI_PAYROLL_AUTHORITY_P4A", "1")

    import app as orch_app  # noqa: WPS433 — production app.db_connect

    pkg_meta = data["package"]
    reason = f"p4b_prep_seed_{data.get('pack_id')}"
    out: dict[str, Any] = {"package": None, "rule_versions": [], "pifss_specs": [], "guards": []}

    with orch_app.db_connect() as conn:
        with conn.cursor() as cur:
            p4a.ensure_payroll_statutory_architecture_schema(cur, force=True)
            created = p4a.create_statutory_package(
                cur,
                country_code=str(data.get("country_code") or "KW"),
                company_code=company_code,
                package_code=str(pkg_meta["package_code"]),
                effective_from=str(pkg_meta.get("effective_from") or "2010-02-21"),
                title_en=str(pkg_meta.get("title_en") or "Kuwait P4B prep candidates"),
                title_ar=pkg_meta.get("title_ar"),
                actor_phone=actor,
                reason=reason,
                is_architecture_fixture=False,
                approval_status="awaiting_legal_validation",
            )
            if not created.get("ok"):
                raise SystemExit(f"package create failed: {created}")
            package = created["package"]
            if package.get("legal_claim") or package.get("approval_status") in FORBIDDEN_STATUS:
                raise SystemExit(f"guard fail package: {package}")
            package_id = str(package["package_id"])
            out["package"] = {
                "package_id": package_id,
                "approval_status": package.get("approval_status"),
                "legal_claim": package.get("legal_claim"),
            }

            # One PIFSS rule version; fund_code distinguishes contribution rows.
            pifss_rule = p4a.create_rule_version(
                cur,
                package_id=package_id,
                rule_family="pifss",
                output_class="mixed_pifss_pack",
                version_label=f"{pkg_meta.get('version_label') or 'p4b_prep_v1'}_pifss",
                effective_from=str(pkg_meta.get("effective_from") or "2010-02-21"),
                actor_phone=actor,
                reason=reason,
                rate_payload={
                    "pack_id": data.get("pack_id"),
                    "source": "ops/payroll_authority_p4b_candidate_records_v1.json",
                    "legal_claim": False,
                },
                is_architecture_fixture=False,
                approval_status="awaiting_legal_validation",
                company_code=company_code,
            )
            if not pifss_rule.get("ok"):
                raise SystemExit(f"pifss rule create failed: {pifss_rule}")
            pifss_rv = pifss_rule["rule_version"]
            assert pifss_rv.get("legal_claim") is False
            assert pifss_rv.get("counsel_signed") is False
            assert pifss_rv.get("approval_status") == "awaiting_legal_validation"
            out["rule_versions"].append(
                {
                    "rule_family": "pifss",
                    "rule_version_id": pifss_rv.get("rule_version_id"),
                    "approval_status": pifss_rv.get("approval_status"),
                    "legal_claim": False,
                }
            )

            for spec in data.get("pifss_contribution_specs") or []:
                cap = spec.get("cap_kwd")
                cap_def = f"cap_kwd_{cap}" if cap is not None else None
                notes = spec.get("notes") or spec.get("primary_source")
                rem = spec.get("remittance_notes")
                inserted = p4a.add_pifss_contribution_spec(
                    cur,
                    rule_version_id=str(pifss_rv["rule_version_id"]),
                    employee_category=str(spec["employee_category"]),
                    contribution_side=str(spec["contribution_side"]),
                    actor_phone=actor,
                    reason=reason,
                    rate_percent=spec.get("rate_percent"),
                    rate_is_architecture_fixture=False,
                    rate_awaiting_legal_validation=True if spec.get("rate_percent") is not None else False,
                    fund_code=str(spec.get("fund") or "unspecified"),
                    base_definition=str(spec.get("base_definition") or "contributory_wage"),
                    cap_definition=cap_def,
                    eligibility_notes=notes,
                    remittance_notes=rem,
                    metadata={
                        "primary_source": spec.get("primary_source"),
                        "primary_source_url": spec.get("primary_source_url"),
                        "confidence": spec.get("confidence"),
                        "counsel_status": spec.get("counsel_status"),
                        "pack_id": data.get("pack_id"),
                        "legal_claim": False,
                        "counsel_signed": False,
                    },
                )
                if not inserted.get("ok"):
                    raise SystemExit(f"pifss spec failed: {inserted}")
                row = inserted["spec"]
                if row.get("rate_is_architecture_fixture"):
                    raise SystemExit("guard: architecture fixture flag set on candidate")
                out["pifss_specs"].append(
                    {
                        "fund_code": row.get("fund_code"),
                        "employee_category": row.get("employee_category"),
                        "contribution_side": row.get("contribution_side"),
                        "rate_percent": row.get("rate_percent"),
                        "rate_awaiting_legal_validation": row.get("rate_awaiting_legal_validation"),
                    }
                )

            for table in (data.get("time_pay_rule_tables") or []) + (data.get("eos_rule_tables") or []):
                family = str(table["rule_family"])
                output_class = str(table["output_class"])
                created_rv = p4a.create_rule_version(
                    cur,
                    package_id=package_id,
                    rule_family=family,
                    output_class=output_class,
                    version_label=str(table.get("version_label") or f"{family}_candidate"),
                    effective_from=str(table.get("effective_from") or pkg_meta.get("effective_from") or "2010-02-21"),
                    actor_phone=actor,
                    reason=reason,
                    rate_payload={
                        **(table.get("rate_payload") or {}),
                        "primary_source": table.get("primary_source"),
                        "confidence": table.get("confidence"),
                        "counsel_status": table.get("counsel_status"),
                        "pack_id": data.get("pack_id"),
                        "legal_claim": False,
                    },
                    multiplier=table.get("multiplier"),
                    fraction_payload=table.get("fraction_payload") or {},
                    is_architecture_fixture=False,
                    approval_status="awaiting_legal_validation",
                    company_code=company_code,
                )
                if not created_rv.get("ok"):
                    raise SystemExit(f"{family} rule create failed: {created_rv}")
                rv = created_rv["rule_version"]
                if (
                    rv.get("legal_claim")
                    or rv.get("counsel_signed")
                    or rv.get("approval_status") != "awaiting_legal_validation"
                    or rv.get("is_architecture_fixture")
                ):
                    raise SystemExit(f"guard fail rule {family}: {rv}")
                # Must not resolve on legal money path
                resolved_legal = p4a.resolve_rule_version(
                    cur,
                    company_code=company_code,
                    rule_family=family,
                    as_of=str(table.get("effective_from") or "2026-08-01"),
                    require_legal_claim=True,
                    allow_architecture_fixture=False,
                )
                if resolved_legal and str(resolved_legal.get("rule_version_id")) == str(rv.get("rule_version_id")):
                    raise SystemExit(f"guard: candidate resolved on legal path for {family}")
                out["rule_versions"].append(
                    {
                        "rule_family": family,
                        "rule_version_id": rv.get("rule_version_id"),
                        "approval_status": rv.get("approval_status"),
                        "legal_claim": False,
                        "counsel_signed": False,
                        "multiplier": rv.get("multiplier"),
                    }
                )

            out["guards"].append("no_legal_claim")
            out["guards"].append("no_counsel_signed")
            out["guards"].append("awaiting_legal_validation_only")
            out["guards"].append("not_resolved_on_legal_money_path")
            conn.commit()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Insert candidates into DB (default: dry-run validate)")
    parser.add_argument("--company", default=None, help="Optional company overlay (e.g. WATHEFNI); default country-level")
    parser.add_argument("--actor", default="96550000000", help="Audit phone digits")
    parser.add_argument("--out", default="", help="Optional JSON summary path")
    parser.add_argument("--ack-non-production", default=os.environ.get("WATHEFNI_DATA_SAFETY_ACK"))
    args = parser.parse_args()

    data = load_candidates()
    validate_only(data)
    if not args.apply:
        print("dry_run_complete — pass --apply to insert awaiting_legal_validation rows")
        return 0

    sys.path.insert(0, str(ORCH))
    import production_data_safety as _pds

    if args.ack_non_production:
        os.environ["WATHEFNI_DATA_SAFETY_ACK"] = args.ack_non_production
    _pds.require_non_production_target()
    _pds.require_non_production_ack()
    if args.company:
        _pds.require_fixture_company(args.company)

    summary = apply_seed(data, company_code=(args.company or None), actor=args.actor)
    text = json.dumps(summary, indent=2, default=str)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print("seed_complete — P4B NOT activated; legal_claim=false; counsel_signed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
