#!/usr/bin/env node
/**
 * Smoke test: outbound clarifying-question shape preserves LLM repair replies.
 *
 * Background — the canonical-summary substitution path was
 * over-eagerly replacing LLM clarifications with the full summary. On
 * 2026-04-19 15:28, a historical poisoned `senderName = "Is this the
 * cheapest option"` was carried into a complete draft; the customer
 * sent "hello"; the LLM correctly replied with a clarifying question
 * ("Is it 'hello' or 'Is this the cheapest option'?"). The outbound
 * verifier classified that reply as `stub_summary` (it lacks the
 * Pickup:/Delivery:/Price: lines of the canonical summary) and
 * substituted it with the full summary, re-surfacing the poisoned
 * value the LLM was trying to repair.
 *
 * The fix adds a `clarifying_question` shape that's evaluated BEFORE
 * the stub_summary / standalone_ack paths and bypasses all
 * substitution paths. This test pins:
 *
 *   1. Clarifying questions (EN, AR, Arabizi) classify as
 *      `clarifying_question`, not `stub_summary`.
 *   2. The canonical "Shall I confirm this order?" line does NOT
 *      trigger the clarifying-question path.
 *   3. A real stub_summary (bare "ready to confirm?") still classifies
 *      as stub_summary.
 *   4. verifyAndRepairOutbound preserves clarifying replies even when
 *      the draft is complete and a substitute WOULD be producible.
 */
