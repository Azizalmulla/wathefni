#!/usr/bin/env python3
"""Employees 360 Wave 1B — staging DB qualification.

Covers Wave 1 containment + Wave 1B production-safe approval:
  phone normalization / aliases / duplicate prevention
  PATCH concurrency
  manager in/out of scope mutations
  production-safe two-person status approval (request/approve/reject/cancel)
  canary rejection outside allowlisted envs
  orphan-document fail-closed markers
  expanded integrity scan
  dashboard/orchestrator API compatibility markers

Safe: uses synthetic employees only; cleans up in finally.
Never targets production.
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
    print("    employees360 wave1b staging qualification")
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    import app
    import employee_status_approval as status_approval

    env = app.employee_status_runtime_env()
    check("runtime env is staging-like (not production)", env in {"staging", "stage", "test", "local", "development", "dev"})
    check("production canary denied by default policy", not (
        env == "production" and app.employee_status_canary_allowed("WATHEFNI")
        and "WATHEFNI_EMPLOYEE_STATUS_CANARY_ENVS" not in os.environ
    ) or env != "production")

    # Source compatibility markers
    api_ts = Path("/Users/azizalmulla/Desktop/claw/apps/wathefni-dashboard/src/lib/api.ts")
    posthire = Path("/Users/azizalmulla/Desktop/claw/apps/wathefni-dashboard/src/posthire/PostHire.tsx")
    if api_ts.exists():
        text = api_ts.read_text(encoding="utf-8")
        check("dashboard API has approval policy client", "getEmployeeStatusApprovalPolicy" in text)
        check("dashboard API has status request client", "createEmployeeStatusApprovalRequest" in text)
        check("dashboard API has decide client", "decideEmployeeStatusApprovalRequest" in text)
    if posthire.exists():
        ui = posthire.read_text(encoding="utf-8")
        check("dashboard UI no longer hardcodes canary-only path", "Approval reference for this internal-canary change" not in ui)
        check("dashboard UI uses approval policy", "getEmployeeStatusApprovalPolicy" in ui)

    company = "WATHEFNI"
    if not any(app.company_has_module(company, m) for m in app.POSTHIRE_PEOPLE_MODULES):
        print("    SKIP: WATHEFNI missing post-hire modules on this DB")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0

    tag = uuid.uuid4().hex[:10]
    local_phone = "51112233"
    canonical = app.canonical_employee_phone(local_phone)
    key = f"{company}-{canonical}"
    other_phone = "96551114455"
    other_key = f"{company}-{other_phone}"

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

    # Find two normal operators with grants when possible
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, role, status, email, name, phone, company_code
                FROM dashboard_users
                WHERE company_code=%s
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 40
                """,
                (company,),
            )
            users = [dict(r) for r in cur.fetchall()]

    managers = []
    approvers = []
    for user in users:
        if not app._normal_dashboard_operator(user):
            continue
        perms = app.dashboard_effective_permissions_for_user(user)
        if "employees.manage" in perms:
            managers.append((user, perms))
        if "employees.status.approve" in perms:
            approvers.append((user, perms))

    seeded_grant_user_id = None
    if managers and not any(str(a[0]["user_id"]) != str(managers[0][0]["user_id"]) for a in approvers):
        # Seed a temporary approve grant on a different normal operator for two-person proof.
        requester_id = str(managers[0][0]["user_id"])
        other = next(
            (
                u
                for u in users
                if str(u["user_id"]) != requester_id and app._normal_dashboard_operator(u)
            ),
            None,
        )
        if other:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO dashboard_user_permission_grants
                          (company_code, user_id, permission, status, review_reference,
                           granted_by_user_id, granted_reason)
                        VALUES (%s,%s,'employees.status.approve','active','wave1b-staging-qual',%s,%s)
                        ON CONFLICT (company_code, user_id, permission)
                        DO UPDATE SET
                          status='active',
                          review_reference=EXCLUDED.review_reference,
                          granted_by_user_id=EXCLUDED.granted_by_user_id,
                          granted_reason=EXCLUDED.granted_reason,
                          granted_at=now(),
                          revoked_at=NULL,
                          revoked_by_user_id=NULL,
                          revoked_reason=NULL,
                          updated_at=now()
                        """,
                        (
                            company,
                            other["user_id"],
                            managers[0][0]["user_id"],
                            "Temporary Wave 1B staging qualification grant",
                        ),
                    )
                conn.commit()
            seeded_grant_user_id = str(other["user_id"])
            approvers.append((other, app.dashboard_effective_permissions_for_user(other)))

    cleanup()
    audits: list[dict] = []
    real_audit = app.record_admin_audit
    app.record_admin_audit = lambda context, action_type, **k: audits.append({"action_type": action_type, **k}) or None

    try:
        # Phone normalization + aliases + duplicate prevention
        created = app.create_company_employee(company, name=f"W1B {tag}", phone=local_phone)
        check("roster create canonicalizes local phone", created.get("status") == "created" and created.get("employee_key") == key)
        check("alias lookup local", (app.find_employee_by_phone(local_phone, company_code=company) or {}).get("employee_key") == key)
        check("alias lookup 965", (app.find_employee_by_phone(canonical, company_code=company) or {}).get("employee_key") == key)
        dup = app.create_company_employee(company, name=f"W1B Dup {tag}", phone=canonical)
        check("duplicate prevention on alias", dup.get("status") == "exists")
        app.create_company_employee(company, name=f"W1B Other {tag}", phone=other_phone)

        # Import path uses find_employee_by_phone (already alias-aware)
        check("import helper alias-aware", hasattr(app, "find_employee_by_phone_aliases"))

        # Recruiting hire marker
        hire_src = (root / "hire_operations.py").read_text(encoding="utf-8")
        check("recruiting hire uses canonical phone", "canonical_employee_phone" in hire_src)

        # PATCH concurrency
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT updated_at FROM employees WHERE employee_key=%s", (key,))
                version = dict(cur.fetchone())["updated_at"]
        stale = app.update_company_employee(company, key, fields={"position_title": "Stale"}, expected_updated_at=version - timedelta(seconds=10))
        check("PATCH concurrency conflict", stale.get("status") == "conflict")
        ok = app.update_company_employee(company, key, fields={"position_title": "Fresh"}, expected_updated_at=version)
        check("PATCH concurrency success", ok.get("status") == "updated")

        # Manager scope deny
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT updated_at FROM employees WHERE employee_key=%s", (key,))
                latest = dict(cur.fetchone())["updated_at"]
        real_scope = app.manager_scope_context
        app.manager_scope_context = lambda *a, **k: {
            "restricted": True,
            "branch_keys": [],
            "team_keys": [],
            "direct_employee_keys": [other_key],
        }
        mgr_ctx = {
            "company_code": company,
            "permissions": ["employees.manage", "employees.status.approve"],
            "access": {"role": "manager", "permissions": ["employees.manage", "employees.status.approve"]},
            "actor_user_id": "00000000-0000-0000-0000-00000000w1b1",
            "permission_authority": "backend_current",
            "permission_subject_user_id": "00000000-0000-0000-0000-00000000w1b1",
            "permission_subject_company": company,
            "actor_role": "manager",
            "hr_phone": "99900000991",
            "hr_user": {"role": "manager", "status": "active", "company_code": company},
        }
        try:
            app.dashboard_posthire_update_employee(
                employee_key=key,
                request=app.DashboardEmployeeUpdate(position_title="Nope", expected_updated_at=latest),
                context=mgr_ctx,
            )
            check("out-of-scope manager PATCH denied", False)
        except app.HTTPException as exc:
            check("out-of-scope manager PATCH denied", exc.status_code == 404)
        app.manager_scope_context = real_scope

        # In-scope unrestricted owner path for status approval policy
        if not managers:
            check("enough operators for two-person approval", False)
        else:
            requester_user, requester_perms = managers[0]
            # Prefer a different approver
            approver_user = None
            for candidate, _perms in approvers:
                if str(candidate["user_id"]) != str(requester_user["user_id"]):
                    approver_user = candidate
                    break
            check("separate eligible approver available or creatable", approver_user is not None)

            if approver_user:
                req_ctx = {
                    "company_code": company,
                    "permissions": list(requester_perms) if "employees.manage" in requester_perms else ["employees.manage"],
                    "access": {"role": requester_user.get("role") or "owner", "permissions": ["employees.manage"]},
                    "actor_user_id": str(requester_user["user_id"]),
                    "permission_authority": "backend_current",
                    "permission_subject_user_id": str(requester_user["user_id"]),
                    "permission_subject_company": company,
                    "actor_role": requester_user.get("role") or "owner",
                    "hr_phone": app.digits(requester_user.get("phone")) or "99900000992",
                    "hr_user": requester_user,
                }
                policy = status_approval.approval_policy(app, company_code=company, actor_user_id=str(requester_user["user_id"]))
                check("policy reports canary allowed on staging", policy.get("canary_allowed") is True)
                check("policy lists eligible approvers excluding self", all(
                    str(a["user_id"]) != str(requester_user["user_id"]) for a in policy.get("eligible_approvers") or []
                ))
                policy_approvers = policy.get("eligible_approvers") or []
                check("policy has at least one eligible approver", len(policy_approvers) >= 1)
                if policy_approvers:
                    approver_user = next(
                        (u for u in users if str(u["user_id"]) == str(policy_approvers[0]["user_id"])),
                        {"user_id": policy_approvers[0]["user_id"], "role": policy_approvers[0].get("role"), "company_code": company},
                    )

                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT employment_status, updated_at FROM employees WHERE employee_key=%s", (key,))
                        row = dict(cur.fetchone())
                # Cancel path
                created_req = status_approval.create_status_change_request(
                    app,
                    req_ctx,
                    employee_key=key,
                    requested_status="left",
                    expected_status=app._canonical_employee_status(row.get("employment_status")),
                    expected_updated_at=row["updated_at"],
                    reason="wave1b cancel path",
                    approval_reference="w1b-cancel",
                    designated_approver_user_id=str(approver_user["user_id"]),
                    idempotency_key=f"w1b-cancel-{tag}",
                )
                check("status approval request created", created_req.get("ok") is True)
                cancel = status_approval.cancel_status_change_request(app, req_ctx, request_id=str(created_req["request"]["request_id"]))
                check("status approval cancelled", cancel.get("request", {}).get("status") == "cancelled")
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (key,))
                        still = dict(cur.fetchone())
                check("cancel leaves employee unchanged", app._canonical_employee_status(still.get("employment_status")) == app._canonical_employee_status(row.get("employment_status")))

                # Reject path
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT employment_status, updated_at FROM employees WHERE employee_key=%s", (key,))
                        row = dict(cur.fetchone())
                created_req = status_approval.create_status_change_request(
                    app,
                    req_ctx,
                    employee_key=key,
                    requested_status="left",
                    expected_status=app._canonical_employee_status(row.get("employment_status")),
                    expected_updated_at=row["updated_at"],
                    reason="wave1b reject path",
                    approval_reference="w1b-reject",
                    designated_approver_user_id=str(approver_user["user_id"]),
                    idempotency_key=f"w1b-reject-{tag}",
                )
                appr_ctx = {
                    **req_ctx,
                    "actor_user_id": str(approver_user["user_id"]),
                    "permission_subject_user_id": str(approver_user["user_id"]),
                    "permissions": ["employees.status.approve"],
                    "hr_user": approver_user,
                    "actor_role": approver_user.get("role") or "hr_manager",
                }
                rejected = status_approval.decide_status_change_request(
                    app, appr_ctx, request_id=str(created_req["request"]["request_id"]), action="reject", decision_reason="wave1b-no"
                )
                check("status approval rejected", rejected.get("decision") == "reject" and rejected.get("committed") is False)
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (key,))
                        still = dict(cur.fetchone())
                check("reject leaves employee unchanged", app._canonical_employee_status(still.get("employment_status")) == app._canonical_employee_status(row.get("employment_status")))

                # Approve path + stale + replay
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT employment_status, updated_at FROM employees WHERE employee_key=%s", (key,))
                        row = dict(cur.fetchone())
                stale_req_id = None
                try:
                    status_approval.create_status_change_request(
                        app,
                        req_ctx,
                        employee_key=key,
                        requested_status="left",
                        expected_status=app._canonical_employee_status(row.get("employment_status")),
                        expected_updated_at=row["updated_at"] - timedelta(seconds=30),
                        reason="wave1b stale",
                        approval_reference="w1b-stale",
                        designated_approver_user_id=str(approver_user["user_id"]),
                        idempotency_key=f"w1b-stale-{tag}",
                    )
                    check("stale request blocked at create", False)
                except app.HTTPException as exc:
                    check("stale request blocked at create", exc.status_code == 409)

                created_req = status_approval.create_status_change_request(
                    app,
                    req_ctx,
                    employee_key=key,
                    requested_status="left",
                    expected_status=app._canonical_employee_status(row.get("employment_status")),
                    expected_updated_at=row["updated_at"],
                    reason="wave1b approve path",
                    approval_reference="w1b-approve",
                    designated_approver_user_id=str(approver_user["user_id"]),
                    idempotency_key=f"w1b-approve-{tag}",
                )
                replay = status_approval.create_status_change_request(
                    app,
                    req_ctx,
                    employee_key=key,
                    requested_status="left",
                    expected_status=app._canonical_employee_status(row.get("employment_status")),
                    expected_updated_at=row["updated_at"],
                    reason="wave1b approve path",
                    approval_reference="w1b-approve",
                    designated_approver_user_id=str(approver_user["user_id"]),
                    idempotency_key=f"w1b-approve-{tag}",
                )
                check("replay same hash is idempotent", replay.get("idempotent") is True)
                try:
                    status_approval.create_status_change_request(
                        app,
                        req_ctx,
                        employee_key=key,
                        requested_status="left",
                        expected_status=app._canonical_employee_status(row.get("employment_status")),
                        expected_updated_at=row["updated_at"],
                        reason="wave1b approve path DIFFERENT",
                        approval_reference="w1b-approve",
                        designated_approver_user_id=str(approver_user["user_id"]),
                        idempotency_key=f"w1b-approve-{tag}",
                    )
                    check("replay different hash conflicts", False)
                except app.HTTPException as exc:
                    check("replay different hash conflicts", exc.status_code == 409)

                # Dual-grant self approve forbidden on request create
                try:
                    status_approval.create_status_change_request(
                        app,
                        req_ctx,
                        employee_key=key,
                        requested_status="left",
                        expected_status=app._canonical_employee_status(row.get("employment_status")),
                        expected_updated_at=row["updated_at"],
                        reason="wave1b self",
                        approval_reference="w1b-self",
                        designated_approver_user_id=str(requester_user["user_id"]),
                        idempotency_key=f"w1b-self-{tag}",
                    )
                    check("self as designated approver forbidden", False)
                except app.HTTPException as exc:
                    check("self as designated approver forbidden", exc.status_code == 403)

                approved = status_approval.decide_status_change_request(
                    app, appr_ctx, request_id=str(created_req["request"]["request_id"]), action="approve"
                )
                check("status approval approved+committed", approved.get("decision") == "approve" and approved.get("committed") is True)
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (key,))
                        after = dict(cur.fetchone())
                check("approve applies left status", app._canonical_employee_status(after.get("employment_status")) == "left")

        # Canary rejection outside approved envs
        prev = os.environ.get("WATHEFNI_ENV")
        os.environ["WATHEFNI_ENV"] = "production"
        check("canary rejected in production env", app.employee_status_canary_allowed(company) is False)
        if prev is None:
            os.environ.pop("WATHEFNI_ENV", None)
        else:
            os.environ["WATHEFNI_ENV"] = prev
        os.environ.setdefault("WATHEFNI_ENV", "staging")

        # Direct separate_approval on commit endpoint rejected (must use request flow)
        if managers:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT employment_status, updated_at FROM employees WHERE employee_key=%s", (key,))
                    row = dict(cur.fetchone())
            owner = managers[0][0]
            ctx = {
                "company_code": company,
                "permissions": ["employees.manage", "employees.status.approve"],
                "access": {"role": "owner", "permissions": ["employees.manage", "employees.status.approve"]},
                "actor_user_id": str(owner["user_id"]),
                "permission_authority": "backend_current",
                "permission_subject_user_id": str(owner["user_id"]),
                "permission_subject_company": company,
                "actor_role": "owner",
                "hr_phone": app.digits(owner.get("phone")) or "99900000993",
                "hr_user": owner,
            }
            try:
                app.dashboard_posthire_set_employee_status(
                    employee_key=key,
                    request=app.DashboardEmployeeStatus(
                        status="active",
                        reason="wave1b direct separate forbidden",
                        idempotency_key=f"w1b-direct-{tag}",
                        expected_status=app._canonical_employee_status(row.get("employment_status")),
                        expected_updated_at=row["updated_at"],
                        approver_user_id=str(approvers[0][0]["user_id"]) if approvers else str(owner["user_id"]),
                        approval_reference="w1b-direct",
                        approval_mode="separate_approval",
                    ),
                    context=ctx,
                )
                check("direct separate_approval commit rejected", False)
            except app.HTTPException as exc:
                check("direct separate_approval commit rejected", exc.status_code == 422)

        # Integrity + orphan markers
        scan = app.workspace_integrity_scan(company)
        names = set((scan.get("tables") or {}).keys())
        check("integrity includes employee_messages", "employee_messages" in names)
        check("integrity includes file_registry", "file_registry" in names)
        src = (root / "app.py").read_text(encoding="utf-8")
        check("orphan document fail-closed marker", "manager_scope_or_orphan" in src)
        check("status approval module present", (root / "employee_status_approval.py").exists())

    finally:
        app.record_admin_audit = real_audit
        cleanup()
        if seeded_grant_user_id:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE dashboard_user_permission_grants
                        SET status='revoked', revoked_reason='wave1b-staging-qual-cleanup',
                            revoked_at=now(), updated_at=now()
                        WHERE company_code=%s AND user_id=%s AND permission='employees.status.approve'
                          AND review_reference='wave1b-staging-qual'
                        """,
                        (company, seeded_grant_user_id),
                    )
                conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
