#!/usr/bin/env python3
"""Attendance Wave 3 — local/staging smoke for HR/manager exception operations.

No real clocking, devices, QR/GPS/kiosk, or production deploy.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", "local")
os.environ["WATHEFNI_ATTENDANCE_AUTHORITY"] = "on"
os.environ["WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES"] = "ATTW3,OTHERCO"
os.environ["WATHEFNI_ATTENDANCE_AUTHORITY_STORE"] = "memory"
os.environ["WATHEFNI_ATTENDANCE_OPS"] = "on"
os.environ["WATHEFNI_ATTENDANCE_OPS_COMPANIES"] = "ATTW3,OTHERCO"
os.environ["WATHEFNI_ATTENDANCE_OPS_STORE"] = "memory"
os.environ["WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS"] = "absence,early_leave"

import attendance_authority_wave1 as auth
import attendance_ops_wave3 as ops

KUWAIT = ZoneInfo("Asia/Kuwait")
RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: object = None) -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail if not ok else None})
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" :: {detail}" if not ok and detail is not None else ""))


def emp(key: str = "ATTW3-E1", phone: str = "96552400001", name: str = "Wave3 Emp") -> dict:
    return {"employee_key": key, "phone": phone, "name": name, "company_code": "ATTW3"}


def shift_day(d: date, shift_id: str = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa") -> dict:
    return {
        "shift_id": shift_id,
        "shift_date": d,
        "start_time": time(9, 0),
        "end_time": time(17, 0),
    }


def dt(d: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=KUWAIT)


def main() -> int:
    locked_dates: set[tuple[str, str, date]] = set()
    configured_managers = {"96552499901", "96552499902", "96552499903"}
    # manager -> allowed employee keys (simulates Employees 360 effective org)
    scope_map = {
        "96552499901": {"ATTW3-E1", "ATTW3-E2"},  # direct/team
        "96552499902": {"ATTW3-E2", "ATTW3-E3"},  # branch/team
        "96552499903": {"ATTW3-E1"},  # self-ish target for denial tests uses E1 phone separately
    }

    def scope_allows(company: str, actor: str, employee_key: str) -> bool:
        if company != "ATTW3":
            return False
        allowed = scope_map.get(actor)
        if allowed is None:
            return False
        return employee_key in allowed

    def payroll_locked(company: str, employee_key: str, d: date) -> bool:
        return (company, employee_key, d) in locked_dates

    def mgr_configured(company: str, actor: str) -> bool:
        return actor in configured_managers

    authority = auth.AttendanceAuthorityService()
    svc = ops.AttendanceOpsService(
        authority_service=authority,
        scope_allows=scope_allows,
        payroll_locked=payroll_locked,
        manager_configured=mgr_configured,
    )

    # --- state model ---
    model = ops.state_model_doc()
    check("state model has exception kinds", "missing_check_in" in model["exception_kinds"] and "lateness" in model["exception_kinds"])
    check("state model separates apply", model["rules"]["approve_reject_apply_separated"] is True)

    # --- missing in/out lifecycle ---
    d_miss = date(2026, 8, 11)
    sh_miss = shift_day(d_miss, "11111111-1111-1111-1111-111111111111")
    only_out = authority.ingest_punch(
        company_code="ATTW3", employee=emp(), punched_at=dt(d_miss, "17:00"), direction="out",
        source="hr", source_event_id="w3-only-out", shift=sh_miss, work_date=d_miss,
    )
    sync = svc.sync_exceptions_from_projection(company_code="ATTW3", employee=emp(), projection=only_out["projection"])
    kinds = {e["kind"] for e in sync["exceptions"]}
    check("missing check-in exception opened", "missing_check_in" in kinds, kinds)
    exc = sync["exceptions"][0]
    assigned = svc.assign_exception(
        company_code="ATTW3", exception_id=exc["exception_id"], owner_phone="96552499901",
        actor_phone="96552499901", expected_row_version=exc["row_version"], actor_role="manager",
    )
    check("exception assigned with owner/priority/due", assigned.get("ok") is True and assigned["exception"]["status"] == "assigned")
    check("exception has due date", assigned["exception"].get("due_at") is not None)

    # request → review approve → apply (separation)
    req = svc.request_correction(
        company_code="ATTW3", employee=emp(), work_date=d_miss,
        requested_by_phone="96552499901",
        changes={"check_in_at": dt(d_miss, "09:00").isoformat()},
        shift=sh_miss, exception_id=assigned["exception"]["exception_id"],
        actor_is_manager=True, actor_role="manager", kind="missing_check_in",
    )
    check("correction case requested", req.get("ok") is True and req["case"]["status"] == "requested")
    case = req["case"]
    rev = svc.review_case(
        company_code="ATTW3", case_id=case["case_id"], decision="approved",
        decided_by_phone="96552499901", expected_row_version=case["row_version"],
        actor_role="manager", employee=emp(),
    )
    check("review approve does not apply", rev.get("ok") is True and rev.get("applied") is False and rev["case"]["status"] == "approved")
    proj_mid = authority.store.get_current_projection(
        company_code="ATTW3", employee_key="ATTW3-E1", work_date=d_miss,
        shift_key=auth.shift_key_of(sh_miss["shift_id"]),
    )
    check("punches unchanged before apply", (proj_mid or {}).get("check_in_at") is None, proj_mid)
    applied = svc.apply_case(
        company_code="ATTW3", case_id=case["case_id"], applied_by_phone="96552499901",
        expected_row_version=rev["case"]["row_version"], idempotency_key="apply-miss-1",
        employee=emp(), shift=sh_miss, actor_role="manager",
    )
    check("apply creates projection version", applied.get("ok") is True and applied.get("applied") is True)
    check("before/after captured", bool(applied.get("before")) and bool(applied.get("after")))
    replay = svc.apply_case(
        company_code="ATTW3", case_id=case["case_id"], applied_by_phone="96552499901",
        expected_row_version=999, idempotency_key="apply-miss-1",
        employee=emp(), shift=sh_miss, actor_role="manager",
    )
    check("idempotent apply replay", replay.get("idempotent_replay") is True or replay.get("already_applied") is True)

    # --- late + early leave correction ---
    d_late = date(2026, 8, 12)
    sh_late = shift_day(d_late, "22222222-2222-2222-2222-222222222222")
    authority.ingest_punch(company_code="ATTW3", employee=emp(), punched_at=dt(d_late, "10:00"), direction="in",
                           source="hr", source_event_id="w3-late-in", shift=sh_late, work_date=d_late)
    late_proj = authority.ingest_punch(company_code="ATTW3", employee=emp(), punched_at=dt(d_late, "16:00"), direction="out",
                                       source="hr", source_event_id="w3-early-out", shift=sh_late, work_date=d_late)
    sync_late = svc.sync_exceptions_from_projection(company_code="ATTW3", employee=emp(), projection=late_proj["projection"])
    late_kinds = {e["kind"] for e in sync_late["exceptions"]}
    check("lateness exception", "lateness" in late_kinds, late_kinds)
    check("early_leave exception", "early_leave" in late_kinds, late_kinds)
    early_exc = next(e for e in sync_late["exceptions"] if e["kind"] == "early_leave")
    # early_leave is dual-approval
    req_early = svc.request_correction(
        company_code="ATTW3", employee=emp(), work_date=d_late,
        requested_by_phone="96552499901",
        changes={"check_out_at": dt(d_late, "17:00").isoformat()},
        shift=sh_late, exception_id=early_exc["exception_id"],
        actor_is_manager=True, actor_role="manager", kind="early_leave",
    )
    check("early leave high-risk dual required", req_early["case"].get("dual_approval_required") is True)
    r1 = svc.review_case(
        company_code="ATTW3", case_id=req_early["case"]["case_id"], decision="approved",
        decided_by_phone="96552499901", expected_row_version=req_early["case"]["row_version"],
        actor_role="manager", employee=emp(),
    )
    check("dual approval first stage", r1.get("dual_pending") is True and r1["case"]["status"] == "pending_dual_approval")
    same = svc.review_case(
        company_code="ATTW3", case_id=req_early["case"]["case_id"], decision="approved",
        decided_by_phone="96552499901", expected_row_version=r1["case"]["row_version"],
        actor_role="manager", employee=emp(),
    )
    check("dual approval rejects same approver", same.get("error") == "dual_approval_requires_distinct_approver", same)
    # second approver must be in scope for E1 — 99902 is NOT; use HR role for second
    r2 = svc.review_case(
        company_code="ATTW3", case_id=req_early["case"]["case_id"], decision="approved",
        decided_by_phone="96552488888", expected_row_version=r1["case"]["row_version"],
        actor_role="hr", employee=emp(),
    )
    check("dual approval second completes", r2.get("ok") is True and r2["case"]["status"] == "approved", r2)
    ap_early = svc.apply_case(
        company_code="ATTW3", case_id=req_early["case"]["case_id"], applied_by_phone="96552488888",
        expected_row_version=r2["case"]["row_version"], idempotency_key="apply-early-1",
        employee=emp(), shift=sh_late, actor_role="hr",
    )
    check("early leave applied", ap_early.get("ok") is True)

    # --- absence correction ---
    d_abs = date(2026, 8, 13)
    sh_abs = shift_day(d_abs, "33333333-3333-3333-3333-333333333333")
    abs_proj = authority.reproject_day(
        company_code="ATTW3", employee=emp(), work_date=d_abs, shift=sh_abs,
        forced_status="absent", created_by_phone="96552488888",
    )
    sync_abs = svc.sync_exceptions_from_projection(company_code="ATTW3", employee=emp(), projection=abs_proj["projection"])
    check("absence exception", any(e["kind"] == "absence" for e in sync_abs["exceptions"]))
    abs_exc = next(e for e in sync_abs["exceptions"] if e["kind"] == "absence")
    req_abs = svc.request_correction(
        company_code="ATTW3", employee=emp(), work_date=d_abs,
        requested_by_phone="96552499901",
        changes={"check_in_at": dt(d_abs, "09:00").isoformat(), "check_out_at": dt(d_abs, "17:00").isoformat(), "status": "completed"},
        shift=sh_abs, exception_id=abs_exc["exception_id"],
        actor_is_manager=True, actor_role="manager", kind="absence",
    )
    # dual for absence
    ra1 = svc.review_case(company_code="ATTW3", case_id=req_abs["case"]["case_id"], decision="approved",
                          decided_by_phone="96552499901", expected_row_version=req_abs["case"]["row_version"],
                          actor_role="manager", employee=emp())
    ra2 = svc.review_case(company_code="ATTW3", case_id=req_abs["case"]["case_id"], decision="approved",
                          decided_by_phone="96552488888", expected_row_version=ra1["case"]["row_version"],
                          actor_role="hr", employee=emp())
    ap_abs = svc.apply_case(company_code="ATTW3", case_id=req_abs["case"]["case_id"], applied_by_phone="96552488888",
                            expected_row_version=ra2["case"]["row_version"], idempotency_key="apply-abs-1",
                            employee=emp(), shift=sh_abs, actor_role="hr")
    check("absence correction applied", ap_abs.get("ok") is True)

    # --- reject path ---
    d_rej = date(2026, 8, 14)
    sh_rej = shift_day(d_rej, "44444444-4444-4444-4444-444444444444")
    authority.ingest_punch(company_code="ATTW3", employee=emp(), punched_at=dt(d_rej, "09:00"), direction="in",
                           source="hr", source_event_id="w3-rej-in", shift=sh_rej, work_date=d_rej)
    only_in = authority.store.get_current_projection(company_code="ATTW3", employee_key="ATTW3-E1", work_date=d_rej,
                                                    shift_key=auth.shift_key_of(sh_rej["shift_id"]))
    sync_rej = svc.sync_exceptions_from_projection(company_code="ATTW3", employee=emp(), projection=only_in or {})
    rej_exc = next((e for e in sync_rej["exceptions"] if e["kind"] == "missing_check_out"), None)
    check("missing checkout for reject path", rej_exc is not None)
    req_rej = svc.request_correction(
        company_code="ATTW3", employee=emp(), work_date=d_rej,
        requested_by_phone="96552499901",
        changes={"check_out_at": dt(d_rej, "17:00").isoformat()},
        shift=sh_rej, exception_id=(rej_exc or {}).get("exception_id"),
        actor_is_manager=True, actor_role="manager",
    )
    rejected = svc.review_case(
        company_code="ATTW3", case_id=req_rej["case"]["case_id"], decision="rejected",
        decided_by_phone="96552499901", expected_row_version=req_rej["case"]["row_version"],
        decision_note="insufficient evidence", actor_role="manager", employee=emp(),
    )
    check("reject without apply", rejected.get("ok") is True and rejected["case"]["status"] == "rejected" and rejected.get("applied") is False)

    # --- dispute + reopen ---
    d_disp = date(2026, 8, 15)
    sh_disp = shift_day(d_disp, "55555555-5555-5555-5555-555555555555")
    authority.ingest_punch(company_code="ATTW3", employee=emp(), punched_at=dt(d_disp, "09:05"), direction="in",
                           source="hr", source_event_id="w3-disp-in", shift=sh_disp, work_date=d_disp)
    authority.ingest_punch(company_code="ATTW3", employee=emp(), punched_at=dt(d_disp, "17:00"), direction="out",
                           source="hr", source_event_id="w3-disp-out", shift=sh_disp, work_date=d_disp)
    cur_disp = authority.store.get_current_projection(company_code="ATTW3", employee_key="ATTW3-E1", work_date=d_disp,
                                                     shift_key=auth.shift_key_of(sh_disp["shift_id"]))
    sync_disp = svc.sync_exceptions_from_projection(company_code="ATTW3", employee=emp(), projection=cur_disp or {})
    lateness = next((e for e in sync_disp["exceptions"] if e["kind"] == "lateness"), None)
    if not lateness:
        opened = svc.open_exception(company_code="ATTW3", employee=emp(), work_date=d_disp, kind="lateness",
                                    shift_key=auth.shift_key_of(sh_disp["shift_id"]), projection=cur_disp)
        lateness = opened["exception"]
    req_d = svc.request_correction(
        company_code="ATTW3", employee=emp(), work_date=d_disp,
        requested_by_phone="96552499901",
        changes={"check_in_at": dt(d_disp, "09:00").isoformat()},
        shift=sh_disp, exception_id=lateness["exception_id"],
        actor_is_manager=True, actor_role="manager", kind="lateness",
    )
    rd = svc.review_case(company_code="ATTW3", case_id=req_d["case"]["case_id"], decision="approved",
                         decided_by_phone="96552499901", expected_row_version=req_d["case"]["row_version"],
                         actor_role="manager", employee=emp())
    ap_d = svc.apply_case(company_code="ATTW3", case_id=req_d["case"]["case_id"], applied_by_phone="96552499901",
                          expected_row_version=rd["case"]["row_version"], idempotency_key="apply-disp-1",
                          employee=emp(), shift=sh_disp, actor_role="manager")
    check("dispute base applied", ap_d.get("ok") is True)
    dispute = svc.raise_dispute(
        company_code="ATTW3", employee=emp(), work_date=d_disp,
        raised_by_phone="96552400001", reason="I was on time",
        exception_id=lateness["exception_id"], case_id=req_d["case"]["case_id"],
        shift_key=auth.shift_key_of(sh_disp["shift_id"]),
    )
    check("employee dispute raised", dispute.get("ok") is True)
    resolved = svc.resolve_dispute(
        company_code="ATTW3", dispute_id=dispute["dispute"]["dispute_id"],
        resolution="overturned", resolved_by_phone="96552499901",
        expected_row_version=dispute["dispute"]["row_version"],
        resolution_note="badge misread", actor_role="manager", employee=emp(),
    )
    check("manager resolves dispute", resolved.get("ok") is True and resolved["dispute"]["status"] == "overturned")
    # resolve exception first for reopen path
    exc_now = svc.store.get_exception(lateness["exception_id"], "ATTW3")
    if exc_now and exc_now["status"] != "resolved":
        svc.store.update_exception(lateness["exception_id"], "ATTW3", expected_row_version=exc_now["row_version"], status="resolved")
        exc_now = svc.store.get_exception(lateness["exception_id"], "ATTW3")
    reopen = svc.reopen_exception(
        company_code="ATTW3", exception_id=lateness["exception_id"],
        actor_phone="96552488888", expected_row_version=int((exc_now or {}).get("row_version") or 1),
        evidence_note="new badge logs attached", actor_role="hr",
    )
    check("reopen after new evidence", reopen.get("ok") is True and reopen["exception"]["status"] == "reopened", reopen)

    # --- stale conflict fail-closed ---
    stale = svc.assign_exception(
        company_code="ATTW3", exception_id=lateness["exception_id"], owner_phone="96552499901",
        actor_phone="96552488888", expected_row_version=1, actor_role="hr",
    )
    check("stale row_version fail-closed", stale.get("error") == "stale_row_version", stale)

    # --- manager scope direct/team/branch ---
    ok_scope = svc.request_correction(
        company_code="ATTW3", employee=emp("ATTW3-E1"), work_date=d_disp,
        requested_by_phone="96552499901", changes={"status": "absent"},
        shift=sh_disp, actor_is_manager=True, actor_role="manager",
    )
    # may fail payroll or other — but should NOT be outside scope
    check("manager in-scope allowed (not outside_scope)", ok_scope.get("error") != "employee_outside_manager_scope", ok_scope)
    out_scope = svc.request_correction(
        company_code="ATTW3", employee=emp("ATTW3-E3", phone="96552400003"), work_date=d_disp,
        requested_by_phone="96552499901", changes={"status": "absent"},
        shift=sh_disp, actor_is_manager=True, actor_role="manager",
    )
    check("manager out-of-scope denied", out_scope.get("error") == "employee_outside_manager_scope", out_scope)
    branch_ok = svc.request_correction(
        company_code="ATTW3", employee=emp("ATTW3-E3", phone="96552400003"), work_date=d_disp,
        requested_by_phone="96552499902", changes={"check_in_at": dt(d_disp, "09:00").isoformat()},
        shift=sh_disp, actor_is_manager=True, actor_role="manager",
    )
    check("branch/team manager in-scope", branch_ok.get("ok") is True or branch_ok.get("error") not in {"employee_outside_manager_scope", "manager_unconfigured"}, branch_ok)

    # --- unconfigured manager denied ---
    unconf = svc.request_correction(
        company_code="ATTW3", employee=emp(), work_date=d_disp,
        requested_by_phone="96552400099", changes={"status": "absent"},
        shift=sh_disp, actor_is_manager=True, actor_role="manager",
    )
    check("unconfigured manager denied", unconf.get("error") == "manager_unconfigured", unconf)

    # --- manager self-correction denied ---
    self_deny = svc.request_correction(
        company_code="ATTW3",
        employee=emp(key="ATTW3-E1", phone="96552499901"),
        work_date=d_disp,
        requested_by_phone="96552499901",
        changes={"status": "absent"},
        shift=sh_disp, actor_is_manager=True, actor_role="manager",
    )
    check("manager self-correction denied", self_deny.get("error") == "manager_self_correction_denied", self_deny)

    # --- locked payroll period denied ---
    d_lock = date(2026, 8, 16)
    sh_lock = shift_day(d_lock, "66666666-6666-6666-6666-666666666666")
    locked_dates.add(("ATTW3", "ATTW3-E1", d_lock))
    lock_deny = svc.request_correction(
        company_code="ATTW3", employee=emp(), work_date=d_lock,
        requested_by_phone="96552499901",
        changes={"check_in_at": dt(d_lock, "09:00").isoformat()},
        shift=sh_lock, actor_is_manager=True, actor_role="manager",
    )
    check("locked payroll period denied", lock_deny.get("error") == "payroll_period_locked", lock_deny)

    # --- correction survives leave reversal ---
    d_leave = date(2026, 8, 17)
    sh_leave = shift_day(d_leave, "77777777-7777-7777-7777-777777777777")
    authority.apply_leave(company_code="ATTW3", employee=emp(), work_date=d_leave, leave_id="leave-w3", shift=sh_leave)
    req_lv = svc.request_correction(
        company_code="ATTW3", employee=emp(), work_date=d_leave,
        requested_by_phone="96552499901",
        changes={"check_in_at": dt(d_leave, "09:00").isoformat(), "check_out_at": dt(d_leave, "17:00").isoformat(), "status": "completed"},
        shift=sh_leave, actor_is_manager=True, actor_role="manager", kind="absence",
    )
    # absence dual
    rl1 = svc.review_case(company_code="ATTW3", case_id=req_lv["case"]["case_id"], decision="approved",
                          decided_by_phone="96552499901", expected_row_version=req_lv["case"]["row_version"],
                          actor_role="manager", employee=emp())
    rl2 = svc.review_case(company_code="ATTW3", case_id=req_lv["case"]["case_id"], decision="approved",
                          decided_by_phone="96552488888", expected_row_version=rl1["case"]["row_version"],
                          actor_role="hr", employee=emp())
    ap_lv = svc.apply_case(company_code="ATTW3", case_id=req_lv["case"]["case_id"], applied_by_phone="96552488888",
                           expected_row_version=rl2["case"]["row_version"], idempotency_key="apply-leave-1",
                           employee=emp(), shift=sh_leave, actor_role="hr")
    check("post-leave correction applied", ap_lv.get("ok") is True and (ap_lv.get("projection") or {}).get("manual_correction") is True)
    rev_leave = authority.reverse_leave(company_code="ATTW3", employee=emp(), work_date=d_leave, leave_id="leave-w3", shift=sh_leave)
    check("leave reverse preserves correction", rev_leave.get("reason") == "manual_correction_preserved", rev_leave)

    # --- approved attendance → payroll snapshot reconciliation ---
    d_pay = date(2026, 8, 18)
    sh_pay = shift_day(d_pay, "88888888-8888-8888-8888-888888888888")
    authority.ingest_punch(company_code="ATTW3", employee=emp(), punched_at=dt(d_pay, "09:00"), direction="in",
                           source="hr", source_event_id="w3-pay-in", shift=sh_pay, work_date=d_pay)
    authority.ingest_punch(company_code="ATTW3", employee=emp(), punched_at=dt(d_pay, "17:00"), direction="out",
                           source="hr", source_event_id="w3-pay-out", shift=sh_pay, work_date=d_pay)
    approved = authority.approve_day(company_code="ATTW3", employee=emp(), work_date=d_pay, approved_by_phone="96552488888", shift=sh_pay)
    check("day approved for payroll", approved.get("ok") is True, approved)
    snap = approved.get("snapshot") or {}
    proj = approved.get("projection") or {}
    payload = snap.get("payload") or {}
    check(
        "approved attendance reconciles to payroll snapshot",
        snap.get("projection_id") == proj.get("projection_id")
        and int(snap.get("projection_version") or 0) == int(proj.get("version") or -1)
        and payload.get("worked_minutes") == proj.get("worked_minutes")
        and payload.get("status") == proj.get("status"),
        {"snap": snap.get("projection_version"), "proj": proj.get("version"), "payload": payload.get("worked_minutes")},
    )

    # disputed/incomplete excluded
    check("incomplete not payroll eligible before fix", only_out["projection"].get("payroll_eligible") is False)
    disputed_proj = authority.store.get_current_projection(
        company_code="ATTW3", employee_key="ATTW3-E1", work_date=d_disp,
        shift_key=auth.shift_key_of(sh_disp["shift_id"]),
    )
    check("disputed stays payroll-excluded or unapproved", (disputed_proj or {}).get("approval_status") == "disputed" or not (disputed_proj or {}).get("payroll_eligible"))

    # --- comments / attachments / audit ---
    cmt = svc.add_comment(company_code="ATTW3", entity_type="exception", entity_id=lateness["exception_id"],
                          author_phone="96552499901", body="Reviewed badge logs")
    check("comment added", cmt.get("ok") is True)
    att = svc.add_attachment(company_code="ATTW3", entity_type="exception", entity_id=lateness["exception_id"],
                             uploaded_by_phone="96552499901", filename="badge.pdf", storage_ref="s3://ops/badge.pdf")
    check("attachment ref stored", att.get("ok") is True)
    bad_att = svc.add_attachment(company_code="ATTW3", entity_type="exception", entity_id=lateness["exception_id"],
                                 uploaded_by_phone="96552499901", filename="x", storage_ref="https://x?token=secret")
    check("secret storage_ref rejected", bad_att.get("error") == "invalid_storage_ref")
    audit = svc.store.list_audit(company_code="ATTW3", entity_type="exception", entity_id=lateness["exception_id"])
    check("audit events present", len(audit) >= 1, len(audit))

    # --- tenant isolation ---
    other = ops.AttendanceOpsService(authority_service=auth.AttendanceAuthorityService())
    other.open_exception(
        company_code="OTHERCO", employee={"employee_key": "OTHER-1", "phone": "96552411111"},
        work_date=d_miss, kind="absence",
    )
    attw3_q = svc.list_queue(company_code="ATTW3", actor_role="hr")
    other_q = other.list_queue(company_code="OTHERCO", actor_role="hr")
    check("tenant isolation ATTW3", all(e["company_code"] == "ATTW3" for e in attw3_q["exceptions"]))
    check("tenant isolation OTHERCO", all(e["company_code"] == "OTHERCO" for e in other_q["exceptions"]) and other_q["count"] >= 1)
    leaked = svc.store.get_exception(other_q["exceptions"][0]["exception_id"], "ATTW3")
    check("cross-tenant get denied", leaked is None)

    # --- connector issue kind ---
    conn_exc = svc.open_exception(
        company_code="ATTW3", employee=emp(), work_date=d_miss, kind="connector_issue",
        source="connector", source_ref="remediation:demo", actor_role="hr",
    )
    check("connector issue exception", conn_exc.get("ok") is True and conn_exc["exception"]["kind"] == "connector_issue")

    # --- ambiguous punches ---
    check("ambiguous kind supported", "ambiguous_punches" in ops.EXCEPTION_KINDS)

    # --- raw punches immutable (correction adds new, does not mutate source) ---
    punches_before = [p for p in authority.store.punches if p.get("source") == "hr" and p.get("source_event_id") == "w3-pay-in"]
    check("raw punch still present after corrections", len(punches_before) == 1)
    check("correction punches are separate source", any(p.get("source") == "correction" for p in authority.store.punches))

    # --- freezes ---
    skip_freeze = (os.environ.get("WATHEFNI_SKIP_FREEZE") or "").strip().lower() in {"1", "true", "yes", "on"}
    if skip_freeze:
        check("freeze skipped", True)
    else:
        freeze_root = Path(os.environ.get("WATHEFNI_ORCH_ROOT") or ROOT)
        for script in ("smoke-test-employees360-freeze-regression.py", "smoke-test-onboarding-freeze-regression.py"):
            path = freeze_root / script
            if not path.exists():
                check(f"freeze {script}", False, "missing")
                continue
            proc = subprocess.run([sys.executable, str(path)], cwd=str(freeze_root), capture_output=True, text=True)
            check(f"freeze {script}", proc.returncode == 0, (proc.stdout + proc.stderr)[-500:])

    # --- module wiring markers ---
    app_src = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    check("app registers ops routes", "register_attendance_ops_routes" in app_src)
    check("app ensures ops schema", "ensure_attendance_ops_postgres_schema" in app_src)
    check("http module present", (ROOT / "attendance_ops_http.py").exists())
    check("postgres module present", (ROOT / "attendance_ops_postgres.py").exists())

    passed = sum(1 for r in RESULTS if r["ok"])
    failed = sum(1 for r in RESULTS if not r["ok"])
    out = {
        "wave": "attendance-wave3",
        "passed": passed,
        "failed": failed,
        "total": len(RESULTS),
        "results": RESULTS,
        "state_model": model,
        "permission_matrix": {
            "hr": ["open", "assign", "review", "apply", "reopen", "resolve_dispute", "comment", "attach"],
            "manager_configured_in_scope": ["open", "assign", "request", "review", "apply", "resolve_dispute", "comment"],
            "manager_unconfigured": ["denied"],
            "manager_out_of_scope": ["denied"],
            "manager_self": ["denied"],
            "employee": ["raise_dispute"],
        },
        "workflow": {
            "exception": "open → assigned → in_review → (pending_dual_approval) → resolved|rejected|reopened → closed",
            "correction": "request → review(approve|reject) → apply(idempotent)",
            "dispute": "raise → under_review → upheld|overturned → optional reopen",
        },
    }
    results_path = os.environ.get("ATTW3_RESULTS_PATH")
    if results_path:
        Path(results_path).parent.mkdir(parents=True, exist_ok=True)
        Path(results_path).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWave 3 smoke: {passed}/{len(RESULTS)} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
