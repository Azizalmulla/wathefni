"""Phase 0 fixtures for Candidate Knowledge contract capture.

Synthetic only. No production reads, Voyage calls, indexing, or mutations.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


TENANT_A = "WATHEFNI"
TENANT_B = "OTHERCO"

# GCC shared-surname fixture: Mariam Almulla vs unrelated Almulla family members.
# Name-only matching must not merge or confuse these identities.
MARIAM_ALMULLA = {
    "fixture_id": "gcc_shared_surname_mariam",
    "company_code": TENANT_A,
    "display_name": "Mariam Almulla",
    "email": "mariam.almulla@example.com",
    "phone": "96550001111",
    "app_key": "app-mariam-almulla-hr",
    "position_code": "HR_ASSISTANT",
    "status": "review_pending",
    "identity": {
        "exact_email": "mariam.almulla@example.com",
        "exact_phone": "96550001111",
        "shared_surname": "Almulla",
        "must_not_match_app_keys": [
            "app-aziz-almulla-ops",
            "app-hamad-almulla-sales",
        ],
    },
}

UNRELATED_ALMULLA_FAMILY = [
    {
        "fixture_id": "gcc_shared_surname_aziz",
        "company_code": TENANT_A,
        "display_name": "Aziz Almulla",
        "email": "aziz.almulla@example.com",
        "phone": "96550002222",
        "app_key": "app-aziz-almulla-ops",
        "position_code": "OPERATIONS",
        "status": "shortlisted",
        "identity": {
            "exact_email": "aziz.almulla@example.com",
            "exact_phone": "96550002222",
            "shared_surname": "Almulla",
            "must_not_match_app_keys": ["app-mariam-almulla-hr"],
        },
    },
    {
        "fixture_id": "gcc_shared_surname_hamad",
        "company_code": TENANT_A,
        "display_name": "Hamad Almulla",
        "email": "hamad.almulla@example.com",
        "phone": "96550003333",
        "app_key": "app-hamad-almulla-sales",
        "position_code": "SALES",
        "status": "screening",
        "identity": {
            "exact_email": "hamad.almulla@example.com",
            "exact_phone": "96550003333",
            "shared_surname": "Almulla",
            "must_not_match_app_keys": ["app-mariam-almulla-hr"],
        },
    },
]

OPEN_IDENTITY_REVIEW = {
    "fixture_id": "open_identity_review",
    "company_code": TENANT_A,
    "display_name": "Sara Alenezi",
    "email": "sara.alenezi@example.com",
    "phone": "96550004444",
    "app_key": "app-sara-identity-review",
    "status": "review_pending",
    "identity_review": {
        "state": "open",
        "reason": "possible_duplicate_email_phone_conflict",
        "resolution_required": True,
    },
}

HELD_STATES = [
    {
        "fixture_id": "held_needs_role",
        "company_code": TENANT_A,
        "display_name": "Held Needs Role",
        "phone": "96550005555",
        "app_key": "app-held-needs-role",
        "status": "needs_role",
        "expected": {
            "talent_pool_search_eligible": False,
            "job_ranking_eligible": False,
            "readable": True,
            "actionable": False,
            "held_state": "needs_role",
        },
    },
    {
        "fixture_id": "held_import_review",
        "company_code": TENANT_A,
        "display_name": "Held Import Review",
        "phone": "96550006666",
        "app_key": "app-held-import-review",
        "status": "import_review",
        "expected": {
            "talent_pool_search_eligible": False,
            "job_ranking_eligible": False,
            "readable": True,
            "actionable": False,
            "held_state": "import_review",
        },
    },
    {
        "fixture_id": "held_import_archived",
        "company_code": TENANT_A,
        "display_name": "Held Import Archived",
        "phone": "96550007777",
        "app_key": "app-held-import-archived",
        "status": "import_archived",
        "expected": {
            "talent_pool_search_eligible": False,
            "job_ranking_eligible": False,
            "readable": True,
            "actionable": False,
            "held_state": "import_archived",
        },
    },
]

# review_pending is intentionally domain-specific today.
REVIEW_PENDING_POLICY_MATRIX = {
    "fixture_id": "review_pending_policy_matrix",
    "status": "review_pending",
    "domains": {
        "production_search_predicate": {
            "excluded": False,
            "note": "production_application_predicate excludes needs_role/import_review/import_archived only",
        },
        "communication_gate": {
            "treated_as_held": False,
            "note": "communication hold set mirrors production predicate held statuses",
        },
        "inbound_identity_retention": {
            "treated_as_held": True,
            "note": "inbound_retention_policy.HELD_APPLICATION_STATUSES includes review_pending",
        },
        "registry_rank_boost_order": {
            "boost_rank": 1,
            "note": "action_registry semantic ORDER BY boosts review_pending after screening_complete",
        },
    },
}

LONG_CV_BEYOND_12000 = {
    "fixture_id": "long_cv_beyond_12000",
    "company_code": TENANT_A,
    "app_key": "app-long-cv",
    "display_name": "Long CV Candidate",
    "phone": "96550008888",
    "status": "review_pending",
    "cv_text": (
        "HEADER UNIQUE TOKEN AAA\n"
        + ("experience line with marketing analytics kuwait arabic english.\n" * 700)
        + "TAIL UNIQUE TOKEN ZZZ AFTER 12000 CHAR BOUNDARY\n"
    ),
    "expected": {
        "char_count_min": 12001,
        "registry_cv_eval_visible_max": 6000,
        "voyage_document_embed_truncate": 12000,
        "tail_token": "TAIL UNIQUE TOKEN ZZZ AFTER 12000 CHAR BOUNDARY",
        "head_token": "HEADER UNIQUE TOKEN AAA",
        "tail_must_be_disclosed_as_not_in_truncated_window": True,
    },
}

MULTIPLE_APPLICATIONS_ONE_CANDIDATE = {
    "fixture_id": "multiple_applications_one_candidate",
    "company_code": TENANT_A,
    "phone": "96550009999",
    "display_name": "Multi App Candidate",
    "email": "multi.app@example.com",
    "applications": [
        {
            "app_key": "app-multi-hr",
            "position_code": "HR_ASSISTANT",
            "status": "review_pending",
        },
        {
            "app_key": "app-multi-ops",
            "position_code": "OPERATIONS",
            "status": "shortlisted",
        },
        {
            "app_key": "app-multi-sales",
            "position_code": "SALES",
            "status": "screening",
        },
    ],
    "expected": {
        "bound_by": "phone",
        "application_count": 3,
        "candidate_ref_anchor": "app-multi-hr",
        "authority_must_aggregate_all_bound_apps": True,
    },
}

MANUAL_SURROGATE = {
    "fixture_id": "manual_surrogate_imp",
    "company_code": TENANT_A,
    "display_name": "Manual Upload Surrogate",
    "phone": "imp-manual-0001",
    "email": "manual.surrogate@example.com",
    "app_key": "app-manual-surrogate",
    "status": "import_review",
    "provenance": {
        "channel": "manual_upload",
        "phone_kind": "surrogate",
        "must_not_merge_to_real_phone": "96550001111",
    },
}

REAL_PHONE_CONTROL = {
    "fixture_id": "real_phone_control",
    "company_code": TENANT_A,
    "display_name": "Real Phone Control",
    "phone": "96550001111",
    "email": "real.phone@example.com",
    "app_key": "app-real-phone-control",
    "status": "review_pending",
}

PERMISSION_FIXTURES = {
    "empty_permissions": {
        "fixture_id": "permission_empty",
        "permission_authority": "legacy_empty",
        "permissions": [],
        "expected_current_tool_admission": {
            "rank_candidates": True,
            "candidate_cv_evaluation": True,
            "note": "tool_call_orchestrator._tool_allowed admits empty perms for *.read when strict WhatsApp flag is off",
        },
        "expected_phase1_authority": {
            "must_deny": True,
            "required_authority": "backend_current",
        },
    },
    "backend_current": {
        "fixture_id": "permission_backend_current",
        "permission_authority": "backend_current",
        "permissions": ["prehire.read"],
        "expected_current_tool_admission": {
            "rank_candidates": True,
            "candidate_cv_evaluation": True,
        },
        "expected_phase1_authority": {
            "must_deny": False,
            "required_authority": "backend_current",
        },
    },
    "backend_current_missing_prehire": {
        "fixture_id": "permission_backend_current_missing",
        "permission_authority": "backend_current",
        "permissions": ["payroll.read"],
        "expected_current_tool_admission": {
            "rank_candidates": False,
            "candidate_cv_evaluation": False,
        },
        "expected_phase1_authority": {
            "must_deny": True,
            "required_authority": "backend_current",
        },
    },
}

TENANT_ISOLATION = {
    "fixture_id": "tenant_isolation",
    "tenant_a": {
        "company_code": TENANT_A,
        "app_key": "app-tenant-a-only",
        "phone": "96551110001",
        "display_name": "Tenant A Candidate",
    },
    "tenant_b": {
        "company_code": TENANT_B,
        "app_key": "app-tenant-b-only",
        "phone": "96551110002",
        "display_name": "Tenant B Candidate",
    },
    "expected": {
        "cross_tenant_exact_read_must_miss": True,
        "cross_tenant_search_must_not_leak": True,
    },
}


def long_cv_text() -> str:
    return str(LONG_CV_BEYOND_12000["cv_text"])


def all_fixtures() -> dict[str, Any]:
    return {
        "mariam_almulla": deepcopy(MARIAM_ALMULLA),
        "unrelated_almulla_family": deepcopy(UNRELATED_ALMULLA_FAMILY),
        "open_identity_review": deepcopy(OPEN_IDENTITY_REVIEW),
        "held_states": deepcopy(HELD_STATES),
        "review_pending_policy_matrix": deepcopy(REVIEW_PENDING_POLICY_MATRIX),
        "long_cv_beyond_12000": {
            **deepcopy(LONG_CV_BEYOND_12000),
            "cv_text": long_cv_text(),
            "cv_char_count": len(long_cv_text()),
        },
        "multiple_applications_one_candidate": deepcopy(MULTIPLE_APPLICATIONS_ONE_CANDIDATE),
        "manual_surrogate": deepcopy(MANUAL_SURROGATE),
        "real_phone_control": deepcopy(REAL_PHONE_CONTROL),
        "permission_fixtures": deepcopy(PERMISSION_FIXTURES),
        "tenant_isolation": deepcopy(TENANT_ISOLATION),
    }
