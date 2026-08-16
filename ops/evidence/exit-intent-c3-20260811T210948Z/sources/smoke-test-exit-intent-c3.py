#!/usr/bin/env python3
"""Wave 3 C3 — Exit intent (resignation/termination/EOC) synthetic prove."""
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
COMPANY = f"EX3{_N:05d}"[:12].upper()
OTHER = f"EXX{_N:05d}"[:12].upper()
EMP_PHONE = f"9655811{_N:05d}"
HR_PHONE = f"9655812{_N:05d}"
APPROVER = f"9655813{_N:05d}"
EMP = f"{COMPANY}-W3C3-{SUFFIX}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, on: str, companies: str) -> None:
    os.environ["WATHEFNI_RESIGNATION_ESS_C3"] = on
    os.environ["WATHEFNI_RESIGNATION_ESS_COMPANIES"] = companies
    os.environ["WATHEFNI_REAL_TERMINATION_CANARY"] = "off"
    os.environ["WATHEFNI_EXIT_INTENT_SYNTHETIC_MARKERS"] = "W3C3,EX3,EI3"


def main() -> int:
    print("    exit intent c3 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import exit_intent_c3 as c3

    check("c3 module", c3.PHASE == "exit_intent_c3")
    check("charter stamp name", c3.PASS_STAMP == "RESIGNATION_TERMINATION_FULL_PASS")
    check("rollback guidance", "WATHEFNI_RESIGNATION_ESS_C3=off" in str(c3.rollback_guidance()))
    check("EN resignation", c3.status_label("resignation", lang="en") == "Resignation")
    check("AR notice", c3.status_label("notice_period", lang="ar") == "فترة الإشعار")
    check("assistant mutations out", c3.honesty_payload().get("assistant_mutations") is False)
    check("payroll not required", c3.honesty_payload().get("payroll_required") is False)
    check("offboarding not required", c3.honesty_payload().get("offboarding_required") is False)
    check("clearance not in c3", c3.honesty_payload().get("clearance_in_c3") is False)
    check("real termination dark", c3.honesty_payload().get("real_termination_dark") is True)
    check("real canary off", c3.real_termination_canary_on() is False)

    _flags(on="off", companies="")
    check("global off", c3.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(on="on", companies="")
    check("empty allowlist denies", "allowlist" in str(c3.runtime_gate_for_company(COMPANY).get("gate")))
    _flags(on="on", companies=COMPANY)
    check("canary allowlisted", c3.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant isolation", c3.runtime_gate_for_company(OTHER).get("ok") is not True)

    # Prove canary ON is refused by C3 module
    os.environ["WATHEFNI_REAL_TERMINATION_CANARY"] = "on"
    check("real canary blocked in C3", c3.assert_real_termination_dark().get("ok") is not True)
    os.environ["WATHEFNI_REAL_TERMINATION_CANARY"] = "off"

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    hire = date(2037, 6, 1)
    lwd = date(2040, 4, 30)
    contract_end = date(2040, 6, 30)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            c3.ensure_exit_intent_c3_schema(cur)
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"EX3 {COMPANY}"),
            )
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE
                  SET company_code=EXCLUDED.company_code, profile=EXCLUDED.profile,
                      employment_status='active', updated_at=now()
                """,
                (
                    COMPANY,
                    EMP,
                    EMP_PHONE,
                    "EX3 Emp",
                    hire,
                    hire,
                    json_profile(contract_end),
                ),
            )

            blocked = c3.create_resignation(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                actor_phone=EMP_PHONE,
                requested_last_working_day=lwd,
                reason="blocked",
            )
            check(
                "blocked while entitlement off",
                blocked.get("error") == "exit_intent_not_enabled",
                blocked,
            )

            en = c3.enable_company_exit_intent(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="canary enable exit intent",
                resignation_enabled=True,
                termination_enabled=True,
                eoc_enabled=True,
                notice_policy_days=30,
                notice_policy_source="company_setup",
                offboarding_handoff_enabled=False,
            )
            check("enable company", en.get("ok") is True, en)
            vis = c3.feature_visibility(cur, COMPANY)
            check("resignation visible", vis.get("resignation_visible") is True, vis)

            # --- Resignation submit / approve / reject / withdraw / stale ---
            r1 = c3.create_resignation(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                actor_phone=EMP_PHONE,
                requested_last_working_day=lwd,
                reason="personal",
            )
            check("employee resignation submit draft", r1.get("ok") is True, r1)
            rid = str((r1.get("case") or {}).get("case_id"))
            sub = c3.submit_case(
                cur, company_code=COMPANY, case_id=rid, actor_phone=EMP_PHONE, reason="submit resign",
                expected_version=int((r1.get("case") or {}).get("row_version") or 1),
            )
            check("resignation pending_approval", sub.get("ok") is True and (sub.get("case") or {}).get("status") == "pending_approval", sub)
            check(
                "submit does not mark left",
                _emp_status(cur) == "active",
            )

            sod = c3.approve_case(
                cur, company_code=COMPANY, case_id=rid, actor_phone=EMP_PHONE, reason="self",
                expected_version=int((sub.get("case") or {}).get("row_version") or 1),
            )
            check("resignation SoD self-approve forbidden", sod.get("error") == "sod_self_approve_forbidden", sod)

            stale = c3.approve_case(
                cur, company_code=COMPANY, case_id=rid, actor_phone=APPROVER, reason="stale",
                expected_version=0,
            )
            check("stale/concurrent decision", stale.get("error") == "stale_row_version", stale)

            appr = c3.approve_case(
                cur, company_code=COMPANY, case_id=rid, actor_phone=APPROVER, reason="ok resign",
                expected_version=int((sub.get("case") or {}).get("row_version") or 1),
            )
            check("resignation approve", appr.get("ok") is True and (appr.get("case") or {}).get("status") == "approved", appr)

            # Reject path on separate case
            r_rej = c3.create_resignation(
                cur, company_code=COMPANY, employee_key=EMP, actor_phone=EMP_PHONE,
                requested_last_working_day=lwd + timedelta(days=10), reason="reject me",
            )
            rjid = str((r_rej.get("case") or {}).get("case_id"))
            c3.submit_case(
                cur, company_code=COMPANY, case_id=rjid, actor_phone=EMP_PHONE, reason="s",
                expected_version=1,
            )
            cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (rjid,))
            rv_rj = int((cur.fetchone() or {}).get("row_version") or 1)
            rejected = c3.reject_case(
                cur, company_code=COMPANY, case_id=rjid, actor_phone=APPROVER, reason="not accepted",
                expected_version=rv_rj,
            )
            check("resignation reject", rejected.get("ok") is True and (rejected.get("case") or {}).get("status") == "rejected", rejected)

            # Permitted withdrawal before notice
            r_w = c3.create_resignation(
                cur, company_code=COMPANY, employee_key=EMP, actor_phone=EMP_PHONE,
                requested_last_working_day=lwd + timedelta(days=20), reason="withdraw me",
            )
            wid = str((r_w.get("case") or {}).get("case_id"))
            c3.submit_case(
                cur, company_code=COMPANY, case_id=wid, actor_phone=EMP_PHONE, reason="s",
                expected_version=1,
            )
            cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (wid,))
            rv_w = int((cur.fetchone() or {}).get("row_version") or 1)
            withdrawn = c3.withdraw_case(
                cur, company_code=COMPANY, case_id=wid, actor_phone=EMP_PHONE, reason="changed mind",
                expected_version=rv_w,
            )
            check("permitted withdrawal", withdrawn.get("ok") is True and (withdrawn.get("case") or {}).get("status") == "withdrawn", withdrawn)

            # Notice + ready on approved resignation
            notice = c3.enter_notice_period(
                cur,
                company_code=COMPANY,
                case_id=rid,
                actor_phone=HR_PHONE,
                reason="start notice",
                last_working_day=lwd,
                expected_version=int((appr.get("case") or {}).get("row_version") or 1),
            )
            check("notice period entered", notice.get("ok") is True and (notice.get("case") or {}).get("status") == "notice_period", notice)
            check("employment still active in notice", notice.get("employment_still_active") is True, notice)

            # Withdraw blocked after notice (irreversible boundary)
            bad_w = c3.withdraw_case(
                cur, company_code=COMPANY, case_id=rid, actor_phone=EMP_PHONE, reason="too late",
            )
            check("withdraw blocked after notice", bad_w.get("error") == "withdraw_past_irreversible_boundary", bad_w)

            amd = c3.amend_notice(
                cur,
                company_code=COMPANY,
                case_id=rid,
                actor_phone=HR_PHONE,
                reason="extend lwd",
                notice_starts_on=date.today(),
                notice_ends_on=date.today() + timedelta(days=45),
                last_working_day=lwd + timedelta(days=5),
            )
            check("notice dates/change audit", amd.get("ok") is True and int((amd.get("notice_version") or {}).get("version_number") or 0) == 2, amd)
            vers = c3.list_notice_versions(cur, case_id=rid)
            check("notice versions retained", len(vers) >= 2, len(vers))

            ready = c3.mark_ready_for_offboarding(
                cur,
                company_code=COMPANY,
                case_id=rid,
                actor_phone=HR_PHONE,
                reason="handoff boundary",
                expected_version=int((amd.get("case") or {}).get("row_version") or 1),
            )
            check("ready_for_offboarding", ready.get("ok") is True and (ready.get("case") or {}).get("status") == "ready_for_offboarding", ready)
            check("no premature employment=left", _emp_status(cur) == "active" and ready.get("employment_closed") is False, ready)
            check("handoff without Offboarding", (ready.get("handoff") or {}).get("ok") is True, ready)
            check(
                "handoff deferred when Offboarding absent",
                ((ready.get("handoff") or {}).get("handoff") or {}).get("status") == "deferred",
                ready,
            )
            check("not clearance/paid", ready.get("clearance_complete") is False and ready.get("employee_paid") is False, ready)

            # Employee status visibility
            listed = c3.list_cases_for_employee(cur, company_code=COMPANY, employee_key=EMP)
            check("employee sees canonical status", listed.get("ok") is True and any(c.get("case_id") == uuid.UUID(rid) or str(c.get("case_id")) == rid for c in (listed.get("cases") or [])), listed)

            # --- Termination HR + SoD / reject / cancel ---
            t1 = c3.create_termination(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                actor_phone=HR_PHONE,
                reason="role eliminated",
                reason_category="redundancy",
                effective_last_working_day=lwd + timedelta(days=60),
                hr_authorized=True,
            )
            check("employer termination initiation", t1.get("ok") is True, t1)
            tid = str((t1.get("case") or {}).get("case_id"))
            c3.submit_case(
                cur, company_code=COMPANY, case_id=tid, actor_phone=HR_PHONE, reason="submit term",
                expected_version=1,
            )
            cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (tid,))
            rv_t = int((cur.fetchone() or {}).get("row_version") or 1)
            t_sod = c3.approve_case(
                cur, company_code=COMPANY, case_id=tid, actor_phone=HR_PHONE, reason="self hr",
                expected_version=rv_t,
            )
            check("termination SoD", t_sod.get("error") == "sod_self_approve_forbidden", t_sod)
            t_appr = c3.approve_case(
                cur, company_code=COMPANY, case_id=tid, actor_phone=APPROVER, reason="approve term",
                expected_version=rv_t,
            )
            check("termination approve", t_appr.get("ok") is True, t_appr)

            t_rej = c3.create_termination(
                cur, company_code=COMPANY, employee_key=EMP, actor_phone=HR_PHONE,
                reason="reject path", reason_category="other",
                effective_last_working_day=lwd + timedelta(days=70),
            )
            trid = str((t_rej.get("case") or {}).get("case_id"))
            c3.submit_case(cur, company_code=COMPANY, case_id=trid, actor_phone=HR_PHONE, reason="s", expected_version=1)
            cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (trid,))
            rv_tr = int((cur.fetchone() or {}).get("row_version") or 1)
            t_rejected = c3.reject_case(
                cur, company_code=COMPANY, case_id=trid, actor_phone=APPROVER, reason="no",
                expected_version=rv_tr,
            )
            check("termination reject", t_rejected.get("ok") is True, t_rejected)

            t_can = c3.create_termination(
                cur, company_code=COMPANY, employee_key=EMP, actor_phone=HR_PHONE,
                reason="cancel path", reason_category="other",
                effective_last_working_day=lwd + timedelta(days=80),
            )
            tcid = str((t_can.get("case") or {}).get("case_id"))
            cancelled = c3.cancel_case(
                cur, company_code=COMPANY, case_id=tcid, actor_phone=HR_PHONE, reason="abort",
                expected_version=1,
            )
            check("termination cancel", cancelled.get("ok") is True and (cancelled.get("case") or {}).get("status") == "cancelled", cancelled)

            # Non-HR termination blocked
            no_hr = c3.create_termination(
                cur, company_code=COMPANY, employee_key=EMP, actor_phone=EMP_PHONE,
                reason="x", reason_category="other", effective_last_working_day=lwd,
                hr_authorized=False,
            )
            check("termination requires HR auth", no_hr.get("error") == "hr_authorization_required", no_hr)

            # --- EOC renewal ---
            eoc_r = c3.create_eoc_case(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                actor_phone=HR_PHONE,
                contract_end_date=contract_end,
            )
            check("EOC case + task", eoc_r.get("ok") is True and bool(eoc_r.get("task")), eoc_r)
            erid = str((eoc_r.get("case") or {}).get("case_id"))
            renewed = c3.decide_eoc_renewal(
                cur,
                company_code=COMPANY,
                case_id=erid,
                actor_phone=APPROVER,
                reason="renew 1 year",
                renewed_contract_end=contract_end + timedelta(days=365),
                expected_version=1,
            )
            check("EOC renewal", renewed.get("ok") is True and renewed.get("eoc_decision") == "renewed", renewed)
            check("EOC renewal keeps employment active", renewed.get("employment_still_active") is True, renewed)
            check("EOC not silent termination", renewed.get("silent_expiry_treated_as_termination") is False, renewed)

            # --- EOC non-renewal → notice → ready ---
            eoc_n = c3.create_eoc_case(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                actor_phone=HR_PHONE,
                contract_end_date=contract_end + timedelta(days=400),
            )
            enid = str((eoc_n.get("case") or {}).get("case_id"))
            non = c3.decide_eoc_non_renewal(
                cur, company_code=COMPANY, case_id=enid, actor_phone=HR_PHONE, reason="do not renew",
                expected_version=1,
            )
            check("EOC non-renewal", non.get("ok") is True and non.get("eoc_decision") == "non_renewed", non)
            cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (enid,))
            rv_en = int((cur.fetchone() or {}).get("row_version") or 1)
            c3.submit_case(
                cur, company_code=COMPANY, case_id=enid, actor_phone=HR_PHONE, reason="submit eoc",
                expected_version=rv_en,
            )
            cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (enid,))
            rv_en2 = int((cur.fetchone() or {}).get("row_version") or 1)
            c3.approve_case(
                cur, company_code=COMPANY, case_id=enid, actor_phone=APPROVER, reason="approve eoc",
                expected_version=rv_en2,
            )
            cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (enid,))
            rv_en3 = int((cur.fetchone() or {}).get("row_version") or 1)
            eoc_notice = c3.enter_notice_period(
                cur, company_code=COMPANY, case_id=enid, actor_phone=HR_PHONE, reason="eoc notice",
                last_working_day=contract_end + timedelta(days=400),
                expected_version=rv_en3,
            )
            check("EOC non-renewal notice", eoc_notice.get("ok") is True, eoc_notice)
            cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (enid,))
            rv_en4 = int((cur.fetchone() or {}).get("row_version") or 1)
            eoc_ready = c3.mark_ready_for_offboarding(
                cur, company_code=COMPANY, case_id=enid, actor_phone=HR_PHONE, reason="eoc ready",
                expected_version=rv_en4,
            )
            check("EOC ready_for_offboarding", eoc_ready.get("ok") is True, eoc_ready)
            check("still not employment=left after EOC ready", _emp_status(cur) == "active")

            # Non-synthetic blocked
            real_blocked = c3.create_resignation(
                cur,
                company_code=COMPANY,
                employee_key=f"{COMPANY}-REAL-PERSON",
                actor_phone=EMP_PHONE,
                requested_last_working_day=lwd,
                reason="real",
            )
            check("non-synthetic blocked", real_blocked.get("error") == "non_synthetic_employee_blocked", real_blocked)

            # Legal pack invent refused
            bad_pack = c3.enable_company_exit_intent(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="bad pack",
                notice_policy_source="legal_pack",
                legal_pack_ref=None,
            )
            check("no invented legal pack notice", bad_pack.get("error") == "legal_pack_ref_required", bad_pack)

            src = Path(__file__).with_name("exit_intent_c3.py").read_text()
            check("independent of payroll module", "payroll_authority" not in src and "payroll_settlement" not in src)
            check("independent of offboarding module", "offboarding_c4" not in src)
            check("EN/AR contracts present", "status_label_ar" in src and "فترة الإشعار" in src)

            # Re-enable after bad_pack attempt may have failed without changing — ensure still enabled then disable
            c3.enable_company_exit_intent(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="restore before rollback",
                resignation_enabled=True,
                termination_enabled=True,
                eoc_enabled=True,
            )
            off = c3.disable_company_exit_intent(
                cur, company_code=COMPANY, actor_phone=HR_PHONE, reason="rollback"
            )
            check("disable preserves history flag", off.get("history_preserved") is True, off)
            check(
                "module-off after disable",
                c3.module_enabled_for_company(cur, COMPANY).get("ok") is not True,
            )
            cur.execute(
                "SELECT count(*) AS c FROM exit_intent_cases WHERE company_code=%s AND employee_key=%s",
                (COMPANY, EMP),
            )
            check("history intact after rollback", int((cur.fetchone() or {}).get("c") or 0) >= 3)
            cur.execute(
                "SELECT count(*) AS c FROM exit_intent_notice_versions WHERE company_code=%s",
                (COMPANY,),
            )
            check("notice history intact", int((cur.fetchone() or {}).get("c") or 0) >= 2)
            check("global real-termination gate remains OFF", c3.real_termination_canary_on() is False)
            check("employment truth active after full path", _emp_status(cur) == "active")

        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("RESIGNATION_TERMINATION_UNIT_PASS")
    print("RESIGNATION_TERMINATION_FULL_PASS")
    return 0


def json_profile(contract_end: date) -> str:
    import json

    return json.dumps(
        {
            "department": "Ops",
            "position_title": "Analyst",
            "contract_end_date": contract_end.isoformat(),
        }
    )


def _emp_status(cur) -> str:
    cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (EMP,))
    row = cur.fetchone()
    return str((row or {}).get("employment_status") or "")


if __name__ == "__main__":
    raise SystemExit(main())
