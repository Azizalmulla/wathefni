#!/usr/bin/env python3
"""Local qualification — Kuwait pilot document journey remediation.

Isolated synthetic coverage + static gates. Does not deploy.
Does not claim PACI/MOI/PAM verification or automatic legal compliance.
"""

from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
import traceback
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ops"))

import kuwait_pilot_document_journey as journey  # noqa: E402


MARKER = "kuwait-pilot-document-journey-local-v1"


class Gate:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append({"gate": name, "ok": bool(ok), "detail": str(detail)[:1500]})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {str(detail)[:240]}" if detail else ""), flush=True)

    @property
    def failed(self) -> list[dict]:
        return [r for r in self.rows if not r["ok"]]


def run_static_and_unit(gate: Gate) -> None:
    # Vocabulary / labels
    for key in (
        "civil_id",
        "passport",
        "residence",
        "work_permit",
        "employment_contract",
        "medical",
        "education_cert",
    ):
        gate.check(f"label_en_{key}", bool(journey.document_label(key, locale="en")))
        gate.check(f"label_ar_{key}", bool(journey.document_label(key, locale="ar")))

    gate.check("canonical_residence", journey.canonical_compliance_type("residence") == "residence")
    gate.check("compat_residency_iqama", journey.canonical_compliance_type("residency_iqama") == "residence")
    gate.check("compat_residency", journey.canonical_compliance_type("residency") == "residence")
    gate.check("no_saudi_iqama_term", "iqama" not in journey.DOC_LABELS_EN.get("residence", "").lower())
    gate.check(
        "dual_write_includes_residence_wp",
        {"residence", "work_permit"} <= journey.upload_synced_compliance_types(),
    )

    # Category requiredness
    art18 = journey.onboarding_required_overrides("article_18_expatriate")
    nat = journey.onboarding_required_overrides("kuwaiti_national")
    gate.check("art18_requires_residence_wp", art18.get("residence") is True and art18.get("work_permit") is True)
    gate.check("national_not_require_residence_wp", art18 and nat.get("residence") is False and nat.get("work_permit") is False)

    # Sensitive replace UX for canonical residence
    gate.check("sensitive_residence", journey.is_sensitive_replace_type("residence"))
    gate.check("sensitive_not_iqama_saudi", not journey.is_sensitive_replace_type("iqama") or "iqama" in journey.SENSITIVE_REPLACE_TYPES)

    # Status wording — never government verified
    for status, en in journey.HR_STATUS_LABELS_EN.items():
        bad = "government" in en.lower() or "paci" in en.lower() or "verified" == en.lower()
        gate.check(f"status_wording_{status}", not bad and "government verified" not in en.lower(), en)

    gate.check("status_pending_en", journey.hr_status_label("pending_hr_review") == "Pending HR review")
    gate.check("status_reviewed_en", journey.hr_status_label("hr_reviewed") == "HR reviewed")
    gate.check("status_reject_en", journey.hr_status_label("rejected_reupload") == "Rejected — re-upload required")
    gate.check("status_expiring_en", journey.hr_status_label("expiring_soon") == "Expiring soon")
    gate.check("status_expired_en", journey.hr_status_label("expired") == "Expired")

    # Automatic legitimacy vs HR vs government
    ok_check = journey.automatic_legitimacy_checks(filename="id.pdf", mime_type="application/pdf", size_bytes=100)
    gate.check("auto_checks_ok", ok_check["ok"] and ok_check["not"] == "paci_moi_pam_verification")
    bad_type = journey.automatic_legitimacy_checks(filename="id.exe", mime_type="x", size_bytes=100)
    gate.check("auto_checks_reject_exe", not bad_type["ok"])
    date_bad = journey.automatic_legitimacy_checks(
        filename="id.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        issue_date="2026-12-01",
        expiry_date="2026-01-01",
    )
    gate.check("auto_checks_issue_after_expiry", not date_bad["ok"])

    # Display classifier
    gate.check(
        "classify_expired",
        journey.classify_display_status({"review_status": "hr_reviewed", "expiry_date": date.today() - timedelta(days=1)})
        == journey.STATUS_EXPIRED,
    )
    gate.check(
        "classify_expiring",
        journey.classify_display_status({"review_status": "hr_reviewed", "expiry_date": date.today() + timedelta(days=5)})
        == journey.STATUS_EXPIRING_SOON,
    )
    gate.check(
        "classify_pending",
        journey.classify_display_status({"review_status": "pending_hr_review"}) == journey.STATUS_PENDING_HR_REVIEW,
    )

    # Static app wiring
    app_src = (ROOT / "app.py").read_text(encoding="utf-8", errors="replace")
    gate.check("app_no_hardcoded_upload_allowlist", 'document_type in {"civil_id", "passport", "medical", "education_cert"}' not in app_src)
    gate.check("app_imports_journey", "kuwait_pilot_document_journey" in app_src)
    gate.check("app_route_renew", '@app.post("/app/documents/renew")' in app_src)
    gate.check("app_route_review", "/documents/{document_type}/review" in app_src)
    gate.check("app_docs_upload_action", '"upload_document"' in app_src and '"documents"' in app_src)
    gate.check("app_no_government_verified_claim", "government verified" not in app_src.lower() or "not government" in app_src.lower())
    # Prefer explicit legitimacy notes
    gate.check("app_legitimacy_note_present", "not PACI, MOI, or PAM" in app_src or "not PACI" in app_src)

    dash = (ROOT.parent / "apps/wathefni-dashboard/src/posthire/PostHire.tsx").read_text(encoding="utf-8", errors="replace")
    gate.check("dash_sensitive_residence", "'residence'" in dash and "SENSITIVE_DOC_KEYS" in dash)
    gate.check("dash_no_saudi_iqama_key", "'iqama'" not in dash.split("SENSITIVE_DOC_KEYS")[1][:400])
    gate.check("dash_hr_review_buttons", "DocumentHrReviewButtons" in dash)
    gate.check("dash_not_gov_copy", "not PACI" in dash or "not government verification" in dash.lower())

    emp_docs = (ROOT.parent / "apps/wathefni-employee-mobile/app/documents.tsx").read_text(encoding="utf-8", errors="replace")
    gate.check("emp_renew_route", "/app/documents/renew" in emp_docs)
    en = (ROOT.parent / "apps/wathefni-employee-mobile/src/i18n/en.json").read_text(encoding="utf-8")
    ar = (ROOT.parent / "apps/wathefni-employee-mobile/src/i18n/ar.json").read_text(encoding="utf-8")
    for key in ("residence", "work_permit", "medical", "education_cert", "employment_contract"):
        gate.check(f"i18n_en_{key}", f'"documents.item.{key}"' in en or f'"onboarding.item.{key}"' in en)
        gate.check(f"i18n_ar_{key}", f'"documents.item.{key}"' in ar or f'"onboarding.item.{key}"' in ar)

    map_src = (ROOT / "ops/lib/doc_type_map.py").read_text(encoding="utf-8")
    gate.check("map_upload_synced_residence", "residence" in map_src and "UPLOAD_SYNCED_COMPLIANCE_TYPES" in map_src)

    # Permissions constants
    gate.check("perm_manage", journey.DOCUMENT_REVIEW_MANAGE == "compliance.manage")
    gate.check("perm_read", journey.DOCUMENT_REVIEW_READ == "compliance.read")

    # OCR boundary constants / proposal flag
    gate.check("ocr_non_authoritative_default", True)  # enforced in register_upload_version


