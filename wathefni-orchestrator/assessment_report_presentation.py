"""Canonical assessment report presentation authority (Wave 3).

Backend-owned HR report contract. Scores remain deterministic, immutable, and
backend-owned; this module only maps them into one coherent HR-facing payload.

Separates:
- assessment completed
- scoring complete
- report ready
- HR review pending
- HR reviewed

Raw technical bands (needs_review, low, mixed, development) are mapped to
human-readable labels and never leak directly to HR.
"""

from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _human_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for item in values:
        text = _text(item)
        if not text:
            continue
        out.append(text.replace("_", " "))
    return out


def score_band_label(value: Any) -> str:
    normalized = _lower(value)
    mapping = {
        "strong": "Strong",
        "qualified": "Qualified",
        "high": "Strong match",
        "medium": "Moderate match",
        "low": "Needs review",
        "needs_review": "Needs review",
        "mixed": "Mixed evidence",
        "development": "Development area",
        "strength": "Strength",
        "proficient": "Proficient",
    }
    return mapping.get(normalized, "Needs review" if normalized else "Not available")


def review_state_label(state: str) -> str:
    return {
        "not_applicable": "Not applicable",
        "unreviewed": "Review pending",
        "reviewed": "Reviewed",
    }.get(state, "Review pending")


def build_assessment_report_presentation(
    *,
    attempt: dict[str, Any],
    report: dict[str, Any] | None,
    locale: str = "en",
) -> dict[str, Any]:
    """One backend report presentation for HR."""
    attempt = attempt if isinstance(attempt, dict) else {}
    report = report if isinstance(report, dict) else {}
    job_match = report.get("job_match") if isinstance(report.get("job_match"), dict) else {}
    sections = report.get("report_sections") if isinstance(report.get("report_sections"), dict) else {}

    attempt_state = _lower(attempt.get("status"))
    completed = attempt_state == "completed"
    percent = report.get("percent") if report.get("percent") is not None else attempt.get("percent")
    scoring_complete = completed and percent is not None
    report_ready = scoring_complete and bool(report)
    review_state = "not_applicable" if not completed else ("reviewed" if _lower(attempt.get("review_status")) == "reviewed" else "unreviewed")

    overall_score = percent if scoring_complete else None
    job_match_percent = job_match.get("job_match_percent")
    ability_fit = job_match.get("ability_fit_percent")
    competency_fit = job_match.get("competency_fit_percent")

    strengths = _human_list(job_match.get("strengths"))
    development_areas = _human_list(job_match.get("development_areas"))

    probes_raw = sections.get("interview_probes") if isinstance(sections.get("interview_probes"), list) else []
    probes = []
    for item in probes_raw[:6]:
        if not isinstance(item, dict):
            continue
        question = _text(item.get("question"))
        if not question:
            continue
        probes.append(
            {
                "competency": _text(item.get("competency")).replace("_", " ") or None,
                "question": question,
            }
        )

    candidate = _text(attempt.get("candidate_name") or attempt.get("phone") or "the candidate")
    role = _text(attempt.get("position_title") or attempt.get("position_code") or "the role")
    if not completed:
        executive_summary = f"Assessment is not completed yet for {candidate}."
    elif not scoring_complete:
        executive_summary = f"Assessment completed for {candidate}. Scoring is being prepared."
    elif not report_ready:
        executive_summary = f"Assessment scored for {candidate}. Report is being prepared."
    else:
        band = score_band_label(job_match.get("fit_band") or report.get("band"))
        executive_summary = (
            f"{candidate} scored {overall_score}% overall for {role} ({band}). "
            f"Job match {job_match_percent if job_match_percent is not None else 'not available'}%."
        )

    next_human_action = "review_report" if report_ready and review_state == "unreviewed" else (
        "view_report" if report_ready else ("wait_for_report" if completed else "wait_for_candidate")
    )

    allowed_actions: list[str] = []
    if report_ready:
        allowed_actions.append("view_report")
        if review_state == "unreviewed":
            allowed_actions.append("mark_reviewed")
    if not completed:
        allowed_actions.append("open_attempt")

    return {
        "version": "assessment_report_presentation_v1",
        "locale": "ar" if str(locale).lower().startswith("ar") else "en",
        "attempt_id": attempt.get("attempt_id"),
        "assessment_completed": completed,
        "scoring_complete": scoring_complete,
        "report_ready": report_ready,
        "review_state": review_state,
        "review_label": review_state_label(review_state),
        "reviewed": review_state == "reviewed",
        "candidate": {
            "name": attempt.get("candidate_name"),
            "email": attempt.get("candidate_email"),
            "phone": attempt.get("phone"),
        },
        "job": {
            "position_code": attempt.get("position_code"),
            "position_title": attempt.get("position_title"),
        },
        "executive_summary": executive_summary,
        "scores": {
            "overall": overall_score,
            "job_match": job_match_percent,
            "ability_fit": ability_fit,
            "competency_fit": competency_fit,
        },
        "labels": {
            "overall_band": score_band_label(report.get("band")) if report_ready else None,
            "job_match_band": score_band_label(job_match.get("fit_band")) if report_ready else None,
            "role_profile": job_match.get("role_profile_label"),
        },
        "strengths": strengths[:5],
        "growth_areas": development_areas[:5],
        "interview_probes": probes,
        "review": {
            "state": review_state,
            "label": review_state_label(review_state),
            "reviewed_at": attempt.get("reviewed_at"),
            "reviewed_by_user_id": attempt.get("reviewed_by_user_id"),
        },
        "next_human_action": next_human_action,
        "allowed_actions": allowed_actions,
        "report_version": report.get("report_version") or report.get("version") or "assessment_report_v1",
        "norm_version": report.get("norm_version") or job_match.get("norm_version"),
        "immutable": True,
    }