import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  const verifyPath = path.join(deliveryRoot, "plugins/shared/outbound-verify.ts");
  const mod = await loadDeliveryTsModule(import.meta.url, verifyPath);
  const { classifyOutboundReplyShape, verifyAndRepairOutbound } = mod;

  // A complete draft + full quote, mirroring the 2026-04-19 state.
  const completeEntry = {
    lastActivityTs: Date.now(),
    language: "en",
    explicitLanguage: null,
    stage: "awaiting_confirmation",
    bookingStep: "confirm",
    conversationId: "conv-clarify",
    replyTarget: "+96599338566",
    accountId: "riders",
    quoteRouteKey: null,
    quoteTs: Date.now(),
    quotePickupAreaNameEn: "Salwa",
    quotePickupAreaNameAr: null,
    quoteDropoffAreaNameEn: "Al Masayel",
    quoteDropoffAreaNameAr: null,
    selectedQuoteOptionType: "standard_sedan",
    selectedQuoteOptionLabelEn: "Standard sedan",
    selectedQuoteOptionLabelAr: null,
    selectedQuoteOptionPrice: 1.25,
    selectedQuoteOptionDirectChatBookingStatus: null,
    selectedDeliveryType: "standard_sedan",
    quotedPrice: 1.25,
    bookingDraft: {
      senderName: "Is this the cheapest option",
      senderPhone: "99118375",
      recipientName: "aziz almulla",
      recipientPhone: "99338566",
      pickupBlock: "3",
      pickupStreet: "4",
      pickupHouse: "19",
      pickupAvenue: null,
      pickupExtra: null,
      pickupLocation: null,
      deliveryBlock: "11",
      deliveryStreet: "7",
      deliveryHouse: null,
      deliveryAvenue: null,
      deliveryExtra: "apartment 11, floor 4, door 10",
      deliveryLocation: null,
      pendingLocation: null,
    },
    dialogState: null,
  };

  // -------------------------------------------------------------------------
  // 1. Clarifying questions classify as clarifying_question
  // -------------------------------------------------------------------------
  const clarifyingReplies = [
    // The exact 2026-04-19 LLM repair reply.
    `Hi, please confirm the sender name for the order. Is it "hello" or "Is this the cheapest option"?`,
    // Variants.
    `Could you confirm the sender phone? It looks unusual.`,
    `Do you mean Salwa or Salmiya for pickup?`,
    `Please clarify whether the pickup is Block 3 or Block 7?`,
    `Did you mean 99118375 or 99338566 for the sender phone?`,
    // Arabic.
    `من فضلك أكد اسم المرسل. هل هو "hello" أم "Is this the cheapest option"؟`,
    `ممكن تأكد الرقم؟`,
    // Arabizi.
    `Akkid il raqam 99118375 wala 99338566?`,
  ];
  for (const replyText of clarifyingReplies) {
    const shape = classifyOutboundReplyShape({
      replyText,
      entry: completeEntry,
      missingFields: [],
      language: replyText.match(/[\u0600-\u06FF]/) ? "ar" : "en",
    });
    assert.equal(
      shape,
      "clarifying_question",
      `expected clarifying_question for ${JSON.stringify(replyText)}, got ${shape}`,
    );
  }

  // -------------------------------------------------------------------------
  // 2. The canonical "Shall I confirm this order?" line is NOT flagged
  //    (it's the normal confirmation prompt, not a clarification).
  // -------------------------------------------------------------------------
  {
    const shape = classifyOutboundReplyShape({
      replyText: "Shall I confirm this order?",
      entry: completeEntry,
      missingFields: [],
      language: "en",
    });
    assert.notEqual(shape, "clarifying_question");
  }

  // -------------------------------------------------------------------------
  // 3. A multi-line summary that happens to contain "confirm" in the
  //    "Shall I confirm this order?" trailing line is NOT flagged.
  // -------------------------------------------------------------------------
  {
    const fullSummary = [
      "Order summary",
      "Pickup: Salwa — Block 3, Street 4, House 19",
      "Delivery: Al Masayel — Block 11, Street 7, apartment 11, floor 4, door 10",
      "Sender: Aziz — 99118375",
      "Recipient: aziz almulla — 99338566",
      "Service: Standard sedan",
      "Price: 1.250 KWD",
      "",
      "Shall I confirm this order?",
    ].join("\n");
    const shape = classifyOutboundReplyShape({
      replyText: fullSummary,
      entry: { ...completeEntry, bookingDraft: { ...completeEntry.bookingDraft, senderName: "Aziz" } },
      missingFields: [],
      language: "en",
    });
    assert.notEqual(shape, "clarifying_question");
  }

  // -------------------------------------------------------------------------
  // 4. A real stub_summary (no clarify verbs) still classifies as stub.
  // -------------------------------------------------------------------------
  {
    const shape = classifyOutboundReplyShape({
      replyText: "All set, ready to confirm?",
      entry: { ...completeEntry, bookingDraft: { ...completeEntry.bookingDraft, senderName: "Aziz" } },
      missingFields: [],
      language: "en",
    });
    assert.equal(shape, "stub_summary", `expected stub_summary for bare prompt, got ${shape}`);
  }

  // -------------------------------------------------------------------------
  // 5. verifyAndRepairOutbound preserves clarifying replies end-to-end.
  //    This is the regression that made the poisoned name visible.
  // -------------------------------------------------------------------------
  {
    const replyText = `Hi, please confirm the sender name for the order. Is it "hello" or "Is this the cheapest option"?`;
    const res = verifyAndRepairOutbound({
      replyText,
      entry: completeEntry,
      missingFields: [],
      language: "en",
    });
    assert.equal(res.replaced, false, "clarifying question must NOT be substituted");
    assert.equal(res.shape, "clarifying_question");
    assert.equal(res.replyText, replyText, "clarifying reply text must pass through unchanged");
    assert.equal(res.reason, "preserved_clarifying_question");
  }

  // -------------------------------------------------------------------------
  // 6. Step-3 narrowing (2026-04): stub_summary on a complete draft is now
  //    LOG-ONLY. The shape detector still fires (so production logs surface
  //    it) but we no longer substitute the canonical labeled-row summary
  //    over the LLM's natural phrasing. Only `summary_fact_drift` triggers
  //    substitution under the "free phrasing, strict facts" policy.
  // -------------------------------------------------------------------------
  {
    const entryWithGoodName = {
      ...completeEntry,
      bookingDraft: { ...completeEntry.bookingDraft, senderName: "Aziz" },
    };
    const res = verifyAndRepairOutbound({
      replyText: "All set, ready to confirm?",
      entry: entryWithGoodName,
      missingFields: [],
      language: "en",
    });
    assert.equal(res.replaced, false, "stub_summary is log-only under Step-3 policy");
    assert.equal(res.shape, "stub_summary");
    assert.equal(res.reason, "detected_stub_summary_log_only");
    assert.equal(res.replyText, "All set, ready to confirm?", "reply passes through unchanged");
  }

  // -------------------------------------------------------------------------
  // 7. Step-3 narrowing: summary_fact_drift on a complete draft STILL gets
  //    substituted. This is the transactional case — the LLM's summary
  //    claims a price / phone tail / name that disagrees with server state,
  //    which is exactly the kind of factual mismatch we must repair on the
  //    wire so the customer cannot act on a wrong summary.
  // -------------------------------------------------------------------------
  {
    const entryWithGoodName = {
      ...completeEntry,
      bookingDraft: { ...completeEntry.bookingDraft, senderName: "Aziz" },
    };
    // Structurally a valid full summary, but with a wrong price (expected
    // 1.250, written as 2.500 KWD).
    const driftyReply = [
      "Order summary",
      "Pickup: Salwa — Block 3, Street 4, House 19",
      "Delivery: Al Masayel — Block 11, Street 7, apartment 11, floor 4, door 10",
      "Sender: Aziz — 99118375",
      "Recipient: aziz almulla — 99338566",
      "Service: Standard sedan",
      "Price: 2.500 KWD",
      "",
      "Shall I confirm this order?",
    ].join("\n");
    const res = verifyAndRepairOutbound({
      replyText: driftyReply,
      entry: entryWithGoodName,
      missingFields: [],
      language: "en",
    });
    assert.equal(res.replaced, true, "summary_fact_drift must still substitute");
    assert.equal(res.shape, "summary_fact_drift");
    assert.match(res.reason || "", /substituted_full_summary:summary_fact_drift/);
    // Substitute must contain the correct price, not the drifty one.
    assert.match(res.replyText, /1\.250 KWD/);
    assert.ok(!/2\.500 KWD/.test(res.replyText), "substituted reply must not carry the drifted price");
  }

  console.log("smoke-test-outbound-clarifying-question: OK");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
