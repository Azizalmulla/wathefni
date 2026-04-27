import type { BookingTruthSnapshot } from "../../shared/booking-truth-snapshot";
import {
  checkPostDrainReplyCoherence,
  type ReplyCoherenceInvalidation,
  type ReplyCoherenceResult,
} from "./post-drain-reply-coherence";

export type PostDrainReauthorMessages = {
  system: string;
  user: string;
};

export type PostDrainReauthorOutcome =
  | {
      status: "not_needed";
      replyText: string;
      initialCoherence: ReplyCoherenceResult;
    }
  | {
      status: "reauthored";
      replyText: string;
      initialCoherence: ReplyCoherenceResult;
      retryCoherence: ReplyCoherenceResult;
    }
  | {
      status: "fallback";
      replyText: string;
      initialCoherence: ReplyCoherenceResult;
      retryCoherence: ReplyCoherenceResult | null;
      reason: "retry_empty" | "retry_conflicted" | "retry_error";
    };

export type GeneratePostDrainReauthorReply = (
  messages: PostDrainReauthorMessages,
) => Promise<string | null>;

function compactRouteSide(side: BookingTruthSnapshot["route"]["pickup"]) {
  return {
    status: side.status,
    areaId: side.areaId,
    nameEn: side.nameEn,
    nameAr: side.nameAr,
    ambiguityGroupId: side.ambiguityGroupId,
    options: side.options,
    sourceText: side.sourceText,
    confirmedByUser: side.confirmedByUser,
  };
}

export function compactSnapshotForReauthor(snapshot: BookingTruthSnapshot) {
  const draft = snapshot.draft;
  return {
    stage: snapshot.stage,
    bookingStep: snapshot.bookingStep,
    lifecycleState: snapshot.lifecycleState,
    nextAction: snapshot.nextAction,
    route: {
      lockStatus: snapshot.route.lockStatus,
      pickup: compactRouteSide(snapshot.route.pickup),
      dropoff: compactRouteSide(snapshot.route.dropoff),
      pendingRouteAmbiguity: snapshot.pendingRouteAmbiguity,
    },
    quote: {
      selectedService: snapshot.quote.selectedService,
      selected: snapshot.quote.selected,
      validQuotedPrices: snapshot.quote.validQuotedPrices,
      optionCatalog: snapshot.quote.optionCatalog,
    },
    missingFields: snapshot.missingFields,
    nextMissingField: snapshot.nextMissingField,
    addressSatisfaction: snapshot.addressSatisfaction,
    requestedSlot: snapshot.requestedSlot
      ? {
          name: snapshot.requestedSlot.name,
          options: snapshot.requestedSlot.options ?? null,
        }
      : null,
    pendingOrderEdits: snapshot.pendingOrderEdits,
    slotConflicts: snapshot.slotConflicts,
    currentTurnDisposition: snapshot.currentTurnDisposition,
    blockedStateActions: snapshot.blockedStateActions,
    summary: snapshot.summary,
    order: snapshot.order,
    savedDraft: draft
      ? {
          senderName: draft.senderName,
          senderPhone: draft.senderPhone,
          recipientName: draft.recipientName,
          recipientPhone: draft.recipientPhone,
          pickupBlock: draft.pickupBlock,
          pickupStreet: draft.pickupStreet,
          pickupAvenue: draft.pickupAvenue,
          pickupHouse: draft.pickupHouse,
          pickupExtra: draft.pickupExtra,
          deliveryBlock: draft.deliveryBlock,
          deliveryStreet: draft.deliveryStreet,
          deliveryAvenue: draft.deliveryAvenue,
          deliveryHouse: draft.deliveryHouse,
          deliveryExtra: draft.deliveryExtra,
        }
      : null,
  };
}

function compactInvalidations(invalidations: ReplyCoherenceInvalidation[]) {
  return invalidations.map((item) => ({
    kind: item.kind,
    field: item.field,
    matchedText: item.matchedText,
  }));
}

export function minimalSafePostDrainFallback(
  preferredLanguage?: "ar" | "en" | null,
): string {
  if (preferredLanguage === "ar") {
    return "آسف، أحتاج أتأكد من التفاصيل قبل ما أكمل.";
  }
  return "Sorry, I need to double-check the details before continuing.";
}

