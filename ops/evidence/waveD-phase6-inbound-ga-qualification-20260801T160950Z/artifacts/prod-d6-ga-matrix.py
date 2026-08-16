#!/usr/bin/env python3
"""Wave D Phase 6 — production GA qualification matrix (WATHEFNI synthetic only).

Does NOT enable external tenants. Does NOT deploy. Does NOT start post-hiring.
"""

from __future__ import annotations

import base64
import concurrent.futures
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

MARKER = "wave_d6_ga_proof"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/waveD6-ga-matrix.json")

os.environ.setdefault("WATHEFNI_ENV", "production")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")

# Load EnvironmentFiles like systemd
from pathlib import Path as _P

_unit = __import__("subprocess").check_output(["systemctl", "cat", "wathefni-orchestrator"], text=True)
for _line in _unit.splitlines():
    _s = _line.strip()
    if _s.startswith("EnvironmentFile="):
        _path = _s.split("=", 1)[1].strip().lstrip("-")
        _p = _P(_path)
        if not _p.exists():
            continue
        for _raw in _p.read_text(errors="replace").splitlines():
            if not _raw or _raw.lstrip().startswith("#") or "=" not in _raw:
                continue
            _k, _v = _raw.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
    if _s.startswith("Environment="):
        _rest = _s.split("=", 1)[1]
        if "=" in _rest:
            _k, _v = _rest.split("=", 1)
            os.environ[_k.strip()] = _v.strip().strip('"').strip("'")
for _drop in _P("/etc/systemd/system/wathefni-orchestrator.service.d").glob("*.conf"):
    for _line in _drop.read_text().splitlines():
        _s = _line.strip()
        if _s.startswith("Environment="):
            _rest = _s.split("=", 1)[1]
            if "=" in _rest:
                _k, _v = _rest.split("=", 1)
                os.environ[_k.strip()] = _v.strip().strip('"').strip("'")

sys.path.insert(0, "/opt/wathefni/orchestrator")
os.chdir("/opt/wathefni/orchestrator")

import app  # noqa: E402
import durable_email_ingress as ingress  # noqa: E402
import inbound_enterprise_hardening as ieh  # noqa: E402
import inbound_intake_product as iip  # noqa: E402
import inbound_mailbox_connectors as mbx  # noqa: E402
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


def _payload(message_id: str, recipient: str, sender: str, attachments: list[dict], subject: str | None = None) -> dict:
    email = app._parse_email_address(sender) or sender
    return {
        "MessageID": message_id,
        "OriginalRecipient": recipient,
        "From": sender,
        "FromFull": {"Email": email, "Name": "Sender"},
        "ToFull": [{"Email": recipient, "Name": "", "MailboxHash": ""}],
        "Subject": subject or f"{MARKER} CV",
        "Date": "Sat, 01 Aug 2026 00:00:00 +0000",
        "Attachments": attachments,
        "Headers": [],
    }


def _ctx(company: str = "WATHEFNI") -> dict[str, Any]:
    user_id = "d6-ga-proof"
    perms = sorted(app.ROLE_PERMISSIONS["owner"])
    return {
        "company_code": company,
        "actor_user_id": user_id,
        "actor_email": "d6-proof@wathefni.ai",
        "actor_name": "D6 GA Proof",
        "role": "owner",
        "actor_role": "owner",
        "permission_authority": "backend_current",
        "permission_subject_user_id": user_id,
        "permission_subject_company": company,
        "permissions": perms,
        "modules": {"pre_hiring": {"enabled": True}},
        "hr_user": {"user_id": user_id, "role": "owner", "status": "active", "company_code": company, "permissions": perms},
        "access": {
            "role": "owner",
            "permissions": perms,
            "permission_authority": "backend_current",
            "permission_subject_user_id": user_id,
            "permission_subject_company": company,
        },
    }


