// ---------------------------------------------------------------------------
// Phase 2 Milestone 1 (2026-04-22): ack-aware reply compose — SHADOW MODE.
//
// DEPLOY_CANARY_REPLY_COMPOSE_MODULE_MARKER: M1 ack-aware compose shadow
//
// ## Architectural role
//
// Today every `ASK_*` directive in the collection flow is rendered by the
// server via `directive-reply-registry.ts` — the ask text ("Sender's phone
// number?", "اسم المرسل الكامل؟", etc.) is server-owned. But the *ack prefix*
// in front of that ask — "Got it.", "Updated.", "Sorry, that didn't come
// through clearly." — is still LLM-authored today, which means it is
// author-time guesswork that only catches the context of the turn when the
// LLM chooses to emit one. That is why `SKILL.md`'s first two "How every
// reply must behave" bullets exist: they push the LLM to always ack-and-
// advance in the same message, and to refrain from stacking the next ASK
// after an informational question.
//
// M1 inverts the ack layer: the server picks the ack prefix from this
// registry, keyed on `turn_intent.kind` (already emitted in shadow by the
// Phase 1 proposer schema), and concatenates it with the existing directive
// renderer's ask text. After the flip-to-live, collection-turn replies are
// deterministic top-to-bottom: server ack + server ask. The LLM's freeform
// reply on those turns is replaced entirely.
//
// ## Shadow-first
//
// This PR ships only the registry + the pure `chooseAckPrefix` /
// `composeAckAwareReply` functions plus a `[reply-compose/shadow]` emit at
// the index.ts dispatch site. Live behaviour is unchanged. The flip-to-live
// happens in a later commit once the shadow logs show the ack choices look
// right on real traffic.
//
// ## Exhaustiveness
//
// `ACK_PREFIX_REGISTRY` is typed `Record<TurnIntentKind, Record<Language,
// AckPrefixChoice>>`. Adding a new `TurnIntentKind` to the proposer schema
// without updating the registry fails to compile — same tripwire discipline
// as `DIRECTIVE_REPLY_RENDERERS` uses.
//
// ## What this module does NOT do
//
// - Does not re-render the ask text. That's `renderDirectiveReply`'s job;
//   we only prepend.
// - Does not change slot-apply. That's M2 (turn_intent-gated draft-apply).
// - Does not change action-selection (the choice of WHICH directive to
//   emit). That's M3 (server-side hold-vs-advance decision driven by
//   turn_intent).
// - Does not touch the pre-booking quote phase, the post-order flow, or
//   the summary — all out of scope for M1.
// ---------------------------------------------------------------------------

import type {
  TurnIntentKind,
  TurnIntentConfidence,
} from "./proposer-schema";
import type { DirectiveAction } from "./directive-reply-registry";
import type { PersistedBookingDraft } from "./conversation-policy";

export type ReplyComposeLanguage = "ar" | "en";

// ---------------------------------------------------------------------------
// Discriminated result.
//
// `prefix`  → concrete ack text to place before the rendered ask, e.g.
//             "Got it." / "تمام." / "Sorry, that didn't come through
//             clearly.". The caller concatenates with a single space or
//             newline; see `composeAckAwareReply`.
// `skip`    → no ack prefix this turn, with a machine-readable reason
//             (logged by the shadow emit + used by tests).
//
// The explicit `skip` branch exists to make the "no ack, here's why" case
// first-class — it is just as important to log a skip reason as to log a
// chosen prefix. Silent "nothing happened" entries make the shadow logs
// useless for calibrating thresholds.
// ---------------------------------------------------------------------------

export type AckPrefixChoice =
  | { kind: "prefix"; text: string }
  | { kind: "skip"; reason: AckSkipReason };

export type AckSkipReason =
  // Turn_intent missing on a collection stage. Expected to be rare after
  // Phase 1 promotion; while still shadow it's the dominant bucket.
  | "turn_intent_missing"
  // Low-confidence classification — conservative: don't risk emitting the
  // wrong ack vibe. Drops to a plain directive render on flip-to-live.
  | "low_confidence"
  // Directive already includes its own built-in ack (currently only
  // `ASK_SENDER_PHONE` when `draft.senderName` is present — the renderer
  // emits "Thanks ${senderName}." / "تمام ${senderName}." inline).
  | "directive_has_builtin_ack"
  // Summary directive: the summary itself is the ack. Adding a prefix
  // would push the summary body below the fold on small WhatsApp bubbles.
  | "summary_directive_self_ack"
  // The customer asked a question. M1's scope is ack-prefix-on-ask, not
  // "answer the question instead of asking". That inversion belongs to M3
  // (action-selection). For M1 we conservatively skip the prefix here so
  // we don't say "Got it." in front of a re-ask when the customer was
  // actually seeking information.
  | "customer_asked_question"
  // Ack-of-ack: the customer's turn was itself a pleasantry. Prefixing
  // our ask with "Got it." in response to "ok thanks" reads robotic.
  | "ack_of_ack"
  // The turn_intent kind has no prefix mapped in the registry for this
  // language. Defensive — the `satisfies` check should make this
  // unreachable at compile time.
  | "unmapped_kind";

