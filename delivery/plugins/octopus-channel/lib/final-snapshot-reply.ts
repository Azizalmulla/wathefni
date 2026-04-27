import type { BookingTruthSnapshot } from "../../shared/booking-truth-snapshot";
import {
  checkPostDrainReplyCoherence,
  type ReplyCoherenceInvalidation,
  type ReplyCoherenceResult,
} from "./post-drain-reply-coherence";
import {
  compactSnapshotForReauthor,
  minimalSafePostDrainFallback,
} from "./post-drain-reply-reauthor";
import { buildDeterministicOrderSummaryFromSnapshot } from "../../shared/outbound-verify";

export type FinalSnapshotReplyMessages = {
  system: string;
  user: string;
};

export type GenerateFinalSnapshotReply = (
  messages: FinalSnapshotReplyMessages,
) => Promise<string | null>;

export type FinalReplyContract = {
  nextAction: BookingTruthSnapshot["nextAction"]["type"];
  lifecycleState: BookingTruthSnapshot["lifecycleState"];
  required: string[];
  forbidden: string[];
  summaryHash: {
    current: string | null;
    lastRendered: string | null;
    matchesLastRendered: boolean;
    requiredForConfirmation: boolean;
  };
};

export type FinalSnapshotReplyOutcome =
  | {
      status: "generated";
      replyText: string;
      coherence: ReplyCoherenceResult;
      markedSummaryShown: boolean;
      attempts: number;
    }
  | {
      status: "server_transaction_result";
      replyText: string;
      coherence: ReplyCoherenceResult;
      markedSummaryShown: boolean;
      attempts: 0;
      reason: "show_order_result" | "submit_order_without_artifact" | "transaction_failure";
    }
  | {
      status: "fallback";
      replyText: string;
      coherence: ReplyCoherenceResult | null;
      markedSummaryShown: boolean;
      attempts: number;
      reason: "generation_empty" | "generation_error" | "validation_failed";
    };

function compactInvalidations(invalidations: ReplyCoherenceInvalidation[]) {
  return invalidations.map((item) => ({
    kind: item.kind,
    field: item.field,
    matchedText: item.matchedText,
  }));
}

export function compactSnapshotForFinalReply(snapshot: BookingTruthSnapshot) {
  return compactSnapshotForReauthor(snapshot);
}

