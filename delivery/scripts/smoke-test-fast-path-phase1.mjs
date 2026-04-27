#!/usr/bin/env node
/**
 * Smoke test: Phase 1 fast-path authority cut (2026-04-24).
 *
 * Context
 * -------
 * On 2026-04-24 12:48 UTC (conv 20125) the pre-LLM deterministic
 * fast-path extractor wrote `sender_name = "No the avenues mall"` to
 * the controller state 20ms after the inbound arrived — BEFORE the LLM
 * was invoked or the turn disposition was classified. Root cause: the
 * "letters+spaces looks like a name" shape predicate inside
 * `extractSenderNameAndDecision` (and its recipient-combined
 * counterpart). That entire class of pre-LLM name-authority has been
 * removed in Phase 1. The LLM now owns every sender/recipient name
 * write via the `apply_booking_field` tool op; the apply-boundary
 * `validateName` still runs on that post-LLM path.
 *
 * This test pins the new contract. If any future change reintroduces a
 * pre-LLM name-writing branch through `extractForNextAction` or the
 * combined extractors, these assertions fail loudly.
 *
 * Cases (all six from the Phase 1 shipping checklist)
 * ----------------------------------------------------
 *   1. "No the avenues mall" on ASK_SENDER_NAME_AND_PHONE_DECISION
 *      MUST NOT write sender_name (the exact live-incident input).
 *   2. "Messilah" on ASK_SENDER_NAME_AND_PHONE_DECISION MUST NOT write
 *      sender_name (an area name that used to shape-pass).
 *   3. "Ahmed 99887766" on ASK_SENDER_NAME_AND_PHONE_DECISION MUST NOT
 *      write sender_name via the fast-path — the LLM owns that
 *      extraction. The phone alone does not create a combined write
 *      signal on this step.
 *   4. Pure phone digits on ASK_SENDER_PHONE must NOT write phone.
 *   5. Location pin → delivery role: `extractForNextAction` on
 *      ASK_DELIVERY_ADDRESS still applies a labeled address. The pin
 *      role assignment path lives in `applyPendingLocationRoleSelection`
 *      in octopus-channel and is NOT affected by this cut, so we only
 *      pin the closest shared behavior (delivery address fast-path).
 *   6. Labeled address "block 5 street 2 house 10" still extracts on
 *      ASK_PICKUP_ADDRESS (the address fast-path is unchanged).
 *
 * Also pinned:
 *   • ASK_SENDER_NAME returns `none` always (no fast-path).
 *   • ASK_RECIPIENT_NAME_AND_PHONE returns `none` always.
 *   • The `use_whatsapp` keyword is also LLM/tool-owned.
 */

