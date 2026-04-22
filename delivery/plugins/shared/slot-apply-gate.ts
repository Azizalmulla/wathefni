// ---------------------------------------------------------------------------
// Phase 2 Milestone 2 (2026-04-22): turn_intent-gated slot-apply — SHADOW.
//
// DEPLOY_CANARY_SLOT_APPLY_GATE_MODULE_MARKER: M2 slot-apply gate shadow
//
// ## Architectural role
//
// Today every booking-draft slot write goes through `applyProposals` in
// `apply-boundary.ts`, which runs a schema/shape evidence contract
// (source-quote present, coherence on names, ambiguous-pair guard,
// requested-slot name-scope, shape validators). What that pipeline does
// NOT check is the SEMANTIC question: did the customer actually answer
// the ask on this turn? The 2026-04-22 pasted-operational-text incident
// is the canonical failure case — the LLM drained `sender_phone = "20260422"`
// lifted from an ISO timestamp, the patch passed every schema gate, and
// the draft advanced as if the customer had provided their phone.
//
// M2 inverts slot-apply: before any LLM-drained write lands, the apply
// layer checks `turn_intent` and refuses writes that the customer's
// utterance did not actually address:
//
//   - `unclear` / `acknowledgement` / `refused_or_stuck` /
//     `clarifying_question` → block_all (no writes this turn; draft
//     stays clean and the renderer re-asks).
//   - `answered_full` / `answered_partial` / `answered_unasked` /
//     `corrected_prior` → allow writes only for fields listed in
//     `addressed_fields`. Everything else in the patch is blocked.
//
// Missing `turn_intent` or `confidence: "low"` → allow (conservative; we
// do not punish the customer for a Phase-1 conformance miss or an
// ambiguous classification). Carryover proposals are always allowed —
// their ground truth is a persisted prior order, not a turn utterance,
// so `turn_intent` has no authority over them.
//
// ## Shadow-first
//
// This module ships the pure gate + an observability emit. The callsite
// computes the decision, emits a `[slot-apply-gate/shadow]` log, and
// still applies the write unchanged. A day or two of shadow logs on live
// traffic validates (a) the block rate on real turns, (b) the false-block
// rate vs turns where a write was actually legitimate, and (c) edge
// cases we didn't anticipate. Flip-to-live is a separate commit.
//
// ## Scope on this commit
//
// Shadow emit runs at the LLM-drain callsite only (callsite B in
// `octopus-channel/index.ts`). The fast-path pre-apply callsite (A) runs
// BEFORE the LLM turn and therefore cannot see this turn's
// `turn_intent`. Gating the fast-path would require re-architecting the
// pre-apply timing (e.g. running fast-path after the LLM call) or
// shipping a narrow fast-path hardening (Fix A). Both are separate
// work. M2 shadow on the LLM-drain path is where the bulk of the
// "schema-valid but meaning-invalid" writes happen.
//
// ## Exhaustiveness
//
// `KIND_BLOCK_POLICY` is typed `Record<TurnIntentKind, KindBlockBehaviour>`,
// enforced via `satisfies`. Adding a new `TurnIntentKind` to the proposer
// schema without updating the policy fails to compile — same tripwire as
// `DIRECTIVE_REPLY_RENDERERS` and `ACK_PREFIX_REGISTRY`.
// ---------------------------------------------------------------------------

import type {
  TurnIntentKind,
  TurnIntentConfidence,
  TurnIntentAddressedField,
} from "./proposer-schema";
import type { BookingFieldPatch, AddressRole } from "./booking-draft";
import type { ProposalSource } from "./apply-boundary";

// ---------------------------------------------------------------------------
// Discriminated result.
//
// `allow`         → write proceeds with the full patch.
// `block_all`     → no writes land this turn. The LLM mis-interpreted the
//                   ask — honour the `turn_intent` kind, drop the patch.
// `block_partial` → some patch fields survive, others are dropped because
//                   the turn did not address them. The caller masks the
//                   patch fields in `blockedFields` before calling
//                   `applyProposals` (flip-to-live path); shadow mode
//                   just logs the decision.
//
// All three carry a machine-readable `reason`; the emit prints it so the
// analyzer can bucket decisions without parsing intent.
// ---------------------------------------------------------------------------

