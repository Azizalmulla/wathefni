"""Wave 4 org authority — staging DB smoke (synthetic WATHEFNI only).

Local/staging only. Does not enable real-employee lifecycle use.
Does not deploy to production. Cleans synthetic rows in finally.
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
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    # Lifecycle must stay synthetic-only / not required for Wave 4 org proofs
    os.environ.setdefault("WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY", "on")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import app
    import employee_authority_wave2 as authority
    import employee_org_wave4 as w4

    company = "WATHEFNI"
    tag = uuid.uuid4().hex[:8]
    phone_a = f"965533{tag[:5]}"
    phone_b = f"965534{tag[:5]}"
    phone_mgr = f"965535{tag[:5]}"
    phone_imp = f"965536{tag[:5]}"
    phone_dup = f"965537{tag[:5]}"
    key_a = f"{company}-{phone_a}"
    key_b = f"{company}-{phone_b}"
    key_mgr = f"{company}-{phone_mgr}"
    today = date.today()
    future = today + timedelta(days=14)
    idem = f"wave4-smoke:{company}:{tag}"
    requester_id = None

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
            perms = app.dashboard_effective_permissions_for_user(u)
            if "employees.manage" in perms:
                requester_id = str(u["user_id"])
                return
        raise RuntimeError("no employees.manage actor")

    def ctx(actor_id: str, company_code: str = company):
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM dashboard_users WHERE company_code=%s AND user_id=%s", (company, actor_id))
                user = dict(cur.fetchone())
        perms = list(app.dashboard_effective_permissions_for_user(user))
        if "employees.manage" not in perms:
            perms.append("employees.manage")
        return {
            "company_code": company_code,
            "actor_user_id": actor_id,
            "actor": user,
            "permissions": perms,
            "access": {"role": user.get("role") or "owner", "permissions": perms},
            "permission_authority": "backend_current",
            "permission_subject_user_id": actor_id,
            "permission_subject_company": company_code,
            "actor_role": user.get("role") or "owner",
        }

    def cleanup():
        keys = [key_a, key_b, key_mgr, f"{company}-{phone_imp}", f"{company}-{phone_dup}"]
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w4.ensure_org_wave4_schema(cur)
                authority.ensure_authority_schema(cur)
                cur.execute(
                    "DELETE FROM employee_org_assignment_history WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                cur.execute(
                    "DELETE FROM employee_org_change_requests WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                cur.execute(
                    "DELETE FROM employee_bulk_job_items WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
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
                cur.execute(
                    """
                    SELECT person_id::text, employment_id::text, assignment_id::text
                    FROM employee_key_authority_map
                    WHERE company_code=%s AND employee_key = ANY(%s)
                    """,
                    (company, keys),
                )
                maps = [dict(r) for r in (cur.fetchall() or [])]
                cur.execute(
                    "DELETE FROM employee_key_authority_map WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
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
                cur.execute("DELETE FROM employees WHERE employee_key = ANY(%s)", (keys,))
            conn.commit()

    cleanup()
    try:
        load_actor()
        actor = ctx(requester_id)
        check("org v4 enabled", w4.org_v4_enabled(company) is True)
        check("cross-tenant org disabled", w4.org_v4_enabled("OTHERCO") is False)

        # --- Policy tiers ---
        small = w4.upsert_org_policy(app, actor, patch={"tier": "small"})
        check("policy small", small.get("tier") == "small", small)
        medium = w4.upsert_org_policy(app, actor, patch={"tier": "medium"})
        check("policy medium", medium.get("tier") == "medium" and "branch" in (medium.get("simple_org_types") or []), medium)
        enterprise = w4.upsert_org_policy(app, actor, patch={"tier": "enterprise"})
        check("policy enterprise dual", enterprise.get("require_dual_approval") is True, enterprise)

        # --- Org structure CRUD (enterprise depth first, then small-safe updates) ---
        legal = w4.upsert_org_unit(app, actor, unit_type="legal_employer", name=f"Legal-{tag}", unit_key=f"legal-{tag}")
        branch = w4.upsert_org_unit(app, actor, unit_type="branch", name=f"Branch-{tag}", unit_key=f"branch-{tag}")
        cc = w4.upsert_org_unit(app, actor, unit_type="cost_center", name=f"CC-{tag}", unit_key=f"cc-{tag}")
        dept = w4.upsert_org_unit(app, actor, unit_type="department", name=f"Ops-{tag}", unit_key=f"ops-{tag}")
        loc = w4.upsert_org_unit(app, actor, unit_type="location", name=f"HQ-{tag}", unit_key=f"hq-{tag}")
        team = w4.upsert_org_unit(app, actor, unit_type="team", name=f"Alpha-{tag}", unit_key=f"alpha-{tag}")
        pos = w4.upsert_org_unit(app, actor, unit_type="position", name=f"Analyst-{tag}", unit_key=f"analyst-{tag}")
        check("enterprise legal employer", legal.get("ok"), legal)
        check("enterprise branch", branch.get("ok"), branch)
        check("enterprise cost center", cc.get("ok"), cc)
        check("create department", dept.get("ok") and dept["unit"]["name"] == f"Ops-{tag}", dept)
        check("create location", loc.get("ok"), loc)
        check("create team", team.get("ok"), team)
        check("create position", pos.get("ok"), pos)
        dept2 = w4.upsert_org_unit(app, actor, unit_type="department", name=f"Ops-Updated-{tag}", unit_key=f"ops-{tag}")
        check("update department version", int(dept2["unit"]["version"]) >= 2 and "Updated" in dept2["unit"]["name"], dept2)
        units = w4.list_org_units(app, company_code=company, unit_type="department")
        check("list departments includes unit", any(u.get("unit_key") == f"ops-{tag}" for u in units), len(units))

        # Restore small for remaining smoke (simpler defaults; units already exist)
        w4.upsert_org_policy(app, actor, patch={"tier": "small", "require_dual_approval": False})
        try:
            w4.upsert_org_unit(app, actor, unit_type="branch", name=f"Blocked-{tag}", unit_key=f"blocked-{tag}")
            check("small blocks deep unit types", False)
        except Exception as exc:
            detail = getattr(exc, "detail", {}) or {}
            err = detail.get("error") if isinstance(detail, dict) else None
            check("small blocks deep unit types", _http_exc_code(exc) == 422 and err == "unit_type_not_enabled_for_tier", exc)

        # --- Employees + authority ---
        created_a = app.create_company_employee(company, name=f"W4 Smoke A {tag}", phone=phone_a, position_title="Analyst", department=f"Ops-{tag}")
        created_b = app.create_company_employee(company, name=f"W4 Smoke B {tag}", phone=phone_b, position_title="Clerk")
        created_m = app.create_company_employee(company, name=f"W4 Smoke Mgr {tag}", phone=phone_mgr, position_title="Manager")
        check("create A", created_a.get("status") == "created", created_a)
        check("create B", created_b.get("status") == "created", created_b)
        check("create mgr", created_m.get("status") == "created", created_m)
        key_a = str(created_a.get("employee_key") or (created_a.get("employee") or {}).get("employee_key") or key_a)
        key_b = str(created_b.get("employee_key") or (created_b.get("employee") or {}).get("employee_key") or key_b)
        key_mgr = str(created_m.get("employee_key") or (created_m.get("employee") or {}).get("employee_key") or key_mgr)
        authority.backfill_company_authority(
            app, company_code=company, idempotency_key=f"{idem}:bf", employee_keys=[key_a, key_b, key_mgr]
        )
        proj_a = authority.get_authority_projection(app, company_code=company, employee_key=key_a)
        check("wave2 authority present", bool(proj_a and proj_a.get("person_id")), proj_a)

        dept_id = str(dept["unit"]["org_unit_id"])
        loc_id = str(loc["unit"]["org_unit_id"])
        team_id = str(team["unit"]["org_unit_id"])
        pos_id = str(pos["unit"]["org_unit_id"])

        # Initial assignment
        init = w4.apply_assignment_change(
            app,
            actor,
            employee_key=key_a,
            effective_from=today - timedelta(days=30),
            change_type="initial",
            reason="initial assignment",
            department_unit_id=dept_id,
            location_unit_id=loc_id,
            position_unit_id=pos_id,
            position_title="Analyst",
        )
        check("initial assignment", init.get("ok") and init.get("history"), init)
        hist_id_1 = init["history"]["history_id"]

        # Transfer with history preserved
        transfer = w4.apply_assignment_change(
            app,
            actor,
            employee_key=key_a,
            effective_from=today,
            change_type="transfer",
            reason="move to alpha team",
            team_unit_id=team_id,
            department_unit_id=dept_id,
            location_unit_id=loc_id,
        )
        check("transfer ok", transfer.get("ok"), transfer)
        check("prior closed not overwritten", transfer.get("closed_prior") and str(transfer["closed_prior"]["history_id"]) == str(hist_id_1), transfer.get("closed_prior"))
        closed_to = transfer["closed_prior"].get("effective_to")
        expected_to = today - timedelta(days=1)
        check(
            "prior effective_to set",
            str(closed_to)[:10] == expected_to.isoformat(),
            transfer["closed_prior"],
        )
        hist = w4.list_assignment_history(app, company_code=company, employee_key=key_a)
        check("history has 2 slices", len(hist) >= 2, hist)
        check("open slice is newest", hist[0].get("effective_to") in (None, "") and hist[0].get("change_type") == "transfer", hist[0])

        # Future-dated manager change (scheduled request)
        mgr_req = w4.create_org_change_request(
            app,
            actor,
            employee_key=key_a,
            change_type="manager_change",
            effective_on=future,
            reason="future manager assignment",
            payload={"manager_employee_key": key_mgr},
            idempotency_key=f"{idem}:mgr-future",
        )
        check("future manager scheduled", mgr_req.get("status") == "scheduled" or (mgr_req.get("request") or {}).get("status") == "scheduled", mgr_req)
        hist_before_exec = w4.list_assignment_history(app, company_code=company, employee_key=key_a)
        open_mgr = next((h for h in hist_before_exec if h.get("effective_to") in (None, "")), None)
        check("manager not applied early", (open_mgr or {}).get("manager_employee_key") != key_mgr, open_mgr)

        # Execute scheduled future-dated change without collapsing to today
        req_id = str((mgr_req.get("request") or mgr_req).get("request_id") or "")
        if not req_id:
            check("future manager request id", False, mgr_req)
        else:
            executed = w4.execute_org_change_request(app, actor, request_id=req_id)
            check("future manager executed", executed.get("ok") and executed.get("applied"), executed)
            open_after = next((h for h in w4.list_assignment_history(app, company_code=company, employee_key=key_a) if h.get("effective_to") in (None, "")), None)
            check("manager now set", (open_after or {}).get("manager_employee_key") == key_mgr, open_after)
            check(
                "manager effective future",
                str((open_after or {}).get("effective_from") or "")[:10] == future.isoformat(),
                open_after,
            )

        # Overlapping assignments fail closed (into closed historical coverage)
        try:
            w4.apply_assignment_change(
                app,
                actor,
                employee_key=key_a,
                effective_from=today - timedelta(days=10),
                change_type="department_change",
                reason="overlap attempt",
                department_unit_id=dept_id,
            )
            check("overlapping assignment fail-closed", False)
        except Exception as exc:
            detail = getattr(exc, "detail", {}) or {}
            err = detail.get("error") if isinstance(detail, dict) else None
            check("overlapping assignment fail-closed", _http_exc_code(exc) == 409 and err == "overlapping_assignment", exc)

        # Same-day open overwrite fail-closed (use today's transfer slice start, not future manager slice)
        try:
            w4.apply_assignment_change(
                app,
                actor,
                employee_key=key_a,
                effective_from=future,
                change_type="location_change",
                reason="same day overwrite attempt",
                location_unit_id=loc_id,
            )
            check("same-day open overwrite fail-closed", False)
        except Exception as exc:
            detail = getattr(exc, "detail", {}) or {}
            err = detail.get("error") if isinstance(detail, dict) else None
            check("same-day open overwrite fail-closed", _http_exc_code(exc) == 409 and err == "overlapping_assignment", exc)

        # --- Migration batch: dry-run / commit / pause / resume / rollback ---
        # Seed an existing employee for conflict + ambiguous name mismatch
        exist = app.create_company_employee(company, name=f"W4 Existing {tag}", phone=phone_dup, position_title="X")
        key_dup = str(exist.get("employee_key") or (exist.get("employee") or {}).get("employee_key"))
        authority.backfill_company_authority(app, company_code=company, idempotency_key=f"{idem}:bf2", employee_keys=[key_dup])

        rows = [
            {"Full Name": f"W4 Import Ok {tag}", "Mobile": phone_imp, "Department": f"ImportDept-{tag}", "Title": "Importer"},
            {"Full Name": f"W4 Existing {tag}", "Mobile": phone_dup, "Department": "X"},  # conflict exact
            {"Full Name": f"W4 Wrong Name {tag}", "Mobile": phone_dup, "Department": "Y"},  # needs_review (same phone different name — but phone already seen as conflict first)
            {"Full Name": "", "Mobile": "96553800001"},  # invalid
            {"Full Name": f"W4 Dup In Batch {tag}", "Mobile": phone_imp, "Department": "Z"},  # duplicate in batch
        ]
        # Fix row 3: use a phone that exists with different name — create that separately
        phone_amb = f"965539{tag[:5]}"
        amb = app.create_company_employee(company, name=f"W4 Ambiguous Real {tag}", phone=phone_amb)
        key_amb = str(amb.get("employee_key") or (amb.get("employee") or {}).get("employee_key"))
        authority.backfill_company_authority(app, company_code=company, idempotency_key=f"{idem}:bf3", employee_keys=[key_amb])
        rows[2] = {"Full Name": f"W4 Ambiguous Other {tag}", "Mobile": phone_amb, "Department": "Y"}

        batch = w4.create_migration_batch(
            app, actor, filename=f"wave4-{tag}.csv", rows=rows, idempotency_key=f"{idem}:mig"
        )
        check("migration batch created", batch.get("ok") and batch.get("row_count") == 5, batch)
        dry = w4.dry_run_migration_batch(app, actor, batch_id=str(batch["batch"]["batch_id"]))
        summary = dry.get("summary") or {}
        check("dry-run valid=1", summary.get("valid") == 1, summary)
        check("dry-run conflict>=1", int(summary.get("conflict") or 0) >= 1, summary)
        check("dry-run needs_review>=1", int(summary.get("needs_review") or 0) >= 1, summary)
        check("dry-run duplicate>=1", int(summary.get("duplicate") or 0) >= 1, summary)
        check("dry-run invalid>=1", int(summary.get("invalid") or 0) >= 1, summary)
        check("no silent partial", dry.get("partial_success") is False, dry)

        # Pause then commit with max_rows=1 then resume
        pause = w4.pause_migration_batch(app, actor, batch_id=str(batch["batch"]["batch_id"]))
        check("migration paused", pause.get("ok") and pause["batch"]["status"] == "paused", pause)
        commit1 = w4.commit_migration_batch(
            app, actor, batch_id=str(batch["batch"]["batch_id"]), resume=True, max_rows=1
        )
        check("commit chunk", commit1.get("ok") and len(commit1.get("committed") or []) == 1, commit1)
        check("paused after chunk or committed", commit1["batch"]["status"] in {"paused", "committed", "staged"}, commit1)
        commit2 = w4.commit_migration_batch(app, actor, batch_id=str(batch["batch"]["batch_id"]), resume=True)
        check("resume finishes", commit2.get("ok"), commit2)
        check("review rows not auto-created", (commit2.get("review_remaining") or {}).get("needs_review", 0) >= 1 or (commit1.get("review_remaining") or {}).get("needs_review", 0) >= 1, commit2)
        # Ambiguous people never auto-merged: needs_review status remains
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, count(*)::int n FROM employee_migration_rows WHERE batch_id=%s GROUP BY status",
                    (batch["batch"]["batch_id"],),
                )
                by_status = {dict(r)["status"]: int(dict(r)["n"]) for r in cur.fetchall()}
            conn.commit()
        check("needs_review in queue", int(by_status.get("needs_review") or 0) >= 1, by_status)
        check("conflict in queue", int(by_status.get("conflict") or 0) >= 1, by_status)

        # Export matches Wave 2 authority for imported key (use committed key, not assumed phone)
        imp_key = str((commit1.get("committed") or [{}])[0].get("employee_key") or "")
        check("import committed key present", bool(imp_key), commit1)
        authority.backfill_company_authority(
            app, company_code=company, idempotency_key=f"{idem}:bf-imp", employee_keys=[imp_key]
        )
        export = w4.export_org_reconciliation(app, company_code=company)
        exp_row = next((r for r in export.get("rows") or [] if r.get("employee_key") == imp_key), None)
        proj_imp = authority.get_authority_projection(app, company_code=company, employee_key=imp_key)
        check("export includes import", bool(exp_row), exp_row)
        check(
            "export matches wave2 authority",
            bool(proj_imp) and exp_row and str(exp_row.get("person_id") or "") == str(proj_imp.get("person_id") or ""),
            {"exp": exp_row, "proj": proj_imp},
        )

        # Rollback migration (history slices)
        rb = w4.rollback_migration_batch(
            app, actor, batch_id=str(batch["batch"]["batch_id"]), idempotency_key=f"{idem}:mig-rb"
        )
        check("migration rollback", rb.get("ok") and rb["batch"]["status"] == "rolled_back", rb)

        # --- Bulk assign idempotent + reversible ---
        # Seed B assignment
        w4.apply_assignment_change(
            app,
            actor,
            employee_key=key_b,
            effective_from=today - timedelta(days=5),
            change_type="initial",
            reason="seed B",
            department_unit_id=dept_id,
        )
        bulk = w4.create_bulk_assign_job(
            app,
            actor,
            employee_keys=[key_b],
            effective_from=today + timedelta(days=1),
            reason="bulk move location",
            idempotency_key=f"{idem}:bulk",
            location_unit_id=loc_id,
            team_unit_id=team_id,
            manager_employee_key=key_mgr,
        )
        check("bulk applied", bulk.get("ok") and key_b in (bulk.get("applied") or []), bulk)
        job_id = str(bulk["job"]["job_id"])
        bulk2 = w4.run_bulk_assign_job(app, actor, job_id=job_id)
        check("bulk idempotent rerun", bulk2.get("idempotent") is True or bulk2["job"]["status"] == "succeeded", bulk2)
        rev = w4.reverse_bulk_assign_job(app, actor, job_id=job_id, idempotency_key=f"{idem}:bulk-rev")
        check("bulk reversible", rev.get("ok") and int(rev.get("reversed_count") or 0) >= 1, rev)
        open_b = next((h for h in w4.list_assignment_history(app, company_code=company, employee_key=key_b) if h.get("effective_to") in (None, "")), None)
        check("bulk reverse restored prior open", open_b and open_b.get("change_type") == "initial", open_b)

        # --- Out-of-scope manager fail-closed ---
        real_scope = app.manager_scope_context
        app.manager_scope_context = lambda *a, **k: {
            "restricted": True,
            "branch_keys": [],
            "team_keys": [],
            "direct_employee_keys": [],
        }
        try:
            w4.apply_assignment_change(
                app,
                actor,
                employee_key=key_a,
                effective_from=today + timedelta(days=2),
                change_type="department_change",
                reason="out of scope",
                department_unit_id=dept_id,
            )
            check("out-of-scope manager denied", False)
        except Exception as exc:
            check("out-of-scope manager denied", _http_exc_code(exc) == 404, exc)
        finally:
            app.manager_scope_context = real_scope

        # --- Cross-tenant fail-closed ---
        other_ctx = ctx(requester_id, company_code="OTHERCO")
        try:
            w4.upsert_org_unit(app, other_ctx, unit_type="department", name=f"X-{tag}", unit_key=f"x-{tag}")
            check("cross-tenant mutation denied", False)
        except Exception as exc:
            detail = getattr(exc, "detail", {}) or {}
            err = detail.get("error") if isinstance(detail, dict) else None
            check("cross-tenant mutation denied", _http_exc_code(exc) == 403 and err == "org_v4_disabled", exc)

        # Enterprise dual-approval gate
        w4.upsert_org_policy(app, actor, patch={"tier": "enterprise"})
        try:
            w4.create_org_change_request(
                app,
                actor,
                employee_key=key_a,
                change_type="job_change",
                effective_on=today + timedelta(days=3),
                reason="needs dual",
                payload={"position_title": "Lead"},
                idempotency_key=f"{idem}:dual",
                designated_approver_user_id=str(requester_id),  # self — must fail
            )
            check("enterprise dual-approval self fail-closed", False)
        except Exception as exc:
            detail = getattr(exc, "detail", {}) or {}
            err = detail.get("error") if isinstance(detail, dict) else None
            check("enterprise dual-approval self fail-closed", _http_exc_code(exc) == 403 and err == "dual_approval_required", exc)
        w4.upsert_org_policy(app, actor, patch={"tier": "small", "require_dual_approval": False})

        check("employee_key compatibility", key_a.startswith(f"{company}-"), key_a)

    finally:
        try:
            cleanup()
            # also cleanup amb/imp if keys differ
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM employees WHERE company_code=%s AND phone LIKE %s AND name LIKE %s",
                        (company, "96553%", f"%{tag}%"),
                    )
                conn.commit()
        except Exception as exc:
            print(f"cleanup warning: {exc}")

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
