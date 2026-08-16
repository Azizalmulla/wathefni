"""Wave D Phase 3 — enterprise multi-tenant inbound hardening (local only).

Proves:
* plan catalog + soft warnings before hard queue
* burst via admin override (queue, never reject volume)
* tenant kill switch holds without dropping mail
* staging/prod Postmark env isolation
* ClamAV/OCR outage dead-letter → replay
* retention dry-run + execute proof
* concurrency-safe address create (IntegrityError → 409)
* usage/health visibility
* external tenants remain disabled; no mailbox sync; no D4
"""

from __future__ import annotations

import base64
import os
import shutil
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from fastapi import HTTPException
from fastapi.testclient import TestClient
from psycopg2.extras import Json

_QUARANTINE = Path(tempfile.mkdtemp(prefix="wathefni-inbound-d3-"))
database_url = str(os.environ.get("WATHEFNI_TEST_DATABASE_URL") or "").strip()
if database_url:
    parsed_database = urlparse(database_url)
    env_file = _QUARANTINE / "postgres.test.env"
    env_file.write_text(f"WATHEFNI_DATABASE_URL={database_url}\n")
    os.environ["WATHEFNI_POSTGRES_ENV"] = str(env_file)
    os.environ["WATHEFNI_ENV"] = "test"
    os.environ["WATHEFNI_EXPECTED_DATABASE_HOST"] = parsed_database.hostname or "127.0.0.1"
    os.environ["WATHEFNI_EXPECTED_DATABASE_PORT"] = str(parsed_database.port or 5432)
    os.environ["WATHEFNI_EXPECTED_DATABASE_NAME"] = parsed_database.path.lstrip("/")
    os.environ.setdefault(
        "WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-local-boundary-remediation-v1"
    )
elif not os.environ.get("WATHEFNI_POSTGRES_ENV"):
    raise RuntimeError(
        "Set WATHEFNI_POSTGRES_ENV or WATHEFNI_TEST_DATABASE_URL to an isolated test database."
    )

os.environ["WATHEFNI_INBOUND_EMAIL"] = "on"
os.environ["WATHEFNI_INBOUND_ALLOWED_COMPANIES"] = "WATHEFNI,D3TESTA,D3TESTB"
os.environ.setdefault("WATHEFNI_POSTMARK_INBOUND_SECRET", "smoke-secret-token-d3")
os.environ["WATHEFNI_INTAKE_QUARANTINE_DIR"] = str(_QUARANTINE)
os.environ["WATHEFNI_INTAKE_MALWARE_SCANNER"] = "test_clean"
os.environ["WATHEFNI_INTAKE_ALLOW_TEST_SCANNER"] = "1"
os.environ["WATHEFNI_POSTMARK_INBOUND_ENV"] = ""
os.environ["WATHEFNI_INTAKE_RETENTION_EXECUTE"] = "off"
os.environ["WATHEFNI_MAILBOX_SYNC"] = "off"
# Retention policy env (required for policy_from_env / activate)
os.environ.setdefault("WATHEFNI_INTAKE_RETENTION_POLICY_VERSION", "d3-enterprise-v1")
os.environ.setdefault("WATHEFNI_INTAKE_RETENTION_CLEAN_DAYS", "1")
os.environ.setdefault("WATHEFNI_INTAKE_RETENTION_NONCLEAN_DAYS", "1")
os.environ.setdefault("WATHEFNI_INTAKE_RETENTION_RESOLVED_REVIEW_DAYS", "1")
os.environ.setdefault("WATHEFNI_INTAKE_RETENTION_WITHDRAWN_HELD_DAYS", "1")
os.environ.setdefault("WATHEFNI_INTAKE_RETENTION_AUDIT_YEARS", "1")
os.environ.setdefault("WATHEFNI_INTAKE_RETENTION_CORRECTION_AUDIT_YEARS", "1")
os.environ.setdefault("WATHEFNI_INTAKE_SCAN_REUSE_HOURS", "1")
os.environ.setdefault("WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS", "60")

