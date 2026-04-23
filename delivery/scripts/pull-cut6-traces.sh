#!/bin/zsh
# ---------------------------------------------------------------------------
# Cut #6 (prompt-shaping disposition) live trace extractor.
#
# Pulls, per conversation, the observables that matter for bake-reviewing
# Cut #6 against Cut #5 on real turns:
#
#   1. `[prompt-disposition/shaping]` — the pre-LLM heuristic
#      disposition for this turn: flag state, disposition value, policy
#      rule, whether state-authoring imperatives were skipped, whether
#      hard rules 4 and 10 were shaped, stage, has_quote,
#      requested_slot, fallthrough reason.
#
#   2. `[turn-disposition/authoring]` — Cut #5's post-LLM
#      authoritative disposition (what meaning said about this turn
#      AFTER the LLM returned). Reading 1 and 2 together gives the
#      per-turn "cell" of the pre × post matrix — agree, disagree,
#      and which direction.
#
#   3. `[one-brain/reply-attribution]` — who authored the reply on
#      the wire (server / llm / fallback + reason).
#
#   4. `[octopus/send-text]` — the outbound text itself.
#
#   5. `[one-brain] turn-snapshot` — the system prompt the LLM saw.
#      Useful for eyeballing whether the imperative block was dropped
#      when disposition ≠ `continue_step`.
#
# Usage:
#   ./scripts/pull-cut6-traces.sh <conversation_id> [since]
#
#   <conversation_id> : the Octopus conversation id (e.g. `19488`).
#   [since]           : journalctl --since expression, defaults to
#                       "30 minutes ago" so the common case of "I just
#                       ran a test turn" works out of the box.
#
# Requires: SSH access to $RIDERS_VPS_HOST (same as deploy.sh).
# ---------------------------------------------------------------------------

set -euo pipefail

VPS_HOST="${RIDERS_VPS_HOST:-root@72.61.106.61}"
CONV_ID="${1:-}"
SINCE="${2:-30 minutes ago}"

if [[ -z "$CONV_ID" ]]; then
  echo "Usage: $0 <conversation_id> [since]" >&2
  echo "Example: $0 19488 '10 minutes ago'" >&2
  exit 1
fi

echo "==> Target: $VPS_HOST"
echo "==> Conversation: $CONV_ID"
echo "==> Since: $SINCE"
echo

ssh "$VPS_HOST" "CONV_ID='$CONV_ID' SINCE='$SINCE' python3 - <<'PY'
import os
import re
import subprocess

conv_id = os.environ['CONV_ID']
since = os.environ['SINCE']

out = subprocess.check_output(
    ['journalctl', '-u', 'riders-delivery', '--since', since, '--no-pager'],
    text=True,
    errors='replace',
)

patterns = [
    ('[prompt-disposition/shaping]', re.compile(r'\[prompt-disposition/shaping\]')),
    ('[turn-disposition/authoring]', re.compile(r'\[turn-disposition/authoring\]')),
    ('[one-brain/reply-attribution]', re.compile(r'\[one-brain/reply-attribution\]')),
    ('[octopus/send-text]', re.compile(r'\[octopus/send-text\]')),
    ('[one-brain] turn-snapshot', re.compile(r'\[one-brain\] turn-snapshot')),
]

for label, pattern in patterns:
    print(f'--- {label} (conversation={conv_id}) ---')
    matched = [
        line for line in out.splitlines()
        if pattern.search(line) and f'conversation={conv_id}' in line
    ]
    if not matched:
        print(f'(no matches)')
    else:
        for line in matched:
            trimmed = re.sub(r'^.*? riders-delivery\[\d+\]: ', '', line)
            print(trimmed)
    print()
PY"
