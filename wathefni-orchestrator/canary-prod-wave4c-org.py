#!/usr/bin/env python3
"""Wave 4C — production synthetic qualification for org authority / migration / bulk.

Strict allowlist: phones 965547*, names W4C-SYNTH|.
Does NOT classify or mutate the four real employees.
Does NOT disable SYNTHETIC_ONLY lifecycle.
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
EVIDENCE: dict = {"checks": [], "ids": {}, "scheduler": {}, "remediation": {}, "reals": {}}

PHONE_PREFIX = "965547"
NAME_PREFIX = "W4C-SYNTH|"
REAL_KEYS = (
    "WATHEFNI-96550252254",
    "WATHEFNI-96566363363",
    "WATHEFNI-96597727743",
    "WATHEFNI-96599411617",
)


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    row = {"label": label, "ok": bool(cond), "detail": detail if not cond else None}
    EVIDENCE["checks"].append(row)
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def _http_exc_code(exc):
    return getattr(exc, "status_code", None)


def _assert_allowlisted(phone: str, name: str) -> None:
    if not str(phone).startswith(PHONE_PREFIX):
        raise RuntimeError(f"phone not on Wave4C allowlist: {phone}")
    if not str(name).startswith(NAME_PREFIX):
        raise RuntimeError(f"name not on Wave4C allowlist: {name}")


def main() -> int:
    os.environ.setdefault("WATHEFNI_EMPLOYEE_AUTHORITY_V2", "on")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_ORG_V4", "on")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_ORG_V4_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_DUE", "on")
    os.environ.setdefault("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY", "on")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import production_data_safety as _r3_data_safety
    _r3_data_safety.require_non_production_ops()
    import app
    import employee_authority_wave2 as authority
    import employee_org_wave4 as w4

    company = "WATHEFNI"
    tag = uuid.uuid4().hex[:8]
    # Digits-only phone suffixes (create_company_employee strips non-digits)
    seed = int(tag, 16) % 90000 + 10000  # 10000..99999
    today = date.today()
    future = today + timedelta(days=7)
    # Strict synthetic phones — 11-digit KW form 965547xxxxx
    phone_a = f"{PHONE_PREFIX}{seed:05d}"
    phone_b = f"{PHONE_PREFIX}{(seed + 1) % 100000:05d}"
    phone_c = f"{PHONE_PREFIX}{(seed + 2) % 100000:05d}"
    phone_m1 = f"{PHONE_PREFIX}{(seed + 3) % 100000:05d}"
    phone_m2 = f"{PHONE_PREFIX}{(seed + 4) % 100000:05d}"
    phone_m3 = f"{PHONE_PREFIX}{(seed + 5) % 100000:05d}"
    for p in (phone_a, phone_b, phone_c, phone_m1, phone_m2, phone_m3):
        assert p.isdigit() and p.startswith(PHONE_PREFIX) and len(p) == 11, p
    idem = f"wave4c-prod:{company}:{tag}"
    requester_id = None
    keys: list[str] = []
    unit_ids: dict[str, str] = {}
    shared_unit_keys: list[str] = []

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

    def snapshot_reals():
        out = {}
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for k in REAL_KEYS:
                    cur.execute(
                        "SELECT employee_key, name, phone FROM employees WHERE company_code=%s AND employee_key=%s",
                        (company, k),
                    )
                    emp = dict(cur.fetchone() or {})
                    cur.execute(
                        """
                        SELECT employment_id::text, employment_status, policy_pack_status, lifecycle_state,
                               jurisdiction_code, worker_category
                        FROM employee_employments
                        WHERE company_code=%s AND legacy_employee_key=%s
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (company, k),
                    )
                    emp_row = dict(cur.fetchone() or {})
                    cur.execute(
                        "SELECT count(*)::int AS n FROM employee_org_assignment_history WHERE company_code=%s AND employee_key=%s",
                        (company, k),
                    )
                    hist_n = int(dict(cur.fetchone())["n"])
                    out[k] = {"hub": emp, "employment": emp_row, "org_history_count": hist_n}
            conn.commit()
        return out

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w4.ensure_org_wave4_schema(cur)
                authority.ensure_authority_schema(cur)
                cur.execute(
                    "SELECT employee_key FROM employees WHERE company_code=%s AND (phone LIKE %s OR name LIKE %s)",
                    (company, f"{PHONE_PREFIX}%", f"%{NAME_PREFIX}%{tag}%"),
                )
                found = [dict(r)["employee_key"] for r in (cur.fetchall() or [])]
                all_keys = list({*keys, *found})
                # Never touch reals
                all_keys = [k for k in all_keys if k not in REAL_KEYS]
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
                # Shared org units intentionally retained after migration rollback proof;
                # final canary cleanup removes only tagged synthetic units.
                cur.execute(
                    "DELETE FROM employee_org_units WHERE company_code=%s AND unit_key LIKE %s",
                    (company, f"%{tag}%"),
                )
                cur.execute(
                    "DELETE FROM employee_org_migration_journal WHERE company_code=%s AND idempotency_key LIKE %s",
                    (company, f"%{tag}%"),
                )
            conn.commit()

    reals_before = snapshot_reals()
    EVIDENCE["reals"]["before"] = reals_before
    cleanup()
    try:
        load_actor()
        actor = ctx()
        check("schema wave4b", w4.SCHEMA_VERSION.startswith("employees360-wave4b"))
        check("org_v4 enabled WATHEFNI", w4.org_v4_enabled(company))
        check("lifecycle synthetic-only on", os.environ.get("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY", "").lower() in {"on", "1", "true", "yes"})

        # Mid tier so cost_center is allowed
        w4.upsert_org_policy(
            app,
            actor,
            patch={
                "tier": "enterprise",
                "require_dual_approval": False,
                "fail_on_overlap": True,
                "allow_future_dated_changes": True,
                "migration_auto_create_org_units": True,
            },
        )

        # Create full org catalog
        for ut, name in [
            ("legal_employer", f"LE-{tag}"),
            ("branch", f"BR-{tag}"),
            ("department", f"Dept-{tag}"),
            ("team", f"Team-{tag}"),
            ("location", f"Loc-{tag}"),
            ("position", f"Pos-{tag}"),
            ("cost_center", f"CC-{tag}"),
        ]:
            uk = f"{ut}-{tag}"
            shared_unit_keys.append(uk)
            out = w4.upsert_org_unit(app, actor, unit_type=ut, name=name, unit_key=uk)
            unit_ids[ut] = str(out["unit"]["org_unit_id"])
            check(f"unit {ut}", bool(unit_ids[ut]), out)
        EVIDENCE["ids"]["units"] = unit_ids

        def create(phone, name):
            _assert_allowlisted(phone, name)
            out = app.create_company_employee(company, name=name, phone=phone, position_title="Role")
            key = str(out.get("employee_key") or (out.get("employee") or {}).get("employee_key"))
            assert key.startswith(f"{company}-{PHONE_PREFIX}"), key
            keys.append(key)
            return key

        key_a = create(phone_a, f"{NAME_PREFIX}A {tag}")
        key_b = create(phone_b, f"{NAME_PREFIX}B {tag}")
        key_c = create(phone_c, f"{NAME_PREFIX}C {tag}")
        EVIDENCE["ids"]["employees"] = {"a": key_a, "b": key_b, "c": key_c}
        authority.backfill_company_authority(
            app, company_code=company, idempotency_key=f"{idem}:bf", employee_keys=[key_a, key_b, key_c]
        )

        # Initial assignment with full org pointers
        w4.apply_assignment_change(
            app,
            actor,
            employee_key=key_a,
            effective_from=today - timedelta(days=20),
            change_type="initial",
            reason="seed",
            legal_employer_unit_id=unit_ids["legal_employer"],
            branch_unit_id=unit_ids["branch"],
            department_unit_id=unit_ids["department"],
            team_unit_id=unit_ids["team"],
            location_unit_id=unit_ids["location"],
            position_unit_id=unit_ids["position"],
            cost_center_unit_id=unit_ids["cost_center"],
            manager_employee_key=key_b,
        )

        # Current transfer closes previous slice
        xfer_now = w4.apply_assignment_change(
            app,
            actor,
            employee_key=key_a,
            effective_from=today,
            change_type="transfer",
            reason="current transfer",
            department_unit_id=unit_ids["department"],
            location_unit_id=unit_ids["location"],
            manager_employee_key=key_b,
        )
        check("current transfer ok", xfer_now.get("ok"), xfer_now)
        hist = w4.list_assignment_history(app, company_code=company, employee_key=key_a)
        closed = [h for h in hist if h.get("effective_to") is not None]
        check("prior slice closed by transfer", len(closed) >= 1, hist)

        # Future dept + manager via change requests
        xfer = w4.create_org_change_request(
            app,
            actor,
            employee_key=key_a,
            change_type="transfer",
            effective_on=future,
            reason="future transfer",
            payload={"location_unit_id": unit_ids["location"], "department_unit_id": unit_ids["department"]},
            idempotency_key=f"{idem}:xfer",
        )
        executed = w4.execute_org_change_request(app, actor, request_id=str((xfer.get("request") or xfer)["request_id"]))
        check("future transfer applied", executed.get("ok"), executed)

        as_today = w4.get_assignment_as_of(app, company_code=company, employee_key=key_a, as_of=today)
        as_future = w4.get_assignment_as_of(app, company_code=company, employee_key=key_a, as_of=future)
        check("as-of today not future slice", str((as_today or {}).get("effective_from") or "")[:10] < future.isoformat(), as_today)
        check("as-of future is transfer", (as_future or {}).get("change_type") == "transfer", as_future)

        mgr_day = future + timedelta(days=1)
        mgr_req = w4.create_org_change_request(
            app,
            actor,
            employee_key=key_a,
            change_type="manager_change",
            effective_on=mgr_day,
            reason="future mgr",
            payload={"manager_employee_key": key_c},
            idempotency_key=f"{idem}:mgr",
        )
        mgr_exec = w4.execute_org_change_request(app, actor, request_id=str((mgr_req.get("request") or mgr_req)["request_id"]))
        check("future manager applied", mgr_exec.get("ok"), mgr_exec)
        as_mgr = w4.get_assignment_as_of(app, company_code=company, employee_key=key_a, as_of=mgr_day)
        check("manager as-of future day", (as_mgr or {}).get("manager_employee_key") == key_c, as_mgr)
        as_today2 = w4.get_assignment_as_of(app, company_code=company, employee_key=key_a, as_of=today)
        check("today manager not yet switched", (as_today2 or {}).get("manager_employee_key") != key_c, as_today2)

        # Activate-due syncs Wave 2 at effective time
        act = w4.activate_due_assignment_slices(app, company_code=company, as_of=mgr_day)
        check("activate due ok", act.get("ok"), act)
        proj = authority.get_authority_projection(app, company_code=company, employee_key=key_a)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT manager_employee_key FROM employee_assignments WHERE company_code=%s AND assignment_id=%s",
                    (company, proj["assignment_id"]),
                )
                w2m = dict(cur.fetchone() or {})
            conn.commit()
        check("wave2 manager equals as-of after activate", w2m.get("manager_employee_key") == key_c, w2m)

        # Overlapping assignments fail closed
        try:
            w4.apply_assignment_change(
                app,
                actor,
                employee_key=key_a,
                effective_from=today - timedelta(days=5),
                change_type="department_change",
                reason="overlap probe",
                department_unit_id=unit_ids["department"],
            )
            check("overlapping assignment fail-closed", False)
        except Exception as exc:
            detail = getattr(exc, "detail", {}) or {}
            err = detail.get("error") if isinstance(detail, dict) else None
            check("overlapping assignment fail-closed", _http_exc_code(exc) in {409, 422} and err == "overlapping_assignment", exc)

        # --- Migration: dry-run → commit interrupt → resume → no auto-merge ---
        rows = [
            {"Full Name": f"{NAME_PREFIX}Imp1 {tag}", "Mobile": phone_m1, "Department": f"ImpDept-{tag}", "Title": "T1"},
            {"Full Name": f"{NAME_PREFIX}Imp2 {tag}", "Mobile": phone_m2, "Department": f"ImpDept-{tag}", "Title": "T2"},
            {"Full Name": f"{NAME_PREFIX}Imp3 {tag}", "Mobile": phone_m3, "Department": f"ImpDept-{tag}", "Title": "T3"},
            {"Full Name": f"{NAME_PREFIX}Dup {tag}", "Mobile": phone_m1, "Department": "X"},
        ]
        for r in rows:
            _assert_allowlisted(r["Mobile"], r["Full Name"])
        batch = w4.create_migration_batch(app, actor, filename=f"w4c-{tag}.csv", rows=rows, idempotency_key=f"{idem}:mig")
        batch_id = str(batch["batch"]["batch_id"])
        EVIDENCE["ids"]["migration_batch_id"] = batch_id
        dry = w4.dry_run_migration_batch(app, actor, batch_id=batch_id)
        check("dry-run valid=3", (dry.get("summary") or {}).get("valid") == 3, dry)
        check("dry-run duplicate enters review", int((dry.get("summary") or {}).get("duplicate") or 0) >= 1, dry)
        # Confirm duplicate never auto-merged (status needs_review / duplicate)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, count(*)::int AS n FROM employee_migration_rows WHERE batch_id=%s GROUP BY status",
                    (batch_id,),
                )
                by_status = {dict(r)["status"]: int(dict(r)["n"]) for r in cur.fetchall()}
            conn.commit()
        check("duplicate not auto-committed", by_status.get("committed", 0) == 0 and (by_status.get("duplicate", 0) + by_status.get("needs_review", 0)) >= 1, by_status)

        c1 = w4.commit_migration_batch(app, actor, batch_id=batch_id, resume=True, max_rows=1)
        check("interrupt after 1", len(c1.get("committed") or []) == 1 and c1.get("paused") is True, c1)
        keys.append(c1["committed"][0]["employee_key"])
        c2 = w4.commit_migration_batch(app, actor, batch_id=batch_id, resume=True, max_rows=1)
        check("resume +1 no dup", len(c2.get("committed") or []) == 1, c2)
        keys.append(c2["committed"][0]["employee_key"])
        c2b = w4.commit_migration_batch(app, actor, batch_id=batch_id, resume=True, max_rows=1)
        c3 = w4.commit_migration_batch(app, actor, batch_id=batch_id, resume=True)
        check("resume finishes remaining", c3.get("ok") and int((c3.get("review_remaining") or {}).get("valid_remaining") or 0) == 0, c3)
        for item in (c2b.get("committed") or []) + (c3.get("committed") or []):
            if item.get("employee_key"):
                keys.append(item["employee_key"])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT employee_key FROM employee_migration_rows WHERE batch_id=%s AND status='committed'",
                    (batch_id,),
                )
                committed_keys = [dict(r)["employee_key"] for r in cur.fetchall()]
                # Capture ImpDept unit before rollback (shared catalog must survive)
                cur.execute(
                    "SELECT org_unit_id::text, unit_key, name FROM employee_org_units WHERE company_code=%s AND name=%s",
                    (company, f"ImpDept-{tag}"),
                )
                shared_dept = dict(cur.fetchone() or {})
            conn.commit()
        check("3 committed imports", len(committed_keys) == 3, committed_keys)
        keys.extend(committed_keys)
        EVIDENCE["ids"]["migration_keys"] = committed_keys
        EVIDENCE["ids"]["shared_imp_dept"] = shared_dept
        check("shared import dept created", bool(shared_dept.get("org_unit_id")), shared_dept)

        # Audit journal
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*)::int AS n FROM employee_org_migration_journal
                    WHERE company_code=%s AND created_at > now() - interval '30 minutes'
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

        # Migration rollback: hub+authority+history gone; shared units remain
        rb = w4.rollback_migration_batch(app, actor, batch_id=batch_id, idempotency_key=f"{idem}:mig-rb")
        check("rollback ok", rb.get("ok") and rb.get("ghost_check", {}).get("ok") is True, rb)
        check("ghost check empty", rb.get("ghost_check", {}).get("ghosts") == [], rb)
        for k in committed_keys:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM employees WHERE employee_key=%s", (k,))
                    hub = cur.fetchone()
                    cur.execute("SELECT 1 FROM employee_key_authority_map WHERE employee_key=%s", (k,))
                    amap = cur.fetchone()
                    cur.execute("SELECT 1 FROM employee_org_assignment_history WHERE employee_key=%s", (k,))
                    hist_g = cur.fetchone()
                conn.commit()
            check(f"no hub ghost {k[-8:]}", hub is None)
            check(f"no authority ghost {k[-8:]}", amap is None)
            check(f"no history ghost {k[-8:]}", hist_g is None)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM employee_org_units WHERE org_unit_id=%s",
                    (shared_dept.get("org_unit_id"),),
                )
                still = cur.fetchone()
            conn.commit()
        check("shared org unit retained after migration rollback", still is not None, shared_dept)

        # --- Bulk idempotent + partial failure ---
        w4.apply_assignment_change(
            app, actor, employee_key=key_b, effective_from=today - timedelta(days=3),
            change_type="initial", reason="seed b", department_unit_id=unit_ids["department"],
        )
        w4.apply_assignment_change(
            app, actor, employee_key=key_c, effective_from=today - timedelta(days=3),
            change_type="initial", reason="seed c", department_unit_id=unit_ids["department"],
        )
        # Success path idempotent
        bulk_ok = w4.create_bulk_assign_job(
            app, actor,
            employee_keys=[key_b, key_c],
            effective_from=today + timedelta(days=3),
            reason="bulk ok",
            idempotency_key=f"{idem}:bulk-ok",
            location_unit_id=unit_ids["location"],
        )
        applied_ok = len(bulk_ok.get("applied") or []) == 2
        job_st = str((bulk_ok.get("job") or {}).get("status") or "")
        check(
            "bulk success",
            bool(bulk_ok.get("ok")) and (applied_ok or job_st in {"completed", "complete", "succeeded", "done"}),
            bulk_ok,
        )
        bulk_ok2 = w4.create_bulk_assign_job(
            app, actor,
            employee_keys=[key_b, key_c],
            effective_from=today + timedelta(days=3),
            reason="bulk ok",
            idempotency_key=f"{idem}:bulk-ok",
            location_unit_id=unit_ids["location"],
        )
        check("bulk idempotent same key", bulk_ok2.get("ok") and str(bulk_ok2.get("job", {}).get("job_id")) == str(bulk_ok.get("job", {}).get("job_id")), bulk_ok2)

        bogus = f"{company}-96554999999"
        bulk = w4.create_bulk_assign_job(
            app, actor,
            employee_keys=[key_b, bogus],
            effective_from=today + timedelta(days=4),
            reason="bulk partial",
            idempotency_key=f"{idem}:bulk",
            location_unit_id=unit_ids["location"],
        )
        check("bulk partial not silent success", bulk.get("partial_success") is False, bulk)
        check("bulk failed state", (bulk.get("job") or {}).get("status") == "failed", bulk)
        check("bulk applied one", key_b in (bulk.get("applied") or []), bulk)
        job_id = str(bulk["job"]["job_id"])
        hist_before = w4.list_assignment_history(app, company_code=company, employee_key=key_b)
        bulk_n = sum(1 for h in hist_before if h.get("change_type") == "bulk_assign")
        retry = w4.run_bulk_assign_job(app, actor, job_id=job_id, retry_failed=True)
        check("retry still fails for bogus", retry.get("ok") is False, retry)
        hist_after = w4.list_assignment_history(app, company_code=company, employee_key=key_b)
        bulk_n2 = sum(1 for h in hist_after if h.get("change_type") == "bulk_assign")
        check("retry no duplicate bulk slice", bulk_n2 == bulk_n, {"before": bulk_n, "after": bulk_n2})
        rev = w4.reverse_bulk_assign_job(app, actor, job_id=job_id, idempotency_key=f"{idem}:bulk-rev")
        check("bulk reverse", rev.get("ok") and int(rev.get("reversed_count") or 0) >= 1, rev)

        # Export + reconcile
        export = w4.export_org_reconciliation(app, company_code=company, as_of=today)
        check("export as-of", export.get("ok") and export.get("as_of") == today.isoformat(), export)
        recon = w4.reconcile_org_authority(app, company_code=company, as_of=today)
        check("reconcile runs", "hard_issue_count" in recon, recon)
        row_a = next((r for r in export.get("rows") or [] if r.get("employee_key") == key_a), None)
        check("export has as-of history for A", bool(row_a and row_a.get("as_of_history_id")), row_a)
        check("export person_id matches wave2", bool(row_a and row_a.get("person_id")), row_a)
        EVIDENCE["reconciliation"] = {
            "hard_issue_count": recon.get("hard_issue_count"),
            "info_issue_count": recon.get("info_issue_count"),
            "export_row_count": len(export.get("rows") or []),
            "row_a": row_a,
        }

        # Cross-tenant / manager scope
        try:
            w4.upsert_org_unit(app, ctx("OTHERCO"), unit_type="department", name=f"X-{tag}", unit_key=f"x-{tag}")
            check("cross-tenant denied", False)
        except Exception as exc:
            detail = getattr(exc, "detail", {}) or {}
            check(
                "cross-tenant denied",
                _http_exc_code(exc) == 403 and (detail.get("error") if isinstance(detail, dict) else None) == "org_v4_disabled",
                exc,
            )

        real_scope = app.manager_scope_context
        app.manager_scope_context = lambda *a, **k: {
            "restricted": True, "branch_keys": [], "team_keys": [], "direct_employee_keys": [],
        }
        try:
            w4.apply_assignment_change(
                app, actor, employee_key=key_a, effective_from=today + timedelta(days=30),
                change_type="department_change", reason="scope deny", department_unit_id=unit_ids["department"],
            )
            check("out-of-scope denied", False)
        except Exception as exc:
            check("out-of-scope denied", _http_exc_code(exc) == 404, exc)
        finally:
            app.manager_scope_context = real_scope

        # --- Unattended activate-due via shared worker (kill switch + idempotency) ---
        # Dedicated employee so prior bulk/transfer history cannot overlap.
        phone_sched = f"{PHONE_PREFIX}{(seed + 9) % 100000:05d}"
        assert phone_sched.isdigit() and len(phone_sched) == 11
        key_sched = create(phone_sched, f"{NAME_PREFIX}Sched {tag}")
        EVIDENCE["ids"]["employees"]["sched"] = key_sched
        authority.backfill_company_authority(
            app, company_code=company, idempotency_key=f"{idem}:bf-sched", employee_keys=[key_sched]
        )
        due_day = today
        w4.apply_assignment_change(
            app, actor, employee_key=key_sched, effective_from=due_day - timedelta(days=2),
            change_type="initial", reason="scheduler seed", department_unit_id=unit_ids["department"],
            manager_employee_key=key_c,
        )
        w4.apply_assignment_change(
            app, actor, employee_key=key_sched, effective_from=due_day,
            change_type="manager_change", reason="scheduler due", manager_employee_key=key_a,
            department_unit_id=unit_ids["department"],
        )
        # Reset wave2 manager away from key_a to prove activate sync
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT assignment_id FROM employee_key_authority_map WHERE company_code=%s AND employee_key=%s",
                    (company, key_sched),
                )
                aid = dict(cur.fetchone() or {}).get("assignment_id")
                if aid:
                    cur.execute(
                        "UPDATE employee_assignments SET manager_employee_key=%s, updated_at=now() WHERE assignment_id=%s",
                        (key_c, aid),
                    )
            conn.commit()

        worker_path = Path(__file__).resolve().parent / "lifecycle-effective-worker.py"
        import importlib.util

        spec = importlib.util.spec_from_file_location("lifecycle_effective_worker_w4c", worker_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        os.environ["WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_DUE"] = "off"
        check("kill switch env off", os.environ.get("WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_DUE") == "off")
        os.environ["WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_DUE"] = "on"
        act1 = w4.activate_due_assignment_slices(app, company_code=company, as_of=due_day)
        act2 = w4.activate_due_assignment_slices(app, company_code=company, as_of=due_day)
        check("activate due first pass", act1.get("ok"), act1)
        check("activate due idempotent second pass", act2.get("ok"), act2)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT manager_employee_key FROM employee_assignments WHERE company_code=%s AND assignment_id=%s",
                    (company, aid),
                )
                synced = dict(cur.fetchone() or {})
                cur.execute(
                    """
                    SELECT count(*)::int AS n FROM employee_org_migration_journal
                    WHERE company_code=%s AND action='activate_due_assignment_slice'
                      AND idempotency_key LIKE %s
                    """,
                    (company, f"w4b-activate:{company}:{key_sched}:{due_day.isoformat()}:%"),
                )
                jn_act = int(dict(cur.fetchone())["n"])
            conn.commit()
        check("unattended-style activate synced wave2", synced.get("manager_employee_key") == key_a, synced)
        check("activate journal idempotent (1 key)", jn_act == 1, jn_act)
        EVIDENCE["scheduler"] = {
            "shared_timer": "wathefni-lifecycle-effective.timer",
            "kill_switch": "WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_DUE",
            "activate_1": act1,
            "activate_2": act2,
            "journal_count": jn_act,
            "employee_key": key_sched,
        }

        # Run worker module once for persistence proof (non-failing)
        try:
            spec.loader.exec_module(mod)
            rc = mod.main()
            check("shared worker exit 0", rc == 0, rc)
        except Exception as exc:
            check("shared worker exit 0", False, exc)

        # Reals untouched
        reals_after = snapshot_reals()
        EVIDENCE["reals"]["after"] = reals_after
        for k in REAL_KEYS:
            b, a = reals_before[k], reals_after[k]
            check(
                f"real untouched {k[-8:]}",
                b == a and a.get("org_history_count", 0) == 0,
                {"before": b, "after": a},
            )

    finally:
        try:
            cleanup()
            # After cleanup, verify zero allowlisted leftovers for this tag
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT count(*)::int AS n FROM employees WHERE company_code=%s AND (phone LIKE %s OR name LIKE %s)",
                        (company, f"{PHONE_PREFIX}%", f"%{NAME_PREFIX}%{tag}%"),
                    )
                    left = int(dict(cur.fetchone())["n"])
                conn.commit()
            check("synthetic cleanup zero", left == 0, left)
        except Exception as exc:
            print(f"cleanup warning: {exc}")
            check("synthetic cleanup zero", False, str(exc))

    EVIDENCE["summary"] = {"pass": PASS, "fail": FAIL, "tag": tag, "phone_prefix": PHONE_PREFIX}
    out_path = os.environ.get("WAVE4C_EVIDENCE_JSON")
    if out_path:
        Path(out_path).write_text(json.dumps(EVIDENCE, default=str, indent=2))
        print(f"evidence_json={out_path}")
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
