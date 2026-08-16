#!/usr/bin/env python3
"""Action Inbox Wave 1 — Unified Action Inbox smoke tests (no DB for builders)."""

from __future__ import annotations

import os

import action_inbox_wave1 as w1


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_cross_source_ranking_and_shape() -> None:
    pack = w1.build_action_inbox(
        analytics_attention=[
            {
                "id": "pending_leave",
                "severity": "high",
                "reason_en": "3 leave requests await a decision",
                "reason_ar": "3 طلبات إجازة بانتظار القرار",
                "subject": "Leave queue",
                "source_module": "leave",
                "deep_link": {"page": "leave"},
            }
        ],
        compliance_findings=[
            {
                "id": "expired:E1:residence",
                "severity": "high",
                "reason_en": "Alice residence expired",
                "reason_ar": "إقامة Alice منتهية",
                "why_it_matters_en": "MOI guidance only",
                "why_it_matters_ar": "إرشاد",
                "employee_key": "E1",
                "employee_name": "Alice",
                "team": "Ops",
                "location": "Salmiya",
                "document_type": "residence",
                "document_type_canonical": "residence",
                "owner_role": "hr_compliance",
                "owner_label_en": "Company HR / Compliance",
                "owner_label_ar": "الموارد البشرية",
                "deadline": "2026-08-03",
                "deadline_label_en": "Overdue",
                "escalation_step": "overdue_daily",
                "escalation_label_en": "Daily follow-up",
                "system_of_action": "compliance",
                "evidence_status": "expired",
                "evidence_status_label_en": "Expired",
                "deep_link": {"page": "compliance", "employee": "E1", "document_type": "residence"},
                "government_verified": False,
                "guidance_only": True,
            }
        ],
        e360_next_actions=[
            w1.normalize_e360_next_action(
                {
                    "id": "onboarding:incomplete",
                    "severity": "medium",
                    "module": "onboarding",
                    "title": "Onboarding incomplete",
                    "reason": "2 required items still open",
                    "target": {"page": "onboarding", "section": "onboarding"},
                },
                employee_key="E2",
                employee_name="Bob",
                team="Sales",
            )
        ],
        apply_phase0_filters=False,
    )
    items = pack["items"]
    assert_true(len(items) == 3, "three streams should contribute")
    assert_true(items[0]["severity"] in {"high", "critical"}, "high severity first")
    for item in items:
        for key in (
            "what_en",
            "why_en",
            "owner_label_en",
            "source_module",
            "system_of_action",
            "deep_link",
            "evidence_status_label_en",
            "authority_status_label_en",
        ):
            assert_true(bool(item.get(key)), f"missing {key}")
        assert_true(item.get("government_verified") is False or item.get("government_verified") is None, "never gov verified")
        assert_true(isinstance(item.get("deep_link"), dict) and item["deep_link"].get("page"), "deep link page")
    assert_true(pack["honesty"]["mutates_records"] is False, "read-only")
    assert_true(pack["honesty"]["ai"] is False, "no AI")
    assert_true(pack["honesty"]["hiring_reports_separate"] is True, "hiring reports separate")
    assert_true(pack["honesty"]["alerts_delivery_owns_notifications"] is True, "alerts own delivery")
    assert_true(pack["as_of"], "as_of")
    assert_true(pack["timezone"] == "Asia/Kuwait", "Kuwait tz")


def test_dedupe_and_clear_on_source_resolve() -> None:
    proof = w1.prove_item_clears_when_source_resolves()
    assert_true(proof["deduped"] >= 1, "E360 compliance duplicate must dedupe")
    assert_true(proof["cleared"] is True, "items must clear when sources resolve")
    assert_true(proof["after_total"] == 1, "only unresolved onboarding remains")
    assert_true(
        proof["remaining_ids"] == ["employees:E1:onboarding:incomplete"],
        proof["remaining_ids"],
    )


