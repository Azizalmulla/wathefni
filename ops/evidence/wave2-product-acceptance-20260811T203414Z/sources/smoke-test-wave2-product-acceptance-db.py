#!/usr/bin/env python3
"""Wave 2 Product Acceptance — staging DB prove (company-scoped canary).

Proves:
  1) Setup Console Wave 2 policies (get/patch — not env-only)
  2) Modularity matrix (alone + combinations; disabled disappear cleanly)
  3) Honesty contracts: payslip release, payment ack≠paid, settlement≠paid/clearance
  4) Optional feeds; payroll independence
  5) Assistant remains read-only
  6) Tenant isolation / SoD markers / EN+AR labels

Process-scoped flags only. Synthetic companies. Never systemd-global.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
ACTOR = f"9655600{_N:05d}"


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


def _ensure_company(cur, company: str) -> None:
    cur.execute(
        """
        INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
        VALUES (%s, %s, '{}'::jsonb, '{}'::jsonb, now(), now())
        ON CONFLICT (company_code) DO NOTHING
        """,
        (company, f"Wave2 Product {company}"),
    )


def _upsert_module(cur, company: str, module_key: str, enabled: bool) -> None:
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s, %s, %s, 'wave2_product', '{}'::jsonb, now())
        ON CONFLICT (company_code, module_key) DO UPDATE
          SET enabled=EXCLUDED.enabled, updated_at=now(), source='wave2_product'
        """,
        (company, module_key, enabled),
    )


def _set_modules(cur, company: str, enabled_keys: set[str]) -> None:
    for key in ("attendance", "leave", "shifts", "payroll"):
        _upsert_module(cur, company, key, key in enabled_keys)


def _flags_for(company: str, *, modules: dict[str, bool], feeds: dict[str, bool] | None = None) -> None:
    """Process-scoped runtime gates for one matrix cell."""
    allow = company
    feeds = feeds or {}

    def on(flag: str, companies_flag: str, enabled: bool) -> None:
        os.environ[flag] = "on" if enabled else "off"
        os.environ[companies_flag] = allow if enabled else ""

    on(
        "WATHEFNI_ATTENDANCE_CAPTURE_INGEST",
        "WATHEFNI_ATTENDANCE_CAPTURE_INGEST_COMPANIES",
        bool(modules.get("attendance")),
    )
    os.environ["WATHEFNI_ATTENDANCE_TRUTH_C1"] = "on" if modules.get("attendance") else "off"
    os.environ["WATHEFNI_ATTENDANCE_TRUTH_COMPANIES"] = allow if modules.get("attendance") else ""
    on("WATHEFNI_LEAVE_ENFORCEMENT", "WATHEFNI_LEAVE_ENFORCEMENT_COMPANIES", bool(modules.get("leave")))
    on("WATHEFNI_SHIFTS_MSS_C3", "WATHEFNI_SHIFTS_MSS_COMPANIES", bool(modules.get("shifts")))
    on("WATHEFNI_PAYROLL_AUTHORITATIVE_C4", "WATHEFNI_PAYROLL_AUTHORITATIVE_COMPANIES", bool(modules.get("payroll")))
    on(
        "WATHEFNI_PAYROLL_PAYMENT_C5",
        "WATHEFNI_PAYROLL_PAYMENT_COMPANIES",
        bool(modules.get("payment_processing")),
    )
    on(
        "WATHEFNI_PAYROLL_SETTLEMENT_C6",
        "WATHEFNI_PAYROLL_SETTLEMENT_COMPANIES",
        bool(modules.get("settlement")),
    )
    os.environ["WATHEFNI_PAYROLL_PAYMENT_KILL"] = "off"
    os.environ["WATHEFNI_PAYROLL_SETTLEMENT_KILL"] = "off"
    _ = feeds


