"""Wathefni internal CV Extraction V2 — provider-independent fallback.

Outputs the exact same `cv-extraction-v2` contract as Mistral Document AI.
Never creates a competing schema or silently overwrites stronger provider facts.
"""

from __future__ import annotations

import re
from typing import Any

from cv_extraction_v2_schema import CV_EXTRACTION_V2_CONTRACT

INTERNAL_EXTRACTOR_VERSION = "wathefni-internal-v2"

# Semantic multilingual heading aliases (meaning, not exact match only).
_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "employment": (
        "experience",
        "work experience",
        "employment",
        "professional experience",
        "career history",
        "career",
        "work history",
        "الخبرة",
        "الخبرات",
        "الخبرة العملية",
        "خبرات العمل",
    ),
    "volunteer_work": (
        "volunteer",
        "volunteering",
        "volunteer work",
        "community service",
        "community involvement",
        "تطوع",
        "العمل التطوعي",
        "خدمة المجتمع",
    ),
    "education": (
        "education",
        "academic background",
        "academic",
        "qualifications",
        "التعليم",
        "المؤهلات",
        "الخلفية الأكاديمية",
    ),
    "skills": (
        "skills",
        "key skills",
        "technical skills",
        "competencies",
        "core competencies",
        "المهارات",
        "مهارات",
    ),
    "languages": (
        "languages",
        "language",
        "اللغات",
        "لغة",
    ),
    "projects": (
        "projects",
        "selected projects",
        "technical projects",
        "المشاريع",
        "مشاريع",
    ),
    "publications": (
        "publications",
        "selected publications",
        "selected publications & reports",
        "reports",
        "research",
        "المنشورات",
        "الأبحاث",
    ),
    "certifications": (
        "certifications",
        "certificates",
        "licenses",
        "الشهادات",
        "شهادات",
    ),
    "training_courses": (
        "training",
        "courses",
        "online courses",
        "professional development",
        "bootcamp",
        "workshops",
        "التدريب",
        "الدورات",
        "التطوير المهني",
    ),
    "memberships_activities": (
        "activities",
        "memberships",
        "clubs",
        "affiliations",
        "extracurricular",
        "الأنشطة",
        "العضويات",
        "النوادي",
    ),
    "awards_honors": (
        "awards",
        "honors",
        "honours",
        "recognition",
        "distinctions",
        "achievements",
        "الجوائز",
        "التكريمات",
        "الإنجازات",
    ),
    "references": (
        "references",
        "referees",
        "المراجع",
    ),
    "professional_summary": (
        "summary",
        "profile",
        "professional summary",
        "about",
        "objective",
        "نبذة",
        "الملخص",
        "الهدف",
    ),
}

_DATE_RE = re.compile(
    r"(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4}(?:[-/]\d{1,2})?)"
    r"(?:\s*[–—\-to]+\s*"
    r"(?P<end>(?:Present|Current|Now|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4}(?:[-/]\d{1,2})?)))?",
    re.I,
)
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?)?\d{3,4}[\s-]?\d{3,4}")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)
_SKILL_CONTAMINATION = re.compile(
    r"publication|report|reference|@|online course|languages?\s*:|selected publications|http|dr\.",
    re.I,
)
_EMP_LINE_RE = re.compile(
    r"^(?P<title>.+?)(?:\s+[–—\-@|]\s+|\s+at\s+|\s+لدى\s+)(?P<company>.+)$",
    re.I,
)


def _norm_heading(line: str) -> str:
    return re.sub(r"[:：\s]+$", "", str(line or "").strip()).casefold()


def classify_heading(line: str) -> str | None:
    raw = str(line or "").strip()
    normalized = _norm_heading(raw)
    if not normalized or len(normalized) > 80:
        return None
    # Inline fields like "Languages: Arabic, English" or "Online Courses: IFRS ..."
    # are content rows, not section headings.
    if re.search(r"[:：]\s*\S+", raw):
        label = re.split(r"[:：]", raw, maxsplit=1)[0].strip()
        if len(label.split()) <= 4:
            return None
    for section, aliases in _SECTION_ALIASES.items():
        alias_set = {a.casefold() for a in aliases}
        if normalized in alias_set:
            return section
    if len(normalized.split()) <= 6 and len(normalized) <= 48:
        for section, aliases in _SECTION_ALIASES.items():
            for alias in aliases:
                a = alias.casefold()
                if len(a) >= 5 and (normalized == a or normalized.startswith(a + " ") or normalized.startswith(a + "&")):
                    return section
    return None


