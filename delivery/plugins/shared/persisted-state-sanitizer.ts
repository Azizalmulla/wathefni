/**
 * Read-time sanitizer for persisted booking state.
 *
 * Purpose
 * -------
 * Before this module existed, the system assumed anything already on
 * disk or in the conversation-controller cache must be valid — "we
 * wrote it, so it must be good." That assumption held only as long as
 * every write path was correct. Each time we found a new way for bad
 * data to reach a write (fast-path extractor mis-attributing a name,
 * LLM tool call with an unguarded argument, carry-over from a
 * historical profile written before today's fixes), the poisoned
 * value would sit on disk and resurface on the NEXT turn, even after
 * the write-side bug was fixed, because the read path trusted it.
 *
 * That's the 2026-04-19 15:28 incident: the customer's profile stored
 * `sender.name = "Is this the cheapest option"` from a session placed
 * before today's deploy. The write-side coherence fix stops this from
 * happening to new orders, but the poisoned row stays on disk until
 * the customer manually corrects it — and the summary builder keeps
 * echoing it every turn.
 *
 * The principled fix is to treat every persisted read as untrusted
 * input, applying the SAME validators we use on write. If a field
 * fails, we drop it and log a structured line so we can see how much
 * historical corruption exists. The customer experience becomes: on
 * the first turn after the fix, the corrupted field vanishes and the
 * LLM re-asks for it; from that turn on, the bad data is gone.
 *
 * This module centralizes that logic so every load path uses the same
 * rules. Today there are two load paths:
 *
 *   - `CustomerProfile.load` (file-backed, per-WhatsApp)
 *   - `ConversationController.get` (Redis-backed, per-conversation)
 *
 * Both must call the sanitizer. Future load paths must call the
 * sanitizer. The validators it delegates to are the SAME ones the
 * write path uses (`validateName`, `cleanPhone`, `cleanAddressPart`),
 * so write-time and read-time logic can never drift.
 */

import {
  cleanAddressPart,
  cleanPhone,
  type BookingDraft,
} from "./booking-draft.js";
import { validateName } from "./responder-state-ops.js";

/** A single field that was dropped during sanitization.
 *
 *  Emitted as telemetry so we can see (a) how much historical
 *  corruption exists in the wild, and (b) whether a new write-path
 *  bug is smuggling bad data past the validators. */
export type SanitizationDrop = {
  /** e.g. "sender_name", "pickupBlock", "last_successful_order.recipient.phone". */
  field: string;
  /** Machine-readable reason from the validator ("name_looks_like_question",
   *  "phone_contains_non_digits", ...). */
  reason: string;
  /** The offending value, truncated for log-safety. */
  received: string;
  /** Which load path produced the drop, for log aggregation. */
  source: "customer_profile" | "controller_entry";
};

export type SanitizationResult<T> = {
  value: T;
  drops: SanitizationDrop[];
};

const LOG_SAFE_MAX = 80;

function forLog(value: unknown): string {
  const s = typeof value === "string" ? value : String(value ?? "");
  if (s.length <= LOG_SAFE_MAX) return s;
  return `${s.slice(0, LOG_SAFE_MAX - 1)}…`;
}

// ---------------------------------------------------------------------------
// Field-level sanitizers. Each returns the cleaned value (or null) plus an
// optional drop record. Values that were ALREADY null stay null with no
// drop — the drop is only emitted when a non-null value fails validation.
// ---------------------------------------------------------------------------

function sanitizeNameField(
  value: string | null | undefined,
): { cleaned: string | null; drop: { reason: string; received: string } | null } {
  if (value == null) return { cleaned: null, drop: null };
  const trimmed = typeof value === "string" ? value.trim() : String(value).trim();
  if (!trimmed) return { cleaned: null, drop: null };
  const reason = validateName(trimmed);
  if (reason) {
    return { cleaned: null, drop: { reason, received: trimmed } };
  }
  // `validateName` doesn't coerce, but we want the same trimmed form the
  // write path produces.
  return { cleaned: trimmed.replace(/\s+/g, " "), drop: null };
}

function sanitizePhoneField(
  value: string | null | undefined,
): { cleaned: string | null; drop: { reason: string; received: string } | null } {
  if (value == null) return { cleaned: null, drop: null };
  const raw = typeof value === "string" ? value : String(value);
  if (!raw.trim()) return { cleaned: null, drop: null };
  const res = cleanPhone(raw);
  if (!res.value) {
    return { cleaned: null, drop: { reason: res.reason ?? "phone_invalid", received: raw } };
  }
  return { cleaned: res.value, drop: null };
}

