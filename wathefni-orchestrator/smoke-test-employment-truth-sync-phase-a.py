#!/usr/bin/env python3
"""Phase A — employment truth-sync dry-run unit + optional DB prove."""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    print("    employment truth-sync — dry-run foundation")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import employment_truth_sync as ets

    os.environ.pop("WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS", None)
    check("writers default off", ets.writers_enabled() is False)
    check("assert writers dark", ets.assert_writers_dark().get("ok") is True)
    check("version pinned", ets.TRUTH_SYNC_VERSION == "1.0.0")
    check("P1–P9 listed", len(ets.PENDING_START_INVARIANTS) == 9)

    import employee_lifecycle_wave3 as w3

    check(
        "canonical hub projection pending_start",
        w3.hub_status_for_lifecycle("pending_start") == "pending_start",
    )
    check(
        "canonical hub projection not active",
        w3.is_active_hub_status(w3.hub_status_for_lifecycle("pending_start")) is False,
    )

    ps = ets.evaluate_pending_start_row(
        {
            "lifecycle_state": "pending_start",
            "hub_status": "active",
            "company_code": "WATHEFNI",
            "payroll_eligible": True,
        }
    )
    codes = {f["code"] for f in ps}
    check("pending_start hub active warning", "pending_start_hub_looks_active" in codes, codes)
    check("pending_start payroll fail", "pending_start_payroll_eligible" in codes, codes)

    jd_missing = ets.diff_joining_date(
        employment_start=None,
        offer_proposed_start=date(2026, 9, 1),
    )
    check("joining missing flagged", jd_missing and jd_missing["code"] == "joining_date_missing_on_employment")
    check("joining write blocked while dark", jd_missing.get("writer_blocked") is True)

    jd_mismatch = ets.diff_joining_date(
        employment_start=date(2026, 8, 1),
        offer_proposed_start=date(2026, 9, 1),
    )
    check("joining mismatch does not suggest overwrite", jd_mismatch.get("suggested_write") is None)

    prob = ets.diff_probation_terms(
        employment_start=date(2026, 9, 1),
        offer_probation_days=90,
        employment_probation_end=None,
    )
    check("probation missing flagged", prob and prob["code"] == "probation_end_missing")
    check("expected probation end", prob.get("expected_probation_end") == "2026-11-30")

    dupes = ets.detect_duplicate_employments(
        [
            {"person_id": "p1", "employment_id": "e1", "lifecycle_state": "active"},
            {"person_id": "p1", "employment_id": "e2", "lifecycle_state": "pending_start"},
        ]
    )
    check("duplicate employment detected", any(d["code"] == "duplicate_active_employment_person" for d in dupes))

    mod_off = ets.module_off_behavior(enabled_modules=["onboarding"])
    check("module-off: joining sync inactive without offers", mod_off["joining_sync_active"] is False)
    check("module-off note present", "usable" in (mod_off.get("note") or "").lower())

    rb = ets.rollback_guidance()
    check("rollback keeps writers off", any("WRITERS=off" in s for s in rb.get("runtime", [])))

    # Optional DB dry-run
    url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("WATHEFNI_DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or ""
    ).strip()
    if not url:
        print("SKIP DB: no DATABASE_URL (unit only)")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0

    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ModuleNotFoundError:
        print("SKIP DB: psycopg2 missing")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0

    company = str(os.environ.get("WATHEFNI_TRUTH_SYNC_COMPANY") or "WATHEFNI").upper()
    conn = psycopg2.connect(url)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            report = ets.dry_run_company(cur, company, limit=100)
            check("dry-run ok", report.get("ok") is True, report)
            check("dry-run writers still off", report.get("writers_enabled") is False)
            check("dry-run mode", report.get("mode") == "dry_run")
            check("counts present", isinstance(report.get("counts"), dict))
            # Projection repair (not truth-sync writers) then re-scan for zero fail invariants.
            from employee_lifecycle_wave3 import ensure_lifecycle_schema, repair_pending_start_hub_projection

            ensure_lifecycle_schema(cur)
            repair = repair_pending_start_hub_projection(cur, company_code=company)
            conn.commit()
            check("hub projection repair ran", repair.get("ok") is True, repair)
            report2 = ets.dry_run_company(cur, company, limit=100)
            check("post-repair dry-run ok", report2.get("ok") is True, report2)
            check(
                "P1–P9 invariant violations == 0",
                report2.get("pending_start_invariants_pass") is True
                and int((report2.get("counts") or {}).get("fail") or 0) == 0,
                {
                    "fail": (report2.get("counts") or {}).get("fail"),
                    "codes": report2.get("invariant_violation_codes"),
                    "findings": report2.get("findings"),
                },
            )
            print(
                f"    dry-run company={company} findings={report2.get('counts', {}).get('findings')} "
                f"fail={report2.get('counts', {}).get('fail')} repaired_hub={repair.get('hub_rows_repaired')}"
            )
            if report2.get("pending_start_invariants_pass") and int((report2.get("counts") or {}).get("fail") or 0) == 0:
                print("    PHASE_A_SLICE3_PENDING_START_INVARIANTS_PASS")
    finally:
        conn.close()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("    PHASE_A_SLICE3_TRUTH_SYNC_DRY_RUN_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
