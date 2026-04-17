#!/usr/bin/env node
/**
 * Eval harness for the ONE-BRAIN foundations.
 *
 * Verifies that the two building blocks that matter most — booking-draft
 * patching and order-guard rejections — handle the bugs surfaced during
 * live testing before we flip RIDERS_ONE_BRAIN=1 for real customers.
 *
 *   Bug 1: service downgraded silently (covered by guard price_mismatch)
 *   Bug 2: sender phone truncated to last 8 digits (applyBookingFieldPatch
 *          now keeps the full WhatsApp number on use_whatsapp)
 *   Bug 3: delivery area silently swapped (covered by guard route_mismatch)
 *   Bug 4: no mismatch detection when user address ≠ route (covered by
 *          route_mismatch + confirmation_missing combo)
 *
 * Run: node delivery/scripts/eval-one-brain.mjs
 */
import path from "node:path";
import fs from "node:fs";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function loadTs(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"));
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return jiti(path.join(root, relativePath));
}

function ok(label) {
  console.log(`PASS ${label}`);
}
function bad(label, detail) {
  console.error(`FAIL ${label} :: ${detail}`);
  process.exitCode = 1;
}
function assertEqual(label, actual, expected) {
  if (actual === expected) {
    ok(label);
  } else {
    bad(label, `expected=${JSON.stringify(expected)} actual=${JSON.stringify(actual)}`);
  }
}
function assertTrue(label, condition, detail) {
  if (condition) {
    ok(label);
  } else {
    bad(label, detail || "condition false");
  }
}

