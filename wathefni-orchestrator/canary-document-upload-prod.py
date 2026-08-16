"""Production canary for HR document upload (one-off, namespaced, self-cleaning).

Validates the live deployed endpoint (dashboard_posthire_employee_document_upload)
against the PRODUCTION database + storage, using a throwaway, clearly-namespaced
company/employee so no real tenant is ever touched. Uploads a dummy PDF (NOT a
real Civil ID/passport) and verifies the full write bundle + read/download path +
audit row + RBAC/tenant/manager-scope deny paths, then purges everything it made.

Run on the prod host from the prod orchestrator dir with the prod env:
  cd /opt/wathefni/orchestrator && \
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env \
  WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni \
  WATHEFNI_DOC_UPLOAD=on \
  .venv/bin/python canary-document-upload-prod.py
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
        print("SKIP: psycopg2/starlette not available; this canary must run on the prod host venv.")
        sys.exit(0)
    raise

COMPANY = "DOCUPLOADCANARY"
MARKER = "doc_upload_prod_canary"

EMP = f"canary-emp-{COMPANY}"
PHONE = "96550000000701"
ITEM = "civil_id"  # exercises compliance_documents linkage; content is a dummy, NOT a real ID

OTHER_EMP = f"canary-other-{COMPANY}"
OTHER_PHONE = "96550000000702"
OTHER_COMPANY = "DOCUPLOADCANARY_OTHER"  # cross-tenant probe target

BRANCH_KEY = app.org_key(COMPANY, "branch", "HQ")
TEAM_A_KEY = app.org_key(COMPANY, "team", "Team A")
TEAM_B_KEY = app.org_key(COMPANY, "team", "Team B")
MGR_OTHER_PHONE = "96550000000710"  # manages Team B -> must NOT touch EMP (Team A)

DUMMY_PDF = b"%PDF-1.4\nCANARY TEST DOCUMENT - NOT A REAL CIVIL ID\n%%EOF"


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


def _ctx(viewer_phone: str | None = None, *, company: str = COMPANY, role: str = "owner") -> dict[str, Any]:
    return {
        "company_code": company,
        "permissions": [],
        "hr_phone": viewer_phone,
        "access": {"role": role, "permissions": []},
        "actor_role": role,
        "actor_user_id": "canary-doc-upload",
        "hr_user": {"role": role, "status": "active", "company_code": company},
    }


def _columns(cur: Any, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    return {r["column_name"] for r in cur.fetchall()}


def _insert_company(cur: Any, code: str) -> None:
    cur.execute(
        "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
        "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO UPDATE SET metadata=EXCLUDED.metadata",
        (code, f"Canary {code}", Json({"smoke": MARKER, "modules": ["onboarding", "compliance"]}), Json({"smoke": MARKER})),
    )


def _insert_employee(cur: Any, columns: set[str], company: str, emp_key: str, phone: str, name: str) -> None:
    desired: dict[str, Any] = {
        "company_code": company, "phone": phone, "name": name,
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
            _insert_company(cur, COMPANY)
            _insert_company(cur, OTHER_COMPANY)
            emp_cols = _columns(cur, "employees")
            item_cols = _columns(cur, "onboarding_items")
            _insert_employee(cur, emp_cols, COMPANY, EMP, PHONE, "Canary Holder")
            _insert_employee(cur, emp_cols, OTHER_COMPANY, OTHER_EMP, OTHER_PHONE, "Other Tenant Holder")
            _insert_item(cur, item_cols, EMP, ITEM)
        conn.commit()
    app.os.environ["WATHEFNI_ORG_HIERARCHY"] = "on"
    app.upsert_org_branch(COMPANY, name="HQ", branch_key=BRANCH_KEY)
    app.upsert_org_team(COMPANY, name="Team A", branch_key=BRANCH_KEY, team_key=TEAM_A_KEY)
    app.upsert_org_team(COMPANY, name="Team B", branch_key=BRANCH_KEY, team_key=TEAM_B_KEY)
    app.set_employee_org_assignment(COMPANY, employee_key=EMP, team_key=TEAM_A_KEY)
    app.upsert_manager_scope(COMPANY, manager_phone=MGR_OTHER_PHONE, scope_type="team", team_key=TEAM_B_KEY)


def _exec(sql: str, params: tuple) -> None:
    with app.db_connect() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()


def _purge() -> None:
    keys = [EMP, OTHER_EMP]
    companies = [COMPANY, OTHER_COMPANY]
    _exec("DELETE FROM manager_scope_members WHERE scope_id IN (SELECT scope_id FROM manager_scopes WHERE company_code=%s)", (COMPANY,))
    for table in ("manager_scopes", "employee_org_assignments", "company_teams", "company_branches", "company_modules"):
        _exec(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
    for table in ("file_registry", "employee_documents", "compliance_documents", "onboarding_items"):
        _exec(f"DELETE FROM {table} WHERE company_code = ANY(%s)", (companies,))
        _exec(f"DELETE FROM {table} WHERE subject_key = ANY(%s)" if table == "file_registry" else f"DELETE FROM {table} WHERE employee_key = ANY(%s)", (keys,))
    _exec("DELETE FROM action_results WHERE company_code = ANY(%s)", (companies,))
    _exec("DELETE FROM employees WHERE company_code = ANY(%s)", (companies,))


def teardown() -> None:
    _purge()
    _exec("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY, OTHER_COMPANY],))
    app.os.environ.pop("WATHEFNI_ORG_HIERARCHY", None)
    try:
        import shutil
        for code in (COMPANY, OTHER_COMPANY):
            shutil.rmtree(app.WORKSPACE / "data" / "companies" / code, ignore_errors=True)
    except Exception:
        pass


def _upload(employee_key: str, item_id: str, filename: str, data: bytes, mime: str, ctx: dict[str, Any]):
    upload = UploadFile(file=io.BytesIO(data), filename=filename, headers=Headers({"content-type": mime}))
    return asyncio.run(app.dashboard_posthire_employee_document_upload(employee_key, file=upload, item_id=item_id, context=ctx))


def _denied(fn: Callable[[], Any], status_code: int) -> bool:
    try:
        fn()
        return False
    except app.HTTPException as exc:
        return exc.status_code == status_code


def _onboarding_status(emp_key: str, item_id: str) -> str | None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id=%s", (emp_key, item_id))
            row = cur.fetchone()
            return str(row["status"]) if row else None


def _file_registry_row(file_id: str) -> dict[str, Any] | None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM file_registry WHERE file_id=%s", (file_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def _employee_documents_row(emp_key: str) -> dict[str, Any] | None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM employee_documents WHERE employee_key=%s ORDER BY updated_at DESC LIMIT 1", (emp_key,))
            row = cur.fetchone()
            return dict(row) if row else None


def _compliance_documents_row(emp_key: str) -> dict[str, Any] | None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM compliance_documents WHERE employee_key=%s ORDER BY updated_at DESC LIMIT 1", (emp_key,))
            row = cur.fetchone()
            return dict(row) if row else None


def _audit_row() -> dict[str, Any] | None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM action_results WHERE company_code=%s AND action_type='document_uploaded' "
                "ORDER BY created_at DESC LIMIT 1",
                (COMPANY,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def run_checks(checks: Checks) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    # --- Flag must be live in this process env (set by the systemd flag + run env)
    checks.check("flag WATHEFNI_DOC_UPLOAD is ON", lambda: app.doc_upload_enabled() is True)

    # --- RBAC deny: viewer has onboarding.read but NOT onboarding.manage -> 403
    checks.check(
        "RBAC: viewer (read-only) denied manage upload (403)",
        lambda: _denied(lambda: _upload(EMP, ITEM, "dummy.pdf", DUMMY_PDF, "application/pdf", _ctx(role="viewer")), 403),
    )
    # --- Tenant deny: a different company's context cannot see this employee -> 404
    checks.check(
        "Tenant: cross-tenant context cannot upload (404)",
        lambda: _denied(lambda: _upload(EMP, ITEM, "dummy.pdf", DUMMY_PDF, "application/pdf", _ctx(company=OTHER_COMPANY)), 404),
    )
    # --- Manager scope deny: manager of Team B cannot touch Team A employee -> 404
    checks.check(
        "Manager scope: out-of-scope manager cannot upload (404)",
        lambda: _denied(lambda: _upload(EMP, ITEM, "dummy.pdf", DUMMY_PDF, "application/pdf", _ctx(MGR_OTHER_PHONE)), 404),
    )
    # --- Validation sanity (cheap, non-destructive)
    checks.check(
        "Validation: unsupported extension rejected (400)",
        lambda: _denied(lambda: _upload(EMP, ITEM, "dummy.exe", DUMMY_PDF, "application/octet-stream", _ctx()), 400),
    )

    # --- Happy path -----------------------------------------------------------
    checks.check("onboarding item starts pending", lambda: _onboarding_status(EMP, ITEM) == "pending")
    res = _upload(EMP, ITEM, "canary-id.pdf", DUMMY_PDF, "application/pdf", _ctx())
    captured["upload_result"] = res
    file_id = str(res.get("file_id") or "")
    checks.check("upload returns ok=True", lambda: res.get("ok") is True)
    checks.check("upload returns a file_id", lambda: bool(file_id))
    checks.check("onboarding item flipped to received", lambda: _onboarding_status(EMP, ITEM) == "received")

    # --- file_registry row ----------------------------------------------------
    fr = _file_registry_row(file_id) if file_id else None
    captured["file_registry"] = fr
    checks.check("file_registry row exists for file_id", lambda: fr is not None)
    checks.check("file_registry scoped to company", lambda: fr is not None and str(fr.get("company_code")) == COMPANY)
    checks.check("file_registry subject is the employee", lambda: fr is not None and str(fr.get("subject_key")) == EMP and str(fr.get("subject_type")) == "employee")
    checks.check("file_registry kind=onboarding_document", lambda: fr is not None and str(fr.get("file_kind")) == "onboarding_document")
    checks.check("file_registry has content_sha256", lambda: fr is not None and bool(fr.get("content_sha256")))

    # --- employee_documents linkage ------------------------------------------
    ed = _employee_documents_row(EMP)
    captured["employee_documents"] = ed
    checks.check("employee_documents row exists", lambda: ed is not None)
    checks.check("employee_documents linked to item_id", lambda: ed is not None and str(ed.get("item_id")) == ITEM)
    checks.check("employee_documents status=received", lambda: ed is not None and str(ed.get("status")) == "received")
    checks.check("employee_documents company scoped", lambda: ed is not None and str(ed.get("company_code")) == COMPANY)

    # --- compliance linkage (civil_id is a compliance type) ------------------
    cd = _compliance_documents_row(EMP)
    captured["compliance_documents"] = cd
    checks.check("compliance_documents row exists for civil_id", lambda: cd is not None and str(cd.get("document_type")) == ITEM)

    # --- document hub index + listing ----------------------------------------
    index = app.employee_document_index(COMPANY, EMP)
    checks.check("document index resolves item -> file_id", lambda: index.get(ITEM) == file_id)
    docs = app.employee_documents_for(COMPANY, EMP)
    captured["hub_documents"] = docs
    checks.check("hub lists exactly one document", lambda: len(docs) == 1 and str(docs[0]["file_id"]) == file_id)
    checks.check("hub document marked available (has_file)", lambda: docs and docs[0].get("has_file") is True)

    # --- view/download --------------------------------------------------------
    resolved = app.resolve_employee_document_file(COMPANY, file_id) if file_id else None
    captured["resolved"] = resolved
    checks.check("resolver returns tenant-scoped file", lambda: resolved is not None and str(resolved.get("subject_key")) == EMP)
    local_path = app.employee_document_local_path(resolved) if resolved else None
    captured["local_path"] = str(local_path) if local_path else None
    checks.check("file is downloadable from disk", lambda: local_path is not None)

    def _bytes_match() -> bool:
        if not local_path:
            return False
        with open(local_path, "rb") as fh:
            return fh.read() == DUMMY_PDF
    checks.check("downloaded bytes match uploaded bytes", _bytes_match)

    # --- audit row ------------------------------------------------------------
    audit = _audit_row()
    captured["audit"] = audit
    checks.check("audit row written (action_results: document_uploaded)", lambda: audit is not None)
    checks.check("audit row company scoped", lambda: audit is not None and str(audit.get("company_code")) == COMPANY)

    return captured


def _print_summary(captured: dict[str, Any]) -> None:
    print("\n=== CANARY EVIDENCE ===")
    res = captured.get("upload_result") or {}
    print(f"upload_result: ok={res.get('ok')} file_id={res.get('file_id')} storage_status={res.get('storage_status')}")
    fr = captured.get("file_registry") or {}
    if fr:
        print(f"file_registry: file_id={fr.get('file_id')} company={fr.get('company_code')} subject={fr.get('subject_type')}:{fr.get('subject_key')} "
              f"kind={fr.get('file_kind')} mime={fr.get('mime_type')} sha256={str(fr.get('content_sha256'))[:16]}... "
              f"size={fr.get('size_bytes') or fr.get('byte_size') or fr.get('size')} provider={fr.get('storage_provider') or fr.get('provider')}")
    ed = captured.get("employee_documents") or {}
    if ed:
        print(f"employee_documents: item_id={ed.get('item_id')} document_type={ed.get('document_type')} status={ed.get('status')} "
              f"company={ed.get('company_code')} provider={ed.get('storage_provider')}")
    cd = captured.get("compliance_documents") or {}
    if cd:
        print(f"compliance_documents: document_type={cd.get('document_type')} status={cd.get('status')}")
    print(f"hub_documents count={len(captured.get('hub_documents') or [])}")
    print(f"download local_path={captured.get('local_path')}")
    audit = captured.get("audit") or {}
    if audit:
        print(f"audit: result_id={audit.get('result_id')} action_type={audit.get('action_type')} status={audit.get('status')} "
              f"company={audit.get('company_code')} actor={audit.get('actor_user_id')} created_at={audit.get('created_at')}")


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"DOC-UPLOAD PROD CANARY — company {COMPANY} (postgres env: {env or 'default'})")
    setup()
    checks = Checks()
    captured: dict[str, Any] = {}
    try:
        captured = run_checks(checks)
    finally:
        _print_summary(captured)
        teardown()
        print("\n(canary artifacts purged)")
    code = checks.report()
    print("\nDOC-UPLOAD PROD CANARY: " + ("ALL CHECKS PASSED" if code == 0 else "FAILURES PRESENT"))
    sys.exit(code)


if __name__ == "__main__":
    main()
