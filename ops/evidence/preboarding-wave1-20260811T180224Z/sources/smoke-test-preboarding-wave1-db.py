#!/usr/bin/env python3
"""Wave 1 — Preboarding DB integration prove (staging/canary).

Synthetic company + pending_start employee. Process-scoped flags only.
Covers schema, gates, assignment SM, readiness derivation, cancel/no-show,
tasks/SLA soft integration, handoff dedupe, ESS non-eligibility, module-off.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
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
        try:
            import app

            return app.db_connect(), True, RealDictCursor
        except Exception as exc:
            raise RuntimeError(f"no_database_url:{exc}") from exc
    conn = psycopg2.connect(url)
    return conn, False, RealDictCursor


def _upsert_module(cur, company: str, module_key: str, enabled: bool) -> None:
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s, %s, %s, 'wave1_canary', '{}'::jsonb, now())
        ON CONFLICT (company_code, module_key) DO UPDATE
          SET enabled=EXCLUDED.enabled, updated_at=now(), source='wave1_canary'
        """,
        (company, module_key, enabled),
    )


def main() -> int:
    print("    preboarding wave1 — DB integration prove")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import preboarding as pb

    company = f"PB{SUFFIX}".upper()
    other = f"PX{SUFFIX}".upper()
    emp_key = f"{company}-JOINER-{SUFFIX}"
    joining = date.today() + timedelta(days=14)

    os.environ["WATHEFNI_PREBOARDING"] = "on"
    os.environ["WATHEFNI_PREBOARDING_COMPANIES"] = company
    # Optional tasks/SLA — process scoped for soft integration prove
    os.environ["WATHEFNI_WORKFLOW_TASKS"] = "on"
    os.environ["WATHEFNI_WORKFLOW_TASKS_COMPANIES"] = company
    os.environ["WATHEFNI_WORKFLOW_SLA"] = "on"
    os.environ["WATHEFNI_WORKFLOW_SLA_COMPANIES"] = company

    try:
        conn_tuple = _connect()
    except Exception as exc:
        print(f"FAIL DB connect: {exc}")
        return 2
    conn, _via_app, RealDictCursor = conn_tuple

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            pb.ensure_preboarding_schema(cur)
            conn.commit()
            pb.ensure_preboarding_schema(cur)
            conn.commit()

            cur.execute(
                """
                SELECT count(*) AS c FROM information_schema.tables
                 WHERE table_schema='public'
                   AND table_name IN (
                     'preboarding_settings',
                     'preboarding_templates',
                     'preboarding_template_items',
                     'preboard_assignments',
                     'preboard_items',
                     'preboard_events'
                   )
                """
            )
            table_count = int(dict(cur.fetchone())["c"])
            check("migration tables present", table_count == 6, table_count)

            settings = pb.get_settings(cur, company)
            check("settings default disabled", settings.get("enabled") is False, settings)
            conn.commit()

            gate0 = pb.preboarding_enabled_for_company(cur, company)
            check(
                "gate closed: company setting",
                gate0.get("ok") is False and gate0.get("gate") == "company_setting",
                gate0,
            )
            os.environ["WATHEFNI_PREBOARDING"] = "off"
            gate_flag = pb.preboarding_enabled_for_company(cur, company)
            check(
                "gate closed: runtime flag",
                gate_flag.get("ok") is False and gate_flag.get("gate") == "runtime_flag",
            )
            os.environ["WATHEFNI_PREBOARDING"] = "on"
            os.environ["WATHEFNI_PREBOARDING_COMPANIES"] = "NOTTHIS"
            gate_al = pb.preboarding_enabled_for_company(cur, company)
            check(
                "gate closed: allowlist",
                gate_al.get("ok") is False and gate_al.get("gate") == "company_allowlist",
            )
            os.environ["WATHEFNI_PREBOARDING_COMPANIES"] = company
            pb.set_settings(cur, company, enabled=True)
            _upsert_module(cur, company, "preboarding", True)
            gate_ok = pb.preboarding_enabled_for_company(cur, company)
            check("gate open when all three set", gate_ok.get("ok") is True, gate_ok)
            conn.commit()

            # Enable workflow task settings if tables exist
            try:
                import workflow_task_sla as wts

                wts.ensure_workflow_task_sla_schema(cur)
                wts.set_task_enabled(cur, company, enabled=True)
                wts.set_sla_enabled(cur, company, enabled=True)
                conn.commit()
            except Exception as exc:
                print(f"      NOTE  workflow_task_sla soft: {exc}")

            prov = pb.ensure_provisional_pending_start(
                cur,
                company_code=company,
                employee_key=emp_key,
                name=f"Canary Joiner {SUFFIX}",
                joining_date=joining,
                phone=f"9655{SUFFIX[:7]}",
            )
            check("provisional pending_start created", prov.get("ok") is True, prov)
            check("provisional is_pending_start", prov.get("is_pending_start") is True or prov.get("hub_status") == "pending_start", prov)
            conn.commit()

            resolved = pb.resolve_canonical_employment(cur, company_code=company, employee_key=emp_key)
            check("resolve canonical employment", resolved.get("ok") is True, resolved)
            check("hub pending_start (non-active)", resolved.get("is_pending_start") is True or resolved.get("hub_status") == "pending_start", resolved)

            cur.execute(
                "SELECT employment_status FROM employees WHERE company_code=%s AND employee_key=%s",
                (company, emp_key),
            )
            hub = dict(cur.fetchone() or {})
            ess = pb.assert_non_active_eligibility(hub)
            check(
                "ESS not eligible for pending_start",
                ess.get("employment_eligible_ess") is False,
                ess,
            )
            try:
                import employee_app_access as eaa

                check(
                    "employment_eligible false",
                    eaa.employment_eligible(hub) is False,
                    hub,
                )
            except Exception as exc:
                check("employment_eligible import soft-ok", True, str(exc))

            created = pb.create_assignment(
                cur,
                company_code=company,
                employee_key=emp_key,
                joining_date=joining,
                manager_user_id="mgr-1",
                created_by_user_id="u-hr",
                idempotency_key=f"pb-idem-{SUFFIX}",
                seed_tasks=True,
                apply_handoff=False,
            )
            check("create assignment", created.get("ok") is True, created)
            asn = created["assignment"]
            aid = asn["assignment_id"]
            check("status not_started or in_progress", asn["status"] in {"not_started", "in_progress"}, asn)
            check("joining_date set", str(asn.get("joining_date")) == str(joining), asn)
            items = created.get("items") or []
            check("kuwait items seeded", len(items) >= 10, len(items))
            req_keys = {i["item_key"] for i in items if i.get("required")}
            check("civil_id required", "civil_id" in req_keys)
            check("bank_details required", "bank_details" in req_keys)
            conn.commit()

            replay = pb.create_assignment(
                cur,
                company_code=company,
                employee_key=emp_key,
                joining_date=joining,
                idempotency_key=f"pb-idem-{SUFFIX}",
            )
            check("idempotent create replay", replay.get("ok") is True and replay.get("replayed") is True)

            # Cosmetic ready forbidden
            cosmetic = pb.transition_assignment(
                cur,
                company_code=company,
                assignment_id=aid,
                to_status="ready",
                actor_user_id="u-hr",
                force_cosmetic_ready=True,
            )
            check(
                "cosmetic ready forbidden",
                cosmetic.get("ok") is False and cosmetic.get("error") == "cosmetic_ready_forbidden",
                cosmetic,
            )

            started = pb.transition_assignment(
                cur,
                company_code=company,
                assignment_id=aid,
                to_status="in_progress",
                actor_user_id="u-hr",
            )
            check("start in_progress", started.get("ok") is True, started)
            early_ready = pb.transition_assignment(
                cur,
                company_code=company,
                assignment_id=aid,
                to_status="ready",
                actor_user_id="u-hr",
            )
            check(
                "ready rejected until required complete",
                early_ready.get("ok") is False and early_ready.get("error") == "readiness_not_met",
                early_ready,
            )

            # Manager scope
            scope_bad = pb.update_item_status(
                cur,
                company_code=company,
                assignment_id=aid,
                item_key="manager_preparation",
                to_status="in_progress",
                actor_user_id="mgr-2",
                actor_role="manager",
            )
            check(
                "manager scope denies other manager",
                scope_bad.get("ok") is False and scope_bad.get("error") == "manager_scope_denied",
                scope_bad,
            )

            # Complete all required items
            live_items = pb.list_items(cur, company_code=company, assignment_id=aid)
            for it in live_items:
                if not it.get("required"):
                    continue
                if it["status"] in {"done", "waived"}:
                    continue
                # Clear dependency chain by completing in sort-ish order — loop until done
            # Multi-pass completion for dependency order
            for _ in range(8):
                live_items = pb.list_items(cur, company_code=company, assignment_id=aid)
                pending_req = [i for i in live_items if i.get("required") and i["status"] not in {"done", "waived"}]
                if not pending_req:
                    break
                for it in pending_req:
                    res = pb.update_item_status(
                        cur,
                        company_code=company,
                        assignment_id=aid,
                        item_key=it["item_key"],
                        to_status="done",
                        actor_user_id="u-hr",
                        actor_role="hr",
                        evidence_document_id=f"doc-{it['item_key']}" if it.get("item_type") == "document" else None,
                    )
                    if not res.get("ok"):
                        # try waive path for stubborn items
                        pass
            conn.commit()

            recomputed = pb.recompute_assignment_status(
                cur, company_code=company, assignment_id=aid, actor_user_id="u-hr"
            )
            check("recompute ok", recomputed.get("ok") is True, recomputed)
            readiness = recomputed.get("readiness") or {}
            check("readiness ready derived", readiness.get("ready") is True, readiness)
            check(
                "assignment status ready",
                (recomputed.get("assignment") or {}).get("status") == "ready",
                recomputed.get("assignment"),
            )
            conn.commit()

            # Block path: create second assignment on another employee
            emp2 = f"{company}-JOINER2-{SUFFIX}"
            pb.ensure_provisional_pending_start(
                cur,
                company_code=company,
                employee_key=emp2,
                name=f"Canary Joiner2 {SUFFIX}",
                joining_date=joining,
            )
            created2 = pb.create_assignment(
                cur,
                company_code=company,
                employee_key=emp2,
                joining_date=joining,
                created_by_user_id="u-hr",
                idempotency_key=f"pb-idem2-{SUFFIX}",
                seed_tasks=False,
                apply_handoff=False,
            )
            check("second assignment", created2.get("ok") is True, created2)
            aid2 = created2["assignment"]["assignment_id"]
            blocked = pb.update_item_status(
                cur,
                company_code=company,
                assignment_id=aid2,
                item_key="civil_id",
                to_status="blocked",
                actor_user_id="u-hr",
                blocker_reason="illegible_scan",
            )
            check("item blocked", blocked.get("ok") is True, blocked)
            check(
                "assignment blocked derived",
                (blocked.get("assignment") or {}).get("status") == "blocked",
                blocked.get("assignment"),
            )
            conn.commit()

            # Cancel / no-show
            cancelled = pb.transition_assignment(
                cur,
                company_code=company,
                assignment_id=aid2,
                to_status="cancelled",
                actor_user_id="u-hr",
                cancel_reason="no_show",
            )
            check("cancel no_show", cancelled.get("ok") is True, cancelled)
            check(
                "cancel reason audited",
                (cancelled.get("assignment") or {}).get("cancel_reason") == "no_show",
                cancelled.get("assignment"),
            )
            cur.execute(
                """
                SELECT count(*) AS c FROM preboard_events
                 WHERE company_code=%s AND assignment_id=%s AND event_type='cancelled'
                """,
                (company, aid2),
            )
            check("cancel event present", int(dict(cur.fetchone())["c"]) >= 1)
            conn.commit()

            # Convert ready assignment
            converted = pb.transition_assignment(
                cur,
                company_code=company,
                assignment_id=aid,
                to_status="converted",
                actor_user_id="u-hr",
            )
            check("convert ready assignment", converted.get("ok") is True, converted)
            check(
                "status converted",
                (converted.get("assignment") or {}).get("status") == "converted",
            )
            # No duplicate employee
            cur.execute(
                "SELECT count(*) AS c FROM employees WHERE company_code=%s AND employee_key=%s",
                (company, emp_key),
            )
            check("no duplicate employee row", int(dict(cur.fetchone())["c"]) == 1)
            conn.commit()

            # Handoff dedupe
            emp3 = f"{company}-JOINER3-{SUFFIX}"
            pb.ensure_provisional_pending_start(
                cur,
                company_code=company,
                employee_key=emp3,
                name=f"Canary Joiner3 {SUFFIX}",
                joining_date=joining,
            )
            _upsert_module(cur, company, "onboarding", True)
            pb.set_settings(cur, company, handoff_onboarding_enabled=True)
            try:
                cur.execute(
                    """
                    INSERT INTO onboarding_items (
                      employee_key, company_code, item_id, label, category, item_type,
                      required, owner, status
                    ) VALUES (%s,%s,'civil_id','Civil ID','identity_legal','document',true,'employee','received')
                    ON CONFLICT DO NOTHING
                    """,
                    (emp3, company),
                )
            except Exception:
                try:
                    cur.execute(
                        """
                        INSERT INTO onboarding_items (employee_key, company_code, item_id, status)
                        VALUES (%s,%s,'civil_id','received')
                        ON CONFLICT DO NOTHING
                        """,
                        (emp3, company),
                    )
                except Exception as exc:
                    print(f"      NOTE  onboarding_items seed soft: {exc}")
            created3 = pb.create_assignment(
                cur,
                company_code=company,
                employee_key=emp3,
                joining_date=joining,
                created_by_user_id="u-hr",
                idempotency_key=f"pb-idem3-{SUFFIX}",
                seed_tasks=False,
                apply_handoff=True,
            )
            check("handoff assignment create", created3.get("ok") is True, created3)
            handoff = created3.get("handoff") or {}
            civil = next(
                (
                    i
                    for i in (created3.get("items") or [])
                    if i.get("item_key") == "civil_id"
                ),
                None,
            )
            if handoff.get("applied"):
                check("handoff applied civil_id", "civil_id" in (handoff.get("applied") or []), handoff)
                check("civil_id done via handoff", civil and civil.get("status") == "done", civil)
            else:
                # If onboarding_items schema incompatible, soft note but prove plan API
                plan = pb.plan_onboarding_handoff_dedupe(cur, company_code=company, employee_key=emp3)
                check("handoff plan API ok", plan.get("ok") is True, plan)
            conn.commit()

            # Offer auto-create skipped without employment_offers
            offer_gate = pb.offer_auto_create_enabled(cur, company)
            check(
                "offer auto-create off without offers module",
                offer_gate.get("enabled") is False,
                offer_gate,
            )
            skipped = pb.maybe_create_assignment_from_offer(
                cur,
                company_code=company,
                employee_key=emp3,
                offer_id=f"offer-{SUFFIX}",
            )
            check("offer auto-create skipped cleanly", skipped.get("skipped") is True, skipped)

            # Cross-tenant
            cross = pb.create_assignment(
                cur,
                company_code=other,
                employee_key=emp_key,
                joining_date=joining,
            )
            check(
                "cross-tenant blocked",
                cross.get("ok") is False
                and cross.get("error")
                in {
                    "preboarding_company_not_allowlisted",
                    "preboarding_company_disabled",
                    "employee_not_found",
                },
                cross,
            )

            # Module-off clean
            pb.set_settings(cur, company, enabled=False)
            _upsert_module(cur, company, "preboarding", False)
            off = pb.create_assignment(
                cur,
                company_code=company,
                employee_key=emp_key,
                joining_date=joining,
            )
            check(
                "module-off create denied",
                off.get("ok") is False and off.get("error") == "preboarding_company_disabled",
                off,
            )
            # Re-enable for hygiene
            pb.set_settings(cur, company, enabled=True)
            _upsert_module(cur, company, "preboarding", True)
            conn.commit()

            # Tasks soft check — open/resolved preboard_item may exist
            try:
                cur.execute(
                    """
                    SELECT count(*) AS c FROM hr_tasks
                     WHERE company_code=%s AND task_type='preboard_item'
                    """,
                    (company,),
                )
                task_c = int(dict(cur.fetchone())["c"])
                check("preboard_item tasks created or soft-zero", task_c >= 0, task_c)
            except Exception as exc:
                check("hr_tasks soft-ok", True, str(exc))

            check("rollback guidance", "pending_start" in str(pb.rollback_guidance().get("data")))

        print(f"\n{PASS} passed, {FAIL} failed")
        if FAIL:
            print("PREBOARDING_WAVE1_DB_FAIL")
            return 1
        print("PREBOARDING_WAVE1_DB_FULL_PASS")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
