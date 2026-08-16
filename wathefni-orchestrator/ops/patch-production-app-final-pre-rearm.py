#!/usr/bin/env python3
"""Apply only the pre-hire CV timer authority gate to production app.py."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


EXPECTED_BASE_SHA256 = (
    "be3811e2e4353deb64ec4bac6db40f97a8b668d8b2bdda99eac15a55dcf8bc32"
)

OLD_SELECT = """                SELECT cd.*, cd.raw_json AS document_raw_json, cd.metadata AS document_metadata,
                       a.*, c.name AS candidate_name, c.email AS candidate_email,
                       c.profile AS candidate_profile, c.raw_json AS candidate_raw_json
                FROM candidate_documents cd
                JOIN applications a ON a.app_key=cd.app_key
                LEFT JOIN candidates c ON c.phone=a.phone
                WHERE cd.document_id=%s
"""

NEW_SELECT = """                SELECT cd.*, cd.raw_json AS document_raw_json, cd.metadata AS document_metadata,
                       a.*, c.name AS candidate_name, c.email AS candidate_email,
                       c.profile AS candidate_profile, c.raw_json AS candidate_raw_json,
                       intake_authority.document_id::text AS authority_intake_document_id,
                       intake_authority.content_sha256 AS authority_content_sha256,
                       import_authority.source AS authority_import_source
                FROM candidate_documents cd
                JOIN applications a ON a.app_key=cd.app_key
                LEFT JOIN candidates c ON c.phone=a.phone
                LEFT JOIN LATERAL (
                  SELECT d.document_id, d.content_sha256
                  FROM intake_documents d
                  WHERE d.company_code=a.company_code
                    AND d.candidate_document_id=cd.document_id
                  ORDER BY d.created_at DESC
                  LIMIT 1
                ) intake_authority ON true
                LEFT JOIN LATERAL (
                  SELECT b.source
                  FROM import_items i
                  JOIN import_batches b ON b.batch_id=i.batch_id
                  WHERE i.document_id=cd.document_id
                  ORDER BY i.created_at DESC
                  LIMIT 1
                ) import_authority ON true
                WHERE cd.document_id=%s
"""

OLD_GATE = """            governed_intake_document_id = str(
                document_metadata.get("intake_document_id")
                or document_cv.get("intake_document_id")
                or ""
            )
            if document_metadata.get("identity_resolution_id"):
                content_sha = str(
                    ((document_cv.get("storage") or {}).get("sha256"))
                    if isinstance(document_cv.get("storage"), dict)
                    else ""
                )
                if not _inbound_cv_authority.binding_is_authorized(
                    cur,
                    company_code=company_code,
                    intake_document_id=governed_intake_document_id,
                    content_sha256=content_sha,
                    candidate_phone=str(app.get("phone") or "") or None,
                    app_key=str(app.get("app_key") or "") or None,
                ):
                    return {
                        "ok": False,
                        "error": "document_current_authority_not_proven",
                        "document_id": document_id,
                    }
"""

NEW_GATE = """            governed_intake_document_id = str(
                item.get("authority_intake_document_id")
                or document_metadata.get("intake_document_id")
                or document_cv.get("intake_document_id")
                or ""
            )
            identity_resolution_id = str(
                document_metadata.get("identity_resolution_id")
                or document_cv.get("identity_resolution_id")
                or ""
            )
            is_governed_inbound = bool(
                item.get("authority_intake_document_id")
                or governed_intake_document_id
                or identity_resolution_id
                or str(item.get("authority_import_source") or "").lower()
                in {"email", "email_inbound"}
            )
            if is_governed_inbound:
                if not governed_intake_document_id or not identity_resolution_id:
                    return {
                        "ok": False,
                        "error": "inbound_email_authority_provenance_missing",
                        "document_id": document_id,
                    }
                document_storage = (
                    document_cv.get("storage")
                    if isinstance(document_cv.get("storage"), dict)
                    else {}
                )
                content_sha = str(
                    item.get("authority_content_sha256")
                    or document_storage.get("sha256")
                    or ""
                )
                if not _inbound_cv_authority.binding_is_authorized(
                    cur,
                    company_code=company_code,
                    intake_document_id=governed_intake_document_id,
                    content_sha256=content_sha,
                    candidate_phone=str(app.get("phone") or "") or None,
                    app_key=str(app.get("app_key") or "") or None,
                ):
                    return {
                        "ok": False,
                        "error": "document_current_authority_not_proven",
                        "document_id": document_id,
                    }
"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-base", default=EXPECTED_BASE_SHA256)
    args = parser.parse_args()
    raw = args.source.read_bytes()
    if digest(raw) != args.expected_base:
        raise SystemExit(
            f"base_sha_mismatch expected={args.expected_base} actual={digest(raw)}"
        )
    text = raw.decode("utf-8")
    for old, new, label in (
        (OLD_SELECT, NEW_SELECT, "authority_select"),
        (OLD_GATE, NEW_GATE, "authority_gate"),
    ):
        if text.count(old) != 1:
            raise SystemExit(f"{label}_anchor_count={text.count(old)}")
        text = text.replace(old, new, 1)
    if "inbound_email_authority_provenance_missing" not in text:
        raise SystemExit("timer_gate_marker_missing")
    args.output.write_text(text, encoding="utf-8")
    print(f"base_sha256={digest(raw)}")
    print(f"patched_sha256={digest(args.output.read_bytes())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
