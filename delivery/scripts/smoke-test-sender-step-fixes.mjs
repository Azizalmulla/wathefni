#!/usr/bin/env node
/**
 * Smoke test: sender-step 19399 regression pack.
 *
 * Pins the three fixes landed in response to the 2026-04-22 live sender-
 * step failure (conversation 19399) where the bot re-asked for sender
 * name+phone three turns in a row and ultimately raised a `sender_phone`
 * conflict. Each case targets one fix in isolation and one case
 * composes all three as the full 19399 trace.
 *
 *   S1  WhatsApp-equivalence normalization (Fix A): LLM writes
 *       `sender_phone = "99338566"` (local part of the customer's
 *       WhatsApp `96599338566`) on a name-requested turn. Boundary
 *       normalizes to `phone_decision = "use_whatsapp"`; draft
 *       `senderPhone` gets the canonical WA number; the
 *       `normalizations` array surfaces one entry with
 *       `kind="whatsapp_equivalence_sender_phone"`.
 *
 *   S2  Same as S1 but from a fast-path proposal. The boundary catches
 *       both sources identically.
 *
 *   S3  Exact-match variant: LLM writes `sender_phone = "96599338566"`
 *       (the full WA number). Also normalized.
 *
 *   S4  No normalization when sender_phone is a DIFFERENT number
 *       ("97777777" vs WA `96599338566`) — patch flows through
 *       unchanged, normalizations is empty.
 *
 *   S5  No normalization when whatsappNumber is null.
 *
 *   S6  Narrow selector branch (Fix B): after Fix A landed
 *       `phone_decision=use_whatsapp` on Turn B, the draft has
 *       `senderPhone` populated but no name. The selector picks
 *       `ASK_SENDER_NAME` (narrow), NOT the combined
 *       `ASK_SENDER_NAME_AND_PHONE_DECISION`.
 *
 *   S7  Selector still picks the combined ask when both name and phone
 *       are missing (baseline preserved).
 *
 *   S8  Selector picks `ASK_SENDER_PHONE` when name is present but
 *       phone is missing (baseline preserved).
 *
 *   S9  ASK_SENDER_NAME registry renderer produces the narrow AR/EN
 *       phrasings.
 *
 *   S10 Requested-slot name-scope guard (Fix C) in the NARROW sender-
 *       name ask state: `dialogState.requestedSlot = { name:
 *       "sender_name" }` AND `draft.senderPhone` is already resolved
 *       (e.g. a prior turn's WA-equivalence normalization populated
 *       it). An LLM patch that writes a non-WA `sender_phone` and NO
 *       name is dropped with reason `requested_slot_name_scope`;
 *       draft.senderPhone preserves the already-resolved value.
 *
 *   S11 Same state, but the patch carries BOTH `sender_name` and
 *       `sender_phone` — both land. The guard only fires when the
 *       name side is missing.
 *
 *   S12 Same state, but the patch phone matches WA. Fix A runs FIRST
 *       and normalizes to `phone_decision=use_whatsapp`, so Fix C
 *       never sees a phone to drop; the decision lands (draft
 *       `senderPhone` = WA, senderPhoneDecision="use_whatsapp").
 *
 *   S13 Recipient symmetry in the NARROW recipient-name ask state:
 *       with `requestedSlot.name = "recipient_name"` AND
 *       `draft.recipientPhone` already filled, a new stray
 *       recipient_phone patch is dropped. Defensive — the product
 *       currently has no path that reaches this state (no narrow
 *       ASK_RECIPIENT_NAME directive) but the guard is symmetric.
 *
 *   S13b Combined sender-name+phone ask: `requestedSlot.name =
 *        "sender_name"` but `draft.senderPhone` is empty (the
 *        server is asking the combined question). A phone-only
 *        patch is a legitimate partial answer and MUST land — the
 *        guard is suppressed in the combined-ask state. Narrowing
 *        pin for the 2026-04-22 live regression.
 *
 *   S13c Combined recipient-name+phone ask — exact live trace from
 *        conv 19399 turn 6. Customer sends only the recipient phone
 *        ("٥٩٣٨٤٨٥٧") while the server had asked
 *        `ASK_RECIPIENT_NAME_AND_PHONE`. The phone MUST land as a
 *        partial answer; the guard MUST NOT fire. Regression pin.
 *
 *   S14 Full 19399 trace: Turn B arrives with a stale LLM write of
 *       `sender_phone = "99338566"` while `requestedSlot.name =
 *       "sender_name"`. Fix A normalizes → use_whatsapp; draft has
 *       senderPhone set from WA, senderName still null. Turn B' next-
 *       action selector picks ASK_SENDER_NAME (narrow). Turn C arrives
 *       with the name → draft.senderName populated, selector moves on
 *       to recipient. No conflict raised anywhere.
 */
