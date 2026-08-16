"""Human-facing presentation for committed Ranking results.

This module is deliberately downstream of ``candidate_ranking``. It translates
canonical values for HR surfaces without recalculating, mutating, or persisting
Ranking authority.
"""

from __future__ import annotations

import copy
import re
from collections import Counter
from typing import Any


PRESENTATION_VERSION = "ranking-result-presentation-v2"
MISSING_REASON_MAPPING_VERSION = "ranking-missing-reasons-v1"
COVERAGE_LABEL_VERSION = "ranking-evidence-coverage-v1"
SCORE_DISPLAY_VERSION = "ranking-score-display-v1"
NARRATIVE_PROMPT_VERSION = "ranking-terra-brief-v2"
TIE_SCORE_DELTA = 2.0

STRONG_COVERAGE_MIN = 0.80
MODERATE_COVERAGE_MIN = 0.50
NUMERIC_SCORE_MIN_COVERAGE = 0.75

_STATE_ALIASES = {
    "eligible": "eligible",
    "met": "eligible",
    "requirement_not_met": "not_met",
    "not_met": "not_met",
    "insufficient_information": "unknown",
    "unknown": "unknown",
    "criteria_not_evaluated": "criteria_not_evaluated",
    "not_applicable": "not_applicable",
}

_COPY = {
    "en": {
        "states": {
            "eligible": "Meets the configured requirements",
            "not_met": "Does not meet one or more required criteria",
            "unknown": "Some required information is still unverified",
            "criteria_not_evaluated": "Ranking incomplete",
            "not_applicable": "Requirements not configured",
        },
        "score_unavailable": "Score unavailable",
        "not_enough_evidence": "Not enough evidence",
        "ranking_incomplete": "Ranking incomplete",
        "setup_needed": "Set job criteria first",
        "coverage": {
            "strong": "Strong evidence coverage",
            "moderate": "Moderate evidence coverage",
            "limited": "Limited evidence coverage",
        },
        "component_values": {
            "strong": "Strong match",
            "partial": "Partial match",
            "not_verified": "Not verified",
            "unavailable": "Unavailable",
            "no_approved_evidence": "No approved evidence",
        },
        "hr_decides": "HR makes the final decision.",
        "missing_heading": "Watch outs",
        "strengths_heading": "What the CV confirms",
        "next_step": "Recommended next step",
        "questions_heading": "Suggested interview questions",
        "matching_heading": "Matching on",
        "technical": "View technical details",
        "optional_omitted": "Optional evidence omitted",
        "close_match": "Close match",
        "no_clear_winner": "No clear winner yet",
        "thin_evidence": "Not enough to choose",
        "fit": {
            "top": "Promising match",
            "strong": "Strong contender",
            "worth": "Worth reviewing",
            "careful": "Review carefully",
            "blocked": "Needs evidence",
            "not_met": "Requirement not met",
            "tied": "Too close to call",
            "thin": "Not enough to choose",
            "setup": "Setup needed",
        },
        "confidence": {
            "high": "High confidence",
            "medium": "Medium confidence",
            "low": "Low confidence",
        },
    },
    "ar": {
        "states": {
            "eligible": "يستوفي المتطلبات المحددة",
            "not_met": "لا يستوفي متطلباً إلزامياً واحداً أو أكثر",
            "unknown": "بعض المعلومات المطلوبة لم يتم التحقق منها بعد",
            "criteria_not_evaluated": "الترتيب غير مكتمل",
            "not_applicable": "المتطلبات غير مُعدّة",
        },
        "score_unavailable": "الدرجة غير متاحة",
        "not_enough_evidence": "لا توجد أدلة كافية",
        "ranking_incomplete": "الترتيب غير مكتمل",
        "setup_needed": "أعدّ معايير الوظيفة أولاً",
        "coverage": {
            "strong": "تغطية الأدلة قوية",
            "moderate": "تغطية الأدلة متوسطة",
            "limited": "تغطية الأدلة محدودة",
        },
        "component_values": {
            "strong": "توافق قوي",
            "partial": "توافق جزئي",
            "not_verified": "لم يتم التحقق",
            "unavailable": "غير متاح",
            "no_approved_evidence": "لا توجد أدلة معتمدة",
        },
        "hr_decides": "القرار النهائي للموارد البشرية.",
        "missing_heading": "نقاط يجب الانتباه لها",
        "strengths_heading": "ما تؤكده السيرة الذاتية",
        "next_step": "الخطوة التالية المقترحة",
        "questions_heading": "أسئلة مقابلة مقترحة",
        "matching_heading": "نقارن على أساس",
        "technical": "عرض التفاصيل التقنية",
        "optional_omitted": "أدلة اختيارية غير مستخدمة",
        "close_match": "تعادل تقريبي",
        "no_clear_winner": "لا يوجد فائز واضح بعد",
        "thin_evidence": "الأدلة غير كافية للاختيار",
        "fit": {
            "top": "توافق واعد",
            "strong": "مرشح قوي",
            "worth": "يستحق المراجعة",
            "careful": "راجع بعناية",
            "blocked": "يحتاج إلى أدلة",
            "not_met": "متطلب غير مستوفى",
            "tied": "الفرق ضئيل جداً",
            "thin": "الأدلة غير كافية للاختيار",
            "setup": "الإعداد مطلوب",
        },
        "confidence": {
            "high": "ثقة عالية",
            "medium": "ثقة متوسطة",
            "low": "ثقة منخفضة",
        },
    },
}

_SKILL_STOPWORDS = {
    "with", "and", "the", "for", "years", "year", "experience", "background",
    "role", "job", "work", "working", "skills", "skill", "using", "from",
    "this", "that", "have", "has", "had", "also", "plus", "etc", "ability",
}

_MISSING_REASON_COPY = {
    "assessment_not_employer_approved_for_ranking": {
        "en": "No employer-approved assessment is available for this Ranking",
        "ar": "لا يوجد تقييم معتمد من جهة العمل لهذا الترتيب",
    },
    "assessment_missing": {
        "en": "Optional assessment evidence was not included",
        "ar": "لم تُدرج أدلة التقييم الاختيارية",
    },
    "assessment_unused_by_policy": {
        "en": "Assessment evidence is not used for this job",
        "ar": "أدلة التقييم غير مستخدمة لهذه الوظيفة",
    },
    "assessment_not_selected_by_policy": {
        "en": "This assessment result is not the employer-selected Ranking evidence",
        "ar": "نتيجة التقييم هذه ليست دليل الترتيب الذي اختارته جهة العمل",
    },
    "semantic_similarity_unavailable": {
        "en": "Optional CV similarity evidence was not included",
        "ar": "لم تُدرج أدلة تشابه السيرة الذاتية الاختيارية",
    },
    "required_cv_unavailable": {
        "en": "A usable CV is required before Ranking can compare this candidate",
        "ar": "يلزم توفر سيرة ذاتية صالحة قبل مقارنة هذا المرشح",
    },
    "required_assessment_missing": {
        "en": "An approved assessment is required for this job’s Ranking",
        "ar": "يلزم تقييم معتمد لترتيب هذه الوظيفة",
    },
    "required_semantic_unavailable": {
        "en": "Required CV similarity evidence is unavailable",
        "ar": "أدلة تشابه السيرة الذاتية المطلوبة غير متاحة",
    },
    "required_screening_incomplete": {
        "en": "Required screening is incomplete",
        "ar": "الفحص الأولي المطلوب غير مكتمل",
    },
    "criteria_not_evaluated": {
        "en": "The job’s Ranking criteria have not been evaluated",
        "ar": "لم يتم تقييم معايير الترتيب الخاصة بالوظيفة",
    },
    "criteria_not_configured": {
        "en": "Requirements are not configured for this job",
        "ar": "المتطلبات غير مُعدّة لهذه الوظيفة",
    },
    "cv_extraction_missing": {
        "en": "The candidate’s current CV has not been fully processed",
        "ar": "لم تتم معالجة السيرة الذاتية الحالية للمرشح بالكامل",
    },
    "cv_extraction_failed": {
        "en": "The candidate’s current CV has not been fully processed",
        "ar": "لم تتم معالجة السيرة الذاتية الحالية للمرشح بالكامل",
    },
    "cv_processing_incomplete": {
        "en": "The candidate’s current CV has not been fully processed",
        "ar": "لم تتم معالجة السيرة الذاتية الحالية للمرشح بالكامل",
    },
    "cv_file_missing": {
        "en": "The candidate’s current CV file is unavailable",
        "ar": "ملف السيرة الذاتية الحالي للمرشح غير متاح",
    },
    "cv_semantic_projection_stale": {
        "en": "The candidate’s current CV needs to be processed again",
        "ar": "تحتاج السيرة الذاتية الحالية للمرشح إلى إعادة المعالجة",
    },
    "cv_evidence_contract_stale": {
        "en": "The candidate’s current CV needs to be processed again",
        "ar": "تحتاج السيرة الذاتية الحالية للمرشح إلى إعادة المعالجة",
    },
    "missing_hard_requirement_evidence": {
        "en": "A required fact could not be verified",
        "ar": "تعذر التحقق من معلومة مطلوبة",
    },
    "required_fact_unverified": {
        "en": "A required fact could not be verified",
        "ar": "تعذر التحقق من معلومة مطلوبة",
    },
}

