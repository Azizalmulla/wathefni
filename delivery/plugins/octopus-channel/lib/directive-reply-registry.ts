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
//   - `{ kind: "server_existing", via: "…" }`     — server-composed, but the
//                                                   substitution lives
//                                                   elsewhere (the dedicated
//                                                   Region-A branches for
//                                                   manual-confirm /
//                                                   clarify-before-proceed).
//                                                   Listed here so the
//                                                   exhaustiveness check
//                                                   covers them.
//   - `{ kind: "llm_owned", rationale: "…" }`     — intentionally left to
//                                                   the LLM (e.g. post-order
//                                                   intent routing; summary
//                                                   text is a Phase 3 target).
//
// The dispatcher `renderDirectiveReply` returns a discriminated result
// that lets the outbound-decision module decide what to do:
//
//   - `{ kind: "render"; text }`   → substitute with `text`
//   - `{ kind: "existing"; via }`  → skip; another Region-A branch owns it
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
} from "../../shared/conversation-policy";
import type { StoredQuotedRoute } from "./quoted-options";
import {
  getEffectivePickupAreaName,
  getEffectiveDeliveryAreaName,
} from "../../shared/conversation-policy";

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
  | "ASK_SENDER_PHONE"
  | "ASK_RECIPIENT_NAME_AND_PHONE"
  | "ASK_PICKUP_ADDRESS"
  | "ASK_DELIVERY_ADDRESS"
  | "CONFIRM_SLOT_CONFLICT"
  // Defensive fallback — should not fire given the current
  // `collectionMissing` filter, but the compile-time exhaustiveness
  // tripwire forces us to carry a renderer.
  | "COLLECT_NEXT_MISSING_FIELD"
  // Manual-confirm flow — server-composed, substitution lives in
  // dedicated Region-A branches (Bug 4, 2026-04-20).
  | "ASK_PICKUP_ADDRESS_FOR_MANUAL_CONFIRM"
  | "ASK_DELIVERY_ADDRESS_FOR_MANUAL_CONFIRM"
  | "REQUEST_HANDOFF_FOR_MANUAL_CONFIRM"
  // Option-disambiguation clarify — server-composed, substitution lives
  // in a dedicated Region-A branch (Bug 1, 2026-04-20).
  | "CLARIFY_OPTION_BEFORE_PROCEED"
  // LLM-owned: the customer's post-order intent is context-dependent
  // (track vs cancel vs re-order vs handoff); a generic renderer would
  // be a downgrade. Guarded by `POST_ORDER_ONLY_*` forbidden shapes.
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
  route: StoredQuotedRoute | null;
  /** Slot name for CONFIRM_SLOT_CONFLICT. Null for other directives. */
  conflictingSlot?: string | null;
  /** For CONFIRM_SLOT_CONFLICT — the two conflicting values to surface. */
  conflictValues?: { incoming: string; existing: string } | null;
  /**
   * Stable identifier for variability seed. Reuse the drain turn id;
   * same turn → same phrasing, different turn → likely different.
   */
  turnSeed: string;
};

export type DirectiveReplyRenderer = (
  ctx: DirectiveReplyRendererContext,
) => string;

type DirectiveReplyRendererSpec =
  | { kind: "server"; render: DirectiveReplyRenderer }
  | {
      kind: "server_existing";
      via:
        | "clarify_option_before_proceed"
        | "manual_confirm_pickup_ask"
        | "manual_confirm_delivery_ask"
        | "manual_confirm_handoff";
    }
  | { kind: "llm_owned"; rationale: string };

// ---------------------------------------------------------------------------
// Dispatcher return shape.
// ---------------------------------------------------------------------------

export type DirectiveReplyRenderResult =
  | { kind: "render"; text: string }
  | {
      kind: "existing";
      via:
        | "clarify_option_before_proceed"
        | "manual_confirm_pickup_ask"
        | "manual_confirm_delivery_ask"
        | "manual_confirm_handoff";
    }
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
  if (ctx.language === "ar") {
    return pick(ctx.turnSeed, [
      "قبل ما نقدر نسعر، عطنا منطقة الاستلام ومنطقة التوصيل.",
      "شنو منطقة الاستلام وشنو منطقة التوصيل؟ من دونهم ما نقدر نطلع سعر.",
      "عشان نسعر بدقّة، أرسل لنا منطقة الاستلام ومنطقة التوصيل.",
    ]);
  }
  return pick(ctx.turnSeed, [
    "Before I can price this, what's the pickup area and what's the delivery area?",
    "Could you share the pickup area and the delivery area? I need both to give you a price.",
    "To price this properly, please send the pickup area and the delivery area.",
  ]);
}

