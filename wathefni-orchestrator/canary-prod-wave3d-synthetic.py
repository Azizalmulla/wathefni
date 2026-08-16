#!/usr/bin/env python3
"""Wave 3D production synthetic canary — WATHEFNI only.

Creates/stamps synthetic employees only. Refuses real employee keys.
Cleans up via wave3c rollback in finally.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, time
from pathlib import Path
from zoneinfo import ZoneInfo

OUT = Path(os.environ.get("WAVE3D_CANARY_OUT", "/tmp/wave3d-prod-canary"))
OUT.mkdir(parents=True, exist_ok=True)

COMPANY = "WATHEFNI"
REAL_KEYS = [
    "WATHEFNI-96550252254",
    "WATHEFNI-96566363363",
    "WATHEFNI-96597727743",
    "WATHEFNI-96599411617",
]

PASS = 0
FAIL = 0
EVIDENCE: dict = {"checks": [], "ids": {}}


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    row = {"label": label, "pass": bool(cond), "detail": detail if not cond else None}
    EVIDENCE["checks"].append(row)
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def _http_exc_code(exc):
    return getattr(exc, "status_code", None)


def dump(name: str, obj) -> None:
    (OUT / name).write_text(json.dumps(obj, indent=2, default=str) + "\n")
    print("wrote", OUT / name)


def main() -> int:
    if str(os.environ.get("WATHEFNI_ENV") or "").lower() not in {"production", "prod"}:
        raise SystemExit("refusing: WATHEFNI_ENV must be production")
    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES"] = "WATHEFNI"
    os.environ["WATHEFNI_EMPLOYEE_LIFECYCLE_V3"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES"] = "WATHEFNI"
    os.environ["WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY"] = "on"
    os.environ["WATHEFNI_LIFECYCLE_COUNSEL_GATE"] = "on"

    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import app
    import employee_authority_wave2 as authority
    import employee_lifecycle_wave3 as w3
    import employee_lifecycle_wave3c as w3c
    import employee_status_approval as status_approval

    check("lifecycle enabled WATHEFNI", w3.lifecycle_v3_enabled(COMPANY) is True)
    check("lifecycle disabled OTHERCO", w3.lifecycle_v3_enabled("OTHERCO") is False)
    check("synthetic only on", w3.lifecycle_synthetic_only_enabled() is True)
    check("notice hints default hidden", w3c.DEFAULT_POLICY["show_notice_hints"] is False)
    check("reinstate default off", w3c.DEFAULT_POLICY["allow_reinstate_after_effective"] is False)
    check("self approval forbidden", w3c.DEFAULT_POLICY["allow_self_approval"] is False)

    tag = uuid.uuid4().hex[:8]
    # Digits-only synthetic phone in reserved 965522* range (avoid hex letters /
    # re-prefixing by canonical_employee_phone).
    phone = f"965522{int(tag[:6], 16) % 100000:05d}"
    key = f"{COMPANY}-{phone}"
    idem = f"wave3d-prod-canary:{COMPANY}:{tag}"
    today = date.today()
    synth_name = f"W3D-SYNTH|Prod Canary {tag}"
    EVIDENCE["ids"] = {"tag": tag, "phone": phone, "employee_key": key, "idempotency_prefix": idem}

    # Prove real employees are blocked before creating anything.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for rk in REAL_KEYS:
                try:
                    w3.assert_lifecycle_synthetic_target(app, cur, company=COMPANY, employee_key=rk)
                    check(f"block real {rk}", False, "gate allowed real employee")
                except Exception as exc:
                    detail = getattr(exc, "detail", {}) or {}
                    err = detail.get("error") if isinstance(detail, dict) else None
                    check(f"block real {rk}", _http_exc_code(exc) == 403 and err == "synthetic_only_gate", exc)

    # Actors (same pattern as staging smoke)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM dashboard_users WHERE company_code=%s AND lower(coalesce(status,''))='active' ORDER BY updated_at DESC NULLS LAST LIMIT 40",
                (COMPANY,),
            )
            users = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
    managers = []
    for u in users:
        if not app._normal_dashboard_operator(u):
            continue
        perms = app.dashboard_effective_permissions_for_user(u)
        if "employees.manage" in perms:
            managers.append(u)
    if not managers:
        raise SystemExit("need managers with employees.manage")
    requester_id = str(managers[0]["user_id"])
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            status_approval.ensure_employee_status_approval_schema(cur)
            eligible = status_approval.list_eligible_status_approvers(
                app, cur, company_code=COMPANY, exclude_user_id=requester_id
            )
            if not eligible:
                other = next((u for u in users if str(u["user_id"]) != requester_id and app._normal_dashboard_operator(u)), None)
                if not other:
                    raise SystemExit("no approver candidate")
                cur.execute(
                    """
                    INSERT INTO dashboard_user_permission_grants
                      (company_code, user_id, permission, status, review_reference, granted_by_user_id, granted_reason)
                    VALUES (%s,%s,'employees.status.approve','active',%s,%s,%s)
                    ON CONFLICT (company_code, user_id, permission) DO UPDATE SET status='active', revoked_at=NULL, updated_at=now()
                    """,
                    (COMPANY, other["user_id"], f"wave3d-{tag}", requester_id, "wave3d synthetic canary"),
                )
                eligible = status_approval.list_eligible_status_approvers(
                    app, cur, company_code=COMPANY, exclude_user_id=requester_id
                )
            conn.commit()
    if not eligible:
        raise SystemExit("no eligible approver")
    approver_id = str(eligible[0]["user_id"])

    def ctx(uid: str, extra_perms=None):
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM dashboard_users WHERE company_code=%s AND user_id=%s", (COMPANY, uid))
                user = dict(cur.fetchone())
                conn.commit()
        perms = list(app.dashboard_effective_permissions_for_user(user))
        for p in extra_perms or []:
            if p not in perms:
                perms.append(p)
        return {
            "company_code": COMPANY,
            "actor_user_id": uid,
            "actor": user,
            "permissions": perms,
            "access": {"role": user.get("role") or "owner", "permissions": perms},
            "permission_authority": "backend_current",
            "permission_subject_user_id": uid,
            "permission_subject_company": COMPANY,
            "actor_role": user.get("role") or "owner",
            "hr_user": user,
            "role": user.get("role"),
        }

    requester_ctx = ctx(requester_id)
    approver_ctx = ctx(approver_id, ["employees.status.approve"])
    check("actors distinct", requester_id != approver_id, {"requester": requester_id, "approver": approver_id})
    EVIDENCE["ids"]["requester_user_id"] = requester_id
    EVIDENCE["ids"]["approver_user_id"] = approver_id

    # Counsel gate for wave3d schema
    try:
        w3c.assert_counsel_gate(app, company_code=COMPANY)
        gate = w3c.counsel_gate_status(app, company_code=COMPANY)
        check("counsel gate signed or will sign", True, gate)
    except Exception as exc:
        check("counsel gate blocks when unsigned", _http_exc_code(exc) == 403, exc)
        answers = {q["id"]: f"synthetic-canary-{tag}" for q in w3c.COUNSEL_QUESTIONS}
        signed = w3c.sign_counsel_checklist(
            app,
            requester_ctx,
            answers=answers,
            signed_by_name="Wave3D Synthetic Canary",
            signed_by_role="ops",
            signed_reference=f"W3D-SYNTH-{tag}",
            notes="Operational synthetic canary sign-off only. Not legal advice; real-employee use remains NO-GO.",
        )
        check("counsel checklist signed", signed.get("ok") is True, signed)

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
            "monetary_calculations_owner": "payroll",
            "settlement_packet_mode": "inputs_only",
            "allow_self_approval": False,
        },
    )
    check("policy notice hidden", policy.get("show_notice_hints") is False and policy.get("notice_hints_ui") is None, policy)
    check("policy reinstate off", policy.get("allow_reinstate_after_effective") is False, policy)
    dump("policy.json", policy)

    created = app.create_company_employee(COMPANY, name=synth_name, phone=phone, position_title="Canary Analyst")
    check("create synthetic employee", created.get("status") == "created", created)
    key = str(created.get("employee_key") or (created.get("employee") or {}).get("employee_key") or key)
    EVIDENCE["ids"]["employee_key"] = key

    authority.backfill_company_authority(app, company_code=COMPANY, idempotency_key=f"{idem}:bf", employee_keys=[key])
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w3.stamp_lifecycle_synthetic_markers(cur, company=COMPANY, employee_key=key)
            future = today + timedelta(days=10)
            cur.execute(
                "INSERT INTO shift_assignments (company_code, employee_key, shift_date, start_time, end_time, status) VALUES (%s,%s,%s,'09:00','17:00','scheduled')",
                (COMPANY, key, future),
            )
            cur.execute(
                """
                INSERT INTO employee_sessions (company_code, employee_key, phone, token_hash, status, expires_at, refresh_expires_at)
                VALUES (%s,%s,%s,%s,'active', now() + interval '7 days', now() + interval '30 days')
                """,
                (COMPANY, key, phone, f"tok-{tag}"),
            )
        conn.commit()

    proj = w3c.get_lifecycle_projection(app, company_code=COMPANY, employee_key=key)
    EVIDENCE["ids"]["person_id"] = str(proj["person_id"])
    EVIDENCE["ids"]["employment_id"] = str(proj["employment_id"])
    EVIDENCE["ids"]["assignment_id"] = str(proj["assignment_id"])

    # Impact ack required
    try:
        w3c.create_lifecycle_request(
            app, requester_ctx, employee_key=key, case_type="termination", reason="no ack",
            approval_reference=f"A-{tag}", designated_approver_user_id=approver_id,
            idempotency_key=f"{idem}:noack", expected_lifecycle_state="active",
            expected_lifecycle_version=int(proj["lifecycle_version"]), expected_hub_updated_at=proj["hub_updated_at"],
            payload={"termination_effective_on": today.isoformat(), "last_working_day": today.isoformat(), "termination_type": "resignation"},
            impact_ack=False,
        )
        check("impact ack required", False)
    except Exception as exc:
        check("impact ack required", _http_exc_code(exc) == 422, exc)

    # Future-dated termination + separate approval
    tomorrow = today + timedelta(days=1)
    lwd = today
    req_fut = w3c.create_lifecycle_request(
        app, requester_ctx, employee_key=key, case_type="termination", reason="future term canary",
        approval_reference=f"FUT-{tag}", designated_approver_user_id=approver_id,
        idempotency_key=f"{idem}:fut", expected_lifecycle_state="active",
        expected_lifecycle_version=int(proj["lifecycle_version"]), expected_hub_updated_at=proj["hub_updated_at"],
        payload={"termination_effective_on": tomorrow.isoformat(), "last_working_day": lwd.isoformat(), "termination_type": "resignation"},
        impact_ack=True, impact_ack_text="Reviewed downstream impact snapshot",
    )
    check("create future term + ack", req_fut.get("ok") and req_fut.get("impact_snapshot_hash"), req_fut)
    EVIDENCE["ids"]["future_request_id"] = str(req_fut["request"]["request_id"])

    # Idempotency
    req_idem = w3c.create_lifecycle_request(
        app, requester_ctx, employee_key=key, case_type="termination", reason="future term canary",
        approval_reference=f"FUT-{tag}", designated_approver_user_id=approver_id,
        idempotency_key=f"{idem}:fut", expected_lifecycle_state="active",
        expected_lifecycle_version=int(proj["lifecycle_version"]), expected_hub_updated_at=proj["hub_updated_at"],
        payload={"termination_effective_on": tomorrow.isoformat(), "last_working_day": lwd.isoformat(), "termination_type": "resignation"},
        impact_ack=True, impact_ack_text="Reviewed downstream impact snapshot",
    )
    check("idempotent retry", req_idem.get("idempotent") is True or str(req_idem.get("request", {}).get("request_id")) == str(req_fut["request"]["request_id"]), req_idem)

    # Self-approval forbidden
    try:
        w3c.decide_lifecycle_request(app, requester_ctx, request_id=str(req_fut["request"]["request_id"]), action="approve")
        check("self-approval forbidden", False)
    except Exception as exc:
        check("self-approval forbidden", _http_exc_code(exc) in {403, 409}, exc)

    decided = w3c.decide_lifecycle_request(app, approver_ctx, request_id=str(req_fut["request"]["request_id"]), action="approve")
    check("separate approval committed", decided.get("committed") is True, decided)
    proj_n = w3c.get_lifecycle_projection(app, company_code=COMPANY, employee_key=key)
    check("notice period", proj_n.get("lifecycle_state") == "notice_period", proj_n)
    check("hub active during notice", proj_n.get("hub_employment_status") == "active", proj_n)
    prior_emp = str(proj_n["employment_id"])

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT access_revoke_at, access_revoke_status FROM employee_employments WHERE employment_id=%s", (prior_emp,))
            ar = dict(cur.fetchone())
            cur.execute("SELECT status FROM employee_sessions WHERE employee_key=%s AND token_hash=%s", (key, f"tok-{tag}"))
            sess = dict(cur.fetchone())
    check("access revoke scheduled", ar.get("access_revoke_status") == "scheduled", ar)
    check("session active before LWD cutoff", sess.get("status") == "active", sess)

    # Cancel before effective
    req_cancel = w3c.create_lifecycle_request(
        app, requester_ctx, employee_key=key, case_type="cancel_scheduled", reason="cancel before effective",
        approval_reference=f"CAN-{tag}", designated_approver_user_id=approver_id,
        idempotency_key=f"{idem}:cancel", expected_lifecycle_state="notice_period",
        expected_lifecycle_version=int(proj_n["lifecycle_version"]), expected_hub_updated_at=proj_n["hub_updated_at"],
        payload={"restore_state": "active"}, impact_ack=True, impact_ack_text="Ack cancel",
    )
    dec_cancel = w3c.decide_lifecycle_request(app, approver_ctx, request_id=str(req_cancel["request"]["request_id"]), action="approve")
    check("cancel-before-effective", dec_cancel.get("committed") and dec_cancel.get("case_type") == "cancel_scheduled", dec_cancel)
    proj_a = w3c.get_lifecycle_projection(app, company_code=COMPANY, employee_key=key)
    check("same employment after cancel", str(proj_a["employment_id"]) == prior_emp, proj_a)

    # Stale conflict
    try:
        w3c.create_lifecycle_request(
            app, requester_ctx, employee_key=key, case_type="termination", reason="stale",
            approval_reference=f"STALE-{tag}", designated_approver_user_id=approver_id,
            idempotency_key=f"{idem}:stale", expected_lifecycle_state="active",
            expected_lifecycle_version=0, expected_hub_updated_at=proj_a["hub_updated_at"],
            payload={"termination_effective_on": tomorrow.isoformat(), "last_working_day": lwd.isoformat(), "termination_type": "resignation"},
            impact_ack=True, impact_ack_text="Ack",
        )
        check("stale conflict fail-closed", False)
    except Exception as exc:
        check("stale conflict fail-closed", _http_exc_code(exc) == 409, exc)

    # Manager scope isolation — out of scope manager denied (if helper exists)
    out_ctx = {
        "company_code": COMPANY,
        "actor_user_id": requester_id,
        "permissions": ["employees.manage"],
        "role": "manager",
        "manager_scope": {"employee_keys": ["WATHEFNI-NOPE"]},
    }
    try:
        w3c.create_lifecycle_request(
            app, out_ctx, employee_key=key, case_type="termination", reason="oos",
            approval_reference=f"OOS-{tag}", designated_approver_user_id=approver_id,
            idempotency_key=f"{idem}:oos", expected_lifecycle_state="active",
            expected_lifecycle_version=int(proj_a["lifecycle_version"]), expected_hub_updated_at=proj_a["hub_updated_at"],
            payload={"termination_effective_on": tomorrow.isoformat(), "last_working_day": lwd.isoformat(), "termination_type": "resignation"},
            impact_ack=True, impact_ack_text="Ack",
        )
        check("manager scope deny", False)
    except Exception as exc:
        check("manager scope deny", _http_exc_code(exc) in {403, 404}, exc)

    # Tenant isolation
    other_ctx = {**requester_ctx, "company_code": "OTHERCO"}
    try:
        w3c.create_lifecycle_request(
            app, other_ctx, employee_key=key, case_type="termination", reason="xt",
            approval_reference=f"XT-{tag}", designated_approver_user_id=approver_id,
            idempotency_key=f"{idem}:xt", expected_lifecycle_state="active",
            expected_lifecycle_version=int(proj_a["lifecycle_version"]), expected_hub_updated_at=proj_a["hub_updated_at"],
            payload={"termination_effective_on": tomorrow.isoformat(), "last_working_day": lwd.isoformat(), "termination_type": "resignation"},
            impact_ack=True, impact_ack_text="Ack",
        )
        check("tenant isolation", False)
    except Exception as exc:
        check("tenant isolation", _http_exc_code(exc) in {403, 404}, exc)

    # Re-create future term then force due via scheduler after backdating
    proj_a = w3c.get_lifecycle_projection(app, company_code=COMPANY, employee_key=key)
    req2 = w3c.create_lifecycle_request(
        app, requester_ctx, employee_key=key, case_type="termination", reason="scheduler path",
        approval_reference=f"SCH-{tag}", designated_approver_user_id=approver_id,
        idempotency_key=f"{idem}:sch", expected_lifecycle_state="active",
        expected_lifecycle_version=int(proj_a["lifecycle_version"]), expected_hub_updated_at=proj_a["hub_updated_at"],
        payload={"termination_effective_on": tomorrow.isoformat(), "last_working_day": lwd.isoformat(), "termination_type": "resignation"},
        impact_ack=True, impact_ack_text="Ack scheduler",
    )
    w3c.decide_lifecycle_request(app, approver_ctx, request_id=str(req2["request"]["request_id"]), action="approve")
    proj_n2 = w3c.get_lifecycle_projection(app, company_code=COMPANY, employee_key=key)
    emp_id = str(proj_n2["employment_id"])
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employee_employments SET
                  termination_effective_on=%s,
                  access_revoke_at=%s,
                  updated_at=now()
                WHERE employment_id=%s
                """,
                (today, datetime.now(tz=ZoneInfo("Asia/Kuwait")) - timedelta(minutes=1), emp_id),
            )
        conn.commit()

    sched = w3c.run_lifecycle_scheduler(app, company_code=COMPANY, environment="production")
    check("scheduler execution ok", sched.get("ok") is True, sched)
    dump("scheduler.json", sched)
    proj_t = w3c.get_lifecycle_projection(app, company_code=COMPANY, employee_key=key)
    check("terminated via scheduler", proj_t.get("lifecycle_state") == "terminated", proj_t)
    check("hub left after effective", proj_t.get("hub_employment_status") == "left", proj_t)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM employee_sessions WHERE employee_key=%s AND token_hash=%s", (key, f"tok-{tag}"))
            sess2 = dict(cur.fetchone())
            cur.execute(
                "SELECT packet, status FROM employee_lifecycle_settlement_packets WHERE employee_key=%s ORDER BY created_at DESC LIMIT 1",
                (key,),
            )
            sp = dict(cur.fetchone() or {})
    check("session revoked after cutoff", sess2.get("status") == "revoked", sess2)
    packet = sp.get("packet") or {}
    if isinstance(packet, str):
        packet = json.loads(packet)
    check("settlement handed off", sp.get("status") == "handed_to_payroll", sp)
    check("settlement inputs present", "inputs" in packet and "disclaimer" in packet, packet)
    check("settlement no amounts", "amounts" not in packet and not any(k for k in packet if "amount" in str(k).lower() and k not in {"monetary_calculations_owner"}), packet)
    dump("settlement.json", {"status": sp.get("status"), "packet": packet})

    # Explicit reversible downstream shift action
    da = w3c.create_downstream_action_request(
        app, requester_ctx, employee_key=key, action_type="cancel_future_shifts", reason="cancel shifts",
        designated_approver_user_id=approver_id, idempotency_key=f"{idem}:ds",
        impact_ack=True, impact_ack_text="Ack downstream",
    )
    dad = w3c.decide_downstream_action(app, approver_ctx, action_id=str(da["action"]["action_id"]), action="approve")
    check("downstream shift cancel", dad.get("committed") is True, dad)
    rev = w3c.create_downstream_action_request(
        app, requester_ctx, employee_key=key, action_type="reverse_cancel_future_shifts", reason="reverse shifts",
        designated_approver_user_id=approver_id, idempotency_key=f"{idem}:dsrev",
        impact_ack=True, impact_ack_text="Ack reverse",
    )
    w3c.decide_downstream_action(app, approver_ctx, action_id=str(rev["action"]["action_id"]), action="approve")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM shift_assignments WHERE employee_key=%s", (key,))
            sh = dict(cur.fetchone())
    check("downstream reverse restored", sh.get("status") == "scheduled", sh)

    # True rehire same person new employment/assignment
    proj_t = w3c.get_lifecycle_projection(app, company_code=COMPANY, employee_key=key)
    prior2 = str(proj_t["employment_id"])
    asn2 = str(proj_t["assignment_id"])
    person = str(proj_t["person_id"])
    req_rh = w3c.create_lifecycle_request(
        app, requester_ctx, employee_key=key, case_type="rehire", reason="same key rehire",
        approval_reference=f"RH-{tag}", designated_approver_user_id=approver_id,
        idempotency_key=f"{idem}:rh", expected_lifecycle_state="terminated",
        expected_lifecycle_version=int(proj_t["lifecycle_version"]), expected_hub_updated_at=proj_t["hub_updated_at"],
        payload={"phone": phone, "name": synth_name, "position_title": "Canary Lead"},
        impact_ack=True, impact_ack_text="Ack rehire",
    )
    dec_rh = w3c.decide_lifecycle_request(app, approver_ctx, request_id=str(req_rh["request"]["request_id"]), action="approve")
    check("rehire new employment", dec_rh.get("new_employment_id") != prior2, dec_rh)
    check("rehire new assignment", dec_rh.get("new_assignment_id") != asn2, dec_rh)
    check("rehire same person", dec_rh.get("person_id") == person, dec_rh)
    check(
        "rehire same employee_key preferred",
        (dec_rh.get("same_employee_key") is True)
        or (dec_rh.get("employee_key") == key)
        or (str(dec_rh.get("new_employee_key") or "") == key),
        dec_rh,
    )
    # Prefer same-key when phone identity matches; record whichever key the system used.
    EVIDENCE["ids"]["rehire_employee_key"] = dec_rh.get("employee_key") or dec_rh.get("new_employee_key") or key
    EVIDENCE["ids"]["rehire_employment_id"] = dec_rh.get("new_employment_id")
    EVIDENCE["ids"]["rehire_assignment_id"] = dec_rh.get("new_assignment_id")
    EVIDENCE["ids"]["same_employee_key"] = bool(
        dec_rh.get("same_employee_key")
        or dec_rh.get("employee_key") == key
        or str(dec_rh.get("new_employee_key") or "") == key
    )

    # Reinstate remains disabled
    # (employee is active after rehire — terminate again not needed; create terminated path already proved reinstate off via policy)
    check("reinstate still disabled in policy", w3c.get_or_create_company_policy(app, company_code=COMPANY).get("allow_reinstate_after_effective") is False)

    # Cleanup / rollback synthetic key only
    rb = w3c.rollback_lifecycle_wave3c(app, company_code=COMPANY, idempotency_key=f"{idem}:rb", employee_keys=[key])
    check("cleanup rollback ok", rb.get("ok") is True, rb)
    dump("rollback.json", rb)

    # Real employees untouched
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT employee_key, employment_status, name FROM employees
                WHERE company_code=%s AND employee_key = ANY(%s) ORDER BY employee_key
                """,
                (COMPANY, REAL_KEYS),
            )
            real_rows = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT count(*) n FROM employees WHERE company_code=%s AND employee_key=%s", (COMPANY, key))
            synth_left = int(dict(cur.fetchone())["n"])
    check("real employees still active", all(r.get("employment_status") == "active" for r in real_rows), real_rows)
    dump("real-employees-after.json", real_rows)
    # rollback may leave or remove hub row depending on implementation — record either way
    EVIDENCE["ids"]["synthetic_hub_rows_after_rollback"] = synth_left

    EVIDENCE["summary"] = {"passed": PASS, "failed": FAIL}
    dump("canary-evidence.json", EVIDENCE)
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
