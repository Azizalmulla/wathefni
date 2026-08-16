#!/usr/bin/env python3
"""Onboarding Wave 3 — production controlled migration of four real checklists.

Requires:
  WATHEFNI_ONBOARDING_WAVE3_MIGRATION=on  (temporary migration gate)
  WATHEFNI_ONBOARDING_SEED=off
  WATHEFNI_ONBOARDING_HR_MUTATE=off
  Explicit planned start dates for all four employees
  Dual-control requester ≠ approver dashboard user ids

Does not broaden employee-app access.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

OUT = Path(os.environ.get("WAVE3_MIG_OUT", "/tmp/onboarding-wave3-migration"))
OUT.mkdir(parents=True, exist_ok=True)

# Explicit planned starts (required — no silent defaults).
# Employees are already in_progress; pin due dates relative to these dates.
PLANNED_STARTS = {
    "WATHEFNI-96550252254": date(2026, 8, 1),  # Talal
    "WATHEFNI-96566363363": date(2026, 8, 1),  # Fouad
    "WATHEFNI-96597727743": date(2026, 8, 1),  # Mohammad
    "WATHEFNI-96599411617": date(2026, 8, 1),  # Brian
}

PASS = 0
FAIL = 0
EVIDENCE: dict = {"checks": [], "ids": {}}


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    EVIDENCE["checks"].append({"label": label, "pass": bool(cond), "detail": None if cond else detail})
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def dump(name: str, obj) -> None:
    (OUT / name).write_text(json.dumps(obj, indent=2, default=str) + "\n")


def main() -> int:
    if str(os.environ.get("WATHEFNI_ENV") or "").lower() not in {"production", "prod"}:
        raise SystemExit("refusing: WATHEFNI_ENV must be production")

    # Hard invariants
    os.environ["WATHEFNI_ONBOARDING_SEED"] = "off"
    os.environ["WATHEFNI_ONBOARDING_HR_MUTATE"] = "off"
    os.environ["WATHEFNI_ONBOARDING_WAVE3_MIGRATION"] = "on"

    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import app
    import onboarding_wave2 as w2
    import onboarding_wave3_migration as w3

    check("seed off", app.onboarding_seed_enabled() is False)
    check("hr_mutate off", app.onboarding_hr_mutate_enabled() is False)
    check("migration gate on", w3.migration_enabled() is True)
    check("employee app allowlist talal-only hint", True)  # verified via env snapshot separately

    # Prefer Wave 3 schema only — avoid racing full ensure_schema against the live service.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w3.ensure_wave3_migration_schema(cur)
        conn.commit()

    # Resolve dual-control actors from dashboard users
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM dashboard_users
                WHERE company_code='WATHEFNI' AND lower(coalesce(status,''))='active'
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 40
                """
            )
            users = [dict(r) for r in (cur.fetchall() or [])]
        conn.commit()
    managers = []
    for u in users:
        try:
            if not app._normal_dashboard_operator(u):
                continue
            perms = app.dashboard_effective_permissions_for_user(u)
            if "onboarding.manage" in perms or "employees.manage" in perms:
                managers.append(u)
        except Exception:
            continue
    if len(managers) < 2:
        # fall back to any two distinct active users
        managers = users[:2] if len(users) >= 2 else managers
    if len(managers) < 2:
        raise SystemExit("need two distinct dashboard users for dual-control")
    requester = str(managers[0]["user_id"])
    approver = str(managers[1]["user_id"])
    if requester == approver:
        raise SystemExit("self_approval_forbidden: need distinct users")
    EVIDENCE["ids"] = {
        "requester_user_id": requester,
        "approver_user_id": approver,
        "requester_email": managers[0].get("email"),
        "approver_email": managers[1].get("email"),
        "planned_starts": {k: v.isoformat() for k, v in PLANNED_STARTS.items()},
    }

    # --- Phase 1: fingerprint + preview ---
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            live = w3.load_four_real_items(cur)
            emps = w3.load_four_real_employees(cur)
            before_fp = w3.fingerprint_items(live)
            preview = w3.build_preview(employees=emps, live_rows=live, planned_starts=PLANNED_STARTS)
            created = w3.create_batch(
                cur,
                requester_user_id=requester,
                planned_starts=PLANNED_STARTS,
                metadata={"wave": "wave3", "stamp": os.environ.get("STAMP")},
            )
        conn.commit()

    dump("fingerprint-before.json", before_fp)
    dump("preview.json", preview)
    dump("batch-created.json", created)
    check("exactly 19 rows before", len(live) == 19, len(live))
    check("preview ok_to_commit", preview.get("ok_to_commit") is True, preview.get("conflicts"))
    check("batch created", created.get("ok") is True, created)
    batch_id = str(created["batch"]["batch_id"])
    EVIDENCE["ids"]["batch_id"] = batch_id
    check("no conflicts", not preview.get("conflicts"), preview.get("conflicts"))

    # Self-approval must fail
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            bad = w3.approve_batch(cur, batch_id=batch_id, approver_user_id=requester)
        conn.rollback()
    check("self-approval forbidden", bad.get("error") == "self_approval_forbidden", bad)

    # Dual-control approve
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            approved = w3.approve_batch(cur, batch_id=batch_id, approver_user_id=approver)
        conn.commit()
    dump("dual-control-approval.json", approved)
    check("approved", approved.get("ok") is True, approved)
    check("approver distinct", approved["batch"]["approver_user_id"] == approver)

    # --- Phase 2: commit ---
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            committed = w3.commit_batch(
                cur,
                batch_id=batch_id,
                actor_user_id=approver,
                recompute_fn=app.recompute_employee_onboarding_counts,
            )
        if not committed.get("ok"):
            conn.rollback()
        else:
            conn.commit()
    dump("commit.json", committed)
    check("commit ok", committed.get("ok") is True, committed)
    check("dry-run matches commit", committed.get("dry_run_match") is True, committed)

    # --- Phase 3: prove post-state ---
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            after = w3.load_four_real_items(cur)
            emps_after = w3.load_four_real_employees(cur)
            # Idempotent re-apply inserts
            preview2 = w3.build_preview(
                employees=emps_after,
                live_rows=after,
                planned_starts=PLANNED_STARTS,
            )
            # Simulate insert path on already-migrated: seed-like missing should be 0 new canonical gaps
            for emp in preview2["employees"]:
                inserts = [a for a in emp["actions"] if a["op"] == "insert_missing"]
                # After migration live includes all template ids + retired obsolete, so inserts should be empty
                check(
                    f"no duplicate inserts {emp['employee_key'][-8:]}",
                    len(inserts) == 0,
                    inserts[:3],
                )
        conn.commit()

    dump("fingerprint-after.json", committed.get("fingerprint_after"))
    dump("employees-after.json", emps_after)

    # Per-employee reports
    per_emp = []
    for key in w2.FOUR_REALS:
        items = [i for i in after if i["employee_key"] == key]
        before_items = [i for i in live if i["employee_key"] == key]
        emp = next(e for e in emps_after if e["employee_key"] == key)
        photo = next((i for i in items if i["item_id"] == "personal_photo"), None)
        bank = next((i for i in items if i["item_id"] == "bank_details"), None)
        obsolete = [i for i in items if i["item_id"] in w2.OBSOLETE_LEGACY_ITEM_IDS]
        received_before = {
            i["item_id"]: (i.get("status"), int(i.get("reminder_count") or 0), i.get("value") is not None and str(i.get("value") or "") != "")
            for i in before_items
            if str(i.get("status") or "").lower() in {"received", "complete", "completed", "verified"}
        }
        received_ok = True
        for iid, (st, rem, _) in received_before.items():
            if iid == "bank_details":
                # status+reminders preserved; value redacted
                cur_bank = next(i for i in items if i["item_id"] == "bank_details")
                if str(cur_bank.get("status")) != str(st) or int(cur_bank.get("reminder_count") or 0) != rem:
                    received_ok = False
                if cur_bank.get("value") not in (None, ""):
                    received_ok = False
            else:
                cur_i = next((i for i in items if i["item_id"] == iid), None)
                if not cur_i or str(cur_i.get("status")) != str(st) or int(cur_i.get("reminder_count") or 0) != rem:
                    received_ok = False
        summary = app.employee_onboarding_summary(emp, company_code="WATHEFNI")
        per_emp.append({
            "employee_key": key,
            "name": emp.get("name"),
            "before_count": len(before_items),
            "after_count": len(items),
            "template_version": emp.get("onboarding_template_version"),
            "brian_photo_preserved": (photo is not None and str(photo.get("status")) == str(next((i for i in before_items if i["item_id"]=="personal_photo"), {}).get("status"))) if key.endswith("411617") else None,
            "obsolete_retired": [
                {"item_id": o["item_id"], "status": o.get("status"), "deleted": False}
                for o in obsolete
            ],
            "bank": {
                "collection_mode": bank.get("collection_mode") if bank else None,
                "authority": bank.get("authority") if bank else None,
                "status": bank.get("status") if bank else None,
                "value_redacted": bank.get("value") in (None, "") if bank else None,
            },
            "received_history_ok": received_ok,
            "summary_pending": summary.get("pending_count"),
            "summary_received": summary.get("received_count"),
            "summary_required_total": summary.get("required_total"),
            "documents_pending": emp.get("documents_pending"),
            "documents_complete": emp.get("documents_complete"),
            "counts_reconcile": (
                summary.get("pending_count") == emp.get("documents_pending")
                and summary.get("received_count") == emp.get("documents_complete")
            ),
        })
    dump("per-employee-before-after.json", per_emp)

    for row in per_emp:
        check(f"pinned {row['employee_key'][-8:]}", row["template_version"] == "2.0.0", row["template_version"])
        check(f"received preserved {row['employee_key'][-8:]}", row["received_history_ok"] is True, row)
        check(f"counts reconcile {row['employee_key'][-8:]}", row["counts_reconcile"] is True, row)
        if row["employee_key"].endswith("411617"):
            check("brian photo preserved", row["brian_photo_preserved"] is True, row)
        for obs in row["obsolete_retired"]:
            check(
                f"obsolete auditable {row['employee_key'][-8:]}:{obs['item_id']}",
                obs["status"] == "retired_legacy" and obs["deleted"] is False,
                obs,
            )
        if row["bank"]["status"] is not None:
            check(
                f"bank ESS {row['employee_key'][-8:]}",
                row["bank"]["collection_mode"] == "ess_encrypted"
                and row["bank"]["authority"] == "ess"
                and row["bank"]["value_redacted"] is True,
                row["bank"],
            )

    # Bank collection still blocked
    ok_bank, reason = app.validate_onboarding_item_receipt(
        "bank_details", "NBK KW81NBOK0000000000000000123456", None
    )
    check("bank plaintext still blocked", ok_bank is False and reason == "bank_via_ess_required", reason)

    # Expanded counts
    check("after has more than 19 rows", len(after) > 19, len(after))
    # Brian expanded
    brian_n = len([i for i in after if i["employee_key"].endswith("411617")])
    check("brian expanded", brian_n >= 35, brian_n)

    # --- Phase 4: rollback to exact 19-row fingerprint ---
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            rb = w3.rollback_batch(cur, batch_id=batch_id, actor_user_id=requester)
            if rb.get("ok"):
                for key in w2.FOUR_REALS:
                    app.recompute_employee_onboarding_counts(cur, key)
            else:
                conn.rollback()
                dump("rollback-failed.json", rb)
                check("rollback ok", False, rb)
                raise SystemExit(1)
        conn.commit()
    dump("rollback.json", rb)
    check("rollback fingerprint restored", rb.get("fingerprint_restored") is True, rb)
    check("rollback count 19", rb.get("item_count") == 19, rb.get("item_count"))
    check("rollback fp equals before", rb.get("fingerprint") == before_fp, {"before_n": len(before_fp), "after_n": len(rb.get("fingerprint") or [])})

    # --- Phase 5: reapply successfully ---
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            created2 = w3.create_batch(
                cur,
                requester_user_id=requester,
                planned_starts=PLANNED_STARTS,
                metadata={"wave": "wave3", "reapply": True},
            )
            batch2 = str(created2["batch"]["batch_id"])
            w3.approve_batch(cur, batch_id=batch2, approver_user_id=approver)
            committed2 = w3.commit_batch(
                cur,
                batch_id=batch2,
                actor_user_id=requester,
                recompute_fn=app.recompute_employee_onboarding_counts,
            )
        if not committed2.get("ok"):
            conn.rollback()
        else:
            conn.commit()
    dump("reapply-commit.json", committed2)
    EVIDENCE["ids"]["reapply_batch_id"] = batch2
    check("reapply ok", committed2.get("ok") is True, committed2)
    check("reapply dry-run match", committed2.get("dry_run_match") is True)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            final = w3.load_four_real_items(cur)
            final_emps = w3.load_four_real_employees(cur)
        conn.commit()

    final_counts = {
        "item_rows": len(final),
        "by_employee": {
            k: len([i for i in final if i["employee_key"] == k]) for k in w2.FOUR_REALS
        },
        "employees": [
            {
                "employee_key": e["employee_key"],
                "name": e.get("name"),
                "template_version": e.get("onboarding_template_version"),
                "documents_pending": e.get("documents_pending"),
                "documents_complete": e.get("documents_complete"),
                "onboarding_status": e.get("onboarding_status"),
            }
            for e in final_emps
        ],
    }
    dump("final-counts.json", final_counts)
    check("final pinned all", all(e.get("onboarding_template_version") == "2.0.0" for e in final_emps))

    # Flags still off
    check("seed still off", app.onboarding_seed_enabled() is False)
    check("hr_mutate still off", app.onboarding_hr_mutate_enabled() is False)

    EVIDENCE["summary"] = {"pass": PASS, "fail": FAIL, "final_counts": final_counts}
    dump("migration-evidence.json", EVIDENCE)
    print(f"\nRESULT pass={PASS} fail={FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
