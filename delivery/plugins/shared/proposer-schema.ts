/**
 * Phase A (2026-04-21): typed proposer output schema v1.0 → v1.1.
 *
 * ## Why this module exists
 *
 * The customer-turn proposer today produces a free-text `payload.text`
 * reply and, separately, zero or more strict-JSON tool calls. There is no
 * single structured artifact that names WHAT the LLM intends to do this
 * turn — so when the LLM silently skips `get_price` on a route-intent
 * turn (Class-15), or free-composes a clarification instead of calling the
 * pricing tool on a post-clarify continuation (Class-17 follow-up
 * `post_clarify_turn_bypasses_get_price`), the server has to infer the
 * drift from the absence of a signal. That is exactly the loop the
 * `[drift/get-price-bypass]` baseline counter is measuring.
 *
 * Phase A introduces a typed proposer output that the LLM produces via a
 * new tool call (`propose_turn_decision`). It is shadow-mode only in this
 * PR: parsed, validated, observed, logged — NOT consumed by
 * `applyProposals`, NOT gating any behavior. Promotion happens in a later
 * PR once the conformance signal clears the >=95% gate on the Phase C
 * eval corpus.
 *
 * ## What the LLM proposes
 *
 *   - `turn_kind`            — the LLM's self-classification of the turn,
 *                              mirroring the `[drift/get-price-bypass]`
 *                              partition so the two signals can be
 *                              cross-referenced.
 *   - `pricing_decision`     — the pricing action the LLM intends to take
 *                              this turn (`call_get_price`,
 *                              `continue_existing_quote`, `informational_only`,
 *                              `awaiting_state`, or `none`) + a one-line
 *                              rationale. We can compare this against
 *                              whether `get_price` actually fired.
 *   - `planned_tool_calls`   — names of the tools the LLM intends to call
 *                              this turn. Names only (schema v1.0); a
 *                              richer shape (names + key args) is a later
 *                              version.
 *   - `customer_reply_draft` — the text the LLM intends to say. In shadow
 *                              mode we compare it against the actual
 *                              `payload.text`; on promotion this becomes
 *                              the authoritative draft.
 *   - `awaiting_confirmation` (v1.1, optional)
 *                            — the LLM's 6-way semantic classification of
 *                              the customer's turn when the server stage
 *                              is `summary_shown` / `awaiting_confirmation`.
 *                              Required in those stages, ignored otherwise.
 *                              This is how the server stops relying on
 *                              hardcoded word lists to decide "did the
 *                              customer confirm / cancel / edit / ask /
 *                              say hi" — the LLM interprets meaning, the
 *                              server owns the resulting action/state
 *                              transition. Shadow-mode in this schema
 *                              bump; the Region-A dispatch gate is wired
 *                              up in a later PR (Phase B) once we see the
 *                              classifier hit a conformance bar on the
 *                              live test pack.
 *
 * ## Version policy
 *
 * The validator accepts BOTH `"1.0"` and `"1.1"` payloads. `awaiting_confirmation`
 * is OPTIONAL at the schema-shape layer regardless of version — the "it's
 * required at summary stages" rule is a prompt-side invariant, not a
 * validator rule, so we don't fail a turn just because the LLM forgot the
 * field. The drain-time emit records missing-but-expected as an
 * observability bucket instead. Unknown extra fields are silently dropped,
 * so a mix of v1.0 and v1.1 payloads is safe in flight during prompt
 * rollout.
 *
 * ## Why no external schema library
 *
 * Matches the existing hand-written JSON-schema style in this repo. The
 * pricing `get_price` tool, `propose_option_interpretation`, etc. all use
 * inline JSON-Schema objects on `api.registerTool`. Introducing zod / ajv
 * here would add a dep and an import surface for one type.
 */

export type ProposedTurnKind =
  | "initial_route"
  | "post_clarify_continuation"
  | "informational"
  | "address_collection"
  | "booking_detail_collection"
  | "confirmation_or_cancel"
  | "post_order_chat"
  | "other";

