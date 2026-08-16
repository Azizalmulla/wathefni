#!/usr/bin/env python3
"""Read-only WATHEFNI automatic email-classification canary monitor."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
from datetime import datetime, timezone
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


EVIDENCE = pathlib.Path(
    os.environ.get("WATHEFNI_AUTO_CLASSIFICATION_EVIDENCE")
    or "/opt/wathefni/production-evidence/talent-pool-auto-email-canary/20260726T012324Z"
)
START_PATH = EVIDENCE / "proofs" / "canary-started-at.txt"
STATE_PATH = EVIDENCE / "monitor-state.json"
JOURNEYS = EVIDENCE / "journeys"
RECIPIENT = "92d69b51cdadf3b594fc08710326ff6b@inbound.postmarkapp.com"


def db():
    values: dict[str, str] = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    return psycopg2.connect(values["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def start() -> str:
    return START_PATH.read_text(encoding="utf-8").strip()


def assert_guards() -> None:
    auto_conf = pathlib.Path(
        "/etc/systemd/system/wathefni-orchestrator.service.d/"
        "talent-pool-auto-email-classification.conf"
    ).read_text(encoding="utf-8")
    classification_conf = pathlib.Path(
        "/etc/systemd/system/wathefni-orchestrator.service.d/"
        "talent-pool-classification.conf"
    ).read_text(encoding="utf-8")
    sender_conf = pathlib.Path(
        "/etc/systemd/system/wathefni-orchestrator.service.d/"
        "sender-acknowledgment-off.conf"
    ).read_text(encoding="utf-8")
    if "WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION=on" not in auto_conf:
        raise RuntimeError("automatic_classification_not_enabled")
    if "WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_TENANTS=WATHEFNI" not in auto_conf:
        raise RuntimeError("automatic_classification_tenant_not_exact")
    if f"WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_RECIPIENT={RECIPIENT}" not in auto_conf:
        raise RuntimeError("automatic_classification_recipient_not_exact")
    if "WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off" not in classification_conf:
        raise RuntimeError("generic_workers_not_off")
    if "WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS=WATHEFNI" not in classification_conf:
        raise RuntimeError("classification_tenant_not_exact")
    if "WATHEFNI_SENDER_ACKNOWLEDGMENT=off" not in sender_conf:
        raise RuntimeError("sender_acknowledgment_not_off")


def _rows(cur: Any, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def collect(inbound_id: str) -> dict[str, Any]:
    assert_guards()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM inbound_messages WHERE inbound_id=%s", (inbound_id,))
            inbound = dict(cur.fetchone() or {})
            if not inbound:
                raise RuntimeError("inbound_message_missing")
            batch_id = inbound.get("batch_id")
            items = (
                _rows(cur, "SELECT * FROM import_items WHERE batch_id=%s ORDER BY created_at", (batch_id,))
                if batch_id
                else []
            )
            app_keys = sorted({str(row.get("app_key")) for row in items if row.get("app_key")})
            if not app_keys and batch_id:
                documents = _rows(
                    cur,
                    """
                    SELECT * FROM candidate_documents
                    WHERE metadata->>'import_batch_id'=%s
                    ORDER BY created_at
                    """,
                    (str(batch_id),),
                )
                app_keys = sorted({str(row["app_key"]) for row in documents})
            else:
                documents = (
                    _rows(
                        cur,
                        """
                        SELECT * FROM candidate_documents
                        WHERE app_key=ANY(%s) AND created_at >= %s
                        ORDER BY created_at
                        """,
                        (app_keys, start()),
                    )
                    if app_keys
                    else []
                )
            document_ids = [str(row["document_id"]) for row in documents]
            applications = (
                _rows(
                    cur,
                    """
                    SELECT app_key, company_code, status, position_code, current_step,
                           created_at, updated_at
                    FROM applications WHERE app_key=ANY(%s)
                    """,
                    (app_keys,),
                )
                if app_keys
                else []
            )
            text_versions = (
                _rows(
                    cur,
                    """
                    SELECT version_id, app_key, document_id, source_content_sha256,
                           extracted_text_hash, extraction_finalization_id, evidence_id,
                           facts_id, extraction_method, status, is_current, created_at,
                           superseded_at
                    FROM candidate_cv_text_versions
                    WHERE document_id::text=ANY(%s)
                    ORDER BY created_at
                    """,
                    (document_ids,),
                )
                if document_ids
                else []
            )
            extraction_runs = (
                _rows(
                    cur,
                    """
                    SELECT * FROM cv_extraction_runs
                    WHERE document_id::text=ANY(%s) ORDER BY created_at
                    """,
                    (document_ids,),
                )
                if document_ids
                else []
            )
            finalizations = (
                _rows(
                    cur,
                    """
                    SELECT * FROM cv_extraction_finalizations
                    WHERE document_id::text=ANY(%s) ORDER BY created_at
                    """,
                    (document_ids,),
                )
                if document_ids
                else []
            )
            jobs = (
                _rows(
                    cur,
                    """
                    SELECT job_id, company_code, app_key, job_type, idempotency_key,
                           status, attempt_count,
                           last_error, dead_letter, payload, created_at, available_at,
                           claimed_at, completed_at, dead_lettered_at, claim_owner, updated_at
                    FROM talent_pool_classification_jobs
                    WHERE app_key=ANY(%s) AND payload->>'source'='automatic_post_extraction'
                    ORDER BY created_at
                    """,
                    (app_keys,),
                )
                if app_keys
                else []
            )
            runs = (
                _rows(
                    cur,
                    "SELECT * FROM candidate_classification_runs WHERE app_key=ANY(%s) ORDER BY created_at",
                    (app_keys,),
                )
                if app_keys
                else []
            )
            suggestions = (
                _rows(
                    cur,
                    """
                    SELECT suggestion_id, run_id, app_key, node_id, node_type,
                           confidence_score, confidence_band, evidence, state, created_at
                    FROM candidate_classification_suggestions
                    WHERE app_key=ANY(%s) ORDER BY created_at
                    """,
                    (app_keys,),
                )
                if app_keys
                else []
            )
            protected: dict[str, Any] = {}
            for table in (
                "application_lifecycle_events",
                "candidate_rank_evaluations",
                "outbound_delivery_events",
            ):
                cur.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name=%s",
                    (table,),
                )
                columns = {row["column_name"] for row in cur.fetchall()}
                key = next((name for name in ("app_key", "application_key", "subject_key") if name in columns), None)
                if key and app_keys:
                    cur.execute(f"SELECT count(*) AS count FROM {table} WHERE {key}=ANY(%s)", (app_keys,))
                    protected[table] = int(cur.fetchone()["count"])
                else:
                    protected[table] = None
    ocr_runs = [
        row
        for row in extraction_runs
        if str(row.get("tier") or "").lower() not in {"", "poppler", "local"}
        or "ocr" in str(row.get("stage") or "").lower()
        or "vision" in str(row.get("actual_request_model") or "").lower()
    ]
    for job in jobs:
        created_at = job.get("created_at")
        completed_at = job.get("completed_at")
        job["end_to_end_latency_seconds"] = (
            (completed_at - created_at).total_seconds()
            if created_at and completed_at
            else None
        )
    journey = {
        "collected_at": now(),
        "inbound": inbound,
        "import_items": items,
        "applications": applications,
        "documents": documents,
        "immutable_text_versions": text_versions,
        "extraction_runs": extraction_runs,
        "extraction_finalizations": finalizations,
        "ocr_trigger_count": len(ocr_runs),
        "classification_jobs": jobs,
        "classification_runs": runs,
        "classification_suggestions": suggestions,
        "protected_mutations": protected,
        "cleanup_performed": False,
    }
    JOURNEYS.mkdir(parents=True, exist_ok=True)
    output = JOURNEYS / f"{inbound_id}.automatic.json"
    output.write_text(json.dumps(journey, indent=2, default=str) + "\n", encoding="utf-8")
    return journey


def new_inbound_ids(seen: set[str]) -> list[str]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT inbound_id FROM inbound_messages
                WHERE coalesce(received_at, created_at) >= %s
                  AND (
                    lower(coalesce(envelope_recipient,''))=lower(%s)
                    OR company_code='WATHEFNI'
                  )
                ORDER BY coalesce(received_at, created_at)
                """,
                (start(), RECIPIENT),
            )
            return [str(row["inbound_id"]) for row in cur.fetchall() if str(row["inbound_id"]) not in seen]


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"
    assert_guards()
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {"seen": [], "started_at": now()}
    while True:
        seen = set(state.get("seen") or [])
        for inbound_id in new_inbound_ids(seen):
            collect(inbound_id)
            state.setdefault("seen", []).append(inbound_id)
            STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")
        STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")
        if mode != "loop":
            break
        time.sleep(15)
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
