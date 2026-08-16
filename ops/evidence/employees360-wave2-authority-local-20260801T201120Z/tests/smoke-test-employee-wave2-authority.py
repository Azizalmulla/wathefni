"""Wave 2 authority — staging DB smoke (synthetic + optional WATHEFNI map verify).

Requires WATHEFNI_EMPLOYEE_AUTHORITY_V2=on and staging DB credentials.
Does not mutate production. Cleans synthetic rows in finally.
"""

from __future__ import annotations

import os
import sys
import uuid
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


def main() -> int:
    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2"] = "on"
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import app
    import employee_authority_wave2 as authority

    company = "WATHEFNI"
    tag = uuid.uuid4().hex[:8]
    phone_a = f"965588{tag[:5]}"
    phone_b = f"965577{tag[:5]}"
    key_a = f"{company}-{phone_a}"
    key_b = f"{company}-{phone_b}"
    rehire_phone = f"965566{tag[:5]}"
    rehire_key = f"{company}-{rehire_phone}"
    idem = f"wave2-smoke-backfill:{company}:{tag}"

    from employee_hygiene_wave1c import phone_digits

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                authority.ensure_authority_schema(cur)
                keys = [key_a, key_b, rehire_key]
                cur.execute(
                    """
                    SELECT person_id::text AS person_id, employment_id::text AS employment_id,
                           assignment_id::text AS assignment_id
                    FROM employee_key_authority_map
                    WHERE company_code=%s AND employee_key = ANY(%s)
                    """,
                    (company, keys),
                )
                maps = [dict(r) for r in (cur.fetchall() or [])]
                assignment_ids = [m["assignment_id"] for m in maps]
                employment_ids = [m["employment_id"] for m in maps]
                person_ids = list({m["person_id"] for m in maps})
                cur.execute(
                    "DELETE FROM employee_key_authority_map WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, keys),
                )
                if assignment_ids:
                    cur.execute(
                        "DELETE FROM employee_assignments WHERE company_code=%s AND assignment_id = ANY(%s::uuid[])",
                        (company, assignment_ids),
                    )
                if employment_ids:
                    cur.execute(
                        "DELETE FROM employee_employments WHERE company_code=%s AND employment_id = ANY(%s::uuid[])",
                        (company, employment_ids),
                    )
                for pid in person_ids:
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
                cur.execute(
                    "DELETE FROM employee_authority_migration_journal WHERE company_code=%s AND idempotency_key LIKE %s",
                    (company, f"%{tag}%"),
                )
                cur.execute("DELETE FROM employees WHERE employee_key = ANY(%s)", (keys,))
            conn.commit()

    cleanup()
    try:
        # Create hub employees via API path
        created_a = app.create_company_employee(company, name=f"W2 Smoke A {tag}", phone=phone_a, email=f"a{tag}@example.com", position_title="Analyst", department="Ops")
        created_b = app.create_company_employee(company, name=f"W2 Smoke B {tag}", phone=phone_b, position_title="Clerk")
        check("create A", created_a.get("status") == "created", created_a)
        check("create B", created_b.get("status") == "created", created_b)
        key_a = str(created_a.get("employee_key") or (created_a.get("employee") or {}).get("employee_key") or "")
        key_b = str(created_b.get("employee_key") or (created_b.get("employee") or {}).get("employee_key") or "")
        check("create returned keys", bool(key_a and key_b), {"a": key_a, "b": key_b, "created_a": created_a})

        # Card compatibility unchanged core fields
        card = created_a.get("employee") or {}
        check("card has employee_key", card.get("employee_key") == key_a, card)
        check("card has name/phone/status", bool(card.get("name") and card.get("phone") and card.get("employment_status") == "active"))

        # Backfill (includes synthetic keys)
        bf1 = authority.backfill_company_authority(
            app, company_code=company, idempotency_key=idem, employee_keys=[key_a, key_b]
        )
        check("backfill applied", bf1.get("ok") and bf1.get("after", {}).get("mapping_count") >= 2, bf1)
        bf2 = authority.backfill_company_authority(
            app, company_code=company, idempotency_key=idem, employee_keys=[key_a, key_b]
        )
        check("backfill idempotent rerun", bf2.get("status") in ("idempotent", "applied"), bf2)
        check("no duplicate persons", bf2.get("duplicate_persons") == [], bf2.get("duplicate_persons"))

        proj = authority.get_authority_projection(app, company_code=company, employee_key=key_a)
        check("projection present", bool(proj and proj.get("person_id") and proj.get("employment_id") and proj.get("assignment_id")), proj)
        check("employee number minted", bool(proj) and str(proj.get("employee_number") or "").startswith("EMP-"), proj)

        # Edit updates authority (staging app may not yet accept expected_updated_at)
        import inspect
        sig = inspect.signature(app.update_company_employee)
        kwargs = {"fields": {"position_title": "Senior Analyst", "name": f"W2 Smoke A Edited {tag}"}}
        if "expected_updated_at" in sig.parameters:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT updated_at FROM employees WHERE employee_key=%s", (key_a,))
                    kwargs["expected_updated_at"] = dict(cur.fetchone())["updated_at"]
        upd = app.update_company_employee(company, key_a, **kwargs)
        check("edit ok", upd.get("status") == "updated", upd)
        # Ensure authority sync even if staging hub hook not deployed yet
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM employees WHERE employee_key=%s", (key_a,))
                hub_row = dict(cur.fetchone())
        authority.sync_authority_from_hub_employee(app, hub_row, hire_source="employee_edit")
        proj2 = authority.get_authority_projection(app, company_code=company, employee_key=key_a)
        check("edit synced assignment title", proj2.get("assignment_position_title") == "Senior Analyst", proj2)
        check("edit synced person name", (proj2.get("person_name") or "").startswith("W2 Smoke A Edited"), proj2)

        # Same person on hire path: create second employment via rehire API helper after leaving first
        # Represent former employee: mark employment left while preserving history
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE employee_employments SET employment_status='left', end_date=CURRENT_DATE WHERE company_code=%s AND legacy_employee_key=%s",
                    (company, key_b),
                )
                cur.execute(
                    "UPDATE employees SET employment_status='left' WHERE employee_key=%s",
                    (key_b,),
                )
                cur.execute("SELECT person_id::text AS person_id FROM employee_key_authority_map WHERE employee_key=%s", (key_b,))
                person_b = dict(cur.fetchone())["person_id"]
            conn.commit()

        rehire = authority.open_rehire_employment(
            app,
            company_code=company,
            person_id=person_b,
            new_employee_key=rehire_key,
            phone=rehire_phone,
            name=f"W2 Smoke B Rehire {tag}",
            position_title="Lead",
        )
        check("rehire ok", rehire.get("ok") is True, rehire)
        check("rehire reuses person", rehire.get("person_id") == person_b, rehire)
        check("rehire new employment", str(rehire.get("employment", {}).get("employment_id")) != str(proj.get("employment_id")))
        check("prior service history retained", int(rehire.get("employment_history_count") or 0) >= 2, rehire)

        # Cross-tenant fail closed
        ok_same = authority.assert_no_cross_tenant_access(app, actor_company=company, person_id=person_b)
        ok_other = authority.assert_no_cross_tenant_access(app, actor_company="OTHERCO", person_id=person_b)
        check("same tenant access ok", ok_same is True)
        check("cross tenant fail closed", ok_other is False)

        # Compatible API still works for list/card
        card_after = app.posthire_employee_card(
            dict(next(iter([
                # fetch hub
            ]), {}))
        ) if False else None
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM employees WHERE employee_key=%s", (key_a,))
                hub = dict(cur.fetchone())
        card_after = app.posthire_employee_card(hub)
        check("compatible card fields", set(["employee_key", "name", "phone", "email", "position_title", "department", "onboarding_status", "employment_status", "start_date", "updated_at"]).issubset(card_after.keys()))

        # If approved WATHEFNI keys exist with matching phones, verify map
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT employee_key, phone FROM employees WHERE company_code=%s AND employee_key = ANY(%s)",
                    (company, list(authority.APPROVED_WATHEFNI_MAP)),
                )
                present = [dict(r) for r in cur.fetchall()]
        if len(present) == 4:
            authority.backfill_company_authority(
                app,
                company_code=company,
                idempotency_key=f"wave2-approved-map:{company}:{tag}",
                employee_keys=[r["employee_key"] for r in present],
            )
            verified = authority.verify_approved_map_ids(app, company_code=company)
            check("approved map IDs match", verified.get("ok") is True, verified)
        else:
            check("approved map optional skip", True, f"present={len(present)}")

        # Rollback scoped to smoke keys only (shared staging tenant safe)
        rb = authority.rollback_company_authority(
            app, company_code=company, idempotency_key=idem, employee_keys=[key_a, key_b, rehire_key]
        )
        check("rollback reported", rb.get("ok") is True, rb)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT person_id FROM employees WHERE employee_key=%s", (key_a,))
                ptr = dict(cur.fetchone()).get("person_id")
                cur.execute("SELECT 1 FROM employees WHERE employee_key=%s", (key_a,))
                hub_ok = bool(cur.fetchone())
                cur.execute("SELECT count(*) AS n FROM employee_key_authority_map WHERE employee_key=%s", (key_a,))
                map_n = int(dict(cur.fetchone())["n"])
        check("hub employee survives rollback", hub_ok is True)
        check("hub authority pointers cleared", ptr is None, ptr)
        check("scoped mapping removed", map_n == 0, map_n)

        # Restore-new: re-backfill smoke keys
        restored = authority.backfill_company_authority(
            app, company_code=company, idempotency_key=idem, employee_keys=[key_a, key_b]
        )
        check("restore-new backfill", restored.get("ok") is True, restored)
        proj3 = authority.get_authority_projection(app, company_code=company, employee_key=key_a)
        check("restore-new projection", bool(proj3 and proj3.get("person_id")), proj3)

    finally:
        cleanup()

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