def _lines(text: str) -> list[str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return [re.sub(r"[ \t]+", " ", line).strip() for line in raw.split("\n")]


def segment_blocks(text: str) -> list[dict[str, Any]]:
    """Deterministic reading-order section blocks with document order."""
    blocks: list[dict[str, Any]] = []
    current_section = "header"
    current_heading = None
    current_lines: list[str] = []
    order = 0

    def flush() -> None:
        nonlocal order, current_lines, current_heading
        if not current_lines and current_section == "header":
            return
        order += 1
        blocks.append(
            {
                "section": current_section,
                "original_heading": current_heading,
                "lines": list(current_lines),
                "document_order": order,
                "language": _guess_language("\n".join(current_lines)),
            }
        )
        current_lines = []

    for line in _lines(text):
        if not line:
            continue
        heading = classify_heading(line)
        if heading:
            flush()
            current_section = heading
            current_heading = line.strip()
            continue
        current_lines.append(line)
    flush()
    return blocks


def _guess_language(text: str) -> str | None:
    if not text:
        return None
    arabic = len(re.findall(r"[\u0600-\u06FF]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if arabic and latin:
        return "mixed"
    if arabic > latin:
        return "ar"
    if latin:
        return "en"
    return None


def _parse_dates(line: str) -> tuple[str | None, str | None]:
    match = _DATE_RE.search(line)
    if not match:
        return None, None
    return match.group("start"), match.group("end")


def _split_items(lines: list[str], *, split_commas: bool = False) -> list[str]:
    items: list[str] = []
    for line in lines:
        if re.match(r"^[-*•●▪]\s+", line):
            items.append(re.sub(r"^[-*•●▪]\s+", "", line).strip())
            continue
        if "|" in line or "·" in line or ";" in line or (split_commas and "," in line):
            parts = re.split(r"[|·;,]" if split_commas else r"[|·;]", line)
            items.extend(p.strip(" ,") for p in parts if p.strip(" ,"))
            continue
        items.append(line)
    return [i for i in items if i]


def _parse_employment(lines: list[str]) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lines:
        start, end = _parse_dates(line)
        emp = _EMP_LINE_RE.match(line)
        looks_like_role = bool(emp) or (start and len(line) < 140)
        if looks_like_role:
            if current:
                roles.append(current)
            title = None
            company = None
            if emp:
                title = emp.group("title").strip(" ,-|")
                company = emp.group("company").strip(" ,-|")
                # Strip trailing dates from company/title.
                company = _DATE_RE.sub("", company or "").strip(" ,-|")
                title = _DATE_RE.sub("", title or "").strip(" ,-|")
            else:
                cleaned = _DATE_RE.sub("", line).strip(" ,-|–—")
                title = cleaned or line
            current = {
                "title": title,
                "company": company,
                "location": None,
                "start_date": start,
                "end_date": end,
                "description": None,
                "achievements": [],
                "source_evidence": {"quote": line[:240], "order": len(roles) + 1},
            }
            continue
        if current:
            if line.startswith(("-", "*", "•")) or line[:1].isdigit():
                current["achievements"].append(re.sub(r"^[-*•●▪\d.)\s]+", "", line).strip())
            elif not current.get("description"):
                current["description"] = line
            else:
                current["achievements"].append(line)
    if current:
        roles.append(current)
    return roles


def _parse_education(lines: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    buf: list[str] = []
    for line in lines + [""]:
        if not line and buf:
            blob = " ".join(buf)
            start, end = _parse_dates(blob)
            degree = None
            institution = None
            gpa = None
            honors = None
            for part in buf:
                if re.search(r"bachelor|master|phd|diploma|b\.?sc|m\.?sc|mba|شهادة|بكالوريوس|ماجستير", part, re.I):
                    degree = part
                elif re.search(r"university|college|school|معهد|جامعة|مدرسة", part, re.I):
                    institution = part
                gpa_match = re.search(r"GPA\s*[:=]?\s*([0-9.]+(?:\s*/\s*[0-9.]+)?)", part, re.I)
                if gpa_match:
                    gpa = gpa_match.group(1)
                if re.search(r"honor|distinction|cum laude|تكريم", part, re.I):
                    honors = part
            # Skip obvious courses/bootcamps — caller may move them.
            records.append(
                {
                    "degree": degree or (buf[0] if buf else None),
                    "institution": institution,
                    "location": None,
                    "start_date": start,
                    "end_date": end,
                    "gpa": gpa,
                    "honors": honors,
                    "source_evidence": {"quote": blob[:240], "order": len(records) + 1},
                }
            )
            buf = []
            continue
        if line:
            buf.append(line)
    return records


def _parse_named_list(lines: list[str], name_key: str = "name") -> list[dict[str, Any]]:
    out = []
    for idx, item in enumerate(_split_items(lines), start=1):
        if _SKILL_CONTAMINATION.search(item) and name_key == "name":
            # skills path filters separately
            pass
        out.append({name_key: item, "source_evidence": {"quote": item[:240], "order": idx}})
    return out


def _contact_details(text: str, header_lines: list[str]) -> dict[str, Any]:
    emails = _EMAIL_RE.findall(text)[:3]
    phones = _PHONE_RE.findall(text)[:3]
    links = _URL_RE.findall(text)[:5]
    full_name = None
    for line in header_lines[:5]:
        if _EMAIL_RE.search(line) or _PHONE_RE.search(line) or classify_heading(line):
            continue
        if 2 <= len(line.split()) <= 6 and not re.search(r"\d{4}", line):
            full_name = line
            break
    location = None
    for line in header_lines[:12]:
        if re.search(r"Kuwait|Dubai|Riyadh|Doha|Cairo|Remote|الكويت|دبي", line, re.I):
            location = line
            break
    return {
        "full_name": full_name,
        "email": emails[0] if emails else None,
        "phone": phones[0] if phones else None,
        "location": location,
        "links": links,
    }


def extract_internal_v2(
    *,
    extracted_text: str,
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Produce schema-valid cv-extraction-v2 from native text/structure. No invention."""
    text = str(extracted_text or "")
    segmented = segment_blocks(text)
    # Optional external blocks ignored for classification but preserved as evidence hint.
    _ = blocks

    payload: dict[str, Any] = {
        "schema_version": CV_EXTRACTION_V2_CONTRACT,
        "professional_summary": None,
        "contact_details": {},
        "employment": [],
        "volunteer_work": [],
        "education": [],
        "skills": [],
        "languages": [],
        "projects": [],
        "publications": [],
        "certifications": [],
        "training_courses": [],
        "memberships_activities": [],
        "awards_honors": [],
        "references": [],
        "availability": None,
        "unmodeled_sections": [],
    }

    header_lines: list[str] = []
    for block in segmented:
        section = block.get("section") or "unmodeled"
        lines = list(block.get("lines") or [])
        heading = block.get("original_heading")
        order = block.get("document_order")
        lang = block.get("language")

        if section == "header":
            header_lines.extend(lines)
            # Inline languages / courses in header-like rows.
            for line in lines:
                m = re.search(r"languages?\s*:\s*(.+)$", line, re.I)
                if m:
                    for part in re.split(r"[,/|]| and ", m.group(1)):
                        name = part.strip(" .;")
                        if name:
                            payload["languages"].append({"language": name, "proficiency": None})
            continue

        if section == "professional_summary":
            payload["professional_summary"] = " ".join(lines)[:2000] or None
        elif section == "employment":
            payload["employment"].extend(_parse_employment(lines))
        elif section == "volunteer_work":
            for role in _parse_employment(lines):
                payload["volunteer_work"].append(
                    {
                        "role": role.get("title"),
                        "organization": role.get("company"),
                        "location": role.get("location"),
                        "start_date": role.get("start_date"),
                        "end_date": role.get("end_date"),
                        "description": role.get("description"),
                        "achievements": role.get("achievements") or [],
                        "source_evidence": role.get("source_evidence"),
                    }
                )
        elif section == "education":
            payload["education"].extend(_parse_education(lines))
        elif section == "skills":
            for item in _split_items(lines, split_commas=True):
                if _SKILL_CONTAMINATION.search(item):
                    payload["unmodeled_sections"].append(
                        {
                            "original_heading": heading or "skills",
                            "items": [item],
                            "content": item,
                            "language": lang,
                            "document_order": order,
                            "reason": "likely_misclassified_skill",
                            "source_evidence": {"quote": item[:240]},
                        }
                    )
                    continue
                payload["skills"].append({"name": item, "category": None, "source_evidence": {"quote": item[:240]}})
        elif section == "languages":
            for item in _split_items(lines, split_commas=True):
                # "Arabic — Native" / "English: Fluent"
                parts = re.split(r"[–—\-:/]| native| fluent", item, maxsplit=1, flags=re.I)
                language = parts[0].strip() if parts else item
                proficiency = None
                m = re.search(r"(Native|Fluent|Intermediate|Basic|مبتدئ|متوسط|طلاقة|لغة أم)", item, re.I)
                if m:
                    proficiency = m.group(1)
                if language:
                    payload["languages"].append({"language": language, "proficiency": proficiency})
        elif section == "projects":
            payload["projects"].extend(_parse_named_list(lines, "name"))
        elif section == "publications":
            for item in _parse_named_list(lines, "title"):
                payload["publications"].append(item)
        elif section == "certifications":
            payload["certifications"].extend(_parse_named_list(lines, "name"))
        elif section == "training_courses":
            # Keep inline "Online Courses: X" content.
            expanded: list[str] = []
            for line in lines:
                m = re.search(r"(?:online\s+)?courses?\s*:\s*(.+)$", line, re.I)
                if m:
                    expanded.extend(p.strip() for p in re.split(r"[,;|]", m.group(1)) if p.strip())
                else:
                    expanded.append(line)
            payload["training_courses"].extend(_parse_named_list(expanded, "name"))
        elif section == "memberships_activities":
            payload["memberships_activities"].extend(_parse_named_list(lines, "name"))
        elif section == "awards_honors":
            for item in _split_items(lines):
                payload["awards_honors"].append(
                    {
                        "title": item,
                        "issuing_organization": None,
                        "date": _parse_dates(item)[0],
                        "description": None,
                        "source_evidence": {"quote": item[:240]},
                    }
                )
        elif section == "references":
            payload["references"].extend(_parse_named_list(lines, "name"))
        else:
            # Capture inline course rows that landed in unmodeled/header-adjacent blocks.
            course_inline = False
            for line in lines:
                m = re.search(r"(?:online\s+)?courses?\s*:\s*(.+)$", line, re.I)
                if m:
                    course_inline = True
                    for part in re.split(r"[,;|]", m.group(1)):
                        name = part.strip()
                        if name:
                            payload["training_courses"].append(
                                {"name": name, "source_evidence": {"quote": line[:240]}}
                            )
            if course_inline:
                continue
            payload["unmodeled_sections"].append(
                {
                    "original_heading": heading,
                    "items": lines,
                    "content": "\n".join(lines),
                    "language": lang,
                    "document_order": order,
                    "reason": "unknown_or_ambiguous_section",
                    "source_evidence": {"quote": (lines[0][:240] if lines else None), "order": order},
                }
            )

    # Inline languages anywhere if still empty.
    if not payload["languages"]:
        m = re.search(r"languages?\s*:\s*([^\n]+)", text, re.I)
        if m:
            for part in re.split(r"[,/|]| and ", m.group(1)):
                name = part.strip(" .;")
                if name:
                    payload["languages"].append({"language": name, "proficiency": None})

    payload["contact_details"] = _contact_details(text, header_lines)

    # Header prose as summary when no summary section.
    if not payload["professional_summary"] and header_lines:
        prose = [ln for ln in header_lines if len(ln) > 60 and not _EMAIL_RE.search(ln)]
        if prose:
            payload["professional_summary"] = " ".join(prose[:3])[:2000]

    return payload


__all__ = [
    "INTERNAL_EXTRACTOR_VERSION",
    "classify_heading",
    "extract_internal_v2",
    "segment_blocks",
]
