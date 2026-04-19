/**
 * Booking draft — single source of truth for the one-brain architecture.
 *
 * This file owns the SEMANTICS of a booking draft: types, validation, and
 * merging. The LLM and the tools only ever interact with a BookingDraft via
 * the helpers in this file. The controller persists it, guards read it, and
 * the order-placement boundary validates it.
 *
 * It intentionally reuses `PersistedBookingDraft` from `conversation-policy`
 * so that the existing persistence layer keeps working unchanged.
 */

import type {
  PersistedBookingDraft,
  PersistedBookingLocation,
} from "./conversation-policy.js";
import {
  type DialogState,
  type SlotName,
  type SlotSource,
  isDialogStateEnabled,
  mirrorDialogStateToDraft,
  slotNameForBookingField,
  updateSlot,
} from "./dialog-state.js";

export type BookingDraft = PersistedBookingDraft;
export type BookingLocation = PersistedBookingLocation;

export type AddressRole = "pickup" | "delivery";
export type PhoneDecision = "use_whatsapp" | "different";

export type BookingFieldPatch = {
  sender_name?: string | null;
  sender_phone?: string | null;
  phone_decision?: PhoneDecision | null;
  recipient_name?: string | null;
  recipient_phone?: string | null;
  address_block?: string | null;
  address_street?: string | null;
  address_house?: string | null;
  // Kuwait address extensions.
  // `address_avenue` maps to the Kuwait "جادة / jadda / jedda / avenue" concept
  // — a distinct road designation separate from street. The backend has a
  // first-class `avenue` field.
  // `address_extra` is a free-form description bag for floor, apartment, office,
  // side-of-block, landmark, gate, or anything else the customer volunteered
  // that doesn't fit block/street/house/avenue. Goes to the driver as notes.
  address_avenue?: string | null;
  address_extra?: string | null;
  address_role?: AddressRole | null;
};

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

export type DraftValidationProblem = {
  field: string;
  reason: string;
  received: string;
};

export const PHONE_MIN_DIGITS = 7;
export const PHONE_MAX_DIGITS = 15;
export const NAME_MIN_LEN = 2;
export const NAME_MAX_LEN = 60;
export const ADDRESS_PART_MAX_LEN = 30;
// `extra` is a sentence-like description (floor, apartment, landmark, etc),
// so it's allowed to be longer and looser than a block/street/house token.
export const ADDRESS_EXTRA_MAX_LEN = 200;

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

export function cleanPhone(value: string | null | undefined): {
  value: string | null;
  reason: string | null;
} {
  if (value == null) return { value: null, reason: null };
  const stripped = String(value).replace(/[\s\-()+]/g, "");
  if (!stripped) return { value: null, reason: "phone_empty" };
  if (!/^\d+$/.test(stripped)) return { value: null, reason: "phone_contains_non_digits" };
  if (stripped.length < PHONE_MIN_DIGITS) return { value: null, reason: "phone_too_short" };
  if (stripped.length > PHONE_MAX_DIGITS) return { value: null, reason: "phone_too_long" };
  return { value: stripped, reason: null };
}

