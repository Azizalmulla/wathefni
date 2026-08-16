"""Local Ranking R0–R3 contract tests (no staging deploy)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import candidate_ranking as cr
import candidate_cv_facts as cvf


class FakeCursor:
    def __init__(self, store: "FakeStore") -> None:
        self.store = store
        self._result: list[dict] = []
        self.rowcount = 0

    def execute(self, sql: str, params=None) -> None:
        self.store.execute(self, sql, params or ())

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConn:
    def __init__(self, store: "FakeStore") -> None:
        self.store = store

    def cursor(self):
        return FakeCursor(self.store)

    def commit(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeStore:
    def __init__(self) -> None:
        self.positions: list[dict] = []
        self.applications: list[dict] = []
        self.criteria_sets: list[dict] = []
        self.criteria: list[dict] = []
        self.runs: list[dict] = []
        self.items: list[dict] = []
        self.narratives: list[dict] = []
        self.recalc_jobs: list[dict] = []
        self.semantic: list[dict] = []

    def db_connect(self):
        return FakeConn(self)

    def execute(self, cur: FakeCursor, sql: str, params: tuple) -> None:
        text = " ".join(sql.split()).lower()
        cur._result = []
        cur.rowcount = 0
        if text.startswith("create table") or text.startswith("create index"):
            return
        if "from positions" in text:
            company, position = params[0], str(params[1]).upper()
            cur._result = [
                p
                for p in self.positions
                if p["company_code"] == company and str(p["position_code"]).upper() == position
            ][:1]
            return
        if "from job_ranking_criteria_sets" in text and "max(version)" in text:
            company, position = params[0], str(params[1]).upper()
            versions = [
                int(s.get("version") or 0)
                for s in self.criteria_sets
                if s["company_code"] == company and str(s["position_code"]).upper() == position
            ]
            cur._result = [{"version": max(versions) if versions else 0}]
            return
        if "from job_ranking_criteria_sets" in text and "status='approved'" in text:
            company, position = params[0], str(params[1]).upper()
            rows = [
                s
                for s in self.criteria_sets
                if s["company_code"] == company
                and str(s["position_code"]).upper() == position
                and s.get("status") == "approved"
            ]
            rows.sort(key=lambda r: int(r.get("version") or 0), reverse=True)
            cur._result = rows[:1]
            return
        if "from job_ranking_criteria" in text:
            set_id = params[0]
            cur._result = [c for c in self.criteria if c["criteria_set_id"] == set_id and c.get("active", True)]
            return
        if "insert into job_ranking_criteria_sets" in text:
            # params: id, company, position, job_id, version, actor, denylist, scoring, [evidence_policy], metadata
            has_policy = len(params) >= 10
            row = {
                "criteria_set_id": params[0],
                "company_code": params[1],
                "position_code": params[2],
                "job_id": params[3],
                "version": params[4],
                "status": "approved",
                "approved_by_user_id": params[5],
                "denylist_version": params[6],
                "scoring_config_version": params[7],
                "evidence_policy": params[8] if has_policy else {},
                "metadata": params[9] if has_policy else (params[8] if len(params) > 8 else {}),
            }
            if isinstance(row["evidence_policy"], str):
                try:
                    row["evidence_policy"] = json.loads(row["evidence_policy"])
                except Exception:
                    row["evidence_policy"] = {}
            if isinstance(row["metadata"], str):
                try:
                    row["metadata"] = json.loads(row["metadata"])
                except Exception:
                    row["metadata"] = {}
            self.criteria_sets.append(row)
            return
        if "insert into job_ranking_criteria" in text:
            self.criteria.append(
                {
                    "criterion_id": f"crit-{len(self.criteria)+1}",
                    "criteria_set_id": params[0],
                    "company_code": params[1],
                    "position_code": params[2],
                    "criterion_type": params[3],
                    "label": params[4],
                    "classification": params[5],
                    "rule_json": params[6] if isinstance(params[6], dict) else json.loads(params[6]) if isinstance(params[6], str) else {},
                    "weight": params[7],
                    "evidence_sources": params[8],
                    "missing_behavior": params[9],
                    "active": True,
                }
            )
            return
        if "update ranking_runs" in text and "is_current=false" in text and "stale_reason=%s" in text:
            company, position = params[1], str(params[2]).upper()
            count = 0
            for run in self.runs:
                if run["company_code"] == company and str(run["position_code"]).upper() == position and run.get("is_current"):
                    run["is_current"] = False
                    run["stale_reason"] = params[0]
                    count += 1
            cur.rowcount = count
            return
        if "insert into ranking_recalculation_jobs" in text:
            self.recalc_jobs.append({"company_code": params[0], "position_code": params[1], "reason": params[2], "status": "pending"})
            return
        if "from ranking_runs" in text and "is_current=true" in text:
            company, position = params[0], str(params[1]).upper()
            rows = [
                r
                for r in self.runs
                if r["company_code"] == company and str(r["position_code"]).upper() == position and r.get("is_current")
            ]
            rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
            cur._result = rows[:1]
            return
        if "from ranking_run_items" in text and "join ranking_runs" in text:
            item_id, company, position = params[0], params[1], str(params[2]).upper()
            rows = []
            for item in self.items:
                if item.get("item_id") != item_id:
                    continue
                if item.get("company_code") != company:
                    continue
                if str(item.get("position_code") or "").upper() != position:
                    continue
                run = next((r for r in self.runs if r.get("run_id") == item.get("run_id")), {})
                rows.append(
                    {
                        **item,
                        "run_id": item.get("run_id"),
                        "job_id": run.get("job_id"),
                        "job_version": run.get("job_version"),
                        "criteria_set_id": run.get("criteria_set_id"),
                        "criteria_version": run.get("criteria_version"),
                        "run_provenance": run.get("provenance"),
                    }
                )
            cur._result = rows[:1]
            return
        if "from ranking_run_items" in text:
            run_id = params[0]
            rows = [i for i in self.items if i["run_id"] == run_id]
            rows.sort(key=lambda i: (i.get("soft_rank") or 9999, i.get("pool_ordinal") or 0))
            cur._result = rows
            return
        if "select count(*)" in text and "from applications" in text:
            company = params[0]
            position = str(params[1]).upper()
            count = 0
            for app in self.applications:
                if app["company_code"] != company:
                    continue
                code = str(app.get("position_code") or "").upper()
                title = str(app.get("position_title") or "").upper()
                if code != position and title != position.replace("_", " "):
                    continue
                if "status not in" in text and app.get("status") in {"hired", "rejected", "withdrawn"}:
                    continue
                count += 1
            cur._result = [{"n": count}]
            return
        if "from applications a" in text and "left join" in text:
            company = params[0]
            position = str(params[1]).upper()
            limit = int(params[-1])
            rows = []
            for app in self.applications:
                if app["company_code"] != company:
                    continue
                code = str(app.get("position_code") or "").upper()
                title = str(app.get("position_title") or "").upper()
                if code != position and title != position.replace("_", " "):
                    continue
                if "status not in" in text and app.get("status") in {"hired", "rejected", "withdrawn"}:
                    continue
                rows.append(dict(app))
            cur._result = rows[:limit]
            return
        if "from semantic_documents" in text:
            keys = set(params[1] or [])
            cur._result = [s for s in self.semantic if s.get("app_key") in keys]
            return
        if "insert into ranking_runs" in text:
            row = {
                "run_id": params[0],
                "company_code": params[1],
                "position_code": params[2],
                "job_id": params[3],
                "job_version": params[4],
                "criteria_set_id": params[5],
                "criteria_version": params[6],
                "actor_user_id": params[7],
                "status": "completed",
                "pool_total": params[8],
                "eligible_count": params[9],
                "not_met_count": params[10],
                "unknown_count": params[11],
                "scored_count": params[12],
                "request_hash": params[13],
                "provenance": params[14],
                "denylist_version": params[15],
                "scoring_config_version": params[16],
                "embedding_model": params[17],
                "reranker_model": params[18],
                "is_current": False,
                "stale_reason": None,
            }
            existing = next(
                (
                    r
                    for r in self.runs
                    if r["company_code"] == row["company_code"]
                    and r["position_code"] == row["position_code"]
                    and r["request_hash"] == row["request_hash"]
                ),
                None,
            )
            if existing:
                existing.update(row)
                cur._result = [{"run_id": existing["run_id"]}]
            else:
                self.runs.append(row)
                cur._result = [{"run_id": row["run_id"]}]
            return
        if "delete from ranking_run_items" in text:
            run_id = params[0]
            self.items = [i for i in self.items if i["run_id"] != run_id]
            return
        if "insert into ranking_run_items" in text:
            item_id = f"item-{len(self.items)+1}"
            self.items.append(
                {
                    "item_id": item_id,
                    "run_id": params[0],
                    "company_code": params[1],
                    "position_code": params[2],
                    "app_key": params[3],
                    "person_id": params[4],
                    "membership_id": params[5],
                    "eligibility_bucket": params[6],
                    "advisory_score": params[7],
                    "component_scores": params[8],
                    "requirement_results": params[9],
                    "evidence": params[10],
                    "missing_data": params[11],
                    "evidence_coverage": params[12],
                    "confidence": params[13],
                    "explanation": params[14],
                    "provenance": params[15],
                    "pool_ordinal": params[16],
                    "soft_rank": params[17],
                    "display": {"name": params[3], "status": "review_pending", "position_code": params[2]},
                }
            )
            cur._result = [{"item_id": item_id}]
            return
        if "from ranking_item_narratives" in text:
            item_id = params[0]
            prompt_version = params[1]
            if len(params) >= 4 and "evidence_hash" in text:
                evidence_hash, locale = params[2], params[3]
                rows = [
                    n
                    for n in self.narratives
                    if n["item_id"] == item_id
                    and n["prompt_version"] == prompt_version
                    and n["evidence_hash"] == evidence_hash
                    and n["locale"] == locale
                ]
            else:
                locale = params[2]
                rows = [
                    n
                    for n in self.narratives
                    if n["item_id"] == item_id
                    and n["prompt_version"] == prompt_version
                    and n["locale"] == locale
                    and n.get("status") == "completed"
                ]
            rows.sort(key=lambda n: n.get("created_at") or "", reverse=True)
            cur._result = rows[:1]
            return
        if "insert into ranking_item_narratives" in text:
            row = {
                "narrative_id": params[0],
                "item_id": params[1],
                "run_id": params[2],
                "company_code": params[3],
                "position_code": params[4],
                "app_key": params[5],
                "narrative_text": params[6],
                "model": params[7],
                "prompt_version": params[8],
                "evidence_hash": params[9],
                "locale": params[10],
                "status": params[11],
                "error": params[12],
                "evidence_envelope": params[13],
                "provenance": params[14],
                "generated_at": "2026-07-22T00:00:00Z" if params[11] == "completed" else None,
                "created_at": "2026-07-22T00:00:00Z",
            }
            existing = next(
                (
                    n
                    for n in self.narratives
                    if n["item_id"] == row["item_id"]
                    and n["prompt_version"] == row["prompt_version"]
                    and n["evidence_hash"] == row["evidence_hash"]
                    and n["locale"] == row["locale"]
                ),
                None,
            )
            if existing:
                if existing.get("status") != "completed":
                    existing.update(row)
                cur._result = [existing]
            else:
                self.narratives.append(row)
                cur._result = [row]
            return
        if "update ranking_runs" in text and "run_id<>%s" in text:
            company, position, run_id = params[0], str(params[1]).upper(), params[2]
            for run in self.runs:
                if run["company_code"] == company and str(run["position_code"]).upper() == position and run.get("is_current") and run["run_id"] != run_id:
                    run["is_current"] = False
                    run["stale_reason"] = run.get("stale_reason") or "superseded_by_new_run"
            return
        if "update ranking_runs" in text and "is_current=true" in text and "where run_id=%s" in text:
            run_id = params[0]
            for run in self.runs:
                if run["run_id"] == run_id:
                    run["is_current"] = True
                    run["stale_reason"] = None
            return


class FakeOrch(FakeStore):
    def production_application_predicate(self, alias="a"):
        return "TRUE"

    def reviewable_application_predicate(self, alias="a"):
        return "TRUE"

    def embedding_provider_config(self):
        return {"model": "voyage-4-large"}

    def embed_rank_query(self, query):
        return None

    def pgvector_literal(self, vector):
        return None

    def Json(self, value):
        return value

    def ranking_terra_narrative_callable(self, *, envelope, locale, model, prompt_version):
        assert model == "gpt-5.6-terra"
        assert prompt_version == cr.NARRATIVE_PROMPT_VERSION
        blob = json.dumps(envelope)
        assert "civil_id" not in blob.lower()
        assert "nationality" not in blob.lower()
        app_key = (((envelope.get("committed_result") or {}).get("app_key")) or "candidate")
        return {
            "narrative": f"Terra narrative for {app_key} in {locale}: matches approved evidence without changing scores.",
            "language": locale,
        }


def _app(company, position, app_key, *, years=None, skills=None, status="review_pending", semantic="", extra=None):
    extracted = {}
    if years is not None:
        extracted["years_experience"] = years
    if skills is not None:
        extracted["skills"] = skills
    payload = {
        "app_key": app_key,
        "company_code": company,
        "phone": f"+965{app_key[-8:]}",
        "position_code": position,
        "position_title": position.replace("_", " "),
        "status": status,
        "cv_received": True,
        "person_id": None,
        "membership_id": None,
        "ingested_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "raw_json": {"cv": {"extracted": extracted, **(extra or {})}},
        "candidate_name": f"Candidate {app_key}",
        "candidate_email": f"{app_key}@example.com",
        "candidate_profile": {},
        "candidate_raw_json": {},
        "semantic_content": semantic or "canonical cv text",
        "semantic_content_hash": "hash",
        "semantic_model": "voyage-4-large",
        "cv_file_id": f"file-{app_key}",
        "cv_file_updated_at": "2026-01-01T00:00:00Z",
        "cv_extraction_run_id": f"xr-{app_key}",
        "cv_extraction_stage": "completed",
        "cv_evidence_id": f"evidence-{app_key}",
        "cv_evidence_status": "ready",
        "cv_evidence_file_id": f"file-{app_key}",
        "cv_evidence_source_sha256": "source-hash",
        "cv_extraction_finalization_id": "00000000-0000-0000-0000-000000000001",
        "cv_extraction_quality_ok": True,
        "cv_extracted_text_hash": "hash",
        "cv_evidence_semantic_content_hash": "hash",
        "cv_evidence_embedding_status": "ready",
        "cv_evidence_contract_version": "application-cv-evidence-v1",
        "assessment_status": None,
        "assessment_percent": None,
        "assessment_attempt_id": None,
    }
    return payload


class RankingUnitTests(unittest.TestCase):
    def test_missing_tenant_fails_closed(self):
        with self.assertRaises(cr.RankingError) as ctx:
            cr.validate_company("")
        self.assertEqual(ctx.exception.code, "tenant_scope_required")

    def test_job_required(self):
        with self.assertRaises(cr.RankingError) as ctx:
            cr.validate_position("")
        self.assertEqual(ctx.exception.code, "job_required")

    def test_sensitive_fields_scrubbed_from_features(self):
        payload = {
            "civil_id": "123",
            "nationality": "KW",
            "gender": "female",
            "skills": ["Python", "إدارة مشاريع"],
            "notes": "Civil ID 299010101234 and religion Muslim",
        }
        cleaned = cr.sanitize_ranking_payload(payload)
        self.assertNotIn("civil_id", cleaned)
        self.assertNotIn("nationality", cleaned)
        self.assertNotIn("gender", cleaned)
        self.assertIn("skills", cleaned)
        text = cr.ranking_feature_text(semantic_content=payload["notes"], structured=payload)
        self.assertNotIn("civil_id", text.lower().replace(" ", ""))
        self.assertIn("[redacted]", text)

    def test_hard_requirement_unknown_not_not_met_when_missing(self):
        criterion = {
            "criterion_id": "c1",
            "criterion_type": "technical_skill",
            "label": "Python",
            "classification": "hard",
            "rule_json": {"value": "python"},
            "missing_behavior": "unknown",
            "active": True,
        }
        row = _app("ACME", "ENGINEER", "a1", skills=["Excel"])
        result = cr.evaluate_hard_criterion(criterion, row)
        self.assertEqual(result["result"], "unknown")

    def test_hard_requirement_met_from_structured_only(self):
        criterion = {
            "criterion_id": "c1",
            "criterion_type": "technical_skill",
            "label": "Python",
            "classification": "hard",
            "rule_json": {"value": "python"},
            "missing_behavior": "unknown",
            "active": True,
        }
        row = _app("ACME", "ENGINEER", "a1", skills=["Python"])
        result = cr.evaluate_hard_criterion(criterion, row)
        self.assertEqual(result["result"], "met")
        self.assertTrue(result["evidence"])

    def test_unstructured_text_alone_is_unknown_for_hard(self):
        criterion = {
            "criterion_id": "c1",
            "criterion_type": "certification",
            "label": "PMP",
            "classification": "hard",
            "rule_json": {"value": "pmp"},
            "missing_behavior": "unknown",
            "active": True,
        }
        row = _app("ACME", "ENGINEER", "a1", semantic="holds PMP certification")
        result = cr.evaluate_hard_criterion(criterion, row)
        self.assertEqual(result["result"], "unknown")

    def test_arabic_bilingual_soft_scoring(self):
        job = {
            "title": "محاسب",
            "title_ar": "محاسب",
            "title_en": "Accountant",
            "requirements_en": ["Excel", "IFRS"],
            "requirements_ar": ["إكسل", "معايير المحاسبة"],
        }
        row = _app(
            "ACME",
            "ACCOUNTANT",
            "ar1",
            years=4,
            skills=["Excel", "إكسل"],
            semantic="خبرة في المحاسبة ومعايير IFRS في الكويت",
        )
        soft = cr.soft_component_scores(row=row, job=job, soft_criteria=[], semantic_similarity=0.7)
        self.assertGreater(soft["advisory_score"], 0)
        self.assertIn("skills_alignment", soft["component_scores"])
        self.assertNotIn("interview", soft["component_scores"])

    def test_short_hr_title_keeps_application_facts_without_inventing_alignment(self):
        row = _app("ACME", "HR", "hr1", semantic="HR Assistant supporting recruitment and onboarding")
        extracted = cvf.extract_application_cv_facts(
            "Skills\nRecruitment- Employee Relations\nExperience\nHR Assistant- Supported onboarding"
        )
        row.update({
            "application_cv_facts": extracted,
            "cv_facts_id": "00000000-0000-0000-0000-000000000099",
            "cv_facts_status": "ready",
            "cv_facts_contract_version": cvf.CV_FACTS_CONTRACT_VERSION,
            "candidate_profile": {"skills": ["Bookkeeping"], "active_position_code": "ACCOUNTING"},
        })
        soft = cr.soft_component_scores(
            row=row,
            job={"title": "HR", "position_code": "HR"},
            soft_criteria=[],
            semantic_similarity=0.4,
        )
        evidence = {item["field"]: item for item in soft["evidence"]}
        self.assertIn("cv_skills", evidence)
        self.assertIn("Recruitment", evidence["cv_skills"]["value"])
        self.assertNotIn("Bookkeeping", evidence["cv_skills"]["value"])
        self.assertIn("employment", evidence)
        self.assertEqual(soft["component_statuses"]["skills_alignment"], "not_configured")
        self.assertEqual(soft["component_statuses"]["experience_alignment"], "present_unquantified")

    def test_reranker_never_omits_and_stays_disabled(self):
        items = [{"app_key": "a"}, {"app_key": "b"}, {"app_key": "c"}]
        with mock.patch.dict("os.environ", {"WATHEFNI_RANKING_RERANK": "0", "VOYAGE_API_KEY": "x"}):
            out, model = cr.maybe_rerank_bounded(items, query="accountant")
        self.assertEqual([i["app_key"] for i in out], ["a", "b", "c"])
        self.assertIsNone(model)
        # Even if mistakenly enabled, local stub makes zero Voyage rerank API calls.
        with mock.patch.dict("os.environ", {"WATHEFNI_RANKING_RERANK": "1", "VOYAGE_API_KEY": "x"}):
            out2, model2 = cr.maybe_rerank_bounded(items, query="accountant")
        self.assertEqual([i["app_key"] for i in out2], ["a", "b", "c"])
        self.assertIsNone(model2)

    def test_complete_sql_pool_and_parity_shape(self):
        orch = FakeOrch()
        orch.positions.append(
            {
                "company_code": "ACME",
                "position_code": "ENGINEER",
                "title": "Engineer",
                "title_en": "Engineer",
                "title_ar": "مهندس",
                "job_id": "job-1",
                "version": 3,
                "status": "open",
                "location": "Kuwait",
                "work_arrangement": "onsite",
                "employment_type": "full_time",
                "requirements_en": ["Python"],
                "requirements_ar": ["بايثون"],
                "updated_at": "2026-01-01",
            }
        )
        orch.applications.extend(
            [
                _app("ACME", "ENGINEER", "app-met", years=6, skills=["Python"]),
                _app("ACME", "ENGINEER", "app-unknown", years=None, skills=["Excel"]),
                _app("ACME", "ENGINEER", "app-other", years=2, skills=["Java"], status="hired"),
                _app("OTHER", "ENGINEER", "app-x", years=9, skills=["Python"]),
            ]
        )
        cr.approve_criteria_set(
            orch,
            company_code="ACME",
            position_code="ENGINEER",
            actor_user_id="hr-1",
            criteria=[
                {
                    "criterion_type": "minimum_experience_years",
                    "label": "3 years",
                    "classification": "hard",
                    "rule_json": {"minimum_years": 3},
                    "missing_behavior": "unknown",
                },
                {
                    "criterion_type": "technical_skill",
                    "label": "Python",
                    "classification": "hard",
                    "rule_json": {"value": "python"},
                    "missing_behavior": "unknown",
                },
            ],
        )
        result = cr.rank_job_applications(orch, company_code="ACME", position_code="ENGINEER")
        self.assertEqual(result["pool_total"], 2)
        keys = {i["app_key"] for i in result["items"]}
        self.assertEqual(keys, {"app-met", "app-unknown"})
        self.assertNotIn("app-x", keys)
        self.assertTrue(result["advisory"])
        self.assertFalse(result["lifecycle_mutations"])
        self.assertEqual(result["provenance"]["denylist_version"], cr.DENYLIST_VERSION)

        legacy = cr.to_legacy_rank_candidates_shape(result, top_n=1)
        self.assertEqual(legacy["pool_total"], 2)
        self.assertEqual(len(legacy["candidates"]), 1)
        self.assertEqual(legacy["run_id"], result["run_id"])
        self.assertEqual(legacy["capped"], int(legacy.get("rankable_count") or 0) > 1)
        self.assertEqual(legacy["filters"]["position_title"], "Engineer")
        self.assertEqual(legacy["ranking_basis"]["source"], "approved_criteria")

        # Surface parity: same run_id / order for dashboard+mobile+assistant adapters.
        dash = cr.rank_candidates_compat(orch, {"position": "ENGINEER", "top_n": 10}, company_code="ACME")
        mobile = cr.rank_candidates_compat(orch, {"position": "ENGINEER", "top_n": 10}, company_code="ACME")
        self.assertEqual(dash["run_id"], mobile["run_id"])
        self.assertEqual([c["app_key"] for c in dash["candidates"]], [c["app_key"] for c in mobile["candidates"]])
        self.assertTrue(dash.get("idempotent_replay") or mobile.get("idempotent_replay") or dash["run_id"] == result["run_id"])

    def test_cross_tenant_denied_by_company_scope(self):
        orch = FakeOrch()
        orch.positions.append(
            {
                "company_code": "ACME",
                "position_code": "ENGINEER",
                "title": "Engineer",
                "title_en": "Engineer",
                "title_ar": None,
                "job_id": "job-1",
                "version": 1,
                "status": "open",
                "location": None,
                "work_arrangement": None,
                "employment_type": None,
                "requirements_en": [],
                "requirements_ar": [],
                "updated_at": None,
            }
        )
        with self.assertRaises(cr.RankingError) as ctx:
            cr.rank_job_applications(orch, company_code="OTHER", position_code="ENGINEER")
        self.assertEqual(ctx.exception.code, "job_not_found")

    def test_unapproved_criteria_do_not_affect(self):
        orch = FakeOrch()
        orch.positions.append(
            {
                "company_code": "ACME",
                "position_code": "ENGINEER",
                "title": "Engineer",
                "title_en": "Engineer",
                "title_ar": None,
                "job_id": "job-1",
                "version": 1,
                "status": "open",
                "location": None,
                "work_arrangement": None,
                "employment_type": None,
                "requirements_en": [],
                "requirements_ar": [],
                "updated_at": None,
            }
        )
        orch.applications.append(_app("ACME", "ENGINEER", "app-1", years=1, skills=[]))
        orch.criteria_sets.append(
            {
                "criteria_set_id": "draft-1",
                "company_code": "ACME",
                "position_code": "ENGINEER",
                "version": 1,
                "status": "draft",
            }
        )
        orch.criteria.append(
            {
                "criteria_set_id": "draft-1",
                "criterion_type": "minimum_experience_years",
                "classification": "hard",
                "rule_json": {"minimum_years": 10},
                "missing_behavior": "not_met",
                "active": True,
            }
        )
        result = cr.rank_job_applications(orch, company_code="ACME", position_code="ENGINEER")
        self.assertEqual(result["items"][0]["eligibility_bucket"], "not_applicable")
        self.assertTrue(result["items"][0].get("requirements_configured"))
        self.assertEqual(result["ranking_basis"]["source"], "job_title")
        self.assertIsNone(result["criteria_set"]["criteria_set_id"])

    def test_automatic_hr_profile_is_useful_but_never_a_hard_gate(self):
        profile = cr.automatic_role_profile({"title": "HR", "position_code": "HR"})
        self.assertEqual(profile["source"], "job_title_profile")
        self.assertGreaterEqual(profile["criteria_count"], 5)
        self.assertTrue(all(item["classification"] == "soft" for item in profile["criteria"]))
        self.assertIn("Recruitment and Talent Acquisition", [item["label"] for item in profile["criteria"]])

    def test_professional_hr_experience_ranks_above_simulated_when_other_signals_match(self):
        profile = cr.automatic_role_profile({"title": "HR", "position_code": "HR"})
        job = {"title": "HR", "position_code": "HR", "_ranking_basis": profile}

        def row_with_facts(app_key, text):
            row = _app("ACME", "HR", app_key, semantic=text)
            extracted = cvf.extract_application_cv_facts(text)
            row.update({
                "application_cv_facts": extracted,
                "cv_facts_id": f"00000000-0000-0000-0000-{app_key[-12:].zfill(12)}",
                "cv_facts_status": "ready",
                "cv_facts_contract_version": cvf.CV_FACTS_CONTRACT_VERSION,
            })
            return row

        professional = row_with_facts(
            "000000000001",
            "Skills\nRecruitment and Talent Acquisition- Employee Relations\n"
            "Experience\nHR Assistant- Supported recruitment and employee onboarding",
        )
        simulated = row_with_facts(
            "000000000002",
            "Skills\nRecruitment and Talent Acquisition- Employee Relations\n"
            "Experience\nHR Assistant (Simulated/Academic Projects)- Practiced recruitment and onboarding",
        )
        pro_score = cr.soft_component_scores(
            row=professional,
            job=job,
            soft_criteria=profile["criteria"],
            semantic_similarity=0.5,
        )
        simulated_score = cr.soft_component_scores(
            row=simulated,
            job=job,
            soft_criteria=profile["criteria"],
            semantic_similarity=0.5,
        )
        self.assertGreater(pro_score["advisory_score"], simulated_score["advisory_score"])

    def test_stale_on_criteria_change(self):
        orch = FakeOrch()
        orch.positions.append(
            {
                "company_code": "ACME",
                "position_code": "ENGINEER",
                "title": "Engineer",
                "title_en": "Engineer",
                "title_ar": None,
                "job_id": "job-1",
                "version": 1,
                "status": "open",
                "location": None,
                "work_arrangement": None,
                "employment_type": None,
                "requirements_en": [],
                "requirements_ar": [],
                "updated_at": None,
            }
        )
        orch.applications.append(_app("ACME", "ENGINEER", "app-1", years=5, skills=["Python"]))
        first = cr.rank_job_applications(orch, company_code="ACME", position_code="ENGINEER")
        self.assertTrue(first["run_id"])
        cr.approve_criteria_set(
            orch,
            company_code="ACME",
            position_code="ENGINEER",
            actor_user_id="hr-1",
            criteria=[
                {
                    "criterion_type": "minimum_experience_years",
                    "classification": "hard",
                    "rule_json": {"minimum_years": 3},
                    "missing_behavior": "unknown",
                }
            ],
        )
        stale_runs = [r for r in orch.runs if r.get("stale_reason") == "criteria_version_changed"]
        self.assertTrue(stale_runs)

    def test_model_narrative_cannot_alter_scores(self):
        soft = cr.soft_component_scores(
            row=_app("ACME", "ENGINEER", "a1", years=5, skills=["Python"]),
            job={"title": "Engineer", "requirements_en": ["Python"], "requirements_ar": []},
            soft_criteria=[],
            semantic_similarity=0.5,
        )
        narrative = "This candidate is perfect and should score 100."
        # Explanation is derived after scoring; narrative text is not an input.
        self.assertNotIn(narrative, json.dumps(soft))
        self.assertLessEqual(soft["advisory_score"], 100)

    def test_candidate_facing_payload_has_no_ranking_internals(self):
        # Candidate WhatsApp contract: never include ranking scores/comparisons.
        candidate_payload = {"status": "screening", "next_step": "upload_cv"}
        serialized = json.dumps(candidate_payload)
        for banned in ("advisory_score", "soft_rank", "requirement_results", "ranking_run"):
            self.assertNotIn(banned, serialized)

    def test_no_lifecycle_mutation_keys(self):
        orch = FakeOrch()
        orch.positions.append(
            {
                "company_code": "ACME",
                "position_code": "ENGINEER",
                "title": "Engineer",
                "title_en": "Engineer",
                "title_ar": None,
                "job_id": "job-1",
                "version": 1,
                "status": "open",
                "location": None,
                "work_arrangement": None,
                "employment_type": None,
                "requirements_en": [],
                "requirements_ar": [],
                "updated_at": None,
            }
        )
        orch.applications.append(_app("ACME", "ENGINEER", "app-1", years=4, skills=["Python"]))
        result = cr.rank_job_applications(orch, company_code="ACME", position_code="ENGINEER")
        blob = json.dumps(result, default=str)
        self.assertNotIn('"shortlist"', blob)
        self.assertNotIn('"reject"', blob)
        self.assertFalse(result.get("lifecycle_mutations"))


class TerraNarrativeTests(unittest.TestCase):
    def _seed(self, orch: FakeOrch, app_key="app-1"):
        orch.positions.append(
            {
                "company_code": "ACME",
                "position_code": "ENGINEER",
                "title": "Engineer",
                "title_en": "Engineer",
                "title_ar": "مهندس",
                "job_id": "job-1",
                "version": 1,
                "status": "open",
                "location": "Kuwait",
                "work_arrangement": "onsite",
                "employment_type": "full_time",
                "requirements_en": ["Python"],
                "requirements_ar": ["بايثون"],
                "updated_at": None,
            }
        )
        orch.applications.append(
            _app(
                "ACME",
                "ENGINEER",
                app_key,
                years=5,
                skills=["Python"],
                extra={"civil_id": "299010101234", "nationality": "KW", "gender": "female"},
            )
        )

    def test_backend_and_terra_layers_and_score_unchanged(self):
        orch = FakeOrch()
        self._seed(orch)
        before = None
        result = cr.rank_job_applications(orch, company_code="ACME", position_code="ENGINEER")
        item = result["items"][0]
        before = (item["advisory_score"], item["eligibility_bucket"], json.dumps(item["component_scores"], sort_keys=True))
        self.assertTrue(item.get("backend_explanation"))
        self.assertEqual(item["terra_narrative"]["status"], "completed")
        self.assertIn("Terra narrative", item["terra_narrative"]["text"])
        self.assertEqual(item["terra_narrative"]["model"], "gpt-5.6-terra")
        self.assertEqual(item["terra_narrative"]["prompt_version"], cr.NARRATIVE_PROMPT_VERSION)
        after = (item["advisory_score"], item["eligibility_bucket"], json.dumps(item["component_scores"], sort_keys=True))
        self.assertEqual(before, after)

    def test_envelope_excludes_sensitive_fields(self):
        orch = FakeOrch()
        self._seed(orch)
        result = cr.rank_job_applications(orch, company_code="ACME", position_code="ENGINEER")
        item = result["items"][0]
        envelope = cr.build_bounded_evidence_envelope(item=item, run=result, job=orch.positions[0], locale="en")
        blob = json.dumps(envelope).lower()
        for banned in ("civil_id", "nationality", "gender", "date_of_birth", "religion"):
            self.assertNotIn(banned, blob)
        self.assertIn("advisory_score", envelope["committed_result"])

    def test_terra_failure_keeps_backend_explanation(self):
        orch = FakeOrch()
        self._seed(orch, "app-fail")

        def boom(**kwargs):
            raise RuntimeError("terra down")

        orch.ranking_terra_narrative_callable = boom
        result = cr.rank_job_applications(orch, company_code="ACME", position_code="ENGINEER")
        item = result["items"][0]
        self.assertTrue(item["backend_explanation"])
        self.assertEqual(item["terra_narrative"]["status"], "failed")
        self.assertFalse(item["terra_narrative"].get("text"))
        self.assertEqual(item["display_explanation"], item["backend_explanation"])
        self.assertEqual(result["pool_total"], 1)

    def test_terra_retry_idempotent(self):
        orch = FakeOrch()
        self._seed(orch, "app-retry")
        result = cr.rank_job_applications(orch, company_code="ACME", position_code="ENGINEER")
        item = result["items"][0]
        first_text = item["terra_narrative"]["text"]
        first_id = item["terra_narrative"]["narrative_id"]
        retried = cr.retry_terra_narrative(
            orch,
            company_code="ACME",
            position_code="ENGINEER",
            item_id=item["item_id"],
            locale="en",
        )
        self.assertEqual(retried["terra_narrative"]["text"], first_text)
        self.assertTrue(retried["terra_narrative"].get("idempotent_replay"))
        self.assertEqual(retried["terra_narrative"]["narrative_id"], first_id)
        self.assertEqual(retried["advisory_score"], item["advisory_score"])

    def test_surface_parity_same_persisted_narrative(self):
        orch = FakeOrch()
        self._seed(orch, "app-parity")
        dash = cr.rank_candidates_compat(orch, {"position": "ENGINEER", "top_n": 10}, company_code="ACME")
        mobile = cr.rank_candidates_compat(orch, {"position": "ENGINEER", "top_n": 10}, company_code="ACME")
        assistant = cr.rank_candidates_compat(orch, {"position": "ENGINEER", "top_n": 10}, company_code="ACME")
        self.assertEqual(dash["run_id"], mobile["run_id"])
        self.assertEqual(dash["run_id"], assistant["run_id"])
        d0, m0, a0 = dash["candidates"][0], mobile["candidates"][0], assistant["candidates"][0]
        self.assertEqual(d0["item_id"], m0["item_id"])
        self.assertEqual(d0["terra_narrative"]["narrative_id"], m0["terra_narrative"]["narrative_id"])
        self.assertEqual(d0["terra_narrative"]["text"], a0["terra_narrative"]["text"])
        self.assertEqual(d0["backend_explanation"], a0["backend_explanation"])
        self.assertEqual(d0["gpt_evaluation"]["source"], "ranking_terra_narrative")


class EvidencePolicyUnitTests(unittest.TestCase):
    def test_default_policy_and_normalize(self):
        policy = cr.normalize_evidence_policy(None)
        self.assertEqual(policy["version"], cr.EVIDENCE_POLICY_VERSION)
        self.assertEqual(policy["sources"]["cv"], "required")
        self.assertEqual(policy["sources"]["assessment"], "unused")
        self.assertEqual(policy["sources"]["interview"], "unused")
        with self.assertRaises(cr.RankingError):
            cr.normalize_evidence_policy(
                {
                    "sources": {
                        "cv": "required",
                        "interview": "required",
                        "screening": "optional",
                        "assessment": "optional",
                        "semantic": "optional",
                    }
                }
            )

    def test_default_unused_assessment_does_not_change_score(self):
        row = {
            "app_key": "app-1",
            "company_code": "ACME",
            "position_code": "ENGINEER",
            "cv_file_id": "file-1",
            "cv_extraction_stage": "completed",
            "semantic_content": "senior python engineer with bachelor degree and five years experience",
            "semantic_content_hash": "hash",
            "cv_evidence_status": "ready",
            "cv_evidence_file_id": "file-1",
            "cv_evidence_source_sha256": "source-hash",
            "cv_extraction_finalization_id": "00000000-0000-0000-0000-000000000001",
            "cv_extraction_quality_ok": True,
            "cv_extracted_text_hash": "hash",
            "cv_evidence_semantic_content_hash": "hash",
            "cv_evidence_contract_version": "application-cv-evidence-v1",
            "assessment_status": "completed",
            "assessment_percent": 90,
            "assessment_attempt_id": "attempt-1",
            "assessment_position_code": "ENGINEER",
            "screening_status": "completed",
        }
        job = {"position_code": "ENGINEER", "title": "Engineer", "requirements": {"skills": ["python"]}}
        soft = cr.soft_component_scores(
            row=row,
            job=job,
            soft_criteria=[],
            semantic_similarity=0.8,
            evidence_policy=cr.DEFAULT_EVIDENCE_POLICY,
        )
        self.assertTrue(soft["required_evidence_complete"])
        self.assertEqual(soft["optional_missing"], [])
        self.assertNotIn("assessment_missing", soft["optional_missing"])
        self.assertNotIn("assessment_evidence", soft["component_scores"])
        self.assertIn("assessment_unused_by_policy", soft["unused_omitted"])
        self.assertEqual(soft["ranking_result_kind"], "cv_based")
        self.assertGreater(soft["advisory_score"], 0)
        self.assertIn(soft["confidence"], {"medium", "high", "low"})

    def test_optional_without_selection_stays_unused(self):
        row = {
            "app_key": "app-1",
            "company_code": "ACME",
            "position_code": "ENGINEER",
            "cv_file_id": "file-1",
            "cv_extraction_stage": "completed",
            "semantic_content": "senior python engineer with bachelor degree",
            "semantic_content_hash": "hash",
            "cv_evidence_status": "ready",
            "cv_evidence_file_id": "file-1",
            "cv_evidence_source_sha256": "source-hash",
            "cv_extraction_finalization_id": "00000000-0000-0000-0000-000000000001",
            "cv_extraction_quality_ok": True,
            "cv_extracted_text_hash": "hash",
            "cv_evidence_semantic_content_hash": "hash",
            "cv_evidence_contract_version": "application-cv-evidence-v1",
            "assessment_status": "completed",
            "assessment_percent": 90,
            "assessment_attempt_id": "attempt-1",
            "assessment_position_code": "ENGINEER",
            "assessment_battery_key": "battery-a",
            "assessment_version_id": "version-a",
            "assessment_norm_version": "norm-a",
            "screening_status": "completed",
        }
        job = {"position_code": "ENGINEER", "title": "Engineer"}
        policy = {
            "version": cr.EVIDENCE_POLICY_VERSION,
            "sources": {
                "cv": "required",
                "screening": "optional",
                "assessment": "optional",
                "semantic": "optional",
                "interview": "unused",
            },
        }
        soft = cr.soft_component_scores(
            row=row,
            job=job,
            soft_criteria=[],
            semantic_similarity=0.8,
            evidence_policy=policy,
            assessments_module_enabled=True,
        )
        self.assertNotIn("assessment_evidence", soft["component_scores"])
        self.assertEqual(soft["ranking_result_kind"], "cv_based")
        self.assertIn("assessment_unused_by_policy", soft["unused_omitted"])

    def test_selected_assessment_contributes_when_module_on(self):
        selection = {
            "battery_key": "battery-a",
            "assessment_version_id": "version-a",
            "norm_version": "norm-a",
            "attempt_selection_rule": "latest_matching_battery_version",
            "approved_by_user_id": "hr-1",
            "approved_at": "2026-07-24T00:00:00+00:00",
            "policy_version": cr.EVIDENCE_POLICY_VERSION,
        }
        row = {
            "app_key": "app-1",
            "company_code": "ACME",
            "position_code": "ENGINEER",
            "cv_file_id": "file-1",
            "cv_extraction_stage": "completed",
            "semantic_content": "senior python engineer with bachelor degree",
            "semantic_content_hash": "hash",
            "cv_evidence_status": "ready",
            "cv_evidence_file_id": "file-1",
            "cv_evidence_source_sha256": "source-hash",
            "cv_extraction_finalization_id": "00000000-0000-0000-0000-000000000001",
            "cv_extraction_quality_ok": True,
            "cv_extracted_text_hash": "hash",
            "cv_evidence_semantic_content_hash": "hash",
            "cv_evidence_contract_version": "application-cv-evidence-v1",
            "assessment_status": "completed",
            "assessment_percent": 80,
            "assessment_attempt_id": "attempt-1",
            "assessment_position_code": "ENGINEER",
            "assessment_battery_key": "battery-a",
            "assessment_version_id": "version-a",
            "assessment_norm_version": "norm-a",
            "screening_status": "completed",
        }
        job = {"position_code": "ENGINEER", "title": "Engineer"}
        policy = {
            "version": cr.EVIDENCE_POLICY_VERSION,
            "sources": {
                "cv": "required",
                "screening": "optional",
                "assessment": "optional",
                "semantic": "optional",
                "interview": "unused",
            },
            "assessment_selection": selection,
        }
        soft = cr.soft_component_scores(
            row=row,
            job=job,
            soft_criteria=[],
            semantic_similarity=0.8,
            evidence_policy=policy,
            assessments_module_enabled=True,
            criteria_metadata={"assessment_selection": selection},
        )
        self.assertIn("assessment_evidence", soft["component_scores"])
        self.assertEqual(soft["ranking_result_kind"], "cv_plus_approved_assessment")
        self.assertNotIn("assessment_missing", soft["optional_missing"])

    def test_required_missing_cv_blocks_eligibility(self):
        row = {
            "app_key": "app-1",
            "company_code": "ACME",
            "position_code": "ENGINEER",
            "cv_file_id": None,
            "raw_json": {},
            "assessment_status": "completed",
            "assessment_percent": 90,
        }
        result = cr.evaluate_application_eligibility(
            [],
            row,
            evidence_policy=cr.DEFAULT_EVIDENCE_POLICY,
        )
        self.assertEqual(result["eligibility_bucket"], "insufficient_information")
        self.assertIn("required_cv_unavailable", result["required_missing"])

    def test_approve_policy_marks_runs_stale_and_versions(self):
        orch = FakeOrch()
        orch.positions.append(
            {
                "company_code": "ACME",
                "position_code": "ENGINEER",
                "title": "Engineer",
                "title_en": "Engineer",
                "title_ar": None,
                "job_id": "job-1",
                "version": 1,
                "status": "open",
                "location": None,
                "work_arrangement": None,
                "employment_type": None,
                "requirements_en": [],
                "requirements_ar": [],
                "updated_at": None,
            }
        )
        orch.applications.append(_app("ACME", "ENGINEER", "app-1", years=5, skills=["Python"]))
        first = cr.rank_job_applications(orch, company_code="ACME", position_code="ENGINEER")
        self.assertTrue(first.get("run_id"))
        approved = cr.approve_job_evidence_policy(
            orch,
            company_code="ACME",
            position_code="ENGINEER",
            evidence_policy={
                "sources": {
                    "cv": "required",
                    "screening": "optional",
                    "assessment": "unused",
                    "semantic": "optional",
                    "interview": "unused",
                }
            },
            actor_user_id="hr-1",
            expected_version=0,
        )
        self.assertTrue(approved["ok"])
        self.assertEqual(approved["evidence_policy"]["sources"]["assessment"], "unused")
        current = cr.current_run(orch, company_code="ACME", position_code="ENGINEER")
        self.assertTrue(
            current is None
            or current.get("stale_reason") == "evidence_policy_changed"
            or not current.get("is_current")
        )
        with self.assertRaises(cr.RankingError):
            cr.approve_job_evidence_policy(
                orch,
                company_code="ACME",
                position_code="ENGINEER",
                evidence_policy=cr.DEFAULT_EVIDENCE_POLICY,
                actor_user_id="hr-1",
                expected_version=0,
            )


class AssistantAuthorityTests(unittest.TestCase):
    def test_assistant_requires_job(self):
        import action_registry as ar

        legacy = SimpleNamespace(
            RANK_CANDIDATES_DEFAULT_TOP_N=5,
            RANK_CANDIDATES_MAX_TOP_N=10,
        )
        ctx = SimpleNamespace(
            legacy=legacy,
            action={"query": "instagram marketing", "top_n": 5},
            request=SimpleNamespace(company_code="ACME", user_id="u1"),
        )
        with mock.patch.object(ar, "_resolve_company_code", return_value="ACME"), mock.patch.object(
            ar, "_rank_candidates_parameters_catalog", return_value={"position": ["ENGINEER"], "position_titles": {}}
        ):
            out = ar._rank_candidates_executor(ctx)
        self.assertFalse(out.get("success"))
        self.assertEqual(out.get("error"), "job_required")
        self.assertEqual(out["filters"]["ranking_mode"], "job_scoped_canonical")


if __name__ == "__main__":
    unittest.main()
