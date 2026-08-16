from datetime import datetime, timedelta
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.candidate import Candidate
from app.models.employee import Employee
from app.models.workflow import JobQueue, OutboxEvent, WorkflowRun, WorkflowStep

ACTIVE_WORKFLOW_STATUSES = ("pending", "running")


def enqueue_job(
    db: Session,
    *,
    job_type: str,
    payload: dict[str, Any],
    workflow_run: WorkflowRun | None = None,
    workflow_step: WorkflowStep | None = None,
    priority: int = 100,
    max_attempts: int = 3,
    available_in_seconds: int = 0,
) -> JobQueue:
    job = JobQueue(
        workflow_run_id=workflow_run.id if workflow_run else None,
        workflow_step_id=workflow_step.id if workflow_step else None,
        job_type=job_type,
        payload=payload,
        priority=priority,
        max_attempts=max_attempts,
        available_at=datetime.utcnow() + timedelta(seconds=available_in_seconds),
    )
    db.add(job)
    return job


def enqueue_outbox_event(
    db: Session,
    *,
    event_type: str,
    channel: str,
    destination: str,
    payload: dict[str, Any],
    workflow_run: WorkflowRun | None = None,
    job: JobQueue | None = None,
    max_attempts: int = 3,
) -> OutboxEvent:
    event = OutboxEvent(
        workflow_run_id=workflow_run.id if workflow_run else None,
        job_id=job.id if job else None,
        event_type=event_type,
        channel=channel,
        destination=destination,
        payload=payload,
        max_attempts=max_attempts,
    )
    db.add(event)
    return event


def create_workflow_run(
    db: Session,
    *,
    workflow_type: str,
    company_id: uuid.UUID | None,
    requested_by: str | None,
    subject_type: str | None,
    subject_id: str | None,
    input_data: dict[str, Any],
) -> WorkflowRun:
    run = WorkflowRun(
        workflow_type=workflow_type,
        company_id=company_id,
        requested_by=requested_by,
        subject_type=subject_type,
        subject_id=subject_id,
        input=input_data,
    )
    db.add(run)
    db.flush()
    return run


def add_workflow_step(
    db: Session,
    *,
    workflow_run: WorkflowRun,
    step_type: str,
    sequence: int,
    input_data: dict[str, Any],
) -> WorkflowStep:
    step = WorkflowStep(
        workflow_run_id=workflow_run.id,
        step_type=step_type,
        sequence=sequence,
        input=input_data,
    )
    workflow_run.total_steps += 1
    db.add(step)
    db.flush()
    return step


def enqueue_hire_workflow(
    db: Session,
    *,
    application: Application,
    requested_by: str | None,
    notify_phone: str | None = None,
) -> WorkflowRun:
    existing = (
        db.query(WorkflowRun)
        .filter(
            WorkflowRun.workflow_type == "hire_candidate",
            WorkflowRun.subject_type == "application",
            WorkflowRun.subject_id == str(application.id),
            WorkflowRun.status.in_(ACTIVE_WORKFLOW_STATUSES),
        )
        .first()
    )
    if existing:
        return existing

    candidate = db.query(Candidate).filter(Candidate.id == application.candidate_id).first()
    candidate_name = candidate.name if candidate else "candidate"

    run = create_workflow_run(
        db,
        workflow_type="hire_candidate",
        company_id=application.company_id,
        requested_by=requested_by,
        subject_type="application",
        subject_id=str(application.id),
        input_data={
            "application_id": str(application.id),
            "candidate_id": str(application.candidate_id),
            "candidate_name": candidate_name,
            "notify_phone": notify_phone,
        },
    )

    status_step = add_workflow_step(
        db,
        workflow_run=run,
        step_type="update_application_status",
        sequence=10,
        input_data={"application_id": str(application.id), "status": "hired"},
    )
    enqueue_job(
        db,
        workflow_run=run,
        workflow_step=status_step,
        job_type="update_application_status",
        payload=status_step.input,
        priority=10,
    )

    post_hire_step = add_workflow_step(
        db,
        workflow_run=run,
        step_type="initialize_post_hire",
        sequence=20,
        input_data={
            "application_id": str(application.id),
            "candidate_id": str(application.candidate_id),
        },
    )
    enqueue_job(
        db,
        workflow_run=run,
        workflow_step=post_hire_step,
        job_type="initialize_post_hire",
        payload=post_hire_step.input,
        priority=20,
    )

    employee_sync_step = add_workflow_step(
        db,
        workflow_run=run,
        step_type="sync_employee_sheet",
        sequence=30,
        input_data={"application_id": str(application.id)},
    )
    enqueue_job(
        db,
        workflow_run=run,
        workflow_step=employee_sync_step,
        job_type="sync_employee_sheet",
        payload=employee_sync_step.input,
        priority=30,
    )

    compliance_sync_step = add_workflow_step(
        db,
        workflow_run=run,
        step_type="sync_compliance_sheet",
        sequence=40,
        input_data={"application_id": str(application.id)},
    )
    enqueue_job(
        db,
        workflow_run=run,
        workflow_step=compliance_sync_step,
        job_type="sync_compliance_sheet",
        payload=compliance_sync_step.input,
        priority=40,
    )

    db.flush()
    return run


def enqueue_start_onboarding_workflow(
    db: Session,
    *,
    employee: Employee,
    requested_by: str | None,
    notify_phone: str | None = None,
) -> WorkflowRun:
    existing = (
        db.query(WorkflowRun)
        .filter(
            WorkflowRun.workflow_type == "start_onboarding",
            WorkflowRun.subject_type == "employee",
            WorkflowRun.subject_id == str(employee.id),
            WorkflowRun.status.in_(ACTIVE_WORKFLOW_STATUSES),
        )
        .first()
    )
    if existing:
        return existing

    run = create_workflow_run(
        db,
        workflow_type="start_onboarding",
        company_id=employee.company_id,
        requested_by=requested_by,
        subject_type="employee",
        subject_id=str(employee.id),
        input_data={
            "employee_id": str(employee.id),
            "employee_name": employee.name,
            "employee_phone": employee.phone,
            "notify_phone": notify_phone,
        },
    )

    onboarding_step = add_workflow_step(
        db,
        workflow_run=run,
        step_type="start_employee_onboarding",
        sequence=10,
        input_data={"employee_id": str(employee.id)},
    )
    enqueue_job(
        db,
        workflow_run=run,
        workflow_step=onboarding_step,
        job_type="start_employee_onboarding",
        payload=onboarding_step.input,
        priority=10,
    )

    employee_sync_step = add_workflow_step(
        db,
        workflow_run=run,
        step_type="sync_employee_sheet",
        sequence=20,
        input_data={"employee_id": str(employee.id)},
    )
    enqueue_job(
        db,
        workflow_run=run,
        workflow_step=employee_sync_step,
        job_type="sync_employee_sheet",
        payload=employee_sync_step.input,
        priority=20,
    )

    db.flush()
    return run
