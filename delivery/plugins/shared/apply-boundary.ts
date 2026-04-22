/**
 * Apply boundary — the ONE place booking-draft fields get committed.
 *
 * This module implements the evidence contract described in
 * `delivery/ARCHITECTURE.md`. It is the Layer-3 decision engine for the
 * B-with-teeth architecture: the LLM proposes, the deterministic fast-path
 * may also propose on unambiguous shapes, and every proposal from every
 * source is validated here against the same checks before any state
 * mutation happens.
 *
 * Evidence contract, run in order per proposal:
 *
 *   1. `source_quote` gate — `fast_path` and `llm` proposals without a
 *      `source_quote` are rejected with `missing_source_quote`. Carryover
 *      proposals are exempt (their ground truth is a persisted prior
 *      order, not a turn quote).
 *
 *   2. Ambiguous-pair guard — when a proposal writes recipient fields
 *      from a single unlabeled name+phone pair while the sender is still
 *      unresolved, the recipient fields are dropped and the next turn is
 *      steered to ask for the sender. Skipped for carryover.
 *
 *   3. Coherence gate — each proposed name value is classified as an
 *      answer to the sender/recipient name slot. Greetings,
 *      acknowledgments ("alright", "ok", "تمام"), questions, and
 *      topic-changes are rejected with `coherence_<kind>`. Skipped for
 *      carryover and for values where the coherence module has no policy
 *      (phones and address parts keep their existing shape-only rules).
 *
 *   4. Edit-intent detection — for `llm` / `fast_path` proposals, inspect
 *      the `source_quote` for explicit edit signals (English/Arabic edit
 *      verbs, `label N to M` patterns, negations like "not X, Y") AND
 *      verify the conversation stage is one where edits are expected
 *      (`collecting_booking_details`, `summary_shown`,
 *      `awaiting_confirmation`). When both hold, the shape+apply step
 *      runs with `editIntent: true`, which turns would-be
 *      filled-slot conflicts into silent overrides. This is the
 *      immediate fix for the post-summary "block 3 to block 4" bug.
 *
 *   5. Shape + apply — surviving patch runs through `applyBookingFieldPatch`
 *      which does the established shape validation (`cleanName` /
 *      `cleanPhone` / `cleanAddressPart`), DST `updateSlot` conflict
 *      detection, and mirrors slots back into the draft.
 *
 * Every rejection, from any check, is returned with a structured reason
 * code. Callers are expected to forward those codes into the outbound
 * hallucination guard's `rejectionsThisTurn` list so the next turn's LLM
 * context sees why its proposal failed.
 *
 * This boundary is the reason the "alright → sender_name" and
 * "hello → sender_name" classes of incident are structurally impossible
 * once every write path routes through it. The fast-path extractor
 * becomes a pure observer + proposer; the LLM drain becomes a pure
 * proposer; neither writes state directly.
 */

import {
  type AddressRole,
  type BookingDraft,
  type BookingFieldPatch,
  type PhoneDecision,
  type SlotConflict,
  PHONE_MIN_DIGITS,
  applyBookingFieldPatch,
  cleanPhone,
} from "./booking-draft.js";
import {
  type DialogState,
  type SlotName,
  setRequestedSlot,
} from "./dialog-state.js";
import { evaluateAmbiguousPair } from "./ambiguous-pair-guard.js";
import {
  classifyResponseForSlot,
  type SlotCoherenceDecision,
} from "./slot-response-coherence.js";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type ProposalSource = "fast_path" | "llm" | "carryover";

/**
 * A typed proposal to write one or more slots. Every path that wants to
 * mutate the booking draft MUST build a `Proposal` and call `applyProposals`
 * — never `applyBookingFieldPatch` directly (except from within this
 * module and legacy test fixtures).
 */
export type Proposal = {
  source: ProposalSource;
  /** Exact customer utterance this proposal derives from. Mandatory for
   *  `fast_path` and `llm` sources; `carryover` may pass null. */
  source_quote: string | null;
  /** Proposed field values. Each non-null key is independently validated
   *  and may be individually rejected. */
  patch: BookingFieldPatch;
  /** Optional — turn identifier for log correlation. */
  turnId?: string | null;
};

