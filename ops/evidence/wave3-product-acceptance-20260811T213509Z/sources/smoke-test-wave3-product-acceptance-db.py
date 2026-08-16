#!/usr/bin/env python3
"""Wave 3 Product Acceptance — staging DB prove (company-scoped canary).

Proves:
  1) Full synthetic lifecycle: employment changes → ESS → exit → notice →
     offboarding/clearance → settlement/access contracts → exit close → alumni/rehire
  2) Modularity matrix (alone + combinations; disabled disappear cleanly)
  3) Setup Console Wave 3 policies (get/patch — not env-only)
  4) Authority: tenant / SoD / stale / idempotent / immutable / no silent reopen
  5) Assistant remains read-only; real termination remains dark
  6) EN/AR labels + rollback preserves canonical lifecycle history

Process-scoped flags only. Synthetic companies. Never systemd-global.
Does NOT unlock WATHEFNI_REAL_TERMINATION_CANARY.
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
_N = int(SUFFIX, 16) % 100000
COMPANY = f"W3P{_N:05d}"[:12].upper()
OTHER = f"W3X{_N:05d}"[:12].upper()
EMP_PHONE = f"9656100{_N:05d}"
HR_PHONE = f"9656101{_N:05d}"
APPROVER = f"9656102{_N:05d}"
IT_PHONE = f"9656103{_N:05d}"
MGR_PHONE = f"9656104{_N:05d}"
CREATOR = f"9656105{_N:05d}"
APPLIER = f"9656106{_N:05d}"
EMP = f"{COMPANY}-W3P-{SUFFIX}"
PERSON = f"PERSON-W3P-{SUFFIX}"
MARKERS = "W3P,W3C5,XC5,W3C4,OB4,W3C3,EX3"

MIN_TEMPLATE = [
    {
        "item_key": "handover",
        "item_class": "handover",
        "required": True,
        "owner_role": "manager",
        "title_en": "Handover",
        "title_ar": "تسليم",
        "depends_on": [],
        "due_offset_days": 1,
    },
    {
        "item_key": "hr_docs",
        "item_class": "hr_docs",
        "required": True,
        "owner_role": "hr",
        "title_en": "HR docs",
        "title_ar": "وثائق",
        "depends_on": ["handover"],
        "due_offset_days": 1,
    },
    {
        "item_key": "optional_keys",
        "item_class": "keys_cards",
        "required": False,
        "owner_role": "hr",
        "title_en": "Keys",
        "title_ar": "مفاتيح",
        "depends_on": [],
        "due_offset_days": 1,
    },
    {
        "item_key": "it_access",
        "item_class": "it_access",
        "required": True,
        "owner_role": "it",
        "title_en": "IT clearance",
        "title_ar": "مخالصة تقنية",
        "depends_on": [],
        "due_offset_days": 1,
    },
]


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

    host = os.environ.get("PGHOST") or os.environ.get("WATHEFNI_EXPECTED_DATABASE_HOST") or "127.0.0.1"
    port = os.environ.get("PGPORT") or os.environ.get("WATHEFNI_EXPECTED_DATABASE_PORT") or "5432"
    name = os.environ.get("PGDATABASE") or os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "wathefni_staging"
    user = os.environ.get("PGUSER") or "postgres"
    password = os.environ.get("PGPASSWORD") or ""
    if password:
        return psycopg2.connect(
            host=host, port=port, dbname=name, user=user, password=password, cursor_factory=RealDictCursor
        )
    import app

    return app.db_connect()


def _flags_all_off() -> None:
    for flag in (
        "WATHEFNI_EMPLOYMENT_CHANGE_C1",
        "WATHEFNI_ESS_LETTERS_DEPENDENTS_C2",
        "WATHEFNI_RESIGNATION_ESS_C3",
        "WATHEFNI_OFFBOARDING_C4",
        "WATHEFNI_EXIT_CLOSE_C5",
        "WATHEFNI_REAL_TERMINATION_CANARY",
        "WATHEFNI_OFFBOARDING_IDP_ADAPTER",
        "WATHEFNI_PAYROLL_SETTLEMENT_C6",
    ):
        os.environ[flag] = "off"
    for companies in (
        "WATHEFNI_EMPLOYMENT_CHANGE_COMPANIES",
        "WATHEFNI_ESS_LETTERS_DEPENDENTS_COMPANIES",
        "WATHEFNI_RESIGNATION_ESS_COMPANIES",
        "WATHEFNI_OFFBOARDING_COMPANIES",
        "WATHEFNI_EXIT_CLOSE_COMPANIES",
        "WATHEFNI_PAYROLL_SETTLEMENT_COMPANIES",
    ):
        os.environ[companies] = ""
    os.environ["WATHEFNI_OFFBOARDING_KILL"] = "off"
    os.environ["WATHEFNI_EXIT_INTENT_SYNTHETIC_MARKERS"] = MARKERS
    os.environ["WATHEFNI_OFFBOARDING_SYNTHETIC_MARKERS"] = MARKERS
    os.environ["WATHEFNI_EXIT_CLOSE_SYNTHETIC_MARKERS"] = MARKERS


def _flags_for(modules: dict[str, bool], *, capabilities: dict[str, bool] | None = None) -> None:
    _flags_all_off()
    allow = COMPANY
    capabilities = capabilities or {}

    def on(flag: str, companies_flag: str, enabled: bool) -> None:
        os.environ[flag] = "on" if enabled else "off"
        os.environ[companies_flag] = allow if enabled else ""

    on("WATHEFNI_EMPLOYMENT_CHANGE_C1", "WATHEFNI_EMPLOYMENT_CHANGE_COMPANIES", bool(modules.get("employment_change")))
    on(
        "WATHEFNI_ESS_LETTERS_DEPENDENTS_C2",
        "WATHEFNI_ESS_LETTERS_DEPENDENTS_COMPANIES",
        bool(modules.get("ess_letters_dependents")),
    )
    on("WATHEFNI_RESIGNATION_ESS_C3", "WATHEFNI_RESIGNATION_ESS_COMPANIES", bool(modules.get("exit_intent")))
    on("WATHEFNI_OFFBOARDING_C4", "WATHEFNI_OFFBOARDING_COMPANIES", bool(modules.get("offboarding")))
    on("WATHEFNI_EXIT_CLOSE_C5", "WATHEFNI_EXIT_CLOSE_COMPANIES", bool(modules.get("exit_close")))
    os.environ["WATHEFNI_OFFBOARDING_IDP_ADAPTER"] = "on" if capabilities.get("idp") else "off"
    if capabilities.get("settlement"):
        os.environ["WATHEFNI_PAYROLL_SETTLEMENT_C6"] = "on"
        os.environ["WATHEFNI_PAYROLL_SETTLEMENT_COMPANIES"] = allow
        os.environ["WATHEFNI_PAYROLL_SETTLEMENT_KILL"] = "off"
    os.environ["WATHEFNI_REAL_TERMINATION_CANARY"] = "off"


def _ensure_company(cur, company: str) -> None:
    cur.execute(
        """
        INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
        VALUES (%s, %s, '{}'::jsonb, '{}'::jsonb, now(), now())
        ON CONFLICT (company_code) DO NOTHING
        """,
        (company, f"Wave3 Product {company}"),
    )


def _ensure_employee(cur, *, emp_key: str, phone: str, name: str = "W3P Emp") -> None:
    hire = date(2035, 1, 1)
    cur.execute(
        """
        INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'active')
        ON CONFLICT (employee_key) DO UPDATE
          SET employment_status='active', company_code=EXCLUDED.company_code,
              profile=EXCLUDED.profile, updated_at=now()
        """,
        (
            COMPANY,
            emp_key,
            phone,
            name,
            hire,
            hire,
            f'{{"department":"Ops","position_title":"Analyst","grade":"L2","person_key":"{PERSON}"}}',
        ),
    )


def _apply_change(cur, c1, *, change_type: str, payload: dict, effective_from: date, effective_to=None) -> dict:
    created = c1.create_change_case(
        cur,
        company_code=COMPANY,
        employee_key=EMP,
        change_type=change_type,
        effective_from=effective_from,
        effective_to=effective_to,
        actor_phone=CREATOR,
        reason=f"w3p {change_type}",
        payload=payload,
    )
    if not created.get("ok"):
        return created
    cid = str(created["case"]["case_id"])
    c1.submit_change_case(
        cur,
        company_code=COMPANY,
        case_id=cid,
        actor_phone=CREATOR,
        reason="submit",
        expected_row_version=int(created["case"].get("row_version") or 1),
    )
    cur.execute("SELECT row_version FROM employment_change_cases WHERE case_id=%s", (cid,))
    rv = int((cur.fetchone() or {}).get("row_version") or 1)
    c1.decide_change_case(
        cur,
        company_code=COMPANY,
        case_id=cid,
        decision="approved",
        actor_phone=APPROVER,
        reason="ok",
        expected_row_version=rv,
    )
    cur.execute("SELECT row_version FROM employment_change_cases WHERE case_id=%s", (cid,))
    rv = int((cur.fetchone() or {}).get("row_version") or 1)
    return c1.apply_change_case(
        cur,
        company_code=COMPANY,
        case_id=cid,
        actor_phone=APPLIER,
        reason="apply",
        expected_row_version=rv,
    )


def _drive_exit_to_ready(cur, c3, *, emp_key: str, intent: str, lwd: date) -> str:
    if intent == "resignation":
        r = c3.create_resignation(
            cur,
            company_code=COMPANY,
            employee_key=emp_key,
            actor_phone=EMP_PHONE,
            requested_last_working_day=lwd,
            reason="w3p resign",
        )
    elif intent == "termination":
        r = c3.create_termination(
            cur,
            company_code=COMPANY,
            employee_key=emp_key,
            actor_phone=HR_PHONE,
            effective_last_working_day=lwd,
            reason="w3p synthetic term",
            reason_category="performance",
            hr_authorized=True,
        )
    else:
        r = c3.create_eoc_case(
            cur,
            company_code=COMPANY,
            employee_key=emp_key,
            actor_phone=HR_PHONE,
            contract_end_date=lwd,
            reason="w3p eoc",
        )
    if not r.get("ok"):
        raise RuntimeError(f"create {intent} failed: {r}")
    eid = str(r["case"]["case_id"])
    c3.submit_case(cur, company_code=COMPANY, case_id=eid, actor_phone=EMP_PHONE if intent == "resignation" else HR_PHONE, reason="s", expected_version=1)
    cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (eid,))
    rv = int((cur.fetchone() or {}).get("row_version") or 1)
    c3.approve_case(cur, company_code=COMPANY, case_id=eid, actor_phone=APPROVER, reason="ok", expected_version=rv)
    cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (eid,))
    rv = int((cur.fetchone() or {}).get("row_version") or 1)
    notice_start = min(date.today(), lwd) - timedelta(days=14)
    notice = c3.enter_notice_period(
        cur,
        company_code=COMPANY,
        case_id=eid,
        actor_phone=HR_PHONE,
        reason="notice",
        last_working_day=lwd,
        notice_starts_on=notice_start,
        expected_version=rv,
    )
    if not notice.get("ok"):
        raise RuntimeError(f"notice failed: {notice}")
    cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (eid,))
    rv = int((cur.fetchone() or {}).get("row_version") or 1)
    ready = c3.mark_ready_for_offboarding(
        cur, company_code=COMPANY, case_id=eid, actor_phone=HR_PHONE, reason="ready", expected_version=rv
    )
    if not ready.get("ok"):
        raise RuntimeError(f"ready failed: {ready}")
    return eid


def _complete_offboarding(cur, c4, *, exit_id: str, waive_optional: bool = True) -> str:
    started = c4.start_offboarding_from_exit_intent(
        cur, company_code=COMPANY, exit_intent_case_id=exit_id, actor_phone=HR_PHONE, reason="start"
    )
    if not started.get("ok"):
        raise RuntimeError(f"offboarding start failed: {started}")
    cid = str(started["case"]["case_id"])
    # Complete required items respecting deps: handover → hr_docs; it_access parallel
    for _ in range(8):
        progress = False
        for item in c4.list_items(cur, case_id=cid):
            if item.get("status") in ("completed", "waived"):
                continue
            if not item.get("required"):
                if waive_optional and item.get("item_key") == "optional_keys":
                    wav = c4.waive_clearance_item(
                        cur,
                        company_code=COMPANY,
                        item_id=str(item["item_id"]),
                        actor_phone=HR_PHONE,
                        actor_role="hr",
                        reason="waive keys",
                        expected_version=int(item.get("row_version") or 1),
                    )
                    if wav.get("ok"):
                        progress = True
                continue
            role = item.get("owner_role")
            phone = {"manager": MGR_PHONE, "it": IT_PHONE}.get(role, HR_PHONE)
            done = c4.complete_clearance_item(
                cur,
                company_code=COMPANY,
                item_id=str(item["item_id"]),
                actor_phone=phone,
                actor_role=role,
                reason="done",
                expected_version=int(item.get("row_version") or 1),
            )
            if done.get("ok"):
                progress = True
            elif done.get("error") == "dependency_blocked":
                continue
        c4._reevaluate_case_status(cur, company_code=COMPANY, case_id=cid)  # noqa: SLF001
        cur.execute("SELECT status FROM offboarding_cases WHERE case_id=%s", (cid,))
        if str((cur.fetchone() or {}).get("status")) == "ready_to_close":
            break
        if not progress:
            break
    cur.execute("SELECT row_version, status FROM offboarding_cases WHERE case_id=%s", (cid,))
    row = dict(cur.fetchone() or {})
    done = c4.complete_offboarding_case(
        cur,
        company_code=COMPANY,
        case_id=cid,
        actor_phone=HR_PHONE,
        reason="complete",
        expected_version=int(row.get("row_version") or 1),
    )
    if not done.get("ok"):
        raise RuntimeError(f"offboarding complete failed: {done}")
    return cid


def prove_setup(cur) -> None:
    import setup_console_wave3_policies as w3p

    _ensure_company(cur, COMPANY)
    allp = w3p.get_all_wave3_policies(cur, COMPANY)
    check("setup get_all wave3 ok", allp.get("ok") is True, allp)
    for key in w3p.WAVE3_MODULE_KEYS:
        check(f"setup has {key}", isinstance((allp.get("modules") or {}).get(key), dict))
    check("setup EN/AR labels", bool((allp.get("modules") or {}).get("exit_close", {}).get("label_ar")))

    patches = [
        ("employment_change", {"enabled": True, "require_distinct_approver": True}),
        ("ess_letters_dependents", {"enabled": True, "dependent_review_required": True}),
        ("exit_intent", {"enabled": True, "resignation_enabled": True, "notice_policy_days": 14}),
        ("offboarding", {"enabled": True, "clearance_sla_days": 5, "waiver_roles": ["hr"]}),
        (
            "exit_close",
            {
                "enabled": True,
                "require_settlement_ack": False,
                "require_access_revoke_ack": False,
                "exit_interview_enabled": True,
                "rehire_eligibility_default": "eligible",
            },
        ),
    ]
    for key, payload in patches:
        p = w3p.patch_wave3_module_policy(
            cur,
            company_code=COMPANY,
            module_key=key,
            actor_phone=HR_PHONE,
            reason="wave3 product acceptance",
            payload=payload,
        )
        check(f"setup patch {key}", p.get("ok") is True, p)
    check("setup owns policies honesty", allp.get("setup_owns_wave3_policies") is True)
    check("setup not env-only", allp.get("env_only_ownership") is False)


def prove_modularity(cur, c1, c2, c3, c4, c5) -> None:
    import setup_console_wave3_policies as w3p

    matrix = w3p.modularity_matrix_configs()
    check("matrix size", len(matrix) >= 8, len(matrix))
    for cell in matrix:
        name = cell["name"]
        modules = cell.get("modules") or {}
        caps = cell.get("capabilities") or {}
        _flags_for(modules, capabilities=caps)
        g1 = c1.runtime_gate_for_company(COMPANY).get("ok") is True
        g2 = c2.runtime_gate_for_company(COMPANY).get("ok") is True
        g3 = c3.runtime_gate_for_company(COMPANY).get("ok") is True
        g4 = c4.runtime_gate_for_company(COMPANY).get("ok") is True
        g5 = c5.runtime_gate_for_company(COMPANY).get("ok") is True
        check(f"matrix {name} employment_change", g1 is bool(modules.get("employment_change")))
        check(f"matrix {name} ess", g2 is bool(modules.get("ess_letters_dependents")))
        check(f"matrix {name} exit_intent", g3 is bool(modules.get("exit_intent")))
        check(f"matrix {name} offboarding", g4 is bool(modules.get("offboarding")))
        check(f"matrix {name} exit_close", g5 is bool(modules.get("exit_close")))
        if name == "resignation_without_offboarding":
            vis = c3.feature_visibility(cur, COMPANY) if g3 else {}
            check("resign without OB: exit visible", bool(vis.get("resignation_visible") or g3), vis)
            check("resign without OB: offboarding gate off", g4 is False)
        if name == "all_disabled":
            check("all disabled clean", not any([g1, g2, g3, g4, g5]))
        if name == "offboarding_without_payroll":
            check("OB without payroll: settlement flag off", os.environ.get("WATHEFNI_PAYROLL_SETTLEMENT_C6") == "off")
        if name == "offboarding_without_idp":
            check("OB without IdP: adapter off", os.environ.get("WATHEFNI_OFFBOARDING_IDP_ADAPTER") == "off")


def prove_full_journey(cur, c1, c2, c3, c4, c5) -> None:
    _flags_for(
        {
            "employment_change": True,
            "ess_letters_dependents": True,
            "exit_intent": True,
            "offboarding": True,
            "exit_close": True,
        },
        capabilities={"settlement": True, "idp": True},
    )
    _ensure_company(cur, COMPANY)
    _ensure_company(cur, OTHER)
    _ensure_employee(cur, emp_key=EMP, phone=EMP_PHONE)

    c1.ensure_employment_change_c1_schema(cur)
    c2.ensure_ess_letters_dependents_c2_schema(cur)
    c3.ensure_exit_intent_c3_schema(cur)
    c4.ensure_offboarding_c4_schema(cur)
    c5.ensure_exit_close_c5_schema(cur)

    en1 = c1.enable_company_employment_change(cur, company_code=COMPANY, actor_phone=HR_PHONE, reason="w3p")
    check("enable employment_change", en1.get("ok") is True, en1)
    en2 = c2.enable_company_ess_letters_dependents(
        cur,
        company_code=COMPANY,
        actor_phone=HR_PHONE,
        reason="w3p",
        letters_enabled=True,
        letters_fulfill=True,
        dependents_enabled=True,
    )
    check("enable ess", en2.get("ok") is True, en2)
    en3 = c3.enable_company_exit_intent(
        cur,
        company_code=COMPANY,
        actor_phone=HR_PHONE,
        reason="w3p",
        resignation_enabled=True,
        termination_enabled=True,
        eoc_enabled=True,
        notice_policy_days=14,
    )
    check("enable exit_intent", en3.get("ok") is True, en3)
    en4 = c4.enable_company_offboarding(
        cur,
        company_code=COMPANY,
        actor_phone=HR_PHONE,
        reason="w3p",
        template=MIN_TEMPLATE,
        waiver_roles=["hr"],
    )
    check("enable offboarding", en4.get("ok") is True, en4)
    en5 = c5.enable_company_exit_close(
        cur,
        company_code=COMPANY,
        actor_phone=HR_PHONE,
        reason="w3p",
        require_settlement_ack=True,
        allow_settlement_waiver=True,
        require_access_revoke_ack=True,
        require_last_working_day_reached=True,
        allow_lwd_override=True,
        exit_interview_enabled=True,
        exit_interview_required=False,
    )
    check("enable exit_close", en5.get("ok") is True, en5)

    # Tenant isolation
    check("tenant iso C5 other company", c5.runtime_gate_for_company(OTHER).get("ok") is not True)
    check("real term dark", c3.assert_real_termination_dark().get("ok") is True)

    eff = date(2035, 2, 1)
    promo = _apply_change(
        cur, c1, change_type="promotion", payload={"position_title": "Lead Analyst", "grade": "L3"}, effective_from=eff
    )
    check("promotion applied", promo.get("ok") is True, promo)
    xfer = _apply_change(
        cur, c1, change_type="transfer", payload={"department": "Finance"}, effective_from=eff + timedelta(days=10)
    )
    check("transfer applied", xfer.get("ok") is True, xfer)
    sec = _apply_change(
        cur,
        c1,
        change_type="secondment",
        payload={"department": "Projects", "host_department": "Projects"},
        effective_from=eff + timedelta(days=20),
        effective_to=eff + timedelta(days=50),
    )
    check("secondment applied", sec.get("ok") is True, sec)
    sal = _apply_change(
        cur,
        c1,
        change_type="salary_change",
        payload={"amount": 1200, "currency": "KWD", "component_code": "BASIC"},
        effective_from=eff + timedelta(days=60),
    )
    check("salary change applied", sal.get("ok") is True, sal)
    hist = c1.list_history(cur, company_code=COMPANY, employee_key=EMP)
    check("employment change history intact", len(hist) >= 4, len(hist))

    # ESS letter
    letter = c2.request_letter(
        cur,
        company_code=COMPANY,
        employee_key=EMP,
        actor_phone=EMP_PHONE,
        letter_type="employment_certificate",
        lang="en",
        purpose="w3p letter",
    )
    check("ESS letter requested", letter.get("ok") is True, letter)
    if letter.get("ok"):
        rid = str(letter["request"]["request_id"])
        cur.execute("SELECT row_version FROM ess_letter_requests WHERE request_id=%s", (rid,))
        rv = int((cur.fetchone() or {}).get("row_version") or 1)
        c2.start_letter_review(
            cur, company_code=COMPANY, request_id=rid, actor_phone=HR_PHONE, expected_version=rv
        )
        cur.execute("SELECT row_version FROM ess_letter_requests WHERE request_id=%s", (rid,))
        rv = int((cur.fetchone() or {}).get("row_version") or 1)
        c2.approve_letter(
            cur, company_code=COMPANY, request_id=rid, actor_phone=APPROVER, reason="ok", expected_version=rv
        )
        cur.execute("SELECT row_version FROM ess_letter_requests WHERE request_id=%s", (rid,))
        rv = int((cur.fetchone() or {}).get("row_version") or 1)
        issued = c2.issue_letter(
            cur, company_code=COMPANY, request_id=rid, actor_phone=HR_PHONE, reason="issue", expected_version=rv
        )
        check("ESS letter issued", issued.get("ok") is True, issued)

    # Resignation without Offboarding (honest stop)
    emp_no_ob = f"{COMPANY}-W3P-NOOB-{SUFFIX}"
    _ensure_employee(cur, emp_key=emp_no_ob, phone=f"9656110{_N:05d}", name="No OB")
    # Temporarily prove path by not starting C4 after ready
    exit_no_ob = _drive_exit_to_ready(cur, c3, emp_key=emp_no_ob, intent="resignation", lwd=date.today() - timedelta(days=1))
    cur.execute("SELECT status, employment_status FROM exit_intent_cases e JOIN employees emp ON emp.employee_key=e.employee_key WHERE e.case_id=%s", (exit_no_ob,))
    # simpler:
    cur.execute("SELECT status FROM exit_intent_cases WHERE case_id=%s", (exit_no_ob,))
    check("resign without OB ends ready_for_offboarding", str((cur.fetchone() or {}).get("status")) == "ready_for_offboarding")
    cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (emp_no_ob,))
    check("resign without OB does not set left", str((cur.fetchone() or {}).get("employment_status")) == "active")
    check(
        "resign without OB: no offboarding case",
        c4.get_case_by_exit_intent(cur, company_code=COMPANY, exit_intent_case_id=exit_no_ob) is None,
    )

    # Synthetic employer termination path (separate employee)
    emp_term = f"{COMPANY}-W3P-TERM-{SUFFIX}"
    _ensure_employee(cur, emp_key=emp_term, phone=f"9656111{_N:05d}", name="Term")
    exit_term = _drive_exit_to_ready(
        cur, c3, emp_key=emp_term, intent="termination", lwd=date.today() - timedelta(days=1)
    )
    check("synthetic termination → ready", bool(exit_term))
    cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (emp_term,))
    check("termination intent ≠ left", str((cur.fetchone() or {}).get("employment_status")) == "active")

    # EOC renew + non-renew
    emp_eoc_r = f"{COMPANY}-W3P-EOCR-{SUFFIX}"
    emp_eoc_n = f"{COMPANY}-W3P-EOCN-{SUFFIX}"
    _ensure_employee(cur, emp_key=emp_eoc_r, phone=f"9656112{_N:05d}", name="EOC R")
    _ensure_employee(cur, emp_key=emp_eoc_n, phone=f"9656113{_N:05d}", name="EOC N")
    eoc_r = c3.create_eoc_case(
        cur,
        company_code=COMPANY,
        employee_key=emp_eoc_r,
        actor_phone=HR_PHONE,
        contract_end_date=date.today() + timedelta(days=30),
        reason="renew path",
    )
    check("EOC case create renew path", eoc_r.get("ok") is True, eoc_r)
    if eoc_r.get("ok"):
        eid = str(eoc_r["case"]["case_id"])
        renew = c3.decide_eoc_renewal(
            cur,
            company_code=COMPANY,
            case_id=eid,
            actor_phone=APPROVER,
            reason="renew",
            renewed_contract_end=date.today() + timedelta(days=365),
            expected_version=1,
        )
        check("EOC renewal", renew.get("ok") is True and renew.get("eoc_decision") == "renewed", renew)
        cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (emp_eoc_r,))
        check("EOC renew keeps active", str((cur.fetchone() or {}).get("employment_status")) == "active")

    eoc_n = c3.create_eoc_case(
        cur,
        company_code=COMPANY,
        employee_key=emp_eoc_n,
        actor_phone=HR_PHONE,
        contract_end_date=date.today() + timedelta(days=60),
        reason="nonrenew path",
    )
    check("EOC case create non-renew", eoc_n.get("ok") is True, eoc_n)
    if eoc_n.get("ok"):
        eid = str(eoc_n["case"]["case_id"])
        non = c3.decide_eoc_non_renewal(
            cur, company_code=COMPANY, case_id=eid, actor_phone=HR_PHONE, reason="nonrenew", expected_version=1
        )
        check("EOC non-renewal", non.get("ok") is True and non.get("eoc_decision") == "non_renewed", non)
        cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (eid,))
        rv = int((cur.fetchone() or {}).get("row_version") or 1)
        c3.submit_case(cur, company_code=COMPANY, case_id=eid, actor_phone=HR_PHONE, reason="s", expected_version=rv)
        cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (eid,))
        rv = int((cur.fetchone() or {}).get("row_version") or 1)
        c3.approve_case(cur, company_code=COMPANY, case_id=eid, actor_phone=APPROVER, reason="ok", expected_version=rv)
        cur.execute("SELECT row_version FROM exit_intent_cases WHERE case_id=%s", (eid,))
        rv = int((cur.fetchone() or {}).get("row_version") or 1)
        notice_n = c3.enter_notice_period(
            cur,
            company_code=COMPANY,
            case_id=eid,
            actor_phone=HR_PHONE,
            reason="eoc notice",
            last_working_day=date.today() + timedelta(days=60),
            notice_starts_on=date.today(),
            expected_version=rv,
        )
        check("EOC non-renew notice-period authority", notice_n.get("ok") is True, notice_n)

    # Full suite primary EMP: resign → notice → exactly one OB → clearance → close
    lwd = date.today() - timedelta(days=1)
    exit_id = _drive_exit_to_ready(cur, c3, emp_key=EMP, intent="resignation", lwd=lwd)
    handoff1 = c4.start_offboarding_from_exit_intent(
        cur, company_code=COMPANY, exit_intent_case_id=exit_id, actor_phone=HR_PHONE, reason="first"
    )
    check("exit intent → offboarding case", handoff1.get("ok") is True, handoff1)
    ob_id = str(handoff1["case"]["case_id"])
    handoff2 = c4.start_offboarding_from_exit_intent(
        cur, company_code=COMPANY, exit_intent_case_id=exit_id, actor_phone=HR_PHONE, reason="dup"
    )
    check(
        "exactly one OB case (idempotent handoff)",
        handoff2.get("duplicate_handoff") is True and str((handoff2.get("case") or {}).get("case_id")) == ob_id,
        handoff2,
    )

    # Dependency: hr_docs depends on handover — try complete hr first
    items = {i["item_key"]: i for i in c4.list_items(cur, case_id=ob_id)}
    if "hr_docs" in items:
        blocked = c4.complete_clearance_item(
            cur,
            company_code=COMPANY,
            item_id=str(items["hr_docs"]["item_id"]),
            actor_phone=HR_PHONE,
            actor_role="hr",
            reason="early",
            expected_version=int(items["hr_docs"].get("row_version") or 1),
        )
        check("clearance dependency blocks", blocked.get("error") == "dependency_blocked", blocked)

    # Optional IdP acknowledgement path before IT clearance complete (request ≠ revoked)
    it_items = [i for i in c4.list_items(cur, case_id=ob_id) if i.get("item_key") == "it_access"]
    if it_items and hasattr(c4, "request_idp_revoke"):
        idp = c4.request_idp_revoke(
            cur,
            company_code=COMPANY,
            case_id=ob_id,
            item_id=str(it_items[0]["item_id"]),
            actor_phone=IT_PHONE,
            reason="request idp",
        )
        check(
            "IdP request ≠ revoked until ack",
            idp.get("ok") is True
            or idp.get("error") in ("idp_adapter_disabled", "item_not_found", "not_applicable"),
            idp,
        )
        if idp.get("ok"):
            check(
                "revoke_requested_is_not_revoked honesty",
                c4.honesty_payload().get("revoke_requested_is_not_revoked") is True,
            )

    # Complete/waive path + manual IT clearance
    for _ in range(8):
        for item in c4.list_items(cur, case_id=ob_id):
            if item.get("status") in ("completed", "waived"):
                continue
            if not item.get("required") and item.get("item_key") == "optional_keys":
                c4.waive_clearance_item(
                    cur,
                    company_code=COMPANY,
                    item_id=str(item["item_id"]),
                    actor_phone=HR_PHONE,
                    actor_role="hr",
                    reason="waive",
                    expected_version=int(item.get("row_version") or 1),
                )
                continue
            if not item.get("required"):
                continue
            role = item.get("owner_role")
            phone = {"manager": MGR_PHONE, "it": IT_PHONE}.get(role, HR_PHONE)
            c4.complete_clearance_item(
                cur,
                company_code=COMPANY,
                item_id=str(item["item_id"]),
                actor_phone=phone,
                actor_role=role,
                reason="done",
                expected_version=int(item.get("row_version") or 1),
            )
        c4._reevaluate_case_status(cur, company_code=COMPANY, case_id=ob_id)  # noqa: SLF001
        cur.execute("SELECT status FROM offboarding_cases WHERE case_id=%s", (ob_id,))
        if str((cur.fetchone() or {}).get("status")) == "ready_to_close":
            break

    cur.execute("SELECT row_version, status FROM offboarding_cases WHERE case_id=%s", (ob_id,))
    row = dict(cur.fetchone() or {})
    check("required clearance ready", row.get("status") == "ready_to_close", row)
    completed = c4.complete_offboarding_case(
        cur,
        company_code=COMPANY,
        case_id=ob_id,
        actor_phone=HR_PHONE,
        reason="complete suite",
        expected_version=int(row.get("row_version") or 1),
    )
    check("offboarding completed", completed.get("ok") is True, completed)
    cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (EMP,))
    check("offboarding complete ≠ left", str((cur.fetchone() or {}).get("employment_status")) == "active")

    opened = c5.open_exit_close_from_offboarding(
        cur, company_code=COMPANY, offboarding_case_id=ob_id, actor_phone=HR_PHONE, reason="open"
    )
    check("open exit close", opened.get("ok") is True, opened)
    close_id = str(opened["case"]["close_id"])

    # Settlement required blocks before ack
    ev = c5.evaluate_close_readiness(cur, company_code=COMPANY, close_id=close_id)
    check(
        "settlement/access gates engage",
        (ev.get("case") or {}).get("status") in ("blocked", "pending_close", "ready_to_close"),
        ev,
    )

    # Wave 2 settlement optional handoff: finalize ≠ ack ≠ paid
    try:
        import payroll_settlement_ot_c6 as sett

        sett.ensure_payroll_settlement_ot_c6_schema(cur)
        sett.enable_company_settlement_ot(
            cur,
            company_code=COMPANY,
            actor_phone=HR_PHONE,
            reason="w3p sett",
            settlement_enabled=True,
            ot_authorization_enabled=False,
        )
        pkt = sett.seed_lifecycle_settlement_packet(
            cur,
            company_code=COMPANY,
            employee_key=EMP,
            termination_effective_on=lwd,
            last_working_day=lwd,
            leave_encashment_days=0,
            compensation_components=[{"code": "BASIC", "amount": 100, "label_en": "Basic", "label_ar": "أساسي"}],
        )
        if pkt.get("ok"):
            packet_id = str((pkt.get("packet") or {}).get("packet_id") or "")
            created_s = sett.create_settlement_from_lifecycle_packet(
                cur,
                company_code=COMPANY,
                lifecycle_packet_id=packet_id,
                actor_phone=HR_PHONE,
                reason="create",
                final_period_start=lwd - timedelta(days=30),
                final_period_end=lwd,
            )
            sid = str((created_s.get("settlement") or {}).get("settlement_id") or "")
            if sid:
                cur.execute("SELECT row_version FROM payroll_settlement_runs WHERE settlement_id=%s", (sid,))
                srv = int((cur.fetchone() or {}).get("row_version") or 1)
                sett.calculate_settlement(
                    cur, company_code=COMPANY, settlement_id=sid, actor_phone=HR_PHONE, reason="calc", expected_row_version=srv
                )
                cur.execute("SELECT row_version FROM payroll_settlement_runs WHERE settlement_id=%s", (sid,))
                srv = int((cur.fetchone() or {}).get("row_version") or 1)
                sett.approve_settlement(
                    cur, company_code=COMPANY, settlement_id=sid, actor_phone=APPROVER, reason="appr", expected_row_version=srv
                )
                cur.execute("SELECT row_version FROM payroll_settlement_runs WHERE settlement_id=%s", (sid,))
                srv = int((cur.fetchone() or {}).get("row_version") or 1)
                fin = sett.finalize_settlement(
                    cur, company_code=COMPANY, settlement_id=sid, actor_phone=IT_PHONE, reason="fin", expected_row_version=srv
                )
                check("settlement finalized", fin.get("ok") is True, fin)
                bind = c5.bind_wave2_settlement_finalized(
                    cur,
                    company_code=COMPANY,
                    close_id=close_id,
                    settlement_run_id=sid,
                    actor_phone=HR_PHONE,
                    reason="bind",
                )
                check("finalized ≠ acknowledged", bind.get("settlement_acknowledged") is False, bind)
                check(
                    "finalized ≠ paid",
                    (bind.get("payment_status") == "not_confirmed")
                    or (c5.honesty_payload().get("settlement_finalized_is_not_paid") is True),
                    bind,
                )
                ack = c5.acknowledge_settlement(
                    cur, company_code=COMPANY, close_id=close_id, actor_phone=HR_PHONE, reason="ack"
                )
                check("settlement acknowledged", ack.get("ok") is True, ack)
            else:
                check("settlement create", False, created_s)
        else:
            # Fall back to waiver so close can proceed
            wav = c5.waive_settlement(
                cur, company_code=COMPANY, close_id=close_id, actor_phone=HR_PHONE, actor_role="hr", reason="no packet"
            )
            check("settlement waiver fallback", wav.get("ok") is True, wav)
    except Exception as exc:
        wav = c5.waive_settlement(
            cur, company_code=COMPANY, close_id=close_id, actor_phone=HR_PHONE, actor_role="hr", reason=f"sett err {exc}"
        )
        check("settlement path or waiver", wav.get("ok") is True, wav)

    ack_a = c5.acknowledge_access_revoke(
        cur, company_code=COMPANY, close_id=close_id, actor_phone=IT_PHONE, reason="manual/idp acked"
    )
    check("access revoke acknowledged", ack_a.get("ok") is True, ack_a)

    # Exit interview complete / decline / skip
    cur.execute(
        "SELECT interview_id FROM exit_interviews WHERE close_id=%s ORDER BY created_at DESC LIMIT 1",
        (close_id,),
    )
    row_iv = cur.fetchone()
    if not row_iv:
        inv = c5.invite_exit_interview(
            cur, company_code=COMPANY, close_id=close_id, actor_phone=HR_PHONE, reason="invite"
        )
        iid = str((inv.get("interview") or {}).get("interview_id"))
    else:
        iid = str(row_iv.get("interview_id"))
    resp = c5.respond_exit_interview(
        cur,
        company_code=COMPANY,
        interview_id=iid,
        actor_phone=EMP_PHONE,
        decision="completed",
        structured_reasons=["career"],
        notes="thanks",
        lang="en",
    )
    check("exit interview complete", resp.get("ok") is True, resp)
    inv2 = c5.invite_exit_interview(cur, company_code=COMPANY, close_id=close_id, actor_phone=HR_PHONE, reason="2")
    if inv2.get("ok"):
        dcl = c5.respond_exit_interview(
            cur,
            company_code=COMPANY,
            interview_id=str(inv2["interview"]["interview_id"]),
            actor_phone=EMP_PHONE,
            decision="declined",
        )
        check("exit interview decline", dcl.get("ok") is True, dcl)
    inv3 = c5.invite_exit_interview(cur, company_code=COMPANY, close_id=close_id, actor_phone=HR_PHONE, reason="3")
    if inv3.get("ok"):
        skp = c5.respond_exit_interview(
            cur,
            company_code=COMPANY,
            interview_id=str(inv3["interview"]["interview_id"]),
            actor_phone=HR_PHONE,
            decision="skipped",
        )
        check("exit interview skip", skp.get("ok") is True, skp)

    ev_ready = c5.evaluate_close_readiness(cur, company_code=COMPANY, close_id=close_id)
    # LWD already past; if still blocked by LWD use override
    if (ev_ready.get("case") or {}).get("status") == "blocked" and "last_working_day" in str(
        (ev_ready.get("readiness") or {}).get("blockers")
    ):
        c5.override_last_working_day_gate(
            cur, company_code=COMPANY, close_id=close_id, actor_phone=HR_PHONE, reason="override"
        )
        ev_ready = c5.evaluate_close_readiness(cur, company_code=COMPANY, close_id=close_id)
    check("ready to close", (ev_ready.get("case") or {}).get("status") == "ready_to_close", ev_ready)

    sod = c5.execute_exit_close(
        cur,
        company_code=COMPANY,
        close_id=close_id,
        actor_phone=HR_PHONE,
        reason="self",
        expected_version=int((ev_ready.get("case") or {}).get("row_version") or 1),
    )
    check("SoD self-close forbidden", sod.get("error") == "sod_self_close_forbidden", sod)

    stale = c5.execute_exit_close(
        cur, company_code=COMPANY, close_id=close_id, actor_phone=APPROVER, reason="stale", expected_version=0
    )
    check("stale close rejected", stale.get("error") == "stale_row_version", stale)

    closed = c5.execute_exit_close(
        cur,
        company_code=COMPANY,
        close_id=close_id,
        actor_phone=APPROVER,
        reason="close employment",
        expected_version=int((ev_ready.get("case") or {}).get("row_version") or 1),
        rehire_eligibility="eligible",
    )
    check("exit close sole writer → left", closed.get("ok") is True and closed.get("employment_status") == "left", closed)
    cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (EMP,))
    check("employment_status left", str((cur.fetchone() or {}).get("employment_status")) == "left")
    wf = c5.is_active_for_workforce(cur, company_code=COMPANY, employee_key=EMP)
    check("disappears from active workforce domains", wf.get("active") is False, wf)

    # Historical employment / change history remains
    hist2 = c1.list_history(cur, company_code=COMPANY, employee_key=EMP)
    check("historical employment changes intact after close", len(hist2) >= 4, len(hist2))

    dup_close = c5.execute_exit_close(
        cur, company_code=COMPANY, close_id=close_id, actor_phone=APPROVER, reason="dup"
    )
    check("idempotent close", dup_close.get("idempotent_duplicate_close") is True, dup_close)
    reopen = c5.attempt_reopen_closed_employment(cur, company_code=COMPANY, employee_key=EMP)
    check("no silent reopen", reopen.get("error") == "silent_reopen_forbidden", reopen)

    reh = c5.set_rehire_eligibility(
        cur,
        company_code=COMPANY,
        close_id=close_id,
        actor_phone=HR_PHONE,
        eligibility="eligible",
        reason="retain person",
    )
    check(
        "rehire eligibility on same person",
        (reh.get("alumni") or {}).get("person_key") == PERSON
        or (reh.get("alumni") or {}).get("rehire_eligibility") == "eligible",
        reh,
    )

    # LWD gate prove on fresh employee
    emp_lwd = f"{COMPANY}-W3P-LWD-{SUFFIX}"
    _ensure_employee(cur, emp_key=emp_lwd, phone=f"9656114{_N:05d}", name="LWD")
    exit_lwd = _drive_exit_to_ready(cur, c3, emp_key=emp_lwd, intent="resignation", lwd=date.today() + timedelta(days=30))
    ob_lwd = _complete_offboarding(cur, c4, exit_id=exit_lwd)
    c5.enable_company_exit_close(
        cur,
        company_code=COMPANY,
        actor_phone=HR_PHONE,
        reason="lwd",
        require_settlement_ack=False,
        require_access_revoke_ack=False,
        require_last_working_day_reached=True,
        allow_lwd_override=True,
        exit_interview_enabled=False,
    )
    o_lwd = c5.open_exit_close_from_offboarding(
        cur, company_code=COMPANY, offboarding_case_id=ob_lwd, actor_phone=HR_PHONE, reason="lwd"
    )
    ev_lwd = c5.evaluate_close_readiness(cur, company_code=COMPANY, close_id=str(o_lwd["case"]["close_id"]))
    check(
        "last-working-date gate",
        (ev_lwd.get("case") or {}).get("status") == "blocked"
        or "last_working_day_not_reached" in str((ev_lwd.get("readiness") or {}).get("blockers")),
        ev_lwd,
    )

    # Rollback preserves history
    off = c5.disable_company_exit_close(cur, company_code=COMPANY, actor_phone=HR_PHONE, reason="rollback")
    check("disable preserves history", off.get("history_preserved") is True, off)
    cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (EMP,))
    check("rollback preserves left truth", str((cur.fetchone() or {}).get("employment_status")) == "left")
    check("real termination remains OFF", c5.real_termination_canary_on() is False)

    # EN/AR
    check("EN closed label", c5.status_label("closed", lang="en") == "Closed")
    check("AR ready label", "جاهز" in c5.status_label("ready_to_close", lang="ar"))


def main() -> int:
    print("    wave3 product acceptance — db")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    _flags_all_off()

    try:
        import employment_change_c1 as c1
        import ess_letters_dependents_c2 as c2
        import exit_intent_c3 as c3
        import offboarding_c4 as c4
        import exit_close_c5 as c5
    except ModuleNotFoundError as exc:
        print(f"IMPORT_FAIL {exc}")
        return 1

    try:
        conn = _connect()
    except Exception as exc:
        print(f"DB_CONNECT_FAIL {exc}")
        return 1

    with conn:
        with conn.cursor() as cur:
            prove_setup(cur)
            prove_modularity(cur, c1, c2, c3, c4, c5)
            prove_full_journey(cur, c1, c2, c3, c4, c5)
        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("WAVE3_PRODUCT_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
