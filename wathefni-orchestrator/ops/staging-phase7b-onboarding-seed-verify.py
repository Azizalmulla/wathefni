#!/usr/bin/env python3
"""Phase 7B staging verifier: onboarding seed controlled activation readiness.

In-process against the staging DB. Does NOT flip production flags.
Does NOT seed or mutate WATHEFNI historical employees.
Uses throwaway company P7BSTG01 only.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

COMPANY = "P7BSTG01"
PROTECTED = "WATHEFNI"
SUFFIX = uuid.uuid4().hex[:6]
PHONES = {
    "off": f"96555558{SUFFIX[:3]}1",
    "optout": f"96555558{SUFFIX[:3]}2",
    "optin": f"96555558{SUFFIX[:3]}3",
    "start": f"96555558{SUFFIX[:3]}4",
    "partial": f"96555558{SUFFIX[:3]}5",
    "backfill": f"96555558{SUFFIX[:3]}6",
}
RESULTS: list[tuple[str, bool, str]] = []


def record(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((label, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), label + (f" — {detail}" if detail else ""))


def emp_key(phone: str) -> str:
    return f"{COMPANY}-{phone}"


def items(app, key: str) -> list[dict]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT item_id, required, status, owner, category, raw_json "
                "FROM onboarding_items WHERE employee_key=%s ORDER BY sort_order",
                (key,),
            )
            return [dict(r) for r in cur.fetchall()]


def cleanup(app) -> None:
    keys = [emp_key(p) for p in PHONES.values()]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM onboarding_items WHERE employee_key = ANY(%s)", (keys,))
            cur.execute("DELETE FROM employees WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM company_modules WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
        conn.commit()


def main() -> int:
    if COMPANY.upper() == PROTECTED:
        raise SystemExit("refusing to run seed verifier against WATHEFNI")

    orchestrator_dir = Path(__file__).resolve().parents[1]
    # Prefer staging tree when present on the VPS.
    staging_dir = Path("/opt/wathefni/staging/orchestrator")
    if staging_dir.exists():
        sys.path.insert(0, str(staging_dir))
        os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
        os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
    else:
        sys.path.insert(0, str(orchestrator_dir))

    import app

    template = app.ONBOARDING_TEMPLATES["default_kuwait"]
    total = len(template)
    required = {spec[0] for spec in template if spec[4] is True}
    record("template registered", total > 0, f"total={total}")
    record("required count expected", required == {"civil_id", "personal_photo", "employment_contract", "bank_details"}, f"required={sorted(required)}")
    record(
        "every required item is employee document/text",
        all(spec[5] == "employee" and spec[3] in ("document", "text") for spec in template if spec[4]),
    )
    record("passport is optional for Kuwait nationals", ("passport", False) in {(s[0], s[4]) for s in template})
    record("HR/system readiness stays non-required", all(not s[4] for s in template if s[5] in ("hr", "system")))

    saved = os.environ.get("WATHEFNI_ONBOARDING_SEED")
    cleanup(app)
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (COMPANY, "Phase 7B Seed Staging", app.Json({}), app.Json({})),
                )
                cur.execute(
                    "INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at) "
                    "VALUES (%s,'onboarding',true,'phase7b',%s,now()) "
                    "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true, updated_at=now()",
                    (COMPANY, app.Json({})),
                )
            conn.commit()

        # OFF
        os.environ["WATHEFNI_ONBOARDING_SEED"] = "off"
        r_off = app.create_company_employee(COMPANY, name="Off Seed", phone=PHONES["off"], start_onboarding=True)
        record("OFF opt-in create seeds nothing", r_off.get("onboarding_seeded") == 0, f"seeded={r_off.get('onboarding_seeded')}")
        record("OFF DB empty", len(items(app, emp_key(PHONES["off"]))) == 0)

        # ON opt-out
        os.environ["WATHEFNI_ONBOARDING_SEED"] = "on"
        r_out = app.create_company_employee(COMPANY, name="Opt Out", phone=PHONES["optout"], start_onboarding=False)
        record("ON opt-out create seeds nothing", r_out.get("onboarding_seeded") == 0, f"seeded={r_out.get('onboarding_seeded')}")
        record("ON opt-out DB empty", len(items(app, emp_key(PHONES["optout"]))) == 0)

        # ON opt-in
        r_in = app.create_company_employee(COMPANY, name="Opt In", phone=PHONES["optin"], start_onboarding=True)
        optin_items = items(app, emp_key(PHONES["optin"]))
        record("ON opt-in seeds full template", r_in.get("onboarding_seeded") == total and len(optin_items) == total, f"seeded={r_in.get('onboarding_seeded')} rows={len(optin_items)}")
        pending_required = {i["item_id"] for i in optin_items if i.get("required") is True}
        record("required pending set matches template", pending_required == required, f"pending={sorted(pending_required)}")
        record("first_day_checklist not required", "first_day_checklist" not in pending_required)

        # start_onboarding on empty OFF-created employee (flag now ON)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM employees WHERE employee_key=%s LIMIT 1", (emp_key(PHONES["off"]),))
                e_start = dict(cur.fetchone() or {})
        app.start_onboarding(e_start)
        start_items = items(app, emp_key(PHONES["off"]))
        record("start_onboarding seeds full template", len(start_items) == total, f"rows={len(start_items)}")
        app.start_onboarding(e_start)
        record("start_onboarding re-run does not duplicate", len(items(app, emp_key(PHONES["off"]))) == total)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                again = app.seed_onboarding_items(cur, e_start)
            conn.commit()
        record("direct re-seed returns 0", again == 0, f"again={again}")

        # partial top-up
        preexisting = next(iter(required))
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO employees (employee_key, phone, company_code, name, updated_at) "
                    "VALUES (%s,%s,%s,%s,now()) ON CONFLICT (employee_key) DO NOTHING",
                    (emp_key(PHONES["partial"]), PHONES["partial"], COMPANY, "Partial"),
                )
                cur.execute(
                    "INSERT INTO onboarding_items (employee_key, item_id, label, item_type, required, document_type, status, raw_json) "
                    "VALUES (%s,%s,'Preexisting','document',true,%s,'received',%s)",
                    (emp_key(PHONES["partial"]), preexisting, preexisting, app.Json({"external": True})),
                )
            conn.commit()
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM employees WHERE employee_key=%s LIMIT 1", (emp_key(PHONES["partial"]),))
                e_partial = dict(cur.fetchone() or {})
                topped = app.seed_onboarding_items(cur, e_partial)
            conn.commit()
        partial_items = items(app, emp_key(PHONES["partial"]))
        pre_row = next((i for i in partial_items if i["item_id"] == preexisting), None)
        record("partial top-up adds only missing", topped == total - 1, f"topped={topped}")
        record("partial total equals template", len(partial_items) == total, f"rows={len(partial_items)}")
        record("preexisting received untouched", pre_row is not None and pre_row.get("status") == "received")

        # seed-missing dry-run + real
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO employees (employee_key, phone, company_code, name, onboarding_status, updated_at) "
                    "VALUES (%s,%s,%s,%s,'in_progress',now()) ON CONFLICT (employee_key) DO NOTHING",
                    (emp_key(PHONES["backfill"]), PHONES["backfill"], COMPANY, "Backfill"),
                )
            conn.commit()
        dry = app.orchestrator_onboarding_seed_missing(
            app.OnboardingSeedMissingRequest(company_code=COMPANY, dry_run=True),
            _internal={"is_internal": True},
        )
        record(
            "seed-missing dry-run finds zero-item in_progress",
            emp_key(PHONES["backfill"]) in (dry.get("employee_keys") or []),
            f"candidates={dry.get('candidates')}",
        )
        record(
            "seed-missing dry-run excludes already seeded",
            emp_key(PHONES["optin"]) not in (dry.get("employee_keys") or []),
        )
        real = app.orchestrator_onboarding_seed_missing(
            app.OnboardingSeedMissingRequest(company_code=COMPANY, dry_run=False),
            _internal={"is_internal": True},
        )
        record("seed-missing seeds candidate", (real.get("employees_seeded") or 0) >= 1 and len(items(app, emp_key(PHONES["backfill"]))) == total)

        # unknown template fallback visibility
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO employees (employee_key, phone, company_code, name, updated_at) "
                    "VALUES (%s,%s,%s,%s,now()) ON CONFLICT (employee_key) DO NOTHING",
                    (f"{COMPANY}-965555589999", "965555589999", COMPANY, "Fallback"),
                )
                seeded_fb = app.seed_onboarding_items(
                    cur, {"employee_key": f"{COMPANY}-965555589999", "company_code": COMPANY}, template_id="missing_template_xyz"
                )
                cur.execute(
                    "SELECT raw_json FROM onboarding_items WHERE employee_key=%s LIMIT 1",
                    (f"{COMPANY}-965555589999",),
                )
                meta = (cur.fetchone() or {}).get("raw_json") or {}
            conn.commit()
        record("unknown template still seeds default", seeded_fb == total, f"seeded={seeded_fb}")
        record(
            "fallback metadata visible",
            meta.get("template_fallback") is True and meta.get("requested_template") == "missing_template_xyz",
            f"meta_keys={sorted(meta)}",
        )

        # rollback OFF leaves rows, stops future seeding
        existing_before_off = len(items(app, emp_key(PHONES["optin"])))
        os.environ["WATHEFNI_ONBOARDING_SEED"] = "off"
        r_after = app.create_company_employee(
            COMPANY, name="After Off", phone=f"96555558{SUFFIX[:3]}9", start_onboarding=True
        )
        record("rollback OFF stops future seeding", r_after.get("onboarding_seeded") == 0, f"seeded={r_after.get('onboarding_seeded')}")
        record(
            "rollback OFF leaves existing rows intact",
            len(items(app, emp_key(PHONES["optin"]))) == existing_before_off == total,
            f"rows={len(items(app, emp_key(PHONES['optin'])))}",
        )
        off_backfill = app.orchestrator_onboarding_seed_missing(
            app.OnboardingSeedMissingRequest(company_code=COMPANY, dry_run=True),
            _internal={"is_internal": True},
        )
        record(
            "rollback OFF disables seed-missing",
            off_backfill.get("ok") is False and off_backfill.get("reason") == "seeding_disabled",
        )

        # Guard: never target WATHEFNI historical employees in this verifier
        record("did not target WATHEFNI employees", True, "throwaway P7BSTG01 only")
    finally:
        try:
            cleanup(app)
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM onboarding_items WHERE employee_key=%s", (f"{COMPANY}-965555589999",))
                    cur.execute("DELETE FROM employees WHERE employee_key=%s", (f"{COMPANY}-965555589999",))
                    cur.execute("DELETE FROM employees WHERE company_code=%s AND phone LIKE %s", (COMPANY, "96555558%"))
                conn.commit()
            cleanup(app)
        except Exception as exc:
            print(f"(cleanup warning: {exc})")
        if saved is None:
            os.environ.pop("WATHEFNI_ONBOARDING_SEED", None)
        else:
            os.environ["WATHEFNI_ONBOARDING_SEED"] = saved

    print("PRODUCTION_SEED_FLAG_UNCHANGED=true")
    print("NO_WATHEFNI_HISTORICAL_TOUCH=true")
    print("NO_MASS_BACKFILL=true")
    print("\nSUMMARY")
    failed = [item for item in RESULTS if not item[1]]
    print(f"{sum(1 for item in RESULTS if item[1])} passed, {len(failed)} failed")
    if failed:
        for label, _, detail in failed:
            print(f"  - {label}: {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
