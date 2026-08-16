"""Phase 0 frozen scenario catalog for Unified Inbound CV Pipeline.

These fixtures document current production contracts. They do not authorize
behavior changes. Each case names the authoritative channel path and the
expected fail-closed / held outcome before Phase 1 refactoring.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


PHASE0_VERSION = "unified-inbound-cv-phase0-v1"
TENANT = "WATHEFNI"

# Held Talent Pool membership statuses (Option B).
HELD_STATUSES = ("needs_role", "import_review", "import_archived")
INTAKE_REVIEW_STATUSES = ("needs_role", "import_review")
IDENTITY_OUTCOMES = (
    "safe_exact_reuse",
    "new_candidate",
    "possible_match",
    "conflict",
)
ACCEPTED_IDENTITY_OUTCOMES = ("safe_exact_reuse", "new_candidate")
EMAIL_SAFETY_STATES = (
    "scan_pending",
    "clean",
    "quarantined",
    "malware_suspicious",
    "unsupported_type",
    "mime_mismatch",
    "password_protected",
    "too_large",
    "invalid_corrupt",
)
EMAIL_SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".png", ".jpg", ".jpeg", ".webp")

THREE_CURRENT_RISKS = (
    {
        "id": "single_item_promotion_sql",
        "title": "Single-item promotion SQL parameter and tenant-predicate defect",
        "authority": "app.py::dashboard_prehire_import_assign",
        "expected_phase0": "reproduced_as_current_defect",
        "wave1_status": "remediated",
    },
    {
        "id": "manual_auto_admit_default",
        "title": "Manual explicit-role auto-admit fail-closed when setting unset",
        "authority": "app.py::company_auto_admit_imports + register_imported_cv",
        "expected_phase0": "reproduced_as_current_contract",
        "wave1_status": "remediated_fail_closed",
    },
    {
        "id": "ck_sibling_over_denial",
        "title": "Candidate Knowledge sibling over-denial across held+live apps",
        "authority": "candidate_knowledge_authority._anchor_actionability",
        "expected_phase0": "reproduced_as_current_contract",
        "wave1_status": "remediated_anchor_scoped",
    },
)


SCENARIOS: dict[str, dict[str, Any]] = {
    "whatsapp_cv_only_unsolicited": {
        "channel": "whatsapp",
        "inputs": {"media": "pdf", "apply_code": None, "job_context": None},
        "expected": {
            "creates_candidate": False,
            "creates_application": False,
            "creates_pending_media": True,
            "status": None,
            "candidate_message": "cv_held_needs_role",
            "ranking_eligible": False,
            "hr_talent_pool_visible": False,
        },
    },
    "whatsapp_cv_then_apply_code": {
        "channel": "whatsapp",
        "inputs": {"order": ["cv", "apply_code"]},
        "expected": {
            "cv_first": "hold_pending_media",
            "apply_code_next": "job_context_preview_without_consuming_cv",
            "application_requires": "explicit_ready_to_apply_or_qualifying_cv_after_preview",
            "ranking_before_binding": False,
        },
    },
    "whatsapp_apply_code_then_cv": {
        "channel": "whatsapp",
        "inputs": {"order": ["apply_code", "cv"]},
        "expected": {
            "after_preview_cv_may": "convert_job_context_to_application(trigger=qualifying_cv)",
            "requires_preview_sent_at": True,
            "ranking_before_convert": False,
        },
    },
    "email_identical_cv_replay": {
        "channel": "email",
        "inputs": {"same_provider_message_id": True, "same_bytes": True},
        "expected": {
            "provider_idempotent": True,
            "no_duplicate_ownership": True,
            "downstream_mutation": False,
        },
    },
    "email_changed_cv_same_sender": {
        "channel": "email",
        "inputs": {"same_sender": True, "different_bytes": True},
        "expected": {
            "sender_is_not_person_key": True,
            "identity_from_cv": True,
            "may_create_new_or_reuse_by_exact_keys": True,
        },
    },
    "email_multiple_attachments": {
        "channel": "email",
        "inputs": {"attachments": 2},
        "expected": {
            "one_intake_document_per_attachment": True,
            "no_assumption_same_person": True,
        },
    },
    "email_unsupported_corrupt_password_malware": {
        "channel": "email",
        "inputs": {
            "unsupported": ".doc",
            "corrupt_pdf": True,
            "password_pdf": True,
            "malware": True,
        },
        "expected": {
            "unsupported_type": True,
            "invalid_corrupt": True,
            "password_protected": True,
            "malware_suspicious_before_ocr": True,
            "no_candidate_on_nonclean": True,
        },
    },
    "email_possible_match_and_conflict": {
        "channel": "email",
        "inputs": {"weak_name": True, "conflicting_strong_keys": True},
        "expected": {
            "possible_match_no_ownership": True,
            "conflict_no_ownership": True,
            "accepted_outcomes_only": list(ACCEPTED_IDENTITY_OUTCOMES),
        },
    },
    "manual_auto_admit_matrix": {
        "channel": "manual",
        "inputs": {
            "explicit_position_code": True,
            "setting_values": [None, False, True],
        },
        "expected": {
            "unset_defaults_true": True,
            "false_holds_import_review": True,
            "true_auto_admits_review_pending": True,
            "governed_email_never_auto_admits": True,
        },
    },
    "mixed_held_live_siblings": {
        "channel": "candidate_knowledge",
        "inputs": {
            "phone": "96550001111",
            "apps": [
                {"app_key": "live-app", "status": "ready_for_review"},
                {"app_key": "held-app", "status": "needs_role"},
            ],
        },
        "expected": {
            "subject_contact_allowed": False,
            "subject_lifecycle_allowed": False,
            "subject_job_ranking_allowed": False,
            "row_level_ranking_excludes_held_only": True,
        },
    },
    "single_item_vs_bulk_link_to_job": {
        "channel": "dashboard",
        "inputs": {"actions": ["assign_single", "assign_bulk"]},
        "expected": {
            "bulk_update_tenant_scoped": True,
            "single_item_sql_placeholder_mismatch": True,
            "link_to_job_ui_stubbed": True,
            "canonical_bridge": "intake_admit",
        },
    },
    "zero_downstream_without_verified_job": {
        "channel": "cross_channel",
        "inputs": {"verified_job_binding": False},
        "expected": {
            "ranking_excluded_for_held": True,
            "communication_blocked_for_held": True,
            "lifecycle_requires_intake_admit": True,
            "ck_held_readable_not_actionable": True,
        },
    },
}


def all_scenarios() -> dict[str, dict[str, Any]]:
    return {key: deepcopy(value) for key, value in SCENARIOS.items()}


def risk_catalog() -> tuple[dict[str, Any], ...]:
    return tuple(deepcopy(item) for item in THREE_CURRENT_RISKS)