def test_phase0_fail_closed_and_payroll_exclude() -> None:
    prev_v = os.environ.get("WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST")
    prev_s = os.environ.get("WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST")
    try:
        os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = ""
        os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = ""
        assert_true(w1.viewer_is_allowlisted(phone="96599338566") is False, "empty viewer deny Aziz")
        assert_true(w1.nav_offerable_for_viewer(company_code="WATHEFNI", phone="96599338566") is False, "nav soft-kill")

        soft = w1.build_action_inbox(
            compliance_findings=[
                {
                    "id": "x",
                    "severity": "high",
                    "reason_en": "Expired",
                    "employee_key": "WATHEFNI-96550252254",
                    "document_type": "residence",
                    "document_type_canonical": "residence",
                    "deep_link": {"page": "compliance"},
                    "evidence_status": "expired",
                }
            ],
            e360_next_actions=[
                w1.normalize_e360_next_action(
                    {
                        "id": "payroll:timesheet",
                        "severity": "high",
                        "module": "payroll",
                        "title": "Timesheet awaiting approval",
                        "reason": "open",
                        "target": {"page": "payroll"},
                    },
                    employee_key="WATHEFNI-96550252254",
                    employee_name="Talal",
                ),
                w1.normalize_e360_next_action(
                    {
                        "id": "onboarding:incomplete",
                        "severity": "medium",
                        "module": "onboarding",
                        "title": "Onboarding incomplete",
                        "reason": "open",
                        "target": {"page": "onboarding"},
                    },
                    employee_key="WATHEFNI-96550252254",
                    employee_name="Talal",
                ),
            ],
            apply_phase0_filters=True,
        )
        assert_true(soft["summary"]["total"] == 0, "empty subject allowlist soft-kills items")
        assert_true(soft["authority"]["exclude_payroll_stream"] is True, "payroll exclude on")

        os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = "96599338566"
        os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = "WATHEFNI-96550252254"
        assert_true(w1.viewer_is_allowlisted(phone="96599338566") is True, "Aziz allowlisted")
        assert_true(w1.viewer_is_allowlisted(phone="66363363") is False, "Fouad denied")
        assert_true(w1.allowlists_within_approved_boundary() is True, "approved boundary")

        live = w1.build_action_inbox(
            analytics_attention=[
                {
                    "id": "pending_leave",
                    "severity": "high",
                    "reason_en": "company leave",
                    "source_module": "leave",
                    "deep_link": {"page": "leave"},
                }
            ],
            compliance_findings=[
                {
                    "id": "talal",
                    "severity": "high",
                    "reason_en": "Talal residence",
                    "employee_key": "WATHEFNI-96550252254",
                    "document_type": "residence",
                    "document_type_canonical": "residence",
                    "deep_link": {"page": "compliance", "employee": "WATHEFNI-96550252254"},
                    "evidence_status": "expired",
                },
                {
                    "id": "other",
                    "severity": "high",
                    "reason_en": "Other residence",
                    "employee_key": "WATHEFNI-96566363363",
                    "document_type": "residence",
                    "document_type_canonical": "residence",
                    "deep_link": {"page": "compliance"},
                    "evidence_status": "expired",
                },
            ],
            e360_next_actions=[
                w1.normalize_e360_next_action(
                    {
                        "id": "payroll:timesheet",
                        "severity": "high",
                        "module": "payroll",
                        "title": "Timesheet awaiting approval",
                        "reason": "open",
                        "target": {"page": "payroll"},
                    },
                    employee_key="WATHEFNI-96550252254",
                    employee_name="Talal",
                ),
                w1.normalize_e360_next_action(
                    {
                        "id": "onboarding:incomplete",
                        "severity": "medium",
                        "module": "onboarding",
                        "title": "Onboarding incomplete",
                        "reason": "open",
                        "target": {"page": "onboarding"},
                    },
                    employee_key="WATHEFNI-96550252254",
                    employee_name="Talal",
                ),
            ],
            apply_phase0_filters=True,
        )
        keys = {str(i.get("employee_key") or "") for i in live["items"]}
        assert_true(keys == {"WATHEFNI-96550252254"}, keys)
        assert_true(all(not w1.is_payroll_inbox_item(i) for i in live["items"]), "no payroll rows")
        assert_true(all(i.get("deep_link", {}).get("page") != "payroll" for i in live["items"]), "no payroll deep links")
        # company-level analytics (no employee_key) dropped
        assert_true(all(i.get("source_stream") != "analytics" for i in live["items"]), "no unscoped analytics")

        os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = "96599338566,99999999999"
        assert_true(w1.allowlists_within_approved_boundary() is False, "widen attempt detected")
        assert_true("99999999999" not in w1.real_viewer_allowlist(), "unapproved phone stripped")
    finally:
        if prev_v is None:
            os.environ.pop("WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST", None)
        else:
            os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = prev_v
        if prev_s is None:
            os.environ.pop("WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST", None)
        else:
            os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = prev_s


