// Phase A (2026-04-21): structured proposer tool.
//
// `propose_turn_decision` is the typed channel the LLM uses to declare its
// per-turn decision (turn_kind, pricing_decision, planned_tool_calls,
// customer_reply_draft) before emitting the final reply. The tool does
// NOT itself change any state — it validates the payload shape and pushes
// a `proposed_turn_decision` responder-op that the octopus drain observes
// in shadow mode.
//
// Shadow-mode guarantees for this PR:
//   - no routing change
//   - no substitution
//   - no new guards
//   - no behavior gate on the op
//
// See `plugins/shared/proposer-schema.ts` for the schema and validator;
// see `plugins/octopus-channel/index.ts` drain for the conformance emit
// `[structured-output/proposer]`.

import {
  pushResponderStateOp,
  type ResponderProposedTurnDecisionOp,
} from "../../shared/responder-state-ops";
import {
  PROPOSE_TURN_DECISION_TOOL_SCHEMA,
  validateProposedTurnDecision,
} from "../../shared/proposer-schema";

import type { ToolDeps } from "./deps";

export function registerProposerTools(api: any, deps: ToolDeps): void {
  const { resolveToolConversationId, resolveToolConversationAliases, resolveToolTurnId } =
    deps.booking;
  const { createTextResult, errorPayload } = deps;

  function collectAliases(ctx: any): string[] {
    try {
      return resolveToolConversationAliases(ctx);
    } catch {
      return [];
    }
  }

  api.registerTool({
    name: "propose_turn_decision",
    label: "Propose Turn Decision",
    description:
      "Structured turn-proposer (Phase A, schema v1.0). Call this exactly once per customer turn, BEFORE you produce any reply. " +
      "Declare: (a) the turn_kind you classify this turn as, (b) your pricing_decision (call_get_price / continue_existing_quote / informational_only / awaiting_state / none) with a short reason, (c) the names of the tools you intend to call THIS turn in planned_tool_calls, and (d) the customer_reply_draft text you intend to send. " +
      "This is a server observability channel — it is NOT a replacement for calling get_price or any other tool. If you declare planned_tool_calls includes 'get_price', you MUST actually call get_price this turn. " +
      "Never call this tool more than once per customer turn.",
    strict: true,
    parameters: PROPOSE_TURN_DECISION_TOOL_SCHEMA,

    async execute(
      _toolCallId: string,
      params: unknown,
      ctx?: any,
    ) {
      try {
        const validation = validateProposedTurnDecision(params);

        const aliases = collectAliases(ctx);
        const primary =
          (resolveToolConversationId && resolveToolConversationId(ctx)) ||
          aliases[0] ||
          "";
        const turnId =
          (resolveToolTurnId && resolveToolTurnId(ctx)) || "";

        // Observability: unconditional entry-log so "tool not called" vs
        // "tool called but push skipped" is always distinguishable. Mirrors
        // the `[responder-ops/mark-*]` logging pattern.
        try {
          const declaredAction =
            validation.ok
              ? validation.value.pricing_decision.action
              : "-";
          const declaredTurnKind = validation.ok
            ? validation.value.turn_kind
            : "-";
          // eslint-disable-next-line no-console
          console.log(
            `[proposer/tool-call] schema_valid=${validation.ok ? "true" : "false"} ` +
              `turn_kind=${declaredTurnKind} pricing_action=${declaredAction} ` +
              `primary=${primary || "-"} turn_id=${turnId || "-"} ` +
              `errors=${validation.ok ? "[]" : JSON.stringify(validation.errors)}`,
          );
        } catch {}

        if (!primary) {
          // No conversation id means we cannot route the op to the drain.
          // In shadow mode we still return success to the LLM so the tool
          // appears well-behaved; the `[proposer/tool-call]` log above
          // records the skip with the raw ctx fingerprint for triage.
          try {
            // eslint-disable-next-line no-console
            console.log(
              `[proposer/push-skip] reason=no_primary_id turn_id=${turnId || "-"} ` +
                `conversation_id=${JSON.stringify(ctx?.ConversationId || ctx?.conversationId || ctx?.ConversationID || null)} ` +
                `session_key=${JSON.stringify(ctx?.SessionKey || ctx?.sessionKey || null)} ` +
                `controller_state_key=${JSON.stringify(ctx?.ControllerStateKey || ctx?.controllerStateKey || null)}`,
            );
          } catch {}
          return createTextResult({
            status: "accepted",
            note: "Proposal recorded for observability; no routing applied.",
          });
        }

        const op: ResponderProposedTurnDecisionOp = {
          op: "proposed_turn_decision",
          // Store the RAW payload so the drain can re-validate with the
          // current validator (future schema bumps won't strand already-
          // pushed ops). Drain calls `validateProposedTurnDecision` again
          // and logs the verdict on its own emit.
          decision: params,
          turn_id: turnId,
        };
        pushResponderStateOp(primary, op, aliases);
        try {
          // eslint-disable-next-line no-console
          console.log(
            `[responder-ops/push] op=proposed_turn_decision conversation=${primary} ` +
              `aliases=${JSON.stringify(aliases)} schema_valid=${validation.ok ? "true" : "false"} ` +
              `turn_id=${turnId || "-"}`,
          );
        } catch {}

        return createTextResult({
          status: "accepted",
          schema_valid: validation.ok,
          // Do NOT echo the decision back — keeps the tool's text output
          // tiny so the LLM doesn't start parroting its own proposal into
          // the next turn's context.
        });
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  });
}
