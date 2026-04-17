// ---------------------------------------------------------------------------
// Wave 4 extraction: booking-flow helpers.
// Pure helpers that inspect a `PersistedBookingDraft` / conversation-controller
// entry and either return a derived predicate, an address formatting, or a
// deterministic booking-step prompt. No state; only reads from inputs and
// already-extracted shared helpers. Extracted from
// `plugins/octopus-channel/index.ts`.
// ---------------------------------------------------------------------------

import { createHash } from "node:crypto";
import type {
  BookingCollectionStep,
  PersistedBookingDraft,
  PersistedBookingLocation,
  PersistedConversationControllerEntry,
} from "../../shared/conversation-policy";
import { normalizeIntentText } from "../../shared/conversation-policy";
import { pickCurrentWhatsappPhone } from "./booking-parse";

export function hasStructuredBookingLocation(
  location: PersistedBookingLocation | null | undefined,
): boolean {
  return Boolean(
    location && Number.isFinite(location.latitude) && Number.isFinite(location.longitude),
  );
}

export function hasCompleteTextAddress(params: {
  block: string | null | undefined;
  street: string | null | undefined;
  house: string | null | undefined;
}): boolean {
  return Boolean(params.block && params.street && params.house);
}

export function hasSatisfiedBookingAddress(
  draft: PersistedBookingDraft,
  kind: "pickup" | "delivery",
): boolean {
  const location = kind === "pickup" ? draft.pickupLocation : draft.deliveryLocation;
  if (hasStructuredBookingLocation(location)) {
    return true;
  }
  return hasCompleteTextAddress({
    block: kind === "pickup" ? draft.pickupBlock : draft.deliveryBlock,
    street: kind === "pickup" ? draft.pickupStreet : draft.deliveryStreet,
    house: kind === "pickup" ? draft.pickupHouse : draft.deliveryHouse,
  });
}

export function resolveNextBookingStepFromDraft(draft: PersistedBookingDraft): BookingCollectionStep {
  if (!draft.senderName || !draft.senderPhone) {
    return "sender";
  }
  if (!draft.recipientName || !draft.recipientPhone) {
    return "recipient";
  }
  if (!hasSatisfiedBookingAddress(draft, "pickup")) {
    return "pickup_address";
  }
  if (!hasSatisfiedBookingAddress(draft, "delivery")) {
    return "delivery_address";
  }
  return "summary_pending";
}

export function getLocationRoleSelection(text: string): "pickup" | "delivery" | null {
  const normalized = normalizeIntentText(text);
  if (!normalized) {
    return null;
  }
  const pickupMarkers = [
    "pickup",
    "pick up",
    "pic up",
    "pikup",
    "pik up",
    "for pickup",
    "its the pickup",
    "it's the pickup",
    "the pickup",
    "pickup location",
    "pickup side",
    "sender side",
    "from here",
    "collection",
    "collect",
    "sender",
    "الاستلام",
    "استلام",
    "استلامه",
    "المرسل",
    "مكان الاستلام",
    "للاستلام",
    "هذا مكان الاستلام",
    "مكان المرسل",
    "جهة الاستلام",
    "مكان الشحن",
  ];
  const deliveryMarkers = [
    "delivery",
    "dropoff",
    "drop off",
    "drop-off",
    "for delivery",
    "its the delivery",
    "it's the delivery",
    "the delivery",
    "delivery location",
    "delivery side",
    "recipient side",
    "destination",
    "recipient",
    "التوصيل",
    "التسليم",
    "توصيل",
    "تسليم",
    "المستلم",
    "الوجهة",
    "الوجهه",
    "مكان التوصيل",
    "للتوصيل",
    "هذا مكان التوصيل",
    "مكان المستلم",
    "جهة التوصيل",
    "مكان التسليم",
  ];
  const isPickup = pickupMarkers.some((marker) => normalized === marker || normalized.includes(marker));
  const isDelivery = deliveryMarkers.some((marker) => normalized === marker || normalized.includes(marker));
  if (isPickup === isDelivery) {
    return null;
  }
  return isPickup ? "pickup" : "delivery";
}

