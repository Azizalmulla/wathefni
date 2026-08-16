#!/usr/bin/env python3
"""Phase A slice 2 — task ontology + SLA unit smoke."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
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
    print("    workflow_task_sla phase A slice 2 — ontology + SLA unit")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))
    import workflow_task_sla as wts

    check("schema version", wts.WORKFLOW_TASK_SLA_SCHEMA_VERSION == "1.0.0")
    check("sql pack exists", wts._SCHEMA_SQL_PATH.is_file())
    for tt in wts.CANONICAL_TASK_TYPES:
        check(f"canonical type {tt}", wts.is_canonical_task_type(tt))
    check("unknown type rejected", not wts.is_canonical_task_type("random_task"))

    check(
        "clock running→breached",
        wts.can_transition(wts.CLOCK_TRANSITIONS, "running", "breached"),
    )
    check(
        "clock breached terminal",
        not wts.can_transition(wts.CLOCK_TRANSITIONS, "breached", "running"),
    )
    check(
        "clock running→satisfied",
        wts.can_transition(wts.CLOCK_TRANSITIONS, "running", "satisfied"),
    )
    check(
        "clock breached→satisfied allowed",
        wts.can_transition(wts.CLOCK_TRANSITIONS, "breached", "satisfied"),
    )
    check(
        "clock breached→cancelled allowed",
        wts.can_transition(wts.CLOCK_TRANSITIONS, "breached", "cancelled"),
    )
    naive = datetime(2026, 8, 11, 12, 0, 0)
    aware = wts.ensure_utc(naive)
    check("naive due_at coerced to UTC", aware is not None and aware.tzinfo == timezone.utc)
    check(
        "invariants documented in rollback guidance",
        any("One open hr_task" in s for s in wts.rollback_guidance().get("invariants", [])),
    )

    prev_t = os.environ.pop("WATHEFNI_WORKFLOW_TASKS", None)
    prev_s = os.environ.pop("WATHEFNI_WORKFLOW_SLA", None)
    try:
        check("tasks flag default off", wts.workflow_tasks_runtime_flag_on() is False)
        check("sla flag default off", wts.workflow_sla_runtime_flag_on() is False)
        os.environ["WATHEFNI_WORKFLOW_TASKS"] = "on"
        os.environ["WATHEFNI_WORKFLOW_SLA"] = "on"
        os.environ["WATHEFNI_WORKFLOW_TASKS_COMPANIES"] = "AAA,BBB"
        os.environ["WATHEFNI_WORKFLOW_SLA_COMPANIES"] = "AAA"
        check("tasks allowlist", wts.workflow_tasks_company_allowlist() == {"AAA", "BBB"})
        check("sla allowlist", wts.workflow_sla_company_allowlist() == {"AAA"})
    finally:
        for k, v in (
            ("WATHEFNI_WORKFLOW_TASKS", prev_t),
            ("WATHEFNI_WORKFLOW_SLA", prev_s),
        ):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.environ.pop("WATHEFNI_WORKFLOW_TASKS_COMPANIES", None)
        os.environ.pop("WATHEFNI_WORKFLOW_SLA_COMPANIES", None)

    rb = wts.rollback_guidance()
    check("rollback modularity note", "modularity" in rb)
    check("rollback retains tables", any("Retain" in s for s in rb.get("data", [])))

    # modularity: SLA may run without breach task if tasks off — documented
    check(
        "modularity: SLA independent of tasks for clocks",
        any("without tasks" in s.lower() for s in rb.get("modularity", [])),
    )

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
