"""Shared document type map for Phase 7C / Kuwait first-client foundation.

Canonical Kuwait residence type is `residence` (not Saudi iqama).
Historical `residency_iqama` / `residency` remain readable via compatibility —
no silent destructive merge of stored rows.
"""

from __future__ import annotations

CANONICAL_RESIDENCE = "residence"
LEGACY_RESIDENCE_TYPES = frozenset({"residency_iqama", "residency"})

ONBOARDING_DOCUMENT_ITEMS = {
    "civil_id",
    "passport",
    "personal_photo",
    "residence",  # canonical (was residency_iqama)
    "residency_iqama",  # historical compatibility only
    "work_permit",
    "employment_contract",
    "offer_letter",
    "bank_details",
}

# Upload dual-write allowlist (app.record_employee_document_receipt).
# Residence + work_permit included for Article 18 expatriate handoff.
UPLOAD_SYNCED_COMPLIANCE_TYPES = {
    "civil_id",
    "passport",
    "medical",
    "education_cert",
    "residence",
    "work_permit",
}

COMPLIANCE_CANONICAL_TYPES = {
    "civil_id",
    "passport",
    "residence",
    "work_permit",
    "medical",
    "education_cert",
}

# Exact item_id → compliance type. New writes use residence; legacy alias maps
# explicitly for dual-write without renaming historical rows in place.
ITEM_TO_COMPLIANCE_TYPE = {
    "civil_id": "civil_id",
    "passport": "passport",
    "work_permit": "work_permit",
    "medical": "medical",
    "education_cert": "education_cert",
    "residence": "residence",
    # Explicit compat mapping (not a silent merge of stored content):
    "residency_iqama": "residence",
    "residency": "residence",
}

AMBIGUOUS_TYPE_GROUPS = {
    "medical_family": ("medical", "medical_check"),
    # Flag-only group for operator review tooling; dual-write uses ITEM_TO_COMPLIANCE_TYPE.
    "residency_family": ("residence", "residency", "residency_iqama"),
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


def normalize_kuwait_document_type(document_type: str | None) -> str:
    raw = str(document_type or "").strip().lower()
    if raw in LEGACY_RESIDENCE_TYPES or raw == CANONICAL_RESIDENCE:
        return CANONICAL_RESIDENCE
    return raw
