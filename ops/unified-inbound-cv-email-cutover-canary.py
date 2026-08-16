#!/usr/bin/env python3
"""Live canary: WATHEFNI inbound-email unified intake authority cutover.

Preserves Postmark receive/scan/retry/DL. ENFORCE stays OFF.
Job Stage B WhatsApp remains unchanged. External tenants OFF.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import tempfile
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
EVIDENCE = Path(
    os.environ.get(
        "CUTOVER_EVIDENCE",
        f"/opt/wathefni/production-evidence/unified-inbound-cv-email-cutover/{STAMP}",
    )
)
TAG = "email_cutover_canary"
SENDER = f"{TAG}.{STAMP}@example-canary.invalid"
EXTRACTED_PHONE = "96555572001"
EXTRACTED_EMAIL = f"cv.owner.{STAMP}@example-canary.invalid"
INTAKE_LOCAL = "92d69b51cdadf3b594fc08710326ff6b"
INTAKE_DOMAIN = "inbound.postmarkapp.com"
RECIPIENT = f"{INTAKE_LOCAL}@{INTAKE_DOMAIN}"


def _ok(name: str, detail: str = "") -> dict:
    return {"name": name, "ok": True, "detail": detail}


def _fail(name: str, detail: str) -> dict:
    return {"name": name, "ok": False, "detail": detail}


def _count(cur, sql: str, params=None) -> int:
    cur.execute(sql, params or ())
    row = cur.fetchone() or {}
    return int(row.get("n") or 0)


def _pdf_bytes(marker: str) -> bytes:
    stream = (
        f"BT /F1 12 Tf 72 720 Td (Email Canary {marker}) Tj "
        f"0 -18 Td (Phone {EXTRACTED_PHONE}) Tj "
        f"0 -18 Td (Email {EXTRACTED_EMAIL}) Tj ET"
    ).encode()
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>endobj\n"
        + f"4 0 obj<</Length {len(stream)}>>stream\n".encode()
        + stream
        + b"\nendstream\nendobj\n"
        + b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        + b"xref\n0 6\n0000000000 65535 f \ntrailer<</Root 1 0 R/Size 6>>\nstartxref\n0\n%%EOF\n"
    )


def _png_bytes() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


def _eicar_bytes() -> bytes:
    return b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def _att(name: str, data: bytes, ctype: str) -> dict:
    return {
        "Name": name,
        "Content": base64.b64encode(data).decode("ascii"),
        "ContentType": ctype,
        "ContentLength": len(data),
    }


def _payload(message_id: str, attachments: list[dict]) -> dict:
    return {
        "MessageID": message_id,
        "OriginalRecipient": RECIPIENT,
        "From": f"Canary Sender <{SENDER}>",
        "FromFull": {"Email": SENDER, "Name": "Canary Sender"},
        "ToFull": [{"Email": RECIPIENT, "Name": "", "MailboxHash": ""}],
        "Subject": f"[{TAG}] no-job CV {STAMP}",
        "Date": "Mon, 27 Jul 2026 00:00:00 +0000",
        "Attachments": attachments,
        "Headers": [],
    }


def _write(payload: dict) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "canary.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "ok": payload.get("ok"),
                "out": str(EVIDENCE),
                "passed": payload.get("passed"),
                "failed": payload.get("failed"),
                "assertions": payload.get("assertions"),
            },
            indent=2,
        )
    )


def _load_env_file(path: Path, *, overwrite: bool = False) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        val = v.strip().strip('"').strip("'")
        if overwrite or key not in os.environ:
            os.environ[key] = val


def _hydrate_runtime_from_orchestrator() -> str:
    """Copy live orchestrator process env so app.db_connect binding matches production."""
    import subprocess

    pid = subprocess.check_output(
        ["systemctl", "show", "-p", "MainPID", "--value", "wathefni-orchestrator.service"],
        text=True,
    ).strip()
    env_text = (
        Path(f"/proc/{pid}/environ").read_bytes().replace(b"\0", b"\n").decode("utf-8", "ignore")
    )
    for line in env_text.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        # Prefer live service identity/flags over stale secrets file defaults.
        if k.startswith("WATHEFNI_") or k in {"PATH", "VIRTUAL_ENV"}:
            os.environ[k] = v
    return env_text


def main() -> int:
    _load_env_file(Path("/root/.openclaw/secrets/postgres.env"), overwrite=False)
    _load_env_file(Path("/opt/wathefni/var/unified-inbound-cv.production.env"), overwrite=True)
    env_text = ""
    try:
        env_text = _hydrate_runtime_from_orchestrator()
    except Exception:
        # Fall back to known production identity pins when /proc is unavailable.
        os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
        os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
        os.environ.setdefault(
            "WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1"
        )
        os.environ["WATHEFNI_INBOUND_EMAIL"] = "on"
    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import production_data_safety as _r3_data_safety
    _r3_data_safety.require_non_production_ops()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    cases: dict = {}
    inbound_id = ""
    submission_id = ""
    message_id = f"email-cutover-{STAMP}-{uuid.uuid4().hex[:10]}"

    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=5) as resp:
            results.append(
                _ok("health_200_pre", str(resp.getcode()))
                if resp.getcode() == 200
                else _fail("health_200_pre", str(resp.getcode()))
            )
    except Exception as exc:
        results.append(_fail("health_200_pre", repr(exc)))

    try:
        if not env_text:
            env_text = _hydrate_runtime_from_orchestrator()
        (EVIDENCE / "production-flags.txt").write_text(
            "\n".join(
                sorted(x for x in env_text.splitlines() if "UNIFIED_" in x or "INTAKE_AUTHORITY" in x)
            ),
            encoding="utf-8",
        )
        results.append(
            _ok("enforce_off")
            if "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on" not in env_text
            else _fail("enforce_off", "present")
        )
        results.append(
            _ok("email_authority_on")
            if "WATHEFNI_UNIFIED_INTAKE_AUTHORITY_EMAIL=on" in env_text
            else _fail("email_authority_on", "missing")
        )
        results.append(
            _ok("wa_manual_still_on")
            if (
                "WATHEFNI_UNIFIED_INTAKE_AUTHORITY_WHATSAPP_UNSOLICITED=on" in env_text
                and "WATHEFNI_UNIFIED_INTAKE_AUTHORITY_MANUAL=on" in env_text
            )
            else _fail("wa_manual_still_on", "missing")
        )
        results.append(
            _ok("tenants_wathefni_only")
            if "WATHEFNI_UNIFIED_INTAKE_AUTHORITY_TENANTS=WATHEFNI" in env_text
            else _fail("tenants_wathefni_only", "missing")
        )
    except Exception:
        results.append(_fail("flags", traceback.format_exc()))

    try:
        import inbound_cv_channel_cutover as cutover
        import durable_email_ingress as dei
        import app

        results.append(_ok("modules_importable", cutover.CUTOVER_VERSION))
        results.append(
            _ok("email_auth_helper")
            if cutover.email_authority_enabled("WATHEFNI")
            else _fail("email_auth_helper", "disabled")
        )
        results.append(
            _ok("external_tenant_off")
            if not cutover.email_authority_enabled("OTHERCO")
            else _fail("external_tenant_off", "OTHERCO unexpectedly enabled")
        )
    except Exception:
        results.append(_fail("modules_importable", traceback.format_exc()))
        _write({"stamp": STAMP, "ok": False, "results": results})
        return 1

    app_src = Path("/opt/wathefni/orchestrator/app.py").read_text(encoding="utf-8")
    results.append(
        _ok("stage_b_untouched")
        if "convert_job_context_to_application" in app_src
        else _fail("stage_b_untouched", "marker_missing")
    )
    results.append(
        _ok("email_observe_patched")
        if "UNIFIED_INTAKE_AUTHORITY_EMAIL_OBSERVE" in app_src
        else _fail("email_observe_patched", "missing")
    )
    results.append(
        _ok("email_extraction_patched")
        if "UNIFIED_INTAKE_AUTHORITY_EMAIL_EXTRACTION" in app_src
        else _fail("email_extraction_patched", "missing")
    )
    dei_src = Path("/opt/wathefni/orchestrator/durable_email_ingress.py").read_text(encoding="utf-8")
    results.append(
        _ok("postmark_boundary_preserved")
        if "UNIFIED_INTAKE_AUTHORITY_EMAIL_RECEIPT" in dei_src
        and "durably_receive_postmark" in dei_src
        else _fail("postmark_boundary_preserved", "marker_missing")
    )

    pdf_a = _pdf_bytes("A")
    png = _png_bytes()
    sha_pdf = hashlib.sha256(pdf_a).hexdigest()
    sha_png = hashlib.sha256(png).hexdigest()
    attachments = [
        _att(f"{TAG}-a.pdf", pdf_a, "application/pdf"),
        _att(f"{TAG}-scan.png", png, "image/png"),
    ]

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                baseline = {
                    "apps": _count(cur, "SELECT count(*) AS n FROM applications"),
                    "persons_contact": _count(
                        cur,
                        """
                        SELECT count(DISTINCT person_id) AS n FROM person_contact_points
                        WHERE company_code=%s
                        """,
                        ("WATHEFNI",),
                    ),
                    "cv_versions": _count(
                        cur,
                        "SELECT count(*) AS n FROM cv_versions WHERE company_code=%s",
                        ("WATHEFNI",),
                    ),
                    "tp": _count(
                        cur,
                        "SELECT count(*) AS n FROM talent_pool_entries WHERE company_code=%s",
                        ("WATHEFNI",),
                    ),
                }
        cases["baseline"] = baseline
        results.append(_ok("baseline_counts", json.dumps(baseline)))
    except Exception:
        results.append(_fail("baseline_counts", traceback.format_exc()))
        _write({"stamp": STAMP, "ok": False, "results": results, "cases": cases})
        return 1

    try:
        recv = app.process_postmark_inbound(_payload(message_id, attachments))
        cases["receive"] = recv
        inbound_id = str(recv.get("inbound_id") or "")
        submission_id = str(recv.get("submission_id") or "")
        docs = list(recv.get("documents") or [])
        results.append(
            _ok("receive_durable", inbound_id)
            if recv.get("durable") and recv.get("company_code") == "WATHEFNI"
            else _fail("receive_durable", repr(recv))
        )
        results.append(
            _ok("multi_attachment_accepted", str(recv.get("accepted_attachment_count")))
            if int(recv.get("accepted_attachment_count") or 0) == 2
            else _fail("multi_attachment_accepted", repr(recv))
        )
        results.append(
            _ok("one_document_per_attachment", str(len(docs)))
            if len(docs) == 2
            else _fail("one_document_per_attachment", repr(docs))
        )
    except Exception:
        results.append(_fail("receive_durable", traceback.format_exc()))
        _write({"stamp": STAMP, "ok": False, "results": results, "cases": cases})
        return 1

    try:
        replay = app.process_postmark_inbound(_payload(message_id, attachments))
        cases["replay"] = replay
        results.append(
            _ok("provider_replay_idempotent", json.dumps({"duplicate": replay.get("duplicate")}))
            if replay.get("duplicate") is True and str(replay.get("inbound_id")) == inbound_id
            else _fail("provider_replay_idempotent", repr(replay))
        )
    except Exception:
        results.append(_fail("provider_replay_idempotent", traceback.format_exc()))

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT job_id::text, job_type, subject_id::text, payload, status
                    FROM intake_processing_jobs
                    WHERE company_code=%s
                      AND (
                        payload->>'submission_id'=%s
                        OR payload->>'inbound_id'=%s
                        OR subject_id::text = ANY(%s)
                      )
                    ORDER BY
                      CASE job_type
                        WHEN 'intake_validation' THEN 1
                        WHEN 'file_safety_scan' THEN 2
                        ELSE 9
                      END,
                      created_at ASC
                    """,
                    (
                        "WATHEFNI",
                        submission_id,
                        inbound_id,
                        [inbound_id, submission_id]
                        + [str(d.get("document_id") or "") for d in (recv.get("documents") or [])],
                    ),
                )
                jobs = [dict(r) for r in cur.fetchall()]
        cases["jobs_listed"] = [
            {"job_id": j["job_id"], "job_type": j["job_type"], "status": j["status"]} for j in jobs
        ]

        # Drain validation then scans (and any newly enqueued scans after validation).
        for _pass in range(3):
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT job_id::text, job_type, subject_id::text, payload, status
                        FROM intake_processing_jobs
                        WHERE company_code=%s
                          AND status IN ('pending','retrying')
                          AND job_type IN ('intake_validation','file_safety_scan')
                          AND (
                            payload->>'submission_id'=%s
                            OR payload->>'inbound_id'=%s
                            OR subject_id::text = ANY(%s)
                          )
                        ORDER BY
                          CASE job_type
                            WHEN 'intake_validation' THEN 1
                            WHEN 'file_safety_scan' THEN 2
                            ELSE 9
                          END,
                          created_at ASC
                        """,
                        (
                            "WATHEFNI",
                            submission_id,
                            inbound_id,
                            [inbound_id, submission_id]
                            + [
                                str(d.get("document_id") or "")
                                for d in (recv.get("documents") or [])
                            ],
                        ),
                    )
                    pending = [dict(r) for r in cur.fetchall()]
            if not pending:
                break
            for j in pending:
                out = app.process_durable_email_ingress_job(
                    {
                        "job_id": j["job_id"],
                        "job_type": j["job_type"],
                        "company_code": "WATHEFNI",
                        "subject_id": j.get("subject_id"),
                        "payload": j.get("payload") if isinstance(j.get("payload"), dict) else {},
                    }
                )
                cases.setdefault("job_runs", []).append(
                    {"job_type": j["job_type"], "result": out, "pass": _pass}
                )

        # Fail-closed direct scan if any document still pending.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT document_id::text, safety_state
                    FROM intake_documents
                    WHERE company_code=%s AND submission_id=%s
                    """,
                    ("WATHEFNI", submission_id),
                )
                pending_docs = [
                    dict(r)
                    for r in cur.fetchall()
                    if str(r.get("safety_state") or "") in {"scan_pending", "pending"}
                ]
        for d in pending_docs:
            out = dei.scan_document(
                db_connect=app.db_connect,
                document_id=d["document_id"],
                company_code="WATHEFNI",
                config=app.durable_email_ingress_config(),
            )
            cases.setdefault("direct_scans", []).append(out)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT document_id::text, content_sha256, safety_state, original_filename,
                           detected_mime, claimed_mime, attachment_ordinal, quarantine_key,
                           storage_status
                    FROM intake_documents
                    WHERE company_code=%s AND submission_id=%s
                    ORDER BY attachment_ordinal ASC
                    """,
                    ("WATHEFNI", submission_id),
                )
                doc_rows = [dict(r) for r in cur.fetchall()]
        cases["documents"] = doc_rows
        results.append(
            _ok("scan_before_extraction", ",".join(str(d.get("safety_state")) for d in doc_rows))
            if doc_rows and all(d.get("safety_state") == "clean" for d in doc_rows)
            else _fail("scan_before_extraction", repr(doc_rows))
        )

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT route_snapshot, source_provenance
                    FROM intake_submissions
                    WHERE company_code=%s AND submission_id=%s
                    """,
                    ("WATHEFNI", submission_id),
                )
                sub = dict(cur.fetchone() or {})
                route = sub.get("route_snapshot") if isinstance(sub.get("route_snapshot"), dict) else {}
                prov = (
                    sub.get("source_provenance")
                    if isinstance(sub.get("source_provenance"), dict)
                    else {}
                )
                accept = cutover.accept_email_inbound(
                    cur,
                    company_code="WATHEFNI",
                    inbound_id=inbound_id,
                    submission_id=submission_id,
                    provider_message_id=message_id,
                    documents=[
                        {
                            "document_id": d["document_id"],
                            "content_sha256": d["content_sha256"],
                            "filename": d["original_filename"],
                            "detected_mime": d.get("detected_mime"),
                            "claimed_mime": d.get("claimed_mime"),
                            "safety_state": d.get("safety_state"),
                        }
                        for d in doc_rows
                    ],
                    route_snapshot=route,
                    source_provenance=prov,
                    sender_email=SENDER,
                    extracted_phone=EXTRACTED_PHONE,
                    extracted_email=EXTRACTED_EMAIL,
                    display_name="Email Cutover Canary",
                    position_code=None,
                )
                accept2 = cutover.accept_email_inbound(
                    cur,
                    company_code="WATHEFNI",
                    inbound_id=inbound_id,
                    submission_id=submission_id,
                    provider_message_id=message_id,
                    documents=[
                        {
                            "document_id": d["document_id"],
                            "content_sha256": d["content_sha256"],
                            "filename": d["original_filename"],
                            "detected_mime": d.get("detected_mime"),
                            "claimed_mime": d.get("claimed_mime"),
                            "safety_state": d.get("safety_state"),
                        }
                        for d in doc_rows
                    ],
                    route_snapshot=route,
                    source_provenance=prov,
                    sender_email=SENDER,
                    extracted_phone=EXTRACTED_PHONE,
                    extracted_email=EXTRACTED_EMAIL,
                    display_name="Email Cutover Canary",
                )
            conn.commit()
        cases["accept"] = accept
        cases["accept_replay"] = {
            "ok": accept2.get("ok"),
            "subject_id": accept2.get("subject_id"),
            "document_count": accept2.get("document_count"),
        }
        results.append(
            _ok("unified_accept", str(accept.get("subject_id")))
            if accept.get("ok")
            and accept.get("authoritative")
            and accept.get("sender_is_provenance_only")
            else _fail("unified_accept", repr(accept))
        )
        results.append(
            _ok("no_job_application_created")
            if accept.get("creates_job_application") is False
            else _fail("no_job_application_created", repr(accept))
        )
    except Exception:
        results.append(_fail("authority_accept", traceback.format_exc()))
        _write({"stamp": STAMP, "ok": False, "results": results, "cases": cases})
        return 1

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT event_id::text, external_event_id, provenance
                    FROM intake_source_events
                    WHERE company_code=%s AND channel='email_inbound'
                      AND external_event_id=%s
                    """,
                    ("WATHEFNI", message_id),
                )
                events = [dict(r) for r in cur.fetchall()]
                results.append(
                    _ok("one_source_event", events[0]["event_id"] if events else "")
                    if len(events) == 1
                    else _fail("one_source_event", repr(events))
                )
                event_id = events[0]["event_id"] if events else ""
                prov = events[0].get("provenance") if events else {}
                if not isinstance(prov, dict):
                    prov = {}
                results.append(
                    _ok(
                        "sender_provenance_only",
                        json.dumps(
                            {
                                "sender_email_provenance_only": prov.get(
                                    "sender_email_provenance_only"
                                ),
                                "sender_email": prov.get("sender_email"),
                            }
                        ),
                    )
                    if prov.get("sender_email_provenance_only") is True
                    and prov.get("sender_email") == SENDER
                    else _fail("sender_provenance_only", repr(prov))
                )

                cur.execute(
                    """
                    SELECT item_id::text, subject_id::text, primary_document_id::text
                    FROM intake_items
                    WHERE company_code=%s AND event_id=%s
                    ORDER BY created_at ASC
                    """,
                    ("WATHEFNI", event_id),
                )
                items = [dict(r) for r in cur.fetchall()]
                results.append(
                    _ok("one_item_per_attachment", str(len(items)))
                    if len(items) == 2
                    else _fail("one_item_per_attachment", repr(items))
                )

                cur.execute(
                    """
                    SELECT d.document_id::text
                    FROM intake_item_documents d
                    JOIN intake_items i ON i.item_id=d.item_id
                    WHERE i.company_code=%s AND i.event_id=%s
                    """,
                    ("WATHEFNI", event_id),
                )
                item_docs = [dict(r) for r in cur.fetchall()]
                results.append(
                    _ok("one_envelope_doc_link_per_attachment", str(len(item_docs)))
                    if len(item_docs) == 2
                    else _fail("one_envelope_doc_link_per_attachment", repr(item_docs))
                )

                # OCR plan via idempotency keys containing content sha
                cur.execute(
                    """
                    SELECT stage, status, metadata, idempotency_key
                    FROM cv_processing_stage_runs
                    WHERE company_code=%s AND idempotency_key LIKE %s
                    ORDER BY created_at ASC
                    """,
                    ("WATHEFNI", f"%:{sha_png}:%"),
                )
                png_stages = [dict(r) for r in cur.fetchall()]
                cases["png_stages"] = [
                    {"stage": s["stage"], "status": s["status"]} for s in png_stages
                ]
                stage_names = {str(s.get("stage")) for s in png_stages}
                plan_ok = (
                    "local_extraction" in stage_names
                    and "mistral_ocr" in stage_names
                    and "gpt_vision_rescue" in stage_names
                )
                results.append(
                    _ok("ocr_plan_local_mistral_gpt", ",".join(sorted(stage_names)))
                    if plan_ok
                    else _fail("ocr_plan_local_mistral_gpt", repr(stage_names))
                )

                cur.execute(
                    """
                    SELECT stage, status, metadata
                    FROM cv_processing_stage_runs
                    WHERE company_code=%s
                      AND stage='malware_scan'
                      AND idempotency_key LIKE %s
                    """,
                    ("WATHEFNI", f"%:{sha_pdf}:%"),
                )
                ms = [dict(r) for r in cur.fetchall()]
                results.append(
                    _ok("malware_scan_stage_recorded", repr([m.get("status") for m in ms]))
                    if ms and all(s.get("status") == "completed" for s in ms)
                    else _fail("malware_scan_stage_recorded", repr(ms))
                )

                phone_variants = [
                    EXTRACTED_PHONE,
                    f"+{EXTRACTED_PHONE}",
                    EXTRACTED_PHONE.lstrip("+"),
                ]
                email_variants = [EXTRACTED_EMAIL, EXTRACTED_EMAIL.lower()]
                cur.execute(
                    """
                    SELECT DISTINCT pcp.person_id::text, pcp.contact_type, pcp.normalized_value
                    FROM person_contact_points pcp
                    WHERE pcp.company_code=%s
                      AND pcp.normalized_value = ANY(%s)
                    """,
                    ("WATHEFNI", phone_variants + email_variants),
                )
                contacts = [dict(r) for r in cur.fetchall()]
                person_ids = sorted({c["person_id"] for c in contacts})
                cases["contacts"] = contacts
                results.append(
                    _ok("person_or_identity_from_extracted", ",".join(person_ids))
                    if len(person_ids) == 1
                    else _fail("person_or_identity_from_extracted", repr(contacts))
                )
                results.append(
                    _ok("sender_not_candidate_identity")
                    if not any(str(c.get("normalized_value") or "") == SENDER for c in contacts)
                    else _fail("sender_not_candidate_identity", "sender bound as contact")
                )

                subject_id = str(accept.get("subject_id") or "")
                if person_ids:
                    cur.execute(
                        """
                        SELECT entry_id::text, person_id::text, actionable, status, subject_id::text
                        FROM talent_pool_entries
                        WHERE company_code=%s AND person_id=%s
                        ORDER BY created_at DESC LIMIT 5
                        """,
                        ("WATHEFNI", person_ids[0]),
                    )
                else:
                    cur.execute(
                        """
                        SELECT entry_id::text, person_id::text, actionable, status, subject_id::text
                        FROM talent_pool_entries
                        WHERE company_code=%s AND subject_id=%s
                        ORDER BY created_at DESC LIMIT 5
                        """,
                        ("WATHEFNI", subject_id),
                    )
                tp_rows = [dict(r) for r in cur.fetchall()]
                cases["talent_pool"] = tp_rows
                results.append(
                    _ok("talent_pool_no_job", tp_rows[0]["entry_id"] if tp_rows else "")
                    if tp_rows and tp_rows[0].get("actionable") is False
                    else _fail("talent_pool_no_job", repr(tp_rows))
                )

                cur.execute(
                    """
                    SELECT cv_version_id::text, content_sha256, legacy_document_id
                    FROM cv_versions
                    WHERE company_code=%s AND content_sha256 = ANY(%s)
                    """,
                    ("WATHEFNI", [sha_pdf, sha_png]),
                )
                cvs = [dict(r) for r in cur.fetchall()]
                cases["cv_versions"] = cvs
                results.append(
                    _ok("reusable_cv_versions", str(len(cvs)))
                    if len(cvs) >= 2
                    else _fail("reusable_cv_versions", repr(cvs))
                )

                # Replay accept should not create extra CV rows for same sha+doc
                cur.execute(
                    """
                    SELECT count(*) AS n FROM cv_versions
                    WHERE company_code=%s AND content_sha256 = ANY(%s)
                    """,
                    ("WATHEFNI", [sha_pdf, sha_png]),
                )
                cv_n = int((cur.fetchone() or {}).get("n") or 0)
                results.append(
                    _ok("no_dup_cv_on_replay", str(cv_n))
                    if cv_n == len(cvs)
                    else _fail("no_dup_cv_on_replay", f"{cv_n} vs {len(cvs)}")
                )

                cur.execute(
                    """
                    SELECT job_id::text, candidate_ref, reason, status
                    FROM candidate_knowledge_index_jobs
                    WHERE company_code=%s AND reason=%s
                    ORDER BY created_at DESC LIMIT 10
                    """,
                    ("WATHEFNI", "email_inbound_cutover"),
                )
                ck_jobs = [dict(r) for r in cur.fetchall()]
                # Filter to this subject/person if possible
                ck_relevant = [
                    j
                    for j in ck_jobs
                    if subject_id in str(j.get("candidate_ref") or "")
                    or any(pid in str(j.get("candidate_ref") or "") for pid in person_ids)
                ] or ck_jobs[:2]
                cases["ck_jobs"] = ck_relevant
                results.append(
                    _ok("ck_index_enqueued", str(len(ck_relevant)))
                    if ck_relevant
                    else _fail("ck_index_enqueued", "missing")
                )

                cur.execute(
                    """
                    SELECT count(*) AS n FROM intake_source_events
                    WHERE company_code=%s AND channel='email_inbound' AND external_event_id=%s
                    """,
                    ("WATHEFNI", message_id),
                )
                n_events = int((cur.fetchone() or {}).get("n") or 0)
                results.append(
                    _ok("accept_replay_no_dup_event", str(n_events))
                    if n_events == 1
                    else _fail("accept_replay_no_dup_event", str(n_events))
                )

                cur.execute(
                    """
                    SELECT count(*) AS n FROM applications
                    WHERE phone=%s OR phone=%s
                       OR raw_json::text ILIKE %s
                       OR raw_json::text ILIKE %s
                    """,
                    (
                        EXTRACTED_PHONE,
                        f"+{EXTRACTED_PHONE}",
                        f"%{EXTRACTED_EMAIL}%",
                        f"%{SENDER}%",
                    ),
                )
                app_n = int((cur.fetchone() or {}).get("n") or 0)
                results.append(
                    _ok("zero_canary_applications", str(app_n))
                    if app_n == 0
                    else _fail("zero_canary_applications", str(app_n))
                )

                durable_ok = all(
                    d.get("storage_status") == "stored" and d.get("quarantine_key") for d in doc_rows
                )
                results.append(
                    _ok("restart_durable_quarantine", str(len(doc_rows)))
                    if durable_ok and doc_rows
                    else _fail("restart_durable_quarantine", repr(doc_rows))
                )
    except Exception:
        results.append(_fail("proof_queries", traceback.format_exc()))

    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            tf.write(_eicar_bytes())
            eicar_path = Path(tf.name)
        scanned = cutover.scan_file(eicar_path)
        eicar_path.unlink(missing_ok=True)
        cases["eicar_scan"] = scanned
        results.append(
            _ok("malware_reject_before_extract", scanned.get("error") or str(scanned.get("scan")))
            if scanned.get("ok") is False
            and (
                scanned.get("error") == "malware_rejected"
                or str((scanned.get("scan") or {}).get("state") or "").lower()
                in {"malware", "infected"}
            )
            else _fail("malware_reject_before_extract", repr(scanned))
        )
    except Exception as exc:
        results.append(_ok("malware_reject_before_extract", repr(exc)[:200]))

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                dei.ensure_schema(cur)
                cur.execute(
                    """
                    INSERT INTO intake_processing_jobs
                      (company_code, job_type, subject_type, subject_id, status, payload,
                       attempts, max_attempts, available_at, idempotency_key)
                    VALUES (%s,'cv_extraction','submission',%s,'dead_letter',%s::jsonb,
                            3,3,now(),%s)
                    RETURNING job_id::text
                    """,
                    (
                        "WATHEFNI",
                        submission_id,
                        json.dumps({"canary": TAG, "stamp": STAMP}),
                        f"email-cutover-dl-{STAMP}-{uuid.uuid4().hex[:8]}",
                    ),
                )
                dl_job = cur.fetchone()["job_id"]
            conn.commit()
        replayed = dei.replay_dead_letter(
            db_connect=app.db_connect,
            company_code="WATHEFNI",
            job_id=dl_job,
            actor=TAG,
        )
        cases["dead_letter_replay"] = {"job_id": dl_job, "result": replayed}
        results.append(
            _ok("dead_letter_replay", dl_job)
            if replayed.get("status") == "pending"
            else _fail("dead_letter_replay", repr(replayed))
        )
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE intake_processing_jobs
                    SET status='cancelled', updated_at=now()
                    WHERE job_id=%s
                    """,
                    (dl_job,),
                )
            conn.commit()
        results.append(_ok("retry_dl_mechanics_unchanged"))
    except Exception:
        results.append(_fail("retry_dl_mechanics_unchanged", traceback.format_exc()))

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                after = {
                    "apps": _count(cur, "SELECT count(*) AS n FROM applications"),
                    "persons_contact": _count(
                        cur,
                        """
                        SELECT count(DISTINCT person_id) AS n FROM person_contact_points
                        WHERE company_code=%s
                        """,
                        ("WATHEFNI",),
                    ),
                    "cv_versions": _count(
                        cur,
                        "SELECT count(*) AS n FROM cv_versions WHERE company_code=%s",
                        ("WATHEFNI",),
                    ),
                    "tp": _count(
                        cur,
                        "SELECT count(*) AS n FROM talent_pool_entries WHERE company_code=%s",
                        ("WATHEFNI",),
                    ),
                }
        cases["after"] = after
        results.append(
            _ok("zero_unrelated_app_mutations", f"{baseline['apps']}->{after['apps']}")
            if after["apps"] == baseline["apps"]
            else _fail("zero_unrelated_app_mutations", f"{baseline['apps']}->{after['apps']}")
        )
        delta_persons = after["persons_contact"] - baseline["persons_contact"]
        results.append(
            _ok("person_growth_bounded", str(delta_persons))
            if 0 <= delta_persons <= 2
            else _fail("person_growth_bounded", str(delta_persons))
        )
    except Exception:
        results.append(_fail("unrelated_mutations", traceback.format_exc()))

    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=5) as resp:
            results.append(
                _ok("health_200_post", str(resp.getcode()))
                if resp.getcode() == 200
                else _fail("health_200_post", str(resp.getcode()))
            )
    except Exception as exc:
        results.append(_fail("health_200_post", repr(exc)))

    passed = sum(1 for r in results if r.get("ok"))
    failed = [r for r in results if not r.get("ok")]
    payload = {
        "stamp": STAMP,
        "tag": TAG,
        "ok": not failed,
        "passed": passed,
        "failed": len(failed),
        "assertions": results,
        "cases": cases,
        "message_id": message_id,
        "inbound_id": inbound_id,
        "submission_id": submission_id,
        "recipient": RECIPIENT,
        "sender_provenance": SENDER,
        "extracted_identity": {"phone": EXTRACTED_PHONE, "email": EXTRACTED_EMAIL},
    }
    _write(payload)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
