"""
WhatsApp webhook handler.
Receives incoming messages from WhatsApp Cloud API and routes them.
"""
from fastapi import APIRouter, Request, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import get_settings
from app.services.routing import identify_sender, parse_apply_code
from app.services.whatsapp import parse_webhook_message, send_text_message
from app.services.hr_engine import handle_hr_query
from app.services.screening import (
    get_screening_questions,
    generate_screening_response,
    generate_completion_message,
    detect_language,
)
from app.models.candidate import Candidate
from app.models.application import Application
from app.models.position import Position
from app.models.company import Company
from app.models.conversation import Conversation

router = APIRouter()
settings = get_settings()

# In-memory session state for active screening conversations
# In production, move this to Redis or database
screening_sessions: dict = {}


@router.get("/webhook/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Meta webhook verification endpoint."""
    if hub_mode == "subscribe" and hub_token == settings.whatsapp_verify_token:
        return int(hub_challenge)
    return {"error": "verification failed"}


@router.post("/webhook/whatsapp")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle incoming WhatsApp messages."""
    body = await request.json()

    # Parse the webhook payload
    message = parse_webhook_message(body)
    if not message:
        return {"status": "no_message"}

    sender_phone = message["from"]
    text = message.get("text", "")
    msg_type = message["type"]

    # Log the conversation
    _log_message(db, sender_phone, "inbound", msg_type, text)

    # Identify the sender
    sender = identify_sender(sender_phone, db)

    if sender["type"] == "hr":
        # HR manager — route to HR query engine
        response = handle_hr_query(text, str(sender["company_id"]), db)
        await send_text_message(sender_phone, response)
        _log_message(db, sender_phone, "outbound", "text", response)
        return {"status": "hr_response_sent"}

    elif sender["type"] == "candidate":
        # Existing candidate — check if they're in a screening session
        return await _handle_candidate_message(sender_phone, text, msg_type, message, db)

    else:
        # Unknown sender — check if it's an APPLY code
        apply_code = parse_apply_code(text)

        if apply_code:
            return await _handle_new_application(sender_phone, message["name"], apply_code, db)
        else:
            # Not an apply code — send a welcome message
            welcome = (
                "👋 Welcome to AI Recruiter by AI Octopus!\n\n"
                "To apply for a job, please scan the QR code on the job posting.\n\n"
                "If you've already applied, I'll remember you — just send me a message."
            )
            await send_text_message(sender_phone, welcome)
            return {"status": "welcome_sent"}


async def _handle_new_application(
    phone: str, name: str, apply_code: dict, db: Session
) -> dict:
    """Handle a new candidate starting an application via QR code."""
    # Find the company and position
    company = db.query(Company).filter(Company.code == apply_code["company_code"]).first()
    if not company:
        await send_text_message(phone, "Sorry, I couldn't find that company. Please check the QR code and try again.")
        return {"status": "company_not_found"}

    position = (
        db.query(Position)
        .filter(
            Position.company_id == company.id,
            Position.code == apply_code["position_code"],
            Position.is_active == True,
        )
        .first()
    )
    if not position:
        await send_text_message(phone, "Sorry, that position is no longer available.")
        return {"status": "position_not_found"}

    # Create or get candidate
    candidate = db.query(Candidate).filter(Candidate.phone == phone).first()
    if not candidate:
        candidate = Candidate(phone=phone, name=name)
        db.add(candidate)
        db.flush()

    # Create application
    application = Application(
        candidate_id=candidate.id,
        position_id=position.id,
        company_id=company.id,
        status="new",
    )
    db.add(application)
    db.commit()

    # Ask for CV
    lang = detect_language(name)
    if lang == "ar":
        msg = (
            f"مرحبا {name}! 👋\n\n"
            f"تقدمت لوظيفة **{position.title}** في **{company.name}**.\n\n"
            f"أرسل لي سيرتك الذاتية (PDF) وبأبدأ بمراجعتها."
        )
    else:
        msg = (
            f"Hi {name}! 👋\n\n"
            f"You're applying for **{position.title}** at **{company.name}**.\n\n"
            f"Please send me your CV as a PDF and I'll start reviewing it."
        )

    await send_text_message(phone, msg)

    # Set up screening session
    screening_sessions[phone] = {
        "state": "waiting_cv",
        "candidate_id": str(candidate.id),
        "application_id": str(application.id),
        "position_id": str(position.id),
        "company_id": str(company.id),
        "company_name": company.name,
        "position_title": position.title,
        "language": lang,
        "screening_questions": get_screening_questions(position.screening_questions),
        "current_question": 0,
        "answers": {},
    }

    return {"status": "application_started"}


async def _handle_candidate_message(
    phone: str, text: str, msg_type: str, message: dict, db: Session
) -> dict:
    """Handle messages from an existing candidate (may be in screening flow)."""
    session = screening_sessions.get(phone)

    if not session:
        # No active session — they might be checking status
        msg = (
            "Hi! If you'd like to apply for a new position, "
            "please scan the QR code on the job posting.\n\n"
            "If you've already applied, your application is being reviewed."
        )
        await send_text_message(phone, msg)
        return {"status": "no_session"}

    state = session["state"]

    if state == "waiting_cv":
        if msg_type in ("document", "image"):
            # They sent a CV — for now, acknowledge it
            # In production: download, parse, extract
            session["state"] = "screening"
            session["current_question"] = 0

            questions = session["screening_questions"]
            first_q = questions[0]
            candidate_name = db.query(Candidate).filter(Candidate.phone == phone).first()
            name = candidate_name.name if candidate_name else "there"

            msg = generate_screening_response(
                candidate_name=name,
                position_title=session["position_title"],
                company_name=session["company_name"],
                current_question=first_q,
                question_number=1,
                total_questions=len(questions),
                language=session["language"],
            )
            await send_text_message(phone, msg)
            return {"status": "screening_started"}
        else:
            # They sent text instead of a CV
            lang = session["language"]
            if lang == "ar":
                await send_text_message(phone, "أرسل لي سيرتك الذاتية كملف PDF أو صورة من فضلك 📄")
            else:
                await send_text_message(phone, "Please send your CV as a PDF or image file 📄")
            return {"status": "waiting_cv"}

    elif state == "screening":
        # Record the answer
        questions = session["screening_questions"]
        current_idx = session["current_question"]
        current_q = questions[current_idx]

        session["answers"][current_q["key"]] = text
        session["current_question"] += 1

        if session["current_question"] >= len(questions):
            # Screening complete
            session["state"] = "complete"

            # Save screening answers to database
            from app.models.application import Application as AppModel

            app = db.query(AppModel).filter(
                AppModel.id == session["application_id"]
            ).first()
            if app:
                app.screening_answers = session["answers"]
                db.commit()

            # Update candidate Kuwait-specific fields
            candidate = db.query(Candidate).filter(Candidate.phone == phone).first()
            if candidate:
                answers = session["answers"]
                candidate.visa_status = answers.get("visa_status")
                candidate.expected_salary = _parse_salary(answers.get("expected_salary"))
                candidate.availability = answers.get("availability")
                db.commit()

            candidate_obj = db.query(Candidate).filter(Candidate.phone == phone).first()
            name = candidate_obj.name if candidate_obj else "there"

            msg = generate_completion_message(
                candidate_name=name,
                position_title=session["position_title"],
                company_name=session["company_name"],
                language=session["language"],
            )
            await send_text_message(phone, msg)

            # Clean up session
            del screening_sessions[phone]
            return {"status": "screening_complete"}
        else:
            # Next question
            next_q = questions[session["current_question"]]
            msg = generate_screening_response(
                candidate_name="",
                position_title=session["position_title"],
                company_name=session["company_name"],
                current_question=next_q,
                question_number=session["current_question"] + 1,
                total_questions=len(questions),
                language=session["language"],
            )
            await send_text_message(phone, msg)
            return {"status": "next_question"}

    return {"status": "unhandled"}


def _log_message(db: Session, phone: str, direction: str, msg_type: str, content: str):
    """Log a conversation message."""
    candidate = db.query(Candidate).filter(Candidate.phone == phone).first()
    if candidate:
        conv = Conversation(
            candidate_id=candidate.id,
            direction=direction,
            message_type=msg_type,
            content=content[:5000] if content else "",
        )
        db.add(conv)
        db.commit()


def _parse_salary(text: str | None) -> float | None:
    """Try to extract a number from a salary answer."""
    if not text:
        return None
    import re
    numbers = re.findall(r"\d+", text)
    if numbers:
        return float(numbers[0])
    return None
