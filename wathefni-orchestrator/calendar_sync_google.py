"""Google Calendar sync adapter (C5) — Wathefni → Google only.

Uses gog CLI with either:
- company refresh token → mint GOG_ACCESS_TOKEN + --account
- legacy_operator mode → platform GOG_ACCOUNT / host keyring

Never called from Calendar domain modules directly.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sync_dry_run() -> bool:
    return _text(os.environ.get("CALENDAR_SYNC_DRY_RUN")).lower() in {"1", "true", "yes", "on"}


class GoogleCalendarSyncAdapter:
    provider_key = "google"

    def healthcheck(self, connection: Mapping[str, Any]) -> dict[str, Any]:
        mode = _text(connection.get("mode"))
        if mode == "legacy_operator":
            account = _text(os.environ.get("GOG_ACCOUNT"))
            try:
                # Prefer openclaw env when available via connection metadata flag.
                if connection.get("_legacy_account"):
                    account = _text(connection.get("_legacy_account")) or account
            except Exception:
                pass
            return {
                "ok": bool(account) or _sync_dry_run(),
                "provider": "google",
                "mode": mode,
                "account_email": account or None,
                "dry_run": _sync_dry_run(),
            }
        email = _text(connection.get("account_email"))
        has_creds = bool(connection.get("has_credentials") or connection.get("_refresh_token"))
        return {
            "ok": bool(email and has_creds) or _sync_dry_run(),
            "provider": "google",
            "mode": mode,
            "account_email": email or None,
            "dry_run": _sync_dry_run(),
        }

    def _run(
        self,
        legacy: Any,
        args: list[str],
        *,
        connection: Mapping[str, Any],
        access_token: str | None = None,
    ) -> dict[str, Any]:
        if _sync_dry_run():
            dry_id = _text(connection.get("_dry_run_event_id")) or f"dry_run_google_{abs(hash(tuple(args)))%10**12}"
            return {
                "ok": True,
                "dry_run": True,
                "json": {
                    "id": dry_id,
                    "htmlLink": "https://calendar.google.com/dry-run",
                },
                "args": args,
            }
        env_extra: dict[str, str] = {}
        if access_token:
            env_extra["GOG_ACCESS_TOKEN"] = access_token
        # Prefer a runner that can inject env; fall back to run_gog.
        if hasattr(legacy, "run_gog_with_env"):
            return legacy.run_gog_with_env(args, timeout=90, extra_env=env_extra)
        if hasattr(legacy, "run_gog"):
            if env_extra:
                # Temporarily inject for this subprocess via a thin wrapper if present.
                prev = {k: os.environ.get(k) for k in env_extra}
                try:
                    os.environ.update(env_extra)
                    return legacy.run_gog(args, timeout=90)
                finally:
                    for k, v in prev.items():
                        if v is None:
                            os.environ.pop(k, None)
                        else:
                            os.environ[k] = v
            return legacy.run_gog(args, timeout=90)
        return {"ok": False, "error": "gog_unavailable"}

    def _account_args(self, connection: Mapping[str, Any]) -> list[str]:
        mode = _text(connection.get("mode"))
        if mode == "legacy_operator":
            account = _text(connection.get("_legacy_account") or os.environ.get("GOG_ACCOUNT"))
        else:
            account = _text(connection.get("account_email"))
        return ["--account", account] if account else []

    def _calendar_id(self, connection: Mapping[str, Any]) -> str:
        return _text(connection.get("external_calendar_id")) or "primary"

    def _extract_event_id(self, result: Mapping[str, Any]) -> str | None:
        data = result.get("json")
        if isinstance(data, dict):
            for key in ("id", "event_id", "eventId"):
                if data.get(key):
                    return _text(data.get(key))
            # nested
            ev = data.get("event") if isinstance(data.get("event"), dict) else None
            if ev and ev.get("id"):
                return _text(ev.get("id"))
        out = _text(result.get("stdout"))
        if out:
            try:
                parsed = json.loads(out)
                if isinstance(parsed, dict) and parsed.get("id"):
                    return _text(parsed.get("id"))
            except Exception:
                pass
        return None

    def _extract_html_link(self, result: Mapping[str, Any]) -> str | None:
        data = result.get("json")
        if isinstance(data, dict):
            link = data.get("htmlLink") or data.get("html_link")
            if link:
                return _text(link)
        return None

    def _rest_request(
        self,
        *,
        method: str,
        path: str,
        access_token: str | None,
        body: dict[str, Any] | None = None,
        dry_event_id: str | None = None,
    ) -> dict[str, Any]:
        import urllib.error
        import urllib.request

        if _sync_dry_run():
            eid = dry_event_id or f"dry_run_google_{abs(hash(path + method)) % 10**12}"
            return {
                "ok": True,
                "dry_run": True,
                "json": {
                    "id": eid if method != "POST" else (dry_event_id or f"dry_run_google_{abs(hash(json.dumps(body or {}, sort_keys=True))) % 10**12}"),
                    "htmlLink": "https://calendar.google.com/dry-run",
                    "hangoutLink": "https://meet.google.com/dry-run" if (body or {}).get("conferenceData") else None,
                },
            }
        if not access_token:
            return {"ok": False, "error": "missing_access_token"}
        url = path if path.startswith("http") else f"https://www.googleapis.com/calendar/v3{path}"
        data = None
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                raw = resp.read().decode("utf-8") or ""
                if method.upper() == "DELETE" or not raw.strip():
                    return {"ok": True, "json": {}}
                return {"ok": True, "json": json.loads(raw)}
        except urllib.error.HTTPError as exc:
            if exc.code in {204, 404} and method.upper() == "DELETE":
                return {"ok": True, "json": {}, "status": exc.code}
            return {"ok": False, "error": f"google_http_{exc.code}"}
        except Exception as exc:
            return {"ok": False, "error": f"google_rest_error:{type(exc).__name__}"}

    def _rest_event_body(self, external_event: Mapping[str, Any], *, with_meet: bool) -> dict[str, Any]:
        all_day = bool(external_event.get("all_day"))
        start = _text(external_event.get("start"))
        end = _text(external_event.get("end"))
        tz = _text(external_event.get("timezone")) or "Asia/Kuwait"
        body: dict[str, Any] = {
            "summary": _text(external_event.get("summary")) or "OctoHR event",
            "description": _text(external_event.get("description")) or "",
            "location": _text(external_event.get("location")) or "",
        }
        if all_day:
            body["start"] = {"date": start[:10]}
            body["end"] = {"date": end[:10]}
        else:
            body["start"] = {"dateTime": start, "timeZone": tz}
            body["end"] = {"dateTime": end, "timeZone": tz}
        if with_meet:
            body["conferenceData"] = {
                "createRequest": {
                    "requestId": f"wathefni-{_text(external_event.get('event_id'))[:32] or abs(hash(start)) % 10**10}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }
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
        legacy = legacy or connection.get("_legacy")
        token = access_token or connection.get("_access_token")
        mode = _text(connection.get("_connection_mode") or (connection.get("_platform_integration") or {}).get("connection_mode") or connection.get("mode"))
        # Prefer Google Calendar REST for DWD / OAuth company tokens (no gog dependency).
        if token or (mode in {"enterprise_dwd", "oauth_delegated", "company"} and _sync_dry_run()):
            cal = self._calendar_id(connection)
            provider_event_id = _text((binding or {}).get("provider_event_id"))
            with_meet = bool(external_event.get("with_meet") or connection.get("with_meet_default"))
            body = self._rest_event_body(external_event, with_meet=with_meet)
            if provider_event_id:
                result = self._rest_request(
                    method="PATCH",
                    path=f"/calendars/{cal}/events/{provider_event_id}",
                    access_token=token,
                    body=body,
                    dry_event_id=provider_event_id,
                )
                if result.get("ok"):
                    data = result.get("json") if isinstance(result.get("json"), dict) else {}
                    return {
                        "ok": True,
                        "provider_event_id": provider_event_id,
                        "external_html_link": _text(data.get("htmlLink")) or (binding or {}).get("external_html_link"),
                        "meeting_url": _text(data.get("hangoutLink")) or None,
                        "operation": "update",
                        "dry_run": bool(result.get("dry_run")),
                    }
                # fall through to gog only if REST failed and not dry-run enterprise
            else:
                q = "?conferenceDataVersion=1" if with_meet else ""
                dry_id = f"dry_run_google_{_text(external_event.get('event_id'))[:48]}"
                result = self._rest_request(
                    method="POST",
                    path=f"/calendars/{cal}/events{q}",
                    access_token=token,
                    body=body,
                    dry_event_id=dry_id,
                )
                if result.get("ok"):
                    data = result.get("json") if isinstance(result.get("json"), dict) else {}
                    new_id = _text(data.get("id")) or (dry_id if result.get("dry_run") else "")
                    if new_id:
                        return {
                            "ok": True,
                            "provider_event_id": new_id,
                            "external_html_link": _text(data.get("htmlLink")) or None,
                            "meeting_url": _text(data.get("hangoutLink")) or None,
                            "operation": "create",
                            "dry_run": bool(result.get("dry_run")),
                        }

        # Legacy gog path (operator / transitional)
        cal = self._calendar_id(connection)
        provider_event_id = _text((binding or {}).get("provider_event_id"))
        summary = _text(external_event.get("summary")) or "OctoHR event"
        start = _text(external_event.get("start"))
        end = _text(external_event.get("end"))
        all_day = bool(external_event.get("all_day"))
        with_meet = bool(external_event.get("with_meet"))
        description = _text(external_event.get("description"))
        location = _text(external_event.get("location"))
        timezone = _text(external_event.get("timezone")) or "Asia/Kuwait"

        account_args = self._account_args(connection)
        if provider_event_id:
            args = [
                "calendar",
                "update",
                cal,
                provider_event_id,
                "--summary",
                summary,
                "--from",
                start,
                "--to",
                end,
                "--send-updates",
                "none",
                "--no-input",
            ]
            if description:
                args.extend(["--description", description])
            if location:
                args.extend(["--location", location])
            if all_day:
                args.append("--all-day")
            args.extend(account_args)
            # Dry-run needs stable id
            conn_mut = dict(connection)
            conn_mut["_dry_run_event_id"] = provider_event_id
            result = self._run(legacy, args, connection=conn_mut, access_token=access_token)
            if result.get("ok"):
                return {
                    "ok": True,
                    "provider_event_id": provider_event_id,
                    "external_html_link": self._extract_html_link(result) or (binding or {}).get("external_html_link"),
                    "operation": "update",
                    "dry_run": bool(result.get("dry_run")),
                    "raw": {k: v for k, v in result.items() if k != "json"} | {"json_keys": list((result.get("json") or {}).keys()) if isinstance(result.get("json"), dict) else []},
                }
            # Fallback events update
            args2 = [
                "calendar",
                "events",
                "update",
                cal,
                provider_event_id,
                "--summary",
                summary,
                "--from",
                start,
                "--to",
                end,
                "--send-updates",
                "none",
                "--no-input",
                *account_args,
            ]
            result2 = self._run(legacy, args2, connection=conn_mut, access_token=access_token)
            if result2.get("ok"):
                return {
                    "ok": True,
                    "provider_event_id": provider_event_id,
                    "external_html_link": self._extract_html_link(result2) or (binding or {}).get("external_html_link"),
                    "operation": "update",
                    "dry_run": bool(result2.get("dry_run")),
                }
            return {"ok": False, "error": _text(result2.get("error") or result.get("stderr") or result.get("error") or "google_update_failed")}

        args = [
            "calendar",
            "create",
            cal,
            "--summary",
            summary,
            "--from",
            start,
            "--to",
            end,
            "--send-updates",
            "none",
            "--no-input",
        ]
        if description:
            args.extend(["--description", description])
        if location:
            args.extend(["--location", location])
        if with_meet:
            args.append("--with-meet")
        if all_day:
            args.append("--all-day")
        # timezone hint for timed events when gog supports it
        if timezone and not all_day:
            args.extend(["--timezone", timezone])
        args.extend(account_args)
        # Stable dry-run id from Wathefni event id (never invent colliding provider ids).
        conn_create = dict(connection)
        conn_create["_dry_run_event_id"] = f"dry_run_google_{_text(external_event.get('event_id'))[:48]}"
        result = self._run(legacy, args, connection=conn_create, access_token=access_token)
        if not result.get("ok"):
            # Retry without --timezone if unsupported
            if "--timezone" in args:
                args = [a for a in args if a != "--timezone" and a != timezone]
                result = self._run(legacy, args, connection=conn_create, access_token=access_token)
        if not result.get("ok"):
            return {"ok": False, "error": _text(result.get("error") or result.get("stderr") or "google_create_failed")}
        new_id = self._extract_event_id(result)
        if not new_id and result.get("dry_run"):
            new_id = conn_create["_dry_run_event_id"]
        if not new_id:
            return {"ok": False, "error": "google_missing_event_id"}
        return {
            "ok": True,
            "provider_event_id": new_id,
            "external_html_link": self._extract_html_link(result),
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
        legacy = legacy or connection.get("_legacy")
        provider_event_id = _text(binding.get("provider_event_id"))
        if not provider_event_id:
            return {"ok": True, "skipped": True, "reason": "no_provider_event"}
        token = access_token or connection.get("_access_token")
        mode = _text(connection.get("_connection_mode") or (connection.get("_platform_integration") or {}).get("connection_mode") or connection.get("mode"))
        if token or (mode in {"enterprise_dwd", "oauth_delegated", "company"} and _sync_dry_run()):
            cal = self._calendar_id(connection)
            result = self._rest_request(
                method="DELETE",
                path=f"/calendars/{cal}/events/{provider_event_id}",
                access_token=token,
                dry_event_id=provider_event_id,
            )
            if result.get("ok"):
                return {"ok": True, "provider_event_id": provider_event_id, "operation": "cancel", "dry_run": bool(result.get("dry_run"))}
        cal = self._calendar_id(connection)
        account_args = self._account_args(connection)
        args = ["calendar", "delete", cal, provider_event_id, "--force", "--no-input", *account_args]
        conn_mut = dict(connection)
        conn_mut["_dry_run_event_id"] = provider_event_id
        result = self._run(legacy, args, connection=conn_mut, access_token=access_token)
        if result.get("ok"):
            return {"ok": True, "provider_event_id": provider_event_id, "operation": "cancel", "dry_run": bool(result.get("dry_run"))}
        return {"ok": False, "error": _text(result.get("error") or result.get("stderr") or "google_delete_failed")}
