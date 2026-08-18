#!/usr/bin/env python3
"""Provision the isolated synthetic Google Play closed-test tenant.

This maintenance command is deliberately hard-pinned to OCTOHR-CLOSED-TEST.
It creates fifteen ordinary HR-mobile users through the existing dashboard
identity tables, never introduces an authentication bypass, and writes clear
text handoff credentials only to owner-only files outside the repository.
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

COMPANY = "OCTOHR-CLOSED-TEST"
MARKER = "octohr_closed_test_v1"
ACTOR_PHONE = "96500001999"
ACCOUNT_COUNT = 15
MODULES = (
    "pre_hiring",
    "onboarding",
    "compliance",
    "attendance",
    "shifts",
    "leave",
    "performance",
)

for name in ("WATHEFNI_PERFORMANCE_GOALS_C1", "WATHEFNI_PERFORMANCE_REVIEWS_C2"):
    os.environ[name] = "on"
for name in ("WATHEFNI_PERFORMANCE_GOALS_COMPANIES", "WATHEFNI_PERFORMANCE_REVIEWS_COMPANIES"):
    existing = {part.strip().upper() for part in os.environ.get(name, "").split(",") if part.strip()}
    existing.add(COMPANY)
    os.environ[name] = ",".join(sorted(existing))
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "1")

import app as legacy  # noqa: E402
import performance_goals_c1 as performance  # noqa: E402
import performance_reviews_c2 as performance_reviews  # noqa: E402
import prehire_jobs  # noqa: E402
from psycopg2.extras import Json  # noqa: E402


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--reconcile-existing", action="store_true")
    parser.add_argument("--owner-file", type=Path)
    parser.add_argument("--tester-instructions-file", type=Path)
    parser.add_argument("--report-file", type=Path)
    return parser.parse_args()


def _secure_write(path: Path, value: str) -> None:
    if not path.is_absolute():
        raise SystemExit("secure output paths must be absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise SystemExit(f"refusing symlink: {path}")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, value.encode("utf-8"))
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


def _secure_json(path: Path, payload: dict[str, Any]) -> None:
    _secure_write(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _identity_rows() -> list[dict[str, str]]:
    return [
        {
            "tester": f"Tester {index:02d}",
            "email": f"tester{index:02d}@closed-test.octo-hr.com",
            "user_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"tester{index:02d}.closed-test.octo-hr.com")),
            "phone": f"9650001{index:04d}",
        }
        for index in range(1, ACCOUNT_COUNT + 1)
    ]


def _new_owner_payload() -> dict[str, Any]:
    return {
        "company_code": COMPANY,
        "warning": "Synthetic closed-test credentials. Keep outside Git and active until production access is approved.",
        "identities": [
            {**identity, "password": secrets.token_urlsafe(22)}
            for identity in _identity_rows()
        ],
    }


def _load_owner(path: Path) -> dict[str, Any]:
    if not path.is_absolute() or path.is_symlink():
        raise RuntimeError("unsafe_owner_file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    identities = payload.get("identities") if isinstance(payload, dict) else None
    if payload.get("company_code") != COMPANY or not isinstance(identities, list) or len(identities) != ACCOUNT_COUNT:
        raise RuntimeError("invalid_closed_test_owner_file")
    expected = {row["email"] for row in _identity_rows()}
    actual = {str(row.get("email") or "") for row in identities}
    if expected != actual or any(not str(row.get("password") or "") for row in identities):
        raise RuntimeError("invalid_closed_test_identity_set")
    return payload


def _instructions(owner: dict[str, Any]) -> str:
    lines = [
        "OctoHR Google Play Closed Test",
        "",
        f"Company code: {COMPANY}",
        "Install OctoHR from the Google Play closed-test opt-in link, open the app, choose HR, and sign in with your assigned account below.",
        "Each tester must use only their own account. On first use, create a local six-digit PIN; do not share that PIN.",
        "All people and records are synthetic. Try Home/Inbox, People, Hiring, Attendance, Leave, Shifts, Onboarding, Documents, Tasks, and Performance.",
        "Report what you tried, device/Android version, the exact screen/action, expected result, actual result, and approximate Kuwait time.",
        "",
    ]
    for row in owner["identities"]:
        lines.extend((
            str(row["tester"]),
            f"Email: {row['email']}",
            f"Password: {row['password']}",
            "",
        ))
    return "\n".join(lines)


def _company_guard(cur: Any, *, reconcile: bool) -> None:
    cur.execute("SELECT metadata FROM companies WHERE company_code=%s", (COMPANY,))
    row = cur.fetchone()
    if not row:
        if reconcile:
            raise RuntimeError("closed_test_company_missing")
        return
    metadata = dict(row).get("metadata") or {}
    if not reconcile:
        raise RuntimeError("closed_test_company_already_exists")
    if metadata.get("provisioner") != MARKER or metadata.get("synthetic_only") is not True:
        raise RuntimeError("closed_test_company_not_marker_owned")


def _upsert_company(cur: Any) -> None:
    metadata = {
        "provisioner": MARKER,
        "synthetic_only": True,
        "google_play_closed_test": True,
        "authentication_policy": {
            "hr_mfa_required": False,
            "scope": "synthetic_closed_test_tenant_only",
        },
    }
    cur.execute(
        """
        INSERT INTO companies
          (company_code,name,country,status,metadata,raw_json,created_at,updated_at)
        VALUES (%s,'OctoHR Closed Test','KW','active',%s,%s,now(),now())
        ON CONFLICT (company_code) DO UPDATE SET
          name=EXCLUDED.name,country='KW',status='active',metadata=EXCLUDED.metadata,
          raw_json=EXCLUDED.raw_json,updated_at=now()
        """,
        (COMPANY, Json(metadata), Json({**metadata, "locale": "en-KW"})),
    )
    for module in MODULES:
        cur.execute(
            """
            INSERT INTO company_modules (company_code,module_key,enabled,source,settings)
            VALUES (%s,%s,true,%s,%s)
            ON CONFLICT (company_code,module_key) DO UPDATE SET
              enabled=true,source=EXCLUDED.source,settings=EXCLUDED.settings,updated_at=now()
            """,
            (COMPANY, module, MARKER, Json({"synthetic_closed_test": True})),
        )


def _upsert_users(cur: Any, owner: dict[str, Any]) -> None:
    expected_ids = []
    for row in owner["identities"]:
        expected_ids.append(row["user_id"])
        cur.execute(
            """
            INSERT INTO dashboard_users
              (user_id,company_code,email,name,phone,role,status,password_hash,accepted_at,metadata,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,'hr_manager','active',%s,now(),%s,now(),now())
            ON CONFLICT (user_id) DO UPDATE SET
              company_code=EXCLUDED.company_code,email=EXCLUDED.email,name=EXCLUDED.name,
              phone=EXCLUDED.phone,role='hr_manager',status='active',password_hash=EXCLUDED.password_hash,
              accepted_at=COALESCE(dashboard_users.accepted_at,now()),metadata=EXCLUDED.metadata,
              disabled_at=NULL,updated_at=now()
            """,
            (
                row["user_id"], COMPANY, row["email"], row["tester"], row["phone"],
                legacy.dashboard_password_hash(row["password"]),
                Json({
                    "provisioner": MARKER,
                    "synthetic_only": True,
                    "closed_test_account": True,
                    "credential_expiry": "until_production_access_approved",
                }),
            ),
        )
    # Employee directory reads are grant-only in the frozen permission model.
    # Remove any prior synthetic grants, then add exactly employees.read; the
    # ordinary hr_manager role still supplies all other operational HR access.
    cur.execute(
        "DELETE FROM dashboard_user_permission_grants WHERE company_code=%s AND user_id = ANY(%s::uuid[])",
        (COMPANY, expected_ids),
    )
    grantor_id = expected_ids[0]
    for user_id in expected_ids:
        cur.execute(
            """
            INSERT INTO dashboard_user_permission_grants
              (company_code,user_id,permission,status,review_reference,
               granted_by_user_id,granted_reason,granted_at,updated_at)
            VALUES (%s,%s,'employees.read','active',%s,%s,%s,now(),now())
            ON CONFLICT (company_code,user_id,permission) DO UPDATE SET
              status='active',review_reference=EXCLUDED.review_reference,
              granted_by_user_id=EXCLUDED.granted_by_user_id,
              granted_reason=EXCLUDED.granted_reason,revoked_at=NULL,updated_at=now()
            """,
            (
                COMPANY,
                user_id,
                MARKER,
                grantor_id,
                "Synthetic closed-test People directory read access",
            ),
        )


def _employees() -> list[dict[str, str]]:
    names = (
        ("Mariam Al-Sabah", "People Operations Manager", "People & Culture"),
        ("Yousef Al-Hamad", "Finance Analyst", "Finance"),
        ("Noor Al-Khaled", "Learning Coordinator", "People & Culture"),
        ("Fahad Al-Ajmi", "Operations Supervisor", "Operations"),
        ("Dana Al-Rashid", "Customer Success Specialist", "Customer Success"),
        ("Ahmed Al-Dosari", "Software Engineer", "Technology"),
        ("Lulwa Al-Mutairi", "Recruiting Specialist", "People & Culture"),
        ("Omar Al-Salem", "Sales Executive", "Sales"),
        ("Hessa Al-Nasser", "Office Administrator", "Operations"),
        ("Khaled Al-Mulla", "Product Designer", "Technology"),
        ("Reem Al-Qattan", "Marketing Specialist", "Marketing"),
        ("Ali Al-Shammari", "Support Associate", "Customer Success"),
    )
    return [
        {
            "employee_key": f"{COMPANY}-EMP-{index:03d}",
            "phone": f"9650010{index:04d}",
            "name": name,
            "title": title,
            "department": department,
            "email": f"employee{index:02d}@closed-test.synthetic.invalid",
        }
        for index, (name, title, department) in enumerate(names, 1)
    ]


def _upsert_employees(cur: Any) -> None:
    for row in _employees():
        profile = {
            "department": row["department"],
            "employment_type": "full_time",
            "location": "Kuwait City",
            "preferred_locale": "en",
            "synthetic": True,
            "provisioner": MARKER,
        }
        cur.execute(
            """
            INSERT INTO employees
              (employee_key,phone,company_code,name,email,position_title,hire_date,start_date,
               onboarding_status,documents_pending,documents_complete,compliance_status,profile,raw_json,
               employment_status,app_access_enabled,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'in_progress',1,2,'attention',%s,%s,
                    'active',false,now(),now())
            ON CONFLICT (employee_key) DO UPDATE SET
              phone=EXCLUDED.phone,company_code=EXCLUDED.company_code,name=EXCLUDED.name,
              email=EXCLUDED.email,position_title=EXCLUDED.position_title,
              employment_status='active',app_access_enabled=false,profile=EXCLUDED.profile,
              raw_json=EXCLUDED.raw_json,updated_at=now()
            """,
            (
                row["employee_key"], row["phone"], COMPANY, row["name"], row["email"],
                row["title"], date(2024, 7, 1), date(2024, 7, 1), Json(profile), Json(profile),
            ),
        )


def _seed_operational_data(cur: Any) -> None:
    today = date.today()
    now = datetime.now(timezone.utc)
    cur.execute("DELETE FROM hr_tasks WHERE company_code=%s AND metadata->>'provisioner'=%s", (COMPANY, MARKER))
    for index, employee in enumerate(_employees()):
        key = employee["employee_key"]
        cur.execute(
            "DELETE FROM shift_assignments WHERE company_code=%s AND employee_key=%s AND metadata->>'provisioner'=%s",
            (COMPANY, key, MARKER),
        )
        for delta in (0, 1, 2):
            cur.execute(
                """
                INSERT INTO shift_assignments
                  (company_code,employee_key,employee_phone,employee_name,shift_date,start_time,end_time,
                   timezone,role,location,status,notes,metadata,created_by_phone)
                VALUES (%s,%s,%s,%s,%s,'09:00','17:00','Asia/Kuwait',%s,
                        'OctoHR Closed Test Office','scheduled','Synthetic closed-test schedule',%s,%s)
                """,
                (
                    COMPANY, key, employee["phone"], employee["name"], today + timedelta(days=delta),
                    employee["title"], Json({"provisioner": MARKER}), ACTOR_PHONE,
                ),
            )
        cur.execute(
            "DELETE FROM attendance_records WHERE company_code=%s AND employee_key=%s AND metadata->>'provisioner'=%s",
            (COMPANY, key, MARKER),
        )
        for days_ago in (1, 2, 3):
            day = today - timedelta(days=days_ago)
            check_in = datetime.combine(day, time(9, 0), timezone.utc) + timedelta(minutes=index % 5)
            cur.execute(
                """
                INSERT INTO attendance_records
                  (company_code,employee_key,employee_phone,employee_name,attendance_date,
                   scheduled_start,scheduled_end,check_in_at,check_out_at,status,late_minutes,
                   metadata,created_by_phone)
                VALUES (%s,%s,%s,%s,%s,'09:00','17:00',%s,%s,'present',%s,%s,%s)
                ON CONFLICT (company_code,employee_key,attendance_date,shift_id) DO NOTHING
                """,
                (
                    COMPANY, key, employee["phone"], employee["name"], day,
                    check_in, check_in + timedelta(hours=8), index % 5,
                    Json({"provisioner": MARKER}), ACTOR_PHONE,
                ),
            )
        cur.execute(
            "DELETE FROM leave_requests WHERE company_code=%s AND employee_key=%s AND metadata->>'provisioner'=%s",
            (COMPANY, key, MARKER),
        )
        leave_status = "approved" if index % 3 else "pending"
        cur.execute(
            """
            INSERT INTO leave_requests
              (company_code,employee_key,employee_phone,employee_name,start_date,end_date,
               leave_type,status,reason,decision_note,requested_by_phone,decided_by_phone,
               requested_at,decided_at,metadata)
            VALUES (%s,%s,%s,%s,%s,%s,'annual',%s,'Synthetic annual leave',%s,%s,%s,%s,%s,%s)
            """,
            (
                COMPANY, key, employee["phone"], employee["name"],
                today + timedelta(days=10 + index), today + timedelta(days=11 + index),
                leave_status, "Approved for synthetic testing" if leave_status == "approved" else None,
                employee["phone"], ACTOR_PHONE if leave_status == "approved" else None,
                now - timedelta(days=2), now - timedelta(days=1) if leave_status == "approved" else None,
                Json({"provisioner": MARKER}),
            ),
        )
        cur.execute("DELETE FROM onboarding_items WHERE company_code=%s AND employee_key=%s", (COMPANY, key))
        for item_id, label, item_type, document_type, status in (
            ("profile-details", "Confirm profile details", "task", None, "complete"),
            ("civil-id", "Upload Civil ID", "document", "civil_id", "complete"),
            ("bank-details", "Confirm bank details", "task", None, "pending"),
        ):
            cur.execute(
                """
                INSERT INTO onboarding_items
                  (company_code,employee_key,item_id,label,item_type,document_type,required,status)
                VALUES (%s,%s,%s,%s,%s,%s,true,%s)
                """,
                (COMPANY, key, item_id, label, item_type, document_type, status),
            )
    tasks = (
        ("Review pending leave requests", "Two synthetic requests need an HR decision.", "leave_review", "high"),
        ("Complete onboarding document review", "Review the synthetic Civil ID and bank details.", "onboarding_review", "normal"),
        ("Confirm attendance exceptions", "Review yesterday's synthetic attendance records.", "attendance_review", "normal"),
        ("Prepare interview shortlist", "Review applicants for the synthetic Customer Success role.", "hiring_review", "normal"),
    )
    for title, detail, task_type, priority in tasks:
        cur.execute(
            """
            INSERT INTO hr_tasks
              (company_code,task_type,source,title,detail,status,priority,metadata,created_at,updated_at)
            VALUES (%s,%s,'closed_test',%s,%s,'open',%s,%s,now(),now())
            """,
            (COMPANY, task_type, title, detail, priority, Json({"provisioner": MARKER, "synthetic_only": True})),
        )


def _seed_documents(cur: Any) -> None:
    pdf = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 72>>stream\nBT 72 720 Td (Synthetic OctoHR closed test document) Tj ET\nendstream endobj\n"
        b"trailer<</Root 1 0 R/Size 5>>\n%%EOF\n"
    )
    checksum = hashlib.sha256(pdf).hexdigest()
    for employee in _employees()[:5]:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="octohr-closed-test-", suffix=".pdf", delete=False) as handle:
                handle.write(pdf)
                temporary = Path(handle.name)
            stored = legacy.store_subject_file(
                company_code=COMPANY,
                owner_phone=employee["phone"],
                subject_type="employee",
                subject_key=employee["employee_key"],
                file_kind="employee_document",
                source_path=temporary,
                mime_type="application/pdf",
                checksum=checksum,
            )
            if not stored.get("ok"):
                raise RuntimeError("closed_test_document_storage_failed")
            legacy.upsert_file_registry(
                cur,
                company_code=COMPANY,
                owner_phone=employee["phone"],
                subject_type="employee",
                subject_key=employee["employee_key"],
                file_kind="employee_document",
                document_type="employment_letter",
                original_filename="synthetic-employment-letter.pdf",
                source_path=None,
                local_path=str((stored.get("metadata") or {}).get("local_path") or "") or None,
                storage_result=stored,
                metadata={"provisioner": MARKER, "synthetic_only": True, "label": "Employment letter"},
            )
        finally:
            if temporary and temporary.exists():
                temporary.unlink()


def _seed_performance(cur: Any, *, reconcile: bool) -> None:
    performance.enable_company_performance_goals(cur, company_code=COMPANY, actor_phone=ACTOR_PHONE, reason=MARKER)
    performance_reviews.enable_company_performance_reviews(
        cur,
        company_code=COMPANY,
        actor_phone=ACTOR_PHONE,
        reason=MARKER,
        goals_integration_enabled=True,
        competencies_enabled=False,
        review_360_enabled=False,
    )
    employee = _employees()[0]
    cur.execute(
        "SELECT 1 FROM perf_objectives WHERE company_code=%s AND title_en=%s",
        (COMPANY, "Improve the employee onboarding experience"),
    )
    if not cur.fetchone():
        measure = performance.create_measure_definition(
            cur,
            company_code=COMPANY,
            actor_phone=ACTOR_PHONE,
            name_en="Employee onboarding satisfaction",
            unit="percent",
            direction="higher_is_better",
            baseline=76,
            target=92,
            period_start=date.today().replace(month=1, day=1),
            period_end=date.today().replace(month=12, day=31),
            owner_employee_key=employee["employee_key"],
        )
        if not measure.get("ok"):
            raise RuntimeError(f"closed_test_performance_measure:{measure.get('error')}")
        objective = performance.create_objective(
            cur,
            company_code=COMPANY,
            actor_phone=ACTOR_PHONE,
            title_en="Improve the employee onboarding experience",
            title_ar="تحسين تجربة انضمام الموظفين",
            scope="individual",
            owner_employee_key=employee["employee_key"],
            period_start=date.today().replace(month=1, day=1),
            period_end=date.today().replace(month=12, day=31),
        )
        if not objective.get("ok"):
            raise RuntimeError(f"closed_test_performance_objective:{objective.get('error')}")

    cycle_name = "Closed Test Performance Review"
    cur.execute(
        "SELECT 1 FROM perf_review_cycles WHERE company_code=%s AND name_en=%s",
        (COMPANY, cycle_name),
    )
    if cur.fetchone():
        return
    scale = performance_reviews.create_rating_scale(
        cur,
        company_code=COMPANY,
        actor_phone=ACTOR_PHONE,
        name_en="Closed Test Five Point Scale",
        name_ar="مقياس الاختبار المغلق من خمس نقاط",
        points=[
            {"value": 1, "label_en": "Needs improvement", "label_ar": "يحتاج إلى تحسين"},
            {"value": 2, "label_en": "Developing", "label_ar": "قيد التطوير"},
            {"value": 3, "label_en": "Meets expectations", "label_ar": "يلبي التوقعات"},
            {"value": 4, "label_en": "Exceeds expectations", "label_ar": "يفوق التوقعات"},
            {"value": 5, "label_en": "Exceptional", "label_ar": "استثنائي"},
        ],
        reason=MARKER,
    )
    template = performance_reviews.create_review_template(
        cur,
        company_code=COMPANY,
        actor_phone=ACTOR_PHONE,
        name_en="Closed Test Manager Review",
        name_ar="تقييم المدير للاختبار المغلق",
        include_goals=True,
        reason=MARKER,
    )
    if not scale.get("ok") or not template.get("ok"):
        raise RuntimeError("closed_test_performance_review_setup_failed")
    cycle = performance_reviews.create_cycle(
        cur,
        company_code=COMPANY,
        actor_phone=ACTOR_PHONE,
        name_en=cycle_name,
        name_ar="دورة تقييم الاختبار المغلق",
        period_start=date.today().replace(month=1, day=1),
        period_end=date.today().replace(month=12, day=31),
        due_self=date.today() + timedelta(days=14),
        due_manager=date.today() + timedelta(days=21),
        template_id=str(template["template"]["template_id"]),
        scale_id=str(scale["scale"]["scale_id"]),
        reason=MARKER,
    )
    if not cycle.get("ok"):
        raise RuntimeError(f"closed_test_performance_cycle:{cycle.get('error')}")
    cycle_id = str(cycle["cycle"]["cycle_id"])
    configured = performance_reviews.configure_cycle(
        cur,
        company_code=COMPANY,
        cycle_id=cycle_id,
        actor_phone=ACTOR_PHONE,
        participants=[{
            "employee_key": employee["employee_key"],
            "employee_phone": employee["phone"],
            "manager_employee_key": _employees()[3]["employee_key"],
            "manager_phone": ACTOR_PHONE,
        }],
        reason=MARKER,
    )
    if not configured.get("ok"):
        raise RuntimeError(f"closed_test_performance_configure:{configured.get('error')}")
    launched = performance_reviews.launch_cycle(
        cur,
        company_code=COMPANY,
        cycle_id=cycle_id,
        actor_phone=ACTOR_PHONE,
        reason=MARKER,
    )
    if not launched.get("ok"):
        raise RuntimeError(f"closed_test_performance_launch:{launched.get('error')}")


def _ensure_hiring_job() -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM positions WHERE company_code=%s AND position_code='CLOSED-CS-01'",
                (COMPANY,),
            )
            if cur.fetchone():
                return
    prehire_jobs.create_job(
        company=COMPANY,
        db_connect=legacy.db_connect,
        actor_user_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, "tester01.closed-test.octo-hr.com")),
        actor_role="hr_manager",
        # A realistic draft is visible to HR testers without bypassing the
        # frozen publish-readiness/requisition authority.
        as_draft=True,
        payload={
            "position_code": "CLOSED-CS-01",
            "title_en": "Customer Success Specialist",
            "title_ar": "أخصائي نجاح العملاء",
            "description": "Synthetic closed-test vacancy for mobile hiring workflows.",
            "department": "Customer Success",
            "location": "Kuwait City",
            "employment_type": "full_time",
            "work_arrangement": "hybrid",
            "vacancies": 2,
            "visibility": "internal",
            "requirements_en": ["Customer communication", "Arabic and English"],
            "metadata": {"provisioner": MARKER, "synthetic_only": True},
        },
    )


def main() -> int:
    args = _args()
    if args.apply == args.validate_only:
        raise SystemExit("choose exactly one of --apply or --validate-only")
    if args.owner_file is None:
        raise SystemExit("--owner-file is required")
    if args.apply and (args.tester_instructions_file is None or args.report_file is None):
        raise SystemExit("--apply requires --tester-instructions-file and --report-file")
    if args.apply and not args.reconcile_existing:
        owner = _new_owner_payload()
        _secure_json(args.owner_file, owner)
    elif args.validate_only and not args.owner_file.exists():
        # Validation exercises the exact insert/hash paths inside a rolled-back
        # transaction without leaving credentials or tenant state behind.
        owner = _new_owner_payload()
    else:
        owner = _load_owner(args.owner_file)
    with legacy.db_connect() as conn:
        try:
            with conn.cursor() as cur:
                _company_guard(cur, reconcile=args.reconcile_existing)
                _upsert_company(cur)
                _upsert_users(cur, owner)
                _upsert_employees(cur)
                _seed_operational_data(cur)
                if args.apply:
                    _seed_documents(cur)
                _seed_performance(cur, reconcile=args.reconcile_existing)
            if args.validate_only:
                conn.rollback()
            else:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
    if args.validate_only:
        print(json.dumps({"ok": True, "validation_only": True, "company_code": COMPANY}, sort_keys=True))
        return 0
    _ensure_hiring_job()
    _secure_write(args.tester_instructions_file, _instructions(owner))
    report = {
        "ok": True,
        "company_code": COMPANY,
        "identity_count": ACCOUNT_COUNT,
        "identity_role": "hr_manager",
        "normal_hr_authentication": True,
        "mfa_policy": "disabled_for_synthetic_tenant_only",
        "synthetic_only": True,
        "employee_count": len(_employees()),
        "modules": list(MODULES),
        "settings_manage": False,
        "users_manage": False,
        "superadmin": False,
        "passwords_in_report": False,
        "credentials_expire_after_14_days": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _secure_json(args.report_file, report)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
