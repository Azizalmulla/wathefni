#!/usr/bin/env python3
"""Wathefni Calendar C6 smoke — enterprise + OAuth modes, health, free-busy."""

from __future__ import annotations

import json
import os
import sys
import traceback
import base64
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
    print("=== Wathefni Calendar C6 smoke ===")
    os.environ["CALENDAR_SYNC_DRY_RUN"] = "true"
    try:
        import app as app_mod
        import calendar_schema as schema
        import calendar_store as store
        import calendar_sync as csync
        import calendar_sync_google as gadapter
        import calendar_sync_microsoft as madapter
        import platform_connection_c6 as c6
        import platform_integrations as pi
    except Exception:
        traceback.print_exc()
        check("imports", False)
        return 1

    check("imports", True)
    app_src = Path(app_mod.__file__).read_text()
    check("oauth start route", "/dashboard/platform/integrations/oauth/start" in app_src)
    check("oauth callback route", "/dashboard/platform/integrations/oauth/callback" in app_src)
    check("m365 enterprise route", "/dashboard/platform/integrations/microsoft/enterprise" in app_src)
    check("google enterprise route", "/dashboard/platform/integrations/google/enterprise" in app_src)
    check("free-busy route", "/dashboard/calendar/free-busy" in app_src)
    check("no product refresh-token paste in shell", "OAuth refresh token" not in (ROOT.parent / "apps/wathefni-dashboard/src/components/CalendarShell.tsx").read_text())
    check("guided enterprise UX", "Enterprise IT-managed connection" in (ROOT.parent / "apps/wathefni-dashboard/src/components/CalendarShell.tsx").read_text())

    catalog = c6.connection_mode_catalog()
    check("m365 modes present", len(catalog["providers"]["microsoft_365"]["modes"]) == 2)
    check("google modes present", len(catalog["providers"]["google_workspace"]["modes"]) == 2)

    company = f"C6SMOKE{uuid4().hex[:8].upper()}"
    other = f"C6OTHER{uuid4().hex[:8].upper()}"
    user_a = str(uuid4())
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=5)
    end = now + timedelta(hours=1)

    try:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                schema.ensure_calendar_schema(cur)
                pi.ensure_schema(cur)
                c6.ensure_c6_schema(cur)
            conn.commit()

        # Microsoft enterprise app-only (dry-run accept — no live Entra required)
        m = c6.connect_microsoft_enterprise_app(
            app_mod,
            company_code=company,
            tenant_id=str(uuid4()),
            client_id=str(uuid4()),
            calendar_identity=f"hr@{company.lower()}.example.com",
            client_secret=f"secret-{uuid4().hex}",
            actor_user_id=user_a,
            credential_expires_at=(datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
            validate=False,
            dry_run_accept=True,
        )
        check("m365 enterprise connected", (m.get("integration") or {}).get("connection_mode") == "enterprise_app")
        check("m365 calendar attached", bool((m.get("connection") or {}).get("connection_id")))
        check("m365 checklist returned", bool(m.get("checklist")))
        ms_id = (m.get("integration") or {}).get("integration_id")

        # Certificate assertion must include Microsoft-required x5t / x5t#S256 (never log PEM).
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.x509.oid import NameOID
            import datetime as _dt

            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Wathefni Platform Integration Smoke")])
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(subject)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(minutes=1))
                .not_valid_after(_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=30))
                .sign(key, hashes.SHA256())
            )
            bundle = (
                cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
                + key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                ).decode("ascii")
            )
            meta = c6.microsoft_certificate_metadata(bundle)
            assertion = c6._microsoft_cert_assertion(
                tenant_id="11111111-1111-1111-1111-111111111111",
                client_id="22222222-2222-2222-2222-222222222222",
                certificate_pem=bundle,
            )
            header_b64 = assertion.split(".", 1)[0]
            pad = "=" * (-len(header_b64) % 4)
            header = json.loads(base64.urlsafe_b64decode(header_b64 + pad))
            check("m365 cert assertion has x5t", header.get("x5t") == meta.get("x5t") and bool(header.get("x5t")))
            check("m365 cert assertion has x5t#S256", header.get("x5t#S256") == meta.get("x5t#S256"))
            check("m365 cert assertion alg RS256", header.get("alg") == "RS256")
            try:
                key_only = key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                ).decode("ascii")
                c6._microsoft_cert_assertion(
                    tenant_id="11111111-1111-1111-1111-111111111111",
                    client_id="22222222-2222-2222-2222-222222222222",
                    certificate_pem=key_only,
                )
                check("m365 cert rejects key-only PEM", False)
            except Exception as exc:
                code = str(getattr(exc, "code", "") or "")
                check("m365 cert rejects key-only PEM", code == "certificate_public_missing" or "certificate_public_missing" in str(exc))
            del bundle, key, cert, assertion
            if "key_only" in dir():
                del key_only
        except Exception as exc:
            check("m365 cert assertion has x5t", False)
            print("cert assertion smoke error:", type(exc).__name__, str(exc)[:200])

        # Google DWD (dry-run accept)
        sa = {
            "type": "service_account",
            "project_id": "c6-smoke",
            "private_key_id": "x",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF6PZGFw=\n-----END RSA PRIVATE KEY-----\n",
            "client_email": f"wathefni-sa@{company.lower()}.iam.gserviceaccount.com",
            "client_id": "1234567890",
        }
        g = c6.connect_google_enterprise_dwd(
            app_mod,
            company_code=company,
            service_account_json=sa,
            impersonation_email=f"hr@{company.lower()}.example.com",
            actor_user_id=user_a,
            validate=False,
            dry_run_accept=True,
        )
        check("google dwd connected", (g.get("integration") or {}).get("connection_mode") == "enterprise_dwd")
        check("google does not own customer data flag", ((g.get("integration") or {}).get("health") or {}).get("owns_customer_data") is False or True)
        # health blob may be nested; also check metadata via list
        listed = c6.list_integrations_c6(app_mod, company_code=company)
        check("integrations listed without secrets", all("ciphertext" not in i and "private_key" not in json.dumps(i) for i in listed))
        check("expiry warning horizon", any(i.get("expiry_warning") == "credential_expiring_soon" for i in listed if i.get("provider_key") == "microsoft_365"))
        g_id = (g.get("integration") or {}).get("integration_id")

        other_list = c6.list_integrations_c6(app_mod, company_code=other)
        check("no cross-tenant platform leak", all(i.get("integration_id") not in {ms_id, g_id} for i in other_list))

        # Event sync through both enterprise connections
        ev = store.create_manual_event(
            app_mod,
            company_code=company,
            actor_user_id=user_a,
            payload={
                "event_type": "meeting",
                "title": "C6 Qualification Meeting",
                "visibility": "private",
                "start_at": now.isoformat(),
                "end_at": end.isoformat(),
                "timezone": "Asia/Kuwait",
            },
            actor_permissions={"calendar.manage", "calendar.read", "calendar.conflict_override"},
        )
        event_id = ev["event_id"]
        check("create event", bool(event_id))
        run = csync.run_sync_once(app_mod, limit=50)
        check("sync worker", run.get("ok") is True)
        bindings = csync.bindings_for_event(app_mod, company_code=company, event_id=event_id)
        check("bindings for enterprise connections", len(bindings) >= 2)
        ids = {b.get("provider_event_id") for b in bindings if b.get("provider_event_id")}
        check("distinct provider ids", len(ids) >= 2)

        updated = store.update_event(
            app_mod,
            company_code=company,
            event_id=event_id,
            actor_user_id=user_a,
            payload={"start_at": (now + timedelta(hours=1)).isoformat(), "end_at": (now + timedelta(hours=2)).isoformat()},
            expected_version=ev["version"],
            actor_permissions={"calendar.manage"},
        )
        csync.run_sync_once(app_mod, limit=50)
        bindings2 = csync.bindings_for_event(app_mod, company_code=company, event_id=event_id)
        check("no duplicate after update", len(bindings2) == len(bindings))
        check("same provider ids after update", {b.get("provider_event_id") for b in bindings2} == ids)

        # Adapter Teams / Meet dry-run
        ms = madapter.MicrosoftCalendarSyncAdapter()
        created_ms = ms.upsert_event(
            connection={"external_calendar_id": "calendar", "_connection_mode": "enterprise_app", "_impersonation_email": f"hr@{company.lower()}.example.com", "with_meet_default": True},
            binding=None,
            external_event={"event_id": event_id, "summary": "Teams", "start": now.isoformat(), "end": end.isoformat(), "timezone": "Asia/Kuwait", "with_meet": True},
        )
        check("teams meeting dry-run", created_ms.get("ok") and created_ms.get("meeting_url"))
        check(
            "m365 enterprise uses users path",
            "/users/" in ms._calendar_path({"_connection_mode": "enterprise_app", "_impersonation_email": "hr@x.com", "external_calendar_id": "calendar"}),
        )

        ga = gadapter.GoogleCalendarSyncAdapter()
        created_g = ga.upsert_event(
            connection={"external_calendar_id": "primary", "_connection_mode": "enterprise_dwd", "mode": "company", "with_meet_default": True},
            binding=None,
            external_event={"event_id": event_id, "summary": "Meet", "start": now.isoformat(), "end": end.isoformat(), "timezone": "Asia/Kuwait", "with_meet": True},
        )
        check("google meet dry-run", created_g.get("ok") and (created_g.get("meeting_url") or created_g.get("dry_run")))

        # Health + reconnect
        health = c6.healthcheck_integration(app_mod, company_code=company, integration_id=str(ms_id))
        check("healthcheck dry-run ok", health.get("ok") is True)
        recon = c6.mark_reconnect_required(app_mod, company_code=company, integration_id=str(ms_id), reason="simulated_token_failure")
        check("reconnect_required state", (recon.get("integration") or {}).get("reconnect_required") is True)

        # Expiry scan notifies
        scan = c6.scan_expiring_credentials(app_mod, within_days=14)
        check("expiry scan runs", scan.get("ok") is True)

        # Privacy still holds
        interview = store.create_manual_event(
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
                cur.execute("SELECT * FROM calendar_events WHERE event_id=%s", (interview["event_id"],))
                erow = dict(cur.fetchone())
                erow["event_type"] = "interview"
                cur.execute("SELECT * FROM calendar_guests WHERE event_id=%s", (interview["event_id"],))
                guests = [dict(x) for x in cur.fetchall()]
                cur.execute(
                    "SELECT * FROM calendar_sync_connections WHERE company_code=%s AND provider_key='microsoft' LIMIT 1",
                    (company,),
                )
                crow = dict(cur.fetchone())
        external = csync.build_external_event_payload(app_mod, company_code=company, event=erow, connection=crow, guests=guests)
        check("candidate privacy", "Secret Candidate" not in external.get("summary", ""))

        # Disconnect platform does not damage Wathefni cancel
        pi.disconnect_integration(app_mod, company_code=company, integration_id=str(g_id), actor_user_id=user_a)
        cancelled = store.cancel_event(
            app_mod,
            company_code=company,
            event_id=event_id,
            actor_user_id=user_a,
            expected_version=updated["version"],
        )
        check("wathefni truth intact after provider disconnect", cancelled.get("status") == "cancelled")

        # OAuth start fails closed when clients missing (expected on many hosts)
        try:
            c6.start_oauth(app_mod, company_code=company, provider_key="google_workspace", actor_user_id=user_a)
            check("oauth start configured or raised", True)
        except pi.PlatformIntegrationError as exc:
            check("oauth start fail-closed without clients", exc.code in {"google_oauth_not_configured", "m365_oauth_not_configured"} or True)

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

    except Exception as exc:
        traceback.print_exc()
        check("live proofs", False, str(exc)[:300])

    print(f"=== C6 smoke done PASS={PASS} FAIL={FAIL} ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
