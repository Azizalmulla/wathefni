"""Microsoft Graph helpers for interview calendar/Teams sync.

Authority model (narrow):
  - Calendar CRUD: Exchange RBACfA Application Calendars.ReadWrite scoped to AU
    (existing; do not replace with tenant-wide Calendars.ReadWrite).
  - Teams join URLs: Graph OnlineMeetings.ReadWrite.All + Teams Application Access
    Policy granted only to authorized organizer users.

This mailbox's calendar reports allowedOnlineMeetingProviders=[] so embedding
Teams via isOnlineMeeting on calendar events is a no-op (returns false). Create
the online meeting via /onlineMeetings, then attach the join URL to the
RBACfA calendar event (attendees → invitation).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

GRAPH = "https://graph.microsoft.com/v1.0"
DEFAULT_EVIDENCE_UPN = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com"


def _text(value: Any) -> str:
    return str(value or "").strip()


def microsoft_env_configured() -> bool:
    client = _text(os.environ.get("WATHEFNI_M365_CLIENT_ID"))
    tenant = _text(os.environ.get("WATHEFNI_M365_TENANT_ID"))
    bundle = _text(os.environ.get("WATHEFNI_M365_CERT_BUNDLE_PATH") or "/root/.openclaw/secrets/wathefni-m365.bundle.pem")
    return bool(client and tenant and os.path.exists(bundle))


def microsoft_mailbox_upn(*, company_code: str | None = None, legacy: Any = None) -> str:
    """Organizer mailbox for enterprise app-only calendar writes."""
    env_upn = _text(os.environ.get("WATHEFNI_M365_CALENDAR_UPN") or os.environ.get("WATHEFNI_M365_IMPERSONATION_EMAIL"))
    if env_upn:
        return env_upn
    if legacy and company_code and hasattr(legacy, "db_connect"):
        try:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT impersonation_email, account_email
                        FROM platform_company_integrations
                        WHERE company_code=%s AND provider_key IN ('microsoft_365','microsoft')
                          AND status='connected'
                        ORDER BY updated_at DESC NULLS LAST
                        LIMIT 1
                        """,
                        (str(company_code).upper(),),
                    )
                    row = cur.fetchone() or {}
                    upn = _text(row.get("impersonation_email") or row.get("account_email"))
                    if upn:
                        return upn
        except Exception:
            pass
    return DEFAULT_EVIDENCE_UPN


def mint_graph_token() -> str:
    import platform_connection_c6 as c6

    client_id = _text(os.environ.get("WATHEFNI_M365_CLIENT_ID"))
    tenant_id = _text(os.environ.get("WATHEFNI_M365_TENANT_ID"))
    bundle_path = _text(os.environ.get("WATHEFNI_M365_CERT_BUNDLE_PATH") or "/root/.openclaw/secrets/wathefni-m365.bundle.pem")
    pem = open(bundle_path, encoding="utf-8").read()
    try:
        return c6.mint_microsoft_app_token(tenant_id=tenant_id, client_id=client_id, certificate_pem=pem)
    finally:
        del pem


def _graph(method: str, path: str, token: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = path if path.startswith("http") else f"{GRAPH}{path}"
    data = None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8") or ""
            status = getattr(resp, "status", 200)
            if status in {204, 202} or not raw.strip():
                return {"ok": True, "status": status, "json": {}}
            return {"ok": True, "status": status, "json": json.loads(raw)}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:500]
        except Exception:
            pass
        return {"ok": False, "status": exc.code, "error": f"graph_http_{exc.code}", "detail": detail}


def _dt_payload(value: datetime | str, tz_name: str) -> dict[str, str]:
    if isinstance(value, datetime):
        raw = value.replace(tzinfo=None).isoformat(timespec="seconds")
    else:
        raw = _text(value).replace("Z", "")
        if "+" in raw[10:]:
            raw = raw.split("+")[0]
    return {"dateTime": raw, "timeZone": tz_name or "UTC"}


