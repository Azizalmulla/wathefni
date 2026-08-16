"""
Postgres-backed workflow worker.

Run one batch locally:
    python -m app.worker --once

Run continuously under systemd or a process manager:
    python -m app.worker
"""
import argparse
import asyncio
import socket
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.application import Application
from app.models.workflow import JobQueue, OutboxEvent, WorkflowRun, WorkflowStep
from app.services.posthire import start_employee_onboarding, transition_hire_to_employee
from app.services.sheet_sync import (
    sync_compliance_by_id,
    sync_compliance_for_application,
    sync_employee_by_id,
    sync_employee_for_application,
)
from app.services.whatsapp import send_text_message
from app.services.workflows import enqueue_outbox_event

WORKER_ID = socket.gethostname()
TERMINAL_JOB_STATUSES = {"completed", "failed"}


def handle_update_application_status(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    application = db.get(Application, uuid.UUID(payload["application_id"]))
    if not application:
        raise ValueError(f"Application not found: {payload['application_id']}")

    old_status = application.status
    application.status = payload["status"]
    application.status_changed_at = datetime.utcnow()
    return {"old_status": old_status, "new_status": application.status}


def handle_initialize_post_hire(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    return transition_hire_to_employee(db, application_id=uuid.UUID(payload["application_id"]))


def handle_send_whatsapp_text(db: Session, payload: dict[str, Any], job: JobQueue) -> dict[str, Any]:
    event = enqueue_outbox_event(
        db,
        event_type="whatsapp_text",
        channel="whatsapp",
        destination=payload["to"],
        payload={"message": payload["message"]},
        workflow_run=job.workflow_run,
        job=job,
    )
    db.flush()
    return {"outbox_event_id": str(event.id)}


def handle_sync_employee_sheet(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("employee_id"):
        return sync_employee_by_id(db, employee_id=uuid.UUID(payload["employee_id"]))
    return sync_employee_for_application(db, application_id=uuid.UUID(payload["application_id"]))


def handle_sync_compliance_sheet(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("employee_id"):
        return sync_compliance_by_id(db, employee_id=uuid.UUID(payload["employee_id"]))
    return sync_compliance_for_application(db, application_id=uuid.UUID(payload["application_id"]))


def handle_start_employee_onboarding(db: Session, payload: dict[str, Any], job: JobQueue) -> dict[str, Any]:
    result = start_employee_onboarding(db, employee_id=uuid.UUID(payload["employee_id"]))
    enqueue_outbox_event(
        db,
        event_type="whatsapp_text",
        channel="whatsapp",
        destination=result["employee_phone"],
        payload={"message": result["message"]},
        workflow_run=job.workflow_run,
        job=job,
    )
    db.flush()
    return result


JOB_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "update_application_status": handle_update_application_status,
    "initialize_post_hire": handle_initialize_post_hire,
    "start_employee_onboarding": handle_start_employee_onboarding,
    "sync_employee_sheet": handle_sync_employee_sheet,
    "sync_compliance_sheet": handle_sync_compliance_sheet,
    "send_whatsapp_text": handle_send_whatsapp_text,
}


def claim_job(db: Session) -> JobQueue | None:
    now = datetime.utcnow()
    job = (
        db.query(JobQueue)
        .filter(JobQueue.status == "pending", JobQueue.available_at <= now)
        .order_by(JobQueue.priority.asc(), JobQueue.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if not job:
        return None

    job.status = "running"
    job.locked_by = WORKER_ID
    job.locked_at = now
    job.started_at = job.started_at or now
    job.attempts += 1
    db.commit()
    db.refresh(job)
    return job


def mark_workflow_progress(db: Session, job: JobQueue, status: str, result: dict[str, Any] | None, error: str | None) -> None:
    now = datetime.utcnow()

    if job.workflow_step_id:
        step = db.get(WorkflowStep, job.workflow_step_id)
        if step:
            step.status = status
            step.started_at = step.started_at or job.started_at or now
            step.completed_at = now if status in TERMINAL_JOB_STATUSES else None
            step.output = result
            step.error = error

    if not job.workflow_run_id:
        return

    run = db.get(WorkflowRun, job.workflow_run_id)
    if not run:
        return

    run.started_at = run.started_at or job.started_at or now
    run.completed_steps = (
        db.query(WorkflowStep)
        .filter(WorkflowStep.workflow_run_id == run.id, WorkflowStep.status == "completed")
        .count()
    )
    run.failed_steps = (
        db.query(WorkflowStep)
        .filter(WorkflowStep.workflow_run_id == run.id, WorkflowStep.status == "failed")
        .count()
    )

    unfinished_jobs = (
        db.query(JobQueue)
        .filter(
            JobQueue.workflow_run_id == run.id,
            JobQueue.status.notin_(list(TERMINAL_JOB_STATUSES)),
        )
        .count()
    )

    if unfinished_jobs == 0:
        run.completed_at = now
        if run.failed_steps:
            run.status = "failed" if run.failed_steps == run.total_steps else "partial"
            run.error = error
        else:
            run.status = "completed"
            run.output = {"completed_steps": run.completed_steps}
            notify_phone = (run.input or {}).get("notify_phone")
            candidate_name = (run.input or {}).get("candidate_name", "candidate")
            employee_name = (run.input or {}).get("employee_name") or "employee"
            if notify_phone:
                if run.workflow_type == "hire_candidate":
                    message = (
                        f"{candidate_name} is hired, employee setup is done, and sheets are synced. "
                        "Should I start onboarding?"
                    )
                elif run.workflow_type == "start_onboarding":
                    message = f"Onboarding started for {employee_name}."
                else:
                    message = f"{run.workflow_type} is complete."
                enqueue_outbox_event(
                    db,
                    event_type="whatsapp_text",
                    channel="whatsapp",
                    destination=notify_phone,
                    payload={"message": message},
                    workflow_run=run,
                )
    else:
        run.status = "running"


def process_job(db: Session, job: JobQueue) -> None:
    handler = JOB_HANDLERS.get(job.job_type)
    if not handler:
        raise ValueError(f"No handler registered for job type: {job.job_type}")

    if job.job_type in {"send_whatsapp_text", "start_employee_onboarding"}:
        result = handler(db, job.payload, job)
    else:
        result = handler(db, job.payload)

    job.status = "completed"
    job.result = result
    job.completed_at = datetime.utcnow()
    job.locked_by = None
    job.locked_at = None
    mark_workflow_progress(db, job, "completed", result, None)


def fail_job(db: Session, job: JobQueue, exc: Exception) -> None:
    job.last_error = str(exc)
    job.locked_by = None
    job.locked_at = None

    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.completed_at = datetime.utcnow()
        mark_workflow_progress(db, job, "failed", None, str(exc))
        return

    job.status = "pending"
    backoff_seconds = min(300, 2 ** job.attempts)
    job.available_at = datetime.utcnow() + timedelta(seconds=backoff_seconds)
    mark_workflow_progress(db, job, "pending", None, str(exc))


def process_jobs_once(limit: int) -> int:
    processed = 0
    for _ in range(limit):
        db = SessionLocal()
        try:
            job = claim_job(db)
            if not job:
                return processed

            try:
                process_job(db, job)
            except Exception as exc:
                fail_job(db, job, exc)

            db.commit()
            processed += 1
        finally:
            db.close()

    return processed


def claim_outbox_event(db: Session) -> OutboxEvent | None:
    now = datetime.utcnow()
    event = (
        db.query(OutboxEvent)
        .filter(OutboxEvent.status == "pending", OutboxEvent.available_at <= now)
        .order_by(OutboxEvent.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if not event:
        return None

    event.status = "sending"
    event.attempts += 1
    db.commit()
    db.refresh(event)
    return event


def send_outbox_event(event: OutboxEvent) -> dict[str, Any]:
    if event.channel == "whatsapp" and event.event_type == "whatsapp_text":
        return asyncio.run(send_text_message(event.destination, event.payload["message"]))

    raise ValueError(f"No outbox sender for {event.channel}:{event.event_type}")


def process_outbox_once(limit: int) -> int:
    processed = 0
    for _ in range(limit):
        db = SessionLocal()
        try:
            event = claim_outbox_event(db)
            if not event:
                return processed

            try:
                result = send_outbox_event(event)
                event.status = "sent"
                event.result = result
                event.sent_at = datetime.utcnow()
            except Exception as exc:
                event.last_error = str(exc)
                if event.attempts >= event.max_attempts:
                    event.status = "failed"
                else:
                    event.status = "pending"
                    event.available_at = datetime.utcnow() + timedelta(seconds=min(300, 2 ** event.attempts))

            db.commit()
            processed += 1
        finally:
            db.close()

    return processed


def run_worker(*, once: bool, batch_size: int, sleep_seconds: float) -> None:
    while True:
        processed_jobs = process_jobs_once(batch_size)
        processed_outbox = process_outbox_once(batch_size)

        if once:
            return

        if processed_jobs == 0 and processed_outbox == 0:
            time.sleep(sleep_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AI Recruiter workflow worker.")
    parser.add_argument("--once", action="store_true", help="Process one batch and exit.")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--sleep-seconds", type=float, default=2.0)
    args = parser.parse_args()

    run_worker(
        once=args.once,
        batch_size=args.batch_size,
        sleep_seconds=args.sleep_seconds,
    )


if __name__ == "__main__":
    main()
