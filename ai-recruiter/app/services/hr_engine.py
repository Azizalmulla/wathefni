"""
HR query engine.
Handles natural language queries from HR managers via WhatsApp.
Translates questions into database queries and returns formatted responses.
"""
import json
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.application import Application
from app.models.position import Position
from app.models.company import Company

import anthropic
from app.config import get_settings

settings = get_settings()
client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

HR_SYSTEM_PROMPT = """You are an HR assistant for a recruitment platform. 
You help HR managers query their candidate database using natural language.

Given a user query, determine the intent and extract parameters. Return JSON only:

{
    "intent": "list_candidates" | "candidate_detail" | "update_status" | "count" | "compare" | "export" | "create_position" | "list_positions" | "close_position" | "unknown",
    "filters": {
        "skills": ["python", "django"],
        "visa_status": "transferable",
        "min_experience": 3,
        "position_code": "MARKETING",
        "salary_max": 1000,
        "language": "hindi",
        "status": "new"
    },
    "candidate_name": "Ahmed",
    "new_status": "shortlisted",
    "position_title": "Marketing Manager",
    "salary_min": 800,
    "salary_max": 1200,
    "response_language": "en"
}

Only include fields that are relevant to the query. Return ONLY valid JSON.
"""


def interpret_hr_query(query: str) -> dict:
    """Use LLM to interpret an HR manager's natural language query."""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=HR_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": query}],
    )

    response_text = message.content[0].text

    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    return json.loads(response_text.strip())


def handle_hr_query(query: str, company_id: str, db: Session) -> str:
    """Process an HR query and return a WhatsApp-friendly response."""
    try:
        parsed = interpret_hr_query(query)
    except Exception:
        return "Sorry, I didn't understand that. Try something like:\n• \"How many applied today?\"\n• \"Show me Python developers\"\n• \"Shortlist Ahmed\"\n• \"Export all candidates\""

    intent = parsed.get("intent", "unknown")
    filters = parsed.get("filters", {})

    if intent == "count":
        return _handle_count(company_id, filters, db)
    elif intent == "list_candidates":
        return _handle_list(company_id, filters, db)
    elif intent == "candidate_detail":
        return _handle_detail(company_id, parsed.get("candidate_name"), db)
    elif intent == "update_status":
        return _handle_status_update(
            company_id, parsed.get("candidate_name"), parsed.get("new_status"), db
        )
    elif intent == "list_positions":
        return _handle_list_positions(company_id, db)
    elif intent == "compare":
        return _handle_compare(company_id, filters, db)
    elif intent == "export":
        return "📎 I'll prepare a CSV export. Give me a moment..."
    elif intent == "create_position":
        return _handle_create_position_prompt(parsed)
    elif intent == "close_position":
        return _handle_close_position(company_id, parsed.get("position_code", parsed.get("position_title")), db)
    else:
        return "I'm not sure what you need. Try:\n• \"Show candidates for marketing role\"\n• \"How many applied this week?\"\n• \"Tell me about Ahmed\"\n• \"Shortlist Omar\""


def _handle_count(company_id: str, filters: dict, db: Session) -> str:
    """Count candidates matching filters."""
    q = db.query(func.count(Application.id)).filter(Application.company_id == company_id)

    if filters.get("status"):
        q = q.filter(Application.status == filters["status"])

    count = q.scalar()
    return f"📊 You have **{count}** candidates{' with status: ' + filters.get('status', '') if filters.get('status') else ''}."


def _handle_list(company_id: str, filters: dict, db: Session) -> str:
    """List candidates matching filters."""
    q = (
        db.query(Candidate, Application)
        .join(Application, Application.candidate_id == Candidate.id)
        .filter(Application.company_id == company_id)
    )

    if filters.get("skills"):
        for skill in filters["skills"]:
            q = q.filter(Candidate.skills.any(skill))

    if filters.get("visa_status"):
        q = q.filter(Candidate.visa_status == filters["visa_status"])

    if filters.get("min_experience"):
        q = q.filter(Candidate.total_years_exp >= filters["min_experience"])

    results = q.limit(10).all()

    if not results:
        return "No candidates found matching those criteria."

    lines = [f"📋 Found {len(results)} candidate(s):\n"]
    for candidate, application in results:
        name = candidate.name or "Unknown"
        exp = f"{candidate.total_years_exp}y exp" if candidate.total_years_exp else "exp unknown"
        status = application.status
        skills = ", ".join(candidate.skills[:3]) if candidate.skills else "—"
        lines.append(f"• **{name}** — {exp} | {skills} | Status: {status}")

    return "\n".join(lines)


