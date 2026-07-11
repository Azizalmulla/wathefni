"""Shared document type map for Phase 7C / 7C.2 reconciliation.

No silent alias merging. Ambiguous families are flag-only.
"""

from __future__ import annotations

ONBOARDING_DOCUMENT_ITEMS = {
    "civil_id",
    "passport",
    "personal_photo",
    "residency_iqama",
    "work_permit",
    "employment_contract",
    "offer_letter",
    "bank_details",
}

# Upload dual-write allowlist (app.record_employee_document_receipt).
UPLOAD_SYNCED_COMPLIANCE_TYPES = {"civil_id", "passport", "medical", "education_cert"}

COMPLIANCE_CANONICAL_TYPES = {
    "civil_id",
    "passport",
    "residency",
    "work_permit",
    "medical",
    "education_cert",
}

# Exact item_id → compliance type when reconciling (no residency_iqama→residency).
ITEM_TO_COMPLIANCE_TYPE = {
    "civil_id": "civil_id",
    "passport": "passport",
    "work_permit": "work_permit",
    "medical": "medical",
    "education_cert": "education_cert",
}

AMBIGUOUS_TYPE_GROUPS = {
    "medical_family": ("medical", "medical_check"),
    "residency_family": ("residency", "residency_iqama"),
    "education_family": ("education_cert", "education", "certificate"),
}

ONBOARDING_SOFT_EXPIRY_TASKS = {
    "civil_id_expiry",
    "passport_expiry",
    "residency_expiry",
    "work_permit_expiry",
}

EMPLOYEE_FILE_KINDS = ("onboarding_document", "compliance_document", "employee_document")

RECEIVED_LIKE = {"received", "submitted", "complete", "completed", "done", "uploaded"}
PENDING_LIKE = {"pending", "missing", "requested", "awaiting", ""}
COMPLIANCE_ACTIVE_LIKE = RECEIVED_LIKE | {"valid", "expiring_soon", "needs_review", "stored"}

# Closed skip / manual vocabulary (Phase 7C.2).
SKIP_COMPLIANCE_ORPHAN_NO_FILE = "skip_compliance_orphan_no_file"
SKIP_NO_SUPPORTED_FILE = "no_supported_file"
SKIP_EXPIRY_OLDER = "expiry_older_than_existing"
SKIP_EXPIRY_CANDIDATE_NULL = "expiry_candidate_null"
SKIP_NULL_EXPIRY_NO_SOURCE = "null_expiry_no_source"
SKIP_NEEDS_OPERATOR_MAP = "needs_operator_map"
SKIP_MANUAL_UNSUPPORTED = "manual_only_unsupported_class"
SKIP_COMPANY_MISMATCH = "company_mismatch"
SKIP_TENANT_MISMATCH = "tenant_mismatch"
SKIP_ORPHAN_EMPLOYEE = "orphan_employee_key"
SKIP_DUPLICATE_ROWS = "duplicate_rows"
SKIP_ONBOARDING_MISSING = "onboarding_item_missing"
SKIP_TYPE_NOT_IN_MAP = "type_not_in_reconcile_map"
SKIP_ALREADY_CONSISTENT = "already_consistent"
SKIP_APPLY_DISABLED = "apply_disabled"
