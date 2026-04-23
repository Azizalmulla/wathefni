#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=${0:A:h}
PROJECT_DIR=${SCRIPT_DIR:h}
PRESERVE_AI_OCTOPUS_BEARER_TOKEN="${AI_OCTOPUS_BEARER_TOKEN:-}"
PRESERVE_AI_OCTOPUS_WEBHOOK_TOKEN="${AI_OCTOPUS_WEBHOOK_TOKEN:-}"
PRESERVE_OPENCLAW_GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-}"
set -a
source "$PROJECT_DIR/.env"
set +a
if [[ -n "$PRESERVE_AI_OCTOPUS_BEARER_TOKEN" ]]; then
  export AI_OCTOPUS_BEARER_TOKEN="$PRESERVE_AI_OCTOPUS_BEARER_TOKEN"
fi
if [[ -n "$PRESERVE_AI_OCTOPUS_WEBHOOK_TOKEN" ]]; then
  export AI_OCTOPUS_WEBHOOK_TOKEN="$PRESERVE_AI_OCTOPUS_WEBHOOK_TOKEN"
fi
if [[ -n "$PRESERVE_OPENCLAW_GATEWAY_TOKEN" ]]; then
  export OPENCLAW_GATEWAY_TOKEN="$PRESERVE_OPENCLAW_GATEWAY_TOKEN"
fi

