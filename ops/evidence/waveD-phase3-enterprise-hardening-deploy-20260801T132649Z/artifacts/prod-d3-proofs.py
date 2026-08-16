#!/usr/bin/env python3
"""Wave D Phase 3 production proofs — WATHEFNI/test only. External tenants stay disabled."""

from __future__ import annotations

import base64
import json
import os
import sys
import traceback
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from psycopg2.extras import Json

MARKER = "wave_d3_prod_proof"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/waveD3-proofs.json")

# Production identity (same as orchestrator service)
os.environ.setdefault("WATHEFNI_ENV", "production")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")

sys.path.insert(0, "/opt/wathefni/orchestrator")
os.chdir("/opt/wathefni/orchestrator")

import app  # noqa: E402
import durable_email_ingress as ingress  # noqa: E402
import inbound_enterprise_hardening as ieh  # noqa: E402
import inbound_intake_product as iip  # noqa: E402
import inbound_retention_policy as retention  # noqa: E402
from intake_quarantine_storage import LocalVolumeQuarantineStorage  # noqa: E402


def _pdf(name: str, email: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({name}) Tj 0 -18 Td (Email {email}) Tj ET".encode()
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>endobj\n"
        + f"4 0 obj<</Length {len(stream)}>>stream\n".encode()
        + stream
        + b"\nendstream\nendobj\n"
        + b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        + b"xref\n0 6\n0000000000 65535 f \ntrailer<</Root 1 0 R/Size 6>>\nstartxref\n0\n%%EOF\n"
    )


def _att(name: str, data: bytes) -> dict[str, Any]:
    encoded = base64.b64encode(data).decode("ascii")
    return {"Name": name, "Content": encoded, "ContentType": "application/pdf", "ContentLength": len(encoded)}


def _payload(message_id: str, recipient: str, sender: str, attachments: list[dict]) -> dict:
    email = app._parse_email_address(sender) or sender
    return {
        "MessageID": message_id,
        "OriginalRecipient": recipient,
        "From": sender,
        "FromFull": {"Email": email, "Name": "Sender"},
        "ToFull": [{"Email": recipient, "Name": "", "MailboxHash": ""}],
        "Subject": f"{MARKER} CV",
        "Date": "Sat, 01 Aug 2026 00:00:00 +0000",
        "Attachments": attachments,
        "Headers": [],
    }


def _ctx(company: str = "WATHEFNI") -> dict[str, Any]:
    user_id = "d3-prod-proof"
    perms = sorted(app.ROLE_PERMISSIONS["owner"])
    return {
        "company_code": company,
        "actor_user_id": user_id,
        "actor_email": "d3-proof@wathefni.ai",
        "actor_name": "D3 Proof",
        "role": "owner",
        "actor_role": "owner",
        "permission_authority": "backend_current",
        "permission_subject_user_id": user_id,
        "permission_subject_company": company,
        "permissions": perms,
        "modules": {"pre_hiring": {"enabled": True}},
        "hr_user": {"user_id": user_id, "role": "owner", "status": "active", "company_code": company, "permissions": perms},
        "access": {"role": "owner", "permissions": perms, "permission_authority": "backend_current", "permission_subject_user_id": user_id, "permission_subject_company": company},
    }


def gate(results: dict, name: str, ok: bool, detail: Any = None) -> None:
    results[name] = {"ok": bool(ok), "detail": detail}
    print(("PASS" if ok else "FAIL"), name, json.dumps(detail, default=str)[:240])


