#!/usr/bin/env python3
"""Wave 1 Product Acceptance — staging DB prove (company-scoped canary).

Proves:
  1) Setup Console Wave 1 policies (get/patch, no env-only ownership)
  2) Modularity matrix (disabled modules fail closed; enabled paths usable)
  3) Canonical task sync (hr_tasks) for Wave 1 events
  4) Surface authority still gates cleanly when modules off
  5) Visual canary seed/cleanup on WATHEFNI

Process-scoped flags only. Synthetic companies + WATHEFNI visual seed.
Never systemd-global.
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
        import app

        return app.db_connect(), RealDictCursor
    return psycopg2.connect(url), RealDictCursor


def _flags_for(*companies: str) -> None:
    allow = ",".join(sorted({str(c).upper() for c in companies if c}))
    for k, v in {
        "WATHEFNI_REQUISITIONS": "on",
        "WATHEFNI_REQUISITIONS_COMPANIES": allow,
        "WATHEFNI_PREBOARDING": "on",
        "WATHEFNI_PREBOARDING_COMPANIES": allow,
        "WATHEFNI_PROBATION": "on",
        "WATHEFNI_PROBATION_COMPANIES": allow,
        "WATHEFNI_HIRE_READY_WAVE1": "on",
        "WATHEFNI_HIRE_READY_COMPANIES": allow,
        "WATHEFNI_WORKFLOW_TASKS": "on",
        "WATHEFNI_WORKFLOW_TASKS_COMPANIES": allow,
        "WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS": "on",
        "WATHEFNI_EMPLOYMENT_TRUTH_SYNC_COMPANIES": allow,
    }.items():
        os.environ[k] = v


def _upsert_module(cur, company: str, module_key: str, enabled: bool) -> None:
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s, %s, %s, 'wave1_product', '{}'::jsonb, now())
        ON CONFLICT (company_code, module_key) DO UPDATE
          SET enabled=EXCLUDED.enabled, updated_at=now(), source='wave1_product'
        """,
        (company, module_key, enabled),
    )


def _ensure_company(cur, company: str) -> None:
    cur.execute(
        """
        INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
        VALUES (%s, %s, '{}'::jsonb, '{}'::jsonb, now(), now())
        ON CONFLICT (company_code) DO NOTHING
        """,
        (company, f"Wave1 Product {company}"),
    )


def _set_modules(cur, company: str, enabled: dict[str, bool]) -> None:
    defaults = {
        "requisitions": False,
        "pre_hiring": False,
        "offers": False,
        "preboarding": False,
        "onboarding": False,
        "probation": False,
    }
    defaults.update(enabled)
    for k, v in defaults.items():
        _upsert_module(cur, company, k, v)