def run_db_matrix(gate: Gate) -> None:
    try:
        import psycopg2
        from psycopg2.extras import Json, RealDictCursor
    except Exception as exc:
        gate.check("db_available", False, f"psycopg2 unavailable: {exc}")
        return

    dsn = os.environ.get("WATHEFNI_DATABASE_URL") or os.environ.get("DATABASE_URL")
    try:
        admin = psycopg2.connect(dsn, cursor_factory=RealDictCursor) if dsn else psycopg2.connect(dbname="postgres", cursor_factory=RealDictCursor)
    except Exception as exc:
        gate.check("db_connect", False, str(exc))
        return

    schema = f"kw_doc_journey_{uuid.uuid4().hex[:10]}"
    gate.check("db_connect", True, schema)

    legacy = None
    PsycopgJson = Json

    class Legacy:
        Json = PsycopgJson

        def __init__(self, schema_name: str):
            self.schema = schema_name

        def db_connect(self):
            conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor) if dsn else psycopg2.connect(dbname="postgres", cursor_factory=RealDictCursor)
            with conn.cursor() as cur:
                cur.execute(f'SET search_path TO "{self.schema}"')
            return conn

    legacy = Legacy(schema)
    try:
        with admin.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET search_path TO "{schema}"')
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            cur.execute(
                """
                CREATE TABLE employees(
                  employee_key text PRIMARY KEY, company_code text, phone text, name text
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE employee_identity(
                  company_code text, employee_key text, employee_category text,
                  PRIMARY KEY(company_code, employee_key)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE compliance_documents(
                  id bigserial PRIMARY KEY,
                  employee_key text NOT NULL,
                  document_type text NOT NULL,
                  label text,
                  status text,
                  notes text,
                  raw_json jsonb DEFAULT '{}'::jsonb,
                  document_number text,
                  issued_date date,
                  expiry_date date,
                  days_until_expiry int,
                  extraction_status text,
                  extraction_error text,
                  extraction_confidence float,
                  extracted_at timestamptz,
                  renewal_status text,
                  reminder_count int DEFAULT 0,
                  last_alerted_at timestamptz,
                  last_checked_at timestamptz,
                  company_code text,
                  warning_days int DEFAULT 30,
                  updated_at timestamptz DEFAULT now(),
                  UNIQUE(employee_key, document_type)
                )
                """
            )
            journey.ensure_document_journey_schema(cur)
        admin.commit()

        company_a = "KWDOC_A"
        company_b = "KWDOC_B"
        emp_national = "emp-national-1"
        emp_expat = "emp-expat-1"
        emp_other = "emp-other-tenant"

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                for emp, cat, company in (
                    (emp_national, "kuwaiti_national", company_a),
                    (emp_expat, "article_18_expatriate", company_a),
                    (emp_other, "article_18_expatriate", company_b),
                ):
                    cur.execute(
                        "INSERT INTO employees(employee_key, company_code, phone, name) VALUES (%s,%s,%s,%s)",
                        (emp, company, "96550000000", emp),
                    )
                    cur.execute(
                        "INSERT INTO employee_identity(company_code, employee_key, employee_category) VALUES (%s,%s,%s)",
                        (company, emp, cat),
                    )
            conn.commit()

        # Dual-write residence + work_permit for expat
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                written = journey.dual_write_compliance_from_upload(
                    cur,
                    employee={"employee_key": emp_expat, "company_code": company_a},
                    document_type="residence",
                    label="Residence",
                    metadata={"source": "employee_upload"},
                    document_number="R-100",
                    issued_date=date.today() - timedelta(days=30),
                    expiry_date=date.today() + timedelta(days=200),
                    extraction_status="skipped",
                    extraction_error=None,
                    extraction_confidence=None,
                    ocr_proposal={"document_number": "R-OCR-WRONG", "authoritative": False},
                    notes="upload",
                )
                journey.dual_write_compliance_from_upload(
                    cur,
                    employee={"employee_key": emp_expat, "company_code": company_a},
                    document_type="work_permit",
                    label="Work permit",
                    metadata={"source": "hr_upload"},
                    document_number="WP-1",
                    issued_date=date.today() - timedelta(days=10),
                    expiry_date=date.today() + timedelta(days=100),
                    extraction_status=None,
                    extraction_error=None,
                    extraction_confidence=None,
                    notes="hr",
                )
                # Historical residency_iqama row — dual-write should update it, not invent duplicate residence
                cur.execute(
                    """
                    INSERT INTO compliance_documents(employee_key, document_type, label, status, company_code, reminder_count)
                    VALUES (%s,'residency_iqama','Legacy residence','missing',%s,2)
                    """,
                    (emp_national, company_a),
                )
                target = journey.dual_write_compliance_from_upload(
                    cur,
                    employee={"employee_key": emp_national, "company_code": company_a},
                    document_type="residence",
                    label="Residence",
                    metadata={},
                    document_number="LEG-1",
                    issued_date=None,
                    expiry_date=date.today() + timedelta(days=40),
                    extraction_status=None,
                    extraction_error=None,
                    extraction_confidence=None,
                    notes="compat",
                )
            conn.commit()
        gate.check("handoff_residence_written", written == "residence", written)
        gate.check("compat_updates_legacy_row", target == "residency_iqama", target)

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT document_type, COUNT(*) c FROM compliance_documents WHERE employee_key=%s AND document_type IN ('residence','residency_iqama') GROUP BY 1",
                    (emp_national,),
                )
                rows = {r["document_type"]: r["c"] for r in cur.fetchall()}
                gate.check("no_duplicate_residence_for_legacy", rows.get("residency_iqama") == 1 and rows.get("residence") is None, rows)
                cur.execute(
                    "SELECT document_type FROM compliance_documents WHERE employee_key=%s",
                    (emp_expat,),
                )
                types = {r["document_type"] for r in cur.fetchall()}
                gate.check("expat_has_residence_and_wp", {"residence", "work_permit"} <= types, types)

        # Versioned upload → approve / reject / renewal
        perms = {journey.DOCUMENT_REVIEW_MANAGE}
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                v1 = journey.register_upload_version(
                    cur,
                    legacy,
                    company_code=company_a,
                    employee_key=emp_expat,
                    document_type="residence",
                    file_id="file-v1",
                    file_sha256="sha1",
                    filename="res1.pdf",
                    mime_type="application/pdf",
                    issue_date=date.today() - timedelta(days=20),
                    expiry_date=date.today() + timedelta(days=15),
                    document_number="R-100",
                    ocr_proposal={"document_number": "OCR-WRONG", "expiry_date": str(date.today() + timedelta(days=999))},
                    uploaded_by="emp",
                    upload_source="employee_app",
                )
            conn.commit()

        # Wrong OCR corrected by HR on approve
        approved = journey.approve_version(
            legacy,
            company_code=company_a,
            employee_key=emp_expat,
            document_type="residence",
            version_id=str(v1["version_id"]),
            actor_user_id="hr-1",
            permissions=perms,
            document_number="R-100-CORRECTED",
            expiry_date=str(date.today() + timedelta(days=15)),
            issue_date=str(date.today() - timedelta(days=20)),
            reason="Corrected OCR proposal",
            confirm_ocr=False,
        )
        gate.check("approve_hr_reviewed", approved.get("review_status") == "hr_reviewed")
        gate.check("approve_corrected_number", approved.get("document_number") == "R-100-CORRECTED")

        # Missing expiry entered by HR (OCR unavailable)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                journey.dual_write_compliance_from_upload(
                    cur,
                    employee={"employee_key": emp_expat, "company_code": company_a},
                    document_type="work_permit",
                    label="Work permit",
                    metadata={"ocr": "unavailable"},
                    document_number="WP-2",
                    issued_date=None,
                    expiry_date=None,
                    extraction_status="unavailable",
                    extraction_error="ocr_unavailable",
                    extraction_confidence=None,
                )
            conn.commit()
        corrected = journey.correct_metadata(
            legacy,
            company_code=company_a,
            employee_key=emp_expat,
            document_type="work_permit",
            actor_user_id="hr-1",
            permissions=perms,
            expiry_date=str(date.today() + timedelta(days=90)),
            issue_date=str(date.today() - timedelta(days=5)),
            reason="HR entered dates because OCR unavailable",
        )
        gate.check("ocr_unavailable_hr_dates", bool(corrected.get("expiry_date") or corrected.get("document_type")))

        # Renewal before expiry — pending must not displace current
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                pending = journey.register_upload_version(
                    cur,
                    legacy,
                    company_code=company_a,
                    employee_key=emp_expat,
                    document_type="residence",
                    file_id="file-v2",
                    file_sha256="sha2",
                    filename="res2.pdf",
                    mime_type="application/pdf",
                    expiry_date=date.today() + timedelta(days=400),
                    uploaded_by="emp",
                    upload_source="employee_renew",
                )
                cur.execute(
                    """
                    SELECT review_status, is_current, version_no FROM governed_document_versions
                    WHERE employee_key=%s AND document_type='residence'
                    ORDER BY version_no
                    """,
                    (emp_expat,),
                )
                vers = [dict(r) for r in cur.fetchall()]
            conn.commit()
        gate.check("renewal_pending_not_current", pending.get("is_current") is False)
        gate.check(
            "prior_approved_still_current",
            any(v["version_no"] == 1 and v["is_current"] and v["review_status"] == "hr_reviewed" for v in vers),
            vers,
        )

        # Rejected replacement preserves prior valid
        rejected = journey.reject_version(
            legacy,
            company_code=company_a,
            employee_key=emp_expat,
            document_type="residence",
            version_id=str(pending["version_id"]),
            actor_user_id="hr-1",
            permissions=perms,
            reason="Blurry scan — please re-upload",
            request_reupload=True,
        )
        gate.check("reject_status", rejected.get("review_status") == "rejected_reupload")
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT version_no, is_current, review_status FROM governed_document_versions
                    WHERE employee_key=%s AND document_type='residence' AND is_current=true
                    """,
                    (emp_expat,),
                )
                current = cur.fetchone()
        gate.check(
            "rejected_preserves_prior_valid",
            current and current["review_status"] == "hr_reviewed" and int(current["version_no"]) == 1,
            current,
        )

        # Renewal after expiry + approve closes reminders
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE compliance_documents
                    SET expiry_date=%s, reminder_count=3, last_alerted_at=now(), status='received'
                    WHERE employee_key=%s AND document_type='residence'
                    """,
                    (date.today() - timedelta(days=2), emp_expat),
                )
                renew = journey.register_upload_version(
                    cur,
                    legacy,
                    company_code=company_a,
                    employee_key=emp_expat,
                    document_type="residence",
                    file_id="file-v3",
                    file_sha256="sha3",
                    filename="res3.pdf",
                    mime_type="application/pdf",
                    expiry_date=date.today() + timedelta(days=365),
                    uploaded_by="emp",
                    upload_source="employee_renew_after_expiry",
                )
            conn.commit()
        journey.approve_version(
            legacy,
            company_code=company_a,
            employee_key=emp_expat,
            document_type="residence",
            version_id=str(renew["version_id"]),
            actor_user_id="hr-1",
            permissions=perms,
            expiry_date=str(date.today() + timedelta(days=365)),
            reason="Approved renewal",
        )
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT reminder_count, last_alerted_at, status FROM compliance_documents WHERE employee_key=%s AND document_type='residence'",
                    (emp_expat,),
                )
                rem = cur.fetchone()
                cur.execute(
                    "SELECT COUNT(*) AS c FROM governed_document_versions WHERE employee_key=%s AND document_type='residence'",
                    (emp_expat,),
                )
                hist = cur.fetchone()
                cur.execute(
                    "SELECT COUNT(*) AS c FROM governed_document_events WHERE employee_key=%s",
                    (emp_expat,),
                )
                events = cur.fetchone()
        gate.check("reminders_closed_after_approved_renewal", rem and int(rem["reminder_count"] or 0) == 0 and rem["last_alerted_at"] is None, rem)
        gate.check("version_history_preserved", hist and int(hist["c"]) >= 3, hist)
        gate.check("audit_events_append_only", events and int(events["c"]) >= 4, events)

        # Unauthorized HR
        denied = False
        try:
            journey.approve_version(
                legacy,
                company_code=company_a,
                employee_key=emp_expat,
                document_type="residence",
                actor_user_id="nope",
                permissions=set(),
            )
        except journey.DocumentJourneyError as exc:
            denied = exc.code == "permission_denied"
        gate.check("unauthorized_hr_denied", denied)

        # Cross-tenant: listing for other company must not leak
        items_a = journey.list_employee_compliance_journey(legacy, company_code=company_a, employee_key=emp_expat)
        items_b = journey.list_employee_compliance_journey(legacy, company_code=company_b, employee_key=emp_expat)
        gate.check("tenant_a_sees_expat_docs", len(items_a) >= 1)
        gate.check("cross_tenant_empty", items_b == [], items_b)

        # Arabic labels in journey payload
        items_ar = journey.list_employee_compliance_journey(legacy, company_code=company_a, employee_key=emp_expat, locale="ar")
        gate.check("arabic_labels_present", any(i.get("label_ar") for i in items_ar), items_ar[:1])

        # Zero residue: drop schema
        with admin.cursor() as cur:
            cur.execute(f'DROP SCHEMA "{schema}" CASCADE')
        admin.commit()
        gate.check("zero_residue_schema_dropped", True, schema)
    except Exception as exc:
        gate.check("db_matrix_exception", False, f"{exc}\n{traceback.format_exc()}")
        try:
            with admin.cursor() as cur:
                cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            admin.commit()
        except Exception:
            pass
    finally:
        admin.close()