export function formatPersistedBookingLocationLabel(
  location: PersistedBookingLocation | null | undefined,
): string | null {
  if (!location) {
    return null;
  }
  const label = [location.name, location.address].filter(Boolean).join(" — ");
  if (label) {
    return label;
  }
  if (location.resolvedAreaName) {
    return location.resolvedAreaName;
  }
  if (Number.isFinite(location.latitude) && Number.isFinite(location.longitude)) {
    return `${location.latitude.toFixed(6)}, ${location.longitude.toFixed(6)}`;
  }
  return null;
}

export function buildSavedLocationRoleReply(params: {
  language: "ar" | "en";
  role: "pickup" | "delivery";
  entry: PersistedConversationControllerEntry;
}): string {
  const bothSidesSaved =
    hasStructuredBookingLocation(params.entry.bookingDraft.pickupLocation) &&
    hasStructuredBookingLocation(params.entry.bookingDraft.deliveryLocation);
  if (params.language === "ar") {
    if (bothSidesSaved) {
      return params.entry.stage === "quoted"
        ? `تمام، حفظنا هذا الموقع كموقع ${params.role === "pickup" ? "الاستلام" : "التوصيل"}. وإذا تبون نكمل الحجز قولوا نعم.`
        : `تمام، حفظنا هذا الموقع كموقع ${params.role === "pickup" ? "الاستلام" : "التوصيل"}. وإذا تبون نحسب السعر لهذا المشوار قولوا احسب السعر.`;
    }
    return params.role === "pickup"
      ? "تمام، حفظنا هذا الموقع كموقع الاستلام. أرسلوا بعد موقع أو منطقة التوصيل."
      : "تمام، حفظنا هذا الموقع كموقع التوصيل. أرسلوا بعد موقع أو منطقة الاستلام.";
  }
  if (bothSidesSaved) {
    return params.entry.stage === "quoted"
      ? `Understood. I saved this as the ${params.role} location. If you want to continue the booking, just say yes.`
      : `Understood. I saved this as the ${params.role} location. If you want, ask me to quote this route.`;
  }
  return params.role === "pickup"
    ? "Understood. I saved this as the pickup location. Now send the delivery location or area."
    : "Understood. I saved this as the delivery location. Now send the pickup location or area.";
}

export function buildDeterministicLocationSavedDuringIdentityReply(params: {
  language: "ar" | "en";
  role: "pickup" | "delivery" | null;
  entry: PersistedConversationControllerEntry;
}): string {
  const nextStepPrompt = buildDeterministicBookingDetailsReply(
    params.language,
    params.entry.bookingStep,
    params.entry,
  );
  if (params.role) {
    return params.language === "ar"
      ? `تمام، حفظنا الموقع كموقع ${params.role === "pickup" ? "الاستلام" : "التوصيل"}. نكمل الخطوة الحالية أول.\n${nextStepPrompt}`
      : `Got it, I saved this as the ${params.role} location. Let's finish the current step first.\n${nextStepPrompt}`;
  }
  return params.language === "ar"
    ? `تمام، حفظنا الموقع. نكمل الخطوة الحالية أول.\n${nextStepPrompt}`
    : `Got it, I saved your location. Let's finish the current step first.\n${nextStepPrompt}`;
}

