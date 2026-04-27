// ---------------------------------------------------------------------------
// Phase 2: directive → server-composed reply registry (2026-04-20).
//
// ## Architectural role
//
// Before Phase 2, every field-ask, recipient-ask, address-ask, and
// conflict-confirm reply was phrased by the LLM. We told it WHICH field
// to ask for via `next_required_action: ASK_X`, and steered it with
// `forbidden_reply_shapes` — but the reply text itself was LLM-authored.
// Drift was constant: wrong field, merged sender+recipient asks, double
// asks, apology noise, asking the wrong side. We caught some failures
// via forbidden-shape substitutions; most we didn't.
//
// Phase 2 moves every directive-driven ask into a server-composed reply
// rendered from state. The LLM's draft reply is substituted at Region A
// of the outbound decision when a directive is active AND the registry
// has a renderer for it.
//
// ## Exhaustiveness contract
//
// `DirectiveAction` is the discriminated union of every value
// `computeOneBrainNextRequiredAction` can emit. `DIRECTIVE_REPLY_RENDERERS`
// is `Record<DirectiveAction, DirectiveReplyRendererSpec>`, enforced by
// TypeScript — adding a new directive without an entry here fails to
// compile. This is the tripwire the user specified: "adding a new
// directive without a renderer fails to build".
//
// Each entry is one of:
//
//   - `{ kind: "server", render: fn }`            — this registry owns the
//                                                   reply. Region A will
//                                                   substitute via `render`.
//   - `{ kind: "llm_owned", rationale: "…" }`     — intentionally left to
//                                                   the LLM (e.g. post-order
//                                                   intent routing; summary
//                                                   text is a Phase 3 target).
//
// Authority-cutover Phase 6 (2026-04-23): the former third variant
// (`server_existing`, referencing the A0/A0a/A0b Region-A substitutions)
// is gone. Those substitutions were deleted in cutover phases 2-3, so
// the `kind: "server_existing"` entries referenced a render path that
// no longer existed. Removed along with the four directives that used
// it: ASK_PICKUP_ADDRESS_FOR_MANUAL_CONFIRM,
// ASK_DELIVERY_ADDRESS_FOR_MANUAL_CONFIRM,
// REQUEST_HANDOFF_FOR_MANUAL_CONFIRM, CLARIFY_OPTION_BEFORE_PROCEED.
// The LLM now handles manual-confirm end-to-end via hard rule 8 +
// `manual_confirmation_required` facts in the prompt.
//
// The dispatcher `renderDirectiveReply` returns a discriminated result
// that lets the outbound-decision module decide what to do:
//
//   - `{ kind: "render"; text }`   → substitute with `text`
//   - `{ kind: "llm_owned" }`      → pass the LLM's draft through unchanged
//   - `{ kind: "unknown_action" }` → unknown directive (defensive; should
//                                    never fire because of the exhaustive
//                                    type, but covers the case where a
//                                    runtime string escapes the type
//                                    contract).
//
// ## Variability
//
// Each `render` picks one of a small phrasing pool via a turn-id-seeded
// hash (`pickPhrasingIndex`). Deterministic per turn — re-rendering the
// same turn yields the same text — and varied across turns so the bot
// doesn't sound robotic.
// ---------------------------------------------------------------------------

import type {
  PersistedBookingDraft,
  PersistedConversationControllerEntry,
} from "./conversation-policy";
import {
  getEffectivePickupAreaName,
  getEffectiveDeliveryAreaName,
} from "./conversation-policy";
import { buildDeterministicOrderSummary } from "./outbound-verify";
import type { SlotName } from "./dialog-state";

