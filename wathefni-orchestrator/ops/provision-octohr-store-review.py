#!/usr/bin/env python3
"""Provision the one production store-review tenant and its synthetic dataset.

This is deliberately not generic fixture tooling. It is hard-pinned to
OCTOHR-STORE-REVIEW, refuses to reconcile any company not bearing its exact
synthetic marker, writes new reviewer passwords only to owner-only files, and
gives the normal session and authorization authorities the same rows they use
for every other tenant.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import tempfile
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

COMPANY = "OCTOHR-STORE-REVIEW"
MARKER = "octohr_store_review_v1"
ACTOR = "96500000999"
MODULES = (
    "employee_app", "onboarding", "compliance", "attendance", "shifts", "leave",
    "payroll", "performance", "talent", "learning", "benefits", "engagement",
)
REVIEW_IDENTITIES = (
    {
        "store": "apple", "principal": "employee",
        "username": "apple.employee@review.octo-hr.com",
        "subject_id": f"{COMPANY}-96500000101",
    },
    {
        "store": "apple", "principal": "hr",
        "username": "apple.hr@review.octo-hr.com",
        "subject_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "apple.hr.review.octo-hr.com")),
    },
    {
        "store": "google", "principal": "employee",
        "username": "google.employee@review.octo-hr.com",
        "subject_id": f"{COMPANY}-96500000102",
    },
    {
        "store": "google", "principal": "hr",
        "username": "google.hr@review.octo-hr.com",
        "subject_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "google.hr.review.octo-hr.com")),
    },
)
SYNTHETIC_EMPLOYEES = (
    (f"{COMPANY}-96500000101", "96500000101", "Apple Employee Reviewer", "apple.employee@review.octo-hr.com", "People Operations Specialist", True),
    (f"{COMPANY}-96500000102", "96500000102", "Google Employee Reviewer", "google.employee@review.octo-hr.com", "Customer Success Specialist", True),
    (f"{COMPANY}-96500000103", "96500000103", "Mariam Al-Sabah", "mariam@synthetic.invalid", "People Operations Manager", False),
    (f"{COMPANY}-96500000104", "96500000104", "Yousef Al-Hamad", "yousef@synthetic.invalid", "Finance Analyst", False),
    (f"{COMPANY}-96500000105", "96500000105", "Noor Al-Khaled", "noor@synthetic.invalid", "Learning Coordinator", False),
)

# These gates are required by the already-frozen domain authorities while this
# explicit maintenance command seeds their canonical tables. Runtime receives
# the same company-scoped gates through the production service configuration.
for name in (
    "WATHEFNI_PERFORMANCE_GOALS_C1",
    "WATHEFNI_TALENT_PROFILE_C5",
    "WATHEFNI_LEARNING_C2",
    "WATHEFNI_BENEFITS_C3",
    "WATHEFNI_ENGAGEMENT_C5",
    "WATHEFNI_PAYROLL_WAVE1",
    "WATHEFNI_PAYROLL_WAVE2A",
    "WATHEFNI_PAYROLL_WAVE3",
):
    os.environ.setdefault(name, "on")
for name in (
    "WATHEFNI_PERFORMANCE_GOALS_COMPANIES",
    "WATHEFNI_TALENT_PROFILE_COMPANIES",
    "WATHEFNI_LEARNING_COMPANIES",
    "WATHEFNI_BENEFITS_COMPANIES",
    "WATHEFNI_ENGAGEMENT_COMPANIES",
    "WATHEFNI_PAYROLL_WAVE1_COMPANIES",
    "WATHEFNI_PAYROLL_WAVE2A_COMPANIES",
    "WATHEFNI_PAYROLL_WAVE3_COMPANIES",
):
    os.environ.setdefault(name, COMPANY)
for name in (
    "WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY",
    "WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY",
    "WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_ONLY",
):
    os.environ.setdefault(name, "on")
for name in (
    "WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_KEY_MARKERS",
):
    os.environ.setdefault(name, COMPANY)
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "1")

import app as legacy  # noqa: E402
import benefits_administration_c3 as benefits  # noqa: E402
import engagement_c5 as engagement  # noqa: E402
import learning_development_c2 as learning  # noqa: E402
import payroll_authority_wave1 as payroll_authority  # noqa: E402
import payroll_external_adapter_wave2a as payroll_external  # noqa: E402
import payroll_payslip_wave3 as payslips  # noqa: E402
import performance_goals_c1 as performance  # noqa: E402
import talent_profile_c5 as talent  # noqa: E402
from psycopg2.extras import Json  # noqa: E402


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--reconcile-existing",
        action="store_true",
        help="Reconcile only the existing marker-owned synthetic tenant without rotating reviewer credentials.",
    )
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--owner-file", type=Path)
    parser.add_argument("--report-file", type=Path)
    parser.add_argument("--apple-instructions-file", type=Path)
    parser.add_argument("--google-instructions-file", type=Path)
    return parser.parse_args()


def _secure_write(path: Path, payload: dict[str, Any]) -> None:
    if not path.is_absolute():
        raise SystemExit("credential and report paths must be absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise SystemExit(f"refusing symlink: {path}")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


def _secure_write_text(path: Path, value: str) -> None:
    if not path.is_absolute():
        raise SystemExit("credential and instruction paths must be absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise SystemExit(f"refusing symlink: {path}")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, value.encode("utf-8"))
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


def _expect(label: str, result: dict[str, Any]) -> dict[str, Any]:
    if not result.get("ok"):
        raise RuntimeError(f"{label}: {result.get('error') or 'failed'}")
    return result


def _existing_company(cur: Any) -> dict[str, Any] | None:
    cur.execute("SELECT * FROM companies WHERE company_code=%s", (COMPANY,))
    row = cur.fetchone()
    return dict(row) if row else None


def _guard_company(cur: Any, *, reconcile_existing: bool) -> None:
    row = _existing_company(cur)
    if not row:
        if reconcile_existing:
            raise RuntimeError("store_review_company_missing_for_reconcile")
        return
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if not reconcile_existing:
        raise RuntimeError("store_review_company_already_exists")
    if metadata.get("provisioner") != MARKER or metadata.get("synthetic_only") is not True:
        raise RuntimeError("existing_company_not_owned_by_store_review_provisioner")


def _upsert_company_and_modules(cur: Any) -> None:
    cur.execute(
        """
        INSERT INTO companies
          (company_code, name, country, status, metadata, raw_json, created_at, updated_at)
        VALUES (%s,'OctoHR Store Review','KW','active',%s,%s,now(),now())
        ON CONFLICT (company_code) DO UPDATE SET
          name=EXCLUDED.name, country=EXCLUDED.country, status='active',
          metadata=EXCLUDED.metadata, raw_json=EXCLUDED.raw_json, updated_at=now()
        """,
        (
            COMPANY,
            Json({"provisioner": MARKER, "synthetic_only": True, "store_review": True}),
            Json({"provisioner": MARKER, "synthetic_only": True, "locale": "en-KW"}),
        ),
    )
    for module in MODULES:
        cur.execute(
            """
            INSERT INTO company_modules (company_code,module_key,enabled,source,settings)
            VALUES (%s,%s,true,%s,%s)
            ON CONFLICT (company_code,module_key) DO UPDATE SET
              enabled=true, source=EXCLUDED.source, settings=EXCLUDED.settings, updated_at=now()
            """,
            (COMPANY, module, MARKER, Json({"synthetic_review": True})),
        )


def _upsert_employees(cur: Any) -> None:
    for key, phone, name, email, title, app_access in SYNTHETIC_EMPLOYEES:
        profile = {
            "department": "People & Culture" if "People" in title or "Learning" in title else "Operations",
            "employment_type": "full_time",
            "location": "Kuwait City",
            "grade": "P3",
            "preferred_locale": "en",
            "synthetic": True,
            "provisioner": MARKER,
        }
        cur.execute(
            """
            INSERT INTO employees
              (employee_key,phone,company_code,app_key,name,email,position_title,hire_date,start_date,
               onboarding_status,documents_pending,documents_complete,compliance_status,profile,raw_json,
               employment_status,app_access_enabled,created_at,updated_at)
            VALUES (%s,%s,%s,NULL,%s,%s,%s,%s,%s,'in_progress',1,2,'attention',%s,%s,
                    'active',%s,now(),now())
            ON CONFLICT (employee_key) DO UPDATE SET
              phone=EXCLUDED.phone, company_code=EXCLUDED.company_code, app_key=NULL,
              name=EXCLUDED.name, email=EXCLUDED.email, position_title=EXCLUDED.position_title,
              employment_status='active', app_access_enabled=EXCLUDED.app_access_enabled,
              profile=EXCLUDED.profile, raw_json=EXCLUDED.raw_json, updated_at=now()
            """,
            (
                key, phone, COMPANY, name, email, title,
                date(2024, 7, 1), date(2024, 7, 1), Json(profile), Json(profile), app_access,
            ),
        )


def _upsert_hr_users(cur: Any) -> None:
    for identity in REVIEW_IDENTITIES:
        if identity["principal"] != "hr":
            continue
        # Deliberately unrelated to the reviewer password: normal HR login must
        # not become a second route for these credentials.
        unreachable_hash = legacy.dashboard_password_hash(secrets.token_urlsafe(48))
        cur.execute(
            """
            INSERT INTO dashboard_users
              (user_id,company_code,email,name,phone,role,status,password_hash,accepted_at,metadata,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,'admin','active',%s,now(),%s,now(),now())
            ON CONFLICT (user_id) DO UPDATE SET
              company_code=EXCLUDED.company_code, email=EXCLUDED.email, name=EXCLUDED.name,
              phone=EXCLUDED.phone, role='admin', status='active',
              metadata=EXCLUDED.metadata, disabled_at=NULL, updated_at=now()
            """,
            (
                identity["subject_id"], COMPANY, identity["username"],
                "Apple HR Reviewer" if identity["store"] == "apple" else "Google HR Reviewer",
                "96500000201" if identity["store"] == "apple" else "96500000202",
                unreachable_hash,
                Json({"provisioner": MARKER, "synthetic_only": True, "store": identity["store"]}),
            ),
        )


def _seed_workday(cur: Any) -> None:
    today = date.today()
    now = datetime.now(timezone.utc)
    for index, (key, phone, name, _email, _title, _app_access) in enumerate(SYNTHETIC_EMPLOYEES):
        cur.execute(
            "DELETE FROM shift_assignments WHERE company_code=%s AND employee_key=%s AND metadata->>'provisioner'=%s",
            (COMPANY, key, MARKER),
        )
        for delta, start_hour in ((0, 9), (1, 9), (2, 10)):
            cur.execute(
                """
                INSERT INTO shift_assignments
                  (company_code,employee_key,employee_phone,employee_name,shift_date,start_time,end_time,
                   timezone,role,location,status,notes,metadata,created_by_phone)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'Asia/Kuwait',%s,'OctoHR Review Office','scheduled',
                        'Synthetic store-review schedule',%s,%s)
                """,
                (
                    COMPANY, key, phone, name, today + timedelta(days=delta), time(start_hour, 0),
                    time(start_hour + 8, 0), "Team member", Json({"provisioner": MARKER}), ACTOR,
                ),
            )
        cur.execute(
            "DELETE FROM attendance_records WHERE company_code=%s AND employee_key=%s AND metadata->>'provisioner'=%s",
            (COMPANY, key, MARKER),
        )
        for days_ago in (1, 2, 3):
            day = today - timedelta(days=days_ago)
            check_in = datetime.combine(day, time(9, 0), timezone.utc) + timedelta(minutes=index * 2)
            cur.execute(
                """
                INSERT INTO attendance_records
                  (company_code,employee_key,employee_phone,employee_name,attendance_date,scheduled_start,
                   scheduled_end,check_in_at,check_out_at,status,late_minutes,metadata,created_by_phone)
                VALUES (%s,%s,%s,%s,%s,'09:00','17:00',%s,%s,'present',%s,%s,%s)
                ON CONFLICT (company_code,employee_key,attendance_date,shift_id) DO NOTHING
                """,
                (
                    COMPANY, key, phone, name, day, check_in, check_in + timedelta(hours=8),
                    index * 2, Json({"provisioner": MARKER}), ACTOR,
                ),
            )
        cur.execute(
            "DELETE FROM leave_requests WHERE company_code=%s AND employee_key=%s AND metadata->>'provisioner'=%s",
            (COMPANY, key, MARKER),
        )
        cur.execute(
            """
            INSERT INTO leave_requests
              (company_code,employee_key,employee_phone,employee_name,start_date,end_date,leave_type,status,
               reason,decision_note,requested_by_phone,decided_by_phone,requested_at,decided_at,metadata)
            VALUES (%s,%s,%s,%s,%s,%s,'annual','approved','Family time','Approved for review dataset',
                    %s,%s,%s,%s,%s)
            """,
            (
                COMPANY, key, phone, name, today + timedelta(days=14), today + timedelta(days=15),
                phone, ACTOR, now - timedelta(days=3), now - timedelta(days=2), Json({"provisioner": MARKER}),
            ),
        )


def _seed_onboarding_documents_notifications(cur: Any) -> None:
    for key, _phone, _name, _email, _title, app_access in SYNTHETIC_EMPLOYEES:
        if not app_access:
            continue
        cur.execute("DELETE FROM onboarding_items WHERE company_code=%s AND employee_key=%s", (COMPANY, key))
        items = (
            ("profile-details", "Confirm profile details", "task", None, True, "complete"),
            ("civil-id", "Upload Civil ID", "document", "civil_id", True, "complete"),
            ("bank-details", "Confirm bank details", "task", None, True, "pending"),
        )
        for item_id, label, item_type, document_type, required, status in items:
            cur.execute(
                """
                INSERT INTO onboarding_items
                  (company_code,employee_key,item_id,label,item_type,document_type,required,status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (COMPANY, key, item_id, label, item_type, document_type, required, status),
            )
        cur.execute(
            "DELETE FROM employee_messages WHERE company_code=%s AND employee_key=%s AND metadata->>'provisioner'=%s",
            (COMPANY, key, MARKER),
        )
        messages = (
            ("leave_decision", "leave_request_approved", "Your annual leave request was approved.", "تمت الموافقة على طلب إجازتك السنوية.", "/(tabs)/leave"),
            ("payroll", "payslip_ready", "Your latest payslip is ready.", "كشف راتبك الأخير جاهز.", "/payslips"),
            ("learning", "learning_assignment", "Workplace Safety Essentials is assigned to you.", "تم تعيين أساسيات السلامة في مكان العمل لك.", "/learning"),
            ("performance", "performance_update", "Your quarterly objective has been updated.", "تم تحديث هدفك الفصلي.", "/performance"),
        )
        for seq, (flow, template, body_en, body_ar, path) in enumerate(messages):
            cur.execute(
                """
                INSERT INTO employee_messages
                  (message_id,company_code,employee_key,flow,template_key,criticality,sensitivity,locale,
                   target_email,status,channel_used,body_preview,dedupe_key,metadata,delivered_at,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,'standard','preview','en',NULL,'delivered','in_app',%s,%s,%s,
                        now(),now()-(%s || ' hours')::interval,now())
                """,
                (
                    str(uuid.uuid4()), COMPANY, key, flow, template, body_en,
                    f"{MARKER}:{key}:{flow}",
                    Json({"provisioner": MARKER, "body_ar": body_ar, "deep_link": {"path": path}}),
                    str(2 + seq * 5),
                ),
            )


