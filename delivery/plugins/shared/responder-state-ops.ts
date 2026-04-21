/**
 * Shared per-turn buffer where responder tool calls push state operations
 * that the octopus-channel orchestrator drains after the LLM turn completes.
 *
 * This is the single channel that lets the LLM propose state changes via
 * tool calls while the orchestrator (octopus-channel) stays the sole authority
 * on validation, application, and safety enforcement. Tools never mutate
 * controller state directly.
 *
 * Entries are scoped by conversationId. The orchestrator MUST drain after
 * each turn to avoid bleed-through.
 */

export type ResponderBookingFieldOp = {
  op: "apply_booking_field";
  sender_name?: string | null;
  sender_phone?: string | null;
  phone_decision?: "use_whatsapp" | "different" | null;
  recipient_name?: string | null;
  recipient_phone?: string | null;
  address_block?: string | null;
  address_street?: string | null;
  address_house?: string | null;
  // Kuwait address extensions — see booking-draft.ts for semantics.
  address_avenue?: string | null;
  address_extra?: string | null;
  address_role?: "pickup" | "delivery" | null;
  source_quote?: string | null;
  turn_id: string;
};

export type ResponderStartBookingOp = {
  op: "start_booking";
  selected_delivery_type?: string | null;
  source_quote?: string | null;
  turn_id: string;
};

export type ResponderConfirmSummaryOp = {
  op: "confirm_summary";
  source_quote?: string | null;
  turn_id: string;
};

export type ResponderCancelBookingOp = {
  op: "cancel_booking";
  reason?: string | null;
  source_quote?: string | null;
  turn_id: string;
};

export type ResponderHandoffOp = {
  op: "request_handoff";
  reason?: string | null;
  source_quote?: string | null;
  turn_id: string;
};

/**
 * Mid-turn signal from a tool to the orchestrator: the assistant is about to
 * ask the customer for a specific slot (area disambiguation, phone re-send,
 * missing address sub-field, etc). The orchestrator records this on
 * `dialogState.requestedSlot` so the next inbound turn's guards and prompt
 * can route the customer's answer to the correct slot.
 *
 * `options` is an optional list of allowed values for disambiguation menus
 * (e.g. `["Sabah Al-Salem", "Sabah Al Salem University"]`). Empty/omitted
 * means free-form.
 */
export type ResponderSetRequestedSlotOp = {
  op: "set_requested_slot";
  slot: string; // SlotName — kept as string here to avoid a cross-module type import
  options?: string[] | null;
  source_quote?: string | null;
  turn_id: string;
};

/**
 * Mid-turn signal from a tool that ONE leg of the route (pickup OR dropoff)
 * resolved successfully to a canonical area — even if the overall get_price
 * call didn't produce a full quote (e.g. the OTHER leg was ambiguous or
 * not_found). The orchestrator persists these values into
 * `pendingPickupAreaNameEn` / `pendingDropoffAreaNameEn` on the controller
 * entry so subsequent turns can see mid-conversation area progress. This
 * prevents the smuggle-guard false-positive where a disambiguation answer
 * (only answering the other leg) would retroactively strip the already-
 * resolved leg.
 *
 * Cleared on: successful quote (promoted to quote*), area replacement with a
 * different canonical value, order submit/cancel, booking cancellation.
 */
export type ResponderSetPendingAreaOp = {
  op: "set_pending_area";
  field: "pickup_area" | "dropoff_area";
  area_name_en: string | null;
  area_name_ar: string | null;
  turn_id: string;
};

