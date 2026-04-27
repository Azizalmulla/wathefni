#!/usr/bin/env node
/**
 * Smoke test: slot-fill regressions surfaced by conv 19399 (2026-04-22).
 *
 * Background
 * ----------
 * A live manual test on 2026-04-22 exposed four defects that together
 * corrupted the sender/recipient identity block:
 *
 *   A) Multi-word Arabic acknowledgments ("أوكي تم") passed the
 *      single-token ack patterns in `slot-response-coherence.ts` and
 *      fell through to `answer` for name slots. The fast-path then
 *      wrote "أوكي تم" to `sender_name` and the real name step was
 *      skipped.
 *
 *   B) `extractRecipientNameAndPhone` rejected labeled Arabic answers
 *      like "اسم احمد باشا رقم 5207777" because the legacy
 *      `\b(...|رقم)\b` guard does not anchor on Arabic (ASCII `\b`).
 *      The full corrupted residual was accepted as `recipient_name`.
 *
 *   C) Historical guard: when a same-turn pre-apply has genuinely committed
 *      one side's phone, the LLM must not mirror the same digit group into
 *      the counterpart side. Identity phone fast-path is now removed, but the
 *      guard remains pinned so only committed writes can ever trigger it.
 *
 *   D) `CONFIRM_SLOT_CONFLICT` dispatch read `rec.conflictValue` off
 *      the DST slot record, but the actual field is
 *      `conflictCandidate`. The `both` branch of the renderer never
 *      fired, so every AR/EN conflict prompt fell back to the
 *      generic "Correct value for X?".
 *
 * This file pins the fixes end-to-end so they don't regress.
 *
 * Cases
 * -----
 *   1. multi-word acknowledgments classify as `acknowledgment` and
 *      fast-path name extractors refuse them.
 *   2. labeled Arabic + EN recipient answers strip the labels and
 *      parse as `(recipient_name, recipient_phone)`; label-only
 *      residuals are rejected; regression guards for unlabeled real
 *      names still hold.
 *   3. `applyCrossSidePhoneGuard` is symmetric and only triggers on
 *      the counterpart side; same-side writes pass through; a drop
 *      produces the stable `cross_side_phone_write_same_turn` reason.
 *   4. DST conflict records expose `conflictCandidate` (the key the
 *      dispatch site now reads), and `renderDirectiveReply` for
 *      `CONFIRM_SLOT_CONFLICT` renders the two-value prompt in both
 *      AR and EN when given that key.
 *   5. Recovery — if `recipient_name` is already corrupted ("اسم احمد
 *      باشا رقم"), a subsequent labeled answer parses cleanly, the
 *      boundary raises a well-formed conflict whose `conflictCandidate`
 *      is the clean value, and the renderer shows both values so the
 *      customer can recover without support intervention.
 */

