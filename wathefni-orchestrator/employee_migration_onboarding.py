"""Migration & Sync P3 — existing-employee onboarding migration.

Honest dispositions for workforce cutover. Never fakes Wathefni checklist
completion. Reuses import batch/row/provenance + 3-layer field mapping.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import schema_contract

CONTRACT = "employee_migration_sync_p3_onboarding"
CONTRACT_VERSION = "3.0.0"

DISPOSITION_ALREADY_EXTERNAL = "already_onboarded_externally"
DISPOSITION_HISTORY_IMPORTED = "onboarding_history_imported"
DISPOSITION_NOT_APPLICABLE = "onboarding_not_applicable"
DISPOSITION_NEEDS_WATHEFNI = "needs_wathefni_onboarding"
DISPOSITION_UNKNOWN = "unknown_insufficient_evidence"

DISPOSITIONS = frozenset(
    {
        DISPOSITION_ALREADY_EXTERNAL,
        DISPOSITION_HISTORY_IMPORTED,
        DISPOSITION_NOT_APPLICABLE,
        DISPOSITION_NEEDS_WATHEFNI,
        DISPOSITION_UNKNOWN,
    }
)

# Hub onboarding_status values that exit the HR "needs onboarding" queue.
SETTLED_HUB_STATUSES = frozenset(
    {
        "migrated_external",
        "imported_history",
        "not_applicable",
        "complete",
        "completed",
        "done",
    }
)

SETTLED_DISPOSITIONS = frozenset(
    {
        DISPOSITION_ALREADY_EXTERNAL,
        DISPOSITION_HISTORY_IMPORTED,
        DISPOSITION_NOT_APPLICABLE,
    }
)

DISPOSITION_TO_HUB = {
    DISPOSITION_ALREADY_EXTERNAL: "migrated_external",
    DISPOSITION_HISTORY_IMPORTED: "imported_history",
    DISPOSITION_NOT_APPLICABLE: "not_applicable",
    DISPOSITION_NEEDS_WATHEFNI: "not_started",
    DISPOSITION_UNKNOWN: "not_started",
}

# Source value → disposition (high confidence). Empty stays unknown.
_STATUS_ALIASES: dict[str, str] = {
    "already_onboarded_externally": DISPOSITION_ALREADY_EXTERNAL,
    "onboarded_externally": DISPOSITION_ALREADY_EXTERNAL,
    "externally_onboarded": DISPOSITION_ALREADY_EXTERNAL,
    "completed_externally": DISPOSITION_ALREADY_EXTERNAL,
    "completed_outside": DISPOSITION_ALREADY_EXTERNAL,
    "onboarded": DISPOSITION_ALREADY_EXTERNAL,
    "completed": DISPOSITION_ALREADY_EXTERNAL,
    "complete": DISPOSITION_ALREADY_EXTERNAL,
    "done": DISPOSITION_ALREADY_EXTERNAL,
    "finished": DISPOSITION_ALREADY_EXTERNAL,
    "history_imported": DISPOSITION_HISTORY_IMPORTED,
    "onboarding_history_imported": DISPOSITION_HISTORY_IMPORTED,
    "imported_history": DISPOSITION_HISTORY_IMPORTED,
    "not_applicable": DISPOSITION_NOT_APPLICABLE,
    "onboarding_not_applicable": DISPOSITION_NOT_APPLICABLE,
    "n/a": DISPOSITION_NOT_APPLICABLE,
    "na": DISPOSITION_NOT_APPLICABLE,
    "not_required": DISPOSITION_NOT_APPLICABLE,
    "needs_wathefni_onboarding": DISPOSITION_NEEDS_WATHEFNI,
    "needs_onboarding": DISPOSITION_NEEDS_WATHEFNI,
    "require_onboarding": DISPOSITION_NEEDS_WATHEFNI,
    "required": DISPOSITION_NEEDS_WATHEFNI,
    "pending": DISPOSITION_NEEDS_WATHEFNI,
    "not_started": DISPOSITION_NEEDS_WATHEFNI,
    "unknown": DISPOSITION_UNKNOWN,
    "insufficient": DISPOSITION_UNKNOWN,
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS employee_onboarding_migration (
  company_code text NOT NULL,
  employee_key text NOT NULL,
  disposition text NOT NULL,
  source_status text,
  source_completed_at text,
  source_system text,
  batch_id uuid,
  row_id uuid,
  authority text NOT NULL DEFAULT 'imported',
  native_superseded boolean NOT NULL DEFAULT false,
  start_requested boolean NOT NULL DEFAULT false,
  started_at timestamptz,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, employee_key),
  CHECK (disposition = ANY (ARRAY[
    'already_onboarded_externally',
    'onboarding_history_imported',
    'onboarding_not_applicable',
    'needs_wathefni_onboarding',
    'unknown_insufficient_evidence'
  ]))
);
CREATE INDEX IF NOT EXISTS idx_employee_onboarding_migration_batch
  ON employee_onboarding_migration(batch_id);
CREATE INDEX IF NOT EXISTS idx_employee_onboarding_migration_disposition
  ON employee_onboarding_migration(company_code, disposition);

CREATE TABLE IF NOT EXISTS employee_onboarding_migration_history (
  history_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  batch_id uuid,
  row_id uuid,
  task_key text,
  task_label text,
  source_status text,
  source_completed_at text,
  source_system text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_employee_onboarding_migration_history_emp
  ON employee_onboarding_migration_history(company_code, employee_key);
CREATE INDEX IF NOT EXISTS idx_employee_onboarding_migration_history_batch
  ON employee_onboarding_migration_history(batch_id);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


_ONBOARDING_SCHEMA_READY = False


def ensure_onboarding_migration_schema(cur: Any, *, force: bool = False) -> None:
    global _ONBOARDING_SCHEMA_READY
    if _ONBOARDING_SCHEMA_READY and not force:
        return
    schema_contract.ensure_sql(
        cur,
        SCHEMA_SQL,
        required_tables=[
            "employee_onboarding_migration",
            "employee_onboarding_migration_history",
        ],
        module="employee_migration_onboarding",
        lock_id=None,
    )
    _ONBOARDING_SCHEMA_READY = True


def honesty_payload() -> dict[str, Any]:
    return {
        "contract": CONTRACT,
        "version": CONTRACT_VERSION,
        "dispositions": sorted(DISPOSITIONS),
        "no_fake_completion": True,
        "no_auto_start_default": True,
        "no_invites": True,
        "missing_means_unknown": True,
        "native_wathefni_wins": True,
        "settled_hub_statuses": sorted(SETTLED_HUB_STATUSES),
    }


def normalize_disposition(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    text = re.sub(r"[\s\-]+", "_", text)
    if text in DISPOSITIONS:
        return text
    return _STATUS_ALIASES.get(text)


def parse_history_payload(raw: Any) -> list[dict[str, Any]]:
    """Accept JSON array or semicolon task=status pairs. Never invents rows."""
    if raw is None:
        return []
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, dict):
                out.append(dict(item))
            elif item:
                out.append({"task_key": str(item), "source_status": "completed"})
        return out
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            return parse_history_payload(parsed)
        except Exception:
            return []
    rows: list[dict[str, Any]] = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, status = part.split("=", 1)
            rows.append({"task_key": key.strip(), "source_status": status.strip() or "completed"})
        else:
            rows.append({"task_key": part, "source_status": "completed"})
    return rows


def resolve_disposition_from_canonical(canonical: dict[str, str]) -> dict[str, Any]:
    """Derive disposition from mapped canonical onboarding fields.

    Rules:
    - Explicit disposition / status wins when recognized.
    - History payload without status → history_imported.
    - Empty / unrecognized → unknown (never invent already-onboarded from employment_status).
    """
    explicit = normalize_disposition(canonical.get("onboarding_migration_disposition"))
    status = normalize_disposition(canonical.get("onboarding_status"))
    history = parse_history_payload(canonical.get("onboarding_history"))
    completed_at = str(canonical.get("onboarding_completed_at") or "").strip() or None
    start_flag = str(canonical.get("onboarding_start_after_import") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }

    disposition = explicit or status
    if history and disposition in {None, DISPOSITION_ALREADY_EXTERNAL}:
        disposition = DISPOSITION_HISTORY_IMPORTED
    if not disposition:
        disposition = DISPOSITION_UNKNOWN

    needs_review = disposition == DISPOSITION_UNKNOWN and bool(
        canonical.get("onboarding_status")
        or canonical.get("onboarding_migration_disposition")
        or canonical.get("onboarding_completed_at")
        or history
    )
    # Unrecognized free-text status with no alias → unknown + review
    raw_status = str(canonical.get("onboarding_status") or "").strip()
    if raw_status and normalize_disposition(raw_status) is None and not explicit:
        disposition = DISPOSITION_UNKNOWN
        needs_review = True

    # Completed_at alone without status is insufficient → unknown + review
    if not explicit and not status and completed_at and not history:
        disposition = DISPOSITION_UNKNOWN
        needs_review = True

    preview_label = {
        DISPOSITION_ALREADY_EXTERNAL: "Existing employee — already onboarded externally",
        DISPOSITION_HISTORY_IMPORTED: "Existing employee — history will be imported",
        DISPOSITION_NOT_APPLICABLE: "Existing employee — onboarding not applicable",
    DISPOSITION_NEEDS_WATHEFNI: "Requires OctoHR onboarding",
        DISPOSITION_UNKNOWN: "Needs review — insufficient onboarding evidence",
    }.get(disposition, "Needs review")

    return {
        "disposition": disposition,
        "source_status": raw_status or None,
        "source_completed_at": completed_at,
        "history": history,
        "start_requested": bool(start_flag and disposition == DISPOSITION_NEEDS_WATHEFNI),
        "needs_review": needs_review or disposition == DISPOSITION_UNKNOWN,
        "preview_label": preview_label,
        "hub_status": DISPOSITION_TO_HUB[disposition],
    }


def load_migration(cur: Any, *, company: str, employee_key: str) -> dict[str, Any] | None:
    ensure_onboarding_migration_schema(cur)
    cur.execute(
        """
        SELECT * FROM employee_onboarding_migration
        WHERE company_code=%s AND employee_key=%s
        """,
        (company, employee_key),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def employee_has_native_onboarding_activity(cur: Any, *, employee_key: str) -> bool:
    """True when Wathefni has launched assignment or checklist progress beyond import."""
    try:
        cur.execute("SAVEPOINT p3_native_assign_probe")
        cur.execute(
            "SELECT status FROM employee_onboarding_assignments WHERE employee_key=%s LIMIT 1",
            (employee_key,),
        )
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT p3_native_assign_probe")
        status = str((row or {}).get("status") or "").lower()
        if status in {"in_progress", "started", "active", "delayed", "completed"}:
            return True
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT p3_native_assign_probe")
        except Exception:
            pass
    try:
        cur.execute("SAVEPOINT p3_native_items_probe")
        cur.execute(
            """
            SELECT count(*) AS c FROM onboarding_items
            WHERE employee_key=%s
              AND lower(coalesce(status,'')) NOT IN ('', 'pending', 'missing', 'not_started')
            """,
            (employee_key,),
        )
        count = int((cur.fetchone() or {}).get("c") or 0)
        cur.execute("RELEASE SAVEPOINT p3_native_items_probe")
        if count > 0:
            return True
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT p3_native_items_probe")
        except Exception:
            pass
    return False


def apply_migrated_completion_mirror(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    disposition: str,
    source_completed_at: str | None,
    source_system: str | None,
    batch_id: str | None,
    actor: str | None,
) -> dict[str, Any]:
    """Persist completion projection for settled migrations without inventing checklist items."""
    import onboarding_completion_contract as occ

    hub = DISPOSITION_TO_HUB.get(disposition, "not_started")
    settled = disposition in SETTLED_DISPOSITIONS
    state = occ.STATE_COMPLETED if settled and disposition != DISPOSITION_NOT_APPLICABLE else (
        occ.STATE_COMPLETED if disposition == DISPOSITION_NOT_APPLICABLE else occ.STATE_NOT_STARTED
    )
    # not_applicable: treat as settled complete for reminders/queues via hub status,
    # completion state completed with honest reason.
    if disposition == DISPOSITION_NOT_APPLICABLE:
        state = occ.STATE_COMPLETED
    reason = f"migration_{disposition}"
    evidence = {
        "source": "migration_import",
        "disposition": disposition,
        "authority": "imported",
        "wathefni_performed": False,
        "source_system": source_system,
        "batch_id": batch_id,
        "source_completed_at": source_completed_at,
        "recorded_at": _now().isoformat(),
        "actor": actor,
    }
    snapshot = {
        "contract_version": occ.CONTRACT_VERSION,
        "state": state,
        "reason": reason,
        "is_complete": settled,
        "required_total": 0,
        "satisfied_count": 0,
        "open_count": 0,
        "counts": {},
        "migration": evidence,
        "legacy_onboarding_status": hub,
        "documents_pending": 0,
        "documents_complete": 0,
        "waiting_on_employee_items": [],
        "waiting_on_hr_items": [],
        "blocked_items": [],
        "suppress_reminders": True,
        "suppress_checklist": True,
    }
    occ.ensure_completion_schema(cur)
    prior = occ.load_completion_row(cur, company_code=company, employee_key=employee_key)
    # Never erase a prior native first_completed_at with migration — COALESCE in upsert.
    completed_at = None
    if settled:
        completed_at = source_completed_at or _now().isoformat()
    occ.persist_completion(
        cur,
        company_code=company,
        employee_key=employee_key,
        snapshot=snapshot,
        actor=actor or "migration_p3",
    )
    # Append migration evidence explicitly
    cur.execute(
        """
        UPDATE employee_onboarding_completion
        SET completion_evidence = completion_evidence || %s::jsonb,
            first_completed_at = COALESCE(first_completed_at, NULLIF(%s,'')::timestamptz, CASE WHEN %s THEN now() ELSE NULL END),
            last_completed_at = COALESCE(NULLIF(%s,'')::timestamptz, last_completed_at, CASE WHEN %s THEN now() ELSE NULL END),
            updated_at=now()
        WHERE company_code=%s AND employee_key=%s
        """,
        (
            json.dumps([evidence]),
            source_completed_at or "",
            settled,
            source_completed_at or "",
            settled,
            company,
            employee_key,
        ),
    )
    cur.execute(
        """
        UPDATE employees
        SET onboarding_status=%s,
            documents_pending=0,
            documents_complete=0
        WHERE company_code=%s AND employee_key=%s
          AND coalesce(onboarding_status,'') IS DISTINCT FROM %s
        """,
        (hub, company, employee_key, hub),
    )
    del prior
    return {"hub_status": hub, "state": state, "snapshot": snapshot}


def upsert_onboarding_migration(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    resolved: dict[str, Any],
    batch_id: str,
    row_id: str,
    source_system: str | None,
    actor: str | None,
) -> dict[str, Any]:
    ensure_onboarding_migration_schema(cur)
    existing = load_migration(cur, company=company, employee_key=employee_key)
    if existing and existing.get("native_superseded"):
        return {
            "ok": False,
            "skipped": True,
            "reason": "native_wathefni_activity_supersedes_import",
            "existing": _jsonable(existing),
        }
    if employee_has_native_onboarding_activity(cur, employee_key=employee_key):
        if existing:
            cur.execute(
                """
                UPDATE employee_onboarding_migration
                SET native_superseded=true, updated_at=now(),
                    provenance = provenance || %s::jsonb
                WHERE company_code=%s AND employee_key=%s
                """,
                (
                    json.dumps({"superseded_at": _now().isoformat(), "by": "native_activity_guard"}),
                    company,
                    employee_key,
                ),
            )
        return {
            "ok": False,
            "skipped": True,
            "reason": "native_wathefni_activity_present",
        }

    disposition = resolved["disposition"]
    provenance = {
        "batch_id": batch_id,
        "row_id": row_id,
        "preview_label": resolved.get("preview_label"),
        "imported_at": _now().isoformat(),
        "actor": actor,
        "contract": CONTRACT,
        "version": CONTRACT_VERSION,
    }
    cur.execute(
        """
        INSERT INTO employee_onboarding_migration (
          company_code, employee_key, disposition, source_status, source_completed_at,
          source_system, batch_id, row_id, authority, native_superseded, start_requested,
          provenance, updated_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'imported',false,%s,%s::jsonb,now())
        ON CONFLICT (company_code, employee_key) DO UPDATE SET
          disposition=EXCLUDED.disposition,
          source_status=EXCLUDED.source_status,
          source_completed_at=EXCLUDED.source_completed_at,
          source_system=EXCLUDED.source_system,
          batch_id=EXCLUDED.batch_id,
          row_id=EXCLUDED.row_id,
          authority='imported',
          start_requested=EXCLUDED.start_requested,
          provenance=EXCLUDED.provenance,
          updated_at=now()
        WHERE employee_onboarding_migration.native_superseded IS NOT TRUE
        RETURNING *
        """,
        (
            company,
            employee_key,
            disposition,
            resolved.get("source_status"),
            resolved.get("source_completed_at"),
            source_system,
            batch_id,
            row_id,
            bool(resolved.get("start_requested")),
            json.dumps(provenance),
        ),
    )
    row = cur.fetchone()
    # Replace history rows for this batch (idempotent re-import)
    cur.execute(
        "DELETE FROM employee_onboarding_migration_history WHERE company_code=%s AND employee_key=%s AND batch_id=%s",
        (company, employee_key, batch_id),
    )
    for item in resolved.get("history") or []:
        cur.execute(
            """
            INSERT INTO employee_onboarding_migration_history (
              company_code, employee_key, batch_id, row_id, task_key, task_label,
              source_status, source_completed_at, source_system, payload
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                company,
                employee_key,
                batch_id,
                row_id,
                str(item.get("task_key") or item.get("key") or "")[:120] or None,
                str(item.get("task_label") or item.get("label") or "")[:240] or None,
                str(item.get("source_status") or item.get("status") or "")[:80] or None,
                str(item.get("source_completed_at") or item.get("completed_at") or "")[:64] or None,
                source_system,
                json.dumps({"imported": True, "wathefni_verified": False, **{k: v for k, v in item.items()}}),
            ),
        )

    mirror = None
    if disposition in SETTLED_DISPOSITIONS:
        mirror = apply_migrated_completion_mirror(
            cur,
            company=company,
            employee_key=employee_key,
            disposition=disposition,
            source_completed_at=resolved.get("source_completed_at"),
            source_system=source_system,
            batch_id=batch_id,
            actor=actor,
        )
    elif disposition == DISPOSITION_NEEDS_WATHEFNI:
        # Explicit: leave not_started; do not seed checklist here.
        cur.execute(
            """
            UPDATE employees SET onboarding_status='not_started'
            WHERE company_code=%s AND employee_key=%s
              AND coalesce(onboarding_status,'') IN ('', 'not_started', 'pending')
            """,
            (company, employee_key),
        )
    # unknown: do not change hub status beyond default create

    return {
        "ok": True,
        "migration": _jsonable(dict(row) if row else {}),
        "mirror": mirror,
        "disposition": disposition,
    }


