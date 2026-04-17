#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────────
# provision-company.sh — Create a new company workspace for the Workforce OS
#
# Usage:
#   ./provision-company.sh \
#     --company-code "ALMULLA" \
#     --company-name "Al Mulla Group" \
#     --company-name-ar "مجموعة الملا" \
#     --whatsapp-number "+96512345678" \
#     --hr-phones "+96599001122,+96599003344" \
#     --hr-names "Sara Al Rashid,Mohammed Ali" \
#     --hr-emails "sara@almulla.com,mohammed@almulla.com" \
#     --hr-roles "manager,admin" \
#     --google-account "almulla-hr@gmail.com" \
#     --modules "hiring,onboarding,compliance" \
#     --country "KW" \
#     --sector "General Trading"
#
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$(cd "$SCRIPT_DIR/../templates" && pwd)"
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"

# ─── Defaults ─────────────────────────────────────────────────────────────────
COMPANY_CODE=""
COMPANY_NAME=""
COMPANY_NAME_AR=""
WHATSAPP_NUMBER=""
HR_PHONES=""
HR_NAMES=""
HR_EMAILS=""
HR_ROLES=""
GOOGLE_ACCOUNT=""
MODULES="hiring"
COUNTRY_CODE="KW"
SECTOR=""
DRY_RUN=false

# ─── Parse Arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --company-code)    COMPANY_CODE="$2"; shift 2 ;;
    --company-name)    COMPANY_NAME="$2"; shift 2 ;;
    --company-name-ar) COMPANY_NAME_AR="$2"; shift 2 ;;
    --whatsapp-number) WHATSAPP_NUMBER="$2"; shift 2 ;;
    --hr-phones)       HR_PHONES="$2"; shift 2 ;;
    --hr-names)        HR_NAMES="$2"; shift 2 ;;
    --hr-emails)       HR_EMAILS="$2"; shift 2 ;;
    --hr-roles)        HR_ROLES="$2"; shift 2 ;;
    --google-account)  GOOGLE_ACCOUNT="$2"; shift 2 ;;
    --modules)         MODULES="$2"; shift 2 ;;
    --country)         COUNTRY_CODE="$2"; shift 2 ;;
    --sector)          SECTOR="$2"; shift 2 ;;
    --dry-run)         DRY_RUN=true; shift ;;
    --help)
      echo "Usage: $0 --company-code CODE --company-name NAME --whatsapp-number +965... --hr-phones +965...,+965... --hr-names Name1,Name2 --google-account email --modules hiring,onboarding,compliance"
      exit 0
      ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

# ─── Validate Required Args ──────────────────────────────────────────────────
missing=()
[[ -z "$COMPANY_CODE" ]]    && missing+=("--company-code")
[[ -z "$COMPANY_NAME" ]]    && missing+=("--company-name")
[[ -z "$WHATSAPP_NUMBER" ]] && missing+=("--whatsapp-number")
[[ -z "$HR_PHONES" ]]       && missing+=("--hr-phones")
[[ -z "$HR_NAMES" ]]        && missing+=("--hr-names")
[[ -z "$GOOGLE_ACCOUNT" ]]  && missing+=("--google-account")

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "❌ Missing required arguments: ${missing[*]}"
  echo "Run $0 --help for usage."
  exit 1
fi

# ─── Derived Values ───────────────────────────────────────────────────────────
COMPANY_CODE_LOWER="$(echo "$COMPANY_CODE" | tr '[:upper:]' '[:lower:]')"
AGENT_ID="${COMPANY_CODE_LOWER}-hr"
WORKSPACE_DIR="$OPENCLAW_HOME/workspaces/company-${COMPANY_CODE_LOWER}"
WHATSAPP_NUMBER_PLAIN="$(echo "$WHATSAPP_NUMBER" | sed 's/+//')"
TODAY="$(date +%Y-%m-%d)"

# Parse comma-separated HR fields into arrays
IFS=',' read -ra PHONE_ARR <<< "$HR_PHONES"
IFS=',' read -ra NAME_ARR  <<< "$HR_NAMES"
IFS=',' read -ra EMAIL_ARR <<< "${HR_EMAILS:-}"
IFS=',' read -ra ROLE_ARR  <<< "${HR_ROLES:-}"

