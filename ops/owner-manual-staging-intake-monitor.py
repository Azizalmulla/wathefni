#!/usr/bin/env python3
"""Owner manual staging intake + classification journey monitor.

Observes real inbound Postmark → staging durable ingress for WATHEFNI.
Does NOT create synthetic CVs. Does NOT clean up. Does NOT start classification
workers. Does NOT send outreach (sender_acknowledgment job type excluded;
WATHEFNI_SENDER_ACKNOWLEDGMENT must remain off; delivery dry_run expected).

Runs on the staging host only.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

EVIDENCE = pathlib.Path(
    os.environ.get("OWNER_MANUAL_EVIDENCE")
    or "/opt/wathefni/staging/staging-evidence/owner-manual-intake"
)
POLL_SECONDS = float(os.environ.get("OWNER_MANUAL_POLL_SECONDS") or "15")
WORKER = "/opt/wathefni/staging/orchestrator/durable-email-ingress-worker.py"
PY = "/opt/wathefni/orchestrator/.venv/bin/python"
ORCH = "/opt/wathefni/staging/orchestrator"

# Intake pipeline only — never sender acknowledgment; never classification workers.
INTAKE_JOB_TYPES = [
    "intake_validation",
    "file_safety_scan",
    "accepted_intake_preparation",
    "cv_extraction",
    "profile_structuring",
    "embedding",
    "retention_privacy",
]

BASELINE_MARKER = EVIDENCE / "baseline.json"
STATE_PATH = EVIDENCE / "monitor_state.json"
JOURNEYS_DIR = EVIDENCE / "journeys"
LOG_PATH = EVIDENCE / "monitor.log"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def db():
    vals: dict[str, str] = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.staging.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return psycopg2.connect(vals["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor)


def log(msg: str) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    line = f"{utc_now()} {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def count_sql(cur, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    return int(cur.fetchone()["c"])


def mutation_snapshot(cur) -> dict[str, Any]:
    """Counts used for no-outreach / no-job-link / no-admit proof."""
    out: dict[str, Any] = {}
    queries = {
        "outbound_delivery_events_total": "SELECT count(*) c FROM outbound_delivery_events",
        "application_lifecycle_events_total": "SELECT count(*) c FROM application_lifecycle_events",
        "applications_with_position": (
            "SELECT count(*) c FROM applications WHERE company_code='WATHEFNI' "
            "AND coalesce(position_code,'') <> ''"
        ),
        "applications_held_needs_role": (
            "SELECT count(*) c FROM applications WHERE company_code='WATHEFNI' "
            "AND status IN ('needs_role','import_review','import_archived')"
        ),
        "candidate_rank_evaluations_total": "SELECT count(*) c FROM candidate_rank_evaluations",
        "intake_processing_jobs_total": "SELECT count(*) c FROM intake_processing_jobs",
        "inbound_messages_total": "SELECT count(*) c FROM inbound_messages",
        "talent_pool_classification_jobs_total": "SELECT count(*) c FROM talent_pool_classification_jobs",
        "candidate_classification_runs_total": "SELECT count(*) c FROM candidate_classification_runs",
        "sender_acknowledgment_jobs": (
            "SELECT count(*) c FROM intake_processing_jobs WHERE job_type='sender_acknowledgment'"
        ),
    }
    for key, sql in queries.items():
        try:
            out[key] = count_sql(cur, sql)
        except Exception as exc:  # noqa: BLE001
            cur.connection.rollback()
            out[key] = f"err:{type(exc).__name__}"
    return out


def write_baseline() -> dict[str, Any]:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    JOURNEYS_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT local_part || '@' || domain AS address, company_code, status, position_code, intake_id
                FROM intake_addresses WHERE status='active'
                """
            )
            addresses = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT coalesce(max(received_at), max(created_at)) AS m FROM inbound_messages")
            max_recv = cur.fetchone()["m"]
            baseline = {
                "captured_at": utc_now(),
                "active_intake_addresses": addresses,
                "inbound_watermark": max_recv.isoformat() if max_recv else None,
                "mutations": mutation_snapshot(cur),
                "guards": {
                    "classification_workers": "must_remain_off",
                    "sender_acknowledgment_job_type": "excluded_from_monitor_worker",
                    "cleanup": "forbidden_until_owner_confirms",
                    "synthetic_fixtures": "forbidden",
                    "production": "untouched",
                },
            }
    BASELINE_MARKER.write_text(json.dumps(baseline, indent=2, default=str) + "\n", encoding="utf-8")
    STATE_PATH.write_text(
        json.dumps({"seen_inbound_ids": [], "started_at": utc_now()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return baseline


def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"seen_inbound_ids": [], "started_at": utc_now()}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def run_intake_worker_once() -> dict[str, Any]:
    env = {
        **os.environ,
        "WATHEFNI_ENV": "staging",
        "WATHEFNI_ENVIRONMENT": "staging",
        "WATHEFNI_POSTGRES_ENV": "/root/.openclaw/secrets/postgres.staging.env",
        "WATHEFNI_WORKSPACE": "/opt/wathefni/staging/workspace",
        "WATHEFNI_EXPECTED_DATABASE_HOST": "127.0.0.1",
        "WATHEFNI_EXPECTED_DATABASE_PORT": "5432",
        "WATHEFNI_EXPECTED_DATABASE_NAME": "wathefni_staging",
        "WATHEFNI_DATABASE_ENVIRONMENT_MARKER": "wathefni-staging-hr2-isolation-v1",
        "WATHEFNI_DELIVERY_MODE": "dry_run",
        "PYTHONPATH": ORCH,
    }
    cmd = [PY, WORKER, "--limit", "25"]
    for jt in INTAKE_JOB_TYPES:
        cmd.extend(["--job-type", jt])
    proc = subprocess.run(cmd, cwd=ORCH, env=env, capture_output=True, text=True, timeout=600)
    raw = (proc.stdout or "").strip().splitlines()
    last = raw[-1] if raw else ""
    try:
        payload = json.loads(last) if last else {"raw": proc.stdout, "stderr": proc.stderr}
    except json.JSONDecodeError:
        payload = {"raw": proc.stdout, "stderr": proc.stderr, "rc": proc.returncode}
    payload["rc"] = proc.returncode
    return payload


def collect_journey(inbound_id: str) -> dict[str, Any]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM inbound_messages WHERE inbound_id=%s", (inbound_id,))
            inbound = cur.fetchone()
            if not inbound:
                return {"inbound_id": inbound_id, "error": "missing"}
            company = inbound.get("company_code")
            cur.execute(
                "SELECT * FROM intake_submissions WHERE inbound_id=%s ORDER BY created_at",
                (inbound_id,),
            )
            submissions = [dict(r) for r in cur.fetchall()]
            cur.execute(
                """
                SELECT * FROM intake_documents
                WHERE inbound_id=%s OR submission_id = ANY(%s)
                ORDER BY created_at
                """,
                (inbound_id, [s.get("submission_id") for s in submissions] or ["__none__"]),
            )
            documents = [dict(r) for r in cur.fetchall()]
            subject_ids = [inbound_id]
            subject_ids.extend(str(s.get("submission_id")) for s in submissions if s.get("submission_id"))
            subject_ids.extend(str(d.get("document_id")) for d in documents if d.get("document_id"))
            cur.execute(
                """
                SELECT * FROM intake_processing_jobs
                WHERE subject_id = ANY(%s)
                ORDER BY created_at
                """,
                (subject_ids,),
            )
            jobs = [dict(r) for r in cur.fetchall()]
            app_keys: list[str] = []
            for d in documents:
                if d.get("app_key"):
                    app_keys.append(str(d["app_key"]))
                meta = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
                if meta.get("app_key"):
                    app_keys.append(str(meta["app_key"]))
            for job in jobs:
                payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
                result = job.get("result") if isinstance(job.get("result"), dict) else {}
                for blob in (payload, result):
                    if blob.get("app_key"):
                        app_keys.append(str(blob["app_key"]))
            app_keys = sorted({k for k in app_keys if k})
            applications: list[dict[str, Any]] = []
            classifications: dict[str, Any] = {"runs": [], "suggestions": []}
            extraction: list[dict[str, Any]] = []
            if app_keys:
                cur.execute(
                    "SELECT app_key, company_code, phone, status, position_code, position_title, current_step, created_at, updated_at "
                    "FROM applications WHERE app_key = ANY(%s)",
                    (app_keys,),
                )
                applications = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    """
                    SELECT *
                    FROM candidate_classification_runs WHERE app_key = ANY(%s) ORDER BY created_at
                    """,
                    (app_keys,),
                )
                classifications["runs"] = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    """
                    SELECT suggestion_id, run_id, app_key, node_id, node_type,
                           confidence_band, confidence_score, state, evidence, created_at
                    FROM candidate_classification_suggestions WHERE app_key = ANY(%s) ORDER BY created_at
                    """,
                    (app_keys,),
                )
                classifications["suggestions"] = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    """
                    SELECT document_id, app_key, filename, document_type, source,
                           extraction_status, extraction_method, extraction_chars, metadata, created_at
                    FROM candidate_documents WHERE app_key = ANY(%s) ORDER BY created_at
                    """,
                    (app_keys,),
                )
                extraction = [dict(r) for r in cur.fetchall()]
            journey = {
                "collected_at": utc_now(),
                "inbound": dict(inbound),
                "submissions": submissions,
                "documents": documents,
                "jobs": jobs,
                "app_keys": app_keys,
                "applications": applications,
                "extraction_documents": extraction,
                "classification": classifications,
                "mutations": mutation_snapshot(cur),
                "company_code": company,
            }
    path = JOURNEYS_DIR / f"{inbound_id}.json"
    path.write_text(json.dumps(journey, indent=2, default=str) + "\n", encoding="utf-8")
    return {"inbound_id": inbound_id, "path": str(path), "app_keys": app_keys, "job_count": len(jobs)}


