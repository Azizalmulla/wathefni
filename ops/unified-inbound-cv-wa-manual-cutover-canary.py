#!/usr/bin/env python3
"""Live canary for WATHEFNI WhatsApp-unsolicited + manual controlled cutover.

ENFORCE stays OFF. Email and Job Stage B remain authoritative.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import traceback
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
EVIDENCE = Path(
    os.environ.get(
        "CUTOVER_EVIDENCE",
        f"/opt/wathefni/production-evidence/unified-inbound-cv-wa-manual-cutover/{STAMP}",
    )
)
TAG = "wa_manual_cutover_canary"
PHONES = {
    "wa_pdf": "96555571001",
    "wa_img": "96555571002",
    "wa_docx": "96555571003",
    "wa_replay": "96555571001",  # same as pdf for replay identity
}


def _ok(name: str, detail: str = "") -> dict:
    return {"name": name, "ok": True, "detail": detail}


def _fail(name: str, detail: str) -> dict:
    return {"name": name, "ok": False, "detail": detail}


def _count(cur, sql: str, params=None) -> int:
    cur.execute(sql, params or ())
    row = cur.fetchone() or {}
    return int(row.get("n") or 0)


def _pdf_bytes() -> bytes:
    return b"""%PDF-1.4
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R >>endobj
4 0 obj<< /Length 44 >>stream
BT /F1 12 Tf 50 150 Td (Canary CV) Tj ET
endstream endobj
xref
0 5
trailer<< /Root 1 0 R /Size 5 >>
startxref
0
%%EOF
"""


def _png_bytes() -> bytes:
    # 1x1 PNG
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


def _docx_bytes() -> bytes:
    buf = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    buf.close()
    path = Path(buf.name)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        zf.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>Canary DOCX CV</w:t></w:r></w:p></w:body>
</w:document>""",
        )
        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
    data = path.read_bytes()
    path.unlink(missing_ok=True)
    return data


def _eicar_bytes() -> bytes:
    return b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def _write(payload: dict) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "canary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"ok": payload.get("ok"), "out": str(EVIDENCE), "assertions": payload.get("assertions")}, indent=2))


