"""Update channel gap registry after Wave 2 wiring."""

from __future__ import annotations

from typing import Any

CHANNELS = (
    "whatsapp_onboarding",
    "ess_onboarding",
    "hr_document_hub",
    "ess_renew",
    "compliance_backfill",
    "email_inbound",
)


def expected_channel_flow() -> dict[str, Any]:
    return {
        "flow": [
            "upload_or_email_attachment",
            "tenant_and_employee_matching",
            "classify_or_verify_expected_item",
            "document_envelope@1",
            "shared_document_processor",
            "non_authoritative_field_proposal",
            "hr_confirmation_or_correction",
            "employee_and_or_compliance_record",
            "expiry_and_renewal_tracking_for_hr_confirmed_dates_only",
        ],
        "identity_types": "delegate_to_identity_document_extraction",
        "contract_education_types": "kuwait_gcc_document_intelligence",
        "no_separate_onboarding_vs_compliance_extractors": True,
        "no_separate_email_extractor": True,
        "no_gpt": True,
        "no_cv_v2": True,
        "uncertain_match": "durable_review_queue_no_auto_attach",
    }


def channel_gap_registry() -> list[dict[str, Any]]:
    """Wave 2 status of previously audited gaps."""

    return [
        {
            "id": "hub_skips_extraction",
            "channel": "hr_document_hub",
            "wave2_status": "closed",
            "fix": "shared_channel_extraction via extract_compliance_document_metadata",
        },
        {
            "id": "ess_renew_skips_extraction",
            "channel": "ess_renew",
            "wave2_status": "closed",
            "fix": "shared_channel_extraction",
        },
        {
            "id": "ess_onboarding_skips_extraction",
            "channel": "ess_onboarding",
            "wave2_status": "closed",
            "fix": "shared_channel_extraction",
        },
        {
            "id": "whatsapp_identity_only_extract",
            "channel": "whatsapp_onboarding",
            "wave2_status": "closed",
            "fix": "education_cert + employment_contract structured via shared path",
        },
        {
            "id": "backfill_identity_only",
            "channel": "compliance_backfill",
            "wave2_status": "closed",
            "fix": "allowlist includes education_cert, employment_contract, residence, contract_amendment",
        },
        {
            "id": "residence_alias_split",
            "channel": "all",
            "wave2_status": "closed",
            "fix": "canonical residence with preserved aliases residency/residency_iqama",
        },
        {
            "id": "medical_vs_medical_check",
            "channel": "onboarding_template",
            "wave2_status": "closed",
            "fix": "canonical medical; medical_check/medical_fitness preserved as aliases",
        },
        {
            "id": "education_cert_obsolete_checklist",
            "channel": "whatsapp_onboarding",
            "wave2_status": "closed_compat",
            "fix": "canonical education_cert; checklist obsolescence unchanged non-destructively",
        },
        {
            "id": "route_matrix_stale_identity_label",
            "channel": "foundation",
            "wave2_status": "closed",
            "fix": "ROUTE_MATRIX labels updated to Mistral identity + kuwait_gcc shared processor",
        },
        {
            "id": "contract_processor_label_only",
            "channel": "foundation",
            "wave2_status": "closed",
            "fix": "structuring=kuwait_gcc_document_intelligence live",
        },
        {
            "id": "email_employee_doc_intake_missing",
            "channel": "email_inbound",
            "wave2_status": "closed",
            "fix": "email_intake.process_email_attachment uses shared processor + durable review queue",
        },
        {
            "id": "ocr_expiry_drove_reminders",
            "channel": "compliance_scan",
            "wave2_status": "closed",
            "fix": "dual_write keeps OCR dates in proposal; reminders require renewal_status=reviewed",
        },
    ]
