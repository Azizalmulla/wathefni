#!/usr/bin/env python3
"""Wave D6A — durable → Held materialization regression (local).

Proves the D6 failure mode is fixed:
* short/synthetic CV text still materializes a Held application (or accepted path)
* identity conflict materializes Held with identity_review_warning
* duplicate MessageID stays idempotent
* worker stages run with realistic sequential timing
* no silent completed identity job without Held app / terminal reason

Does not enable external tenants. Does not start post-hiring.
"""

from __future__ import annotations

from typing import Any

import base64
import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

_QUARANTINE = Path(tempfile.mkdtemp(prefix="wathefni-d6a-"))
_WORKSPACE = Path(tempfile.mkdtemp(prefix="wathefni-d6a-ws-"))
database_url = str(os.environ.get("WATHEFNI_TEST_DATABASE_URL") or "").strip()
if not database_url:
    env_path = Path("/tmp/waveC-local-env/postgres.test.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("WATHEFNI_DATABASE_URL="):
                database_url = line.split("=", 1)[1].strip()
                break
if database_url:
    parsed_database = urlparse(database_url)
    env_file = _QUARANTINE / "postgres.test.env"
    env_file.write_text(f"WATHEFNI_DATABASE_URL={database_url}\n")
    os.environ["WATHEFNI_POSTGRES_ENV"] = str(env_file)
    os.environ["WATHEFNI_ENV"] = "test"
    os.environ["WATHEFNI_EXPECTED_DATABASE_HOST"] = parsed_database.hostname or "127.0.0.1"
    os.environ["WATHEFNI_EXPECTED_DATABASE_PORT"] = str(parsed_database.port or 5432)
    os.environ["WATHEFNI_EXPECTED_DATABASE_NAME"] = parsed_database.path.lstrip("/")
    os.environ.setdefault(
        "WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-local-boundary-remediation-v1"
    )
elif not os.environ.get("WATHEFNI_POSTGRES_ENV"):
    raise RuntimeError(
        "Set WATHEFNI_POSTGRES_ENV or WATHEFNI_TEST_DATABASE_URL to an isolated test database."
    )

os.environ["WATHEFNI_WORKSPACE"] = str(_WORKSPACE)
os.environ["WATHEFNI_INBOUND_EMAIL"] = "on"
os.environ["WATHEFNI_INBOUND_ALLOWED_COMPANIES"] = "D6AALPHA,D6ABRAVO"
os.environ.setdefault("WATHEFNI_POSTMARK_INBOUND_SECRET", "smoke-secret-token")
os.environ["WATHEFNI_INTAKE_QUARANTINE_DIR"] = str(_QUARANTINE)
os.environ["WATHEFNI_INTAKE_MALWARE_SCANNER"] = "test_clean"
os.environ["WATHEFNI_INTAKE_ALLOW_TEST_SCANNER"] = "1"
os.environ["WATHEFNI_MAILBOX_SYNC"] = "off"

import app  # noqa: E402

COMPANY = "D6AALPHA"
MARKER = "wave_d6a_held_materialization"
RUNS = 3


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _pdf_short(name: str, email: str) -> bytes:
    """D6-style thin PDF that fails full quality gate but still exposes contact."""
    return _make_pdf([name, f"Email {email}"])


def _pdf_rich(name: str, email: str) -> bytes:
    summary = (
        "Senior Welder with eight years of industrial inspection experience, "
        "safety compliance, NDT testing, team leadership, technical reporting, "
        "quality assurance, and bilingual client coordination."
    )
    return _make_pdf([name, f"Email {email}", summary])


def _make_pdf(lines: list[str]) -> bytes:
    """Minimal structurally valid PDF with text in the content stream."""
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
    objects.append(
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n"
    )
    header = b"%PDF-1.4\n"
    body = b"".join(objects)
    offsets = [0]
    pos = len(header)
    for obj in objects:
        offsets.append(pos)
        pos += len(obj)
    xref_pos = pos
    xref = [b"xref\n0 6\n", b"0000000000 65535 f \n"]
    for off in offsets[1:]:
        xref.append(f"{off:010d} 00000 n \n".encode())
    trailer = (
        f"trailer<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return header + body + b"".join(xref) + trailer


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


def _run_stage(job_type: str, *, limit: int = 20) -> dict:
    t0 = time.perf_counter()
    out = app.run_durable_email_ingress_worker(limit=limit, job_types=[job_type])
    out["_elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    return out


def _drain_pipeline() -> dict[str, Any]:
    """Realistic sequential worker timing across the durable → Held bridge."""
    timing = {}
    for stage in (
        "intake_validation",
        "file_safety_scan",
        "cv_identity_resolution",
        "accepted_intake_preparation",
        "held_intake_materialization",
    ):
        timing[stage] = _run_stage(stage)
    return timing


def _ensure_company_and_address() -> str:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO companies (company_code, name, status)
                VALUES (%s,%s,'active')
                ON CONFLICT (company_code) DO UPDATE SET status='active'
                """,
                (COMPANY, "D6A Alpha"),
            )
            # Soft-disable prior marker addresses
            cur.execute(
                """
                UPDATE intake_addresses SET status='disabled'
                WHERE company_code=%s AND label ILIKE %s AND status='active'
                """,
                (COMPANY, f"%{MARKER}%"),
            )
            local = f"d6a-{uuid.uuid4().hex[:8]}"
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


def _cleanup() -> dict:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT app_key FROM applications
                WHERE company_code=%s
                  AND status IN ('needs_role','import_review','import_archived')
                  AND (
                    coalesce(raw_json->>'candidate_name','') ILIKE 'D6A %%'
                    OR coalesce(raw_json->>'candidate_name','') ILIKE 'Ali Hassan%%'
                    OR coalesce(raw_json->>'candidate_name','') ILIKE 'Noor Tahat%%'
                    OR coalesce(raw_json->>'candidate_name','') ILIKE 'Zayd%%'
                    OR coalesce(source_ref,'') ILIKE %s
                    OR coalesce(raw_json->'import'->>'original_filename','') ILIKE 'D6A%%'
                    OR coalesce(raw_json->'import'->>'original_filename','') ILIKE 'Ali_%%'
                    OR coalesce(raw_json->'import'->>'original_filename','') ILIKE 'Noor_%%'
                    OR coalesce(raw_json->'import'->>'original_filename','') ILIKE 'Zayd_%%'
                    OR phone LIKE 'imp-d6aalpha-%%'
                  )
                """,
                (COMPANY, f"%{MARKER}%"),
            )
            keys = [r["app_key"] for r in cur.fetchall()]
            if keys:
                cur.execute(
                    "UPDATE applications SET status='import_archived' WHERE company_code=%s AND app_key = ANY(%s)",
                    (COMPANY, keys),
                )
            # Drop weak-name pollution from prior D6A runs so new_candidate stays deterministic.
            cur.execute(
                """
                UPDATE candidates
                SET name=NULL,
                    email=NULL,
                    current_status='import_archived',
                    profile = COALESCE(profile,'{}'::jsonb) || '{"d6a_sterilized": true}'::jsonb,
                    updated_at=now()
                WHERE active_company_code=%s
                  AND phone LIKE 'imp-d6aalpha-%%'
                """,
                (COMPANY,),
            )
            cur.execute(
                """
                UPDATE candidate_identity_keys
                SET active=false
                WHERE company_code=%s
                  AND candidate_phone LIKE 'imp-d6aalpha-%%'
                  AND active
                """,
                (COMPANY,),
            )
            cur.execute(
                """
                UPDATE intake_addresses SET status='disabled'
                WHERE company_code=%s AND label ILIKE %s AND status='active'
                """,
                (COMPANY, f"%{MARKER}%"),
            )
            cur.execute(
                "SELECT count(*) AS c FROM intake_addresses WHERE company_code=%s AND status='active'",
                (COMPANY,),
            )
            active = cur.fetchone()["c"]
        conn.commit()
    return {"archived_apps": len(keys), "active_intakes": active}


def run_once(run_idx: int, address: str) -> dict:
    short = uuid.uuid4().hex[:8]
    email = f"d6a.cand.{run_idx}.{short}@example.com"
    mid = f"d6a-{run_idx}-{short}"
    receipt = app.process_postmark_inbound(
        _payload(
            mid,
            address,
            f"Agency Desk <agency.{short}@example.com>",
            [_att(f"D6A_Short_{short}.pdf", _pdf_short(f"D6A Cand {short}", email))],
        )
    )
    assert_true(receipt.get("durable") is True, f"run{run_idx} durable receive")
    timing = _drain_pipeline()

    # Duplicate replay
    dup = app.process_postmark_inbound(
        _payload(
            mid,
            address,
            f"Agency Desk <agency.{short}@example.com>",
            [_att(f"D6A_Short_{short}.pdf", _pdf_short(f"D6A Cand {short}", email))],
        )
    )
    assert_true(bool(dup.get("duplicate")) or dup.get("inbound_id") == receipt.get("inbound_id"), f"run{run_idx} duplicate")

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.app_key, d.metadata, r.outcome,
                       a.status AS app_status,
                       c.email AS candidate_email,
                       COALESCE((a.raw_json->'import'->>'identity_review_warning')::boolean,false) AS warned,
                       a.raw_json->'import'->>'identity_terminal_reason' AS terminal_reason,
                       s.status AS submission_status
                FROM intake_documents d
                JOIN intake_submissions s ON s.submission_id=d.submission_id
                LEFT JOIN inbound_cv_identity_resolutions r
                  ON r.intake_document_id=d.document_id AND r.company_code=d.company_code
                LEFT JOIN applications a ON a.app_key=d.app_key AND a.company_code=d.company_code
                LEFT JOIN candidates c ON c.phone=a.phone
                WHERE d.inbound_id=%s
                ORDER BY d.created_at
                """,
                (receipt["inbound_id"],),
            )
            rows = [dict(r) for r in cur.fetchall()]
    assert_true(len(rows) >= 1, f"run{run_idx} document present")
    row = rows[0]
    assert_true(bool(row.get("app_key")), f"run{run_idx} Held app_key materialized: {row}")
    assert_true(
        row.get("app_status") in {"needs_role", "import_review"},
        f"run{run_idx} Held status: {row.get('app_status')}",
    )
    # Either accepted (contact-only soft path) without warning, or blocked with warning/terminal
    if row.get("outcome") in {"new_candidate", "safe_exact_reuse"}:
        materialization = "accepted"
    else:
        materialization = "held_identity_review"
        assert_true(
            bool(row.get("warned")) or bool(row.get("terminal_reason")) or row.get("submission_status") in {"identity_review_required", "held_identity_review"},
            f"run{run_idx} explicit terminal reason required: {row}",
        )

    # No silent identity completion without materialization job or accepted prepare
    assert_true(
        int((timing.get("accepted_intake_preparation") or {}).get("processed") or 0)
        + int((timing.get("held_intake_materialization") or {}).get("processed") or 0)
        >= 1
        or bool(row.get("app_key")),
        f"run{run_idx} preparation/materialization ran",
    )
    return {
        "run": run_idx,
        "inbound_id": receipt.get("inbound_id"),
        "app_key": row.get("app_key"),
        "outcome": row.get("outcome"),
        "materialization": materialization,
        "timing": {k: {"processed": v.get("processed"), "elapsed_ms": v.get("_elapsed_ms")} for k, v in timing.items()},
        "duplicate_ok": True,
    }


def main() -> int:
    results = {"marker": MARKER, "runs": [], "passed": True}
    results["pre_cleanup"] = _cleanup()
    address = _ensure_company_and_address()
    try:
        for i in range(1, RUNS + 1):
            results["runs"].append(run_once(i, address))

        # Rich CV happy path still reaches accepted Held needs_role
        short = uuid.uuid4().hex[:8]
        rich_email = f"d6a.rich.{short}@example.com"
        rich_name = f"Zayd Unique {short}"
        rich = app.process_postmark_inbound(
            _payload(
                f"d6a-rich-{short}",
                address,
                f"Agency <agency.rich.{short}@example.com>",
                [_att(f"Zayd_Unique_{short}.pdf", _pdf_rich(rich_name, rich_email))],
            )
        )
        timing = _drain_pipeline()
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT a.app_key, a.status, c.email, r.outcome,
                           COALESCE((a.raw_json->'import'->>'identity_review_warning')::boolean,false) AS warned
                    FROM intake_documents d
                    JOIN inbound_cv_identity_resolutions r ON r.intake_document_id=d.document_id
                    JOIN applications a ON a.app_key=d.app_key
                    JOIN candidates c ON c.phone=a.phone
                    WHERE d.inbound_id=%s
                    """,
                    (rich["inbound_id"],),
                )
                rich_row = dict(cur.fetchone() or {})
        assert_true(rich_row.get("status") == "needs_role", f"rich held: {rich_row}")
        assert_true(rich_row.get("email") == rich_email, f"rich email from CV: {rich_row}")
        assert_true(rich_row.get("outcome") in {"new_candidate", "safe_exact_reuse"}, f"rich outcome: {rich_row}")
        assert_true(rich_row.get("warned") is False, "rich path should not warn")
        results["rich_path"] = {
            "ok": True,
            "row": rich_row,
            "accepted_processed": (timing.get("accepted_intake_preparation") or {}).get("processed"),
        }

        # Conflict path: same CV email as existing held candidate, disjoint name → Held warning
        conflict = app.process_postmark_inbound(
            _payload(
                f"d6a-conflict-{short}",
                address,
                f"Other Desk <other.{short}@example.com>",
                [_att(f"Noor_Tahat_CV.pdf", _pdf_rich("Noor Tahat", rich_email))],
            )
        )
        _drain_pipeline()
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.outcome, r.ownership_confirmed, d.app_key, a.status,
                           COALESCE((a.raw_json->'import'->>'identity_review_warning')::boolean,false) AS warned
                    FROM intake_documents d
                    JOIN inbound_cv_identity_resolutions r ON r.intake_document_id=d.document_id
                    LEFT JOIN applications a ON a.app_key=d.app_key
                    WHERE d.inbound_id=%s
                    """,
                    (conflict["inbound_id"],),
                )
                crow = dict(cur.fetchone() or {})
        assert_true(crow.get("outcome") == "conflict", f"conflict outcome: {crow}")
        assert_true(crow.get("ownership_confirmed") is False, f"conflict ownership: {crow}")
        assert_true(bool(crow.get("app_key")) and crow.get("status") in {"needs_role", "import_review"}, f"conflict held: {crow}")
        assert_true(crow.get("warned") is True, f"conflict warned: {crow}")
        assert_true(crow.get("app_key") != rich_row.get("app_key"), "conflict must not reuse rich app_key")
        results["conflict_path"] = {"ok": True, "row": crow}

        # Opaque CV (no parseable contact): must still Held-materialize with terminal reason
        opaque_short = uuid.uuid4().hex[:8]
        opaque = app.process_postmark_inbound(
            _payload(
                f"d6a-opaque-{opaque_short}",
                address,
                f"Opaque Desk <opaque.{opaque_short}@example.com>",
                [
                    _att(
                        f"Opaque_{opaque_short}.pdf",
                        _make_pdf(
                            [
                                f"Curriculum Vitae page {opaque_short}",
                                "skills list only without contact channels",
                            ]
                        ),
                    )
                ],
            )
        )
        opaque_timing = _drain_pipeline()
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.outcome, d.app_key, a.status, s.status AS submission_status,
                           COALESCE((a.raw_json->'import'->>'identity_review_warning')::boolean,false) AS warned,
                           a.raw_json->'import'->>'identity_terminal_reason' AS terminal_reason
                    FROM intake_documents d
                    JOIN intake_submissions s ON s.submission_id=d.submission_id
                    JOIN inbound_cv_identity_resolutions r ON r.intake_document_id=d.document_id
                    LEFT JOIN applications a ON a.app_key=d.app_key
                    WHERE d.inbound_id=%s
                    """,
                    (opaque["inbound_id"],),
                )
                orow = dict(cur.fetchone() or {})
        assert_true(bool(orow.get("app_key")), f"opaque must materialize Held: {orow}")
        assert_true(
            orow.get("status") in {"needs_role", "import_review"},
            f"opaque held status: {orow}",
        )
        assert_true(
            orow.get("warned") is True
            or bool(orow.get("terminal_reason"))
            or orow.get("submission_status") in {"identity_review_required", "held_identity_review"},
            f"opaque terminal visibility: {orow}",
        )
        assert_true(
            int((opaque_timing.get("held_intake_materialization") or {}).get("processed") or 0) >= 1,
            f"opaque held worker: {opaque_timing}",
        )
        results["opaque_path"] = {
            "ok": True,
            "row": orow,
            "held_processed": (opaque_timing.get("held_intake_materialization") or {}).get("processed"),
            "held_ms": (opaque_timing.get("held_intake_materialization") or {}).get("_elapsed_ms"),
        }

    except Exception as exc:
        results["passed"] = False
        results["error"] = str(exc)
        raise
    finally:
        results["cleanup"] = _cleanup()
        shutil.rmtree(_QUARANTINE, ignore_errors=True)
        shutil.rmtree(_WORKSPACE, ignore_errors=True)

    out = Path(os.environ.get("D6A_OUT") or "/tmp/waveD6A-local-matrix.json")
    out.write_text(json.dumps(results, indent=2, default=str) + "\n")
    print(json.dumps({"passed": results["passed"], "runs": len(results["runs"]), "out": str(out)}, indent=2))
    return 0 if results["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