_COMPONENTS = {
    "skills_alignment": ("Skills match", "توافق المهارات", 30.0),
    "experience_alignment": ("Relevant experience", "الخبرة ذات الصلة", 25.0),
    "education_cert_alignment": ("Education and certifications", "التعليم والشهادات", 15.0),
    "assessment_evidence": ("Assessment evidence", "أدلة التقييم", 15.0),
    "semantic_alignment": ("CV-based semantic evidence", "أدلة السيرة الذاتية", 15.0),
}

_UNAVAILABLE_REASONS = {
    "assessment_not_employer_approved_for_ranking",
    "required_cv_unavailable",
    "required_assessment_missing",
    "required_semantic_unavailable",
    "required_screening_incomplete",
    "cv_extraction_missing",
    "cv_extraction_failed",
    "cv_processing_incomplete",
    "cv_file_missing",
    "cv_semantic_projection_stale",
    "cv_evidence_contract_stale",
}

_OPTIONAL_MISSING_REASONS = {
    "assessment_missing",
    "assessment_failed",
    "assessment_cancelled",
    "assessment_expired",
    "assessment_in_progress",
    "assessment_pending",
    "assessment_unrelated_to_job",
    "assessment_percent_unusable",
    "assessment_not_selected_by_policy",
    "semantic_similarity_unavailable",
    "cv_unavailable",
    "screening_incomplete",
}

_CRITERIA_REASONS = {"criteria_not_evaluated", "criteria_not_configured"}

_RAW_TECHNICAL_PATTERN = re.compile(
    r"(?:Eligibility=|coverage=|components\[|advisory=|"
    r"assessment_not_employer_approved_for_ranking|semantic_similarity_unavailable|"
    r"criteria_not_evaluated|cv_extraction_|cv_evidence_|semantic_content_hash|"
    r"run_id|item_id|prompt_version|evidence_hash|embedding_model|"
    r"alignment:\s*\d|similarity:\s*0\.|evidence coverage|confidence is medium|"
    r"https?://|```|[{}\[\]]|\b0\.\d{2,}\b)",
    re.IGNORECASE,
)

_TERRA_MAX_CHARS = 420
_TERRA_MAX_SENTENCES = 4


def normalize_locale(locale: str | None) -> str:
    return "ar" if str(locale or "").lower().startswith("ar") else "en"


def canonical_state(value: Any) -> str:
    return _STATE_ALIASES.get(str(value or "").strip().lower(), "unknown")


def state_label(value: Any, *, locale: str = "en") -> str:
    lang = normalize_locale(locale)
    return _COPY[lang]["states"][canonical_state(value)]


def missing_reason_label(reason: Any, *, locale: str = "en") -> str:
    lang = normalize_locale(locale)
    code = str(reason or "").strip().lower()
    mapped = _MISSING_REASON_COPY.get(code)
    if mapped:
        return mapped[lang]
    if any(token in code for token in ("cv_extract", "cv_processing", "cv_parse")):
        return _MISSING_REASON_COPY["cv_extraction_missing"][lang]
    if any(token in code for token in ("hard_requirement", "required_fact", "required_evidence")):
        return _MISSING_REASON_COPY["missing_hard_requirement_evidence"][lang]
    return (
        "Additional evidence needs verification"
        if lang == "en"
        else "توجد أدلة إضافية تحتاج إلى التحقق"
    )


def coverage_presentation(value: Any, *, locale: str = "en") -> dict[str, Any]:
    lang = normalize_locale(locale)
    try:
        exact = max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        exact = 0.0
    level = "strong" if exact >= STRONG_COVERAGE_MIN else "moderate" if exact >= MODERATE_COVERAGE_MIN else "limited"
    return {
        "version": COVERAGE_LABEL_VERSION,
        "level": level,
        "label": _COPY[lang]["coverage"][level],
        "percentage": round(exact * 100),
    }


def _missing_codes(item: dict[str, Any]) -> list[str]:
    values = item.get("missing_data")
    if not isinstance(values, list):
        values = item.get("missing_evidence")
    return [str(value).strip() for value in (values or []) if str(value).strip()]


def _assessment_contribution_active(item: dict[str, Any]) -> bool:
    """True only when Ranking actually consumes approved assessment evidence."""
    provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
    mode = str(provenance.get("assessment_mode") or item.get("assessment_mode") or "").strip().lower()
    if mode == "unused":
        return False
    unused = {
        str(value).strip().lower()
        for value in [
            *(item.get("unused_omitted") or []),
            *(provenance.get("unused_omitted") or []),
            *(item.get("missing_data") or []),
        ]
        if str(value).strip()
    }
    if "assessment_unused_by_policy" in unused:
        return False
    kind = str(provenance.get("ranking_result_kind") or item.get("ranking_result_kind") or "").strip()
    if kind == "cv_plus_approved_assessment":
        return True
    components = item.get("component_scores") if isinstance(item.get("component_scores"), dict) else {}
    if "assessment_evidence" in components:
        return True
    if kind == "cv_based":
        return False
    # Legacy committed rows without the new provenance fields keep prior wording.
    return True


def _display_missing_codes(item: dict[str, Any], codes: list[str] | None = None) -> list[str]:
    """Omit assessment-needed codes when assessment is unused for Ranking."""
    raw = list(codes) if codes is not None else _missing_codes(item)
    if _assessment_contribution_active(item):
        return [
            code
            for code in raw
            if str(code).strip().lower() not in {"assessment_unused_by_policy"}
        ]
    return [
        code
        for code in raw
        if not str(code).strip().lower().startswith("assessment_")
        and str(code).strip().lower() != "required_assessment_missing"
    ]


def _job_label(item: dict[str, Any], *, run: dict[str, Any] | None = None, locale: str = "en") -> str:
    run_data = run if isinstance(run, dict) else {}
    raw = str(
        item.get("position_title")
        or (item.get("display") or {}).get("position_title")
        or run_data.get("position_title")
        or item.get("position_code")
        or run_data.get("position_code")
        or ""
    ).strip()
    if not raw:
        return "هذه الوظيفة" if normalize_locale(locale) == "ar" else "this role"
    if normalize_locale(locale) == "en":
        # Keep short role codes readable: HR, IT, etc.
        if len(raw) <= 3 and raw.isalpha():
            return raw.upper()
        return raw.title() if raw.isupper() or raw.islower() else raw
    return raw


def _evidence_signals(item: dict[str, Any], *, locale: str = "en") -> dict[str, Any]:
    """Classify whether verified evidence is strong enough for a meaningful ranking score."""
    lang = normalize_locale(locale)
    skills: list[str] = []
    education: list[str] = []
    employment: list[dict[str, Any]] = []
    has_experience = False
    experience_years: float | None = None
    assessment_percent: float | None = None
    for evidence in list(item.get("evidence") or []):
        if not isinstance(evidence, dict):
            continue
        field = str(evidence.get("field") or "").strip().lower()
        source = str(evidence.get("source") or "").strip().lower()
        value = evidence.get("value")
        if field in {"skills", "cv_skills"}:
            skills.extend(_clean_skill_values(value if isinstance(value, list) else [value], locale=lang))
        elif field in {"education_cert", "cv_education"}:
            education.extend(_clean_skill_values(value if isinstance(value, list) else [value], locale=lang))
        elif field == "employment" and isinstance(value, list):
            employment.extend(part for part in value if isinstance(part, dict))
            has_experience = bool(employment)
        elif field == "experience_years":
            try:
                experience_years = float(value)
                has_experience = experience_years > 0
            except (TypeError, ValueError):
                pass
        elif field == "percent" and source == "assessment":
            try:
                assessment_percent = float(value)
            except (TypeError, ValueError):
                assessment_percent = None
    provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
    facts_readiness = (
        provenance.get("cv_facts_readiness")
        if isinstance(provenance.get("cv_facts_readiness"), dict)
        else {}
    )
    facts_ready = bool(facts_readiness.get("ready")) or any(
        str(e.get("source") or "") == "application_cv_facts"
        for e in (item.get("evidence") or [])
        if isinstance(e, dict)
    )
    has_skills = bool(skills)
    has_education = bool(education)
    has_assessment = assessment_percent is not None
    # Education alone (or empty) is not enough to pretend we can rank for a role.
    rankable = has_skills or has_experience or has_assessment
    thin = not rankable
    return {
        "thin": thin,
        "rankable": rankable,
        "has_skills": has_skills,
        "has_experience": has_experience,
        "has_education": has_education,
        "has_assessment": has_assessment,
        "facts_ready": facts_ready,
        "facts_status": facts_readiness.get("status") or ("ready" if facts_ready else "missing"),
        "skills": skills[:6],
        "education": education[:4],
        "employment": employment[:4],
        "experience_years": experience_years,
        "assessment_percent": assessment_percent,
    }


def _ranking_basis(item: dict[str, Any]) -> dict[str, Any]:
    direct = item.get("ranking_basis")
    if isinstance(direct, dict):
        return direct
    provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
    basis = provenance.get("ranking_basis")
    return basis if isinstance(basis, dict) else {}