export type BoundaryRejectionReason =
  // Source-quote gate
  | "missing_source_quote"
  // Ambiguous-pair
  | "ambiguous_pair_sender_unresolved"
  // Coherence gate (one of the `CoherenceKind` values except `answer`)
  | "coherence_greeting"
  | "coherence_acknowledgment"
  | "coherence_question"
  | "coherence_topic_change"
  | "coherence_ambiguous"
  | "coherence_empty"
  // Requested-slot name-scope guard: on a name-requested turn we reject
  // same-side phone writes that aren't accompanied by a same-side name in
  // the patch. See `applyRequestedSlotNameScope` below.
  | "requested_slot_name_scope"
  // Shape gate — passes through whatever `applyBookingFieldPatch` says
  | string;

/**
 * A soft normalization applied by the boundary before the shape+apply
 * step. Normalizations are not rejections — the write still lands, just
 * in a different field (e.g. a sender_phone write that matches the
 * customer's WhatsApp tail collapses into `phone_decision=use_whatsapp`).
 * Surfaced on `BoundaryResult.normalizations` so the caller can log them
 * for provenance / observability.
 */
export type BoundaryNormalizationKind =
  | "whatsapp_equivalence_sender_phone";

export type BoundaryNormalization = {
  kind: BoundaryNormalizationKind;
  field: keyof BookingFieldPatch;
  incoming: string;
  mappedTo: string;
  source: ProposalSource;
};

export type BoundaryRejection = {
  field: string;
  reason: BoundaryRejectionReason;
  received: string;
  source: ProposalSource;
};

export type BoundaryResult = {
  draft: BookingDraft;
  dialogState: DialogState | null;
  /** Fields successfully committed, in the order they were applied. */
  applied: Array<keyof BookingFieldPatch>;
  rejections: BoundaryRejection[];
  /** DST conflicts surfaced by the underlying apply step; callers may
   *  want to log these but they are not rejections. */
  conflicts: SlotConflict[];
  /** When the boundary steered the next turn (today: ambiguous-pair
   *  rejection steers to `sender_name`), this is the slot the caller
   *  should set as requested on the controller's dialog state. */
  requestedSlotOverride: SlotName | null;
  /** Sender phone decision, if any proposal set one. Mirrors
   *  `ApplyPatchResult.senderPhoneDecision`. */
  senderPhoneDecision: PhoneDecision | null;
  /** Soft normalizations applied before shape+apply. Not failures —
   *  surfaced for logging only. */
  normalizations: BoundaryNormalization[];
};

export type BoundaryContext = {
  draft: BookingDraft;
  dialogState: DialogState | null;
  whatsappNumber: string | null;
  /** Conversation stage from the controller entry. Used by the edit-intent
   *  detector: explicit edits are only honored in stages where the
   *  customer has plausibly seen the filled value at least once
   *  (collecting_booking_details / summary_shown / awaiting_confirmation).
   *  Absent or unrecognized stage disables the edit path, so callers that
   *  don't have stage information degrade safely to the pre-existing
   *  conflict behavior. */
  stage?: string | null;
};

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function mapSourceToDstSource(source: ProposalSource): "customer_fast_path" | "llm_apply" | "carryover" {
  switch (source) {
    case "fast_path":
      return "customer_fast_path";
    case "llm":
      return "llm_apply";
    case "carryover":
      return "carryover";
  }
}

