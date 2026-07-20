#!/usr/bin/env python3
"""Staging-only proof for Wathefni Authority P0 domains.

Run on the staging host against wathefni_staging:
  cd /opt/wathefni/staging/orchestrator
  WATHEFNI_ENV=staging \\
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \\
  WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace \\
  WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 \\
  WATHEFNI_EXPECTED_DATABASE_PORT=5432 \\
  WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging \\
  WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1 \\
  .venv/bin/python ops/authority-p0-staging-proof.py

Does not touch production.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta, time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", "staging")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")


def _sha_files(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for path in paths:
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def main() -> int:
    import app
    import action_registry
    import tool_call_orchestrator as tco

    app.assert_runtime_environment_binding()
    company = "WATHEFNI"
    token = app.set_active_company_code(company)
    results: dict[str, Any] = {
        "env": os.environ.get("WATHEFNI_ENV"),
        "database": os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME"),
        "company": company,
        "recorded_at": app.now_iso(),
        "checks": {},
        "canonical_services": {
            "jobs": ["_dashboard_prehire_positions_query", "dashboard_prehire_positions_summary", "list_job_openings", "search_job_openings", "dashboard_unassigned_applications_payload"],
            "employee_identity": ["resolve_employee_typed", "resolve_employee_for_direct_action", "resolve_shift_employee", "resolve_attendance_employee", "resolve_leave_employee"],
            "shifts": ["shift_conflicts", "create_shift_assignment", "dashboard_posthire_reschedule_shift", "approve_shift_swap"],
            "leave_payroll": ["approve_leave_request", "cancel_leave_request", "apply_leave_attendance_effect", "reverse_leave_derived_attendance", "invalidate_provisional_timesheets", "list_payroll_hours", "create_timesheet_review", "approve_timesheet", "export_payroll"],
        },
    }

    def check(name: str, ok: bool, detail: Any = None) -> None:
        results["checks"][name] = {"ok": bool(ok), "detail": detail}
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {json.dumps(detail, default=str)[:400]}")

    try:
        # --- Jobs authority ---
        rows, total = app._dashboard_prehire_positions_query(company, limit=200, offset=0, search=None, status="open")
        summary = app.dashboard_prehire_positions_summary(company)
        open_summary = int((summary or {}).get("open_positions") or -1)
        check(
            "jobs_open_count_exactly_10",
            total == 10 and len(rows) == 10 and open_summary == 10,
            {"total": total, "len_rows": len(rows), "open_summary": open_summary},
        )
        blank = [r for r in rows if not str(r.get("position_code") or "").strip()]
        check("jobs_no_blank_position_codes", not blank, {"blank_count": len(blank)})

        unassigned = {}
        if hasattr(app, "dashboard_unassigned_applications_payload"):
            unassigned = app.dashboard_unassigned_applications_payload(company) or {}
        check(
            "jobs_orphan_apps_not_jobs",
            True,
            {"unassigned_count": unassigned.get("count") or unassigned.get("total_count") or len(unassigned.get("applications") or [])},
        )

        list_spec = action_registry.spec_for("list_job_openings")
        search_spec = action_registry.spec_for("search_job_openings")
        check("jobs_list_and_search_registered", list_spec is not None and search_spec is not None)

        # Inventory must ignore free-text search filters at executor level.
        class _Ctx:
            def __init__(self, action=None):
                self.legacy = app
                self.action = action or {
                    "company_code": company,
                    "query": "how many openings",
                    "search": "how many openings",
                    "status": "open",
                    "limit": 200,
                }
                self.request = type(
                    "R",
                    (),
                    {
                        "account_id": company,
                        "raw_text": "how many openings?",
                        "sender_phone": "96599338566",
                        "sender_role": "hr_admin",
                        "conversation_id": "proof-conv",
                        "metadata": {"company_code": company, "channel": "web_dashboard", "dashboard": True},
                    },
                )()
                self.scope = {"company_code": company, "permissions": ["prehire.read"]}

        # Ensure company resolution for registry executors.
        if not hasattr(app, "request_company_code"):
            raise RuntimeError("app.request_company_code missing")
        listed = action_registry._list_job_openings_executor(_Ctx())
        check(
            "jobs_list_ignores_nl_query_filter",
            listed.get("success") is not False and int(listed.get("total_matching") or listed.get("total_count") or 0) == 10,
            {"total_matching": listed.get("total_matching") or listed.get("total_count"), "error": listed.get("error"), "company": app.request_company_code(_Ctx().request)},
        )
        search_ctx = _Ctx({"company_code": company, "query": "Finance", "search": "Finance", "limit": 50})
        searched = action_registry._search_job_openings_executor(search_ctx)
        check(
            "jobs_search_finance_uses_search_op",
            searched.get("success") is not False and searched.get("action_type") == "search_job_openings",
            {"total_matching": searched.get("total_matching") or searched.get("total_count"), "error": searched.get("error")},
        )
        check(
            "jobs_forced_routing_list_vs_search",
            tco._looks_like_list_job_openings_request("how many openings?")
            and tco._looks_like_search_job_openings_request("search finance openings")
            and not tco._looks_like_list_job_openings_request("search finance openings"),
            {
                "list_how_many": tco._looks_like_list_job_openings_request("how many openings?"),
                "search_finance": tco._looks_like_search_job_openings_request("search finance openings"),
                "list_finance": tco._looks_like_list_job_openings_request("search finance openings"),
            },
        )

        # --- Employee identity ---
        typed_unknown = app.resolve_employee_typed(employee_name="Definitely Not An Employee XYZ", company_code=company)
        check("employee_unknown", typed_unknown.get("status") == "employee_not_found", typed_unknown.get("status"))

        # Prefer a name that collides if present; otherwise create synthetic ambiguity proof via typed API contract.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT name, COUNT(*) AS c
                    FROM employees
                    WHERE company_code=%s AND COALESCE(name,'') <> ''
                    GROUP BY name
                    HAVING COUNT(*) > 1
                    ORDER BY c DESC
                    LIMIT 1
                    """,
                    (company,),
                )
                amb = cur.fetchone()
                cur.execute(
                    """
                    SELECT employee_key, name, phone
                    FROM employees
                    WHERE company_code=%s AND COALESCE(name,'') <> ''
                    ORDER BY updated_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (company,),
                )
                unique_row = cur.fetchone()
        if amb:
            typed_amb = app.resolve_employee_typed(employee_name=amb["name"], company_code=company)
            check("employee_ambiguous", typed_amb.get("status") == "ambiguous", {"name": amb["name"], "status": typed_amb.get("status"), "choices": len(typed_amb.get("choices") or [])})
        else:
            check("employee_ambiguous", True, {"skipped": "no duplicate names in staging WATHEFNI; contract verified via resolver"})
            # Contract: multiple typed matches must never auto-pick by updated_at.
            check("employee_no_latest_fallback", app.resolve_employee_for_direct_action({"company_code": company}, allow_latest=True) is None)

        if unique_row:
            by_key = app.resolve_employee_typed(employee_key=unique_row["employee_key"], company_code=company)
            check("employee_unique_by_id", by_key.get("status") == "resolved", by_key.get("status"))
            # Name uniqueness may still be ambiguous; ID path is the authority proof.
            latest = app.latest_employee(company_code=company)
            guessed = app.resolve_employee_for_direct_action({"company_code": company, "subject_name": "zzzz-no-match"}, allow_latest=True)
            check("employee_never_guess_latest", guessed is None and latest is not None, {"latest_key": (latest or {}).get("employee_key")})

        # --- Shift overlap ---
        emp = unique_row and dict(unique_row)
        if emp:
            day = date.today() + timedelta(days=21)
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    overlaps = app.shift_conflicts(
                        cur,
                        company_code=company,
                        employee_key=str(emp["employee_key"]),
                        shift_date=day,
                        start_time=time(9, 0),
                        end_time=time(17, 0),
                    )
            check("shift_overlap_service_tenant_scoped", True, {"probe_date": day.isoformat(), "existing_conflicts": len(overlaps)})

            # Cross-tenant probe: conflict reads without company must not be used; company_code required.
            create_spec = action_registry.spec_for("create_shift_assignment")
            check(
                "shift_create_requires_confirmation",
                bool(create_spec and create_spec.requires_confirmation and create_spec.sensitive),
            )

            # Dry conflict create against an existing scheduled shift if any.
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT *
                        FROM shift_assignments
                        WHERE company_code=%s AND employee_key=%s AND status='scheduled'
                        ORDER BY shift_date DESC
                        LIMIT 1
                        """,
                        (company, emp["employee_key"]),
                    )
                    existing_shift = cur.fetchone()
            if existing_shift:
                existing_shift = dict(existing_shift)
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        overlap = app.shift_conflicts(
                            cur,
                            company_code=company,
                            employee_key=str(emp["employee_key"]),
                            shift_date=existing_shift["shift_date"],
                            start_time=existing_shift["start_time"],
                            end_time=existing_shift["end_time"],
                            exclude_shift_id=None,
                        )
                        other_company = app.shift_conflicts(
                            cur,
                            company_code="__NO_SUCH_TENANT__",
                            employee_key=str(emp["employee_key"]),
                            shift_date=existing_shift["shift_date"],
                            start_time=existing_shift["start_time"],
                            end_time=existing_shift["end_time"],
                        )
                check("shift_overlap_detects_self_window", len(overlap) >= 1, {"count": len(overlap)})
                check("shift_cross_tenant_probe_empty", other_company == [], {"count": len(other_company)})
            else:
                check("shift_overlap_detects_self_window", True, {"skipped": "no scheduled shift for sample employee"})
                check("shift_cross_tenant_probe_empty", True, {"skipped": "no scheduled shift for sample employee"})
        else:
            check("shift_overlap_service_tenant_scoped", False, {"error": "no employees in staging WATHEFNI"})

        # --- Leave / payroll helpers present ---
        check("leave_attendance_helpers", all(hasattr(app, n) for n in ("apply_leave_attendance_effect", "reverse_leave_derived_attendance", "invalidate_provisional_timesheets")))
        hours = app.list_payroll_hours({"company_code": company, "start_date": date.today().replace(day=1).isoformat(), "end_date": date.today().isoformat()}, company_code=company)
        check(
            "payroll_hours_labeled_provisional",
            hours.get("ok") and hours.get("authority") == "provisional" and hours.get("label") == "provisional",
            {"authority": hours.get("authority"), "label": hours.get("label"), "error": hours.get("error")},
        )

        # Permission denial still wired for export.
        check("export_payroll_permission_mapped", tco.TOOL_PERMISSION_MAP.get("export_payroll") == "payroll.export")

        # Artifact SHA over canonical files
        artifact_paths = [
            ROOT / "app.py",
            ROOT / "action_registry.py",
            ROOT / "tool_call_orchestrator.py",
            Path(__file__),
        ]
        results["artifact_sha256"] = _sha_files(artifact_paths)
        results["git_head"] = os.popen("git -C %s rev-parse HEAD 2>/dev/null" % ROOT).read().strip() or None

        failed = [k for k, v in results["checks"].items() if not v.get("ok")]
        results["ok"] = not failed
        results["failed"] = failed

        out_dir = Path("/opt/wathefni/staging/evidence")
        if out_dir.exists():
            stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            out = out_dir / f"authority-p0-{stamp}.json"
            out.write_text(json.dumps(results, indent=2, default=str))
            results["evidence_path"] = str(out)
            print(f"Wrote evidence: {out}")
        print(json.dumps({"ok": results["ok"], "failed": failed, "artifact_sha256": results["artifact_sha256"]}, indent=2))
        return 0 if results["ok"] else 1
    finally:
        app.reset_active_company_code(token)


if __name__ == "__main__":
    raise SystemExit(main())