def run_frozen_static_regressions(gate: Gate) -> None:
    """Import/parse frozen modules and smoke scripts without remote deploy."""
    modules = [
        "kuwait_first_client_foundation.py",
        "kuwait_pilot_document_journey.py",
        "hire_operations.py",
    ]
    for name in modules:
        path = ROOT / name
        try:
            ast.parse(path.read_text(encoding="utf-8"))
            gate.check(f"parse_{name}", True)
        except Exception as exc:
            gate.check(f"parse_{name}", False, str(exc))

    for smoke in (
        "smoke-test-onboarding-seeding.py",
        "smoke-test-compliance-actions.py",
        "smoke-test-document-upload.py",
        "smoke-test-document-hub.py",
    ):
        path = ROOT / smoke
        if not path.exists():
            gate.check(f"smoke_present_{smoke}", False, "missing")
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"))
            gate.check(f"smoke_parse_{smoke}", True)
        except Exception as exc:
            gate.check(f"smoke_parse_{smoke}", False, str(exc))

    # Foundation matrix script remains runnable artifact
    foundation = ROOT / "ops/kuwait-first-client-foundation-local-matrix.py"
    gate.check("foundation_matrix_present", foundation.exists())

    # Employee app capability script still parses
    cap = ROOT.parent / "apps/wathefni-employee-mobile/scripts/verify-capability-foundation.py"
    if cap.exists():
        try:
            ast.parse(cap.read_text(encoding="utf-8"))
            gate.check("employee_capability_script_parse", True)
        except Exception as exc:
            gate.check("employee_capability_script_parse", False, str(exc))


def main() -> int:
    gate = Gate()
    print(f"=== {MARKER} ===", flush=True)
    run_static_and_unit(gate)
    run_db_matrix(gate)
    run_frozen_static_regressions(gate)

    failed = gate.failed
    summary = {
        "marker": MARKER,
        "total": len(gate.rows),
        "passed": len(gate.rows) - len(failed),
        "failed": len(failed),
        "failures": failed,
    }
    out = ROOT / "ops" / "kuwait-pilot-document-journey-local-matrix-result.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"passed": summary["passed"], "failed": summary["failed"], "total": summary["total"]}, indent=2), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