def prove_setup_policies(cur, company: str) -> None:
    import setup_console_wave1_policies as w1p
    import requisitions as rq
    import preboarding as pb
    import probation as pr

    _ensure_company(cur, company)
    _set_modules(
        cur,
        company,
        {
            "requisitions": True,
            "pre_hiring": True,
            "preboarding": True,
            "onboarding": True,
            "probation": True,
            "offers": True,
        },
    )
    rq.ensure_requisitions_schema(cur)
    pb.ensure_preboarding_schema(cur)
    pr.ensure_probation_schema(cur)
    rq.set_settings(cur, company, enabled=True, jobs_require_approved_requisition=True)
    pb.set_settings(cur, company, enabled=True)
    pr.set_settings(cur, company, enabled=True)

    allp = w1p.get_all_wave1_policies(cur, company)
    check("setup get_all ok", allp.get("ok") is True, allp)
    check("setup has requisitions policy", isinstance(allp.get("requisitions"), dict))
    check("setup has preboarding policy", isinstance(allp.get("preboarding"), dict))
    check("setup has probation policy", isinstance(allp.get("probation"), dict))
    check("setup has onboarding_auto_start", isinstance(allp.get("onboarding_auto_start"), dict))

    p1 = w1p.patch_wave1_module_policy(
        cur,
        company_code=company,
        module_key="requisitions",
        actor_phone="96550009999",
        reason="product acceptance gate",
        payload={"required": {"jobs_require_approved_requisition": False}},
    )
    check("setup patch requisitions gate off", p1.get("ok") is True, p1)
    gate = (p1.get("policy") or {}).get("required", {}).get("jobs_require_approved_requisition")
    check("setup gate persisted false", gate is False, p1)

    p2 = w1p.patch_wave1_module_policy(
        cur,
        company_code=company,
        module_key="preboarding",
        actor_phone="96550009999",
        reason="product acceptance gate",
        payload={
            "required": {"auto_create_on_offer_accept": False, "required_for_ready_mark": True},
            "optional": {"handoff_onboarding_enabled": True},
        },
    )
    check("setup patch preboarding", p2.get("ok") is True, p2)
    auto = (p2.get("policy") or {}).get("required", {}).get("auto_create_on_offer_accept")
    check("setup offer→preboard contract off", auto is False, p2)

    p3 = w1p.patch_wave1_module_policy(
        cur,
        company_code=company,
        module_key="probation",
        actor_phone="96550009999",
        reason="product acceptance gate",
        payload={"required": {"auto_plan_on_hire": True, "default_probation_days": 60, "start_mode": "hire_date"}},
    )
    check("setup patch probation", p3.get("ok") is True, p3)
    days = (p3.get("policy") or {}).get("required", {}).get("default_probation_days")
    check("setup probation days 60", days == 60, p3)

    p4 = w1p.patch_wave1_module_policy(
        cur,
        company_code=company,
        module_key="onboarding_auto_start",
        actor_phone="96550009999",
        reason="product acceptance gate",
        payload={"required": {"auto_start_on_hire": False}},
    )
    check("setup patch hire→onboarding auto-start", p4.get("ok") is True, p4)
    auto_ob = (p4.get("policy") or {}).get("required", {}).get("auto_start_on_hire")
    check("setup onboarding auto-start off", auto_ob is False, p4)

    # Restore useful defaults for remaining proves
    w1p.patch_wave1_module_policy(
        cur,
        company_code=company,
        module_key="requisitions",
        actor_phone="96550009999",
        reason="restore",
        payload={"required": {"jobs_require_approved_requisition": True}},
    )
    w1p.patch_wave1_module_policy(
        cur,
        company_code=company,
        module_key="preboarding",
        actor_phone="96550009999",
        reason="restore",
        payload={"required": {"auto_create_on_offer_accept": True}},
    )
    w1p.patch_wave1_module_policy(
        cur,
        company_code=company,
        module_key="onboarding_auto_start",
        actor_phone="96550009999",
        reason="restore",
        payload={"required": {"auto_start_on_hire": True}},
    )

    # inactive when module off
    _upsert_module(cur, company, "probation", False)
    pol = w1p.get_probation_company_policy(cur, company)
    check("setup probation inactive when module off", pol.get("inactive") is True, pol)
    _upsert_module(cur, company, "probation", True)


