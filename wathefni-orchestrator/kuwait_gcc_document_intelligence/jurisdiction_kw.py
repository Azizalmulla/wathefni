"""Jurisdiction profiles — Kuwait first; other GCC profiles addable later."""

from __future__ import annotations

from typing import Any


# Shared foundation must not assume Kuwait. Callers pass country_code.
SUPPORTED_COUNTRY_CODES = frozenset({"KW"})  # Wave 1: Kuwait only implemented


KUWAIT_PROFILE: dict[str, Any] = {
    "country_code": "KW",
    "country_name": "Kuwait",
    "jurisdiction": "kuwait_private_sector",
    "default_currency": "KWD",  # only a profile default — extractors prefer document currency
    "rtl_primary_language": "ar",
    "authorities": {
        "PACI": {
            "name_en": "Public Authority for Civil Information",
            "name_ar": "الهيئة العامة للمعلومات المدنية",
            "documents": ["civil_id"],
        },
        "PAM": {
            "name_en": "Public Authority for Manpower",
            "name_ar": "الهيئة العامة للقوى العاملة",
            "documents": ["work_permit"],
        },
        "MOI": {
            "name_en": "Ministry of Interior",
            "name_ar": "وزارة الداخلية",
            "documents": ["residence", "visa", "entry_visa"],
        },
        "PIFSS": {
            "name_en": "Public Institution for Social Security",
            "name_ar": "المؤسسة العامة للتأمينات الاجتماعية",
            "documents": ["pifss_statement", "pifss_certificate"],
            "processing": "external_authority_mirror_or_payroll",
        },
        "MOCI": {
            "name_en": "Ministry of Commerce and Industry",
            "name_ar": "وزارة التجارة والصناعة",
            "documents": ["commercial_licence"],
            "processing": "employer_text_mirror_until_doc_intelligence",
        },
        "MOH": {
            "name_en": "Ministry of Health",
            "name_ar": "وزارة الصحة",
            "documents": ["medical", "medical_fitness"],
        },
        "EMPLOYER": {
            "name_en": "Employer / private sector",
            "documents": ["employment_contract", "contract_amendment", "offer_letter", "education_cert", "authorised_signature"],
        },
    },
    "identity_number_shapes": {
        "civil_id": r"^\d{12}$",
        "passport": r"^[A-Z0-9]{6,12}$",
    },
    "reminder_warning_days": {
        "civil_id": 30,
        "passport": 60,
        "residence": 30,
        "work_permit": 30,
        "medical": 30,
        "education_cert": 30,
        "employment_contract": None,  # term end is HR-managed, not default compliance window
        "commercial_licence": 60,
    },
    "article_18_notes": (
        "Article 18 expatriate residency/work-permit requiredness is category-aware "
        "in kuwait_first_client_foundation; this profile does not invent requiredness."
    ),
    "honesty": {
        "hr_reviewed_is_not_government_verified": True,
        "no_legal_advice": True,
        "machine_non_authoritative_until_hr_confirm": True,
    },
    "gcc_extension_hooks": {
        "planned_country_codes": ["SA", "AE", "BH", "QA", "OM"],
        "add_profile_file_pattern": "jurisdiction_{cc}.py",
        "shared_schemas_remain_country_agnostic": True,
    },
}


def jurisdiction_profile(country_code: str | None) -> dict[str, Any] | None:
    cc = str(country_code or "").strip().upper()
    if cc == "KW":
        return dict(KUWAIT_PROFILE)
    return None


def issuing_authority_for(document_type: str, *, country_code: str = "KW") -> str | None:
    profile = jurisdiction_profile(country_code) or {}
    for code, row in (profile.get("authorities") or {}).items():
        if document_type in (row.get("documents") or []):
            return code
    return None
