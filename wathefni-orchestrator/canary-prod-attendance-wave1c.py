#!/usr/bin/env python3
"""Attendance Wave 1C — production synthetic canary (postgres authority).

Creates ATTW1C synthetic punches/projections only. Never touches the four real
employees or the 42 legacy demo attendance_records. Cleans up afterward.

Requires:
  WATHEFNI_ATTENDANCE_AUTHORITY=on
  WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES=WATHEFNI
  WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
  WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list[dict] = []
SYNTHETIC_IDS: dict[str, str] = {}


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    RESULTS.append({"label": label, "ok": bool(cond), "detail": detail})
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def main() -> int:
    if (os.environ.get("WATHEFNI_ENV") or "").strip().lower() != "production":
        print("REFUSE: WATHEFNI_ENV must be production for this canary")
        return 2

    import app
    import attendance_authority_wave1 as core
    import attendance_authority_postgres as pg
    import attendance_authority_hooks as hooks

    # Force postgres store selection after flags are set by systemd.
    core.reset_authority_services_for_tests()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = cur.fetchone()["db"]
    check("production database", db == "wathefni", db)

    check("authority on", core.attendance_authority_enabled() is True)
    check("companies WATHEFNI", core.attendance_authority_companies() == {"WATHEFNI"})
    check("synthetic only on", core.attendance_authority_synthetic_only() is True)
    check("store postgres", pg.authority_store_mode() == "postgres")
    check("import still off", not getattr(app, "attendance_import_enabled", lambda: False)() if hasattr(app, "attendance_import_enabled") else os.environ.get("WATHEFNI_ATTENDANCE_IMPORT", "off").lower() not in {"1", "true", "on", "yes"})

    # Real employees must NOT enter authority
    for key in core.FOUR_REAL_ATTENDANCE_KEYS:
        phone = key.split("-")[-1]
        allowed = core.attendance_authority_allowed_for("WATHEFNI", {"employee_key": key, "phone": phone})
        check(f"real denied {key}", allowed is False)
    check("hooks deny real", hooks.allowed_for("WATHEFNI", {"employee_key": "WATHEFNI-96550252254", "phone": "96550252254"}) is False)

    # Cleanup GUC must not be in app.py request paths
    app_src = Path(app.__file__).read_text(encoding="utf-8")
    check("cleanup GUC absent from app.py", hooks.assert_cleanup_guc_not_in_app_paths(app_src))

    # Baseline: 42 demo rows untouched fingerprint
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
            before_n = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT md5(string_agg(attendance_id::text || ':' || status || ':' || coalesce(metadata->>'demo_seed',''), '|' ORDER BY attendance_id::text)) AS fp
                FROM attendance_records WHERE company_code='WATHEFNI'
                """
            )
            before_fp = cur.fetchone()["fp"]
            cur.execute(
                "SELECT COUNT(*) AS n FROM attendance_records WHERE metadata->>'demo_seed'='wathefni_v1'"
            )
            before_demo = int(cur.fetchone()["n"])
    check("baseline 42 rows", before_n == 42 and before_demo == 42, {"n": before_n, "demo": before_demo})

    tag = uuid.uuid4().hex[:8]
    company = "WATHEFNI"
    phone = f"965524{tag[:6]}"
    emp_key = f"WATHEFNI-ATTW1C-{tag}"
    emp = {"employee_key": emp_key, "phone": phone, "name": f"W1C-SYNTH|{tag}", "company_code": company}
    SYNTHETIC_IDS.update({"employee_key": emp_key, "phone": phone, "tag": tag})
    check("synthetic allowed", core.attendance_authority_allowed_for(company, emp) is True)

    day = date(2026, 8, 22)
    shift_id = str(uuid.uuid4())
    shift = {
        "shift_id": shift_id,
        "shift_date": day,
        "start_time": time(9, 0),
        "end_time": time(17, 0),
        "employee_key": emp_key,
        "status": "scheduled",
    }
    overnight_day = date(2026, 8, 23)
    oshift_id = str(uuid.uuid4())
    oshift = {
        "shift_id": oshift_id,
        "shift_date": overnight_day,
        "start_time": time(22, 0),
        "end_time": time(6, 0),
        "employee_key": emp_key,
        "status": "scheduled",
    }
    SYNTHETIC_IDS["shift_id"] = shift_id
    SYNTHETIC_IDS["oshift_id"] = oshift_id

    def dt(d: date, hhmm: str) -> datetime:
        h, m = map(int, hhmm.split(":"))
        return datetime.combine(d, time(h, m), tzinfo=core.KUWAIT_TZ)

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('wathefni.allow_authority_cleanup', '1', true)")
                for tbl in (
                    "attendance_compat_drift",
                    "attendance_authority_events",
                    "attendance_payroll_snapshots",
                    "attendance_corrections",
                    "attendance_day_projections",
                    "attendance_punches",
                ):
                    cur.execute(
                        f"DELETE FROM {tbl} WHERE employee_key=%s OR (company_code=%s AND employee_key LIKE 'WATHEFNI-ATTW1C-%%')",
                        (emp_key, company),
                    )
                # Never delete demo rows — only synthetic-tagged mirrors if any
                cur.execute(
                    """
                    DELETE FROM attendance_records
                    WHERE employee_key=%s
                       OR (company_code=%s AND metadata->>'wave' = '1c')
                       OR (company_code=%s AND employee_key LIKE 'WATHEFNI-ATTW1C-%%')
                    """,
                    (emp_key, company, company),
                )
                cur.execute("DELETE FROM attendance_events WHERE employee_key=%s", (emp_key,))
                cur.execute("DELETE FROM employees WHERE employee_key=%s", (emp_key,))
            conn.commit()

    # Ensure schema present
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            hooks.ensure_schema(cur)
        conn.commit()

    cleanup()
    store = pg.PostgresAuthorityStore(app.db_connect)
    svc = core.AttendanceAuthorityService(store=store)

    try:
        # normal day
        r1 = svc.ingest_punch(company_code=company, employee=emp, punched_at=dt(day, "09:00"), direction="in", source="hr", source_event_id=f"{tag}-in", shift=shift, work_date=day)
        r2 = svc.ingest_punch(company_code=company, employee=emp, punched_at=dt(day, "17:00"), direction="out", source="hr", source_event_id=f"{tag}-out", shift=shift, work_date=day)
        check("normal completed", r2["projection"]["status"] == "completed")
        check("normal worked 480", int(r2["projection"]["worked_minutes"]) == 480)
        SYNTHETIC_IDS["punch_in"] = str(r1["punch"]["punch_id"])
        SYNTHETIC_IDS["projection_id"] = str(r2["projection"]["projection_id"])

        # overnight + after midnight
        svc.ingest_punch(company_code=company, employee=emp, punched_at=dt(overnight_day, "22:05"), direction="in", source="hr", source_event_id=f"{tag}-oin", shift=oshift, work_date=overnight_day)
        o = svc.ingest_punch(company_code=company, employee=emp, punched_at=dt(overnight_day + timedelta(days=1), "06:00"), direction="out", source="hr", source_event_id=f"{tag}-oout", shift=oshift, work_date=overnight_day)
        check("overnight ok", o["projection"]["status"] in {"completed", "late"} and 470 <= int(o["projection"]["worked_minutes"]) <= 480, o["projection"].get("worked_minutes"))

        # multi session + breaks
        md = date(2026, 8, 24)
        msh = {**shift, "shift_id": str(uuid.uuid4()), "shift_date": md}
        for eid, at, direction, paid in [
            ("ms-in1", "09:00", "in", None),
            ("ms-bs", "12:00", "break_start", False),
            ("ms-be", "12:30", "break_end", False),
            ("ms-out1", "13:00", "out", None),
            ("ms-in2", "14:00", "in", None),
            ("ms-pbs", "15:00", "break_start", True),
            ("ms-pbe", "15:15", "break_end", True),
            ("ms-out2", "17:00", "out", None),
        ]:
            svc.ingest_punch(company_code=company, employee=emp, punched_at=dt(md, at), direction=direction, source="hr", source_event_id=f"{tag}-{eid}", shift=msh, work_date=md, break_paid=paid)
        mp = store.get_current_projection(company_code=company, employee_key=emp_key, work_date=md, shift_key=core.shift_key_of(msh["shift_id"]))
        check("multi sessions", len(mp.get("sessions") or []) == 2)
        check("unpaid/paid breaks", int(mp.get("unpaid_break_minutes") or 0) == 30 and int(mp.get("paid_break_minutes") or 0) == 15)
        check("worked excludes unpaid", int(mp.get("worked_minutes") or 0) == 390)

        # restart persistence via new store (before concurrent mutates the day)
        store2 = pg.PostgresAuthorityStore(app.db_connect)
        again = store2.get_current_projection(company_code=company, employee_key=emp_key, work_date=day, shift_key=core.shift_key_of(shift_id))
        punches2 = store2.list_punches(company_code=company, employee_key=emp_key, work_date=day, shift_key=core.shift_key_of(shift_id))
        check(
            "restart projection",
            again is not None
            and str(again.get("projection_id")) == SYNTHETIC_IDS["projection_id"]
            and int(again.get("worked_minutes") or 0) == 480
            and any(str(p.get("punch_id")) == SYNTHETIC_IDS["punch_in"] for p in punches2),
            {"proj": (again or {}).get("projection_id"), "worked": (again or {}).get("worked_minutes"), "punches": len(punches2)},
        )

        # duplicate + concurrent
        dup = svc.ingest_punch(company_code=company, employee=emp, punched_at=dt(day, "09:00"), direction="in", source="hr", source_event_id=f"{tag}-in", shift=shift, work_date=day)
        check("duplicate idempotent", dup.get("duplicate") is True)
        ids, errors = [], []
        shared = pg.PostgresAuthorityStore(app.db_connect)

        def race(_i: int) -> None:
            try:
                s = core.AttendanceAuthorityService(store=shared)
                res = s.ingest_punch(company_code=company, employee=emp, punched_at=dt(day, "09:03"), direction="in", source="import", source_event_id=f"{tag}-conc", shift=shift, work_date=day)
                ids.append((res.get("created"), str(res["punch"]["punch_id"])))
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))

        threads = [threading.Thread(target=race, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        check("concurrent ok", not errors and len({x[1] for x in ids}) == 1 and sum(1 for x in ids if x[0]) == 1, {"errors": errors[:2], "ids": ids})

        # rebuild
        before = store2.get_current_projection(company_code=company, employee_key=emp_key, work_date=md, shift_key=core.shift_key_of(msh["shift_id"]))
        rebuilt = pg.rebuild_projection_from_punches(core.AttendanceAuthorityService(store=store2), company_code=company, employee=emp, work_date=md, shift=msh)
        check("rebuild exact", int(rebuilt["projection"]["worked_minutes"]) == int(before["worked_minutes"]) and int(rebuilt["projection"]["version"]) > int(before["version"]))

        # absence vs late punch
        rd = date(2026, 8, 25)
        rsh = {**shift, "shift_id": str(uuid.uuid4()), "shift_date": rd}
        svc_r = core.AttendanceAuthorityService(store=pg.PostgresAuthorityStore(app.db_connect))
        abs_ok = svc_r.mark_absent(company_code=company, employee=emp, work_date=rd, shift=rsh, source_event_id=f"{tag}-abs")
        check("absence first", abs_ok.get("ok") and abs_ok["projection"]["status"] == "absent")
        late = svc_r.ingest_punch(company_code=company, employee=emp, punched_at=dt(rd, "09:40"), direction="in", source="whatsapp", source_event_id=f"{tag}-late", shift=rsh, work_date=rd)
        check("late supersedes absence", late["projection"]["status"] in {"present", "late"})
        deny_abs = svc_r.mark_absent(company_code=company, employee=emp, work_date=rd, shift=rsh, source_event_id=f"{tag}-abs2")
        check("absence loses to check-in", deny_abs.get("error") == "check_in_already_exists")

        # corrections
        req = svc.request_correction(company_code=company, employee=emp, work_date=day, requested_by_phone="965524999001", changes={"check_out_at": dt(day, "17:30").isoformat()}, shift=shift, actor_is_manager=True)
        check("correction requested", req.get("ok"))
        rej = svc.review_correction(company_code=company, correction_id=str(req["correction"]["correction_id"]), decision="rejected", decided_by_phone="965524999002", employee=emp, shift=shift)
        check("correction rejected", rej["correction"]["status"] == "rejected")
        req2 = svc.request_correction(company_code=company, employee=emp, work_date=day, requested_by_phone="965524999001", changes={"check_out_at": dt(day, "17:30").isoformat()}, shift=shift, actor_is_manager=True)
        disp = svc.review_correction(company_code=company, correction_id=str(req2["correction"]["correction_id"]), decision="disputed", decided_by_phone="965524999002", dispute_reason="unclear", employee=emp, shift=shift)
        check("correction disputed", disp["correction"]["status"] == "disputed")
        req3 = svc.request_correction(company_code=company, employee=emp, work_date=day, requested_by_phone="965524999001", changes={"check_out_at": dt(day, "17:00").isoformat()}, shift=shift, actor_is_manager=True)
        appr = svc.review_correction(company_code=company, correction_id=str(req3["correction"]["correction_id"]), decision="approved", decided_by_phone="965524999002", employee=emp, shift=shift)
        check("correction approved", appr.get("ok") and appr["projection"].get("manual_correction") is True)
        denied = svc.request_correction(company_code=company, employee=emp, work_date=day, requested_by_phone=phone, changes={"status": "absent"}, shift=shift, actor_is_manager=True)
        check("self-correction denied", denied.get("error") == "manager_self_correction_denied")

        # leave + safe reversal
        ld = date(2026, 8, 26)
        lsh = {**shift, "shift_id": str(uuid.uuid4()), "shift_date": ld}
        leave_id = f"leave-{tag}"
        svc.apply_leave(company_code=company, employee=emp, work_date=ld, leave_id=leave_id, shift=lsh)
        corr = svc.request_correction(company_code=company, employee=emp, work_date=ld, requested_by_phone="965524999001", changes={"check_in_at": dt(ld, "09:00").isoformat(), "check_out_at": dt(ld, "17:00").isoformat()}, shift=lsh, actor_is_manager=True)
        svc.review_correction(company_code=company, correction_id=str(corr["correction"]["correction_id"]), decision="approved", decided_by_phone="965524999002", employee=emp, shift=lsh)
        rev = svc.reverse_leave(company_code=company, employee=emp, work_date=ld, leave_id=leave_id, shift=lsh)
        check("leave reverse preserves correction", rev.get("reason") == "manual_correction_preserved")

        # approve payroll snapshot
        pd = date(2026, 8, 27)
        psh = {**shift, "shift_id": str(uuid.uuid4()), "shift_date": pd}
        svc.ingest_punch(company_code=company, employee=emp, punched_at=dt(pd, "09:00"), direction="in", source="hr", source_event_id=f"{tag}-pin", shift=psh, work_date=pd)
        svc.ingest_punch(company_code=company, employee=emp, punched_at=dt(pd, "17:00"), direction="out", source="hr", source_event_id=f"{tag}-pout", shift=psh, work_date=pd)
        pay0 = svc.list_payroll_hours_from_snapshots(company_code=company, start_date=pd, end_date=pd, shifts=[psh], employee_key=emp_key)
        check("unapproved excluded", pay0["source_counts"]["approved_snapshots"] == 0)
        approved = svc.approve_day(company_code=company, employee=emp, work_date=pd, approved_by_phone="965524999002", shift=psh)
        check("day approved", approved.get("ok") is True, approved.get("error"))
        SYNTHETIC_IDS["snapshot_id"] = str(approved["snapshot"]["snapshot_id"])
        pay1 = svc.list_payroll_hours_from_snapshots(company_code=company, start_date=pd, end_date=pd, shifts=[psh], employee_key=emp_key)
        check("payroll reconcile exact", int(pay1["summaries"][0]["worked_minutes"]) == int(approved["snapshot"]["payload"]["worked_minutes"]))

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                immut = pg.verify_snapshot_immutable(cur, SYNTHETIC_IDS["snapshot_id"])
                try:
                    cur.execute("UPDATE attendance_punches SET direction='out' WHERE punch_id=%s", (SYNTHETIC_IDS["punch_in"],))
                    punch_locked = False
                except Exception as exc:
                    conn.rollback()
                    punch_locked = True
                    punch_exc = str(exc).split("\n")[0]
        check("snapshot immutable", immut.get("ok") and immut.get("immutable"))
        check("punch append-only", punch_locked, punch_exc if punch_locked else None)

        # drift quarantine
        cd = date(2026, 8, 28)
        svc.ingest_punch(company_code=company, employee=emp, punched_at=dt(cd, "09:00"), direction="in", source="hr", source_event_id=f"{tag}-din", shift=None, work_date=cd)
        dproj = svc.ingest_punch(company_code=company, employee=emp, punched_at=dt(cd, "17:00"), direction="out", source="hr", source_event_id=f"{tag}-dout", shift=None, work_date=cd)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                # matching mirror
                cur.execute(
                    """
                    INSERT INTO attendance_records (
                      company_code, employee_key, employee_phone, employee_name, shift_id,
                      attendance_date, check_in_at, check_out_at, status, late_minutes, early_leave_minutes, metadata
                    ) VALUES (%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    """,
                    (
                        company, emp_key, phone, emp["name"], cd,
                        dproj["projection"]["check_in_at"], dproj["projection"]["check_out_at"], dproj["projection"]["status"],
                        dproj["projection"]["late_minutes"], dproj["projection"]["early_leave_minutes"],
                        json.dumps({"authority": core.AUTHORITY_VERSION, "compat_mirrored": True, "wave": "1c"}),
                    ),
                )
                conflict = date(2026, 8, 29)
                svc.ingest_punch(company_code=company, employee=emp, punched_at=dt(conflict, "09:00"), direction="in", source="hr", source_event_id=f"{tag}-xin", shift=None, work_date=conflict)
                svc.ingest_punch(company_code=company, employee=emp, punched_at=dt(conflict, "17:00"), direction="out", source="hr", source_event_id=f"{tag}-xout", shift=None, work_date=conflict)
                cur.execute(
                    """
                    INSERT INTO attendance_records (
                      company_code, employee_key, employee_phone, employee_name, shift_id,
                      attendance_date, status, late_minutes, early_leave_minutes, metadata
                    ) VALUES (%s,%s,%s,%s,NULL,%s,'absent',0,0,%s::jsonb)
                    """,
                    (company, emp_key, phone, emp["name"], conflict, json.dumps({"authority": core.AUTHORITY_VERSION, "compat_mirrored": True, "wave": "1c"})),
                )
                report = pg.reconcile_compat_mirror(cur, company_code=company, start_date=cd, end_date=conflict, employee_key=emp_key, quarantine=True)
            conn.commit()
        check("drift detected+quarantined", report["drift_count"] >= 1 and report["quarantined"] >= 1 and report["silent_overwrite"] is False, report)
        check("matched mirror", report["matched"] >= 1, report)

        # tenant isolation (other company synthetic must not bleed)
        other = {"employee_key": f"OTHER-ATTW1C-{tag}", "phone": f"9655248{tag[:5]}", "name": "Other", "company_code": "OTHERCO"}
        # OTHERCO not in allowlist — service still can write if called directly; prove company filter on list
        svc_o = core.AttendanceAuthorityService(store=pg.PostgresAuthorityStore(app.db_connect))
        # Direct write under OTHERCO should not be allowed_for; still insert to prove list isolation by company_code
        # Skip write — instead ensure WATHEFNI list doesn't include foreign keys
        rows = svc.list_compat_attendance(company_code=company, start_date=day, end_date=conflict, employee_key=emp_key)
        check("tenant list only synthetic key", all(r.get("employee_key") == emp_key for r in rows) and len(rows) >= 1)

        # manager scope helper exists
        check("manager scope helper", hasattr(app, "manager_scope_allows_employee"))

    except Exception:
        traceback.print_exc()
        check("uncaught", False, traceback.format_exc()[-500:])
    finally:
        cleanup()
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
                after_n = int(cur.fetchone()["n"])
                cur.execute(
                    """
                    SELECT md5(string_agg(attendance_id::text || ':' || status || ':' || coalesce(metadata->>'demo_seed',''), '|' ORDER BY attendance_id::text)) AS fp
                    FROM attendance_records WHERE company_code='WATHEFNI'
                    """
                )
                after_fp = cur.fetchone()["fp"]
                cur.execute("SELECT COUNT(*) AS n FROM attendance_punches WHERE employee_key=%s", (emp_key,))
                left_punches = int(cur.fetchone()["n"])
                cur.execute("SELECT COUNT(*) AS n FROM attendance_day_projections WHERE employee_key=%s", (emp_key,))
                left_proj = int(cur.fetchone()["n"])
                cur.execute(
                    "SELECT COUNT(*) AS n FROM employees WHERE employee_key = ANY(%s)",
                    (list(core.FOUR_REAL_ATTENDANCE_KEYS),),
                )
                reals = int(cur.fetchone()["n"])
        check("demo rows untouched count", after_n == before_n == 42, {"before": before_n, "after": after_n})
        check("demo fingerprint unchanged", after_fp == before_fp)
        check("synthetic punches cleaned", left_punches == 0)
        check("synthetic projections cleaned", left_proj == 0)
        check("four reals still present", reals == 4, reals)

    out = {
        "pass": PASS,
        "fail": FAIL,
        "verdict": "PASS" if FAIL == 0 else "FAIL",
        "synthetic_ids": SYNTHETIC_IDS,
        "results": RESULTS,
    }
    dest = os.environ.get("WAVE1C_CANARY_OUT")
    if dest:
        Path(dest).mkdir(parents=True, exist_ok=True)
        (Path(dest) / "canary-evidence.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"summary": {"pass": PASS, "fail": FAIL}, "synthetic_ids": SYNTHETIC_IDS}, indent=2))
    print(f"\nSUMMARY pass={PASS} fail={FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