def _missing_finding(
    *,
    employee_key: str,
    employee_name: str,
    doc: str,
    severity: str = "high",
) -> dict:
    return {
        "id": f"missing:{employee_key}:{doc}",
        "bucket": "missing",
        "severity": severity,
        "reason_en": f"{employee_name} missing {doc}",
        "reason_ar": f"{employee_name} ينقصه {doc}",
        "employee_key": employee_key,
        "employee_name": employee_name,
        "document_type": doc,
        "document_type_canonical": doc,
        "owner_role": "hr_compliance",
        "owner_label_en": "Company HR / Compliance",
        "system_of_action": "onboarding",
        "evidence_status": "missing",
        "deep_link": {"page": "onboarding", "employee": employee_key, "document_type": doc},
        "government_verified": False,
        "guidance_only": True,
    }


def test_same_employee_missing_docs_group_not_flood() -> None:
    """One employee with many missing docs must become one ranked case, not N cards."""
    talal = "WATHEFNI-96550252254"
    other = "WATHEFNI-96566363363"
    docs = ["civil_id", "passport", "residence", "work_permit", "driving_license"]
    findings = [_missing_finding(employee_key=talal, employee_name="Talal Fadhli", doc=d) for d in docs]
    findings.append(_missing_finding(employee_key=other, employee_name="Other Emp", doc="passport"))
    findings.append(
        {
            "id": f"expired:{talal}:residence",
            "bucket": "expired",
            "severity": "critical",
            "reason_en": "Talal Fadhli residence expired",
            "employee_key": talal,
            "employee_name": "Talal Fadhli",
            "document_type": "residence",
            "document_type_canonical": "residence",
            "owner_role": "hr_compliance",
            "system_of_action": "compliance",
            "evidence_status": "expired",
            "deadline": "2026-07-01",
            "deep_link": {"page": "compliance", "employee": talal, "document_type": "residence"},
            "government_verified": False,
            "guidance_only": True,
        }
    )

    # Before grouping semantics: normalize alone would be 7 rows; compose must collapse.
    pack = w1.build_action_inbox(
        compliance_findings=findings,
        apply_phase0_filters=False,
    )
    items = pack["items"]
    talal_items = [i for i in items if i.get("employee_key") == talal]
    other_items = [i for i in items if i.get("employee_key") == other]
    assert_true(len(items) == 3, f"expected 3 ranked cases (missing Talal, renewal Talal, missing Other), got {len(items)}")
    assert_true(len(talal_items) == 2, f"Talal must occupy 2 slots max (missing+renewal), got {len(talal_items)}")
    assert_true(len(other_items) == 1, "other employee must remain visible")
    missing = next(i for i in talal_items if i.get("grouped") or "missing" in str(i.get("what_en") or "").lower())
    assert_true(missing.get("grouped") is True, "missing docs must be grouped")
    assert_true(int(missing.get("grouped_count") or 0) == 5, missing.get("grouped_count"))
    assert_true("missing 5 required documents" in str(missing.get("what_en") or ""), missing.get("what_en"))
    assert_true(missing.get("deep_link", {}).get("document_type") in (None, ""), "group opens person context")
    assert_true(pack["summary"]["pre_group_total"] == 7, pack["summary"]["pre_group_total"])
    assert_true(pack["summary"]["grouped_compliance_cases"] == 1, pack["summary"])
    assert_true(pack["summary"]["grouped_collapsed_members"] == 5, pack["summary"])

    # Different destination/owner must stay separate even for same employee+bucket.
    split = w1.build_action_inbox(
        compliance_findings=[
            _missing_finding(employee_key=talal, employee_name="Talal Fadhli", doc="civil_id"),
            {
                **_missing_finding(employee_key=talal, employee_name="Talal Fadhli", doc="passport"),
                "owner_role": "line_manager",
                "owner_label_en": "Line manager",
            },
        ],
        apply_phase0_filters=False,
    )
    assert_true(len(split["items"]) == 2, "different owners must not merge")


