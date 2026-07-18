"""HR document upload harness (staging).

Closes the loop on the Document Hub: HR can attach/replace an employee's
onboarding document from the dashboard, and the stored file must be
indistinguishable from one the employee sent over WhatsApp (same storage path,
same file_registry/onboarding_items/document index).

Drives the real async endpoint (dashboard_posthire_employee_document_upload) with
a constructed UploadFile so the full gate is exercised: dark-launch flag, RBAC
(manage, not just read), manager scope, extension + size + empty validation, and
the happy-path write that reuses store_onboarding_document +
record_employee_document_receipt. Then verifies the uploaded file is indexed and
downloadable through the existing hub resolver.

Run on a host with the orchestrator venv + (staging) database:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-document-upload.py

NEVER point this at the production database: it writes and deletes a company.
"""

from __future__ import annotations

import asyncio
import io
import sys
from typing import Any, Callable

try:
    import app
    from psycopg2.extras import Json
    from starlette.datastructures import Headers, UploadFile
except ModuleNotFoundError as exc:
    if exc.name in {"psycopg2", "app", "starlette"} or (exc.name or "").startswith("psycopg2"):
        print("SKIP: psycopg2/starlette not available locally; full run happens on staging.")
        sys.exit(0)
    raise

COMPANY = "DOCUPLOADTESTCO"
MARKER = "temporary_document_upload_harness"

EMP = f"docupload-emp-{COMPANY}"
PHONE = "96550000000601"
ITEM = "civil_id"
MODULES = ["onboarding", "compliance"]

