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
from app.models.position import Position
from app.models.hr_user import HRUser
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
    qr_path = generate_qr_code(company.code, data.code)
    position.qr_code_url = qr_path

    db.commit()
    db.refresh(position)

    return {
        "id": str(position.id),
        "title": position.title,
        "code": position.code,
        "qr_code_path": qr_path,
        "apply_link": f"https://wa.me/96599338566?text=APPLY-{company.code}-{data.code}",
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