def _numeric_score_presentation(
    item: dict[str, Any],
    *,
    state: str,
    coverage: float,
    stale: bool,
    locale: str,
) -> dict[str, Any]:
    lang = normalize_locale(locale)
    raw_score = item.get("advisory_score", item.get("score"))
    codes = set(_missing_codes(item))
    optional_missing = {
        str(x).strip().lower()
        for x in (item.get("optional_missing") or [])
        if str(x or "").strip()
    } | (codes & _OPTIONAL_MISSING_REASONS)
    required_missing = {
        str(x).strip().lower()
        for x in (item.get("required_missing") or [])
        if str(x or "").strip()
    } | (codes & _UNAVAILABLE_REASONS)
    required_complete = item.get("required_evidence_complete")
    if required_complete is None:
        required_complete = not bool(required_missing)
    try:
        score = float(raw_score)
        score_valid = 0.0 <= score <= 100.0
    except (TypeError, ValueError):
        score = 0.0
        score_valid = False

    signals = _evidence_signals(item, locale=lang)
    basis = _ranking_basis(item)
    # Published requirements or a conservative title profile can support an
    # advisory comparison even before HR customizes advanced criteria.
    criteria_evaluated = state in {"eligible", "not_met"} or (
        state == "not_applicable"
        and basis.get("source") in {"job_requirements", "job_title_profile", "job_title"}
        and bool(basis.get("criteria_count"))
    )
    # ranking-soft-v2: optional missing evidence must not hide the numeric score.
    blocking = set(required_missing)
    unavailable_dominates_zero = score == 0.0 and bool(blocking) and not optional_missing
    # Thin evidence (education-only / no role signal) must not look like a real ranking score.
    thin = bool(signals.get("thin"))
    meaningful = (
        score_valid
        and criteria_evaluated
        and not stale
        and bool(required_complete)
        and not blocking
        and not unavailable_dominates_zero
        and not thin
    )
    if meaningful:
        return {
            "version": SCORE_DISPLAY_VERSION,
            "show_numeric": True,
            "value": raw_score,
            "label": f"{score:g}/100" if lang == "en" else f"{score:g}/100",
            "reason": "meaningful_current_result",
            "confidence": item.get("confidence"),
            "optional_omitted": sorted(optional_missing),
        }
    if not required_complete or blocking:
        label = _COPY[lang]["not_enough_evidence"]
        reason = "required_evidence_incomplete"
    elif state == "not_applicable" and not criteria_evaluated:
        label = _COPY[lang]["setup_needed"]
        reason = "job_criteria_not_configured"
    elif thin:
        label = _COPY[lang]["thin_evidence"]
        reason = "thin_evidence_not_meaningful"
    elif state == "criteria_not_evaluated":
        label = _COPY[lang]["ranking_incomplete"]
        reason = "criteria_not_evaluated"
    else:
        label = _COPY[lang]["score_unavailable"]
        reason = "score_not_meaningful"
    return {
        "version": SCORE_DISPLAY_VERSION,
        "show_numeric": False,
        "value": None,
        "label": label,
        "reason": reason,
        "confidence": item.get("confidence"),
        "optional_omitted": sorted(optional_missing),
    }


