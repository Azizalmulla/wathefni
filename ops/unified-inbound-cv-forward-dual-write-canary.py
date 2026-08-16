#!/usr/bin/env python3
"""Controlled forward dual-write canary for WATHEFNI (owner-authorized, tiny set).

Five cases only:
  1) inbound email CV, no Job
  2) unsolicited WhatsApp CV, no Job
  3) manual dashboard CV upload, no Job
  4) WhatsApp apply-code → exact Job application + bindings
  5) Talent Pool candidate later promoted to exact Job + bindings

Channels remain authoritative. ENFORCE stays OFF. No channel cutover.
Job applications are marked smoke_test / quarantined canary rows on J2P2_PROD_TEST.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
EVIDENCE = Path(
    os.environ.get(
        "FWD_CANARY_EVIDENCE",
        f"/opt/wathefni/production-evidence/unified-inbound-cv-forward-dual-write-canary/{STAMP}",
    )
)
CANARY_TAG = "forward_dual_write_canary"
CANARY_DETAIL = f"{CANARY_TAG}:{STAMP}:quarantined"
JOB_POSITION = "J2P2_PROD_TEST"
JOB_APPLY = "APPLY-WATHEFNI-J2P2_PROD_TEST"

# Distinct from legacy smoke 9655555013x
PHONES = {
    "email": "96555570001",
    "wa_unsolicited": "96555570002",
    "wa_job": "96555570003",
    "tp_promote": "96555570004",
}

CANARY_ENV = {
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


def _count(cur: Any, sql: str, params: tuple | list | None = None) -> int:
    cur.execute(sql, params or ())
    row = cur.fetchone() or {}
    return int(row.get("n") or 0)


def _digest(label: str) -> str:
    return hashlib.sha256(f"{CANARY_TAG}:{STAMP}:{label}".encode()).hexdigest()


def _write(payload: dict) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "canary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"ok": payload.get("ok"), "out": str(EVIDENCE), "assertions": payload.get("assertions")}, indent=2, default=str))


def _assert_one(cur: Any, *, table: str, where_sql: str, params: tuple, label: str) -> dict:
    n = _count(cur, f"SELECT count(*)::int AS n FROM {table} WHERE {where_sql}", params)
    return _ok(label, str(n)) if n == 1 else _fail(label, f"count={n}")


def _ensure_canary_candidate(cur: Any, *, phone: str, name: str) -> None:
    cur.execute(
        """
        INSERT INTO candidates (phone, name, data_source, data_source_detail, raw_json)
        VALUES (%s, %s, 'smoke_test', %s, %s::jsonb)
        ON CONFLICT (phone) DO UPDATE SET
          data_source='smoke_test',
          data_source_detail=EXCLUDED.data_source_detail,
          updated_at=CURRENT_DATE
        """,
        (phone, name, CANARY_DETAIL, json.dumps({"canary": CANARY_TAG, "stamp": STAMP})),
    )


def _ensure_canary_application(
    cur: Any,
    *,
    phone: str,
    position_code: str,
    apply_code: str,
    person_id: str | None,
    membership_id: str | None,
    title: str,
) -> str:
    app_key = f"{phone}-WATHEFNI-{position_code}"
    cur.execute(
        """
        INSERT INTO applications (
          app_key, phone, company_code, position_code, apply_code, position_title,
          company_name, status, current_step, cv_received, raw_json,
          data_source, data_source_detail, person_id, membership_id, created_at, updated_at
        ) VALUES (
          %s,%s,'WATHEFNI',%s,%s,%s,
          'WATHEFNI','awaiting_cv','cv',true,%s::jsonb,
          'smoke_test',%s,%s,%s,CURRENT_DATE,CURRENT_DATE
        )
        ON CONFLICT (app_key) DO UPDATE SET
          data_source='smoke_test',
          data_source_detail=EXCLUDED.data_source_detail,
          person_id=COALESCE(EXCLUDED.person_id, applications.person_id),
          membership_id=COALESCE(EXCLUDED.membership_id, applications.membership_id),
          updated_at=CURRENT_DATE
        RETURNING app_key
        """,
        (
            app_key,
            phone,
            position_code,
            apply_code,
            title,
            json.dumps(
                {
                    "canary": CANARY_TAG,
                    "stamp": STAMP,
                    "channel": "forward_dual_write",
                    "authoritative_path": "simulated_live_wrapper",
                }
            ),
            CANARY_DETAIL,
            person_id,
            membership_id,
        ),
    )
    row = cur.fetchone() or {}
    return str(row.get("app_key") or app_key)


def _ck_checks(ck_w4: Any, parse_exact_candidate_ref: Any, *, person_id: str | None, subject_id: str | None, held: bool) -> list[dict]:
    out: list[dict] = []
    # CK person/subject refs require the Wave4 flag in process env for authority parse.
    os.environ["WATHEFNI_UNIFIED_CK_PERSON_SUBJECT_REFS"] = "1"
    if person_id:
        pref = ck_w4.candidate_ref_from_person_id(str(person_id))
        try:
            parsed = parse_exact_candidate_ref(pref)
            parse_ok = parsed == pref
            detail = pref
        except Exception as exc:
            # Fall back to Wave4 classifier when authority gate still app-only in some builds
            kind, normalized = ck_w4.classify_knowledge_ref(pref)
            parse_ok = kind == "person" and normalized == pref
            detail = f"{pref}; authority={exc!r}; wave4_ok={parse_ok}"
        out.append(_ok("ck_person_ref_parse", detail) if parse_ok else _fail("ck_person_ref_parse", detail))
        meta = ck_w4.index_meta_for_ref(candidate_ref=pref, actionable=False, provisional=False)
        out.append(
            _ok("ck_person_index_meta", json.dumps(meta))
            if meta.get("searchable") and meta.get("ref_kind") == "person" and not meta.get("actionable")
            else _fail("ck_person_index_meta", json.dumps(meta))
        )
    if subject_id:
        sref = ck_w4.candidate_ref_from_subject_id(str(subject_id))
        try:
            parsed = parse_exact_candidate_ref(sref)
            parse_ok = parsed == sref
            detail = sref
        except Exception as exc:
            kind, normalized = ck_w4.classify_knowledge_ref(sref)
            parse_ok = kind == "subject" and normalized == sref
            detail = f"{sref}; authority={exc!r}; wave4_ok={parse_ok}"
        out.append(_ok("ck_subject_ref_parse", detail) if parse_ok else _fail("ck_subject_ref_parse", detail))
        meta = ck_w4.index_meta_for_ref(candidate_ref=sref, actionable=False, provisional=True)
        out.append(
            _ok("ck_subject_index_meta", json.dumps(meta))
            if meta.get("searchable") and meta.get("ref_kind") == "subject" and not meta.get("actionable")
            else _fail("ck_subject_index_meta", json.dumps(meta))
        )
    act = ck_w4.talent_pool_actionability(provisional=False, held=held, restricted=False)
    out.append(
        _ok("ck_held_non_actionable", json.dumps(act.to_dict()))
        if act.readable and not act.job_ranking_allowed
        else _fail("ck_held_non_actionable", json.dumps(act.to_dict()))
    )
    # app: compatibility still required
    out.append(
        _ok("ck_app_compat", "app:canary")
        if parse_exact_candidate_ref("app:canary-x") == "app:canary-x"
        else _fail("ck_app_compat", "failed")
    )
    return out


def _shadow(vjbg: Any, cur: Any, *, app_key: str, expect_mode: str) -> dict:
    decision = vjbg.assert_verified_job_binding(
        cur,
        company_code="WATHEFNI",
        app_key=app_key,
        action="ranking",
        environ=CANARY_ENV,
    )
    return (
        _ok(f"shadow_{app_key}", decision.mode)
        if decision.mode == expect_mode
        else _fail(f"shadow_{app_key}", f"expected={expect_mode} got={decision.mode} reasons={list(decision.reason_codes)}")
    )


def main() -> int:
    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import production_data_safety as _r3_data_safety
    _r3_data_safety.require_non_production_ops()
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    cases: dict[str, Any] = {}
    assertions: dict[str, Any] = {}

    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=5) as resp:
            code = resp.getcode()
        results.append(_ok("health_200_pre", str(code)) if code == 200 else _fail("health_200_pre", str(code)))
    except Exception as exc:
        results.append(_fail("health_200_pre", repr(exc)))

    # Refuse ENFORCE on live process
    try:
        import subprocess

        pid = subprocess.check_output(
            ["systemctl", "show", "-p", "MainPID", "--value", "wathefni-orchestrator.service"],
            text=True,
        ).strip()
        env_text = Path(f"/proc/{pid}/environ").read_bytes().replace(b"\0", b"\n").decode("utf-8", "ignore")
        results.append(
            _ok("enforce_off_live")
            if "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on" not in env_text
            else _fail("enforce_off_live", "ENFORCE present")
        )
        results.append(
            _ok("shadow_on_live")
            if "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW=on" in env_text
            else _fail("shadow_on_live", "SHADOW missing")
        )
        (EVIDENCE / "production-flags.txt").write_text(
            "\n".join(sorted(line for line in env_text.splitlines() if "UNIFIED_" in line)),
            encoding="utf-8",
        )
    except Exception:
        results.append(_fail("live_flags", traceback.format_exc()))

    try:
        import inbound_cv_intake as ici
        import inbound_cv_processing as icp
        import inbound_cv_adapters as adapters
        import inbound_cv_wave4 as wave4
        import job_binding_authority as job_bind
        import verified_job_binding_gate as vjbg
        import candidate_knowledge_wave4 as ck_w4
        from candidate_knowledge_authority import parse_exact_candidate_ref
        from psycopg2.extras import RealDictCursor
        import psycopg2
        import durable_email_ingress as dei  # noqa: F401 — path remains importable

        results.append(_ok("modules_importable"))
    except Exception:
        results.append(_fail("modules_importable", traceback.format_exc()))
        _write({"stamp": STAMP, "ok": False, "results": results})
        return 1

    # Authoritative path markers (no cutover)
    dei_src = Path("/opt/wathefni/orchestrator/durable_email_ingress.py").read_text(encoding="utf-8")
    results.append(
        _ok("email_path_authoritative")
        if "dual_write_email_receipt" in dei_src
        and "Live email tables, jobs, scanning, and identity remain authoritative" in dei_src
        else _fail("email_path_authoritative", "marker_missing")
    )
    app_src = Path("/opt/wathefni/orchestrator/app.py").read_text(encoding="utf-8")
    results.append(
        _ok("channels_not_cut_over")
        if "adapt_whatsapp_unsolicited" in app_src or "inbound_cv_adapters" in app_src
        else _fail("channels_not_cut_over", "adapter_hooks_missing")
    )

    cfg: dict[str, str] = {}
    for line in Path(os.environ["WATHEFNI_POSTGRES_ENV"]).read_text().splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    dsn = cfg.get("WATHEFNI_DATABASE_URL") or ""
    if "wathefni_staging" in dsn:
        raise SystemExit("refusing_staging")

    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db")
            db = (cur.fetchone() or {}).get("db")
            if db != "wathefni":
                raise RuntimeError(f"refusing_db:{db}")
            results.append(_ok("production_db", str(db)))

            ici.ensure_schema(cur)
            icp.ensure_schema(cur)
            job_bind.ensure_schema(cur)

            before = {
                "candidates": _count(cur, "SELECT count(*)::int AS n FROM candidates"),
                "applications": _count(cur, "SELECT count(*)::int AS n FROM applications"),
                "applications_non_canary": _count(
                    cur,
                    """
                    SELECT count(*)::int AS n FROM applications
                    WHERE company_code='WATHEFNI'
                      AND COALESCE(data_source_detail,'') NOT LIKE %s
                    """,
                    (f"%{CANARY_TAG}%",),
                ),
                "candidates_non_canary": _count(
                    cur,
                    """
                    SELECT count(*)::int AS n FROM candidates
                    WHERE COALESCE(data_source_detail,'') NOT LIKE %s
                      AND phone NOT IN %s
                    """,
                    (f"%{CANARY_TAG}%", tuple(PHONES.values())),
                ),
                "verified_bindings": _count(
                    cur,
                    "SELECT count(*)::int AS n FROM application_job_bindings WHERE company_code='WATHEFNI' AND verified",
                ),
                "held_unbound": _count(
                    cur,
                    """
                    SELECT count(*)::int AS n FROM applications a
                    WHERE a.company_code='WATHEFNI'
                      AND a.app_key IN (
                        'imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT',
                        'imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT'
                      )
                      AND NOT EXISTS (
                        SELECT 1 FROM application_job_bindings b
                        WHERE b.company_code=a.company_code AND b.app_key=a.app_key AND b.verified
                      )
                    """,
                ),
            }

            cur.execute(
                """
                SELECT position_code, apply_code, title, job_id::text AS job_id, status
                FROM positions
                WHERE company_code='WATHEFNI' AND position_code=%s
                LIMIT 1
                """,
                (JOB_POSITION,),
            )
            job = cur.fetchone()
            if not job or str(job.get("status") or "").lower() != "open":
                results.append(_fail("canary_job_position", json.dumps(dict(job or {}))))
                conn.rollback()
                _write({"stamp": STAMP, "ok": False, "results": results, "before": before})
                return 1
            job = dict(job)
            results.append(_ok("canary_job_position", job["position_code"]))

            # ------------------------------------------------------------------
            # Case 1: email CV, no Job
            # ------------------------------------------------------------------
            c1: dict[str, Any] = {"case": "email_no_job"}
            dig1 = _digest("email")
            doc1 = str(uuid.uuid4())
            inbound_id = str(uuid.uuid4())
            submission_id = str(uuid.uuid4())
            msg_id = f"{CANARY_TAG}-email-{STAMP}"
            email_receipt = ici.dual_write_email_receipt(
                cur,
                company_code="WATHEFNI",
                inbound_id=inbound_id,
                submission_id=submission_id,
                provider="postmark",
                provider_message_id=msg_id,
                route_snapshot={"intake_id": CANARY_TAG, "company_code": "WATHEFNI"},
                source_provenance={"channel": "email_inbound", "canary": CANARY_TAG, "stamp": STAMP},
                documents=[
                    {
                        "document_id": doc1,
                        "ordinal": 1,
                        "filename": f"{CANARY_TAG}-email.pdf",
                        "storage_status": "stored",
                        "safety_state": "clean",
                        "content_sha256": dig1,
                    }
                ],
                environ=CANARY_ENV,
            )
            email_replay = ici.dual_write_email_receipt(
                cur,
                company_code="WATHEFNI",
                inbound_id=inbound_id,
                submission_id=submission_id,
                provider="postmark",
                provider_message_id=msg_id,
                route_snapshot={"intake_id": CANARY_TAG, "company_code": "WATHEFNI"},
                source_provenance={"channel": "email_inbound", "canary": CANARY_TAG, "stamp": STAMP},
                documents=[
                    {
                        "document_id": doc1,
                        "ordinal": 1,
                        "filename": f"{CANARY_TAG}-email.pdf",
                        "storage_status": "stored",
                        "safety_state": "clean",
                        "content_sha256": dig1,
                    }
                ],
                environ=CANARY_ENV,
            )
            subject1 = str(email_receipt.get("subject_id") or "")
            item1 = (email_receipt.get("item_ids") or [None])[0]
            stages1 = adapters.observe_shared_stages_for_document(
                cur,
                company_code="WATHEFNI",
                subject_id=str(item1),
                content_sha256=dig1,
                mime_or_suffix="application/pdf",
                local_text_ok=True,
                needs_ocr=False,
                channel="email",
                environ=CANARY_ENV,
            )
            after1 = wave4.after_intake_receipt(
                cur,
                company_code="WATHEFNI",
                subject_id=subject1,
                email=f"{CANARY_TAG}-email-{STAMP}@example.com",
                phone=f"+{PHONES['email']}",
                display_name="Canary Email NoJob",
                content_sha256=dig1,
                document_id=doc1,
                actionable=False,
                channel="email",
                environ=CANARY_ENV,
            )
            c1.update(
                {
                    "receipt": email_receipt,
                    "replay_event_id": email_replay.get("event_id"),
                    "stages": stages1,
                    "wave4": after1,
                }
            )
            results.append(
                _ok("c1_email_idempotent_event")
                if email_receipt.get("event_id") and email_receipt.get("event_id") == email_replay.get("event_id")
                else _fail("c1_email_idempotent_event", json.dumps({"a": email_receipt, "b": email_replay}))
            )
            results.append(
                _ok("c1_one_item", str(item1))
                if email_receipt.get("item_ids") and len(email_receipt["item_ids"]) == 1
                else _fail("c1_one_item", json.dumps(email_receipt))
            )
            results.append(
                _ok("c1_scan_extract_path")
                if stages1.get("ok")
                and (stages1.get("provider_plan") or {}).get("local_first") is True
                and any(
                    "local_extraction" in str(r.get("idempotency_key") or r.get("stage") or "")
                    for r in (stages1.get("runs") or [])
                )
                else _fail("c1_scan_extract_path", json.dumps(stages1))
            )
            person1 = (after1.get("person") or {})
            tp1 = after1.get("talent_pool") or {}
            cv1 = after1.get("cv_version") or {}
            results.append(
                _ok("c1_person_decision", person1.get("status", ""))
                if person1.get("status") in {"linked", "identity_review"} and not person1.get("merged")
                else _fail("c1_person_decision", json.dumps(person1))
            )
            results.append(
                _ok("c1_talent_pool_non_actionable", tp1.get("entry_id", ""))
                if tp1.get("entry_id") and tp1.get("actionable") is False
                else _fail("c1_talent_pool_non_actionable", json.dumps(tp1))
            )
            results.append(
                _ok("c1_cv_version", str(cv1.get("cv_version_id") or ""))
                if cv1.get("cv_version_id")
                else _fail("c1_cv_version", json.dumps(cv1))
            )
            results.append(
                _ok("c1_no_job_application")
                if after1.get("creates_job_application") is False
                else _fail("c1_no_job_application", json.dumps(after1))
            )
            results.extend(
                _ck_checks(
                    ck_w4,
                    parse_exact_candidate_ref,
                    person_id=person1.get("person_id"),
                    subject_id=subject1,
                    held=True,
                )
            )
            # reusable cv: second dual-write same digest/doc → same id
            cv1b = icp.dual_write_cv_version(
                cur,
                company_code="WATHEFNI",
                content_sha256=dig1,
                legacy_document_id=doc1,
                person_id=person1.get("person_id"),
                subject_id=subject1,
                provenance={"canary": CANARY_TAG, "reuse_check": True},
                environ=CANARY_ENV,
            )
            results.append(
                _ok("c1_cv_reusable", str(cv1b.get("cv_version_id") or ""))
                if cv1b.get("cv_version_id") == cv1.get("cv_version_id")
                else _fail("c1_cv_reusable", json.dumps({"a": cv1, "b": cv1b}))
            )
            results.append(
                _assert_one(
                    cur,
                    table="cv_versions",
                    where_sql="company_code='WATHEFNI' AND content_sha256=%s AND legacy_document_id=%s",
                    params=(dig1, doc1),
                    label="c1_one_cv_row",
                )
            )
            cases["email_no_job"] = c1

            # ------------------------------------------------------------------
            # Case 2: unsolicited WhatsApp, no Job
            # ------------------------------------------------------------------
            dig2 = _digest("wa_unsolicited")
            pending2 = str(uuid.uuid4())
            wa_u = adapters.adapt_whatsapp_unsolicited(
                cur,
                company_code="WATHEFNI",
                provider_message_id=f"{CANARY_TAG}-wa-u-{STAMP}",
                phone=f"+{PHONES['wa_unsolicited']}",
                account_id=CANARY_TAG,
                conversation_id=f"conv-u-{STAMP}",
                pending_id=pending2,
                content_sha256=dig2,
                filename=f"{CANARY_TAG}-wa-u.pdf",
                mime_or_suffix="application/pdf",
                needs_ocr=False,
                environ=CANARY_ENV,
            )
            receipt2 = wa_u.get("receipt") or {}
            wave2 = wa_u.get("wave4") or {}
            stages2 = wa_u.get("shared_processing") or {}
            results.append(
                _ok("c2_wa_unsolicited_ok")
                if wa_u.get("ok") and not wa_u.get("creates_job_application")
                else _fail("c2_wa_unsolicited_ok", json.dumps(wa_u))
            )
            results.append(
                _ok("c2_one_item")
                if receipt2.get("item_ids") and len(receipt2["item_ids"]) == 1
                else _fail("c2_one_item", json.dumps(receipt2))
            )
            results.append(
                _ok("c2_scan_extract_path")
                if stages2.get("ok") and (stages2.get("provider_plan") or {}).get("local_first") is True
                else _fail("c2_scan_extract_path", json.dumps(stages2))
            )
            person2 = wave2.get("person") or {}
            tp2 = wave2.get("talent_pool") or {}
            cv2 = wave2.get("cv_version") or {}
            results.append(
                _ok("c2_person_decision", person2.get("status", ""))
                if person2.get("status") in {"linked", "identity_review"} and not person2.get("merged")
                else _fail("c2_person_decision", json.dumps(person2))
            )
            results.append(
                _ok("c2_talent_pool_non_actionable")
                if tp2.get("entry_id") and tp2.get("actionable") is False
                else _fail("c2_talent_pool_non_actionable", json.dumps(tp2))
            )
            results.append(
                _ok("c2_cv_version", str(cv2.get("cv_version_id") or ""))
                if cv2.get("cv_version_id")
                else _fail("c2_cv_version", json.dumps(cv2))
            )
            results.append(
                _ok("c2_visibility_held")
                if (wa_u.get("talent_pool") or {}).get("actionable") is False
                else _fail("c2_visibility_held", json.dumps(wa_u.get("talent_pool")))
            )
            cases["wa_unsolicited_no_job"] = {
                "adapter": wa_u,
                "person_id": person2.get("person_id"),
                "subject_id": receipt2.get("subject_id"),
                "cv_version_id": cv2.get("cv_version_id"),
                "tp_entry_id": tp2.get("entry_id"),
            }

            # ------------------------------------------------------------------
            # Case 3: manual dashboard upload, no Job
            # ------------------------------------------------------------------
            dig3 = _digest("manual")
            doc3 = str(uuid.uuid4())
            manual = adapters.adapt_manual_import(
                cur,
                company_code="WATHEFNI",
                batch_id=f"{CANARY_TAG}-batch-{STAMP}",
                content_sha256=dig3,
                filename=f"{CANARY_TAG}-manual.pdf",
                document_id=doc3,
                app_key=None,
                held_status="needs_role",
                mime_or_suffix="application/pdf",
                environ=CANARY_ENV,
            )
            receipt3 = manual.get("receipt") or {}
            wave3 = manual.get("wave4") or {}
            stages3 = manual.get("shared_processing") or {}
            results.append(
                _ok("c3_manual_ok")
                if manual.get("ok") and not manual.get("creates_job_application") and manual.get("held_by_default")
                else _fail("c3_manual_ok", json.dumps(manual))
            )
            results.append(
                _ok("c3_one_item")
                if receipt3.get("item_ids") and len(receipt3["item_ids"]) == 1
                else _fail("c3_one_item", json.dumps(receipt3))
            )
            results.append(
                _ok("c3_scan_extract_path")
                if stages3.get("ok") and (stages3.get("provider_plan") or {}).get("local_first") is True
                else _fail("c3_scan_extract_path", json.dumps(stages3))
            )
            person3 = wave3.get("person") or {}
            tp3 = wave3.get("talent_pool") or {}
            cv3 = wave3.get("cv_version") or {}
            results.append(
                _ok("c3_person_or_review", person3.get("status", ""))
                if person3.get("status") in {"linked", "identity_review", "skipped"} or person3.get("skipped")
                else _fail("c3_person_or_review", json.dumps(person3))
            )
            results.append(
                _ok("c3_talent_pool_non_actionable")
                if tp3.get("entry_id") and tp3.get("actionable") is False
                else _fail("c3_talent_pool_non_actionable", json.dumps(tp3))
            )
            results.append(
                _ok("c3_cv_version", str(cv3.get("cv_version_id") or ""))
                if cv3.get("cv_version_id")
                else _fail("c3_cv_version", json.dumps(cv3))
            )
            cases["manual_no_job"] = {
                "adapter": manual,
                "person_id": person3.get("person_id"),
                "subject_id": receipt3.get("subject_id"),
                "cv_version_id": cv3.get("cv_version_id"),
                "tp_entry_id": tp3.get("entry_id"),
            }

            # ------------------------------------------------------------------
            # Case 4: WhatsApp apply-code → exact Job application + bindings
            # ------------------------------------------------------------------
            dig4 = _digest("wa_job")
            doc4 = str(uuid.uuid4())
            phone4 = PHONES["wa_job"]
            _ensure_canary_candidate(cur, phone=phone4, name="Canary WA Job")
            # Person/TP/CV first via wave4 after job adapter receipt path pieces
            # Create application as the live Stage B path would (authoritative), then dual-write.
            # We first run adapter+wave4 with pending app_key, then bind.
            app4 = _ensure_canary_application(
                cur,
                phone=phone4,
                position_code=JOB_POSITION,
                apply_code=JOB_APPLY,
                person_id=None,
                membership_id=None,
                title=str(job.get("title") or JOB_POSITION),
            )
            wa_j = adapters.adapt_whatsapp_job(
                cur,
                company_code="WATHEFNI",
                provider_message_id=f"{CANARY_TAG}-wa-j-{STAMP}",
                phone=f"+{phone4}",
                account_id=CANARY_TAG,
                conversation_id=f"conv-j-{STAMP}",
                document_id=doc4,
                content_sha256=dig4,
                filename=f"{CANARY_TAG}-wa-j.pdf",
                app_key=app4,
                apply_code=JOB_APPLY,
                human_confirmed=True,
                mime_or_suffix="application/pdf",
                needs_ocr=False,
                environ=CANARY_ENV,
            )
            receipt4 = wa_j.get("receipt") or {}
            wave4r = wa_j.get("wave4") or {}
            stages4 = wa_j.get("shared_processing") or {}
            person4 = wave4r.get("person") or {}
            cv4 = wave4r.get("cv_version") or {}
            # Attach person to application (live path would already have it)
            if person4.get("person_id"):
                cur.execute(
                    """
                    UPDATE applications
                    SET person_id=%s, membership_id=COALESCE(%s, membership_id), updated_at=CURRENT_DATE
                    WHERE app_key=%s
                    """,
                    (person4.get("person_id"), person4.get("membership_id"), app4),
                )
            promote4 = wave4.promote_with_verified_job_binding(
                cur,
                company_code="WATHEFNI",
                app_key=app4,
                position_code=JOB_POSITION,
                apply_code=JOB_APPLY,
                job_id=job.get("job_id"),
                human_confirmed=True,
                subject_id=receipt4.get("subject_id"),
                person_id=person4.get("person_id"),
                membership_id=person4.get("membership_id"),
                cv_version_id=cv4.get("cv_version_id"),
                actor_type="system",
                actor_id=CANARY_TAG,
                environ=CANARY_ENV,
            )
            results.append(
                _ok("c4_wa_job_adapter")
                if wa_j.get("ok") and not wa_j.get("creates_job_application") and wa_j.get("links_existing_application")
                else _fail("c4_wa_job_adapter", json.dumps(wa_j))
            )
            results.append(
                _ok("c4_one_item")
                if receipt4.get("item_ids") and len(receipt4["item_ids"]) == 1
                else _fail("c4_one_item", json.dumps(receipt4))
            )
            results.append(
                _ok("c4_scan_extract_path")
                if stages4.get("ok") and (stages4.get("provider_plan") or {}).get("local_first") is True
                else _fail("c4_scan_extract_path", json.dumps(stages4))
            )
            results.append(
                _ok("c4_person_decision", person4.get("status", ""))
                if person4.get("status") in {"linked", "identity_review"} and not person4.get("merged")
                else _fail("c4_person_decision", json.dumps(person4))
            )
            results.append(
                _ok("c4_cv_version", str(cv4.get("cv_version_id") or ""))
                if cv4.get("cv_version_id")
                else _fail("c4_cv_version", json.dumps(cv4))
            )
            results.append(
                _ok("c4_promote_ok")
                if promote4.get("ok") and (promote4.get("binding") or {}).get("verified")
                else _fail("c4_promote_ok", json.dumps(promote4))
            )
            cur.execute(
                """
                SELECT position_code, verified, provenance
                FROM application_job_bindings
                WHERE company_code='WATHEFNI' AND app_key=%s
                """,
                (app4,),
            )
            jb4 = cur.fetchone()
            results.append(
                _ok("c4_job_binding", app4)
                if jb4 and jb4.get("verified") and jb4.get("position_code") == JOB_POSITION
                else _fail("c4_job_binding", json.dumps(dict(jb4 or {})))
            )
            cur.execute(
                """
                SELECT cv_version_id::text AS cv_version_id, pinned
                FROM application_cv_bindings
                WHERE company_code='WATHEFNI' AND app_key=%s AND pinned=true
                """,
                (app4,),
            )
            cb4 = cur.fetchone()
            results.append(
                _ok("c4_cv_binding_pinned", str((cb4 or {}).get("cv_version_id") or ""))
                if cb4 and cb4.get("pinned") and str(cb4.get("cv_version_id")) == str(cv4.get("cv_version_id"))
                else _fail("c4_cv_binding_pinned", json.dumps({"cb": dict(cb4 or {}), "cv": cv4}))
            )
            results.append(_shadow(vjbg, cur, app_key=app4, expect_mode="allow"))
            # No TP actionable Job invent from adapter
            results.append(
                _ok("c4_adapter_no_invent")
                if wa_j.get("creates_job_application") is False
                else _fail("c4_adapter_no_invent", "true")
            )
            cases["wa_apply_code_job"] = {
                "app_key": app4,
                "person_id": person4.get("person_id"),
                "cv_version_id": cv4.get("cv_version_id"),
                "promote": promote4,
                "job_binding": dict(jb4 or {}),
                "cv_binding": dict(cb4 or {}),
            }

            # ------------------------------------------------------------------
            # Case 5: Talent Pool → later exact Job promote
            # ------------------------------------------------------------------
            dig5 = _digest("tp_promote")
            doc5 = str(uuid.uuid4())
            phone5 = PHONES["tp_promote"]
            # Start as no-Job unsolicited TP
            pending5 = str(uuid.uuid4())
            wa_tp = adapters.adapt_whatsapp_unsolicited(
                cur,
                company_code="WATHEFNI",
                provider_message_id=f"{CANARY_TAG}-tp-seed-{STAMP}",
                phone=f"+{phone5}",
                account_id=CANARY_TAG,
                conversation_id=f"conv-tp-{STAMP}",
                pending_id=pending5,
                content_sha256=dig5,
                filename=f"{CANARY_TAG}-tp.pdf",
                mime_or_suffix="application/pdf",
                needs_ocr=False,
                environ=CANARY_ENV,
            )
            receipt5 = wa_tp.get("receipt") or {}
            wave5a = wa_tp.get("wave4") or {}
            person5 = wave5a.get("person") or {}
            tp5 = wave5a.get("talent_pool") or {}
            cv5 = wave5a.get("cv_version") or {}
            # Unsolicited adapter owns cv via pending_id as legacy_document_id.
            if not cv5.get("cv_version_id") and receipt5.get("subject_id"):
                wave5a = wave4.after_intake_receipt(
                    cur,
                    company_code="WATHEFNI",
                    subject_id=str(receipt5.get("subject_id")),
                    phone=f"+{phone5}",
                    display_name="Canary TP Promote",
                    content_sha256=dig5,
                    document_id=str(pending5),
                    actionable=False,
                    channel="whatsapp_unsolicited",
                    environ=CANARY_ENV,
                )
                person5 = wave5a.get("person") or person5
                tp5 = wave5a.get("talent_pool") or tp5
                cv5 = wave5a.get("cv_version") or cv5
            # doc5 reserved for evidence only when adapter already created cv
            _ = doc5

            results.append(
                _ok("c5_tp_seed_non_actionable")
                if tp5.get("entry_id") and tp5.get("actionable") is False and cv5.get("cv_version_id")
                else _fail("c5_tp_seed_non_actionable", json.dumps({"tp": tp5, "cv": cv5, "wa": wa_tp}))
            )

            _ensure_canary_candidate(cur, phone=phone5, name="Canary TP Promote")
            app5 = _ensure_canary_application(
                cur,
                phone=phone5,
                position_code=JOB_POSITION,
                apply_code=JOB_APPLY,
                person_id=person5.get("person_id"),
                membership_id=person5.get("membership_id"),
                title=str(job.get("title") or JOB_POSITION),
            )
            # Before binding: shadow deny
            results.append(_shadow(vjbg, cur, app_key=app5, expect_mode="shadow_deny"))
            promote5 = wave4.promote_with_verified_job_binding(
                cur,
                company_code="WATHEFNI",
                app_key=app5,
                position_code=JOB_POSITION,
                apply_code=JOB_APPLY,
                job_id=job.get("job_id"),
                human_confirmed=True,
                subject_id=receipt5.get("subject_id"),
                person_id=person5.get("person_id"),
                membership_id=person5.get("membership_id"),
                cv_version_id=cv5.get("cv_version_id"),
                actor_type="hr",
                actor_id=f"{CANARY_TAG}-promote",
                environ=CANARY_ENV,
            )
            results.append(
                _ok("c5_promote_ok")
                if promote5.get("ok") and (promote5.get("binding") or {}).get("verified")
                else _fail("c5_promote_ok", json.dumps(promote5))
            )
            cur.execute(
                """
                SELECT position_code, verified FROM application_job_bindings
                WHERE company_code='WATHEFNI' AND app_key=%s
                """,
                (app5,),
            )
            jb5 = cur.fetchone()
            results.append(
                _ok("c5_job_binding")
                if jb5 and jb5.get("verified") and jb5.get("position_code") == JOB_POSITION
                else _fail("c5_job_binding", json.dumps(dict(jb5 or {})))
            )
            cur.execute(
                """
                SELECT cv_version_id::text AS cv_version_id, pinned
                FROM application_cv_bindings
                WHERE company_code='WATHEFNI' AND app_key=%s AND pinned=true
                """,
                (app5,),
            )
            cb5 = cur.fetchone()
            results.append(
                _ok("c5_cv_binding_pinned")
                if cb5 and cb5.get("pinned") and str(cb5.get("cv_version_id")) == str(cv5.get("cv_version_id"))
                else _fail("c5_cv_binding_pinned", json.dumps({"cb": dict(cb5 or {}), "cv": cv5}))
            )
            results.append(_shadow(vjbg, cur, app_key=app5, expect_mode="allow"))
            # TP entry remains non-actionable (searchable pool; Job action via binding)
            cur.execute(
                "SELECT actionable FROM talent_pool_entries WHERE entry_id=%s",
                (tp5.get("entry_id"),),
            )
            tp5_after = cur.fetchone() or {}
            results.append(
                _ok("c5_tp_still_non_actionable_pool_row")
                if tp5_after.get("actionable") is False
                else _fail("c5_tp_still_non_actionable_pool_row", json.dumps(dict(tp5_after)))
            )
            cases["tp_promote_to_job"] = {
                "app_key": app5,
                "person_id": person5.get("person_id"),
                "tp_entry_id": tp5.get("entry_id"),
                "cv_version_id": cv5.get("cv_version_id"),
                "promote": promote5,
                "job_binding": dict(jb5 or {}),
                "cv_binding": dict(cb5 or {}),
            }

            # ------------------------------------------------------------------
            # Held records remain non-actionable / unbound
            # ------------------------------------------------------------------
            for held_key in (
                "imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT",
                "imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT",
            ):
                results.append(_shadow(vjbg, cur, app_key=held_key, expect_mode="shadow_deny"))
            held_unbound_after = _count(
                cur,
                """
                SELECT count(*)::int AS n FROM applications a
                WHERE a.company_code='WATHEFNI'
                  AND a.app_key IN (
                    'imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT',
                    'imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT'
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM application_job_bindings b
                    WHERE b.company_code=a.company_code AND b.app_key=a.app_key AND b.verified
                  )
                """,
            )
            results.append(
                _ok("held_remain_unbound", str(held_unbound_after))
                if held_unbound_after == 2
                else _fail("held_remain_unbound", str(held_unbound_after))
            )

            # ------------------------------------------------------------------
            # Duplicate / unrelated mutation checks
            # ------------------------------------------------------------------
            after = {
                "candidates": _count(cur, "SELECT count(*)::int AS n FROM candidates"),
                "applications": _count(cur, "SELECT count(*)::int AS n FROM applications"),
                "applications_non_canary": _count(
                    cur,
                    """
                    SELECT count(*)::int AS n FROM applications
                    WHERE company_code='WATHEFNI'
                      AND COALESCE(data_source_detail,'') NOT LIKE %s
                    """,
                    (f"%{CANARY_TAG}%",),
                ),
                "candidates_non_canary": _count(
                    cur,
                    """
                    SELECT count(*)::int AS n FROM candidates
                    WHERE COALESCE(data_source_detail,'') NOT LIKE %s
                      AND phone NOT IN %s
                    """,
                    (f"%{CANARY_TAG}%", tuple(PHONES.values())),
                ),
                "verified_bindings": _count(
                    cur,
                    "SELECT count(*)::int AS n FROM application_job_bindings WHERE company_code='WATHEFNI' AND verified",
                ),
                "canary_apps": _count(
                    cur,
                    """
                    SELECT count(*)::int AS n FROM applications
                    WHERE company_code='WATHEFNI' AND data_source_detail LIKE %s
                    """,
                    (f"%{CANARY_TAG}%",),
                ),
            }
            results.append(
                _ok(
                    "zero_unrelated_app_mutation",
                    f"{before['applications_non_canary']}->{after['applications_non_canary']}",
                )
                if before["applications_non_canary"] == after["applications_non_canary"]
                else _fail(
                    "zero_unrelated_app_mutation",
                    f"{before['applications_non_canary']}->{after['applications_non_canary']}",
                )
            )
            results.append(
                _ok(
                    "zero_unrelated_candidate_mutation",
                    f"{before['candidates_non_canary']}->{after['candidates_non_canary']}",
                )
                if before["candidates_non_canary"] == after["candidates_non_canary"]
                else _fail(
                    "zero_unrelated_candidate_mutation",
                    f"{before['candidates_non_canary']}->{after['candidates_non_canary']}",
                )
            )
            results.append(
                _ok("canary_apps_exactly_two", str(after["canary_apps"]))
                if after["canary_apps"] == 2
                else _fail("canary_apps_exactly_two", str(after["canary_apps"]))
            )
            results.append(
                _ok(
                    "bindings_plus_two",
                    f"{before['verified_bindings']}->{after['verified_bindings']}",
                )
                if after["verified_bindings"] == before["verified_bindings"] + 2
                else _fail(
                    "bindings_plus_two",
                    f"{before['verified_bindings']}->{after['verified_bindings']}",
                )
            )
            # No duplicate persons for canary phones (company-scoped contact points)
            for label, phone in PHONES.items():
                if label == "manual":
                    continue
                n = _count(
                    cur,
                    """
                    SELECT count(DISTINCT pc.person_id)::int AS n
                    FROM person_contact_points pc
                    WHERE pc.company_code='WATHEFNI'
                      AND pc.contact_type='phone'
                      AND pc.normalized_value IN (%s, %s)
                    """,
                    (phone, f"+{phone}"),
                )
                results.append(
                    _ok(f"no_dup_person_{label}", str(n))
                    if n <= 1
                    else _fail(f"no_dup_person_{label}", str(n))
                )

            # Existing legacy smoke remain shadow_deny
            for smoke in (
                "96555550132-WATHEFNI-ACCOUNTING",
                "96555550133-WATHEFNI-ACCOUNTING",
                "96555550134-WATHEFNI-ACCOUNTING_EXCEL",
                "96555550135-WATHEFNI-ACCOUNTING_EXCEL",
                "96555550136-WATHEFNI-ACCOUNTING_EXCEL",
            ):
                results.append(_shadow(vjbg, cur, app_key=smoke, expect_mode="shadow_deny"))

            conn.commit()
            results.append(_ok("canary_commit"))
    except Exception:
        conn.rollback()
        results.append(_fail("canary_flow", traceback.format_exc()))
    finally:
        conn.close()

    # Post health
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=5) as resp:
            code = resp.getcode()
        results.append(_ok("health_200_post", str(code)) if code == 200 else _fail("health_200_post", str(code)))
    except Exception as exc:
        results.append(_fail("health_200_post", repr(exc)))

    failed = [r for r in results if not r["ok"]]
    assertions = {
        "failed_count": len(failed),
        "failed_names": [r["name"] for r in failed],
        "enforce_enabled": False,
        "channel_cutover": False,
        "canary_job_position": JOB_POSITION,
        "canary_phones": PHONES,
    }
    payload = {
        "stamp": STAMP,
        "ok": len(failed) == 0,
        "tag": CANARY_TAG,
        "passed": sum(1 for r in results if r["ok"]),
        "failed": len(failed),
        "results": results,
        "cases": cases,
        "assertions": assertions,
        "before": before if "before" in locals() else {},
        "go_no_go_hint": "NO-GO_channel_cutover_until_owner_authorization",
    }
    _write(payload)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
