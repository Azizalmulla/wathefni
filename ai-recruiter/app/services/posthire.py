from datetime import date, datetime, timedelta
import re
import uuid

from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.candidate import Candidate
from app.models.employee import ComplianceDocument, Employee, EmployeeDocument, OnboardingItem
from app.models.position import Position


DEFAULT_ONBOARDING_ITEMS = [
    {
        "item_key": "welcome_message",
        "title": "Send welcome and onboarding message",
        "category": "communication",
        "owner": "hr",
        "due_days": 0,
    },
    {
        "item_key": "civil_id_collection",
        "title": "Collect Civil ID copy",
        "category": "documents",
        "owner": "employee",
        "due_days": 2,
    },
    {
        "item_key": "bank_details",
        "title": "Collect bank account details",
        "category": "payroll",
        "owner": "employee",
        "due_days": 3,
    },
    {
        "item_key": "contract_signature",
        "title": "Prepare and sign employment contract",
        "category": "legal",
        "owner": "hr",
        "due_days": 5,
    },
    {
        "item_key": "first_day_briefing",
        "title": "Schedule first day briefing",
        "category": "orientation",
        "owner": "hr",
        "due_days": 7,
    },
]

DEFAULT_EMPLOYEE_DOCUMENTS = [
    "civil_id",
    "passport",
    "work_permit",
    "employment_contract",
    "bank_details",
]

DEFAULT_COMPLIANCE_DOCUMENTS = [
    {"document_type": "civil_id", "warning_days": 30},
    {"document_type": "passport", "warning_days": 60},
    {"document_type": "work_permit", "warning_days": 30},
    {"document_type": "employment_contract", "warning_days": None},
]

ONBOARDING_WELCOME_MESSAGE = (
    "Welcome to Wathefni. Your hiring setup is ready. "
    "Please send your Civil ID copy, passport copy, work permit if available, "
    "and bank account details so HR can complete onboarding."
)


def build_employee_key(phone: str | None, candidate_id: uuid.UUID) -> str:
    digits = re.sub(r"\D+", "", phone or "")
    if digits:
        return f"WATHEFNI-{digits}"
    return f"WATHEFNI-{str(candidate_id)[:8].upper()}"


def transition_hire_to_employee(db: Session, *, application_id: uuid.UUID) -> dict:
    application = db.get(Application, application_id)
    if not application:
        raise ValueError(f"Application not found: {application_id}")

    candidate = db.get(Candidate, application.candidate_id)
    if not candidate:
        raise ValueError(f"Candidate not found: {application.candidate_id}")

    position = db.get(Position, application.position_id)
    employee = (
        db.query(Employee)
        .filter(
            (Employee.application_id == application.id)
            | (Employee.candidate_id == candidate.id)
            | (Employee.employee_key == build_employee_key(candidate.phone, candidate.id))
        )
        .first()
    )

    created_employee = False
    if not employee:
        employee = Employee(
            company_id=application.company_id,
            candidate_id=candidate.id,
            application_id=application.id,
            employee_key=build_employee_key(candidate.phone, candidate.id),
            hire_date=date.today(),
        )
        db.add(employee)
        created_employee = True

    employee.company_id = application.company_id
    employee.candidate_id = candidate.id
    employee.application_id = application.id
    employee.name = candidate.name
    employee.phone = candidate.phone
    employee.email = candidate.email
    employee.position_title = position.title if position else None
    employee.status = employee.status or "onboarding"
    db.flush()

    onboarding_created = ensure_onboarding_items(db, employee)
    employee_docs_created = ensure_employee_documents(db, employee)
    compliance_created = ensure_compliance_documents(db, employee)

    return {
        "employee_id": str(employee.id),
        "employee_key": employee.employee_key,
        "created_employee": created_employee,
        "onboarding_items_created": onboarding_created,
        "employee_documents_created": employee_docs_created,
        "compliance_documents_created": compliance_created,
    }


def start_employee_onboarding(db: Session, *, employee_id: uuid.UUID) -> dict:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise ValueError(f"Employee not found: {employee_id}")
    if not employee.phone:
        raise ValueError(f"Employee has no phone number: {employee_id}")

    now = datetime.utcnow()
    already_started = employee.onboarding_started_at is not None
    employee.status = "onboarding"
    employee.onboarding_started_at = employee.onboarding_started_at or now

    welcome_item = (
        db.query(OnboardingItem)
        .filter(OnboardingItem.employee_id == employee.id, OnboardingItem.item_key == "welcome_message")
        .first()
    )
    if welcome_item and welcome_item.status != "completed":
        welcome_item.status = "completed"
        welcome_item.completed_at = now

    return {
        "employee_id": str(employee.id),
        "employee_key": employee.employee_key,
        "employee_phone": employee.phone,
        "message": ONBOARDING_WELCOME_MESSAGE,
        "already_started": already_started,
    }


def ensure_onboarding_items(db: Session, employee: Employee) -> int:
    existing_keys = {
        item.item_key
        for item in db.query(OnboardingItem).filter(OnboardingItem.employee_id == employee.id).all()
    }
    created = 0
    today = date.today()

    for item in DEFAULT_ONBOARDING_ITEMS:
        if item["item_key"] in existing_keys:
            continue

        db.add(
            OnboardingItem(
                employee_id=employee.id,
                item_key=item["item_key"],
                title=item["title"],
                category=item["category"],
                owner=item["owner"],
                due_date=today + timedelta(days=item["due_days"]),
            )
        )
        created += 1

    return created


def ensure_employee_documents(db: Session, employee: Employee) -> int:
    existing_types = {
        document.document_type
        for document in db.query(EmployeeDocument).filter(EmployeeDocument.employee_id == employee.id).all()
    }
    created = 0

    for document_type in DEFAULT_EMPLOYEE_DOCUMENTS:
        if document_type in existing_types:
            continue

        db.add(EmployeeDocument(employee_id=employee.id, document_type=document_type))
        created += 1

    return created


def ensure_compliance_documents(db: Session, employee: Employee) -> int:
    existing_types = {
        document.document_type
        for document in db.query(ComplianceDocument).filter(ComplianceDocument.employee_id == employee.id).all()
    }
    created = 0

    for document in DEFAULT_COMPLIANCE_DOCUMENTS:
        document_type = document["document_type"]
        if document_type in existing_types:
            continue

        db.add(
            ComplianceDocument(
                employee_id=employee.id,
                document_type=document_type,
                warning_days=document["warning_days"],
            )
        )
        created += 1

    return created