export type SlotApplyGateDecision =
  | { kind: "allow"; reason: SlotApplyGateAllowReason }
  | { kind: "block_all"; reason: SlotApplyGateBlockReason }
  | {
      kind: "block_partial";
      reason: "field_not_in_addressed";
      blockedFields: readonly string[];
      /** Fields the patch carries that WERE in `addressed_fields`. Kept
       *  for log legibility; the caller doesn't need them separately. */
      allowedFields: readonly string[];
    };

export type SlotApplyGateAllowReason =
  // Carryover proposals are ground-truth historical; turn_intent has no
  // authority over them.
  | "source_carryover_exempt"
  // turn_intent not emitted by the LLM (Phase-1 conformance miss).
  // Conservative default; we do not block on missing signal.
  | "turn_intent_missing"
  // LLM declared a low-confidence classification. Don't punish slot
  // writes for an uncertain kind — the fallback is the existing
  // schema/shape contract.
  | "low_confidence"
  // The classification kind accepts writes AND every field in the patch
  // was listed in `addressed_fields` (or mapped to a token that was).
  | "all_fields_addressed"
  // The classification kind accepts writes AND the LLM marked
  // `addressed_fields = []`. Permissive fallback: the LLM signalled
  // "answered" without tagging fields, we trust the schema/shape layer
  // to validate the write rather than block it outright.
  | "addressed_fields_empty_permissive"
  // Patch had no data-bearing fields to gate (meta-only, e.g. only
  // `address_role` with no address parts). Skip the gate.
  | "empty_patch_after_meta_filter";

export type SlotApplyGateBlockReason =
  | "ti_kind_unclear"
  | "ti_kind_acknowledgement"
  | "ti_kind_refused_or_stuck"
  | "ti_kind_clarifying_question";

// ---------------------------------------------------------------------------
// Per-kind block policy.
//
// Each row says what to do when `turn_intent.kind === K`. Kinds that
// accept writes ("check_addressed") fall through to the per-field
// `addressed_fields` check. Kinds that refuse writes ("block_all") short-
// circuit at that level.
// ---------------------------------------------------------------------------

type KindBlockBehaviour =
  | { kind: "block_all"; reason: SlotApplyGateBlockReason }
  | { kind: "check_addressed" };

const KIND_BLOCK_POLICY = {
  // Answer-like kinds: accept writes, but only for addressed fields.
  answered_full: { kind: "check_addressed" },
  answered_partial: { kind: "check_addressed" },
  answered_unasked: { kind: "check_addressed" },
  corrected_prior: { kind: "check_addressed" },

  // Non-answer kinds: refuse every write on this turn.
  unclear: { kind: "block_all", reason: "ti_kind_unclear" },
  acknowledgement: { kind: "block_all", reason: "ti_kind_acknowledgement" },
  refused_or_stuck: {
    kind: "block_all",
    reason: "ti_kind_refused_or_stuck",
  },
  clarifying_question: {
    kind: "block_all",
    reason: "ti_kind_clarifying_question",
  },
} as const satisfies Record<TurnIntentKind, KindBlockBehaviour>;

// ---------------------------------------------------------------------------
// BookingFieldPatch → TurnIntent addressed_fields mapping.
//
// The proposer schema's `addressed_fields` enum is intentionally coarser
// than `BookingFieldPatch` keys — policy cares about "did they address the
// pickup address?" as a unit, not which of block / street / house /
// avenue / extra was named. This mapping reflects that contract.
//
//   - Identity patch fields map 1:1 to identity tokens.
//   - `phone_decision` maps to `sender_phone`. A `phone_decision=use_whatsapp`
//     IS the sender-phone answer; treating it as `sender_phone`-addressed
//     keeps the gate consistent with the WA-equivalence normalization
//     that runs upstream in `apply-boundary.ts`.
//   - Address-part fields (`address_block` / `address_street` / `address_house`
//     / `address_avenue` / `address_extra`) depend on `patch.address_role`:
//     `"pickup"` → `pickup_address`; `"delivery"` → `delivery_address`.
//     A missing or invalid role means we cannot determine which coarse
//     token the part belongs to — the safe shadow-mode choice is to emit
//     `null` from the mapper, treat it as "ungateable", and include it
//     in neither allowed nor blocked. The caller records the count in
//     the log (`ungateable_fields`).
//   - `address_role` itself carries no data; skipped by `patchDataFields`
//     below before it reaches the mapper.
//
// Route-token expansion: when `addressed_fields` contains `"route"`, we
// treat it as having addressed BOTH `pickup_area` and `dropoff_area`.
// This matches the semantic in the proposer schema description.
// `BookingFieldPatch` has neither `pickup_area` nor `dropoff_area` keys
// today — areas are written via `set_pending_area` / active-route state,
// not through the boundary — so route expansion is forward-compatible
// but doesn't fire on any write path in this PR.
// ---------------------------------------------------------------------------

