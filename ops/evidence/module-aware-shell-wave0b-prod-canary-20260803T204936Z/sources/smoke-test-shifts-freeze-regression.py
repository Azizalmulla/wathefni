#!/usr/bin/env python3
"""Shifts freeze regression — hard gates for every future Shifts / post-hire PR.

Fails if canonical L0 authority, published-version immutability, lifecycle/leave gates,
self-decision bans, manager scope, concurrency/idempotency, overnight/split semantics,
template regeneration safety, notification dedupe/tenant isolation, the controlled real
allowlists, the notify kill switch, the subject exclusions, the no-money boundaries, or
the frozen sibling modules weaken.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OPS = ROOT.parent / "ops"
if not OPS.exists():
    OPS = Path("/opt/wathefni/ops")
RESULTS: list[tuple[str, bool, object]] = []


def check(name: str, ok: bool, detail: object = None) -> None:
    RESULTS.append((name, bool(ok), detail if not ok else None))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" :: {detail}" if not ok and detail is not None else ""))


def read(name: str) -> str:
    p = ROOT / name
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def main() -> int:
    freeze_candidates = [
        OPS / "SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        Path("/opt/wathefni/ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md"),
        Path("/Users/azizalmulla/Desktop/claw/ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md"),
    ]
    freeze = next((p for p in freeze_candidates if p.is_file()), None)
    check("shifts freeze doc present", freeze is not None, str(freeze_candidates[0]))
    if freeze is not None:
        txt = freeze.read_text(encoding="utf-8")
        for needle in (
            "NO-GO",
            "HR_ALLOWLIST",
            "MANAGER_ALLOWLIST",
            "NOTIFY_REAL_ALLOWLIST",
            "NOTIFY_KILL",
            "EXCLUDED_SUBJECTS",
            "SYNTHETIC_ONLY",
            "manual_submission_required",
            "Payroll",
            "Leave",
            "Attendance",
            "Employees 360",
            "Onboarding",
            "published",
            "self",
        ):
            check(f"freeze doc mentions {needle}", needle.lower() in txt.lower(), needle)

    w1 = read("shifts_authority_wave1.py")
    w2 = read("shifts_schedule_integrity_wave2.py")
    w3 = read("shifts_wave3_controlled.py")
    w4 = read("shifts_templates_wave4.py")
    w5 = read("shifts_publish_wave5.py")
    w6 = read("shifts_enterprise_wave6.py")
    n6 = read("shifts_notifications_wave6b.py")
    w6c = read("shifts_controlled_wave6c.py")
    cleanup = read("shifts_synthetic_cleanup.py")
    appsrc = read("app.py")

    for name, src in (
        ("wave1", w1), ("wave2", w2), ("wave3", w3), ("wave4", w4),
        ("wave5", w5), ("wave6", w6), ("notifications", n6), ("wave6c", w6c),
    ):
        check(f"{name} module present", bool(src.strip()))

    # canonical L0 authority + published immutability
    check("L0 authority helpers present", "shift_assignments" in w5 and "schedule_version" in w5)
    check("published version immutability guarded", "published" in w5 and ("immutab" in w5.lower() or "already_published" in w5))

    # lifecycle / leave gates
    check("lifecycle gate present", "block_terminated" in w1 or "lifecycle" in w1)
    check("leave conflict mode present", "leave_conflict_mode" in w1)

    # self-decision bans and manager scope
    check("manager scope enforced in app", "manager_scope_allows_employee" in appsrc)
    check("out of scope denial", "employee_outside_manager_scope" in appsrc)
    check("self decision banned in matrix", '"self_decision": False' in w3 or "'self_decision': False" in w3)
    check("wave6c manager self decision banned", '"self_decision": False' in w6c)

    # concurrency / idempotency
    check("expected_updated_at concurrency token", "expected_updated_at" in appsrc)
    check("idempotency key honored", "idempotency_key" in appsrc)

    # overnight / split semantics
    check("overnight allowed flag", "WATHEFNI_SHIFTS_ALLOW_OVERNIGHT" in w1)
    check("ends_next_day semantics", "ends_next_day" in appsrc)

    # template regeneration safety
    check("regen detach safety", "regen_detached" in w4 or "regen_detached" in appsrc)

    # notification dedupe / tenant isolation / ack once
    check("notification dedupe unique", "dedupe_key" in n6)
    check("notification tenant isolation", "tenant_isolation_violation" in n6)
    check("ack recorded once", "already_acked" in n6)
    check("drafts do not notify", "drafts_do_not_notify" in n6)

    # Wave 6C controlled real rollout guards
    check("real notify allowlist fail closed", "real_notify_allowlist_empty" in w6c)
    check("recipient allowlist enforced", "recipient_not_allowlisted" in w6c)
    check("channel allowlist enforced", "channel_not_approved" in w6c)
    check("consent required for external channels", "consent_missing" in w6c)
    check("notify kill switch", "WATHEFNI_SHIFTS_NOTIFY_KILL" in w6c and "notify_kill_switch_active" in w6c)
    check("real delivery fail closed", "def real_delivery_enabled" in w6c and "default=False" in w6c)
    check("subject exclusions enforced", "subject_excluded" in w6c and "WATHEFNI-ORPHAN-" in w6c)
    check("manager real rollout hard no", "def manager_real_rollout_enabled" in w6c and "return False" in w6c)
    check("operator timers default off", "WATHEFNI_SHIFTS_OPERATOR_TIMERS" in w6c)
    check("job advisory lock", "pg_try_advisory_lock" in w6c)
    check("job batch bounded", "min(500" in w6c)
    check("job no overlap status", "skipped_locked" in w6c)
    check("freeze invariants exposed", "def freeze_invariants" in w6c)
    check("approved hr operators pinned", 'APPROVED_HR_OPERATORS = frozenset({"96599338566"})' in w6c)
    check("allowlist boundary helper", "def allowlists_within_approved_boundary" in w6c)
    check("authority boundary helper", "def authority_scope_within_approved_boundary" in w6c)
    for wave, src in (("wave1b", read("canary-prod-shifts-wave1b.py")),):
        check(f"{wave} asserts authority boundary", "authority_scope_within_approved_boundary" in src)
    for wave in ("wave3b", "wave4b", "wave5b", "wave6b"):
        src = read(f"canary-prod-shifts-{wave}.py")
        check(f"{wave} asserts allowlist boundary", "allowlists_within_approved_boundary" in src)

    # real mutation gate
    check("real mutation gate present", "def real_mutation_denied" in w3)
    check("real mutation denial code", "shifts_real_mutation_not_allowlisted" in w3)
    check("audit reason required", "audit_reason_required" in w3)
    check("app wires real mutation gate", "real_mutation_denied" in appsrc)

    # no money / no leave balance / no attendance authority mutation
    for name, src in (("wave6c", w6c), ("notifications", n6), ("wave6", w6), ("wave5", w5)):
        check(f"{name} no payroll money sql", "UPDATE payroll" not in src and "INSERT INTO payroll" not in src)
        check(f"{name} no leave balance sql", "UPDATE leave_balances" not in src and "INSERT INTO leave_balances" not in src)
        check(f"{name} no attendance authority sql", "UPDATE attendance_records" not in src)

    # PAM export only
    check("pam export only", "manual_submission_required" in w6)
    check("no automated pam submission", '"pam_submission": False' in w6 or "'pam_submission': False" in w6)

    # cleanup contract + orphan protection
    check("cleanup contract >= 1.5", 'CLEANUP_CONTRACT_VERSION = "1.5' in cleanup or 'CLEANUP_CONTRACT_VERSION = "1.6' in cleanup)
    check("production orphan allowlist intact", "PRODUCTION_ORPHAN_ALLOWLIST" in cleanup)
    check("wave6c cleanup scope present", "def wave6c_scope" in cleanup)

    # deploy templates keep dangerous things off
    deploy = ""
    for cand in (
        ROOT / "ops" / "deploy-shifts-wave6c-prod-controlled.sh",
        Path("/opt/wathefni/orchestrator/ops/deploy-shifts-wave6c-prod-controlled.sh"),
        Path("/Users/azizalmulla/Desktop/claw/wathefni-orchestrator/ops/deploy-shifts-wave6c-prod-controlled.sh"),
    ):
        if cand.is_file():
            deploy = cand.read_text(encoding="utf-8")
            break
    check("wave6c deploy template found", bool(deploy))
    if deploy:
        check("deploy keeps capture ingest off", "WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off" in deploy)
        check("deploy keeps manager allowlist empty", "WATHEFNI_SHIFTS_MANAGER_ALLOWLIST=" in deploy and "MANAGER_ALLOWLIST=9" not in deploy)
        check("deploy keeps operator timers off", "WATHEFNI_SHIFTS_OPERATOR_TIMERS=0" in deploy)
        check("deploy keeps real reminders off", "WATHEFNI_SHIFTS_REAL_REMINDERS=0" in deploy)
        check("deploy keeps integrity jobs off", "WATHEFNI_SHIFTS_INTEGRITY_JOBS=0" in deploy)
        check("deploy keeps employee app allowlist to Talal", "WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST=WATHEFNI-96550252254" in deploy)
        check("deploy has rollback script", "ROLLBACK_OK" in deploy)

    cursor_candidates = [
        ROOT.parent / ".cursor" / "rules" / "shifts-freeze.mdc",
        Path("/Users/azizalmulla/Desktop/claw/.cursor/rules/shifts-freeze.mdc"),
        Path("/opt/wathefni/ops/shifts-freeze.mdc"),
    ]
    cursor = next((p for p in cursor_candidates if p.is_file()), None)
    check("shifts freeze cursor rule present", cursor is not None, str(cursor_candidates[0]))

    for name in (
        "EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
        "LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md",
    ):
        paths = [
            OPS / name,
            Path("/opt/wathefni/ops") / name,
            Path("/Users/azizalmulla/Desktop/claw/ops") / name,
        ]
        p = next((c for c in paths if c.is_file()), None)
        check(f"frozen module doc intact {name}", p is not None, str(paths[0]))

    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
