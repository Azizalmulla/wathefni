"""Wave 3C/3D unit tests (no DB)."""

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


def main() -> int:
    check("schema version wave3d", w3c.SCHEMA_VERSION.startswith("employees360-wave3d"))
    check("cancel_scheduled in cases", "cancel_scheduled" in w3c.CASE_TYPES)
    check("reinstate in cases", "reinstate" in w3c.CASE_TYPES)
    check("no self approval default", w3c.DEFAULT_POLICY["allow_self_approval"] is False)
    check("kuwait tz default", w3c.DEFAULT_POLICY["timezone"] == "Asia/Kuwait")
    check("warn first default", w3c.DEFAULT_POLICY["downstream_mode"] == "warn_first")
    check("notice hints hidden by default", w3c.DEFAULT_POLICY["show_notice_hints"] is False)
    check("reinstate disabled by default", w3c.DEFAULT_POLICY["allow_reinstate_after_effective"] is False)
    check("require LWD default", w3c.DEFAULT_POLICY["require_last_working_day"] is True)
    check("kuwait only jurisdiction", w3c.DEFAULT_POLICY["jurisdiction_mode"] == "kuwait_private_sector_only")
    check("retain documents default", w3c.DEFAULT_POLICY["document_retention_mode"] == "retain")
    check("no auto cancel shifts", w3c.DEFAULT_POLICY["auto_cancel_shifts"] is False)
    check("no auto decline leave", w3c.DEFAULT_POLICY["auto_decline_leave"] is False)
    check("payroll owns money", w3c.DEFAULT_POLICY["monetary_calculations_owner"] == "payroll")
    check("counsel questions 10", len(w3c.COUNSEL_QUESTIONS) == 10)

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
            "policy_json": {"wave": "wave3c", "disclaimer": "old"},
        }
    )
    check("normalize hides notice UI", hidden.get("notice_hints_ui") is None, hidden.get("notice_hints_ui"))
    check("normalize reinstate off", hidden.get("allow_reinstate_after_effective") is False)
    check("normalize show hints false", hidden.get("show_notice_hints") is False)

    shown = w3c._normalize_policy(
        {
            "company_code": "WATHEFNI",
            "timezone": "Asia/Kuwait",
            "notice_hint_monthly_days": 90,
            "notice_hint_other_days": 30,
            "policy_json": {"show_notice_hints": True, "wave": "wave3d"},
        }
    )
    check("normalize can expose labeled hints", isinstance(shown.get("notice_hints_ui"), dict), shown.get("notice_hints_ui"))
    check(
        "exposed hints labeled configurable",
        "Configurable policy guidance" in str((shown.get("notice_hints_ui") or {}).get("label") or ""),
        shown.get("notice_hints_ui"),
    )

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