def new_inbound_ids(state: dict[str, Any]) -> list[str]:
    seen = set(state.get("seen_inbound_ids") or [])
    baseline = json.loads(BASELINE_MARKER.read_text(encoding="utf-8")) if BASELINE_MARKER.exists() else {}
    watermark = baseline.get("inbound_watermark")
    with db() as conn:
        with conn.cursor() as cur:
            if watermark:
                cur.execute(
                    """
                    SELECT inbound_id FROM inbound_messages
                    WHERE coalesce(received_at, created_at) > %s::timestamptz
                    ORDER BY coalesce(received_at, created_at)
                    """,
                    (watermark,),
                )
            else:
                cur.execute(
                    "SELECT inbound_id FROM inbound_messages ORDER BY coalesce(received_at, created_at)"
                )
            ids = [str(r["inbound_id"]) for r in cur.fetchall()]
    return [i for i in ids if i not in seen]


def assert_guards() -> None:
    # Classification workers must stay off in staging drop-in + live process.
    conf = pathlib.Path(
        "/etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf"
    ).read_text(encoding="utf-8")
    if "WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off" not in conf:
        raise RuntimeError("classification_workers_not_off_in_dropin")
    if pathlib.Path("/etc/systemd/system/wathefni-intake-worker-staging.service").exists():
        # Ensure the persistent systemd intake worker is not enabled (we use one-shot monitor).
        enabled = subprocess.run(
            ["systemctl", "is-enabled", "wathefni-intake-worker-staging.service"],
            capture_output=True,
            text=True,
        )
        if enabled.stdout.strip() == "enabled":
            raise RuntimeError("persistent_intake_worker_enabled_forbidden_for_this_phase")


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "loop"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    JOURNEYS_DIR.mkdir(parents=True, exist_ok=True)
    assert_guards()
    if mode == "baseline":
        baseline = write_baseline()
        log(f"baseline_written addresses={baseline.get('active_intake_addresses')}")
        print(json.dumps(baseline, indent=2, default=str))
        return 0
    if mode == "once":
        if not BASELINE_MARKER.exists():
            write_baseline()
        state = load_state()
        worker = run_intake_worker_once()
        log(f"worker_once processed={worker.get('processed')} rc={worker.get('rc')}")
        for inbound_id in new_inbound_ids(state):
            summary = collect_journey(inbound_id)
            state.setdefault("seen_inbound_ids", []).append(inbound_id)
            log(f"journey {summary}")
        save_state(state)
        print(json.dumps({"worker": worker, "state": state}, indent=2, default=str))
        return 0

    # loop
    if not BASELINE_MARKER.exists():
        write_baseline()
        log("baseline_created")
    log("monitor_loop_start")
    refresh_every = max(1, int(os.environ.get("OWNER_MANUAL_REFRESH_EVERY") or "3"))
    ticks = 0
    while True:
        try:
            assert_guards()
            state = load_state()
            worker = run_intake_worker_once()
            processed = int(worker.get("processed") or 0)
            if processed:
                log(f"worker_processed={processed}")
            for inbound_id in new_inbound_ids(state):
                summary = collect_journey(inbound_id)
                state.setdefault("seen_inbound_ids", []).append(inbound_id)
                save_state(state)
                log(f"new_inbound journey={summary}")
            ticks += 1
            # Re-snapshot known journeys so manual classification/review appears without cleanup.
            if ticks % refresh_every == 0:
                for inbound_id in list(state.get("seen_inbound_ids") or []):
                    collect_journey(inbound_id)
            save_state(state)
        except Exception as exc:  # noqa: BLE001
            log(f"monitor_error {type(exc).__name__}: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