import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  const fastPath = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/fast-path-extractor.ts"),
  );
  const {
    extractForNextAction,
    extractSenderNameAndDecision,
    extractRecipientNameAndPhone,
  } = fastPath;

  // -------------------------------------------------------------------------
  // Case 1 — "No the avenues mall" must not leak into sender_name.
  // -------------------------------------------------------------------------
  {
    const r = extractForNextAction({
      text: "No the avenues mall",
      action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      whatsappNumber: "96599338566",
    });
    assert.equal(
      r.patch?.sender_name ?? null,
      null,
      `Phase 1: "No the avenues mall" must not write sender_name. Got: ${JSON.stringify(r)}`,
    );
    assert.equal(
      r.patch,
      null,
      `Phase 1: "No the avenues mall" must produce no patch at all. Got: ${JSON.stringify(r)}`,
    );
    assert.equal(r.confidence, "none");
  }

  // -------------------------------------------------------------------------
  // Case 2 — "Messilah" (an area) must not leak into sender_name.
  // -------------------------------------------------------------------------
  {
    const r = extractForNextAction({
      text: "Messilah",
      action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      whatsappNumber: "96599338566",
    });
    assert.equal(
      r.patch?.sender_name ?? null,
      null,
      `Phase 1: "Messilah" must not write sender_name. Got: ${JSON.stringify(r)}`,
    );
    assert.equal(r.patch, null);
  }

  // -------------------------------------------------------------------------
  // Case 3 — "Ahmed 99887766" must not pre-write Ahmed as sender_name.
  //
  // The phone is structured, but sender-vs-recipient attribution is semantic.
  // A name + phone message is left entirely to the LLM/tool path.
  // -------------------------------------------------------------------------
  {
    const r = extractSenderNameAndDecision({ text: "Ahmed 99887766" });
    assert.equal(
      r.patch?.sender_name ?? null,
      null,
      `Phase 1: "Ahmed 99887766" must not write sender_name. Got: ${JSON.stringify(r)}`,
    );
  }

  // -------------------------------------------------------------------------
  // Case 4 — pure phone digits on ASK_SENDER_PHONE no longer write pre-LLM.
  // -------------------------------------------------------------------------
  {
    const r = extractForNextAction({
      text: "99887766",
      action: "ASK_SENDER_PHONE",
      whatsappNumber: "96599338566",
    });
    assert.equal(r.confidence, "none");
    assert.equal(r.patch, null);
    assert.ok(r.reasons.includes("llm_owned_sender_phone"));
  }
  // `use whatsapp` on ASK_SENDER_PHONE is also LLM/tool-owned.
  {
    const r = extractForNextAction({
      text: "use my whatsapp",
      action: "ASK_SENDER_PHONE",
      whatsappNumber: "96599338566",
    });
    assert.equal(r.confidence, "none");
    assert.equal(r.patch, null);
    assert.ok(r.reasons.includes("llm_owned_sender_phone"));
  }

  // -------------------------------------------------------------------------
  // Case 5 — delivery-side address fast-path is unchanged by Phase 1.
  //
  // (The pin→role assignment — the literal "location pin already
  // resolved, customer says 'delivery'" fast-path — lives in
  // `plugins/octopus-channel/index.ts::applyPendingLocationRoleSelection`
  // and is not touched by this cut. Here we pin the closest analogous
  // behavior that runs through this module: a labeled delivery
  // address still gets `address_role: "delivery"` applied.)
  // -------------------------------------------------------------------------
  {
    const r = extractForNextAction({
      text: "block 5 street 2 house 10",
      action: "ASK_DELIVERY_ADDRESS",
      whatsappNumber: null,
    });
    assert.equal(r.confidence, "high", `got reasons=${r.reasons?.join(",")}`);
    assert.equal(r.patch?.address_role, "delivery");
    assert.equal(r.patch?.address_block, "5");
    assert.equal(r.patch?.address_street, "2");
    assert.equal(r.patch?.address_house, "10");
  }

  // -------------------------------------------------------------------------
  // Case 6 — labeled pickup address still extracts.
  // -------------------------------------------------------------------------
  {
    const r = extractForNextAction({
      text: "block 5 street 2 house 10",
      action: "ASK_PICKUP_ADDRESS",
      whatsappNumber: null,
    });
    assert.equal(r.confidence, "high");
    assert.equal(r.patch?.address_role, "pickup");
    assert.equal(r.patch?.address_block, "5");
    assert.equal(r.patch?.address_street, "2");
    assert.equal(r.patch?.address_house, "10");
  }

  // -------------------------------------------------------------------------
  // Sanity — the dispatcher routes the removed branches to `none`.
  // -------------------------------------------------------------------------
  {
    const r = extractForNextAction({
      text: "Aziz Al Mulla",
      action: "ASK_SENDER_NAME",
      whatsappNumber: "96599338566",
    });
    assert.equal(r.confidence, "none");
    assert.equal(r.patch, null);
    assert.ok(
      r.reasons.includes("llm_owned_name_extraction"),
      `expected llm_owned_name_extraction in reasons, got [${r.reasons.join(",")}]`,
    );
  }
  {
    const r = extractForNextAction({
      text: "Mohammed Hamad 99887766",
      action: "ASK_RECIPIENT_NAME_AND_PHONE",
      whatsappNumber: "96599338566",
    });
    assert.equal(r.confidence, "none");
    assert.equal(r.patch, null);
    assert.ok(
      r.reasons.includes("llm_owned_recipient_combined"),
      `expected llm_owned_recipient_combined in reasons, got [${r.reasons.join(",")}]`,
    );
  }

  // -------------------------------------------------------------------------
  // Direct-call regression — recipient combined extractor never writes.
  // -------------------------------------------------------------------------
  for (const text of [
    "Mohammed Hamad 99887766",
    "Ahmad Basha 62844738",
    "No the avenues mall",
    "62844738",
    "",
  ]) {
    const r = extractRecipientNameAndPhone({ text });
    assert.equal(
      r.patch,
      null,
      `Phase 1: recipient combined fast-path must always return null; leaked on ${JSON.stringify(text)}`,
    );
    assert.equal(r.confidence, "none");
  }

  console.log("smoke-test-fast-path-phase1: OK");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