PRIMARY_HR_NAME="${NAME_ARR[0]}"
PRIMARY_HR_PHONE="${PHONE_ARR[0]}"
PRIMARY_HR_EMAIL="${EMAIL_ARR[0]:-}"
PRIMARY_HR_ROLE="${ROLE_ARR[0]:-HR Manager}"

# Parse modules
IFS=',' read -ra MODULE_ARR <<< "$MODULES"
HAS_HIRING=false
HAS_ONBOARDING=false
HAS_COMPLIANCE=false
for mod in "${MODULE_ARR[@]}"; do
  case "$(echo "$mod" | tr '[:upper:]' '[:lower:]' | xargs)" in
    hiring)     HAS_HIRING=true ;;
    onboarding) HAS_ONBOARDING=true ;;
    compliance|pro) HAS_COMPLIANCE=true ;;
  esac
done

# ─── Module description text ─────────────────────────────────────────────────
MODULE_DESC_PARTS=()
$HAS_HIRING     && MODULE_DESC_PARTS+=("screen candidates and manage hiring")
$HAS_ONBOARDING && MODULE_DESC_PARTS+=("onboard new employees")
$HAS_COMPLIANCE && MODULE_DESC_PARTS+=("track document compliance and PRO operations")
MODULE_DESCRIPTION="$(IFS=', '; echo "${MODULE_DESC_PARTS[*]}")"

HR_SCOPE_PARTS=()
$HAS_HIRING     && HR_SCOPE_PARTS+=("candidates, positions, interviews, assessments")
$HAS_ONBOARDING && HR_SCOPE_PARTS+=("onboarding, employee setup")
$HAS_COMPLIANCE && HR_SCOPE_PARTS+=("document compliance, renewals, PRO operations")
HR_SCOPE="$(IFS=', '; echo "${HR_SCOPE_PARTS[*]}")"

# Build modules JSON array
MODULES_JSON="["
first=true
for mod in "${MODULE_ARR[@]}"; do
  $first || MODULES_JSON+=","
  MODULES_JSON+="\"$(echo "$mod" | xargs)\""
  first=false
done
MODULES_JSON+="]"

MODULES_LIST="$(IFS=', '; echo "${MODULE_ARR[*]}")"

# Build HR users JSON block
HR_USERS_JSON=""
for i in "${!PHONE_ARR[@]}"; do
  [[ $i -gt 0 ]] && HR_USERS_JSON+=","$'\n'
  phone="${PHONE_ARR[$i]}"
  name="${NAME_ARR[$i]:-User $((i+1))}"
  email="${EMAIL_ARR[$i]:-}"
  role="${ROLE_ARR[$i]:-manager}"
  HR_USERS_JSON+="    {\"phone\": \"$phone\", \"name\": \"$name\", \"email\": \"$email\", \"role\": \"$role\"}"
done

# Build HR users block for TOOLS.md
HR_USERS_BLOCK=""
for i in "${!PHONE_ARR[@]}"; do
  name="${NAME_ARR[$i]:-User $((i+1))}"
  phone="${PHONE_ARR[$i]}"
  role="${ROLE_ARR[$i]:-manager}"
  HR_USERS_BLOCK+="- $name ($phone) — $role"$'\n'
done

# Build modules block for AGENTS.md / TOOLS.md
MODULES_BLOCK=""
$HAS_HIRING     && MODULES_BLOCK+="- **Module 1: Hiring** — Job posting, QR intake, CV screening, interviews, assessments"$'\n'
$HAS_ONBOARDING && MODULES_BLOCK+="- **Module 2: Onboarding** — Post-hire document collection, checklists, Drive upload"$'\n'
$HAS_COMPLIANCE && MODULES_BLOCK+="- **Module 3: PRO/Compliance** — Document expiry tracking, renewal reminders, compliance alerts"$'\n'

# Build HR allowed actions for IDENTITY.md
HR_ALLOWED_ACTIONS=""
$HAS_HIRING     && HR_ALLOWED_ACTIONS+="- Search/filter/rank candidates
- Shortlist, reject, hire, or offer
- Schedule interviews and send invites
- Add/edit positions and screening questions
- View/update the Google Sheet dashboard
- Check emails for applications
- Generate QR codes or apply links
- Trigger assessments and review results
"
$HAS_ONBOARDING && HR_ALLOWED_ACTIONS+="- Hire and onboard candidates
- Check onboarding status and send reminders
- Add employees manually
"
$HAS_COMPLIANCE && HR_ALLOWED_ACTIONS+="- View expiring documents and compliance reports
- Update document expiry dates after renewal
- Request documents from employees
- Schedule PACI/MOI/medical appointments
- Offboard employees
- Add employees manually (not from hiring flow)
"

