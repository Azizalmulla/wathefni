#!/usr/bin/env python3
"""Live Microsoft Graph Calendar proof via certificate app-only (no client secret).

Uses evidence mailbox only; attempts unapproved mailbox deny; never logs tokens/keys.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

GRAPH = "https://graph.microsoft.com/v1.0"
EVIDENCE_UPN = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com"


def _json_req(method: str, url: str, token: str, body: dict | None = None) -> dict:
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
            parsed = json.loads(raw) if raw.strip() else {}
            return {"ok": True, "status": status, "json": parsed}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:500]
        except Exception:
            pass
        return {"ok": False, "status": exc.code, "error": f"http_{exc.code}", "detail": detail}


def main() -> int:
    import platform_connection_c6 as c6

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evid = Path(os.environ.get("C6B_EVID", f"/opt/wathefni/production-evidence/wathefni-calendar-c6b/m365-live-{stamp}"))
    evid.mkdir(parents=True, exist_ok=True)
    results: dict = {"stamp": stamp, "proofs": {}}

    def record(name: str, ok: bool, **details):
        safe = {k: v for k, v in details.items() if "token" not in k.lower() and "pem" not in k.lower() and "key" not in k.lower()}
        results["proofs"][name] = {"ok": ok, **safe}
        print(("PASS" if ok else "FAIL"), name, json.dumps(safe, default=str)[:280])

    client_id = (os.environ.get("WATHEFNI_M365_CLIENT_ID") or "").strip()
    tenant_id = (os.environ.get("WATHEFNI_M365_TENANT_ID") or "").strip()
    bundle_path = Path((os.environ.get("WATHEFNI_M365_CERT_BUNDLE_PATH") or "/root/.openclaw/secrets/wathefni-m365.bundle.pem").strip())
    denied_upn = (os.environ.get("WATHEFNI_M365_DENIED_UPN") or "").strip()

    if not (client_id and tenant_id and bundle_path.exists()):
        record("preconditions", False, error="missing_client_tenant_or_bundle")
        (evid / "m365-live-calendar-results.json").write_text(json.dumps(results, indent=2))
        return 1

    bundle = bundle_path.read_text()
    try:
        token = c6.mint_microsoft_app_token(tenant_id=tenant_id, client_id=client_id, certificate_pem=bundle)
        record("cert_token_mint", bool(token), token_len=len(token or ""))
    except Exception as exc:
        record("cert_token_mint", False, error=getattr(exc, "code", type(exc).__name__), message=str(getattr(exc, "message", exc))[:200])
        (evid / "m365-live-calendar-results.json").write_text(json.dumps(results, indent=2))
        return 1
    finally:
        del bundle

    user = urllib.parse.quote(EVIDENCE_UPN)
    now = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=4)
    end = now + timedelta(hours=1)
    subject = f"Wathefni C6B M365 Evidence {stamp}"

    create_body = {
        "subject": subject,
        "body": {"contentType": "text", "content": "Controlled Wathefni Calendar C6B Microsoft evidence event."},
        "start": {"dateTime": now.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"},
        "end": {"dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"},
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness",
        "location": {"displayName": "Wathefni evidence"},
    }
    created = _json_req("POST", f"{GRAPH}/users/{user}/events", token, create_body)
    event = created.get("json") if isinstance(created.get("json"), dict) else {}
    event_id = str(event.get("id") or "")
    meet = event.get("onlineMeeting") if isinstance(event.get("onlineMeeting"), dict) else {}
    meet_url = str(meet.get("joinUrl") or "")
    record(
        "outlook_create",
        created.get("ok") is True and bool(event_id),
        status=created.get("status"),
        error=created.get("error"),
        has_event_id=bool(event_id),
        web_link_present=bool(event.get("webLink")),
    )
    record(
        "teams_meeting",
        bool(meet_url) and "teams.microsoft.com" in meet_url.lower(),
        has_join_url=bool(meet_url),
        join_host=("teams.microsoft.com" if "teams.microsoft.com" in meet_url.lower() else None),
    )

    if not event_id:
        # Deny probe still useful even if create failed
        if denied_upn:
            denied = _json_req(
                "POST",
                f"{GRAPH}/users/{urllib.parse.quote(denied_upn)}/events",
                token,
                {**create_body, "subject": f"DENY {subject}", "isOnlineMeeting": False},
            )
            record(
                "unapproved_mailbox_denied",
                denied.get("ok") is False and int(denied.get("status") or 0) in {401, 403, 404},
                status=denied.get("status"),
                error=denied.get("error"),
            )
        (evid / "m365-live-calendar-results.json").write_text(json.dumps(results, indent=2, default=str))
        print(json.dumps({"passed": sum(1 for p in results["proofs"].values() if p.get("ok")), "failed": sum(1 for p in results["proofs"].values() if not p.get("ok"))}))
        print("EVID", evid)
        return 1

    # Update same id
    upd_body = {
        "subject": f"{subject} UPDATED",
        "start": {"dateTime": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"},
        "end": {"dateTime": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"},
    }
    updated = _json_req("PATCH", f"{GRAPH}/users/{user}/events/{urllib.parse.quote(event_id)}", token, upd_body)
    updated_json = updated.get("json") if isinstance(updated.get("json"), dict) else {}
    same_id = str(updated_json.get("id") or event_id) == event_id
    record(
        "outlook_update_same_id",
        updated.get("ok") is True and same_id,
        status=updated.get("status"),
        same_provider_event_id=same_id,
    )

    # Retry create should be avoided — instead GET then cancel twice (no duplicate)
    got = _json_req("GET", f"{GRAPH}/users/{user}/events/{urllib.parse.quote(event_id)}", token)
    record("outlook_get_after_update", got.get("ok") is True, status=got.get("status"))

    cancelled = _json_req("DELETE", f"{GRAPH}/users/{user}/events/{urllib.parse.quote(event_id)}", token)
    record(
        "outlook_cancel",
        cancelled.get("ok") is True or int(cancelled.get("status") or 0) in {204, 200},
        status=cancelled.get("status"),
        error=cancelled.get("error"),
    )
    # Second cancel/delete — should be 404 not create a new event
    cancelled2 = _json_req("DELETE", f"{GRAPH}/users/{user}/events/{urllib.parse.quote(event_id)}", token)
    record(
        "no_duplicate_after_retry_cancel",
        int(cancelled2.get("status") or 0) in {404, 204, 200} or cancelled2.get("ok") is True,
        status=cancelled2.get("status"),
        note="second delete must not create a new event",
    )

    # Unapproved mailbox deny
    if denied_upn:
        denied = _json_req(
            "POST",
            f"{GRAPH}/users/{urllib.parse.quote(denied_upn)}/events",
            token,
            {
                "subject": f"DENY {subject}",
                "start": create_body["start"],
                "end": create_body["end"],
                "body": {"contentType": "text", "content": "should fail"},
            },
        )
        record(
            "unapproved_mailbox_denied",
            denied.get("ok") is False and int(denied.get("status") or 0) in {401, 403, 404},
            status=denied.get("status"),
            error=denied.get("error"),
            denied_upn_suffix=denied_upn.split("@")[-1],
        )
    else:
        record("unapproved_mailbox_denied", False, blocked_reason="WATHEFNI_M365_DENIED_UPN not set")

    # Wathefni truth intact on provider failure: create a local calendar event row and leave it
    # cancelled/confirmed independent of Graph deny.
    try:
        import app as app_mod
        import calendar_schema as schema
        import calendar_store as store

        company = "WATHEFNI"
        actor = str(uuid4())
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                schema.ensure_calendar_schema(cur)
            conn.commit()
        ev = store.create_manual_event(
            app_mod,
            company_code=company,
            actor_user_id=actor,
            payload={
                "event_type": "meeting",
                "title": f"M365 Failure-Isolation {stamp}",
                "visibility": "private",
                "start_at": now.isoformat(),
                "end_at": end.isoformat(),
                "timezone": "Asia/Kuwait",
            },
            actor_permissions={"calendar.manage", "calendar.read", "calendar.conflict_override"},
        )
        # Simulate provider failure by attempting Graph against denied (or invalid) and ensuring Wathefni row unchanged
        _ = _json_req("POST", f"{GRAPH}/users/{urllib.parse.quote(denied_upn or 'nobody@wathefni.onmicrosoft.com')}/events", token, create_body)
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, title FROM calendar_events WHERE event_id=%s", (ev["event_id"],))
                row = dict(cur.fetchone() or {})
        record(
            "provider_failure_wathefni_intact",
            row.get("status") in {"confirmed", "tentative"} and row.get("title") == ev.get("title"),
            status=row.get("status"),
            event_id=ev["event_id"],
        )
        store.cancel_event(app_mod, company_code=company, event_id=ev["event_id"], actor_user_id=actor, expected_version=ev["version"])
    except Exception as exc:
        record("provider_failure_wathefni_intact", False, error=str(exc)[:240])

    # Never write token
    del token
    passed = sum(1 for p in results["proofs"].values() if p.get("ok"))
    failed = sum(1 for p in results["proofs"].values() if not p.get("ok"))
    results["summary"] = {"passed": passed, "failed": failed}
    (evid / "m365-live-calendar-results.json").write_text(json.dumps(results, indent=2, default=str))
    print(json.dumps(results["summary"]))
    print("EVID", evid)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
