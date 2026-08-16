"""Canonical live-application authority for candidate communication.

Held Talent Pool rows (`needs_role`, `import_review`, `import_archived`) and
restricted / deletion-pending governance must fail closed before any outbound
provider call, delivery event, invitation token, lifecycle event, retry, or
queued outbound work.

Live Job applications continue under existing permissions, tenant scope, Job
state, lifecycle, channel entitlement, and template/provider rules.

This module is pure: no DB, no providers, no side effects.
"""

from __future__ import annotations

from typing import Any

HELD_IMPORT_STATUSES = ("needs_role", "import_review", "import_archived")
PRODUCTION_DATA_SOURCE = "production"
NON_PRODUCTION_DATA_SOURCES = {"smoke_test", "demo", "test"}

ERROR_HELD = "held_record_communication_forbidden"
ERROR_RESTRICTED = "restricted_record_communication_forbidden"
ERROR_NOT_LIVE = "candidate_communication_requires_live_application"
ERROR_MISSING = "candidate_communication_context_required"
ERROR_TENANT = "candidate_communication_tenant_mismatch"

COMMUNICATION_KINDS = frozenset(
    {
        "notify",
        "email",
        "whatsapp",
        "sms",
        "assessment",
        "assessment_resend",
        "interview_invite",
        "video_interview",
        "screening",
        "cv_validation",
        "offer",
        "calendar_invite",
        "bulk",
        "assistant",
        "generic",
    }
)

DELETION_PENDING_STATES = frozenset({"requested", "in_progress", "pending", "completed"})
RESTRICTION_ACTIVE_STATES = frozenset({"restricted", "active", "true", "1"})
ARCHIVE_ACTIVE_STATES = frozenset({"archived", "active", "true", "1"})