def _seed_employee_documents(cur: Any) -> None:
    """Store a real synthetic document through the canonical file authority."""
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 83>>stream\nBT /F1 14 Tf 72 720 Td (Synthetic OctoHR store review employment letter) Tj ET\nendstream endobj\n"
        b"xref\n0 5\n0000000000 65535 f \ntrailer<</Root 1 0 R/Size 5>>\nstartxref\n0\n%%EOF\n"
    )
    checksum = hashlib.sha256(pdf_bytes).hexdigest()
    for key, phone, _name, _email, _title, app_access in SYNTHETIC_EMPLOYEES:
        if not app_access:
            continue
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="octohr-review-", suffix=".pdf", delete=False) as handle:
                handle.write(pdf_bytes)
                temp_path = Path(handle.name)
            stored = legacy.store_subject_file(
                company_code=COMPANY,
                owner_phone=phone,
                subject_type="employee",
                subject_key=key,
                file_kind="employee_document",
                source_path=temp_path,
                mime_type="application/pdf",
                checksum=checksum,
            )
            if not stored.get("ok"):
                raise RuntimeError(f"review_document_storage_failed:{stored.get('storage_error') or 'unknown'}")
            legacy.upsert_file_registry(
                cur,
                company_code=COMPANY,
                owner_phone=phone,
                subject_type="employee",
                subject_key=key,
                file_kind="employee_document",
                document_type="employment_letter",
                original_filename="synthetic-employment-letter.pdf",
                source_path=None,
                local_path=str((stored.get("metadata") or {}).get("local_path") or "") or None,
                storage_result=stored,
                metadata={
                    "provisioner": MARKER,
                    "synthetic_only": True,
                    "label": "Employment letter",
                    "label_ar": "خطاب التوظيف",
                },
            )
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()


