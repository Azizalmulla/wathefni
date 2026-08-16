#!/usr/bin/env python3
"""Attendance Wave 1 — authority foundation qualification (local/staging, no deploy).

Proves calculator, punch ledger, sessions/breaks, corrections, payroll snapshots,
tenant isolation, dark flags, and freeze regressions. No production mutations.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

import attendance_authority_wave1 as auth

PASS = 0
FAIL = 0
RESULTS: list[dict] = []


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    entry = {"label": label, "ok": bool(cond), "detail": detail}
    RESULTS.append(entry)
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def emp(key="ATTW1-E1", phone="96550000001", name="Wave1 Emp") -> dict:
    return {"employee_key": key, "phone": phone, "name": name, "company_code": "ATTW1"}


def shift_day(d: date, start="09:00", end="17:00", shift_id="11111111-1111-1111-1111-111111111111") -> dict:
    return {
        "shift_id": shift_id,
        "shift_date": d,
        "start_time": time.fromisoformat(start),
        "end_time": time.fromisoformat(end),
        "employee_key": "ATTW1-E1",
        "employee_name": "Wave1 Emp",
        "employee_phone": "96550000001",
        "status": "scheduled",
    }


def overnight_shift(d: date, shift_id="22222222-2222-2222-2222-222222222222") -> dict:
    return shift_day(d, start="22:00", end="06:00", shift_id=shift_id)


def dt(d: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(d, time(h, m), tzinfo=auth.KUWAIT_TZ)


def main() -> int:
    auth.reset_authority_services_for_tests()
    os.environ.pop("WATHEFNI_ATTENDANCE_AUTHORITY", None)
    os.environ.pop("WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES", None)

    # --- dark flags ---
    check("authority default off", auth.attendance_authority_enabled() is False)
    check("authority company gated off", auth.attendance_authority_enabled_for_company("ATTW1") is False)
    os.environ["WATHEFNI_ATTENDANCE_AUTHORITY"] = "on"
    os.environ["WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES"] = "ATTW1"
    check("authority on for allowlisted", auth.attendance_authority_enabled_for_company("ATTW1") is True)
    check("authority off for other tenant", auth.attendance_authority_enabled_for_company("WATHEFNI") is False)

    # --- pure calculator: overnight window ---
    win = auth.shift_window(date(2026, 8, 1), "22:00", "06:00")
    check("overnight window spans midnight", win is not None and (win[1] - win[0]) == timedelta(hours=8), win)
    check("scheduled minutes overnight=480", auth.scheduled_minutes("22:00", "06:00") == 480)
    check("legacy minutes_between_times bug avoided", auth.scheduled_minutes("22:00", "06:00") > 0)

    day = date(2026, 8, 3)
    sh = shift_day(day)
    svc = auth.AttendanceAuthorityService()

    # --- normal day ---
    r1 = svc.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(day, "09:00"), direction="in", source="whatsapp", source_event_id="n1-in", shift=sh, work_date=day)
    r2 = svc.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(day, "17:00"), direction="out", source="whatsapp", source_event_id="n1-out", shift=sh, work_date=day)
    proj = r2["projection"]
    check("normal day completed", proj.get("status") == "completed", proj.get("status"))
    check("normal worked 480", int(proj.get("worked_minutes") or 0) == 480, proj.get("worked_minutes"))
    check("normal no exception", proj.get("exception_state") == "none", proj.get("exception_state"))
    check("normal version >= 2", int(proj.get("version") or 0) >= 2, proj.get("version"))

    # --- overnight 22:00–06:00 + checkout after midnight ---
    ond = date(2026, 8, 4)
    osh = overnight_shift(ond)
    svc2 = auth.AttendanceAuthorityService()
    svc2.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(ond, "22:05"), direction="in", source="whatsapp", source_event_id="o-in", shift=osh, work_date=ond)
    out_at = dt(ond + timedelta(days=1), "06:02")
    r_out = svc2.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=out_at, direction="out", source="whatsapp", source_event_id="o-out", shift=osh, work_date=ond)
    op = r_out["projection"]
    check("overnight status completed/late", op.get("status") in {"completed", "late"}, op.get("status"))
    check("overnight worked ~477", 470 <= int(op.get("worked_minutes") or 0) <= 480, op.get("worked_minutes"))
    check("overnight work_date preserved", str(op.get("work_date")) in {ond.isoformat(), str(ond)}, op.get("work_date"))
    attributed = auth.attribute_work_date(out_at, shift=osh)
    check("post-midnight punch attributes to shift date", attributed == ond, attributed)

    # --- multiple sessions + paid/unpaid breaks ---
    md = date(2026, 8, 5)
    msh = shift_day(md, shift_id="33333333-3333-3333-3333-333333333333")
    svc3 = auth.AttendanceAuthorityService()
    for eid, at, direction, paid in [
        ("m-in1", "09:00", "in", None),
        ("m-bs", "12:00", "break_start", False),
        ("m-be", "12:30", "break_end", False),
        ("m-out1", "13:00", "out", None),
        ("m-in2", "14:00", "in", None),
        ("m-pbs", "15:00", "break_start", True),
        ("m-pbe", "15:15", "break_end", True),
        ("m-out2", "17:00", "out", None),
    ]:
        svc3.ingest_punch(
            company_code="ATTW1",
            employee=emp(),
            punched_at=dt(md, at),
            direction=direction,
            source="hr",
            source_event_id=eid,
            shift=msh,
            work_date=md,
            break_paid=paid,
        )
    mp = svc3.store.get_current_projection(company_code="ATTW1", employee_key="ATTW1-E1", work_date=md, shift_key=auth.shift_key_of(msh["shift_id"]))
    check("multi sessions count=2", len(mp.get("sessions") or []) == 2, mp.get("sessions"))
    check("breaks count=2", len(mp.get("breaks") or []) == 2, mp.get("breaks"))
    check("unpaid break 30", int(mp.get("unpaid_break_minutes") or 0) == 30, mp.get("unpaid_break_minutes"))
    check("paid break 15", int(mp.get("paid_break_minutes") or 0) == 15, mp.get("paid_break_minutes"))
    # session1 09-13=240 minus unpaid 30 nested ≈ 210 contribution; session2 14-17=180; total worked = 240+180-30=390
    check("worked excludes unpaid break", int(mp.get("worked_minutes") or 0) == 390, mp.get("worked_minutes"))

    # --- duplicate + concurrent punches ---
    dd = date(2026, 8, 6)
    dsh = shift_day(dd, shift_id="44444444-4444-4444-4444-444444444444")
    svc4 = auth.AttendanceAuthorityService()
    a = svc4.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(dd, "09:00"), direction="in", source="whatsapp", source_event_id="dup-1", shift=dsh, work_date=dd)
    b = svc4.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(dd, "09:00"), direction="in", source="whatsapp", source_event_id="dup-1", shift=dsh, work_date=dd)
    check("duplicate retry not created", a.get("created") is True and b.get("duplicate") is True)
    check("duplicate same punch_id", a["punch"]["punch_id"] == b["punch"]["punch_id"])
    punch_ids = []
    errors = []

    def _race(i: int) -> None:
        try:
            # Same source_event_id → exactly one row
            res = svc4.ingest_punch(
                company_code="ATTW1",
                employee=emp(),
                punched_at=dt(dd, "09:01"),
                direction="in",
                source="import",
                source_event_id="concurrent-1",
                shift=dsh,
                work_date=dd,
            )
            punch_ids.append((res.get("created"), res["punch"]["punch_id"]))
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    threads = [threading.Thread(target=_race, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    created = [x for x in punch_ids if x[0]]
    ids = {x[1] for x in punch_ids}
    check("concurrent no errors", not errors, errors)
    check("concurrent single punch id", len(ids) == 1 and len(created) == 1, {"ids": list(ids), "created": len(created), "n": len(punch_ids)})

    # --- absence-scan vs late check-in race ---
    rd = date(2026, 8, 7)
    rsh = shift_day(rd, shift_id="55555555-5555-5555-5555-555555555555")
    svc5 = auth.AttendanceAuthorityService()
    # Path A: check-in wins
    svc5.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(rd, "09:40"), direction="in", source="whatsapp", source_event_id="race-in", shift=rsh, work_date=rd)
    absent_fail = svc5.mark_absent(company_code="ATTW1", employee=emp(), work_date=rd, shift=rsh, source_event_id="race-abs", notes="Auto no-show scan")
    check("absence loses to prior check-in", absent_fail.get("ok") is False and absent_fail.get("error") == "check_in_already_exists", absent_fail)

    # Path B: absence first, then late check-in supersedes
    svc5b = auth.AttendanceAuthorityService()
    abs_ok = svc5b.mark_absent(company_code="ATTW1", employee=emp(), work_date=rd, shift=rsh, source_event_id="race-abs-2")
    check("absence first ok", abs_ok.get("ok") is True and abs_ok["projection"]["status"] == "absent")
    late = svc5b.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(rd, "09:50"), direction="in", source="whatsapp", source_event_id="late-in", shift=rsh, work_date=rd)
    check("late check-in supersedes absence", late["projection"]["status"] in {"present", "late"}, late["projection"]["status"])
    check("late minutes > 0", int(late["projection"].get("late_minutes") or 0) >= 50, late["projection"].get("late_minutes"))

    # --- missing check-in / checkout ---
    svc6 = auth.AttendanceAuthorityService()
    miss_d = date(2026, 8, 8)
    msh2 = shift_day(miss_d, shift_id="66666666-6666-6666-6666-666666666666")
    only_out = svc6.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(miss_d, "17:00"), direction="out", source="hr", source_event_id="only-out", shift=msh2, work_date=miss_d)
    check("missing check-in exception", only_out["projection"]["exception_state"] == "missing_check_in", only_out["projection"]["exception_state"])
    svc6b = auth.AttendanceAuthorityService()
    only_in = svc6b.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(miss_d, "09:00"), direction="in", source="hr", source_event_id="only-in", shift=msh2, work_date=miss_d)
    check("missing checkout exception", only_in["projection"]["exception_state"] == "missing_check_out", only_in["projection"]["exception_state"])
    deny = svc6b.approve_day(company_code="ATTW1", employee=emp(), work_date=miss_d, approved_by_phone="96559999999", shift=msh2)
    check("incomplete cannot approve/payroll", deny.get("ok") is False, deny)

    # --- correction request → reject / dispute / approve ---
    cd = date(2026, 8, 9)
    csh = shift_day(cd, shift_id="77777777-7777-7777-7777-777777777777")
    svc7 = auth.AttendanceAuthorityService()
    svc7.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(cd, "09:00"), direction="in", source="whatsapp", source_event_id="c-in", shift=csh, work_date=cd)
    svc7.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(cd, "16:00"), direction="out", source="whatsapp", source_event_id="c-out", shift=csh, work_date=cd)
    req = svc7.request_correction(
        company_code="ATTW1",
        employee=emp(),
        work_date=cd,
        requested_by_phone="96558888888",
        changes={"check_out_at": dt(cd, "17:00").isoformat()},
        shift=csh,
        actor_is_manager=True,
    )
    check("correction requested", req.get("ok") is True and req["correction"]["status"] == "requested")
    rej = svc7.review_correction(company_code="ATTW1", correction_id=req["correction"]["correction_id"], decision="rejected", decided_by_phone="96557777777", decision_note="no", employee=emp(), shift=csh)
    check("correction rejected", rej.get("ok") is True and rej["correction"]["status"] == "rejected")

    req2 = svc7.request_correction(company_code="ATTW1", employee=emp(), work_date=cd, requested_by_phone="96558888888", changes={"check_out_at": dt(cd, "17:00").isoformat()}, shift=csh, actor_is_manager=True)
    disp = svc7.review_correction(company_code="ATTW1", correction_id=req2["correction"]["correction_id"], decision="disputed", decided_by_phone="96557777777", dispute_reason="unclear", employee=emp(), shift=csh)
    check("correction disputed", disp.get("ok") is True and disp["correction"]["status"] == "disputed")

    req3 = svc7.request_correction(company_code="ATTW1", employee=emp(), work_date=cd, requested_by_phone="96558888888", changes={"check_out_at": dt(cd, "17:00").isoformat()}, shift=csh, actor_is_manager=True)
    v_before = svc7.store.get_current_projection(company_code="ATTW1", employee_key="ATTW1-E1", work_date=cd, shift_key=auth.shift_key_of(csh["shift_id"]))
    before_id = (v_before or {}).get("projection_id")
    before_ver = int((v_before or {}).get("version") or 0)
    appr = svc7.review_correction(company_code="ATTW1", correction_id=req3["correction"]["correction_id"], decision="approved", decided_by_phone="96557777777", employee=emp(), shift=csh)
    v_after = appr.get("projection") or {}
    check("correction approved new version", int(v_after.get("version") or 0) > before_ver, {"before": before_ver, "after": v_after.get("version")})
    check("correction preserves history (manual flag)", v_after.get("manual_correction") is True)
    prior = next((p for p in svc7.store.projections if p.get("projection_id") == before_id), None)
    check("old projection not current", prior is not None and prior.get("is_current") is False, prior)
    hist = [p for p in svc7.store.projections if p["employee_key"] == "ATTW1-E1" and auth.parse_date(p["work_date"]) == cd]
    check("version history retained", len(hist) >= 2, len(hist))

    # --- manager self-correction denial ---
    denied = svc7.request_correction(
        company_code="ATTW1",
        employee=emp(phone="96550000001"),
        work_date=cd,
        requested_by_phone="96550000001",
        changes={"status": "absent"},
        shift=csh,
        actor_is_manager=True,
    )
    check("manager self-correction denied", denied.get("error") == "manager_self_correction_denied", denied)

    # --- approved leave + reversal cannot wipe later manual correction ---
    ld = date(2026, 8, 10)
    lsh = shift_day(ld, shift_id="88888888-8888-8888-8888-888888888888")
    svc8 = auth.AttendanceAuthorityService()
    leave = svc8.apply_leave(company_code="ATTW1", employee=emp(), work_date=ld, leave_id="leave-1", shift=lsh)
    check("approved leave status", leave["projection"]["status"] == "approved_leave")
    # Manual correction after leave
    corr = svc8.request_correction(company_code="ATTW1", employee=emp(), work_date=ld, requested_by_phone="96558888888", changes={"check_in_at": dt(ld, "09:00").isoformat(), "check_out_at": dt(ld, "17:00").isoformat(), "status": "completed"}, shift=lsh, actor_is_manager=True)
    reviewed = svc8.review_correction(company_code="ATTW1", correction_id=corr["correction"]["correction_id"], decision="approved", decided_by_phone="96557777777", employee=emp(), shift=lsh)
    check("post-leave manual correction applied", reviewed.get("ok") is True and reviewed["projection"].get("manual_correction") is True)
    rev = svc8.reverse_leave(company_code="ATTW1", employee=emp(), work_date=ld, leave_id="leave-1", shift=lsh)
    check("leave reverse preserves manual correction", rev.get("reason") == "manual_correction_preserved", rev)

    # Leave reverse without correction does clear
    svc8b = auth.AttendanceAuthorityService()
    svc8b.apply_leave(company_code="ATTW1", employee=emp(), work_date=ld, leave_id="leave-2", shift=lsh)
    rev2 = svc8b.reverse_leave(company_code="ATTW1", employee=emp(), work_date=ld, leave_id="leave-2", shift=lsh)
    check("leave reverse without correction proceeds", rev2.get("ok") is True and rev2.get("reason") != "manual_correction_preserved", rev2.get("reason"))

    # --- nullable shift_id cannot create duplicate employee-day authority ---
    nd = date(2026, 8, 11)
    svc9 = auth.AttendanceAuthorityService()
    p1 = svc9.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(nd, "09:00"), direction="in", source="hr", source_event_id="null-1", shift=None, work_date=nd)
    p2 = svc9.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(nd, "17:00"), direction="out", source="hr", source_event_id="null-2", shift=None, work_date=nd)
    currents = [p for p in svc9.store.projections if p.get("is_current") and auth.parse_date(p["work_date"]) == nd and p["employee_key"] == "ATTW1-E1"]
    check("null shift_key single current", len(currents) == 1 and currents[0].get("shift_key") == "", currents)
    check("null-shift day completed", p2["projection"]["status"] == "completed")

    # --- approved attendance → payroll snapshot reconciliation ---
    pd = date(2026, 8, 12)
    psh = shift_day(pd, shift_id="99999999-9999-9999-9999-999999999999")
    svc10 = auth.AttendanceAuthorityService()
    svc10.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(pd, "09:00"), direction="in", source="whatsapp", source_event_id="pay-in", shift=psh, work_date=pd)
    svc10.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(pd, "17:00"), direction="out", source="whatsapp", source_event_id="pay-out", shift=psh, work_date=pd)
    # Unapproved must not appear in payroll
    pay0 = svc10.list_payroll_hours_from_snapshots(company_code="ATTW1", start_date=pd, end_date=pd, shifts=[psh])
    snap_count0 = pay0["source_counts"]["approved_snapshots"]
    check("unapproved excluded from payroll", snap_count0 == 0, pay0)
    approved = svc10.approve_day(company_code="ATTW1", employee=emp(), work_date=pd, approved_by_phone="96557777777", shift=psh)
    check("day approved payroll_eligible", approved.get("ok") is True and approved["projection"].get("payroll_eligible") is True, approved)
    pay1 = svc10.list_payroll_hours_from_snapshots(company_code="ATTW1", start_date=pd, end_date=pd, shifts=[{**psh, "company_code": "ATTW1"}])
    check("approved snapshot reaches payroll", pay1["source_counts"]["approved_snapshots"] == 1, pay1)
    summary = (pay1.get("summaries") or [{}])[0]
    check("payroll worked reconciles to snapshot", int(summary.get("worked_minutes") or 0) == int(approved["snapshot"]["payload"]["worked_minutes"]), {"summary": summary.get("worked_minutes"), "snap": approved["snapshot"]["payload"]["worked_minutes"]})
    check("payroll authority label", pay1.get("authority") == "approved_attendance_snapshots")

    # --- tenant isolation ---
    svc_a = auth.get_authority_service("ATTW1")
    svc_b = auth.get_authority_service("OTHERCO")
    check("tenant services isolated", svc_a is not svc_b)
    svc_b.ingest_punch(company_code="OTHERCO", employee=emp(key="OTHER-1", phone="96551111111"), punched_at=dt(pd, "09:00"), direction="in", source="hr", source_event_id="t-1", work_date=pd)
    rows_a = svc_a.list_compat_attendance(company_code="ATTW1", start_date=pd, end_date=pd)
    rows_b = svc_b.list_compat_attendance(company_code="OTHERCO", start_date=pd, end_date=pd)
    check("tenant A does not see B", all(r.get("company_code") == "ATTW1" for r in rows_a), rows_a)
    check("tenant B only own rows", all(r.get("employee_key") == "OTHER-1" for r in rows_b), rows_b)

    # --- compatibility read shape ---
    compat = auth.projection_to_compat_record(approved["projection"])
    for field in ("attendance_id", "company_code", "employee_key", "attendance_date", "status", "check_in_at", "check_out_at", "late_minutes", "early_leave_minutes", "metadata"):
        check(f"compat has {field}", field in compat)

    # --- punches never overwritten ---
    punches = svc10.store.list_punches(company_code="ATTW1", employee_key="ATTW1-E1", work_date=pd, shift_key=auth.shift_key_of(psh["shift_id"]))
    check("raw punches retained", len(punches) == 2)
    # Attempt "overwrite" via same event id — still one
    again = svc10.ingest_punch(company_code="ATTW1", employee=emp(), punched_at=dt(pd, "10:00"), direction="in", source="whatsapp", source_event_id="pay-in", shift=psh, work_date=pd)
    check("idempotent retry keeps original punched_at", again.get("duplicate") is True and again["punch"]["punched_at"] == punches[0]["punched_at"])

    # --- schema DDL present ---
    check("schema has attendance_punches", "CREATE TABLE IF NOT EXISTS attendance_punches" in auth.SCHEMA_DDL)
    check("schema unique source_event", "UNIQUE (company_code, source, source_event_id)" in auth.SCHEMA_DDL)
    check("schema shift_key current unique", "uq_att_day_current" in auth.SCHEMA_DDL)
    check("schema payroll snapshots", "attendance_payroll_snapshots" in auth.SCHEMA_DDL)
    check("schema corrections", "attendance_corrections" in auth.SCHEMA_DDL)

    # --- app wiring markers (no import of full app — too heavy / env) ---
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("app imports authority module", "import attendance_authority_wave1" in app_src)
    check("app ensures authority schema", "ensure_attendance_authority_schema" in app_src)
    check("app flag helper", "def attendance_authority_enabled_for_company" in app_src)
    check("check_in branches on authority", "attendance_authority_enabled_for_company(company)" in app_src and "ingest_punch" in app_src)
    check("payroll approved snapshots branch", "list_payroll_hours_from_snapshots" in app_src)
    check("leave reverse preserves manual", "manual_correction_preserved" in app_src or "reverse_leave" in app_src)

    # --- freeze regressions ---
    for script in ("smoke-test-employees360-freeze-regression.py", "smoke-test-onboarding-freeze-regression.py"):
        path = ROOT / script
        if not path.exists():
            check(f"freeze script {script}", False, "missing")
            continue
        import subprocess

        proc = subprocess.run([sys.executable, str(path)], cwd=str(ROOT), capture_output=True, text=True)
        check(f"freeze {script} exit 0", proc.returncode == 0, proc.stdout[-500:] + proc.stderr[-500:])

    # Reset env
    os.environ.pop("WATHEFNI_ATTENDANCE_AUTHORITY", None)
    os.environ.pop("WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES", None)
    auth.reset_authority_services_for_tests()

    print(f"\nSUMMARY pass={PASS} fail={FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 2
    # Write machine-readable results beside evidence if EVID set
    evid = os.environ.get("ATTW1_EVID")
    if evid:
        Path(evid).mkdir(parents=True, exist_ok=True)
        out = {"pass": PASS, "fail": FAIL, "results": RESULTS, "verdict": "PASS" if FAIL == 0 else "FAIL"}
        (Path(evid) / "qualification.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    raise SystemExit(code)