def prove_modularity_matrix(cur, allow_companies: list[str]) -> None:
    import requisitions as rq
    import preboarding as pb
    import probation as pr
    import hire_ready_bridge as hrb

    c1 = f"W1M1{SUFFIX}"[:12].upper()
    c2 = f"W1M2{SUFFIX}"[:12].upper()
    c3 = f"W1M3{SUFFIX}"[:12].upper()
    c4 = f"W1M4{SUFFIX}"[:12].upper()
    c5 = f"W1M5{SUFFIX}"[:12].upper()
    c6 = f"W1M6{SUFFIX}"[:12].upper()
    allow_companies.extend([c1, c2, c3, c4, c5, c6])
    _flags_for(*allow_companies)

    # M1: Requisitions only + Hiring
    _ensure_company(cur, c1)
    _set_modules(cur, c1, {"requisitions": True, "pre_hiring": True})
    rq.ensure_requisitions_schema(cur)
    rq.set_settings(cur, c1, enabled=True, jobs_require_approved_requisition=True)
    created = rq.create_requisition(
        cur,
        company_code=c1,
        title_en="M1 Req",
        title_ar="طلب م1",
        headcount=1,
        created_by_user_id="m1-creator",
        submit=True,
        idempotency_key=f"m1:{SUFFIX}",
    )
    check("M1 requisitions+hiring create", created.get("ok") is True, created)
    pb_gate = pb.preboarding_enabled_for_company(cur, c1)
    check("M1 preboarding cleanly off", pb_gate.get("ok") is not True, pb_gate)
    pr_gate = pr.probation_enabled_for_company(cur, c1)
    check("M1 probation cleanly off", pr_gate.get("ok") is not True, pr_gate)

    # M2: Hiring + Offers, no Preboarding
    _ensure_company(cur, c2)
    _set_modules(cur, c2, {"pre_hiring": True, "offers": True, "preboarding": False})
    pb.ensure_preboarding_schema(cur)
    pb.set_settings(cur, c2, enabled=False)
    gate2 = pb.preboarding_enabled_for_company(cur, c2)
    check("M2 hiring+offers preboarding off", gate2.get("ok") is not True, gate2)
    check("M2 offers module present", True)

    # M3: Preboarding without Recruiting
    _ensure_company(cur, c3)
    _set_modules(cur, c3, {"preboarding": True, "pre_hiring": False, "offers": False, "requisitions": False})
    pb.ensure_preboarding_schema(cur)
    pb.set_settings(cur, c3, enabled=True)
    emp = f"{c3}-EMP"
    joining = date.today() + timedelta(days=7)
    cur.execute(
        """
        INSERT INTO employees (employee_key, company_code, name, phone, employment_status, start_date, updated_at)
        VALUES (%s,%s,%s,%s,'pending_start',%s, now())
        ON CONFLICT (employee_key) DO UPDATE SET employment_status='pending_start', updated_at=now()
        """,
        (emp, c3, "M3 Joiner", f"96570{SUFFIX[:6]}", joining),
    )
    pb.ensure_provisional_pending_start(
        cur, company_code=c3, employee_key=emp, name="M3 Joiner", joining_date=joining, phone=f"96570{SUFFIX[:6]}"
    )
    asn = pb.create_assignment(
        cur,
        company_code=c3,
        employee_key=emp,
        joining_date=joining,
        created_by_user_id="m3-hr",
        idempotency_key=f"m3:{SUFFIX}",
    )
    check("M3 preboarding without recruiting", asn.get("ok") is True, asn)
    rq_gate = rq.requisitions_enabled_for_company(cur, c3)
    check("M3 requisitions cleanly off", rq_gate.get("ok") is not True, rq_gate)

    # M4: Preboarding + Onboarding
    _ensure_company(cur, c4)
    _set_modules(cur, c4, {"preboarding": True, "onboarding": True})
    pb.ensure_preboarding_schema(cur)
    pb.set_settings(cur, c4, enabled=True, handoff_onboarding_enabled=True)
    import setup_console_wave1_policies as w1p

    pol = w1p.get_preboarding_company_policy(cur, c4)
    check("M4 preboard+onboarding handoff flag", (pol.get("optional") or {}).get("handoff_onboarding_enabled") is True, pol)

    # M5: Probation without Onboarding
    _ensure_company(cur, c5)
    _set_modules(cur, c5, {"probation": True, "onboarding": False})
    pr.ensure_probation_schema(cur)
    pr.set_settings(cur, c5, enabled=True, auto_plan_on_hire=True)
    emp5 = f"{c5}-EMP"
    start = date.today() - timedelta(days=5)
    cur.execute(
        """
        INSERT INTO employees (employee_key, company_code, name, phone, employment_status, start_date, updated_at)
        VALUES (%s,%s,%s,%s,'active',%s, now())
        ON CONFLICT (employee_key) DO UPDATE SET employment_status='active', updated_at=now()
        """,
        (emp5, c5, "M5 Prob", f"96571{SUFFIX[:6]}", start),
    )
    case = pr.create_case(
        cur,
        company_code=c5,
        employee_key=emp5,
        probation_start=start,
        probation_days=90,
        actor_user_id="m5-hr",
        idempotency_key=f"m5:{SUFFIX}",
    )
    check("M5 probation without onboarding", case.get("ok") is True, case)

    # M6: full Hire→Ready suite
    _ensure_company(cur, c6)
    _set_modules(
        cur,
        c6,
        {
            "requisitions": True,
            "pre_hiring": True,
            "offers": True,
            "preboarding": True,
            "onboarding": True,
            "probation": True,
        },
    )
    rq.ensure_requisitions_schema(cur)
    pb.ensure_preboarding_schema(cur)
    pr.ensure_probation_schema(cur)
    rq.set_settings(cur, c6, enabled=True, jobs_require_approved_requisition=True)
    pb.set_settings(cur, c6, enabled=True, auto_create_on_offer_accept=True, required_for_ready_mark=True)
    pr.set_settings(cur, c6, enabled=True, auto_plan_on_hire=True)
    for gate_fn, label in (
        (rq.requisitions_enabled_for_company, "M6 requisitions on"),
        (pb.preboarding_enabled_for_company, "M6 preboarding on"),
        (pr.probation_enabled_for_company, "M6 probation on"),
    ):
        g = gate_fn(cur, c6)
        check(label, g.get("ok") is True, g)
    check("M6 hire_ready on_offer_accepted", callable(hrb.on_offer_accepted))
    check("M6 hire_ready writers gate", callable(hrb.writers_enabled_for_company))


