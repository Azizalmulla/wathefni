"""Typed failures for Candidate Knowledge Phase 1."""

from __future__ import annotations

from typing import Any


class CandidateKnowledgeError(Exception):
    """Fail-closed Candidate Knowledge error. Never leaks cross-tenant existence."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        reason_codes: tuple[str, ...] | list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)
        self.reason_codes = tuple(str(item) for item in (reason_codes or (self.code,)))
        self.extra = dict(extra or {})

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "ok": False,
            "error": self.code,
            "error_code": self.code,
            "message": self.message,
            "reason_codes": list(self.reason_codes),
            "authority": "candidate_knowledge_v1",
        }
        # Never attach existence hints for other tenants.
        safe_extra = {
            key: value
            for key, value in self.extra.items()
            if key not in {"exists", "found", "other_tenant", "foreign_app_key"}
        }
        payload.update(safe_extra)
        return payload


ERROR_TENANT_SCOPE_REQUIRED = "tenant_scope_required"
ERROR_ACTOR_REQUIRED = "actor_required"
ERROR_BACKEND_CURRENT_REQUIRED = "backend_current_permission_required"
ERROR_PERMISSION_SUBJECT_MISMATCH = "permission_subject_mismatch"
ERROR_PERMISSION_DENIED = "permission_denied"
ERROR_MODULE_DISABLED = "module_disabled"
ERROR_INVALID_CANDIDATE_REF = "invalid_candidate_ref"
ERROR_CANDIDATE_NOT_FOUND = "candidate_not_found"
ERROR_CANDIDATE_AMBIGUOUS = "candidate_ambiguous"
ERROR_CANDIDATE_RESTRICTED = "candidate_restricted"
ERROR_SOURCE_READER_BLOCKED = "source_reader_blocked"
ERROR_NAME_ONLY_INVALID = "name_only_invalid"
ERROR_INDEX_NOT_READY = "index_not_ready"
ERROR_RETRIEVAL_DEGRADED = "retrieval_degraded"
ERROR_INVALID_COMPARISON_CONTEXT = "invalid_comparison_context"
ERROR_SECTION_NOT_AUTHORIZED = "section_not_authorized"
ERROR_IDENTITY_REVIEW_OPEN = "identity_review_open"
ERROR_AUDIT_WRITE_FAILED = "audit_write_failed"
ERROR_SHADOW_TOOLS_DISABLED = "shadow_tools_disabled"
ERROR_CANONICAL_CV_UNAVAILABLE = "canonical_cv_unavailable"
ERROR_CANONICAL_VERSION_CONFLICT = "canonical_version_conflict"