def main() -> int:
    results: dict[str, Any] = {"stamp": datetime.now(UTC).isoformat(), "marker": MARKER}
    stamp = uuid.uuid4().hex[:8]
    ctx = _ctx("WATHEFNI")
    cleanup: dict[str, Any] = {"intake_ids": [], "inbound_ids": [], "job_ids": [], "settings_restored": False}
    store = ingress.LocalQuarantineStore(app.durable_email_ingress_config().quarantine_root)
    previous_enterprise = None

    try:
        # --- Allowlist / enablement ---
        gate(
            results,
            "wathefni_allowlisted_external_disabled",
            iip.company_on_inbound_allowlist("WATHEFNI")
            and not iip.company_on_inbound_allowlist("ACMECORP")
            and (os.environ.get("WATHEFNI_MAILBOX_SYNC") or "off").lower() in {"off", "0", "false", ""},
            {
                "WATHEFNI": iip.company_on_inbound_allowlist("WATHEFNI"),
                "ACMECORP": iip.company_on_inbound_allowlist("ACMECORP"),
                "allowed_env": os.environ.get("WATHEFNI_INBOUND_ALLOWED_COMPANIES"),
                "mailbox_sync": os.environ.get("WATHEFNI_MAILBOX_SYNC"),
                "test_tenant_heuristic": iip.company_looks_like_test_tenant("INBOUNDQA"),
            },
        )

        # Soft warning unit
        soft = ieh.evaluate_quota(
            {"day": {"messages": 80, "source_bytes": 0}, "month": {"messages": 0, "source_bytes": 0}},
            company_code="WATHEFNI",
            settings={"inbound_enterprise": {"plan": "starter", "quota_overrides": {"daily_message_quota": 100}}},
        )
        gate(
            results,
            "soft_warning_at_threshold",
            soft.status is None and "daily_message_quota_soft_warning" in soft.soft_warnings,
            {"status": soft.status, "warnings": list(soft.soft_warnings)},
        )

        # Save + set enterprise settings for proof
        previous_enterprise = (app.get_company_settings("WATHEFNI") or {}).get("inbound_enterprise")
        app.dashboard_inbound_plan_update(
            {
                "plan": "starter",
                "quota_overrides": {"daily_message_quota": 1, "monthly_message_quota": 0},
                "soft_warning_pct": 80,
                "kill_switch": False,
            },
            ctx,
        )

        created = app.dashboard_intake_create({"label": f"{MARKER} general"}, ctx)
        address = created["address"]["address"]
        intake_id = created["address"]["intake_id"]
        local_part = created["address"]["local_part"]
        cleanup["intake_ids"].append(intake_id)
        gate(results, "create_intake_address", bool(address and intake_id), created["address"])

        # Over-limit → waiting_quota
        first = app.process_postmark_inbound(
            _payload(f"d3p-{stamp}-1", address, "d3cand1@example.com", [_att("c1.pdf", _pdf("C1", "d3cand1@example.com"))]),
            quarantine_store=store,
        )
        cleanup["inbound_ids"].append(first.get("inbound_id"))
        second = app.process_postmark_inbound(
            _payload(f"d3p-{stamp}-2", address, "d3cand2@example.com", [_att("c2.pdf", _pdf("C2", "d3cand2@example.com"))]),
            quarantine_store=store,
        )
        cleanup["inbound_ids"].append(second.get("inbound_id"))
        gate(
            results,
            "over_limit_waiting_quota_never_rejected",
            first.get("durable") is True
            and second.get("durable") is True
            and second.get("status") == "waiting_quota"
            and second.get("quota_code") == "daily_message_quota",
            {"first": {"status": first.get("status"), "durable": first.get("durable")}, "second": second},
        )

        # Burst override
        raised = app.dashboard_inbound_admin_override(
            {
                "burst_enabled": True,
                "burst_pct": 0,
                "hours": 1,
                "reason": "d3_prod_proof_campaign",
                "quota_overrides": {"daily_message_quota": 100},
            },
            ctx,
        )
        third = app.process_postmark_inbound(
            _payload(f"d3p-{stamp}-3", address, "d3cand3@example.com", [_att("c3.pdf", _pdf("C3", "d3cand3@example.com"))]),
            quarantine_store=store,
        )
        cleanup["inbound_ids"].append(third.get("inbound_id"))
        expires = ieh._parse_iso(raised["admin_override"]["expires_at"])
        gate(
            results,
            "burst_override_works",
            raised.get("ok")
            and third.get("durable") is True
            and third.get("status") != "waiting_quota"
            and expires is not None
            and expires > datetime.now(UTC),
            {"override": raised.get("admin_override"), "third_status": third.get("status"), "expires_at": raised["admin_override"].get("expires_at")},
        )

        # Expiry: synthesize expired override and confirm inactive
        expired = dict(raised["admin_override"])
        expired["expires_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        active = ieh.admin_override_active(expired)
        gate(results, "burst_override_expires", active is None, {"expired_payload_expires_at": expired["expires_at"], "active": active})

        # Kill switch hold
        app.dashboard_inbound_plan_update({"kill_switch": True}, ctx)
        held = app.process_postmark_inbound(
            _payload(f"d3p-{stamp}-4", address, "d3cand4@example.com", [_att("c4.pdf", _pdf("C4", "d3cand4@example.com"))]),
            quarantine_store=store,
        )
        cleanup["inbound_ids"].append(held.get("inbound_id"))
        gate(
            results,
            "tenant_kill_switch_waiting_budget",
            held.get("durable") is True
            and held.get("status") == "waiting_budget"
            and held.get("quota_code") == "tenant_kill_switch",
            held,
        )
        app.dashboard_inbound_plan_update({"kill_switch": False}, ctx)
        app.dashboard_inbound_admin_override_clear(ctx)

        # Tenant isolation — external cannot create/use
        try:
            app.dashboard_intake_create({"label": "x"}, _ctx("ACMECORP"))
            ext_ok = False
            ext_detail = "unexpected_success"
        except Exception as exc:
            detail = getattr(exc, "detail", {})
            ext_ok = getattr(exc, "status_code", None) in {403, 404} or (
                isinstance(detail, dict) and detail.get("error") in {"inbound_tenant_not_allowlisted", "inbound_feature_unavailable", "company_not_found"}
            )
            ext_detail = detail if isinstance(detail, dict) else str(exc)
        gate(results, "tenant_isolation_external_denied", ext_ok, ext_detail)

        # Postmark env mismatch fail-closed via live webhook
        secret = app.inbound_postmark_secret()
        mismatch = httpx.post(
            f"http://127.0.0.1:8010/webhook/postmark/inbound?token={secret}",
            json=_payload(f"d3p-{stamp}-env", address, "x@example.com", []),
            headers={"X-Wathefni-Inbound-Env": "staging"},
            timeout=30.0,
        )
        pin_ok = httpx.post(
            f"http://127.0.0.1:8010/webhook/postmark/inbound?token={secret}",
            json=_payload(f"d3p-{stamp}-pin", address, "pin@example.com", [_att("p.pdf", _pdf("Pin", "pin@example.com"))]),
            headers={},  # relies on ENV_PIN=production
            timeout=30.0,
        )
        if pin_ok.status_code == 200:
            try:
                cleanup["inbound_ids"].append(pin_ok.json().get("inbound_id"))
            except Exception:
                pass
        gate(
            results,
            "postmark_env_mismatch_fail_closed",
            mismatch.status_code == 401
            and (mismatch.json().get("detail") or {}).get("error") == "inbound_env_mismatch"
            and pin_ok.status_code == 200
            and pin_ok.json().get("durable") is True,
            {"mismatch": mismatch.status_code, "mismatch_body": mismatch.json(), "pin_status": pin_ok.status_code, "pin_durable": (pin_ok.json() or {}).get("durable")},
        )

        # Outage dead-letter + replay
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO intake_processing_jobs
                      (company_code, job_type, subject_type, subject_id, priority, status,
                       available_at, max_attempts, idempotency_key, payload,
                       last_error_code, last_error_detail)
                    VALUES ('WATHEFNI','malware_scan','intake_document',%s,100,'dead_letter',now(),5,%s,%s,
                            'scanner_unavailable','clamav down d3 proof')
                    RETURNING job_id::text AS job_id
                    """,
                    (str(uuid.uuid4()), f"d3-outage-{stamp}", Json({"document_id": str(uuid.uuid4()), "marker": MARKER})),
                )
                dead_id = cur.fetchone()["job_id"]
                cleanup["job_ids"].append(dead_id)
                listed = ieh.list_outage_dead_letters(cur, company_code="WATHEFNI", limit=50)
            conn.commit()
        replayed = ingress.replay_dead_letter(db_connect=app.db_connect, company_code="WATHEFNI", job_id=dead_id, actor="d3_prod_outage_proof")
        gate(
            results,
            "outage_dead_letter_replay",
            any(r["job_id"] == dead_id for r in listed) and replayed.get("status") == "pending",
            {"dead_id": dead_id, "listed": True, "replayed": replayed},
        )

        # Retention dry-run + opt-in execute (synthetic aged infected decision)
        policy = retention.policy_from_env("WATHEFNI", {
            **dict(os.environ),
            "WATHEFNI_INTAKE_RETENTION_POLICY_VERSION": f"d3-prod-{stamp}",
            "WATHEFNI_INTAKE_RETENTION_CLEAN_DAYS": "1",
            "WATHEFNI_INTAKE_RETENTION_NONCLEAN_DAYS": "1",
            "WATHEFNI_INTAKE_RETENTION_RESOLVED_REVIEW_DAYS": "1",
            "WATHEFNI_INTAKE_RETENTION_WITHDRAWN_HELD_DAYS": "1",
            "WATHEFNI_INTAKE_RETENTION_AUDIT_YEARS": "1",
            "WATHEFNI_INTAKE_RETENTION_CORRECTION_AUDIT_YEARS": "1",
            "WATHEFNI_INTAKE_SCAN_REUSE_HOURS": "1",
            "WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS": "60",
        })
        storage = LocalVolumeQuarantineStorage(app.durable_email_ingress_config().quarantine_root)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                retention.activate_policy(cur, policy, actor="d3_prod_proof")
                dry = retention.execute_cleanup(cur, company_code="WATHEFNI", storage=storage, actor="d3_prod_proof", dry_run=True, limit=20)
                cur.execute(
                    """
                    SELECT document_id::text AS document_id, inbound_id::text AS inbound_id,
                           attachment_ordinal, content_sha256, quarantine_key
                    FROM intake_documents
                    WHERE company_code='WATHEFNI' AND quarantine_key IS NOT NULL
                      AND inbound_id = ANY(%s::uuid[])
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    ([i for i in cleanup["inbound_ids"] if i],),
                )
                doc = cur.fetchone()
            conn.commit()
        gate(results, "retention_dry_run", dry.get("dry_run") is not False and "eligible" in dry, {"eligible_count": dry.get("eligible_count"), "blocked": dry.get("blocked_counts")})

        executed: dict[str, Any] = {}
        if doc:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    old = datetime.now(UTC) - timedelta(days=30)
                    cur.execute(
                        """
                        INSERT INTO inbound_attachment_scan_decisions(
                          company_code, inbound_id, intake_document_id, attachment_ordinal,
                          content_sha256, scanner_policy_version, attempt_no, state,
                          scanner_engine, scan_started_at, scan_completed_at, result,
                          failure_reason, quarantine_object_ref, actor_service_identity, evidence)
                        VALUES ('WATHEFNI',%s,%s,%s,%s,%s,1,'infected','d3_prod',%s,%s,'infected','eicar_sim',%s,'d3_prod',%s)
                        ON CONFLICT (company_code, intake_document_id, attempt_no) DO UPDATE
                          SET state='infected', scan_completed_at=EXCLUDED.scan_completed_at
                        """,
                        (
                            doc["inbound_id"],
                            doc["document_id"],
                            doc["attachment_ordinal"],
                            doc["content_sha256"],
                            f"d3-prod-{stamp}",
                            old,
                            old,
                            doc["quarantine_key"],
                            Json({"marker": MARKER}),
                        ),
                    )
                    executed = retention.execute_cleanup(
                        cur, company_code="WATHEFNI", storage=storage, actor="d3_prod_retention_execute", dry_run=False, limit=20
                    )
                conn.commit()
            gate(results, "retention_opt_in_execute", int(executed.get("deleted_count") or 0) >= 1, executed)
        else:
            gate(results, "retention_opt_in_execute", False, "no_proof_document")

        # retention execute flag remains off at platform level
        gate(results, "retention_execute_flag_off", ieh.retention_execute_enabled() is False, {"env": os.environ.get("WATHEFNI_INTAKE_RETENTION_EXECUTE")})

        # Address create race → 409
        try:
            app.dashboard_intake_create({"local_part": local_part}, ctx)
            dup_ok = False
            dup_detail = "unexpected_success"
        except Exception as exc:
            detail = getattr(exc, "detail", {})
            dup_ok = getattr(exc, "status_code", None) == 409 and isinstance(detail, dict) and detail.get("error") == "address_taken"
            dup_detail = detail
        gate(results, "address_create_race_409", dup_ok, dup_detail)

        rotated = app.dashboard_intake_rotate(intake_id, ctx)
        cleanup["intake_ids"].append(rotated["address"]["intake_id"])
        gate(results, "address_rotate", rotated.get("ok") and rotated["previous"]["status"] == "disabled", {"previous": rotated["previous"]["intake_id"], "new": rotated["address"]["intake_id"]})

        # Usage visibility
        usage = app.dashboard_inbound_usage(ctx)
        gate(
            results,
            "usage_visibility",
            usage.get("usage", {}).get("never_reject_for_volume") is True and usage.get("feature", {}).get("mailbox_sync_enabled") is False,
            {"plan": usage.get("usage", {}).get("plan"), "limits": usage.get("usage", {}).get("effective_limits")},
        )

        # Audit presence (best-effort query of recent admin actions)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT action_type, count(*)::int AS n
                    FROM action_results
                    WHERE company_code='WATHEFNI'
                      AND created_at >= now() - interval '2 hours'
                      AND action_type = ANY(%s)
                    GROUP BY action_type
                    """,
                    (
                        [
                            "inbound_admin_override_raised",
                            "inbound_admin_override_cleared",
                            "inbound_plan_updated",
                            "inbound_tenant_kill_switch",
                            "intake_address_created",
                            "intake_address_rotated",
                            "inbound_outage_replay",
                            "inbound_postmark_env_rejected",
                        ],
                    ),
                )
                audit_rows = {r["action_type"]: r["n"] for r in cur.fetchall()}
            conn.commit()
        needed = {
            "inbound_admin_override_raised",
            "inbound_admin_override_cleared",
            "inbound_plan_updated",
            "inbound_tenant_kill_switch",
            "intake_address_created",
            "intake_address_rotated",
        }
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*)::int AS n FROM action_results
                    WHERE action_type='inbound_postmark_env_rejected'
                      AND created_at >= now() - interval '2 hours'
                    """
                )
                env_audit = int((cur.fetchone() or {}).get("n") or 0)
            conn.commit()
        gate(
            results,
            "audit_logs_present",
            needed.issubset(set(audit_rows)) and env_audit >= 1,
            {"wathefni_actions": audit_rows, "env_reject_count": env_audit},
        )

    except Exception as exc:
        results["fatal"] = {"error": str(exc), "trace": traceback.format_exc()}
        print("FATAL", exc)
        print(traceback.format_exc())
    finally:
        # Cleanup: disable proof addresses, remove proof jobs/messages, restore settings
        try:
            for iid in cleanup.get("intake_ids") or []:
                try:
                    app.dashboard_intake_disable(iid, ctx)
                except Exception:
                    pass
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT set_config('wathefni.authority_cleanup','synthetic',true)")
                    ids = [i for i in (cleanup.get("inbound_ids") or []) if i]
                    if ids:
                        cur.execute("DELETE FROM intake_processing_jobs WHERE company_code='WATHEFNI' AND subject_id = ANY(%s::text[])", (ids,))
                        cur.execute(
                            """
                            DELETE FROM intake_processing_jobs
                            WHERE company_code='WATHEFNI'
                              AND (idempotency_key LIKE %s OR last_error_detail LIKE %s OR payload->>'marker'=%s)
                            """,
                            (f"d3-outage-{stamp}%", "%d3 proof%", MARKER),
                        )
                        cur.execute("DELETE FROM intake_documents WHERE company_code='WATHEFNI' AND inbound_id = ANY(%s::uuid[])", (ids,))
                        cur.execute("DELETE FROM intake_submissions WHERE company_code='WATHEFNI' AND inbound_id = ANY(%s::uuid[])", (ids,))
                        cur.execute("DELETE FROM inbound_messages WHERE company_code='WATHEFNI' AND inbound_id = ANY(%s::uuid[])", (ids,))
                    for jid in cleanup.get("job_ids") or []:
                        cur.execute("DELETE FROM intake_processing_job_events WHERE job_id=%s", (jid,))
                        cur.execute("DELETE FROM intake_processing_jobs WHERE job_id=%s", (jid,))
                    # disable leftover proof addresses by label
                    cur.execute(
                        """
                        UPDATE intake_addresses SET status='disabled', updated_at=now()
                        WHERE company_code='WATHEFNI' AND status='active' AND coalesce(label,'') LIKE %s
                        """,
                        (f"%{MARKER}%",),
                    )
                    # restore enterprise settings to safe internal defaults for WATHEFNI continuous freeze
                    if previous_enterprise is None:
                        app.set_company_setting(
                            "WATHEFNI",
                            "inbound_enterprise",
                            {"plan": "internal", "kill_switch": False},
                        )
                    else:
                        restored = dict(previous_enterprise) if isinstance(previous_enterprise, dict) else {"plan": "internal"}
                        restored["kill_switch"] = False
                        restored.pop("admin_override", None)
                        app.set_company_setting("WATHEFNI", "inbound_enterprise", restored)
                    cleanup["settings_restored"] = True
                    # clear proof retention assignment so continuous freeze keeps prior policy
                    cur.execute(
                        "DELETE FROM inbound_retention_policy_assignments WHERE company_code='WATHEFNI' AND policy_version LIKE %s",
                        (f"d3-prod-%",),
                    )
                    cur.execute(
                        "DELETE FROM inbound_retention_policies WHERE company_code='WATHEFNI' AND policy_version LIKE %s",
                        (f"d3-prod-%",),
                    )
                conn.commit()
        except Exception as exc:
            cleanup["error"] = str(exc)
            print("CLEANUP_ERROR", exc)
        results["cleanup"] = cleanup
        # continuous freeze: ensure we didn't leave kill switch on
        settings = app.get_company_settings("WATHEFNI") or {}
        ent = settings.get("inbound_enterprise") if isinstance(settings.get("inbound_enterprise"), dict) else {}
        results["post_cleanup_kill_switch"] = bool(ent.get("kill_switch"))

    OUT.write_text(json.dumps(results, indent=2, default=str) + "\n")
    failed = [k for k, v in results.items() if isinstance(v, dict) and "ok" in v and not v["ok"]]
    print(json.dumps({"failed": failed, "out": str(OUT)}, indent=2))
    return 1 if failed or results.get("fatal") else 0


if __name__ == "__main__":
    raise SystemExit(main())
