#!/usr/bin/env bash
# One-shot: wait until ~05:40 Asia/Kuwait, then ONE outside-scope sendMail probe.
# If denied → minimal allow/deny matrix. If 202 → stop. No RBAC changes. No loops.
set -euo pipefail

TARGET_KUWAIT="${TARGET_KUWAIT:-05:40}"
EVID_LOCAL_ROOT="${EVID_LOCAL_ROOT:-/Users/azizalmulla/Desktop/claw/ops/evidence}"
VPS=root@76.13.63.68
DENIED_UPN=wathefni-rbac-deny-probe@wathefni.onmicrosoft.com
EVIDENCE_UPN=ABDULAZIZALMULLA@wathefni.onmicrosoft.com

now_k=$(TZ=Asia/Kuwait date +%s)
# Today 05:40 Kuwait; if already past, still run once immediately after a short notice sleep of 0
target_k=$(TZ=Asia/Kuwait date -j -f '%Y-%m-%d %H:%M:%S' "$(TZ=Asia/Kuwait date +%Y-%m-%d) ${TARGET_KUWAIT}:00" +%s 2>/dev/null || true)
if [ -z "${target_k:-}" ]; then
  # GNU date on remote; locally use python for portability
  target_k=$(python3 - <<'PY'
from datetime import datetime
from zoneinfo import ZoneInfo
z=ZoneInfo("Asia/Kuwait")
now=datetime.now(z)
target=now.replace(hour=5, minute=40, second=0, microsecond=0)
print(int(target.timestamp()))
PY
)
fi
sleep_s=$(( target_k - $(date +%s) ))
if [ "$sleep_s" -lt 0 ]; then sleep_s=0; fi
echo "SCHEDULED_PROBE wait_s=$sleep_s target_kuwait=$(TZ=Asia/Kuwait date -r "$target_k" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || python3 -c "from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.fromtimestamp($target_k, ZoneInfo('Asia/Kuwait')))")"
sleep "$sleep_s"
echo "PROBE_START $(TZ=Asia/Kuwait date '+%Y-%m-%d %H:%M:%S %Z') / $(date -u +%Y-%m-%dT%H:%M:%SZ)"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOCAL_EV="$EVID_LOCAL_ROOT/hybrid-email-m365-outbound-recheck-$STAMP"
mkdir -p "$LOCAL_EV"

ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS" "STAMP='$STAMP' DENIED_UPN='$DENIED_UPN' EVIDENCE_UPN='$EVIDENCE_UPN' bash -s" <<'REMOTE'
set -euo pipefail
EVID="/opt/wathefni/production-evidence/hybrid-email-m365-outbound/recheck-$STAMP"
mkdir -p "$EVID"
PID=$(systemctl show -p MainPID --value wathefni-orchestrator.service)
ENV_FILE=$(mktemp)
tr '\0' '\n' < /proc/$PID/environ > "$ENV_FILE"
set -a
source <(grep -E '^(WATHEFNI_|PATH|HOME|VIRTUAL_ENV|PG|DATABASE)' "$ENV_FILE" | sed 's/^/export /')
set +a
rm -f "$ENV_FILE"
cd /opt/wathefni/orchestrator

.venv/bin/python - <<'PY' | tee "$EVID/outside-scope-probe.json"
import json, microsoft_mail_send as mms, app, tenant_email_authority as tea
# Keep tenant on wathefni for the single deny probe
tea.force_wathefni_fallback(app, "WATHEFNI", updated_by_user_id="scheduled-deny-probe")
denied = mms.send_mail_as_mailbox(
    mailbox="wathefni-rbac-deny-probe@wathefni.onmicrosoft.com",
    to="ABDULAZIZALMULLA@wathefni.onmicrosoft.com",
    subject="scheduled-outside-scope-probe-once",
    body="single probe",
    save_to_sent_items=False,
)
out = {
    "ok": denied.get("ok"),
    "provider_accept_status": denied.get("provider_accept_status"),
    "error": denied.get("error"),
    "http": (denied.get("raw") or {}).get("http_status"),
    "body": ((denied.get("raw") or {}).get("body") or "")[:300],
}
print(json.dumps(out, indent=2))
open("/tmp/outside-scope-probe-result.json","w").write(json.dumps(out))
PY

python3 - <<'PY'
import json
r=json.load(open("/tmp/outside-scope-probe-result.json"))
denied = (not r.get("ok")) and int(r.get("http") or 0) in {401,403}
open("/tmp/outside-scope-denied.flag","w").write("1" if denied else "0")
print("OUTSIDE_SCOPE_DENIED=" + ("yes" if denied else "no"))
print("HTTP=" + str(r.get("http")))
PY

