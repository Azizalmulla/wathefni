/**
 * Ambiguous name+phone pair guard.
 *
 * Problem this module solves (observed 2026-04-19 19:14):
 *
 *   Bot turn:      "Please send the sender name and mobile number, and the
 *                   recipient name and number."
 *   Customer turn: "Aziz almulla 99338566"
 *   LLM op:        apply_booking_field(recipient_name="Aziz almulla",
 *                                      recipient_phone="99338566")
 *   Bot turn:      "Recipient noted..."
 *
 * The LLM silently attributed a single unlabeled name+phone pair to the
 * recipient even though the sender was still unresolved. That is never
 * safe: the customer's intent is ambiguous and the server should force
 * a clarification, not gamble.
 *
 * The rule (state-derived, not phrasing-derived):
 *
 *   IF the op proposes writing `recipient_name` or `recipient_phone`
 *   AND the `source_quote` looks like a SINGLE UNLABELED NAME+PHONE PAIR
 *   AND `sender_name` is still unresolved in the draft
 *   AND the op does NOT also write a sender field for this turn
 *   THEN the recipient write is rejected (dropped from the patch),
 *        a rejection is recorded so the LLM knows its write failed,
 *        and the caller is told to set `requestedSlot = "sender_name"`
 *        so the next turn's context asks the right party first.
 *
 * The rule deliberately does NOT care what the bot asked in the last
 * turn. Sequencing might drift (combined ask vs sequential ask) but the
 * safety condition is the same: ambiguity + unresolved sender +
 * recipient write = clarify.
 *
 * This module is pure. No I/O. Never throws. Returns a structured
 * decision; the caller mutates state and logs.
 */

export type AmbiguousPairGuardInput = {
  /** Proposed op values. Null/empty fields are ignored. */
  op: {
    sender_name?: string | null;
    sender_phone?: string | null;
    recipient_name?: string | null;
    recipient_phone?: string | null;
    phone_decision?: "use_whatsapp" | "different" | null;
    source_quote?: string | null;
  };
  /** Current draft. Only the sender / recipient text fields are read. */
  draft: {
    senderName: string | null;
    senderPhone: string | null;
    recipientName: string | null;
    recipientPhone: string | null;
  };
};

export type AmbiguousPairGuardDecision =
  | {
      action: "allow";
      /** Why the guard chose not to fire. Useful for log triage. */
      reason:
        | "no_recipient_write"
        | "sender_already_resolved"
        | "op_also_writes_sender"
        | "source_quote_not_single_pair"
        | "no_source_quote";
    }
  | {
      action: "reject_recipient_write";
      reason: "ambiguous_unlabeled_pair_with_sender_unresolved";
      /** Fields to drop from the applied patch. Everything else on the op
       *  may still be applied (address, phone_decision, etc.). */
      dropFields: Array<"recipient_name" | "recipient_phone">;
      /** Slot the caller should set as requested so the next turn's
       *  context steers the LLM to ask for the sender first. */
      requestedSlot: "sender_name";
      /** Suggested FieldRejection entries to push onto this turn's
       *  `rejectionsThisTurn` array so the post-LLM hallucination guard
       *  can see the write was rejected. */
      rejections: Array<{ field: string; reason: string; received: string }>;
    };

/**
 * Is the source_quote plausibly a single "name + phone" pair with no
 * explicit sender/recipient labels?
 *
 * Tight detection:
 *   - Contains EXACTLY ONE long digit run (≥ 7 digits, ≤ 15 digits).
 *   - Has at least one letter token (Latin or Arabic) alongside it.
 *   - Does NOT mention any of the attribution words `sender`,
 *     `recipient`, `المرسل`, `المستلم`, `من`, `الى`/`إلى`, `لـ`, `to`,
 *     `from`, `for`. Messages that DO name the role ("sender is Aziz
 *     99338566") are not ambiguous — the LLM's attribution is grounded.
 *
 * Returns false on empty / multi-pair / label-carrying / pure-phone /
 * pure-name inputs. False is the safe answer (the guard won't fire).
 */
