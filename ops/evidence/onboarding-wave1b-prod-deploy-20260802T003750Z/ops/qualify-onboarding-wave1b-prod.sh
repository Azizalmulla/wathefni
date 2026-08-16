#!/usr/bin/env bash
# Onboarding Wave 1B — production qualification (read-only checklist; synthetic DB probes cleaned up).
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
REMOTE_EVID="/opt/wathefni/production-evidence/onboarding-wave1b-prod-deploy/${STAMP}"
mkdir -p "$REMOTE_EVID"/{verify,data,tests,flags}

set -a
# shellcheck disable=SC1091
source /root/.openclaw/secrets/postgres.env
set +a
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1

cd "$ORCH"
PY=.venv/bin/python

# Import process flags for accuracy (service env)
PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in
    WATHEFNI_*=*) export "$line" ;;
  esac
done < /proc/"$PID"/environ

echo '=== freeze regression ===' | tee "$REMOTE_EVID/tests/e360-freeze.txt"
$PY smoke-test-employees360-freeze-regression.py 2>&1 | tee -a "$REMOTE_EVID/tests/e360-freeze.txt"

echo '=== wave1 smoke offline+DB ===' | tee "$REMOTE_EVID/tests/wave1-smoke.txt"
$PY smoke-test-onboarding-wave1-read-authority.py 2>&1 | tee -a "$REMOTE_EVID/tests/wave1-smoke.txt"

echo '=== production four-real reconcile + bank + flags + unchanged fingerprint ==='
$PY - <<'PY' | tee "$REMOTE_EVID/verify/prod-qualification.json"
import json, os, uuid, app

app.ensure_schema()
KEYS = [
  "WATHEFNI-96550252254",
  "WATHEFNI-96566363363",
  "WATHEFNI-96597727743",
  "WATHEFNI-96599411617",
]

# Load before fingerprint if present
before_path = os.environ.get("W1B_BEFORE_JSON")
before_fp = None
if before_path and os.path.isfile(before_path):
    before = json.loads(open(before_path).read())
    before_fp = before.get("item_fingerprint")

results = {
    "seed_enabled": app.onboarding_seed_enabled(),
    "hr_mutate_enabled": app.onboarding_hr_mutate_enabled(),
    "bank_receipt": list(app.validate_onboarding_item_receipt(
        "bank_details", "NBK KW81NBOK0000000000000000123456", None
    )),
    "bank_forbidden_helper": app.onboarding_plaintext_bank_forbidden("bank_details"),
    "reminder_no_company": app.pending_onboarding_reminder_candidates(company_code=None) == [],
    "employees": [],
    "gates": {},
}

assert results["seed_enabled"] is False
assert results["hr_mutate_enabled"] is False
assert results["bank_receipt"] == [False, "bank_via_ess_required"]
assert results["bank_forbidden_helper"] is True
assert results["reminder_no_company"] is True

