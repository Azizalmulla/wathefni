#!/usr/bin/env python3
"""Wave 1C production apply — exact qualified hygiene remediations only.

Applies:
  - WATHEFNI-96597727743 null → active
  - WATHEFNI-96550252254 null → active
  - quarantine 3 orphan employee_messages for WATHEFNI-P0-DUP-1

Supports phases: before | apply | prove | rollback | restore | all
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(os.environ.get("WAVE1C_PROD_OUT", "/tmp/wave1c-prod-apply"))
OUT.mkdir(parents=True, exist_ok=True)

COMPANY = "WATHEFNI"
NULL_KEYS = ("WATHEFNI-96597727743", "WATHEFNI-96550252254")
ORPHAN_KEY = "WATHEFNI-P0-DUP-1"
STATUS_IDEMP = {
    "WATHEFNI-96597727743": "wave1c-null-status:WATHEFNI-96597727743:active",
    "WATHEFNI-96550252254": "wave1c-null-status:WATHEFNI-96550252254:active",
}
ORPHAN_IDEMP = "wave1c-quarantine:WATHEFNI-P0-DUP-1"


def dump(name: str, obj) -> None:
    path = OUT / name
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")
    print(f"wrote {path}")


def live_evidence(app, employee_key: str) -> dict:
    """Rebuild evidence gate inputs from live prod (no guessing)."""
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM employees WHERE employee_key=%s AND company_code=%s", (employee_key, COMPANY))
            emp = dict(cur.fetchone() or {})
            app_key = emp.get("app_key")
            apps = []
            if app_key:
                cur.execute(
                    "SELECT app_key, status, company_code FROM applications WHERE app_key=%s",
                    (app_key,),
                )
                apps = [dict(r) for r in cur.fetchall()]
            counts = {}
            for table in (
                "attendance_records",
                "shift_assignments",
                "leave_requests",
                "employee_messages",
                "employee_status_changes",
                "onboarding_items",
                "compliance_documents",
            ):
                cur.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
                    (table,),
                )
                if not cur.fetchone():
                    counts[table] = {"count": 0}
                    continue
                cur.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
                    (table,),
                )
                cols = {r["column_name"] for r in cur.fetchall()}
                if "company_code" in cols and "employee_key" in cols:
                    cur.execute(
                        f"SELECT count(*)::bigint AS n FROM {table} WHERE company_code=%s AND employee_key=%s",
                        (COMPANY, employee_key),
                    )
                else:
                    cur.execute(f"SELECT count(*)::bigint AS n FROM {table} WHERE employee_key=%s", (employee_key,))
                counts[table] = {"count": int(dict(cur.fetchone())["n"])}
    return {
        "employee": {
            "employment_status": emp.get("employment_status"),
            "app_key": emp.get("app_key"),
            "onboarding_status": emp.get("onboarding_status"),
            "name": emp.get("name"),
            "employee_key": emp.get("employee_key"),
        },
        "applications": apps,
        "attendance_records": counts["attendance_records"],
        "shift_assignments": counts["shift_assignments"],
        "leave_requests": counts["leave_requests"],
        "employee_messages": counts["employee_messages"],
        "employee_status_changes": counts["employee_status_changes"],
        "onboarding_items": counts["onboarding_items"],
        "compliance_documents": counts["compliance_documents"],
    }


def snapshot(app) -> dict:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT employee_key, employment_status, updated_at
                FROM employees WHERE company_code=%s ORDER BY employee_key
                """,
                (COMPANY,),
            )
            employees = [dict(r) for r in cur.fetchall()]
            cur.execute(
                """
                SELECT message_id, employee_key, flow, template_key, status, created_at
                FROM employee_messages
                WHERE company_code=%s AND employee_key=%s
                ORDER BY created_at
                """,
                (COMPANY, ORPHAN_KEY),
            )
            orphan_live = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT to_regclass('public.employee_messages_quarantine') AS q")
            q_present = dict(cur.fetchone())["q"] is not None
            quarantine = []
            if q_present:
                cur.execute(
                    """
                    SELECT quarantine_id, message_id, employee_key, quarantine_reason, restored_at, quarantined_at
                    FROM employee_messages_quarantine
                    WHERE company_code=%s AND employee_key=%s
                    ORDER BY quarantined_at
                    """,
                    (COMPANY, ORPHAN_KEY),
                )
                quarantine = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT to_regclass('public.employee_hygiene_remediation_journal') AS j")
            j_present = dict(cur.fetchone())["j"] is not None
            journal = []
            if j_present:
                cur.execute(
                    """
                    SELECT remediation_id, action, target_key, status, dry_run, idempotency_key,
                           reason, before_json, after_json, evidence, created_at, rolled_back_at
                    FROM employee_hygiene_remediation_journal
                    WHERE company_code=%s
                      AND idempotency_key = ANY(%s)
                    ORDER BY created_at
                    """,
                    (COMPANY, list(STATUS_IDEMP.values()) + [ORPHAN_IDEMP]),
                )
                journal = [dict(r) for r in cur.fetchall()]
            status_hist = {}
            for e in employees:
                status_hist[e["employee_key"]] = e.get("employment_status")
    scan = app.workspace_integrity_scan(COMPANY)
    return {
        "stamp": datetime.now(timezone.utc).isoformat(),
        "employees": employees,
        "status_by_key": status_hist,
        "target_null_statuses": {k: status_hist.get(k) for k in NULL_KEYS},
        "other_statuses": {k: v for k, v in status_hist.items() if k not in NULL_KEYS},
        "orphan_live_count": len(orphan_live),
        "orphan_live": orphan_live,
        "quarantine_count_active": len([q for q in quarantine if q.get("restored_at") is None]),
        "quarantine": quarantine,
        "journal": journal,
        "integrity": {
            "total_orphans": scan.get("total_orphans"),
            "ok": scan.get("ok"),
            "employee_messages": (scan.get("tables") or {}).get("employee_messages"),
        },
    }


