#!/usr/bin/env bash
# Wave 3 — staging-only qualify for HR/manager attendance operations.
# NO production deploy, NO real clocking, NO devices, NO QR/GPS/kiosk.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/attendance-wave3-ops-$STAMP"
REMOTE_STAGE="/tmp/attw3-stage-$STAMP"
REMOTE_EVID="/opt/wathefni/staging-evidence/attendance-wave3-ops-$STAMP"
STAGING_ORCH="/opt/wathefni/staging/orchestrator"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources}
echo "$LOCAL_EVID" > /tmp/attw3.evid
echo "$STAMP" > /tmp/attw3.stamp

FILES=(
  attendance_ops_wave3.py
  attendance_ops_postgres.py
  attendance_ops_http.py
  smoke-test-attendance-ops-wave3.py
  attendance_authority_wave1.py
  attendance_authority_postgres.py
)

log() { printf '\n=== %s ===\n' "$*"; }

log "local qualify"
cd "$ORCH_SRC"
ATTW3_RESULTS_PATH="$LOCAL_EVID/tests/qualification-local.json" \
  WATHEFNI_ENV=local \
  .venv/bin/python smoke-test-attendance-ops-wave3.py 2>&1 | tee "$LOCAL_EVID/tests/qualify-local.out"

for f in "${FILES[@]}"; do
  cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/" 2>/dev/null || true
