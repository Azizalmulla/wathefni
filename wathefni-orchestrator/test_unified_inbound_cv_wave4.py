"""Wave 4 Person Registry / Talent Pool / CK refs / Job binding / gate tests."""

from __future__ import annotations

import hashlib
import unittest
import uuid
from pathlib import Path
from typing import Any
from unittest import mock

import candidate_identity as identity
import candidate_knowledge_authority as cka
import candidate_knowledge_index_store as ck_index
import candidate_knowledge_types as ckt
import candidate_knowledge_wave4 as ck_w4
import inbound_cv_adapters as adapters
import inbound_cv_intake as ici
import inbound_cv_person_registry as person_reg
import inbound_cv_processing as icp
import inbound_cv_wave4 as wave4
import job_binding_authority as job_bind
import talent_pool_authority as tpa
import verified_job_binding_gate as vjbg


ROOT = Path(__file__).resolve().parent
APP_PY = ROOT / "app.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class FakeCursor:
    """Minimal cursor covering Wave 4 dual-write SQL shapes."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "intake_subjects": [],
            "persons": [],
            "person_company_memberships": [],
            "person_contact_points": [],
            "talent_pool_entries": [],
            "cv_versions": [],
            "application_job_bindings": [],
            "application_cv_bindings": [],
            "intake_consent_events": [],
            "applications": [],
            "cv_processing_stage_runs": [],
            "intake_source_events": [],
            "intake_items": [],
            "intake_item_documents": [],
        }
        self._fetch: Any = None
        self.statements: list[tuple[str, Any]] = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        text = " ".join(sql.split())
        if (
            text.startswith("CREATE TABLE")
            or text.startswith("ALTER TABLE")
            or "CREATE INDEX" in text
            or text.startswith("CREATE UNIQUE")
        ):
            self._fetch = None
            return

        if "FROM intake_subjects" in text and "SELECT" in text:
            company, subject = params[0], params[1]
            row = next(
                (
                    r
                    for r in self.tables["intake_subjects"]
                    if r.get("company_code") == company and r.get("subject_id") == subject
                ),
                None,
            )
            self._fetch = dict(row) if row else None
            return

        if "UPDATE intake_subjects" in text and "identity_review" in text:
            company, subject = params[0], params[1]
            for row in self.tables["intake_subjects"]:
                if row.get("company_code") == company and row.get("subject_id") == subject:
                    row["status"] = "identity_review"
                    row["person_id"] = None
                    row["membership_id"] = None
            self._fetch = None
            return

        if "UPDATE intake_subjects" in text and "person_id=%s" in text:
            person_id, membership_id, phone_norm, company, subject = params
            for row in self.tables["intake_subjects"]:
                if row.get("company_code") == company and row.get("subject_id") == subject:
                    row["person_id"] = person_id
                    row["membership_id"] = membership_id
                    row["status"] = "linked"
                    row["legacy_candidate_phone"] = phone_norm or row.get("legacy_candidate_phone")
            self._fetch = None
            return

        if "FROM person_contact_points" in text:
            company, norm = params[0], params[1]
            ctype = "phone" if "'phone'" in text else "email"
            matches = []
            for c in self.tables["person_contact_points"]:
                if (
                    c.get("company_code") == company
                    and c.get("contact_type") == ctype
                    and c.get("normalized_value") == norm
                ):
                    person_id = c["person_id"]
                    mem = next(
                        (
                            m
                            for m in self.tables["person_company_memberships"]
                            if m.get("person_id") == person_id and m.get("company_code") == company
                        ),
                        None,
                    )
                    if mem:
                        matches.append(
                            {"person_id": person_id, "membership_id": mem["membership_id"]}
                        )
            self._fetch = matches
            return

        if "INSERT INTO persons" in text:
            person_id = params[0]
            if not any(p["person_id"] == person_id for p in self.tables["persons"]):
                self.tables["persons"].append(
                    {"person_id": person_id, "display_name": params[1], "status": "active"}
                )
            self._fetch = None
            return

        if "INSERT INTO person_company_memberships" in text:
            membership_id, person_id, company, source = params
            if not any(m["membership_id"] == membership_id for m in self.tables["person_company_memberships"]):
                self.tables["person_company_memberships"].append(
                    {
                        "membership_id": membership_id,
                        "person_id": person_id,
                        "company_code": company,
                        "source": source,
                    }
                )
            self._fetch = None
            return

        if "INSERT INTO person_contact_points" in text:
            person_id, company, raw, norm = params[0], params[1], params[2], params[3]
            ctype = "phone" if "'phone'" in text else "email"
            self.tables["person_contact_points"].append(
                {
                    "person_id": person_id,
                    "company_code": company,
                    "contact_type": ctype,
                    "raw_value": raw,
                    "normalized_value": norm,
                }
            )
            self._fetch = None
            return

        if "INSERT INTO talent_pool_entries" in text:
            entry_id = params[0]
            company = params[1]
            subject_id = params[4]
            existing = next(
                (
                    r
                    for r in self.tables["talent_pool_entries"]
                    if r.get("company_code") == company and r.get("subject_id") == subject_id
                ),
                None,
            )
            row = {
                "entry_id": entry_id,
                "company_code": company,
                "person_id": params[2],
                "membership_id": params[3],
                "subject_id": subject_id,
                "status": params[5],
                "actionable": params[6],
                "current_cv_version_id": params[7],
            }
            if existing:
                existing.update(row)
            else:
                self.tables["talent_pool_entries"].append(row)
            self._fetch = {"entry_id": entry_id, "actionable": row["actionable"], "status": row["status"]}
            return

        if "UPDATE talent_pool_entries" in text and "current_cv_version_id" in text:
            cv_id, company, entry_id = params
            for row in self.tables["talent_pool_entries"]:
                if row.get("entry_id") == entry_id and row.get("company_code") == company:
                    row["current_cv_version_id"] = cv_id
                    self._fetch = {"entry_id": entry_id, "current_cv_version_id": cv_id}
                    return
            self._fetch = None
            return

        if "INSERT INTO cv_versions" in text:
            cv_id = params[0]
            company, sha, doc = params[1], params[2], params[8]
            existing = next(
                (
                    r
                    for r in self.tables["cv_versions"]
                    if r.get("company_code") == company
                    and r.get("content_sha256") == sha
                    and r.get("legacy_document_id") == doc
                ),
                None,
            )
            # person_id/subject_id positions after envelope_item_id
            person_id = params[13] if len(params) > 13 else None
            subject_id = params[14] if len(params) > 14 else None
            if existing is None:
                self.tables["cv_versions"].append(
                    {
                        "cv_version_id": cv_id,
                        "company_code": company,
                        "content_sha256": sha,
                        "legacy_document_id": doc,
                        "person_id": person_id,
                        "subject_id": subject_id,
                        "legacy_app_key": params[7],
                    }
                )
            else:
                existing["person_id"] = existing.get("person_id") or person_id
                existing["subject_id"] = existing.get("subject_id") or subject_id
                cv_id = existing["cv_version_id"]
            self._fetch = {"cv_version_id": cv_id}
            return

        if "INSERT INTO intake_consent_events" in text:
            self.tables["intake_consent_events"].append({"consent_id": params[0]})
            self._fetch = None
            return

        if "INSERT INTO application_job_bindings" in text:
            binding_id, company, app_key = params[0], params[1], params[2]
            existing = next(
                (
                    r
                    for r in self.tables["application_job_bindings"]
                    if r.get("company_code") == company and r.get("app_key") == app_key
                ),
                None,
            )
            row = {
                "binding_id": binding_id,
                "company_code": company,
                "app_key": app_key,
                "position_code": params[3],
                "verified": True,
                "person_id": params[7],
                "membership_id": params[8],
                "subject_id": params[9],
            }
            if existing:
                existing.update(row)
            else:
                self.tables["application_job_bindings"].append(row)
            self._fetch = {"binding_id": binding_id, "verified": True}
            return

        if "UPDATE application_cv_bindings" in text and "pinned=false" in text:
            self._fetch = None
            return

        if "INSERT INTO application_cv_bindings" in text:
            binding_id, company, app_key, cv_version_id = params[0], params[1], params[2], params[3]
            self.tables["application_cv_bindings"].append(
                {
                    "binding_id": binding_id,
                    "company_code": company,
                    "app_key": app_key,
                    "cv_version_id": cv_version_id,
                    "pinned": True,
                }
            )
            self._fetch = {"binding_id": binding_id, "cv_version_id": cv_version_id}
            return

        if "FROM application_job_bindings" in text:
            company, app_key = params[0], params[1]
            row = next(
                (
                    r
                    for r in self.tables["application_job_bindings"]
                    if r.get("company_code") == company
                    and r.get("app_key") == app_key
                    and r.get("verified")
                ),
                None,
            )
            self._fetch = dict(row) if row else None
            return

        if "FROM applications" in text and "person_id" in text:
            self._fetch = None
            return

        if "INSERT INTO cv_processing_stage_runs" in text or "INSERT INTO intake_" in text:
            self._fetch = {"run_id": str(uuid.uuid4()), "status": "completed"}
            return

        if "UPDATE candidate_cv_text_versions" in text or "UPDATE application_cv_" in text:
            self._fetch = None
            return

        self._fetch = None

    def fetchone(self):
        if isinstance(self._fetch, list):
            return self._fetch[0] if self._fetch else None
        return self._fetch

    def fetchall(self):
        if isinstance(self._fetch, list):
            return self._fetch
        if self._fetch is None:
            return []
        return [self._fetch]


class Wave4PersonTalentPoolTests(unittest.TestCase):
    def test_flags_default_off(self):
        env = {}
        self.assertFalse(person_reg.enabled(env))
        self.assertFalse(tpa.enabled(env))
        self.assertFalse(job_bind.enabled(env))
        self.assertFalse(vjbg.gate_enabled(env))
        self.assertFalse(ck_w4.enabled(env))

    def test_safe_link_exact_phone_no_merge_on_ambiguity(self):
        cur = FakeCursor()
        subject = str(uuid.uuid4())
        cur.tables["intake_subjects"].append(
            {
                "subject_id": subject,
                "company_code": "WATHEFNI",
                "person_id": None,
                "membership_id": None,
                "status": "provisional",
            }
        )
        # Two distinct persons share ambiguous evidence → identity_review, no merge.
        p1, p2 = str(uuid.uuid4()), str(uuid.uuid4())
        cur.tables["persons"].extend(
            [{"person_id": p1, "status": "active"}, {"person_id": p2, "status": "active"}]
        )
        cur.tables["person_company_memberships"].extend(
            [
                {"membership_id": str(uuid.uuid4()), "person_id": p1, "company_code": "WATHEFNI"},
                {"membership_id": str(uuid.uuid4()), "person_id": p2, "company_code": "WATHEFNI"},
            ]
        )
        phone = "+96550001111"
        norm = identity.normalize_phone(phone)
        cur.tables["person_contact_points"].extend(
            [
                {
                    "person_id": p1,
                    "company_code": "WATHEFNI",
                    "contact_type": "phone",
                    "normalized_value": norm,
                },
                {
                    "person_id": p2,
                    "company_code": "WATHEFNI",
                    "contact_type": "phone",
                    "normalized_value": norm,
                },
            ]
        )
        env = {person_reg.FEATURE: "1"}
        result = person_reg.ensure_or_link_person_for_subject(
            cur,
            company_code="WATHEFNI",
            subject_id=subject,
            phone=phone,
            environ=env,
        )
        self.assertEqual(result["status"], "identity_review")
        self.assertFalse(result.get("merged"))
        self.assertIsNone(result.get("person_id"))

    def test_new_person_and_talent_pool_non_actionable(self):
        cur = FakeCursor()
        subject = str(uuid.uuid4())
        cur.tables["intake_subjects"].append(
            {
                "subject_id": subject,
                "company_code": "WATHEFNI",
                "person_id": None,
                "membership_id": None,
                "status": "provisional",
            }
        )
        env = {
            person_reg.FEATURE: "1",
            tpa.FEATURE: "1",
            icp.FEATURE_CV_VERSION_DUAL_WRITE: "1",
            wave4.FEATURE_WAVE4: "1",
        }
        out = wave4.after_intake_receipt(
            cur,
            company_code="WATHEFNI",
            subject_id=subject,
            phone="+96550002222",
            email="cv@example.com",
            content_sha256=hashlib.sha256(b"cv-bytes").hexdigest(),
            document_id=str(uuid.uuid4()),
            actionable=False,
            channel="email",
            environ=env,
        )
        self.assertFalse(out.get("creates_job_application"))
        self.assertEqual(out["person"]["status"], "linked")
        self.assertFalse(out["talent_pool"]["actionable"])
        self.assertEqual(len(cur.tables["cv_versions"]), 1)
        self.assertEqual(cur.tables["cv_versions"][0]["person_id"], out["person"]["person_id"])


class Wave4JobBindingGateTests(unittest.TestCase):
    def test_bind_requires_confirmation(self):
        cur = FakeCursor()
        env = {job_bind.FEATURE: "1"}
        denied = job_bind.bind_application_to_job(
            cur,
            company_code="WATHEFNI",
            app_key="app-1",
            position_code="ENG",
            human_confirmed=False,
            environ=env,
        )
        self.assertEqual(denied["error"], "exact_job_confirmation_required")

    def test_bind_and_shadow_then_enforce(self):
        cur = FakeCursor()
        env = {
            job_bind.FEATURE: "1",
            vjbg.FEATURE_GATE: "1",
            vjbg.FEATURE_SHADOW: "1",
        }
        promoted = wave4.promote_with_verified_job_binding(
            cur,
            company_code="WATHEFNI",
            app_key="app-live",
            position_code="ENG",
            human_confirmed=True,
            cv_version_id=str(uuid.uuid4()),
            environ=env,
        )
        self.assertTrue(promoted["ok"])
        allow = vjbg.assert_verified_job_binding(
            cur,
            company_code="WATHEFNI",
            app_key="app-live",
            action="ranking",
            environ=env,
        )
        self.assertTrue(allow.allowed)
        self.assertEqual(allow.mode, "allow")

        missing = vjbg.assert_verified_job_binding(
            cur,
            company_code="WATHEFNI",
            app_key="app-missing",
            action="ranking",
            environ=env,
        )
        self.assertTrue(missing.allowed)  # shadow
        self.assertEqual(missing.mode, "shadow_deny")

        enforce_env = {**env, vjbg.FEATURE_ENFORCE: "1"}
        denied = vjbg.assert_verified_job_binding(
            cur,
            company_code="WATHEFNI",
            app_key="app-missing",
            action="offer",
            environ=enforce_env,
        )
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.mode, "enforce_deny")

    def test_held_talent_pool_shadow_deny(self):
        decision = vjbg.assert_verified_job_binding(
            None,
            company_code="WATHEFNI",
            app_key="held-1",
            action="screening",
            application={"status": "needs_role"},
            environ={vjbg.FEATURE_GATE: "1", vjbg.FEATURE_SHADOW: "1"},
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.mode, "shadow_deny")
        self.assertIn("held_or_unassigned_talent_pool_record", decision.reason_codes)


class Wave4CandidateKnowledgeTests(unittest.TestCase):
    def test_app_ref_unchanged_when_flag_off(self):
        with self.assertRaises(cka.CandidateKnowledgeError):
            cka.parse_exact_candidate_ref("person:abc")
        self.assertEqual(cka.parse_exact_candidate_ref("app:live-1"), "app:live-1")
        self.assertEqual(ckt.CANDIDATE_REF_PREFIX, "app:")

    def test_person_subject_refs_and_non_actionable(self):
        env = {ck_w4.FEATURE_CK_PERSON_SUBJECT: "1"}
        with mock.patch.dict("os.environ", env, clear=False):
            pref = ck_w4.candidate_ref_from_person_id("11111111-1111-1111-1111-111111111111")
            sref = ck_w4.candidate_ref_from_subject_id("22222222-2222-2222-2222-222222222222")
            self.assertEqual(cka.parse_exact_candidate_ref(pref), pref)
            self.assertEqual(cka.parse_exact_candidate_ref(sref), sref)
            act = ck_w4.talent_pool_actionability(provisional=True, held=True, restricted=False)
            self.assertTrue(act.readable)
            self.assertFalse(act.job_ranking_allowed)
            self.assertFalse(act.contact_allowed)

    def test_identity_correction_invalidates_before_reindex(self):
        store = ck_index.InMemoryCandidateKnowledgeIndexStore()
        store.chunks = [
            {
                "company_code": "WATHEFNI",
                "candidate_ref": "person:old",
                "app_key": None,
                "state": "current",
            },
            {
                "company_code": "WATHEFNI",
                "candidate_ref": "app:live",
                "app_key": "live",
                "state": "current",
            },
        ]
        out = ck_w4.invalidate_before_identity_reindex(
            store,
            company_code="WATHEFNI",
            old_candidate_refs=["person:old"],
        )
        self.assertEqual(out["invalidated"], 1)
        self.assertEqual(store.chunks[0]["state"], "invalidated")
        self.assertEqual(store.chunks[1]["state"], "current")

    def test_anchor_actionability_preserved(self):
        src = _source(ROOT / "candidate_knowledge_authority.py")
        self.assertIn("_anchor_actionability", src)
        self.assertIn("Exact Job capabilities follow the anchor application", src)


class Wave4ChannelAndSafetyTests(unittest.TestCase):
    def test_cv_only_stays_talent_pool(self):
        gate = adapters.assert_no_job_without_exact_confirmation(
            job_selected=False, human_confirmed=False, create_application=True
        )
        self.assertFalse(gate["allowed"])

    def test_app_py_gate_hook_present(self):
        src = _source(APP_PY)
        self.assertIn("UNIFIED_VERIFIED_JOB_BINDING_GATE_WAVE4", src)
        self.assertIn("verified_job_binding_required", src)

    def test_zero_downstream_mutation_contract(self):
        # Promote records bindings only; does not insert applications rows.
        cur = FakeCursor()
        env = {job_bind.FEATURE: "1"}
        wave4.promote_with_verified_job_binding(
            cur,
            company_code="WATHEFNI",
            app_key="app-x",
            position_code="OPS",
            human_confirmed=True,
            environ=env,
        )
        self.assertEqual(cur.tables["applications"], [])
        self.assertEqual(len(cur.tables["application_job_bindings"]), 1)

    def test_cross_tenant_person_seed_differs(self):
        a = person_reg.stable_person_id_for_exact_contact(
            company_code="WATHEFNI", contact_type="phone", normalized="+96550003333"
        )
        b = person_reg.stable_person_id_for_exact_contact(
            company_code="OTHERCO", contact_type="phone", normalized="+96550003333"
        )
        self.assertNotEqual(a, b)

    def test_reuse_cv_version_across_apps_without_rewrite(self):
        cur = FakeCursor()
        env = {icp.FEATURE_CV_VERSION_DUAL_WRITE: "1"}
        sha = hashlib.sha256(b"same-bytes").hexdigest()
        doc = str(uuid.uuid4())
        first = icp.dual_write_cv_version(
            cur,
            company_code="WATHEFNI",
            content_sha256=sha,
            legacy_document_id=doc,
            person_id="person-1",
            subject_id="subject-1",
            environ=env,
        )
        second = icp.dual_write_cv_version(
            cur,
            company_code="WATHEFNI",
            content_sha256=sha,
            legacy_document_id=doc,
            legacy_app_key="app-later",
            person_id="person-1",
            environ=env,
        )
        self.assertEqual(first["cv_version_id"], second["cv_version_id"])
        self.assertEqual(len(cur.tables["cv_versions"]), 1)
        self.assertFalse(second.get("reader_cutover", True) is False and False)
        self.assertEqual(second.get("reader_cutover"), False)


if __name__ == "__main__":
    unittest.main()
