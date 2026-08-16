"""Canonical assessment presentation authority (Wave 1).

Backend-authoritative presentation that separates:
- person
- application
- invitation
- attempt
- delivery state
- attempt state
- review state
- report state
- next human action
- allowed actions

Operational queues count actionable application/attempt records; people count is
secondary metadata only. Raw legacy fields remain untouched for audit/history.
"""

from __future__ import annotations

from typing import Any


DELIVERY_FAILED_STATES = ("failed", "send_failed", "invitation_failed")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def delivery_failed(delivery_status: str | None) -> bool:
    return _lower(delivery_status) in DELIVERY_FAILED_STATES


def canonical_delivery_state(delivery_status: str | None) -> str:
    normalized = _lower(delivery_status)
    if normalized in DELIVERY_FAILED_STATES:
        return "failed"
    if normalized in {"sent", "delivered"}:
        return "sent"
    if normalized in {"pending", "queued"}:
        return "pending"
    return "not_requested"


def canonical_attempt_state(status: str | None) -> str:
    normalized = _lower(status)
    if normalized in {"pending", "in_progress", "expired", "completed", "cancelled"}:
        return normalized
    return normalized or "none"


def canonical_review_state(review_status: str | None, attempt_state: str) -> str:
    normalized = _lower(review_status)
    if attempt_state != "completed":
        return "not_applicable"
    return "reviewed" if normalized == "reviewed" else "unreviewed"


def canonical_report_state(attempt_state: str, has_report: bool, percent: Any) -> str:
    if attempt_state != "completed":
        return "unavailable"
    if has_report or percent is not None:
        return "ready"
    return "pending"


def next_human_action(
    *,
    attempt_state: str,
    delivery_state: str,
    review_state: str,
    report_state: str,
    has_active_invitation: bool,
) -> str:
    if attempt_state == "none":
        return "send_assessment"
    if delivery_state == "failed":
        return "retry_delivery"
    if attempt_state == "expired":
        return "resend_assessment"
    if attempt_state == "pending":
        return "wait_for_candidate"
    if attempt_state == "in_progress":
        return "wait_for_candidate"
    if attempt_state == "completed":
        if review_state == "unreviewed" and report_state == "ready":
            return "review_report"
        return "view_report" if report_state == "ready" else "wait_for_report"
    if attempt_state == "cancelled":
        return "reissue_assessment"
    return "review_next_step"


def allowed_actions(
    *,
    can_manage: bool,
    attempt_state: str,
    delivery_state: str,
    review_state: str,
    report_state: str,
    has_active_invitation: bool,
) -> list[str]:
    if not can_manage:
        return []
    actions: list[str] = []

    def _add(name: str) -> None:
        if name not in actions:
            actions.append(name)

    if attempt_state == "none":
        _add("send_assessment")
        return actions
    if delivery_state == "failed":
        _add("resend_assessment")
        _add("cancel_assessment")
        return actions
    if attempt_state == "expired":
        _add("resend_assessment")
        return actions
    if attempt_state in {"pending", "in_progress"}:
        _add("resend_assessment")
        _add("cancel_assessment")
        _add("open_attempt")
        return actions
    if attempt_state == "completed":
        if report_state == "ready":
            _add("view_report")
            if review_state == "unreviewed":
                _add("mark_reviewed")
        else:
            _add("open_attempt")
        return actions
    if attempt_state == "cancelled":
        _add("resend_assessment")
        return actions
    return actions


