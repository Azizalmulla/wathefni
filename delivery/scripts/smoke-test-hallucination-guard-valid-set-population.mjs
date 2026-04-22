#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test for the hallucination-guard valid-set population fix
// (2026-04-22, conv 19400).
//
// Context
// -------
// The octopus-channel dispatcher holds two snapshots of the active
// quoted route during a turn:
//
//   1. Turn-start (pre-drain) `activeQuotedRoute` — read at dispatcher
//      entry from the persisted session. On an INITIAL-route turn (no
//      prior quote on session), this is `null` for the entire handler.
//
//   2. Post-drain `sessionGuard.lastQuotedRoute` — reflects the route
//      just materialised by this turn's `get_price` call.
//
// Before the fix, the hallucination guard's `activeQuotedPrices` input
// was built only from (1). On first-quote turns the array was empty and
// the guard fell back to the scalar default option (standard sedan,
// 1.250 KWD). A truthful reply naming "Express sedan 1.750 KWD" then
// registered as `price_mismatch mentioned=1.75 valid=1.25` and was
// replaced with the neutral price-repair template — clobbering a
// correct catalog-backed answer.
//
// The fix introduces two pure helpers in
// `plugins/octopus-channel/lib/quoted-options.ts`:
//
//   * `selectGuardQuotedRoute` — prefers the post-drain session
//     snapshot when THIS turn actually ran `get_price` (gate:
//     `lastToolName === "get_price"` AND `lastToolTs >= turnStartMs`).
//     Falls back to the turn-start snapshot otherwise.
//
//   * `collectActiveQuotedPrices` — canonical union builder over
//     `pricesByType` + `optionCatalog[*].quoted_price`.
//
// Coverage
// --------
// 1. Initial-route turn: `activeQuotedRoute = null`, `get_price`
//    fired this turn → select the session snapshot, valid set is the
//    full union.
// 2. Follow-up turn: no new `get_price` this turn, `activeQuotedRoute`
//    is the turn-start snapshot → fall back, valid set unchanged.
// 3. Stale `sessionGuard.lastQuotedRoute` (lastToolTs BEFORE
//    turnStartMs) must NOT be trusted — fall back to turn-start.
// 4. `lastToolName !== "get_price"` → fall back to turn-start.
// 5. End-to-end: feed the guard the array built from the fix — the
//    "Express sedan 1.750 KWD" reply passes on a first quote that
//    contains 1.25 (standard sedan) and 1.75 (express sedan) in the
//    catalog. Pre-fix simulation (empty array + scalar 1.25 fallback)
//    is blocked as `price_mismatch`.
// 6. Collector ignores invalid entries (negative, zero, NaN, non-number).
// ---------------------------------------------------------------------------

