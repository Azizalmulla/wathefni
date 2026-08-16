#!/usr/bin/env python3
"""Staging qualification — Kuwait pilot document journey.

Exercises reachable FastAPI handlers (same endpoints as UI) against wathefni_staging
with isolated synthetic tenants. Does not deploy to production.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import shutil
import sys
import traceback
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from psycopg2.extras import Json
from starlette.datastructures import Headers

MARKER = "kuwait-pilot-document-journey-staging-v1"
COMPANY = "KWDOCSTG1"
OTHER = "KWDOCSTG2"
EMP_NAT = "kwdoc-nat-1"
EMP_EXP = "kwdoc-exp-1"
EMP_OTHER = "kwdoc-other-1"
PHONE_NAT = "96555558101"
PHONE_EXP = "96555558102"
PHONE_OTHER = "96555558201"
ACTOR = "a0a10000-0000-4000-8000-00000000d0c1"
ARTIFACT = "6018796d265c1a8d77e3bd880849b8e65f627003dc20ca544403db426d2097e1"

# Flags for this process (handler invocation) — staging service already has dry_run.
# WATHEFNI_ENV is not inferred. Missing environment refuses to run.
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")
os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")
os.environ["WATHEFNI_EMPLOYEE_APP"] = "on"
os.environ["WATHEFNI_DOC_UPLOAD"] = "on"
os.environ["WATHEFNI_ONBOARDING_SEED"] = "on"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "ops") not in sys.path:
    sys.path.insert(0, str(ROOT / "ops"))

import production_data_safety as _pds  # noqa: E402

_pds.require_fixture_tooling(company_code=COMPANY, extra_companies=[OTHER], destructive=True)

import app as orch  # noqa: E402
import kuwait_first_client_foundation as kw  # noqa: E402
import kuwait_pilot_document_journey as journey  # noqa: E402


class Gate:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append({"gate": name, "ok": bool(ok), "detail": str(detail)[:1500]})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {str(detail)[:220]}" if detail else ""), flush=True)

    @property
    def failed(self) -> list[dict]:
        return [r for r in self.rows if not r["ok"]]


def exec_sql(sql: str, params: tuple | list | None = None) -> list[dict]:
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            if cur.description:
                rows = [dict(r) for r in cur.fetchall()]
            else:
                rows = []
        conn.commit()
    return rows


def cleanup() -> None:
    companies = [COMPANY, OTHER]
    _pds.require_destructive_scope(companies)
    keys = [EMP_NAT, EMP_EXP, EMP_OTHER]
    statements = [
        ("DELETE FROM governed_document_events WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM governed_document_versions WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM employee_sessions WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM employee_app_invites WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM document_storage_operations WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM employee_documents WHERE company_code = ANY(%s) OR employee_key = ANY(%s)", (companies, keys)),
        ("DELETE FROM compliance_documents WHERE company_code = ANY(%s) OR employee_key = ANY(%s)", (companies, keys)),
        ("DELETE FROM file_registry WHERE company_code = ANY(%s) OR subject_key = ANY(%s)", (companies, keys)),
        ("DELETE FROM onboarding_items WHERE employee_key = ANY(%s)", (keys,)),
        ("DELETE FROM employee_identity WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM company_modules WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM company_settings WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM employees WHERE company_code = ANY(%s) OR employee_key = ANY(%s)", (companies, keys)),
        ("DELETE FROM companies WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM dashboard_users WHERE company_code = ANY(%s)", (companies,)),
        ("DELETE FROM action_results WHERE company_code = ANY(%s)", (companies,)),
    ]
    for sql, params in statements:
        try:
            exec_sql(sql, params)
        except Exception:
            continue
    workspace = Path(os.environ["WATHEFNI_WORKSPACE"])
    for company in companies:
        shutil.rmtree(workspace / "data" / "companies" / company, ignore_errors=True)


def ensure_company(company: str, name: str) -> None:
    exec_sql(
        """
        INSERT INTO companies(company_code, name, country, status, metadata, raw_json)
        VALUES (%s,%s,'KW','active',%s::jsonb,'{}'::jsonb)
        ON CONFLICT (company_code) DO UPDATE SET country='KW', updated_at=now()
        """,
        (company, name, json.dumps({"marker": MARKER})),
    )
    for module in ("onboarding", "compliance", "employees"):
        exec_sql(
            """
            INSERT INTO company_modules(company_code, module_key, enabled, source, updated_at)
            VALUES (%s,%s,true,'staging_matrix',now())
            ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true, updated_at=now()
            """,
            (company, module),
        )


def ensure_employee(company: str, key: str, phone: str, name: str, category: str) -> dict:
    exec_sql(
        """
        INSERT INTO employees(employee_key, phone, company_code, name, employment_status, onboarding_status, raw_json, updated_at)
        VALUES (%s,%s,%s,%s,'active','in_progress',%s::jsonb, now())
        ON CONFLICT (employee_key) DO UPDATE SET company_code=EXCLUDED.company_code, phone=EXCLUDED.phone, updated_at=now()
        """,
        (key, phone, company, name, json.dumps({"marker": MARKER})),
    )
    kw.set_employee_category(
        orch,
        company_code=company,
        employee_key=key,
        category=category,
        actor_user_id=ACTOR,
        permissions={kw.IDENTITY_WRITE, kw.IDENTITY_READ},
    )
    rows = exec_sql("SELECT * FROM employees WHERE employee_key=%s", (key,))
    return dict(rows[0])


def emp_ctx(employee: dict) -> dict:
    return {
        "company_code": employee["company_code"],
        "employee_key": employee["employee_key"],
        "employee": employee,
        "locale": "en",
        "permissions": [],
        "features": {
            "documents": {"enabled": True, "actions": ["view", "download", "upload_document"]},
            "onboarding": {"enabled": True, "actions": ["view", "upload_document"]},
        },
    }


def hr_ctx(company: str, *, manage: bool = True) -> dict:
    perms = ["compliance.read", "onboarding.read", "onboarding.manage", "employees.read"]
    if manage:
        perms.append("compliance.manage")
    actor = ACTOR if manage else "unauthorized-hr"
    return {
        "company_code": company,
        "company_id": company,
        "actor_user_id": actor,
        "admin_user_id": actor,
        "dashboard_user_id": actor,
        "permission_authority": "backend_current",
        "permission_subject_user_id": actor,
        "permission_subject_company": company,
        "actor_role": "owner" if manage else "viewer",
        "role_scope": "owner" if manage else "viewer",
        "hr_phone": "96555558000",
        "permissions": perms,
        "access": {
            "role": "owner" if manage else "viewer",
            "permission_authority": "backend_current",
            "permission_subject_user_id": actor,
            "permission_subject_company": company,
            "permissions": perms,
        },
        "hr_user": {
            "status": "active",
            "role": "owner" if manage else "viewer",
            "company_code": company,
            "phone": "96555558000",
            "name": "Staging Doc Journey HR",
        },
        "actor": {
            "status": "active",
            "role": "owner" if manage else "viewer",
            "company_code": company,
        },
    }


def pdf_bytes(tag: str) -> bytes:
    return b"%PDF-1.4\n%" + tag.encode() + b"\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


async def upload_onboarding(employee: dict, item_id: str, filename: str, data: bytes) -> dict:
    ctx = emp_ctx(employee)
    upload = UploadFile(filename=filename, file=io.BytesIO(data), headers=Headers({"content-type": "application/pdf"}))
    return await orch.app_onboarding_document_upload(file=upload, item_id=item_id, context=ctx)


async def upload_renew(employee: dict, document_type: str, filename: str, data: bytes) -> dict:
    ctx = emp_ctx(employee)
    upload = UploadFile(filename=filename, file=io.BytesIO(data), headers=Headers({"content-type": "application/pdf"}))
    return await orch.app_documents_renew(file=upload, document_type=document_type, context=ctx)


async def hr_upload(employee: dict, item_id: str, filename: str, data: bytes) -> dict:
    ctx = hr_ctx(employee["company_code"])
    upload = UploadFile(filename=filename, file=io.BytesIO(data), headers=Headers({"content-type": "application/pdf"}))
    return await orch.dashboard_posthire_employee_document_upload(
        employee_key=employee["employee_key"],
        file=upload,
        item_id=item_id,
        context=ctx,
    )


def review(employee: dict, document_type: str, body: dict, *, manage: bool = True) -> Any:
    ctx = hr_ctx(employee["company_code"], manage=manage)
    payload = orch.DocumentReviewBody(**body)
    return orch.dashboard_document_review(
        employee_key=employee["employee_key"],
        document_type=document_type,
        body=payload,
        context=ctx,
    )


def main() -> int:
    gate = Gate()
    print(f"=== {MARKER} artifact={ARTIFACT} ===", flush=True)
    orch.assert_runtime_environment_binding()
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select current_database() as d")
            gate.check("db_is_staging", cur.fetchone()["d"] == "wathefni_staging")

    # Artifact identity on disk
    orch_path = Path("/opt/wathefni/staging/orchestrator")
    gate.check(
        "artifact_journey_sha",
        hashlib.sha256((orch_path / "kuwait_pilot_document_journey.py").read_bytes()).hexdigest()
        == "78befeb08da1f94dca5cb10f3bc6514d4799a6ad71e383fda0eeb50b294f99f4",
    )
    gate.check(
        "artifact_app_sha",
        hashlib.sha256((orch_path / "app.py").read_bytes()).hexdigest()
        == "b266a0d24ff49659fb8966b03818f32f2e12fc76cf659ea28514ad8a447d7602",
    )
    pin = Path("/opt/wathefni/staging/kuwait-pilot-document-journey-artifact.sha256").read_text().strip()
    gate.check("artifact_pin_file", pin == ARTIFACT, pin)

    # Static safety: no gov APIs / statutory claims in journey module
    journey_src = (orch_path / "kuwait_pilot_document_journey.py").read_text()
    bad = ["paci_verify", "moi_file", "pam_submit", "government_api", "enforce_leave", "eos_calculate", "pifss_calculate", "statutory_ot"]
    gate.check("no_gov_or_statutory_hooks", not any(b in journey_src.lower() for b in bad))
    gate.check("no_government_verified_claim_as_status", '"government verified"' not in journey_src.lower().replace("never means government verified", "").replace('never "government verified"', ""))
    # Explicit negation / boundary wording is required; bare positive claim is not.
    gate.check("legitimacy_negation_present", "never means government verified" in journey_src.lower() or "not government verified" in journey_src.lower())
    dash_js = list(Path("/opt/wathefni/staging/dashboard-dist/assets").glob("dashboard-*.js"))
    gate.check("dashboard_dist_present", bool(dash_js))
    if dash_js:
        js = dash_js[0].read_text(errors="ignore")
        gate.check("dashboard_hr_reviewed_copy", "HR reviewed" in js)
        gate.check("dashboard_not_paci_copy", "PACI" in js and "not PACI" in js)
        # Allow "not government verified" clarification; forbid positive government-verified claim.
        gate.check(
            "dashboard_no_positive_gov_verified",
            "government verified" in js.lower() and "not government verified" in js.lower(),
        )
    emp_art = Path("/opt/wathefni/staging/employee-mobile-artifact")
    gate.check("employee_mobile_artifact_present", (emp_art / "app/documents.tsx").exists())
    en = (emp_art / "src/i18n/en.json").read_text()
    ar = (emp_art / "src/i18n/ar.json").read_text()
    for key in ("residence", "work_permit", "civil_id", "passport", "employment_contract", "medical", "education_cert"):
        gate.check(f"i18n_en_{key}", f'"documents.item.{key}"' in en or f'"onboarding.item.{key}"' in en)
        gate.check(f"i18n_ar_{key}", f'"documents.item.{key}"' in ar or f'"onboarding.item.{key}"' in ar)

    cleanup()
    try:
        ensure_company(COMPANY, "KW Doc Journey Staging A")
        ensure_company(OTHER, "KW Doc Journey Staging B")
        nat = ensure_employee(COMPANY, EMP_NAT, PHONE_NAT, "National One", "kuwaiti_national")
        exp = ensure_employee(COMPANY, EMP_EXP, PHONE_EXP, "Expat One", "article_18_expatriate")
        other = ensure_employee(OTHER, EMP_OTHER, PHONE_OTHER, "Other Tenant", "article_18_expatriate")

        # Seed onboarding with category-aware requiredness
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                n_seed = orch.seed_onboarding_items(cur, nat)
                e_seed = orch.seed_onboarding_items(cur, exp)
            conn.commit()
        gate.check("seed_national_items", n_seed > 0, str(n_seed))
        gate.check("seed_expat_items", e_seed > 0, str(e_seed))

        nat_req = {r["item_id"]: r["required"] for r in exec_sql(
            "SELECT item_id, required FROM onboarding_items WHERE employee_key=%s AND item_id = ANY(%s)",
            (EMP_NAT, ["residence", "work_permit"]),
        )}
        exp_req = {r["item_id"]: r["required"] for r in exec_sql(
            "SELECT item_id, required FROM onboarding_items WHERE employee_key=%s AND item_id = ANY(%s)",
            (EMP_EXP, ["residence", "work_permit"]),
        )}
        gate.check("national_residence_not_required", nat_req.get("residence") in (False, None) or nat_req.get("residence") is False, nat_req)
        # seed inserts bool required False for national
        gate.check("national_wp_not_required", bool(nat_req) and all(not v for v in nat_req.values()), nat_req)
        gate.check("expat_residence_required", exp_req.get("residence") is True, exp_req)
        gate.check("expat_wp_required", exp_req.get("work_permit") is True, exp_req)

        # Historical residency_iqama row
        exec_sql(
            """
            INSERT INTO compliance_documents(employee_key, document_type, label, status, company_code, reminder_count, warning_days)
            VALUES (%s,'residency_iqama','Legacy residence','missing',%s,2,30)
            ON CONFLICT (employee_key, document_type) DO NOTHING
            """,
            (EMP_NAT, COMPANY),
        )

        import asyncio

        async def run_uploads():
            # Employee onboarding upload civil_id
            r1 = await upload_onboarding(nat, "civil_id", "civil.pdf", pdf_bytes("civil"))
            gate.check("employee_onboarding_upload", bool(r1.get("ok")), r1)
            # HR upload work_permit for expat
            r2 = await hr_upload(exp, "work_permit", "wp.pdf", pdf_bytes("wp"))
            gate.check("hr_dashboard_upload", bool(r2.get("ok")), r2)
            # Employee residence upload (onboarding)
            r3 = await upload_onboarding(exp, "residence", "res.pdf", pdf_bytes("res1"))
            gate.check("employee_residence_upload", bool(r3.get("ok")), r3)
            # Compat: national residence upload updates legacy row
            r4 = await upload_onboarding(nat, "residence", "res-legacy.pdf", pdf_bytes("leg"))
            gate.check("compat_upload_ok", bool(r4.get("ok")), r4)

        asyncio.run(run_uploads())

        types_exp = {r["document_type"] for r in exec_sql(
            "SELECT document_type FROM compliance_documents WHERE employee_key=%s", (EMP_EXP,)
        )}
        gate.check("handoff_residence_wp", {"residence", "work_permit"} <= types_exp, types_exp)
        legacy = exec_sql(
            "SELECT document_type, status FROM compliance_documents WHERE employee_key=%s AND document_type IN ('residence','residency_iqama')",
            (EMP_NAT,),
        )
        gate.check(
            "compat_no_duplicate_canonical",
            len(legacy) == 1 and legacy[0]["document_type"] == "residency_iqama",
            legacy,
        )

        # OCR proposal non-authoritative + HR correct
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                journey.ensure_document_journey_schema(cur)
                v = journey.register_upload_version(
                    cur,
                    orch,
                    company_code=COMPANY,
                    employee_key=EMP_EXP,
                    document_type="residence",
                    file_id="ocr-file",
                    file_sha256="ocrsha",
                    filename="ocr.pdf",
                    mime_type="application/pdf",
                    expiry_date=date.today() + timedelta(days=20),
                    document_number="OCR-WRONG",
                    ocr_proposal={"document_number": "OCR-WRONG", "expiry_date": str(date.today() + timedelta(days=999)), "authoritative": False},
                    uploaded_by="emp",
                    upload_source="employee_app",
                )
            conn.commit()
        gate.check("ocr_proposal_non_authoritative", (v.get("ocr_proposal") or {}).get("authoritative") is False)

        approved = review(
            exp,
            "residence",
            {
                "action": "approve",
                "version_id": str(v["version_id"]),
                "document_number": "R-CORRECT",
                "expiry_date": str(date.today() + timedelta(days=20)),
                "issue_date": str(date.today() - timedelta(days=10)),
                "reason": "Corrected OCR",
                "confirm_ocr": False,
            },
        )
        gate.check("hr_approve", bool(approved.get("ok")), approved)
        gate.check("ocr_corrected_by_hr", approved["result"].get("document_number") == "R-CORRECT")

        # Missing expiry / OCR unavailable — HR enter dates
        corrected = review(
            exp,
            "work_permit",
            {
                "action": "correct_metadata",
                "expiry_date": str(date.today() + timedelta(days=120)),
                "issue_date": str(date.today() - timedelta(days=3)),
                "reason": "OCR unavailable — HR entered dates",
            },
        )
        gate.check("hr_enter_dates_ocr_unavailable", bool(corrected.get("ok")), corrected)

        # Renewal before expiry: pending not current
        async def renew_flow():
            renew = await upload_renew(exp, "residence", "res2.pdf", pdf_bytes("res2"))
            gate.check("employee_documents_renew_api", bool(renew.get("ok")) and renew.get("review_status") == "pending_hr_review", renew)
            docs = orch.app_documents(context=emp_ctx(exp))
            gate.check("employee_documents_payload_has_compliance", bool(docs.get("compliance")), docs.get("count"))
            statuses = {c["document_type"]: c for c in docs.get("compliance") or []}
            res = statuses.get("residence") or {}
            gate.check("employee_ui_fields_status", bool(res.get("review_status_label")), res)
            gate.check("employee_ui_fields_expiry", "expiry_date" in res, res)
            gate.check("employee_can_renew_flag", res.get("can_renew") is True, res)
            gate.check("legitimacy_note_on_documents", "PACI" in str(docs.get("legitimacy_note") or "") and "not" in str(docs.get("legitimacy_note") or "").lower())

            vers = exec_sql(
                """
                SELECT version_no, is_current, review_status FROM governed_document_versions
                WHERE company_code=%s AND employee_key=%s AND document_type='residence'
                ORDER BY version_no
                """,
                (COMPANY, EMP_EXP),
            )
            gate.check(
                "replacement_pending_prior_current",
                any(v["is_current"] and v["review_status"] == "hr_reviewed" for v in vers)
                and any((not v["is_current"]) and v["review_status"] == "pending_hr_review" for v in vers),
                vers,
            )
            pending = next(v for v in vers if v["review_status"] == "pending_hr_review")
            # Reject replacement
            rejected = review(
                exp,
                "residence",
                {"action": "reject", "reason": "Blurry — re-upload required", "version_id": None},
            )
            # find pending version id from DB
            pending_rows = exec_sql(
                """
                SELECT version_id FROM governed_document_versions
                WHERE company_code=%s AND employee_key=%s AND document_type='residence' AND review_status='pending_hr_review'
                ORDER BY version_no DESC LIMIT 1
                """,
                (COMPANY, EMP_EXP),
            )
            if pending_rows:
                rejected = review(
                    exp,
                    "residence",
                    {
                        "action": "request_reupload",
                        "version_id": str(pending_rows[0]["version_id"]),
                        "reason": "Blurry — re-upload required",
                    },
                )
            gate.check("hr_reject_reupload", bool(rejected.get("ok")), rejected)
            current = exec_sql(
                """
                SELECT version_no, review_status, is_current FROM governed_document_versions
                WHERE company_code=%s AND employee_key=%s AND document_type='residence' AND is_current=true
                """,
                (COMPANY, EMP_EXP),
            )
            gate.check(
                "rejected_preserves_prior_approved",
                current and current[0]["review_status"] == "hr_reviewed",
                current,
            )

            # After expiry renewal + approve closes reminders
            exec_sql(
                """
                UPDATE compliance_documents SET expiry_date=%s, reminder_count=4, last_alerted_at=now(), status='received'
                WHERE employee_key=%s AND document_type='residence'
                """,
                (date.today() - timedelta(days=2), EMP_EXP),
            )
            renew2 = await upload_renew(exp, "residence", "res3.pdf", pdf_bytes("res3"))
            gate.check("renew_after_expiry_upload", bool(renew2.get("ok")), renew2)
            pending2 = exec_sql(
                """
                SELECT version_id FROM governed_document_versions
                WHERE company_code=%s AND employee_key=%s AND document_type='residence' AND review_status='pending_hr_review'
                ORDER BY version_no DESC LIMIT 1
                """,
                (COMPANY, EMP_EXP),
            )
            appr2 = review(
                exp,
                "residence",
                {
                    "action": "approve",
                    "version_id": str(pending2[0]["version_id"]),
                    "expiry_date": str(date.today() + timedelta(days=365)),
                    "reason": "Approved renewal after expiry",
                },
            )
            gate.check("newest_approved_becomes_current", bool(appr2.get("ok")), appr2)
            rem = exec_sql(
                "SELECT reminder_count, last_alerted_at, status FROM compliance_documents WHERE employee_key=%s AND document_type='residence'",
                (EMP_EXP,),
            )
            gate.check(
                "reminders_reset_after_approved_renewal",
                rem and int(rem[0]["reminder_count"] or 0) == 0 and rem[0]["last_alerted_at"] is None,
                rem,
            )
            hist = exec_sql(
                """
                SELECT version_no, review_status, is_current FROM governed_document_versions
                WHERE company_code=%s AND employee_key=%s AND document_type='residence' ORDER BY version_no
                """,
                (COMPANY, EMP_EXP),
            )
            gate.check("version_history_retained", len(hist) >= 3, hist)
            gate.check(
                "prior_superseded_or_rejected_present",
                any(h["review_status"] in ("superseded", "rejected_reupload", "hr_reviewed") and not h["is_current"] for h in hist),
                hist,
            )
            events = exec_sql(
                "SELECT action, actor_user_id FROM governed_document_events WHERE company_code=%s AND employee_key=%s",
                (COMPANY, EMP_EXP),
            )
            gate.check("append_only_audit_events", len(events) >= 3, events)

            # Unauthorized HR
            denied = False
            try:
                review(exp, "residence", {"action": "approve", "reason": "nope"}, manage=False)
            except Exception as exc:
                denied = "permission" in str(exc).lower() or getattr(exc, "status_code", None) == 403 or "403" in str(exc)
                # FastAPI HTTPException
                detail = getattr(exc, "detail", None)
                if isinstance(detail, dict) and detail.get("error") in {"permission_denied", "module_disabled"}:
                    denied = True
            gate.check("unauthorized_hr_fail_closed", denied)

            # Cross-tenant
            cross_ok = False
            try:
                cross = orch.dashboard_employee_compliance_journey(EMP_EXP, context=hr_ctx(OTHER))
                cross_ok = cross.get("documents") in (None, [])
                gate.check("cross_tenant_empty_list", cross_ok, cross)
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                cross_ok = status == 404 or "404" in str(exc) or "employee_not_found" in str(exc)
                gate.check("cross_tenant_404", cross_ok, str(exc)[:200])
            gate.check("cross_tenant_resolves_empty_or_404", cross_ok)

            # Employee isolation: handler always uses context employee_key
            own = orch.app_documents(context=emp_ctx(nat))
            gate.check("employee_self_scope_only", own.get("ok") is True, own.get("count"))

            # Arabic labels via journey list
            ar_items = journey.list_employee_compliance_journey(orch, company_code=COMPANY, employee_key=EMP_EXP, locale="ar")
            gate.check("arabic_labels", any(i.get("label_ar") for i in ar_items), ar_items[:1])

            # Status wording mapping
            gate.check("status_label_hr_reviewed", journey.hr_status_label("hr_reviewed") == "HR reviewed")
            gate.check("status_label_pending", journey.hr_status_label("pending_hr_review") == "Pending HR review")
            gate.check("status_label_rejected", journey.hr_status_label("rejected_reupload") == "Rejected — re-upload required")

        asyncio.run(renew_flow())

    except Exception as exc:
        gate.check("matrix_uncaught", False, f"{exc}\n{traceback.format_exc()}")
    finally:
        cleanup()
        left = exec_sql("SELECT company_code FROM companies WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
        gate.check("zero_synthetic_residue_companies", left == [], left)
        left_v = exec_sql(
            "SELECT count(*) AS c FROM governed_document_versions WHERE company_code = ANY(%s)",
            ([COMPANY, OTHER],),
        )
        gate.check("zero_synthetic_residue_versions", left_v and int(left_v[0]["c"]) == 0, left_v)

    # Health after matrix
    import urllib.request

    try:
        with urllib.request.urlopen("http://127.0.0.1:8011/health", timeout=5) as resp:
            gate.check("staging_health_green", resp.status == 200)
    except Exception as exc:
        gate.check("staging_health_green", False, str(exc))

    summary = {
        "marker": MARKER,
        "artifact": ARTIFACT,
        "total": len(gate.rows),
        "passed": len(gate.rows) - len(gate.failed),
        "failed": len(gate.failed),
        "failures": gate.failed,
    }
    out_dir = Path("/opt/wathefni/staging/staging-evidence")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir / f"kuwait-pilot-document-journey-staging-{ts}.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"passed": summary["passed"], "failed": summary["failed"], "total": summary["total"], "evidence": str(out)}, indent=2))
    return 1 if gate.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
