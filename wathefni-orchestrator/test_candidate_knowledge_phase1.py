"""Phase 1 Candidate Knowledge authority tests.

Synthetic in-memory store only. Proves zero database mutations and that source
readers cannot execute before authorization + exact resolution.
"""

from __future__ import annotations

import unittest

from candidate_knowledge_authority import (
    CandidateKnowledgeAuthority,
    InMemoryCandidateKnowledgeStore,
    build_request_context,
    parse_exact_candidate_ref,
)
from candidate_knowledge_errors import (
    ERROR_ACTOR_REQUIRED,
    ERROR_BACKEND_CURRENT_REQUIRED,
    ERROR_CANDIDATE_AMBIGUOUS,
    ERROR_CANDIDATE_NOT_FOUND,
    ERROR_CANDIDATE_RESTRICTED,
    ERROR_INVALID_CANDIDATE_REF,
    ERROR_MODULE_DISABLED,
    ERROR_PERMISSION_DENIED,
    ERROR_PERMISSION_SUBJECT_MISMATCH,
    ERROR_SOURCE_READER_BLOCKED,
    ERROR_TENANT_SCOPE_REQUIRED,
    CandidateKnowledgeError,
)
from candidate_record_state_policy import evaluate_candidate_record_state
from fixtures.candidate_knowledge_phase0 import (
    MANUAL_SURROGATE,
    MARIAM_ALMULLA,
    MULTIPLE_APPLICATIONS_ONE_CANDIDATE,
    REAL_PHONE_CONTROL,
    TENANT_ISOLATION,
    UNRELATED_ALMULLA_FAMILY,
)


def _ctx(
    *,
    company: str = "WATHEFNI",
    actor: str = "user-1",
    authority: str = "backend_current",
    subject_user: str | None = None,
    subject_company: str | None = None,
    permissions: list[str] | None = None,
    modules: list[str] | None = None,
) -> object:
    return build_request_context(
        company_code=company,
        actor_user_id=actor,
        permission_authority=authority,
        permission_subject_user_id=subject_user if subject_user is not None else actor,
        permission_subject_company=subject_company if subject_company is not None else company,
        permissions=permissions if permissions is not None else ["prehire.read"],
        modules_enabled=modules if modules is not None else ["pre_hiring"],
    )


def _app(
    *,
    company: str,
    app_key: str,
    phone: str,
    status: str = "review_pending",
    name: str = "Candidate",
    position_code: str = "HR",
) -> dict:
    return {
        "company_code": company,
        "app_key": app_key,
        "phone": phone,
        "status": status,
        "candidate_name": name,
        "position_code": position_code,
        "data_source": "production",
    }


class RequestContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryCandidateKnowledgeStore()
        self.authority = CandidateKnowledgeAuthority(
            self.store,
            module_enabled=lambda company, module: module == "pre_hiring" and company == "WATHEFNI",
        )

    def test_valid_backend_current_context(self):
        ctx = _ctx()
        self.assertEqual(self.authority.authorize(ctx).company_code, "WATHEFNI")

    def test_empty_permissions_denied(self):
        with self.assertRaises(CandidateKnowledgeError) as raised:
            self.authority.authorize(_ctx(permissions=[]))
        self.assertEqual(raised.exception.code, ERROR_PERMISSION_DENIED)

    def test_missing_prehire_read_denied(self):
        with self.assertRaises(CandidateKnowledgeError) as raised:
            self.authority.authorize(_ctx(permissions=["payroll.read"]))
        self.assertEqual(raised.exception.code, ERROR_PERMISSION_DENIED)

    def test_legacy_untrusted_authority_denied(self):
        with self.assertRaises(CandidateKnowledgeError) as raised:
            self.authority.authorize(_ctx(authority="legacy_untrusted"))
        self.assertEqual(raised.exception.code, ERROR_BACKEND_CURRENT_REQUIRED)

    def test_empty_authority_denied(self):
        with self.assertRaises(CandidateKnowledgeError) as raised:
            self.authority.authorize(_ctx(authority=""))
        self.assertEqual(raised.exception.code, ERROR_BACKEND_CURRENT_REQUIRED)

    def test_actor_mismatch_denied(self):
        with self.assertRaises(CandidateKnowledgeError) as raised:
            self.authority.authorize(_ctx(actor="user-1", subject_user="user-2"))
        self.assertEqual(raised.exception.code, ERROR_PERMISSION_SUBJECT_MISMATCH)

    def test_company_mismatch_denied(self):
        with self.assertRaises(CandidateKnowledgeError) as raised:
            self.authority.authorize(_ctx(company="WATHEFNI", subject_company="OTHERCO"))
        self.assertEqual(raised.exception.code, ERROR_PERMISSION_SUBJECT_MISMATCH)

    def test_missing_tenant_denied(self):
        with self.assertRaises(CandidateKnowledgeError) as raised:
            self.authority.authorize(_ctx(company=""))
        self.assertEqual(raised.exception.code, ERROR_TENANT_SCOPE_REQUIRED)

    def test_missing_actor_denied(self):
        with self.assertRaises(CandidateKnowledgeError) as raised:
            self.authority.authorize(_ctx(actor=""))
        self.assertEqual(raised.exception.code, ERROR_ACTOR_REQUIRED)

    def test_module_disabled_denied(self):
        authority = CandidateKnowledgeAuthority(
            self.store,
            module_enabled=lambda *_args: False,
        )
        with self.assertRaises(CandidateKnowledgeError) as raised:
            authority.authorize(_ctx())
        self.assertEqual(raised.exception.code, ERROR_MODULE_DISABLED)


class ResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        multi = MULTIPLE_APPLICATIONS_ONE_CANDIDATE
        apps = [
            _app(
                company=MARIAM_ALMULLA["company_code"],
                app_key=MARIAM_ALMULLA["app_key"],
                phone=MARIAM_ALMULLA["phone"],
                name=MARIAM_ALMULLA["display_name"],
                status=MARIAM_ALMULLA["status"],
            ),
            *[
                _app(
                    company=item["company_code"],
                    app_key=item["app_key"],
                    phone=item["phone"],
                    name=item["display_name"],
                    status=item["status"],
                )
                for item in UNRELATED_ALMULLA_FAMILY
            ],
            *[
                _app(
                    company=multi["company_code"],
                    app_key=item["app_key"],
                    phone=multi["phone"],
                    name=multi["display_name"],
                    status=item["status"],
                    position_code=item["position_code"],
                )
                for item in multi["applications"]
            ],
            _app(
                company=MANUAL_SURROGATE["company_code"],
                app_key=MANUAL_SURROGATE["app_key"],
                phone=MANUAL_SURROGATE["phone"],
                name=MANUAL_SURROGATE["display_name"],
                status=MANUAL_SURROGATE["status"],
            ),
            _app(
                company=REAL_PHONE_CONTROL["company_code"],
                app_key=REAL_PHONE_CONTROL["app_key"],
                phone="96550001999",  # distinct from Mariam fixture phone for aggregation isolation
                name=REAL_PHONE_CONTROL["display_name"],
                status=REAL_PHONE_CONTROL["status"],
            ),
            _app(
                company=TENANT_ISOLATION["tenant_a"]["company_code"],
                app_key=TENANT_ISOLATION["tenant_a"]["app_key"],
                phone=TENANT_ISOLATION["tenant_a"]["phone"],
                name=TENANT_ISOLATION["tenant_a"]["display_name"],
            ),
            _app(
                company=TENANT_ISOLATION["tenant_b"]["company_code"],
                app_key=TENANT_ISOLATION["tenant_b"]["app_key"],
                phone=TENANT_ISOLATION["tenant_b"]["phone"],
                name=TENANT_ISOLATION["tenant_b"]["display_name"],
            ),
            # Same app_key in another tenant must not leak.
            _app(
                company="OTHERCO",
                app_key=MARIAM_ALMULLA["app_key"],
                phone="96559999999",
                name="Foreign Mariam",
            ),
            _app(
                company="WATHEFNI",
                app_key="app-open-identity-review",
                phone="96550004444",
                name="Sara Alenezi",
                status="review_pending",
            ),
        ]
        self.store = InMemoryCandidateKnowledgeStore(applications=apps)
        self.authority = CandidateKnowledgeAuthority(
            self.store,
            module_enabled=lambda company, module: module == "pre_hiring",
        )

    def test_exact_same_tenant_app_resolution(self):
        resolved = self.authority.resolve_exact(_ctx(), f"app:{MARIAM_ALMULLA['app_key']}")
        self.assertEqual(resolved.anchor_app_key, MARIAM_ALMULLA["app_key"])
        self.assertEqual(resolved.candidate_key, MARIAM_ALMULLA["phone"])
        self.assertEqual(len(resolved.applications), 1)

    def test_cross_tenant_denial_no_existence_leak(self):
        # Tenant A asking for tenant B's app_key.
        with self.assertRaises(CandidateKnowledgeError) as raised:
            self.authority.resolve_exact(
                _ctx(company="WATHEFNI"),
                f"app:{TENANT_ISOLATION['tenant_b']['app_key']}",
            )
        err = raised.exception
        self.assertEqual(err.code, ERROR_CANDIDATE_NOT_FOUND)
        payload = err.to_dict()
        self.assertNotIn("exists", payload)
        self.assertNotIn("OTHERCO", str(payload))

    def test_same_app_key_other_tenant_does_not_resolve_here(self):
        # Mariam app_key exists in OTHERCO too; WATHEFNI still resolves only local row.
        resolved = self.authority.resolve_exact(_ctx(), f"app:{MARIAM_ALMULLA['app_key']}")
        self.assertEqual(resolved.company_code, "WATHEFNI")
        self.assertEqual(resolved.applications[0]["phone"], MARIAM_ALMULLA["phone"])

    def test_invalid_app_reference(self):
        with self.assertRaises(CandidateKnowledgeError) as raised:
            parse_exact_candidate_ref("app:")
        self.assertEqual(raised.exception.code, ERROR_INVALID_CANDIDATE_REF)

    def test_name_only_ambiguity(self):
        with self.assertRaises(CandidateKnowledgeError) as raised:
            self.authority.resolve_exact(_ctx(), "Mariam Almulla")
        self.assertEqual(raised.exception.code, ERROR_CANDIDATE_AMBIGUOUS)
        with self.assertRaises(CandidateKnowledgeError) as raised2:
            self.authority.resolve_name_only(_ctx(), "Mariam Almulla")
        self.assertEqual(raised2.exception.code, ERROR_CANDIDATE_AMBIGUOUS)

    def test_multiple_applications_bound_to_one_candidate(self):
        multi = MULTIPLE_APPLICATIONS_ONE_CANDIDATE
        anchor = multi["applications"][0]["app_key"]
        resolved = self.authority.resolve_exact(_ctx(), f"app:{anchor}")
        self.assertEqual(resolved.candidate_key, multi["phone"])
        self.assertEqual(len(resolved.applications), 3)
        keys = {item["app_key"] for item in resolved.applications}
        self.assertEqual(keys, {item["app_key"] for item in multi["applications"]})

    def test_manual_surrogate_remains_separate(self):
        surrogate = self.authority.resolve_exact(_ctx(), f"app:{MANUAL_SURROGATE['app_key']}")
        real = self.authority.resolve_exact(_ctx(), f"app:{REAL_PHONE_CONTROL['app_key']}")
        self.assertEqual(surrogate.candidate_key, MANUAL_SURROGATE["phone"])
        self.assertTrue(str(surrogate.candidate_key).startswith("imp-"))
        self.assertFalse(str(real.candidate_key).startswith("imp-"))
        self.assertNotEqual(surrogate.candidate_key, real.candidate_key)
        self.assertNotEqual(surrogate.candidate_key, MARIAM_ALMULLA["phone"])
        self.assertEqual(len(surrogate.applications), 1)
        self.assertEqual(len(real.applications), 1)

    def test_shared_surname_candidates_remain_separate(self):
        mariam = self.authority.resolve_exact(_ctx(), f"app:{MARIAM_ALMULLA['app_key']}")
        for item in UNRELATED_ALMULLA_FAMILY:
            other = self.authority.resolve_exact(_ctx(), f"app:{item['app_key']}")
            self.assertNotEqual(mariam.candidate_key, other.candidate_key)
            self.assertEqual(len(other.applications), 1)

    def test_open_identity_review_does_not_resolve_by_name_or_merge(self):
        # Exact app still works; name path stays ambiguous; no auto-merge to Mariam.
        resolved = self.authority.resolve_exact(_ctx(), "app:app-open-identity-review")
        self.assertEqual(resolved.anchor_app_key, "app-open-identity-review")
        self.assertNotEqual(resolved.candidate_key, MARIAM_ALMULLA["phone"])
        with self.assertRaises(CandidateKnowledgeError):
            self.authority.resolve_exact(_ctx(), "Sara Alenezi")


