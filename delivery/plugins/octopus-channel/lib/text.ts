// ---------------------------------------------------------------------------
// Wave 2a extraction: pure text / language / reply sanitization helpers.
// These are deterministic string transforms used by the inbound flow to
// classify reply shape, scrub provider error strings, and build short
// deterministic Arabic/English replies. No I/O, no module-scope state.
// ---------------------------------------------------------------------------

import { hasVisibleArabic, hasVisibleLatin } from "../../shared/conversation-policy";
import { asTrimmedString } from "./normalize";

export function isProviderErrorText(value: unknown): boolean {
  const text = asTrimmedString(value);
  if (!text) return false;
  const normalized = text.replace(/\s+/g, " ").trim();
  return (
    normalized.includes("An error occurred while processing your request") ||
    normalized.includes("help.openai.com") ||
    /Please include the request ID req_[a-zA-Z0-9]+/i.test(normalized)
  );
}

export function sanitizeAgentReplyText(replyText: unknown): {
  replyText: string;
  providerErrorSuppressed: boolean;
} {
  const text = asTrimmedString(replyText);
  if (!text) {
    return { replyText: "", providerErrorSuppressed: false };
  }
  const blocks = text
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);
  const filteredBlocks = blocks.filter((block) => !isProviderErrorText(block));
  const cleaned = filteredBlocks.join("\n\n").trim();
  if (cleaned) {
    return {
      replyText: cleaned,
      providerErrorSuppressed: filteredBlocks.length !== blocks.length,
    };
  }
  if (isProviderErrorText(text)) {
    return { replyText: "", providerErrorSuppressed: true };
  }
  return { replyText: text, providerErrorSuppressed: false };
}

export function normalizeReplyTextForComparison(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

export function looksLikePriceOnlyReply(text: string): boolean {
  const normalized = normalizeReplyTextForComparison(text);
  if (!normalized) {
    return false;
  }
  return /^(?:it'?s\s+|price:?\s+)?\d+(?:\.\d{1,3})?\s*(?:KWD|KD|د\.ك)\.?$/i.test(normalized);
}

export function containsArabic(text: string): boolean {
  return hasVisibleArabic(text);
}

export function containsLatin(text: string): boolean {
  return hasVisibleLatin(text);
}

export function buildDeterministicGreetingReply(language: "ar" | "en"): string {
  return language === "ar"
    ? "يا هلا حياكم الله في رايدرز، شلون نقدر نخدمكم؟"
    : "Welcome to Riders, How can we help you?";
}

export function buildDeterministicPassengerTransportReply(language: "ar" | "en"): string {
  return language === "ar"
    ? "نعتذر منكم، إحنا نوصل الطلبات والشحنات فقط وما نوفر خدمة نقل أشخاص."
    : "We only deliver items and packages. We do not transport people.";
}

export function buildDeterministicLanguageSwitchReply(language: "ar" | "en"): string {
  return language === "ar"
    ? "حياكم الله في رايدرز، نكمل بالعربي. شلون نقدر نخدمكم؟"
    : "Sure, we can continue in English. How can we help you?";
}

export function buildDeterministicServiceOverviewReply(language: "ar" | "en"): string {
  return language === "ar"
    ? "نوفر خدمة سيارة عادية، وسيارة سريعة، وبوكس، وبوكس سريع، وسيارة مبردة، وخدمة مساعد. إذا تبون، أرسلوا منطقتي الاستلام والتوصيل ونحسب لكم السعر الدقيق."
    : "We offer standard sedan, express sedan, box van, express box van, refrigerated van, and helper service. If you want, send the pickup and dropoff areas and we'll quote the exact price.";
}

export function buildDeterministicGraceWindowReply(language: "ar" | "en"): string {
  return language === "ar"
    ? "هلا! عندنا طلبك السابق محفوظ. تبون نكمل من وين وقفنا ولا تبون نبدأ من جديد؟"
    : "Hi! Your previous booking is still saved. Would you like to continue where you left off or start fresh?";
}

export function buildProviderIssueFallbackReply(language: "ar" | "en"): string {
  return language === "ar"
    ? "عذراً، عندنا مشكلة مؤقتة بالنظام حالياً. حاولوا بعد شوي، وإذا مستعجلين نقدر نحولكم للموظف."
    : "Sorry, we are having a temporary system issue right now. Please try again shortly, or we can hand you to a human agent.";
}
