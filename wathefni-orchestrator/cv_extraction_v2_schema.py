"""cv-extraction-v2 JSON schema for Mistral Document AI annotations.

Extensible, not exhaustive. Semantic multilingual section classification is
enforced by the extraction prompt + schema descriptions — not exact headings.

Mistral strict json_schema requires additionalProperties=false and required
lists that include every property key.
"""

from __future__ import annotations

from typing import Any

CV_EXTRACTION_V2_SCHEMA_NAME = "cv-extraction-v2"
CV_EXTRACTION_V2_CONTRACT = "cv-extraction-v2"
CV_EXTRACTION_V2_EXTRACTOR = "mistral-document-ai-v2"
CV_PROFILE_FACTS_V2_SCHEMA = "candidate-profile-facts-v2"

_STRING = {"type": ["string", "null"]}
_STRING_LIST = {"type": "array", "items": {"type": "string"}}
_INT_NULL = {"type": ["integer", "null"]}


def _source_evidence() -> dict[str, Any]:
    props = {
        "page": _INT_NULL,
        "block_id": _STRING,
        "quote": _STRING,
        "order": _INT_NULL,
    }
    return {
        "type": ["object", "null"],
        "additionalProperties": False,
        "properties": props,
        "required": list(props.keys()),
    }


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": props,
        "required": list(props.keys()),
    }


def _employment_item() -> dict[str, Any]:
    return _obj(
        {
            "title": _STRING,
            "company": _STRING,
            "location": _STRING,
            "start_date": _STRING,
            "end_date": _STRING,
            "description": _STRING,
            "achievements": _STRING_LIST,
            "source_evidence": _source_evidence(),
        }
    )


def _volunteer_item() -> dict[str, Any]:
    return _obj(
        {
            "role": _STRING,
            "organization": _STRING,
            "location": _STRING,
            "start_date": _STRING,
            "end_date": _STRING,
            "description": _STRING,
            "achievements": _STRING_LIST,
            "source_evidence": _source_evidence(),
        }
    )


def _education_item() -> dict[str, Any]:
    return _obj(
        {
            "degree": _STRING,
            "institution": _STRING,
            "location": _STRING,
            "start_date": _STRING,
            "end_date": _STRING,
            "gpa": _STRING,
            "honors": _STRING,
            "source_evidence": _source_evidence(),
        }
    )


def _award_item() -> dict[str, Any]:
    return _obj(
        {
            "title": _STRING,
            "issuing_organization": _STRING,
            "date": _STRING,
            "description": _STRING,
            "source_evidence": _source_evidence(),
        }
    )


def _simple_named_item(*fields: str) -> dict[str, Any]:
    props = {name: _STRING for name in fields}
    props["source_evidence"] = _source_evidence()
    return _obj(props)


def _unmodeled_section() -> dict[str, Any]:
    return _obj(
        {
            "original_heading": _STRING,
            "items": {"type": "array", "items": {"type": "string"}},
            "content": _STRING,
            "language": _STRING,
            "document_order": _INT_NULL,
            "source_evidence": _source_evidence(),
            "reason": _STRING,
        }
    )


def cv_extraction_v2_json_schema() -> dict[str, Any]:
    """Strict JSON schema for Mistral document_annotation_format / chat response_format."""
    props: dict[str, Any] = {
        "schema_version": {"type": "string"},
        "professional_summary": _STRING,
        "contact_details": _obj(
            {
                "full_name": _STRING,
                "email": _STRING,
                "phone": _STRING,
                "location": _STRING,
                "links": _STRING_LIST,
            }
        ),
        "employment": {"type": "array", "items": _employment_item()},
        "volunteer_work": {"type": "array", "items": _volunteer_item()},
        "education": {"type": "array", "items": _education_item()},
        "skills": {
            "type": "array",
            "items": _obj(
                {
                    "name": _STRING,
                    "category": _STRING,
                    "source_evidence": _source_evidence(),
                }
            ),
        },
        "languages": {
            "type": "array",
            "items": _obj(
                {
                    "language": _STRING,
                    "proficiency": _STRING,
                    "source_evidence": _source_evidence(),
                }
            ),
        },
        "projects": {
            "type": "array",
            "items": _simple_named_item(
                "name", "role", "description", "start_date", "end_date", "organization"
            ),
        },
        "publications": {
            "type": "array",
            "items": _simple_named_item(
                "title", "authors", "venue", "date", "description", "status"
            ),
        },
        "certifications": {
            "type": "array",
            "items": _simple_named_item(
                "name", "issuer", "date", "credential_id", "description"
            ),
        },
        "training_courses": {
            "type": "array",
            "items": _simple_named_item(
                "name", "provider", "date", "status", "description", "location"
            ),
        },
        "memberships_activities": {
            "type": "array",
            "items": _simple_named_item(
                "name", "organization", "role", "start_date", "end_date", "description"
            ),
        },
        "awards_honors": {"type": "array", "items": _award_item()},
        "references": {
            "type": "array",
            "items": _simple_named_item(
                "name", "title", "organization", "email", "phone", "relationship"
            ),
        },
        "availability": _STRING,
        "unmodeled_sections": {"type": "array", "items": _unmodeled_section()},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": props,
        "required": list(props.keys()),
    }


def document_annotation_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": CV_EXTRACTION_V2_SCHEMA_NAME,
            "schema": cv_extraction_v2_json_schema(),
            "strict": True,
        },
    }


DOCUMENT_ANNOTATION_PROMPT = """
You are Wathefni CV Extraction V2.

Extract the candidate CV into the provided JSON schema.

Rules:
1. Classify sections by meaning across languages (EN/AR and others), not exact heading text.
   Examples:
   - Career History / Work Experience / الخبرة → employment
   - Academic Background / Education / التعليم → education
   - Recognition / Distinctions / الجوائز → awards_honors
   - Community Service / Volunteer → volunteer_work
   - Professional Development / Online Courses / Bootcamp → training_courses
   - Selected Publications & Reports → publications
   - Additional Information languages → languages
2. Keep employment and volunteer_work as separate arrays. Never merge them.
3. Skills must contain genuine skills only. Never put publications, references, emails,
   courses, awards, or section headings into skills.
4. Education records store degree/institution/location/dates/GPA/honors only.
   Course lists, memberships, clubs, and bootcamps belong in training_courses or
   memberships_activities — not as flat education strings.
5. Preserve every content block. If a section is unknown or ambiguous, put it in
   unmodeled_sections with original_heading, items/content, language, document_order,
   and source evidence. Never silently drop content or force it into the nearest category.
6. Use null for unknown scalars and [] for empty arrays.
7. schema_version must be "cv-extraction-v2".
8. Prefer source quotes from the document when possible.
""".strip()


__all__ = [
    "CV_EXTRACTION_V2_CONTRACT",
    "CV_EXTRACTION_V2_EXTRACTOR",
    "CV_EXTRACTION_V2_SCHEMA_NAME",
    "CV_PROFILE_FACTS_V2_SCHEMA",
    "DOCUMENT_ANNOTATION_PROMPT",
    "cv_extraction_v2_json_schema",
    "document_annotation_format",
]
