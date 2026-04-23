/**
 * Dialog State Tracking (DST) — typed slot register with `requested_slot`
 * and per-slot conflict detection.
 *
 * This module is the single source of truth for "what slot values do we know?"
 * and "what did we just ask the customer for?". Every write to a booking-level
 * slot should go through `updateSlot`; every disambiguation/clarification
 * prompt should call `setRequestedSlot`. The evidence guard and prompt
 * builders consult the state on read.
 *
 * The layer is intentionally a pure function module — no I/O, no globals. The
 * persisted conversation-controller entry owns the DialogState value and
 * passes it through every write path. A parallel mirror (`mirrorDialogStateToDraft`)
 * keeps the legacy `PersistedBookingDraft` shape working unchanged so existing
 * readers don't break during the migration.
 *
 * Why this exists: see the "DST Slots Layer" plan. The short version is that
 * the LLM occasionally writes a field to the wrong slot (e.g. answers a
 * dropoff disambiguation by writing pickup), or silently overwrites a filled
 * slot with a stale value. Catching either requires (a) knowing what slot was
 * just asked for, and (b) knowing which slots are already filled — neither of
 * which lived anywhere in the old state model.
 */

import type { PersistedBookingDraft } from "./conversation-policy.js";

export type SlotStatus = "unfilled" | "filled" | "conflict";

export type SlotName =
  | "sender_name"
  | "sender_phone"
  | "recipient_name"
  | "recipient_phone"
  | "pickup_area"
  | "dropoff_area"
  | "pickup_block"
  | "pickup_street"
  | "pickup_house"
  | "pickup_avenue"
  | "pickup_extra"
  | "delivery_block"
  | "delivery_street"
  | "delivery_house"
  | "delivery_avenue"
  | "delivery_extra";

export const ALL_SLOT_NAMES: readonly SlotName[] = [
  "sender_name",
  "sender_phone",
  "recipient_name",
  "recipient_phone",
  "pickup_area",
  "dropoff_area",
  "pickup_block",
  "pickup_street",
  "pickup_house",
  "pickup_avenue",
  "pickup_extra",
  "delivery_block",
  "delivery_street",
  "delivery_house",
  "delivery_avenue",
  "delivery_extra",
];

/**
 * Slots that describe WHO is sending / receiving (identity). These survive a
 * route-reset: the customer is the same person, so their name/phone and the
 * recipient's name/phone carry over even when the pickup/delivery addresses
 * change. Mirrors `createRouteResetDraft` in booking-draft.ts.
 */
export const IDENTITY_SLOT_NAMES: readonly SlotName[] = [
  "sender_name",
  "sender_phone",
  "recipient_name",
  "recipient_phone",
];

/**
 * Slots that describe WHERE the delivery is going. These are wiped on a
 * route-reset since a new pickup-and-delivery route invalidates any prior
 * address sub-fields.
 */
export const ROUTE_SCOPED_SLOT_NAMES: readonly SlotName[] = [
  "pickup_area",
  "dropoff_area",
  "pickup_block",
  "pickup_street",
  "pickup_house",
  "pickup_avenue",
  "pickup_extra",
  "delivery_block",
  "delivery_street",
  "delivery_house",
  "delivery_avenue",
  "delivery_extra",
];

export type SlotSource =
  | "customer_fast_path"
  | "llm_apply"
  | "legacy_mirror"
  // Slot was populated by `carry_over_from_last_order` — i.e. from the
  // customer's previously-saved profile rather than from the current turn.
  // Used by the summary render to annotate carried-over lines and by the
  // route-reset partition to preserve identity fields across a new route.
  | "carryover";

export type SlotRecord = {
  value: string | null;
  status: SlotStatus;
  lastSetTs: number | null;
  lastSource: SlotSource | null;
  /** Only populated when status === "conflict": the incoming value that
   *  disagreed with the current filled value. The customer must disambiguate
   *  before we know which to keep. */
  conflictCandidate?: string | null;
};

export type RequestedSlot = {
  name: SlotName;
  /** Optional menu of allowed values for disambiguation prompts. When set,
   *  the evidence guard will route an incoming value to this slot if the
   *  value (or an alias resolving to it) is in `options`. */
  options?: string[] | null;
  askedTs: number;
} | null;

export type DialogState = {
  slots: Partial<Record<SlotName, SlotRecord>>;
  requestedSlot: RequestedSlot;
  /** Schema version. Bumped when the shape changes in a non-backwards
   *  compatible way so migrations can be applied on load. */
  version: 1;
};

export const DIALOG_STATE_VERSION: 1 = 1;

