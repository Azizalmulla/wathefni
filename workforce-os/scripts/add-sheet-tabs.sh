#!/usr/bin/env bash
set -euo pipefail

# Add "Employees" and "Compliance" tabs to the AI Octopus Google Sheet
# Usage: ./add-sheet-tabs.sh

SHEET_ID="1zMqYRGj0OSdoYYlMThAEfxoc1DQv-rRfHzpiAronwRM"
ACCOUNT="azizalmulla16@gmail.com"
TOKEN_FILE="/tmp/gog-token.json"
CREDS_FILE="$HOME/Library/Application Support/gogcli/credentials.json"

echo "📋 Adding Employees + Compliance tabs to AI Octopus sheet..."

# 1. Export refresh token
gog auth tokens export "$ACCOUNT" --out "$TOKEN_FILE" --overwrite >/dev/null 2>&1
REFRESH_TOKEN=$(python3 -c "import json; print(json.load(open('$TOKEN_FILE'))['refresh_token'])")

# 2. Read client credentials
CLIENT_ID=$(python3 -c "import json; print(json.load(open('$CREDS_FILE'))['client_id'])")
CLIENT_SECRET=$(python3 -c "import json; print(json.load(open('$CREDS_FILE'))['client_secret'])")

# 3. Exchange for access token
ACCESS_TOKEN=$(curl -s -X POST https://oauth2.googleapis.com/token \
  -d "client_id=$CLIENT_ID" \
  -d "client_secret=$CLIENT_SECRET" \
  -d "refresh_token=$REFRESH_TOKEN" \
  -d "grant_type=refresh_token" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

if [ -z "$ACCESS_TOKEN" ]; then
  echo "❌ Failed to get access token. Re-auth with: gog auth login"
  rm -f "$TOKEN_FILE"
  exit 1
fi

# 4. Add tabs via Sheets batchUpdate API
RESULT=$(curl -s -w "\n%{http_code}" -X POST \
  "https://sheets.googleapis.com/v4/spreadsheets/$SHEET_ID:batchUpdate" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      {"addSheet": {"properties": {"title": "Employees", "index": 1}}},
      {"addSheet": {"properties": {"title": "Compliance", "index": 2}}}
    ]
  }')

HTTP_CODE=$(echo "$RESULT" | tail -1)
BODY=$(echo "$RESULT" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
  echo "✅ Tabs created successfully!"
  echo "$BODY" | python3 -c "
import sys,json
r = json.load(sys.stdin)
for s in r.get('replies', []):
    props = s.get('addSheet', {}).get('properties', {})
    print(f\"  ✓ {props.get('title')} (sheetId={props.get('sheetId')})\")
"
else
  echo "⚠️  HTTP $HTTP_CODE — checking if tabs already exist..."
  echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error',{}).get('message','unknown error'))" 2>/dev/null || echo "$BODY"
fi

# 5. Add column headers to Employees tab
echo ""
echo "📝 Adding headers to Employees tab..."
gog sheets update "$SHEET_ID" "Employees!A1:L1" \
  --values-json '[["Name","Phone","Email","Position","Company","Hire Date","Onboarding Status","Documents Pending","Documents Complete","Start Date","Notes","Employee Key"]]' \
  --account "$ACCOUNT" 2>&1 && echo "  ✓ Employees headers set" || echo "  ⚠️ Failed to set Employees headers"

# 6. Add column headers to Compliance tab
echo ""
echo "📝 Adding headers to Compliance tab..."
gog sheets update "$SHEET_ID" "Compliance!A1:J1" \
  --values-json '[["Employee","Phone","Document Type","Status","Expiry Date","Days Until Expiry","Last Reminded","Reminder Count","Authority","Notes"]]' \
  --account "$ACCOUNT" 2>&1 && echo "  ✓ Compliance headers set" || echo "  ⚠️ Failed to set Compliance headers"

# 7. Cleanup
rm -f "$TOKEN_FILE"

echo ""
echo "Done! 🎉 Open the sheet to verify:"
echo "  https://docs.google.com/spreadsheets/d/$SHEET_ID/edit"