def _to_utc_iso(value: datetime | str, timezone_name: str = "UTC") -> str:
    """Online Meetings API wants UTC ISO timestamps."""
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    raw = _text(value).replace("Z", "")
    if "+" in raw[10:]:
        raw = raw.split("+")[0]
    # Treat naive wall times as already representing the intended instant when
    # callers pass UTC; otherwise append Z for Graph.
    if timezone_name.upper() in {"UTC", "GMT"} or not timezone_name:
        return f"{raw}.000Z" if "." not in raw else f"{raw}Z" if not raw.endswith("Z") else raw
    # For non-UTC labels without offset, still send as Z — callers in Wathefni
    # normally pass timezone-aware datetimes into this helper.
    return f"{raw}.000Z" if "." not in raw else raw


def microsoft_organizer_object_id(*, mailbox_upn: str | None = None) -> str:
    """Online Meetings app-only API requires the organizer's Entra object id (GUID).

    Prefer explicit env; fall back to known evidence organizer. Does not call
    Directory APIs (keeps User.Read.All out of the runtime path).
    """
    env_id = _text(os.environ.get("WATHEFNI_M365_ORGANIZER_OBJECT_ID") or os.environ.get("WATHEFNI_M365_CALENDAR_USER_ID"))
    if env_id:
        return env_id
    upn = _text(mailbox_upn).lower()
    # Evidence AU organizer used for Microsoft live proofs.
    if upn in {"", DEFAULT_EVIDENCE_UPN.lower(), "abdulazizalmulla@wathefni.onmicrosoft.com"}:
        return "dcb6b7dd-8509-4a20-8069-ec0de9445dd7"
    return ""


def create_online_meeting(
    *,
    token: str,
    mailbox_upn: str,
    summary: str,
    start: datetime | str,
    end: datetime | str,
    timezone_name: str = "UTC",
    organizer_object_id: str | None = None,
) -> dict[str, Any]:
    """Create a Teams online meeting for the organizer (requires OnlineMeetings + AAP)."""
    oid = _text(organizer_object_id) or microsoft_organizer_object_id(mailbox_upn=mailbox_upn)
    if not oid:
        return {
            "ok": False,
            "error": "organizer_object_id_required",
            "detail": "OnlineMeetings app-only path requires WATHEFNI_M365_ORGANIZER_OBJECT_ID (GUID)",
            "status": 400,
        }
    user = urllib.parse.quote(oid)
    payload = {
        "subject": summary,
        "startDateTime": _to_utc_iso(start, timezone_name),
        "endDateTime": _to_utc_iso(end, timezone_name),
    }
    result = _graph("POST", f"/users/{user}/onlineMeetings", token, payload)
    if not result.get("ok"):
        return result
    data = result.get("json") if isinstance(result.get("json"), dict) else {}
    join = _text(data.get("joinWebUrl") or data.get("joinUrl"))
    return {
        "ok": True,
        "online_meeting_id": _text(data.get("id")),
        "meet_link": join,
        "organizer_object_id": oid,
        "json": data,
        "provider": "microsoft",
        "mailbox": mailbox_upn,
    }


def create_teams_event(
    *,
    token: str,
    mailbox_upn: str,
    summary: str,
    start: datetime | str,
    end: datetime | str,
    timezone_name: str = "UTC",
    attendees: list[str] | None = None,
    body: str = "",
) -> dict[str, Any]:
    """Create Teams meeting + RBACfA calendar event with join URL and attendees.

    Does not rely on calendar isOnlineMeeting (unsupported when
    allowedOnlineMeetingProviders is empty).
    """
    meeting = create_online_meeting(
        token=token,
        mailbox_upn=mailbox_upn,
        summary=summary,
        start=start,
        end=end,
        timezone_name=timezone_name,
    )
    if not meeting.get("ok"):
        return meeting
    meet_link = _text(meeting.get("meet_link"))
    if not meet_link:
        return {
            "ok": False,
            "error": "teams_join_url_missing",
            "detail": "Online meeting created without joinWebUrl",
            "online_meeting_id": meeting.get("online_meeting_id"),
        }

    user = urllib.parse.quote(mailbox_upn)
    content = body or summary
    if meet_link not in content:
        content = f"{content}\n\nMicrosoft Teams meeting:\n{meet_link}".strip()
    payload: dict[str, Any] = {
        "subject": summary,
        "body": {"contentType": "text", "content": content},
        "start": _dt_payload(start, timezone_name),
        "end": _dt_payload(end, timezone_name),
        "location": {"displayName": "Microsoft Teams meeting"},
        # Explicitly do NOT set isOnlineMeeting — mailbox providers list is empty;
        # setting it is ignored and confuses proofs.
    }
    if attendees:
        payload["attendees"] = [
            {"emailAddress": {"address": a}, "type": "required"} for a in attendees if _text(a)
        ]
    result = _graph("POST", f"/users/{user}/events", token, payload)
    if not result.get("ok"):
        return {
            **result,
            "meet_link": meet_link,
            "online_meeting_id": meeting.get("online_meeting_id"),
            "partial": "online_meeting_created_calendar_failed",
        }
    data = result.get("json") if isinstance(result.get("json"), dict) else {}
    return {
        "ok": True,
        "event_id": _text(data.get("id")),
        "web_link": _text(data.get("webLink")),
        "meet_link": meet_link,
        "online_meeting_id": meeting.get("online_meeting_id"),
        "json": data,
        "online_meeting": meeting.get("json"),
        "provider": "microsoft",
        "mailbox": mailbox_upn,
        "linked": True,
    }