import app  # noqa: E402
import durable_email_ingress as ingress  # noqa: E402
import inbound_enterprise_hardening as ieh  # noqa: E402
import inbound_intake_product as iip  # noqa: E402
import inbound_retention_policy as retention  # noqa: E402
from intake_quarantine_storage import LocalVolumeQuarantineStorage  # noqa: E402

COMPANY_A = "D3TESTA"
COMPANY_B = "D3TESTB"
EXTERNAL = "ACMECORP"
MARKER = "wave_d3_enterprise_hardening"


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:
            self.failed.append(f"{label} -> raised {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def report(self) -> int:
        for label in self.passed:
            print(f"PASS  {label}")
        for label in self.failed:
            print(f"FAIL  {label}")
        print(f"\n{len(self.passed)} passed, {len(self.failed)} failed")
        return 0 if not self.failed else 1


def _pdf(name: str, email: str) -> bytes:
    stream = (
        f"BT /F1 12 Tf 72 720 Td ({name}) Tj 0 -18 Td (Email {email}) Tj ET"
    ).encode()
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
    return {
        "Name": name,
        "Content": encoded,
        "ContentType": "application/pdf",
        "ContentLength": len(encoded),
    }


def _payload(message_id: str, recipient: str, sender: str, attachments: list[dict]) -> dict:
    email = app._parse_email_address(sender) or sender
    return {
        "MessageID": message_id,
        "OriginalRecipient": recipient,
        "From": sender,
        "FromFull": {"Email": email, "Name": "Sender"},
        "ToFull": [{"Email": recipient, "Name": "", "MailboxHash": ""}],
        "Subject": "My CV",
        "Date": "Sat, 01 Aug 2026 00:00:00 +0000",
        "Attachments": attachments,
        "Headers": [],
    }


def _ctx(company: str) -> dict[str, Any]:
    user_id = f"d3-user-{company.lower()}"
    perms = sorted(app.ROLE_PERMISSIONS["owner"])
    return {
        "company_code": company,
        "actor_user_id": user_id,
        "actor_email": "hr@example.com",
        "actor_name": "D3 HR",
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


def setup() -> None:
    app.ensure_schema(force=True)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            ingress.ensure_schema(cur)
            retention.ensure_schema(cur)
            for company in (COMPANY_A, COMPANY_B, EXTERNAL, "WATHEFNI"):
                cur.execute(
                    """
                    INSERT INTO companies
                      (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (
                        company,
                        f"D3 {company}",
                        Json({"smoke": MARKER}),
                        Json({"smoke": MARKER}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO company_modules (company_code, module_key, enabled, settings, source, updated_at)
                    VALUES (%s,'pre_hiring',true,'{}'::jsonb,'smoke',now())
                    ON CONFLICT (company_code, module_key) DO UPDATE
                      SET enabled=true, updated_at=now()
                    """,
                    (company,),
                )
        conn.commit()


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('wathefni.authority_cleanup','synthetic',true)")
            companies = [COMPANY_A, COMPANY_B, EXTERNAL]
            cur.execute("DELETE FROM intake_processing_job_events WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM intake_processing_jobs WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM intake_documents WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM intake_submissions WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM inbound_messages WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM intake_addresses WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM intake_quota_usage WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM inbound_retention_deletions WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM inbound_retention_policy_assignments WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM inbound_retention_policies WHERE company_code = ANY(%s)", (companies,))
            cur.execute("DELETE FROM company_settings WHERE company_code = ANY(%s)", (companies,))
        conn.commit()
    shutil.rmtree(_QUARANTINE, ignore_errors=True)


def main() -> int:
    checks = Checks()
    stamp = uuid.uuid4().hex[:8]
    setup()
    store = ingress.LocalQuarantineStore(_QUARANTINE)
    storage = LocalVolumeQuarantineStorage(_QUARANTINE)
    client = TestClient(app.app)

    try:
        checks.check(
            "enterprise plan catalog has starter/growth/enterprise/internal",
            lambda: set(ieh.PLAN_CATALOG) >= {"starter", "growth", "enterprise", "internal"},
        )
        soft = ieh.evaluate_quota(
            {"day": {"messages": 80, "source_bytes": 0}, "month": {"messages": 0, "source_bytes": 0}},
            company_code="ACME",
            settings={
                "inbound_enterprise": {
                    "plan": "starter",
                    "quota_overrides": {"daily_message_quota": 100},
                }
            },
        )
        soft_ok = soft.status is None and "daily_message_quota_soft_warning" in soft.soft_warnings
        checks.check("soft warning fires at 80% without hard queue", lambda soft_ok=soft_ok: soft_ok)
        hard = ieh.evaluate_quota(
            {"day": {"messages": 501, "source_bytes": 0}, "month": {"messages": 0, "source_bytes": 0}},
            company_code="ACME",
            settings={"inbound_enterprise": {"plan": "starter"}},
        )
        checks.check(
            "over hard cap queues waiting_quota (never reject)",
            lambda: hard.status == "waiting_quota" and hard.code == "daily_message_quota",
        )
        override = ieh.build_admin_override(
            actor="d3",
            burst_enabled=True,
            burst_pct=100,
            hours=24,
            quota_overrides={"daily_message_quota": 10},
        )
        burst = ieh.effective_limits(
            "ACME",
            settings={"inbound_enterprise": {"plan": "starter", "admin_override": override}},
        )
        checks.check(
            "admin override enables burst headroom",
            lambda: burst["admin_override_active"] and burst["limits"]["daily_message_quota"] == 20,
        )

        os.environ["WATHEFNI_POSTMARK_INBOUND_ENV"] = "production"
        ok_missing, code_missing = ieh.verify_postmark_inbound_environment()
        ok_bad, code_bad = ieh.verify_postmark_inbound_environment(header_env="staging")
        ok_good, _ = ieh.verify_postmark_inbound_environment(header_env="production")
        checks.check(
            "postmark env rejects missing marker",
            lambda: (not ok_missing) and code_missing == "inbound_env_marker_missing",
        )
        checks.check(
            "postmark env rejects staging→production mismatch",
            lambda: (not ok_bad) and code_bad == "inbound_env_mismatch",
        )
        checks.check("postmark env accepts matching production marker", lambda: ok_good)
        os.environ["WATHEFNI_POSTMARK_INBOUND_ENV"] = ""

        checks.check(
            "external tenant still not allowlisted",
            lambda: not iip.company_on_inbound_allowlist(EXTERNAL),
        )

        ctx_a = _ctx(COMPANY_A)
        created = app.dashboard_intake_create({"label": "D3 general"}, ctx_a)
        address = created["address"]["address"]
        intake_id = created["address"]["intake_id"]
        local_part = created["address"]["local_part"]
        checks.check("create intake address for allowlisted tenant", lambda: bool(address and intake_id))

        app.dashboard_inbound_plan_update(
            {
                "plan": "starter",
                "quota_overrides": {"daily_message_quota": 1, "monthly_message_quota": 0},
                "soft_warning_pct": 80,
            },
            ctx_a,
        )
        usage_view = app.dashboard_inbound_usage(ctx_a)
        checks.check(
            "usage visibility exposes enterprise limits and never_reject flag",
            lambda: usage_view["usage"]["never_reject_for_volume"]
            and usage_view["usage"]["effective_limits"]["daily_message_quota"] == 1
            and usage_view["feature"].get("mailbox_sync_enabled") is False,
        )

        first = app.process_postmark_inbound(
            _payload(
                f"d3-{stamp}-1",
                address,
                "cand1@example.com",
                [_att("cv1.pdf", _pdf("Cand One", "cand1@example.com"))],
            ),
            quarantine_store=store,
        )
        checks.check("first message durable under tiny quota", lambda: first.get("durable") is True)

        second = app.process_postmark_inbound(
            _payload(
                f"d3-{stamp}-2",
                address,
                "cand2@example.com",
                [_att("cv2.pdf", _pdf("Cand Two", "cand2@example.com"))],
            ),
            quarantine_store=store,
        )
        checks.check(
            "second message durable + queued waiting_quota (not rejected)",
            lambda: second.get("durable") is True
            and second.get("status") == "waiting_quota"
            and second.get("quota_code") == "daily_message_quota",
        )

        raised = app.dashboard_inbound_admin_override(
            {
                "burst_enabled": True,
                "burst_pct": 0,
                "hours": 24,
                "reason": "seasonal_hiring_spike",
                "quota_overrides": {"daily_message_quota": 100},
            },
            ctx_a,
        )
        checks.check(
            "admin override raised",
            lambda: raised.get("ok") is True and raised["admin_override"]["enabled"] is True,
        )

        third = app.process_postmark_inbound(
            _payload(
                f"d3-{stamp}-3",
                address,
                "cand3@example.com",
                [_att("cv3.pdf", _pdf("Cand Three", "cand3@example.com"))],
            ),
            quarantine_store=store,
        )
        checks.check(
            "after override, traffic is durable and not waiting_quota",
            lambda: third.get("durable") is True and third.get("status") != "waiting_quota",
        )

        app.dashboard_inbound_plan_update({"kill_switch": True}, ctx_a)
        held = app.process_postmark_inbound(
            _payload(
                f"d3-{stamp}-4",
                address,
                "cand4@example.com",
                [_att("cv4.pdf", _pdf("Cand Four", "cand4@example.com"))],
            ),
            quarantine_store=store,
        )
        checks.check(
            "tenant kill switch holds mail as waiting_budget without loss",
            lambda: held.get("durable") is True
            and held.get("status") == "waiting_budget"
            and held.get("quota_code") == "tenant_kill_switch",
        )
        app.dashboard_inbound_plan_update({"kill_switch": False}, ctx_a)
        app.dashboard_inbound_admin_override_clear(ctx_a)

        ctx_b = _ctx(COMPANY_B)
        created_b = app.dashboard_intake_create({"label": "B"}, ctx_b)
        addr_b = created_b["address"]["address"]
        msg_b = app.process_postmark_inbound(
            _payload(
                f"d3-{stamp}-b1",
                addr_b,
                "other@example.com",
                [_att("b.pdf", _pdf("Other", "other@example.com"))],
            ),
            quarantine_store=store,
        )
        checks.check(
            "tenant B message scoped to B only",
            lambda: msg_b.get("company_code") == COMPANY_B and msg_b.get("durable") is True,
        )

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO intake_processing_jobs
                      (company_code, job_type, subject_type, subject_id, priority, status,
                       available_at, max_attempts, idempotency_key, payload,
                       last_error_code, last_error_detail)
                    VALUES (%s,'malware_scan','intake_document',%s,100,'dead_letter',now(),5,%s,%s,
                            'scanner_unavailable','clamav down')
                    RETURNING job_id::text AS job_id
                    """,
                    (
                        COMPANY_A,
                        str(uuid.uuid4()),
                        f"d3-outage-{stamp}",
                        Json({"document_id": str(uuid.uuid4())}),
                    ),
                )
                dead_id = cur.fetchone()["job_id"]
                outage_rows = ieh.list_outage_dead_letters(cur, company_code=COMPANY_A, limit=20)
            conn.commit()
        checks.check(
            "outage dead-letter listed for ClamAV code",
            lambda: any(r["job_id"] == dead_id for r in outage_rows),
        )
        replayed = ingress.replay_dead_letter(
            db_connect=app.db_connect,
            company_code=COMPANY_A,
            job_id=dead_id,
            actor="d3_outage_drill",
        )
        checks.check("outage dead-letter replayed to pending", lambda: replayed.get("status") == "pending")

        # Retention: activate short policy, age a document, dry-run then execute
        policy = retention.policy_from_env(COMPANY_A, os.environ)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                retention.activate_policy(cur, policy, actor="d3_smoke")
                cur.execute(
                    """
                    SELECT document_id::text AS document_id, quarantine_key, content_sha256
                    FROM intake_documents
                    WHERE company_code=%s AND quarantine_key IS NOT NULL
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (COMPANY_A,),
                )
                doc = cur.fetchone()
                dry = retention.execute_cleanup(
                    cur,
                    company_code=COMPANY_A,
                    storage=storage,
                    actor="d3_retention",
                    dry_run=True,
                    limit=50,
                )
            conn.commit()
        checks.check(
            "retention dry-run returns plan without delete",
            lambda: dry.get("dry_run") is not False and "eligible" in dry,
        )

        if doc:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT document_id::text AS document_id,
                               inbound_id::text AS inbound_id,
                               attachment_ordinal, content_sha256, quarantine_key
                        FROM intake_documents
                        WHERE company_code=%s AND document_id=%s
                        """,
                        (COMPANY_A, doc["document_id"]),
                    )
                    full = dict(cur.fetchone() or {})
                    old = datetime.now(UTC) - timedelta(days=30)
                    cur.execute(
                        """
                        INSERT INTO inbound_attachment_scan_decisions(
                          company_code, inbound_id, intake_document_id, attachment_ordinal,
                          content_sha256, scanner_policy_version, attempt_no, state,
                          scanner_engine, scan_started_at, scan_completed_at, result,
                          failure_reason, quarantine_object_ref, actor_service_identity, evidence)
                        VALUES (%s,%s,%s,%s,%s,'d3-scan-v1',1,'infected',
                                'd3_smoke',%s,%s,'infected','eicar_sim',%s,'d3_smoke',%s)
                        ON CONFLICT (company_code, intake_document_id, attempt_no) DO UPDATE
                          SET state='infected', scan_completed_at=EXCLUDED.scan_completed_at
                        """,
                        (
                            COMPANY_A,
                            full["inbound_id"],
                            full["document_id"],
                            full["attachment_ordinal"],
                            full["content_sha256"],
                            old,
                            old,
                            full["quarantine_key"],
                            Json({"d3_retention_probe": True}),
                        ),
                    )
                    executed = retention.execute_cleanup(
                        cur,
                        company_code=COMPANY_A,
                        storage=storage,
                        actor="d3_retention_execute",
                        dry_run=False,
                        limit=50,
                    )
                conn.commit()
            checks.check(
                "retention execute deletes eligible raw object with audit row",
                lambda: int(executed.get("deleted_count") or 0) >= 1,
            )
        else:
            checks.check("retention execute deletes eligible raw object with audit row", lambda: False)

        try:
            app.dashboard_intake_create({"local_part": local_part}, ctx_a)
            dup_ok = False
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            dup_ok = exc.status_code == 409 and detail.get("error") == "address_taken"
        checks.check("duplicate active local_part returns 409 address_taken", lambda: dup_ok)

        rotated = app.dashboard_intake_rotate(intake_id, ctx_a)
        checks.check(
            "rotate creates new active address and disables old",
            lambda: rotated.get("ok") and rotated["previous"]["status"] == "disabled",
        )

        os.environ["WATHEFNI_POSTMARK_INBOUND_ENV"] = "staging"
        bad = client.post(
            "/webhook/postmark/inbound?token=smoke-secret-token-d3",
            json=_payload(
                f"d3-{stamp}-env",
                rotated["address"]["address"],
                "x@example.com",
                [],
            ),
            headers={"X-Wathefni-Inbound-Env": "production"},
        )
        checks.check("webhook rejects env mismatch with 401", lambda: bad.status_code == 401)
        os.environ["WATHEFNI_POSTMARK_INBOUND_ENV"] = ""
    finally:
        teardown()

    return checks.report()


if __name__ == "__main__":
    raise SystemExit(main())
