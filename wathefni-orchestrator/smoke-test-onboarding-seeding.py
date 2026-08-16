"""Smoke test: Phase 2 onboarding checklist seeding.

Pins the template-driven seeding engine added in Phase 2:

  - the Default Kuwait template is well-formed: unique item_ids, valid
    categories, and the safety invariant that every required=True item is an
    employee-owned document/text item (so reminders/counts/app never nag for
    HR/system readiness tasks, which are required=False)
  - the dark-launch flag WATHEFNI_ONBOARDING_SEED defaults OFF and gates
    everything (seeding is a no-op while OFF)
  - start_onboarding seeds the full template, flips onboarding_status, and is
    idempotent (re-running never duplicates)
  - roster create is opt-in: start_onboarding=False seeds nothing;
    start_onboarding=True seeds the template
  - top-up: an employee that already has some items (e.g. a pipeline hire) is
    only topped up with the missing items; existing/received items are untouched
  - required rows == the template's employee documents; readiness tasks stay out
    of the pending bucket
  - unknown template_id falls back to Default Kuwait
  - the internal backfill route seeds only in_progress + zero-item employees and
    is a no-op while the flag is OFF

Run (staging has psycopg2): WATHEFNI_DELIVERY_MODE=dry_run python3 smoke-test-onboarding-seeding.py
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
COMPANY = f"ZZSEED{SUFFIX}".upper()
# Full 965-form numbers so the employee_key is stable/predictable.
P1 = "96590000001"
P2 = "96590000002"
P3 = "96590000003"
P4 = "96590000004"
P5 = "96590000005"
P6 = "96590000006"


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def _emp_key(phone: str) -> str:
    return f"{COMPANY}-{phone}"


def _items(app, employee_key: str) -> list[dict]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT item_id, required, status, category, owner, sort_order "
                "FROM onboarding_items WHERE employee_key=%s ORDER BY sort_order",
                (employee_key,),
            )
            return [dict(r) for r in cur.fetchall()]


def _fetch_emp(app, employee_key: str) -> dict | None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM employees WHERE employee_key=%s LIMIT 1", (employee_key,))
            row = cur.fetchone()
            return dict(row) if row else None


def main() -> int:
    print("    onboarding seeding — template invariants + flag gate + seed behaviour")
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    # --- 1) template invariants (no DB) -------------------------------------
    template = app.ONBOARDING_TEMPLATES.get("default_kuwait")
    check("default_kuwait template is registered", isinstance(template, list) and len(template) > 0)
    item_ids = [spec[0] for spec in template]
    check("item_ids are unique", len(item_ids) == len(set(item_ids)))
    check("all categories are valid", all(spec[2] in app.ONBOARDING_ITEM_CATEGORIES for spec in template))
    required_specs = [spec for spec in template if spec[4] is True]
    # Required items must be employee-owned AND have a surface the employee can
    # act on. Documents and text fields qualify; so does the ESS bank task, which
    # has its own employee flow. Anything else would be an HR readiness nag.
    ESS_BACKED_REQUIRED_TASKS = {"bank_details"}
    check(
        "every required item is employee-owned and employee-actionable",
        all(
            spec[5] == "employee"
            and (spec[3] in ("document", "text") or spec[0] in ESS_BACKED_REQUIRED_TASKS)
            for spec in required_specs
        ),
    )
    TOTAL = len(template)
    REQUIRED_IDS = {spec[0] for spec in required_specs}
    check("there is at least one required employee document", len(REQUIRED_IDS) > 0)

    # --- 2) flag helper ------------------------------------------------------
    saved_flag = os.environ.get("WATHEFNI_ONBOARDING_SEED")
    os.environ.pop("WATHEFNI_ONBOARDING_SEED", None)
    check("seed flag defaults OFF when unset", app.onboarding_seed_enabled() is False)
    os.environ["WATHEFNI_ONBOARDING_SEED"] = "off"
    check("seed flag stays OFF for 'off'", app.onboarding_seed_enabled() is False)
    os.environ["WATHEFNI_ONBOARDING_SEED"] = "on"
    check("seed flag flips ON for 'on'", app.onboarding_seed_enabled() is True)

    # --- 3) route registration ----------------------------------------------
    paths = {getattr(r, "path", None) for r in app.app.routes}
    check("seed-missing backfill route is registered", "/orchestrator/onboarding/seed-missing" in paths)

    def cleanup() -> None:
        keys = [_emp_key(p) for p in (P1, P2, P3, P4, P5, P6)]
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM onboarding_items WHERE employee_key = ANY(%s)", (keys,))
                cur.execute("DELETE FROM employees WHERE company_code=%s", (COMPANY,))
                cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
            conn.commit()

    cleanup()
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (COMPANY, "Onboarding Seed Test", app.Json({}), app.Json({})),
                )
            conn.commit()

        # --- 4) flag OFF -> seeding is a no-op even when opted in -----------
        os.environ["WATHEFNI_ONBOARDING_SEED"] = "off"
        r1 = app.create_company_employee(COMPANY, name="Seed One", phone=P1, start_onboarding=True)
        check("create employee succeeds (flag off)", r1.get("status") == "created")
        check("no items seeded while flag OFF", r1.get("onboarding_seeded") == 0)
        check("DB has zero items while flag OFF", len(_items(app, _emp_key(P1))) == 0)

        # --- 5) flag ON, opt-out preserved ----------------------------------
        os.environ["WATHEFNI_ONBOARDING_SEED"] = "on"
        r2 = app.create_company_employee(COMPANY, name="Seed Two", phone=P2, start_onboarding=False)
        check("opt-out create seeds nothing", r2.get("onboarding_seeded") == 0)
        check("DB has zero items for opt-out employee", len(_items(app, _emp_key(P2))) == 0)

        # --- 6) opt-in create seeds the full template -----------------------
        r3 = app.create_company_employee(COMPANY, name="Seed Three", phone=P3, start_onboarding=True)
        check("opt-in create seeds the whole template", r3.get("onboarding_seeded") == TOTAL)
        e3_items = _items(app, _emp_key(P3))
        check("DB item count matches template", len(e3_items) == TOTAL)
        e3_required = {i["item_id"] for i in e3_items if i["required"] is True}
        check("required rows == template employee documents", e3_required == REQUIRED_IDS)
        e3 = _fetch_emp(app, _emp_key(P3))
        check("opt-in create flips onboarding_status to in_progress", (e3 or {}).get("onboarding_status") == "in_progress")
        seeded_row = next((i for i in e3_items if i["category"]), None)
        check("seeded rows carry a category", seeded_row is not None and seeded_row.get("category") in app.ONBOARDING_ITEM_CATEGORIES)
        check("seeded rows carry an owner", any(i.get("owner") in ("employee", "hr", "system") for i in e3_items))

        # readiness tasks stay out of the pending bucket
        summary3 = app.employee_onboarding_summary(e3)
        pending_ids = {str(i.get("item_id")) for i in summary3.get("pending", [])}
        check("pending bucket == required employee documents", pending_ids == REQUIRED_IDS)
        check("a readiness task is NOT in the pending bucket", "first_day_checklist" not in pending_ids)

        # --- 7) start_onboarding seeds + is idempotent ----------------------
        e1 = _fetch_emp(app, _emp_key(P1))
        app.start_onboarding(e1)
        check("start_onboarding seeds the template", len(_items(app, _emp_key(P1))) == TOTAL)
        e1_after = _fetch_emp(app, _emp_key(P1))
        check("start_onboarding sets in_progress", (e1_after or {}).get("onboarding_status") == "in_progress")
        app.start_onboarding(e1)
        check("re-running start_onboarding does not duplicate", len(_items(app, _emp_key(P1))) == TOTAL)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                again = app.seed_onboarding_items(cur, e1)
            conn.commit()
        check("direct re-seed returns 0 (idempotent)", again == 0)

        # --- 8) top-up preserves pre-existing items -------------------------
        preexisting = next(iter(REQUIRED_IDS))
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                # Employee first — onboarding_items has a FK on employee_key.
                cur.execute(
                    "INSERT INTO employees (employee_key, phone, company_code, name, updated_at) "
                    "VALUES (%s,%s,%s,%s, now()) ON CONFLICT (employee_key) DO NOTHING",
                    (_emp_key(P4), P4, COMPANY, "Seed Four"),
                )
                cur.execute(
                    "INSERT INTO onboarding_items (employee_key, item_id, label, item_type, required, document_type, status, raw_json) "
                    "VALUES (%s,%s,'Preexisting','document',true,%s,'received',%s)",
                    (_emp_key(P4), preexisting, preexisting, app.Json({"external": True})),
                )
            conn.commit()
        e4 = _fetch_emp(app, _emp_key(P4))
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                topped = app.seed_onboarding_items(cur, e4)
            conn.commit()
        check("top-up adds only the missing items", topped == TOTAL - 1)
        e4_items = _items(app, _emp_key(P4))
        check("top-up leaves total at template size", len(e4_items) == TOTAL)
        pre_row = next((i for i in e4_items if i["item_id"] == preexisting), None)
        check("pre-existing received item is untouched", pre_row is not None and pre_row.get("status") == "received")

        # --- 9) unknown template_id falls back to Default Kuwait ------------
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO employees (employee_key, phone, company_code, name, updated_at) "
                    "VALUES (%s,%s,%s,%s, now()) ON CONFLICT (employee_key) DO NOTHING",
                    (_emp_key(P5), P5, COMPANY, "Seed Five"),
                )
                e5 = {"employee_key": _emp_key(P5), "company_code": COMPANY}
                fallback = app.seed_onboarding_items(cur, e5, template_id="does_not_exist")
            conn.commit()
        check("unknown template_id falls back to default (full seed)", fallback == TOTAL)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT raw_json FROM onboarding_items WHERE employee_key=%s LIMIT 1",
                    (_emp_key(P5),),
                )
                fallback_meta = (cur.fetchone() or {}).get("raw_json") or {}
        check(
            "unknown template_id records visible fallback metadata",
            fallback_meta.get("template_fallback") is True
            and fallback_meta.get("requested_template") == "does_not_exist"
            and fallback_meta.get("template") == "default_kuwait",
        )
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                resolved_name, resolved_specs, resolved_fallback = app.resolve_onboarding_template(
                    cur, COMPANY, template_id="does_not_exist"
                )
        check(
            "resolve_onboarding_template surfaces fallback_from",
            resolved_name == "default_kuwait"
            and len(resolved_specs) == TOTAL
            and resolved_fallback == "does_not_exist",
        )

        # --- 10) backfill route: only in_progress + zero-item employees -----
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO employees (employee_key, phone, company_code, name, onboarding_status, updated_at) "
                    "VALUES (%s,%s,%s,%s,'in_progress', now()) ON CONFLICT (employee_key) DO NOTHING",
                    (_emp_key(P6), P6, COMPANY, "Seed Six"),
                )
            conn.commit()
        req = app.OnboardingSeedMissingRequest(company_code=COMPANY, dry_run=True)
        internal = {"is_internal": True}
        dry = app.orchestrator_onboarding_seed_missing(req, _internal=internal)
        check("backfill dry-run finds the zero-item in_progress employee", _emp_key(P6) in (dry.get("employee_keys") or []))
        check("backfill dry-run excludes already-seeded employees", _emp_key(P3) not in (dry.get("employee_keys") or []))
        real = app.orchestrator_onboarding_seed_missing(
            app.OnboardingSeedMissingRequest(company_code=COMPANY, dry_run=False), _internal=internal
        )
        check("backfill seeds at least one employee", (real.get("employees_seeded") or 0) >= 1)
        check("backfill seeded the missing employee's items", len(_items(app, _emp_key(P6))) == TOTAL)
        dry2 = app.orchestrator_onboarding_seed_missing(req, _internal=internal)
        check("backfill is idempotent (no candidates left)", _emp_key(P6) not in (dry2.get("employee_keys") or []))

        # --- 11) backfill is a no-op while flag OFF -------------------------
        os.environ["WATHEFNI_ONBOARDING_SEED"] = "off"
        off = app.orchestrator_onboarding_seed_missing(req, _internal=internal)
        check("backfill is disabled while flag OFF", off.get("ok") is False and off.get("reason") == "seeding_disabled")
        os.environ["WATHEFNI_ONBOARDING_SEED"] = "on"
    finally:
        cleanup()
        if saved_flag is None:
            os.environ.pop("WATHEFNI_ONBOARDING_SEED", None)
        else:
            os.environ["WATHEFNI_ONBOARDING_SEED"] = saved_flag

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    ONBOARDING SEEDING: FAILURES")
        return 1
    print("    ONBOARDING SEEDING: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
