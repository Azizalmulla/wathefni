#!/usr/bin/env python3
"""READ-ONLY data integrity checks for the Wathefni audit. SELECTs only."""
import os
from pathlib import Path

ENV = Path(os.environ.get("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env"))
if ENV.exists():
    for line in ENV.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(os.environ["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor()

def q(label, sql):
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        print(f"\n## {label}")
        if not rows:
            print("   (no rows)")
        for r in rows:
            print("   " + " | ".join(f"{k}={v}" for k, v in r.items()))
    except Exception as e:
        print(f"\n## {label}\n   ERROR: {e}")

print("=== TENANT / COMPANY SPREAD ===")
q("distinct company_code in companies", "SELECT company_code, name FROM companies")
for t in ["applications","employees","candidates","attendance_records","leave_requests",
          "shift_assignments","payroll_timesheets","positions","import_batches","action_results",
          "candidate_interviews","assessment_attempts","employee_documents","file_registry"]:
    col = "active_company_code" if t == "candidates" else "company_code"
    q(f"{t}: company_code spread", f"SELECT {col} AS company_code, count(*) AS n FROM {t} GROUP BY 1 ORDER BY 2 DESC")

print("\n=== NULL / MISSING TENANT OR IDENTITY ===")
q("candidates with NULL active_company_code", "SELECT count(*) AS n FROM candidates WHERE active_company_code IS NULL")
q("applications NULL company_code/position", "SELECT count(*) AS n FROM applications WHERE company_code IS NULL OR position_code IS NULL")
q("employees NULL company_code/phone", "SELECT count(*) AS n FROM employees WHERE company_code IS NULL OR phone IS NULL")
q("employees NULL app_key (not hire-linked)", "SELECT employee_key, name, company_code, app_key FROM employees")

print("\n=== ORPHANS / DANGLING REFERENCES ===")
q("applications.phone not in candidates",
  "SELECT a.app_key, a.phone FROM applications a LEFT JOIN candidates c ON c.phone=a.phone WHERE c.phone IS NULL")
q("employees.app_key not in applications",
  "SELECT e.employee_key, e.app_key FROM employees e WHERE e.app_key IS NOT NULL AND e.app_key NOT IN (SELECT app_key FROM applications)")
for t in ["attendance_records","leave_requests","shift_assignments","payroll_timesheets",
          "onboarding_items","compliance_documents","employee_documents"]:
    q(f"{t}: employee_key not in employees",
      f"SELECT count(*) AS orphans FROM {t} x LEFT JOIN employees e ON e.employee_key=x.employee_key WHERE e.employee_key IS NULL")

print("\n=== CROSS-COMPANY CONSISTENCY ===")
q("employees vs their application company_code mismatch",
  "SELECT e.employee_key, e.company_code AS emp_cc, a.company_code AS app_cc FROM employees e JOIN applications a ON a.app_key=e.app_key WHERE e.company_code <> a.company_code")
q("post-hire rows whose employee belongs to a different company (attendance)",
  "SELECT count(*) AS n FROM attendance_records x JOIN employees e ON e.employee_key=x.employee_key WHERE e.company_code <> x.company_code")
q("post-hire rows whose employee belongs to a different company (shifts)",
  "SELECT count(*) AS n FROM shift_assignments x JOIN employees e ON e.employee_key=x.employee_key WHERE e.company_code <> x.company_code")
q("post-hire rows whose employee belongs to a different company (leave)",
  "SELECT count(*) AS n FROM leave_requests x JOIN employees e ON e.employee_key=x.employee_key WHERE e.company_code <> x.company_code")
q("post-hire rows whose employee belongs to a different company (timesheets)",
  "SELECT count(*) AS n FROM payroll_timesheets x JOIN employees e ON e.employee_key=x.employee_key WHERE e.company_code <> x.company_code")

print("\n=== DUPLICATES ===")
q("duplicate employees by (company_code, phone)",
  "SELECT company_code, phone, count(*) AS n FROM employees GROUP BY 1,2 HAVING count(*)>1")
q("duplicate employees by (company_code, app_key)",
  "SELECT company_code, app_key, count(*) AS n FROM employees WHERE app_key IS NOT NULL GROUP BY 1,2 HAVING count(*)>1")
q("duplicate applications by (company_code, phone, position_code)",
  "SELECT company_code, phone, position_code, count(*) AS n FROM applications GROUP BY 1,2,3 HAVING count(*)>1")
q("duplicate candidates by email",
  "SELECT lower(email) AS email, count(*) AS n FROM candidates WHERE email IS NOT NULL AND email<>'' GROUP BY 1 HAVING count(*)>1")
q("duplicate import_items by content_sha256",
  "SELECT content_sha256, count(*) AS n FROM import_items WHERE content_sha256 IS NOT NULL GROUP BY 1 HAVING count(*)>1")
q("duplicate candidate_documents by content (sha via metadata absent) — by (phone,filename)",
  "SELECT phone, filename, count(*) AS n FROM candidate_documents GROUP BY 1,2 HAVING count(*)>1")

print("\n=== PAYROLL / PERIOD INTEGRITY ===")
q("timesheets missing period/employee/company",
  "SELECT count(*) AS n FROM payroll_timesheets WHERE period_start IS NULL OR period_end IS NULL OR employee_key IS NULL OR company_code IS NULL")
q("payroll_exports missing period/company",
  "SELECT count(*) AS n FROM payroll_exports WHERE period_start IS NULL OR period_end IS NULL OR company_code IS NULL")

print("\n=== AUDIT COVERAGE SNAPSHOT ===")
q("action_results status spread", "SELECT status, count(*) AS n FROM action_results GROUP BY 1 ORDER BY 2 DESC")
q("action_results NULL company_code", "SELECT count(*) AS n FROM action_results WHERE company_code IS NULL")
q("action_results distinct action_type (top 30)", "SELECT action_type, count(*) AS n FROM action_results GROUP BY 1 ORDER BY 2 DESC LIMIT 30")
q("action_results actor identity coverage",
  "SELECT (actor_user_id IS NOT NULL) AS has_user, (actor_phone IS NOT NULL) AS has_phone, count(*) AS n FROM action_results GROUP BY 1,2")
q("outbound_delivery_events linkage", "SELECT channel, (company_code IS NOT NULL) AS has_cc, (subject_key IS NOT NULL) AS has_subject, count(*) AS n FROM outbound_delivery_events GROUP BY 1,2,3 ORDER BY 4 DESC")
q("pending_actions status", "SELECT status, count(*) AS n FROM pending_actions GROUP BY 1")
q("payroll_timesheet_events types", "SELECT event_type, count(*) AS n FROM payroll_timesheet_events GROUP BY 1")
q("payroll_policy_events types", "SELECT event_type, count(*) AS n FROM payroll_policy_events GROUP BY 1")
q("leave_events types", "SELECT event_type, count(*) AS n FROM leave_events GROUP BY 1")
q("shift_events types", "SELECT event_type, count(*) AS n FROM shift_events GROUP BY 1")

print("\n=== MODULE ENTITLEMENTS (live) ===")
q("company_modules", "SELECT company_code, module_key, enabled, source FROM company_modules ORDER BY 1,2")

print("\n=== USERS / ROLES (live) ===")
q("dashboard_users roles", "SELECT company_code, email, role, status FROM dashboard_users ORDER BY 1")
q("dashboard_whatsapp_identities", "SELECT company_code, phone, status FROM dashboard_whatsapp_identities")

cur.close(); conn.close()