# ─── Print Summary ────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           WhatsApp Workforce OS — Company Provisioning      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Company:     $COMPANY_NAME ($COMPANY_CODE)"
echo "  Agent ID:    $AGENT_ID"
echo "  WhatsApp:    $WHATSAPP_NUMBER"
echo "  Country:     $COUNTRY_CODE"
echo "  Modules:     $MODULES_LIST"
echo "  HR Users:    ${#PHONE_ARR[@]}"
echo "  Google:      $GOOGLE_ACCOUNT"
echo "  Workspace:   $WORKSPACE_DIR"
echo ""

if $DRY_RUN; then
  echo "🔍 DRY RUN — no files will be created."
  echo ""
  exit 0
fi

# ─── Check if workspace already exists ────────────────────────────────────────
if [[ -d "$WORKSPACE_DIR" ]]; then
  echo "⚠️  Workspace already exists at $WORKSPACE_DIR"
  read -rp "   Overwrite? (y/N): " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }
fi

# ─── Template substitution function ──────────────────────────────────────────
render_template() {
  local input="$1"
  local output="$2"

  local content
  content="$(cat "$input")"

  # Simple variable substitution
  content="${content//\{\{COMPANY_CODE\}\}/$COMPANY_CODE}"
  content="${content//\{\{COMPANY_NAME\}\}/$COMPANY_NAME}"
  content="${content//\{\{COMPANY_NAME_AR\}\}/$COMPANY_NAME_AR}"
  content="${content//\{\{COMPANY_CODE_LOWER\}\}/$COMPANY_CODE_LOWER}"
  content="${content//\{\{WHATSAPP_NUMBER\}\}/$WHATSAPP_NUMBER}"
  content="${content//\{\{WHATSAPP_NUMBER_PLAIN\}\}/$WHATSAPP_NUMBER_PLAIN}"
  content="${content//\{\{GOOGLE_ACCOUNT\}\}/$GOOGLE_ACCOUNT}"
  content="${content//\{\{COUNTRY_CODE\}\}/$COUNTRY_CODE}"
  content="${content//\{\{SECTOR\}\}/$SECTOR}"
  content="${content//\{\{TODAY\}\}/$TODAY}"
  content="${content//\{\{AGENT_ID\}\}/$AGENT_ID}"
  content="${content//\{\{WORKSPACE_PATH\}\}/$WORKSPACE_DIR}"
  content="${content//\{\{PRIMARY_HR_NAME\}\}/$PRIMARY_HR_NAME}"
  content="${content//\{\{PRIMARY_HR_PHONE\}\}/$PRIMARY_HR_PHONE}"
  content="${content//\{\{PRIMARY_HR_EMAIL\}\}/$PRIMARY_HR_EMAIL}"
  content="${content//\{\{PRIMARY_HR_ROLE\}\}/$PRIMARY_HR_ROLE}"
  content="${content//\{\{MODULE_DESCRIPTION\}\}/$MODULE_DESCRIPTION}"
  content="${content//\{\{HR_SCOPE\}\}/$HR_SCOPE}"
  content="${content//\{\{MODULES_JSON\}\}/$MODULES_JSON}"
  content="${content//\{\{MODULES_LIST\}\}/$MODULES_LIST}"
  content="${content//\{\{MODULES_BLOCK\}\}/$MODULES_BLOCK}"
  content="${content//\{\{HR_USERS_JSON\}\}/$HR_USERS_JSON}"
  content="${content//\{\{HR_USERS_BLOCK\}\}/$HR_USERS_BLOCK}"
  content="${content//\{\{HR_ALLOWED_ACTIONS\}\}/$HR_ALLOWED_ACTIONS}"

  # Placeholders that will be filled after Google resources are created
  content="${content//\{\{SHEET_ID\}\}/PENDING_SHEET_ID}"
  content="${content//\{\{DRIVE_FOLDER_ID\}\}/PENDING_DRIVE_FOLDER_ID}"

  # User context
  local user_context="$PRIMARY_HR_NAME is the primary HR contact at $COMPANY_NAME. When they ask questions, respond in HR mode with data-driven answers."
  content="${content//\{\{USER_CONTEXT\}\}/$user_context}"

  # Module conditional sections
  if $HAS_HIRING; then
    content="$(echo "$content" | sed 's/{{#MODULE_HIRING}}//g; s/{{\/MODULE_HIRING}}//g')"
  else
    content="$(echo "$content" | perl -0pe 's/\{\{#MODULE_HIRING\}\}.*?\{\{\/MODULE_HIRING\}\}//gs')"
  fi

  if $HAS_ONBOARDING; then
    content="$(echo "$content" | sed 's/{{#MODULE_ONBOARDING}}//g; s/{{\/MODULE_ONBOARDING}}//g')"
  else
    content="$(echo "$content" | perl -0pe 's/\{\{#MODULE_ONBOARDING\}\}.*?\{\{\/MODULE_ONBOARDING\}\}//gs')"
  fi

  if $HAS_COMPLIANCE; then
    content="$(echo "$content" | sed 's/{{#MODULE_COMPLIANCE}}//g; s/{{\/MODULE_COMPLIANCE}}//g')"
  else
    content="$(echo "$content" | perl -0pe 's/\{\{#MODULE_COMPLIANCE\}\}.*?\{\{\/MODULE_COMPLIANCE\}\}//gs')"
  fi

  echo "$content" > "$output"
}