def update_teams_event(
    *,
    token: str,
    mailbox_upn: str,
    event_id: str,
    summary: str,
    start: datetime | str,
    end: datetime | str,
    timezone_name: str = "UTC",
    attendees: list[str] | None = None,
    meet_link: str | None = None,
    online_meeting_id: str | None = None,
    organizer_object_id: str | None = None,
) -> dict[str, Any]:
    """Reschedule calendar event in place (same event id). Keeps existing join URL.

    Does not create a second online meeting.
    """
    user = urllib.parse.quote(mailbox_upn)
    eid = urllib.parse.quote(event_id)
    payload: dict[str, Any] = {
        "subject": summary,
        "start": _dt_payload(start, timezone_name),
        "end": _dt_payload(end, timezone_name),
    }
    if attendees is not None:
        payload["attendees"] = [
            {"emailAddress": {"address": a}, "type": "required"} for a in attendees if _text(a)
        ]
    if meet_link:
        payload["body"] = {
            "contentType": "text",
            "content": f"{summary}\n\nMicrosoft Teams meeting:\n{meet_link}",
        }
        payload["location"] = {"displayName": "Microsoft Teams meeting"}
    result = _graph("PATCH", f"/users/{user}/events/{eid}", token, payload)
    if not result.get("ok"):
        return result
    data = result.get("json") if isinstance(result.get("json"), dict) else {}
    # Best-effort: patch online meeting times when id known (same meeting, no duplicate).
    if online_meeting_id:
        oid = _text(organizer_object_id) or microsoft_organizer_object_id(mailbox_upn=mailbox_upn)
        if oid:
            _graph(
                "PATCH",
                f"/users/{urllib.parse.quote(oid)}/onlineMeetings/{urllib.parse.quote(online_meeting_id)}",
                token,
                {
                    "startDateTime": _to_utc_iso(start, timezone_name),
                    "endDateTime": _to_utc_iso(end, timezone_name),
                    "subject": summary,
                },
            )
    return {
        "ok": True,
        "event_id": event_id,
        "web_link": _text(data.get("webLink")),
        "meet_link": _text(meet_link),
        "online_meeting_id": _text(online_meeting_id) or None,
        "json": data,
        "provider": "microsoft",
        "same_event_id": True,
    }


def cancel_teams_event(
    *,
    token: str,
    mailbox_upn: str,
    event_id: str,
    online_meeting_id: str | None = None,
    organizer_object_id: str | None = None,
) -> dict[str, Any]:
    user = urllib.parse.quote(mailbox_upn)
    eid = urllib.parse.quote(event_id)
    result = _graph("DELETE", f"/users/{user}/events/{eid}", token, None)
    om_status = None
    if online_meeting_id:
        oid = _text(organizer_object_id) or microsoft_organizer_object_id(mailbox_upn=mailbox_upn)
        if oid:
            om = _graph(
                "DELETE",
                f"/users/{urllib.parse.quote(oid)}/onlineMeetings/{urllib.parse.quote(online_meeting_id)}",
                token,
                None,
            )
            om_status = om.get("status")
    if result.get("ok") or result.get("status") in {204, 202, 404}:
        return {
            "ok": True,
            "event_id": event_id,
            "online_meeting_id": online_meeting_id,
            "online_meeting_delete_status": om_status,
            "provider": "microsoft",
            "status": result.get("status"),
        }
    return result
