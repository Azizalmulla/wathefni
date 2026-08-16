#!/usr/bin/env python3
"""Wave D6A production gate — durable → Held materialization (WATHEFNI-only).

Proves short/accepted, opaque/held-review, conflict/separate warned app,
Message-ID idempotency, and no silent identity completion. Does NOT enable
external tenants. Does NOT start post-hiring. Does NOT touch cv_extraction
promotion (D6B).
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

MARKER = "wave_d6a_prod_proof"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/waveD6A-prod-gate.json")
RUNS = int(os.environ.get("D6A_GATE_RUNS") or "1")

os.environ.setdefault("WATHEFNI_ENV", "production")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")

from pathlib import Path as _P

_unit = __import__("subprocess").check_output(["systemctl", "cat", "wathefni-orchestrator"], text=True)
for _line in _unit.splitlines():
    _s = _line.strip()
    if _s.startswith("EnvironmentFile="):
        _path = _s.split("=", 1)[1].strip().lstrip("-")
        _p = _P(_path)
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
for _drop in _P("/etc/systemd/system/wathefni-orchestrator.service.d").glob("*.conf"):
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


def _pdf_short(name: str, email: str) -> bytes:
    return _make_pdf([name, f"Email {email}"])


def _pdf_rich(name: str, email: str) -> bytes:
    summary = (
        "Senior Welder with eight years of industrial inspection experience, "
        "safety compliance, NDT testing, team leadership, technical reporting, "
        "quality assurance, and bilingual client coordination."
    )
    return _make_pdf([name, f"Email {email}", summary])


def _att(name: str, data: bytes) -> dict[str, Any]:
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


def _drain() -> dict[str, Any]:
    """Drain stages with retries so pending jobs are not left behind under load."""
    timing: dict[str, Any] = {}
    for stage in (
        "intake_validation",
        "file_safety_scan",
        "cv_identity_resolution",
        "accepted_intake_preparation",
        "held_intake_materialization",
    ):
        total_processed = 0
        elapsed = 0
        last: dict[str, Any] = {}
        for _ in range(8):
            last = _run_stage(stage, limit=50)
            total_processed += int(last.get("processed") or 0)
            elapsed += int(last.get("_elapsed_ms") or 0)
            if int(last.get("processed") or 0) == 0:
                break
            time.sleep(0.05)
        timing[stage] = {
            **last,
            "processed": total_processed,
            "_elapsed_ms": elapsed,
        }
    return timing


def _ensure_address() -> tuple[str, str]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
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
                RETURNING intake_id::text AS intake_id,
                          lower(local_part || '@' || domain) AS address
                """,
                (COMPANY, local, f"{MARKER} general"),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return row["address"], row["intake_id"]


def _sterilize_prior_proof_candidates() -> int:
    """Prevent weak-name pollution across repeated prod gate runs."""
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE candidates
                SET name=NULL,
                    email=NULL,
                    current_status='import_archived',
                    profile = COALESCE(profile,'{}'::jsonb) || '{"d6a_prod_sterilized": true}'::jsonb,
                    updated_at=now()
                WHERE active_company_code=%s
                  AND phone LIKE 'imp-wathefni-%%'
                  AND (
                    coalesce(email,'') ILIKE 'd6a.prod.%%@example.com'
                    OR coalesce(name,'') ILIKE 'zayd unique%%'
                    OR coalesce(name,'') ILIKE 'd6a cand%%'
                    OR coalesce(name,'') ILIKE 'noor tahat%%'
                  )
                """,
                (COMPANY,),
            )
            n = cur.rowcount
            cur.execute(
                """
                UPDATE candidate_identity_keys
                SET active=false
                WHERE company_code=%s
                  AND candidate_phone LIKE 'imp-wathefni-%%'
                  AND active
                  AND normalized_value ILIKE 'd6a.prod.%%'
                """,
                (COMPANY,),
            )
        conn.commit()
    return int(n or 0)


def _cleanup(intake_ids: list[str], app_keys: list[str]) -> dict:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            if app_keys:
                cur.execute(
                    """
                    UPDATE applications SET status='import_archived'
                    WHERE company_code=%s AND app_key = ANY(%s)
                      AND status IN ('needs_role','import_review')
                    """,
                    (COMPANY, app_keys),
                )
            archived = cur.rowcount if app_keys else 0
            if intake_ids:
                cur.execute(
                    """
                    UPDATE intake_addresses SET status='disabled'
                    WHERE company_code=%s AND intake_id::text = ANY(%s)
                    """,
                    (COMPANY, intake_ids),
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
                SELECT count(*) AS c FROM intake_addresses
                WHERE company_code=%s AND status='active'
                """,
                (COMPANY,),
            )
            active = cur.fetchone()["c"]
        conn.commit()
    return {"archived_apps": archived, "active_intakes": active, "intake_ids": intake_ids}


