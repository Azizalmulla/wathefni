"""
CV parsing service.
Extracts text from PDF/images and uses LLM to parse into structured data.
"""
import json
import os

import anthropic
from PyPDF2 import PdfReader

from app.config import get_settings

settings = get_settings()
client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

CV_PARSE_PROMPT = """You are a CV/resume parser. Extract the following information from this CV text and return it as JSON.
Be thorough — extract everything available. If a field is not found, use null.

Return ONLY valid JSON in this exact format:
{
    "name": "Full name in English",
    "name_ar": "Full name in Arabic if present, else null",
    "email": "email@example.com",
    "phone": "+965XXXXXXXX",
    "education": [
        {"degree": "BSc Computer Science", "institution": "Kuwait University", "year": 2020, "field": "Computer Science"}
    ],
    "experience": [
        {"title": "Software Developer", "company": "Company X", "duration": "2 years", "description": "Built web apps..."}
    ],
    "skills": ["Python", "Django", "SQL"],
    "languages": [
        {"language": "Arabic", "level": "native"},
        {"language": "English", "level": "fluent"}
    ],
    "certifications": ["AWS Certified", "PMP"],
    "total_years_exp": 5,
    "nationality": "Kuwaiti",
    "summary": "Brief 2-3 sentence summary of this candidate's profile"
}

CV TEXT:
"""


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file."""
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text.strip()


def parse_cv_with_llm(cv_text: str) -> dict:
    """Send CV text to Claude and get structured JSON back."""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": CV_PARSE_PROMPT + cv_text,
            }
        ],
    )

    response_text = message.content[0].text

    # Extract JSON from response (handle markdown code blocks)
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    return json.loads(response_text.strip())


def parse_cv(file_path: str) -> dict:
    """Full pipeline: file → text → LLM → structured data."""
    # Extract text based on file type
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        cv_text = extract_text_from_pdf(file_path)
    else:
        # For images, we'd use vision API — placeholder for now
        raise ValueError(f"Unsupported file type: {ext}. PDF only for now.")

    if not cv_text or len(cv_text) < 50:
        raise ValueError("Could not extract enough text from CV. Please send a clearer PDF.")

    # Parse with LLM
    parsed = parse_cv_with_llm(cv_text)

    # Attach the raw text
    parsed["cv_text"] = cv_text

    return parsed