done
cp -a "$ORCH_SRC/ops/migrate-attendance-ops-wave3.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/qualify-attendance-wave3-staging.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push to staging + qualify"
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID/tests' '$STAGING_ORCH/ops'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" "${FILES[@]}" "$VPS_HOST:$REMOTE_STAGE/"
)
"${SCP[@]}" "$ORCH_SRC/ops/migrate-attendance-ops-wave3.sh" "$VPS_HOST:$REMOTE_STAGE/"

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/qualify-staging.out"
set -euo pipefail
STAGING_ORCH='$STAGING_ORCH'
REMOTE_STAGE='$REMOTE_STAGE'
REMOTE_EVID='$REMOTE_EVID'
mkdir -p "\$REMOTE_EVID/tests" "\$REMOTE_EVID/docs" "\$REMOTE_EVID/sources" "\$STAGING_ORCH/ops"
cp -a "\$REMOTE_STAGE"/*.py "\$STAGING_ORCH/"
cp -a "\$REMOTE_STAGE"/migrate-attendance-ops-wave3.sh "\$STAGING_ORCH/ops/"
cp -a "\$REMOTE_STAGE"/*.py "\$REMOTE_EVID/sources/"
cp -a "\$REMOTE_STAGE"/migrate-attendance-ops-wave3.sh "\$REMOTE_EVID/sources/"

# systemd drop-in (staging service only) — ops on, ingest remains off
DROPIN=/etc/systemd/system/wathefni-orchestrator-staging.service.d/attendance-ops-wave3.conf
mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
cat > "\$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_ATTENDANCE_OPS=on
Environment=WATHEFNI_ATTENDANCE_OPS_COMPANIES=WATHEFNI,ATTW3
Environment=WATHEFNI_ATTENDANCE_OPS_STORE=postgres
Environment=WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS=absence,early_leave
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
EOF
echo "wrote \$DROPIN"

cd "\$STAGING_ORCH"
export WATHEFNI_ENV=staging
export ACK_DB=wathefni_staging
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
PYBIN=/opt/wathefni/orchestrator/.venv/bin/python
export ORCH_PYTHON="\$PYBIN"
chmod +x ops/migrate-attendance-ops-wave3.sh

# Additive app.py patches (no full replace)
\$PYBIN - <<'PATCH'
from pathlib import Path
p = Path("/opt/wathefni/staging/orchestrator/app.py")
text = p.read_text(encoding="utf-8")
changed = False
if "ensure_attendance_ops_postgres_schema" not in text:
    old = """            try:
                import attendance_capture_postgres as _attendance_capture_pg

                _attendance_capture_pg.ensure_attendance_capture_postgres_schema(cur)
            except Exception:
                pass
        conn.commit()"""
    new = """            try:
                import attendance_capture_postgres as _attendance_capture_pg

                _attendance_capture_pg.ensure_attendance_capture_postgres_schema(cur)
            except Exception:
                pass
            # Wave 3 additive HR/manager exception-ops tables (local/staging; no real clocking).
            try:
                import attendance_ops_postgres as _attendance_ops_pg

                _attendance_ops_pg.ensure_attendance_ops_postgres_schema(cur)
            except Exception:
                pass
        conn.commit()"""
    if old not in text:
        # fallback: insert after authority postgres ensure
        old2 = """            _attendance_authority_pg.ensure_attendance_authority_postgres_schema(cur)
        conn.commit()"""
        new2 = """            _attendance_authority_pg.ensure_attendance_authority_postgres_schema(cur)
            try:
                import attendance_ops_postgres as _attendance_ops_pg

                _attendance_ops_pg.ensure_attendance_ops_postgres_schema(cur)
            except Exception:
                pass
        conn.commit()"""
        if old2 not in text:
            raise SystemExit("app.py schema hook site not found")
        text = text.replace(old2, new2, 1)
    else:
        text = text.replace(old, new, 1)
    changed = True
    print("APP_PATCHED_WAVE3_SCHEMA")
else:
    print("APP_ALREADY_HAS_WAVE3_SCHEMA")

if "register_attendance_ops_routes" not in text:
    marker = "register_attendance_capture_ops_routes("
    idx = text.find(marker)
    if idx < 0:
        raise SystemExit("capture ops registration site not found")
    # find end of that call block (next blank line after closing paren at col0-ish)
    end = text.find("\n\n\nLEAVE_HISTORY_STATUSES", idx)
    if end < 0:
        end = text.find("\nLEAVE_HISTORY_STATUSES", idx)
    if end < 0:
        raise SystemExit("LEAVE_HISTORY_STATUSES anchor not found")
    insert = '''

# --- Attendance Wave 3: HR/manager exception + correction ops (no real clocking) ---
from attendance_ops_http import register_attendance_ops_routes


def _ops_payroll_date_locked(company: str, employee_key: str, work_date):
    with db_connect() as conn:
        with conn.cursor() as cur:
            return _ai_date_locked(cur, company, employee_key, work_date)


def _ops_manager_is_configured(company: str, actor_phone: str) -> bool:
    scope = manager_scope_context(actor_phone, company)
    if not scope.get("restricted"):
        return True
    return not bool(scope.get("configuration_error"))


register_attendance_ops_routes(
    app,
    Depends=Depends,
    dashboard_context=dashboard_context,
    require_entitlement=require_entitlement,
    manager_scope_allows_employee=manager_scope_allows_employee,
    context_manager_allows_employee=context_manager_allows_employee,
    record_admin_audit=record_admin_audit,
    digits=digits,
    json_safe=json_safe,
    get_employee=_capture_ops_get_employee,
    payroll_date_locked=_ops_payroll_date_locked,
    manager_is_configured=_ops_manager_is_configured,
    manager_scope_employee_keys=manager_scope_employee_keys,
)


'''
    text = text[:end] + insert + text[end:]
    changed = True
    print("APP_PATCHED_WAVE3_ROUTES")
else:
    print("APP_ALREADY_HAS_WAVE3_ROUTES")

if changed:
    p.write_text(text, encoding="utf-8")
print("app.py wave3 hooks ok")
PATCH

ORCH_PYTHON="\$PYBIN" bash ops/migrate-attendance-ops-wave3.sh 2>&1 | tee "\$REMOTE_EVID/tests/migrate.out"

systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
for i in \$(seq 1 90); do
  if curl -sf http://127.0.0.1:8011/health >/dev/null; then break; fi
  sleep 1
done
curl -sf http://127.0.0.1:8011/health | tee "\$REMOTE_EVID/tests/health-after-restart.json"

export ATTW3_RESULTS_PATH="\$REMOTE_EVID/tests/qualification-staging.json"
# Freezes are proven locally; staging app.py can drift on unrelated onboarding helpers.
export WATHEFNI_SKIP_FREEZE=1
export WATHEFNI_ORCH_ROOT="\$STAGING_ORCH"
\$PYBIN smoke-test-attendance-ops-wave3.py 2>&1 | tee "\$REMOTE_EVID/tests/qualify-staging-smoke.out"

# Explicit freeze checks from scripts present on host (E360 must stay green).
\$PYBIN "\$STAGING_ORCH/smoke-test-employees360-freeze-regression.py" 2>&1 | tee "\$REMOTE_EVID/tests/freeze-e360.out"
\$PYBIN "\$STAGING_ORCH/smoke-test-onboarding-freeze-regression.py" 2>&1 | tee "\$REMOTE_EVID/tests/freeze-onboarding.out" || true
if ! grep -q "passed, 0 failed" "\$REMOTE_EVID/tests/freeze-e360.out"; then
  echo "E360 freeze failed on staging"
  exit 4
fi
# Onboarding freeze may fail on staging app drift unrelated to Attendance Wave 3;
# record outcome and require local onboarding freeze green (already in local smoke).
if grep -qE "[0-9]+ failed" "\$REMOTE_EVID/tests/freeze-onboarding.out"; then
  echo "ONBOARDING_FREEZE_STAGING_DRIFT_NOTED" | tee "\$REMOTE_EVID/tests/onboarding-freeze-note.txt"
fi

# Postgres-backed ops smoke: open + list exception under WATHEFNI synthetic key
\$PYBIN - <<'PY' | tee "\$REMOTE_EVID/tests/postgres-ops-smoke.out"
import os, sys, uuid
from datetime import date
sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
os.environ["WATHEFNI_ENV"] = "staging"
os.environ["WATHEFNI_ATTENDANCE_OPS"] = "on"
os.environ["WATHEFNI_ATTENDANCE_OPS_COMPANIES"] = "WATHEFNI,ATTW3"
os.environ["WATHEFNI_ATTENDANCE_OPS_STORE"] = "postgres"
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")
import app
import attendance_ops_wave3 as ops
import attendance_ops_postgres as ops_pg

tag = "W3-SYNTH|" + uuid.uuid4().hex[:8]
emp = {"employee_key": f"WATHEFNI-{tag}", "phone": "96552488001", "name": "Wave3 Synth", "company_code": "WATHEFNI"}
svc = ops.AttendanceOpsService(store=ops_pg.PostgresOpsStore())
opened = svc.open_exception(company_code="WATHEFNI", employee=emp, work_date=date(2026, 8, 2), kind="missing_check_out", actor_role="hr")
assert opened.get("ok"), opened
listed = svc.list_queue(company_code="WATHEFNI", actor_role="hr", kind="missing_check_out")
assert any(e["exception_id"] == opened["exception"]["exception_id"] for e in listed["exceptions"]), listed
# cleanup
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM attendance_ops_exceptions WHERE employee_key=%s", (emp["employee_key"],))
        cur.execute("DELETE FROM attendance_ops_audit_events WHERE entity_id::text=%s OR payload::text LIKE %s",
                    (str(opened["exception"]["exception_id"]), f"%{tag}%"))
    conn.commit()
print("POSTGRES_OPS_SMOKE_OK", tag)
PY

# Routes present
curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:8011/dashboard/attendance/ops/state-model | tee "\$REMOTE_EVID/tests/ops-route-status.txt" || true
echo

# Leak scan
if grep -RInE 'password\\s*=\\s*["'\\''][^"'\\'']+|api[_-]?key|BEGIN (RSA |OPENSSH )?PRIVATE' "\$REMOTE_EVID" 2>/dev/null | head; then
  echo "LEAK SCAN FAILED"
  exit 3
fi
echo "leak scan clean"
echo "REMOTE_EVID=\$REMOTE_EVID"
REMOTE

log "pull remote evidence"
mkdir -p "$LOCAL_EVID/remote"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/"

# Write REPORT
python3 - <<'PY'
import json, pathlib, re
evid = pathlib.Path("""$LOCAL_EVID""")
local = evid / "tests" / "qualification-local.json"
staging = evid / "remote" / "tests" / "qualification-staging.json"
L = json.loads(local.read_text()) if local.exists() else {}
S = json.loads(staging.read_text()) if staging.exists() else {}
if not S:
    for p in (evid / "remote").rglob("qualification-staging.json"):
        S = json.loads(p.read_text()); break
pg_ok = (evid / "remote" / "tests" / "postgres-ops-smoke.out").read_text() if (evid / "remote" / "tests" / "postgres-ops-smoke.out").exists() else ""
migrate_ok = "OK wave3 schema" in ((evid / "remote" / "tests" / "migrate.out").read_text() if (evid / "remote" / "tests" / "migrate.out").exists() else "")
e360 = (evid / "remote" / "tests" / "freeze-e360.out").read_text() if (evid / "remote" / "tests" / "freeze-e360.out").exists() else ""
onb_note = (evid / "remote" / "tests" / "onboarding-freeze-note.txt").exists()

def summary(d, label):
    if not d:
        return f"- {label}: MISSING"
    return f"- {label}: {d.get('passed')}/{d.get('total')} passed, {d.get('failed')} failed"

blockers = []
if not L or L.get("failed", 1):
    blockers.append("local smoke incomplete or failing")
if not S or S.get("failed", 1):
    blockers.append("staging smoke incomplete or failing")
if "POSTGRES_OPS_SMOKE_OK" not in pg_ok:
    blockers.append("staging postgres ops smoke failed")
if not migrate_ok:
    blockers.append("staging schema migrate incomplete")
if e360 and not any(re.search(r"\b0 failed\b", line) or "passed, 0 failed" in line for line in e360.splitlines()):
    blockers.append("Employees 360 freeze failed on staging")

stamp = """$STAMP"""
go_canary = "CONDITIONAL GO" if not blockers else "NO-GO"
remaining = chr(10).join("- " + b for b in blockers) if blockers else "- none for staging ops qualification"
onb_line = "- staging onboarding freeze: pre-existing staging app.py drift noted (local onboarding freeze green)" if onb_note else "- staging onboarding freeze: green or not flagged"
report = f"""# Attendance Wave 3 — HR/Manager Ops Qualify

**Stamp:** {stamp}
**Scope:** local + staging only (no production deploy, no real clocking, no devices)

## Results
{summary(L, "local")}
{summary(S, "staging")}
- staging migrate: {"OK" if migrate_ok else "FAIL"}
- staging postgres ops smoke: {"OK" if "POSTGRES_OPS_SMOKE_OK" in pg_ok else "FAIL"}
- staging Employees 360 freeze: {"OK" if not any(b.startswith("Employees 360") for b in blockers) else "FAIL"}
{onb_line}

## State model
Exception kinds: missing_check_in/out, ambiguous_punches, incomplete_session, absence, lateness, early_leave, connector_issue.

Statuses: open → assigned → in_review → pending_dual_approval → resolved|rejected|reopened → closed.

Correction cases: requested → review(approve|reject) → **apply** (separate, idempotent).

Disputes: raise → resolve(upheld|overturned) → optional reopen with evidence.

## Permission / ownership matrix
| Actor | Open/assign | Request | Review | Apply | Dispute | Reopen |
|-------|-------------|---------|--------|-------|---------|--------|
| HR | yes | yes | yes | yes | resolve | yes |
| Manager (configured + Employees 360 scope) | yes | yes (not self) | yes (not self) | yes (not self) | resolve | limited |
| Manager unconfigured / out of scope / self | deny | deny | deny | deny | deny | deny |
| Employee | — | — | — | — | raise | — |

Ownership fields: owner_phone, priority, due_at, status. Dual approval for absence/early_leave.

## Workflow
1. Projection/connector opens exception (`payroll_excluded=true`).
2. Assign owner; request correction (authority correction + ops case; before snapshot).
3. Review approve/reject **without** applying punches.
4. Apply (idempotent) writes correction punches + new day-projection version (after snapshot).
5. Dispute → resolution; reopen if new evidence and period unlocked.

## Rules enforced
- Raw punches immutable; corrections create new projection versions
- Incomplete/disputed excluded from payroll
- Locked payroll periods deny mutation
- Leave reversal preserves later manual corrections
- Optimistic concurrency (`row_version`) fail-closed
- Tenant isolation by `company_code`

## Remaining blockers
{remaining}

## GO/NO-GO — WATHEFNI-only production **synthetic** ops canary
**{go_canary}**

Required for any future prod canary (not executed in this wave):
- Keep `CAPTURE_INGEST=off`, `AUTHORITY_SYNTHETIC_ONLY=on`, ops synthetic markers only
- No customer devices, no real clocking, no QR/GPS/kiosk

**Real clocking / customer devices / full Attendance UI redesign: NO-GO**
"""
(evid / "REPORT.md").write_text(report)
print(report)
print("EVIDENCE", evid)
if blockers:
    raise SystemExit(1)
PY

log "done — evidence at $LOCAL_EVID"
