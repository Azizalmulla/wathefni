import re
from datetime import datetime
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.models.employee import ComplianceDocument, Employee, EmployeeDocument, OnboardingItem
from app.models.hr_user import HRUser
from app.services.workflows import enqueue_job, enqueue_outbox_event

DOCUMENT_LABELS = {
    "civil_id": "Civil ID",
    "passport": "passport",
    "work_permit": "work permit",
    "bank_details": "bank details",
    "employment_contract": "employment contract",
}

DOCUMENT_KEYWORDS = {
    "civil_id": ("civil id", "civilid", "cid", "بطاقة", "مدنية", "civil"),
    "passport": ("passport", "جواز"),
    "work_permit": ("work permit", "permit", "اذن عمل", "إذن عمل"),
    "bank_details": ("bank", "iban", "account", "salary account", "nbk", "kfh", "gulf bank", "بنك", "حساب", "ايبان"),
    "employment_contract": ("contract", "employment contract", "عقد"),
}

NEGATIVE_PHRASES = (
    "dont have",
    "don't have",
    "do not have",
    "not available",
    "later",
    "no ",
    "ما عندي",
    "لاحقا",
)


def handle_employee_onboarding_message(
    db: Session,
    *,
    employee: Employee,
    text: str,
    msg_type: str,
    message: dict[str, Any],
) -> dict[str, Any]:
    if not employee.onboarding_started_at:
        return {
            "reply": "Your onboarding is not open yet. HR will message you when it is ready.",
            "updated": False,
        }

    document_type = detect_document_type(text, msg_type, message, employee, db)
    if not document_type:
        return {
            "reply": "Got it. Please send your Civil ID, passport, work permit if available, and bank details one by one.",
            "updated": False,
        }

    unavailable = is_unavailable_message(text)
    result = record_employee_document(
        db,
        employee=employee,
        document_type=document_type,
        text=text,
        msg_type=msg_type,
        message=message,
        unavailable=unavailable,
    )
    enqueue_posthire_syncs(db, employee)
    notify_hr_document_update(db, employee, document_type, result["status"])
    db.commit()

    if unavailable:
        return {
            "reply": f"No problem. I marked {DOCUMENT_LABELS[document_type]} as pending.",
            "updated": True,
        }

    return {
        "reply": f"Got it, {DOCUMENT_LABELS[document_type]} received.",
        "updated": True,
    }


def detect_document_type(
    text: str,
    msg_type: str,
    message: dict[str, Any],
    employee: Employee,
    db: Session,
) -> str | None:
    searchable = " ".join(
        value
        for value in [
            text,
            str((message.get("document") or {}).get("filename") or ""),
            str((message.get("document") or {}).get("caption") or ""),
            str((message.get("image") or {}).get("caption") or ""),
        ]
        if value
    ).lower()

    for document_type, keywords in DOCUMENT_KEYWORDS.items():
        if any(keyword in searchable for keyword in keywords):
            return document_type

    if msg_type in {"document", "image"}:
        return first_missing_document_type(db, employee)

    return None


def first_missing_document_type(db: Session, employee: Employee) -> str | None:
    document = (
        db.query(EmployeeDocument)
        .filter(EmployeeDocument.employee_id == employee.id, EmployeeDocument.status.in_(["missing", "pending"]))
        .order_by(EmployeeDocument.created_at.asc())
        .first()
    )
    return document.document_type if document else None


def is_unavailable_message(text: str) -> bool:
    normalized = text.lower().strip()
    return any(phrase in normalized for phrase in NEGATIVE_PHRASES)


def record_employee_document(
    db: Session,
    *,
    employee: Employee,
    document_type: str,
    text: str,
    msg_type: str,
    message: dict[str, Any],
    unavailable: bool,
) -> dict[str, str]:
    status = "pending" if unavailable else "received"
    employee_document = get_or_create_employee_document(db, employee.id, document_type)
    employee_document.status = status
    employee_document.notes = clean_note(text) if text else employee_document.notes

    media_id = extract_media_id(message)
    if media_id and not unavailable:
        employee_document.file_url = f"whatsapp_media:{media_id}"

    if document_type in {"civil_id", "passport", "work_permit", "employment_contract"}:
        compliance_document = get_or_create_compliance_document(db, employee.id, document_type)
        compliance_document.status = status
        compliance_document.notes = employee_document.notes

    update_onboarding_items(db, employee.id, document_type, status)
    return {"status": status}


def get_or_create_employee_document(db: Session, employee_id: uuid.UUID, document_type: str) -> EmployeeDocument:
    document = (
        db.query(EmployeeDocument)
        .filter(EmployeeDocument.employee_id == employee_id, EmployeeDocument.document_type == document_type)
        .first()
    )
    if document:
        return document

    document = EmployeeDocument(employee_id=employee_id, document_type=document_type)
    db.add(document)
    db.flush()
    return document


def get_or_create_compliance_document(db: Session, employee_id: uuid.UUID, document_type: str) -> ComplianceDocument:
    document = (
        db.query(ComplianceDocument)
        .filter(ComplianceDocument.employee_id == employee_id, ComplianceDocument.document_type == document_type)
        .first()
    )
    if document:
        return document

    document = ComplianceDocument(employee_id=employee_id, document_type=document_type)
    db.add(document)
    db.flush()
    return document


def update_onboarding_items(db: Session, employee_id: uuid.UUID, document_type: str, status: str) -> None:
    item_key = {
        "civil_id": "civil_id_collection",
        "bank_details": "bank_details",
        "employment_contract": "contract_signature",
    }.get(document_type)
    if not item_key or status != "received":
        return

    item = (
        db.query(OnboardingItem)
        .filter(OnboardingItem.employee_id == employee_id, OnboardingItem.item_key == item_key)
        .first()
    )
    if item and item.status != "completed":
        item.status = "completed"
        item.completed_at = datetime.utcnow()


def enqueue_posthire_syncs(db: Session, employee: Employee) -> None:
    enqueue_job(
        db,
        job_type="sync_employee_sheet",
        payload={"employee_id": str(employee.id)},
        priority=50,
    )
    enqueue_job(
        db,
        job_type="sync_compliance_sheet",
        payload={"employee_id": str(employee.id)},
        priority=60,
    )


def notify_hr_document_update(db: Session, employee: Employee, document_type: str, status: str) -> None:
    hr_users = (
        db.query(HRUser)
        .filter(HRUser.company_id == employee.company_id, HRUser.is_active == True)
        .all()
    )
    verb = "sent" if status == "received" else "marked pending for"
    message = f"{employee.name or 'Employee'} {verb} {DOCUMENT_LABELS[document_type]}."
    for hr_user in hr_users:
        enqueue_outbox_event(
            db,
            event_type="whatsapp_text",
            channel="whatsapp",
            destination=hr_user.phone,
            payload={"message": message},
        )


def extract_media_id(message: dict[str, Any]) -> str | None:
    document = message.get("document") or {}
    image = message.get("image") or {}
    return document.get("id") or image.get("id")


def clean_note(text: str) -> str | None:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500] if text else None