export function buildFinalReplyContract(
  snapshot: BookingTruthSnapshot,
): FinalReplyContract {
  const action = snapshot.nextAction;
  const base = {
    nextAction: action.type,
    lifecycleState: snapshot.lifecycleState,
    summaryHash: {
      current: snapshot.summary.currentHash,
      lastRendered: snapshot.summary.lastRenderedHash,
      matchesLastRendered: snapshot.summary.hashMatchesLastRendered,
      requiredForConfirmation: snapshot.summary.hashRequiredForConfirmation,
    },
  };
  switch (action.type) {
    case "show_summary":
      return {
        ...base,
        required: [
          "full operational summary",
          "service",
          "price",
          "pickup area",
          "pickup address",
          "sender name",
          "sender phone",
          "delivery area",
          "delivery address",
          "recipient name",
          "recipient phone",
          "confirmation ask",
        ],
        forbidden: ["missing-field ask", "route ambiguity ask", "order creation claim"],
      };
    case "wait_for_confirmation":
      return {
        ...base,
        required: ["ask for confirmation only"],
        forbidden: ["full summary repeat", "missing-field ask", "route ambiguity ask", "order creation claim"],
      };
    case "show_quote":
      return {
        ...base,
        required: ["show the current route quote", "include available service options and prices"],
        forbidden: ["missing-field ask", "summary", "confirmation ask", "order creation claim"],
      };
    case "ask_edit_target":
      return {
        ...base,
        required: ["ask what the customer wants to change"],
        forbidden: ["confirmation ask", "full summary repeat", "order creation claim"],
      };
    case "answer_question_then_wait_for_confirmation":
      return {
        ...base,
        required: ["answer the customer's question", "lightly mention confirmation can continue after the answer"],
        forbidden: ["full summary repeat", "missing-field ask", "route ambiguity ask", "order creation claim"],
      };
    case "pause_confirmation":
      return {
        ...base,
        required: ["acknowledge pause or hesitation", "do not push for immediate confirmation"],
        forbidden: ["order creation claim", "hard confirmation push", "full summary repeat"],
      };
    case "cancel_or_confirm_cancel":
      return {
        ...base,
        required: ["ask whether to cancel the draft booking"],
        forbidden: ["order creation claim", "continue confirmation ask", "full summary repeat"],
      };
    case "ask_clarification_about_confirmation":
      return {
        ...base,
        required: ["ask a short clarification about whether to confirm, edit, pause, or cancel"],
        forbidden: ["order creation claim", "full summary repeat"],
      };
    case "submit_order":
      return {
        ...base,
        required: ["transaction-safe order submission result only"],
        forbidden: ["summary", "confirmation ask", "missing-field ask", "route ambiguity ask"],
      };
    case "resolve_route_ambiguity":
      return {
        ...base,
        required: [`ask customer to choose ${action.field}`, "show only route options"],
        forbidden: ["quote", "summary", "unrelated missing-field ask", "order creation claim"],
      };
    case "collect_missing_field":
      return {
        ...base,
        required: [`ask only for ${action.field}`],
        forbidden: ["route ambiguity ask", "summary", "confirmation ask", "order creation claim"],
      };
    case "reprice_route":
      return {
        ...base,
        required: ["state that route needs a fresh price before continuing"],
        forbidden: ["old price", "summary", "confirmation ask", "order creation claim"],
      };
    case "resolve_coverage_ambiguity":
      return {
        ...base,
        required: ["resolve coverage ambiguity"],
        forbidden: ["quote", "summary", "confirmation ask", "order creation claim"],
      };
    case "resolve_slot_conflict":
      return {
        ...base,
        required: [`ask which ${action.field || "field"} value to keep`],
        forbidden: ["summary", "confirmation ask", "order creation claim"],
      };
    case "resolve_pending_edit":
      return {
        ...base,
        required: [`ask only for pending edit fields: ${action.fields.join(", ")}`],
        forbidden: ["unrelated missing-field ask", "summary", "confirmation ask", "order creation claim"],
      };
    case "show_order_result":
      return {
        ...base,
        required: ["show confirmed order result from transaction artifact"],
        forbidden: ["new summary", "confirmation ask", "missing-field ask"],
      };
    case "handoff_or_transaction_failure":
      return {
        ...base,
        required: ["transaction-safe failure or handoff message"],
        forbidden: ["order creation claim", "summary", "confirmation ask"],
      };
    case "answer_customer_question":
    case "none_idle":
      return {
        ...base,
        required: ["answer naturally without changing booking state"],
        forbidden: ["invented booking facts", "order creation claim"],
      };
  }
}

function transactionSafeSubmitFailure(language: "ar" | "en", cause?: string | null): string {
  const suffix = cause ? ` Logged cause: ${cause}.` : "";
  return language === "ar"
    ? `آسف، ما أقدر أأكد إنشاء الطلب من غير نتيجة آمنة من النظام. السبب المسجل: ${cause || "transaction_result_missing"}. بحوله للدعم يتأكدون من الطلب.`
    : `Sorry, I can't safely confirm that the order was created without a system result. I'll pass it to support to verify the booking.${suffix}`;
}

function transactionSafeOrderSubmittedFallback(language: "ar" | "en"): string {
  return language === "ar"
    ? "تم إنشاء الطلب، لحظة أجهز لك تفاصيل الطلب ورابط الدفع."
    : "Your order has been created. Give me a moment to prepare the order details and payment link.";
}

