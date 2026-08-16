#!/usr/bin/env python3
"""Live-HTTP production qualification matrix for default_kuwait@2.0.0 upload docs.

Uses minted employee session → live uvicorn (127.0.0.1:8010).
Each document type runs in an isolated subprocess with hard timeout so one
OCR stall cannot block the matrix. Partial results are preserved on disk.

Never mutates Aziz real civil_id. Bank ESS out of scope.
"""

from __future__ import annotations

import production_data_safety as _r3_data_safety
_r3_data_safety.require_explicit_environment()
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EMP = "WATHEFNI-96599338566"
OTHER_EMP = "WATHEFNI-96550252254"
COMPANY = "WATHEFNI"
EXPECTED_CIVIL_SHA = "fe98f7d9d481578804a3ca3e19ca96ad4b4fa6e046f46e25d4ab21d9e15f0bb7"
BASE_URL = os.environ.get("WATHEFNI_DOCS_QUAL_BASE", "http://127.0.0.1:8010")
REQUEST_TIMEOUT_S = float(os.environ.get("WATHEFNI_DOCS_QUAL_REQ_TIMEOUT", "120"))
TYPE_TIMEOUT_S = int(os.environ.get("WATHEFNI_DOCS_QUAL_TYPE_TIMEOUT", "420"))
MAX_RETRIES = int(os.environ.get("WATHEFNI_DOCS_QUAL_RETRIES", "1"))
PARTIAL_DIR = Path(os.environ.get("WATHEFNI_DOCS_QUAL_PARTIAL_DIR", "/tmp/kuwait-docs-qual-partial"))

FIXTURE_DIRS = [
    Path("/tmp/kuwait-docs-qual-fixtures"),
    Path("/opt/wathefni/orchestrator/fixtures/kuwait-docs-qual"),
]

IDENTITY_FIELD_SCHEMA = [
    "document_type",
    "side",
    "document_relationship",
    "full_name",
    "full_name_ar",
    "full_name_en",
    "document_number",
    "nationality",
    "date_of_birth",
    "issue_date",
    "issued_date",
    "expiry_date",
    "employer_or_sponsor",
    "confidence",
    "extraction_status",
]

