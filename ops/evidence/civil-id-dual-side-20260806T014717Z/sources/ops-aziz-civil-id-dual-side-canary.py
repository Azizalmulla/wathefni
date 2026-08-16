#!/usr/bin/env python3
"""Disposable Civil ID dual-side canary checklist item.

Safety:
  - Touches ONLY item_id=civil_id_dual_side_canary for WATHEFNI-96599338566
  - Never mutates real civil_id / accepted docs / required progress
  - document_type stays civil_id_dual_side_canary (isolated governed lane)
  - Soft DocVal validates as Civil ID via CANARY_VALIDATION_ALIASES
  - Dual-side flag must be on for Aziz to exercise the flow

Usage on production orchestrator host:
  WATHEFNI_ENV=production .venv/bin/python ops-aziz-civil-id-dual-side-canary.py create
  WATHEFNI_ENV=production .venv/bin/python ops-aziz-civil-id-dual-side-canary.py verify
  WATHEFNI_ENV=production .venv/bin/python ops-aziz-civil-id-dual-side-canary.py reset
  WATHEFNI_ENV=production .venv/bin/python ops-aziz-civil-id-dual-side-canary.py cleanup
  WATHEFNI_ENV=production .venv/bin/python ops-aziz-civil-id-dual-side-canary.py snapshot-civil-id
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

EMP = "WATHEFNI-96599338566"
COMPANY = "WATHEFNI"
ITEM = "civil_id_dual_side_canary"
LABEL = "CANARY ONLY — Civil ID front & back (disposable)"
EXPECTED_CIVIL_SHA = "fe98f7d9d481578804a3ca3e19ca96ad4b4fa6e046f46e25d4ab21d9e15f0bb7"


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


def assert_civil_id_untouched(before: dict[str, Any], after: dict[str, Any]) -> None:
    if (
        before.get("status") != after.get("status")
        or before.get("content_sha256") != after.get("content_sha256")
        or before.get("value") != after.get("value")
    ):
        raise SystemExit(f"ABORT: civil_id changed before={before} after={after}")


def create(cur) -> dict[str, Any]:
    real = snapshot_real_civil_id(cur)
    cur.execute(
        "SELECT 1 FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
        (EMP, ITEM),
    )
    if cur.fetchone():
        return {"action": "already_present", "civil_id": real["status"], "civil_id_sha": real.get("content_sha256")}

    meta = {
        "explicitly_assigned": True,
        "canary": True,
        "disposable": True,
        "purpose": "civil_id_dual_side_live_test",
        "do_not_approve_as_real": True,
        "dual_side": True,
        "created_at": _now(),
    }
    raw = {
        "seeded_by": "ops_aziz_civil_id_dual_side_canary",
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
          9998, %s, 'pending', '[]'::jsonb,
          'document', 'onboarding', '2.0.0-canary', 1,
          0, %s::jsonb, %s::jsonb, now(), now()
        )
        """,
        (EMP, ITEM, LABEL, ITEM, json.dumps(meta), json.dumps(raw)),
    )
    return {
        "action": "created",
        "civil_id_untouched": real["status"],
        "civil_id_sha": real.get("content_sha256"),
    }


def reset(cur) -> dict[str, Any]:
    real = snapshot_real_civil_id(cur)
    # Supersede open dual-side drafts for this canary lane only.
    try:
        cur.execute(
            """
            UPDATE governed_document_versions
            SET review_status='superseded', is_current=false, updated_at=now()
            WHERE company_code=%s AND employee_key=%s AND document_type=%s
              AND review_status='draft_parts'
            """,
            (COMPANY, EMP, ITEM),
        )
        superseded = int(cur.rowcount or 0)
    except Exception:
        superseded = 0
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
            json.dumps(
                {
                    "canary_reset_at": _now(),
                    "explicitly_assigned": True,
                    "canary": True,
                    "dual_side": True,
                }
            ),
            EMP,
            ITEM,
        ),
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit("ABORT: canary item missing — run create first")
    return {
        "action": "reset",
        "canary": dict(row),
        "drafts_superseded": superseded,
        "civil_id_untouched": real["status"],
        "civil_id_sha": real.get("content_sha256"),
    }


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
        "governed_document_version_parts",
        """
        DELETE FROM governed_document_version_parts
        WHERE version_id IN (
          SELECT version_id FROM governed_document_versions
          WHERE company_code=%s AND employee_key=%s AND document_type=%s
        )
        """,
        (COMPANY, EMP, ITEM),
    )
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
    assert_civil_id_untouched(real_before, real_after)
    return {"action": "cleanup", "deleted": deleted, "civil_id": real_after}


def verify_projection() -> dict[str, Any]:
    import app
    import onboarding_civil_id_dual_side as dual
    import onboarding_lifecycle_wave2a as lc

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            real = snapshot_real_civil_id(cur)
            dual.ensure_dual_side_schema(cur)
            cur.execute(
                "SELECT item_id, status, required, document_type, lifecycle_meta FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
                (EMP, ITEM),
            )
            canary = cur.fetchone()
            versions = lc.load_latest_versions_by_type(cur, company_code=COMPANY, employee_key=EMP)
            canary_ver = versions.get(ITEM)
            if canary_ver and canary_ver.get("version_id"):
                canary_ver["parts"] = dual.load_parts(cur, str(canary_ver["version_id"]))
        conn.commit()

    enabled = dual.dual_side_enabled(company_code=COMPANY, employee_key=EMP)
    return {
        "civil_id": {
            "status": real.get("status"),
            "sha": real.get("content_sha256"),
            "sha_matches_expected": real.get("content_sha256") == EXPECTED_CIVIL_SHA,
        },
        "dual_side_enabled": enabled,
        "canary_item": dict(canary) if canary else None,
        "canary_version": {
            "version_id": (canary_ver or {}).get("version_id"),
            "review_status": (canary_ver or {}).get("review_status"),
            "parts_schema": (canary_ver or {}).get("parts_schema"),
            "parts_complete": (canary_ver or {}).get("parts_complete"),
            "parts": dual.parts_projection((canary_ver or {}).get("parts") or {}),
        }
        if canary_ver
        else None,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: create|verify|reset|cleanup|snapshot-civil-id", file=sys.stderr)
        return 2
    cmd = sys.argv[1].strip().lower()
    import app

    if cmd == "verify":
        print(json.dumps(verify_projection(), indent=2, default=str))
        return 0
    if cmd == "snapshot-civil-id":
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                print(json.dumps(snapshot_real_civil_id(cur), indent=2, default=str))
            conn.commit()
        return 0

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            if cmd == "create":
                out = create(cur)
            elif cmd == "reset":
                out = reset(cur)
            elif cmd == "cleanup":
                out = cleanup(cur)
            else:
                raise SystemExit(f"unknown command: {cmd}")
        conn.commit()
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
