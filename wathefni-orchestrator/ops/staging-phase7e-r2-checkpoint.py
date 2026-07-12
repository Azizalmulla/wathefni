#!/usr/bin/env python3
"""Focused staging checkpoint for Phase 7E-R2 compensation and rejection audit."""

from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

from psycopg2.extras import Json

STAGING_ORCH = Path("/opt/wathefni/staging/orchestrator")
ORCH = STAGING_ORCH if STAGING_ORCH.is_dir() else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ORCH))

import app  # noqa: E402

COMPANY = "P7ER2STG01"
OTHER = "P7ER2STG02"
EMPLOYEE = "p7er2-employee"
PHONE = "96555559821"
MARKER = "phase7e-r2-checkpoint"
PDF = b"%PDF-1.4\n% phase7e r2\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + (b"\x00" * 32)


def db(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = [dict(row) for row in cur.fetchall()] if cur.description else []
        conn.commit()
    return rows


def scalar(sql: str, params: tuple[Any, ...] = ()) -> Any:
    rows = db(sql, params)
    return next(iter(rows[0].values())) if rows else None


def table_columns(table: str) -> set[str]:
    return {
        row["column_name"]
        for row in db(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
            (table,),
        )
    }


def insert_dynamic(table: str, values: dict[str, Any]) -> None:
    columns = table_columns(table)
    chosen = [key for key in values if key in columns]
    db(
        f"INSERT INTO {table} ({','.join(chosen)}) VALUES ({','.join(['%s'] * len(chosen))})",
        tuple(values[key] for key in chosen),
    )


def cleanup() -> None:
    workspace = Path(os.environ.get("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace"))
    shutil.rmtree(workspace / "data" / "companies" / COMPANY, ignore_errors=True)
    shutil.rmtree(workspace / "data" / "companies" / OTHER, ignore_errors=True)
    for sql, params in (
        ("DELETE FROM action_results WHERE company_code IN (%s,%s)", (COMPANY, OTHER)),
        ("DELETE FROM file_registry WHERE company_code IN (%s,%s)", (COMPANY, OTHER)),
        ("DELETE FROM employee_documents WHERE company_code IN (%s,%s)", (COMPANY, OTHER)),
        ("DELETE FROM compliance_documents WHERE company_code IN (%s,%s)", (COMPANY, OTHER)),
        ("DELETE FROM onboarding_items WHERE company_code IN (%s,%s) OR employee_key=%s", (COMPANY, OTHER, EMPLOYEE)),
        ("DELETE FROM document_storage_operations WHERE company_code IN (%s,%s)", (COMPANY, OTHER)),
        ("DELETE FROM company_modules WHERE company_code IN (%s,%s)", (COMPANY, OTHER)),
        ("DELETE FROM employees WHERE company_code IN (%s,%s) OR employee_key=%s", (COMPANY, OTHER, EMPLOYEE)),
        ("DELETE FROM companies WHERE company_code IN (%s,%s)", (COMPANY, OTHER)),
    ):
        try:
            db(sql, params)
        except Exception:
            pass


def setup() -> dict[str, Any]:
    cleanup()
    for company in (COMPANY, OTHER):
        db(
            "INSERT INTO companies (company_code,name,status,metadata,raw_json) VALUES (%s,%s,'active',%s,%s)",
            (company, f"{company} synthetic", Json({"marker": MARKER}), Json({"marker": MARKER})),
        )
        db(
            "INSERT INTO company_modules (company_code,module_key,enabled,source) VALUES (%s,'onboarding',TRUE,%s)",
            (company, MARKER),
        )
    insert_dynamic(
        "employees",
        {
            "company_code": COMPANY,
            "employee_key": EMPLOYEE,
            "phone": PHONE,
            "name": "R2 Synthetic Employee",
            "email": "r2@synthetic.invalid",
            "employment_status": "active",
            "onboarding_status": "in_progress",
            "raw_json": Json({"marker": MARKER}),
            "profile": Json({"marker": MARKER}),
        },
    )
    employee = dict(db("SELECT * FROM employees WHERE employee_key=%s", (EMPLOYEE,))[0])
    return {
        "company_code": COMPANY,
        "employee_key": EMPLOYEE,
        "employee": employee,
        "actor_role": "employee",
    }


def add_item(item_id: str) -> None:
    insert_dynamic(
        "onboarding_items",
        {
            "company_code": COMPANY,
            "employee_key": EMPLOYEE,
            "item_id": item_id,
            "label": item_id.replace("_", " ").title(),
            "item_type": "document",
            "document_type": item_id,
            "required": True,
            "status": "pending",
            "raw_json": Json({"marker": MARKER}),
        },
    )


def upload(filename: str, mime: str, content: bytes, item_id: str, context: dict[str, Any]) -> dict[str, Any]:
    from starlette.datastructures import Headers, UploadFile

    file = UploadFile(file=io.BytesIO(content), filename=filename, headers=Headers({"content-type": mime}))
    try:
        body = asyncio.run(app.app_onboarding_document_upload(file=file, item_id=item_id, context=context))
        return {"status": 200, "body": body}
    except app.HTTPException as exc:
        return {"status": exc.status_code, "body": exc.detail}
    except Exception as exc:
        return {"status": 500, "exception": type(exc).__name__}


def operation_for(item_id: str) -> dict[str, Any]:
    return db(
        "SELECT * FROM document_storage_operations WHERE company_code=%s AND item_id=%s ORDER BY created_at DESC LIMIT 1",
        (COMPANY, item_id),
    )[0]


def run() -> dict[str, Any]:
    context = setup()
    checks: list[dict[str, Any]] = []

    def check(name: str, condition: Callable[[], bool] | bool, evidence: Any = None) -> None:
        passed = bool(condition() if callable(condition) else condition)
        checks.append({"name": name, "passed": passed, "evidence": evidence})
        print(f"{'PASS' if passed else 'FAIL'} {name}")

    # C07k: provider succeeds, canonical transaction fails, immediate local delete succeeds.
    add_item("db_failure_delete")
    original_receipt = app.record_employee_document_receipt
    app.record_employee_document_receipt = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("synthetic_db_failure"))
    try:
        failed = upload("db-failure.pdf", "application/pdf", PDF, "db_failure_delete", context)
    finally:
        app.record_employee_document_receipt = original_receipt
    op = operation_for("db_failure_delete")
    object_path = Path(str(op.get("storage_object_key") or ""))
    if not object_path.is_absolute():
        object_path = app.WORKSPACE / object_path
    check("db failure returns failed request", failed["status"] == 500, failed)
    check("successful compensation removes object", op["status"] == "compensated" and not object_path.exists(), op["status"])
    check(
        "failed canonical transaction leaves onboarding pending",
        scalar("SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id='db_failure_delete'", (EMPLOYEE,)) == "pending",
    )

    # Provider failure/unknown persists a retry, then succeeds.
    add_item("provider_retry")
    original_delete = app.delete_document_storage_object
    app.delete_document_storage_object = lambda _operation: {"ok": False, "outcome": "delete_unknown"}
    app.record_employee_document_receipt = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("synthetic_db_failure"))
    try:
        retry_failed = upload("provider-retry.pdf", "application/pdf", PDF + b"retry", "provider_retry", context)
    finally:
        app.record_employee_document_receipt = original_receipt
        app.delete_document_storage_object = original_delete
    retry_op = operation_for("provider_retry")
    check(
        "unknown provider outcome remains durable and retryable",
        retry_failed["status"] == 500 and retry_op["status"] == "compensation_pending" and retry_op["attempt_count"] == 1,
        retry_op["status"],
    )
    retried = app.reconcile_document_storage_operation(str(retry_op["operation_id"]), lease_owner="r2-checkpoint")
    check("reconciliation retry succeeds", retried.get("ok") and retried.get("status") == "compensated", retried)
    repeated = app.reconcile_document_storage_operation(str(retry_op["operation_id"]), lease_owner="r2-checkpoint")
    check("repeated reconciliation is idempotent", repeated.get("outcome") == "compensated", repeated)

    # Recover a process crash after local storage but before provider result persistence.
    add_item("prepared_crash")
    prepared = app.prepare_document_storage_operation(employee=context["employee"], item_id="prepared_crash")
    config = app.document_storage_config(COMPANY)
    crash_dir = Path(config["local_root"]) / PHONE / "documents" / "prepared_crash"
    crash_dir.mkdir(parents=True, exist_ok=True)
    crash_object = crash_dir / f"prepared_crash-synthetic-{prepared['trace_key']}.pdf"
    crash_object.write_bytes(PDF)
    db("UPDATE document_storage_operations SET next_attempt_at=now() WHERE operation_id=%s", (prepared["operation_id"],))
    crash_recovery = app.reconcile_document_storage_operation(str(prepared["operation_id"]), lease_owner="r2-checkpoint")
    check("prepared crash trace is recovered and deleted", crash_recovery.get("ok") and not crash_object.exists(), crash_recovery)

    # Unknown database truth never permits deletion.
    add_item("unknown_db_truth")
    unknown = app.prepare_document_storage_operation(employee=context["employee"], item_id="unknown_db_truth")
    unknown_dir = Path(config["local_root"]) / PHONE / "documents" / "unknown_db_truth"
    unknown_dir.mkdir(parents=True, exist_ok=True)
    unknown_path = unknown_dir / f"unknown_db_truth-synthetic-{unknown['trace_key']}.pdf"
    unknown_path.write_bytes(PDF)
    unknown_storage = {
        "ok": True,
        "provider": "local",
        "storage_status": "stored",
        "storage_object_key": app.storage_object_key_for_path(unknown_path),
        "external_file_id": None,
        "content_sha256": app.sha256_file(unknown_path),
        "metadata": {"local_path": str(unknown_path)},
    }
    app.update_document_storage_operation_after_store(str(unknown["operation_id"]), storage_result=unknown_storage, config=config)
    original_references = app.document_storage_canonical_references
    app.document_storage_canonical_references = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("synthetic_db_truth_unknown"))
    try:
        unknown_result = app.reconcile_document_storage_operation(str(unknown["operation_id"]), lease_owner="r2-checkpoint")
    finally:
        app.document_storage_canonical_references = original_references
    check(
        "unknown database truth never deletes",
        unknown_result.get("outcome") == "reconciliation_error" and unknown_path.exists(),
        unknown_result,
    )
    unknown_cleanup = app.reconcile_document_storage_operation(str(unknown["operation_id"]), lease_owner="r2-checkpoint")
    check("unknown-truth operation remains recoverable", unknown_cleanup.get("ok") and not unknown_path.exists(), unknown_cleanup)

    # An unexpired deletion lease prevents concurrent workers; expiry safely resumes.
    add_item("lease_control")
    leased = app.prepare_document_storage_operation(employee=context["employee"], item_id="lease_control")
    lease_dir = Path(config["local_root"]) / PHONE / "documents" / "lease_control"
    lease_dir.mkdir(parents=True, exist_ok=True)
    lease_path = lease_dir / f"lease_control-synthetic-{leased['trace_key']}.pdf"
    lease_path.write_bytes(PDF)
    lease_storage = {
        "ok": True,
        "provider": "local",
        "storage_status": "stored",
        "storage_object_key": app.storage_object_key_for_path(lease_path),
        "external_file_id": None,
        "content_sha256": app.sha256_file(lease_path),
        "metadata": {"local_path": str(lease_path)},
    }
    app.update_document_storage_operation_after_store(str(leased["operation_id"]), storage_result=lease_storage, config=config)
    db(
        "UPDATE document_storage_operations SET status='deleting', lease_owner='other-worker', lease_expires_at=now() + interval '10 minutes' WHERE operation_id=%s",
        (leased["operation_id"],),
    )
    leased_result = app.reconcile_document_storage_operation(str(leased["operation_id"]), lease_owner="r2-checkpoint")
    check("active lease blocks concurrent deletion", leased_result.get("outcome") == "leased" and lease_path.exists(), leased_result)
    db(
        "UPDATE document_storage_operations SET lease_expires_at=now() - interval '1 second' WHERE operation_id=%s",
        (leased["operation_id"],),
    )
    lease_cleanup = app.reconcile_document_storage_operation(str(leased["operation_id"]), lease_owner="r2-checkpoint")
    check("expired lease resumes idempotent deletion", lease_cleanup.get("ok") and not lease_path.exists(), lease_cleanup)

    # A confirmed already-missing provider object is a successful terminal result.
    add_item("already_missing")
    missing = app.prepare_document_storage_operation(employee=context["employee"], item_id="already_missing")
    missing_path = Path(config["local_root"]) / PHONE / "documents" / "already_missing" / f"already_missing-{missing['trace_key']}.pdf"
    missing_storage = {
        "ok": True,
        "provider": "local",
        "storage_status": "stored",
        "storage_object_key": app.storage_object_key_for_path(missing_path),
        "external_file_id": None,
        "content_sha256": "synthetic-missing",
        "metadata": {"local_path": str(missing_path)},
    }
    app.update_document_storage_operation_after_store(str(missing["operation_id"]), storage_result=missing_storage, config=config)
    missing_result = app.reconcile_document_storage_operation(str(missing["operation_id"]), lease_owner="r2-checkpoint")
    check("confirmed already-missing is idempotent success", missing_result.get("outcome") == "already_missing" and missing_result.get("status") == "compensated", missing_result)

    # Canonical reference blocks deletion.
    add_item("referenced_object")
    referenced = app.prepare_document_storage_operation(employee=context["employee"], item_id="referenced_object")
    ref_dir = Path(config["local_root"]) / PHONE / "documents" / "referenced_object"
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref_path = ref_dir / f"referenced_object-synthetic-{referenced['trace_key']}.pdf"
    ref_path.write_bytes(PDF)
    ref_storage = {
        "ok": True,
        "provider": "local",
        "storage_status": "stored",
        "storage_object_key": app.storage_object_key_for_path(ref_path),
        "external_file_id": None,
        "content_sha256": app.sha256_file(ref_path),
        "metadata": {"local_path": str(ref_path)},
    }
    app.update_document_storage_operation_after_store(str(referenced["operation_id"]), storage_result=ref_storage, config=config)
    db(
        """
        INSERT INTO file_registry (
            company_code,subject_type,subject_key,file_kind,document_type,storage_provider,
            storage_object_key,content_sha256,storage_status,metadata,raw_json
        ) VALUES (%s,'employee',%s,'onboarding_document','referenced_object','local',%s,%s,'stored',%s,%s)
        """,
        (
            COMPANY,
            EMPLOYEE,
            ref_storage["storage_object_key"],
            ref_storage["content_sha256"],
            Json({"item_id": "referenced_object"}),
            Json({"marker": MARKER}),
        ),
    )
    referenced_result = app.reconcile_document_storage_operation(str(referenced["operation_id"]), lease_owner="r2-checkpoint")
    check(
        "canonically referenced object is never deleted",
        referenced_result.get("outcome") == "canonical_reference_found" and ref_path.exists(),
        referenced_result,
    )

    # Cross-tenant path cannot be deleted.
    other_root = app.WORKSPACE / "data" / "companies" / OTHER / "employees"
    cross_path = other_root / PHONE / "documents" / "cross_tenant"
    cross_path.mkdir(parents=True, exist_ok=True)
    cross_file = cross_path / f"cross_tenant-{uuid.uuid4().hex}.pdf"
    cross_file.write_bytes(PDF)
    cross_id = str(uuid.uuid4())
    cross_trace = cross_file.stem.split("-")[-1]
    db(
        """
        INSERT INTO document_storage_operations (
            operation_id,company_code,employee_key,item_id,provider,provider_scope,trace_key,
            storage_object_key,status,next_attempt_at,stored_at
        ) VALUES (%s,%s,%s,'cross_tenant','local',%s,%s,%s,'stored',now(),now())
        """,
        (
            cross_id,
            COMPANY,
            EMPLOYEE,
            str(Path(config["local_root"]).resolve()),
            cross_trace,
            app.storage_object_key_for_path(cross_file),
        ),
    )
    db(
        """
        INSERT INTO file_registry (
            company_code,subject_type,subject_key,file_kind,document_type,storage_provider,
            storage_object_key,storage_status,metadata,raw_json
        ) VALUES (%s,'employee','other-tenant-employee','onboarding_document','cross_tenant',
                  'local',%s,'stored',%s,%s)
        """,
        (
            OTHER,
            app.storage_object_key_for_path(cross_file),
            Json({"item_id": "cross_tenant"}),
            Json({"marker": MARKER}),
        ),
    )
    cross_result = app.reconcile_document_storage_operation(cross_id, lease_owner="r2-checkpoint")
    check(
        "cross-tenant canonical reference is never deleted",
        cross_result.get("outcome") == "canonical_reference_found" and cross_file.exists(),
        cross_result,
    )
    ownership_result = app.delete_document_storage_object(
        {
            "provider": "local",
            "company_code": COMPANY,
            "employee_key": EMPLOYEE,
            "item_id": "cross_tenant",
            "provider_scope": str(Path(config["local_root"]).resolve()),
            "trace_key": cross_trace,
            "storage_object_key": app.storage_object_key_for_path(cross_file),
        }
    )
    check(
        "cross-tenant provider ownership mismatch is terminal",
        ownership_result.get("outcome") == "ownership_mismatch" and ownership_result.get("terminal") and cross_file.exists(),
        ownership_result,
    )

    # Drive provider-aware control, entirely mocked.
    drive_calls: list[list[str]] = []
    drive_trace = uuid.uuid4().hex
    drive_operation = {
        "provider": "google_drive",
        "company_code": COMPANY,
        "item_id": "drive_control",
        "trace_key": drive_trace,
        "storage_object_key": "drive-file-r2",
        "provider_scope": "drive-folder-r2",
    }
    original_config = app.document_storage_config
    original_gog = app.run_gog_wathefni
    app.document_storage_config = lambda _company: {
        "company_code": COMPANY,
        "provider": "google_drive",
        "fallback_provider": "local",
        "drive_folder_id": "drive-folder-r2",
        "local_root": config["local_root"],
    }

    def fake_gog(args: list[str], timeout: int = 90) -> dict[str, Any]:
        drive_calls.append(args)
        if args[:2] == ["drive", "get"]:
            return {
                "ok": True,
                "json": {
                    "id": "drive-file-r2",
                    "name": f"{COMPANY}-{PHONE}-drive_control-{drive_trace}.pdf",
                    "parents": ["drive-folder-r2"],
                },
            }
        return {"ok": True, "json": {"id": "drive-file-r2"}}

    app.run_gog_wathefni = fake_gog
    try:
        drive_deleted = app.delete_document_storage_object(drive_operation)
        drive_operation_id = str(uuid.uuid4())
        db(
            """
            INSERT INTO document_storage_operations (
                operation_id,company_code,employee_key,item_id,provider,provider_scope,
                trace_key,storage_object_key,external_file_id,status,next_attempt_at,stored_at
            ) VALUES (%s,%s,%s,'drive_control','google_drive','drive-folder-r2',%s,
                      'drive-file-r2','drive-file-r2','compensation_pending',now(),now())
            """,
            (drive_operation_id, COMPANY, EMPLOYEE, drive_trace),
        )
        drive_reconciled = app.reconcile_document_storage_operation(drive_operation_id, lease_owner="r2-checkpoint")
    finally:
        app.run_gog_wathefni = original_gog
        app.document_storage_config = original_config
    check(
        "Drive deletion verifies ownership then permanently deletes",
        drive_deleted.get("ok")
        and drive_calls[0][:2] == ["drive", "get"]
        and "--permanent" in drive_calls[1]
        and "--force" in drive_calls[1],
        drive_calls,
    )
    check(
        "stored Drive operation compensates through reconciler",
        drive_reconciled.get("ok") and drive_reconciled.get("status") == "compensated",
        drive_reconciled,
    )

    # C07l: one safe audit per rejection and no canonical/storage side effects.
    for item_id in ("audit_extension", "audit_mime", "audit_signature", "audit_detector"):
        add_item(item_id)
    audits_before = int(scalar("SELECT count(*) FROM action_results WHERE company_code=%s AND action_type='employee_document_upload_rejected'", (COMPANY,)) or 0)
    rejection_results = [
        upload("unsafe.exe", "application/octet-stream", b"MZ payload", "audit_extension", context),
        upload("wrong.pdf", "image/png", PNG, "audit_mime", context),
        upload("spoof.pdf", "application/pdf", PNG, "audit_signature", context),
    ]
    original_detector = app._detect_employee_app_upload_matches
    app._detect_employee_app_upload_matches = lambda _data: (_ for _ in ()).throw(RuntimeError("synthetic_detector_error"))
    try:
        rejection_results.append(upload("detector.pdf", "application/pdf", PDF, "audit_detector", context))
    finally:
        app._detect_employee_app_upload_matches = original_detector
    audits = db(
        "SELECT result FROM action_results WHERE company_code=%s AND action_type='employee_document_upload_rejected' ORDER BY created_at",
        (COMPANY,),
    )
    new_audits = audits[audits_before:]
    check("each rejected upload creates exactly one audit", len(new_audits) == 4, len(new_audits))
    check("all validation controls retain 4xx responses", all(400 <= row["status"] < 500 for row in rejection_results), rejection_results)
    serialized = json.dumps(new_audits, default=str).lower()
    check(
        "audit metadata excludes bytes filenames paths and payloads",
        all(term not in serialized for term in ("mz payload", "unsafe.exe", "wrong.pdf", "spoof.pdf", "detector.pdf", "tmp/", "full_payload")),
    )
    allowed_audit_keys = {
        "event_id",
        "company_code",
        "employee_key",
        "item_id",
        "actor_context",
        "rejection_code",
        "declared_mime",
        "extension",
        "attempted_byte_size",
    }
    check(
        "audit rows contain only approved metadata fields",
        all(set((row.get("result") or {}).keys()) == allowed_audit_keys for row in new_audits),
        [sorted((row.get("result") or {}).keys()) for row in new_audits],
    )
    canonical_rejections = int(
        scalar(
            "SELECT count(*) FROM file_registry WHERE company_code=%s AND document_type LIKE 'audit_%%'",
            (COMPANY,),
        )
        or 0
    )
    check("rejected uploads create no canonical object rows", canonical_rejections == 0, canonical_rejections)

    # Approved best-effort sink behavior: the original rejection is unchanged.
    add_item("audit_sink_failure")
    original_audit = app.record_employee_upload_rejection_audit
    app.record_employee_upload_rejection_audit = lambda *_a, **_k: False
    try:
        sink_failure = upload("sink.exe", "application/octet-stream", b"MZ", "audit_sink_failure", context)
    finally:
        app.record_employee_upload_rejection_audit = original_audit
    check("audit sink failure preserves rejection and zero storage", sink_failure["status"] == 400, sink_failure)

    pending = int(
        scalar(
            "SELECT count(*) FROM document_storage_operations WHERE company_code=%s AND status IN ('prepared','stored','deleting','compensation_pending')",
            (COMPANY,),
        )
        or 0
    )
    check("checkpoint leaves no retryable operation residue", pending == 0, pending)

    passed = sum(1 for row in checks if row["passed"])
    result = {"phase": "7E-R2", "passed": passed, "total": len(checks), "checks": checks}
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    return result


def main() -> None:
    app.ensure_schema(force=True)
    try:
        result = run()
    finally:
        cleanup()
    raise SystemExit(0 if result["passed"] == result["total"] else 1)


if __name__ == "__main__":
    main()
