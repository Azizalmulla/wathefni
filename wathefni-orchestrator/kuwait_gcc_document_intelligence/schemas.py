"""Shared document-class schemas — country-agnostic; Kuwait profile supplies authorities."""

from __future__ import annotations

from typing import Any

# Types already owned by identity_document_extraction — never re-implemented here.
IDENTITY_DELEGATE_TYPES = frozenset(
    {"civil_id", "passport", "residency", "residence", "work_permit", "medical"}
)

# Types this module extracts (or will extract) via shared Mistral path.
STRUCTURING_TYPES = frozenset(
    {
        "employment_contract",
        "contract_amendment",
        "education_cert",
        "commercial_licence",
        "authorised_signature",
        "medical_fitness",  # alias family with medical when not identity path
        "bank_certificate",
        "iban_letter",
    }
)

# All types that must share one channel-agnostic contract across onboarding + Hub/ESS.
SHARED_CHANNEL_TYPES = IDENTITY_DELEGATE_TYPES | STRUCTURING_TYPES | frozenset(
    {"offer_letter", "personal_photo", "pifss_statement", "visa", "entry_visa"}
)

STORAGE_ONLY_TYPES = frozenset(
    {
        "offer_letter",  # generated or upload evidence; never OCR generated offers
        "personal_photo",
        "police_certificate",
        "police_clearance",
        "blood_type",
        "blood_test",
        "lease",
        "lease_contract",
        "fingerprint_notice",
    }
)

GENERATED_ONLY_TYPES = frozenset({"generated_offer", "payslip", "payroll_mirror", "pifss_worksheet"})

EXTERNAL_AUTHORITY_MIRRORS = frozenset(
    {
        "commercial_licence_text",  # legal_entities.licence_no / CR
        "pam_employer_file_no",
        "authorised_signatory_name",
        "pifss_payroll_worksheet",
    }
)

DOCUMENT_CLASSES: dict[str, dict[str, Any]] = {
    "civil_id": {
        "processor": "identity_delegate",
        "default_authority": "PACI",
        "channels": ["whatsapp_onboarding", "ess_onboarding", "hr_document_hub", "ess_renew"],
    },
    "passport": {
        "processor": "identity_delegate",
        "default_authority": "MOI",
        "channels": ["whatsapp_onboarding", "ess_onboarding", "hr_document_hub", "ess_renew"],
    },
    "residence": {
        "processor": "identity_delegate",
        "aliases": ["residency", "residency_iqama"],
        "default_authority": "MOI",
        "channels": ["whatsapp_onboarding", "ess_onboarding", "hr_document_hub", "ess_renew"],
    },
    "work_permit": {
        "processor": "identity_delegate",
        "default_authority": "PAM",
        "channels": ["whatsapp_onboarding", "ess_onboarding", "hr_document_hub", "ess_renew"],
    },
    "medical": {
        "processor": "identity_delegate",
        "default_authority": "MOH",
        "channels": ["whatsapp_onboarding", "ess_onboarding", "hr_document_hub", "ess_renew"],
    },
    "education_cert": {
        "processor": "mistral_document_ai",
        "default_authority": "EMPLOYER",
        "channels": ["whatsapp_onboarding", "ess_onboarding", "hr_document_hub", "ess_renew"],
    },
    "employment_contract": {
        "processor": "mistral_document_ai",
        "default_authority": "EMPLOYER",
        "channels": ["whatsapp_onboarding", "ess_onboarding", "hr_document_hub", "ess_renew"],
    },
    "contract_amendment": {
        "processor": "mistral_document_ai",
        "default_authority": "EMPLOYER",
        "channels": ["hr_document_hub", "ess_renew"],
        "status": "schema_ready_no_intake_type_yet",
    },
    "commercial_licence": {
        "processor": "storage_or_text_mirror",
        "default_authority": "MOCI",
        "channels": ["employer_setup"],
        "status": "employer_text_mirror",
    },
    "authorised_signature": {
        "processor": "storage_or_text_mirror",
        "default_authority": "EMPLOYER",
        "status": "offer_snapshot_text_mirror",
    },
    "offer_letter": {
        "processor": "storage_or_generated",
        "default_authority": "EMPLOYER",
        "status": "generated_preferred_upload_storage_only",
    },
    "bank_certificate": {
        "processor": "mistral_document_ai",
        "default_authority": "BANK",
        "aliases": ["iban_letter", "salary_transfer_letter", "bank_letter"],
        "channels": ["ess_bank", "ess_onboarding", "hr_document_hub"],
        "status": "bank_ess_p1",
    },
}


