#!/usr/bin/env python3
"""Calendar C2 durability amendment — transactional outbox proofs."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail: str | None = None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS: {label}")
    else:
        FAIL += 1
        print(f"FAIL: {label}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("=== Wathefni Calendar C2 durability amendment ===")
    import app
    import calendar_outbox as outbox
    import calendar_schema as schema
    import interview_service as iv

    src = Path(iv.__file__).read_text(encoding="utf-8")
    import re

    check("require helper present", "_require_calendar_outbox_intent" in src)
    check(
        "no swallow of enqueue_from_interview",
        re.search(r"enqueue_from_interview[\s\S]{0,240}except Exception:\s*\n\s*pass", src) is None,
    )
    check("module policy always_enqueue_defer", outbox.MODULE_DISABLED_POLICY == "always_enqueue_defer_until_enabled")
    check("CalendarOutboxError defined", hasattr(outbox, "CalendarOutboxError"))
    check("require_enqueue_from_interview defined", callable(outbox.require_enqueue_from_interview))
    check("schedule uses require helper", "_require_calendar_outbox_intent" in src and 'operation="ensure"' in src)
    check("cancel uses require helper", 'operation="cancel"' in src and "_require_calendar_outbox_intent" in src)

    app_src = Path(app.__file__).read_text(encoding="utf-8")
    check("dashboard status uses require_enqueue", "require_enqueue_from_interview" in app_src)
    check("dashboard rolls back on outbox failure", "conn.rollback()" in app_src and "CalendarOutboxError" in app_src)

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                schema.ensure_calendar_schema(cur)
            conn.commit()
    except Exception as exc:
        check("db available", False, detail=str(exc)[:200])
        print(f"=== durability done PASS={PASS} FAIL={FAIL} ===")
        return 1 if FAIL else 0

    company = f"C2D{uuid.uuid4().hex[:8].upper()}"
    interview_id = str(uuid.uuid4())
    marker = f"durability-{uuid.uuid4().hex[:8]}"
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=4)
    end = start + timedelta(hours=1)

    # 1) Forced outbox insert failure must not leave Interview mutation committed.
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                schema.ensure_calendar_schema(cur)
                cur.execute(
                    """
                    INSERT INTO candidate_interviews (
                      interview_id, company_code, app_key, interview_type, status,
                      scheduled_start, scheduled_end, timezone, candidate_name, source
                    ) VALUES (%s,%s,%s,'live','scheduled',%s,%s,'Asia/Kuwait',%s,%s)
                    """,
                    (interview_id, company, f"app-{marker}", start, end, marker, marker),
                )
                interview = {
                    "interview_id": interview_id,
                    "company_code": company,
                    "app_key": f"app-{marker}",
                    "interview_type": "live",
                    "status": "scheduled",
                    "scheduled_start": start,
                    "scheduled_end": end,
                    "timezone": "Asia/Kuwait",
                    "candidate_name": marker,
                }

                def _boom(*args, **kwargs):
                    raise outbox.CalendarOutboxError(
                        "calendar_outbox_enqueue_failed",
                        "forced failure for durability proof",
                        retryable=True,
                    )

                with mock.patch.object(outbox, "enqueue_interview_calendar_intent", side_effect=_boom):
                    raised = False
                    try:
                        outbox.require_enqueue_from_interview(
                            cur,
                            app,
                            interview=interview,
                            assignments=[],
                            operation="ensure",
                            operation_token=f"tok-{marker}",
                        )
                    except outbox.CalendarOutboxError:
                        raised = True
                    check("forced enqueue failure raises", raised)
                # Do not commit — simulate caller abort
                conn.rollback()

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM candidate_interviews WHERE interview_id=%s AND company_code=%s",
                    (interview_id, company),
                )
                check("interview mutation not committed after outbox failure", cur.fetchone() is None)
                cur.execute(
                    "SELECT 1 FROM calendar_link_outbox WHERE company_code=%s AND source_record_id=%s",
                    (company, interview_id),
                )
                check("no orphan outbox after rollback", cur.fetchone() is None)
    except Exception as exc:
        check("forced failure rollback proof", False, detail=str(exc))

    # 2) Successful TX: interview + outbox commit together; worker failure does not undo interview.
    interview_id2 = str(uuid.uuid4())
    token2 = f"tok2-{uuid.uuid4().hex[:8]}"
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO candidate_interviews (
                      interview_id, company_code, app_key, interview_type, status,
                      scheduled_start, scheduled_end, timezone, candidate_name, source
                    ) VALUES (%s,%s,%s,'live','scheduled',%s,%s,'Asia/Kuwait',%s,%s)
                    """,
                    (interview_id2, company, f"app2-{marker}", start, end, marker, marker),
                )
                interview2 = {
                    "interview_id": interview_id2,
                    "company_code": company,
                    "app_key": f"app2-{marker}",
                    "interview_type": "live",
                    "status": "scheduled",
                    "scheduled_start": start,
                    "scheduled_end": end,
                    "timezone": "Asia/Kuwait",
                    "candidate_name": marker,
                    "schedule_operation_id": token2,
                }
                enq = outbox.require_enqueue_from_interview(
                    cur,
                    app,
                    interview=interview2,
                    assignments=[{"assignee_user_id": str(uuid.uuid4()), "is_organizer": True, "panel_role": "organizer"}],
                    operation="ensure",
                    operation_token=token2,
                )
                check("successful require enqueue", bool(enq.get("ok") and (enq.get("enqueued") or enq.get("idempotent_replay"))))
                # Duplicate in same TX is idempotent success
                enq2 = outbox.require_enqueue_from_interview(
                    cur,
                    app,
                    interview=interview2,
                    assignments=[],
                    operation="ensure",
                    operation_token=token2,
                )
                check("duplicate enqueue idempotent success", bool(enq2.get("ok") and enq2.get("idempotent_replay")))
            conn.commit()

        # Simulate worker failure: mark outbox dead without deleting interview
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE calendar_link_outbox
                    SET status='dead', last_error='forced_worker_failure', updated_at=now()
                    WHERE company_code=%s AND source_record_id=%s
                    """,
                    (company, interview_id2),
                )
            conn.commit()

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM candidate_interviews WHERE interview_id=%s AND company_code=%s",
                    (interview_id2, company),
                )
                row = cur.fetchone()
                check("worker failure does not undo interview truth", bool(row) and row.get("status") == "scheduled")
                cur.execute(
                    "SELECT status FROM calendar_link_outbox WHERE company_code=%s AND source_record_id=%s",
                    (company, interview_id2),
                )
                ob = cur.fetchone()
                check("outbox intent still durable after worker failure", bool(ob) and ob.get("status") == "dead")
    except Exception as exc:
        check("commit + worker failure proof", False, detail=str(exc))

    # 3) Module-disabled policy: still enqueues (defer later)
    interview_id3 = str(uuid.uuid4())
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM company_modules WHERE company_code=%s AND module_key='calendar'", (company,))
                cur.execute(
                    """
                    INSERT INTO candidate_interviews (
                      interview_id, company_code, app_key, interview_type, status,
                      scheduled_start, scheduled_end, timezone, candidate_name, source
                    ) VALUES (%s,%s,%s,'live','scheduled',%s,%s,'Asia/Kuwait',%s,%s)
                    """,
                    (interview_id3, company, f"app3-{marker}", start, end, marker, marker),
                )
                interview3 = {
                    "interview_id": interview_id3,
                    "company_code": company,
                    "app_key": f"app3-{marker}",
                    "interview_type": "live",
                    "status": "scheduled",
                    "scheduled_start": start,
                    "scheduled_end": end,
                    "timezone": "Asia/Kuwait",
                    "candidate_name": marker,
                }
                # Confirm module disabled
                enabled = False
                if callable(getattr(app, "company_has_module", None)):
                    enabled = bool(app.company_has_module(company, "calendar"))
                check("test tenant calendar module disabled", enabled is False)
                enq3 = outbox.require_enqueue_from_interview(
                    cur,
                    app,
                    interview=interview3,
                    assignments=[],
                    operation="ensure",
                    operation_token=f"tok3-{marker}",
                )
                check("module-disabled still enqueues intent", bool(enq3.get("ok") and enq3.get("enqueued")))
            conn.commit()

        # Worker should defer, not drop intent
        result = outbox.run_outbox_once(app, limit=20, company_code=company)
        check("module-disabled worker defers", int(result.get("deferred") or 0) >= 1)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, last_error FROM calendar_link_outbox
                    WHERE company_code=%s AND source_record_id=%s
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (company, interview_id3),
                )
                row = cur.fetchone()
                check(
                    "intent retained under module-disabled policy",
                    bool(row) and row.get("status") in {"pending", "failed", "processing"},
                )
                # Interview still present — enabling later + backfill covers history;
                # this intent means live ops after C2 are not silently missed.
                cur.execute(
                    "SELECT 1 FROM candidate_interviews WHERE interview_id=%s",
                    (interview_id3,),
                )
                check("interview + intent both durable when module off", bool(cur.fetchone()))
    except Exception as exc:
        check("module-disabled enqueue policy", False, detail=str(exc))

    # Cleanup
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for iid in (interview_id, interview_id2, interview_id3):
                    cur.execute("DELETE FROM calendar_link_outbox WHERE company_code=%s AND source_record_id=%s", (company, iid))
                    cur.execute("DELETE FROM candidate_interviews WHERE company_code=%s AND interview_id=%s", (company, iid))
                cur.execute("DELETE FROM company_modules WHERE company_code=%s AND module_key='calendar'", (company,))
            conn.commit()
        check("cleanup", True)
    except Exception as exc:
        check("cleanup", False, detail=str(exc))

    print(f"=== durability done PASS={PASS} FAIL={FAIL} ===")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
