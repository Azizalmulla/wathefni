"""
Internal admin endpoints.
Used by AI Octopus team to onboard companies, create positions, manage HR users.
Not exposed publicly — for manual setup and testing.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.company import Company
from app.models.employee import ComplianceDocument, Employee, EmployeeDocument, OnboardingItem
from app.models.position import Position
from app.models.hr_user import HRUser
from app.models.workflow import JobQueue, WorkflowRun, WorkflowStep
from app.services.qr_generator import generate_qr_code

router = APIRouter(prefix="/internal", tags=["internal"])


# --- Pydantic schemas ---

class CompanyCreate(BaseModel):
    name: str
    name_ar: str | None = None
    code: str
    sector: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class PositionCreate(BaseModel):
    title: str
    title_ar: str | None = None
    description: str | None = None
    requirements: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    location: str | None = None
    employment_type: str | None = None
    code: str
    screening_questions: list | None = None


class HRUserCreate(BaseModel):
    name: str
    phone: str
    email: str | None = None
    role: str = "manager"


# --- Company endpoints ---

@router.post("/companies")
def create_company(data: CompanyCreate, db: Session = Depends(get_db)):
    existing = db.query(Company).filter(Company.code == data.code).first()
    if existing:
        raise HTTPException(400, f"Company code '{data.code}' already exists")

    company = Company(**data.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return {"id": str(company.id), "name": company.name, "code": company.code}


@router.get("/companies")
def list_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).filter(Company.is_active == True).all()
    return [
        {"id": str(c.id), "name": c.name, "code": c.code, "sector": c.sector}
        for c in companies
    ]


@router.get("/companies/{company_id}")
def get_company(company_id: str, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    return {
        "id": str(company.id),
        "name": company.name,
        "code": company.code,
        "sector": company.sector,
        "contact_name": company.contact_name,
        "contact_email": company.contact_email,
        "contact_phone": company.contact_phone,
    }


# --- Position endpoints ---

@router.post("/companies/{company_id}/positions")
def create_position(company_id: str, data: PositionCreate, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    position = Position(company_id=company.id, **data.model_dump())
    db.add(position)
    db.flush()

    # Generate QR code
    try:
        qr_path = generate_qr_code(company.code, data.code)
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc
    position.qr_code_url = qr_path

    db.commit()
    db.refresh(position)

    from app.services.qr_generator import _apply_whatsapp_number

    try:
        wa_number = _apply_whatsapp_number()
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc
    apply_code = f"APPLY-{company.code}-{data.code}"
    return {
        "id": str(position.id),
        "title": position.title,
        "code": position.code,
        "qr_code_path": qr_path,
        "apply_link": f"https://wa.me/{wa_number}?text={apply_code}",
    }


@router.get("/companies/{company_id}/positions")
def list_positions(company_id: str, db: Session = Depends(get_db)):
    positions = (
        db.query(Position)
        .filter(Position.company_id == company_id, Position.is_active == True)
        .all()
    )
    return [
        {
            "id": str(p.id),
            "title": p.title,
            "code": p.code,
            "salary_min": float(p.salary_min) if p.salary_min else None,
            "salary_max": float(p.salary_max) if p.salary_max else None,
            "is_active": p.is_active,
        }
        for p in positions
    ]


# --- HR User endpoints ---

@router.post("/companies/{company_id}/hr-users")
def create_hr_user(company_id: str, data: HRUserCreate, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    existing = db.query(HRUser).filter(HRUser.phone == data.phone).first()
    if existing:
        raise HTTPException(400, f"Phone '{data.phone}' already registered")

    hr_user = HRUser(company_id=company.id, **data.model_dump())
    db.add(hr_user)
    db.commit()
    db.refresh(hr_user)

    return {
        "id": str(hr_user.id),
        "name": hr_user.name,
        "phone": hr_user.phone,
        "company": company.name,
        "role": hr_user.role,
    }


@router.get("/companies/{company_id}/hr-users")
def list_hr_users(company_id: str, db: Session = Depends(get_db)):
    users = db.query(HRUser).filter(HRUser.company_id == company_id, HRUser.is_active == True).all()
    return [
        {"id": str(u.id), "name": u.name, "phone": u.phone, "role": u.role}
        for u in users
    ]


# --- Workflow operations ---

@router.get("/companies/{company_id}/workflows")
def list_workflows(company_id: str, status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(WorkflowRun).filter(WorkflowRun.company_id == company_id)
    if status:
        query = query.filter(WorkflowRun.status == status)

    workflows = query.order_by(WorkflowRun.created_at.desc()).limit(50).all()
    return [
        {
            "id": str(workflow.id),
            "type": workflow.workflow_type,
            "status": workflow.status,
            "subject_type": workflow.subject_type,
            "subject_id": workflow.subject_id,
            "total_steps": workflow.total_steps,
            "completed_steps": workflow.completed_steps,
            "failed_steps": workflow.failed_steps,
            "created_at": workflow.created_at.isoformat(),
            "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
        }
        for workflow in workflows
    ]


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    workflow = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id).first()
    if not workflow:
        raise HTTPException(404, "Workflow not found")

    steps = (
        db.query(WorkflowStep)
        .filter(WorkflowStep.workflow_run_id == workflow.id)
        .order_by(WorkflowStep.sequence.asc())
        .all()
    )
    jobs = (
        db.query(JobQueue)
        .filter(JobQueue.workflow_run_id == workflow.id)
        .order_by(JobQueue.created_at.asc())
        .all()
    )

    return {
        "id": str(workflow.id),
        "type": workflow.workflow_type,
        "status": workflow.status,
        "input": workflow.input,
        "output": workflow.output,
        "error": workflow.error,
        "steps": [
            {
                "id": str(step.id),
                "type": step.step_type,
                "status": step.status,
                "sequence": step.sequence,
                "output": step.output,
                "error": step.error,
            }
            for step in steps
        ],
        "jobs": [
            {
                "id": str(job.id),
                "type": job.job_type,
                "status": job.status,
                "attempts": job.attempts,
                "last_error": job.last_error,
            }
            for job in jobs
        ],
    }


# --- Post-hire employees ---

@router.get("/companies/{company_id}/employees")
def list_employees(company_id: str, status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Employee).filter(Employee.company_id == company_id)
    if status:
        query = query.filter(Employee.status == status)

    employees = query.order_by(Employee.created_at.desc()).limit(100).all()
    return [
        {
            "id": str(employee.id),
            "employee_key": employee.employee_key,
            "name": employee.name,
            "phone": employee.phone,
            "email": employee.email,
            "position_title": employee.position_title,
            "status": employee.status,
            "hire_date": employee.hire_date.isoformat(),
        }
        for employee in employees
    ]


@router.get("/employees/{employee_id}")
def get_employee(employee_id: str, db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(404, "Employee not found")

    onboarding_items = (
        db.query(OnboardingItem)
        .filter(OnboardingItem.employee_id == employee.id)
        .order_by(OnboardingItem.due_date.asc(), OnboardingItem.created_at.asc())
        .all()
    )
    employee_documents = (
        db.query(EmployeeDocument)
        .filter(EmployeeDocument.employee_id == employee.id)
        .order_by(EmployeeDocument.document_type.asc())
        .all()
    )
    compliance_documents = (
        db.query(ComplianceDocument)
        .filter(ComplianceDocument.employee_id == employee.id)
        .order_by(ComplianceDocument.document_type.asc())
        .all()
    )

    return {
        "id": str(employee.id),
        "employee_key": employee.employee_key,
        "name": employee.name,
        "phone": employee.phone,
        "email": employee.email,
        "position_title": employee.position_title,
        "status": employee.status,
        "hire_date": employee.hire_date.isoformat(),
        "start_date": employee.start_date.isoformat() if employee.start_date else None,
        "onboarding_items": [
            {
                "id": str(item.id),
                "key": item.item_key,
                "title": item.title,
                "category": item.category,
                "owner": item.owner,
                "status": item.status,
                "due_date": item.due_date.isoformat() if item.due_date else None,
                "completed_at": item.completed_at.isoformat() if item.completed_at else None,
            }
            for item in onboarding_items
        ],
        "employee_documents": [
            {
                "id": str(document.id),
                "type": document.document_type,
                "status": document.status,
                "file_url": document.file_url,
                "expires_at": document.expires_at.isoformat() if document.expires_at else None,
            }
            for document in employee_documents
        ],
        "compliance_documents": [
            {
                "id": str(document.id),
                "type": document.document_type,
                "required": document.required,
                "status": document.status,
                "expiry_date": document.expiry_date.isoformat() if document.expiry_date else None,
                "warning_days": document.warning_days,
            }
            for document in compliance_documents
        ],
    }