COMMON_FIELDS = [
    "country_code",
    "issuing_authority",
    "document_type",
    "jurisdiction",
    "document_number",
    "employee_or_holder",
    "employer_or_sponsor",
    "issue_date",
    "expiry_date",
    "renewal_required",
]


def normalize_document_type(document_type: str | None) -> str:
    raw = str(document_type or "").strip().lower()
    if raw in {"residency", "residency_iqama"}:
        return "residence"
    if raw in {"medical_check", "medical_fitness"}:
        return "medical"
    if raw in {"authorized_signature", "authorized_signatory"}:
        return "authorised_signature"
    if raw in {"iban_letter", "salary_transfer_letter", "bank_letter", "bank_cert", "kw_iban_letter"}:
        return "bank_certificate"
    return raw


def bank_certificate_json_schema() -> dict[str, Any]:
    """Kuwait bank certificate / IBAN letter fields for Bank ESS P1.

    Non-authoritative: employee must confirm/correct before sealed submit.
    Never writes verified or payroll-effective rows.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "document_type": {
                "type": "string",
                "enum": ["bank_certificate", "iban_letter", "unknown"],
            },
            "country_code": {"type": ["string", "null"]},
            "bank_name": {"type": ["string", "null"]},
            "account_holder": {"type": ["string", "null"]},
            "iban": {"type": ["string", "null"]},
            "account_number": {"type": ["string", "null"]},
            "branch": {"type": ["string", "null"]},
            "swift": {"type": ["string", "null"]},
            "currency": {"type": ["string", "null"]},
            "overall_confidence": {"type": "number"},
            "unreadable_reason": {"type": ["string", "null"]},
            "warnings": {
                "type": "array",
                "items": {"type": "string"},
            },
            "field_confidence": {"type": "object", "additionalProperties": {"type": "number"}},
        },
        "required": [
            "document_type",
            "bank_name",
            "account_holder",
            "iban",
            "account_number",
            "overall_confidence",
        ],
    }


def employment_contract_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "document_type": {
                "type": "string",
                "enum": ["employment_contract", "contract_amendment", "offer_letter", "unknown"],
            },
            "country_code": {"type": ["string", "null"]},
            "jurisdiction": {"type": ["string", "null"]},
            "issuing_authority": {"type": ["string", "null"]},
            "document_number": {"type": ["string", "null"]},
            "employee_name_ar": {"type": ["string", "null"]},
            "employee_name_en": {"type": ["string", "null"]},
            "employer_legal_name_ar": {"type": ["string", "null"]},
            "employer_legal_name_en": {"type": ["string", "null"]},
            "job_title": {"type": ["string", "null"]},
            "contract_type": {"type": ["string", "null"]},
            "contract_start_date": {"type": ["string", "null"]},
            "contract_end_date": {"type": ["string", "null"]},
            "probation_period": {"type": ["string", "null"]},
            "salary_amount": {"type": ["number", "null"]},
            "salary_currency": {"type": ["string", "null"]},
            "allowances": {"type": ["string", "null"]},
            "work_location": {"type": ["string", "null"]},
            "working_hours": {"type": ["string", "null"]},
            "weekly_rest_days": {"type": ["string", "null"]},
            "annual_leave_entitlement": {"type": ["string", "null"]},
            "notice_period": {"type": ["string", "null"]},
            "renewal_terms": {"type": ["string", "null"]},
            "termination_clauses": {"type": ["string", "null"]},
            "signatories": {"type": ["string", "null"]},
            "employee_signature_status": {
                "type": "string",
                "enum": ["signed", "unsigned", "unclear", "unknown"],
            },
            "employer_signature_status": {
                "type": "string",
                "enum": ["signed", "unsigned", "unclear", "unknown"],
            },
            "clause_evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "clause": {"type": "string"},
                        "language": {"type": "string", "enum": ["ar", "en", "bilingual", "unknown"]},
                        "page": {"type": ["integer", "null"]},
                        "excerpt": {"type": ["string", "null"]},
                    },
                    "required": ["clause", "language", "page", "excerpt"],
                },
            },
            "issue_date": {"type": ["string", "null"]},
            "expiry_date": {"type": ["string", "null"]},
            "renewal_required": {"type": ["boolean", "null"]},
            "overall_confidence": {"type": "number"},
            "unreadable_reason": {"type": ["string", "null"]},
            "field_confidence": {"type": "object", "additionalProperties": {"type": "number"}},
        },
        "required": [
            "document_type",
            "employee_name_ar",
            "employee_name_en",
            "employer_legal_name_en",
            "job_title",
            "contract_start_date",
            "contract_end_date",
            "salary_amount",
            "salary_currency",
            "employee_signature_status",
            "employer_signature_status",
            "overall_confidence",
        ],
    }


def compliance_certificate_json_schema() -> dict[str, Any]:
    """Work permit / residency / licence / education / medical-style compliance fields."""

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "document_type": {
                "type": "string",
                "enum": [
                    "education_cert",
                    "commercial_licence",
                    "authorised_signature",
                    "work_permit",
                    "residence",
                    "medical",
                    "unknown",
                ],
            },
            "country_code": {"type": ["string", "null"]},
            "jurisdiction": {"type": ["string", "null"]},
            "issuing_authority": {"type": ["string", "null"]},
            "document_number": {"type": ["string", "null"]},
            "employee_or_holder_ar": {"type": ["string", "null"]},
            "employee_or_holder_en": {"type": ["string", "null"]},
            "employer_or_sponsor": {"type": ["string", "null"]},
            "occupation_or_profession": {"type": ["string", "null"]},
            "permit_or_residency_category": {"type": ["string", "null"]},
            "qualification_or_category": {"type": ["string", "null"]},
            "document_status": {"type": ["string", "null"]},
            "issue_date": {"type": ["string", "null"]},
            "expiry_date": {"type": ["string", "null"]},
            "renewal_required": {"type": ["boolean", "null"]},
            "overall_confidence": {"type": "number"},
            "unreadable_reason": {"type": ["string", "null"]},
            "field_confidence": {"type": "object", "additionalProperties": {"type": "number"}},
        },
        "required": [
            "document_type",
            "issuing_authority",
            "document_number",
            "employee_or_holder_en",
            "issue_date",
            "expiry_date",
            "overall_confidence",
        ],
    }


CONTRACT_ANNOTATION_PROMPT = (
    "Extract employment-contract fields for Kuwait/GCC private-sector HR. "
    "Return ONLY values explicitly present. Never invent. "
    "Keep Arabic and English names separate. Prefer ISO dates YYYY-MM-DD. "
    "Salary currency must come from the document (do not assume KWD if another currency is written). "
    "Put start/end terms only in contract_start_date and contract_end_date. "
    "issue_date must be null unless an explicit issue/signing date line is visible — never copy the start date. "
    "expiry_date must be null unless an explicit expiry/validity line is visible — never invent from end date. "
    "Do not judge legality of clauses — only extract stated terms and note missing/unreadable fields. "
    "Include clause_evidence with page references when visible."
)

COMPLIANCE_ANNOTATION_PROMPT = (
    "Extract compliance/certificate document fields for Kuwait/GCC HR. "
    "Identify issuing authority when named (PAM, MOI, PACI, PIFSS, MOH, MOCI, employer, other). "
    "Return ONLY visible values. Never invent. Keep Arabic and English names separate. "
    "Prefer ISO dates. Missing fields remain null."
)

BANK_CERTIFICATE_ANNOTATION_PROMPT = (
    "Extract fields from a Kuwait bank certificate, IBAN letter, or salary-transfer letter. "
    "Return ONLY values explicitly printed. Never invent. "
    "Normalize IBAN to letters and digits only (no spaces). Prefer KW… IBANs when present. "
    "account_holder is the account owner name as printed. "
    "bank_name is the bank’s legal or common name. "
    "account_number only when a separate account number is shown (not the full IBAN). "
    "branch and SWIFT/BIC only when clearly printed. "
    "If the scan is unclear, lower overall_confidence and set unreadable_reason. "
    "Add short warnings for low-confidence fields. Missing fields remain null."
)
