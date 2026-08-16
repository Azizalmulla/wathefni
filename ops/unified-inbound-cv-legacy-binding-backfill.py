#!/usr/bin/env python3
"""Narrow audited legacy Job-binding backfill for WATHEFNI (exact 11 apps).

Creates application_job_bindings with provenance.legacy_backfill=true.
Creates application_cv_bindings only when a trustworthy cv_version already exists.
Does NOT enable ENFORCE. Does NOT cut over channels.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Exact allowlist from accepted read-only audit stamp 20260727T003453Z.
ALLOWLIST: tuple[str, ...] = (
    "96597727743-WATHEFNI-FULLSTACK_DEVELOPER",
    "96599338566-WATHEFNI-FULLSTACK_DEVELOPER",
    "96597727743-WATHEFNI-MARKETING_SPECIALIST",
    "96550252254-WATHEFNI-SOCIAL_MEDIA_MANAGER",
    "96599652277-WATHEFNI-SOCIAL_MEDIA_MANAGER",
    "96597485758-WATHEFNI-HR",
    "96598900677-WATHEFNI-ACCOUNTING",
    "96598900677-WATHEFNI-FINANCE",
    "96598900677-WATHEFNI-HR",
    "96566363363-WATHEFNI-IT_MAINTENANCE",
    "96597485758-WATHEFNI-ACCOUNTING_EXCEL",
)

EXCLUDE_SMOKE: frozenset[str] = frozenset(
    {
        "96555550132-WATHEFNI-ACCOUNTING",
        "96555550133-WATHEFNI-ACCOUNTING",
        "96555550134-WATHEFNI-ACCOUNTING_EXCEL",
        "96555550135-WATHEFNI-ACCOUNTING_EXCEL",
        "96555550136-WATHEFNI-ACCOUNTING_EXCEL",
    }
)
EXCLUDE_HELD: frozenset[str] = frozenset(
    {
        "imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT",
        "imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT",
    }
)

HELD_STATUSES = frozenset({"needs_role", "import_review", "import_archived"})
SHADOW_ENV = {
    "WATHEFNI_UNIFIED_JOB_BINDING_AUTHORITY": "1",
    "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_GATE": "1",
    "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW": "1",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def classify_shadow(app: dict[str, Any], mode: str, reasons: list[str]) -> str:
    status = str(app.get("status") or "").strip().lower()
    position = str(app.get("position_code") or "").strip()
    ds = str(app.get("data_source") or "").strip().lower()
    detail = str(app.get("data_source_detail") or "").strip().lower()
    app_key = str(app.get("app_key") or "")

    if mode == "allow":
        return "allow_verified_binding"
    if status in HELD_STATUSES or not position:
        return "expected_missing_verified_binding"
    if ds == "smoke_test" or "quarantined" in detail or app_key in EXCLUDE_SMOKE:
        return "expected_missing_verified_binding"  # excluded / should remain shadow-deny
    if "verified_job_binding_missing" in reasons:
        if app_key in ALLOWLIST:
            return "bug"  # allowlisted should allow after backfill
        return "valid_legacy_application_needing_audited_backfill"
    return "unexplained"


def find_trustworthy_cv_version(cur: Any, *, app_key: str) -> str | None:
    """Only reuse an existing ready cv_versions row clearly owned by this app."""

    cur.execute(
        """
        SELECT cv_version_id::text AS cv_version_id
        FROM cv_versions
        WHERE company_code='WATHEFNI'
          AND legacy_app_key=%s
          AND COALESCE(status,'ready')='ready'
        ORDER BY created_at DESC NULLS LAST
        LIMIT 2
        """,
        (app_key,),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    if len(rows) == 1:
        return rows[0]["cv_version_id"]

    cur.execute(
        """
        SELECT cv_version_id::text AS cv_version_id
        FROM candidate_cv_text_versions
        WHERE company_code='WATHEFNI'
          AND app_key=%s
          AND cv_version_id IS NOT NULL
          AND COALESCE(is_current,false)=true
          AND COALESCE(status,'ready') IN ('ready','current','completed')
        ORDER BY created_at DESC NULLS LAST
        LIMIT 2
        """,
        (app_key,),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    if len(rows) == 1:
        return rows[0]["cv_version_id"]
    return None


def preflight_app(cur: Any, app_key: str) -> dict[str, Any]:
    if app_key in EXCLUDE_SMOKE:
        return {"ok": False, "error": "excluded_smoke_test", "app_key": app_key}
    if app_key in EXCLUDE_HELD:
        return {"ok": False, "error": "excluded_held", "app_key": app_key}
    if app_key not in ALLOWLIST:
        return {"ok": False, "error": "not_in_allowlist", "app_key": app_key}

    cur.execute(
        """
        SELECT app_key, company_code, status, position_code, apply_code, phone,
               person_id::text AS person_id, membership_id::text AS membership_id,
               data_source, data_source_detail, position_title
        FROM applications
        WHERE company_code='WATHEFNI' AND app_key=%s
        LIMIT 1
        """,
        (app_key,),
    )
    app = cur.fetchone()
    if not app:
        return {"ok": False, "error": "application_not_found", "app_key": app_key}
    app = dict(app)
    if str(app.get("company_code") or "").upper() != "WATHEFNI":
        return {"ok": False, "error": "wrong_company", "app": app}
    status = str(app.get("status") or "").strip().lower()
    if status in HELD_STATUSES:
        return {"ok": False, "error": "held_status", "app": app}
    ds = str(app.get("data_source") or "").strip().lower()
    detail = str(app.get("data_source_detail") or "").strip().lower()
    if ds == "smoke_test" or "quarantined" in detail:
        return {"ok": False, "error": "ambiguous_smoke", "app": app}
    position_code = str(app.get("position_code") or "").strip()
    if not position_code:
        return {"ok": False, "error": "missing_position", "app": app}

    cur.execute(
        """
        SELECT position_code, title, status, apply_code, job_id::text AS job_id
        FROM positions
        WHERE company_code='WATHEFNI' AND position_code=%s
        LIMIT 1
        """,
        (position_code,),
    )
    pos = cur.fetchone()
    if not pos:
        return {"ok": False, "error": "canonical_job_missing", "app": app}
    pos = dict(pos)
    app_apply = str(app.get("apply_code") or "").strip()
    pos_apply = str(pos.get("apply_code") or "").strip()
    if app_apply and pos_apply and app_apply != pos_apply:
        return {"ok": False, "error": "apply_code_conflict", "app": app, "position": pos}

    cur.execute(
        """
        SELECT binding_id::text AS binding_id, verified, position_code, provenance
        FROM application_job_bindings
        WHERE company_code='WATHEFNI' AND app_key=%s
        LIMIT 1
        """,
        (app_key,),
    )
    existing = cur.fetchone()
    if existing:
        existing = dict(existing)
        if existing.get("verified") and str(existing.get("position_code") or "") != position_code:
            return {"ok": False, "error": "conflicting_existing_binding", "existing": existing, "app": app}
        if existing.get("verified") and str(existing.get("position_code") or "") == position_code:
            return {
                "ok": True,
                "skipped": True,
                "reason": "already_verified_same_position",
                "app": app,
                "position": pos,
                "existing": existing,
            }

    cv_version_id = find_trustworthy_cv_version(cur, app_key=app_key)
    return {
        "ok": True,
        "skipped": False,
        "app": app,
        "position": pos,
        "cv_version_id": cv_version_id,
    }


def shadow_scan(cur: Any, *, require_allowlist_allow: bool = False) -> dict[str, Any]:
    import verified_job_binding_gate as vjbg
    import job_binding_authority as job_bind

    job_bind.ensure_schema(cur)
    cur.execute(
        """
        SELECT app_key, status, position_code, phone, data_source, data_source_detail
        FROM applications
        WHERE company_code='WATHEFNI'
        ORDER BY app_key
        """
    )
    apps = [dict(r) for r in (cur.fetchall() or [])]
    counts: dict[str, int] = {}
    samples: list[dict[str, Any]] = []
    by_app: dict[str, dict[str, Any]] = {}
    for app in apps:
        decision = vjbg.assert_verified_job_binding(
            cur,
            company_code="WATHEFNI",
            app_key=str(app["app_key"]),
            action="ranking",
            application=app,
            environ=SHADOW_ENV,
        )
        app_key = str(app["app_key"])
        if app_key in EXCLUDE_SMOKE | EXCLUDE_HELD:
            if decision.mode == "allow":
                cls = "bug"
            else:
                cls = "expected_missing_verified_binding"
        elif require_allowlist_allow and app_key in ALLOWLIST:
            cls = "allow_verified_binding" if decision.mode == "allow" else "bug"
        elif app_key in ALLOWLIST and decision.mode == "shadow_deny":
            cls = "valid_legacy_application_needing_audited_backfill"
        else:
            cls = classify_shadow(app, decision.mode, list(decision.reason_codes))
        counts[cls] = counts.get(cls, 0) + 1
        row = {
            "app_key": app["app_key"],
            "status": app.get("status"),
            "position_code": app.get("position_code"),
            "mode": decision.mode,
            "reason_codes": list(decision.reason_codes),
            "classification": cls,
            "bucket": (
                "allowlist"
                if app["app_key"] in ALLOWLIST
                else (
                    "smoke"
                    if app["app_key"] in EXCLUDE_SMOKE
                    else ("held" if app["app_key"] in EXCLUDE_HELD else "other")
                )
            ),
        }
        by_app[str(app["app_key"])] = row
        samples.append(row)
    return {"counts": counts, "samples": samples, "by_app": by_app}


def run_backfill(cur: Any) -> dict[str, Any]:
    import job_binding_authority as job_bind

    job_bind.ensure_schema(cur)
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for app_key in ALLOWLIST:
        check = preflight_app(cur, app_key)
        if not check.get("ok"):
            rejected.append(check)
            continue
        if check.get("skipped"):
            skipped.append(check)
            continue
        app = check["app"]
        pos = check["position"]
        cv_version_id = check.get("cv_version_id")
        consent_id = job_bind.record_consent(
            cur,
            company_code="WATHEFNI",
            consent_kind="legacy_backfill",
            actor_type="system",
            actor_id="legacy-binding-backfill",
            person_id=app.get("person_id"),
            evidence={
                "app_key": app_key,
                "position_code": pos["position_code"],
                "apply_code": pos.get("apply_code") or app.get("apply_code"),
                "audit_stamp": "20260727T003453Z",
                "classification": "safe_to_backfill_after_owner_approval",
            },
        )
        bound = job_bind.bind_application_to_job(
            cur,
            company_code="WATHEFNI",
            app_key=app_key,
            position_code=str(pos["position_code"]),
            apply_code=str(pos.get("apply_code") or app.get("apply_code") or "") or None,
            job_id=str(pos.get("job_id") or "") or None,
            human_confirmed=True,
            consent_id=consent_id,
            person_id=app.get("person_id"),
            membership_id=app.get("membership_id"),
            cv_version_id=cv_version_id,
            provenance={
                "legacy_backfill": True,
                "source": "legacy_binding_backfill",
                "audit_stamp": "20260727T003453Z",
                "classification": "safe_to_backfill_after_owner_approval",
                "backfilled_at": _now(),
                "cv_binding_created": bool(cv_version_id),
            },
            environ={"WATHEFNI_UNIFIED_JOB_BINDING_AUTHORITY": "1"},
        )
        if not bound.get("ok"):
            rejected.append({"app_key": app_key, "error": "bind_failed", "result": bound})
            continue
        created.append(
            {
                "app_key": app_key,
                "consent_id": consent_id,
                "position_code": pos["position_code"],
                "job_id": pos.get("job_id"),
                "cv_version_id": cv_version_id,
                "cv_binding_created": bool(cv_version_id),
                "binding": bound,
            }
        )
    return {
        "created": created,
        "skipped": skipped,
        "rejected": rejected,
        "allowlist_size": len(ALLOWLIST),
    }


def delete_legacy_backfill(cur: Any, app_keys: list[str]) -> dict[str, Any]:
    """Rollback helper: remove only legacy_backfill bindings for listed apps."""

    cur.execute(
        """
        DELETE FROM application_cv_bindings
        WHERE company_code='WATHEFNI'
          AND app_key = ANY(%s)
          AND COALESCE(provenance->>'legacy_backfill','') = 'true'
        """,
        (app_keys,),
    )
    cv_deleted = cur.rowcount
    # Also delete CV bindings created in same backfill without legacy flag on older path
    cur.execute(
        """
        DELETE FROM application_cv_bindings b
        USING application_job_bindings j
        WHERE b.company_code=j.company_code AND b.app_key=j.app_key
          AND j.company_code='WATHEFNI'
          AND j.app_key = ANY(%s)
          AND COALESCE(j.provenance->>'legacy_backfill','') = 'true'
        """,
        (app_keys,),
    )
    cv_deleted2 = cur.rowcount
    cur.execute(
        """
        DELETE FROM application_job_bindings
        WHERE company_code='WATHEFNI'
          AND app_key = ANY(%s)
          AND COALESCE(provenance->>'legacy_backfill','') = 'true'
        """,
        (app_keys,),
    )
    job_deleted = cur.rowcount
    cur.execute(
        """
        DELETE FROM intake_consent_events
        WHERE company_code='WATHEFNI'
          AND consent_kind='legacy_backfill'
          AND COALESCE(evidence->>'app_key','') = ANY(%s)
        """,
        (app_keys,),
    )
    consent_deleted = cur.rowcount
    return {
        "job_bindings_deleted": int(job_deleted or 0),
        "cv_bindings_deleted": int((cv_deleted or 0) + (cv_deleted2 or 0)),
        "consents_deleted": int(consent_deleted or 0),
    }


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(
        os.environ.get(
            "LEGACY_BACKFILL_OUT",
            f"/opt/wathefni/production-evidence/unified-inbound-cv-legacy-binding-backfill/{stamp}",
        )
    )
    out.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import production_data_safety as _r3_data_safety
    _r3_data_safety.require_production_maintenance(operation='unified-inbound-cv-legacy-binding-backfill')
    from psycopg2.extras import RealDictCursor
    import psycopg2

    cfg: dict[str, str] = {}
    for line in Path(os.environ["WATHEFNI_POSTGRES_ENV"]).read_text().splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    dsn = cfg.get("WATHEFNI_DATABASE_URL") or ""
    if "wathefni_staging" in dsn:
        raise SystemExit("refusing_staging")

    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    payload: dict[str, Any] = {
        "stamp": stamp,
        "mode": mode,
        "allowlist": list(ALLOWLIST),
        "exclude_smoke": sorted(EXCLUDE_SMOKE),
        "exclude_held": sorted(EXCLUDE_HELD),
        "enforce_enabled": False,
        "channel_cutover": False,
    }
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db")
            db = (cur.fetchone() or {}).get("db")
            if db != "wathefni":
                raise SystemExit(f"refusing_db:{db}")
            payload["database"] = db

            cur.execute("SELECT count(*)::int AS n FROM applications WHERE company_code='WATHEFNI'")
            before_apps = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT count(*)::int AS n FROM candidates")
            before_cand = int((cur.fetchone() or {}).get("n") or 0)
            payload["before_counts"] = {"applications": before_apps, "candidates": before_cand}

            if mode in {"full", "shadow-only", "before"}:
                payload["shadow_before"] = shadow_scan(cur, require_allowlist_allow=False)

            if mode in {"full", "backfill", "rollback-demo"}:
                # Explicitly refuse ENFORCE in environment
                if str(os.environ.get("WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE") or "").lower() in {
                    "1",
                    "true",
                    "on",
                    "yes",
                }:
                    raise SystemExit("refusing_enforce_on")

                first = run_backfill(cur)
                payload["backfill_pass1"] = first
                if first.get("rejected"):
                    conn.rollback()
                    payload["error"] = "rejected_preflight"
                    (out / "backfill.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
                    print(json.dumps({"ok": False, "out": str(out), "rejected": first["rejected"]}, indent=2, default=str))
                    return 1
                conn.commit()

                if mode == "rollback-demo" or mode == "full":
                    # Prove rollback by deleting legacy_backfill rows, then re-apply.
                    with conn.cursor(cursor_factory=RealDictCursor) as cur2:
                        payload["rollback_delete"] = delete_legacy_backfill(cur2, list(ALLOWLIST))
                        conn.commit()
                        payload["shadow_after_rollback"] = shadow_scan(cur2, require_allowlist_allow=False)
                        second = run_backfill(cur2)
                        payload["backfill_pass2_final"] = second
                        if second.get("rejected"):
                            conn.rollback()
                            payload["error"] = "rejected_reapply"
                            (out / "backfill.json").write_text(
                                json.dumps(payload, indent=2, default=str), encoding="utf-8"
                            )
                            print(json.dumps({"ok": False, "out": str(out)}, indent=2))
                            return 1
                        conn.commit()
                        payload["shadow_after"] = shadow_scan(cur2, require_allowlist_allow=True)
                        cur2.execute(
                            "SELECT count(*)::int AS n FROM applications WHERE company_code='WATHEFNI'"
                        )
                        after_apps = int((cur2.fetchone() or {}).get("n") or 0)
                        cur2.execute("SELECT count(*)::int AS n FROM candidates")
                        after_cand = int((cur2.fetchone() or {}).get("n") or 0)
                        payload["after_counts"] = {
                            "applications": after_apps,
                            "candidates": after_cand,
                        }
                        cur2.execute(
                            """
                            SELECT app_key, position_code, verified,
                                   provenance->>'legacy_backfill' AS legacy_backfill,
                                   apply_code, job_id
                            FROM application_job_bindings
                            WHERE company_code='WATHEFNI' AND app_key = ANY(%s)
                            ORDER BY app_key
                            """,
                            (list(ALLOWLIST),),
                        )
                        payload["final_job_bindings"] = [dict(r) for r in (cur2.fetchall() or [])]
                        cur2.execute(
                            """
                            SELECT app_key, cv_version_id::text AS cv_version_id, pinned
                            FROM application_cv_bindings
                            WHERE company_code='WATHEFNI' AND app_key = ANY(%s)
                            ORDER BY app_key
                            """,
                            (list(ALLOWLIST),),
                        )
                        payload["final_cv_bindings"] = [dict(r) for r in (cur2.fetchall() or [])]

            # Assertions for full mode
            if mode == "full":
                after = payload.get("shadow_after") or {}
                counts = after.get("counts") or {}
                by_app = after.get("by_app") or {}
                allow_ok = all(
                    (by_app.get(k) or {}).get("mode") == "allow" for k in ALLOWLIST
                )
                smoke_ok = all(
                    (by_app.get(k) or {}).get("mode") == "shadow_deny" for k in EXCLUDE_SMOKE
                )
                held_ok = all(
                    (by_app.get(k) or {}).get("mode") == "shadow_deny" for k in EXCLUDE_HELD
                )
                payload["assertions"] = {
                    "allowlist_all_allow": allow_ok,
                    "smoke_all_shadow_deny": smoke_ok,
                    "held_all_shadow_deny": held_ok,
                    "bugs": int(counts.get("bug") or 0),
                    "unexplained": int(counts.get("unexplained") or 0),
                    "zero_app_mutation": payload["before_counts"]["applications"]
                    == payload["after_counts"]["applications"],
                    "zero_candidate_mutation": payload["before_counts"]["candidates"]
                    == payload["after_counts"]["candidates"],
                    "job_bindings_created": len(payload.get("final_job_bindings") or []),
                    "cv_bindings_created": len(payload.get("final_cv_bindings") or []),
                }
                ok = (
                    allow_ok
                    and smoke_ok
                    and held_ok
                    and payload["assertions"]["bugs"] == 0
                    and payload["assertions"]["unexplained"] == 0
                    and payload["assertions"]["zero_app_mutation"]
                    and payload["assertions"]["zero_candidate_mutation"]
                    and payload["assertions"]["job_bindings_created"] == 11
                )
                payload["ok"] = ok
            else:
                payload["ok"] = True

        (out / "backfill.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"ok": payload.get("ok"), "out": str(out), "assertions": payload.get("assertions")}, indent=2, default=str))
        return 0 if payload.get("ok") else 1
    except Exception as exc:
        conn.rollback()
        payload["error"] = repr(exc)
        (out / "backfill.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
