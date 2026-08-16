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
#     --modules "hiring,onboarding,compliance,shifts,attendance,leave,payroll,analytics" \
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
      echo "Usage: $0 --company-code CODE --company-name NAME --whatsapp-number +965... --hr-phones +965...,+965... --hr-names Name1,Name2 --google-account email --modules hiring,onboarding,compliance,shifts,attendance,leave,payroll,analytics"
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
HAS_SHIFTS=false
HAS_ATTENDANCE=false
HAS_LEAVE=false
HAS_PAYROLL=false
HAS_ANALYTICS=false
for mod in "${MODULE_ARR[@]}"; do
  case "$(echo "$mod" | tr '[:upper:]' '[:lower:]' | xargs)" in
    hiring|pre_hiring|pre-hiring|recruiting) HAS_HIRING=true ;;
    onboarding|post_hiring|post-hiring)      HAS_ONBOARDING=true ;;
    compliance|pro)                          HAS_COMPLIANCE=true ;;
    shifts|shift|shifting|scheduling)        HAS_SHIFTS=true ;;
    attendance|attendence|time_tracking|time-tracking|timekeeping|checkin|check-in) HAS_ATTENDANCE=true ;;
    leave|time_off|time-off|vacation)        HAS_LEAVE=true ;;
    payroll|payroll_hours|payroll-hours|timesheet|time_sheet|time-sheet) HAS_PAYROLL=true ;;
    analytics|insights|dashboard|reports)     HAS_ANALYTICS=true ;;
  esac
done

# ─── Module description text ─────────────────────────────────────────────────
MODULE_DESC_PARTS=()
$HAS_HIRING     && MODULE_DESC_PARTS+=("screen candidates and manage hiring")
$HAS_ONBOARDING && MODULE_DESC_PARTS+=("onboard new employees")
$HAS_COMPLIANCE && MODULE_DESC_PARTS+=("track document compliance and PRO operations")
$HAS_SHIFTS     && MODULE_DESC_PARTS+=("manage employee shifts, coverage, availability, and shift swaps")
$HAS_ATTENDANCE && MODULE_DESC_PARTS+=("track attendance, lateness, absences, and check-ins")
$HAS_LEAVE      && MODULE_DESC_PARTS+=("manage employee leave and time off")
$HAS_PAYROLL    && MODULE_DESC_PARTS+=("calculate payroll-ready working hours, policy previews, and locked payroll exports")
$HAS_ANALYTICS  && MODULE_DESC_PARTS+=("answer workforce analytics and operational performance questions")
MODULE_DESC_PARTS+=("enforce branch, team, and manager scope when configured")
MODULE_DESCRIPTION="$(IFS=', '; echo "${MODULE_DESC_PARTS[*]}")"