/**
 * Carry fields over from the customer's previously-saved
 * `CustomerProfile.last_successful_order` into the active booking draft.
 * The tool only pushes the INTENT — the orchestrator reads the profile at
 * drain time, revalidates each field through the existing
 * `cleanName`/`cleanPhone`/`cleanAddressPart` helpers, and writes through
 * `applyBookingFieldPatch` with `dstSource: "carryover"` so downstream
 * consumers (summary render, route-reset partition) can distinguish
 * carried-over values from customer-turn values.
 *
 * Buckets are an enumerated set; the LLM / reuse-intent classifier picks
 * the ones the customer actually asked to reuse so partial reuse is
 * first-class ("same sender, different recipient").
 *
 * Bucket semantics:
 *
 *   - `sender_identity`    sender name + sender phone (V1 — implemented)
 *   - `recipient_identity` recipient name + recipient phone (V1 — implemented)
 *   - `payer`              order-level payer attribute (V1 — stub: accepted
 *                          but not written to the draft; payer lives on the
 *                          order, not the draft, and is wired at
 *                          create_simple_order time)
 *   - `pickup_location`    pickup area + block + street + house + avenue +
 *                          extra (V2 — accepted but returns `ask_fresh` for
 *                          now, see the drain handler). When implemented,
 *                          carry-over will be FULL-TUPLE ATOMIC: every field
 *                          must revalidate or the whole bucket skips. This
 *                          avoids the close-but-wrong failure mode where
 *                          block/street match but house has changed.
 *   - `delivery_location`  delivery area + address fields (V2 — same shape
 *                          as pickup_location).
 */
export type CarryOverBucket =
  | "sender_identity"
  | "recipient_identity"
  | "pickup_location"
  | "delivery_location"
  | "payer";

export type ResponderCarryOverFromLastOrderOp = {
  op: "carry_over_from_last_order";
  /** Which buckets to copy. Unknown values are ignored. Empty array is a no-op. */
  buckets: CarryOverBucket[];
  source_quote?: string | null;
  turn_id: string;
};

/**
 * LLM-side structured interpretation of the customer's option intent
 * (Phase 1, 2026-04-20 "one source of truth for option resolution").
 *
 * ## Why this op exists
 *
 * Before this op, option resolution was double-sourced: the server ran
 * regex/token matching over the raw customer text
 * (`matchQuotedOptionDiscriminated`) AND the LLM independently understood
 * the utterance but had no typed channel to share that understanding. On
 * phrases the matcher didn't cover — dialect variants, typos, rare
 * synonyms, inverted word order — the LLM knew the right answer but the
 * server ignored it. And when the two implicitly disagreed, we had no
 * way to detect that disagreement.
 *
 * This op is the LLM's *proposal* for the `{class, tier}` the customer
 * meant, in structured form. It is PROPOSE-ONLY — emitting the op does
 * not mutate state. The orchestrator's
 * `resolveOptionFromProposals` (in `quoted-options.ts`) reconciles this
 * proposal with the deterministic raw-text outcome and commits via the
 * same `applySelectedQuotedOptionToController` path as today's
 * deterministic matcher.
 *
 * ## Fields
 *
 * `class`   — vehicle/service class. Null when the customer didn't
 *             signal a class (tier-only utterance like "express").
 * `tier`    — speed tier. Null when the customer didn't signal a tier
 *             (class-only utterance like "helper" or "sedan").
 * `qualifiers` — free-form short tokens the LLM extracted as evidence
 *             ("cooled", "refrigerated", "ref van", "مبرد"). Used for
 *             observability + future disambiguation work; the resolver
 *             does not key on these today.
 * `source_quote` — the substring of the customer's actual inbound text
 *             the LLM based this interpretation on. The orchestrator
 *             validates this appears in the turn's visible text and
 *             drops the proposal if it doesn't — same contract as the
 *             `apply_booking_field` evidence check. Prevents the LLM
 *             from synthesizing an interpretation out of earlier
 *             conversation or its own prior reply.
 * `confidence` — `"high"` when the LLM is confident the mapping is
 *             correct, `"low"` when it is guessing. The resolver only
 *             commits on high-confidence LLM proposals; low-confidence
 *             ones are observability signals only.
 *
 * ## What the LLM should emit
 *
 * Only when the customer utterance in THIS turn is a selection or a
 * switch between already-quoted options. Not for generic booking
 * questions, price asks, or any message that does not name an option.
 * If the customer's phrasing is genuinely ambiguous, the LLM should
 * still emit the op with the fields it is confident about (e.g.
 * `{class:"cooled_van", tier:null, confidence:"low"}`) — that signal is
 * enough for the resolver to steer to clarify on ambiguity rather than
 * auto-pick.
 */