export const PROPOSED_TURN_KINDS: readonly ProposedTurnKind[] = [
  "initial_route",
  "post_clarify_continuation",
  "informational",
  "address_collection",
  "booking_detail_collection",
  "confirmation_or_cancel",
  "post_order_chat",
  "other",
] as const;

export type ProposedPricingAction =
  | "call_get_price"
  | "continue_existing_quote"
  | "informational_only"
  | "awaiting_state"
  | "none";

export const PROPOSED_PRICING_ACTIONS: readonly ProposedPricingAction[] = [
  "call_get_price",
  "continue_existing_quote",
  "informational_only",
  "awaiting_state",
  "none",
] as const;

export interface ProposedPricingDecision {
  action: ProposedPricingAction;
  reason: string;
}

// ---------------------------------------------------------------------------
// v1.1 (2026-04-22): awaiting-confirmation semantic classification.
//
// When the server stage is `summary_shown` or `awaiting_confirmation`, the
// LLM classifies the customer's turn into exactly one of these six kinds.
// This replaces the Phase A approach of gating summary re-render on
// hardcoded word lists (`isExplicitOrderConfirmation`, etc.). The server
// reads the classification at Region-A dispatch time and applies a small
// policy map (Phase B, not in this PR). Outside of the two stages the
// field is ignored by the validator and by the emit.
//
// Kind definitions (must stay in sync with the prompt-side text in
// one-brain-context.ts rule 11):
//   - confirm_order          — customer agrees with the summary as shown
//                               and wants the order placed. Includes
//                               explicit ("yes", "confirm", "نعم", "أكد"),
//                               soft ("ok", "تمام", "اوكي", "ايوه",
//                               "sure", "great") and long-tail natural
//                               language ("send it", "ارسله", "let's do
//                               this", "go for it", "please proceed").
//   - cancel_order           — customer wants to abandon the booking
//                               entirely. "cancel", "ألغي", "never mind
//                               the whole thing", "stop it". Does NOT
//                               include option-switch wording (that's
//                               `edit_order`).
//   - edit_order             — customer wants to correct / change one or
//                               more fields on the summary. Includes
//                               option switches ("actually make it
//                               fast box van"), address edits ("change
//                               block to 4"), identity edits, route
//                               edits, vehicle-class edits.
//   - informational_question — customer is asking a question about the
//                               summary / options / prices / timing /
//                               service without confirming or editing.
//                               "what's the cheapest again?", "how long
//                               does delivery take?", "is there a van?"
//   - coherence_pleasantry   — brief conversational filler that is not
//                               an action: greetings ("hi", "السلام
//                               عليكم"), thanks ("شكرا", "thank you"),
//                               fillers ("one sec", "لحظة", "hmm", "hold
//                               on", "noted"), politeness not attached
//                               to a confirm/cancel/edit/question.
//   - unclear                — anything the LLM cannot confidently place
//                               in the five categories above. Used when
//                               the turn is ambiguous, off-topic, or too
//                               short to classify. On Phase B the server
//                               will ask a short clarification instead
//                               of replaying the full summary.
// ---------------------------------------------------------------------------

export type AwaitingConfirmationKind =
  | "confirm_order"
  | "cancel_order"
  | "edit_order"
  | "informational_question"
  | "coherence_pleasantry"
  | "unclear";

export const AWAITING_CONFIRMATION_KINDS: readonly AwaitingConfirmationKind[] = [
  "confirm_order",
  "cancel_order",
  "edit_order",
  "informational_question",
  "coherence_pleasantry",
  "unclear",
] as const;

export interface ProposedAwaitingConfirmation {
  kind: AwaitingConfirmationKind;
  /** One-line rationale (≤200 chars). Observability only — not shown to the customer. */
  reason: string;
}

export type ProposerSchemaVersion = "1.0" | "1.1";

export const PROPOSER_SCHEMA_VERSIONS: readonly ProposerSchemaVersion[] = [
  "1.0",
  "1.1",
] as const;

