#!/usr/bin/env python3
"""Disposable Civil ID canary checklist item for Aziz Document Validation Parity tests.

Safety:
  - Touches ONLY item_id=civil_id_canary_test for WATHEFNI-96599338566
  - Never mutates real civil_id / accepted docs / required progress
  - document_type stays civil_id_canary_test (isolated governed lane)
  - Soft-gate validates as Civil ID via CANARY_VALIDATION_ALIASES

Usage on production orchestrator host:
  WATHEFNI_ENV=production .venv/bin/python ops-aziz-docval-canary-item.py create
  WATHEFNI_ENV=production .venv/bin/python ops-aziz-docval-canary-item.py verify
  WATHEFNI_ENV=production .venv/bin/python ops-aziz-docval-canary-item.py reset
  WATHEFNI_ENV=production .venv/bin/python ops-aziz-docval-canary-item.py cleanup
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

EMP = "WATHEFNI-96599338566"
COMPANY = "WATHEFNI"
ITEM = "civil_id_canary_test"
LABEL = "CANARY ONLY — Civil ID upload test (disposable)"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def snapshot_real_civil_id(cur) -> dict[str, Any]:
    cur.execute(
        """
        SELECT item_id, status, required, document_type, value, storage_status,
               content_sha256, row_version, lifecycle_meta
        FROM onboarding_items
        WHERE employee_key=%s AND item_id='civil_id'
        """,
        (EMP,),
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit("ABORT: real civil_id missing for Aziz")
    return dict(row)


def create(cur) -> dict[str, Any]:
    real = snapshot_real_civil_id(cur)
    cur.execute(
        "SELECT 1 FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
        (EMP, ITEM),
    )
    if cur.fetchone():
        return {"action": "already_present", "civil_id": real["status"]}

    meta = {
        "explicitly_assigned": True,
        "canary": True,
        "disposable": True,
        "purpose": "document_validation_parity_live_test",
        "do_not_approve_as_real": True,
        "created_at": _now(),
    }
    raw = {
        "seeded_by": "ops_aziz_docval_canary_item",
        "canary": True,
        "source": ITEM,
    }
    cur.execute(
        """
        INSERT INTO onboarding_items (
          employee_key, item_id, label, category, item_type, required, owner,
          sort_order, document_type, status, depends_on,
          collection_mode, authority, template_version, row_version,
          reminder_count, lifecycle_meta, raw_json, created_at, updated_at
        ) VALUES (
          %s, %s, %s, 'identity_legal', 'document', false, 'employee',
          9999, %s, 'pending', '[]'::jsonb,
          'document', 'onboarding', '2.0.0-canary', 1,
          0, %s::jsonb, %s::jsonb, now(), now()
        )
        """,
        (EMP, ITEM, LABEL, ITEM, json.dumps(meta), json.dumps(raw)),
    )
    return {"action": "created", "civil_id_untouched": real["status"]}


def reset(cur) -> dict[str, Any]:
    """Re-open canary upload without deleting canary version history."""
    real = snapshot_real_civil_id(cur)
    cur.execute(
        """
        UPDATE onboarding_items
        SET status='pending',
            rejection_reason=NULL,
            completed_at=NULL,
            updated_at=now(),
            row_version=row_version+1,
            lifecycle_meta = coalesce(lifecycle_meta,'{}'::jsonb) || %s::jsonb
        WHERE employee_key=%s AND item_id=%s
        RETURNING status, document_type, required
        """,
        (
            json.dumps({"canary_reset_at": _now(), "explicitly_assigned": True, "canary": True}),
            EMP,
            ITEM,
        ),
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit("ABORT: canary item missing — run create first")
    return {"action": "reset", "canary": dict(row), "civil_id_untouched": real["status"]}


def cleanup(cur) -> dict[str, Any]:
    real_before = snapshot_real_civil_id(cur)
    deleted: dict[str, int] = {}

    def _del(label: str, sql: str, params: tuple[Any, ...]) -> None:
        try:
            cur.execute(sql, params)
            deleted[label] = int(cur.rowcount or 0)
        except Exception as exc:  # noqa: BLE001
            deleted[label] = 0
            deleted[f"{label}_error"] = str(exc)[:200]

    _del(
        "governed_document_events",
        """
        DELETE FROM governed_document_events
        WHERE company_code=%s AND employee_key=%s AND document_type=%s
        """,
        (COMPANY, EMP, ITEM),
    )
    _del(
        "governed_document_versions",
        """
        DELETE FROM governed_document_versions
        WHERE company_code=%s AND employee_key=%s AND document_type=%s
        """,
        (COMPANY, EMP, ITEM),
    )
    _del(
        "employee_documents",
        """
        DELETE FROM employee_documents
        WHERE employee_key=%s AND (document_type=%s OR coalesce(item_id,'')=%s)
        """,
        (EMP, ITEM, ITEM),
    )
    _del(
        "file_registry",
        """
        DELETE FROM file_registry
        WHERE company_code=%s AND subject_type='employee' AND subject_key=%s
          AND document_type=%s
        """,
        (COMPANY, EMP, ITEM),
    )
    _del(
        "document_storage_operations",
        """
        DELETE FROM document_storage_operations
        WHERE company_code=%s AND employee_key=%s AND item_id=%s
        """,
        (COMPANY, EMP, ITEM),
    )
    _del(
        "onboarding_audit_events",
        """
        DELETE FROM onboarding_audit_events
        WHERE company_code=%s AND employee_key=%s AND item_id=%s
        """,
        (COMPANY, EMP, ITEM),
    )
    _del(
        "onboarding_items",
        "DELETE FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
        (EMP, ITEM),
    )
    real_after = snapshot_real_civil_id(cur)
    if (
        real_before["status"] != real_after["status"]
        or real_before.get("content_sha256") != real_after.get("content_sha256")
        or real_before.get("value") != real_after.get("value")
    ):
        raise SystemExit(f"ABORT: civil_id changed during cleanup before={real_before} after={real_after}")
    return {"action": "cleanup", "deleted": deleted, "civil_id": real_after["status"]}


def verify_projection() -> dict[str, Any]:
    import app
    import onboarding_lifecycle_wave2a as lc

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            real = snapshot_real_civil_id(cur)
            cur.execute(
                """
                SELECT * FROM onboarding_items
                WHERE employee_key=%s
                ORDER BY sort_order NULLS LAST, item_id
                """,
                (EMP,),
            )
            rows = [dict(r) for r in cur.fetchall()]

    canary = next((r for r in rows if r.get("item_id") == ITEM), None)
    visible = False
    actions: list[str] = []
    group = None
    if canary is not None:
        visible = lc._employee_visible(canary)  # noqa: SLF001
        actions = lc.actions_for_item(canary, can_upload=True, lifecycle_on=True)
        group = lc.group_key_for_item(canary)

    required_excluding = sum(1 for r in rows if r.get("required") and r.get("item_id") != ITEM)
    return {
        "canary_present": canary is not None,
        "canary_status": (canary or {}).get("status"),
        "canary_document_type": (canary or {}).get("document_type"),
        "canary_label": (canary or {}).get("label"),
        "visible_in_employee_app": visible,
        "group": group,
        "actions": actions,
        "upload_enabled": any(a in actions for a in ("upload", "replace", "resubmit")),
        "required_canary": bool(canary and canary.get("required")),
        "real_civil_id_status": real["status"],
        "real_civil_id_required": real["required"],
        "real_civil_id_sha": real.get("content_sha256"),
        "required_item_count_excluding_canary": required_excluding,
    }


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in {"create", "reset", "cleanup", "verify"}:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    import app

    if cmd == "verify":
        report = verify_projection()
        print(json.dumps(report, indent=2, default=str))
        ok = (
            report["canary_present"]
            and report["visible_in_employee_app"]
            and report["upload_enabled"]
            and report["canary_document_type"] == ITEM
            and report["real_civil_id_status"] == "accepted"
            and not report["required_canary"]
        )
        print("VERIFY", "PASS" if ok else "FAIL")
        return 0 if ok else 1

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            if cmd == "create":
                result = create(cur)
            elif cmd == "reset":
                result = reset(cur)
            else:
                result = cleanup(cur)
        conn.commit()
    print(json.dumps(result, indent=2, default=str))

    if cmd in {"create", "reset"}:
        report = verify_projection()
        print(json.dumps({"verify": report}, indent=2, default=str))
        ok = (
            report["canary_present"]
            and report["visible_in_employee_app"]
            and report["upload_enabled"]
            and report["real_civil_id_status"] == "accepted"
        )
        print("READY_FOR_APP_TEST" if ok else "NOT_READY", ITEM)
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
