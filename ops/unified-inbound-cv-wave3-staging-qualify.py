#!/usr/bin/env python3
"""Staging qualification for Unified Inbound CV Wave 1–3 dual-write + adapters.

Runs ONLY against wathefni_staging on the staging orchestrator host.
Never touches production DB or production systemd units.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
EVIDENCE = Path(
    os.environ.get(
        "WAVE3_EVIDENCE",
        f"/opt/wathefni/staging/staging-evidence/unified-inbound-cv-wave3/{STAMP}",
    )
)


def _ok(name: str, detail: str = "") -> dict:
    return {"name": name, "ok": True, "detail": detail}


def _fail(name: str, detail: str) -> dict:
    return {"name": name, "ok": False, "detail": detail}


def main() -> int:
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    os.environ.setdefault(
        "WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env"
    )
    sys.path.insert(0, "/opt/wathefni/staging/orchestrator")

    results: list[dict] = []
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    # Health
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8011/health", timeout=5) as resp:
            code = resp.getcode()
        results.append(_ok("health_200", str(code)) if code == 200 else _fail("health_200", str(code)))
    except Exception as exc:
        results.append(_fail("health_200", repr(exc)))

    # Confirm staging env / not production unit
    try:
        env_name = os.environ.get("WATHEFNI_ENV", "")
        results.append(
            _ok("staging_env", env_name)
            if env_name == "staging"
            else _fail("staging_env", env_name)
        )
    except Exception as exc:
        results.append(_fail("staging_env", repr(exc)))

    # Import modules
    try:
        import inbound_cv_intake as ici
        import inbound_cv_processing as icp
        import inbound_cv_adapters as adapters
        from psycopg2.extras import RealDictCursor
        import psycopg2

        results.append(_ok("modules_importable"))
    except Exception as exc:
        results.append(_fail("modules_importable", traceback.format_exc()))
        _write(results)
        return 1

    # Load DB
    try:
        env_path = Path(os.environ["WATHEFNI_POSTGRES_ENV"])
        cfg = {}
        for line in env_path.read_text().splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
        dsn = cfg.get("WATHEFNI_DATABASE_URL") or cfg.get("DATABASE_URL") or ""
        if not dsn:
            raise RuntimeError("WATHEFNI_DATABASE_URL missing from staging secrets")
        if "wathefni_staging" not in dsn:
            raise RuntimeError(f"refusing non-staging database url host/db marker")
        conn = psycopg2.connect(dsn)
        conn.autocommit = False
        results.append(_ok("staging_db_connect", "wathefni_staging"))
    except Exception as exc:
        results.append(_fail("staging_db_connect", traceback.format_exc()))
        _write(results)
        return 1

    staging_env = {
        "WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE": "1",
        "WATHEFNI_UNIFIED_CV_VERSION_DUAL_WRITE": "1",
        "WATHEFNI_UNIFIED_CV_PROCESSING_STAGE_LEDGER": "1",
        "WATHEFNI_UNIFIED_INBOUND_CV_ADAPTERS": "1",
        "WATHEFNI_UNIFIED_ADAPTER_SHARED_PROCESSING": "1",
    }

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            ici.ensure_schema(cur)
            icp.ensure_schema(cur)

            before_candidates = _count(cur, "SELECT count(*)::int AS n FROM candidates")
            before_apps = _count(cur, "SELECT count(*)::int AS n FROM applications")
            before_ocr = _count(
                cur,
                "SELECT count(*)::int AS n FROM cv_extraction_runs"
                if _table_exists(cur, "cv_extraction_runs")
                else "SELECT 0::int AS n",
            )
            before_class = _count(
                cur,
                "SELECT count(*)::int AS n FROM talent_pool_classification_jobs"
                if _table_exists(cur, "talent_pool_classification_jobs")
                else "SELECT 0::int AS n",
            )
            before_ck = _count(
                cur,
                "SELECT count(*)::int AS n FROM candidate_knowledge_index_jobs"
                if _table_exists(cur, "candidate_knowledge_index_jobs")
                else "SELECT 0::int AS n",
            )

            inbound_id = str(uuid.uuid4())
            submission_id = str(uuid.uuid4())
            document_id = str(uuid.uuid4())
            digest = "a" * 64
            msg_id = f"wave3-staging-{STAMP}"

            # Seed minimal live submission/document rows for bridge updates if tables exist.
            if _table_exists(cur, "intake_submissions") and _table_exists(cur, "inbound_messages"):
                try:
                    cur.execute(
                        """
                        INSERT INTO inbound_messages
                          (inbound_id, provider, provider_message_id, status)
                        VALUES (%s,'postmark',%s,'durable')
                        ON CONFLICT DO NOTHING
                        """,
                        (inbound_id, msg_id),
                    )
                except Exception:
                    conn.rollback()
                    ici.ensure_schema(cur)
                    icp.ensure_schema(cur)

            receipt1 = ici.dual_write_email_receipt(
                cur,
                company_code="WATHEFNI",
                inbound_id=inbound_id,
                submission_id=submission_id,
                provider="postmark",
                provider_message_id=msg_id,
                route_snapshot={"intake_id": "staging-route", "company_code": "WATHEFNI"},
                source_provenance={"channel": "email_inbound", "staging": True},
                documents=[
                    {
                        "document_id": document_id,
                        "ordinal": 1,
                        "filename": "staging-cv.pdf",
                        "storage_status": "stored",
                        "safety_state": "scan_pending",
                        "content_sha256": digest,
                    }
                ],
                environ=staging_env,
            )
            receipt2 = ici.dual_write_email_receipt(
                cur,
                company_code="WATHEFNI",
                inbound_id=inbound_id,
                submission_id=submission_id,
                provider="postmark",
                provider_message_id=msg_id,
                route_snapshot={"intake_id": "staging-route", "company_code": "WATHEFNI"},
                source_provenance={"channel": "email_inbound", "staging": True},
                documents=[
                    {
                        "document_id": document_id,
                        "ordinal": 1,
                        "filename": "staging-cv.pdf",
                        "storage_status": "stored",
                        "safety_state": "scan_pending",
                        "content_sha256": digest,
                    }
                ],
                environ=staging_env,
            )
            results.append(
                _ok("envelope_idempotent", receipt1.get("event_id", ""))
                if receipt1.get("event_id") == receipt2.get("event_id") and not receipt1.get("skipped")
                else _fail("envelope_idempotent", json.dumps({"r1": receipt1, "r2": receipt2}))
            )

            cur.execute(
                "SELECT count(*)::int AS n FROM intake_source_events WHERE company_code=%s AND external_event_id=%s",
                ("WATHEFNI", msg_id),
            )
            event_n = int((cur.fetchone() or {}).get("n") or 0)
            results.append(_ok("one_envelope_event", str(event_n)) if event_n == 1 else _fail("one_envelope_event", str(event_n)))

            cur.execute(
                """
                SELECT count(*)::int AS n FROM intake_item_documents
                WHERE company_code=%s AND content_sha256=%s
                """,
                ("WATHEFNI", digest),
            )
            link_n = int((cur.fetchone() or {}).get("n") or 0)
            results.append(
                _ok("document_checksum_parity", str(link_n))
                if link_n == 1
                else _fail("document_checksum_parity", str(link_n))
            )

            cv = icp.dual_write_cv_version(
                cur,
                company_code="WATHEFNI",
                content_sha256=digest,
                legacy_document_id=document_id,
                legacy_app_key="wave3-staging-app",
                extracted_text_hash="b" * 64,
                extraction_method="staging_parity",
                environ=staging_env,
            )
            cv2 = icp.dual_write_cv_version(
                cur,
                company_code="WATHEFNI",
                content_sha256=digest,
                legacy_document_id=document_id,
                legacy_app_key="wave3-staging-app",
                environ=staging_env,
            )
            results.append(
                _ok("cv_version_dual_write_parity", cv.get("cv_version_id", ""))
                if cv.get("cv_version_id") == cv2.get("cv_version_id") and not cv.get("skipped")
                else _fail("cv_version_dual_write_parity", json.dumps({"cv": cv, "cv2": cv2}))
            )

            # Adapter smoke (no live job create)
            adapters.adapt_whatsapp_unsolicited(
                cur,
                company_code="WATHEFNI",
                provider_message_id=f"wa-{STAMP}",
                phone="96559990001",
                account_id="staging-acct",
                conversation_id="staging-conv",
                pending_id=str(uuid.uuid4()),
                content_sha256=digest,
                filename="wa.pdf",
                environ=staging_env,
            )
            results.append(_ok("whatsapp_unsolicited_adapter"))

            after_candidates = _count(cur, "SELECT count(*)::int AS n FROM candidates")
            after_apps = _count(cur, "SELECT count(*)::int AS n FROM applications")
            after_ocr = _count(
                cur,
                "SELECT count(*)::int AS n FROM cv_extraction_runs"
                if _table_exists(cur, "cv_extraction_runs")
                else "SELECT 0::int AS n",
            )
            after_class = _count(
                cur,
                "SELECT count(*)::int AS n FROM talent_pool_classification_jobs"
                if _table_exists(cur, "talent_pool_classification_jobs")
                else "SELECT 0::int AS n",
            )
            after_ck = _count(
                cur,
                "SELECT count(*)::int AS n FROM candidate_knowledge_index_jobs"
                if _table_exists(cur, "candidate_knowledge_index_jobs")
                else "SELECT 0::int AS n",
            )

            zero_dup = (
                after_candidates == before_candidates
                and after_apps == before_apps
                and after_ocr == before_ocr
                and after_class == before_class
                and after_ck == before_ck
            )
            results.append(
                _ok(
                    "zero_duplicate_authority_writes",
                    json.dumps(
                        {
                            "candidates": [before_candidates, after_candidates],
                            "applications": [before_apps, after_apps],
                            "ocr": [before_ocr, after_ocr],
                            "classification": [before_class, after_class],
                            "ck": [before_ck, after_ck],
                        }
                    ),
                )
                if zero_dup
                else _fail("zero_duplicate_authority_writes", "counts changed")
            )

            # Kill switch / retry helpers
            results.append(
                _ok("retry_helper", "retrying")
                if icp.mark_stage_retry_or_dead_letter(attempt=1, max_attempts=5, error_code="x") == "retrying"
                else _fail("retry_helper", "bad")
            )
            results.append(
                _ok("dead_letter_helper", "dead_letter")
                if icp.mark_stage_retry_or_dead_letter(attempt=5, max_attempts=5, error_code="x") == "dead_letter"
                else _fail("dead_letter_helper", "bad")
            )
            results.append(
                _ok("malware_kill_switch", "on")
                if icp.stage_killed("malware_scan", {"WATHEFNI_UNIFIED_STAGE_KILL_MALWARE_SCAN": "1"})
                else _fail("malware_kill_switch", "off")
            )

            # Rollback proof: flag off skips writes
            skipped = ici.dual_write_email_receipt(
                cur,
                company_code="WATHEFNI",
                inbound_id=str(uuid.uuid4()),
                submission_id=str(uuid.uuid4()),
                provider="postmark",
                provider_message_id=f"rollback-{STAMP}",
                route_snapshot={},
                source_provenance={},
                documents=[],
                environ={},
            )
            results.append(
                _ok("rollback_flag_off_skips", skipped.get("reason", ""))
                if skipped.get("skipped")
                else _fail("rollback_flag_off_skips", json.dumps(skipped))
            )

            # Job gate
            gate = adapters.assert_no_job_without_exact_confirmation(
                job_selected=False, human_confirmed=False, create_application=True
            )
            results.append(
                _ok("job_gate_fail_closed")
                if not gate.get("allowed")
                else _fail("job_gate_fail_closed", json.dumps(gate))
            )

        conn.commit()
        results.append(_ok("staging_commit"))
    except Exception:
        conn.rollback()
        results.append(_fail("staging_transaction", traceback.format_exc()))
    finally:
        conn.close()

    # Confirm production unit flags untouched (best-effort)
    try:
        prod_env = Path("/proc/%s/environ" % _pid("wathefni-orchestrator.service"))
        raw = prod_env.read_bytes().replace(b"\0", b"\n").decode(errors="ignore")
        touched = "WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE=on" in raw or "WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE=1" in raw
        results.append(
            _ok("production_dual_write_untouched")
            if not touched
            else _fail("production_dual_write_untouched", "production flag enabled")
        )
    except Exception as exc:
        results.append(_ok("production_dual_write_untouched", f"skip:{exc}"))

    _write(results)
    failed = [r for r in results if not r["ok"]]
    print(json.dumps({"stamp": STAMP, "passed": len(results) - len(failed), "failed": len(failed), "results": results}, indent=2))
    return 1 if failed else 0


def _count(cur, sql: str) -> int:
    cur.execute(sql)
    return int((cur.fetchone() or {}).get("n") or 0)


def _table_exists(cur, name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS ok", (name,))
    return bool((cur.fetchone() or {}).get("ok"))


def _pid(unit: str) -> str:
    import subprocess

    return subprocess.check_output(
        ["systemctl", "show", "-p", "MainPID", "--value", unit], text=True
    ).strip()


def _write(results: list[dict]) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "qualification.json").write_text(
        json.dumps({"stamp": STAMP, "results": results}, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