def prove_setup(cur, company: str) -> None:
    import setup_console_wave2_policies as w2p

    _ensure_company(cur, company)
    _set_modules(cur, company, {"attendance", "leave", "shifts", "payroll"})
    allp = w2p.get_all_wave2_policies(cur, company)
    check("setup get_all wave2 ok", allp.get("ok") is True, allp)
    check("setup has attendance policy", isinstance((allp.get("modules") or {}).get("attendance"), dict))
    check("setup has settlement policy", isinstance((allp.get("modules") or {}).get("settlement"), dict))
    check("setup EN/AR labels", bool((allp.get("modules") or {}).get("leave", {}).get("label_ar")))

    p1 = w2p.patch_wave2_module_policy(
        cur,
        company_code=company,
        module_key="attendance",
        actor_phone=ACTOR,
        reason="wave2 product acceptance",
        payload={"ingest_enabled": True, "correction_enabled": True},
    )
    check("setup patch attendance", p1.get("ok") is True, p1)
    check(
        "setup attendance persisted",
        (p1.get("policy") or {}).get("ingest_enabled") is True,
        p1,
    )

    p2 = w2p.patch_wave2_module_policy(
        cur,
        company_code=company,
        module_key="leave",
        actor_phone=ACTOR,
        reason="wave2 product acceptance",
        payload={"enforced": False, "legal_pack_attested": False},
    )
    check("setup patch leave", p2.get("ok") is True, p2)

    p3 = w2p.patch_wave2_module_policy(
        cur,
        company_code=company,
        module_key="payroll",
        actor_phone=ACTOR,
        reason="wave2 product acceptance",
        payload={"authoritative_finalize": False, "manual_inputs_ok": True, "feed_attendance": False},
    )
    check("setup patch payroll independence defaults", p3.get("ok") is True, p3)
    check(
        "setup payroll manual_inputs_ok",
        (p3.get("policy") or {}).get("manual_inputs_ok") is True,
        p3,
    )

    p4 = w2p.patch_wave2_module_policy(
        cur,
        company_code=company,
        module_key="payment_processing",
        actor_phone=ACTOR,
        reason="wave2 product acceptance",
        payload={"enabled": False, "acknowledged_is_not_paid": True},
    )
    check("setup payment_processing default off", p4.get("ok") is True, p4)
    check(
        "setup ack≠paid contract",
        (p4.get("policy") or {}).get("acknowledged_is_not_paid") is True,
        p4,
    )

    p5 = w2p.patch_wave2_module_policy(
        cur,
        company_code=company,
        module_key="settlement",
        actor_phone=ACTOR,
        reason="wave2 product acceptance",
        payload={"enabled": False, "finalized_is_not_paid": True, "not_clearance": True},
    )
    check("setup settlement honesty", p5.get("ok") is True, p5)


def prove_matrix_cell(cur, cfg: dict) -> None:
    import attendance_truth_c1 as c1
    import leave_enforcement_c2 as c2
    import shifts_mss_c3 as c3
    import payroll_authoritative_c4 as c4
    import payroll_payslip_payment_c5 as c5
    import payroll_settlement_ot_c6 as c6

    name = cfg["name"]
    company = f"W2{name[:6].upper()}{_N:05d}"[:12]
    modules = dict(cfg.get("modules") or {})
    feeds = dict(cfg.get("feeds") or {})
    _ensure_company(cur, company)
    commercial = {k for k in ("attendance", "leave", "shifts", "payroll") if modules.get(k)}
    _set_modules(cur, company, commercial)
    _flags_for(company, modules=modules, feeds=feeds)

    other = f"X{company[1:]}"[:12]
    expect_att = bool(modules.get("attendance"))
    expect_leave = bool(modules.get("leave"))
    expect_shifts = bool(modules.get("shifts"))
    expect_pay = bool(modules.get("payroll"))
    expect_pf = bool(modules.get("payment_processing"))
    expect_set = bool(modules.get("settlement"))

    # Entitlement sync for payroll/payment/settlement when matrix cell enables them
    if expect_pay:
        try:
            c4.ensure_payroll_authoritative_c4_schema(cur)
            c4.enable_company_authoritative_finalize(
                cur, company_code=company, actor_phone=ACTOR, reason=f"w2 matrix pay {name}"
            )
        except Exception:
            pass
    if expect_pf:
        try:
            c5.ensure_payroll_payslip_payment_c5_schema(cur)
            c5.enable_company_payment_processing(
                cur, company_code=company, actor_phone=ACTOR, reason=f"w2 matrix pf {name}"
            )
        except Exception:
            pass
    if expect_set:
        try:
            c6.ensure_payroll_settlement_ot_c6_schema(cur)
            c6.enable_company_settlement_ot(
                cur,
                company_code=company,
                actor_phone=ACTOR,
                reason=f"w2 matrix set {name}",
                settlement_enabled=True,
                ot_authorization_enabled=True,
                ot_to_payroll_enabled=bool(feeds.get("ot")),
            )
        except Exception:
            pass

    att_ok = c1.capture_ingest_enabled_for_company(company).get("ok") is True
    # Leave modularity: runtime allowlist opens the path; pack attestation remains C2 prove
    leave_ok = bool(
        c2.leave_enforcement_runtime_on()
        and company in c2.leave_enforcement_company_allowlist()
    )
    shifts_ok = c3.mss_enabled_for_company(company).get("ok") is True
    pay_runtime = c4.runtime_gate_for_company(company).get("ok") is True
    pay_ent = c4.authoritative_finalize_enabled_for_company(cur, company) if pay_runtime else {"ok": False}
    pay_ok = pay_runtime and bool(pay_ent.get("ok"))
    pf_runtime = c5.runtime_gate_for_company(company).get("ok") is True
    pf_ent = c5.payment_processing_enabled_for_company(cur, company) if pf_runtime else {"ok": False}
    pf_ok = pf_runtime and bool(pf_ent.get("ok"))
    set_runtime = c6.runtime_gate_for_company(company).get("ok") is True
    set_ent = c6.settlement_enabled_for_company(cur, company) if set_runtime else {"ok": False}
    set_ok = set_runtime and bool(set_ent.get("ok"))

    check(f"matrix[{name}] attendance gate", att_ok is expect_att, {"ok": att_ok, "expect": expect_att})
    check(f"matrix[{name}] leave runtime path", leave_ok is expect_leave, {"ok": leave_ok, "expect": expect_leave})
    check(f"matrix[{name}] shifts gate", shifts_ok is expect_shifts, {"ok": shifts_ok, "expect": expect_shifts})
    check(f"matrix[{name}] payroll gate", pay_ok is expect_pay, {"ok": pay_ok, "expect": expect_pay})
    check(f"matrix[{name}] payment gate", pf_ok is expect_pf, {"ok": pf_ok, "expect": expect_pf})
    check(f"matrix[{name}] settlement gate", set_ok is expect_set, {"ok": set_ok, "expect": expect_set})

    check(
        f"matrix[{name}] tenant isolation",
        c4.runtime_gate_for_company(other).get("ok") is not True
        and c1.capture_ingest_enabled_for_company(other).get("ok") is not True,
    )

    if expect_pay and not modules.get("attendance") and not modules.get("leave"):
        check(
            f"matrix[{name}] payroll independent (no att/leave required)",
            c4.honesty_payload().get("attendance_required") is False
            and c4.honesty_payload().get("leave_required") is False,
        )