TYPES: list[dict[str, Any]] = [
    {
        "item_id": "civil_id_dual_side_canary",
        "validation_item": "civil_id",
        "label": "CANARY ONLY — Civil ID dual-side qual",
        "dual_side": True,
        "front_fixture": "kuwait_paci_civil_id_front_v1.png",
        "back_fixture": "kuwait_paci_civil_id_back_v1.png",
        "wrong_fixture": "wrong_non_document_v1.png",
        "identity_applicable": True,
        "expiry_applicable": True,
        "category": "identity_legal",
    },
    {
        "item_id": "docs_qual_passport",
        "validation_item": "passport",
        "label": "CANARY ONLY — Passport qual",
        "dual_side": False,
        "fixture": "passport_aziz_v1.png",
        "wrong_fixture": "wrong_non_document_v1.png",
        "cross_wrong_fixture": "kuwait_paci_civil_id_front_v1.png",
        "identity_applicable": True,
        "expiry_applicable": True,
        "category": "identity_legal",
    },
    {
        "item_id": "docs_qual_residence",
        "validation_item": "residence",
        "label": "CANARY ONLY — Residence qual",
        "dual_side": False,
        "fixture": "residence_aziz_v1.png",
        "wrong_fixture": "wrong_non_document_v1.png",
        "cross_wrong_fixture": "personal_photo_aziz_v1.png",
        "identity_applicable": False,
        "expiry_applicable": True,
        "category": "identity_legal",
    },
    {
        "item_id": "docs_qual_work_permit",
        "validation_item": "work_permit",
        "label": "CANARY ONLY — Work permit qual",
        "dual_side": False,
        "fixture": "work_permit_aziz_v1.png",
        "wrong_fixture": "wrong_non_document_v1.png",
        "cross_wrong_fixture": "personal_photo_aziz_v1.png",
        "identity_applicable": False,
        "expiry_applicable": True,
        "category": "identity_legal",
    },
    {
        "item_id": "docs_qual_employment_contract",
        "validation_item": "employment_contract",
        "label": "CANARY ONLY — Employment contract qual",
        "dual_side": False,
        "fixture": "employment_contract_aziz_v1.png",
        "wrong_fixture": "wrong_non_document_v1.png",
        "cross_wrong_fixture": "personal_photo_aziz_v1.png",
        "identity_applicable": False,
        "expiry_applicable": False,
        "category": "employment",
    },
    {
        "item_id": "docs_qual_personal_photo",
        "validation_item": "personal_photo",
        "label": "CANARY ONLY — Personal photo qual",
        "dual_side": False,
        "fixture": "personal_photo_aziz_v1.png",
        "wrong_fixture": "kuwait_paci_civil_id_front_v1.png",
        "identity_applicable": False,
        "expiry_applicable": False,
        "category": "identity_legal",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(msg: str) -> None:
    print(f"[{_now()}] {msg}", flush=True)


def fixtures_dir() -> Path:
    for d in FIXTURE_DIRS:
        if d.is_dir() and (d / "passport_aziz_v1.png").is_file():
            return d
    raise SystemExit("fixtures missing")


def assert_civil(cur) -> dict[str, Any]:
    cur.execute(
        "SELECT status, content_sha256, value FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
        (EMP, "civil_id"),
    )
    row = dict(cur.fetchone() or {})
    if row.get("status") != "accepted" or row.get("content_sha256") != EXPECTED_CIVIL_SHA:
        raise SystemExit(f"ABORT civil_id changed: {row}")
    return row


def wipe_canary_history(cur, item: str) -> None:
    cur.execute(
        """
        DELETE FROM governed_document_version_parts
        WHERE version_id IN (
          SELECT version_id FROM governed_document_versions
          WHERE company_code=%s AND employee_key=%s AND document_type=%s
        )
        """,
        (COMPANY, EMP, item),
    )
    cur.execute(
        "DELETE FROM governed_document_events WHERE company_code=%s AND employee_key=%s AND document_type=%s",
        (COMPANY, EMP, item),
    )
    cur.execute(
        "DELETE FROM governed_document_versions WHERE company_code=%s AND employee_key=%s AND document_type=%s",
        (COMPANY, EMP, item),
    )
    try:
        cur.execute(
            "DELETE FROM compliance_documents WHERE company_code=%s AND employee_key=%s AND document_type=%s",
            (COMPANY, EMP, item),
        )
    except Exception:
        pass


def ensure_canary(cur, spec: dict[str, Any]) -> None:
    item = spec["item_id"]
    meta = {
        "explicitly_assigned": True,
        "canary": True,
        "disposable": True,
        "purpose": "kuwait_docs_qual_matrix_http",
        "do_not_approve_as_real": True,
        "validation_alias": spec["validation_item"],
        "created_at": _now(),
    }
    cur.execute("SELECT 1 FROM onboarding_items WHERE employee_key=%s AND item_id=%s", (EMP, item))
    if cur.fetchone():
        cur.execute(
            """
            UPDATE onboarding_items
            SET status='pending', rejection_reason=NULL, completed_at=NULL,
                value=NULL, local_path=NULL, content_sha256=NULL, mime_type=NULL,
                storage_status=NULL, storage_object_key=NULL, external_file_id=NULL,
                storage_url=NULL, drive_file_id=NULL, drive_url=NULL,
                lifecycle_meta = coalesce(lifecycle_meta,'{}'::jsonb) || %s::jsonb,
                updated_at=now(), row_version=row_version+1
            WHERE employee_key=%s AND item_id=%s
            """,
            (json.dumps(meta), EMP, item),
        )
    else:
        cur.execute(
            """
            INSERT INTO onboarding_items (
              employee_key, item_id, label, category, item_type, required, owner,
              sort_order, document_type, status, depends_on,
              collection_mode, authority, template_version, row_version,
              reminder_count, lifecycle_meta, raw_json, created_at, updated_at
            ) VALUES (
              %s,%s,%s,%s,'document',false,'employee',
              9900,%s,'pending','[]'::jsonb,
              'document','onboarding','2.0.0-canary',1,
              0,%s::jsonb,%s::jsonb,now(),now()
            )
            """,
            (
                EMP,
                item,
                spec["label"],
                spec.get("category") or "identity_legal",
                item,
                json.dumps(meta),
                json.dumps({"canary": True, "source": "kuwait_docs_qual_http"}),
            ),
        )
    wipe_canary_history(cur, item)


def cleanup_canary(cur, item: str) -> None:
    wipe_canary_history(cur, item)
    cur.execute("DELETE FROM onboarding_items WHERE employee_key=%s AND item_id=%s", (EMP, item))


def verdict(proven: list[str], partial: list[str], missing: list[str]) -> str:
    if missing:
        return "missing/broken" if not proven else "partially proven"
    if partial:
        return "partially proven"
    return "fully proven"


def extract_schema(ocr: dict[str, Any] | None) -> dict[str, Any]:
    ocr = ocr or {}
    fields = ocr.get("fields") if isinstance(ocr.get("fields"), dict) else {}
    out: dict[str, Any] = {}
    for key in IDENTITY_FIELD_SCHEMA:
        if key in ocr and ocr.get(key) is not None:
            out[key] = ocr.get(key)
        elif key in fields:
            cell = fields[key]
            if isinstance(cell, dict):
                out[key] = {"value": cell.get("value"), "confidence": cell.get("confidence")}
            else:
                out[key] = cell
    out["_top_level_keys"] = sorted(ocr.keys())
    out["_field_keys"] = sorted(fields.keys()) if fields else []
    return out


def http_upload(
    *,
    token: str,
    path: Path,
    item_id: str,
    part: str | None = None,
) -> tuple[int, dict[str, Any], str]:
    import urllib.error
    import urllib.request

    boundary = f"----WathefniQual{os.getpid()}{int(datetime.now().timestamp())}"
    body = bytearray()

    def add_field(name: str, value: str) -> None:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode())
        body.extend(b"\r\n")

    add_field("item_id", item_id)
    if part:
        add_field("part", part)
    data = path.read_bytes()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode()
    )
    body.extend(b"Content-Type: image/png\r\n\r\n")
    body.extend(data)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"{BASE_URL}/app/onboarding/documents",
        data=bytes(body),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"raw": raw[:2000]}
            return int(resp.status), parsed, "ok"
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw[:2000]}
        return int(exc.code), parsed, "http_error"
    except TimeoutError:
        return 0, {"error": "timeout", "timeout_s": REQUEST_TIMEOUT_S}, "timeout"
    except Exception as exc:
        return 0, {"error": type(exc).__name__, "message": str(exc)[:500]}, "exception"


