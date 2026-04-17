#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=${0:A:h}
PROJECT_DIR=${SCRIPT_DIR:h}
set -a
source "$PROJECT_DIR/.env"
set +a

FORCE=false
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=true ;;
  esac
done

PROFILE_NAME="${OPENCLAW_PROFILE:-delivery}"
PROFILE_DIR="$HOME/.openclaw-${PROFILE_NAME}"
CONFIG_PATH="$PROFILE_DIR/openclaw.json"
TEMPLATE_PATH="$PROJECT_DIR/openclaw.template.json"

mkdir -p "$PROFILE_DIR"

if [ -f "$CONFIG_PATH" ] && ! $FORCE; then
  echo "Delivery profile already exists at $CONFIG_PATH"
  exit 0
fi

TOKEN="${OPENCLAW_GATEWAY_TOKEN:-}"
if [ -f "$CONFIG_PATH" ] && [ -z "$TOKEN" ]; then
TOKEN="$(CONFIG_PATH="$CONFIG_PATH" python3 - <<'PY'
import json
import os
from pathlib import Path

config_path = Path(os.environ['CONFIG_PATH'])
try:
    config = json.loads(config_path.read_text())
except Exception:
    print('')
    raise SystemExit
token = (((config.get('gateway') or {}).get('auth') or {}).get('token') or '').strip()
print(token)
PY
)"
fi

if [ -z "$TOKEN" ] || [ "$TOKEN" = "CHANGE_ME_DELIVERY_TOKEN" ]; then
TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(24))
PY
)"
fi

TEMPLATE_PATH="$TEMPLATE_PATH" PROFILE_NAME="$PROFILE_NAME" DELIVERY_TOKEN="$TOKEN" \
RIDERS_PRICING_SOURCE_MODE="${RIDERS_PRICING_SOURCE_MODE:-}" \
RIDERS_PRICING_PUBLISHED_PATH="${RIDERS_PRICING_PUBLISHED_PATH:-}" \
RIDERS_PRICING_RESOLVER_OVERLAY_PATH="${RIDERS_PRICING_RESOLVER_OVERLAY_PATH:-}" \
RIDERS_PRICING_SHEET_ID="${RIDERS_PRICING_SHEET_ID:-}" \
RIDERS_PRICING_SHEET_NAME="${RIDERS_PRICING_SHEET_NAME:-}" \
RIDERS_PRICING_SHEET_HEADER_ROW="${RIDERS_PRICING_SHEET_HEADER_ROW:-}" \
RIDERS_BEHAVIOR_POLICY_PUBLISHED_PATH="${RIDERS_BEHAVIOR_POLICY_PUBLISHED_PATH:-}" \
python3 - <<'PY'
from pathlib import Path
import json
import os

template_path = Path(os.environ['TEMPLATE_PATH'])
profile_name = os.environ['PROFILE_NAME']
config_path = Path.home() / f'.openclaw-{profile_name}' / 'openclaw.json'
existed = config_path.exists()
config = json.loads(template_path.read_text())
config['gateway']['auth']['token'] = os.environ['DELIVERY_TOKEN']

entries = (((config.setdefault('plugins', {})).setdefault('entries', {})))
riders_tools = entries.setdefault('riders-tools', {})
riders_tools['enabled'] = True
riders_tools_config = riders_tools.setdefault('config', {})
riders_tools_pricing = riders_tools_config.setdefault('pricing', {})
riders_tools_pricing['sourceMode'] = (
    os.environ.get('RIDERS_PRICING_SOURCE_MODE', '').strip() or 'published_preferred'
)
riders_tools_pricing['publishedPath'] = (
    os.environ.get('RIDERS_PRICING_PUBLISHED_PATH', '').strip()
    or '/Users/azizalmulla/Desktop/claw/delivery/workspaces/riders/data/pricing.published.json'
)
riders_tools_pricing['resolverOverlayPath'] = (
    os.environ.get('RIDERS_PRICING_RESOLVER_OVERLAY_PATH', '').strip()
    or '/Users/azizalmulla/Desktop/claw/delivery/workspaces/riders/data/pricing.resolver.overlay.json'
)
riders_tools_pricing.setdefault('adminAllowlist', [])
riders_tools_google_sheet = riders_tools_pricing.setdefault('googleSheet', {})
if os.environ.get('RIDERS_PRICING_SHEET_ID', '').strip():
    riders_tools_google_sheet['spreadsheetId'] = os.environ['RIDERS_PRICING_SHEET_ID'].strip()
if os.environ.get('RIDERS_PRICING_SHEET_NAME', '').strip():
    riders_tools_google_sheet['sheetName'] = os.environ['RIDERS_PRICING_SHEET_NAME'].strip()
if os.environ.get('RIDERS_PRICING_SHEET_HEADER_ROW', '').strip():
    riders_tools_google_sheet['headerRow'] = int(os.environ['RIDERS_PRICING_SHEET_HEADER_ROW'])

riders_tools_behavior = riders_tools_config.setdefault('behavior', {})
riders_tools_behavior['publishedPath'] = (
    os.environ.get('RIDERS_BEHAVIOR_POLICY_PUBLISHED_PATH', '').strip()
    or '/Users/azizalmulla/Desktop/claw/delivery/workspaces/riders/data/behavior-policy.published.json'
)
riders_tools_behavior.setdefault('adminAllowlist', [])

config_path.write_text(json.dumps(config, indent=2) + '\n')
print(f'{"Updated" if existed else "Created"} {config_path}')
print(f'Delivery gateway token: {os.environ["DELIVERY_TOKEN"]}')
PY