export function cleanName(value: string | null | undefined): {
  value: string | null;
  reason: string | null;
} {
  if (value == null) return { value: null, reason: null };
  const trimmed = String(value).trim().replace(/\s+/g, " ");
  if (!trimmed) return { value: null, reason: "name_empty" };
  if (trimmed.length < NAME_MIN_LEN) return { value: null, reason: "name_too_short" };
  if (trimmed.length > NAME_MAX_LEN) return { value: null, reason: "name_too_long" };
  if (/^\d+$/.test(trimmed)) return { value: null, reason: "name_is_digits" };
  if (looksLikeArtifact(trimmed)) return { value: null, reason: "name_is_artifact" };
  if (!/^[\p{L}][\p{L}\s'\-.]*$/u.test(trimmed)) {
    return { value: null, reason: "name_has_invalid_chars" };
  }
  return { value: trimmed, reason: null };
}

export function cleanAddressPart(value: string | null | undefined): {
  value: string | null;
  reason: string | null;
} {
  if (value == null) return { value: null, reason: null };
  const trimmed = String(value).trim();
  if (!trimmed) return { value: null, reason: "address_part_empty" };
  if (trimmed.length > ADDRESS_PART_MAX_LEN) return { value: null, reason: "address_part_too_long" };
  if (looksLikeArtifact(trimmed)) return { value: null, reason: "address_part_is_artifact" };
  if (!/[\p{L}\p{N}]/u.test(trimmed)) return { value: null, reason: "address_part_no_alnum" };
  return { value: trimmed, reason: null };
}

/**
 * Detect values that look like interior/unit detail rather than a building
 * identifier. These are apartment, flat, floor, office, door, gate, and their
 * Arabic equivalents. Callers use this as a deterministic backstop so that
 * interior details never land in `address_house` — they get rerouted into
 * `address_extra` (where the driver reads them after finding the building).
 *
 * Matches whole words or short tokens; e.g. "door 312", "apt 5", "floor 2",
 * "شقة ٨", "دور 3", "طابق 2", "باب 12", "office A", "gate 7".
 */
export function looksLikeInteriorDetail(value: string | null | undefined): boolean {
  if (value == null) return false;
  const s = String(value).toLowerCase().trim();
  if (!s) return false;
  // English / Arabizi keywords — common and common-variant spellings.
  if (/\b(apt|appt|apartment|apartement|flat|floor|fl|office|door|gate|suite|unit|room|lobby|basement|mezzanine|penthouse|ground\s*floor|first\s*floor|second\s*floor|upper\s*floor|lower\s*floor)\b/.test(s)) return true;
  // Arabic keywords (no word-boundary support for Arabic script in JS regex)
  if (/(شقه|شقة|فلات|دور|طابق|باب|مكتب|بوابة|ارضي|أرضي|علوي|سفلي|قبو)/.test(s)) return true;
  return false;
}

// A valid `address_house` value is a short street-level identifier a driver
// reads off a façade — "17", "23b", "villa 4", "tower A", "bldg 12". It is
// NEVER a sentence or a multi-piece description. This length cap catches the
// case where the LLM dumps an entire address sentence into house without the
// interior keywords triggering. 32 chars is generous for "Villa 123, Tower B".
const ADDRESS_HOUSE_MAX_LEN = 32;

export function looksLikeSuspiciousHouseValue(value: string | null | undefined): boolean {
  if (value == null) return false;
  const s = String(value).trim();
  if (!s) return false;
  if (s.length > ADDRESS_HOUSE_MAX_LEN) return true;
  // No digits anywhere AND more than 2 words → almost certainly not a house
  // number (real pure-text house identifiers are short: "villa", "tower A").
  const hasDigit = /\d/.test(s);
  const wordCount = s.split(/\s+/).filter(Boolean).length;
  if (!hasDigit && wordCount > 2) return true;
  return false;
}

/**
 * Clean a free-form address description ("Floor 3, Apt 12, near the mosque").
 * Allows Arabic + Latin letters, digits, spaces, and common punctuation.
 * Collapses whitespace, rejects obvious artifacts and empty values.
 */
export function cleanAddressExtra(value: string | null | undefined): {
  value: string | null;
  reason: string | null;
} {
  if (value == null) return { value: null, reason: null };
  const trimmed = String(value).trim().replace(/\s+/g, " ");
  if (!trimmed) return { value: null, reason: "address_extra_empty" };
  if (trimmed.length > ADDRESS_EXTRA_MAX_LEN) {
    return { value: null, reason: "address_extra_too_long" };
  }
  if (looksLikeArtifact(trimmed)) return { value: null, reason: "address_extra_is_artifact" };
  if (!/[\p{L}\p{N}]/u.test(trimmed)) return { value: null, reason: "address_extra_no_alnum" };
  return { value: trimmed, reason: null };
}

export function createEmptyBookingDraft(): BookingDraft {
  return {
    senderName: null,
    senderPhone: null,
    recipientName: null,
    recipientPhone: null,
    pickupBlock: null,
    pickupStreet: null,
    pickupHouse: null,
    pickupAvenue: null,
    pickupExtra: null,
    pickupLocation: null,
    deliveryBlock: null,
    deliveryStreet: null,
    deliveryHouse: null,
    deliveryAvenue: null,
    deliveryExtra: null,
    deliveryLocation: null,
    pendingLocation: null,
  };
}

/**
 * Field names on `BookingDraft` that are tied to a specific pickup-and-delivery
 * route. When the customer starts a new route mid-conversation ("salwa to
 * massayel" after finishing an unrelated order), these must be wiped so the
 * new quote + address-collection flow starts clean.
 *
 * The identity fields (sender/recipient name + phone) are deliberately NOT in
 * this list — those travel with the customer across orders. Preserving them
 * is the whole point of the carry-over architecture: if they were already
 * filled (either by the customer this turn, by a fast-path, or by
 * `carry_over_from_last_order`), the new route must not nuke them.
 */
export const ROUTE_SCOPED_DRAFT_FIELDS: ReadonlyArray<keyof BookingDraft> = [
  "pickupBlock",
  "pickupStreet",
  "pickupHouse",
  "pickupAvenue",
  "pickupExtra",
  "pickupLocation",
  "deliveryBlock",
  "deliveryStreet",
  "deliveryHouse",
  "deliveryAvenue",
  "deliveryExtra",
  "deliveryLocation",
  "pendingLocation",
];

/**
 * Return a new draft with route-scoped fields cleared and identity fields
 * (sender/recipient name + phone) preserved from `previous`. Used by the
 * orchestrator when it detects a brand-new route mid-conversation and needs
 * to start a fresh quote without losing the customer's identity details —
 * especially the ones they just asked to carry over from a previous order.
 *
 * This is the fix for the transcript bug where `reset active booking flow
 * after new route message` wiped `same names and number as last order` the
 * instant the customer said "salwa to massayel".
 */
export function createRouteResetDraft(previous: BookingDraft | null | undefined): BookingDraft {
  const empty = createEmptyBookingDraft();
  if (!previous) return empty;
  return {
    ...empty,
    senderName: previous.senderName ?? null,
    senderPhone: previous.senderPhone ?? null,
    recipientName: previous.recipientName ?? null,
    recipientPhone: previous.recipientPhone ?? null,
  };
}

export type SlotConflict = {
  slot: SlotName;
  filledValue: string;
  incomingValue: string;
};

export type ApplyPatchResult = {
  draft: BookingDraft;
  applied: Array<keyof BookingFieldPatch>;
  rejected: BookingFieldValidationError[];
  senderPhoneDecision?: PhoneDecision;
  /** When a `dialogState` was passed in, the updated state reflecting every
   *  successfully-applied field in the patch. When no `dialogState` was
   *  passed, this is null (legacy callers unchanged). */
  dialogState?: DialogState | null;
  /** Slots that would have been overwritten with a different value — they
   *  were NOT applied (the legacy draft keeps the previously-filled value)
   *  and the caller is expected to ask the customer which to keep. Always
   *  an empty array when `dialogState` wasn't passed. */
  conflicts?: SlotConflict[];
};

/**
 * Apply a structured patch onto an existing draft. Each field is validated
 * individually; invalid fields are dropped with a reason and the rest still
 * apply. This is what `apply_booking_field` calls.
 *
 * `whatsappNumber` is needed when the customer chose `phone_decision: use_whatsapp`
 * so the sender phone gets filled in with the correct full number.
 */
export function applyBookingFieldPatch(params: {
  draft: BookingDraft;
  patch: BookingFieldPatch;
  whatsappNumber?: string | null;
  /** Optional DST state. When provided, every successfully-validated field
   *  write is funneled through `updateSlot` for conflict detection. When
   *  omitted, the function behaves exactly like before (legacy callers). */
  dialogState?: DialogState | null;
  /** Defaults to `"llm_apply"`. Callers that know they're applying a
   *  customer-fast-path patch or a tool override should pass the matching
   *  source so the slot record's `lastSource` is accurate. */
  dstSource?: SlotSource;
  /** When true and a DST `requestedSlot` is active, an incoming value for a
   *  different slot name is redirected to the requested slot. Only the guard
   *  (which has evidence that the incoming value is a valid answer to the
   *  requested slot) should pass this. */
  routeToRequested?: boolean;
  /** Explicit edit-intent flag. Set by the apply boundary when the incoming
   *  proposal's `source_quote` contains an edit signal (English/Arabic
   *  edit verbs, negations like "not X", `label N to M` patterns) AND the
   *  conversation stage is one where edits are expected (summary_shown,
   *  awaiting_confirmation, collecting_booking_details). When true, every
   *  `updateSlot` call in this patch passes `forceOverwrite: true`, so a
   *  different-value write on a filled/conflict slot REPLACES the incumbent
   *  silently instead of raising a conflict. Logged as `[edit-override]`
   *  so we can audit firing rates. See
   *  `apply-boundary.ts` → `sourceQuoteLooksLikeEdit`. */
  editIntent?: boolean;
}): ApplyPatchResult {
  const next: BookingDraft = { ...params.draft };
  const applied: Array<keyof BookingFieldPatch> = [];
  const rejected: BookingFieldValidationError[] = [];
  let senderPhoneDecision: PhoneDecision | undefined;

  // Collect every successful (field, value) write so we can walk them through
  // DST at the end. We can't just snapshot `next` because DST needs the patch
  // *field key* (to map to a slot name), which isn't recoverable from the
  // draft shape alone. Entries are added only when validation succeeded.
  const dstWrites: Array<{ patchField: string; role: "pickup" | "delivery" | null; value: string | null }> = [];

  const p = params.patch || {};

  if (p.sender_name != null) {
    const r = cleanName(p.sender_name);
    if (r.value) {
      next.senderName = r.value;
      applied.push("sender_name");
      dstWrites.push({ patchField: "sender_name", role: null, value: r.value });
    } else if (r.reason) {
      rejected.push({ field: "sender_name", reason: r.reason, received: String(p.sender_name) });
    }
  }

  if (p.phone_decision === "use_whatsapp") {
    senderPhoneDecision = "use_whatsapp";
    const wa = params.whatsappNumber ? cleanPhone(params.whatsappNumber) : { value: null, reason: null };
    if (wa.value) {
      next.senderPhone = wa.value;
      applied.push("phone_decision");
      dstWrites.push({ patchField: "sender_phone", role: null, value: wa.value });
    } else {
      // No WA number available — leave senderPhone as-is, record decision only.
      applied.push("phone_decision");
    }
  } else if (p.phone_decision === "different") {
    senderPhoneDecision = "different";
    applied.push("phone_decision");
  }

  if (p.sender_phone != null) {
    const r = cleanPhone(p.sender_phone);
    if (r.value) {
      next.senderPhone = r.value;
      applied.push("sender_phone");
      dstWrites.push({ patchField: "sender_phone", role: null, value: r.value });
    } else if (r.reason) {
      rejected.push({ field: "sender_phone", reason: r.reason, received: String(p.sender_phone) });
    }
  }

  if (p.recipient_name != null) {
    const r = cleanName(p.recipient_name);
    if (r.value) {
      next.recipientName = r.value;
      applied.push("recipient_name");
      dstWrites.push({ patchField: "recipient_name", role: null, value: r.value });
    } else if (r.reason) {
      rejected.push({ field: "recipient_name", reason: r.reason, received: String(p.recipient_name) });
    }
  }

  if (p.recipient_phone != null) {
    const r = cleanPhone(p.recipient_phone);
    if (r.value) {
      next.recipientPhone = r.value;
      applied.push("recipient_phone");
      dstWrites.push({ patchField: "recipient_phone", role: null, value: r.value });
    } else if (r.reason) {
      rejected.push({ field: "recipient_phone", reason: r.reason, received: String(p.recipient_phone) });
    }
  }

  const role = p.address_role === "pickup" || p.address_role === "delivery" ? p.address_role : null;

  if (p.address_block != null) {
    const r = cleanAddressPart(p.address_block);
    if (r.value) {
      if (role === "pickup") {
        next.pickupBlock = r.value;
        applied.push("address_block");
        dstWrites.push({ patchField: "address_block", role: "pickup", value: r.value });
      } else if (role === "delivery") {
        next.deliveryBlock = r.value;
        applied.push("address_block");
        dstWrites.push({ patchField: "address_block", role: "delivery", value: r.value });
      }
      // If role is null we leave it alone — the LLM should ask
    } else if (r.reason) {
      rejected.push({ field: "address_block", reason: r.reason, received: String(p.address_block) });
    }
  }

  if (p.address_street != null) {
    const r = cleanAddressPart(p.address_street);
    if (r.value) {
      if (role === "pickup") {
        next.pickupStreet = r.value;
        applied.push("address_street");
        dstWrites.push({ patchField: "address_street", role: "pickup", value: r.value });
      } else if (role === "delivery") {
        next.deliveryStreet = r.value;
        applied.push("address_street");
        dstWrites.push({ patchField: "address_street", role: "delivery", value: r.value });
      }
    } else if (r.reason) {
      rejected.push({ field: "address_street", reason: r.reason, received: String(p.address_street) });
    }
  }

  // Interior-detail salvage: if the model routed something like "door 312",
  // "apt 5, floor 2", "شقة ٨" into `address_house`, merge it into
  // `address_extra` instead of discarding the information. `address_house`
  // is reserved for the street-level building number that a driver reads off
  // the façade — apartment / floor / door / gate go into the free-form extras
  // bag. This kills the "door 312" class of bug deterministically, regardless
  // of prompt drift.
  let rerouteHouseToExtra: string | null = null;
  if (p.address_house != null && looksLikeInteriorDetail(p.address_house)) {
    rerouteHouseToExtra = String(p.address_house).trim();
    rejected.push({
      field: "address_house",
      reason: "address_house_is_interior_detail",
      received: String(p.address_house),
    });
  } else if (p.address_house != null && looksLikeSuspiciousHouseValue(p.address_house)) {
    // Catches sentence-shaped or overlong values that slipped past the
    // interior-keyword detector (e.g. "Villa 4 near the mosque next to the
    // gas station", "ground", "the big white building on the corner").
    // Preserve the information in `address_extra` and force the LLM to ask
    // the customer for the actual building number.
    rerouteHouseToExtra = String(p.address_house).trim();
    rejected.push({
      field: "address_house",
      reason: "address_house_suspicious_value",
      received: String(p.address_house),
    });
  } else if (p.address_house != null) {
    const r = cleanAddressPart(p.address_house);
    if (r.value) {
      if (role === "pickup") {
        next.pickupHouse = r.value;
        applied.push("address_house");
        dstWrites.push({ patchField: "address_house", role: "pickup", value: r.value });
      } else if (role === "delivery") {
        next.deliveryHouse = r.value;
        applied.push("address_house");
        dstWrites.push({ patchField: "address_house", role: "delivery", value: r.value });
      }
    } else if (r.reason) {
      rejected.push({ field: "address_house", reason: r.reason, received: String(p.address_house) });
    }
  }

  if (p.address_avenue != null) {
    const r = cleanAddressPart(p.address_avenue);
    if (r.value) {
      if (role === "pickup") {
        next.pickupAvenue = r.value;
        applied.push("address_avenue");
        dstWrites.push({ patchField: "address_avenue", role: "pickup", value: r.value });
      } else if (role === "delivery") {
        next.deliveryAvenue = r.value;
        applied.push("address_avenue");
        dstWrites.push({ patchField: "address_avenue", role: "delivery", value: r.value });
      }
    } else if (r.reason) {
      rejected.push({ field: "address_avenue", reason: r.reason, received: String(p.address_avenue) });
    }
  }

  // Merge any interior-detail value that the model mis-routed into
  // `address_house` (e.g. "door 312") with `address_extra`. The customer said
  // it, so the driver gets it — just in the correct bucket.
  const mergedExtra =
    rerouteHouseToExtra && p.address_extra
      ? `${String(p.address_extra).trim()}, ${rerouteHouseToExtra}`
      : rerouteHouseToExtra ?? p.address_extra;

  if (mergedExtra != null) {
    const r = cleanAddressExtra(mergedExtra);
    if (r.value) {
      if (role === "pickup") {
        next.pickupExtra = r.value;
        applied.push("address_extra");
        dstWrites.push({ patchField: "address_extra", role: "pickup", value: r.value });
      } else if (role === "delivery") {
        next.deliveryExtra = r.value;
        applied.push("address_extra");
        dstWrites.push({ patchField: "address_extra", role: "delivery", value: r.value });
      }
    } else if (r.reason) {
      rejected.push({
        field: "address_extra",
        reason: r.reason,
        received: String(mergedExtra),
      });
    }
  }

  // DST projection: if the caller handed us a dialogState, run every
  // successful write through `updateSlot`. Conflicts surface as rejections
  // (so the existing hallucination-guard/rejections plumbing sees them) AND
  // as a separate `conflicts` array so callers can render a disambiguation
  // prompt. The draft is updated only when the slot actually accepts the
  // write — conflicts revert the legacy draft field so readers keep seeing
  // the last-known-good value.
  const conflicts: SlotConflict[] = [];
  let nextDialogState: DialogState | null = params.dialogState ?? null;
  // Respect the env kill-switch: if DST is disabled at runtime, ignore the
  // passed-in state entirely and fall through to the legacy-only path. The
  // returned `dialogState` is set to null so callers don't try to persist a
  // half-updated copy.
  if (nextDialogState && !isDialogStateEnabled()) {
    nextDialogState = null;
  }
  if (nextDialogState) {
    const source: SlotSource = params.dstSource ?? "llm_apply";

    // Tuple-atomic source-precedence override.
    //
    // Product rule (2026-04-19): a fresh customer-turn identity tuple
    // (BOTH `*_name` AND `*_phone` in the same patch) silently supersedes
    // a carried-over identity for this order. Single-field corrections
    // still flow through the normal conflict path — that's a real
    // "you said X, now you're saying Y" moment.
    //
    // This sits at the patch level because tuple-atomicity is only
    // visible here: `updateSlot` sees one slot at a time and can't know
    // whether the other half of the identity is being updated in the
    // same turn. We decide once per patch, then pass
    // `overrideIfSourceWas: "carryover"` into the two relevant
    // `updateSlot` calls.
    //
    // Only customer-authored writes can trigger the override
    // (`customer_fast_path` or `llm_apply`). The `llm_apply` source is
    // included because the LLM is the one that usually extracts and
    // applies the customer's new tuple; the fast-path is a faster
    // alternate route but expresses the same intent. `carryover` is
    // explicitly excluded so a second carry-over op can't overwrite an
    // earlier carry-over (which would be a nonsense).
    const isCustomerAuthoredWrite =
      source === "customer_fast_path" || source === "llm_apply";
    const senderTuplePresent =
      dstWrites.some((w) => w.patchField === "sender_name") &&
      dstWrites.some((w) => w.patchField === "sender_phone");
    const recipientTuplePresent =
      dstWrites.some((w) => w.patchField === "recipient_name") &&
      dstWrites.some((w) => w.patchField === "recipient_phone");
    const senderOverride = isCustomerAuthoredWrite && senderTuplePresent;
    const recipientOverride = isCustomerAuthoredWrite && recipientTuplePresent;

    for (const w of dstWrites) {
      const slotName = slotNameForBookingField(w.patchField, w.role);
      if (!slotName) continue;
      // Per-write decision whether this specific slot carries the tuple
      // override. Only the two identity-tuple fields whose other half is
      // also in the patch are eligible.
      const eligibleForOverride =
        (senderOverride &&
          (slotName === "sender_name" || slotName === "sender_phone")) ||
        (recipientOverride &&
          (slotName === "recipient_name" || slotName === "recipient_phone"));
      const res = updateSlot(nextDialogState, slotName, w.value, source, {
        routeToRequested: params.routeToRequested === true,
        overrideIfSourceWas: eligibleForOverride ? "carryover" : undefined,
        forceOverwrite: params.editIntent === true,
      });
      nextDialogState = res.state;
      if (res.decision.action === "conflict") {
        conflicts.push({
          slot: slotName,
          filledValue: res.decision.filledValue,
          incomingValue: res.decision.incomingValue,
        });
        // Revert the legacy draft field for this slot so the draft mirrors
        // the DST state: the previously-filled value stays canonical until
        // the customer disambiguates. We can't simply re-read from
        // `params.draft` per-slot since the applied-list might have been
        // affected earlier in the same patch; use the DST mirror as the
        // single source of truth.
        // (applied.push was already called for this field; keep it as-is
        // since the patch was validated — but surface the rejection.)
        rejected.push({
          field: patchFieldToRejectionField(w.patchField),
          reason: "slot_conflict_with_filled_value",
          received: String(w.value),
        });
      } else if (res.decision.action === "overridden_by_source_precedence") {
        // Structured log so we can see the override firing at the right
        // rate in production. Grep key: `[carryover-override]`.
        try {
          console.warn(
            `[carryover-override] slot=${slotName} previousSource=${res.decision.previousSource ?? "null"} newSource=${res.decision.newSource} previousValue=${JSON.stringify(res.decision.previousValue ?? "")} incomingValue=${JSON.stringify(w.value ?? "")}`,
          );
        } catch {}
      } else if (res.decision.action === "overridden_by_edit_intent") {
        // Structured log for the explicit-edit override. Grep key:
        // `[edit-override]`. Firing rate should correlate with
        // post-summary corrections like "block 3 to block 4", "change
        // the street to 10", "actually recipient phone is …", etc.
        try {
          console.warn(
            `[edit-override] slot=${slotName} previousSource=${res.decision.previousSource ?? "null"} newSource=${res.decision.newSource} previousValue=${JSON.stringify(res.decision.previousValue ?? "")} incomingValue=${JSON.stringify(w.value ?? "")}`,
          );
        } catch {}
      } else if (res.decision.action === "upgraded_by_superset") {
        // Structured log for the address-extra strict-superset upgrade.
        // Grep key: `[slot-upgrade]`. This fires when two grounded
        // writes land in the same turn and the second one strictly
        // adds info — the canonical case is fast-path seeing "floor 11,
        // door 14" and the LLM seeing the full "apartment 11, floor 11,
        // door 14" from the same customer utterance. Should be
        // frequent enough to be benign but rare in absolute numbers.
        try {
          console.warn(
            `[slot-upgrade] slot=${slotName} previousSource=${res.decision.previousSource ?? "null"} newSource=${res.decision.newSource} previousValue=${JSON.stringify(res.decision.previousValue ?? "")} incomingValue=${JSON.stringify(w.value ?? "")}`,
          );
        } catch {}
      }
    }
    // Mirror DST onto the legacy draft so the `draft` shape returned to
    // callers reflects conflict-reverts (filled value kept, candidate held
    // in DST). Only mirror the fields that DST actually owns; locations and
    // senderPhoneRejected on the incoming draft are preserved.
    const mirrored = mirrorDialogStateToDraft(nextDialogState, next);
    Object.assign(next, mirrored);
  }

  return {
    draft: next,
    applied,
    rejected,
    senderPhoneDecision,
    dialogState: nextDialogState,
    conflicts,
  };
}

function patchFieldToRejectionField(
  patchField: string,
): BookingFieldValidationError["field"] {
  switch (patchField) {
    case "sender_name":
      return "sender_name";
    case "sender_phone":
      return "sender_phone";
    case "recipient_name":
      return "recipient_name";
    case "recipient_phone":
      return "recipient_phone";
    case "address_block":
      return "address_block";
    case "address_street":
      return "address_street";
    case "address_house":
      return "address_house";
    case "address_avenue":
      return "address_avenue";
    case "address_extra":
      return "address_extra";
    default:
      return "sender_name"; // unreachable given the slotName filter above
  }
}

function pickupAddressComplete(draft: BookingDraft): boolean {
  if (draft.pickupLocation) return true;
  return Boolean(draft.pickupBlock && draft.pickupStreet && draft.pickupHouse);
}

function deliveryAddressComplete(draft: BookingDraft): boolean {
  if (draft.deliveryLocation) return true;
  return Boolean(draft.deliveryBlock && draft.deliveryStreet && draft.deliveryHouse);
}

export function isDraftComplete(draft: BookingDraft): boolean {
  return Boolean(
    draft.senderName &&
      draft.senderPhone &&
      draft.recipientName &&
      draft.recipientPhone &&
      pickupAddressComplete(draft) &&
      deliveryAddressComplete(draft),
  );
}

export function missingDraftFields(draft: BookingDraft): string[] {
  const out: string[] = [];
  if (!draft.senderName) out.push("sender_name");
  if (!draft.senderPhone) out.push("sender_phone");
  if (!draft.recipientName) out.push("recipient_name");
  if (!draft.recipientPhone) out.push("recipient_phone");
  if (!pickupAddressComplete(draft)) out.push("pickup_address");
  if (!deliveryAddressComplete(draft)) out.push("delivery_address");
  return out;
}

/**
 * Full validation of the draft at the order-placement boundary. Returns a
 * structured result. An `ok: true` result means the draft is safe to send
 * to the backend, subject to route + price guards applied separately.
 */
export type DraftOrderValidation =
  | { ok: true }
  | { ok: false; missing: string[]; invalid: DraftValidationProblem[] };

export function validateDraftForOrder(draft: BookingDraft): DraftOrderValidation {
  const missing: string[] = [];
  const invalid: DraftValidationProblem[] = [];

  const nameChecks: Array<{ field: string; value: string | null }> = [
    { field: "sender_name", value: draft.senderName },
    { field: "recipient_name", value: draft.recipientName },
  ];
  for (const c of nameChecks) {
    if (!c.value) {
      missing.push(c.field);
      continue;
    }
    const r = cleanName(c.value);
    if (!r.value) invalid.push({ field: c.field, reason: r.reason || "invalid", received: c.value });
  }

  const phoneChecks: Array<{ field: string; value: string | null }> = [
    { field: "sender_phone", value: draft.senderPhone },
    { field: "recipient_phone", value: draft.recipientPhone },
  ];
  for (const c of phoneChecks) {
    if (!c.value) {
      missing.push(c.field);
      continue;
    }
    const r = cleanPhone(c.value);
    if (!r.value) invalid.push({ field: c.field, reason: r.reason || "invalid", received: c.value });
  }

  if (!pickupAddressComplete(draft)) {
    missing.push("pickup_address");
  } else if (!draft.pickupLocation) {
    const parts: Array<{ field: string; value: string | null }> = [
      { field: "pickup_block", value: draft.pickupBlock },
      { field: "pickup_street", value: draft.pickupStreet },
      { field: "pickup_house", value: draft.pickupHouse },
    ];
    for (const c of parts) {
      const r = cleanAddressPart(c.value);
      if (!r.value) invalid.push({ field: c.field, reason: r.reason || "invalid", received: c.value || "" });
    }
  }

  if (!deliveryAddressComplete(draft)) {
    missing.push("delivery_address");
  } else if (!draft.deliveryLocation) {
    const parts: Array<{ field: string; value: string | null }> = [
      { field: "delivery_block", value: draft.deliveryBlock },
      { field: "delivery_street", value: draft.deliveryStreet },
      { field: "delivery_house", value: draft.deliveryHouse },
    ];
    for (const c of parts) {
      const r = cleanAddressPart(c.value);
      if (!r.value) invalid.push({ field: c.field, reason: r.reason || "invalid", received: c.value || "" });
    }
  }

  if (missing.length === 0 && invalid.length === 0) {
    return { ok: true };
  }
  return { ok: false, missing, invalid };
}
