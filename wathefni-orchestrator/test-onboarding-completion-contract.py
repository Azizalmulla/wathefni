#!/usr/bin/env python3
"""Unit tests for the canonical onboarding completion contract (pure logic).

No DB required. Run: python3 test-onboarding-completion-contract.py
"""

from __future__ import annotations

import sys

import onboarding_completion_contract as C

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f"  {detail}" if not ok else ""))
    if not ok:
        FAILURES.append(name)


def item(item_id: str, status: str, **kw) -> dict:
    row = {"item_id": item_id, "status": status, "required": True, "owner": "employee"}
    row.update(kw)
    return row


# --- satisfaction semantics -------------------------------------------------
check("accepted satisfies", C.item_is_satisfied("accepted"))
check("waived satisfies", C.item_is_satisfied("waived"))
check("verified satisfies", C.item_is_satisfied("verified"))
check("not_applicable satisfies", C.item_is_satisfied("not_applicable"))
check("received does NOT satisfy (submitted != verified)", not C.item_is_satisfied("received"))
check("processing does NOT satisfy", not C.item_is_satisfied("processing"))
check("replacement_required does NOT satisfy", not C.item_is_satisfied("replacement_required"))
check("pending does NOT satisfy", not C.item_is_satisfied("pending"))

# --- item classification ---------------------------------------------------
check(
    "processing → waiting_hr",
    C.classify_item(item("civil_id", "processing")) == C.ITEM_WAITING_HR,
)
check(
    "received (legacy) → waiting_hr not complete",
    C.classify_item(item("civil_id", "received")) == C.ITEM_WAITING_HR,
)
check(
    "replacement_required → waiting_employee",
    C.classify_item(item("civil_id", "replacement_required")) == C.ITEM_WAITING_EMPLOYEE,
)
check(
    "hr-owned pending → waiting_hr",
    C.classify_item(item("salary_transfer_details", "pending", owner="hr")) == C.ITEM_WAITING_HR,
)
check(
    "blocked_by → blocked",
    C.classify_item(item("residence", "pending", blocked_by=["civil_id"])) == C.ITEM_BLOCKED,
)
check(
    "lifecycle_meta not_applicable → satisfied_not_applicable",
    C.classify_item(item("work_permit", "pending", lifecycle_meta={"not_applicable": True}))
    == C.ITEM_SATISFIED_NOT_APPLICABLE,
)
check(
    "not_applicable item is not required",
    not C.item_is_required(item("work_permit", "pending", lifecycle_meta={"not_applicable": True})),
)

# --- employee-level states -------------------------------------------------
snap = C.compute_completion([item("civil_id", "pending"), item("photo", "pending")])
check("new employee no progress → not_started", snap["state"] == C.STATE_NOT_STARTED, snap["state"])
check("not_started is not complete", snap["is_complete"] is False)

snap = C.compute_completion([item("civil_id", "processing"), item("photo", "pending")])
check(
    "partial: employee still owes → waiting_on_employee",
    snap["state"] == C.STATE_WAITING_ON_EMPLOYEE,
    snap["state"],
)

snap = C.compute_completion([item("civil_id", "processing"), item("photo", "submitted")])
check("all submitted → waiting_on_hr", snap["state"] == C.STATE_WAITING_ON_HR, snap["state"])

snap = C.compute_completion([item("civil_id", "replacement_required"), item("photo", "accepted")])
check(
    "rejected item → waiting_on_employee",
    snap["state"] == C.STATE_WAITING_ON_EMPLOYEE,
    snap["state"],
)

snap = C.compute_completion([item("civil_id", "accepted"), item("photo", "waived")])
check("accepted + waived → completed", snap["state"] == C.STATE_COMPLETED, snap["state"])
check("completed is_complete", snap["is_complete"] is True)
check("completed legacy mirror", snap["legacy_onboarding_status"] == "completed")
check("completed has zero pending", snap["documents_pending"] == 0)

snap = C.compute_completion(
    [item("civil_id", "accepted"), item("work_permit", "pending", lifecycle_meta={"not_applicable": True})]
)
check("not_applicable does not block completion", snap["state"] == C.STATE_COMPLETED, snap["state"])

snap = C.compute_completion([item("photo", "accepted"), item("bank_details", "pending", required=False)])
check("optional item does not block completion", snap["state"] == C.STATE_COMPLETED, snap["state"])

snap = C.compute_completion(
    [item("civil_id", "pending", blocked_by=["contract"]), item("contract", "accepted")]
)
check("all open blocked → blocked", snap["state"] == C.STATE_BLOCKED, snap["state"])

snap = C.compute_completion(
    [
        item("civil_id", "pending", blocked_by=["contract"]),
        item("photo", "pending"),
        item("contract", "accepted"),
    ]
)
check(
    "blocked + actionable → waiting_on_employee (not blocked)",
    snap["state"] == C.STATE_WAITING_ON_EMPLOYEE,
    snap["state"],
)

