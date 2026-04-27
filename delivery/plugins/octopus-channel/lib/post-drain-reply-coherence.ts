import type { BookingTruthSnapshot } from "../../shared/booking-truth-snapshot";

export type ReplyCoherenceInvalidation = {
  kind:
    | "asks_for_non_missing_field"
    | "asks_for_satisfied_address_field"
    | "asks_for_selected_service"
    | "asks_for_any_missing_field_when_complete"
    | "asks_for_wrong_missing_field"
    | "asks_for_route_ambiguity_when_snapshot_locked"
    | "asks_for_route_ambiguity_when_submitting"
    | "proceeds_with_unlocked_route"
    | "states_wrong_selected_service"
    | "states_wrong_selected_price"
    | "mutates_summary_value"
    | "omits_required_summary"
    | "omits_required_missing_field_ask"
    | "omits_required_route_ambiguity";
  field: string;
  matchedText: string;
};

export type ReplyCoherenceResult = {
  coherent: boolean;
  invalidations: ReplyCoherenceInvalidation[];
};

const FIELD_ASK_PATTERNS: Array<{ field: string; patterns: RegExp[] }> = [
  {
    field: "sender.phone",
    patterns: [/\bsender\s+(?:phone|number)\b/i],
  },
  {
    field: "recipient.phone",
    patterns: [/\brecipient\s+(?:phone|number)\b/i],
  },
  {
    field: "sender.name",
    patterns: [/\bsender\s+name\b/i],
  },
  {
    field: "recipient.name",
    patterns: [/\brecipient\s+name\b/i],
  },
  {
    field: "pickup.house_or_unit",
    patterns: [/\bpickup\b[^.!?\n]{0,50}\b(?:house|building)\b/i],
  },
  {
    field: "pickup.block",
    patterns: [/\bpickup\b[^.!?\n]{0,50}\bblock\b/i],
  },
  {
    field: "pickup.street_or_avenue",
    patterns: [/\bpickup\b[^.!?\n]{0,50}\b(?:street|avenue)\b/i],
  },
  {
    field: "pickup.address",
    patterns: [/\bpickup\s+address\b/i],
  },
  {
    field: "delivery.house_or_unit",
    patterns: [
      /\b(?:delivery|dropoff|drop\s*off)\b[^.!?\n]{0,50}\b(?:house|building)\b/i,
    ],
  },
  {
    field: "delivery.block",
    patterns: [
      /\b(?:delivery|dropoff|drop\s*off)\b[^.!?\n]{0,50}\bblock\b/i,
    ],
  },
  {
    field: "delivery.street_or_avenue",
    patterns: [
      /\b(?:delivery|dropoff|drop\s*off)\b[^.!?\n]{0,50}\b(?:street|avenue)\b/i,
    ],
  },
  {
    field: "delivery.address",
    patterns: [
      /\b(?:delivery|dropoff|drop\s*off)\s+address\b/i,
    ],
  },
  {
    field: "service_type",
    patterns: [
      /\b(?:which|what)\b[^.!?\n]{0,30}\b(?:service|option|delivery type)\b/i,
      /\b(?:choose|select|pick)\b[^.!?\n]{0,30}\b(?:service|option|delivery type)\b/i,
      /\b(?:standard|express)\s+or\s+(?:standard|express)\b/i,
    ],
  },
];

const ANY_MISSING_FIELD_ASK_PATTERNS = [
  /\b(?:still\s+need|need|missing)\b[^.!?\n]{0,80}\b(?:sender|recipient|phone|name|address|block|street|avenue|house|building|service|option)\b/i,
  /\b(?:send|share|give)\b[^.!?\n]{0,80}\b(?:sender|recipient|phone|name|address|block|street|avenue|house|building|service|option)\b/i,
];