// ---------------------------------------------------------------------------
// Registry.
//
// Entries are indexed `[turnIntentKind][language]` so the matrix stays
// readable. The `satisfies` clause on the export gives us the compile-time
// tripwire: adding a new `TurnIntentKind` without a row here is a type
// error.
//
// Copy rationale:
//
//   - `answered_full` / `answered_partial` → "Got it." / "تمام."
//     Short, neutral, and compatible with the subsequent ask. Does not
//     claim completeness ("all set") because on `answered_partial` the
//     ask that follows is still asking for something — "Got it. Sender's
//     phone number?" reads correctly whether the customer answered the
//     whole compound ask or just part of it.
//
//   - `answered_unasked` → "Got it."
//     Volunteered data (e.g. customer gives the recipient phone while the
//     server was asking for the sender). Under M2 the apply layer will
//     decide whether to persist it; for M1's rendering layer, "Got it."
//     is still the right tone — we received the data, even if we then
//     ask again for the actually-asked field.
//
//   - `corrected_prior` → "Updated."
//     "Got it." would be accurate but flat. "Updated." explicitly
//     acknowledges that we heard the correction and overwrote the prior
//     value. This is also what the `CONFIRM_SLOT_CONFLICT` renderer
//     hints at, so the two layers line up.
//
//   - `clarifying_question` → skip (customer_asked_question)
//     Under today's flow, the server will still emit a directive on this
//     turn, because action-selection is state-driven. Prefixing "Got it."
//     in front of a re-ask when the customer was seeking information
//     reads as if the bot ignored the question. Skipping the prefix at
//     least leaves the bare ask, which is less offensive. M3 will stop
//     emitting the directive at all on these turns.
//
//   - `acknowledgement` → skip (ack_of_ack)
//     The customer said "ok", "thanks", "لحظة". Acknowledging an ack is
//     robotic. Today the LLM often over-emits "Sure — sender's phone
//     number?"; server-composed collection asks don't need to replicate
//     that shape.
//
//   - `refused_or_stuck` → "No worries — we can go step by step."
//     Softer lead-in when the customer is frustrated or declined. On AR
//     this is shorter: "ما عليك، نمشي خطوة خطوة.". Same intent — ease the
//     flow before the next ask.
//
//   - `unclear` → "Sorry, that didn't come through clearly."
//     This is the pasted-operational-text class, the voice-transcript-
//     error class, the keyboard-mash class. A minimal, non-blaming lead-
//     in that makes the bot feel aware that it saw something odd,
//     followed by the next ask. Today the LLM authors "Sender's full
//     name?" after a pasted deploy message, which is the exact
//     situationally-dumb failure mode the user flagged on 2026-04-22.
//
// All English prefixes end with a period and a single trailing space
// intentionally stripped — the `composeAckAwareReply` concatenator inserts
// its own newline. Arabic prefixes use the Arabic full-stop "." (same
// Unicode) and lead with a fresh sentence. Both EN and AR are short to
// leave WhatsApp viewport for the server-rendered ask.
// ---------------------------------------------------------------------------

type LanguageMap = Record<ReplyComposeLanguage, AckPrefixChoice>;

export const ACK_PREFIX_REGISTRY = {
  answered_full: {
    en: { kind: "prefix", text: "Got it." },
    ar: { kind: "prefix", text: "تمام." },
  },
  answered_partial: {
    en: { kind: "prefix", text: "Got it." },
    ar: { kind: "prefix", text: "تمام." },
  },
  answered_unasked: {
    en: { kind: "prefix", text: "Got it." },
    ar: { kind: "prefix", text: "تمام." },
  },
  corrected_prior: {
    en: { kind: "prefix", text: "Updated." },
    ar: { kind: "prefix", text: "تم التحديث." },
  },
  clarifying_question: {
    en: { kind: "skip", reason: "customer_asked_question" },
    ar: { kind: "skip", reason: "customer_asked_question" },
  },
  acknowledgement: {
    en: { kind: "skip", reason: "ack_of_ack" },
    ar: { kind: "skip", reason: "ack_of_ack" },
  },
  refused_or_stuck: {
    en: { kind: "prefix", text: "No worries — we can go step by step." },
    ar: { kind: "prefix", text: "ما عليك، نمشي خطوة خطوة." },
  },
  unclear: {
    en: { kind: "prefix", text: "Sorry, that didn't come through clearly." },
    ar: { kind: "prefix", text: "عذراً، ما وصلت بشكل واضح." },
  },
} as const satisfies Record<TurnIntentKind, LanguageMap>;

