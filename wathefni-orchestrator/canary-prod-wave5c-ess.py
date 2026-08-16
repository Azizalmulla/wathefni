#!/usr/bin/env python3
"""Wave 5C — production synthetic canary for ESS self-service (WATHEFNI only).

Allowlist: phones 965549*, names W5C-SYNTH|.
Does not classify or mutate the four real employees.
Does not enable real lifecycle. Does not leave synthetic leftovers.
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
EVIDENCE: dict = {"checks": [], "ids": {}, "reals": {}, "encryption": {}, "session": {}, "cleanup": {}}

PHONE_PREFIX = "965549"
NAME_PREFIX = "W5C-SYNTH|"
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


def _code(exc):
    return getattr(exc, "status_code", None)


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
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import production_data_safety as _r3_data_safety
    _r3_data_safety.require_non_production_ops()
    import app
    import employee_authority_wave2 as authority
    import employee_org_wave4 as w4
    import employee_selfservice_wave5 as w5

    company = "WATHEFNI"
    tag = uuid.uuid4().hex[:8]
    seed = int(tag, 16) % 90000 + 10000
    today = date.today()
    phones = [f"{PHONE_PREFIX}{(seed + i) % 100000:05d}" for i in range(6)]
    for p in phones:
        assert p.isdigit() and len(p) == 11 and p.startswith(PHONE_PREFIX)
    phone_e, phone_m, phone_r, phone_dup, phone_t, phone_s = phones
    idem = f"wave5c-prod:{company}:{tag}"
    keys: list[str] = []
    hr_id = None

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
            "employees.ess.apply", "employees.ess.unmask",
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
                    cur.execute("SELECT employee_key, name, phone FROM employees WHERE company_code=%s AND employee_key=%s", (company, k))
                    hub = dict(cur.fetchone() or {})
                    cur.execute(
                        """
                        SELECT employment_id::text, employment_status, policy_pack_status, lifecycle_state
                        FROM employee_employments WHERE company_code=%s AND legacy_employee_key=%s
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (company, k),
                    )
                    emp = dict(cur.fetchone() or {})
                    cur.execute("SELECT count(*)::int AS n FROM employee_ess_requests WHERE company_code=%s AND employee_key=%s", (company, k))
                    n = int(dict(cur.fetchone())["n"])
                    out[k] = {"hub": hub, "employment": emp, "ess_requests": n}
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
                        "DELETE FROM employee_ess_letter_orders WHERE company_code=%s AND employee_key = ANY(%s)",
                        "DELETE FROM employee_org_assignment_history WHERE company_code=%s AND employee_key = ANY(%s)",
                    ]:
                        cur.execute(sql, (company, all_keys))
                    cur.execute(
                        "DELETE FROM employee_ess_request_events WHERE company_code=%s AND request_id IN (SELECT request_id FROM employee_ess_requests WHERE company_code=%s AND employee_key = ANY(%s))",
                        (company, company, all_keys),
                    )
                    cur.execute("DELETE FROM employee_ess_requests WHERE company_code=%s AND employee_key = ANY(%s)", (company, all_keys))
                    cur.execute("UPDATE employee_sessions SET status='revoked', revoked_at=now(), revoked_reason='wave5c_cleanup' WHERE company_code=%s AND employee_key = ANY(%s) AND status='active'", (company, all_keys))
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

    reals_before = snapshot_reals()
    EVIDENCE["reals"]["before"] = reals_before
    cleanup()
    try:
        load_actor()
        hr = ctx(hr_id)
        check("schema wave5b", w5.SCHEMA_VERSION.startswith("employees360-wave5b"))
        check("ess enabled", w5.ess_v5_enabled(company))
        check("synthetic only on", w5.ess_synthetic_only_enabled())
        check("bank encryption available", w5.bank_encryption_available())
        check("lifecycle synthetic-only on", os.environ.get("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY", "").lower() in {"on", "1", "true", "yes"})

        def create(phone, name, email=None):
            assert phone.startswith(PHONE_PREFIX) and name.startswith(NAME_PREFIX)
            out = app.create_company_employee(company, name=name, phone=phone, email=email, position_title="Role")
            key = str(out.get("employee_key") or (out.get("employee") or {}).get("employee_key"))
            assert key.startswith(f"{company}-{PHONE_PREFIX}")
            keys.append(key)
            return key

        key_e = create(phone_e, f"{NAME_PREFIX}Emp {tag}", email=f"w5c-e-{tag}@example.test")
        key_m = create(phone_m, f"{NAME_PREFIX}Mgr {tag}", email=f"w5c-m-{tag}@example.test")
        key_r = create(phone_r, f"{NAME_PREFIX}Rpt {tag}", email=f"w5c-r-{tag}@example.test")
        key_dup = create(phone_dup, f"{NAME_PREFIX}Dup {tag}", email=f"w5c-d-{tag}@example.test")
        key_term = create(phone_t, f"{NAME_PREFIX}Term {tag}")
        key_susp = create(phone_s, f"{NAME_PREFIX}Susp {tag}")
        EVIDENCE["ids"]["employees"] = {"e": key_e, "m": key_m, "r": key_r, "dup": key_dup, "term": key_term, "susp": key_susp}
        authority.backfill_company_authority(
            app, company_code=company, idempotency_key=f"{idem}:bf",
            employee_keys=[key_e, key_m, key_r, key_dup, key_term, key_susp],
        )
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
            conn.commit()

        # Identity bind
        bind = w5.bind_employee_identity(app, emp, employee_key=key_e)
        check("identity binds", bind.get("ok") and (bind.get("binding") or {}).get("employee_key") == key_e, bind)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT person_id::text, employment_id::text FROM employee_key_authority_map WHERE employee_key=%s", (key_e,))
                auth = dict(cur.fetchone() or {})
            conn.commit()
        b = bind.get("binding") or {}
        check("bind matches person/employment", str(b.get("person_id")) == str(auth.get("person_id")) and str(b.get("employment_id")) == str(auth.get("employment_id")), {"bind": b, "auth": auth})
        EVIDENCE["session"]["binding"] = {"employee_key": key_e, "session_epoch": b.get("session_epoch"), "person_ok": True}

        # /app session epoch wiring
        sess = app.create_employee_session(company, key_e, phone_e)
        token = sess["token"]
        check("session stamped with epoch", sess.get("ess_session_epoch") == b.get("session_epoch") or sess.get("ess_session_epoch") is not None, sess)
        live = app.employee_by_session(token)
        check("session auth works pre-revoke", live and live.get("employee_key") == key_e, live)
        rev = w5.revoke_employee_sessions(app, hr, employee_key=key_e, reason="wave5c_canary")
        check("session revoke ok", rev.get("ok"), rev)
        stale = app.employee_by_session(token)
        check("stale /app token rejected", stale is None, stale)
        hist = app.employee_session_record(token)
        check(
            "revoked reason ess_session_epoch",
            str((hist or {}).get("revoked_reason") or "") in {"ess_session_epoch_stale", "ess_session_epoch_bump"}
            or str((hist or {}).get("status") or "") == "revoked",
            hist,
        )
        EVIDENCE["session"]["revoke"] = {"app_sessions_revoked": rev.get("app_sessions_revoked"), "reason": (hist or {}).get("revoked_reason")}

        # Own data / manager scope
        own = w5.get_own_view(app, emp, employee_key=key_e)
        check("employee own view", own.get("ok") and own.get("employee_key") == key_e, own)
        reports = w5.list_manager_reports(app, mgr, as_of=today)
        rkeys = {r["employee_key"] for r in reports.get("reports") or []}
        check("manager sees in-scope reports", key_e in rkeys or key_r in rkeys, reports)

        # Personal + emergency
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
        pa = w5.apply_request(app, hr, request_id=pid, idempotency_key=f"{idem}:pers-apply")
        check("personal apply", pa.get("ok") and (pa.get("request") or {}).get("state") == "applied", pa)
        emerg = w5.create_request(
            app, emp, employee_key=key_e, request_type="emergency_contact_change",
            proposed_values={"contact_name": "EC", "contact_phone": "96550001111"},
            idempotency_key=f"{idem}:ec", requester_kind="employee",
        )
        eid = str(emerg["request"]["request_id"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL, state='approved' WHERE request_id=%s", (eid,))
                conn.commit()
        ea = w5.apply_request(app, hr, request_id=eid)
        check("emergency apply", ea.get("ok"), ea)

        # Bank HR → Payroll → encrypt
        bank = w5.create_request(
            app, emp, employee_key=key_e, request_type="bank_detail_change",
            proposed_values={"iban": "KW81CBKU0000000000001234560101", "bank_name": "CBK", "account_holder": "Emp"},
            idempotency_key=f"{idem}:bank", requester_kind="employee",
        )
        bid = str(bank["request"]["request_id"])
        check("bank pending_hr", (bank.get("request") or {}).get("state") == "pending_hr", bank)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL WHERE request_id=%s", (bid,))
                conn.commit()
        d1 = w5.decide_request(app, hr, request_id=bid, action="approve")
        check("bank after hr → payroll", (d1.get("request") or {}).get("state") == "pending_payroll", d1)
        d2 = w5.decide_request(app, hr, request_id=bid, action="approve")
        check("bank approved separate from apply", (d2.get("request") or {}).get("state") == "approved" and d2.get("applied") is False, d2)
        ba = w5.apply_request(app, hr, request_id=bid, idempotency_key=f"{idem}:bank-apply")
        check("bank applied", ba.get("ok"), ba)
        ba2 = w5.apply_request(app, hr, request_id=bid, idempotency_key=f"{idem}:bank-apply")
        check("bank apply idempotent", ba2.get("idempotent") or (ba2.get("request") or {}).get("state") == "applied", ba2)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT bank_ciphertext, bank_fingerprint FROM employee_ess_bank_profiles WHERE employee_key=%s", (key_e,))
                brow = dict(cur.fetchone())
                blob = brow["bank_ciphertext"]
                if isinstance(blob, str):
                    blob = json.loads(blob)
            conn.commit()
        check("bank encrypted at rest", blob.get("schema") == "ess_bank_v1" and "ciphertext" in blob and "iban" not in blob, {"keys": list(blob.keys())})
        EVIDENCE["encryption"]["fingerprint"] = brow.get("bank_fingerprint")
        EVIDENCE["encryption"]["schema"] = blob.get("schema")
        EVIDENCE["encryption"]["has_ciphertext"] = bool(blob.get("ciphertext"))
        masked = w5.get_own_view(app, emp, employee_key=key_e)
        check("bank masked by default", (masked.get("bank") or {}).get("iban") == "****" or (masked.get("bank") or {}).get("has_bank_on_file"), masked.get("bank"))
        try:
            w5.create_request(
                app, emp, employee_key=key_e, request_type="bank_detail_change",
                proposed_values={"iban": "KW81CBKU0000000000001234560199", "store_plaintext": True},
                idempotency_key=f"{idem}:pt", requester_kind="employee",
            )
            check("plaintext bank rejected", False)
        except Exception as exc:
            check("plaintext bank rejected", _err(exc) == "plaintext_bank_forbidden", exc)
        unmasked = w5.get_own_view(app, hr, employee_key=key_e)
        check("authorized unmask", "KW81" in str((unmasked.get("bank") or {}).get("iban") or ""), unmasked.get("bank"))
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*)::int AS n FROM employee_ess_sensitive_access_log WHERE company_code=%s AND employee_key=%s AND action='unmask_bank'",
                    (company, key_e),
                )
                n_audit = int(dict(cur.fetchone())["n"])
            conn.commit()
        check("unmask audited", n_audit >= 1, n_audit)
        rot = w5.rotate_bank_encryption(app, hr, employee_key=key_e)
        check("key rotation/re-wrap", rot.get("ok") and rot.get("version"), rot)
        EVIDENCE["encryption"]["rotated_version"] = rot.get("version")

        # Document versions
        for i, ver in enumerate([1, 2], start=1):
            doc = w5.create_request(
                app, emp, employee_key=key_e, request_type="document_change",
                proposed_values={"document_key": "civil_id", "storage_ref": f"ess/{tag}/v{ver}"},
                idempotency_key=f"{idem}:doc{ver}", requester_kind="employee",
            )
            did = str(doc["request"]["request_id"])
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL, state='approved' WHERE request_id=%s", (did,))
                    conn.commit()
            w5.apply_request(app, hr, request_id=did)
        own2 = w5.get_own_view(app, emp, employee_key=key_e)
        civil = [d for d in (own2.get("documents") or []) if d.get("document_key") == "civil_id"]
        check("document versions preserved", len(civil) >= 2, civil)

        # Transfer + manager-change via Wave 4
        hist_before = w4.list_assignment_history(app, company_code=company, employee_key=key_r)
        xfer = w5.create_request(
            app, mgr, employee_key=key_r, request_type="transfer",
            proposed_values={"effective_from": today.isoformat(), "department_unit_id": dept_id, "location_unit_id": loc_id, "reason": "move"},
            idempotency_key=f"{idem}:xfer", requester_kind="manager",
        )
        xid = str(xfer["request"]["request_id"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL, state='approved' WHERE request_id=%s", (xid,))
                conn.commit()
        xa = w5.apply_request(app, hr, request_id=xid)
        check("transfer applied via wave4", xa.get("ok") and (xa.get("request") or {}).get("state") == "applied", xa)
        mgr_ch = w5.create_request(
            app, mgr, employee_key=key_r, request_type="manager_change",
            proposed_values={"effective_from": (today + timedelta(days=1)).isoformat(), "manager_employee_key": key_e, "reason": "mgr"},
            idempotency_key=f"{idem}:mgr", requester_kind="manager",
        )
        mid = str(mgr_ch["request"]["request_id"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employee_ess_requests SET requester_user_id=NULL, state='approved' WHERE request_id=%s", (mid,))
                conn.commit()
        ma = w5.apply_request(app, hr, request_id=mid)
        check("manager-change applied via wave4", ma.get("ok"), ma)
        hist_after = w4.list_assignment_history(app, company_code=company, employee_key=key_r)
        check("wave4 history grew", len(hist_after) > len(hist_before), {"b": len(hist_before), "a": len(hist_after)})

        # Stale conflict → needs_review
        stale = w5.create_request(
            app, emp, employee_key=key_e, request_type="personal_detail_change",
            proposed_values={"city": "Hawalli"}, idempotency_key=f"{idem}:stale", requester_kind="employee",
        )
        sid = str(stale["request"]["request_id"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE employee_ess_requests SET requester_user_id=NULL, state='approved', expected_personal_version=0 WHERE request_id=%s",
                    (sid,),
                )
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

        # Duplicate phone bind
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE employees SET phone=%s WHERE employee_key=%s", (phone_e, key_dup))
            conn.commit()
        try:
            w5.bind_employee_identity(app, ctx(hr_id, employee_key=key_dup), employee_key=key_dup)
            check("duplicate phone bind fails", False)
        except Exception as exc:
            check("duplicate phone bind fails", _err(exc) == "phone_already_bound", exc)

        # Suspended / terminated
        try:
            w5.bind_employee_identity(app, ctx(hr_id, employee_key=key_term), employee_key=key_term)
            check("terminated session denied", False)
        except Exception as exc:
            check("terminated session denied", _err(exc) == "session_not_allowed", exc)
        try:
            w5.create_request(
                app, ctx(hr_id, employee_key=key_susp), employee_key=key_susp,
                request_type="bank_detail_change", proposed_values={"iban": "KW81CBKU0000000000001234560188"},
                idempotency_key=f"{idem}:susp", requester_kind="employee",
            )
            check("suspended bank blocked", False)
        except Exception as exc:
            check("suspended bank blocked", _err(exc) == "suspended_employee_request_blocked", exc)

        # Self-approval / scope / cross-tenant
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
        real_scope = app.manager_scope_context
        app.manager_scope_context = lambda *a, **k: {"restricted": True, "branch_keys": [], "team_keys": [], "direct_employee_keys": []}
        try:
            w5.create_request(
                app, mgr, employee_key=key_r, request_type="transfer",
                proposed_values={"effective_from": (today + timedelta(days=2)).isoformat(), "department_unit_id": dept_id, "reason": "oos"},
                idempotency_key=f"{idem}:oos", requester_kind="manager",
            )
            check("manager-scope denied", False)
        except Exception as exc:
            check("manager-scope denied", _code(exc) in {403, 404}, exc)
        finally:
            app.manager_scope_context = real_scope

        # Real employee blocked by synthetic gate
        try:
            w5.create_request(
                app, emp, employee_key=REAL_KEYS[0], request_type="personal_detail_change",
                proposed_values={"city": "Nope"}, idempotency_key=f"{idem}:real", requester_kind="employee",
            )
            check("real employee ess blocked", False)
        except Exception as exc:
            check("real employee ess blocked", _err(exc) in {"ess_synthetic_only", "own_data_only", "employee_not_found"} or _code(exc) in {403, 404}, exc)

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

    EVIDENCE["summary"] = {"pass": PASS, "fail": FAIL, "tag": tag, "phone_prefix": PHONE_PREFIX}
    out_path = os.environ.get("WAVE5C_EVIDENCE_JSON")
    if out_path:
        Path(out_path).write_text(json.dumps(EVIDENCE, default=str, indent=2))
        print(f"evidence_json={out_path}")
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
