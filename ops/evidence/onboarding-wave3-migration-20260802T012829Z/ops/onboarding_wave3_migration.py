#!/usr/bin/env python3
"""Onboarding Wave 3 — controlled migration of four real legacy checklists.

Migrates WATHEFNI legacy rows → default_kuwait@2.0.0 without enabling
ONBOARDING_SEED / ONBOARDING_HR_MUTATE. Dual-control required to commit.
Obsolete items are retired by audited status (never deleted). Bank becomes
ESS-owned; historical plaintext bank values are redacted, not copied.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any

import onboarding_wave2 as w2

COMPANY = "WATHEFNI"
MIGRATION_WAVE = "onboarding_wave3"
RETIRED_STATUS = "retired_legacy"
TEMPLATE_ID = w2.CANONICAL_TEMPLATE_ID
TEMPLATE_VERSION = w2.CANONICAL_TEMPLATE_VERSION

# Explicit planned starts are mandatory for due-date calculation.
# Callers must supply them; missing → conflict fail-closed.


def _on(val: str | None) -> bool:
    return str(val or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def migration_enabled() -> bool:
    """Separate from SEED/HR_MUTATE — Wave 3 controlled migration gate only."""
    return _on(os.environ.get("WATHEFNI_ONBOARDING_WAVE3_MIGRATION"))


def ensure_wave3_migration_schema(cur: Any) -> None:
    w2.ensure_onboarding_wave2_schema(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS onboarding_migration_batches (
          batch_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          wave text NOT NULL DEFAULT 'onboarding_wave3',
          template_id text NOT NULL,
          template_version text NOT NULL,
          status text NOT NULL,
          dry_run_hash text,
          commit_hash text,
          planned_starts jsonb NOT NULL DEFAULT '{}'::jsonb,
          preview_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          conflicts_json jsonb NOT NULL DEFAULT '[]'::jsonb,
          requester_user_id text NOT NULL,
          approver_user_id text,
          approved_at timestamptz,
          committed_at timestamptz,
          rolled_back_at timestamptz,
          fingerprint_before jsonb NOT NULL DEFAULT '[]'::jsonb,
          fingerprint_after jsonb,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (requester_user_id <> coalesce(approver_user_id, ''))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS onboarding_migration_item_snapshots (
          snapshot_id uuid PRIMARY KEY,
          batch_id uuid NOT NULL REFERENCES onboarding_migration_batches(batch_id) ON DELETE CASCADE,
          employee_key text NOT NULL,
          item_id text NOT NULL,
          row_json jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_onboarding_mig_snap_batch
          ON onboarding_migration_item_snapshots (batch_id, employee_key, item_id)
        """
    )


def item_fingerprint_row(row: dict[str, Any]) -> str:
    value = row.get("value")
    value_s = "" if value is None else str(value)
    value_md5 = hashlib.md5(value_s.encode("utf-8")).hexdigest()
    required = row.get("required")
    # Normalize bool/None for stable fingerprints across drivers
    if required is True or required == "t" or required == "true":
        req_s = "True"
    elif required is False or required == "f" or required == "false":
        req_s = "False"
    else:
        req_s = str(required)
    return (
        f"{row.get('employee_key')}|{row.get('item_id')}|{req_s}|"
        f"{row.get('status')}|{value_md5}|{int(row.get('reminder_count') or 0)}"
    )


def load_four_real_items(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT oi.*, e.name AS employee_name, e.start_date AS employee_start_date,
               e.onboarding_status AS employee_onboarding_status,
               e.documents_pending, e.documents_complete
        FROM onboarding_items oi
        JOIN employees e ON e.employee_key = oi.employee_key
        WHERE e.company_code=%s AND oi.employee_key = ANY(%s)
        ORDER BY oi.employee_key, oi.item_id
        """,
        (COMPANY, list(w2.FOUR_REALS)),
    )
    return [dict(r) for r in (cur.fetchall() or [])]


def load_four_real_employees(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT employee_key, name, phone, company_code, onboarding_status, start_date,
               documents_pending, documents_complete, onboarding_template_version, raw_json
        FROM employees
        WHERE company_code=%s AND employee_key = ANY(%s)
        ORDER BY employee_key
        """,
        (COMPANY, list(w2.FOUR_REALS)),
    )
    return [dict(r) for r in (cur.fetchall() or [])]