export type ResponderOptionInterpretationOp = {
  op: "propose_option_interpretation";
  class: "sedan" | "van" | "cooled_van" | "helper" | null;
  tier: "normal" | "fast" | null;
  qualifiers?: string[] | null;
  source_quote: string;
  confidence: "high" | "low";
  turn_id: string;
};

export type ResponderStateOp =
  | ResponderBookingFieldOp
  | ResponderStartBookingOp
  | ResponderConfirmSummaryOp
  | ResponderCancelBookingOp
  | ResponderHandoffOp
  | ResponderSetRequestedSlotOp
  | ResponderSetPendingAreaOp
  | ResponderCarryOverFromLastOrderOp
  | ResponderOptionInterpretationOp;

// Class-10 fix (2026-04-21): `module_instance_isolation_drops_responder_ops`.
//
// Failure mode: the pricing tool (in the `riders-tools` plugin) pushes
// `set_pending_area` / `set_requested_slot` ops into `buffer`, but the
// `octopus-channel` drain reads an EMPTY buffer for the same key and never
// emits the `[one-brain] drained` log. Two plugins importing the same
// relative path (`../shared/responder-state-ops`) should share one module
// instance under Node ESM's URL-keyed cache, but the OpenClaw plugin loader
// has at times instantiated `plugins/shared/*` modules per-plugin (sandboxed
// import contexts, separate bundle outputs, etc). The symptom is that push
// and drain observe DIFFERENT `Map` instances in the same process, and
// every cross-plugin responder op vanishes.
//
// Invariant: a `pushResponderStateOp` call must be visible to a subsequent
// `drainResponderStateOps` call in the same process, regardless of which
// plugin bundle owns each side.
//
// Fix: pin the backing Map on `globalThis` so it is process-singleton even
// when the module source is duplicated. The type cast is intentional —
// `globalThis` is untyped here on purpose so we don't leak the op shape to
// unrelated code paths.
const __RESPONDER_OPS_BUFFER_KEY = "__ridersResponderStateOpsBuffer__";
const buffer: Map<string, ResponderStateOp[]> =
  ((globalThis as any)[__RESPONDER_OPS_BUFFER_KEY] as Map<string, ResponderStateOp[]> | undefined) ??
  ((globalThis as any)[__RESPONDER_OPS_BUFFER_KEY] = new Map<string, ResponderStateOp[]>());
const TURN_OP_LIMIT = 32;

function normalizeKey(raw: string | null | undefined): string {
  return String(raw || "").trim();
}

function collectKeys(
  primary: string,
  aliases?: readonly string[] | null,
): string[] {
  const keys: string[] = [];
  const seen = new Set<string>();
  const add = (raw: string | null | undefined) => {
    const key = normalizeKey(raw);
    if (!key || seen.has(key)) return;
    seen.add(key);
    keys.push(key);
  };
  add(primary);
  if (aliases) {
    for (const alias of aliases) add(alias);
  }
  return keys;
}

/**
 * Push a responder state op into the per-turn buffer.
 *
 * `aliases` is an optional list of additional keys to mirror the op under.
 * The Octopus tool-context sometimes disagrees with the orchestrator on
 * which identifier is "the" conversation id (SessionKey-embedded id vs
 * `To=octopus:<replyTarget>` vs NativeChannelId). When the tool doesn't
 * know which one the drain will look up, it pushes under all candidates;
 * `drainResponderStateOps` merges + dedups at drain time so the customer
 * never loses a clarification op just because of a key-shape drift.
 *
 * Dedup key is `op.op|op.turn_id|<field-or-slot-discriminator>` — pushing
 * the same op under multiple aliases yields ONE drained op, not N copies.
 */
