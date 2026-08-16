"""Wave 3C lifecycle safety — staging DB smoke (synthetic WATHEFNI only)."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timedelta, time
from pathlib import Path
from zoneinfo import ZoneInfo

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


def _http_exc_code(exc):
    return getattr(exc, "status_code", None)


def main() -> int:
    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2"] = "on"
    os.environ.setdefault("WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES", "WATHEFNI")
    os.environ["WATHEFNI_EMPLOYEE_LIFECYCLE_V3"] = "on"
    os.environ.setdefault("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES", "WATHEFNI")
    os.environ["WATHEFNI_LIFECYCLE_COUNSEL_GATE"] = "on"
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import app
    import employee_authority_wave2 as authority
    import employee_lifecycle_wave3 as w3
    import employee_lifecycle_wave3c as w3c
    import employee_status_approval as status_approval

    company = "WATHEFNI"
    tag = uuid.uuid4().hex[:8]
    phone = f"965522{tag[:5]}"
    key = f"{company}-{phone}"
    idem = f"wave3c-smoke:{company}:{tag}"
    today = date.today()
    tz = ZoneInfo("Asia/Kuwait")
    requester_id = None
    approver_id = None

    def load_actors():
        nonlocal requester_id, approver_id
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM dashboard_users WHERE company_code=%s AND lower(coalesce(status,''))='active' ORDER BY updated_at DESC NULLS LAST LIMIT 40",
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
            raise RuntimeError("no managers")
        requester_id = str(managers[0]["user_id"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                status_approval.ensure_employee_status_approval_schema(cur)
                eligible = status_approval.list_eligible_status_approvers(app, cur, company_code=company, exclude_user_id=requester_id)
            conn.commit()
        if not eligible:
            other = next((u for u in users if str(u["user_id"]) != requester_id and app._normal_dashboard_operator(u)), None)
            if not other:
                raise RuntimeError("no approver")
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO dashboard_user_permission_grants
                          (company_code, user_id, permission, status, review_reference, granted_by_user_id, granted_reason)
                        VALUES (%s,%s,'employees.status.approve','active',%s,%s,%s)
                        ON CONFLICT (company_code, user_id, permission) DO UPDATE SET status='active', revoked_at=NULL, updated_at=now()
                        """,
                        (company, other["user_id"], f"wave3c-{tag}", requester_id, "wave3c smoke"),
                    )
                    eligible = status_approval.list_eligible_status_approvers(app, cur, company_code=company, exclude_user_id=requester_id)
                conn.commit()
        if not eligible:
            raise RuntimeError("no eligible approver")
        approver_id = str(eligible[0]["user_id"])

    def ctx(actor_id: str, extra=None):
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM dashboard_users WHERE company_code=%s AND user_id=%s", (company, actor_id))
                user = dict(cur.fetchone())
        perms = list(app.dashboard_effective_permissions_for_user(user))
        for p in extra or []:
            if p not in perms:
                perms.append(p)
        return {
            "company_code": company,
            "actor_user_id": actor_id,
            "actor": user,
            "permissions": perms,
            "access": {"role": user.get("role") or "owner", "permissions": perms},
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
                w3c.ensure_wave3c_schema(cur)
                keys = [key]
                # collect person employments for rehire history
                cur.execute("SELECT person_id::text FROM employee_key_authority_map WHERE employee_key=%s", (key,))
                row = cur.fetchone()
                person_ids = [dict(row)["person_id"]] if row else []
                for table_sql in [
                    "DELETE FROM employee_lifecycle_downstream_actions WHERE company_code=%s AND employee_key = ANY(%s)",
                    "DELETE FROM employee_lifecycle_settlement_packets WHERE company_code=%s AND employee_key = ANY(%s)",
                    "DELETE FROM employee_lifecycle_events WHERE company_code=%s AND employee_key = ANY(%s)",
                    "DELETE FROM employee_lifecycle_requests WHERE company_code=%s AND employee_key = ANY(%s)",
                    "DELETE FROM employee_lifecycle_cases WHERE company_code=%s AND employee_key = ANY(%s)",
                    "DELETE FROM employee_lifecycle_impact_snapshots WHERE company_code=%s AND employee_key = ANY(%s)",
                ]:
                    cur.execute(table_sql, (company, keys))
                for table in ("shift_assignments", "leave_requests", "attendance_records", "payroll_timesheets", "employee_sessions", "employee_app_invites"):
                    try:
                        cur.execute(f"DELETE FROM {table} WHERE company_code=%s AND employee_key = ANY(%s)", (company, keys))
                    except Exception:
                        conn.rollback()
                        w3c.ensure_wave3c_schema(cur)
                if person_ids:
                    cur.execute("SELECT employment_id::text FROM employee_employments WHERE company_code=%s AND person_id = ANY(%s::uuid[])", (company, person_ids))
                    emp_ids = [dict(r)["employment_id"] for r in (cur.fetchall() or [])]
                    cur.execute("SELECT assignment_id::text FROM employee_assignments WHERE company_code=%s AND person_id = ANY(%s::uuid[])", (company, person_ids))
                    asn_ids = [dict(r)["assignment_id"] for r in (cur.fetchall() or [])]
                    cur.execute("DELETE FROM employee_key_authority_map WHERE company_code=%s AND employee_key = ANY(%s)", (company, keys))
                    # Also clear maps pointing at collected assignment/employment ids
                    if asn_ids:
                        cur.execute(
                            "DELETE FROM employee_key_authority_map WHERE company_code=%s AND assignment_id = ANY(%s::uuid[])",
                            (company, asn_ids),
                        )
                    if emp_ids:
                        cur.execute(
                            "DELETE FROM employee_key_authority_map WHERE company_code=%s AND employment_id = ANY(%s::uuid[])",
                            (company, emp_ids),
                        )
                    if asn_ids:
                        cur.execute("DELETE FROM employee_assignments WHERE company_code=%s AND assignment_id = ANY(%s::uuid[])", (company, asn_ids))
                    if emp_ids:
                        cur.execute("DELETE FROM employee_employments WHERE company_code=%s AND employment_id = ANY(%s::uuid[])", (company, emp_ids))
                    for pid in person_ids:
                        cur.execute("SELECT 1 FROM employee_employments WHERE company_code=%s AND person_id=%s LIMIT 1", (company, pid))
                        if not cur.fetchone():
                            cur.execute("DELETE FROM employee_person_contact_aliases WHERE company_code=%s AND person_id=%s", (company, pid))
                            cur.execute("DELETE FROM employee_persons WHERE company_code=%s AND person_id=%s", (company, pid))
                cur.execute("DELETE FROM employees WHERE employee_key = ANY(%s)", (keys,))
                cur.execute("DELETE FROM employee_lifecycle_scheduler_runs WHERE company_code=%s AND evidence::text LIKE %s", (company, f"%{tag}%"))
            conn.commit()

    cleanup()
    try:
        nonlocal_key = {"value": key}

        def set_key(v: str) -> None:
            nonlocal_key["value"] = v

        def get_key() -> str:
            return nonlocal_key["value"]

        load_actors()
        check("actors distinct", requester_id != approver_id)
        requester_ctx = ctx(requester_id)
        approver_ctx = ctx(approver_id, ["employees.status.approve"])

        # P0-9 counsel gate
        try:
            w3c.assert_counsel_gate(app, company_code=company)
            # may already be signed from prior runs
            gate = w3c.counsel_gate_status(app, company_code=company)
            if gate.get("signed"):
                check("counsel gate already signed or required", True)
            else:
                check("counsel gate blocks when unsigned", False, gate)
        except Exception as exc:
            check("counsel gate blocks when unsigned", _http_exc_code(exc) == 403, exc)
            answers = {q["id"]: f"reviewed-{tag}" for q in w3c.COUNSEL_QUESTIONS}
            signed = w3c.sign_counsel_checklist(
                app, requester_ctx, answers=answers, signed_by_name="Staging Counsel", signed_by_role="counsel", signed_reference=f"W3C-{tag}"
            )
            check("counsel checklist signed", signed.get("ok") is True, signed)

        policy = w3c.get_or_create_company_policy(app, company_code=company)
        check("policy kuwait tz", policy.get("timezone") == "Asia/Kuwait", policy)
        check("policy warn first", policy.get("downstream_mode") == "warn_first", policy)
        check("policy notice hints hidden", policy.get("show_notice_hints") is False and policy.get("notice_hints_ui") is None, policy)
        check("policy reinstate disabled", policy.get("allow_reinstate_after_effective") is False, policy)
        check("policy kuwait only", policy.get("jurisdiction_mode") == "kuwait_private_sector_only", policy)
        check("policy retain docs", policy.get("document_retention_mode") == "retain", policy)
        check("policy no auto shifts", policy.get("auto_cancel_shifts") is False, policy)
        # Persist Wave 3D conservative knobs onto existing staging row
        policy = w3c.upsert_company_policy(
            app,
            requester_ctx,
            patch={
                "show_notice_hints": False,
                "allow_reinstate_after_effective": False,
                "require_last_working_day": True,
                "jurisdiction_mode": "kuwait_private_sector_only",
                "document_retention_mode": "retain",
                "auto_cancel_shifts": False,
                "auto_decline_leave": False,
            },
        )
        check("policy upsert wave3d", (policy.get("policy_json") or {}).get("wave") == "wave3d", policy)

        created = app.create_company_employee(company, name=f"W3C Smoke {tag}", phone=phone, position_title="Analyst")
        check("create employee", created.get("status") == "created", created)
        set_key(str(created.get("employee_key") or (created.get("employee") or {}).get("employee_key") or get_key()))
        key = get_key()

        authority.backfill_company_authority(app, company_code=company, idempotency_key=f"{idem}:bf", employee_keys=[key])

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                future = today + timedelta(days=10)
                cur.execute(
                    "INSERT INTO shift_assignments (company_code, employee_key, shift_date, start_time, end_time, status) VALUES (%s,%s,%s,'09:00','17:00','scheduled')",
                    (company, key, future),
                )
                cur.execute(
                    """
                    INSERT INTO employee_sessions (company_code, employee_key, phone, token_hash, status, expires_at, refresh_expires_at)
                    VALUES (%s,%s,%s,%s,'active', now() + interval '7 days', now() + interval '30 days')
                    """,
                    (company, key, phone, f"tok-{tag}"),
                )
            conn.commit()

        proj = w3c.get_lifecycle_projection(app, company_code=company, employee_key=key)
        hub_updated = proj["hub_updated_at"]
        version = int(proj["lifecycle_version"])

        # missing ack fails
        try:
            w3c.create_lifecycle_request(
                app, requester_ctx, employee_key=key, case_type="termination", reason="no ack",
                approval_reference=f"A-{tag}", designated_approver_user_id=approver_id,
                idempotency_key=f"{idem}:noack", expected_lifecycle_state="active",
                expected_lifecycle_version=version, expected_hub_updated_at=hub_updated,
                payload={"termination_effective_on": today.isoformat(), "termination_type": "resignation"},
                impact_ack=False,
            )
            check("impact ack required", False)
        except Exception as exc:
            check("impact ack required", _http_exc_code(exc) == 422, exc)

        # Future termination (effective = today so scheduler can fire in smoke; notice path uses tomorrow then force due)
        # Use tomorrow for notice, then backdate effective for scheduler proof
        tomorrow = today + timedelta(days=1)
        lwd = today
        req_fut = w3c.create_lifecycle_request(
            app, requester_ctx, employee_key=key, case_type="termination", reason="future term smoke",
            approval_reference=f"FUT-{tag}", designated_approver_user_id=approver_id,
            idempotency_key=f"{idem}:fut", expected_lifecycle_state="active",
            expected_lifecycle_version=version, expected_hub_updated_at=hub_updated,
            payload={"termination_effective_on": tomorrow.isoformat(), "last_working_day": lwd.isoformat(), "termination_type": "resignation"},
            impact_ack=True, impact_ack_text="Reviewed downstream impact snapshot",
        )
        check("create future term with ack", req_fut.get("ok") and req_fut.get("impact_snapshot_hash"), req_fut)
        check("ack hash stored", bool((req_fut.get("request") or {}).get("impact_snapshot_hash")), req_fut)

        decided = w3c.decide_lifecycle_request(app, approver_ctx, request_id=str(req_fut["request"]["request_id"]), action="approve")
        check("approve future term", decided.get("committed") is True, decided)
        proj_n = w3c.get_lifecycle_projection(app, company_code=company, employee_key=key)
        check("notice period", proj_n.get("lifecycle_state") == "notice_period", proj_n)
        check("hub still active", proj_n.get("hub_employment_status") == "active", proj_n)
        prior_emp = str(proj_n["employment_id"])

        # Access still active before revoke time
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT access_revoke_at, access_revoke_status FROM employee_employments WHERE employment_id=%s", (prior_emp,))
                ar = dict(cur.fetchone())
                cur.execute("SELECT status FROM employee_sessions WHERE employee_key=%s AND token_hash=%s", (key, f"tok-{tag}"))
                sess = dict(cur.fetchone())
        check("access revoke scheduled", ar.get("access_revoke_status") == "scheduled", ar)
        check("session active before revoke", sess.get("status") == "active", sess)

        # Cancel before effective
        hub_updated = proj_n["hub_updated_at"]
        version = int(proj_n["lifecycle_version"])
        req_cancel = w3c.create_lifecycle_request(
            app, requester_ctx, employee_key=key, case_type="cancel_scheduled", reason="cancel before effective",
            approval_reference=f"CAN-{tag}", designated_approver_user_id=approver_id,
            idempotency_key=f"{idem}:cancel", expected_lifecycle_state="notice_period",
            expected_lifecycle_version=version, expected_hub_updated_at=hub_updated,
            payload={"restore_state": "active"}, impact_ack=True, impact_ack_text="Ack cancel",
        )
        dec_cancel = w3c.decide_lifecycle_request(app, approver_ctx, request_id=str(req_cancel["request"]["request_id"]), action="approve")
        check("cancel scheduled", dec_cancel.get("committed") and dec_cancel.get("case_type") == "cancel_scheduled", dec_cancel)
        proj_a = w3c.get_lifecycle_projection(app, company_code=company, employee_key=key)
        check("same employment after cancel", str(proj_a["employment_id"]) == prior_emp, proj_a)
        check("active after cancel", proj_a.get("lifecycle_state") == "active", proj_a)

        # Re-term with effective today for scheduler
        hub_updated = proj_a["hub_updated_at"]
        version = int(proj_a["lifecycle_version"])
        req_term = w3c.create_lifecycle_request(
            app, requester_ctx, employee_key=key, case_type="termination", reason="scheduler term",
            approval_reference=f"SCH-{tag}", designated_approver_user_id=approver_id,
            idempotency_key=f"{idem}:sch", expected_lifecycle_state="active",
            expected_lifecycle_version=version, expected_hub_updated_at=hub_updated,
            payload={"termination_effective_on": tomorrow.isoformat(), "last_working_day": lwd.isoformat(), "termination_type": "end_of_contract"},
            impact_ack=True, impact_ack_text="Ack scheduler path",
        )
        w3c.decide_lifecycle_request(app, approver_ctx, request_id=str(req_term["request"]["request_id"]), action="approve")
        # Backdate effective to today so scheduler executes now
        proj_n2 = w3c.get_lifecycle_projection(app, company_code=company, employee_key=key)
        emp_id = str(proj_n2["employment_id"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE employee_employments SET termination_effective_on=%s, access_revoke_at=%s, access_revoke_status=%s WHERE employment_id=%s",
                    (today, datetime.now(tz=tz) - timedelta(seconds=5), "scheduled", emp_id),
                )
            conn.commit()

        # Failed scheduler run then retry
        fail = w3c.run_lifecycle_scheduler(app, company_code=company, environment="staging", fail_before_commit=True)
        check("scheduler failure recorded", fail.get("ok") is False, fail)
        run1 = w3c.run_lifecycle_scheduler(app, company_code=company, environment="staging", now=datetime.now(tz=tz))
        check("scheduler succeeds", run1.get("ok") is True, run1)
        proj_t = w3c.get_lifecycle_projection(app, company_code=company, employee_key=key)
        check("terminated via scheduler", proj_t.get("lifecycle_state") == "terminated", proj_t)
        run2 = w3c.run_lifecycle_scheduler(app, company_code=company, environment="staging", now=datetime.now(tz=tz))
        check("scheduler retry idempotent", run2.get("ok") is True and int((run2.get("terminations") or {}).get("count") or 0) == 0, run2)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM employee_sessions WHERE employee_key=%s AND token_hash=%s", (key, f"tok-{tag}"))
                sess2 = dict(cur.fetchone())
                cur.execute(
                    "SELECT packet, status FROM employee_lifecycle_settlement_packets WHERE employee_key=%s ORDER BY created_at DESC LIMIT 1",
                    (key,),
                )
                pkt = dict(cur.fetchone() or {})
        check("session revoked after revoke time", sess2.get("status") == "revoked", sess2)
        check("settlement packet handed off", pkt.get("status") == "handed_to_payroll", pkt)
        packet = pkt.get("packet") or {}
        if isinstance(packet, str):
            import json as _json
            packet = _json.loads(packet)
        check("settlement has no amounts", "amounts" not in packet, packet)
        check("settlement has inputs only disclaimer", "inputs" in packet and "disclaimer" in packet, packet)

        # Downstream explicit action + reverse
        da = w3c.create_downstream_action_request(
            app, requester_ctx, employee_key=key, action_type="cancel_future_shifts", reason="cancel shifts",
            designated_approver_user_id=approver_id, idempotency_key=f"{idem}:ds",
            impact_ack=True, impact_ack_text="Ack downstream",
        )
        check("downstream request", da.get("ok") is True, da)
        dad = w3c.decide_downstream_action(app, approver_ctx, action_id=str(da["action"]["action_id"]), action="approve")
        check("downstream executed", dad.get("committed") is True, dad)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM shift_assignments WHERE employee_key=%s", (key,))
                sh = dict(cur.fetchone())
        check("shift cancelled_lifecycle", sh.get("status") == "cancelled_lifecycle", sh)
        rev = w3c.create_downstream_action_request(
            app, requester_ctx, employee_key=key, action_type="reverse_cancel_future_shifts", reason="reverse shifts",
            designated_approver_user_id=approver_id, idempotency_key=f"{idem}:dsrev",
            impact_ack=True, impact_ack_text="Ack reverse",
        )
        w3c.decide_downstream_action(app, approver_ctx, action_id=str(rev["action"]["action_id"]), action="approve")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM shift_assignments WHERE employee_key=%s", (key,))
                sh2 = dict(cur.fetchone())
        check("shift reverse restored", sh2.get("status") == "scheduled", sh2)

        # Reinstate after effective — disabled by default; true rehire is the safe path.
        hub_updated = proj_t["hub_updated_at"]
        version = int(proj_t["lifecycle_version"])
        proj_t = w3c.get_lifecycle_projection(app, company_code=company, employee_key=key)
        hub_updated = proj_t["hub_updated_at"]
        version = int(proj_t["lifecycle_version"])
        term_emp = str(proj_t["employment_id"])
        try:
            w3c.create_lifecycle_request(
                app, requester_ctx, employee_key=key, case_type="reinstate", reason="should be blocked",
                approval_reference=f"REIN-BLOCK-{tag}", designated_approver_user_id=approver_id,
                idempotency_key=f"{idem}:rein-block", expected_lifecycle_state="terminated",
                expected_lifecycle_version=version, expected_hub_updated_at=hub_updated,
                payload={"restore_state": "active"}, impact_ack=True, impact_ack_text="Ack reinstate",
            )
            check("reinstate blocked by default", False)
        except Exception as exc:
            detail = getattr(exc, "detail", {}) or {}
            err = detail.get("error") if isinstance(detail, dict) else None
            check("reinstate blocked by default", _http_exc_code(exc) == 422 and err == "reinstate_disabled_by_policy", exc)

        # Opt-in reinstate for explicit enablement path (same employment, no silent session restore)
        w3c.upsert_company_policy(app, requester_ctx, patch={"allow_reinstate_after_effective": True})
        proj_t = w3c.get_lifecycle_projection(app, company_code=company, employee_key=key)
        hub_updated = proj_t["hub_updated_at"]
        version = int(proj_t["lifecycle_version"])
        req_re = w3c.create_lifecycle_request(
            app, requester_ctx, employee_key=key, case_type="reinstate", reason="reinstate after effective",
            approval_reference=f"REIN-{tag}", designated_approver_user_id=approver_id,
            idempotency_key=f"{idem}:rein", expected_lifecycle_state="terminated",
            expected_lifecycle_version=version, expected_hub_updated_at=hub_updated,
            payload={"restore_state": "active"}, impact_ack=True, impact_ack_text="Ack reinstate",
        )
        dec_re = w3c.decide_lifecycle_request(app, approver_ctx, request_id=str(req_re["request"]["request_id"]), action="approve")
        check("reinstate committed when enabled", dec_re.get("committed") and dec_re.get("case_type") == "reinstate", dec_re)
        proj_r = w3c.get_lifecycle_projection(app, company_code=company, employee_key=key)
        check("same employment after reinstate", str(proj_r["employment_id"]) == term_emp, proj_r)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM employee_sessions WHERE employee_key=%s AND token_hash=%s", (key, f"tok-{tag}"))
                sess3 = dict(cur.fetchone())
        check("reinstate does not silent-restore session", sess3.get("status") == "revoked", sess3)
        # Restore conservative default after opt-in proof
        w3c.upsert_company_policy(app, requester_ctx, patch={"allow_reinstate_after_effective": False})

        # Non-Kuwait jurisdiction excluded
        try:
            w3c.create_lifecycle_request(
                app, requester_ctx, employee_key=key, case_type="termination", reason="cross border",
                approval_reference=f"XB-{tag}", designated_approver_user_id=approver_id,
                idempotency_key=f"{idem}:xb", expected_lifecycle_state="active",
                expected_lifecycle_version=int(proj_r["lifecycle_version"]), expected_hub_updated_at=proj_r["hub_updated_at"],
                payload={
                    "termination_effective_on": today.isoformat(),
                    "last_working_day": today.isoformat(),
                    "termination_type": "resignation",
                    "work_country": "AE",
                },
                impact_ack=True, impact_ack_text="Ack",
            )
            check("non-kuwait excluded", False)
        except Exception as exc:
            detail = getattr(exc, "detail", {}) or {}
            err = detail.get("error") if isinstance(detail, dict) else None
            check("non-kuwait excluded", _http_exc_code(exc) == 422 and err == "jurisdiction_excluded", exc)

        # LWD required
        try:
            w3c.create_lifecycle_request(
                app, requester_ctx, employee_key=key, case_type="termination", reason="missing lwd",
                approval_reference=f"LWD-{tag}", designated_approver_user_id=approver_id,
                idempotency_key=f"{idem}:nolwd", expected_lifecycle_state="active",
                expected_lifecycle_version=int(proj_r["lifecycle_version"]), expected_hub_updated_at=proj_r["hub_updated_at"],
                payload={"termination_effective_on": today.isoformat(), "termination_type": "resignation"},
                impact_ack=True, impact_ack_text="Ack",
            )
            check("last working day required", False)
        except Exception as exc:
            detail = getattr(exc, "detail", {}) or {}
            err = detail.get("error") if isinstance(detail, dict) else None
            check("last working day required", _http_exc_code(exc) == 422 and err == "last_working_day_required", exc)

        # Terminate again then same-key rehire
        proj_r = w3c.get_lifecycle_projection(app, company_code=company, employee_key=key)
        req_t2 = w3c.create_lifecycle_request(
            app, requester_ctx, employee_key=key, case_type="termination", reason="term for rehire",
            approval_reference=f"T2-{tag}", designated_approver_user_id=approver_id,
            idempotency_key=f"{idem}:t2", expected_lifecycle_state="active",
            expected_lifecycle_version=int(proj_r["lifecycle_version"]), expected_hub_updated_at=proj_r["hub_updated_at"],
            payload={"termination_effective_on": today.isoformat(), "last_working_day": today.isoformat(), "termination_type": "resignation"},
            impact_ack=True, impact_ack_text="Ack",
        )
        w3c.decide_lifecycle_request(app, approver_ctx, request_id=str(req_t2["request"]["request_id"]), action="approve")
        proj_t2 = w3c.get_lifecycle_projection(app, company_code=company, employee_key=key)
        prior2 = str(proj_t2["employment_id"])
        asn2 = str(proj_t2["assignment_id"])
        person = str(proj_t2["person_id"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT phone FROM employees WHERE employee_key=%s", (key,))
                rehire_phone = str(dict(cur.fetchone())["phone"])
        req_rh = w3c.create_lifecycle_request(
            app, requester_ctx, employee_key=key, case_type="rehire", reason="same key rehire",
            approval_reference=f"RH-{tag}", designated_approver_user_id=approver_id,
            idempotency_key=f"{idem}:rh", expected_lifecycle_state="terminated",
            expected_lifecycle_version=int(proj_t2["lifecycle_version"]), expected_hub_updated_at=proj_t2["hub_updated_at"],
            payload={"phone": rehire_phone, "name": f"W3C Rehire {tag}", "position_title": "Lead"},
            impact_ack=True, impact_ack_text="Ack rehire",
        )
        dec_rh = w3c.decide_lifecycle_request(app, approver_ctx, request_id=str(req_rh["request"]["request_id"]), action="approve")
        check("rehire same key", dec_rh.get("same_employee_key") is True, dec_rh)
        check("rehire same employee_key value", dec_rh.get("employee_key") == key, dec_rh)
        check("rehire new employment", dec_rh.get("new_employment_id") != prior2, dec_rh)
        check("rehire new assignment", dec_rh.get("new_assignment_id") != asn2, dec_rh)
        check("rehire same person", dec_rh.get("person_id") == person, dec_rh)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT lifecycle_state FROM employee_employments WHERE employment_id=%s", (prior2,))
                prior_row = dict(cur.fetchone())
        check("prior employment immutable terminated", prior_row.get("lifecycle_state") == "terminated", prior_row)

        # Wave 3 regression markers still importable / unit path
        check("wave3 enabled", w3.lifecycle_v3_enabled(company) is True)
        check("wave2 authority present", authority.authority_v2_enabled(company) is True)

        rb = w3c.rollback_lifecycle_wave3c(app, company_code=company, idempotency_key=f"{idem}:rb", employee_keys=[key])
        check("rollback ok", rb.get("ok") is True, rb)

    finally:
        cleanup()

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