export function buildDeterministicBookingDetailsReply(
  language: "ar" | "en",
  bookingStep: BookingCollectionStep = "sender",
  controllerEntry: PersistedConversationControllerEntry | null = null,
): string {
  const effectiveBookingStep =
    controllerEntry &&
    (bookingStep === "sender" ||
      bookingStep === "recipient" ||
      bookingStep === "pickup_address" ||
      bookingStep === "delivery_address")
      ? resolveNextBookingStepFromDraft(controllerEntry.bookingDraft)
      : bookingStep;
  const pickupArea =
    language === "ar"
      ? controllerEntry?.quotePickupAreaNameAr || controllerEntry?.quotePickupAreaNameEn || "منطقة الاستلام"
      : controllerEntry?.quotePickupAreaNameEn || "the pickup area";
  const dropoffArea =
    language === "ar"
      ? controllerEntry?.quoteDropoffAreaNameAr || controllerEntry?.quoteDropoffAreaNameEn || "منطقة التوصيل"
      : controllerEntry?.quoteDropoffAreaNameEn || "the delivery area";
  const senderPhone = controllerEntry?.bookingDraft.senderPhone || null;
  const currentWhatsappPhone = pickCurrentWhatsappPhone(controllerEntry?.replyTarget || null);
  const senderNameMissing = !controllerEntry?.bookingDraft.senderName;
  const senderPhoneMissing = !senderPhone;
  const recipientNameMissing = !controllerEntry?.bookingDraft.recipientName;
  const recipientPhoneMissing = !controllerEntry?.bookingDraft.recipientPhone;
  const pickupMissing = {
    block: !controllerEntry?.bookingDraft.pickupBlock,
    street: !controllerEntry?.bookingDraft.pickupStreet,
    house: !controllerEntry?.bookingDraft.pickupHouse,
  };
  const deliveryMissing = {
    block: !controllerEntry?.bookingDraft.deliveryBlock,
    street: !controllerEntry?.bookingDraft.deliveryStreet,
    house: !controllerEntry?.bookingDraft.deliveryHouse,
  };
  const hasPendingLocation = Boolean(controllerEntry?.bookingDraft.pendingLocation);

  if (language === "ar") {
    if (effectiveBookingStep === "recipient") {
      if (recipientNameMissing && recipientPhoneMissing) {
        return "الخطوة التالية: أرسلوا اسم المستلم ورقم المستلم.";
      }
      if (recipientNameMissing) {
        return "الخطوة التالية: أرسلوا اسم المستلم الكامل.";
      }
      return "الخطوة التالية: أرسلوا رقم المستلم.";
    }
    if (effectiveBookingStep === "pickup_address") {
      if (hasPendingLocation) {
        return "عندنا موقع مرسل منكم. إذا كان للاستلام قولوا استلام، وإذا كان للتوصيل قولوا توصيل.";
      }
      if (pickupMissing.block && pickupMissing.street && pickupMissing.house) {
        return `الخطوة التالية: أرسلوا موقع الاستلام في ${pickupArea} كلوكيشن أو رابط خريطة، أو اكتبوا القطعة والشارع والمنزل أو البناية.`;
      }
      if (pickupMissing.block) {
        return `الخطوة التالية: أرسلوا قطعة عنوان الاستلام في ${pickupArea}.`;
      }
      if (pickupMissing.street) {
        return `الخطوة التالية: أرسلوا شارع عنوان الاستلام في ${pickupArea}.`;
      }
      return `الخطوة التالية: أرسلوا المنزل أو البناية لعنوان الاستلام في ${pickupArea}.`;
    }
    if (effectiveBookingStep === "delivery_address") {
      if (hasPendingLocation) {
        return "عندنا موقع مرسل منكم. إذا كان للاستلام قولوا استلام، وإذا كان للتوصيل قولوا توصيل.";
      }
      if (deliveryMissing.block && deliveryMissing.street && deliveryMissing.house) {
        return `الخطوة التالية: أرسلوا موقع التوصيل في ${dropoffArea} كلوكيشن أو رابط خريطة، أو اكتبوا القطعة والشارع والمنزل أو البناية.`;
      }
      if (deliveryMissing.block) {
        return `الخطوة التالية: أرسلوا قطعة عنوان التوصيل في ${dropoffArea}.`;
      }
      if (deliveryMissing.street) {
        return `الخطوة التالية: أرسلوا شارع عنوان التوصيل في ${dropoffArea}.`;
      }
      return `الخطوة التالية: أرسلوا المنزل أو البناية لعنوان التوصيل في ${dropoffArea}.`;
    }
    if (effectiveBookingStep === "summary_pending" || effectiveBookingStep === "awaiting_summary_confirmation") {
      return "نلخص لكم الطلب وننتظر تأكيدكم النهائي قبل إنشاءه.";
    }
    if (senderNameMissing && senderPhoneMissing) {
      return [
        "أكيد، نكمل الطلب.",
        "أول خطوة: أرسلوا اسم المرسل.",
        currentWhatsappPhone
          ? `وأكّدوا إذا نستخدم رقم الواتساب الحالي ${currentWhatsappPhone} كرقم المرسل، أو اكتبوا رقم مرسل مختلف.`
          : "وأرسلوا رقم المرسل.",
      ].join("\n");
    }
    if (senderNameMissing) {
      return "أول خطوة: أرسلوا اسم المرسل الكامل.";
    }
    if (senderPhoneMissing) {
      if (controllerEntry?.bookingDraft.senderPhoneRejected) {
        return "أرسلوا رقم المرسل.";
      }
      return currentWhatsappPhone
        ? `أول خطوة: هل نعتمد رقم الواتساب الحالي ${currentWhatsappPhone} كرقم المرسل، أو ترسلون رقم مرسل مختلف؟`
        : "أول خطوة: أرسلوا رقم المرسل.";
    }
    return [
      "أكيد، نكمل الطلب.",
      "أول خطوة: أرسلوا اسم المرسل.",
      currentWhatsappPhone
        ? `ونستخدم رقم الواتساب الحالي ${currentWhatsappPhone} كرقم المرسل إذا أكّدتوا ذلك، أو اكتبوا رقم مرسل مختلف.`
        : "وأرسلوا رقم المرسل إذا مختلف.",
    ].join("\n");
  }

  if (effectiveBookingStep === "recipient") {
    if (recipientNameMissing && recipientPhoneMissing) {
      return "Next step: please send the recipient full name and recipient phone number.";
    }
    if (recipientNameMissing) {
      return "Next step: please send the recipient full name.";
    }
    return "Next step: please send the recipient phone number.";
  }
  if (effectiveBookingStep === "pickup_address") {
    if (hasPendingLocation) {
      return "You already shared a location. Reply with pickup if it is the pickup address, or delivery if it is the delivery address.";
    }
    if (pickupMissing.block && pickupMissing.street && pickupMissing.house) {
      return `Next step: please send the pickup location pin or map link for ${pickupArea}, or send the pickup block, street, and house/building.`;
    }
    if (pickupMissing.block) {
      return `Next step: please send the pickup block for ${pickupArea}.`;
    }
    if (pickupMissing.street) {
      return `Next step: please send the pickup street for ${pickupArea}.`;
    }
    return `Next step: please send the pickup house/building for ${pickupArea}.`;
  }
  if (effectiveBookingStep === "delivery_address") {
    if (hasPendingLocation) {
      return "You already shared a location. Reply with pickup if it is the pickup address, or delivery if it is the delivery address.";
    }
    if (deliveryMissing.block && deliveryMissing.street && deliveryMissing.house) {
      return `Next step: please send the delivery location pin or map link for ${dropoffArea}, or send the delivery block, street, and house/building.`;
    }
    if (deliveryMissing.block) {
      return `Next step: please send the delivery block for ${dropoffArea}.`;
    }
    if (deliveryMissing.street) {
      return `Next step: please send the delivery street for ${dropoffArea}.`;
    }
    return `Next step: please send the delivery house/building for ${dropoffArea}.`;
  }
  if (effectiveBookingStep === "summary_pending" || effectiveBookingStep === "awaiting_summary_confirmation") {
    return "We will summarize the order now and wait for your final confirmation before creating it.";
  }
  if (senderNameMissing && senderPhoneMissing) {
    return [
      "Sure, let's book it.",
      "First step: please send the sender full name.",
      currentWhatsappPhone
        ? `Please also confirm whether we should use this WhatsApp number ${currentWhatsappPhone} as the sender phone, or send a different sender number.`
        : "Please also send the sender phone number.",
    ].join("\n");
  }
  if (senderNameMissing) {
    return "First step: please send the sender full name.";
  }
  if (senderPhoneMissing) {
    if (controllerEntry?.bookingDraft.senderPhoneRejected) {
      return "Please send the sender phone number.";
    }
    return currentWhatsappPhone
      ? `First step: should we use this WhatsApp number ${currentWhatsappPhone} as the sender phone, or would you like to send a different sender number?`
      : "First step: please send the sender phone number.";
  }
  return [
    "Sure, let's book it.",
    "First step: please send the sender full name.",
    currentWhatsappPhone
      ? `We can use this WhatsApp number ${currentWhatsappPhone} as the sender phone if you confirm it, or you can send a different sender number.`
      : "Please also send the sender phone number.",
  ].join("\n");
}

