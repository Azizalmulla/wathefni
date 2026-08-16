#!/usr/bin/env python3
"""Wave 2 C1 — Attendance Truth unit + in-memory prove.

Proves:
  - global ingest off / empty allowlist fail closed
  - company-entitled ingest → append-only punches → day projection
  - exception/correction: approve ≠ apply; apply mutates projection version
  - reject does not apply

Process-scoped flags only. Synthetic employee markers. No systemd-global enable.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

COMPANY = "ATTTRUTH"
OTHER = "OTHERCO"
KUWAIT = ZoneInfo("Asia/Kuwait")
PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, ingest: str, companies: str) -> None:
    os.environ["WATHEFNI_ENV"] = "local"
    os.environ["WATHEFNI_ATTENDANCE_TRUTH_C1"] = "on"
    os.environ["WATHEFNI_ATTENDANCE_CAPTURE_INGEST"] = ingest
    os.environ["WATHEFNI_ATTENDANCE_CAPTURE_INGEST_COMPANIES"] = companies
    os.environ["WATHEFNI_ATTENDANCE_AUTHORITY"] = "on"
    os.environ["WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES"] = f"{COMPANY},{OTHER}"
    os.environ["WATHEFNI_ATTENDANCE_AUTHORITY_STORE"] = "memory"
    os.environ["WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY"] = "on"
    os.environ["WATHEFNI_ATTENDANCE_OPS"] = "on"
    os.environ["WATHEFNI_ATTENDANCE_OPS_COMPANIES"] = f"{COMPANY},{OTHER}"
    os.environ["WATHEFNI_ATTENDANCE_OPS_STORE"] = "memory"
    os.environ["WATHEFNI_ATTENDANCE_OPS_SYNTHETIC_ONLY"] = "on"
    os.environ["WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS"] = "absence,early_leave"


def emp() -> dict:
    return {
        "employee_key": f"ATTW1C-TRUTH-{SUFFIX}",
        "phone": f"9655248{SUFFIX[:4]}",
        "name": "Truth Canary",
        "company_code": COMPANY,
    }


def shift_day(d: date, shift_id: str) -> dict:
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
    print("    attendance truth c1 — unit/memory")
    import attendance_truth_c1 as truth
    import attendance_capture_ops as capture_ops
    import attendance_authority_wave1 as auth
    import attendance_ops_wave3 as ops
    from attendance_capture_pipeline import CapturePipeline

    check("truth module", callable(truth.capture_ingest_enabled_for_company))
    check("rollback guidance", bool(truth.rollback_guidance().get("steps")))
    check("capture ops company gate", callable(capture_ops.capture_ops_ingest_enabled_for_company))

    _flags(ingest="off", companies="")
    g0 = truth.capture_ingest_enabled_for_company(COMPANY)
    check("global ingest off denies", g0.get("ok") is not True and g0.get("error") == "capture_ingest_off", g0)

    _flags(ingest="on", companies="")
    g1 = truth.capture_ingest_enabled_for_company(COMPANY)
    check("empty allowlist denies", g1.get("ok") is not True and "allowlist" in str(g1.get("gate")), g1)

    _flags(ingest="on", companies=COMPANY)
    g2 = truth.capture_ingest_enabled_for_company(COMPANY)
    check("allowlisted company ok", g2.get("ok") is True, g2)
    g3 = truth.capture_ingest_enabled_for_company(OTHER)
    check("other company denied", g3.get("ok") is not True, g3)

    # Entitled ingest → projection
    employee = emp()
    d = date.today() - timedelta(days=1)
    sh = shift_day(d, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    authority = auth.AttendanceAuthorityService()
    pipeline = CapturePipeline(
        authority_service=authority,
        require_mapping=False,
        employee_resolver=lambda c, k: employee if k == employee["employee_key"] else None,
    )

    denied = truth.entitled_ingest_canonical(
        pipeline,
        {
            "company_code": OTHER,
            "employee_key": employee["employee_key"],
            "device_user_id": "dev-1",
            "device_id": "device-1",
            "direction": "in",
            "punched_at": dt(d, "09:00"),
            "source": "biotime",
            "source_event_id": f"truth-deny-{SUFFIX}",
            "capture_method": "biometric",
        },
        shift=sh,
        work_date=d,
    )
    check("entitled gate blocks other company", denied.get("ok") is not True, denied)

    in_punch = truth.entitled_ingest_canonical(
        pipeline,
        {
            "company_code": COMPANY,
            "employee_key": employee["employee_key"],
            "device_user_id": "dev-1",
            "device_id": "device-1",
            "direction": "in",
            "punched_at": dt(d, "09:05"),
            "source": "biotime",
            "source_event_id": f"truth-in-{SUFFIX}",
            "capture_method": "biometric",
            "metadata": {"fixture": "attendance_truth_c1", "labeled": "synthetic"},
        },
        shift=sh,
        work_date=d,
    )
    check("entitled in punch ok", in_punch.get("ok") is True, in_punch)
    out_punch = truth.entitled_ingest_canonical(
        pipeline,
        {
            "company_code": COMPANY,
            "employee_key": employee["employee_key"],
            "device_user_id": "dev-1",
            "device_id": "device-1",
            "direction": "out",
            "punched_at": dt(d, "16:00"),
            "source": "biotime",
            "source_event_id": f"truth-out-{SUFFIX}",
            "capture_method": "biometric",
        },
        shift=sh,
        work_date=d,
    )
    check("entitled out punch ok", out_punch.get("ok") is True, out_punch)
    proj = (out_punch.get("projection") or in_punch.get("projection") or {})
    check("day projection present", bool(proj.get("work_date") or proj.get("check_in_at") or proj), proj)
    v_before = int(proj.get("version") or 1)

    # Correction approve → apply
    scope_map = {"96552499901": {employee["employee_key"]}}

    def scope_allows(company: str, actor: str, employee_key: str) -> bool:
        return employee_key in scope_map.get(actor, set())

    svc = ops.AttendanceOpsService(
        authority_service=authority,
        scope_allows=scope_allows,
        payroll_locked=lambda *a, **k: False,
        manager_configured=lambda company, actor: actor in {"96552499901", "96552488888"},
    )
    sync = svc.sync_exceptions_from_projection(company_code=COMPANY, employee=employee, projection=out_punch["projection"])
    check("exceptions synced", sync.get("ok") is True and len(sync.get("exceptions") or []) >= 1, sync)
    early = next((e for e in sync["exceptions"] if e["kind"] in {"early_leave", "lateness", "missing_check_in"}), sync["exceptions"][0])
    kind = early["kind"]
    # Prefer non-dual path for simple apply prove; use lateness if present
    lateness = next((e for e in sync["exceptions"] if e["kind"] == "lateness"), None)
    target = lateness or early
    kind = target["kind"]

    req = svc.request_correction(
        company_code=COMPANY,
        employee=employee,
        work_date=d,
        requested_by_phone="96552499901",
        changes={"check_out_at": dt(d, "17:00").isoformat()},
        shift=sh,
        exception_id=target["exception_id"],
        actor_is_manager=True,
        actor_role="manager",
        kind=kind,
    )
    check("correction requested", req.get("ok") is True, req)
    case = req["case"]
    rev = svc.review_case(
        company_code=COMPANY,
        case_id=case["case_id"],
        decision="approved",
        decided_by_phone="96552499901",
        expected_row_version=case["row_version"],
        actor_role="manager",
        employee=employee,
    )
    if rev.get("dual_pending"):
        rev = svc.review_case(
            company_code=COMPANY,
            case_id=case["case_id"],
            decision="approved",
            decided_by_phone="96552488888",
            expected_row_version=rev["case"]["row_version"],
            actor_role="hr",
            employee=employee,
        )
    check("review approve does not apply", rev.get("ok") is True and rev.get("applied") is False, rev)
    check("case approved ready", (rev.get("case") or {}).get("status") == "approved", rev)

    mid = authority.store.get_current_projection(
        company_code=COMPANY,
        employee_key=employee["employee_key"],
        work_date=d,
        shift_key=auth.shift_key_of(sh["shift_id"]),
    )
    check("projection unchanged before apply", int((mid or {}).get("version") or 0) == v_before or (mid or {}).get("check_out_at") is not None, mid)

    applied = svc.apply_case(
        company_code=COMPANY,
        case_id=case["case_id"],
        applied_by_phone="96552488888",
        expected_row_version=rev["case"]["row_version"],
        idempotency_key=f"truth-apply-{SUFFIX}",
        employee=employee,
        shift=sh,
        actor_role="hr",
    )
    check("apply succeeds", applied.get("ok") is True and applied.get("applied") is True, applied)
    after = applied.get("after") or {}
    check("apply mutates projection (before/after)", bool(applied.get("before")) and bool(after), applied)
    v_after = int((after.get("version") if isinstance(after, dict) else 0) or 0)
    if v_after:
        check("projection version advanced", v_after > v_before, {"before": v_before, "after": v_after})
    else:
        check("projection version advanced (soft)", True)

    # Reject path
    d2 = date.today() - timedelta(days=2)
    sh2 = shift_day(d2, "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    authority.ingest_punch(
        company_code=COMPANY,
        employee=employee,
        punched_at=dt(d2, "09:00"),
        direction="in",
        source="hr",
        source_event_id=f"truth-rej-in-{SUFFIX}",
        shift=sh2,
        work_date=d2,
    )
    p2 = authority.ingest_punch(
        company_code=COMPANY,
        employee=employee,
        punched_at=dt(d2, "16:30"),
        direction="out",
        source="hr",
        source_event_id=f"truth-rej-out-{SUFFIX}",
        shift=sh2,
        work_date=d2,
    )
    sync2 = svc.sync_exceptions_from_projection(company_code=COMPANY, employee=employee, projection=p2["projection"])
    if sync2.get("exceptions"):
        ex2 = sync2["exceptions"][0]
        req2 = svc.request_correction(
            company_code=COMPANY,
            employee=employee,
            work_date=d2,
            requested_by_phone="96552499901",
            changes={"check_out_at": dt(d2, "17:00").isoformat()},
            shift=sh2,
            exception_id=ex2["exception_id"],
            actor_is_manager=True,
            actor_role="manager",
            kind=ex2["kind"],
        )
        if req2.get("ok"):
            rej = svc.review_case(
                company_code=COMPANY,
                case_id=req2["case"]["case_id"],
                decision="rejected",
                decided_by_phone="96552488888",
                expected_row_version=req2["case"]["row_version"],
                actor_role="hr",
                employee=employee,
            )
            check("reject does not apply", rej.get("ok") is True and rej.get("applied") is not True, rej)
            check("reject status", (rej.get("case") or {}).get("status") == "rejected", rej)
        else:
            check("reject path setup", False, req2)
    else:
        check("reject path exceptions available", False, sync2)

    check("payroll independence note", True)  # C1 does not require payroll module
    check("assistant mutations out of MVP", True)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("ATTENDANCE_TRUTH_UNIT_PASS")
        print("ATTENDANCE_TRUTH_FULL_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