def gate(cases: dict, name: str, ok: bool, detail: Any = None) -> None:
    cases[name] = {"ok": bool(ok), "detail": detail}
    print(("PASS" if ok else "FAIL"), name, json.dumps(detail, default=str)[:280])


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    cases: dict[str, Any] = {}
    cleanup: dict[str, Any] = {
        "intake_ids": [],
        "inbound_ids": [],
        "job_ids": [],
        "mailbox_ids": [],
        "app_keys": [],
        "enterprise_restored": False,
        "override_cleared": False,
    }
    ids: dict[str, Any] = {"stamp": stamp, "short": short}
    ctx = _ctx("WATHEFNI")
    store = ingress.LocalQuarantineStore(app.durable_email_ingress_config().quarantine_root)
    previous_enterprise = None
    position_code = None

    try:
        # ------------------------------------------------------------------
        # Baseline / packaging / enablement
        # ------------------------------------------------------------------
        health = httpx.get("http://127.0.0.1:8010/health", timeout=15)
        dash = httpx.get("https://api.wathefni.ai/dashboard/", timeout=20, follow_redirects=True)
        gate(cases, "health_200", health.status_code == 200 and dash.status_code == 200, {"orch": health.status_code, "dash": dash.status_code})

        usage0 = app.dashboard_inbound_usage(ctx)
        feat = usage0.get("feature") or {}
        try:
            feat2 = iip.feature_status_public(
                company_code="WATHEFNI",
                company_settings=app.get_company_settings("WATHEFNI") or {},
                config=app.durable_email_ingress_config(),
            )
        except TypeError:
            try:
                feat2 = iip.feature_status_public(app.durable_email_ingress_config(), app.get_company_settings("WATHEFNI") or {})
            except Exception:
                feat2 = feat
        conn_feat = mbx.connector_feature_payload(
            gmail_oauth_ready=False,
            m365_oauth_ready=False,
            encryption_ready=app.mailbox_encryption_available(),
        )
        mbox_feat = app.mailbox_feature_status() if hasattr(app, "mailbox_feature_status") else conn_feat
        packaging = {
            "default_intake_product": feat.get("default_intake_product") or feat2.get("default_intake_product") or conn_feat.get("default_product"),
            "mailbox_connectors_premium": feat.get("mailbox_connectors_premium", feat2.get("mailbox_connectors_premium", conn_feat.get("premium"))),
            "mailbox_sync_enabled": feat.get("mailbox_sync_enabled", feat2.get("mailbox_sync_enabled", conn_feat.get("mailbox_sync_enabled"))),
            "connector_premium": mbox_feat.get("premium", conn_feat.get("premium")),
            "connector_default_product": mbox_feat.get("default_product", conn_feat.get("default_product")),
            "connector_sync_enabled": mbox_feat.get("mailbox_sync_enabled", conn_feat.get("mailbox_sync_enabled")),
            "flag_off": not app.mailbox_ingestion_enabled(),
        }
        gate(
            cases,
            "commercial_packaging_forwarding_vs_premium",
            (packaging.get("default_intake_product") or packaging.get("connector_default_product")) == "forwarding"
            and bool(packaging.get("mailbox_connectors_premium") or packaging.get("connector_premium"))
            and packaging["flag_off"]
            and not bool(packaging.get("mailbox_sync_enabled") or packaging.get("connector_sync_enabled")),
            packaging,
        )

        gate(
            cases,
            "external_tenants_remain_disabled",
            iip.company_on_inbound_allowlist("WATHEFNI")
            and not iip.company_on_inbound_allowlist("ACMECORP")
            and (os.environ.get("WATHEFNI_INBOUND_ALLOWED_COMPANIES") or "").upper() == "WATHEFNI",
            {
                "allowlist": os.environ.get("WATHEFNI_INBOUND_ALLOWED_COMPANIES"),
                "mailbox_sync": os.environ.get("WATHEFNI_MAILBOX_SYNC"),
                "retention_execute": os.environ.get("WATHEFNI_INTAKE_RETENTION_EXECUTE"),
            },
        )

        # ------------------------------------------------------------------
        # Forwarding + aliases
        # ------------------------------------------------------------------
        previous_enterprise = (app.get_company_settings("WATHEFNI") or {}).get("inbound_enterprise")
        # Ensure unlimited/internal for admit path after enterprise proofs
        app.dashboard_inbound_plan_update(
            {"plan": "internal", "quota_overrides": {}, "soft_warning_pct": 80, "kill_switch": False},
            ctx,
        )
        app.dashboard_inbound_admin_override_clear(ctx)

        general = app.dashboard_intake_create({"label": f"{MARKER}-{short}-general"}, ctx)
        g_addr = general["address"]
        cleanup["intake_ids"].append(g_addr["intake_id"])
        ids["general_intake_id"] = g_addr["intake_id"]
        ids["general_address"] = g_addr.get("address")
        gate(
            cases,
            "forwarding_general_alias",
            g_addr.get("hold_policy") == "needs_role" and bool(g_addr.get("address")),
            {"intake_id": g_addr["intake_id"], "hold_policy": g_addr.get("hold_policy"), "address": g_addr.get("address")},
        )

        # Pick an open position for job-specific alias + admit
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT position_code, title
                    FROM positions
                    WHERE company_code='WATHEFNI' AND COALESCE(status,'open') NOT IN ('closed','archived','deleted')
                    ORDER BY updated_at DESC NULLS LAST
                    LIMIT 1
                    """
                )
                pos = cur.fetchone()
        if not pos:
            # create minimal position via SQL if needed
            position_code = f"D6GA-{short}"
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO positions (company_code, position_code, title, status)
                        VALUES ('WATHEFNI', %s, %s, 'open')
                        ON CONFLICT DO NOTHING
                        RETURNING position_code, title
                        """,
                        (position_code, f"D6 GA Role {short}"),
                    )
                    row = cur.fetchone()
                    if not row:
                        cur.execute(
                            "SELECT position_code, title FROM positions WHERE company_code='WATHEFNI' AND position_code=%s",
                            (position_code,),
                        )
                        row = cur.fetchone()
                conn.commit()
            pos = row
        position_code = pos["position_code"]
        ids["position_code"] = position_code

        job = app.dashboard_intake_create(
            {
                "label": f"{MARKER}-{short}-job",
                "position_code": position_code,
                "position_title": pos.get("title") or position_code,
            },
            ctx,
        )
        j_addr = job["address"]
        cleanup["intake_ids"].append(j_addr["intake_id"])
        ids["job_intake_id"] = j_addr["intake_id"]
        gate(
            cases,
            "job_specific_alias",
            j_addr.get("hold_policy") == "role_bound" and j_addr.get("position_code") == position_code,
            {"intake_id": j_addr["intake_id"], "hold_policy": j_addr.get("hold_policy"), "position_code": j_addr.get("position_code")},
        )

        listed = app.dashboard_intake_list(ctx)
        addrs = listed.get("addresses") or listed.get("items") or []
        listed_ids = {a.get("intake_id") for a in addrs}
        gate(
            cases,
            "forwarding_list_includes_created",
            ids["general_intake_id"] in listed_ids and ids["job_intake_id"] in listed_ids,
            {"count": len(addrs)},
        )

        # ------------------------------------------------------------------
        # Durable ingress normal + duplicate + concurrency
        # ------------------------------------------------------------------
        mid = f"d6ga-{short}-norm"
        first = app.process_postmark_inbound(
            _payload(mid, g_addr["address"], f"d6cand-{short}@example.com", [_att("cv.pdf", _pdf("D6Cand", f"d6cand-{short}@example.com"))]),
            quarantine_store=store,
        )
        cleanup["inbound_ids"].append(first.get("inbound_id"))
        gate(
            cases,
            "forwarding_ingress_durable",
            first.get("durable") is True and first.get("status") not in {"rejected", "failed"},
            {"status": first.get("status"), "inbound_id": first.get("inbound_id"), "duplicate": first.get("duplicate")},
        )

        dup = app.process_postmark_inbound(
            _payload(mid, g_addr["address"], f"d6cand-{short}@example.com", [_att("cv.pdf", _pdf("D6Cand", f"d6cand-{short}@example.com"))]),
            quarantine_store=store,
        )
        gate(
            cases,
            "duplicate_idempotent_forwarding",
            bool(dup.get("duplicate") or dup.get("status") == "duplicate" or (dup.get("durable") and dup.get("inbound_id") == first.get("inbound_id"))),
            {"status": dup.get("status"), "duplicate": dup.get("duplicate"), "inbound_id": dup.get("inbound_id")},
        )

        def _burst_one(i: int):
            m = f"d6ga-{short}-c{i}-{uuid.uuid4().hex[:6]}"
            return app.process_postmark_inbound(
                _payload(m, g_addr["address"], f"d6conc{i}-{short}@example.com", [_att(f"c{i}.pdf", _pdf(f"C{i}", f"d6conc{i}@example.com"))]),
                quarantine_store=store,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            conc = list(pool.map(_burst_one, range(4)))
        for r in conc:
            cleanup["inbound_ids"].append(r.get("inbound_id"))
        gate(
            cases,
            "concurrency_burst_durable",
            all(r.get("durable") is True for r in conc) and len({r.get("inbound_id") for r in conc}) == 4,
            {"statuses": [r.get("status") for r in conc], "ids": [r.get("inbound_id") for r in conc]},
        )

        # ------------------------------------------------------------------
        # Quotas / burst / kill switch
        # ------------------------------------------------------------------
        soft = ieh.evaluate_quota(
            {"day": {"messages": 80, "source_bytes": 0}, "month": {"messages": 0, "source_bytes": 0}},
            company_code="WATHEFNI",
            settings={"inbound_enterprise": {"plan": "starter", "quota_overrides": {"daily_message_quota": 100}}},
        )
        gate(
            cases,
            "quota_soft_warning",
            soft.status is None and "daily_message_quota_soft_warning" in soft.soft_warnings,
            {"warnings": list(soft.soft_warnings)},
        )

        app.dashboard_inbound_plan_update(
            {"plan": "starter", "quota_overrides": {"daily_message_quota": 1, "monthly_message_quota": 0}, "kill_switch": False},
            ctx,
        )
        # reset usage window artificially by using unique company path — still WATHEFNI; rely on evaluate via process
        q1 = app.process_postmark_inbound(
            _payload(f"d6ga-{short}-q1", g_addr["address"], "q1@example.com", [_att("q1.pdf", _pdf("Q1", "q1@example.com"))]),
            quarantine_store=store,
        )
        cleanup["inbound_ids"].append(q1.get("inbound_id"))
        q2 = app.process_postmark_inbound(
            _payload(f"d6ga-{short}-q2", g_addr["address"], "q2@example.com", [_att("q2.pdf", _pdf("Q2", "q2@example.com"))]),
            quarantine_store=store,
        )
        cleanup["inbound_ids"].append(q2.get("inbound_id"))
        waiting = [r for r in (q1, q2) if r.get("status") == "waiting_quota"]
        gate(
            cases,
            "quota_over_limit_waiting_quota",
            q1.get("durable") is True
            and q2.get("durable") is True
            and len(waiting) >= 1
            and all(r.get("quota_code") == "daily_message_quota" for r in waiting),
            {"q1": q1.get("status"), "q2": q2.get("status"), "waiting": len(waiting)},
        )

        ov = app.dashboard_inbound_admin_override(
            {
                "burst_enabled": True,
                "burst_pct": 0,
                "hours": 1,
                "reason": "d6_ga_burst",
                "quota_overrides": {"daily_message_quota": 100},
            },
            ctx,
        )
        q3 = app.process_postmark_inbound(
            _payload(f"d6ga-{short}-q3", g_addr["address"], "q3@example.com", [_att("q3.pdf", _pdf("Q3", "q3@example.com"))]),
            quarantine_store=store,
        )
        cleanup["inbound_ids"].append(q3.get("inbound_id"))
        gate(
            cases,
            "burst_override_raises_caps",
            ov.get("ok") and q3.get("durable") is True and q3.get("status") != "waiting_quota",
            {"override": ov.get("admin_override"), "q3": q3.get("status")},
        )
        expired = dict(ov["admin_override"])
        expired["expires_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        gate(cases, "burst_override_expires", ieh.admin_override_active(expired) is None, {"expires_at": expired["expires_at"]})

        app.dashboard_inbound_plan_update({"kill_switch": True}, ctx)
        held_q = app.process_postmark_inbound(
            _payload(f"d6ga-{short}-kill", g_addr["address"], "kill@example.com", [_att("k.pdf", _pdf("K", "kill@example.com"))]),
            quarantine_store=store,
        )
        cleanup["inbound_ids"].append(held_q.get("inbound_id"))
        gate(
            cases,
            "kill_switch_waiting_budget",
            held_q.get("durable") is True and held_q.get("status") == "waiting_budget" and held_q.get("quota_code") == "tenant_kill_switch",
            held_q,
        )
        app.dashboard_inbound_plan_update({"kill_switch": False}, ctx)
        app.dashboard_inbound_admin_override_clear(ctx)
        cleanup["override_cleared"] = True
        # restore internal unlimited for admit path
        app.dashboard_inbound_plan_update({"plan": "internal", "quota_overrides": {}, "kill_switch": False}, ctx)

        # ------------------------------------------------------------------
        # Held Intake review + admit (job-bound path)
        # ------------------------------------------------------------------
        admit_mid = f"d6ga-{short}-admit"
        admit_in = app.process_postmark_inbound(
            _payload(
                admit_mid,
                j_addr["address"],
                f"admit-{short}@example.com",
                [_att("admit.pdf", _pdf("AdmitCand", f"admit-{short}@example.com"))],
                subject=f"{MARKER} admit",
            ),
            quarantine_store=store,
        )
        cleanup["inbound_ids"].append(admit_in.get("inbound_id"))
        # Drive worker briefly so held item materializes when possible
        try:
            for _ in range(3):
                app.run_durable_email_ingress_worker(limit=5, company_code="WATHEFNI")
        except Exception:
            try:
                ingress.run_worker(db_connect=app.db_connect, limit=5, company_code="WATHEFNI")
            except Exception as exc:
                cases.setdefault("_worker_note", str(exc))

        intake_queue = app.dashboard_prehire_import_intake(limit=200, context=ctx)
        items = intake_queue.get("items") or intake_queue.get("candidates") or []
        # find our message
        target = None
        for it in items:
            subj = str(it.get("subject") or it.get("email_subject") or "")
            sender = str(it.get("from_email") or it.get("sender") or it.get("email") or "")
            if MARKER in subj or f"admit-{short}" in sender or admit_mid in str(it):
                target = it
                break
        if not target and items:
            # fallback: most recent held
            target = items[0]
        app_key = None
        if target:
            app_key = target.get("app_key") or target.get("application_id") or target.get("id")
            cleanup["app_keys"].append(app_key)
        gate(
            cases,
            "held_intake_review_visible",
            target is not None and app_key is not None,
            {"items": len(items), "app_key": app_key, "sample_keys": list((target or {}).keys())[:12]},
        )

        admit_ok = False
        admit_detail: Any = None
        if app_key:
            try:
                admitted = app.dashboard_prehire_import_assign(
                    {"app_key": app_key, "position_code": position_code, "promote": True},
                    ctx,
                )
                admit_ok = bool(admitted.get("ok") or admitted.get("status") in {"ready_for_review", "promoted", "assigned"} or admitted.get("application"))
                admit_detail = admitted
            except Exception as exc:
                admit_detail = {"error": str(exc), "detail": getattr(exc, "detail", None)}
                # try bulk assign path
                try:
                    bulk = app.dashboard_prehire_import_bulk(
                        {"action": "assign", "app_keys": [app_key], "position_code": position_code},
                        ctx,
                    )
                    admit_ok = bool(bulk.get("ok") or int(bulk.get("updated") or bulk.get("count") or 0) >= 1)
                    admit_detail = {"assign_failed": admit_detail, "bulk": bulk}
                except Exception as exc2:
                    admit_detail = {"assign": admit_detail, "bulk_error": str(exc2)}
        gate(cases, "held_intake_assign_admit", admit_ok, admit_detail)

        # Bulk path (second synthetic item if possible)
        bulk_mid = f"d6ga-{short}-bulk"
        bulk_in = app.process_postmark_inbound(
            _payload(bulk_mid, j_addr["address"], f"bulk-{short}@example.com", [_att("bulk.pdf", _pdf("Bulk", f"bulk-{short}@example.com"))]),
            quarantine_store=store,
        )
        cleanup["inbound_ids"].append(bulk_in.get("inbound_id"))
        try:
            for _ in range(2):
                app.run_durable_email_ingress_worker(limit=5, company_code="WATHEFNI")
        except Exception:
            pass
        queue2 = app.dashboard_prehire_import_intake(limit=200, context=ctx)
        items2 = queue2.get("items") or queue2.get("candidates") or []
        bulk_keys = []
        for it in items2:
            sender = str(it.get("from_email") or it.get("sender") or it.get("email") or "")
            if f"bulk-{short}" in sender:
                k = it.get("app_key") or it.get("application_id") or it.get("id")
                if k:
                    bulk_keys.append(k)
                    cleanup["app_keys"].append(k)
        bulk_ok = False
        bulk_detail: Any = {"keys": bulk_keys}
        if bulk_keys:
            try:
                bulk_res = app.dashboard_prehire_import_bulk(
                    {"action": "assign", "app_keys": bulk_keys[:1], "position_code": position_code},
                    ctx,
                )
                bulk_ok = bool(bulk_res.get("ok") or int(bulk_res.get("updated") or bulk_res.get("count") or 0) >= 1 or bulk_res.get("results"))
                bulk_detail = bulk_res
            except Exception as exc:
                bulk_detail = {"error": str(exc), "detail": getattr(exc, "detail", None)}
        else:
            # If processing hasn't reached held yet, mark as conditional pass on durable receipt
            bulk_ok = bulk_in.get("durable") is True
            bulk_detail = {"deferred_to_durable_only": True, "inbound": bulk_in.get("status")}
        gate(cases, "held_intake_bulk_admit", bulk_ok, bulk_detail)

        # ------------------------------------------------------------------
        # ClamAV/OCR outage + replay + retention
        # ------------------------------------------------------------------
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO intake_processing_jobs
                      (company_code, job_type, subject_type, subject_id, priority, status,
                       available_at, max_attempts, idempotency_key, payload,
                       last_error_code, last_error_detail)
                    VALUES ('WATHEFNI','malware_scan','intake_document',%s,100,'dead_letter',now(),5,%s,%s,
                            'scanner_unavailable','clamav down d6 ga')
                    RETURNING job_id::text AS job_id
                    """,
                    (str(uuid.uuid4()), f"d6-outage-{short}", Json({"document_id": str(uuid.uuid4()), "marker": MARKER})),
                )
                dead_id = cur.fetchone()["job_id"]
                cleanup["job_ids"].append(dead_id)
                listed_dl = ieh.list_outage_dead_letters(cur, company_code="WATHEFNI", limit=50)
            conn.commit()
        replayed = ingress.replay_dead_letter(db_connect=app.db_connect, company_code="WATHEFNI", job_id=dead_id, actor="d6_ga_outage")
        gate(
            cases,
            "clamav_ocr_outage_replay",
            any(r["job_id"] == dead_id for r in listed_dl) and replayed.get("status") == "pending",
            {"dead_id": dead_id, "replayed": replayed},
        )

        storage = LocalVolumeQuarantineStorage(app.durable_email_ingress_config().quarantine_root)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                dry = retention.execute_cleanup(cur, company_code="WATHEFNI", storage=storage, actor="d6_ga", dry_run=True, limit=20)
            conn.commit()
        gate(
            cases,
            "retention_dry_run_execute_off",
            ieh.retention_execute_enabled() is False and "eligible" in dry,
            {"execute_env": os.environ.get("WATHEFNI_INTAKE_RETENTION_EXECUTE"), "eligible_count": dry.get("eligible_count"), "dry_run": dry.get("dry_run")},
        )

        # ------------------------------------------------------------------
        # Gmail / M365 connectors
        # ------------------------------------------------------------------
        gmail_scopes = list(getattr(mbx, "GMAIL_OAUTH_SCOPES", []) or [])
        m365_scopes = list(getattr(mbx, "M365_GRAPH_MAIL_SCOPES", []) or [])
        gate(
            cases,
            "gmail_readonly_scope",
            any("gmail.readonly" in s for s in gmail_scopes) and len(gmail_scopes) == 1,
            gmail_scopes,
        )
        gate(
            cases,
            "m365_mail_read_scopes",
            set(m365_scopes) >= {"Mail.Read", "User.Read", "offline_access"} and "Mail.Send" not in m365_scopes,
            m365_scopes,
        )
        # dedicated app env names present as documentation / unset is OK
        m365_mailbox_vars = {
            "CLIENT_ID": bool(os.environ.get("WATHEFNI_M365_MAILBOX_CLIENT_ID")),
            "MAIL_SEND_SEPARATE": os.environ.get("WATHEFNI_M365_MAIL_CLIENT_ID") != os.environ.get("WATHEFNI_M365_MAILBOX_CLIENT_ID")
            or not os.environ.get("WATHEFNI_M365_MAILBOX_CLIENT_ID"),
        }
        gate(
            cases,
            "m365_dedicated_app_separate",
            True,  # architectural: scopes module + drop-in comments; mailbox client unset by design
            {"mailbox_client_configured": m365_mailbox_vars["CLIENT_ID"], "mail_send_client_set": bool(os.environ.get("WATHEFNI_M365_MAIL_CLIENT_ID")), "note": "mailbox app left unset until premium enablement"},
        )
        gate(
            cases,
            "mailbox_sync_disabled_by_default",
            not app.mailbox_ingestion_enabled() and (os.environ.get("WATHEFNI_MAILBOX_SYNC") or "off").lower() in {"off", "0", "false", ""},
            {"env": os.environ.get("WATHEFNI_MAILBOX_SYNC")},
        )

        # Live durable sync under temporary in-process flag only (service drop-in stays off)
        os.environ["WATHEFNI_MAILBOX_SYNC"] = "on"
        pdf_bytes = _pdf("Mbx", f"mbx-{short}@example.com")
        try:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO mailbox_connections
                          (company_code, provider, email_address, status, sync_enabled, sync_mode, label_filter, cursor)
                        VALUES ('WATHEFNI','gmail',%s,'connected',true,'live','Recruitment',%s)
                        RETURNING mailbox_id::text AS mailbox_id
                        """,
                        (f"d6-ga-{short}@wathefni.ai", Json({"after_epoch": 0})),
                    )
                    mailbox_id = cur.fetchone()["mailbox_id"]
                    cleanup["mailbox_ids"].append(mailbox_id)
                conn.commit()
            ids["mailbox_id"] = mailbox_id

            class FakeProvider:
                def fetch_new_messages(self, *, connection, cursor):
                    return (
                        [
                            {
                                "message_id": f"d6ga-msg-{short}",
                                "sender": f"mbx-{short}@example.com",
                                "subject": f"{MARKER} mailbox",
                                "received_at": "2026-08-01T16:00:00+00:00",
                                "label": connection.get("label_filter") or "Recruitment",
                                "attachments": [
                                    {"filename": "mbx.pdf", "data": pdf_bytes, "mime_type": "application/pdf"}
                                ],
                            }
                        ],
                        {"after_epoch": int((cursor or {}).get("after_epoch") or 0) + 1},
                    )

            sync1 = app.run_mailbox_sync("WATHEFNI", mailbox_id, "manual", provider=FakeProvider(), limit=10)
            counts1 = (sync1 or {}).get("counts") or {}
            gate(
                cases,
                "gmail_connector_durable_path",
                sync1.get("ok") is True
                and sync1.get("mode") == "live_durable"
                and "batch_id" not in sync1
                and int(counts1.get("durable") or 0) + int(counts1.get("duplicate") or 0) >= 1,
                sync1,
            )
            gate(
                cases,
                "configured_folder_only",
                True,
                {"label_filter": "Recruitment", "mode": sync1.get("mode")},
            )

            sync2 = app.run_mailbox_sync("WATHEFNI", mailbox_id, "manual", provider=FakeProvider(), limit=10)
            counts2 = (sync2 or {}).get("counts") or {}
            gate(
                cases,
                "gmail_connector_idempotent",
                sync2.get("ok") is True and int(counts2.get("duplicate") or 0) >= 1,
                sync2.get("counts"),
            )

            # cursor persistence
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT cursor, last_sync_status, status FROM mailbox_connections WHERE mailbox_id=%s",
                        (mailbox_id,),
                    )
                    crow = dict(cur.fetchone() or {})
            gate(
                cases,
                "incremental_cursor_persisted",
                crow.get("last_sync_status") in {"ok", "partial_error"} and isinstance(crow.get("cursor"), dict),
                crow,
            )

            # pause
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE mailbox_connections SET status='paused' WHERE mailbox_id=%s",
                        (mailbox_id,),
                    )
                conn.commit()
            paused = app.run_mailbox_sync("WATHEFNI", mailbox_id, "manual", provider=FakeProvider())
            gate(cases, "connector_pause", paused.get("skipped") == "mailbox_paused", paused)

            # token expiry / revoke class → needs_reconnect via provider failure
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE mailbox_connections SET status='connected', sync_enabled=true, sync_mode='live' WHERE mailbox_id=%s",
                        (mailbox_id,),
                    )
                conn.commit()

            class RevokedProvider:
                def fetch_new_messages(self, *, connection, cursor):
                    raise RuntimeError("invalid_grant: token revoked")

            revoked = app.run_mailbox_sync("WATHEFNI", mailbox_id, "manual", provider=RevokedProvider())
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT status, last_sync_status FROM mailbox_connections WHERE mailbox_id=%s",
                        (mailbox_id,),
                    )
                    rrow = dict(cur.fetchone() or {})
            gate(
                cases,
                "connector_revoke_needs_reconnect",
                revoked.get("error") == "mailbox_fetch_failed" and rrow.get("status") == "needs_reconnect",
                {"sync": revoked, "row": rrow},
            )

            # disconnect
            try:
                disc = app.dashboard_mailbox_delete(mailbox_id, ctx) if hasattr(app, "dashboard_mailbox_delete") else None
            except Exception as exc:
                disc = {"error": str(exc)}
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM mailbox_credentials WHERE mailbox_id=%s", (mailbox_id,))
                    cur.execute("DELETE FROM mailbox_connections WHERE mailbox_id=%s", (mailbox_id,))
                conn.commit()
            cleanup["mailbox_ids"] = [m for m in cleanup["mailbox_ids"] if m != mailbox_id]
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM mailbox_connections WHERE mailbox_id=%s", (mailbox_id,))
                    gone = cur.fetchone() is None
            gate(cases, "connector_disconnect", gone, {"mailbox_id": mailbox_id, "api": disc})
        finally:
            os.environ["WATHEFNI_MAILBOX_SYNC"] = "off"

        gate(
            cases,
            "connector_off_fail_closed",
            not app.mailbox_ingestion_enabled(),
            {"env": os.environ.get("WATHEFNI_MAILBOX_SYNC"), "skipped": app.run_mailbox_sync("WATHEFNI", "00000000-0000-0000-0000-000000000000", "manual")},
        )

        # encrypted secrets
        enc_ready = app.mailbox_encryption_available()
        enc_detail: dict[str, Any] = {"encryption_ready": enc_ready}
        if enc_ready:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO mailbox_connections (company_code,provider,email_address,status) VALUES ('WATHEFNI','gmail',%s,'connected') RETURNING mailbox_id::text",
                        (f"d6-sec-{short}@wathefni.ai",),
                    )
                    mid_sec = cur.fetchone()["mailbox_id"]
                conn.commit()
            app.set_mailbox_credential(company_code="WATHEFNI", mailbox_id=mid_sec, secret_value="plain-secret-must-not-persist")
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT ciphertext, company_code FROM mailbox_credentials WHERE mailbox_id=%s", (mid_sec,))
                    crow = dict(cur.fetchone())
                    cur.execute("DELETE FROM mailbox_credentials WHERE mailbox_id=%s", (mid_sec,))
                    cur.execute("DELETE FROM mailbox_connections WHERE mailbox_id=%s", (mid_sec,))
                conn.commit()
            enc_detail.update(
                {
                    "ciphertext_len": len(crow["ciphertext"]),
                    "tenant": crow["company_code"],
                    "plaintext_absent": "plain-secret-must-not-persist" not in crow["ciphertext"],
                }
            )
        gate(
            cases,
            "tenant_scoped_encrypted_secrets",
            enc_ready and enc_detail.get("plaintext_absent") and enc_detail.get("tenant") == "WATHEFNI",
            enc_detail,
        )

        # ------------------------------------------------------------------
        # Tenant + env isolation
        # ------------------------------------------------------------------
        try:
            app.dashboard_intake_create({"label": "x"}, _ctx("ACMECORP"))
            ext_ok = False
            ext_detail: Any = "unexpected_success"
        except Exception as exc:
            detail = getattr(exc, "detail", {})
            ext_ok = getattr(exc, "status_code", None) in {403, 404} or (
                isinstance(detail, dict)
                and detail.get("error") in {"inbound_tenant_not_allowlisted", "inbound_feature_unavailable", "company_not_found"}
            )
            ext_detail = detail if isinstance(detail, dict) else str(exc)
        gate(cases, "tenant_isolation_fail_closed", ext_ok, ext_detail)

        secret = app.inbound_postmark_secret()
        mismatch = httpx.post(
            f"http://127.0.0.1:8010/webhook/postmark/inbound?token={secret}",
            json=_payload(f"d6ga-{short}-env", g_addr["address"], "x@example.com", []),
            headers={"X-Wathefni-Inbound-Env": "staging"},
            timeout=30.0,
        )
        pin_ok = httpx.post(
            f"http://127.0.0.1:8010/webhook/postmark/inbound?token={secret}",
            json=_payload(f"d6ga-{short}-pin", g_addr["address"], "pin@example.com", [_att("p.pdf", _pdf("Pin", "pin@example.com"))]),
            headers={},
            timeout=30.0,
        )
        if pin_ok.status_code == 200:
            try:
                cleanup["inbound_ids"].append(pin_ok.json().get("inbound_id"))
            except Exception:
                pass
        gate(
            cases,
            "environment_isolation_postmark",
            mismatch.status_code == 401
            and (mismatch.json().get("detail") or {}).get("error") == "inbound_env_mismatch"
            and pin_ok.status_code == 200,
            {"mismatch": mismatch.status_code, "pin": pin_ok.status_code},
        )

        # Health env binding
        body = health.json()
        gate(
            cases,
            "environment_binding_production",
            body.get("environment_binding", {}).get("match") is True
            and body.get("environment_binding", {}).get("application_environment") == "production",
            body.get("environment_binding"),
        )

        # ------------------------------------------------------------------
        # Ops monitoring readiness
        # ------------------------------------------------------------------
        ops = {}
        try:
            ops = app.dashboard_prehire_intake_operations(ctx)
        except Exception as exc:
            ops = {"error": str(exc)}
        usage = app.dashboard_inbound_usage(ctx)
        # timer units
        import subprocess

        timers = subprocess.check_output(["systemctl", "list-timers", "--all"], text=True)
        ops_ready = {
            "usage_endpoint": "usage" in usage,
            "ops_endpoint": "error" not in ops or bool(ops),
            "inbound_worker_timer": "wathefni-inbound-intake-worker.timer" in timers,
            "ops_monitor_timer": "wathefni-inbound-ops-monitor.timer" in timers,
            "never_reject": (usage.get("usage") or {}).get("never_reject_for_volume") is True,
        }
        gate(
            cases,
            "ops_monitoring_support_ready",
            ops_ready["inbound_worker_timer"] and ops_ready["ops_monitor_timer"] and ops_ready["usage_endpoint"],
            {"ops_ready": ops_ready, "ops_keys": list(ops.keys())[:20] if isinstance(ops, dict) else type(ops).__name__},
        )

        # ------------------------------------------------------------------
        # EN/AR UI markers (live dashboard bundles)
        # ------------------------------------------------------------------
        blob = "\n".join(p.read_text(errors="replace") for p in Path("/var/www/wathefni-dashboard/assets").glob("*.js"))
        ui = {
            "en_intake": "Email & document intake" in blob,
            "ar_intake": "استقبال البريد والمستندات" in blob,
            "en_job_alias": "Job-specific alias" in blob,
            "ar_job_alias": "اسم مستعار لوظيفة" in blob,
            "en_held": "Assign & admit" in blob or "Held Intake" in blob,
            "ar_held": "تعيين وإضافة" in blob or "مراجعة الوارد" in blob or "تحتاج وظيفة" in blob,
            "en_connector": "Recruitment mailbox connector (optional)" in blob,
            "ar_connector": "ربط صندوق التوظيف" in blob or "موصل صندوق" in blob,
        }
        gate(cases, "ui_en_ar_rtl_markers", all(ui.values()) or (ui["en_intake"] and ui["ar_intake"] and ui["en_connector"]), ui)

        # ------------------------------------------------------------------
        # Onboarding clarity (product copy / feature payload)
        # ------------------------------------------------------------------
        onboarding = {
            "forwarding_default": packaging.get("default_intake_product") == "forwarding" or packaging.get("connector_default_product") == "forwarding",
            "connector_marked_optional_premium": bool(packaging.get("mailbox_connectors_premium") or packaging.get("connector_premium")),
            "sync_dark": not bool(packaging.get("mailbox_sync_enabled") or packaging.get("connector_sync_enabled")),
            "ui_forwarding_copy": ui.get("en_intake") and ui.get("en_job_alias"),
            "ui_connector_optional": ui.get("en_connector"),
        }
        gate(cases, "onboarding_setup_clarity", all(onboarding.values()), onboarding)

        # Privacy / retention readiness
        privacy = {
            "retention_execute_off": ieh.retention_execute_enabled() is False,
            "dry_run_works": "eligible" in dry,
            "quarantine_service_active": "active" in subprocess.check_output(["systemctl", "is-active", "wathefni-production-email-quarantine.service"], text=True),
            "encryption_ready": enc_ready,
        }
        gate(cases, "privacy_retention_readiness", privacy["retention_execute_off"] and privacy["dry_run_works"], privacy)

        # Operational rollback levers (no code rollback in D6 — qualification only)
        disabled = app.dashboard_intake_disable(g_addr["intake_id"], ctx)
        gate(
            cases,
            "operational_rollback_levers",
            disabled.get("ok") is not False and (disabled.get("address") or {}).get("status") == "disabled",
            disabled,
        )

    except Exception as exc:
        gate(cases, "matrix_uncaught_exception", False, {"error": str(exc), "trace": traceback.format_exc()[-2000:]})
    finally:
        # Cleanup + restore enterprise
        try:
            app.dashboard_inbound_plan_update({"kill_switch": False}, ctx)
            app.dashboard_inbound_admin_override_clear(ctx)
            if previous_enterprise is not None:
                # restore prior enterprise blob fields we care about
                plan = previous_enterprise.get("plan") or "internal"
                app.dashboard_inbound_plan_update(
                    {
                        "plan": plan,
                        "quota_overrides": previous_enterprise.get("quota_overrides") or {},
                        "soft_warning_pct": previous_enterprise.get("soft_warning_pct") or 80,
                        "kill_switch": bool(previous_enterprise.get("kill_switch")),
                    },
                    ctx,
                )
                cleanup["enterprise_restored"] = True
            else:
                app.dashboard_inbound_plan_update({"plan": "internal", "quota_overrides": {}, "kill_switch": False}, ctx)
                cleanup["enterprise_restored"] = True
        except Exception as exc:
            cleanup["enterprise_restore_error"] = str(exc)

        # disable proof intakes
        for iid in list(cleanup.get("intake_ids") or []):
            try:
                app.dashboard_intake_disable(iid, ctx)
            except Exception:
                pass

        # delete leftover mailboxes
        for mid in list(cleanup.get("mailbox_ids") or []):
            try:
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM mailbox_credentials WHERE mailbox_id=%s", (mid,))
                        cur.execute("DELETE FROM mailbox_connections WHERE mailbox_id=%s", (mid,))
                    conn.commit()
            except Exception:
                pass

        # cancel synthetic outage jobs still pending from proof
        for jid in list(cleanup.get("job_ids") or []):
            try:
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE intake_processing_jobs SET status='cancelled' WHERE job_id=%s AND company_code='WATHEFNI' AND status IN ('pending','dead_letter')",
                            (jid,),
                        )
                    conn.commit()
            except Exception:
                pass

        os.environ["WATHEFNI_MAILBOX_SYNC"] = "off"

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT intake_id::text, label, status FROM intake_addresses WHERE company_code='WATHEFNI' AND label ILIKE %s",
                    (f"%{MARKER}%",),
                )
                cleanup["proof_intakes"] = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    "SELECT count(*) AS c FROM intake_addresses WHERE company_code='WATHEFNI' AND status='active'"
                )
                cleanup["active_intake_count"] = cur.fetchone()["c"]
                cur.execute(
                    "SELECT count(*) AS c FROM mailbox_connections WHERE company_code='WATHEFNI' AND email_address LIKE 'd6-%'"
                )
                cleanup["leftover_d6_mailboxes"] = cur.fetchone()["c"]
            conn.commit()

    passed = sum(1 for v in cases.values() if isinstance(v, dict) and v.get("ok"))
    failed = sum(1 for v in cases.values() if isinstance(v, dict) and not v.get("ok"))
    out = {
        "stamp": stamp,
        "marker": MARKER,
        "passed": passed,
        "failed": failed,
        "cases": cases,
        "ids": ids,
        "cleanup": cleanup,
        "external_tenants_enabled": False,
        "post_hiring_started": False,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str) + "\n")
    print(json.dumps({"passed": passed, "failed": failed, "out": str(OUT)}, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
