// ---------------------------------------------------------------------------
// Wave 2b extraction: pure booking-step input parsers.
// These helpers take a customer-authored string and deterministically extract
// sender/recipient/address fields for the booking flow. Extracted from
// `plugins/octopus-channel/index.ts`. Shared `normalizeIntentText` from the
// conversation-policy module is used for token normalization; nothing here
// touches module-scope state.
// ---------------------------------------------------------------------------

import { normalizeIntentText } from "../../shared/conversation-policy";

export function normalizeBookingPhone(value: string | null): string | null {
  const digits = String(value || "").replace(/[^\d+]/g, "").trim();
  if (!digits) {
    return null;
  }
  return digits.replace(/^\+/, "");
}

export function normalizeCurrentWhatsappBookingPhone(value: string | null): string | null {
  const normalized = normalizeBookingPhone(value);
  if (!normalized) {
    return null;
  }
  if (/^00965\d{8}$/.test(normalized)) {
    return normalized.slice(-8);
  }
  if (/^965\d{8}$/.test(normalized)) {
    return normalized.slice(-8);
  }
  if (/^\d{8}$/.test(normalized)) {
    return normalized;
  }
  return null;
}

export function pickCurrentWhatsappPhone(replyTarget: string | null): string | null {
  return normalizeCurrentWhatsappBookingPhone(replyTarget);
}

export function cleanParsedName(value: string): string | null {
  const cleaned = value
    .replace(
      /\b(?:and use the current number|use the current number|same number|current number|this number)\b/gi,
      "",
    )
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[,.\-\s]+|[,.\-\s]+$/g, "");
  return cleaned || null;
}

export function textMentionsCurrentWhatsappNumber(value: string): boolean {
  return (
    /\b(?:and use the current number|use the current number|same number|current number|this number|use this number|use whatsapp number|same whatsapp number)\b/i.test(
      value,
    ) ||
    /(?:نفس الرقم|هذا الرقم|رقم الواتساب|استخدم(?:وا)? هذا الرقم|استخدم(?:وا)? نفس الرقم)/i.test(
      value,
    )
  );
}

export function isSenderPhoneConfirmationText(value: string): boolean {
  const normalized = normalizeIntentText(value);
  return [
    "yes",
    "yes please",
    "ok",
    "okay",
    "confirm",
    "confirmed",
    "same number",
    "current number",
    "this number",
    "use this number",
    "use current number",
    "use whatsapp number",
    "same whatsapp number",
    "نعم",
    "اي",
    "ايي",
    "اي نعم",
    "أكيد",
    "اكيد",
    "مؤكد",
    "أكد",
    "نفس الرقم",
    "هذا الرقم",
    "رقم الواتساب",
  ].includes(normalized);
}

export function parseSenderStepInput(
  text: string,
  replyTarget: string | null,
  current: { senderName: string | null; senderPhone: string | null },
): {
  senderName: string | null;
  senderPhone: string | null;
  hasSignal: boolean;
} {
  const normalizedText = text.trim();
  if (!normalizedText) {
    return {
      senderName: null,
      senderPhone: null,
      hasSignal: false,
    };
  }
  const explicitPhone = normalizeBookingPhone(
    normalizedText.match(/(\+?\d[\d\s-]{6,}\d)/)?.[1] || null,
  );
  const withoutPhone = normalizedText
    .replace(/(\+?\d[\d\s-]{6,}\d)/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const confirmationOnly = isSenderPhoneConfirmationText(normalizedText);
  let senderName = cleanParsedName(withoutPhone);
  if (confirmationOnly && current.senderName) {
    senderName = null;
  }
  const useCurrentWhatsapp =
    textMentionsCurrentWhatsappNumber(normalizedText) ||
    (confirmationOnly && !!current.senderName);
  return {
    senderName,
    senderPhone:
      explicitPhone ||
      (useCurrentWhatsapp ? pickCurrentWhatsappPhone(replyTarget) : null),
    hasSignal: Boolean(senderName || explicitPhone || useCurrentWhatsapp),
  };
}

export function parseRecipientStepInput(text: string): {
  recipientName: string | null;
  recipientPhone: string | null;
  hasSignal: boolean;
} {
  const normalizedText = text.trim();
  if (!normalizedText) {
    return {
      recipientName: null,
      recipientPhone: null,
      hasSignal: false,
    };
  }
  const phoneMatch = normalizedText.match(/(\+?\d[\d\s-]{6,}\d)/);
  const recipientPhone = normalizeBookingPhone(phoneMatch?.[1] || null);
  const recipientName = cleanParsedName(
    normalizedText.replace(phoneMatch?.[0] || "", " "),
  );
  return {
    recipientName,
    recipientPhone,
    hasSignal: Boolean(recipientName || recipientPhone),
  };
}

export function normalizeAddressFieldValue(
  value: string | null | undefined,
): string | null {
  const cleaned = String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[,.\-\s]+|[,.\-\s]+$/g, "");
  return cleaned || null;
}

export function stripAddressFieldLabels(value: string): string {
  return value
    .replace(/^(?:block|street|house|building)\s*[:\-]?\s*/i, "")
    .replace(
      /^(?:قطعة|قطعه|بلوك|شارع|منزل|بيت|بناية|بنايه|عمارة|عماره)\s*[:\-]?\s*/i,
      "",
    )
    .trim();
}

export function parseAddressStepInput(
  text: string,
  current: { block: string | null; street: string | null; house: string | null },
): {
  block: string | null;
  street: string | null;
  house: string | null;
  hasSignal: boolean;
} {
  const normalizedText = text.replace(/\s+/g, " ").trim();
  if (!normalizedText) {
    return {
      block: null,
      street: null,
      house: null,
      hasSignal: false,
    };
  }
  const partial = {
    block: normalizeAddressFieldValue(
      normalizedText.match(
        /(?:\bblock\b|قطعة|قطعه|بلوك)\s*[:\-]?\s*([^,\n]+)(?:,|\n|$)/i,
      )?.[1] || null,
    ),
    street: normalizeAddressFieldValue(
      normalizedText.match(
        /(?:\bstreet\b|شارع)\s*[:\-]?\s*([^,\n]+)(?:,|\n|$)/i,
      )?.[1] || null,
    ),
    house: normalizeAddressFieldValue(
      normalizedText.match(
        /(?:\bhouse\b|\bbuilding\b|منزل|بيت|بناية|بنايه|عمارة|عماره)\s*[:\-]?\s*([^,\n]+)(?:,|\n|$)/i,
      )?.[1] || null,
    ),
  };
  if (partial.block || partial.street || partial.house) {
    return {
      ...partial,
      hasSignal: true,
    };
  }
  const compactParts = normalizedText
    .split(/[,\n]/)
    .map((part) => stripAddressFieldLabels(part))
    .map((part) => normalizeAddressFieldValue(part))
    .filter(Boolean) as string[];
  if (compactParts.length > 0) {
    const missingFields = [
      !current.block ? "block" : null,
      !current.street ? "street" : null,
      !current.house ? "house" : null,
    ].filter(Boolean) as Array<"block" | "street" | "house">;
    const next: {
      block: string | null;
      street: string | null;
      house: string | null;
      hasSignal: boolean;
    } = {
      block: null,
      street: null,
      house: null,
      hasSignal: false,
    };
    compactParts.forEach((part, index) => {
      const field = missingFields[index];
      if (!field || !part) {
        return;
      }
      next[field] = part;
      next.hasSignal = true;
    });
    if (next.hasSignal) {
      return next;
    }
  }
  return {
    block: null,
    street: null,
    house: null,
    hasSignal: false,
  };
}
