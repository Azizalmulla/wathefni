#!/usr/bin/env python3
"""Prove narrow Teams Online Meetings authority + calendar link (RBACfA preserved)."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import interview_microsoft_calendar as mcal  # noqa: E402

EVIDENCE_UPN = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com"
DENIED_UPN = os.environ.get("WATHEFNI_M365_DENIED_UPN", "wathefni-rbac-deny-probe@wathefni.onmicrosoft.com").strip()


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evid = Path(os.environ.get("C6B_EVID", f"/opt/wathefni/production-evidence/wathefni-calendar-c6b/m365-teams-{stamp}"))
    evid.mkdir(parents=True, exist_ok=True)
    results: dict = {"stamp": stamp, "proofs": {}}

    def record(name: str, ok: bool, **details):
        safe = {k: v for k, v in details.items() if "token" not in k.lower() and "pem" not in k.lower()}
        results["proofs"][name] = {"ok": ok, **safe}
        print(("PASS" if ok else "FAIL"), name, json.dumps(safe, default=str)[:320])

    if not mcal.microsoft_env_configured():
        record("preconditions", False, error="microsoft_env_not_configured")
        (evid / "results.json").write_text(json.dumps(results, indent=2))
        return 1

    token = mcal.mint_graph_token()
    record("cert_token_mint", True)
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=9)
    end = start + timedelta(minutes=30)
    subject = f"OctoHR Teams authority {stamp}"

    created = mcal.create_teams_event(
        token=token,
        mailbox_upn=EVIDENCE_UPN,
        summary=subject,
        start=start,
        end=end,
        timezone_name="Asia/Kuwait",
        attendees=[EVIDENCE_UPN, "candidate-evidence@wathefni.onmicrosoft.com"],
        body="Teams authority proof invitation",
    )
    join = str(created.get("meet_link") or "")
    event_id = str(created.get("event_id") or "")
    om_id = str(created.get("online_meeting_id") or "")
    record(
        "teams_create_join_url",
        bool(created.get("ok") and join and "teams.microsoft.com" in join.lower()),
        has_join_url=bool(join),
        join_host=("teams.microsoft.com" if "teams.microsoft.com" in join.lower() else None),
        online_meeting_id=bool(om_id),
        error=created.get("error"),
        status=created.get("status"),
        detail=str(created.get("detail") or "")[:220],
    )
    record(
        "calendar_event_linked",
        bool(event_id and join and created.get("linked")),
        has_event_id=bool(event_id),
        has_web_link=bool(created.get("web_link")),
    )
    att = ((created.get("json") or {}).get("attendees") or []) if isinstance(created.get("json"), dict) else []
    record("attendees_on_invite", len(att) >= 1, attendee_count=len(att))
    start_obj = ((created.get("json") or {}).get("start") or {}) if isinstance(created.get("json"), dict) else {}
    record(
        "timezone_consistency",
        start_obj.get("timeZone") == "Asia/Kuwait",
        timeZone=start_obj.get("timeZone"),
        dateTime=start_obj.get("dateTime"),
    )

    if event_id:
        updated = mcal.update_teams_event(
            token=token,
            mailbox_upn=EVIDENCE_UPN,
            event_id=event_id,
            summary=subject + " RESCHEDULED",
            start=start + timedelta(hours=1),
            end=end + timedelta(hours=1),
            timezone_name="Asia/Kuwait",
            attendees=[EVIDENCE_UPN],
            meet_link=join,
            online_meeting_id=om_id or None,
        )
        same = str(updated.get("event_id") or "") == event_id
        record(
            "reschedule_same_event_no_duplicate",
            bool(updated.get("ok") and same),
            same_event_id=same,
            error=updated.get("error"),
        )
        cancelled = mcal.cancel_teams_event(
            token=token,
            mailbox_upn=EVIDENCE_UPN,
            event_id=event_id,
            online_meeting_id=om_id or None,
        )
        record("cancel", bool(cancelled.get("ok")), status=cancelled.get("status"))
    else:
        record("reschedule_same_event_no_duplicate", False, blocked_reason="no_event_id")
        record("cancel", False, blocked_reason="no_event_id")

    # Outside AAP: deny probe organizer GUID must fail Online Meetings
    denied_oid = os.environ.get("WATHEFNI_M365_DENIED_OBJECT_ID", "08cd915e-3b63-43be-a35a-a35adfde96fc").strip()
    denied_om = mcal.create_online_meeting(
        token=token,
        mailbox_upn=DENIED_UPN,
        summary=f"DENY OM {stamp}",
        start=start,
        end=end,
        timezone_name="UTC",
        organizer_object_id=denied_oid,
    )
    record(
        "outside_aap_online_meeting_denied",
        denied_om.get("ok") is False and int(denied_om.get("status") or 0) in {403, 404, 401},
        status=denied_om.get("status"),
        error=denied_om.get("error"),
        detail=str(denied_om.get("detail") or "")[:180],
    )

    # Calendar AU deny still intact
    denied_cal = mcal._graph(
        "POST",
        f"/users/{urllib.parse.quote(DENIED_UPN)}/events",
        token,
        {
            "subject": f"DENY CAL {stamp}",
            "start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"},
            "end": {"dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"},
        },
    )
    record(
        "outside_au_calendar_still_denied",
        denied_cal.get("ok") is False and int(denied_cal.get("status") or 0) in {403, 404},
        status=denied_cal.get("status"),
    )

    # Assistant path: schedule executor imports microsoft calendar helper
    try:
        import action_registry as ar
        import inspect

        fn = ar._schedule_interview_executor
        src = inspect.getsource(fn)
        record(
            "assistant_schedule_executor_wired",
            "microsoft_teams" in src and ("interview_service" in src or "schedule_interview" in src),
        )
    except Exception as exc:
        record("assistant_schedule_executor_wired", False, error=str(exc)[:200])

    passed = sum(1 for p in results["proofs"].values() if p.get("ok"))
    failed = sum(1 for p in results["proofs"].values() if not p.get("ok"))
    results["summary"] = {"passed": passed, "failed": failed, "verdict": "PASS" if failed == 0 else "FAIL"}
    (evid / "results.json").write_text(json.dumps(results, indent=2, default=str))
    print(json.dumps(results["summary"]))
    print("EVID", evid)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