def _component_presentation(item: dict[str, Any], *, locale: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    lang = normalize_locale(locale)
    raw = item.get("component_scores")
    if not isinstance(raw, dict):
        raw = item.get("score_breakdown")
    components = raw if isinstance(raw, dict) else {}
    missing = set(_missing_codes(item))
    strengths: list[dict[str, str]] = []
    evidence_sections: list[dict[str, str]] = []
    for key, (label_en, label_ar, maximum) in _COMPONENTS.items():
        if key not in components:
            continue
        try:
            value = float(components.get(key) or 0.0)
        except (TypeError, ValueError):
            continue
        label = label_ar if lang == "ar" else label_en
        ratio = value / maximum if maximum else 0.0
        if ratio >= 0.67:
            status = "strong"
        elif value > 0:
            status = "partial"
        elif key == "assessment_evidence" and "assessment_not_employer_approved_for_ranking" in missing:
            status = "no_approved_evidence"
        elif key == "semantic_alignment" and missing & {
            "semantic_similarity_unavailable",
            "cv_extraction_missing",
            "cv_extraction_failed",
            "cv_processing_incomplete",
        }:
            status = "unavailable"
        else:
            status = "not_verified"
        section = {"label": label, "value": _COPY[lang]["component_values"][status], "status": status}
        evidence_sections.append(section)
        if status in {"strong", "partial"}:
            strengths.append(section)
    return strengths[:3], evidence_sections


def _evidence_highlights(item: dict[str, Any], *, locale: str) -> list[dict[str, str]]:
    """Translate bounded committed evidence into useful, non-technical HR facts."""
    lang = normalize_locale(locale)
    highlights: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    labels = {
        "skills": ("CV skills", "مهارات من السيرة الذاتية"),
        "experience_years": ("Relevant experience", "الخبرة ذات الصلة"),
        "education_cert": ("Education and certifications", "التعليم والشهادات"),
        "assessment": ("Approved assessment", "التقييم المعتمد"),
    }
    for evidence in list(item.get("evidence") or [])[:12]:
        if not isinstance(evidence, dict):
            continue
        field = str(evidence.get("field") or "").strip().lower()
        source = str(evidence.get("source") or "").strip().lower()
        value = evidence.get("value")
        label_key = field
        if source == "assessment" and field == "percent":
            label_key = "assessment"
            try:
                rendered = f"{round(float(value))}%"
            except (TypeError, ValueError):
                continue
        elif field == "experience_years":
            try:
                years = float(value)
                rendered = (
                    f"{years:g} سنة خبرة"
                    if lang == "ar"
                    else f"{years:g} years"
                )
            except (TypeError, ValueError):
                continue
        elif field in {"skills", "education_cert"}:
            values = value if isinstance(value, list) else [value]
            clean = _clean_skill_values(values[:6], locale=lang)
            if not clean:
                continue
            rendered = ", ".join(clean)[:120]
        else:
            # Similarity values and internal scoring evidence are intentionally
            # excluded; they are not meaningful source facts for HR.
            continue
        label_pair = labels.get(label_key)
        if not label_pair:
            continue
        label = label_pair[1] if lang == "ar" else label_pair[0]
        key = (label, rendered.lower())
        if key in seen:
            continue
        seen.add(key)
        highlights.append({"label": label, "value": rendered, "source": "verified"})
    return highlights[:4]


def _title_case_name(value: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return text
    if text.isupper() or text.islower():
        return text.title()
    return text


def _pretty_token(value: Any, *, locale: str = "en") -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if normalize_locale(locale) == "en" and text.islower():
        return text[:1].upper() + text[1:]
    return text


def _clean_skill_values(values: list[Any], *, locale: str = "en") -> list[str]:
    clean: list[str] = []
    seen: set[str] = set()
    for part in values:
        token = str(part or "").strip()
        if not token:
            continue
        key = token.lower()
        if key in _SKILL_STOPWORDS or key in seen:
            continue
        seen.add(key)
        clean.append(_pretty_token(token, locale=locale))
    return clean


def _fit_presentation(
    *,
    score_visible: bool,
    score: Any,
    state: str,
    tied: bool,
    locale: str,
) -> dict[str, str]:
    lang = normalize_locale(locale)
    labels = _COPY[lang]["fit"]
    if not score_visible:
        return {"code": "blocked", "label": labels["blocked"], "tone": "warning"}
    if state == "not_met":
        return {"code": "not_met", "label": labels["not_met"], "tone": "danger"}
    if tied:
        return {"code": "tied", "label": labels["tied"], "tone": "neutral"}
    try:
        value = float(score or 0)
    except (TypeError, ValueError):
        value = 0.0
    if value >= 85:
        return {"code": "top", "label": labels["top"], "tone": "success"}
    if value >= 70:
        return {"code": "strong", "label": labels["strong"], "tone": "success"}
    if value >= 55:
        return {"code": "worth", "label": labels["worth"], "tone": "neutral"}
    return {"code": "careful", "label": labels["careful"], "tone": "warning"}


def _matching_on(item: dict[str, Any], *, locale: str, run: dict[str, Any] | None = None) -> list[str]:
    lang = normalize_locale(locale)
    run_data = run if isinstance(run, dict) else {}
    job_title = str(
        item.get("position_title")
        or (item.get("display") or {}).get("position_title")
        or run_data.get("position_title")
        or item.get("position_code")
        or run_data.get("position_code")
        or ""
    ).strip()
    chips: list[str] = []
    if job_title:
        chips.append(job_title if lang == "ar" else job_title.title())
    for evidence in list(item.get("evidence") or [])[:8]:
        if not isinstance(evidence, dict):
            continue
        field = str(evidence.get("field") or "").strip().lower()
        if field == "skills":
            chips.extend(_clean_skill_values(list(evidence.get("value") or [])[:4], locale=lang))
        elif field == "education_cert":
            chips.append("Education" if lang == "en" else "التعليم")
        elif field == "experience_years":
            chips.append("Relevant experience" if lang == "en" else "الخبرة")
        elif field == "percent" and str(evidence.get("source") or "") == "assessment":
            chips.append("Assessment" if lang == "en" else "التقييم")
    # Keep unique, short chips.
    out: list[str] = []
    seen: set[str] = set()
    for chip in chips:
        key = chip.lower()
        if not chip or key in seen:
            continue
        seen.add(key)
        out.append(chip)
    return out[:6]


def _interview_questions(item: dict[str, Any], *, locale: str, matching_on: list[str]) -> list[str]:
    lang = normalize_locale(locale)
    job = matching_on[0] if matching_on else ("this role" if lang == "en" else "هذه الوظيفة")
    skills = [c for c in matching_on[1:] if c.lower() not in {"education", "assessment", "relevant experience", "التعليم", "التقييم", "الخبرة"}][:2]
    skill_hint = skills[0] if skills else ("the core skills" if lang == "en" else "المهارات الأساسية")
    if lang == "ar":
        return [
            f"حدثني عن خبرتك العملية الأقرب لوظيفة {job}.",
            f"كيف استخدمت {skill_hint} في عملك اليومي؟",
            "ما التحدي المهني الأهم الذي تعاملت معه مؤخراً؟",
        ]
    return [
        f"Walk me through your most relevant experience for {job}.",
        f"How have you used {skill_hint} in day-to-day work?",
        "What recent challenge best shows how you work under pressure?",
    ]


def _terra_brief(item: dict[str, Any]) -> dict[str, Any] | None:
    terra = item.get("terra_narrative") if isinstance(item.get("terra_narrative"), dict) else {}
    brief = terra.get("brief") if isinstance(terra.get("brief"), dict) else None
    if not brief:
        return None
    evidence_hash = str(item.get("evidence_hash") or "")
    exact_hash = bool(evidence_hash) and str(terra.get("evidence_hash") or "") == evidence_hash
    if not exact_hash or terra.get("canonical") is False:
        return None
    if str(terra.get("status") or "") != "completed":
        return None
    if str(terra.get("prompt_version") or "") not in {NARRATIVE_PROMPT_VERSION, "ranking-terra-brief-v2"}:
        return None
    return brief


def _clean_string_list(value: Any, *, limit: int = 5) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for part in value:
        text = str(part or "").strip()
        if not text or _RAW_TECHNICAL_PATTERN.search(text):
            continue
        # Drop score-ish fragments that are not useful to HR.
        if re.search(r"\b\d+\.\d+\b", text) and re.search(r"alignment|similarity|coverage|score", text, re.I):
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _dedupe_why(lines: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        text = str(line or "").strip()
        if not text:
            continue
        key = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", text.lower()).strip()
        # Collapse bachelor/degree duplicates into one education fact.
        if any(token in key for token in ("bachelor", "degree", "بكالوريوس", "شهادة")):
            key = "education_bachelor"
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _human_why_facts(signals: dict[str, Any], *, locale: str) -> list[str]:
    lang = normalize_locale(locale)
    why: list[str] = []
    if signals.get("skills"):
        joined = ", ".join(signals["skills"][:4])
        why.append(
            f"CV skills include {joined}"
            if lang == "en"
            else f"مهارات السيرة الذاتية تشمل {joined}"
        )
    if signals.get("has_experience"):
        years = signals.get("experience_years")
        if years is not None:
            why.append(
                f"Relevant experience: {years:g} years"
                if lang == "en"
                else f"خبرة ذات صلة: {years:g} سنة"
            )
        elif signals.get("employment"):
            first = signals["employment"][0]
            role = str(first.get("role") or "").strip() or ("Experience section" if lang == "en" else "قسم الخبرة")
            academic = str(first.get("experience_type") or "") == "academic_or_simulated"
            if lang == "en":
                why.append(
                    f"Academic/simulated experience on the CV: {role}"
                    if academic
                    else f"Experience on the CV: {role}"
                )
            else:
                why.append(
                    f"خبرة أكاديمية/محاكاة في السيرة الذاتية: {role}"
                    if academic
                    else f"خبرة في السيرة الذاتية: {role}"
                )
    if signals.get("has_education"):
        education_values: list[str] = []
        for raw in signals.get("education") or []:
            cleaned = re.split(
                r"relevant coursework\s*:",
                str(raw),
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-")
            if cleaned and cleaned.lower() not in {value.lower() for value in education_values}:
                education_values.append(cleaned)
        edu = next(
            (value for value in education_values if len(value.split()) > 1),
            education_values[0] if education_values else ("Bachelor's degree" if lang == "en" else "بكالوريوس"),
        )
        why.append(
            f"Education on CV: {edu}"
            if lang == "en"
            else f"التعليم في السيرة الذاتية: {edu}"
        )
    if signals.get("assessment_percent") is not None:
        pct = round(float(signals["assessment_percent"]))
        why.append(
            f"Approved assessment score: {pct}%"
            if lang == "en"
            else f"درجة التقييم المعتمد: {pct}%"
        )
    return _dedupe_why(why)[:4]


def _role_gaps(signals: dict[str, Any], *, job: str, codes: list[str], locale: str) -> list[str]:
    lang = normalize_locale(locale)
    gaps: list[str] = []
    role = job or ("this role" if lang == "en" else "هذه الوظيفة")
    if not signals.get("facts_ready"):
        gaps.append(
            "Structured CV facts are not ready yet; do not infer missing skills or experience."
            if lang == "en"
            else "حقائق السيرة الذاتية المنظمة غير جاهزة بعد؛ لا تستنتج غياب المهارات أو الخبرة."
        )
    else:
        if not signals.get("has_skills"):
            gaps.append(
                f"The current facts extraction did not identify skills to compare with {role}"
                if lang == "en"
                else f"لم يحدد استخراج الحقائق الحالي مهارات لمقارنتها بوظيفة {role}"
            )
        if not signals.get("has_experience"):
            gaps.append(
                "The current facts extraction did not identify employment details"
                if lang == "en"
                else "لم يحدد استخراج الحقائق الحالي تفاصيل خبرة وظيفية"
            )
        elif signals.get("employment") and all(
            str(item.get("experience_type") or "") == "academic_or_simulated"
            for item in signals["employment"]
        ):
            gaps.append(
                "The experience shown is academic or simulated rather than professional employment"
                if lang == "en"
                else "الخبرة المعروضة أكاديمية أو محاكاة وليست خبرة وظيفية مهنية"
            )
    code_set = {str(c).lower() for c in codes}
    if any(c.startswith("assessment_") for c in code_set):
        if "assessment_unused_by_policy" in code_set:
            pass
        elif "assessment_expired" in code_set:
            gaps.append("Assessment is expired" if lang == "en" else "التقييم منتهٍ")
        elif "assessment_missing" in code_set:
            gaps.append("No assessment result yet" if lang == "en" else "لا توجد نتيجة تقييم بعد")
        elif "assessment_not_selected_by_policy" in code_set:
            gaps.append(missing_reason_label("assessment_not_selected_by_policy", locale=lang))
        else:
            gaps.append(missing_reason_label(next(c for c in codes if str(c).lower().startswith("assessment_")), locale=lang))
    return _dedupe_why(gaps)[:4]


def _because_phrase(why: list[str], *, locale: str) -> str:
    lang = normalize_locale(locale)
    clean = [re.sub(r"^(CV skills include|Education on CV:|Approved assessment score:|مهارات السيرة الذاتية تشمل|التعليم في السيرة الذاتية:|درجة التقييم المعتمد:)\s*", "", w, flags=re.I).strip() for w in why]
    clean = [c for c in clean if c]
    if not clean:
        return ""
    if lang == "ar":
        if len(clean) == 1:
            return clean[0]
        if len(clean) == 2:
            return f"{clean[0]} و{clean[1]}"
        return "، ".join(clean[:-1]) + f"، و{clean[-1]}"
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1]}"
    return ", ".join(clean[:-1]) + f", and {clean[-1]}"


def _build_ranking_brief(
    item: dict[str, Any],
    *,
    locale: str,
    state: str,
    score_visible: bool,
    score: Any,
    codes: list[str],
    stale: bool,
    run: dict[str, Any] | None = None,
    tied: bool = False,
) -> dict[str, Any]:
    """Honest HR brief: because-XYZ when earned, otherwise no clear winner / not enough."""
    lang = normalize_locale(locale)
    display = item.get("display") if isinstance(item.get("display"), dict) else {}
    name = _title_case_name(str(item.get("name") or display.get("name") or ("Candidate" if lang == "en" else "مرشح")))
    job = _job_label(item, run=run, locale=lang)
    signals = _evidence_signals(item, locale=lang)
    thin = bool(signals.get("thin"))
    basis = _ranking_basis(item)
    automatic_comparison = basis.get("source") in {
        "job_requirements",
        "job_title_profile",
        "job_title",
    } and bool(basis.get("criteria_count"))
    needs_setup = state == "not_applicable" and not automatic_comparison
    terra = _terra_brief(item)
    terra_for_copy = terra if score_visible and signals.get("facts_ready") and not thin else None

    why = _human_why_facts(signals, locale=lang)
    # Terra may rephrase accepted rankable facts, but is never an evidence authority.
    for line in _clean_string_list((terra_for_copy or {}).get("why"), limit=4):
        lower = line.lower()
        if "eligibility" in lower or "not applicable" in lower:
            continue
        if any(token in lower for token in ("alignment", "coverage", "confidence", "semantic")):
            continue
        if line not in why:
            why.append(line)
    why = _dedupe_why(why)[:4]

    provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
    optional_codes = {
        str(value).lower()
        for value in [
            *(item.get("optional_missing") or []),
            *(provenance.get("optional_missing") or []),
        ]
    }
    assessment_active = _assessment_contribution_active(item)
    display_codes = _display_missing_codes(item, codes)
    display_codes = [code for code in display_codes if not score_visible or str(code).lower() not in optional_codes]
    gaps = _role_gaps(signals, job=job, codes=display_codes, locale=lang)
    # Gaps are deterministic; free-form Terra gaps can create unsupported negatives.
    if needs_setup:
        gaps.append(
            "Job criteria are not configured, so no reliable ranking has been produced."
            if lang == "en"
            else "معايير الوظيفة غير مُعدّة، لذلك لم يتم إنتاج ترتيب موثوق."
        )
    gaps = _dedupe_why(gaps)[:4]

    matching = [
        m for m in _clean_string_list((terra_for_copy or {}).get("matching_on"), limit=6)
        if "alignment" not in m.lower()
        and "confidence" not in m.lower()
        and "semantic" not in m.lower()
        and "eligibility" not in m.lower()
    ]
    if len(matching) < 2:
        matching = []
        if signals.get("skills"):
            matching.extend(signals["skills"][:3])
        if signals.get("has_education"):
            matching.append("Education" if lang == "en" else "التعليم")
        if signals.get("has_assessment"):
            matching.append("Assessment" if lang == "en" else "التقييم")
        if signals.get("has_experience"):
            matching.append("Experience" if lang == "en" else "الخبرة")
        if not matching and job:
            matching = [job]
    # Normalize chips like "Hr" -> "HR"
    normalized_matching: list[str] = []
    for chip in matching:
        text = str(chip).strip()
        if len(text) <= 3 and text.isalpha():
            text = text.upper()
        elif text.lower() == job.lower() and len(job) <= 3:
            text = job.upper() if job.isalpha() else job
        if text and text not in normalized_matching:
            normalized_matching.append(text)
    matching = normalized_matching[:6]

    if thin or not score_visible:
        questions = [
            f"What {job}-related work have you done so far?" if lang == "en" else f"ما العمل المتعلق بوظيفة {job} الذي قمت به حتى الآن؟",
            f"Which {job} tools or processes have you used?" if lang == "en" else f"ما أدوات أو عمليات {job} التي استخدمتها؟",
            "What would you want us to know before we compare candidates?" if lang == "en" else "ما الذي تود أن نعرفه قبل مقارنة المرشحين؟",
        ]
    else:
        questions = _interview_questions(item, locale=lang, matching_on=matching or [job])

    code_set = {str(c).lower() for c in display_codes}
    if needs_setup:
        next_step = (
            f"Set the job criteria for {job}, then recalculate Ranking."
            if lang == "en"
            else f"حدّد معايير وظيفة {job}، ثم أعد حساب الترتيب."
        )
    elif not signals.get("facts_ready"):
        next_step = (
            "Finish structured CV fact processing, then recalculate Ranking."
            if lang == "en"
            else "أكمل معالجة حقائق السيرة الذاتية المنظمة، ثم أعد حساب الترتيب."
        )
    elif automatic_comparison:
        next_step = (
            f"Use the suggested questions to confirm this candidate’s {job} experience."
            if lang == "en"
            else f"استخدم الأسئلة المقترحة للتأكد من خبرة المرشح في {job}."
        )
    elif assessment_active and any(
        c.startswith("assessment_") and c not in {"assessment_unused_by_policy", "assessment_not_selected_by_policy"}
        for c in code_set
    ):
        next_step = (
            f"Send a fresh {job} assessment using the employer’s standard assessment flow."
            if lang == "en"
            else f"أرسل تقييماً جديداً لوظيفة {job} عبر مسار التقييم المعتمد لدى جهة العمل."
        )
    else:
        next_step = _recommended_next_step(
            state,
            code_set,
            stale=stale,
            locale=lang,
            score_visible=score_visible,
            score=score,
            assessment_active=assessment_active,
        )

    if needs_setup:
        fit = {"code": "setup", "label": _COPY[lang]["fit"]["setup"], "tone": "warning"}
        card_mode = "blocked"
    elif not score_visible and (item.get("required_evidence_complete") is False or set(codes) & _UNAVAILABLE_REASONS):
        fit = {"code": "blocked", "label": _COPY[lang]["fit"]["blocked"], "tone": "warning"}
        card_mode = "blocked"
    elif thin:
        fit = {"code": "thin", "label": _COPY[lang]["fit"]["thin"], "tone": "warning"}
        card_mode = "thin"
    elif tied:
        fit = {"code": "tied", "label": _COPY[lang]["fit"]["tied"], "tone": "neutral"}
        card_mode = "ranked"
    else:
        fit = _fit_presentation(
            score_visible=score_visible,
            score=score,
            state=state,
            tied=False,
            locale=lang,
        )
        card_mode = "ranked"

    because = _because_phrase(why, locale=lang)
    if needs_setup:
        verdict = (
            f"{name}: the CV facts are available, but HR must set job criteria before a reliable {job} comparison."
            if lang == "en" and signals.get("facts_ready")
            else (
                f"{name}: set job criteria and finish CV fact processing before a reliable {job} comparison."
                if lang == "en"
                else (
                    f"{name}: حقائق السيرة الذاتية متاحة، لكن يجب على الموارد البشرية تحديد معايير الوظيفة قبل مقارنة موثوقة لوظيفة {job}."
                    if signals.get("facts_ready")
                    else f"{name}: حدّد معايير الوظيفة وأكمل معالجة حقائق السيرة الذاتية قبل مقارنة موثوقة لوظيفة {job}."
                )
            )
        )
    elif card_mode == "blocked":
        verdict = (
            f"{name}: finish the missing evidence before this candidate can be compared."
            if lang == "en"
            else f"{name}: أكمل الأدلة الناقصة قبل مقارنة هذا المرشح."
        )
    elif thin:
        if why:
            verdict = (
                f"{name}: not enough verified evidence yet for a confident {job} ranking. Only {because} confirmed so far."
                if lang == "en"
                else f"{name}: لا توجد أدلة موثقة كافية لترتيب واثق لوظيفة {job}. المؤكد حتى الآن: {because}."
            )
        else:
            verdict = (
                f"{name}: not enough verified evidence yet for a confident {job} ranking."
                if lang == "en"
                else f"{name}: لا توجد أدلة موثقة كافية لترتيب واثق لوظيفة {job}."
            )
    elif because and fit["code"] in {"top", "strong", "worth"}:
        verdict = (
            f"{name} looks promising because {because}."
            if lang == "en"
            else f"{name} يبدو واعداً بسبب {because}."
        )
    elif because and tied:
        verdict = (
            f"{name} is close with the others because {because}—not enough difference to force a winner yet."
            if lang == "en"
            else f"{name} قريب من الآخرين بسبب {because} — لا يوجد فرق كافٍ لحسم الفائز بعد."
        )
    elif because:
        verdict = (
            f"{name} has some useful signals ({because}), but dig into the gaps before deciding."
            if lang == "en"
            else f"{name} لديه إشارات مفيدة ({because})، لكن راجع الفجوات قبل القرار."
        )
    else:
        verdict = (
            f"{name}: review the available evidence before deciding."
            if lang == "en"
            else f"{name}: راجع الأدلة المتاحة قبل القرار."
        )

    return {
        "fit": fit,
        "verdict": verdict,
        "why": why[:4],
        "gaps": gaps[:4],
        "matching_on": matching[:6],
        "interview_questions": questions[:3],
        "recommended_next_step": next_step,
        "source": "terra_brief" if terra_for_copy else "deterministic_brief",
        "tied": tied and not thin,
        "tie_label": (_COPY[lang]["close_match"] if tied and not thin else None),
        "thin": thin,
        "card_mode": card_mode,
        "evidence_quality": "thin" if thin else ("partial" if not signals.get("has_skills") or not signals.get("has_experience") else "strong"),
    }


def _safe_valid_narrative(item: dict[str, Any]) -> tuple[str | None, bool]:
    terra = item.get("terra_narrative") if isinstance(item.get("terra_narrative"), dict) else {}
    # Prefer structured brief verdict when available.
    brief = _terra_brief(item)
    if brief and str(brief.get("verdict") or "").strip():
        text = str(brief.get("verdict")).strip()
        if text and not _RAW_TECHNICAL_PATTERN.search(text) and len(text) <= 220:
            return text, True
    text = str(terra.get("text") or terra.get("narrative_text") or "").strip()
    evidence_hash = str(item.get("evidence_hash") or "")
    exact_hash = bool(evidence_hash) and str(terra.get("evidence_hash") or "") == evidence_hash
    valid = (
        bool(text)
        and len(text) <= _TERRA_MAX_CHARS
        and len([part for part in re.split(r"[.!؟]+", text) if part.strip()]) <= _TERRA_MAX_SENTENCES
        and "\n\n" not in text
        and str(terra.get("status") or "") == "completed"
        and str(terra.get("prompt_version") or "") in {NARRATIVE_PROMPT_VERSION, "ranking-terra-brief-v2", "ranking-terra-narrative-v1"}
        and exact_hash
        and terra.get("canonical") is not False
        and not _RAW_TECHNICAL_PATTERN.search(text)
    )
    return (text if valid else None), valid


def _deterministic_explanation(
    *,
    state: str,
    score_visible: bool,
    score: Any,
    locale: str,
    missing_codes: set[str] | None = None,
) -> str:
    lang = normalize_locale(locale)
    codes = missing_codes or set()
    cv_blocked = bool(codes & {
        "required_cv_unavailable",
        "cv_file_missing",
        "cv_extraction_missing",
        "cv_extraction_failed",
        "cv_processing_incomplete",
        "cv_semantic_projection_stale",
        "cv_evidence_contract_stale",
    })
    if cv_blocked:
        return (
            "يلزم إكمال معالجة السيرة الذاتية الحالية قبل مقارنة هذا المرشح."
            if lang == "ar"
            else "The current CV must finish processing before this candidate can be compared."
        )
    if lang == "ar":
        if state == "criteria_not_evaluated":
            return "لا توجد أدلة موثقة كافية لتقييم هذا المرشح بشكل موثوق حتى الآن."
        if state == "unknown":
            return "لا تزال بعض المعلومات المطلوبة غير موثقة، لذلك لا يمكن إجراء مقارنة موثوقة بعد."
        if state == "not_met":
            suffix = " كما أن الدرجة الاستشارية منخفضة وفق الأدلة المتاحة." if score_visible and float(score or 0) < 40 else ""
            return "تشير النتيجة الملتزم بها إلى أن المرشح لا يستوفي متطلباً إلزامياً واحداً أو أكثر." + suffix
        if state == "not_applicable":
            return "مقارنة سريعة مبنية على الأدلة المتاحة — أضف متطلبات الوظيفة للحصول على حكم أوضح."
        if score_visible and float(score or 0) < 40:
            return "الإشارة العامة ما زالت ضعيفة وفق الأدلة المتاحة."
        return "تشير الأدلة المتاحة إلى توافق يستحق المراجعة."
    if state == "criteria_not_evaluated":
        return "There is not enough verified evidence to evaluate this candidate reliably yet."
    if state == "unknown":
        return "Some required information is still unverified, so a reliable comparison is not available yet."
    if state == "not_met":
        suffix = " The advisory score is also low based on the available evidence." if score_visible and float(score or 0) < 40 else ""
        return "The committed result shows that this candidate does not meet one or more required criteria." + suffix
    if state == "not_applicable":
        return "A quick evidence-based comparison—add job requirements for a sharper fit call."
    if score_visible and float(score or 0) < 40:
        return "The overall signal is still modest based on the available evidence."
    return "The available evidence suggests a fit worth reviewing."


def _recommended_next_step(
    state: str,
    codes: set[str],
    *,
    stale: bool,
    locale: str,
    score_visible: bool = True,
    score: Any = None,
    assessment_active: bool = True,
) -> str:
    lang = normalize_locale(locale)
    if stale:
        return "أعد حساب الترتيب بعد تحديث الأدلة" if lang == "ar" else "Recalculate ranking after the evidence is updated"
    if codes & {
        "required_cv_unavailable",
        "cv_file_missing",
        "cv_extraction_missing",
        "cv_extraction_failed",
        "cv_processing_incomplete",
        "cv_semantic_projection_stale",
        "cv_evidence_contract_stale",
    }:
        return "أكمل معالجة السيرة الذاتية ثم أعد الترتيب" if lang == "ar" else "Finish CV processing, then refresh ranking"
    if assessment_active and any(
        code.startswith("assessment_")
        and code not in {"assessment_unused_by_policy", "assessment_not_selected_by_policy"}
        for code in codes
    ):
        return (
            "أرسل تقييماً قصيراً مناسباً للوظيفة، ثم راجع النتيجة"
            if lang == "ar"
            else "Send a short role-relevant assessment, then review the result"
        )
    if state == "not_applicable" or codes & _CRITERIA_REASONS:
        return (
            "راجع السيرة الذاتية، ثم حدّد 3–5 متطلبات للوظيفة للحصول على ترتيب أوضح"
            if lang == "ar"
            else "Review the CV, then set 3–5 job requirements for a sharper ranking"
        )
    if state == "unknown":
        return "تحقق من المعلومة الناقصة قبل المقارنة" if lang == "ar" else "Verify the missing fact before comparing further"
    if state == "not_met":
        return "راجع المتطلب غير المستوفى وقرر إن كان قابلاً للتجاوز" if lang == "ar" else "Review the unmet requirement and decide if it is flexible"
    try:
        value = float(score or 0) if score_visible else 0.0
    except (TypeError, ValueError):
        value = 0.0
    if score_visible and value >= 70:
        return "راجع السيرة الذاتية ثم حدّد مقابلة قصيرة" if lang == "ar" else "Review the CV, then schedule a short interview"
    if score_visible and value >= 55:
        if assessment_active:
            return "راجع الأدلة ثم قرر: تقييم قصير أو مقابلة أولية" if lang == "ar" else "Review the evidence, then choose a short assessment or screening interview"
        return "راجع الأدلة ثم قرر خطوة المقابلة الأولية" if lang == "ar" else "Review the evidence, then choose a screening interview"
    return "راجع الأدلة بعناية قبل اتخاذ أي خطوة تالية" if lang == "ar" else "Review the evidence carefully before deciding the next move"


def present_candidate(
    item: dict[str, Any],
    *,
    run: dict[str, Any] | None = None,
    locale: str = "en",
    tied: bool = False,
) -> dict[str, Any]:
    """Build compact and technical views from one committed item."""
    lang = normalize_locale(locale)
    run_data = run if isinstance(run, dict) else {}
    display = item.get("display") if isinstance(item.get("display"), dict) else {}
    state = canonical_state(item.get("eligibility_bucket"))
    basis = _ranking_basis(item)
    automatic_comparison = basis.get("source") in {
        "job_requirements",
        "job_title_profile",
        "job_title",
    } and bool(basis.get("criteria_count"))
    coverage_raw = item.get("evidence_coverage")
    if coverage_raw is None:
        coverage_raw = (item.get("provenance") or {}).get("evidence_coverage") if isinstance(item.get("provenance"), dict) else None
    try:
        coverage_value = float(coverage_raw)
    except (TypeError, ValueError):
        coverage_value = 0.0
    stale = bool(run_data.get("stale") or run_data.get("stale_reason") or item.get("stale"))
    score = _numeric_score_presentation(
        item,
        state=state,
        coverage=coverage_value,
        stale=stale,
        locale=lang,
    )
    strengths, evidence_sections = _component_presentation(item, locale=lang)
    codes = _display_missing_codes(item)
    missing_labels = list(dict.fromkeys(missing_reason_label(code, locale=lang) for code in codes))
    brief = _build_ranking_brief(
        item,
        locale=lang,
        state=state,
        score_visible=bool(score["show_numeric"]),
        score=item.get("advisory_score", item.get("score")),
        codes=list(codes),
        stale=stale,
        run=run_data,
        tied=tied,
    )
    # The brief owns the HR-facing verdict (because-XYZ or honest "not enough").
    # Do not let long/playful Terra prose override that product contract.
    explanation = brief["verdict"] or _deterministic_explanation(
        state=state,
        score_visible=bool(score["show_numeric"]),
        score=item.get("advisory_score", item.get("score")),
        locale=lang,
        missing_codes=set(codes),
    )
    explanation_source = brief.get("source") or "deterministic_committed_result"
    if explanation_source == "deterministic_brief":
        explanation_source = "deterministic_committed_result"
    provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
    run_provenance = run_data.get("provenance") if isinstance(run_data.get("provenance"), dict) else {}
    technical = {
        "run_id": run_data.get("run_id") or item.get("run_id"),
        "item_id": item.get("item_id"),
        "eligibility_bucket": item.get("eligibility_bucket"),
        "evidence_coverage": copy.deepcopy(coverage_raw),
        "missing_reason_codes": copy.deepcopy(codes),
        "requirement_results": copy.deepcopy(item.get("requirement_results") or []),
        "stale": stale,
        "criteria_version": provenance.get("criteria_version") or run_provenance.get("criteria_version"),
        "scoring_config_version": provenance.get("scoring_config_version") or run_data.get("scoring_config_version"),
        "denylist_version": provenance.get("denylist_version") or run_data.get("denylist_version"),
        "evidence_quality": brief.get("evidence_quality"),
        "card_mode": brief.get("card_mode"),
        "ranking_basis": copy.deepcopy(basis),
    }
    # Never expose advisory_score in technical_details when the owner-facing card hides it.
    if score["show_numeric"]:
        technical["advisory_score"] = copy.deepcopy(item.get("advisory_score", item.get("score")))
    raw_name = item.get("name") or display.get("name") or "Candidate"
    return {
        "version": PRESENTATION_VERSION,
        "locale": lang,
        "candidate_name": _title_case_name(str(raw_name)),
        "job_title": item.get("position_title") or display.get("position_title") or run_data.get("position_title") or item.get("position_code") or run_data.get("position_code"),
        "state": {
            "code": state,
            "label": (
                ("Compared using the job profile" if lang == "en" else "مقارنة باستخدام ملف الوظيفة")
                if state == "not_applicable" and automatic_comparison
                else _COPY[lang]["states"][state]
            ),
        },
        "ranking_basis": copy.deepcopy(basis),
        "score": score,
        "coverage": coverage_presentation(coverage_value, locale=lang),
        "explanation": explanation,
        "explanation_source": explanation_source,
        "fit": brief["fit"],
        "verdict": brief["verdict"],
        "why": brief["why"],
        "gaps": brief["gaps"],
        "matching_on": brief["matching_on"],
        "interview_questions": brief["interview_questions"],
        "tied": bool(brief.get("tied")),
        "tie_label": brief.get("tie_label"),
        "thin": bool(brief.get("thin")),
        "card_mode": brief.get("card_mode") or "ranked",
        "evidence_quality": brief.get("evidence_quality") or "partial",
        "strengths": strengths,
        "evidence_highlights": _evidence_highlights(item, locale=lang),
        "missing": missing_labels,
        "evidence_sections": evidence_sections,
        "recommended_next_step": brief["recommended_next_step"],
        "hr_decides": _COPY[lang]["hr_decides"],
        "labels": {
            "missing": _COPY[lang]["missing_heading"],
            "strengths": _COPY[lang]["strengths_heading"],
            "next_step": _COPY[lang]["next_step"],
            "questions": _COPY[lang]["questions_heading"],
            "matching": _COPY[lang]["matching_heading"],
            "technical_details": _COPY[lang]["technical"],
        },
        "technical_details": technical,
    }


def hydrate_ranking_display_names(
    orch: Any,
    result: dict[str, Any],
    *,
    company_code: str | None = None,
) -> dict[str, Any]:
    """Tenant-scoped, read-only display-name hydration for Ranking presentation.

    Resolves names from canonical candidate/application records by
    ``company_code + app_key``. Never persists into Ranking runs/items.
    """
    if not isinstance(result, dict):
        return result
    company = str(company_code or result.get("company_code") or "").strip()
    if not company:
        return result
    app_keys: list[str] = []
    for bucket in (result.get("items"), result.get("candidates")):
        for item in list(bucket or []):
            if not isinstance(item, dict):
                continue
            key = str(item.get("app_key") or "").strip()
            if key:
                app_keys.append(key)
    app_keys = sorted(set(app_keys))
    if not app_keys:
        return result
    names: dict[str, str] = {}
    try:
        with orch.db_connect() as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    SELECT a.app_key,
                           COALESCE(
                             NULLIF(btrim(c.name), ''),
                             NULLIF(btrim(a.raw_json->>'candidate_name'), ''),
                             NULLIF(btrim(a.raw_json->'candidate'->>'name'), ''),
                             NULLIF(btrim(a.raw_json->>'name'), '')
                           ) AS display_name
                    FROM applications a
                    LEFT JOIN candidates c ON c.phone = a.phone
                    WHERE a.company_code=%s AND a.app_key = ANY(%s)
                    """,
                    (company, app_keys),
                )
                rows = cur.fetchall() or []
            finally:
                close = getattr(cur, "close", None)
                if callable(close):
                    close()
            for row in rows:
                payload = dict(row) if not isinstance(row, dict) else row
                key = str(payload.get("app_key") or "").strip()
                name = str(payload.get("display_name") or "").strip()
                if key and name:
                    names[key] = name
    except Exception:
        # Presentation hydration must never fail Ranking reads.
        return result

    def _apply(item: dict[str, Any]) -> None:
        key = str(item.get("app_key") or "").strip()
        display = item.get("display") if isinstance(item.get("display"), dict) else {}
        current = str(item.get("name") or display.get("name") or "").strip()
        resolved = names.get(key) or current
        if not resolved or resolved.lower() in {"candidate", "unknown", "n/a", "-"}:
            if not names.get(key):
                return
        pretty = _title_case_name(str(names.get(key) or resolved))
        item["name"] = pretty
        item["display"] = {**display, "name": pretty}

    for item in list(result.get("items") or []):
        if isinstance(item, dict):
            _apply(item)
    for item in list(result.get("candidates") or []):
        if isinstance(item, dict):
            _apply(item)
    return result


def attach_presentations(
    result: dict[str, Any],
    *,
    locale: str = "en",
    orch: Any = None,
    company_code: str | None = None,
) -> dict[str, Any]:
    """Attach the shared presentation contract to a legacy Ranking response.

    Canonical fields are retained exactly. Only additive presentation fields are
    written to the response object.
    """
    if orch is not None:
        hydrate_ranking_display_names(orch, result, company_code=company_code or result.get("company_code"))
    lang = normalize_locale(locale)
    canonical_items = {
        str(item.get("app_key") or ""): item
        for item in (result.get("items") or [])
        if isinstance(item, dict)
    }
    # Pre-compute close ties from committed advisory scores (never mutate scores).
    scored: list[tuple[str, float]] = []
    for item in (result.get("items") or []):
        if not isinstance(item, dict):
            continue
        key = str(item.get("app_key") or "")
        try:
            value = float(item.get("advisory_score"))
        except (TypeError, ValueError):
            continue
        if key:
            scored.append((key, value))
    tied_keys: set[str] = set()
    for idx, (key, value) in enumerate(scored):
        for other_key, other_value in scored:
            if other_key == key:
                continue
            if abs(value - other_value) <= TIE_SCORE_DELTA:
                tied_keys.add(key)
                tied_keys.add(other_key)
    for candidate in list(result.get("candidates") or []):
        if not isinstance(candidate, dict):
            continue
        committed = canonical_items.get(str(candidate.get("app_key") or ""))
        source = (
            {
                **committed,
                "name": candidate.get("name") or (committed or {}).get("name"),
                "position_title": candidate.get("position_title"),
                "position_code": candidate.get("position_code"),
                "optional_missing": (committed or {}).get("optional_missing") or candidate.get("optional_missing"),
                "required_missing": (committed or {}).get("required_missing") or candidate.get("required_missing"),
                "required_evidence_complete": (committed or {}).get("required_evidence_complete", candidate.get("required_evidence_complete")),
                "confidence": (committed or {}).get("confidence") or candidate.get("confidence"),
            }
            if isinstance(committed, dict)
            else candidate
        )
        candidate["presentation"] = present_candidate(
            source,
            run=result,
            locale=lang,
            tied=str(candidate.get("app_key") or "") in tied_keys,
        )
    presentations = [
        c.get("presentation")
        for c in (result.get("candidates") or [])
        if isinstance(c, dict) and isinstance(c.get("presentation"), dict)
    ]
    thin_count = sum(1 for p in presentations if p.get("thin") or p.get("card_mode") == "thin")
    blocked_count = sum(1 for p in presentations if p.get("card_mode") == "blocked")
    setup_count = sum(1 for p in presentations if (p.get("fit") or {}).get("code") == "setup")
    ranked_count = sum(1 for p in presentations if p.get("card_mode") == "ranked" and p.get("score", {}).get("show_numeric"))
    ranked_presentations = [
        p for p in presentations
        if p.get("card_mode") == "ranked" and p.get("score", {}).get("show_numeric")
    ]
    result_filters = result.get("filters") if isinstance(result.get("filters"), dict) else {}
    job_title = (
        result_filters.get("display_title")
        or result_filters.get("position_title")
        or result.get("position_title")
        or result_filters.get("position")
        or result_filters.get("position_raw")
        or result.get("position_code")
        or ("this job" if lang == "en" else "هذه الوظيفة")
    )
    if presentations and setup_count == len(presentations):
        comparison = {
            "status": "blocked",
            "title": _COPY[lang]["setup_needed"],
            "detail": (
                f"Set the job criteria for {job_title}, then recalculate Ranking."
                if lang == "en"
                else f"حدّد معايير وظيفة {job_title}، ثم أعد حساب الترتيب."
            ),
        }
    elif presentations and blocked_count == len(presentations):
        comparison = {
            "status": "blocked",
            "title": _COPY[lang]["fit"]["blocked"],
            "detail": (
                "Required evidence is still missing before these candidates can be compared."
                if lang == "en"
                else "ما زالت الأدلة المطلوبة ناقصة قبل مقارنة هؤلاء المرشحين."
            ),
        }
    elif presentations and thin_count == len(presentations):
        comparison = {
            "status": "no_clear_winner",
            "title": _COPY[lang]["no_clear_winner"],
            "detail": (
                f"Candidates for {job_title} only share thin verified evidence so far—not enough to force a ranking winner."
                if lang == "en"
                else f"مرشحو {job_title} يتشاركون أدلة موثقة ضعيفة حتى الآن — ليست كافية لحسم فائز في الترتيب."
            ),
        }
    elif thin_count and ranked_count:
        comparison = {
            "status": "mixed",
            "title": _COPY[lang]["thin_evidence"] if lang == "en" else _COPY[lang]["thin_evidence"],
            "detail": (
                f"{ranked_count} candidate(s) have enough signal to review; {thin_count} still need stronger evidence."
                if lang == "en"
                else f"{ranked_count} مرشح لديهم إشارة كافية للمراجعة؛ و{thin_count} ما زالوا يحتاجون أدلة أقوى."
            ),
        }
    elif len(presentations) == 1 and ranked_count == 1:
        comparison = {
            "status": "single_candidate",
            "title": _COPY[lang]["fit"].get("worth") if lang == "en" else "مرشح واحد للمراجعة",
            "detail": (
                f"There is one candidate for {job_title}. Review the match, watch-outs, and suggested questions below."
                if lang == "en"
                else f"يوجد مرشح واحد لوظيفة {job_title}. راجع التوافق والملاحظات والأسئلة المقترحة أدناه."
            ),
        }
        if lang == "en":
            comparison["title"] = "1 candidate to review"
    elif ranked_count >= 2 and sum(1 for p in ranked_presentations if p.get("tied")) >= 2:
        comparison = {
            "status": "no_clear_winner",
            "title": _COPY[lang]["no_clear_winner"],
            "detail": (
                f"The leading candidates for {job_title} are too close to separate confidently. Use the suggested questions to confirm the difference."
                if lang == "en"
                else f"المرشحون المتصدرون لوظيفة {job_title} متقاربون جداً. استخدم الأسئلة المقترحة للتأكد من الفارق."
            ),
        }
    elif ranked_count >= 2:
        leader = ranked_presentations[0]
        leader_name = leader.get("candidate_name") or ("The top candidate" if lang == "en" else "المرشح الأول")
        basis_label = (leader.get("ranking_basis") or {}).get("label")
        leader["fit"] = {
            "code": "leader",
            "label": "Strongest match" if lang == "en" else "الأقوى توافقاً",
            "tone": "success",
        }
        comparison = {
            "status": "leader",
            "title": (
                f"{leader_name} is the strongest match"
                if lang == "en"
                else f"{leader_name} هو الأقوى توافقاً"
            ),
            "detail": (
                f"Based on {str(basis_label or 'the job profile').lower()} and the available CV facts. Review why and the watch-outs below."
                if lang == "en"
                else "استناداً إلى ملف الوظيفة وحقائق السيرة الذاتية المتاحة. راجع الأسباب والملاحظات أدناه."
            ),
        }
    else:
        comparison = {
            "status": "ready",
            "title": (
                f"{ranked_count} candidate{'s' if ranked_count != 1 else ''} ready to compare"
                if lang == "en"
                else f"{ranked_count} مرشح جاهز للمقارنة"
            ),
            "detail": (
                f"Candidates for {job_title} are ordered by the available verified evidence."
                if lang == "en"
                else f"مرشحو {job_title} مرتبون حسب الأدلة الموثقة المتاحة."
            ),
        }
    result["comparison"] = comparison
    result["presentation_contract"] = {
        "version": PRESENTATION_VERSION,
        "missing_reason_mapping_version": MISSING_REASON_MAPPING_VERSION,
        "coverage_label_version": COVERAGE_LABEL_VERSION,
        "score_display_version": SCORE_DISPLAY_VERSION,
        "locale": lang,
    }
    result["presentation_summary"] = ranking_summary(result, locale=lang)
    return result


def ranking_summary(result: dict[str, Any], *, locale: str = "en") -> str:
    lang = normalize_locale(locale)
    candidates = [c for c in (result.get("candidates") or []) if isinstance(c, dict)]
    total = int(result.get("pool_total") or result.get("total_matching") or len(candidates))
    position = (
        (result.get("filters") or {}).get("display_title")
        if isinstance(result.get("filters"), dict)
        else None
    ) or (
        (result.get("filters") or {}).get("position")
        if isinstance(result.get("filters"), dict)
        else None
    ) or result.get("position_title") or result.get("position_code") or "this job"
    presentations = [c.get("presentation") for c in candidates if isinstance(c.get("presentation"), dict)]
    comparison = result.get("comparison") if isinstance(result.get("comparison"), dict) else {}
    if comparison.get("status") == "no_clear_winner":
        return str(comparison.get("detail") or "") + (" HR makes the final decision." if lang == "en" else " القرار النهائي للموارد البشرية.")
    incomplete = [
        p for p in presentations
        if p.get("card_mode") in {"blocked", "thin"}
        or p["state"]["code"] in {"criteria_not_evaluated", "unknown"}
        or not p["score"]["show_numeric"]
    ]
    missing_counter = Counter(label for p in presentations for label in p.get("gaps") or p.get("missing") or [])
    shared_missing = [label for label, count in missing_counter.items() if count == len(presentations) and count > 0]
    if lang == "ar":
        if presentations and len(incomplete) == len(presentations):
            text = f"وجدت {total} مرشحاً لوظيفة {position}، لكن لا تتوفر أدلة موثقة كافية لإجراء مقارنة موثوقة حتى الآن."
            if shared_missing:
                text += " النواقص المشتركة: " + "، ".join(shared_missing[:3]) + "."
            return text + " أوصي بإرسال التقييم نفسه أو استكمال الأدلة قبل اتخاذ القرار. القرار النهائي للموارد البشرية."
        return f"وجدت {total} مرشحاً لوظيفة {position}. تعرض البطاقات لماذا يبدو المرشح واعداً، وما ينقصه، والخطوة التالية. القرار النهائي للموارد البشرية."
    if presentations and len(incomplete) == len(presentations):
        noun = "candidate" if total == 1 else "candidates"
        subject = "this candidate does not" if total == 1 else "they do not"
        text = f"I found {total} {noun} for {position}, but {subject} have enough verified evidence for a reliable comparison yet."
        if shared_missing:
            text += " Shared gaps: " + "; ".join(shared_missing[:3]) + "."
        return text + " I recommend sending the same assessment or completing the missing evidence before deciding. HR makes the final decision."
    noun = "candidate" if total == 1 else "candidates"
    return f"I found {total} {noun} for {position}. Each card explains why they look promising, what is missing, and what to do next. HR makes the final decision."


def format_compact_card(presentation: dict[str, Any]) -> str:
    lang = normalize_locale(str(presentation.get("locale") or "en"))
    labels = presentation.get("labels") if isinstance(presentation.get("labels"), dict) else {}
    lines = [
        f"**{presentation.get('candidate_name') or 'Candidate'}**",
        str(presentation.get("job_title") or ""),
        "",
        f"**{(presentation.get('state') or {}).get('label')}**",
        "",
        str(presentation.get("explanation") or ""),
    ]
    score = presentation.get("score") if isinstance(presentation.get("score"), dict) else {}
    if score.get("show_numeric"):
        lines.extend(["", f"{'Advisory score' if lang == 'en' else 'الدرجة الاستشارية'}: {score.get('label')}"])
    elif score.get("label"):
        lines.extend(["", str(score["label"])])
    coverage = presentation.get("coverage") if isinstance(presentation.get("coverage"), dict) else {}
    if coverage.get("label"):
        lines.append(f"{'Evidence' if lang == 'en' else 'الأدلة'}: {coverage['label']}")
    strengths = presentation.get("strengths") or []
    if strengths:
        lines.extend(["", f"{labels.get('strengths') or 'Key strengths'}:"])
        lines.extend(f"- {item.get('label')}: {item.get('value')}" for item in strengths)
    missing = presentation.get("missing") or []
    if missing:
        lines.extend(["", f"{labels.get('missing') or 'Missing'}:"])
        lines.extend(f"- {item}" for item in missing)
    lines.extend(
        [
            "",
            f"{labels.get('next_step') or 'Next step'}: {presentation.get('recommended_next_step')}",
            "",
            str(presentation.get("hr_decides") or _COPY[lang]["hr_decides"]),
        ]
    )
    return "\n".join(line for line in lines if line is not None).strip()


def format_assistant_result(result: dict[str, Any], *, locale: str = "en") -> str:
    attach_presentations(result, locale=locale)
    cards = [
        format_compact_card(candidate["presentation"])
        for candidate in (result.get("candidates") or [])
        if isinstance(candidate, dict) and isinstance(candidate.get("presentation"), dict)
    ]
    summary = str(result.get("presentation_summary") or "")
    return "\n\n---\n\n".join([summary, *cards]) if cards else summary


def compact_chat_artifact(candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Return presentation-safe fields for a dashboard Assistant candidate card."""
    presentation = candidate.get("presentation") if isinstance(candidate.get("presentation"), dict) else None
    if not presentation:
        return None
    score = presentation.get("score") if isinstance(presentation.get("score"), dict) else {}
    explanation = str(presentation.get("explanation") or "").strip()
    return {
        "position": presentation.get("job_title"),
        "score": score.get("value") if score.get("show_numeric") else None,
        "reasons": [explanation] if explanation else [],
        "presentation": copy.deepcopy(presentation),
    }
