// Z1-P0: cold-start symmetric-area rejection for get_price.
//
// Scope of this module:
//   Pure decision logic for whether a `get_price(pickup_area, dropoff_area)`
//   call on cold-start (no mid-flow rebind target available) should be
//   rejected before any pricing resolution or controller writes happen.
//
//   The actual `get_price` tool in `../tools/pricing.ts` continues to own
//   the execute body; it calls `evaluateSymmetricAreaGuard` once per turn
//   AFTER the existing mid-flow symmetric-rebind override has had a
//   chance to fix symmetric params. If the params are STILL symmetric at
//   that point AND the mid-flow guard had nothing pending to rebind to,
//   this module returns a `reject` decision. The tool then throws a
//   structured `Error` with the message so the LLM re-reads and
//   self-corrects on the next turn.
//
// Why a separate module:
//   The host function is already 800+ lines. A unit-testable pure
//   function removes the need to mock `loadPricing`, intent gates,
//   pricing resolver, responder-state ops, etc., to verify the symmetry
//   decision.
//
// Safety:
//   - Only acts when both `pickup_area` and `dropoff_area` are non-empty
//     strings that compare equal (case-insensitive, trimmed).
//   - Never acts when the mid-flow symmetric-rebind guard in
//     `../tools/pricing.ts` would have had a target to rebind to
//     (`requestedSlot.name === "dropoff_area"` with `pendingPickup`, or
//     `requestedSlot.name === "pickup_area"` with `pendingDropoff`) —
//     in that case the real guard upstream of this check already fired
//     or will fire and the params are no longer symmetric.
//   - Never acts on a legitimate asymmetric route like
//     `pickup=Khaldiya, dropoff=Salmiya`.

export interface SymmetricGuardInputs {
  pickupArea: string | null | undefined;
  dropoffArea: string | null | undefined;
  requestedSlotName: "pickup_area" | "dropoff_area" | string | null | undefined;
  pendingPickupAreaNameEn: string | null | undefined;
  pendingDropoffAreaNameEn: string | null | undefined;
  envValue: string | null | undefined;
}

export type SymmetricGuardDecision =
  | {
      action: "pass";
      reason:
        | "not_symmetric"
        | "mid_flow_rebind_target_present";
    }
  | {
      action: "reject";
      reason: "symmetric_cold_start";
      normalizedArea: string;
      message: string;
    };

function coerceNonEmptyTrimmed(value: string | null | undefined): string {
  if (typeof value !== "string") return "";
  return value.trim();
}

/**
 * Decide whether a `get_price` invocation should be rejected because the
 * two legs resolve to the same area on a cold-start shape. See module
 * header for the full rationale.
 */
export function evaluateSymmetricAreaGuard(
  inputs: SymmetricGuardInputs,
): SymmetricGuardDecision {
  void inputs.envValue;

  const pickup = coerceNonEmptyTrimmed(inputs.pickupArea);
  const dropoff = coerceNonEmptyTrimmed(inputs.dropoffArea);
  if (!pickup || !dropoff) {
    return { action: "pass", reason: "not_symmetric" };
  }
  if (pickup.toLowerCase() !== dropoff.toLowerCase()) {
    return { action: "pass", reason: "not_symmetric" };
  }

  const pendingPickup = coerceNonEmptyTrimmed(inputs.pendingPickupAreaNameEn);
  const pendingDropoff = coerceNonEmptyTrimmed(inputs.pendingDropoffAreaNameEn);
  const requestedSlot =
    typeof inputs.requestedSlotName === "string"
      ? inputs.requestedSlotName
      : "";

  // Mid-flow rebind target detection. Mirrors the conditions the
  // existing `[area-symmetric-rebind]` guard in `pricing.ts` uses to
  // decide when to override the non-requested leg. If a target exists,
  // we do NOT reject here — the live call chain runs the mid-flow
  // guard BEFORE this validator, so by the time we run, either the
  // params are no longer symmetric (rebind succeeded) or something is
  // very wrong (rebind misfired); in either case rejection is not the
  // right tool.
  const midFlowTargetExists =
    (requestedSlot === "dropoff_area" && pendingPickup.length > 0) ||
    (requestedSlot === "pickup_area" && pendingDropoff.length > 0);
  if (midFlowTargetExists) {
    return { action: "pass", reason: "mid_flow_rebind_target_present" };
  }

  const message =
    "get_price was called with pickup_area and dropoff_area set to the same area (" +
    pickup +
    '). That is not a valid quote route. Treat this as a single-area coverage question or a missing-leg route request. Do NOT write quote state and do NOT call get_price again until you have TWO DIFFERENT areas.';

  return {
    action: "reject",
    reason: "symmetric_cold_start",
    normalizedArea: pickup,
    message,
  };
}

/**
 * Rendered metric line for log ingestion. Kept as a helper so the tool
 * call site and tests emit the same shape.
 */
export function formatRejectMetric(
  decision: Extract<SymmetricGuardDecision, { action: "reject" }>,
  context: {
    requestedSlotName: string | null | undefined;
    pendingPickupPresent: boolean;
    pendingDropoffPresent: boolean;
    stage: string | null | undefined;
  },
): string {
  return (
    `[metric] get_price.validator_reject reason=${decision.reason}` +
    ` pickup="${decision.normalizedArea}" dropoff="${decision.normalizedArea}"` +
    ` requestedSlot=${context.requestedSlotName || "null"}` +
    ` pendingPickup=${context.pendingPickupPresent ? "set" : "null"}` +
    ` pendingDropoff=${context.pendingDropoffPresent ? "set" : "null"}` +
    ` stage=${context.stage || "unknown"}`
  );
}
