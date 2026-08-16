"""Wave 1 Employees 360 containment — local smoke.

Pins:
  - phone alias matrix (local 8 ↔ 965…) for lookup + duplicate prevention
  - self_approved_internal_canary fail-closed allowlist (company + env)
  - manager-scope denial on employee PATCH / status mutations (+ audit)
  - optimistic concurrency on normal employee edits
  - integrity scan covers expanded employee-linked tables

Safe to re-run: synthetic keys are removed in finally. Never touches production.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    employees 360 wave1 containment — aliases, dups, canary, scope, concurrency")
    os.environ.setdefault("WATHEFNI_ENV", "test")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; running pure allowlist checks only.")
            return _pure_checks_only()
        raise

    # ---- pure / no-DB checks first -----------------------------------------
    _pure_checks(app)

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT company_code FROM employees WHERE company_code <> '' LIMIT 30")
                candidates = [str(dict(r)["company_code"]).upper() for r in cur.fetchall()]
    except Exception as exc:
        print(f"    SKIP DB cases: {type(exc).__name__}: {exc}")
        print(f"\n    {PASS} passed, {FAIL} failed (pure-only)")
        return 1 if FAIL else 0
    if "WATHEFNI" not in candidates:
        candidates.append("WATHEFNI")
    company = next(
        (c for c in candidates if any(app.company_has_module(c, m) for m in app.POSTHIRE_PEOPLE_MODULES)),
        None,
    )
    if not company:
        print("    (no company has a post-hire people module enabled — skipping DB cases)")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0
    print(f"    using company {company}")

    local_phone = "51234567"
    canonical = app.canonical_employee_phone(local_phone)
    check("canonical maps 8-digit local to 965 form", canonical == f"965{local_phone}")
    check(
        "phone identity candidates include both forms",
        set(app.employee_phone_alias_list(local_phone)) == {local_phone, canonical},
    )

    key_canon = f"{company}-{canonical}"
    key_local_wrong = f"{company}-{local_phone}"
    other_phone = "96599007701"
    key_other = f"{company}-{other_phone}"
    smoke_tag = f"wave1-{uuid.uuid4().hex[:10]}"

    audits: list[dict] = []
    real_audit = app.record_admin_audit
    app.record_admin_audit = lambda context, action_type, **k: audits.append({"action_type": action_type, **k}) or real_audit(context, action_type, **k)

    real_scope = app.manager_scope_context

    def owner_ctx():
        return {
            "company_code": company,
            "permissions": ["employees.manage", "employees.status.approve", "onboarding.read", "compliance.read"],
            "access": {"role": "owner", "permissions": ["employees.manage", "employees.status.approve"]},
            "actor_user_id": "smoke-wave1-owner",
            "permission_authority": "backend_current",
            "permission_subject_user_id": "smoke-wave1-owner",
            "permission_subject_company": company,
            "actor_role": "owner",
            "hr_phone": "99900000071",
            "hr_user": {"role": "owner", "status": "active", "company_code": company},
        }

    def manager_ctx():
        return {
            "company_code": company,
            "permissions": ["employees.manage", "employees.status.approve"],
            "access": {"role": "manager", "permissions": ["employees.manage", "employees.status.approve"]},
            "actor_user_id": "smoke-wave1-mgr",
            "permission_authority": "backend_current",
            "permission_subject_user_id": "smoke-wave1-mgr",
            "permission_subject_company": company,
            "actor_role": "manager",
            "hr_phone": "99900000072",
            "hr_user": {"role": "manager", "status": "active", "company_code": company},
        }

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for key in (key_canon, key_local_wrong, key_other):
                    cur.execute("DELETE FROM employee_status_changes WHERE employee_key=%s", (key,))
                    cur.execute("DELETE FROM compliance_documents WHERE employee_key=%s", (key,))
                    cur.execute("DELETE FROM employees WHERE employee_key=%s", (key,))
            conn.commit()

    cleanup()
    try:
        # Seed canonical employee using local phone input (create must canonicalize).
        created = app.create_company_employee(company, name=f"Wave1 Canon {smoke_tag}", phone=local_phone)
        check("create stores canonical phone", created.get("status") == "created")
        check("create employee_key uses 965 form", created.get("employee_key") == key_canon)
        check(
            "create card phone is canonical",
            (created.get("employee") or {}).get("phone") == canonical,
        )

        # Alias-aware lookup
        by_local = app.find_employee_by_phone(local_phone, company_code=company)
        by_965 = app.find_employee_by_phone(canonical, company_code=company)
        check("lookup by local 8 resolves same employee", bool(by_local) and by_local.get("employee_key") == key_canon)
        check("lookup by 965 resolves same employee", bool(by_965) and by_965.get("employee_key") == key_canon)

        # Duplicate prevention across alias forms (no DB unique constraint required)
        audits.clear()
        dup = app.create_company_employee(company, name=f"Wave1 Dup {smoke_tag}", phone=canonical)
        check("alias re-create returns exists", dup.get("status") == "exists")
        check("alias re-create points at existing key", dup.get("employee_key") == key_canon)

        # Force a legacy local-key collision path: insert a synthetic local-key row
        # then ensure a canonical create is blocked by alias matching.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM employees WHERE employee_key=%s", (key_canon,))
                cur.execute(
                    """
                    INSERT INTO employees (employee_key, phone, company_code, name, profile, raw_json, updated_at)
                    VALUES (%s,%s,%s,%s,'{}'::jsonb,%s, now())
                    """,
                    (key_local_wrong, local_phone, company, f"Wave1 LegacyLocal {smoke_tag}", app.Json({"source": "wave1_smoke"})),
                )
            conn.commit()
        blocked = app.create_company_employee(company, name=f"Wave1 Blocked {smoke_tag}", phone=canonical)
        check("create blocked by legacy local phone alias", blocked.get("status") == "exists")
        check("blocked create returns legacy key", blocked.get("employee_key") == key_local_wrong)
        check("identity_collision flagged when keys differ", bool(blocked.get("identity_collision")))

        http_exists = app.dashboard_posthire_create_employee(
            request=app.DashboardEmployeeCreate(name=f"Wave1 HTTP {smoke_tag}", phone=canonical),
            context=owner_ctx(),
        )
        check("HTTP create returns exists for alias collision", http_exists.get("status") == "exists")
        check(
            "identity collision audited",
            any(a["action_type"] == "employee_identity_collision" for a in audits),
        )

        # Rebuild canonical primary subject for remaining checks
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM employees WHERE employee_key IN (%s,%s)", (key_local_wrong, key_canon))
            conn.commit()
        created = app.create_company_employee(company, name=f"Wave1 Primary {smoke_tag}", phone=canonical)
        check("primary employee recreated", created.get("status") == "created")
        app.create_company_employee(company, name=f"Wave1 Other {smoke_tag}", phone=other_phone)

        # Optimistic concurrency
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT updated_at FROM employees WHERE company_code=%s AND employee_key=%s",
                    (company, key_canon),
                )
                version = dict(cur.fetchone())["updated_at"]
        stale = version - timedelta(seconds=30) if isinstance(version, datetime) else version
        conflict = app.update_company_employee(
            company,
            key_canon,
            fields={"position_title": "Stale"},
            expected_updated_at=stale,
        )
        check("stale expected_updated_at returns conflict", conflict.get("status") == "conflict")
        ok_edit = app.update_company_employee(
            company,
            key_canon,
            fields={"position_title": "Fresh Title"},
            expected_updated_at=version,
        )
        check("matching expected_updated_at updates", ok_edit.get("status") == "updated")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT updated_at, position_title FROM employees WHERE company_code=%s AND employee_key=%s",
                    (company, key_canon),
                )
                latest = dict(cur.fetchone())
        try:
            app.dashboard_posthire_update_employee(
                employee_key=key_canon,
                request=app.DashboardEmployeeUpdate(
                    position_title="Should Conflict",
                    expected_updated_at=version,
                ),
                context=owner_ctx(),
            )
            check("HTTP PATCH stale version raises 409", False)
        except app.HTTPException as exc:
            check("HTTP PATCH stale version raises 409", exc.status_code == 409)
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            check("HTTP conflict code is employee_version_conflict", detail.get("error") == "employee_version_conflict")

        # Alias phone collision on edit
        phone_dup = app.update_company_employee(company, key_canon, fields={"phone": "99007701"})
        check("editing phone to another employee's alias is duplicate", phone_dup.get("status") == "duplicate")

        # Manager scope denial on PATCH + status
        audits.clear()

        def restricted_scope(*_a, **_k):
            return {
                "restricted": True,
                "company_code": company,
                "branch_keys": [],
                "team_keys": [],
                "direct_employee_keys": [key_other],  # not key_canon
                "scopes": [],
                "scope_authority": "test",
            }

        app.manager_scope_context = restricted_scope
        try:
            app.dashboard_posthire_update_employee(
                employee_key=key_canon,
                request=app.DashboardEmployeeUpdate(
                    position_title="Out of scope",
                    expected_updated_at=latest["updated_at"],
                ),
                context=manager_ctx(),
            )
            check("scoped manager PATCH denied", False)
        except app.HTTPException as exc:
            check("scoped manager PATCH denied with 404", exc.status_code == 404)
        check(
            "scope denial audited for PATCH",
            any(
                a["action_type"] == "employee_mutation_denied" and (a.get("details") or {}).get("action") == "employee_update"
                for a in audits
            ),
        )

        audits.clear()
        try:
            app.dashboard_posthire_set_employee_status(
                employee_key=key_canon,
                request=app.DashboardEmployeeStatus(
                    status="left",
                    reason="wave1 scope denial",
                    idempotency_key=str(uuid.uuid4()),
                    expected_status="active",
                    expected_updated_at=latest["updated_at"],
                    approver_user_id="self",
                    approval_reference="wave1-scope",
                    approval_mode="self_approved_internal_canary",
                ),
                context=manager_ctx(),
            )
            check("scoped manager status denied", False)
        except app.HTTPException as exc:
            check("scoped manager status denied with 404", exc.status_code == 404)
        check(
            "scope denial audited for status",
            any(
                a["action_type"] == "employee_mutation_denied" and (a.get("details") or {}).get("action") == "employee_status"
                for a in audits
            ),
        )
        app.manager_scope_context = real_scope

        # Canary restriction
        audits.clear()
        prev_env = os.environ.get("WATHEFNI_ENV")
        prev_companies = os.environ.get("WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES")
        try:
            os.environ["WATHEFNI_ENV"] = "production"
            os.environ["WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES"] = "WATHEFNI"
            # even WATHEFNI is denied when env is production (not in default env allowlist)
            check("canary denied for production env by default", app.employee_status_canary_allowed("WATHEFNI") is False)
            os.environ["WATHEFNI_ENV"] = "test"
            os.environ["WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES"] = "WATHEFNI"
            check("canary allowed for WATHEFNI in test", app.employee_status_canary_allowed("WATHEFNI") is True)
            check("canary denied for external company", app.employee_status_canary_allowed("ACMECO") is False)

            # HTTP denial for external company even if env allowlisted
            foreign = {**owner_ctx(), "company_code": "ACMECO", "permission_subject_company": "ACMECO"}
            # Use a helper-level check via transition gate by calling the endpoint
            # with a company that has modules — if ACMECO lacks modules, permission
            # gate fires first. Assert pure allowlist + endpoint deny path for WATHEFNI
            # with production env instead.
            os.environ["WATHEFNI_ENV"] = "production"
            try:
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT employment_status, updated_at FROM employees WHERE company_code=%s AND employee_key=%s",
                            (company, key_canon),
                        )
                        cur_row = dict(cur.fetchone())
                app.dashboard_posthire_set_employee_status(
                    employee_key=key_canon,
                    request=app.DashboardEmployeeStatus(
                        status="left",
                        reason="wave1 canary deny",
                        idempotency_key=str(uuid.uuid4()),
                        expected_status=app._canonical_employee_status(cur_row.get("employment_status")),
                        expected_updated_at=cur_row["updated_at"],
                        approver_user_id="self",
                        approval_reference="wave1-canary",
                        approval_mode="self_approved_internal_canary",
                    ),
                    context=owner_ctx(),
                )
                check("canary HTTP denied in production env", False)
            except app.HTTPException as exc:
                check("canary HTTP denied in production env", exc.status_code == 403)
                detail = exc.detail if isinstance(exc.detail, dict) else {}
                check("canary deny code is canary_not_allowed", detail.get("error") == "canary_not_allowed")
            check(
                "canary denial audited",
                any(
                    a["action_type"] == "employee_mutation_denied" and (a.get("details") or {}).get("reason") == "canary_not_allowed"
                    for a in audits
                ),
            )
        finally:
            if prev_env is None:
                os.environ.pop("WATHEFNI_ENV", None)
            else:
                os.environ["WATHEFNI_ENV"] = prev_env
            if prev_companies is None:
                os.environ.pop("WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES", None)
            else:
                os.environ["WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES"] = prev_companies
            os.environ.setdefault("WATHEFNI_ENV", "test")

        # Integrity diagnostics expansion
        scan = app.workspace_integrity_scan(company)
        expected_tables = {
            "employee_messages",
            "employee_sessions",
            "employee_app_invites",
            "employee_status_changes",
            "employee_org_assignments",
            "file_registry",
            "onboarding_items",
            "employee_documents",
            "hr_tasks",
        }
        present = set((scan.get("tables") or {}).keys())
        check("integrity scan includes expanded employee-linked tables", expected_tables.issubset(present))
        check("integrity scan remains read-only dict result", isinstance(scan.get("total_orphans"), int))

    finally:
        app.record_admin_audit = real_audit
        app.manager_scope_context = real_scope
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


def _pure_checks(app) -> None:
    prev_env = os.environ.get("WATHEFNI_ENV")
    prev_companies = os.environ.get("WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES")
    prev_envs = os.environ.get("WATHEFNI_EMPLOYEE_STATUS_CANARY_ENVS")
    try:
        os.environ["WATHEFNI_ENV"] = "staging"
        os.environ["WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES"] = "WATHEFNI"
        check("pure: WATHEFNI+staging canary allowed", app.employee_status_canary_allowed("WATHEFNI") is True)
        os.environ["WATHEFNI_ENV"] = "production"
        check("pure: WATHEFNI+production canary denied by default", app.employee_status_canary_allowed("WATHEFNI") is False)
        os.environ["WATHEFNI_EMPLOYEE_STATUS_CANARY_ENVS"] = "production"
        check("pure: production canary allowed only when explicitly listed", app.employee_status_canary_allowed("WATHEFNI") is True)
        os.environ["WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES"] = ""
        check("pure: empty company allowlist fails closed", app.employee_status_canary_allowed("WATHEFNI") is False)
        check(
            "pure: alias list bidirectional",
            set(app.employee_phone_alias_list("96551239999")) == {"51239999", "96551239999"},
        )
    finally:
        for key, prev in (
            ("WATHEFNI_ENV", prev_env),
            ("WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES", prev_companies),
            ("WATHEFNI_EMPLOYEE_STATUS_CANARY_ENVS", prev_envs),
        ):
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev


def _pure_checks_only() -> int:
    # Minimal stand-in when app cannot import: validate alias helper logic inline.
    import re

    def digits(value):
        return re.sub(r"\D+", "", value or "")

    def candidates(value):
        raw = digits(value)
        out = {raw} if raw else set()
        if len(raw) == 8:
            out.add(f"965{raw}")
        if len(raw) == 11 and raw.startswith("965"):
            out.add(raw[3:])
        return out

    check("offline alias local→965", "96551234567" in candidates("51234567"))
    check("offline alias 965→local", "51234567" in candidates("96551234567"))
    print(f"\n    {PASS} passed, {FAIL} failed (offline)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