function renderAskPickupArea(ctx: DirectiveReplyRendererContext): string {
  if (ctx.language === "ar") {
    return pick(ctx.turnSeed, [
      "شنو منطقة الاستلام بالضبط؟",
      "عطنا منطقة الاستلام (مثل: السالمية، الجابرية، حولي).",
      "من أي منطقة نستلم؟",
    ]);
  }
  return pick(ctx.turnSeed, [
    "What's the pickup area?",
    "Could you share the pickup area (e.g. Salmiya, Jabriya, Hawalli)?",
    "Which area is the pickup from?",
  ]);
}

function renderAskDeliveryArea(ctx: DirectiveReplyRendererContext): string {
  if (ctx.language === "ar") {
    return pick(ctx.turnSeed, [
      "شنو منطقة التوصيل بالضبط؟",
      "عطنا منطقة التوصيل (مثل: السالمية، الجابرية، حولي).",
      "إلى أي منطقة نوصل؟",
    ]);
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
    return "ممكن ترسل البيانات الناقصة عشان نكمل؟";
  }
  return "Could you send the remaining booking details so we can continue?";
}

function renderAskSenderNameAndPhoneDecision(
  ctx: DirectiveReplyRendererContext,
): string {
  if (ctx.language === "ar") {
    return pick(ctx.turnSeed, [
      "تمام. شنو الاسم الكامل للمرسل، وهل تبون نستخدم هالرقم (رقم واتساب الحالي) أو رقم ثاني؟",
      "تمام. عطنا اسم المرسل الكامل، وهل نخلي الرقم هالرقم أو رقم ثاني؟",
      "تمام. شنو اسم المرسل الكامل، ونستخدم رقمك الحالي لو عندك رقم غيره؟",
    ]);
  }
  return pick(ctx.turnSeed, [
    "Got it. What's the sender's full name, and should we use this number (your WhatsApp) or a different one?",
    "Great. Sender's full name please, and is this WhatsApp number the sender's contact or a different one?",
    "Noted. Could I get the sender's full name, and confirm whether to use this number or another?",
  ]);
}

function renderAskSenderPhone(ctx: DirectiveReplyRendererContext): string {
  const senderName = (ctx.draft.senderName || "").trim();
  if (ctx.language === "ar") {
    const base = senderName
      ? `تمام ${senderName}. شنو رقم المرسل؟`
      : "شنو رقم المرسل؟";
    return pick(ctx.turnSeed, [
      base,
      senderName
        ? `سجّلنا الاسم ${senderName}. عطنا رقم تواصل المرسل من فضلك.`
        : "عطنا رقم تواصل المرسل من فضلك.",
    ]);
  }
  const base = senderName
    ? `Thanks ${senderName}. What's the sender's phone number?`
    : "What's the sender's phone number?";
  return pick(ctx.turnSeed, [
    base,
    senderName
      ? `Got the name (${senderName}). Could you share the sender's phone number?`
      : "Could you share the sender's phone number?",
  ]);
}

function renderAskRecipientNameAndPhone(
  ctx: DirectiveReplyRendererContext,
): string {
  if (ctx.language === "ar") {
    return pick(ctx.turnSeed, [
      "ممتاز. الحين عطنا اسم المستلم الكامل ورقمه.",
      "تمام. شنو اسم المستلم الكامل ورقم تواصله؟",
      "زين. عطنا بيانات المستلم: الاسم الكامل والرقم.",
    ]);
  }
  return pick(ctx.turnSeed, [
    "Thanks. Now could you share the recipient's full name and phone number?",
    "Got it. What's the recipient's full name and phone number?",
    "Noted. Please send the recipient's full name and contact number.",
  ]);
}

function renderAskPickupAddress(ctx: DirectiveReplyRendererContext): string {
  const areaName =
    ctx.language === "ar"
      ? (ctx.entry.quotePickupAreaNameAr ||
          ctx.entry.pendingPickupAreaNameAr ||
          getEffectivePickupAreaName(ctx.draft, ctx.entry) ||
          null)
      : getEffectivePickupAreaName(ctx.draft, ctx.entry);
  if (ctx.language === "ar") {
    const suffix = areaName ? ` في ${areaName}` : "";
    return pick(ctx.turnSeed, [
      `ممكن ترسل عنوان الاستلام${suffix} (القطعة، الشارع، والمبنى/الشقة)؟`,
      `عطنا عنوان الاستلام${suffix}: قطعة، شارع، ومبنى أو شقة.`,
      `شنو عنوان الاستلام${suffix} بالتفصيل — قطعة، شارع، ومبنى/شقة؟`,
    ]);
  }
  const suffix = areaName ? ` in ${areaName}` : "";
  return pick(ctx.turnSeed, [
    `Could you share the pickup address${suffix} — block, street, and building/apartment?`,
    `What's the pickup address${suffix}? Please include block, street, and building or apartment.`,
    `Please send the pickup address${suffix}: block, street, and the building/apartment detail.`,
  ]);
}

