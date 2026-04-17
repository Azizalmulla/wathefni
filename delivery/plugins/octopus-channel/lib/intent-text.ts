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
  const escalationMarkers = [
    "تم تحويل محادثتكم لموظف الدعم المختص",
    "تم تحويل المحادثة لموظف الدعم المختص",
    "تم تسجيل الشكوى وتحويلها للإدارة للمراجعة",
    "human agent",
    "moved to a human agent",
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