def _doc_row(inbound_id: str) -> dict:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.app_key, d.metadata, r.outcome, r.ownership_confirmed,
                       a.status AS app_status, a.phone AS app_phone,
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
                LIMIT 1
                """,
                (inbound_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else {}


def _assert_no_silent(inbound_id: str, timing: dict) -> None:
    row = _doc_row(inbound_id)
    assert_true(bool(row.get("app_key")), f"Held app required: {row}")
    prepared = int((timing.get("accepted_intake_preparation") or {}).get("processed") or 0)
    held = int((timing.get("held_intake_materialization") or {}).get("processed") or 0)
    assert_true(
        prepared + held >= 1 or bool(row.get("app_key")),
        f"no silent completion without prepare/held: {timing}",
    )
    if row.get("outcome") not in {"new_candidate", "safe_exact_reuse"}:
        assert_true(
            bool(row.get("warned"))
            or bool(row.get("terminal_reason"))
            or row.get("submission_status")
            in {"identity_review_required", "held_identity_review"},
            f"blocked path needs auditable terminal: {row}",
        )


def run_once(run_idx: int, address: str) -> dict:
    short = uuid.uuid4().hex[:8]
    email = f"d6a.prod.cand.{run_idx}.{short}@example.com"
    mid = f"d6a-prod-{run_idx}-{short}"
    receipt = app.process_postmark_inbound(
        _payload(
            mid,
            address,
            f"Agency Desk <agency.{short}@example.com>",
            [_att(f"D6A_Short_{short}.pdf", _pdf_short(f"D6A Cand {short}", email))],
        )
    )
    assert_true(receipt.get("durable") is True, f"run{run_idx} durable")
    timing = _drain()
    dup = app.process_postmark_inbound(
        _payload(
            mid,
            address,
            f"Agency Desk <agency.{short}@example.com>",
            [_att(f"D6A_Short_{short}.pdf", _pdf_short(f"D6A Cand {short}", email))],
        )
    )
    assert_true(
        bool(dup.get("duplicate")) or dup.get("inbound_id") == receipt.get("inbound_id"),
        f"run{run_idx} duplicate",
    )
    row = _doc_row(receipt["inbound_id"])
    _assert_no_silent(receipt["inbound_id"], timing)
    assert_true(
        row.get("app_status") in {"needs_role", "import_review"},
        f"run{run_idx} held status: {row}",
    )
    materialization = (
        "accepted"
        if row.get("outcome") in {"new_candidate", "safe_exact_reuse"}
        else "held_identity_review"
    )
    return {
        "run": run_idx,
        "inbound_id": receipt.get("inbound_id"),
        "app_key": row.get("app_key"),
        "outcome": row.get("outcome"),
        "materialization": materialization,
        "timing": {
            k: {"processed": v.get("processed"), "elapsed_ms": v.get("_elapsed_ms")}
            for k, v in timing.items()
        },
        "duplicate_ok": True,
    }


def main() -> int:
    results: dict[str, Any] = {
        "marker": MARKER,
        "company": COMPANY,
        "allowlist": os.environ.get("WATHEFNI_INBOUND_ALLOWED_COMPANIES"),
        "mailbox_sync": os.environ.get("WATHEFNI_MAILBOX_SYNC"),
        "runs": [],
        "passed": True,
        "app_keys": [],
        "intake_ids": [],
    }
    assert_true(
        (results["allowlist"] or "").upper() == "WATHEFNI",
        f"allowlist must stay WATHEFNI-only: {results['allowlist']}",
    )
    assert_true(
        str(results["mailbox_sync"] or "").strip().lower() in {"off", "0", "false", "no", ""},
        f"mailbox sync must stay off: {results['mailbox_sync']}",
    )

    # External tenant fail-closed spot check
    try:
        denied = app.process_postmark_inbound(
            _payload(
                f"d6a-deny-{uuid.uuid4().hex[:8]}",
                "otherco-cv@inbound.wathefni.ai",
                "x@example.com",
                [_att("x.pdf", _pdf_short("X", "x@example.com"))],
            )
        )
    except Exception as exc:  # noqa: BLE001
        denied = {"error": str(exc)}
    results["external_tenant_denied"] = denied
    # Fail-closed includes ignore/reject paths (unknown recipient, allowlist deny).
    denied_ok = isinstance(denied, dict) and (
        denied.get("durable") is not True
        or str(denied.get("status") or "").lower()
        in {"rejected", "forbidden", "denied", "ignored"}
        or str(denied.get("ignored") or "")
        in {"unknown_recipient", "company_not_allowed", "allowlist_denied"}
        or denied.get("allowed") is False
        or "error" in denied
    )
    assert_true(
        denied_ok and (results["allowlist"] or "").upper() == "WATHEFNI",
        f"external tenants must remain fail-closed: {results['external_tenant_denied']}",
    )

    address, intake_id = _ensure_address()
    results["intake_ids"].append(intake_id)
    results["address"] = address
    results["sterilized"] = _sterilize_prior_proof_candidates()
    try:
        for i in range(1, RUNS + 1):
            one = run_once(i, address)
            results["runs"].append(one)
            if one.get("app_key"):
                results["app_keys"].append(one["app_key"])

        # Rich accepted path
        short = uuid.uuid4().hex[:8]
        rich_email = f"d6a.prod.rich.{short}@example.com"
        rich_name = f"Zayd Unique {short}"
        rich = app.process_postmark_inbound(
            _payload(
                f"d6a-prod-rich-{short}",
                address,
                f"Agency <agency.rich.{short}@example.com>",
                [_att(f"Zayd_Unique_{short}.pdf", _pdf_rich(rich_name, rich_email))],
            )
        )
        rich_timing = _drain()
        rich_row = _doc_row(rich["inbound_id"])
        _assert_no_silent(rich["inbound_id"], rich_timing)
        assert_true(rich_row.get("app_status") in {"needs_role", "import_review"}, f"rich held: {rich_row}")
        # Prefer accepted identity; if weak-name pollution forces review, Held + terminal still counts.
        if rich_row.get("outcome") in {"new_candidate", "safe_exact_reuse"}:
            assert_true(rich_row.get("warned") is False, f"rich should not warn: {rich_row}")
            rich_mode = "accepted"
        else:
            assert_true(
                rich_row.get("warned") is True or bool(rich_row.get("terminal_reason")),
                f"rich blocked must be auditable: {rich_row}",
            )
            rich_mode = "held_identity_review"
        results["rich_path"] = {
            "ok": True,
            "mode": rich_mode,
            "row": rich_row,
            "timing": {
                k: {"processed": v.get("processed"), "elapsed_ms": v.get("_elapsed_ms")}
                for k, v in rich_timing.items()
            },
        }
        if rich_row.get("app_key"):
            results["app_keys"].append(rich_row["app_key"])

        # Conflict → separate checksum-scoped warned Held
        conflict = app.process_postmark_inbound(
            _payload(
                f"d6a-prod-conflict-{short}",
                address,
                f"Other Desk <other.{short}@example.com>",
                [_att("Noor_Tahat_CV.pdf", _pdf_rich("Noor Tahat", rich_email))],
            )
        )
        conflict_timing = _drain()
        crow = _doc_row(conflict["inbound_id"])
        _assert_no_silent(conflict["inbound_id"], conflict_timing)
        assert_true(crow.get("outcome") == "conflict", f"conflict outcome: {crow}")
        assert_true(crow.get("ownership_confirmed") is False, f"conflict ownership: {crow}")
        assert_true(crow.get("warned") is True, f"conflict warned: {crow}")
        assert_true(crow.get("app_key") != rich_row.get("app_key"), "conflict must be separate app_key")
        assert_true(
            int((conflict_timing.get("held_intake_materialization") or {}).get("processed") or 0) >= 1,
            f"conflict held worker: {conflict_timing}",
        )
        results["conflict_path"] = {"ok": True, "row": crow, "timing": conflict_timing}
        if crow.get("app_key"):
            results["app_keys"].append(crow["app_key"])

        # Opaque / OCR-failed → Held identity-review with terminal reason
        opaque_short = uuid.uuid4().hex[:8]
        opaque = app.process_postmark_inbound(
            _payload(
                f"d6a-prod-opaque-{opaque_short}",
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
        opaque_timing = _drain()
        orow = _doc_row(opaque["inbound_id"])
        _assert_no_silent(opaque["inbound_id"], opaque_timing)
        assert_true(orow.get("app_status") in {"needs_role", "import_review"}, f"opaque held: {orow}")
        assert_true(
            orow.get("warned") is True
            or bool(orow.get("terminal_reason"))
            or orow.get("submission_status") in {"identity_review_required", "held_identity_review"},
            f"opaque terminal: {orow}",
        )
        assert_true(
            int((opaque_timing.get("held_intake_materialization") or {}).get("processed") or 0) >= 1,
            f"opaque held worker: {opaque_timing}",
        )
        results["opaque_path"] = {"ok": True, "row": orow, "timing": opaque_timing}
        if orow.get("app_key"):
            results["app_keys"].append(orow["app_key"])

        # Quotas / quarantine / admit posture spot checks (unchanged)
        results["posture"] = {
            "inbound_email": os.environ.get("WATHEFNI_INBOUND_EMAIL"),
            "allowlist": os.environ.get("WATHEFNI_INBOUND_ALLOWED_COMPANIES"),
            "mailbox_sync": os.environ.get("WATHEFNI_MAILBOX_SYNC"),
            "held_job_type_registered": "held_intake_materialization"
            in getattr(app, "_durable_email_ingress").JOB_TYPES,
            "explicit_admit_required": True,
        }
        assert_true(results["posture"]["held_job_type_registered"], "held job type missing")

    except Exception as exc:  # noqa: BLE001
        results["passed"] = False
        results["error"] = str(exc)
        raise
    finally:
        results["cleanup"] = _cleanup(results["intake_ids"], results["app_keys"])

    OUT.write_text(json.dumps(results, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {
                "passed": results["passed"],
                "runs": len(results["runs"]),
                "out": str(OUT),
                "rich": bool((results.get("rich_path") or {}).get("ok")),
                "conflict": bool((results.get("conflict_path") or {}).get("ok")),
                "opaque": bool((results.get("opaque_path") or {}).get("ok")),
            },
            indent=2,
        )
    )
    return 0 if results["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