import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`);
    process.exit(1);
  }
}

async function loadTsModule(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(
    path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
  );
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return await jiti(path.join(root, relativePath));
}

const {
  selectGuardQuotedRoute,
  collectActiveQuotedPrices,
} = await loadTsModule("plugins/octopus-channel/lib/quoted-options.ts");
const {
  runHallucinationGuard,
} = await loadTsModule("plugins/shared/reply-hallucination-guard.ts");
const { createEmptyBookingDraft } = await loadTsModule("plugins/shared/conversation-policy.ts");

// ---------------------------------------------------------------------------
// Route fixtures. Shape mirrors a real `StoredQuotedRoute` produced by
// `get_price` for surra→salwa (the live incident route).
// ---------------------------------------------------------------------------

function buildSurraSalwaRoute() {
  return {
    routeKey: "surra|salwa",
    pickupAreaNameEn: "Surra",
    pickupAreaNameAr: "السرة",
    dropoffAreaNameEn: "Salwa",
    dropoffAreaNameAr: "سلوى",
    pricesByType: {
      sedan_normal: 1.25,
      sedan_fast: 1.75,
      van_normal: 1.75,
      van_fast: 2.25,
      cooled_van_normal: 1.75,
      cooled_van_fast: 2.25,
    },
    optionCatalog: [
      { delivery_type: "sedan_normal", label_en: "Standard sedan", label_ar: "سيدان عادي", quoted_price: 1.25, formatted_price: "1.250 KWD", visibility: "public", direct_chat_booking_status: "bookable", direct_chat_booking_note: null },
      { delivery_type: "sedan_fast", label_en: "Express sedan", label_ar: "سيدان سريع", quoted_price: 1.75, formatted_price: "1.750 KWD", visibility: "public", direct_chat_booking_status: "bookable", direct_chat_booking_note: null },
      { delivery_type: "van_normal", label_en: "Standard box van", label_ar: "فان عادي", quoted_price: 1.75, formatted_price: "1.750 KWD", visibility: "public", direct_chat_booking_status: "bookable", direct_chat_booking_note: null },
      { delivery_type: "van_fast", label_en: "Express box van", label_ar: "فان سريع", quoted_price: 2.25, formatted_price: "2.250 KWD", visibility: "public", direct_chat_booking_status: "bookable", direct_chat_booking_note: null },
      { delivery_type: "cooled_van_normal", label_en: "Standard refrigerated van", label_ar: "فان مبرد عادي", quoted_price: 1.75, formatted_price: "1.750 KWD", visibility: "public", direct_chat_booking_status: "bookable", direct_chat_booking_note: null },
      { delivery_type: "cooled_van_fast", label_en: "Express refrigerated van", label_ar: "فان مبرد سريع", quoted_price: 2.25, formatted_price: "2.250 KWD", visibility: "public", direct_chat_booking_status: "bookable", direct_chat_booking_note: null },
      { delivery_type: "helper_standard", label_en: "Helper service", label_ar: "خدمة مساعد", quoted_price: 3.25, formatted_price: "3.250 KWD", visibility: "public", direct_chat_booking_status: "manual_confirm", direct_chat_booking_note: null },
    ],
  };
}

// ---------------------------------------------------------------------------
// Test 1: initial-route turn — prefer post-drain session snapshot
// ---------------------------------------------------------------------------

{
  const route = buildSurraSalwaRoute();
  const turnStartMs = 1_000_000;
  const selected = selectGuardQuotedRoute({
    turnStartSnapshot: null,
    sessionGuard: {
      lastToolName: "get_price",
      lastToolTs: turnStartMs + 500,
      lastQuotedRoute: route,
    },
    turnStartMs,
  });
  assert(selected === route, "Test 1: initial-route turn should select post-drain sessionGuard.lastQuotedRoute");
  const prices = collectActiveQuotedPrices(selected);
  assert(prices.includes(1.25), "Test 1: prices include standard sedan 1.25");
  assert(prices.includes(1.75), "Test 1: prices include express sedan 1.75");
  assert(prices.includes(2.25), "Test 1: prices include express van 2.25");
  assert(prices.includes(3.25), "Test 1: prices include helper_standard 3.25 from optionCatalog");
  console.log("PASS Test 1 — initial-route turn promotes post-drain snapshot into guard valid-set");
}

// ---------------------------------------------------------------------------
// Test 2: follow-up turn — no get_price this turn, fall back to
// turn-start snapshot
// ---------------------------------------------------------------------------

{
  const priorRoute = buildSurraSalwaRoute();
  const turnStartMs = 2_000_000;
  const selected = selectGuardQuotedRoute({
    turnStartSnapshot: priorRoute,
    sessionGuard: {
      lastToolName: "create_simple_order",
      lastToolTs: turnStartMs + 100,
      lastQuotedRoute: priorRoute,
    },
    turnStartMs,
  });
  assert(selected === priorRoute, "Test 2: follow-up turn falls back to turn-start snapshot when lastToolName != get_price");
  console.log("PASS Test 2 — follow-up turn falls back to turn-start snapshot");
}

// ---------------------------------------------------------------------------
// Test 3: stale sessionGuard (lastToolTs BEFORE turnStartMs) is NOT
// trusted — this protects against a persisted snapshot from a prior
// session/turn being promoted here.
// ---------------------------------------------------------------------------

{
  const priorRoute = buildSurraSalwaRoute();
  const turnStartMs = 3_000_000;
  const selected = selectGuardQuotedRoute({
    turnStartSnapshot: priorRoute,
    sessionGuard: {
      lastToolName: "get_price",
      lastToolTs: turnStartMs - 10_000, // stale — fired in a prior turn
      lastQuotedRoute: priorRoute,
    },
    turnStartMs,
  });
  assert(selected === priorRoute, "Test 3: stale session snapshot falls back to turn-start");
  // And same gate when turn-start is null: no route available at all.
  const selectedNullTurnStart = selectGuardQuotedRoute({
    turnStartSnapshot: null,
    sessionGuard: {
      lastToolName: "get_price",
      lastToolTs: turnStartMs - 10_000,
      lastQuotedRoute: priorRoute,
    },
    turnStartMs,
  });
  assert(selectedNullTurnStart === null, "Test 3: stale session snapshot + null turn-start returns null");
  console.log("PASS Test 3 — stale sessionGuard (lastToolTs < turnStartMs) is rejected");
}

// ---------------------------------------------------------------------------
// Test 4: sessionGuard present but null/missing lastQuotedRoute OR
// null sessionGuard → turn-start fallback
// ---------------------------------------------------------------------------

{
  const priorRoute = buildSurraSalwaRoute();
  const turnStartMs = 4_000_000;

  const nullGuard = selectGuardQuotedRoute({
    turnStartSnapshot: priorRoute,
    sessionGuard: null,
    turnStartMs,
  });
  assert(nullGuard === priorRoute, "Test 4a: null sessionGuard falls back to turn-start");

  const missingRouteOnGuard = selectGuardQuotedRoute({
    turnStartSnapshot: priorRoute,
    sessionGuard: {
      lastToolName: "get_price",
      lastToolTs: turnStartMs + 500,
      lastQuotedRoute: null,
    },
    turnStartMs,
  });
  assert(
    missingRouteOnGuard === priorRoute,
    "Test 4b: sessionGuard with null lastQuotedRoute falls back to turn-start",
  );

  const undefinedGuard = selectGuardQuotedRoute({
    turnStartSnapshot: null,
    sessionGuard: undefined,
    turnStartMs,
  });
  assert(undefinedGuard === null, "Test 4c: undefined sessionGuard + null turn-start returns null");

  console.log("PASS Test 4 — null/missing session snapshot falls back to turn-start");
}

// ---------------------------------------------------------------------------
// Test 5: end-to-end guard behaviour
// ---------------------------------------------------------------------------
// Build the guard inputs the same way index.ts does — via the helpers —
// and verify the truthful reply passes post-fix, while the pre-fix
// simulation (empty array) still produces a price_mismatch. This pins
// down the exact shape of the fix against the live-incident symptom.

{
  const route = buildSurraSalwaRoute();
  const turnStartMs = 5_000_000;

  const fixedGuardRoute = selectGuardQuotedRoute({
    turnStartSnapshot: null,
    sessionGuard: {
      lastToolName: "get_price",
      lastToolTs: turnStartMs + 100,
      lastQuotedRoute: route,
    },
    turnStartMs,
  });
  const fixedActivePrices = collectActiveQuotedPrices(fixedGuardRoute);

  // `entry.quotedPrice` is the default/selected scalar, as the dispatcher
  // materialises it via `applySelectedQuotedOptionToController` →
  // `getQuotedRouteDefaultOption` (usually the standard sedan). The fix
  // does not change this — it only improves the UNION passed alongside.
  const quotedEntry = {
    bookingDraft: createEmptyBookingDraft(),
    quotedPrice: 1.25,
    stage: "quoted",
    submittedOrderUid: null,
  };

  const expressReply =
    "Delivery from Surra to Salwa\nExpress sedan — 1.750 KWD";
  const fixedResult = runHallucinationGuard({
    replyText: expressReply,
    entry: quotedEntry,
    rejectionsThisTurn: [],
    missingFields: [],
    activeQuotedPrices: fixedActivePrices,
    language: "en",
  });
  assert(
    fixedResult.blocked === false,
    `Test 5a (post-fix): express-sedan truthful reply should NOT be blocked, reason=${fixedResult.reason}`,
  );
  assert(
    fixedResult.replyText === expressReply,
    "Test 5a (post-fix): reply text must pass through unchanged",
  );

  // Pre-fix simulation: initial-route turn had null turn-start snapshot
  // and the helper didn't exist, so activeQuotedPrices was []. Reproduce
  // that and confirm the guard WOULD have blocked the same reply.
  const preFixResult = runHallucinationGuard({
    replyText: expressReply,
    entry: quotedEntry,
    rejectionsThisTurn: [],
    missingFields: [],
    activeQuotedPrices: [], // pre-fix population on an initial-route turn
    language: "en",
  });
  assert(
    preFixResult.blocked === true,
    "Test 5b (pre-fix simulation): empty activeQuotedPrices must produce price_mismatch on a non-default option",
  );
  assert(
    Array.isArray(preFixResult.claims) && preFixResult.claims.includes("price_mismatch"),
    `Test 5b (pre-fix simulation): expected price_mismatch claim, got=${JSON.stringify(preFixResult.claims)}`,
  );
  assert(
    typeof preFixResult.reason === "string" && /valid=1\.25/.test(preFixResult.reason),
    `Test 5b (pre-fix simulation): expected valid=1.25 in reason (scalar-fallback), got=${preFixResult.reason}`,
  );

  console.log("PASS Test 5 — guard accepts Express sedan 1.750 post-fix; pre-fix simulation reproduces price_mismatch");
}

// ---------------------------------------------------------------------------
// Test 6: collectActiveQuotedPrices robustness
// ---------------------------------------------------------------------------

{
  const emptyFromNull = collectActiveQuotedPrices(null);
  assert(Array.isArray(emptyFromNull) && emptyFromNull.length === 0, "Test 6a: null route → empty array");

  const emptyFromUndefined = collectActiveQuotedPrices(undefined);
  assert(Array.isArray(emptyFromUndefined) && emptyFromUndefined.length === 0, "Test 6b: undefined route → empty array");

  const mixed = collectActiveQuotedPrices({
    routeKey: "x",
    pickupAreaNameEn: "", pickupAreaNameAr: "",
    dropoffAreaNameEn: "", dropoffAreaNameAr: "",
    pricesByType: {
      good: 1.25,
      negative: -1,
      zero: 0,
      nan: Number.NaN,
      infinity: Number.POSITIVE_INFINITY,
      notNumber: "1.75",
    },
    optionCatalog: [
      { delivery_type: "a", label_en: "", label_ar: "", quoted_price: 1.75, formatted_price: null, visibility: null, direct_chat_booking_status: null, direct_chat_booking_note: null },
      { delivery_type: "b", label_en: "", label_ar: "", quoted_price: null, formatted_price: null, visibility: null, direct_chat_booking_status: null, direct_chat_booking_note: null },
      { delivery_type: "c", label_en: "", label_ar: "", quoted_price: -5, formatted_price: null, visibility: null, direct_chat_booking_status: null, direct_chat_booking_note: null },
      { delivery_type: "d", label_en: "", label_ar: "", quoted_price: 3.25, formatted_price: null, visibility: null, direct_chat_booking_status: null, direct_chat_booking_note: null },
    ],
  });
  assert(
    JSON.stringify(mixed.slice().sort()) === JSON.stringify([1.25, 1.75, 3.25].sort()),
    `Test 6c: expected [1.25, 1.75, 3.25], got=${JSON.stringify(mixed)}`,
  );

  console.log("PASS Test 6 — collectActiveQuotedPrices skips invalid entries");
}

console.log("\nAll hallucination-guard valid-set population smoke tests passed.");
