#!/bin/zsh
# ---------------------------------------------------------------------------
# Cut #5 (turn-disposition authoring gate) live trace extractor.
#
# Pulls, per conversation, the three observables that matter for validating
# that Cut #5 is doing what we intended on real turns:
#
#   1. `[turn-disposition/authoring]` — what meaning classified this turn
#      as, whether state-machine authoring was skipped, whether the prompt
#      directive injection was skipped, and what directive the state
#      machine WOULD have authored if allowed.
#
#   2. `[one-brain/reply-attribution]` — who actually authored the reply
#      on the wire: server / llm / fallback + reason.
#
#   3. The outbound text itself. We anchor on
#      `[octopus/send-text] conversation=<id>` log lines (that prefix is
#      the existing provenance-carrying wire emit), trim to just the text.
#
# Usage:
#   ./scripts/pull-cut5-traces.sh <conversation_id> [since]
#
#   <conversation_id> : the Octopus conversation id (e.g. `19488`).
#   [since]           : journalctl --since expression, defaults to
#                       "30 minutes ago" so the common case of "I just ran
#                       a test turn" works out of the box.
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
    ('[turn-disposition/authoring]', re.compile(r'\[turn-disposition/authoring\]')),
    ('[one-brain/reply-attribution]', re.compile(r'\[one-brain/reply-attribution\]')),
    ('[octopus/send-text]', re.compile(r'\[octopus/send-text\]')),
    ('[one-brain/directive-dispatch]', re.compile(r'\[one-brain/directive-dispatch\]')),
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
