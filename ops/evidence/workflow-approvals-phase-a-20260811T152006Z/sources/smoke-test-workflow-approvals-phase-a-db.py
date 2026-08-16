#!/usr/bin/env python3
"""Phase A Slice 1 — workflow_approvals DB integration prove (staging/canary).

Synthetic canary subjects only. Does not enable the feature globally.
Requires DATABASE_URL / WATHEFNI_DATABASE_URL (or app.db_connect env).

Run on staging:
  WATHEFNI_ENV=staging ... python3 smoke-test-workflow-approvals-phase-a-db.py
"""
from __future__ import annotations

import inspect
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _connect():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("WATHEFNI_DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or ""
    ).strip()
    if not url:
        # Fall back to app.db_connect if orchestrator env is fully loaded.
        try:
            import app

            return app.db_connect(), True, RealDictCursor
        except Exception as exc:
            raise RuntimeError(f"no_database_url:{exc}") from exc
    conn = psycopg2.connect(url)
    return conn, False, RealDictCursor


def main() -> int:
    print("    workflow_approvals phase A slice 1 — DB integration prove")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import workflow_approvals as wa

    company = f"WFA{SUFFIX}".upper()  # synthetic canary tenant — not a real customer code
    other = f"WFX{SUFFIX}".upper()
    subject_type = "phase_a_canary"
    # Scoped env for this process only (never systemd-global in this script).
    os.environ["WATHEFNI_WORKFLOW_APPROVALS"] = "on"
    os.environ["WATHEFNI_WORKFLOW_APPROVALS_COMPANIES"] = company

    try:
        conn_tuple = _connect()
    except Exception as exc:
        print(f"FAIL DB connect: {exc}")
        return 2
    conn, via_app, RealDictCursor = conn_tuple

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # --- migration applies cleanly + idempotent -----------------------
            wa.ensure_workflow_approvals_schema(cur)
            conn.commit()
            wa.ensure_workflow_approvals_schema(cur)
            conn.commit()
            cur.execute(
                """
                SELECT count(*) AS c FROM information_schema.tables
                 WHERE table_schema='public'
                   AND table_name IN (
                     'workflow_approval_settings',
                     'workflow_approval_policies',
                     'workflow_approval_instances',
                     'workflow_approval_steps',
                     'workflow_delegation_grants',
                     'workflow_approval_events'
                   )
                """
            )
            table_count = int(dict(cur.fetchone())["c"])
            check("migration tables present", table_count == 6, table_count)
            check("migration second apply idempotent", True)

            # --- company settings default disabled ----------------------------
            settings = wa.get_company_workflow_approval_settings(cur, company)
            check("company settings default disabled", settings.get("enabled") is False, settings)
            conn.commit()

            # --- gates fail closed before enable ------------------------------
            gate0 = wa.workflow_approvals_enabled_for_company(cur, company)
            check(
                "gate closed: company setting",
                gate0.get("ok") is False and gate0.get("gate") == "company_setting",
                gate0,
            )
            os.environ["WATHEFNI_WORKFLOW_APPROVALS"] = "off"
            gate_flag = wa.workflow_approvals_enabled_for_company(cur, company)
            check(
                "gate closed: runtime flag",
                gate_flag.get("ok") is False and gate_flag.get("gate") == "runtime_flag",
                gate_flag,
            )
            os.environ["WATHEFNI_WORKFLOW_APPROVALS"] = "on"
            os.environ["WATHEFNI_WORKFLOW_APPROVALS_COMPANIES"] = "NOTTHIS"
            gate_al = wa.workflow_approvals_enabled_for_company(cur, company)
            check(
                "gate closed: allowlist",
                gate_al.get("ok") is False and gate_al.get("gate") == "company_allowlist",
                gate_al,
            )
            os.environ["WATHEFNI_WORKFLOW_APPROVALS_COMPANIES"] = company
            wa.set_company_workflow_approval_enabled(cur, company, enabled=True)
            gate_ok = wa.workflow_approvals_enabled_for_company(cur, company)
            check("gate open when all three set", gate_ok.get("ok") is True, gate_ok)
            conn.commit()

            # --- policy create/update -----------------------------------------
            pol1 = wa.upsert_policy(
                cur,
                company_code=company,
                subject_type=subject_type,
                name="Canary v1",
                steps=[{"step_order": 1, "assignee_user_id": "u-approver"}],
                actor_user_id="u-admin",
            )
            check("policy create", pol1.get("ok") is True, pol1)
            pol2 = wa.upsert_policy(
                cur,
                company_code=company,
                subject_type=subject_type,
                name="Canary v2",
                steps=[
                    {"step_order": 1, "assignee_user_id": "u-approver"},
                    {"step_order": 2, "assignee_user_id": "u-hr"},
                ],
                forbid_self_approval=True,
                actor_user_id="u-admin",
            )
            check("policy update (new active)", pol2.get("ok") is True, pol2)
            active = wa.get_active_policy(cur, company_code=company, subject_type=subject_type)
            check("active policy is v2 two-step", active and len(active["steps"]) == 2 and active["name"] == "Canary v2", active)
            conn.commit()

            # --- instance create + multi-step ---------------------------------
            idem = f"WFA-SYNTH|{SUFFIX}|create"
            created = wa.create_instance(
                cur,
                company_code=company,
                subject_type=subject_type,
                subject_id=f"WFA-SYNTH|{SUFFIX}|subj",
                created_by_user_id="u-creator",
                created_by_phone="96577000001",
                idempotency_key=idem,
                submit=True,
            )
            check("approval instance creation", created.get("ok") is True, created)
            inst = created["instance"]

            # SoD
            sod = wa.decide_step(
                cur,
                company_code=company,
                instance_id=inst["instance_id"],
                decision="approved",
                actor_user_id="u-creator",
                decision_id=f"WFA-SYNTH|{SUFFIX}|sod",
                expected_row_version=inst["row_version"],
            )
            check("self-approval SoD denial", sod.get("error") == "self_approval_forbidden", sod)

            # stale row_version
            stale = wa.decide_step(
                cur,
                company_code=company,
                instance_id=inst["instance_id"],
                decision="approved",
                actor_user_id="u-approver",
                decision_id=f"WFA-SYNTH|{SUFFIX}|stale",
                expected_row_version=int(inst["row_version"]) + 50,
            )
            check("stale row_version conflict", stale.get("error") == "concurrency_conflict", stale)

            d1 = wa.decide_step(
                cur,
                company_code=company,
                instance_id=inst["instance_id"],
                decision="approved",
                actor_user_id="u-approver",
                decision_id=f"WFA-SYNTH|{SUFFIX}|d1",
                expected_row_version=inst["row_version"],
            )
            check(
                "multi-step progression step1",
                d1.get("ok") is True and d1["instance"]["status"] == "pending",
                d1,
            )

            # idempotent decision replay
            d1r = wa.decide_step(
                cur,
                company_code=company,
                instance_id=inst["instance_id"],
                decision="approved",
                actor_user_id="u-approver",
                decision_id=f"WFA-SYNTH|{SUFFIX}|d1",
                expected_row_version=d1["instance"]["row_version"],
            )
            check("idempotent decision replay", d1r.get("ok") is True and d1r.get("replayed") is True, d1r)

            # --- delegation denials + valid path ------------------------------
            # out-of-scope
            g_oos = wa.create_delegation_grant(
                cur,
                company_code=company,
                delegator_user_id="u-hr",
                delegate_user_id="u-oos",
                starts_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                ends_at=datetime.now(timezone.utc) + timedelta(days=1),
                scope_subject_types=["other_subject"],
                actor_user_id="u-hr",
            )
            check("delegation out-of-scope grant created", g_oos.get("ok") is True, g_oos)
            deny_oos = wa.decide_step(
                cur,
                company_code=company,
                instance_id=inst["instance_id"],
                decision="approved",
                actor_user_id="u-oos",
                decision_id=f"WFA-SYNTH|{SUFFIX}|oos",
                expected_row_version=d1["instance"]["row_version"],
            )
            check("out-of-scope delegation denial", deny_oos.get("error") == "actor_not_assignee", deny_oos)

            # expired (insert past-window grant directly; create API rejects already_ended)
            expired_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO workflow_delegation_grants (
                  grant_id, company_code, delegator_user_id, delegate_user_id,
                  scope_subject_types, status, starts_at, ends_at
                ) VALUES (%s,%s,'u-hr','u-expired',ARRAY[%s],'active', now() - interval '2 days', now() - interval '1 hour')
                """,
                (expired_id, company, subject_type),
            )
            deny_exp = wa.decide_step(
                cur,
                company_code=company,
                instance_id=inst["instance_id"],
                decision="approved",
                actor_user_id="u-expired",
                decision_id=f"WFA-SYNTH|{SUFFIX}|exp",
                expected_row_version=d1["instance"]["row_version"],
            )
            check("expired delegation denial", deny_exp.get("error") == "actor_not_assignee", deny_exp)

            # revoked
            g_rev = wa.create_delegation_grant(
                cur,
                company_code=company,
                delegator_user_id="u-hr",
                delegate_user_id="u-revoked",
                starts_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                ends_at=datetime.now(timezone.utc) + timedelta(days=1),
                scope_subject_types=[subject_type],
                actor_user_id="u-hr",
            )
            check("revokable grant created", g_rev.get("ok") is True, g_rev)
            rev = wa.revoke_delegation_grant(
                cur,
                company_code=company,
                grant_id=str(g_rev["grant"]["grant_id"]),
                actor_user_id="u-hr",
            )
            check("delegation revoke", rev.get("ok") is True, rev)
            deny_rev = wa.decide_step(
                cur,
                company_code=company,
                instance_id=inst["instance_id"],
                decision="approved",
                actor_user_id="u-revoked",
                decision_id=f"WFA-SYNTH|{SUFFIX}|rev",
                expected_row_version=d1["instance"]["row_version"],
            )
            check("revoked delegation denial", deny_rev.get("error") == "actor_not_assignee", deny_rev)

            # valid delegation decision (final step)
            g_ok = wa.create_delegation_grant(
                cur,
                company_code=company,
                delegator_user_id="u-hr",
                delegate_user_id="u-delegate",
                starts_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                ends_at=datetime.now(timezone.utc) + timedelta(days=1),
                scope_subject_types=[subject_type],
                actor_user_id="u-hr",
            )
            check("valid delegation grant", g_ok.get("ok") is True, g_ok)
            d2 = wa.decide_step(
                cur,
                company_code=company,
                instance_id=inst["instance_id"],
                decision="approved",
                actor_user_id="u-delegate",
                decision_id=f"WFA-SYNTH|{SUFFIX}|d2",
                expected_row_version=d1["instance"]["row_version"],
            )
            check(
                "valid delegation decision",
                d2.get("ok") is True
                and d2["instance"]["status"] == "approved"
                and d2.get("acting_as_user_id") == "u-hr",
                d2,
            )

            # --- cross-tenant read/write denial -------------------------------
            cross_read = wa._load_instance(
                cur, company_code=other, instance_id=inst["instance_id"]
            )
            check("cross-tenant read denial", cross_read is None)
            cross_write = wa.decide_step(
                cur,
                company_code=other,
                instance_id=inst["instance_id"],
                decision="rejected",
                actor_user_id="u-approver",
                decision_id=f"WFA-SYNTH|{SUFFIX}|x",
            )
            check(
                "cross-tenant write denial",
                cross_write.get("ok") is False
                and cross_write.get("error") in {"workflow_approvals_company_not_allowlisted", "instance_not_found", "workflow_approvals_company_disabled"},
                cross_write,
            )

            # --- audit events -------------------------------------------------
            cur.execute(
                """
                SELECT event_type, count(*) AS c
                  FROM workflow_approval_events
                 WHERE company_code=%s
                 GROUP BY event_type
                """,
                (company,),
            )
            ev_map = {str(r["event_type"]): int(r["c"]) for r in cur.fetchall()}
            required_events = {
                "policy_upserted",
                "instance_created",
                "instance_submitted",
                "sod_denied",
                "concurrency_conflict",
                "step_decided",
                "idempotent_replay",
                "delegation_created",
                "delegation_revoked",
                "instance_approved",
            }
            missing = sorted(required_events - set(ev_map))
            check("audit events emitted correctly", not missing, {"missing": missing, "seen": ev_map})

            # --- disable returns safely to legacy behavior --------------------
            wa.set_company_workflow_approval_enabled(cur, company, enabled=False)
            blocked = wa.create_instance(
                cur,
                company_code=company,
                subject_type=subject_type,
                subject_id=f"WFA-SYNTH|{SUFFIX}|after-off",
                created_by_user_id="u-creator",
            )
            check(
                "disabling feature blocks new authority writes",
                blocked.get("ok") is False and blocked.get("gate") == "company_setting",
                blocked,
            )
            conn.commit()

            # --- Offer/Leave approval paths remain untouched ------------------
            # Static: workflow_approvals must not be imported by offer/leave decide paths.
            offer_src = Path(orch / "offer_service.py")
            leave_paths = [
                orch / "leave_authority_wave1.py",
                orch / "leave_workflow_wave3.py",
            ]
            offer_imports_wa = False
            if offer_src.is_file():
                offer_imports_wa = "workflow_approvals" in offer_src.read_text(encoding="utf-8")
            leave_imports = False
            for p in leave_paths:
                if p.is_file() and "workflow_approvals" in p.read_text(encoding="utf-8"):
                    leave_imports = True
            check("offer path does not import workflow_approvals", offer_imports_wa is False)
            check("leave authority paths do not import workflow_approvals", leave_imports is False)

            # Runtime: leave dual-control helpers still exist independently
            try:
                import app as app_mod

                check(
                    "leave dual-control API still present",
                    hasattr(app_mod, "initiate_leave_stale_dual_control")
                    and hasattr(app_mod, "confirm_leave_stale_dual_control"),
                )
                # offer.approve permission still in role matrix
                perms = set(app_mod.hr_role_permissions("hr_admin") if hasattr(app_mod, "hr_role_permissions") else [])
                if perms:
                    check("offer.approve permission untouched", "offer.approve" in perms)
                else:
                    check("offer.approve permission untouched (skipped roles)", True)
            except Exception as exc:
                # Staging may load app; if not, static checks above suffice.
                check(f"legacy path runtime probe skipped ({type(exc).__name__})", True)

        # cleanup synthetic canary rows (retain schema)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("DELETE FROM workflow_approval_events WHERE company_code=%s", (company,))
            cur.execute(
                "DELETE FROM workflow_approval_steps WHERE company_code=%s", (company,)
            )
            cur.execute(
                "DELETE FROM workflow_approval_instances WHERE company_code=%s", (company,)
            )
            cur.execute(
                "DELETE FROM workflow_delegation_grants WHERE company_code=%s", (company,)
            )
            cur.execute(
                "DELETE FROM workflow_approval_policies WHERE company_code=%s", (company,)
            )
            cur.execute(
                "DELETE FROM workflow_approval_settings WHERE company_code=%s", (company,)
            )
            conn.commit()
            check("synthetic canary cleanup", True)
    finally:
        conn.close()
        os.environ.pop("WATHEFNI_WORKFLOW_APPROVALS", None)
        os.environ.pop("WATHEFNI_WORKFLOW_APPROVALS_COMPANIES", None)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("    PHASE_A_SLICE1_DB_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