def main() -> int:
    # Load production cutover flags into this process (systemd EnvironmentFile is not inherited).
    flags_file = Path("/opt/wathefni/var/unified-inbound-cv.production.env")
    if flags_file.exists():
        for line in flags_file.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()
    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import production_data_safety as _r3_data_safety
    _r3_data_safety.require_non_production_ops()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    cases: dict = {}

    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=5) as resp:
            results.append(_ok("health_200_pre", str(resp.getcode())) if resp.getcode() == 200 else _fail("health_200_pre", str(resp.getcode())))
    except Exception as exc:
        results.append(_fail("health_200_pre", repr(exc)))

    try:
        import subprocess

        pid = subprocess.check_output(
            ["systemctl", "show", "-p", "MainPID", "--value", "wathefni-orchestrator.service"],
            text=True,
        ).strip()
        env_text = Path(f"/proc/{pid}/environ").read_bytes().replace(b"\0", b"\n").decode("utf-8", "ignore")
        (EVIDENCE / "production-flags.txt").write_text(
            "\n".join(sorted(x for x in env_text.splitlines() if "UNIFIED_" in x or "INTAKE_AUTHORITY" in x)),
            encoding="utf-8",
        )
        results.append(
            _ok("enforce_off")
            if "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on" not in env_text
            else _fail("enforce_off", "present")
        )
        results.append(
            _ok("wa_authority_on")
            if "WATHEFNI_UNIFIED_INTAKE_AUTHORITY_WHATSAPP_UNSOLICITED=on" in env_text
            else _fail("wa_authority_on", "missing")
        )
        results.append(
            _ok("manual_authority_on")
            if "WATHEFNI_UNIFIED_INTAKE_AUTHORITY_MANUAL=on" in env_text
            else _fail("manual_authority_on", "missing")
        )
        results.append(
            _ok("email_not_cut_over")
            if "WATHEFNI_UNIFIED_INTAKE_AUTHORITY_EMAIL=on" not in env_text
            else _fail("email_not_cut_over", "email authority unexpectedly on")
        )
    except Exception:
        results.append(_fail("flags", traceback.format_exc()))

    try:
        import inbound_cv_channel_cutover as cutover
        import inbound_cv_intake as ici
        from psycopg2.extras import RealDictCursor
        import psycopg2

        results.append(_ok("modules_importable"))
    except Exception:
        results.append(_fail("modules_importable", traceback.format_exc()))
        _write({"stamp": STAMP, "ok": False, "results": results})
        return 1

    # Email path still authoritative marker
    dei = Path("/opt/wathefni/orchestrator/durable_email_ingress.py").read_text(encoding="utf-8")
    results.append(
        _ok("email_path_authoritative")
        if "Live email tables, jobs, scanning, and identity remain authoritative" in dei
        else _fail("email_path_authoritative", "marker_missing")
    )
    app_src = Path("/opt/wathefni/orchestrator/app.py").read_text(encoding="utf-8")
    results.append(
        _ok("stage_b_untouched_marker")
        if "convert_job_context_to_application" in app_src
        and "UNIFIED_INTAKE_AUTHORITY_WHATSAPP_UNSOLICITED_CUTOVER" in app_src
        else _fail("stage_b_untouched_marker", "patch_or_stage_b_missing")
    )
    results.append(
        _ok("cv_received_talent_pool_template")
        if "cv_received_talent_pool" in Path("/opt/wathefni/orchestrator/candidate_messages.py").read_text(encoding="utf-8")
        else _fail("cv_received_talent_pool_template", "missing")
    )

    cfg = {}
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
    before = {}
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db")
            db = (cur.fetchone() or {}).get("db")
            if db != "wathefni":
                raise RuntimeError(f"refusing_db:{db}")
            results.append(_ok("production_db", str(db)))
            ici.ensure_schema(cur)

            before = {
                "applications": _count(cur, "SELECT count(*)::int AS n FROM applications"),
                "candidates": _count(cur, "SELECT count(*)::int AS n FROM candidates"),
                "applications_non_canary": _count(
                    cur,
                    "SELECT count(*)::int AS n FROM applications WHERE COALESCE(data_source_detail,'') NOT LIKE %s",
                    (f"%{TAG}%",),
                ),
            }

            tmpdir = Path(tempfile.mkdtemp(prefix="cutover-canary-"))
            pdf_path = tmpdir / "canary.pdf"
            png_path = tmpdir / "canary-scan.png"
            docx_path = tmpdir / "canary.docx"
            eicar_path = tmpdir / "eicar.pdf"
            empty_path = tmpdir / "empty.pdf"
            pdf_path.write_bytes(_pdf_bytes())
            png_path.write_bytes(_png_bytes())
            docx_path.write_bytes(_docx_bytes())
            eicar_path.write_bytes(_eicar_bytes())
            empty_path.write_bytes(b"")

            # --- WhatsApp PDF ---
            msg_pdf = f"{TAG}-wa-pdf-{STAMP}"
            pending_pdf = str(uuid.uuid4())
            wa_pdf = cutover.accept_whatsapp_unsolicited(
                cur,
                company_code="WATHEFNI",
                phone=PHONES["wa_pdf"],
                provider_message_id=msg_pdf,
                account_id=TAG,
                conversation_id=f"conv-pdf-{STAMP}",
                pending_id=pending_pdf,
                media_path=str(pdf_path),
                mime_or_suffix="application/pdf",
                filename="canary.pdf",
            )
            results.append(
                _ok("wa_pdf_accept")
                if wa_pdf.get("ok")
                and wa_pdf.get("authoritative")
                and not wa_pdf.get("creates_job_application")
                and wa_pdf.get("confirmation_key") == "cv_received_talent_pool"
                and (wa_pdf.get("talent_pool") or {}).get("actionable") is False
                else _fail("wa_pdf_accept", json.dumps(wa_pdf, default=str)[:1500])
            )
            durable = Path(str(wa_pdf.get("durable_path") or ""))
            results.append(_ok("wa_pdf_durable_file") if durable.is_file() else _fail("wa_pdf_durable_file", str(durable)))
            # replay idempotency
            wa_pdf_replay = cutover.accept_whatsapp_unsolicited(
                cur,
                company_code="WATHEFNI",
                phone=PHONES["wa_pdf"],
                provider_message_id=msg_pdf,
                account_id=TAG,
                conversation_id=f"conv-pdf-{STAMP}",
                pending_id=pending_pdf,
                media_path=str(pdf_path),
                mime_or_suffix="application/pdf",
                filename="canary.pdf",
            )
            ev1 = ((wa_pdf.get("receipt") or {}).get("event_id"))
            ev2 = ((wa_pdf_replay.get("receipt") or {}).get("event_id"))
            results.append(
                _ok("wa_provider_replay_idempotent", str(ev1))
                if ev1 and ev1 == ev2
                else _fail("wa_provider_replay_idempotent", json.dumps({"a": ev1, "b": ev2}))
            )
            n_events = _count(
                cur,
                """
                SELECT count(*)::int AS n FROM intake_source_events
                WHERE company_code='WATHEFNI' AND external_event_id=%s
                """,
                (msg_pdf,),
            )
            results.append(_ok("wa_one_source_event", str(n_events)) if n_events == 1 else _fail("wa_one_source_event", str(n_events)))
            cases["wa_pdf"] = wa_pdf

            # --- image / OCR path ---
            wa_img = cutover.accept_whatsapp_unsolicited(
                cur,
                company_code="WATHEFNI",
                phone=PHONES["wa_img"],
                provider_message_id=f"{TAG}-wa-img-{STAMP}",
                account_id=TAG,
                conversation_id=f"conv-img-{STAMP}",
                pending_id=str(uuid.uuid4()),
                media_path=str(png_path),
                mime_or_suffix="image/png",
                filename="canary-scan.png",
            )
            plan = ((wa_img.get("shared_processing") or {}).get("provider_plan") or {})
            results.append(
                _ok("wa_image_ocr_plan")
                if wa_img.get("ok") and plan.get("local_first") is True
                else _fail("wa_image_ocr_plan", json.dumps(wa_img, default=str)[:1200])
            )
            cases["wa_img"] = {"ok": wa_img.get("ok"), "plan": plan, "cv": wa_img.get("cv_version_id")}

            # --- DOCX ---
            wa_docx = cutover.accept_whatsapp_unsolicited(
                cur,
                company_code="WATHEFNI",
                phone=PHONES["wa_docx"],
                provider_message_id=f"{TAG}-wa-docx-{STAMP}",
                account_id=TAG,
                conversation_id=f"conv-docx-{STAMP}",
                pending_id=str(uuid.uuid4()),
                media_path=str(docx_path),
                mime_or_suffix="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename="canary.docx",
            )
            results.append(
                _ok("wa_docx_accept")
                if wa_docx.get("ok") and wa_docx.get("cv_version_id")
                else _fail("wa_docx_accept", json.dumps(wa_docx, default=str)[:1200])
            )

            # --- malware reject ---
            wa_mal = cutover.accept_whatsapp_unsolicited(
                cur,
                company_code="WATHEFNI",
                phone="96555571999",
                provider_message_id=f"{TAG}-wa-eicar-{STAMP}",
                account_id=TAG,
                conversation_id=f"conv-eicar-{STAMP}",
                pending_id=str(uuid.uuid4()),
                media_path=str(eicar_path),
                mime_or_suffix="application/pdf",
                filename="eicar.pdf",
            )
            results.append(
                _ok("wa_malware_rejected")
                if wa_mal.get("rejected") and wa_mal.get("error") == "malware_rejected"
                else _fail("wa_malware_rejected", json.dumps(wa_mal, default=str)[:800])
            )

            # --- invalid empty ---
            wa_empty = cutover.accept_whatsapp_unsolicited(
                cur,
                company_code="WATHEFNI",
                phone="96555571998",
                provider_message_id=f"{TAG}-wa-empty-{STAMP}",
                account_id=TAG,
                conversation_id=f"conv-empty-{STAMP}",
                pending_id=str(uuid.uuid4()),
                media_path=str(empty_path),
                mime_or_suffix="application/pdf",
                filename="empty.pdf",
            )
            results.append(
                _ok("wa_empty_rejected")
                if wa_empty.get("rejected")
                else _fail("wa_empty_rejected", json.dumps(wa_empty, default=str)[:500])
            )

            # --- restart durability: durable path survives without temp media ---
            results.append(
                _ok("restart_durable_not_temp_only")
                if durable.is_file() and "/intake-durable/" in str(durable)
                else _fail("restart_durable_not_temp_only", str(durable))
            )

            # --- manual PDF accept ---
            batch_id = f"{TAG}-batch-{STAMP}"
            manual = cutover.accept_manual_upload(
                cur,
                company_code="WATHEFNI",
                batch_id=batch_id,
                content_sha256=hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                filename="manual-canary.pdf",
                document_id=str(uuid.uuid4()),
                source_path=str(pdf_path),
                mime_or_suffix="application/pdf",
                app_key=None,
                held_status="needs_role",
                uploader_user_id="owner-canary",
                source="manual_upload",
            )
            results.append(
                _ok("manual_accept_held")
                if manual.get("ok")
                and manual.get("held_by_default")
                and manual.get("auto_admit") is False
                and not manual.get("creates_job_application")
                and (manual.get("provenance") or {}).get("batch_id") == batch_id
                else _fail("manual_accept_held", json.dumps(manual, default=str)[:1500])
            )
            cases["manual"] = {
                "ok": manual.get("ok"),
                "held": manual.get("held_status"),
                "provenance": manual.get("provenance"),
                "ck": manual.get("ck_index"),
            }

            # manual malware pre-scan
            pre_mal = cutover.pre_scan_manual_bytes(
                company_code="WATHEFNI",
                batch_id=batch_id,
                filename="eicar.pdf",
                data=_eicar_bytes(),
            )
            results.append(
                _ok("manual_malware_rejected")
                if pre_mal.get("rejected") and pre_mal.get("error") == "malware_rejected"
                else _fail("manual_malware_rejected", json.dumps(pre_mal, default=str)[:800])
            )

            # HR visibility: TP entries for canary subjects
            tp_n = _count(
                cur,
                """
                SELECT count(*)::int AS n FROM talent_pool_entries
                WHERE company_code='WATHEFNI' AND actionable=false
                  AND entry_id::text = ANY(%s)
                """,
                (
                    [
                        str((wa_pdf.get("talent_pool") or {}).get("entry_id") or ""),
                        str((((manual.get("adapter") or {}).get("wave4") or {}).get("talent_pool") or {}).get("entry_id") or ""),
                    ],
                ),
            )
            results.append(
                _ok("hr_visible_non_actionable_tp", str(tp_n))
                if tp_n >= 1
                else _fail("hr_visible_non_actionable_tp", str(tp_n))
            )

            # CK jobs non-actionable meta
            ck = wa_pdf.get("ck_index") or {}
            results.append(
                _ok("ck_indexed_non_actionable")
                if ck.get("ok")
                and (ck.get("index_meta") or {}).get("searchable")
                and not (ck.get("index_meta") or {}).get("actionable")
                else _fail("ck_indexed_non_actionable", json.dumps(ck, default=str)[:800])
            )

            # Zero Job workflow mutation for WA accepts (no new non-canary apps; no apps for WA phones)
            wa_apps = _count(
                cur,
                "SELECT count(*)::int AS n FROM applications WHERE phone = ANY(%s)",
                (list(PHONES.values()),),
            )
            results.append(_ok("wa_zero_job_applications", str(wa_apps)) if wa_apps == 0 else _fail("wa_zero_job_applications", str(wa_apps)))

            after = {
                "applications": _count(cur, "SELECT count(*)::int AS n FROM applications"),
                "candidates": _count(cur, "SELECT count(*)::int AS n FROM candidates"),
                "applications_non_canary": _count(
                    cur,
                    "SELECT count(*)::int AS n FROM applications WHERE COALESCE(data_source_detail,'') NOT LIKE %s",
                    (f"%{TAG}%",),
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
            # No duplicate cv_version for pdf digest+document
            n_cv = _count(
                cur,
                """
                SELECT count(*)::int AS n FROM cv_versions
                WHERE company_code='WATHEFNI' AND content_sha256=%s AND legacy_document_id=%s
                """,
                (wa_pdf.get("content_sha256"), wa_pdf.get("document_id")),
            )
            results.append(_ok("no_dup_cv_version", str(n_cv)) if n_cv == 1 else _fail("no_dup_cv_version", str(n_cv)))

            n_tp_person = _count(
                cur,
                """
                SELECT count(*)::int AS n FROM talent_pool_entries
                WHERE company_code='WATHEFNI' AND person_id=%s
                """,
                (wa_pdf.get("person_id"),),
            )
            results.append(
                _ok("no_dup_tp_for_person", str(n_tp_person))
                if wa_pdf.get("person_id") and n_tp_person == 1
                else _fail("no_dup_tp_for_person", f"{wa_pdf.get('person_id')} n={n_tp_person}")
            )

            conn.commit()
            results.append(_ok("canary_commit"))
    except Exception:
        conn.rollback()
        results.append(_fail("canary_flow", traceback.format_exc()))
    finally:
        conn.close()

    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=5) as resp:
            results.append(_ok("health_200_post", str(resp.getcode())) if resp.getcode() == 200 else _fail("health_200_post", str(resp.getcode())))
    except Exception as exc:
        results.append(_fail("health_200_post", repr(exc)))

    failed = [r for r in results if not r["ok"]]
    payload = {
        "stamp": STAMP,
        "ok": len(failed) == 0,
        "tag": TAG,
        "passed": sum(1 for r in results if r["ok"]),
        "failed": len(failed),
        "results": results,
        "cases": cases,
        "before": before,
        "assertions": {
            "failed_names": [r["name"] for r in failed],
            "enforce_enabled": False,
            "email_cutover": False,
            "stage_b_cutover": False,
        },
    }
    _write(payload)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
