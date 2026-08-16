#!/usr/bin/env python3
"""Wave 1 — Probation authority unit smoke (no DB)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    print("    probation wave1 — SM + template + flags")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import probation as pr

    check("schema version", pr.PROBATION_SCHEMA_VERSION == "1.0.0")
    check("sql pack exists", pr._SCHEMA.is_file())

    check("active→under_review", pr.can_transition_case("active", "under_review"))
    check("under_review→confirmed", pr.can_transition_case("under_review", "confirmed"))
    check("under_review→extended", pr.can_transition_case("under_review", "extended"))
    check("under_review→failed", pr.can_transition_case("under_review", "failed"))
    check("confirmed terminal", not pr.can_transition_case("confirmed", "active"))
    check("failed terminal", not pr.can_transition_case("failed", "under_review"))
    check("milestone pending→completed", pr.can_transition_milestone("pending", "completed"))
    check("milestone pending→overdue", pr.can_transition_milestone("pending", "overdue"))
    check("milestone completed terminal", not pr.can_transition_milestone("completed", "pending"))

    ms = pr.default_kuwait_milestones()
    keys = {m["milestone_key"] for m in ms}
    check("30/60/90 keys", keys == {"day_30", "day_60", "day_90"}, keys)
    check("offsets 30/60/90", [m["offset_days"] for m in ms] == [30, 60, 90])

    os.environ.pop("WATHEFNI_PROBATION", None)
    check("runtime off default", pr.probation_runtime_flag_on() is False)
    os.environ["WATHEFNI_PROBATION"] = "on"
    os.environ["WATHEFNI_PROBATION_COMPANIES"] = "CANARY"
    check("allowlist present", "CANARY" in pr.probation_company_allowlist())

    app_src = (orch / "app.py").read_text(encoding="utf-8")
    check("app ensure_probation_schema hook", "ensure_probation_schema" in app_src)
    bridge = (orch / "hire_ready_bridge.py").read_text(encoding="utf-8")
    check("hire bridge soft probation hook", "maybe_create_case_on_hire" in bridge)
    check("rollback guidance", "WATHEFNI_PROBATION=off" in str(pr.rollback_guidance()))
    check("no UI claim", "No Probation UI" in str(pr.rollback_guidance().get("note")))

    os.environ["WATHEFNI_PROBATION"] = "off"
    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PROBATION_WAVE1_UNIT_FULL_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