function serverOwnedTransactionReply(params: {
  snapshot: BookingTruthSnapshot;
  language: "ar" | "en";
  canonicalTransactionText?: string | null;
}): FinalSnapshotReplyOutcome | null {
  const action = params.snapshot.nextAction;
  if (action.type === "show_order_result") {
    const text =
      String(params.canonicalTransactionText || "").trim() ||
      transactionSafeOrderSubmittedFallback(params.language);
    return {
      status: "server_transaction_result",
      replyText: text,
      coherence: { coherent: true, invalidations: [] },
      markedSummaryShown: false,
      attempts: 0,
      reason: "show_order_result",
    };
  }
  if (action.type === "submit_order") {
    return {
      status: "server_transaction_result",
      replyText: transactionSafeSubmitFailure(
        params.language,
        "submit_order_without_transaction_artifact",
      ),
      coherence: { coherent: true, invalidations: [] },
      markedSummaryShown: false,
      attempts: 0,
      reason: "submit_order_without_artifact",
    };
  }
  if (action.type === "handoff_or_transaction_failure") {
    return {
      status: "server_transaction_result",
      replyText: transactionSafeSubmitFailure(params.language, action.reason),
      coherence: { coherent: true, invalidations: [] },
      markedSummaryShown: false,
      attempts: 0,
      reason: "transaction_failure",
    };
  }
  return null;
}

function customerFieldLabel(field: string, language: "ar" | "en"): string {
  const labels: Record<string, { en: string; ar: string }> = {
    "sender.name": { en: "sender name", ar: "اسم المرسل" },
    "sender.phone": { en: "sender phone number", ar: "رقم المرسل" },
    "recipient.name": { en: "recipient name", ar: "اسم المستلم" },
    "recipient.phone": { en: "recipient phone number", ar: "رقم المستلم" },
    "pickup.address": { en: "pickup address", ar: "عنوان الاستلام" },
    "pickup.block": { en: "pickup block", ar: "قطعة الاستلام" },
    "pickup.street_or_avenue": { en: "pickup street or avenue", ar: "شارع أو جادة الاستلام" },
    "pickup.house_or_unit": { en: "pickup house/building", ar: "منزل أو بناية الاستلام" },
    "delivery.address": { en: "delivery address", ar: "عنوان التوصيل" },
    "delivery.block": { en: "delivery block", ar: "قطعة التوصيل" },
    "delivery.street_or_avenue": { en: "delivery street or avenue", ar: "شارع أو جادة التوصيل" },
    "delivery.house_or_unit": { en: "delivery house/building", ar: "منزل أو بناية التوصيل" },
    service_type: { en: "delivery service option", ar: "خيار خدمة التوصيل" },
    quoted_price: { en: "quoted price", ar: "السعر" },
    "pickup.area": { en: "pickup area", ar: "منطقة الاستلام" },
    "delivery.area": { en: "delivery area", ar: "منطقة التوصيل" },
  };
  const label = labels[field];
  return label ? label[language] : field.replace(/[._]/g, " ");
}

function routeOptionLabels(snapshot: BookingTruthSnapshot): string {
  const options = snapshot.pendingRouteAmbiguity?.options || [];
  return options
    .map((option) => option.nameEn || option.nameAr)
    .filter(Boolean)
    .join(" / ");
}