function fieldHasValue(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function coherenceReasonCode(decision: SlotCoherenceDecision): BoundaryRejectionReason {
  switch (decision.kind) {
    case "greeting":
      return "coherence_greeting";
    case "acknowledgment":
      return "coherence_acknowledgment";
    case "question":
      return "coherence_question";
    case "topic_change":
      return "coherence_topic_change";
    case "ambiguous":
      return "coherence_ambiguous";
    case "empty":
      return "coherence_empty";
    case "answer":
      // Should never reach here — the caller only calls this on
      // non-answer decisions.
      return "coherence_ambiguous";
  }
}

/**
 * Slots that the coherence gate is authoritative for. Today only the two
 * name slots — phones and addresses have strong shape validation at
 * `applyBookingFieldPatch` and do not benefit from the conversational
 * coherence classifier (a bare digit run is not a "greeting", a block
 * number is not a "topic change"). If we extend coherence to additional
 * slots in future, add them here.
 */
const COHERENCE_GATED_FIELDS: ReadonlyArray<{
  field: "sender_name" | "recipient_name";
  slot: SlotName;
}> = [
  { field: "sender_name", slot: "sender_name" },
  { field: "recipient_name", slot: "recipient_name" },
];

// ---------------------------------------------------------------------------
// WhatsApp-equivalence normalization (Fix A, 2026-04-22 sender-step incident).
//
// When a proposal writes `sender_phone = X` and X is the same phone as the
// customer's WhatsApp number — either an exact match, or X is the local-part
// and WA carries a country code (or vice versa) — the semantic is the same
// as `phone_decision = use_whatsapp`. Before this normalization, that case
// landed as a raw `sender_phone` write, and any subsequent "use_whatsapp"
// evidence (voice-spelled digits, LLM transliteration lag) would later
// conflict with the already-written phone. Collapsing early lets the
// apply-boundary treat this as the "use the WA number" path, which is what
// the customer meant.
//
// Conservative match: both sides must pass `cleanPhone` (>= PHONE_MIN_DIGITS,
// digits only) and either
//   - cand === wa, or
//   - one is a strict suffix of the other, with the shorter one >=
//     PHONE_MIN_DIGITS (so a coincidental 3-digit tail doesn't trigger).
//
// This catches both fast-path and LLM writes because every proposal passes
// through `applyProposals`. Live defect on conversation 19399 turn B (voice
// transcript of digits spelled out, LLM wrote sender_phone=99338566 while
// WA=96599338566 — a tail match, normalized to use_whatsapp here).
// ---------------------------------------------------------------------------
function senderPhoneMatchesWhatsapp(
  candidate: string,
  whatsappNumber: string | null,
): { matched: boolean; mappedTo: string | null } {
  if (!whatsappNumber) return { matched: false, mappedTo: null };
  const cand = cleanPhone(candidate).value;
  const wa = cleanPhone(whatsappNumber).value;
  if (!cand || !wa) return { matched: false, mappedTo: null };
  if (cand === wa) return { matched: true, mappedTo: wa };
  const longer = cand.length >= wa.length ? cand : wa;
  const shorter = cand.length >= wa.length ? wa : cand;
  if (shorter.length < PHONE_MIN_DIGITS) return { matched: false, mappedTo: null };
  if (longer.endsWith(shorter)) return { matched: true, mappedTo: wa };
  return { matched: false, mappedTo: null };
}

function normalizeWhatsappEquivalence(
  patch: BookingFieldPatch,
  whatsappNumber: string | null,
): { patch: BookingFieldPatch; normalized: BoundaryNormalization | null } {
  if (patch.sender_phone == null || typeof patch.sender_phone !== "string") {
    return { patch, normalized: null };
  }
  const { matched, mappedTo } = senderPhoneMatchesWhatsapp(
    patch.sender_phone,
    whatsappNumber,
  );
  if (!matched || !mappedTo) return { patch, normalized: null };
  const next: BookingFieldPatch = { ...patch };
  const incoming = next.sender_phone as string;
  next.sender_phone = null;
  // If the LLM signalled "different" while providing the WA local-part,
  // the equivalence wins — the two digits are the same number. Likewise
  // if no decision was signalled at all.
  if (next.phone_decision !== "use_whatsapp") {
    next.phone_decision = "use_whatsapp";
  }
  return {
    patch: next,
    normalized: {
      kind: "whatsapp_equivalence_sender_phone",
      field: "sender_phone",
      incoming,
      mappedTo,
      source: "llm",
    },
  };
}

// ---------------------------------------------------------------------------
// Requested-slot name-scope guard (Fix C, 2026-04-22 sender-step incident).
//
// When `dialogState.requestedSlot.name` is a name slot (`sender_name` /
// `recipient_name`) and a proposal writes the SAME-side phone field WITHOUT
// also providing the name the server asked for, we drop the phone write.
// The rationale:
//
//   * On a name-requested turn the customer's single utterance should
//     answer the name. If the proposal only writes the phone, the
//     "answer" slot is still missing and the pattern that follows —
//     server re-asks, customer re-provides — is strictly a regression vs.
//     accepting nothing and re-asking the full name+phone combined.
//
//   * When the phone happens to match the customer's WhatsApp it is
//     already collapsed by the WA-equivalence normalization above, so this
//     guard only fires on genuinely-different numbers.
//
//   * When the proposal writes BOTH name and phone on the same turn, the
//     name is present and the guard does NOT fire — both writes land. This
//     preserves the "volunteer-more" UX (customer answers name + phone in
//     one breath).
//
// Implementation note: the guard runs AFTER coherence, so a name that was
// rejected for being an acknowledgment ("ok") has already been nulled out
// by the coherence pass. In that case, treating the patch as "no name
// present" and dropping the phone is the right call — we want the
// customer to re-provide a valid name, not to silently keep a half-
// understood phone.
// ---------------------------------------------------------------------------
const REQUESTED_SLOT_NAME_SCOPE: ReadonlyArray<{
  requested: SlotName;
  phoneField: "sender_phone" | "recipient_phone";
  nameField: "sender_name" | "recipient_name";
}> = [
  {
    requested: "sender_name",
    phoneField: "sender_phone",
    nameField: "sender_name",
  },
  {
    requested: "recipient_name",
    phoneField: "recipient_phone",
    nameField: "recipient_name",
  },
];

function applyRequestedSlotNameScope(
  patch: BookingFieldPatch,
  dialogState: DialogState | null,
): { patch: BookingFieldPatch; rejections: Array<{ field: string; received: string }> } {
  const rejections: Array<{ field: string; received: string }> = [];
  const requested = dialogState?.requestedSlot?.name ?? null;
  if (!requested) return { patch, rejections };
  const entry = REQUESTED_SLOT_NAME_SCOPE.find((e) => e.requested === requested);
  if (!entry) return { patch, rejections };
  const phoneVal = patch[entry.phoneField];
  const nameVal = patch[entry.nameField];
  const hasPhoneWrite = fieldHasValue(phoneVal);
  const hasNameWrite = fieldHasValue(nameVal);
  if (hasPhoneWrite && !hasNameWrite) {
    const next: BookingFieldPatch = { ...patch };
    next[entry.phoneField] = null;
    rejections.push({ field: entry.phoneField, received: String(phoneVal) });
    return { patch: next, rejections };
  }
  return { patch, rejections };
}

// ---------------------------------------------------------------------------
// Edit-intent detector
//
// Two-part check: (1) the `source_quote` must contain an explicit edit
// signal — either a natural-language edit verb / negation, a
// `<label> <value> to <value>` pattern, or the Arabic/Arabizi equivalents;
// AND (2) the conversation stage must be one where the customer has
// plausibly already seen the filled value (so the new value is a
// correction, not an out-of-nowhere write).
//
// Both conditions intentionally err on the conservative side. A false
// negative here just means the pre-existing conflict path runs — the LLM
// will see `slot_conflicts` and ask for disambiguation, which is the
// current (suboptimal but safe) behavior. A false positive would let a
// non-edit message silently overwrite a filled slot, which is strictly
// worse than the status quo, so the regexes only match explicit cues.
//
// This is the immediate production fix for the "block 3 to block 4"
// post-summary edit bug (incident 2026-04-19). The long-term shape is
// for the LLM's `apply_booking_field` op to carry an explicit
// `intent: "edit"` tag in the schema, at which point this detector
// becomes a fallback for when the LLM forgets to set it. See
// `delivery/ARCHITECTURE.md` step 3 (apply boundary — evidence contract).
// ---------------------------------------------------------------------------

/** English/Arabizi edit verbs. Case-insensitive. Requires a word boundary
 *  so "updated" matches but "updatedness" does not. */
const EDIT_VERBS_LATIN =
  /\b(?:change(?:d|s|ing)?|edit(?:ed|s|ing)?|update(?:d|s|ing)?|correct(?:ion|ed|s|ing)?|fix(?:ed|es|ing)?|replace(?:d|s|ing)?|revise(?:d|s|ing)?|instead|rather|actually|make\s+it|sorry[,!.\s]+(?:i\s+meant|meant)|i\s+meant)\b/iu;

/** Explicit negation patterns that signal a correction. "no, make it 10",
 *  "not 9, 10", "it's not the old one". Kept narrow to avoid matching
 *  the common fill-time "no" answer to yes/no questions. */
const EDIT_NEGATION_LATIN =
  /(?:\bno[,!.\-\s]+(?:it'?s|make\s+it|change|actually|its|let'?s\s+make)\b|\bnot\s+(?:the|a|an|\d))/iu;

/** `<label> <value> to <value>` pattern. The leading label ties the
 *  preposition `to` to a known field, so "block 3 to block 4" matches
 *  but "send it to me" doesn't. */
const EDIT_FIELD_TO_VALUE =
  /\b(?:block|street|house|building|floor|flat|apt|apartment|door|office|gate|avenue|phone|number|sender|recipient|pickup|delivery|drop\s?off|name)s?\s+\S+\s+to\s+\S+/iu;

/** `from X to Y` pattern with two concrete values. Required two values
 *  mitigates matches like "from Jabriya to Surra" where X and Y are
 *  area names (that's a route quote, not an edit). */
const EDIT_FROM_TO = /\bfrom\s+\S+\s+to\s+\S+/iu;

/** Arabic edit verbs. The character-class `[يّ]` lets us accept both
 *  tashkeel'd and bare forms ("غيّر" / "غير", "بدّل" / "بدل"). */
const EDIT_VERBS_ARABIC =
  /(?:بد[ّ]?ل|غي[يّ]?ر|عد[ّ]?ل|عدلها|صح[يّ]?ح|الصح(?:يح)?|\bمش\b|\bمو\b)/u;

/** Arabizi (Romanized Arabic) edit verbs. Same semantics as above but
 *  written in Latin script, which is common in Kuwait WhatsApp. */
const EDIT_VERBS_ARABIZI =
  /\b(?:badel|badal|baddel|ghayyer|ghair|3addel|3adel|addel|sa77e7|sahheh|mub|mu)\b/iu;

/** Conversation stages where an explicit edit is plausible: the customer
 *  has either already provided booking fields (collecting_booking_details),
 *  seen the summary (summary_shown), or is looking at the summary waiting
 *  for confirmation (awaiting_confirmation). `quoted` is excluded — there
 *  are no filled booking slots to "edit" yet; any different value is a
 *  fresh write, not a correction. */
const EDIT_ELIGIBLE_STAGES: ReadonlySet<string> = new Set([
  "collecting_booking_details",
  "summary_shown",
  "awaiting_confirmation",
]);

/** Public for tests. Returns true if the given source quote contains at
 *  least one explicit edit signal. */
export function sourceQuoteLooksLikeEdit(quote: string | null | undefined): boolean {
  if (!fieldHasValue(quote)) return false;
  const q = quote.trim();
  if (q.length < 3) return false;
  return (
    EDIT_VERBS_LATIN.test(q) ||
    EDIT_NEGATION_LATIN.test(q) ||
    EDIT_FIELD_TO_VALUE.test(q) ||
    EDIT_FROM_TO.test(q) ||
    EDIT_VERBS_ARABIC.test(q) ||
    EDIT_VERBS_ARABIZI.test(q)
  );
}

/** Public for tests. Returns true if the given stage is one where
 *  edits are expected. */
export function stageAllowsEdit(stage: string | null | undefined): boolean {
  if (!fieldHasValue(stage)) return false;
  return EDIT_ELIGIBLE_STAGES.has(stage);
}

// ---------------------------------------------------------------------------
// Public entry point
// ---------------------------------------------------------------------------

/**
 * Apply an ordered list of proposals to a booking draft, running the
 * evidence contract on each. Proposals are applied sequentially so a
 * later proposal sees the state written by earlier proposals (important
 * for the ambiguous-pair check: the sender fields from a fast-path
 * proposal this turn should disambiguate a later LLM proposal).
 */
export function applyProposals(
  proposals: Proposal[],
  ctx: BoundaryContext,
): BoundaryResult {
  let draft: BookingDraft = ctx.draft;
  let dialogState: DialogState | null = ctx.dialogState;
  const applied: Array<keyof BookingFieldPatch> = [];
  const rejections: BoundaryRejection[] = [];
  const conflicts: SlotConflict[] = [];
  const normalizations: BoundaryNormalization[] = [];
  let requestedSlotOverride: SlotName | null = null;
  let senderPhoneDecision: PhoneDecision | null = null;

  for (const proposal of proposals) {
    let patch: BookingFieldPatch = { ...proposal.patch };
    const sourceQuote = proposal.source_quote;

    // ---------------------------------------------------------------
    // 1. Source-quote gate
    // ---------------------------------------------------------------
    const quoteMissing =
      (proposal.source === "fast_path" || proposal.source === "llm") &&
      !fieldHasValue(sourceQuote);
    if (quoteMissing) {
      for (const [key, value] of Object.entries(patch)) {
        if (value == null) continue;
        rejections.push({
          field: key,
          reason: "missing_source_quote",
          received: String(value),
          source: proposal.source,
        });
      }
      continue;
    }

    // ---------------------------------------------------------------
    // 1b. WhatsApp-equivalence normalization.
    //
    // Runs before any gate so downstream checks see the semantically-
    // correct patch. Not a rejection — logged on `normalizations` for
    // provenance. Skipped for carryover (carried-over phones are
    // already-trusted values).
    // ---------------------------------------------------------------
    if (proposal.source !== "carryover") {
      const waNorm = normalizeWhatsappEquivalence(patch, ctx.whatsappNumber);
      if (waNorm.normalized) {
        patch = waNorm.patch;
        normalizations.push({
          ...waNorm.normalized,
          source: proposal.source,
        });
      }
    }

    // ---------------------------------------------------------------
    // 2. Ambiguous-pair guard (skipped for carryover)
    // ---------------------------------------------------------------
    if (proposal.source !== "carryover") {
      const ambiguousDecision = evaluateAmbiguousPair({
        op: {
          sender_name: patch.sender_name ?? null,
          sender_phone: patch.sender_phone ?? null,
          recipient_name: patch.recipient_name ?? null,
          recipient_phone: patch.recipient_phone ?? null,
          phone_decision: patch.phone_decision ?? null,
          source_quote: sourceQuote ?? null,
        },
        draft: {
          senderName: draft.senderName ?? null,
          senderPhone: draft.senderPhone ?? null,
          recipientName: draft.recipientName ?? null,
          recipientPhone: draft.recipientPhone ?? null,
        },
      });
      if (ambiguousDecision.action === "reject_recipient_write") {
        for (const field of ambiguousDecision.dropFields) {
          const received = String(patch[field] ?? "");
          patch[field] = null;
          rejections.push({
            field,
            reason: "ambiguous_pair_sender_unresolved",
            received,
            source: proposal.source,
          });
        }
        if (dialogState) {
          dialogState = setRequestedSlot(dialogState, {
            name: ambiguousDecision.requestedSlot as SlotName,
            options: null,
            askedTs: Date.now(),
          });
        }
        requestedSlotOverride =
          requestedSlotOverride ?? (ambiguousDecision.requestedSlot as SlotName);
      }
    }

    // ---------------------------------------------------------------
    // 3. Coherence gate (skipped for carryover)
    //
    // We classify each proposed name value as an answer to its slot.
    // Anything that isn't a confident `answer` (greetings,
    // acknowledgments, questions, topic-changes) is rejected — phones
    // and addresses keep their shape-only validation path.
    // ---------------------------------------------------------------
    if (proposal.source !== "carryover") {
      for (const entry of COHERENCE_GATED_FIELDS) {
        const value = patch[entry.field];
        if (!fieldHasValue(value)) continue;
        const decision = classifyResponseForSlot({
          text: value,
          slot: entry.slot,
        });
        if (decision.kind === "answer") continue;
        // Ambiguous on a strict slot (names are strict) is also a
        // rejection — `isAcceptableSlotResponse` would have returned
        // `acceptable: false` for it too.
        const received = value;
        patch[entry.field] = null;
        rejections.push({
          field: entry.field,
          reason: coherenceReasonCode(decision),
          received,
          source: proposal.source,
        });
      }
    }

    // ---------------------------------------------------------------
    // 3b. Requested-slot name-scope guard (skipped for carryover).
    //
    // On a name-requested turn, a same-side phone write without an
    // accompanying name write is dropped. See
    // `applyRequestedSlotNameScope` above. The WA-equivalence step
    // already rewrote WA-equivalent phones into `phone_decision`, so
    // this only affects genuinely-different phones.
    // ---------------------------------------------------------------
    if (proposal.source !== "carryover") {
      const scoped = applyRequestedSlotNameScope(patch, dialogState);
      if (scoped.rejections.length > 0) {
        patch = scoped.patch;
        for (const r of scoped.rejections) {
          rejections.push({
            field: r.field,
            reason: "requested_slot_name_scope",
            received: r.received,
            source: proposal.source,
          });
        }
      }
    }

    // ---------------------------------------------------------------
    // 4. Edit-intent detection.
    //
    // For LLM and fast-path proposals (never carryover — a carried-over
    // identity is not an "edit"), check whether this turn is an
    // explicit edit of an already-filled slot. If so, the downstream
    // `applyBookingFieldPatch` passes `forceOverwrite: true` into
    // every `updateSlot` call for this patch, turning would-be
    // conflicts into silent overrides. See `sourceQuoteLooksLikeEdit`
    // / `stageAllowsEdit` above for the detection contract.
    // ---------------------------------------------------------------
    const editIntent =
      (proposal.source === "llm" || proposal.source === "fast_path") &&
      stageAllowsEdit(ctx.stage) &&
      sourceQuoteLooksLikeEdit(sourceQuote);

    // ---------------------------------------------------------------
    // 5. Shape + apply (existing `applyBookingFieldPatch` pipeline)
    // ---------------------------------------------------------------
    const patchHasAnyValue = Object.values(patch).some((v) => v != null);
    if (!patchHasAnyValue) {
      continue;
    }
    const applyRes = applyBookingFieldPatch({
      draft,
      patch,
      whatsappNumber: ctx.whatsappNumber,
      dialogState,
      dstSource: mapSourceToDstSource(proposal.source),
      editIntent,
    });
    draft = applyRes.draft;
    if (applyRes.dialogState !== undefined && applyRes.dialogState !== null) {
      dialogState = applyRes.dialogState;
    }
    for (const key of applyRes.applied) {
      applied.push(key);
    }
    for (const r of applyRes.rejected) {
      rejections.push({
        field: r.field,
        reason: r.reason,
        received: r.received,
        source: proposal.source,
      });
    }
    if (applyRes.conflicts && applyRes.conflicts.length > 0) {
      for (const c of applyRes.conflicts) conflicts.push(c);
    }
    if (applyRes.senderPhoneDecision) {
      senderPhoneDecision = applyRes.senderPhoneDecision;
    }
  }

  return {
    draft,
    dialogState,
    applied,
    rejections,
    conflicts,
    requestedSlotOverride,
    senderPhoneDecision,
    normalizations,
  };
}

// ---------------------------------------------------------------------------
// Convenience builders for call sites
// ---------------------------------------------------------------------------

/**
 * Build a `Proposal` from a fast-path extractor result. Fast-path
 * extractors emit a `BookingFieldPatch` plus the raw customer text they
 * were given; this wraps both into the shape the boundary expects.
 */
export function fastPathProposal(params: {
  patch: BookingFieldPatch;
  sourceQuote: string;
  turnId?: string | null;
}): Proposal {
  return {
    source: "fast_path",
    source_quote: params.sourceQuote,
    patch: params.patch,
    turnId: params.turnId ?? null,
  };
}

/**
 * Build a `Proposal` from a drained LLM `apply_booking_field` op. The
 * op already carries a `source_quote`; the boundary enforces that it's
 * non-empty.
 */
export function llmProposal(params: {
  op: {
    sender_name?: string | null;
    sender_phone?: string | null;
    phone_decision?: PhoneDecision | null;
    recipient_name?: string | null;
    recipient_phone?: string | null;
    address_block?: string | null;
    address_street?: string | null;
    address_house?: string | null;
    address_avenue?: string | null;
    address_extra?: string | null;
    address_role?: AddressRole | null;
    source_quote?: string | null;
    turn_id?: string | null;
  };
}): Proposal {
  const o = params.op;
  return {
    source: "llm",
    source_quote: o.source_quote ?? null,
    turnId: o.turn_id ?? null,
    patch: {
      sender_name: o.sender_name ?? null,
      sender_phone: o.sender_phone ?? null,
      phone_decision: o.phone_decision ?? null,
      recipient_name: o.recipient_name ?? null,
      recipient_phone: o.recipient_phone ?? null,
      address_block: o.address_block ?? null,
      address_street: o.address_street ?? null,
      address_house: o.address_house ?? null,
      address_avenue: o.address_avenue ?? null,
      address_extra: o.address_extra ?? null,
      address_role: o.address_role ?? null,
    },
  };
}
