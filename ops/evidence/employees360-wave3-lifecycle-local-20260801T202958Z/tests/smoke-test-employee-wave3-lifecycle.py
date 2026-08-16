"""Wave 3 lifecycle — staging DB smoke (synthetic WATHEFNI only).

Covers: normal/future termination, cancel before effective, reversal,
true rehire, impact preview, idempotency, stale concurrency, scope,
cross-tenant fail-closed, rollback.

Does not mutate production. Cleans synthetic rows in finally.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def _http_exc_code(exc) -> int | None:
    return getattr(exc, "status_code", None)


def main() -> int:
    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2"] = "on"
    os.environ.setdefault("WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES", "WATHEFNI")
    os.environ["WATHEFNI_EMPLOYEE_LIFECYCLE_V3"] = "on"
    os.environ.setdefault("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import app
    import employee_authority_wave2 as authority
    import employee_lifecycle_wave3 as lifecycle
    import employee_status_approval as status_approval

    company = "WATHEFNI"
    tag = uuid.uuid4().hex[:8]
    phone = f"965544{tag[:5]}"
    key = f"{company}-{phone}"
    rehire_phone = f"965533{tag[:5]}"
    rehire_key = f"{company}-{rehire_phone}"
    idem_prefix = f"wave3-smoke:{company}:{tag}"
    today = date.today()
    future = today + timedelta(days=14)

    requester_id = None
    approver_id = None

    def load_actors():
        nonlocal requester_id, approver_id
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM dashboard_users
                    WHERE company_code=%s AND lower(coalesce(status,''))='active'
                    ORDER BY updated_at DESC NULLS LAST
                    LIMIT 40
                    """,
                    (company,),
                )
                users = [dict(r) for r in (cur.fetchall() or [])]
        managers = []
        for u in users:
            if not app._normal_dashboard_operator(u):
                continue
            perms = app.dashboard_effective_permissions_for_user(u)
            if "employees.manage" in perms:
                managers.append(u)
        if not managers:
            raise RuntimeError("no employees.manage operators on WATHEFNI")
        requester = managers[0]
        requester_id = str(requester["user_id"])
        # Prefer an existing eligible approver other than requester
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                status_approval.ensure_employee_status_approval_schema(cur)
                eligible = status_approval.list_eligible_status_approvers(
                    app, cur, company_code=company, exclude_user_id=requester_id
                )
            conn.commit()
        if eligible:
            approver_id = str(eligible[0]["user_id"])
            return
        # Seed temporary approve grant on another normal operator
        other = next(
            (u for u in users if str(u["user_id"]) != requester_id and app._normal_dashboard_operator(u)),
            None,
        )
        if not other:
            raise RuntimeError("no second operator for approver grant")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dashboard_user_permission_grants
                      (company_code, user_id, permission, status, review_reference,
                       granted_by_user_id, granted_reason)
                    VALUES (%s,%s,'employees.status.approve','active',%s,%s,%s)
                    ON CONFLICT (company_code, user_id, permission)
                    DO UPDATE SET
                      status='active',
                      review_reference=EXCLUDED.review_reference,
                      granted_by_user_id=EXCLUDED.granted_by_user_id,
                      granted_reason=EXCLUDED.granted_reason,
                      granted_at=now(),
                      revoked_at=NULL,
                      updated_at=now()
                    """,
                    (
                        company,
                        other["user_id"],
                        f"wave3-smoke-{tag}",
                        requester_id,
                        "Temporary Wave 3 staging qualification grant",
                    ),
                )
                eligible = status_approval.list_eligible_status_approvers(
                    app, cur, company_code=company, exclude_user_id=requester_id
                )
            conn.commit()
        if not eligible:
            raise RuntimeError("failed to seed eligible lifecycle approver")
        approver_id = str(eligible[0]["user_id"])


    def ctx(actor_id: str, *, extra_perms: list[str] | None = None) -> dict:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM dashboard_users WHERE company_code=%s AND user_id=%s",
                    (company, actor_id),
                )
                user = dict(cur.fetchone())
        base_perms = list(app.dashboard_effective_permissions_for_user(user))
        if extra_perms:
            for p in extra_perms:
                if p not in base_perms:
                    base_perms.append(p)
        return {
            "company_code": company,
            "actor_user_id": actor_id,
            "actor": user,
            "permissions": base_perms,
            "access": {"role": user.get("role") or "owner", "permissions": base_perms},
            "permission_authority": "backend_current",
            "permission_subject_user_id": actor_id,
            "permission_subject_company": company,
            "actor_role": user.get("role") or "owner",
            "hr_user": user,
            "role": user.get("role"),
        }

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                lifecycle.ensure_lifecycle_schema(cur)
                authority.ensure_authority_schema(cur)
                keys = [key, rehire_key]
                # Wave3 rows
                cur.execute(
                    "DELETE FROM employee_lifecycle_events WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                cur.execute(
                    "DELETE FROM employee_lifecycle_requests WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                cur.execute(
                    "DELETE FROM employee_lifecycle_cases WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                cur.execute(
                    "DELETE FROM employee_lifecycle_impact_snapshots WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                cur.execute(
                    "DELETE FROM employee_lifecycle_migration_journal WHERE company_code=%s AND idempotency_key LIKE %s",
                    (company, f"%{tag}%"),
                )
                # Downstream fixtures
                for table in (
                    "shift_assignments",
                    "leave_requests",
                    "attendance_records",
                    "payroll_timesheets",
                    "employee_sessions",
                    "employee_app_invites",
                ):
                    try:
                        cur.execute(
                            f"DELETE FROM {table} WHERE company_code=%s AND employee_key = ANY(%s)",
                            (company, keys),
                        )
                    except Exception:
                        conn.rollback()
                        lifecycle.ensure_lifecycle_schema(cur)
                        authority.ensure_authority_schema(cur)
                # Authority + hub
                cur.execute(
                    """
                    SELECT person_id::text AS person_id, employment_id::text AS employment_id,
                           assignment_id::text AS assignment_id
                    FROM employee_key_authority_map
                    WHERE company_code=%s AND employee_key = ANY(%s)
                    """,
                    (company, keys),
                )
                maps = [dict(r) for r in (cur.fetchall() or [])]
                assignment_ids = [m["assignment_id"] for m in maps]
                employment_ids = [m["employment_id"] for m in maps]
                person_ids = list({m["person_id"] for m in maps})
                # Also collect employments for persons (history from rehire)
                if person_ids:
                    cur.execute(
                        "SELECT employment_id::text AS employment_id FROM employee_employments WHERE company_code=%s AND person_id = ANY(%s::uuid[])",
                        (company, person_ids),
                    )
                    employment_ids = list({*(employment_ids or []), *[dict(r)["employment_id"] for r in (cur.fetchall() or [])]})
                    cur.execute(
                        "SELECT assignment_id::text AS assignment_id FROM employee_assignments WHERE company_code=%s AND person_id = ANY(%s::uuid[])",
                        (company, person_ids),
                    )
                    assignment_ids = list({*(assignment_ids or []), *[dict(r)["assignment_id"] for r in (cur.fetchall() or [])]})
                cur.execute(
                    "DELETE FROM employee_key_authority_map WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                if assignment_ids:
                    cur.execute(
                        "DELETE FROM employee_assignments WHERE company_code=%s AND assignment_id = ANY(%s::uuid[])",
                        (company, assignment_ids),
                    )
                if employment_ids:
                    cur.execute(
                        "DELETE FROM employee_employments WHERE company_code=%s AND employment_id = ANY(%s::uuid[])",
                        (company, employment_ids),
                    )
                for pid in person_ids:
                    cur.execute(
                        "SELECT 1 FROM employee_employments WHERE company_code=%s AND person_id=%s LIMIT 1",
                        (company, pid),
                    )
                    if cur.fetchone():
                        continue
                    cur.execute(
                        "DELETE FROM employee_person_contact_aliases WHERE company_code=%s AND person_id=%s",
                        (company, pid),
                    )
                    cur.execute(
                        "DELETE FROM employee_persons WHERE company_code=%s AND person_id=%s",
                        (company, pid),
                    )
                cur.execute(
                    "DELETE FROM employee_authority_migration_journal WHERE company_code=%s AND idempotency_key LIKE %s",
                    (company, f"%{tag}%"),
                )
                cur.execute("DELETE FROM employees WHERE employee_key = ANY(%s)", (keys,))
            conn.commit()

    cleanup()
    try:
        load_actors()
        check("actors distinct", requester_id and approver_id and requester_id != approver_id, (requester_id, approver_id))

        created = app.create_company_employee(
            company,
            name=f"W3 Smoke {tag}",
            phone=phone,
            email=f"w3{tag}@example.com",
            position_title="Analyst",
            department="Ops",
        )
        check("create employee", created.get("status") == "created", created)
        created_key = str(
            created.get("employee_key") or (created.get("employee") or {}).get("employee_key") or key
        )
        key = created_key

        bf = authority.backfill_company_authority(
            app, company_code=company, idempotency_key=f"{idem_prefix}:backfill", employee_keys=[key]
        )
        check("authority backfill", bf.get("ok") is True, bf)

        # Seed downstream impact fixtures
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO shift_assignments (
                      company_code, employee_key, shift_date, start_time, end_time, status
                    ) VALUES (%s,%s,%s,'09:00','17:00','scheduled')
                    """,
                    (company, key, future),
                )
                cur.execute(
                    """
                    INSERT INTO leave_requests (
                      company_code, employee_key, start_date, end_date, status, leave_type
                    ) VALUES (%s,%s,%s,%s,'pending','annual')
                    """,
                    (company, key, future, future + timedelta(days=2)),
                )
                cur.execute(
                    """
                    INSERT INTO attendance_records (
                      company_code, employee_key, attendance_date, status, late_minutes
                    ) VALUES (%s,%s,%s,'pending',15)
                    """,
                    (company, key, today - timedelta(days=1)),
                )
                cur.execute(
                    """
                    INSERT INTO payroll_timesheets (
                      company_code, employee_key, status, period_start, period_end
                    ) VALUES (%s,%s,'draft',%s,%s)
                    """,
                    (company, key, today.replace(day=1), today),
                )
            conn.commit()

        impact = lifecycle.preview_downstream_impact(
            app, company_code=company, employee_key=key, as_of_date=today
        )
        domains = impact.get("domains") or {}
        check("impact future shifts", int((domains.get("future_shifts") or {}).get("count") or 0) >= 1, impact)
        check("impact open leave", int((domains.get("open_leave_requests") or {}).get("count") or 0) >= 1, impact)
        check("impact attendance", int((domains.get("attendance_exceptions") or {}).get("count") or 0) >= 1, impact)
        check("impact payroll", int((domains.get("payroll_timesheets") or {}).get("count") or 0) >= 1, impact)
        check("impact no auto legal", all(d.get("automatic") is False for d in domains.values() if isinstance(d, dict) and "automatic" in d), domains)
        check("impact disclaimer", "no automatic" in str(impact.get("disclaimer") or "").lower(), impact)

        proj = lifecycle.get_lifecycle_projection(app, company_code=company, employee_key=key)
        check("lifecycle projection active", proj and proj.get("lifecycle_state") == "active", proj)
        hub_updated = proj["hub_updated_at"]
        version = int(proj["lifecycle_version"])

        requester_ctx = ctx(requester_id)
        approver_ctx = ctx(approver_id, extra_perms=["employees.status.approve"])

        # --- Out-of-scope manager fail-closed ---
        real_scope = app.manager_scope_context
        app.manager_scope_context = lambda *a, **k: {
            "restricted": True,
            "branch_keys": [],
            "team_keys": [],
            "direct_employee_keys": [],
        }
        try:
            lifecycle.create_lifecycle_request(
                app,
                requester_ctx,
                employee_key=key,
                case_type="termination",
                reason="out of scope attempt",
                approval_reference=f"W3-SCOPE-{tag}",
                designated_approver_user_id=approver_id,
                idempotency_key=f"{idem_prefix}:scope",
                expected_lifecycle_state="active",
                expected_lifecycle_version=version,
                expected_hub_updated_at=hub_updated,
                payload={"termination_effective_on": today.isoformat(), "termination_type": "other"},
            )
            check("out-of-scope manager denied", False)
        except Exception as exc:
            check("out-of-scope manager denied", _http_exc_code(exc) == 404, exc)
        finally:
            app.manager_scope_context = real_scope

        # --- Cancel pending request before approval ---
        req_cancel = lifecycle.create_lifecycle_request(
            app,
            requester_ctx,
            employee_key=key,
            case_type="termination",
            reason="smoke cancel before approve",
            approval_reference=f"W3-CANCEL-{tag}",
            designated_approver_user_id=approver_id,
            idempotency_key=f"{idem_prefix}:cancel-pending",
            expected_lifecycle_state="active",
            expected_lifecycle_version=version,
            expected_hub_updated_at=hub_updated,
            payload={"termination_effective_on": today.isoformat(), "termination_type": "resignation"},
        )
        check("create cancel-pending request", req_cancel.get("ok") is True, req_cancel)
        cancelled = lifecycle.cancel_lifecycle_request(
            app, requester_ctx, request_id=str(req_cancel["request"]["request_id"])
        )
        check("cancel pending request", cancelled.get("ok") and cancelled["request"]["status"] == "cancelled", cancelled)

        # --- Idempotency ---
        req1 = lifecycle.create_lifecycle_request(
            app,
            requester_ctx,
            employee_key=key,
            case_type="termination",
            reason="smoke future term",
            approval_reference=f"W3-FUT-{tag}",
            designated_approver_user_id=approver_id,
            idempotency_key=f"{idem_prefix}:future-term",
            expected_lifecycle_state="active",
            expected_lifecycle_version=version,
            expected_hub_updated_at=hub_updated,
            payload={
                "termination_effective_on": future.isoformat(),
                "last_working_day": (future - timedelta(days=1)).isoformat(),
                "termination_type": "resignation",
            },
        )
        check("create future termination", req1.get("ok") and not req1.get("idempotent"), req1)
        req1b = lifecycle.create_lifecycle_request(
            app,
            requester_ctx,
            employee_key=key,
            case_type="termination",
            reason="smoke future term",
            approval_reference=f"W3-FUT-{tag}",
            designated_approver_user_id=approver_id,
            idempotency_key=f"{idem_prefix}:future-term",
            expected_lifecycle_state="active",
            expected_lifecycle_version=version,
            expected_hub_updated_at=hub_updated,
            payload={
                "termination_effective_on": future.isoformat(),
                "last_working_day": (future - timedelta(days=1)).isoformat(),
                "termination_type": "resignation",
            },
        )
        check("idempotent retry same payload", req1b.get("idempotent") is True, req1b)
        try:
            lifecycle.create_lifecycle_request(
                app,
                requester_ctx,
                employee_key=key,
                case_type="termination",
                reason="smoke future term DIFFERENT",
                approval_reference=f"W3-FUT-{tag}",
                designated_approver_user_id=approver_id,
                idempotency_key=f"{idem_prefix}:future-term",
                expected_lifecycle_state="active",
                expected_lifecycle_version=version,
                expected_hub_updated_at=hub_updated,
                payload={
                    "termination_effective_on": future.isoformat(),
                    "termination_type": "dismissal",
                },
            )
            check("idempotency conflict fail-closed", False)
        except Exception as exc:
            check("idempotency conflict fail-closed", _http_exc_code(exc) == 409, exc)

        # --- Self approval forbidden ---
        try:
            lifecycle.create_lifecycle_request(
                app,
                requester_ctx,
                employee_key=key,
                case_type="termination",
                reason="self approve attempt",
                approval_reference=f"W3-SELF-{tag}",
                designated_approver_user_id=requester_id,
                idempotency_key=f"{idem_prefix}:self",
                expected_lifecycle_state="active",
                expected_lifecycle_version=version,
                expected_hub_updated_at=hub_updated,
                payload={"termination_effective_on": today.isoformat(), "termination_type": "other"},
            )
            check("self-approval forbidden", False)
        except Exception as exc:
            check("self-approval forbidden", _http_exc_code(exc) == 403, exc)

        # --- Approve future-dated → notice_period ---
        decided_future = lifecycle.decide_lifecycle_request(
            app,
            approver_ctx,
            request_id=str(req1["request"]["request_id"]),
            action="approve",
        )
        check("approve future termination", decided_future.get("committed") is True, decided_future)
        proj_notice = lifecycle.get_lifecycle_projection(app, company_code=company, employee_key=key)
        check("state notice_period", proj_notice and proj_notice.get("lifecycle_state") == "notice_period", proj_notice)
        check("hub still active during notice", proj_notice.get("hub_employment_status") == "active", proj_notice)
        check("effective date stored", str(proj_notice.get("termination_effective_on"))[:10] == future.isoformat(), proj_notice)
        prior_employment_id = str(proj_notice["employment_id"])
        person_id = str(proj_notice["person_id"])

        # --- Cancel scheduled termination before effective (reversal from notice) ---
        hub_updated = proj_notice["hub_updated_at"]
        version = int(proj_notice["lifecycle_version"])
        req_rev_notice = lifecycle.create_lifecycle_request(
            app,
            requester_ctx,
            employee_key=key,
            case_type="reversal",
            reason="cancel before effective date",
            approval_reference=f"W3-REV-NOTICE-{tag}",
            designated_approver_user_id=approver_id,
            idempotency_key=f"{idem_prefix}:rev-notice",
            expected_lifecycle_state="notice_period",
            expected_lifecycle_version=version,
            expected_hub_updated_at=hub_updated,
            payload={"restore_state": "active"},
        )
        check("create reversal-before-effective", req_rev_notice.get("ok") is True, req_rev_notice)
        decided_rev_notice = lifecycle.decide_lifecycle_request(
            app, approver_ctx, request_id=str(req_rev_notice["request"]["request_id"]), action="approve"
        )
        check("approve reversal-before-effective", decided_rev_notice.get("committed") is True, decided_rev_notice)
        proj_active = lifecycle.get_lifecycle_projection(app, company_code=company, employee_key=key)
        check("restored active", proj_active and proj_active.get("lifecycle_state") == "active", proj_active)
        check("term fields cleared", proj_active.get("termination_effective_on") is None, proj_active)
        check("same employment after cancel", str(proj_active["employment_id"]) == prior_employment_id, proj_active)

        # --- Stale request fail-closed ---
        hub_updated = proj_active["hub_updated_at"]
        version = int(proj_active["lifecycle_version"])
        req_stale = lifecycle.create_lifecycle_request(
            app,
            requester_ctx,
            employee_key=key,
            case_type="termination",
            reason="will be stale",
            approval_reference=f"W3-STALE-{tag}",
            designated_approver_user_id=approver_id,
            idempotency_key=f"{idem_prefix}:stale",
            expected_lifecycle_state="active",
            expected_lifecycle_version=version,
            expected_hub_updated_at=hub_updated,
            payload={"termination_effective_on": today.isoformat(), "termination_type": "mutual"},
        )
        # Bump hub updated_at to invalidate expected concurrency token
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE employees SET updated_at=clock_timestamp() WHERE employee_key=%s RETURNING updated_at",
                    (key,),
                )
            conn.commit()
        try:
            lifecycle.decide_lifecycle_request(
                app, approver_ctx, request_id=str(req_stale["request"]["request_id"]), action="approve"
            )
            check("stale decide fail-closed", False)
        except Exception as exc:
            check("stale decide fail-closed", _http_exc_code(exc) == 409, exc)

        # Cancel the stale pending request so we can proceed
        lifecycle.cancel_lifecycle_request(app, requester_ctx, request_id=str(req_stale["request"]["request_id"]))

        # --- Normal (immediate) termination ---
        proj_active = lifecycle.get_lifecycle_projection(app, company_code=company, employee_key=key)
        hub_updated = proj_active["hub_updated_at"]
        version = int(proj_active["lifecycle_version"])
        req_term = lifecycle.create_lifecycle_request(
            app,
            requester_ctx,
            employee_key=key,
            case_type="termination",
            reason="normal termination smoke",
            approval_reference=f"W3-TERM-{tag}",
            designated_approver_user_id=approver_id,
            idempotency_key=f"{idem_prefix}:normal-term",
            expected_lifecycle_state="active",
            expected_lifecycle_version=version,
            expected_hub_updated_at=hub_updated,
            payload={
                "termination_effective_on": today.isoformat(),
                "last_working_day": today.isoformat(),
                "termination_type": "end_of_contract",
            },
        )
        decided_term = lifecycle.decide_lifecycle_request(
            app, approver_ctx, request_id=str(req_term["request"]["request_id"]), action="approve"
        )
        check("normal termination committed", decided_term.get("committed") is True, decided_term)
        proj_term = lifecycle.get_lifecycle_projection(app, company_code=company, employee_key=key)
        check("state terminated", proj_term and proj_term.get("lifecycle_state") == "terminated", proj_term)
        check("hub left", proj_term.get("hub_employment_status") == "left", proj_term)
        check("term type stored", proj_term.get("termination_type") == "end_of_contract", proj_term)
        terminated_employment_id = str(proj_term["employment_id"])

        # --- Reversal after termination ---
        hub_updated = proj_term["hub_updated_at"]
        version = int(proj_term["lifecycle_version"])
        req_rev = lifecycle.create_lifecycle_request(
            app,
            requester_ctx,
            employee_key=key,
            case_type="reversal",
            reason="reversal after termination",
            approval_reference=f"W3-REV-AFTER-{tag}",
            designated_approver_user_id=approver_id,
            idempotency_key=f"{idem_prefix}:rev-after",
            expected_lifecycle_state="terminated",
            expected_lifecycle_version=version,
            expected_hub_updated_at=hub_updated,
            payload={"restore_state": "active"},
        )
        decided_rev = lifecycle.decide_lifecycle_request(
            app, approver_ctx, request_id=str(req_rev["request"]["request_id"]), action="approve"
        )
        check("reversal after termination", decided_rev.get("committed") is True, decided_rev)
        proj_rev = lifecycle.get_lifecycle_projection(app, company_code=company, employee_key=key)
        check("reversed to active", proj_rev and proj_rev.get("lifecycle_state") == "active", proj_rev)
        check("same employment after reversal", str(proj_rev["employment_id"]) == terminated_employment_id, proj_rev)
        check("hub active after reversal", proj_rev.get("hub_employment_status") == "active", proj_rev)

        # Terminate again so we can prove true rehire (not left→active reactivation)
        hub_updated = proj_rev["hub_updated_at"]
        version = int(proj_rev["lifecycle_version"])
        req_term2 = lifecycle.create_lifecycle_request(
            app,
            requester_ctx,
            employee_key=key,
            case_type="termination",
            reason="terminate for rehire path",
            approval_reference=f"W3-TERM2-{tag}",
            designated_approver_user_id=approver_id,
            idempotency_key=f"{idem_prefix}:term-for-rehire",
            expected_lifecycle_state="active",
            expected_lifecycle_version=version,
            expected_hub_updated_at=hub_updated,
            payload={"termination_effective_on": today.isoformat(), "termination_type": "resignation"},
        )
        lifecycle.decide_lifecycle_request(
            app, approver_ctx, request_id=str(req_term2["request"]["request_id"]), action="approve"
        )
        proj_term2 = lifecycle.get_lifecycle_projection(app, company_code=company, employee_key=key)
        prior_emp = str(proj_term2["employment_id"])
        prior_asn = str(proj_term2["assignment_id"])
        person_id = str(proj_term2["person_id"])

        hub_updated = proj_term2["hub_updated_at"]
        version = int(proj_term2["lifecycle_version"])
        req_rehire = lifecycle.create_lifecycle_request(
            app,
            requester_ctx,
            employee_key=key,
            case_type="rehire",
            reason="true rehire smoke",
            approval_reference=f"W3-REHIRE-{tag}",
            designated_approver_user_id=approver_id,
            idempotency_key=f"{idem_prefix}:rehire",
            expected_lifecycle_state="terminated",
            expected_lifecycle_version=version,
            expected_hub_updated_at=hub_updated,
            payload={
                "phone": rehire_phone,
                "name": f"W3 Smoke Rehire {tag}",
                "position_title": "Lead",
                "new_employee_key": rehire_key,
            },
        )
        decided_rehire = lifecycle.decide_lifecycle_request(
            app, approver_ctx, request_id=str(req_rehire["request"]["request_id"]), action="approve"
        )
        check("rehire committed", decided_rehire.get("committed") and decided_rehire.get("rehire"), decided_rehire)
        check("rehire same person", decided_rehire.get("person_id") == person_id, decided_rehire)
        check("rehire new employment", decided_rehire.get("new_employment_id") != prior_emp, decided_rehire)
        check("rehire new assignment", decided_rehire.get("new_assignment_id") != prior_asn, decided_rehire)
        check("history count >= 2", int(decided_rehire.get("employment_history_count") or 0) >= 2, decided_rehire)

        # Prior employment immutable / still terminated
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT lifecycle_state, employment_status FROM employee_employments WHERE employment_id=%s",
                    (prior_emp,),
                )
                prior_row = dict(cur.fetchone())
                cur.execute(
                    "SELECT count(*)::bigint AS n FROM employee_employments WHERE company_code=%s AND person_id=%s",
                    (company, person_id),
                )
                hist_n = int(dict(cur.fetchone())["n"])
        check("prior employment remains terminated", prior_row.get("lifecycle_state") == "terminated", prior_row)
        check("prior authority status left", prior_row.get("employment_status") == "left", prior_row)
        check("immutable history rows", hist_n >= 2, hist_n)

        new_proj = lifecycle.get_lifecycle_projection(app, company_code=company, employee_key=rehire_key)
        check("new key active", new_proj and new_proj.get("lifecycle_state") == "active", new_proj)
        check("new key same person", str(new_proj.get("person_id")) == person_id, new_proj)

        # --- Cross-tenant fail-closed ---
        ok_same = authority.assert_no_cross_tenant_access(app, actor_company=company, person_id=person_id)
        ok_other = authority.assert_no_cross_tenant_access(app, actor_company="OTHERCO", person_id=person_id)
        check("same tenant ok", ok_same is True)
        check("cross-tenant fail-closed", ok_other is False)
        check("lifecycle disabled for OTHERCO", lifecycle.lifecycle_v3_enabled("OTHERCO") is False)

        # --- Rollback restores pre-Wave-3 lifecycle overlays (authority retained) ---
        rb = lifecycle.rollback_lifecycle_wave3(
            app,
            company_code=company,
            idempotency_key=f"{idem_prefix}:rollback",
            employee_keys=[key, rehire_key],
        )
        check("rollback ok", rb.get("ok") is True, rb)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*)::bigint AS n FROM employee_lifecycle_requests WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, [key, rehire_key]),
                )
                req_n = int(dict(cur.fetchone())["n"])
                cur.execute(
                    "SELECT 1 FROM employee_key_authority_map WHERE employee_key=%s",
                    (rehire_key,),
                )
                map_ok = bool(cur.fetchone())
        check("lifecycle requests cleared", req_n == 0, req_n)
        check("wave2 authority survives rollback", map_ok is True)

    finally:
        cleanup()

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
