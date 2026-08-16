import json
import subprocess
from datetime import date
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.application import Application
from app.models.company import Company
from app.models.employee import ComplianceDocument, Employee, EmployeeDocument, OnboardingItem
from app.services.posthire import transition_hire_to_employee

EMPLOYEE_HEADERS = [
    "Name",
    "Phone",
    "Email",
    "Position",
    "Company",
    "Hire Date",
    "Onboarding Status",
    "Documents Pending",
    "Documents Complete",
    "Start Date",
    "Notes",
    "Employee Key",
]

COMPLIANCE_HEADERS = [
    "Employee",
    "Phone",
    "Document Type",
    "Status",
    "Expiry Date",
    "Days Until Expiry",
    "Last Reminded",
    "Reminder Count",
    "Authority",
    "Notes",
]


class SheetSyncDisabled(RuntimeError):
    pass


def sync_employee_for_application(db: Session, *, application_id: uuid.UUID) -> dict[str, Any]:
    employee = ensure_employee_for_application(db, application_id)
    return sync_employee_row(db, employee)


def sync_employee_by_id(db: Session, *, employee_id: uuid.UUID) -> dict[str, Any]:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise ValueError(f"Employee not found: {employee_id}")
    return sync_employee_row(db, employee)


def sync_compliance_for_application(db: Session, *, application_id: uuid.UUID) -> dict[str, Any]:
    employee = ensure_employee_for_application(db, application_id)
    return sync_compliance_rows(db, employee)


def sync_compliance_by_id(db: Session, *, employee_id: uuid.UUID) -> dict[str, Any]:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise ValueError(f"Employee not found: {employee_id}")
    return sync_compliance_rows(db, employee)


def ensure_employee_for_application(db: Session, application_id: uuid.UUID) -> Employee:
    result = transition_hire_to_employee(db, application_id=application_id)
    employee = db.get(Employee, uuid.UUID(result["employee_id"]))
    if not employee:
        raise ValueError(f"Employee not found after post-hire transition: {result['employee_id']}")
    return employee


def sync_employee_row(db: Session, employee: Employee) -> dict[str, Any]:
    settings = get_settings()
    if not settings.google_sheet_id:
        return {"status": "skipped", "reason": "GOOGLE_SHEET_ID is not configured"}

    sheet_name = settings.employees_sheet_name
    ensure_headers(sheet_name, EMPLOYEE_HEADERS)

    values = get_values(f"{sheet_name}!A1:L")
    row_number = find_row_number(values, key_column=11, key_value=employee.employee_key)
    row = build_employee_row(db, employee)

    if row_number:
        update_values(f"{sheet_name}!A{row_number}:L{row_number}", [row])
        action = "updated"
    else:
        append_values(f"{sheet_name}!A:L", [row])
        action = "appended"

    return {"status": action, "employee_id": str(employee.id), "employee_key": employee.employee_key}


def sync_compliance_rows(db: Session, employee: Employee) -> dict[str, Any]:
    settings = get_settings()
    if not settings.google_sheet_id:
        return {"status": "skipped", "reason": "GOOGLE_SHEET_ID is not configured"}

    sheet_name = settings.compliance_sheet_name
    ensure_headers(sheet_name, COMPLIANCE_HEADERS)

    values = get_values(f"{sheet_name}!A1:J")
    documents = (
        db.query(ComplianceDocument)
        .filter(ComplianceDocument.employee_id == employee.id)
        .order_by(ComplianceDocument.document_type.asc())
        .all()
    )

    updated = 0
    appended = 0
    for document in documents:
        row_number = find_compliance_row_number(values, employee.phone, document.document_type)
        row = build_compliance_row(employee, document)
        if row_number:
            update_values(f"{sheet_name}!A{row_number}:J{row_number}", [row])
            updated += 1
        else:
            append_values(f"{sheet_name}!A:J", [row])
            appended += 1

    return {
        "status": "synced",
        "employee_id": str(employee.id),
        "employee_key": employee.employee_key,
        "updated": updated,
        "appended": appended,
    }


