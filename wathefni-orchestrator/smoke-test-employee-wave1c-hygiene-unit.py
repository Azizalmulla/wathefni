"""Wave 1C hygiene — pure unit tests (no DB)."""

from __future__ import annotations

import employee_hygiene_wave1c as h

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
    # Classifier: refuse guess
    empty = h.classify_null_status_from_evidence({"employee": {"employment_status": None}})
    check("refuse guess without evidence", empty["classification"] == "needs_manual_review" and empty["proposed_status"] is None)

    hired = h.classify_null_status_from_evidence(
        {
            "employee": {"employment_status": None, "app_key": "x", "onboarding_status": "in_progress"},
            "applications": [{"status": "hired"}],
            "attendance_records": {"count": 2},
            "shift_assignments": {"count": 1},
            "leave_requests": {"count": 0},
            "employee_messages": {"count": 1},
            "employee_status_changes": {"count": 0},
        }
    )
    check("hired+activity → active high", hired["classification"] == "null_should_be_active" and hired["proposed_status"] == "active" and hired["confidence"] == "high")

    leftish = h.classify_null_status_from_evidence(
        {
            "employee": {"employment_status": None, "app_key": "x"},
            "applications": [{"status": "rejected"}],
            "attendance_records": {"count": 0},
            "shift_assignments": {"count": 0},
            "leave_requests": {"count": 0},
            "employee_messages": {"count": 0},
            "employee_status_changes": {"count": 0},
        }
    )
    check("rejected app → manual review", leftish["classification"] == "needs_manual_review")

    # Synthetic key detection
    check("P0-DUP synthetic", h.is_synthetic_employee_key("WATHEFNI-P0-DUP-1"))
    check("real key not synthetic", not h.is_synthetic_employee_key("WATHEFNI-96597727743"))

    # Deterministic map
    row = h.build_migration_readiness_row(
        {"company_code": "WATHEFNI", "employee_key": "WATHEFNI-96597727743", "phone": "96597727743", "email": None, "employment_status": None}
    )
    row2 = h.build_migration_readiness_row(
        {"company_code": "WATHEFNI", "employee_key": "WATHEFNI-96597727743", "phone": "96597727743", "email": None, "employment_status": None}
    )
    check("person_id deterministic", row["person_id"] == row2["person_id"])
    check("employment_id deterministic", row["employment_id"] == row2["employment_id"])
    check("assignment_id present", bool(row["assignments"][0]["assignment_id"]))

    # Different phones → different persons
    other = h.build_migration_readiness_row(
        {"company_code": "WATHEFNI", "employee_key": "WATHEFNI-96550252254", "phone": "96550252254"}
    )
    check("distinct phones distinct persons", row["person_id"] != other["person_id"])

    m = h.build_migration_readiness_map(
        [
            {"company_code": "WATHEFNI", "employee_key": "WATHEFNI-96597727743", "phone": "96597727743"},
            {"company_code": "WATHEFNI", "employee_key": "WATHEFNI-96550252254", "phone": "96550252254"},
        ],
        synthetic_orphan_keys=["WATHEFNI-P0-DUP-1"],
    )
    check("map excludes orphan mint", m["synthetic_orphans_excluded_from_person_mint"][0]["person_id"] is None)
    check("map count", m["employee_count"] == 2)

    # Match production audit uuid5 for known phone (from audit extract)
    # Recompute expected from seed
    pid, seed = h.mint_person_id(company_code="WATHEFNI", phone="96597727743")
    check("seed format", seed == "person:WATHEFNI:phone:96597727743")
    check("prod map person matches mint", pid == row["person_id"])

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
