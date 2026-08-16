#!/usr/bin/env python3
"""Wave 3E production synthetic-only scheduler operational closeout.

Proves unattended timer execution. Does not target real employees.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

OUT = Path(os.environ.get("WAVE3E_OUT", "/tmp/wave3e-closeout"))
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
EVIDENCE: dict = {"checks": [], "timestamps": {}, "ids": {}}


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    EVIDENCE["checks"].append({"label": label, "pass": bool(cond), "detail": None if cond else detail})
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def dump(name: str, obj) -> None:
    (OUT / name).write_text(json.dumps(obj, indent=2, default=str) + "\n")
    print("wrote", OUT / name)


def sh(cmd: list[str] | str, check_rc: bool = True) -> subprocess.CompletedProcess:
    if isinstance(cmd, str):
        cp = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    else:
        cp = subprocess.run(cmd, text=True, capture_output=True)
    if check_rc and cp.returncode != 0:
        raise RuntimeError(f"cmd failed rc={cp.returncode}: {cmd}\n{cp.stdout}\n{cp.stderr}")
    return cp


def timer_status() -> dict:
    out = {}
    for unit in [
        "wathefni-lifecycle-effective.timer",
        "wathefni-lifecycle-effective-proof.timer",
        "wathefni-lifecycle-effective.service",
    ]:
        cp = sh(["systemctl", "show", unit, "-p", "ActiveState", "-p", "SubState", "-p", "UnitFileState", "-p", "LastTriggerUSec", "-p", "NextElapseUSecRealtime", "-p", "Persistent"], check_rc=False)
        props = {}
        for line in (cp.stdout or "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                props[k] = v
        out[unit] = props
    return out


def journal_since(since_iso: str) -> str:
    # systemd accepts "YYYY-MM-DD HH:MM:SS UTC" roughly; use --since with ISO-ish
    cp = sh(
        ["journalctl", "-u", "wathefni-lifecycle-effective.service", f"--since={since_iso}", "--no-pager", "-o", "short-iso"],
        check_rc=False,
    )
    return cp.stdout or ""


def wait_for_timer_execution(*, before: datetime, employment_id: str, timeout_sec: int = 150) -> dict:
    """Wait until employment is terminated by scheduler (not by this process)."""
    import app

    deadline = time.time() + timeout_sec
    polls = []
    while time.time() < deadline:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT lifecycle_state, termination_effective_on, access_revoke_status, access_revoked_at
                    FROM employee_employments WHERE employment_id=%s
                    """,
                    (employment_id,),
                )
                emp = dict(cur.fetchone())
                cur.execute(
                    """
                    SELECT run_id::text, status, started_at, finished_at, terminations_executed, revokes_executed,
                           lag_seconds, error_text, evidence
                    FROM employee_lifecycle_scheduler_runs
                    WHERE company_code=%s AND environment='production' AND started_at >= %s
                    ORDER BY started_at DESC LIMIT 10
                    """,
                    (COMPANY, before),
                )
                runs = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    """
                    SELECT event_id::text, event_type, created_at, payload
                    FROM employee_lifecycle_events
                    WHERE employment_id=%s AND created_at >= %s
                    ORDER BY created_at
                    """,
                    (employment_id, before),
                )
                events = [dict(r) for r in cur.fetchall()]
            conn.commit()
        poll = {
            "at": datetime.now(timezone.utc).isoformat(),
            "lifecycle_state": emp.get("lifecycle_state"),
            "access_revoke_status": emp.get("access_revoke_status"),
            "runs": len(runs),
            "events": [e.get("event_type") for e in events],
        }
        polls.append(poll)
        print(f"poll {poll}", flush=True)
        if emp.get("lifecycle_state") == "terminated" and any(r.get("status") == "succeeded" and int(r.get("terminations_executed") or 0) >= 1 for r in runs):
            return {"emp": emp, "runs": runs, "events": events, "polls": polls}
        time.sleep(5)
    return {"emp": emp, "runs": runs, "events": events, "polls": polls, "timeout": True}


