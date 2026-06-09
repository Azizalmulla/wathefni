"""Employee Document Hub harness (staging).

The Document Hub closes the loop "WhatsApp/document upload -> stored file ->
dashboard visibility -> HR review". HR must be able to list and open an
employee's stored documents, but ONLY:
  - within their own tenant (never cross-company),
  - for files that physically exist (missing files degrade gracefully),
  - through the proxy (no raw local path is ever returned to the client),
  - with path-traversal blocked at the filesystem boundary,
  - gated on holding onboarding/compliance read on a company that has the module.

This drives the real helpers + the read-context gate behind the two endpoints
(employee_documents_for / employee_document_index / resolve_employee_document_file
/ employee_document_local_path / _document_hub_read_context). A green run means
the surfaces in onboarding, compliance, and Employee 360 all resolve files the
same safe way.

Run on a host with the orchestrator venv + (staging) database:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-document-hub.py

NEVER point this at the production database: it writes and deletes a company.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

try:
    import app
    from psycopg2.extras import Json
except ModuleNotFoundError as exc:
    if exc.name in {"psycopg2", "app"} or (exc.name or "").startswith("psycopg2"):
        print("SKIP: psycopg2 not available locally; full run happens on staging.")
        sys.exit(0)
    raise

COMPANY = "DOCHUBTESTCO"
OTHER_COMPANY = "DOCHUBOTHERCO"
MARKER = "temporary_document_hub_harness"

EMP = f"dochub-emp-{COMPANY}"
PHONE = "96550000000701"
MODULES = ["onboarding", "compliance"]


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


def _ctx(company: str, permissions: list[str]) -> dict[str, Any]:
    return {
        "company_code": company,
        "permissions": permissions,
        "access": {"role": "owner", "permissions": permissions},
        "actor_role": "owner",
    }


def _employees_columns(cur: Any) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='employees'")
    return {row["column_name"] for row in cur.fetchall()}


def _insert_employee(cur: Any, columns: set[str], company: str, emp_key: str, phone: str, name: str) -> None:
    desired: dict[str, Any] = {
        "company_code": company,
        "phone": phone,
        "name": name,
        "email": f"{emp_key}@example.com",
        "employee_key": emp_key,
        "onboarding_status": "in_progress",
        "status": "active",
        "raw_json": Json({"smoke": MARKER, "name": name}),
        "profile": Json({"smoke": MARKER}),
    }
    cols = [c for c in desired if c in columns]
    placeholders = ",".join(["%s"] * len(cols))
    cur.execute(f"INSERT INTO employees ({','.join(cols)}) VALUES ({placeholders})", [desired[c] for c in cols])


def _local_doc_path() -> Path:
    # A real file INSIDE the workspace root, so the path-traversal guard accepts it.
    root = Path(app.WORKSPACE)
    root.mkdir(parents=True, exist_ok=True)
    p = root / f"_dochub_smoke_{EMP}.txt"
    p.write_text("smoke document bytes", encoding="utf-8")
    return p


def _insert_file(cur: Any, *, company: str, document_type: str, file_kind: str, status: str,
                 local_path: str | None, storage_url: str | None, provider: str,
                 item_id: str | None = None, filename: str = "doc.pdf") -> str:
    cur.execute(
        """
        INSERT INTO file_registry
          (company_code, subject_type, subject_key, file_kind, document_type,
           original_filename, local_path, storage_provider, storage_url,
           mime_type, size_bytes, storage_status, metadata, stored_at, updated_at)
        VALUES (%s,'employee',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), now())
        RETURNING file_id
        """,
        (company, EMP, file_kind, document_type, filename, local_path, provider,
         storage_url, "application/pdf", 1234, status,
         Json({"smoke": MARKER, **({"item_id": item_id} if item_id else {})})),
    )
    return str(cur.fetchone()["file_id"])


STATE: dict[str, Any] = {}


def setup() -> None:
    _purge()
    local_path = _local_doc_path()
    STATE["local_path"] = local_path
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY, OTHER_COMPANY):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO UPDATE SET metadata=EXCLUDED.metadata",
                    (company, "Doc Hub Harness", Json({"smoke": MARKER, "modules": MODULES}), Json({"smoke": MARKER})),
                )
            columns = _employees_columns(cur)
            _insert_employee(cur, columns, COMPANY, EMP, PHONE, "Doc Holder")
            # 1) Local, stored, with a real file + onboarding item_id.
            STATE["local_file_id"] = _insert_file(
                cur, company=COMPANY, document_type="civil_id", file_kind="onboarding_document",
                status="stored", local_path=str(local_path), storage_url="local://" + str(local_path),
                provider="local", item_id="civil_id_item",
            )
            # 2) External (Google Drive) stored file — link, no local bytes.
            STATE["external_file_id"] = _insert_file(
                cur, company=COMPANY, document_type="passport", file_kind="compliance_document",
                status="stored", local_path=None, storage_url="https://drive.google.com/file/d/abc/view",
                provider="google_drive",
            )
            # 3) Pending/missing — stored row absent on disk.
            STATE["missing_file_id"] = _insert_file(
                cur, company=COMPANY, document_type="medical", file_kind="compliance_document",
                status="pending", local_path=str(local_path) + ".nope", storage_url=None,
                provider="local",
            )
            # 4) A file under the OTHER company (cross-tenant probe). Distinct
            # employee_key — the employees PK is the key alone (tenant-agnostic).
            _insert_employee(cur, columns, OTHER_COMPANY, f"{EMP}-other", "96550000000702", "Other Holder")
            STATE["other_file_id"] = _insert_file(
                cur, company=OTHER_COMPANY, document_type="civil_id", file_kind="onboarding_document",
                status="stored", local_path=str(local_path), storage_url="local://x",
                provider="local",
            )
        conn.commit()


def _purge() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY, OTHER_COMPANY):
                cur.execute("DELETE FROM file_registry WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM employees WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM company_modules WHERE company_code=%s", (company,))
        conn.commit()


def teardown() -> None:
    _purge()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY, OTHER_COMPANY):
                cur.execute("DELETE FROM companies WHERE company_code=%s", (company,))
        conn.commit()
    lp = STATE.get("local_path")
    if isinstance(lp, Path) and lp.exists():
        lp.unlink()


def run_checks(checks: Checks) -> None:
    # --- Listing: metadata only, never bytes / local path -------------------
    docs = app.employee_documents_for(COMPANY, EMP)
    checks.check("lists all 3 of the employee's documents", lambda: len(docs) == 3)
    leaky = {"local_path", "source_path", "storage_object_key", "content_sha256"}
    checks.check("listing never leaks filesystem/storage internals", lambda: all(leaky.isdisjoint(d.keys()) for d in docs))
    checks.check("listing marks the stored local file as available", lambda: any(d["file_id"] == STATE["local_file_id"] and d["has_file"] for d in docs))
    checks.check("listing marks the pending file as unavailable", lambda: any(d["file_id"] == STATE["missing_file_id"] and not d["has_file"] for d in docs))

    # --- Document index: keyed by item_id AND document_type -----------------
    index = app.employee_document_index(COMPANY, EMP)
    checks.check("index resolves by onboarding item_id", lambda: index.get("civil_id_item") == STATE["local_file_id"])
    checks.check("index resolves by document_type", lambda: index.get("passport") == STATE["external_file_id"])
    checks.check("index omits files with no stored bytes", lambda: "medical" not in index)

    # --- Tenant isolation on the serve resolver -----------------------------
    checks.check("resolves an in-tenant file", lambda: (app.resolve_employee_document_file(COMPANY, STATE["local_file_id"]) or {}).get("file_id") is not None)
    checks.check("does NOT resolve a cross-tenant file", lambda: app.resolve_employee_document_file(COMPANY, STATE["other_file_id"]) is None)
    checks.check("does NOT resolve other tenant's view of our file", lambda: app.resolve_employee_document_file(OTHER_COMPANY, STATE["local_file_id"]) is None)
    checks.check("malformed file_id returns None (no raise)", lambda: app.resolve_employee_document_file(COMPANY, "not-a-uuid") is None)

    # --- Local path safety ---------------------------------------------------
    local_doc = app.resolve_employee_document_file(COMPANY, STATE["local_file_id"])
    checks.check("local path resolves to the real on-disk file", lambda: app.employee_document_local_path(local_doc) == STATE["local_path"].resolve())
    missing_doc = app.resolve_employee_document_file(COMPANY, STATE["missing_file_id"])
    checks.check("missing on-disk file yields no path", lambda: app.employee_document_local_path(missing_doc) is None)
    checks.check("path-traversal outside workspace is refused", lambda: app.employee_document_local_path({"local_path": "/etc/passwd"}) is None)
    external_doc = app.resolve_employee_document_file(COMPANY, STATE["external_file_id"])
    checks.check("external (drive) doc carries a storage_url, no local path", lambda: bool(external_doc.get("storage_url")) and app.employee_document_local_path(external_doc) is None)

    # --- RBAC / module gate on the read context -----------------------------
    owner = sorted(app.hr_role_permissions("owner"))
    checks.check("owner with module passes the read gate", lambda: app._document_hub_read_context(_ctx(COMPANY, owner)) == COMPANY)
    checks.check("user without onboarding/compliance read is denied (403)", lambda: _denied(_ctx(COMPANY, ["attendance.read"])))
    checks.check("company without the modules is denied (403)", lambda: _denied(_ctx("ZZ_NO_MODULES", owner)))


def _denied(context: dict[str, Any]) -> bool:
    try:
        app._document_hub_read_context(context)
        return False
    except app.HTTPException as exc:
        return exc.status_code == 403


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"document hub harness — company {COMPANY} (env: {env or 'default'})")
    try:
        import psycopg2  # noqa: F401
    except ModuleNotFoundError:
        print("SKIP: psycopg2 not available locally; full run happens on staging.")
        sys.exit(0)
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nDOCUMENT HUB: FAILURES PRESENT")
    else:
        print("\nDOCUMENT HUB: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