// ---------------------------------------------------------------------------
// Localized slot-label maps.
//
// `CONFIRM_SLOT_CONFLICT` names the disputed field in its prompt. Before
// 2026-04-22 the renderer derived the label purely by replacing `_` with
// a space on the raw DST slot name (`sender_name` → "sender name"). That
// was accidentally readable in English and a bug in Arabic, where the
// English token got plugged into an Arabic sentence — e.g. the transcript
// leak `القيمة الصحيحة للـ sender name؟` (conv 19294, 2026-04-22).
//
// These maps are `Record<SlotName, string>`, so adding a new slot name
// to the `SlotName` union without adding a label here is a compile error
// — the same exhaustiveness contract `DIRECTIVE_REPLY_RENDERERS` relies
// on for directives. The runtime type of `conflictingSlot` in the
// renderer context is `string | null` rather than `SlotName`, so a
// malformed value is still possible at runtime; `slotLabel()` below logs
// loudly via `console.warn` (deduped per-process) and falls back to the
// underscore-stripped form rather than crashing or emitting a silent
// bug.
// ---------------------------------------------------------------------------

const SLOT_LABELS_AR: Record<SlotName, string> = {
  sender_name: "اسم المرسل",
  sender_phone: "رقم المرسل",
  recipient_name: "اسم المستلم",
  recipient_phone: "رقم المستلم",
  pickup_area: "منطقة الاستلام",
  dropoff_area: "منطقة التسليم",
  pickup_block: "قطعة الاستلام",
  pickup_street: "شارع الاستلام",
  pickup_house: "منزل/مبنى الاستلام",
  pickup_avenue: "جادة الاستلام",
  pickup_extra: "تفاصيل الاستلام",
  delivery_block: "قطعة التسليم",
  delivery_street: "شارع التسليم",
  delivery_house: "منزل/مبنى التسليم",
  delivery_avenue: "جادة التسليم",
  delivery_extra: "تفاصيل التسليم",
};

// English labels intentionally mirror the legacy "underscore-stripped"
// form (e.g. `pickup_extra` → "pickup extra") one-for-one. The accidental
// readability of raw slot keys in English means pre-2026-04-22 customer
// UX is preserved byte-for-byte on the EN path, so this patch is an
// AR-only fix in customer-visible behaviour. Keeping the map here (and
// making it `Record<SlotName, string>`) still gives us the compile-time
// guarantee that a new slot name carries both an EN and AR label rather
// than falling back silently.
const SLOT_LABELS_EN: Record<SlotName, string> = {
  sender_name: "sender name",
  sender_phone: "sender phone",
  recipient_name: "recipient name",
  recipient_phone: "recipient phone",
  pickup_area: "pickup area",
  dropoff_area: "dropoff area",
  pickup_block: "pickup block",
  pickup_street: "pickup street",
  pickup_house: "pickup house",
  pickup_avenue: "pickup avenue",
  pickup_extra: "pickup extra",
  delivery_block: "delivery block",
  delivery_street: "delivery street",
  delivery_house: "delivery house",
  delivery_avenue: "delivery avenue",
  delivery_extra: "delivery extra",
};

// Dedupes the fallback warning to one `console.warn` per process per
// unique (lang, slot) tuple. The renderer is called inside the turn hot
// path; if a bug upstream starts flooding unknown slot names, one line
// per tuple is enough to surface it without drowning the log stream.
const SLOT_LABEL_WARN_ONCE = new Set<string>();

function slotLabel(language: "ar" | "en", slot: string): string {
  const map = language === "ar" ? SLOT_LABELS_AR : SLOT_LABELS_EN;
  const hit = (map as Record<string, string>)[slot];
  if (hit) return hit;
  const warnKey = `${language}::${slot}`;
  if (!SLOT_LABEL_WARN_ONCE.has(warnKey)) {
    SLOT_LABEL_WARN_ONCE.add(warnKey);
    try {
      console.warn(
        `[slot-label-fallback] language=${language} slot=${JSON.stringify(slot)} remediation=add_entry_to_SLOT_LABELS_${language.toUpperCase()}_in_directive_reply_registry`,
      );
    } catch {
      // console.warn failure is not worth crashing the render.
    }
  }
  return slot.replace(/_/g, " ");
}

// ---------------------------------------------------------------------------
// Directive action union (compile-time exhaustive).
// ---------------------------------------------------------------------------