snap = C.compute_completion(
    [item("civil_id", "pending", blocked_by=["contract"]), item("photo", "pending")]
)
check(
    "no progress outranks blocked/waiting → not_started",
    snap["state"] == C.STATE_NOT_STARTED,
    snap["state"],
)

snap = C.compute_completion([item("civil_id", "replacement_required")], previously_completed=True)
check("reopen after completion → reopened", snap["state"] == C.STATE_REOPENED, snap["state"])
check("reopened is not complete", snap["is_complete"] is False)

snap = C.compute_completion([item("civil_id", "accepted")], previously_completed=True)
check("recompleted after reopen → completed", snap["state"] == C.STATE_COMPLETED, snap["state"])

snap = C.compute_completion(
    [item("civil_id", "pending")], assignment_status="cancelled"
)
check("cancelled assignment → blocked", snap["state"] == C.STATE_BLOCKED, snap["state"])

# HR launching onboarding is itself progress: the process is underway even with
# nothing submitted, so the employee owes the first action.
snap = C.compute_completion(
    [item("civil_id", "pending"), item("photo", "pending")],
    assignment_status="in_progress",
)
check(
    "launched assignment, no submissions → waiting_on_employee",
    snap["state"] == C.STATE_WAITING_ON_EMPLOYEE,
    snap["state"],
)
snap = C.compute_completion(
    [item("civil_id", "pending")], assignment_status="not_started"
)
check(
    "unlaunched assignment, no submissions → not_started",
    snap["state"] == C.STATE_NOT_STARTED,
    snap["state"],
)

snap = C.compute_completion([])
check("no items → not_started (never completed)", snap["state"] == C.STATE_NOT_STARTED, snap["state"])
check("no items is not complete", snap["is_complete"] is False)

# Requirement added after completion.
after = C.compute_completion(
    [item("civil_id", "accepted"), item("new_policy", "pending")], previously_completed=True
)
check(
    "requirement added after completion → reopened",
    after["state"] == C.STATE_REOPENED,
    after["state"],
)

# Requirement removed after progress.
removed = C.compute_completion([item("civil_id", "accepted")])
check("requirement removed → completed", removed["state"] == C.STATE_COMPLETED, removed["state"])

# --- next action: no dead ends ---------------------------------------------
for state in C.COMPLETION_STATES:
    na = C.next_action({"state": state})
    check(f"next_action defined for {state}", bool(na.get("message")) and bool(na.get("owner")))
    na_ar = C.next_action({"state": state}, locale="ar")
    check(f"next_action arabic for {state}", na_ar["message"] == na_ar["message_ar"])
    check(f"next_action arabic non-empty for {state}", bool(na_ar["message_ar"].strip()))

# --- reminders: dedup + covers correction states ---------------------------
snap = C.compute_completion([item("civil_id", "replacement_required"), item("photo", "accepted")])
r1 = C.reminder_targets(snap)
check("reminder targets employee on correction", r1["party"] == "employee", r1)
check("reminder includes rejected item", "civil_id" in r1["items"], r1)
r2 = C.reminder_targets(C.compute_completion([item("photo", "accepted"), item("civil_id", "replacement_required")]))
check("reminder dedup key stable regardless of item order", r1["dedup_key"] == r2["dedup_key"], (r1, r2))

snap_hr = C.compute_completion([item("civil_id", "processing")])
check("reminder targets hr when awaiting review", C.reminder_targets(snap_hr)["party"] == "hr")

snap_done = C.compute_completion([item("civil_id", "accepted")])
check("no reminder when complete", C.reminder_targets(snap_done)["party"] == "none")

# --- SQL predicate parity --------------------------------------------------
sql = C.sql_satisfied_list()
check("sql satisfied includes accepted", "'accepted'" in sql, sql)
check("sql satisfied excludes received", "'received'" not in sql, sql)
check("sql closed includes blocked terminals", "'abandoned_employment_ended'" in C.sql_closed_list())
check("sql employee action includes replacement_required", "'replacement_required'" in C.sql_employee_action_list())
check(
    "python and SQL satisfaction agree",
    all(C.item_is_satisfied(s) for s in C.SATISFIED_STATUSES)
    and not any(C.item_is_satisfied(s) for s in C.HR_REVIEW_STATUSES),
)

# --- idempotency of pure computation --------------------------------------
rows = [item("civil_id", "accepted"), item("photo", "processing")]
a = C.compute_completion(rows)
b = C.compute_completion(rows)
check("compute_completion deterministic", a == b)

print()
if FAILURES:
    print(f"FAILED {len(FAILURES)}: {FAILURES}")
    sys.exit(1)
print("ALL PASS")