export interface ProposedTurnDecision {
  schema_version: ProposerSchemaVersion;
  turn_kind: ProposedTurnKind;
  pricing_decision: ProposedPricingDecision;
  planned_tool_calls: string[];
  customer_reply_draft: string;
  /**
   * v1.1 addition. Present when the LLM classified the turn for the
   * awaiting-confirmation policy map; omitted (or `null`) on turns where
   * the stage is not `summary_shown` / `awaiting_confirmation`. v1.0
   * payloads simply never include this field.
   */
  awaiting_confirmation?: ProposedAwaitingConfirmation | null;
  rationale?: string;
}

export type ValidateResult<T> =
  | { ok: true; value: T }
  | { ok: false; errors: string[] };

/**
 * Hand-rolled validator for `ProposedTurnDecision`. Strict on the fields
 * that matter for classification (`turn_kind`, `pricing_decision.action`,
 * `schema_version`); lenient-cast on strings so a stray whitespace or
 * line break doesn't reject an otherwise well-formed proposal. Unknown
 * extra fields are silently dropped — future schema versions can add
 * fields without breaking the v1.0 parser.
 *
 * Accepts both `"1.0"` and `"1.1"` payloads. v1.1 introduces the optional
 * `awaiting_confirmation` field; if present AND non-null it must carry a
 * valid `kind` + `reason`. Absence is not a validator-level error — the
 * "must be present when stage is summary_shown/awaiting_confirmation"
 * invariant is enforced at the observability layer (drain emit records
 * missing-but-expected) and, in Phase B, at the Region-A dispatch gate.
 */