class CandidateCommunicationAuthorityError(Exception):
    """Fail-closed domain error for held / non-live candidate communication."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        reason: str | None = None,
        extra: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.reason = reason or code
        self.extra = extra or {}

    def as_detail(self) -> dict[str, Any]:
        detail = {
            "error": self.code,
            "message": self.message,
            "reason": self.reason,
            "authority": "candidate_communication_live_application",
        }
        detail.update(self.extra)
        return detail

    def as_result(self) -> dict[str, Any]:
        return {
            "ok": False,
            "success": False,
            "status": "failed",
            "error": self.code,
            "error_code": self.code,
            "reason": self.reason,
            "message": self.message,
            "safe_user_message": self.message,
            "authority": "candidate_communication_live_application",
            **self.extra,
        }


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def application_data_source(application: dict[str, Any] | None) -> str:
    row = application if isinstance(application, dict) else {}
    raw = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
    source = _norm_lower(row.get("data_source") or raw.get("data_source") or PRODUCTION_DATA_SOURCE)
    return source or PRODUCTION_DATA_SOURCE


def governance_is_restricted(gov: dict[str, Any] | None) -> bool:
    if not isinstance(gov, dict):
        return False
    state = _norm_lower(gov.get("restriction_state"))
    deletion = _norm_lower(gov.get("deletion_request_state"))
    return state in RESTRICTION_ACTIVE_STATES or deletion in DELETION_PENDING_STATES


def governance_is_archived(gov: dict[str, Any] | None, status: Any) -> bool:
    if _norm_lower(status) == "import_archived":
        return True
    if not isinstance(gov, dict):
        return False
    return _norm_lower(gov.get("archive_state")) in ARCHIVE_ACTIVE_STATES


def is_test_identity(application: dict[str, Any] | None) -> bool:
    row = application if isinstance(application, dict) else {}
    raw = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
    phone = _norm(row.get("phone"))
    app_key = _norm(row.get("app_key"))
    name = _norm(row.get("candidate_name") or raw.get("candidate_name") or raw.get("name"))
    if phone.startswith("9655555"):
        return True
    if "TEST" in app_key.upper():
        return True
    if name.lower().startswith("test "):
        return True
    return False


def is_held_status(status: Any) -> bool:
    return _norm_lower(status) in HELD_IMPORT_STATUSES


def is_canonical_live_application(
    application: dict[str, Any] | None,
    *,
    governance: dict[str, Any] | None = None,
    expected_company_code: str | None = None,
) -> bool:
    decision = evaluate_candidate_communication_authority(
        application,
        governance=governance,
        expected_company_code=expected_company_code,
    )
    return bool(decision.get("allowed"))


def evaluate_candidate_communication_authority(
    application: dict[str, Any] | None,
    *,
    governance: dict[str, Any] | None = None,
    expected_company_code: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    """Return an allow/deny decision without raising."""
    del kind  # kinds share one live-application predicate
    if not isinstance(application, dict) or not application:
        return {
            "allowed": False,
            "code": ERROR_MISSING,
            "reason": "missing_application",
            "message": "A live Job application is required before contacting the candidate.",
            "status_code": 422,
        }

    app_key = _norm(application.get("app_key"))
    company = _norm(application.get("company_code")).upper()
    expected = _norm(expected_company_code).upper()
    if not app_key or not company:
        return {
            "allowed": False,
            "code": ERROR_MISSING,
            "reason": "missing_app_or_tenant",
            "message": "A tenant-bound live Job application is required before contacting the candidate.",
            "status_code": 422,
            "app_key": app_key or None,
            "company_code": company or None,
        }
    if expected and company != expected:
        return {
            "allowed": False,
            "code": ERROR_TENANT,
            "reason": "tenant_mismatch",
            "message": "Candidate communication is limited to the authenticated tenant.",
            "status_code": 403,
            "app_key": app_key,
            "company_code": company,
            "expected_company_code": expected,
        }

    status = _norm_lower(application.get("status"))
    if is_held_status(status):
        return {
            "allowed": False,
            "code": ERROR_HELD,
            "reason": f"held_status:{status}",
            "message": (
                "Talent Pool held records cannot receive outreach, notifications, "
                "assessments, or interview invitations until linked to a live Job application."
            ),
            "status_code": 409,
            "app_key": app_key,
            "company_code": company,
            "status": status,
        }

    gov = governance if isinstance(governance, dict) else None
    if governance_is_restricted(gov):
        return {
            "allowed": False,
            "code": ERROR_RESTRICTED,
            "reason": "restricted_or_deletion_pending",
            "message": (
                "Restricted or deletion-pending candidate records cannot receive "
                "outreach or candidate communication."
            ),
            "status_code": 409,
            "app_key": app_key,
            "company_code": company,
            "status": status,
        }

    if governance_is_archived(gov, status) and status != "hired":
        # import_archived already caught above; governance archive on non-live rows
        return {
            "allowed": False,
            "code": ERROR_RESTRICTED,
            "reason": "archived_record",
            "message": "Archived candidate records cannot receive outreach or candidate communication.",
            "status_code": 409,
            "app_key": app_key,
            "company_code": company,
            "status": status,
        }

    data_source = application_data_source(application)
    if data_source in NON_PRODUCTION_DATA_SOURCES:
        return {
            "allowed": False,
            "code": ERROR_NOT_LIVE,
            "reason": f"non_production_data_source:{data_source}",
            "message": "Only production live Job applications can receive candidate communication.",
            "status_code": 409,
            "app_key": app_key,
            "company_code": company,
            "data_source": data_source,
        }

    if is_test_identity(application):
        return {
            "allowed": False,
            "code": ERROR_NOT_LIVE,
            "reason": "test_identity",
            "message": "Test or synthetic application identities cannot receive candidate communication.",
            "status_code": 409,
            "app_key": app_key,
            "company_code": company,
        }

    return {
        "allowed": True,
        "code": None,
        "reason": "live_application",
        "message": "ok",
        "status_code": 200,
        "app_key": app_key,
        "company_code": company,
        "status": status,
        "data_source": data_source,
    }


def assert_candidate_communication_allowed(
    application: dict[str, Any] | None,
    *,
    governance: dict[str, Any] | None = None,
    expected_company_code: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    decision = evaluate_candidate_communication_authority(
        application,
        governance=governance,
        expected_company_code=expected_company_code,
        kind=kind,
    )
    if decision.get("allowed"):
        return decision
    raise CandidateCommunicationAuthorityError(
        str(decision.get("code") or ERROR_NOT_LIVE),
        str(decision.get("message") or "Candidate communication is not allowed."),
        status_code=int(decision.get("status_code") or 409),
        reason=str(decision.get("reason") or "denied"),
        extra={
            key: value
            for key, value in decision.items()
            if key not in {"allowed", "code", "message", "reason", "status_code"}
        },
    )


def filter_live_applications_for_communication(
    applications: list[dict[str, Any]],
    *,
    governance_by_app_key: dict[str, dict[str, Any]] | None = None,
    expected_company_code: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    """Split a bulk selection into allowed live rows and denied held/restricted rows."""
    gov_map = governance_by_app_key or {}
    allowed: list[dict[str, Any]] = []
    denied: list[dict[str, Any]] = []
    for app in applications:
        if not isinstance(app, dict):
            continue
        app_key = _norm(app.get("app_key"))
        decision = evaluate_candidate_communication_authority(
            app,
            governance=gov_map.get(app_key),
            expected_company_code=expected_company_code,
            kind=kind,
        )
        entry = {"application": app, "decision": decision, "app_key": app_key}
        if decision.get("allowed"):
            allowed.append(entry)
        else:
            denied.append(entry)
    return {
        "allowed": allowed,
        "denied": denied,
        "allowed_count": len(allowed),
        "denied_count": len(denied),
        "total_count": len(allowed) + len(denied),
    }
