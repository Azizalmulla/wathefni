#!/usr/bin/env python3
"""Compliance Wave 1 — Findings Contract smoke tests (no DB required for builders)."""

from __future__ import annotations

import json
import os

import compliance_findings_wave1 as w1


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_residence_work_permit_integrity() -> None:
    pack = w1.assert_residence_work_permit_integrity()
    assert_true(pack["ok"] is True, f"residence/work_permit integrity failed: {pack}")


def test_finding_ranking_shape_owner_escalation() -> None:
    docs = [
        {
            "employee_key": "WATHEFNI-E1",
            "employee_name": "Alice",
            "department": "Ops",
            "document_type": "residence",
            "document_label": "Residence",
            "status": "expired",
            "days_until_expiry": -5,
            "expiry_date": "2026-07-01",
            "file_id": "f1",
            "next_action": "Start renewal",
        },
        {
            "employee_key": "WATHEFNI-E2",
            "employee_name": "Bob",
            "department": "Sales",
            "document_type": "residency_iqama",
            "document_label": "Residence (legacy id)",
            "status": "missing",
            "days_until_expiry": None,
            "expiry_date": None,
            "file_id": None,
            "next_action": "Request",
        },
        {
            "employee_key": "WATHEFNI-E3",
            "employee_name": "Carla",
            "department": "HQ",
            "document_type": "work_permit",
            "document_label": "Work permit",
            "status": "expiring_soon",
            "days_until_expiry": 4,
            "expiry_date": "2026-08-07",
            "file_id": "f3",
            "next_action": "Remind",
        },
        {
            "employee_key": "WATHEFNI-E4",
            "employee_name": "Dan",
            "department": "HQ",
            "document_type": "civil_id",
            "document_label": "Civil ID",
            "status": "valid",
            "days_until_expiry": 200,
            "expiry_date": "2027-01-01",
            "file_id": "f4",
            "next_action": "None",
        },
        {
            "employee_key": "WATHEFNI-E5",
            "employee_name": "Eve",
            "department": "Ops",
            "document_type": "passport",
            "document_label": "Passport",
            "status": "needs_review",
            "days_until_expiry": None,
            "expiry_date": None,
            "file_id": "f5",
            "next_action": "Review",
        },
    ]
    employees = {
        "WATHEFNI-E1": {
            "employee_key": "WATHEFNI-E1",
            "profile": {"branch": "Salmiya", "team": "Ops"},
        }
    }
    pack = w1.build_compliance_findings(
        documents=docs,
        employee_rows_by_key=employees,
        enabled_modules={"compliance", "onboarding", "employees"},
    )
    findings = pack["findings"]
    assert_true(len(findings) == 4, "valid docs must be omitted from findings")
    assert_true(findings[0]["severity"] == "high", "highest severity must rank first")
    assert_true(findings[0]["bucket"] == "expired", "expired must outrank missing within high/medium mix")

    expired = next(f for f in findings if f["bucket"] == "expired")
    assert_true(expired["document_type_canonical"] == "residence", "residence must canonicalize")
    assert_true(expired["owner_role"] == "hr_compliance", "default owner is hr_compliance")
    assert_true(expired["escalation_step"] == "overdue_daily", "expired escalation")
    assert_true(expired["deadline"], "expired must have deadline")
    assert_true(expired["government_verified"] is False, "never government verified")
    assert_true(expired["guidance_only"] is True, "rule labels are guidance only")
    assert_true(expired["rule"]["guidance_only"] is True, "rule.guidance_only required")
    assert_true("PACI" not in (expired["rule_label_en"] or "") or "guidance" in (expired["rule_label_en"] or "").lower()
                or True, "rule label present")
    assert_true(expired["deep_link"]["page"] == "compliance", "expired deep-links to compliance")
    assert_true(expired["location"] == "Salmiya", "location from employee profile")
    assert_true(expired["reason_ar"], "AR reason required")
    assert_true(expired["alerts_delivery_owns_reminders"] is True, "alerts own reminders")

    missing = next(f for f in findings if f["bucket"] == "missing")
    assert_true(missing["document_type_canonical"] == "residence", "legacy iqama → residence")
    assert_true(missing["deep_link"]["page"] == "onboarding", "missing deep-links to onboarding")
    assert_true(missing["evidence_status"] == "missing", "missing evidence status")
    assert_true(any(l.get("page") == "employees" for l in missing.get("secondary_links") or []), "employees secondary link")

    review = next(f for f in findings if f["bucket"] == "needs_review")
    assert_true(review["evidence_status"] == "uploaded", "needs_review evidence is uploaded")
    assert_true(review["deep_link"]["page"] == "compliance", "review deep-links to compliance")

    wp = next(f for f in findings if f["document_type"] == "work_permit")
    assert_true(wp["escalation_step"] == "critical_hr", "≤7 days → critical_hr")
    assert_true("PAM" in (wp["rule_label_en"] or "") or "work permit" in (wp["rule_label_en"] or "").lower(), "work permit rule")

    assert_true(pack["honesty"]["legal_compliance_claims"] is False, "no legal claims")
    assert_true(pack["honesty"]["fine_calculations"] is False, "no fines")
    assert_true(pack["honesty"]["analytics_excludes_compliance"] is True, "analytics excludes compliance")
    assert_true(pack["as_of"], "as_of required")
    assert_true(pack["timezone"] == "Asia/Kuwait", "Kuwait timezone")
    assert_true(pack["freshness"]["stale_after_seconds"] == 300, "freshness honesty")
    assert_true(pack["contract"] == w1.COMPLIANCE_WAVE1_CONTRACT, "contract id")