// ---------------------------------------------------------------------------
// Per-directive skips.
//
// A small set of directives already include an inline ack inside the
// rendered ask text itself — prepending a registry prefix to those would
// produce awkward double-ack wording ("Got it.\nThanks Ahmad. Sender's
// phone number?"). Rather than probe the rendered text post-hoc (which
// would couple this module to the renderer's exact phrasing), we enumerate
// the coupling here explicitly so changes to the inline ack in the
// renderer stay co-located with the skip decision.
//
// Currently only `ASK_SENDER_PHONE` meets this criterion, and only when
// `draft.senderName` is non-empty — that's the trigger for the renderer's
// built-in "Thanks ${senderName}." / "تمام ${senderName}." phrasing (see
// `renderAskSenderPhone` in directive-reply-registry.ts).
// ---------------------------------------------------------------------------

function directiveHasBuiltinAck(
  directiveAction: DirectiveAction,
  draft: PersistedBookingDraft,
): boolean {
  if (directiveAction === "ASK_SENDER_PHONE") {
    const senderName = (draft.senderName || "").trim();
    return senderName.length > 0;
  }
  return false;
}

// ---------------------------------------------------------------------------
// Pure chooser.
//
// Takes all signals needed to pick an ack prefix and returns a
// discriminated `AckPrefixChoice`. No side effects, no rendering —
// rendering is the directive-reply-registry's concern. The caller
// concatenates if the choice is `{kind: "prefix"}`, or passes through the
// rendered ask unchanged if `{kind: "skip"}`.
// ---------------------------------------------------------------------------

export interface ChooseAckPrefixInput {
  tiKind: TurnIntentKind | null;
  tiConfidence: TurnIntentConfidence | null;
  directiveAction: DirectiveAction;
  language: ReplyComposeLanguage;
  draft: PersistedBookingDraft;
}

export function chooseAckPrefix(
  input: ChooseAckPrefixInput,
): AckPrefixChoice {
  // Summary is its own ack. Skip before anything else — even if turn_intent
  // is present.
  if (
    input.directiveAction ===
    "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED"
  ) {
    return { kind: "skip", reason: "summary_directive_self_ack" };
  }

  // Directive-owned inline ack (currently only ASK_SENDER_PHONE with a
  // known sender name). See `directiveHasBuiltinAck` above.
  if (directiveHasBuiltinAck(input.directiveAction, input.draft)) {
    return { kind: "skip", reason: "directive_has_builtin_ack" };
  }

  // No turn_intent emitted — Phase 1 conformance miss.
  if (input.tiKind === null) {
    return { kind: "skip", reason: "turn_intent_missing" };
  }

  // Conservative: low-confidence classification falls back to a plain
  // directive render (no prefix). When we flip to live this keeps us from
  // emitting the wrong vibe on ambiguous turns.
  if (input.tiConfidence === "low") {
    return { kind: "skip", reason: "low_confidence" };
  }

  const row = ACK_PREFIX_REGISTRY[input.tiKind];
  if (!row) {
    return { kind: "skip", reason: "unmapped_kind" };
  }
  const choice = row[input.language];
  if (!choice) {
    return { kind: "skip", reason: "unmapped_kind" };
  }
  return choice;
}

// ---------------------------------------------------------------------------
// Pure composer.
//
// For the flip-to-live path: given the rendered ask text and the ack
// choice, return the final reply text. Shadow mode does not call this — it
// only logs the choice. But the flip-to-live call site will.
//
// Separator policy: single `"\n"` between prefix and ask. WhatsApp renders
// this as a line break inside one message bubble, which reads as two short
// sentences. A double newline (paragraph) feels too spaced out for the
// short ack + short ask pairing.
// ---------------------------------------------------------------------------

export function composeAckAwareReply(input: {
  choice: AckPrefixChoice;
  renderedAskText: string;
}): string {
  const ask = input.renderedAskText.trim();
  if (input.choice.kind === "skip") {
    return ask;
  }
  const prefix = input.choice.text.trim();
  if (!prefix) {
    return ask;
  }
  if (!ask) {
    return prefix;
  }
  return `${prefix}\n${ask}`;
}

// ---------------------------------------------------------------------------
// Shadow-emit helper.
//
// Formats the single-line `[reply-compose/shadow]` log payload so the
// index.ts call site stays short. Emitted at most once per turn on
// directive-eligible turns. All fields are scalar / enum-valued — no text
// contents leak the customer's message.
// ---------------------------------------------------------------------------

export interface ReplyComposeShadowEmit {
  conversation_id: string;
  session_key: string;
  directive_action: string;
  language: ReplyComposeLanguage;
  ti_kind: string;
  ti_confidence: string;
  choice_kind: "prefix" | "skip";
  choice_reason: string;
  prefix_chars: number;
}

export function formatReplyComposeShadowLog(e: ReplyComposeShadowEmit): string {
  return (
    `[reply-compose/shadow] ` +
    `conversation=${e.conversation_id} ` +
    `sessionKey=${e.session_key} ` +
    `directive=${e.directive_action} ` +
    `lang=${e.language} ` +
    `ti_kind=${e.ti_kind} ` +
    `ti_confidence=${e.ti_confidence} ` +
    `choice=${e.choice_kind} ` +
    `reason=${e.choice_reason} ` +
    `prefix_chars=${e.prefix_chars}`
  );
}
