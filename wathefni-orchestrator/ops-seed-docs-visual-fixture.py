#!/usr/bin/env python3
"""Seed disposable Documents fixtures for Employee App visual QA.

Target: WATHEFNI-96550010001 (Noura) — already on the employee-app allowlist.
Aziz/Talal are never touched.

Seeds compliance_documents + governed_document_versions + tiny local files in
file_registry. Rows tagged for cleanup (notes / metadata / confirmed_metadata).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _pds  # noqa: E402

_pds.activate_fixture_tooling_from_argv()
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP", "on")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "0")

import app as legacy  # noqa: E402
import kuwait_pilot_document_journey as journey  # noqa: E402
from psycopg2.extras import Json  # noqa: E402

COMPANY = os.environ["WATHEFNI_COMPANY_CODE"]
KEY = f"{COMPANY}-96550010001"
PROTECTED = {"WATHEFNI-96599338566", "WATHEFNI-96550252254"}
TAG = "docs-visual-fixture"
STAMP = os.environ.get("DOCS_VISUAL_STAMP") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

# Minimal valid-enough PDF bytes for View/download smoke.
MINI_PDF = b"%PDF-1.1\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _guard() -> None:
    if KEY in PROTECTED:
        raise SystemExit(f"refusing protected canary key {KEY}")


def _fixture_dir() -> Path:
    root = Path(os.environ.get("WATHEFNI_WORKSPACE") or "/root/.openclaw/workspaces/company-wathefni")
    path = root / "fixtures" / TAG / STAMP
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup() -> dict[str, Any]:
    _guard()
    deleted = {"versions": 0, "compliance": 0, "files": 0, "events": 0}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            journey.ensure_document_journey_schema(cur)
            cur.execute(
                """
                DELETE FROM governed_document_events
                WHERE company_code=%s AND employee_key=%s
                  AND (
                    COALESCE(reason,'') = %s
                    OR COALESCE(new_state->>'fixture','') = %s
                  )
                """,
                (COMPANY, KEY, TAG, TAG),
            )
            deleted["events"] = cur.rowcount
            cur.execute(
                """
                DELETE FROM governed_document_versions
                WHERE company_code=%s AND employee_key=%s
                  AND COALESCE(confirmed_metadata->>'fixture','') = %s
                """,
                (COMPANY, KEY, TAG),
            )
            deleted["versions"] = cur.rowcount
            cur.execute(
                """
                DELETE FROM compliance_documents
                WHERE company_code=%s AND employee_key=%s
                  AND (
                    COALESCE(notes,'') = %s
                    OR document_type IN (
                      SELECT DISTINCT document_type FROM governed_document_versions
                      WHERE company_code=%s AND employee_key=%s
                        AND COALESCE(confirmed_metadata->>'fixture','') = %s
                    )
                  )
                """,
                (COMPANY, KEY, TAG, COMPANY, KEY, TAG),
            )
            deleted["compliance"] = cur.rowcount
            cur.execute(
                """
                DELETE FROM file_registry
                WHERE company_code=%s AND subject_type='employee' AND subject_key=%s
                  AND COALESCE(metadata->>'fixture','') = %s
                """,
                (COMPANY, KEY, TAG),
            )
            deleted["files"] = cur.rowcount
        conn.commit()
    return {"employee_key": KEY, "deleted": deleted, "stamp": STAMP}


def _write_pdf(name: str) -> tuple[Path, str, int]:
    path = _fixture_dir() / name
    # Unique content so file_registry checksums differ per version.
    body = MINI_PDF + f"\n% {TAG}:{STAMP}:{name}\n".encode()
    path.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    return path, digest, len(body)


def _insert_file(cur: Any, *, phone: str, document_type: str, filename: str) -> str:
    path, digest, size = _write_pdf(filename)
    file_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO file_registry (
          file_id, company_code, owner_phone, subject_type, subject_key, file_kind,
          document_type, original_filename, source_path, local_path,
          storage_provider, content_sha256, mime_type, size_bytes, storage_status,
          metadata, raw_json, stored_at, updated_at
        ) VALUES (
          %s,%s,%s,'employee',%s,'compliance_document',
          %s,%s,%s,%s,
          'local',%s,'application/pdf',%s,'stored',
          %s,%s,now(),now()
        )
        RETURNING file_id
        """,
        (
            file_id,
            COMPANY,
            phone,
            KEY,
            document_type,
            filename,
            str(path),
            str(path),
            digest,
            size,
            Json({"fixture": TAG, "stamp": STAMP, "label": journey.document_label(document_type)}),
            Json({"fixture": TAG, "stamp": STAMP}),
        ),
    )
    return str(cur.fetchone()["file_id"])