function renderQuoteFromSnapshot(snapshot: BookingTruthSnapshot, language: "ar" | "en"): string {
  const pickup = snapshot.route.pickup.nameEn || snapshot.route.pickup.nameAr || "pickup";
  const dropoff = snapshot.route.dropoff.nameEn || snapshot.route.dropoff.nameAr || "delivery";
  const options = (snapshot.quote.optionCatalog || [])
    .filter((option) => option.quoted_price != null)
    .slice(0, 6)
    .map((option) => {
      const label =
        language === "ar"
          ? option.label_ar || option.label_en || option.delivery_type
          : option.label_en || option.label_ar || option.delivery_type;
      const price =
        option.formatted_price ||
        `${Number(option.quoted_price).toFixed(3)} KWD`;
      return `- ${label}: ${price}`;
    });
  if (language === "ar") {
    return [
      `سعر التوصيل من ${pickup} إلى ${dropoff}:`,
      ...options,
      "إذا يناسبكم السعر، أرسلوا التفاصيل اللي تحبون نكمل عليها.",
    ].join("\n");
  }
  return [
    `Delivery quote from ${pickup} to ${dropoff}:`,
    ...options,
    "If one of these works, send the details you want to continue with.",
  ].join("\n");
}

export function renderFinalReplyContractFallback(params: {
  snapshot: BookingTruthSnapshot;
  language: "ar" | "en";
  canonicalTransactionText?: string | null;
}): string {
  const { snapshot, language } = params;
  const action = snapshot.nextAction;
  if (action.type === "show_summary") {
    return buildDeterministicOrderSummaryFromSnapshot({ snapshot, language });
  }
  if (action.type === "wait_for_confirmation") {
    return language === "ar"
      ? "هل تأكد الطلب بهذه التفاصيل؟"
      : "Please confirm if I should place the order with those details.";
  }
  if (action.type === "show_quote") {
    return renderQuoteFromSnapshot(snapshot, language);
  }
  if (action.type === "ask_edit_target") {
    return language === "ar"
      ? "أكيد، شنو التعديل اللي تبونه؟"
      : "Sure, what would you like to change?";
  }
  if (action.type === "answer_question_then_wait_for_confirmation") {
    return language === "ar"
      ? "أكيد، شنو حابين تعرفون قبل ما نكمل؟"
      : "Sure, what would you like to know before we continue?";
  }
  if (action.type === "pause_confirmation") {
    return language === "ar"
      ? "أكيد، خذوا وقتكم. أنا بانتظاركم."
      : "Sure, take your time. I’ll wait for you.";
  }
  if (action.type === "cancel_or_confirm_cancel") {
    return language === "ar"
      ? "تبون ألغي مسودة الطلب؟"
      : "Would you like me to cancel this draft booking?";
  }
  if (action.type === "ask_clarification_about_confirmation") {
    return language === "ar"
      ? "تبون تأكدون الطلب، تعدلون شي، توقفون شوي، أو تلغونه؟"
      : "Would you like to confirm, change something, pause, or cancel?";
  }
  if (action.type === "submit_order") {
    return transactionSafeSubmitFailure(language, "submit_order_not_executed");
  }
  if (action.type === "show_order_result") {
    return (
      String(params.canonicalTransactionText || "").trim() ||
      transactionSafeOrderSubmittedFallback(language)
    );
  }
  if (action.type === "resolve_route_ambiguity") {
    const field = customerFieldLabel(
      action.field === "pickup_area" ? "pickup.area" : "delivery.area",
      language,
    );
    const options = routeOptionLabels(snapshot);
    return language === "ar"
      ? `أي ${field} تقصد؟${options ? ` الخيارات: ${options}` : ""}`
      : `Which ${field} do you mean?${options ? ` Options: ${options}` : ""}`;
  }
  if (action.type === "collect_missing_field") {
    const field = customerFieldLabel(action.field, language);
    return language === "ar"
      ? `أرسلوا ${field} فقط.`
      : `Please send the ${field}.`;
  }
  if (action.type === "reprice_route") {
    return language === "ar"
      ? "أحتاج أراجع سعر المسار من جديد قبل ما أكمل."
      : "I need to check a fresh price for this route before continuing.";
  }
  if (action.type === "resolve_coverage_ambiguity") {
    return language === "ar"
      ? "أحتاج أتأكد من تغطية المنطقة قبل ما أكمل."
      : "I need to confirm coverage for this area before continuing.";
  }
  if (action.type === "resolve_slot_conflict") {
    const field = customerFieldLabel(String(action.field || "field"), language);
    return language === "ar"
      ? `أي قيمة نعتمد لـ ${field}؟`
      : `Which value should I keep for ${field}?`;
  }
  if (action.type === "resolve_pending_edit") {
    const fields = action.fields.map((field) => customerFieldLabel(String(field), language)).join(", ");
    return language === "ar"
      ? `أرسلوا التعديل المطلوب فقط: ${fields}.`
      : `Please send only the pending edit values: ${fields}.`;
  }
  if (action.type === "handoff_or_transaction_failure") {
    return transactionSafeSubmitFailure(language, action.reason);
  }
  return language === "ar"
    ? "شلون أقدر أساعدكم؟"
    : "How can I help?";
}

