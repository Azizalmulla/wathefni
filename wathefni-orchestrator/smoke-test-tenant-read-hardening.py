from __future__ import annotations

from pathlib import Path


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    root = Path(__file__).resolve().parent
    app_source = (root / "app.py").read_text(encoding="utf-8")
    toolcall_source = (root / "tool_call_orchestrator.py").read_text(encoding="utf-8")

    # Per-turn tenant scope primitives exist.
    assert_true("def resolved_company_scope(" in app_source, "resolved_company_scope helper must exist")
    assert_true("def set_active_company_code(" in app_source, "set_active_company_code must exist")
    assert_true("def reset_active_company_code(" in app_source, "reset_active_company_code must exist")
    assert_true("contextvars.ContextVar" in app_source, "active company must be tracked via contextvars")

    # Helper signatures accept company scope and fail closed.
    assert_true("def infer_position_filter_from_text(text: str, *, company_code: str | None = None)" in app_source, "position inference must take company scope")
    assert_true("def application_mentioned_in_text(text: str, *, company_code: str | None = None)" in app_source, "application name match must take company scope")
    assert_true("def employee_mentioned_in_text(text: str, *, company_code: str | None = None)" in app_source, "employee name match must take company scope")
    assert_true("def _fuzzy_candidate_phones_by_name(name: str, *, threshold: float, limit: int, company_code: str | None = None)" in app_source, "candidate fuzzy lookup must take company scope")

    # Fail-closed guards present in each scoped helper.
    for needle in (
        "    company = resolved_company_scope(company_code)\n    if not company:\n        return None",
    ):
        assert_true(needle in app_source, "scoped helpers must fail closed when no company is resolved")
    assert_true("    if not company:\n        return []" in app_source, "fuzzy/candidate helpers must fail closed with empty list")

    # Company filter is applied in the SQL of the previously-global reads.
    assert_true("FROM positions\n                WHERE company_code=%s" in app_source, "position inference must filter by company_code")
    assert_true("JOIN candidates c ON c.phone = a.phone\n                WHERE a.company_code=%s" in app_source, "application name match must filter by company_code")
    assert_true("FROM employees WHERE company_code=%s ORDER BY updated_at DESC LIMIT 200" in app_source, "employee name match must filter by company_code")
    assert_true("EXISTS (SELECT 1 FROM applications a WHERE a.phone = c.phone AND a.company_code = %s)" in app_source, "fuzzy candidate name lookup must be company-scoped via applications")
    assert_true("EXISTS (SELECT 1 FROM applications a WHERE a.phone = cd.phone AND a.company_code = %s)" in app_source, "fuzzy candidate filename lookup must be company-scoped via applications")

    # candidate_matches_from_text no longer defaults to a hardcoded tenant.
    assert_true("def candidate_matches_from_text(text: str | None, *, company_code: str | None = None" in app_source, "candidate_matches_from_text must not default to a hardcoded company")
    assert_true("def find_application_by_candidate_name(name: str | None, company_code: str | None = None)" in app_source, "application-by-name lookup signature preserved")

    # Hot-path DB safety: pool + schema run-once guard.
    assert_true("psycopg2.pool.ThreadedConnectionPool" in app_source, "connection pool must be used")
    assert_true("class _DbConnection" in app_source, "pooled connection context manager must exist")
    assert_true("def ensure_schema(force: bool = False)" in app_source, "ensure_schema must support a run-once guard with force override")
    assert_true("_SCHEMA_READY" in app_source and "def _ensure_schema_impl(" in app_source, "ensure_schema must guard against repeated DDL on hot paths")

    # Tenant pinned at the turn entrypoints.
    assert_true("set_active_company_code(request_company_code(request))" in app_source, "whatsapp turn must pin tenant scope")
    assert_true("legacy.set_active_company_code(company_scope)" in toolcall_source, "toolcall turn must pin tenant scope")
    assert_true("legacy.reset_active_company_code(token)" in toolcall_source, "toolcall turn must reset tenant scope")

    print("tenant read hardening smoke tests passed")


if __name__ == "__main__":
    main()
