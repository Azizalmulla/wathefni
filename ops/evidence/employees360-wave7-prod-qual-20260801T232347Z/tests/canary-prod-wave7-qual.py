#!/usr/bin/env python3
"""Wave 7 — production synthetic qualification for Employees 360 (UI + API).

Allowlist: phones 965549*, names W7-SYNTH| for ESS; lifecycle stays on 965522 / W3D-SYNTH|.
Does not classify or mutate the four real employees.
Does not lift SYNTHETIC_ONLY. Cleans up synthetics.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0
EVIDENCE: dict = {"checks": [], "ids": {}, "reals": {}, "remediation": {}, "cleanup": {}, "flags": {}}

PHONE_PREFIX = "965549"
NAME_PREFIX = "W7-SYNTH|"
REAL_KEYS = (
    "WATHEFNI-96550252254",
    "WATHEFNI-96566363363",
    "WATHEFNI-96597727743",
    "WATHEFNI-96599411617",
)


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    EVIDENCE["checks"].append({"label": label, "ok": bool(cond), "detail": None if cond else detail})
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def _err(exc):
    d = getattr(exc, "detail", {}) or {}
    return d.get("error") if isinstance(d, dict) else None


def main() -> int:
    os.environ.setdefault("WATHEFNI_EMPLOYEE_AUTHORITY_V2", "on")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_ORG_V4", "on")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_ESS_V5", "on")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_ESS_V5_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_ONLY", "on")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_PHONE_PREFIXES", PHONE_PREFIX)
    os.environ.setdefault("WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_NAME_PREFIX", NAME_PREFIX)
    os.environ.setdefault("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY", "on")
    os.environ.setdefault("WATHEFNI_ENV", "production")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import app
    import employee_authority_wave2 as authority
    import employee_org_wave4 as w4
    import employee_policy_packs_wave3h as packs
    import employee_selfservice_wave5 as w5

    company = "WATHEFNI"
    tag = uuid.uuid4().hex[:8]
    seed = int(tag, 16) % 90000 + 10000
    today = date.today()
    phones = [f"{PHONE_PREFIX}{(seed + i) % 100000:05d}" for i in range(4)]
    phone_e, phone_m, phone_r, phone_x = phones
    idem = f"wave7-prod:{company}:{tag}"
    keys: list[str] = []
    hr_id = None

    EVIDENCE["flags"] = {
        "ess_v5": os.environ.get("WATHEFNI_EMPLOYEE_ESS_V5"),
        "ess_synthetic_only": os.environ.get("WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_ONLY"),
        "lifecycle_synthetic_only": os.environ.get("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY"),
        "employee_app": os.environ.get("WATHEFNI_EMPLOYEE_APP", "unset"),
    }

    def load_actor():
        nonlocal hr_id
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM dashboard_users WHERE company_code=%s AND lower(coalesce(status,''))='active' ORDER BY updated_at DESC NULLS LAST LIMIT 40",
                    (company,),
                )
                users = [dict(r) for r in (cur.fetchall() or [])]
        for u in users:
            if not app._normal_dashboard_operator(u):
                continue
            if "employees.manage" in app.dashboard_effective_permissions_for_user(u):
                hr_id = str(u["user_id"])
                return
        raise RuntimeError("no manage actor")

    def ctx(user_id, *, employee_key=None, company_code=company):
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM dashboard_users WHERE company_code=%s AND user_id=%s", (company, user_id))
                user = dict(cur.fetchone())
        perms = list(app.dashboard_effective_permissions_for_user(user))
        for p in [
            "employees.manage", "employees.read", "employees.ess.request",
            "employees.ess.approve.hr", "employees.ess.approve.payroll",
            "employees.ess.apply", "employees.ess.unmask", "employees.status.approve",
        ]:
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

    def snapshot_reals():
        out = {}
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for k in REAL_KEYS:
                    cur.execute("SELECT employee_key, name, phone, updated_at FROM employees WHERE company_code=%s AND employee_key=%s", (company, k))
                    hub = dict(cur.fetchone() or {})
                    cur.execute(
                        """
                        SELECT employment_status, policy_pack_status, lifecycle_state, jurisdiction_code, worker_category
                        FROM employee_employments WHERE company_code=%s AND legacy_employee_key=%s
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (company, k),
                    )
                    emp = dict(cur.fetchone() or {})
                    cur.execute("SELECT count(*)::int AS n FROM employee_ess_requests WHERE company_code=%s AND employee_key=%s", (company, k))
                    n = int(dict(cur.fetchone())["n"])
                    out[k] = {"hub_updated_at": str(hub.get("updated_at")), "employment": {str(a): str(b) for a, b in emp.items()}, "ess_requests": n}
            conn.commit()
        return out

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w5.ensure_ess_wave5_schema(cur)
                w4.ensure_org_wave4_schema(cur)
                authority.ensure_authority_schema(cur)
                cur.execute(
                    "SELECT employee_key FROM employees WHERE company_code=%s AND (phone LIKE %s OR name LIKE %s)",
                    (company, f"{PHONE_PREFIX}%", f"%{NAME_PREFIX}%"),
                )
                found = [dict(r)["employee_key"] for r in (cur.fetchall() or [])]
                all_keys = [k for k in {*keys, *found} if k not in REAL_KEYS]
                if all_keys:
                    for sql in [
                        "DELETE FROM employee_ess_sensitive_access_log WHERE company_code=%s AND employee_key = ANY(%s)",
                        "DELETE FROM employee_ess_overlay_conflicts WHERE company_code=%s AND employee_key = ANY(%s)",
                        "DELETE FROM employee_ess_identity_bindings WHERE company_code=%s AND employee_key = ANY(%s)",
                        "DELETE FROM employee_ess_personal_profiles WHERE company_code=%s AND employee_key = ANY(%s)",
                        "DELETE FROM employee_ess_bank_profiles WHERE company_code=%s AND employee_key = ANY(%s)",
                        "DELETE FROM employee_ess_document_versions WHERE company_code=%s AND employee_key = ANY(%s)",
                        "DELETE FROM employee_org_assignment_history WHERE company_code=%s AND employee_key = ANY(%s)",
                    ]:
                        cur.execute(sql, (company, all_keys))
                    cur.execute(
                        "DELETE FROM employee_ess_request_events WHERE company_code=%s AND request_id IN (SELECT request_id FROM employee_ess_requests WHERE company_code=%s AND employee_key = ANY(%s))",
                        (company, company, all_keys),
                    )
                    cur.execute("DELETE FROM employee_ess_requests WHERE company_code=%s AND employee_key = ANY(%s)", (company, all_keys))
                    cur.execute("UPDATE employee_sessions SET status='revoked', revoked_at=now(), revoked_reason='wave7_cleanup' WHERE company_code=%s AND employee_key = ANY(%s) AND status='active'", (company, all_keys))
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
            conn.commit()

    reals_before = snapshot_reals()
    EVIDENCE["reals"]["before"] = reals_before
    cleanup()
    try:
        load_actor()
        hr = ctx(hr_id)
        check("ess synthetic only on", w5.ess_synthetic_only_enabled())
        check("bank encryption available", w5.bank_encryption_available())
        check("lifecycle synthetic only env", os.environ.get("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY", "").lower() in {"on", "1", "true", "yes"})
        check("employee app off or unset", str(os.environ.get("WATHEFNI_EMPLOYEE_APP", "off")).lower() in {"off", "0", "false", "no", ""})

        rem = packs.list_remediation_queue(app, company_code=company)
        rows = rem.get("rows") or []
        real_rem = [r for r in rows if r.get("employee_key") in REAL_KEYS]
        EVIDENCE["remediation"] = {
            "total": rem.get("count"),
            "reals": len(real_rem),
            "note": "prod reals remain unclassified by design; staging count differs by environment data",
        }
        check("prod remediation readable", rem.get("ok") is True)
        check("exactly four reals in remediation queue", len(real_rem) == 4, len(real_rem))

        units = w4.list_org_units(app, company_code=company)
        check("org units listable", isinstance(units, list))
        batches = w4.list_migration_batches(app, company_code=company, limit=20)
        check("migration batches listable", isinstance(batches, list))

        def create(phone, name, email=None):
            out = app.create_company_employee(company, name=name, phone=phone, email=email, position_title="Role")
            key = str(out.get("employee_key") or (out.get("employee") or {}).get("employee_key"))
            keys.append(key)
            return key

        key_e = create(phone_e, f"{NAME_PREFIX}Emp {tag}", email=f"w7-e-{tag}@example.test")
        key_m = create(phone_m, f"{NAME_PREFIX}Mgr {tag}", email=f"w7-m-{tag}@example.test")
        key_r = create(phone_r, f"{NAME_PREFIX}Rpt {tag}", email=f"w7-r-{tag}@example.test")
        EVIDENCE["ids"] = {"e": key_e, "m": key_m, "r": key_r, "tag": tag}
        authority.backfill_company_authority(app, company_code=company, idempotency_key=f"{idem}:bf", employee_keys=[key_e, key_m, key_r])
        emp = ctx(hr_id, employee_key=key_e)
        mgr = ctx(hr_id, employee_key=key_m)

        w4.upsert_org_policy(app, hr, patch={"tier": "medium", "require_dual_approval": False})
        dept = w4.upsert_org_unit(app, hr, unit_type="department", name=f"D-{tag}", unit_key=f"dept-{tag}")
        loc = w4.upsert_org_unit(app, hr, unit_type="location", name=f"L-{tag}", unit_key=f"loc-{tag}")
        dept_id = str(dept["unit"]["org_unit_id"])
        loc_id = str(loc["unit"]["org_unit_id"])
        w4.apply_assignment_change(
            app, hr, employee_key=key_e, effective_from=today - timedelta(days=7),
            change_type="initial", reason="seed", department_unit_id=dept_id, manager_employee_key=key_m,
        )
        w4.apply_assignment_change(
            app, hr, employee_key=key_r, effective_from=today - timedelta(days=7),
            change_type="initial", reason="seed", department_unit_id=dept_id, manager_employee_key=key_m,
        )
        hist = w4.list_assignment_history(app, company_code=company, employee_key=key_e)
        check("assignment history present", len(hist) >= 1, len(hist))

        # future-effective transfer
        fut = today + timedelta(days=3)
        w4.apply_assignment_change(
            app, hr, employee_key=key_r, effective_from=fut,
            change_type="transfer", reason="future", department_unit_id=dept_id, location_unit_id=loc_id, manager_employee_key=key_m,
        )
        hist2 = w4.list_assignment_history(app, company_code=company, employee_key=key_r)
        scheduled = [h for h in hist2 if str(h.get("effective_from") or "")[:10] >= fut.isoformat()]
        check("future-effective assignment recorded", len(scheduled) >= 1, hist2)

        # activate-due path (scheduler sibling): no-op as of today, then activate as of fut
        act0 = w4.activate_due_assignment_slices(app, company_code=company, as_of=today)
        check("activate_due runs", isinstance(act0, dict) and act0.get("ok") is not False, act0)
        act1 = w4.activate_due_assignment_slices(app, company_code=company, as_of=fut)
        check("activate_due future-effective", isinstance(act1, dict) and act1.get("ok") is not False, act1)

        bind = w5.bind_employee_identity(app, emp, employee_key=key_e)
        check("identity bind", bind.get("ok"), bind)
        sess = app.create_employee_session(company, key_e, phone_e)
        token = sess["token"]
        check("session live", app.employee_by_session(token) is not None)
        rev = w5.revoke_employee_sessions(app, hr, employee_key=key_e, reason="wave7")
        check("session revoke", rev.get("ok") and app.employee_by_session(token) is None, rev)

        # ESS personal + bank HR→Payroll + encrypt
        personal = w5.create_request(
            app, emp, employee_key=key_e, request_type="personal_detail_change",
            proposed_values={"preferred_name": f"Pref-{tag}", "city": "Kuwait"},
            idempotency_key=f"{idem}:pers", requester_kind="employee",
        )
        pid = str(personal["request"]["request_id"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL, state='approved' WHERE request_id=%s", (pid,))
                conn.commit()
        check("personal apply", w5.apply_request(app, hr, request_id=pid).get("ok"))

        bank = w5.create_request(
            app, emp, employee_key=key_e, request_type="bank_detail_change",
            proposed_values={"iban": "KW81CBKU0000000000001234560101", "bank_name": "CBK", "account_holder": "Emp"},
            idempotency_key=f"{idem}:bank", requester_kind="employee",
        )
        bid = str(bank["request"]["request_id"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL WHERE request_id=%s", (bid,))
                conn.commit()
        d1 = w5.decide_request(app, hr, request_id=bid, action="approve")
        check("bank → payroll", (d1.get("request") or {}).get("state") == "pending_payroll", d1)
        d2 = w5.decide_request(app, hr, request_id=bid, action="approve")
        check("approve ≠ apply", (d2.get("request") or {}).get("state") == "approved" and d2.get("applied") is False, d2)
        ba = w5.apply_request(app, hr, request_id=bid, idempotency_key=f"{idem}:bank-apply")
        ba2 = w5.apply_request(app, hr, request_id=bid, idempotency_key=f"{idem}:bank-apply")
        check("bank apply + idempotent", ba.get("ok") and (ba2.get("idempotent") or (ba2.get("request") or {}).get("state") == "applied"), ba2)
        masked = w5.get_own_view(app, emp, employee_key=key_e)
        check("bank masked default", (masked.get("bank") or {}).get("iban") in {None, "****"} or (masked.get("bank") or {}).get("has_bank_on_file"), masked.get("bank"))

        # transfer via ESS — effective after the future-dated Wave4 slice to avoid overlap
        xfer_from = fut + timedelta(days=1)
        xfer = w5.create_request(
            app, mgr, employee_key=key_r, request_type="transfer",
            proposed_values={"effective_from": xfer_from.isoformat(), "department_unit_id": dept_id, "location_unit_id": loc_id, "reason": "move"},
            idempotency_key=f"{idem}:xfer", requester_kind="manager",
        )
        xid = str(xfer["request"]["request_id"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL, state='approved' WHERE request_id=%s", (xid,))
                conn.commit()
        check("ess transfer apply via wave4", w5.apply_request(app, hr, request_id=xid).get("ok"))

        # stale → needs_review
        stale = w5.create_request(
            app, emp, employee_key=key_e, request_type="personal_detail_change",
            proposed_values={"city": "Hawalli"}, idempotency_key=f"{idem}:stale", requester_kind="employee",
        )
        sid = str(stale["request"]["request_id"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL, state='approved', expected_personal_version=0 WHERE request_id=%s", (sid,))
                cur.execute("UPDATE employee_ess_personal_profiles SET version=9 WHERE employee_key=%s", (key_e,))
                conn.commit()
        try:
            w5.apply_request(app, hr, request_id=sid)
            check("stale conflict fail-closed", False)
        except Exception as exc:
            check("stale conflict fail-closed", _err(exc) == "overlay_conflict", exc)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT state FROM employee_ess_requests WHERE request_id=%s", (sid,))
                st = dict(cur.fetchone())["state"]
            conn.commit()
        check("stale enters needs_review", st == "needs_review", st)

        # fail-closed gates
        self_req = w5.create_request(
            app, emp, employee_key=key_e, request_type="personal_detail_change",
            proposed_values={"city": "X"}, idempotency_key=f"{idem}:self", requester_kind="employee",
        )
        try:
            w5.decide_request(app, emp, request_id=str(self_req["request"]["request_id"]), action="approve")
            check("self-approval denied", False)
        except Exception as exc:
            check("self-approval denied", _err(exc) == "self_approval_forbidden", exc)
        try:
            w5.create_request(
                app, ctx(hr_id, company_code="OTHERCO", employee_key=key_e),
                employee_key=key_e, request_type="personal_detail_change",
                proposed_values={"city": "Y"}, idempotency_key=f"{idem}:xt", requester_kind="employee",
            )
            check("cross-tenant denied", False)
        except Exception as exc:
            check("cross-tenant denied", _err(exc) == "ess_v5_disabled", exc)
        try:
            w5.create_request(
                app, emp, employee_key=REAL_KEYS[0], request_type="personal_detail_change",
                proposed_values={"city": "Nope"}, idempotency_key=f"{idem}:real", requester_kind="employee",
            )
            check("real employee ess blocked", False)
        except Exception as exc:
            check("real employee ess blocked", _err(exc) in {"ess_synthetic_only", "own_data_only"} or getattr(exc, "status_code", None) in {403, 404}, exc)

        real_scope = app.manager_scope_context
        app.manager_scope_context = lambda *a, **k: {"restricted": True, "branch_keys": [], "team_keys": [], "direct_employee_keys": []}
        try:
            w5.create_request(
                app, mgr, employee_key=key_r, request_type="transfer",
                proposed_values={"effective_from": (today + timedelta(days=5)).isoformat(), "department_unit_id": dept_id, "reason": "oos"},
                idempotency_key=f"{idem}:oos", requester_kind="manager",
            )
            check("manager-scope denied", False)
        except Exception as exc:
            check("manager-scope denied", getattr(exc, "status_code", None) in {403, 404}, exc)
        finally:
            app.manager_scope_context = real_scope

        rec = w5.reconcile_ess_overlays(app, hr, employee_key=key_e)
        check("ess reconcile callable", isinstance(rec, dict) and rec.get("ok") is not False, rec)

        reals_after = snapshot_reals()
        EVIDENCE["reals"]["after"] = reals_after
        for k in REAL_KEYS:
            check(f"real untouched {k[-8:]}", reals_before[k] == reals_after[k], {"b": reals_before[k], "a": reals_after[k]})

    finally:
        try:
            cleanup()
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT count(*)::int AS n FROM employees WHERE company_code=%s AND (phone LIKE %s OR name LIKE %s)",
                        (company, f"{PHONE_PREFIX}%", f"%{NAME_PREFIX}%"),
                    )
                    left = int(dict(cur.fetchone())["n"])
                conn.commit()
            check("synthetic cleanup zero", left == 0, left)
            EVIDENCE["cleanup"]["remaining"] = left
        except Exception as exc:
            check("synthetic cleanup zero", False, str(exc))

    EVIDENCE["summary"] = {"pass": PASS, "fail": FAIL, "tag": tag}
    out_path = os.environ.get("WAVE7_EVIDENCE_JSON")
    if out_path:
        Path(out_path).write_text(json.dumps(EVIDENCE, default=str, indent=2))
        print(f"evidence_json={out_path}")
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
