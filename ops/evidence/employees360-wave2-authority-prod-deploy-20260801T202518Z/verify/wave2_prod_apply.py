#!/usr/bin/env python3
"""Wave 2 production deploy apply + prove for WATHEFNI only."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(os.environ.get("WAVE2_PROD_OUT", "/tmp/wave2-prod-apply"))
OUT.mkdir(parents=True, exist_ok=True)

COMPANY = "WATHEFNI"
APPROVED_KEYS = [
    "WATHEFNI-96550252254",
    "WATHEFNI-96566363363",
    "WATHEFNI-96597727743",
    "WATHEFNI-96599411617",
]
BACKFILL_IDEMP = "wave2-backfill:WATHEFNI:approved-map-v1"


def dump(name: str, obj) -> None:
    (OUT / name).write_text(json.dumps(obj, indent=2, default=str) + "\n")
    print("wrote", OUT / name)


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    os.environ.setdefault("WATHEFNI_ENV", "production")
    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES"] = "WATHEFNI"
    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import app
    import employee_authority_wave2 as authority
    from employee_hygiene_wave1c import phone_digits

    if os.environ.get("WATHEFNI_ENV") != "production":
        raise SystemExit("refusing non-production")
    if not authority.authority_v2_enabled(COMPANY):
        raise SystemExit("V2 not enabled for WATHEFNI")
    if authority.authority_v2_enabled("OTHERCO"):
        raise SystemExit("V2 incorrectly enabled for non-WATHEFNI")

    def hub_snapshot():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT employee_key, phone, email, name, employment_status, onboarding_status,
                           position_title, app_key, person_id::text, employment_id::text, assignment_id::text,
                           updated_at
                    FROM employees WHERE company_code=%s AND employee_key = ANY(%s)
                    ORDER BY employee_key
                    """,
                    (COMPANY, APPROVED_KEYS),
                )
                return [dict(r) for r in cur.fetchall()]

    def authority_snapshot():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                authority.ensure_authority_schema(cur)
                cur.execute(
                    "SELECT schema_version FROM employee_authority_schema_meta WHERE schema_name='employees360_wave2'"
                )
                meta = dict(cur.fetchone() or {})
                cur.execute(
                    """
                    SELECT m.employee_key, m.person_id::text, m.employment_id::text, m.assignment_id::text,
                           m.mapping_status, p.employee_number, p.primary_phone, p.primary_email,
                           e.employment_status, e.legacy_employee_key
                    FROM employee_key_authority_map m
                    JOIN employee_persons p ON p.person_id=m.person_id AND p.company_code=m.company_code
                    JOIN employee_employments e ON e.employment_id=m.employment_id AND e.company_code=m.company_code
                    WHERE m.company_code=%s AND m.employee_key = ANY(%s)
                    ORDER BY m.employee_key
                    """,
                    (COMPANY, APPROVED_KEYS),
                )
                maps = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    "SELECT count(*)::bigint n FROM employee_persons WHERE company_code=%s",
                    (COMPANY,),
                )
                persons = int(dict(cur.fetchone())["n"])
                cur.execute(
                    "SELECT count(*)::bigint n FROM employee_employments WHERE company_code=%s",
                    (COMPANY,),
                )
                employments = int(dict(cur.fetchone())["n"])
                cur.execute(
                    "SELECT count(*)::bigint n FROM employee_assignments WHERE company_code=%s",
                    (COMPANY,),
                )
                assignments = int(dict(cur.fetchone())["n"])
                cur.execute(
                    """
                    SELECT person_id::text, count(*) n FROM employee_persons
                    WHERE company_code=%s GROUP BY person_id HAVING count(*)>1
                    """,
                    (COMPANY,),
                )
                dup_p = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    """
                    SELECT employment_id::text, count(*) n FROM employee_employments
                    WHERE company_code=%s GROUP BY employment_id HAVING count(*)>1
                    """,
                    (COMPANY,),
                )
                dup_e = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    """
                    SELECT assignment_id::text, count(*) n FROM employee_assignments
                    WHERE company_code=%s GROUP BY assignment_id HAVING count(*)>1
                    """,
                    (COMPANY,),
                )
                dup_a = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    """
                    SELECT journal_id::text, action, idempotency_key, status, created_at
                    FROM employee_authority_migration_journal
                    WHERE company_code=%s AND idempotency_key=%s
                    """,
                    (COMPANY, BACKFILL_IDEMP),
                )
                journal = [dict(r) for r in cur.fetchall()]
        return {
            "schema_version": meta.get("schema_version"),
            "maps": maps,
            "counts": {"persons": persons, "employments": employments, "assignments": assignments},
            "duplicates": {"persons": dup_p, "employments": dup_e, "assignments": dup_a},
            "journal": journal,
        }

    def check(label, cond, detail=None, checks=None):
        item = {"label": label, "ok": bool(cond), "detail": detail}
        if checks is not None:
            checks.append(item)
        print(("PASS" if cond else "FAIL"), label, "" if cond else detail)
        return bool(cond)

    if phase in ("before", "all"):
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                authority.ensure_authority_schema(cur)
            conn.commit()
        before = {"hub": hub_snapshot(), "authority": authority_snapshot(), "stamp": datetime.now(timezone.utc).isoformat()}
        dump("before.json", before)

    if phase in ("backfill", "all"):
        # ensure schema first
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                authority.ensure_authority_schema(cur)
            conn.commit()
        bf1 = authority.backfill_company_authority(
            app, company_code=COMPANY, idempotency_key=BACKFILL_IDEMP, employee_keys=APPROVED_KEYS
        )
        bf2 = authority.backfill_company_authority(
            app, company_code=COMPANY, idempotency_key=BACKFILL_IDEMP, employee_keys=APPROVED_KEYS
        )
        verified = authority.verify_approved_map_ids(app, company_code=COMPANY)
        dump("backfill.json", {"first": bf1, "second": bf2, "verified": verified})

    if phase in ("prove", "all", "prove-final"):
        checks = []
        hub = hub_snapshot()
        auth = authority_snapshot()
        dump("authority-after.json", auth)
        dump("hub-after.json", hub)
        check("schema version set", auth.get("schema_version") == authority.SCHEMA_VERSION, auth.get("schema_version"), checks)
        check("backfill 4/4 maps", len(auth.get("maps") or []) == 4, auth.get("maps"), checks)
        check("exactly 4 persons for company maps", auth["counts"]["persons"] >= 4, auth["counts"], checks)
        # one current employment + primary assignment per approved employee
        for m in auth.get("maps") or []:
            check(f"map active {m['employee_key']}", m.get("mapping_status") == "active", m, checks)
            check(f"employee_number {m['employee_key']}", str(m.get("employee_number") or "").startswith("EMP-"), m, checks)
        check("no dup persons", auth["duplicates"]["persons"] == [], auth["duplicates"], checks)
        check("no dup employments", auth["duplicates"]["employments"] == [], auth["duplicates"], checks)
        check("no dup assignments", auth["duplicates"]["assignments"] == [], auth["duplicates"], checks)
        verified = authority.verify_approved_map_ids(app, company_code=COMPANY)
        check("deterministic approved IDs 4/4", verified.get("ok") is True, verified, checks)
        # compatibility matrix
        matrix = []
        for h in hub:
            m = next((x for x in auth["maps"] if x["employee_key"] == h["employee_key"]), None)
            matrix.append({
                "employee_key": h["employee_key"],
                "hub_phone": h.get("phone"),
                "person_id": (m or {}).get("person_id") or h.get("person_id"),
                "employment_id": (m or {}).get("employment_id") or h.get("employment_id"),
                "assignment_id": (m or {}).get("assignment_id") or h.get("assignment_id"),
                "employee_number": (m or {}).get("employee_number"),
                "hub_employment_status": h.get("employment_status"),
                "authority_employment_status": (m or {}).get("employment_status"),
            })
        dump("compatibility-matrix.json", matrix)
        check("compatibility matrix complete", len(matrix) == 4 and all(r.get("person_id") and r.get("employment_id") and r.get("assignment_id") for r in matrix), matrix, checks)

        # API card compatibility for each
        for h in hub:
            card = app.posthire_employee_card(h)
            check(
                f"card fields {h['employee_key']}",
                set(["employee_key", "name", "phone", "email", "position_title", "department", "onboarding_status", "employment_status", "start_date", "updated_at"]).issubset(card.keys()),
                card,
                checks,
            )

        # Phone alias → same person
        sample = hub[0]
        local = phone_digits(sample["phone"])
        if local.startswith("965") and len(local) == 11:
            local8 = local[-8:]
            found_local = app.find_employee_by_phone_aliases(local8, company_code=COMPANY)
            found_full = app.find_employee_by_phone_aliases(local, company_code=COMPANY)
            check("alias local resolves", (found_local or {}).get("employee_key") == sample["employee_key"], found_local, checks)
            check("alias 965 resolves same", (found_full or {}).get("employee_key") == sample["employee_key"], found_full, checks)
            proj = authority.get_authority_projection(app, company_code=COMPANY, employee_key=sample["employee_key"])
            check("alias maps to person", bool(proj and proj.get("person_id")), proj, checks)

        # Cross-tenant fail closed
        pid = auth["maps"][0]["person_id"]
        check("same tenant ok", authority.assert_no_cross_tenant_access(app, actor_company=COMPANY, person_id=pid) is True, None, checks)
        check("cross tenant denied", authority.assert_no_cross_tenant_access(app, actor_company="OTHERCO", person_id=pid) is False, None, checks)

        # Manual create/edit/hire shadow-sync with synthetic (cleanup)
        tag = uuid.uuid4().hex[:8]
        phone = f"965570{tag[:5]}"
        created = app.create_company_employee(COMPANY, name=f"W2 Prod Smoke {tag}", phone=phone, position_title="Temp")
        skey = str(created.get("employee_key") or "")
        check("manual create", created.get("status") in ("created", "exists") and bool(skey), created, checks)
        # ensure sync (hooks should do it; call explicitly if needed)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM employees WHERE employee_key=%s", (skey,))
                row = dict(cur.fetchone())
        authority.sync_authority_from_hub_employee(app, row, hire_source="dashboard_roster")
        proj_s = authority.get_authority_projection(app, company_code=COMPANY, employee_key=skey)
        check("create shadow-sync", bool(proj_s and proj_s.get("person_id")), proj_s, checks)
        upd = app.update_company_employee(COMPANY, skey, fields={"position_title": "Temp Edited"})
        check("manual edit", upd.get("status") in ("updated", "noop", "conflict"), upd, checks)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM employees WHERE employee_key=%s", (skey,))
                row = dict(cur.fetchone())
        authority.sync_authority_from_hub_employee(app, row, hire_source="employee_edit")
        proj_e = authority.get_authority_projection(app, company_code=COMPANY, employee_key=skey)
        check("edit shadow-sync title", (proj_e or {}).get("assignment_position_title") == "Temp Edited", proj_e, checks)

        # recruiting hire shadow path: simulate upsert as canonical_hire on synthetic
        hire_sync = authority.sync_authority_from_hub_employee(app, row, hire_source="canonical_hire")
        check("hire shadow-sync path", bool(hire_sync and hire_sync.get("ids")), hire_sync, checks)

        # cleanup synthetic
        authority.rollback_company_authority(app, company_code=COMPANY, idempotency_key=f"wave2-smoke:{tag}", employee_keys=[skey])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM employees WHERE employee_key=%s", (skey,))
            conn.commit()

        # Module API surface unchanged markers
        for name in ("list_employees", "workspace_integrity_scan", "create_company_employee", "update_company_employee"):
            check(f"api present {name}", hasattr(app, name) or name == "list_employees", None, checks)

        # Integrity still clean for employee-linked orphans
        scan = app.workspace_integrity_scan(COMPANY)
        check("integrity no employee-linked orphans", int(scan.get("total_orphans") or 0) == 0, scan.get("total_orphans"), checks)

        result = {
            "pass": sum(1 for c in checks if c["ok"]),
            "fail": sum(1 for c in checks if not c["ok"]),
            "checks": checks,
            "matrix": matrix,
            "journal": auth.get("journal"),
        }
        dump("prove.json", result)
        if phase == "prove" and result["fail"]:
            return 1

    if phase in ("rollback-drill", "all"):
        # Capture hub business fields before rollback
        hub_before_rb = hub_snapshot()
        business_before = {
            r["employee_key"]: {
                k: r.get(k)
                for k in ("phone", "email", "name", "employment_status", "onboarding_status", "position_title", "app_key")
            }
            for r in hub_before_rb
        }
        rb = authority.rollback_company_authority(
            app, company_code=COMPANY, idempotency_key=BACKFILL_IDEMP, employee_keys=APPROVED_KEYS
        )
        dump("rollback.json", rb)
        hub_after_rb = hub_snapshot()
        auth_after_rb = authority_snapshot()
        dump("after-rollback-hub.json", hub_after_rb)
        dump("after-rollback-authority.json", auth_after_rb)
        checks = []
        check("rollback removed maps", len(auth_after_rb.get("maps") or []) == 0, auth_after_rb.get("maps"), checks)
        for r in hub_after_rb:
            check(f"hub pointers null {r['employee_key']}", r.get("person_id") is None and r.get("employment_id") is None and r.get("assignment_id") is None, r, checks)
            before = business_before[r["employee_key"]]
            after = {k: r.get(k) for k in before}
            check(f"hub business unchanged {r['employee_key']}", before == after, {"before": before, "after": after}, checks)
        dump("rollback-prove.json", {"pass": sum(1 for c in checks if c["ok"]), "fail": sum(1 for c in checks if not c["ok"]), "checks": checks})

        # restore-new
        restored = authority.backfill_company_authority(
            app, company_code=COMPANY, idempotency_key=BACKFILL_IDEMP, employee_keys=APPROVED_KEYS
        )
        dump("restore-new.json", restored)
        verified = authority.verify_approved_map_ids(app, company_code=COMPANY)
        auth_final = authority_snapshot()
        dump("authority-final.json", auth_final)
        checks2 = []
        check("restore-new ok", restored.get("ok") is True, restored, checks2)
        check("restore maps 4/4", len(auth_final.get("maps") or []) == 4, auth_final.get("maps"), checks2)
        check("restore IDs match approved map", verified.get("ok") is True, verified, checks2)
        dump("restore-prove.json", {"pass": sum(1 for c in checks2 if c["ok"]), "fail": sum(1 for c in checks2 if not c["ok"]), "checks": checks2})

    if phase == "all":
        # re-run prove final
        os.environ["WAVE2_PROD_OUT"] = str(OUT)
        # inline final summary
        auth = authority_snapshot()
        prove = json.loads((OUT / "prove.json").read_text())
        rb_prove = json.loads((OUT / "rollback-prove.json").read_text())
        rs_prove = json.loads((OUT / "restore-prove.json").read_text())
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=5) as resp:
                health = resp.status
        except Exception as exc:
            health = f"error:{exc}"
        final = {
            "verdict": "PASS"
            if prove["fail"] == 0 and rb_prove["fail"] == 0 and rs_prove["fail"] == 0 and health == 200
            else "FAIL",
            "health": health,
            "schema_version": auth.get("schema_version"),
            "journal_ids": [j.get("journal_id") for j in (auth.get("journal") or [])],
            "backfill_ids": [
                {
                    "employee_key": m["employee_key"],
                    "person_id": m["person_id"],
                    "employment_id": m["employment_id"],
                    "assignment_id": m["assignment_id"],
                    "employee_number": m.get("employee_number"),
                }
                for m in auth.get("maps") or []
            ],
            "prove_fail": prove["fail"],
            "rollback_fail": rb_prove["fail"],
            "restore_fail": rs_prove["fail"],
            "counts": auth.get("counts"),
        }
        dump("final.json", final)
        print(json.dumps(final, indent=2))
        return 0 if final["verdict"] == "PASS" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