VPS_HOST="${RIDERS_VPS_HOST:-root@72.61.106.61}"
VPS_PLUGIN_DIR="/opt/riders-delivery/plugins/riders-tools"
VPS_OCTOPUS_PLUGIN_DIR="/opt/riders-delivery/plugins/octopus-channel"
VPS_SHARED_PLUGIN_DIR="/opt/riders-delivery/plugins/shared"
VPS_RIDERS_WORKSPACE_DIR="/opt/riders-delivery/workspaces/riders"
VPS_RIDERS_ADMIN_WORKSPACE_DIR="/opt/riders-delivery/workspaces/riders-admin"
VPS_RIDERS_DATA_DIR="$VPS_RIDERS_WORKSPACE_DIR/data"
VPS_SCRIPTS_DIR="/opt/riders-delivery/scripts"
VPS_TEMPLATE_PATH="/opt/riders-delivery/openclaw.template.json"
VPS_PROFILE_CONFIG="/root/.openclaw-delivery/openclaw.json"
VPS_ENV_PATH="/opt/riders-delivery/.env"
VPS_BACKUP_ROOT="/opt/riders-delivery/backups"
VPS_CADDY_SITE_PATH="${RIDERS_CADDY_SITE_PATH:-/etc/caddy/Caddyfile}"
VPS_PRICING_PUBLISHED_PATH="$VPS_RIDERS_DATA_DIR/pricing.published.json"
VPS_PRICING_RESOLVER_OVERLAY_PATH="$VPS_RIDERS_DATA_DIR/pricing.resolver.overlay.json"
VPS_BEHAVIOR_POLICY_PUBLISHED_PATH="$VPS_RIDERS_DATA_DIR/behavior-policy.published.json"
DEPLOY_CANARY_CLASS12_MARKER='must be a non-empty array of member areas'
DEPLOY_CANARY_GROUP_MARKER='"id": "kuwait_city_downtown"'
DEPLOY_CANARY_OPTION_MARKER='"name_en": "Bnaid Al-Qar"'
# Class-15 build canary markers (2026-04-21). Every file MUST carry the
# string below after a deploy of the route-intent-bypass repair.
DEPLOY_CANARY_CLASS15_VERIFY_MARKER='looksLikeFreeComposedAreaClarification'
DEPLOY_CANARY_CLASS15_REASON_MARKER='replace_get_price_bypass'
DEPLOY_CANARY_CLASS15_INDEX_MARKER='classFifteenBypass'
# Class-17 build canary markers (2026-04-21). If any of these ever disappear
# from a deployed bundle, the stripped-ctx booking-authority fallback is
# silently degraded back to Class-11 identity-only and the paired
# `hawalli → doha → mina doha` symmetric-rebind regression will reappear.
DEPLOY_CANARY_CLASS17_STASH_MARKER='getStashedBookingAuthority'
DEPLOY_CANARY_CLASS17_INGRESS_MARKER='bookingAuthority'
DEPLOY_CANARY_CLASS17_REASON_MARKER='pricing_area_binding'
# Phase D drift-counter build canary markers (2026-04-21). Baseline
# `get_price`-bypass rate is meaningless if the counter silently falls
# out of a future deploy, so we anchor both the emit tag and the
# turn_kind partition literal. Observation-only — not a behavior guard.
DEPLOY_CANARY_DRIFT_EMIT_MARKER='[drift/get-price-bypass]'
DEPLOY_CANARY_DRIFT_PARTITION_MARKER='post_clarify_continuation'
# Phase A structured-output build canary markers (2026-04-21). Shadow-
# mode typed proposer output. If any of these go missing, the eval
# corpus conformance measurement (>=95% well-formed across blocker
# transcripts) will silently regress to undefined and we will have lost
# the Phase A vs baseline comparison. Observation-only.
DEPLOY_CANARY_PROPOSER_TOOL_MARKER='propose_turn_decision'
DEPLOY_CANARY_PROPOSER_EMIT_MARKER='[structured-output/proposer]'
DEPLOY_CANARY_PROPOSER_CONTRACT_MARKER='structured_output_v1'
# Phase B measure-first build canary (2026-04-21). The
# `[directive-render/trace]` emit must land in every future
# octopus-channel bundle so we can keep reading verbs-vs-facts ratios.
# Observation-only — not a behavior guard.
DEPLOY_CANARY_DIRECTIVE_TRACE_MARKER='[directive-render/trace]'
# Phase 1 turn-intent build canary markers (2026-04-22). The three
# anchor points of the v1.2 shadow layer: schema definition (new
# TurnIntent types + validator), prompt rule (Rule 13 telling the LLM
# when to emit `turn_intent`), and emit (ti_* fields on the
# `[structured-output/proposer]` log line). If any of these go missing
# from a deployed bundle, the turn-intent conformance signal silently
# drops to noise — Phase 2 policy wiring relies on these three being
# present and consistent. Shadow-only, observation-only.
DEPLOY_CANARY_TURN_INTENT_SCHEMA_MARKER='DEPLOY_CANARY_TURN_INTENT_SCHEMA_MARKER'
DEPLOY_CANARY_TURN_INTENT_EMIT_MARKER='DEPLOY_CANARY_TURN_INTENT_EMIT_MARKER'
# Guard valid-set population canary markers (2026-04-22). Anchors the
# post-drain `sessionGuard.lastQuotedRoute` selection used to build the
# hallucination guard's `activeQuotedPrices` input on initial-route
# turns. If either symbol goes missing from a deployed bundle, the
# guard silently reverts to the null turn-start snapshot and truthful
# catalog-backed replies (e.g. "Express sedan 1.750 KWD" on a first
# quote) get blocked as price_mismatch again (conv 19400 regression).
DEPLOY_CANARY_GUARD_VALIDSET_HELPER_MARKER='selectGuardQuotedRoute'
DEPLOY_CANARY_GUARD_VALIDSET_CALLSITE_MARKER='collectActiveQuotedPrices'
# Authority cutover phase 4 (2026-04-23): the Phase 2 M1/M2/M3 shadow
# modules (reply-compose, slot-apply-gate, action-selection-gate) were
# deleted outright along with their shadow-emit callsites; their
# build canaries are removed. Phase 3c post_order_intent prompt rule
# was removed in Phase 1; only the schema and emit markers remain
# relevant until post_order_intent is fully pulled from the proposer
# schema in a later phase.
DEPLOY_CANARY_POST_ORDER_INTENT_SCHEMA_MARKER='POST_ORDER_INTENT_KINDS'
DEPLOY_CANARY_POST_ORDER_INTENT_EMIT_MARKER='DEPLOY_CANARY_POST_ORDER_INTENT_EMIT_MARKER'
# Unified turn-decision layer build canary markers (2026-04-22).
# Relocation 1 (scaffold observer) — anchors the new module and its
# late-turn callsite that emits the `[turn-decision/trace]` line. The
# trace line is the regression gate for relocations 2–5; losing it
# silently breaks diff-based verification of every subsequent
# relocation. Observation-only; not a behaviour guard.
# See delivery/ARCHITECTURE_TURN_DECISION.md.
DEPLOY_CANARY_TURN_DECISION_MODULE_MARKER='DEPLOY_CANARY_TURN_DECISION_MODULE_MARKER'
DEPLOY_CANARY_TURN_DECISION_CALLSITE_MARKER='DEPLOY_CANARY_TURN_DECISION_CALLSITE_MARKER'
# Relocation 2 (A4 → layer): deriveDispatch export present in the
# module, and a4_inputs block wired at the callsite. Absence means the
# deployed build predates the dispatch derivation and the trace will
# not emit layer_source / dispatch_agreement tokens.
DEPLOY_CANARY_TURN_DECISION_A4_RELOC_MARKER='DEPLOY_CANARY_TURN_DECISION_A4_RELOC_MARKER'
DEPLOY_CANARY_TURN_DECISION_A4_CALLSITE_MARKER='a4_inputs: {'
# Relocation 3 (A1 → layer): deriveA1Substitute export present in the
# module, and a1_inputs block wired at the callsite. Absence means the
# deployed build predates the A1 derivation and the trace will not
# emit layer_a1_intent / a1_agreement tokens.
DEPLOY_CANARY_TURN_DECISION_A1_RELOC_MARKER='DEPLOY_CANARY_TURN_DECISION_A1_RELOC_MARKER'
DEPLOY_CANARY_TURN_DECISION_A1_CALLSITE_MARKER='DEPLOY_CANARY_TURN_DECISION_A1_CALLSITE_MARKER'
# Relocation 3 FLIP (2026-04-22): A0c passthrough wired live behind
# env flag RIDERS_TURN_DECISION_A1_FLIP (default on, "off" to roll
# back). Absence means the deployed build is shadow-only and the
# three semantic-gate passthroughs will NOT take effect live.
DEPLOY_CANARY_TURN_DECISION_A1_FLIP_BRANCH_MARKER='DEPLOY_CANARY_TURN_DECISION_A1_FLIP_BRANCH_MARKER'
DEPLOY_CANARY_TURN_DECISION_A1_FLIP_CALLSITE_MARKER='DEPLOY_CANARY_TURN_DECISION_A1_FLIP_CALLSITE_MARKER'
# Relocation 3 HOIST (2026-04-23): semantic gates (pass_on_clarifying /
# pass_on_partial_answer / pass_on_route_change) now run ABOVE the
# legacy A0 / A0a / A0b substitutions inside `deriveA1Substitute`, and
# the A1 passthrough also bypasses those A0-family branches inside
# `decidePreStateOutbound`. Absence means the deployed build still has
# the pre-hoist ordering and clarifying questions during a
# clarify-before-proceed turn will continue to dump the option list.
DEPLOY_CANARY_TURN_DECISION_A1_SEMANTIC_GATE_HOIST_MARKER='DEPLOY_CANARY_TURN_DECISION_A1_SEMANTIC_GATE_HOIST_MARKER'
# Job-A authority removal (2026-04-23): the blanket callsite
# `a1FlipConfidenceOk` gate has been deleted. `deriveA1Substitute` is
# now the single source of truth for per-rule confidence policy
# (`pass_on_clarifying` and `pass_on_partial_answer` already require
# high/medium confidence inside the derivation; `pass_on_route_change`
# uses structural signals by design and must not be vetoed by a
# ti_confidence check, since fresh `initial_route` turns don't emit a
# turn_intent). Absence means the deployed build still has the old
# callsite second-guess gate and fresh-route turns will still be
# over-gated into the legacy `replace_directive_ask` branch.
DEPLOY_CANARY_TURN_DECISION_A1_FLIP_CONFIDENCE_GATE_REMOVAL_MARKER='DEPLOY_CANARY_TURN_DECISION_A1_FLIP_CONFIDENCE_GATE_REMOVAL_MARKER'
# Relocation 4 (directive → layer, 2026-04-22): decideDirectiveDisposition
# export present in the module, and directive_inputs block wired at the
# trace callsite. Absence means the deployed build predates the
# directive-disposition derivation and the trace will not emit the
# `directive_disposition` / `directive_agreement` tokens that the bake
# review and the subsequent live flip rely on. Shadow-only in this cut.
DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_RELOC_MARKER='DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_RELOC_MARKER'
DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_CALLSITE_MARKER='DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_CALLSITE_MARKER'
# Cut #2 (2026-04-23, Job-A authority removal): narrow live flip of the
# directive-disposition layer's `suppress_on_correction_intent` rule.
# When the layer classifies the turn as `corrected_prior` at high/medium
# confidence, the state-machine directive is cleared at the callsite so
# the LLM's acknowledge-the-correction draft passes through instead of
# being overridden by the A0c server render. The other three Reloc 4
# suppress rules (fresh route, clarifying, cancel) stay shadow-only
# until each becomes its own cut. Absence means the deployed build
# still pushes the candidate directive on correction turns, and the
# `actually my name is X` failure mode is still live.
DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_FLIP_CALLSITE_MARKER='DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_FLIP_CALLSITE_MARKER'
DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_FLIP_CORRECTION_MARKER='DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_FLIP_CORRECTION_MARKER'
# Cut #3 (2026-04-23, Job-A authority removal): narrow live flip of the
# directive-disposition layer's `suppress_on_acknowledgement_intent`
# rule. When the layer classifies the turn as `acknowledgement` at
# high/medium confidence, the state-machine directive is cleared at
# the callsite so the LLM's ack reply passes through instead of the
# state machine re-stamping the same slot ask. The remaining three
# Reloc 4 suppress rules (fresh route, clarifying, cancel) stay
# shadow-only until each becomes its own cut. Absence means the
# deployed build still pushes the candidate directive on mid-flow
# acknowledgement turns, and the `ok` / `thanks` loop failure mode is
# still live.
DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_FLIP_ACKNOWLEDGEMENT_MARKER='DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_FLIP_ACKNOWLEDGEMENT_MARKER'
# Relocation 5 Phase 5.0 shadow (2026-04-23): decideTurnDisposition
# authored in `plugins/shared/turn-disposition.ts` with the
# `DEPLOY_CANARY_TURN_DISPOSITION_MODULE_MARKER` canary, plus the
# `disposition_inputs` block wired at the trace callsite alongside
# the `DEPLOY_CANARY_TURN_DISPOSITION_CALLSITE_MARKER` canary.
# Absence means the deployed build predates the meaning-authors-first
# layer — the trace will not emit `disposition=` /
# `authored_directive=` / `state_consistency=` tokens that the bake
# review relies on. Shadow-only in this cut; callsite does not
# consume the derived disposition.
DEPLOY_CANARY_TURN_DISPOSITION_MODULE_MARKER='DEPLOY_CANARY_TURN_DISPOSITION_MODULE_MARKER'
DEPLOY_CANARY_TURN_DECISION_DISPOSITION_RELOC_MARKER='DEPLOY_CANARY_TURN_DECISION_DISPOSITION_RELOC_MARKER'
DEPLOY_CANARY_TURN_DISPOSITION_CALLSITE_MARKER='DEPLOY_CANARY_TURN_DISPOSITION_CALLSITE_MARKER'
# Cut #4 (2026-04-23, state coherence): DST conflict-slot pinning. When
# any DST slot is `status: "conflict"`, the post-drain requested-slot
# derivation in octopus-channel/index.ts pins `requestedSlot` to that
# slot — overriding both the missing-field derivation (which walks
# past conflicts because conflicting slots are still "filled" at
# draft-level and invisible to deriveRequestedSlotFromMissing) and
# any tool-pushed requested slot. This repairs the split-brain where
# the directive gate said CONFIRM_SLOT_CONFLICT(sender_name) while
# `requestedSlot` had drifted to sender_phone, producing the
# 2026-04-23 "aziz vs ahmad" stale-conflict loop. Absence means the
# deployed build predates this fix — later `ok`/ack turns can still
# re-arm the conflict against a prompt context that no longer points
# to the right slot. Invariant: findFirstConflictSlot() uses the same
# first-hit-in-entries order as the one-brain conflict gate; keep them
# in lockstep.
DEPLOY_CANARY_DST_CONFLICT_SLOT_PIN_MARKER='DEPLOY_CANARY_DST_CONFLICT_SLOT_PIN_MARKER'
# Cut #5 (2026-04-23, Reloc 5 inversion): turn-disposition AUTHORING gate.
# `decideTurnDisposition` is called live at the directive callsite BEFORE
# `directiveActionForRender` is assigned. When the layer classifies the
# turn as anything other than `continue_step`, the state-machine directive
# is NOT consumed — the LLM's draft survives through Region A. This
# inverts the authoring axis from "state authors; meaning vetoes" to
# "meaning authors; state is a subroutine called only on continue_step".
# Two markers anchor the cut: the import and the callsite. Absence of
# EITHER means the deployed build predates the inversion — the
# `[turn-disposition/authoring]` trace line will not emit, and every
# non-continue turn will fall through to the state-machine directive
# exactly as it did pre-Cut-#5. Behaviour-gated: env flag
# `RIDERS_TURN_DISPOSITION_AUTHOR_LIVE` (default "on", explicit "off"
# = one-line rollback).
DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_IMPORT_MARKER='DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_IMPORT_MARKER'
DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_CALLSITE_MARKER='DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_CALLSITE_MARKER'
# Pre-LLM prompt-shaping disposition (Cut #6). Module + import + callsite
# anchors. The per-rule GATE marker inside
# `formatOneBrainLiveChannelContext` was removed in the authority cutover
# (the prompt no longer carries state-machine authoring imperatives to
# gate); the decision is still computed and fed to the turn router.
DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_MODULE_MARKER='DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_MODULE_MARKER'
# ---------------------------------------------------------------------------
# Turn Router (Cut 9.0) — top-level meaning-first dispatcher. Module +
# import + callsite + state-machine gate anchors. `meaning_first` is
# hardcoded post-cutover; the env flag that used to toggle this is gone.
DEPLOY_CANARY_TURN_ROUTER_MODULE_MARKER='DEPLOY_CANARY_TURN_ROUTER_MODULE_MARKER'
DEPLOY_CANARY_TURN_ROUTER_IMPORT_MARKER='DEPLOY_CANARY_TURN_ROUTER_IMPORT_MARKER'
DEPLOY_CANARY_TURN_ROUTER_CALLSITE_MARKER='DEPLOY_CANARY_TURN_ROUTER_CALLSITE_MARKER'
DEPLOY_CANARY_TURN_ROUTER_STATE_MACHINE_GATE_MARKER='DEPLOY_CANARY_TURN_ROUTER_STATE_MACHINE_GATE_MARKER'
RIDERS_PUBLIC_WEBHOOK_HOST="${RIDERS_PUBLIC_WEBHOOK_HOST:-api.riderskw.com}"
RIDERS_PUBLIC_WEBHOOK_URL="${RIDERS_PUBLIC_WEBHOOK_URL:-https://$RIDERS_PUBLIC_WEBHOOK_HOST/webhook}"
RIDERS_PUBLIC_WEBHOOK_UPSTREAM="${RIDERS_PUBLIC_WEBHOOK_UPSTREAM:-127.0.0.1:18790}"
RIDERS_CADDY_ACCESS_LOG="${RIDERS_CADDY_ACCESS_LOG:-/var/log/caddy/riders-delivery-access.json}"
LOCAL_CADDY_TEMPLATE_PATH="$PROJECT_DIR/config/caddy/riders-delivery.Caddyfile.template"
LOCAL_CADDY_RENDERED_PATH="$(mktemp "${TMPDIR:-/tmp}/riders-delivery-caddy.XXXXXX")"
DEPLOY_TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
VPS_DEPLOY_BACKUP_DIR="$VPS_BACKUP_ROOT/$DEPLOY_TIMESTAMP"