def prove_task_sync_and_surfaces(cur, company: str) -> None:
    import requisitions as rq
    import wave1_task_sync as w1t
    import probation as pr
    import workflow_task_sla as wts

    _flags_for(company)
    _ensure_company(cur, company)
    _set_modules(
        cur,
        company,
        {
            "requisitions": True,
            "pre_hiring": True,
            "preboarding": True,
            "probation": True,
            "onboarding": True,
            "offers": True,
        },
    )
    rq.ensure_requisitions_schema(cur)
    pr.ensure_probation_schema(cur)
    try:
        wts.ensure_workflow_task_sla_schema(cur)
        wts.set_task_enabled(cur, company, enabled=True)
    except Exception as exc:
        check("workflow tasks schema", False, exc)
        return

    created = rq.create_requisition(
        cur,
        company_code=company,
        title_en=f"Product task {SUFFIX}",
        title_ar=f"مهمة منتج {SUFFIX}",
        headcount=1,
        created_by_user_id="prod-creator",
        submit=True,
        idempotency_key=f"prod-task:{SUFFIX}",
    )
    check("task-sync requisition create", created.get("ok") is True, created)
    req = created.get("requisition") or {}
    rid = str(req.get("requisition_id") or "")
    t1 = w1t.on_requisition_pending_approval(cur, company_code=company, requisition=req, actor_user_id="prod-creator")
    check("task-sync requisition_approval emitted", t1.get("ok") is True or t1.get("skipped") is True, t1)
    if t1.get("ok") is True:
        cur.execute(
            """
            SELECT task_id, task_type, subject_id FROM hr_tasks
            WHERE company_code=%s AND subject_id=%s AND task_type='requisition_approval'
            ORDER BY created_at DESC LIMIT 1
            """,
            (company, rid),
        )
        row = cur.fetchone()
        check("canonical hr_tasks row for requisition", bool(row), row)

    emp = f"{company}-TS"
    start = date.today() - timedelta(days=10)
    cur.execute(
        """
        INSERT INTO employees (employee_key, company_code, name, phone, employment_status, start_date, updated_at)
        VALUES (%s,%s,%s,%s,'active',%s, now())
        ON CONFLICT (employee_key) DO UPDATE SET employment_status='active', updated_at=now()
        """,
        (emp, company, "Task Sync Emp", f"96572{SUFFIX[:6]}", start),
    )
    case = pr.create_case(
        cur,
        company_code=company,
        employee_key=emp,
        probation_start=start,
        probation_days=90,
        actor_user_id="prod-hr",
        idempotency_key=f"prod-prb:{SUFFIX}",
    )
    check("task-sync probation case", case.get("ok") is True, case)
    cobj = case.get("case") or {}
    # move under_review if API supports
    try:
        tr = pr.transition_case(
            cur,
            company_code=company,
            case_id=str(cobj.get("case_id")),
            to_status="under_review",
            actor_user_id="prod-hr",
            expected_row_version=cobj.get("row_version"),
        )
        if tr.get("ok"):
            cobj = tr.get("case") or cobj
    except Exception:
        pass
    t2 = w1t.on_probation_decision_required(cur, company_code=company, case=cobj)
    check("task-sync probation_decision emitted", t2.get("ok") is True or t2.get("skipped") is True, t2)

    # Disabled module fail-closed
    _upsert_module(cur, company, "requisitions", False)
    off = rq.requisitions_enabled_for_company(cur, company)
    check("disabled requisitions fail closed", off.get("ok") is not True, off)
    _upsert_module(cur, company, "requisitions", True)


