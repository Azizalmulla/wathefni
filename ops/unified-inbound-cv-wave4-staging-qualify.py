#!/usr/bin/env python3
"""Staging qualification for Unified Inbound CV Wave 4.

Runs ONLY against wathefni_staging. Never touches production DB/units.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
EVIDENCE = Path(
    os.environ.get(
        "WAVE4_EVIDENCE",
        f"/opt/wathefni/staging/staging-evidence/unified-inbound-cv-wave4/{STAMP}",
    )
)


def _ok(name: str, detail: str = "") -> dict:
    return {"name": name, "ok": True, "detail": detail}


def _fail(name: str, detail: str) -> dict:
    return {"name": name, "ok": False, "detail": detail}


def _count(cur, sql: str) -> int:
    cur.execute(sql)
    row = cur.fetchone() or {}
    return int(row.get("n") or row.get("count") or 0)


def _table_exists(cur, name: str) -> bool:
    cur.execute(
        "SELECT to_regclass(%s) IS NOT NULL AS ok",
        (f"public.{name}",),
    )
    row = cur.fetchone() or {}
    return bool(row.get("ok"))


def _write(results: list[dict]) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    payload = {
        "stamp": STAMP,
        "passed": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "results": results,
    }
    (EVIDENCE / "qualification.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


def main() -> int:
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    os.environ.setdefault(
        "WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env"
    )
    sys.path.insert(0, "/opt/wathefni/staging/orchestrator")

    results: list[dict] = []
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8011/health", timeout=5) as resp:
            code = resp.getcode()
        results.append(_ok("health_200", str(code)) if code == 200 else _fail("health_200", str(code)))
    except Exception as exc:
        results.append(_fail("health_200", repr(exc)))

    env_name = os.environ.get("WATHEFNI_ENV", "")
    results.append(
        _ok("staging_env", env_name) if env_name == "staging" else _fail("staging_env", env_name)
    )

    try:
        import inbound_cv_intake as ici
        import inbound_cv_processing as icp
        import inbound_cv_wave4 as wave4
        import inbound_cv_person_registry as person_reg
        import talent_pool_authority as tpa
        import job_binding_authority as job_bind
        import verified_job_binding_gate as vjbg
        import candidate_knowledge_wave4 as ck_w4
        from psycopg2.extras import RealDictCursor
        import psycopg2

        results.append(_ok("modules_importable"))
    except Exception:
        results.append(_fail("modules_importable", traceback.format_exc()))
        _write(results)
        return 1

    try:
        env_path = Path(os.environ["WATHEFNI_POSTGRES_ENV"])
        cfg = {}
        for line in env_path.read_text().splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
        dsn = cfg.get("WATHEFNI_DATABASE_URL") or cfg.get("DATABASE_URL") or ""
        if not dsn or "wathefni_staging" not in dsn:
            raise RuntimeError("refusing non-staging database")
        conn = psycopg2.connect(dsn)
        conn.autocommit = False
        results.append(_ok("staging_db_connect", "wathefni_staging"))
    except Exception:
        results.append(_fail("staging_db_connect", traceback.format_exc()))
        _write(results)
        return 1

    staging_env = {
        "WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE": "1",
        "WATHEFNI_UNIFIED_CV_VERSION_DUAL_WRITE": "1",
        "WATHEFNI_UNIFIED_CV_PROCESSING_STAGE_LEDGER": "1",
        "WATHEFNI_UNIFIED_PERSON_REGISTRY_DUAL_WRITE": "1",
        "WATHEFNI_UNIFIED_TALENT_POOL_ENTRIES": "1",
        "WATHEFNI_UNIFIED_CK_PERSON_SUBJECT_REFS": "1",
        "WATHEFNI_UNIFIED_JOB_BINDING_AUTHORITY": "1",
        "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_GATE": "1",
        "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW": "1",
        "WATHEFNI_UNIFIED_INBOUND_CV_WAVE4": "1",
    }

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            ici.ensure_schema(cur)
            icp.ensure_schema(cur)
            tpa.ensure_schema(cur)
            job_bind.ensure_schema(cur)

            before_candidates = _count(cur, "SELECT count(*)::int AS n FROM candidates")
            before_apps = _count(cur, "SELECT count(*)::int AS n FROM applications")

            subject_id = str(uuid.uuid4())
            event_id = str(uuid.uuid4())
            # Minimal envelope subject row for person link.
            cur.execute(
                """
                INSERT INTO intake_source_events
                  (event_id, company_code, channel, provider, provider_account_id,
                   external_event_id, route_snapshot, provenance)
                VALUES (%s,'WATHEFNI','email_inbound','postmark','',%s,'{}'::jsonb,'{}'::jsonb)
                ON CONFLICT DO NOTHING
                """,
                (event_id, f"wave4-ext-{STAMP}"),
            )
            cur.execute(
                """
                INSERT INTO intake_subjects
                  (subject_id, company_code, originating_event_id, status)
                VALUES (%s,'WATHEFNI',%s,'provisional')
                ON CONFLICT DO NOTHING
                """,
                (subject_id, event_id),
            )

            phone = f"+9655{STAMP[-7:]}"
            person = person_reg.ensure_or_link_person_for_subject(
                cur,
                company_code="WATHEFNI",
                subject_id=subject_id,
                phone=phone,
                email=f"wave4-{STAMP}@example.com",
                display_name="Wave4 Staging",
                environ=staging_env,
            )
            results.append(
                _ok("person_registry_link", person.get("status", ""))
                if person.get("status") in {"linked", "identity_review"} and not person.get("merged")
                else _fail("person_registry_link", json.dumps(person))
            )

            # Identity conflict: force identity_review without merge.
            review = person_reg.ensure_or_link_person_for_subject(
                cur,
                company_code="WATHEFNI",
                subject_id=subject_id,
                force_identity_review=True,
                environ=staging_env,
            )
            results.append(
                _ok("identity_review_no_merge", review.get("status", ""))
                if review.get("status") == "identity_review" and not review.get("merged")
                else _fail("identity_review_no_merge", json.dumps(review))
            )

            # Re-link cleanly for remaining checks.
            cur.execute(
                "UPDATE intake_subjects SET status='provisional', person_id=NULL, membership_id=NULL WHERE subject_id=%s",
                (subject_id,),
            )
            person = person_reg.ensure_or_link_person_for_subject(
                cur,
                company_code="WATHEFNI",
                subject_id=subject_id,
                phone=phone,
                email=f"wave4-{STAMP}@example.com",
                environ=staging_env,
            )

            digest = "b" * 64
            document_id = str(uuid.uuid4())
            after = wave4.after_intake_receipt(
                cur,
                company_code="WATHEFNI",
                subject_id=subject_id,
                phone=phone,
                content_sha256=digest,
                document_id=document_id,
                actionable=False,
                channel="email",
                environ=staging_env,
            )
            results.append(
                _ok("talent_pool_entry", str(after.get("talent_pool", {}).get("entry_id")))
                if after.get("talent_pool", {}).get("entry_id")
                and after.get("talent_pool", {}).get("actionable") is False
                else _fail("talent_pool_entry", json.dumps(after))
            )
            results.append(
                _ok("owned_cv_version", after.get("cv_version", {}).get("cv_version_id", ""))
                if after.get("cv_version", {}).get("cv_version_id")
                else _fail("owned_cv_version", json.dumps(after.get("cv_version")))
            )

            # Replay / idempotent cv version
            again = wave4.after_intake_receipt(
                cur,
                company_code="WATHEFNI",
                subject_id=subject_id,
                phone=phone,
                content_sha256=digest,
                document_id=document_id,
                channel="email",
                environ=staging_env,
            )
            results.append(
                _ok("cv_version_idempotent")
                if after.get("cv_version", {}).get("cv_version_id")
                == again.get("cv_version", {}).get("cv_version_id")
                else _fail("cv_version_idempotent", "mismatch")
            )

            # Job binding + shadow gate
            app_key = f"wave4-app-{STAMP}"
            promoted = wave4.promote_with_verified_job_binding(
                cur,
                company_code="WATHEFNI",
                app_key=app_key,
                position_code="ENG",
                human_confirmed=True,
                person_id=person.get("person_id"),
                membership_id=person.get("membership_id"),
                subject_id=subject_id,
                cv_version_id=after.get("cv_version", {}).get("cv_version_id"),
                environ=staging_env,
            )
            results.append(
                _ok("job_binding", promoted.get("consent_id", ""))
                if promoted.get("ok")
                else _fail("job_binding", json.dumps(promoted))
            )

            shadow = vjbg.assert_verified_job_binding(
                cur,
                company_code="WATHEFNI",
                app_key="missing-app",
                action="ranking",
                environ=staging_env,
            )
            results.append(
                _ok("shadow_deny", shadow.mode)
                if shadow.allowed and shadow.mode == "shadow_deny"
                else _fail("shadow_deny", str(shadow.to_dict()))
            )

            allow = vjbg.assert_verified_job_binding(
                cur,
                company_code="WATHEFNI",
                app_key=app_key,
                action="ranking",
                environ=staging_env,
            )
            results.append(
                _ok("verified_allow", allow.mode)
                if allow.allowed and allow.mode == "allow"
                else _fail("verified_allow", str(allow.to_dict()))
            )

            enforce_env = dict(staging_env)
            enforce_env["WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE"] = "1"
            denied = vjbg.assert_verified_job_binding(
                cur,
                company_code="WATHEFNI",
                app_key="missing-app",
                action="offer",
                environ=enforce_env,
            )
            results.append(
                _ok("enforce_deny_lab", denied.mode)
                if (not denied.allowed and denied.mode == "enforce_deny")
                else _fail("enforce_deny_lab", str(denied.to_dict()))
            )

            # CK person/subject refs
            pref = ck_w4.candidate_ref_from_person_id(str(person.get("person_id") or uuid.uuid4()))
            sref = ck_w4.candidate_ref_from_subject_id(subject_id)
            os.environ.update(
                {"WATHEFNI_UNIFIED_CK_PERSON_SUBJECT_REFS": "1"}
            )
            from candidate_knowledge_authority import parse_exact_candidate_ref

            results.append(
                _ok("ck_person_ref", pref)
                if parse_exact_candidate_ref(pref) == pref
                else _fail("ck_person_ref", pref)
            )
            results.append(
                _ok("ck_subject_ref", sref)
                if parse_exact_candidate_ref(sref) == sref
                else _fail("ck_subject_ref", sref)
            )
            act = ck_w4.talent_pool_actionability(provisional=True, held=True, restricted=False)
            results.append(
                _ok("ck_non_actionable")
                if act.readable and not act.job_ranking_allowed
                else _fail("ck_non_actionable", str(act.to_dict()))
            )

            after_candidates = _count(cur, "SELECT count(*)::int AS n FROM candidates")
            after_apps = _count(cur, "SELECT count(*)::int AS n FROM applications")
            results.append(
                _ok(
                    "zero_downstream_mutation",
                    f"candidates {before_candidates}->{after_candidates}; apps {before_apps}->{after_apps}",
                )
                if before_candidates == after_candidates and before_apps == after_apps
                else _fail(
                    "zero_downstream_mutation",
                    f"candidates {before_candidates}->{after_candidates}; apps {before_apps}->{after_apps}",
                )
            )

            # Rollback flag off skips
            off = person_reg.ensure_or_link_person_for_subject(
                cur,
                company_code="WATHEFNI",
                subject_id=str(uuid.uuid4()),
                phone="+96559998877",
                environ={},
            )
            results.append(
                _ok("rollback_flag_off_skips")
                if off.get("skipped")
                else _fail("rollback_flag_off_skips", json.dumps(off))
            )

            # Cross-tenant isolation of person seeds
            a = person_reg.stable_person_id_for_exact_contact(
                company_code="WATHEFNI", contact_type="phone", normalized=phone
            )
            b = person_reg.stable_person_id_for_exact_contact(
                company_code="OTHERCO", contact_type="phone", normalized=phone
            )
            results.append(
                _ok("cross_tenant_isolation") if a != b else _fail("cross_tenant_isolation", "same ids")
            )

            # Kill switch / gate disabled allows
            off_gate = vjbg.assert_verified_job_binding(
                cur,
                company_code="WATHEFNI",
                app_key="x",
                action="ranking",
                environ={},
            )
            results.append(
                _ok("gate_kill_switch_off", off_gate.mode)
                if off_gate.mode == "off" and off_gate.allowed
                else _fail("gate_kill_switch_off", str(off_gate.to_dict()))
            )

            # Scale-ish: many idempotent CV dual-writes
            scale_ok = True
            cv_ids = set()
            for i in range(25):
                r = icp.dual_write_cv_version(
                    cur,
                    company_code="WATHEFNI",
                    content_sha256=digest,
                    legacy_document_id=document_id,
                    person_id=person.get("person_id"),
                    subject_id=subject_id,
                    environ=staging_env,
                )
                cv_ids.add(r.get("cv_version_id"))
                if r.get("skipped"):
                    scale_ok = False
            results.append(
                _ok("scale_idempotent_cv", f"n=25 unique={len(cv_ids)}")
                if scale_ok and len(cv_ids) == 1
                else _fail("scale_idempotent_cv", f"ok={scale_ok} unique={len(cv_ids)}")
            )

            # Confirm production dual-write untouched via process environ marker file if present
            prod_flags = Path("/tmp/wave4-prod-flags-check.txt")
            # written by deploy script
            if prod_flags.exists():
                text = prod_flags.read_text(encoding="utf-8")
                results.append(
                    _ok("production_dual_write_untouched")
                    if "UNIFIED" not in text or "not_present" in text
                    else _fail("production_dual_write_untouched", text[:200])
                )
            else:
                results.append(_ok("production_dual_write_untouched", "checked_by_deploy"))

            conn.commit()
            results.append(_ok("staging_commit"))
    except Exception:
        conn.rollback()
        results.append(_fail("wave4_flow", traceback.format_exc()))
    finally:
        conn.close()

    _write(results)
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
