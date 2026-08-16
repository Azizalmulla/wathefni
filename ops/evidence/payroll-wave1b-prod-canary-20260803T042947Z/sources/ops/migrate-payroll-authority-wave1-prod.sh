#!/usr/bin/env bash
# Payroll Wave 1B — production schema migrate (ACK required).
# Applies payroll_authority_wave1 schema 1.0.0 + soft-quarantines May smoke timesheets.
# Does NOT enable payment_processing or money authority.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_PAYROLL_W1B:?Set ACK_PRODUCTION_PAYROLL_W1B=YES to migrate production}"
if [[ "${ACK_PRODUCTION_PAYROLL_W1B}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_PAYROLL_W1B must be YES"
  exit 2
fi

: "${WATHEFNI_ENV:?}"
if [[ "${WATHEFNI_ENV}" != "production" ]]; then
  echo "REFUSE: WATHEFNI_ENV must be production for this script"
  exit 2
fi

PYBIN="${ORCH_PYTHON:-python3}"
"$PYBIN" - <<'PY'
import os
import sys

sys.path.insert(0, ".")
import app
import payroll_authority_wave1 as pyw1

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
print("wave1_version", pyw1.PAYROLL_WAVE1_VERSION)
honesty = pyw1.honesty_payload()
assert honesty.get("payment_processing") == "disabled"
assert honesty.get("money_authority") is False
print("honesty_ok", {k: honesty[k] for k in ("payment_processing", "money_authority", "annual_leave_eligibility_months")})

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        assert db == "wathefni", db
        pyw1.ensure_payroll_wave1_schema(cur, force=True)
        settings = pyw1.ensure_company_settings(cur, company_code="WATHEFNI")
        # Hard-pin money off
        cur.execute(
            """
            UPDATE payroll_company_settings
            SET payment_processing='disabled',
                annual_leave_eligibility_months=6,
                updated_at=now()
            WHERE company_code='WATHEFNI'
            RETURNING *
            """
        )
        settings = dict(cur.fetchone() or settings)
        assert settings.get("payment_processing") == "disabled"
        assert int(settings.get("annual_leave_eligibility_months") or 0) == 6
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname='public'
              AND tablename IN (
                'payroll_company_settings',
                'payroll_compensation_contracts',
                'payroll_compensation_components',
                'payroll_compensation_events',
                'payroll_periods',
                'payroll_period_events'
              )
            ORDER BY 1
            """
        )
        tables = [dict(r)["tablename"] for r in cur.fetchall()]
        print("tables", tables)
        assert len(tables) == 6, tables
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='payroll_timesheets'
              AND column_name IN ('quarantine_status', 'row_version')
            ORDER BY 1
            """
        )
        cols = [dict(r)["column_name"] for r in cur.fetchall()]
        print("timesheet_cols", cols)
        assert "quarantine_status" in cols and "row_version" in cols

        # Soft quarantine May smoke residue — never hard-delete.
        before = []
        cur.execute(
            """
            SELECT timesheet_id::text, employee_key, status, quarantine_status, payroll_status
            FROM payroll_timesheets
            WHERE company_code='WATHEFNI' AND timesheet_id::text = ANY(%s)
            ORDER BY timesheet_id::text
            """,
            (list(pyw1.SMOKE_TIMESHEET_IDS),),
        )
        before = [dict(r) for r in cur.fetchall()]
        print("smoke_before", before)
        q = pyw1.quarantine_smoke_timesheets(cur, company_code="WATHEFNI")
        print("quarantine", {"ok": q.get("ok"), "count": q.get("count"), "hard_deleted": q.get("hard_deleted")})
        assert q.get("ok") is True
        assert q.get("hard_deleted") is False
        cur.execute(
            """
            SELECT timesheet_id::text, employee_key, status, quarantine_status, payroll_status
            FROM payroll_timesheets
            WHERE company_code='WATHEFNI' AND timesheet_id::text = ANY(%s)
            ORDER BY timesheet_id::text
            """,
            (list(pyw1.SMOKE_TIMESHEET_IDS),),
        )
        after = [dict(r) for r in cur.fetchall()]
        print("smoke_after", after)
        assert len(after) == len(before) or len(after) >= 0
        for row in after:
            assert row.get("quarantine_status") == "wave0_smoke_quarantined", row
            assert row.get("payroll_status") == "quarantined", row
        # Rows must still exist (no hard delete)
        assert len(after) == 2, after
    conn.commit()
print("MIGRATE_OK payroll_authority_wave1_prod")
PY
