"""Assistant HR read tools harness (staging).

Covers the two read-only Assistant tools that let the Wathefni Assistant answer
onboarding / compliance / document-status questions using the SAME source of
truth as the dashboard:

  * list_onboarding_status      (onboarding.read)
  * list_compliance_documents   (compliance.read)

What this asserts:
  * Registration + schema flag gate: the tools are only offered to the LLM when
    WATHEFNI_ASSISTANT_HR_READS is on (default OFF -> not in build_tool_schemas).
  * RBAC: TOOL_PERMISSION_MAP maps each tool to its .read permission; a viewer
    without that permission cannot run / see it.
  * Tenant isolation: reads never cross company_code.
  * Manager scope: a scoped manager (viewer_phone) only sees their own people.
  * Dashboard parity: tool output matches dashboard_compliance_payload exactly,
    and onboarding "missing document" matches the onboarding checklist truth.
  * No raw data leakage: replies / rows never carry file ids, urls, storage
    paths, or bytes.
  * Full registry executor path (ExecutionContext -> spec.executor) produces a
    clean, HR-friendly safe_user_message with requires_confirmation off.

Run on a host with the orchestrator venv + (staging) database:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-assistant-hr-reads.py

NEVER point this at the production database: it writes and deletes companies.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any, Callable

try:
    import app
    import action_registry
    import tool_call_orchestrator as tco
    from psycopg2.extras import Json
except ModuleNotFoundError as exc:
    if exc.name in {"psycopg2", "app", "action_registry", "tool_call_orchestrator"} or (exc.name or "").startswith("psycopg2"):
        print("SKIP: psycopg2/app not available locally; full run happens on staging.")
        sys.exit(0)
    raise

COMPANY = "ASSTHRREADSCO"
OTHERCO = "ASSTHRREADSOTHER"
MARKER = "temporary_assistant_hr_reads_harness"

EMP1 = f"asst-emp1-{COMPANY}"   # Team A, in_progress, expired civil_id + expiring passport + needs-review medical
EMP2 = f"asst-emp2-{COMPANY}"   # Team B, complete, valid civil_id
EMP3 = f"asst-emp3-{COMPANY}"   # Team B, not_started, pending civil_id
OTHER_EMP = f"asst-emp-{OTHERCO}"  # different tenant

PHONE1, PHONE2, PHONE3, OTHER_PHONE = "96550000000701", "96550000000702", "96550000000703", "96550000000704"

BRANCH_KEY = app.org_key(COMPANY, "branch", "HQ")
TEAM_A_KEY = app.org_key(COMPANY, "team", "Team A")
TEAM_B_KEY = app.org_key(COMPANY, "team", "Team B")
MGR_TEAM_B_PHONE = "96550000000710"  # manages Team B -> sees EMP2/EMP3, never EMP1

FLAG = "WATHEFNI_ASSISTANT_HR_READS"

# Keys that would constitute raw-document leakage if they ever reached a reply.
LEAK_KEYS = ("file_id", "file_url", "url", "storage_path", "path", "local_path", "bytes", "file_path", "storage_url")
LEAK_TEXT = ("http://", "https://", "/data/", "/companies/", "file_id", "storage")


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
        app.os.environ[FLAG] = "on"
    else:
        app.os.environ.pop(FLAG, None)


def _columns(cur: Any, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    return {r["column_name"] for r in cur.fetchall()}


def _insert_employee(cur: Any, columns: set[str], company: str, emp_key: str, phone: str, name: str, status: str) -> None:
    desired: dict[str, Any] = {
        "company_code": company, "phone": phone, "name": name,
        "email": f"{emp_key}@example.com", "employee_key": emp_key,
        "onboarding_status": status, "status": "active",
        "department": "Ops",
        "raw_json": Json({"smoke": MARKER}), "profile": Json({"smoke": MARKER}),
    }
    cols = [c for c in desired if c in columns]
    cur.execute(f"INSERT INTO employees ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})", [desired[c] for c in cols])


def _insert_item(cur: Any, columns: set[str], company: str, emp_key: str, item_id: str, label: str, status: str, required: bool = True) -> None:
    desired: dict[str, Any] = {
        "company_code": company, "employee_key": emp_key, "item_id": item_id,
        "label": label, "item_type": "document", "document_type": item_id,
        "required": required, "status": status,
    }
    cols = [c for c in desired if c in columns]
    cur.execute(f"INSERT INTO onboarding_items ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})", [desired[c] for c in cols])


def _insert_compliance(cur: Any, columns: set[str], company: str, emp_key: str, document_type: str, label: str, status: str, expiry: Any, warning_days: int = 30) -> None:
    desired: dict[str, Any] = {
        "company_code": company, "employee_key": emp_key, "document_type": document_type,
        "label": label, "status": status, "expiry_date": expiry, "warning_days": warning_days,
        "updated_at": app.now_utc(),
    }
    cols = [c for c in desired if c in columns]
    cur.execute(f"INSERT INTO compliance_documents ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})", [desired[c] for c in cols])


def setup() -> None:
    _purge()
    today = app.now_utc().date()
    from datetime import timedelta
    expired = today - timedelta(days=10)
    expiring = today + timedelta(days=3)
    valid = today + timedelta(days=365)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY, OTHERCO):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO UPDATE SET metadata=EXCLUDED.metadata",
                    (company, "Assistant HR Reads Harness", Json({"smoke": MARKER, "modules": ["onboarding", "compliance"]}), Json({"smoke": MARKER})),
                )
            # Explicit module rows so company_has_module is true for _visible_tools.
            mod_cols = _columns(cur, "company_modules")
            for module in ("onboarding", "compliance"):
                desired = {"company_code": COMPANY, "module_key": module, "enabled": True}
                cols = [c for c in desired if c in mod_cols]
                cur.execute(
                    f"INSERT INTO company_modules ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))}) ON CONFLICT DO NOTHING",
                    [desired[c] for c in cols],
                )

            emp_cols = _columns(cur, "employees")
            item_cols = _columns(cur, "onboarding_items")
            comp_cols = _columns(cur, "compliance_documents")

            _insert_employee(cur, emp_cols, COMPANY, EMP1, PHONE1, "Alpha Pending", "in_progress")
            _insert_employee(cur, emp_cols, COMPANY, EMP2, PHONE2, "Bravo Complete", "complete")
            _insert_employee(cur, emp_cols, COMPANY, EMP3, PHONE3, "Charlie NotStarted", "not_started")
            _insert_employee(cur, emp_cols, OTHERCO, OTHER_EMP, OTHER_PHONE, "Other Tenant", "in_progress")

            # Onboarding items
            _insert_item(cur, item_cols, COMPANY, EMP1, "civil_id", "Civil ID", "pending")
            _insert_item(cur, item_cols, COMPANY, EMP1, "passport", "Passport", "pending")
            _insert_item(cur, item_cols, COMPANY, EMP1, "bank_details", "Bank Details", "received")
            _insert_item(cur, item_cols, COMPANY, EMP2, "civil_id", "Civil ID", "received")
            _insert_item(cur, item_cols, COMPANY, EMP3, "civil_id", "Civil ID", "pending")
            _insert_item(cur, item_cols, OTHERCO, OTHER_EMP, "civil_id", "Civil ID", "pending")

            # Compliance documents
            _insert_compliance(cur, comp_cols, COMPANY, EMP1, "civil_id", "Civil ID", "active", expired)
            _insert_compliance(cur, comp_cols, COMPANY, EMP1, "passport", "Passport", "active", expiring)
            _insert_compliance(cur, comp_cols, COMPANY, EMP1, "medical", "Medical", "received", None)  # needs review
            _insert_compliance(cur, comp_cols, COMPANY, EMP2, "civil_id", "Civil ID", "active", valid)
            _insert_compliance(cur, comp_cols, OTHERCO, OTHER_EMP, "civil_id", "Civil ID", "active", expired)
        conn.commit()

    # Org scope so the manager probe has a real out-of-scope target (EMP1=Team A).
    app.os.environ["WATHEFNI_ORG_HIERARCHY"] = "on"
    app.upsert_org_branch(COMPANY, name="HQ", branch_key=BRANCH_KEY)
    app.upsert_org_team(COMPANY, name="Team A", branch_key=BRANCH_KEY, team_key=TEAM_A_KEY)
    app.upsert_org_team(COMPANY, name="Team B", branch_key=BRANCH_KEY, team_key=TEAM_B_KEY)
    app.set_employee_org_assignment(COMPANY, employee_key=EMP1, team_key=TEAM_A_KEY)
    app.set_employee_org_assignment(COMPANY, employee_key=EMP2, team_key=TEAM_B_KEY)
    app.set_employee_org_assignment(COMPANY, employee_key=EMP3, team_key=TEAM_B_KEY)
    app.upsert_manager_scope(COMPANY, manager_phone=MGR_TEAM_B_PHONE, scope_type="team", team_key=TEAM_B_KEY)


def _exec(sql: str, params: tuple) -> None:
    with app.db_connect() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()


def _purge() -> None:
    keys = [EMP1, EMP2, EMP3, OTHER_EMP]
    _exec("DELETE FROM manager_scope_members WHERE scope_id IN (SELECT scope_id FROM manager_scopes WHERE company_code=%s)", (COMPANY,))
    for table in ("manager_scopes", "employee_org_assignments", "company_teams", "company_branches", "company_modules"):
        _exec(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
    for table in ("file_registry", "employee_documents", "compliance_documents", "onboarding_items"):
        for company in (COMPANY, OTHERCO):
            _exec(f"DELETE FROM {table} WHERE company_code=%s", (company,))
        _exec(f"DELETE FROM {table} WHERE subject_key = ANY(%s)" if table == "file_registry" else f"DELETE FROM {table} WHERE employee_key = ANY(%s)", (keys,))
    for company in (COMPANY, OTHERCO):
        _exec("DELETE FROM employees WHERE company_code=%s", (company,))


def teardown() -> None:
    _purge()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY, OTHERCO],))
        conn.commit()
    _flag(False)
    app.os.environ.pop("WATHEFNI_ORG_HIERARCHY", None)


def _action(viewer_phone: str | None = None, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"company_code": COMPANY}
    if viewer_phone:
        base["viewer_phone"] = viewer_phone
    base.update(extra)
    return base


def _names(result: dict[str, Any]) -> set[str]:
    return {str(r.get("employee_name") or "") for r in (result.get("rows") or [])}


def _bucket_set(payload: dict[str, Any], bucket: str) -> set[tuple[str, str]]:
    return {(str(d.get("employee_key")), str(d.get("document_type"))) for d in payload.get("documents", []) if d.get("status") == bucket}


def _tool_set(result: dict[str, Any]) -> set[tuple[str, str]]:
    # tool rows don't carry employee_key (metadata only); join on name -> key via cards is overkill,
    # so parity uses (employee_name, document_type) which is unique within the harness.
    return {(str(r.get("employee_name")), str(r.get("document_type"))) for r in (result.get("rows") or [])}


def _payload_name_set(payload: dict[str, Any], bucket: str) -> set[tuple[str, str]]:
    return {(str(d.get("employee_name")), str(d.get("document_type"))) for d in payload.get("documents", []) if d.get("status") == bucket}


def _no_leak_rows(result: dict[str, Any]) -> bool:
    for r in (result.get("rows") or []):
        if any(k in r for k in LEAK_KEYS):
            return False
    return True


def _no_leak_text(text: str) -> bool:
    low = (text or "").lower()
    return not any(token in low for token in LEAK_TEXT)


def _exec_via_registry(name: str, viewer_phone: str | None = None, **args: Any) -> dict[str, Any]:
    spec = action_registry.REGISTRY[name]
    request = SimpleNamespace(sender_phone=viewer_phone, company_code=COMPANY)
    action = {"company_code": COMPANY, **args}
    ctx = action_registry.ExecutionContext(request, action, {}, {}, {}, app)
    return spec.executor(ctx)


def run_checks(checks: Checks) -> None:
    # --- Registration + schema flag gate ------------------------------------
    checks.check("list_onboarding_status registered", lambda: "list_onboarding_status" in action_registry.REGISTRY)
    checks.check("list_compliance_documents registered", lambda: "list_compliance_documents" in action_registry.REGISTRY)
    checks.check("onboarding read tool is onboarding module", lambda: action_registry.REGISTRY["list_onboarding_status"].module == "onboarding")
    checks.check("compliance read tool is compliance module", lambda: action_registry.REGISTRY["list_compliance_documents"].module == "compliance")
    checks.check("onboarding read tool not sensitive / no confirmation", lambda: action_registry.REGISTRY["list_onboarding_status"].requires_confirmation is False)
    checks.check("compliance read tool not sensitive / no confirmation", lambda: action_registry.REGISTRY["list_compliance_documents"].requires_confirmation is False)

    req = SimpleNamespace(sender_phone=None, company_code=COMPANY)
    _flag(False)
    checks.check("flag defaults OFF", lambda: app.assistant_hr_reads_enabled() is False)

    def _schema_names() -> set[str]:
        return {str((t.get("function") or {}).get("name")) for t in action_registry.build_tool_schemas(app, req)}

    checks.check("tools hidden from LLM schema while flag OFF", lambda: not ({"list_onboarding_status", "list_compliance_documents"} & _schema_names()))
    _flag(True)
    checks.check("flag flips ON", lambda: app.assistant_hr_reads_enabled() is True)
    checks.check("both tools exposed to LLM schema while flag ON", lambda: {"list_onboarding_status", "list_compliance_documents"} <= _schema_names())

    # --- RBAC ----------------------------------------------------------------
    checks.check("onboarding read tool -> onboarding.read", lambda: tco.TOOL_PERMISSION_MAP.get("list_onboarding_status") == "onboarding.read")
    checks.check("compliance read tool -> compliance.read", lambda: tco.TOOL_PERMISSION_MAP.get("list_compliance_documents") == "compliance.read")
    checks.check("viewer with onboarding.read may run onboarding read", lambda: tco._tool_allowed("list_onboarding_status", {"permissions": ["onboarding.read"]})[0] is True)
    checks.check("viewer without onboarding.read denied onboarding read", lambda: tco._tool_allowed("list_onboarding_status", {"permissions": ["leave.read"]})[0] is False)
    checks.check("viewer with compliance.read may run compliance read", lambda: tco._tool_allowed("list_compliance_documents", {"permissions": ["compliance.read"]})[0] is True)
    checks.check("viewer without compliance.read denied compliance read", lambda: tco._tool_allowed("list_compliance_documents", {"permissions": ["onboarding.read"]})[0] is False)

    def _visible(perms: list[str]) -> set[str]:
        scope = {"company_id": COMPANY, "permissions": perms}
        return {str((t.get("function") or {}).get("name")) for t in tco._visible_tools(action_registry.build_tool_schemas(app, req), scope)}

    checks.check("catalog shows both reads for a full HR reader", lambda: {"list_onboarding_status", "list_compliance_documents"} <= _visible(["onboarding.read", "compliance.read"]))
    checks.check("catalog hides compliance read from an onboarding-only reader", lambda: "list_compliance_documents" not in _visible(["onboarding.read"]))

    # --- Onboarding reads ----------------------------------------------------
    missing_civil = app.list_onboarding_status(_action(document_type="civil_id"), company_code=COMPANY)
    checks.check("missing Civil ID flags EMP1 + EMP3 (pending), not EMP2 (received)", lambda: _names(missing_civil) == {"Alpha Pending", "Charlie NotStarted"})

    missing_passport = app.list_onboarding_status(_action(document_type="passport"), company_code=COMPANY)
    checks.check("no passport uploaded flags only EMP1 (only one with a passport item)", lambda: _names(missing_passport) == {"Alpha Pending"})

    pending = app.list_onboarding_status(_action(pending_only=True), company_code=COMPANY)
    checks.check("pending onboarding items flags EMP1 + EMP3", lambda: _names(pending) == {"Alpha Pending", "Charlie NotStarted"})

    not_complete = app.list_onboarding_status(_action(), company_code=COMPANY)
    checks.check("not-completed onboarding flags EMP1 + EMP3, excludes EMP2", lambda: _names(not_complete) == {"Alpha Pending", "Charlie NotStarted"})

    completed = app.list_onboarding_status(_action(status="complete"), company_code=COMPANY)
    checks.check("completed onboarding flags only EMP2", lambda: _names(completed) == {"Bravo Complete"})

    # --- Compliance reads ----------------------------------------------------
    payload = app.dashboard_compliance_payload(COMPANY)
    expired = app.list_compliance_documents(_action(status="expired"), company_code=COMPANY)
    checks.check("expired documents flags EMP1 Civil ID", lambda: _tool_set(expired) == {("Alpha Pending", "civil_id")})
    checks.check("expired parity with dashboard payload", lambda: _tool_set(expired) == _payload_name_set(payload, "expired"))

    expiring = app.list_compliance_documents(_action(status="expiring_soon"), company_code=COMPANY)
    checks.check("expiring-soon flags EMP1 Passport", lambda: _tool_set(expiring) == {("Alpha Pending", "passport")})
    checks.check("expiring-soon parity with dashboard payload", lambda: _tool_set(expiring) == _payload_name_set(payload, "expiring_soon"))

    needs_review = app.list_compliance_documents(_action(status="needs_review"), company_code=COMPANY)
    checks.check("needs-review flags EMP1 Medical", lambda: _tool_set(needs_review) == {("Alpha Pending", "medical")})

    this_month = app.list_compliance_documents(_action(status="expiring_soon", timeframe="this_month"), company_code=COMPANY)
    checks.check("expiring this-month rows are a subset of expiring-soon", lambda: _tool_set(this_month) <= _tool_set(expiring))
    checks.check("expiring this-month rows all fall in the current month", lambda: all(app._assistant_expiry_in_current_month(r.get("expiry_date")) for r in this_month.get("rows", [])))

    # --- Tenant isolation ----------------------------------------------------
    checks.check("onboarding read never crosses tenant (no Other Tenant)", lambda: "Other Tenant" not in _names(missing_civil))
    checks.check("compliance read never crosses tenant (no Other Tenant)", lambda: all(r.get("employee_name") != "Other Tenant" for r in expired.get("rows", [])))
    other_payload = app.list_compliance_documents(_action(status="expired"), company_code=OTHERCO)
    checks.check("OTHERCO sees only its own expired doc", lambda: _tool_set(other_payload) == {("Other Tenant", "civil_id")})

    # --- Manager scope -------------------------------------------------------
    mgr_not_complete = app.list_onboarding_status(_action(MGR_TEAM_B_PHONE), company_code=COMPANY)
    checks.check("Team B manager sees only EMP3 (EMP1 out of scope, EMP2 complete)", lambda: _names(mgr_not_complete) == {"Charlie NotStarted"})
    mgr_expired = app.list_compliance_documents(_action(MGR_TEAM_B_PHONE, status="expired"), company_code=COMPANY)
    checks.check("Team B manager sees no expired docs (EMP1 out of scope)", lambda: _tool_set(mgr_expired) == set())

    # --- No raw data leakage -------------------------------------------------
    checks.check("compliance rows carry no file id / url / path / bytes", lambda: _no_leak_rows(expired) and _no_leak_rows(expiring) and _no_leak_rows(needs_review))
    checks.check("onboarding rows carry no file id / url / path / bytes", lambda: _no_leak_rows(missing_civil) and _no_leak_rows(pending) and _no_leak_rows(not_complete))

    # --- Full registry executor path (reply formatting + normalization) ------
    exec_onb = _exec_via_registry("list_onboarding_status", document_type="civil_id")
    checks.check("registry onboarding executor succeeds", lambda: exec_onb.get("success") is True and exec_onb.get("action_type") == "list_onboarding_status")
    checks.check("registry onboarding reply is HR-friendly + names the people", lambda: "missing Civil ID" in exec_onb.get("message", "") and "Alpha Pending" in exec_onb.get("message", ""))
    checks.check("registry onboarding reply leaks nothing", lambda: _no_leak_text(exec_onb.get("message", "")))

    exec_comp = _exec_via_registry("list_compliance_documents", status="expired")
    checks.check("registry compliance executor succeeds", lambda: exec_comp.get("success") is True and exec_comp.get("action_type") == "list_compliance_documents")
    checks.check("registry compliance reply summarizes expired docs", lambda: "expired document" in exec_comp.get("message", "") and "Alpha Pending" in exec_comp.get("message", ""))
    checks.check("registry compliance reply leaks nothing", lambda: _no_leak_text(exec_comp.get("message", "")))

    exec_mgr = _exec_via_registry("list_onboarding_status", MGR_TEAM_B_PHONE, document_type="civil_id")
    checks.check("registry executor honors manager scope via sender_phone", lambda: "Alpha Pending" not in exec_mgr.get("message", "") and "Charlie NotStarted" in exec_mgr.get("message", ""))


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"assistant HR reads harness — company {COMPANY} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nASSISTANT HR READS: FAILURES PRESENT")
    else:
        print("\nASSISTANT HR READS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