function renderAskDeliveryAddress(ctx: DirectiveReplyRendererContext): string {
  const areaName =
    ctx.language === "ar"
      ? (ctx.entry.quoteDropoffAreaNameAr ||
          ctx.entry.pendingDropoffAreaNameAr ||
          getEffectiveDeliveryAreaName(ctx.draft, ctx.entry) ||
          null)
      : getEffectiveDeliveryAreaName(ctx.draft, ctx.entry);
  if (ctx.language === "ar") {
    const suffix = areaName ? ` في ${areaName}` : "";
    return pick(ctx.turnSeed, [
      `ممكن ترسل عنوان التوصيل${suffix} (القطعة، الشارع، والمبنى/الشقة)؟`,
      `عطنا عنوان التوصيل${suffix}: قطعة، شارع، ومبنى أو شقة.`,
      `شنو عنوان التوصيل${suffix} بالتفصيل — قطعة، شارع، ومبنى/شقة؟`,
    ]);
  }
  const suffix = areaName ? ` in ${areaName}` : "";
  return pick(ctx.turnSeed, [
    `Could you share the delivery address${suffix} — block, street, and building/apartment?`,
    `What's the delivery address${suffix}? Please include block, street, and building or apartment.`,
    `Please send the delivery address${suffix}: block, street, and the building/apartment detail.`,
  ]);
}

function renderConfirmSlotConflict(ctx: DirectiveReplyRendererContext): string {
  const slot = ctx.conflictingSlot || "that field";
  const prettySlot = slot
    .replace(/_/g, " ")
    .replace(/\b(pickup|delivery)\b/gi, (m) => m.toLowerCase());
  const incoming = ctx.conflictValues?.incoming || null;
  const existing = ctx.conflictValues?.existing || null;
  const both = incoming && existing;
  if (ctx.language === "ar") {
    if (both) {
      return pick(ctx.turnSeed, [
        `قبل ما نكمل، أي قيمة بالضبط تبون نحفظها لـ ${prettySlot}: "${existing}" أو "${incoming}"؟`,
        `أيها الصحيح للـ ${prettySlot}: "${existing}" ولا "${incoming}"؟`,
      ]);
    }
    return pick(ctx.turnSeed, [
      `عندنا قيمتين مختلفتين للـ ${prettySlot}. ممكن تأكد لنا القيمة الصحيحة قبل نكمل؟`,
      `نبي نتأكد من القيمة الصحيحة للـ ${prettySlot} قبل نكمل.`,
    ]);
  }
  if (both) {
    return pick(ctx.turnSeed, [
      `Before we continue, which value should I keep for ${prettySlot}: "${existing}" or "${incoming}"?`,
      `Quick check on ${prettySlot} — is the correct value "${existing}" or "${incoming}"?`,
    ]);
  }
  return pick(ctx.turnSeed, [
    `I have two different values for ${prettySlot}. Could you confirm the correct one before we continue?`,
    `Quick check — which value should I keep for ${prettySlot}?`,
  ]);
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
  ASK_SENDER_PHONE: { kind: "server", render: renderAskSenderPhone },
  ASK_RECIPIENT_NAME_AND_PHONE: {
    kind: "server",
    render: renderAskRecipientNameAndPhone,
  },
  ASK_PICKUP_ADDRESS: { kind: "server", render: renderAskPickupAddress },
  ASK_DELIVERY_ADDRESS: { kind: "server", render: renderAskDeliveryAddress },
  CONFIRM_SLOT_CONFLICT: { kind: "server", render: renderConfirmSlotConflict },

  ASK_PICKUP_ADDRESS_FOR_MANUAL_CONFIRM: {
    kind: "server_existing",
    via: "manual_confirm_pickup_ask",
  },
  ASK_DELIVERY_ADDRESS_FOR_MANUAL_CONFIRM: {
    kind: "server_existing",
    via: "manual_confirm_delivery_ask",
  },
  REQUEST_HANDOFF_FOR_MANUAL_CONFIRM: {
    kind: "server_existing",
    via: "manual_confirm_handoff",
  },
  CLARIFY_OPTION_BEFORE_PROCEED: {
    kind: "server_existing",
    via: "clarify_option_before_proceed",
  },

  POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF: {
    kind: "llm_owned",
    rationale:
      "Post-order intent is context-dependent (track / cancel / re-order / handoff). A generic renderer would be a downgrade; the POST_ORDER_ONLY_* forbidden shapes enforce the boundary.",
  },
  WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED: {
    kind: "llm_owned",
    rationale:
      "Summary rendering is the Phase 3 target. Today the C-drift fact verifier intercepts drift; Phase 3 will compose the summary deterministically from state.",
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
    case "server_existing":
      return { kind: "existing", via: spec.via };
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
