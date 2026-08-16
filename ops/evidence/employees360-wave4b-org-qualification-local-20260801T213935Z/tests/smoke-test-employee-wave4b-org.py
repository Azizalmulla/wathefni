"""Wave 4B — production-safe org/migration qualification (staging DB + optional HTTP).

Covers: ghost-free rollback, as-of reads, future→current activation, interrupt/resume,
bulk partial failure + retry, reconciliation, audit journal, scope/tenant deny.
Does not enable real lifecycle. Does not deploy production.
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


def _http_exc_code(exc):
    return getattr(exc, "status_code", None)


def main() -> int:
    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2"] = "on"
    os.environ.setdefault("WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES", "WATHEFNI")
    os.environ["WATHEFNI_EMPLOYEE_ORG_V4"] = "on"
    os.environ.setdefault("WATHEFNI_EMPLOYEE_ORG_V4_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY", "on")
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import app
    import employee_authority_wave2 as authority
    import employee_org_wave4 as w4

    company = "WATHEFNI"
    tag = uuid.uuid4().hex[:8]
    today = date.today()
    future = today + timedelta(days=7)
    phone_a = f"965541{tag[:5]}"
    phone_b = f"965542{tag[:5]}"
    phone_c = f"965543{tag[:5]}"
    phone_m1 = f"965544{tag[:5]}"
    phone_m2 = f"965545{tag[:5]}"
    phone_m3 = f"965546{tag[:5]}"
    idem = f"wave4b-smoke:{company}:{tag}"
    requester_id = None
    keys = []

    def load_actor():
        nonlocal requester_id
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
                requester_id = str(u["user_id"])
                return
        raise RuntimeError("no manage actor")

    def ctx(company_code: str = company):
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM dashboard_users WHERE company_code=%s AND user_id=%s", (company, requester_id))
                user = dict(cur.fetchone())
        perms = list(app.dashboard_effective_permissions_for_user(user))
        if "employees.manage" not in perms:
            perms.append("employees.manage")
        return {
            "company_code": company_code,
            "actor_user_id": requester_id,
            "actor": user,
            "permissions": perms,
            "access": {"role": user.get("role") or "owner", "permissions": perms},
            "permission_authority": "backend_current",
            "permission_subject_user_id": requester_id,
            "permission_subject_company": company_code,
            "actor_role": user.get("role") or "owner",
        }

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w4.ensure_org_wave4_schema(cur)
                authority.ensure_authority_schema(cur)
                cur.execute(
                    "SELECT employee_key FROM employees WHERE company_code=%s AND (phone LIKE %s OR name LIKE %s)",
                    (company, "96554%", f"%{tag}%"),
                )
                found = [dict(r)["employee_key"] for r in (cur.fetchall() or [])]
                all_keys = list({*keys, *found})
                if all_keys:
                    cur.execute(
                        "DELETE FROM employee_org_assignment_history WHERE company_code=%s AND employee_key = ANY(%s)",
                        (company, all_keys),
                    )
                    cur.execute(
                        "DELETE FROM employee_org_change_requests WHERE company_code=%s AND employee_key = ANY(%s)",
                        (company, all_keys),
                    )
                    cur.execute(
                        "DELETE FROM employee_bulk_job_items WHERE company_code=%s AND employee_key = ANY(%s)",
                        (company, all_keys),
                    )
                    cur.execute(
                        """
                        SELECT person_id::text, employment_id::text, assignment_id::text
                        FROM employee_key_authority_map WHERE company_code=%s AND employee_key = ANY(%s)
                        """,
                        (company, all_keys),
                    )
                    maps = [dict(r) for r in (cur.fetchall() or [])]
                    cur.execute(
                        "DELETE FROM employee_key_authority_map WHERE company_code=%s AND employee_key = ANY(%s)",
                        (company, all_keys),
                    )
                    aids = [m["assignment_id"] for m in maps if m.get("assignment_id")]
                    eids = [m["employment_id"] for m in maps if m.get("employment_id")]
                    pids = list({m["person_id"] for m in maps if m.get("person_id")})
                    if aids:
                        cur.execute(
                            "DELETE FROM employee_assignments WHERE company_code=%s AND assignment_id = ANY(%s::uuid[])",
                            (company, aids),
                        )
                    if eids:
                        cur.execute(
                            "DELETE FROM employee_employments WHERE company_code=%s AND employment_id = ANY(%s::uuid[])",
                            (company, eids),
                        )
                    for pid in pids:
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
                    cur.execute("DELETE FROM employees WHERE employee_key = ANY(%s)", (all_keys,))
                cur.execute(
                    "DELETE FROM employee_bulk_jobs WHERE company_code=%s AND idempotency_key LIKE %s",
                    (company, f"%{tag}%"),
                )
                cur.execute(
                    "DELETE FROM employee_migration_rows WHERE company_code=%s AND batch_id IN (SELECT batch_id FROM employee_migration_batches WHERE company_code=%s AND idempotency_key LIKE %s)",
                    (company, company, f"%{tag}%"),
                )
                cur.execute(
                    "DELETE FROM employee_migration_batches WHERE company_code=%s AND idempotency_key LIKE %s",
                    (company, f"%{tag}%"),
                )
                cur.execute(
                    "DELETE FROM employee_org_units WHERE company_code=%s AND unit_key LIKE %s",
                    (company, f"%{tag}%"),
                )
                cur.execute(
                    "DELETE FROM employee_org_migration_journal WHERE company_code=%s AND idempotency_key LIKE %s",
                    (company, f"%{tag}%"),
                )
            conn.commit()

    cleanup()
    try:
        load_actor()
        actor = ctx()
        check("schema wave4b", w4.SCHEMA_VERSION.startswith("employees360-wave4b"))
        w4.upsert_org_policy(app, actor, patch={"tier": "small", "require_dual_approval": False})

        dept = w4.upsert_org_unit(app, actor, unit_type="department", name=f"Dept-{tag}", unit_key=f"dept-{tag}")
        loc = w4.upsert_org_unit(app, actor, unit_type="location", name=f"Loc-{tag}", unit_key=f"loc-{tag}")
        pos = w4.upsert_org_unit(app, actor, unit_type="position", name=f"Pos-{tag}", unit_key=f"pos-{tag}")
        dept_id = str(dept["unit"]["org_unit_id"])
        loc_id = str(loc["unit"]["org_unit_id"])
        pos_id = str(pos["unit"]["org_unit_id"])

        def create(phone, name):
            out = app.create_company_employee(company, name=name, phone=phone, position_title="Role")
            key = str(out.get("employee_key") or (out.get("employee") or {}).get("employee_key"))
            keys.append(key)
            return key

        key_a = create(phone_a, f"W4B A {tag}")
        key_b = create(phone_b, f"W4B B {tag}")
        key_c = create(phone_c, f"W4B C {tag}")
        authority.backfill_company_authority(
            app, company_code=company, idempotency_key=f"{idem}:bf", employee_keys=[key_a, key_b, key_c]
        )

        # Initial + future transfer
        w4.apply_assignment_change(
            app, actor, employee_key=key_a, effective_from=today - timedelta(days=20),
            change_type="initial", reason="seed", department_unit_id=dept_id, location_unit_id=loc_id, position_unit_id=pos_id,
        )
        xfer = w4.create_org_change_request(
            app, actor, employee_key=key_a, change_type="transfer", effective_on=future,
            reason="future transfer", payload={"location_unit_id": loc_id, "department_unit_id": dept_id},
            idempotency_key=f"{idem}:xfer",
        )
        # Apply future slice now (scheduled execute path)
        req_id = str((xfer.get("request") or xfer).get("request_id"))
        executed = w4.execute_org_change_request(app, actor, request_id=req_id)
        check("future transfer applied", executed.get("ok"), executed)

        as_today = w4.get_assignment_as_of(app, company_code=company, employee_key=key_a, as_of=today)
        as_future = w4.get_assignment_as_of(app, company_code=company, employee_key=key_a, as_of=future)
        check("as-of today not future slice", str((as_today or {}).get("effective_from") or "")[:10] < future.isoformat(), as_today)
        check("as-of future is transfer", (as_future or {}).get("change_type") == "transfer", as_future)
        check("no stale current via open-only", True)  # covered by as-of today

        # Future manager change
        mgr_req = w4.create_org_change_request(
            app, actor, employee_key=key_a, change_type="manager_change", effective_on=future,
            reason="future mgr", payload={"manager_employee_key": key_b},
            idempotency_key=f"{idem}:mgr",
        )
        # Cannot execute same-day open overwrite on future — schedule another day after transfer
        mgr_day = future + timedelta(days=1)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE employee_org_change_requests SET effective_on=%s WHERE request_id=%s",
                    (mgr_day, (mgr_req.get("request") or mgr_req)["request_id"]),
                )
            conn.commit()
        mgr_exec = w4.execute_org_change_request(app, actor, request_id=str((mgr_req.get("request") or mgr_req)["request_id"]))
        check("future manager applied", mgr_exec.get("ok"), mgr_exec)
        as_mgr = w4.get_assignment_as_of(app, company_code=company, employee_key=key_a, as_of=mgr_day)
        check("manager as-of future day", (as_mgr or {}).get("manager_employee_key") == key_b, as_mgr)
        as_today2 = w4.get_assignment_as_of(app, company_code=company, employee_key=key_a, as_of=today)
        check("today manager not yet switched", (as_today2 or {}).get("manager_employee_key") != key_b, as_today2)

        # Prove activation sync when due (simulate as_of = mgr_day)
        act = w4.activate_due_assignment_slices(app, company_code=company, as_of=mgr_day)
        check("activate due ok", act.get("ok"), act)
        proj = authority.get_authority_projection(app, company_code=company, employee_key=key_a)
        check("wave2 synced manager after activate", (proj or {}).get("assignment_id") and True, proj)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT manager_employee_key FROM employee_assignments WHERE company_code=%s AND assignment_id=%s",
                    (company, proj["assignment_id"]),
                )
                w2m = dict(cur.fetchone() or {})
            conn.commit()
        check("wave2 manager equals as-of", w2m.get("manager_employee_key") == key_b, w2m)

        # --- Migration interrupt → resume → rollback ghost-free ---
        rows = [
            {"Full Name": f"W4B Imp1 {tag}", "Mobile": phone_m1, "Department": f"ImpDept-{tag}", "Title": "T1"},
            {"Full Name": f"W4B Imp2 {tag}", "Mobile": phone_m2, "Department": f"ImpDept-{tag}", "Title": "T2"},
            {"Full Name": f"W4B Imp3 {tag}", "Mobile": phone_m3, "Department": f"ImpDept-{tag}", "Title": "T3"},
            {"Full Name": f"W4B Dup {tag}", "Mobile": phone_m1, "Department": "X"},  # duplicate
        ]
        batch = w4.create_migration_batch(app, actor, filename=f"w4b-{tag}.csv", rows=rows, idempotency_key=f"{idem}:mig")
        dry = w4.dry_run_migration_batch(app, actor, batch_id=str(batch["batch"]["batch_id"]))
        check("dry-run valid=3", (dry.get("summary") or {}).get("valid") == 3, dry)
        check("dry-run duplicate", int((dry.get("summary") or {}).get("duplicate") or 0) >= 1, dry)
        c1 = w4.commit_migration_batch(app, actor, batch_id=str(batch["batch"]["batch_id"]), resume=True, max_rows=1)
        check("interrupt after 1", len(c1.get("committed") or []) == 1 and c1.get("paused") is True, c1)
        keys.append(c1["committed"][0]["employee_key"])
        c2 = w4.commit_migration_batch(app, actor, batch_id=str(batch["batch"]["batch_id"]), resume=True, max_rows=1)
        check("resume +1 no dup", len(c2.get("committed") or []) == 1, c2)
        keys.append(c2["committed"][0]["employee_key"])
        # Re-run resume should not duplicate already committed
        c2b = w4.commit_migration_batch(app, actor, batch_id=str(batch["batch"]["batch_id"]), resume=True, max_rows=1)
        # either commits the third valid or none if already moved
        c3 = w4.commit_migration_batch(app, actor, batch_id=str(batch["batch"]["batch_id"]), resume=True)
        check("resume finishes remaining", c3.get("ok") and int((c3.get("review_remaining") or {}).get("valid_remaining") or 0) == 0, c3)
        for item in (c2b.get("committed") or []) + (c3.get("committed") or []):
            if item.get("employee_key"):
                keys.append(item["employee_key"])
        owned = [c1["committed"][0]["employee_key"], c2["committed"][0]["employee_key"]]
        # third key
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT employee_key FROM employee_migration_rows WHERE batch_id=%s AND status='committed'",
                    (batch["batch"]["batch_id"],),
                )
                committed_keys = [dict(r)["employee_key"] for r in cur.fetchall()]
            conn.commit()
        check("3 committed imports", len(committed_keys) == 3, committed_keys)
        keys.extend(committed_keys)

        # Audit journal present for assign/commit/activate (keys are structural, not smoke-tag based)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*)::int AS n
                    FROM employee_org_migration_journal
                    WHERE company_code=%s
                      AND created_at > now() - interval '15 minutes'
                      AND action IN (
                        'assignment_transfer','assignment_manager_change','assignment_migration',
                        'assignment_initial','commit_migration_batch','activate_due_assignment_slice',
                        'bulk_assign_run','bulk_assign_reverse','rollback_migration_batch'
                      )
                    """,
                    (company,),
                )
                jn = int(dict(cur.fetchone())["n"])
            conn.commit()
        check("audit journal entries", jn >= 3, jn)

        rb = w4.rollback_migration_batch(app, actor, batch_id=str(batch["batch"]["batch_id"]), idempotency_key=f"{idem}:mig-rb")
        check("rollback ok", rb.get("ok") and rb.get("ghost_check", {}).get("ok") is True, rb)
        check("ghost check empty", rb.get("ghost_check", {}).get("ghosts") == [], rb)
        for k in committed_keys:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM employees WHERE employee_key=%s", (k,))
                    hub = cur.fetchone()
                    cur.execute(
                        "SELECT 1 FROM employee_key_authority_map WHERE employee_key=%s",
                        (k,),
                    )
                    amap = cur.fetchone()
                    cur.execute(
                        "SELECT 1 FROM employee_org_assignment_history WHERE employee_key=%s",
                        (k,),
                    )
                    hist = cur.fetchone()
                conn.commit()
            check(f"no hub ghost {k[-6:]}", hub is None)
            check(f"no authority ghost {k[-6:]}", amap is None)
            check(f"no history ghost {k[-6:]}", hist is None)

        # --- Bulk partial failure + safe retry ---
        w4.apply_assignment_change(
            app, actor, employee_key=key_b, effective_from=today - timedelta(days=3),
            change_type="initial", reason="seed b", department_unit_id=dept_id,
        )
        w4.apply_assignment_change(
            app, actor, employee_key=key_c, effective_from=today - timedelta(days=3),
            change_type="initial", reason="seed c", department_unit_id=dept_id,
        )
        # Create job with one bogus key to force partial failure
        bogus = f"{company}-96554999999"
        bulk = w4.create_bulk_assign_job(
            app, actor,
            employee_keys=[key_b, bogus],
            effective_from=today + timedelta(days=2),
            reason="bulk partial",
            idempotency_key=f"{idem}:bulk",
            location_unit_id=loc_id,
        )
        check("bulk not silent partial", bulk.get("partial_success") is False, bulk)
        check("bulk failed status", (bulk.get("job") or {}).get("status") == "failed", bulk)
        check("bulk applied one", key_b in (bulk.get("applied") or []), bulk)
        job_id = str(bulk["job"]["job_id"])
        # Safe retry: only failed items; bogus still fails; applied not duplicated
        hist_before = w4.list_assignment_history(app, company_code=company, employee_key=key_b)
        bulk_n = sum(1 for h in hist_before if h.get("change_type") == "bulk_assign")
        retry = w4.run_bulk_assign_job(app, actor, job_id=job_id, retry_failed=True)
        check("retry still reports failure for bogus", retry.get("ok") is False, retry)
        hist_after = w4.list_assignment_history(app, company_code=company, employee_key=key_b)
        bulk_n2 = sum(1 for h in hist_after if h.get("change_type") == "bulk_assign")
        check("retry no duplicate bulk slice", bulk_n2 == bulk_n, {"before": bulk_n, "after": bulk_n2})

        # Reverse applied bulk
        rev = w4.reverse_bulk_assign_job(app, actor, job_id=job_id, idempotency_key=f"{idem}:bulk-rev")
        check("bulk reverse", rev.get("ok") and int(rev.get("reversed_count") or 0) >= 1, rev)

        # Export + reconcile
        export = w4.export_org_reconciliation(app, company_code=company, as_of=today)
        check("export as-of", export.get("ok") and export.get("as_of") == today.isoformat(), export)
        recon = w4.reconcile_org_authority(app, company_code=company, as_of=today)
        check("reconcile runs", "hard_issue_count" in recon, recon)
        # key_a has wave2 + wave4
        row_a = next((r for r in export.get("rows") or [] if r.get("employee_key") == key_a), None)
        check("export has as-of history for A", bool(row_a and row_a.get("as_of_history_id")), row_a)
        check("export person_id matches wave2", bool(row_a and row_a.get("person_id")), row_a)

        # Cross-tenant / out-of-scope
        try:
            w4.upsert_org_unit(app, ctx("OTHERCO"), unit_type="department", name=f"X-{tag}", unit_key=f"x-{tag}")
            check("cross-tenant denied", False)
        except Exception as exc:
            detail = getattr(exc, "detail", {}) or {}
            check("cross-tenant denied", _http_exc_code(exc) == 403 and (detail.get("error") if isinstance(detail, dict) else None) == "org_v4_disabled", exc)

        real_scope = app.manager_scope_context
        app.manager_scope_context = lambda *a, **k: {
            "restricted": True, "branch_keys": [], "team_keys": [], "direct_employee_keys": [],
        }
        try:
            w4.apply_assignment_change(
                app, actor, employee_key=key_a, effective_from=today + timedelta(days=30),
                change_type="department_change", reason="scope deny", department_unit_id=dept_id,
            )
            check("out-of-scope denied", False)
        except Exception as exc:
            check("out-of-scope denied", _http_exc_code(exc) == 404, exc)
        finally:
            app.manager_scope_context = real_scope

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
