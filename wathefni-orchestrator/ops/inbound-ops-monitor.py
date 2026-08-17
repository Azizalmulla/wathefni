#!/usr/bin/env python3
"""Operational monitor for continuous WATHEFNI inbound Talent Pool automation.

Read-only snapshots + platform-ops alert delivery.
Never sends messages to candidates. Never surfaces alerts to normal HR.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(
    os.environ.get("WATHEFNI_INBOUND_OPS_MONITOR_ROOT")
    or "/var/lib/wathefni/inbound-ops-monitor"
)
RECIPIENT = "92d69b51cdadf3b594fc08710326ff6b@inbound.postmarkapp.com"

# Thresholds (seconds / counts) — platform ops, not HR.
PENDING_JOB_MAX_AGE_SEC = int(os.environ.get("WATHEFNI_OPS_PENDING_JOB_MAX_AGE_SEC") or 900)
RUNNING_JOB_MAX_AGE_SEC = int(os.environ.get("WATHEFNI_OPS_RUNNING_JOB_MAX_AGE_SEC") or 600)
PENDING_ASYNC_MAX_AGE_SEC = int(
    os.environ.get("WATHEFNI_OPS_PENDING_ASYNC_MAX_AGE_SEC") or 1800
)
QUEUE_DEPTH_ALERT = int(os.environ.get("WATHEFNI_OPS_QUEUE_DEPTH_ALERT") or 25)
OCR_FAILURE_ALERT_24H = int(os.environ.get("WATHEFNI_OPS_OCR_FAILURE_ALERT_24H") or 3)
CK_FAILURE_ALERT_1H = int(os.environ.get("WATHEFNI_OPS_CK_FAILURE_ALERT_1H") or 5)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dburl() -> str:
    for line in Path("/root/.openclaw/secrets/postgres.env").read_text().splitlines():
        if line.startswith("WATHEFNI_DATABASE_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("database_url_missing")


def unit_state(unit: str, action: str = "is-active") -> str:
    run = subprocess.run(["systemctl", action, unit], text=True, capture_output=True)
    return (run.stdout or run.stderr).strip() or f"rc={run.returncode}"


def _load_healthcheck_env() -> dict[str, str]:
    path = Path(
        os.environ.get("WATHEFNI_HEALTHCHECK_ENV")
        or "/root/.openclaw/secrets/healthcheck.env"
    )
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def deliver_platform_alerts(alerts: list[str], *, captured_at: str) -> dict[str, Any]:
    """Actively deliver alerts to platform ops (Healthchecks + journal + Postmark).

    Local JSON is retained as evidence. Delivery channels:
    1. journal CRITICAL lines (logger)
    2. Healthchecks success/fail ping when WATHEFNI_OPS_ALERT_HEALTHCHECK_URL is set
    3. Postmark email to WATHEFNI_OPS_ALERT_EMAIL on alert-set changes
    """
    env = _load_healthcheck_env()
    pg_env: dict[str, str] = {}
    pg_path = Path("/root/.openclaw/secrets/postgres.env")
    if pg_path.is_file():
        for line in pg_path.read_text().splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            pg_env[key.strip()] = value.strip().strip('"').strip("'")

    ping_url = (
        os.environ.get("WATHEFNI_OPS_ALERT_HEALTHCHECK_URL")
        or env.get("WATHEFNI_OPS_ALERT_HEALTHCHECK_URL")
        or ""
    ).strip()
    alert_email = (
        os.environ.get("WATHEFNI_OPS_ALERT_EMAIL")
        or env.get("WATHEFNI_OPS_ALERT_EMAIL")
        or "azizalmulla16@gmail.com"
    ).strip()
    result: dict[str, Any] = {
        "captured_at": captured_at,
        "alert_count": len(alerts),
        "healthchecks": {"configured": bool(ping_url), "ok": False, "mode": None},
        "postmark": {"configured": False, "ok": False, "skipped": True},
        "journal": {"written": 0},
    }
    for name in alerts:
        line = f"wathefni_platform_ops_alert alert={name} captured_at={captured_at}"
        subprocess.run(
            ["logger", "-t", "wathefni-inbound-ops-monitor", "-p", "daemon.crit", line],
            check=False,
        )
        result["journal"]["written"] += 1

    if ping_url:
        target = ping_url.rstrip("/")
        if alerts:
            if not target.endswith("/fail"):
                target = f"{target}/fail"
            result["healthchecks"]["mode"] = "fail"
        else:
            if target.endswith("/fail"):
                target = target[: -len("/fail")]
            result["healthchecks"]["mode"] = "success"
        try:
            req = urllib.request.Request(target, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result["healthchecks"]["ok"] = 200 <= int(resp.status) < 300
                result["healthchecks"]["status"] = int(resp.status)
        except urllib.error.HTTPError as exc:
            result["healthchecks"]["ok"] = False
            result["healthchecks"]["status"] = int(exc.code)
            result["healthchecks"]["error"] = str(exc.reason)
        except Exception as exc:  # noqa: BLE001
            result["healthchecks"]["ok"] = False
            result["healthchecks"]["error"] = type(exc).__name__
    else:
        result["healthchecks"]["error"] = "WATHEFNI_OPS_ALERT_HEALTHCHECK_URL_missing"

    prev_path = ROOT / "alerts.delivered.json"
    prev_alerts: list[str] = []
    if prev_path.is_file():
        try:
            prev_alerts = list(json.loads(prev_path.read_text()).get("alerts") or [])
        except Exception:
            prev_alerts = []
    changed = sorted(alerts) != sorted(prev_alerts)
    token = pg_env.get("WATHEFNI_POSTMARK_SERVER_TOKEN") or ""
    from_email = (
        os.environ.get("WATHEFNI_OPS_ALERT_FROM")
        or env.get("WATHEFNI_OPS_ALERT_FROM")
        or pg_env.get("WATHEFNI_OUTBOUND_FROM")
        or "no-reply@octo-hr.com"
    )
    result["postmark"]["configured"] = bool(token and alert_email)
    if changed and alerts and token and alert_email:
        result["postmark"]["skipped"] = False
        body = {
            "From": from_email,
            "To": alert_email,
            "Subject": f"[OctoHR platform ops] {len(alerts)} alert(s)",
            "TextBody": (
                f"Platform operations alerts at {captured_at} (not for HR):\n\n"
                + "\n".join(f"- {a}" for a in alerts)
                + "\n\nSource: wathefni-inbound-ops-monitor\n"
            ),
            "MessageStream": pg_env.get("WATHEFNI_POSTMARK_MESSAGE_STREAM") or "outbound",
        }
        try:
            req = urllib.request.Request(
                "https://api.postmarkapp.com/email",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Postmark-Server-Token": token,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
            result["postmark"]["ok"] = bool(parsed.get("MessageID"))
            result["postmark"]["message_id"] = parsed.get("MessageID")
            result["postmark"]["error_code"] = parsed.get("ErrorCode")
        except Exception as exc:  # noqa: BLE001
            result["postmark"]["ok"] = False
            result["postmark"]["error"] = type(exc).__name__
    elif not alerts and changed:
        result["postmark"]["skipped"] = True
        result["postmark"]["reason"] = "alerts_cleared"
    else:
        result["postmark"]["reason"] = "unchanged" if not changed else "missing_token_or_email"

    prev_path.write_text(json.dumps({"captured_at": captured_at, "alerts": alerts}, indent=2) + "\n")
    return result


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    stamp = utc_now()
    started_at = ""
    for line in Path("/root/.openclaw/secrets/wathefni-intake.env").read_text().splitlines():
        if line.startswith("WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_STARTED_AT="):
            started_at = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

    with psycopg2.connect(dburl(), cursor_factory=RealDictCursor) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  (SELECT count(*) FROM intake_processing_jobs
                     WHERE status IN ('pending','running','retrying','waiting_quota','waiting_budget')
                  ) AS intake_queue_depth,
                  (SELECT count(*) FROM talent_pool_classification_jobs
                     WHERE status IN ('queued','retrying','processing') AND dead_letter=false
                  ) AS classification_queue_depth,
                  (SELECT extract(epoch FROM (now() - min(available_at)))::bigint
                     FROM intake_processing_jobs
                     WHERE status IN ('pending','retrying','waiting_quota','waiting_budget')
                       AND available_at <= now()
                  ) AS oldest_intake_pending_age_seconds,
                  (SELECT extract(epoch FROM (now() - min(started_at)))::bigint
                     FROM intake_processing_jobs
                     WHERE status='running' AND started_at IS NOT NULL
                  ) AS oldest_intake_running_age_seconds,
                  (SELECT extract(epoch FROM (now() - min(created_at)))::bigint
                     FROM talent_pool_classification_jobs
                     WHERE status IN ('queued','retrying') AND dead_letter=false
                       AND available_at <= now()
                  ) AS oldest_classification_pending_age_seconds,
                  (SELECT count(*) FROM intake_processing_jobs
                     WHERE status='completed'
                       AND completed_at >= now() - interval '24 hours'
                  ) AS intake_success_24h,
                  (SELECT count(*) FROM intake_processing_jobs
                     WHERE status='dead_letter'
                       AND coalesce(completed_at,updated_at) >= now() - interval '24 hours'
                  ) AS intake_dead_letter_24h,
                  (SELECT count(*) FROM intake_processing_jobs
                     WHERE status='retrying'
                  ) AS intake_retrying,
                  (SELECT count(*) FROM talent_pool_classification_jobs
                     WHERE status='completed'
                       AND completed_at >= now() - interval '24 hours'
                  ) AS classification_success_24h,
                  (SELECT count(*) FROM talent_pool_classification_jobs
                     WHERE dead_letter=true
                       AND coalesce(dead_lettered_at,completed_at,updated_at) >= now() - interval '24 hours'
                  ) AS classification_dead_letter_24h,
                  (SELECT count(*) FROM talent_pool_classification_jobs
                     WHERE status='retrying' AND dead_letter=false
                  ) AS classification_retrying,
                  (SELECT count(*) FROM inbound_attachment_scan_decisions
                     WHERE state IN ('malware_detected','scan_failed','scanner_unavailable','timeout')
                       AND created_at >= now() - interval '24 hours'
                  ) AS scan_failure_24h,
                  (SELECT count(*) FROM inbound_attachment_scan_decisions
                     WHERE state='malware_detected'
                       AND created_at >= now() - interval '24 hours'
                  ) AS malware_detected_24h,
                  (SELECT count(*) FROM inbound_cv_identity_reviews
                     WHERE status='open'
                  ) AS open_identity_reviews,
                  (SELECT count(*) FROM inbound_cv_identity_resolutions
                     WHERE outcome IN ('conflict','held_review','unsafe')
                       AND created_at >= now() - interval '24 hours'
                  ) AS identity_conflicts_24h,
                  (SELECT count(*) FROM candidate_documents
                     WHERE extraction_status IN ('failed','error')
                       AND updated_at >= now() - interval '24 hours'
                  ) AS extraction_failures_24h,
                  (SELECT count(*) FROM cv_extraction_runs
                     WHERE provider='mistral'
                       AND coalesce(error,'') <> ''
                       AND created_at >= now() - interval '24 hours'
                  ) AS ocr_provider_failures_24h,
                  (SELECT count(*) FROM candidate_cv_text_versions
                     WHERE extraction_method ILIKE '%%ocr%%'
                       AND created_at >= now() - interval '24 hours'
                  ) AS ocr_versions_24h,
                  (SELECT coalesce(avg(extract(epoch FROM (completed_at - created_at))),0)::numeric(12,3)
                     FROM talent_pool_classification_jobs
                     WHERE status='completed'
                       AND completed_at >= now() - interval '24 hours'
                       AND completed_at IS NOT NULL
                  ) AS classification_latency_avg_seconds_24h,
                  (SELECT count(*) FROM intake_processing_jobs
                     WHERE company_code <> 'WATHEFNI'
                       AND status IN ('pending','running','retrying','waiting_quota','waiting_budget')
                  ) AS non_wathefni_active_intake_jobs,
                  (SELECT count(*) FROM talent_pool_classification_jobs
                     WHERE company_code <> 'WATHEFNI'
                       AND status IN ('queued','retrying','processing')
                       AND dead_letter=false
                  ) AS non_wathefni_active_classification_jobs,
                  (SELECT count(*) FROM intake_submissions
                     WHERE lower(envelope_recipient) <> lower(%s)
                       AND durable_at >= coalesce(%s::timestamptz, '-infinity'::timestamptz)
                  ) AS post_activation_recipient_violations,
                  (SELECT count(*) FROM applications a
                     WHERE a.company_code='WATHEFNI'
                       AND a.status IN ('needs_role','import_review')
                       AND coalesce(a.position_code,'') <> ''
                       AND a.updated_at::text >= coalesce(%s, '')
                  ) AS held_with_job_binding_suspect,
                  (SELECT count(*) FROM applications
                     WHERE raw_json->'cv'->'processing'->>'status'='pending_async_processing'
                       AND coalesce(
                             (raw_json->'cv'->'processing'->>'updated_at')::timestamptz,
                             updated_at,
                             ingested_at
                           ) < now() - make_interval(secs => %s)
                  ) AS stuck_pending_async_count,
                  (SELECT count(*) FROM intake_submissions s
                     WHERE s.status IN ('durable','receiving','accepted_processing')
                       AND NOT EXISTS (
                         SELECT 1 FROM intake_processing_jobs j
                         WHERE j.company_code=s.company_code
                           AND (
                             j.subject_id=s.submission_id::text
                             OR j.payload->>'submission_id'=s.submission_id::text
                             OR j.idempotency_key=concat('submission:', s.submission_id::text, ':validate')
                           )
                       )
                  ) AS durable_submissions_without_jobs,
                  (SELECT count(*) FROM candidate_knowledge_index_jobs
                     WHERE (status='failed' OR dead_letter=true)
                       AND coalesce(updated_at, created_at) >= now() - interval '1 hour'
                  ) AS ck_index_failures_1h
                """,
                (
                    RECIPIENT,
                    started_at or None,
                    started_at or "",
                    PENDING_ASYNC_MAX_AGE_SEC,
                ),
            )
            metrics = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT
                  (SELECT count(*) FROM application_lifecycle_events) AS lifecycle_events_total,
                  (SELECT count(*) FROM candidate_rank_evaluations) AS ranking_evaluations_total,
                  (SELECT count(*) FROM outbound_delivery_events) AS outbound_events_total,
                  (SELECT count(*) FROM candidate_interviews) AS interviews_total
                """
            )
            metrics.update(dict(cur.fetchone() or {}))

    snapshot = {
        "captured_at": stamp,
        "activation_started_at": started_at or None,
        "authorized_recipient": RECIPIENT,
        "metrics": metrics,
        "units": {
            "orchestrator": unit_state("wathefni-orchestrator.service"),
            "intake_timer": unit_state("wathefni-inbound-intake-worker.timer"),
            "classification_timer": unit_state(
                "wathefni-talent-pool-auto-email-classification.timer"
            ),
            "monitor_timer": unit_state("wathefni-inbound-ops-monitor.timer"),
            "prehire_cv_timer": unit_state("wathefni-prehire-cv-process.timer"),
            "clamav_container": subprocess.run(
                [
                    "docker",
                    "inspect",
                    "-f",
                    "{{.State.Health.Status}}",
                    "wathefni-production-clamav",
                ],
                text=True,
                capture_output=True,
            ).stdout.strip()
            or "unknown",
        },
        "alerts": [],
        "candidate_messaging": "disabled",
        "audience": "platform_operations",
    }

    alerts = snapshot["alerts"]
    m = metrics
    if int(m.get("non_wathefni_active_intake_jobs") or 0) > 0:
        alerts.append("non_wathefni_active_intake_jobs")
    if int(m.get("non_wathefni_active_classification_jobs") or 0) > 0:
        alerts.append("non_wathefni_active_classification_jobs")
    if int(m.get("post_activation_recipient_violations") or 0) > 0:
        alerts.append("post_activation_recipient_violations")
    if int(m.get("scan_failure_24h") or 0) > 0:
        alerts.append("scan_failure_24h")
    if int(m.get("malware_detected_24h") or 0) > 0:
        alerts.append("malware_detected_24h")
    if int(m.get("open_identity_reviews") or 0) > 0:
        alerts.append("open_identity_reviews")
    if int(m.get("intake_dead_letter_24h") or 0) > 0:
        alerts.append("intake_dead_letter_24h")
    if int(m.get("classification_dead_letter_24h") or 0) > 0:
        alerts.append("classification_dead_letter_24h")
    if int(m.get("held_with_job_binding_suspect") or 0) > 0:
        alerts.append("held_with_job_binding_suspect")
    if snapshot["units"]["clamav_container"] not in {"healthy", "starting"}:
        alerts.append("clamav_unhealthy")
    if snapshot["units"]["orchestrator"] != "active":
        alerts.append("orchestrator_inactive")
    if snapshot["units"]["intake_timer"] != "active":
        alerts.append("intake_worker_timer_inactive")
    if snapshot["units"]["monitor_timer"] != "active":
        alerts.append("monitor_timer_inactive")
    # Legacy competing path must stay off; alert if someone re-enables it.
    if snapshot["units"]["prehire_cv_timer"] == "active":
        alerts.append("legacy_prehire_cv_timer_active")

    oldest_pending = m.get("oldest_intake_pending_age_seconds")
    if oldest_pending is not None and int(oldest_pending) > PENDING_JOB_MAX_AGE_SEC:
        alerts.append("pending_job_too_old")
    oldest_running = m.get("oldest_intake_running_age_seconds")
    if oldest_running is not None and int(oldest_running) > RUNNING_JOB_MAX_AGE_SEC:
        alerts.append("running_job_beyond_sla")
    if int(m.get("stuck_pending_async_count") or 0) > 0:
        alerts.append("stuck_pending_async_processing")
    if int(m.get("durable_submissions_without_jobs") or 0) > 0:
        alerts.append("durable_submission_without_jobs")
    if int(m.get("intake_queue_depth") or 0) >= QUEUE_DEPTH_ALERT:
        alerts.append("intake_queue_depth_high")
    if int(m.get("ocr_provider_failures_24h") or 0) >= OCR_FAILURE_ALERT_24H:
        alerts.append("repeated_ocr_provider_failures")
    if int(m.get("ck_index_failures_1h") or 0) >= CK_FAILURE_ALERT_1H:
        alerts.append("repeated_ck_index_failures")

    delivery = deliver_platform_alerts(alerts, captured_at=stamp)
    snapshot["delivery"] = delivery

    latest = ROOT / "latest.json"
    history = ROOT / "history"
    history.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, indent=2, default=str) + "\n"
    latest.write_text(payload)
    (history / f"{stamp.replace(':', '')}.json").write_text(payload)
    alerts_path = ROOT / "alerts.latest.json"
    alerts_path.write_text(
        json.dumps(
            {"captured_at": stamp, "alerts": alerts, "delivery": delivery, "audience": "platform_operations"},
            indent=2,
            default=str,
        )
        + "\n"
    )
    flag = ROOT / "ALERT_ACTIVE"
    if alerts:
        flag.write_text("\n".join(alerts) + "\n")
    elif flag.exists():
        flag.unlink()
    print(json.dumps({"captured_at": stamp, "alerts": alerts, "delivery": delivery, "metrics": metrics}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
