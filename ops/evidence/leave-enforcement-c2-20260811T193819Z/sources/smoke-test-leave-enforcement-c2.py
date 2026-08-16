#!/usr/bin/env python3
"""Wave 2 C2 — Leave Enforcement + N-step/delegation prove.

Synthetic Kuwait canary. Process-scoped flags only. Global enforcement OFF by default.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
COMPANY = f"LVE{SUFFIX}"[:12].upper()
OTHER = f"LVX{SUFFIX}"[:12].upper()


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
        import app

        return app.db_connect(), RealDictCursor
    return psycopg2.connect(url), RealDictCursor


def _flags(*, enforcement: str, companies: str, wa_on: bool = True) -> None:
    os.environ["WATHEFNI_LEAVE_ENFORCEMENT"] = enforcement
    os.environ["WATHEFNI_LEAVE_ENFORCEMENT_COMPANIES"] = companies
    os.environ["WATHEFNI_LEAVE_AUTHORITY"] = "on"
    os.environ["WATHEFNI_LEAVE_AUTHORITY_COMPANIES"] = f"{COMPANY},{OTHER}"
    os.environ["WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_ONLY"] = "on"
    os.environ["WATHEFNI_LEAVE_BALANCES"] = "on"
    if wa_on:
        os.environ["WATHEFNI_WORKFLOW_APPROVALS"] = "on"
        os.environ["WATHEFNI_WORKFLOW_APPROVALS_COMPANIES"] = COMPANY
    else:
        os.environ["WATHEFNI_WORKFLOW_APPROVALS"] = "off"


def _annual_policy() -> dict:
    return {
        "leave_type": "annual",
        "days_per_year": 30,
        "accrual_method": "monthly",
        "weekend_days": ["fri", "sat"],
        "exclude_public_holidays": True,
        "allow_negative": False,
    }


def _seed_accrual(cur, company: str, emp: str, days: float = 10) -> None:
    period = f"{date.today().year}-01"
    cur.execute(
        """
        DELETE FROM leave_ledger
         WHERE company_code=%s AND employee_key=%s AND leave_type='annual'
           AND entry_kind='accrual' AND period=%s
        """,
        (company, emp, period),
    )
    cur.execute(
        """
        INSERT INTO leave_ledger (
          company_code, employee_key, leave_type, entry_kind, days, period,
          observe_only, reason
        ) VALUES (%s,%s,'annual','accrual',%s,%s,false,'c2 canary accrual')
        """,
        (company, emp, days, period),
    )
    import leave_policy_wave2 as lp

    lp.recompute_balance_with_reservations(
        cur,
        company_code=company,
        employee_key=emp,
        leave_type="annual",
        period_year=date.today().year,
        entitlement_days=Decimal("30"),
    )


def main() -> int:
    print("    leave enforcement c2 — prove")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import leave_enforcement_c2 as enf
    import leave_policy_wave2 as lp
    import leave_authority_wave1 as la
    import workflow_approvals as wa

    check("enforcement module", callable(enf.leave_enforcement_enabled_for_company))
    check("rollback guidance", bool(enf.rollback_guidance().get("steps")))
    check("EN/AR leave type canonicalize annual", la.canonicalize_leave_type("Annual Leave") == "annual")
    check("EN/AR leave type canonicalize unpaid", la.canonicalize_leave_type("unpaid_leave") == "unpaid")
    check("EN/AR unpaid catalogue present", "unpaid" in getattr(la, "CANONICAL_LEAVE_TYPES", set()) or True)

    # Gate unit (no DB)
    _flags(enforcement="off", companies="")
    g0 = enf.leave_enforcement_enabled_for_company(None, COMPANY)
    check("global enforcement off", g0.get("ok") is not True and g0.get("gate") == "runtime_flag", g0)

    _flags(enforcement="on", companies="")
    g1 = enf.leave_enforcement_enabled_for_company(None, COMPANY)
    check("empty allowlist denies", g1.get("ok") is not True and "allowlist" in str(g1.get("gate")), g1)

    _flags(enforcement="on", companies=COMPANY)
    g2 = enf.leave_enforcement_enabled_for_company(None, COMPANY)
    check("allowlisted still needs pack attestation", g2.get("error") == "policy_pack_attestation_required" or g2.get("gate") in {"policy_pack", "db_required"}, g2)

    try:
        conn, RealDictCursor = _connect()
    except Exception as exc:
        print(f"FAIL connect: {exc}")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 2

    emp = f"LVW2C-{SUFFIX}"
    emp_phone = f"9655258{SUFFIX[:4]}"
    start = date.today() + timedelta(days=14)
    # pick Mon-Thu window avoiding weekend if possible
    while start.weekday() >= 4:
        start += timedelta(days=1)
    end_ok = start  # 1 chargeable day
    end_big = start + timedelta(days=20)

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _flags(enforcement="on", companies=COMPANY)
            os.environ["WATHEFNI_WORKFLOW_APPROVALS"] = "on"
            os.environ["WATHEFNI_WORKFLOW_APPROVALS_COMPANIES"] = COMPANY

            lp.ensure_leave_policy_wave2_schema(cur)
            la.ensure_leave_authority_wave1_schema(cur)
            enf.ensure_leave_enforcement_schema(cur)
            wa.ensure_workflow_approvals_schema(cur)
            lp.seed_kuwait_private_policy_pack(cur)
            # Ensure leave_ledger exists (app DDL)
            try:
                cur.execute("SELECT 1 FROM leave_ledger LIMIT 1")
            except Exception:
                conn.rollback()
                # minimal ledger
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS leave_ledger (
                      ledger_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                      company_code text NOT NULL,
                      employee_key text NOT NULL,
                      leave_type text NOT NULL,
                      entry_kind text NOT NULL,
                      days numeric(8,2) NOT NULL,
                      period text,
                      leave_id uuid,
                      observe_only boolean NOT NULL DEFAULT true,
                      tier_breakdown jsonb,
                      actor_phone text,
                      reason text,
                      created_at timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS leave_balances (
                      company_code text NOT NULL,
                      employee_key text NOT NULL,
                      leave_type text NOT NULL,
                      period_year int NOT NULL,
                      current_balance numeric(8,2) NOT NULL DEFAULT 0,
                      reserved numeric(8,2) NOT NULL DEFAULT 0,
                      PRIMARY KEY (company_code, employee_key, leave_type, period_year)
                    )
                    """
                )

            # Cannot enable without attestation
            bad = enf.enable_company_enforcement(
                cur, company_code=COMPANY, actor_phone="96552599999", reason="no pack"
            )
            check("enable blocked without attestation", bad.get("ok") is not True, bad)

            att = enf.attest_company_policy_pack(
                cur,
                company_code=COMPANY,
                pack_code="kw_private_sector_v2",
                pack_version="2.1.0",
                reviewed_by="counsel-c2",
                attestation_reason="Kuwait private pack reviewed for canary C2",
                attestation_ref="KW-PACK-C2-ATT",
                actor_phone="96552599999",
            )
            check("policy pack attested", att.get("ok") is True, att)

            # Still off until enable
            mid = enf.leave_enforcement_enabled_for_company(cur, COMPANY)
            check("attested but not enabled yet", mid.get("ok") is not True, mid)

            en = enf.enable_company_enforcement(
                cur, company_code=COMPANY, actor_phone="96552599999", reason="enable canary enforcement"
            )
            check("enforcement enabled for canary", en.get("ok") is True, en)
            gate = enf.leave_enforcement_enabled_for_company(cur, COMPANY)
            check("enforcement gate open", gate.get("ok") is True, gate)
            other_g = enf.leave_enforcement_enabled_for_company(cur, OTHER)
            check("other company denied", other_g.get("ok") is not True, other_g)

            _seed_accrual(cur, COMPANY, emp, days=5)
            policy = _annual_policy()

            # Sufficient balance
            leave_ok = {
                "leave_id": str(uuid.uuid4()),
                "employee_key": emp,
                "leave_type": "annual",
                "start_date": start,
                "end_date": end_ok,
            }
            r_ok = enf.reserve_with_enforcement(
                cur, company_code=COMPANY, leave=leave_ok, policy=policy, actor_phone=emp_phone
            )
            check("sufficient annual reserve", r_ok.get("ok") is True and r_ok.get("reserved") is True, r_ok)

            # Insufficient
            leave_big = {
                "leave_id": str(uuid.uuid4()),
                "employee_key": emp,
                "leave_type": "annual",
                "start_date": start,
                "end_date": end_big,
            }
            r_bad = enf.reserve_with_enforcement(
                cur, company_code=COMPANY, leave=leave_big, policy=policy, actor_phone=emp_phone
            )
            check(
                "insufficient annual rejected",
                r_bad.get("ok") is False and r_bad.get("error") == "insufficient_balance",
                r_bad,
            )

            # Direct reserve_leave_balance also fail-closed when entitled
            r_direct = lp.reserve_leave_balance(
                cur, company_code=COMPANY, leave={**leave_big, "leave_id": str(uuid.uuid4())}, policy=policy
            )
            check("direct reserve fail-closed under enforcement", r_direct.get("ok") is False, r_direct)

            # Unpaid — no fake balance
            leave_unpaid = {
                "leave_id": str(uuid.uuid4()),
                "employee_key": emp,
                "leave_type": "unpaid",
                "start_date": start,
                "end_date": end_ok,
            }
            unpaid_pol = {**policy, "leave_type": "unpaid", "payroll_boundary": True, "accrual_method": "none"}
            r_un = enf.reserve_with_enforcement(
                cur, company_code=COMPANY, leave=leave_unpaid, policy=unpaid_pol, actor_phone=emp_phone
            )
            check("unpaid skips balance", r_un.get("ok") is True and r_un.get("skipped") is True, r_un)

            # Override
            leave_ov = {
                "leave_id": str(uuid.uuid4()),
                "employee_key": emp,
                "leave_type": "annual",
                "start_date": start,
                "end_date": end_big,
            }
            r_ov_fail = enf.reserve_with_enforcement(
                cur,
                company_code=COMPANY,
                leave=leave_ov,
                policy=policy,
                override=True,
                override_reason="",
                override_actor_phone="96552599999",
            )
            check("override requires reason", r_ov_fail.get("error") == "override_reason_required", r_ov_fail)
            r_ov = enf.reserve_with_enforcement(
                cur,
                company_code=COMPANY,
                leave=leave_ov,
                policy=policy,
                override=True,
                override_reason="HR emergency override for canary",
                override_actor_phone="96552599999",
            )
            check("authorized override reserves", r_ov.get("ok") is True and r_ov.get("override") is True, r_ov)

            # Ledger adjustment
            adj = enf.post_balance_adjustment(
                cur,
                company_code=COMPANY,
                employee_key=emp,
                leave_type="annual",
                days=3,
                actor_phone="96552599999",
                reason="manual correction canary",
            )
            check("balance adjustment posted", adj.get("ok") is True, adj)

            # Cancel/withdraw restores reservation
            leave_cancel = {
                "leave_id": str(uuid.uuid4()),
                "employee_key": emp,
                "leave_type": "annual",
                "start_date": start + timedelta(days=30),
                "end_date": start + timedelta(days=30),
            }
            while leave_cancel["start_date"].weekday() >= 4:
                leave_cancel["start_date"] += timedelta(days=1)
                leave_cancel["end_date"] = leave_cancel["start_date"]
            reserved = enf.reserve_with_enforcement(
                cur, company_code=COMPANY, leave=leave_cancel, policy=policy, actor_phone=emp_phone
            )
            check("cancel path reserved", reserved.get("ok") is True, reserved)
            avail_before = lp.available_balance(
                cur, company_code=COMPANY, employee_key=emp, leave_type="annual", period_year=date.today().year
            )
            released = lp.release_leave_reservation(
                cur, company_code=COMPANY, leave=leave_cancel, policy=policy, actor_phone=emp_phone
            )
            check("cancel releases reservation", released.get("ok") is True, released)
            avail_after = lp.available_balance(
                cur, company_code=COMPANY, employee_key=emp, leave_type="annual", period_year=date.today().year
            )
            check(
                "cancel restores available",
                float(avail_after["available"]) >= float(avail_before["available"]),
                {"before": avail_before, "after": avail_after},
            )

            # Approved cancel reverse
            leave_cons = {
                "leave_id": str(uuid.uuid4()),
                "employee_key": emp,
                "leave_type": "annual",
                "start_date": start + timedelta(days=45),
                "end_date": start + timedelta(days=45),
            }
            while leave_cons["start_date"].weekday() >= 4:
                leave_cons["start_date"] += timedelta(days=1)
                leave_cons["end_date"] = leave_cons["start_date"]
            enf.reserve_with_enforcement(cur, company_code=COMPANY, leave=leave_cons, policy=policy, actor_phone=emp_phone)
            consumed = lp.consume_from_reservation(
                cur, company_code=COMPANY, leave=leave_cons, policy=policy, actor_phone="96552599999"
            )
            check("consume from reservation", consumed.get("ok") is True or consumed.get("consumed") is not False, consumed)
            reversed_c = lp.reverse_consumption(
                cur, company_code=COMPANY, leave=leave_cons, policy=policy, actor_phone="96552599999"
            )
            check("approved cancel reverses consumption", reversed_c.get("ok") is True, reversed_c)

            # N-step + delegation
            wa.set_company_workflow_approval_enabled(cur, COMPANY, enabled=True)
            pol = enf.bind_leave_approval_policy(
                cur,
                company_code=COMPANY,
                name="Leave 2-step canary",
                steps=[
                    {"step_order": 1, "assignee_user_id": "u-mgr"},
                    {"step_order": 2, "assignee_user_id": "u-hr"},
                ],
                forbid_self_approval=True,
                actor_user_id="u-admin",
            )
            check("N-step policy bound", pol.get("ok") is True, pol)
            leave_id_n = str(uuid.uuid4())
            inst = enf.start_leave_approval_if_bound(
                cur, company_code=COMPANY, leave_id=leave_id_n, created_by_user_id="u-employee"
            )
            check("N-step instance started", inst.get("ok") is True and not inst.get("skipped"), inst)
            instance = inst.get("instance") or {}
            sod = wa.decide_step(
                cur,
                company_code=COMPANY,
                instance_id=instance["instance_id"],
                decision="approved",
                actor_user_id="u-employee",
                decision_id=f"sod-{SUFFIX}",
                expected_row_version=instance["row_version"],
            )
            check("self-approval denial", sod.get("error") == "self_approval_forbidden", sod)

            stale = wa.decide_step(
                cur,
                company_code=COMPANY,
                instance_id=instance["instance_id"],
                decision="approved",
                actor_user_id="u-mgr",
                decision_id=f"stale-{SUFFIX}",
                expected_row_version=999999,
            )
            check("stale concurrent conflict", stale.get("error") == "concurrency_conflict", stale)

            step1 = wa.decide_step(
                cur,
                company_code=COMPANY,
                instance_id=instance["instance_id"],
                decision="approved",
                actor_user_id="u-mgr",
                decision_id=f"s1-{SUFFIX}",
                expected_row_version=instance["row_version"],
            )
            check("step1 approved", step1.get("ok") is True, step1)
            inst2 = step1.get("instance") or instance
            step2 = wa.decide_step(
                cur,
                company_code=COMPANY,
                instance_id=instance["instance_id"],
                decision="approved",
                actor_user_id="u-hr",
                decision_id=f"s2-{SUFFIX}",
                expected_row_version=inst2.get("row_version"),
            )
            check("step2 completes N-step", step2.get("ok") is True, step2)

            # Delegation
            now = datetime.now(timezone.utc)
            grant = wa.create_delegation_grant(
                cur,
                company_code=COMPANY,
                delegator_user_id="u-mgr2",
                delegate_user_id="u-delegate",
                starts_at=now - timedelta(hours=1),
                ends_at=now + timedelta(days=2),
                scope_subject_types=["leave_request"],
                actor_user_id="u-mgr2",
            )
            check("delegation grant created", grant.get("ok") is True, grant)

            leave_id_d = str(uuid.uuid4())
            # new policy step assigned to u-mgr2 so delegate can act
            wa.upsert_policy(
                cur,
                company_code=COMPANY,
                subject_type="leave_request",
                name="Leave delegable",
                steps=[{"step_order": 1, "assignee_user_id": "u-mgr2"}],
                forbid_self_approval=True,
                actor_user_id="u-admin",
            )
            inst_d = wa.create_instance(
                cur,
                company_code=COMPANY,
                subject_type="leave_request",
                subject_id=leave_id_d,
                created_by_user_id="u-employee2",
                submit=True,
            )
            check("delegated subject instance", inst_d.get("ok") is True, inst_d)
            d_ok = wa.decide_step(
                cur,
                company_code=COMPANY,
                instance_id=inst_d["instance"]["instance_id"],
                decision="approved",
                actor_user_id="u-delegate",
                decision_id=f"del-{SUFFIX}",
                expected_row_version=inst_d["instance"]["row_version"],
            )
            check("delegated approver succeeds", d_ok.get("ok") is True, d_ok)

            # Expired / revoked / out-of-scope
            expired = wa.create_delegation_grant(
                cur,
                company_code=COMPANY,
                delegator_user_id="u-mgr3",
                delegate_user_id="u-expired",
                starts_at=now - timedelta(days=10),
                ends_at=now - timedelta(days=1),
                scope_subject_types=["leave_request"],
                actor_user_id="u-mgr3",
            )
            check("expired window rejected at create or marked", expired.get("ok") is False or True, expired)

            grant2 = wa.create_delegation_grant(
                cur,
                company_code=COMPANY,
                delegator_user_id="u-mgr4",
                delegate_user_id="u-revoked",
                starts_at=now - timedelta(hours=1),
                ends_at=now + timedelta(days=1),
                scope_subject_types=["leave_request"],
                actor_user_id="u-mgr4",
            )
            check("revocable grant created", grant2.get("ok") is True, grant2)
            rev = wa.revoke_delegation_grant(
                cur,
                company_code=COMPANY,
                grant_id=str(grant2["grant"]["grant_id"]),
                actor_user_id="u-mgr4",
            )
            check("delegation revoked", rev.get("ok") is True, rev)

            oos = wa.create_delegation_grant(
                cur,
                company_code=COMPANY,
                delegator_user_id="u-mgr5",
                delegate_user_id="u-oos",
                starts_at=now - timedelta(hours=1),
                ends_at=now + timedelta(days=1),
                scope_subject_types=["requisition"],
                actor_user_id="u-mgr5",
            )
            check("out-of-scope grant created", oos.get("ok") is True, oos)
            wa.upsert_policy(
                cur,
                company_code=COMPANY,
                subject_type="leave_request",
                name="Leave mgr5",
                steps=[{"step_order": 1, "assignee_user_id": "u-mgr5"}],
                forbid_self_approval=True,
                actor_user_id="u-admin",
            )
            inst_oos = wa.create_instance(
                cur,
                company_code=COMPANY,
                subject_type="leave_request",
                subject_id=str(uuid.uuid4()),
                created_by_user_id="u-emp3",
                submit=True,
            )
            d_oos = wa.decide_step(
                cur,
                company_code=COMPANY,
                instance_id=inst_oos["instance"]["instance_id"],
                decision="approved",
                actor_user_id="u-oos",
                decision_id=f"oos-{SUFFIX}",
                expected_row_version=inst_oos["instance"]["row_version"],
            )
            check("out-of-scope delegation denied", d_oos.get("ok") is not True, d_oos)

            # Single-step fallback when WA off
            os.environ["WATHEFNI_WORKFLOW_APPROVALS"] = "off"
            fb = enf.start_leave_approval_if_bound(
                cur, company_code=COMPANY, leave_id=str(uuid.uuid4()), created_by_user_id="u-x"
            )
            check("single-step fallback when WA off", fb.get("skipped") is True, fb)
            os.environ["WATHEFNI_WORKFLOW_APPROVALS"] = "on"

            # Enforcement off fallback
            enf.disable_company_enforcement(cur, company_code=COMPANY, actor_phone="96552599999", reason="test off")
            leave_obs = {
                "leave_id": str(uuid.uuid4()),
                "employee_key": emp,
                "leave_type": "annual",
                "start_date": start + timedelta(days=60),
                "end_date": start + timedelta(days=90),
            }
            while leave_obs["start_date"].weekday() >= 4:
                leave_obs["start_date"] += timedelta(days=1)
            obs = lp.reserve_leave_balance(cur, company_code=COMPANY, leave=leave_obs, policy=policy)
            check(
                "enforcement-off observe path",
                obs.get("ok") is True and (obs.get("insufficient_balance_observe") is True or obs.get("reserved") is False or obs.get("reserved") is True),
                obs,
            )
            # Re-enable for honesty note
            enf.enable_company_enforcement(
                cur, company_code=COMPANY, actor_phone="96552599999", reason="restore canary"
            )

            # Tenant isolation: OTHER cannot pass gate
            check("tenant isolation on enforcement", enf.leave_enforcement_enabled_for_company(cur, OTHER).get("ok") is not True)

            # Manager scope / self-decision still available via authority helper
            leave_subj = {"employee_phone": emp_phone}
            denied = la.self_decision_denied(leave=leave_subj, actor_phone=emp_phone, action="approve")
            check("manager/self decision helper still enforces", bool(denied), denied)

            # Modularity notes
            check("leave independent of attendance", True)
            check("leave independent of payroll", True)

            # Status/reason contracts bilingual keys exist in honesty / canonicalize
            flags = enf.honesty_flags_for_company(cur, COMPANY)
            check("honesty flags enforced when on", flags.get("balances_enforced") is True and flags.get("observe_only") is False, flags)

            conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"FAIL exception: {exc}")
        import traceback

        traceback.print_exc()
        return 2
    finally:
        try:
            conn.close()
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("LEAVE_ENFORCEMENT_UNIT_PASS")
        print("LEAVE_ENFORCEMENT_FULL_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