def maybe_start_wathefni_onboarding(
    legacy: Any,
    *,
    company: str,
    employee_key: str,
    start_requested: bool,
) -> dict[str, Any]:
    """Deliberate start only — never an automatic import side effect."""
    if not start_requested:
        return {"started": False, "reason": "not_requested"}
    emp = legacy.find_employee_by_key(employee_key) if hasattr(legacy, "find_employee_by_key") else None
    if not emp:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM employees WHERE company_code=%s AND employee_key=%s",
                    (company, employee_key),
                )
                emp = dict(cur.fetchone() or {})
                conn.commit()
    if not emp:
        return {"started": False, "reason": "employee_missing"}
    try:
        result = legacy.start_onboarding(emp)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                ensure_onboarding_migration_schema(cur)
                cur.execute(
                    """
                    UPDATE employee_onboarding_migration
                    SET started_at=now(), updated_at=now(),
                        provenance = provenance || %s::jsonb
                    WHERE company_code=%s AND employee_key=%s
                    """,
                    (
                        json.dumps({"started_via": "migration_p3_explicit", "at": _now().isoformat()}),
                        company,
                        employee_key,
                    ),
                )
                conn.commit()
        return {"started": True, "result": _jsonable(result)}
    except Exception as exc:
        return {"started": False, "reason": str(exc)[:240]}