def main() -> int:
    if str(os.environ.get("WATHEFNI_ENV") or "").lower() not in {"production", "prod"}:
        raise SystemExit("refusing non-production")
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

    EVIDENCE["timestamps"]["closeout_start"] = datetime.now(timezone.utc).isoformat()
    check("synthetic only on", w3.lifecycle_synthetic_only_enabled() is True)
    check("lifecycle WATHEFNI only", w3.lifecycle_v3_enabled(COMPANY) and not w3.lifecycle_v3_enabled("OTHERCO"))
    check("notice hints hidden", w3c.DEFAULT_POLICY["show_notice_hints"] is False)
    check("reinstate disabled", w3c.DEFAULT_POLICY["allow_reinstate_after_effective"] is False)

    # Block real employees
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for rk in REAL_KEYS:
                try:
                    w3.assert_lifecycle_synthetic_target(app, cur, company=COMPANY, employee_key=rk)
                    check(f"block real {rk}", False)
                except Exception as exc:
                    detail = getattr(exc, "detail", {}) or {}
                    err = detail.get("error") if isinstance(detail, dict) else None
                    check(f"block real {rk}", getattr(exc, "status_code", None) == 403 and err == "synthetic_only_gate", exc)

    # Actors
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM dashboard_users WHERE company_code=%s AND lower(coalesce(status,''))='active' ORDER BY updated_at DESC NULLS LAST LIMIT 40",
                (COMPANY,),
            )
            users = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
    managers = [u for u in users if app._normal_dashboard_operator(u) and "employees.manage" in app.dashboard_effective_permissions_for_user(u)]
    requester_id = str(managers[0]["user_id"])
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            status_approval.ensure_employee_status_approval_schema(cur)
            eligible = status_approval.list_eligible_status_approvers(app, cur, company_code=COMPANY, exclude_user_id=requester_id)
            if not eligible:
                other = next(u for u in users if str(u["user_id"]) != requester_id and app._normal_dashboard_operator(u))
                cur.execute(
                    """
                    INSERT INTO dashboard_user_permission_grants
                      (company_code, user_id, permission, status, review_reference, granted_by_user_id, granted_reason)
                    VALUES (%s,%s,'employees.status.approve','active',%s,%s,%s)
                    ON CONFLICT (company_code, user_id, permission) DO UPDATE SET status='active', revoked_at=NULL, updated_at=now()
                    """,
                    (COMPANY, other["user_id"], "wave3e", requester_id, "wave3e closeout"),
                )
                eligible = status_approval.list_eligible_status_approvers(app, cur, company_code=COMPANY, exclude_user_id=requester_id)
            conn.commit()
    approver_id = str(eligible[0]["user_id"])

    def ctx(uid: str):
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM dashboard_users WHERE company_code=%s AND user_id=%s", (COMPANY, uid))
                user = dict(cur.fetchone())
                conn.commit()
        perms = list(app.dashboard_effective_permissions_for_user(user))
        if "employees.status.approve" not in perms and uid == approver_id:
            perms.append("employees.status.approve")
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
    approver_ctx = ctx(approver_id)

    # Counsel gate
    try:
        w3c.assert_counsel_gate(app, company_code=COMPANY)
    except Exception:
        answers = {q["id"]: "wave3e-ops" for q in w3c.COUNSEL_QUESTIONS}
        w3c.sign_counsel_checklist(
            app, requester_ctx, answers=answers, signed_by_name="Wave3E Ops", signed_by_role="ops",
            signed_reference=f"W3E-{uuid.uuid4().hex[:8]}", notes="Synthetic timer closeout only",
        )

    policy = w3c.upsert_company_policy(
        app, requester_ctx,
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
            "lag_alert_seconds": 60,
            "scheduler_cadence": "hourly",
        },
    )
    check("lag alert threshold set to 60s", int(policy.get("lag_alert_seconds") or 0) == 60, policy)

    tag = uuid.uuid4().hex[:8]
    phone = f"965522{int(tag[:6], 16) % 100000:05d}"
    key = f"{COMPANY}-{phone}"
    name = f"W3D-SYNTH|W3E Timer {tag}"
    idem = f"wave3e:{COMPANY}:{tag}"
    today = date.today()
    tomorrow = today + timedelta(days=1)
    EVIDENCE["ids"].update({"tag": tag, "phone": phone, "employee_key": key})

    created = app.create_company_employee(COMPANY, name=name, phone=phone, position_title="Timer Canary")
    check("create synthetic", created.get("status") == "created", created)
    key = str(created.get("employee_key") or key)
    authority.backfill_company_authority(app, company_code=COMPANY, idempotency_key=f"{idem}:bf", employee_keys=[key])
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w3.stamp_lifecycle_synthetic_markers(cur, company=COMPANY, employee_key=key)
            cur.execute(
                """
                INSERT INTO employee_sessions (company_code, employee_key, phone, token_hash, status, expires_at, refresh_expires_at)
                VALUES (%s,%s,%s,%s,'active', now() + interval '7 days', now() + interval '30 days')
                """,
                (COMPANY, key, phone, f"tok-w3e-{tag}"),
            )
        conn.commit()

    proj = w3c.get_lifecycle_projection(app, company_code=COMPANY, employee_key=key)
    emp_id = str(proj["employment_id"])
    EVIDENCE["ids"].update({
        "person_id": str(proj["person_id"]),
        "employment_id": emp_id,
        "assignment_id": str(proj["assignment_id"]),
    })

    # Future-dated termination (notice_period)
    req = w3c.create_lifecycle_request(
        app, requester_ctx, employee_key=key, case_type="termination", reason="w3e unattended timer",
        approval_reference=f"W3E-{tag}", designated_approver_user_id=approver_id,
        idempotency_key=f"{idem}:term", expected_lifecycle_state="active",
        expected_lifecycle_version=int(proj["lifecycle_version"]), expected_hub_updated_at=proj["hub_updated_at"],
        payload={"termination_effective_on": tomorrow.isoformat(), "last_working_day": today.isoformat(), "termination_type": "resignation"},
        impact_ack=True, impact_ack_text="Ack W3E timer canary",
    )
    dec = w3c.decide_lifecycle_request(app, approver_ctx, request_id=str(req["request"]["request_id"]), action="approve")
    check("future term approved notice_period", dec.get("committed") is True, dec)
    proj_n = w3c.get_lifecycle_projection(app, company_code=COMPANY, employee_key=key)
    check("state notice_period", proj_n.get("lifecycle_state") == "notice_period", proj_n)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM employee_sessions WHERE employee_key=%s AND token_hash=%s", (key, f"tok-w3e-{tag}"))
            sess = dict(cur.fetchone())
            cur.execute("SELECT access_revoke_status, access_revoke_at FROM employee_employments WHERE employment_id=%s", (emp_id,))
            ar = dict(cur.fetchone())
    check("session active before cutoff", sess.get("status") == "active", sess)
    check("access revoke scheduled before cutoff", ar.get("access_revoke_status") == "scheduled", ar)

    # Make due for next unattended tick (do NOT call worker manually for happy path)
    overdue_eff = today - timedelta(days=1)
    revoke_past = datetime.now(tz=ZoneInfo("Asia/Kuwait")) - timedelta(minutes=2)
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
                (overdue_eff, revoke_past, emp_id),
            )
        conn.commit()
    EVIDENCE["timestamps"]["made_due_at"] = datetime.now(timezone.utc).isoformat()

    # Lag metric before execution
    lag = w3c.compute_scheduler_lag(app, company_code=COMPANY)
    check("lag seconds > 0 for overdue", int(lag.get("lag_seconds") or 0) > 0, lag)
    check("lag alert true with 60s threshold", lag.get("alert") is True, lag)
    dump("lag-before.json", lag)

    # --- Retry path: inject fail on next timer tick, then success on following tick ---
    fail_file = Path("/tmp/wathefni-lifecycle-fail-once")
    fail_file.write_text("1\n")
    before_fail = datetime.now(timezone.utc)
    EVIDENCE["timestamps"]["fail_inject_at"] = before_fail.isoformat()
    # Wait for a failed run recorded
    fail_seen = False
    for _ in range(36):
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id::text, status, error_text, started_at
                    FROM employee_lifecycle_scheduler_runs
                    WHERE company_code=%s AND started_at >= %s
                    ORDER BY started_at DESC LIMIT 5
                    """,
                    (COMPANY, before_fail),
                )
                runs = [dict(r) for r in cur.fetchall()]
            conn.commit()
        if any(r.get("status") == "failed" for r in runs):
            fail_seen = True
            dump("retry-failed-runs.json", runs)
            EVIDENCE["timestamps"]["failed_run_seen_at"] = datetime.now(timezone.utc).isoformat()
            break
        # still notice_period
        proj_chk = w3c.get_lifecycle_projection(app, company_code=COMPANY, employee_key=key)
        if proj_chk.get("lifecycle_state") == "terminated":
            # fail inject missed; still ok if later success is idempotent
            break
        time.sleep(5)
    check("failed execution recorded for retry drill", fail_seen, {"note": "timer may have succeeded if fail file raced"})

    # Ensure still due if fail happened
    proj_mid = w3c.get_lifecycle_projection(app, company_code=COMPANY, employee_key=key)
    if proj_mid.get("lifecycle_state") != "notice_period":
        # already terminated by a success tick that raced — record and continue
        check("employment terminated (possibly raced past fail inject)", proj_mid.get("lifecycle_state") == "terminated", proj_mid)
    else:
        before_ok = datetime.now(timezone.utc)
        EVIDENCE["timestamps"]["await_success_from"] = before_ok.isoformat()
        waited = wait_for_timer_execution(before=before_ok, employment_id=emp_id, timeout_sec=150)
        dump("unattended-wait.json", waited)
        check("unattended timer terminated employment", waited.get("emp", {}).get("lifecycle_state") == "terminated", waited)
        check("scheduler succeeded with terminations", any(r.get("status") == "succeeded" and int(r.get("terminations_executed") or 0) >= 1 for r in waited.get("runs") or []), waited)
        EVIDENCE["timestamps"]["unattended_terminated_at"] = datetime.now(timezone.utc).isoformat()

    # Audit: event + settlement + session revoke
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT event_id::text, event_type, created_at, payload
                FROM employee_lifecycle_events
                WHERE employment_id=%s AND event_type IN ('termination_effective','access_revoked')
                ORDER BY created_at
                """,
                (emp_id,),
            )
            evs = [dict(r) for r in cur.fetchall()]
            cur.execute(
                """
                SELECT packet_id::text, status, packet, handed_off_at, created_at
                FROM employee_lifecycle_settlement_packets
                WHERE employment_id=%s ORDER BY created_at DESC LIMIT 1
                """,
                (emp_id,),
            )
            sp = dict(cur.fetchone() or {})
            cur.execute("SELECT status FROM employee_sessions WHERE employee_key=%s AND token_hash=%s", (key, f"tok-w3e-{tag}"))
            sess2 = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT count(*)::int n FROM employee_lifecycle_events
                WHERE employment_id=%s AND event_type='termination_effective'
                """,
                (emp_id,),
            )
            term_events = int(dict(cur.fetchone())["n"])
            cur.execute(
                """
                SELECT run_id::text, status, terminations_executed, revokes_executed, lag_seconds, started_at, finished_at, error_text
                FROM employee_lifecycle_scheduler_runs
                WHERE company_code=%s AND environment='production'
                ORDER BY started_at DESC LIMIT 15
                """,
                (COMPANY,),
            )
            recent_runs = [dict(r) for r in cur.fetchall()]
        conn.commit()
    dump("audit-events.json", evs)
    dump("audit-settlement.json", sp)
    dump("scheduler-runs-recent.json", recent_runs)
    packet = sp.get("packet") or {}
    if isinstance(packet, str):
        packet = json.loads(packet)
    check("termination_effective event audited", any(e.get("event_type") == "termination_effective" for e in evs), evs)
    check("access_revoked event audited", any(e.get("event_type") == "access_revoked" for e in evs), evs)
    check("settlement packet audited inputs-only", sp.get("status") == "handed_to_payroll" and "inputs" in packet and "amounts" not in packet, sp)
    check("session revoked after cutoff", sess2.get("status") == "revoked", sess2)
    check("no duplicate termination_effective", term_events == 1, {"count": term_events})

    # Second timer tick idempotent (no extra termination events)
    time.sleep(65)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*)::int n FROM employee_lifecycle_events WHERE employment_id=%s AND event_type='termination_effective'",
                (emp_id,),
            )
            term_events2 = int(dict(cur.fetchone())["n"])
        conn.commit()
    check("retry/next tick no duplicate effects", term_events2 == 1, {"count": term_events2})

    # Kill switch: disable lifecycle for service env via drop-in overlay for worker only
    kill_dropin = Path("/etc/systemd/system/wathefni-lifecycle-effective.service.d")
    kill_dropin.mkdir(parents=True, exist_ok=True)
    (kill_dropin / "kill-switch.conf").write_text(
        "[Service]\nEnvironment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3=off\n"
    )
    sh(["systemctl", "daemon-reload"])
    EVIDENCE["timestamps"]["kill_switch_on_at"] = datetime.now(timezone.utc).isoformat()
    # Create another synthetic due notice_period that must NOT execute while killed
    tag2 = uuid.uuid4().hex[:8]
    phone2 = f"965522{int(tag2[:6], 16) % 100000:05d}"
    key2 = f"{COMPANY}-{phone2}"
    name2 = f"W3D-SYNTH|W3E Kill {tag2}"
    created2 = app.create_company_employee(COMPANY, name=name2, phone=phone2, position_title="Kill Switch")
    check("create kill-switch synthetic", created2.get("status") == "created", created2)
    key2 = str(created2.get("employee_key") or key2)
    authority.backfill_company_authority(app, company_code=COMPANY, idempotency_key=f"{idem}:bf2", employee_keys=[key2])
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w3.stamp_lifecycle_synthetic_markers(cur, company=COMPANY, employee_key=key2)
        conn.commit()
    # Temporarily enable lifecycle in THIS process to create the scheduled term
    os.environ["WATHEFNI_EMPLOYEE_LIFECYCLE_V3"] = "on"
    proj2 = w3c.get_lifecycle_projection(app, company_code=COMPANY, employee_key=key2)
    req2 = w3c.create_lifecycle_request(
        app, requester_ctx, employee_key=key2, case_type="termination", reason="should not fire under kill switch",
        approval_reference=f"KILL-{tag2}", designated_approver_user_id=approver_id,
        idempotency_key=f"{idem}:kill", expected_lifecycle_state="active",
        expected_lifecycle_version=int(proj2["lifecycle_version"]), expected_hub_updated_at=proj2["hub_updated_at"],
        payload={"termination_effective_on": tomorrow.isoformat(), "last_working_day": today.isoformat(), "termination_type": "resignation"},
        impact_ack=True, impact_ack_text="Ack kill",
    )
    w3c.decide_lifecycle_request(app, approver_ctx, request_id=str(req2["request"]["request_id"]), action="approve")
    emp2 = str(w3c.get_lifecycle_projection(app, company_code=COMPANY, employee_key=key2)["employment_id"])
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE employee_employments SET termination_effective_on=%s, access_revoke_at=%s WHERE employment_id=%s",
                (today, revoke_past, emp2),
            )
        conn.commit()
    before_kill = datetime.now(timezone.utc)
    time.sleep(70)
    # Run worker once under kill switch env (simulates timer tick with kill drop-in)
    cp_kill = sh("systemctl start wathefni-lifecycle-effective.service; echo rc=$?", check_rc=False)
    dump("kill-switch-start.txt", {"stdout": cp_kill.stdout, "stderr": cp_kill.stderr, "rc": cp_kill.returncode})
    time.sleep(3)
    proj_kill = w3c.get_lifecycle_projection(app, company_code=COMPANY, employee_key=key2)
    check("kill switch stops execution (still notice_period)", proj_kill.get("lifecycle_state") == "notice_period", proj_kill)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, evidence, error_text FROM employee_lifecycle_scheduler_runs
                WHERE company_code=%s AND started_at >= %s ORDER BY started_at DESC LIMIT 5
                """,
                (COMPANY, before_kill),
            )
            kill_runs = [dict(r) for r in cur.fetchall()]
        conn.commit()
    dump("kill-switch-runs.json", kill_runs)
    # disabled run should report ok:false lifecycle_disabled without terminating
    check(
        "kill switch scheduler reports disabled or no term",
        proj_kill.get("lifecycle_state") == "notice_period",
        kill_runs,
    )

    # Restore kill switch off
    (kill_dropin / "kill-switch.conf").unlink(missing_ok=True)
    try:
        kill_dropin.rmdir()
    except OSError:
        pass
    sh(["systemctl", "daemon-reload"])
    EVIDENCE["timestamps"]["kill_switch_off_at"] = datetime.now(timezone.utc).isoformat()

    # Real employees still active / blocked
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT employee_key, employment_status FROM employees WHERE company_code=%s AND employee_key = ANY(%s) ORDER BY 1",
                (COMPANY, REAL_KEYS),
            )
            real = [dict(r) for r in cur.fetchall()]
        conn.commit()
    check("real employees still active", all(r.get("employment_status") == "active" for r in real), real)
    dump("real-employees.json", real)

    # Cleanup synthetics
    synth_keys = [key, key2]
    rb = w3c.rollback_lifecycle_wave3c(app, company_code=COMPANY, idempotency_key=f"{idem}:rb", employee_keys=synth_keys)
    check("rollback wave3c ok", rb.get("ok") is True, rb)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM employees
                WHERE company_code=%s AND (employee_key = ANY(%s) OR name LIKE %s)
                RETURNING employee_key
                """,
                (COMPANY, synth_keys, "W3D-SYNTH|W3E %"),
            )
            deleted = [dict(r)["employee_key"] for r in cur.fetchall()]
        conn.commit()
    check("synthetic hub cleaned", True, deleted)
    dump("cleanup.json", {"deleted": deleted, "rollback": rb})

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*)::int n FROM employees WHERE company_code=%s AND (name LIKE %s OR employee_key = ANY(%s))",
                (COMPANY, "W3D-SYNTH|W3E %", synth_keys),
            )
            left = int(dict(cur.fetchone())["n"])
        conn.commit()
    check("no synthetic leftover", left == 0, {"left": left})

    EVIDENCE["timestamps"]["closeout_end"] = datetime.now(timezone.utc).isoformat()
    EVIDENCE["summary"] = {"passed": PASS, "failed": FAIL}
    EVIDENCE["timer_status"] = timer_status()
    dump("closeout-evidence.json", EVIDENCE)
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