class PolicyAndActionabilityTests(unittest.TestCase):
    def test_each_held_state(self):
        for status in ("needs_role", "import_review", "import_archived"):
            decision = evaluate_candidate_record_state({"status": status, "phone": "1", "app_key": "a"})
            self.assertEqual(decision.intake_hold_state, status)
            self.assertFalse(decision.communication_allowed)
            self.assertFalse(decision.job_ranking_eligible)
            self.assertFalse(decision.talent_pool_search_eligible)
            self.assertFalse(decision.lifecycle_mutation_allowed)
            self.assertEqual(decision.read_projection, "full" if status != "import_archived" else "redacted")
            self.assertTrue(decision.to_actionability()["readable"] or status == "import_archived")

    def test_review_pending_domain_differences(self):
        decision = evaluate_candidate_record_state({"status": "review_pending", "app_key": "a", "phone": "1"})
        self.assertIsNone(decision.intake_hold_state)
        self.assertTrue(decision.communication_allowed)
        self.assertTrue(decision.talent_pool_search_eligible)
        self.assertTrue(decision.job_ranking_eligible)
        self.assertTrue(decision.retention_blocked)
        self.assertIn("review_pending_retention_held_only", decision.reason_codes)

    def test_normal_live_and_finalized_states(self):
        live = evaluate_candidate_record_state({"status": "shortlisted", "app_key": "a", "phone": "1"})
        self.assertTrue(live.communication_allowed)
        self.assertTrue(live.job_ranking_eligible)
        self.assertFalse(live.retention_blocked)
        finalized = evaluate_candidate_record_state({"status": "hired", "app_key": "a", "phone": "1"})
        self.assertFalse(finalized.job_ranking_eligible)
        self.assertFalse(finalized.lifecycle_mutation_allowed)

    def test_governance_archived_restricted_legal_hold_deletion(self):
        archived = evaluate_candidate_record_state(
            {"status": "shortlisted", "app_key": "a", "phone": "1"},
            governance={"archive_state": "archived"},
        )
        self.assertIn("archived", archived.governance_flags)
        self.assertEqual(archived.read_projection, "redacted")
        self.assertFalse(archived.communication_allowed)

        restricted = evaluate_candidate_record_state(
            {"status": "shortlisted", "app_key": "a", "phone": "1"},
            governance={"restriction_state": "restricted"},
        )
        self.assertEqual(restricted.read_projection, "metadata_only")
        self.assertFalse(restricted.communication_allowed)

        legal = evaluate_candidate_record_state(
            {"status": "shortlisted", "app_key": "a", "phone": "1"},
            governance={"legal_hold_state": "active"},
        )
        self.assertTrue(legal.retention_blocked)
        self.assertIn("legal_hold", legal.governance_flags)

        deleting = evaluate_candidate_record_state(
            {"status": "shortlisted", "app_key": "a", "phone": "1"},
            governance={"deletion_request_state": "in_progress"},
        )
        self.assertEqual(deleting.read_projection, "redacted")
        self.assertFalse(deleting.lifecycle_mutation_allowed)

        deleted = evaluate_candidate_record_state(
            {"status": "shortlisted", "app_key": "a", "phone": "1"},
            governance={"deletion_request_state": "completed"},
        )
        self.assertEqual(deleted.read_projection, "denied")

    def test_authority_raises_restricted_for_deletion_completed(self):
        store = InMemoryCandidateKnowledgeStore(
            applications=[_app(company="WATHEFNI", app_key="app-deleted", phone="96550001212", status="shortlisted")],
            governance={("WATHEFNI", "app-deleted"): {"deletion_request_state": "completed"}},
        )
        authority = CandidateKnowledgeAuthority(store, module_enabled=lambda *_: True)
        with self.assertRaises(CandidateKnowledgeError) as raised:
            authority.resolve_exact(_ctx(), "app:app-deleted")
        self.assertEqual(raised.exception.code, ERROR_CANDIDATE_RESTRICTED)