def _upsert_compliance(
    cur: Any,
    *,
    document_type: str,
    status: str,
    expiry: date | None,
    warning_days: int = 30,
) -> None:
    label = journey.document_label(document_type)
    # Do NOT put the fixture tag in `notes` — the journey surfaces notes as
    # rejection_reason, which would push every row into Needs attention.
    cur.execute(
        """
        INSERT INTO compliance_documents
          (company_code, employee_key, document_type, label, status, expiry_date, warning_days, notes, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,NULL, now())
        ON CONFLICT (employee_key, document_type) DO UPDATE SET
          company_code=EXCLUDED.company_code,
          label=EXCLUDED.label,
          status=EXCLUDED.status,
          expiry_date=EXCLUDED.expiry_date,
          warning_days=EXCLUDED.warning_days,
          notes=NULL,
          updated_at=now()
        """,
        (COMPANY, KEY, document_type, label, status, expiry, warning_days),
    )


def _insert_version(
    cur: Any,
    *,
    document_type: str,
    version_no: int,
    file_id: str | None,
    review_status: str,
    is_current: bool,
    expiry: date | None,
    issue: date | None = None,
    rejection_reason: str | None = None,
) -> str:
    version_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO governed_document_versions (
          version_id, company_code, employee_key, document_type, version_no,
          file_id, filename, mime_type, review_status, is_current,
          issue_date, expiry_date, rejection_reason,
          confirmed_metadata, upload_source, created_at, updated_at
        ) VALUES (
          %s,%s,%s,%s,%s,
          %s,%s,'application/pdf',%s,%s,
          %s,%s,%s,
          %s,'docs_visual_fixture',now(),now()
        )
        """,
        (
            version_id,
            COMPANY,
            KEY,
            document_type,
            version_no,
            file_id,
            f"{document_type}-v{version_no}.pdf",
            review_status,
            is_current,
            issue,
            expiry,
            rejection_reason,
            Json({"fixture": TAG, "stamp": STAMP}),
        ),
    )
    return version_id


def seed() -> dict[str, Any]:
    _guard()
    emp = legacy.find_employee_by_key(KEY, company_code=COMPANY) or {}
    if not emp:
        raise SystemExit(f"missing synthetic employee {KEY}")
    phone = legacy.digits(emp.get("phone"))
    cleanup()

    today = legacy.kuwait_today() if hasattr(legacy, "kuwait_today") else date.today()
    created_files: list[str] = []

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            journey.ensure_document_journey_schema(cur)

            # —— Needs attention ——
            # Civil ID expiring soon
            civil_old = _insert_file(cur, phone=phone, document_type="civil_id", filename="civil_id-old.pdf")
            civil_cur = _insert_file(cur, phone=phone, document_type="civil_id", filename="civil_id-current.pdf")
            created_files.extend([civil_old, civil_cur])
            _upsert_compliance(cur, document_type="civil_id", status="valid", expiry=today + timedelta(days=18))
            _insert_version(
                cur,
                document_type="civil_id",
                version_no=1,
                file_id=civil_old,
                review_status="superseded",
                is_current=False,
                expiry=today - timedelta(days=400),
                issue=today - timedelta(days=1200),
            )
            _insert_version(
                cur,
                document_type="civil_id",
                version_no=2,
                file_id=civil_cur,
                review_status="hr_reviewed",
                is_current=True,
                expiry=today + timedelta(days=18),
                issue=today - timedelta(days=340),
            )

            # Residence expired
            res_old = _insert_file(cur, phone=phone, document_type="residence", filename="residence-old.pdf")
            res_cur = _insert_file(cur, phone=phone, document_type="residence", filename="residence-current.pdf")
            created_files.extend([res_old, res_cur])
            _upsert_compliance(cur, document_type="residence", status="valid", expiry=today - timedelta(days=12))
            _insert_version(
                cur,
                document_type="residence",
                version_no=1,
                file_id=res_old,
                review_status="superseded",
                is_current=False,
                expiry=today - timedelta(days=400),
                issue=today - timedelta(days=900),
            )
            _insert_version(
                cur,
                document_type="residence",
                version_no=2,
                file_id=res_cur,
                review_status="hr_reviewed",
                is_current=True,
                expiry=today - timedelta(days=12),
                issue=today - timedelta(days=380),
            )

            # Work permit rejected — action needed
            wp_file = _insert_file(cur, phone=phone, document_type="work_permit", filename="work_permit-rejected.pdf")
            created_files.append(wp_file)
            _upsert_compliance(cur, document_type="work_permit", status="needs_review", expiry=today + timedelta(days=200))
            _insert_version(
                cur,
                document_type="work_permit",
                version_no=1,
                file_id=wp_file,
                review_status="rejected_reupload",
                is_current=True,
                expiry=today + timedelta(days=200),
                issue=today - timedelta(days=20),
                rejection_reason="The photo is unclear. Please upload a sharper scan.",
            )

            # —— Current / healthy ——
            for dtype, days, issue_ago in (
                ("passport", 700, 200),
                ("employment_contract", None, 500),
                ("personal_photo", None, 100),
                ("medical", 400, 60),
            ):
                fid = _insert_file(cur, phone=phone, document_type=dtype, filename=f"{dtype}-current.pdf")
                created_files.append(fid)
                expiry = today + timedelta(days=days) if days is not None else None
                _upsert_compliance(cur, document_type=dtype, status="valid", expiry=expiry)
                if dtype == "passport":
                    old = _insert_file(cur, phone=phone, document_type=dtype, filename=f"{dtype}-old.pdf")
                    created_files.append(old)
                    _insert_version(
                        cur,
                        document_type=dtype,
                        version_no=1,
                        file_id=old,
                        review_status="superseded",
                        is_current=False,
                        expiry=today - timedelta(days=30),
                        issue=today - timedelta(days=900),
                    )
                    _insert_version(
                        cur,
                        document_type=dtype,
                        version_no=2,
                        file_id=fid,
                        review_status="hr_reviewed",
                        is_current=True,
                        expiry=expiry,
                        issue=today - timedelta(days=issue_ago),
                    )
                else:
                    _insert_version(
                        cur,
                        document_type=dtype,
                        version_no=1,
                        file_id=fid,
                        review_status="hr_reviewed",
                        is_current=True,
                        expiry=expiry,
                        issue=today - timedelta(days=issue_ago),
                    )

            # Education cert — current + multi-year superseded history for density
            edu_versions: list[tuple[str, date | None, bool]] = []
            for idx, (year, month, current) in enumerate(
                (
                    (2023, 4, False),
                    (2023, 11, False),
                    (2024, 1, False),
                    (2024, 8, False),
                    (2025, 3, False),
                    (2026, 1, True),
                ),
                start=1,
            ):
                fid = _insert_file(
                    cur,
                    phone=phone,
                    document_type="education_cert",
                    filename=f"education_cert-{year}-{month:02d}.pdf",
                )
                created_files.append(fid)
                exp = None if current else date(year, month, 15)
                edu_versions.append((fid, exp, current))
            _upsert_compliance(cur, document_type="education_cert", status="valid", expiry=None)
            for i, (fid, exp, is_current) in enumerate(edu_versions, start=1):
                _insert_version(
                    cur,
                    document_type="education_cert",
                    version_no=i,
                    file_id=fid,
                    review_status="hr_reviewed" if is_current else "superseded",
                    is_current=is_current,
                    expiry=exp,
                    issue=(exp or today) - timedelta(days=30),
                )

        conn.commit()

    # Ensure access + activation for physical inspect
    if not emp.get("app_access_enabled"):
        import employee_app_access as access

        access.set_employee_app_access(
            legacy,
            {
                "company_code": COMPANY,
                "user_id": "docs-visual-fixture",
                "actor_user_id": "docs-visual-fixture",
                "email": "docs-visual-fixture@wathefni.ai",
                "permissions": ["employees.manage", "onboarding.manage"],
            },
            employee_key=KEY,
            enabled=True,
            reason="docs-visual-fixture",
            deliver_invite=False,
        )
        emp = legacy.find_employee_by_key(KEY, company_code=COMPANY) or emp

    invite, code = legacy.create_employee_app_invite(
        COMPANY, emp, created_by_user_id="docs-visual-fixture"
    )

    phone = legacy.digits(emp.get("phone"))
    ctx = {
        "company_code": COMPANY,
        "employee_key": KEY,
        "employee": emp,
        "phone": phone,
        "session_id": f"docs-visual-{STAMP}",
        "actor_employee_key": KEY,
        "actor_user_id": f"employee_app:{KEY}",
        "actor_phone": phone,
        "actor_email": emp.get("email") or "",
        "actor_role": "employee",
        "hr_phone": "",
        "hr_user": {
            "role": "employee",
            "company_code": COMPANY,
            "phone": phone,
            "name": emp.get("name") or "",
        },
    }
    page = legacy.app_documents(context=ctx)
    compliance = page.get("compliance") or []
    documents = page.get("documents") or []
    statuses = {str(i.get("review_status") or "") for i in compliance}
    attention = sum(
        1
        for i in compliance
        if i.get("renewal_required")
        or str(i.get("review_status") or "")
        in {
            "expired",
            "expiring_soon",
            "rejected_reupload",
            "missing",
            "pending_hr_review",
            "replacement_required",
        }
        or i.get("rejection_reason")
    )
    current = len(compliance) - attention
    ok = (
        attention >= 2
        and current >= 3
        and len(documents) >= 8
        and ("expired" in statuses or "expiring_soon" in statuses)
        and "hr_reviewed" in statuses
    )
    return {
        "ok": ok,
        "stamp": STAMP,
        "employee_key": KEY,
        "name": emp.get("name"),
        "phone": phone,
        "activation_code": code,
        "invite_expires_at": str(invite.get("expires_at") or ""),
        "compliance_count": len(compliance),
        "attention_estimate": attention,
        "current_estimate": current,
        "registry_count": len(documents),
        "statuses": sorted(statuses),
        "files_created": len(created_files),
        "protected_untouched": sorted(PROTECTED),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", default=os.environ.get("WATHEFNI_COMPANY_CODE"))
    parser.add_argument("--ack-non-production", default=os.environ.get("WATHEFNI_DATA_SAFETY_ACK"))
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.cleanup:
        print(json.dumps(cleanup(), indent=2))
        return 0
    result = seed()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
