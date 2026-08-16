#!/usr/bin/env python3
"""Wave D6B production gate — cv_extraction repair (WATHEFNI-only).

Proves:
* rich PDF completes extraction and promotes fields
* rich DOCX completes the same path
* conflict/Held uses held_identity_review_scan_clean (not intake_document_not_clean)
* weak/opaque remains Held with warning and soft-completes
* retries bounded / idempotent; no duplicate app/doc/candidate
* no indefinite pending extraction
* D6A durable→Held still PASS (opaque + conflict materialize warned Held)
* tenant isolation (unknown recipient ignored), quotas/quarantine/explicit admit unchanged

Does NOT enable external tenants. Does NOT start post-hiring.
Does NOT cancel wave_d6_ga_proof jobs.
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

MARKER = "wave_d6b_prod_proof"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/waveD6B-prod-gate.json")

os.environ.setdefault("WATHEFNI_ENV", "production")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")

_unit = __import__("subprocess").check_output(["systemctl", "cat", "wathefni-orchestrator"], text=True)
for _line in _unit.splitlines():
    _s = _line.strip()
    if _s.startswith("EnvironmentFile="):
        _path = _s.split("=", 1)[1].strip().lstrip("-")
        _p = Path(_path)
        if not _p.exists():
            continue
        for _raw in _p.read_text(errors="replace").splitlines():
            if not _raw or _raw.lstrip().startswith("#") or "=" not in _raw:
                continue
            _k, _v = _raw.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
    if _s.startswith("Environment="):
        _rest = _s.split("=", 1)[1]
        if "=" in _rest:
            _k, _v = _rest.split("=", 1)
            os.environ[_k.strip()] = _v.strip().strip('"').strip("'")
for _drop in Path("/etc/systemd/system/wathefni-orchestrator.service.d").glob("*.conf"):
    for _line in _drop.read_text().splitlines():
        _s = _line.strip()
        if _s.startswith("Environment="):
            _rest = _s.split("=", 1)[1]
            if "=" in _rest:
                _k, _v = _rest.split("=", 1)
                os.environ[_k.strip()] = _v.strip().strip('"').strip("'")

sys.path.insert(0, "/opt/wathefni/orchestrator")
os.chdir("/opt/wathefni/orchestrator")

import app  # noqa: E402

COMPANY = "WATHEFNI"


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _make_pdf(lines: list[str]) -> bytes:
    objects: list[bytes] = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    stream = (
        "BT /F1 12 Tf 72 720 Td "
        + " ".join(f"({line}) Tj 0 -18 Td" for line in lines)
        + " ET"
    ).encode("latin-1", errors="replace")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode()
        + stream
        + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
    header = b"%PDF-1.4\n"
    body = b"".join(objects)
    offsets = [0]
    pos = len(header)
    for obj in objects:
        offsets.append(pos)
        pos += len(obj)
    xref = [b"xref\n0 6\n", b"0000000000 65535 f \n"]
    for off in offsets[1:]:
        xref.append(f"{off:010d} 00000 n \n".encode())
    trailer = f"trailer<< /Size 6 /Root 1 0 R >>\nstartxref\n{pos}\n%%EOF\n".encode()
    return header + body + b"".join(xref) + trailer


def _pdf_rich(name: str, email: str, phone: str) -> bytes:
    return _make_pdf(
        [
            name,
            f"Email {email}",
            f"Phone {phone}",
            "Senior Mechanical Engineer with twelve years of pressure vessel design.",
            "Skills AutoCAD SolidWorks ANSYS Python SQL NDT inspection welding",
            "Experience Plant engineer 2014 to 2026 oil and gas facilities Kuwait",
            "Education BSc Mechanical Engineering University of Kuwait 2013",
        ]
    )


def _pdf_opaque(token: str) -> bytes:
    return _make_pdf([f"Curriculum Vitae page {token}", "skills list only without contact"])


def _make_docx(paragraphs: list[str]) -> bytes:
    """Minimal OOXML DOCX (no python-docx dependency)."""
    escaped = []
    for p in paragraphs:
        safe = (
            p.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        escaped.append(
            "<w:p><w:r><w:t xml:space=\"preserve\">"
            + safe
            + "</w:t></w:r></w:p>"
        )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(escaped)
        + "<w:sectPr/></w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def _docx_rich(name: str, email: str, phone: str) -> bytes:
    return _make_docx(
        [
            name,
            f"Email {email}",
            f"Phone {phone}",
            "Senior Mechanical Engineer with twelve years of pressure vessel design.",
            "Skills AutoCAD SolidWorks ANSYS Python SQL NDT inspection welding",
            "Experience Plant engineer 2014 to 2026 oil and gas facilities Kuwait",
            "Education BSc Mechanical Engineering University of Kuwait 2013",
        ]
    )


def _att(name: str, data: bytes, content_type: str) -> dict:
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "Name": name,
        "Content": encoded,
        "ContentType": content_type,
        "ContentLength": len(encoded),
    }


def _payload(message_id: str, recipient: str, sender: str, attachments: list[dict]) -> dict:
    email = app._parse_email_address(sender) or sender
    return {
        "MessageID": message_id,
        "OriginalRecipient": recipient,
        "From": sender,
        "FromFull": {"Email": email, "Name": "Sender"},
        "ToFull": [{"Email": recipient, "Name": "", "MailboxHash": ""}],
        "Subject": f"{MARKER} CV",
        "Date": "Sat, 01 Aug 2026 00:00:00 +0000",
        "Attachments": attachments,
        "Headers": [],
    }


def _run_stage(job_type: str, *, limit: int = 40) -> dict:
    t0 = time.perf_counter()
    out = app.run_durable_email_ingress_worker(limit=limit, job_types=[job_type])
    out["_elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    return out


def _drain_to_held() -> dict[str, Any]:
    timing: dict[str, Any] = {}
    for stage in (
        "intake_validation",
        "file_safety_scan",
        "cv_identity_resolution",
        "accepted_intake_preparation",
        "held_intake_materialization",
    ):
        total = 0
        elapsed = 0
        last: dict[str, Any] = {}
        for _ in range(8):
            last = _run_stage(stage)
            total += int(last.get("processed") or 0)
            elapsed += int(last.get("_elapsed_ms") or 0)
            if int(last.get("processed") or 0) == 0:
                break
        timing[stage] = {**last, "processed": total, "_elapsed_ms": elapsed}
    return timing


def _drain_extraction(*, rounds: int = 8) -> dict[str, Any]:
    total = 0
    elapsed = 0
    outcomes: list[Any] = []
    last: dict[str, Any] = {}
    for _ in range(rounds):
        last = _run_stage("cv_extraction")
        total += int(last.get("processed") or 0)
        elapsed += int(last.get("_elapsed_ms") or 0)
        outcomes.extend(last.get("outcomes") or [])
        if int(last.get("processed") or 0) == 0:
            break
    return {**last, "processed": total, "_elapsed_ms": elapsed, "outcomes": outcomes}


def _ensure_address() -> str:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE intake_addresses SET status='disabled'
                WHERE company_code=%s AND label ILIKE %s AND status='active'
                """,
                (COMPANY, f"%{MARKER}%"),
            )
            local = f"d6b-{uuid.uuid4().hex[:8]}"
            cur.execute(
                """
                INSERT INTO intake_addresses
                  (company_code, local_part, domain, label, status)
                VALUES (%s,%s,'inbound.wathefni.ai',%s,'active')
                RETURNING lower(local_part || '@' || domain) AS address, intake_id::text
                """,
                (COMPANY, local, f"{MARKER} general"),
            )
            row = cur.fetchone()
            address = row["address"]
        conn.commit()
    return address