export function buildFinalSnapshotReplyMessages(params: {
  originalCustomerMessage: string | null | undefined;
  appliedOpsSummary: string[];
  rejectedOpsSummary?: string[];
  bookingTruthSnapshot: BookingTruthSnapshot;
  preferredLanguage: "ar" | "en";
  priorReplyText?: string | null;
  invalidations?: ReplyCoherenceInvalidation[];
  retry?: boolean;
}): FinalSnapshotReplyMessages {
  const system = [
    "You write the final WhatsApp reply for Riders after the server has committed all tool results.",
    "Use only the post-drain snapshot and applied ops in the user payload.",
    "Do not call tools. Do not invent route facts, prices, order status, payment links, missing fields, or saved values.",
    "bookingTruthSnapshot.nextAction is the single final booking next step. Word that action naturally.",
    "finalReplyContract is binding. Satisfy its required items and avoid every forbidden item.",
    "Server truth beats conversational memory and any prior reply draft.",
    "If nextAction.type is show_summary, write a full order summary from savedDraft, route, selected service, and selected price. Copy customer-provided names and address values exactly; localize labels only.",
    "If the saved address says apartment, floor, or door, keep those words and values; never rewrite them as house/building.",
    "If nextAction.type is collect_missing_field, ask only for nextAction.field.",
    "If nextAction.type is resolve_route_ambiguity, ask the customer to choose from route.pendingRouteAmbiguity.options.",
    "If nextAction.type is resolve_slot_conflict, ask which conflicting value to keep.",
    "If nextAction.type is resolve_pending_edit, ask for only the pending edit fields.",
    "If nextAction.type is show_quote, show the route quote/options first. Do not ask for sender, recipient, address, summary confirmation, or order confirmation in the same reply.",
    "If nextAction.type is ask_edit_target, ask what the customer wants to change. Do not ask for confirmation.",
    "If nextAction.type is answer_question_then_wait_for_confirmation, answer the customer's question from the available context, then lightly indicate they can confirm afterward.",
    "If nextAction.type is pause_confirmation, acknowledge the pause and wait. Do not pressure the customer to confirm.",
    "If nextAction.type is cancel_or_confirm_cancel, ask whether they want to cancel the draft booking.",
    "If nextAction.type is ask_clarification_about_confirmation, ask a short clarification about confirming, editing, pausing, or canceling.",
    "If nextAction.type is wait_for_confirmation, ask for confirmation only. Do not repeat the full summary.",
    "If nextAction.type is submit_order, do not claim the order was created. The server owns order submission and transaction artifacts.",
    "Never ask for any field that is not listed in missingFields.",
    "If addressSatisfaction for a side is true, do not ask for address details for that side.",
    "If route.lockStatus is locked, do not reopen route ambiguity.",
    "Use the preferred language unless the customer's values are in another language; do not translate names or raw address values.",
    "Keep the reply concise, natural, and customer-facing. Return only the reply text.",
  ].join("\n");

  const user = JSON.stringify(
    {
      task: params.retry
        ? "Rewrite the final reply. The previous attempt contradicted post-drain truth."
        : "Write the final customer reply from the post-drain snapshot.",
      preferredLanguage: params.preferredLanguage,
      originalCustomerMessage: params.originalCustomerMessage || "",
      appliedOpsSummary: params.appliedOpsSummary,
      rejectedOpsSummary: params.rejectedOpsSummary || [],
      priorReplyText: params.priorReplyText || null,
      invalidations: compactInvalidations(params.invalidations || []),
      finalReplyContract: buildFinalReplyContract(params.bookingTruthSnapshot),
      bookingTruthSnapshot: compactSnapshotForFinalReply(params.bookingTruthSnapshot),
    },
    null,
    2,
  );
  return { system, user };
}