# ─── Create Directory Structure ───────────────────────────────────────────────
echo "📁 Creating workspace directories..."
mkdir -p "$WORKSPACE_DIR"/{data/companies/"$COMPANY_CODE"/{positions,sync-queue},data/candidates,memory,.openclaw}

$HAS_ONBOARDING && mkdir -p "$WORKSPACE_DIR/data/companies/$COMPANY_CODE"/{employees,onboarding-templates}
$HAS_COMPLIANCE && mkdir -p "$WORKSPACE_DIR/data/companies/$COMPANY_CODE"/employees

# ─── Render Workspace Templates ──────────────────────────────────────────────
echo "📝 Rendering workspace templates..."
for tmpl in "$TEMPLATE_DIR/workspace/"*.tmpl; do
  filename="$(basename "$tmpl" .tmpl)"
  render_template "$tmpl" "$WORKSPACE_DIR/$filename"
  echo "   ✓ $filename"
done

# ─── Render Data Templates ───────────────────────────────────────────────────
echo "📦 Rendering data files..."
render_template "$TEMPLATE_DIR/data/company.json.tmpl" \
  "$WORKSPACE_DIR/data/companies/$COMPANY_CODE/company.json"
echo "   ✓ company.json"

render_template "$TEMPLATE_DIR/data/hr-users.json.tmpl" \
  "$WORKSPACE_DIR/data/companies/$COMPANY_CODE/hr-users.json"
echo "   ✓ hr-users.json"

# ─── Copy Compliance Rules ───────────────────────────────────────────────────
if $HAS_COMPLIANCE; then
  rules_file="$TEMPLATE_DIR/data/compliance-rules/${COUNTRY_CODE}.json"
  if [[ -f "$rules_file" ]]; then
    cp "$rules_file" "$WORKSPACE_DIR/data/companies/$COMPANY_CODE/compliance-rules.json"
    echo "   ✓ compliance-rules.json ($COUNTRY_CODE)"
  else
    echo "   ⚠️  No compliance rules found for $COUNTRY_CODE — create manually"
  fi
fi

# ─── Copy Onboarding Templates ───────────────────────────────────────────────
if $HAS_ONBOARDING; then
  cp "$TEMPLATE_DIR/data/onboarding-templates/default.json" \
    "$WORKSPACE_DIR/data/companies/$COMPANY_CODE/onboarding-templates/default.json"
  echo "   ✓ onboarding template (default)"
fi

