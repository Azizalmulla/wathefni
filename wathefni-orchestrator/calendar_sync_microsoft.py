"""Microsoft 365 / Outlook Calendar + Teams sync adapter (C5).

Uses Microsoft Graph. Credentials come from platform_company_integrations —
never from Calendar domain code.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping


GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sync_dry_run() -> bool:
    return _text(os.environ.get("CALENDAR_SYNC_DRY_RUN")).lower() in {"1", "true", "yes", "on"}


def _graph_request(
    *,
    method: str,
    path: str,
    access_token: str | None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if _sync_dry_run():
        eid = _text((body or {}).get("id")) or f"dry_run_m365_{abs(hash(path + method)) % 10**12}"
        return {
            "ok": True,
            "dry_run": True,
            "json": {
                "id": eid if method != "POST" else f"dry_run_m365_{abs(hash(json.dumps(body or {}, sort_keys=True))) % 10**12}",
                "webLink": "https://outlook.office.com/dry-run",
                "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/dry-run"} if (body or {}).get("isOnlineMeeting") else None,
            },
        }
    if not access_token:
        return {"ok": False, "error": "missing_access_token"}
    url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
    data = None
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read().decode("utf-8") or ""
            if status in {204, 202} or not raw.strip():
                return {"ok": True, "json": {}, "status": status}
            parsed = json.loads(raw) if raw.strip() else {}
            return {"ok": True, "json": parsed, "status": status}
    except urllib.error.HTTPError as exc:
        if exc.code in {204, 202}:
            return {"ok": True, "json": {}, "status": exc.code}
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8")[:300]
        except Exception:
            pass
        return {"ok": False, "error": f"graph_http_{exc.code}", "detail": err_body}
    except Exception as exc:
        return {"ok": False, "error": f"graph_error:{type(exc).__name__}:{str(exc)[:120]}"}


class MicrosoftCalendarSyncAdapter:
    provider_key = "microsoft"

    def healthcheck(self, connection: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "ok": bool(connection.get("_access_token") or connection.get("has_credentials") or _sync_dry_run()),
            "provider": "microsoft",
            "account_email": _text(connection.get("account_email")) or None,
            "dry_run": _sync_dry_run(),
        }

    def _calendar_path(self, connection: Mapping[str, Any], provider_event_id: str | None = None) -> str:
        cal = _text(connection.get("external_calendar_id")) or "calendar"
        # App-only enterprise: act as calendar identity via /users/{upn}
        mode = _text(connection.get("_connection_mode") or (connection.get("_platform_integration") or {}).get("connection_mode"))
        identity = _text(
            connection.get("_impersonation_email")
            or (connection.get("_platform_integration") or {}).get("impersonation_email")
            or connection.get("account_email")
        )
        if mode == "enterprise_app" and identity:
            user = urllib.parse.quote(identity)
            if cal in {"primary", "calendar", "me"}:
                base = f"/users/{user}/events"
            else:
                base = f"/users/{user}/calendars/{urllib.parse.quote(cal)}/events"
        elif cal in {"primary", "calendar", "me"}:
            base = "/me/events"
        else:
            base = f"/me/calendars/{urllib.parse.quote(cal)}/events"
        if provider_event_id:
            return f"{base}/{urllib.parse.quote(provider_event_id)}"
        return base

    def _event_body(self, external_event: Mapping[str, Any], *, with_teams: bool) -> dict[str, Any]:
        all_day = bool(external_event.get("all_day"))
        start = _text(external_event.get("start"))
        end = _text(external_event.get("end"))
        tz = _text(external_event.get("timezone")) or "Asia/Kuwait"
        body: dict[str, Any] = {
            "subject": _text(external_event.get("summary")) or "Wathefni event",
            "body": {
                "contentType": "text",
                "content": _text(external_event.get("description")) or "",
            },
            "location": {"displayName": _text(external_event.get("location")) or ""},
            "isAllDay": all_day,
            "start": {"dateTime": start.replace("Z", "") if start.endswith("Z") else start, "timeZone": tz},
            "end": {"dateTime": end.replace("Z", "") if end.endswith("Z") else end, "timeZone": tz},
        }
        if with_teams:
            body["isOnlineMeeting"] = True
            body["onlineMeetingProvider"] = "teamsForBusiness"
        return body

    def upsert_event(
        self,
        *,
        connection: Mapping[str, Any],
        binding: Mapping[str, Any] | None,
        external_event: Mapping[str, Any],
        legacy: Any = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        _ = legacy
        token = access_token or connection.get("_access_token")
        with_teams = bool(external_event.get("with_meet") or connection.get("with_meet_default"))
        provider_event_id = _text((binding or {}).get("provider_event_id"))
        body = self._event_body(external_event, with_teams=with_teams)

        if provider_event_id:
            # Preserve id for dry-run stability
            body["id"] = provider_event_id
            result = _graph_request(
                method="PATCH",
                path=self._calendar_path(connection, provider_event_id),
                access_token=token,
                body=body,
            )
            if not result.get("ok"):
                return {"ok": False, "error": _text(result.get("error")) or "microsoft_update_failed"}
            data = result.get("json") if isinstance(result.get("json"), dict) else {}
            return {
                "ok": True,
                "provider_event_id": provider_event_id,
                "external_html_link": _text(data.get("webLink")) or (binding or {}).get("external_html_link"),
                "meeting_url": _text(((data.get("onlineMeeting") or {}) if isinstance(data.get("onlineMeeting"), dict) else {}).get("joinUrl")),
                "operation": "update",
                "dry_run": bool(result.get("dry_run")),
            }

        result = _graph_request(
            method="POST",
            path=self._calendar_path(connection),
            access_token=token,
            body=body,
        )
        if not result.get("ok"):
            return {"ok": False, "error": _text(result.get("error")) or "microsoft_create_failed"}
        data = result.get("json") if isinstance(result.get("json"), dict) else {}
        new_id = _text(data.get("id"))
        if not new_id:
            return {"ok": False, "error": "microsoft_missing_event_id"}
        meet = data.get("onlineMeeting") if isinstance(data.get("onlineMeeting"), dict) else {}
        return {
            "ok": True,
            "provider_event_id": new_id,
            "external_html_link": _text(data.get("webLink")) or None,
            "meeting_url": _text(meet.get("joinUrl")) or None,
            "operation": "create",
            "dry_run": bool(result.get("dry_run")),
        }

    def cancel_event(
        self,
        *,
        connection: Mapping[str, Any],
        binding: Mapping[str, Any],
        legacy: Any = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        _ = legacy
        provider_event_id = _text(binding.get("provider_event_id"))
        if not provider_event_id:
            return {"ok": True, "skipped": True, "reason": "no_provider_event"}
        token = access_token or connection.get("_access_token")
        result = _graph_request(
            method="DELETE",
            path=self._calendar_path(connection, provider_event_id),
            access_token=token,
            body=None,
        )
        # Graph delete returns empty 204 — treat missing json as ok when dry_run or status ok
        if result.get("ok") or result.get("dry_run") or _sync_dry_run():
            if _sync_dry_run() and not result.get("ok"):
                return {"ok": True, "provider_event_id": provider_event_id, "operation": "cancel", "dry_run": True}
            return {
                "ok": True,
                "provider_event_id": provider_event_id,
                "operation": "cancel",
                "dry_run": bool(result.get("dry_run")),
            }
        # 204 No Content often surfaces as ok with empty body
        if _text(result.get("error")) in {"graph_http_204"}:
            return {"ok": True, "provider_event_id": provider_event_id, "operation": "cancel"}
        return {"ok": False, "error": _text(result.get("error")) or "microsoft_delete_failed"}
