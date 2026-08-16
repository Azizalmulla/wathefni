#!/usr/bin/env python3
"""Attendance Wave 3 — production WATHEFNI-only synthetic ops canary.

Boundaries (strict):
  - Synthetic attendance data only (W3-SYNTH| / ATTW3 / 965524*)
  - CAPTURE_INGEST=off
  - No real employee clocking
  - No biometric devices or connectors
  - No payroll impact on real employees
  - No external tenants
  - No UI redesign

Cleans up all synthetic ops/authority rows afterward.
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
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
RESULTS: list[dict[str, Any]] = []
KUWAIT = ZoneInfo("Asia/Kuwait")


def check(label: str, cond: bool, detail: Any = None) -> None:
    global PASS, FAIL

    def _j(v: Any) -> Any:
        if v is None or isinstance(v, (str, int, float, bool)):
            return v
        if isinstance(v, (datetime, date, time)):
            return v.isoformat()
        if isinstance(v, dict):
            return {str(k): _j(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [_j(x) for x in v]
        return str(v)

    RESULTS.append({"label": label, "ok": bool(cond), "detail": _j(detail) if not cond else None})
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def dt(d: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=KUWAIT)


def main() -> int:
    if (os.environ.get("WATHEFNI_ENV") or "").strip().lower() != "production":
        print("REFUSE: WATHEFNI_ENV must be production")
        return 2

    # Keep ingest off regardless of caller
    os.environ["WATHEFNI_ATTENDANCE_CAPTURE_INGEST"] = "off"
    os.environ.setdefault("WATHEFNI_ATTENDANCE_OPS_SYNTHETIC_ONLY", "on")

    try:
        import app
        import attendance_authority_postgres as auth_pg
        import attendance_authority_wave1 as core
        import attendance_ops_postgres as ops_pg
        import attendance_ops_wave3 as ops
    except Exception as exc:  # noqa: BLE001
        print("BOOT_FAIL", exc)
        traceback.print_exc()
        return 2

    core.reset_authority_services_for_tests()
    ops.reset_ops_services_for_tests()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = cur.fetchone()["db"]
    check("production database", db == "wathefni", db)

    check("ops enabled", ops.ops_enabled() is True)
    check("ops companies WATHEFNI", "WATHEFNI" in ops.ops_companies(), ops.ops_companies())
    check("ops store postgres", ops.ops_store_mode() == "postgres", ops.ops_store_mode())
    check("ops synthetic only", ops.ops_synthetic_only() is True)
    check("authority synthetic only", core.attendance_authority_synthetic_only() is True)
    check("capture ingest off", (os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST") or "").lower() in {"", "0", "false", "no", "off"} or not getattr(app, "attendance_capture_ingest_enabled", lambda: False)())
    if hasattr(app, "attendance_capture_ingest_enabled"):
        check("app capture ingest off", app.attendance_capture_ingest_enabled() is False)
    check("import off", not getattr(app, "attendance_import_enabled", lambda: True)())

    tag = uuid.uuid4().hex[:8]
    company = "WATHEFNI"
    other = "OTHERCO"
    emp_key = f"W3-SYNTH|{tag}"
    emp_phone = f"96552470{tag[:4]}"
    mgr_phone = f"96552471{tag[:4]}"
    mgr2_phone = f"96552472{tag[:4]}"
    hr_phone = f"96552473{tag[:4]}"
    out_mgr = f"96552474{tag[:4]}"
    emp = {"employee_key": emp_key, "phone": emp_phone, "name": f"Wave3 Canary {tag}", "company_code": company}
    emp_other = {"employee_key": f"W3-SYNTH|OUT-{tag}", "phone": f"96552475{tag[:4]}", "name": "Other", "company_code": other}

    check("synthetic employee allowed", ops.ops_allowed_for(company, emp) is True)
    for key in core.FOUR_REAL_ATTENDANCE_KEYS:
        phone = key.split("-")[-1]
        check(
            f"real denied ops {key[-8:]}",
            ops.ops_allowed_for(company, {"employee_key": key, "phone": phone}) is False,
        )
        check(
            f"real denied authority {key[-8:]}",
            core.attendance_authority_allowed_for(company, {"employee_key": key, "phone": phone}) is False,
        )

    # Baseline fingerprints (must remain unchanged)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
            before_att = int(cur.fetchone()["n"])
            cur.execute(
                "SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI' AND metadata->>'demo_seed'='wathefni_v1'"
            )
            before_demo = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT md5(string_agg(attendance_id::text || ':' || status || ':' || coalesce(metadata->>'demo_seed',''), '|'
                           ORDER BY attendance_id::text)) AS fp
                FROM attendance_records WHERE company_code='WATHEFNI'
                """
            )
            before_att_fp = cur.fetchone()["fp"]
            cur.execute(
                "SELECT COUNT(*) AS n FROM employees WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)",
                (list(core.FOUR_REAL_ATTENDANCE_KEYS),),
            )
            before_four = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT md5(string_agg(timesheet_id::text || ':' || status || ':' || employee_key, '|'
                           ORDER BY timesheet_id::text)) AS fp,
                       COUNT(*) AS n
                FROM payroll_timesheets
                WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)
                """,
                (list(core.FOUR_REAL_ATTENDANCE_KEYS),),
            )
            row = cur.fetchone()
            before_ts_fp, before_ts_n = row["fp"], int(row["n"])
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM attendance_payroll_snapshots
                WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)
                """,
                (list(core.FOUR_REAL_ATTENDANCE_KEYS),),
            )
            before_snap_reals = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM attendance_day_projections
                WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)
                """,
                (list(core.FOUR_REAL_ATTENDANCE_KEYS),),
            )
            before_proj_reals = int(cur.fetchone()["n"])
    check("baseline 42 attendance rows", before_att == 42 and before_demo == 42, {"n": before_att, "demo": before_demo})
    check("four reals present", before_four == 4, before_four)

    locked_dates: set[tuple[str, str, date]] = set()
    configured = {mgr_phone, mgr2_phone, hr_phone}
    scope_map = {
        mgr_phone: {emp_key},
        mgr2_phone: {emp_key},
        out_mgr: {f"W3-SYNTH|OTHER-{tag}"},
    }

    def scope_allows(c: str, actor: str, employee_key: str) -> bool:
        if c != company:
            return False
        allowed = scope_map.get(actor)
        return bool(allowed and employee_key in allowed)

    def payroll_locked(c: str, employee_key: str, d: date) -> bool:
        return (c, employee_key, d) in locked_dates

    def mgr_configured(c: str, actor: str) -> bool:
        return actor in configured

    auth_store = auth_pg.PostgresAuthorityStore()
    authority = core.AttendanceAuthorityService(store=auth_store)
    ops_store = ops_pg.PostgresOpsStore()
    # Ensure schema present
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            ops_pg.ensure_attendance_ops_postgres_schema(cur)
            auth_pg.ensure_attendance_authority_postgres_schema(cur)
        conn.commit()

    svc = ops.AttendanceOpsService(
        store=ops_store,
        authority_service=authority,
        scope_allows=scope_allows,
        payroll_locked=payroll_locked,
        manager_configured=mgr_configured,
    )

    def shift_day(d: date) -> dict[str, Any]:
        return {
            "shift_id": str(uuid.uuid4()),
            "shift_date": d,
            "start_time": time(9, 0),
            "end_time": time(17, 0),
            "employee_key": emp_key,
            "status": "scheduled",
        }

    def cleanup() -> None:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('wathefni.allow_authority_cleanup', '1', true)")
                like = f"W3-SYNTH|{tag}%"
                cur.execute(
                    "SELECT exception_id::text AS id FROM attendance_ops_exceptions WHERE company_code=%s AND (employee_key=%s OR employee_key LIKE %s)",
                    (company, emp_key, like),
                )
                exc_ids = [r["id"] for r in cur.fetchall()]
                cur.execute(
                    "SELECT case_id::text AS id FROM attendance_ops_cases WHERE company_code=%s AND (employee_key=%s OR employee_key LIKE %s)",
                    (company, emp_key, like),
                )
                case_ids = [r["id"] for r in cur.fetchall()]
                cur.execute(
                    "SELECT dispute_id::text AS id FROM attendance_ops_disputes WHERE company_code=%s AND (employee_key=%s OR employee_key LIKE %s)",
                    (company, emp_key, like),
                )
                disp_ids = [r["id"] for r in cur.fetchall()]
                entity_ids = exc_ids + case_ids + disp_ids
                if entity_ids:
                    cur.execute(
                        "DELETE FROM attendance_ops_comments WHERE company_code=%s AND entity_id::text = ANY(%s)",
                        (company, entity_ids),
                    )
                    cur.execute(
                        "DELETE FROM attendance_ops_attachments WHERE company_code=%s AND entity_id::text = ANY(%s)",
                        (company, entity_ids),
                    )
                cur.execute(
                    "DELETE FROM attendance_ops_idempotency WHERE company_code=%s AND idempotency_key LIKE %s",
                    (company, f"%{tag}%"),
                )
                for tbl in ("attendance_ops_disputes", "attendance_ops_cases", "attendance_ops_exceptions"):
                    cur.execute(
                        f"DELETE FROM {tbl} WHERE company_code=%s AND (employee_key=%s OR employee_key LIKE %s)",
                        (company, emp_key, like),
                    )
                for tbl in (
                    "attendance_compat_drift",
                    "attendance_authority_events",
                    "attendance_payroll_snapshots",
                    "attendance_corrections",
                    "attendance_day_projections",
                    "attendance_punches",
                ):
                    cur.execute(
                        f"DELETE FROM {tbl} WHERE company_code=%s AND (employee_key=%s OR employee_key LIKE %s OR employee_key LIKE %s)",
                        (company, emp_key, like, f"%{tag}%"),
                    )
                cur.execute(
                    """
                    DELETE FROM attendance_records
                    WHERE company_code=%s AND (employee_key=%s OR employee_key LIKE %s)
                      AND coalesce(metadata->>'demo_seed','') <> 'wathefni_v1'
                    """,
                    (company, emp_key, like),
                )
                cur.execute(
                    "DELETE FROM payroll_timesheets WHERE company_code=%s AND employee_key=%s",
                    (company, emp_key),
                )
            conn.commit()

    cleanup()  # pre-clean any leftover tag collision (unlikely)

    try:
        # --- every exception kind openable ---
        base_day = date(2026, 9, 1)
        for kind in sorted(ops.EXCEPTION_KINDS):
            opened = svc.open_exception(
                company_code=company,
                employee=emp,
                work_date=base_day,
                kind=kind,
                actor_phone=hr_phone,
                shift_key="kind-scan",
                source="canary",
                source_ref=f"canary:{tag}:{kind}",
                actor_role="hr",
            )
            check(f"open kind {kind}", opened.get("ok") is True, opened)

        # Real employee denied
        real_key = next(iter(core.FOUR_REAL_ATTENDANCE_KEYS))
        denied_real = svc.open_exception(
            company_code=company,
            employee={"employee_key": real_key, "phone": real_key.split("-")[-1]},
            work_date=base_day,
            kind="absence",
            actor_role="hr",
        )
        check("real employee ops denied", denied_real.get("error") == "ops_synthetic_only_denied", denied_real)

        # External tenant denied by company gate
        other_open = svc.open_exception(
            company_code=other,
            employee=emp_other,
            work_date=base_day,
            kind="absence",
            actor_role="hr",
        )
        check("external tenant ops denied", other_open.get("ok") is False, other_open)

        # --- missing check-in lifecycle: assign → request → review → apply ---
        d_miss = date(2026, 9, 2)
        sh = shift_day(d_miss)
        only_out = authority.ingest_punch(
            company_code=company, employee=emp, punched_at=dt(d_miss, "17:00"), direction="out",
            source="hr", source_event_id=f"w3c-only-out-{tag}", shift=sh, work_date=d_miss,
        )
        sync = svc.sync_exceptions_from_projection(company_code=company, employee=emp, projection=only_out["projection"])
        miss = next((e for e in sync["exceptions"] if e["kind"] == "missing_check_in"), None)
        check("missing_check_in synced", miss is not None, sync.get("kinds"))
        assert miss is not None
        assigned = svc.assign_exception(
            company_code=company, exception_id=miss["exception_id"], owner_phone=mgr_phone,
            actor_phone=hr_phone, expected_row_version=int(miss["row_version"]), actor_role="hr",
            priority="high",
        )
        check("exception assigned", assigned.get("ok") is True and assigned["exception"]["owner_phone"] == mgr_phone)

        req = svc.request_correction(
            company_code=company, employee=emp, work_date=d_miss,
            requested_by_phone=mgr_phone,
            changes={"check_in_at": dt(d_miss, "09:00").isoformat()},
            shift=sh, exception_id=assigned["exception"]["exception_id"],
            actor_is_manager=True, actor_role="manager", kind="missing_check_in",
        )
        check("correction requested", req.get("ok") is True)
        case = req["case"]
        before_ver = int((authority.store.get_current_projection(
            company_code=company, employee_key=emp_key, work_date=d_miss,
            shift_key=core.shift_key_of(sh["shift_id"]),
        ) or {}).get("version") or 0)

        rev = svc.review_case(
            company_code=company, case_id=case["case_id"], decision="approved",
            decided_by_phone=mgr_phone, expected_row_version=int(case["row_version"]),
            actor_role="manager", employee=emp,
        )
        check("approve without apply", rev.get("ok") is True and rev.get("applied") is False)
        mid = authority.store.get_current_projection(
            company_code=company, employee_key=emp_key, work_date=d_miss,
            shift_key=core.shift_key_of(sh["shift_id"]),
        )
        check("projection unchanged pre-apply", (mid or {}).get("check_in_at") is None)

        applied = svc.apply_case(
            company_code=company, case_id=case["case_id"], applied_by_phone=hr_phone,
            expected_row_version=int(rev["case"]["row_version"]),
            idempotency_key=f"apply-miss-{tag}", employee=emp, shift=sh, actor_role="hr",
        )
        check("apply creates new version", applied.get("ok") is True and int((applied.get("projection") or {}).get("version") or 0) > before_ver)
        check("before/after present", bool(applied.get("before")) and bool(applied.get("after")))

        replay = svc.apply_case(
            company_code=company, case_id=case["case_id"], applied_by_phone=hr_phone,
            expected_row_version=999, idempotency_key=f"apply-miss-{tag}",
            employee=emp, shift=sh, actor_role="hr",
        )
        check("idempotent apply replay", replay.get("idempotent_replay") is True or replay.get("already_applied") is True)

        # --- concurrent apply attempts ---
        d_conc = date(2026, 9, 3)
        shc = shift_day(d_conc)
        authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(d_conc, "09:00"), direction="in",
                               source="hr", source_event_id=f"w3c-conc-in-{tag}", shift=shc, work_date=d_conc)
        # missing out
        proj_c = authority.store.get_current_projection(
            company_code=company, employee_key=emp_key, work_date=d_conc,
            shift_key=core.shift_key_of(shc["shift_id"]),
        )
        sync_c = svc.sync_exceptions_from_projection(company_code=company, employee=emp, projection=proj_c or {})
        miss_out = next((e for e in sync_c["exceptions"] if e["kind"] == "missing_check_out"), None)
        req_c = svc.request_correction(
            company_code=company, employee=emp, work_date=d_conc, requested_by_phone=mgr_phone,
            changes={"check_out_at": dt(d_conc, "17:00").isoformat()},
            shift=shc, exception_id=(miss_out or {}).get("exception_id"),
            actor_is_manager=True, actor_role="manager",
        )
        rev_c = svc.review_case(
            company_code=company, case_id=req_c["case"]["case_id"], decision="approved",
            decided_by_phone=mgr_phone, expected_row_version=int(req_c["case"]["row_version"]),
            actor_role="manager", employee=emp,
        )
        case_c = rev_c["case"]
        results_conc: list[dict[str, Any]] = []
        barrier = threading.Barrier(2)

        def _apply_conc(key: str) -> None:
            barrier.wait(timeout=10)
            results_conc.append(
                svc.apply_case(
                    company_code=company, case_id=case_c["case_id"], applied_by_phone=hr_phone,
                    expected_row_version=int(case_c["row_version"]),
                    idempotency_key=key, employee=emp, shift=shc, actor_role="hr",
                )
            )

        t1 = threading.Thread(target=_apply_conc, args=(f"conc-a-{tag}",))
        t2 = threading.Thread(target=_apply_conc, args=(f"conc-b-{tag}",))
        t1.start(); t2.start(); t1.join(); t2.join()
        oks = [
            r for r in results_conc
            if r.get("ok") and r.get("applied") and not r.get("idempotent_replay") and not r.get("already_applied")
        ]
        check(
            "concurrent apply single winner",
            len(results_conc) == 2
            and len(oks) == 1
            and any(
                (not r.get("ok") and r.get("error") in {
                    "stale_row_version", "case_not_approved", "correction_not_open",
                })
                or r.get("already_applied")
                for r in results_conc
                if r not in oks
            ),
            results_conc,
        )

        # Same idempotency key concurrent — both succeed as replay/apply
        d_idem = date(2026, 9, 4)
        shi = shift_day(d_idem)
        authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(d_idem, "09:00"), direction="in",
                               source="hr", source_event_id=f"w3c-idem-in-{tag}", shift=shi, work_date=d_idem)
        proj_i = authority.store.get_current_projection(
            company_code=company, employee_key=emp_key, work_date=d_idem,
            shift_key=core.shift_key_of(shi["shift_id"]),
        )
        sync_i = svc.sync_exceptions_from_projection(company_code=company, employee=emp, projection=proj_i or {})
        miss_i = next((e for e in sync_i["exceptions"] if e["kind"] == "missing_check_out"), None)
        req_i = svc.request_correction(
            company_code=company, employee=emp, work_date=d_idem, requested_by_phone=mgr_phone,
            changes={"check_out_at": dt(d_idem, "17:00").isoformat()},
            shift=shi, exception_id=(miss_i or {}).get("exception_id"),
            actor_is_manager=True, actor_role="manager",
        )
        rev_i = svc.review_case(
            company_code=company, case_id=req_i["case"]["case_id"], decision="approved",
            decided_by_phone=mgr_phone, expected_row_version=int(req_i["case"]["row_version"]),
            actor_role="manager", employee=emp,
        )
        same_key_results: list[dict[str, Any]] = []
        barrier2 = threading.Barrier(2)

        def _apply_same() -> None:
            barrier2.wait(timeout=10)
            same_key_results.append(
                svc.apply_case(
                    company_code=company, case_id=rev_i["case"]["case_id"], applied_by_phone=hr_phone,
                    expected_row_version=int(rev_i["case"]["row_version"]),
                    idempotency_key=f"same-idem-{tag}", employee=emp, shift=shi, actor_role="hr",
                )
            )

        u1 = threading.Thread(target=_apply_same); u2 = threading.Thread(target=_apply_same)
        u1.start(); u2.start(); u1.join(); u2.join()
        check(
            "concurrent same idempotency both ok",
            len(same_key_results) == 2 and all(r.get("ok") for r in same_key_results),
            same_key_results,
        )

        # --- late + early leave + dual approval ---
        d_late = date(2026, 9, 5)
        shl = shift_day(d_late)
        authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(d_late, "10:30"), direction="in",
                               source="hr", source_event_id=f"w3c-late-in-{tag}", shift=shl, work_date=d_late)
        late_p = authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(d_late, "16:00"), direction="out",
                                        source="hr", source_event_id=f"w3c-early-out-{tag}", shift=shl, work_date=d_late)
        sync_l = svc.sync_exceptions_from_projection(company_code=company, employee=emp, projection=late_p["projection"])
        kinds_l = {e["kind"] for e in sync_l["exceptions"]}
        check("lateness exception", "lateness" in kinds_l, kinds_l)
        check("early_leave exception", "early_leave" in kinds_l, kinds_l)
        early = next(e for e in sync_l["exceptions"] if e["kind"] == "early_leave")
        req_e = svc.request_correction(
            company_code=company, employee=emp, work_date=d_late, requested_by_phone=mgr_phone,
            changes={"check_out_at": dt(d_late, "17:00").isoformat()},
            shift=shl, exception_id=early["exception_id"],
            actor_is_manager=True, actor_role="manager", kind="early_leave",
        )
        check("dual approval required", req_e["case"].get("dual_approval_required") is True)
        r1 = svc.review_case(
            company_code=company, case_id=req_e["case"]["case_id"], decision="approved",
            decided_by_phone=mgr_phone, expected_row_version=int(req_e["case"]["row_version"]),
            actor_role="manager", employee=emp,
        )
        check("dual first pending", r1.get("dual_pending") is True)
        same = svc.review_case(
            company_code=company, case_id=req_e["case"]["case_id"], decision="approved",
            decided_by_phone=mgr_phone, expected_row_version=int(r1["case"]["row_version"]),
            actor_role="manager", employee=emp,
        )
        check("dual same approver denied", same.get("error") == "dual_approval_requires_distinct_approver", same)
        r2 = svc.review_case(
            company_code=company, case_id=req_e["case"]["case_id"], decision="approved",
            decided_by_phone=mgr2_phone, expected_row_version=int(r1["case"]["row_version"]),
            actor_role="manager", employee=emp,
        )
        check("dual second completes", r2.get("ok") is True and r2["case"]["status"] == "approved")
        ap_e = svc.apply_case(
            company_code=company, case_id=req_e["case"]["case_id"], applied_by_phone=hr_phone,
            expected_row_version=int(r2["case"]["row_version"]),
            idempotency_key=f"apply-early-{tag}", employee=emp, shift=shl, actor_role="hr",
        )
        check("early leave applied", ap_e.get("ok") is True)

        # --- absence + dual ---
        d_abs = date(2026, 9, 6)
        sha = shift_day(d_abs)
        abs_p = authority.reproject_day(
            company_code=company, employee=emp, work_date=d_abs, shift=sha,
            forced_status="absent", created_by_phone=hr_phone,
        )
        sync_a = svc.sync_exceptions_from_projection(company_code=company, employee=emp, projection=abs_p["projection"])
        abs_exc = next(e for e in sync_a["exceptions"] if e["kind"] == "absence")
        req_a = svc.request_correction(
            company_code=company, employee=emp, work_date=d_abs, requested_by_phone=mgr_phone,
            changes={"check_in_at": dt(d_abs, "09:00").isoformat(), "check_out_at": dt(d_abs, "17:00").isoformat(), "status": "completed"},
            shift=sha, exception_id=abs_exc["exception_id"],
            actor_is_manager=True, actor_role="manager", kind="absence",
        )
        ra1 = svc.review_case(company_code=company, case_id=req_a["case"]["case_id"], decision="approved",
                              decided_by_phone=mgr_phone, expected_row_version=int(req_a["case"]["row_version"]),
                              actor_role="manager", employee=emp)
        ra2 = svc.review_case(company_code=company, case_id=req_a["case"]["case_id"], decision="approved",
                              decided_by_phone=mgr2_phone, expected_row_version=int(ra1["case"]["row_version"]),
                              actor_role="manager", employee=emp)
        ap_a = svc.apply_case(company_code=company, case_id=req_a["case"]["case_id"], applied_by_phone=hr_phone,
                              expected_row_version=int(ra2["case"]["row_version"]),
                              idempotency_key=f"apply-abs-{tag}", employee=emp, shift=sha, actor_role="hr")
        check("absence correction applied", ap_a.get("ok") is True)

        # --- reject path ---
        d_rej = date(2026, 9, 7)
        shr = shift_day(d_rej)
        authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(d_rej, "09:00"), direction="in",
                               source="hr", source_event_id=f"w3c-rej-in-{tag}", shift=shr, work_date=d_rej)
        proj_r = authority.store.get_current_projection(
            company_code=company, employee_key=emp_key, work_date=d_rej,
            shift_key=core.shift_key_of(shr["shift_id"]),
        )
        sync_r = svc.sync_exceptions_from_projection(company_code=company, employee=emp, projection=proj_r or {})
        miss_r = next((e for e in sync_r["exceptions"] if e["kind"] == "missing_check_out"), None)
        req_r = svc.request_correction(
            company_code=company, employee=emp, work_date=d_rej, requested_by_phone=mgr_phone,
            changes={"check_out_at": dt(d_rej, "17:00").isoformat()},
            shift=shr, exception_id=(miss_r or {}).get("exception_id"),
            actor_is_manager=True, actor_role="manager",
        )
        rejected = svc.review_case(
            company_code=company, case_id=req_r["case"]["case_id"], decision="rejected",
            decided_by_phone=mgr_phone, expected_row_version=int(req_r["case"]["row_version"]),
            decision_note="insufficient evidence", actor_role="manager", employee=emp,
        )
        check("reject without apply", rejected.get("ok") is True and rejected.get("applied") is False)

        # --- dispute + reopen ---
        d_disp = date(2026, 9, 8)
        shd = shift_day(d_disp)
        authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(d_disp, "09:20"), direction="in",
                               source="hr", source_event_id=f"w3c-disp-in-{tag}", shift=shd, work_date=d_disp)
        authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(d_disp, "17:00"), direction="out",
                               source="hr", source_event_id=f"w3c-disp-out-{tag}", shift=shd, work_date=d_disp)
        proj_d = authority.store.get_current_projection(
            company_code=company, employee_key=emp_key, work_date=d_disp,
            shift_key=core.shift_key_of(shd["shift_id"]),
        )
        sync_d = svc.sync_exceptions_from_projection(company_code=company, employee=emp, projection=proj_d or {})
        late_exc = next((e for e in sync_d["exceptions"] if e["kind"] == "lateness"), None)
        if not late_exc:
            late_exc = svc.open_exception(
                company_code=company, employee=emp, work_date=d_disp, kind="lateness",
                shift_key=core.shift_key_of(shd["shift_id"]), projection=proj_d, actor_role="hr",
            )["exception"]
        req_d = svc.request_correction(
            company_code=company, employee=emp, work_date=d_disp, requested_by_phone=mgr_phone,
            changes={"check_in_at": dt(d_disp, "09:00").isoformat()},
            shift=shd, exception_id=late_exc["exception_id"],
            actor_is_manager=True, actor_role="manager", kind="lateness",
        )
        rd = svc.review_case(company_code=company, case_id=req_d["case"]["case_id"], decision="approved",
                             decided_by_phone=mgr_phone, expected_row_version=int(req_d["case"]["row_version"]),
                             actor_role="manager", employee=emp)
        ap_d = svc.apply_case(company_code=company, case_id=req_d["case"]["case_id"], applied_by_phone=hr_phone,
                              expected_row_version=int(rd["case"]["row_version"]),
                              idempotency_key=f"apply-disp-{tag}", employee=emp, shift=shd, actor_role="hr")
        check("dispute base applied", ap_d.get("ok") is True)
        dispute = svc.raise_dispute(
            company_code=company, employee=emp, work_date=d_disp, raised_by_phone=emp_phone,
            reason="badge misread", exception_id=late_exc["exception_id"], case_id=req_d["case"]["case_id"],
            shift_key=core.shift_key_of(shd["shift_id"]),
        )
        check("employee dispute raised", dispute.get("ok") is True)
        resolved = svc.resolve_dispute(
            company_code=company, dispute_id=dispute["dispute"]["dispute_id"],
            resolution="overturned", resolved_by_phone=mgr_phone,
            expected_row_version=int(dispute["dispute"]["row_version"]),
            resolution_note="accept employee evidence", actor_role="manager", employee=emp,
        )
        check("dispute resolved", resolved.get("ok") is True)
        exc_now = ops_store.get_exception(late_exc["exception_id"], company)
        if exc_now and exc_now["status"] not in {"resolved", "rejected", "closed"}:
            ops_store.update_exception(late_exc["exception_id"], company, expected_row_version=int(exc_now["row_version"]), status="resolved")
            exc_now = ops_store.get_exception(late_exc["exception_id"], company)
        reopen = svc.reopen_exception(
            company_code=company, exception_id=late_exc["exception_id"],
            actor_phone=hr_phone, expected_row_version=int((exc_now or {}).get("row_version") or 1),
            evidence_note="new badge export", actor_role="hr",
        )
        check("reopen after evidence", reopen.get("ok") is True and reopen["exception"]["status"] == "reopened", reopen)

        stale = svc.assign_exception(
            company_code=company, exception_id=late_exc["exception_id"], owner_phone=mgr_phone,
            actor_phone=hr_phone, expected_row_version=1, actor_role="hr",
        )
        check("stale row_version fail-closed", stale.get("error") == "stale_row_version", stale)

        # --- permission boundaries ---
        out_scope = svc.request_correction(
            company_code=company, employee=emp, work_date=d_disp, requested_by_phone=out_mgr,
            changes={"status": "absent"}, shift=shd, actor_is_manager=True, actor_role="manager",
        )
        check("out-of-scope manager denied", out_scope.get("error") == "employee_outside_manager_scope", out_scope)
        unconf = svc.request_correction(
            company_code=company, employee=emp, work_date=d_disp, requested_by_phone="96552400099",
            changes={"status": "absent"}, shift=shd, actor_is_manager=True, actor_role="manager",
        )
        check("unconfigured manager denied", unconf.get("error") == "manager_unconfigured", unconf)
        self_deny = svc.request_correction(
            company_code=company,
            employee={**emp, "phone": mgr_phone},
            work_date=d_disp, requested_by_phone=mgr_phone,
            changes={"status": "absent"}, shift=shd, actor_is_manager=True, actor_role="manager",
        )
        check("manager self-correction denied", self_deny.get("error") == "manager_self_correction_denied", self_deny)

        # --- payroll lock ---
        d_lock = date(2026, 9, 9)
        shl2 = shift_day(d_lock)
        locked_dates.add((company, emp_key, d_lock))
        lock_deny = svc.request_correction(
            company_code=company, employee=emp, work_date=d_lock, requested_by_phone=mgr_phone,
            changes={"check_in_at": dt(d_lock, "09:00").isoformat()},
            shift=shl2, actor_is_manager=True, actor_role="manager",
        )
        check("payroll lock denies correction", lock_deny.get("error") == "payroll_period_locked", lock_deny)

        # --- leave reversal preserves correction ---
        d_leave = date(2026, 9, 10)
        shlv = shift_day(d_leave)
        authority.apply_leave(company_code=company, employee=emp, work_date=d_leave, leave_id=f"leave-{tag}", shift=shlv)
        req_lv = svc.request_correction(
            company_code=company, employee=emp, work_date=d_leave, requested_by_phone=mgr_phone,
            changes={"check_in_at": dt(d_leave, "09:00").isoformat(), "check_out_at": dt(d_leave, "17:00").isoformat(), "status": "completed"},
            shift=shlv, actor_is_manager=True, actor_role="manager", kind="absence",
        )
        rl1 = svc.review_case(company_code=company, case_id=req_lv["case"]["case_id"], decision="approved",
                              decided_by_phone=mgr_phone, expected_row_version=int(req_lv["case"]["row_version"]),
                              actor_role="manager", employee=emp)
        rl2 = svc.review_case(company_code=company, case_id=req_lv["case"]["case_id"], decision="approved",
                              decided_by_phone=mgr2_phone, expected_row_version=int(rl1["case"]["row_version"]),
                              actor_role="manager", employee=emp)
        ap_lv = svc.apply_case(company_code=company, case_id=req_lv["case"]["case_id"], applied_by_phone=hr_phone,
                               expected_row_version=int(rl2["case"]["row_version"]),
                               idempotency_key=f"apply-leave-{tag}", employee=emp, shift=shlv, actor_role="hr")
        check("post-leave correction applied", ap_lv.get("ok") is True)
        rev_leave = authority.reverse_leave(
            company_code=company, employee=emp, work_date=d_leave, leave_id=f"leave-{tag}", shift=shlv,
        )
        check("leave reverse preserves correction", rev_leave.get("reason") == "manual_correction_preserved", rev_leave)

        # --- approved attendance → payroll snapshot (synthetic only) ---
        d_pay = date(2026, 9, 11)
        shp = shift_day(d_pay)
        authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(d_pay, "09:00"), direction="in",
                               source="hr", source_event_id=f"w3c-pay-in-{tag}", shift=shp, work_date=d_pay)
        authority.ingest_punch(company_code=company, employee=emp, punched_at=dt(d_pay, "17:00"), direction="out",
                               source="hr", source_event_id=f"w3c-pay-out-{tag}", shift=shp, work_date=d_pay)
        approved = authority.approve_day(
            company_code=company, employee=emp, work_date=d_pay, approved_by_phone=hr_phone, shift=shp,
        )
        check("synthetic day approved", approved.get("ok") is True, approved)
        snap = approved.get("snapshot") or {}
        proj = approved.get("projection") or {}
        check(
            "snapshot reconciles projection",
            snap.get("projection_id") == proj.get("projection_id")
            and int(snap.get("projection_version") or 0) == int(proj.get("version") or -1),
            {"snap": snap.get("projection_version"), "proj": proj.get("version")},
        )

        # Raw punches immutable
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS n FROM attendance_punches WHERE company_code=%s AND source='hr' AND source_event_id=%s",
                    (company, f"w3c-pay-in-{tag}"),
                )
                check("raw punch immutable retained", int(cur.fetchone()["n"]) == 1)
                cur.execute(
                    "SELECT COUNT(*) AS n FROM attendance_punches WHERE company_code=%s AND source='correction' AND employee_key=%s",
                    (company, emp_key),
                )
                check("correction punches separate source", int(cur.fetchone()["n"]) >= 1)

        # Comments / attachments / audit
        cmt = svc.add_comment(company_code=company, entity_type="exception", entity_id=str(late_exc["exception_id"]),
                              author_phone=hr_phone, body="canary comment")
        check("comment added", cmt.get("ok") is True)
        att = svc.add_attachment(company_code=company, entity_type="exception", entity_id=str(late_exc["exception_id"]),
                                 uploaded_by_phone=hr_phone, filename="evidence.pdf",
                                 storage_ref=f"ops://canary/{tag}/evidence.pdf")
        check("attachment ref stored", att.get("ok") is True)
        audit = ops_store.list_audit(company_code=company, entity_type="exception", entity_id=str(late_exc["exception_id"]))
        check("append-only audit events present", len(audit) >= 1, len(audit))
        # Prove audit immutability
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        "UPDATE attendance_ops_audit_events SET event_type='tamper' WHERE company_code=%s AND entity_id=%s",
                        (company, str(late_exc["exception_id"])),
                    )
                    conn.commit()
                    check("audit update blocked", False, "update succeeded")
                except Exception as exc:  # noqa: BLE001
                    conn.rollback()
                    check("audit update blocked", "append-only" in str(exc).lower() or "attendance_ops_audit" in str(exc), str(exc)[:200])

        # --- isolation: synthetic must not enter real workflows ---
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
                after_att = int(cur.fetchone()["n"])
                cur.execute(
                    """
                    SELECT md5(string_agg(attendance_id::text || ':' || status || ':' || coalesce(metadata->>'demo_seed',''), '|'
                               ORDER BY attendance_id::text)) AS fp
                    FROM attendance_records WHERE company_code='WATHEFNI'
                    """
                )
                after_att_fp = cur.fetchone()["fp"]
                cur.execute(
                    "SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI' AND employee_key=%s",
                    (emp_key,),
                )
                synth_in_records = int(cur.fetchone()["n"])
                cur.execute(
                    """
                    SELECT md5(string_agg(timesheet_id::text || ':' || status || ':' || employee_key, '|'
                               ORDER BY timesheet_id::text)) AS fp,
                           COUNT(*) AS n
                    FROM payroll_timesheets
                    WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)
                    """,
                    (list(core.FOUR_REAL_ATTENDANCE_KEYS),),
                )
                row = cur.fetchone()
                after_ts_fp, after_ts_n = row["fp"], int(row["n"])
                cur.execute(
                    "SELECT COUNT(*) AS n FROM payroll_timesheets WHERE company_code='WATHEFNI' AND employee_key=%s",
                    (emp_key,),
                )
                synth_ts = int(cur.fetchone()["n"])
                cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM attendance_payroll_snapshots
                    WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)
                    """,
                    (list(core.FOUR_REAL_ATTENDANCE_KEYS),),
                )
                after_snap_reals = int(cur.fetchone()["n"])
                cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM attendance_day_projections
                    WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)
                    """,
                    (list(core.FOUR_REAL_ATTENDANCE_KEYS),),
                )
                after_proj_reals = int(cur.fetchone()["n"])
                cur.execute("SELECT COUNT(*) AS n FROM employees WHERE company_code='WATHEFNI' AND employee_key=%s", (emp_key,))
                synth_emp_row = int(cur.fetchone()["n"])
                # leave balances table if present
                cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM information_schema.tables
                    WHERE table_schema='public' AND table_name='employee_leave_balances'
                    """
                )
                has_bal = int(cur.fetchone()["n"]) > 0
                synth_bal = 0
                if has_bal:
                    cur.execute(
                        "SELECT COUNT(*) AS n FROM employee_leave_balances WHERE company_code='WATHEFNI' AND employee_key=%s",
                        (emp_key,),
                    )
                    synth_bal = int(cur.fetchone()["n"])

        check("42 attendance rows unchanged", after_att == before_att == 42, after_att)
        check("attendance fingerprint unchanged", after_att_fp == before_att_fp)
        check("synthetic absent from attendance_records", synth_in_records == 0, synth_in_records)
        check("real payroll timesheets unchanged", after_ts_fp == before_ts_fp and after_ts_n == before_ts_n)
        check("synthetic absent from payroll_timesheets", synth_ts == 0, synth_ts)
        check("real authority snapshots unchanged", after_snap_reals == before_snap_reals)
        check("real day projections unchanged", after_proj_reals == before_proj_reals)
        check("synthetic not in employees table", synth_emp_row == 0, synth_emp_row)
        check("synthetic not in leave balances", synth_bal == 0, synth_bal)

        # Compat list for real employee must not include synth key
        real_key = next(iter(core.FOUR_REAL_ATTENDANCE_KEYS))
        compat_rows = authority.list_compat_attendance(
            company_code=company,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
            employee_key=real_key,
        )
        leaked = [r for r in (compat_rows or []) if str(r.get("employee_key") or "") == emp_key]
        check("real employee report excludes synthetic", len(leaked) == 0, len(leaked))

        summary = authority.list_payroll_hours_from_snapshots(
            company_code=company,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
            employee_keys=set(core.FOUR_REAL_ATTENDANCE_KEYS),
        )
        summaries = summary.get("summaries") or []
        check(
            "payroll summary four-reals excludes synthetic",
            all(s.get("employee_key") in core.FOUR_REAL_ATTENDANCE_KEYS for s in summaries),
            [s.get("employee_key") for s in summaries],
        )

        # No capture devices/connectors created by this canary
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM attendance_capture_devices
                    WHERE company_code=%s AND terminal_sn LIKE %s
                    """,
                    (company, f"%{tag}%"),
                )
                check("no canary devices registered", int(cur.fetchone()["n"]) == 0)

    finally:
        cleanup()

    # Post-cleanup invariants
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
            final_att = int(cur.fetchone()["n"])
            cur.execute(
                "SELECT COUNT(*) AS n FROM attendance_ops_exceptions WHERE employee_key=%s OR employee_key LIKE %s",
                (emp_key, f"W3-SYNTH|{tag}%"),
            )
            leftover_exc = int(cur.fetchone()["n"])
            cur.execute(
                "SELECT COUNT(*) AS n FROM attendance_punches WHERE employee_key=%s OR employee_key LIKE %s",
                (emp_key, f"W3-SYNTH|{tag}%"),
            )
            leftover_punches = int(cur.fetchone()["n"])
            cur.execute(
                "SELECT COUNT(*) AS n FROM attendance_day_projections WHERE employee_key=%s OR employee_key LIKE %s",
                (emp_key, f"W3-SYNTH|{tag}%"),
            )
            leftover_proj = int(cur.fetchone()["n"])
    check("post-cleanup 42 rows", final_att == 42, final_att)
    check("post-cleanup exceptions gone", leftover_exc == 0, leftover_exc)
    check("post-cleanup punches gone", leftover_punches == 0, leftover_punches)
    check("post-cleanup projections gone", leftover_proj == 0, leftover_proj)

    out = {
        "wave": "attendance-wave3-prod-synthetic",
        "passed": PASS,
        "failed": FAIL,
        "total": PASS + FAIL,
        "tag": tag,
        "employee_key": emp_key,
        "company": company,
        "results": RESULTS,
        "flags": {
            "WATHEFNI_ATTENDANCE_OPS": os.environ.get("WATHEFNI_ATTENDANCE_OPS"),
            "WATHEFNI_ATTENDANCE_OPS_COMPANIES": os.environ.get("WATHEFNI_ATTENDANCE_OPS_COMPANIES"),
            "WATHEFNI_ATTENDANCE_OPS_STORE": os.environ.get("WATHEFNI_ATTENDANCE_OPS_STORE"),
            "WATHEFNI_ATTENDANCE_OPS_SYNTHETIC_ONLY": os.environ.get("WATHEFNI_ATTENDANCE_OPS_SYNTHETIC_ONLY"),
            "WATHEFNI_ATTENDANCE_CAPTURE_INGEST": os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST"),
            "WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY": os.environ.get("WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY"),
            "WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES": os.environ.get("WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES"),
        },
    }
    results_path = os.environ.get("ATTW3_RESULTS") or os.environ.get("ATTW3_RESULTS_PATH")
    if results_path:
        Path(results_path).parent.mkdir(parents=True, exist_ok=True)
        Path(results_path).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWave 3 prod synthetic canary: {PASS}/{PASS+FAIL} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