export function buildPendingOrderSummaryFingerprint(
  entry: PersistedConversationControllerEntry | null,
): string | null {
  if (!entry) {
    return null;
  }
  const normalizeAddressPart = (value: unknown) =>
    String(value ?? "")
      .trim()
      .toLowerCase()
      .replace(/^(block|street|house|building)\s+/i, "")
      .trim();
  const normalized = {
    sender_name: String(entry.bookingDraft.senderName ?? "").trim().toLowerCase(),
    sender_phone: String(entry.bookingDraft.senderPhone ?? "").replace(/\D/g, ""),
    recipient_name: String(entry.bookingDraft.recipientName ?? "").trim().toLowerCase(),
    recipient_phone: String(entry.bookingDraft.recipientPhone ?? "").replace(/\D/g, ""),
    delivery_type: String(entry.selectedDeliveryType ?? "").trim().toLowerCase(),
    quoted_price: Number(entry.quotedPrice ?? 0).toFixed(3),
    pickup_block: normalizeAddressPart(entry.bookingDraft.pickupBlock),
    pickup_street: normalizeAddressPart(entry.bookingDraft.pickupStreet),
    pickup_house: normalizeAddressPart(entry.bookingDraft.pickupHouse),
    pickup_location: hasStructuredBookingLocation(entry.bookingDraft.pickupLocation)
      ? [
          entry.bookingDraft.pickupLocation?.source || "",
          entry.bookingDraft.pickupLocation?.latitude?.toFixed(6) || "",
          entry.bookingDraft.pickupLocation?.longitude?.toFixed(6) || "",
        ].join(":")
      : "",
    delivery_block: normalizeAddressPart(entry.bookingDraft.deliveryBlock),
    delivery_street: normalizeAddressPart(entry.bookingDraft.deliveryStreet),
    delivery_house: normalizeAddressPart(entry.bookingDraft.deliveryHouse),
    delivery_location: hasStructuredBookingLocation(entry.bookingDraft.deliveryLocation)
      ? [
          entry.bookingDraft.deliveryLocation?.source || "",
          entry.bookingDraft.deliveryLocation?.latitude?.toFixed(6) || "",
          entry.bookingDraft.deliveryLocation?.longitude?.toFixed(6) || "",
        ].join(":")
      : "",
  };
  return createHash("sha256").update(JSON.stringify(normalized)).digest("hex");
}

export function formatSummaryAreaLine(params: {
  language: "ar" | "en";
  area: string | null;
  block: string | null;
  street: string | null;
  house: string | null;
  location: PersistedBookingLocation | null | undefined;
}): string {
  const locationLabel = formatPersistedBookingLocationLabel(params.location);
  if (locationLabel) {
    return [
      params.area || "-",
      params.language === "ar" ? `الموقع: ${locationLabel}` : `Location: ${locationLabel}`,
      params.house ? (params.language === "ar" ? `الوحدة: ${params.house}` : `Unit: ${params.house}`) : null,
    ]
      .filter(Boolean)
      .join(", ");
  }
  return [
    params.area || "-",
    params.block ? (params.language === "ar" ? `قطعة ${params.block}` : `Block ${params.block}`) : null,
    params.street ? (params.language === "ar" ? `شارع ${params.street}` : `Street ${params.street}`) : null,
    params.house ? (params.language === "ar" ? `منزل ${params.house}` : `House ${params.house}`) : null,
  ]
    .filter(Boolean)
    .join(", ");
}