const ASK_INTENT_PATTERNS = [
  /[?؟]$/,
  /\b(?:please|pls)\b/i,
  /\b(?:send|share|give|provide|tell me|let me know|need|still need|missing|what is|what's|which|choose|select|pick)\b/i,
  /(?:شنو|شو|وش|وين|أي|اي|اختار|اختر|ارسل|دز|عطني|ابي|أبي|احتاج|ناقص|مطلوب|تقصد|تقصدين)/i,
];

const FACT_STATEMENT_PREFIX_PATTERN =
  /^\s*(?:[-*]\s*)?(?:pickup|delivery|drop\s*off|sender|recipient|service|price)\s*[:：-]/i;

const ROUTE_LOCKED_PROGRESS_PATTERNS = [
  /\b(?:price|cost|total)\b[^.!?\n]{0,40}\b\d+(?:\.\d+)?\s*(?:KWD|KD)\b/i,
  /\b\d+(?:\.\d+)?\s*(?:KWD|KD)\b[^.!?\n]{0,40}\b(?:for|from)\b/i,
  /\b(?:book|booking|order|confirm|summary)\b[^.!?\n]{0,80}\b(?:ready|confirmed|details|sender|recipient|address)\b/i,
  /\b(?:send|share|give)\b[^.!?\n]{0,80}\b(?:sender|recipient|pickup|delivery|dropoff)\b[^.!?\n]{0,40}\b(?:name|phone|address|block|street|house)\b/i,
];

const ROUTE_CLARIFICATION_ASK_PATTERNS = [
  /\b(?:which|what)\b[^.!?؟\n]{0,80}\b(?:pickup|delivery|drop\s*off|dropoff|area|location)\b/i,
  /\b(?:did you mean|do you mean|where in)\b[^.!?؟\n]{0,100}/i,
  /\b(?:choose|select|pick)\b[^.!?؟\n]{0,80}\b(?:pickup|delivery|drop\s*off|dropoff|area|location)\b/i,
  /(?:أي|اي|شنو|وين|اختار|اختر|تقصد|تقصدين)[^.!?؟\n]{0,100}(?:منطقة|استلام|توصيل|الصليبخات|الصليبيخات|شويخ|الشويخ)/i,
  /[\u0600-\u06ff][^.!?؟\n]{0,80}\sأو\s[^.!?؟\n]{0,80}[?؟]/i,
];

const SUMMARY_LABEL_PATTERNS = [
  /\b(?:pickup|delivery|drop\s*off|sender|recipient|service|price)\s*[:：-]/i,
  /(?:الاستلام|التوصيل|المرسل|المستلم|الخدمة|السعر)\s*[:：-]/i,
];

const SERVICE_TOKEN_PATTERNS: Record<string, RegExp[]> = {
  sedan_normal: [
    /\b(?:standard|normal|regular)\b[^.!?؟\n]{0,30}\b(?:sedan|car|delivery)\b/i,
    /\b(?:sedan|car|delivery)\b[^.!?؟\n]{0,30}\b(?:standard|normal|regular)\b/i,
    /(?:سيارة|السيارة|توصيل)[^.!?؟\n]{0,30}(?:عادي|عادية|العاديه|العادية)/i,
    /(?:عادي|عادية|العاديه|العادية)[^.!?؟\n]{0,30}(?:سيارة|السيارة|توصيل)/i,
  ],
  sedan_fast: [
    /\b(?:express|fast|quick)\b[^.!?؟\n]{0,30}\b(?:sedan|car|delivery)\b/i,
    /\b(?:sedan|car|delivery)\b[^.!?؟\n]{0,30}\b(?:express|fast|quick)\b/i,
    /(?:اكسبرس|إكسبرس|سريع|سريعة)[^.!?؟\n]{0,30}(?:سيدان|سيارة|السيارة|توصيل)?/i,
    /(?:سيدان|سيارة|السيارة|توصيل)[^.!?؟\n]{0,30}(?:اكسبرس|إكسبرس|سريع|سريعة)/i,
  ],
  van_normal: [
    /\b(?:standard|normal|regular)\b[^.!?؟\n]{0,30}\b(?:van|box)\b/i,
    /\b(?:van|box)\b[^.!?؟\n]{0,30}\b(?:standard|normal|regular)\b/i,
    /(?:بوكس|فان)[^.!?؟\n]{0,30}(?:عادي|عادية|العاديه|العادية)/i,
  ],
  van_fast: [
    /\b(?:express|fast|quick)\b[^.!?؟\n]{0,30}\b(?:van|box)\b/i,
    /\b(?:van|box)\b[^.!?؟\n]{0,30}\b(?:express|fast|quick)\b/i,
    /(?:بوكس|فان)[^.!?؟\n]{0,30}(?:اكسبرس|إكسبرس|سريع|سريعة)/i,
  ],
};

function extractKwdPrices(reply: string): number[] {
  const out: number[] = [];
  for (const match of reply.matchAll(/\b(\d+(?:[.,]\d{1,3})?)\s*(?:KWD|KD|د\.?ك|دينار)\b/gi)) {
    const n = Number(String(match[1] || "").replace(",", "."));
    if (Number.isFinite(n)) out.push(n);
  }
  return out;
}

function pricesClose(a: number, b: number): boolean {
  return Math.abs(Number(a) - Number(b)) < 0.001;
}

function selectedServiceMentioned(reply: string, selectedType: string | null): boolean {
  if (!selectedType) return false;
  return (SERVICE_TOKEN_PATTERNS[selectedType] || []).some((pattern) =>
    pattern.test(reply),
  );
}

function contradictoryServiceMention(reply: string, selectedType: string | null): string | null {
  if (!selectedType) return null;
  for (const [deliveryType, patterns] of Object.entries(SERVICE_TOKEN_PATTERNS)) {
    if (deliveryType === selectedType) continue;
    const match = patterns
      .map((pattern) => reply.match(pattern))
      .find((item) => item?.[0]);
    if (match?.[0]) return match[0];
  }
  return null;
}

function replyLooksLikeSummary(reply: string, snapshot: BookingTruthSnapshot): boolean {
  const labelCount = SUMMARY_LABEL_PATTERNS.reduce(
    (count, pattern) => count + (pattern.test(reply) ? 1 : 0),
    0,
  );
  const draft = snapshot.draft;
  const lower = reply.toLowerCase();
  const savedSignals = [
    draft?.senderName,
    draft?.senderPhone,
    draft?.recipientName,
    draft?.recipientPhone,
    snapshot.route.pickup.nameEn,
    snapshot.route.pickup.nameAr,
    snapshot.route.dropoff.nameEn,
    snapshot.route.dropoff.nameAr,
  ].filter(Boolean) as string[];
  const matchedSavedSignals = savedSignals.filter((value) =>
    lower.includes(String(value).toLowerCase()),
  ).length;
  return labelCount > 0 && matchedSavedSignals >= 3;
}

function clauseAsksForField(field: string, askClauses: string[]): boolean {
  const entry = FIELD_ASK_PATTERNS.find((item) => item.field === field);
  if (!entry) return false;
  return entry.patterns.some((pattern) =>
    askClauses.some((clause) => pattern.test(clause)),
  );
}

function clauseAsksRouteAmbiguity(askClauses: string[]): boolean {
  return ROUTE_CLARIFICATION_ASK_PATTERNS.some((pattern) =>
    askClauses.some((clause) => pattern.test(clause)),
  );
}

function splitReplyIntoClauses(reply: string): string[] {
  return (reply.match(/[^.!?؟\n]+[.!?؟]?/g) || [])
    .map((part) => part.trim())
    .filter(Boolean);
}

function isAskShapedClause(clause: string): boolean {
  const trimmed = clause.trim();
  if (!trimmed) return false;
  if (FACT_STATEMENT_PREFIX_PATTERN.test(trimmed)) return false;
  return ASK_INTENT_PATTERNS.some((pattern) => pattern.test(trimmed));
}

function fieldSatisfiedByMissingSet(field: string, missing: Set<string>): boolean {
  if (missing.has(field)) return false;
  if (field === "pickup.house_or_unit") {
    return !missing.has("pickup.address") && !missing.has("pickup.house_or_unit");
  }
  if (field === "pickup.block") {
    return !missing.has("pickup.address") && !missing.has("pickup.block");
  }
  if (field === "pickup.street_or_avenue") {
    return !missing.has("pickup.address") && !missing.has("pickup.street_or_avenue");
  }
  if (field === "pickup.address") {
    return !missing.has("pickup.address");
  }
  if (field === "delivery.house_or_unit") {
    return !missing.has("delivery.address") && !missing.has("delivery.house_or_unit");
  }
  if (field === "delivery.block") {
    return !missing.has("delivery.address") && !missing.has("delivery.block");
  }
  if (field === "delivery.street_or_avenue") {
    return !missing.has("delivery.address") && !missing.has("delivery.street_or_avenue");
  }
  if (field === "delivery.address") {
    return !missing.has("delivery.address");
  }
  return true;
}

function invalidationKindForField(
  field: string,
  snapshot: BookingTruthSnapshot,
): ReplyCoherenceInvalidation["kind"] {
  if (field === "service_type") return "asks_for_selected_service";
  if (
    field.startsWith("pickup.") &&
    snapshot.addressSatisfaction.pickup &&
    (field === "pickup.address" ||
      field === "pickup.block" ||
      field === "pickup.street_or_avenue" ||
      field === "pickup.house_or_unit")
  ) {
    return "asks_for_satisfied_address_field";
  }
  if (
    field.startsWith("delivery.") &&
    snapshot.addressSatisfaction.delivery &&
    (field === "delivery.address" ||
      field === "delivery.block" ||
      field === "delivery.street_or_avenue" ||
      field === "delivery.house_or_unit")
  ) {
    return "asks_for_satisfied_address_field";
  }
  return "asks_for_non_missing_field";
}

function compactText(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLowerCase();
}

function replyContainsExpectedValue(reply: string, expected: string | null | undefined): boolean {
  const value = compactText(String(expected || ""));
  if (!value) return true;
  return compactText(reply).includes(value);
}

function replyContainsOneExpectedValue(
  reply: string,
  values: Array<string | null | undefined>,
): boolean {
  return values.some((value) => {
    const expected = String(value || "").trim();
    return expected ? replyContainsExpectedValue(reply, expected) : false;
  });
}

function selectedServiceSummaryPresent(reply: string, snapshot: BookingTruthSnapshot): boolean {
  const selected = snapshot.quote?.selected ?? null;
  const selectedType =
    selected?.deliveryType || snapshot.quote?.selectedService || null;
  if (selectedServiceMentioned(reply, selectedType)) return true;
  return replyContainsOneExpectedValue(reply, [
    selected?.labelEn,
    selected?.labelAr,
    selectedType,
  ]);
}

function selectedPriceSummaryPresent(reply: string, snapshot: BookingTruthSnapshot): boolean {
  const selectedPrice = snapshot.quote?.selected?.price ?? null;
  if (selectedPrice == null || !Number.isFinite(Number(selectedPrice))) return true;
  return extractKwdPrices(reply).some((price) =>
    pricesClose(price, Number(selectedPrice)),
  );
}

function replyAsksForConfirmation(reply: string): boolean {
  return [
    /\b(?:confirm|confirmed|proceed|go ahead|place (?:it|the order)|book (?:it|the order)|shall i|should i)\b/i,
    /[?؟]\s*$/,
    /(?:تأكد|تاكد|أأكد|اكد|نأكد|ناكد|تبي|تبون|أحجز|احجز|اكمل|يلا|تمام)/i,
  ].some((pattern) => pattern.test(reply));
}

function collectRequiredShowSummaryInvalidations(
  reply: string,
  snapshot: BookingTruthSnapshot,
): ReplyCoherenceInvalidation[] {
  if (snapshot.nextAction?.type !== "show_summary" || !snapshot.summary?.ready) {
    return [];
  }
  const draft = snapshot.draft;
  if (!draft) return [];
  const checks: Array<{ field: string; ok: boolean }> = [
    {
      field: "pickup.area",
      ok: replyContainsOneExpectedValue(reply, [
        snapshot.route?.pickup?.nameEn,
        snapshot.route?.pickup?.nameAr,
      ]),
    },
    {
      field: "delivery.area",
      ok: replyContainsOneExpectedValue(reply, [
        snapshot.route?.dropoff?.nameEn,
        snapshot.route?.dropoff?.nameAr,
      ]),
    },
    { field: "sender.name", ok: replyContainsExpectedValue(reply, draft.senderName) },
    { field: "sender.phone", ok: replyContainsExpectedValue(reply, draft.senderPhone) },
    { field: "recipient.name", ok: replyContainsExpectedValue(reply, draft.recipientName) },
    { field: "recipient.phone", ok: replyContainsExpectedValue(reply, draft.recipientPhone) },
    { field: "pickup.block", ok: replyContainsExpectedValue(reply, draft.pickupBlock) },
    { field: "pickup.street", ok: replyContainsExpectedValue(reply, draft.pickupStreet) },
    { field: "pickup.avenue", ok: replyContainsExpectedValue(reply, draft.pickupAvenue) },
    { field: "pickup.house", ok: replyContainsExpectedValue(reply, draft.pickupHouse) },
    { field: "pickup.extra", ok: replyContainsExpectedValue(reply, draft.pickupExtra) },
    { field: "delivery.block", ok: replyContainsExpectedValue(reply, draft.deliveryBlock) },
    { field: "delivery.street", ok: replyContainsExpectedValue(reply, draft.deliveryStreet) },
    { field: "delivery.avenue", ok: replyContainsExpectedValue(reply, draft.deliveryAvenue) },
    { field: "delivery.house", ok: replyContainsExpectedValue(reply, draft.deliveryHouse) },
    { field: "delivery.extra", ok: replyContainsExpectedValue(reply, draft.deliveryExtra) },
    { field: "quote.selectedService", ok: selectedServiceSummaryPresent(reply, snapshot) },
    { field: "quote.selected.price", ok: selectedPriceSummaryPresent(reply, snapshot) },
    { field: "confirmation.ask", ok: replyAsksForConfirmation(reply) },
  ];
  return checks
    .filter((check) => !check.ok)
    .map((check) => ({
      kind: "omits_required_summary" as const,
      field: check.field,
      matchedText: reply.slice(0, 160),
    }));
}

function collectSummaryValueInvalidations(
  reply: string,
  snapshot: BookingTruthSnapshot,
): ReplyCoherenceInvalidation[] {
  const draft = snapshot.draft;
  if (!draft) return [];
  if (!snapshot.route?.pickup || !snapshot.route?.dropoff) return [];
  if (!replyLooksLikeSummary(reply, snapshot)) return [];
  const checks: Array<{ field: string; value: string | null | undefined }> = [
    { field: "sender.name", value: draft.senderName },
    { field: "recipient.name", value: draft.recipientName },
    { field: "sender.phone", value: draft.senderPhone },
    { field: "recipient.phone", value: draft.recipientPhone },
    { field: "pickup.extra", value: draft.pickupExtra },
    { field: "delivery.extra", value: draft.deliveryExtra },
  ];
  const invalidations: ReplyCoherenceInvalidation[] = [];
  for (const check of checks) {
    const value = String(check.value || "").trim();
    if (!value) continue;
    if (!replyContainsExpectedValue(reply, value)) {
      invalidations.push({
        kind: "mutates_summary_value",
        field: check.field,
        matchedText: reply.slice(0, 160),
      });
    }
  }
  return invalidations;
}

export function checkPostDrainReplyCoherence(params: {
  replyText: string | null | undefined;
  bookingTruthSnapshot: BookingTruthSnapshot | null | undefined;
}): ReplyCoherenceResult {
  const reply = String(params.replyText || "").trim();
  const snapshot = params.bookingTruthSnapshot ?? null;
  if (!reply || !snapshot) {
    return { coherent: true, invalidations: [] };
  }
  const missing = new Set(snapshot.missingFields || []);
  const invalidations: ReplyCoherenceInvalidation[] = [];
  const askClauses = splitReplyIntoClauses(reply).filter(isAskShapedClause);
  const nextAction = snapshot.nextAction ?? null;
  const selectedType = snapshot.quote?.selected?.deliveryType || snapshot.quote?.selectedService || null;
  const selectedPrice = snapshot.quote?.selected?.price ?? null;
  const enforceSelectedQuoteFacts = !(
    nextAction?.type === "answer_customer_question" ||
    nextAction?.type === "none_idle" ||
    nextAction?.type === "resolve_coverage_ambiguity"
  );

  for (const entry of FIELD_ASK_PATTERNS) {
    for (const pattern of entry.patterns) {
      const match = askClauses.map((clause) => clause.match(pattern)).find((item) => item?.[0]);
      if (!match?.[0]) continue;
      if (
        nextAction?.type === "collect_missing_field" &&
        entry.field !== nextAction.field
      ) {
        invalidations.push({
          kind: "asks_for_wrong_missing_field",
          field: entry.field,
          matchedText: match[0],
        });
        break;
      }
      if (fieldSatisfiedByMissingSet(entry.field, missing)) {
        invalidations.push({
          kind: invalidationKindForField(entry.field, snapshot),
          field: entry.field,
          matchedText: match[0],
        });
      }
      break;
    }
  }

  if (missing.size === 0) {
    for (const pattern of ANY_MISSING_FIELD_ASK_PATTERNS) {
      const match = askClauses.map((clause) => clause.match(pattern)).find((item) => item?.[0]);
      if (match?.[0]) {
        invalidations.push({
          kind: "asks_for_any_missing_field_when_complete",
          field: "missingFields",
          matchedText: match[0],
        });
        break;
      }
    }
  }

  if (snapshot.route.lockStatus !== "locked") {
    for (const pattern of ROUTE_LOCKED_PROGRESS_PATTERNS) {
      const match = reply.match(pattern);
      if (match?.[0]) {
        invalidations.push({
          kind: "proceeds_with_unlocked_route",
          field: "route.lockStatus",
          matchedText: match[0],
        });
        break;
      }
    }
  }

  if (
    (snapshot.route.lockStatus === "locked" && !snapshot.pendingRouteAmbiguity) ||
    nextAction?.type === "submit_order"
  ) {
    for (const pattern of ROUTE_CLARIFICATION_ASK_PATTERNS) {
      const match = askClauses.map((clause) => clause.match(pattern)).find((item) => item?.[0]);
      if (match?.[0]) {
        invalidations.push({
          kind:
            nextAction?.type === "submit_order"
              ? "asks_for_route_ambiguity_when_submitting"
              : "asks_for_route_ambiguity_when_snapshot_locked",
          field: "route.pendingAmbiguity",
          matchedText: match[0],
        });
        break;
      }
    }
  }

  if (enforceSelectedQuoteFacts && selectedType) {
    const wrongService = contradictoryServiceMention(reply, selectedType);
    if (wrongService && !selectedServiceMentioned(reply, selectedType)) {
      invalidations.push({
        kind: "states_wrong_selected_service",
        field: "quote.selectedService",
        matchedText: wrongService,
      });
    }
  }

  if (
    enforceSelectedQuoteFacts &&
    selectedPrice != null &&
    Number.isFinite(Number(selectedPrice))
  ) {
    const wrongPrice = extractKwdPrices(reply).find(
      (price) => !pricesClose(price, Number(selectedPrice)),
    );
    if (wrongPrice != null) {
      invalidations.push({
        kind: "states_wrong_selected_price",
        field: "quote.selected.price",
        matchedText: `${wrongPrice.toFixed(3)} KWD`,
      });
    }
  }

  if (
    nextAction?.type === "show_summary" &&
    snapshot.summary.ready &&
    !replyLooksLikeSummary(reply, snapshot)
  ) {
    invalidations.push({
      kind: "omits_required_summary",
      field: "nextAction.show_summary",
      matchedText: reply.slice(0, 160),
    });
  }
  invalidations.push(...collectRequiredShowSummaryInvalidations(reply, snapshot));
  invalidations.push(...collectSummaryValueInvalidations(reply, snapshot));

  if (
    nextAction?.type === "collect_missing_field" &&
    !clauseAsksForField(nextAction.field, askClauses)
  ) {
    invalidations.push({
      kind: "omits_required_missing_field_ask",
      field: nextAction.field,
      matchedText: reply.slice(0, 160),
    });
  }

  if (
    nextAction?.type === "resolve_route_ambiguity" &&
    !clauseAsksRouteAmbiguity(askClauses)
  ) {
    invalidations.push({
      kind: "omits_required_route_ambiguity",
      field: nextAction.field,
      matchedText: reply.slice(0, 160),
    });
  }

  return {
    coherent: invalidations.length === 0,
    invalidations,
  };
}
