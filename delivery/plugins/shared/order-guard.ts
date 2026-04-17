/**
 * Order creation guardrail — the single API-boundary check before we call
 * the backend order-store.
 *
 * The LLM is free to call `create_simple_order` whenever it judges the
 * customer has confirmed. This guard is the deterministic net that makes
 * sure the request is safe to place:
 *
 *   1. Draft is complete and every field is well-formed.
 *   2. The route + service + price match a live `get_price` result from this
 *      session (or the route is resolvable and the price matches sheet).
 *   3. The customer's latest visible message actually looks like a
 *      confirmation. (Defense against the LLM jumping to order creation
 *      mid-collection.)
 *
 * This replaces the scattered stage/step/hint preconditions inside the tool.
 */

import {
  type BookingDraft,
  validateDraftForOrder,
  type DraftValidationProblem,
} from "./booking-draft.js";
import { type PersistedGuardSessionState, type PersistedQuotedRouteState } from "./guard-state.js";

export type OrderGuardRejection =
  | { ok: false; code: "draft_incomplete"; missing: string[] }
  | { ok: false; code: "draft_invalid"; invalid: DraftValidationProblem[] }
  | { ok: false; code: "no_live_quote"; message: string }
  | { ok: false; code: "route_mismatch"; message: string; expected: string; actual: string }
  | { ok: false; code: "service_not_quoted"; message: string; available: string[] }
  | { ok: false; code: "price_mismatch"; message: string; expected: number; actual: number }
  | { ok: false; code: "confirmation_missing"; message: string };

export type OrderGuardResult = { ok: true } | OrderGuardRejection;

export type GuardedOrderRequest = {
  draft: BookingDraft;
  pickupAreaNameEn: string;
  dropoffAreaNameEn: string;
  deliveryType: string;
  quotedPrice: number;
  visibleCustomerText: string | null;
  lastQuotedRoute: PersistedQuotedRouteState | null;
  /**
   * If true, skip the confirmation-text sniff. Use when the orchestrator
   * already established confirmation out of band (e.g. structured signal).
   */
  skipConfirmationCheck?: boolean;
};

const CONFIRMATION_PATTERNS: RegExp[] = [
  /^\s*(yes|yeah|yep|sure|ok|okay|k|confirm(ed)?|proceed|go\s*ahead|do\s*it|place\s*it|book(ed)?|send\s*it|ship\s*it|yalla|yallah)\b.*$/i,
  /^\s*(confirmed|please\s*proceed|go)\b.*$/i,
  /^(نعم|اي|ايي|أكيد|اكيد|أكده|اكده|مؤكد|أكد|اكد|تمام|اكمل|كمل|احجز|أرسل|ارسل|ابعث|سوها|نفذ|يلا|يالله|اوكي|اوكيه|طيب)\s*.*$/,
];

export function looksLikeConfirmation(text: string | null | undefined): boolean {
  if (!text) return false;
  const trimmed = String(text).trim();
  if (!trimmed) return false;
  if (trimmed.length > 120) {
    // Long freeform message — if the first clause looks like a confirmation
    // token we accept, otherwise we don't.
    const head = trimmed.split(/[.,\n!?؟]/)[0] || trimmed;
    return CONFIRMATION_PATTERNS.some((rx) => rx.test(head));
  }
  return CONFIRMATION_PATTERNS.some((rx) => rx.test(trimmed));
}

function pricesMatch(a: number, b: number): boolean {
  if (!Number.isFinite(a) || !Number.isFinite(b)) return false;
  return Math.abs(a - b) < 0.001;
}

function normalizeAreaName(value: string | null | undefined): string {
  return String(value || "").trim().toLowerCase();
}

function areaMatches(actual: string | null | undefined, expected: string | null | undefined): boolean {
  const a = normalizeAreaName(actual);
  const e = normalizeAreaName(expected);
  if (!a || !e) return false;
  return a === e;
}

/**
 * Main guard entry point. Returns `{ ok: true }` if safe to place the order,
 * or a structured rejection with a reason code and human-readable message.
 *
 * Does NOT check sheet pricing or area resolvability — those are the tool's
 * concern since they need the pricing data source. This guard only checks
 * session invariants: draft, live quote, confirmation.
 */