def http_upload_retry(*, token: str, path: Path, item_id: str, part: str | None = None) -> tuple[int, dict[str, Any], str]:
    last = (0, {"error": "no_attempt"}, "none")
    for attempt in range(1, MAX_RETRIES + 2):
        log(f"  HTTP upload item={item_id} part={part} file={path.name} attempt={attempt}")
        code, body, kind = http_upload(token=token, path=path, item_id=item_id, part=part)
        last = (code, body, kind)
        log(f"  → http={code} kind={kind}")
        if kind == "timeout":
            if attempt <= MAX_RETRIES:
                continue
            return last
        # retry only transient 5xx
        if code >= 500 and attempt <= MAX_RETRIES:
            continue
        return last
    return last


def run_one_type(item_id: str, token: str, other_token: str) -> dict[str, Any]:
    spec = next(s for s in TYPES if s["item_id"] == item_id)
    fx = fixtures_dir()
    row: dict[str, Any] = {
        "item_id": item_id,
        "validation_item": spec["validation_item"],
        "started_at": _now(),
        "checks": {},
        "proven": [],
        "partial": [],
        "missing": [],
        "extracted_schema": None,
        "errors": [],
        "failing_request": None,
    }

    import app
    import kuwait_pilot_document_journey as journey

    def save_partial() -> None:
        PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
        path = PARTIAL_DIR / f"{item_id}.json"
        path.write_text(json.dumps(row, indent=2, default=str))

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                ensure_canary(cur, spec)
                link_civil = assert_civil(cur)
                cur.execute(
                    """
                    SELECT employee_key, item_id, document_type, status, required, owner, collection_mode
                    FROM onboarding_items WHERE employee_key=%s AND item_id=%s
                    """,
                    (EMP, item_id),
                )
                link = dict(cur.fetchone() or {})
            conn.commit()
        row["checks"]["civil_untouched"] = link_civil
        row["checks"]["linkage"] = link
        if link.get("employee_key") == EMP and link.get("document_type") == item_id and link.get("required") is False:
            row["proven"].append("linkage")
        else:
            row["missing"].append("linkage")
        save_partial()

        # wrong document
        code_w, body_w, kind_w = http_upload_retry(
            token=token,
            path=fx / spec["wrong_fixture"],
            item_id=item_id,
            part="front" if spec.get("dual_side") else None,
        )
        row["checks"]["wrong_document"] = {"http": code_w, "kind": kind_w, "body": body_w}
        if kind_w == "timeout":
            row["missing"].append("wrong_document_rejection")
            row["failing_request"] = {
                "step": "wrong_document",
                "timeout_s": REQUEST_TIMEOUT_S,
                "item_id": item_id,
                "file": spec["wrong_fixture"],
            }
            row["errors"].append("timeout_on_wrong_document")
        elif code_w == 422:
            row["proven"].append("wrong_document_rejection")
        else:
            row["missing"].append("wrong_document_rejection")
        save_partial()

        # cross-type
        if spec.get("cross_wrong_fixture"):
            code_x, body_x, kind_x = http_upload_retry(
                token=token,
                path=fx / spec["cross_wrong_fixture"],
                item_id=item_id,
                part="front" if spec.get("dual_side") else None,
            )
            row["checks"]["cross_type_rejection"] = {"http": code_x, "kind": kind_x, "body": body_x}
            if kind_x == "timeout":
                row["partial"].append("cross_type_rejection")
                row["failing_request"] = row["failing_request"] or {
                    "step": "cross_type",
                    "timeout_s": REQUEST_TIMEOUT_S,
                    "item_id": item_id,
                    "file": spec["cross_wrong_fixture"],
                }
            elif code_x == 422:
                row["proven"].append("cross_type_rejection")
            else:
                row["partial"].append("cross_type_rejection")
            save_partial()

        # correct upload
        last_body: dict[str, Any] = {}
        upload_ok = False
        if spec.get("dual_side"):
            code_f, body_f, kind_f = http_upload_retry(
                token=token, path=fx / spec["front_fixture"], item_id=item_id, part="front"
            )
            row["checks"]["upload_front"] = {"http": code_f, "kind": kind_f, "body": body_f}
            if kind_f == "timeout":
                row["failing_request"] = {
                    "step": "upload_front",
                    "timeout_s": REQUEST_TIMEOUT_S,
                    "item_id": item_id,
                    "file": spec["front_fixture"],
                }
                row["missing"].append("supported_upload")
                save_partial()
                row["verdict"] = verdict(row["proven"], row["partial"], row["missing"])
                row["finished_at"] = _now()
                return row
            code_b, body_b, kind_b = http_upload_retry(
                token=token, path=fx / spec["back_fixture"], item_id=item_id, part="back"
            )
            row["checks"]["upload_back"] = {"http": code_b, "kind": kind_b, "body": body_b}
            last_body = body_b
            if kind_b == "timeout":
                row["failing_request"] = {
                    "step": "upload_back",
                    "timeout_s": REQUEST_TIMEOUT_S,
                    "item_id": item_id,
                    "file": spec["back_fixture"],
                }
                row["missing"].append("supported_upload")
            else:
                upload_ok = code_f == 200 and code_b == 200 and bool(body_b.get("parts_complete"))
        else:
            code_u, body_u, kind_u = http_upload_retry(
                token=token, path=fx / spec["fixture"], item_id=item_id
            )
            row["checks"]["upload"] = {"http": code_u, "kind": kind_u, "body": body_u}
            last_body = body_u
            if kind_u == "timeout":
                row["failing_request"] = {
                    "step": "upload",
                    "timeout_s": REQUEST_TIMEOUT_S,
                    "item_id": item_id,
                    "file": spec["fixture"],
                }
                row["missing"].append("supported_upload")
            else:
                upload_ok = code_u == 200
        if upload_ok:
            row["proven"].append("supported_upload")
            row["proven"].append("classification_allow")
        elif "supported_upload" not in row["missing"]:
            row["missing"].append("supported_upload")
        save_partial()

        # stored OCR / version
        ver: dict[str, Any] = {}
        ocr: dict[str, Any] = {}
        parts_ocr: dict[str, Any] = {}
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT version_id, review_status, parts_complete, parts_schema,
                           document_number, expiry_date, issue_date, ocr_proposal, file_id, file_sha256
                    FROM governed_document_versions
                    WHERE company_code=%s AND employee_key=%s AND document_type=%s
                    ORDER BY version_no DESC LIMIT 1
                    """,
                    (COMPANY, EMP, item_id),
                )
                ver = dict(cur.fetchone() or {})
                ocr = ver.get("ocr_proposal") if isinstance(ver.get("ocr_proposal"), dict) else {}
                if ver.get("version_id") and spec.get("dual_side"):
                    cur.execute(
                        """
                        SELECT part_key, detected_side, hr_warning, ocr_proposal, file_sha256
                        FROM governed_document_version_parts WHERE version_id=%s
                        """,
                        (ver["version_id"],),
                    )
                    for p in cur.fetchall() or []:
                        pd = dict(p)
                        po = pd.get("ocr_proposal") if isinstance(pd.get("ocr_proposal"), dict) else {}
                        parts_ocr[str(pd.get("part_key"))] = {
                            "detected_side": pd.get("detected_side"),
                            "hr_warning": pd.get("hr_warning"),
                            "sha": pd.get("file_sha256"),
                            "schema": extract_schema(po),
                        }
                        if po and not ocr:
                            ocr = po
                assert_civil(cur)
            conn.commit()

        row["checks"]["version"] = {
            "version_id": ver.get("version_id"),
            "review_status": ver.get("review_status"),
            "parts_complete": ver.get("parts_complete"),
            "document_number": ver.get("document_number"),
            "expiry_date": str(ver.get("expiry_date") or "") or None,
            "issue_date": str(ver.get("issue_date") or "") or None,
            "file_id": ver.get("file_id"),
        }
        row["extracted_schema"] = extract_schema(ocr)
        if parts_ocr:
            row["parts_extracted_schema"] = parts_ocr
        if ver.get("version_id") and (ocr or parts_ocr):
            row["proven"].append("ocr_stored")
        elif upload_ok:
            row["partial"].append("ocr_stored")
        else:
            row["missing"].append("ocr_stored")

        # identity
        if spec.get("identity_applicable"):
            id_check = None
            if isinstance(ocr, dict):
                id_check = ocr.get("identity_check") or ocr.get("canary_identity_alias_applied")
            row["checks"]["identity"] = id_check
            if id_check or (isinstance(ocr, dict) and (ocr.get("full_name") or ocr.get("full_name_en"))):
                row["proven"].append("identity_matching")
            else:
                row["partial"].append("identity_matching")
        else:
            row["checks"]["identity"] = "not_applicable_for_item"
            row["proven"].append("identity_matching_na")

        # expiry
        if spec.get("expiry_applicable"):
            exp = ver.get("expiry_date")
            if not exp and isinstance(ocr, dict):
                exp = ocr.get("expiry_date")
                fields = ocr.get("fields") if isinstance(ocr.get("fields"), dict) else {}
                cell = fields.get("expiry_date") if isinstance(fields, dict) else None
                if isinstance(cell, dict) and not exp:
                    exp = cell.get("value")
            row["checks"]["expiry"] = str(exp or "") or None
            if exp:
                row["proven"].append("expiry_extraction")
            else:
                row["partial"].append("expiry_extraction")
        else:
            row["proven"].append("expiry_na")
        save_partial()

        # HR journey — match ONLY the disposable canary lane (never real passport/civil_id/etc).
        docs = journey.list_employee_compliance_journey(
            app, company_code=COMPANY, employee_key=EMP, locale="en"
        )
        match = [d for d in docs if str(d.get("document_type") or "") == item_id]
        hr_doc = match[0] if match else None
        row["checks"]["hr_journey_hit"] = bool(hr_doc)
        if hr_doc:
            ocr_prop = hr_doc.get("ocr_proposal") if isinstance(hr_doc.get("ocr_proposal"), dict) else {}
            row["checks"]["hr_projection"] = {
                "review_status": hr_doc.get("review_status"),
                "expiry_date": hr_doc.get("expiry_date"),
                "issue_date": hr_doc.get("issue_date"),
                "has_ocr_proposal": bool(ocr_prop),
                "ocr_keys": sorted(ocr_prop.keys())[:40],
                "versions_count": len(hr_doc.get("versions") or []),
            }
            if hr_doc.get("versions"):
                row["proven"].append("version_history")
            else:
                row["partial"].append("version_history")
            row["proven"].append("hr_receives_submission")
            # Shared DocumentExtractionSummary surfaces OCR on Compliance + Onboarding HR paths.
            # Masked document numbers + extracted-vs-verified copy are part of that UI.
            ui_fields = [
                "expiry_date",
                "issue_date",
                "review_status",
                "rejection_reason",
                "versions",
                "extracted_name",
                "document_type",
                "nationality",
                "date_of_birth",
                "employer_or_sponsor",
                "confidence",
                "extraction_status",
                "identity_match",
                "hr_warnings",
                "document_number_masked",
                "civil_id_parts_front_back",
                "extracted_vs_verified",
            ]
            row["checks"]["hr_fields_shown_in_ui"] = ui_fields
            row["checks"]["hr_fields_in_api_not_ui"] = []
            row["checks"]["extraction_vs_verified"] = hr_doc.get("extraction_vs_verified")
            row["checks"]["verified_fields"] = hr_doc.get("verified_fields")
            if hr_doc.get("extraction_vs_verified") and ocr_prop:
                row["proven"].append("hr_ocr_summary_ui")
            else:
                row["partial"].append("hr_ocr_summary_ui")
            # Never claim raw OCR dump is shown.
            if "raw" in ocr_prop:
                row["missing"].append("hr_ocr_no_raw_dump")
            else:
                row["proven"].append("hr_ocr_no_raw_dump")
        else:
            row["missing"].append("hr_receives_submission")
            row["missing"].append("version_history")

        # preview
        file_id = ver.get("file_id") or last_body.get("file_id")
        if spec.get("dual_side"):
            file_id = (
                (last_body.get("parts") or {}).get("front", {}).get("file_id")
                or file_id
            )
        row["checks"]["preview_file_id"] = file_id
        if file_id:
            import urllib.request

            req = urllib.request.Request(
                f"{BASE_URL}/app/documents/{file_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    row["checks"]["preview_http"] = resp.status
                    if resp.status in {200, 302, 307}:
                        row["proven"].append("preview")
                    else:
                        row["partial"].append("preview")
            except Exception as exc:
                # HTTPError may still be a usable redirect/json
                code = getattr(exc, "code", None)
                row["checks"]["preview_http"] = code or str(exc)[:120]
                if code in {200, 302, 307, 401, 403}:
                    # 401/403 still proves endpoint exists; treat as partial if auth odd
                    row["partial"].append("preview")
                elif code:
                    row["partial"].append("preview")
                else:
                    row["partial"].append("preview")
        else:
            row["missing"].append("preview")
        save_partial()

        # HR approve / reject replacement via journey (same code path as dashboard).
        # IMPORTANT: do not nest db_connect around approve/reject — they open their own
        # connections and FOR UPDATE nesting deadlocks the pool.
        if ver.get("version_id") and upload_ok:
            try:
                journey.approve_version(
                    app,
                    company_code=COMPANY,
                    employee_key=EMP,
                    document_type=item_id,
                    version_id=str(ver["version_id"]),
                    actor_user_id="docs_qual_http_bot",
                    permissions={journey.DOCUMENT_REVIEW_MANAGE},
                    confirm_ocr=True,
                )
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
                            (EMP, item_id),
                        )
                        st_after = dict(cur.fetchone() or {}).get("status")
                        row["checks"]["employee_status_after_approve"] = st_after
                        cur.execute(
                            """
                            SELECT version_id FROM governed_document_versions
                            WHERE company_code=%s AND employee_key=%s AND document_type=%s
                            ORDER BY version_no DESC LIMIT 1
                            """,
                            (COMPANY, EMP, item_id),
                        )
                        vid2 = dict(cur.fetchone() or {}).get("version_id")
                        assert_civil(cur)
                    conn.commit()
                if str(st_after or "") in {"accepted", "completed"}:
                    row["proven"].append("hr_approve_roundtrip")
                else:
                    row["partial"].append("hr_approve_roundtrip")
                save_partial()

                if vid2:
                    journey.reject_version(
                        app,
                        company_code=COMPANY,
                        employee_key=EMP,
                        document_type=item_id,
                        version_id=str(vid2),
                        actor_user_id="docs_qual_http_bot",
                        permissions={journey.DOCUMENT_REVIEW_MANAGE},
                        reason="canary qualification reject for replacement test",
                        request_reupload=True,
                    )
                    with app.db_connect() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                "SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
                                (EMP, item_id),
                            )
                            st_rej = dict(cur.fetchone() or {}).get("status")
                            row["checks"]["employee_status_after_reject"] = st_rej
                            assert_civil(cur)
                        conn.commit()
                    if str(st_rej or "") in {"replacement_required", "rejected", "pending"}:
                        row["proven"].append("hr_reject_replacement")
                    else:
                        row["partial"].append("hr_reject_replacement")
            except Exception as exc:
                row["checks"]["hr_roundtrip_error"] = f"{type(exc).__name__}: {exc}"
                row["partial"].append("hr_approve_roundtrip")
                row["errors"].append(traceback.format_exc()[-800:])
        else:
            row["missing"].append("hr_approve_roundtrip")
        save_partial()

        # cross-employee permission
        code_p, body_p, kind_p = http_upload_retry(
            token=other_token,
            path=fx / (spec.get("fixture") or spec.get("front_fixture")),
            item_id=item_id,
            part="front" if spec.get("dual_side") else None,
        )
        row["checks"]["cross_employee_upload"] = {"http": code_p, "kind": kind_p, "body": body_p}
        if kind_p == "timeout":
            row["partial"].append("cross_employee_blocked")
        elif code_p >= 400:
            row["proven"].append("cross_employee_blocked")
        else:
            row["missing"].append("cross_employee_blocked")

    except Exception as exc:
        row["errors"].append(f"{type(exc).__name__}: {exc}")
        row["errors"].append(traceback.format_exc()[-1200:])
        row["missing"].append("exception")

    row["verdict"] = verdict(row["proven"], row["partial"], row["missing"])
    row["finished_at"] = _now()
    save_partial()
    return row


def cmd_run_type(argv: list[str]) -> int:
    item_id = argv[0]
    token = os.environ["WATHEFNI_DOCS_QUAL_TOKEN"]
    other_token = os.environ["WATHEFNI_DOCS_QUAL_OTHER_TOKEN"]
    os.environ.setdefault("WATHEFNI_EMPLOYEE_APP", "on")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST", "on")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST", f"{OTHER_EMP},{EMP}")
    os.environ.setdefault("WATHEFNI_CIVIL_ID_DUAL_SIDE", "on")
    os.environ.setdefault("WATHEFNI_CIVIL_ID_DUAL_SIDE_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_CIVIL_ID_DUAL_SIDE_EMPLOYEE_ALLOWLIST", EMP)
    os.environ.setdefault("WATHEFNI_ONBOARDING_LIFECYCLE_V2A", "on")
    os.environ.setdefault("WATHEFNI_ONBOARDING_LIFECYCLE_V2A_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_ONBOARDING_LIFECYCLE_V2A_EMPLOYEE_ALLOWLIST", f"{EMP},{OTHER_EMP}")
    os.environ.setdefault("WATHEFNI_ONBOARDING_DOC_VALIDATION_SOFT", "on")
    os.environ.setdefault("WATHEFNI_ONBOARDING_DOC_VALIDATION_HARD", "off")
    os.environ.setdefault("WATHEFNI_ONBOARDING_DOC_VALIDATION_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_ONBOARDING_DOC_VALIDATION_EMPLOYEE_ALLOWLIST", f"{EMP},{OTHER_EMP}")
    os.environ.setdefault("WATHEFNI_IDENTITY_MISTRAL_AUTHORITY", "on")
    row = run_one_type(item_id, token, other_token)
    print(json.dumps(row, indent=2, default=str))
    return 0 if row.get("verdict") != "missing/broken" else 2


def cmd_orchestrate() -> int:
    # Mirror production allowlists so session minting works outside systemd.
    os.environ.setdefault("WATHEFNI_EMPLOYEE_APP", "on")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST", "on")
    os.environ.setdefault(
        "WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST",
        f"{OTHER_EMP},{EMP}",
    )
    os.environ.setdefault("WATHEFNI_CIVIL_ID_DUAL_SIDE", "on")
    os.environ.setdefault("WATHEFNI_CIVIL_ID_DUAL_SIDE_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_CIVIL_ID_DUAL_SIDE_EMPLOYEE_ALLOWLIST", EMP)
    os.environ.setdefault("WATHEFNI_ONBOARDING_LIFECYCLE_V2A", "on")
    os.environ.setdefault("WATHEFNI_ONBOARDING_LIFECYCLE_V2A_COMPANIES", "WATHEFNI")
    os.environ.setdefault(
        "WATHEFNI_ONBOARDING_LIFECYCLE_V2A_EMPLOYEE_ALLOWLIST",
        f"{EMP},{OTHER_EMP}",
    )
    os.environ.setdefault("WATHEFNI_ONBOARDING_DOC_VALIDATION_SOFT", "on")
    os.environ.setdefault("WATHEFNI_ONBOARDING_DOC_VALIDATION_HARD", "off")
    os.environ.setdefault("WATHEFNI_ONBOARDING_DOC_VALIDATION_COMPANIES", "WATHEFNI")
    os.environ.setdefault(
        "WATHEFNI_ONBOARDING_DOC_VALIDATION_EMPLOYEE_ALLOWLIST",
        f"{EMP},{OTHER_EMP}",
    )
    os.environ.setdefault("WATHEFNI_IDENTITY_MISTRAL_AUTHORITY", "on")

    import app

    PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "started_at": _now(),
        "mode": "live_http_uvicorn",
        "base_url": BASE_URL,
        "request_timeout_s": REQUEST_TIMEOUT_S,
        "type_timeout_s": TYPE_TIMEOUT_S,
        "max_retries": MAX_RETRIES,
        "template": "default_kuwait@2.0.0",
        "employee_key": EMP,
        "bank_ess": "out_of_scope_submission_not_live",
        "types": {},
        "matrix": {},
        "hr_fields_shown": [
            "expiry_date",
            "issue_date",
            "review_status",
            "rejection_reason",
            "versions",
            "extracted_name",
            "document_type",
            "nationality",
            "date_of_birth",
            "employer_or_sponsor",
            "confidence",
            "extraction_status",
            "identity_match",
            "hr_warnings",
            "document_number_masked",
            "civil_id_parts_front_back",
            "extracted_vs_verified",
        ],
        "hr_fields_api_but_ui_hidden": [
            "ocr_proposal.raw",
        ],
    }

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            report["civil_id_before"] = assert_civil(cur)
            for spec in TYPES:
                ensure_canary(cur, spec)
        conn.commit()

    emp = app.find_employee_by_key(EMP, company_code=COMPANY)
    other = app.find_employee_by_key(OTHER_EMP, company_code=COMPANY)
    sess = app.create_employee_session(COMPANY, EMP, emp.get("phone") if emp else None)
    other_sess = app.create_employee_session(COMPANY, OTHER_EMP, other.get("phone") if other else None)
    token = str(sess["token"])
    other_token = str(other_sess["token"])
    log(f"minted sessions aziz+talal base={BASE_URL}")

    script = str(Path(__file__).resolve())
    env = os.environ.copy()
    env["WATHEFNI_DOCS_QUAL_TOKEN"] = token
    env["WATHEFNI_DOCS_QUAL_OTHER_TOKEN"] = other_token
    env["WATHEFNI_ENV"] = "production"
    env["WATHEFNI_POSTGRES_ENV"] = "/root/.openclaw/secrets/postgres.env"
    env["WATHEFNI_EXPECTED_DATABASE_HOST"] = "127.0.0.1"
    env["WATHEFNI_EXPECTED_DATABASE_PORT"] = "5432"
    env["WATHEFNI_EXPECTED_DATABASE_NAME"] = "wathefni"
    env["WATHEFNI_DATABASE_ENVIRONMENT_MARKER"] = "wathefni-production-isolation-v1"
    env["WATHEFNI_IDENTITY_MISTRAL_AUTHORITY"] = "on"

    for spec in TYPES:
        item = spec["item_id"]
        log(f"==== START type={item} timeout={TYPE_TIMEOUT_S}s ====")
        out_path = PARTIAL_DIR / f"{item}.stdout.json"
        err_path = PARTIAL_DIR / f"{item}.stderr.txt"
        try:
            with out_path.open("w") as out_fh, err_path.open("w") as err_fh:
                proc = subprocess.run(
                    [sys.executable, script, "run-type", item],
                    env=env,
                    stdout=out_fh,
                    stderr=err_fh,
                    timeout=TYPE_TIMEOUT_S,
                    cwd=str(Path(__file__).resolve().parent),
                )
            exit_code = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            exit_code = 124
            timed_out = True
            log(f"==== TIMEOUT type={item} after {TYPE_TIMEOUT_S}s ====")

        partial_path = PARTIAL_DIR / f"{item}.json"
        row: dict[str, Any]
        if partial_path.is_file():
            try:
                row = json.loads(partial_path.read_text())
            except Exception:
                row = {"item_id": item, "verdict": "missing/broken", "errors": ["partial_json_unreadable"]}
        else:
            row = {
                "item_id": item,
                "verdict": "missing/broken",
                "proven": [],
                "partial": [],
                "missing": ["no_partial_result"],
                "errors": ["subprocess produced no partial file"],
            }
        if timed_out:
            row["subprocess_timeout"] = True
            row["type_timeout_s"] = TYPE_TIMEOUT_S
            row.setdefault("failing_request", {"step": "type_subprocess", "timeout_s": TYPE_TIMEOUT_S, "item_id": item})
            row.setdefault("missing", []).append("type_subprocess_timeout")
            row["verdict"] = verdict(row.get("proven") or [], row.get("partial") or [], row.get("missing") or [])
            partial_path.write_text(json.dumps(row, indent=2, default=str))
        row["subprocess_exit"] = exit_code
        # Prefer stdout JSON if richer
        if out_path.is_file() and out_path.stat().st_size > 10:
            try:
                stdout_row = json.loads(out_path.read_text())
                if isinstance(stdout_row, dict) and stdout_row.get("item_id") == item:
                    row = stdout_row
                    row["subprocess_exit"] = exit_code
            except Exception:
                pass
        if err_path.is_file() and err_path.stat().st_size:
            row.setdefault("stderr_tail", err_path.read_text()[-1500:])

        report["types"][item] = row
        report["matrix"][item] = {
            "verdict": row.get("verdict"),
            "proven": row.get("proven"),
            "partial": row.get("partial"),
            "missing": row.get("missing"),
            "failing_request": row.get("failing_request"),
        }
        log(f"==== DONE type={item} verdict={row.get('verdict')} ====")
        (PARTIAL_DIR / "report.partial.json").write_text(json.dumps(report, indent=2, default=str))

    # cleanup canaries + assert civil
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for spec in TYPES:
                cleanup_canary(cur, spec["item_id"])
            report["civil_id_after"] = assert_civil(cur)
            cur.execute(
                """
                SELECT count(*) n FROM onboarding_items
                WHERE employee_key=%s AND (item_id LIKE 'docs_qual_%%' OR item_id=%s)
                """,
                (EMP, "civil_id_dual_side_canary"),
            )
            report["canary_items_remaining"] = int(dict(cur.fetchone() or {}).get("n") or 0)
        conn.commit()

    report["finished_at"] = _now()
    report["ok"] = all(
        (report["matrix"].get(s["item_id"]) or {}).get("verdict") != "missing/broken" for s in TYPES
    ) and report["civil_id_after"].get("content_sha256") == EXPECTED_CIVIL_SHA

    out = PARTIAL_DIR / "report.final.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    log(f"wrote {out}")
    return 0 if report.get("ok") else 1


def cmd_rerun_types(items: list[str]) -> int:
    """Re-run selected types and merge into report.final.json."""
    os.environ.setdefault("WATHEFNI_EMPLOYEE_APP", "on")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST", "on")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST", f"{OTHER_EMP},{EMP}")
    os.environ.setdefault("WATHEFNI_CIVIL_ID_DUAL_SIDE", "on")
    os.environ.setdefault("WATHEFNI_CIVIL_ID_DUAL_SIDE_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_CIVIL_ID_DUAL_SIDE_EMPLOYEE_ALLOWLIST", EMP)
    os.environ.setdefault("WATHEFNI_ONBOARDING_LIFECYCLE_V2A", "on")
    os.environ.setdefault("WATHEFNI_ONBOARDING_LIFECYCLE_V2A_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_ONBOARDING_LIFECYCLE_V2A_EMPLOYEE_ALLOWLIST", f"{EMP},{OTHER_EMP}")
    os.environ.setdefault("WATHEFNI_ONBOARDING_DOC_VALIDATION_SOFT", "on")
    os.environ.setdefault("WATHEFNI_ONBOARDING_DOC_VALIDATION_HARD", "off")
    os.environ.setdefault("WATHEFNI_ONBOARDING_DOC_VALIDATION_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_ONBOARDING_DOC_VALIDATION_EMPLOYEE_ALLOWLIST", f"{EMP},{OTHER_EMP}")
    os.environ.setdefault("WATHEFNI_IDENTITY_MISTRAL_AUTHORITY", "on")

    import app

    PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
    final_path = PARTIAL_DIR / "report.final.json"
    report = json.loads(final_path.read_text()) if final_path.is_file() else {
        "started_at": _now(),
        "types": {},
        "matrix": {},
    }

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            report["civil_id_before_rerun"] = assert_civil(cur)
            for item in items:
                spec = next(s for s in TYPES if s["item_id"] == item)
                ensure_canary(cur, spec)
            conn.commit()

    emp = app.find_employee_by_key(EMP, company_code=COMPANY)
    other = app.find_employee_by_key(OTHER_EMP, company_code=COMPANY)
    sess = app.create_employee_session(COMPANY, EMP, emp.get("phone") if emp else None)
    other_sess = app.create_employee_session(COMPANY, OTHER_EMP, other.get("phone") if other else None)
    token = str(sess["token"])
    other_token = str(other_sess["token"])

    script = str(Path(__file__).resolve())
    env = os.environ.copy()
    env["WATHEFNI_DOCS_QUAL_TOKEN"] = token
    env["WATHEFNI_DOCS_QUAL_OTHER_TOKEN"] = other_token
    env["WATHEFNI_ENV"] = "production"
    env["WATHEFNI_POSTGRES_ENV"] = "/root/.openclaw/secrets/postgres.env"
    env["WATHEFNI_EXPECTED_DATABASE_HOST"] = "127.0.0.1"
    env["WATHEFNI_EXPECTED_DATABASE_PORT"] = "5432"
    env["WATHEFNI_EXPECTED_DATABASE_NAME"] = "wathefni"
    env["WATHEFNI_DATABASE_ENVIRONMENT_MARKER"] = "wathefni-production-isolation-v1"
    env["WATHEFNI_IDENTITY_MISTRAL_AUTHORITY"] = "on"
    env["WATHEFNI_EMPLOYEE_APP"] = "on"
    env["WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST"] = "on"
    env["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = f"{OTHER_EMP},{EMP}"

    for item in items:
        log(f"==== RERUN type={item} ====")
        out_path = PARTIAL_DIR / f"{item}.stdout.json"
        err_path = PARTIAL_DIR / f"{item}.stderr.txt"
        try:
            with out_path.open("w") as out_fh, err_path.open("w") as err_fh:
                proc = subprocess.run(
                    [sys.executable, script, "run-type", item],
                    env=env,
                    stdout=out_fh,
                    stderr=err_fh,
                    timeout=TYPE_TIMEOUT_S,
                    cwd=str(Path(__file__).resolve().parent),
                )
            exit_code = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            exit_code = 124
            timed_out = True
        partial_path = PARTIAL_DIR / f"{item}.json"
        row = json.loads(partial_path.read_text()) if partial_path.is_file() else {
            "item_id": item, "verdict": "missing/broken", "missing": ["no_partial"], "proven": [], "partial": []
        }
        if timed_out:
            row["subprocess_timeout"] = True
            row.setdefault("missing", []).append("type_subprocess_timeout")
            row["verdict"] = verdict(row.get("proven") or [], row.get("partial") or [], row.get("missing") or [])
        if out_path.is_file() and out_path.stat().st_size > 10:
            try:
                stdout_row = json.loads(out_path.read_text())
                if isinstance(stdout_row, dict) and stdout_row.get("item_id") == item:
                    row = stdout_row
            except Exception:
                pass
        row["subprocess_exit"] = exit_code
        report.setdefault("types", {})[item] = row
        report.setdefault("matrix", {})[item] = {
            "verdict": row.get("verdict"),
            "proven": row.get("proven"),
            "partial": row.get("partial"),
            "missing": row.get("missing"),
            "failing_request": row.get("failing_request"),
        }
        log(f"==== RERUN DONE {item} verdict={row.get('verdict')} ====")

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for item in items:
                cleanup_canary(cur, item)
            # also ensure other canaries gone
            for spec in TYPES:
                cleanup_canary(cur, spec["item_id"])
            report["civil_id_after"] = assert_civil(cur)
            cur.execute(
                """
                SELECT count(*) n FROM onboarding_items
                WHERE employee_key=%s AND (item_id LIKE 'docs_qual_%%' OR item_id=%s)
                """,
                (EMP, "civil_id_dual_side_canary"),
            )
            report["canary_items_remaining"] = int(dict(cur.fetchone() or {}).get("n") or 0)
        conn.commit()

    report["rerun_at"] = _now()
    report["finished_at"] = _now()
    report["ok"] = all(
        (report.get("matrix") or {}).get(s["item_id"], {}).get("verdict") != "missing/broken"
        for s in TYPES
    ) and report["civil_id_after"].get("content_sha256") == EXPECTED_CIVIL_SHA
    final_path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"matrix": report.get("matrix"), "ok": report.get("ok"), "civil": report.get("civil_id_after")}, indent=2, default=str))
    return 0 if report.get("ok") else 1


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "run-type":
        return cmd_run_type(sys.argv[2:])
    if len(sys.argv) >= 3 and sys.argv[1] == "rerun-types":
        return cmd_rerun_types(sys.argv[2:])
    return cmd_orchestrate()


if __name__ == "__main__":
    raise SystemExit(main())