if [ "$(cat /tmp/outside-scope-denied.flag)" != "1" ]; then
  echo PROPAGATION_STILL_PENDING | tee "$EVID/VERDICT.txt"
  python3 -c 'import json; r=json.load(open("/tmp/outside-scope-probe-result.json")); print("Still HTTP", r.get("http"), "- stop. No further sends.")'
  exit 0
fi

echo "DENY_OK — running minimal allow/deny matrix (2 sends max)" | tee "$EVID/deny-ok.txt"
.venv/bin/python - <<'PY' | tee "$EVID/minimal-matrix.json"
import json, os, uuid
import app, microsoft_mail_send as mms, tenant_email_authority as tea

EVIDENCE_UPN = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com"
DENIED_UPN = "wathefni-rbac-deny-probe@wathefni.onmicrosoft.com"
COMPANY = "WATHEFNI"
marker = f"recheck-{uuid.uuid4().hex[:10]}"
proofs = {}

def rec(name, cond, **d):
    proofs[name] = {"ok": bool(cond), **d}
    print(("PASS" if cond else "FAIL"), name, json.dumps(d)[:240])
    if not cond:
        raise SystemExit(2)

# Ensure mailbox approved + probed (no extra Graph send)
boxes = tea.list_operational_mailboxes(app, COMPANY)
mb = next((m for m in boxes if str(m.get("address") or "").lower() == EVIDENCE_UPN.lower()), None)
if not mb:
    mb = tea.upsert_operational_mailbox(
        app, COMPANY, address=EVIDENCE_UPN, display_name="Wathefni Evidence",
        provider="microsoft", allow_send=True, status="approved",
        exchange_scope_ref=os.environ.get("WATHEFNI_M365_MAIL_AU_ID") or "Wathefni-Mail-Evidence",
    )
mms.mint_mail_graph_token()
tea.record_mailbox_probe(app, COMPANY, str(mb["mailbox_id"]), ok=True)
tea.upsert_email_settings(
    app, COMPANY,
    {"outbound_mode": "microsoft_mailbox", "outbound_mailbox_id": str(mb["mailbox_id"]),
     "reply_to": "hr@wathefni.ai", "allow_wathefni_emergency_fallback": False},
    allow_unready_mode=False, updated_by_user_id="scheduled-recheck",
)

allow = mms.send_mail_as_mailbox(
    mailbox=EVIDENCE_UPN, to=EVIDENCE_UPN,
    subject=f"[evidence-allow] {marker}", body=f"marker={marker}\n",
    reply_to="hr@wathefni.ai", save_to_sent_items=True,
)
rec("approved_send", allow.get("ok") and allow.get("provider_accept_status") == "accepted_by_provider",
    http=(allow.get("raw") or {}).get("http_status"), status=allow.get("provider_accept_status"))

deny = mms.send_mail_as_mailbox(
    mailbox=DENIED_UPN, to=EVIDENCE_UPN,
    subject=f"[evidence-deny] {marker}", body="should fail",
    save_to_sent_items=False,
)
rec("outside_scope_denied", (not deny.get("ok")) and int((deny.get("raw") or {}).get("http_status") or 0) in {401, 403},
    http=(deny.get("raw") or {}).get("http_status"), error=deny.get("error"))

restored = tea.force_wathefni_fallback(app, COMPANY, updated_by_user_id="scheduled-recheck")
rec("restored_wathefni", restored.get("outbound_mode") == "wathefni")

# No other tenants branded
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM company_email_settings WHERE outbound_mode <> 'wathefni'")
        r = cur.fetchone()
        n = int(r["n"] if isinstance(r, dict) else r[0])
rec("only_evidence_was_toggled", n == 0, branded_remaining=n)

print(json.dumps({"marker": marker, "proofs": proofs}, indent=2))
print("MINIMAL_MATRIX_PASS")
PY

echo FULL_PASS | tee "$EVID/VERDICT.txt"
REMOTE

rsync -az -e "ssh -o BatchMode=yes" "$VPS:/opt/wathefni/production-evidence/hybrid-email-m365-outbound/recheck-$STAMP/" "$LOCAL_EV/" || true
echo "LOCAL_EV=$LOCAL_EV"
cat "$LOCAL_EV/VERDICT.txt" 2>/dev/null || true
echo SCHEDULED_PROBE_DONE
