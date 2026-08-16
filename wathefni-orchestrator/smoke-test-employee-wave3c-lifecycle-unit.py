"""Wave 3C/3D/3F unit tests (no DB)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import employee_lifecycle_wave3c as w3c

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


class _FakeHTTP(Exception):
    def __init__(self, status_code: int, detail):
        self.status_code = status_code
        self.detail = detail


class _FakeLegacy:
    HTTPException = _FakeHTTP


def main() -> int:
    check("schema version wave3h", w3c.SCHEMA_VERSION.startswith("employees360-wave3h"), w3c.SCHEMA_VERSION)
    check("cancel_scheduled in cases", "cancel_scheduled" in w3c.CASE_TYPES)
    check("reinstate in cases", "reinstate" in w3c.CASE_TYPES)
    check("no self approval default", w3c.DEFAULT_POLICY["allow_self_approval"] is False)
    check("kuwait tz default", w3c.DEFAULT_POLICY["timezone"] == "Asia/Kuwait")
    check("warn first default", w3c.DEFAULT_POLICY["downstream_mode"] == "warn_first")
    check("notice hints hidden by default", w3c.DEFAULT_POLICY["show_notice_hints"] is False)
    check("reinstate disabled by default", w3c.DEFAULT_POLICY["allow_reinstate_after_effective"] is False)
    check("require LWD default", w3c.DEFAULT_POLICY["require_last_working_day"] is True)
    check("require classification default", w3c.DEFAULT_POLICY["require_employment_classification"] is True)
    check("require case class default", w3c.DEFAULT_POLICY["require_termination_case_class"] is True)
    check("kuwait pack jurisdiction mode", w3c.DEFAULT_POLICY["jurisdiction_mode"] == "policy_pack")
    check("retain documents default", w3c.DEFAULT_POLICY["document_retention_mode"] == "retain")
    check("retention floor 365", w3c.DEFAULT_POLICY["document_retention_floor_days"] == 365)
    check("no auto cancel shifts", w3c.DEFAULT_POLICY["auto_cancel_shifts"] is False)
    check("no auto decline leave", w3c.DEFAULT_POLICY["auto_decline_leave"] is False)
    check("payroll owns money", w3c.DEFAULT_POLICY["monetary_calculations_owner"] == "payroll")
    check("counsel gate off for normal ops", w3c.DEFAULT_POLICY["require_counsel_gate"] is False)
    check("service certificate default", w3c.DEFAULT_POLICY["service_certificate_default"] is True)
    check("public-law questions 10", len(w3c.COUNSEL_QUESTIONS) == 10)
    check("PL1 present", w3c.COUNSEL_QUESTIONS[0]["id"] == "PL1")
    check("contract types vocab", "unlimited" in w3c.CONTRACT_TYPES and "fixed_term" in w3c.CONTRACT_TYPES)
    check("exceptional classes include 41a", "summary_dismissal_41a" in w3c.EXCEPTIONAL_CASE_CLASSES)

    import employee_lifecycle_wave3 as w3

    os_env = __import__("os").environ
    prev = os_env.get("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY")
    os_env["WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY"] = "on"
    try:
        check("synth phone prefix match", w3.is_lifecycle_synthetic_employee_row(phone="96552212345", name="X"))
        check("real phone blocked pattern", not w3.is_lifecycle_synthetic_employee_row(phone="96550252254", name="Talal Fadhli"))
        check("synth name prefix match", w3.is_lifecycle_synthetic_employee_row(phone="96599999999", name="W3D-SYNTH|Canary"))
        check("synthetic only flag on", w3.lifecycle_synthetic_only_enabled() is True)
    finally:
        if prev is None:
            os_env.pop("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY", None)
        else:
            os_env["WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY"] = prev

    policy = dict(w3c.DEFAULT_POLICY)
    eff = date(2026, 8, 10)
    lwd = date(2026, 8, 9)
    revoke_at = w3c.compute_access_revoke_at(policy=policy, termination_effective_on=eff, last_working_day=lwd)
    check("revoke at end of LWD", revoke_at == datetime(2026, 8, 9, 23, 59, 59, tzinfo=ZoneInfo("Asia/Kuwait")), revoke_at)

    policy2 = {**policy, "revoke_mode": "start_of_effective_date"}
    revoke2 = w3c.compute_access_revoke_at(policy=policy2, termination_effective_on=eff, last_working_day=lwd)
    check("alt revoke at effective 00:00", revoke2 == datetime(2026, 8, 10, 0, 0, 0, tzinfo=ZoneInfo("Asia/Kuwait")), revoke2)

    h1 = w3c._impact_hash({"as_of_date": "2026-08-01", "employee_key": "X", "domains": {"a": 1}, "snapshot_id": "1"})
    h2 = w3c._impact_hash({"domains": {"a": 1}, "employee_key": "X", "as_of_date": "2026-08-01", "snapshot_id": "1"})
    check("impact hash stable", h1 == h2)

    hidden = w3c._normalize_policy(
        {
            "company_code": "WATHEFNI",
            "timezone": "Asia/Kuwait",
            "notice_hint_monthly_days": 90,
            "notice_hint_other_days": 30,
            "require_counsel_gate": True,
            "policy_json": {"wave": "wave3d", "disclaimer": "old"},
        }
    )
    check("normalize hides notice UI", hidden.get("notice_hints_ui") is None, hidden.get("notice_hints_ui"))
    check("normalize reinstate off", hidden.get("allow_reinstate_after_effective") is False)
    check("normalize show hints false", hidden.get("show_notice_hints") is False)
    check("normalize migrates wave3h", (hidden.get("policy_json") or {}).get("wave") == "wave3h", hidden.get("policy_json"))
    check("normalize counsel gate off on migrate", hidden.get("require_counsel_gate") is False, hidden.get("require_counsel_gate"))

    shown = w3c._normalize_policy(
        {
            "company_code": "WATHEFNI",
            "timezone": "Asia/Kuwait",
            "notice_hint_monthly_days": 90,
            "notice_hint_other_days": 30,
            "policy_json": {"show_notice_hints": True, "wave": "wave3f"},
        }
    )
    check("normalize can expose labeled hints", isinstance(shown.get("notice_hints_ui"), dict), shown.get("notice_hints_ui"))
    check(
        "exposed hints labeled guidance",
        "guidance" in str((shown.get("notice_hints_ui") or {}).get("label") or "").lower(),
        shown.get("notice_hints_ui"),
    )

    legacy = _FakeLegacy()
    ok = w3c._assert_termination_classification(
        legacy,
        policy=policy,
        payload={
            "contract_type": "unlimited",
            "pay_frequency": "monthly",
            "probation_status": "completed",
            "termination_case_class": "resignation",
        },
    )
    check("classification ok unlimited", ok.get("ok") is True and ok["notice"]["eligible"] is False, ok)
    # eligible only when show_notice_hints true
    pol_hints = {**policy, "show_notice_hints": True}
    ok2 = w3c._assert_termination_classification(
        legacy,
        policy=pol_hints,
        payload={
            "contract_type": "unlimited",
            "pay_frequency": "monthly",
            "probation_status": "completed",
            "termination_case_class": "resignation",
        },
    )
    check("notice eligible when hints on + unlimited", ok2["notice"]["eligible"] is True and ok2["notice"]["hint_days"] == 90, ok2)

    try:
        w3c._assert_termination_classification(legacy, policy=policy, payload={"termination_case_class": "resignation"})
        check("missing classification fails closed", False)
    except _FakeHTTP as exc:
        check(
            "missing classification fails closed",
            exc.status_code == 422 and (exc.detail or {}).get("error") == "manual_review_missing_classification",
            exc.detail,
        )

    try:
        w3c._assert_termination_classification(
            legacy,
            policy=policy,
            payload={
                "contract_type": "unlimited",
                "pay_frequency": "monthly",
                "probation_status": "completed",
                "termination_case_class": "summary_dismissal_41a",
            },
        )
        check("exceptional requires escalation note", False)
    except _FakeHTTP as exc:
        check(
            "exceptional requires escalation note",
            (exc.detail or {}).get("error") == "exceptional_case_manual_escalation_required",
            exc.detail,
        )

    notice_blocked = w3c.notice_guidance_eligibility(
        policy=pol_hints,
        contract_type="fixed_term",
        pay_frequency="monthly",
        probation_status="completed",
        termination_case_class="end_of_fixed_term",
    )
    check("notice hidden for fixed_term", notice_blocked["eligible"] is False and "contract_not_unlimited" in notice_blocked["block_reasons"])

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