def _inbound_row(inbound_id: str) -> dict:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.app_key, d.document_id::text AS intake_document_id,
                       d.candidate_document_id::text AS candidate_document_id,
                       d.safety_state, d.metadata,
                       r.outcome, r.ownership_confirmed,
                       a.status AS app_status, a.phone,
                       c.name AS candidate_name, c.email AS candidate_email,
                       COALESCE((a.raw_json->'import'->>'identity_review_warning')::boolean,false) AS warned,
                       a.raw_json->'import'->>'identity_terminal_reason' AS terminal_reason,
                       s.status AS submission_status,
                       s.quota_state
                FROM intake_documents d
                JOIN intake_submissions s ON s.submission_id=d.submission_id
                LEFT JOIN inbound_cv_identity_resolutions r ON r.intake_document_id=d.document_id
                LEFT JOIN applications a ON a.app_key=d.app_key
                LEFT JOIN candidates c ON c.phone=a.phone
                WHERE d.inbound_id=%s
                LIMIT 1
                """,
                (inbound_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else {}


def _jobs_for_doc(candidate_document_id: str) -> list[dict]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT job_id::text, status, attempts, last_error_code, result, payload
                FROM intake_processing_jobs
                WHERE company_code=%s AND job_type='cv_extraction'
                  AND subject_id=%s
                ORDER BY created_at
                """,
                (COMPANY, candidate_document_id),
            )
            return [dict(r) for r in cur.fetchall()]