cleanup() {
  rm -f "$LOCAL_CADDY_RENDERED_PATH"
}

trap cleanup EXIT

require_env_value() {
  local name="$1"
  local value="${(P)name:-}"
  if [[ -z "$value" ]]; then
    echo "Missing required env var: $name" >&2
    exit 1
  fi
}

warn_env_value() {
  local name="$1"
  local value="${(P)name:-}"
  if [[ -z "$value" ]]; then
    echo "Warning: env var is not set, continuing without it: $name" >&2
  fi
}

require_non_placeholder() {
  local name="$1"
  local value="${(P)name:-}"
  if [[ -z "$value" || "$value" == CHANGE_ME* || "$value" == *CHANGE_ME* ]]; then
    echo "Env var must be set to a non-placeholder value: $name" >&2
    exit 1
  fi
}

render_caddy_template() {
  if [[ ! -f "$LOCAL_CADDY_TEMPLATE_PATH" ]]; then
    echo "Missing Caddy template: $LOCAL_CADDY_TEMPLATE_PATH" >&2
    exit 1
  fi
  python3 - <<'PY' "$LOCAL_CADDY_TEMPLATE_PATH" "$LOCAL_CADDY_RENDERED_PATH" "$RIDERS_PUBLIC_WEBHOOK_HOST" "$RIDERS_PUBLIC_WEBHOOK_UPSTREAM" "$RIDERS_CADDY_ACCESS_LOG"
from pathlib import Path
import sys

template_path = Path(sys.argv[1])
rendered_path = Path(sys.argv[2])
host = sys.argv[3]
upstream = sys.argv[4]
access_log = sys.argv[5]

rendered = (
    template_path.read_text()
    .replace("__RIDERS_PUBLIC_WEBHOOK_HOST__", host)
    .replace("__RIDERS_PUBLIC_WEBHOOK_UPSTREAM__", upstream)
    .replace("__RIDERS_CADDY_ACCESS_LOG__", access_log)
)
rendered_path.write_text(rendered)
PY
}