export function validateProposedTurnDecision(
  raw: unknown,
): ValidateResult<ProposedTurnDecision> {
  const errors: string[] = [];
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return { ok: false, errors: ["proposer_payload_not_object"] };
  }
  const obj = raw as Record<string, unknown>;

  const schemaVersion = obj.schema_version;
  if (
    typeof schemaVersion !== "string" ||
    !PROPOSER_SCHEMA_VERSIONS.includes(schemaVersion as ProposerSchemaVersion)
  ) {
    errors.push(
      `schema_version_unsupported:${
        typeof schemaVersion === "string" ? schemaVersion : "-"
      }`,
    );
  }

  const turnKind = obj.turn_kind;
  if (
    typeof turnKind !== "string" ||
    !PROPOSED_TURN_KINDS.includes(turnKind as ProposedTurnKind)
  ) {
    errors.push(
      `turn_kind_invalid:${
        typeof turnKind === "string" ? turnKind : "-"
      }`,
    );
  }

  const pricingDecisionRaw = obj.pricing_decision;
  let pricingDecision: ProposedPricingDecision | null = null;
  if (
    !pricingDecisionRaw ||
    typeof pricingDecisionRaw !== "object" ||
    Array.isArray(pricingDecisionRaw)
  ) {
    errors.push("pricing_decision_not_object");
  } else {
    const pdObj = pricingDecisionRaw as Record<string, unknown>;
    const action = pdObj.action;
    const reason = pdObj.reason;
    if (
      typeof action !== "string" ||
      !PROPOSED_PRICING_ACTIONS.includes(action as ProposedPricingAction)
    ) {
      errors.push(
        `pricing_decision.action_invalid:${
          typeof action === "string" ? action : "-"
        }`,
      );
    }
    if (typeof reason !== "string") {
      errors.push("pricing_decision.reason_not_string");
    }
    if (
      typeof action === "string" &&
      PROPOSED_PRICING_ACTIONS.includes(action as ProposedPricingAction) &&
      typeof reason === "string"
    ) {
      pricingDecision = {
        action: action as ProposedPricingAction,
        reason: reason.trim().slice(0, 400),
      };
    }
  }

  const plannedToolCallsRaw = obj.planned_tool_calls;
  let plannedToolCalls: string[] = [];
  if (!Array.isArray(plannedToolCallsRaw)) {
    errors.push("planned_tool_calls_not_array");
  } else {
    for (let i = 0; i < plannedToolCallsRaw.length; i += 1) {
      const entry = plannedToolCallsRaw[i];
      if (typeof entry !== "string" || !entry.trim()) {
        errors.push(`planned_tool_calls.${i}_not_nonempty_string`);
        continue;
      }
      plannedToolCalls.push(entry.trim());
    }
    // A turn with >16 planned tool calls is almost certainly a drift
    // artifact. Cap + log so we don't silently tolerate garbage lists.
    if (plannedToolCalls.length > 16) {
      errors.push(`planned_tool_calls_too_long:${plannedToolCalls.length}`);
      plannedToolCalls = plannedToolCalls.slice(0, 16);
    }
  }

  const customerReplyDraftRaw = obj.customer_reply_draft;
  let customerReplyDraft = "";
  if (typeof customerReplyDraftRaw !== "string") {
    errors.push("customer_reply_draft_not_string");
  } else {
    customerReplyDraft = customerReplyDraftRaw.trim();
  }

  const rationaleRaw = obj.rationale;
  let rationale: string | undefined;
  if (rationaleRaw !== undefined && rationaleRaw !== null) {
    if (typeof rationaleRaw !== "string") {
      errors.push("rationale_not_string");
    } else {
      const trimmed = rationaleRaw.trim();
      if (trimmed) {
        rationale = trimmed.slice(0, 600);
      }
    }
  }

  // v1.1 (2026-04-22): awaiting_confirmation semantic classification.
  // Optional at the shape layer for BOTH v1.0 and v1.1 payloads — missing
  // is never a validator error, because forgetting the field on an
  // awaiting-confirmation turn is a conformance miss (logged via
  // [structured-output/proposer] awaiting_confirmation_missing) not a
  // payload-level failure. If the field IS present and non-null, its kind
  // must be one of the six enum values and reason must be a string.
  const awaitingConfirmationRaw = obj.awaiting_confirmation;
  let awaitingConfirmation: ProposedAwaitingConfirmation | null = null;
  if (
    awaitingConfirmationRaw !== undefined &&
    awaitingConfirmationRaw !== null
  ) {
    if (
      typeof awaitingConfirmationRaw !== "object" ||
      Array.isArray(awaitingConfirmationRaw)
    ) {
      errors.push("awaiting_confirmation_not_object");
    } else {
      const acObj = awaitingConfirmationRaw as Record<string, unknown>;
      const kind = acObj.kind;
      const reason = acObj.reason;
      if (
        typeof kind !== "string" ||
        !AWAITING_CONFIRMATION_KINDS.includes(kind as AwaitingConfirmationKind)
      ) {
        errors.push(
          `awaiting_confirmation.kind_invalid:${
            typeof kind === "string" ? kind : "-"
          }`,
        );
      }
      if (typeof reason !== "string") {
        errors.push("awaiting_confirmation.reason_not_string");
      }
      if (
        typeof kind === "string" &&
        AWAITING_CONFIRMATION_KINDS.includes(kind as AwaitingConfirmationKind) &&
        typeof reason === "string"
      ) {
        awaitingConfirmation = {
          kind: kind as AwaitingConfirmationKind,
          reason: reason.trim().slice(0, 200),
        };
      }
    }
  }

  if (errors.length > 0) {
    return { ok: false, errors };
  }
  if (!pricingDecision) {
    return { ok: false, errors: ["pricing_decision_missing_after_validation"] };
  }

  const value: ProposedTurnDecision = {
    schema_version: schemaVersion as ProposerSchemaVersion,
    turn_kind: turnKind as ProposedTurnKind,
    pricing_decision: pricingDecision,
    planned_tool_calls: plannedToolCalls,
    customer_reply_draft: customerReplyDraft,
    ...(awaitingConfirmation !== null
      ? { awaiting_confirmation: awaitingConfirmation }
      : {}),
    ...(rationale !== undefined ? { rationale } : {}),
  };

  return { ok: true, value };
}