import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  const coherence = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/slot-response-coherence.ts"),
  );
  const fastPath = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/fast-path-extractor.ts"),
  );
  const crossSide = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/cross-side-phone-guard.ts"),
  );
  const dialogState = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/dialog-state.ts"),
  );
  const applyBoundary = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/apply-boundary.ts"),
  );
  const registry = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/directive-reply-registry.ts"),
  );
  const bookingDraft = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/booking-draft.ts"),
  );

  const { classifyResponseForSlot, isAcceptableSlotResponse } = coherence;
  const { extractForNextAction, extractSenderNameAndDecision, extractRecipientNameAndPhone } = fastPath;
  const { applyCrossSidePhoneGuard } = crossSide;
  const { createEmptyDialogState, updateSlot } = dialogState;
  const { applyProposals, fastPathProposal, llmProposal } = applyBoundary;
  const { renderDirectiveReply } = registry;
  const { createEmptyBookingDraft } = bookingDraft;

  // -------------------------------------------------------------------------
  // Fix 1 — multi-word acknowledgments
  // -------------------------------------------------------------------------
  const multiWordAcks = [
    // Arabic × Arabic
    "أوكي تم",
    "اوكي تم",
    "تمام ماشي",
    "تم زين",
    "طيب تمام",
    // EN × EN
    "ok done",
    "yes noted",
    "alright done",
    "sure okay",
    "ok got it",
    // EN × Arabizi
    "ok tamam",
    "yes mashi",
    // trailing punctuation
    "ok done.",
    "أوكي تم!",
  ];
  for (const text of multiWordAcks) {
    for (const slot of ["sender_name", "recipient_name"]) {
      const d = classifyResponseForSlot({ text, slot });
      assert.equal(
        d.kind,
        "acknowledgment",
        `expected acknowledgment for ${JSON.stringify(text)} on ${slot}, got ${d.kind} (${d.reason})`,
      );
      assert.equal(d.confidence, "high");
      const res = isAcceptableSlotResponse({ text, slot });
      assert.equal(res.acceptable, false, `${JSON.stringify(text)} must not be acceptable for ${slot}`);
    }
  }

  // Fast-path for ASK_SENDER_NAME_AND_PHONE_DECISION must refuse
  // multi-word acks (this is the exact conv 19399 entry point that
  // used to write "أوكي تم" to sender_name).
  for (const text of ["أوكي تم", "ok done", "تمام ماشي", "yes noted"]) {
    const r = extractSenderNameAndDecision({ text });
    assert.equal(
      r.patch?.sender_name ?? null,
      null,
      `fast-path sender must refuse multi-word ack ${JSON.stringify(text)} as sender_name (reasons=${r.reasons?.join(",")})`,
    );
  }

  // Negative — "ok Ali" has only ONE ack token + a real-name token,
  // which must NOT be swallowed as an ack (still lets the boundary's
  // own validator decide).
  {
    const d = classifyResponseForSlot({ text: "ok Ali", slot: "sender_name" });
    assert.notEqual(
      d.kind,
      "acknowledgment",
      `"ok Ali" must not be classified as a two-word ack`,
    );
  }
  // Identity cut (2026-04-26): legitimate names and phone decisions no
  // longer extract via the fast-path. The LLM/tool path owns the whole
  // sender identity tuple.
  {
    const r = extractSenderNameAndDecision({ text: "Aziz Al Mulla, use whatsapp" });
    assert.equal(
      r.patch?.sender_name ?? null,
      null,
      "Phase 1: fast-path must not write sender_name from letters+spaces",
    );
    assert.equal(r.patch, null);
    assert.equal(r.confidence, "none");
  }

  // -------------------------------------------------------------------------
  // Fix 2 — labeled recipient answers (historical)
  //
  // Phase 1 authority cut (2026-04-24): the entire recipient
  // combined extractor is now a shim returning `none`. The LLM owns
  // every recipient-name write via `apply_booking_field`. The
  // tests below used to assert label-stripping and clean extraction;
  // we now pin the opposite — the fast-path must NOT write a
  // `recipient_name` on any of these shapes.
  // -------------------------------------------------------------------------
  const recipientCombinedShapes = [
    "اسم احمد باشا رقم 5207777",
    "الاسم احمد باشا الرقم 5207777",
    "name Ahmed Basha phone 52077777",
    "رقم 5207777",
    "Mohammed Hamad 99887766",
  ];
  for (const text of recipientCombinedShapes) {
    const r = extractRecipientNameAndPhone({ text });
    assert.equal(
      r.confidence,
      "none",
      `Phase 1: recipient combined fast-path must be disabled; ${JSON.stringify(text)} leaked confidence=${r.confidence}`,
    );
    assert.equal(
      r.patch,
      null,
      `Phase 1: recipient combined fast-path must return null patch for ${JSON.stringify(text)}`,
    );
  }

  // -------------------------------------------------------------------------
  // Identity cut — no pre-LLM name/phone writes; LLM/tool proposals commit.
  // -------------------------------------------------------------------------
  {
    const pre = extractForNextAction({
      text: "حمد الملا 97485758",
      action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      whatsappNumber: "96599338566",
    });
    assert.equal(pre.patch, null, "recipient name+phone must not trigger sender phone fast-path");
    assert.equal(pre.confidence, "none");

    const draft = {
      ...createEmptyBookingDraft(),
      senderName: "aziz almulla",
      senderPhone: "96599338566",
    };
    let state = createEmptyDialogState();
    state = updateSlot(state, "sender_name", "aziz almulla", "llm_apply").state;
    state = updateSlot(state, "sender_phone", "96599338566", "llm_apply").state;
    const res = applyProposals([
      llmProposal({
        op: {
          recipient_name: "حمد الملا",
          recipient_phone: "97485758",
          source_quote: "حمد الملا 97485758",
        },
      }),
    ], {
      draft,
      dialogState: state,
      whatsappNumber: "96599338566",
      stage: "collecting_booking_details",
    });
    assert.equal(res.draft.recipientName, "حمد الملا");
    assert.equal(res.draft.recipientPhone, "97485758");
    assert.ok(res.applied.includes("recipient_name"));
    assert.ok(res.applied.includes("recipient_phone"));
    assert.equal(res.rejections.length, 0);
  }

  {
    const pre = extractForNextAction({
      text: "99383746",
      action: "ASK_SENDER_PHONE",
      whatsappNumber: "96599338566",
    });
    assert.equal(pre.patch, null, "sender phone digits must be LLM/tool-owned");
    assert.equal(pre.confidence, "none");

    const res = applyProposals([
      llmProposal({
        op: {
          sender_phone: "99383746",
          phone_decision: "different",
          source_quote: "99383746",
        },
      }),
    ], {
      draft: createEmptyBookingDraft(),
      dialogState: createEmptyDialogState(),
      whatsappNumber: "96599338566",
      stage: "collecting_booking_details",
    });
    assert.equal(res.draft.senderPhone, "99383746");
    assert.ok(res.applied.includes("sender_phone"));
    assert.equal(res.rejections.length, 0);
  }

  {
    const pre = extractForNextAction({
      text: "Abdulaziz almulla same number as whatsapp",
      action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      whatsappNumber: "96599338566",
    });
    assert.equal(pre.patch, null, "sender name + WhatsApp decision must be LLM/tool-owned");
    assert.equal(pre.confidence, "none");

    const res = applyProposals([
      llmProposal({
        op: {
          sender_name: "Abdulaziz almulla",
          phone_decision: "use_whatsapp",
          source_quote: "Abdulaziz almulla same number as whatsapp",
        },
      }),
    ], {
      draft: createEmptyBookingDraft(),
      dialogState: createEmptyDialogState(),
      whatsappNumber: "96599338566",
      stage: "collecting_booking_details",
    });
    assert.equal(res.draft.senderName, "Abdulaziz almulla");
    assert.equal(res.draft.senderPhone, "96599338566");
    assert.ok(res.applied.includes("sender_name"));
    assert.ok(res.applied.includes("phone_decision"));
    assert.equal(res.rejections.length, 0);
  }

  {
    const draft = {
      ...createEmptyBookingDraft(),
      senderPhone: "96599338566",
    };
    let state = createEmptyDialogState();
    state = updateSlot(state, "sender_phone", "96599338566", "llm_apply").state;
    const conflicted = applyProposals([
      fastPathProposal({
        patch: {
          sender_phone: "97485758",
          phone_decision: "different",
        },
        sourceQuote: "97485758",
      }),
    ], {
      draft,
      dialogState: state,
      whatsappNumber: "96599338566",
      stage: "collecting_booking_details",
    });
    assert.equal(conflicted.draft.senderPhone, "96599338566");
    assert.equal(conflicted.conflicts.length, 1);
    assert.ok(
      conflicted.rejections.some((r) => r.field === "sender_phone" && r.reason === "slot_conflict_with_filled_value"),
      `expected sender_phone conflict rejection, got ${JSON.stringify(conflicted.rejections)}`,
    );
    assert.ok(
      !conflicted.applied.includes("sender_phone") && !conflicted.applied.includes("phone_decision"),
      `conflicted fast-path write must not count as applied: ${JSON.stringify(conflicted.applied)}`,
    );
    const out = applyCrossSidePhoneGuard({
      fastPathPreApplied: conflicted.applied,
      senderPhone: null,
      recipientPhone: "97485758",
    });
    assert.equal(out.recipientPhone, "97485758");
    assert.equal(out.drops.length, 0, "conflicted fast-path attempt must not mask LLM recipient_phone");
  }

  // -------------------------------------------------------------------------
  // Fix 3 — cross-side phone guard
  // -------------------------------------------------------------------------
  // Historical guard: if a committed same-turn pre-apply says sender_phone,
  // a mirrored recipient side must be dropped.
  {
    const out = applyCrossSidePhoneGuard({
      fastPathPreApplied: ["sender_phone", "phone_decision"],
      senderPhone: "99338566",
      recipientPhone: "99338566",
    });
    assert.equal(out.senderPhone, "99338566", "same-side write must pass through");
    assert.equal(out.recipientPhone, null, "cross-side write must be dropped");
    assert.equal(out.drops.length, 1);
    assert.deepEqual(out.drops[0], {
      field: "recipient_phone",
      triggeredBy: "sender_phone",
      value: "99338566",
      reason: "cross_side_phone_write_same_turn",
    });
  }
  // Symmetric case — a committed same-turn recipient_phone pre-apply.
  {
    const out = applyCrossSidePhoneGuard({
      fastPathPreApplied: ["recipient_phone", "recipient_name"],
      senderPhone: "5207777",
      recipientPhone: "5207777",
    });
    assert.equal(out.senderPhone, null, "cross-side write must be dropped");
    assert.equal(out.recipientPhone, "5207777", "same-side write must pass through");
    assert.equal(out.drops.length, 1);
    assert.equal(out.drops[0].field, "sender_phone");
    assert.equal(out.drops[0].triggeredBy, "recipient_phone");
  }
  // No fast-path pre-apply → LLM patches pass through unchanged.
  {
    const out = applyCrossSidePhoneGuard({
      fastPathPreApplied: [],
      senderPhone: "99338566",
      recipientPhone: "5207777",
    });
    assert.equal(out.senderPhone, "99338566");
    assert.equal(out.recipientPhone, "5207777");
    assert.equal(out.drops.length, 0);
  }
  // Same-side idempotent write with no counterpart → no drop.
  {
    const out = applyCrossSidePhoneGuard({
      fastPathPreApplied: ["sender_phone"],
      senderPhone: "99338566",
      recipientPhone: null,
    });
    assert.equal(out.senderPhone, "99338566");
    assert.equal(out.recipientPhone, null);
    assert.equal(out.drops.length, 0);
  }
  // Fast-path pre-applied non-phone fields (e.g. name) → phones pass through.
  {
    const out = applyCrossSidePhoneGuard({
      fastPathPreApplied: ["recipient_name"],
      senderPhone: "99338566",
      recipientPhone: "5207777",
    });
    assert.equal(out.senderPhone, "99338566");
    assert.equal(out.recipientPhone, "5207777");
    assert.equal(out.drops.length, 0);
  }

  // -------------------------------------------------------------------------
  // Fix 4 — DST exposes conflictCandidate (the key the dispatch site
  // now reads), and the renderer produces the two-value prompt.
  // -------------------------------------------------------------------------
  {
    let state = createEmptyDialogState();
    // First write — accepted and filled.
    const r1 = updateSlot(state, "recipient_name", "احمد الباشا", "llm_apply");
    state = r1.state;
    assert.equal(r1.decision.action, "accepted");
    // Second write with a different value — raises a conflict and
    // stashes the incoming value on `conflictCandidate` (not
    // `conflictValue`).
    const r2 = updateSlot(state, "recipient_name", "محمد الباشا", "llm_apply");
    state = r2.state;
    assert.equal(r2.decision.action, "conflict");
    const rec = state.slots.recipient_name;
    assert.equal(rec?.status, "conflict");
    assert.equal(rec?.value, "احمد الباشا");
    assert.equal(
      rec?.conflictCandidate,
      "محمد الباشا",
      "DST must store incoming on `conflictCandidate` — the key the dispatch site reads",
    );
    // Verify the key name itself — a regression here would silently
    // re-break Fix 4's plumbing.
    assert.ok(
      Object.prototype.hasOwnProperty.call(rec, "conflictCandidate"),
      "SlotRecord must expose `conflictCandidate` (not `conflictValue`)",
    );
    assert.equal(
      rec?.conflictValue,
      undefined,
      "SlotRecord must NOT expose a `conflictValue` field (the original typo)",
    );

    // Renderer — with both values plumbed through, AR + EN must emit
    // the "«existing» or «incoming»?" shape.
    const arCtx = {
      language: "ar",
      draft: createEmptyBookingDraft(),
      entry: {},
      conflictingSlot: "recipient_name",
      conflictValues: { existing: rec.value, incoming: rec.conflictCandidate },
      turnSeed: "seed-ar",
    };
    const arResult = renderDirectiveReply("CONFIRM_SLOT_CONFLICT", arCtx);
    assert.equal(arResult.kind, "render");
    assert.ok(
      arResult.text.includes("احمد الباشا") && arResult.text.includes("محمد الباشا"),
      `AR two-value prompt must include both values, got: ${JSON.stringify(arResult.text)}`,
    );
    assert.ok(
      arResult.text.includes("«") && arResult.text.includes("»"),
      `AR two-value prompt must use Arabic quotation marks, got: ${JSON.stringify(arResult.text)}`,
    );
    assert.ok(
      !arResult.text.startsWith("القيمة الصحيحة لـ"),
      `AR must not fall back to the generic "القيمة الصحيحة لـ" prompt, got: ${JSON.stringify(arResult.text)}`,
    );

    const enCtx = { ...arCtx, language: "en", turnSeed: "seed-en" };
    const enResult = renderDirectiveReply("CONFIRM_SLOT_CONFLICT", enCtx);
    assert.equal(enResult.kind, "render");
    assert.ok(
      enResult.text.includes("احمد الباشا") && enResult.text.includes("محمد الباشا"),
      `EN two-value prompt must include both values, got: ${JSON.stringify(enResult.text)}`,
    );
    assert.ok(
      !enResult.text.startsWith("Correct value for"),
      `EN must not fall back to the generic "Correct value for" prompt, got: ${JSON.stringify(enResult.text)}`,
    );
  }

  // -------------------------------------------------------------------------
  // Recovery path notes (Phase 1 — 2026-04-24)
  //
  // The previous "fast-path extracts a clean recipient name → apply
  // boundary raises a well-formed conflict → renderer shows both
  // values" end-to-end recovery test was removed as part of the
  // Phase 1 authority cut. The premise — "the fast-path produces a
  // clean value to conflict against" — no longer holds: combined
  // recipient name+phone extraction is now LLM-owned. The same
  // recovery flow still works end-to-end; it's just driven by an
  // LLM-authored `apply_booking_field` tool op now, and that path
  // is covered by `smoke-test-slot-response-coherence.mjs` and the
  // apply-boundary DST tests rather than here.
  // -------------------------------------------------------------------------
  // Unused after Phase 1 cut (kept in the loader for brevity).
  void applyProposals; void llmProposal;

  console.log("smoke-test-slot-fill-fixes: OK");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
