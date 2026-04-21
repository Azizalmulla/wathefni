#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: clarification turn must not be promoted to stage=quoted
// (2026-04-21 category fix for
// `stale_guard_state_clobbers_clarification_turn`).
//
// Failure class
// -------------
// The quoted-state promotion block in `plugins/octopus-channel/index.ts`
// inherits `stage=quoted` + `quote*AreaNameEn` from
// `sessionGuard.lastQuotedRoute` whenever:
//   - `sessionGuard.lastToolName === "get_price"`
//   - `sessionGuard.lastQuotedRoute` is truthy
//   - `sessionGuard.lastToolTs !== controllerEntry.quoteTs`
// This is correct on a turn where `get_price` actually produced a fresh
// priced route, BUT the gate is sign-blind. `riders-guard-state.json` is
// persisted to disk, survives service restart, and also survives the
// conversation-controller scrub. So a stale `lastQuotedRoute` from a prior
// session (e.g. yesterday's `Sharq → Salmiya` quote) can satisfy the test
// on a brand-new turn whose `get_price` returned AREA_AMBIGUOUS — falsely
// promoting the controller to `stage=quoted` with the stale route and
// CLEARING `pendingPickupAreaNameEn` / `pendingDropoffAreaNameEn`
// ("just promoted to quote*"). The next turn then misroutes: the fast-path
// extractor sees `stage=quoted` with no `requested_slot`, pre-applies a
// `sender_name` write, and the flow advances into booking collection —
// completely bypassing the clarification.
//
// Invariant
// ---------
// A controller entry may be promoted to `stage=quoted` / populated with
// `quote*AreaNameEn` ONLY when the current turn actually produced a fresh
// priced route. A turn whose drain contained a `set_requested_slot` for a
// route-side slot (`pickup_area` / `dropoff_area`) is mid-clarification —
// the promotion block must be skipped, regardless of what
// `sessionGuard.lastQuotedRoute` holds.
//
// Production trace (conversation 19055, 2026-04-21 10:47-10:48):
//   10:47:25 inbound "delivery salmiya to kuwait city pls"
//            state at start: stage=idle, quoted_pickup=null
//   10:47:33 get_price called
//   10:47:39 [controller] "quote not yet presented to customer
//            (clarification pending)" ← bad promotion firing
//   10:47:39 reply_author=llm stage=quoted      ← controller now lies
//   10:48:04 inbound "hmmmm dasman"
//            state at start: stage=quoted, quoted_pickup=Sharq,
//            quoted_dropoff=Salmiya ← stale route from yesterday
//            fast-path pre-applied sender_name="hmmmm dasman"
//   10:48:15 outbound "Got the name (hmmmm dasman). Could you share the
//            sender's phone number?" ← bypassed clarification entirely
//
// The fix is a single veto: `turnDrainedRouteSideClarification` is set in
// the drain when a route-side `set_requested_slot` op is applied, and the
// promotion block treats it as a hard "skip" signal. The fix is
// class-level — it makes the whole bug class impossible, independent of
// which specific persisted state was stale and which specific route was
// being clarified.
// ---------------------------------------------------------------------------

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const SOURCE_PATH = path.resolve(
  path.dirname(new URL(import.meta.url).pathname),
  "..",
  "plugins/octopus-channel/index.ts",
);
const source = fs.readFileSync(SOURCE_PATH, "utf8");

// ---------------------------------------------------------------------------
// P1: the veto flag is declared at an outer scope visible to BOTH the drain
// loop AND the quoted-state promotion block. If a future refactor moves the
// declaration into a narrower scope, the promotion block's reference will
// become a dangling identifier and the TypeScript build will fail — but we
// also want a runtime assertion here so a `let` → `const` slip elsewhere
// doesn't hide the regression.
// ---------------------------------------------------------------------------
assert.ok(
  /let\s+turnDrainedRouteSideClarification\s*=\s*false;/.test(source),
  "P1: `turnDrainedRouteSideClarification` must be declared with `let` at drain-outer scope",
);

// ---------------------------------------------------------------------------
// P2: the flag is LIFTED (set to true) only inside the drain loop, and only
// for route-side slots — never for sender_name / sender_phone / recipient_*
// / address_* slot asks, because those asks cannot be confused with a
// priced-route promotion.
// ---------------------------------------------------------------------------
assert.ok(
  /op\.slot\s*===\s*"pickup_area"\s*\|\|\s*\n?\s*op\.slot\s*===\s*"dropoff_area"[\s\S]{0,120}turnDrainedRouteSideClarification\s*=\s*true/.test(
    source,
  ),
  "P2: `turnDrainedRouteSideClarification` must be lifted only for pickup_area|dropoff_area slot asks",
);

// ---------------------------------------------------------------------------
// P3: the quoted-state promotion block references the veto flag in its
// condition. This is the core invariant — without it, a stale
// `lastQuotedRoute` can promote a clarification turn to `stage=quoted`.
// ---------------------------------------------------------------------------
{
  // Narrow the search to the promotion block region so we don't accidentally
  // match the declaration above or the observability log below.
  const promotionBlock = source.match(
    /sessionGuard\.lastToolName\s*===\s*"get_price"[\s\S]{0,1200}?\)\s*\{\s*[\r\n\s]*const replyContainsPrice/,
  );
  assert.ok(
    promotionBlock,
    "P3a: the quoted-state promotion block must still exist around `lastToolName === \"get_price\"`",
  );
  assert.ok(
    /!turnDrainedRouteSideClarification/.test(promotionBlock[0]),
    "P3b: quoted-state promotion must be gated on `!turnDrainedRouteSideClarification`",
  );
}

