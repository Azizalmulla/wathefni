/**
 * Cross-side phone guard — same-turn protection against LLM mirroring a
 * single digit group into both sender_phone AND recipient_phone.
 *
 * Live-incident shape (conv 19399, 2026-04-22):
 *
 *   Bot:      ASK_SENDER_PHONE
 *   Customer: "99338566"
 *   Fast-path pre-apply → sender_phone = 99338566 (reasons=pure_phone)
 *   LLM's apply_booking_field → {
 *     sender_phone:   "99338566",      // idempotent, fine
 *     recipient_phone: "99338566",     // WRONG — mirrored into counterpart
 *   }
 *
 * The boundary accepted the recipient_phone because the slot was still
 * empty. Customer sees their own number pre-filled on the recipient side
 * and has to correct it, or worse — misses it and the order ships with
 * garbage.
 *
 * Rule: only a phone write that actually committed earlier in the current
 * turn may block a counterpart-side phone. Attempted, rejected, or conflicted
 * writes must never reach `fastPathPreApplied`.
 *
 * This guard is symmetric (sender↔recipient) so a future
 * ASK_RECIPIENT_NAME_AND_PHONE / sender-mirror variant is covered too.
 *
 * Pure helper so the drain loop can stay a thin orchestrator and the
 * rule itself is unit-testable. See `smoke-test-slot-fill-fixes.mjs`
 * for the pinned cases.
 */

import type { BookingFieldPatch } from "./booking-draft";

export type CrossSidePhoneGuardInput = {
  /** Names of fields the fast-path pre-apply successfully committed THIS
   *  turn. The caller must pass committed writes only; this helper only
   *  reacts to `sender_phone` / `recipient_phone` entries. */
  fastPathPreApplied: ReadonlyArray<keyof BookingFieldPatch | string>;
  /** LLM's proposed sender_phone on this turn's apply_booking_field op
   *  (or null/undefined if not set). */
  senderPhone: string | null | undefined;
  /** LLM's proposed recipient_phone on this turn's apply_booking_field
   *  op (or null/undefined if not set). */
  recipientPhone: string | null | undefined;
};

export type CrossSidePhoneDrop = {
  /** Which side of the LLM's patch was dropped. */
  field: "sender_phone" | "recipient_phone";
  /** Which side the fast-path had already written — the trigger for
   *  the drop. */
  triggeredBy: "sender_phone" | "recipient_phone";
  /** The value that was masked out. */
  value: string;
  /** Stable machine-readable reason code, suitable for boundary
   *  rejection logs and telemetry. */
  reason: "cross_side_phone_write_same_turn";
};

export type CrossSidePhoneGuardResult = {
  /** Post-guard sender phone (null means "drop this write"). */
  senderPhone: string | null;
  /** Post-guard recipient phone (null means "drop this write"). */
  recipientPhone: string | null;
  /** Zero-or-more drop events in deterministic order. A single turn
   *  can only produce at most one drop (a side is masked only when
   *  its counterpart was pre-applied), but we return an array so
   *  callers can iterate uniformly. */
  drops: CrossSidePhoneDrop[];
};

export function applyCrossSidePhoneGuard(
  input: CrossSidePhoneGuardInput,
): CrossSidePhoneGuardResult {
  const pre = new Set(input.fastPathPreApplied);
  let senderPhone: string | null = input.senderPhone ?? null;
  let recipientPhone: string | null = input.recipientPhone ?? null;
  const drops: CrossSidePhoneDrop[] = [];

  if (pre.has("sender_phone") && recipientPhone != null) {
    drops.push({
      field: "recipient_phone",
      triggeredBy: "sender_phone",
      value: recipientPhone,
      reason: "cross_side_phone_write_same_turn",
    });
    recipientPhone = null;
  }
  if (pre.has("recipient_phone") && senderPhone != null) {
    drops.push({
      field: "sender_phone",
      triggeredBy: "recipient_phone",
      value: senderPhone,
      reason: "cross_side_phone_write_same_turn",
    });
    senderPhone = null;
  }
  return { senderPhone, recipientPhone, drops };
}