for arg in "$@"; do
  case "$arg" in
    --plugin-only) ;;
    --help|-h)
      echo "Usage: $0 [--plugin-only]"
      echo "  Deploys riders-tools/octopus-channel and syncs the live OpenClaw profile."
      exit 0
      ;;
  esac
done

require_env_value AI_OCTOPUS_BEARER_TOKEN
warn_env_value AI_OCTOPUS_WEBHOOK_TOKEN
require_non_placeholder OPENCLAW_GATEWAY_TOKEN
render_caddy_template

echo "==> Target: $VPS_HOST"

ssh "$VPS_HOST" "rm -rf /opt/riders-delivery/plugins/google-sheets-tools && mkdir -p $VPS_PLUGIN_DIR $VPS_OCTOPUS_PLUGIN_DIR $VPS_SHARED_PLUGIN_DIR $VPS_RIDERS_WORKSPACE_DIR $VPS_RIDERS_DATA_DIR $VPS_RIDERS_ADMIN_WORKSPACE_DIR $VPS_SCRIPTS_DIR $VPS_BACKUP_ROOT"
ssh "$VPS_HOST" "find $VPS_OCTOPUS_PLUGIN_DIR -mindepth 1 -maxdepth 1 -exec rm -rf {} +"
ssh "$VPS_HOST" "find $VPS_SHARED_PLUGIN_DIR -mindepth 1 -maxdepth 1 -exec rm -rf {} +"

echo "==> Backing up live pricing data..."
ssh "$VPS_HOST" "mkdir -p $VPS_DEPLOY_BACKUP_DIR && for path in $VPS_PRICING_PUBLISHED_PATH $VPS_PRICING_RESOLVER_OVERLAY_PATH $VPS_BEHAVIOR_POLICY_PUBLISHED_PATH $VPS_CADDY_SITE_PATH; do if [ -f \"\$path\" ]; then cp \"\$path\" \"$VPS_DEPLOY_BACKUP_DIR/\"; fi; done"

echo "==> Deploying delivery template and bootstrap script..."
scp "$PROJECT_DIR/openclaw.template.json" "$VPS_HOST:$VPS_TEMPLATE_PATH"
scp "$PROJECT_DIR/scripts/bootstrap-profile.sh" "$VPS_HOST:$VPS_SCRIPTS_DIR/"

echo "==> Deploying riders-tools plugin (rsync of full directory)..."
# The plugin now ships as a tree (index.ts + tools/*.ts helpers) after the
# Wave 1a surgical split. Use rsync with --delete so any removed source file
# on the box is cleared too; excludes keep local build artifacts, node
# modules and OpenClaw runtime state out of the upload.
rsync -az --delete \
  --exclude='node_modules/' \
  --exclude='.openclaw/' \
  --exclude='.tmp/' \
  --exclude='*.log' \
  --exclude='*.tmp' \
  --exclude='package-lock.json' \
  "$PROJECT_DIR/plugins/riders-tools/" \
  "$VPS_HOST:$VPS_PLUGIN_DIR/"

echo "==> Deploying octopus-channel plugin (rsync of full directory)..."
# After Waves 2-5 the plugin ships as a tree (index.ts + lib/*.ts helpers +
# openclaw.plugin.json + optional node-shims.d.ts). Use rsync with --delete
# so any removed source file on the box is cleared too; excludes keep local
# build artifacts, node modules and OpenClaw runtime state out of the upload.
rsync -az --delete \
  --exclude='node_modules/' \
  --exclude='.openclaw/' \
  --exclude='.tmp/' \
  --exclude='*.log' \
  --exclude='*.tmp' \
  --exclude='package-lock.json' \
  --exclude='tsconfig.json' \
  "$PROJECT_DIR/plugins/octopus-channel/" \
  "$VPS_HOST:$VPS_OCTOPUS_PLUGIN_DIR/"

echo "==> Deploying shared plugin helpers (rsync of full directory)..."
# rsync (not scp) so newly-added shared modules don't silently fail to ship.
# Previous bug: new file `reply-hallucination-guard.ts` wasn't in the explicit
# scp list → VPS plugin crashed on boot with "Cannot find module". Using
# --delete so any removed source file on the box is cleared too; excludes
# keep local build artifacts and tests out.
rsync -az --delete \
  --exclude='node_modules/' \
  --exclude='.openclaw/' \
  --exclude='.tmp/' \
  --exclude='*.log' \
  --exclude='*.tmp' \
  --exclude='*.test.ts' \
  --exclude='*.spec.ts' \
  "$PROJECT_DIR/plugins/shared/" \
  "$VPS_HOST:$VPS_SHARED_PLUGIN_DIR/"

echo "==> Deploying Riders workspace files..."
scp "$PROJECT_DIR/workspaces/riders/AGENTS.md" \
    "$PROJECT_DIR/workspaces/riders/IDENTITY.md" \
    "$PROJECT_DIR/workspaces/riders/MEMORY.md" \
    "$PROJECT_DIR/workspaces/riders/REFERENCE.md" \
    "$PROJECT_DIR/workspaces/riders/SKILL.md" \
    "$PROJECT_DIR/workspaces/riders/SOUL.md" \
    "$PROJECT_DIR/workspaces/riders/TOOLS.md" \
    "$VPS_HOST:$VPS_RIDERS_WORKSPACE_DIR/"
scp "$PROJECT_DIR/workspaces/riders/data/behavior-policy.published.json" \
    "$PROJECT_DIR/workspaces/riders/data/pricing.published.json" \
    "$PROJECT_DIR/workspaces/riders/data/pricing.resolver.overlay.json" \
    "$VPS_HOST:$VPS_RIDERS_DATA_DIR/"

