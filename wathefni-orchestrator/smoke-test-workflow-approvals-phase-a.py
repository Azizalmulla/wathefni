#!/usr/bin/env python3
"""Phase A slice 1 — workflow_approvals authority smoke.

Pins:
  - schema version
  - instance/step/delegation state machines
  - SoD self-approval ban
  - delegation coverage + effective status
  - next-instance status after step
  - default runtime OFF + company allowlist fail-closed
  - rollback guidance present
  - optional in-memory DB path when psycopg2 + DATABASE_URL available

Run: python3 smoke-test-workflow-approvals-phase-a.py
"""
from __future__ import annotations

import os
import sys
import uuid
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
    print("    workflow_approvals phase A slice 1 — SM + SoD + gates + delegation")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import workflow_approvals as wa

    check("schema version pinned", wa.WORKFLOW_APPROVALS_SCHEMA_VERSION == "1.0.0")
    check("sql pack exists", wa._SCHEMA_SQL_PATH.is_file())

    # --- State machines -------------------------------------------------------
    check(
        "instance draft→pending",
        wa.can_transition(wa.INSTANCE_TRANSITIONS, "draft", "pending"),
    )
    check(
        "instance pending→approved",
        wa.can_transition(wa.INSTANCE_TRANSITIONS, "pending", "approved"),
    )
    check(
        "instance approved terminal",
        not wa.can_transition(wa.INSTANCE_TRANSITIONS, "approved", "pending"),
    )
    check(
        "step pending→approved",
        wa.can_transition(wa.STEP_TRANSITIONS, "pending", "approved"),
    )
    check(
        "step approved terminal",
        not wa.can_transition(wa.STEP_TRANSITIONS, "approved", "rejected"),
    )
    check(
        "delegation active→revoked",
        wa.can_transition(wa.DELEGATION_TRANSITIONS, "active", "revoked"),
    )
    check(
        "delegation revoked terminal",
        not wa.can_transition(wa.DELEGATION_TRANSITIONS, "revoked", "active"),
    )

    # --- Policy steps ---------------------------------------------------------
    bad = wa.validate_policy_steps([])
    check("empty policy steps rejected", isinstance(bad, dict) and bad.get("error") == "policy_steps_required")
    good = wa.validate_policy_steps(
        [{"step_order": 1, "assignee_user_id": "u-mgr"}, {"step_order": 2, "assignee_role": "hr_admin"}]
    )
    check("policy steps normalize", isinstance(good, list) and len(good) == 2)

    # --- SoD ------------------------------------------------------------------
    sod = wa.sod_self_approval_denied(
        forbid_self_approval=True,
        created_by_user_id="u-creator",
        created_by_phone="96550001111",
        actor_user_id="u-creator",
        actor_phone="96559999999",
    )
    check("SoD blocks same user", bool(sod) and sod.get("error") == "self_approval_forbidden")
    sod_phone = wa.sod_self_approval_denied(
        forbid_self_approval=True,
        created_by_user_id="u-a",
        created_by_phone="96550001111",
        actor_user_id="u-b",
        actor_phone="96550001111",
    )
    check("SoD blocks same phone", bool(sod_phone) and sod_phone.get("error") == "self_approval_forbidden")
    sod_ok = wa.sod_self_approval_denied(
        forbid_self_approval=True,
        created_by_user_id="u-a",
        created_by_phone="96550001111",
        actor_user_id="u-b",
        actor_phone="96550002222",
    )
    check("SoD allows other actor", sod_ok is None)
    sod_off = wa.sod_self_approval_denied(
        forbid_self_approval=False,
        created_by_user_id="u-a",
        created_by_phone="96550001111",
        actor_user_id="u-a",
        actor_phone="96550001111",
    )
    check("SoD optional when policy allows", sod_off is None)

    # --- Delegation model -----------------------------------------------------
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    grant = {
        "status": "active",
        "starts_at": now - timedelta(hours=1),
        "ends_at": now + timedelta(days=1),
        "scope_subject_types": ["requisition"],
    }
    check(
        "delegation covers scoped subject",
        wa.delegation_covers(grant=grant, subject_type="requisition", at=now),
    )
    check(
        "delegation rejects out-of-scope",
        not wa.delegation_covers(grant=grant, subject_type="probation_decision", at=now),
    )
    all_scope = {**grant, "scope_subject_types": None}
    check("delegation null scope = all", wa.delegation_covers(grant=all_scope, subject_type="x", at=now))
    expired = {**grant, "ends_at": now - timedelta(minutes=1)}
    check("delegation expired window", not wa.delegation_covers(grant=expired, subject_type="requisition", at=now))
    scheduled = {
        "status": "scheduled",
        "starts_at": now - timedelta(minutes=5),
        "ends_at": now + timedelta(days=1),
        "scope_subject_types": None,
    }
    check(
        "scheduled becomes active when started",
        wa.effective_delegation_status(scheduled, now) == "active",
    )

    step = {"assignee_user_id": "u-mgr", "assignee_role": None}
    check("direct assignee may decide", wa.actor_may_decide_step(step=step, actor_user_id="u-mgr"))
    check(
        "delegate may decide as acting_as",
        wa.actor_may_decide_step(step=step, actor_user_id="u-delegate", acting_as_user_id="u-mgr"),
    )
    check(
        "stranger may not decide",
        not wa.actor_may_decide_step(step=step, actor_user_id="u-other"),
    )

    # --- Instance progression -------------------------------------------------
    check(
        "reject ends instance",
        wa.next_instance_status_after_step(decision="rejected", has_remaining_pending_steps=True)
        == "rejected",
    )
    check(
        "approve with remaining stays pending",
        wa.next_instance_status_after_step(decision="approved", has_remaining_pending_steps=True)
        == "pending",
    )
    check(
        "approve final → approved",
        wa.next_instance_status_after_step(decision="approved", has_remaining_pending_steps=False)
        == "approved",
    )

    # --- Tenant / module gates (fail closed) ----------------------------------
    prev_flag = os.environ.pop("WATHEFNI_WORKFLOW_APPROVALS", None)
    prev_cos = os.environ.pop("WATHEFNI_WORKFLOW_APPROVALS_COMPANIES", None)
    try:
        check("runtime flag default off", wa.workflow_approvals_runtime_flag_on() is False)
        os.environ["WATHEFNI_WORKFLOW_APPROVALS"] = "on"
        check("runtime flag on", wa.workflow_approvals_runtime_flag_on() is True)
        os.environ["WATHEFNI_WORKFLOW_APPROVALS_COMPANIES"] = "WATHEFNI,ACME"
        allow = wa.workflow_approvals_company_allowlist()
        check("allowlist parsed", allow == {"WATHEFNI", "ACME"})
        check("allowlist excludes others", "OTHER" not in allow)
    finally:
        if prev_flag is None:
            os.environ.pop("WATHEFNI_WORKFLOW_APPROVALS", None)
        else:
            os.environ["WATHEFNI_WORKFLOW_APPROVALS"] = prev_flag
        if prev_cos is None:
            os.environ.pop("WATHEFNI_WORKFLOW_APPROVALS_COMPANIES", None)
        else:
            os.environ["WATHEFNI_WORKFLOW_APPROVALS_COMPANIES"] = prev_cos

    rb = wa.rollback_guidance()
    check("rollback has runtime steps", isinstance(rb.get("runtime"), list) and len(rb["runtime"]) >= 2)
    check("rollback retains tables", any("Retain" in s or "retain" in s.lower() for s in rb.get("data", [])))

    # --- Optional DB integration ----------------------------------------------
    db_url = str(os.environ.get("DATABASE_URL") or os.environ.get("WATHEFNI_DATABASE_URL") or "").strip()
    if not db_url:
        print("SKIP DB: no DATABASE_URL (unit gates only)")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0

    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ModuleNotFoundError:
        print("SKIP DB: psycopg2 not available")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0

    suffix = uuid.uuid4().hex[:8]
    company = f"WFA{suffix}".upper()
    os.environ["WATHEFNI_WORKFLOW_APPROVALS"] = "on"
    os.environ["WATHEFNI_WORKFLOW_APPROVALS_COMPANIES"] = company

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            wa.ensure_workflow_approvals_schema(cur)
            conn.commit()

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                gate = wa.workflow_approvals_enabled_for_company(cur, company)
                check(
                    "DB gate blocked until company enabled",
                    gate.get("ok") is False and gate.get("gate") == "company_setting",
                    gate,
                )
                wa.set_company_workflow_approval_enabled(cur, company, enabled=True)
                gate2 = wa.workflow_approvals_enabled_for_company(cur, company)
                check("DB gate opens when enabled", gate2.get("ok") is True, gate2)

                pol = wa.upsert_policy(
                    cur,
                    company_code=company,
                    subject_type="phase_a_probe",
                    name="Phase A probe",
                    steps=[
                        {"step_order": 1, "assignee_user_id": "u-approver"},
                        {"step_order": 2, "assignee_user_id": "u-hr"},
                    ],
                    forbid_self_approval=True,
                    actor_user_id="u-admin",
                )
                check("DB policy upsert", pol.get("ok") is True, pol)

                idem = f"idem-{suffix}"
                created = wa.create_instance(
                    cur,
                    company_code=company,
                    subject_type="phase_a_probe",
                    subject_id=f"subj-{suffix}",
                    created_by_user_id="u-creator",
                    created_by_phone="96550001111",
                    idempotency_key=idem,
                    submit=True,
                )
                check("DB instance create", created.get("ok") is True and not created.get("replayed"), created)
                replay = wa.create_instance(
                    cur,
                    company_code=company,
                    subject_type="phase_a_probe",
                    subject_id=f"subj-{suffix}-other",
                    created_by_user_id="u-creator",
                    idempotency_key=idem,
                    submit=True,
                )
                check("DB create idempotent replay", replay.get("ok") is True and replay.get("replayed") is True)

                inst = created["instance"]
                sod_block = wa.decide_step(
                    cur,
                    company_code=company,
                    instance_id=inst["instance_id"],
                    decision="approved",
                    actor_user_id="u-creator",
                    decision_id=f"d-sod-{suffix}",
                    expected_row_version=inst["row_version"],
                )
                check(
                    "DB SoD blocks creator",
                    sod_block.get("error") == "self_approval_forbidden",
                    sod_block,
                )

                # wrong version concurrency
                conflict = wa.decide_step(
                    cur,
                    company_code=company,
                    instance_id=inst["instance_id"],
                    decision="approved",
                    actor_user_id="u-approver",
                    decision_id=f"d-c-{suffix}",
                    expected_row_version=int(inst["row_version"]) + 99,
                )
                check(
                    "DB concurrency conflict",
                    conflict.get("error") == "concurrency_conflict",
                    conflict,
                )

                d1 = wa.decide_step(
                    cur,
                    company_code=company,
                    instance_id=inst["instance_id"],
                    decision="approved",
                    actor_user_id="u-approver",
                    decision_id=f"d1-{suffix}",
                    expected_row_version=inst["row_version"],
                )
                check("DB step1 approve", d1.get("ok") is True and d1["instance"]["status"] == "pending", d1)

                d1b = wa.decide_step(
                    cur,
                    company_code=company,
                    instance_id=inst["instance_id"],
                    decision="approved",
                    actor_user_id="u-approver",
                    decision_id=f"d1-{suffix}",
                    expected_row_version=d1["instance"]["row_version"],
                )
                check("DB decision_id replay", d1b.get("ok") is True and d1b.get("replayed") is True)

                # delegation for step 2
                grant = wa.create_delegation_grant(
                    cur,
                    company_code=company,
                    delegator_user_id="u-hr",
                    delegate_user_id="u-delegate",
                    starts_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                    ends_at=datetime.now(timezone.utc) + timedelta(days=1),
                    scope_subject_types=["phase_a_probe"],
                    actor_user_id="u-hr",
                )
                check("DB delegation create", grant.get("ok") is True, grant)

                d2 = wa.decide_step(
                    cur,
                    company_code=company,
                    instance_id=inst["instance_id"],
                    decision="approved",
                    actor_user_id="u-delegate",
                    decision_id=f"d2-{suffix}",
                    expected_row_version=d1["instance"]["row_version"],
                )
                check(
                    "DB delegate final approve",
                    d2.get("ok") is True and d2["instance"]["status"] == "approved",
                    d2,
                )
                check("DB acting_as set", d2.get("acting_as_user_id") == "u-hr", d2)

                cur.execute(
                    "SELECT count(*) AS c FROM workflow_approval_events WHERE company_code=%s",
                    (company,),
                )
                ev_count = int(dict(cur.fetchone())["c"])
                check("DB audit events written", ev_count >= 5, ev_count)

                # tenant isolation: other company cannot see gate
                other = wa.workflow_approvals_enabled_for_company(cur, "OTHERCO")
                check(
                    "DB other company gated",
                    other.get("ok") is False,
                    other,
                )

                # disable company setting = rollback path
                wa.set_company_workflow_approval_enabled(cur, company, enabled=False)
                closed = wa.create_instance(
                    cur,
                    company_code=company,
                    subject_type="phase_a_probe",
                    subject_id=f"after-off-{suffix}",
                    created_by_user_id="u-creator",
                )
                check(
                    "DB rollback company disable blocks create",
                    closed.get("ok") is False and closed.get("gate") == "company_setting",
                    closed,
                )
            conn.commit()
    finally:
        conn.close()
        os.environ.pop("WATHEFNI_WORKFLOW_APPROVALS", None)
        os.environ.pop("WATHEFNI_WORKFLOW_APPROVALS_COMPANIES", None)

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