export function looksLikeSingleUnlabeledPair(source: string | null): boolean {
  if (!source) return false;
  const text = source.trim();
  if (!text) return false;

  // Explicit role attribution kills the ambiguity claim outright. We
  // check for whole-word / token matches to avoid a false hit on names
  // that happen to contain substrings like "to" / "for".
  const LABELS = [
    /\bsender\b/i,
    /\brecipient\b/i,
    /\bto\b/i,
    /\bfor\b/i,
    /\bfrom\b/i,
    /\breceiver\b/i,
    /\brecv\b/i,
    /المرسل/u,
    /المستلم/u,
    /(?:\s|^)(?:من|الى|إلى)(?:\s|$)/u,
    /(?:\s|^)لـ(?:\s|$)/u,
  ];
  for (const rx of LABELS) {
    if (rx.test(text)) return false;
  }

  // Collect digit runs of length ≥ 7 (phone-candidate bar matches the
  // rest of the codebase — see `extractPhoneCandidates` in outbound-
  // verify.ts and the fast-path recipient extractor).
  const digitRuns: string[] = [];
  const re = /[\d\s+\-()]{7,}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const clean = m[0].replace(/\D+/g, "");
    if (clean.length >= 7 && clean.length <= 15) digitRuns.push(clean);
  }
  if (digitRuns.length !== 1) return false;

  // Must also contain a letter token. "99338566" alone is a pure phone,
  // not a pair.
  if (!/[A-Za-z\u0600-\u06FF]/.test(text)) return false;

  return true;
}

export function evaluateAmbiguousPair(
  input: AmbiguousPairGuardInput,
): AmbiguousPairGuardDecision {
  const { op, draft } = input;

  const writesRecipientName =
    typeof op.recipient_name === "string" && op.recipient_name.trim().length > 0;
  const writesRecipientPhone =
    typeof op.recipient_phone === "string" && op.recipient_phone.trim().length > 0;
  if (!writesRecipientName && !writesRecipientPhone) {
    return { action: "allow", reason: "no_recipient_write" };
  }

  const writesSenderName =
    typeof op.sender_name === "string" && op.sender_name.trim().length > 0;
  const writesSenderPhone =
    typeof op.sender_phone === "string" && op.sender_phone.trim().length > 0;
  const writesSenderPhoneDecision = op.phone_decision != null;
  if (writesSenderName || writesSenderPhone || writesSenderPhoneDecision) {
    // The op itself already disambiguates: if the LLM writes both
    // sender AND recipient values from the same customer turn, that's
    // a labeled-pair interpretation (e.g. "sender: Aziz 99338566,
    // recipient: Ali 62844738"). The guard must not second-guess.
    return { action: "allow", reason: "op_also_writes_sender" };
  }

  // Sender already resolved in the draft? No ambiguity — the customer
  // has already provided the sender on a previous turn, so an unlabeled
  // pair this turn can reasonably be the recipient.
  const senderNameResolved =
    typeof draft.senderName === "string" && draft.senderName.trim().length > 0;
  const senderPhoneResolved =
    typeof draft.senderPhone === "string" && draft.senderPhone.trim().length > 0;
  if (senderNameResolved && senderPhoneResolved) {
    return { action: "allow", reason: "sender_already_resolved" };
  }

  if (!op.source_quote) {
    // Without a source_quote we can't verify the "unlabeled single
    // pair" condition. Default to allowing — the guard is a narrow
    // safety net; requiring source_quote is how we keep false
    // positives near zero.
    return { action: "allow", reason: "no_source_quote" };
  }

  if (!looksLikeSingleUnlabeledPair(op.source_quote)) {
    return { action: "allow", reason: "source_quote_not_single_pair" };
  }

  const dropFields: Array<"recipient_name" | "recipient_phone"> = [];
  const rejections: Array<{ field: string; reason: string; received: string }> = [];
  if (writesRecipientName) {
    dropFields.push("recipient_name");
    rejections.push({
      field: "recipient_name",
      reason: "ambiguous_pair_sender_unresolved",
      received: op.recipient_name || "",
    });
  }
  if (writesRecipientPhone) {
    dropFields.push("recipient_phone");
    rejections.push({
      field: "recipient_phone",
      reason: "ambiguous_pair_sender_unresolved",
      received: op.recipient_phone || "",
    });
  }

  return {
    action: "reject_recipient_write",
    reason: "ambiguous_unlabeled_pair_with_sender_unresolved",
    dropFields,
    requestedSlot: "sender_name",
    rejections,
  };
}