import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  const boundaryMod = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/apply-boundary.ts"),
  );
  const { applyProposals, fastPathProposal, llmProposal } = boundaryMod;

  const bookingDraftMod = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/booking-draft.ts"),
  );
  const { createEmptyBookingDraft } = bookingDraftMod;

  const dialogStateMod = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/dialog-state.ts"),
  );
  const {
    createEmptyDialogState,
    setRequestedSlot,
  } = dialogStateMod;

  const obcMod = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/octopus-channel/lib/one-brain-context.ts"),
  );
  const { computeOneBrainNextRequiredAction } = obcMod;

  const registryMod = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/directive-reply-registry.ts"),
  );
  const { renderDirectiveReply } = registryMod;

  const WA = "96599338566";

  function emptyCtx() {
    return {
      draft: createEmptyBookingDraft(),
      dialogState: null,
      whatsappNumber: WA,
    };
  }

  function ctxWithRequestedSlot(slotName, draft = null) {
    const ds = setRequestedSlot(createEmptyDialogState(), {
      name: slotName,
      options: null,
      askedTs: Date.now(),
    });
    return {
      draft: draft ?? createEmptyBookingDraft(),
      dialogState: ds,
      whatsappNumber: WA,
    };
  }

  // -------------------------------------------------------------------------
  // S1 — LLM writes sender_phone with WA local part → normalized
  // -------------------------------------------------------------------------
  {
    const proposal = llmProposal({
      op: {
        sender_phone: "99338566",
        source_quote: "99338566",
        turn_id: "s1",
      },
    });
    const res = applyProposals([proposal], emptyCtx());
    assert.equal(
      res.normalizations.length,
      1,
      "S1: one normalization recorded",
    );
    const n = res.normalizations[0];
    assert.equal(n.kind, "whatsapp_equivalence_sender_phone");
    assert.equal(n.field, "sender_phone");
    assert.equal(n.incoming, "99338566");
    assert.equal(n.mappedTo, WA);
    assert.equal(n.source, "llm");
    assert.equal(
      res.senderPhoneDecision,
      "use_whatsapp",
      "S1: phone_decision landed as use_whatsapp",
    );
    assert.equal(
      res.draft.senderPhone,
      WA,
      "S1: draft.senderPhone set to canonical WA",
    );
    assert.equal(
      res.rejections.length,
      0,
      "S1: no rejections; the write landed via phone_decision",
    );
  }

  // -------------------------------------------------------------------------
  // S2 — Same normalization from fast-path
  // -------------------------------------------------------------------------
  {
    const proposal = fastPathProposal({
      patch: { sender_phone: "99338566" },
      sourceQuote: "99338566",
    });
    const res = applyProposals([proposal], emptyCtx());
    assert.equal(res.normalizations.length, 1, "S2: normalized");
    assert.equal(res.normalizations[0].source, "fast_path");
    assert.equal(res.draft.senderPhone, WA, "S2: draft.senderPhone = WA");
    assert.equal(res.senderPhoneDecision, "use_whatsapp");
  }

  // -------------------------------------------------------------------------
  // S3 — Exact match (full WA number as sender_phone) also normalizes
  // -------------------------------------------------------------------------
  {
    const proposal = llmProposal({
      op: {
        sender_phone: WA,
        source_quote: WA,
        turn_id: "s3",
      },
    });
    const res = applyProposals([proposal], emptyCtx());
    assert.equal(res.normalizations.length, 1, "S3: exact-match normalized");
    assert.equal(res.normalizations[0].incoming, WA);
    assert.equal(res.senderPhoneDecision, "use_whatsapp");
  }

  // -------------------------------------------------------------------------
  // S4 — Different phone passes through unchanged
  // -------------------------------------------------------------------------
  {
    const proposal = llmProposal({
      op: {
        sender_name: "Aziz Almulla",
        sender_phone: "97777777",
        phone_decision: "different",
        source_quote: "Aziz Almulla 97777777",
        turn_id: "s4",
      },
    });
    const res = applyProposals([proposal], emptyCtx());
    assert.equal(res.normalizations.length, 0, "S4: no normalization");
    assert.equal(res.draft.senderPhone, "97777777");
    assert.equal(res.draft.senderName, "Aziz Almulla");
    assert.equal(res.senderPhoneDecision, "different");
  }

  // -------------------------------------------------------------------------
  // S5 — No normalization when whatsappNumber is null
  // -------------------------------------------------------------------------
  {
    const proposal = llmProposal({
      op: {
        sender_phone: "99338566",
        source_quote: "99338566",
        turn_id: "s5",
      },
    });
    const res = applyProposals([proposal], {
      draft: createEmptyBookingDraft(),
      dialogState: null,
      whatsappNumber: null,
    });
    assert.equal(res.normalizations.length, 0, "S5: no WA → no normalization");
    assert.equal(res.draft.senderPhone, "99338566");
  }

  // -------------------------------------------------------------------------
  // S6 — Selector picks narrow ASK_SENDER_NAME when phone resolved,
  //      name missing
  // -------------------------------------------------------------------------
  function collectionEntry(overrides = {}) {
    return {
      bookingStep: "collecting_booking_details",
      stage: "collecting_booking_details",
      dialogState: null,
      pendingPickupAreaNameEn: "Salmiya",
      pendingDropoffAreaNameEn: "Hawalli",
      quotePickupAreaNameEn: "Salmiya",
      quoteDropoffAreaNameEn: "Hawalli",
      quotePickupAreaNameAr: null,
      quoteDropoffAreaNameAr: null,
      pendingPickupAreaNameAr: null,
      pendingDropoffAreaNameAr: null,
      activeQuoteOption: null,
      quotedPrice: 1.25,
      selectedDeliveryType: "sedan_normal",
      selectedQuoteOptionDirectChatBookingStatus: "bookable",
      ...overrides,
    };
  }
  {
    const draft = { ...createEmptyBookingDraft(), senderPhone: WA };
    const entry = collectionEntry({ bookingDraft: draft });
    const missing = [
      "sender.name",
      "recipient.name",
      "recipient.phone",
      "pickup.address",
      "delivery.address",
    ];
    const directive = computeOneBrainNextRequiredAction({
      draft,
      entry,
      missing,
    });
    assert.equal(
      directive.action,
      "ASK_SENDER_NAME",
      "S6: narrow sender-name ask picked",
    );
    assert.equal(directive.field, "sender.name");
  }

  // -------------------------------------------------------------------------
  // S7 — Selector still picks combined ask when BOTH name and phone
  //      are missing
  // -------------------------------------------------------------------------
  {
    const draft = createEmptyBookingDraft();
    const entry = collectionEntry({ bookingDraft: draft });
    const missing = ["sender.name", "sender.phone"];
    const directive = computeOneBrainNextRequiredAction({
      draft,
      entry,
      missing,
    });
    assert.equal(
      directive.action,
      "ASK_SENDER_NAME_AND_PHONE_DECISION",
      "S7: combined ask preserved",
    );
  }

  // -------------------------------------------------------------------------
  // S8 — Selector picks ASK_SENDER_PHONE when name present, phone missing
  // -------------------------------------------------------------------------
  {
    const draft = { ...createEmptyBookingDraft(), senderName: "Aziz" };
    const entry = collectionEntry({ bookingDraft: draft });
    const missing = ["sender.phone"];
    const directive = computeOneBrainNextRequiredAction({
      draft,
      entry,
      missing,
    });
    assert.equal(directive.action, "ASK_SENDER_PHONE");
  }

  // -------------------------------------------------------------------------
  // S9 — ASK_SENDER_NAME renderer (narrow AR + EN phrasings)
  // -------------------------------------------------------------------------
  {
    const draft = { ...createEmptyBookingDraft(), senderPhone: WA };
    const entry = collectionEntry({ bookingDraft: draft, lastActivityTs: Date.now() });
    const en = renderDirectiveReply("ASK_SENDER_NAME", {
      language: "en",
      draft,
      entry,
      conflictingSlot: null,
      conflictValues: null,
      turnSeed: "s9-en",
    });
    const ar = renderDirectiveReply("ASK_SENDER_NAME", {
      language: "ar",
      draft,
      entry,
      conflictingSlot: null,
      conflictValues: null,
      turnSeed: "s9-ar",
    });
    assert.equal(en.kind, "render", "S9: EN renderer returned render");
    assert.equal(en.text, "Sender's full name?");
    assert.equal(ar.kind, "render", "S9: AR renderer returned render");
    assert.equal(ar.text, "اسم المرسل الكامل؟");
  }

  // -------------------------------------------------------------------------
  // S10 — Requested-slot name-scope guard (narrow sender-name ask state):
  //       sender phone is ALREADY resolved on the draft (narrow
  //       `ASK_SENDER_NAME` scenario after Fix A collapsed the combined
  //       ask), requestedSlot=sender_name, and the LLM writes a
  //       non-WA sender_phone without a name. The stray phone is
  //       dropped because the server's "name?" question was not
  //       answered.
  // -------------------------------------------------------------------------
  {
    const draft = { ...createEmptyBookingDraft(), senderPhone: WA };
    const proposal = llmProposal({
      op: {
        sender_phone: "97777777",
        source_quote: "97777777",
        turn_id: "s10",
      },
    });
    const res = applyProposals([proposal], ctxWithRequestedSlot("sender_name", draft));
    const rej = res.rejections.find((r) => r.field === "sender_phone");
    assert.ok(rej, "S10: sender_phone rejection present (narrow-ask state)");
    assert.equal(rej.reason, "requested_slot_name_scope");
    assert.equal(rej.source, "llm");
    assert.equal(
      res.draft.senderPhone,
      WA,
      "S10: draft.senderPhone preserved as the already-resolved WA number",
    );
    assert.equal(res.normalizations.length, 0);
  }

  // -------------------------------------------------------------------------
  // S11 — Same state but both name AND phone are in the patch → both land
  // -------------------------------------------------------------------------
  {
    const proposal = llmProposal({
      op: {
        sender_name: "Aziz Almulla",
        sender_phone: "97777777",
        phone_decision: "different",
        source_quote: "Aziz Almulla 97777777",
        turn_id: "s11",
      },
    });
    const res = applyProposals([proposal], ctxWithRequestedSlot("sender_name"));
    assert.equal(res.draft.senderName, "Aziz Almulla");
    assert.equal(res.draft.senderPhone, "97777777");
    assert.equal(
      res.rejections.filter((r) => r.reason === "requested_slot_name_scope").length,
      0,
      "S11: name-scope guard did not fire when name accompanies phone",
    );
  }

  // -------------------------------------------------------------------------
  // S12 — Same state but phone matches WA → Fix A wins first
  // -------------------------------------------------------------------------
  {
    const proposal = llmProposal({
      op: {
        sender_phone: "99338566",
        source_quote: "99338566",
        turn_id: "s12",
      },
    });
    const res = applyProposals([proposal], ctxWithRequestedSlot("sender_name"));
    assert.equal(
      res.normalizations.length,
      1,
      "S12: WA-equivalence normalized first",
    );
    assert.equal(res.senderPhoneDecision, "use_whatsapp");
    assert.equal(
      res.rejections.filter((r) => r.reason === "requested_slot_name_scope").length,
      0,
      "S12: name-scope guard did not fire (nothing left to drop)",
    );
    assert.equal(
      res.draft.senderPhone,
      WA,
      "S12: WA number landed via phone_decision",
    );
  }

  // -------------------------------------------------------------------------
  // S13 — Recipient symmetry (narrow recipient-name ask state):
  //       recipient phone is ALREADY resolved on the draft,
  //       requestedSlot=recipient_name. Defensive test — this state is
  //       not reached by the current selector (there is no
  //       ASK_RECIPIENT_NAME narrow directive) but the boundary guard
  //       is symmetric and a new stray recipient_phone write must
  //       still be dropped.
  // -------------------------------------------------------------------------
  {
    const draft = {
      ...createEmptyBookingDraft(),
      senderName: "Aziz",
      senderPhone: WA,
      recipientPhone: "99111111",
    };
    const proposal = llmProposal({
      op: {
        recipient_phone: "98888888",
        source_quote: "98888888",
        turn_id: "s13",
      },
    });
    const res = applyProposals([proposal], ctxWithRequestedSlot("recipient_name", draft));
    const rej = res.rejections.find((r) => r.field === "recipient_phone");
    assert.ok(rej, "S13: recipient_phone rejection present (narrow-ask state)");
    assert.equal(rej.reason, "requested_slot_name_scope");
    assert.equal(
      res.draft.recipientPhone,
      "99111111",
      "S13: draft.recipientPhone preserved (already-resolved value)",
    );
  }

  // -------------------------------------------------------------------------
  // S13b — Combined sender-name+phone ask (Fix C narrowing regression
  //        pin): requestedSlot=sender_name but draft.senderPhone is
  //        empty. A phone-only patch is a partial answer to the
  //        combined ask and MUST land — the name-scope guard is
  //        suppressed in the combined-ask state to avoid the
  //        "bot ignored my phone" regression.
  // -------------------------------------------------------------------------
  {
    const proposal = llmProposal({
      op: {
        sender_phone: "97777777",
        phone_decision: "different",
        source_quote: "97777777",
        turn_id: "s13b",
      },
    });
    const res = applyProposals([proposal], ctxWithRequestedSlot("sender_name"));
    assert.equal(
      res.rejections.filter((r) => r.reason === "requested_slot_name_scope").length,
      0,
      "S13b: guard suppressed in combined-ask state (sender phone empty)",
    );
    assert.equal(res.draft.senderPhone, "97777777", "S13b: sender_phone landed");
    assert.equal(res.senderPhoneDecision, "different");
  }

  // -------------------------------------------------------------------------
  // S13c — Combined recipient-name+phone ask (live 19399 recipient-
  //        step regression pin): requestedSlot=recipient_name, sender
  //        already filled, draft.recipientPhone empty. Customer
  //        answers with the recipient phone only (the exact live
  //        trace: "٥٩٣٨٤٨٥٧"). Phone MUST land; guard MUST NOT fire.
  // -------------------------------------------------------------------------
  {
    const draft = {
      ...createEmptyBookingDraft(),
      senderName: "Aziz",
      senderPhone: WA,
    };
    const proposal = llmProposal({
      op: {
        recipient_phone: "59384857",
        source_quote: "٥٩٣٨٤٨٥٧",
        turn_id: "s13c",
      },
    });
    const res = applyProposals([proposal], ctxWithRequestedSlot("recipient_name", draft));
    assert.equal(
      res.rejections.filter((r) => r.reason === "requested_slot_name_scope").length,
      0,
      "S13c: guard suppressed in combined recipient ask — phone lands as partial answer",
    );
    assert.equal(
      res.draft.recipientPhone,
      "59384857",
      "S13c: recipient_phone landed (regression pin for conv 19399 turn 6)",
    );
  }

  // -------------------------------------------------------------------------
  // S14 — Full 19399 trace composition. Walks Turn B and Turn C through
  //       the boundary and selector end to end.
  // -------------------------------------------------------------------------
  {
    // Turn B: requestedSlot=sender_name, LLM writes stale sender_phone
    // matching WA local-part. Fix A normalizes → use_whatsapp.
    const turnBProposal = llmProposal({
      op: {
        sender_phone: "99338566",
        source_quote: "تسعة تسعة ثلاثة ثلاثة ثمانية خمسة ستة ستة",
        turn_id: "turn-b",
      },
    });
    const turnBCtx = ctxWithRequestedSlot("sender_name");
    const turnBRes = applyProposals([turnBProposal], turnBCtx);
    assert.equal(
      turnBRes.normalizations.length,
      1,
      "S14/B: WA-equivalence normalized",
    );
    assert.equal(turnBRes.senderPhoneDecision, "use_whatsapp");
    assert.equal(turnBRes.draft.senderPhone, WA);
    assert.equal(turnBRes.draft.senderName, null);

    // Next-action selector on the post-Turn-B draft:
    // senderName null + senderPhone WA → ASK_SENDER_NAME.
    const entryAfterB = collectionEntry({
      bookingDraft: turnBRes.draft,
      dialogState: turnBRes.dialogState,
    });
    const directiveAfterB = computeOneBrainNextRequiredAction({
      draft: turnBRes.draft,
      entry: entryAfterB,
      missing: [
        "sender.name",
        "recipient.name",
        "recipient.phone",
        "pickup.address",
        "delivery.address",
      ],
    });
    assert.equal(
      directiveAfterB.action,
      "ASK_SENDER_NAME",
      "S14/B: narrow ASK_SENDER_NAME picked",
    );

    // Turn C: customer replies "Abdulaziz Almulla".
    const turnCCtx = {
      draft: turnBRes.draft,
      dialogState: turnBRes.dialogState,
      whatsappNumber: WA,
    };
    const turnCProposal = llmProposal({
      op: {
        sender_name: "Abdulaziz Almulla",
        source_quote: "Abdulaziz Almulla",
        turn_id: "turn-c",
      },
    });
    const turnCRes = applyProposals([turnCProposal], turnCCtx);
    assert.equal(turnCRes.draft.senderName, "Abdulaziz Almulla");
    assert.equal(turnCRes.draft.senderPhone, WA, "S14/C: senderPhone preserved");
    assert.equal(
      turnCRes.conflicts.length,
      0,
      "S14/C: no conflict raised (the WA phone is stable)",
    );
  }

  console.log("✓ smoke-test-sender-step-fixes: all cases passed");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
