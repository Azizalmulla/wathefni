#!/bin/zsh
# ---------------------------------------------------------------------------
# Cut 7b (A0 / A0a / A0b arming disposition gate) live trace extractor.
#
# Pulls, per conversation, the observables that matter for bake-reviewing
# Cut 7b against the legacy A0/A0a/A0b behaviour on real turns:
#
#   1. `[a0-arming/disposition]` — the per-turn matrix: flag state,
#      pre-LLM disposition, policy rule, whether the gate blocked
#      arming, clarify / mc_ask / mc_handoff would-have-armed vs
#      actually-armed, stage, has_quote. Emitted UNCONDITIONALLY per
#      customer turn (even with the env flag off), so a pre-flip
#      bake review can read exactly what will be gated once live.
#
#   2. `[prompt-disposition/shaping]` — the same pre-LLM decision
#      that feeds Cut 7b (same `promptShapingDecision`). Useful to
#      confirm disposition / policy_rule agree across both emits.
#
#   3. `[one-brain/clarify-option]` — whether the legacy A0 gate
#      fired (`gate=fired`) or Cut 7b suppressed it
#      (`gate=suppressed_by_disposition`).
#
#   4. `[one-brain/manual-confirm]` — same for the manual-confirm
#      A0a/A0b gates.
#
#   5. `[guard] Substituted clarify-before-proceed` —
#      outbound-decision warn line confirming A0 actually wrote the
#      options-menu reply. Absence of this line on a gated turn is
#      the strongest signal the cut worked.
#
#   6. `[turn-disposition/authoring]` — Cut #5's post-LLM
#      authoritative disposition. Reading 1 and 6 together shows
#      pre × post agreement.
#
#   7. `[one-brain/reply-attribution]` — who authored the reply on
#      the wire (server / llm / fallback + reason).
#
#   8. `[octopus/send-text]` — the outbound text itself. For the
#      canonical failure case we want to see a real answer, not the
#      hardcoded options-menu template.
#
# Usage:
#   ./scripts/pull-cut7b-traces.sh <conversation_id> [since]
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
  echo "       $0 ANY [since]   # dump all conversations in window" >&2
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
    ('[a0-arming/disposition]',                re.compile(r'\[a0-arming/disposition\]')),
    ('[prompt-disposition/shaping]',           re.compile(r'\[prompt-disposition/shaping\]')),
    ('[one-brain/clarify-option]',             re.compile(r'\[one-brain/clarify-option\]')),
    ('[one-brain/manual-confirm]',             re.compile(r'\[one-brain/manual-confirm\]')),
    ('[guard] Substituted clarify-before-proceed', re.compile(r'Substituted clarify-before-proceed')),
    ('[turn-disposition/authoring]',           re.compile(r'\[turn-disposition/authoring\]')),
    ('[one-brain/reply-attribution]',          re.compile(r'\[one-brain/reply-attribution\]')),
    ('[octopus/send-text]',                    re.compile(r'\[octopus/send-text\]')),
]

for label, pattern in patterns:
    print(f'--- {label} (conversation={conv_id}) ---')
    matched = []
    for line in out.splitlines():
        if not pattern.search(line):
            continue
        if conv_id != 'ANY' and f'conversation={conv_id}' not in line:
            continue
        matched.append(line)
    if not matched:
        print('(no matches)')
    else:
        for line in matched:
            trimmed = re.sub(r'^.*? riders-delivery\[\d+\]: ', '', line)
            print(trimmed)
    print()
PY"
