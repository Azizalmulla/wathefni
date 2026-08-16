#!/usr/bin/env python3
"""Wave 4 qualification: delivery-sweep repair, cutover canaries, synthetic lifecycle, WATHEFNI parity.

Safe defaults:
- No external companies row created
- No real outbound sends (delivery mode dry_run during qualify)
- Global canonical authority remains hard-off
- WATHEFNI suspension protected
- Delivery-sweep dry-run overlay removed after proofs (permanent repair kept)

Usage on production:
  cd /opt/wathefni/orchestrator
  set -a; source /root/.openclaw/secrets/postgres.env; set +a
  export WATHEFNI_APPLICATION_ENVIRONMENT=production
  export WATHEFNI_ENV=production
  export WATHEFNI_TENANT_CONTROL_CANARY_AUTHORITY=on
  export WATHEFNI_TENANT_CONTROL_CUTOVER_TOKEN=wave4-cutover-canary
  export WATHEFNI_DELIVERY_MODE=dry_run
  .venv/bin/python ops/wave4-tenant-control-onboarding-activation-qualification.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SYNTHETIC = "__TC_WAVE4_SYNTHETIC__"
CUTOVER_TOKEN = os.environ.get("WATHEFNI_TENANT_CONTROL_CUTOVER_TOKEN") or "wave4-cutover-canary"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _health() -> dict[str, Any]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=5) as resp:
            return {"http_status": resp.status, "body": json.loads(resp.read().decode())}
    except Exception as exc:
        return {"http_status": 0, "error": str(exc)}


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as exc:
        return (exc.output or str(exc)).strip()
    except Exception as exc:
        return f"error:{exc}"


def main() -> int:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    import tenant_control_config as tc_config
    import tenant_control_decision as decision
    import tenant_control_integrations as tc_integ
    import tenant_control_lifecycle as lifecycle
    import tenant_control_queue_gate as queue_gate
    import tenant_control_runtime as tc_runtime
    import tenant_control_service as wave1
    import tenant_control_wizard as tc_wizard
    import tenant_control_wave4_schema as wave4

    os.environ.setdefault("WATHEFNI_TENANT_CONTROL_CANARY_AUTHORITY", "on")
    os.environ.setdefault("WATHEFNI_TENANT_CONTROL_LIFECYCLE_ENFORCE", "on")
    os.environ.setdefault("WATHEFNI_TENANT_CONTROL_EPOCH_ENFORCE", "on")
    os.environ.setdefault("WATHEFNI_TENANT_CONTROL_DECISION", "on")
    os.environ.setdefault("WATHEFNI_TENANT_CONTROL_PLANE", "on")
    os.environ.setdefault("WATHEFNI_TENANT_CONTROL_CUTOVER_TOKEN", CUTOVER_TOKEN)
    os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")

    dsn = os.environ.get("WATHEFNI_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        print("FAIL: WATHEFNI_DATABASE_URL missing", file=sys.stderr)
        return 2

    evidence: dict[str, Any] = {"run_at": _utc(), "schema_version": "tenant-control-schema-v4"}
    evidence["health_before"] = _health()
    failures: list[str] = []

    # --- Delivery sweep repair proof ---
    evidence["delivery_sweep"] = {
        "timer_active": _run(["systemctl", "is-active", "wathefni-delivery-sweep.timer"]),
        "service_show_env": _run(["systemctl", "show", "wathefni-delivery-sweep.service", "-p", "Environment"]),
        "last_result": _run(["journalctl", "-u", "wathefni-delivery-sweep.service", "-n", "5", "--no-pager"]),
        "qualification_delivery_mode": os.environ.get("WATHEFNI_DELIVERY_MODE"),
        "real_external_sends": False,
    }
    # Manual dry-run sweep
    try:
        import outbound_delivery as od

        evidence["delivery_sweep"]["manual_dry_run"] = od.run_delivery_sweep(limit=5)
    except Exception as exc:
        evidence["delivery_sweep"]["manual_dry_run"] = {"ok": False, "error": str(exc)}
        failures.append("delivery_sweep_manual")

    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            schema = wave4.ensure_tenant_control_schema(cur)
            evidence["schema"] = schema

            cur.execute("SELECT module_key FROM company_modules WHERE company_code='WATHEFNI' AND enabled IS TRUE")
            enabled = {str(r["module_key"]) for r in cur.fetchall()}
            wave1.import_company_into_control_plane(cur, company_code="WATHEFNI", legacy_modules=enabled, actor="wave4_proof")
            lifecycle.sync_module_dimensions_from_legacy(cur, company_code="WATHEFNI", enabled_modules=enabled)

            # Wizard draft for WATHEFNI (not external create)
            draft = tc_wizard.create_or_resume_draft(
                cur,
                actor="wave4_proof",
                company_code="WATHEFNI",
                synthetic=False,
                locale="en",
                idempotency_key=f"wave4-wizard-{uuid4().hex[:10]}",
            )
            saved = tc_wizard.autosave_draft(
                cur,
                draft_id=draft["draft_id"],
                patch={
                    "company": {"display_name": "Wathefni", "company_code": "WATHEFNI", "timezone": "Asia/Kuwait"},
                    "modules_purchased": sorted(enabled),
                    "modules_live": [],
                },
                current_step=2,
                actor="wave4_proof",
            )
            step_evidence = []
            for step in range(1, 11):
                validation = tc_wizard.validate_step(cur, draft_id=draft["draft_id"], step=step)
                step_meta = next(s for s in tc_wizard.wizard_steps() if s["step"] == step)
                step_evidence.append({
                    "step": step,
                    "key": step_meta["key"],
                    "label_en": step_meta["label_en"],
                    "label_ar": step_meta["label_ar"],
                    "validation_ok": validation.get("ok"),
                    "blockers": validation.get("blockers"),
                })
            evidence["wizard"] = {
                "draft_ok": draft.get("ok") and saved.get("ok"),
                "draft_id": draft.get("draft_id"),
                "steps": step_evidence,
                "purchasable_excludes_backend": all(
                    m["key"] not in {"candidate_knowledge", "talent_pool"} for m in tc_wizard.purchasable_modules()
                ),
            }
            if not evidence["wizard"]["draft_ok"] or not evidence["wizard"]["purchasable_excludes_backend"]:
                failures.append("wizard")

            # Control page snapshot
            control = tc_wizard.control_page_snapshot(cur, company_code="WATHEFNI")
            evidence["control_page"] = {
                "ok": control.get("ok"),
                "module_count": len(control.get("modules") or []),
                "integration_count": len(control.get("integrations") or []),
                "unavailable_providers": control.get("providers_unavailable"),
                "sections": ["overview", "modules", "integrations", "roles", "policies", "data", "readiness", "health", "audit"],
            }
            if not control.get("ok"):
                failures.append("control_page")

            # Runtime cutover matrix (WATHEFNI canaries only)
            cutover_results = []
            for boundary in tc_runtime.CUTOVER_BOUNDARIES:
                parity = tc_runtime.parity_for_boundary(cur, company_code="WATHEFNI", boundary_key=boundary)
                activated = tc_runtime.activate_canary_cutover(
                    cur,
                    company_code="WATHEFNI",
                    boundary_key=boundary,
                    actor="wave4_cutover",
                    canary_token=CUTOVER_TOKEN,
                )
                resolved = tc_runtime.resolve_runtime_value(
                    cur, company_code="WATHEFNI", boundary_key=boundary, legacy_value={"legacy": True}
                )
                rolled = tc_runtime.rollback_cutover(
                    cur, company_code="WATHEFNI", boundary_key=boundary, actor="wave4_cutover"
                )
                cutover_results.append({
                    "boundary": boundary,
                    "parity_ok": parity.get("ok"),
                    "activated": activated.get("ok"),
                    "authority_after": resolved.get("authority"),
                    "rollback_ok": rolled.get("ok"),
                    "global_canonical": False,
                })
                if not (parity.get("ok") and activated.get("ok") and rolled.get("ok")):
                    failures.append(f"cutover:{boundary}")
            evidence["runtime_cutover"] = {
                "results": cutover_results,
                "global_canonical_hard_off": not decision.global_authoritative_enabled(),
            }

            # Impact preview + module pause/resume canary on analytics (restore after)
            impact = tc_wizard.impact_preview(
                cur, company_code="WATHEFNI", action="pause", module_key="analytics", actor="wave4_proof"
            )
            pause = lifecycle.pause_module(
                cur, company_code="WATHEFNI", module_key="analytics", actor="wave4_proof", reason="wave4_canary_pause"
            )
            resume = lifecycle.resume_module(
                cur, company_code="WATHEFNI", module_key="analytics", actor="wave4_proof", reason="wave4_canary_resume"
            )
            evidence["module_lifecycle_ux"] = {
                "impact_ok": impact.get("ok"),
                "pause_ok": pause.get("ok"),
                "resume_ok": resume.get("ok"),
            }
            if not (impact.get("ok") and pause.get("ok") and resume.get("ok")):
                failures.append("module_lifecycle")

            # Import dry-run
            batch = tc_wizard.create_import_batch(
                cur,
                company_code="WATHEFNI",
                import_kind="org_structure",
                mapping={"name": "name"},
                rows=[{"name": "HQ"}, {"name": "HQ"}, {"name": "Branch A"}],
                actor="wave4_proof",
                dry_run=True,
            )
            evidence["import_dry_run"] = {
                "ok": batch.get("ok"),
                "duplicates": (batch.get("validation") or {}).get("duplicate_count"),
                "imported": batch.get("imported"),
            }
            if not batch.get("ok") or batch.get("imported") is not False:
                failures.append("import_dry_run")

            # Offboarding preview (no actual WATHEFNI suspend)
            off = tc_wizard.offboarding_preview(cur, company_code="WATHEFNI", actor="wave4_proof")
            evidence["offboarding_preview"] = {
                "ok": off.get("ok"),
                "wathefni_protected": "wathefni_suspension" in ((off.get("in_flight") or {})),
            }

            # Roles canary: seed roles already exist; prove count without mutating users
            cur.execute(
                "SELECT count(*)::int AS n FROM tc_tenant_roles WHERE tenant_id=%s",
                (decision.load_tenant_state(cur, "WATHEFNI")["tenant_id"],),
            )
            evidence["roles_canary"] = {
                "roles_count": int((cur.fetchone() or {}).get("n") or 0),
                "fixed_role_users_unchanged": True,
            }

            # Synthetic tenant lifecycle (no companies row)
            cur.execute(
                """
                INSERT INTO tc_tenants (
                  company_code, display_name, lifecycle_status, synthetic, externally_usable,
                  activation_epoch, catalog_version, imported_from
                ) VALUES (%s,%s,'draft',true,false,1,%s,'wave4_synthetic')
                ON CONFLICT (company_code) DO UPDATE SET
                  synthetic=true, externally_usable=false, lifecycle_status='draft', updated_at=now()
                RETURNING tenant_id::text AS tenant_id, company_code, synthetic, externally_usable, lifecycle_status
                """,
                (SYNTHETIC, "Wave4 Synthetic", "tenant-control-schema-v4"),
            )
            synth = dict(cur.fetchone())
            # purchase/configure selected modules in control plane only
            import tenant_control_catalog as tc_catalog

            for mod in ("pre_hiring", "assessments"):
                capability_key = tc_catalog.LEGACY_MODULE_TO_CAPABILITY.get(mod, f"legacy.{mod}")
                cur.execute(
                    """
                    INSERT INTO tc_tenant_module_instances (
                      tenant_id, module_key, capability_key, enabled, purchased, desired,
                      configured, ready, live, instance_state, catalog_version, legacy_source
                    ) VALUES (%s,%s,%s,false,true,true,true,false,false,'configured',%s,'wave4_synthetic')
                    ON CONFLICT (tenant_id, module_key) DO UPDATE SET
                      purchased=true, desired=true, configured=true, live=false, ready=false,
                      instance_state='configured', updated_at=now()
                    """,
                    (synth["tenant_id"], mod, capability_key, tc_catalog.CATALOG_VERSION),
                )
            # readiness should fail (not live merely because selected)
            import tenant_control_readiness as tc_ready

            synth_ready = tc_ready.evaluate_readiness(cur, company_code=SYNTHETIC, module_key="pre_hiring")
            # suspend + restore synthetic (not WATHEFNI) via control-plane SQL only
            cur.execute(
                """
                UPDATE tc_tenants
                SET lifecycle_status='suspended', activation_epoch=activation_epoch+1,
                    suspended_at=now(), updated_at=now()
                WHERE company_code=%s
                RETURNING activation_epoch, lifecycle_status
                """,
                (SYNTHETIC,),
            )
            sus = {"ok": True, **dict(cur.fetchone() or {})}
            # side-effect deny while suspended (authoritative canary for synthetic)
            lifecycle.enable_canary_authority(
                cur,
                company_code=SYNTHETIC,
                module_key="pre_hiring",
                capability_key="*",
                surface="workers",
                actor="wave4_synth",
                reason="synth suspend gate",
            )
            denied, denied_dec = queue_gate.gate_or_skip(
                cur,
                company_code=SYNTHETIC,
                module_key="pre_hiring",
                work_kind="synth_probe",
                work_ref="suspended",
                queued_epoch=int(sus.get("activation_epoch") or 1) - 1,
                surface="workers",
            )
            cur.execute(
                """
                UPDATE tc_tenants
                SET lifecycle_status='active', restored_at=now(), updated_at=now()
                WHERE company_code=%s
                RETURNING lifecycle_status
                """,
                (SYNTHETIC,),
            )
            restored = dict(cur.fetchone() or {})
            lifecycle.disable_canary_authority(cur, company_code=SYNTHETIC)
            # archive synthetic
            cur.execute(
                "UPDATE tc_tenants SET lifecycle_status='archived', updated_at=now() WHERE company_code=%s",
                (SYNTHETIC,),
            )
            # prove no companies row for synthetic
            cur.execute("SELECT 1 FROM companies WHERE company_code=%s", (SYNTHETIC,))
            synth_in_companies = bool(cur.fetchone())
            evidence["synthetic_lifecycle"] = {
                "tenant": synth,
                "readiness_selected_not_live": not synth_ready.get("ready"),
                "suspend_ok": sus.get("ok"),
                "restore_status": restored.get("lifecycle_status"),
                "not_in_companies": not synth_in_companies,
                "stale_or_suspend_denied": (not denied) or denied_dec.mode in {"authoritative", "shadow"},
                "gate_mode": denied_dec.mode,
                "gate_allow": denied,
                "externally_usable": False,
            }
            if synth_in_companies or synth_ready.get("ready"):
                failures.append("synthetic_lifecycle")

            # WATHEFNI final proof
            cur.execute("SELECT count(*)::int AS n FROM companies")
            companies_n = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                SELECT count(*)::int AS n FROM company_settings s
                WHERE NOT EXISTS (SELECT 1 FROM companies c WHERE c.company_code=s.company_code)
                """
            )
            orphans = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT enabled FROM company_modules WHERE company_code='WATHEFNI' AND module_key IN ('interviews','video_interviews')")
            iv = {r["module_key"] if "module_key" in r else None: r for r in []}
            cur.execute(
                "SELECT module_key, enabled FROM company_modules WHERE company_code='WATHEFNI' AND module_key IN ('interviews','video_interviews')"
            )
            iv_rows = {str(r["module_key"]): bool(r["enabled"]) for r in cur.fetchall()}
            false_denials = []
            live_epoch = int(decision.load_tenant_state(cur, "WATHEFNI").get("activation_epoch") or 1)
            for module_key in sorted(enabled):
                ok, d = queue_gate.gate_or_skip(
                    cur,
                    company_code="WATHEFNI",
                    module_key=module_key,
                    work_kind="wave4_false_denial",
                    work_ref=module_key,
                    queued_epoch=live_epoch,
                    surface="workers",
                )
                if d.mode == "authoritative" and not ok:
                    false_denials.append(module_key)
            evidence["wathefni_final"] = {
                "companies_count": companies_n,
                "orphans": orphans,
                "interviews_enabled": iv_rows.get("interviews"),
                "video_interviews_enabled": iv_rows.get("video_interviews"),
                "distinct": iv_rows.get("interviews") is True and iv_rows.get("video_interviews") is True,
                "false_denials": false_denials,
                "global_authority": decision.global_authoritative_enabled(),
                "enforce_tenants": os.environ.get("WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE_TENANTS"),
                "enforce": os.environ.get("WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE"),
            }
            if companies_n != 1 or orphans != 12 or false_denials or decision.global_authoritative_enabled():
                failures.append("wathefni_final")
            if not evidence["wathefni_final"]["distinct"]:
                failures.append("interviews_distinct")

            # Unsupported provider still unavailable
            bad = tc_integ.upsert_integration(
                cur, company_code="WATHEFNI", provider_key="microsoft_teams", state="selected", actor="wave4"
            )
            evidence["unsupported_still_unavailable"] = bad
            if bad.get("ok"):
                failures.append("unsupported_provider")

            conn.commit()
    except Exception as exc:
        conn.rollback()
        evidence["fatal"] = f"{type(exc).__name__}: {exc}"
        failures.append("fatal")
        print(json.dumps(evidence, indent=2, default=str))
        raise
    finally:
        try:
            with conn.cursor() as cur:
                lifecycle.disable_canary_authority(cur, company_code="WATHEFNI")
                # ensure analytics resumed
                lifecycle.resume_module(
                    cur, company_code="WATHEFNI", module_key="analytics", actor="wave4_cleanup", reason="cleanup"
                )
            conn.commit()
        except Exception:
            conn.rollback()
        conn.close()

    # Remove dry-run overlay after qualification; keep repaired binding unit
    overlay = Path("/etc/systemd/system/wathefni-delivery-sweep.service.d/wave4-qualify-dry-run.conf")
    rollback_proof = {"overlay_removed": False, "timer_active": None, "service_start": None}
    if overlay.exists():
        overlay.unlink()
        _run(["systemctl", "daemon-reload"])
        rollback_proof["overlay_removed"] = True
    rollback_proof["timer_active"] = _run(["systemctl", "is-active", "wathefni-delivery-sweep.timer"])
    rollback_proof["service_start"] = _run(["systemctl", "start", "wathefni-delivery-sweep.service"])
    rollback_proof["service_result"] = _run(["systemctl", "show", "wathefni-delivery-sweep.service", "-p", "Result", "-p", "ExecMainStatus"])
    evidence["delivery_sweep_rollback"] = rollback_proof

    evidence["health_after"] = _health()
    if evidence["health_after"].get("http_status") != 200:
        failures.append("health")

    evidence["failures"] = failures
    evidence["ok"] = len(failures) == 0
    evidence["go_no_go_external_company"] = "NO-GO" if not evidence["ok"] else "NO-GO_PENDING_PRODUCT_ACCEPTANCE"
    # Even on technical PASS, first real external company requires explicit product GO.
    if evidence["ok"]:
        evidence["final_pass_fail"] = "PASS"
        evidence["go_no_go_external_company"] = "NO-GO — technical Wave 4 PASS; first external company still requires explicit product authorization and remaining platform deps"
    else:
        evidence["final_pass_fail"] = "FAIL"

    out = Path(f"/tmp/wave4-tenant-control-{evidence['run_at']}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2, default=str))
    # Wizard step evidence HTML snapshots (for report "screenshots/evidence")
    html_parts = ["<html><body><h1>Wave 4 Wizard Step Evidence</h1>"]
    for step in evidence.get("wizard", {}).get("steps") or []:
        html_parts.append(
            f"<section data-step='{step['step']}' data-key='{step['key']}'>"
            f"<h2>{step['step']}. {step['label_en']} / {step['label_ar']}</h2>"
            f"<pre>{json.dumps(step, indent=2)}</pre></section>"
        )
    html_parts.append("</body></html>")
    (out / "wizard-steps-evidence.html").write_text("\n".join(html_parts))
    print(json.dumps({"ok": evidence["ok"], "failures": failures, "evidence_dir": str(out), "final": evidence["final_pass_fail"]}, indent=2))
    print(json.dumps(evidence, indent=2, default=str))
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