export function buildPostDrainReauthorMessages(params: {
  originalCustomerMessage: string | null | undefined;
  originalReplyText: string;
  appliedOpsSummary: string[];
  bookingTruthSnapshot: BookingTruthSnapshot;
  invalidations: ReplyCoherenceInvalidation[];
  preferredLanguage?: "ar" | "en" | null;
}): PostDrainReauthorMessages {
  const system = [
    "You write the final WhatsApp reply for Riders after server state has already been committed.",
    "Use only the fresh post-drain booking truth in the user payload.",
    "Do not call tools. Do not invent prices, route facts, order status, or missing fields.",
    "The postDrainSnapshot.nextAction is the single final booking next step. Word that action naturally.",
    "Use postDrainSnapshot.quote.selected as the selected service and selected price. Never mention a different service or price as the booked choice.",
    "If nextAction.type is collect_missing_field, ask only for nextAction.field.",
    "If nextAction.type is resolve_route_ambiguity, ask the customer to choose from route.pendingRouteAmbiguity.options.",
    "If nextAction.type is show_summary, write a concise summary using savedDraft, route, selected service, and selected price.",
    "If nextAction.type is submit_order or wait_for_confirmation, do not ask route clarification or missing-field questions.",
    "Do not ask for any field that is not listed in missingFields.",
    "If route.lockStatus is not locked, do not quote a price, summarize a booking, or proceed to booking details as if the route is locked.",
    "If addressSatisfaction for a side is true, do not ask for block, street, avenue, house, building, apartment, or address details for that side.",
    "Keep the reply short, natural, and customer-facing. Return only the reply text.",
  ].join("\n");
  const user = JSON.stringify(
    {
      task: "Regenerate the final reply because the first reply contradicted fresh post-drain truth.",
      preferredLanguage: params.preferredLanguage || "unknown",
      appliedOpsSummary: params.appliedOpsSummary,
      invalidations: compactInvalidations(params.invalidations),
      postDrainSnapshot: compactSnapshotForReauthor(params.bookingTruthSnapshot),
    },
    null,
    2,
  );
  return { system, user };
}

export async function reauthorPostDrainReply(params: {
  replyText: string;
  originalCustomerMessage: string | null | undefined;
  appliedOpsSummary: string[];
  bookingTruthSnapshot: BookingTruthSnapshot;
  preferredLanguage?: "ar" | "en" | null;
  generateReply: GeneratePostDrainReauthorReply;
}): Promise<PostDrainReauthorOutcome> {
  const initialCoherence = checkPostDrainReplyCoherence({
    replyText: params.replyText,
    bookingTruthSnapshot: params.bookingTruthSnapshot,
  });
  if (initialCoherence.coherent) {
    return {
      status: "not_needed",
      replyText: params.replyText,
      initialCoherence,
    };
  }

  const messages = buildPostDrainReauthorMessages({
    originalCustomerMessage: params.originalCustomerMessage,
    originalReplyText: params.replyText,
    appliedOpsSummary: params.appliedOpsSummary,
    bookingTruthSnapshot: params.bookingTruthSnapshot,
    invalidations: initialCoherence.invalidations,
    preferredLanguage: params.preferredLanguage,
  });

  let candidate: string | null = null;
  try {
    candidate = await params.generateReply(messages);
  } catch {
    return {
      status: "fallback",
      replyText: minimalSafePostDrainFallback(params.preferredLanguage),
      initialCoherence,
      retryCoherence: null,
      reason: "retry_error",
    };
  }

  const trimmed = String(candidate || "").trim();
  if (!trimmed) {
    return {
      status: "fallback",
      replyText: minimalSafePostDrainFallback(params.preferredLanguage),
      initialCoherence,
      retryCoherence: null,
      reason: "retry_empty",
    };
  }

  const retryCoherence = checkPostDrainReplyCoherence({
    replyText: trimmed,
    bookingTruthSnapshot: params.bookingTruthSnapshot,
  });
  if (!retryCoherence.coherent) {
    return {
      status: "fallback",
      replyText: minimalSafePostDrainFallback(params.preferredLanguage),
      initialCoherence,
      retryCoherence,
      reason: "retry_conflicted",
    };
  }

  return {
    status: "reauthored",
    replyText: trimmed,
    initialCoherence,
    retryCoherence,
  };
}