# Out-of-scope manager probe.
OTHER_EMP = f"docupload-other-{COMPANY}"
OTHER_PHONE = "96550000000602"
TEAM_A_KEY = app.org_key(COMPANY, "team", "Team A")
TEAM_B_KEY = app.org_key(COMPANY, "team", "Team B")
BRANCH_KEY = app.org_key(COMPANY, "branch", "HQ")
MGR_OTHER_PHONE = "96550000000610"  # manages Team B -> cannot touch EMP (Team A)
MGR_OTHER_USER = "doc-upload-mgr-other"
OWNER_USER = "doc-upload-owner"


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:
            self.failed.append(f"{label} -> raised {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def report(self) -> int:
        for label in self.passed:
            print(f"  PASS  {label}")
        for label in self.failed:
            print(f"  FAIL  {label}")
        print(f"\n{len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def _flag(on: bool) -> None:
    if on:
        app.os.environ["WATHEFNI_DOC_UPLOAD"] = "on"
    else:
        app.os.environ.pop("WATHEFNI_DOC_UPLOAD", None)


def _ctx(viewer_phone: str | None = None) -> dict[str, Any]:
    # Owner role with backend_current grants. When the out-of-scope manager phone
    # is attached, the seeded Team B manager_scopes row still restricts visibility
    # (owners/HR become restricted once they have explicit scopes).
    user_id = MGR_OTHER_USER if viewer_phone == MGR_OTHER_PHONE else OWNER_USER
    permissions = sorted(set(app.hr_role_permissions("owner")) | {"employees.read"})
    return {
        "company_code": COMPANY,
        "permissions": permissions,
        "hr_phone": viewer_phone,
        "access": {"role": "owner", "permissions": permissions},
        "actor_role": "owner",
        "actor_user_id": user_id,
        "permission_authority": "backend_current",
        "permission_subject_user_id": user_id,
        "permission_subject_company": COMPANY,
        "hr_user": {"role": "owner", "status": "active", "company_code": COMPANY, "user_id": user_id},
    }


def _columns(cur: Any, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    return {r["column_name"] for r in cur.fetchall()}


def _insert_employee(cur: Any, columns: set[str], emp_key: str, phone: str, name: str) -> None:
    desired: dict[str, Any] = {
        "company_code": COMPANY, "phone": phone, "name": name,
        "email": f"{emp_key}@example.com", "employee_key": emp_key,
        "onboarding_status": "in_progress", "status": "active",
        "raw_json": Json({"smoke": MARKER}), "profile": Json({"smoke": MARKER}),
    }
    cols = [c for c in desired if c in columns]
    cur.execute(f"INSERT INTO employees ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})", [desired[c] for c in cols])


def _insert_item(cur: Any, columns: set[str], emp_key: str, item_id: str) -> None:
    desired: dict[str, Any] = {
        "company_code": COMPANY, "employee_key": emp_key, "item_id": item_id,
        "label": "Civil ID", "item_type": "document", "document_type": item_id,
        "required": True, "status": "pending",
    }
    cols = [c for c in desired if c in columns]
    cur.execute(f"INSERT INTO onboarding_items ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})", [desired[c] for c in cols])


def setup() -> None:
    _purge()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO UPDATE SET metadata=EXCLUDED.metadata",
                (COMPANY, "Doc Upload Harness", Json({"smoke": MARKER, "modules": MODULES}), Json({"smoke": MARKER})),
            )
            emp_cols = _columns(cur, "employees")
            item_cols = _columns(cur, "onboarding_items")
            _insert_employee(cur, emp_cols, EMP, PHONE, "Upload Holder")
            _insert_employee(cur, emp_cols, OTHER_EMP, OTHER_PHONE, "Other Holder")
            _insert_item(cur, item_cols, EMP, ITEM)
            _insert_item(cur, item_cols, OTHER_EMP, ITEM)
        conn.commit()
    # Org scope so the manager probe has a real out-of-scope target.
    app.os.environ["WATHEFNI_ORG_HIERARCHY"] = "on"
    app.upsert_org_branch(COMPANY, name="HQ", branch_key=BRANCH_KEY)
    app.upsert_org_team(COMPANY, name="Team A", branch_key=BRANCH_KEY, team_key=TEAM_A_KEY)
    app.upsert_org_team(COMPANY, name="Team B", branch_key=BRANCH_KEY, team_key=TEAM_B_KEY)
    app.set_employee_org_assignment(COMPANY, employee_key=EMP, team_key=TEAM_A_KEY)
    app.upsert_manager_scope(
        COMPANY,
        manager_phone=MGR_OTHER_PHONE,
        scope_type="team",
        team_key=TEAM_B_KEY,
        dashboard_user_id=MGR_OTHER_USER,
    )


def _exec(sql: str, params: tuple) -> None:
    # Each delete in its own transaction so a missing column on one table can
    # never roll back successful deletes (notably file_registry, which must be
    # fully cleared between runs or the "exactly one document" check leaks).
    with app.db_connect() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()


def _purge() -> None:
    keys = [EMP, OTHER_EMP]
    _exec("DELETE FROM manager_scope_members WHERE scope_id IN (SELECT scope_id FROM manager_scopes WHERE company_code=%s)", (COMPANY,))
    for table in ("manager_scopes", "employee_org_assignments", "company_teams", "company_branches", "company_modules"):
        _exec(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
    for table in ("file_registry", "employee_documents", "compliance_documents", "onboarding_items"):
        _exec(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
        _exec(f"DELETE FROM {table} WHERE subject_key = ANY(%s)" if table == "file_registry" else f"DELETE FROM {table} WHERE employee_key = ANY(%s)", (keys,))
    _exec("DELETE FROM employees WHERE company_code=%s", (COMPANY,))


def teardown() -> None:
    _purge()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
        conn.commit()
    _flag(False)
    app.os.environ.pop("WATHEFNI_ORG_HIERARCHY", None)
    # Best-effort removal of the stored file tree for this throwaway company.
    try:
        import shutil
        shutil.rmtree(app.WORKSPACE / "data" / "companies" / COMPANY, ignore_errors=True)
    except Exception:
        pass


def _upload(employee_key: str, item_id: str, filename: str, data: bytes, mime: str, ctx: dict[str, Any]):
    upload = UploadFile(file=io.BytesIO(data), filename=filename, headers=Headers({"content-type": mime}))
    return asyncio.run(app.dashboard_posthire_employee_document_upload(employee_key, file=upload, item_id=item_id, context=ctx))


def _status(emp_key: str, item_id: str) -> str | None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id=%s", (emp_key, item_id))
            row = cur.fetchone()
            return str(row["status"]) if row else None


def run_checks(checks: Checks) -> None:
    pdf = b"%PDF-1.4 smoke document bytes\n%%EOF"

    # --- Flag gate -----------------------------------------------------------
    _flag(False)
    checks.check("flag defaults OFF", lambda: app.doc_upload_enabled() is False)
    checks.check("upload denied while flag OFF (403)", lambda: _denied(lambda: _upload(EMP, ITEM, "id.pdf", pdf, "application/pdf", _ctx()), 403))
    # Compliance + Employee 360 surfaces must mirror the gate (OFF -> hidden).
    checks.check("compliance payload gate OFF when flag OFF", lambda: app.dashboard_compliance_payload(COMPANY).get("doc_upload_enabled") is False)
    checks.check("employee 360 gate OFF when flag OFF", lambda: app.dashboard_employee_profile(_ctx(), EMP).get("doc_upload_enabled") is False)

    _flag(True)
    checks.check("flag flips ON", lambda: app.doc_upload_enabled() is True)
    checks.check("compliance payload gate ON when flag ON", lambda: app.dashboard_compliance_payload(COMPANY).get("doc_upload_enabled") is True)
    checks.check("employee 360 gate ON when flag ON", lambda: app.dashboard_employee_profile(_ctx(), EMP).get("doc_upload_enabled") is True)

    # --- Validation ----------------------------------------------------------
    checks.check("unsupported extension rejected (400)", lambda: _denied(lambda: _upload(EMP, ITEM, "id.exe", pdf, "application/octet-stream", _ctx()), 400))
    checks.check("empty file rejected (400)", lambda: _denied(lambda: _upload(EMP, ITEM, "id.pdf", b"", "application/pdf", _ctx()), 400))

    original_cap = app._DOC_UPLOAD_MAX_BYTES
    app._DOC_UPLOAD_MAX_BYTES = 8
    try:
        checks.check("oversize file rejected (400)", lambda: _denied(lambda: _upload(EMP, ITEM, "id.pdf", pdf, "application/pdf", _ctx()), 400))
    finally:
        app._DOC_UPLOAD_MAX_BYTES = original_cap

    # --- Manager scope -------------------------------------------------------
    checks.check("out-of-scope manager cannot upload (404)", lambda: _denied(lambda: _upload(EMP, ITEM, "id.pdf", pdf, "application/pdf", _ctx(MGR_OTHER_PHONE)), 404))
    checks.check("unknown employee 404", lambda: _denied(lambda: _upload("nope", ITEM, "id.pdf", pdf, "application/pdf", _ctx()), 404))

    # --- Happy path ----------------------------------------------------------
    checks.check("item starts pending", lambda: _status(EMP, ITEM) == "pending")
    res = _upload(EMP, ITEM, "civil-id.pdf", pdf, "application/pdf", _ctx())
    checks.check("upload returns ok", lambda: res.get("ok") is True)
    checks.check("upload returns a file_id", lambda: bool(res.get("file_id")))
    checks.check("item now received", lambda: _status(EMP, ITEM) == "received")

    index = app.employee_document_index(COMPANY, EMP)
    checks.check("document index resolves the item to the new file", lambda: index.get(ITEM) == res.get("file_id"))

    docs = app.employee_documents_for(COMPANY, EMP)
    checks.check("hub lists exactly one document", lambda: len(docs) == 1 and docs[0]["file_id"] == res.get("file_id"))
    checks.check("uploaded file is marked available", lambda: docs[0]["has_file"] is True)

    resolved = app.resolve_employee_document_file(COMPANY, str(res.get("file_id")))
    checks.check("uploaded file resolves tenant-scoped", lambda: resolved is not None and str(resolved.get("subject_key")) == EMP)
    checks.check("uploaded file is downloadable from disk", lambda: app.employee_document_local_path(resolved) is not None)

    # --- Compliance + Employee 360 surfaces see the uploaded document --------
    # civil_id is a compliance type, so the dashboard-uploaded file must surface
    # on both the company compliance read and the per-employee 360 documents tab,
    # which is where the new upload/replace controls live.
    comp = app.dashboard_compliance_payload(COMPANY)
    checks.check(
        "compliance payload lists the uploaded civil_id with a file_id",
        lambda: any(d.get("document_type") == ITEM and d.get("file_id") for d in comp.get("documents", [])),
    )
    prof = app.dashboard_employee_profile(_ctx(), EMP)
    checks.check(
        "employee 360 documents section includes the uploaded file",
        lambda: any(str(x.get("file_id")) == str(res.get("file_id")) for x in ((prof.get("sections") or {}).get("documents") or {}).get("items", [])),
    )

    # --- Replace (re-upload) keeps a single indexed file ---------------------
    res2 = _upload(EMP, ITEM, "civil-id-v2.pdf", pdf + b" v2", "application/pdf", _ctx())
    checks.check("replace returns ok + file_id", lambda: res2.get("ok") is True and bool(res2.get("file_id")))
    checks.check("index points at the replacement", lambda: app.employee_document_index(COMPANY, EMP).get(ITEM) == res2.get("file_id"))


def _denied(fn: Callable[[], Any], status_code: int) -> bool:
    try:
        fn()
        return False
    except app.HTTPException as exc:
        return exc.status_code == status_code


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"document upload harness — company {COMPANY} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nDOCUMENT UPLOAD: FAILURES PRESENT")
    else:
        print("\nDOCUMENT UPLOAD: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