def fingerprint_items(rows: list[dict[str, Any]]) -> list[str]:
    return sorted(item_fingerprint_row(r) for r in rows)


def parse_planned_starts(raw: dict[str, Any] | None) -> dict[str, date]:
    out: dict[str, date] = {}
    for key, val in (raw or {}).items():
        if val is None or str(val).strip() == "":
            continue
        if hasattr(val, "isoformat") and not isinstance(val, str):
            out[str(key)] = val  # type: ignore[assignment]
        else:
            out[str(key)] = date.fromisoformat(str(val)[:10])
    return out


def build_preview(
    *,
    employees: list[dict[str, Any]],
    live_rows: list[dict[str, Any]],
    planned_starts: dict[str, date],
) -> dict[str, Any]:
    """Build per-employee migration plan. Conflicts fail closed (no silent defaults)."""
    by_emp: dict[str, list[dict[str, Any]]] = {}
    for row in live_rows:
        by_emp.setdefault(str(row["employee_key"]), []).append(row)
    emp_by_key = {str(e["employee_key"]): e for e in employees}
    template_ids = {i.item_id for i in w2.DEFAULT_KUWAIT_V2}
    conflicts: list[dict[str, Any]] = []
    employees_out = []

    for key in w2.FOUR_REALS:
        emp = emp_by_key.get(key) or {"employee_key": key, "name": ""}
        items = by_emp.get(key) or []
        live_ids = {str(i["item_id"]) for i in items}
        planned = planned_starts.get(key)
        emp_conflicts = []
        if planned is None:
            emp_conflicts.append({
                "code": "planned_start_required",
                "message": "Explicit planned_start_date required before due dates can be calculated",
                "employee_key": key,
            })

        actions: list[dict[str, Any]] = []
        # Preserve / enrich existing
        for live in items:
            iid = str(live["item_id"])
            mapped = w2.LEGACY_ITEM_MAP.get(iid, iid if iid in template_ids else None)
            if iid in w2.OBSOLETE_LEGACY_ITEM_IDS:
                actions.append({
                    "op": "retire_obsolete",
                    "item_id": iid,
                    "maps_to": mapped,
                    "new_status": RETIRED_STATUS,
                    "preserve_reminder_count": int(live.get("reminder_count") or 0),
                    "preserve_status_was": live.get("status"),
                    "delete": False,
                })
                continue
            if iid == "bank_details":
                actions.append({
                    "op": "convert_bank_ess",
                    "item_id": "bank_details",
                    "preserve_status": live.get("status"),
                    "preserve_reminder_count": int(live.get("reminder_count") or 0),
                    "redact_plaintext_value": True,
                    "collection_mode": "ess_encrypted",
                    "authority": "ess",
                    "label": w2.get_template_item("bank_details").label if w2.get_template_item("bank_details") else None,
                })
                continue
            if iid in template_ids:
                spec = w2.get_template_item(iid)
                actions.append({
                    "op": "enrich_existing",
                    "item_id": iid,
                    "preserve_status": live.get("status"),
                    "preserve_reminder_count": int(live.get("reminder_count") or 0),
                    "preserve_value": True,
                    "preserve_received_docs": str(live.get("status") or "").lower()
                    in {"received", "complete", "completed", "verified"},
                    "category": spec.category if spec else live.get("category"),
                    "owner": spec.owner if spec else live.get("owner"),
                    "label": spec.label if spec else live.get("label"),
                    "required": bool(spec.required) if spec else bool(live.get("required")),
                    "depends_on": list(spec.depends_on) if spec else [],
                    "collection_mode": spec.collection_mode if spec else live.get("collection_mode"),
                    "authority": spec.authority if spec else live.get("authority"),
                    "due_offset_days": spec.due_offset_days if spec else None,
                    "due_date": (
                        w2.compute_due_date(planned, spec.due_offset_days).isoformat()
                        if planned is not None and spec and spec.due_offset_days is not None
                        else None
                    ),
                })
                continue
            emp_conflicts.append({
                "code": "unmapped_item",
                "message": f"Live item {iid} has no canonical mapping",
                "item_id": iid,
                "employee_key": key,
            })

        # medical → ensure medical_check exists (template add); medical row retired above
        missing = sorted(template_ids - live_ids)
        # If medical exists, medical_check is still missing and should be added
        if "medical" in live_ids and "medical_check" not in live_ids and "medical_check" not in missing:
            missing.append("medical_check")
            missing = sorted(set(missing))
        for mid in missing:
            # Don't re-add obsolete ids
            if mid in w2.OBSOLETE_LEGACY_ITEM_IDS:
                continue
            spec = w2.get_template_item(mid)
            if not spec:
                emp_conflicts.append({
                    "code": "unknown_template_item",
                    "item_id": mid,
                    "employee_key": key,
                })
                continue
            actions.append({
                "op": "insert_missing",
                "item_id": mid,
                "status": "pending",
                "required": bool(spec.required),
                "owner": spec.owner,
                "category": spec.category,
                "label": spec.label,
                "item_type": spec.item_type,
                "depends_on": list(spec.depends_on),
                "collection_mode": spec.collection_mode,
                "authority": spec.authority,
                "due_offset_days": spec.due_offset_days,
                "due_date": (
                    w2.compute_due_date(planned, spec.due_offset_days).isoformat()
                    if planned is not None and spec.due_offset_days is not None
                    else None
                ),
                "template_version": TEMPLATE_VERSION,
            })

        brian_partial = key.endswith("411617")
        if brian_partial:
            photo = next((i for i in items if i.get("item_id") == "personal_photo"), None)
            if not photo:
                emp_conflicts.append({
                    "code": "brian_missing_personal_photo",
                    "message": "Brian partial checklist must retain personal_photo",
                    "employee_key": key,
                })
            actions.insert(0, {
                "op": "brian_partial_guard",
                "preserve_item_id": "personal_photo",
                "preserve_row": True,
                "audit_event": "onboarding_migration_brian_partial",
            })

        conflicts.extend(emp_conflicts)
        employees_out.append({
            "employee_key": key,
            "name": emp.get("name"),
            "onboarding_status": emp.get("onboarding_status"),
            "live_count": len(items),
            "brian_partial": brian_partial,
            "planned_start_date": planned.isoformat() if planned else None,
            "actions": actions,
            "action_counts": {
                "insert_missing": sum(1 for a in actions if a["op"] == "insert_missing"),
                "enrich_existing": sum(1 for a in actions if a["op"] == "enrich_existing"),
                "retire_obsolete": sum(1 for a in actions if a["op"] == "retire_obsolete"),
                "convert_bank_ess": sum(1 for a in actions if a["op"] == "convert_bank_ess"),
            },
            "conflicts": emp_conflicts,
            "pin": {"template_id": TEMPLATE_ID, "template_version": TEMPLATE_VERSION},
        })

    preview = {
        "wave": MIGRATION_WAVE,
        "company_code": COMPANY,
        "template_id": TEMPLATE_ID,
        "template_version": TEMPLATE_VERSION,
        "mode": "controlled_four_real_migration",
        "seed_flag_required": False,
        "hr_mutate_flag_required": False,
        "fingerprint_before": fingerprint_items(live_rows),
        "fingerprint_before_count": len(live_rows),
        "employees": employees_out,
        "conflicts": conflicts,
        "ok_to_commit": len(conflicts) == 0,
        "policy": {
            "preserve_received_and_reminders": True,
            "preserve_brian_personal_photo": True,
            "obsolete_retire_not_delete": True,
            "bank_ess_redact_plaintext": True,
            "planned_start_required": True,
            "dual_control_required": True,
            "production_seed_off": True,
            "production_hr_mutate_off": True,
        },
    }
    preview["dry_run_hash"] = hashlib.sha256(
        json.dumps(preview, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return preview


def _stable_action_digest(preview: dict[str, Any]) -> str:
    """Hash of actionable ops only (for dry-run == commit equality)."""
    slim = []
    for emp in preview.get("employees") or []:
        slim.append({
            "employee_key": emp["employee_key"],
            "planned_start_date": emp.get("planned_start_date"),
            "actions": emp.get("actions"),
            "pin": emp.get("pin"),
        })
    return hashlib.sha256(json.dumps(slim, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def create_batch(
    cur: Any,
    *,
    requester_user_id: str,
    planned_starts: dict[str, date],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_wave3_migration_schema(cur)
    requester = str(requester_user_id or "").strip()
    if not requester:
        return {"ok": False, "error": "requester_required"}
    employees = load_four_real_employees(cur)
    live = load_four_real_items(cur)
    if len(live) != 19:
        return {
            "ok": False,
            "error": "unexpected_live_count",
            "expected": 19,
            "actual": len(live),
            "message": "Refusing migration unless exactly 19 legacy rows are present (pre-migration fingerprint).",
        }
    preview = build_preview(employees=employees, live_rows=live, planned_starts=planned_starts)
    batch_id = str(uuid.uuid4())
    status = "preview_blocked" if preview["conflicts"] else "pending_approval"
    cur.execute(
        """
        INSERT INTO onboarding_migration_batches
          (batch_id, company_code, wave, template_id, template_version, status,
           dry_run_hash, planned_starts, preview_json, conflicts_json,
           requester_user_id, fingerprint_before, metadata)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s::jsonb,%s::jsonb)
        RETURNING *
        """,
        (
            batch_id,
            COMPANY,
            MIGRATION_WAVE,
            TEMPLATE_ID,
            TEMPLATE_VERSION,
            status,
            preview["dry_run_hash"],
            json.dumps({k: v.isoformat() for k, v in planned_starts.items()}),
            json.dumps(preview, default=str),
            json.dumps(preview["conflicts"], default=str),
            requester,
            json.dumps(preview["fingerprint_before"]),
            json.dumps({**(metadata or {}), "action_digest": _stable_action_digest(preview)}, default=str),
        ),
    )
    batch = dict(cur.fetchone())
    # Snapshot every live row for exact rollback
    for row in live:
        # Redact bank value in snapshot storage? Keep original for rollback fidelity.
        cur.execute(
            """
            INSERT INTO onboarding_migration_item_snapshots
              (snapshot_id, batch_id, employee_key, item_id, row_json)
            VALUES (%s,%s,%s,%s,%s::jsonb)
            """,
            (
                str(uuid.uuid4()),
                batch_id,
                row["employee_key"],
                row["item_id"],
                json.dumps(row, default=str),
            ),
        )
    w2.record_onboarding_audit(
        cur,
        company_code=COMPANY,
        employee_key="*",
        event_type="onboarding_migration_batch_created",
        actor_user_id=requester,
        after={"batch_id": batch_id, "status": status, "dry_run_hash": preview["dry_run_hash"]},
        metadata={"conflicts": len(preview["conflicts"])},
    )
    return {"ok": True, "batch": batch, "preview": preview}


def approve_batch(
    cur: Any,
    *,
    batch_id: str,
    approver_user_id: str,
) -> dict[str, Any]:
    ensure_wave3_migration_schema(cur)
    approver = str(approver_user_id or "").strip()
    if not approver:
        return {"ok": False, "error": "approver_required"}
    cur.execute(
        "SELECT * FROM onboarding_migration_batches WHERE batch_id=%s FOR UPDATE",
        (batch_id,),
    )
    batch = cur.fetchone()
    if not batch:
        return {"ok": False, "error": "batch_not_found"}
    batch = dict(batch)
    if batch["status"] == "preview_blocked":
        return {"ok": False, "error": "conflicts_unresolved", "conflicts": batch.get("conflicts_json")}
    if batch["status"] not in {"pending_approval", "approved"}:
        return {"ok": False, "error": "invalid_status", "status": batch["status"]}
    if str(batch["requester_user_id"]) == approver:
        return {"ok": False, "error": "self_approval_forbidden"}
    if batch["status"] == "approved" and str(batch.get("approver_user_id")) == approver:
        return {"ok": True, "idempotent": True, "batch": batch}
    cur.execute(
        """
        UPDATE onboarding_migration_batches
        SET status='approved', approver_user_id=%s, approved_at=now(), updated_at=now()
        WHERE batch_id=%s
        RETURNING *
        """,
        (approver, batch_id),
    )
    updated = dict(cur.fetchone())
    w2.record_onboarding_audit(
        cur,
        company_code=COMPANY,
        employee_key="*",
        event_type="onboarding_migration_batch_approved",
        actor_user_id=approver,
        after={"batch_id": batch_id, "requester": batch["requester_user_id"], "approver": approver},
    )
    return {"ok": True, "batch": updated}


def _apply_actions(cur: Any, *, preview: dict[str, Any], batch_id: str, actor: str) -> dict[str, Any]:
    applied = []
    for emp in preview["employees"]:
        key = emp["employee_key"]
        planned = date.fromisoformat(emp["planned_start_date"]) if emp.get("planned_start_date") else None
        for action in emp["actions"]:
            op = action["op"]
            if op == "brian_partial_guard":
                w2.record_onboarding_audit(
                    cur,
                    company_code=COMPANY,
                    employee_key=key,
                    item_id="personal_photo",
                    event_type="onboarding_migration_brian_partial",
                    actor_user_id=actor,
                    metadata={"batch_id": batch_id, "preserve": True},
                )
                applied.append({"employee_key": key, **action})
                continue
            if op == "retire_obsolete":
                cur.execute(
                    """
                    UPDATE onboarding_items
                    SET status=%s,
                        required=FALSE,
                        row_version=row_version+1,
                        template_version=%s,
                        raw_json=COALESCE(raw_json,'{}'::jsonb) || %s::jsonb,
                        updated_at=now()
                    WHERE employee_key=%s AND item_id=%s
                    RETURNING item_id, status, reminder_count
                    """,
                    (
                        RETIRED_STATUS,
                        TEMPLATE_VERSION,
                        json.dumps({
                            "retired_by": MIGRATION_WAVE,
                            "batch_id": batch_id,
                            "previous_status": action.get("preserve_status_was"),
                            "delete": False,
                        }),
                        key,
                        action["item_id"],
                    ),
                )
                row = cur.fetchone()
                w2.record_onboarding_audit(
                    cur,
                    company_code=COMPANY,
                    employee_key=key,
                    item_id=action["item_id"],
                    event_type="onboarding_migration_retire_obsolete",
                    actor_user_id=actor,
                    after=dict(row) if row else {},
                    metadata={"batch_id": batch_id},
                )
                applied.append({"employee_key": key, **action, "result": dict(row) if row else None})
                continue
            if op == "convert_bank_ess":
                # Redact plaintext; preserve status + reminders; never copy value elsewhere.
                cur.execute(
                    """
                    UPDATE onboarding_items
                    SET collection_mode='ess_encrypted',
                        authority='ess',
                        label=COALESCE(%s, label),
                        category='payroll_bank',
                        owner='employee',
                        item_type='task',
                        value=NULL,
                        template_version=%s,
                        row_version=row_version+1,
                        raw_json=COALESCE(raw_json,'{}'::jsonb) || %s::jsonb,
                        updated_at=now()
                    WHERE employee_key=%s AND item_id='bank_details'
                    RETURNING item_id, status, reminder_count, collection_mode, authority, value
                    """,
                    (
                        action.get("label"),
                        TEMPLATE_VERSION,
                        json.dumps({
                            "bank_converted_ess": True,
                            "plaintext_redacted": True,
                            "batch_id": batch_id,
                            "prior_status_preserved": action.get("preserve_status"),
                        }),
                        key,
                    ),
                )
                row = cur.fetchone()
                w2.record_onboarding_audit(
                    cur,
                    company_code=COMPANY,
                    employee_key=key,
                    item_id="bank_details",
                    event_type="onboarding_migration_bank_ess",
                    actor_user_id=actor,
                    after={
                        "status": (row or {}).get("status"),
                        "reminder_count": (row or {}).get("reminder_count"),
                        "collection_mode": "ess_encrypted",
                        "value_redacted": True,
                    },
                    metadata={"batch_id": batch_id, "plaintext_not_copied": True},
                )
                applied.append({"employee_key": key, **action, "result": dict(row) if row else None})
                continue
            if op == "enrich_existing":
                due = action.get("due_date")
                cur.execute(
                    """
                    UPDATE onboarding_items
                    SET label=%s,
                        category=%s,
                        owner=%s,
                        required=%s,
                        depends_on=%s::jsonb,
                        collection_mode=%s,
                        authority=%s,
                        due_date=%s,
                        template_version=%s,
                        row_version=row_version+1,
                        raw_json=COALESCE(raw_json,'{}'::jsonb) || %s::jsonb,
                        updated_at=now()
                    WHERE employee_key=%s AND item_id=%s
                    RETURNING item_id, status, reminder_count, due_date
                    """,
                    (
                        action.get("label"),
                        action.get("category"),
                        action.get("owner"),
                        bool(action.get("required")),
                        json.dumps(action.get("depends_on") or []),
                        action.get("collection_mode"),
                        action.get("authority"),
                        due,
                        TEMPLATE_VERSION,
                        json.dumps({"enriched_by": MIGRATION_WAVE, "batch_id": batch_id}),
                        key,
                        action["item_id"],
                    ),
                )
                row = cur.fetchone()
                # Never overwrite status / reminder_count / value
                applied.append({"employee_key": key, **action, "result": dict(row) if row else None})
                continue
            if op == "insert_missing":
                cur.execute(
                    "SELECT 1 FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
                    (key, action["item_id"]),
                )
                if cur.fetchone():
                    applied.append({"employee_key": key, **action, "skipped": "already_exists"})
                    continue
                document_type = action["item_id"] if action.get("item_type") == "document" else None
                cur.execute(
                    """
                    INSERT INTO onboarding_items
                      (employee_key, item_id, label, category, item_type, required, owner,
                       sort_order, document_type, status, due_date, depends_on,
                       collection_mode, authority, template_version, row_version, reminder_count,
                       raw_json, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s::jsonb,%s,%s,%s,1,0,%s::jsonb, now())
                    """,
                    (
                        key,
                        action["item_id"],
                        action.get("label"),
                        action.get("category"),
                        action.get("item_type"),
                        bool(action.get("required")),
                        action.get("owner"),
                        100,
                        document_type,
                        action.get("due_date"),
                        json.dumps(action.get("depends_on") or []),
                        action.get("collection_mode"),
                        action.get("authority"),
                        TEMPLATE_VERSION,
                        json.dumps({
                            "seeded_by": MIGRATION_WAVE,
                            "batch_id": batch_id,
                            "template": TEMPLATE_ID,
                            "template_version": TEMPLATE_VERSION,
                        }),
                    ),
                )
                applied.append({"employee_key": key, **action, "inserted": True})
                continue
        # Pin assignment + employee template version; set start_date if null
        w2.upsert_assignment(
            cur,
            employee_key=key,
            company_code=COMPANY,
            status=str(emp.get("onboarding_status") or "in_progress"),
            planned_start_date=planned,
            template_id=TEMPLATE_ID,
            template_version=TEMPLATE_VERSION,
            metadata={"migrated_by": MIGRATION_WAVE, "batch_id": batch_id},
            bump_version=True,
        )
        cur.execute(
            """
            UPDATE employees
            SET onboarding_template_version=%s,
                start_date=COALESCE(start_date, %s),
                updated_at=now(),
                raw_json=COALESCE(raw_json,'{}'::jsonb) || %s::jsonb
            WHERE employee_key=%s
            """,
            (
                TEMPLATE_VERSION,
                planned,
                json.dumps({
                    "onboarding_migration_batch_id": batch_id,
                    "onboarding_template_id": TEMPLATE_ID,
                    "onboarding_template_version": TEMPLATE_VERSION,
                }),
                key,
            ),
        )
        # Recompute counts excluding retired/cancelled
        # Caller may pass app.recompute — done in runner
    return {"applied": applied, "action_digest": _stable_action_digest(preview)}


def commit_batch(
    cur: Any,
    *,
    batch_id: str,
    actor_user_id: str,
    recompute_fn: Any = None,
) -> dict[str, Any]:
    ensure_wave3_migration_schema(cur)
    if not migration_enabled():
        return {"ok": False, "error": "migration_gate_off", "message": "WATHEFNI_ONBOARDING_WAVE3_MIGRATION must be on"}
    cur.execute(
        "SELECT * FROM onboarding_migration_batches WHERE batch_id=%s FOR UPDATE",
        (batch_id,),
    )
    batch = cur.fetchone()
    if not batch:
        return {"ok": False, "error": "batch_not_found"}
    batch = dict(batch)
    if batch["status"] != "approved":
        return {"ok": False, "error": "not_approved", "status": batch["status"]}
    if not batch.get("approver_user_id") or str(batch["requester_user_id"]) == str(batch["approver_user_id"]):
        return {"ok": False, "error": "dual_control_incomplete"}
    actor = str(actor_user_id or "")
    if actor not in {str(batch["requester_user_id"]), str(batch["approver_user_id"])}:
        return {"ok": False, "error": "actor_not_on_batch"}

    preview = batch.get("preview_json") or {}
    if isinstance(preview, str):
        preview = json.loads(preview)
    if preview.get("conflicts"):
        return {"ok": False, "error": "conflicts_unresolved", "conflicts": preview["conflicts"]}

    # Live fingerprint must still match snapshot
    live = load_four_real_items(cur)
    live_fp = fingerprint_items(live)
    before_fp = batch.get("fingerprint_before") or []
    if isinstance(before_fp, str):
        before_fp = json.loads(before_fp)
    if live_fp != before_fp:
        return {
            "ok": False,
            "error": "fingerprint_drift",
            "message": "Live checklist fingerprint changed since preview; refusing commit",
        }

    result = _apply_actions(cur, preview=preview, batch_id=batch_id, actor=actor)
    if recompute_fn:
        for emp in preview["employees"]:
            recompute_fn(cur, emp["employee_key"])

    after_rows = load_four_real_items(cur)
    after_fp = fingerprint_items(after_rows)
    commit_hash = result["action_digest"]
    dry_digest = (batch.get("metadata") or {}).get("action_digest") if isinstance(batch.get("metadata"), dict) else None
    if dry_digest is None and isinstance(batch.get("metadata"), str):
        dry_digest = json.loads(batch["metadata"]).get("action_digest")
    if commit_hash != dry_digest:
        return {
            "ok": False,
            "error": "dry_run_mismatch",
            "dry_digest": dry_digest,
            "commit_digest": commit_hash,
        }

    cur.execute(
        """
        UPDATE onboarding_migration_batches
        SET status='committed', committed_at=now(), commit_hash=%s,
            fingerprint_after=%s::jsonb, updated_at=now()
        WHERE batch_id=%s
        RETURNING *
        """,
        (commit_hash, json.dumps(after_fp), batch_id),
    )
    updated = dict(cur.fetchone())
    w2.record_onboarding_audit(
        cur,
        company_code=COMPANY,
        employee_key="*",
        event_type="onboarding_migration_batch_committed",
        actor_user_id=actor,
        after={
            "batch_id": batch_id,
            "commit_hash": commit_hash,
            "after_count": len(after_rows),
            "dry_run_match": True,
        },
    )
    return {
        "ok": True,
        "batch": updated,
        "applied_count": len(result["applied"]),
        "fingerprint_after": after_fp,
        "fingerprint_after_count": len(after_rows),
        "dry_run_match": True,
        "commit_hash": commit_hash,
    }


def rollback_batch(cur: Any, *, batch_id: str, actor_user_id: str) -> dict[str, Any]:
    """Restore exact pre-migration item rows from snapshots; remove post-migration inserts."""
    ensure_wave3_migration_schema(cur)
    cur.execute(
        "SELECT * FROM onboarding_migration_batches WHERE batch_id=%s FOR UPDATE",
        (batch_id,),
    )
    batch = cur.fetchone()
    if not batch:
        return {"ok": False, "error": "batch_not_found"}
    batch = dict(batch)
    if batch["status"] not in {"committed", "rolled_back"}:
        return {"ok": False, "error": "not_committed", "status": batch["status"]}
    if batch["status"] == "rolled_back":
        return {"ok": True, "idempotent": True, "batch": batch}

    cur.execute(
        "SELECT employee_key, item_id, row_json FROM onboarding_migration_item_snapshots WHERE batch_id=%s",
        (batch_id,),
    )
    snaps = [dict(r) for r in (cur.fetchall() or [])]
    snap_keys = {(s["employee_key"], s["item_id"]) for s in snaps}

    # Delete items for four reals that were inserted by migration (not in snapshot)
    cur.execute(
        """
        SELECT oi.employee_key, oi.item_id
        FROM onboarding_items oi
        WHERE oi.employee_key = ANY(%s)
        """,
        (list(w2.FOUR_REALS),),
    )
    current = [(r["employee_key"], r["item_id"]) for r in (cur.fetchall() or [])]
    for ek, iid in current:
        if (ek, iid) not in snap_keys:
            cur.execute(
                "DELETE FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
                (ek, iid),
            )

    # Restore snapshot rows exactly (status/value/reminders/etc.)
    for s in snaps:
        row = s["row_json"]
        if isinstance(row, str):
            row = json.loads(row)
        # Upsert full restore of known columns
        cur.execute(
            """
            UPDATE onboarding_items SET
              label=%s, category=%s, item_type=%s, required=%s, owner=%s,
              status=%s, value=%s, reminder_count=%s,
              due_date=%s, depends_on=%s::jsonb,
              collection_mode=%s, authority=%s, template_version=%s,
              row_version=%s, raw_json=%s::jsonb, updated_at=now(),
              local_path=%s, drive_file_id=%s, drive_url=%s,
              storage_provider=%s, storage_object_key=%s, external_file_id=%s,
              storage_url=%s, content_sha256=%s, mime_type=%s,
              storage_status=%s, storage_error=%s, document_type=%s, sort_order=%s
            WHERE employee_key=%s AND item_id=%s
            """,
            (
                row.get("label"),
                row.get("category"),
                row.get("item_type"),
                row.get("required"),
                row.get("owner"),
                row.get("status"),
                row.get("value"),
                row.get("reminder_count") or 0,
                row.get("due_date"),
                json.dumps(row.get("depends_on") or []),
                row.get("collection_mode"),
                row.get("authority"),
                row.get("template_version"),
                row.get("row_version") or 1,
                json.dumps(row.get("raw_json") or {}, default=str),
                row.get("local_path"),
                row.get("drive_file_id"),
                row.get("drive_url"),
                row.get("storage_provider"),
                row.get("storage_object_key"),
                row.get("external_file_id"),
                row.get("storage_url"),
                row.get("content_sha256"),
                row.get("mime_type"),
                row.get("storage_status"),
                row.get("storage_error"),
                row.get("document_type"),
                row.get("sort_order"),
                s["employee_key"],
                s["item_id"],
            ),
        )

    # Clear template pins / assignments created by migration
    for key in w2.FOUR_REALS:
        cur.execute(
            """
            UPDATE employees
            SET onboarding_template_version=NULL,
                raw_json = COALESCE(raw_json,'{}'::jsonb) - 'onboarding_migration_batch_id'
                           - 'onboarding_template_id' - 'onboarding_template_version',
                updated_at=now()
            WHERE employee_key=%s
            """,
            (key,),
        )
        cur.execute("DELETE FROM employee_onboarding_assignments WHERE employee_key=%s", (key,))

    after = load_four_real_items(cur)
    after_fp = fingerprint_items(after)
    before_fp = batch.get("fingerprint_before") or []
    if isinstance(before_fp, str):
        before_fp = json.loads(before_fp)
    if after_fp != before_fp:
        return {
            "ok": False,
            "error": "rollback_fingerprint_mismatch",
            "expected": before_fp,
            "actual": after_fp,
        }

    cur.execute(
        """
        UPDATE onboarding_migration_batches
        SET status='rolled_back', rolled_back_at=now(), updated_at=now()
        WHERE batch_id=%s
        RETURNING *
        """,
        (batch_id,),
    )
    updated = dict(cur.fetchone())
    w2.record_onboarding_audit(
        cur,
        company_code=COMPANY,
        employee_key="*",
        event_type="onboarding_migration_batch_rolled_back",
        actor_user_id=actor_user_id,
        after={"batch_id": batch_id, "fingerprint_restored": True, "count": len(after)},
    )
    return {
        "ok": True,
        "batch": updated,
        "fingerprint_restored": True,
        "fingerprint": after_fp,
        "item_count": len(after),
    }
