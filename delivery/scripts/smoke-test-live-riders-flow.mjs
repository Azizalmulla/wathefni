#!/usr/bin/env node
import {
  ageLiveQuoteState,
  compactWhitespace,
  containsArabic,
  containsEmoji,
  containsUrl,
  createRunContext,
  ensureLiveGatewayReady,
  fetchGatewayLogs,
  fetchGatewayLogsByNeedle,
  fetchSessionSnapshot,
  findToolCallsAfter,
  findToolResultsAfter,
  getLiveSmokeConfig,
  postRawWebhookRequest,
  postAudioTurn,
  postImageTurn,
  postLocationTurn,
  postTextTurn,
  printTranscriptTail,
  resetLiveConversationState,
  waitForAssistantReply,
  waitForGatewayReplyLog,
} from "./live-riders-harness.mjs";

const TEST_IMAGE_URL = "https://dummyimage.com/600x400/ffffff/000000.png&text=package";
const ALT_DROPOFF_INPUT = "Jahra";
const ALT_DROPOFF_EXPECTED = "Jahra";
const FARWANIYA_COORDS = {
  latitude: 29.2775,
  longitude: 47.9586,
};
const BAYAN_COORDS = {
  latitude: 29.3031,
  longitude: 48.0478,
};

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function failWithSnapshot(message, snapshot) {
  const error = new Error(message);
  error.snapshot = snapshot;
  throw error;
}

function assertWithSnapshot(condition, message, snapshot) {
  if (!condition) {
    failWithSnapshot(message, snapshot);
  }
}

function parseArgs(argv) {
  const result = {
    scenario: "all",
    list: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--list") {
      result.list = true;
      continue;
    }
    if (arg === "--scenario" && argv[index + 1]) {
      result.scenario = argv[index + 1];
      index += 1;
      continue;
    }
  }
  return result;
}

function assertEnglishNoEmoji(text, label) {
  assert(!containsArabic(text), `${label} should stay in English, but Arabic text was found: ${text}`);
  assert(!containsEmoji(text), `${label} should not contain emojis: ${text}`);
}

function assertArabicNoEmoji(text, label) {
  assert(containsArabic(text), `${label} should stay in Arabic, but Arabic text was not found: ${text}`);
  assert(!containsEmoji(text), `${label} should not contain emojis: ${text}`);
}

function assertNoToolCallsAfter(snapshot, timestampMs, toolNames, message) {
  const names = Array.isArray(toolNames) ? toolNames : [toolNames];
  const unexpected = names.flatMap((toolName) => findToolCallsAfter(snapshot, timestampMs, toolName));
  assertWithSnapshot(
    unexpected.length === 0,
    `${message} Unexpected tools: ${unexpected.map((event) => event.toolName).join(", ") || "none"}`,
    snapshot,
  );
}

async function assertInterpreterActionLogged(config, run, acceptedAtMs, expectedAction, label) {
  const logLines = await fetchGatewayLogs(config, run, acceptedAtMs, "[turn-interpreter]");
  assert(
    logLines.some((line) => line.includes(`action=${expectedAction}`)),
    `${label} should log turn-interpreter action=${expectedAction}. Logs: ${logLines.slice(-6).join(" | ")}`,
  );
}

async function waitForIngressLog(config, requestId, needle, label) {
  const deadline = Date.now() + config.timeoutMs;
  let lastLines = [];
  while (Date.now() <= deadline) {
    lastLines = await fetchGatewayLogsByNeedle(config, Date.now() - (config.timeoutMs + 5_000), requestId);
    if (lastLines.some((line) => line.includes(needle))) {
      return lastLines;
    }
    await new Promise((resolve) => setTimeout(resolve, config.pollMs));
  }
  throw new Error(`Timed out waiting for ${needle} after ${label}. Last lines: ${lastLines.slice(-8).join(" | ")}`);
}

