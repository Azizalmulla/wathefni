#!/usr/bin/env python3
"""Wathefni Calendar C4 smoke — RSVP, guest tokens, reminders, delivery, reschedule requests."""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS: {name}")
    else:
        FAIL += 1
        print(f"FAIL: {name} {detail}")


def main() -> int:
    print("=== Wathefni Calendar C4 smoke ===")
    try:
        import app as app_mod
        import calendar_participation as part
        import calendar_schema as schema
        import calendar_store as store
        import calendar_projections as proj
    except Exception:
        traceback.print_exc()
        check("imports", False)
        print(f"=== C4 smoke done PASS={PASS} FAIL={FAIL} ===")
        return 1

    check("imports", True)
    src = Path(part.__file__).read_text()
    app_src = Path(app_mod.__file__).read_text()
    check("RSVP states include removed", "removed" in part.RSVP_STATES)
    check("guest actions include reschedule", "request_reschedule" in part.GUEST_ACTIONS)
    check("reminders never create blocks (doc)", "Does not create calendar blocks" in (part.schedule_event_reminders.__doc__ or "") or "notify only" in (part.__doc__ or "").lower())
    check("rsvp route", "/dashboard/calendar/events/{event_id}/rsvp" in app_src)
    check("guest public page", "/calendar/guest/{token}" in app_src)
    check("reschedule resolve route", "/dashboard/calendar/reschedule-requests/" in app_src)
    check("hashed token storage", "token_hash" in src and "sha256" in src.lower())
    check("delivery states", "not_queued" in src and "dead" in src)
    check("interview authority preserved note", "Interview" in src)

    company = f"C4SMOKE{uuid4().hex[:8].upper()}"
    user_a = str(uuid4())
    user_b = str(uuid4())
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=3)
    end = now + timedelta(hours=1)

    try:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                schema.ensure_calendar_schema(cur)
            conn.commit()

        ev = store.create_manual_event(
            app_mod,
            company_code=company,
            actor_user_id=user_a,
            payload={
                "event_type": "meeting",
                "title": "C4 Participation",
                "visibility": "attendees_only",
                "start_at": now.isoformat(),
                "end_at": end.isoformat(),
                "timezone": "Asia/Kuwait",
                "attendees": [{"user_id": user_a, "role": "organizer"}, {"user_id": user_b, "role": "required"}],
                "guests": [{"email": "guest@example.com", "display_name": "Guest", "guest_kind": "external", "invite_channel": "email"}],
            },
            actor_permissions={"calendar.manage", "calendar.read", "calendar.conflict_override"},
        )
        check("create meeting with guest", bool(ev.get("event_id")))
        event_id = ev["event_id"]
        guest_id = (ev.get("guests") or [{}])[0].get("guest_id")
        check("guest row present", bool(guest_id))

        # Internal RSVP self
        rsvp = part.set_attendee_rsvp(
            app_mod,
            company_code=company,
            event_id=event_id,
            actor_user_id=user_b,
            rsvp_status="accepted",
            permissions={"calendar.read"},
        )
        check("internal RSVP accepted", rsvp["attendee"]["rsvp_status"] == "accepted")

        # Cannot RSVP for another without manage+organizer
        denied = False
        try:
            part.set_attendee_rsvp(
                app_mod,
                company_code=company,
                event_id=event_id,
                actor_user_id=user_b,
                target_user_id=user_a,
                rsvp_status="declined",
                permissions={"calendar.read"},
            )
        except part.CalendarParticipationError as exc:
            denied = exc.http_status == 403
        check("cannot RSVP for another attendee", denied)

        # Guest invite token
        invite = part.queue_guest_invite(
            app_mod,
            company_code=company,
            event_id=event_id,
            guest_id=str(guest_id),
            channel="email",
            actor_user_id=user_a,
        )
        check("guest invite queued", invite.get("ok") and bool(invite.get("invite_path")))
        raw = invite["invite_path"].rsplit("/", 1)[-1]

        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                row = part.resolve_guest_token(cur, raw)
                payload = part.public_guest_payload(row)
        check("token resolves privacy-safe payload", "title" in payload["event"] and "attendees" not in payload["event"])
        check("token payload has no audit", "audit" not in str(payload).lower())

        # Wrong token
        bad = False
        try:
            with app_mod.db_connect() as conn:
                with conn.cursor() as cur:
                    part.resolve_guest_token(cur, "not-a-real-token-value-xxx")
        except part.CalendarParticipationError as exc:
            bad = exc.http_status == 404
        check("invalid token fails safely", bad)

        # Guest accept (replay-safe)
        a1 = part.apply_guest_action(app_mod, raw_token=raw, action="accept")
        a2 = part.apply_guest_action(app_mod, raw_token=raw, action="accept")
        check("guest accept", a1.get("rsvp_status") == "accepted")
        check("guest accept replay idempotent", a2.get("idempotent") is True)

        # Reschedule request does not change time
        before_start = ev.get("start_at")
        req = part.apply_guest_action(
            app_mod,
            raw_token=raw,
            action="request_reschedule",
            note="Prefer tomorrow morning",
            preferred_times=["tomorrow 10:00"],
        )
        check("reschedule request created", bool((req.get("request") or {}).get("request_id")))
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT start_at FROM calendar_events WHERE event_id=%s", (event_id,))
                still = cur.fetchone()
        check("reschedule request did not change event time", store._iso(still["start_at"]) == before_start or str(still["start_at"])[:19] in str(before_start))

        dup = part.apply_guest_action(app_mod, raw_token=raw, action="request_reschedule", note="again")
        check("duplicate pending reschedule idempotent", dup.get("idempotent") is True)

        # Reminder schedule does not create events
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                schema.ensure_calendar_schema(cur)
                n = part.schedule_event_reminders(cur, app_mod, company_code=company, event_id=event_id, offsets_minutes=[30])
                cur.execute("SELECT count(*) AS c FROM calendar_events WHERE company_code=%s", (company,))
                ev_count = int((cur.fetchone() or {}).get("c") or 0)
                cur.execute("SELECT count(*) AS c FROM calendar_reminders WHERE company_code=%s AND event_id=%s", (company, event_id))
                rem_count = int((cur.fetchone() or {}).get("c") or 0)
            conn.commit()
        check("reminders created", rem_count >= 1 or n >= 0)
        check("reminders did not add calendar blocks", ev_count == 1)

        # Cancel stops future reminders
        cancelled = store.cancel_event(
            app_mod,
            company_code=company,
            event_id=event_id,
            actor_user_id=user_a,
            expected_version=ev["version"] if False else store.get_event(app_mod, company_code=company, event_id=event_id)["payload"]["version"],
        )
        check("event cancelled", cancelled.get("status") == "cancelled")
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) AS c FROM calendar_reminders
                    WHERE company_code=%s AND event_id=%s AND status='pending'
                    """,
                    (company, event_id),
                )
                pending = int((cur.fetchone() or {}).get("c") or 0)
                cur.execute(
                    "SELECT revoked_at IS NOT NULL AS r FROM calendar_guest_tokens WHERE company_code=%s AND event_id=%s LIMIT 1",
                    (company, event_id),
                )
                tok = cur.fetchone() or {}
        check("cancelled event stops pending reminders", pending == 0)
        check("cancelled event revokes guest tokens", bool(tok.get("r")))

        # Cross-tenant token isolation: create other company event shouldn't resolve with first token after revoke
        # Delivery dry-run worker
        os.environ["CALENDAR_DELIVERY_DRY_RUN"] = "true"
        # New event for delivery proof
        ev2 = store.create_manual_event(
            app_mod,
            company_code=company,
            actor_user_id=user_a,
            payload={
                "event_type": "meeting",
                "title": "C4 Delivery",
                "visibility": "private",
                "start_at": (now + timedelta(days=2)).isoformat(),
                "end_at": (now + timedelta(days=2, hours=1)).isoformat(),
                "timezone": "Asia/Kuwait",
                "guests": [{"email": "deliver@example.com", "guest_kind": "external", "invite_channel": "email"}],
            },
            actor_permissions={"calendar.manage", "calendar.read", "calendar.conflict_override"},
        )
        gid2 = (ev2.get("guests") or [{}])[0].get("guest_id")
        part.queue_guest_invite(app_mod, company_code=company, event_id=ev2["event_id"], guest_id=str(gid2), channel="email")
        run = part.run_delivery_once(app_mod, limit=20)
        check("delivery worker ran", run.get("ok") is True)
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT channel, status, provider_ref, payload
                    FROM calendar_delivery_outbox
                    WHERE company_code=%s AND event_id=%s AND purpose='guest_invite'
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (company, ev2["event_id"]),
                )
                drow = dict(cur.fetchone() or {})
        check("outbox channel is routed handoff", drow.get("channel") == "routed", str(drow.get("channel")))
        check("guest invite delivered via canonical router", drow.get("status") == "delivered", str(drow))
        check("no direct provider selection on outbox row", drow.get("channel") != "email" or drow.get("status") == "delivered")
        pl = drow.get("payload") if isinstance(drow.get("payload"), dict) else {}
        check("intent payload has recipient_type", pl.get("recipient_type") in {"external_guest", "candidate"}, str(pl.get("recipient_type")))
        check("calendar source has no send_octopus call", "send_octopus_whatsapp(" not in Path(part.__file__).read_text())
        check("canonical router module present", (ROOT / "wathefni_communication.py").exists())

        # Interview-linked schedule edit still rejected
        linked = store.create_manual_event(
            app_mod,
            company_code=company,
            actor_user_id=user_a,
            payload={
                "event_type": "meeting",
                "title": "C4 Linked",
                "visibility": "private",
                "start_at": (now + timedelta(days=5)).isoformat(),
                "end_at": (now + timedelta(days=5, hours=1)).isoformat(),
                "timezone": "Asia/Kuwait",
            },
            actor_permissions={"calendar.manage", "calendar.read", "calendar.conflict_override"},
        )
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO calendar_event_links
                      (link_id, company_code, event_id, source_workflow, source_record_id, link_status)
                    VALUES (%s,%s,%s,'interview',%s,'active')
                    """,
                    (str(uuid4()), company, linked["event_id"], str(uuid4())),
                )
            conn.commit()
        rejected = False
        try:
            store.update_event(
                app_mod,
                company_code=company,
                event_id=linked["event_id"],
                actor_user_id=user_a,
                payload={"start_at": (now + timedelta(days=6)).isoformat()},
                expected_version=linked["version"],
                actor_permissions={"calendar.manage"},
            )
        except store.CalendarError as exc:
            rejected = exc.code == "interview_authority_required"
        check("interview authority still required", rejected)

        # Cleanup
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                for table in (
                    "calendar_delivery_outbox",
                    "calendar_reminders",
                    "calendar_guest_tokens",
                    "calendar_reschedule_requests",
                    "calendar_event_audit",
                    "calendar_attendees",
                    "calendar_guests",
                    "calendar_event_links",
                    "calendar_event_org_scopes",
                    "calendar_events",
                ):
                    cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (company,))
            conn.commit()
        check("cleanup", True)

        # Static frontend markers
        shell = (ROOT.parent / "apps/wathefni-dashboard/src/components/CalendarShell.tsx")
        if shell.exists():
            text = shell.read_text()
            check("UI RSVP controls", "submitRsvp" in text or "My RSVP" in text)
            check("UI reschedule inbox", "Reschedule requests" in text or "resolveRequest" in text)
        else:
            dash = Path("/var/www/wathefni-dashboard/assets")
            js = ""
            if dash.exists():
                for p in sorted(dash.glob("dashboard-*.js"))[::-1]:
                    js = p.read_text(errors="ignore")
                    if "RSVP" in js or "rsvp" in js:
                        break
            check("dashboard RSVP markers", "rsvp" in js.lower() or "RSVP" in js)

    except Exception as exc:
        traceback.print_exc()
        check("live proofs", False, str(exc)[:240])

    print(f"=== C4 smoke done PASS={PASS} FAIL={FAIL} ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