/**
 * JSON-schema-compatible shape for the `propose_turn_decision` tool's
 * `parameters`. Handed to `api.registerTool` with `strict: true` so the
 * host runtime enforces the envelope (type, required fields, enum
 * values). Enum literals MUST stay in sync with `PROPOSED_TURN_KINDS` /
 * `PROPOSED_PRICING_ACTIONS`; the smoke test anchors both lists against
 * this schema.
 */
export const PROPOSE_TURN_DECISION_TOOL_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: [
    "schema_version",
    "turn_kind",
    "pricing_decision",
    "planned_tool_calls",
    "customer_reply_draft",
  ],
  properties: {
    schema_version: {
      type: "string",
      enum: [...PROPOSER_SCHEMA_VERSIONS],
      description:
        "Schema version. Use '1.1' when declaring `awaiting_confirmation` on " +
        "summary-stage turns; '1.0' remains accepted for backward compat. " +
        "Validator accepts both.",
    },
    turn_kind: {
      type: "string",
      enum: [...PROPOSED_TURN_KINDS],
      description:
        "Your self-classification of this customer turn. Mirrors the " +
        "server-side drift-counter partition so the two signals can be " +
        "cross-referenced.",
    },
    pricing_decision: {
      type: "object",
      additionalProperties: false,
      required: ["action", "reason"],
      properties: {
        action: {
          type: "string",
          enum: [...PROPOSED_PRICING_ACTIONS],
          description:
            "What you intend to do about pricing this turn. If this turn " +
            "carries a route intent and there is no active quoted route, " +
            "this MUST be 'call_get_price' and 'get_price' MUST appear in " +
            "planned_tool_calls.",
        },
        reason: {
          type: "string",
          description:
            "One-line rationale for the pricing action. Keep <=120 chars.",
        },
      },
    },
    planned_tool_calls: {
      type: "array",
      items: { type: "string" },
      description:
        "Names of the tools you intend to call THIS turn, in order. Names " +
        "only (e.g. 'get_price', 'set_pending_area'). Required-but-empty " +
        "list is valid for turns that genuinely have no tool calls (pure " +
        "informational answer).",
    },
    customer_reply_draft: {
      type: "string",
      description:
        "The text you intend to send to the customer. May be empty for " +
        "turns that defer to a server-rendered directive.",
    },
    awaiting_confirmation: {
      type: ["object", "null"],
      additionalProperties: false,
      required: ["kind", "reason"],
      properties: {
        kind: {
          type: "string",
          enum: [...AWAITING_CONFIRMATION_KINDS],
          description:
            "6-way semantic classification of the customer's turn. " +
            "REQUIRED when current_conversation_stage is 'summary_shown' " +
            "or 'awaiting_confirmation'; omit (or null) otherwise. " +
            "confirm_order: agrees with summary and wants the order placed " +
            "(explicit, soft, or natural-language variants — classify by " +
            "meaning, not surface words). cancel_order: wants to abandon the " +
            "booking entirely. edit_order: wants to change one or more fields " +
            "(option switch, address edit, identity edit, route edit). " +
            "informational_question: asking about the summary/options/prices/" +
            "timing without confirming or editing. coherence_pleasantry: " +
            "greeting / thanks / filler / brief politeness that isn't an " +
            "action. unclear: genuinely ambiguous, off-topic, or too short " +
            "to classify confidently.",
        },
        reason: {
          type: "string",
          description:
            "One-line rationale for the kind you chose. <=200 chars. " +
            "Observability only — not shown to the customer.",
        },
      },
      description:
        "Your 6-way classification of this turn for the awaiting-confirmation " +
        "policy map. Server reads this to decide whether to place the order, " +
        "cancel, run the correction flow, answer the question, acknowledge " +
        "politely, or ask a short clarification. In shadow mode today — the " +
        "Region-A gate wires this up in a later PR.",
    },
    rationale: {
      type: "string",
      description:
        "Optional free-form rationale (<=400 chars). For observability only.",
    },
  },
} as const;