def _handle_detail(company_id: str, candidate_name: str, db: Session) -> str:
    """Get detailed info about a specific candidate."""
    if not candidate_name:
        return "Which candidate? Give me a name."

    candidate = (
        db.query(Candidate)
        .join(Application, Application.candidate_id == Candidate.id)
        .filter(
            Application.company_id == company_id,
            Candidate.name.ilike(f"%{candidate_name}%"),
        )
        .first()
    )

    if not candidate:
        return f"No candidate named '{candidate_name}' found."

    lines = [
        f"👤 **{candidate.name}**",
        f"📞 {candidate.phone}",
        f"📧 {candidate.email or '—'}",
        f"🎓 {_format_education(candidate.education)}",
        f"💼 {candidate.total_years_exp or '?'} years experience",
        f"🛠 Skills: {', '.join(candidate.skills) if candidate.skills else '—'}",
        f"🗣 Languages: {_format_languages(candidate.languages)}",
        f"📋 Visa: {candidate.visa_status or '—'}",
        f"💰 Expected: {candidate.expected_salary or '?'} KD",
        f"📅 Available: {candidate.availability or '—'}",
    ]

    if candidate.ai_summary:
        lines.append(f"\n🤖 AI Summary: {candidate.ai_summary}")

    return "\n".join(lines)


def _handle_status_update(company_id: str, candidate_name: str, new_status: str, db: Session) -> str:
    """Update a candidate's application status."""
    if not candidate_name or not new_status:
        return "Please specify: \"Shortlist [name]\" or \"Reject [name]\""

    valid_statuses = ["new", "reviewed", "shortlisted", "interview", "offered", "hired", "rejected"]
    if new_status.lower() not in valid_statuses:
        return f"Invalid status. Use one of: {', '.join(valid_statuses)}"

    application = (
        db.query(Application)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .filter(
            Application.company_id == company_id,
            Candidate.name.ilike(f"%{candidate_name}%"),
        )
        .first()
    )

    if not application:
        return f"No application found for '{candidate_name}'."

    old_status = application.status
    application.status = new_status.lower()
    application.status_changed_at = datetime.utcnow()
    db.commit()

    return f"✅ Updated {candidate_name}: {old_status} → **{new_status}**"


def _handle_list_positions(company_id: str, db: Session) -> str:
    """List active positions for the company."""
    positions = (
        db.query(Position)
        .filter(Position.company_id == company_id, Position.is_active == True)
        .all()
    )

    if not positions:
        return "No active positions. Text me to create one!"

    lines = ["📌 Your active positions:\n"]
    for p in positions:
        app_count = db.query(func.count(Application.id)).filter(Application.position_id == p.id).scalar()
        salary = f"{p.salary_min}-{p.salary_max} KD" if p.salary_min else "—"
        lines.append(f"• **{p.title}** ({p.code}) — {salary} | {app_count} applicants")

    return "\n".join(lines)


def _handle_compare(company_id: str, filters: dict, db: Session) -> str:
    """Compare top candidates for a position."""
    q = (
        db.query(Candidate, Application)
        .join(Application, Application.candidate_id == Candidate.id)
        .filter(Application.company_id == company_id)
    )

    if filters.get("position_code"):
        q = q.join(Position, Position.id == Application.position_id).filter(
            Position.code.ilike(f"%{filters['position_code']}%")
        )

    results = q.limit(3).all()

    if not results:
        return "No candidates to compare."

    lines = ["🔍 Top candidates comparison:\n"]
    for i, (candidate, application) in enumerate(results, 1):
        name = candidate.name or "Unknown"
        exp = candidate.total_years_exp or "?"
        skills = ", ".join(candidate.skills[:5]) if candidate.skills else "—"
        salary = candidate.expected_salary or "?"
        lines.append(f"{i}. **{name}** — {exp}y exp | {skills} | {salary} KD")

    return "\n".join(lines)


def _handle_create_position_prompt(parsed: dict) -> str:
    """Return a prompt to collect position details."""
    title = parsed.get("position_title", "")
    return f"Creating position: **{title}**\n\nI need a few details:\n1. Job description (brief)\n2. Key requirements\n3. Salary range (KD)\n4. Location\n5. Any custom screening questions?\n\nSend them one by one or all at once."


def _handle_close_position(company_id: str, position_ref: str, db: Session) -> str:
    """Close/deactivate a position."""
    if not position_ref:
        return "Which position do you want to close?"

    position = (
        db.query(Position)
        .filter(
            Position.company_id == company_id,
            (Position.code.ilike(f"%{position_ref}%")) | (Position.title.ilike(f"%{position_ref}%")),
        )
        .first()
    )

    if not position:
        return f"No position found matching '{position_ref}'."

    position.is_active = False
    db.commit()
    return f"✅ Closed position: **{position.title}** ({position.code})"


def _format_education(education: list | None) -> str:
    if not education:
        return "—"
    items = []
    for e in education[:2]:
        if isinstance(e, dict):
            items.append(f"{e.get('degree', '?')} @ {e.get('institution', '?')}")
    return "; ".join(items) if items else "—"


def _format_languages(languages: list | None) -> str:
    if not languages:
        return "—"
    items = []
    for l in languages:
        if isinstance(l, dict):
            items.append(f"{l.get('language', '?')} ({l.get('level', '?')})")
    return ", ".join(items) if items else "—"