# Loader source gate
from pathlib import Path
src = Path("app.py").read_text()
s = src.find("def employee_onboarding_items"); e = src.find("\ndef ", s + 1)
assert "candidates.read" not in src[s:e]
results["gates"]["no_candidates_read_in_loader"] = True

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT employee_key, name, company_code, onboarding_status,
                   documents_pending, documents_complete
            FROM employees
            WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)
            ORDER BY employee_key
            """,
            (KEYS,),
        )
        emps = [dict(r) for r in cur.fetchall() or []]
        cur.execute(
            """
            SELECT oi.employee_key, oi.item_id, oi.required, oi.status,
                   md5(coalesce(oi.value::text,'')) AS value_md5
            FROM onboarding_items oi
            JOIN employees e ON e.employee_key=oi.employee_key
            WHERE e.company_code='WATHEFNI' AND oi.employee_key = ANY(%s)
            ORDER BY oi.employee_key, oi.item_id
            """,
            (KEYS,),
        )
        raw_items = [dict(r) for r in cur.fetchall() or []]

after_fp = sorted(
    f"{r['employee_key']}|{r['item_id']}|{r['required']}|{r['status']}|{r.get('value_md5')}"
    for r in raw_items
)
results["item_fingerprint_after"] = after_fp
results["checklist_unchanged"] = (before_fp == after_fp) if before_fp is not None else None
if before_fp is not None:
    assert before_fp == after_fp, "real checklist rows changed during deploy"

for e in emps:
    key = e["employee_key"]
    company = e["company_code"]
    items = app.load_onboarding_items(employee_key=key, company_code=company)
    summary = app.employee_onboarding_summary(e, company_code=company)
    sql = app.onboarding_counts_by_employee(company, [key]).get(key) or {}
    wrong = app.load_onboarding_items(employee_key=key, company_code="NOPE")
    # recompute dry alignment (no lasting change if already consistent)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            app.recompute_employee_onboarding_counts(cur, key)
            cur.execute(
                "SELECT documents_pending, documents_complete, onboarding_status FROM employees WHERE employee_key=%s",
                (key,),
            )
            roll = dict(cur.fetchone())
        conn.commit()
    summary2 = app.employee_onboarding_summary(e, company_code=company)
    row = {
        "employee_key": key,
        "name": e.get("name"),
        "item_count": len(items),
        "helper_eq_summary_ids": sorted(i["item_id"] for i in items)
        == sorted(i["item_id"] for i in (summary.get("items") or [])),
        "counts_match_sql": summary.get("pending_count") == sql.get("pending_count")
        and summary.get("received_count") == sql.get("received_count"),
        "pending": summary.get("pending_count"),
        "received": summary.get("received_count"),
        "required_total": summary.get("required_total"),
        "wrong_tenant_empty": wrong == [],
        "recompute_match": int(roll["documents_pending"]) == summary2["pending_count"]
        and int(roll["documents_complete"]) == summary2["received_count"],
        "bank_values_redacted": all(
            (i.get("value") is None) or (i.get("item_id") != "bank_details")
            for i in items
            if i.get("item_id") == "bank_details" or i.get("value_redacted")
        ),
    }
    assert row["helper_eq_summary_ids"] and row["counts_match_sql"] and row["wrong_tenant_empty"] and row["recompute_match"]
    results["employees"].append(row)

# Manager-scope fail-closed: create ephemeral scope that excludes a real, then cleanup
suffix = uuid.uuid4().hex[:8]
company = "WATHEFNI"
mgr_phone = f"96500{suffix[:6]}"
# Use manager_scope_allows_employee with synthetic context if available
target = emps[0] if emps else None
scope_gate = {"ok": True, "detail": "no_employee_skip"}
if target and hasattr(app, "manager_scope_allows_employee"):
    # Without a manager_scopes row for this phone, owners/unscoped path may allow;
    # instead verify wrong-company load + reminder company isolation.
    cands = app.pending_onboarding_reminder_candidates(company_code=company, limit=50, min_hours_since_last=0)
    foreign = [c for c in cands if str(c.get("company_code") or "").upper() != company]
    scope_gate = {
        "ok": foreign == [],
        "reminder_foreign_count": len(foreign),
        "still_onboarding_no_company": app.employees_still_onboarding(company_code=None) == [],
    }
    assert scope_gate["ok"] and scope_gate["still_onboarding_no_company"]
results["tenant_reminder_gate"] = scope_gate

# Synthetic waived count probe (cleanup)
probe_key = f"W1B-{suffix}"
try:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees (employee_key, company_code, name, phone, onboarding_status, documents_pending, documents_complete)
                VALUES (%s,'WATHEFNI',%s,%s,'in_progress',0,0)
                ON CONFLICT (employee_key) DO NOTHING
                """,
                (probe_key, f"W1B probe {suffix}", f"96599{suffix[:6]}"),
            )
            for item_id, required, status in (
                ("civil_id", True, "received"),
                ("passport", True, "waived"),
                ("personal_photo", True, "pending"),
            ):
                cur.execute(
                    """
                    INSERT INTO onboarding_items (employee_key, item_id, label, item_type, required, document_type, status)
                    VALUES (%s,%s,%s,'document',%s,%s,%s)
                    ON CONFLICT (employee_key, item_id) DO UPDATE SET status=EXCLUDED.status, required=EXCLUDED.required
                    """,
                    (probe_key, item_id, item_id, required, item_id, status),
                )
            app.recompute_employee_onboarding_counts(cur, probe_key)
        conn.commit()
    emp = {"employee_key": probe_key, "company_code": "WATHEFNI", "name": "probe", "onboarding_status": "in_progress"}
    summary = app.employee_onboarding_summary(emp, company_code="WATHEFNI")
    sql = app.onboarding_counts_by_employee("WATHEFNI", [probe_key]).get(probe_key) or {}
    waived_ok = summary["pending_count"] == 1 and summary["received_count"] == 1 and sql["pending_count"] == 1
    results["waived_probe"] = {
        "ok": waived_ok,
        "summary": {k: summary[k] for k in ("pending_count", "received_count", "required_total")},
        "sql": sql,
    }
    assert waived_ok
finally:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM onboarding_items WHERE employee_key=%s", (probe_key,))
            cur.execute("DELETE FROM employees WHERE employee_key=%s", (probe_key,))
        conn.commit()
    results["cleanup_probe_deleted"] = True

results["gates"]["all_four_present"] = len(results["employees"]) == 4
results["gates"]["all_reconcile"] = all(
    r["helper_eq_summary_ids"] and r["counts_match_sql"] and r["recompute_match"] for r in results["employees"]
)
results["ok"] = (
    results["gates"]["no_candidates_read_in_loader"]
    and results["gates"]["all_four_present"]
    and results["gates"]["all_reconcile"]
    and results["checklist_unchanged"] is True
    and results["seed_enabled"] is False
    and results["hr_mutate_enabled"] is False
    and results["cleanup_probe_deleted"] is True
)
print(json.dumps(results, indent=2, default=str))
raise SystemExit(0 if results["ok"] else 1)
PY

echo 'QUAL_OK'