HR_SCOPE_PARTS=()
$HAS_HIRING     && HR_SCOPE_PARTS+=("candidates, positions, interviews, assessments")
$HAS_ONBOARDING && HR_SCOPE_PARTS+=("onboarding, employee setup")
$HAS_COMPLIANCE && HR_SCOPE_PARTS+=("document compliance, renewals, PRO operations")
$HAS_SHIFTS     && HR_SCOPE_PARTS+=("shift schedules, coverage, reminders, availability, shift swaps")
$HAS_ATTENDANCE && HR_SCOPE_PARTS+=("attendance, check-ins, check-outs, lateness, absences")
$HAS_LEAVE      && HR_SCOPE_PARTS+=("leave requests, approvals, time off")
$HAS_PAYROLL    && HR_SCOPE_PARTS+=("payroll hours, timesheets, payroll policy, payroll exports, overtime, absence hours")
$HAS_ANALYTICS  && HR_SCOPE_PARTS+=("workforce analytics, branch performance, exceptions, trends")
HR_SCOPE_PARTS+=("branch/team manager-scoped workforce operations")
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
$HAS_SHIFTS     && MODULES_BLOCK+="- **Module 4: Shifts** — Staff schedules, coverage checks, shift reminders, availability, and shift swaps"$'\n'
$HAS_ATTENDANCE && MODULES_BLOCK+="- **Module 5: Attendance** — Check-ins, check-outs, lateness, absence tracking, attendance dashboards"$'\n'
$HAS_LEAVE      && MODULES_BLOCK+="- **Module 6: Leave** — Time-off requests, approvals, conflict checks, leave dashboards"$'\n'
$HAS_PAYROLL    && MODULES_BLOCK+="- **Module 7: Payroll** — Payroll-ready hours, draft timesheets, approval workflow, policy previews, and locked exports from shifts, attendance, and approved leave"$'\n'
$HAS_ANALYTICS  && MODULES_BLOCK+="- **Module 8: Analytics** — Workforce insights, branch performance, lateness, absences, overtime risk, and review priorities"$'\n'
MODULES_BLOCK+="- **Manager / Multi-Branch Layer** — Optional branch, team, and manager scopes applied across enabled workforce modules"$'\n'

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
$HAS_SHIFTS && HR_ALLOWED_ACTIONS+="- Create and update shift schedules
- Ask who is working today or tomorrow
- Detect missing coverage, conflicts, and overtime risk
- Record availability and unavailability
- Review, approve, or reject shift swap requests
- Send shift reminders to employees
"
$HAS_ATTENDANCE && HR_ALLOWED_ACTIONS+="- Check employees in or out
- Mark employees absent or correct attendance records
- Ask who is late, absent, checked in, or checked out
- Review attendance exceptions and dashboard updates
"
$HAS_LEAVE && HR_ALLOWED_ACTIONS+="- Create, approve, reject, or cancel leave requests
- Ask who is off or who has pending leave
- Review leave conflicts with scheduled shifts
"
$HAS_PAYROLL && HR_ALLOWED_ACTIONS+="- Review payroll hours by employee or period
- Ask for worked, scheduled, overtime, leave, and absence hours
- Prepare, approve, or reject timesheets for a payroll period
- View or update payroll policy and preview payroll from approved timesheets
- Export payroll for an explicit approved period without processing payment
- Update the Payroll Hours, Payroll Preview, and Payroll Export dashboards
"
$HAS_ANALYTICS && HR_ALLOWED_ACTIONS+="- Ask workforce analytics questions
- Review lateness, absences, overtime risk, branch performance, and review priorities
- Update the Analytics dashboard
"
HR_ALLOWED_ACTIONS+="- Ask branch/team-scoped workforce questions when manager scopes are configured
- Manage only employees inside the sender's configured branch/team manager scope
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

  if $HAS_SHIFTS; then
    content="$(echo "$content" | sed 's/{{#MODULE_SHIFTS}}//g; s/{{\/MODULE_SHIFTS}}//g')"
  else
    content="$(echo "$content" | perl -0pe 's/\{\{#MODULE_SHIFTS\}\}.*?\{\{\/MODULE_SHIFTS\}\}//gs')"
  fi

  if $HAS_ATTENDANCE; then
    content="$(echo "$content" | sed 's/{{#MODULE_ATTENDANCE}}//g; s/{{\/MODULE_ATTENDANCE}}//g')"
  else
    content="$(echo "$content" | perl -0pe 's/\{\{#MODULE_ATTENDANCE\}\}.*?\{\{\/MODULE_ATTENDANCE\}\}//gs')"
  fi

  if $HAS_LEAVE; then
    content="$(echo "$content" | sed 's/{{#MODULE_LEAVE}}//g; s/{{\/MODULE_LEAVE}}//g')"
  else
    content="$(echo "$content" | perl -0pe 's/\{\{#MODULE_LEAVE\}\}.*?\{\{\/MODULE_LEAVE\}\}//gs')"
  fi

  if $HAS_PAYROLL; then
    content="$(echo "$content" | sed 's/{{#MODULE_PAYROLL}}//g; s/{{\/MODULE_PAYROLL}}//g')"
  else
    content="$(echo "$content" | perl -0pe 's/\{\{#MODULE_PAYROLL\}\}.*?\{\{\/MODULE_PAYROLL\}\}//gs')"
  fi

  if $HAS_ANALYTICS; then
    content="$(echo "$content" | sed 's/{{#MODULE_ANALYTICS}}//g; s/{{\/MODULE_ANALYTICS}}//g')"
  else
    content="$(echo "$content" | perl -0pe 's/\{\{#MODULE_ANALYTICS\}\}.*?\{\{\/MODULE_ANALYTICS\}\}//gs')"
  fi

  echo "$content" > "$output"
}