class Phase1BoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryCandidateKnowledgeStore(
            applications=[_app(company="WATHEFNI", app_key="app-x", phone="96550000001", status="shortlisted")]
        )
        self.authority = CandidateKnowledgeAuthority(self.store, module_enabled=lambda *_: True)

    def test_source_readers_cannot_execute_before_authorization(self):
        with self.assertRaises(CandidateKnowledgeError) as raised:
            self.authority.assert_source_reader_blocked("canonical_cv")
        self.assertEqual(raised.exception.code, ERROR_SOURCE_READER_BLOCKED)

    def test_source_readers_blocked_after_resolution_in_phase1(self):
        self.authority.resolve_exact(_ctx(), "app:app-x")
        # Phase 2 section names are gated to assemble_phase2; Phase 3+ remain blocked.
        self.authority.assert_source_reader_blocked("effective_facts")
        with self.assertRaises(CandidateKnowledgeError) as raised:
            self.authority.assert_source_reader_blocked("candidates.profile")
        self.assertEqual(raised.exception.code, ERROR_SOURCE_READER_BLOCKED)
        with self.assertRaises(CandidateKnowledgeError):
            self.authority.assert_source_reader_blocked("applications.raw_json")
        with self.assertRaises(CandidateKnowledgeError):
            self.authority.assert_source_reader_blocked("semantic_documents")

    def test_phase1_shell_has_no_source_payloads(self):
        resolved = self.authority.resolve_exact(_ctx(), "app:app-x")
        record = self.authority.phase1_record_shell(resolved)
        payload = record.to_dict()
        self.assertEqual(payload["canonical_cv"], {})
        self.assertEqual(payload["effective_facts"], {})
        self.assertEqual(payload["classifications"], {})
        self.assertEqual(payload["assessments"], [])
        self.assertEqual(payload["interviews"], [])
        self.assertEqual(payload["ranking_evaluations"], [])
        self.assertEqual(payload["notes"], [])
        self.assertEqual(payload["screening_evidence"], [])
        self.assertTrue(payload["actionability"]["readable"])

    def test_zero_database_mutation(self):
        before = self.store.write_attempts
        self.authority.resolve_exact(_ctx(), "app:app-x")
        self.assertEqual(self.store.write_attempts, before)
        self.assertEqual(self.authority.mutation_count, 0)
        with self.assertRaises(RuntimeError):
            self.store.mutate(foo="bar")
        self.assertEqual(self.store.write_attempts, before + 1)


if __name__ == "__main__":
    unittest.main()
