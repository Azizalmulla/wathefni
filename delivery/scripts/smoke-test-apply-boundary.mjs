#!/usr/bin/env node
/**
 * Smoke test: the one apply boundary.
 *
 * Pins the evidence contract described in `delivery/ARCHITECTURE.md`.
 * Every proposal from every source — `fast_path`, `llm`, `carryover`
 * — runs through `applyProposals` and is validated identically.
 *
 * Cases covered:
 *
 *   B1  LLM proposal with `sender_name="alright"` on an unresolved
 *       draft → rejected with `coherence_acknowledgment`; no write.
 *       Regression anchor for 2026-04-19 22:08 "alright → sender_name".
 *
 *   B2  Fast-path proposal with `sender_name="hello"` → rejected with
 *       `coherence_greeting`.
 *
 *   B3  LLM proposal with a single unlabeled name+phone pair as the
 *       source_quote, writing `recipient_name` + `recipient_phone` on
 *       an unresolved sender draft → recipient fields dropped,
 *       `requestedSlotOverride` set to `sender_name`. Regression anchor
 *       for 2026-04-19 19:14 "silent recipient attribution".
 *
 *   B4  LLM proposal with missing `source_quote` → all fields rejected
 *       with `missing_source_quote`.
 *
 *   B5  LLM proposal with a well-formed sender name → accepted,
 *       draft has the new value, no rejections.
 *
 *   B6  Fast-path proposal with a well-formed address (block + street
 *       + house) → accepted, address fields written.
 *
 *   B7  Carryover proposal with `sender_name="Aziz"` + no source_quote
 *       → accepted (carryover is exempt from source_quote and coherence
 *       checks).
 *
 *   B8  Proposal returned applied names in BoundaryResult.applied and
 *       structured rejections in BoundaryResult.rejections with the
 *       `source` tag preserved.
 *
 *   B9  Proposal with an acknowledgment candidate for `recipient_name`
 *       also rejected (symmetry between sender and recipient).
 *
 *   B10 Direction invariant: the boundary updates the `draft` in place
 *       across multiple sequential proposals — a sender write first,
 *       then an ambiguous-pair check second, so the sender proposal
 *       resolves the ambiguity.
 *
 *   B11 `sourceQuoteLooksLikeEdit` matches explicit edit cues in
 *       English, Arabizi, and Arabic (change / instead / actually /
 *       make it / "block N to M" / بدّل / غيّر / badel) and rejects
 *       plain fills ("block 3 street 9", "99338566", "hello").
 *
 *   B12 `stageAllowsEdit` returns true only for stages where the
 *       customer has plausibly seen the filled value: collecting /
 *       summary_shown / awaiting_confirmation. idle / quoted / null
 *       return false.
 *
 *   B13 Edit-intent override on a filled slot: draft + DST have
 *       `delivery_block="3"` (filled by a prior customer turn). LLM
 *       proposal sets `address_block="4"`, `source_quote="block 3 to
 *       block 4"`, stage=`awaiting_confirmation`. Expect: block → "4",
 *       no conflict, no rejection, DST slot `filled`, no
 *       `conflictCandidate`.
 *
 *   B14 Same shape as B13 but stage=`quoted` → stage gate blocks the
 *       edit path; conflict is raised and the old value is kept.
 *
 *   B15 Same shape as B13 but source_quote="block 4" (no edit signal)
 *       → regex gate blocks the edit path; conflict is raised.
 *
 *   B16 Conflict recovery: DST slot is already in `conflict` status;
 *       an LLM edit proposal clears the conflict (status → `filled`
 *       with the new value, `conflictCandidate` discarded).
 */