echo "==> Deploying Riders admin workspace files..."
scp "$PROJECT_DIR/workspaces/riders-admin/AGENTS.md" \
    "$PROJECT_DIR/workspaces/riders-admin/IDENTITY.md" \
    "$PROJECT_DIR/workspaces/riders-admin/SKILL.md" \
    "$PROJECT_DIR/workspaces/riders-admin/TOOLS.md" \
    "$VPS_HOST:$VPS_RIDERS_ADMIN_WORKSPACE_DIR/"

echo "==> Verifying deployed build canaries..."
ssh "$VPS_HOST" "python3 - <<'PY'
from pathlib import Path

checks = [
    (
        Path('$VPS_PLUGIN_DIR/lib/pricing-resolver.ts'),
        '$DEPLOY_CANARY_CLASS12_MARKER',
        'class-12 startup invariant marker',
    ),
    (
        Path('$VPS_PRICING_RESOLVER_OVERLAY_PATH'),
        '$DEPLOY_CANARY_GROUP_MARKER',
        'kuwait_city_downtown ambiguity group marker',
    ),
    (
        Path('$VPS_PRICING_RESOLVER_OVERLAY_PATH'),
        '$DEPLOY_CANARY_OPTION_MARKER',
        'kuwait_city_downtown member option marker',
    ),
    (
        Path('$VPS_SHARED_PLUGIN_DIR/outbound-verify.ts'),
        '$DEPLOY_CANARY_CLASS15_VERIFY_MARKER',
        'class-15 free-composed-area-clarification detector marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/lib/outbound-decision.ts'),
        '$DEPLOY_CANARY_CLASS15_REASON_MARKER',
        'class-15 replace_get_price_bypass reason-code marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_CLASS15_INDEX_MARKER',
        'class-15 classFifteenBypass callsite marker',
    ),
    (
        Path('$VPS_PLUGIN_DIR/lib/tool-conversation-ids.ts'),
        '$DEPLOY_CANARY_CLASS17_STASH_MARKER',
        'class-17 getStashedBookingAuthority export marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_CLASS17_INGRESS_MARKER',
        'class-17 ingress bookingAuthority publish marker',
    ),
    (
        Path('$VPS_PLUGIN_DIR/tools/pricing.ts'),
        '$DEPLOY_CANARY_CLASS17_REASON_MARKER',
        'class-17 pricing authority-fallback reason marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_DRIFT_EMIT_MARKER',
        'phase-d drift get_price-bypass emit marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_DRIFT_PARTITION_MARKER',
        'phase-d drift post_clarify_continuation partition literal',
    ),
    (
        Path('$VPS_PLUGIN_DIR/tools/proposer.ts'),
        '$DEPLOY_CANARY_PROPOSER_TOOL_MARKER',
        'phase-a propose_turn_decision tool registration marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_PROPOSER_EMIT_MARKER',
        'phase-a structured-output conformance emit marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/lib/one-brain-context.ts'),
        '$DEPLOY_CANARY_PROPOSER_CONTRACT_MARKER',
        'phase-a structured_output_v1 prompt contract marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/lib/outbound-decision.ts'),
        '$DEPLOY_CANARY_DIRECTIVE_TRACE_MARKER',
        'phase-b directive-render trace emit marker',
    ),
    (
        Path('$VPS_SHARED_PLUGIN_DIR/proposer-schema.ts'),
        '$DEPLOY_CANARY_TURN_INTENT_SCHEMA_MARKER',
        'phase-1 turn_intent v1.2 schema marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_INTENT_EMIT_MARKER',
        'phase-1 turn_intent ti_classification shadow emit marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/lib/quoted-options.ts'),
        '$DEPLOY_CANARY_GUARD_VALIDSET_HELPER_MARKER',
        'guard valid-set selectGuardQuotedRoute helper marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_GUARD_VALIDSET_CALLSITE_MARKER',
        'guard valid-set collectActiveQuotedPrices callsite marker',
    ),
    (
        Path('$VPS_SHARED_PLUGIN_DIR/proposer-schema.ts'),
        '$DEPLOY_CANARY_POST_ORDER_INTENT_SCHEMA_MARKER',
        'Phase 3c post_order_intent schema enum marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_POST_ORDER_INTENT_EMIT_MARKER',
        'Phase 3c post_order_intent shadow emit marker',
    ),
    (
        Path('$VPS_SHARED_PLUGIN_DIR/turn-decision.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_MODULE_MARKER',
        'turn-decision scaffold observer module marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_CALLSITE_MARKER',
        'turn-decision [turn-decision/trace] callsite marker',
    ),
    (
        Path('$VPS_SHARED_PLUGIN_DIR/turn-decision.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_A4_RELOC_MARKER',
        'turn-decision A4 deriveDispatch module marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_A4_CALLSITE_MARKER',
        'turn-decision A4 a4_inputs callsite marker',
    ),
    (
        Path('$VPS_SHARED_PLUGIN_DIR/turn-decision.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_A1_RELOC_MARKER',
        'turn-decision A1 deriveA1Substitute module marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_A1_CALLSITE_MARKER',
        'turn-decision A1 a1_inputs callsite marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/lib/outbound-decision.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_A1_FLIP_BRANCH_MARKER',
        'turn-decision A1 flip (A0c skip) branch marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_A1_FLIP_CALLSITE_MARKER',
        'turn-decision A1 flip callsite marker',
    ),
    (
        Path('$VPS_SHARED_PLUGIN_DIR/turn-decision.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_A1_SEMANTIC_GATE_HOIST_MARKER',
        'turn-decision A1 semantic-gate hoist marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_A1_FLIP_CONFIDENCE_GATE_REMOVAL_MARKER',
        'turn-decision A1 flip confidence-gate removal marker (Job-A authority removal)',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_FLIP_CALLSITE_MARKER',
        'turn-decision directive flip callsite marker (Cut #2, correction)',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_FLIP_CORRECTION_MARKER',
        'turn-decision directive flip correction marker (Cut #2, correction)',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_FLIP_ACKNOWLEDGEMENT_MARKER',
        'turn-decision directive flip acknowledgement marker (Cut #3, acknowledgement)',
    ),
    (
        Path('$VPS_SHARED_PLUGIN_DIR/turn-decision.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_RELOC_MARKER',
        'turn-decision directive-disposition module marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_CALLSITE_MARKER',
        'turn-decision directive_inputs callsite marker',
    ),
    (
        Path('$VPS_SHARED_PLUGIN_DIR/turn-disposition.ts'),
        '$DEPLOY_CANARY_TURN_DISPOSITION_MODULE_MARKER',
        'turn-disposition (Reloc 5 Phase 5.0) module marker',
    ),
    (
        Path('$VPS_SHARED_PLUGIN_DIR/turn-decision.ts'),
        '$DEPLOY_CANARY_TURN_DECISION_DISPOSITION_RELOC_MARKER',
        'turn-decision disposition reloc (5.0) module marker',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_DISPOSITION_CALLSITE_MARKER',
        'turn-disposition disposition_inputs callsite marker',
    ),
    (
        Path('$VPS_SHARED_PLUGIN_DIR/dialog-state.ts'),
        '$DEPLOY_CANARY_DST_CONFLICT_SLOT_PIN_MARKER',
        'dst conflict-slot pin helper marker (Cut #4, state coherence)',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_DST_CONFLICT_SLOT_PIN_MARKER',
        'dst conflict-slot pin callsite marker (Cut #4, state coherence)',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_IMPORT_MARKER',
        'turn-disposition authoring-gate import marker (Cut #5, Reloc 5 live)',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_CALLSITE_MARKER',
        'turn-disposition authoring-gate callsite marker (Cut #5, Reloc 5 live)',
    ),
    (
        Path('$VPS_SHARED_PLUGIN_DIR/turn-disposition.ts'),
        '$DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_MODULE_MARKER',
        'prompt-shaping disposition module marker (Cut #6, Reloc 5 input-side)',
    ),
    (
        Path('$VPS_SHARED_PLUGIN_DIR/turn-router.ts'),
        '$DEPLOY_CANARY_TURN_ROUTER_MODULE_MARKER',
        'turn-router module marker (Cut 9.0, meaning-first dispatcher)',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_ROUTER_IMPORT_MARKER',
        'turn-router import marker (Cut 9.0, meaning-first dispatcher)',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_ROUTER_CALLSITE_MARKER',
        'turn-router callsite + trace emit marker (Cut 9.0, meaning-first dispatcher)',
    ),
    (
        Path('$VPS_OCTOPUS_PLUGIN_DIR/index.ts'),
        '$DEPLOY_CANARY_TURN_ROUTER_STATE_MACHINE_GATE_MARKER',
        'turn-router state-machine gate marker (Cut 9.0, one consumer wired)',
    ),
]

missing = []
for path, marker, label in checks:
    try:
        text = path.read_text()
    except Exception as exc:
        missing.append(f'{label}: unreadable {path} ({exc})')
        continue
    if marker not in text:
        missing.append(f'{label}: missing marker {marker!r} in {path}')

if missing:
    raise SystemExit('deploy verifier failed:\\n' + '\\n'.join(missing))

print('Build canary markers OK')
PY"

echo "==> Fixing ownership on delivery project files..."
ssh "$VPS_HOST" "chown -R root:root /opt/riders-delivery"

echo "==> Updating live delivery env vars..."
ssh "$VPS_HOST" "VPS_ENV_PATH='$VPS_ENV_PATH' RIDERS_PRICING_SOURCE_MODE='${RIDERS_PRICING_SOURCE_MODE:-published_preferred}' RIDERS_PRICING_PUBLISHED_PATH='$VPS_PRICING_PUBLISHED_PATH' RIDERS_PRICING_RESOLVER_OVERLAY_PATH='$VPS_PRICING_RESOLVER_OVERLAY_PATH' RIDERS_PRICING_SHEET_ID='${RIDERS_PRICING_SHEET_ID:-}' RIDERS_PRICING_SHEET_NAME='${RIDERS_PRICING_SHEET_NAME:-}' RIDERS_PRICING_SHEET_HEADER_ROW='${RIDERS_PRICING_SHEET_HEADER_ROW:-}' RIDERS_PRICING_ADMIN_ALLOWLIST='${RIDERS_PRICING_ADMIN_ALLOWLIST}' RIDERS_BEHAVIOR_ADMIN_ALLOWLIST='${RIDERS_BEHAVIOR_ADMIN_ALLOWLIST}' AI_OCTOPUS_ADMIN_ALLOWLIST='${AI_OCTOPUS_ADMIN_ALLOWLIST:-}' RIDERS_TRACKING_PROVIDER='${RIDERS_TRACKING_PROVIDER:-}' FLEETRUNNR_API_BASE_URL='${FLEETRUNNR_API_BASE_URL:-}' FLEETRUNNR_BEARER_TOKEN='${FLEETRUNNR_BEARER_TOKEN:-}' RIDERS_GRID_API_BASE_URL='${RIDERS_GRID_API_BASE_URL:-}' RIDERS_GRID_API_KEY='${RIDERS_GRID_API_KEY:-}' VOYAGE_API_KEY='${VOYAGE_API_KEY:-}' python3 - <<'PY'
import os
from pathlib import Path

env_path = Path(os.environ['VPS_ENV_PATH'])
current = {}
if env_path.exists():
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in raw_line:
            continue
        key, value = raw_line.split('=', 1)
        current[key] = value

current['RIDERS_PRICING_SOURCE_MODE'] = os.environ.get('RIDERS_PRICING_SOURCE_MODE', '') or 'published_preferred'
current['RIDERS_PRICING_PUBLISHED_PATH'] = os.environ.get('RIDERS_PRICING_PUBLISHED_PATH', '')
current['RIDERS_PRICING_RESOLVER_OVERLAY_PATH'] = os.environ.get('RIDERS_PRICING_RESOLVER_OVERLAY_PATH', '')

for key in ['RIDERS_PRICING_SHEET_ID', 'RIDERS_PRICING_SHEET_NAME', 'RIDERS_PRICING_SHEET_HEADER_ROW']:
    val = os.environ.get(key, '')
    if val:
        current[key] = val

current['RIDERS_PRICING_ADMIN_ALLOWLIST'] = os.environ['RIDERS_PRICING_ADMIN_ALLOWLIST']
current['RIDERS_BEHAVIOR_ADMIN_ALLOWLIST'] = os.environ['RIDERS_BEHAVIOR_ADMIN_ALLOWLIST']
ai_octopus = os.environ.get('AI_OCTOPUS_ADMIN_ALLOWLIST', '')
if ai_octopus:
    current['AI_OCTOPUS_ADMIN_ALLOWLIST'] = ai_octopus

for key in ['RIDERS_TRACKING_PROVIDER', 'FLEETRUNNR_API_BASE_URL', 'FLEETRUNNR_BEARER_TOKEN', 'RIDERS_GRID_API_BASE_URL', 'RIDERS_GRID_API_KEY', 'VOYAGE_API_KEY']:
    val = os.environ.get(key, '')
    if val:
        current[key] = val

ordered_keys = [
    'RIDERS_PRICING_SOURCE_MODE',
    'RIDERS_PRICING_PUBLISHED_PATH',
    'RIDERS_PRICING_RESOLVER_OVERLAY_PATH',
    'RIDERS_PRICING_SHEET_ID',
    'RIDERS_PRICING_SHEET_NAME',
    'RIDERS_PRICING_SHEET_HEADER_ROW',
    'RIDERS_PRICING_ADMIN_ALLOWLIST',
    'RIDERS_BEHAVIOR_ADMIN_ALLOWLIST',
    'AI_OCTOPUS_ADMIN_ALLOWLIST',
    'RIDERS_TRACKING_PROVIDER',
    'FLEETRUNNR_API_BASE_URL',
    'FLEETRUNNR_BEARER_TOKEN',
    'RIDERS_GRID_API_BASE_URL',
    'RIDERS_GRID_API_KEY',
    'VOYAGE_API_KEY',
]
existing_keys = [key for key in current.keys() if key not in ordered_keys]
lines = [f'{key}={current[key]}' for key in existing_keys]
for key in ordered_keys:
    if key in current:
        lines.append(f'{key}={current[key]}')
env_path.write_text('\n'.join(lines) + '\n')
print(f'Updated {env_path}')
PY"

echo "==> Updating live delivery OpenClaw profile..."
ssh "$VPS_HOST" "chmod +x $VPS_SCRIPTS_DIR/bootstrap-profile.sh && RIDERS_PRICING_SOURCE_MODE='${RIDERS_PRICING_SOURCE_MODE:-published_preferred}' RIDERS_PRICING_PUBLISHED_PATH='$VPS_PRICING_PUBLISHED_PATH' RIDERS_PRICING_RESOLVER_OVERLAY_PATH='$VPS_PRICING_RESOLVER_OVERLAY_PATH' RIDERS_PRICING_SHEET_ID='${RIDERS_PRICING_SHEET_ID:-}' RIDERS_PRICING_SHEET_NAME='${RIDERS_PRICING_SHEET_NAME:-}' RIDERS_PRICING_SHEET_HEADER_ROW='${RIDERS_PRICING_SHEET_HEADER_ROW:-}' RIDERS_TRACKING_PROVIDER='${RIDERS_TRACKING_PROVIDER:-}' FLEETRUNNR_API_BASE_URL='${FLEETRUNNR_API_BASE_URL:-}' FLEETRUNNR_BEARER_TOKEN='${FLEETRUNNR_BEARER_TOKEN:-}' python3 - <<'PY'
import json
import os
from pathlib import Path

config_path = Path('$VPS_PROFILE_CONFIG')
config = json.loads(config_path.read_text())

agents_section = config.setdefault('agents', {})
agents = agents_section.setdefault('list', [])
defaults = agents_section.setdefault('defaults', {})
default_model = ((defaults.get('model') or {}).get('primary')) or 'openai/gpt-5.4-mini'
defaults['bootstrapMaxChars'] = int(defaults.get('bootstrapMaxChars') or 50000)
defaults['bootstrapTotalMaxChars'] = int(defaults.get('bootstrapTotalMaxChars') or 180000)
defaults['thinkingDefault'] = str(defaults.get('thinkingDefault') or 'medium')
defaults_models = defaults.setdefault('models', {})
mini_model_entry = defaults_models.setdefault('openai/gpt-5.4-mini', {})
mini_params = mini_model_entry.setdefault('params', {})
mini_params['reasoning'] = {'effort': 'medium'}
mini_params['text'] = {'verbosity': 'low'}
mini_params['transport'] = 'auto'
mini_params['openaiWsWarmup'] = True
mini_params['responsesServerCompaction'] = True
defaults_models.pop('openai/gpt-5.4', None)

def ensure_agent(agent_id, workspace, primary_model):
    for agent in agents:
        if agent.get('id') == agent_id:
            agent['workspace'] = workspace
            model = agent.setdefault('model', {})
            model['primary'] = primary_model
            return agent
    agent = {
        'id': agent_id,
        'workspace': workspace,
        'model': {'primary': primary_model},
    }
    agents.append(agent)
    return agent

def ensure_denied_tools(agent, *tool_names):
    tools = agent.setdefault('tools', {})
    deny = tools.get('deny') or []
    for name in tool_names:
        if name not in deny:
            deny.append(name)
    tools['deny'] = deny

def configure_agent_runtime(agent, thinking_default):
    agent['thinkingDefault'] = thinking_default

riders = ensure_agent('riders', '$VPS_RIDERS_WORKSPACE_DIR', default_model)
ensure_denied_tools(riders, 'message')
configure_agent_runtime(riders, 'medium')

riders_admin = ensure_agent('riders-admin', '$VPS_RIDERS_ADMIN_WORKSPACE_DIR', default_model)
ensure_denied_tools(riders_admin, 'exec')
configure_agent_runtime(riders_admin, 'medium')

riders_mini = ensure_agent('riders-mini', '$VPS_RIDERS_WORKSPACE_DIR', 'openai/gpt-5.4-mini')
ensure_denied_tools(riders_mini, 'message')
configure_agent_runtime(riders_mini, 'medium')

agents[:] = [agent for agent in agents if agent.get('id') != 'riders-full']

plugins = config.setdefault('plugins', {})
plugins.pop('allow', None)
load = plugins.setdefault('load', {})
paths = load.setdefault('paths', [])
for path in [
    '$VPS_PLUGIN_DIR',
    '$VPS_OCTOPUS_PLUGIN_DIR',
]:
    if path not in paths:
        paths.append(path)

paths[:] = [path for path in paths if path != '/opt/riders-delivery/plugins/google-sheets-tools']

entries = plugins.setdefault('entries', {})
openai_entry = entries.setdefault('openai', {})
openai_entry['enabled'] = True
openai_config = openai_entry.setdefault('config', {})
openai_config['personality'] = 'off'
riders_tools = entries.setdefault('riders-tools', {})
riders_tools['enabled'] = True
riders_tools_config = riders_tools.setdefault('config', {})
riders_tools_pricing = riders_tools_config.setdefault('pricing', {})
riders_tools_pricing['sourceMode'] = os.environ.get('RIDERS_PRICING_SOURCE_MODE', '') or 'published_preferred'
riders_tools_pricing['publishedPath'] = os.environ.get('RIDERS_PRICING_PUBLISHED_PATH', '') or '$VPS_PRICING_PUBLISHED_PATH'
riders_tools_pricing['resolverOverlayPath'] = os.environ.get('RIDERS_PRICING_RESOLVER_OVERLAY_PATH', '') or '$VPS_PRICING_RESOLVER_OVERLAY_PATH'
riders_tools_pricing.setdefault('adminAllowlist', [])
riders_tools_google_sheet = riders_tools_pricing.setdefault('googleSheet', {})
if os.environ.get('RIDERS_PRICING_SHEET_ID', ''):
    riders_tools_google_sheet['spreadsheetId'] = os.environ['RIDERS_PRICING_SHEET_ID']
if os.environ.get('RIDERS_PRICING_SHEET_NAME', ''):
    riders_tools_google_sheet['sheetName'] = os.environ['RIDERS_PRICING_SHEET_NAME']
if os.environ.get('RIDERS_PRICING_SHEET_HEADER_ROW', ''):
    riders_tools_google_sheet['headerRow'] = int(os.environ['RIDERS_PRICING_SHEET_HEADER_ROW'])
riders_tools_behavior = riders_tools_config.setdefault('behavior', {})
riders_tools_behavior['publishedPath'] = '$VPS_RIDERS_WORKSPACE_DIR/data/behavior-policy.published.json'
riders_tools_behavior.setdefault('adminAllowlist', [])
entries.setdefault('octopus-channel', {})['enabled'] = True
entries.pop('octopus', None)
entries.pop('google-sheets-tools', None)
entries.pop('whatsapp', None)

channels = config.setdefault('channels', {})
octopus = channels.setdefault('octopus', {})
octopus['enabled'] = True
octopus['agentId'] = octopus.get('agentId') or 'riders'
octopus['dmPolicy'] = octopus.get('dmPolicy') or 'open'
octopus['typingEnabled'] = True if octopus.get('typingEnabled') is None else octopus.get('typingEnabled')
octopus['typingRefreshMs'] = int(octopus.get('typingRefreshMs') or 9000)
octopus['webhookPath'] = '/webhook'
octopus['behaviorPolicyPublishedPath'] = '$VPS_RIDERS_WORKSPACE_DIR/data/behavior-policy.published.json'
octopus_accounts = octopus.setdefault('accounts', {})
octopus_default_account = octopus_accounts.setdefault('default', {})
octopus_default_account['enabled'] = True

gateway = config.setdefault('gateway', {})
gateway['trustedProxies'] = ['127.0.0.1/8', '::1/128']

tools = config.setdefault('tools', {})
media_tools = tools.setdefault('media', {})
audio_tools = media_tools.setdefault('audio', {})
audio_tools['enabled'] = True
audio_tools['maxBytes'] = int(audio_tools.get('maxBytes') or 20971520)
audio_tools['models'] = [
    {
        'provider': 'openai',
        'model': 'gpt-4o-transcribe',
    }
]

env_section = config.setdefault('env', {})
tracking_provider = os.environ.get('RIDERS_TRACKING_PROVIDER', '')
fleetrunnr_base = os.environ.get('FLEETRUNNR_API_BASE_URL', '')
fleetrunnr_token = os.environ.get('FLEETRUNNR_BEARER_TOKEN', '')
if tracking_provider:
    env_section['RIDERS_TRACKING_PROVIDER'] = tracking_provider
if fleetrunnr_base:
    env_section['FLEETRUNNR_API_BASE_URL'] = fleetrunnr_base
if fleetrunnr_token:
    env_section['FLEETRUNNR_BEARER_TOKEN'] = fleetrunnr_token

session_section = config.setdefault('session', {})
session_section['dmScope'] = 'per-channel-peer'
session_section['reset'] = {'mode': 'idle', 'idleMinutes': 1440}

# Safety: remove empty apiKey fields that override env vars
providers = config.get('models', {}).get('providers', {})
for prov_name, prov_cfg in providers.items():
    if 'apiKey' in prov_cfg and not prov_cfg['apiKey']:
        del prov_cfg['apiKey']
    for model_entry in prov_cfg.get('models', []):
        declared_input = set(model_entry.get('input') or ['text'])
        declared_input.add('image')
        model_entry['input'] = sorted(declared_input)

config_path.write_text(json.dumps(config, indent=2) + '\n')
print(f'Updated {config_path}')
PY"

echo "==> Deploying public webhook proxy config..."
scp "$LOCAL_CADDY_RENDERED_PATH" "$VPS_HOST:$VPS_CADDY_SITE_PATH.tmp"
ssh "$VPS_HOST" "mkdir -p \"$(dirname "$RIDERS_CADDY_ACCESS_LOG")\" && chmod 644 \"$VPS_CADDY_SITE_PATH.tmp\" && caddy validate --config \"$VPS_CADDY_SITE_PATH.tmp\" && mv \"$VPS_CADDY_SITE_PATH.tmp\" \"$VPS_CADDY_SITE_PATH\" && chown root:root \"$VPS_CADDY_SITE_PATH\" && chmod 644 \"$VPS_CADDY_SITE_PATH\" && rm -f \"$RIDERS_CADDY_ACCESS_LOG\" && install -o caddy -g caddy -m 664 /dev/null \"$RIDERS_CADDY_ACCESS_LOG\" && (timeout 30s systemctl reload caddy || systemctl restart caddy)"

echo "==> Restarting services..."
ssh "$VPS_HOST" "systemctl restart riders-delivery"

echo "==> Verifying services..."
sleep 2
ssh "$VPS_HOST" "
  echo '--- riders-delivery ---'
  systemctl is-active riders-delivery
  echo '--- caddy ---'
  systemctl is-active caddy
"

echo "==> Verifying gateway health..."
ssh "$VPS_HOST" "OPENCLAW_PROFILE='${OPENCLAW_PROFILE:-delivery}' openclaw gateway health"

echo "==> Probing public webhook..."
PROBE_REQUEST_ID="deploy-probe-$DEPLOY_TIMESTAMP"
PROBE_CURL_ARGS=(
  -fsS
  -X POST
  "$RIDERS_PUBLIC_WEBHOOK_URL"
  -H "Content-Type: application/json"
  -H "X-Request-Id: $PROBE_REQUEST_ID"
  --data '{}'
)
if [[ -n "${AI_OCTOPUS_WEBHOOK_TOKEN:-}" ]]; then
  PROBE_CURL_ARGS+=(-H "x-ai-octopus-token: $AI_OCTOPUS_WEBHOOK_TOKEN")
fi
PROBE_RESPONSE=""
for attempt in {1..10}; do
  if PROBE_RESPONSE="$(curl "${PROBE_CURL_ARGS[@]}")"; then
    break
  fi
  if [[ "$attempt" -eq 10 ]]; then
    echo "Public webhook probe failed after $attempt attempts." >&2
    exit 1
  fi
  echo "Public webhook probe not ready yet (attempt $attempt/10); retrying..."
  sleep 3
done
python3 - <<'PY' "$PROBE_RESPONSE"
import json
import sys

payload = json.loads(sys.argv[1])
if not payload.get("ok") or not payload.get("probe"):
    raise SystemExit(f"Unexpected webhook probe response: {payload}")
print(f"Webhook probe response OK: {payload}")
PY

echo "==> Verifying ingress markers..."
ssh "$VPS_HOST" "python3 - <<'PY'
import subprocess

request_id = '$PROBE_REQUEST_ID'
out = subprocess.check_output(
    ['journalctl', '-u', 'riders-delivery', '--since', '5 minutes ago', '--no-pager'],
    text=True,
    errors='replace',
)
lines = [line for line in out.splitlines() if request_id in line]
required = ['webhook_received', 'webhook_validation_probe']
missing = [needle for needle in required if not any(needle in line for line in lines)]
if missing:
    raise SystemExit(f'Missing ingress markers for {request_id}: {missing} :: {lines[-20:]}')
print(f'Ingress markers OK for {request_id}')
PY"

echo "==> Deploy complete."