def test_phase0_subject_allowlist_excludes_other_employees() -> None:
    """Other employees are hard-excluded by Phase 0 subject allowlist, not ranked below a limit."""
    prev_s = os.environ.get("WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST")
    try:
        os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = "WATHEFNI-96550252254"
        talal = "WATHEFNI-96550252254"
        other = "WATHEFNI-96566363363"
        pack = w1.build_action_inbox(
            compliance_findings=[
                *[_missing_finding(employee_key=talal, employee_name="Talal Fadhli", doc=d) for d in ("a", "b", "c")],
                _missing_finding(employee_key=other, employee_name="Other Emp", doc="passport"),
            ],
            apply_phase0_filters=True,
        )
        keys = {str(i.get("employee_key") or "") for i in pack["items"]}
        assert_true(keys == {talal}, keys)
        assert_true(len(pack["items"]) == 1, "Talal missing docs collapse to one case after Phase 0")
        assert_true(pack["summary"]["phase0_drops"]["dropped_subject"] >= 1, "other employee dropped by allowlist")
        assert_true(pack["items"][0].get("grouped_count") == 3, pack["items"][0])
        # No hard result-count cap — full ranked list after filters/grouping.
        assert_true("result_limit" not in pack.get("summary", {}), "no result limit field")
    finally:
        if prev_s is None:
            os.environ.pop("WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST", None)
        else:
            os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = prev_s


def test_sibling_freezes_not_weakened() -> None:
    import analytics_attention_wave1 as anw1
    import compliance_findings_wave1 as cfw1

    assert_true(anw1.honesty_payload().get("compliance_metrics") is False, "analytics excludes compliance")
    assert_true(cfw1.honesty_payload().get("legal_compliance_claims") is False, "compliance no legal claims")
    assert_true(w1.honesty_payload().get("payroll_money") is False, "inbox no payroll money")
    assert_true(w1.honesty_payload().get("attendance_ingest") is False, "no attendance ingest")
    assert_true(w1.honesty_payload().get("shifts_manager_expansion") is False, "no shifts manager expand")
    assert_true(w1.honesty_payload().get("compliance_wave2") is False, "no compliance wave2")
    assert_true(w1.honesty_payload().get("analytics_wave2") is False, "no analytics wave2")
    assert_true(w1.honesty_payload().get("phase0_viewer_allowlist_fail_closed") is True, "phase0 viewer")
    assert_true(w1.honesty_payload().get("phase0_subject_allowlist_fail_closed") is True, "phase0 subject")


def test_scope_isolation_wiring() -> None:
    import inspect
    import app

    src = inspect.getsource(app.dashboard_action_inbox_payload)
    assert_true("viewer_phone" in src and "actor_role" in src, "identity keys in inbox payload")
    assert_true("manager_scope_employee_keys" in inspect.getsource(app._inbox_e360_next_actions), "E360 scope filter")
    gate = inspect.getsource(app._action_inbox_gate)
    assert_true("action_inbox_viewer_denied" in gate, "viewer allowlist denial")
    assert_true("action_inbox_disabled" in gate, "wave kill switch denial")
    boot = inspect.getsource(app.dashboard_workspace_bootstrap)
    assert_true("action_inbox" in boot and "nav_offerable_for_viewer" in boot, "bootstrap nav gate")


def main() -> None:
    test_cross_source_ranking_and_shape()
    test_dedupe_and_clear_on_source_resolve()
    test_phase0_fail_closed_and_payroll_exclude()
    test_same_employee_missing_docs_group_not_flood()
    test_phase0_subject_allowlist_excludes_other_employees()
    test_sibling_freezes_not_weakened()
    test_scope_isolation_wiring()
    print("action-inbox-wave1 smoke tests passed")


if __name__ == "__main__":
    main()
