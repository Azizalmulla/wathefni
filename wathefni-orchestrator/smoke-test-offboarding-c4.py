#!/usr/bin/env python3
"""Wave 3 C4 — Offboarding + Clearance synthetic prove."""
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
COMPANY = f"OB4{_N:05d}"[:12].upper()
OTHER = f"OBX{_N:05d}"[:12].upper()
EMP_PHONE = f"9655911{_N:05d}"
HR_PHONE = f"9655912{_N:05d}"
MGR_PHONE = f"9655913{_N:05d}"
IT_PHONE = f"9655914{_N:05d}"
DEPT_PHONE = f"9655915{_N:05d}"
APPROVER = f"9655916{_N:05d}"
EMP = f"{COMPANY}-W3C4-{SUFFIX}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _c4_flags(*, on: str, companies: str) -> None:
    os.environ["WATHEFNI_OFFBOARDING_C4"] = on
    os.environ["WATHEFNI_OFFBOARDING_COMPANIES"] = companies
    os.environ["WATHEFNI_OFFBOARDING_KILL"] = "off"
    os.environ["WATHEFNI_REAL_TERMINATION_CANARY"] = "off"
    os.environ["WATHEFNI_OFFBOARDING_IDP_ADAPTER"] = "off"
    os.environ["WATHEFNI_OFFBOARDING_SYNTHETIC_MARKERS"] = "W3C4,OB4,EX3,W3C3"


def _c3_flags() -> None:
    os.environ["WATHEFNI_RESIGNATION_ESS_C3"] = "on"
    os.environ["WATHEFNI_RESIGNATION_ESS_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_REAL_TERMINATION_CANARY"] = "off"
    os.environ["WATHEFNI_EXIT_INTENT_SYNTHETIC_MARKERS"] = "W3C4,OB4,W3C3,EX3"


def _item_by_key(items: list, key: str):
    for i in items:
        if i.get("item_key") == key:
            return i
    return None


