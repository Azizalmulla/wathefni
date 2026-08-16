"""Kuwait/GCC Contracts & Compliance Document Intelligence — Wave 2.

Shared, channel-agnostic processing for onboarding + Hub/ESS/email/backfill.

Hard constraints:
- Does NOT replace or duplicate identity_document_extraction (Mistral authority).
- Does NOT use CV V2 or GPT for classify / extract / verify / fallback.
- Does NOT touch Ranking, Candidate Knowledge, Migration, payroll, or CV extraction.
- Machine results remain non-authoritative until HR confirms.
- Kuwait rules live in a jurisdiction profile; shared foundation stays country-agnostic.
"""

from __future__ import annotations

from kuwait_gcc_document_intelligence.authority import (
    authority_status,
    kuwait_gcc_authority_enabled,
)
from kuwait_gcc_document_intelligence.extraction import (
    process_document,
    classify_document,
    verify_document,
    extract_document,
    runtime_counters,
    reset_runtime_counters,
)
from kuwait_gcc_document_intelligence.intake import (
    CANONICAL_TYPE_MAP,
    PRESERVED_ALIASES,
    canonical_document_type,
    extraction_for_receipt,
    shared_channel_extraction,
)
from kuwait_gcc_document_intelligence.jurisdiction_kw import KUWAIT_PROFILE, jurisdiction_profile
from kuwait_gcc_document_intelligence.schemas import (
    DOCUMENT_CLASSES,
    IDENTITY_DELEGATE_TYPES,
    SHARED_CHANNEL_TYPES,
    STORAGE_ONLY_TYPES,
    GENERATED_ONLY_TYPES,
    EXTERNAL_AUTHORITY_MIRRORS,
)
from kuwait_gcc_document_intelligence.channel_contract import (
    CHANNELS,
    channel_gap_registry,
    expected_channel_flow,
)

__all__ = [
    "KUWAIT_PROFILE",
    "DOCUMENT_CLASSES",
    "IDENTITY_DELEGATE_TYPES",
    "STORAGE_ONLY_TYPES",
    "GENERATED_ONLY_TYPES",
    "EXTERNAL_AUTHORITY_MIRRORS",
    "CHANNELS",
    "CANONICAL_TYPE_MAP",
    "PRESERVED_ALIASES",
    "jurisdiction_profile",
    "kuwait_gcc_authority_enabled",
    "authority_status",
    "canonical_document_type",
    "shared_channel_extraction",
    "extraction_for_receipt",
    "process_document",
    "classify_document",
    "verify_document",
    "extract_document",
    "runtime_counters",
    "reset_runtime_counters",
    "channel_gap_registry",
    "expected_channel_flow",
]