export type DirectiveAction =
  // Area-resolution gate — SERVER-COMPOSED (Phase 2).
  | "ASK_MISSING_AREAS"
  | "ASK_PICKUP_AREA"
  | "ASK_DELIVERY_AREA"
  // Collection-flow field asks — SERVER-COMPOSED (Phase 2).
  | "ASK_SENDER_NAME_AND_PHONE_DECISION"
  // Narrower sender ask — emitted when the sender phone is already
  // resolved (either via a direct write or a `use_whatsapp` decision)
  // but the sender name is still missing. Added 2026-04-22 to stop
  // re-emitting the combined ask after only the phone landed. See
  // `one-brain-context.ts` selector and the live-run sender-step
  // incident on conversation 19399.
  | "ASK_SENDER_NAME"
  | "ASK_SENDER_PHONE"
  | "ASK_RECIPIENT_NAME_AND_PHONE"
  | "ASK_PICKUP_ADDRESS"
  | "ASK_DELIVERY_ADDRESS"
  | "CONFIRM_SLOT_CONFLICT"
  // Defensive fallback — should not fire given the current
  // `collectionMissing` filter, but the compile-time exhaustiveness
  // tripwire forces us to carry a renderer.
  | "COLLECT_NEXT_MISSING_FIELD"
  // LLM-owned: the customer's post-order intent is context-dependent
  // (track vs cancel vs re-order vs handoff); a generic renderer would
  // be a downgrade. The hallucination guard uses this action as its
  // signal to repair post-order-flow hallucinations via a deterministic
  // nudge (see `reply-hallucination-guard.ts`).
  | "POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF"
  // LLM-owned for Phase 2 — becomes server-composed in Phase 3.
  | "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED";

// ---------------------------------------------------------------------------
// Renderer types.
// ---------------------------------------------------------------------------

export type DirectiveReplyRendererContext = {
  language: "ar" | "en";
  draft: PersistedBookingDraft;
  entry: PersistedConversationControllerEntry;
  /** Slot name for CONFIRM_SLOT_CONFLICT. Null for other directives. */
  conflictingSlot?: string | null;
  /** For CONFIRM_SLOT_CONFLICT — the two conflicting values to surface. */
  conflictValues?: { incoming: string; existing: string } | null;
  /**
   * Stable identifier for variability seed. Phase B (2026-04-22) trim
   * collapsed every non-area-clarification renderer to a single facts-
   * only phrasing, so the seed no longer affects output for the trimmed
   * directives — kept in the type signature because the area-
   * clarification generic fallbacks (`renderAskPickupArea` /
   * `renderAskDeliveryArea`) still use `pick()` when no preserved side
   * and no option list are available.
   */
  turnSeed: string;
};

export type DirectiveReplyRenderer = (
  ctx: DirectiveReplyRendererContext,
) => string;

type DirectiveReplyRendererSpec =
  | { kind: "server"; render: DirectiveReplyRenderer }
  | { kind: "llm_owned"; rationale: string };

// ---------------------------------------------------------------------------
// Dispatcher return shape.
// ---------------------------------------------------------------------------

export type DirectiveReplyRenderResult =
  | { kind: "render"; text: string }
  | { kind: "llm_owned"; rationale: string }
  | { kind: "unknown_action"; action: string };

// ---------------------------------------------------------------------------
// Phrasing-pool helper.
//
// Deterministic pick from a small set of phrasings seeded on the turn id.
// Cheap djb2-style hash; stability matters more than distribution.
// ---------------------------------------------------------------------------

function hashSeed(seed: string): number {
  let h = 5381;
  for (let i = 0; i < seed.length; i++) {
    h = ((h << 5) + h) ^ seed.charCodeAt(i);
  }
  return Math.abs(h >>> 0);
}

export function pickPhrasingIndex(seed: string, count: number): number {
  if (count <= 1) return 0;
  return hashSeed(seed || "") % count;
}

function pick<T>(seed: string, options: T[]): T {
  return options[pickPhrasingIndex(seed, options.length)];
}

// ---------------------------------------------------------------------------
// Renderers.
// ---------------------------------------------------------------------------

function renderAskMissingAreas(ctx: DirectiveReplyRendererContext): string {
  // Phase B trim (2026-04-22): single facts-only phrasing, no pool.
  if (ctx.language === "ar") {
    return "منطقة الاستلام ومنطقة التوصيل؟";
  }
  return "Pickup area and delivery area?";
}