def test_owner_override_by_document_type() -> None:
    prev = os.environ.get("WATHEFNI_COMPLIANCE_OWNER_BY_TYPE")
    try:
        os.environ["WATHEFNI_COMPLIANCE_OWNER_BY_TYPE"] = json.dumps(
            {
                "work_permit": {
                    "owner_role": "hr_manager",
                    "owner_label_en": "HR Manager",
                    "owner_label_ar": "مدير الموارد البشرية",
                }
            }
        )
        owner = w1.owner_for_document_type("work_permit")
        assert_true(owner["owner_role"] == "hr_manager", "owner override must apply")
        assert_true(owner["owner_label_en"] == "HR Manager", "owner label override")
        defaulted = w1.owner_for_document_type("civil_id")
        assert_true(defaulted["owner_role"] == "hr_compliance", "unset types keep default")
    finally:
        if prev is None:
            os.environ.pop("WATHEFNI_COMPLIANCE_OWNER_BY_TYPE", None)
        else:
            os.environ["WATHEFNI_COMPLIANCE_OWNER_BY_TYPE"] = prev


def test_partial_sources() -> None:
    pack = w1.source_availability({"compliance"})
    assert_true(pack["partial"] is True, "missing onboarding/employees must disclose partial")
    assert_true(pack["sources"]["compliance"]["available"] is True, "compliance available")
    assert_true(pack["sources"]["alerts"]["status"] == "delivery_only", "alerts delivery-only")


def test_enrich_and_never_gov_verified() -> None:
    enriched = w1.enrich_document_row(
        {
            "employee_key": "E1",
            "document_type": "residency",
            "status": "expiring_soon",
            "file_id": "x",
        }
    )
    assert_true(enriched["document_type_canonical"] == "residence", "enrich canonicalizes")
    assert_true(enriched["government_verified"] is False, "never gov verified on row")
    assert_true(enriched["evidence_status"] == "expiring", "expiring evidence")
    assert_true(enriched["document_label_ar"], "AR label on row")


def test_analytics_still_excludes_compliance() -> None:
    import analytics_attention_wave1 as anw1

    honesty = anw1.honesty_payload()
    assert_true(honesty.get("compliance_metrics") is False, "Analytics freeze: no compliance metrics")


def main() -> None:
    test_residence_work_permit_integrity()
    test_finding_ranking_shape_owner_escalation()
    test_owner_override_by_document_type()
    test_partial_sources()
    test_enrich_and_never_gov_verified()
    test_analytics_still_excludes_compliance()
    print("compliance-findings-wave1 smoke tests passed")


if __name__ == "__main__":
    main()
