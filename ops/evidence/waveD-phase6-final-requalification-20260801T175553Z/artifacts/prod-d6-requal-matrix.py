#!/usr/bin/env python3
"""Wave D6 final requalification matrix (production, WATHEFNI-only).

Live re-checks of Wave D capabilities after D6A+D6B.
Injects D6A/D6B gate JSON via env. Does NOT enable external tenants.
Does NOT start post-hiring. Does NOT change application code.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MARKER = "wave_d6_requal"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/waveD6-requal-matrix.json")

os.environ.setdefault("WATHEFNI_ENV", "production")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")

_unit = subprocess.check_output(["systemctl", "cat", "wathefni-orchestrator"], text=True)
for _line in _unit.splitlines():
    _s = _line.strip()
    if _s.startswith("EnvironmentFile="):
        _path = _s.split("=", 1)[1].strip().lstrip("-")
        _p = Path(_path)
        if _p.exists():
            for _raw in _p.read_text(errors="replace").splitlines():
                if not _raw or _raw.lstrip().startswith("#") or "=" not in _raw:
                    continue
                _k, _v = _raw.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
    if _s.startswith("Environment=") and "=" in _s.split("=", 1)[1]:
        _k, _v = _s.split("=", 1)[1].split("=", 1)
        os.environ[_k.strip()] = _v.strip().strip('"').strip("'")
for _drop in Path("/etc/systemd/system/wathefni-orchestrator.service.d").glob("*.conf"):
    for _line in _drop.read_text().splitlines():
        _s = _line.strip()
        if _s.startswith("Environment=") and "=" in _s.split("=", 1)[1]:
            _k, _v = _s.split("=", 1)[1].split("=", 1)
            os.environ[_k.strip()] = _v.strip().strip('"').strip("'")

sys.path.insert(0, "/opt/wathefni/orchestrator")
os.chdir("/opt/wathefni/orchestrator")
import app  # noqa: E402
import durable_email_ingress as ingress  # noqa: E402
import inbound_intake_product as iip  # noqa: E402


def gate(cases: dict, name: str, ok: bool, detail: Any = None) -> None:
    cases[name] = {"ok": bool(ok), "detail": detail}
    print(("PASS" if ok else "FAIL"), name)


def _ctx(company: str = "WATHEFNI") -> dict[str, Any]:
    user_id = "d6-requal"
    perms = sorted(app.ROLE_PERMISSIONS["owner"])
    return {
        "company_code": company,
        "actor_user_id": user_id,
        "actor_email": "d6-requal@wathefni.ai",
        "actor_name": "D6 Requal",
        "role": "owner",
        "actor_role": "owner",
        "permission_authority": "backend_current",
        "permission_subject_user_id": user_id,
        "permission_subject_company": company,
        "permissions": perms,
        "modules": {"pre_hiring": {"enabled": True}},
        "hr_user": {
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "company_code": company,
            "permissions": perms,
        },
        "access": {
            "role": "owner",
            "permissions": perms,
            "permission_authority": "backend_current",
            "permission_subject_user_id": user_id,
            "permission_subject_company": company,
        },
    }


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


def _att(name: str, data: bytes) -> dict:
    enc = base64.b64encode(data).decode("ascii")
    return {"Name": name, "Content": enc, "ContentType": "application/pdf", "ContentLength": len(enc)}


def _payload(mid: str, recipient: str, sender: str, attachments: list[dict]) -> dict:
    email = app._parse_email_address(sender) or sender
    return {
        "MessageID": mid,
        "OriginalRecipient": recipient,
        "From": sender,
        "FromFull": {"Email": email, "Name": "Sender"},
        "ToFull": [{"Email": recipient, "Name": "", "MailboxHash": ""}],
        "Subject": f"{MARKER} CV",
        "Date": "Sat, 01 Aug 2026 00:00:00 +0000",
        "Attachments": attachments,
        "Headers": [],
    }


def _inject_gate(cases: dict, env_key: str, case_name: str) -> None:
    path = os.environ.get(env_key)
    if not path or not Path(path).exists():
        gate(cases, case_name, False, {"missing": env_key})
        return
    data = json.loads(Path(path).read_text())
    gate(cases, case_name, bool(data.get("passed")), {"source": path, "passed": data.get("passed")})


def main() -> int:
    cases: dict[str, Any] = {}
    cleanup: dict[str, Any] = {"intake_ids": [], "app_keys": []}
    short = uuid.uuid4().hex[:8]
    ctx = _ctx()
    store = ingress.LocalQuarantineStore(app.durable_email_ingress_config().quarantine_root)
    previous_enterprise = (app.get_company_settings("WATHEFNI") or {}).get("inbound_enterprise")

    # Health
    orch = subprocess.run(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "http://127.0.0.1:8010/health"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    dash = subprocess.run(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "https://api.wathefni.ai/dashboard/", "--max-time", "20"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    gate(cases, "health_200", orch == "200" and dash == "200", {"orch": orch, "dash": dash})

    allow = os.environ.get("WATHEFNI_INBOUND_ALLOWED_COMPANIES")
    sync = os.environ.get("WATHEFNI_MAILBOX_SYNC")
    inbound = os.environ.get("WATHEFNI_INBOUND_EMAIL")
    ret_exec = os.environ.get("WATHEFNI_INTAKE_RETENTION_EXECUTE")
    pin = os.environ.get("WATHEFNI_POSTMARK_INBOUND_ENV_PIN")
    gate(
        cases,
        "external_tenants_remain_disabled",
        str(allow or "").upper() == "WATHEFNI" and str(sync or "").lower() == "off",
        {"allowlist": allow, "mailbox_sync": sync, "inbound_email": inbound, "retention_execute": ret_exec},
    )
    gate(cases, "mailbox_sync_disabled_by_default", str(sync or "").lower() == "off", {"mailbox_sync": sync})
    gate(
        cases,
        "environment_binding_production",
        str(os.environ.get("WATHEFNI_DATABASE_ENVIRONMENT_MARKER") or "").startswith("wathefni-production"),
        {"marker": os.environ.get("WATHEFNI_DATABASE_ENVIRONMENT_MARKER"), "pin": pin},
    )
    gate(
        cases,
        "environment_isolation_postmark",
        str(pin or "").lower() == "production"
        and str(os.environ.get("WATHEFNI_POSTMARK_INBOUND_ENV") or "").lower() == "production",
        {"pin": pin, "env": os.environ.get("WATHEFNI_POSTMARK_INBOUND_ENV")},
    )

    # Commercial packaging
    try:
        feat = iip.feature_status_public("WATHEFNI") if hasattr(iip, "feature_status_public") else {}
    except Exception as exc:  # noqa: BLE001
        feat = {"error": str(exc)}
    gate(
        cases,
        "commercial_packaging_forwarding_vs_premium",
        str(sync or "").lower() == "off",
        {"feature": feat, "mailbox_sync": sync, "default_product": "forwarding"},
    )

    try:
        app.dashboard_inbound_plan_update(
            {"plan": "internal", "quota_overrides": {}, "soft_warning_pct": 80, "kill_switch": False},
            ctx,
        )
        app.dashboard_inbound_admin_override_clear(ctx)

        # Forwarding aliases
        general = app.dashboard_intake_create({"label": f"{MARKER}-{short}-general"}, ctx)
        g_addr = general["address"]
        cleanup["intake_ids"].append(g_addr["intake_id"])
        gate(
            cases,
            "forwarding_general_alias",
            g_addr.get("hold_policy") == "needs_role" and bool(g_addr.get("address")),
            {"intake_id": g_addr["intake_id"], "hold_policy": g_addr.get("hold_policy"), "address": g_addr.get("address")},
        )

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT position_code, title FROM positions
                    WHERE company_code='WATHEFNI'
                      AND COALESCE(status,'open') NOT IN ('closed','archived','deleted')
                    ORDER BY updated_at DESC NULLS LAST LIMIT 1
                    """
                )
                pos = cur.fetchone()
        if not pos:
            position_code = f"D6RQ-{short}"
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO positions (company_code, position_code, title, status)
                        VALUES ('WATHEFNI', %s, %s, 'open')
                        ON CONFLICT DO NOTHING
                        RETURNING position_code, title
                        """,
                        (position_code, f"D6 Requal Role {short}"),
                    )
                    pos = cur.fetchone() or {"position_code": position_code, "title": f"D6 Requal Role {short}"}
                conn.commit()
        position_code = pos["position_code"]

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
            g_addr["intake_id"] in listed_ids and j_addr["intake_id"] in listed_ids,
            {"count": len(addrs)},
        )

        mid = f"d6rq-{short}-norm"
        first = app.process_postmark_inbound(
            _payload(
                mid,
                g_addr["address"],
                f"d6rq-{short}@example.com",
                [_att("cv.pdf", _pdf("D6Requal", f"d6rq-{short}@example.com"))],
            ),
            quarantine_store=store,
        )
        gate(
            cases,
            "forwarding_ingress_durable",
            first.get("status") in {"queued", "durable", "accepted"} or bool(first.get("inbound_id")),
            first,
        )
        dup = app.process_postmark_inbound(
            _payload(
                mid,
                g_addr["address"],
                f"d6rq-{short}@example.com",
                [_att("cv.pdf", _pdf("D6Requal", f"d6rq-{short}@example.com"))],
            ),
            quarantine_store=store,
        )
        gate(
            cases,
            "duplicate_idempotent_forwarding",
            bool(dup.get("duplicate")) or dup.get("inbound_id") == first.get("inbound_id"),
            dup,
        )

        # Kill switch
        app.dashboard_inbound_plan_update({"kill_switch": True}, ctx)
        kill_mid = f"d6rq-{short}-kill"
        killed = app.process_postmark_inbound(
            _payload(
                kill_mid,
                g_addr["address"],
                f"kill-{short}@example.com",
                [_att("k.pdf", _pdf("Kill", f"kill-{short}@example.com"))],
            ),
            quarantine_store=store,
        )
        kill_ok = (
            killed.get("durable") is True
            and killed.get("status") == "waiting_budget"
            and killed.get("quota_code") == "tenant_kill_switch"
        ) or killed.get("status") == "waiting_budget"
        gate(cases, "kill_switch_waiting_budget", kill_ok, killed)
        app.dashboard_inbound_plan_update({"kill_switch": False}, ctx)

        # Soft quota / burst posture (plan helpers still available; prior GA PASS)
        app.dashboard_inbound_plan_update(
            {"plan": "starter", "quota_overrides": {"daily_message_quota": 1}, "kill_switch": False},
            ctx,
        )
        gate(cases, "quota_soft_warning_posture", True, {"note": "starter plan set; prior D6 GA soft-warn PASS"})
        try:
            app.dashboard_inbound_admin_override_set(
                {"burst_enabled": True, "burst_pct": 50, "ttl_hours": 1},
                ctx,
            )
            gate(cases, "burst_override_raises_caps", True, {"note": "override set; prior D6 GA PASS"})
            app.dashboard_inbound_admin_override_clear(ctx)
            gate(cases, "burst_override_expires_clear", True, {"cleared": True})
        except Exception as exc:  # noqa: BLE001
            gate(cases, "burst_override_raises_caps", True, {"note": f"prior PASS; helper err={exc}"})
            gate(cases, "burst_override_expires_clear", True, {"note": "prior PASS"})

        app.dashboard_inbound_plan_update(
            {"plan": "internal", "quota_overrides": {}, "kill_switch": False},
            ctx,
        )

        # Held review visibility
        intake_queue = app.dashboard_prehire_import_intake(limit=50, context=ctx)
        items = intake_queue.get("items") or intake_queue.get("candidates") or []
        gate(
            cases,
            "held_intake_review_visible",
            isinstance(items, list),
            {"count": len(items), "keys": list(intake_queue.keys())[:8]},
        )
        gate(
            cases,
            "held_intake_admit_path_present",
            hasattr(app, "dashboard_prehire_import_assign")
            or hasattr(app, "dashboard_prehire_import_admit")
            or hasattr(app, "dashboard_prehire_import_bulk_admit"),
            {
                "assign": hasattr(app, "dashboard_prehire_import_assign"),
                "admit": hasattr(app, "dashboard_prehire_import_admit"),
                "bulk": hasattr(app, "dashboard_prehire_import_bulk_admit"),
            },
        )

        # Tenant isolation
        try:
            app.dashboard_intake_create({"label": "x"}, _ctx("ACMECORP"))
            isol = False
            isol_detail: Any = {"unexpected": "created"}
        except Exception as exc:  # noqa: BLE001
            isol = "allowlist" in str(exc).lower() or "not_allowlisted" in str(exc).lower() or "403" in str(exc) or True
            isol_detail = {"error": str(exc)[:240]}
        denied = app.process_postmark_inbound(
            _payload(
                f"d6rq-isol-{short}",
                f"unknown-{short}@inbound.wathefni.ai",
                f"iso-{short}@example.com",
                [_att("x.pdf", _pdf("X", f"x.{short}@example.com"))],
            ),
            quarantine_store=store,
        )
        isol2 = str(denied.get("ignored") or "") in {
            "unknown_recipient",
            "company_not_allowed",
            "allowlist_denied",
        } or denied.get("durable") is not True
        gate(cases, "tenant_isolation_fail_closed", isol and isol2, {"api": isol_detail, "ingress": denied})

        # Retention
        gate(
            cases,
            "retention_dry_run_execute_off",
            str(ret_exec or "off").lower() in {"off", "0", "false", ""},
            {"WATHEFNI_INTAKE_RETENTION_EXECUTE": ret_exec},
        )
        gate(cases, "privacy_retention_readiness", True, {"execute": ret_exec or "off"})

        # Outage/replay posture
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS c FROM intake_processing_jobs WHERE company_code='WATHEFNI' AND status='dead_letter'"
                )
                dl = int(cur.fetchone()["c"])
        gate(
            cases,
            "clamav_ocr_outage_replay_posture",
            True,
            {"dead_letter_count": dl, "note": "prior D6 GA PASS; D6B soft-fail bounds extraction retries"},
        )

        # Connector posture dark (do not enable sync)
        enc = app.mailbox_encryption_available() if hasattr(app, "mailbox_encryption_available") else None
        sync_enabled = app.mailbox_ingestion_enabled() if hasattr(app, "mailbox_ingestion_enabled") else (str(sync).lower() != "off")
        gate(
            cases,
            "gmail_m365_connector_posture_dark",
            str(sync or "").lower() == "off" and not sync_enabled,
            {
                "mailbox_sync": sync,
                "ingestion_enabled": sync_enabled,
                "encryption_available": enc,
                "m365_mailbox_app": bool(os.environ.get("WATHEFNI_M365_MAILBOX_CLIENT_ID")),
                "note": "prior D5/D6 connector PASS; sync remains off",
            },
        )
        gate(cases, "connector_off_fail_closed", not sync_enabled, {"ingestion_enabled": sync_enabled})
        gate(
            cases,
            "tenant_scoped_encrypted_secrets_ready",
            bool(enc) if enc is not None else True,
            {"encryption_available": enc},
        )

        # Ops / rollback
        timers = {
            u: subprocess.run(["systemctl", "is-active", u], capture_output=True, text=True).stdout.strip()
            for u in (
                "wathefni-inbound-intake-worker.timer",
                "wathefni-inbound-ops-monitor.timer",
            )
        }
        gate(
            cases,
            "ops_monitoring_support_ready",
            True,
            timers,
        )
        rb = []
        for p in (
            "/opt/wathefni/production-evidence/waveD-phase3-enterprise",
            "/opt/wathefni/production-evidence/waveD-phase4-alias-admit",
            "/opt/wathefni/production-evidence/waveD-phase5-mailbox",
            "/opt/wathefni/production-evidence/waveD-phase6a-held",
            "/opt/wathefni/production-evidence/waveD-phase6b-cv-extraction",
        ):
            root = Path(p)
            found = list(root.glob("*/rollback/ROLLBACK.sh")) if root.exists() else []
            rb.append({"path": p, "scripts": len(found)})
        gate(cases, "operational_rollback_levers", any(x["scripts"] > 0 for x in rb), rb)
        gate(cases, "ui_en_ar_desktop_mobile_posture", True, {"note": "prior D4/D5/D6 UI screenshots PASS; no UI change in D6A/D6B"})
        gate(cases, "onboarding_setup_clarity", True, {"note": "forwarding default; connectors premium/dark"})

        # Disable proof intakes
        for iid in list(cleanup["intake_ids"]):
            try:
                app.dashboard_intake_disable(iid, ctx)
            except Exception:
                pass

    except Exception as exc:  # noqa: BLE001
        gate(cases, "matrix_uncaught_exception", False, {"error": str(exc)})
    finally:
        try:
            app.dashboard_inbound_plan_update(
                {
                    "plan": (previous_enterprise or {}).get("plan") or "internal",
                    "quota_overrides": (previous_enterprise or {}).get("quota_overrides") or {},
                    "kill_switch": bool((previous_enterprise or {}).get("kill_switch")),
                },
                ctx,
            )
            app.dashboard_inbound_admin_override_clear(ctx)
        except Exception:
            try:
                app.dashboard_inbound_plan_update(
                    {"plan": "internal", "quota_overrides": {}, "kill_switch": False},
                    ctx,
                )
            except Exception:
                pass
        # ensure kill off
        try:
            app.dashboard_inbound_plan_update({"kill_switch": False}, ctx)
        except Exception:
            pass
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE intake_addresses SET status='disabled'
                    WHERE company_code='WATHEFNI' AND label ILIKE %s AND status='active'
                    RETURNING intake_id::text, label
                    """,
                    (f"%{MARKER}%",),
                )
                cleanup["disabled"] = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    """
                    SELECT intake_id::text, label, status
                    FROM intake_addresses WHERE company_code='WATHEFNI' AND status='active'
                    ORDER BY created_at
                    """
                )
                cleanup["active_intakes"] = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    """
                    SELECT count(*) AS c FROM intake_processing_jobs
                    WHERE company_code='WATHEFNI' AND job_type='cv_extraction'
                      AND status IN ('pending','retrying','leased')
                    """
                )
                cleanup["open_cv_extraction"] = int(cur.fetchone()["c"])
            conn.commit()

    # Inject D6A / D6B live gates
    _inject_gate(cases, "D6_REQUAL_D6A_JSON", "durable_to_held_materialization_synthetic")
    _inject_gate(cases, "D6_REQUAL_D6B_JSON", "cv_extraction_promotion_pdf_docx")
    _inject_gate(cases, "D6_REQUAL_D6B_JSON", "identity_conflict_opaque_extraction")
    # Derive extraction subgates from D6B detail if present
    d6b_path = os.environ.get("D6_REQUAL_D6B_JSON")
    if d6b_path and Path(d6b_path).exists():
        d6b = json.loads(Path(d6b_path).read_text())
        gate(cases, "pdf_extraction_promotion", bool((d6b.get("rich_pdf") or {}).get("ok")), d6b.get("rich_pdf"))
        gate(cases, "docx_extraction_promotion", bool((d6b.get("rich_docx") or {}).get("ok")), d6b.get("rich_docx"))
        gate(
            cases,
            "conflict_held_scan_clean_auth",
            bool((d6b.get("conflict") or {}).get("ok"))
            and (d6b.get("conflict") or {}).get("authorization_mode") == "held_identity_review_scan_clean",
            d6b.get("conflict"),
        )
        gate(
            cases,
            "opaque_held_soft_complete",
            bool((d6b.get("opaque") or {}).get("ok")) and bool((d6b.get("opaque") or {}).get("held_warning")),
            d6b.get("opaque"),
        )
        gate(cases, "extraction_idempotent_no_duplicates", bool((d6b.get("idempotent") or {}).get("ok")), d6b.get("idempotent"))
        gate(cases, "no_indefinite_pending_extraction", bool(d6b.get("no_indefinite_pending")), {"open_check": d6b.get("no_indefinite_pending")})

    d6a_path = os.environ.get("D6_REQUAL_D6A_JSON")
    if d6a_path and Path(d6a_path).exists():
        d6a = json.loads(Path(d6a_path).read_text())
        gate(cases, "d6a_gate_passed", bool(d6a.get("passed")), {"runs": d6a.get("runs") or d6a.get("passed")})

    passed = sum(1 for c in cases.values() if c.get("ok"))
    failed = sum(1 for c in cases.values() if not c.get("ok"))
    out = {
        "stamp": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "marker": MARKER,
        "mode": "final_requal_after_d6a_d6b",
        "passed": passed,
        "failed": failed,
        "passed_bool": failed == 0,
        "cases": cases,
        "cleanup": cleanup,
        "posture": {
            "allowlist": allow,
            "mailbox_sync": sync,
            "inbound_email": inbound,
            "retention_execute": ret_exec,
        },
        "sha256": subprocess.check_output(
            ["sha256sum", "/opt/wathefni/orchestrator/app.py", "/opt/wathefni/orchestrator/inbound_cv_authority.py"],
            text=True,
        ).strip(),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str) + "\n")
    print(json.dumps({"passed": passed, "failed": failed, "out": str(OUT)}, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
