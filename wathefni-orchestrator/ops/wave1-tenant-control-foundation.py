#!/usr/bin/env python3
"""Wave 1 production foundation: schema, WATHEFNI import, shadow matrix, orphans, proofs.

Safe by default:
- additive schema only
- does not mutate companies / company_modules / company_settings
- does not enable external tenants
- dual-write dry-run validates interviews protection without writing legacy rows

Usage (on production host):
  cd /opt/wathefni/orchestrator
  set -a; source /root/.openclaw/secrets/postgres.env; set +a
  .venv/bin/python ops/wave1-tenant-control-foundation.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _health() -> dict[str, Any]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8010/health", timeout=5) as resp:
            body = resp.read().decode("utf-8")
            return {"http_status": resp.status, "body": json.loads(body)}
    except Exception as exc:
        return {"http_status": 0, "error": str(exc)}


def main() -> int:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    import module_catalog as modules
    import tenant_control_catalog as catalog
    import tenant_control_service as service
    import verified_job_binding_gate as vjbg

    dsn = os.environ.get("WATHEFNI_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        print("FAIL: WATHEFNI_DATABASE_URL not set", file=sys.stderr)
        return 2

    evidence: dict[str, Any] = {
        "run_at": _utc(),
        "catalog_version": catalog.CATALOG_VERSION,
        "schema_version": "tenant-control-schema-v1",
        "authoritative": service.authoritative_enabled(),
    }

    health = _health()
    evidence["health"] = health

    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            schema = service.ensure_schema(cur)
            evidence["schema"] = schema

            cur.execute(
                """
                SELECT company_code, status, coalesce(name, company_code) AS display_name
                FROM companies
                ORDER BY company_code
                """
            )
            companies = [dict(row) for row in cur.fetchall()]
            evidence["companies"] = companies
            evidence["external_tenants"] = [row for row in companies if row["company_code"] != "WATHEFNI"]

            cur.execute(
                """
                SELECT module_key, enabled, source, settings
                FROM company_modules
                WHERE company_code='WATHEFNI'
                ORDER BY module_key
                """
            )
            module_rows = [dict(row) for row in cur.fetchall()]
            enabled = {str(row["module_key"]) for row in module_rows if row.get("enabled")}
            evidence["legacy_modules"] = {
                "rows": [
                    {
                        "module_key": row["module_key"],
                        "enabled": bool(row["enabled"]),
                        "source": row.get("source"),
                    }
                    for row in module_rows
                ],
                "enabled": sorted(enabled),
            }

            cur.execute("SELECT settings FROM company_settings WHERE company_code='WATHEFNI'")
            settings_row = cur.fetchone()
            settings = dict((settings_row or {}).get("settings") or {})

            company_row = next((row for row in companies if row["company_code"] == "WATHEFNI"), None)
            imported = service.import_company_into_control_plane(
                cur,
                company_code="WATHEFNI",
                legacy_modules=enabled,
                company_status=(company_row or {}).get("status"),
                display_name=(company_row or {}).get("display_name"),
                module_rows=module_rows,
                settings=settings,
                actor="wave1_foundation_script",
            )
            evidence["wathefni_import"] = imported

            # Zero module loss
            canonical = service.canonical_modules_for_tenant(cur, "WATHEFNI")
            evidence["module_parity"] = {
                "legacy": sorted(enabled),
                "canonical": sorted(canonical),
                "zero_loss": enabled <= canonical and canonical <= enabled,
            }

            shadow = service.run_shadow_matrix(cur, company_code="WATHEFNI", legacy_modules=enabled)
            # Compact results for report
            evidence["shadow_matrix"] = {
                "checked": shadow["checked"],
                "mismatches": shadow["mismatches"],
                "parity": shadow["parity"],
                "legacy_modules": shadow["legacy_modules"],
                "canonical_modules": shadow["canonical_modules"],
                "mismatch_subjects": [
                    item["subject_key"] for item in shadow["results"] if not item["parity"]
                ][:50],
            }

            # Orphan settings classification (do not delete)
            cur.execute(
                """
                SELECT company_code, settings, updated_at
                FROM company_settings s
                WHERE NOT EXISTS (
                  SELECT 1 FROM companies c WHERE c.company_code = s.company_code
                )
                ORDER BY company_code
                """
            )
            orphans = [dict(row) for row in cur.fetchall()]
            classified = service.classify_orphan_settings(cur, orphans)
            evidence["orphan_settings"] = {
                "count": len(classified),
                "items": classified,
            }

            # Other orphan / cross-tenant probes (read-only)
            probes = {}
            for table, col in (
                ("company_modules", "company_code"),
                ("dashboard_users", "company_code"),
                ("positions", "company_code"),
                ("applications", "company_code"),
                ("employees", "company_code"),
                ("candidate_interviews", "company_code"),
            ):
                sp = f"probe_{table}"
                try:
                    cur.execute(f"SAVEPOINT {sp}")
                    cur.execute(
                        f"""
                        SELECT count(*)::int AS n
                        FROM {table} t
                        WHERE NOT EXISTS (
                          SELECT 1 FROM companies c WHERE c.company_code = t.{col}
                        )
                        """
                    )
                    probes[table] = int((cur.fetchone() or {}).get("n") or 0)
                    cur.execute(f"RELEASE SAVEPOINT {sp}")
                except Exception as exc:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                    probes[table] = {"error": str(exc)[:200]}
            evidence["orphan_probes"] = probes

            # Dual-write dry-run: omit interviews from requested; protection must retain it.
            # Uses a savepoint so we can roll back dual-write mutations after proof,
            # then re-import clean state.
            cur.execute("SAVEPOINT wave1_dual_write_proof")
            before_enabled = sorted(enabled)
            omit_interviews = [key for key in before_enabled if key != "interviews"]
            dual = service.dual_write_module_save(
                cur,
                company_code="WATHEFNI",
                requested_modules=omit_interviews,
                currently_enabled=before_enabled,
                actor="wave1_dual_write_proof",
                idempotency_key=f"wave1-dual-write-proof-{_utc()}",
            )
            protected_ok = "interviews" in (dual.get("modules") or [])
            rollback_target = dual.get("rollback_target")
            rollback_proof = None
            if dual.get("ok") and dual.get("version_number"):
                # Roll control-plane back to prior version number if present.
                target = dual.get("rollback_target") or max((dual.get("version_number") or 1) - 1, 1)
                rollback_proof = service.rollback_config_version(
                    cur,
                    company_code="WATHEFNI",
                    target_version=int(target),
                    actor="wave1_rollback_proof",
                )
            evidence["dual_write_proof"] = {
                "requested_without_interviews": omit_interviews,
                "result_modules": dual.get("modules"),
                "protected_retained": dual.get("protected_retained"),
                "interviews_retained": protected_ok,
                "version_number": dual.get("version_number"),
                "rollback_target": rollback_target,
                "rollback_proof_ok": bool((rollback_proof or {}).get("ok")),
                "diff": dual.get("diff"),
            }
            cur.execute("ROLLBACK TO SAVEPOINT wave1_dual_write_proof")

            # Re-import clean after savepoint rollback (dependency defs etc. remain).
            imported_again = service.import_company_into_control_plane(
                cur,
                company_code="WATHEFNI",
                legacy_modules=enabled,
                company_status=(company_row or {}).get("status"),
                display_name=(company_row or {}).get("display_name"),
                module_rows=module_rows,
                settings=settings,
                actor="wave1_foundation_reimport",
            )
            evidence["reimport"] = {
                "ok": imported_again.get("ok"),
                "modules": imported_again.get("modules_enabled"),
            }

            # Interview functional posture (read-only)
            cur.execute(
                """
                SELECT status, count(*)::int AS n
                FROM candidate_interviews
                WHERE company_code='WATHEFNI'
                GROUP BY status
                ORDER BY status
                """
            )
            evidence["interviews_status_counts"] = [dict(row) for row in cur.fetchall()]
            evidence["interviews_module_enabled"] = "interviews" in enabled

            # Unified inbound / verified binding posture
            evidence["verified_binding"] = {
                "enforce_flag": vjbg.enforce_flag_on(),
                "enforce_wathefni": vjbg.enforce_enabled(company_code="WATHEFNI"),
                "enforce_other": vjbg.enforce_enabled(company_code="OTHERCO"),
                "shadow_wathefni": vjbg.shadow_enabled(company_code="WATHEFNI"),
                "tenants_env": os.environ.get("WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE_TENANTS"),
            }
            evidence["unified_inbound_flags"] = {
                key: os.environ.get(key)
                for key in (
                    "WATHEFNI_UNIFIED_INBOUND_CV_ADAPTERS",
                    "WATHEFNI_UNIFIED_INBOUND_CV_WAVE4",
                    "WATHEFNI_UNIFIED_INTAKE_AUTHORITY_TENANTS",
                    "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_GATE",
                    "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW",
                    "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE",
                    "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE_TENANTS",
                )
            }

            # Kill switch proof (in-process)
            evidence["kill_switches"] = {
                "plane_default": service.plane_enabled({}),
                "plane_off": service.plane_enabled({"WATHEFNI_TENANT_CONTROL_PLANE": "off"}),
                "dual_write_off": service.dual_write_enabled({"WATHEFNI_TENANT_CONTROL_PLANE": "off"}),
                "shadow_off": service.shadow_enabled({"WATHEFNI_TENANT_CONTROL_PLANE": "off"}),
                "authoritative_forced_false": service.authoritative_enabled({"WATHEFNI_TENANT_CONTROL_AUTHORITATIVE": "on"}),
            }

            # Catalog protection unit proof
            evidence["p0_protection"] = {
                "omit_interviews_result": modules.protect_setup_module_selection(
                    [k for k in sorted(enabled) if k != "interviews"],
                    currently_enabled=sorted(enabled),
                ),
                "interviews_in_catalog": "interviews" in modules.MODULE_BY_KEY,
                "video_interviews_in_catalog": "video_interviews" in modules.MODULE_BY_KEY,
            }

            cur.execute(
                """
                SELECT meta_key, meta_value
                FROM tc_control_plane_meta
                ORDER BY meta_key
                """
            )
            evidence["control_plane_meta"] = [dict(row) for row in cur.fetchall()]

            cur.execute("SELECT count(*)::int AS n FROM tc_tenants")
            evidence["tc_tenant_count"] = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT count(*)::int AS n FROM tc_tenant_module_instances WHERE enabled IS TRUE")
            evidence["tc_enabled_module_instances"] = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT count(*)::int AS n FROM tc_audit_events WHERE company_code='WATHEFNI'")
            evidence["tc_audit_count"] = int((cur.fetchone() or {}).get("n") or 0)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # GO/NO-GO assembly
    checks = {
        "health_200": health.get("http_status") == 200,
        "only_wathefni_company": len(evidence.get("companies") or []) == 1
        and (evidence.get("companies") or [{}])[0].get("company_code") == "WATHEFNI",
        "no_external_tenants": not evidence.get("external_tenants"),
        "zero_module_loss": bool((evidence.get("module_parity") or {}).get("zero_loss")),
        "shadow_parity": bool((evidence.get("shadow_matrix") or {}).get("parity")),
        "interviews_enabled": bool(evidence.get("interviews_module_enabled")),
        "interviews_protected_on_omit": "interviews"
        in ((evidence.get("p0_protection") or {}).get("omit_interviews_result") or []),
        "dual_write_retained_interviews": bool((evidence.get("dual_write_proof") or {}).get("interviews_retained")),
        "rollback_proof_ok": bool((evidence.get("dual_write_proof") or {}).get("rollback_proof_ok")),
        "enforce_wathefni": bool((evidence.get("verified_binding") or {}).get("enforce_wathefni")),
        "enforce_not_global": not bool((evidence.get("verified_binding") or {}).get("enforce_other")),
        "authoritative_off": evidence.get("authoritative") is False,
        "kill_switch_works": bool((evidence.get("kill_switches") or {}).get("plane_off") is False),
        "orphans_classified_not_deleted": (evidence.get("orphan_settings") or {}).get("count") == 12,
    }
    evidence["proof_checks"] = checks
    evidence["go"] = all(checks.values())

    out_dir = Path("/tmp") / f"wave1-tenant-control-{evidence['run_at']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "evidence.json"
    out_path.write_text(json.dumps(evidence, indent=2, default=str) + "\n")
    print(json.dumps({"ok": evidence["go"], "evidence": str(out_path), "checks": checks}, indent=2))
    return 0 if evidence["go"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