export function pushResponderStateOp(
  conversationId: string,
  op: ResponderStateOp,
  aliases?: readonly string[] | null,
): void {
  const keys = collectKeys(conversationId, aliases);
  if (keys.length === 0) return;
  for (const key of keys) {
    const existing = buffer.get(key) || [];
    if (existing.length >= TURN_OP_LIMIT) continue;
    existing.push(op);
    buffer.set(key, existing);
  }
  // Class-10 observability: emit an unconditional line every push so we
  // can correlate push -> drain across plugin boundaries without relying
  // on the caller having an `api.logger`. Size-of-buffer is included so a
  // divergent (per-plugin) instance is immediately visible in logs.
  try {
    // eslint-disable-next-line no-console
    console.log(
      `[responder-ops/buffer-push] primary=${conversationId} keys=${JSON.stringify(keys)} op=${op.op} turn_id=${String((op as { turn_id?: string }).turn_id || "")} buffer_size=${buffer.size}`,
    );
  } catch {}
}

function opDedupKey(op: ResponderStateOp): string {
  const base = `${op.op}|${(op as { turn_id?: string }).turn_id || ""}`;
  switch (op.op) {
    case "apply_booking_field":
      return `${base}|af|${op.address_role || ""}|${op.sender_name || ""}|${op.sender_phone || ""}|${op.recipient_name || ""}|${op.recipient_phone || ""}|${op.address_block || ""}|${op.address_street || ""}|${op.address_house || ""}`;
    case "set_pending_area":
      return `${base}|${op.field}|${op.area_name_en || ""}`;
    case "set_requested_slot":
      return `${base}|${op.slot}|${(op.options || []).join(",")}`;
    case "carry_over_from_last_order":
      return `${base}|${(op.buckets || []).join(",")}`;
    case "propose_option_interpretation":
      return `${base}|${op.class || ""}|${op.tier || ""}|${op.confidence}`;
    default:
      return base;
  }
}

/**
 * Drain responder state ops. `conversationId` is the primary key; `aliases`
 * are optional additional keys to drain + merge (dedup'd by turn_id + op
 * shape). All matching buffers are cleared atomically.
 */
export function drainResponderStateOps(
  conversationId: string,
  aliases?: readonly string[] | null,
): ResponderStateOp[] {
  const keys = collectKeys(conversationId, aliases);
  if (keys.length === 0) return [];
  const merged: ResponderStateOp[] = [];
  const seen = new Set<string>();
  const perKeyCounts: Record<string, number> = {};
  for (const key of keys) {
    const existing = buffer.get(key) || [];
    perKeyCounts[key] = existing.length;
    if (existing.length === 0) continue;
    for (const op of existing) {
      const dedup = opDedupKey(op);
      if (seen.has(dedup)) continue;
      seen.add(dedup);
      merged.push(op);
    }
    buffer.delete(key);
  }
  // Class-10 observability: emit an unconditional line every drain. If
  // every `keys[k]` shows 0 despite a same-turn push, that proves the push
  // and drain are reading different `buffer` instances.
  try {
    // eslint-disable-next-line no-console
    console.log(
      `[responder-ops/buffer-drain] primary=${conversationId} keys=${JSON.stringify(keys)} per_key=${JSON.stringify(perKeyCounts)} drained=${merged.length} buffer_size=${buffer.size}`,
    );
  } catch {}
  return merged;
}

export function clearResponderStateOps(
  conversationId: string,
  aliases?: readonly string[] | null,
): void {
  const keys = collectKeys(conversationId, aliases);
  for (const key of keys) buffer.delete(key);
}

export function peekResponderStateOps(conversationId: string): ResponderStateOp[] {
  const key = normalizeKey(conversationId);
  if (!key) return [];
  return [...(buffer.get(key) || [])];
}

/**
 * Per-field validation for apply_booking_field ops. The tool runs this
 * synchronously before pushing, and the orchestrator runs it again when
 * draining — defense-in-depth so garbage can never reach bookingDraft.
 */

export type BookingFieldValidationError = {
  field:
    | "sender_name"
    | "sender_phone"
    | "recipient_name"
    | "recipient_phone"
    | "address_block"
    | "address_street"
    | "address_house"
    | "address_avenue"
    | "address_extra";
  reason: string;
  received: string;
};

export type ApplyBookingFieldValidationResult = {
  cleaned: ResponderBookingFieldOp;
  errors: BookingFieldValidationError[];
  hasAnyValidField: boolean;
};