function sanitizeAddressPartField(
  value: string | null | undefined,
): { cleaned: string | null; drop: { reason: string; received: string } | null } {
  if (value == null) return { cleaned: null, drop: null };
  const raw = typeof value === "string" ? value : String(value);
  if (!raw.trim()) return { cleaned: null, drop: null };
  const res = cleanAddressPart(raw);
  if (!res.value) {
    return { cleaned: null, drop: { reason: res.reason ?? "address_part_invalid", received: raw } };
  }
  return { cleaned: res.value, drop: null };
}

// ---------------------------------------------------------------------------
// BookingDraft sanitization — used by the controller-entry load path.
// ---------------------------------------------------------------------------

/** Fields in `BookingDraft` that are person-name slots. */
const NAME_FIELDS = ["senderName", "recipientName"] as const;
/** Fields in `BookingDraft` that are phone slots. */
const PHONE_FIELDS = ["senderPhone", "recipientPhone"] as const;
/** Fields in `BookingDraft` that are short address tokens
 *  (block / street / house / avenue). `extra` is a free-form bag with
 *  its own looser validator, so we treat it like a name-free string. */
const ADDRESS_PART_FIELDS = [
  "pickupBlock",
  "pickupStreet",
  "pickupHouse",
  "pickupAvenue",
  "deliveryBlock",
  "deliveryStreet",
  "deliveryHouse",
  "deliveryAvenue",
] as const;

/**
 * Sanitize a `BookingDraft` by running every typed field through the
 * same validators the write path uses. Fields that fail validation are
 * set to `null` and recorded in `drops`. All other fields are left
 * untouched (we explicitly only re-coerce the fields we validate —
 * auxiliary fields like `senderPhoneRejected`, locations, and `extra`
 * bags are preserved as-is so we never silently lose state the caller
 * relies on).
 *
 * The returned draft is always a NEW object; the input is not mutated.
 */
export function sanitizeBookingDraft(
  draft: BookingDraft | null | undefined,
  source: SanitizationDrop["source"] = "controller_entry",
): SanitizationResult<BookingDraft | null> {
  if (!draft) return { value: draft ?? null, drops: [] };
  const drops: SanitizationDrop[] = [];
  const next: BookingDraft = { ...draft };

  for (const field of NAME_FIELDS) {
    const { cleaned, drop } = sanitizeNameField(draft[field]);
    next[field] = cleaned;
    if (drop) {
      drops.push({ field, reason: drop.reason, received: forLog(drop.received), source });
    }
  }

  for (const field of PHONE_FIELDS) {
    const { cleaned, drop } = sanitizePhoneField(draft[field]);
    next[field] = cleaned;
    if (drop) {
      drops.push({ field, reason: drop.reason, received: forLog(drop.received), source });
    }
  }

  for (const field of ADDRESS_PART_FIELDS) {
    const { cleaned, drop } = sanitizeAddressPartField(draft[field]);
    next[field] = cleaned;
    if (drop) {
      drops.push({ field, reason: drop.reason, received: forLog(drop.received), source });
    }
  }

  return { value: next, drops };
}

// ---------------------------------------------------------------------------
// CustomerProfile.last_successful_order sanitization — used by the
// customer-profile load path. We keep this tolerant of the loose
// `SavedCustomerOrder` shape: sender/recipient/pickup/delivery may be
// absent, null, or partially filled. We don't invent fields; we only
// drop values that are present-but-invalid.
//
// NB: the existing `sanitizeCustomerProfile` in
// plugins/octopus-channel/lib/customer-profile.ts handles one specific
// coarse failure mode (both names look like phones AND both phones
// match the customer AND addresses are empty). We keep it — this
// module is additive, running field-by-field validation in every case
// the coarse check misses.
// ---------------------------------------------------------------------------

type SavedOrderLike = {
  sender?: { name?: string | null; phone?: string | null } | null;
  recipient?: { name?: string | null; phone?: string | null } | null;
  pickup?: { house?: string | null; avenue?: string | null } | null;
  delivery?: { house?: string | null; avenue?: string | null } | null;
  [key: string]: unknown;
};

/**
 * Sanitize the saved `last_successful_order` on a `CustomerProfile`.
 * The function:
 *   - Clones the input (never mutates).
 *   - Replaces invalid sender/recipient names and phones with `null`.
 *   - Replaces invalid pickup/delivery `house` and `avenue` with `null`.
 *   - Leaves all other fields (payer, payment_method, notes, etc.)
 *     untouched so we don't silently drop state.
 *
 * Returns `null` for `value` when the input is null. The `drops` array
 * is always populated with whatever fields were cleared, even if the
 * sanitized object is still mostly intact.
 */