def recompute_guard(
    cur: Any,
    *,
    company: str,
    employee_key: str,
) -> dict[str, Any] | None:
    """If migration settled and no native activity, short-circuit recompute.

    Returns a completion-like snapshot when migration should win; None to continue.
    """
    mig = load_migration(cur, company=company, employee_key=employee_key)
    if not mig or mig.get("native_superseded"):
        return None
    disposition = str(mig.get("disposition") or "")
    if disposition not in SETTLED_DISPOSITIONS:
        return None
    if employee_has_native_onboarding_activity(cur, employee_key=employee_key):
        cur.execute(
            """
            UPDATE employee_onboarding_migration
            SET native_superseded=true, updated_at=now(),
                provenance = provenance || %s::jsonb
            WHERE company_code=%s AND employee_key=%s
            """,
            (
                json.dumps({"superseded_at": _now().isoformat(), "by": "recompute_native_activity"}),
                company,
                employee_key,
            ),
        )
        return None
    mirrored = apply_migrated_completion_mirror(
        cur,
        company=company,
        employee_key=employee_key,
        disposition=disposition,
        source_completed_at=mig.get("source_completed_at"),
        source_system=mig.get("source_system"),
        batch_id=str(mig.get("batch_id") or "") or None,
        actor="recompute_migration_guard",
    )
    return mirrored.get("snapshot")


