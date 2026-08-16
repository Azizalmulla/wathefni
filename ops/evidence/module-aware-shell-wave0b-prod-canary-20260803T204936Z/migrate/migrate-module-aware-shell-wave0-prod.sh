#!/usr/bin/env bash
# Module-Aware Shell Wave 0-B — production ACK (honesty + audit marker).
# Does NOT enable mutations, money, ingest, WhatsApp widen, or further shell waves.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_MODULE_AWARE_SHELL_W0B:?Set ACK_PRODUCTION_MODULE_AWARE_SHELL_W0B=YES to ACK production}"
if [[ "${ACK_PRODUCTION_MODULE_AWARE_SHELL_W0B}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_MODULE_AWARE_SHELL_W0B must be YES"
  exit 2
fi

: "${WATHEFNI_ENV:?}"
if [[ "${WATHEFNI_ENV}" != "production" ]]; then
  echo "REFUSE: WATHEFNI_ENV must be production for this script"
  exit 2
fi

INGEST="${WATHEFNI_ATTENDANCE_CAPTURE_INGEST:-off}"
if echo "$INGEST" | grep -qiE '^(on|true|1|yes)$'; then
  echo "REFUSE: WATHEFNI_ATTENDANCE_CAPTURE_INGEST must remain off" >&2
  exit 3
fi

PYBIN="${ORCH_PYTHON:-python3}"
"$PYBIN" - <<'PY'
import os
import sys

sys.path.insert(0, ".")
import app
import platform_assistant_spine_wave1 as spine
import workspace_capability as wc
import assistant_capability_catalog as caps

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
os.environ.setdefault("WATHEFNI_ASSISTANT_MUTATIONS", "0")
os.environ.setdefault("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")

assert spine.assistant_mutations_allowed() is False
assert os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off").lower() in {"off", "0", "false", "no", ""}

# Landing contract smoke
assert wc.resolve_focused_posthire_landing(["leave"], available_pages=["leave", "employees"], action_inbox_offerable=False) == "leave"
assert wc.resolve_focused_posthire_landing(
    ["leave", "attendance", "shifts"],
    available_pages=["leave", "attendance", "shifts", "employees", "inbox"],
    action_inbox_offerable=True,
) == "inbox"
assert wc.resolve_focused_posthire_landing(
    ["pre_hiring", "leave"],
    available_pages=["overview", "leave", "employees"],
    action_inbox_offerable=True,
) == "overview"

# Catalog: pre_hiring not always on
class Legacy:
    def __init__(self, enabled):
        self.enabled = set(enabled)

    def configured_company_modules(self, company):
        return set(self.enabled)

tools = [{"function": {"name": n}} for n in ("list_job_openings", "list_leave_requests", "summarize_employee_360")]
cat = caps.build_assistant_capability_catalog(
    legacy=Legacy({"leave"}),
    company_code="WATHEFNI",
    permissions=["leave.read", "employees.read", "jobs.read", "prehire.read"],
    visible_tools=tools,
)
assert cat["capabilities"]["jobs"]["status"] == caps.STATUS_MODULE_OFF
assert cat["capabilities"]["posthire_employees_360"]["offerable"] is True or cat["capabilities"]["posthire_employees_360"]["status"] == caps.STATUS_AVAILABLE

honesty = {
    "contract": "module_aware_shell_wave0_focused_workforce",
    "wathefni_only": True,
    "hr_dashboard_only": True,
    "mutates_records": False,
    "payroll_money": False,
    "attendance_ingest": False,
    "whatsapp_widening": False,
    "home_rebuild": False,
    "assistant_wave3": False,
}

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        assert db == "wathefni", db
        spine.ensure_assistant_spine_audit_schema(cur, force=True)
        ack = spine.record_assistant_event(
            cur,
            company_code="WATHEFNI",
            event_type="assistant.shell_wave0b_production_ack",
            channel="web_dashboard",
            detail={**honesty, "ack": "ACK_PRODUCTION_MODULE_AWARE_SHELL_W0B=YES"},
            environment="production",
        )
        conn.commit()
        print("ack_event_id", ack.get("event_id"))
        print("ACK_PRODUCTION_MODULE_AWARE_SHELL_W0B=YES")
        print("residual_policy=canary_tagged_cleaned_ack_retained")
print("MIGRATE_OK")
PY