import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  const mod = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/apply-boundary.ts"),
  );
  const {
    applyProposals,
    fastPathProposal,
    llmProposal,
    sourceQuoteLooksLikeEdit,
    stageAllowsEdit,
  } = mod;

  const dialogStateMod = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/dialog-state.ts"),
  );
  const { createEmptyDialogState, updateSlot: rawUpdateSlot } = dialogStateMod;

  const bookingDraftMod = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/booking-draft.ts"),
  );
  const { createEmptyBookingDraft } = bookingDraftMod;

  function emptyCtx() {
    return {
      draft: createEmptyBookingDraft(),
      dialogState: null,
      whatsappNumber: "96599338566",
    };
  }

  // -------------------------------------------------------------------------
  // B1 — "alright" → sender_name rejected (2026-04-19 22:08 regression)
  // -------------------------------------------------------------------------
  {
    const proposal = llmProposal({
      op: {
        sender_name: "alright",
        source_quote: "alright",
        turn_id: "t1",
      },
    });
    const res = applyProposals([proposal], emptyCtx());
    assert.equal(res.applied.length, 0, "B1: nothing should be applied");
    assert.equal(res.draft.senderName, null, "B1: senderName must remain null");
    assert.ok(res.rejections.length > 0, "B1: at least one rejection");
    const rej = res.rejections.find((r) => r.field === "sender_name");
    assert.ok(rej, "B1: sender_name rejection present");
    assert.equal(rej.reason, "coherence_acknowledgment");
    assert.equal(rej.source, "llm");
  }

  // -------------------------------------------------------------------------
  // B2 — "hello" fast-path proposal rejected
  // -------------------------------------------------------------------------
  {
    const proposal = fastPathProposal({
      patch: { sender_name: "hello" },
      sourceQuote: "hello",
    });
    const res = applyProposals([proposal], emptyCtx());
    assert.equal(res.applied.length, 0, "B2: nothing should be applied");
    const rej = res.rejections.find((r) => r.field === "sender_name");
    assert.equal(rej?.reason, "coherence_greeting");
    assert.equal(rej?.source, "fast_path");
  }

  // -------------------------------------------------------------------------
  // B3 — ambiguous unlabeled pair → recipient fields dropped, sender
  //      requested (2026-04-19 19:14 regression)
  // -------------------------------------------------------------------------
  {
    const proposal = llmProposal({
      op: {
        recipient_name: "Aziz almulla",
        recipient_phone: "99338566",
        source_quote: "Aziz almulla 99338566",
        turn_id: "t3",
      },
    });
    const res = applyProposals([proposal], emptyCtx());
    const recNameRej = res.rejections.find((r) => r.field === "recipient_name");
    const recPhoneRej = res.rejections.find((r) => r.field === "recipient_phone");
    assert.ok(recNameRej, "B3: recipient_name rejection present");
    assert.ok(recPhoneRej, "B3: recipient_phone rejection present");
    assert.equal(recNameRej.reason, "ambiguous_pair_sender_unresolved");
    assert.equal(recPhoneRej.reason, "ambiguous_pair_sender_unresolved");
    assert.equal(res.draft.recipientName, null, "B3: recipientName must be null");
    assert.equal(res.draft.recipientPhone, null, "B3: recipientPhone must be null");
    assert.equal(res.requestedSlotOverride, "sender_name");
  }

  // -------------------------------------------------------------------------
  // B4 — missing source_quote → all fields rejected
  // -------------------------------------------------------------------------
  {
    const proposal = llmProposal({
      op: {
        sender_name: "Aziz Almulla",
        sender_phone: "99338566",
        source_quote: "",
        turn_id: "t4",
      },
    });
    const res = applyProposals([proposal], emptyCtx());
    assert.equal(res.applied.length, 0, "B4: nothing applied without source_quote");
    assert.equal(res.draft.senderName, null);
    assert.equal(res.draft.senderPhone, null);
    const allMissing = res.rejections.every((r) => r.reason === "missing_source_quote");
    assert.ok(allMissing, "B4: all rejections must be missing_source_quote");
    assert.ok(
      res.rejections.find((r) => r.field === "sender_name"),
      "B4: sender_name rejection present",
    );
    assert.ok(
      res.rejections.find((r) => r.field === "sender_phone"),
      "B4: sender_phone rejection present",
    );
  }

  // -------------------------------------------------------------------------
  // B5 — well-formed sender name accepted
  // -------------------------------------------------------------------------
  {
    const proposal = llmProposal({
      op: {
        sender_name: "Aziz Almulla",
        source_quote: "sender is Aziz Almulla",
        turn_id: "t5",
      },
    });
    const res = applyProposals([proposal], emptyCtx());
    assert.equal(res.draft.senderName, "Aziz Almulla", "B5: senderName written");
    assert.ok(res.applied.includes("sender_name"), "B5: sender_name in applied");
    assert.equal(res.rejections.length, 0, "B5: no rejections");
  }

  // -------------------------------------------------------------------------
  // B6 — fast-path address proposal (block + street + house) accepted
  // -------------------------------------------------------------------------
  {
    const proposal = fastPathProposal({
      patch: {
        address_block: "11",
        address_street: "7",
        address_house: "19",
        address_role: "pickup",
      },
      sourceQuote: "block 11 street 7 house 19",
    });
    const res = applyProposals([proposal], emptyCtx());
    assert.equal(res.draft.pickupBlock, "11", "B6: block written");
    assert.equal(res.draft.pickupStreet, "7", "B6: street written");
    assert.equal(res.draft.pickupHouse, "19", "B6: house written");
    assert.equal(res.rejections.length, 0, "B6: no rejections");
  }

  // -------------------------------------------------------------------------
  // B7 — carryover proposal exempt from source_quote and coherence
  // -------------------------------------------------------------------------
  {
    const carryover = {
      source: "carryover",
      source_quote: null,
      patch: { sender_name: "Aziz", sender_phone: "99338566" },
    };
    const res = applyProposals([carryover], emptyCtx());
    assert.equal(res.draft.senderName, "Aziz", "B7: carryover sender_name applied");
    assert.equal(res.draft.senderPhone, "99338566", "B7: carryover sender_phone applied");
    assert.equal(res.rejections.length, 0, "B7: no rejections for carryover");
  }

  // -------------------------------------------------------------------------
  // B8 — applied order + rejection source tags
  // -------------------------------------------------------------------------
  {
    const good = llmProposal({
      op: {
        sender_name: "Ahmed",
        source_quote: "Ahmed",
      },
    });
    const bad = llmProposal({
      op: {
        recipient_name: "ok",
        source_quote: "ok",
      },
    });
    const res = applyProposals([good, bad], emptyCtx());
    assert.ok(res.applied.includes("sender_name"));
    const rej = res.rejections.find((r) => r.field === "recipient_name");
    assert.ok(rej, "B8: recipient_name rejection present");
    assert.equal(rej.reason, "coherence_acknowledgment");
    assert.equal(rej.source, "llm");
  }

  // -------------------------------------------------------------------------
  // B9 — recipient-name acknowledgment is also rejected (symmetry)
  // -------------------------------------------------------------------------
  {
    // Start from a draft where sender is already resolved so the
    // ambiguous-pair guard doesn't fire first.
    const draft = createEmptyBookingDraft();
    draft.senderName = "Aziz";
    draft.senderPhone = "99338566";
    const ctx = { draft, dialogState: null, whatsappNumber: "96599338566" };
    const proposal = llmProposal({
      op: {
        recipient_name: "sure",
        source_quote: "sure",
      },
    });
    const res = applyProposals([proposal], ctx);
    const rej = res.rejections.find((r) => r.field === "recipient_name");
    assert.equal(rej?.reason, "coherence_acknowledgment");
    assert.equal(res.draft.recipientName, null);
  }

  // -------------------------------------------------------------------------
  // B10 — sequential proposals see each other's writes. A sender-write
  //       proposal followed by what would otherwise be an ambiguous pair
  //       should NOT trigger the ambiguous-pair guard, because the
  //       sender is now resolved by the time the second proposal runs.
  // -------------------------------------------------------------------------
  {
    const first = llmProposal({
      op: {
        sender_name: "Aziz",
        sender_phone: "99887766",
        source_quote: "sender is Aziz 99887766",
      },
    });
    const second = llmProposal({
      op: {
        recipient_name: "Ahmed",
        recipient_phone: "55443322",
        // Unlabeled pair shape, but draft is resolved — should allow.
        source_quote: "Ahmed 55443322",
      },
    });
    const res = applyProposals([first, second], emptyCtx());
    assert.equal(res.draft.senderName, "Aziz", "B10: sender applied");
    assert.equal(res.draft.recipientName, "Ahmed", "B10: recipient applied");
    assert.equal(res.draft.recipientPhone, "55443322", "B10: recipient phone applied");
    assert.equal(res.requestedSlotOverride, null, "B10: no steer since sender was resolved");
    assert.equal(res.rejections.length, 0, "B10: no rejections");
  }

  // -------------------------------------------------------------------------
  // B11 — edit-cue regex precision
  // -------------------------------------------------------------------------
  {
    const positive = [
      "block 3 to block 4 and street 9 to 10",
      "change the street to 10",
      "please update the sender phone",
      "actually, make it 10",
      "no, make it block 4",
      "not 9, 10",
      "correction: apartment 23",
      "from jabriya block 3 to jabriya block 4",
      "use 10 instead",
      "بدّل الشقة إلى ٢٥",
      "غيّر الشارع",
      "عدّل الطابق",
      "badel block 3 la 4",
      "3addel l sharee3",
    ];
    for (const q of positive) {
      assert.equal(
        sourceQuoteLooksLikeEdit(q),
        true,
        `B11+ expected edit cue in: ${JSON.stringify(q)}`,
      );
    }
    const negative = [
      "",
      null,
      "block 3 street 9 house 19",
      "Aziz Almulla 99338566",
      "99338566",
      "hello",
      "yes",
      "ok",
      "book it",
      // Sender name that happens to contain "to" but no edit cue.
      "Ahmad Al Otaibi",
    ];
    for (const q of negative) {
      assert.equal(
        sourceQuoteLooksLikeEdit(q),
        false,
        `B11- expected no edit cue in: ${JSON.stringify(q)}`,
      );
    }
  }

  // -------------------------------------------------------------------------
  // B12 — stage gate precision
  // -------------------------------------------------------------------------
  {
    for (const s of [
      "collecting_booking_details",
      "summary_shown",
      "awaiting_confirmation",
    ]) {
      assert.equal(stageAllowsEdit(s), true, `B12+ stage should allow: ${s}`);
    }
    for (const s of ["idle", "greeting", "quoted", "order_submitted", "", null, undefined]) {
      assert.equal(
        stageAllowsEdit(s),
        false,
        `B12- stage should block: ${JSON.stringify(s)}`,
      );
    }
  }

  // Helper: build a draft + DST that already has delivery_block = "3"
  // written by a prior customer turn. Used by B13–B16.
  function seededDeliveryBlockContext({ stage } = {}) {
    const draft = createEmptyBookingDraft();
    draft.deliveryBlock = "3";
    let ds = createEmptyDialogState();
    ds = rawUpdateSlot(ds, "delivery_block", "3", "llm_apply", {}).state;
    return {
      draft,
      dialogState: ds,
      whatsappNumber: "96599338566",
      stage: stage ?? null,
    };
  }

  // -------------------------------------------------------------------------
  // B13 — edit-intent override accepted at awaiting_confirmation
  // -------------------------------------------------------------------------
  {
    const ctx = seededDeliveryBlockContext({ stage: "awaiting_confirmation" });
    const proposal = llmProposal({
      op: {
        address_block: "4",
        address_role: "delivery",
        source_quote: "block 3 to block 4",
        turn_id: "t13",
      },
    });
    const res = applyProposals([proposal], ctx);
    assert.equal(res.draft.deliveryBlock, "4", "B13: delivery block overwritten");
    assert.equal(res.rejections.length, 0, "B13: no rejections");
    assert.equal(res.conflicts.length, 0, "B13: no conflicts surfaced");
    const slot = res.dialogState?.slots?.delivery_block;
    assert.ok(slot, "B13: DST slot exists");
    assert.equal(slot.status, "filled", "B13: DST slot status is filled");
    assert.equal(slot.value, "4", "B13: DST slot value is new");
    assert.equal(
      slot.conflictCandidate ?? null,
      null,
      "B13: no conflictCandidate left on DST",
    );
  }

  // -------------------------------------------------------------------------
  // B14 — stage gate blocks edit path (stage=quoted) → conflict kept
  // -------------------------------------------------------------------------
  {
    const ctx = seededDeliveryBlockContext({ stage: "quoted" });
    const proposal = llmProposal({
      op: {
        address_block: "4",
        address_role: "delivery",
        source_quote: "block 3 to block 4",
        turn_id: "t14",
      },
    });
    const res = applyProposals([proposal], ctx);
    assert.equal(res.draft.deliveryBlock, "3", "B14: old value kept");
    assert.ok(
      res.conflicts.some((c) => c.slot === "delivery_block"),
      "B14: delivery_block conflict surfaced",
    );
    const rej = res.rejections.find(
      (r) => r.field === "address_block" && r.reason === "slot_conflict_with_filled_value",
    );
    assert.ok(rej, "B14: slot_conflict_with_filled_value rejection present");
    const slot = res.dialogState?.slots?.delivery_block;
    assert.equal(slot.status, "conflict", "B14: DST slot held in conflict");
    assert.equal(
      slot.conflictCandidate,
      "4",
      "B14: conflictCandidate holds the incoming value",
    );
  }

  // -------------------------------------------------------------------------
  // B15 — regex gate blocks edit path (no edit cue) → conflict kept
  // -------------------------------------------------------------------------
  {
    const ctx = seededDeliveryBlockContext({ stage: "awaiting_confirmation" });
    const proposal = llmProposal({
      op: {
        address_block: "4",
        address_role: "delivery",
        source_quote: "block 4",
        turn_id: "t15",
      },
    });
    const res = applyProposals([proposal], ctx);
    assert.equal(res.draft.deliveryBlock, "3", "B15: old value kept");
    assert.ok(
      res.conflicts.some((c) => c.slot === "delivery_block"),
      "B15: conflict surfaced when regex gate blocks edit",
    );
  }

  // -------------------------------------------------------------------------
  // B16 — explicit edit clears a pre-existing conflict
  // -------------------------------------------------------------------------
  {
    const draft = createEmptyBookingDraft();
    draft.deliveryBlock = "3";
    let ds = createEmptyDialogState();
    ds = rawUpdateSlot(ds, "delivery_block", "3", "llm_apply", {}).state;
    // Introduce a conflict (a different value from a different turn).
    ds = rawUpdateSlot(ds, "delivery_block", "5", "llm_apply", {}).state;
    {
      const slot = ds.slots.delivery_block;
      assert.equal(slot.status, "conflict", "B16 setup: starting from conflict");
      assert.equal(slot.conflictCandidate, "5");
    }
    const ctx = {
      draft,
      dialogState: ds,
      whatsappNumber: "96599338566",
      stage: "awaiting_confirmation",
    };
    const proposal = llmProposal({
      op: {
        address_block: "4",
        address_role: "delivery",
        source_quote: "change block to 4",
        turn_id: "t16",
      },
    });
    const res = applyProposals([proposal], ctx);
    assert.equal(res.draft.deliveryBlock, "4", "B16: block overwritten to 4");
    const slot = res.dialogState?.slots?.delivery_block;
    assert.equal(slot.status, "filled", "B16: slot status reset to filled");
    assert.equal(slot.value, "4", "B16: slot value is the new edit");
    assert.equal(
      slot.conflictCandidate ?? null,
      null,
      "B16: conflictCandidate cleared",
    );
    assert.equal(res.rejections.length, 0, "B16: no rejections");
    // The edit did NOT write anything into conflicts — the conflict is
    // resolved by the override.
    assert.equal(res.conflicts.length, 0, "B16: no conflicts surfaced");
  }

  console.log("smoke-test-apply-boundary: OK");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