def projection_overlay(
    *,
    company: str,
    employee_key: str,
    locale: str = "en",
) -> dict[str, Any] | None:
    """HR/employee-safe overlay. Avoid internal jargon for employees."""
    try:
        import app as legacy

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                mig = load_migration(cur, company=company, employee_key=employee_key)
                history = []
                if mig:
                    cur.execute(
                        """
                        SELECT task_key, task_label, source_status, source_completed_at, source_system, payload
                        FROM employee_onboarding_migration_history
                        WHERE company_code=%s AND employee_key=%s
                        ORDER BY created_at
                        """,
                        (company, employee_key),
                    )
                    history = [dict(r) for r in (cur.fetchall() or [])]
                conn.commit()
    except Exception:
        return None
    if not mig or mig.get("native_superseded"):
        return None
    disposition = str(mig.get("disposition") or "")
    is_ar = str(locale or "").lower().startswith("ar")
    employee_messages = {
        DISPOSITION_ALREADY_EXTERNAL: (
                    "تم إكمال التهيئة خارج OctoHR." if is_ar else "Your onboarding was completed outside OctoHR."
        ),
        DISPOSITION_HISTORY_IMPORTED: (
            "تم استيراد سجل التهيئة السابق." if is_ar else "Your previous onboarding history was imported."
        ),
        DISPOSITION_NOT_APPLICABLE: (
            "التهيئة غير مطلوبة لحسابك." if is_ar else "Onboarding is not required for your account."
        ),
    }
    hr_labels = {
        DISPOSITION_ALREADY_EXTERNAL: "Already onboarded externally (migrated)",
        DISPOSITION_HISTORY_IMPORTED: "Onboarding history imported (migrated)",
        DISPOSITION_NOT_APPLICABLE: "Onboarding not applicable (migrated)",
        DISPOSITION_NEEDS_WATHEFNI: "Needs OctoHR onboarding",
        DISPOSITION_UNKNOWN: "Unknown — insufficient source evidence",
    }
    settled = disposition in SETTLED_DISPOSITIONS
    return {
        "disposition": disposition,
        "settled": settled,
        "native_superseded": False,
        "source_system": mig.get("source_system"),
        "source_completed_at": mig.get("source_completed_at"),
        "authority": "imported",
        "wathefni_performed": False,
        "employee_message": employee_messages.get(disposition),
        "hr_label": hr_labels.get(disposition),
        "suppress_checklist": settled,
        "suppress_reminders": settled,
        "history_imported_count": len(history),
        "history": _jsonable(history) if history else [],
        "batch_id": str(mig.get("batch_id") or "") or None,
    }


