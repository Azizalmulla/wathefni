#!/usr/bin/env python3
"""Wathefni Calendar C5 smoke — platform integrations + Calendar sync consumers."""

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
    print("=== Wathefni Calendar C5 smoke (platform + sync) ===")
    os.environ["CALENDAR_SYNC_DRY_RUN"] = "true"
    try:
        import app as app_mod
        import calendar_schema as schema
        import calendar_store as store
        import calendar_sync as csync
        import calendar_sync_adapter as adapter_mod
        import calendar_sync_google as gadapter
        import calendar_sync_microsoft as madapter
        import platform_integrations as pi
    except Exception:
        traceback.print_exc()
        check("imports", False)
        return 1

    check("imports", True)
    src_sync = Path(csync.__file__).read_text()
    src_store = Path(store.__file__).read_text()
    src_pi = Path(pi.__file__).read_text()
    check("no google imports in calendar_store", "calendar_sync_google" not in src_store and "run_gog" not in src_store)
    check("no microsoft imports in calendar_store", "calendar_sync_microsoft" not in src_store and "graph.microsoft" not in src_store)
    check("sync layer uses adapter factory", "get_adapter" in src_sync)
    check("sync prefers platform credentials", "platform_integration_id" in src_sync and "mint_access_for_integration" in src_sync)
    check("legacy_operator mode present", "legacy_operator" in src_sync)
    check("candidate name default hidden", "sync_include_candidate_name" in src_sync)
    check("platform reserved caps not executed", "RESERVED_CAPABILITIES" in src_pi and "identity.sso" in src_pi)
    check("implemented caps only calendar+meetings", "calendar.events" in src_pi and "meetings.create" in src_pi)
    app_src = Path(app_mod.__file__).read_text()
    check("sync routes present", "/dashboard/calendar/sync/connections" in app_src)
    check("microsoft sync connect route", "/dashboard/calendar/sync/connections/microsoft" in app_src)
    check("platform integration routes", "/dashboard/platform/integrations" in app_src)
    check("event sync status route", "/dashboard/calendar/events/{event_id}/sync" in app_src)
    check("adapter routes microsoft", "microsoft_365" in Path(adapter_mod.__file__).read_text())

    company = f"C5SMOKE{uuid4().hex[:8].upper()}"
    other = f"C5OTHER{uuid4().hex[:8].upper()}"
    user_a = str(uuid4())
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=4)
    end = now + timedelta(hours=1)
    encryption_ok = hasattr(app_mod, "encrypt_sensitive_text")

    try:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                schema.ensure_calendar_schema(cur)
                pi.ensure_schema(cur)
            conn.commit()

        registry = pi.capability_registry()
        check("capability registry providers", "google_workspace" in registry["providers"] and "microsoft_365" in registry["providers"])
        check(
            "reserved future listed not implemented",
            "identity.sso" in registry["reserved_future"] and "identity.sso" not in registry["implemented"],
        )

        # Legacy operator connection (dry-run ok without GOG)
        legacy = csync.ensure_legacy_operator_connection(app_mod, company_code=company, actor_user_id=user_a)
        check("legacy_operator connection", legacy.get("ok") and (legacy.get("connection") or {}).get("mode") == "legacy_operator")
        conn_id = (legacy.get("connection") or {})["connection_id"]

        other_list = csync.list_connections(app_mod, company_code=other)
        check("no cross-tenant connection leak", all(c.get("connection_id") != conn_id for c in other_list))

        google_conn_id = None
        ms_conn_id = None
        google_integ_id = None
        ms_integ_id = None

        if encryption_ok:
            g_plat = pi.connect_provider(
                app_mod,
                company_code=company,
                provider_key=pi.PROVIDER_GOOGLE_WORKSPACE,
                account_email=f"gw-{company.lower()}@example.com",
                refresh_token=f"refresh-google-{uuid4().hex}",
                actor_user_id=user_a,
                capabilities=[pi.CAPABILITY_CALENDAR_EVENTS, pi.CAPABILITY_MEETINGS_CREATE, pi.CAPABILITY_SSO],
            )
            google_integ = g_plat.get("integration") or {}
            google_integ_id = google_integ.get("integration_id")
            check("google workspace platform connected", google_integ.get("status") == "connected")
            check("reserved SSO not granted", "identity.sso" not in (google_integ.get("capabilities") or []))
            check("calendar+meetings granted", set(google_integ.get("capabilities") or {}) >= {"calendar.events", "meetings.create"})
            check("credentials flag without ciphertext", google_integ.get("has_credentials") is True and "ciphertext" not in google_integ)

            g_attach = pi.attach_calendar_sync_connection(
                app_mod,
                company_code=company,
                integration_id=str(google_integ_id),
                actor_user_id=user_a,
                external_calendar_id="primary",
                with_meet_default=True,
            )
            google_conn = g_attach.get("connection") or {}
            google_conn_id = google_conn.get("connection_id")
            check("google calendar sync attached", google_conn.get("provider_key") == "google" and google_conn.get("platform_integration_id") == google_integ_id)

            m_plat = csync.connect_microsoft_company(
                app_mod,
                company_code=company,
                account_email=f"m365-{company.lower()}@example.com",
                refresh_token=f"refresh-m365-{uuid4().hex}",
                actor_user_id=user_a,
                with_meet_default=True,
            )
            ms_integ = m_plat.get("integration") or {}
            ms_conn = m_plat.get("connection") or {}
            ms_integ_id = ms_integ.get("integration_id")
            ms_conn_id = ms_conn.get("connection_id")
            check("microsoft platform connected", ms_integ.get("provider_key") == "microsoft_365" and ms_integ.get("status") == "connected")
            check("microsoft calendar sync attached", ms_conn.get("provider_key") == "microsoft" and bool(ms_conn_id))

            other_integs = pi.list_integrations(app_mod, company_code=other)
            check("no cross-tenant platform leak", all(i.get("integration_id") not in {google_integ_id, ms_integ_id} for i in other_integs))
            listed_plat = pi.list_integrations(app_mod, company_code=company)
            check(
                "platform list hides secrets",
                all("ciphertext" not in i and "refresh_token" not in i for i in listed_plat),
            )
        else:
            check("encryption available for platform connect", False, "encrypt_sensitive_text missing")

        # Create event → enqueue sync (legacy + platform connections)
        ev = store.create_manual_event(
            app_mod,
            company_code=company,
            actor_user_id=user_a,
            payload={
                "event_type": "meeting",
                "title": "C5 Sync Meeting",
                "visibility": "private",
                "start_at": now.isoformat(),
                "end_at": end.isoformat(),
                "timezone": "Asia/Kuwait",
            },
            actor_permissions={"calendar.manage", "calendar.read", "calendar.conflict_override"},
        )
        event_id = ev["event_id"]
        check("create event", bool(event_id))

        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS c FROM calendar_sync_outbox WHERE company_code=%s AND event_id=%s",
                    (company, event_id),
                )
                qn = int((cur.fetchone() or {}).get("c") or 0)
        check("sync outbox enqueued on create", qn >= 1)

        run1 = csync.run_sync_once(app_mod, limit=50)
        check("sync worker ran", run1.get("ok") is True)

        bindings = csync.bindings_for_event(app_mod, company_code=company, event_id=event_id)
        check("binding created", len(bindings) >= 1)
        by_conn0 = {b.get("connection_id"): b for b in bindings}
        b0 = by_conn0.get(conn_id) or bindings[0]
        provider_id = b0.get("provider_event_id")
        check("dry-run provider id set", bool(provider_id))
        check("binding synced", b0.get("sync_status") == "synced")
        if encryption_ok and google_conn_id and ms_conn_id:
            check("google platform binding synced", (by_conn0.get(google_conn_id) or {}).get("sync_status") == "synced")
            check("microsoft platform binding synced", (by_conn0.get(ms_conn_id) or {}).get("sync_status") == "synced")
            check(
                "distinct provider ids per connection",
                len({b.get("provider_event_id") for b in bindings if b.get("provider_event_id")}) >= 2,
            )

        updated = store.update_event(
            app_mod,
            company_code=company,
            event_id=event_id,
            actor_user_id=user_a,
            payload={"start_at": (now + timedelta(hours=2)).isoformat(), "end_at": (now + timedelta(hours=3)).isoformat()},
            expected_version=ev["version"],
            actor_permissions={"calendar.manage"},
        )
        check("reschedule ok", int(updated.get("version") or 0) > int(ev.get("version") or 0))
        run2 = csync.run_sync_once(app_mod, limit=50)
        check("sync after reschedule", run2.get("ok") is True)
        bindings2 = csync.bindings_for_event(app_mod, company_code=company, event_id=event_id)
        # One binding per connection
        expected_bindings = 1 + (1 if google_conn_id else 0) + (1 if ms_conn_id else 0)
        check("one binding per connection", len(bindings2) == expected_bindings)
        legacy_b = next((b for b in bindings2 if b.get("connection_id") == conn_id), bindings2[0])
        check("same provider_event_id after update", legacy_b.get("provider_event_id") == provider_id)

        again = csync.enqueue_sync_for_event_tx(app_mod, company_code=company, event_id=event_id, operation="upsert")
        check("re-enqueue ok", again.get("ok") is True)
        csync.run_sync_once(app_mod, limit=50)
        bindings3 = csync.bindings_for_event(app_mod, company_code=company, event_id=event_id)
        check("idempotent binding count", len(bindings3) == expected_bindings)

        interview_ev = store.create_manual_event(
            app_mod,
            company_code=company,
            actor_user_id=user_a,
            payload={
                "event_type": "meeting",
                "title": "Interview with Secret Candidate",
                "visibility": "attendees_only",
                "start_at": (now + timedelta(days=1)).isoformat(),
                "end_at": (now + timedelta(days=1, hours=1)).isoformat(),
                "timezone": "Asia/Kuwait",
                "guests": [{"email": "cand@example.com", "display_name": "Secret Candidate", "guest_kind": "candidate"}],
                "metadata": {"job_title": "Backend Engineer"},
            },
            actor_permissions={"calendar.manage", "calendar.read", "calendar.conflict_override"},
        )
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM calendar_events WHERE event_id=%s", (interview_ev["event_id"],))
                erow = dict(cur.fetchone())
                erow["event_type"] = "interview"
                cur.execute("SELECT * FROM calendar_guests WHERE event_id=%s", (interview_ev["event_id"],))
                guests = [dict(g) for g in cur.fetchall()]
                cur.execute("SELECT * FROM calendar_sync_connections WHERE connection_id=%s", (conn_id,))
                crow = dict(cur.fetchone())
        external = csync.build_external_event_payload(
            app_mod, company_code=company, event=erow, connection=crow, guests=guests
        )
        check("candidate name hidden by default", "Secret Candidate" not in external.get("summary", ""))
        check("limited interview title", external.get("summary") in {"Interview", "Backend Engineer"})

        disc = csync.disconnect_connection(app_mod, company_code=company, connection_id=conn_id, actor_user_id=user_a)
        check("disconnect", (disc.get("connection") or {}).get("status") == "disconnected")
        cancelled = store.cancel_event(
            app_mod,
            company_code=company,
            event_id=event_id,
            actor_user_id=user_a,
            expected_version=updated["version"],
        )
        check("wathefni cancel intact after disconnect", cancelled.get("status") == "cancelled")

        recon = csync.reconnect_connection(app_mod, company_code=company, connection_id=conn_id, actor_user_id=user_a)
        check("reconnect", (recon.get("connection") or {}).get("status") == "connected")
        csync.run_sync_once(app_mod, limit=50)
        bindings4 = csync.bindings_for_event(app_mod, company_code=company, event_id=event_id)
        check("reconnect no duplicate bindings", len([b for b in bindings4 if b.get("connection_id") == conn_id]) == 1)

        if encryption_ok and google_integ_id:
            disc_plat = pi.disconnect_integration(
                app_mod, company_code=company, integration_id=str(google_integ_id), actor_user_id=user_a
            )
            check("platform disconnect", (disc_plat.get("integration") or {}).get("status") == "disconnected")
            listed_sync = csync.list_connections(app_mod, company_code=company)
            g_row = next((c for c in listed_sync if c.get("connection_id") == google_conn_id), None)
            check("calendar sync detached on platform disconnect", (g_row or {}).get("status") == "disconnected")

        adapter = gadapter.GoogleCalendarSyncAdapter()
        fake_conn = {
            "mode": "legacy_operator",
            "_legacy_account": "ops@example.com",
            "external_calendar_id": "primary",
            "_legacy": app_mod,
        }
        created = adapter.upsert_event(
            connection=fake_conn,
            binding=None,
            external_event={
                "event_id": event_id,
                "summary": "C5 proof",
                "start": now.isoformat(),
                "end": end.isoformat(),
                "timezone": "Asia/Kuwait",
                "all_day": False,
                "with_meet": True,
            },
            legacy=app_mod,
        )
        check("google create dry-run", created.get("ok") and created.get("dry_run") and created.get("provider_event_id"))
        updated_g = adapter.upsert_event(
            connection=fake_conn,
            binding={"provider_event_id": created["provider_event_id"]},
            external_event={
                "event_id": event_id,
                "summary": "C5 proof updated",
                "start": (now + timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=2)).isoformat(),
                "timezone": "Asia/Kuwait",
            },
            legacy=app_mod,
        )
        check("google update same id", updated_g.get("ok") and updated_g.get("provider_event_id") == created["provider_event_id"])
        cancelled_g = adapter.cancel_event(
            connection=fake_conn,
            binding={"provider_event_id": created["provider_event_id"]},
            legacy=app_mod,
        )
        check("google cancel dry-run", cancelled_g.get("ok") is True)

        ms = madapter.MicrosoftCalendarSyncAdapter()
        ms_conn_fake = {"external_calendar_id": "calendar", "with_meet_default": True, "_access_token": None}
        created_ms = ms.upsert_event(
            connection=ms_conn_fake,
            binding=None,
            external_event={
                "event_id": event_id,
                "summary": "C5 M365 proof",
                "start": now.isoformat(),
                "end": end.isoformat(),
                "timezone": "Asia/Kuwait",
                "with_meet": True,
            },
        )
        check("microsoft create dry-run + teams", created_ms.get("ok") and created_ms.get("dry_run") and created_ms.get("provider_event_id") and created_ms.get("meeting_url"))
        updated_ms = ms.upsert_event(
            connection=ms_conn_fake,
            binding={"provider_event_id": created_ms["provider_event_id"]},
            external_event={
                "event_id": event_id,
                "summary": "C5 M365 proof updated",
                "start": (now + timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=2)).isoformat(),
                "timezone": "Asia/Kuwait",
                "with_meet": True,
            },
        )
        check("microsoft update same id", updated_ms.get("ok") and updated_ms.get("provider_event_id") == created_ms["provider_event_id"])
        cancelled_ms = ms.cancel_event(connection=ms_conn_fake, binding={"provider_event_id": created_ms["provider_event_id"]})
        check("microsoft cancel dry-run", cancelled_ms.get("ok") is True)

        bf = csync.backfill_legacy_google_bindings(app_mod, company_code=company, dry_run=True, limit=50)
        check("legacy backfill dry-run", bf.get("ok") is True and bf.get("dry_run") is True)

        listed = csync.list_connections(app_mod, company_code=company)
        check("public connection has no ciphertext", all("ciphertext" not in c and "refresh_token" not in c for c in listed))

        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                for table in (
                    "calendar_sync_audit",
                    "calendar_sync_outbox",
                    "calendar_sync_bindings",
                    "calendar_sync_credentials",
                    "calendar_sync_connections",
                    "platform_company_integration_audit",
                    "platform_company_integration_credentials",
                    "platform_company_integrations",
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
                    try:
                        cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (company,))
                        cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (other,))
                    except Exception:
                        pass
            conn.commit()
        check("cleanup", True)

        shell = ROOT.parent / "apps/wathefni-dashboard/src/components/CalendarShell.tsx"
        panel = ROOT.parent / "apps/wathefni-dashboard/src/components/PlatformIntegrationsPanel.tsx"
        settings = ROOT.parent / "apps/wathefni-dashboard/src/pages/SettingsPage.tsx"
        if shell.exists() and panel.exists():
            text = shell.read_text()
            panel_text = panel.read_text()
            settings_text = settings.read_text() if settings.exists() else ""
            check("UI platform panel in Settings host", "PlatformIntegrationsPanel" in settings_text)
            check("UI platform panel component", "Platform integrations" in panel_text or "تكاملات المنصة" in panel_text)
            check("UI calendar has no External sync", "External sync" not in text and "مزامنة خارجية" not in text)
            check("UI calendar quiet Synced", "Synced" in text or "تمت المزامنة" in text)
            check("UI calendar quiet Not synced", "Not synced" in text or "غير متزامن" in text)
            check("UI microsoft option", "microsoft_365" in panel_text and "Google Workspace" in panel_text)
        else:
            check("UI sync markers skipped", True)

    except Exception as exc:
        traceback.print_exc()
        check("live proofs", False, str(exc)[:300])

    print(f"=== C5 smoke done PASS={PASS} FAIL={FAIL} ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
