// ---------------------------------------------------------------------------
// Wave 4 extraction: pure text/language intent helpers.
// These helpers classify or rewrite customer-authored text and agent replies
// without touching any module-scoped state. Extracted from
// `plugins/octopus-channel/index.ts`. Some depend on `normalizeIntentText` /
// `isTrackingIntent` / `extractTrackingOrderId` from the shared
// conversation-policy module, which are already pure and don't touch state.
// ---------------------------------------------------------------------------

import {
  extractTrackingOrderId,
  isTrackingIntent,
  normalizeIntentText,
} from "../../shared/conversation-policy";

export function stripBookingContinuationLeadIn(language: "ar" | "en", text: string): string {
  const normalized = String(text || "");
  if (language === "ar") {
    return normalized.startsWith("أكيد، نكمل الطلب.\n")
      ? normalized.slice("أكيد، نكمل الطلب.\n".length)
      : normalized;
  }
  return normalized.startsWith("Sure, let's book it.\n")
    ? normalized.slice("Sure, let's book it.\n".length)
    : normalized;
}

export function includesAnyNormalizedPhrase(text: string, phrases: readonly string[]): boolean {
  return phrases.some((phrase) => text.includes(phrase));
}

export function isSummaryEditRequest(text: string): boolean {
  const normalized = normalizeIntentText(text);
  if (!normalized) {
    return false;
  }
  if (
    [
      "no",
      "nope",
      "wrong",
      "fix it",
      "change it",
      "edit it",
      "start over",
      "لا",
      "غلط",
      "مو صحيح",
      "مو صح",
      "عدله",
      "عدليها",
      "غيره",
      "غيرها",
    ].includes(normalized)
  ) {
    return true;
  }
  return [
    "thats wrong",
    "that's wrong",
    "this is wrong",
    "this is not right",
    "that is wrong",
    "مو هذا",
    "هذا غلط",
    "هذا مو صحيح",
    "لا هذا غلط",
    "لا مو صحيح",
  ].some((phrase) => normalized.includes(phrase));
}

export function textContainsUrl(text: string): boolean {
  return /https?:\/\/\S+/i.test(text);
}

export function shouldMoveToHumanAgent(replyText: string): boolean {
  const normalized = replyText.replace(/\s+/g, " ").trim();
  if (!normalized) return false;
  // String-matching escalation detector. The markers split into two
  // families:
  //
  //   1. LLM / support-tool markers — Arabic customer-facing phrasing
  //      the `assign_agent` / `complaint` support tools emit when they
  //      stub the Octopus `toagent` call, plus generic "human agent"
  //      phrasing the LLM sometimes emits directly.
  //   2. Manual-confirm HANDOFF markers (Phase 4, 2026-04-20) —
  //      distinctive substrings from the server-rendered
  //      `buildDeterministicManualConfirmHandoffReply` only. We match
  //      on "one of our agents will reach out" (EN) and
  //      "راح يتواصل معك أحد الموظفين" (AR) because those substrings
  //      are unique to the handoff reply; they do NOT appear in the
  //      pickup-ask or delivery-ask replies (which also mention
  //      "manual confirmation by our team" but don't promise agent
  //      contact). This keeps `toagent` firing only on the actual
  //      handoff turn, not on every manual-confirm collection turn.
  const escalationMarkers = [
    "تم تحويل محادثتكم لموظف الدعم المختص",
    "تم تحويل المحادثة لموظف الدعم المختص",
    "تم تسجيل الشكوى وتحويلها للإدارة للمراجعة",
    "human agent",
    "moved to a human agent",
    // Manual-confirm handoff (Phase 4).
    "one of our agents will reach out",
    "راح يتواصل معك أحد الموظفين",
  ];
  return escalationMarkers.some((marker) => normalized.includes(marker));
}

export function buildDeterministicTrackingGuardReply(
  text: string,
  language: "ar" | "en",
): string | null {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (!normalized || normalized.startsWith("<media:")) {
    return null;
  }
  if (!isTrackingIntent(normalized)) {
    return null;
  }
  if (extractTrackingOrderId(normalized)) {
    return null;
  }
  return language === "ar"
    ? 'للمتابعة، أرسل رقم الطلب الصحيح الذي يبدأ بـ "ORDER-" مثل ORDER-12345.'
    : 'To continue, send the correct order number starting with "ORDER-", for example ORDER-12345.';
}
