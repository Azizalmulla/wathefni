"""
Message routing service.
Determines if an incoming WhatsApp message is from a candidate or an HR user,
and routes it to the appropriate handler.
"""
from sqlalchemy.orm import Session

from app.models.hr_user import HRUser
from app.models.employee import Employee
from app.models.candidate import Candidate


def identify_sender(phone: str, db: Session) -> dict:
    """
    Look up a phone number and determine if it belongs to an HR user or a candidate.
    
    Returns:
        {
            "type": "hr" | "employee" | "candidate" | "unknown",
            "user": HRUser | Candidate | None,
            "company_id": UUID | None
        }
    """
    # Check if sender is a registered HR user
    hr_user = db.query(HRUser).filter(
        HRUser.phone == phone,
        HRUser.is_active == True
    ).first()

    if hr_user:
        return {
            "type": "hr",
            "user": hr_user,
            "company_id": hr_user.company_id,
        }

    # Employees are routed before candidates because a hired candidate can exist in both tables.
    employee = db.query(Employee).filter(Employee.phone == phone).first()
    if employee:
        return {
            "type": "employee",
            "user": employee,
            "company_id": employee.company_id,
        }

    # Check if sender is an existing candidate
    candidate = db.query(Candidate).filter(Candidate.phone == phone).first()

    if candidate:
        return {
            "type": "candidate",
            "user": candidate,
            "company_id": None,
        }

    # Unknown sender — treat as new candidate
    return {
        "type": "unknown",
        "user": None,
        "company_id": None,
    }


def parse_apply_code(message: str) -> dict | None:
    """
    Parse an APPLY code from the first message.
    Format: APPLY-{COMPANY_CODE}-{POSITION_CODE}
    
    Returns:
        {"company_code": str, "position_code": str} or None
    """
    message = message.strip().upper()

    if not message.startswith("APPLY-"):
        return None

    parts = message.split("-")
    if len(parts) < 3:
        return None

    return {
        "company_code": parts[1],
        "position_code": "-".join(parts[2:]),  # Handle position codes with dashes
    }