def build_assessment_presentation(
    *,
    application: dict[str, Any] | None = None,
    attempt: dict[str, Any] | None = None,
    person: dict[str, Any] | None = None,
    can_manage: bool = False,
) -> dict[str, Any]:
    """One backend presentation object per application/attempt."""
    application = application if isinstance(application, dict) else {}
    attempt = attempt if isinstance(attempt, dict) else None
    person = person if isinstance(person, dict) else {}

    app_key = _text((attempt or {}).get("app_key") or application.get("app_key"))
    application_status = _lower((attempt or {}).get("application_status") or application.get("status"))
    candidate_name = (attempt or {}).get("candidate_name") or person.get("name") or application.get("candidate_name")
    candidate_email = (attempt or {}).get("candidate_email") or person.get("email") or application.get("candidate_email")
    phone = (attempt or {}).get("phone") or application.get("phone")

    attempt_state = canonical_attempt_state((attempt or {}).get("status")) if attempt else "none"
    delivery_state = canonical_delivery_state((attempt or {}).get("delivery_status")) if attempt else "not_requested"
    review_state = canonical_review_state((attempt or {}).get("review_status") if attempt else None, attempt_state)
    has_report = bool((attempt or {}).get("report_json") or (attempt or {}).get("summary"))
    percent = (attempt or {}).get("percent")
    report_state = canonical_report_state(attempt_state, has_report, percent)
    has_active_invitation = bool(
        attempt
        and attempt_state in {"pending", "in_progress"}
        and not (attempt or {}).get("cancelled_at")
        and delivery_state != "failed"
    )

    action = next_human_action(
        attempt_state=attempt_state,
        delivery_state=delivery_state,
        review_state=review_state,
        report_state=report_state,
        has_active_invitation=has_active_invitation,
    )
    actions = allowed_actions(
        can_manage=can_manage,
        attempt_state=attempt_state,
        delivery_state=delivery_state,
        review_state=review_state,
        report_state=report_state,
        has_active_invitation=has_active_invitation,
    )

    # Cohort classification for queue parity (application/attempt unit)
    if not attempt:
        cohort = "assessment_ready_to_send"
    elif delivery_state == "failed" and attempt_state in {"pending", "in_progress"}:
        cohort = "assessment_delivery_failed"
    elif attempt_state == "pending":
        cohort = "assessment_sent_pending"
    elif attempt_state == "in_progress":
        cohort = "assessment_in_progress"
    elif attempt_state == "expired":
        cohort = "assessment_resend_needed"
    elif attempt_state == "completed":
        cohort = "assessment_completed"
    elif attempt_state == "cancelled":
        # Attempts-history only — never Send / attention.
        cohort = None
    else:
        cohort = None

    display_status = {
        "assessment_ready_to_send": "Ready to send",
        "assessment_sent_pending": "Sent",
        "assessment_in_progress": "In progress",
        "assessment_resend_needed": "Expired",
        "assessment_delivery_failed": "Delivery failed",
        "assessment_completed": "Completed",
    }.get(cohort or "", None)
    if display_status is None:
        if attempt_state == "cancelled":
            display_status = "Cancelled"
        else:
            display_status = attempt_state.replace("_", " ").title() or "Not sent"

    return {
        "version": "assessment_presentation_v1",
        "unit": "attempt" if attempt else "application",
        "person": {
            "name": candidate_name,
            "email": candidate_email,
            "phone": phone,
        },
        "application": {
            "app_key": app_key or None,
            "status": application_status or None,
            "position_code": (attempt or {}).get("position_code") or application.get("position_code"),
            "position_title": (attempt or {}).get("position_title") or application.get("position_title"),
        },
        "invitation": {
            "attempt_id": (attempt or {}).get("attempt_id"),
            "has_active": has_active_invitation,
            "delivery_state": delivery_state,
            "expires_at": (attempt or {}).get("expires_at"),
            "cancelled_at": (attempt or {}).get("cancelled_at"),
        },
        "attempt": {
            "state": attempt_state,
            "delivery_state": delivery_state,
            "review_state": review_state,
            "report_state": report_state,
            "percent": percent,
            "band": (attempt or {}).get("band"),
            "job_match_percent": ((attempt or {}).get("job_match") or {}).get("job_match_percent")
            if isinstance((attempt or {}).get("job_match"), dict)
            else None,
            "completed_at": (attempt or {}).get("completed_at"),
        },
        "report": {
            "state": report_state,
            "ready": report_state == "ready",
            "immutable": True,
        },
        "cohort_key": cohort,
        "display_status": display_status,
        "needs_review": attempt_state == "completed" and review_state == "unreviewed",
        "next_human_action": action,
        "allowed_actions": actions,
    }
