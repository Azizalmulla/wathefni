#!/usr/bin/env python3
"""Production post-deploy proof for Employees 360 Wave 1 + 1B.

Synthetic-only. Does not clean null statuses or delete orphan messages.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: dict = {"checks": []}


def check(label: str, condition: bool, detail=None) -> None:
    global PASS, FAIL
    RESULTS["checks"].append({"label": label, "ok": bool(condition), "detail": detail})
    if condition:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def main() -> int:
    os.environ.setdefault("WATHEFNI_ENV", "production")
    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import app
    import employee_status_approval as status_approval

    company = "WATHEFNI"
    tag = uuid.uuid4().hex[:10]
    local_phone = "50001122"
    canonical = app.canonical_employee_phone(local_phone)
    key = f"{company}-{canonical}"
    other_phone = "96550003344"
    other_key = f"{company}-{other_phone}"

    # Freeze / canary gates
    check("canary disabled in production", app.employee_status_canary_allowed(company) is False)
    check("production not in canary env allowlist", "production" not in app.employee_status_canary_envs())
    check("Wave D mailbox sync remains off", app.mailbox_ingestion_enabled() is False)
    check("Wave D inbound email flag readable", hasattr(app, "inbound_email_enabled"))

    # Integrity scan (read-only)
    scan = app.workspace_integrity_scan(company)
    RESULTS["integrity_scan"] = scan
    check("integrity scan runs", isinstance(scan.get("total_orphans"), int))
    check("integrity includes employee_messages", "employee_messages" in (scan.get("tables") or {}))
    check("integrity includes file_registry", "file_registry" in (scan.get("tables") or {}))

    # Approval policy
    fouad = "b69f4cad-589d-4029-8a2d-cfa85399966c"
    aziz = "88b17ca9-aff4-4721-a553-c1b5514ef95f"
    pol = status_approval.approval_policy(app, company_code=company, actor_user_id=fouad)
    RESULTS["approval_policy_fouad"] = pol
    check("policy self_approval_allowed false", pol.get("self_approval_allowed") is False)
    check("policy production_safe_required", pol.get("production_safe_required") is True)
    check("policy has eligible separate approver", pol.get("eligible_approver_count", 0) >= 1)
    check("aziz listed as eligible for fouad", any(a.get("user_id") == aziz for a in pol.get("eligible_approvers") or []))

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                status_approval.ensure_employee_status_approval_schema(cur)
                for k in (key, other_key):
                    cur.execute("DELETE FROM employee_status_change_requests WHERE employee_key=%s", (k,))
                    cur.execute("DELETE FROM employee_status_changes WHERE employee_key=%s", (k,))
                    cur.execute("DELETE FROM compliance_documents WHERE employee_key=%s", (k,))
                    cur.execute("DELETE FROM employees WHERE employee_key=%s", (k,))
            conn.commit()

    cleanup()
    try:
        # Phone alias + duplicate
        created = app.create_company_employee(company, name=f"ProdW1 {tag}", phone=local_phone)
        check("manual create canonicalizes", created.get("status") == "created" and created.get("employee_key") == key)
        check("lookup local resolves", (app.find_employee_by_phone(local_phone, company_code=company) or {}).get("employee_key") == key)
        check("lookup 965 resolves same", (app.find_employee_by_phone(canonical, company_code=company) or {}).get("employee_key") == key)
        dup = app.create_company_employee(company, name=f"ProdW1 Dup {tag}", phone=canonical)
        check("duplicate creation blocked", dup.get("status") == "exists")
        app.create_company_employee(company, name=f"ProdW1 Other {tag}", phone=other_phone)
        # import path helper
        check("import uses alias find", hasattr(app, "find_employee_by_phone_aliases"))
        hire_src = Path("/opt/wathefni/orchestrator/hire_operations.py").read_text(encoding="utf-8")
        check("recruiting hire canonical", "canonical_employee_phone" in hire_src)

        # Concurrency 409
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT updated_at FROM employees WHERE employee_key=%s", (key,))
                version = dict(cur.fetchone())["updated_at"]
        stale = app.update_company_employee(company, key, fields={"position_title": "Stale"}, expected_updated_at=version - timedelta(seconds=5))
        check("stale edit conflict", stale.get("status") == "conflict")
        ok = app.update_company_employee(company, key, fields={"position_title": "Fresh"}, expected_updated_at=version)
        check("fresh edit ok", ok.get("status") == "updated")

        # Manager scope
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT updated_at FROM employees WHERE employee_key=%s", (key,))
                latest = dict(cur.fetchone())["updated_at"]
        real_scope = app.manager_scope_context
        # in-scope unrestricted owner context
        owner_ctx = {
            "company_code": company,
            "permissions": ["employees.manage", "employees.status.approve"],
            "access": {"role": "owner", "permissions": ["employees.manage", "employees.status.approve"]},
            "actor_user_id": fouad,
            "permission_authority": "backend_current",
            "permission_subject_user_id": fouad,
            "permission_subject_company": company,
            "actor_role": "owner",
            "hr_phone": "96550000001",
            "hr_user": {"role": "owner", "status": "active", "company_code": company, "user_id": fouad},
        }
        in_scope = app.dashboard_posthire_update_employee(
            employee_key=key,
            request=app.DashboardEmployeeUpdate(position_title="InScope", expected_updated_at=latest),
            context=owner_ctx,
        )
        check("in-scope manager mutation works", bool(in_scope.get("ok")))

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT updated_at FROM employees WHERE employee_key=%s", (key,))
                latest = dict(cur.fetchone())["updated_at"]
        app.manager_scope_context = lambda *a, **k: {
            "restricted": True,
            "branch_keys": [],
            "team_keys": [],
            "direct_employee_keys": [other_key],
        }
        mgr_ctx = {
            **owner_ctx,
            "actor_role": "manager",
            "actor_user_id": "00000000-0000-0000-0000-00000000scop",
            "permission_subject_user_id": "00000000-0000-0000-0000-00000000scop",
            "access": {"role": "manager", "permissions": ["employees.manage"]},
            "hr_user": {
                "role": "manager",
                "status": "active",
                "company_code": company,
                "user_id": "00000000-0000-0000-0000-00000000scop",
            },
        }
        try:
            app.dashboard_posthire_update_employee(
                employee_key=key,
                request=app.DashboardEmployeeUpdate(position_title="Out", expected_updated_at=latest),
                context=mgr_ctx,
            )
            check("out-of-scope mutation fail-closed", False, "unexpected success")
        except app.HTTPException as exc:
            check("out-of-scope mutation fail-closed", exc.status_code == 404, getattr(exc, "detail", None))
        app.manager_scope_context = real_scope

        # Orphan document fail-closed marker in live code
        src = Path("/opt/wathefni/orchestrator/app.py").read_text(encoding="utf-8")
        check("orphan-doc fail-closed present", "manager_scope_or_orphan" in src)

        # Status approval flows
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT employment_status, updated_at FROM employees WHERE employee_key=%s", (key,))
                row = dict(cur.fetchone())
        # self approve forbidden
        try:
            status_approval.create_status_change_request(
                app, owner_ctx, employee_key=key, requested_status="left",
                expected_status=app._canonical_employee_status(row.get("employment_status")),
                expected_updated_at=row["updated_at"], reason="prod self forbid",
                approval_reference="prod-self", designated_approver_user_id=fouad,
                idempotency_key=f"prod-self-{tag}",
            )
            check("requester cannot self-approve request", False)
        except app.HTTPException as exc:
            check("requester cannot self-approve request", exc.status_code == 403)

        # no eligible approver clear failure via empty policy for synthetic company? use policy blocked for actor with no others — already proved aziz exists.
        # cancel
        created = status_approval.create_status_change_request(
            app, owner_ctx, employee_key=key, requested_status="left",
            expected_status=app._canonical_employee_status(row.get("employment_status")),
            expected_updated_at=row["updated_at"], reason="prod cancel",
            approval_reference="prod-cancel", designated_approver_user_id=aziz,
            idempotency_key=f"prod-cancel-{tag}",
        )
        cancel = status_approval.cancel_status_change_request(app, owner_ctx, request_id=str(created["request"]["request_id"]))
        check("cancel works", cancel.get("request", {}).get("status") == "cancelled")

        # reject
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT employment_status, updated_at FROM employees WHERE employee_key=%s", (key,))
                row = dict(cur.fetchone())
        created = status_approval.create_status_change_request(
            app, owner_ctx, employee_key=key, requested_status="left",
            expected_status=app._canonical_employee_status(row.get("employment_status")),
            expected_updated_at=row["updated_at"], reason="prod reject",
            approval_reference="prod-reject", designated_approver_user_id=aziz,
            idempotency_key=f"prod-reject-{tag}",
        )
        appr_ctx = {**owner_ctx, "actor_user_id": aziz, "permission_subject_user_id": aziz, "permissions": ["employees.status.approve"]}
        rejected = status_approval.decide_status_change_request(
            app, appr_ctx, request_id=str(created["request"]["request_id"]), action="reject", decision_reason="prod-no"
        )
        check("separate approver can reject", rejected.get("decision") == "reject" and rejected.get("committed") is False)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (key,))
                still = dict(cur.fetchone())
        check("reject leaves status unchanged", app._canonical_employee_status(still.get("employment_status")) == app._canonical_employee_status(row.get("employment_status")))

        # stale + replay + approve
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT employment_status, updated_at FROM employees WHERE employee_key=%s", (key,))
                row = dict(cur.fetchone())
        try:
            status_approval.create_status_change_request(
                app, owner_ctx, employee_key=key, requested_status="left",
                expected_status=app._canonical_employee_status(row.get("employment_status")),
                expected_updated_at=row["updated_at"] - timedelta(seconds=20), reason="prod stale",
                approval_reference="prod-stale", designated_approver_user_id=aziz,
                idempotency_key=f"prod-stale-{tag}",
            )
            check("stale request fail-closed", False)
        except app.HTTPException as exc:
            check("stale request fail-closed", exc.status_code == 409)

        created = status_approval.create_status_change_request(
            app, owner_ctx, employee_key=key, requested_status="left",
            expected_status=app._canonical_employee_status(row.get("employment_status")),
            expected_updated_at=row["updated_at"], reason="prod approve",
            approval_reference="prod-approve", designated_approver_user_id=aziz,
            idempotency_key=f"prod-approve-{tag}",
        )
        replay = status_approval.create_status_change_request(
            app, owner_ctx, employee_key=key, requested_status="left",
            expected_status=app._canonical_employee_status(row.get("employment_status")),
            expected_updated_at=row["updated_at"], reason="prod approve",
            approval_reference="prod-approve", designated_approver_user_id=aziz,
            idempotency_key=f"prod-approve-{tag}",
        )
        check("replay same hash idempotent", replay.get("idempotent") is True)
        try:
            status_approval.create_status_change_request(
                app, owner_ctx, employee_key=key, requested_status="left",
                expected_status=app._canonical_employee_status(row.get("employment_status")),
                expected_updated_at=row["updated_at"], reason="prod approve DIFFERENT",
                approval_reference="prod-approve", designated_approver_user_id=aziz,
                idempotency_key=f"prod-approve-{tag}",
            )
            check("replay different hash conflicts", False)
        except app.HTTPException as exc:
            check("replay different hash conflicts", exc.status_code == 409)

        approved = status_approval.decide_status_change_request(
            app, appr_ctx, request_id=str(created["request"]["request_id"]), action="approve"
        )
        check("separate approver can approve", approved.get("decision") == "approve" and approved.get("committed") is True)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (key,))
                after = dict(cur.fetchone())
        check("approve applies left", app._canonical_employee_status(after.get("employment_status")) == "left")

        # direct canary denied
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT employment_status, updated_at FROM employees WHERE employee_key=%s", (key,))
                row = dict(cur.fetchone())
        try:
            app.dashboard_posthire_set_employee_status(
                employee_key=key,
                request=app.DashboardEmployeeStatus(
                    status="active",
                    reason="prod canary deny",
                    idempotency_key=f"prod-canary-{tag}",
                    expected_status=app._canonical_employee_status(row.get("employment_status")),
                    expected_updated_at=row["updated_at"],
                    approver_user_id="self",
                    approval_reference="prod-canary",
                    approval_mode="self_approved_internal_canary",
                ),
                context=owner_ctx,
            )
            check("production canary direct status denied", False)
        except app.HTTPException as exc:
            check("production canary direct status denied", exc.status_code == 403)
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            check("canary deny code", detail.get("error") == "canary_not_allowed")

        # no eligible approver fails closed clearly (policy for requester who is the only approver after excluding self)
        only_aziz = status_approval.approval_policy(app, company_code=company, actor_user_id=aziz)
        # Fouad still eligible when Aziz is actor — prove blocked_reason shape via empty company
        empty_pol = status_approval.approval_policy(app, company_code="ZZZNONE", actor_user_id=str(uuid.uuid4()))
        RESULTS["approval_policy_empty"] = empty_pol
        check(
            "no eligible approver fails closed clearly",
            empty_pol.get("status_change_available") is False and empty_pol.get("blocked_reason") == "no_eligible_approver",
            empty_pol,
        )
        check("aziz also has separate eligible approver", only_aziz.get("eligible_approver_count", 0) >= 1)

        # Confirm known null statuses untouched (do not assert absolute count — synthetic creates may also be null)
        known_nulls = ("WATHEFNI-96597727743", "WATHEFNI-96550252254")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT employee_key, employment_status FROM employees WHERE employee_key = ANY(%s)",
                    (list(known_nulls),),
                )
                null_rows = {r["employee_key"]: r["employment_status"] for r in cur.fetchall()}
                cur.execute("SELECT count(*) AS n FROM employee_messages WHERE company_code=%s AND employee_key LIKE %s", (company, "WATHEFNI-P0-DUP-%"))
                orphans = int(cur.fetchone()["n"])
        RESULTS["known_null_statuses"] = null_rows
        RESULTS["synthetic_orphan_messages"] = orphans
        check(
            "null statuses not cleaned",
            all(k in null_rows and null_rows[k] is None for k in known_nulls),
            null_rows,
        )
        check("synthetic orphan messages not deleted", orphans == 3, orphans)

    finally:
        cleanup()

    RESULTS["pass"] = PASS
    RESULTS["fail"] = FAIL
    RESULTS["verdict"] = "PASS" if FAIL == 0 else "FAIL"
    print(json.dumps({"pass": PASS, "fail": FAIL, "verdict": RESULTS["verdict"]}, indent=2))
    Path("/tmp/e360-prod-proofs.json").write_text(json.dumps(RESULTS, indent=2, default=str) + "\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
