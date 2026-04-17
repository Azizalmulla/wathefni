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

export type ResponderStateOp =
  | ResponderBookingFieldOp
  | ResponderStartBookingOp
  | ResponderConfirmSummaryOp
  | ResponderCancelBookingOp
  | ResponderHandoffOp;

const buffer = new Map<string, ResponderStateOp[]>();
const TURN_OP_LIMIT = 32;

export function pushResponderStateOp(conversationId: string, op: ResponderStateOp): void {
  if (!conversationId) return;
  const existing = buffer.get(conversationId) || [];
  if (existing.length >= TURN_OP_LIMIT) return;
  existing.push(op);
  buffer.set(conversationId, existing);
}

export function drainResponderStateOps(conversationId: string): ResponderStateOp[] {
  if (!conversationId) return [];
  const existing = buffer.get(conversationId) || [];
  if (existing.length > 0) {
    buffer.delete(conversationId);
  }
  return existing;
}

export function clearResponderStateOps(conversationId: string): void {
  if (!conversationId) return;
  buffer.delete(conversationId);
}

export function peekResponderStateOps(conversationId: string): ResponderStateOp[] {
  if (!conversationId) return [];
  return [...(buffer.get(conversationId) || [])];
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
const ADDRESS_PART_MAX_LEN = 30;
const ADDRESS_EXTRA_MAX_LEN = 200;

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

function validateName(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed.length < NAME_MIN_LEN) return "name_too_short";
  if (trimmed.length > NAME_MAX_LEN) return "name_too_long";
  if (/^\d+$/.test(trimmed)) return "name_is_digits";
  if (looksLikeArtifact(trimmed)) return "name_is_artifact";
  // Letters (any script), spaces, hyphens, apostrophes, dots. No digits.
  if (!/^[\p{L}][\p{L}\s'\-.]*$/u.test(trimmed)) return "name_has_invalid_chars";
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