// Area-clarification renderers (ASK_PICKUP_AREA / ASK_DELIVERY_AREA).
//
// The server fires these whenever `computeOneBrainNextRequiredAction` sees
// the controller mid-booking with one route leg missing. In practice the
// most common shape is the "one leg ambiguous" flow: the customer said
// e.g. "salmiya to kuwait city", the pricing tool resolved Salmiya and
// flagged "Kuwait City" as an ambiguity_group, and we now need to ask the
// customer which sub-area they meant.
//
// Behavior:
//   1. Always recap the preserved side when we know it
//      (`pendingPickupAreaNameEn` / `pendingDropoffAreaNameEn` —
//      pricing.ts pushes `set_pending_area` for the leg that resolved).
//      This keeps the customer oriented and anchors the LLM-free
//      reply to real state, so the generic fallback
//      ("What's the delivery area?") never fires when the server has
//      better context.
//   2. Surface the ambiguity options when we have them
//      (`dialogState.requestedSlot.options` — pricing.ts pushes
//      `set_requested_slot` with the candidate list for
//      ambiguity-group cases, e.g. Kuwait City →
//      [Sharq, Mirqab, Qibla, Bnaid Al-Qar, Dasman]).
//   3. Fall back to a generic ask only when neither is present.

function extractRequestedOptions(
  entry: PersistedConversationControllerEntry,
  slotName: "pickup_area" | "dropoff_area",
): string[] {
  const slot = entry.dialogState?.requestedSlot;
  if (!slot || slot.name !== slotName) return [];
  const options = Array.isArray(slot.options) ? slot.options : [];
  return options.map((o) => (typeof o === "string" ? o.trim() : "")).filter(Boolean);
}

function renderAskPickupArea(ctx: DirectiveReplyRendererContext): string {
  const preservedDelivery =
    ctx.entry.quoteDropoffAreaNameEn ||
    ctx.entry.pendingDropoffAreaNameEn ||
    null;
  const preservedDeliveryAr =
    ctx.entry.quoteDropoffAreaNameAr ||
    ctx.entry.pendingDropoffAreaNameAr ||
    null;
  const options = extractRequestedOptions(ctx.entry, "pickup_area");

  if (ctx.language === "ar") {
    const deliveryLabel = preservedDeliveryAr || preservedDelivery;
    if (deliveryLabel && options.length > 0) {
      return `توصيل إلى ${deliveryLabel}. شنو منطقة الاستلام بالضبط (${options.join("، ")})؟`;
    }
    if (deliveryLabel) {
      return `توصيل إلى ${deliveryLabel}. شنو منطقة الاستلام بالضبط؟`;
    }
    if (options.length > 0) {
      return `شنو منطقة الاستلام بالضبط (${options.join("، ")})؟`;
    }
    return pick(ctx.turnSeed, [
      "شنو منطقة الاستلام بالضبط؟",
      "عطنا منطقة الاستلام (مثل: السالمية، الجابرية، حولي).",
      "من أي منطقة نستلم؟",
    ]);
  }

  if (preservedDelivery && options.length > 0) {
    return `Delivery to ${preservedDelivery}. What's the pickup area (${options.join(", ")})?`;
  }
  if (preservedDelivery) {
    return `Delivery to ${preservedDelivery}. What's the pickup area?`;
  }
  if (options.length > 0) {
    return `What's the pickup area (${options.join(", ")})?`;
  }
  return pick(ctx.turnSeed, [
    "What's the pickup area?",
    "Could you share the pickup area (e.g. Salmiya, Jabriya, Hawalli)?",
    "Which area is the pickup from?",
  ]);
}

