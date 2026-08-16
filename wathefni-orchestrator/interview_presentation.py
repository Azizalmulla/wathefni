"""Canonical interview presentation authority (Wave 1).

Backend-authoritative presentation contract that separates:
- interview type
- interview progress
- schedule state
- invitation state
- candidate confirmation

Raw legacy fields remain untouched for audit/history. This module only reads
current records and derives one coherent HR-facing presentation per interview.
"""

from __future__ import annotations

from typing import Any


ASYNC_VIDEO_PROGRESS_STATES = {
    "created",
    "link_sent",
    "opened",
    "consented",
    "submitted",
    "ready_for_review",
    "reviewed",
    "expired",
    "cancelled",
}

LIVE_PROGRESS_STATES = {
    "draft",
    "invitation_pending",
    "scheduled",
    "confirmed",
    "completed",
    "no_show",
    "cancelled",
    "rescheduled",
}

SCHEDULE_STATES = {"not_applicable", "date_missing", "scheduled", "past_due"}
INVITATION_MATRIX_STATES = {
    "not_sent",
    "send_pending",
    "sent_awaiting_response",
    "delivered_confirmed",
    "delivery_failed",
    "candidate_declined",
}
CANDIDATE_CONFIRMATIONS = {"not_requested", "not_confirmed", "confirmed", "declined", "tentative"}
EVIDENCE_READINESS = {"none", "waiting", "partial", "ready", "reviewed"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _is_async_video(summary: dict[str, Any]) -> bool:
    interview_type = _lower(summary.get("interview_type"))
    source = _lower(summary.get("source"))
    return interview_type == "async_video" or source == "async_video"


def canonical_interview_type(summary: dict[str, Any]) -> str:
    """Map to one of: async_video, live_video, phone, in_person."""
    if _is_async_video(summary):
        return "async_video"
    meeting = _lower(summary.get("meeting_type"))
    if meeting in {"phone", "call", "telephone"}:
        return "phone"
    if meeting in {"in_person", "inperson", "physical", "office"}:
        return "in_person"
    return "live_video"


def _async_progress(summary: dict[str, Any], evidence: str) -> str:
    if _lower(summary.get("status")) == "cancelled":
        return "cancelled"
    if _lower(summary.get("async_status")) == "expired":
        return "expired"
    review = summary.get("video_review_status") if isinstance(summary.get("video_review_status"), dict) else {}
    state = _lower(review.get("state"))
    if state == "cancelled":
        return "cancelled"
    if canonical_feedback_state(summary).get("complete"):
        return "reviewed"
    if state == "ready_for_review":
        return "ready_for_review"
    if state in {"submitted", "processing", "summary_pending", "transcription_failed"}:
        return "submitted"
    if state in {"started", "opened", "consented", "in_progress"}:
        async_status = _lower(summary.get("async_status"))
        return "consented" if async_status == "consented" else "opened"
    if _lower(summary.get("async_status")) in {"opened", "consented", "in_progress"}:
        return _lower(summary.get("async_status"))
    if evidence in {"partial", "ready", "reviewed"}:
        return "submitted"
    if _lower(summary.get("status")) == "completed":
        return "submitted"
    if summary.get("candidate_notified") or _lower(summary.get("channel_send_status")) in {"send_accepted", "delivered"}:
        return "link_sent"
    return "created"


def _live_progress(summary: dict[str, Any]) -> str:
    status = _lower(summary.get("status"))
    if status in {"completed", "no_show", "cancelled", "rescheduled"}:
        return status
    has_datetime = bool(summary.get("scheduled_start"))
    channel = _lower(summary.get("channel_send_status"))
    invited = bool(summary.get("candidate_notified") or summary.get("calendar_invite_sent") or summary.get("candidate_invited"))
    confirmation = _lower(summary.get("candidate_confirmation"))
    if not has_datetime:
        return "invitation_pending" if invited or channel not in {"", "not_requested"} else "draft"
    if confirmation == "confirmed":
        return "confirmed"
    return "scheduled"


def _schedule_state(summary: dict[str, Any], interview_type: str) -> tuple[str, str | None]:
    raw_start = summary.get("scheduled_start")
    start = _text(raw_start)
    if interview_type == "async_video":
        # Async video may exist without a date/time; HR must never see Scheduled.
        return ("not_applicable", start or None)
    if not start:
        return ("date_missing", None)
    # Past-due is presentation-only; keep it simple and non-destructive.
    return ("scheduled", start)


def _invitation_matrix(summary: dict[str, Any], confirmation: str) -> tuple[str, str | None]:
    """Combined invitation/confirmation state with contradiction explanation."""
    channel = _lower(summary.get("channel_send_status"))
    if channel == "not_requested" and (summary.get("candidate_notified") or summary.get("calendar_invite_sent")):
        channel = "send_accepted"
    failed = bool(summary.get("failed")) or channel == "failed" or _lower(summary.get("provider_sync_status")) == "failed"
    if failed:
        return ("delivery_failed", None)
    if confirmation == "declined":
        return ("candidate_declined", None)
    sent = channel in {"send_accepted", "delivered"} or bool(summary.get("candidate_notified") or summary.get("calendar_invite_sent"))
    if confirmation == "confirmed":
        if channel == "pending":
            return ("send_pending", "Candidate confirmation is recorded but the invitation send is still pending.")
        if sent or summary.get("consent_accepted_at"):
            return ("delivered_confirmed", None if sent else "Confirmed from recorded video consent without a live invitation send.")
        return ("send_pending", "Candidate confirmation is recorded but the invitation send is still pending.")
    if channel == "pending":
        return ("send_pending", None)
    if sent:
        return ("sent_awaiting_response", None)
    return ("not_sent", None)


FEEDBACK_STATES = {"not_started", "draft", "submitted", "complete"}


def canonical_feedback_state(summary: dict[str, Any]) -> dict[str, Any]:
    """One backend-authoritative feedback state derived from real submissions/scorecard.

    Legacy fields (feedback_status, human_feedback_status, notes_status) are read
    only as hints; they never independently create HR-facing truth. Structured
    submission wins. Notes alone never complete feedback.
    """
    human = _lower(summary.get("human_feedback_status"))
    legacy = _lower(summary.get("feedback_status"))
    submission = summary.get("feedback_submission") if isinstance(summary.get("feedback_submission"), dict) else None
    submission_status = _lower((submission or {}).get("status"))
    reopened = submission_status == "reopened"
    # Reopened wins over legacy completion mirrors; a reopened scorecard is not complete.
    submitted = (submission_status == "submitted") or (
        not reopened and (human == "feedback_complete" or (not submission and legacy == "feedback_complete" and human == "feedback_complete"))
    )

    notes_present = bool(_text(summary.get("notes")))
    complete = bool(submitted and not reopened)
    if reopened:
        state = "draft"
    elif complete:
        state = "complete"
    elif submitted:
        state = "submitted"
    elif submission_status == "draft":
        state = "draft"
    elif notes_present or human == "notes_pending" or legacy == "notes_pending":
        # Notes do not equal started structured feedback; treat as not_started unless a draft exists.
        state = "not_started"
    else:
        state = "not_started"

    needs_feedback = state in {"not_started", "draft"}
    conflicting_legacy = (legacy == "feedback_complete") != complete
    return {
        "state": state,
        "label": {
            "not_started": "Feedback not started",
            "draft": "Feedback draft",
            "submitted": "Feedback submitted",
            "complete": "Feedback complete",
        }[state],
        "complete": complete,
        "submitted": bool(submitted and not reopened),
        "needs_feedback": needs_feedback,
        "notes_present": notes_present,
        "submission_id": (submission or {}).get("submission_id"),
        "submission_status": submission_status or None,
        "legacy_feedback_status": legacy or None,
        "legacy_human_feedback_status": human or None,
        "legacy_conflict": conflicting_legacy,
        "reopened": reopened,
    }


def _evidence_readiness(summary: dict[str, Any], interview_type: str) -> str:
    if interview_type != "async_video":
        return "none" if _lower(summary.get("status")) != "completed" else "ready"
    answers = summary.get("video_answers") if isinstance(summary.get("video_answers"), list) else []
    review = summary.get("video_review_status") if isinstance(summary.get("video_review_status"), dict) else {}
    if canonical_feedback_state(summary).get("complete"):
        return "reviewed"
    if _lower(review.get("state")) == "ready_for_review" or bool(review.get("summary_ready")):
        return "ready"
    if answers or int(review.get("response_count") or 0):
        return "partial"
    return "waiting"


def _next_human_action(interview_type: str, progress: str, schedule_state: str, invitation_state: str, evidence: str, feedback_complete: bool) -> str:
    if progress == "cancelled":
        return "review_next_step"
    if invitation_state == "delivery_failed":
        return "resolve_invitation"
    if interview_type == "async_video":
        if progress in {"created", "link_sent"}:
            return "resend_video_link" if invitation_state in {"not_sent", "delivery_failed"} else "wait_for_video_response"
        if progress in {"opened", "consented"}:
            return "wait_for_video_response"
        if progress in {"submitted", "ready_for_review"}:
            return "review_video_interview" if evidence in {"partial", "ready"} else "wait_for_video_summary"
        if progress == "reviewed":
            return "decide_application"
        if progress == "expired":
            return "reopen_invitation"
        return "review_video_interview"
    # live/phone/in-person
    if progress == "draft":
        return "schedule_interview"
    if progress == "invitation_pending":
        return "send_invitation"
    if schedule_state == "date_missing":
        return "set_interview_datetime"
    if progress in {"scheduled", "confirmed", "rescheduled"}:
        return "conduct_interview"
    if progress == "completed":
        return "decide_application" if feedback_complete else "record_feedback"
    if progress == "no_show":
        return "review_next_step"
    return "review_next_step"


def _allowed_actions(
    interview_type: str,
    progress: str,
    evidence: str,
    feedback_complete: bool,
    base_actions: list[str] | None,
    can_manage: bool,
    *,
    schedule_state: str = "not_applicable",
    invitation_state: str = "not_sent",
    assignment_assigned: bool = True,
    feedback: dict[str, Any] | None = None,
) -> list[str]:
    """Wave 2 canonical allowed actions. Backend-authoritative; never grants permissions.

    Action vocabulary (existing mutation paths only):
      send_video_invitation, retry_video_invitation, resend_video_link,
      cancel_interview, mark_completed, mark_no_show, write_notes,
      review_video, open_candidate, set_interview_datetime, assign_interviewer,
      reschedule_interview, send_interview_invitation, mark_reviewed (alias of
      mark_completed for async reviewed evidence), reopen_invitation (expired).
    """
    if not can_manage:
        return []
    actions: list[str] = []

    def _add(name: str) -> None:
        if name not in actions:
            actions.append(name)

    has_answers = evidence in {"partial", "ready", "reviewed"}
    evidence_ready = evidence in {"partial", "ready"}
    feedback_state = _lower((feedback or {}).get("state")) if feedback else ""

    if interview_type == "async_video":
        if progress == "created":
            _add("send_video_invitation")
        if invitation_state == "delivery_failed":
            _add("retry_video_invitation")
        if progress in {"link_sent", "opened", "consented"}:
            # allow HR to nudge/resend link when candidate has not submitted yet
            _add("resend_video_link")
        if progress in {"submitted", "ready_for_review"} and evidence_ready:
            _add("review_video")
            if not feedback_complete:
                _add("write_notes")
                _add("mark_reviewed")
        elif progress in {"submitted", "ready_for_review"} and not evidence_ready:
            # summary still processing; notes allowed but no review completion
            _add("write_notes")
        if progress == "reviewed":
            if feedback_state in {"submitted", "complete"}:
                _add("view_feedback")
            _add("open_candidate")
        if progress == "expired":
            _add("reopen_invitation")
            _add("resend_video_link")
        if progress not in {"cancelled", "reviewed"}:
            _add("cancel_interview")
        if progress in {"opened", "consented"}:
            _add("open_candidate")
    else:
        # live video / phone / in-person
        if progress in {"draft", "invitation_pending"} or schedule_state == "date_missing":
            _add("set_interview_datetime")
            if not assignment_assigned:
                _add("assign_interviewer")
            if progress == "invitation_pending":
                _add("send_interview_invitation")
            _add("cancel_interview")
        elif progress in {"scheduled", "confirmed", "rescheduled"}:
            _add("reschedule_interview")
            _add("send_interview_invitation")
            _add("mark_completed")
            _add("mark_no_show")
            _add("cancel_interview")
            if not assignment_assigned:
                _add("assign_interviewer")
        elif progress == "completed":
            if feedback_state in {"submitted", "complete"}:
                _add("view_feedback")
            else:
                _add("write_notes")
            _add("open_candidate")
        elif progress in {"cancelled", "no_show"}:
            _add("reschedule_interview")
            _add("open_candidate")

    # Never allow feedback completion or review completion without required evidence for async.
    if interview_type == "async_video" and not has_answers:
        for name in ("mark_reviewed", "mark_completed", "review_video"):
            while name in actions:
                actions.remove(name)

    # Keep legacy backend actions only if still valid; always include open_candidate for HR context.
    base = [str(a) for a in (base_actions or [])]
    if "open_candidate" in base and "open_candidate" not in actions:
        actions.append("open_candidate")

    return actions


def interviewer_assignment(summary: dict[str, Any], cur: Any | None = None) -> dict[str, Any]:
    assignees = summary.get("interviewer_assignments") or summary.get("assignees") or []
    names = [a for a in assignees if isinstance(a, str) and a.strip()]
    return {
        "assigned": bool(names),
        "count": len(names),
        "names": names[:4],
        "label": ", ".join(names[:3]) if names else None,
    }


def build_interview_presentation(
    summary: dict[str, Any],
    *,
    can_manage: bool,
    legacy_next_action: str | None = None,
    assignments: list[str] | None = None,
) -> dict[str, Any]:
    """One backend presentation object per interview. Frontend must not re-derive."""
    interview_type = canonical_interview_type(summary)
    confirmation = _lower(summary.get("candidate_confirmation")) or "not_requested"
    if confirmation not in CANDIDATE_CONFIRMATIONS:
        confirmation = "not_requested"
    feedback = canonical_feedback_state(summary)
    feedback_complete = bool(feedback.get("complete"))
    evidence = _evidence_readiness(summary, interview_type)
    progress = _async_progress(summary, evidence) if interview_type == "async_video" else _live_progress(summary)
    schedule_state, date_time = _schedule_state(summary, interview_type)
    invitation_state, invitation_note = _invitation_matrix(summary, confirmation)
    assignment = {
        "assigned": bool(assignments),
        "count": len(assignments or []),
        "names": (assignments or [])[:4],
        "label": ", ".join((assignments or [])[:3]) if assignments else None,
    }
    next_action = _next_human_action(interview_type, progress, schedule_state, invitation_state, evidence, feedback_complete)
    base_actions = list(summary.get("allowed_actions") or [])
    allowed_actions = _allowed_actions(
        interview_type,
        progress,
        evidence,
        feedback_complete,
        base_actions,
        can_manage,
        feedback=feedback,
        schedule_state=schedule_state,
        invitation_state=invitation_state,
        assignment_assigned=bool(assignment.get("assigned")),
    )

    status_label = {
        "async_video": {
            "created": "Created",
            "link_sent": "Link sent",
            "opened": "Opened",
            "consented": "Consent recorded",
            "submitted": "Submitted",
            "ready_for_review": "Ready for review",
            "reviewed": "Reviewed",
            "expired": "Expired",
            "cancelled": "Cancelled",
        }.get(progress, progress.replace("_", " ")),
    }.get(interview_type)
    if not status_label:
        status_label = {
            "draft": "Draft",
            "invitation_pending": "Invitation pending",
            "scheduled": "Scheduled",
            "confirmed": "Confirmed",
            "completed": "Completed",
            "no_show": "No-show",
            "cancelled": "Cancelled",
            "rescheduled": "Rescheduled",
        }.get(progress, progress.replace("_", " "))

    type_label = {
        "async_video": "Recorded video interview",
        "live_video": "Live video interview",
        "phone": "Phone interview",
        "in_person": "In-person interview",
    }.get(interview_type, "Interview")

    return {
        "version": "interview_presentation_v1",
        "interview_type": interview_type,
        "interview_type_label": type_label,
        "progress_state": progress,
        "progress_label": status_label,
        "schedule_state": schedule_state,
        "date_time": date_time,
        "invitation_state": invitation_state,
        "invitation_note": invitation_note,
        "candidate_confirmation": confirmation,
        "evidence_readiness": evidence,
        "feedback": feedback,
        "feedback_complete": feedback_complete,
        "interviewer_assignment": assignment,
        "next_human_action": next_action,
        "next_human_action_legacy": legacy_next_action,
        "allowed_actions": allowed_actions,
        "display": {
            "status_label": status_label,
            "type_label": type_label,
            "show_datetime": schedule_state == "scheduled",
            "is_async": interview_type == "async_video",
        },
    }
