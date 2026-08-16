#!/usr/bin/env python3
"""Isolated live Google Calendar soak against staging-green Interviews artifact.

Does NOT modify orchestrator code. Synthetic tenant INTVGCAL only.
Marker: interviews-live-gcal-soak-v1
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ORCH = Path("/opt/wathefni/staging/orchestrator")
sys.path.insert(0, str(ORCH))

MARKER = "interviews-live-gcal-soak-v1"
COMPANY = "INTVGCAL"
POSITION = "INTV_GCAL_ROLE"
PHONE = "+96588409901"
CAND_EMAIL = "cand.gcal.soak@intv.invalid"
PANEL_EMAIL = "panel.gcal.soak@intv.invalid"
ACCOUNT = "azizalmulla16@gmail.com"
EXPECTED_ARTIFACT = "4ffa87f435b613cc3ac1ed7cdf3c17fe3b9ec77c267cddf8ed596ccd90739a3a"
EVIDENCE = Path("/opt/wathefni/staging/orchestrator/ops/interviews")


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class Gate:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def check(self, name: str, ok: bool, detail: Any = None) -> None:
        self.rows.append({"gate": name, "result": "PASS" if ok else "FAIL", "detail": detail})
        print(("PASS" if ok else "FAIL") + f": {name} :: {detail}", flush=True)


def actor() -> dict[str, Any]:
    return {
        "actor_user_id": "hr-gcal-soak",
        "actor_phone": "96550009901",
        "actor_role": "hr",
        "actor_type": "human",
    }


def gog_json(args: list[str]) -> dict[str, Any]:
    env = os.environ.copy()
    cmd = ["gog", "-a", ACCOUNT, *args, "--json", "--no-input"]
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=90, env=env)
    parsed: Any = None
    out = (proc.stdout or "").strip()
    if out:
        try:
            parsed = json.loads(out)
        except Exception:
            parsed = {"raw": out}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": out[-4000:],
        "stderr": (proc.stderr or "")[-2000:],
        "json": parsed,
    }


def get_event(event_id: str) -> dict[str, Any]:
    return gog_json(["calendar", "event", "primary", event_id])


def list_events_around(start: datetime, end: datetime) -> list[dict[str, Any]]:
    from_s = (start - timedelta(hours=2)).isoformat()
    to_s = (end + timedelta(hours=2)).isoformat()
    res = gog_json(["calendar", "events", "primary", "--from", from_s, "--to", to_s, "--max", "50"])
    payload = res.get("json") or {}
    events: list[Any] = []
    if isinstance(payload, dict):
        for key in ("events", "items", "result"):
            if isinstance(payload.get(key), list):
                events = payload[key]
                break
        if not events and isinstance(payload.get("event"), dict):
            events = [payload["event"]]
    return [e for e in events if isinstance(e, dict)]


def attendee_emails(event: dict[str, Any]) -> set[str]:
    attendees = event.get("attendees") or []
    return {str(a.get("email") or "").lower() for a in attendees if isinstance(a, dict) and a.get("email")}


def event_status(event: dict[str, Any]) -> str:
    return str(event.get("status") or "").lower()


def extract_event(payload: dict[str, Any]) -> dict[str, Any]:
    js = payload.get("json")
    if not isinstance(js, dict):
        return {}
    if isinstance(js.get("event"), dict):
        return js["event"]
    if js.get("id") and (js.get("kind") == "calendar#event" or "start" in js):
        return js
    return {}


def cleanup(app: Any, cur: Any, *, google_event_ids: list[str]) -> dict[str, Any]:
    import interview_service as svc

    deleted = []
    for eid in list(dict.fromkeys([e for e in google_event_ids if e])):
        try:
            r = svc._google_delete(app, str(eid))
            deleted.append({"event_id": eid, "ok": bool(r.get("ok")), "raw": {"ok": r.get("ok"), "stderr": r.get("stderr")}})
        except Exception as exc:
            deleted.append({"event_id": eid, "ok": False, "error": str(exc)})
        gog_json(["calendar", "delete", "primary", str(eid), "--send-updates", "none", "-y"])

    for sql, params in [
        ("DELETE FROM interview_feedback_revisions WHERE submission_id IN (SELECT submission_id FROM interview_feedback_submissions WHERE company_code=%s)", (COMPANY,)),
        ("DELETE FROM interview_feedback_submissions WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM interview_feedback_versions WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM interview_feedback_definitions WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM candidate_interview_assignments WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM interview_schedule_operations WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM interview_video_retention_operations WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM candidate_video_interview_responses WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM candidate_interview_events WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM candidate_interviews WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM applications WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM company_modules WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM positions WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM companies WHERE company_code=%s", (COMPANY,)),
        ("DELETE FROM candidates WHERE phone=%s", (PHONE,)),
    ]:
        try:
            cur.execute("SAVEPOINT gcal_clean")
            cur.execute(sql, params)
            cur.execute("RELEASE SAVEPOINT gcal_clean")
        except Exception:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT gcal_clean")
            except Exception:
                pass
    return {"deleted_google_events": deleted}


def residue(cur: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    checks = {
        "interviews": ("SELECT COUNT(*) AS c FROM candidate_interviews WHERE company_code=%s", (COMPANY,)),
        "assignments": ("SELECT COUNT(*) AS c FROM candidate_interview_assignments WHERE company_code=%s", (COMPANY,)),
        "ops": ("SELECT COUNT(*) AS c FROM interview_schedule_operations WHERE company_code=%s", (COMPANY,)),
        "applications": ("SELECT COUNT(*) AS c FROM applications WHERE company_code=%s", (COMPANY,)),
        "companies": ("SELECT COUNT(*) AS c FROM companies WHERE company_code=%s", (COMPANY,)),
        "candidates": ("SELECT COUNT(*) AS c FROM candidates WHERE phone=%s", (PHONE,)),
    }
    for key, (sql, params) in checks.items():
        try:
            cur.execute("SAVEPOINT res_" + key)
            cur.execute(sql, params)
            out[key] = int((cur.fetchone() or {}).get("c") or 0)
            cur.execute("RELEASE SAVEPOINT res_" + key)
        except Exception:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT res_" + key)
            except Exception:
                pass
            out[key] = -1
    return out


def write_evidence(evidence: dict[str, Any]) -> Path:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / ("interviews-live-gcal-soak-" + stamp() + ".json")
    path.write_text(json.dumps(evidence, indent=2, default=str) + "\n")
    return path


def main() -> int:
    gate = Gate()
    evidence: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "marker": MARKER,
        "company": COMPANY,
        "artifact_sha_expected": EXPECTED_ARTIFACT,
        "account": ACCOUNT,
        "gates": [],
        "google_events": [],
        "residuals": {},
    }

    artifact = Path("/opt/wathefni/staging/last-green.sha256").read_text().strip()
    gate.check("artifact_sha_matches_staging_green", artifact == EXPECTED_ARTIFACT, artifact)
    if artifact != EXPECTED_ARTIFACT:
        evidence["gates"] = gate.rows
        evidence["verdict"] = "FAIL_ARTIFACT_MISMATCH"
        path = write_evidence(evidence)
        print(path)
        return 2

    if os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") != "wathefni_staging":
        print("REFUSING: not wathefni_staging", file=sys.stderr)
        return 2

    cal = gog_json(["calendar", "calendars"])
    gate.check("oauth_calendar_list_ok", bool(cal.get("ok")), ((cal.get("stderr") or "")[:300] or "ok"))
    if not cal.get("ok"):
        evidence["gates"] = gate.rows
        evidence["verdict"] = "FAIL_OAUTH_OPERATIONAL"
        evidence["residuals"]["oauth"] = {"stderr": cal.get("stderr"), "stdout": cal.get("stdout")}
        path = write_evidence(evidence)
        print(json.dumps({"verdict": evidence["verdict"], "path": str(path)}, indent=2))
        return 3

    import app
    import interview_lifecycle as life
    import interview_service as svc

    google_events: list[str] = []
    start_base = datetime.now(timezone.utc) + timedelta(days=3)
    start_base = start_base.replace(minute=0, second=0, microsecond=0)
    create_start = start_base + timedelta(hours=10)
    create_end = create_start + timedelta(minutes=30)
    resched_start = start_base + timedelta(hours=12)
    resched_end = resched_start + timedelta(minutes=30)
    app_key = MARKER + "-gcal-1"

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cleanup(app, cur, google_event_ids=[])
                cur.execute(
                    """
                    INSERT INTO companies(company_code,name,status,metadata,raw_json,created_at,updated_at)
                    VALUES (%s,%s,'active',%s,%s,now(),now())
                    ON CONFLICT (company_code) DO UPDATE SET
                      metadata=companies.metadata || EXCLUDED.metadata,
                      raw_json=companies.raw_json || EXCLUDED.raw_json,
                      updated_at=now()
                    """,
                    (
                        COMPANY,
                        "Interviews live GCal soak",
                        app.Json({"interviews_marker": MARKER, "timezone": "Asia/Kuwait"}),
                        app.Json({"interviews_marker": MARKER, "timezone": "Asia/Kuwait"}),
                    ),
                )
                cur.execute("DELETE FROM company_modules WHERE company_code=%s", (COMPANY,))
                for module in ("recruiting", "interviews"):
                    cur.execute(
                        """
                        INSERT INTO company_modules(company_code,module_key,enabled,source,updated_at)
                        VALUES (%s,%s,true,%s,now())
                        """,
                        (COMPANY, module, MARKER),
                    )
                cur.execute(
                    """
                    INSERT INTO positions(
                      company_code, position_code, title, title_en, title_ar, job_id, version, status,
                      location, work_arrangement, employment_type
                    ) VALUES (%s,%s,%s,%s,%s,%s,1,'open','Kuwait City','onsite','full_time')
                    ON CONFLICT (company_code, position_code) DO UPDATE SET title=EXCLUDED.title, status='open', updated_at=now()
                    """,
                    (COMPANY, POSITION, "GCal Soak Role", "GCal Soak Role", "GCal Soak Role", str(uuid.uuid4())),
                )
                cur.execute(
                    """
                    INSERT INTO candidates(phone, name, email, raw_json)
                    VALUES (%s,%s,%s,%s)
                    ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, email=EXCLUDED.email, raw_json=EXCLUDED.raw_json
                    """,
                    (PHONE, "GCal Soak Candidate", CAND_EMAIL, app.Json({"interviews_marker": MARKER})),
                )
                cur.execute("DELETE FROM applications WHERE company_code=%s AND app_key=%s", (COMPANY, app_key))
                try:
                    cur.execute("SAVEPOINT app_full")
                    cur.execute(
                        """
                        INSERT INTO applications(
                          app_key, company_code, phone, position_code, position_title, status, current_step,
                          cv_received, cv_received_at, data_source, ingested_at, updated_at, raw_json, lifecycle_version,
                          screening_status, candidate_name, candidate_email
                        ) VALUES (%s,%s,%s,%s,%s,'shortlisted','review',true,now()::date,'production',now(),now(),%s,0,'complete',%s,%s)
                        RETURNING *
                        """,
                        (
                            app_key,
                            COMPANY,
                            PHONE,
                            POSITION,
                            "GCal Soak Role",
                            app.Json(
                                {
                                    "interviews_marker": MARKER,
                                    "candidate_name": "GCal Soak Candidate",
                                    "candidate_email": CAND_EMAIL,
                                }
                            ),
                            "GCal Soak Candidate",
                            CAND_EMAIL,
                        ),
                    )
                    cur.execute("RELEASE SAVEPOINT app_full")
                except Exception:
                    cur.execute("ROLLBACK TO SAVEPOINT app_full")
                    cur.execute(
                        """
                        INSERT INTO applications(
                          app_key, company_code, phone, position_code, position_title, status, current_step,
                          cv_received, cv_received_at, data_source, ingested_at, updated_at, raw_json, lifecycle_version,
                          screening_status
                        ) VALUES (%s,%s,%s,%s,%s,'shortlisted','review',true,now()::date,'production',now(),now(),%s,0,'complete')
                        RETURNING *
                        """,
                        (
                            app_key,
                            COMPANY,
                            PHONE,
                            POSITION,
                            "GCal Soak Role",
                            app.Json(
                                {
                                    "interviews_marker": MARKER,
                                    "candidate_name": "GCal Soak Candidate",
                                    "candidate_email": CAND_EMAIL,
                                }
                            ),
                        ),
                    )
            conn.commit()

        gate.check("google_calendar_configured", life.google_calendar_configured(app), ACCOUNT)

        created = svc.schedule_interview(
            company_code=COMPANY,
            app_key=app_key,
            start=create_start.isoformat(),
            end=create_end.isoformat(),
            meeting_type="google_meet",
            panel=[{"email": PANEL_EMAIL, "role": "interviewer"}],
            idempotency_key=MARKER + ":create",
            actor=actor(),
            sync_external=True,
            move_application_stage=False,
            source=MARKER,
        )
        iv = created.get("interview") or {}
        event_id = str(iv.get("calendar_event_id") or "")
        if event_id:
            google_events.append(event_id)
        evidence["create"] = {
            "ok": created.get("ok"),
            "interview_id": iv.get("interview_id"),
            "status": iv.get("status"),
            "provider_sync_status": iv.get("provider_sync_status"),
            "provider_sync_error": iv.get("provider_sync_error"),
            "calendar_event_id": event_id,
            "meet_link": iv.get("meet_link"),
            "provider_sync": created.get("provider_sync"),
        }
        gate.check(
            "create_wathefni_scheduled",
            bool(created.get("ok")) and iv.get("status") == "scheduled",
            evidence["create"],
        )
        gate.check(
            "create_provider_synced",
            iv.get("provider_sync_status") == "synced" and bool(event_id),
            "sync=%s event=%s err=%s" % (iv.get("provider_sync_status"), event_id, iv.get("provider_sync_error")),
        )

        live = get_event(event_id) if event_id else {"ok": False}
        live_event = extract_event(live)
        evidence["create_google_event"] = {
            "id": live_event.get("id"),
            "status": live_event.get("status"),
            "attendees": live_event.get("attendees"),
            "hangoutLink": live_event.get("hangoutLink"),
            "start": live_event.get("start"),
            "end": live_event.get("end"),
            "summary": live_event.get("summary"),
        }
        emails = attendee_emails(live_event) if live_event else set()
        gate.check("create_one_google_event_exists", bool(live.get("ok")) and bool(live_event.get("id")), live_event.get("id"))
        gate.check(
            "create_attendees_candidate_and_panel",
            CAND_EMAIL.lower() in emails and PANEL_EMAIL.lower() in emails,
            sorted(emails),
        )
        gate.check(
            "create_meet_link_present",
            bool(live_event.get("hangoutLink") or iv.get("meet_link")),
            live_event.get("hangoutLink") or iv.get("meet_link"),
        )
        gate.check(
            "wathefni_canonical_after_create",
            iv.get("status") == "scheduled" and iv.get("provider_key") == "google",
            {"status": iv.get("status"), "provider_key": iv.get("provider_key")},
        )

        resched = svc.reschedule_interview(
            company_code=COMPANY,
            interview_id=str(iv["interview_id"]),
            start=resched_start.isoformat(),
            end=resched_end.isoformat(),
            meeting_type="google_meet",
            idempotency_key=MARKER + ":reschedule",
            actor=actor(),
            sync_external=True,
        )
        riv = resched.get("interview") or {}
        new_event_id = str(riv.get("calendar_event_id") or "")
        if new_event_id:
            google_events.append(new_event_id)
        evidence["reschedule"] = {
            "ok": resched.get("ok"),
            "status": riv.get("status"),
            "provider_sync_status": riv.get("provider_sync_status"),
            "provider_sync_error": riv.get("provider_sync_error"),
            "old_event_id": event_id,
            "new_event_id": new_event_id,
            "scheduled_start": str(riv.get("scheduled_start")),
            "provider_sync": resched.get("provider_sync"),
        }
        gate.check(
            "reschedule_same_event_id",
            new_event_id == event_id and riv.get("provider_sync_status") == "synced",
            evidence["reschedule"],
        )
        gate.check("reschedule_wathefni_still_canonical", riv.get("status") == "scheduled", riv.get("status"))

        updated = get_event(event_id) if event_id else {"ok": False}
        ue = extract_event(updated)
        evidence["reschedule_google_event"] = {
            "id": ue.get("id"),
            "status": ue.get("status"),
            "start": ue.get("start"),
            "end": ue.get("end"),
            "hangoutLink": ue.get("hangoutLink"),
        }
        prev_start = str(((live_event.get("start") or {}).get("dateTime") or ""))
        start_str = str(((ue.get("start") or {}).get("dateTime") or ""))
        gate.check(
            "reschedule_google_event_updated_in_place",
            ue.get("id") == event_id and bool(start_str) and start_str != prev_start,
            {"event_id": ue.get("id"), "start": start_str, "prev": prev_start},
        )

        nearby = list_events_around(create_start, resched_end)
        soak_events = [
            e
            for e in nearby
            if str(e.get("summary") or "").startswith("Wathefni interview")
            and event_status(e) != "cancelled"
            and (
                CAND_EMAIL.lower() in attendee_emails(e)
                or PANEL_EMAIL.lower() in attendee_emails(e)
                or e.get("id") == event_id
            )
        ]
        evidence["nearby_soak_events_after_reschedule"] = [
            {"id": e.get("id"), "status": e.get("status"), "start": e.get("start"), "summary": e.get("summary")}
            for e in soak_events
        ]
        gate.check(
            "no_duplicate_active_events_after_reschedule",
            len(soak_events) == 1 and soak_events[0].get("id") == event_id,
            evidence["nearby_soak_events_after_reschedule"],
        )

        cancelled = svc.cancel_interview(
            company_code=COMPANY,
            interview_id=str(iv["interview_id"]),
            idempotency_key=MARKER + ":cancel",
            actor=actor(),
            sync_external=True,
            revert_application_stage=False,
        )
        civ = cancelled.get("interview") or {}
        evidence["cancel"] = {
            "ok": cancelled.get("ok"),
            "status": civ.get("status"),
            "provider_sync_status": civ.get("provider_sync_status"),
            "provider_sync_error": civ.get("provider_sync_error"),
            "provider_sync": cancelled.get("provider_sync"),
            "calendar_event_id": civ.get("calendar_event_id"),
        }
        gate.check(
            "cancel_wathefni_cancelled_history_preserved",
            bool(cancelled.get("ok")) and civ.get("status") == "cancelled" and bool(civ.get("calendar_event_id") or event_id),
            evidence["cancel"],
        )
        gate.check(
            "cancel_provider_synced",
            civ.get("provider_sync_status") == "synced",
            civ.get("provider_sync_status"),
        )

        after = get_event(event_id) if event_id else {"ok": False}
        ae = extract_event(after)
        evidence["cancel_google_event"] = {
            "ok": after.get("ok"),
            "id": ae.get("id"),
            "status": ae.get("status"),
            "stderr": (after.get("stderr") or "")[:300],
        }
        cancelled_or_gone = (not after.get("ok")) or event_status(ae) == "cancelled" or not ae.get("id")
        gate.check("cancel_removes_or_cancels_google_event", cancelled_or_gone, evidence["cancel_google_event"])

        nearby2 = list_events_around(create_start, resched_end)
        active_soak = [
            e
            for e in nearby2
            if str(e.get("summary") or "").startswith("Wathefni interview")
            and event_status(e) != "cancelled"
            and (CAND_EMAIL.lower() in attendee_emails(e) or PANEL_EMAIL.lower() in attendee_emails(e) or e.get("id") == event_id)
        ]
        evidence["nearby_active_after_cancel"] = [
            {"id": e.get("id"), "status": e.get("status"), "summary": e.get("summary")} for e in active_soak
        ]
        gate.check("no_stale_active_meet_or_event_after_cancel", len(active_soak) == 0, evidence["nearby_active_after_cancel"])

    except Exception as exc:
        evidence["exception"] = str(exc)
        gate.check("soak_exception_free", False, str(exc))
        import traceback

        evidence["traceback"] = traceback.format_exc()

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                clean_meta = cleanup(app, cur, google_event_ids=google_events)
                res = residue(cur)
            conn.commit()
        evidence["cleanup"] = clean_meta
        evidence["residue"] = res
        gate.check("cleanup_zero_db_residue", all(v == 0 for v in res.values()), res)

        final_nearby = list_events_around(create_start, resched_end)
        final_active = [
            e
            for e in final_nearby
            if event_status(e) != "cancelled"
            and str(e.get("summary") or "").startswith("Wathefni interview")
            and (CAND_EMAIL.lower() in attendee_emails(e) or PANEL_EMAIL.lower() in attendee_emails(e))
        ]
        for eid in google_events:
            ge = get_event(eid)
            ge_e = extract_event(ge)
            if ge.get("ok") and event_status(ge_e) not in {"", "cancelled"} and ge_e.get("id"):
                final_active.append(ge_e)
        evidence["final_google_active"] = [
            {"id": e.get("id"), "status": e.get("status"), "summary": e.get("summary")} for e in final_active
        ]
        gate.check("cleanup_zero_google_residue", len(final_active) == 0, evidence["final_google_active"])
    except Exception as exc:
        gate.check("cleanup_completed", False, str(exc))
        evidence["cleanup_exception"] = str(exc)

    evidence["gates"] = gate.rows
    evidence["google_events"] = google_events
    evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
    fails = [g for g in gate.rows if g["result"] != "PASS"]
    evidence["summary"] = {"passed": len(gate.rows) - len(fails), "failed": len(fails), "total": len(gate.rows)}
    if any(g["gate"] == "oauth_calendar_list_ok" and g["result"] != "PASS" for g in gate.rows):
        evidence["verdict"] = "FAIL_OAUTH_OPERATIONAL"
    elif fails:
        evidence["verdict"] = "FAIL_PRODUCT"
    else:
        evidence["verdict"] = "PASS"

    path = write_evidence(evidence)
    print(json.dumps({"verdict": evidence["verdict"], "summary": evidence["summary"], "path": str(path)}, indent=2))
    return 0 if evidence["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