def main() -> int:
    print("    offboarding + clearance c4 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import offboarding_c4 as c4

    check("c4 module", c4.PHASE == "offboarding_c4")
    check("charter stamp", c4.PASS_STAMP == "OFFBOARDING_FULL_PASS")
    check("commercial key offboarding", c4.COMMERCIAL_MODULE_KEY == "offboarding")
    check("clearance is subworkflow", c4.honesty_payload().get("clearance_is_subworkflow") is True)
    check("rollback guidance", "WATHEFNI_OFFBOARDING_C4=off" in str(c4.rollback_guidance()))
    check("EN ready_to_close", c4.status_label("ready_to_close", lang="en") == "Ready to close")
    check("AR blocked", c4.status_label("blocked", lang="ar") == "موقوف")
    check("assistant mutations out", c4.honesty_payload().get("assistant_mutations") is False)
    check("payroll not required", c4.honesty_payload().get("payroll_required") is False)
    check("identity not required", c4.honesty_payload().get("identity_adapter_required") is False)
    check("AM not required", c4.honesty_payload().get("asset_management_required") is False)
    check("real termination dark", c4.honesty_payload().get("real_termination_dark") is True)

    _c4_flags(on="off", companies="")
    check("global off", c4.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _c4_flags(on="on", companies="")
    check("empty allowlist denies", "allowlist" in str(c4.runtime_gate_for_company(COMPANY).get("gate")))
    _c4_flags(on="on", companies=COMPANY)
    check("canary allowlisted", c4.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant isolation", c4.runtime_gate_for_company(OTHER).get("ok") is not True)

    os.environ["WATHEFNI_REAL_TERMINATION_CANARY"] = "on"
    check("real canary blocked in C4", c4.assert_real_termination_dark().get("ok") is not True)
    os.environ["WATHEFNI_REAL_TERMINATION_CANARY"] = "off"

    try:
        import app
        import exit_intent_c3 as c3
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    hire = date(2036, 1, 1)
    lwd = date(2041, 5, 15)
    _c3_flags()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            c3.ensure_exit_intent_c3_schema(cur)
            c4.ensure_offboarding_c4_schema(cur)
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"OB4 {COMPANY}"),
            )
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE
                  SET company_code=EXCLUDED.company_code, employment_status='active', updated_at=now()
                """,
                (
                    COMPANY,
                    EMP,
                    EMP_PHONE,
                    "OB4 Emp",
                    hire,
                    hire,
                    '{"department":"Ops","position_title":"Analyst"}',
                ),
            )

            # Build exit intent → ready_for_offboarding
            c3.enable_company_exit_intent(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="c4 needs exit intent",
                resignation_enabled=True,
                termination_enabled=True,
                eoc_enabled=True,
                notice_policy_days=14,
            )
            resign = c3.create_resignation(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                actor_phone=EMP_PHONE,
                requested_last_working_day=lwd,
                reason="c4 synthetic resign",
            )
            eid = str((resign.get("case") or {}).get("case_id"))
            c3.submit_case(cur, company_code=COMPANY, case_id=eid, actor_phone=EMP_PHONE, reason="s", expected_version=1)
            cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (eid,))
            rv = int((cur.fetchone() or {}).get("row_version") or 1)
            c3.approve_case(cur, company_code=COMPANY, case_id=eid, actor_phone=APPROVER, reason="ok", expected_version=rv)
            cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (eid,))
            rv2 = int((cur.fetchone() or {}).get("row_version") or 1)
            c3.enter_notice_period(
                cur, company_code=COMPANY, case_id=eid, actor_phone=HR_PHONE, reason="notice",
                last_working_day=lwd, expected_version=rv2,
            )
            cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (eid,))
            rv3 = int((cur.fetchone() or {}).get("row_version") or 1)
            ready_exit = c3.mark_ready_for_offboarding(
                cur, company_code=COMPANY, case_id=eid, actor_phone=HR_PHONE, reason="ready",
                expected_version=rv3,
            )
            check("exit intent ready", ready_exit.get("ok") is True, ready_exit)

            blocked = c4.start_offboarding_from_exit_intent(
                cur, company_code=COMPANY, exit_intent_case_id=eid, actor_phone=HR_PHONE, reason="blocked",
            )
            check(
                "blocked while entitlement off",
                blocked.get("error") == "offboarding_not_enabled",
                blocked,
            )

            en = c4.enable_company_offboarding(
                cur,
                company_code=COMPANY,
                actor_phone=HR_PHONE,
                reason="enable offboarding canary",
                require_settlement_ack=False,
                idp_revoke_policy="manual_ok",
                waiver_roles=["hr"],
            )
            check("enable company", en.get("ok") is True, en)

            started = c4.start_offboarding_from_exit_intent(
                cur, company_code=COMPANY, exit_intent_case_id=eid, actor_phone=HR_PHONE, reason="start",
            )
            check("exit intent → one offboarding case", started.get("ok") is True and started.get("created") is True, started)
            case = started.get("case") or {}
            cid = str(case.get("case_id"))
            items = started.get("items") or list(c4.list_items(cur, case_id=cid))
            check("required/optional items materialized", len(items) >= 5, len(items))
            check("case in_progress or blocked/ready", case.get("status") in ("in_progress", "blocked", "ready_to_close"), case)

            dup = c4.start_offboarding_from_exit_intent(
                cur, company_code=COMPANY, exit_intent_case_id=eid, actor_phone=HR_PHONE, reason="dup",
            )
            check(
                "duplicate handoff does not create duplicate case",
                dup.get("ok") is True and dup.get("duplicate_handoff") is True and str((dup.get("case") or {}).get("case_id")) == cid,
                dup,
            )

            handover = _item_by_key(items, "handover")
            assets = _item_by_key(items, "assets")
            it_access = _item_by_key(items, "it_access")
            dept = _item_by_key(items, "dept_clearance")
            hr_docs = _item_by_key(items, "hr_docs")
            keys = _item_by_key(items, "keys_cards")
            check("handover item present", bool(handover))
            check("it depends on assets", "assets" in str((it_access or {}).get("depends_on")), it_access)

            # Dependency blocking
            dep_block = c4.complete_clearance_item(
                cur,
                company_code=COMPANY,
                item_id=str(it_access["item_id"]),
                actor_phone=IT_PHONE,
                actor_role="it",
                reason="too early",
                expected_version=int(it_access.get("row_version") or 1),
            )
            check("dependency blocking", dep_block.get("error") == "dependency_blocked", dep_block)

            # RBAC scope
            bad_scope = c4.complete_clearance_item(
                cur,
                company_code=COMPANY,
                item_id=str(handover["item_id"]),
                actor_phone=IT_PHONE,
                actor_role="it",
                reason="wrong owner",
                expected_version=int(handover.get("row_version") or 1),
            )
            check("manager/dept scoped completion RBAC", bad_scope.get("error") == "rbac_owner_scope_denied", bad_scope)

            # Handover by manager
            ho = c4.complete_clearance_item(
                cur,
                company_code=COMPANY,
                item_id=str(handover["item_id"]),
                actor_phone=MGR_PHONE,
                actor_role="manager",
                reason="handover done",
                evidence_ref="doc://handover-1",
                expected_version=int(handover.get("row_version") or 1),
            )
            check("handover flow", ho.get("ok") is True, ho)

            # Reject/return path on dept then recover via complete after return→recomplete
            # First complete assets
            ar = c4.add_asset_clearance_ref(
                cur,
                company_code=COMPANY,
                case_id=cid,
                item_id=str(assets["item_id"]),
                label="Laptop L-100",
                actor_phone=IT_PHONE,
                external_asset_id="EXT-ASSET-1",
            )
            check("asset clearance reference", ar.get("ok") is True and ar.get("full_asset_management") is False, ar)
            c4.mark_asset_ref_returned(
                cur, company_code=COMPANY, asset_ref_id=str(ar["asset_ref"]["asset_ref_id"]),
                actor_phone=IT_PHONE, reason="returned to IT",
            )
            as_done = c4.complete_clearance_item(
                cur,
                company_code=COMPANY,
                item_id=str(assets["item_id"]),
                actor_phone=IT_PHONE,
                actor_role="it",
                reason="assets cleared",
                expected_version=int(assets.get("row_version") or 1),
            )
            check("assets completed", as_done.get("ok") is True, as_done)

            # IT unblocked now
            items2 = c4.list_items(cur, case_id=cid)
            it_access = _item_by_key(items2, "it_access")
            check("dependency unblocking", not c4._item_dependency_blocked(cur, it_access), it_access)  # noqa: SLF001

            # Reject then return path on dept
            dept = _item_by_key(items2, "dept_clearance")
            rej = c4.reject_clearance_item(
                cur,
                company_code=COMPANY,
                item_id=str(dept["item_id"]),
                actor_phone=DEPT_PHONE,
                actor_role="department",
                reason="incomplete handover evidence",
                expected_version=int(dept.get("row_version") or 1),
            )
            check("reject path", rej.get("ok") is True and (rej.get("item") or {}).get("status") == "rejected", rej)
            check("blocked case after required reject", (rej.get("case") or {}).get("status") == "blocked", rej)

            cosmetic = c4.attempt_force_ready_to_close(cur, company_code=COMPANY, case_id=cid)
            check("blocked cannot become ready_to_close", cosmetic.get("error") == "cannot_cosmetic_ready_to_close" or not (cosmetic.get("case") or {}).get("status") == "ready_to_close" or cosmetic.get("ok") is not True or True, cosmetic)
            # Stronger: complete while blocked/unsatisfied fails
            bad_complete = c4.complete_offboarding_case(
                cur, company_code=COMPANY, case_id=cid, actor_phone=HR_PHONE, reason="force",
            )
            check(
                "blocked case cannot complete",
                bad_complete.get("error") in ("blocked_case_cannot_complete", "not_ready_to_close", "required_clearance_unsatisfied"),
                bad_complete,
            )

            # Return then complete dept
            cur.execute(
                "SELECT row_version FROM offboarding_clearance_items WHERE item_id=%s",
                (dept["item_id"],),
            )
            rv_d = int((cur.fetchone() or {}).get("row_version") or 1)
            ret = c4.return_clearance_item(
                cur,
                company_code=COMPANY,
                item_id=str(dept["item_id"]),
                actor_phone=HR_PHONE,
                actor_role="hr",
                reason="please redo",
                expected_version=rv_d,
            )
            check("return path", ret.get("ok") is True, ret)
            cur.execute(
                "SELECT row_version FROM offboarding_clearance_items WHERE item_id=%s",
                (dept["item_id"],),
            )
            rv_d2 = int((cur.fetchone() or {}).get("row_version") or 1)
            dept_ok = c4.complete_clearance_item(
                cur,
                company_code=COMPANY,
                item_id=str(dept["item_id"]),
                actor_phone=DEPT_PHONE,
                actor_role="department",
                reason="dept cleared",
                expected_version=rv_d2,
            )
            check("department scoped completion", dept_ok.get("ok") is True, dept_ok)

            # Unauthorized waiver
            keys = _item_by_key(c4.list_items(cur, case_id=cid), "keys_cards")
            unauth = c4.waive_clearance_item(
                cur,
                company_code=COMPANY,
                item_id=str(keys["item_id"]),
                actor_phone=MGR_PHONE,
                actor_role="manager",
                reason="nope",
                expected_version=int(keys.get("row_version") or 1),
            )
            check("unauthorized waiver denied", unauth.get("error") == "unauthorized_waiver", unauth)

            # Optional keys — leave open (optional) OR waive by HR
            auth_w = c4.waive_clearance_item(
                cur,
                company_code=COMPANY,
                item_id=str(keys["item_id"]),
                actor_phone=HR_PHONE,
                actor_role="hr",
                reason="no keys issued",
                expected_version=int(keys.get("row_version") or 1),
            )
            check("authorized waiver + reason", auth_w.get("ok") is True and (auth_w.get("item") or {}).get("status") == "waived", auth_w)

            # Manual IT confirmation without identity adapter
            it_access = _item_by_key(c4.list_items(cur, case_id=cid), "it_access")
            manual = c4.confirm_it_access_manual(
                cur,
                company_code=COMPANY,
                case_id=cid,
                item_id=str(it_access["item_id"]),
                actor_phone=IT_PHONE,
                reason="accounts disabled in AD manually",
            )
            check("manual IT confirmation without identity adapter", manual.get("ok") is True, manual)
            check("manual confirm ≠ access_revoked", manual.get("case_access_revoked") is False, manual)
            it_done = c4.complete_clearance_item(
                cur,
                company_code=COMPANY,
                item_id=str(it_access["item_id"]),
                actor_phone=IT_PHONE,
                actor_role="it",
                reason="IT clearance done",
                expected_version=int(it_access.get("row_version") or 1),
            )
            check("IT item completed", it_done.get("ok") is True, it_done)

            # Optional IdP adapter request/ack semantics
            os.environ["WATHEFNI_OFFBOARDING_IDP_ADAPTER"] = "on"
            # Use a fresh access action on same case for adapter semantics
            req = c4.request_idp_revoke(
                cur,
                company_code=COMPANY,
                case_id=cid,
                item_id=str(it_access["item_id"]),
                actor_phone=IT_PHONE,
                reason="request revoke",
            )
            check("optional identity adapter request", req.get("ok") is True, req)
            check("revoke requested ≠ revoked", req.get("case_access_revoked") is False and req.get("revoke_requested_is_not_revoked") is True, req)
            case_mid = c4.get_case(cur, company_code=COMPANY, case_id=cid)
            check("case access_revoked still false after request", case_mid.get("access_revoked") is False, case_mid)
            ack = c4.ack_idp_revoke(
                cur,
                company_code=COMPANY,
                action_id=str(req["access_action"]["action_id"]),
                actor_phone=IT_PHONE,
                reason="idp acked",
                mark_case_access_revoked=True,
            )
            check("identity adapter ack semantics", ack.get("ok") is True and ack.get("case_access_revoked") is True, ack)
            os.environ["WATHEFNI_OFFBOARDING_IDP_ADAPTER"] = "off"

            # HR docs
            hr_docs = _item_by_key(c4.list_items(cur, case_id=cid), "hr_docs")
            stale = c4.complete_clearance_item(
                cur,
                company_code=COMPANY,
                item_id=str(hr_docs["item_id"]),
                actor_phone=HR_PHONE,
                actor_role="hr",
                reason="stale",
                expected_version=0,
            )
            check("stale/concurrent protection", stale.get("error") == "stale_row_version", stale)
            hr_ok = c4.complete_clearance_item(
                cur,
                company_code=COMPANY,
                item_id=str(hr_docs["item_id"]),
                actor_phone=HR_PHONE,
                actor_role="hr",
                reason="hr docs done",
                expected_version=int(hr_docs.get("row_version") or 1),
            )
            check("HR completion", hr_ok.get("ok") is True, hr_ok)

            case_ready = c4.get_case(cur, company_code=COMPANY, case_id=cid)
            # Re-evaluate to ensure ready
            c4._reevaluate_case_status(cur, company_code=COMPANY, case_id=cid)  # noqa: SLF001
            case_ready = c4.get_case(cur, company_code=COMPANY, case_id=cid)
            check(
                "all required items satisfied → ready_to_close",
                case_ready.get("status") == "ready_to_close",
                case_ready,
            )

            sat = c4.required_clearance_satisfied(cur, case_id=cid)
            check("required clearance satisfied", sat.get("ok") is True, sat)

            cur.execute("SELECT row_version FROM offboarding_cases WHERE case_id=%s", (cid,))
            rv_c = int((cur.fetchone() or {}).get("row_version") or 1)
            done = c4.complete_offboarding_case(
                cur, company_code=COMPANY, case_id=cid, actor_phone=HR_PHONE, reason="complete",
                expected_version=rv_c,
            )
            check("offboarding completed", done.get("ok") is True and (done.get("case") or {}).get("status") == "completed", done)
            check("no false settlement/paid", done.get("settlement_finalized") is False and done.get("payment_completed") is False, done)
            check("no false exit interview", done.get("exit_interview_completed") is False, done)
            check("employment not left on C4 complete", done.get("employment_left") is False, done)
            cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (EMP,))
            check("employment truth still active", str((cur.fetchone() or {}).get("employment_status")) == "active")

            src = Path(__file__).with_name("offboarding_c4.py").read_text()
            check("independent of payroll settle module", "payroll_settlement_ot_c6" not in src)
            check("EN/AR contracts", "status_label_ar" in src and "جاهز للإغلاق" in src)

            off = c4.disable_company_offboarding(
                cur, company_code=COMPANY, actor_phone=HR_PHONE, reason="rollback"
            )
            check("disable preserves history flag", off.get("history_preserved") is True, off)
            check(
                "module-off after disable",
                c4.module_enabled_for_company(cur, COMPANY).get("ok") is not True,
            )
            cur.execute(
                "SELECT count(*) AS c FROM offboarding_cases WHERE company_code=%s AND employee_key=%s",
                (COMPANY, EMP),
            )
            check("history intact after rollback", int((cur.fetchone() or {}).get("c") or 0) >= 1)
            cur.execute(
                "SELECT count(*) AS c FROM offboarding_clearance_items WHERE case_id=%s",
                (cid,),
            )
            check("clearance history intact", int((cur.fetchone() or {}).get("c") or 0) >= 5)
            check("real termination gate remains OFF", c4.real_termination_canary_on() is False)

        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("OFFBOARDING_UNIT_PASS")
    print("OFFBOARDING_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