def build_employee_row(db: Session, employee: Employee) -> list[str]:
    company = db.get(Company, employee.company_id)
    pending_docs = (
        db.query(EmployeeDocument)
        .filter(EmployeeDocument.employee_id == employee.id, EmployeeDocument.status != "complete")
        .count()
    )
    complete_docs = (
        db.query(EmployeeDocument)
        .filter(EmployeeDocument.employee_id == employee.id, EmployeeDocument.status == "complete")
        .count()
    )
    total_items = db.query(OnboardingItem).filter(OnboardingItem.employee_id == employee.id).count()
    completed_items = (
        db.query(OnboardingItem)
        .filter(OnboardingItem.employee_id == employee.id, OnboardingItem.status == "completed")
        .count()
    )
    onboarding_status = f"{completed_items}/{total_items} completed" if total_items else "not started"

    return [
        employee.name or "",
        employee.phone or "",
        employee.email or "",
        employee.position_title or "",
        company.name if company else "",
        employee.hire_date.isoformat() if employee.hire_date else "",
        onboarding_status,
        str(pending_docs),
        str(complete_docs),
        employee.start_date.isoformat() if employee.start_date else "",
        "",
        employee.employee_key,
    ]


def build_compliance_row(employee: Employee, document: ComplianceDocument) -> list[str]:
    return [
        employee.name or "",
        employee.phone or "",
        document.document_type,
        document.status,
        document.expiry_date.isoformat() if document.expiry_date else "",
        days_until(document.expiry_date),
        "",
        "0",
        "",
        document.notes or "",
    ]


def days_until(expiry_date: date | None) -> str:
    if not expiry_date:
        return ""
    return str((expiry_date - date.today()).days)


def ensure_headers(sheet_name: str, headers: list[str]) -> None:
    end_column = chr(ord("A") + len(headers) - 1)
    update_values(f"{sheet_name}!A1:{end_column}1", [headers])


def find_row_number(values: list[list[str]], *, key_column: int, key_value: str) -> int | None:
    for index, row in enumerate(values[1:], start=2):
        if len(row) > key_column and row[key_column] == key_value:
            return index
    return None


def find_compliance_row_number(values: list[list[str]], phone: str | None, document_type: str) -> int | None:
    phone = phone or ""
    for index, row in enumerate(values[1:], start=2):
        row_phone = row[1] if len(row) > 1 else ""
        row_document_type = row[2] if len(row) > 2 else ""
        if row_phone == phone and row_document_type == document_type:
            return index
    return None


def get_values(range_name: str) -> list[list[str]]:
    result = run_gog(["sheets", "get", get_settings().google_sheet_id, range_name, "--json"])
    return extract_values(result)


def update_values(range_name: str, rows: list[list[str]]) -> None:
    run_gog(
        [
            "sheets",
            "update",
            get_settings().google_sheet_id,
            range_name,
            "--values-json",
            json.dumps(rows),
        ]
    )


def append_values(range_name: str, rows: list[list[str]]) -> None:
    run_gog(
        [
            "sheets",
            "append",
            get_settings().google_sheet_id,
            range_name,
            "--values-json",
            json.dumps(rows),
        ]
    )


def run_gog(args: list[str]) -> Any:
    settings = get_settings()
    if not settings.google_sheet_id:
        raise SheetSyncDisabled("GOOGLE_SHEET_ID is not configured")

    command = [settings.gog_bin, *args]
    if settings.google_account:
        command.extend(["--account", settings.google_account])

    completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "gog command failed"
        raise RuntimeError(message)

    output = completed.stdout.strip()
    if not output:
        return None

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output


def extract_values(result: Any) -> list[list[str]]:
    if result is None:
        return []
    if isinstance(result, list):
        return normalize_values(result)
    if isinstance(result, dict):
        for key in ("values", "rows", "data"):
            if isinstance(result.get(key), list):
                return normalize_values(result[key])
    return []


def normalize_values(values: list[Any]) -> list[list[str]]:
    normalized: list[list[str]] = []
    for row in values:
        if isinstance(row, list):
            normalized.append(["" if value is None else str(value) for value in row])
        elif isinstance(row, dict):
            normalized.append(["" if value is None else str(value) for value in row.values()])
    return normalized
