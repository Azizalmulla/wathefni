#!/usr/bin/env python3
"""Wave 3 C5 — Exit Close + Settlement Ack + Interview + Rehire synthetic prove."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"XC5{_N:05d}"[:12].upper()
OTHER = f"XCX{_N:05d}"[:12].upper()
EMP_PHONE = f"9656011{_N:05d}"
HR_PHONE = f"9656012{_N:05d}"
APPROVER = f"9656013{_N:05d}"
IT_PHONE = f"9656014{_N:05d}"
MGR_PHONE = f"9656015{_N:05d}"
EMP = f"{COMPANY}-W3C5-{SUFFIX}"

MIN_TEMPLATE = [
    {
        "item_key": "handover",
        "item_class": "handover",
        "required": True,
        "owner_role": "manager",
        "title_en": "Handover",
        "title_ar": "تسليم",
        "depends_on": [],
        "due_offset_days": 1,
    },
    {
        "item_key": "hr_docs",
        "item_class": "hr_docs",
        "required": True,
        "owner_role": "hr",
        "title_en": "HR docs",
        "title_ar": "وثائق",
        "depends_on": [],
        "due_offset_days": 1,
    },
    {
        "item_key": "optional_keys",
        "item_class": "keys_cards",
        "required": False,
        "owner_role": "hr",
        "title_en": "Keys",
        "title_ar": "مفاتيح",
        "depends_on": [],
        "due_offset_days": 1,
    },
]


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags_c5(*, on: str, companies: str) -> None:
    os.environ["WATHEFNI_EXIT_CLOSE_C5"] = on
    os.environ["WATHEFNI_EXIT_CLOSE_COMPANIES"] = companies
    os.environ["WATHEFNI_REAL_TERMINATION_CANARY"] = "off"
    os.environ["WATHEFNI_EXIT_CLOSE_SYNTHETIC_MARKERS"] = "W3C5,XC5,W3C4,OB4,W3C3,EX3"


def _flags_upstream() -> None:
    os.environ["WATHEFNI_RESIGNATION_ESS_C3"] = "on"
    os.environ["WATHEFNI_RESIGNATION_ESS_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_EXIT_INTENT_SYNTHETIC_MARKERS"] = "W3C5,XC5,W3C4,OB4,W3C3"
    os.environ["WATHEFNI_OFFBOARDING_C4"] = "on"
    os.environ["WATHEFNI_OFFBOARDING_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_OFFBOARDING_KILL"] = "off"
    os.environ["WATHEFNI_OFFBOARDING_SYNTHETIC_MARKERS"] = "W3C5,XC5,W3C4,OB4,W3C3"


def _build_completed_offboarding(cur, c3, c4, *, lwd: date, emp_key: str = EMP) -> str:
    """Returns offboarding case_id in completed status."""
    c3.enable_company_exit_intent(
        cur,
        company_code=COMPANY,
        actor_phone=HR_PHONE,
        reason="c5 upstream",
        resignation_enabled=True,
        notice_policy_days=1,
    )
    c4.enable_company_offboarding(
        cur,
        company_code=COMPANY,
        actor_phone=HR_PHONE,
        reason="c5 upstream ob",
        template=MIN_TEMPLATE,
        require_settlement_ack=False,
        waiver_roles=["hr"],
    )
    r = c3.create_resignation(
        cur,
        company_code=COMPANY,
        employee_key=emp_key,
        actor_phone=EMP_PHONE,
        requested_last_working_day=lwd,
        reason="c5 resign",
    )
    eid = str(r["case"]["case_id"])
    c3.submit_case(cur, company_code=COMPANY, case_id=eid, actor_phone=EMP_PHONE, reason="s", expected_version=1)
    cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (eid,))
    rv = int((cur.fetchone() or {}).get("row_version") or 1)
    c3.approve_case(cur, company_code=COMPANY, case_id=eid, actor_phone=APPROVER, reason="ok", expected_version=rv)
    cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (eid,))
    rv = int((cur.fetchone() or {}).get("row_version") or 1)
    c3.enter_notice_period(
        cur, company_code=COMPANY, case_id=eid, actor_phone=HR_PHONE, reason="n",
        last_working_day=lwd, expected_version=rv,
    )
    cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (eid,))
    rv = int((cur.fetchone() or {}).get("row_version") or 1)
    c3.mark_ready_for_offboarding(
        cur, company_code=COMPANY, case_id=eid, actor_phone=HR_PHONE, reason="ready", expected_version=rv,
    )
    started = c4.start_offboarding_from_exit_intent(
        cur, company_code=COMPANY, exit_intent_case_id=eid, actor_phone=HR_PHONE, reason="start",
    )
    cid = str(started["case"]["case_id"])
    for item in c4.list_items(cur, case_id=cid):
        if not item.get("required"):
            continue
        role = item.get("owner_role")
        phone = MGR_PHONE if role == "manager" else HR_PHONE
        c4.complete_clearance_item(
            cur,
            company_code=COMPANY,
            item_id=str(item["item_id"]),
            actor_phone=phone,
            actor_role=role,
            reason="done",
            expected_version=int(item.get("row_version") or 1),
        )
    c4._reevaluate_case_status(cur, company_code=COMPANY, case_id=cid)  # noqa: SLF001
    cur.execute("SELECT row_version, status FROM offboarding_cases WHERE case_id=%s", (cid,))
    row = dict(cur.fetchone() or {})
    if row.get("status") != "ready_to_close":
        # force re-eval
        c4._reevaluate_case_status(cur, company_code=COMPANY, case_id=cid)  # noqa: SLF001
        cur.execute("SELECT row_version, status FROM offboarding_cases WHERE case_id=%s", (cid,))
        row = dict(cur.fetchone() or {})
    done = c4.complete_offboarding_case(
        cur,
        company_code=COMPANY,
        case_id=cid,
        actor_phone=HR_PHONE,
        reason="complete for c5",
        expected_version=int(row.get("row_version") or 1),
    )
    if not done.get("ok"):
        raise RuntimeError(f"offboarding complete failed: {done}")
    return cid


def main() -> int:
    print("    exit close c5 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import exit_close_c5 as c5

    check("c5 module", c5.PHASE == "exit_close_c5")
    check("charter stamp", c5.PASS_STAMP == "EXIT_CLOSE_HANDOFF_FULL_PASS")
    check("rollback", "WATHEFNI_EXIT_CLOSE_C5=off" in str(c5.rollback_guidance()))
    check("EN closed", c5.status_label("closed", lang="en") == "Closed")
    check("AR ready", c5.status_label("ready_to_close", lang="ar") == "جاهز للإغلاق")
    check("assistant out", c5.honesty_payload().get("assistant_mutations") is False)
    check("sole left authority", c5.honesty_payload().get("sole_employment_left_authority") is True)
    check("finalized ≠ paid", c5.honesty_payload().get("settlement_finalized_is_not_paid") is True)
    check("real term dark", c5.honesty_payload().get("real_termination_dark") is True)

    _flags_c5(on="off", companies="")
    check("global off", c5.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags_c5(on="on", companies="")
    check("empty allowlist", "allowlist" in str(c5.runtime_gate_for_company(COMPANY).get("gate")))
    _flags_c5(on="on", companies=COMPANY)
    check("canary ok", c5.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant iso", c5.runtime_gate_for_company(OTHER).get("ok") is not True)
    os.environ["WATHEFNI_REAL_TERMINATION_CANARY"] = "on"
    check("real canary blocked", c5.assert_real_termination_dark().get("ok") is not True)
    os.environ["WATHEFNI_REAL_TERMINATION_CANARY"] = "off"

    try:
        import app
        import exit_intent_c3 as c3
        import offboarding_c4 as c4
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    hire = date(2035, 1, 1)
    lwd_past = date.today() - timedelta(days=1)
    lwd_future = date.today() + timedelta(days=30)
    _flags_upstream()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            c3.ensure_exit_intent_c3_schema(cur)
            c4.ensure_offboarding_c4_schema(cur)
            c5.ensure_exit_close_c5_schema(cur)
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"XC5 {COMPANY}"),
            )
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE
                  SET employment_status='active', company_code=EXCLUDED.company_code, updated_at=now()
                """,
                (COMPANY, EMP, EMP_PHONE, "XC5 Emp", hire, hire, '{"department":"Ops","person_key":"PERSON-' + SUFFIX + '"}'),
            )

            en = c5.enable_company_exit_close(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="enable close no payroll",
                require_settlement_ack=False,
                require_access_revoke_ack=False,
                require_last_working_day_reached=True,
                exit_interview_enabled=False,
            )
            check("enable company", en.get("ok") is True, en)
            vis = c5.feature_visibility(cur, COMPANY)
            check("interview hidden when disabled", vis.get("exit_interview_visible") is False, vis)

            # Incomplete offboarding: start case but do not complete required items
            c3.enable_company_exit_intent(
                cur, company_code=COMPANY, actor_phone=HR_PHONE, reason="x", resignation_enabled=True,
            )
            c4.enable_company_offboarding(
                cur, company_code=COMPANY, actor_phone=HR_PHONE, reason="x", template=MIN_TEMPLATE,
            )
            r0 = c3.create_resignation(
                cur, company_code=COMPANY, employee_key=EMP, actor_phone=EMP_PHONE,
                requested_last_working_day=lwd_past, reason="incomplete path",
            )
            check("incomplete path resign draft", r0.get("ok") is True, r0)
            e0 = str((r0.get("case") or {}).get("case_id"))
            c3.submit_case(cur, company_code=COMPANY, case_id=e0, actor_phone=EMP_PHONE, reason="s", expected_version=1)
            cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (e0,))
            rv = int((cur.fetchone() or {}).get("row_version") or 1)
            c3.approve_case(cur, company_code=COMPANY, case_id=e0, actor_phone=APPROVER, reason="ok", expected_version=rv)
            cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (e0,))
            rv = int((cur.fetchone() or {}).get("row_version") or 1)
            c3.enter_notice_period(
                cur, company_code=COMPANY, case_id=e0, actor_phone=HR_PHONE, reason="n",
                last_working_day=lwd_past, expected_version=rv,
            )
            cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (e0,))
            rv = int((cur.fetchone() or {}).get("row_version") or 1)
            ready0 = c3.mark_ready_for_offboarding(
                cur, company_code=COMPANY, case_id=e0, actor_phone=HR_PHONE, reason="r", expected_version=rv,
            )
            check("incomplete path exit ready", ready0.get("ok") is True, ready0)
            inc = c4.start_offboarding_from_exit_intent(
                cur, company_code=COMPANY, exit_intent_case_id=e0, actor_phone=HR_PHONE, reason="inc",
            )
            check("incomplete offboarding started", inc.get("ok") is True, inc)
            inc_id = str((inc.get("case") or {}).get("case_id"))

            blocked_inc = c5.open_exit_close_from_offboarding(
                cur, company_code=COMPANY, offboarding_case_id=inc_id, actor_phone=HR_PHONE, reason="early",
            )
            check(
                "incomplete required clearance blocks close",
                blocked_inc.get("error") == "offboarding_not_completed",
                blocked_inc,
            )

            # Complete the incomplete case so EMP can be reused for Path A, OR use helper which creates new exit
            # Path A uses same EMP — complete remaining items on inc_id then complete case
            for item in c4.list_items(cur, case_id=inc_id):
                if not item.get("required"):
                    continue
                if item.get("status") in ("completed", "waived"):
                    continue
                role = item.get("owner_role")
                phone = MGR_PHONE if role == "manager" else HR_PHONE
                c4.complete_clearance_item(
                    cur,
                    company_code=COMPANY,
                    item_id=str(item["item_id"]),
                    actor_phone=phone,
                    actor_role=role,
                    reason="finish incomplete",
                    expected_version=int(item.get("row_version") or 1),
                )
            c4._reevaluate_case_status(cur, company_code=COMPANY, case_id=inc_id)  # noqa: SLF001
            cur.execute("SELECT row_version FROM offboarding_cases WHERE case_id=%s", (inc_id,))
            rv_ob = int((cur.fetchone() or {}).get("row_version") or 1)
            c4.complete_offboarding_case(
                cur, company_code=COMPANY, case_id=inc_id, actor_phone=HR_PHONE, reason="finish",
                expected_version=rv_ob,
            )
            ob_id = inc_id
            opened = c5.open_exit_close_from_offboarding(
                cur, company_code=COMPANY, offboarding_case_id=ob_id, actor_phone=HR_PHONE, reason="open",
            )
            check("completed clearance → close case", opened.get("ok") is True, opened)
            close_id = str(opened["case"]["close_id"])
            check(
                "Payroll absent + settlement not required → ready/closable",
                (opened.get("case") or {}).get("status") in ("ready_to_close", "pending_close", "blocked")
                and (opened.get("case") or {}).get("settlement_gate") == "not_required",
                opened,
            )
            # Ensure ready
            ev = c5.evaluate_close_readiness(cur, company_code=COMPANY, close_id=close_id)
            check("ready to close (no payroll)", (ev.get("case") or {}).get("status") == "ready_to_close", ev)

            dup = c5.open_exit_close_from_offboarding(
                cur, company_code=COMPANY, offboarding_case_id=ob_id, actor_phone=HR_PHONE, reason="dup",
            )
            check("duplicate open idempotent", dup.get("duplicate_open") is True, dup)

            sod = c5.execute_exit_close(
                cur, company_code=COMPANY, close_id=close_id, actor_phone=HR_PHONE, reason="self",
                expected_version=int((ev.get("case") or {}).get("row_version") or 1),
            )
            check("SoD self-close forbidden", sod.get("error") == "sod_self_close_forbidden", sod)

            stale = c5.execute_exit_close(
                cur, company_code=COMPANY, close_id=close_id, actor_phone=APPROVER, reason="stale",
                expected_version=0,
            )
            check("stale close rejected", stale.get("error") == "stale_row_version", stale)

            closed = c5.execute_exit_close(
                cur,
                company_code=COMPANY,
                close_id=close_id,
                actor_phone=APPROVER,
                reason="close employment",
                expected_version=int((ev.get("case") or {}).get("row_version") or 1),
                rehire_eligibility="eligible",
            )
            check("canonical employment becomes left only at close", closed.get("ok") is True and closed.get("employment_status") == "left", closed)
            cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (EMP,))
            check("employment_status left", str((cur.fetchone() or {}).get("employment_status")) == "left")
            wf = c5.is_active_for_workforce(cur, company_code=COMPANY, employee_key=EMP)
            check("active workforce domains stop", wf.get("active") is False, wf)

            dup_close = c5.execute_exit_close(
                cur, company_code=COMPANY, close_id=close_id, actor_phone=APPROVER, reason="dup close",
            )
            check("duplicate close idempotent", dup_close.get("idempotent_duplicate_close") is True, dup_close)

            reopen = c5.attempt_reopen_closed_employment(
                cur, company_code=COMPANY, employee_key=EMP,
            )
            check("no silent reopen", reopen.get("error") == "silent_reopen_forbidden", reopen)

            reh = c5.set_rehire_eligibility(
                cur,
                company_code=COMPANY,
                close_id=close_id,
                actor_phone=HR_PHONE,
                eligibility="review_required",
                reason="manager flag",
            )
            check("rehire eligibility + audit", reh.get("ok") is True and (reh.get("alumni") or {}).get("rehire_eligibility") == "review_required", reh)
            check("same person preserved", (reh.get("alumni") or {}).get("person_key") == f"PERSON-{SUFFIX}", reh)

            # LWD gate on a fresh employee
            emp2 = f"{COMPANY}-W3C5B-{SUFFIX}"
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE SET employment_status='active'
                """,
                (COMPANY, emp2, f"9656021{_N:05d}", "XC5 B", hire, hire),
            )
            # Reset employee EMP already left — use emp2
            # Need phone for resign - create_resignation uses actor not emp phone match
            ob2 = _build_completed_offboarding(cur, c3, c4, lwd=lwd_future, emp_key=emp2)
            # Patch exit snapshot LWD future already from notice
            c5.enable_company_exit_close(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="lwd gate on",
                require_settlement_ack=False,
                require_last_working_day_reached=True,
                allow_lwd_override=True,
                exit_interview_enabled=False,
            )
            o2 = c5.open_exit_close_from_offboarding(
                cur, company_code=COMPANY, offboarding_case_id=ob2, actor_phone=HR_PHONE, reason="lwd",
            )
            c2 = str(o2["case"]["close_id"])
            ev2 = c5.evaluate_close_readiness(cur, company_code=COMPANY, close_id=c2)
            check(
                "last-working-date gate blocks",
                (ev2.get("case") or {}).get("status") == "blocked"
                and "last_working_day_not_reached" in str((ev2.get("readiness") or {}).get("blockers")),
                ev2,
            )
            ov = c5.override_last_working_day_gate(
                cur, company_code=COMPANY, close_id=c2, actor_phone=HR_PHONE, reason="HR override LWD",
            )
            check("LWD override by HR", (ov.get("case") or {}).get("status") == "ready_to_close", ov)

            # Settlement required path — new employee emp3
            emp3 = f"{COMPANY}-W3C5C-{SUFFIX}"
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE SET employment_status='active'
                """,
                (COMPANY, emp3, f"9656022{_N:05d}", "XC5 C", hire, hire),
            )
            ob3 = _build_completed_offboarding(cur, c3, c4, lwd=lwd_past, emp_key=emp3)
            c5.enable_company_exit_close(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="settlement required",
                require_settlement_ack=True,
                allow_settlement_waiver=True,
                require_last_working_day_reached=True,
                exit_interview_enabled=False,
            )
            o3 = c5.open_exit_close_from_offboarding(
                cur, company_code=COMPANY, offboarding_case_id=ob3, actor_phone=HR_PHONE, reason="sett",
            )
            c3id = str(o3["case"]["close_id"])
            ev3 = c5.evaluate_close_readiness(cur, company_code=COMPANY, close_id=c3id)
            check(
                "settlement required blocks before finalize/ack",
                (ev3.get("case") or {}).get("status") == "blocked",
                ev3,
            )

            unauth_w = c5.waive_settlement(
                cur,
                company_code=COMPANY,
                close_id=c3id,
                actor_phone=MGR_PHONE,
                actor_role="manager",
                reason="nope",
            )
            check("unauthorized settlement waiver denied", unauth_w.get("error") == "unauthorized_settlement_waiver", unauth_w)

            # Wave 2 settlement finalize + ack path on emp3
            try:
                import payroll_settlement_ot_c6 as sett

                os.environ["WATHEFNI_PAYROLL_SETTLEMENT_C6"] = "on"
                os.environ["WATHEFNI_PAYROLL_SETTLEMENT_COMPANIES"] = COMPANY
                os.environ["WATHEFNI_PAYROLL_SETTLEMENT_KILL"] = "off"
                sett.ensure_payroll_settlement_ot_c6_schema(cur)
                sett.enable_company_settlement_ot(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR_PHONE,
                    reason="c5 consume wave2",
                    settlement_enabled=True,
                    ot_authorization_enabled=False,
                )
                pkt = sett.seed_lifecycle_settlement_packet(
                    cur,
                    company_code=COMPANY,
                    employee_key=emp3,
                    termination_effective_on=lwd_past,
                    last_working_day=lwd_past,
                    leave_encashment_days=0,
                    compensation_components=[
                        {"code": "BASIC", "amount": 100, "label_en": "Basic", "label_ar": "أساسي"}
                    ],
                )
                check("wave2 packet seeded", pkt.get("ok") is True, pkt)
                packet_id = str((pkt.get("packet") or {}).get("packet_id") or "")
                created_s = sett.create_settlement_from_lifecycle_packet(
                    cur,
                    company_code=COMPANY,
                    lifecycle_packet_id=packet_id,
                    actor_phone=HR_PHONE,
                    reason="create settlement",
                    final_period_start=lwd_past - timedelta(days=30),
                    final_period_end=lwd_past,
                )
                check("wave2 settlement created", created_s.get("ok") is True, created_s)
                sid = str((created_s.get("settlement") or {}).get("settlement_id") or "")
                if sid:
                    cur.execute("SELECT row_version FROM payroll_settlement_runs WHERE settlement_id=%s", (sid,))
                    srv = int((cur.fetchone() or {}).get("row_version") or 1)
                    calc = sett.calculate_settlement(
                        cur, company_code=COMPANY, settlement_id=sid, actor_phone=HR_PHONE, reason="calc",
                        expected_row_version=srv,
                    )
                    cur.execute("SELECT row_version FROM payroll_settlement_runs WHERE settlement_id=%s", (sid,))
                    srv = int((cur.fetchone() or {}).get("row_version") or 1)
                    if calc.get("ok"):
                        sett.approve_settlement(
                            cur, company_code=COMPANY, settlement_id=sid, actor_phone=APPROVER, reason="appr",
                            expected_row_version=srv,
                        )
                        cur.execute("SELECT row_version FROM payroll_settlement_runs WHERE settlement_id=%s", (sid,))
                        srv = int((cur.fetchone() or {}).get("row_version") or 1)
                        fin = sett.finalize_settlement(
                            cur, company_code=COMPANY, settlement_id=sid, actor_phone=IT_PHONE, reason="fin",
                            expected_row_version=srv,
                        )
                        check("wave2 settlement finalized", fin.get("ok") is True, fin)
                    bind = c5.bind_wave2_settlement_finalized(
                        cur,
                        company_code=COMPANY,
                        close_id=c3id,
                        settlement_run_id=sid,
                        actor_phone=HR_PHONE,
                        reason="bind finalized",
                    )
                    check("bind finalized settlement", bind.get("ok") is True, bind)
                    check("finalized but ack absent still blocked/distinct", bind.get("settlement_acknowledged") is False, bind)
                    ev_b = c5.evaluate_close_readiness(cur, company_code=COMPANY, close_id=c3id)
                    check(
                        "settlement finalized but required acknowledgement absent → blocked",
                        (ev_b.get("case") or {}).get("status") == "blocked"
                        or "finalized_awaiting_ack" in str((ev_b.get("readiness") or {}).get("blockers")),
                        ev_b,
                    )
                    check(
                        "payment status distinct from settlement ack",
                        (bind.get("payment_status") == "not_confirmed")
                        and (ev_b.get("case") or {}).get("distinctions", {}).get("finalized_equals_paid") is False,
                        bind,
                    )
                    ack = c5.acknowledge_settlement(
                        cur, company_code=COMPANY, close_id=c3id, actor_phone=HR_PHONE, reason="ack settlement",
                    )
                    check(
                        "Payroll enabled + settlement finalized/acknowledged → ready",
                        (ack.get("case") or {}).get("status") == "ready_to_close",
                        ack,
                    )
                    cur.execute("SELECT row_version FROM exit_close_cases WHERE close_id=%s", (c3id,))
                    rv_c = int((cur.fetchone() or {}).get("row_version") or 1)
                    closed3 = c5.execute_exit_close(
                        cur, company_code=COMPANY, close_id=c3id, actor_phone=APPROVER, reason="close with sett",
                        expected_version=rv_c,
                    )
                    check("close with settlement ack", closed3.get("ok") is True, closed3)
            except Exception as exc:
                check("wave2 settlement path", False, str(exc))

            # Settlement waiver path (emp4)
            emp4 = f"{COMPANY}-W3C5D-{SUFFIX}"
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE SET employment_status='active'
                """,
                (COMPANY, emp4, f"9656023{_N:05d}", "XC5 D", hire, hire),
            )
            ob4 = _build_completed_offboarding(cur, c3, c4, lwd=lwd_past, emp_key=emp4)
            c5.enable_company_exit_close(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="waiver path",
                require_settlement_ack=True,
                allow_settlement_waiver=True,
                exit_interview_enabled=False,
            )
            o4 = c5.open_exit_close_from_offboarding(
                cur, company_code=COMPANY, offboarding_case_id=ob4, actor_phone=HR_PHONE, reason="w",
            )
            c4id = str(o4["case"]["close_id"])
            wav = c5.waive_settlement(
                cur, company_code=COMPANY, close_id=c4id, actor_phone=HR_PHONE, actor_role="hr", reason="no settlement run",
            )
            check("settlement waiver authorized", (wav.get("case") or {}).get("settlement_gate") == "waived", wav)
            # Ensure no fake settlement row invented
            cur.execute(
                "SELECT settlement_run_id FROM exit_close_cases WHERE close_id=%s",
                (c4id,),
            )
            check("no fake settlement row on waiver", (cur.fetchone() or {}).get("settlement_run_id") is None)

            # Access ack optional semantics
            emp5 = f"{COMPANY}-W3C5E-{SUFFIX}"
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE SET employment_status='active'
                """,
                (COMPANY, emp5, f"9656024{_N:05d}", "XC5 E", hire, hire),
            )
            ob5 = _build_completed_offboarding(cur, c3, c4, lwd=lwd_past, emp_key=emp5)
            c5.enable_company_exit_close(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="access gate",
                require_settlement_ack=False,
                require_access_revoke_ack=True,
                exit_interview_enabled=False,
            )
            o5 = c5.open_exit_close_from_offboarding(
                cur, company_code=COMPANY, offboarding_case_id=ob5, actor_phone=HR_PHONE, reason="a",
            )
            c5id = str(o5["case"]["close_id"])
            ev5 = c5.evaluate_close_readiness(cur, company_code=COMPANY, close_id=c5id)
            check(
                "optional IdP/access ack gate blocks until ack",
                (ev5.get("case") or {}).get("status") == "blocked",
                ev5,
            )
            unauth_a = c5.waive_access_revoke(
                cur, company_code=COMPANY, close_id=c5id, actor_phone=MGR_PHONE, actor_role="manager", reason="x",
            )
            check("unauthorized access waiver denied", unauth_a.get("error") == "unauthorized_access_waiver", unauth_a)
            ack_a = c5.acknowledge_access_revoke(
                cur, company_code=COMPANY, close_id=c5id, actor_phone=IT_PHONE, reason="manual/idp acked",
            )
            check("access acknowledgement semantics", (ack_a.get("case") or {}).get("status") == "ready_to_close", ack_a)

            # Exit interview non-blocking default + complete/decline/skip
            emp6 = f"{COMPANY}-W3C5F-{SUFFIX}"
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE SET employment_status='active'
                """,
                (COMPANY, emp6, f"9656025{_N:05d}", "XC5 F", hire, hire),
            )
            ob6 = _build_completed_offboarding(cur, c3, c4, lwd=lwd_past, emp_key=emp6)
            c5.enable_company_exit_close(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="interview optional",
                require_settlement_ack=False,
                exit_interview_enabled=True,
                exit_interview_required=False,
            )
            vis2 = c5.feature_visibility(cur, COMPANY)
            check("exit interview visible when enabled", vis2.get("exit_interview_visible") is True, vis2)
            o6 = c5.open_exit_close_from_offboarding(
                cur, company_code=COMPANY, offboarding_case_id=ob6, actor_phone=HR_PHONE, reason="iv",
            )
            c6id = str(o6["case"]["close_id"])
            ev6 = c5.evaluate_close_readiness(cur, company_code=COMPANY, close_id=c6id)
            check(
                "exit interview non-blocking default",
                (ev6.get("case") or {}).get("status") == "ready_to_close",
                ev6,
            )
            cur.execute(
                "SELECT interview_id FROM exit_interviews WHERE close_id=%s ORDER BY created_at DESC LIMIT 1",
                (c6id,),
            )
            iid = str((cur.fetchone() or {}).get("interview_id"))
            resp = c5.respond_exit_interview(
                cur,
                company_code=COMPANY,
                interview_id=iid,
                actor_phone=EMP_PHONE,
                decision="completed",
                structured_reasons=["career", "compensation"],
                notes="شكراً",
                lang="ar",
            )
            check("exit interview complete", resp.get("ok") is True and (resp.get("interview") or {}).get("status") == "completed", resp)
            # Decline / skip on separate invites
            inv2 = c5.invite_exit_interview(
                cur, company_code=COMPANY, close_id=c6id, actor_phone=HR_PHONE, reason="second",
            )
            dcl = c5.respond_exit_interview(
                cur, company_code=COMPANY, interview_id=str(inv2["interview"]["interview_id"]),
                actor_phone=EMP_PHONE, decision="declined",
            )
            check("exit interview decline", dcl.get("ok") is True, dcl)
            inv3 = c5.invite_exit_interview(
                cur, company_code=COMPANY, close_id=c6id, actor_phone=HR_PHONE, reason="third",
            )
            skp = c5.respond_exit_interview(
                cur, company_code=COMPANY, interview_id=str(inv3["interview"]["interview_id"]),
                actor_phone=HR_PHONE, decision="skipped",
            )
            check("exit interview skip", skp.get("ok") is True, skp)
            conf = c5.get_exit_interview(
                cur, company_code=COMPANY, interview_id=iid, actor_role="manager",
            )
            check("interview confidentiality RBAC", "[redacted]" in str((conf.get("interview") or {}).get("notes")), conf)

            src = Path(__file__).with_name("exit_close_c5.py").read_text()
            check("EN/AR contracts", "status_label_ar" in src and "مغلق" in src)
            check("no fake settlement invent", "fake_settlement_rows_forbidden" in src)

            off = c5.disable_company_exit_close(
                cur, company_code=COMPANY, actor_phone=HR_PHONE, reason="rollback",
            )
            check("disable preserves history", off.get("history_preserved") is True, off)
            cur.execute(
                "SELECT count(*) AS c FROM exit_close_cases WHERE company_code=%s AND status='closed'",
                (COMPANY,),
            )
            check("rollback preserves closed truth", int((cur.fetchone() or {}).get("c") or 0) >= 1)
            cur.execute(
                "SELECT employment_status FROM employees WHERE employee_key=%s",
                (EMP,),
            )
            check("closed employment truth intact", str((cur.fetchone() or {}).get("employment_status")) == "left")
            check("real termination gate remains OFF", c5.real_termination_canary_on() is False)

        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("EXIT_CLOSE_HANDOFF_UNIT_PASS")
    print("EXIT_CLOSE_HANDOFF_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
