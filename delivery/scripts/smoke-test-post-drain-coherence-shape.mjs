#!/usr/bin/env node
import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

const mod = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/octopus-channel/lib/post-drain-reply-coherence.ts"),
);

const { checkPostDrainReplyCoherence } = mod;

function snapshot(overrides = {}) {
  return {
    missingFields: [],
    addressSatisfaction: {
      pickup: true,
      delivery: true,
    },
    route: {
      lockStatus: "locked",
    },
    ...overrides,
  };
}

{
  const result = checkPostDrainReplyCoherence({
    replyText:
      "Order summary\n" +
      "Pickup: Northwest Sulaibikhat, block 2, street 7, house 19\n" +
      "Delivery: Zahra, block 2, street 9, apartment 11, floor 4, door 2\n" +
      "Sender: Abdulaziz, 99338566\n" +
      "Recipient: Ahmad, 99227462",
    bookingTruthSnapshot: snapshot(),
  });
  assert.equal(result.coherent, true, JSON.stringify(result.invalidations));
}

{
  const result = checkPostDrainReplyCoherence({
    replyText: "I still need the recipient phone before I can confirm.",
    bookingTruthSnapshot: snapshot(),
  });
  assert.equal(result.coherent, false);
  assert.equal(result.invalidations[0]?.field, "recipient.phone");
}

{
  const result = checkPostDrainReplyCoherence({
    replyText: "Please send me the pickup block.",
    bookingTruthSnapshot: snapshot(),
  });
  assert.equal(result.coherent, false);
  assert.equal(result.invalidations[0]?.kind, "asks_for_satisfied_address_field");
}

{
  const result = checkPostDrainReplyCoherence({
    replyText: "Pickup block?",
    bookingTruthSnapshot: snapshot(),
  });
  assert.equal(result.coherent, false);
  assert.equal(result.invalidations[0]?.field, "pickup.block");
}

console.log("ok - post-drain coherence distinguishes saved-fact statements from asks");
