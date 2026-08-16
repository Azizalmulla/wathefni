"""Wave 3 lifecycle — pure unit tests (no DB)."""

from __future__ import annotations

import os

import employee_lifecycle_wave3 as w3

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
    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES"] = "WATHEFNI"
    os.environ["WATHEFNI_EMPLOYEE_LIFECYCLE_V3"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES"] = "WATHEFNI"

    check("enabled WATHEFNI", w3.lifecycle_v3_enabled("WATHEFNI") is True)
    check("disabled OTHERCO", w3.lifecycle_v3_enabled("OTHERCO") is False)

    os.environ["WATHEFNI_EMPLOYEE_LIFECYCLE_V3"] = "off"
    check("flag off", w3.lifecycle_v3_enabled("WATHEFNI") is False)
    os.environ["WATHEFNI_EMPLOYEE_LIFECYCLE_V3"] = "on"

    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2"] = "off"
    check("requires wave2", w3.lifecycle_v3_enabled("WATHEFNI") is False)
    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2"] = "on"

    check("hub terminated→left", w3.hub_status_for_lifecycle("terminated") == "left")
    check("hub active→active", w3.hub_status_for_lifecycle("active") == "active")
    check("hub notice→active", w3.hub_status_for_lifecycle("notice_period") == "active")
    check("hub suspended→active", w3.hub_status_for_lifecycle("suspended") == "active")
    check("hub pending→active", w3.hub_status_for_lifecycle("pending_start") == "active")

    for st in ("pending_start", "active", "notice_period", "suspended", "terminated"):
        check(f"state known {st}", st in w3.LIFECYCLE_STATES)

    for t in ("resignation", "dismissal", "end_of_contract", "mutual", "other"):
        check(f"term type {t}", t in w3.TERMINATION_TYPES)

    h1 = w3._request_hash({"a": 1, "b": 2})
    h2 = w3._request_hash({"b": 2, "a": 1})
    h3 = w3._request_hash({"a": 1, "b": 3})
    check("hash stable order", h1 == h2)
    check("hash differs on change", h1 != h3)
    check("schema version", w3.SCHEMA_VERSION == "employees360-wave3-lifecycle-v1")

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
