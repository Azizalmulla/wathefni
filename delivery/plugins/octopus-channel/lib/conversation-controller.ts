// ---------------------------------------------------------------------------
// Wave 3 extraction: conversation controller factory.
// Owns read/write access to the persisted conversation-controller state plus
// the in-process `globalThis.__ridersConversationControllerState` mirror that
// other plugins (riders-tools) read synchronously.
//
// Extracted from `plugins/octopus-channel/index.ts`. `index.ts` now builds a
// single controller instance at boot (passing in the persisted state store and
// the `createEmptyBookingDraft` seed from conversation-policy) and calls the
// factory methods instead of the inlined helpers.
// ---------------------------------------------------------------------------

import type { PersistedConversationControllerEntry } from "../../shared/conversation-policy";
import type { ConversationControllerState } from "./types";

export type ConversationControllerOptions = {
  load(): Promise<ConversationControllerState>;
  save(state: ConversationControllerState): Promise<void>;
  expiryMs: number;
  createEmptyBookingDraft(): PersistedConversationControllerEntry["bookingDraft"];
};

export type ConversationController = {
  isExpired(entry: PersistedConversationControllerEntry | null): boolean;
  get(params: {
    key: string;
    accountId: string;
    conversationId: string;
    replyTarget: string;
  }): Promise<PersistedConversationControllerEntry>;
  upsert(
    key: string,
    entry: PersistedConversationControllerEntry,
  ): Promise<void>;
  mirror(
    key: string,
    entry: PersistedConversationControllerEntry | null,
  ): void;
};

export function createConversationController(
  options: ConversationControllerOptions,
): ConversationController {
  const { load, save, expiryMs, createEmptyBookingDraft } = options;

  function isExpired(entry: PersistedConversationControllerEntry | null): boolean {
    if (!entry) {
      return true;
    }
    return (Date.now() - entry.lastActivityTs) > expiryMs;
  }

  async function get(params: {
    key: string;
    accountId: string;
    conversationId: string;
    replyTarget: string;
  }): Promise<PersistedConversationControllerEntry> {
    const state = await load();
    const existing = state[params.key];
    if (existing && !isExpired(existing)) {
      return {
        bookingStep: "none",
        quotePickupAreaNameEn: null,
        quotePickupAreaNameAr: null,
        quoteDropoffAreaNameEn: null,
        quoteDropoffAreaNameAr: null,
        selectedQuoteOptionType: null,
        selectedQuoteOptionLabelAr: null,
        selectedQuoteOptionLabelEn: null,
        selectedQuoteOptionPrice: null,
        selectedQuoteOptionDirectChatBookingStatus: null,
        selectedDeliveryType: null,
        quotedPrice: null,
        ...existing,
        bookingDraft: {
          ...createEmptyBookingDraft(),
          ...(existing.bookingDraft || {}),
        },
      };
    }
    if (existing) {
      delete state[params.key];
      await save(state);
    }
    return {
      lastActivityTs: Date.now(),
      language: "en",
      explicitLanguage: null,
      stage: "idle",
      bookingStep: "none",
      conversationId: params.conversationId,
      replyTarget: params.replyTarget,
      accountId: params.accountId,
      quoteRouteKey: null,
      quoteTs: null,
      quotePickupAreaNameEn: null,
      quotePickupAreaNameAr: null,
      quoteDropoffAreaNameEn: null,
      quoteDropoffAreaNameAr: null,
      selectedQuoteOptionType: null,
      selectedQuoteOptionLabelAr: null,
      selectedQuoteOptionLabelEn: null,
      selectedQuoteOptionPrice: null,
      selectedQuoteOptionDirectChatBookingStatus: null,
      selectedDeliveryType: null,
      quotedPrice: null,
      bookingDraft: createEmptyBookingDraft(),
    };
  }

  async function upsert(
    key: string,
    entry: PersistedConversationControllerEntry,
  ): Promise<void> {
    const state = await load();
    state[key] = entry;
    for (const [otherKey, otherEntry] of Object.entries(state)) {
      if (isExpired(otherEntry)) {
        delete state[otherKey];
      }
    }
    await save(state);
  }

  function mirror(
    key: string,
    entry: PersistedConversationControllerEntry | null,
  ): void {
    const root = (globalThis as any);
    const existing = root.__ridersConversationControllerState;
    const map: Map<string, PersistedConversationControllerEntry> =
      existing?.entries instanceof Map ? existing.entries : new Map();
    if (entry) {
      const aliases = new Set([
        key,
        entry.conversationId,
        entry.replyTarget,
        `${entry.accountId}::${entry.conversationId}`,
      ].filter(Boolean) as string[]);
      for (const alias of aliases) {
        map.set(alias, entry);
      }
    } else {
      map.delete(key);
    }
    root.__ridersConversationControllerState = { entries: map };
  }

  return {
    isExpired,
    get,
    upsert,
    mirror,
  };
}
