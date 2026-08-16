"""Wave 2 authority — pure unit tests (no DB)."""

from __future__ import annotations

import employee_authority_wave2 as w2
from employee_hygiene_wave1c import mint_person_id

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
    for key, approved in w2.APPROVED_WATHEFNI_MAP.items():
        phone = approved["person_seed"].split(":")[-1]
        emp = {"company_code": "WATHEFNI", "employee_key": key, "phone": phone}
        ids = w2.resolve_ids_for_employee(emp)
        check(f"map person {key}", ids["person_id"] == approved["person_id"], ids)
        check(f"map employment {key}", ids["employment_id"] == approved["employment_id"], ids)
        check(f"map assignment {key}", ids["assignment_id"] == approved["assignment_id"], ids)
        pid, seed = mint_person_id(company_code="WATHEFNI", phone=phone)
        check(f"seed stable {key}", seed == approved["person_seed"] and pid == approved["person_id"])

    # Seed mismatch must fail closed
    try:
        w2.resolve_ids_for_employee(
            {"company_code": "WATHEFNI", "employee_key": "WATHEFNI-96550252254", "phone": "96500000000"}
        )
        check("seed mismatch fail-closed", False)
    except ValueError:
        check("seed mismatch fail-closed", True)

    # Non-map employee still deterministic
    a = w2.resolve_ids_for_employee({"company_code": "ACME", "employee_key": "ACME-96551112222", "phone": "96551112222"})
    b = w2.resolve_ids_for_employee({"company_code": "ACME", "employee_key": "ACME-96551112222", "phone": "96551112222"})
    check("non-map deterministic", a == b)
    check("tenant isolation in person seed", "ACME" in a["person_seed"])

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