function renderAskDeliveryArea(ctx: DirectiveReplyRendererContext): string {
  const preservedPickup =
    ctx.entry.quotePickupAreaNameEn ||
    ctx.entry.pendingPickupAreaNameEn ||
    null;
  const preservedPickupAr =
    ctx.entry.quotePickupAreaNameAr ||
    ctx.entry.pendingPickupAreaNameAr ||
    null;
  const options = extractRequestedOptions(ctx.entry, "dropoff_area");

  if (ctx.language === "ar") {
    const pickupLabel = preservedPickupAr || preservedPickup;
    if (pickupLabel && options.length > 0) {
      return `استلام من ${pickupLabel}. شنو منطقة التوصيل بالضبط (${options.join("، ")})؟`;
    }
    if (pickupLabel) {
      return `استلام من ${pickupLabel}. شنو منطقة التوصيل بالضبط؟`;
    }
    if (options.length > 0) {
      return `شنو منطقة التوصيل بالضبط (${options.join("، ")})؟`;
    }
    return pick(ctx.turnSeed, [
      "شنو منطقة التوصيل بالضبط؟",
      "عطنا منطقة التوصيل (مثل: السالمية، الجابرية، حولي).",
      "إلى أي منطقة نوصل؟",
    ]);
  }

  if (preservedPickup && options.length > 0) {
    return `Pickup from ${preservedPickup}. What's the delivery area (${options.join(", ")})?`;
  }
  if (preservedPickup) {
    return `Pickup from ${preservedPickup}. What's the delivery area?`;
  }
  if (options.length > 0) {
    return `What's the delivery area (${options.join(", ")})?`;
  }
  return pick(ctx.turnSeed, [
    "What's the delivery area?",
    "Could you share the delivery area (e.g. Salmiya, Jabriya, Hawalli)?",
    "Which area is the delivery to?",
  ]);
}

function renderCollectNextMissingField(
  ctx: DirectiveReplyRendererContext,
): string {
  // Defensive fallback — the concrete ASK_* branches should always win.
  // If this fires, the concrete directive logic has a gap and we should
  // fix it rather than rely on the generic phrasing.
  if (ctx.language === "ar") {
    return "البيانات الناقصة؟";
  }
  return "Remaining booking details?";
}

function renderAskSenderNameAndPhoneDecision(
  ctx: DirectiveReplyRendererContext,
): string {
  // Phase B trim (2026-04-22): worst offender pre-trim (mean=100, 55%
  // verb overhead, pool=3). Collapsed to a single facts-only phrasing
  // that decomposes the compound ask into two short clauses. The
  // semantic of "is this WhatsApp number the sender's?" and "should we
  // use this number for the sender?" is identical from the customer's
  // POV, so we pick the shorter framing.
  if (ctx.language === "ar") {
    return "اسم المرسل الكامل؟ نستخدم رقم الواتساب هذا أو رقم ثاني؟";
  }
  return "Sender's full name? Use this WhatsApp number, or a different one?";
}

function renderAskSenderName(ctx: DirectiveReplyRendererContext): string {
  // Narrow sender-name ask. Fired when the sender phone is already
  // resolved (draft.senderPhone populated — either via a `use_whatsapp`
  // decision or an explicit write) but the sender name is still
  // missing. The factual anchor is intentionally minimal: saying more
  // risks repeating the previous combined ask, which is precisely what
  // this directive exists to stop.
  if (ctx.language === "ar") {
    return "اسم المرسل الكامل؟";
  }
  return "Sender's full name?";
}

function renderAskSenderPhone(ctx: DirectiveReplyRendererContext): string {
  // Phase B trim: preserve the sender-name fact as a brief anchor; drop
  // the pool entirely.
  const senderName = (ctx.draft.senderName || "").trim();
  if (ctx.language === "ar") {
    return senderName
      ? `تمام ${senderName}. رقم المرسل؟`
      : "رقم المرسل؟";
  }
  return senderName
    ? `Thanks ${senderName}. Sender's phone number?`
    : "Sender's phone number?";
}

function renderAskRecipientNameAndPhone(
  ctx: DirectiveReplyRendererContext,
): string {
  // Phase B trim: single facts-only phrasing, no pool.
  if (ctx.language === "ar") {
    return "اسم المستلم الكامل ورقمه؟";
  }
  return "Recipient's full name and phone number?";
}