def phase_before(app) -> dict:
    snap = snapshot(app)
    dump("before.json", snap)
    return snap


def phase_apply(app, hygiene) -> dict:
    results = {"status": [], "orphan": None}
    for key in NULL_KEYS:
        evidence = live_evidence(app, key)
        dump(f"evidence-{key}.json", evidence)
        reason = (
            "wave1c prod apply: evidence-gated null→active; "
            + "; ".join(hygiene.classify_null_status_from_evidence(evidence).get("reasons") or [])
        )
        out = hygiene.remediate_null_employment_status(
            app,
            company_code=COMPANY,
            employee_key=key,
            evidence=evidence,
            reason=reason[:2000],
            idempotency_key=STATUS_IDEMP[key],
            dry_run=False,
            allow_confidence=("high",),
        )
        results["status"].append(out)
        print("STATUS", key, out.get("status"), out.get("remediation", {}).get("remediation_id"))
    orphan = hygiene.quarantine_orphan_employee_messages(
        app,
        company_code=COMPANY,
        employee_key=ORPHAN_KEY,
        reason=(
            "wave1c prod apply: quarantine synthetic orphan WATHEFNI-P0-DUP-1; "
            "no employee row; no valid refs; 3 harness residue messages"
        ),
        idempotency_key=ORPHAN_IDEMP,
        dry_run=False,
        require_synthetic_key=True,
        require_no_employee_row=True,
    )
    results["orphan"] = orphan
    print("ORPHAN", orphan.get("status"), orphan.get("count"), orphan.get("remediation", {}).get("remediation_id"))
    dump("apply-results.json", results)
    return results


def phase_prove(app) -> dict:
    snap = snapshot(app)
    checks = []

    def check(label: str, cond: bool, detail=None):
        checks.append({"label": label, "ok": bool(cond), "detail": detail})
        print(("PASS" if cond else "FAIL"), label, detail if not cond else "")

    for key in NULL_KEYS:
        check(f"{key} is active", snap["status_by_key"].get(key) == "active", snap["status_by_key"].get(key))
    # other employees unchanged from before file if present
    before_path = OUT / "before.json"
    if before_path.exists():
        before = json.loads(before_path.read_text())
        for key, status in (before.get("other_statuses") or {}).items():
            check(
                f"other status unchanged {key}",
                snap["status_by_key"].get(key) == status,
                {"before": status, "after": snap["status_by_key"].get(key)},
            )
        # targets must have changed null→active (or already active if restore-new)
        for key in NULL_KEYS:
            check(
                f"target was null before apply window or active after restore",
                before["status_by_key"].get(key) in (None, "active") and snap["status_by_key"].get(key) == "active",
                {"before": before["status_by_key"].get(key), "after": snap["status_by_key"].get(key)},
            )
    check("orphan live count 0", snap["orphan_live_count"] == 0, snap["orphan_live_count"])
    check("quarantine has 3 active", snap["quarantine_count_active"] == 3, snap["quarantine_count_active"])
    check("integrity total orphans 0", snap["integrity"]["total_orphans"] == 0, snap["integrity"])
    check("integrity ok", snap["integrity"]["ok"] is True)
    # journal reversible evidence
    applied = [j for j in snap["journal"] if j.get("status") == "applied"]
    check("journal applied entries present", len(applied) >= 3, [{"id": j.get("remediation_id"), "action": j.get("action"), "key": j.get("idempotency_key")} for j in applied])
    for j in applied:
        check(
            f"journal before/after {j.get('idempotency_key')}",
            bool(j.get("before_json")) and bool(j.get("after_json")),
        )
    # freeze-ish: ensure we did not create person tables
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.employees360_persons') AS p")
            check("no Wave2 persons table", dict(cur.fetchone())["p"] is None)
    result = {"checks": checks, "snapshot": snap, "pass": sum(1 for c in checks if c["ok"]), "fail": sum(1 for c in checks if not c["ok"])}
    dump("prove.json", result)
    return result


