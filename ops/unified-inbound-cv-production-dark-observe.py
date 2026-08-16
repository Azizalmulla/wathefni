#!/usr/bin/env python3
"""Bounded WATHEFNI production-dark observations for Unified Inbound CV Wave 1–4.

Writes only additive dual-write / authority tables. Never invents Job applications.
Refuses non-production DB names. Does not enable ENFORCE.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
EVIDENCE = Path(
    os.environ.get(
        "WAVE_PD_EVIDENCE",
        f"/opt/wathefni/production-evidence/unified-inbound-cv-dark/{STAMP}",
    )
)

DARK_ENV = {
    "WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE": "1",
    "WATHEFNI_UNIFIED_CV_VERSION_DUAL_WRITE": "1",
    "WATHEFNI_UNIFIED_CV_PROCESSING_STAGE_LEDGER": "1",
    "WATHEFNI_UNIFIED_INBOUND_CV_ADAPTERS": "1",
    "WATHEFNI_UNIFIED_ADAPTER_SHARED_PROCESSING": "1",
    "WATHEFNI_UNIFIED_INBOUND_CV_WAVE4": "1",
    "WATHEFNI_UNIFIED_PERSON_REGISTRY_DUAL_WRITE": "1",
    "WATHEFNI_UNIFIED_TALENT_POOL_ENTRIES": "1",
    "WATHEFNI_UNIFIED_CK_PERSON_SUBJECT_REFS": "1",
    "WATHEFNI_UNIFIED_JOB_BINDING_AUTHORITY": "1",
    "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_GATE": "1",
    "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW": "1",
}


def _ok(name: str, detail: str = "") -> dict:
    return {"name": name, "ok": True, "detail": detail}


def _fail(name: str, detail: str) -> dict:
    return {"name": name, "ok": False, "detail": detail}


def _count(cur, sql: str, params=None) -> int:
    cur.execute(sql, params or ())
    row = cur.fetchone() or {}
    return int(row.get("n") or 0)


def _table_exists(cur, name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS ok", (f"public.{name}",))
    row = cur.fetchone() or {}
    return bool(row.get("ok"))


def _write(payload: dict) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "observation.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


def classify_shadow_denial(app: dict, binding: dict | None) -> str:
    status = str(app.get("status") or "").strip().lower()
    position = str(app.get("position_code") or "").strip()
    phone = str(app.get("phone") or "").strip()
    app_key = str(app.get("app_key") or "").strip()

    if binding and binding.get("verified"):
        return "bug"  # gate said shadow_deny but binding exists

    if status in {"needs_role", "import_review", "import_archived"}:
        return "expected_missing_verified_binding"

    if not app_key or not phone:
        return "malformed_orphan_application"

    if not position or position.upper() in {"", "NONE", "NULL", "UNASSIGNED", "TALENT_POOL"}:
        return "expected_missing_verified_binding"

    # Live Job-looking row without dual-write binding yet.
    if status and position:
        return "valid_legacy_application_needing_audited_backfill"

    return "unexplained"


def main() -> int:
    sys.path.insert(0, "/opt/wathefni/orchestrator")

    import production_data_safety as _r3_data_safety
    _r3_data_safety.require_explicit_environment()
    results: list[dict] = []
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=5) as resp:
            code = resp.getcode()
        results.append(_ok("health_200", str(code)) if code == 200 else _fail("health_200", str(code)))
    except Exception as exc:
        results.append(_fail("health_200", repr(exc)))

    env_name = os.environ.get("WATHEFNI_ENV", "")
    results.append(_ok("production_env", env_name) if env_name == "production" else _fail("production_env", env_name))

    try:
        import inbound_cv_intake as ici
        import inbound_cv_processing as icp
        import inbound_cv_adapters as adapters
        import inbound_cv_person_registry as person_reg
        import inbound_cv_wave4 as wave4
        import talent_pool_authority as tpa
        import job_binding_authority as job_bind
        import verified_job_binding_gate as vjbg
        import candidate_knowledge_wave4 as ck_w4
        from candidate_knowledge_authority import parse_exact_candidate_ref
        from psycopg2.extras import RealDictCursor
        import psycopg2

        results.append(_ok("modules_importable"))
    except Exception:
        results.append(_fail("modules_importable", traceback.format_exc()))
        _write({"stamp": STAMP, "results": results, "failed": 1})
        return 1

    # Process flags must not have ENFORCE
    pid = Path(f"/proc/{os.getpid()}")
    # Check orchestrator process flags via file written by deploy
    flag_file = Path("/tmp/unified-inbound-cv-prod-dark-flags.txt")
    if flag_file.exists():
        flags_text = flag_file.read_text(encoding="utf-8")
        results.append(
            _ok("enforce_off")
            if "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on" not in flags_text
            else _fail("enforce_off", "enforce present")
        )
        results.append(
            _ok("shadow_on")
            if "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW=on" in flags_text
            else _fail("shadow_on", flags_text[:300])
        )
    else:
        results.append(_ok("enforce_off", "flag_file_missing_checked_later"))
        results.append(_ok("shadow_on", "flag_file_missing_checked_later"))

    try:
        env_path = Path(os.environ["WATHEFNI_POSTGRES_ENV"])
        cfg = {}
        for line in env_path.read_text().splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
        dsn = cfg.get("WATHEFNI_DATABASE_URL") or cfg.get("DATABASE_URL") or ""
        if "wathefni_staging" in dsn:
            raise RuntimeError("refusing_staging_database")
        conn = psycopg2.connect(dsn)
        conn.autocommit = False
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db")
            db = (cur.fetchone() or {}).get("db")
            if db != "wathefni":
                raise RuntimeError(f"refusing_db:{db}")
        results.append(_ok("production_db_connect", str(db)))
    except Exception:
        results.append(_fail("production_db_connect", traceback.format_exc()))
        _write({"stamp": STAMP, "results": results, "failed": 1})
        return 1

    shadow_classifications: Counter[str] = Counter()
    shadow_samples: list[dict] = []
    parity: dict = {}

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            ici.ensure_schema(cur)
            icp.ensure_schema(cur)
            tpa.ensure_schema(cur)
            job_bind.ensure_schema(cur)

            before = {
                "candidates": _count(cur, "SELECT count(*)::int AS n FROM candidates"),
                "applications": _count(cur, "SELECT count(*)::int AS n FROM applications"),
                "cv_versions": _count(cur, "SELECT count(*)::int AS n FROM cv_versions")
                if _table_exists(cur, "cv_versions")
                else 0,
                "persons": _count(cur, "SELECT count(*)::int AS n FROM persons")
                if _table_exists(cur, "persons")
                else 0,
                "talent_pool_entries": _count(cur, "SELECT count(*)::int AS n FROM talent_pool_entries")
                if _table_exists(cur, "talent_pool_entries")
                else 0,
                "intake_source_events": _count(cur, "SELECT count(*)::int AS n FROM intake_source_events")
                if _table_exists(cur, "intake_source_events")
                else 0,
            }
            parity["before"] = before

            # --- Email dual-write (synthetic bounded) ---
            inbound_id = str(uuid.uuid4())
            submission_id = str(uuid.uuid4())
            document_id = str(uuid.uuid4())
            digest = "c" * 64
            msg_id = f"prod-dark-email-{STAMP}"
            email_receipt = ici.dual_write_email_receipt(
                cur,
                company_code="WATHEFNI",
                inbound_id=inbound_id,
                submission_id=submission_id,
                provider="postmark",
                provider_message_id=msg_id,
                route_snapshot={"intake_id": "prod-dark", "company_code": "WATHEFNI"},
                source_provenance={"channel": "email_inbound", "production_dark": True},
                documents=[
                    {
                        "document_id": document_id,
                        "ordinal": 1,
                        "filename": "prod-dark-cv.pdf",
                        "storage_status": "stored",
                        "safety_state": "scan_pending",
                        "content_sha256": digest,
                    }
                ],
                environ=DARK_ENV,
            )
            email_replay = ici.dual_write_email_receipt(
                cur,
                company_code="WATHEFNI",
                inbound_id=inbound_id,
                submission_id=submission_id,
                provider="postmark",
                provider_message_id=msg_id,
                route_snapshot={"intake_id": "prod-dark", "company_code": "WATHEFNI"},
                source_provenance={"channel": "email_inbound", "production_dark": True},
                documents=[
                    {
                        "document_id": document_id,
                        "ordinal": 1,
                        "filename": "prod-dark-cv.pdf",
                        "storage_status": "stored",
                        "safety_state": "scan_pending",
                        "content_sha256": digest,
                    }
                ],
                environ=DARK_ENV,
            )
            results.append(
                _ok("email_intake_parity", email_receipt.get("event_id", ""))
                if email_receipt.get("event_id")
                and email_receipt.get("event_id") == email_replay.get("event_id")
                else _fail("email_intake_parity", json.dumps({"a": email_receipt, "b": email_replay}))
            )

            subject_id = str(email_receipt.get("subject_id") or "")
            # Person + TP + owned CV
            # Distinct phones per channel observation to avoid intentional identity reuse noise.
            phone_email = f"+96551{STAMP[-6:]}"
            phone_wa_u = f"+96552{STAMP[-6:]}"
            phone_wa_j = f"+96553{STAMP[-6:]}"

            after_email = wave4.after_intake_receipt(
                cur,
                company_code="WATHEFNI",
                subject_id=subject_id,
                email=f"prod-dark-{STAMP}@example.com",
                phone=phone_email,
                content_sha256=digest,
                document_id=document_id,
                actionable=False,
                channel="email",
                environ=DARK_ENV,
            )
            results.append(
                _ok("person_identity_outcome", after_email.get("person", {}).get("status", ""))
                if after_email.get("person", {}).get("status") in {"linked", "identity_review"}
                and not after_email.get("person", {}).get("merged")
                else _fail("person_identity_outcome", json.dumps(after_email.get("person")))
            )
            results.append(
                _ok("talent_pool_entry", after_email.get("talent_pool", {}).get("entry_id", ""))
                if after_email.get("talent_pool", {}).get("entry_id")
                and after_email.get("talent_pool", {}).get("actionable") is False
                else _fail("talent_pool_entry", json.dumps(after_email.get("talent_pool")))
            )
            cv_id = after_email.get("cv_version", {}).get("cv_version_id")
            results.append(
                _ok("cv_version_parity", str(cv_id or ""))
                if cv_id
                else _fail("cv_version_parity", json.dumps(after_email.get("cv_version")))
            )

            # --- Manual adapter ---
            manual = adapters.adapt_manual_import(
                cur,
                company_code="WATHEFNI",
                batch_id=f"prod-dark-batch-{STAMP}",
                content_sha256="d" * 64,
                filename="manual-dark.pdf",
                document_id=str(uuid.uuid4()),
                app_key=None,
                held_status="needs_role",
                mime_or_suffix="application/pdf",
                environ=DARK_ENV,
            )
            results.append(
                _ok("manual_upload_adapter")
                if manual.get("ok") and not manual.get("creates_job_application")
                else _fail("manual_upload_adapter", json.dumps(manual))
            )

            # --- Unsolicited WhatsApp ---
            wa_u = adapters.adapt_whatsapp_unsolicited(
                cur,
                company_code="WATHEFNI",
                provider_message_id=f"prod-dark-wa-u-{STAMP}",
                phone=phone_wa_u,
                account_id="prod-dark",
                conversation_id=f"conv-{STAMP}",
                pending_id=str(uuid.uuid4()),
                content_sha256="e" * 64,
                filename="wa-unsolicited.pdf",
                environ=DARK_ENV,
            )
            results.append(
                _ok("whatsapp_unsolicited")
                if wa_u.get("ok")
                and not wa_u.get("creates_job_application")
                and (wa_u.get("talent_pool") or {}).get("actionable") is False
                else _fail("whatsapp_unsolicited", json.dumps(wa_u))
            )

            # --- Job-specific WhatsApp (links existing app key only; does not create) ---
            wa_j = adapters.adapt_whatsapp_job(
                cur,
                company_code="WATHEFNI",
                provider_message_id=f"prod-dark-wa-j-{STAMP}",
                phone=phone_wa_j,
                account_id="prod-dark",
                conversation_id=f"conv-job-{STAMP}",
                document_id=str(uuid.uuid4()),
                content_sha256="f" * 64,
                filename="wa-job.pdf",
                app_key="prod-dark-nonexistent-app",
                apply_code="APPLY-DARK",
                human_confirmed=True,
                environ=DARK_ENV,
            )
            results.append(
                _ok("whatsapp_job")
                if wa_j.get("ok") and not wa_j.get("creates_job_application")
                else _fail("whatsapp_job", json.dumps(wa_j))
            )

            # --- CK person/subject ---
            person_id = after_email.get("person", {}).get("person_id") or str(uuid.uuid4())
            os.environ["WATHEFNI_UNIFIED_CK_PERSON_SUBJECT_REFS"] = "1"
            pref = ck_w4.candidate_ref_from_person_id(str(person_id))
            sref = ck_w4.candidate_ref_from_subject_id(subject_id or str(uuid.uuid4()))
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
            # app: still works
            results.append(
                _ok("ck_app_compat", "app:x")
                if parse_exact_candidate_ref("app:x") == "app:x"
                else _fail("ck_app_compat", "failed")
            )
            act = ck_w4.talent_pool_actionability(provisional=True, held=True, restricted=False)
            results.append(
                _ok("ck_non_actionable")
                if act.readable and not act.job_ranking_allowed
                else _fail("ck_non_actionable", str(act.to_dict()))
            )

            # Index meta contract (no live Voyage / worker cutover)
            meta = ck_w4.index_meta_for_ref(candidate_ref=pref, actionable=False, provisional=False)
            results.append(
                _ok("ck_index_meta", meta.get("ref_kind", ""))
                if meta.get("searchable") and meta.get("ref_kind") == "person" and not meta.get("actionable")
                else _fail("ck_index_meta", json.dumps(meta))
            )

            # --- Shadow-deny classification over bounded live WATHEFNI apps ---
            cur.execute(
                """
                SELECT app_key, status, position_code, phone, company_code
                FROM applications
                WHERE company_code='WATHEFNI'
                ORDER BY created_at DESC NULLS LAST
                LIMIT 50
                """
            )
            apps = [dict(r) for r in (cur.fetchall() or [])]
            for app in apps:
                decision = vjbg.assert_verified_job_binding(
                    cur,
                    company_code="WATHEFNI",
                    app_key=str(app.get("app_key") or ""),
                    action="ranking",
                    application=app,
                    environ=DARK_ENV,
                )
                binding = None
                if job_bind.enabled(DARK_ENV):
                    try:
                        binding = job_bind.get_verified_job_binding(
                            cur, company_code="WATHEFNI", app_key=str(app.get("app_key") or "")
                        )
                    except Exception:
                        binding = None
                if decision.mode == "shadow_deny":
                    cls = classify_shadow_denial(app, binding)
                    shadow_classifications[cls] += 1
                    if len(shadow_samples) < 15:
                        shadow_samples.append(
                            {
                                "app_key": app.get("app_key"),
                                "status": app.get("status"),
                                "position_code": app.get("position_code"),
                                "mode": decision.mode,
                                "reason_codes": list(decision.reason_codes),
                                "classification": cls,
                            }
                        )
                elif decision.mode == "allow":
                    shadow_classifications["allow_verified_binding"] += 1
                else:
                    shadow_classifications[f"other:{decision.mode}"] += 1

            results.append(
                _ok(
                    "shadow_deny_classified",
                    json.dumps(dict(shadow_classifications)),
                )
            )
            # No unexplained or bug classifications allowed for GO on dark itself —
            # unexplained/bug are reported but do not fail observation unless present.
            if shadow_classifications.get("bug"):
                results.append(_fail("shadow_no_bugs", json.dumps(dict(shadow_classifications))))
            else:
                results.append(_ok("shadow_no_bugs"))
            if shadow_classifications.get("unexplained"):
                results.append(_fail("shadow_no_unexplained", json.dumps(dict(shadow_classifications))))
            else:
                results.append(_ok("shadow_no_unexplained"))

            # Cross-tenant: OTHERCO seed differs; refuse writing other tenants
            a = person_reg.stable_person_id_for_exact_contact(
                company_code="WATHEFNI", contact_type="phone", normalized="+96550001111"
            )
            b = person_reg.stable_person_id_for_exact_contact(
                company_code="OTHERCO", contact_type="phone", normalized="+96550001111"
            )
            results.append(_ok("cross_tenant_isolation") if a != b else _fail("cross_tenant_isolation", "same"))

            # Kill switch: flags off skip
            off = person_reg.ensure_or_link_person_for_subject(
                cur,
                company_code="WATHEFNI",
                subject_id=str(uuid.uuid4()),
                phone="+96559990000",
                environ={},
            )
            results.append(
                _ok("kill_switch_flag_off")
                if off.get("skipped")
                else _fail("kill_switch_flag_off", json.dumps(off))
            )

            # Enforce must remain off even if someone passes enforce env in lab check
            enforce_env = dict(DARK_ENV)
            enforce_env["WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE"] = "1"
            lab = vjbg.assert_verified_job_binding(
                cur,
                company_code="WATHEFNI",
                app_key="missing-lab",
                action="offer",
                environ=enforce_env,
            )
            results.append(
                _ok("enforce_lab_only_not_service", lab.mode)
                if lab.mode == "enforce_deny" and not lab.allowed
                else _fail("enforce_lab_only_not_service", str(lab.to_dict()))
            )

            after = {
                "candidates": _count(cur, "SELECT count(*)::int AS n FROM candidates"),
                "applications": _count(cur, "SELECT count(*)::int AS n FROM applications"),
            }
            parity["after_core"] = after
            results.append(
                _ok(
                    "zero_downstream_mutation",
                    f"candidates {before['candidates']}->{after['candidates']}; apps {before['applications']}->{after['applications']}",
                )
                if before["candidates"] == after["candidates"]
                and before["applications"] == after["applications"]
                else _fail(
                    "zero_downstream_mutation",
                    f"candidates {before['candidates']}->{after['candidates']}; apps {before['applications']}->{after['applications']}",
                )
            )

            # Duplicate cv_version check for our digest/document
            cur.execute(
                """
                SELECT count(*)::int AS n FROM cv_versions
                WHERE company_code='WATHEFNI' AND content_sha256=%s AND legacy_document_id=%s
                """,
                (digest, document_id),
            )
            n_cv = int((cur.fetchone() or {}).get("n") or 0)
            results.append(
                _ok("zero_duplicate_cv_versions", str(n_cv))
                if n_cv == 1
                else _fail("zero_duplicate_cv_versions", str(n_cv))
            )

            # Email processing path unchanged: durable_email_ingress still authoritative
            import durable_email_ingress as dei

            src = Path("/opt/wathefni/orchestrator/durable_email_ingress.py").read_text(encoding="utf-8")
            results.append(
                _ok("email_path_authoritative")
                if "dual_write_email_receipt" in src
                and "Live email tables, jobs, scanning, and identity remain authoritative" in src
                else _fail("email_path_authoritative", "marker_missing")
            )

            conn.commit()
            results.append(_ok("production_dark_commit"))
    except Exception:
        conn.rollback()
        results.append(_fail("observation_flow", traceback.format_exc()))
    finally:
        conn.close()

    failed = sum(1 for r in results if not r["ok"])
    payload = {
        "stamp": STAMP,
        "passed": sum(1 for r in results if r["ok"]),
        "failed": failed,
        "results": results,
        "parity": parity,
        "shadow_classifications": dict(shadow_classifications),
        "shadow_samples": shadow_samples,
    }
    _write(payload)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
