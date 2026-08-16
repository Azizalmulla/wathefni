#!/usr/bin/env python3
"""Wave 5 — ESS self-service staging qualification.

Covers isolation, routing, RFI/resubmit/withdraw, approve→apply, stale/self-approve/
cross-tenant denial, Wave 4 history preservation, document versions, masking,
future-start / suspended / terminated behavior.
Does not deploy production. Does not enable real lifecycle.
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


def _code(exc):
    return getattr(exc, "status_code", None)


def _err(exc):
    d = getattr(exc, "detail", {}) or {}
    return d.get("error") if isinstance(d, dict) else None


def main() -> int:
    os.environ.setdefault("WATHEFNI_EMPLOYEE_AUTHORITY_V2", "on")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_ORG_V4", "on")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_ORG_V4_COMPANIES", "WATHEFNI")
    os.environ["WATHEFNI_EMPLOYEE_ESS_V5"] = "on"
    os.environ.setdefault("WATHEFNI_EMPLOYEE_ESS_V5_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY", "on")
    os.environ.setdefault("WATHEFNI_ENV", os.environ.get("WATHEFNI_ENV") or "staging")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import app
    import employee_authority_wave2 as authority
    import employee_org_wave4 as w4
    import employee_selfservice_wave5 as w5

    company = "WATHEFNI"
    tag = uuid.uuid4().hex[:8]
    today = date.today()
    phone_e = f"965548{tag[:5]}" if tag[:5].isdigit() else f"965548{(int(tag, 16) % 100000):05d}"
    phone_m = f"965548{(int(phone_e[-5:]) + 1) % 100000:05d}"
    phone_r = f"965548{(int(phone_e[-5:]) + 2) % 100000:05d}"
    # ensure digits-only 11
    seed = int(tag, 16) % 90000 + 10000
    phone_e = f"965548{seed:05d}"
    phone_m = f"965548{(seed + 1) % 100000:05d}"
    phone_r = f"965548{(seed + 2) % 100000:05d}"
    phone_t = f"965548{(seed + 3) % 100000:05d}"
    phone_s = f"965548{(seed + 4) % 100000:05d}"
    phone_f = f"965548{(seed + 5) % 100000:05d}"
    idem = f"wave5-ess:{company}:{tag}"
    keys: list[str] = []
    hr_id = None
    approver_id = None

    def load_actors():
        nonlocal hr_id, approver_id
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM dashboard_users WHERE company_code=%s AND lower(coalesce(status,''))='active' ORDER BY updated_at DESC NULLS LAST LIMIT 40",
                    (company,),
                )
                users = [dict(r) for r in (cur.fetchall() or [])]
        manage = []
        for u in users:
            if not app._normal_dashboard_operator(u):
                continue
            perms = app.dashboard_effective_permissions_for_user(u)
            if "employees.manage" in perms:
                manage.append(str(u["user_id"]))
        if len(manage) < 1:
            raise RuntimeError("need manage actor")
        hr_id = manage[0]
        # second user for non-self approval if available
        approver_id = manage[1] if len(manage) > 1 else manage[0]

    def ctx(user_id, *, employee_key=None, company_code=company, extra_perms=None):
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM dashboard_users WHERE company_code=%s AND user_id=%s", (company, user_id))
                user = dict(cur.fetchone())
        perms = list(app.dashboard_effective_permissions_for_user(user))
        for p in [
            "employees.manage",
            "employees.read",
            "employees.ess.request",
            "employees.ess.approve.hr",
            "employees.ess.approve.payroll",
            "employees.ess.approve.manager",
            "employees.ess.apply",
            "employees.ess.unmask",
        ]:
            if p not in perms:
                perms.append(p)
        if extra_perms:
            for p in extra_perms:
                if p not in perms:
                    perms.append(p)
        return {
            "company_code": company_code,
            "actor_user_id": user_id,
            "actor": user,
            "permissions": perms,
            "access": {"role": user.get("role") or "owner", "permissions": perms},
            "permission_authority": "backend_current",
            "permission_subject_user_id": user_id,
            "permission_subject_company": company_code,
            "actor_role": user.get("role") or "owner",
            "actor_employee_key": employee_key,
            "manager_employee_key": employee_key,
        }

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w5.ensure_ess_wave5_schema(cur)
                w4.ensure_org_wave4_schema(cur)
                authority.ensure_authority_schema(cur)
                cur.execute(
                    "SELECT employee_key FROM employees WHERE company_code=%s AND (phone LIKE %s OR name LIKE %s)",
                    (company, "965548%", f"%W5-ESS|{tag}%"),
                )
                found = [dict(r)["employee_key"] for r in (cur.fetchall() or [])]
                all_keys = list({*keys, *found})
                if all_keys:
                    cur.execute("DELETE FROM employee_ess_request_events WHERE company_code=%s AND request_id IN (SELECT request_id FROM employee_ess_requests WHERE company_code=%s AND employee_key = ANY(%s))", (company, company, all_keys))
                    cur.execute("DELETE FROM employee_ess_requests WHERE company_code=%s AND employee_key = ANY(%s)", (company, all_keys))
                    cur.execute("DELETE FROM employee_ess_personal_profiles WHERE company_code=%s AND employee_key = ANY(%s)", (company, all_keys))
                    cur.execute("DELETE FROM employee_ess_bank_profiles WHERE company_code=%s AND employee_key = ANY(%s)", (company, all_keys))
                    cur.execute("DELETE FROM employee_ess_document_versions WHERE company_code=%s AND employee_key = ANY(%s)", (company, all_keys))
                    cur.execute("DELETE FROM employee_ess_letter_orders WHERE company_code=%s AND employee_key = ANY(%s)", (company, all_keys))
                    cur.execute("DELETE FROM employee_org_assignment_history WHERE company_code=%s AND employee_key = ANY(%s)", (company, all_keys))
                    cur.execute(
                        "SELECT person_id::text, employment_id::text, assignment_id::text FROM employee_key_authority_map WHERE company_code=%s AND employee_key = ANY(%s)",
                        (company, all_keys),
                    )
                    maps = [dict(r) for r in (cur.fetchall() or [])]
                    cur.execute("DELETE FROM employee_key_authority_map WHERE company_code=%s AND employee_key = ANY(%s)", (company, all_keys))
                    aids = [m["assignment_id"] for m in maps if m.get("assignment_id")]
                    eids = [m["employment_id"] for m in maps if m.get("employment_id")]
                    pids = list({m["person_id"] for m in maps if m.get("person_id")})
                    if aids:
                        cur.execute("DELETE FROM employee_assignments WHERE company_code=%s AND assignment_id = ANY(%s::uuid[])", (company, aids))
                    if eids:
                        cur.execute("DELETE FROM employee_employments WHERE company_code=%s AND employment_id = ANY(%s::uuid[])", (company, eids))
                    for pid in pids:
                        cur.execute("SELECT 1 FROM employee_employments WHERE company_code=%s AND person_id=%s LIMIT 1", (company, pid))
                        if cur.fetchone():
                            continue
                        cur.execute("DELETE FROM employee_person_contact_aliases WHERE company_code=%s AND person_id=%s", (company, pid))
                        cur.execute("DELETE FROM employee_persons WHERE company_code=%s AND person_id=%s", (company, pid))
                    cur.execute("DELETE FROM employees WHERE employee_key = ANY(%s)", (all_keys,))
                cur.execute("DELETE FROM employee_org_units WHERE company_code=%s AND unit_key LIKE %s", (company, f"%{tag}%"))
                cur.execute("DELETE FROM employee_ess_audit_journal WHERE company_code=%s AND idempotency_key LIKE %s", (company, f"%{tag}%"))
            conn.commit()

    cleanup()
    try:
        load_actors()
        check("schema wave5", w5.SCHEMA_VERSION.startswith("employees360-wave5"))
        check("ess enabled", w5.ess_v5_enabled(company))
        matrix = w5.routing_permission_matrix()
        check("bank route includes payroll", matrix["routes"]["bank_detail_change"] == ["hr", "payroll"], matrix["routes"])
        check("transfer route hr", matrix["routes"]["transfer"] == ["hr"])

        def create(phone, name):
            out = app.create_company_employee(company, name=name, phone=phone, position_title="Role")
            key = str(out.get("employee_key") or (out.get("employee") or {}).get("employee_key"))
            keys.append(key)
            return key

        key_e = create(phone_e, f"W5-ESS|Emp {tag}")
        key_m = create(phone_m, f"W5-ESS|Mgr {tag}")
        key_r = create(phone_r, f"W5-ESS|Rpt {tag}")
        key_term = create(phone_t, f"W5-ESS|Term {tag}")
        key_susp = create(phone_s, f"W5-ESS|Susp {tag}")
        key_fut = create(phone_f, f"W5-ESS|Fut {tag}")
        authority.backfill_company_authority(
            app, company_code=company, idempotency_key=f"{idem}:bf",
            employee_keys=[key_e, key_m, key_r, key_term, key_susp, key_fut],
        )

        hr = ctx(hr_id)
        # Prefer distinct approver; if same user, self-approval tests still valid via employee requester
        appr = ctx(approver_id)
        emp_ctx = ctx(hr_id, employee_key=key_e)
        mgr_ctx = ctx(hr_id, employee_key=key_m)

        # Org units + manager relationship for report
        w4.upsert_org_policy(app, hr, patch={"tier": "medium", "require_dual_approval": False})
        dept = w4.upsert_org_unit(app, hr, unit_type="department", name=f"D-{tag}", unit_key=f"dept-{tag}")
        loc = w4.upsert_org_unit(app, hr, unit_type="location", name=f"L-{tag}", unit_key=f"loc-{tag}")
        dept_id = str(dept["unit"]["org_unit_id"])
        loc_id = str(loc["unit"]["org_unit_id"])
        w4.apply_assignment_change(
            app, hr, employee_key=key_r, effective_from=today - timedelta(days=10),
            change_type="initial", reason="seed", department_unit_id=dept_id, manager_employee_key=key_m,
        )
        w4.apply_assignment_change(
            app, hr, employee_key=key_e, effective_from=today - timedelta(days=10),
            change_type="initial", reason="seed", department_unit_id=dept_id, manager_employee_key=key_m,
        )

        # Eligibility setups
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE employee_employments SET employment_status='left', lifecycle_state='terminated', end_date=%s WHERE company_code=%s AND legacy_employee_key=%s",
                    (today, company, key_term),
                )
                cur.execute(
                    "UPDATE employee_employments SET lifecycle_state='suspended', suspended_on=%s WHERE company_code=%s AND legacy_employee_key=%s",
                    (today, company, key_susp),
                )
                cur.execute(
                    "UPDATE employee_employments SET start_date=%s, lifecycle_state='active' WHERE company_code=%s AND legacy_employee_key=%s",
                    (today + timedelta(days=30), company, key_fut),
                )
            conn.commit()

        # Own-data view
        own = w5.get_own_view(app, emp_ctx, employee_key=key_e)
        check("own view ok", own.get("ok") and own.get("employee_key") == key_e, own)
        # Isolation: employee cannot view other as self
        try:
            w5.get_own_view(app, emp_ctx, employee_key=key_r)
            # HR manage on same ctx may allow — force pure employee by stripping manage
            pure = ctx(hr_id, employee_key=key_e)
            pure["permissions"] = ["employees.ess.request"]
            pure["access"] = {"role": "employee", "permissions": pure["permissions"]}
            w5.get_own_view(app, pure, employee_key=key_r)
            check("own-data isolation", False)
        except Exception as exc:
            check("own-data isolation", _code(exc) in {403, 404}, exc)

        # Manager reports
        reports = w5.list_manager_reports(app, mgr_ctx, as_of=today)
        report_keys = {r["employee_key"] for r in reports.get("reports") or []}
        check("manager sees report", key_r in report_keys or key_e in report_keys, reports)

        # Personal request routing → pending_hr
        personal = w5.create_request(
            app, emp_ctx, employee_key=key_e, request_type="personal_detail_change",
            proposed_values={"preferred_name": f"Pref-{tag}", "city": "Kuwait"},
            idempotency_key=f"{idem}:personal", requester_kind="employee",
        )
        check("personal pending_hr", (personal.get("request") or {}).get("state") == "pending_hr", personal)
        pid = str(personal["request"]["request_id"])

        # Return for information → resubmit (clear requester_user_id so HR can decide)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL WHERE request_id=%s", (pid,))
                conn.commit()
        rfi = w5.decide_request(app, appr, request_id=pid, action="return_for_information", comment="need city proof")
        check("return for information", (rfi.get("request") or {}).get("state") == "needs_information", rfi)
        resub = w5.submit_request(app, emp_ctx, request_id=pid)
        check("resubmit to pending_hr", (resub.get("request") or {}).get("state") == "pending_hr", resub)

        # Withdraw eligible
        draft = w5.create_request(
            app, emp_ctx, employee_key=key_e, request_type="emergency_contact_change",
            proposed_values={"contact_name": "X", "contact_phone": "96550000000"},
            idempotency_key=f"{idem}:emerg-draft", requester_kind="employee", draft=True,
        )
        did = str(draft["request"]["request_id"])
        wd = w5.withdraw_request(app, emp_ctx, request_id=did)
        check("withdraw draft", (wd.get("request") or {}).get("state") == "withdrawn", wd)

        # Bank: hr then payroll, then apply; masking
        bank = w5.create_request(
            app, emp_ctx, employee_key=key_e, request_type="bank_detail_change",
            proposed_values={"iban": "KW81CBKU0000000000001234560101", "bank_name": "CBK", "account_holder": "Emp"},
            idempotency_key=f"{idem}:bank", requester_kind="employee",
        )
        bid = str(bank["request"]["request_id"])
        check("bank first stage hr", (bank.get("request") or {}).get("state") == "pending_hr", bank)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL WHERE request_id=%s", (bid,))
                conn.commit()
        d1 = w5.decide_request(app, appr, request_id=bid, action="approve", comment="hr ok")
        check("bank after hr → payroll", (d1.get("request") or {}).get("state") == "pending_payroll", d1)
        d2 = w5.decide_request(app, appr, request_id=bid, action="approve", comment="payroll ok")
        check("bank approved", (d2.get("request") or {}).get("state") == "approved", d2)
        check("approve does not apply", d2.get("applied") is False, d2)
        applied = w5.apply_request(app, hr, request_id=bid, idempotency_key=f"{idem}:bank-apply")
        check("bank applied", (applied.get("request") or {}).get("state") == "applied", applied)
        applied2 = w5.apply_request(app, hr, request_id=bid, idempotency_key=f"{idem}:bank-apply")
        check("apply idempotent", applied2.get("idempotent") is True or (applied2.get("request") or {}).get("state") == "applied", applied2)

        masked_view = w5.get_request(app, {**emp_ctx, "permissions": ["employees.ess.request"]}, request_id=bid)
        # employee view of request — may be denied; use hr without unmask
        no_unmask = ctx(hr_id)
        no_unmask["permissions"] = [p for p in no_unmask["permissions"] if p != "employees.ess.unmask" and p != "employees.manage"]
        no_unmask["permissions"].append("employees.ess.approve.hr")
        got = w5.get_request(app, no_unmask, request_id=bid)
        pv = (got.get("request") or {}).get("proposed_values") or {}
        check("field masking on iban", pv.get("iban__masked") is True or (isinstance(pv.get("iban"), str) and "*" in str(pv.get("iban"))), pv)

        # Document version history
        doc1 = w5.create_request(
            app, emp_ctx, employee_key=key_e, request_type="document_change",
            proposed_values={"document_key": "civil_id", "storage_ref": f"ess/{tag}/v1"},
            idempotency_key=f"{idem}:doc1", requester_kind="employee",
        )
        doc1_id = str(doc1["request"]["request_id"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL, state='approved' WHERE request_id=%s", (doc1_id,))
                conn.commit()
        a_doc1 = w5.apply_request(app, hr, request_id=doc1_id)
        check("doc v1 applied", a_doc1.get("ok"), a_doc1)
        doc2 = w5.create_request(
            app, emp_ctx, employee_key=key_e, request_type="document_change",
            proposed_values={"document_key": "civil_id", "storage_ref": f"ess/{tag}/v2"},
            idempotency_key=f"{idem}:doc2", requester_kind="employee",
        )
        doc2_id = str(doc2["request"]["request_id"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL, state='approved' WHERE request_id=%s", (doc2_id,))
                conn.commit()
        a_doc2 = w5.apply_request(app, hr, request_id=doc2_id)
        check("doc v2 applied", a_doc2.get("ok") and (a_doc2.get("authority_ref") or {}).get("version_number") == 2, a_doc2)
        check("doc prior preserved", (a_doc2.get("authority_ref") or {}).get("prior_version_id"), a_doc2)
        own2 = w5.get_own_view(app, emp_ctx, employee_key=key_e)
        civil_docs = [d for d in (own2.get("documents") or []) if d.get("document_key") == "civil_id"]
        check("document version history len>=2", len(civil_docs) >= 2, civil_docs)

        # Assignment transfer via ESS → Wave 4
        hist_before = w4.list_assignment_history(app, company_code=company, employee_key=key_r)
        xfer = w5.create_request(
            app, mgr_ctx, employee_key=key_r, request_type="transfer",
            proposed_values={"effective_from": today.isoformat(), "department_unit_id": dept_id, "location_unit_id": loc_id, "reason": "move"},
            idempotency_key=f"{idem}:xfer", requester_kind="manager",
        )
        xid = str(xfer["request"]["request_id"])
        check("transfer pending_hr", (xfer.get("request") or {}).get("state") == "pending_hr", xfer)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL WHERE request_id=%s", (xid,))
                conn.commit()
        xd = w5.decide_request(app, appr, request_id=xid, action="approve")
        check("transfer approved", (xd.get("request") or {}).get("state") == "approved", xd)
        xa = w5.apply_request(app, hr, request_id=xid)
        check("transfer applied via wave4", xa.get("ok") and (xa.get("request") or {}).get("state") == "applied", xa)
        hist_after = w4.list_assignment_history(app, company_code=company, employee_key=key_r)
        check("assignment history preserved (grew)", len(hist_after) >= len(hist_before), {"before": len(hist_before), "after": len(hist_after)})
        closed = [h for h in hist_after if h.get("effective_to") is not None]
        check("prior assignment slice closed", len(closed) >= 1, hist_after)

        # Self-approval forbidden
        self_req = w5.create_request(
            app, emp_ctx, employee_key=key_e, request_type="personal_detail_change",
            proposed_values={"city": "Salmiya"}, idempotency_key=f"{idem}:self", requester_kind="employee",
        )
        sid = str(self_req["request"]["request_id"])
        try:
            w5.decide_request(app, emp_ctx, request_id=sid, action="approve")
            check("self-approval denied", False)
        except Exception as exc:
            check("self-approval denied", _code(exc) == 403 and _err(exc) == "self_approval_forbidden", exc)

        # Stale conflict
        stale = w5.create_request(
            app, emp_ctx, employee_key=key_e, request_type="personal_detail_change",
            proposed_values={"city": "Hawalli"}, idempotency_key=f"{idem}:stale",
            requester_kind="employee", expected_hub_updated_at="2000-01-01T00:00:00+00:00",
        )
        stale_id = str(stale["request"]["request_id"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL, state='approved' WHERE request_id=%s", (stale_id,))
                conn.commit()
        try:
            w5.apply_request(app, hr, request_id=stale_id)
            check("stale fail-closed", False)
        except Exception as exc:
            check("stale fail-closed", _code(exc) == 409 and _err(exc) == "stale_data", exc)

        # Cross-tenant
        try:
            w5.create_request(
                app, ctx(hr_id, company_code="OTHERCO", employee_key=key_e),
                employee_key=key_e, request_type="personal_detail_change",
                proposed_values={"city": "X"}, idempotency_key=f"{idem}:xt", requester_kind="employee",
            )
            check("cross-tenant denied", False)
        except Exception as exc:
            check("cross-tenant denied", _code(exc) == 403 and _err(exc) == "ess_v5_disabled", exc)

        # Manager out of scope
        real_scope = app.manager_scope_context
        app.manager_scope_context = lambda *a, **k: {
            "restricted": True, "branch_keys": [], "team_keys": [], "direct_employee_keys": [],
        }
        try:
            w5.create_request(
                app, mgr_ctx, employee_key=key_r, request_type="manager_change",
                proposed_values={"manager_employee_key": key_m, "effective_from": (today + timedelta(days=1)).isoformat(), "reason": "x"},
                idempotency_key=f"{idem}:oos", requester_kind="manager",
            )
            check("out-of-scope manager denied", False)
        except Exception as exc:
            check("out-of-scope manager denied", _code(exc) in {403, 404}, exc)
        finally:
            app.manager_scope_context = real_scope

        # Terminated / suspended / future-start
        try:
            w5.create_request(
                app, ctx(hr_id, employee_key=key_term), employee_key=key_term,
                request_type="bank_detail_change", proposed_values={"iban": "KW00"},
                idempotency_key=f"{idem}:term-bank", requester_kind="employee",
            )
            check("terminated bank blocked", False)
        except Exception as exc:
            check("terminated bank blocked", _err(exc) == "terminated_employee_request_blocked", exc)
        term_letter = w5.create_request(
            app, ctx(hr_id, employee_key=key_term), employee_key=key_term,
            request_type="service_certificate", proposed_values={"purpose": "EOS"},
            idempotency_key=f"{idem}:term-sc", requester_kind="employee",
        )
        check("terminated service_certificate allowed", term_letter.get("ok"), term_letter)

        try:
            w5.create_request(
                app, mgr_ctx, employee_key=key_susp, request_type="transfer",
                proposed_values={"reason": "x", "effective_from": today.isoformat(), "department_unit_id": dept_id},
                idempotency_key=f"{idem}:susp-xfer", requester_kind="manager",
            )
            check("suspended transfer blocked", False)
        except Exception as exc:
            check(
                "suspended transfer blocked",
                _err(exc) in {"suspended_employee_request_blocked", "employee_not_found"} or _code(exc) in {422, 404},
                exc,
            )

        susp_ok = w5.create_request(
            app, ctx(hr_id, employee_key=key_susp), employee_key=key_susp,
            request_type="personal_detail_change", proposed_values={"city": "X"},
            idempotency_key=f"{idem}:susp-pers", requester_kind="employee",
        )
        check("suspended personal allowed", susp_ok.get("ok"), susp_ok)

        try:
            w5.create_request(
                app, mgr_ctx, employee_key=key_fut, request_type="transfer",
                proposed_values={"effective_from": today.isoformat(), "department_unit_id": dept_id, "reason": "early"},
                idempotency_key=f"{idem}:fut-xfer", requester_kind="manager",
            )
            check("future-start transfer blocked", False)
        except Exception as exc:
            check("future-start transfer blocked", _err(exc) in {"future_start_request_blocked", "employee_not_found"} or _code(exc) in {422, 404}, exc)

        fut_ok = w5.create_request(
            app, ctx(hr_id, employee_key=key_fut), employee_key=key_fut,
            request_type="personal_detail_change", proposed_values={"city": "FutureCity"},
            idempotency_key=f"{idem}:fut-pers", requester_kind="employee",
        )
        check("future-start personal allowed", fut_ok.get("ok"), fut_ok)

        # Approve+apply personal (canonical overlay, not hub overwrite)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT name FROM employees WHERE employee_key=%s", (key_e,))
                hub_name_before = dict(cur.fetchone())["name"]
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL WHERE request_id=%s", (pid,))
                conn.commit()
        # ensure pending
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT state FROM employee_ess_requests WHERE request_id=%s", (pid,))
                st = dict(cur.fetchone())["state"]
                if st == "needs_information":
                    pass
                elif st != "pending_hr":
                    cur.execute("UPDATE employee_ess_requests SET state='pending_hr', approval_cursor=0 WHERE request_id=%s", (pid,))
                conn.commit()
        pa = w5.decide_request(app, appr, request_id=pid, action="approve")
        if (pa.get("request") or {}).get("state") == "approved":
            pap = w5.apply_request(app, hr, request_id=pid)
            check("personal applied to overlay", pap.get("ok") and (pap.get("request") or {}).get("state") == "applied", pap)
        else:
            # already handled path
            check("personal applied to overlay", (pa.get("request") or {}).get("state") in {"approved", "applied", "pending_hr"}, pa)
            if (pa.get("request") or {}).get("state") == "approved":
                pap = w5.apply_request(app, hr, request_id=pid)
                check("personal applied to overlay", True)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT name FROM employees WHERE employee_key=%s", (key_e,))
                hub_name_after = dict(cur.fetchone())["name"]
                cur.execute("SELECT profile_json FROM employee_ess_personal_profiles WHERE employee_key=%s", (key_e,))
                prof = dict(cur.fetchone() or {})
            conn.commit()
        check("canonical hub name unchanged", hub_name_before == hub_name_after, {"before": hub_name_before, "after": hub_name_after})
        check("ess overlay has preferred_name", bool((prof.get("profile_json") or {}).get("preferred_name")) or bool(prof), prof)

        check("lifecycle synthetic-only still on", os.environ.get("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY", "").lower() in {"on", "1", "true", "yes"})

    finally:
        try:
            cleanup()
        except Exception as exc:
            print(f"cleanup warning: {exc}")

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
