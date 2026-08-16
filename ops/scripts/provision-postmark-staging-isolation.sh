#!/usr/bin/env bash
# Create a dedicated Postmark staging inbound server WITHOUT touching production server 19430066.
set -euo pipefail
PROD_SERVER_ID=19430066
ACCOUNT_ENV=/root/.openclaw/secrets/wathefni-postmark-account.staging.env
STAGING_PM_ENV=/root/.openclaw/secrets/wathefni-postmark.staging.env
INTAKE_ENV=/root/.openclaw/secrets/wathefni-intake.staging.env
EVIDENCE_ROOT=/opt/wathefni/staging/staging-evidence/postmark-staging-isolation

if [[ ! -f "$ACCOUNT_ENV" ]]; then
  echo "MISSING: $ACCOUNT_ENV" >&2
  echo "Create it with: WATHEFNI_POSTMARK_ACCOUNT_TOKEN=... (Account API token, not Server token)" >&2
  exit 2
fi
set -a; source "$ACCOUNT_ENV"; set +a
: "${WATHEFNI_POSTMARK_ACCOUNT_TOKEN:?}"

STAGING_SECRET=$(grep '^WATHEFNI_POSTMARK_INBOUND_SECRET=' "$INTAKE_ENV" | cut -d= -f2-)
: "${STAGING_SECRET:?}"

WEBHOOK_URL="https://wathefni:${STAGING_SECRET}@api.wathefni.ai/webhook/postmark-staging/inbound"

TS=$(date -u +%Y%m%dT%H%M%SZ)
EVIDENCE="$EVIDENCE_ROOT/$TS-provision"
mkdir -p "$EVIDENCE"

PROD_TOKEN=$(grep '^WATHEFNI_POSTMARK_SERVER_TOKEN=' /root/.openclaw/secrets/postgres.env | cut -d= -f2-)
curl -fsS -H "Accept: application/json" -H "X-Postmark-Server-Token: $PROD_TOKEN" \
  https://api.postmarkapp.com/server > "$EVIDENCE/production_server.before.json"
python3 -c "import json; d=json.load(open('$EVIDENCE/production_server.before.json')); assert d.get('ID')==$PROD_SERVER_ID"

CREATE_BODY=$(WEBHOOK_URL="$WEBHOOK_URL" python3 - <<'PY'
import json, os
print(json.dumps({
  "Name": "wathefni-staging-ingress",
  "Color": "blue",
  "SmtpApiActivated": False,
  "RawEmailEnabled": False,
  "DeliveryType": "Live",
  "InboundHookUrl": os.environ["WEBHOOK_URL"],
  "BounceHookUrl": "",
  "OpenHookUrl": "",
  "DeliveryHookUrl": "",
  "ClickHookUrl": "",
  "PostFirstOpenOnly": False,
  "IncludeBounceContentInHook": False,
  "EnableSmtpApiErrorHooks": False,
}))
PY
)

curl -fsS -X POST "https://api.postmarkapp.com/servers" \
  -H "Accept: application/json" -H "Content-Type: application/json" \
  -H "X-Postmark-Account-Token: $WATHEFNI_POSTMARK_ACCOUNT_TOKEN" \
  -d "$CREATE_BODY" > "$EVIDENCE/staging_server.created.json"

python3 - <<PY
import json, os
from pathlib import Path
evidence=Path("$EVIDENCE")
d=json.loads((evidence/"staging_server.created.json").read_text())
assert d.get("ID") != $PROD_SERVER_ID
assert "postmark-staging" in (d.get("InboundHookUrl") or "")
token=None
toks=d.get("ApiTokens") or []
if toks and isinstance(toks[0], str):
  token=toks[0]
elif toks and isinstance(toks[0], dict):
  token=toks[0].get("Token") or toks[0].get("ServerToken")
summary={
  "ID": d.get("ID"),
  "Name": d.get("Name"),
  "InboundHash": d.get("InboundHash"),
  "InboundDomain": d.get("InboundDomain"),
  "InboundAddress": d.get("InboundAddress"),
  "InboundHookUrl_has_staging_path": "postmark-staging" in (d.get("InboundHookUrl") or ""),
}
(evidence/"staging_server.summary.json").write_text(json.dumps(summary, indent=2)+"\n")
print(json.dumps(summary, indent=2))
if token:
  Path("$STAGING_PM_ENV").write_text(
    "# Staging-only Postmark server credentials. DO NOT put production tokens here.\n"
    f"WATHEFNI_POSTMARK_STAGING_SERVER_ID={d.get('ID')}\n"
    f"WATHEFNI_POSTMARK_STAGING_SERVER_TOKEN={token}\n"
    f"WATHEFNI_POSTMARK_STAGING_INBOUND_HASH={d.get('InboundHash')}\n"
    f"WATHEFNI_POSTMARK_STAGING_INBOUND_ADDRESS={d.get('InboundAddress')}\n"
  )
  os.chmod("$STAGING_PM_ENV", 0o600)
  print("wrote_env", True)
else:
  print("wrote_env", False)
PY

if [[ ! -f "$STAGING_PM_ENV" ]]; then
  SID=$(python3 -c "import json;print(json.load(open('$EVIDENCE/staging_server.created.json'))['ID'])")
  curl -fsS -H "Accept: application/json" -H "X-Postmark-Account-Token: $WATHEFNI_POSTMARK_ACCOUNT_TOKEN" \
    "https://api.postmarkapp.com/servers/$SID" > "$EVIDENCE/staging_server.get.json"
  python3 - <<PY
import json, os
from pathlib import Path
d=json.loads(Path("$EVIDENCE/staging_server.get.json").read_text())
assert d.get("ID") != $PROD_SERVER_ID
token=None
toks=d.get("ApiTokens") or []
if toks and isinstance(toks[0], str): token=toks[0]
elif toks and isinstance(toks[0], dict): token=toks[0].get("Token") or toks[0].get("ServerToken")
assert token, "no server token available"
Path("$STAGING_PM_ENV").write_text(
  "# Staging-only Postmark server credentials. DO NOT put production tokens here.\n"
  f"WATHEFNI_POSTMARK_STAGING_SERVER_ID={d.get('ID')}\n"
  f"WATHEFNI_POSTMARK_STAGING_SERVER_TOKEN={token}\n"
  f"WATHEFNI_POSTMARK_STAGING_INBOUND_HASH={d.get('InboundHash')}\n"
  f"WATHEFNI_POSTMARK_STAGING_INBOUND_ADDRESS={d.get('InboundAddress')}\n"
)
os.chmod("$STAGING_PM_ENV", 0o600)
print("wrote", "$STAGING_PM_ENV")
PY
fi

curl -fsS -H "Accept: application/json" -H "X-Postmark-Server-Token: $PROD_TOKEN" \
  https://api.postmarkapp.com/server > "$EVIDENCE/production_server.after.json"
python3 - <<PY
from pathlib import Path
b=Path("$EVIDENCE/production_server.before.json").read_bytes()
a=Path("$EVIDENCE/production_server.after.json").read_bytes()
assert b==a, "PRODUCTION POSTMARK SERVER MUTATED"
print("production_postmark_unchanged_byte_for_byte")
PY
echo "OK evidence=$EVIDENCE"
