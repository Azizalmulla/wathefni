#!/usr/bin/env python3
"""Seed a removable Wave 1 visual canary on company WATHEFNI (process-scoped flags).

Creates tagged fixtures for owner visual review:
  - 1 pending_approval requisition
  - 1 open requisition
  - 1 preboarding assignment (joining soon)
  - 1 active probation case with 30/60/90

Cleanup: --cleanup removes rows tagged metadata.wave1_visual_canary=true
No systemd-global enable. Does not mutate unrelated tenant data beyond WATHEFNI canary rows.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

TAG = "wave1_visual_canary"
COMPANY = os.environ.get("WATHEFNI_COMPANY_CODE") or ""


def _connect():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("WATHEFNI_DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or ""
    ).strip()
    if not url:
        import app

        return app.db_connect(), RealDictCursor
    return psycopg2.connect(url), RealDictCursor


def _enable_process_flags() -> None:
    for k, v in {
        "WATHEFNI_REQUISITIONS": "on",
        "WATHEFNI_REQUISITIONS_COMPANIES": COMPANY,
        "WATHEFNI_PREBOARDING": "on",
        "WATHEFNI_PREBOARDING_COMPANIES": COMPANY,
        "WATHEFNI_PROBATION": "on",
        "WATHEFNI_PROBATION_COMPANIES": COMPANY,
        "WATHEFNI_HIRE_READY_WAVE1": "on",
        "WATHEFNI_HIRE_READY_COMPANIES": COMPANY,
        "WATHEFNI_WORKFLOW_TASKS": "on",
        "WATHEFNI_WORKFLOW_TASKS_COMPANIES": COMPANY,
    }.items():
        os.environ[k] = v


def _safe_exec(cur, sql: str, args: tuple) -> int:
    try:
        cur.execute("SAVEPOINT wave1_seed_cleanup")
        cur.execute(sql, args)
        n = cur.rowcount or 0
        cur.execute("RELEASE SAVEPOINT wave1_seed_cleanup")
        return n
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT wave1_seed_cleanup")
        except Exception:
            pass
        return 0


def cleanup(cur) -> int:
    n = 0
    # Tasks first (may reference canary subjects)
    for sql, args in (
        (
            """
            DELETE FROM hr_tasks
             WHERE company_code=%s
               AND (
                 metadata->>'fixture'=%s
                 OR subject_id IN (
                   SELECT requisition_id::text FROM requisitions
                    WHERE company_code=%s AND metadata->>'fixture'=%s
                 )
                 OR subject_id IN (
                   SELECT case_id::text FROM probation_cases
                    WHERE company_code=%s AND metadata->>'fixture'=%s
                 )
                 OR subject_id IN (
                   SELECT assignment_id::text FROM preboard_assignments
                    WHERE company_code=%s AND metadata->>'fixture'=%s
                 )
               )
            """,
            (COMPANY, TAG, COMPANY, TAG, COMPANY, TAG, COMPANY, TAG),
        ),
        (
            "DELETE FROM probation_milestones WHERE company_code=%s AND case_id IN (SELECT case_id FROM probation_cases WHERE company_code=%s AND metadata->>'fixture'=%s)",
            (COMPANY, COMPANY, TAG),
        ),
        (
            "DELETE FROM probation_events WHERE company_code=%s AND case_id IN (SELECT case_id FROM probation_cases WHERE company_code=%s AND metadata->>'fixture'=%s)",
            (COMPANY, COMPANY, TAG),
        ),
        ("DELETE FROM probation_cases WHERE company_code=%s AND metadata->>'fixture'=%s", (COMPANY, TAG)),
        (
            "DELETE FROM preboard_items WHERE company_code=%s AND assignment_id IN (SELECT assignment_id FROM preboard_assignments WHERE company_code=%s AND metadata->>'fixture'=%s)",
            (COMPANY, COMPANY, TAG),
        ),
        (
            "DELETE FROM preboard_events WHERE company_code=%s AND assignment_id IN (SELECT assignment_id FROM preboard_assignments WHERE company_code=%s AND metadata->>'fixture'=%s)",
            (COMPANY, COMPANY, TAG),
        ),
        ("DELETE FROM preboard_assignments WHERE company_code=%s AND metadata->>'fixture'=%s", (COMPANY, TAG)),
        (
            "DELETE FROM requisition_events WHERE company_code=%s AND requisition_id IN (SELECT requisition_id FROM requisitions WHERE company_code=%s AND metadata->>'fixture'=%s)",
            (COMPANY, COMPANY, TAG),
        ),
        ("DELETE FROM requisitions WHERE company_code=%s AND metadata->>'fixture'=%s", (COMPANY, TAG)),
    ):
        n += _safe_exec(cur, sql, args)
    n += _safe_exec(
        cur,
        "DELETE FROM employees WHERE company_code=%s AND metadata->>'fixture'=%s",
        (COMPANY, TAG),
    )
    n += _safe_exec(
        cur,
        "DELETE FROM employees WHERE company_code=%s AND (employee_key LIKE %s OR employee_key LIKE %s)",
        (COMPANY, f"{COMPANY}-VIS-%", f"{COMPANY}-VIS-PRB-%"),
    )
    return n


def seed(cur) -> dict:
    import preboarding as pb
    import probation as pr
    import requisitions as rq
    import wave1_task_sync as w1t

    rq.ensure_requisitions_schema(cur)
    pb.ensure_preboarding_schema(cur)
    pr.ensure_probation_schema(cur)
    rq.set_settings(cur, COMPANY, enabled=True, jobs_require_approved_requisition=True)
    pb.set_settings(cur, COMPANY, enabled=True, auto_create_on_offer_accept=True, required_for_ready_mark=True)
    pr.set_settings(cur, COMPANY, enabled=True, auto_plan_on_hire=True, start_mode="hire_date")
    for mod in ("requisitions", "preboarding", "probation", "pre_hiring", "onboarding"):
        cur.execute(
            """
            INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
            VALUES (%s,%s,true,'wave1_visual_canary','{}'::jsonb, now())
            ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true, updated_at=now()
            """,
            (COMPANY, mod),
        )

    suffix = uuid.uuid4().hex[:6]
    meta = json.dumps({"fixture": TAG, "seed": suffix})

    # Requisitions — pending + open
    pending = rq.create_requisition(
        cur,
        company_code=COMPANY,
        title_en=f"[Canary] Headcount Ops {suffix}",
        title_ar=f"[تجريبي] احتياج تشغيلي {suffix}",
        headcount=2,
        department="Operations",
        created_by_user_id="visual-creator",
        submit=True,
        idempotency_key=f"vis-req-p:{suffix}",
    )
    rid_p = (pending.get("requisition") or {}).get("requisition_id")
    if rid_p:
        cur.execute("UPDATE requisitions SET metadata=%s::jsonb WHERE requisition_id=%s", (meta, rid_p))
        w1t.on_requisition_pending_approval(cur, company_code=COMPANY, requisition=pending.get("requisition") or {})

    open_req = rq.create_requisition(
        cur,
        company_code=COMPANY,
        title_en=f"[Canary] Open Eng {suffix}",
        title_ar=f"[تجريبي] هندسة مفتوح {suffix}",
        headcount=1,
        department="Engineering",
        created_by_user_id="visual-creator",
        submit=True,
        idempotency_key=f"vis-req-o:{suffix}",
    )
    rid_o = (open_req.get("requisition") or {}).get("requisition_id")
    ver = (open_req.get("requisition") or {}).get("row_version")
    if rid_o:
        approved = rq.transition_requisition(
            cur,
            company_code=COMPANY,
            requisition_id=str(rid_o),
            to_status="approved",
            actor_user_id="visual-approver",
            expected_row_version=ver,
        )
        ver2 = (approved.get("requisition") or {}).get("row_version")
        rq.transition_requisition(
            cur,
            company_code=COMPANY,
            requisition_id=str(rid_o),
            to_status="open",
            actor_user_id="visual-approver",
            expected_row_version=ver2,
        )
        cur.execute("UPDATE requisitions SET metadata=%s::jsonb WHERE requisition_id=%s", (meta, rid_o))

    # Preboarding future joiner
    joining = date.today() + timedelta(days=10)
    phone = f"9655000{suffix[:4]}"
    emp = f"{COMPANY}-VIS-{suffix}"
    cur.execute(
        """
        INSERT INTO employees (employee_key, company_code, name, phone, employment_status, start_date, updated_at)
        VALUES (%s,%s,%s,%s,'pending_start',%s, now())
        ON CONFLICT (employee_key) DO UPDATE SET employment_status='pending_start', start_date=EXCLUDED.start_date, updated_at=now()
        """,
        (emp, COMPANY, f"Visual Joiner {suffix}", phone, joining),
    )
    pb.ensure_provisional_pending_start(
        cur, company_code=COMPANY, employee_key=emp, name=f"Visual Joiner {suffix}", joining_date=joining, phone=phone
    )
    asn = pb.create_assignment(
        cur,
        company_code=COMPANY,
        employee_key=emp,
        joining_date=joining,
        created_by_user_id="visual-hr",
        idempotency_key=f"vis-pb:{suffix}",
    )
    aid = (asn.get("assignment") or {}).get("assignment_id")
    if aid:
        try:
            cur.execute(
                "UPDATE preboard_assignments SET metadata = COALESCE(metadata,'{}'::jsonb) || %s::jsonb WHERE assignment_id=%s",
                (meta, aid),
            )
        except Exception:
            pass

    # Probation active case
    emp2 = f"{COMPANY}-VIS-PRB-{suffix}"
    start = date.today() - timedelta(days=20)
    cur.execute(
        """
        INSERT INTO employees (employee_key, company_code, name, phone, employment_status, start_date, updated_at)
        VALUES (%s,%s,%s,%s,'active',%s, now())
        ON CONFLICT (employee_key) DO UPDATE SET employment_status='active', updated_at=now()
        """,
        (emp2, COMPANY, f"Visual Probationer {suffix}", f"9655111{suffix[:4]}", start),
    )
    case = pr.create_case(
        cur,
        company_code=COMPANY,
        employee_key=emp2,
        probation_start=start,
        probation_days=90,
        manager_user_id="visual-mgr",
        actor_user_id="visual-hr",
        idempotency_key=f"vis-prb:{suffix}",
    )
    cid = (case.get("case") or {}).get("case_id")
    if cid:
        try:
            cur.execute(
                "UPDATE probation_cases SET metadata = COALESCE(metadata,'{}'::jsonb) || %s::jsonb WHERE case_id=%s",
                (meta, cid),
            )
        except Exception:
            pass

    return {
        "ok": True,
        "company_code": COMPANY,
        "suffix": suffix,
        "requisition_pending_id": rid_p,
        "requisition_open_id": rid_o,
        "preboard_assignment_id": aid,
        "probation_case_id": cid,
        "employee_pending_start": emp,
        "employee_probation": emp2,
        "cleanup": f"python3 ops-seed-wave1-visual-canary.py --cleanup",
    }


def main() -> int:
    import production_data_safety as _pds
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", default=os.environ.get("WATHEFNI_COMPANY_CODE"))
    parser.add_argument("--ack-non-production", default=os.environ.get("WATHEFNI_DATA_SAFETY_ACK"))
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.ack_non_production:
        os.environ["WATHEFNI_DATA_SAFETY_ACK"] = args.ack_non_production
    if args.company:
        os.environ["WATHEFNI_COMPANY_CODE"] = args.company
    target = _pds.require_fixture_tooling(company_code=args.company, destructive=args.cleanup)
    global COMPANY
    COMPANY = target.company_code
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))
    _enable_process_flags()
    try:
        conn, RealDictCursor = _connect()
    except Exception as exc:
        print(f"FAIL connect: {exc}")
        return 2
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if args.cleanup:
                n = cleanup(cur)
                conn.commit()
                print(json.dumps({"ok": True, "cleaned": n, "company_code": COMPANY}))
                return 0
            cleanup(cur)  # replace prior visual canary
            out = seed(cur)
            conn.commit()
            print(json.dumps(out, default=str))
            return 0 if out.get("ok") else 1
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
