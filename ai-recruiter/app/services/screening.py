"""
Screening conversation engine.
Manages the stateful screening flow for candidates.
"""
import json

import anthropic

from app.config import get_settings

settings = get_settings()
client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# Default screening questions for Kuwait
DEFAULT_QUESTIONS = [
    {
        "key": "visa_status",
        "question_en": "What is your current visa/residency status in Kuwait? (citizen, valid work permit, transferable, visit visa)",
        "question_ar": "شنو وضعك الحالي بالكويت؟ (مواطن، إقامة عمل سارية، إقامة قابلة للتحويل، زيارة)",
    },
    {
        "key": "expected_salary",
        "question_en": "What is your expected monthly salary in KD?",
        "question_ar": "شقد الراتب المتوقع بالدينار الكويتي؟",
    },
    {
        "key": "availability",
        "question_en": "When can you start? (immediately, 2 weeks, 1 month, other)",
        "question_ar": "متى تقدر تبدأ؟ (فوري، أسبوعين، شهر، غير)",
    },
    {
        "key": "languages",
        "question_en": "What languages do you speak fluently?",
        "question_ar": "شنو اللغات اللي تتكلمها بطلاقة؟",
    },
]


def get_screening_questions(position_questions: list | None = None) -> list:
    """
    Combine default Kuwait-specific questions with position-specific ones.
    """
    questions = list(DEFAULT_QUESTIONS)

    if position_questions:
        for q in position_questions:
            questions.append({
                "key": q.get("key", f"custom_{len(questions)}"),
                "question_en": q.get("question_en", q.get("question", "")),
                "question_ar": q.get("question_ar", ""),
            })

    return questions


def generate_screening_response(
    candidate_name: str,
    position_title: str,
    company_name: str,
    current_question: dict,
    question_number: int,
    total_questions: int,
    language: str = "en",
) -> str:
    """Generate a natural screening question message."""
    q = current_question.get(f"question_{language}", current_question.get("question_en", ""))

    if question_number == 1:
        if language == "ar":
            return f"شكراً {candidate_name}! استلمت سيرتك الذاتية لوظيفة {position_title} في {company_name}.\n\nعندي {total_questions} أسئلة سريعة:\n\n{question_number}. {q}"
        return f"Thanks {candidate_name}! I've received your CV for the {position_title} role at {company_name}.\n\nI have {total_questions} quick screening questions:\n\n{question_number}. {q}"
    else:
        if language == "ar":
            return f"👍 تمام.\n\n{question_number}. {q}"
        return f"👍 Got it.\n\n{question_number}. {q}"


def generate_completion_message(
    candidate_name: str,
    position_title: str,
    company_name: str,
    language: str = "en",
) -> str:
    """Generate the screening complete message."""
    if language == "ar":
        return f"✅ شكراً {candidate_name}! خلصنا الأسئلة.\n\nتقديمك لوظيفة {position_title} في {company_name} تم بنجاح. فريق الموارد البشرية راح يراجع تقديمك وبيتواصلون معاك.\n\nبالتوفيق! 🤞"
    return f"✅ Thanks {candidate_name}! Screening complete.\n\nYour application for {position_title} at {company_name} has been submitted. The HR team will review your profile and get back to you.\n\nGood luck! 🤞"


def detect_language(text: str) -> str:
    """Simple language detection — checks for Arabic characters."""
    arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
    if arabic_chars > len(text) * 0.3:
        return "ar"
    return "en"