const PHONE_MIN_DIGITS = 7;
const PHONE_MAX_DIGITS = 15;
const NAME_MIN_LEN = 2;
const NAME_MAX_LEN = 60;
// Real names in Kuwaiti delivery context are 1–4 tokens (Aziz, Aziz Al
// Mulla, Mohammed Hamad Al Sabah). Strings longer than this are almost
// always a snippet of conversation that the LLM mis-attributed to a name
// field (e.g. "Is this the cheapest option").
const NAME_MAX_WORDS = 4;
const ADDRESS_PART_MAX_LEN = 30;
const ADDRESS_EXTRA_MAX_LEN = 200;

// Strings starting with these tokens are almost certainly questions or
// conversational fragments the LLM mis-attributed to a name field.
// Covered: English interrogatives + common Arabic interrogatives in both
// proper script and Arabizi. Each pattern matches the prefix at the
// start of the trimmed value, followed by whitespace, end-of-string, or
// punctuation. We use an explicit non-letter lookahead instead of `\b`
// because JS word boundaries don't handle Arabic letters reliably across
// engines.
const NAME_QUESTION_PREFIXES: RegExp[] = [
  /^(is|are|am|do|does|did|can|could|will|would|should|may|might|have|has|had|was|were)(?=$|[^\p{L}])/iu,
  /^(what|when|where|why|who|whom|whose|which|how)(?=$|[^\p{L}])/iu,
  /^(هل|شو|شنو|متى|وين|كيف|كم|ليش|منو|اي|ايش)(?=$|[^\p{L}])/u,
  /^(shlon|shlonk|shloon|shloo|shku|shnu|shno|wain|win|kam|kef|kaif|laish|leysh|menu|mno|aysh|esh)(?=$|[^\p{L}])/iu,
];

function looksLikeQuestion(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return false;
  if (/[?؟]/.test(trimmed)) return true;
  return NAME_QUESTION_PREFIXES.some((rx) => rx.test(trimmed));
}

function countNameWords(value: string): number {
  const trimmed = value.trim();
  if (!trimmed) return 0;
  return trimmed.split(/\s+/u).filter(Boolean).length;
}

const ARTIFACT_PATTERNS: RegExp[] = [
  /^ok$/i,
  /^okay$/i,
  /^yes$/i,
  /^no$/i,
  /^yep$/i,
  /^sure$/i,
  /^thanks?$/i,
  /^ty$/i,
  /^thenumber\s+is$/i,
  /^the\s+number\s+is$/i,
  /^confirm$/i,
  /^proceed$/i,
  /^go\s*ahead$/i,
  /^-+$/,
  /^\.+$/,
  /^(تمام|نعم|اكمل|لا|زين)$/,
];

function looksLikeArtifact(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return true;
  return ARTIFACT_PATTERNS.some((rx) => rx.test(trimmed));
}

function validatePhone(value: string): string | null {
  const stripped = value.replace(/[\s\-()+]/g, "");
  if (!stripped) return "phone_empty";
  if (!/^\d+$/.test(stripped)) return "phone_contains_non_digits";
  if (stripped.length < PHONE_MIN_DIGITS) return "phone_too_short";
  if (stripped.length > PHONE_MAX_DIGITS) return "phone_too_long";
  return null;
}

/**
 * Validate a person-name string. Returns null when the value passes all
 * shape rules, or a short snake_case reason when it doesn't.
 *
 * Exported so the pre-LLM fast-path (`fast-path-extractor.ts`) can use
 * the SAME shape policy as the post-LLM apply-boundary. Without this
 * single source of truth, the fast-path has its own (weaker) name
 * predicate and can write conversational fragments straight into the
 * draft, bypassing every LLM-side guard. That class of bug is exactly
 * what corrupted "Is this the cheapest option" → sender_name on
 * 2026-04-19 13:42 (live).
 *
 * Relationship to slot-response coherence
 * ---------------------------------------
 * `validateName` is a pure VALUE shape check ("does the string the LLM
 * emitted look like a plausible name?"). It runs on every name op,
 * regardless of conversation context. The question-shape and
 * word-count checks below are value-level heuristics: they catch the
 * case where the LLM emits `{sender_name: "Is this the cheapest
 * option"}` even when we can't see the customer's original message.
 *
 * The complementary check — "did the customer's MESSAGE coherently
 * answer the slot we asked for?" — lives in `slot-response-coherence`
 * and runs at both write paths (fast-path and apply-boundary) with
 * access to `visibleText + requestedSlot`. Coherence catches the case
 * where `validateName("Aziz")` passes in isolation but the customer's
 * raw message was "What is the cheapest? Aziz" and the LLM mis-routed
 * a name it fabricated out of a fragment.
 *
 * Keep both. They cover different failure modes.
 */