export function sanitizeSavedOrder<T extends SavedOrderLike>(
  order: T | null | undefined,
): SanitizationResult<T | null> {
  if (!order) return { value: order ?? null, drops: [] };
  const drops: SanitizationDrop[] = [];
  const source: SanitizationDrop["source"] = "customer_profile";

  const next: T = { ...order };

  // Sender
  if (order.sender) {
    const nextSender: { name: string | null; phone: string | null; [k: string]: unknown } = {
      ...order.sender,
      name: order.sender.name ?? null,
      phone: order.sender.phone ?? null,
    };
    const n = sanitizeNameField(order.sender.name);
    nextSender.name = n.cleaned;
    if (n.drop) {
      drops.push({
        field: "last_successful_order.sender.name",
        reason: n.drop.reason,
        received: forLog(n.drop.received),
        source,
      });
    }
    const p = sanitizePhoneField(order.sender.phone);
    nextSender.phone = p.cleaned;
    if (p.drop) {
      drops.push({
        field: "last_successful_order.sender.phone",
        reason: p.drop.reason,
        received: forLog(p.drop.received),
        source,
      });
    }
    (next as SavedOrderLike).sender = nextSender;
  }

  // Recipient
  if (order.recipient) {
    const nextRecipient: { name: string | null; phone: string | null; [k: string]: unknown } = {
      ...order.recipient,
      name: order.recipient.name ?? null,
      phone: order.recipient.phone ?? null,
    };
    const n = sanitizeNameField(order.recipient.name);
    nextRecipient.name = n.cleaned;
    if (n.drop) {
      drops.push({
        field: "last_successful_order.recipient.name",
        reason: n.drop.reason,
        received: forLog(n.drop.received),
        source,
      });
    }
    const p = sanitizePhoneField(order.recipient.phone);
    nextRecipient.phone = p.cleaned;
    if (p.drop) {
      drops.push({
        field: "last_successful_order.recipient.phone",
        reason: p.drop.reason,
        received: forLog(p.drop.received),
        source,
      });
    }
    (next as SavedOrderLike).recipient = nextRecipient;
  }

  // Pickup / Delivery addresses. The saved shape only stores `house` and
  // `avenue` as short-token fields; the rest (area, notes) are either
  // resolved by the area resolver on replay or are free-form strings we
  // don't validate here.
  if (order.pickup) {
    const nextPickup: { house: string | null; avenue: string | null; [k: string]: unknown } = {
      ...order.pickup,
      house: order.pickup.house ?? null,
      avenue: order.pickup.avenue ?? null,
    };
    const h = sanitizeAddressPartField(order.pickup.house);
    nextPickup.house = h.cleaned;
    if (h.drop) {
      drops.push({
        field: "last_successful_order.pickup.house",
        reason: h.drop.reason,
        received: forLog(h.drop.received),
        source,
      });
    }
    const a = sanitizeAddressPartField(order.pickup.avenue);
    nextPickup.avenue = a.cleaned;
    if (a.drop) {
      drops.push({
        field: "last_successful_order.pickup.avenue",
        reason: a.drop.reason,
        received: forLog(a.drop.received),
        source,
      });
    }
    (next as SavedOrderLike).pickup = nextPickup;
  }

  if (order.delivery) {
    const nextDelivery: { house: string | null; avenue: string | null; [k: string]: unknown } = {
      ...order.delivery,
      house: order.delivery.house ?? null,
      avenue: order.delivery.avenue ?? null,
    };
    const h = sanitizeAddressPartField(order.delivery.house);
    nextDelivery.house = h.cleaned;
    if (h.drop) {
      drops.push({
        field: "last_successful_order.delivery.house",
        reason: h.drop.reason,
        received: forLog(h.drop.received),
        source,
      });
    }
    const a = sanitizeAddressPartField(order.delivery.avenue);
    nextDelivery.avenue = a.cleaned;
    if (a.drop) {
      drops.push({
        field: "last_successful_order.delivery.avenue",
        reason: a.drop.reason,
        received: forLog(a.drop.received),
        source,
      });
    }
    (next as SavedOrderLike).delivery = nextDelivery;
  }

  return { value: next, drops };
}

/**
 * Format a drop list for a single structured log line. The caller
 * passes this to its usual logger (`api.logger.info`) so every load
 * path shares the same log shape.
 */
export function formatSanitizerDrops(drops: SanitizationDrop[]): string {
  if (!drops.length) return "";
  return drops
    .map((d) => `${d.field}=${d.reason} received=${JSON.stringify(d.received)}`)
    .join(" ");
}