function mentionsSenderStep(text) {
  return /(sender'?s? full name|full name for the sender|name for the sender|sender, and confirm|sender phone)/i.test(text);
}

function mentionsSenderStepArabic(text) {
  return /(اسم.*المرسل|رقم.*المرسل|اسم صاحب الطلب|هاتف المرسل)/i.test(text);
}

function logStep(name, text) {
  console.log(`\n[step] ${name}`);
  console.log(`  customer: ${text}`);
}

async function runTurn(config, run, stepName, text) {
  logStep(stepName, text);
  const ack = await postTextTurn(config, run, text);
  const { snapshot, reply } = await waitForOutboundReply(config, run, ack.acceptedAtMs, stepName);
  console.log(`  assistant: ${compactWhitespace(reply.text)}`);
  return { ack, snapshot, reply };
}

async function runLocationPayload(config, run, stepName, params) {
  logStep(stepName, params.text || "Location payload");
  const ack = await postLocationTurn(config, run, params);
  assert(ack.response?.has_location_message, `Location payload was not accepted as a location message: ${JSON.stringify(ack.response)}`);
  const { snapshot, reply } = await waitForOutboundReply(config, run, ack.acceptedAtMs, stepName);
  console.log(`  assistant: ${compactWhitespace(reply.text)}`);
  return { ack, snapshot, reply };
}

async function runAudioPayload(config, run, stepName, params) {
  logStep(stepName, params.text || params.textToSpeech || "Voice note");
  const ack = await postAudioTurn(config, run, params);
  assert(ack.response?.has_audio_message, `Audio payload was not accepted as an audio message: ${JSON.stringify(ack.response)}`);
  const { snapshot, reply } = await waitForOutboundReply(config, run, ack.acceptedAtMs, stepName);
  console.log(`  assistant: ${compactWhitespace(reply.text)}`);
  return { ack, snapshot, reply };
}

async function runDeterministicLocationPayload(config, run, stepName, params) {
  logStep(stepName, params.text || "Location payload");
  const ack = await postLocationTurn(config, run, params);
  assert(ack.response?.has_location_message, `Location payload was not accepted as a location message: ${JSON.stringify(ack.response)}`);
  const locationReply = await waitForGatewayReplyLog(
    config,
    run,
    ack.acceptedAtMs,
    "Deterministic location clarification reply sent",
    stepName,
  );
  console.log(`  assistant: ${compactWhitespace(locationReply.reply.text)}`);
  return {
    ack,
    snapshot: locationReply.snapshot,
    reply: locationReply.reply,
  };
}

async function runDeterministicBookingTurn(config, run, stepName, text) {
  logStep(stepName, text);
  const ack = await postTextTurn(config, run, text);
  let bookingReply;
  let snapshot;
  try {
    bookingReply = await waitForGatewayReplyLog(
      config,
      run,
      ack.acceptedAtMs,
      "Deterministic booking-details reply sent",
      stepName,
    );
    snapshot = await fetchSessionSnapshot(config, run);
  } catch (error) {
    const fallback = await waitForOutboundReply(config, run, ack.acceptedAtMs, stepName);
    bookingReply = { reply: fallback.reply, snapshot: fallback.snapshot };
    snapshot = fallback.snapshot;
    if (error instanceof Error) {
      console.log(`  note: deterministic booking log marker missing, accepted outbound reply fallback (${compactWhitespace(error.message)})`);
    }
  }
  console.log(`  assistant: ${compactWhitespace(bookingReply.reply.text)}`);
  return {
    ack,
    snapshot,
    reply: bookingReply.reply,
  };
}

async function waitForOutboundReply(config, run, acceptedAtMs, label) {
  try {
    const outboundReply = await waitForGatewayReplyLog(
      config,
      run,
      acceptedAtMs,
      "outbound reply sent",
      label,
    );
    const snapshot = await fetchSessionSnapshot(config, run);
    return {
      reply: outboundReply.reply,
      snapshot,
    };
  } catch (error) {
    const fallback = await waitForAssistantReply(config, run, acceptedAtMs, label);
    if (error instanceof Error) {
      console.log(`  note: outbound log marker missing, accepted assistant-session fallback (${compactWhitespace(error.message)})`);
    }
    return fallback;
  }
}

async function runMapLinkPricing(config) {
  const run = await createRunContext(config);
  const mapLink = `https://maps.google.com/?q=${encodeURIComponent(config.pickupInput)}`;
  const message = `How much from ${mapLink} to ${config.dropoffInput}?`;
  console.log(`[run] scenario=map-link-pricing runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  const pricing = await runTurn(config, run, "map-link pricing", message);
  assertEnglishNoEmoji(pricing.reply.text, "Map-link pricing reply");
  assert(
    pricing.reply.text.includes(config.pickupExpected) && pricing.reply.text.includes(config.dropoffExpected),
    `Map-link pricing reply should mention ${config.pickupExpected} and ${config.dropoffExpected}: ${pricing.reply.text}`,
  );
  assert(/Price:\s*\d+\.\d{3}\s*KWD/i.test(pricing.reply.text), `Map-link pricing reply should contain a structured price: ${pricing.reply.text}`);
  return {
    run,
    sessionFile: pricing.snapshot.sessionFile,
  };
}

async function runLocationPinIntake(config) {
  const run = await createRunContext(config);
  console.log(`[run] scenario=location-pin-intake runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  const { ack, snapshot, reply } = await runDeterministicLocationPayload(config, run, "location pin", {
    text: "Pickup location",
    latitude: FARWANIYA_COORDS.latitude,
    longitude: FARWANIYA_COORDS.longitude,
    name: config.pickupExpected,
    address: `${config.pickupExpected}, Kuwait`,
  });
  assertEnglishNoEmoji(reply.text, "Location-pin reply");
  assert(
    /(delivery|drop[- ]?off|destination|where.*deliver|where.*send)/i.test(reply.text),
    `Location-pin reply should ask for the destination or delivery side: ${reply.text}`,
  );
  assert(
    !/(block|street|house|building)/i.test(reply.text),
    `Location-pin reply should not ask for block/street/house when the pin is the address: ${reply.text}`,
  );
  assertNoToolCallsAfter(
    snapshot,
    ack.acceptedAtMs,
    ["get_price", "assign_agent", "create_simple_order"],
    "A lone location pin should not trigger pricing or order creation.",
  );
  return {
    run,
    sessionFile: snapshot.sessionFile,
  };
}

async function runStickyLanguageLocationPin(config) {
  const run = await createRunContext(config);
  console.log(`[run] scenario=location-pin-language-sticky-regression runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  const arabicSwitch = await runTurn(config, run, "explicit arabic switch", "بالعربي");
  assertArabicNoEmoji(arabicSwitch.reply.text, "Explicit Arabic switch reply");
  const englishReset = await runTurn(config, run, "english reset", "Hi");
  assertEnglishNoEmoji(englishReset.reply.text, "English reset reply");
  const locationTurn = await runDeterministicLocationPayload(config, run, "pin-only after english reset", {
    latitude: FARWANIYA_COORDS.latitude,
    longitude: FARWANIYA_COORDS.longitude,
    name: config.pickupExpected,
    address: `${config.pickupExpected}, Kuwait`,
  });
  assertEnglishNoEmoji(locationTurn.reply.text, "Sticky-language location reply");
  assert(
    /(delivery|drop[- ]?off|destination|where.*deliver|where.*send|pickup)/i.test(locationTurn.reply.text),
    `Sticky-language location reply should ask whether the pin is for pickup or delivery: ${locationTurn.reply.text}`,
  );
  assert(
    !/(block|street|house|building)/i.test(locationTurn.reply.text),
    `Sticky-language location reply should not ask for block/street/house when the pin is the address: ${locationTurn.reply.text}`,
  );
  assertNoToolCallsAfter(
    locationTurn.snapshot,
    locationTurn.ack.acceptedAtMs,
    ["get_price", "assign_agent", "create_simple_order"],
    "A pin-only turn after an English reset should stay inside location clarification.",
  );
  return {
    run,
    sessionFile: locationTurn.snapshot.sessionFile,
  };
}

async function runArabicLocationPinIntake(config) {
  const run = await createRunContext(config);
  console.log(`[run] scenario=arabic-location-pin-intake runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  const arabicGreeting = await runTurn(config, run, "arabic greeting before pin", "السلام عليكم");
  assertArabicNoEmoji(arabicGreeting.reply.text, "Arabic pre-pin greeting");
  const locationTurn = await runDeterministicLocationPayload(config, run, "arabic pin-only", {
    latitude: FARWANIYA_COORDS.latitude,
    longitude: FARWANIYA_COORDS.longitude,
    name: config.pickupExpected,
    address: `${config.pickupExpected}, Kuwait`,
  });
  assertArabicNoEmoji(locationTurn.reply.text, "Arabic location-pin reply");
  assert(
    /(الاستلام|التسليم|التوصيل|الوجهة)/i.test(locationTurn.reply.text),
    `Arabic location reply should ask whether the pin is for pickup or delivery: ${locationTurn.reply.text}`,
  );
  assert(
    !/(بلوك|شارع|منزل|بيت|block|street|house|building)/i.test(locationTurn.reply.text),
    `Arabic location reply should not ask for block/street/house when the pin is the address: ${locationTurn.reply.text}`,
  );
  return {
    run,
    sessionFile: locationTurn.snapshot.sessionFile,
  };
}

async function runImagePricing(config) {
  const run = await createRunContext(config);
  console.log(`[run] scenario=image-pricing runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  logStep("image pricing", "Image with pricing caption");
  const ack = await postImageTurn(config, run, {
    imageUrl: TEST_IMAGE_URL,
    mimeType: "image/png",
    caption: `How much from ${config.pickupInput} to ${config.dropoffInput}?`,
  });
  assert(ack.response?.has_image_message, `Image payload was not accepted as an image message: ${JSON.stringify(ack.response)}`);
  const { snapshot, reply } = await waitForOutboundReply(config, run, ack.acceptedAtMs, "image pricing");
  console.log(`  assistant: ${compactWhitespace(reply.text)}`);
  assertEnglishNoEmoji(reply.text, "Image pricing reply");
  assert(
    reply.text.includes(config.pickupExpected) && reply.text.includes(config.dropoffExpected),
    `Image pricing reply should mention ${config.pickupExpected} and ${config.dropoffExpected}: ${reply.text}`,
  );
  assert(/Price:\s*\d+\.\d{3}\s*KWD/i.test(reply.text), `Image pricing reply should contain a structured price: ${reply.text}`);
  const imageLogs = await fetchGatewayLogs(config, run, ack.acceptedAtMs, "image saved");
  assert(imageLogs.length > 0, "Expected the gateway logs to confirm the inbound image was saved.");
  return {
    run,
    sessionFile: snapshot.sessionFile,
  };
}

async function runImageTrackingGuard(config) {
  const run = await createRunContext(config);
  console.log(`[run] scenario=image-tracking-guard runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  logStep("image tracking without order id", "Image with tracking caption");
  const ack = await postImageTurn(config, run, {
    imageUrl: TEST_IMAGE_URL,
    mimeType: "image/png",
    caption: "Track my order",
  });
  assert(ack.response?.has_image_message, `Image payload was not accepted as an image message: ${JSON.stringify(ack.response)}`);
  const trackingReply = await waitForGatewayReplyLog(
    config,
    run,
    ack.acceptedAtMs,
    "deterministic tracking guard reply sent",
    "image tracking without order id",
  );
  console.log(`  assistant: ${compactWhitespace(trackingReply.reply.text)}`);
  assertEnglishNoEmoji(trackingReply.reply.text, "Image tracking guard reply");
  assert(
    /ORDER-/i.test(trackingReply.reply.text),
    `Image tracking guard reply should ask for an ORDER- number: ${trackingReply.reply.text}`,
  );
  const imageLogs = await fetchGatewayLogs(config, run, ack.acceptedAtMs, "image saved");
  assert(imageLogs.length > 0, "Expected the gateway logs to confirm the inbound image was saved.");
  const logLines = await fetchGatewayLogs(config, run, ack.acceptedAtMs, "");
  assert(
    !logLines.some((line) => line.includes("tool:track_order")),
    `Image tracking guard should not invoke track_order without an order id. Logs: ${logLines.slice(-6).join(" | ")}`,
  );
  return {
    run,
    sessionFile: trackingReply.snapshot.sessionFile,
  };
}

async function runAudioPricing(config) {
  const run = await createRunContext(config);
  console.log(`[run] scenario=audio-pricing runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  const routePrompt = `How much from ${config.pickupInput} to ${config.dropoffInput}`;
  const { ack, snapshot, reply } = await runAudioPayload(config, run, "audio pricing", {
    textToSpeech: routePrompt,
  });
  assertEnglishNoEmoji(reply.text, "Audio pricing reply");
  assert(
    reply.text.includes(config.pickupExpected) && reply.text.includes(config.dropoffExpected),
    `Audio pricing reply should mention ${config.pickupExpected} and ${config.dropoffExpected}: ${reply.text}`,
  );
  assert(/Price:\s*\d+\.\d{3}\s*KWD/i.test(reply.text), `Audio pricing reply should contain a structured price: ${reply.text}`);
  assertNoToolCallsAfter(
    snapshot,
    ack.acceptedAtMs,
    ["assign_agent", "track_order", "create_simple_order"],
    "Audio pricing should not escalate, track, or create an order.",
  );
  return {
    run,
    sessionFile: snapshot.sessionFile,
  };
}

async function runQuoteOptionFollowup(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  console.log(`[run] scenario=quote-option-followup runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  const pricing = await runTurn(config, run, "route pricing", `${config.pickupInput} to ${config.dropoffInput}`);
  assertEnglishNoEmoji(pricing.reply.text, "Quote-followup base pricing reply");
  await assertInterpreterActionLogged(config, run, pricing.ack.acceptedAtMs, "pricing_request", "Route pricing turn");
  const followup = await runTurn(config, run, "quote option follow-up", "What about express?");
  assertEnglishNoEmoji(followup.reply.text, "Quote option follow-up reply");
  assert(/express/i.test(followup.reply.text), `Quote option follow-up should mention express: ${followup.reply.text}`);
  assert(/KWD|KD/i.test(followup.reply.text), `Quote option follow-up should contain a price: ${followup.reply.text}`);
  await assertInterpreterActionLogged(config, run, followup.ack.acceptedAtMs, "same_route_quote_option", "Quote option follow-up turn");
  assertNoToolCallsAfter(
    followup.snapshot,
    followup.ack.acceptedAtMs,
    ["get_price", "assign_agent", "create_simple_order"],
    "Same-route quote follow-up should answer from quote state without repricing or escalation.",
  );
  return {
    run,
    sessionFile: followup.snapshot.sessionFile,
  };
}

async function runQuoteRouteChange(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  console.log(`[run] scenario=quote-route-change runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  const pricing = await runTurn(config, run, "base route pricing", `${config.pickupInput} to ${config.dropoffInput}`);
  assertEnglishNoEmoji(pricing.reply.text, "Quote route-change base pricing reply");
  await assertInterpreterActionLogged(config, run, pricing.ack.acceptedAtMs, "pricing_request", "Base route pricing turn");
  const followup = await runTurn(config, run, "route change after quote", `What about ${config.pickupInput} to ${ALT_DROPOFF_INPUT}?`);
  assertEnglishNoEmoji(followup.reply.text, "Route-change follow-up reply");
  assert(
    followup.reply.text.includes(config.pickupExpected) && new RegExp(ALT_DROPOFF_EXPECTED, "i").test(followup.reply.text),
    `Route-change follow-up should mention ${config.pickupExpected} and ${ALT_DROPOFF_EXPECTED}: ${followup.reply.text}`,
  );
  assert(/Price:\s*\d+\.\d{3}\s*KWD/i.test(followup.reply.text), `Route-change follow-up should contain a structured price: ${followup.reply.text}`);
  await assertInterpreterActionLogged(config, run, followup.ack.acceptedAtMs, "pricing_request", "Route change follow-up turn");
  const getPriceCalls = findToolCallsAfter(followup.snapshot, followup.ack.acceptedAtMs, "get_price");
  assert(getPriceCalls.length > 0, "Changing the route after a quote should trigger a fresh get_price lookup.");
  return {
    run,
    sessionFile: followup.snapshot.sessionFile,
  };
}

async function runArabicQuoteBookingFollowup(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  console.log(`[run] scenario=arabic-quote-booking-followup runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  const pricing = await runTurn(config, run, "arabic route pricing", "بكم من الفروانية إلى حولي");
  assertArabicNoEmoji(pricing.reply.text, "Arabic quote reply");
  const followup = await runDeterministicBookingTurn(config, run, "arabic quote booking follow-up", "ابي اكمل");
  assertArabicNoEmoji(followup.reply.text, "Arabic quote booking-start reply");
  assert(
    mentionsSenderStepArabic(followup.reply.text),
    `Arabic quote follow-up should start sender step in Arabic: ${followup.reply.text}`,
  );
  assertNoToolCallsAfter(
    followup.snapshot,
    followup.ack.acceptedAtMs,
    ["assign_agent", "create_simple_order", "get_price"],
    "Arabic quote booking follow-up should start booking without repricing or escalation.",
  );
  return {
    run,
    sessionFile: followup.snapshot.sessionFile,
  };
}

async function runArabicUnorthodoxFlow(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  console.log(`[run] scenario=arabic-unorthodox-flow runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);

  const greeting = await runTurn(config, run, "arabic greeting", "هلا");
  assertArabicNoEmoji(greeting.reply.text, "Arabic unorthodox greeting reply");
  assert(/هلا|حياكم|شلون/i.test(greeting.reply.text), `Arabic greeting reply looked wrong: ${greeting.reply.text}`);

  const ambiguous = await runTurn(config, run, "ambiguous arabic pricing ask", "ابي السعر");
  assertArabicNoEmoji(ambiguous.reply.text, "Ambiguous Arabic pricing reply");
  assert(
    /منطقة|الاستلام|التوصيل|من وين|إلى وين|اسم المنطقة/i.test(ambiguous.reply.text),
    `Ambiguous Arabic pricing reply should ask for route details: ${ambiguous.reply.text}`,
  );
  const ambiguousLogs = await fetchGatewayLogs(config, run, ambiguous.ack.acceptedAtMs, "[turn-interpreter]");
  assert(
    ambiguousLogs.some((line) => line.includes("action=clarify") || line.includes("action=pricing_request")),
    `Ambiguous Arabic pricing turn should be clarify or pricing_request. Logs: ${ambiguousLogs.slice(-6).join(" | ")}`,
  );
  assertNoToolCallsAfter(
    ambiguous.snapshot,
    ambiguous.ack.acceptedAtMs,
    ["get_price", "assign_agent", "create_simple_order", "track_order"],
    "An ambiguous Arabic pricing ask should request missing route details before using tools.",
  );

  const pricing = await runTurn(config, run, "unorthodox arabic route pricing", "بكم التوصيل من حولي حق سلوى");
  assertArabicNoEmoji(pricing.reply.text, "Unorthodox Arabic pricing reply");
  assert(
    /حولي/i.test(pricing.reply.text) && /سلوى/i.test(pricing.reply.text),
    `Arabic pricing reply should mention Hawalli and Salwa in Arabic: ${pricing.reply.text}`,
  );
  assert(/1\.250|KWD/i.test(pricing.reply.text), `Arabic pricing reply should contain the structured price: ${pricing.reply.text}`);
  await assertInterpreterActionLogged(config, run, pricing.ack.acceptedAtMs, "pricing_request", "Arabic route pricing turn");

  const standardOnly = await runTurn(config, run, "arabic standard-only follow-up", "بس العادي؟");
  assertArabicNoEmoji(standardOnly.reply.text, "Arabic standard-only follow-up reply");
  assert(
    /العادي|سيارة عادية|ستاندرد/i.test(standardOnly.reply.text),
    `Arabic standard-only follow-up should answer the same-route standard option: ${standardOnly.reply.text}`,
  );
  assert(/1\.250|KWD/i.test(standardOnly.reply.text), `Arabic standard-only follow-up should contain a price: ${standardOnly.reply.text}`);
  assertNoToolCallsAfter(
    standardOnly.snapshot,
    standardOnly.ack.acceptedAtMs,
    ["get_price", "assign_agent", "create_simple_order"],
    "Same-route Arabic standard follow-up should answer from quote context without repricing.",
  );

  const express = await runTurn(config, run, "arabic express follow-up", "وشنو السريع؟");
  assertArabicNoEmoji(express.reply.text, "Arabic express follow-up reply");
  assert(
    /السريع|سريع/i.test(express.reply.text),
    `Arabic express follow-up should mention the express option: ${express.reply.text}`,
  );
  assert(/1\.750|KWD/i.test(express.reply.text), `Arabic express follow-up should contain the express price: ${express.reply.text}`);
  await assertInterpreterActionLogged(config, run, express.ack.acceptedAtMs, "same_route_quote_option", "Arabic express follow-up turn");
  assertNoToolCallsAfter(
    express.snapshot,
    express.ack.acceptedAtMs,
    ["get_price", "assign_agent", "create_simple_order"],
    "Same-route Arabic express follow-up should answer from quote context without repricing.",
  );

  const otherOptions = await runTurn(config, run, "arabic other-options follow-up", "وشنو غيره؟");
  assertArabicNoEmoji(otherOptions.reply.text, "Arabic other-options reply");
  assert(
    /بوكس|مبرد|مساعد|خيارات/i.test(otherOptions.reply.text),
    `Arabic other-options reply should surface alternative services: ${otherOptions.reply.text}`,
  );
  await assertInterpreterActionLogged(config, run, otherOptions.ack.acceptedAtMs, "same_route_show_other_options", "Arabic other-options turn");

  const bookingStart = await runDeterministicBookingTurn(config, run, "arabic ambiguous booking yes", "نعم");
  assertArabicNoEmoji(bookingStart.reply.text, "Arabic booking-start after unorthodox flow");
  assert(
    mentionsSenderStepArabic(bookingStart.reply.text),
    `Arabic yes after quote should start booking with sender step: ${bookingStart.reply.text}`,
  );
  await assertInterpreterActionLogged(config, run, bookingStart.ack.acceptedAtMs, "start_booking", "Arabic booking-start turn");
  assertNoToolCallsAfter(
    bookingStart.snapshot,
    bookingStart.ack.acceptedAtMs,
    ["get_price", "assign_agent", "create_simple_order"],
    "Arabic yes after quote should start booking without repricing or escalation.",
  );

  return {
    run,
    sessionFile: bookingStart.snapshot.sessionFile,
  };
}

async function runBookingHappyPath(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  const routePrompt = `${config.pickupInput} to ${config.dropoffInput}`;
  let successReplyText = null;

  console.log(`[run] scenario=booking-happy-path runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=true replyTarget=${run.replyTarget} marker=${run.marker}`);

  const greeting = await runTurn(config, run, "english greeting", "Hi");
  assertEnglishNoEmoji(greeting.reply.text, "Greeting reply");
  assert(/riders|help/i.test(greeting.reply.text), `Greeting reply looked wrong: ${greeting.reply.text}`);

  const pricing = await runTurn(config, run, "route pricing", routePrompt);
  assertEnglishNoEmoji(pricing.reply.text, "Pricing reply");
  const pricingLogs = await fetchGatewayLogs(config, run, pricing.ack.acceptedAtMs, "[turn-interpreter]");
  assert(
    pricingLogs.some((line) => line.includes("action=pricing_request") || line.includes("action=clarify")),
    `Happy-path pricing turn should be pricing_request or clarify. Logs: ${pricingLogs.slice(-6).join(" | ")}`,
  );
  assert(
    pricing.reply.text.includes(config.pickupExpected) && pricing.reply.text.includes(config.dropoffExpected),
    `Pricing reply should mention ${config.pickupExpected} and ${config.dropoffExpected}: ${pricing.reply.text}`,
  );
  assert(/Price:\s*\d+\.\d{3}\s*KWD/i.test(pricing.reply.text), `Pricing reply should contain a structured price: ${pricing.reply.text}`);
  assert(!/Available for booking|Shall we proceed/i.test(pricing.reply.text), `Pricing reply should not force a booking CTA: ${pricing.reply.text}`);

  const bookingStart = await runDeterministicBookingTurn(config, run, "booking follow-up", "Yes");
  assertEnglishNoEmoji(bookingStart.reply.text, "Booking-start reply");
  await assertInterpreterActionLogged(config, run, bookingStart.ack.acceptedAtMs, "start_booking", "Happy-path booking-start turn");
  assert(mentionsSenderStep(bookingStart.reply.text), `Booking should start with sender step only: ${bookingStart.reply.text}`);
  assert(!/recipient/i.test(bookingStart.reply.text), `Booking-start reply should not ask for recipient yet: ${bookingStart.reply.text}`);
  assertNoToolCallsAfter(
    bookingStart.snapshot,
    bookingStart.ack.acceptedAtMs,
    ["assign_agent", "create_simple_order"],
    "Booking start should stay inside the controller flow.",
  );

  const senderStep = await runDeterministicBookingTurn(
    config,
    run,
    "sender step",
    `${run.senderName} ${config.senderPhone}`,
  );
  assertWithSnapshot(
    findToolCallsAfter(senderStep.snapshot, senderStep.ack.acceptedAtMs, "create_simple_order").length === 0,
    `Sender step should not call create_simple_order yet. Reply was: ${senderStep.reply.text}`,
    senderStep.snapshot,
  );
  assertNoToolCallsAfter(
    senderStep.snapshot,
    senderStep.ack.acceptedAtMs,
    ["get_price", "assign_agent"],
    "Sender step should not re-price or escalate.",
  );
  assertWithSnapshot(
    /recipient full name/i.test(senderStep.reply.text),
    `Sender step should move to recipient step: ${senderStep.reply.text}`,
    senderStep.snapshot,
  );
  assertWithSnapshot(
    /recipient.*phone|phone number/i.test(senderStep.reply.text),
    `Sender step should request recipient phone: ${senderStep.reply.text}`,
    senderStep.snapshot,
  );

  const recipientStep = await runDeterministicBookingTurn(
    config,
    run,
    "recipient step",
    `${run.recipientName} ${run.recipientPhone}`,
  );
  assertWithSnapshot(
    findToolCallsAfter(recipientStep.snapshot, recipientStep.ack.acceptedAtMs, "create_simple_order").length === 0,
    `Recipient step should not call create_simple_order yet. Reply was: ${recipientStep.reply.text}`,
    recipientStep.snapshot,
  );
  assertNoToolCallsAfter(
    recipientStep.snapshot,
    recipientStep.ack.acceptedAtMs,
    ["get_price", "assign_agent"],
    "Recipient step should not re-price or escalate.",
  );
  assertWithSnapshot(
    /pickup block/i.test(recipientStep.reply.text),
    `Recipient step should move to pickup address step: ${recipientStep.reply.text}`,
    recipientStep.snapshot,
  );
  assertWithSnapshot(
    !/delivery block/i.test(recipientStep.reply.text),
    `Recipient step should not skip ahead to delivery address: ${recipientStep.reply.text}`,
    recipientStep.snapshot,
  );

  const pickupStep = await runDeterministicBookingTurn(config, run, "pickup address step", config.pickupAddressStep);
  assertNoToolCallsAfter(
    pickupStep.snapshot,
    pickupStep.ack.acceptedAtMs,
    ["get_price", "assign_agent", "create_simple_order"],
    "Pickup step should stay in booking collection.",
  );
  assertWithSnapshot(
    /delivery block/i.test(pickupStep.reply.text),
    `Pickup step should move to delivery address step: ${pickupStep.reply.text}`,
    pickupStep.snapshot,
  );

  const deliveryStep = await runTurn(config, run, "delivery address step", config.dropoffAddressStep);
  assertEnglishNoEmoji(deliveryStep.reply.text, "Summary reply");
  assertNoToolCallsAfter(
    deliveryStep.snapshot,
    deliveryStep.ack.acceptedAtMs,
    ["get_price", "assign_agent"],
    "Delivery step should not re-price or escalate before confirmation.",
  );
  assertWithSnapshot(
    deliveryStep.reply.text.includes(run.senderName),
    `Summary should mention sender name ${run.senderName}: ${deliveryStep.reply.text}`,
    deliveryStep.snapshot,
  );
  assertWithSnapshot(
    deliveryStep.reply.text.includes(run.recipientName),
    `Summary should mention recipient name ${run.recipientName}: ${deliveryStep.reply.text}`,
    deliveryStep.snapshot,
  );
  assertWithSnapshot(
    /proceed|confirm|shall i/i.test(deliveryStep.reply.text),
    `Summary should ask for explicit confirmation: ${deliveryStep.reply.text}`,
    deliveryStep.snapshot,
  );
  const preConfirmCreateResults = findToolResultsAfter(deliveryStep.snapshot, deliveryStep.ack.acceptedAtMs, "create_simple_order");
  const prematureSuccess = preConfirmCreateResults.find((result) => result?.json?.status === "ok");
  assertWithSnapshot(
    !prematureSuccess,
    "Order should not be successfully created before summary confirmation.",
    deliveryStep.snapshot,
  );
  const unexpectedPrematureFailure = preConfirmCreateResults.find((result) => {
    const message = String(result?.json?.message || result?.text || "");
    return message && !/Do not call create_simple_order yet/i.test(message);
  });
  assertWithSnapshot(
    !unexpectedPrematureFailure,
    `Unexpected create_simple_order failure before confirmation: ${unexpectedPrematureFailure?.text || "unknown"}`,
    deliveryStep.snapshot,
  );

  const confirmation = await runTurn(config, run, "summary confirmation", "Yes, confirm");
  await assertInterpreterActionLogged(config, run, confirmation.ack.acceptedAtMs, "confirm_summary", "Happy-path summary confirmation turn");
  const createCalls = findToolCallsAfter(confirmation.snapshot, confirmation.ack.acceptedAtMs, "create_simple_order");
  const createResults = findToolResultsAfter(confirmation.snapshot, confirmation.ack.acceptedAtMs, "create_simple_order");
  assert(createCalls.length > 0, "Expected create_simple_order to be called after confirming the summary.");
  assert(createResults.length > 0, "Expected a successful create_simple_order result after confirming the summary.");
  const latestCreateResult = createResults.at(-1);
  assert(latestCreateResult?.json?.status === "ok", `Order creation tool result was not ok: ${latestCreateResult?.text || "missing result"}`);
  assert(/Order ID:\s*ORDER-/i.test(confirmation.reply.text), `Success reply should contain the order ID: ${confirmation.reply.text}`);
  assert(containsUrl(confirmation.reply.text), `Success reply should contain the payment link: ${confirmation.reply.text}`);
  successReplyText = confirmation.reply.text;

  const postOrderGreeting = await runTurn(config, run, "post-order unrelated greeting", "Hi");
  assertEnglishNoEmoji(postOrderGreeting.reply.text, "Post-order greeting reply");
  assert(/riders|help/i.test(postOrderGreeting.reply.text), `Post-order greeting should return to a normal greeting: ${postOrderGreeting.reply.text}`);
  assert(!/ORDER-/i.test(postOrderGreeting.reply.text), `Post-order greeting should not replay an order ID: ${postOrderGreeting.reply.text}`);
  assert(!containsUrl(postOrderGreeting.reply.text), `Post-order greeting should not replay a payment link: ${postOrderGreeting.reply.text}`);
  assert(
    compactWhitespace(postOrderGreeting.reply.text) !== compactWhitespace(successReplyText),
    "Post-order greeting should not replay the previous order-success message.",
  );

  return {
    run,
    sessionFile: postOrderGreeting.snapshot.sessionFile,
  };
}

async function runBookingWithLocationAddresses(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  const routePrompt = `${config.pickupInput} to ${config.dropoffInput}`;

  console.log(`[run] scenario=booking-with-location-addresses runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=true replyTarget=${run.replyTarget} marker=${run.marker}`);

  const pricing = await runTurn(config, run, "route pricing", routePrompt);
  assertEnglishNoEmoji(pricing.reply.text, "Location-address pricing reply");
  assert(/Price:\s*\d+\.\d{3}\s*KWD/i.test(pricing.reply.text), `Pricing reply should contain a structured price: ${pricing.reply.text}`);

  const bookingStart = await runDeterministicBookingTurn(config, run, "booking follow-up", "Yes");
  assertEnglishNoEmoji(bookingStart.reply.text, "Location-address booking start");
  assert(mentionsSenderStep(bookingStart.reply.text), `Booking should start with sender step: ${bookingStart.reply.text}`);

  const senderStep = await runDeterministicBookingTurn(
    config,
    run,
    "sender step",
    `${run.senderName} ${config.senderPhone}`,
  );
  assert(/recipient full name/i.test(senderStep.reply.text), `Sender step should move to recipient: ${senderStep.reply.text}`);

  const recipientStep = await runDeterministicBookingTurn(
    config,
    run,
    "recipient step",
    `${run.recipientName} ${run.recipientPhone}`,
  );
  assert(
    /pickup location|pickup block|map link/i.test(recipientStep.reply.text),
    `Recipient step should request pickup address evidence: ${recipientStep.reply.text}`,
  );

  const pickupPin = await runLocationPayload(config, run, "pickup location pin", {
    text: "Pickup pin",
    latitude: FARWANIYA_COORDS.latitude,
    longitude: FARWANIYA_COORDS.longitude,
    name: config.pickupExpected,
    address: `${config.pickupExpected}, Kuwait`,
  });
  assertEnglishNoEmoji(pickupPin.reply.text, "Pickup location-pin reply");
  assert(
    /(delivery|drop[- ]?off|destination|map link)/i.test(pickupPin.reply.text),
    `Pickup pin reply should move to delivery address collection: ${pickupPin.reply.text}`,
  );
  assert(
    !/pickup block|pickup street|pickup house|pickup building/i.test(pickupPin.reply.text),
    `Pickup pin reply should not ask again for pickup block/street/house: ${pickupPin.reply.text}`,
  );
  assertNoToolCallsAfter(
    pickupPin.snapshot,
    pickupPin.ack.acceptedAtMs,
    ["get_price", "assign_agent", "create_simple_order"],
    "Pickup location pin should stay in booking collection.",
  );

  const deliveryMapLink = await runTurn(
    config,
    run,
    "delivery map link",
    `Delivery pin https://maps.google.com/?q=${BAYAN_COORDS.latitude},${BAYAN_COORDS.longitude}`,
  );
  assertEnglishNoEmoji(deliveryMapLink.reply.text, "Delivery map-link reply");
  assert(
    /summary|shall i proceed|confirm|sender:/i.test(deliveryMapLink.reply.text),
    `Delivery map link should produce the order summary: ${deliveryMapLink.reply.text}`,
  );
  const preConfirmCreateResults = findToolResultsAfter(
    deliveryMapLink.snapshot,
    deliveryMapLink.ack.acceptedAtMs,
    "create_simple_order",
  );
  assert(
    !preConfirmCreateResults.some((result) => result?.json?.status === "ok"),
    "Location-address flow should not create the order before summary confirmation.",
  );

  const confirmation = await runTurn(config, run, "summary confirmation", "Yes, confirm");
  await assertInterpreterActionLogged(config, run, confirmation.ack.acceptedAtMs, "confirm_summary", "Location-address confirmation turn");
  const createCalls = findToolCallsAfter(confirmation.snapshot, confirmation.ack.acceptedAtMs, "create_simple_order");
  const createResults = findToolResultsAfter(confirmation.snapshot, confirmation.ack.acceptedAtMs, "create_simple_order");
  assert(createCalls.length > 0, "Expected create_simple_order to be called after confirming the location-address summary.");
  assert(createResults.length > 0, "Expected a create_simple_order result after confirming the location-address summary.");
  assert(createResults.at(-1)?.json?.status === "ok", `Location-address order creation failed: ${createResults.at(-1)?.text || "missing result"}`);
  const latestCreateCall = createCalls.at(-1);
  assertWithSnapshot(
    typeof latestCreateCall?.params?.pickup_latitude === "number" &&
      typeof latestCreateCall?.params?.pickup_longitude === "number" &&
      typeof latestCreateCall?.params?.delivery_latitude === "number" &&
      typeof latestCreateCall?.params?.delivery_longitude === "number",
    `Location-address order should pass exact coordinates into create_simple_order: ${JSON.stringify(latestCreateCall?.params || {})}`,
    confirmation.snapshot,
  );
  assert(/Order ID:\s*ORDER-/i.test(confirmation.reply.text), `Location-address success reply should contain the order ID: ${confirmation.reply.text}`);

  return {
    run,
    sessionFile: confirmation.snapshot.sessionFile,
  };
}

async function runArabicBookingHappyPath(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  const senderName = `المرسل ${run.marker}`;
  const recipientName = `المستلم ${run.marker}`;
  let successReplyText = null;

  console.log(`[run] scenario=arabic-booking-happy-path runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=true replyTarget=${run.replyTarget} marker=${run.marker}`);

  const greeting = await runTurn(config, run, "arabic greeting", "السلام عليكم");
  assertArabicNoEmoji(greeting.reply.text, "Arabic happy-path greeting reply");
  await assertInterpreterActionLogged(config, run, greeting.ack.acceptedAtMs, "greeting", "Arabic happy-path greeting turn");

  const pricing = await runTurn(config, run, "arabic route pricing", "بكم التوصيل من حولي حق سلوى");
  assertArabicNoEmoji(pricing.reply.text, "Arabic happy-path pricing reply");
  await assertInterpreterActionLogged(config, run, pricing.ack.acceptedAtMs, "pricing_request", "Arabic happy-path pricing turn");
  assert(
    /حولي/i.test(pricing.reply.text) && /سلوى/i.test(pricing.reply.text),
    `Arabic pricing reply should mention Hawalli and Salwa in Arabic: ${pricing.reply.text}`,
  );
  assert(/1\.250|KWD/i.test(pricing.reply.text), `Arabic pricing reply should contain the structured price: ${pricing.reply.text}`);

  const bookingStart = await runDeterministicBookingTurn(config, run, "arabic booking follow-up", "نعم");
  assertArabicNoEmoji(bookingStart.reply.text, "Arabic booking-start reply");
  await assertInterpreterActionLogged(config, run, bookingStart.ack.acceptedAtMs, "start_booking", "Arabic happy-path booking-start turn");
  assert(
    mentionsSenderStepArabic(bookingStart.reply.text),
    `Arabic booking should start with sender step only: ${bookingStart.reply.text}`,
  );
  assertNoToolCallsAfter(
    bookingStart.snapshot,
    bookingStart.ack.acceptedAtMs,
    ["assign_agent", "create_simple_order"],
    "Arabic booking start should stay inside the controller flow.",
  );

  const senderStep = await runDeterministicBookingTurn(
    config,
    run,
    "arabic sender step",
    `${senderName} ${config.senderPhone}`,
  );
  assertArabicNoEmoji(senderStep.reply.text, "Arabic sender-step reply");
  assertWithSnapshot(
    findToolCallsAfter(senderStep.snapshot, senderStep.ack.acceptedAtMs, "create_simple_order").length === 0,
    `Arabic sender step should not call create_simple_order yet. Reply was: ${senderStep.reply.text}`,
    senderStep.snapshot,
  );
  assertWithSnapshot(
    /المستلم|اسم.*المستلم|رقم.*المستلم/i.test(senderStep.reply.text),
    `Arabic sender step should move to recipient details: ${senderStep.reply.text}`,
    senderStep.snapshot,
  );

  const recipientStep = await runDeterministicBookingTurn(
    config,
    run,
    "arabic recipient step",
    `${recipientName} ${run.recipientPhone}`,
  );
  assertArabicNoEmoji(recipientStep.reply.text, "Arabic recipient-step reply");
  assertWithSnapshot(
    findToolCallsAfter(recipientStep.snapshot, recipientStep.ack.acceptedAtMs, "create_simple_order").length === 0,
    `Arabic recipient step should not call create_simple_order yet. Reply was: ${recipientStep.reply.text}`,
    recipientStep.snapshot,
  );
  assertWithSnapshot(
    /قطعة|الاستلام|المرسل/i.test(recipientStep.reply.text),
    `Arabic recipient step should move to pickup address collection: ${recipientStep.reply.text}`,
    recipientStep.snapshot,
  );

  const pickupStep = await runDeterministicBookingTurn(
    config,
    run,
    "arabic pickup address step",
    "قطعة 1، شارع 1، منزل 1",
  );
  assertArabicNoEmoji(pickupStep.reply.text, "Arabic pickup-step reply");
  assertNoToolCallsAfter(
    pickupStep.snapshot,
    pickupStep.ack.acceptedAtMs,
    ["get_price", "assign_agent", "create_simple_order"],
    "Arabic pickup step should stay in booking collection.",
  );
  assertWithSnapshot(
    /التسليم|التوصيل|المستلم/i.test(pickupStep.reply.text),
    `Arabic pickup step should move to delivery address collection: ${pickupStep.reply.text}`,
    pickupStep.snapshot,
  );

  const deliveryStep = await runTurn(
    config,
    run,
    "arabic delivery address step",
    "قطعة 2، شارع 2، منزل 2",
  );
  assertArabicNoEmoji(deliveryStep.reply.text, "Arabic summary reply");
  assertWithSnapshot(
    deliveryStep.reply.text.includes(senderName),
    `Arabic summary should mention sender name ${senderName}: ${deliveryStep.reply.text}`,
    deliveryStep.snapshot,
  );
  assertWithSnapshot(
    deliveryStep.reply.text.includes(recipientName),
    `Arabic summary should mention recipient name ${recipientName}: ${deliveryStep.reply.text}`,
    deliveryStep.snapshot,
  );
  assertWithSnapshot(
    /تأكيد|نأكد|نكمل|ملخص/i.test(deliveryStep.reply.text),
    `Arabic summary should ask for explicit confirmation: ${deliveryStep.reply.text}`,
    deliveryStep.snapshot,
  );
  const preConfirmCreateResults = findToolResultsAfter(deliveryStep.snapshot, deliveryStep.ack.acceptedAtMs, "create_simple_order");
  const prematureSuccess = preConfirmCreateResults.find((result) => result?.json?.status === "ok");
  assertWithSnapshot(
    !prematureSuccess,
    "Arabic order should not be successfully created before summary confirmation.",
    deliveryStep.snapshot,
  );

  const confirmation = await runTurn(config, run, "arabic summary confirmation", "نعم أكد الطلب");
  assertArabicNoEmoji(confirmation.reply.text, "Arabic confirmation success reply");
  await assertInterpreterActionLogged(config, run, confirmation.ack.acceptedAtMs, "confirm_summary", "Arabic happy-path summary confirmation turn");
  const createCalls = findToolCallsAfter(confirmation.snapshot, confirmation.ack.acceptedAtMs, "create_simple_order");
  const createResults = findToolResultsAfter(confirmation.snapshot, confirmation.ack.acceptedAtMs, "create_simple_order");
  assert(createCalls.length > 0, "Expected Arabic create_simple_order to be called after confirming the summary.");
  assert(createResults.length > 0, "Expected a successful Arabic create_simple_order result after confirming the summary.");
  const latestCreateResult = createResults.at(-1);
  assert(latestCreateResult?.json?.status === "ok", `Arabic order creation tool result was not ok: ${latestCreateResult?.text || "missing result"}`);
  assert(/ORDER-/i.test(confirmation.reply.text), `Arabic success reply should contain the order ID: ${confirmation.reply.text}`);
  assert(containsUrl(confirmation.reply.text), `Arabic success reply should contain the payment link: ${confirmation.reply.text}`);
  successReplyText = confirmation.reply.text;

  const postOrderGreeting = await runTurn(config, run, "arabic post-order unrelated greeting", "هلا");
  assertArabicNoEmoji(postOrderGreeting.reply.text, "Arabic post-order greeting reply");
  await assertInterpreterActionLogged(config, run, postOrderGreeting.ack.acceptedAtMs, "greeting", "Arabic happy-path post-order greeting turn");
  assert(/هلا|شلون|نخدم/i.test(postOrderGreeting.reply.text), `Arabic post-order greeting should return to a normal greeting: ${postOrderGreeting.reply.text}`);
  assert(!/ORDER-/i.test(postOrderGreeting.reply.text), `Arabic post-order greeting should not replay an order ID: ${postOrderGreeting.reply.text}`);
  assert(!containsUrl(postOrderGreeting.reply.text), `Arabic post-order greeting should not replay a payment link: ${postOrderGreeting.reply.text}`);
  assert(
    compactWhitespace(postOrderGreeting.reply.text) !== compactWhitespace(successReplyText),
    "Arabic post-order greeting should not replay the previous order-success message.",
  );

  return {
    run,
    sessionFile: postOrderGreeting.snapshot.sessionFile,
  };
}

async function runBookingSplitFields(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  const routePrompt = `${config.pickupInput} to ${config.dropoffInput}`;
  console.log(`[run] scenario=booking-split-fields runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=true replyTarget=${run.replyTarget} marker=${run.marker}`);

  const pricing = await runTurn(config, run, "route pricing", routePrompt);
  assertEnglishNoEmoji(pricing.reply.text, "Split-flow pricing reply");

  const bookingStart = await runDeterministicBookingTurn(config, run, "booking follow-up", "Yes");
  assertEnglishNoEmoji(bookingStart.reply.text, "Split-flow booking start");
  assert(mentionsSenderStep(bookingStart.reply.text), `Split-flow booking should start with sender step: ${bookingStart.reply.text}`);

  const senderNameOnly = await runDeterministicBookingTurn(config, run, "sender name only", run.senderName);
  assertEnglishNoEmoji(senderNameOnly.reply.text, "Sender-name-only reply");
  assert(
    /sender phone/i.test(senderNameOnly.reply.text) && !/recipient full name/i.test(senderNameOnly.reply.text),
    `Sender-name-only reply should ask only for sender phone when no valid current WhatsApp number is available: ${senderNameOnly.reply.text}`,
  );

  const senderPhoneOnly = await runDeterministicBookingTurn(config, run, "sender phone only", config.senderPhone);
  assertEnglishNoEmoji(senderPhoneOnly.reply.text, "Sender-phone-only reply");
  assert(
    /recipient full name/i.test(senderPhoneOnly.reply.text) && /recipient phone/i.test(senderPhoneOnly.reply.text),
    `Sender-phone-only reply should advance to recipient details: ${senderPhoneOnly.reply.text}`,
  );

  const recipientNameOnly = await runDeterministicBookingTurn(config, run, "recipient name only", run.recipientName);
  assertEnglishNoEmoji(recipientNameOnly.reply.text, "Recipient-name-only reply");
  assert(
    /recipient phone/i.test(recipientNameOnly.reply.text) && !/pickup block/i.test(recipientNameOnly.reply.text),
    `Recipient-name-only reply should ask only for recipient phone: ${recipientNameOnly.reply.text}`,
  );

  const recipientPhoneOnly = await runDeterministicBookingTurn(config, run, "recipient phone only", run.recipientPhone);
  assertEnglishNoEmoji(recipientPhoneOnly.reply.text, "Recipient-phone-only reply");
  assert(/pickup block/i.test(recipientPhoneOnly.reply.text), `Recipient-phone-only reply should move to pickup block: ${recipientPhoneOnly.reply.text}`);

  const pickupBlockOnly = await runDeterministicBookingTurn(config, run, "pickup block only", "1");
  assert(/pickup street/i.test(pickupBlockOnly.reply.text), `Pickup-block-only reply should ask for pickup street: ${pickupBlockOnly.reply.text}`);

  const pickupStreetOnly = await runDeterministicBookingTurn(config, run, "pickup street only", "2");
  assert(/pickup house|pickup building/i.test(pickupStreetOnly.reply.text), `Pickup-street-only reply should ask for pickup house/building: ${pickupStreetOnly.reply.text}`);

  const pickupHouseOnly = await runDeterministicBookingTurn(config, run, "pickup house only", "3");
  assert(/delivery block/i.test(pickupHouseOnly.reply.text), `Pickup-house-only reply should move to delivery block: ${pickupHouseOnly.reply.text}`);

  const deliveryBlockOnly = await runDeterministicBookingTurn(config, run, "delivery block only", "4");
  assert(/delivery street/i.test(deliveryBlockOnly.reply.text), `Delivery-block-only reply should ask for delivery street: ${deliveryBlockOnly.reply.text}`);

  const deliveryStreetOnly = await runDeterministicBookingTurn(config, run, "delivery street only", "5");
  assert(/delivery house|delivery building/i.test(deliveryStreetOnly.reply.text), `Delivery-street-only reply should ask for delivery house/building: ${deliveryStreetOnly.reply.text}`);

  const deliveryHouseOnly = await runTurn(config, run, "delivery house only", "6");
  assert(/summary|shall i proceed|confirm|sender:/i.test(deliveryHouseOnly.reply.text), `Delivery-house-only reply should produce the order summary: ${deliveryHouseOnly.reply.text}`);

  const confirmation = await runTurn(config, run, "summary confirmation", "Yes, confirm");
  await assertInterpreterActionLogged(config, run, confirmation.ack.acceptedAtMs, "confirm_summary", "Split-flow summary confirmation turn");
  const createResults = findToolResultsAfter(confirmation.snapshot, confirmation.ack.acceptedAtMs, "create_simple_order");
  assert(createResults.length > 0, "Split-flow confirmation should create the order.");
  assert(createResults.at(-1)?.json?.status === "ok", `Split-flow order creation failed: ${createResults.at(-1)?.text || "missing result"}`);
  assert(/Order ID:\s*ORDER-/i.test(confirmation.reply.text), `Split-flow success reply should contain the order ID: ${confirmation.reply.text}`);

  return {
    run,
    sessionFile: confirmation.snapshot.sessionFile,
  };
}

async function runBookingSenderPhoneDifferentIntent(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  const routePrompt = `${config.pickupInput} to ${config.dropoffInput}`;
  console.log(`[run] scenario=booking-sender-phone-different-intent runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=true replyTarget=${run.replyTarget} marker=${run.marker}`);

  const pricing = await runTurn(config, run, "route pricing", routePrompt);
  assertEnglishNoEmoji(pricing.reply.text, "Different-intent pricing reply");

  const bookingStart = await runDeterministicBookingTurn(config, run, "booking follow-up", "Yes");
  assertEnglishNoEmoji(bookingStart.reply.text, "Different-intent booking start");
  assert(mentionsSenderStep(bookingStart.reply.text), `Booking should start with sender step: ${bookingStart.reply.text}`);

  const combined = await runDeterministicBookingTurn(
    config,
    run,
    "sender name plus reject whatsapp phone",
    "Aziz almulla and no we should use a diff number",
  );
  assertEnglishNoEmoji(combined.reply.text, "Sender combined-intent reply");
  await assertInterpreterActionLogged(config, run, combined.ack.acceptedAtMs, "booking_step_input", "Combined sender+phone-intent turn");
  const interpreterLogs = await fetchGatewayLogs(config, run, combined.ack.acceptedAtMs, "[turn-interpreter]");
  assert(
    interpreterLogs.some((line) => line.includes("booking=") && line.includes("pd=different")),
    `Turn interpreter should log phone decision different. Logs: ${interpreterLogs.slice(-8).join(" | ")}`,
  );
  assert(
    interpreterLogs.some((line) => line.includes("booking=") && /sn="Aziz almulla"/i.test(line)),
    `Turn interpreter should log clean sender name. Logs: ${interpreterLogs.slice(-8).join(" | ")}`,
  );
  assert(
    !/recipient full name/i.test(combined.reply.text),
    `Should stay on sender step until phone is provided: ${combined.reply.text}`,
  );

  const senderPhoneOnly = await runDeterministicBookingTurn(config, run, "sender phone after different intent", config.senderPhone);
  assertEnglishNoEmoji(senderPhoneOnly.reply.text, "Sender-phone follow-up reply");
  assert(
    /recipient full name/i.test(senderPhoneOnly.reply.text),
    `After sender phone, should move to recipient: ${senderPhoneOnly.reply.text}`,
  );

  return {
    run,
    sessionFile: senderPhoneOnly.snapshot.sessionFile,
  };
}

async function runArabicGreeting(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  console.log(`[run] scenario=arabic-greeting runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  const greeting = await runTurn(config, run, "arabic greeting", "السلام عليكم");
  assertArabicNoEmoji(greeting.reply.text, "Arabic greeting reply");
  assert(/هلا|شلون|نقدر نخدم/i.test(greeting.reply.text), `Arabic greeting reply looked wrong: ${greeting.reply.text}`);
  await assertInterpreterActionLogged(config, run, greeting.ack.acceptedAtMs, "greeting", "Arabic greeting turn");
  assertNoToolCallsAfter(
    greeting.snapshot,
    greeting.ack.acceptedAtMs,
    ["get_price", "assign_agent", "create_simple_order", "track_order"],
    "Greeting should not invoke tools.",
  );
  return {
    run,
    sessionFile: greeting.snapshot.sessionFile,
  };
}

async function runPassengerTransportRejection(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  console.log(`[run] scenario=passenger-transport-rejection runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  logStep("passenger request", "Will u drop me airport");
  const ack = await postTextTurn(config, run, "Will u drop me airport");
  const rejection = await waitForGatewayReplyLog(
    config,
    run,
    ack.acceptedAtMs,
    "deterministic passenger reply sent",
    "passenger request",
  );
  console.log(`  assistant: ${compactWhitespace(rejection.reply.text)}`);
  assertEnglishNoEmoji(rejection.reply.text, "Passenger rejection reply");
  assert(
    /deliver items and packages|do not transport people/i.test(rejection.reply.text),
    `Passenger rejection reply should clearly reject human transport: ${rejection.reply.text}`,
  );
  await assertInterpreterActionLogged(config, run, ack.acceptedAtMs, "passenger_transport_request", "Passenger rejection turn");
  const logLines = await fetchGatewayLogs(config, run, ack.acceptedAtMs, "");
  const forbiddenMarkers = ["tool:get_price", "tool:create_simple_order", "tool:assign_agent", "tool:track_order"];
  assert(
    forbiddenMarkers.every((marker) => !logLines.some((line) => line.includes(marker))),
    `Passenger transport request should be rejected before tools run. Logs: ${logLines.slice(-6).join(" | ")}`,
  );
  return {
    run,
    sessionFile: rejection.snapshot.sessionFile,
  };
}

async function runArabicPassengerTransportRejection(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  console.log(`[run] scenario=arabic-passenger-transport-rejection runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  logStep("arabic passenger request", "ودني المطار");
  const ack = await postTextTurn(config, run, "ودني المطار");
  const rejection = await waitForGatewayReplyLog(
    config,
    run,
    ack.acceptedAtMs,
    "deterministic passenger reply sent",
    "arabic passenger request",
  );
  console.log(`  assistant: ${compactWhitespace(rejection.reply.text)}`);
  assertArabicNoEmoji(rejection.reply.text, "Arabic passenger rejection reply");
  assert(
    /نقل أشخاص|نوفر خدمة نقل أشخاص|نوصل الطلبات|الشحنات فقط/i.test(rejection.reply.text),
    `Arabic passenger rejection should clearly reject human transport: ${rejection.reply.text}`,
  );
  await assertInterpreterActionLogged(config, run, ack.acceptedAtMs, "passenger_transport_request", "Arabic passenger rejection turn");
  return {
    run,
    sessionFile: rejection.snapshot.sessionFile,
  };
}

async function runServiceOverview(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  console.log(`[run] scenario=service-overview runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  const overview = await runTurn(config, run, "service overview", "What services do you offer?");
  assertEnglishNoEmoji(overview.reply.text, "Service overview reply");
  assert(
    /service|sedan|box|refrigerated|helper|pickup|dropoff|pricing/i.test(overview.reply.text),
    `Service overview reply should describe services naturally: ${overview.reply.text}`,
  );
  await assertInterpreterActionLogged(config, run, overview.ack.acceptedAtMs, "service_overview", "Service overview turn");
  assertNoToolCallsAfter(
    overview.snapshot,
    overview.ack.acceptedAtMs,
    ["get_price", "track_order", "create_simple_order", "assign_agent"],
    "Broad service overview should not invoke route pricing or booking tools.",
  );
  return {
    run,
    sessionFile: overview.snapshot.sessionFile,
  };
}

async function runTrackingGuard(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  console.log(`[run] scenario=tracking-guard runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  logStep("tracking without order id", "Track my order");
  const ack = await postTextTurn(config, run, "Track my order");
  const trackingReply = await waitForGatewayReplyLog(
    config,
    run,
    ack.acceptedAtMs,
    "deterministic tracking guard reply sent",
    "tracking without order id",
  );
  console.log(`  assistant: ${compactWhitespace(trackingReply.reply.text)}`);
  assertEnglishNoEmoji(trackingReply.reply.text, "Tracking guard reply");
  assert(
    /ORDER-/i.test(trackingReply.reply.text),
    `Tracking guard reply should ask for an ORDER- number: ${trackingReply.reply.text}`,
  );
  await assertInterpreterActionLogged(config, run, ack.acceptedAtMs, "tracking_missing_id", "Tracking guard turn");
  const logLines = await fetchGatewayLogs(config, run, ack.acceptedAtMs, "");
  assert(
    !logLines.some((line) => line.includes("tool:track_order")),
    `Tracking guard should not invoke track_order without an order id. Logs: ${logLines.slice(-6).join(" | ")}`,
  );
  return {
    run,
    sessionFile: trackingReply.snapshot.sessionFile,
  };
}

async function runArabicTrackingGuard(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  console.log(`[run] scenario=arabic-tracking-guard runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  logStep("arabic tracking without order id", "وين طلبي");
  const ack = await postTextTurn(config, run, "وين طلبي");
  const trackingReply = await waitForGatewayReplyLog(
    config,
    run,
    ack.acceptedAtMs,
    "deterministic tracking guard reply sent",
    "arabic tracking without order id",
  );
  console.log(`  assistant: ${compactWhitespace(trackingReply.reply.text)}`);
  assertArabicNoEmoji(trackingReply.reply.text, "Arabic tracking guard reply");
  assert(
    /ORDER-/i.test(trackingReply.reply.text),
    `Arabic tracking guard should ask for an ORDER- number: ${trackingReply.reply.text}`,
  );
  await assertInterpreterActionLogged(config, run, ack.acceptedAtMs, "tracking_missing_id", "Arabic tracking guard turn");
  return {
    run,
    sessionFile: trackingReply.snapshot.sessionFile,
  };
}

async function runBookingPhraseVariation(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  console.log(`[run] scenario=booking-phrase-variation runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);
  const pricing = await runTurn(config, run, "route pricing", `${config.pickupInput} to ${config.dropoffInput}`);
  assertEnglishNoEmoji(pricing.reply.text, "Variation pricing reply");
  await assertInterpreterActionLogged(config, run, pricing.ack.acceptedAtMs, "pricing_request", "Variation pricing turn");
  const bookingStart = await runTurn(config, run, "booking phrase variation", "Book please");
  assertEnglishNoEmoji(bookingStart.reply.text, "Variation booking-start reply");
  assert(
    mentionsSenderStep(bookingStart.reply.text),
    `Book please should start with the sender step: ${bookingStart.reply.text}`,
  );
  await assertInterpreterActionLogged(config, run, bookingStart.ack.acceptedAtMs, "start_booking", "Booking phrase variation turn");
  assertNoToolCallsAfter(
    bookingStart.snapshot,
    bookingStart.ack.acceptedAtMs,
    ["assign_agent", "create_simple_order"],
    "Book please should start booking without escalating or creating an order.",
  );
  return {
    run,
    sessionFile: bookingStart.snapshot.sessionFile,
  };
}

async function runGreetingDuringBooking(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  console.log(`[run] scenario=greeting-during-booking runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=true replyTarget=${run.replyTarget} marker=${run.marker}`);

  const pricing = await runTurn(config, run, "route pricing", `${config.pickupInput} to ${config.dropoffInput}`);
  assertEnglishNoEmoji(pricing.reply.text, "Greeting-during-booking pricing reply");

  const bookingStart = await runDeterministicBookingTurn(config, run, "booking follow-up", "Yes");
  assertEnglishNoEmoji(bookingStart.reply.text, "Greeting-during-booking start reply");
  assert(mentionsSenderStep(bookingStart.reply.text), `Booking should start with sender step: ${bookingStart.reply.text}`);

  const greeting = await runDeterministicBookingTurn(config, run, "greeting during booking", "Hi");
  assertEnglishNoEmoji(greeting.reply.text, "Greeting-during-booking continuation reply");
  assert(
    mentionsSenderStep(greeting.reply.text) && !/recipient full name/i.test(greeting.reply.text),
    `Greeting during booking should preserve the sender step: ${greeting.reply.text}`,
  );

  const senderStep = await runDeterministicBookingTurn(
    config,
    run,
    "sender details after greeting",
    `${run.senderName} ${config.senderPhone}`,
  );
  assert(
    /recipient full name/i.test(senderStep.reply.text) && /recipient phone/i.test(senderStep.reply.text),
    `Booking should continue normally after a greeting: ${senderStep.reply.text}`,
  );

  return {
    run,
    sessionFile: senderStep.snapshot.sessionFile,
  };
}

async function runStaleQuoteBookingBlocked(config) {
  const run = await createRunContext(config);
  await resetLiveConversationState(config, run);
  console.log(`[run] scenario=stale-quote-booking-blocked runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=true replyTarget=${run.replyTarget} marker=${run.marker}`);

  const pricing = await runTurn(config, run, "route pricing", `${config.pickupInput} to ${config.dropoffInput}`);
  assertEnglishNoEmoji(pricing.reply.text, "Stale-quote pricing reply");
  await assertInterpreterActionLogged(config, run, pricing.ack.acceptedAtMs, "pricing_request", "Stale-quote pricing turn");

  const aged = await ageLiveQuoteState(config, run, 31 * 60_000);
  assert(
    aged.controllerUpdated > 0 || aged.guardUpdated > 0,
    `Expected stale-quote setup to update controller or guard state, got ${JSON.stringify(aged)}`,
  );

  const followup = await runTurn(config, run, "stale quote booking follow-up", "Yes");
  assertEnglishNoEmoji(followup.reply.text, "Stale-quote follow-up reply");
  assert(
    !mentionsSenderStep(followup.reply.text),
    `A stale quote should not jump into booking collection: ${followup.reply.text}`,
  );
  const interpreterLogs = await fetchGatewayLogs(config, run, followup.ack.acceptedAtMs, "[turn-interpreter]");
  assert(
    !interpreterLogs.some((line) => line.includes("action=start_booking")),
    `A stale quote should not be interpreted as start_booking. Logs: ${interpreterLogs.slice(-8).join(" | ")}`,
  );
  const expiredLogs = await fetchGatewayLogs(config, run, followup.ack.acceptedAtMs, "expired stale quoted state");
  assert(
    expiredLogs.length > 0,
    `Expected stale quoted state to be cleared before handling follow-up. Logs: ${expiredLogs.slice(-8).join(" | ")}`,
  );
  const bookingLogs = await fetchGatewayLogs(config, run, followup.ack.acceptedAtMs, "Deterministic booking-details reply sent");
  assert(
    bookingLogs.length === 0,
    `A stale quote should not emit booking-details reply. Logs: ${bookingLogs.slice(-8).join(" | ")}`,
  );

  return {
    run,
    sessionFile: followup.snapshot.sessionFile,
  };
}

async function runWebhookObservability(config) {
  const run = await createRunContext(config);
  console.log(`[run] scenario=webhook-observability runId=${run.runId} conversationId=${run.conversationId}`);
  console.log(`[run] destructive=false replyTarget=${run.replyTarget} marker=${run.marker}`);

  if (config.webhookToken) {
    const badTokenResponse = await postRawWebhookRequest(config, {
      requestId: `webhook-auth-${run.runId}`,
      payload: {
        conversation_id: `auth-check-${run.runId}`,
        phone: run.replyTarget,
        from: run.replyTarget,
        sender_id: run.replyTarget,
        message_id: `auth-${run.runId}`,
        message: "hello",
      },
      webhookToken: "bad-token",
    });
    assert(
      badTokenResponse.statusCode === 401,
      `Bad webhook token should return 401, got ${badTokenResponse.statusCode}: ${badTokenResponse.body}`,
    );
    const authLines = await waitForIngressLog(config, badTokenResponse.requestId, "webhook_auth_failed", "bad-token request");
    assert(
      authLines.some((line) => line.includes("webhook_auth_failed")),
      `Bad-token request should emit webhook_auth_failed: ${authLines.slice(-8).join(" | ")}`,
    );
  }

  const invalidJsonResponse = await postRawWebhookRequest(config, {
    requestId: `webhook-parse-${run.runId}`,
    rawBody: "{invalid",
    headers: { "Content-Type": "application/json" },
  });
  assert(
    invalidJsonResponse.statusCode === 400,
    `Invalid JSON should return 400, got ${invalidJsonResponse.statusCode}: ${invalidJsonResponse.body}`,
  );
  const parseLines = await waitForIngressLog(config, invalidJsonResponse.requestId, "webhook_parse_failed", "invalid-json request");
  assert(
    parseLines.some((line) => line.includes("webhook_parse_failed")),
    `Invalid JSON request should emit webhook_parse_failed: ${parseLines.slice(-8).join(" | ")}`,
  );

  const missingConversationResponse = await postRawWebhookRequest(config, {
    requestId: `webhook-missing-conversation-${run.runId}`,
    payload: {
      phone: run.replyTarget,
      from: run.replyTarget,
      sender_id: run.replyTarget,
      message_id: `missing-conversation-${run.runId}`,
      message: "hello",
    },
  });
  assert(
    missingConversationResponse.statusCode === 400,
    `Missing conversation_id should return 400, got ${missingConversationResponse.statusCode}: ${missingConversationResponse.body}`,
  );
  const missingConversationLines = await waitForIngressLog(
    config,
    missingConversationResponse.requestId,
    "webhook_missing_conversation_id",
    "missing-conversation request",
  );
  assert(
    missingConversationLines.some((line) => line.includes("webhook_missing_conversation_id")),
    `Missing conversation_id request should emit webhook_missing_conversation_id: ${missingConversationLines.slice(-8).join(" | ")}`,
  );

  const acceptedTurn = await runTurn(config, run, "webhook accepted path", "What do you do?");
  const acceptedLogs = await fetchGatewayLogs(config, run, acceptedTurn.ack.acceptedAtMs, "webhook_accepted");
  assert(
    acceptedLogs.some((line) => line.includes("webhook_accepted")),
    `Accepted webhook should emit webhook_accepted: ${acceptedLogs.slice(-8).join(" | ")}`,
  );
  const enqueuedLogs = await fetchGatewayLogs(config, run, acceptedTurn.ack.acceptedAtMs, "webhook_enqueued");
  assert(
    enqueuedLogs.some((line) => line.includes("webhook_enqueued")),
    `Accepted webhook should emit webhook_enqueued: ${enqueuedLogs.slice(-8).join(" | ")}`,
  );
  const outboundLogs = await fetchGatewayLogs(config, run, acceptedTurn.ack.acceptedAtMs, "outbound_result");
  assert(
    outboundLogs.some((line) => line.includes("status=sent")),
    `Accepted webhook should emit outbound_result status=sent: ${outboundLogs.slice(-8).join(" | ")}`,
  );

  return {
    run,
    sessionFile: acceptedTurn.snapshot.sessionFile,
  };
}

async function runAllScenarios(config) {
  const results = [];
  results.push(await runWebhookObservability(config));
  results.push(await runArabicGreeting(config));
  results.push(await runArabicPassengerTransportRejection(config));
  results.push(await runAudioPricing(config));
  results.push(await runPassengerTransportRejection(config));
  results.push(await runServiceOverview(config));
  results.push(await runMapLinkPricing(config));
  results.push(await runLocationPinIntake(config));
  results.push(await runStickyLanguageLocationPin(config));
  results.push(await runArabicLocationPinIntake(config));
  results.push(await runImagePricing(config));
  results.push(await runImageTrackingGuard(config));
  results.push(await runQuoteOptionFollowup(config));
  results.push(await runQuoteRouteChange(config));
  results.push(await runTrackingGuard(config));
  results.push(await runArabicTrackingGuard(config));
  results.push(await runArabicQuoteBookingFollowup(config));
  results.push(await runBookingPhraseVariation(config));
  results.push(await runGreetingDuringBooking(config));
  results.push(await runStaleQuoteBookingBlocked(config));
  results.push(await runBookingHappyPath(config));
  results.push(await runBookingWithLocationAddresses(config));
  results.push(await runArabicBookingHappyPath(config));
  results.push(await runBookingSplitFields(config));
  results.push(await runBookingSenderPhoneDifferentIntent(config));
  return {
    run: results.at(-1)?.run || { runId: "n/a", conversationId: "n/a" },
    sessionFile: results.at(-1)?.sessionFile || "unknown",
  };
}

const scenarios = {
  all: runAllScenarios,
  "audio-pricing": runAudioPricing,
  "arabic-greeting": runArabicGreeting,
  "arabic-location-pin-intake": runArabicLocationPinIntake,
  "arabic-booking-happy-path": runArabicBookingHappyPath,
  "arabic-passenger-transport-rejection": runArabicPassengerTransportRejection,
  "arabic-quote-booking-followup": runArabicQuoteBookingFollowup,
  "arabic-tracking-guard": runArabicTrackingGuard,
  "arabic-unorthodox-flow": runArabicUnorthodoxFlow,
  "greeting-during-booking": runGreetingDuringBooking,
  "booking-happy-path": runBookingHappyPath,
  "booking-with-location-addresses": runBookingWithLocationAddresses,
  "booking-phrase-variation": runBookingPhraseVariation,
  "stale-quote-booking-blocked": runStaleQuoteBookingBlocked,
  "booking-split-fields": runBookingSplitFields,
  "booking-sender-phone-different-intent": runBookingSenderPhoneDifferentIntent,
  "image-pricing": runImagePricing,
  "image-tracking-guard": runImageTrackingGuard,
  "location-pin-intake": runLocationPinIntake,
  "location-pin-language-sticky-regression": runStickyLanguageLocationPin,
  "map-link-pricing": runMapLinkPricing,
  "passenger-transport-rejection": runPassengerTransportRejection,
  "quote-option-followup": runQuoteOptionFollowup,
  "quote-route-change": runQuoteRouteChange,
  "service-overview": runServiceOverview,
  "tracking-guard": runTrackingGuard,
  "webhook-observability": runWebhookObservability,
};

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.list) {
    console.log(Object.keys(scenarios).join("\n"));
    return;
  }

  const scenario = scenarios[args.scenario];
  if (!scenario) {
    throw new Error(`Unknown scenario "${args.scenario}". Use --list to see available scenarios.`);
  }

  const config = getLiveSmokeConfig();
  await ensureLiveGatewayReady(config);

  try {
    const result = await scenario(config);
    console.log("\n[result] PASS");
    console.log(`  scenario: ${args.scenario}`);
    console.log(`  runId: ${result.run.runId}`);
    console.log(`  conversationId: ${result.run.conversationId}`);
    console.log(`  sessionFile: ${result.sessionFile || "unknown"}`);
  } catch (error) {
    console.error("\n[result] FAIL");
    console.error(`  scenario: ${args.scenario}`);
    console.error(`  error: ${error instanceof Error ? error.message : String(error)}`);
    if (error?.snapshot) {
      printTranscriptTail(error.snapshot);
    }
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(`Fatal: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