async function main() {
  const bd = loadTs("plugins/shared/booking-draft.ts");
  const og = loadTs("plugins/shared/order-guard.ts");
  const ov = loadTs("plugins/shared/outbound-verify.ts");
  const fp = loadTs("plugins/shared/fast-path-extractor.ts");

  const {
    applyBookingFieldPatch,
    createEmptyBookingDraft,
    validateDraftForOrder,
    cleanPhone,
    cleanName,
  } = bd;
  const { guardCreateSimpleOrder, looksLikeConfirmation } = og;
  const {
    classifyOutboundReplyShape,
    verifyAndRepairOutbound,
    buildDeterministicOrderSummary,
  } = ov;
  const {
    extractForNextAction,
    extractAddressForRole,
    extractSenderPhone,
    extractSenderNameAndDecision,
    extractRecipientNameAndPhone,
    normalizeArabicDigits,
  } = fp;

  // --- Bug 2: whatsapp number full-length on use_whatsapp -------------------
  {
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: { phone_decision: "use_whatsapp", sender_name: "Aziz" },
      whatsappNumber: "96599338566",
    });
    assertEqual(
      "bug2.phone_decision.use_whatsapp keeps full 11-digit number",
      result.draft.senderPhone,
      "96599338566",
    );
    assertEqual("bug2.sender_name applied", result.draft.senderName, "Aziz");
  }

  // --- Address role: pickup vs delivery disambiguation ----------------------
  {
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: {
        address_block: "12",
        address_street: "5",
        address_house: "23",
        address_role: "pickup",
      },
    });
    assertEqual("address_role.pickup sets pickupBlock", result.draft.pickupBlock, "12");
    assertEqual("address_role.pickup leaves deliveryBlock null", result.draft.deliveryBlock, null);
  }
  {
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: {
        address_block: "1",
        address_street: "3",
        address_house: "11",
        address_role: "delivery",
      },
    });
    assertEqual("address_role.delivery sets deliveryBlock", result.draft.deliveryBlock, "1");
    assertEqual("address_role.delivery leaves pickupBlock null", result.draft.pickupBlock, null);
  }

  // --- Kuwait address schema: avenue (jadda/jedda) + extra ------------------
  {
    // Classic Kuwait compound message: "farwaniya block 6, street 9, house 17,
    // jedda 9, floor 2" — all five parts must land on the delivery side.
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: {
        address_block: "6",
        address_street: "9",
        address_house: "17",
        address_avenue: "9",
        address_extra: "Floor 2",
        address_role: "delivery",
      },
    });
    assertEqual("kuwait.delivery.block", result.draft.deliveryBlock, "6");
    assertEqual("kuwait.delivery.street", result.draft.deliveryStreet, "9");
    assertEqual("kuwait.delivery.house", result.draft.deliveryHouse, "17");
    assertEqual("kuwait.delivery.avenue (jedda/jadda)", result.draft.deliveryAvenue, "9");
    assertEqual("kuwait.delivery.extra (floor 2)", result.draft.deliveryExtra, "Floor 2");
    assertEqual("kuwait.delivery does not leak to pickup", result.draft.pickupAvenue, null);
  }

  {
    // Arabic idiom: "الدور الثاني، شقة ٨" as extra, with a pickup role.
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: {
        address_extra: "الدور الثاني، شقة ٨",
        address_role: "pickup",
      },
    });
    assertEqual(
      "kuwait.pickup.extra (arabic floor/apt)",
      result.draft.pickupExtra,
      "الدور الثاني، شقة ٨",
    );
  }

  {
    // address_extra alone with artifact → rejected.
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: { address_extra: "ok", address_role: "delivery" },
    });
    assertTrue(
      "kuwait.extra.artifact rejected",
      result.rejected.some((r) => r.field === "address_extra"),
      JSON.stringify(result.rejected),
    );
  }

  {
    // address_extra longer than 200 chars → rejected.
    const longString = "x".repeat(250);
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: { address_extra: longString, address_role: "delivery" },
    });
    assertTrue(
      "kuwait.extra.too_long rejected",
      result.rejected.some((r) => r.field === "address_extra"),
      JSON.stringify(result.rejected),
    );
  }

  {
    // avenue without role should NOT apply (same contract as block/street/house).
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: { address_avenue: "9" },
    });
    assertEqual(
      "kuwait.avenue.without_role stays null (pickup)",
      result.draft.pickupAvenue,
      null,
    );
    assertEqual(
      "kuwait.avenue.without_role stays null (delivery)",
      result.draft.deliveryAvenue,
      null,
    );
  }

  {
    // Landmark in English as extra for pickup.
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: {
        address_extra: "next to the mosque, Apt 12",
        address_role: "pickup",
      },
    });
    assertEqual(
      "kuwait.pickup.extra (english landmark)",
      result.draft.pickupExtra,
      "next to the mosque, Apt 12",
    );
  }

  // --- Phase-1 guard: address_house interior-detail reroute -----------------
  // When the LLM drifts and puts an apartment / floor / door / Arabic equivalent
  // into address_house, the patch must (1) leave house null, (2) move the value
  // into address_extra, (3) emit a rejection reason so the LLM knows.
  {
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: {
        address_house: "door 312",
        address_role: "delivery",
      },
    });
    assertEqual("reroute.house.door leaves house null", result.draft.deliveryHouse, null);
    assertEqual("reroute.house.door lands in extra", result.draft.deliveryExtra, "door 312");
    assertTrue(
      "reroute.house.door reason emitted",
      result.rejected.some(
        (r) => r.field === "address_house" && r.reason === "address_house_is_interior_detail",
      ),
      JSON.stringify(result.rejected),
    );
  }

  {
    // Merge case: existing extra + interior-detail in house → concatenated.
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: {
        address_house: "apt 5",
        address_extra: "Floor 2",
        address_role: "pickup",
      },
    });
    assertEqual("reroute.house.merge leaves house null", result.draft.pickupHouse, null);
    assertEqual(
      "reroute.house.merge concatenates with extra",
      result.draft.pickupExtra,
      "Floor 2, apt 5",
    );
  }

  {
    // Arabic شقة (apartment) mis-routed to house.
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: {
        address_house: "شقة ٨",
        address_role: "delivery",
      },
    });
    assertEqual("reroute.house.arabic_apt leaves house null", result.draft.deliveryHouse, null);
    assertEqual(
      "reroute.house.arabic_apt lands in extra",
      result.draft.deliveryExtra,
      "شقة ٨",
    );
  }

  {
    // Legitimate building number still lands in house.
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: {
        address_house: "17",
        address_role: "delivery",
      },
    });
    assertEqual("reroute.house.legit_building stays in house", result.draft.deliveryHouse, "17");
    assertEqual(
      "reroute.house.legit_building does not leak to extra",
      result.draft.deliveryExtra,
      null,
    );
  }

  {
    // "villa 4" — villa is a BUILDING descriptor, must stay in house.
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: {
        address_house: "villa 4",
        address_role: "pickup",
      },
    });
    assertEqual("reroute.house.villa stays in house", result.draft.pickupHouse, "villa 4");
  }

  // --- Rejections: artifact text as name ------------------------------------
  {
    const result = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: { sender_name: "Ok", sender_phone: "thenumber is" },
    });
    assertTrue(
      "artifact name rejected",
      result.rejected.some((r) => r.field === "sender_name"),
      JSON.stringify(result.rejected),
    );
    assertTrue(
      "artifact phone rejected",
      result.rejected.some((r) => r.field === "sender_phone"),
      JSON.stringify(result.rejected),
    );
    assertEqual("rejected draft keeps empty sender", result.draft.senderName, null);
  }

  // --- cleanPhone / cleanName basics ----------------------------------------
  assertEqual("cleanPhone strips spaces and +965 prefix stays", cleanPhone("+965 9472 8472").value, "96594728472");
  assertEqual("cleanPhone rejects letters", cleanPhone("94AB8472").value, null);
  assertEqual("cleanPhone too short null", cleanPhone("1234").value, null);
  assertEqual("cleanName rejects digits-only", cleanName("12345").value, null);
  assertEqual("cleanName keeps apostrophe", cleanName("O'Brien").value, "O'Brien");

  // --- validateDraftForOrder: incomplete + invalid --------------------------
  {
    const draft = createEmptyBookingDraft();
    const v = validateDraftForOrder(draft);
    assertEqual("empty draft invalid", v.ok, false);
    if (!v.ok) {
      assertTrue(
        "empty draft missing sender_name",
        v.missing.includes("sender_name"),
        JSON.stringify(v.missing),
      );
    }
  }

  // --- Fully valid draft passes the draft check -----------------------------
  const fullDraft = {
    senderName: "Aziz",
    senderPhone: "96599338566",
    recipientName: "Ahmad",
    recipientPhone: "59384581",
    pickupBlock: "1",
    pickupStreet: "5",
    pickupHouse: "23",
    pickupAvenue: null,
    pickupExtra: null,
    pickupLocation: null,
    deliveryBlock: "1",
    deliveryStreet: "3",
    deliveryHouse: "11",
    deliveryAvenue: null,
    deliveryExtra: null,
    deliveryLocation: null,
    pendingLocation: null,
  };
  {
    const v = validateDraftForOrder(fullDraft);
    assertEqual("full draft valid", v.ok, true);
  }

  // Validation of a complete draft that also has avenue + extra should still pass.
  {
    const draft = {
      ...fullDraft,
      deliveryAvenue: "9",
      deliveryExtra: "Floor 2, Apt 5, next to the mosque",
    };
    const v = validateDraftForOrder(draft);
    assertEqual("kuwait.validate_full_with_avenue_extra ok", v.ok, true);
  }

  // --- looksLikeConfirmation -----------------------------------------------
  assertEqual("'yes' is confirmation", looksLikeConfirmation("yes"), true);
  assertEqual("'go ahead' is confirmation", looksLikeConfirmation("go ahead please"), true);
  assertEqual("'تمام' is confirmation", looksLikeConfirmation("تمام"), true);
  assertEqual("'what about express?' is NOT confirmation", looksLikeConfirmation("what about express?"), false);
  assertEqual("empty string is NOT confirmation", looksLikeConfirmation(""), false);

  // --- guardCreateSimpleOrder: draft_incomplete -----------------------------
  {
    const result = guardCreateSimpleOrder({
      draft: createEmptyBookingDraft(),
      pickupAreaNameEn: "Salwa",
      dropoffAreaNameEn: "Qadsiya",
      deliveryType: "sedan_normal",
      quotedPrice: 1.75,
      visibleCustomerText: "yes",
      lastQuotedRoute: null,
    });
    assertEqual("guard.draft_incomplete code", result.ok ? "ok" : result.code, "draft_incomplete");
  }

  // --- guardCreateSimpleOrder: confirmation_missing -------------------------
  {
    const quote = {
      routeKey: "salwa_qadsiya",
      pickupAreaNameEn: "Salwa",
      pickupAreaNameAr: "سلوى",
      dropoffAreaNameEn: "Qadsiya",
      dropoffAreaNameAr: "القادسية",
      pricesByType: { sedan_normal: 1.75, sedan_fast: 2.25 },
      optionCatalog: [],
      serviceDiscovery: null,
      quotedAt: Date.now(),
      quoteRef: "q1",
    };
    const result = guardCreateSimpleOrder({
      draft: fullDraft,
      pickupAreaNameEn: "Salwa",
      dropoffAreaNameEn: "Qadsiya",
      deliveryType: "sedan_normal",
      quotedPrice: 1.75,
      visibleCustomerText: "what about express?",
      lastQuotedRoute: quote,
    });
    assertEqual("guard.confirmation_missing code", result.ok ? "ok" : result.code, "confirmation_missing");
  }

  // --- guardCreateSimpleOrder: no_live_quote --------------------------------
  {
    const result = guardCreateSimpleOrder({
      draft: fullDraft,
      pickupAreaNameEn: "Salwa",
      dropoffAreaNameEn: "Qadsiya",
      deliveryType: "sedan_normal",
      quotedPrice: 1.75,
      visibleCustomerText: "yes",
      lastQuotedRoute: null,
    });
    assertEqual("guard.no_live_quote code", result.ok ? "ok" : result.code, "no_live_quote");
  }

  // --- guardCreateSimpleOrder: route_mismatch (bug 3/4) ---------------------
  {
    const quote = {
      routeKey: "salwa_qadsiya",
      pickupAreaNameEn: "Salwa",
      pickupAreaNameAr: "سلوى",
      dropoffAreaNameEn: "Qadsiya",
      dropoffAreaNameAr: "القادسية",
      pricesByType: { sedan_normal: 1.75 },
      optionCatalog: [],
      serviceDiscovery: null,
      quotedAt: Date.now(),
      quoteRef: "q1",
    };
    const result = guardCreateSimpleOrder({
      draft: fullDraft,
      pickupAreaNameEn: "Salwa",
      dropoffAreaNameEn: "Salmiya", // customer's delivery area differs from quote
      deliveryType: "sedan_normal",
      quotedPrice: 1.75,
      visibleCustomerText: "yes proceed",
      lastQuotedRoute: quote,
    });
    assertEqual("guard.route_mismatch code (bug3/4)", result.ok ? "ok" : result.code, "route_mismatch");
  }

  // --- guardCreateSimpleOrder: service_not_quoted (bug 1 variant) -----------
  {
    const quote = {
      routeKey: "salwa_qadsiya",
      pickupAreaNameEn: "Salwa",
      pickupAreaNameAr: "سلوى",
      dropoffAreaNameEn: "Qadsiya",
      dropoffAreaNameAr: "القادسية",
      pricesByType: { sedan_normal: 1.75 },
      optionCatalog: [],
      serviceDiscovery: null,
      quotedAt: Date.now(),
      quoteRef: "q1",
    };
    const result = guardCreateSimpleOrder({
      draft: fullDraft,
      pickupAreaNameEn: "Salwa",
      dropoffAreaNameEn: "Qadsiya",
      deliveryType: "sedan_fast", // not in pricesByType
      quotedPrice: 2.25,
      visibleCustomerText: "yes",
      lastQuotedRoute: quote,
    });
    assertEqual("guard.service_not_quoted code", result.ok ? "ok" : result.code, "service_not_quoted");
  }

  // --- guardCreateSimpleOrder: price_mismatch (bug 1) -----------------------
  {
    const quote = {
      routeKey: "salmiya_salmiya",
      pickupAreaNameEn: "Salmiya",
      pickupAreaNameAr: "السالمية",
      dropoffAreaNameEn: "Salmiya",
      dropoffAreaNameAr: "السالمية",
      pricesByType: { sedan_normal: 10.0, sedan_fast: 15.0 },
      optionCatalog: [],
      serviceDiscovery: null,
      quotedAt: Date.now(),
      quoteRef: "q2",
    };
    const result = guardCreateSimpleOrder({
      draft: fullDraft,
      pickupAreaNameEn: "Salmiya",
      dropoffAreaNameEn: "Salmiya",
      deliveryType: "sedan_fast",
      quotedPrice: 10.0, // old standard price instead of 15.0 express
      visibleCustomerText: "yes",
      lastQuotedRoute: quote,
    });
    assertEqual("guard.price_mismatch code (bug1)", result.ok ? "ok" : result.code, "price_mismatch");
  }

  // --- guardCreateSimpleOrder: happy path -----------------------------------
  {
    const quote = {
      routeKey: "salwa_qadsiya",
      pickupAreaNameEn: "Salwa",
      pickupAreaNameAr: "سلوى",
      dropoffAreaNameEn: "Qadsiya",
      dropoffAreaNameAr: "القادسية",
      pricesByType: { sedan_normal: 1.75, sedan_fast: 2.25 },
      optionCatalog: [],
      serviceDiscovery: null,
      quotedAt: Date.now(),
      quoteRef: "q1",
    };
    const result = guardCreateSimpleOrder({
      draft: fullDraft,
      pickupAreaNameEn: "Salwa",
      dropoffAreaNameEn: "Qadsiya",
      deliveryType: "sedan_normal",
      quotedPrice: 1.75,
      visibleCustomerText: "yes proceed",
      lastQuotedRoute: quote,
    });
    assertEqual("guard.happy_path ok", result.ok, true);
  }

  // --- Phase-2: Output verification loop ------------------------------------
  const buildEntry = (overrides = {}) => ({
    lastActivityTs: Date.now(),
    language: "en",
    explicitLanguage: null,
    stage: "quoted",
    bookingStep: "collecting_details",
    conversationId: "c1",
    replyTarget: "96599338566",
    accountId: "default",
    quoteRouteKey: "jabriya_surra",
    quoteTs: Date.now(),
    quotePickupAreaNameEn: "Jabriya",
    quotePickupAreaNameAr: "الجابرية",
    quoteDropoffAreaNameEn: "Surra",
    quoteDropoffAreaNameAr: "الصرة",
    selectedQuoteOptionType: "sedan_normal",
    selectedQuoteOptionLabelAr: null,
    selectedQuoteOptionLabelEn: null,
    selectedQuoteOptionPrice: 1.25,
    selectedQuoteOptionDirectChatBookingStatus: null,
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
    bookingDraft: {
      senderName: "Aziz Almulla",
      senderPhone: "96594728472",
      recipientName: "Ahmad Basha",
      recipientPhone: "96562844738",
      pickupBlock: "5",
      pickupStreet: "7",
      pickupHouse: "19",
      pickupAvenue: null,
      pickupExtra: null,
      pickupLocation: null,
      deliveryBlock: "6",
      deliveryStreet: "9",
      deliveryHouse: "17",
      deliveryAvenue: null,
      deliveryExtra: null,
      deliveryLocation: null,
      pendingLocation: null,
    },
    ...overrides,
  });

  // Classifier: stub summary when draft complete.
  {
    const shape = classifyOutboundReplyShape({
      replyText: "Delivery from Jabriya to Surra\nPrice: 1.250 KWD (standard sedan)",
      entry: buildEntry(),
      missingFields: [],
      language: "en",
    });
    assertEqual("verify.classify.route_recap_when_complete", shape, "route_price_recap");
  }

  // Classifier: standalone ack is caught.
  {
    const shape = classifyOutboundReplyShape({
      replyText: "Sure.",
      entry: buildEntry(),
      missingFields: ["delivery.address"],
      language: "en",
    });
    assertEqual("verify.classify.standalone_ack", shape, "standalone_ack");
  }

  // Classifier: a real full summary passes.
  {
    const realSummary =
      "*Order summary*\nPickup: Jabriya — Block 5, Street 7, House 19\nDelivery: Surra — Block 6, Street 9, House 17\nSender: Aziz Almulla — 96594728472\nRecipient: Ahmad Basha — 96562844738\nService: Standard sedan\nPrice: 1.250 KWD\n\nShall I confirm this order?";
    const shape = classifyOutboundReplyShape({
      replyText: realSummary,
      entry: buildEntry(),
      missingFields: [],
      language: "en",
    });
    assertEqual("verify.classify.full_summary_passes", shape, "ok");
  }

  // Classifier: stub summary (missing key fields) when complete draft.
  {
    const shape = classifyOutboundReplyShape({
      replyText: "All set, ready to confirm?",
      entry: buildEntry(),
      missingFields: [],
      language: "en",
    });
    assertEqual("verify.classify.stub_summary_when_complete", shape, "stub_summary");
  }

  // Classifier: no booking started (pre-quote) → ok.
  {
    const shape = classifyOutboundReplyShape({
      replyText: "Delivery from Jabriya to Surra, 1.250 KWD for standard sedan. Want to book?",
      entry: buildEntry({ selectedDeliveryType: null, quotedPrice: null }),
      missingFields: ["sender.name"],
      language: "en",
    });
    assertEqual("verify.classify.prequote_passes", shape, "ok");
  }

  // Classifier: recap + explicit next-step ask = legit first-collection turn.
  // Bug: was flagging "Delivery from A to B is 1.250 KWD. If you want to book,
  // send us the sender name and phone number" as route_price_recap even though
  // it contains an explicit ask. Fix: presence of an imperative / question
  // mark suppresses the flag.
  {
    const shape = classifyOutboundReplyShape({
      replyText:
        "Delivery from Abu Ftaira to Al Masayel is 1.250 KWD for standard sedan. If you want to book it, send us the sender name and phone number.",
      entry: buildEntry({
        bookingDraft: {
          ...buildEntry().bookingDraft,
          senderName: null,
          senderPhone: null,
          recipientName: null,
          recipientPhone: null,
          pickupBlock: null,
          pickupStreet: null,
          pickupHouse: null,
          deliveryBlock: null,
          deliveryStreet: null,
          deliveryHouse: null,
        },
      }),
      missingFields: [
        "sender.name",
        "sender.phone",
        "recipient.name",
        "recipient.phone",
        "pickup.address",
        "delivery.address",
      ],
      language: "en",
    });
    assertEqual("verify.classify.recap_plus_ask_is_ok", shape, "ok");
  }

  // Classifier: same recap + ask in Arabic = also legit.
  {
    const shape = classifyOutboundReplyShape({
      replyText:
        "التوصيل من الجابرية إلى الصرة 1.250 د.ك سيدان عادي. أرسل اسم المرسل ورقم الهاتف.",
      entry: buildEntry({
        bookingDraft: {
          ...buildEntry().bookingDraft,
          senderName: null,
          senderPhone: null,
          recipientName: null,
          recipientPhone: null,
          pickupBlock: null,
          pickupStreet: null,
          pickupHouse: null,
          deliveryBlock: null,
          deliveryStreet: null,
          deliveryHouse: null,
        },
      }),
      missingFields: ["sender.name", "sender.phone"],
      language: "ar",
    });
    assertEqual("verify.classify.recap_plus_ask_ar_is_ok", shape, "ok");
  }

  // Classifier: bare recap with NO ask is still flagged mid-booking.
  {
    const shape = classifyOutboundReplyShape({
      replyText: "Delivery from Jabriya to Surra, 1.250 KWD.",
      entry: buildEntry({
        bookingDraft: {
          ...buildEntry().bookingDraft,
          senderName: "Aziz Almulla",
          senderPhone: null,
          recipientName: null,
          recipientPhone: null,
          pickupBlock: null,
          pickupStreet: null,
          pickupHouse: null,
          deliveryBlock: null,
          deliveryStreet: null,
          deliveryHouse: null,
        },
      }),
      missingFields: ["sender.phone", "recipient.name"],
      language: "en",
    });
    assertEqual("verify.classify.bare_recap_no_ask_flagged", shape, "route_price_recap");
  }

  // Repair: stub summary → substituted full canonical summary (EN).
  {
    const result = verifyAndRepairOutbound({
      replyText: "All set, ready to confirm?",
      entry: buildEntry(),
      missingFields: [],
      language: "en",
    });
    assertEqual("verify.repair.replaced", result.replaced, true);
    assertTrue(
      "verify.repair.contains_sender",
      result.replyText.includes("Aziz Almulla"),
      result.replyText,
    );
    assertTrue(
      "verify.repair.contains_recipient",
      result.replyText.includes("Ahmad Basha"),
      result.replyText,
    );
    assertTrue(
      "verify.repair.contains_price",
      result.replyText.includes("1.250"),
      result.replyText,
    );
    assertTrue(
      "verify.repair.contains_pickup_address",
      result.replyText.includes("Block 5") && result.replyText.includes("House 19"),
      result.replyText,
    );
  }

  // Repair: route recap in complete state → substituted.
  {
    const result = verifyAndRepairOutbound({
      replyText: "Delivery from Jabriya to Surra\nPrice: 1.250 KWD",
      entry: buildEntry(),
      missingFields: [],
      language: "en",
    });
    assertEqual("verify.repair.route_recap_replaced", result.replaced, true);
    assertTrue(
      "verify.repair.route_recap_new_reply_is_full",
      result.replyText.includes("Aziz Almulla") && result.replyText.includes("Ahmad Basha"),
      result.replyText,
    );
  }

  // Repair: does NOT interfere during mid-collection.
  {
    const result = verifyAndRepairOutbound({
      replyText: "Sure.",
      entry: buildEntry(),
      missingFields: ["delivery.address"],
      language: "en",
    });
    assertEqual("verify.repair.midcollection_no_substitute", result.replaced, false);
    assertEqual("verify.repair.midcollection_keeps_original", result.replyText, "Sure.");
  }

  // Repair: Arabic canonical summary.
  {
    const result = verifyAndRepairOutbound({
      replyText: "Ready?",
      entry: buildEntry(),
      missingFields: [],
      language: "ar",
    });
    assertEqual("verify.repair.arabic_replaced", result.replaced, true);
    assertTrue(
      "verify.repair.arabic_uses_arabic_labels",
      result.replyText.includes("المرسل") && result.replyText.includes("د.ك"),
      result.replyText,
    );
  }

  // Repair: no substitute when draft incomplete.
  {
    const result = verifyAndRepairOutbound({
      replyText: "All set, ready to confirm?",
      entry: buildEntry({
        bookingDraft: {
          ...buildEntry().bookingDraft,
          recipientName: null,
        },
      }),
      missingFields: ["recipient.name"],
      language: "en",
    });
    assertEqual("verify.repair.incomplete_no_substitute", result.replaced, false);
  }

  // Deterministic summary: includes pickup avenue + extra when present.
  {
    const entry = buildEntry({
      bookingDraft: {
        ...buildEntry().bookingDraft,
        pickupAvenue: "9",
        pickupExtra: "Floor 2, Apt 12",
      },
    });
    const text = buildDeterministicOrderSummary({ entry, language: "en" });
    assertTrue(
      "verify.summary.contains_avenue",
      text.includes("Jedda 9"),
      text,
    );
    assertTrue(
      "verify.summary.contains_extra",
      text.includes("Floor 2, Apt 12"),
      text,
    );
  }

  // ==========================================================================
  // Structured-summary bar. Even when a reply mentions every booking field,
  // it must be written as labeled rows on separate lines — not as prose. A
  // paragraph-style summary with all the content but no structure fails the
  // classifier and gets substituted with the canonical layout. This is what
  // fixes the "booking summary looked like a paragraph" bug.
  // ==========================================================================

  // Case S-A: paragraph summary with every field baked into prose → stub_summary.
  {
    const paragraph =
      "Delivery from Jabriya to Surra for Aziz Almulla (96594728472) to Ahmad Basha (96562844738), standard sedan, 1.250 KWD. Confirm?";
    const shape = classifyOutboundReplyShape({
      replyText: paragraph,
      entry: buildEntry(),
      missingFields: [],
      language: "en",
    });
    assertEqual(
      "verify.structure.paragraph_with_all_fields_is_stub",
      shape,
      "stub_summary",
    );
  }

  // Case S-B: same paragraph gets substituted with a structured canonical
  // summary by the repair pass.
  {
    const paragraph =
      "Delivery from Jabriya to Surra for Aziz Almulla (96594728472) to Ahmad Basha (96562844738), standard sedan, 1.250 KWD. Confirm?";
    const result = verifyAndRepairOutbound({
      replyText: paragraph,
      entry: buildEntry(),
      missingFields: [],
      language: "en",
    });
    assertEqual("verify.structure.paragraph_substituted", result.replaced, true);
    const replaced = result.replyText;
    const lineCount = replaced
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean).length;
    assertTrue(
      "verify.structure.substitute_is_multiline",
      lineCount >= 6,
      replaced,
    );
    assertTrue(
      "verify.structure.substitute_has_pickup_row",
      /^Pickup:\s/m.test(replaced),
      replaced,
    );
    assertTrue(
      "verify.structure.substitute_has_price_row",
      /^Price:\s/m.test(replaced),
      replaced,
    );
  }

  // Case S-C: comma-joined summary on one line (labels present but no
  // newlines) → stub_summary. Catches "Pickup: Jabriya, Delivery: Surra,
  // Sender: Aziz..." style dumps.
  {
    const oneLine =
      "Pickup: Jabriya — Block 5, Street 7, House 19, Delivery: Surra — Block 6, Street 9, House 17, Sender: Aziz Almulla — 96594728472, Recipient: Ahmad Basha — 96562844738, Service: Standard sedan, Price: 1.250 KWD. Confirm?";
    const shape = classifyOutboundReplyShape({
      replyText: oneLine,
      entry: buildEntry(),
      missingFields: [],
      language: "en",
    });
    assertEqual("verify.structure.one_line_labeled_is_stub", shape, "stub_summary");
  }

  // Case S-D: canonical structured summary passes (control: we didn't regress
  // the happy path by tightening the structural bar).
  {
    const structured =
      "*Order summary*\nPickup: Jabriya — Block 5, Street 7, House 19\nDelivery: Surra — Block 6, Street 9, House 17\nSender: Aziz Almulla — 96594728472\nRecipient: Ahmad Basha — 96562844738\nService: Standard sedan\nPrice: 1.250 KWD\n\nShall I confirm this order?";
    const shape = classifyOutboundReplyShape({
      replyText: structured,
      entry: buildEntry(),
      missingFields: [],
      language: "en",
    });
    assertEqual("verify.structure.canonical_passes", shape, "ok");
  }

  // Case S-E: Arabic structured summary with `الاستلام:` / `التسليم:` labels
  // passes (structural bar is language-aware).
  {
    const structuredAr =
      "*ملخص الطلب*\nالاستلام: الجابرية — قطعة 5، شارع 7، منزل 19\nالتسليم: الصرة — قطعة 6، شارع 9، منزل 17\nالمرسل: عزيز الملا — 96594728472\nالمستلم: أحمد باشا — 96562844738\nالخدمة: سيدان عادي\nالسعر: 1.250 د.ك\n\nأأكد الطلب؟";
    const shape = classifyOutboundReplyShape({
      replyText: structuredAr,
      entry: buildEntry(),
      missingFields: [],
      language: "ar",
    });
    assertEqual("verify.structure.arabic_canonical_passes", shape, "ok");
  }

  // Case S-F: list-marker summary (bullets / dashes before labels) still
  // passes — LLM sometimes renders with "- Pickup: ..." style.
  {
    const bulletStyle =
      "*Order summary*\n- Pickup: Jabriya — Block 5, Street 7, House 19\n- Delivery: Surra — Block 6, Street 9, House 17\n- Sender: Aziz Almulla — 96594728472\n- Recipient: Ahmad Basha — 96562844738\n- Service: Standard sedan\n- Price: 1.250 KWD\n\nShall I confirm this order?";
    const shape = classifyOutboundReplyShape({
      replyText: bulletStyle,
      entry: buildEntry(),
      missingFields: [],
      language: "en",
    });
    assertEqual("verify.structure.bullet_style_passes", shape, "ok");
  }

  // --- Phase-3: Fast-path extractor -----------------------------------------

  // Arabic digits normalization.
  assertEqual(
    "fast.normalize_arabic_digits",
    normalizeArabicDigits("٥،٧،١٩"),
    "5،7،19",
  );

  // Bare triplet: "5, 7, 19" → pickup block/street/house.
  {
    const r = extractAddressForRole({ text: "5, 7, 19", role: "pickup" });
    assertEqual("fast.bare_triplet.confidence", r.confidence, "high");
    assertEqual("fast.bare_triplet.block", r.patch.address_block, "5");
    assertEqual("fast.bare_triplet.street", r.patch.address_street, "7");
    assertEqual("fast.bare_triplet.house", r.patch.address_house, "19");
    assertEqual("fast.bare_triplet.role", r.patch.address_role, "pickup");
    assertEqual("fast.bare_triplet.avenue", r.patch.address_avenue, null);
  }

  // Bare triplet with spaces only: "5 7 19".
  {
    const r = extractAddressForRole({ text: "5 7 19", role: "delivery" });
    assertEqual("fast.bare_triplet.spaces_only.conf", r.confidence, "high");
    assertEqual("fast.bare_triplet.spaces_only.role", r.patch.address_role, "delivery");
  }

  // Bare quad: "5, 7, 9, 19" → block/street/avenue/house.
  {
    const r = extractAddressForRole({ text: "5, 7, 9, 19", role: "pickup" });
    assertEqual("fast.bare_quad.conf", r.confidence, "high");
    assertEqual("fast.bare_quad.avenue", r.patch.address_avenue, "9");
    assertEqual("fast.bare_quad.house", r.patch.address_house, "19");
  }

  // Arabic digits triplet: "٥،٧،١٩".
  {
    const r = extractAddressForRole({ text: "٥،٧،١٩", role: "pickup" });
    assertEqual("fast.arabic_digits.conf", r.confidence, "high");
    assertEqual("fast.arabic_digits.block", r.patch.address_block, "5");
    assertEqual("fast.arabic_digits.house", r.patch.address_house, "19");
  }

  // Labeled EN: "block 5, street 7, house 19".
  {
    const r = extractAddressForRole({
      text: "block 5, street 7, house 19",
      role: "pickup",
    });
    assertEqual("fast.labeled_en.conf", r.confidence, "high");
    assertEqual("fast.labeled_en.block", r.patch.address_block, "5");
    assertEqual("fast.labeled_en.street", r.patch.address_street, "7");
    assertEqual("fast.labeled_en.house", r.patch.address_house, "19");
  }

  // Labeled EN with interior reroute: "block 5 street 7 house 19 apt 12 floor 2".
  {
    const r = extractAddressForRole({
      text: "block 5 street 7 house 19 apt 12 floor 2",
      role: "delivery",
    });
    assertEqual("fast.labeled_en_with_extra.conf", r.confidence, "high");
    assertEqual("fast.labeled_en_with_extra.house", r.patch.address_house, "19");
    assertTrue(
      "fast.labeled_en_with_extra.extra",
      r.patch.address_extra && r.patch.address_extra.toLowerCase().includes("apt"),
      JSON.stringify(r.patch.address_extra),
    );
  }

  // Labeled AR: "قطعة ٥ شارع ٧ منزل ١٩".
  {
    const r = extractAddressForRole({
      text: "قطعة ٥ شارع ٧ منزل ١٩",
      role: "pickup",
    });
    assertEqual("fast.labeled_ar.conf", r.confidence, "high");
    assertEqual("fast.labeled_ar.block", r.patch.address_block, "5");
    assertEqual("fast.labeled_ar.street", r.patch.address_street, "7");
    assertEqual("fast.labeled_ar.house", r.patch.address_house, "19");
  }

  // Ambiguous: a single labeled part is insufficient.
  {
    const r = extractAddressForRole({ text: "block 5", role: "pickup" });
    assertEqual("fast.partial_label.no_confidence", r.confidence, "none");
  }

  // Ambiguous: free-form chatter must not parse.
  {
    const r = extractAddressForRole({
      text: "not sure yet, let me ask",
      role: "pickup",
    });
    assertEqual("fast.freeform.no_confidence", r.confidence, "none");
  }

  // Ambiguous: two numbers only.
  {
    const r = extractAddressForRole({ text: "5,7", role: "pickup" });
    assertEqual("fast.two_numbers.no_confidence", r.confidence, "none");
  }

  // Ambiguous: too many numbers.
  {
    const r = extractAddressForRole({ text: "5,7,19,3,2", role: "pickup" });
    assertEqual("fast.five_numbers.no_confidence", r.confidence, "none");
  }

  // Phone: pure 11-digit Kuwait number.
  {
    const r = extractSenderPhone({ text: "96594728472", whatsappNumber: null });
    assertEqual("fast.phone.pure11.conf", r.confidence, "high");
    assertEqual("fast.phone.pure11.value", r.patch.sender_phone, "96594728472");
    assertEqual("fast.phone.pure11.decision", r.patch.phone_decision, "different");
  }

  // Phone: formatted "+965 9472 8472".
  {
    const r = extractSenderPhone({ text: "+965 9472 8472", whatsappNumber: null });
    assertEqual("fast.phone.formatted.conf", r.confidence, "high");
    assertEqual("fast.phone.formatted.value", r.patch.sender_phone, "96594728472");
  }

  // Phone: "use my whatsapp" shortcut.
  {
    const r = extractSenderPhone({
      text: "use my whatsapp",
      whatsappNumber: "96599338566",
    });
    assertEqual("fast.phone.whatsapp_en.conf", r.confidence, "high");
    assertEqual("fast.phone.whatsapp_en.decision", r.patch.phone_decision, "use_whatsapp");
  }

  // Phone: Arabic "نفس رقم الواتس".
  {
    const r = extractSenderPhone({
      text: "نفس رقم الواتس",
      whatsappNumber: "96599338566",
    });
    assertEqual("fast.phone.whatsapp_ar.conf", r.confidence, "high");
    assertEqual("fast.phone.whatsapp_ar.decision", r.patch.phone_decision, "use_whatsapp");
  }

  // Phone: bare-digits-with-label "phone: 9472 8472".
  {
    const r = extractSenderPhone({ text: "phone: 9472 8472", whatsappNumber: null });
    assertEqual("fast.phone.label_prefix.conf", r.confidence, "high");
    assertEqual("fast.phone.label_prefix.value", r.patch.sender_phone, "94728472");
  }

  // Phone: free-form chatter rejected.
  {
    const r = extractSenderPhone({
      text: "can you send later",
      whatsappNumber: null,
    });
    assertEqual("fast.phone.freeform.none", r.confidence, "none");
  }

  // Recipient: "Ahmad Basha 62844738" → name + phone.
  {
    const r = extractRecipientNameAndPhone({ text: "Ahmad Basha 62844738" });
    assertEqual("fast.recipient.name_plus_phone.conf", r.confidence, "high");
    assertEqual("fast.recipient.name_plus_phone.name", r.patch.recipient_name, "Ahmad Basha");
    assertEqual("fast.recipient.name_plus_phone.phone", r.patch.recipient_phone, "62844738");
  }

  // Recipient: two phones → ambiguous, no extraction.
  {
    const r = extractRecipientNameAndPhone({
      text: "Ahmad 62844738 or 51234567",
    });
    assertEqual("fast.recipient.two_phones.none", r.confidence, "none");
  }

  // Recipient: label noise ("phone: …") bails out and lets LLM handle.
  {
    const r = extractRecipientNameAndPhone({
      text: "Ahmad phone 62844738",
    });
    assertEqual("fast.recipient.label_noise.none", r.confidence, "none");
  }

  // Recipient: no letters → not a name.
  {
    const r = extractRecipientNameAndPhone({ text: "62844738" });
    assertEqual("fast.recipient.digits_only.none", r.confidence, "none");
  }

  // Top-level dispatch honors next_required_action.
  {
    const r = extractForNextAction({
      text: "5, 7, 19",
      action: "ASK_PICKUP_ADDRESS",
      whatsappNumber: null,
    });
    assertEqual("fast.dispatch.pickup.role", r.patch.address_role, "pickup");
  }
  {
    const r = extractForNextAction({
      text: "5, 7, 19",
      action: "ASK_DELIVERY_ADDRESS",
      whatsappNumber: null,
    });
    assertEqual("fast.dispatch.delivery.role", r.patch.address_role, "delivery");
  }
  // Wrong-action input: we do NOT apply pickup address if step is phone.
  {
    const r = extractForNextAction({
      text: "5, 7, 19",
      action: "ASK_SENDER_PHONE",
      whatsappNumber: null,
    });
    // 5,7,19 is not a Kuwait phone (too few digits) → none.
    assertEqual("fast.dispatch.wrong_step.none", r.confidence, "none");
  }
  // Unknown / null action → none.
  {
    const r = extractForNextAction({
      text: "5, 7, 19",
      action: null,
      whatsappNumber: null,
    });
    assertEqual("fast.dispatch.null_action.none", r.confidence, "none");
  }

  // --- Phase-3b: Sender combined extractor ----------------------------------

  // Name + "use my whatsapp" → both extracted.
  {
    const r = extractSenderNameAndDecision({ text: "Aziz Almulla, use my whatsapp" });
    assertEqual("fast.sender.name_plus_whatsapp.conf", r.confidence, "high");
    assertEqual("fast.sender.name_plus_whatsapp.name", r.patch.sender_name, "Aziz Almulla");
    assertEqual("fast.sender.name_plus_whatsapp.decision", r.patch.phone_decision, "use_whatsapp");
    assertEqual("fast.sender.name_plus_whatsapp.no_phone", r.patch.sender_phone, undefined);
  }

  // Flipped order: marker first, then name.
  {
    const r = extractSenderNameAndDecision({ text: "use whatsapp, Aziz Almulla" });
    assertEqual("fast.sender.marker_first.conf", r.confidence, "high");
    assertEqual("fast.sender.marker_first.name", r.patch.sender_name, "Aziz Almulla");
    assertEqual("fast.sender.marker_first.decision", r.patch.phone_decision, "use_whatsapp");
  }

  // Name + "different number" + phone digits → all three extracted.
  {
    const r = extractSenderNameAndDecision({
      text: "Aziz Almulla different number 9472 8472",
    });
    assertEqual("fast.sender.name_plus_different.conf", r.confidence, "high");
    assertEqual("fast.sender.name_plus_different.name", r.patch.sender_name, "Aziz Almulla");
    assertEqual("fast.sender.name_plus_different.decision", r.patch.phone_decision, "different");
    assertEqual("fast.sender.name_plus_different.phone", r.patch.sender_phone, "94728472");
  }

  // Name + bare phone digits → decision inferred to "different".
  {
    const r = extractSenderNameAndDecision({ text: "Aziz Almulla 94728472" });
    assertEqual("fast.sender.name_plus_bare_phone.conf", r.confidence, "high");
    assertEqual("fast.sender.name_plus_bare_phone.name", r.patch.sender_name, "Aziz Almulla");
    assertEqual("fast.sender.name_plus_bare_phone.decision", r.patch.phone_decision, "different");
    assertEqual("fast.sender.name_plus_bare_phone.phone", r.patch.sender_phone, "94728472");
  }

  // Name only → decision unresolved, name captured for LLM follow-up.
  {
    const r = extractSenderNameAndDecision({ text: "Aziz Almulla" });
    assertEqual("fast.sender.name_only.conf", r.confidence, "high");
    assertEqual("fast.sender.name_only.name", r.patch.sender_name, "Aziz Almulla");
    assertEqual("fast.sender.name_only.no_decision", r.patch.phone_decision, undefined);
  }

  // use_whatsapp only → decision captured, name unresolved.
  {
    const r = extractSenderNameAndDecision({ text: "use my whatsapp" });
    assertEqual("fast.sender.whatsapp_only.conf", r.confidence, "high");
    assertEqual("fast.sender.whatsapp_only.decision", r.patch.phone_decision, "use_whatsapp");
    assertEqual("fast.sender.whatsapp_only.no_name", r.patch.sender_name, undefined);
  }

  // Arabic "نفس رقم الواتس" + name.
  {
    const r = extractSenderNameAndDecision({ text: "عبدالعزيز الملا، نفس رقم الواتس" });
    assertEqual("fast.sender.arabic_whatsapp.conf", r.confidence, "high");
    assertEqual("fast.sender.arabic_whatsapp.decision", r.patch.phone_decision, "use_whatsapp");
    assertTrue(
      "fast.sender.arabic_whatsapp.name_arabic",
      r.patch.sender_name && r.patch.sender_name.includes("عبدالعزيز"),
      JSON.stringify(r.patch.sender_name),
    );
  }

  // "different number" marker WITHOUT a phone → ambiguous, bail.
  {
    const r = extractSenderNameAndDecision({ text: "Aziz Almulla, different number" });
    assertEqual("fast.sender.different_no_phone.none", r.confidence, "none");
  }

  // Conflicting markers → bail.
  {
    const r = extractSenderNameAndDecision({
      text: "Aziz use whatsapp different number 94728472",
    });
    assertEqual("fast.sender.conflicting_markers.none", r.confidence, "none");
  }

  // Two separate phone candidates → bail.
  {
    const r = extractSenderNameAndDecision({
      text: "Aziz 94728472 or 51234567",
    });
    assertEqual("fast.sender.two_phones.none", r.confidence, "none");
  }

  // Empty string → none.
  {
    const r = extractSenderNameAndDecision({ text: "   " });
    assertEqual("fast.sender.empty.none", r.confidence, "none");
  }

  // Non-name tokens like "yes" / "ok" → no name captured.
  {
    const r = extractSenderNameAndDecision({ text: "ok" });
    assertEqual("fast.sender.bareword.none", r.confidence, "none");
  }

  // Name with digits embedded → not a clean name, reject if no marker / phone.
  {
    const r = extractSenderNameAndDecision({ text: "Aziz123" });
    assertEqual("fast.sender.name_with_digits.none", r.confidence, "none");
  }

  // Dispatch integration: ASK_SENDER_NAME_AND_PHONE_DECISION now handled.
  {
    const r = extractForNextAction({
      text: "Aziz Almulla, use my whatsapp",
      action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      whatsappNumber: "96599338566",
    });
    assertEqual("fast.dispatch.sender_combined.conf", r.confidence, "high");
    assertEqual("fast.dispatch.sender_combined.name", r.patch.sender_name, "Aziz Almulla");
    assertEqual("fast.dispatch.sender_combined.decision", r.patch.phone_decision, "use_whatsapp");
  }

  // ==========================================================================
  // Phase 4: Evidence-binding area verification (verifyAreaEvidence)
  //
  // Defends against the "messilah → Al Masayel" silent-substitution class of
  // LLM failure (agent-sourced assertion, Waqas et al. arXiv:2512.00332).
  // ==========================================================================
  {
    const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
    const pricingRaw = fs.readFileSync(
      path.join(root, "workspaces/riders/data/pricing.published.json"),
      "utf-8",
    );
    const pricing = JSON.parse(pricingRaw);
    const ridersTools = loadTs("plugins/riders-tools/index.ts");
    const { verifyAreaEvidence, resolveAreaDeterministicSync } = ridersTools.__resolverTestHooks;

    // Sanity: matcher primitives we depend on resolve known areas correctly.
    {
      const jabriya = resolveAreaDeterministicSync("Jabriya", pricing);
      assertTrue(
        "evidence.sanity.jabriya_resolves",
        jabriya?.status === "resolved" && jabriya.area.name_en === "Jabriya",
        JSON.stringify(jabriya),
      );
    }
    {
      const messilah = resolveAreaDeterministicSync("messilah", pricing);
      assertTrue(
        "evidence.sanity.messilah_does_not_resolve",
        !messilah || messilah.status !== "resolved",
        JSON.stringify(messilah),
      );
    }

    // Case A: both raw and model resolve to the same area → keep.
    {
      const decision = verifyAreaEvidence({
        rawToken: "Jabriya",
        modelValue: "Jabriya",
        idOverride: null,
        data: pricing,
      });
      assertEqual("evidence.same_area.keep", decision.action, "keep");
    }

    // Case B: Arabic raw + English model, same canonical → keep (the whole
    // point of the tool's fuzzy layer).
    {
      const decision = verifyAreaEvidence({
        rawToken: "الجابرية",
        modelValue: "Jabriya",
        idOverride: null,
        data: pricing,
      });
      assertEqual("evidence.arabic_english_match.keep", decision.action, "keep");
    }

    // Case C: both resolve but disagree → override with raw.
    {
      const decision = verifyAreaEvidence({
        rawToken: "Salmiya",
        modelValue: "Jabriya",
        idOverride: null,
        data: pricing,
      });
      assertEqual("evidence.disagreement.override", decision.action, "override");
      if (decision.action === "override") {
        assertEqual(
          "evidence.disagreement.override_value",
          decision.value,
          "Salmiya",
        );
      }
    }

    // Case D: raw resolves, model garbage → override with raw.
    {
      const decision = verifyAreaEvidence({
        rawToken: "Salmiya",
        modelValue: "NotAnArea_xyz",
        idOverride: null,
        data: pricing,
      });
      assertEqual("evidence.model_garbage.override", decision.action, "override");
      if (decision.action === "override") {
        assertEqual(
          "evidence.model_garbage.value",
          decision.value,
          "Salmiya",
        );
      }
    }

    // Case E: THE MESSILAH SMUGGLE — raw="messilah" does not resolve and
    // does not fuzzy-match Al Masayel closely enough; model claims
    // Al Masayel. MUST reject.
    {
      const decision = verifyAreaEvidence({
        rawToken: "messilah",
        modelValue: "Al Masayel",
        idOverride: null,
        data: pricing,
      });
      assertEqual("evidence.messilah_smuggle.reject", decision.action, "reject");
      if (decision.action === "reject") {
        assertEqual(
          "evidence.messilah_smuggle.rawToken",
          decision.rawToken,
          "messilah",
        );
        assertEqual(
          "evidence.messilah_smuggle.modelCanonical",
          decision.modelCanonical,
          "Al Masayel",
        );
        assertEqual(
          "evidence.messilah_smuggle.modelArea",
          decision.modelArea?.name_en,
          "Al Masayel",
        );
        // Messilah has no close typo-match for Al Masayel (distance > 2),
        // so the reason should be smuggle_not_found, not smuggle_suspected.
        assertEqual(
          "evidence.messilah_smuggle.reason",
          decision.reason,
          "smuggle_not_found",
        );
      }
    }

    // Case F: legitimate close transliteration — raw="Salmia" (typo of
    // "Salmiya"), model="Salmiya". typo-matcher should accept this and keep.
    // This protects against over-rejection of plausible user typos.
    {
      const decision = verifyAreaEvidence({
        rawToken: "Salmia",
        modelValue: "Salmiya",
        idOverride: null,
        data: pricing,
      });
      // Expected: either keep (if Salmia is a close-enough typo-match for
      // Salmiya) OR reject with smuggle_suspected pointing at Salmiya.
      // Crucially: it MUST NOT silently accept a different area.
      assertTrue(
        "evidence.close_typo.no_silent_accept",
        decision.action === "keep" || decision.action === "reject",
        JSON.stringify(decision),
      );
      if (decision.action === "reject") {
        assertEqual(
          "evidence.close_typo.suggested_is_salmiya",
          decision.suggestedArea?.name_en,
          "Salmiya",
        );
      }
    }

    // Case G: explicit area_id override skips verification (customer already
    // picked from a disambiguation list).
    {
      const decision = verifyAreaEvidence({
        rawToken: "messilah",
        modelValue: "Al Masayel",
        idOverride: 129,
        data: pricing,
      });
      assertEqual("evidence.id_override.keep", decision.action, "keep");
    }

    // Case H: no raw token (e.g. customer didn't phrase it as a route) →
    // keep; we have no evidence to check against.
    {
      const decision = verifyAreaEvidence({
        rawToken: null,
        modelValue: "Al Masayel",
        idOverride: null,
        data: pricing,
      });
      assertEqual("evidence.no_raw_token.keep", decision.action, "keep");
    }

    // Case I: neither raw nor model resolves → keep (let downstream
    // pipeline return not_found through the normal resolver path).
    {
      const decision = verifyAreaEvidence({
        rawToken: "xyzgarbage",
        modelValue: "xyzgarbage",
        idOverride: null,
        data: pricing,
      });
      assertEqual("evidence.both_garbage.keep", decision.action, "keep");
    }

    // Case J: raw is a clean area, model is different clean area → override.
    // Classic A-B disagreement.
    {
      const decision = verifyAreaEvidence({
        rawToken: "Abu Ftaira",
        modelValue: "Mubarak Al Kabeer",
        idOverride: null,
        data: pricing,
      });
      assertEqual("evidence.ab_swap.override", decision.action, "override");
      if (decision.action === "override") {
        assertEqual(
          "evidence.ab_swap.value",
          decision.value,
          "Abu Ftaira",
        );
      }
    }
  }

  // ==========================================================================
  // Phase 5: Post-order correction guardrails
  //
  // Defends against the "We've passed this to the support team" hallucination
  // plus silent writes to a dead booking draft after create_simple_order.
  // Covers:
  //   - next_required_action directive when stage=order_submitted
  //   - submitted_order_uid rendered into the one-brain system context
  //   - explicit forbidden shapes (fake_handoff_claim, field_update_without_recreate)
  // The apply_booking_field tool-level gate is exercised end-to-end by the
  // live-agent eval; here we validate the state-shaped pieces that feed it.
  // ==========================================================================
  {
    const octopus = loadTs("plugins/octopus-channel/index.ts");
    const { computeOneBrainNextRequiredAction, formatOneBrainLiveChannelContext } =
      octopus.__testables;

    const baseEntry = {
      lastActivityTs: Date.now(),
      language: "en",
      explicitLanguage: "en",
      stage: "order_submitted",
      bookingStep: "none",
      conversationId: "conv-test-po",
      replyTarget: "+96599338566",
      accountId: "acc-1",
      quoteRouteKey: null,
      quoteTs: null,
      quotePickupAreaNameEn: null,
      quotePickupAreaNameAr: null,
      quoteDropoffAreaNameEn: null,
      quoteDropoffAreaNameAr: null,
      selectedQuoteOptionType: null,
      selectedQuoteOptionLabelAr: null,
      selectedQuoteOptionLabelEn: null,
      selectedQuoteOptionPrice: null,
      selectedQuoteOptionDirectChatBookingStatus: null,
      selectedDeliveryType: null,
      quotedPrice: null,
      bookingDraft: createEmptyBookingDraft(),
      submittedOrderUid: "ORDER-ABC123",
    };

    // Case PO-A: post-order directive fires on order_submitted stage.
    {
      const directive = computeOneBrainNextRequiredAction({
        draft: baseEntry.bookingDraft,
        entry: baseEntry,
        missing: [],
      });
      assertTrue(
        "post_order.directive.emitted",
        directive !== null,
        JSON.stringify(directive),
      );
      assertEqual(
        "post_order.directive.action",
        directive && directive.action,
        "POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF",
      );
      assertTrue(
        "post_order.directive.forbids_fake_handoff",
        directive && directive.forbiddenShapes.includes("fake_handoff_claim"),
        JSON.stringify(directive),
      );
      assertTrue(
        "post_order.directive.forbids_field_update_without_recreate",
        directive &&
          directive.forbiddenShapes.includes("field_update_without_recreate"),
        JSON.stringify(directive),
      );
      assertTrue(
        "post_order.directive.forbids_route_price_recap",
        directive && directive.forbiddenShapes.includes("route_price_recap"),
        JSON.stringify(directive),
      );
    }

    // Case PO-B: same directive fires even without a submitted_order_uid on
    // the entry (defensive — we still want to forbid field-update hallucinations
    // in the edge case where the UID capture missed).
    {
      const entryNoUid = { ...baseEntry, submittedOrderUid: null };
      const directive = computeOneBrainNextRequiredAction({
        draft: entryNoUid.bookingDraft,
        entry: entryNoUid,
        missing: [],
      });
      assertEqual(
        "post_order.no_uid.directive_still_fires",
        directive && directive.action,
        "POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF",
      );
    }

    // Case PO-C: idle stage → no post-order directive (pre-quote chit-chat).
    {
      const idleEntry = {
        ...baseEntry,
        stage: "idle",
        submittedOrderUid: null,
      };
      const directive = computeOneBrainNextRequiredAction({
        draft: idleEntry.bookingDraft,
        entry: idleEntry,
        missing: [],
      });
      assertEqual("post_order.idle.no_directive", directive, null);
    }

    // Case PO-D: collecting_booking_details stage → standard collection
    // directive, NOT post-order. Verifies we didn't regress the earlier
    // stages.
    {
      const collectingEntry = {
        ...baseEntry,
        stage: "collecting_booking_details",
        quotedPrice: 1.25,
        selectedDeliveryType: "sedan_normal",
        submittedOrderUid: null,
      };
      const directive = computeOneBrainNextRequiredAction({
        draft: collectingEntry.bookingDraft,
        entry: collectingEntry,
        missing: ["sender.name", "sender.phone"],
      });
      assertTrue(
        "post_order.collecting.not_post_order",
        directive &&
          directive.action !== "POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF",
        JSON.stringify(directive),
      );
    }

    // Case PO-E: the one-brain live channel context renders the
    // submitted_order_uid line + stage line when stage=order_submitted.
    {
      const context = formatOneBrainLiveChannelContext({
        normalizedReplyTarget: "+96599338566",
        preferredReplyLanguage: "en",
        controllerEntry: baseEntry,
        quotedRoute: null,
      });
      assertTrue(
        "post_order.context.has_stage_line",
        context.includes("current_conversation_stage: order_submitted"),
        context.split("\n").slice(0, 20).join("\n"),
      );
      assertTrue(
        "post_order.context.has_submitted_uid",
        context.includes('submitted_order_uid: "ORDER-ABC123"'),
        context.split("\n").slice(0, 20).join("\n"),
      );
      assertTrue(
        "post_order.context.has_directive",
        context.includes(
          "next_required_action: POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF",
        ),
        context.split("\n").slice(0, 30).join("\n"),
      );
    }

    // Case PO-F: stage=idle → no submitted_order_uid line leaks into context.
    {
      const idleEntry = {
        ...baseEntry,
        stage: "idle",
        submittedOrderUid: null,
      };
      const context = formatOneBrainLiveChannelContext({
        normalizedReplyTarget: "+96599338566",
        preferredReplyLanguage: "en",
        controllerEntry: idleEntry,
        quotedRoute: null,
      });
      assertTrue(
        "post_order.idle.no_submitted_uid_line",
        !context.includes("submitted_order_uid:"),
        context,
      );
    }
  }

  console.log("");
  if (process.exitCode) {
    console.error("Some ONE-BRAIN checks failed.");
  } else {
    console.log("All ONE-BRAIN checks passed.");
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