// ---------------------------------------------------------------------------
// P4: observability — when the veto fires, an explicit
// `[one-brain/clarify-preserved] skipped_quoted_promotion` log must be
// emitted so the regression can be correlated in journalctl. The log must
// include the stale route (to confirm it WAS the stale-guard case) and the
// currently-preserved `requested_slot` + pending pickup/dropoff (to confirm
// the clarification state was NOT clobbered).
// ---------------------------------------------------------------------------
assert.ok(
  /\[one-brain\/clarify-preserved\]\s*skipped_quoted_promotion/.test(source),
  "P4a: must emit `[one-brain/clarify-preserved] skipped_quoted_promotion` when the veto fires",
);
assert.ok(
  /stale_route=\$\{sessionGuard\.lastQuotedRoute\.pickupAreaNameEn/.test(
    source,
  ),
  "P4b: clarify-preserved log must include stale_route=<pickup>_to_<dropoff>",
);
assert.ok(
  /requested_slot=\$\{conversationControllerEntry\.dialogState\?\.requestedSlot\?\.name/.test(
    source,
  ),
  "P4c: clarify-preserved log must include requested_slot",
);
assert.ok(
  /pending_pickup=\$\{conversationControllerEntry\.pendingPickupAreaNameEn/.test(
    source,
  ) &&
    /pending_dropoff=\$\{conversationControllerEntry\.pendingDropoffAreaNameEn/.test(
      source,
    ),
  "P4d: clarify-preserved log must include pending_pickup and pending_dropoff",
);

// ---------------------------------------------------------------------------
// P5: symmetry with the clarify-commit log. Both logs describe the same
// invariant from different angles:
//   [one-brain/clarify-commit]     — we materialized the clarification
//   [one-brain/clarify-preserved]  — we REFUSED to clobber it
// Both must exist in the same file so dashboards can ingest both sides.
// ---------------------------------------------------------------------------
assert.ok(
  /\[one-brain\/clarify-commit\]/.test(source) &&
    /\[one-brain\/clarify-preserved\]/.test(source),
  "P5: both clarify-commit and clarify-preserved logs must coexist in octopus-channel/index.ts",
);

// ---------------------------------------------------------------------------
// P6: class-level coverage — the veto condition considers BOTH route-side
// slots (pickup_area, dropoff_area) identically. This guards against a
// future refactor that silently drops one side.
// ---------------------------------------------------------------------------
assert.ok(
  /op\.slot\s*===\s*"pickup_area"/.test(source),
  "P6a: veto must fire on set_requested_slot(pickup_area)",
);
assert.ok(
  /op\.slot\s*===\s*"dropoff_area"/.test(source),
  "P6b: veto must fire on set_requested_slot(dropoff_area)",
);

// ---------------------------------------------------------------------------
// P7: the veto is NOT lifted for non-route-side slot asks. If it were, then
// a `set_requested_slot(sender_phone)` on a turn that also happened to have
// a stale `lastQuotedRoute` would incorrectly skip the quoted-state
// promotion (breaking the case where a legitimately-quoted route is
// followed by a phone-resend ask). Prove the lift is narrowly scoped.
// ---------------------------------------------------------------------------
{
  // Pull the small region around the lift and confirm only the route-side
  // comparison is inside it.
  const liftRegion = source.match(
    /if\s*\(\s*\n?\s*op\.slot\s*===\s*"pickup_area"[\s\S]{0,300}?turnDrainedRouteSideClarification\s*=\s*true;\s*[\r\n\s]*\}/,
  );
  assert.ok(
    liftRegion,
    "P7a: veto-lift region must be well-formed and narrowly scoped to route-side slots",
  );
  const region = liftRegion[0];
  for (const forbidden of [
    "sender_name",
    "sender_phone",
    "recipient_name",
    "recipient_phone",
    "pickup_address",
    "delivery_address",
  ]) {
    assert.ok(
      !region.includes(forbidden),
      `P7b: veto-lift region must NOT reference "${forbidden}" (only route-side slots)`,
    );
  }
}

// ---------------------------------------------------------------------------
// P8: forward-compatibility with a future `set_requested_slot` op that
// carries a new slot kind we haven't seen yet. The veto uses explicit
// string comparison rather than a catch-all — intentional, because any
// NEW slot kind we add should explicitly opt in to "this is route-side
// and therefore a clarification turn". A silent catch-all would couple
// slot additions to quoted-state semantics in a way that's easy to break.
// ---------------------------------------------------------------------------
assert.ok(
  !/turnDrainedRouteSideClarification\s*=\s*true[\s\S]{0,80}else/.test(source),
  "P8: veto-lift must not have a bare else that flips on ALL slot kinds",
);

// ---------------------------------------------------------------------------
// P9: the veto does not reference `appliedPendingArea`. A turn where only
// `set_pending_area` fired (BOTH legs resolved, full quote produced)
// should STILL promote to quoted. The veto is specifically about
// clarification turns, not all turns that touched area state.
// ---------------------------------------------------------------------------
{
  const promotionCondition = source.match(
    /sessionGuard\.lastToolName\s*===\s*"get_price"[\s\S]{0,1800}?\)\s*\{\s*[\r\n\s]*const replyContainsPrice/,
  );
  assert.ok(
    promotionCondition,
    "P9a: promotion condition must be locatable around `lastToolName === \"get_price\"`",
  );
  assert.ok(
    /!turnDrainedRouteSideClarification/.test(promotionCondition[0]),
    "P9b: promotion condition must include `!turnDrainedRouteSideClarification`",
  );
  assert.ok(
    !/appliedPendingArea/.test(promotionCondition[0]),
    "P9c: promotion condition must NOT reference appliedPendingArea — a pure-resolve turn must still promote",
  );
}

console.log("[smoke] clarification turn not promoted: OK (P1..P9 invariants)");
