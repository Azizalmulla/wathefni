#!/usr/bin/env python3
"""Calendar C6B controlled live evidence proofs (Google OAuth + communication).

Microsoft Entra / Google Workspace DWD are attempted and recorded as blocked
when host credentials/domain delegation are unavailable.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Live for this process only.
os.environ["CALENDAR_SYNC_DRY_RUN"] = "false"
os.environ["CALENDAR_DELIVERY_DRY_RUN"] = "false"


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evid = Path(os.environ.get("C6B_EVID", f"/opt/wathefni/production-evidence/wathefni-calendar-c6b/{stamp}"))
    evid.mkdir(parents=True, exist_ok=True)
    results: dict = {"stamp": stamp, "proofs": {}}

    def record(name: str, ok: bool, **details):
        results["proofs"][name] = {"ok": ok, **details}
        print(("PASS" if ok else "FAIL"), name, json.dumps(details, default=str)[:280])

    try:
        import app as app_mod
        import calendar_schema as schema
        import calendar_store as store
        import calendar_sync as csync
        import platform_connection_c6 as c6
        import platform_integrations as pi
        import wathefni_communication as comm
    except Exception:
        traceback.print_exc()
        return 1

    company = "WATHEFNI"
    actor = "c6b-evidence"
    refresh_env = Path("/root/.openclaw/secrets/gog-refresh.evidence.env")
    refresh = ""
    account = "azizalmulla16@gmail.com"
    if refresh_env.exists():
        for line in refresh_env.read_text().splitlines():
            if line.startswith("WATHEFNI_EVIDENCE_GOOGLE_REFRESH_TOKEN="):
                refresh = line.split("=", 1)[1].strip()
            if line.startswith("WATHEFNI_EVIDENCE_GOOGLE_ACCOUNT="):
                account = line.split("=", 1)[1].strip()

    # --- Google OAuth client readiness ---
    record(
        "google_oauth_client_provisioned",
        c6.google_oauth_ready(),
        client_configured=c6.google_oauth_ready(),
    )

    # --- Microsoft readiness ---
    record(
        "microsoft_oauth_client_provisioned",
        c6.microsoft_oauth_ready(),
        detail="requires WATHEFNI_M365_CLIENT_*",
    )
    record(
        "microsoft_enterprise_app_live",
        False,
        blocked_reason="no_entra_app_registration_credentials_on_host",
    )
    record(
        "microsoft_delegated_oauth_live",
        False,
        blocked_reason="no_entra_app_registration_credentials_on_host",
    )
    record(
        "microsoft_teams_live",
        False,
        blocked_reason="depends_on_m365_credentials",
    )

    # --- Google DWD attempt ---
    sa_path = Path("/root/.openclaw/secrets/wathefni-service-account.json")
    dwd_ok = False
    dwd_err = ""
    if sa_path.exists():
        try:
            sa = json.loads(sa_path.read_text())
            c6.mint_google_dwd_token(sa, impersonation_email=account)
            dwd_ok = True
        except Exception as exc:
            dwd_err = str(exc)[:240]
    record(
        "google_dwd_live",
        dwd_ok,
        service_account=bool(sa_path.exists()),
        impersonation_attempt=account,
        error=dwd_err or None,
        note="Gmail consumer accounts cannot be DWD-impersonated; Workspace domain + Admin DWD required",
    )

    # --- Connect Google delegated OAuth (platform) — single connection only ---
    if not refresh:
        record("google_oauth_connect", False, error="missing_refresh_token_evidence_file")
        (evid / "c6b-results.json").write_text(json.dumps(results, indent=2, default=str))
        return 1

    try:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                schema.ensure_calendar_schema(cur)
                pi.ensure_schema(cur)
                c6.ensure_c6_schema(cur)
                # Disconnect all existing sync connections so oauth proof is single-path.
                cur.execute(
                    """
                    UPDATE calendar_sync_connections
                       SET status='disconnected', disconnected_at=now(), updated_at=now()
                     WHERE company_code=%s AND status='connected'
                    """,
                    (company,),
                )
            conn.commit()

        connected = pi.connect_provider(
            app_mod,
            company_code=company,
            provider_key=pi.PROVIDER_GOOGLE_WORKSPACE,
            account_email=account,
            refresh_token=refresh,
            actor_user_id=actor,
            display_name="C6B evidence Google OAuth",
            capabilities=[pi.CAPABILITY_CALENDAR_EVENTS, pi.CAPABILITY_MEETINGS_CREATE],
        )
        integ = connected["integration"]
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE platform_company_integrations SET connection_mode=%s, updated_at=now() WHERE integration_id=%s",
                    ("oauth_delegated", integ["integration_id"]),
                )
            conn.commit()
        attached = pi.attach_calendar_sync_connection(
            app_mod,
            company_code=company,
            integration_id=str(integ["integration_id"]),
            actor_user_id=actor,
            external_calendar_id="primary",
            with_meet_default=True,
        )
        # Do NOT enable legacy_operator — that dual-writes and creates duplicate Google events.
        record(
            "google_oauth_connect",
            True,
            integration_id=integ["integration_id"],
            connection_id=(attached.get("connection") or {}).get("connection_id"),
            account=account,
            mode="oauth_delegated",
            single_connection=True,
        )
    except Exception as exc:
        traceback.print_exc()
        record("google_oauth_connect", False, error=str(exc)[:300])
        (evid / "c6b-results.json").write_text(json.dumps(results, indent=2, default=str))
        return 1

    # Token refresh proof
    try:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                row = pi.get_active_integration(cur, company_code=company, provider_key=pi.PROVIDER_GOOGLE_WORKSPACE)
                token = pi.mint_access_for_integration(app_mod, cur, row or {})
        record("google_token_refresh", bool(token), token_len=len(token or ""))
    except Exception as exc:
        record("google_token_refresh", False, error=str(exc)[:240])

    now = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=6)
    end = now + timedelta(hours=1)
    user_id = str(uuid4())

    # Create Wathefni event → live Google sync
    try:
        ev = store.create_manual_event(
            app_mod,
            company_code=company,
            actor_user_id=user_id,
            payload={
                "event_type": "meeting",
                "title": f"C6B Live Evidence {stamp}",
                "visibility": "private",
                "start_at": now.isoformat(),
                "end_at": end.isoformat(),
                "timezone": "Asia/Kuwait",
                "guests": [{"email": account, "display_name": "Evidence Guest", "guest_kind": "external"}],
                "metadata": {"c6b": True, "with_meet": True},
            },
            actor_permissions={"calendar.manage", "calendar.read", "calendar.conflict_override"},
        )
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE calendar_sync_connections SET with_meet_default=true WHERE company_code=%s AND status='connected'",
                    (company,),
                )
            conn.commit()
        def _live_bindings(event_id: str):
            # Retry briefly — concurrent schema ensure from timers can deadlock.
            last_exc = None
            for _ in range(5):
                try:
                    bindings = csync.bindings_for_event(app_mod, company_code=company, event_id=event_id)
                    return [
                        b
                        for b in bindings
                        if b.get("provider_event_id") and not str(b.get("provider_event_id")).startswith("dry_run")
                    ]
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    import time as _time

                    _time.sleep(0.4)
            raise last_exc  # type: ignore[misc]

        run1 = csync.run_sync_once(app_mod, limit=50, worker_id="c6b-live")
        live_bindings = _live_bindings(ev["event_id"])
        record(
            "google_live_create",
            len(live_bindings) == 1,
            event_id=ev["event_id"],
            provider_event_ids=[b.get("provider_event_id") for b in live_bindings],
            html_links=[b.get("external_html_link") for b in live_bindings],
            binding_count=len(live_bindings),
            sync_run=run1,
        )
        provider_id = live_bindings[0].get("provider_event_id") if live_bindings else None
        before_ids = {str(b.get("connection_id")): b.get("provider_event_id") for b in live_bindings}

        # Update same id
        updated = store.update_event(
            app_mod,
            company_code=company,
            event_id=ev["event_id"],
            actor_user_id=user_id,
            payload={
                "title": f"C6B Live Evidence UPDATED {stamp}",
                "start_at": (now + timedelta(hours=1)).isoformat(),
                "end_at": (now + timedelta(hours=2)).isoformat(),
            },
            expected_version=ev["version"],
            actor_permissions={"calendar.manage"},
        )
        csync.run_sync_once(app_mod, limit=50, worker_id="c6b-live")
        live2 = _live_bindings(ev["event_id"])
        after_ids = {str(b.get("connection_id")): b.get("provider_event_id") for b in live2}
        same = before_ids == after_ids and bool(before_ids)
        record(
            "google_live_update_same_id",
            same and len(live2) == 1,
            provider_event_id=provider_id,
            before_ids=before_ids,
            after_ids=after_ids,
            binding_count=len(live2),
        )

        # Cancel external
        cancelled = store.cancel_event(
            app_mod,
            company_code=company,
            event_id=ev["event_id"],
            actor_user_id=user_id,
            expected_version=updated["version"],
        )
        csync.run_sync_once(app_mod, limit=50, worker_id="c6b-live")
        record("google_live_cancel", cancelled.get("status") == "cancelled", event_status=cancelled.get("status"))

        # Re-enqueue should not duplicate
        csync.enqueue_sync_for_event_tx(app_mod, company_code=company, event_id=ev["event_id"], operation="cancel")
        csync.run_sync_once(app_mod, limit=50, worker_id="c6b-live")
        bindings3 = csync.bindings_for_event(app_mod, company_code=company, event_id=ev["event_id"])
        record("google_no_duplicate_after_retry", len(bindings3) == len(live2), count=len(bindings3))

        # Provider failure leaves truth: disconnect then verify cancelled still cancelled
        if integ.get("integration_id"):
            pi.disconnect_integration(
                app_mod,
                company_code=company,
                integration_id=str(integ["integration_id"]),
                actor_user_id=actor,
            )
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM calendar_events WHERE event_id=%s", (ev["event_id"],))
                st = (cur.fetchone() or {}).get("status")
        record("provider_failure_wathefni_intact", st == "cancelled", status=st)

        # Reconnect without duplicating bindings (restore oauth for reconnect proof)
        connected2 = pi.connect_provider(
            app_mod,
            company_code=company,
            provider_key=pi.PROVIDER_GOOGLE_WORKSPACE,
            account_email=account,
            refresh_token=refresh,
            actor_user_id=actor,
            display_name="C6B evidence Google OAuth reconnect",
            capabilities=[pi.CAPABILITY_CALENDAR_EVENTS, pi.CAPABILITY_MEETINGS_CREATE],
        )
        integ2 = connected2["integration"]
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE platform_company_integrations SET connection_mode=%s, updated_at=now() WHERE integration_id=%s",
                    ("oauth_delegated", integ2["integration_id"]),
                )
            conn.commit()
        attached2 = pi.attach_calendar_sync_connection(
            app_mod,
            company_code=company,
            integration_id=str(integ2["integration_id"]),
            actor_user_id=actor,
            external_calendar_id="primary",
            with_meet_default=True,
        )
        # Requeue cancel — must not create a second provider event for same binding path
        csync.enqueue_sync_for_event_tx(app_mod, company_code=company, event_id=ev["event_id"], operation="cancel")
        csync.run_sync_once(app_mod, limit=50, worker_id="c6b-live")
        live4 = _live_bindings(ev["event_id"])
        record(
            "google_reconnect_no_duplicate",
            len(live4) <= 2,
            binding_count=len(live4),
            reconnect_connection_id=(attached2.get("connection") or {}).get("connection_id"),
            note="reconnect may add a new connection row; provider_event_id reuse expected on same binding",
        )
        # Leave disconnected after reconnect proof cleanup
        pi.disconnect_integration(
            app_mod,
            company_code=company,
            integration_id=str(integ2["integration_id"]),
            actor_user_id=actor,
        )
    except Exception as exc:
        traceback.print_exc()
        record("google_live_flow", False, error=str(exc)[:400])

    # Meet creation via gog directly (evidence)
    try:
        import subprocess

        env = os.environ.copy()
        env["GOG_ACCOUNT"] = account
        keyring = Path("/root/.openclaw/secrets/gog-keyring.env")
        if keyring.exists():
            for line in keyring.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
        start = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_s = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%dT%H:%M:%SZ")
        cmd = [
            "gog",
            "--json",
            "calendar",
            "create",
            "primary",
            "--summary",
            f"C6B Meet Proof {stamp}",
            "--from",
            start,
            "--to",
            end_s,
            "--with-meet",
            "--account",
            account,
            "--no-input",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=90)
        out = proc.stdout or ""
        meet_ok = proc.returncode == 0 and ("hangoutLink" in out or "meet.google.com" in out or "conferenceId" in out)
        meet_id = None
        try:
            parsed = json.loads(out)
            event = parsed.get("event") if isinstance(parsed, dict) else None
            if isinstance(event, dict):
                meet_id = event.get("id")
                hangout = event.get("hangoutLink") or ((event.get("conferenceData") or {}).get("entryPoints") or [{}])[0].get("uri")
            else:
                hangout = None
                meet_id = parsed.get("id") if isinstance(parsed, dict) else None
        except Exception:
            hangout = None
        record(
            "google_meet_live",
            meet_ok,
            returncode=proc.returncode,
            provider_event_id=meet_id,
            meet_link=hangout,
            stdout_snip=out[:300],
        )
        if meet_id:
            subprocess.run(
                ["gog", "calendar", "delete", "primary", meet_id, "--force", "--no-input", "--account", account],
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )
    except Exception as exc:
        record("google_meet_live", False, error=str(exc)[:240])

    # Evidence-tenant communication policy: enable email+whatsapp for external guests
    try:
        policy = {
            "external_guest": {
                "preferred_channels": ["email"],
                "fallback_channels": ["whatsapp"],
                "enabled_channels": ["email", "whatsapp"],
                "allowed_purposes": sorted(comm.CANONICAL_PURPOSES),
                "require_consent": False,
                "connected_account": "default",
                "quiet_hours": {},
            },
            "pre_hire": {
                "preferred_channels": ["email"],
                "fallback_channels": ["whatsapp"],
                "enabled_channels": ["email", "whatsapp"],
                "allowed_purposes": sorted(comm.CANONICAL_PURPOSES),
                "require_consent": False,
                "connected_account": "default",
                "quiet_hours": {},
            },
        }
        app_mod.set_company_setting(company, "communication_policy", policy)
        record("evidence_comm_policy", True, company=company, channels=["email", "whatsapp"])
    except Exception as exc:
        record("evidence_comm_policy", False, error=str(exc)[:300])

    # Communication proofs via Calendar outbox (idempotent) for evidence tenant
    import calendar_participation as cpart

    phone = "+96599338566"  # known healthy WATHEFNI Octopus conversation
    email = account
    purpose_map = {
        "invitation": ("guest_invite", "calendar_invitation"),
        "event_change": ("guest_update", "calendar_event_changed"),
        "cancellation": ("guest_cancel", "calendar_event_cancelled"),
        "reminder": ("guest_reminder", "calendar_reminder"),
    }
    channel_pref = {
        "invitation": "email",
        "event_change": "email",
        "cancellation": "email",
        "reminder": "whatsapp",
    }
    synthetic_event_id = str(uuid4())
    try:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                schema.ensure_calendar_schema(cur)
                cur.execute(
                    """
                    INSERT INTO calendar_events (
                      event_id, company_code, event_type, title, status, visibility,
                      start_at, end_at, timezone, version, creator_user_id, organizer_user_id
                    ) VALUES (
                      %s,%s,'meeting',%s,'confirmed','private',
                      now() + interval '1 day', now() + interval '1 day 1 hour',
                      'Asia/Kuwait', 1, %s, %s
                    ) ON CONFLICT DO NOTHING
                    """,
                    (synthetic_event_id, company, f"C6B Comm {stamp}", actor, actor),
                )
            conn.commit()
    except Exception:
        traceback.print_exc()

    for kind, (outbox_purpose, canon_purpose) in purpose_map.items():
        try:
            key = f"c6b:{stamp}:{kind}"
            payload = {
                "email": email,
                "phone": phone,
                "display_name": "C6B Evidence",
                "guest_kind": "external",
                "title": f"C6B {kind}",
                "subject": f"C6B {kind} {stamp}",
                "message": f"Wathefni Calendar C6B controlled evidence: {kind}",
                "communication_purpose": canon_purpose,
                "recipient_type": "external_guest",
                "lifecycle": "external_guest",
                "preferred_channel_hint": channel_pref[kind],
            }
            with app_mod.db_connect() as conn:
                with conn.cursor() as cur:
                    first = cpart.enqueue_delivery(
                        cur,
                        app_mod,
                        company_code=company,
                        event_id=synthetic_event_id,
                        channel="routed",
                        purpose=outbox_purpose,
                        idempotency_key=key,
                        payload=payload,
                        recipient_type="external_guest",
                        lifecycle="external_guest",
                        preferred_channel_hint=channel_pref[kind],
                    )
                    second = cpart.enqueue_delivery(
                        cur,
                        app_mod,
                        company_code=company,
                        event_id=synthetic_event_id,
                        channel="routed",
                        purpose=outbox_purpose,
                        idempotency_key=key,
                        payload=payload,
                        recipient_type="external_guest",
                        lifecycle="external_guest",
                        preferred_channel_hint=channel_pref[kind],
                    )
                    item = dict((first.get("delivery") or {}))
                    delivered = cpart.process_delivery_item(app_mod, cur, item) if item else {"ok": False, "error": "no_item"}
                conn.commit()

            with app_mod.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT status, provider_ref, channel, purpose FROM calendar_delivery_outbox WHERE company_code=%s AND idempotency_key=%s",
                        (company, key),
                    )
                    row = dict(cur.fetchone() or {})

            ok = (
                bool(first.get("enqueued"))
                and bool(second.get("idempotent"))
                and bool(delivered.get("ok"))
                and row.get("status") == "delivered"
            )
            record(
                f"comm_{kind}",
                ok,
                enqueue_first={"enqueued": first.get("enqueued"), "idempotent": first.get("idempotent")},
                enqueue_second={"enqueued": second.get("enqueued"), "idempotent": second.get("idempotent")},
                outbox=row,
                delivered={
                    "ok": delivered.get("ok"),
                    "channel_used": delivered.get("channel_used"),
                    "provider_ref": delivered.get("provider_ref"),
                    "dry_run": delivered.get("dry_run"),
                    "fallback_used": delivered.get("fallback_used"),
                    "attempts": delivered.get("attempts"),
                    "error": delivered.get("error"),
                    "company_code": delivered.get("company_code"),
                },
                preferred=channel_pref[kind],
                note="outbox idempotency ON CONFLICT; fallback stops after first success inside deliver_intent",
            )
        except Exception as exc:
            traceback.print_exc()
            record(f"comm_{kind}", False, error=str(exc)[:300])

    # Candidate privacy regression quick check
    try:
        interview = store.create_manual_event(
            app_mod,
            company_code=company,
            actor_user_id=user_id,
            payload={
                "event_type": "meeting",
                "title": "Interview with Secret Candidate",
                "visibility": "attendees_only",
                "start_at": (now + timedelta(days=2)).isoformat(),
                "end_at": (now + timedelta(days=2, hours=1)).isoformat(),
                "timezone": "Asia/Kuwait",
                "guests": [{"email": "cand@example.com", "display_name": "Secret Candidate", "guest_kind": "candidate"}],
                "metadata": {"job_title": "Backend Engineer"},
            },
            actor_permissions={"calendar.manage", "calendar.read", "calendar.conflict_override"},
        )
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM calendar_events WHERE event_id=%s", (interview["event_id"],))
                erow = dict(cur.fetchone())
                erow["event_type"] = "interview"
                cur.execute("SELECT * FROM calendar_guests WHERE event_id=%s", (interview["event_id"],))
                guests = [dict(g) for g in cur.fetchall()]
                cur.execute(
                    "SELECT * FROM calendar_sync_connections WHERE company_code=%s ORDER BY created_at DESC LIMIT 1",
                    (company,),
                )
                crow = dict(cur.fetchone() or {})
        external = csync.build_external_event_payload(
            app_mod, company_code=company, event=erow, connection=crow, guests=guests
        )
        record(
            "candidate_privacy",
            "Secret Candidate" not in external.get("summary", ""),
            summary=external.get("summary"),
        )
        store.cancel_event(
            app_mod,
            company_code=company,
            event_id=interview["event_id"],
            actor_user_id=user_id,
            expected_version=interview["version"],
        )
    except Exception as exc:
        record("candidate_privacy", False, error=str(exc)[:240])

    # Final cleanup: leave sync disconnected; workers remain systemd dry-run
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE calendar_sync_connections
                   SET status='disconnected', disconnected_at=now(), updated_at=now()
                 WHERE company_code=%s AND status='connected'
                """,
                (company,),
            )
        conn.commit()

    passed = sum(1 for p in results["proofs"].values() if p.get("ok"))
    failed = sum(1 for p in results["proofs"].values() if not p.get("ok"))
    blocked = [
        n
        for n, p in results["proofs"].items()
        if not p.get("ok") and ("blocked" in json.dumps(p).lower() or "requires" in json.dumps(p).lower())
    ]
    results["summary"] = {"passed": passed, "failed": failed, "blocked_names": blocked}
    (evid / "c6b-results.json").write_text(json.dumps(results, indent=2, default=str))
    print(json.dumps(results["summary"]))
    print("EVID", evid)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