// ---------------------------------------------------------------------------
// Construction / accessors
// ---------------------------------------------------------------------------

export function createEmptyDialogState(): DialogState {
  return {
    slots: {},
    requestedSlot: null,
    version: DIALOG_STATE_VERSION,
  };
}

/**
 * Return a dialog state where every route-scoped slot is cleared but identity
 * slots (sender/recipient name + phone) are preserved from `previous`. Used
 * by the orchestrator's route-reset path so a "new route" message doesn't
 * silently discard identity fields the customer just asked to carry over
 * from a previous order.
 */
export function createRouteResetDialogState(
  previous: DialogState | null | undefined,
): DialogState {
  if (!previous) return createEmptyDialogState();
  const slots: Partial<Record<SlotName, SlotRecord>> = {};
  for (const name of IDENTITY_SLOT_NAMES) {
    const existing = previous.slots[name];
    if (existing) slots[name] = existing;
  }
  return {
    slots,
    requestedSlot: null,
    version: DIALOG_STATE_VERSION,
  };
}

export function getSlot(state: DialogState, name: SlotName): SlotRecord {
  return (
    state.slots[name] ?? {
      value: null,
      status: "unfilled",
      lastSetTs: null,
      lastSource: null,
    }
  );
}

// ---------------------------------------------------------------------------
// Requested-slot register
// ---------------------------------------------------------------------------

export function setRequestedSlot(
  state: DialogState,
  req: RequestedSlot,
): DialogState {
  return { ...state, requestedSlot: req };
}

export function clearRequestedSlot(state: DialogState): DialogState {
  if (!state.requestedSlot) return state;
  return { ...state, requestedSlot: null };
}

// ---------------------------------------------------------------------------
// Conflict helpers
// ---------------------------------------------------------------------------

/** Trim-and-fold equality used when comparing filled vs. incoming values. We
 *  don't do full canonicalization here — the caller has already run
 *  field-specific cleaners (cleanPhone, cleanName, area-resolver, etc.). This
 *  just absorbs trivial whitespace/casing differences so "Salwa " and "salwa"
 *  aren't seen as conflicts. */