export function patchFieldToAddressedToken(
  field: keyof BookingFieldPatch,
  addressRole: AddressRole | null,
): TurnIntentAddressedField | null {
  switch (field) {
    case "sender_name":
      return "sender_name";
    case "sender_phone":
    case "phone_decision":
      return "sender_phone";
    case "recipient_name":
      return "recipient_name";
    case "recipient_phone":
      return "recipient_phone";
    case "address_block":
    case "address_street":
    case "address_house":
    case "address_avenue":
    case "address_extra":
      if (addressRole === "pickup") return "pickup_address";
      if (addressRole === "delivery") return "delivery_address";
      return null;
    case "address_role":
      // Meta; never participates in gating. Upstream filter drops it.
      return null;
    default: {
      // Defensive — future field additions to BookingFieldPatch must
      // update this mapper. Unknown fields fall through as ungateable.
      const _exhaustive: never = field as never;
      void _exhaustive;
      return null;
    }
  }
}

/** Data-bearing subset of BookingFieldPatch keys (drops `address_role`). */
export const GATED_PATCH_FIELDS: readonly (keyof BookingFieldPatch)[] = [
  "sender_name",
  "sender_phone",
  "phone_decision",
  "recipient_name",
  "recipient_phone",
  "address_block",
  "address_street",
  "address_house",
  "address_avenue",
  "address_extra",
];

function isDataBearing(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim().length > 0;
  return true;
}

/** Extract the data-bearing field keys from a patch, in the order defined
 *  by `GATED_PATCH_FIELDS`. Drops null/empty values and meta fields. */