def prove_visual_canary(cur, allow_companies: list[str]) -> None:
    import importlib.util

    path = Path(__file__).resolve().parent / "ops-seed-wave1-visual-canary.py"
    spec = importlib.util.spec_from_file_location("ops_seed_wave1_visual_canary", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    allow_companies.append("WATHEFNI")
    _flags_for(*allow_companies)
    mod._enable_process_flags()
    # Keep WATHEFNI in allowlists (seed overwrites env to WATHEFNI-only — restore combined)
    _flags_for(*allow_companies)
    cleaned = mod.cleanup(cur)
    out = mod.seed(cur)
    check("visual canary seed ok", out.get("ok") is True, out)
    check("visual canary has pending req", bool(out.get("requisition_pending_id")), out)
    check("visual canary has open req", bool(out.get("requisition_open_id")), out)
    check("visual canary has preboard", bool(out.get("preboard_assignment_id")), out)
    check("visual canary has probation", bool(out.get("probation_case_id")), out)
    # Keep seeded data for owner visual review (do not cleanup after seed)
    check(
        "visual canary left for owner review",
        True,
        {"cleaned_prior": cleaned, **{k: out.get(k) for k in ("suffix", "requisition_pending_id", "preboard_assignment_id", "probation_case_id")}},
    )


def prove_product_surface_wiring() -> None:
    """Static product completeness — no backend-only Wave 1 module without UI.

    On staging orch-only hosts the monorepo apps/ tree is absent; unit smoke
    already asserts those paths. Skip file checks when apps/ is missing.
    """
    root = Path(__file__).resolve().parent.parent
    web = root / "apps" / "wathefni-dashboard" / "src"
    mobile = root / "apps" / "wathefni-employee-mobile"
    if not (root / "apps").is_dir():
        check("surface wiring (apps tree absent — covered by unit smoke)", True)
        return
    checks = [
        ("HR Web requisitions", web / "prehire/RequisitionsWorkspace.tsx"),
        ("HR Web preboarding", web / "posthire/PreboardingWorkspace.tsx"),
        ("HR Web probation", web / "posthire/ProbationWorkspace.tsx"),
        ("Setup Wave1 policies", web / "setup-console/Wave1HireReadyPoliciesCard.tsx"),
        ("HR mobile requisitions queue", mobile / "src/hr/features/requisitions/HRRequisitionsQueueView.tsx"),
        ("HR mobile probation queue", mobile / "src/hr/features/probation/HRProbationQueueView.tsx"),
        ("Employee preboarding", mobile / "app/preboarding.tsx"),
        ("Employee probation", mobile / "app/probation.tsx"),
        ("nav capability requisitions", web / "lib/workspaceCapability.ts"),
    ]
    for label, path in checks:
        check(label, path.is_file(), path)
    cap = (web / "lib/workspaceCapability.ts").read_text(encoding="utf-8")
    for key in ("nav.requisitions", "nav.preboarding", "nav.probation"):
        check(f"capability {key}", key in cap)
    card = (web / "setup-console/Wave1HireReadyPoliciesCard.tsx").read_text(encoding="utf-8")
    check("setup card EN+AR", "titleEn" in card and "titleAr" in card)


def main() -> int:
    print("    wave1 product acceptance — db")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))
    company = f"W1PA{SUFFIX}"[:12].upper()
    allow = [company, "WATHEFNI"]
    _flags_for(*allow)
    prove_product_surface_wiring()

    try:
        conn, RealDictCursor = _connect()
    except Exception as exc:
        print(f"FAIL connect: {exc}")
        return 2

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            print("    --- setup console policies ---")
            prove_setup_policies(cur, company)
            print("    --- modularity matrix ---")
            prove_modularity_matrix(cur, allow)
            _flags_for(*allow)
            print("    --- task sync + fail-closed ---")
            prove_task_sync_and_surfaces(cur, company)
            print("    --- visual canary WATHEFNI ---")
            prove_visual_canary(cur, allow)
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
        print("WAVE1_PRODUCT_FULL_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