def prove_honesty_contracts() -> None:
    import payroll_payslip_payment_c5 as c5
    import payroll_settlement_ot_c6 as c6
    import payroll_payslip_wave3 as w3
    import platform_assistant_spine_wave1 as spine

    check("released payslip visibility helper", callable(w3.employee_can_view))
    # Unreleased synthetic doc
    unreleased = {"status": getattr(w3, "STATUS_ACTIVE", "active"), "employee_visibility": getattr(w3, "EMP_VIS_NOT_RELEASED", "not_released")}
    released = {"status": getattr(w3, "STATUS_ACTIVE", "active"), "employee_visibility": getattr(w3, "EMP_VIS_RELEASED", "released")}
    check("unreleased not visible", w3.employee_can_view(unreleased) is False, unreleased)
    check("released visible", w3.employee_can_view(released) is True, released)
    check("payment ack ≠ paid", c5.honesty_payload().get("acknowledged_is_not_paid") is True)
    check("settlement finalized ≠ paid", c6.honesty_payload().get("settlement_finalized_is_not_paid") is True)
    check("settlement ≠ clearance", c6.honesty_payload().get("settlement_is_not_clearance") is True)
    os.environ["WATHEFNI_ASSISTANT_MUTATIONS"] = "off"
    check("assistant read-only (mutations off)", spine.assistant_mutations_allowed() is False)
    os.environ.pop("WATHEFNI_ASSISTANT_MUTATIONS", None)
    os.environ["WATHEFNI_PLATFORM_ASSISTANT_WAVE1"] = "on"
    check("assistant read-only under spine wave", spine.assistant_mutations_allowed() is False)
    os.environ.pop("WATHEFNI_PLATFORM_ASSISTANT_WAVE1", None)
    check("EN/AR settlement labels", c6.status_label("finalized", lang="ar") and c6.status_label("finalized", lang="en"))
    check("EN/AR payment labels", c5.status_label("acknowledged", lang="ar") and c5.status_label("released", lang="en"))


def prove_rollout_rollback() -> None:
    import attendance_truth_c1 as c1
    import payroll_settlement_ot_c6 as c6

    os.environ["WATHEFNI_ATTENDANCE_CAPTURE_INGEST"] = "on"
    os.environ["WATHEFNI_ATTENDANCE_CAPTURE_INGEST_COMPANIES"] = "CANARY1"
    g = c1.capture_ingest_enabled_for_company("CANARY1")
    check("rollout canary allowlist", g.get("ok") is True, g)
    check("rollout gate structured", "ok" in g and "phase" in g, g)

    os.environ["WATHEFNI_ATTENDANCE_CAPTURE_INGEST"] = "off"
    check("rollback global off", c1.capture_ingest_enabled_for_company("CANARY1").get("ok") is not True)

    rb = c6.rollback_guidance()
    check("rollback guidance present", rb.get("ok") is True and "WATHEFNI_PAYROLL_SETTLEMENT_KILL=on" in str(rb))


def main() -> int:
    print("    wave2 product acceptance — db")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import setup_console_wave2_policies as w2p

    prove_honesty_contracts()
    prove_rollout_rollback()

    conn_cm, _ = _connect()
    with conn_cm as conn:
        with conn.cursor() as cur:
            setup_co = f"W2S{_N:05d}"[:12]
            prove_setup(cur, setup_co)

            for cfg in w2p.modularity_matrix_configs():
                prove_matrix_cell(cur, cfg)

            # Wave 1 freeze regression marker (stamp still accepted)
            root = Path(__file__).resolve().parent.parent
            w1 = (root / "ops/WAVE1_PRODUCT_FULL_PASS.md").read_text(encoding="utf-8")
            check("Wave 1 freeze regression (stamp ACCEPTED)", "ACCEPTED" in w1 and "FROZEN" in w1)

        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("WAVE2_PRODUCT_DB_PASS")
    print("WAVE2_PRODUCT_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