export function guardCreateSimpleOrder(req: GuardedOrderRequest): OrderGuardResult {
  const draftCheck = validateDraftForOrder(req.draft);
  if (!draftCheck.ok) {
    if (draftCheck.missing.length > 0) {
      return { ok: false, code: "draft_incomplete", missing: draftCheck.missing };
    }
    return { ok: false, code: "draft_invalid", invalid: draftCheck.invalid };
  }

  if (!req.skipConfirmationCheck && !looksLikeConfirmation(req.visibleCustomerText)) {
    return {
      ok: false,
      code: "confirmation_missing",
      message:
        "The customer has not explicitly confirmed the order summary in their latest message. Show them the full summary and wait for a clear confirmation before calling create_simple_order.",
    };
  }

  const quote = req.lastQuotedRoute;
  if (!quote) {
    return {
      ok: false,
      code: "no_live_quote",
      message:
        "No live quote found for this conversation. Call get_price for the pickup/dropoff route first, show the customer the price, and only place the order after they confirm.",
    };
  }

  const routeMatchesQuote =
    (areaMatches(req.pickupAreaNameEn, quote.pickupAreaNameEn) ||
      areaMatches(req.pickupAreaNameEn, quote.pickupAreaNameAr)) &&
    (areaMatches(req.dropoffAreaNameEn, quote.dropoffAreaNameEn) ||
      areaMatches(req.dropoffAreaNameEn, quote.dropoffAreaNameAr));

  if (!routeMatchesQuote) {
    return {
      ok: false,
      code: "route_mismatch",
      message:
        "The pickup/dropoff route you are about to book does not match the last quoted route. Re-quote the route with get_price and confirm the new price with the customer before calling create_simple_order.",
      expected: `${quote.pickupAreaNameEn} → ${quote.dropoffAreaNameEn}`,
      actual: `${req.pickupAreaNameEn} → ${req.dropoffAreaNameEn}`,
    };
  }

  const quotedPriceForService = quote.pricesByType?.[req.deliveryType];
  if (quotedPriceForService == null) {
    const available = Object.keys(quote.pricesByType || {});
    return {
      ok: false,
      code: "service_not_quoted",
      message: `Service "${req.deliveryType}" was not part of the last live quote. Ask get_price for it on this route, confirm with the customer, then retry.`,
      available,
    };
  }

  if (!pricesMatch(req.quotedPrice, quotedPriceForService)) {
    return {
      ok: false,
      code: "price_mismatch",
      message: `The price you passed (${req.quotedPrice}) does not match the live quoted price (${quotedPriceForService}) for ${req.deliveryType} on ${quote.pickupAreaNameEn} → ${quote.dropoffAreaNameEn}. Use the live quoted price or re-quote.`,
      expected: quotedPriceForService,
      actual: req.quotedPrice,
    };
  }

  return { ok: true };
}

/**
 * Human-readable rejection summary the LLM can consume inside the tool
 * result. Kept short and imperative — the LLM should parse the code and
 * the message tells it what to do next.
 */
export function describeRejection(reject: OrderGuardRejection): string {
  switch (reject.code) {
    case "draft_incomplete":
      return `draft_incomplete:${reject.missing.join(",")}`;
    case "draft_invalid":
      return `draft_invalid:${reject.invalid.map((i) => `${i.field}:${i.reason}`).join(",")}`;
    case "no_live_quote":
      return "no_live_quote";
    case "route_mismatch":
      return `route_mismatch:expected=${reject.expected}|actual=${reject.actual}`;
    case "service_not_quoted":
      return `service_not_quoted:available=${reject.available.join(",")}`;
    case "price_mismatch":
      return `price_mismatch:expected=${reject.expected}|actual=${reject.actual}`;
    case "confirmation_missing":
      return "confirmation_missing";
  }
}

/** Convenience: session only has `lastQuotedRoute`, pass it through. */
export function extractLastQuotedRoute(
  session: PersistedGuardSessionState | null | undefined,
): PersistedQuotedRouteState | null {
  return session?.lastQuotedRoute || null;
}