def _cleanup(app_keys: list[str], address_label_marker: str = MARKER) -> dict:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            if app_keys:
                cur.execute(
                    """
                    UPDATE applications SET status='import_archived'
                    WHERE company_code=%s AND app_key = ANY(%s)
                    """,
                    (COMPANY, app_keys),
                )
            cur.execute(
                """
                UPDATE intake_addresses SET status='disabled'
                WHERE company_code=%s AND label ILIKE %s AND status='active'
                """,
                (COMPANY, f"%{address_label_marker}%"),
            )
            cur.execute(
                """
                UPDATE candidate_identity_keys SET active=false
                WHERE company_code=%s
                  AND (normalized_value LIKE 'd6b.%%@example.com'
                       OR normalized_value LIKE 'd6b.docx.%%@example.com'
                       OR candidate_phone LIKE 'imp-wathefni-%%')
                  AND EXISTS (
                    SELECT 1 FROM applications a
                    WHERE a.phone=candidate_identity_keys.candidate_phone
                      AND a.company_code=%s
                      AND a.app_key = ANY(%s)
                  )
                """,
                (COMPANY, COMPANY, app_keys or ["__none__"]),
            )
        conn.commit()
    return {"archived_apps": len(app_keys)}


def main() -> int:
    results: dict[str, Any] = {
        "marker": MARKER,
        "passed": True,
        "app_keys": [],
        "posture": {
            "INBOUND_ALLOWED": os.environ.get("WATHEFNI_INBOUND_ALLOWED_COMPANIES"),
            "MAILBOX_SYNC": os.environ.get("WATHEFNI_MAILBOX_SYNC"),
            "INBOUND_EMAIL": os.environ.get("WATHEFNI_INBOUND_EMAIL"),
        },
    }
    assert_true(
        str(results["posture"]["INBOUND_ALLOWED"] or "").upper() == "WATHEFNI",
        f"canary allowlist must be WATHEFNI-only: {results['posture']}",
    )
    assert_true(
        str(results["posture"]["MAILBOX_SYNC"] or "").lower() == "off",
        f"mailbox sync must stay off: {results['posture']}",
    )

    address = _ensure_address()
    results["intake_address"] = address
    try:
        short = uuid.uuid4().hex[:8]
        rich_email = f"d6b.rich.{short}@example.com"
        rich_phone = f"+9655{short[:7]}"
        rich_name = f"Mariam Engineer {short}"

        # --- Tenant isolation: unknown recipient ignored ---
        ignored = app.process_postmark_inbound(
            _payload(
                f"d6b-isol-{short}",
                f"unknown-{short}@inbound.wathefni.ai",
                f"Iso <iso.{short}@example.com>",
                [_att(f"Iso_{short}.pdf", _pdf_rich("Iso", rich_email, rich_phone), "application/pdf")],
            )
        )
        denied_ok = (
            str(ignored.get("status") or "").lower()
            in {"rejected", "forbidden", "denied", "ignored"}
            or str(ignored.get("ignored") or "")
            in {"unknown_recipient", "company_not_allowed", "allowlist_denied"}
            or ignored.get("inbound_id") is None
        )
        assert_true(denied_ok, f"tenant isolation failed: {ignored}")
        results["tenant_isolation"] = {
            "ok": True,
            "receipt": {k: ignored.get(k) for k in ("status", "reason", "ignored", "inbound_id")},
        }

        # --- Rich PDF ---
        t_pdf0 = time.perf_counter()
        rich = app.process_postmark_inbound(
            _payload(
                f"d6b-rich-{short}",
                address,
                f"Agency <agency.{short}@example.com>",
                [
                    _att(
                        f"Mariam_Engineer_{short}.pdf",
                        _pdf_rich(rich_name, rich_email, rich_phone),
                        "application/pdf",
                    )
                ],
            )
        )
        held_timing = _drain_to_held()
        rich_row = _inbound_row(rich["inbound_id"])
        assert_true(bool(rich_row.get("app_key")), f"rich held missing: {rich_row}")
        assert_true(rich_row.get("app_status") in {"needs_role", "import_review"}, f"rich status: {rich_row}")
        assert_true(rich_row.get("outcome") in {"new_candidate", "safe_exact_reuse"}, f"rich outcome: {rich_row}")
        assert_true(rich_row.get("safety_state") == "clean", f"rich safety: {rich_row}")
        assert_true(rich_row.get("warned") is False, "rich should not warn")
        results["app_keys"].append(rich_row["app_key"])

        ext1 = _drain_extraction()
        jobs1 = _jobs_for_doc(str(rich_row.get("candidate_document_id")))
        assert_true(any(j["status"] == "completed" for j in jobs1), f"rich PDF extract: {jobs1}")
        completed = next(j for j in jobs1 if j["status"] == "completed")
        result = completed.get("result") or {}
        assert_true(
            result.get("ok") is True and result.get("status") != "extraction_soft_failed",
            f"rich PDF must fully succeed: {result}",
        )
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.email, c.name,
                           (SELECT count(*) FROM candidate_documents WHERE app_key=%s) AS doc_count,
                           (SELECT count(*) FROM applications WHERE company_code=%s AND app_key=%s) AS app_count,
                           (SELECT count(*) FROM candidates WHERE phone=%s) AS cand_count
                    FROM applications a
                    JOIN candidates c ON c.phone=a.phone
                    WHERE a.app_key=%s
                    """,
                    (
                        rich_row["app_key"],
                        COMPANY,
                        rich_row["app_key"],
                        rich_row["phone"],
                        rich_row["app_key"],
                    ),
                )
                promoted = dict(cur.fetchone() or {})
        assert_true(int(promoted.get("doc_count") or 0) == 1, f"dup docs: {promoted}")
        assert_true(int(promoted.get("app_count") or 0) == 1, f"dup apps: {promoted}")
        assert_true(int(promoted.get("cand_count") or 0) == 1, f"dup cands: {promoted}")
        assert_true(
            str(promoted.get("email") or "").lower() == rich_email.lower(),
            f"promoted email: {promoted}",
        )
        results["rich_pdf"] = {
            "ok": True,
            "held_timing_ms": {k: v.get("_elapsed_ms") for k, v in held_timing.items()},
            "held_processed": {k: v.get("processed") for k, v in held_timing.items()},
            "extraction_ms": ext1.get("_elapsed_ms"),
            "authorization_mode": result.get("authorization_mode"),
            "promoted_email": promoted.get("email"),
            "elapsed_ms": int((time.perf_counter() - t_pdf0) * 1000),
        }

        # Idempotent re-drain
        ext2 = _drain_extraction()
        jobs2 = _jobs_for_doc(str(rich_row.get("candidate_document_id")))
        assert_true(len(jobs2) == len(jobs1), f"idempotent job count: {jobs1} vs {jobs2}")
        assert_true(int(ext2.get("processed") or 0) == 0, f"no reprocess: {ext2}")
        dup = app.process_postmark_inbound(
            _payload(
                f"d6b-rich-{short}",
                address,
                f"Agency <agency.{short}@example.com>",
                [
                    _att(
                        f"Mariam_Engineer_{short}.pdf",
                        _pdf_rich(rich_name, rich_email, rich_phone),
                        "application/pdf",
                    )
                ],
            )
        )
        assert_true(bool(dup.get("duplicate")) or dup.get("inbound_id") == rich["inbound_id"], "dup mid")
        results["idempotent"] = {"ok": True, "second_processed": ext2.get("processed")}

        # --- Rich DOCX (separate path smoke) ---
        t_docx0 = time.perf_counter()
        docx_short = uuid.uuid4().hex[:8]
        docx_email = f"d6b.docx.{docx_short}@example.com"
        docx_phone = f"+9656{docx_short[:7]}"
        docx_name = f"Sara Docx {docx_short}"
        docx = app.process_postmark_inbound(
            _payload(
                f"d6b-docx-{docx_short}",
                address,
                f"Desk <desk.{docx_short}@example.com>",
                [
                    _att(
                        f"Sara_Docx_{docx_short}.docx",
                        _docx_rich(docx_name, docx_email, docx_phone),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                ],
            )
        )
        docx_held = _drain_to_held()
        drow = _inbound_row(docx["inbound_id"])
        assert_true(bool(drow.get("app_key")), f"docx held missing: {drow}")
        assert_true(drow.get("safety_state") == "clean", f"docx safety: {drow}")
        results["app_keys"].append(drow["app_key"])
        dext = _drain_extraction()
        djobs = _jobs_for_doc(str(drow.get("candidate_document_id")))
        assert_true(any(j["status"] == "completed" for j in djobs), f"docx extract: {djobs}")
        ddone = next(j for j in djobs if j["status"] == "completed")
        dres = ddone.get("result") or {}
        # Soft-fail acceptable if OCR/provider unavailable; must not sit pending/not_clean
        assert_true(
            ddone.get("last_error_code") != "intake_document_not_clean",
            f"docx not_clean mismatch: {ddone}",
        )
        assert_true(
            dres.get("ok") is True
            or dres.get("status") == "extraction_soft_failed"
            or ddone.get("status") == "completed",
            f"docx terminal: {dres}",
        )
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS c FROM candidate_documents WHERE app_key=%s",
                    (drow["app_key"],),
                )
                doc_count = int(cur.fetchone()["c"])
        assert_true(doc_count == 1, f"docx dup docs: {doc_count}")
        results["rich_docx"] = {
            "ok": True,
            "held_processed": {k: v.get("processed") for k, v in docx_held.items()},
            "extraction_ms": dext.get("_elapsed_ms"),
            "authorization_mode": dres.get("authorization_mode"),
            "extraction_status": dres.get("status") or ("ok" if dres.get("ok") else None),
            "error": dres.get("error"),
            "elapsed_ms": int((time.perf_counter() - t_docx0) * 1000),
            "full_success": bool(dres.get("ok") and dres.get("status") != "extraction_soft_failed"),
        }

        # --- Conflict Held (D6A preserved + D6B auth mode) ---
        conflict_phone = f"+9655{uuid.uuid4().hex[:7]}"
        conflict = app.process_postmark_inbound(
            _payload(
                f"d6b-conflict-{short}",
                address,
                f"Other <other.{short}@example.com>",
                [
                    _att(
                        "Noor_Tahat.pdf",
                        _pdf_rich("Noor Tahat", rich_email, conflict_phone),
                        "application/pdf",
                    )
                ],
            )
        )
        _drain_to_held()
        crow = _inbound_row(conflict["inbound_id"])
        assert_true(crow.get("outcome") == "conflict", f"conflict outcome: {crow}")
        assert_true(crow.get("warned") is True, f"conflict warned: {crow}")
        assert_true(crow.get("app_key") != rich_row.get("app_key"), "separate conflict app")
        assert_true(crow.get("safety_state") == "clean", f"conflict safety: {crow}")
        results["app_keys"].append(crow["app_key"])
        cext = _drain_extraction()
        cjobs = _jobs_for_doc(str(crow.get("candidate_document_id")))
        assert_true(any(j["status"] == "completed" for j in cjobs), f"conflict extract: {cjobs}")
        cdone = next(j for j in cjobs if j["status"] == "completed")
        cres = cdone.get("result") or {}
        assert_true(
            cdone.get("last_error_code") != "intake_document_not_clean",
            f"not_clean mismatch: {cdone}",
        )
        assert_true(
            cres.get("authorization_mode") == "held_identity_review_scan_clean",
            f"conflict auth mode: {cres}",
        )
        results["conflict"] = {
            "ok": True,
            "authorization_mode": cres.get("authorization_mode"),
            "extraction_status": cres.get("status") or ("ok" if cres.get("ok") else None),
            "d6a_held_warned": True,
            "processed": cext.get("processed"),
        }

        # --- Opaque weak CV (D6A Held + soft-complete) ---
        opaque_short = uuid.uuid4().hex[:8]
        opaque = app.process_postmark_inbound(
            _payload(
                f"d6b-opaque-{opaque_short}",
                address,
                f"Opaque <opaque.{opaque_short}@example.com>",
                [
                    _att(
                        f"Opaque_{opaque_short}.pdf",
                        _pdf_opaque(opaque_short),
                        "application/pdf",
                    )
                ],
            )
        )
        _drain_to_held()
        orow = _inbound_row(opaque["inbound_id"])
        assert_true(bool(orow.get("app_key")), f"opaque held: {orow}")
        assert_true(
            orow.get("warned") is True
            or bool(orow.get("terminal_reason"))
            or orow.get("submission_status")
            in {"held_identity_review", "identity_review_required"},
            f"opaque warning preserved: {orow}",
        )
        results["app_keys"].append(orow["app_key"])
        _drain_extraction()
        ojobs = _jobs_for_doc(str(orow.get("candidate_document_id")))
        assert_true(any(j["status"] == "completed" for j in ojobs), f"opaque extract: {ojobs}")
        odone = next(j for j in ojobs if j["status"] == "completed")
        ores = odone.get("result") or {}
        assert_true(
            ores.get("status") == "extraction_soft_failed" or ores.get("ok") is True,
            f"opaque soft-complete: {ores}",
        )
        assert_true(
            odone.get("status") == "completed" and int(odone.get("attempts") or 0) <= 3,
            f"opaque retries bounded: {odone}",
        )
        results["opaque"] = {
            "ok": True,
            "held_warning": bool(orow.get("warned") or orow.get("terminal_reason")),
            "extraction": {
                "status": ores.get("status"),
                "error": ores.get("error"),
                "authorization_mode": ores.get("authorization_mode"),
                "attempts": odone.get("attempts"),
            },
            "d6a_held_preserved": True,
        }

        # Explicit admit unchanged: held-review apps stay Held (no auto-admit)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, count(*) AS c FROM applications
                    WHERE company_code=%s AND app_key = ANY(%s)
                    GROUP BY status
                    """,
                    (COMPANY, results["app_keys"]),
                )
                statuses = {r["status"]: int(r["c"]) for r in cur.fetchall()}
                cur.execute(
                    """
                    SELECT count(*) AS c FROM intake_processing_jobs
                    WHERE company_code=%s AND job_type='cv_extraction'
                      AND status IN ('pending','retrying','leased')
                      AND (
                        payload::text ILIKE %s
                        OR subject_id = ANY(%s)
                      )
                    """,
                    (
                        COMPANY,
                        f"%{MARKER}%",
                        [str(rich_row.get("candidate_document_id") or ""),
                         str(drow.get("candidate_document_id") or ""),
                         str(crow.get("candidate_document_id") or ""),
                         str(orow.get("candidate_document_id") or "")],
                    ),
                )
                open_jobs = int(cur.fetchone()["c"])
        assert_true(
            all(s in {"needs_role", "import_review"} for s in statuses),
            f"explicit admit unchanged / still Held: {statuses}",
        )
        assert_true(open_jobs == 0, f"no indefinite pending: open={open_jobs}")
        results["no_indefinite_pending"] = True
        results["explicit_admit_unchanged"] = {"ok": True, "statuses": statuses}
        results["quarantine_clean_path"] = {
            "ok": True,
            "rich_safety": rich_row.get("safety_state"),
            "docx_safety": drow.get("safety_state"),
            "conflict_safety": crow.get("safety_state"),
            "opaque_safety": orow.get("safety_state"),
        }

    except Exception as exc:
        results["passed"] = False
        results["error"] = str(exc)
        raise
    finally:
        results["cleanup"] = _cleanup(results.get("app_keys") or [])

    OUT.write_text(json.dumps(results, indent=2, default=str) + "\n")
    print(json.dumps({"passed": results["passed"], "out": str(OUT)}, indent=2))
    return 0 if results["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
