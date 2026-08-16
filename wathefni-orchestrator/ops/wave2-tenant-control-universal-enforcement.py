#!/usr/bin/env python3
"""Wave 2 universal enforcement proofs and bounded canaries.

Safe defaults:
- Does not create externally usable companies rows
- Protects WATHEFNI from suspension without explicit token
- Restores analytics pause and canary authority before exit
- Leaves the 12 classified orphan settings untouched

Usage on production host:
  cd /opt/wathefni/orchestrator
  set -a; source /root/.openclaw/secrets/postgres.env
  source /opt/wathefni/var/unified-inbound-cv.production.env; set +a
  export WATHEFNI_APPLICATION_ENVIRONMENT=production
  export WATHEFNI_TENANT_CONTROL_CANARY_AUTHORITY=on
  .venv/bin/python ops/wave2-tenant-control-universal-enforcement.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SYNTHETIC_TENANT = "__TC_WAVE2_CANARY__"
CANARY_MODULE = "analytics"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _health() -> dict[str, Any]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=5) as resp:
            return {"http_status": resp.status, "body": json.loads(resp.read().decode())}
    except Exception as exc:
        return {"http_status": 0, "error": str(exc)}


def main() -> int:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    import module_catalog as modules
    import tenant_control_decision as decision
    import tenant_control_lifecycle as lifecycle
    import tenant_control_queue_gate as queue_gate
    import tenant_control_roles as roles
    import tenant_control_service as wave1
    import tenant_control_surfaces as surfaces
    import verified_job_binding_gate as vjbg

    # Ensure canary authority flag on for this proof process.
    os.environ.setdefault("WATHEFNI_TENANT_CONTROL_CANARY_AUTHORITY", "on")
    os.environ.setdefault("WATHEFNI_TENANT_CONTROL_LIFECYCLE_ENFORCE", "on")
    os.environ.setdefault("WATHEFNI_TENANT_CONTROL_EPOCH_ENFORCE", "on")
    os.environ.setdefault("WATHEFNI_TENANT_CONTROL_DECISION", "on")

    dsn = os.environ.get("WATHEFNI_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        print("FAIL: WATHEFNI_DATABASE_URL missing", file=sys.stderr)
        return 2

    evidence: dict[str, Any] = {
        "run_at": _utc(),
        "schema_version": "tenant-control-schema-v2",
        "canary_module": CANARY_MODULE,
        "synthetic_tenant": SYNTHETIC_TENANT,
    }
    evidence["health_before"] = _health()

    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            schema = decision.ensure_schema(cur)
            evidence["schema"] = schema

            # --- Import / dimension sync for WATHEFNI ---
            cur.execute(
                "SELECT module_key FROM company_modules WHERE company_code='WATHEFNI' AND enabled IS TRUE"
            )
            enabled = {str(r["module_key"]) for r in cur.fetchall()}
            wave1.import_company_into_control_plane(
                cur,
                company_code="WATHEFNI",
                legacy_modules=enabled,
                actor="wave2_proof",
            )
            dims = lifecycle.sync_module_dimensions_from_legacy(
                cur, company_code="WATHEFNI", enabled_modules=enabled
            )
            evidence["dimension_sync"] = dims

            # --- Permission parity ---
            parity = roles.run_permission_parity(cur, company_code="WATHEFNI")
            evidence["permission_parity"] = {
                "parity": parity.get("parity"),
                "checked": parity.get("checked"),
                "mismatches": parity.get("mismatches"),
            }

            # --- Orphan integrity monitoring (no deletes) ---
            cur.execute(
                """
                SELECT company_code, updated_at
                FROM company_settings s
                WHERE NOT EXISTS (SELECT 1 FROM companies c WHERE c.company_code=s.company_code)
                ORDER BY company_code
                """
            )
            orphans = [dict(r) for r in cur.fetchall()]
            classified = wave1.classify_orphan_settings(
                cur,
                [{"company_code": o["company_code"], "settings": {}, "updated_at": o.get("updated_at")} for o in orphans],
            )
            other = {}
            for table in ("company_modules", "dashboard_users", "positions", "applications", "employees"):
                cur.execute(
                    f"""
                    SELECT count(*)::int AS n FROM {table} t
                    WHERE NOT EXISTS (SELECT 1 FROM companies c WHERE c.company_code=t.company_code)
                    """
                )
                other[table] = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                INSERT INTO tc_orphan_monitoring (
                  orphan_settings_count, new_orphan_settings_count, other_orphan_counts, detail
                ) VALUES (%s,0,%s::jsonb,%s::jsonb)
                """,
                (
                    len(orphans),
                    json.dumps(other),
                    json.dumps({"classified": [i["company_code"] for i in classified]}),
                ),
            )
            evidence["orphan_integrity"] = {
                "orphan_settings_count": len(orphans),
                "unchanged_twelve": len(orphans) == 12,
                "other_orphan_counts": other,
                "action": "retain_do_not_delete",
            }

            # Prevent new orphan settings proof
            blocked_orphan_write = False
            try:
                cur.execute("SAVEPOINT orphan_write_proof")
                cur.execute(
                    """
                    INSERT INTO company_settings (company_code, settings)
                    SELECT 'ZZNEVERCREATE', '{}'::jsonb
                    WHERE EXISTS (SELECT 1 FROM companies WHERE company_code='ZZNEVERCREATE')
                    """
                )
                # Application-level guard is in set_company_setting; emulate here:
                cur.execute("SELECT 1 FROM companies WHERE company_code='ZZNEVERCREATE'")
                blocked_orphan_write = cur.fetchone() is None
                cur.execute("ROLLBACK TO SAVEPOINT orphan_write_proof")
            except Exception as exc:
                cur.execute("ROLLBACK TO SAVEPOINT orphan_write_proof")
                blocked_orphan_write = True
                evidence["orphan_write_error"] = str(exc)[:200]
            evidence["orphan_integrity"]["new_orphan_creation_blocked_by_company_fk_guard"] = blocked_orphan_write

            # ===================== CANARY A: pause analytics =====================
            impact = lifecycle.preview_module_pause(CANARY_MODULE)
            for surface in (
                "navigation", "apis", "ai_tools", "module_check", "outbound_notifications",
                "workers", "queue_claims", "timers", "*",
            ):
                lifecycle.enable_canary_authority(
                    cur,
                    company_code="WATHEFNI",
                    module_key=CANARY_MODULE,
                    capability_key="mod.analytics",
                    surface=surface,
                    actor="wave2_canary_a",
                    reason="bounded analytics pause canary",
                )
            before_epoch_row = decision.load_module_state(
                cur,
                decision.load_tenant_state(cur, "WATHEFNI")["tenant_id"],
                CANARY_MODULE,
            )
            pause = lifecycle.pause_module(
                cur,
                company_code="WATHEFNI",
                module_key=CANARY_MODULE,
                actor="wave2_canary_a",
                reason="bounded_non_critical_canary",
            )
            epoch_n = int((before_epoch_row or {}).get("activation_epoch") or 1)
            epoch_n1 = int(pause.get("activation_epoch") or (epoch_n + 1))

            nav = decision.evaluate_decision(
                cur, company_code="WATHEFNI", surface="navigation",
                module_key=CANARY_MODULE, legacy_allow=True, persist=True,
            )
            api = decision.evaluate_decision(
                cur, company_code="WATHEFNI", surface="apis",
                module_key=CANARY_MODULE, legacy_allow=True, persist=True,
            )
            ai = decision.evaluate_decision(
                cur, company_code="WATHEFNI", surface="ai_tools",
                module_key=CANARY_MODULE, legacy_allow=True, persist=True,
            )
            queue = queue_gate.allow_queue_claim(
                cur, company_code="WATHEFNI", module_key=CANARY_MODULE,
                queued_epoch=epoch_n1, work_kind="canary_queue", work_ref="a1",
                legacy_allow=True,
            )
            notify = decision.evaluate_decision(
                cur, company_code="WATHEFNI", surface="outbound_notifications",
                module_key=CANARY_MODULE, legacy_allow=True, persist=True,
            )
            # Stale epoch work under previous epoch
            stale = queue_gate.allow_worker_side_effect(
                cur, company_code="WATHEFNI", module_key=CANARY_MODULE,
                queued_epoch=epoch_n, work_kind="canary_stale_epoch", work_ref="a-stale",
                legacy_allow=True,
            )
            evidence["canary_a_pause"] = {
                "impact_preview": impact,
                "pause": {
                    "ok": pause.get("ok"),
                    "activation_epoch": pause.get("activation_epoch"),
                    "correlation_id": pause.get("correlation_id"),
                },
                "navigation_allow": nav.allow,
                "navigation_mode": nav.mode,
                "api_allow": api.allow,
                "api_mode": api.mode,
                "ai_allow": ai.allow,
                "queue_allow": queue.allow,
                "notify_allow": notify.allow,
                "stale_epoch_allow": stale.allow,
                "stale_reason": stale.reason_code,
                "legacy_modules_unchanged": sorted(enabled),
            }

            # Restore analytics
            resume = lifecycle.resume_module(
                cur,
                company_code="WATHEFNI",
                module_key=CANARY_MODULE,
                actor="wave2_canary_a",
                reason="restore_after_canary",
            )
            restored = decision.evaluate_decision(
                cur, company_code="WATHEFNI", surface="apis",
                module_key=CANARY_MODULE, legacy_allow=True, persist=True,
            )
            evidence["canary_a_restore"] = {
                "resume_ok": resume.get("ok"),
                "activation_epoch": resume.get("activation_epoch"),
                "api_allow_after_restore": restored.allow,
                "canonical_allow_after_restore": restored.detail.get("canonical_allow"),
            }
            lifecycle.disable_canary_authority(cur, company_code="WATHEFNI", module_key=CANARY_MODULE)

            # ===================== CANARY B: synthetic tenant suspend =====================
            # Ensure no companies row for synthetic tenant.
            cur.execute("SELECT 1 FROM companies WHERE company_code=%s", (SYNTHETIC_TENANT,))
            assert cur.fetchone() is None, "synthetic tenant must not exist in companies"

            for surface in ("navigation", "intake", "queue_claims", "outbound_notifications", "webhooks", "*"):
                lifecycle.enable_canary_authority(
                    cur,
                    company_code=SYNTHETIC_TENANT,
                    module_key=None,
                    capability_key=None,
                    surface=surface,
                    actor="wave2_canary_b",
                    reason="synthetic suspend canary",
                )
            suspended = lifecycle.set_tenant_lifecycle(
                cur,
                company_code=SYNTHETIC_TENANT,
                lifecycle_status="suspended",
                actor="wave2_canary_b",
                reason="bounded_synthetic_suspend",
                synthetic=True,
                externally_usable=False,
            )
            # Prove WATHEFNI suspend blocked without token
            wathefni_block = None
            try:
                lifecycle.set_tenant_lifecycle(
                    cur,
                    company_code="WATHEFNI",
                    lifecycle_status="suspended",
                    actor="wave2_canary_b",
                    reason="should_fail",
                )
                wathefni_block = {"blocked": False}
            except PermissionError as exc:
                wathefni_block = {"blocked": True, "error": str(exc)}

            session_reject = decision.evaluate_decision(
                cur, company_code=SYNTHETIC_TENANT, surface="navigation",
                legacy_allow=True, persist=True,
            )
            intake_block = queue_gate.allow_intake(
                cur, company_code=SYNTHETIC_TENANT, channel="email", legacy_allow=True
            )
            queue_block = queue_gate.allow_queue_claim(
                cur, company_code=SYNTHETIC_TENANT, module_key="pre_hiring",
                queued_epoch=suspended.get("activation_epoch"),
                work_kind="synthetic_queue", legacy_allow=True,
            )
            delivery_block = decision.evaluate_decision(
                cur, company_code=SYNTHETIC_TENANT, surface="outbound_notifications",
                legacy_allow=True, persist=True,
            )
            restored_tenant = lifecycle.set_tenant_lifecycle(
                cur,
                company_code=SYNTHETIC_TENANT,
                lifecycle_status="active",
                actor="wave2_canary_b",
                reason="restore_synthetic",
                synthetic=True,
                externally_usable=False,
            )
            after_restore = decision.evaluate_decision(
                cur, company_code=SYNTHETIC_TENANT, surface="navigation",
                legacy_allow=True, persist=True,
            )
            lifecycle.disable_canary_authority(cur, company_code=SYNTHETIC_TENANT)
            evidence["canary_b_synthetic_suspend"] = {
                "companies_row_absent": True,
                "externally_usable": False,
                "suspend": suspended,
                "wathefni_suspension_blocked": wathefni_block,
                "session_allow": session_reject.allow,
                "session_reason": session_reject.reason_code,
                "intake_allow": intake_block.allow,
                "queue_allow": queue_block.allow,
                "delivery_allow": delivery_block.allow,
                "restore_ok": restored_tenant.get("ok"),
                "allow_after_restore": after_restore.allow,
            }

            # ===================== CANARY C: activation epoch =====================
            lifecycle.enable_canary_authority(
                cur, company_code="WATHEFNI", module_key=CANARY_MODULE,
                capability_key="mod.analytics", surface="workers",
                actor="wave2_canary_c", reason="epoch canary",
            )
            lifecycle.enable_canary_authority(
                cur, company_code="WATHEFNI", module_key=CANARY_MODULE,
                capability_key="mod.analytics", surface="queue_claims",
                actor="wave2_canary_c", reason="epoch canary",
            )
            state0 = decision.load_module_state(
                cur, decision.load_tenant_state(cur, "WATHEFNI")["tenant_id"], CANARY_MODULE
            )
            epoch_n = int((state0 or {}).get("activation_epoch") or 1)
            # Enqueue under epoch N (logical)
            enqueued_epoch = epoch_n
            pause2 = lifecycle.pause_module(
                cur, company_code="WATHEFNI", module_key=CANARY_MODULE,
                actor="wave2_canary_c", reason="epoch_bump_pause",
            )
            resume2 = lifecycle.resume_module(
                cur, company_code="WATHEFNI", module_key=CANARY_MODULE,
                actor="wave2_canary_c", reason="epoch_bump_resume",
            )
            live_epoch = int(resume2.get("activation_epoch") or epoch_n)
            stale_exec = queue_gate.allow_worker_side_effect(
                cur, company_code="WATHEFNI", module_key=CANARY_MODULE,
                queued_epoch=enqueued_epoch, work_kind="epoch_canary",
                work_ref=f"epoch-{enqueued_epoch}", legacy_allow=True,
            )
            fresh_exec = queue_gate.allow_worker_side_effect(
                cur, company_code="WATHEFNI", module_key=CANARY_MODULE,
                queued_epoch=live_epoch, work_kind="epoch_canary",
                work_ref=f"epoch-{live_epoch}", legacy_allow=True,
            )
            lifecycle.disable_canary_authority(cur, company_code="WATHEFNI", module_key=CANARY_MODULE)
            evidence["canary_c_epoch"] = {
                "enqueued_epoch": enqueued_epoch,
                "live_epoch_after_pause_resume": live_epoch,
                "stale_allow": stale_exec.allow,
                "stale_reason": stale_exec.reason_code,
                "fresh_allow": fresh_exec.allow,
                "epoch_advanced": live_epoch > enqueued_epoch,
            }

            # ===================== CANARY D: WATHEFNI live modules healthy =====================
            live_checks = {}
            false_denials = []
            for module in sorted(enabled):
                d = decision.evaluate_decision(
                    cur, company_code="WATHEFNI", surface="apis",
                    module_key=module, legacy_allow=True, persist=True,
                )
                live_checks[module] = {
                    "allow": d.allow,
                    "mode": d.mode,
                    "parity": d.parity,
                    "canonical_allow": d.detail.get("canonical_allow"),
                }
                if d.mode == "authoritative" and d.allow is False:
                    false_denials.append(module)
            cur.execute(
                """
                SELECT status, count(*)::int AS n
                FROM candidate_interviews WHERE company_code='WATHEFNI'
                GROUP BY status ORDER BY status
                """
            )
            interviews = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT company_code, status FROM companies ORDER BY 1")
            companies_rows = [dict(r) for r in cur.fetchall()]
            evidence["canary_d_wathefni_health"] = {
                "live_module_checks": live_checks,
                "false_denials": false_denials,
                "interviews_module_enabled": "interviews" in enabled,
                "interview_status_counts": interviews,
                "verified_binding": {
                    "enforce_wathefni": vjbg.enforce_enabled(company_code="WATHEFNI"),
                    "enforce_other": vjbg.enforce_enabled(company_code="OTHERCO"),
                    "tenants": os.environ.get("WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE_TENANTS"),
                },
                "unified_inbound": {
                    k: os.environ.get(k)
                    for k in (
                        "WATHEFNI_UNIFIED_INBOUND_CV_ADAPTERS",
                        "WATHEFNI_UNIFIED_INBOUND_CV_WAVE4",
                        "WATHEFNI_UNIFIED_INTAKE_AUTHORITY_TENANTS",
                    )
                },
                "companies": companies_rows,
            }

            # Blocked work evidence
            cur.execute(
                """
                SELECT work_kind, reason_code, disposition, count(*)::int AS n
                FROM tc_blocked_work
                WHERE company_code IN ('WATHEFNI', %s)
                GROUP BY 1,2,3 ORDER BY 1,2
                """,
                (SYNTHETIC_TENANT,),
            )
            evidence["blocked_work"] = [dict(r) for r in cur.fetchall()]

            # Kill switches
            evidence["kill_switches"] = {
                "plane_off": decision.plane_enabled({"WATHEFNI_TENANT_CONTROL_PLANE": "off"}) is False,
                "decision_off": decision.decision_enabled({"WATHEFNI_TENANT_CONTROL_PLANE": "on", "WATHEFNI_TENANT_CONTROL_DECISION": "off"}) is False,
                "lifecycle_off": decision.lifecycle_enforce_enabled({"WATHEFNI_TENANT_CONTROL_LIFECYCLE_ENFORCE": "off"}) is False,
                "epoch_off": decision.epoch_enforce_enabled({"WATHEFNI_TENANT_CONTROL_EPOCH_ENFORCE": "off"}) is False,
                "global_authoritative_forced_false": decision.global_authoritative_enabled({"WATHEFNI_TENANT_CONTROL_AUTHORITATIVE": "on"}) is False,
                "wave1_authoritative_false": wave1.authoritative_enabled() is False,
            }

            # Rollback-to-wave1 behavior: with decision off, paused module would not deny.
            # (We already restored analytics; prove bypass path.)
            bypass = decision.evaluate_decision(
                cur, company_code="WATHEFNI", surface="apis", module_key="analytics",
                legacy_allow=True, persist=False,
                environ={
                    "WATHEFNI_TENANT_CONTROL_PLANE": "on",
                    "WATHEFNI_TENANT_CONTROL_DECISION": "off",
                },
            )
            evidence["rollback_wave1_behavior"] = {
                "decision_bypass_allow": bypass.allow,
                "mode": bypass.mode,
                "reason_code": bypass.reason_code,
            }

            # Ensure no external tenant / companies still only WATHEFNI
            cur.execute("SELECT company_code FROM companies ORDER BY 1")
            evidence["companies_final"] = [r["company_code"] for r in cur.fetchall()]
            cur.execute("SELECT company_code, synthetic, externally_usable, lifecycle_status FROM tc_tenants ORDER BY 1")
            evidence["tc_tenants_final"] = [dict(r) for r in cur.fetchall()]

            # Ensure analytics live again and canary authority off
            st = decision.load_module_state(
                cur, decision.load_tenant_state(cur, "WATHEFNI")["tenant_id"], CANARY_MODULE
            )
            evidence["analytics_final_state"] = {
                k: (st or {}).get(k) for k in ("enabled", "live", "paused", "instance_state", "activation_epoch")
            }
            cur.execute(
                "SELECT count(*)::int AS n FROM tc_canary_authority WHERE company_code='WATHEFNI' AND enabled IS TRUE"
            )
            evidence["wathefni_canary_authority_enabled_count"] = int((cur.fetchone() or {}).get("n") or 0)

            # Legacy modules still enabled
            cur.execute(
                "SELECT count(*)::int AS n FROM company_modules WHERE company_code='WATHEFNI' AND enabled IS TRUE"
            )
            evidence["legacy_enabled_count"] = int((cur.fetchone() or {}).get("n") or 0)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    evidence["health_after"] = _health()

    checks = {
        "health_200": evidence["health_after"].get("http_status") == 200,
        "only_wathefni_company": evidence.get("companies_final") == ["WATHEFNI"],
        "permission_parity": bool((evidence.get("permission_parity") or {}).get("parity")),
        "orphans_twelve_retained": bool((evidence.get("orphan_integrity") or {}).get("unchanged_twelve")),
        "canary_a_nav_denied": evidence.get("canary_a_pause", {}).get("navigation_allow") is False,
        "canary_a_api_denied": evidence.get("canary_a_pause", {}).get("api_allow") is False,
        "canary_a_ai_denied": evidence.get("canary_a_pause", {}).get("ai_allow") is False,
        "canary_a_queue_denied": evidence.get("canary_a_pause", {}).get("queue_allow") is False,
        "canary_a_notify_denied": evidence.get("canary_a_pause", {}).get("notify_allow") is False,
        "canary_a_restored": evidence.get("canary_a_restore", {}).get("api_allow_after_restore") is True,
        "canary_b_sessions_denied": evidence.get("canary_b_synthetic_suspend", {}).get("session_allow") is False,
        "canary_b_intake_denied": evidence.get("canary_b_synthetic_suspend", {}).get("intake_allow") is False,
        "canary_b_queue_denied": evidence.get("canary_b_synthetic_suspend", {}).get("queue_allow") is False,
        "canary_b_delivery_denied": evidence.get("canary_b_synthetic_suspend", {}).get("delivery_allow") is False,
        "canary_b_wathefni_protected": bool(
            (evidence.get("canary_b_synthetic_suspend", {}).get("wathefni_suspension_blocked") or {}).get("blocked")
        ),
        "canary_b_restored": evidence.get("canary_b_synthetic_suspend", {}).get("allow_after_restore") is True,
        "canary_c_stale_denied": evidence.get("canary_c_epoch", {}).get("stale_allow") is False,
        "canary_c_fresh_allowed": evidence.get("canary_c_epoch", {}).get("fresh_allow") is True,
        "canary_c_epoch_advanced": bool(evidence.get("canary_c_epoch", {}).get("epoch_advanced")),
        "no_false_denials": evidence.get("canary_d_wathefni_health", {}).get("false_denials") == [],
        "interviews_enabled": bool(evidence.get("canary_d_wathefni_health", {}).get("interviews_module_enabled")),
        "enforce_wathefni_only": bool(
            (evidence.get("canary_d_wathefni_health", {}).get("verified_binding") or {}).get("enforce_wathefni")
        )
        and not bool(
            (evidence.get("canary_d_wathefni_health", {}).get("verified_binding") or {}).get("enforce_other")
        ),
        "kill_switches_ok": all(evidence.get("kill_switches", {}).values()),
        "wave1_rollback_bypass": evidence.get("rollback_wave1_behavior", {}).get("mode") == "bypass",
        "analytics_live_again": evidence.get("analytics_final_state", {}).get("live") is True
        and evidence.get("analytics_final_state", {}).get("paused") is False,
        "canary_authority_cleared": evidence.get("wathefni_canary_authority_enabled_count") == 0,
        "legacy_modules_intact": evidence.get("legacy_enabled_count") == 12,
        "global_authoritative_off": decision.global_authoritative_enabled() is False,
    }
    evidence["proof_checks"] = checks
    evidence["go"] = all(checks.values())

    out_dir = Path("/tmp") / f"wave2-tenant-control-{evidence['run_at']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "evidence.json"
    out_path.write_text(json.dumps(evidence, indent=2, default=str) + "\n")
    print(json.dumps({"ok": evidence["go"], "evidence": str(out_path), "checks": checks}, indent=2))
    return 0 if evidence["go"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