function renderAskPickupAddress(ctx: DirectiveReplyRendererContext): string {
  // Phase B trim: single facts-only phrasing, no pool. Area fact
  // preserved when known (keeps customer oriented).
  const areaName =
    ctx.language === "ar"
      ? (ctx.entry.quotePickupAreaNameAr ||
          ctx.entry.pendingPickupAreaNameAr ||
          getEffectivePickupAreaName(ctx.draft, ctx.entry) ||
          null)
      : getEffectivePickupAreaName(ctx.draft, ctx.entry);
  if (ctx.language === "ar") {
    const suffix = areaName ? ` في ${areaName}` : "";
    return `عنوان الاستلام${suffix} — قطعة، شارع، مبنى/شقة؟`;
  }
  const suffix = areaName ? ` in ${areaName}` : "";
  return `Pickup address${suffix} — block, street, building/apartment?`;
}

function renderAskDeliveryAddress(ctx: DirectiveReplyRendererContext): string {
  // Phase B trim: single facts-only phrasing, no pool. Area fact
  // preserved when known.
  const areaName =
    ctx.language === "ar"
      ? (ctx.entry.quoteDropoffAreaNameAr ||
          ctx.entry.pendingDropoffAreaNameAr ||
          getEffectiveDeliveryAreaName(ctx.draft, ctx.entry) ||
          null)
      : getEffectiveDeliveryAreaName(ctx.draft, ctx.entry);
  if (ctx.language === "ar") {
    const suffix = areaName ? ` في ${areaName}` : "";
    return `عنوان التوصيل${suffix} — قطعة، شارع، مبنى/شقة؟`;
  }
  const suffix = areaName ? ` in ${areaName}` : "";
  return `Delivery address${suffix} — block, street, building/apartment?`;
}

function renderFullOrderSummary(ctx: DirectiveReplyRendererContext): string {
  // Phase 3 (2026-04-20): the summary is now server-composed from
  // controller state. Delegates to the same canonical builder that
  // previously served as the C-drift substitute (see
  // `buildDeterministicOrderSummary` in `shared/outbound-verify.ts`),
  // so the format is identical and the post-state C-drift guard
  // effectively becomes a regression alarm — if it ever fires after
  // Phase 3, either Phase 3 didn't substitute or the LLM wrote its
  // own summary before our substitution could apply, both of which
  // are bugs worth surfacing.
  return buildDeterministicOrderSummary({
    entry: ctx.entry,
    language: ctx.language,
  });
}

function renderConfirmSlotConflict(ctx: DirectiveReplyRendererContext): string {
  // Phase B trim: single facts-only phrasing, no pool. The slot label
  // and the two conflicting values ARE the facts; everything else is
  // removable framing.
  //
  // 2026-04-22: slot labels are now looked up via `slotLabel()` so the
  // AR prompt stops leaking raw English DST keys (`sender_name` → no
  // longer surfaces in Arabic output). Missing keys fall back to the
  // legacy underscore-stripped form + `console.warn` so the bug is
  // loud rather than silent. The compile-time
  // `Record<SlotName, string>` shape on the label maps enforces that
  // every new slot added to the DST gets both EN and AR labels.
  const rawSlot = ctx.conflictingSlot || null;
  if (!rawSlot) {
    return ctx.language === "ar"
      ? "ارسل اسم الحقل والقيمة الصحيحة للتعديل."
      : "Please send the field name and the correct value for the edit.";
  }
  const label = rawSlot
    ? slotLabel(ctx.language, rawSlot)
    : ctx.language === "ar"
      ? "هذا الحقل"
      : "that field";
  const incoming = ctx.conflictValues?.incoming || null;
  const existing = ctx.conflictValues?.existing || null;
  const both = incoming && existing;
  if (ctx.language === "ar") {
    if (both) {
      return `${label}: «${existing}» أو «${incoming}»؟`;
    }
    // Note: we use the preposition `لـ` (without the definite article
    // `ال`) because every entry in `SLOT_LABELS_AR` already carries its
    // own article (e.g. "اسم المرسل"). Before the AR label map landed,
    // the prompt used `للـ ` (for the) with the raw English slot key
    // plugged in after the space — grammatically accidental and
    // visually broken. `لـ ${label}` reads correctly for every entry in
    // the map.
    return `القيمة الصحيحة لـ ${label}؟`;
  }
  if (both) {
    return `${label}: "${existing}" or "${incoming}"?`;
  }
  return `Correct value for ${label}?`;
}