export function validateName(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed.length < NAME_MIN_LEN) return "name_too_short";
  if (trimmed.length > NAME_MAX_LEN) return "name_too_long";
  if (/^\d+$/.test(trimmed)) return "name_is_digits";
  if (looksLikeArtifact(trimmed)) return "name_is_artifact";
  // Letters (any script), spaces, hyphens, apostrophes, dots. No digits.
  if (!/^[\p{L}][\p{L}\s'\-.]*$/u.test(trimmed)) return "name_has_invalid_chars";
  // Reject conversational fragments / questions that the LLM may have
  // mis-attributed to a name field. Real names don't start with
  // interrogatives ("Is this the cheapest option") and don't contain
  // question marks.
  if (looksLikeQuestion(trimmed)) return "name_looks_like_question";
  // Reject overly-long word counts. Real Kuwaiti names rarely exceed 4
  // tokens; strings beyond that are almost always conversation snippets.
  if (countNameWords(trimmed) > NAME_MAX_WORDS) return "name_too_many_words";
  return null;
}

function validateAddressPart(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return "address_part_empty";
  if (trimmed.length > ADDRESS_PART_MAX_LEN) return "address_part_too_long";
  if (looksLikeArtifact(trimmed)) return "address_part_is_artifact";
  if (!/[\p{L}\p{N}]/u.test(trimmed)) return "address_part_no_alnum";
  return null;
}

function validateAddressExtra(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return "address_extra_empty";
  if (trimmed.length > ADDRESS_EXTRA_MAX_LEN) return "address_extra_too_long";
  if (looksLikeArtifact(trimmed)) return "address_extra_is_artifact";
  if (!/[\p{L}\p{N}]/u.test(trimmed)) return "address_extra_no_alnum";
  return null;
}

export function validateApplyBookingFieldOp(
  op: ResponderBookingFieldOp,
): ApplyBookingFieldValidationResult {
  const errors: BookingFieldValidationError[] = [];
  const cleaned: ResponderBookingFieldOp = { ...op };

  const checks: Array<{
    field: BookingFieldValidationError["field"];
    value: string | null | undefined;
    validate: (v: string) => string | null;
  }> = [
    { field: "sender_name", value: op.sender_name, validate: validateName },
    { field: "sender_phone", value: op.sender_phone, validate: validatePhone },
    { field: "recipient_name", value: op.recipient_name, validate: validateName },
    { field: "recipient_phone", value: op.recipient_phone, validate: validatePhone },
    { field: "address_block", value: op.address_block, validate: validateAddressPart },
    { field: "address_street", value: op.address_street, validate: validateAddressPart },
    { field: "address_house", value: op.address_house, validate: validateAddressPart },
    { field: "address_avenue", value: op.address_avenue, validate: validateAddressPart },
    { field: "address_extra", value: op.address_extra, validate: validateAddressExtra },
  ];

  for (const check of checks) {
    if (check.value == null) continue;
    if (typeof check.value !== "string") continue;
    const reason = check.validate(check.value);
    if (reason) {
      errors.push({ field: check.field, reason, received: check.value });
      (cleaned as any)[check.field] = null;
    }
  }

  const hasAnyValidField = Boolean(
    cleaned.sender_name ||
      cleaned.sender_phone ||
      cleaned.phone_decision ||
      cleaned.recipient_name ||
      cleaned.recipient_phone ||
      cleaned.address_block ||
      cleaned.address_street ||
      cleaned.address_house ||
      cleaned.address_avenue ||
      cleaned.address_extra,
  );

  return { cleaned, errors, hasAnyValidField };
}

/**
 * Sanity check a finalized booking draft before confirm_summary is accepted.
 * Returns a list of problems. An empty list means the draft is safe to place.
 */
export type DraftSanityProblem = {
  field: string;
  reason: string;
  received: string;
};

export function sanityCheckBookingDraft(draft: {
  senderName?: string | null;
  senderPhone?: string | null;
  recipientName?: string | null;
  recipientPhone?: string | null;
  pickupAddressBlock?: string | null;
  pickupAddressStreet?: string | null;
  pickupAddressHouse?: string | null;
  deliveryAddressBlock?: string | null;
  deliveryAddressStreet?: string | null;
  deliveryAddressHouse?: string | null;
}): DraftSanityProblem[] {
  const problems: DraftSanityProblem[] = [];

  const nameChecks: Array<{ field: string; value: string | null | undefined }> = [
    { field: "sender_name", value: draft.senderName },
    { field: "recipient_name", value: draft.recipientName },
  ];
  for (const c of nameChecks) {
    if (!c.value) {
      problems.push({ field: c.field, reason: "missing", received: "" });
      continue;
    }
    const err = validateName(c.value);
    if (err) problems.push({ field: c.field, reason: err, received: c.value });
  }

  const phoneChecks: Array<{ field: string; value: string | null | undefined }> = [
    { field: "sender_phone", value: draft.senderPhone },
    { field: "recipient_phone", value: draft.recipientPhone },
  ];
  for (const c of phoneChecks) {
    if (!c.value) {
      problems.push({ field: c.field, reason: "missing", received: "" });
      continue;
    }
    const err = validatePhone(c.value);
    if (err) problems.push({ field: c.field, reason: err, received: c.value });
  }

  const addressChecks: Array<{ field: string; value: string | null | undefined }> = [
    { field: "pickup_block", value: draft.pickupAddressBlock },
    { field: "pickup_street", value: draft.pickupAddressStreet },
    { field: "pickup_house", value: draft.pickupAddressHouse },
    { field: "delivery_block", value: draft.deliveryAddressBlock },
    { field: "delivery_street", value: draft.deliveryAddressStreet },
    { field: "delivery_house", value: draft.deliveryAddressHouse },
  ];
  for (const c of addressChecks) {
    if (!c.value) {
      problems.push({ field: c.field, reason: "missing", received: "" });
      continue;
    }
    const err = validateAddressPart(c.value);
    if (err) problems.push({ field: c.field, reason: err, received: c.value });
  }

  return problems;
}

// ---------------------------------------------------------------------------
// Option-interpretation validator (Phase 1, 2026-04-20).
//
// Shape-only check — semantic reconciliation against the catalog lives in
// `resolveOptionFromProposals` (`quoted-options.ts`). This function rejects
// ops that are structurally malformed before they reach the resolver.
// ---------------------------------------------------------------------------

const OPTION_INTERPRETATION_VALID_CLASSES = new Set([
  "sedan",
  "van",
  "cooled_van",
  "helper",
]);
const OPTION_INTERPRETATION_VALID_TIERS = new Set(["normal", "fast"]);
const OPTION_INTERPRETATION_VALID_CONFIDENCES = new Set(["high", "low"]);
const OPTION_INTERPRETATION_SOURCE_QUOTE_MAX_LEN = 200;
const OPTION_INTERPRETATION_QUALIFIER_MAX_COUNT = 8;
const OPTION_INTERPRETATION_QUALIFIER_MAX_LEN = 40;

export type OptionInterpretationValidationError = {
  field: "class" | "tier" | "source_quote" | "confidence" | "qualifiers";
  reason: string;
  received?: string;
};

/**
 * Shape-validate an incoming `propose_option_interpretation` op. Returns
 * a cleaned op (field types narrowed) plus the list of validation errors.
 * Called by the tool registration synchronously before pushing AND by the
 * orchestrator when draining — defense-in-depth mirroring
 * `validateApplyBookingFieldOp`.
 *
 * NOTE: `class` and `tier` are independently nullable. A proposal with
 * `{class: "cooled_van", tier: null}` is valid — it tells the resolver
 * "customer clearly signalled the refrigerated-van class but didn't pick
 * normal vs fast". The resolver then falls through to the class-only
 * unique-match rule, or clarify if the catalog has >1 option in that
 * class. At least one of `class` / `tier` must be non-null; otherwise the
 * op carries no useful signal.
 */
export function validateOptionInterpretationOp(input: any): {
  cleaned: ResponderOptionInterpretationOp;
  errors: OptionInterpretationValidationError[];
} {
  const errors: OptionInterpretationValidationError[] = [];
  const rawClass =
    typeof input?.class === "string" ? input.class.trim().toLowerCase() : null;
  const rawTier =
    typeof input?.tier === "string" ? input.tier.trim().toLowerCase() : null;
  const rawConfidence =
    typeof input?.confidence === "string"
      ? input.confidence.trim().toLowerCase()
      : "";
  const rawSourceQuote =
    typeof input?.source_quote === "string" ? input.source_quote.trim() : "";
  const rawTurnId = typeof input?.turn_id === "string" ? input.turn_id : "";

  let cleanedClass: ResponderOptionInterpretationOp["class"] = null;
  if (rawClass && !OPTION_INTERPRETATION_VALID_CLASSES.has(rawClass)) {
    errors.push({
      field: "class",
      reason: "class_unknown",
      received: String(input?.class ?? ""),
    });
  } else if (rawClass) {
    cleanedClass = rawClass as ResponderOptionInterpretationOp["class"];
  }

  let cleanedTier: ResponderOptionInterpretationOp["tier"] = null;
  if (rawTier && !OPTION_INTERPRETATION_VALID_TIERS.has(rawTier)) {
    errors.push({
      field: "tier",
      reason: "tier_unknown",
      received: String(input?.tier ?? ""),
    });
  } else if (rawTier) {
    cleanedTier = rawTier as ResponderOptionInterpretationOp["tier"];
  }

  if (cleanedClass === null && cleanedTier === null) {
    errors.push({
      field: "class",
      reason: "class_and_tier_both_null",
    });
  }

  if (!rawSourceQuote) {
    errors.push({ field: "source_quote", reason: "source_quote_empty" });
  } else if (rawSourceQuote.length > OPTION_INTERPRETATION_SOURCE_QUOTE_MAX_LEN) {
    errors.push({
      field: "source_quote",
      reason: "source_quote_too_long",
      received: String(rawSourceQuote.length),
    });
  }

  if (!OPTION_INTERPRETATION_VALID_CONFIDENCES.has(rawConfidence)) {
    errors.push({
      field: "confidence",
      reason: "confidence_unknown",
      received: String(input?.confidence ?? ""),
    });
  }

  let cleanedQualifiers: string[] | null = null;
  if (input?.qualifiers !== undefined && input?.qualifiers !== null) {
    if (!Array.isArray(input.qualifiers)) {
      errors.push({ field: "qualifiers", reason: "qualifiers_not_array" });
    } else {
      const out: string[] = [];
      for (const q of input.qualifiers) {
        if (typeof q !== "string") continue;
        const trimmed = q.trim();
        if (!trimmed) continue;
        if (trimmed.length > OPTION_INTERPRETATION_QUALIFIER_MAX_LEN) continue;
        out.push(trimmed);
        if (out.length >= OPTION_INTERPRETATION_QUALIFIER_MAX_COUNT) break;
      }
      cleanedQualifiers = out.length > 0 ? out : null;
    }
  }

  const cleaned: ResponderOptionInterpretationOp = {
    op: "propose_option_interpretation",
    class: cleanedClass,
    tier: cleanedTier,
    qualifiers: cleanedQualifiers,
    source_quote: rawSourceQuote.slice(0, OPTION_INTERPRETATION_SOURCE_QUOTE_MAX_LEN),
    confidence:
      (rawConfidence as ResponderOptionInterpretationOp["confidence"]) || "low",
    turn_id: rawTurnId,
  };

  return { cleaned, errors };
}