function valuesEqual(a: string | null, b: string | null): boolean {
  if (a == null || b == null) return a === b;
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

/**
 * Address-extra slots (pickup_extra / delivery_extra) frequently see the
 * SAME canonical value written twice in one turn by two different
 * components: the fast-path extractor writes a compacted form
 * ("apartment11, floor 5, door1") and the LLM's apply_booking_field op
 * writes the properly spaced form ("apartment 11, floor 5, door 1"). A
 * naive string compare treats them as different → conflict → "Please
 * confirm the pickup extra" salad next turn.
 *
 * This helper returns a whitespace- and token-normalized canonical form
 * that collapses:
 *
 *   1. Letter<->digit glue: "apartment11" ≡ "apartment 11",
 *      "door1" ≡ "door 1". Works for Latin AND Arabic letter ranges.
 *   2. Comma-separated token order: "floor 5, apartment 11" ≡
 *      "apartment 11, floor 5" (same set of extras).
 *   3. Internal whitespace + case: "Floor  5" ≡ "floor 5".
 *
 * The output is a sorted `", "-joined string of normalized tokens`, so
 * set equality reduces to string equality on canonical forms. This lets
 * us both (a) detect "unchanged" and (b) check strict-superset for the
 * upgrade path below.
 *
 * Kept scoped to the two extra slots — other slots (names, phones,
 * address parts like block/street/house) already have stable
 * shape-validated values by the time they reach `updateSlot`.
 */
function canonicalAddressExtra(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/\s+/g, " ")
    .replace(/([a-z\u0600-\u06FF])(\d)/g, "$1 $2")
    .replace(/(\d)([a-z\u0600-\u06FF])/g, "$1 $2")
    .split(/\s*,\s*/)
    .map((t) => t.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .sort()
    .join(", ");
}

function addressExtraTokens(value: string): string[] {
  return value
    .toLowerCase()
    .trim()
    .replace(/\s+/g, " ")
    .replace(/([a-z\u0600-\u06FF])(\d)/g, "$1 $2")
    .replace(/(\d)([a-z\u0600-\u06FF])/g, "$1 $2")
    .split(/\s*,\s*/)
    .map((t) => t.replace(/\s+/g, " ").trim())
    .filter(Boolean);
}

function isAddressExtraSlot(name: SlotName): boolean {
  return name === "pickup_extra" || name === "delivery_extra";
}

/**
 * Per-slot value equivalence. For address-extra slots, uses the canonical
 * form above so fast-path vs LLM whitespace drift is treated as
 * "unchanged". For every other slot, falls back to the generic
 * trim+lowercase comparison.
 */
function areSlotValuesEquivalent(
  name: SlotName,
  a: string | null,
  b: string | null,
): boolean {
  if (a == null || b == null) return a === b;
  if (isAddressExtraSlot(name)) {
    return canonicalAddressExtra(a) === canonicalAddressExtra(b);
  }
  return valuesEqual(a, b);
}

/**
 * Per-slot strict-superset check. Only meaningful for address-extra
 * slots today: if the incoming value contains EVERY normalized token
 * from the current value AND at least one additional token, it's an
 * information upgrade (e.g. fast-path got "floor 11, door 14", LLM got
 * the full "apartment 11, floor 11, door 14"). Returns false for
 * anything else — including same-sized but different-token sets, which
 * are genuine conflicts the customer has to disambiguate.
 */
function isSlotValueStrictUpgrade(
  name: SlotName,
  current: string | null,
  incoming: string | null,
): boolean {
  if (current == null || incoming == null) return false;
  if (!isAddressExtraSlot(name)) return false;
  const currentTokens = addressExtraTokens(current);
  const incomingTokens = new Set(addressExtraTokens(incoming));
  if (currentTokens.length === 0) return false;
  if (incomingTokens.size <= currentTokens.length) return false;
  for (const t of currentTokens) {
    if (!incomingTokens.has(t)) return false;
  }
  return true;
}

// ---------------------------------------------------------------------------
// updateSlot — the chokepoint
// ---------------------------------------------------------------------------

export type UpdateSlotDecision =
  | { action: "accepted"; previousValue: string | null }
  | { action: "unchanged" }
  | { action: "conflict"; filledValue: string; incomingValue: string }
  | {
      action: "routed_to_requested";
      intendedSlot: SlotName;
      requestedSlot: SlotName;
      previousValue: string | null;
    }
  | { action: "cleared"; previousValue: string | null }
  | { action: "rejected"; reason: string }
  /** The incumbent filled value was overwritten silently because its
   *  `lastSource` matched `options.overrideIfSourceWas`. Distinct from
   *  `"accepted"` so callers can log the provenance override separately and
   *  so the LLM context surface never shows a conflict where there isn't
   *  one. */
  | {
      action: "overridden_by_source_precedence";
      previousValue: string | null;
      previousSource: SlotSource | null;
      newSource: SlotSource;
    }
  /** Explicit edit-intent override. The caller has already verified (via
   *  the apply boundary's edit-intent detector — regex on the proposal's
   *  `source_quote` + stage gate) that the customer is deliberately
   *  changing this field, not re-stating it in a way that accidentally
   *  differs. The incumbent value (and any `conflictCandidate`) is
   *  replaced silently. Distinct action code so logs and tests can
   *  distinguish edit overrides from source-precedence overrides or
   *  first-fill acceptances. */
  | {
      action: "overridden_by_edit_intent";
      previousValue: string | null;
      previousSource: SlotSource | null;
      newSource: SlotSource;
    }
  /** Strict-superset upgrade. Only fires on address-extra slots today:
   *  the incoming value contains every normalized token of the current
   *  value plus at least one additional token. Treated as an information
   *  upgrade — the incumbent is replaced silently, no conflict is raised,
   *  no customer-facing confirm is needed. Distinct action code so logs
   *  and tests can tell upgrades apart from edits, carryover overrides,
   *  and first fills. */
  | {
      action: "upgraded_by_superset";
      previousValue: string | null;
      previousSource: SlotSource | null;
      newSource: SlotSource;
    };

export type UpdateSlotResult = {
  state: DialogState;
  decision: UpdateSlotDecision;
};

export type UpdateSlotOptions = {
  /** When set, the update is interpreted as a response to an outstanding
   *  `requestedSlot`. If the caller-intended `name` differs from
   *  `state.requestedSlot.name`, and the route hook opts in, the write is
   *  redirected to the requested slot. This is how we catch the
   *  "LLM put the dropoff answer in the pickup slot" class of bug.
   *
   *  The pricing guard has the context (resolver + options) to decide whether
   *  the incoming value is a plausible answer to the requested slot. So
   *  rather than hardcoding route logic here, we let callers pass
   *  `routeToRequested: true` when they've already verified evidence-match. */
  routeToRequested?: boolean;
  /** Source-precedence override. When the incumbent slot's `lastSource`
   *  matches this value AND the incoming value differs, the incoming value
   *  overwrites silently (no conflict raised, no `conflictCandidate`). Used
   *  by the apply path to let a fresh customer-turn identity tuple supersede
   *  a carried-over identity without triggering a clarification loop.
   *
   *  The rule is stated per-call (not baked into the source ordering) because
   *  tuple-atomicity lives at the patch level: `applyBookingFieldPatch` only
   *  passes this option when it's seeing BOTH halves of an identity bucket
   *  in the same patch. Single-field corrections still flow through the
   *  normal conflict path, which is the right behavior. */
  overrideIfSourceWas?: SlotSource;
  /**
   * Explicit edit-intent override. When true, a different-value write on
   * a filled or conflict slot REPLACES the incumbent value silently:
   *   - the new value becomes the canonical `filled` value,
   *   - any stale `conflictCandidate` is discarded,
   *   - decision is returned as `overridden_by_edit_intent` (not
   *     `conflict`), so the apply boundary does not surface a rejection
   *     and the LLM context builder does not emit `slot_conflicts` for
   *     this slot next turn.
   *
   * The apply boundary sets this when the LLM's (or fast-path's)
   * `source_quote` contains an explicit edit signal AND the conversation
   * stage is one where edits are expected (see
   * `apply-boundary.ts` → `sourceQuoteLooksLikeEdit`). It is NOT a way
   * to bypass shape, coherence, or ambiguous-pair checks; those run
   * before this flag is ever consulted.
   *
   * When set, `overrideIfSourceWas` is ignored (edit intent is strictly
   * stronger than source-precedence override — an explicit edit wins
   * even if the incumbent came from a customer fast-path write, not
   * just a carried-over one).
   */
  forceOverwrite?: boolean;
  now?: number;
};

/**
 * Write a slot. The single chokepoint. Every path that mutates slot state
 * should end up here.
 *
 * Behaviors:
 *   - `value === null` with an existing filled slot → clears the slot (status
 *     transitions to "unfilled"). Used by explicit resets and cancellations.
 *   - Value unchanged (same trim-fold as current) → decision "unchanged", no
 *     writes.
 *   - Filling an unfilled slot → decision "accepted", status → "filled".
 *   - Same value on a filled slot → decision "unchanged".
 *   - Different value on a filled slot → decision "conflict", stored as
 *     `conflictCandidate`. The actual value does NOT change. Caller is
 *     expected to ask the customer.
 *   - Conflict slot + same value as the filled → resolves the conflict,
 *     status → "filled", `conflictCandidate` cleared.
 *   - `routeToRequested: true` with a non-matching slot target and an active
 *     `requestedSlot` → the write is redirected to `state.requestedSlot.name`
 *     (the LLM's intended target is recorded in the decision for logging).
 *
 * Side-effect: any write that successfully fills (or resolves a conflict on)
 * the currently `requestedSlot` clears `requestedSlot`.
 */
export function updateSlot(
  state: DialogState,
  name: SlotName,
  value: string | null,
  source: SlotSource,
  options: UpdateSlotOptions = {},
): UpdateSlotResult {
  const now = options.now ?? Date.now();

  // Routing: LLM tried to write slot X, but we're waiting for slot Y and the
  // caller has already decided this value is a valid Y-answer.
  let targetName = name;
  let routed = false;
  if (
    options.routeToRequested &&
    state.requestedSlot &&
    state.requestedSlot.name !== name
  ) {
    targetName = state.requestedSlot.name;
    routed = true;
  }

  const current = getSlot(state, targetName);

  // Clearing
  if (value == null) {
    if (current.status === "unfilled" && current.value == null) {
      return { state, decision: { action: "unchanged" } };
    }
    const nextSlots = { ...state.slots };
    delete nextSlots[targetName];
    const nextState: DialogState = {
      ...state,
      slots: nextSlots,
      requestedSlot:
        state.requestedSlot?.name === targetName ? null : state.requestedSlot,
    };
    return {
      state: nextState,
      decision: { action: "cleared", previousValue: current.value },
    };
  }

  // Unchanged (same value already filled or conflict-pending). For
  // address-extra slots, equivalence is normalized — see
  // `canonicalAddressExtra`. This is what makes the fast-path vs LLM
  // whitespace-drift double-write stop raising a phantom conflict.
  if (current.status === "filled" && areSlotValuesEquivalent(targetName, current.value, value)) {
    // Still clear `requestedSlot` if we were waiting on this slot — the
    // customer's re-assertion counts as an answer.
    if (state.requestedSlot?.name === targetName) {
      return {
        state: { ...state, requestedSlot: null },
        decision: { action: "unchanged" },
      };
    }
    return { state, decision: { action: "unchanged" } };
  }

  // Filling an unfilled slot
  if (current.status === "unfilled") {
    const record: SlotRecord = {
      value,
      status: "filled",
      lastSetTs: now,
      lastSource: source,
    };
    const nextState: DialogState = {
      ...state,
      slots: { ...state.slots, [targetName]: record },
      requestedSlot:
        state.requestedSlot?.name === targetName ? null : state.requestedSlot,
    };
    if (routed) {
      return {
        state: nextState,
        decision: {
          action: "routed_to_requested",
          intendedSlot: name,
          requestedSlot: targetName,
          previousValue: current.value,
        },
      };
    }
    return {
      state: nextState,
      decision: { action: "accepted", previousValue: current.value },
    };
  }

  // Resolving a conflict by re-asserting the filled value
  if (
    current.status === "conflict" &&
    current.value != null &&
    areSlotValuesEquivalent(targetName, current.value, value)
  ) {
    const record: SlotRecord = {
      value: current.value,
      status: "filled",
      lastSetTs: now,
      lastSource: source,
    };
    const nextState: DialogState = {
      ...state,
      slots: { ...state.slots, [targetName]: record },
      requestedSlot:
        state.requestedSlot?.name === targetName ? null : state.requestedSlot,
    };
    return {
      state: nextState,
      decision: { action: "accepted", previousValue: current.value },
    };
  }

  // Resolving a conflict by picking the conflictCandidate
  if (
    current.status === "conflict" &&
    current.conflictCandidate != null &&
    areSlotValuesEquivalent(targetName, current.conflictCandidate, value)
  ) {
    const record: SlotRecord = {
      value: current.conflictCandidate,
      status: "filled",
      lastSetTs: now,
      lastSource: source,
    };
    const nextState: DialogState = {
      ...state,
      slots: { ...state.slots, [targetName]: record },
      requestedSlot:
        state.requestedSlot?.name === targetName ? null : state.requestedSlot,
    };
    return {
      state: nextState,
      decision: {
        action: "accepted",
        previousValue: current.value,
      },
    };
  }

  // Filled slot + different value. Four paths, in priority order:
  //
  //   (a) Edit-intent override: the caller has already confirmed (via
  //       regex on source_quote + stage gate in the apply boundary)
  //       that the customer is deliberately changing this slot.
  //       Replace silently; no conflict.
  //
  //   (b) Source-precedence override: if the caller declared the incumbent's
  //       `lastSource` as overridable (e.g. "carryover") and the incumbent
  //       actually has that source, overwrite silently. This is the fresh-
  //       identity-beats-carried-over rule. See `UpdateSlotOptions.
  //       overrideIfSourceWas` for the full rationale.
  //
  //   (c) Strict-superset upgrade: for address-extra slots, if the
  //       incoming value contains EVERY token of the current value plus
  //       at least one additional token, it's an information upgrade
  //       (fast-path saw "floor 11, door 14" → LLM sees the full
  //       "apartment 11, floor 11, door 14"). Replace silently — no
  //       conflict, no customer-facing ask, because both values are
  //       grounded in the same utterance. See `isSlotValueStrictUpgrade`.
  //
  //   (d) Normal conflict: hold the incumbent, stash the incoming as
  //       `conflictCandidate`, and let the caller ask the customer which
  //       to keep.
  if (current.status === "filled") {
    if (options.forceOverwrite) {
      const record: SlotRecord = {
        value,
        status: "filled",
        lastSetTs: now,
        lastSource: source,
      };
      const nextState: DialogState = {
        ...state,
        slots: { ...state.slots, [targetName]: record },
        requestedSlot:
          state.requestedSlot?.name === targetName ? null : state.requestedSlot,
      };
      return {
        state: nextState,
        decision: {
          action: "overridden_by_edit_intent",
          previousValue: current.value,
          previousSource: current.lastSource,
          newSource: source,
        },
      };
    }
    if (isSlotValueStrictUpgrade(targetName, current.value, value)) {
      const record: SlotRecord = {
        value,
        status: "filled",
        lastSetTs: now,
        lastSource: source,
      };
      const nextState: DialogState = {
        ...state,
        slots: { ...state.slots, [targetName]: record },
        requestedSlot:
          state.requestedSlot?.name === targetName ? null : state.requestedSlot,
      };
      return {
        state: nextState,
        decision: {
          action: "upgraded_by_superset",
          previousValue: current.value,
          previousSource: current.lastSource,
          newSource: source,
        },
      };
    }
    if (
      options.overrideIfSourceWas &&
      current.lastSource === options.overrideIfSourceWas
    ) {
      const record: SlotRecord = {
        value,
        status: "filled",
        lastSetTs: now,
        lastSource: source,
      };
      const nextState: DialogState = {
        ...state,
        slots: { ...state.slots, [targetName]: record },
        requestedSlot:
          state.requestedSlot?.name === targetName ? null : state.requestedSlot,
      };
      return {
        state: nextState,
        decision: {
          action: "overridden_by_source_precedence",
          previousValue: current.value,
          previousSource: current.lastSource,
          newSource: source,
        },
      };
    }
    const record: SlotRecord = {
      ...current,
      status: "conflict",
      conflictCandidate: value,
    };
    const nextState: DialogState = {
      ...state,
      slots: { ...state.slots, [targetName]: record },
    };
    return {
      state: nextState,
      decision: {
        action: "conflict",
        filledValue: current.value ?? "",
        incomingValue: value,
      },
    };
  }

  // Conflict slot + another new value. Same override rules as the
  // filled-slot branch:
  //
  //   (a) Edit-intent override: replace the incumbent, discard the stale
  //       conflictCandidate, resolve the conflict as filled. This is the
  //       intended shape for explicit post-summary edits — the boundary
  //       should never carry a conflict forward across an explicit edit.
  //
  //   (b) Source-precedence override: same behavior as (a) when the
  //       incumbent's lastSource matches (e.g. carried-over identity).
  //
  //   (c) Otherwise, update the candidate and keep the conflict open.
  if (current.status === "conflict") {
    if (options.forceOverwrite) {
      const record: SlotRecord = {
        value,
        status: "filled",
        lastSetTs: now,
        lastSource: source,
      };
      const nextState: DialogState = {
        ...state,
        slots: { ...state.slots, [targetName]: record },
        requestedSlot:
          state.requestedSlot?.name === targetName ? null : state.requestedSlot,
      };
      return {
        state: nextState,
        decision: {
          action: "overridden_by_edit_intent",
          previousValue: current.value,
          previousSource: current.lastSource,
          newSource: source,
        },
      };
    }
    if (isSlotValueStrictUpgrade(targetName, current.value, value)) {
      const record: SlotRecord = {
        value,
        status: "filled",
        lastSetTs: now,
        lastSource: source,
      };
      const nextState: DialogState = {
        ...state,
        slots: { ...state.slots, [targetName]: record },
        requestedSlot:
          state.requestedSlot?.name === targetName ? null : state.requestedSlot,
      };
      return {
        state: nextState,
        decision: {
          action: "upgraded_by_superset",
          previousValue: current.value,
          previousSource: current.lastSource,
          newSource: source,
        },
      };
    }
    if (
      options.overrideIfSourceWas &&
      current.lastSource === options.overrideIfSourceWas
    ) {
      const record: SlotRecord = {
        value,
        status: "filled",
        lastSetTs: now,
        lastSource: source,
      };
      const nextState: DialogState = {
        ...state,
        slots: { ...state.slots, [targetName]: record },
        requestedSlot:
          state.requestedSlot?.name === targetName ? null : state.requestedSlot,
      };
      return {
        state: nextState,
        decision: {
          action: "overridden_by_source_precedence",
          previousValue: current.value,
          previousSource: current.lastSource,
          newSource: source,
        },
      };
    }
    const record: SlotRecord = {
      ...current,
      conflictCandidate: value,
    };
    const nextState: DialogState = {
      ...state,
      slots: { ...state.slots, [targetName]: record },
    };
    return {
      state: nextState,
      decision: {
        action: "conflict",
        filledValue: current.value ?? "",
        incomingValue: value,
      },
    };
  }

  // Fallthrough — should be unreachable
  return { state, decision: { action: "rejected", reason: "unreachable" } };
}

// ---------------------------------------------------------------------------
// Legacy mirror — project DST slots into PersistedBookingDraft shape
// ---------------------------------------------------------------------------

/**
 * Project the DST slots into the legacy `PersistedBookingDraft` shape so that
 * existing readers (everything that calls `entry.bookingDraft.senderName` etc)
 * keep working unchanged. This is the backwards-compat bridge.
 *
 * Rules:
 *   - DST slots with status `"filled"` project their value.
 *   - Status `"unfilled"` projects null.
 *   - Status `"conflict"` projects the original filled value (NOT the
 *     candidate) — the conflict is not yet resolved, so downstream should
 *     still see the last-known-good value. The hallucination/evidence guard
 *     reads DST directly to see the conflict.
 *   - `pickup_area`/`dropoff_area` do NOT have slots on the draft — they live
 *     on the controller entry itself (`quotePickupAreaNameEn` etc.), so this
 *     mirror leaves them alone.
 *   - `pickupLocation`, `deliveryLocation`, `pendingLocation`,
 *     `senderPhoneRejected` are preserved from the incoming `draft` — they
 *     aren't DST slots (they're structured values, not single strings).
 */
export function mirrorDialogStateToDraft(
  state: DialogState,
  draft: PersistedBookingDraft,
): PersistedBookingDraft {
  const pickValue = (name: SlotName): string | null => {
    const slot = state.slots[name];
    if (!slot) return null;
    if (slot.status === "filled") return slot.value;
    if (slot.status === "conflict") return slot.value; // last-known-good
    return null;
  };

  // Helper: prefer DST value when the slot exists; otherwise preserve the
  // existing draft value (so fields that DST hasn't been taught about yet —
  // e.g. pickupLocation pins — don't get erased).
  const dstOrDraft = (
    slotName: SlotName,
    draftValue: string | null,
  ): string | null => {
    const slot = state.slots[slotName];
    if (!slot) return draftValue;
    return pickValue(slotName);
  };

  return {
    ...draft,
    senderName: dstOrDraft("sender_name", draft.senderName),
    senderPhone: dstOrDraft("sender_phone", draft.senderPhone),
    recipientName: dstOrDraft("recipient_name", draft.recipientName),
    recipientPhone: dstOrDraft("recipient_phone", draft.recipientPhone),
    pickupBlock: dstOrDraft("pickup_block", draft.pickupBlock),
    pickupStreet: dstOrDraft("pickup_street", draft.pickupStreet),
    pickupHouse: dstOrDraft("pickup_house", draft.pickupHouse),
    pickupAvenue: dstOrDraft("pickup_avenue", draft.pickupAvenue),
    pickupExtra: dstOrDraft("pickup_extra", draft.pickupExtra),
    deliveryBlock: dstOrDraft("delivery_block", draft.deliveryBlock),
    deliveryStreet: dstOrDraft("delivery_street", draft.deliveryStreet),
    deliveryHouse: dstOrDraft("delivery_house", draft.deliveryHouse),
    deliveryAvenue: dstOrDraft("delivery_avenue", draft.deliveryAvenue),
    deliveryExtra: dstOrDraft("delivery_extra", draft.deliveryExtra),
  };
}

/**
 * Seed a DialogState from an existing PersistedBookingDraft. Used on first
 * load of a controller entry that predates DST so existing filled values are
 * reflected in the slot register. Treats every populated draft field as
 * `filled` with source `legacy_mirror`.
 */
export function seedDialogStateFromDraft(
  draft: PersistedBookingDraft,
  now: number = Date.now(),
): DialogState {
  const state = createEmptyDialogState();
  const seed = (name: SlotName, value: string | null): void => {
    if (value == null || value === "") return;
    state.slots[name] = {
      value,
      status: "filled",
      lastSetTs: now,
      lastSource: "legacy_mirror",
    };
  };
  seed("sender_name", draft.senderName);
  seed("sender_phone", draft.senderPhone);
  seed("recipient_name", draft.recipientName);
  seed("recipient_phone", draft.recipientPhone);
  seed("pickup_block", draft.pickupBlock);
  seed("pickup_street", draft.pickupStreet);
  seed("pickup_house", draft.pickupHouse);
  seed("pickup_avenue", draft.pickupAvenue);
  seed("pickup_extra", draft.pickupExtra);
  seed("delivery_block", draft.deliveryBlock);
  seed("delivery_street", draft.deliveryStreet);
  seed("delivery_house", draft.deliveryHouse);
  seed("delivery_avenue", draft.deliveryAvenue);
  seed("delivery_extra", draft.deliveryExtra);
  return state;
}

// ---------------------------------------------------------------------------
// Translators between BookingFieldPatch naming and SlotName
// ---------------------------------------------------------------------------

/**
 * Map the first concrete missing-field marker produced by
 * `computeOneBrainMissingFields` to its DST SlotName. Used by the
 * orchestrator to set `requestedSlot` whenever the LLM is about to ask the
 * customer for a specific slot (phone re-send, missing address sub-field).
 *
 * Returns null when the marker is coarse-grained (e.g. "pickup.address"
 * without a sub-field), which means no one specific slot is being asked for.
 */
export function deriveRequestedSlotFromMissing(
  missing: string[],
): SlotName | null {
  // Prefer sub-field markers over their coarse parents so we set the
  // tightest possible requested_slot. E.g. if both "pickup.address" and
  // "pickup.block" are present, prefer pickup_block.
  const subFieldPrefs: Array<[string, SlotName]> = [
    ["sender.name", "sender_name"],
    ["sender.phone", "sender_phone"],
    ["recipient.name", "recipient_name"],
    ["recipient.phone", "recipient_phone"],
    ["pickup.area", "pickup_area"],
    ["delivery.area", "dropoff_area"],
    ["pickup.block", "pickup_block"],
    ["pickup.street", "pickup_street"],
    ["pickup.house", "pickup_house"],
    ["pickup.avenue", "pickup_avenue"],
    ["pickup.extra", "pickup_extra"],
    ["delivery.block", "delivery_block"],
    ["delivery.street", "delivery_street"],
    ["delivery.house", "delivery_house"],
    ["delivery.avenue", "delivery_avenue"],
    ["delivery.extra", "delivery_extra"],
  ];
  const set = new Set(missing);
  for (const [marker, slot] of subFieldPrefs) {
    if (set.has(marker)) return slot;
  }
  return null;
}

/**
 * Return the first DST slot currently in `status: "conflict"`, matching the
 * selection order used by `computeOneBrainNextRequiredAction`'s conflict gate
 * (first entry of `Object.entries(state.slots)`). Returns null when no slot
 * is in conflict.
 *
 * Used by the post-drain requested-slot pin (Cut #4, 2026-04-23) in
 * `octopus-channel/index.ts` so that `dialogState.requestedSlot` always
 * mirrors the directive-level conflict slot while a conflict is open,
 * instead of drifting to whatever slot happens to be missing next.
 *
 * IMPORTANT: this helper and the one-brain conflict gate MUST agree on
 * which slot is "the" conflict slot. Both use first-hit in entries order.
 * If either side changes selection policy, update the other in lockstep.
 *
 * DEPLOY_CANARY_DST_CONFLICT_SLOT_PIN_MARKER — do not remove. Deploy
 * verifier greps for this marker; absence means the deployed build
 * predates Cut #4 and stale-conflict split-brain can recur.
 */
export function findFirstConflictSlot(
  state: DialogState | null | undefined,
): SlotName | null {
  if (!state || !state.slots) return null;
  for (const [name, record] of Object.entries(state.slots)) {
    if (record && record.status === "conflict") {
      return name as SlotName;
    }
  }
  return null;
}

/**
 * Env-flag kill-switch for the whole DST layer. Default ON.
 *
 * When disabled:
 *   - `applyBookingFieldPatch` ignores the passed-in `dialogState` and
 *     returns without funneling writes through `updateSlot`.
 *   - `conversation-controller.ts` skips seeding / persisting dialog state.
 *   - The LLM prompt builder skips the `requested_slot` / `slot_conflicts`
 *     system lines.
 *   - The hallucination guard ignores the DST evidence branch and falls
 *     back to the legacy draft-level validator.
 *
 * Flip `RIDERS_DIALOG_STATE_ENABLED=0` (or `false`/`off`/`no`/`disabled`)
 * for emergency rollback to the pre-DST behavior.
 */
export function isDialogStateEnabled(
  env: NodeJS.ProcessEnv = process.env,
): boolean {
  const raw = env.RIDERS_DIALOG_STATE_ENABLED;
  if (raw == null) return true;
  const normalized = String(raw).trim().toLowerCase();
  if (["0", "false", "off", "no", "disabled"].includes(normalized)) {
    return false;
  }
  return true;
}

/** Map a booking-draft-level field write (role + address_part) to its
 *  canonical DST slot name. Returns null for patch keys that don't map to a
 *  slot (e.g. `phone_decision`, `address_role`). */
export function slotNameForBookingField(
  field: string,
  role: "pickup" | "delivery" | null,
): SlotName | null {
  switch (field) {
    case "sender_name":
      return "sender_name";
    case "sender_phone":
      return "sender_phone";
    case "recipient_name":
      return "recipient_name";
    case "recipient_phone":
      return "recipient_phone";
    case "address_block":
      return role === "pickup" ? "pickup_block" : role === "delivery" ? "delivery_block" : null;
    case "address_street":
      return role === "pickup" ? "pickup_street" : role === "delivery" ? "delivery_street" : null;
    case "address_house":
      return role === "pickup" ? "pickup_house" : role === "delivery" ? "delivery_house" : null;
    case "address_avenue":
      return role === "pickup" ? "pickup_avenue" : role === "delivery" ? "delivery_avenue" : null;
    case "address_extra":
      return role === "pickup" ? "pickup_extra" : role === "delivery" ? "delivery_extra" : null;
    default:
      return null;
  }
}