def phase_rollback(app, hygiene) -> dict:
    out = {
        "orphan": hygiene.restore_quarantined_employee_messages(app, company_code=COMPANY, idempotency_key=ORPHAN_IDEMP),
        "status": [
            hygiene.rollback_null_employment_status(app, company_code=COMPANY, idempotency_key=STATUS_IDEMP[k])
            for k in NULL_KEYS
        ],
    }
    dump("rollback-results.json", out)
    snap = snapshot(app)
    dump("after-rollback.json", snap)
    checks = []
    for key in NULL_KEYS:
        ok = snap["status_by_key"].get(key) is None
        checks.append({"label": f"rollback {key} to null", "ok": ok, "detail": snap["status_by_key"].get(key)})
        print(("PASS" if ok else "FAIL"), f"rollback {key} to null", snap["status_by_key"].get(key))
    ok = snap["orphan_live_count"] == 3
    checks.append({"label": "rollback orphans restored live", "ok": ok, "detail": snap["orphan_live_count"]})
    print(("PASS" if ok else "FAIL"), "rollback orphans restored live", snap["orphan_live_count"])
    return {"results": out, "checks": checks, "snapshot": snap}


def phase_restore(app, hygiene) -> dict:
    # Re-apply exact qualified remediations after rollback drill
    return phase_apply(app, hygiene)


def main() -> int:
    phase = (sys.argv[1] if len(sys.argv) > 1 else "all").strip()
    os.environ.setdefault("WATHEFNI_ENV", "production")
    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import app
    import employee_hygiene_wave1c as hygiene

    if os.environ.get("WATHEFNI_ENV") != "production":
        raise SystemExit(f"refusing: WATHEFNI_ENV={os.environ.get('WATHEFNI_ENV')}")

    if phase == "before":
        phase_before(app)
        return 0
    if phase == "apply":
        phase_apply(app, hygiene)
        return 0
    if phase == "prove":
        prove = phase_prove(app)
        return 1 if prove["fail"] else 0
    if phase == "rollback":
        phase_rollback(app, hygiene)
        return 0
    if phase == "restore":
        phase_restore(app, hygiene)
        prove = phase_prove(app)
        return 1 if prove["fail"] else 0
    if phase == "all":
        phase_before(app)
        phase_apply(app, hygiene)
        prove1 = phase_prove(app)
        dump("prove-after-apply.json", prove1)
        rb = phase_rollback(app, hygiene)
        dump("rollback-summary.json", rb)
        # After rollback, journal rows are rolled_back — restore-new re-applies same keys
        phase_restore(app, hygiene)
        prove2 = phase_prove(app)
        dump("prove-after-restore.json", prove2)
        health = None
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=5) as resp:
                health = resp.status
        except Exception as exc:
            health = f"error:{exc}"
        final = {
            "prove_after_apply_fail": prove1["fail"],
            "prove_after_restore_fail": prove2["fail"],
            "health": health,
            "verdict": "PASS" if prove1["fail"] == 0 and prove2["fail"] == 0 and health == 200 else "FAIL",
            "journal_ids_applied": [
                j.get("remediation_id")
                for j in prove2["snapshot"]["journal"]
                if j.get("status") == "applied"
            ],
            "journal": [
                {
                    "remediation_id": j.get("remediation_id"),
                    "action": j.get("action"),
                    "target_key": j.get("target_key"),
                    "idempotency_key": j.get("idempotency_key"),
                    "status": j.get("status"),
                }
                for j in prove2["snapshot"]["journal"]
            ],
            "before_counts": json.loads((OUT / "before.json").read_text()) if (OUT / "before.json").exists() else None,
            "after_counts": {
                "target_statuses": prove2["snapshot"]["target_null_statuses"],
                "other_statuses": prove2["snapshot"]["other_statuses"],
                "orphan_live": prove2["snapshot"]["orphan_live_count"],
                "quarantine_active": prove2["snapshot"]["quarantine_count_active"],
                "integrity_total_orphans": prove2["snapshot"]["integrity"]["total_orphans"],
            },
        }
        # slim before counts
        if final["before_counts"]:
            b = final["before_counts"]
            final["before_counts"] = {
                "target_statuses": b.get("target_null_statuses"),
                "other_statuses": b.get("other_statuses"),
                "orphan_live": b.get("orphan_live_count"),
                "integrity_total_orphans": (b.get("integrity") or {}).get("total_orphans"),
            }
        dump("final.json", final)
        print(json.dumps(final, indent=2, default=str))
        return 0 if final["verdict"] == "PASS" else 1
    raise SystemExit(f"unknown phase {phase}")


if __name__ == "__main__":
    raise SystemExit(main())
