#!/usr/bin/env node
/**
 * Smoke test: native WhatsApp location pins satisfy active address steps.
 *
 * Regression locked:
 *   pickup address ask → customer sends WhatsApp location pin
 *   old behavior: LLM wrote the pin as pickup_extra, so pickup_block/street
 *                 stayed missing and the bot asked for pickup block again.
 *   expected: native pin becomes pickupLocation/deliveryLocation, and block
 *             / street are no longer required for that side.
 */

import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

function makeLocation() {
  return {
    source: "location_pin",
    latitude: 29.204677581787,
    longitude: 48.101867675781,
    name: null,
    address: null,
    resolvedAreaName: "Abu Ftaira",
  };
}

function makeEntry({ bookingStep = "pickup_address", requestedSlot = "pickup_block" } = {}) {
  return {
    lastActivityTs: 1,
    language: "en",
    explicitLanguage: null,
    stage: "collecting_booking_details",
    bookingStep,
    conversationId: "test-conv",
    replyTarget: "96500000000",
    accountId: "default",
    quoteRouteKey: "Abu Ftaira::Al Masayel",
    quoteTs: 1,
    quotePickupAreaNameEn: "Abu Ftaira",
    quotePickupAreaNameAr: "ابو فطيرة",
    quoteDropoffAreaNameEn: "Al Masayel",
    quoteDropoffAreaNameAr: "المسايل",
    pendingPickupAreaNameEn: null,
    pendingPickupAreaNameAr: null,
    pendingDropoffAreaNameEn: null,
    pendingDropoffAreaNameAr: null,
    selectedQuoteOptionType: "sedan_normal",
    selectedQuoteOptionLabelAr: "سيارة عادية",
    selectedQuoteOptionLabelEn: "Standard sedan",
    selectedQuoteOptionPrice: 1.25,
    selectedQuoteOptionDirectChatBookingStatus: "bookable",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
    pendingReplyText: null,
    bookingDraft: {
      senderName: "aziz almulla",
      senderPhone: "96599338566",
      recipientName: "ahmad basha",
      recipientPhone: "99384578",
      pickupBlock: null,
      pickupStreet: null,
      pickupHouse: null,
      pickupAvenue: null,
      pickupExtra: null,
      pickupLocation: null,
      deliveryBlock: null,
      deliveryStreet: null,
      deliveryHouse: null,
      deliveryAvenue: null,
      deliveryExtra: null,
      deliveryLocation: null,
      pendingLocation: null,
    },
    dialogState: {
      slots: {},
      requestedSlot: requestedSlot
        ? { name: requestedSlot, askedTs: 1, options: null }
        : null,
      version: 1,
    },
  };
}

async function main() {
  const bookingFlowPath = path.join(deliveryRoot, "plugins/octopus-channel/lib/booking-flow.ts");
  const mod = await loadDeliveryTsModule(import.meta.url, bookingFlowPath);
  const {
    bindNativeLocationToAddressStep,
    diagnoseBookingAddressMissing,
    hasSatisfiedBookingAddress,
    resolveNativeLocationAddressRole,
  } = mod;

  {
    const entry = makeEntry();
    assert.equal(resolveNativeLocationAddressRole(entry), "pickup");
    const result = bindNativeLocationToAddressStep({
      entry,
      location: makeLocation(),
      now: 99,
    });
    assert.equal(result.role, "pickup");
    assert.equal(result.entry.bookingDraft.pickupLocation.latitude, makeLocation().latitude);
    assert.equal(result.entry.bookingDraft.pickupExtra, null);
    assert.equal(result.entry.bookingDraft.pickupBlock, null);
    assert.equal(result.entry.bookingDraft.pickupStreet, null);
    assert.equal(result.entry.dialogState.requestedSlot, null);
    assert.equal(hasSatisfiedBookingAddress(result.entry.bookingDraft, "pickup"), true);
    assert.deepEqual(diagnoseBookingAddressMissing(result.entry.bookingDraft, "pickup"), []);
    assert.equal(result.entry.bookingStep, "delivery_address");
  }

  {
    const entry = makeEntry();
    const first = bindNativeLocationToAddressStep({
      entry,
      location: makeLocation(),
      now: 100,
    }).entry;
    const withOptionalHouse = {
      ...first,
      bookingDraft: {
        ...first.bookingDraft,
        pickupHouse: "13",
      },
      dialogState: {
        ...first.dialogState,
        requestedSlot: null,
      },
    };
    assert.equal(hasSatisfiedBookingAddress(withOptionalHouse.bookingDraft, "pickup"), true);
    assert.deepEqual(diagnoseBookingAddressMissing(withOptionalHouse.bookingDraft, "pickup"), []);
  }

  {
    const entry = makeEntry({
      bookingStep: "delivery_address",
      requestedSlot: "delivery_street",
    });
    assert.equal(resolveNativeLocationAddressRole(entry), "delivery");
    const result = bindNativeLocationToAddressStep({
      entry,
      location: { ...makeLocation(), resolvedAreaName: "Al Masayel" },
      now: 101,
    });
    assert.equal(result.role, "delivery");
    assert.equal(result.entry.bookingDraft.deliveryLocation.resolvedAreaName, "Al Masayel");
    assert.equal(result.entry.dialogState.requestedSlot, null);
    assert.equal(hasSatisfiedBookingAddress(result.entry.bookingDraft, "delivery"), true);
  }

  {
    const entry = makeEntry({ bookingStep: "recipient", requestedSlot: "recipient_name" });
    assert.equal(resolveNativeLocationAddressRole(entry), null);
    assert.equal(
      bindNativeLocationToAddressStep({ entry, location: makeLocation(), now: 102 }),
      null,
    );
  }

  console.log("smoke-test-native-location-address-binding: OK");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