export async function generateFinalSnapshotReply(params: {
  originalCustomerMessage: string | null | undefined;
  appliedOpsSummary: string[];
  rejectedOpsSummary?: string[];
  bookingTruthSnapshot: BookingTruthSnapshot;
  preferredLanguage: "ar" | "en";
  canonicalTransactionText?: string | null;
  generateReply: GenerateFinalSnapshotReply;
}): Promise<FinalSnapshotReplyOutcome> {
  const serverTransaction = serverOwnedTransactionReply({
    snapshot: params.bookingTruthSnapshot,
    language: params.preferredLanguage,
    canonicalTransactionText: params.canonicalTransactionText,
  });
  if (serverTransaction) return serverTransaction;

  const markedSummaryShown =
    params.bookingTruthSnapshot.nextAction.type === "show_summary";
  let messages = buildFinalSnapshotReplyMessages({
    originalCustomerMessage: params.originalCustomerMessage,
    appliedOpsSummary: params.appliedOpsSummary,
    rejectedOpsSummary: params.rejectedOpsSummary,
    bookingTruthSnapshot: params.bookingTruthSnapshot,
    preferredLanguage: params.preferredLanguage,
  });

  for (let attempt = 1; attempt <= 2; attempt += 1) {
    let candidate: string | null = null;
    try {
      candidate = await params.generateReply(messages);
    } catch {
      return {
        status: "fallback",
        replyText: minimalSafePostDrainFallback(params.preferredLanguage),
        coherence: null,
        markedSummaryShown: false,
        attempts: attempt,
        reason: "generation_error",
      };
    }

    const replyText = String(candidate || "").trim();
    if (!replyText) {
      return {
        status: "fallback",
        replyText: minimalSafePostDrainFallback(params.preferredLanguage),
        coherence: null,
        markedSummaryShown: false,
        attempts: attempt,
        reason: "generation_empty",
      };
    }

    const coherence = checkPostDrainReplyCoherence({
      replyText,
      bookingTruthSnapshot: params.bookingTruthSnapshot,
    });
    if (coherence.coherent) {
      return {
        status: "generated",
        replyText,
        coherence,
        markedSummaryShown,
        attempts: attempt,
      };
    }

    messages = buildFinalSnapshotReplyMessages({
      originalCustomerMessage: params.originalCustomerMessage,
      appliedOpsSummary: params.appliedOpsSummary,
      rejectedOpsSummary: params.rejectedOpsSummary,
      bookingTruthSnapshot: params.bookingTruthSnapshot,
      preferredLanguage: params.preferredLanguage,
      priorReplyText: replyText,
      invalidations: coherence.invalidations,
      retry: true,
    });
  }

  const fallbackText = renderFinalReplyContractFallback({
    snapshot: params.bookingTruthSnapshot,
    language: params.preferredLanguage,
    canonicalTransactionText: params.canonicalTransactionText,
  });
  const coherence = checkPostDrainReplyCoherence({
    replyText: fallbackText,
    bookingTruthSnapshot: params.bookingTruthSnapshot,
  });
  return {
    status: "fallback",
    replyText: fallbackText,
    coherence,
    markedSummaryShown: params.bookingTruthSnapshot.nextAction.type === "show_summary",
    attempts: 2,
    reason: "validation_failed",
  };
}