# ─── Generate OpenClaw Config Snippet ─────────────────────────────────────────
CONFIG_SNIPPET="$WORKSPACE_DIR/.openclaw/agent-config.json"
cat > "$CONFIG_SNIPPET" << EOF
{
  "_comment": "Add this agent to openclaw.json agents.list and add the binding",
  "agent": {
    "id": "$AGENT_ID",
    "name": "$COMPANY_NAME HR",
    "workspace": "$WORKSPACE_DIR",
    "model": {
      "primary": "anthropic/claude-sonnet-4-6"
    }
  },
  "binding": {
    "match": {
      "channel": "whatsapp",
      "accountId": "${COMPANY_CODE_LOWER}-wa"
    },
    "agentId": "$AGENT_ID"
  },
  "whatsapp_allowFrom": [
$(for phone in "${PHONE_ARR[@]}"; do echo "    \"$phone\","; done)
    "*"
  ]
}
EOF
echo "   ✓ agent-config.json (snippet for openclaw.json)"

# ─── Generate Cron Job Snippets ──────────────────────────────────────────────
if $HAS_COMPLIANCE; then
  cat > "$WORKSPACE_DIR/.openclaw/compliance-cron.json" << EOF
{
  "_comment": "Add via: openclaw cron add --agent $AGENT_ID ...",
  "name": "compliance-check-${COMPANY_CODE_LOWER}",
  "schedule": { "kind": "cron", "expr": "0 8 * * *", "tz": "Asia/Kuwait" },
  "sessionTarget": "isolated",
  "agentId": "$AGENT_ID",
  "payload": {
    "kind": "agentTurn",
    "message": "Run daily compliance check. Read all employee documents in data/companies/$COMPANY_CODE/employees/*/documents/. Check expiry dates against compliance-rules.json. Send reminders per escalation rules. Update the Compliance tab in Google Sheet. Report summary to HR at $PRIMARY_HR_PHONE."
  },
  "delivery": {
    "mode": "announce",
    "channel": "whatsapp",
    "to": "$PRIMARY_HR_PHONE"
  }
}
EOF
  echo "   ✓ compliance-cron.json"
fi

if $HAS_ONBOARDING; then
  cat > "$WORKSPACE_DIR/.openclaw/onboarding-cron.json" << EOF
{
  "_comment": "Add via: openclaw cron add --agent $AGENT_ID ...",
  "name": "onboarding-followup-${COMPANY_CODE_LOWER}",
  "schedule": { "kind": "cron", "expr": "0 10 * * *", "tz": "Asia/Kuwait" },
  "sessionTarget": "isolated",
  "agentId": "$AGENT_ID",
  "payload": {
    "kind": "agentTurn",
    "message": "Check all employees with onboarding status in_progress in data/companies/$COMPANY_CODE/employees/. For any missing documents not reminded in 24h, send a WhatsApp reminder to the employee. Report summary to HR at $PRIMARY_HR_PHONE."
  },
  "delivery": {
    "mode": "announce",
    "channel": "whatsapp",
    "to": "$PRIMARY_HR_PHONE"
  }
}
EOF
  echo "   ✓ onboarding-cron.json"
fi

# ─── Post-Provisioning Checklist ─────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    ✅ Workspace Created!                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "📋 Post-provisioning checklist:"
echo ""
echo "  1. CREATE Google Sheet for $COMPANY_NAME:"
echo "     gog sheets create \"$COMPANY_NAME - HR Dashboard\" --account $GOOGLE_ACCOUNT"
echo "     → Update SHEET_ID in TOOLS.md and MEMORY.md"
echo ""
echo "  2. CREATE Google Drive folder:"
echo "     gog drive mkdir \"$COMPANY_NAME - HR Docs\" --account $GOOGLE_ACCOUNT"
echo "     → Update DRIVE_FOLDER_ID in TOOLS.md and IDENTITY.md"
echo ""
echo "  3. ADD agent to openclaw.json:"
echo "     See: $CONFIG_SNIPPET"
echo ""
echo "  4. PAIR WhatsApp number $WHATSAPP_NUMBER:"
echo "     openclaw channels whatsapp pair --account ${COMPANY_CODE_LOWER}-wa"
echo ""
if $HAS_COMPLIANCE; then
echo "  5. ADD compliance cron job:"
echo "     See: $WORKSPACE_DIR/.openclaw/compliance-cron.json"
echo ""
fi
if $HAS_ONBOARDING; then
echo "  6. ADD onboarding cron job:"
echo "     See: $WORKSPACE_DIR/.openclaw/onboarding-cron.json"
echo ""
fi
echo "  7. RESTART Gateway:"
echo "     openclaw gateway restart"
echo ""
echo "Done! 🎉 $COMPANY_NAME is ready to go."
