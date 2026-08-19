#!/usr/bin/env python3
"""Attendance Wave 4B — seed daily board + click-through + API/UI reconciliation.

Local or staging (import app when WATHEFNI_ENV=staging). Synthetic markers only.
No real ingest, devices, QR/GPS/kiosk, or production deploy.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

KUWAIT = ZoneInfo("Asia/Kuwait")
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("ATTW4B_EVID") or f"/tmp/attw4b-{uuid.uuid4().hex[:8]}")
EVID.mkdir(parents=True, exist_ok=True)


def check(name: str, ok: bool, detail: object = None) -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if not ok and detail is not None else ""))


def dt(d: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=KUWAIT)


def shift_day(d: date, start: str = "09:00", end: str = "17:00", shift_id: str | None = None) -> dict:
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    return {
        "shift_id": shift_id or str(uuid.uuid4()),
        "shift_date": d,
        "start_time": time(sh, sm),
        "end_time": time(eh, em),
    }


def kuwait_today() -> date:
    return datetime.now(KUWAIT).date()


def main() -> int:
    tag = uuid.uuid4().hex[:8].upper()
    suffix = f"{int(tag, 16) % 10000:04d}"
    company = os.environ.get("ATTW4B_COMPANY") or "WATHEFNI"
    today = kuwait_today()

    os.environ.setdefault("WATHEFNI_ATTENDANCE_AUTHORITY", "on")
    os.environ.setdefault("WATHEFNI_ATTENDANCE_OPS", "on")
    os.environ.setdefault("WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS", "absence,early_leave")
    os.environ.setdefault("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")

    env = (os.environ.get("WATHEFNI_ENV") or "local").strip().lower()
    use_app = env in {"staging", "production"} or os.environ.get("ATTW4B_USE_APP") == "1"

    locked_dates: set[tuple[str, str, date]] = set()
    # manager phones (digit-only)
    hr_phone = f"96552480{suffix}"
    mgr_phone = f"96552481{suffix}"
    mgr2_phone = f"96552482{suffix}"
    out_mgr = f"96552483{suffix}"

    employees: dict[str, dict[str, Any]] = {}
    scenarios = (
        "NORMAL",
        "OVERNIGHT",
        "MULTI",
        "MISSIN",
        "MISSOUT",
        "LATE",
        "ABSENT",
        "DUAL",  # absence dual-approval click path (separate from display ABSENT)
        "DISPUTE",
        "LOCKED",
        "CLICK",  # dedicated missing-out for click-through correction
    )
    for i, name in enumerate(scenarios):
        employees[name] = {
            "employee_key": f"W3-SYNTH|ATTW4B-{tag}-{name}",
            "phone": f"9655249{i}{suffix}",
            "name": f"AttW4B {name} {tag}",
            "company_code": company,
        }

    scope_map = {
        mgr_phone: {
            employees["CLICK"]["employee_key"],
            employees["LATE"]["employee_key"],
            employees["ABSENT"]["employee_key"],
            employees["DUAL"]["employee_key"],
            employees["DISPUTE"]["employee_key"],
            employees["LOCKED"]["employee_key"],
        },
        mgr2_phone: {employees["CLICK"]["employee_key"], employees["DUAL"]["employee_key"]},
        out_mgr: set(),
    }

    def scope_allows(_company: str, actor: str, employee_key: str) -> bool:
        allowed = scope_map.get(actor)
        if allowed is None:
            # HR / unrestricted
            return True
        return employee_key in allowed

    def payroll_locked(_company: str, employee_key: str, d: date) -> bool:
        return (_company, employee_key, d) in locked_dates

    def mgr_configured(_company: str, actor: str) -> bool:
        return actor in {mgr_phone, mgr2_phone, out_mgr, hr_phone} or actor.startswith("965524")

    if use_app:
        import attendance_authority_wave1 as auth
        import attendance_ops_wave3 as ops

        os.environ.setdefault("WATHEFNI_ATTENDANCE_OPS_COMPANIES", "WATHEFNI,ATTW3")
        authority = auth.get_authority_service(company)
        svc = ops.AttendanceOpsService(
            authority_service=authority,
            scope_allows=scope_allows,
            payroll_locked=payroll_locked,
            manager_configured=mgr_configured,
        )
    else:
        os.environ["WATHEFNI_ATTENDANCE_AUTHORITY_STORE"] = "memory"
        os.environ["WATHEFNI_ATTENDANCE_OPS_STORE"] = "memory"
        os.environ["WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES"] = "WATHEFNI,ATTW3"
        os.environ["WATHEFNI_ATTENDANCE_OPS_COMPANIES"] = "WATHEFNI,ATTW3"
        import attendance_authority_wave1 as auth
        import attendance_ops_wave3 as ops

        ops.reset_ops_services_for_tests()
        authority = auth.AttendanceAuthorityService()
        svc = ops.AttendanceOpsService(
            authority_service=authority,
            scope_allows=scope_allows,
            payroll_locked=payroll_locked,
            manager_configured=mgr_configured,
        )

    seed_index: dict[str, Any] = {"tag": tag, "company": company, "work_date": today.isoformat(), "employees": {}}

    def punch(emp: dict, d: date, hhmm: str, direction: str, *, shift: dict, event: str, break_paid: bool | None = None, at: datetime | None = None) -> dict:
        return authority.ingest_punch(
            company_code=company,
            employee=emp,
            punched_at=at or dt(d, hhmm),
            direction=direction,
            source="hr",
            source_event_id=f"attw4b-{tag}-{event}",
            shift=shift,
            work_date=d,
            break_paid=break_paid,
            created_by_phone=hr_phone,
            metadata={"attw4b_tag": tag, "scenario": event},
        )

    # --- NORMAL (approve) ---
    emp = employees["NORMAL"]
    sh = shift_day(today, shift_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tag}-normal")))
    punch(emp, today, "09:00", "in", shift=sh, event="normal-in")
    punch(emp, today, "17:00", "out", shift=sh, event="normal-out")
    ap = authority.approve_day(company_code=company, employee=emp, work_date=today, approved_by_phone=hr_phone, shift=sh)
    check("normal day approved + payroll eligible", ap.get("ok") is True and (ap.get("projection") or {}).get("payroll_eligible") is True, ap.get("error"))
    seed_index["employees"]["NORMAL"] = {"key": emp["employee_key"], "shift_id": sh["shift_id"], "state": "approved"}

    # --- OVERNIGHT ---
    emp = employees["OVERNIGHT"]
    sh = shift_day(today, "22:00", "06:00", shift_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tag}-overnight")))
    punch(emp, today, "22:05", "in", shift=sh, event="ov-in")
    nxt = today + timedelta(days=1)
    punch(emp, today, "06:00", "out", shift=sh, event="ov-out", at=dt(nxt, "06:00"))
    ov = authority.store.get_current_projection(company_code=company, employee_key=emp["employee_key"], work_date=today, shift_key=auth.shift_key_of(sh["shift_id"]))
    check("overnight projection present", ov is not None and int((ov or {}).get("worked_minutes") or 0) > 0, {"worked": (ov or {}).get("worked_minutes") if ov else None})
    seed_index["employees"]["OVERNIGHT"] = {"key": emp["employee_key"], "worked_minutes": (ov or {}).get("worked_minutes")}

    # --- MULTI sessions + paid/unpaid breaks ---
    emp = employees["MULTI"]
    sh = shift_day(today, shift_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tag}-multi")))
    for direction, hhmm, event, paid in (
        ("in", "09:00", "m1-in", None),
        ("break_start", "12:00", "m1-bs-unpaid", False),
        ("break_end", "12:30", "m1-be-unpaid", False),
        ("out", "13:00", "m1-out", None),
        ("in", "14:00", "m2-in", None),
        ("break_start", "15:00", "m2-bs-paid", True),
        ("break_end", "15:15", "m2-be-paid", True),
        ("out", "17:00", "m2-out", None),
    ):
        punch(emp, today, hhmm, direction, shift=sh, event=event, break_paid=paid)
    multi = authority.store.get_current_projection(company_code=company, employee_key=emp["employee_key"], work_date=today, shift_key=auth.shift_key_of(sh["shift_id"]))
    sessions = (multi or {}).get("sessions") or []
    breaks = (multi or {}).get("breaks") or []
    check("multi-session day has 2+ sessions", len(sessions) >= 2, len(sessions))
    check("paid and unpaid breaks present", int((multi or {}).get("paid_break_minutes") or 0) > 0 and int((multi or {}).get("unpaid_break_minutes") or 0) > 0, {
        "paid": (multi or {}).get("paid_break_minutes"),
        "unpaid": (multi or {}).get("unpaid_break_minutes"),
        "breaks": len(breaks),
    })
    seed_index["employees"]["MULTI"] = {
        "key": emp["employee_key"],
        "sessions": len(sessions),
        "paid_break_minutes": (multi or {}).get("paid_break_minutes"),
        "unpaid_break_minutes": (multi or {}).get("unpaid_break_minutes"),
        "worked_minutes": (multi or {}).get("worked_minutes"),
    }

    # --- MISSING IN / OUT ---
    emp = employees["MISSIN"]
    sh = shift_day(today, shift_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tag}-missin")))
    only_out = authority.ingest_punch(
        company_code=company, employee=emp, punched_at=dt(today, "17:00"), direction="out",
        source="hr", source_event_id=f"attw4b-{tag}-missin-out", shift=sh, work_date=today, created_by_phone=hr_phone,
        metadata={"attw4b_tag": tag},
    )
    sync = svc.sync_exceptions_from_projection(company_code=company, employee=emp, projection=only_out.get("projection") or {})
    check("missing check-in exception", any(e["kind"] == "missing_check_in" for e in sync.get("exceptions") or []), sync)

    emp = employees["MISSOUT"]
    sh = shift_day(today, shift_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tag}-missout")))
    only_in = authority.ingest_punch(
        company_code=company, employee=emp, punched_at=dt(today, "09:00"), direction="in",
        source="hr", source_event_id=f"attw4b-{tag}-missout-in", shift=sh, work_date=today, created_by_phone=hr_phone,
        metadata={"attw4b_tag": tag},
    )
    sync = svc.sync_exceptions_from_projection(company_code=company, employee=emp, projection=only_in.get("projection") or {})
    check("missing check-out exception", any(e["kind"] == "missing_check_out" for e in sync.get("exceptions") or []), sync)

    # --- LATE + EARLY LEAVE ---
    emp = employees["LATE"]
    sh = shift_day(today, shift_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tag}-late")))
    authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(today, "09:45"), direction="in",
                           source="hr", source_event_id=f"attw4b-{tag}-late-in", shift=sh, work_date=today, created_by_phone=hr_phone, metadata={"attw4b_tag": tag})
    late_proj = authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(today, "16:30"), direction="out",
                                       source="hr", source_event_id=f"attw4b-{tag}-late-out", shift=sh, work_date=today, created_by_phone=hr_phone, metadata={"attw4b_tag": tag})
    lp = late_proj.get("projection") or {}
    check("late minutes > 0", int(lp.get("late_minutes") or 0) > 0, lp.get("late_minutes"))
    check("early leave minutes > 0", int(lp.get("early_leave_minutes") or 0) > 0, lp.get("early_leave_minutes"))
    svc.sync_exceptions_from_projection(company_code=company, employee=emp, projection=lp)

    # --- ABSENCE (display only — not mutated by dual apply) ---
    emp = employees["ABSENT"]
    sh = shift_day(today, shift_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tag}-absent")))
    abs_proj = authority.reproject_day(
        company_code=company, employee=emp, work_date=today, shift=sh,
        forced_status="absent", created_by_phone=hr_phone, metadata={"attw4b_tag": tag},
    )
    check("absence status", (abs_proj.get("projection") or {}).get("status") == "absent")
    svc.sync_exceptions_from_projection(company_code=company, employee=emp, projection=abs_proj.get("projection") or {})
    seed_index["employees"]["ABSENT"] = {"key": emp["employee_key"], "status": "absent"}

    # --- DUAL absence employee (for dual-approval click path) ---
    emp = employees["DUAL"]
    sh = shift_day(today, shift_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tag}-dual")))
    dual_proj = authority.reproject_day(
        company_code=company, employee=emp, work_date=today, shift=sh,
        forced_status="absent", created_by_phone=hr_phone, metadata={"attw4b_tag": tag},
    )
    svc.sync_exceptions_from_projection(company_code=company, employee=emp, projection=dual_proj.get("projection") or {})
    seed_index["employees"]["DUAL"] = {"key": emp["employee_key"], "status": "absent"}

    # --- DISPUTE path base (apply then dispute) ---
    emp = employees["DISPUTE"]
    sh = shift_day(today, shift_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tag}-dispute")))
    authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(today, "09:20"), direction="in",
                           source="hr", source_event_id=f"attw4b-{tag}-disp-in", shift=sh, work_date=today, created_by_phone=hr_phone, metadata={"attw4b_tag": tag})
    authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(today, "17:00"), direction="out",
                           source="hr", source_event_id=f"attw4b-{tag}-disp-out", shift=sh, work_date=today, created_by_phone=hr_phone, metadata={"attw4b_tag": tag})
    proj_d = authority.store.get_current_projection(company_code=company, employee_key=emp["employee_key"], work_date=today, shift_key=auth.shift_key_of(sh["shift_id"]))
    sync_d = svc.sync_exceptions_from_projection(company_code=company, employee=emp, projection=proj_d or {})
    late_exc = next((e for e in sync_d.get("exceptions") or [] if e["kind"] == "lateness"), None)
    if not late_exc:
        late_exc = svc.open_exception(
            company_code=company, employee=emp, work_date=today, kind="lateness",
            shift_key=auth.shift_key_of(sh["shift_id"]), projection=proj_d, actor_phone=hr_phone, actor_role="hr",
        )["exception"]
    req_d = svc.request_correction(
        company_code=company, employee=emp, work_date=today, requested_by_phone=mgr_phone,
        changes={"check_in_at": dt(today, "09:00").isoformat()},
        shift=sh, exception_id=late_exc["exception_id"], actor_is_manager=True, actor_role="manager", kind="lateness",
    )
    check("dispute base correction requested", req_d.get("ok") is True, req_d)
    rd = svc.review_case(company_code=company, case_id=req_d["case"]["case_id"], decision="approved",
                         decided_by_phone=mgr_phone, expected_row_version=int(req_d["case"]["row_version"]),
                         actor_role="manager", employee=emp)
    check("dispute base approved (single — lateness)", rd.get("ok") is True and rd.get("dual_pending") is not True, rd)
    ap_d = svc.apply_case(company_code=company, case_id=req_d["case"]["case_id"], applied_by_phone=hr_phone,
                          expected_row_version=int(rd["case"]["row_version"]),
                          idempotency_key=f"attw4b-apply-disp-{tag}", employee=emp, shift=sh, actor_role="hr")
    check("dispute base applied (approve≠apply)", ap_d.get("ok") is True and ap_d.get("applied") is True, ap_d)
    dispute = svc.raise_dispute(
        company_code=company, employee=emp, work_date=today, raised_by_phone=emp["phone"],
        reason="badge misread — Wave4B", exception_id=late_exc["exception_id"], case_id=req_d["case"]["case_id"],
        shift_key=auth.shift_key_of(sh["shift_id"]),
    )
    check("employee dispute raised", dispute.get("ok") is True, dispute)
    seed_index["employees"]["DISPUTE"] = {"key": emp["employee_key"], "dispute_id": (dispute.get("dispute") or {}).get("dispute_id")}

    # --- LOCKED metadata display + lock denial ---
    emp = employees["LOCKED"]
    sh = shift_day(today, shift_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tag}-locked")))
    authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(today, "09:00"), direction="in",
                           source="hr", source_event_id=f"attw4b-{tag}-lock-in", shift=sh, work_date=today, created_by_phone=hr_phone, metadata={"attw4b_tag": tag})
    authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(today, "17:00"), direction="out",
                           source="hr", source_event_id=f"attw4b-{tag}-lock-out", shift=sh, work_date=today, created_by_phone=hr_phone, metadata={"attw4b_tag": tag})
    locked_proj = authority.reproject_day(
        company_code=company, employee=emp, work_date=today, shift=sh, created_by_phone=hr_phone,
        approval_status="unapproved",
        metadata={"attw4b_tag": tag, "payroll_locked": True},
    )
    check("locked metadata on projection", bool(((locked_proj.get("projection") or {}).get("metadata") or {}).get("payroll_locked")), locked_proj.get("projection"))
    locked_dates.add((company, emp["employee_key"], today))
    lock_deny = svc.request_correction(
        company_code=company, employee=emp, work_date=today, requested_by_phone=mgr_phone,
        changes={"check_in_at": dt(today, "09:05").isoformat()},
        shift=sh, actor_is_manager=True, actor_role="manager",
    )
    check("payroll lock denies correction", lock_deny.get("error") == "payroll_period_locked", lock_deny)
    seed_index["employees"]["LOCKED"] = {"key": emp["employee_key"], "payroll_locked": True}

    # --- CLICK-THROUGH: request → dual approve (absence) → apply; reject path; reopen; stale; scope; self ---
    emp = employees["CLICK"]
    sh = shift_day(today, shift_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tag}-click")))
    only_in = authority.ingest_punch(
        company_code=company, employee=emp, punched_at=dt(today, "09:00"), direction="in",
        source="hr", source_event_id=f"attw4b-{tag}-click-in", shift=sh, work_date=today, created_by_phone=hr_phone, metadata={"attw4b_tag": tag},
    )
    sync = svc.sync_exceptions_from_projection(company_code=company, employee=emp, projection=only_in.get("projection") or {})
    exc = next((e for e in sync.get("exceptions") or [] if e["kind"] == "missing_check_out"), None)
    check("click exception opened", exc is not None, sync)
    assert exc
    assigned = svc.assign_exception(
        company_code=company, exception_id=exc["exception_id"], owner_phone=mgr_phone,
        actor_phone=mgr_phone, expected_row_version=int(exc["row_version"]), actor_role="manager",
    )
    check("click exception assigned", assigned.get("ok") is True, assigned)

    # Reject path (separate case on ABSENT kind for dual later) — first a simple reject on lateness-like fix
    req_rej = svc.request_correction(
        company_code=company, employee=emp, work_date=today, requested_by_phone=mgr_phone,
        changes={"check_out_at": dt(today, "17:00").isoformat()},
        shift=sh, exception_id=exc["exception_id"], actor_is_manager=True, actor_role="manager", kind="missing_check_out",
    )
    check("correction requested", req_rej.get("ok") is True, req_rej)
    case = req_rej["case"]
    check("case status requested (not applied)", case.get("status") == "requested" and case.get("status") != "applied")
    rejected = svc.review_case(
        company_code=company, case_id=case["case_id"], decision="rejected",
        decided_by_phone=mgr_phone, expected_row_version=int(case["row_version"]),
        decision_note="insufficient evidence", actor_role="manager", employee=emp,
    )
    check("reject without apply", rejected.get("ok") is True and rejected.get("applied") is not True and (rejected.get("case") or {}).get("status") == "rejected", rejected)

    # Fresh correction for approve≠apply + dual (use DUAL employee)
    emp_dual = employees["DUAL"]
    sh_dual = shift_day(today, shift_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tag}-dual")))
    dual_exc = svc.open_exception(
        company_code=company, employee=emp_dual, work_date=today, kind="absence",
        shift_key=auth.shift_key_of(sh_dual["shift_id"]), actor_phone=hr_phone, actor_role="hr",
    )
    check("absence exception for dual", dual_exc.get("ok") is True, dual_exc)
    req_dual = svc.request_correction(
        company_code=company, employee=emp_dual, work_date=today, requested_by_phone=mgr_phone,
        changes={"check_in_at": dt(today, "09:00").isoformat(), "check_out_at": dt(today, "17:00").isoformat(), "status": "completed"},
        shift=sh_dual, exception_id=(dual_exc.get("exception") or {}).get("exception_id"),
        actor_is_manager=True, actor_role="manager", kind="absence",
    )
    check("dual correction requested", req_dual.get("ok") is True, req_dual)
    r1 = svc.review_case(
        company_code=company, case_id=req_dual["case"]["case_id"], decision="approved",
        decided_by_phone=mgr_phone, expected_row_version=int(req_dual["case"]["row_version"]),
        actor_role="manager", employee=emp_dual,
    )
    check("first approval dual_pending", r1.get("ok") is True and r1.get("dual_pending") is True, r1)
    check("not applied after first approve", (r1.get("case") or {}).get("status") == "pending_dual_approval")
    same = svc.review_case(
        company_code=company, case_id=req_dual["case"]["case_id"], decision="approved",
        decided_by_phone=mgr_phone, expected_row_version=int((r1.get("case") or {}).get("row_version") or 1),
        actor_role="manager", employee=emp_dual,
    )
    check("same approver blocked", same.get("error") == "dual_approval_requires_distinct_approver", same)
    r2 = svc.review_case(
        company_code=company, case_id=req_dual["case"]["case_id"], decision="approved",
        decided_by_phone=mgr2_phone, expected_row_version=int((r1.get("case") or {}).get("row_version") or 1),
        actor_role="manager", employee=emp_dual,
    )
    check("second approval ready to apply", r2.get("ok") is True and (r2.get("case") or {}).get("status") == "approved" and r2.get("applied") is not True, r2)
    check("approve and apply remain separate", (r2.get("case") or {}).get("status") == "approved")
    applied = svc.apply_case(
        company_code=company, case_id=req_dual["case"]["case_id"], applied_by_phone=hr_phone,
        expected_row_version=int((r2.get("case") or {}).get("row_version") or 1),
        idempotency_key=f"attw4b-apply-dual-{tag}", employee=emp_dual, shift=sh_dual, actor_role="hr",
    )
    check("apply after dual approval", applied.get("ok") is True and applied.get("applied") is True, applied)

    # Reopen after resolve dispute
    resolved = svc.resolve_dispute(
        company_code=company, dispute_id=dispute["dispute"]["dispute_id"],
        resolution="overturned", resolved_by_phone=mgr_phone,
        expected_row_version=int(dispute["dispute"]["row_version"]),
        resolution_note="accept employee evidence", actor_role="manager", employee=employees["DISPUTE"],
    )
    check("dispute resolved", resolved.get("ok") is True, resolved)
    exc_now = svc.store.get_exception(late_exc["exception_id"], company)
    if exc_now and exc_now["status"] not in {"resolved", "rejected", "closed"}:
        svc.store.update_exception(late_exc["exception_id"], company, expected_row_version=int(exc_now["row_version"]), status="resolved")
        exc_now = svc.store.get_exception(late_exc["exception_id"], company)
    reopen = svc.reopen_exception(
        company_code=company, exception_id=late_exc["exception_id"],
        actor_phone=hr_phone, expected_row_version=int((exc_now or {}).get("row_version") or 1),
        evidence_note="new badge export Wave4B", actor_role="hr",
    )
    check("reopen after evidence", reopen.get("ok") is True and (reopen.get("exception") or {}).get("status") == "reopened", reopen)

    stale = svc.assign_exception(
        company_code=company, exception_id=late_exc["exception_id"], owner_phone=mgr_phone,
        actor_phone=hr_phone, expected_row_version=1, actor_role="hr",
    )
    check("stale row_version fail-closed", stale.get("error") == "stale_row_version", stale)

    out_scope = svc.request_correction(
        company_code=company, employee=employees["CLICK"], work_date=today, requested_by_phone=out_mgr,
        changes={"status": "absent"}, shift=sh, actor_is_manager=True, actor_role="manager",
    )
    check("out-of-scope manager denied", out_scope.get("error") == "employee_outside_manager_scope", out_scope)

    self_deny = svc.request_correction(
        company_code=company,
        employee={**employees["CLICK"], "phone": mgr_phone},
        work_date=today, requested_by_phone=mgr_phone,
        changes={"status": "absent"}, shift=sh, actor_is_manager=True, actor_role="manager",
    )
    check("manager self-correction denied", self_deny.get("error") == "manager_self_correction_denied", self_deny)

    # --- API/UI reconciliation (compat list vs expected life-state counts) ---
    compat = authority.list_compat_attendance(company_code=company, start_date=today, end_date=today)
    mine = [r for r in compat if str(r.get("employee_key") or "").startswith(f"W3-SYNTH|ATTW4B-{tag}-")]
    check("daily board seed rows >= 8", len(mine) >= 8, len(mine))

    def life_state(row: dict) -> str:
        return str(row.get("life_state") or auth.attendance_life_state(row) or "")

    counts = {"approved": 0, "incomplete": 0, "absent": 0, "disputed": 0, "locked": 0, "needs_review": 0, "captured": 0}
    exclusion_checks = []
    for row in mine:
        st = life_state(row)
        counts[st] = counts.get(st, 0) + 1
        meta = row.get("metadata") or {}
        eligible = meta.get("payroll_eligible")
        if eligible is False or meta.get("exception_state") not in {None, "none"} or meta.get("payroll_locked") or str(meta.get("approval_status") or "") == "disputed":
            exclusion_checks.append({
                "employee_key": row.get("employee_key"),
                "exception_state": meta.get("exception_state"),
                "approval_status": meta.get("approval_status"),
                "payroll_eligible": eligible,
                "payroll_locked": meta.get("payroll_locked"),
                "late_minutes": row.get("late_minutes"),
                "early_leave_minutes": row.get("early_leave_minutes"),
                "worked_minutes": meta.get("worked_minutes"),
                "sessions": len(meta.get("sessions") or []),
                "breaks": len(meta.get("breaks") or []),
            })

    check("has approved row", counts.get("approved", 0) >= 1, counts)
    check("has incomplete rows", counts.get("incomplete", 0) >= 1, counts)
    check("has absent row", counts.get("absent", 0) >= 1, counts)
    check("has locked row", counts.get("locked", 0) >= 1, counts)
    check("exclusion reasons sample non-empty", len(exclusion_checks) >= 3, exclusion_checks[:3])

    # Exact totals match: recompute worked/late/early from authority projections
    mismatches = []
    for row in mine:
        key = row["employee_key"]
        meta = row.get("metadata") or {}
        proj = authority.store.get_current_projection(
            company_code=company, employee_key=key, work_date=today, shift_key=str(meta.get("shift_key") or ""),
        )
        if not proj:
            # try any shift
            projs = authority.store.list_current_projections(company_code=company, start_date=today, end_date=today, employee_key=key)
            proj = projs[0] if projs else None
        if not proj:
            mismatches.append({"key": key, "error": "projection_missing"})
            continue
        for field in ("late_minutes", "early_leave_minutes", "worked_minutes"):
            ui_val = row.get(field) if field != "worked_minutes" else meta.get("worked_minutes")
            api_val = proj.get(field)
            if int(ui_val or 0) != int(api_val or 0):
                mismatches.append({"key": key, "field": field, "ui": ui_val, "api": api_val})
        if bool(meta.get("payroll_eligible")) != bool(proj.get("payroll_eligible")):
            mismatches.append({"key": key, "field": "payroll_eligible", "ui": meta.get("payroll_eligible"), "api": proj.get("payroll_eligible")})
    check("API/UI totals exact match", len(mismatches) == 0, mismatches[:5])

    seed_index["counts"] = counts
    seed_index["compat_rows"] = len(mine)
    seed_index["exclusion_sample"] = exclusion_checks[:6]
    seed_index["click"] = {
        "reject_case": (rejected.get("case") or {}).get("case_id"),
        "dual_case": (applied.get("case") or {}).get("case_id") or req_dual["case"]["case_id"],
        "dispute_id": (dispute.get("dispute") or {}).get("dispute_id"),
        "reopened_exception": late_exc["exception_id"],
    }

    (EVID / "seed-index.json").write_text(json.dumps(seed_index, indent=2, default=str), encoding="utf-8")
    (EVID / "clickthrough-results.json").write_text(json.dumps(RESULTS, indent=2, default=str), encoding="utf-8")
    passed = sum(1 for r in RESULTS if r["ok"])
    failed = sum(1 for r in RESULTS if not r["ok"])
    summary = {"tag": tag, "company": company, "work_date": today.isoformat(), "passed": passed, "failed": failed, "total": len(RESULTS), "evid": str(EVID)}
    (EVID / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"SEED_TAG={tag}")
    print(f"WORK_DATE={today.isoformat()}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