// ---------------------------------------------------------------------------
// Registry (compile-time exhaustive).
//
// `satisfies Record<DirectiveAction, …>` enforces that every member of
// the union has an entry. Adding a new directive to `DirectiveAction`
// without updating this object is a type error.
// ---------------------------------------------------------------------------

export const DIRECTIVE_REPLY_RENDERERS = {
  ASK_MISSING_AREAS: { kind: "server", render: renderAskMissingAreas },
  ASK_PICKUP_AREA: { kind: "server", render: renderAskPickupArea },
  ASK_DELIVERY_AREA: { kind: "server", render: renderAskDeliveryArea },
  COLLECT_NEXT_MISSING_FIELD: {
    kind: "server",
    render: renderCollectNextMissingField,
  },

  ASK_SENDER_NAME_AND_PHONE_DECISION: {
    kind: "server",
    render: renderAskSenderNameAndPhoneDecision,
  },
  ASK_SENDER_NAME: { kind: "server", render: renderAskSenderName },
  ASK_SENDER_PHONE: { kind: "server", render: renderAskSenderPhone },
  ASK_RECIPIENT_NAME_AND_PHONE: {
    kind: "server",
    render: renderAskRecipientNameAndPhone,
  },
  ASK_PICKUP_ADDRESS: { kind: "server", render: renderAskPickupAddress },
  ASK_DELIVERY_ADDRESS: { kind: "server", render: renderAskDeliveryAddress },
  CONFIRM_SLOT_CONFLICT: { kind: "server", render: renderConfirmSlotConflict },

  POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF: {
    kind: "llm_owned",
    rationale:
      "Post-order intent is context-dependent (track / cancel / re-order / handoff). A generic renderer would be a downgrade; the POST_ORDER_ONLY_* forbidden shapes enforce the boundary.",
  },
  // Phase 3 (2026-04-20): server-composed summary. The caller must also
  // gate on `!isExplicitOrderConfirmation(customerText)` so the
  // confirmation turn (customer said "yes") still reaches the LLM, which
  // owns the create_simple_order tool call and the order-confirmation
  // reply. See index.ts Region-A wiring.
  WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED: {
    kind: "server",
    render: renderFullOrderSummary,
  },
} as const satisfies Record<DirectiveAction, DirectiveReplyRendererSpec>;

// ---------------------------------------------------------------------------
// Public dispatcher.
// ---------------------------------------------------------------------------

export function renderDirectiveReply(
  action: string,
  ctx: DirectiveReplyRendererContext,
): DirectiveReplyRenderResult {
  if (!isRegisteredDirectiveAction(action)) {
    return { kind: "unknown_action", action };
  }
  const spec = DIRECTIVE_REPLY_RENDERERS[action];
  switch (spec.kind) {
    case "server":
      return { kind: "render", text: spec.render(ctx) };
    case "llm_owned":
      return { kind: "llm_owned", rationale: spec.rationale };
    default: {
      // Exhaustiveness sanity — the `satisfies` check guarantees this
      // branch is unreachable at compile time.
      const _exhaustive: never = spec;
      void _exhaustive;
      return { kind: "unknown_action", action };
    }
  }
}

export function isRegisteredDirectiveAction(
  action: string,
): action is DirectiveAction {
  return Object.prototype.hasOwnProperty.call(
    DIRECTIVE_REPLY_RENDERERS,
    action,
  );
}

/**
 * Convenience: returns true when the registry expects THIS module to
 * produce the reply text (the `"server"` kind). Existing substitutions
 * and LLM-owned directives return false — the outbound-decision caller
 * skips the registry-backed substitute in those cases.
 */
export function directiveHasServerRenderer(action: string): boolean {
  if (!isRegisteredDirectiveAction(action)) return false;
  return DIRECTIVE_REPLY_RENDERERS[action].kind === "server";
}