export function extractDataFieldsFromPatch(
  patch: BookingFieldPatch,
): (keyof BookingFieldPatch)[] {
  const out: (keyof BookingFieldPatch)[] = [];
  for (const field of GATED_PATCH_FIELDS) {
    if (isDataBearing(patch[field])) {
      out.push(field);
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Gate input shape.
// ---------------------------------------------------------------------------

export interface SlotApplyGateInput {
  tiKind: TurnIntentKind | null;
  tiConfidence: TurnIntentConfidence | null;
  tiAddressedFields: readonly TurnIntentAddressedField[] | null;
  proposalSource: ProposalSource;
  patch: BookingFieldPatch;
}

// ---------------------------------------------------------------------------
// Gate function.
// ---------------------------------------------------------------------------

export function decideSlotApplyGate(
  input: SlotApplyGateInput,
): SlotApplyGateDecision {
  // 1. Carryover is exempt — ground-truth historical, not turn-derived.
  if (input.proposalSource === "carryover") {
    return { kind: "allow", reason: "source_carryover_exempt" };
  }

  // 2. Missing turn_intent — conservative allow. Phase-1 conformance miss
  //    should not manifest as a write failure.
  if (input.tiKind === null) {
    return { kind: "allow", reason: "turn_intent_missing" };
  }

  // 3. Low-confidence — conservative allow. We'd rather accept a possibly
  //    wrong write than block a possibly-right write on a `low` signal
  //    during the M2 rollout window. Can be tightened later.
  if (input.tiConfidence === "low") {
    return { kind: "allow", reason: "low_confidence" };
  }

  // 4. Per-kind policy.
  const policy = KIND_BLOCK_POLICY[input.tiKind];
  if (policy.kind === "block_all") {
    return { kind: "block_all", reason: policy.reason };
  }

  // 5. Answer-like kind. Extract data fields from patch; if there are
  //    none, nothing to gate.
  const dataFields = extractDataFieldsFromPatch(input.patch);
  if (dataFields.length === 0) {
    return { kind: "allow", reason: "empty_patch_after_meta_filter" };
  }

  // 6. Per-field check against addressed_fields.
  const addressed = input.tiAddressedFields ?? [];
  if (addressed.length === 0) {
    // LLM classified as answered_* but didn't tag which fields. Permissive
    // fallback — let the schema/shape layer validate.
    return { kind: "allow", reason: "addressed_fields_empty_permissive" };
  }

  const addressedSet = new Set<string>(addressed);
  if (addressedSet.has("route")) {
    addressedSet.add("pickup_area");
    addressedSet.add("dropoff_area");
  }

  const addressRole =
    (input.patch.address_role as AddressRole | null | undefined) ?? null;

  const allowedFields: string[] = [];
  const blockedFields: string[] = [];
  for (const field of dataFields) {
    const token = patchFieldToAddressedToken(field, addressRole);
    if (token === null) {
      // Ungateable (e.g. address part without a role). Shadow-mode
      // default: DO NOT add to blocked. Count it in the log so we can
      // see how often it happens; don't let it drive false blocks.
      continue;
    }
    if (addressedSet.has(token)) {
      allowedFields.push(field);
    } else {
      blockedFields.push(field);
    }
  }

  if (blockedFields.length === 0) {
    return { kind: "allow", reason: "all_fields_addressed" };
  }
  return {
    kind: "block_partial",
    reason: "field_not_in_addressed",
    blockedFields,
    allowedFields,
  };
}

// ---------------------------------------------------------------------------
// Shadow-emit helper.
//
// One-line token shape; stays consistent with other shadow logs in this
// plugin (`[reply-compose/shadow]`, `[structured-output/proposer]`) so the
// analyzer can parse them uniformly.
// ---------------------------------------------------------------------------

export interface SlotApplyGateShadowEmit {
  conversation_id: string;
  turn_id: string | null;
  proposal_source: ProposalSource;
  ti_kind: string;
  ti_confidence: string;
  ti_addressed_fields_count: number;
  patch_data_fields_count: number;
  ungateable_fields_count: number;
  decision_kind: "allow" | "block_all" | "block_partial";
  decision_reason: string;
  blocked_fields: readonly string[];
  allowed_fields: readonly string[];
}

export function formatSlotApplyGateShadowLog(
  e: SlotApplyGateShadowEmit,
): string {
  const blocked = e.blocked_fields.length > 0 ? e.blocked_fields.join("|") : "-";
  const allowed = e.allowed_fields.length > 0 ? e.allowed_fields.join("|") : "-";
  return (
    `[slot-apply-gate/shadow] ` +
    `conversation=${e.conversation_id} ` +
    `turn_id=${e.turn_id || "-"} ` +
    `source=${e.proposal_source} ` +
    `ti_kind=${e.ti_kind} ` +
    `ti_confidence=${e.ti_confidence} ` +
    `ti_addressed_count=${e.ti_addressed_fields_count} ` +
    `patch_fields_count=${e.patch_data_fields_count} ` +
    `ungateable_count=${e.ungateable_fields_count} ` +
    `decision=${e.decision_kind} ` +
    `reason=${e.decision_reason} ` +
    `blocked=[${blocked}] ` +
    `allowed=[${allowed}]`
  );
}

/** Helper that computes the `ungateable_fields_count` for a patch — the
 *  number of data fields whose token mapping returned `null`. Exported so
 *  the callsite can produce the shadow emit without duplicating logic. */
export function countUngateablePatchFields(patch: BookingFieldPatch): number {
  const dataFields = extractDataFieldsFromPatch(patch);
  const addressRole =
    (patch.address_role as AddressRole | null | undefined) ?? null;
  let count = 0;
  for (const field of dataFields) {
    if (patchFieldToAddressedToken(field, addressRole) === null) count += 1;
  }
  return count;
}