def rollback_onboarding_migration_for_batch(cur: Any, *, company: str, batch_id: str) -> dict[str, int]:
    """Remove migration stamps for this batch without erasing newer native activity."""
    ensure_onboarding_migration_schema(cur)
    cur.execute(
        """
        SELECT employee_key, native_superseded, disposition
        FROM employee_onboarding_migration
        WHERE company_code=%s AND batch_id=%s
        """,
        (company, batch_id),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    removed = 0
    preserved = 0
    for row in rows:
        key = str(row["employee_key"])
        if row.get("native_superseded") or employee_has_native_onboarding_activity(cur, employee_key=key):
            preserved += 1
            continue
        cur.execute(
            "DELETE FROM employee_onboarding_migration_history WHERE company_code=%s AND employee_key=%s AND batch_id=%s",
            (company, key, batch_id),
        )
        cur.execute(
            "DELETE FROM employee_onboarding_migration WHERE company_code=%s AND employee_key=%s AND batch_id=%s",
            (company, key, batch_id),
        )
        # Reset hub status only when still a migration settled stamp from this batch
        cur.execute(
            """
            UPDATE employees
            SET onboarding_status='not_started'
            WHERE company_code=%s AND employee_key=%s
              AND lower(coalesce(onboarding_status,'')) IN ('migrated_external','imported_history','not_applicable')
            """,
            (company, key),
        )
        # Soft-clear migration evidence only — do not delete completion if native first_completed_at exists with other evidence
        cur.execute(
            """
            DELETE FROM employee_onboarding_completion
            WHERE company_code=%s AND employee_key=%s
              AND (snapshot->>'reason') LIKE 'migration_%%'
              AND NOT EXISTS (
                SELECT 1 FROM onboarding_items WHERE employee_key=%s
              )
            """,
            (company, key, key),
        )
        removed += 1
    cur.execute(
        "DELETE FROM employee_onboarding_migration_history WHERE company_code=%s AND batch_id=%s",
        (company, batch_id),
    )
    return {"removed": removed, "preserved_native": preserved}


def preview_label_for_row(detail: dict[str, Any] | None) -> str | None:
    block = (detail or {}).get("onboarding_migration") or {}
    return block.get("preview_label")
