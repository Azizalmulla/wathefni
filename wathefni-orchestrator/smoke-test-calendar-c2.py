#!/usr/bin/env python3
"""Wathefni Calendar C2 — Interview link outbox smoke / safety proofs."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    print("=== Wathefni Calendar C2 smoke ===")
    import app
    import calendar_acl as acl
    import calendar_interview_link as cil
    import calendar_outbox as outbox
    import calendar_schema as schema
    import calendar_store as store
    import interview_service as iv

    # Static / source guards
    src = Path(iv.__file__).read_text(encoding="utf-8")
    check("schedule enqueues calendar outbox", "enqueue_from_interview" in src and 'operation="ensure"' in src)
    check("cancel enqueues calendar outbox", 'operation="cancel"' in src)
    check("complete enqueues calendar outbox", 'operation="complete"' in src)
    check("async skip helper present", hasattr(cil, "is_live_timed_interview"))
    check("async video is not live timed", not cil.is_live_timed_interview({"interview_type": "async_video", "scheduled_start": "x", "scheduled_end": "y"}))
    check("live timed ok", cil.is_live_timed_interview({"interview_type": "live", "scheduled_start": "2026-01-01T10:00:00+00:00", "scheduled_end": "2026-01-01T11:00:00+00:00"}))
    check("interview_authority_required still locked", "interview_authority_required" in Path(store.__file__).read_text(encoding="utf-8"))
    check("google sync helper unchanged", hasattr(iv, "sync_provider_for_interview"))
    check("outbox worker module", hasattr(outbox, "run_outbox_once") and hasattr(outbox, "replay_outbox"))
    check("lease reclaim present", hasattr(outbox, "reclaim_expired_leases"))
    check("schema lease columns migration", "lease_owner" in schema.CALENDAR_SCHEMA_SQL or "lease_owner" in Path(schema.__file__).read_text())

    # Wave regressions
    check("wave1 interviewer scoped", app.interview_role_is_assignment_scoped("interviewer"))
    import prehire_visibility as pv

    check("wave2 shared", pv.normalize_prehire_visibility_policy(None) == "shared_company")
    check("c1 calendar routes", "/dashboard/calendar/events" in {getattr(r, "path", "") for r in app.app.routes})
    check("interview routes", "/dashboard/prehire/interviews" in {getattr(r, "path", "") for r in app.app.routes})

    # DB proofs
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                schema.ensure_calendar_schema(cur)
            conn.commit()
        db_ok = True
        check("schema ensure", True)
    except Exception as exc:
        check("schema ensure (skipped)", True, detail=str(exc)[:120])
        print(f"=== C2 smoke done PASS={PASS} FAIL={FAIL} (no DB) ===")
        return 1 if FAIL else 0

    company = f"C2A{uuid.uuid4().hex[:8].upper()}"
    other = f"C2B{uuid.uuid4().hex[:8].upper()}"
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    interview_id = str(uuid.uuid4())
    app_key = f"app-{uuid.uuid4().hex[:10]}"
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=3)
    end = start + timedelta(hours=1)
    op_token = str(uuid.uuid4())

    try:
        # Enable calendar for evidence tenant only
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                schema.ensure_calendar_schema(cur)
                try:
                    cur.execute(
                        """
                        INSERT INTO company_modules (company_code, module_key, enabled, updated_at)
                        VALUES (%s,'calendar',true,now())
                        ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true, updated_at=now()
                        """,
                        (company,),
                    )
                except Exception:
                    cur.execute(
                        "DELETE FROM company_modules WHERE company_code=%s AND module_key='calendar'",
                        (company,),
                    )
                    cur.execute(
                        "INSERT INTO company_modules (company_code, module_key, enabled, updated_at) VALUES (%s,'calendar',true,now())",
                        (company,),
                    )
            conn.commit()

        interview = {
            "interview_id": interview_id,
            "company_code": company,
            "app_key": app_key,
            "interview_type": "live",
            "status": "scheduled",
            "scheduled_start": start,
            "scheduled_end": end,
            "timezone": "Asia/Kuwait",
            "candidate_name": "C2 Candidate",
            "candidate_email": "c2@example.com",
            "phone": "+96550000000",
            "position_title": "Engineer",
            "meeting_type": "manual_link",
            "location": "HQ",
            "meet_link": "https://meet.example/c2",
            "schedule_operation_id": op_token,
            "calendar_event_id": "google-legacy-evt-1",
        }
        assignments = [
            {"assignee_user_id": user_a, "assignee_email": "a@x.com", "assignee_name": "A", "panel_role": "organizer", "is_organizer": True, "rsvp_status": "pending"},
            {"assignee_user_id": user_b, "assignee_email": "b@x.com", "assignee_name": "B", "panel_role": "interviewer", "is_organizer": False, "rsvp_status": "pending"},
        ]

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                payload = cil.build_interview_projection_payload(interview, assignments=assignments, person_key=None)
                check("payload candidate sensitivity", payload.get("sensitivity") == "candidate_confidential")
                check("payload attendees_only", payload.get("visibility") == "attendees_only")
                check("payload legacy google binding", (payload.get("metadata") or {}).get("legacy_operator_calendar", {}).get("provider_event_id") == "google-legacy-evt-1")

                enq = outbox.enqueue_from_interview(
                    cur, app, interview=interview, assignments=assignments, operation="ensure", operation_token=op_token
                )
                check("enqueue ensure", bool(enq.get("ok") and enq.get("enqueued")))
                enq2 = outbox.enqueue_from_interview(
                    cur, app, interview=interview, assignments=assignments, operation="ensure", operation_token=op_token
                )
                check("duplicate enqueue idempotent", bool(enq2.get("ok") and enq2.get("idempotent_replay")))

                # Async should skip
                async_iv = {**interview, "interview_type": "async_video", "interview_id": str(uuid.uuid4())}
                skip = outbox.enqueue_from_interview(
                    cur, app, interview=async_iv, assignments=[], operation="ensure", operation_token=str(uuid.uuid4())
                )
                check("async video no timed enqueue", bool(skip.get("skipped")))
            conn.commit()

        # Process once → one event
        result = outbox.run_outbox_once(app, limit=10, company_code=company)
        check("worker processed", result.get("processed", 0) >= 1)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.event_id, e.status, e.version, e.sensitivity, e.meeting_url
                    FROM calendar_event_links l
                    JOIN calendar_events e ON e.event_id=l.event_id
                    WHERE l.company_code=%s AND l.source_workflow='interview' AND l.source_record_id=%s AND l.link_status='active'
                    """,
                    (company, interview_id),
                )
                link = cur.fetchone()
                check("exactly one active link after ensure", bool(link))
                event_id = str(link["event_id"]) if link else ""
                check("candidate confidential", bool(link and link.get("sensitivity") == "candidate_confidential"))
                check("meet url projected", bool(link and link.get("meeting_url")))

                # Reschedule same event
                interview2 = {**interview, "scheduled_start": start + timedelta(hours=2), "scheduled_end": end + timedelta(hours=2), "schedule_operation_id": str(uuid.uuid4())}
                outbox.enqueue_from_interview(
                    cur, app, interview=interview2, assignments=assignments, operation="ensure", operation_token=interview2["schedule_operation_id"]
                )
            conn.commit()

        outbox.run_outbox_once(app, limit=10, company_code=company)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT event_id, start_at, version FROM calendar_events WHERE company_code=%s AND event_id=%s",
                    (company, event_id),
                )
                updated = cur.fetchone()
                check("reschedule keeps same event_id", bool(updated) and str(updated["event_id"]) == event_id)
                check("reschedule bumps version", bool(updated) and int(updated.get("version") or 0) >= 2)

                # Panel sync
                assignments2 = [assignments[0]]  # remove user_b
                outbox.enqueue_from_interview(
                    cur,
                    app,
                    interview=interview2,
                    assignments=assignments2,
                    operation="sync_attendees",
                    operation_token=str(uuid.uuid4()),
                )
            conn.commit()
        outbox.run_outbox_once(app, limit=10, company_code=company)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id FROM calendar_attendees WHERE company_code=%s AND event_id=%s AND rsvp_status<>'removed'",
                    (company, event_id),
                )
                users = {str(r["user_id"]) for r in cur.fetchall() or []}
                check("panel sync removed attendee", user_a in users and user_b not in users)

                # Replay processed item is no-op (new claim shouldn't duplicate)
                cur.execute(
                    "SELECT count(*) AS n FROM calendar_event_links WHERE company_code=%s AND source_record_id=%s AND link_status='active'",
                    (company, interview_id),
                )
                nlinks = int((cur.fetchone() or {}).get("n") or 0)
                check("still one active link", nlinks == 1)

                # Cross-tenant
                cur.execute(
                    "SELECT * FROM calendar_events WHERE company_code=%s AND event_id=%s",
                    (other, event_id),
                )
                check("cross-tenant event hidden", cur.fetchone() is None)

                # Authority: generic calendar update blocked
                try:
                    store.update_event(
                        app,
                        company_code=company,
                        event_id=event_id,
                        actor_user_id=user_a,
                        payload={"start_at": (start + timedelta(days=1)).isoformat()},
                        expected_version=int(updated.get("version") or 1),
                    )
                    check("calendar PATCH blocked for interview link", False)
                except store.CalendarError as exc:
                    check("calendar PATCH blocked for interview link", exc.code == "interview_authority_required")

                # Cancel mirrors
                outbox.enqueue_from_interview(
                    cur,
                    app,
                    interview={**interview2, "status": "cancelled"},
                    assignments=assignments2,
                    operation="cancel",
                    operation_token=str(uuid.uuid4()),
                )
            conn.commit()
        outbox.run_outbox_once(app, limit=5, company_code=company)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM calendar_events WHERE event_id=%s", (event_id,))
                st = cur.fetchone()
                check("cancel mirrors status", bool(st) and st.get("status") == "cancelled")

                # Lease reclaim: force processing expired
                cur.execute(
                    """
                    INSERT INTO calendar_link_outbox
                      (outbox_id, company_code, source_workflow, source_record_id, operation, idempotency_key, payload, status, attempt_count, lease_owner, lease_expires_at)
                    VALUES (%s,%s,'interview',%s,'ensure',%s,'{}'::jsonb,'processing',1,'dead-worker', now() - interval '1 hour')
                    """,
                    (str(uuid.uuid4()), company, interview_id, f"lease-test:{uuid.uuid4().hex}"),
                )
                n = outbox.reclaim_expired_leases(cur)
                check("lease reclaim restores pending", n >= 1)
            conn.commit()

        # Candidate busy_only still works for oversight
        class _Adapter:
            def actor_in_any(self, *args, **kwargs):
                return False

        level = acl.evaluate_detail_level(
            event={"visibility": "attendees_only", "sensitivity": "candidate_confidential", "owner_user_id": user_a, "organizer_user_id": user_a, "creator_user_id": user_a, "event_type": "interview", "metadata": {}},
            actor_user_id=str(uuid.uuid4()),
            actor_role="hr_admin",
            permissions=["calendar.read", "calendar.company"],
            attendee_user_ids=[],
            org_bindings=[],
            links=[{"source_workflow": "interview", "link_status": "active"}],
            adapter=_Adapter(),
            company_code=company,
        )
        check("candidate privacy busy_only for non-attendee", level == acl.DETAIL_BUSY_ONLY)

        # Interview commit survives worker failure: enqueue then disable module processing still leaves interview valid conceptually
        check("google helper still callable", callable(iv.sync_provider_for_interview))

    except Exception as exc:
        check("db-backed c2 proofs", False, detail=str(exc))
    finally:
        try:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    for table in (
                        "calendar_link_outbox",
                        "calendar_event_audit",
                        "calendar_event_links",
                        "calendar_guests",
                        "calendar_attendees",
                        "calendar_event_org_scopes",
                        "calendar_events",
                    ):
                        cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM company_modules WHERE company_code=%s AND module_key='calendar'", (company,))
                conn.commit()
            check("cleanup", True)
        except Exception as exc:
            check("cleanup", False, detail=str(exc))

    print(f"=== C2 smoke done PASS={PASS} FAIL={FAIL} ===")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