# ─── Create Directory Structure ───────────────────────────────────────────────
echo "📁 Creating workspace directories..."
mkdir -p "$WORKSPACE_DIR"/{data/companies/"$COMPANY_CODE"/{positions,sync-queue},data/candidates,memory,.openclaw}

$HAS_ONBOARDING && mkdir -p "$WORKSPACE_DIR/data/companies/$COMPANY_CODE"/{employees,onboarding-templates}
$HAS_COMPLIANCE && mkdir -p "$WORKSPACE_DIR/data/companies/$COMPANY_CODE"/employees
$HAS_SHIFTS && mkdir -p "$WORKSPACE_DIR/data/companies/$COMPANY_CODE"/{employees,shifts}
$HAS_ATTENDANCE && mkdir -p "$WORKSPACE_DIR/data/companies/$COMPANY_CODE"/{employees,attendance}
$HAS_LEAVE && mkdir -p "$WORKSPACE_DIR/data/companies/$COMPANY_CODE"/{employees,leave}
$HAS_PAYROLL && mkdir -p "$WORKSPACE_DIR/data/companies/$COMPANY_CODE"/{employees,payroll}
$HAS_ANALYTICS && mkdir -p "$WORKSPACE_DIR/data/companies/$COMPANY_CODE"/analytics

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

if $HAS_SHIFTS; then
  cat > "$WORKSPACE_DIR/.openclaw/shifts-reminder-cron.json" << EOF
{
  "_comment": "Add via: openclaw cron add --agent $AGENT_ID ...",
  "name": "shift-reminders-${COMPANY_CODE_LOWER}",
  "schedule": { "kind": "cron", "expr": "0 * * * *", "tz": "Asia/Kuwait" },
  "sessionTarget": "isolated",
  "agentId": "$AGENT_ID",
  "payload": {
    "kind": "agentTurn",
    "message": "Run the Shifts reminder scan for upcoming shifts. Send employee reminders only once per shift and report summary to HR at $PRIMARY_HR_PHONE."
  },
  "delivery": {
    "mode": "announce",
    "channel": "whatsapp",
    "to": "$PRIMARY_HR_PHONE"
  }
}
EOF
  echo "   ✓ shifts-reminder-cron.json"
fi

if $HAS_ATTENDANCE; then
  cat > "$WORKSPACE_DIR/.openclaw/attendance-absence-cron.json" << EOF
{
  "_comment": "Add via: openclaw cron add --agent $AGENT_ID ...",
  "name": "attendance-absence-scan-${COMPANY_CODE_LOWER}",
  "schedule": { "kind": "cron", "expr": "*/30 * * * *", "tz": "Asia/Kuwait" },
  "sessionTarget": "isolated",
  "agentId": "$AGENT_ID",
  "payload": {
    "kind": "agentTurn",
    "message": "Run the Attendance absence scan. Mark no-shows only after the configured grace period, notify HR about exceptions, and update the Attendance dashboard. Never infer an employee from vague context."
  },
  "delivery": {
    "mode": "announce",
    "channel": "whatsapp",
    "to": "$PRIMARY_HR_PHONE"
  }
}
EOF
  echo "   ✓ attendance-absence-cron.json"
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
if $HAS_SHIFTS; then
echo "  7. ADD shifts reminder cron job:"
echo "     See: $WORKSPACE_DIR/.openclaw/shifts-reminder-cron.json"
echo ""
fi
if $HAS_ATTENDANCE; then
echo "  8. ADD attendance absence cron job:"
echo "     See: $WORKSPACE_DIR/.openclaw/attendance-absence-cron.json"
echo ""
fi
echo "  FINAL. RESTART Gateway:"
echo "     openclaw gateway restart"
echo ""
echo "Done! 🎉 $COMPANY_NAME is ready to go."
