#!/usr/bin/env python3
"""Wave D6B — local cv_extraction promotion + not_clean gate repair.

Proves:
* rich PDF completes cv_extraction and promotes fields into Held app/candidate
* weak/opaque CV still Held with warning; extraction soft-completes (no infinite retry)
* conflict Held path is scan-clean authorized (not mislabeled intake_document_not_clean)
* Message-ID / extraction job idempotent; no duplicate apps/docs
* D6A weak-CV Held behavior preserved

No external tenants. No post-hiring.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_QUARANTINE = Path(tempfile.mkdtemp(prefix="wathefni-d6b-"))
_WORKSPACE = Path(tempfile.mkdtemp(prefix="wathefni-d6b-ws-"))
database_url = str(os.environ.get("WATHEFNI_TEST_DATABASE_URL") or "").strip()
if not database_url:
    env_path = Path("/tmp/waveC-local-env/postgres.test.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("WATHEFNI_DATABASE_URL="):
                database_url = line.split("=", 1)[1].strip()
                break
if not database_url:
    raise RuntimeError("Set WATHEFNI_TEST_DATABASE_URL")

parsed = urlparse(database_url)
env_file = _QUARANTINE / "postgres.test.env"
env_file.write_text(f"WATHEFNI_DATABASE_URL={database_url}\n")
os.environ["WATHEFNI_POSTGRES_ENV"] = str(env_file)
os.environ["WATHEFNI_ENV"] = "test"
os.environ["WATHEFNI_EXPECTED_DATABASE_HOST"] = parsed.hostname or "127.0.0.1"
os.environ["WATHEFNI_EXPECTED_DATABASE_PORT"] = str(parsed.port or 5432)
os.environ["WATHEFNI_EXPECTED_DATABASE_NAME"] = parsed.path.lstrip("/")
os.environ.setdefault(
    "WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-local-boundary-remediation-v1"
)
os.environ["WATHEFNI_WORKSPACE"] = str(_WORKSPACE)
os.environ["WATHEFNI_INBOUND_EMAIL"] = "on"
os.environ["WATHEFNI_INBOUND_ALLOWED_COMPANIES"] = "D6BBRAVO"
os.environ.setdefault("WATHEFNI_POSTMARK_INBOUND_SECRET", "smoke-secret-token")
os.environ["WATHEFNI_INTAKE_QUARANTINE_DIR"] = str(_QUARANTINE)
os.environ["WATHEFNI_INTAKE_MALWARE_SCANNER"] = "test_clean"
os.environ["WATHEFNI_INTAKE_ALLOW_TEST_SCANNER"] = "1"
os.environ["WATHEFNI_MAILBOX_SYNC"] = "off"

import app  # noqa: E402

COMPANY = "D6BBRAVO"
MARKER = "wave_d6b_cv_extraction"


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
    summary = (
        "Senior Mechanical Engineer with twelve years of pressure vessel design, "
        "ASME code compliance, finite element analysis, project leadership, "
        "bilingual client coordination, commissioning, and safety management systems."
    )
    skills = (
        "Skills AutoCAD SolidWorks ANSYS Python SQL NDT inspection welding procedures "
        "root cause analysis team mentoring stakeholder reporting quality assurance"
    )
    return _make_pdf(
        [
            name,
            f"Email {email}",
            f"Phone {phone}",
            summary,
            skills,
            "Experience Plant engineer 2014 to 2026 oil and gas facilities Kuwait and UAE",
            "Education BSc Mechanical Engineering University of Kuwait 2013",
        ]
    )


def _pdf_opaque(token: str) -> bytes:
    return _make_pdf([f"Curriculum Vitae page {token}", "skills list only without contact"])


def _att(name: str, data: bytes) -> dict:
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "Name": name,
        "Content": encoded,
        "ContentType": "application/pdf",
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
    timing = {}
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
        for _ in range(6):
            last = _run_stage(stage)
            total += int(last.get("processed") or 0)
            elapsed += int(last.get("_elapsed_ms") or 0)
            if int(last.get("processed") or 0) == 0:
                break
        timing[stage] = {**last, "processed": total, "_elapsed_ms": elapsed}
    return timing


def _drain_extraction(*, rounds: int = 6) -> dict[str, Any]:
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
                INSERT INTO companies (company_code, name, status)
                VALUES (%s,%s,'active')
                ON CONFLICT (company_code) DO UPDATE SET status='active'
                """,
                (COMPANY, "D6B Bravo"),
            )
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
                RETURNING lower(local_part || '@' || domain) AS address
                """,
                (COMPANY, local, f"{MARKER} general"),
            )
            address = cur.fetchone()["address"]
        conn.commit()
    return address


def _cleanup(app_keys: list[str]) -> dict:
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
                (COMPANY, f"%{MARKER}%"),
            )
            cur.execute(
                """
                UPDATE candidates SET name=NULL, email=NULL, current_status='import_archived'
                WHERE active_company_code=%s AND phone LIKE 'imp-d6bbravo-%%'
                """,
                (COMPANY,),
            )
            # Deactivate synthetic identity keys so later runs cannot
            # safe_exact_reuse stale phone/email bindings.
            cur.execute(
                """
                UPDATE candidate_identity_keys
                SET active=false
                WHERE company_code=%s
                  AND (candidate_phone LIKE 'imp-d6bbravo-%%'
                       OR normalized_value LIKE 'd6b.%%@example.com'
                       OR normalized_value LIKE '9655%%')
                """,
                (COMPANY,),
            )
            cur.execute(
                """
                UPDATE intake_processing_jobs
                SET status='cancelled', updated_at=now(),
                    last_error_code=COALESCE(last_error_code,'d6b_smoke_cleanup')
                WHERE company_code=%s AND job_type='cv_extraction'
                  AND status IN ('pending','retrying','leased')
                """,
                (COMPANY,),
            )
        conn.commit()
    return {"archived": len(app_keys)}


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
                       s.status AS submission_status
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


def main() -> int:
    results: dict[str, Any] = {"marker": MARKER, "passed": True, "app_keys": []}
    # Clear prior synthetic residue (apps, keys, open extraction jobs).
    _cleanup([])
    address = _ensure_address()
    try:
        short = uuid.uuid4().hex[:8]
        rich_email = f"d6b.rich.{short}@example.com"
        rich_phone = f"+9655{short[:7]}"
        rich_name = f"Mariam Engineer {short}"

        # --- Rich accepted path + extraction promotion ---
        rich = app.process_postmark_inbound(
            _payload(
                f"d6b-rich-{short}",
                address,
                f"Agency <agency.{short}@example.com>",
                [_att(f"Mariam_{short}.pdf", _pdf_rich(rich_name, rich_email, rich_phone))],
            )
        )
        held_timing = _drain_to_held()
        rich_row = _inbound_row(rich["inbound_id"])
        assert_true(bool(rich_row.get("app_key")), f"rich held missing: {rich_row}")
        assert_true(rich_row.get("app_status") in {"needs_role", "import_review"}, f"rich status: {rich_row}")
        assert_true(rich_row.get("outcome") in {"new_candidate", "safe_exact_reuse"}, f"rich outcome: {rich_row}")
        assert_true(rich_row.get("safety_state") == "clean", f"rich safety: {rich_row}")
        results["app_keys"].append(rich_row["app_key"])

        ext1 = _drain_extraction()
        jobs1 = _jobs_for_doc(str(rich_row.get("candidate_document_id")))
        assert_true(len(jobs1) >= 1, "extraction job enqueued")
        assert_true(
            any(j["status"] == "completed" for j in jobs1),
            f"rich extraction must complete: {jobs1}",
        )
        completed = next(j for j in jobs1 if j["status"] == "completed")
        result = completed.get("result") or {}
        assert_true(
            result.get("ok") is True and result.get("status") != "extraction_soft_failed",
            f"rich extraction should fully succeed: {result}",
        )

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.email, c.name, c.profile,
                           a.raw_json->'cv' AS cv,
                           a.raw_json->'cv_pending' AS cv_pending,
                           (SELECT count(*) FROM candidate_documents WHERE app_key=%s) AS doc_count,
                           (SELECT count(*) FROM applications WHERE company_code=%s AND app_key=%s) AS app_count
                    FROM applications a
                    JOIN candidates c ON c.phone=a.phone
                    WHERE a.app_key=%s
                    """,
                    (rich_row["app_key"], COMPANY, rich_row["app_key"], rich_row["app_key"]),
                )
                promoted = dict(cur.fetchone() or {})
        assert_true(int(promoted.get("doc_count") or 0) == 1, f"no duplicate docs: {promoted}")
        assert_true(int(promoted.get("app_count") or 0) == 1, f"no duplicate apps: {promoted}")
        # Email from CV should be on candidate (from identity and/or extraction)
        assert_true(
            str(promoted.get("email") or "").lower() == rich_email.lower()
            or rich_email.lower() in json.dumps(promoted.get("profile") or {}).lower(),
            f"promoted email missing: {promoted}",
        )
        results["rich_path"] = {
            "ok": True,
            "held_timing": {k: v.get("processed") for k, v in held_timing.items()},
            "extraction_processed": ext1.get("processed"),
            "job_result_status": result.get("status") or "ok",
            "authorization_mode": result.get("authorization_mode"),
            "promoted_email": promoted.get("email"),
            "doc_count": promoted.get("doc_count"),
        }

        # Idempotent re-drain: no new jobs / no duplicate completion side effects
        ext2 = _drain_extraction()
        jobs2 = _jobs_for_doc(str(rich_row.get("candidate_document_id")))
        assert_true(len(jobs2) == len(jobs1), f"idempotent job count: {jobs1} vs {jobs2}")
        assert_true(int(ext2.get("processed") or 0) == 0, f"no reprocess: {ext2}")
        results["idempotent_extraction"] = {"ok": True, "second_processed": ext2.get("processed")}

        # Duplicate Message-ID
        dup = app.process_postmark_inbound(
            _payload(
                f"d6b-rich-{short}",
                address,
                f"Agency <agency.{short}@example.com>",
                [_att(f"Mariam_{short}.pdf", _pdf_rich(rich_name, rich_email, rich_phone))],
            )
        )
        assert_true(bool(dup.get("duplicate")) or dup.get("inbound_id") == rich["inbound_id"], "duplicate mid")
        results["duplicate_message"] = {"ok": True}

        # --- Conflict Held: must NOT raise intake_document_not_clean forever ---
        # Same CV email as rich, disjoint name → conflicting_cv_name Held review.
        # Use a per-run phone so leftover identity keys cannot force safe_exact_reuse.
        conflict_phone = f"+9655{uuid.uuid4().hex[:7]}"
        conflict = app.process_postmark_inbound(
            _payload(
                f"d6b-conflict-{short}",
                address,
                f"Other <other.{short}@example.com>",
                [_att("Noor_Tahat.pdf", _pdf_rich("Noor Tahat", rich_email, conflict_phone))],
            )
        )
        _drain_to_held()
        crow = _inbound_row(conflict["inbound_id"])
        assert_true(crow.get("outcome") == "conflict", f"conflict outcome: {crow}")
        assert_true(crow.get("warned") is True, f"conflict warned: {crow}")
        assert_true(crow.get("app_key") != rich_row.get("app_key"), "separate conflict app")
        assert_true(crow.get("safety_state") == "clean", f"conflict safety clean: {crow}")
        results["app_keys"].append(crow["app_key"])
        cext = _drain_extraction()
        cjobs = _jobs_for_doc(str(crow.get("candidate_document_id")))
        assert_true(any(j["status"] == "completed" for j in cjobs), f"conflict extract complete: {cjobs}")
        cdone = next(j for j in cjobs if j["status"] == "completed")
        cres = cdone.get("result") or {}
        # May soft-fail or succeed; must not sit retrying with intake_document_not_clean
        assert_true(
            cdone.get("last_error_code") != "intake_document_not_clean",
            f"not_clean mismatch fixed: {cdone}",
        )
        assert_true(
            cres.get("authorization_mode") == "held_identity_review_scan_clean"
            or cres.get("ok") is True,
            f"conflict auth mode: {cres}",
        )
        results["conflict_path"] = {
            "ok": True,
            "authorization_mode": cres.get("authorization_mode"),
            "extraction_status": cres.get("status") or ("ok" if cres.get("ok") else None),
            "processed": cext.get("processed"),
        }

        # --- Opaque weak CV: Held + soft-complete extraction (no infinite pending) ---
        opaque_short = uuid.uuid4().hex[:8]
        opaque = app.process_postmark_inbound(
            _payload(
                f"d6b-opaque-{opaque_short}",
                address,
                f"Opaque <opaque.{opaque_short}@example.com>",
                [_att(f"Opaque_{opaque_short}.pdf", _pdf_opaque(opaque_short))],
            )
        )
        _drain_to_held()
        orow = _inbound_row(opaque["inbound_id"])
        assert_true(bool(orow.get("app_key")), f"opaque held: {orow}")
        assert_true(
            orow.get("warned") is True
            or bool(orow.get("terminal_reason"))
            or orow.get("submission_status") in {"held_identity_review", "identity_review_required"},
            f"opaque warning preserved: {orow}",
        )
        results["app_keys"].append(orow["app_key"])
        _drain_extraction()
        ojobs = _jobs_for_doc(str(orow.get("candidate_document_id")))
        assert_true(any(j["status"] == "completed" for j in ojobs), f"opaque extract terminal: {ojobs}")
        odone = next(j for j in ojobs if j["status"] == "completed")
        ores = odone.get("result") or {}
        assert_true(
            ores.get("status") == "extraction_soft_failed" or ores.get("ok") is True,
            f"opaque soft-complete: {ores}",
        )
        assert_true(
            odone.get("status") == "completed" and odone.get("attempts", 0) <= 2,
            f"opaque must not burn retries: {odone}",
        )
        results["opaque_path"] = {
            "ok": True,
            "held_warning": bool(orow.get("warned") or orow.get("terminal_reason")),
            "extraction": ores,
        }

        # No open pending/retrying extraction for this company proof set
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) AS c FROM intake_processing_jobs
                    WHERE company_code=%s AND job_type='cv_extraction'
                      AND status IN ('pending','retrying')
                    """,
                    (COMPANY,),
                )
                open_jobs = int(cur.fetchone()["c"])
        assert_true(open_jobs == 0, f"no indefinite pending: open={open_jobs}")
        results["no_indefinite_pending"] = True

    except Exception as exc:
        results["passed"] = False
        results["error"] = str(exc)
        raise
    finally:
        results["cleanup"] = _cleanup(results.get("app_keys") or [])
        shutil.rmtree(_QUARANTINE, ignore_errors=True)
        shutil.rmtree(_WORKSPACE, ignore_errors=True)

    out = Path(os.environ.get("D6B_OUT") or "/tmp/waveD6B-local.json")
    out.write_text(json.dumps(results, indent=2, default=str) + "\n")
    print(json.dumps({"passed": results["passed"], "out": str(out)}, indent=2))
    return 0 if results["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