def _approved_review_contract(cur: Any, *, employee_key: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT contract_id::text
        FROM payroll_compensation_contracts
        WHERE company_code=%s AND employee_key=%s AND status='approved'
          AND metadata->>'provisioner'=%s
        ORDER BY effective_from DESC, created_at DESC
        LIMIT 1
        """,
        (COMPANY, employee_key, MARKER),
    )
    existing = cur.fetchone()
    if existing:
        contract = payroll_authority.get_contract(
            cur, company_code=COMPANY, contract_id=str(dict(existing)["contract_id"])
        )
        if contract:
            return contract
    created = _expect(
        "payroll contract draft",
        payroll_authority.create_contract_draft(
            cur,
            company_code=COMPANY,
            employee_key=employee_key,
            effective_from=date(2024, 7, 1),
            components=[
                {
                    "component_kind": "earning",
                    "code": "BASIC",
                    "label_en": "Basic salary",
                    "label_ar": "الراتب الأساسي",
                    "amount": 1000,
                    "amount_unit": "monthly",
                    "is_basic": True,
                    "sort_order": 10,
                },
                {
                    "component_kind": "allowance",
                    "code": "HOUSING",
                    "label_en": "Housing allowance",
                    "label_ar": "بدل السكن",
                    "amount": 250,
                    "amount_unit": "monthly",
                    "sort_order": 20,
                },
                {
                    "component_kind": "deduction",
                    "code": "SOCIAL_INSURANCE",
                    "label_en": "Social insurance",
                    "label_ar": "التأمينات الاجتماعية",
                    "amount": 92.5,
                    "amount_unit": "monthly",
                    "sort_order": 30,
                },
            ],
            actor_phone=ACTOR,
            reason=f"{MARKER}:canonical_contract",
            metadata={"provisioner": MARKER, "synthetic_only": True},
        ),
    )["contract"]
    return _expect(
        "payroll contract approval",
        payroll_authority.approve_contract(
            cur,
            company_code=COMPANY,
            contract_id=str(created["contract_id"]),
            actor_phone="96500000998",
            reason=f"{MARKER}:canonical_contract_approval",
            expected_row_version=int(created.get("row_version") or 1),
        ),
    )["contract"]


def _payroll_period(cur: Any, *, period_start: date, period_end: date) -> dict[str, Any]:
    cur.execute(
        """
        SELECT * FROM payroll_periods
        WHERE company_code=%s AND period_start=%s AND period_end=%s
        """,
        (COMPANY, period_start, period_end),
    )
    existing = cur.fetchone()
    if existing:
        return dict(existing)
    return _expect(
        "payroll period",
        payroll_authority.create_period(
            cur,
            company_code=COMPANY,
            period_start=period_start,
            period_end=period_end,
            attendance_input_source="legacy_records",
            actor_phone=ACTOR,
            reason=f"{MARKER}:canonical_period",
        ),
    )["period"]


def _seed_payslips(cur: Any) -> None:
    """Create released review payslips only through the frozen payroll authorities."""
    payroll_authority.ensure_payroll_wave1_schema(cur)
    payroll_external.ensure_payroll_wave2a_schema(cur)
    payslips.ensure_payroll_wave3_schema(cur)
    _expect(
        "external payroll mode",
        payroll_authority.set_payroll_mode(
            cur,
            company_code=COMPANY,
            mode="external",
            attendance_input_source="legacy_records",
            actor_phone=ACTOR,
            reason=f"{MARKER}:external_money_authority",
        ),
    )
    review_people = [row for row in SYNTHETIC_EMPLOYEES if row[5]]
    contracts = [
        _approved_review_contract(cur, employee_key=employee_key)
        for employee_key, _phone, _name, _email, _title, _access in review_people
    ]
    employees = [
        {"employee_key": employee_key, "phone": phone, "name": name}
        for employee_key, phone, name, _email, _title, _access in review_people
    ]

    # Preserve the old direct-seed rows as revoked history; never hard-delete.
    cur.execute(
        """
        SELECT payslip_id::text
        FROM payroll_payslip_documents
        WHERE company_code=%s AND status='active'
          AND document_payload->>'provisioner'=%s
        """,
        (COMPANY, MARKER),
    )
    for row in cur.fetchall():
        _expect(
            "revoke legacy review payslip",
            payslips.revoke_payslip(
                cur,
                company_code=COMPANY,
                payslip_id=str(dict(row)["payslip_id"]),
                actor_phone=ACTOR,
                reason=f"{MARKER}:replace_direct_seed_with_canonical_authority",
            ),
        )

    first_this_month = date.today().replace(day=1)
    for months_ago in (1, 2, 3):
        period_end = first_this_month - timedelta(days=1)
        for _ in range(months_ago - 1):
            period_end = period_end.replace(day=1) - timedelta(days=1)
        period_start = period_end.replace(day=1)
        period = _payroll_period(cur, period_start=period_start, period_end=period_end)
        external_run_id = f"OCTOHR-REVIEW-{period_end.strftime('%Y%m')}"
        exported = _expect(
            "payroll external export",
            payroll_external.create_external_export(
                cur,
                company_code=COMPANY,
                period=period,
                employees=employees,
                contracts=contracts,
                attendance=[{"employee_key": row[0], "worked_minutes": 9600} for row in review_people],
                leave_classifications=[
                    {"employee_key": row[0], "leave_type": "annual", "classification": "paid"}
                    for row in review_people
                ],
                actor_phone=ACTOR,
                reason=f"{MARKER}:canonical_export:{period_end.isoformat()}",
                external_run_id=external_run_id,
            ),
        )
        export_run = exported["export_run"]
        export_payload = export_run.get("payload") or {}
        if isinstance(export_payload, str):
            export_payload = json.loads(export_payload)
        if not export_payload:
            cur.execute(
                "SELECT payload FROM payroll_adapter_export_runs WHERE export_run_id=%s",
                (str(export_run["export_run_id"]),),
            )
            export_payload = dict(cur.fetchone())["payload"]
        result_csv = payroll_external.build_synthetic_result_csv(
            export_payload=export_payload,
            external_run_id=external_run_id,
        )
        imported = _expect(
            "payroll external import",
            payroll_external.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=str(export_run["export_run_id"]),
                csv_text=result_csv,
                actor_phone="96500000998",
                reason=f"{MARKER}:canonical_import:{period_end.isoformat()}",
                expected_input_fingerprint=str(exported["input_fingerprint"]),
            ),
        )
        import_run = imported["import_run"]
        reconciliation = _expect(
            "payroll export/import reconciliation",
            payroll_external.reconcile_export_import(
                cur,
                company_code=COMPANY,
                export_run_id=str(export_run["export_run_id"]),
                import_run_id=str(import_run["import_run_id"]),
                actor_phone="96500000998",
                reason=f"{MARKER}:canonical_reconciliation:{period_end.isoformat()}",
            ),
        )
        if reconciliation.get("has_differences"):
            raise RuntimeError("review_payroll_reconciliation_has_differences")
        for employee_key, _phone, _name, _email, _title, _access in review_people:
            generated = _expect(
                "payslip generation",
                payslips.generate_external_payslip(
                    cur,
                    company_code=COMPANY,
                    import_run_id=str(import_run["import_run_id"]),
                    employee_key=employee_key,
                    actor_phone=ACTOR,
                    reason=f"{MARKER}:canonical_payslip_generation",
                ),
            )
            _expect(
                "payslip release",
                payslips.release_payslip_to_employee(
                    cur,
                    company_code=COMPANY,
                    payslip_id=str(generated["payslip"]["payslip_id"]),
                    actor_phone="96500000998",
                    reason=f"{MARKER}:explicit_employee_release",
                ),
            )
        if str(period.get("status")) == "open":
            period = _expect(
                "payroll period lock",
                payroll_authority.lock_period(
                    cur,
                    company_code=COMPANY,
                    period_id=str(period["period_id"]),
                    actor_phone="96500000998",
                    reason=f"{MARKER}:period_finalization",
                    expected_row_version=int(period.get("row_version") or 1),
                ),
            )["period"]
        if str(period.get("status")) == "locked":
            _expect(
                "payroll period close",
                payroll_authority.close_period(
                    cur,
                    company_code=COMPANY,
                    period_id=str(period["period_id"]),
                    actor_phone="96500000998",
                    reason=f"{MARKER}:period_finalization",
                    expected_row_version=int(period.get("row_version") or 1),
                ),
            )


def _seed_posthire(cur: Any) -> dict[str, Any]:
    employee_keys = [row[0] for row in SYNTHETIC_EMPLOYEES]
    _expect("enable performance", performance.enable_company_performance_goals(
        cur, company_code=COMPANY, actor_phone=ACTOR, reason=MARKER,
    ))
    _expect("enable talent", talent.enable_company_talent_profile(
        cur, company_code=COMPANY, actor_phone=ACTOR, reason=MARKER,
    ))
    _expect("enable learning", learning.enable_company_learning(
        cur, company_code=COMPANY, actor_phone=ACTOR, reason=MARKER,
    ))
    _expect("enable benefits", benefits.enable_company_benefits(
        cur, company_code=COMPANY, actor_phone=ACTOR, reason=MARKER,
        employee_self_service_enabled=True,
    ))
    _expect("enable engagement", engagement.enable_company_engagement(
        cur, company_code=COMPANY, actor_phone=ACTOR, reason=MARKER, min_responses=5,
    ))

    period_start = date.today().replace(month=1, day=1)
    period_end = date.today().replace(month=12, day=31)
    measure = _expect("performance measure", performance.create_measure_definition(
        cur, company_code=COMPANY, actor_phone=ACTOR, name_en="Employee experience score",
        unit="percent", direction="higher_is_better", baseline=72, target=90,
        period_start=period_start, period_end=period_end,
        owner_employee_key=employee_keys[0],
    ))
    objective = _expect("performance objective", performance.create_objective(
        cur, company_code=COMPANY, actor_phone=ACTOR,
        title_en="Deliver an excellent employee experience",
        title_ar="تقديم تجربة موظف ممتازة", scope="individual",
        owner_employee_key=employee_keys[0], period_start=period_start, period_end=period_end,
    ))
    objective_id = str(objective["objective"]["objective_id"])
    key_result = _expect("performance key result", performance.add_key_result(
        cur, company_code=COMPANY, objective_id=objective_id, actor_phone=ACTOR,
        title_en="Reach a 90% experience score",
        measure_id=str(measure["measure"]["measure_id"]), weight=1,
    ))
    _expect("activate performance objective", performance.activate_objective(
        cur, company_code=COMPANY, objective_id=objective_id, actor_phone=ACTOR, reason=MARKER,
    ))
    _expect("performance progress", performance.record_progress(
        cur, company_code=COMPANY, subject_type="key_result",
        subject_id=str(key_result["key_result"]["key_result_id"]),
        actor_phone=ACTOR, current_value=82, source="manual",
        note="Synthetic store-review progress",
    ))

    for key in employee_keys[:2]:
        _expect("talent profile", talent.ensure_talent_profile(
            cur, company_code=COMPANY, employee_key=key, actor_phone=ACTOR,
        ))
        _expect("talent aspiration", talent.add_dimension_fact(
            cur, company_code=COMPANY, actor_phone=ACTOR, employee_key=key,
            dimension_kind="career_aspiration", title_en="Grow into a team lead role",
            title_ar="التطور إلى دور قائد فريق", source="employee_declared",
            visibility="employee_visible", reason=MARKER,
        ))
        _expect("talent skill", talent.add_dimension_fact(
            cur, company_code=COMPANY, actor_phone=ACTOR, employee_key=key,
            dimension_kind="skill_note", title_en="Stakeholder communication",
            title_ar="التواصل مع أصحاب المصلحة", source="manager_assessed",
            visibility="employee_visible", confidence="demonstrated", reason=MARKER,
        ))

    provider = _expect("learning provider", learning.upsert_provider(
        cur, company_code=COMPANY, actor_phone=ACTOR, code="OCTOHR-ACADEMY",
        name_en="OctoHR Academy", name_ar="أكاديمية أوكتو إتش آر",
    ))
    course = _expect("learning course", learning.upsert_learning_item(
        cur, company_code=COMPANY, actor_phone=ACTOR, code="SAFE-101",
        item_type="mandatory_compliance", title_en="Workplace Safety Essentials",
        title_ar="أساسيات السلامة في مكان العمل", status="published", category="compliance",
        provider_id=str(provider["provider"]["provider_id"]), delivery_mode="self_paced",
        duration_minutes=35, completion_requirements={"pass_score": 80}, reason=MARKER,
    ))
    for key in employee_keys[:2]:
        _expect("learning assignment", learning.create_assignment(
            cur, company_code=COMPANY, actor_phone=ACTOR, employee_key=key,
            item_id=str(course["stable_id"]), item_version=int(course["item"]["effective_version"]),
            source="hr_assigned", required=True, due_date=date.today() + timedelta(days=14), reason=MARKER,
        ))

    benefit_provider = _expect("benefits provider", benefits.upsert_provider(
        cur, company_code=COMPANY, actor_phone=ACTOR, code="REVIEW-MED",
        name_en="Review Health Network", name_ar="شبكة الرعاية التجريبية",
    ))
    plan = _expect("benefits plan", benefits.upsert_plan(
        cur, company_code=COMPANY, actor_phone=ACTOR, code="MED-PLUS", category="medical",
        title_en="Medical Plus", title_ar="التأمين الطبي بلس", status="published",
        provider_id=str(benefit_provider["provider"]["provider_id"]),
        tier_options=["employee_only", "family"],
        contribution_policy={"employee_mode": "fixed", "amount": 12, "currency": "KWD"},
        effective_start=date.today() - timedelta(days=30), reason=MARKER,
    ))
    rule = _expect("benefits rule", benefits.create_eligibility_rule(
        cur, company_code=COMPANY, actor_phone=ACTOR, plan_id=str(plan["stable_id"]),
        code="ACTIVE-FT", title_en="Active full-time employees",
        title_ar="الموظفون النشطون بدوام كامل",
        criteria={"employment_status": "active", "employment_type": "full_time"},
    ))
    for key in employee_keys[:2]:
        _expect("benefits eligibility", benefits.evaluate_eligibility(
            cur, company_code=COMPANY, employee_key=key, plan_id=str(plan["stable_id"]),
            rule_id=str(rule["rule"]["rule_id"]),
            attributes={"employment_status": "active", "employment_type": "full_time"},
        ))

    survey = _expect("engagement survey", engagement.create_survey_template(
        cur, company_code=COMPANY, actor_phone=ACTOR, code="REVIEW-PULSE",
        title_en="Employee Experience Pulse", title_ar="نبض تجربة الموظف",
    ))
    survey_version = _expect("engagement survey version", engagement.create_survey_version(
        cur, company_code=COMPANY, actor_phone=ACTOR, survey_id=str(survey["stable_id"]),
        version_no=1, privacy_mode="anonymous", min_responses=5,
        questions=[
            {"question_type": "rating_scale", "prompt_en": "I have what I need to do my best work", "prompt_ar": "لدي ما أحتاجه لتقديم أفضل عمل", "scale_min": 1, "scale_max": 5, "sort_order": 0},
            {"question_type": "free_text", "prompt_en": "What would improve your experience?", "prompt_ar": "ما الذي سيحسن تجربتك؟", "sort_order": 1},
        ],
    ))
    campaign = _expect("engagement campaign", engagement.create_campaign(
        cur, company_code=COMPANY, actor_phone=ACTOR, survey_id=str(survey["stable_id"]),
        survey_version_id=str(survey_version["survey_version"]["survey_version_id"]),
        title_en="August Employee Pulse", title_ar="نبض الموظفين لشهر أغسطس",
        audience_rule={"scope": "all_employees", "synthetic_review": True},
        audience_employee_keys=employee_keys,
    ))
    _expect("engagement launch", engagement.launch_campaign(
        cur, company_code=COMPANY, actor_phone=ACTOR,
        campaign_id=str(campaign["campaign"]["campaign_id"]),
    ))
    return {
        "objective_id": objective_id,
        "course_id": str(course["stable_id"]),
        "benefit_plan_id": str(plan["stable_id"]),
        "engagement_campaign_id": str(campaign["campaign"]["campaign_id"]),
    }


def _write_credentials(
    credentials_file: Path,
    owner_file: Path,
    apple_instructions_file: Path,
    google_instructions_file: Path,
) -> None:
    secure_rows = []
    owner_rows = []
    for identity in REVIEW_IDENTITIES:
        password = secrets.token_urlsafe(24)
        secure_rows.append({**identity, "password_hash": legacy.dashboard_password_hash(password)})
        owner_rows.append({
            "store": identity["store"],
            "principal": identity["principal"],
            "username": identity["username"],
            "password": password,
        })
    _secure_write(credentials_file, {"company_code": COMPANY, "identities": secure_rows})
    _secure_write(owner_file, {
        "company_code": COMPANY,
        "warning": "Store reviewer credentials. Keep outside Git and rotate/disable after review.",
        "identities": owner_rows,
    })
    by_pair = {(row["store"], row["principal"]): row for row in owner_rows}
    for store, label, destination in (
        ("apple", "Apple App Review", apple_instructions_file),
        ("google", "Google Play App Access", google_instructions_file),
    ):
        employee = by_pair[(store, "employee")]
        hr = by_pair[(store, "hr")]
        text = f"""{label} — OctoHR

Open OctoHR and choose Store review on the sign-in screen.

Employee workspace
Username: {employee['username']}
Password: {employee['password']}
Select Employee, then sign in. On first use, create a local six-digit PIN. No email, OTP, or MFA is required.

HR workspace
Username: {hr['username']}
Password: {hr['password']}
Select HR, then sign in.

Company: OctoHR Store Review ({COMPANY})
All displayed people and records are synthetic. Employee and HR sessions and local PINs remain separate. Use Switch workspace to move between principals after each principal has signed in.
"""
        _secure_write_text(destination, text)


def main() -> int:
    args = _args()
    if args.apply == args.validate_only:
        raise SystemExit("choose exactly one of --apply or --validate-only")
    output_paths = (
        args.credentials_file,
        args.owner_file,
        args.report_file,
        args.apple_instructions_file,
        args.google_instructions_file,
    )
    if args.apply and not args.reconcile_existing and any(path is None for path in output_paths):
        raise SystemExit("--apply requires all secure output file paths")
    if args.apply and not args.reconcile_existing and args.credentials_file.resolve() == args.owner_file.resolve():
        raise SystemExit("hashed server config and owner credential file must be different")
    if args.apply and not args.reconcile_existing:
        _write_credentials(
            args.credentials_file,
            args.owner_file,
            args.apple_instructions_file,
            args.google_instructions_file,
        )
    with legacy.db_connect() as conn:
        try:
            with conn.cursor() as cur:
                _guard_company(cur, reconcile_existing=args.reconcile_existing)
                _upsert_company_and_modules(cur)
                _upsert_employees(cur)
                _upsert_hr_users(cur)
                _seed_workday(cur)
                _seed_onboarding_documents_notifications(cur)
                if args.apply:
                    _seed_employee_documents(cur)
                _seed_payslips(cur)
                # Existing review tenants already carry canonical post-hire
                # history. Reconciliation must not duplicate it. New tenants
                # receive the full data set once through the frozen authorities.
                posthire = (
                    {"preserved_existing": True, "provisioner": MARKER}
                    if args.reconcile_existing
                    else _seed_posthire(cur)
                )
            if args.validate_only:
                conn.rollback()
            else:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
    if args.validate_only:
        print(json.dumps({"ok": True, "company_code": COMPANY, "validation_only": True}, sort_keys=True))
        return 0
    report = {
        "ok": True,
        "company_code": COMPANY,
        "synthetic_only": True,
        "identity_count": len(REVIEW_IDENTITIES),
        "review_employee_count": 2,
        "review_hr_count": 2,
        "synthetic_employee_count": len(SYNTHETIC_EMPLOYEES),
        "modules": list(MODULES),
        "posthire": posthire,
        "passwords_in_report": False,
        "secure_store_instruction_files": 2,
        "credentials_rotated": not args.reconcile_existing,
        "reconciled_existing": bool(args.reconcile_existing),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if args.report_file:
        _secure_write(args.report_file, report)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
