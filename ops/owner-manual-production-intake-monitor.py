#!/usr/bin/env python3
"""Owner manual PRODUCTION intake + classification journey monitor.

Observes real inbound Postmark → production for WATHEFNI only.
No synthetic CVs. No cleanup. Classification workers remain OFF.
Does not mutate production configuration beyond observation/processing snapshots.
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
    os.environ.get("OWNER_MANUAL_PROD_EVIDENCE")
    or "/opt/wathefni/production-evidence/owner-manual-intake"
)
POLL_SECONDS = float(os.environ.get("OWNER_MANUAL_POLL_SECONDS") or "15")
ORCH = "/opt/wathefni/orchestrator"
PY = "/opt/wathefni/orchestrator/.venv/bin/python"

BASELINE_MARKER = EVIDENCE / "baseline.json"
STATE_PATH = EVIDENCE / "monitor_state.json"
JOURNEYS_DIR = EVIDENCE / "journeys"
LOG_PATH = EVIDENCE / "monitor.log"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def db():
    vals: dict[str, str] = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.env").read_text().splitlines():
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


def count_sql(cur, sql: str) -> Any:
    try:
        cur.execute(sql)
        return int(cur.fetchone()["c"])
    except Exception as exc:  # noqa: BLE001
        cur.connection.rollback()
        return f"err:{type(exc).__name__}"


def mutation_snapshot(cur) -> dict[str, Any]:
    out = {}
    queries = {
        "outbound_delivery_events_total": "SELECT count(*) c FROM outbound_delivery_events",
        "application_lifecycle_events_total": "SELECT count(*) c FROM application_lifecycle_events",
        "applications_with_position_wathefni": (
            "SELECT count(*) c FROM applications WHERE company_code='WATHEFNI' AND coalesce(position_code,'')<>''"
        ),
        "applications_held_wathefni": (
            "SELECT count(*) c FROM applications WHERE company_code='WATHEFNI' "
            "AND status IN ('needs_role','import_review','import_archived')"
        ),
        "candidate_rank_evaluations_total": "SELECT count(*) c FROM candidate_rank_evaluations",
        "inbound_messages_total": "SELECT count(*) c FROM inbound_messages",
        "candidate_classification_runs_total": "SELECT count(*) c FROM candidate_classification_runs",
        "candidate_classification_suggestions_total": "SELECT count(*) c FROM candidate_classification_suggestions",
        "talent_pool_classification_jobs_total": "SELECT count(*) c FROM talent_pool_classification_jobs",
        "cv_extraction_runs_total": "SELECT count(*) c FROM cv_extraction_runs",
    }
    for key, sql in queries.items():
        out[key] = count_sql(cur, sql)
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
                "environment": "production",
                "active_intake_addresses": addresses,
                "inbound_watermark": max_recv.isoformat() if max_recv else None,
                "mutations": mutation_snapshot(cur),
                "guards": {
                    "classification_workers": "must_remain_off",
                    "cleanup": "forbidden_until_owner_confirms",
                    "synthetic_fixtures": "forbidden",
                    "external_tenants": "forbidden",
                },
            }
    BASELINE_MARKER.write_text(json.dumps(baseline, indent=2, default=str) + "\n", encoding="utf-8")
    STATE_PATH.write_text(json.dumps({"seen_inbound_ids": [], "started_at": utc_now()}, indent=2) + "\n")
    return baseline


def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"seen_inbound_ids": [], "started_at": utc_now()}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def assert_guards() -> None:
    conf = pathlib.Path(
        "/etc/systemd/system/wathefni-orchestrator.service.d/talent-pool-classification.conf"
    ).read_text(encoding="utf-8")
    if "WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off" not in conf:
        raise RuntimeError("classification_workers_not_off")
    if "WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS=WATHEFNI" not in conf:
        raise RuntimeError("canary_tenants_not_wathefni_only")


def collect_journey(inbound_id: str) -> dict[str, Any]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM inbound_messages WHERE inbound_id=%s", (inbound_id,))
            inbound = cur.fetchone()
            if not inbound:
                return {"inbound_id": inbound_id, "error": "missing"}
            # Prefer applications created near this inbound timestamp for WATHEFNI held rows
            received = inbound.get("received_at") or inbound.get("created_at")
            cur.execute(
                """
                SELECT app_key, company_code, phone, status, position_code, position_title, current_step, created_at, updated_at
                FROM applications
                WHERE company_code='WATHEFNI'
                  AND created_at >= (%s::timestamptz - interval '2 hours')
                ORDER BY created_at DESC
                LIMIT 50
                """,
                (received,),
            )
            recent_apps = [dict(r) for r in cur.fetchall()]
            app_keys = [a["app_key"] for a in recent_apps]
            docs = []
            runs = []
            suggestions = []
            if app_keys:
                cur.execute(
                    """
                    SELECT document_id, app_key, filename, document_type, source,
                           extraction_status, extraction_method, extraction_chars, metadata, created_at
                    FROM candidate_documents WHERE app_key = ANY(%s) ORDER BY created_at
                    """,
                    (app_keys,),
                )
                docs = [dict(r) for r in cur.fetchall()]
                cur.execute("SELECT * FROM candidate_classification_runs WHERE app_key = ANY(%s) ORDER BY created_at", (app_keys,))
                runs = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    """
                    SELECT suggestion_id, run_id, app_key, node_id, node_type,
                           confidence_band, confidence_score, state, evidence, created_at
                    FROM candidate_classification_suggestions WHERE app_key = ANY(%s) ORDER BY created_at
                    """,
                    (app_keys,),
                )
                suggestions = [dict(r) for r in cur.fetchall()]
            journey = {
                "collected_at": utc_now(),
                "inbound": dict(inbound),
                "recent_wathefni_applications": recent_apps,
                "extraction_documents": docs,
                "classification": {"runs": runs, "suggestions": suggestions},
                "mutations": mutation_snapshot(cur),
            }
    path = JOURNEYS_DIR / f"{inbound_id}.json"
    path.write_text(json.dumps(journey, indent=2, default=str) + "\n", encoding="utf-8")
    return {"inbound_id": inbound_id, "path": str(path), "recent_apps": len(recent_apps)}


def new_inbound_ids(state: dict[str, Any]) -> list[str]:
    seen = set(state.get("seen_inbound_ids") or [])
    baseline = json.loads(BASELINE_MARKER.read_text(encoding="utf-8")) if BASELINE_MARKER.exists() else {}
    watermark = baseline.get("inbound_watermark")
    recip = "92d69b51cdadf3b594fc08710326ff6b@inbound.postmarkapp.com"
    with db() as conn:
        with conn.cursor() as cur:
            if watermark:
                cur.execute(
                    """
                    SELECT inbound_id FROM inbound_messages
                    WHERE coalesce(received_at, created_at) > %s::timestamptz
                      AND (
                        lower(coalesce(envelope_recipient,'')) = lower(%s)
                        OR company_code='WATHEFNI'
                      )
                    ORDER BY coalesce(received_at, created_at)
                    """,
                    (watermark, recip),
                )
            else:
                cur.execute(
                    """
                    SELECT inbound_id FROM inbound_messages
                    WHERE lower(coalesce(envelope_recipient,'')) = lower(%s) OR company_code='WATHEFNI'
                    ORDER BY coalesce(received_at, created_at)
                    """,
                    (recip,),
                )
            ids = [str(r["inbound_id"]) for r in cur.fetchall()]
    return [i for i in ids if i not in seen]


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "loop"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    JOURNEYS_DIR.mkdir(parents=True, exist_ok=True)
    assert_guards()
    if mode == "baseline":
        baseline = write_baseline()
        log(f"baseline_written {baseline.get('active_intake_addresses')}")
        print(json.dumps(baseline, indent=2, default=str))
        return 0
    if not BASELINE_MARKER.exists():
        write_baseline()
    log("monitor_loop_start")
    ticks = 0
    while True:
        try:
            assert_guards()
            state = load_state()
            for inbound_id in new_inbound_ids(state):
                summary = collect_journey(inbound_id)
                state.setdefault("seen_inbound_ids", []).append(inbound_id)
                save_state(state)
                log(f"new_inbound {summary}")
            ticks += 1
            if ticks % 3 == 0:
                for inbound_id in list(state.get("seen_inbound_ids") or []):
                    collect_journey(inbound_id)
            save_state(state)
        except Exception as exc:  # noqa: BLE001
            log(f"monitor_error {type(exc).__name__}: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
