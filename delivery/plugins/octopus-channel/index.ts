/// <reference path="./node-shims.d.ts" />
import { promises as fs } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import {
  buildConversationControllerKey,
  classifyCustomerIntent,
  CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS,
  createEmptyBookingDraft,
  BookingCollectionStep,
  ConversationFlowStage,
  CustomerIntent,
  detectConversationLanguage,
  detectExplicitLanguageRequest,
  extractTrackingOrderId,
  hasActiveQuotedBookingAuthority,
  hasVisibleArabic,
  hasVisibleLatin,
  hasRouteEvidence,
  isBookingStartIntent,
  isPassengerTransportRequest,
  PersistedBookingLocation,
  PersistedBookingDraft,
  isGeneralServiceInquiry,
  isSimpleGreeting,
  isTrackingIntent,
  normalizeIntentText,
  PersistedConversationControllerEntry,
  resolveCustomerReplyLanguage,
  resolveSessionIdentityKey,
} from "../shared/conversation-policy";
import { findPersistedGuardSession } from "../shared/guard-state";
import {
  drainResponderStateOps,
  clearResponderStateOps,
  ResponderStateOp,
  ResponderBookingFieldOp,
  validateApplyBookingFieldOp,
  sanityCheckBookingDraft,
  DraftSanityProblem,
} from "../shared/responder-state-ops";
import {
  applyBookingFieldPatch,
  type BookingFieldPatch,
} from "../shared/booking-draft";
import { verifyAndRepairOutbound } from "../shared/outbound-verify";
import {
  extractForNextAction,
  type FastPathAction,
} from "../shared/fast-path-extractor";
import type {
  ChannelPlugin,
  OpenClawConfig,
  OpenClawPluginApi,
  OctopusChannelSection,
  ResolvedOctopusAccount,
  SavedAddress,
  SavedCustomerOrder,
  CustomerProfile,
  OctopusInboundAudioMessage,
  OctopusInboundImageMessage,
  OctopusInboundLocationMessage,
  CachedGeoArea,
  DebouncedMessage,
  DebounceBucket,
  PersistedInactivityEntry,
  InactivityState,
  PersistedClosedConversationAlert,
  ClosedConversationAlertState,
  OctopusReplySource,
  ConversationControllerState,
  IngressLedgerStatus,
  PersistedIngressLedgerEntry,
  IngressLedgerState,
} from "./lib/types";
import {
  asTrimmedString,
  normalizePhone,
  looksLikePhone,
  normalizeAllowEntry,
  normalizeAdminSenderId,
  buildAdminSenderIdCandidates,
  splitMimeType,
  describePath,
  computeStableTextHash,
} from "./lib/normalize";
import {
  MAP_URL_RE,
  SHORTENED_RE,
  extractFromMapUrl,
  matchPlaceNameToGeoArea,
} from "./lib/maps";
import {
  readRequestBody as libReadRequestBody,
  writeJson,
  hashIngressPayload,
  extractWebhookRequestId,
  resolveRemoteAddress,
  createIngressId,
  formatWebhookLogValue,
  logWebhookEvent,
  isTerminalIngressStatus,
  extractConversationId,
  extractWhatsAppMessages,
  extractMessageText,
  extractWhatsAppMessageId,
  extractReplyTarget,
  extractAudioMessage,
  extractImageMessage,
  extractLocationMessage,
  getAudioFileExtension,
  getImageFileExtension,
} from "./lib/webhook";
import {
  isProviderErrorText,
  sanitizeAgentReplyText,
  normalizeReplyTextForComparison,
  looksLikePriceOnlyReply,
  containsArabic,
  containsLatin,
  buildDeterministicGreetingReply,
  buildDeterministicPassengerTransportReply,
  buildDeterministicLanguageSwitchReply,
  buildDeterministicServiceOverviewReply,
  buildDeterministicGraceWindowReply,
  buildProviderIssueFallbackReply,
} from "./lib/text";
import {
  normalizeBookingPhone,
  normalizeCurrentWhatsappBookingPhone,
  pickCurrentWhatsappPhone,
  cleanParsedName,
  textMentionsCurrentWhatsappNumber,
  isSenderPhoneConfirmationText,
  parseSenderStepInput,
  parseRecipientStepInput,
  normalizeAddressFieldValue,
  stripAddressFieldLabels,
  parseAddressStepInput,
} from "./lib/booking-parse";
import {
  safeJsonParse,
  parseObjectValue,
  extractTextFromContent,
  getSessionRecordTimestamp,
  isTrackingOnlyBehaviorText,
  filterTrackingOnlyBehaviorRules,
} from "./lib/session-helpers";
import { createIngressLedger } from "./lib/ingress-ledger";
import { createJsonStateStore } from "./lib/persisted-state";
import { createConversationController } from "./lib/conversation-controller";
import { createGeoAreaLoader } from "./lib/geo-area-loader";
import {
  createCustomerProfileStore,
  formatCustomerMemoryValue,
  hasSavedAddressEvidence,
  isSuspiciousSavedOrder,
  looksLikeSavedPhoneValue,
  sanitizeCustomerProfile,
} from "./lib/customer-profile";
import {
  stripBookingContinuationLeadIn,
  includesAnyNormalizedPhrase,
  isSummaryEditRequest,
  textContainsUrl,
  shouldMoveToHumanAgent,
  buildDeterministicTrackingGuardReply,
} from "./lib/intent-text";
import {
  formatLocationAsText,
  formatLocationPinContext,
  createPersistedBookingLocation,
  buildSavedAddress,
} from "./lib/location-formatting";
import {
  hasStructuredBookingLocation,
  hasCompleteTextAddress,
  hasSatisfiedBookingAddress,
  resolveNextBookingStepFromDraft,
  getLocationRoleSelection,
  formatPersistedBookingLocationLabel,
  buildSavedLocationRoleReply,
  buildDeterministicLocationSavedDuringIdentityReply,
  buildDeterministicBookingDetailsReply,
  buildPendingOrderSummaryFingerprint,
  formatSummaryAreaLine,
} from "./lib/booking-flow";
import type {
  RouteQuoteOption,
  StoredQuotedRoute,
  SameRouteQuoteFollowupAction,
} from "./lib/quoted-options";
import {
  BOOKABLE_QUOTED_OPTION_TYPES,
  DELIVERY_TYPE_ALIASES,
  SAME_ROUTE_OTHER_OPTIONS_MARKERS,
  SAME_ROUTE_CONFIRM_CURRENT_MARKERS,
  isBookableQuotedOptionType,
  getQuotedRouteDefaultOption,
  getQuotedRouteOption,
  getActiveSelectedQuotedOption,
  formatQuotedOptionLabel,
  formatQuotedOptionPrice,
  applySelectedQuotedOptionToController,
  syncControllerSelectionFromQuotedRoute,
  buildQuotedOptionAliases,
  scoreQuotedOptionMatch,
  resolveSameRouteQuoteFollowupAction,
  buildDeterministicSelectedQuotedOptionReply,
  buildDeterministicOtherQuotedOptionsReply,
  buildQuotedRouteContextLines,
} from "./lib/quoted-options";
import {
  shouldIncludeQuotedRouteContext,
  formatOneBrainValue,
  computeOneBrainMissingFields,
  computeOneBrainNextRequiredAction,
  formatOneBrainLiveChannelContext,
} from "./lib/one-brain-context";
import type { OneBrainNextRequiredAction } from "./lib/one-brain-context";
import { formatLiveChannelContext } from "./lib/live-channel-context";
import type {
  InterpretedCustomerTurn,
  InterpretedCustomerTurnAction,
  InterpretedBookingFields,
} from "./lib/interpreter-types";

const nodeProcess = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process;
const env = nodeProcess?.env ?? {};
const nodeBuffer = (globalThis as { Buffer?: any }).Buffer;
const webFormData = (globalThis as { FormData?: any }).FormData;
const webBlob = (globalThis as { Blob?: any }).Blob;

// =========================================================================
// Riders geo area auto-resolution (Haversine nearest-area lookup)
// Fetches all areas from Riders Grid API on first use, caches in memory.
// =========================================================================

// CachedGeoArea type moved to ./lib/types.ts (wave 2a).

// loadAllGeoAreas, resolveNearestArea, haversineKm moved to
// ./lib/geo-area-loader.ts (wave 3).
const RIDERS_GRID_BASE =
  env.RIDERS_GRID_API_BASE_URL?.replace(/\/+$/, "") ||
  "https://app-order.tryriders.com/api";
const RIDERS_GRID_KEY = env.RIDERS_GRID_API_KEY?.trim() || env.RIDERS_API_KEY?.trim() || "";
const geoAreaLoader = createGeoAreaLoader({
  baseUrl: RIDERS_GRID_BASE,
  apiKey: RIDERS_GRID_KEY,
});
const loadAllGeoAreas = geoAreaLoader.loadAll;
const resolveNearestArea = geoAreaLoader.resolveNearestArea;

const DEFAULT_ACCOUNT_ID = "default";
const DEFAULT_BASE_URL = "https://app.ai-octopus.com";
const DEFAULT_TEXT_CHUNK_LIMIT = 3500;
const DEFAULT_TYPING_REFRESH_MS = 9000;
const DEFAULT_MEDIA_MAX_MB = 25;
const DEFAULT_BEHAVIOR_POLICY_PUBLISHED_PATH = new URL(
  "../../workspaces/riders/data/behavior-policy.published.json",
  import.meta.url,
);
const HOME_DIR = env.HOME?.trim() || ".";
const OPENCLAW_PROFILE = env.OPENCLAW_PROFILE?.trim() || "delivery";
const RIDERS_CUSTOMER_MEMORY_DIR =
  env.RIDERS_CUSTOMER_MEMORY_DIR?.trim() ||
  path.join(HOME_DIR, `.openclaw-${OPENCLAW_PROFILE}`, "customer-profiles");
const MAX_CUSTOMER_PROFILE_SESSION_FILES = 40;
const WORKSPACE_PROMPT_FILES = ["AGENTS.md", "IDENTITY.md", "SKILL.md", "TOOLS.md"] as const;
const PROVIDER_NAME = "octopus";
const PATH_PREFIX = "/webhook";
const DEFAULT_ADMIN_AGENT_ID = "riders-admin";
const workspacePromptRevisionCache = new Map<string, { signature: string; revision: string }>();
const ADMIN_ALLOWLIST = Array.from(
  new Set(
    [
      env.AI_OCTOPUS_ADMIN_ALLOWLIST,
      env.RIDERS_PRICING_ADMIN_ALLOWLIST,
      env.RIDERS_BEHAVIOR_ADMIN_ALLOWLIST,
    ]
      .flatMap((value) => String(value || "").split(","))
      .map((value) => normalizeAdminSenderId(value))
      .filter(Boolean),
  ),
);

const INBOUND_DEBOUNCE_MS = 5000;
const INBOUND_MEDIA_DEBOUNCE_MS = INBOUND_DEBOUNCE_MS;

// DebouncedMessage + DebounceBucket types moved to ./lib/types.ts (wave 2a).

const inboundDebounceMap = new Map<string, DebounceBucket>();

function hasInboundMedia(msg: Pick<DebouncedMessage, "audioMessage" | "imageMessage" | "locationMessage">): boolean {
  return Boolean(msg.audioMessage || msg.imageMessage || msg.locationMessage);
}

function resolveInboundDebounceMs(messages: DebouncedMessage[]): number {
  return messages.some((msg) => hasInboundMedia(msg))
    ? INBOUND_MEDIA_DEBOUNCE_MS
    : INBOUND_DEBOUNCE_MS;
}

// ---------------------------------------------------------------------------
// Inactivity timeout — restart-resilient, language-aware
// Two-step: nudge after 10 min, close after 25 min
// State is persisted to disk so timers survive service restarts.
// A periodic sweep (every 30 s) checks timestamps and sends messages.
// ---------------------------------------------------------------------------

const INACTIVITY_NUDGE_MS = Math.max(
  60_000,
  Number(env.INACTIVITY_NUDGE_MINUTES || "10") * 60_000,
);
const INACTIVITY_CLOSE_MS = Math.max(
  60_000,
  Number(env.INACTIVITY_CLOSE_MINUTES || "25") * 60_000,
);
const INACTIVITY_SWEEP_MS = 30_000;
const INACTIVITY_EXPIRY_MS = 2 * 60 * 60_000; // garbage-collect after 2 h
const INACTIVITY_STATE_PATH = path.join(
  HOME_DIR,
  `.openclaw-${OPENCLAW_PROFILE}`,
  "inactivity-state.json",
);
const INGRESS_LEDGER_PATH = path.join(
  HOME_DIR,
  `.openclaw-${OPENCLAW_PROFILE}`,
  "octopus-ingress-ledger.json",
);
const INGRESS_LEDGER_RETENTION_MS = 7 * 24 * 60 * 60_000;
const INGRESS_LEDGER_MAX_ENTRIES = 3000;
const INGRESS_REPLAY_MIN_AGE_MS = 15_000;
const INGRESS_REPLAY_BATCH_LIMIT = 50;
const CLOSED_CONVERSATION_ALERTS_PATH = path.join(
  HOME_DIR,
  `.openclaw-${OPENCLAW_PROFILE}`,
  "closed-conversation-alerts.json",
);
// PersistedInactivityEntry, InactivityState, PersistedClosedConversationAlert,
// ClosedConversationAlertState, OctopusReplySource, ConversationControllerState,
// IngressLedgerStatus, PersistedIngressLedgerEntry, IngressLedgerState moved to
// ./lib/types.ts (wave 2a).

// Runtime references — rebuilt after restart, not persisted
let inactivityApiRef: OpenClawPluginApi | null = null;
const inactivityAccountCache = new Map<string, ResolvedOctopusAccount>();
let inactivitySweepTimer: ReturnType<typeof setInterval> | null = null;
let inactivitySweepRunning = false;

const CONVERSATION_CONTROLLER_EXPIRY_MS = 6 * 60 * 60_000;
const CONVERSATION_CONTROLLER_STATE_PATH = path.join(
  HOME_DIR,
  `.openclaw-${OPENCLAW_PROFILE}`,
  "conversation-controller-state.json",
);

// loadInactivityState/saveInactivityState, loadClosedConversationAlertState/
// saveClosedConversationAlertState, loadConversationControllerState/
// saveConversationControllerState moved to ./lib/persisted-state.ts (wave 3).
const inactivityStateStore = createJsonStateStore<InactivityState>(INACTIVITY_STATE_PATH);
const loadInactivityState = inactivityStateStore.load;
const saveInactivityState = inactivityStateStore.save;

const closedConversationAlertStore =
  createJsonStateStore<ClosedConversationAlertState>(CLOSED_CONVERSATION_ALERTS_PATH);
const loadClosedConversationAlertState = closedConversationAlertStore.load;
const saveClosedConversationAlertState = closedConversationAlertStore.save;

const conversationControllerStore =
  createJsonStateStore<ConversationControllerState>(CONVERSATION_CONTROLLER_STATE_PATH);
const loadConversationControllerState = conversationControllerStore.load;
const saveConversationControllerState = conversationControllerStore.save;

// loadIngressLedgerState, pruneIngressLedgerState, saveIngressLedgerState,
// mutateIngressLedgerState, upsertIngressLedgerEntry, updateIngressLedgerEntries,
// persistAcceptedIngressEntry moved to ./lib/ingress-ledger.ts (wave 3).
// `ingressLedger` below is the single factory instance used by this plugin.
const ingressLedger = createIngressLedger({
  ledgerPath: INGRESS_LEDGER_PATH,
  retentionMs: INGRESS_LEDGER_RETENTION_MS,
  maxEntries: INGRESS_LEDGER_MAX_ENTRIES,
});
const loadIngressLedgerState = ingressLedger.load;
const upsertIngressLedgerEntry = ingressLedger.upsert;
const updateIngressLedgerEntries = ingressLedger.update;
const persistAcceptedIngressEntry = ingressLedger.persistAccepted;

// isTerminalIngressStatus moved to ./lib/webhook.ts (wave 2a).

// isConversationControllerEntryExpired, getConversationControllerEntry,
// upsertConversationControllerEntry, mirrorConversationControllerEntry
// moved to ./lib/conversation-controller.ts (wave 3).
const conversationController = createConversationController({
  load: loadConversationControllerState,
  save: saveConversationControllerState,
  expiryMs: CONVERSATION_CONTROLLER_EXPIRY_MS,
  createEmptyBookingDraft,
});
const isConversationControllerEntryExpired = conversationController.isExpired;
const getConversationControllerEntry = conversationController.get;
const upsertConversationControllerEntry = conversationController.upsert;
const mirrorConversationControllerEntry = conversationController.mirror;

async function recordInactivityActivity(params: {
  api: OpenClawPluginApi;
  account: ResolvedOctopusAccount;
  conversationId: string;
  replyTarget: string;
  messageText: string | null;
  languageOverride?: "ar" | "en" | null;
}): Promise<void> {
  const { api, account, conversationId, replyTarget, messageText, languageOverride } = params;
  const key = `${account.accountId}::${conversationId}`;

  // Update runtime caches
  inactivityApiRef = api;
  inactivityAccountCache.set(account.accountId, account);

  // Update persisted state — new message resets nudge
  const state = await loadInactivityState();
  const existing = state[key];
  const language = languageOverride || (
    messageText
    ? detectConversationLanguage(messageText)
    : existing?.language ?? "en"
  );
  state[key] = {
    lastActivityTs: Date.now(),
    nudgeSentTs: null,
    language,
    conversationId,
    replyTarget,
    accountId: account.accountId,
  };
  await saveInactivityState(state);
}

async function sweepInactivity(): Promise<void> {
  if (inactivitySweepRunning) return;
  inactivitySweepRunning = true;
  try {
    const api = inactivityApiRef;
    if (!api) return;

    const state = await loadInactivityState();
    const now = Date.now();
    let dirty = false;

    for (const [key, entry] of Object.entries(state)) {
      let account = inactivityAccountCache.get(entry.accountId);
      if (!account) {
        const resolvedAccount = resolveOctopusAccount(api.config, entry.accountId);
        if (!resolvedAccount.enabled) {
          api.logger.warn(
            `[octopus] inactivity sweep skipped disabled account accountId=${entry.accountId} conversation=${entry.conversationId}`,
          );
          continue;
        }
        inactivityAccountCache.set(resolvedAccount.accountId, resolvedAccount);
        account = resolvedAccount;
        api.logger.info(
          `[octopus] inactivity sweep refreshed account cache accountId=${entry.accountId} conversation=${entry.conversationId}`,
        );
      }

      const elapsed = now - entry.lastActivityTs;

      // Garbage-collect very stale entries
      if (elapsed > INACTIVITY_EXPIRY_MS) {
        delete state[key];
        dirty = true;
        continue;
      }

      // Close threshold (only after nudge was already sent). Keep the entry
      // until delivery succeeds so transient send failures can retry safely.
      if (entry.nudgeSentTs !== null && elapsed >= INACTIVITY_CLOSE_MS) {
        const closeLang = entry.language;
        const closeConvId = entry.conversationId;
        const closeReplyTarget = entry.replyTarget;
        const closeAccountId = entry.accountId;
        try {
          const text =
            closeLang === "ar"
              ? "شكرا لكم راح نغلق المحادثه ، و لاتترددون تكلمونّـا اي وقت.. بخدمتكم"
              : "Thank you, we will close the chat. Feel free to contact us anytime. We are at your service.";
          await sendOctopusTextReply({
            api,
            account,
            conversationId: closeConvId,
            replyTarget: closeReplyTarget,
            text,
            source: "inactivity_close",
          });
          api.logger.info(
            `[octopus] inactivity close sent conversation=${closeConvId} lang=${closeLang}`,
          );
          delete state[key];
          dirty = true;
          await saveInactivityState(state);
          dirty = false;
          const controllerKey = buildConversationControllerKey(closeAccountId, closeConvId);
          const controllerState = await loadConversationControllerState();
          if (controllerState[controllerKey]) {
            delete controllerState[controllerKey];
            await saveConversationControllerState(controllerState);
            mirrorConversationControllerEntry(controllerKey, null);
            api.logger.info(
              `[octopus] cleared conversation controller on close conversation=${closeConvId}`,
            );
          }
        } catch (error) {
          api.logger.error(
            `[octopus] inactivity close failed conversation=${closeConvId} error=${error instanceof Error ? error.message : String(error)}`,
          );
          if (isAiOctopusConversationClosedError(error)) {
            delete state[key];
            dirty = true;
            await saveInactivityState(state);
            dirty = false;
            api.logger.info(
              `[octopus] dropped inactivity close for closed conversation=${closeConvId}`,
            );
          }
        }
        continue;
      }

      // Nudge threshold — persist nudgeSentTs before sending so restarts
      // mid-flight cannot re-trigger the same nudge from stale state.
      if (entry.nudgeSentTs === null && elapsed >= INACTIVITY_NUDGE_MS) {
        entry.nudgeSentTs = now;
        dirty = true;
        await saveInactivityState(state);
        dirty = false;
        try {
          const text =
            entry.language === "ar"
              ? "للحين موجودين لخدمتكم، تامرون على اي شي بعد ثاني؟"
              : "We are still here to help. Is there anything else you need?";
          await sendOctopusTextReply({
            api,
            account,
            conversationId: entry.conversationId,
            replyTarget: entry.replyTarget,
            text,
            source: "inactivity_nudge",
          });
          api.logger.info(
            `[octopus] inactivity nudge sent conversation=${entry.conversationId} lang=${entry.language}`,
          );
        } catch (error) {
          api.logger.error(
            `[octopus] inactivity nudge failed conversation=${entry.conversationId} error=${error instanceof Error ? error.message : String(error)}`,
          );
          if (isAiOctopusConversationClosedError(error)) {
            delete state[key];
            dirty = true;
            api.logger.info(
              `[octopus] dropped inactivity nudge for closed conversation=${entry.conversationId}`,
            );
          }
        }
      }
    }

    if (dirty) {
      await saveInactivityState(state);
    }
  } finally {
    inactivitySweepRunning = false;
  }
}

function startInactivitySweep(api: OpenClawPluginApi): void {
  inactivityApiRef = api;
  if (inactivitySweepTimer) {
    return;
  }
  inactivitySweepTimer = setInterval(() => {
    void sweepInactivity();
  }, INACTIVITY_SWEEP_MS);
  void sweepInactivity();
  api.logger.info(
    `[octopus] inactivity sweep started interval=${INACTIVITY_SWEEP_MS}ms nudge=${INACTIVITY_NUDGE_MS}ms close=${INACTIVITY_CLOSE_MS}ms`,
  );
}

function flushDebounceBucket(key: string) {
  const bucket = inboundDebounceMap.get(key);
  if (!bucket || bucket.messages.length === 0) {
    inboundDebounceMap.delete(key);
    return;
  }
  inboundDebounceMap.delete(key);
  const messages = bucket.messages;
  const first = messages[0];

  const combinedText = messages
    .map((m) => m.messageText)
    .filter(Boolean)
    .join("\n");

  const latestMessageId = messages[messages.length - 1].messageId;
  const latestPayload = messages[messages.length - 1].payload;
  const newestFirst = [...messages].reverse();
  const audioMessage = newestFirst.find((m) => m.audioMessage)?.audioMessage || null;
  const imageMessage = newestFirst.find((m) => m.imageMessage)?.imageMessage || null;
  const locationMessage = newestFirst.find((m) => m.locationMessage)?.locationMessage || null;
  const ingressIds = Array.from(new Set(messages.map((m) => m.ingressId).filter(Boolean)));

  first.api.logger.info(
    `[octopus] debounce flush key=${key} count=${messages.length} combinedLength=${(combinedText || "").length}`,
  );

  const processingStartedAt = new Date().toISOString();
  void updateIngressLedgerEntries(ingressIds, (entry) => ({
    ...entry,
    status: "processing",
    processingStartedAt,
    lastUpdatedAt: processingStartedAt,
    error: null,
  }));

  void handleInboundMessage({
    api: first.api,
    account: first.account,
    ingressIds,
    payload: latestPayload,
    conversationId: first.conversationId,
    messageText: combinedText || null,
    replyTarget: first.replyTarget,
    messageId: latestMessageId,
    audioMessage,
    imageMessage,
    locationMessage,
  })
    .then(async () => {
      const processedAt = new Date().toISOString();
      await updateIngressLedgerEntries(ingressIds, (entry) => ({
        ...entry,
        status: entry.status === "replied" || entry.status === "ignored_non_text"
          ? entry.status
          : "processed",
        processedAt: entry.processedAt || processedAt,
        lastUpdatedAt: processedAt,
      }));
    })
    .catch(async (error) => {
      const errorText = error instanceof Error ? error.message : String(error);
      first.api.logger.error(
        `[octopus] processing error account=${first.account.accountId} conversation=${first.conversationId} error=${errorText}`,
      );
      const failedAt = new Date().toISOString();
      await updateIngressLedgerEntries(ingressIds, (entry) => ({
        ...entry,
        status: "failed",
        error: errorText,
        lastUpdatedAt: failedAt,
      }));
      if (first.replyTarget) {
        try {
          await sendOctopusTextReply({
            api: first.api,
            account: first.account,
            conversationId: first.conversationId,
            replyTarget: first.replyTarget,
            text: buildProviderIssueFallbackReply("en"),
            source: "processing_error_fallback",
            ingressIds,
          });
        } catch (_) {}
      }
    });
}

function enqueueInboundMessage(msg: DebouncedMessage) {
  const key = `${msg.account.accountId}:${msg.conversationId}`;
  const existing = inboundDebounceMap.get(key);
  if (existing) {
    clearTimeout(existing.timer);
    existing.messages.push(msg);
    const debounceMs = resolveInboundDebounceMs(existing.messages);
    existing.timer = setTimeout(() => flushDebounceBucket(key), debounceMs);
    msg.api.logger.info(
      `[octopus] debounce buffered key=${key} depth=${existing.messages.length} windowMs=${debounceMs}`,
    );
  } else {
    const debounceMs = resolveInboundDebounceMs([msg]);
    const timer = setTimeout(() => flushDebounceBucket(key), debounceMs);
    inboundDebounceMap.set(key, { timer, messages: [msg] });
    msg.api.logger.info(
      `[octopus] debounce started key=${key} windowMs=${debounceMs}`,
    );
  }
  const enqueuedAt = new Date().toISOString();
  void updateIngressLedgerEntries([msg.ingressId], (entry) => ({
    ...entry,
    status: "enqueued",
    attempts: Math.max(1, Number(entry.attempts || 0)),
    lastUpdatedAt: enqueuedAt,
    note: "debounce_enqueued",
  }));
}

async function replayPendingIngressLedgerEntries(api: OpenClawPluginApi): Promise<void> {
  const state = await loadIngressLedgerState();
  const now = Date.now();
  const pendingEntries = Object.values(state)
    .filter((entry) =>
      !isTerminalIngressStatus(entry.status) &&
      Boolean(entry.payload) &&
      Boolean(entry.conversationId) &&
      (now - (Date.parse(entry.lastUpdatedAt || entry.receivedAt || "") || 0)) >= INGRESS_REPLAY_MIN_AGE_MS,
    )
    .sort((left, right) =>
      (Date.parse(left.lastUpdatedAt || left.receivedAt || "") || 0) -
      (Date.parse(right.lastUpdatedAt || right.receivedAt || "") || 0),
    )
    .slice(0, INGRESS_REPLAY_BATCH_LIMIT);
  if (pendingEntries.length === 0) {
    return;
  }
  logWebhookEvent(api.logger, "error", "operator action required", {
    cause: "pending_ingress_replay",
    pendingCount: pendingEntries.length,
    remediation: "inspect_recent_restarts_or_processing_failures",
  });
  for (const entry of pendingEntries) {
    const account = resolveOctopusAccount(api.config, entry.accountId);
    if (!account.enabled) {
      const skippedAt = new Date().toISOString();
      await updateIngressLedgerEntries([entry.ingressId], (current) => ({
        ...current,
        status: "failed",
        error: "account_disabled_during_replay",
        lastUpdatedAt: skippedAt,
      }));
      continue;
    }
    const messageText = extractMessageText(entry.payload);
    const audioMessage = !messageText ? extractAudioMessage(entry.payload) : null;
    const imageMessage = extractImageMessage(entry.payload);
    const locationMessage = extractLocationMessage(entry.payload);
    if (!messageText && !audioMessage && !imageMessage && !locationMessage) {
      const ignoredAt = new Date().toISOString();
      await updateIngressLedgerEntries([entry.ingressId], (current) => ({
        ...current,
        status: "ignored_non_text",
        processedAt: ignoredAt,
        lastUpdatedAt: ignoredAt,
        note: "replay_ignored_non_text",
      }));
      continue;
    }
    const replayedAt = new Date().toISOString();
    await updateIngressLedgerEntries([entry.ingressId], (current) => ({
      ...current,
      replayCount: Math.max(0, Number(current.replayCount || 0)) + 1,
      attempts: Math.max(1, Number(current.attempts || 0)) + 1,
      note: "replayed_after_restart",
      error: null,
      lastUpdatedAt: replayedAt,
    }));
    logWebhookEvent(api.logger, "warn", "webhook_replayed", {
      ingressId: entry.ingressId,
      requestId: entry.requestId,
      account: account.accountId,
      conversation: entry.conversationId,
      replyTarget: entry.replyTarget,
      messageId: entry.messageId,
      previousStatus: entry.status,
      replayCount: (entry.replayCount || 0) + 1,
    });
    enqueueInboundMessage({
      api,
      account,
      ingressId: entry.ingressId,
      payload: entry.payload,
      conversationId: String(entry.conversationId || ""),
      messageText,
      replyTarget: entry.replyTarget,
      messageId: entry.messageId,
      audioMessage,
      imageMessage,
      locationMessage,
    });
  }
}

const octopusChannelConfigSchema = {
  schema: {
    type: "object",
    additionalProperties: false,
    properties: {
      enabled: { type: "boolean" },
      name: { type: "string" },
      baseUrl: { type: "string" },
      bearerToken: { type: "string" },
      webhookToken: { type: "string" },
      webhookPath: { type: "string" },
      agentId: { type: "string" },
      dmPolicy: {
        type: "string",
        enum: ["open", "allowlist", "disabled", "pairing"],
      },
      allowFrom: {
        type: "array",
        items: { type: "string" },
      },
      textChunkLimit: { type: "integer", minimum: 1 },
      typingEnabled: { type: "boolean" },
      typingRefreshMs: { type: "integer", minimum: 2500 },
      mediaMaxMb: { type: "integer", minimum: 1 },
      behaviorPolicyPublishedPath: { type: "string" },
      accounts: {
        type: "object",
        additionalProperties: {
          type: "object",
          additionalProperties: false,
          properties: {
            enabled: { type: "boolean" },
            name: { type: "string" },
            baseUrl: { type: "string" },
            bearerToken: { type: "string" },
            webhookToken: { type: "string" },
            webhookPath: { type: "string" },
            agentId: { type: "string" },
            dmPolicy: {
              type: "string",
              enum: ["open", "allowlist", "disabled", "pairing"],
            },
            allowFrom: {
              type: "array",
              items: { type: "string" },
            },
            textChunkLimit: { type: "integer", minimum: 1 },
            typingEnabled: { type: "boolean" },
            typingRefreshMs: { type: "integer", minimum: 2500 },
            mediaMaxMb: { type: "integer", minimum: 1 },
            behaviorPolicyPublishedPath: { type: "string" },
          },
        },
      },
    },
  },
};

// asTrimmedString, normalizePhone, looksLikePhone, normalizeAllowEntry,
// normalizeAdminSenderId, buildAdminSenderIdCandidates moved to
// ./lib/normalize.ts (wave 2a).

function resolveInboundAgentId(defaultAgentId: string, replyTarget: string | null): string {
  const adminAgentId = asTrimmedString(env.AI_OCTOPUS_ADMIN_OPENCLAW_AGENT) || DEFAULT_ADMIN_AGENT_ID;
  const senderCandidates = buildAdminSenderIdCandidates(replyTarget);
  return senderCandidates.some((candidate) => ADMIN_ALLOWLIST.includes(candidate))
    ? adminAgentId
    : defaultAgentId;
}

function normalizeBaseUrl(value: string | null | undefined): string {
  const raw = value?.trim() || DEFAULT_BASE_URL;
  return raw.replace(/\/+$/, "") || DEFAULT_BASE_URL;
}

function normalizeWebhookPath(value: string | null | undefined, accountId: string): string {
  const raw = value?.trim();
  if (!raw) {
    return accountId === DEFAULT_ACCOUNT_ID ? PATH_PREFIX : `${PATH_PREFIX}/${accountId}`;
  }
  try {
    const parsed = new URL(raw);
    return parsed.pathname || PATH_PREFIX;
  } catch {
    return raw.startsWith("/") ? raw : `/${raw}`;
  }
}

// splitMimeType moved to ./lib/normalize.ts (wave 2a).

function getChannelSection(cfg: OpenClawConfig): OctopusChannelSection {
  const section = cfg.channels?.[PROVIDER_NAME as keyof typeof cfg.channels];
  return section && typeof section === "object" ? (section as OctopusChannelSection) : {};
}

function hasBaseAccountFields(section: OctopusChannelSection): boolean {
  return Boolean(
    section.baseUrl ||
      section.bearerToken ||
      section.webhookToken ||
      section.webhookPath ||
      section.agentId ||
      section.name ||
      section.enabled !== undefined ||
      section.dmPolicy ||
      (Array.isArray(section.allowFrom) && section.allowFrom.length > 0) ||
      section.textChunkLimit !== undefined ||
      section.typingEnabled !== undefined ||
      section.typingRefreshMs !== undefined ||
      section.mediaMaxMb !== undefined ||
      section.behaviorPolicyPublishedPath,
  );
}

function listOctopusAccountIds(cfg: OpenClawConfig): string[] {
  const section = getChannelSection(cfg);
  const accountIds = Object.keys(section.accounts || {}).filter(Boolean);
  if (hasBaseAccountFields(section) || accountIds.length === 0) {
    accountIds.unshift(DEFAULT_ACCOUNT_ID);
  }
  return Array.from(new Set(accountIds));
}

function resolveOctopusAccount(cfg: OpenClawConfig, accountId?: string | null): ResolvedOctopusAccount {
  const section = getChannelSection(cfg);
  const resolvedAccountId = asTrimmedString(accountId) || DEFAULT_ACCOUNT_ID;
  const accountSection =
    section.accounts && typeof section.accounts[resolvedAccountId] === "object"
      ? (section.accounts[resolvedAccountId] as OctopusChannelSection)
      : {};
  const baseUrl = normalizeBaseUrl(
    asTrimmedString(accountSection.baseUrl) ||
      asTrimmedString(section.baseUrl) ||
      asTrimmedString(env.AI_OCTOPUS_BASE_URL),
  );
  const bearerToken =
    asTrimmedString(accountSection.bearerToken) ||
    asTrimmedString(section.bearerToken) ||
    asTrimmedString(env.AI_OCTOPUS_BEARER_TOKEN) ||
    "";
  const webhookToken =
    asTrimmedString(accountSection.webhookToken) ||
    asTrimmedString(section.webhookToken) ||
    asTrimmedString(env.AI_OCTOPUS_WEBHOOK_TOKEN) ||
    "";
  const agentId =
    asTrimmedString(accountSection.agentId) ||
    asTrimmedString(section.agentId) ||
    asTrimmedString(env.AI_OCTOPUS_OPENCLAW_AGENT) ||
    "riders";
  const enabled =
    accountSection.enabled ??
    (resolvedAccountId === DEFAULT_ACCOUNT_ID ? (section.enabled ?? false) : true);
  const dmPolicy =
    asTrimmedString(accountSection.dmPolicy) ||
    asTrimmedString(section.dmPolicy) ||
    "open";
  const allowFrom = [
    ...((Array.isArray(section.allowFrom) ? section.allowFrom : []) as string[]),
    ...((Array.isArray(accountSection.allowFrom) ? accountSection.allowFrom : []) as string[]),
  ]
    .map((entry) => normalizeAllowEntry(entry))
    .filter(Boolean);
  const textChunkLimit = Math.max(
    1,
    Number(
      accountSection.textChunkLimit ??
        section.textChunkLimit ??
        env.AI_OCTOPUS_TEXT_CHUNK_LIMIT ??
        DEFAULT_TEXT_CHUNK_LIMIT,
    ) || DEFAULT_TEXT_CHUNK_LIMIT,
  );
  const typingEnabled =
    accountSection.typingEnabled ??
    section.typingEnabled ??
    env.AI_OCTOPUS_TYPING_ENABLED !== "false";
  const typingRefreshMs = Math.max(
    2500,
    Number(
      accountSection.typingRefreshMs ??
        section.typingRefreshMs ??
        env.AI_OCTOPUS_TYPING_REFRESH_MS ??
        DEFAULT_TYPING_REFRESH_MS,
    ) || DEFAULT_TYPING_REFRESH_MS,
  );
  const mediaMaxMb = Math.max(
    1,
    Number(accountSection.mediaMaxMb ?? section.mediaMaxMb ?? DEFAULT_MEDIA_MAX_MB) ||
      DEFAULT_MEDIA_MAX_MB,
  );
  const behaviorPolicyPublishedPath =
    asTrimmedString(accountSection.behaviorPolicyPublishedPath) ||
    asTrimmedString(section.behaviorPolicyPublishedPath) ||
    asTrimmedString(env.RIDERS_BEHAVIOR_POLICY_PUBLISHED_PATH) ||
    DEFAULT_BEHAVIOR_POLICY_PUBLISHED_PATH.pathname;
  return {
    accountId: resolvedAccountId,
    enabled,
    name: asTrimmedString(accountSection.name) || asTrimmedString(section.name) || undefined,
    baseUrl,
    bearerToken,
    webhookToken,
    webhookPath: normalizeWebhookPath(
      asTrimmedString(accountSection.webhookPath) || asTrimmedString(section.webhookPath),
      resolvedAccountId,
    ),
    agentId,
    dmPolicy,
    allowFrom: Array.from(new Set(allowFrom)),
    textChunkLimit,
    typingEnabled,
    typingRefreshMs,
    mediaMaxMb,
    behaviorPolicyPublishedPath,
  };
}

// describePath + computeStableTextHash moved to ./lib/normalize.ts (wave 2a).

function resolveAgentWorkspacePath(cfg: OpenClawConfig, agentId: string): string | null {
  const agents = cfg && typeof cfg === "object" ? (cfg as { agents?: unknown }).agents : null;
  const list =
    agents && typeof agents === "object" && Array.isArray((agents as { list?: unknown }).list)
      ? ((agents as { list: unknown[] }).list ?? [])
      : [];
  for (const entry of list) {
    if (!entry || typeof entry !== "object") {
      continue;
    }
    if (asTrimmedString((entry as { id?: unknown }).id) !== agentId) {
      continue;
    }
    const workspace = asTrimmedString((entry as { workspace?: unknown }).workspace);
    if (workspace) {
      return workspace;
    }
  }
  if (agents && typeof agents === "object") {
    const defaults = (agents as { defaults?: unknown }).defaults;
    if (defaults && typeof defaults === "object") {
      return asTrimmedString((defaults as { workspace?: unknown }).workspace) || null;
    }
  }
  return null;
}

async function resolveAgentWorkspacePromptRevision(
  cfg: OpenClawConfig,
  agentId: string,
): Promise<string> {
  const workspacePath = resolveAgentWorkspacePath(cfg, agentId);
  if (!workspacePath) {
    return "base";
  }
  const descriptors: Array<{ name: string; path: string; signature: string }> = [];
  for (const fileName of WORKSPACE_PROMPT_FILES) {
    const filePath = path.join(workspacePath, fileName);
    try {
      const stat = await fs.stat(filePath);
      descriptors.push({
        name: fileName,
        path: filePath,
        signature: `${fileName}:${Math.trunc(stat.mtimeMs)}:${stat.size}`,
      });
    } catch (error) {
      const code =
        error && typeof error === "object" && "code" in error
          ? String((error as { code?: unknown }).code || "")
          : "";
      descriptors.push({
        name: fileName,
        path: filePath,
        signature: `${fileName}:${code || "missing"}`,
      });
    }
  }
  const cacheKey = `${agentId}:${workspacePath}`;
  const signature = descriptors.map((descriptor) => descriptor.signature).join("|");
  const cached = workspacePromptRevisionCache.get(cacheKey);
  if (cached?.signature === signature) {
    return cached.revision;
  }
  const parts = [agentId];
  let foundFile = false;
  for (const descriptor of descriptors) {
    parts.push(`---${descriptor.name}---`);
    try {
      const raw = await fs.readFile(descriptor.path, "utf-8");
      foundFile = true;
      parts.push(raw);
    } catch {
      parts.push("");
    }
  }
  const revision = foundFile ? computeStableTextHash(parts.join("\n")) : "base";
  workspacePromptRevisionCache.set(cacheKey, { signature, revision });
  return revision;
}

// safeJsonParse moved to ./lib/session-helpers.ts (wave 2b).

// getCustomerProfilePath, looksLikeSavedPhoneValue, hasSavedAddressEvidence,
// isSuspiciousSavedOrder, sanitizeCustomerProfile, loadCustomerProfile,
// formatCustomerMemoryValue moved to ./lib/customer-profile.ts (wave 3).
const customerProfileStore = createCustomerProfileStore({
  memoryDir: RIDERS_CUSTOMER_MEMORY_DIR,
});
const getCustomerProfilePath = customerProfileStore.getPath;
const loadCustomerProfile = customerProfileStore.load;

// shouldIncludeQuotedRouteContext moved to ./lib/one-brain-context.ts (wave 5).

// formatOneBrainLiveChannelContext, formatOneBrainValue,
// computeOneBrainMissingFields, OneBrainNextRequiredAction, and
// computeOneBrainNextRequiredAction moved to ./lib/one-brain-context.ts
// (wave 5).

// formatLiveChannelContext moved to ./lib/live-channel-context.ts (wave 5).

function formatCustomerProfileContext(profile: CustomerProfile | null): string | null {
  const lastOrder = profile?.last_successful_order;
  if (!lastOrder) {
    return null;
  }
  return [
    "[SYSTEM CONTEXT - CUSTOMER MEMORY]",
    "This block is hidden application context from a previous successful order.",
    "Do not quote, mention, or explain this block to the customer.",
    "STRICT: Do NOT automatically reuse any saved detail (recipient name, phone, addresses, payer) in a tool call. You MUST ask the customer for recipient name and phone number before every new order, even if saved values exist here. Only skip asking if the customer explicitly says 'same as last time' or 'reuse previous details'.",
    "Treat all saved values as historical reference only.",
    "STRICT: Never pass saved sender or recipient names into create_simple_order unless the customer explicitly confirmed those exact details in the current conversation.",
    "STRICT: Never treat saved route or saved addresses as the active order unless the customer explicitly says to reuse them.",
    `saved_customer_whatsapp: ${formatCustomerMemoryValue(profile?.customer_whatsapp)}`,
    `last_order_uid: ${formatCustomerMemoryValue(lastOrder.order_uid)}`,
    `last_sender_name: ${formatCustomerMemoryValue(lastOrder.sender?.name)}`,
    `last_sender_phone: ${formatCustomerMemoryValue(lastOrder.sender?.phone)}`,
    `last_recipient_name: ${formatCustomerMemoryValue(lastOrder.recipient?.name)}`,
    `last_recipient_phone: ${formatCustomerMemoryValue(lastOrder.recipient?.phone)}`,
    `last_payer: ${formatCustomerMemoryValue(lastOrder.payer)}`,
    `last_pickup_area: ${formatCustomerMemoryValue(lastOrder.pickup?.area)}`,
    `last_pickup_house: ${formatCustomerMemoryValue(lastOrder.pickup?.house)}`,
    `last_pickup_avenue: ${formatCustomerMemoryValue(lastOrder.pickup?.avenue)}`,
    `last_pickup_notes: ${formatCustomerMemoryValue(lastOrder.pickup?.notes)}`,
    `last_delivery_area: ${formatCustomerMemoryValue(lastOrder.delivery?.area)}`,
    `last_delivery_house: ${formatCustomerMemoryValue(lastOrder.delivery?.house)}`,
    `last_delivery_avenue: ${formatCustomerMemoryValue(lastOrder.delivery?.avenue)}`,
    `last_delivery_notes: ${formatCustomerMemoryValue(lastOrder.delivery?.notes)}`,
    "[/SYSTEM CONTEXT - CUSTOMER MEMORY]",
  ].join("\n");
}

// parseObjectValue, extractTextFromContent, getSessionRecordTimestamp
// moved to ./lib/session-helpers.ts (wave 2b).

// buildSavedAddress moved to ./lib/location-formatting.ts (wave 4).

function getAgentSessionsDir(agentId: string): string {
  return path.join(HOME_DIR, `.openclaw-${OPENCLAW_PROFILE}`, "agents", agentId, "sessions");
}

function sessionMatchesReplyTarget(records: any[], replyTarget: string): boolean {
  const candidates = buildAdminSenderIdCandidates(replyTarget);
  if (candidates.length === 0) {
    return false;
  }
  const markers = candidates.flatMap((candidate) => [
    `"sender_id": "${candidate}"`,
    `"sender": "${candidate}"`,
    `current_customer_whatsapp: ${candidate}`,
    `current_admin_whatsapp: ${candidate}`,
  ]);
  for (const record of records) {
    const message = record?.message;
    if (!message || typeof message !== "object") {
      continue;
    }
    const content = (message as { content?: unknown }).content;
    if (!Array.isArray(content)) {
      continue;
    }
    for (const item of content) {
      const text = item && typeof item === "object" ? asTrimmedString((item as { text?: unknown }).text) : null;
      if (text && markers.some((marker) => text.includes(marker))) {
        return true;
      }
    }
  }
  return false;
}

function extractLatestSuccessfulCreateSimpleOrderFromRecords(records: any[]) {
  const sortedRecords = [...records].sort((a, b) => getSessionRecordTimestamp(a) - getSessionRecordTimestamp(b));
  const toolCalls = new Map<string, Record<string, any> | null>();
  let latestSuccess: { payload: Record<string, any>; arguments: Record<string, any> | null; timestampMs: number } | null = null;
  for (const record of sortedRecords) {
    const message = record?.message;
    if (!message || typeof message !== "object") {
      continue;
    }
    if (message.role === "assistant" && Array.isArray(message.content)) {
      for (const item of message.content) {
        if (item?.type !== "toolCall" || item?.name !== "create_simple_order" || !item?.id) {
          continue;
        }
        toolCalls.set(item.id, parseObjectValue(item.arguments));
      }
    }
    if (message.role !== "toolResult" || message.toolName !== "create_simple_order") {
      continue;
    }
    const payload = parseObjectValue(extractTextFromContent(message.content));
    const order = payload?.order;
    if (!payload || payload.status !== "ok" || !order || (!order.uid && !order.id)) {
      continue;
    }
    latestSuccess = {
      payload,
      arguments: message.toolCallId ? toolCalls.get(message.toolCallId) ?? null : null,
      timestampMs: getSessionRecordTimestamp(record),
    };
  }
  return latestSuccess;
}

async function extractLatestSuccessfulCreateSimpleOrder(agentId: string, replyTarget: string) {
  const sessionsDir = getAgentSessionsDir(agentId);
  let entries: any[];
  try {
    entries = await fs.readdir(sessionsDir, { withFileTypes: true });
  } catch {
    return null;
  }
  const files: Array<{ fullPath: string; mtimeMs: number }> = [];
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".jsonl")) {
      continue;
    }
    const fullPath = path.join(sessionsDir, entry.name);
    const stat = await fs.stat(fullPath);
    files.push({ fullPath, mtimeMs: stat.mtimeMs });
  }
  files.sort((a, b) => b.mtimeMs - a.mtimeMs);
  let latestSuccess: { payload: Record<string, any>; arguments: Record<string, any> | null; timestampMs: number } | null = null;
  for (const file of files.slice(0, MAX_CUSTOMER_PROFILE_SESSION_FILES)) {
    const raw = await fs.readFile(file.fullPath, "utf-8");
    const records = raw
      .split(/\r?\n/)
      .map((line: string) => safeJsonParse(line))
      .filter((record: unknown) => record && typeof record === "object");
    if (!sessionMatchesReplyTarget(records, replyTarget)) {
      continue;
    }
    const candidate = extractLatestSuccessfulCreateSimpleOrderFromRecords(records);
    if (candidate && (!latestSuccess || candidate.timestampMs > latestSuccess.timestampMs)) {
      latestSuccess = candidate;
    }
  }
  return latestSuccess;
}

async function maybeSaveCustomerProfileFromSessions(params: {
  agentId: string;
  replyTarget: string;
  conversationId: string;
}) {
  const { agentId, replyTarget, conversationId } = params;
  const profilePath = getCustomerProfilePath(replyTarget);
  if (!profilePath) {
    return { saved: false, reason: "invalid_reply_target" };
  }
  const latestOrder = await extractLatestSuccessfulCreateSimpleOrder(agentId, replyTarget);
  if (!latestOrder) {
    return { saved: false, reason: "no_successful_order" };
  }
  const args = latestOrder.arguments && typeof latestOrder.arguments === "object" ? latestOrder.arguments : {};
  const payload = latestOrder.payload || {};
  const order = payload.order || {};
  const nextProfile: CustomerProfile = {
    version: 1,
    customer_whatsapp: normalizePhone(replyTarget) || replyTarget,
    updated_at: new Date().toISOString(),
    last_successful_order: {
      conversation_id: String(conversationId),
      order_id: order.id ?? null,
      order_uid: order.uid ?? null,
      selected_delivery_type: asTrimmedString(payload.selected_delivery_type) || null,
      payment_method: asTrimmedString(payload.payment_method) || null,
      shipping_method:
        payload.shipping_method && typeof payload.shipping_method === "object"
          ? {
              id: payload.shipping_method.id ?? null,
              name: asTrimmedString(payload.shipping_method.name) || null,
              type: asTrimmedString(payload.shipping_method.type) || null,
            }
          : null,
      sender: {
        name: asTrimmedString(args.sender_name) || asTrimmedString(order.sender_name) || null,
        phone: normalizePhone(args.sender_phone) || normalizePhone(order.sender_phone) || null,
      },
      recipient: {
        name: asTrimmedString(args.recipient_name) || asTrimmedString(order.recipient_name) || null,
        phone: normalizePhone(args.recipient_phone) || normalizePhone(order.recipient_phone) || null,
      },
      payer: asTrimmedString(args.payer) || asTrimmedString(order.payer) || null,
      pickup: buildSavedAddress(args, "pickup"),
      delivery: buildSavedAddress(args, "delivery"),
      saved_from_turn_at: latestOrder.timestampMs ? new Date(latestOrder.timestampMs).toISOString() : null,
    },
  };
  const existingProfile = await loadCustomerProfile(replyTarget);
  const existingOrder = existingProfile?.last_successful_order;
  const nextOrder = nextProfile.last_successful_order;
  if (isSuspiciousSavedOrder(nextOrder, nextProfile.customer_whatsapp)) {
    return {
      saved: false,
      reason: "suspicious_order",
      orderUid: nextOrder?.order_uid || null,
      profilePath,
    };
  }
  const isAlreadySaved =
    (existingOrder?.order_uid && nextOrder?.order_uid && existingOrder.order_uid === nextOrder.order_uid) ||
    (existingOrder?.order_id !== undefined &&
      existingOrder?.order_id !== null &&
      nextOrder?.order_id !== undefined &&
      nextOrder?.order_id !== null &&
      String(existingOrder.order_id) === String(nextOrder.order_id));
  if (isAlreadySaved) {
    return {
      saved: false,
      reason: "already_saved",
      orderUid: nextOrder?.order_uid || null,
      profilePath,
    };
  }
  await fs.mkdir(RIDERS_CUSTOMER_MEMORY_DIR, { recursive: true });
  await fs.writeFile(profilePath, `${JSON.stringify(nextProfile, null, 2)}\n`, "utf-8");
  return {
    saved: true,
    reason: "saved",
    orderUid: nextOrder?.order_uid || null,
    profilePath,
  };
}

// isTrackingOnlyBehaviorText, filterTrackingOnlyBehaviorRules
// moved to ./lib/session-helpers.ts (wave 2b).

function formatBehaviorPolicyContext(
  raw: unknown,
  options?: {
    currentIntent?: CustomerIntent | null;
  },
): string | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return null;
  }
  const policy = raw as Record<string, unknown>;
  const summary = typeof policy.summary === "string" ? policy.summary.trim() : "";
  const version = Number(policy.version) || 1;
  const lastUpdated = typeof policy.last_updated === "string" ? policy.last_updated.trim() : "";
  const liveInstructions = Array.isArray(policy.live_instructions)
    ? policy.live_instructions
        .map((value: unknown) => (typeof value === "string" ? value.trim() : ""))
        .filter(Boolean)
    : [];
  const replyCorrections = Array.isArray(policy.reply_corrections)
    ? policy.reply_corrections.filter((rule: any) => rule && typeof rule === "object" && rule.enabled !== false)
    : [];
  const flowRules = Array.isArray(policy.flow_rules)
    ? policy.flow_rules.filter((rule: any) => rule && typeof rule === "object" && rule.enabled !== false)
    : [];
  const hasPricingFlowRule = flowRules.some((rule: any) => {
    const title = typeof rule?.title === "string" ? rule.title.trim() : "";
    const situation = typeof rule?.situation === "string" ? rule.situation.trim() : "";
    const guidance = typeof rule?.guidance === "string" ? rule.guidance.trim() : "";
    const requiredSteps = Array.isArray(rule?.required_steps)
      ? rule.required_steps.map((step: unknown) => (typeof step === "string" ? step.trim() : "")).filter(Boolean)
      : [];
    const haystack = [title, situation, guidance, ...requiredSteps].join(" ").toLowerCase();
    const mentionsPricing =
      haystack.includes("price") || haystack.includes("pricing") || haystack.includes("quote");
    const mentionsRoute =
      haystack.includes("pickup") ||
      haystack.includes("dropoff") ||
      haystack.includes("drop-off") ||
      haystack.includes("delivery") ||
      haystack.includes("sedan_normal");
    return mentionsPricing && mentionsRoute;
  });
  const phraseGuards = Array.isArray(policy.phrase_guards)
    ? policy.phrase_guards.filter((rule: any) => rule && typeof rule === "object" && rule.enabled !== false)
    : [];
  const includeTrackingOnly = options?.currentIntent === "tracking";
  const filteredLiveInstructions = includeTrackingOnly
    ? liveInstructions
    : liveInstructions.filter((instruction) => !isTrackingOnlyBehaviorText(instruction));
  const filteredReplyCorrections = filterTrackingOnlyBehaviorRules(replyCorrections, includeTrackingOnly);
  const filteredFlowRules = filterTrackingOnlyBehaviorRules(flowRules, includeTrackingOnly);
  const filteredPhraseGuards = filterTrackingOnlyBehaviorRules(phraseGuards, includeTrackingOnly);

  const lines: string[] = [
    `Live behavior policy v${version}${lastUpdated ? ` (${lastUpdated})` : ""}. This is the highest-priority live override for customer behavior. If any live instruction or enabled behavior rule conflicts with a base workspace rule, follow the live behavior policy and ignore the conflicting base rule.`,
  ];
  const hasFilteredSections =
    filteredLiveInstructions.length > 0 ||
    filteredReplyCorrections.length > 0 ||
    filteredFlowRules.length > 0 ||
    filteredPhraseGuards.length > 0;
  if (!hasFilteredSections) {
    return null;
  }
  if (summary) {
    lines.push(`Summary: ${summary}`);
  }
  if (filteredLiveInstructions.length > 0) {
    lines.push("Live admin instructions:");
    for (const instruction of filteredLiveInstructions) {
      lines.push(`- ${instruction}`);
    }
  }
  if (filteredReplyCorrections.length > 0) {
    lines.push("Reply corrections:");
    for (const rule of filteredReplyCorrections) {
      const situation = typeof rule.situation === "string" ? rule.situation.trim() : "";
      const preferredReply = typeof rule.preferred_reply === "string" ? rule.preferred_reply.trim() : "";
      const wrongReply = typeof rule.wrong_reply === "string" ? rule.wrong_reply.trim() : "";
      const guidance = typeof rule.guidance === "string" ? rule.guidance.trim() : "";
      const languageScope = typeof rule.language_scope === "string" ? rule.language_scope.trim() : "";
      if (!situation || !preferredReply) {
        continue;
      }
      let line = `- When ${situation}, prefer: ${preferredReply}`;
      if (wrongReply) {
        line += ` | avoid: ${wrongReply}`;
      }
      if (guidance) {
        line += ` | guidance: ${guidance}`;
      }
      if (languageScope && languageScope !== "any") {
        line += ` | language: ${languageScope}`;
      }
      lines.push(line);
    }
  }
  if (filteredFlowRules.length > 0) {
    lines.push("Flow rules:");
    for (const rule of filteredFlowRules) {
      const situation = typeof rule.situation === "string" ? rule.situation.trim() : "";
      const requiredSteps = Array.isArray(rule.required_steps)
        ? rule.required_steps.map((step: unknown) => (typeof step === "string" ? step.trim() : "")).filter(Boolean)
        : [];
      const guidance = typeof rule.guidance === "string" ? rule.guidance.trim() : "";
      if (!situation || requiredSteps.length === 0) {
        continue;
      }
      let line = `- For ${situation}, follow: ${requiredSteps.join(" -> ")}`;
      if (guidance) {
        line += ` | guidance: ${guidance}`;
      }
      lines.push(line);
    }
  }
  if (hasPricingFlowRule) {
    lines.push("Critical pricing execution rule:");
    lines.push(
      "- Before quoting any delivery price, you MUST call get_price with both pickup_area and dropoff_area. If either area is missing or ambiguous, clarify it first. Never quote from memory, assumption, or prior examples. Use only the get_price result.",
    );
  }
  if (filteredPhraseGuards.length > 0) {
    lines.push("Phrase guards:");
    for (const rule of filteredPhraseGuards) {
      const kind = typeof rule.kind === "string" ? rule.kind.trim() : "";
      const phrase = typeof rule.phrase === "string" ? rule.phrase.trim() : "";
      const appliesWhen = typeof rule.applies_when === "string" ? rule.applies_when.trim() : "";
      const guidance = typeof rule.guidance === "string" ? rule.guidance.trim() : "";
      if (!phrase || (kind !== "blocked" && kind !== "required")) {
        continue;
      }
      let line = kind === "blocked" ? `- Do not say: ${phrase}` : `- Make sure to include when appropriate: ${phrase}`;
      if (appliesWhen) {
        line += ` | when: ${appliesWhen}`;
      }
      if (guidance) {
        line += ` | guidance: ${guidance}`;
      }
      lines.push(line);
    }
  }
  return lines.length > 1 ? lines.join("\n") : null;
}

async function loadBehaviorPolicyContext(
  account: ResolvedOctopusAccount,
  logger: OpenClawPluginApi["logger"],
  options?: {
    currentIntent?: CustomerIntent | null;
  },
): Promise<string | null> {
  try {
    const raw = await fs.readFile(account.behaviorPolicyPublishedPath, "utf-8");
    if (!raw.trim()) {
      return null;
    }
    return formatBehaviorPolicyContext(JSON.parse(raw) as unknown, options);
  } catch (error) {
    const code =
      error && typeof error === "object" && "code" in error
        ? String((error as { code?: unknown }).code || "")
        : "";
    if (code === "ENOENT") {
      return null;
    }
    logger.warn(
      `[octopus] behavior policy load failed account=${account.accountId} path=${describePath(account.behaviorPolicyPublishedPath)} error=${error instanceof Error ? error.message : String(error)}`,
    );
    return null;
  }
}

// extractConversationId, extractWhatsAppMessages, extractMessageText,
// extractWhatsAppMessageId, extractReplyTarget, extractAudioMessage,
// extractImageMessage, extractLocationMessage moved to ./lib/webhook.ts
// (wave 2a).

// formatLocationAsText, formatLocationPinContext, createPersistedBookingLocation
// moved to ./lib/location-formatting.ts (wave 4).

function buildInboundTurnSignals(params: {
  workflowInputText: string;
}): { workflowInputText: string; languageSignalText: string } {
  const workflowInputText = asTrimmedString(params.workflowInputText) || "";
  return {
    workflowInputText,
    // Only use customer-authored text, captions, or transcripts for language inference.
    languageSignalText: workflowInputText,
  };
}

function resolveControllerFallbackLanguage(
  controllerEntry: PersistedConversationControllerEntry | null,
): "ar" | "en" {
  return controllerEntry?.language || controllerEntry?.explicitLanguage || "en";
}

// =========================================================================
// Google Maps / Apple Maps URL → coordinates extraction
// Handles: full URLs with @lat,lng or q=lat,lng or ll=lat,lng
//          shortened URLs (goo.gl/maps, maps.app.goo.gl) via redirect follow
//          place-name-only URLs via ?q=PlaceName → geo area fuzzy match
// =========================================================================

// MAP_URL_RE, SHORTENED_RE, COORDS_* regex, PLACE_NAME_RE, Q_PARAM_RE,
// MapUrlExtraction type, normalizeMapPlaceName, extractFromMapUrl,
// matchPlaceNameToGeoArea moved to ./lib/maps.ts (wave 2a).

async function resolveMapUrlToLocation(text: string): Promise<OctopusInboundLocationMessage | null> {
  MAP_URL_RE.lastIndex = 0;
  const urls = text.match(MAP_URL_RE);
  if (!urls || urls.length === 0) return null;

  for (const url of urls) {
    // Try direct extraction first (full URLs)
    const direct = extractFromMapUrl(url);

    // If we got coords, return immediately
    if (direct.lat != null && direct.lng != null) {
      return {
        latitude: direct.lat,
        longitude: direct.lng,
        name: direct.placeName,
        address: null,
      };
    }

    // If we got a place name but no coords from the URL itself, try geo area matching
    if (direct.placeName) {
      const areas = await loadAllGeoAreas();
      const matched = matchPlaceNameToGeoArea(direct.placeName, areas);
      if (matched) {
        return {
          latitude: matched.lat,
          longitude: matched.lng,
          name: direct.placeName,
          address: matched.name,
        };
      }
      // Even without a geo area match, return the place name with 0,0 coords
      // so the LLM at least sees the name
      return {
        latitude: 0,
        longitude: 0,
        name: direct.placeName,
        address: null,
      };
    }

    // For shortened URLs, follow the redirect to get the expanded URL
    if (SHORTENED_RE.test(url)) {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);
        const response = await fetch(url, {
          method: "GET",
          redirect: "follow",
          signal: controller.signal,
          headers: { "User-Agent": "Mozilla/5.0" },
        });
        clearTimeout(timeout);
        const expandedUrl = response.url;
        if (expandedUrl && expandedUrl !== url) {
          const expanded = extractFromMapUrl(expandedUrl);

          // Got coords from expanded URL
          if (expanded.lat != null && expanded.lng != null) {
            return {
              latitude: expanded.lat,
              longitude: expanded.lng,
              name: expanded.placeName,
              address: null,
            };
          }

          // Got place name but no coords from expanded URL — match against geo areas
          if (expanded.placeName) {
            const areas = await loadAllGeoAreas();
            const matched = matchPlaceNameToGeoArea(expanded.placeName, areas);
            if (matched) {
              return {
                latitude: matched.lat,
                longitude: matched.lng,
                name: expanded.placeName,
                address: matched.name,
              };
            }
            return {
              latitude: 0,
              longitude: 0,
              name: expanded.placeName,
              address: null,
            };
          }
        }

        // Fallback: check response body for coordinates
        const body = await response.text();
        const bodyExtraction = extractFromMapUrl(body);
        if (bodyExtraction.lat != null && bodyExtraction.lng != null) {
          return {
            latitude: bodyExtraction.lat,
            longitude: bodyExtraction.lng,
            name: bodyExtraction.placeName,
            address: null,
          };
        }
      } catch {
        // Redirect follow failed — fall through
      }
    }
  }
  return null;
}

// getAudioFileExtension, getImageFileExtension moved to ./lib/webhook.ts (wave 2a).

async function readRequestBody(req: any) {
  return await libReadRequestBody(req, nodeBuffer);
}

// writeJson moved to ./lib/webhook.ts (wave 2a).

// buildProviderIssueFallbackReply moved to ./lib/text.ts (wave 2a).

// hashIngressPayload, extractWebhookRequestId, resolveRemoteAddress,
// createIngressId, formatWebhookLogValue, logWebhookEvent moved to
// ./lib/webhook.ts (wave 2a).

function buildIngressLedgerEntry(params: {
  ingressId: string;
  requestId: string | null;
  accountId: string;
  webhookPath: string;
  method: string;
  status: IngressLedgerStatus;
  note?: string | null;
  error?: string | null;
  conversationId?: string | null;
  replyTarget?: string | null;
  messageId?: string | null;
  hasMessageText?: boolean;
  hasAudioMessage?: boolean;
  hasImageMessage?: boolean;
  hasLocationMessage?: boolean;
  rawSize?: number;
  payloadHash?: string | null;
  contentType?: string | null;
  remoteAddress?: string | null;
  payload?: any;
}): PersistedIngressLedgerEntry {
  const now = new Date().toISOString();
  return {
    ingressId: params.ingressId,
    requestId: params.requestId,
    accountId: params.accountId,
    webhookPath: params.webhookPath,
    method: params.method,
    status: params.status,
    receivedAt: now,
    lastUpdatedAt: now,
    processedAt: null,
    processingStartedAt: null,
    attempts: 1,
    replayCount: 0,
    note: params.note || null,
    error: params.error || null,
    conversationId: params.conversationId || null,
    replyTarget: params.replyTarget || null,
    messageId: params.messageId || null,
    hasMessageText: Boolean(params.hasMessageText),
    hasAudioMessage: Boolean(params.hasAudioMessage),
    hasImageMessage: Boolean(params.hasImageMessage),
    hasLocationMessage: Boolean(params.hasLocationMessage),
    rawSize: Math.max(0, Number(params.rawSize || 0)),
    payloadHash: params.payloadHash || null,
    contentType: params.contentType || null,
    remoteAddress: params.remoteAddress || null,
    payload: params.payload ?? null,
  };
}

// isProviderErrorText, sanitizeAgentReplyText, normalizeReplyTextForComparison
// moved to ./lib/text.ts (wave 2a).

function findSessionGuardEntry(
  sessionState: Map<string, any>,
  params: {
    activeSessionKey: string;
    conversationId: string;
    replyTarget: string | null;
  },
): { key: string; session: any | null } {
  const directCandidates = [
    params.activeSessionKey,
    params.conversationId,
    params.replyTarget || "",
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  for (const candidate of directCandidates) {
    const session = sessionState.get(candidate);
    if (session) {
      return { key: candidate, session };
    }
  }
  let bestKey = "";
  let bestSession: any = null;
  const sessionConversationNeedle = `:octopus:direct:${params.conversationId}::prompt=`;
  const sessionConversationSuffix = `:octopus:direct:${params.conversationId}`;
  for (const [key, session] of sessionState.entries()) {
    if (
      key.includes(sessionConversationNeedle) ||
      key.endsWith(sessionConversationSuffix) ||
      (params.replyTarget && key === params.replyTarget)
    ) {
      if (!bestSession || Number(session?.lastToolTs || 0) > Number(bestSession?.lastToolTs || 0)) {
        bestKey = key;
        bestSession = session;
      }
    }
  }
  return { key: bestKey || params.activeSessionKey, session: bestSession };
}

async function findSessionGuardEntryWithPersistence(
  sessionState: Map<string, any> | null | undefined,
  params: {
    activeSessionKey: string;
    conversationId: string;
    replyTarget: string | null;
  },
): Promise<{ key: string; session: any | null }> {
  if (sessionState instanceof Map) {
    const inMemoryEntry = findSessionGuardEntry(sessionState, params);
    if (inMemoryEntry.session) {
      return inMemoryEntry;
    }
  }
  const persistedEntry = await findPersistedGuardSession(params);
  if (persistedEntry.session && sessionState instanceof Map) {
    for (const alias of [
      params.activeSessionKey,
      params.conversationId,
      params.replyTarget || "",
      persistedEntry.key,
    ]) {
      const normalized = String(alias || "").trim();
      if (normalized) {
        sessionState.set(normalized, persistedEntry.session);
      }
    }
  }
  return persistedEntry;
}

// looksLikePriceOnlyReply, containsArabic, containsLatin,
// buildDeterministicGreetingReply, buildDeterministicPassengerTransportReply,
// buildDeterministicLanguageSwitchReply, buildDeterministicServiceOverviewReply
// moved to ./lib/text.ts (wave 2a).

// RouteQuoteOption, StoredQuotedRoute, SameRouteQuoteFollowupAction moved to
// ./lib/quoted-options.ts (wave 4).

// InterpretedCustomerTurnAction, InterpretedBookingFields, and
// InterpretedCustomerTurn moved to ./lib/interpreter-types.ts (wave 5).

const RESPONDER_FIRST_FLAG = (() => {
  const raw = String(env.RIDERS_RESPONDER_FIRST || "").trim().toLowerCase();
  return raw === "1" || raw === "true" || raw === "yes" || raw === "on";
})();
// ONE-BRAIN flag: when ON, the channel skips the turn-interpreter LLM,
// skips the deterministic greeting shortcut, skips the deterministic
// order-summary builder, and drains responder state ops through a minimal
// patch-apply path (no stage/step/hint threading). The agent (single LLM)
// owns every customer-facing message; deterministic guards only check prices
// at outbound and order preconditions at create time.
const ONE_BRAIN_FLAG = (() => {
  const raw = String(env.RIDERS_ONE_BRAIN || "").trim().toLowerCase();
  return raw === "1" || raw === "true" || raw === "yes" || raw === "on";
})();
// Optional per-number allowlist for ONE-BRAIN. When set, ONE-BRAIN only
// applies to the listed WhatsApp numbers. Leave empty to apply globally
// once the flag is on.
const ONE_BRAIN_ALLOWLIST: Set<string> = new Set(
  String(env.RIDERS_ONE_BRAIN_ALLOWLIST || "")
    .split(",")
    .map((value) => value.replace(/\s+/g, ""))
    .filter(Boolean),
);
function isOneBrainConversation(replyTarget: string | null | undefined): boolean {
  if (!ONE_BRAIN_FLAG) return false;
  if (ONE_BRAIN_ALLOWLIST.size === 0) return true;
  const normalized = String(replyTarget || "").replace(/\s+/g, "");
  return Boolean(normalized) && ONE_BRAIN_ALLOWLIST.has(normalized);
}
const TURN_INTERPRETER_MODEL = String(env.RIDERS_TURN_INTERPRETER_MODEL || "gpt-5.4").trim();
const TURN_INTERPRETER_TIMEOUT_MS = Number.parseInt(env.RIDERS_TURN_INTERPRETER_TIMEOUT_MS || "12000", 10);
const TURN_INTERPRETER_DELIVERY_TYPES = [
  "sedan_normal",
  "sedan_fast",
  "van_normal",
  "van_fast",
  "cooled_van_normal",
  "cooled_van_fast",
  "helper_standard",
] as const;
const TURN_INTERPRETER_ACTIONS = [
  "greeting",
  "language_switch",
  "service_overview",
  "pricing_request",
  "same_route_quote_option",
  "same_route_show_other_options",
  "start_booking",
  "booking_step_input",
  "correct_booking_field",
  "confirm_summary",
  "cancel_booking",
  "tracking_request",
  "tracking_missing_id",
  "passenger_transport_request",
  "handoff",
  "clarify",
  "general_support",
] as const;

const TURN_INTERPRETER_RESPONSE_FORMAT = {
  type: "json_schema",
  json_schema: {
    name: "riders_turn_interpretation",
    strict: true,
    schema: {
      type: "object",
      additionalProperties: false,
      properties: {
        action: { type: "string", enum: [...TURN_INTERPRETER_ACTIONS] },
        selected_delivery_type: {
          anyOf: [
            { type: "string", enum: [...TURN_INTERPRETER_DELIVERY_TYPES] },
            { type: "null" },
          ],
        },
        should_use_active_quote: { type: "boolean" },
        route_changed: { type: "boolean" },
        order_id: {
          anyOf: [
            { type: "string" },
            { type: "null" },
          ],
        },
        requested_language: {
          anyOf: [
            { type: "string", enum: ["ar", "en"] },
            { type: "null" },
          ],
        },
        confidence: { type: "string", enum: ["low", "medium", "high"] },
        reason: { type: "string" },
        booking_fields: {
          anyOf: [
            {
              type: "object",
              additionalProperties: false,
              properties: {
                sender_name: { anyOf: [{ type: "string" }, { type: "null" }] },
                sender_phone: { anyOf: [{ type: "string" }, { type: "null" }] },
                phone_decision: { anyOf: [{ type: "string", enum: ["use_whatsapp", "different", "none"] }, { type: "null" }] },
                recipient_name: { anyOf: [{ type: "string" }, { type: "null" }] },
                recipient_phone: { anyOf: [{ type: "string" }, { type: "null" }] },
                address_block: { anyOf: [{ type: "string" }, { type: "null" }] },
                address_street: { anyOf: [{ type: "string" }, { type: "null" }] },
                address_house: { anyOf: [{ type: "string" }, { type: "null" }] },
              },
              required: [
                "sender_name",
                "sender_phone",
                "phone_decision",
                "recipient_name",
                "recipient_phone",
                "address_block",
                "address_street",
                "address_house",
              ],
            },
            { type: "null" },
          ],
        },
        location_role_hint: {
          anyOf: [
            { type: "string", enum: ["pickup", "delivery"] },
            { type: "null" },
          ],
        },
      },
      required: [
        "action",
        "selected_delivery_type",
        "should_use_active_quote",
        "route_changed",
        "order_id",
        "requested_language",
        "confidence",
        "reason",
        "booking_fields",
        "location_role_hint",
      ],
    },
  },
} as const;

// BOOKABLE_QUOTED_OPTION_TYPES, DELIVERY_TYPE_ALIASES, SAME_ROUTE_* markers, and
// all quoted-option helpers (isBookableQuotedOptionType, getQuotedRouteDefaultOption,
// getQuotedRouteOption, getActiveSelectedQuotedOption, formatQuotedOptionLabel,
// formatQuotedOptionPrice, applySelectedQuotedOptionToController,
// syncControllerSelectionFromQuotedRoute, buildQuotedOptionAliases,
// scoreQuotedOptionMatch, resolveSameRouteQuoteFollowupAction,
// buildDeterministicSelectedQuotedOptionReply, buildDeterministicOtherQuotedOptionsReply)
// moved to ./lib/quoted-options.ts (wave 4).

function buildTurnInterpreterStateSummary(params: {
  controllerEntry: PersistedConversationControllerEntry | null;
  preferredReplyLanguage: "ar" | "en";
  explicitLanguageRequest: "ar" | "en" | null;
  route: StoredQuotedRoute | null | undefined;
  nearestAreaName: string | null;
  hasLocationMessage: boolean;
}): string {
  const lines = [
    "[TRUSTED STATE]",
    `preferred_reply_language: ${params.preferredReplyLanguage}`,
    `explicit_language_request: ${params.explicitLanguageRequest || "-"}`,
    `conversation_stage: ${params.controllerEntry?.stage || "idle"}`,
    `booking_step: ${params.controllerEntry?.bookingStep || "none"}`,
    `active_quote_route_key: ${params.controllerEntry?.quoteRouteKey || "-"}`,
    `active_quote_pickup_en: ${params.controllerEntry?.quotePickupAreaNameEn || "-"}`,
    `active_quote_dropoff_en: ${params.controllerEntry?.quoteDropoffAreaNameEn || "-"}`,
    `selected_quote_option_type: ${params.controllerEntry?.selectedQuoteOptionType || "-"}`,
    `selected_quote_option_label_en: ${params.controllerEntry?.selectedQuoteOptionLabelEn || "-"}`,
    `selected_quote_option_price: ${params.controllerEntry?.selectedQuoteOptionPrice ?? "-"}`,
    `selected_delivery_type: ${params.controllerEntry?.selectedDeliveryType || "-"}`,
    `selected_delivery_price: ${params.controllerEntry?.quotedPrice ?? "-"}`,
    `quote_presented_to_customer: ${params.controllerEntry?.quotePresentedToCustomer === false ? "no" : params.controllerEntry?.stage === "quoted" ? "yes" : "-"}`,
    `nearest_area_name: ${params.nearestAreaName || "-"}`,
    `has_location_message: ${params.hasLocationMessage ? "yes" : "no"}`,
    `pending_shared_location: ${formatPersistedBookingLocationLabel(params.controllerEntry?.bookingDraft.pendingLocation) || "-"}`,
    `confirmed_pickup_location: ${formatPersistedBookingLocationLabel(params.controllerEntry?.bookingDraft.pickupLocation) || "-"}`,
    `confirmed_delivery_location: ${formatPersistedBookingLocationLabel(params.controllerEntry?.bookingDraft.deliveryLocation) || "-"}`,
  ];
  if (params.route) {
    lines.push(`quoted_route_pickup_en: ${params.route.pickupAreaNameEn}`);
    lines.push(`quoted_route_dropoff_en: ${params.route.dropoffAreaNameEn}`);
    lines.push("quoted_options:");
    for (const option of params.route.optionCatalog.filter((entry) => entry.quoted_price != null)) {
      lines.push(
        `- ${option.delivery_type} | ${option.label_en} | ${formatQuotedOptionPrice(option)} | direct_chat=${option.direct_chat_booking_status || "-"}`,
      );
    }
  }
  lines.push("[/TRUSTED STATE]");
  return lines.join("\n");
}

function normalizeInterpretedCustomerTurn(value: unknown): InterpretedCustomerTurn | null {
  const parsed = parseObjectValue(value);
  const action = asTrimmedString(parsed?.action);
  const confidence = asTrimmedString(parsed?.confidence);
  if (
    !action ||
    !TURN_INTERPRETER_ACTIONS.includes(action as typeof TURN_INTERPRETER_ACTIONS[number]) ||
    !confidence ||
    !["low", "medium", "high"].includes(confidence)
  ) {
    return null;
  }
  const selectedDeliveryType = asTrimmedString(parsed?.selected_delivery_type);
  const requestedLanguage = asTrimmedString(parsed?.requested_language);
  return {
    action: action as InterpretedCustomerTurnAction,
    selected_delivery_type:
      selectedDeliveryType && TURN_INTERPRETER_DELIVERY_TYPES.includes(selectedDeliveryType as typeof TURN_INTERPRETER_DELIVERY_TYPES[number])
        ? selectedDeliveryType
        : null,
    should_use_active_quote: Boolean(parsed?.should_use_active_quote),
    route_changed: Boolean(parsed?.route_changed),
    order_id: asTrimmedString(parsed?.order_id) || null,
    requested_language: requestedLanguage === "ar" || requestedLanguage === "en" ? requestedLanguage : null,
    confidence: confidence as InterpretedCustomerTurn["confidence"],
    reason: asTrimmedString(parsed?.reason) || "",
    booking_fields: normalizeBookingFields(parsed?.booking_fields),
    location_role_hint: (() => {
      const hint = asTrimmedString(parsed?.location_role_hint);
      return hint === "pickup" || hint === "delivery" ? hint : null;
    })(),
  };
}

function normalizeBookingFields(value: unknown): InterpretedBookingFields | null {
  if (!value || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  const senderName = typeof v.sender_name === "string" ? v.sender_name.trim() || null : null;
  const senderPhone = typeof v.sender_phone === "string" ? v.sender_phone.replace(/\D/g, "").trim() || null : null;
  const rawPd = typeof v.phone_decision === "string" ? v.phone_decision.trim() : null;
  const phoneDecision = rawPd === "use_whatsapp" || rawPd === "different" || rawPd === "none" ? rawPd : null;
  const recipientName = typeof v.recipient_name === "string" ? v.recipient_name.trim() || null : null;
  const recipientPhone = typeof v.recipient_phone === "string" ? v.recipient_phone.replace(/\D/g, "").trim() || null : null;
  const addressBlock = typeof v.address_block === "string" ? v.address_block.trim() || null : null;
  const addressStreet = typeof v.address_street === "string" ? v.address_street.trim() || null : null;
  const addressHouse = typeof v.address_house === "string" ? v.address_house.trim() || null : null;
  if (!senderName && !senderPhone && !phoneDecision && !recipientName && !recipientPhone && !addressBlock && !addressStreet && !addressHouse) {
    return null;
  }
  return { sender_name: senderName, sender_phone: senderPhone, phone_decision: phoneDecision, recipient_name: recipientName, recipient_phone: recipientPhone, address_block: addressBlock, address_street: addressStreet, address_house: addressHouse };
}

async function interpretCustomerTurnWithOpenAi(params: {
  logger: Pick<Console, "info" | "warn" | "error"> | OpenClawPluginApi["logger"];
  visibleText: string;
  rawBody: string;
  preferredReplyLanguage: "ar" | "en";
  explicitLanguageRequest: "ar" | "en" | null;
  controllerEntry: PersistedConversationControllerEntry | null;
  route: StoredQuotedRoute | null | undefined;
  nearestAreaName: string | null;
  hasLocationMessage: boolean;
}): Promise<InterpretedCustomerTurn | null> {
  const apiKey = env.OPENAI_API_KEY?.trim();
  if (!apiKey || !params.rawBody.trim()) {
    return null;
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TURN_INTERPRETER_TIMEOUT_MS);
  try {
    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: TURN_INTERPRETER_MODEL,
        temperature: 0,
        response_format: TURN_INTERPRETER_RESPONSE_FORMAT,
        messages: [
          {
            role: "system",
            content: [
              "You are a strict customer-turn interpreter for Riders delivery support.",
              buildTurnInterpreterStateSummary({
                controllerEntry: params.controllerEntry,
                preferredReplyLanguage: params.preferredReplyLanguage,
                explicitLanguageRequest: params.explicitLanguageRequest,
                route: params.route,
                nearestAreaName: params.nearestAreaName,
                hasLocationMessage: params.hasLocationMessage,
              }),
              "Use the trusted state as the source of truth. Do not answer the user. Do not roleplay.",
              "If conversation_stage=quoted and quote_presented_to_customer=yes and the route did not change, classify precisely: (a) ANY message that indicates the customer accepts/chooses and wants to proceed — whether bare ('ok', 'yes', 'yep', 'sure', 'yalla', 'proceed', 'go ahead', 'احجز', 'كمل', 'تمام'), acceptance + option name ('ok lets go with the express sedan', 'proceed with the box van', 'نعم خذ الفان', 'go with helper'), or any other phrasing that commits to booking — use action=start_booking with should_use_active_quote=true, and if they named an option, populate selected_delivery_type. The presence of 'ok/yes/lets/go with/proceed/احجز/تمام/كمل' combined with a route/option in context is acceptance, NOT inquiry. (b) A pure inquiry about a different option with NO acceptance verb ('what about express sedan?', 'how much for the box van?', 'is refrigerated available?', 'كم الفان؟') means action=same_route_quote_option with should_use_active_quote=true and selected_delivery_type populated. (c) A request to see all options ('what options are available?', 'show me all cars', 'شنو الخيارات') means action=same_route_show_other_options. Do NOT use confirm_summary when conversation_stage=quoted. If conversation_stage=quoted but quote_presented_to_customer=no, the customer has not yet seen the price — short confirmations likely answer a pending clarification (e.g. area disambiguation). In that case use action=pricing_request with route_changed=false so the price is shown.",
              "If conversation_stage=awaiting_confirmation or booking_step=awaiting_summary_confirmation, confirmation messages mean action=confirm_summary.",
              "If conversation_stage=collecting_booking_details, sender/recipient/phone/address details mean action=booking_step_input unless the customer clearly changes topic. When action=booking_step_input, populate booking_fields: extract sender_name (just the person's name, no extra text), sender_phone (digits only if given), phone_decision (use_whatsapp if confirming the WhatsApp number, different if rejecting it or asking to use another number, none otherwise), recipient_name, recipient_phone, address_block, address_street, address_house. Use booking_step from the trusted state to map short unlabeled replies to the next missing field: if sender name is already known and the customer sends digits, that is sender_phone; if recipient name is already known and the customer sends digits, that is recipient_phone; if booking_step is pickup_address or delivery_address and the customer sends one unlabeled value like '2', map it to the first missing address field in order block, street, house. If has_location_message=yes during pickup_address or delivery_address, still use action=booking_step_input even if booking_fields stay null because the location pin/map link itself may be the address evidence. Only fill fields the customer explicitly provided; leave the rest null. For all other actions set booking_fields to null.",
              "If the customer explicitly corrects a previously submitted booking field (e.g. 'actually my name is Ahmed', 'wrong number, use 99887766', 'change the recipient name to X'), use action=correct_booking_field and populate the corrected value(s) in booking_fields regardless of the current booking_step. This allows overwriting past fields without restarting.",
              "If conversation_stage is collecting_booking_details, summary_shown, or awaiting_confirmation and the customer clearly wants to cancel, abandon, or start over (e.g. 'cancel', 'never mind', 'nvm', 'forget it', 'start over', 'لا خلاص', 'الغي', 'ما ابي'), use action=cancel_booking.",
              "If pending_shared_location is set (not '-') and the customer indicates which role the location should serve (pickup or delivery), set location_role_hint to 'pickup' or 'delivery'. This covers natural phrasing like 'this is where they pick it up from', 'for the sender', 'delivery side', 'هذا مكان الاستلام', 'مكان المرسل', etc. If pending_shared_location is '-' or the customer is not answering a location-role question, set location_role_hint to null.",
              "Broad service questions without a specific route mean action=service_overview. If the customer wants to move a person rather than a package (e.g. ودني المطار ,وصلني ,خذني, take me, drop me, taxi), use action=passenger_transport_request even if they only mention a destination. Do not use pricing_request or clarify for person-transport. Human-help, complaint, or refund requests mean action=handoff.",
              "If the customer clearly asks for a new route price or changes pickup/dropoff for a package or delivery, use action=pricing_request and set route_changed=true.",
              "Tracking with a valid ORDER- number means action=tracking_request and set order_id. Tracking without a valid ORDER- number means action=tracking_missing_id.",
              "Pure greetings mean action=greeting. Explicit language changes mean action=language_switch.",
              "Set should_use_active_quote=true only when the customer is still on the same active quoted route; otherwise false.",
              "If the latest message is still ambiguous after using the trusted state, use action=clarify. Return only the schema.",
            ].join("\n"),
          },
          {
            role: "user",
            content: params.rawBody,
          },
        ],
      }),
    });
    if (!response.ok) {
      const raw = await response.text();
      params.logger.warn(`[turn-interpreter] openai request failed status=${response.status} body=${raw.slice(0, 300)}`);
      return null;
    }
    const payload = (await response.json()) as any;
    const rawContent = payload?.choices?.[0]?.message?.content;
    const refusal = asTrimmedString(payload?.choices?.[0]?.message?.refusal);
    if (refusal) {
      params.logger.warn(`[turn-interpreter] model refusal: ${refusal}`);
      return null;
    }
    const contentText = Array.isArray(rawContent)
      ? rawContent
        .map((item: any) => asTrimmedString(item?.text) || asTrimmedString(item?.content) || "")
        .filter(Boolean)
        .join("\n")
      : asTrimmedString(rawContent);
    const interpreted = normalizeInterpretedCustomerTurn(contentText ? safeJsonParse(contentText) : null);
    if (!interpreted) {
      params.logger.warn(`[turn-interpreter] invalid structured output: ${String(contentText || "").slice(0, 300)}`);
      return null;
    }
    return interpreted;
  } catch (error) {
    params.logger.warn(
      `[turn-interpreter] structured interpretation failed: ${error instanceof Error ? error.message : String(error)}`,
    );
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

function mapInterpretedActionToCustomerIntent(action: InterpretedCustomerTurn | null): CustomerIntent | null {
  if (!action) return null;
  switch (action.action) {
    case "greeting":
      return "greeting";
    case "service_overview":
      return "service_inquiry";
    case "pricing_request":
    case "same_route_quote_option":
    case "same_route_show_other_options":
      return "pricing_request";
    case "start_booking":
    case "booking_step_input":
    case "correct_booking_field":
    case "confirm_summary":
    case "cancel_booking":
      return "booking_followup";
    case "tracking_request":
    case "tracking_missing_id":
      return "tracking";
    case "language_switch":
      return "language_switch";
    case "passenger_transport_request":
      return "passenger_transport_request";
    case "handoff":
    case "clarify":
    case "general_support":
    default:
      return "general_support";
  }
}

function resolveSameRouteQuoteActionFromInterpreter(params: {
  interpretedTurn: InterpretedCustomerTurn | null;
  route: StoredQuotedRoute | null | undefined;
  controllerEntry: PersistedConversationControllerEntry | null;
}): SameRouteQuoteFollowupAction {
  if (
    !params.interpretedTurn ||
    !params.route ||
    !params.controllerEntry ||
    !hasActiveQuotedBookingAuthority(params.controllerEntry)
  ) {
    return null;
  }
  if (params.interpretedTurn.action === "same_route_show_other_options") {
    return { kind: "show_other_options" };
  }
  const wantsQuotedOption =
    (
      params.interpretedTurn.action === "same_route_quote_option" ||
      (
        params.interpretedTurn.action === "start_booking" &&
        params.interpretedTurn.should_use_active_quote
      )
    ) &&
    !!params.interpretedTurn.selected_delivery_type;
  if (!wantsQuotedOption || !params.interpretedTurn.selected_delivery_type) {
    return null;
  }
  const option = getQuotedRouteOption(params.route, params.interpretedTurn.selected_delivery_type);
  if (!option) {
    return null;
  }
  const selectedOption = getActiveSelectedQuotedOption(params.route, params.controllerEntry);
  if (selectedOption?.delivery_type === option.delivery_type) {
    return { kind: "confirm_selected_option", option };
  }
  return { kind: "switch_option", option };
}

// buildQuotedRouteContextLines moved to ./lib/quoted-options.ts (wave 5).

function buildDeterministicLocationClarificationReply(params: {
  language: "ar" | "en";
  nearestAreaName: string | null;
  locationMessage: OctopusInboundLocationMessage | null;
}): string {
  const areaLabel =
    params.nearestAreaName ||
    params.locationMessage?.name ||
    params.locationMessage?.address ||
    (params.language === "ar" ? "الموقع المرسل" : "the shared location");
  return params.language === "ar"
    ? `تمام، المنطقة ${areaLabel}. تبون نعتبرها موقع الاستلام ولا التسليم؟`
    : `Understood. The area is ${areaLabel}. Should I treat this as the pickup location or the delivery location?`;
}

function shouldUseDeterministicLocationClarification(params: {
  controllerEntry: PersistedConversationControllerEntry | null;
  locationMessage: OctopusInboundLocationMessage | null;
}): boolean {
  if (!params.locationMessage) {
    return false;
  }
  const stage = String(params.controllerEntry?.stage || "idle");
  const bookingStep = String(params.controllerEntry?.bookingStep || "none");
  if (
    stage === "collecting_booking_details" ||
    stage === "summary_shown" ||
    stage === "awaiting_confirmation" ||
    stage === "order_submitted"
  ) {
    return false;
  }
  return bookingStep === "none";
}

// hasStructuredBookingLocation, hasCompleteTextAddress, hasSatisfiedBookingAddress
// moved to ./lib/booking-flow.ts (wave 4).

function getStandaloneLocationAutoAssignmentRole(
  controllerEntry: PersistedConversationControllerEntry | null,
): "pickup" | "delivery" | null {
  if (!controllerEntry) {
    return null;
  }
  if (
    controllerEntry.stage === "collecting_booking_details" ||
    controllerEntry.stage === "summary_shown" ||
    controllerEntry.stage === "awaiting_confirmation" ||
    controllerEntry.stage === "order_submitted" ||
    controllerEntry.bookingStep !== "none"
  ) {
    return null;
  }
  const hasPickup = hasSatisfiedBookingAddress(controllerEntry.bookingDraft, "pickup");
  const hasDelivery = hasSatisfiedBookingAddress(controllerEntry.bookingDraft, "delivery");
  if (hasPickup && !hasDelivery) {
    return "delivery";
  }
  if (!hasPickup && hasDelivery) {
    return "pickup";
  }
  return null;
}

function applyStandaloneLocationAssignment(params: {
  controllerEntry: PersistedConversationControllerEntry;
  location: PersistedBookingLocation;
  role: "pickup" | "delivery";
}): PersistedConversationControllerEntry {
  const nextEntry: PersistedConversationControllerEntry = {
    ...params.controllerEntry,
    bookingDraft: {
      ...params.controllerEntry.bookingDraft,
      pendingLocation: null,
    },
  };
  if (params.role === "pickup") {
    nextEntry.bookingDraft.pickupLocation = params.location;
    nextEntry.bookingDraft.pickupBlock = null;
    nextEntry.bookingDraft.pickupStreet = null;
    nextEntry.bookingDraft.pickupHouse = null;
  } else {
    nextEntry.bookingDraft.deliveryLocation = params.location;
    nextEntry.bookingDraft.deliveryBlock = null;
    nextEntry.bookingDraft.deliveryStreet = null;
    nextEntry.bookingDraft.deliveryHouse = null;
  }
  return nextEntry;
}

function getDeclaredLocationRole(params: {
  visibleText: string;
  interpretedTurn: InterpretedCustomerTurn | null;
}): "pickup" | "delivery" | null {
  return getLocationRoleSelection(params.visibleText) || params.interpretedTurn?.location_role_hint || null;
}

function applyVolunteeredFutureBookingFields(params: {
  controllerEntry: PersistedConversationControllerEntry;
  bookingFields: InterpretedBookingFields | null | undefined;
}): PersistedConversationControllerEntry {
  if (!params.bookingFields) {
    return params.controllerEntry;
  }
  const nextEntry: PersistedConversationControllerEntry = {
    ...params.controllerEntry,
    bookingDraft: { ...params.controllerEntry.bookingDraft },
  };
  if (
    params.controllerEntry.bookingStep === "sender" &&
    !nextEntry.bookingDraft.recipientName &&
    params.bookingFields.recipient_name
  ) {
    nextEntry.bookingDraft.recipientName = params.bookingFields.recipient_name;
  }
  if (
    params.controllerEntry.bookingStep === "sender" &&
    !nextEntry.bookingDraft.recipientPhone &&
    params.bookingFields.recipient_phone
  ) {
    nextEntry.bookingDraft.recipientPhone = params.bookingFields.recipient_phone;
  }
  return nextEntry;
}

function clearQuotedRouteContext(
  entry: PersistedConversationControllerEntry,
): PersistedConversationControllerEntry {
  return {
    ...entry,
    stage: "idle",
    bookingStep: "none",
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
    quotePresentedToCustomer: false,
  };
}

function clearAutomatedConversationContext(
  entry: PersistedConversationControllerEntry,
): PersistedConversationControllerEntry {
  return {
    ...clearQuotedRouteContext(entry),
    stage: "idle",
    bookingStep: "none",
    bookingDraft: createEmptyBookingDraft(),
    pendingReplyText: null,
    submittedOrderUid: null,
  };
}

function resolveAddressCorrectionRole(params: {
  controllerEntry: PersistedConversationControllerEntry;
  visibleText: string;
}): "pickup" | "delivery" | null {
  const explicitRole = getLocationRoleSelection(params.visibleText);
  if (explicitRole) {
    return explicitRole;
  }
  if (params.controllerEntry.bookingStep === "pickup_address") {
    return "pickup";
  }
  if (params.controllerEntry.bookingStep === "delivery_address") {
    return "delivery";
  }
  const pickupSatisfied = hasSatisfiedBookingAddress(params.controllerEntry.bookingDraft, "pickup");
  const deliverySatisfied = hasSatisfiedBookingAddress(params.controllerEntry.bookingDraft, "delivery");
  if (pickupSatisfied && !deliverySatisfied) {
    return "delivery";
  }
  if (!pickupSatisfied && deliverySatisfied) {
    return "pickup";
  }
  return null;
}

type BookingFieldCorrectionStatus = "applied" | "ambiguous_address_role" | "no_op";

function applyBookingFieldCorrection(params: {
  controllerEntry: PersistedConversationControllerEntry;
  visibleText: string;
  replyTarget: string | null;
  bookingFields: InterpretedBookingFields;
}): { entry: PersistedConversationControllerEntry; status: BookingFieldCorrectionStatus } {
  const { controllerEntry, visibleText, replyTarget, bookingFields } = params;
  const correctedDraft = { ...controllerEntry.bookingDraft };
  let appliedCount = 0;
  let ambiguousAddressDropped = false;
  if (bookingFields.sender_name) {
    correctedDraft.senderName = bookingFields.sender_name;
    appliedCount += 1;
  }
  if (bookingFields.sender_phone) {
    correctedDraft.senderPhone = bookingFields.sender_phone;
    correctedDraft.senderPhoneRejected = false;
    appliedCount += 1;
  }
  if (bookingFields.phone_decision === "use_whatsapp" && replyTarget) {
    correctedDraft.senderPhone = pickCurrentWhatsappPhone(replyTarget);
    correctedDraft.senderPhoneRejected = false;
    appliedCount += 1;
  } else if (bookingFields.phone_decision === "different") {
    correctedDraft.senderPhone = null;
    correctedDraft.senderPhoneRejected = true;
    appliedCount += 1;
  }
  if (bookingFields.recipient_name) {
    correctedDraft.recipientName = bookingFields.recipient_name;
    appliedCount += 1;
  }
  if (bookingFields.recipient_phone) {
    correctedDraft.recipientPhone = bookingFields.recipient_phone;
    appliedCount += 1;
  }
  if (bookingFields.address_block || bookingFields.address_street || bookingFields.address_house) {
    const correctionRole = resolveAddressCorrectionRole({
      controllerEntry,
      visibleText,
    });
    if (correctionRole === "pickup") {
      if (bookingFields.address_block) correctedDraft.pickupBlock = bookingFields.address_block;
      if (bookingFields.address_street) correctedDraft.pickupStreet = bookingFields.address_street;
      if (bookingFields.address_house) correctedDraft.pickupHouse = bookingFields.address_house;
      appliedCount += 1;
    } else if (correctionRole === "delivery") {
      if (bookingFields.address_block) correctedDraft.deliveryBlock = bookingFields.address_block;
      if (bookingFields.address_street) correctedDraft.deliveryStreet = bookingFields.address_street;
      if (bookingFields.address_house) correctedDraft.deliveryHouse = bookingFields.address_house;
      appliedCount += 1;
    } else {
      ambiguousAddressDropped = true;
    }
  }
  if (appliedCount === 0) {
    const status: BookingFieldCorrectionStatus = ambiguousAddressDropped
      ? "ambiguous_address_role"
      : "no_op";
    return { entry: controllerEntry, status };
  }
  const nextStep = resolveNextBookingStepFromDraft(correctedDraft);
  const nextEntry: PersistedConversationControllerEntry =
    nextStep === "summary_pending"
      ? {
          ...controllerEntry,
          bookingDraft: correctedDraft,
          stage: "awaiting_confirmation",
          bookingStep: "awaiting_summary_confirmation",
        }
      : {
          ...controllerEntry,
          bookingDraft: correctedDraft,
          stage: "collecting_booking_details",
          bookingStep: nextStep,
        };
  return { entry: nextEntry, status: "applied" };
}

/**
 * Responder-first path only.
 * Drains state-operation proposals pushed by responder tools during the turn,
 * validates each, and applies accepted ones to the controller entry.
 * Returns the updated controller entry plus a summary for the turn-trace log.
 */
function applyResponderStateOps(params: {
  controllerEntry: PersistedConversationControllerEntry | null;
  visibleText: string;
  replyTarget: string | null;
  ops: ResponderStateOp[];
}): {
  controllerEntry: PersistedConversationControllerEntry | null;
  applied: Array<{ op: string; outcome: string }>;
  summaryReady: boolean;
  cancelled: boolean;
  handoffRequested: boolean;
  confirmSummary: boolean;
  corrections: { applied: number; ambiguous: number; noop: number; rejected: number };
  validationRejections: Array<{ field: string; reason: string; received: string }>;
  draftSanityProblems: DraftSanityProblem[];
} {
  const { controllerEntry, visibleText, replyTarget, ops } = params;
  const applied: Array<{ op: string; outcome: string }> = [];
  let entry = controllerEntry;
  let summaryReady = false;
  let cancelled = false;
  let handoffRequested = false;
  let confirmSummary = false;
  const corrections = { applied: 0, ambiguous: 0, noop: 0, rejected: 0 };
  const validationRejections: Array<{ field: string; reason: string; received: string }> = [];
  let draftSanityProblems: DraftSanityProblem[] = [];

  for (const op of ops) {
    if (op.op === "apply_booking_field") {
      if (!entry) {
        applied.push({ op: op.op, outcome: "no_controller_entry" });
        continue;
      }
      // Defense-in-depth: re-validate even though the tool already validated.
      const validation = validateApplyBookingFieldOp(op as ResponderBookingFieldOp);
      if (validation.errors.length > 0) {
        for (const err of validation.errors) {
          validationRejections.push({ field: err.field, reason: err.reason, received: err.received });
        }
        corrections.rejected += 1;
        try {
          console.warn(
            `[responder-op] apply_booking_field drain_validation_errors errors=${JSON.stringify(validation.errors)}`,
          );
        } catch {}
      }
      const cleanedOp = validation.cleaned;
      const bookingFields: InterpretedBookingFields = {
        sender_name: cleanedOp.sender_name ?? null,
        sender_phone: cleanedOp.sender_phone ?? null,
        phone_decision: cleanedOp.phone_decision ?? null,
        recipient_name: cleanedOp.recipient_name ?? null,
        recipient_phone: cleanedOp.recipient_phone ?? null,
        address_block: cleanedOp.address_block ?? null,
        address_street: cleanedOp.address_street ?? null,
        address_house: cleanedOp.address_house ?? null,
      };
      const hasAnyField = Boolean(
        bookingFields.sender_name ||
          bookingFields.sender_phone ||
          bookingFields.phone_decision ||
          bookingFields.recipient_name ||
          bookingFields.recipient_phone ||
          bookingFields.address_block ||
          bookingFields.address_street ||
          bookingFields.address_house,
      );
      if (!hasAnyField) {
        applied.push({ op: op.op, outcome: validation.errors.length > 0 ? "rejected_all_invalid" : "empty" });
        if (validation.errors.length === 0) corrections.noop += 1;
        continue;
      }
      const effectiveText =
        cleanedOp.address_role === "pickup"
          ? `pickup ${visibleText}`
          : cleanedOp.address_role === "delivery"
            ? `delivery ${visibleText}`
            : visibleText;
      const result = applyBookingFieldCorrection({
        controllerEntry: entry,
        visibleText: effectiveText,
        replyTarget,
        bookingFields,
      });
      entry = result.entry;
      if (result.status === "applied") {
        corrections.applied += 1;
        applied.push({ op: op.op, outcome: validation.errors.length > 0 ? "applied_partial" : "applied" });
        if (
          entry?.bookingStep === "summary_pending" ||
          entry?.bookingStep === "awaiting_summary_confirmation" ||
          entry?.stage === "awaiting_confirmation"
        ) {
          summaryReady = true;
        }
      } else if (result.status === "ambiguous_address_role") {
        corrections.ambiguous += 1;
        applied.push({ op: op.op, outcome: "ambiguous_address_role" });
      } else {
        corrections.noop += 1;
        applied.push({ op: op.op, outcome: "no_op" });
      }
      continue;
    }
    if (op.op === "confirm_summary") {
      if (
        entry?.stage === "awaiting_confirmation" ||
        entry?.bookingStep === "awaiting_summary_confirmation"
      ) {
        // Pre-confirm draft sanity check. If the draft has malformed fields,
        // refuse to flip confirmSummary and return structured problems to the
        // caller so the responder can ask the customer to resend specifics.
        //
        // Only MALFORMED values block confirm — missing values mean the stage
        // transition upstream is wrong, which is handled by different guards
        // (and would already throw from create_simple_order preconditions).
        const draft = entry.bookingDraft;
        const allProblems = sanityCheckBookingDraft({
          senderName: draft?.senderName,
          senderPhone: draft?.senderPhone,
          recipientName: draft?.recipientName,
          recipientPhone: draft?.recipientPhone,
          pickupAddressBlock: draft?.pickupBlock,
          pickupAddressStreet: draft?.pickupStreet,
          pickupAddressHouse: draft?.pickupHouse,
          deliveryAddressBlock: draft?.deliveryBlock,
          deliveryAddressStreet: draft?.deliveryStreet,
          deliveryAddressHouse: draft?.deliveryHouse,
        });
        const problems = allProblems.filter((p) => p.reason !== "missing");
        if (problems.length > 0) {
          draftSanityProblems = problems;
          applied.push({ op: op.op, outcome: "rejected_draft_problems" });
          try {
            console.warn(
              `[responder-op] confirm_summary rejected draft_problems=${JSON.stringify(problems)}`,
            );
          } catch {}
        } else {
          confirmSummary = true;
          applied.push({ op: op.op, outcome: "accepted" });
        }
      } else {
        applied.push({ op: op.op, outcome: "ignored_not_summary_stage" });
      }
      continue;
    }
    if (op.op === "cancel_booking") {
      cancelled = true;
      applied.push({ op: op.op, outcome: "accepted" });
      continue;
    }
    if (op.op === "request_handoff") {
      handoffRequested = true;
      applied.push({ op: op.op, outcome: "accepted" });
      continue;
    }
    if (op.op === "start_booking") {
      applied.push({ op: op.op, outcome: "noted" });
      continue;
    }
    applied.push({ op: (op as any).op || "unknown", outcome: "unhandled" });
  }
  return {
    controllerEntry: entry,
    applied,
    summaryReady,
    cancelled,
    handoffRequested,
    confirmSummary,
    corrections,
    validationRejections,
    draftSanityProblems,
  };
}

// resolveNextBookingStepFromDraft moved to ./lib/booking-flow.ts (wave 4).

function applyBookingDraftProgress(entry: PersistedConversationControllerEntry): PersistedConversationControllerEntry {
  const nextStep = resolveNextBookingStepFromDraft(entry.bookingDraft);
  return {
    ...entry,
    stage: nextStep === "summary_pending" ? "summary_shown" : "collecting_booking_details",
    bookingStep: nextStep,
  };
}

// getLocationRoleSelection, formatPersistedBookingLocationLabel,
// buildSavedLocationRoleReply, buildDeterministicLocationSavedDuringIdentityReply
// moved to ./lib/booking-flow.ts (wave 4).
// buildDeterministicGraceWindowReply moved to ./lib/text.ts (wave 2a).

// buildDeterministicBookingDetailsReply, buildPendingOrderSummaryFingerprint,
// formatSummaryAreaLine moved to ./lib/booking-flow.ts (wave 4).

function buildDeterministicOrderSummaryReply(
  language: "ar" | "en",
  entry: PersistedConversationControllerEntry | null,
): string {
  const senderName = entry?.bookingDraft.senderName || "-";
  const senderPhone = entry?.bookingDraft.senderPhone || "-";
  const recipientName = entry?.bookingDraft.recipientName || "-";
  const recipientPhone = entry?.bookingDraft.recipientPhone || "-";
  const pickupArea =
    language === "ar"
      ? (entry?.quotePickupAreaNameAr || entry?.quotePickupAreaNameEn || "-")
      : (entry?.quotePickupAreaNameEn || "-");
  const dropoffArea =
    language === "ar"
      ? (entry?.quoteDropoffAreaNameAr || entry?.quoteDropoffAreaNameEn || "-")
      : (entry?.quoteDropoffAreaNameEn || "-");
  const pickupLine = formatSummaryAreaLine({
    language,
    area: pickupArea,
    block: entry?.bookingDraft.pickupBlock || null,
    street: entry?.bookingDraft.pickupStreet || null,
    house: entry?.bookingDraft.pickupHouse || null,
    location: entry?.bookingDraft.pickupLocation || null,
  });
  const deliveryLine = formatSummaryAreaLine({
    language,
    area: dropoffArea,
    block: entry?.bookingDraft.deliveryBlock || null,
    street: entry?.bookingDraft.deliveryStreet || null,
    house: entry?.bookingDraft.deliveryHouse || null,
    location: entry?.bookingDraft.deliveryLocation || null,
  });
  const deliveryType = language === "ar"
    ? (entry?.selectedQuoteOptionLabelAr || "سيارة عادية + توصيل عادي")
    : (entry?.selectedQuoteOptionLabelEn || (
      entry?.selectedDeliveryType === "sedan_fast"
        ? "Express sedan"
        : entry?.selectedDeliveryType === "van_normal"
          ? "Standard box van"
          : entry?.selectedDeliveryType === "van_fast"
            ? "Express box van"
            : "Standard sedan"
    ));
  const price = Number(entry?.quotedPrice ?? 0).toFixed(3);
  if (language === "ar") {
    return [
      "ملخص الطلب:",
      `المرسل: ${senderName}، ${senderPhone}`,
      `المستلم: ${recipientName}، ${recipientPhone}`,
      `الاستلام: ${pickupLine}`,
      `التوصيل: ${deliveryLine}`,
      `الخدمة: ${deliveryType}`,
      `السعر: ${price} KWD`,
      "",
      "هل نكمل؟",
    ].join("\n");
  }
  return [
    "Order summary:",
    `Sender: ${senderName}, ${senderPhone}`,
    `Recipient: ${recipientName}, ${recipientPhone}`,
    `Pickup: ${pickupLine}`,
    `Delivery: ${deliveryLine}`,
    `Service: ${deliveryType}`,
    `Price: ${price} KWD`,
    "",
    "Shall I proceed?",
  ].join("\n");
}

// normalizeBookingPhone, normalizeCurrentWhatsappBookingPhone,
// pickCurrentWhatsappPhone, cleanParsedName, textMentionsCurrentWhatsappNumber,
// isSenderPhoneConfirmationText, parseSenderStepInput, parseRecipientStepInput,
// normalizeAddressFieldValue, stripAddressFieldLabels, parseAddressStepInput
// moved to ./lib/booking-parse.ts (wave 2b).

function hasBookingSignalForCurrentStep(params: {
  controllerEntry: PersistedConversationControllerEntry | null;
  visibleText: string;
  replyTarget: string | null;
  location: PersistedBookingLocation | null;
}): boolean {
  const { controllerEntry, visibleText, replyTarget, location } = params;
  if (!controllerEntry || controllerEntry.stage !== "collecting_booking_details") {
    return false;
  }
  if (controllerEntry.bookingStep === "sender") {
    if (!visibleText.trim()) {
      return false;
    }
    return parseSenderStepInput(visibleText, replyTarget, {
      senderName: controllerEntry.bookingDraft.senderName,
      senderPhone: controllerEntry.bookingDraft.senderPhone,
    }).hasSignal;
  }
  if (controllerEntry.bookingStep === "recipient") {
    if (!visibleText.trim()) {
      return false;
    }
    return parseRecipientStepInput(visibleText).hasSignal;
  }
  if (controllerEntry.bookingStep === "pickup_address") {
    if (hasStructuredBookingLocation(location)) {
      return true;
    }
    if (!visibleText.trim()) {
      return false;
    }
    return parseAddressStepInput(visibleText, {
      block: controllerEntry.bookingDraft.pickupBlock,
      street: controllerEntry.bookingDraft.pickupStreet,
      house: controllerEntry.bookingDraft.pickupHouse,
    }).hasSignal;
  }
  if (controllerEntry.bookingStep === "delivery_address") {
    if (hasStructuredBookingLocation(location)) {
      return true;
    }
    if (!visibleText.trim()) {
      return false;
    }
    return parseAddressStepInput(visibleText, {
      block: controllerEntry.bookingDraft.deliveryBlock,
      street: controllerEntry.bookingDraft.deliveryStreet,
      house: controllerEntry.bookingDraft.deliveryHouse,
    }).hasSignal;
  }
  return false;
}

function isSingleUnlabeledAddressValue(text: string): boolean {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (!normalized || /[,\n]/.test(normalized)) {
    return false;
  }
  return !/(?:\bblock\b|\bstreet\b|\bhouse\b|\bbuilding\b|قطعة|قطعه|بلوك|شارع|منزل|بيت|بناية|بنايه|عمارة|عماره)/i.test(normalized);
}

function getNextMissingAddressField(
  current: { block: string | null; street: string | null; house: string | null },
): "block" | "street" | "house" | null {
  if (!current.block) {
    return "block";
  }
  if (!current.street) {
    return "street";
  }
  if (!current.house) {
    return "house";
  }
  return null;
}

function alignBookingFieldsToCurrentStep(params: {
  controllerEntry: PersistedConversationControllerEntry;
  visibleText: string;
  bookingFields: InterpretedBookingFields;
}): InterpretedBookingFields {
  const { controllerEntry, visibleText } = params;
  const bookingFields: InterpretedBookingFields = { ...params.bookingFields };
  const normalizedPhone = normalizeBookingPhone(visibleText);

  if (controllerEntry.bookingStep === "sender") {
    if (
      normalizedPhone &&
      !bookingFields.sender_phone &&
      !bookingFields.phone_decision &&
      !bookingFields.sender_name &&
      !!controllerEntry.bookingDraft.senderName
    ) {
      bookingFields.sender_phone = normalizedPhone;
    }
    return bookingFields;
  }

  if (controllerEntry.bookingStep === "recipient") {
    if (
      normalizedPhone &&
      !bookingFields.recipient_phone &&
      !bookingFields.recipient_name &&
      !!controllerEntry.bookingDraft.recipientName
    ) {
      bookingFields.recipient_phone = normalizedPhone;
    }
    return bookingFields;
  }

  if (
    controllerEntry.bookingStep === "pickup_address" ||
    controllerEntry.bookingStep === "delivery_address"
  ) {
    const current =
      controllerEntry.bookingStep === "pickup_address"
        ? {
            block: controllerEntry.bookingDraft.pickupBlock,
            street: controllerEntry.bookingDraft.pickupStreet,
            house: controllerEntry.bookingDraft.pickupHouse,
          }
        : {
            block: controllerEntry.bookingDraft.deliveryBlock,
            street: controllerEntry.bookingDraft.deliveryStreet,
            house: controllerEntry.bookingDraft.deliveryHouse,
          };
    const nextMissingField = getNextMissingAddressField(current);
    const addressValues = [
      bookingFields.address_block,
      bookingFields.address_street,
      bookingFields.address_house,
    ].filter(Boolean) as string[];
    if (
      nextMissingField &&
      addressValues.length === 1 &&
      isSingleUnlabeledAddressValue(visibleText)
    ) {
      const singleValue = addressValues[0];
      bookingFields.address_block = nextMissingField === "block" ? singleValue : null;
      bookingFields.address_street = nextMissingField === "street" ? singleValue : null;
      bookingFields.address_house = nextMissingField === "house" ? singleValue : null;
    }
  }

  return bookingFields;
}

function advanceBookingControllerFromCustomerText(params: {
  controllerEntry: PersistedConversationControllerEntry | null;
  visibleText: string;
  replyTarget: string | null;
  bookingFields?: InterpretedBookingFields | null;
  location?: PersistedBookingLocation | null;
}): PersistedConversationControllerEntry | null {
  const { controllerEntry, visibleText, replyTarget, bookingFields, location } = params;
  if (!controllerEntry || (!visibleText.trim() && !hasStructuredBookingLocation(location))) {
    return controllerEntry;
  }
  if (controllerEntry.stage === "awaiting_confirmation") {
    return controllerEntry;
  }
  if (controllerEntry.stage !== "collecting_booking_details") {
    return controllerEntry;
  }
  const alignedBookingFields = bookingFields
    ? alignBookingFieldsToCurrentStep({
        controllerEntry,
        visibleText,
        bookingFields,
      })
    : null;
  const nextEntry: PersistedConversationControllerEntry = {
    ...controllerEntry,
    bookingDraft: { ...controllerEntry.bookingDraft },
  };
  if (controllerEntry.bookingStep === "sender") {
    if (alignedBookingFields && (alignedBookingFields.sender_name || alignedBookingFields.sender_phone || alignedBookingFields.phone_decision)) {
      if (alignedBookingFields.sender_name) {
        nextEntry.bookingDraft.senderName = alignedBookingFields.sender_name;
      }
      if (alignedBookingFields.sender_phone) {
        nextEntry.bookingDraft.senderPhone = alignedBookingFields.sender_phone;
        nextEntry.bookingDraft.senderPhoneRejected = false;
      } else if (alignedBookingFields.phone_decision === "use_whatsapp" && replyTarget) {
        nextEntry.bookingDraft.senderPhone = pickCurrentWhatsappPhone(replyTarget);
        nextEntry.bookingDraft.senderPhoneRejected = false;
      } else if (alignedBookingFields.phone_decision === "different") {
        nextEntry.bookingDraft.senderPhone = null;
        nextEntry.bookingDraft.senderPhoneRejected = true;
      } else {
        nextEntry.bookingDraft.senderPhone =
          controllerEntry.bookingDraft.senderPhone || null;
      }
      return applyBookingDraftProgress(
        applyVolunteeredFutureBookingFields({
          controllerEntry: nextEntry,
          bookingFields,
        }),
      );
    }
    const parsed = parseSenderStepInput(visibleText, replyTarget, {
      senderName: controllerEntry.bookingDraft.senderName,
      senderPhone: controllerEntry.bookingDraft.senderPhone,
    });
    if (!parsed.hasSignal) {
      return controllerEntry;
    }
    if (parsed.senderName) {
      nextEntry.bookingDraft.senderName = parsed.senderName;
    }
    if (parsed.senderPhone) {
      nextEntry.bookingDraft.senderPhone = parsed.senderPhone;
      nextEntry.bookingDraft.senderPhoneRejected = false;
    } else {
      nextEntry.bookingDraft.senderPhone =
        controllerEntry.bookingDraft.senderPhone;
    }
    return applyBookingDraftProgress(nextEntry);
  }
  if (controllerEntry.bookingStep === "recipient") {
    if (alignedBookingFields && (alignedBookingFields.recipient_name || alignedBookingFields.recipient_phone)) {
      if (alignedBookingFields.recipient_name) {
        nextEntry.bookingDraft.recipientName = alignedBookingFields.recipient_name;
      }
      if (alignedBookingFields.recipient_phone) {
        nextEntry.bookingDraft.recipientPhone = alignedBookingFields.recipient_phone;
      }
      return applyBookingDraftProgress(nextEntry);
    }
    const parsed = parseRecipientStepInput(visibleText);
    if (!parsed.hasSignal) {
      return controllerEntry;
    }
    if (parsed.recipientName) {
      nextEntry.bookingDraft.recipientName = parsed.recipientName;
    }
    if (parsed.recipientPhone) {
      nextEntry.bookingDraft.recipientPhone = parsed.recipientPhone;
    }
    return applyBookingDraftProgress(nextEntry);
  }
  if (controllerEntry.bookingStep === "pickup_address") {
    if (hasStructuredBookingLocation(location)) {
      nextEntry.bookingDraft.pickupLocation = location || null;
      nextEntry.bookingDraft.pickupBlock = null;
      nextEntry.bookingDraft.pickupStreet = null;
      nextEntry.bookingDraft.pickupHouse = null;
      nextEntry.bookingDraft.pendingLocation = null;
      return applyBookingDraftProgress(nextEntry);
    }
    if (alignedBookingFields && (alignedBookingFields.address_block || alignedBookingFields.address_street || alignedBookingFields.address_house)) {
      nextEntry.bookingDraft.pickupLocation = null;
      nextEntry.bookingDraft.pickupBlock = alignedBookingFields.address_block || controllerEntry.bookingDraft.pickupBlock;
      nextEntry.bookingDraft.pickupStreet = alignedBookingFields.address_street || controllerEntry.bookingDraft.pickupStreet;
      nextEntry.bookingDraft.pickupHouse = alignedBookingFields.address_house || controllerEntry.bookingDraft.pickupHouse;
      return applyBookingDraftProgress(nextEntry);
    }
    const parsed = parseAddressStepInput(visibleText, {
      block: controllerEntry.bookingDraft.pickupBlock,
      street: controllerEntry.bookingDraft.pickupStreet,
      house: controllerEntry.bookingDraft.pickupHouse,
    });
    if (!parsed.hasSignal) {
      return controllerEntry;
    }
    nextEntry.bookingDraft.pickupLocation = null;
    nextEntry.bookingDraft.pickupBlock = parsed.block || controllerEntry.bookingDraft.pickupBlock;
    nextEntry.bookingDraft.pickupStreet = parsed.street || controllerEntry.bookingDraft.pickupStreet;
    nextEntry.bookingDraft.pickupHouse = parsed.house || controllerEntry.bookingDraft.pickupHouse;
    return applyBookingDraftProgress(nextEntry);
  }
  if (controllerEntry.bookingStep === "delivery_address") {
    if (hasStructuredBookingLocation(location)) {
      nextEntry.bookingDraft.deliveryLocation = location || null;
      nextEntry.bookingDraft.deliveryBlock = null;
      nextEntry.bookingDraft.deliveryStreet = null;
      nextEntry.bookingDraft.deliveryHouse = null;
      nextEntry.bookingDraft.pendingLocation = null;
      return applyBookingDraftProgress(nextEntry);
    }
    if (alignedBookingFields && (alignedBookingFields.address_block || alignedBookingFields.address_street || alignedBookingFields.address_house)) {
      nextEntry.bookingDraft.deliveryLocation = null;
      nextEntry.bookingDraft.deliveryBlock = alignedBookingFields.address_block || controllerEntry.bookingDraft.deliveryBlock;
      nextEntry.bookingDraft.deliveryStreet = alignedBookingFields.address_street || controllerEntry.bookingDraft.deliveryStreet;
      nextEntry.bookingDraft.deliveryHouse = alignedBookingFields.address_house || controllerEntry.bookingDraft.deliveryHouse;
      return applyBookingDraftProgress(nextEntry);
    }
    const parsed = parseAddressStepInput(visibleText, {
      block: controllerEntry.bookingDraft.deliveryBlock,
      street: controllerEntry.bookingDraft.deliveryStreet,
      house: controllerEntry.bookingDraft.deliveryHouse,
    });
    if (!parsed.hasSignal) {
      return controllerEntry;
    }
    nextEntry.bookingDraft.deliveryLocation = null;
    nextEntry.bookingDraft.deliveryBlock = parsed.block || controllerEntry.bookingDraft.deliveryBlock;
    nextEntry.bookingDraft.deliveryStreet = parsed.street || controllerEntry.bookingDraft.deliveryStreet;
    nextEntry.bookingDraft.deliveryHouse = parsed.house || controllerEntry.bookingDraft.deliveryHouse;
    return applyBookingDraftProgress(nextEntry);
  }
  return controllerEntry;
}

function applyPendingLocationRoleSelection(params: {
  controllerEntry: PersistedConversationControllerEntry | null;
  visibleText: string;
}): { entry: PersistedConversationControllerEntry; role: "pickup" | "delivery" } | null {
  const controllerEntry = params.controllerEntry;
  const pendingLocation = controllerEntry?.bookingDraft.pendingLocation;
  if (!controllerEntry || !pendingLocation) {
    return null;
  }
  const role = getLocationRoleSelection(params.visibleText);
  if (!role) {
    return null;
  }
  let nextEntry: PersistedConversationControllerEntry = {
    ...controllerEntry,
    bookingDraft: {
      ...controllerEntry.bookingDraft,
      pendingLocation: null,
    },
  };
  if (role === "pickup") {
    nextEntry.bookingDraft.pickupLocation = pendingLocation;
    nextEntry.bookingDraft.pickupBlock = null;
    nextEntry.bookingDraft.pickupStreet = null;
    nextEntry.bookingDraft.pickupHouse = null;
  } else {
    nextEntry.bookingDraft.deliveryLocation = pendingLocation;
    nextEntry.bookingDraft.deliveryBlock = null;
    nextEntry.bookingDraft.deliveryStreet = null;
    nextEntry.bookingDraft.deliveryHouse = null;
  }
  if (controllerEntry.stage === "collecting_booking_details") {
    nextEntry = applyBookingDraftProgress(nextEntry);
  }
  return { entry: nextEntry, role };
}

function shouldReissueBookingDetailsForLanguageSwitch(params: {
  explicitLanguage: "ar" | "en" | null;
  controllerEntry: PersistedConversationControllerEntry | null;
}): boolean {
  return !!params.explicitLanguage && [
    "collecting_booking_details",
    "summary_shown",
    "awaiting_confirmation",
  ].includes(String(params.controllerEntry?.stage || ""));
}

function isStoredQuotedRouteFresh(route: ({ quotedAt: number } & StoredQuotedRoute) | null | undefined): boolean {
  return !!route?.quotedAt && (Date.now() - route.quotedAt) <= CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS;
}

function isActiveBookingControllerFlow(entry: PersistedConversationControllerEntry | null): boolean {
  return !!entry && (
    entry.stage === "collecting_booking_details" ||
    entry.stage === "summary_shown" ||
    entry.stage === "awaiting_confirmation" ||
    entry.bookingStep === "sender" ||
    entry.bookingStep === "recipient" ||
    entry.bookingStep === "pickup_address" ||
    entry.bookingStep === "delivery_address" ||
    entry.bookingStep === "summary_pending" ||
    entry.bookingStep === "awaiting_summary_confirmation"
  );
}

const GREETING_GRACE_WINDOW_MS = 15 * 60_000;

function shouldPreserveGreetingDuringActiveFlow(entry: PersistedConversationControllerEntry | null): boolean {
  return !!entry &&
    isActiveBookingControllerFlow(entry) &&
    (Date.now() - entry.lastActivityTs) <= CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS;
}

function isGreetingInGraceWindow(entry: PersistedConversationControllerEntry | null): boolean {
  if (!entry || !isActiveBookingControllerFlow(entry)) return false;
  const elapsed = Date.now() - entry.lastActivityTs;
  return elapsed > CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS &&
    elapsed <= CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS + GREETING_GRACE_WINDOW_MS;
}

// stripBookingContinuationLeadIn moved to ./lib/intent-text.ts (wave 4).

function buildGreetingContinuationReply(
  language: "ar" | "en",
  entry: PersistedConversationControllerEntry | null,
): string {
  const intro = language === "ar"
    ? "هلا، نكمل من حيث وقفنا."
    : "Hi, we can continue from where we left off.";
  if (
    entry?.stage === "summary_shown" ||
    entry?.stage === "awaiting_confirmation" ||
    entry?.bookingStep === "summary_pending" ||
    entry?.bookingStep === "awaiting_summary_confirmation"
  ) {
    return `${intro}\n${buildDeterministicOrderSummaryReply(language, entry)}`;
  }
  return `${intro}\n${stripBookingContinuationLeadIn(
    language,
    buildDeterministicBookingDetailsReply(language, entry?.bookingStep || "sender", entry),
  )}`;
}

// includesAnyNormalizedPhrase moved to ./lib/intent-text.ts (wave 4).

function shouldFallbackToDeterministicBookingReply(params: {
  replyText: string | null;
  controllerEntry: PersistedConversationControllerEntry | null;
}): boolean {
  const entry = params.controllerEntry;
  if (
    !entry ||
    entry.stage !== "collecting_booking_details" ||
    !["sender", "recipient", "pickup_address", "delivery_address"].includes(entry.bookingStep)
  ) {
    return false;
  }
  const normalizedReply = normalizeIntentText(params.replyText || "");
  if (!normalizedReply) {
    return true;
  }
  const asksSender = includesAnyNormalizedPhrase(normalizedReply, [
    "sender",
    "sending the shipment",
    "full name",
    "same whatsapp number",
    "whatsapp number",
    "sender phone",
    "اسم المرسل",
    "اسمك",
    "رقم المرسل",
    "رقم الواتساب",
    "نفس الرقم",
  ]);
  const asksRecipient = includesAnyNormalizedPhrase(normalizedReply, [
    "recipient",
    "receiver",
    "who will receive",
    "recipient phone",
    "اسم المستلم",
    "رقم المستلم",
    "اللي يستلم",
    "المستلم",
  ]);
  const asksPickup = includesAnyNormalizedPhrase(normalizedReply, [
    "pickup",
    "pick up",
    "collect",
    "collection",
    "pickup address",
    "location pin",
    "map link",
    "where should we collect",
    "عنوان الاستلام",
    "موقع الاستلام",
    "لوكيشن الاستلام",
    "البلوك",
    "الشارع",
    "المنزل",
  ]);
  const asksDelivery = includesAnyNormalizedPhrase(normalizedReply, [
    "delivery",
    "dropoff",
    "drop off",
    "where should we deliver",
    "delivery address",
    "location pin",
    "map link",
    "عنوان التوصيل",
    "موقع التوصيل",
    "لوكيشن التوصيل",
    "البلوك",
    "الشارع",
    "المنزل",
  ]);
  const stepMatches = [asksSender, asksRecipient, asksPickup, asksDelivery].filter(Boolean).length;
  if (stepMatches > 1) {
    return true;
  }
  switch (entry.bookingStep) {
    case "sender":
      return !asksSender;
    case "recipient":
      return !asksRecipient;
    case "pickup_address":
      return !asksPickup || asksDelivery;
    case "delivery_address":
      return !asksDelivery || asksPickup;
    default:
      return false;
  }
}

function shouldFallbackToDeterministicSummaryReply(params: {
  replyText: string | null;
  preferredLanguage: "ar" | "en";
}): boolean {
  const rawReply = String(params.replyText || "");
  const normalizedReply = normalizeIntentText(rawReply);
  if (!normalizedReply) {
    return true;
  }
  const hasPrice =
    /\b\d+(?:\.\d{1,3})?\s*(kwd|kd)\b/i.test(rawReply) ||
    normalizedReply.includes("السعر");
  const hasConfirmationCue = includesAnyNormalizedPhrase(normalizedReply, [
    "shall i proceed",
    "should i proceed",
    "confirm",
    "confirmation",
    "go ahead",
    "proceed",
    "continue",
    "نكمل",
    "نأكد",
    "تأكيد",
    "اعتماد",
    "أعتمد",
  ]);
  const summarySignals = [
    includesAnyNormalizedPhrase(normalizedReply, ["sender", "المرسل"]),
    includesAnyNormalizedPhrase(normalizedReply, ["recipient", "receiver", "المستلم"]),
    includesAnyNormalizedPhrase(normalizedReply, ["pickup", "pick up", "الاستلام"]),
    includesAnyNormalizedPhrase(normalizedReply, ["delivery", "dropoff", "drop off", "التوصيل"]),
    includesAnyNormalizedPhrase(normalizedReply, ["service", "الخدمة"]),
  ].filter(Boolean).length;
  return !hasPrice || !hasConfirmationCue || summarySignals < 4;
}

function shouldReplaceGreetingForLanguage(params: {
  visibleText: string;
  replyText: string;
  preferredLanguage: "ar" | "en";
}): boolean {
  if (!isSimpleGreeting(params.visibleText)) {
    return false;
  }
  if (params.preferredLanguage === "en") {
    return containsArabic(params.replyText) && !containsLatin(params.replyText);
  }
  return containsLatin(params.replyText) && !containsArabic(params.replyText);
}

// isSummaryEditRequest moved to ./lib/intent-text.ts (wave 4).

function shouldResetControllerForNewRouteMessage(params: {
  controllerEntry: PersistedConversationControllerEntry | null;
  visibleText: string;
}): boolean {
  if (!params.controllerEntry || !params.visibleText.trim()) {
    return false;
  }
  if (!hasRouteEvidence(params.visibleText) || extractTrackingOrderId(params.visibleText)) {
    return false;
  }
  return (
    params.controllerEntry.stage === "collecting_booking_details" ||
    params.controllerEntry.stage === "summary_shown" ||
    params.controllerEntry.stage === "awaiting_confirmation" ||
    params.controllerEntry.stage === "order_submitted" ||
    params.controllerEntry.bookingStep !== "none"
  );
}

// textContainsUrl moved to ./lib/intent-text.ts (wave 4).

function shouldPreferCanonicalToolReply(params: {
  toolName: string | null;
  replyText: string;
  canonicalText: string | null;
  preferredLanguage: "ar" | "en";
  lastToolAgeMs: number;
  extractPricesFromText: (text: string) => string[];
}): boolean {
  const canonical = params.canonicalText ? normalizeReplyTextForComparison(params.canonicalText) : "";
  const reply = normalizeReplyTextForComparison(params.replyText);
  if (!params.toolName || !canonical || !reply || reply === canonical) {
    return false;
  }
  const wrongLanguageForConversation =
    params.preferredLanguage === "en"
      ? containsArabic(reply)
      : containsLatin(reply);
  if (wrongLanguageForConversation) {
    return true;
  }
  if (params.toolName === "create_simple_order" || params.toolName === "track_order") {
    if (params.lastToolAgeMs > 15_000) {
      return false;
    }
    const canonicalHasUrl = textContainsUrl(canonical);
    const replyHasUrl = textContainsUrl(reply);
    const replyTooShort = reply.length <= Math.max(48, Math.floor(canonical.length * 0.45));
    const canonicalHasOrderId = /\bORDER-[A-Za-z0-9-]+\b/i.test(canonical);
    const replyHasOrderId = /\bORDER-[A-Za-z0-9-]+\b/i.test(reply);
    return (canonicalHasUrl && !replyHasUrl) ||
      (canonicalHasOrderId && !replyHasOrderId) ||
      replyTooShort;
  }
  if (params.toolName !== "get_price") {
    return false;
  }
  const replyPrices = params.extractPricesFromText(reply);
  const canonicalPrices = params.extractPricesFromText(canonical);
  const sharesKnownPrice =
    replyPrices.length > 0 &&
    canonicalPrices.length > 0 &&
    replyPrices.every((price) => canonicalPrices.includes(price));
  const canonicalHasRouteContext =
    /delivery from|التوصيل من|available for booking|متاح للحجز|manual confirmation|تأكيد يدوي/i.test(canonical);
  const replyLooksLossy =
    looksLikePriceOnlyReply(reply) ||
    reply.length <= Math.max(24, Math.floor(canonical.length * 0.35)) ||
    (canonicalHasRouteContext &&
      !/delivery from|التوصيل من|available for booking|متاح للحجز|manual confirmation|تأكيد يدوي/i.test(reply));
  return sharesKnownPrice && replyLooksLossy;
}

// shouldMoveToHumanAgent, buildDeterministicTrackingGuardReply moved to
// ./lib/intent-text.ts (wave 4).

function isAllowedInbound(account: ResolvedOctopusAccount, conversationId: string, replyTarget: string | null): boolean {
  if (account.dmPolicy === "open") {
    return true;
  }
  if (account.dmPolicy === "disabled") {
    return false;
  }
  const allow = new Set(account.allowFrom.map((entry) => normalizeAllowEntry(entry)));
  if (allow.size === 0) {
    return false;
  }
  const conversationKey = normalizeAllowEntry(conversationId);
  const replyKey = normalizeAllowEntry(replyTarget);
  return allow.has(conversationKey) || (replyKey ? allow.has(replyKey) : false);
}

async function aiOctopusRequest(
  account: ResolvedOctopusAccount,
  endpoint: string,
  body: Record<string, unknown>,
): Promise<any> {
  if (!account.bearerToken) {
    throw new Error("AI_OCTOPUS_BEARER_TOKEN is missing.");
  }
  const response = await fetch(`${account.baseUrl}${endpoint}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${account.bearerToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  const raw = await response.text();
  let parsed: any;
  try {
    parsed = raw ? JSON.parse(raw) : null;
  } catch {
    parsed = raw;
  }
  if (!response.ok || (parsed && typeof parsed === "object" && parsed.success === false)) {
    throw new Error(`AI Octopus request failed: ${response.status} ${raw}`);
  }
  return parsed;
}

function isAiOctopusConversationClosedError(error: unknown): boolean {
  const text = error instanceof Error ? error.message : String(error || "");
  return text.includes("Conversation is closed");
}

async function clearInactivityEntry(params: {
  accountId: string;
  conversationId: string;
  logger: OpenClawPluginApi["logger"];
  reason: string;
}): Promise<void> {
  const key = `${params.accountId}::${params.conversationId}`;
  const state = await loadInactivityState();
  if (!state[key]) {
    return;
  }
  delete state[key];
  await saveInactivityState(state);
  params.logger.info(
    `[octopus] inactivity state cleared conversation=${params.conversationId} reason=${params.reason}`,
  );
}

function buildClosedConversationAlertKey(accountId: string, conversationId: string): string {
  return `${accountId}::${conversationId}`;
}

async function recordClosedConversationAlert(params: {
  accountId: string;
  conversationId: string;
  replyTarget: string;
  logger: OpenClawPluginApi["logger"];
  errorText: string;
}): Promise<void> {
  const key = buildClosedConversationAlertKey(params.accountId, params.conversationId);
  const state = await loadClosedConversationAlertState();
  const previous = state[key];
  const now = Date.now();
  const next: PersistedClosedConversationAlert = {
    accountId: params.accountId,
    conversationId: params.conversationId,
    replyTarget: params.replyTarget,
    firstDetectedTs: previous?.firstDetectedTs ?? now,
    lastDetectedTs: now,
    lastError: params.errorText,
    failureCount: (previous?.failureCount ?? 0) + 1,
  };
  state[key] = next;
  await saveClosedConversationAlertState(state);
  params.logger.error(
    `[octopus] operator action required account=${params.accountId} conversation=${params.conversationId} replyTarget=${params.replyTarget} cause=closed_conversation_thread remediation=reopen_or_new_thread failureCount=${next.failureCount} lastError=${JSON.stringify(params.errorText)}`,
  );
}

async function clearClosedConversationAlerts(params: {
  accountId: string;
  replyTarget: string;
}): Promise<string[]> {
  const state = await loadClosedConversationAlertState();
  const clearedConversationIds: string[] = [];
  for (const [key, entry] of Object.entries(state)) {
    if (entry.accountId !== params.accountId || entry.replyTarget !== params.replyTarget) {
      continue;
    }
    clearedConversationIds.push(entry.conversationId);
    delete state[key];
  }
  if (clearedConversationIds.length > 0) {
    await saveClosedConversationAlertState(state);
  }
  return clearedConversationIds;
}

async function sendTypingIndicator(
  account: ResolvedOctopusAccount,
  conversationId: string,
  messageId: string | null,
): Promise<boolean> {
  if (!account.typingEnabled || !conversationId || !messageId || !account.bearerToken) {
    return false;
  }
  try {
    const response = await fetch(`${account.baseUrl}/client/conversation/reply`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${account.bearerToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        messaging_product: "whatsapp",
        conversation_id: conversationId,
        status: "read",
        message_id: messageId,
        typing_indicator: { type: "text" },
      }),
    });
    await response.text();
    return response.ok;
  } catch {
    return false;
  }
}

function startTypingLoop(params: {
  account: ResolvedOctopusAccount;
  conversationId: string;
  messageId: string | null;
  logger: Pick<Console, "info"> | OpenClawPluginApi["logger"];
}): { stop: () => Promise<void> } {
  const { account, conversationId, messageId } = params;
  if (!account.typingEnabled || !conversationId || !messageId) {
    return { stop: async () => {} };
  }
  let timer: ReturnType<typeof setInterval> | null = null;
  const firstSend = sendTypingIndicator(account, conversationId, messageId).catch(() => false);
  timer = setInterval(() => {
    void sendTypingIndicator(account, conversationId, messageId).catch(() => false);
  }, account.typingRefreshMs);
  return {
    stop: async () => {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      await firstSend;
    },
  };
}

async function sendOctopusTextReply(params: {
  api: OpenClawPluginApi;
  account: ResolvedOctopusAccount;
  conversationId: string;
  replyTarget: string;
  text: string;
  source?: OctopusReplySource;
  preferredLanguage?: "ar" | "en";
  ingressIds?: string[];
}): Promise<void> {
  const {
    api,
    account,
    conversationId,
    replyTarget,
    text,
    source = "reply",
    preferredLanguage = "en",
    ingressIds = [],
  } = params;
  const sanitized = sanitizeAgentReplyText(text);
  let outboundText = sanitized.replyText;
  if (!outboundText && sanitized.providerErrorSuppressed) {
    outboundText = buildProviderIssueFallbackReply(preferredLanguage);
    logWebhookEvent(api.logger, "error", "operator action required", {
      account: account.accountId,
      conversation: conversationId,
      replyTarget,
      cause: "provider_error_suppressed",
      remediation: "inspect_model_or_provider_failure",
      source,
      ingressIds: ingressIds.length > 0 ? ingressIds.join(",") : undefined,
    });
  }
  if (!outboundText) {
    logWebhookEvent(api.logger, "warn", "outbound_result", {
      account: account.accountId,
      conversation: conversationId,
      replyTarget,
      source,
      status: "skipped_empty",
      ingressIds: ingressIds.length > 0 ? ingressIds.join(",") : undefined,
    });
    return;
  }
  const chunkMode = api.runtime.channel.text.resolveChunkMode(api.config, PROVIDER_NAME, account.accountId);
  const chunks = api.runtime.channel.text.chunkMarkdownTextWithMode(
    outboundText,
    account.textChunkLimit,
    chunkMode,
  );
  logWebhookEvent(api.logger, "info", "outbound_attempt", {
    account: account.accountId,
    conversation: conversationId,
    replyTarget,
    source,
    chunks: chunks.length,
    textLength: outboundText.length,
    providerErrorSuppressed: sanitized.providerErrorSuppressed,
    ingressIds: ingressIds.length > 0 ? ingressIds.join(",") : undefined,
  });
  const attemptStartedAt = Date.now();
  for (const [index, chunk] of chunks.entries()) {
    try {
      await aiOctopusRequest(account, "/client/conversation/reply", {
        messaging_product: "whatsapp",
        conversation_id: conversationId,
        to: replyTarget,
        type: "text",
        recipient_type: "individual",
        text: {
          body: chunk,
        },
      });
    } catch (error) {
      const errorText = error instanceof Error ? error.message : String(error);
      logWebhookEvent(api.logger, "error", "outbound_result", {
        account: account.accountId,
        conversation: conversationId,
        replyTarget,
        source,
        status: "failed",
        chunk: `${index + 1}/${chunks.length}`,
        durationMs: Date.now() - attemptStartedAt,
        error: errorText,
        ingressIds: ingressIds.length > 0 ? ingressIds.join(",") : undefined,
      });
      logWebhookEvent(api.logger, "error", "operator action required", {
        account: account.accountId,
        conversation: conversationId,
        replyTarget,
        cause: "outbound_send_failed",
        remediation: "inspect_octopus_delivery_api_or_credentials",
        error: errorText,
        ingressIds: ingressIds.length > 0 ? ingressIds.join(",") : undefined,
      });
      const failedAt = new Date().toISOString();
      await updateIngressLedgerEntries(ingressIds, (entry) => ({
        ...entry,
        status: "failed",
        error: errorText,
        lastUpdatedAt: failedAt,
      }));
      if (isAiOctopusConversationClosedError(error)) {
        await clearInactivityEntry({
          accountId: account.accountId,
          conversationId,
          logger: api.logger,
          reason: "conversation_closed",
        });
        if (source === "reply") {
          await recordClosedConversationAlert({
            accountId: account.accountId,
            conversationId,
            replyTarget,
            logger: api.logger,
            errorText: error instanceof Error ? error.message : String(error),
          });
        }
      }
      throw error;
    }
  }
  if (shouldMoveToHumanAgent(outboundText)) {
    await aiOctopusRequest(account, "/client/conversation/toagent", {
      conversation_id: conversationId,
    });
  }
  if (source === "reply") {
    const clearedConversationIds = await clearClosedConversationAlerts({
      accountId: account.accountId,
      replyTarget,
    });
    if (clearedConversationIds.length > 0) {
      api.logger.info(
        `[octopus] closed conversation alert cleared replyTarget=${replyTarget} activeConversation=${conversationId} clearedConversations=${clearedConversationIds.join(",")}`,
      );
    }
  }
  const repliedAt = new Date().toISOString();
  await updateIngressLedgerEntries(ingressIds, (entry) => ({
    ...entry,
    status: "replied",
    processedAt: repliedAt,
    lastUpdatedAt: repliedAt,
    error: null,
  }));
  logWebhookEvent(api.logger, "info", "outbound_result", {
    account: account.accountId,
    conversation: conversationId,
    replyTarget,
    source,
    status: "sent",
    chunks: chunks.length,
    durationMs: Date.now() - attemptStartedAt,
    providerErrorSuppressed: sanitized.providerErrorSuppressed,
    ingressIds: ingressIds.length > 0 ? ingressIds.join(",") : undefined,
  });
  api.logger.info(
    `[octopus] outbound reply sent conversation=${conversationId} text=${JSON.stringify(outboundText)}`,
  );
}

const TRANSCRIPTION_PROMPT_MAX_CHARS = 1800;
let cachedRidersVocabPrompt: string | null = null;

async function loadRidersTranscriptionVocab(): Promise<string | null> {
  if (cachedRidersVocabPrompt !== null) return cachedRidersVocabPrompt || null;
  try {
    const pricingPath = new URL("../../workspaces/riders/data/pricing.json", import.meta.url);
    const raw = await fs.readFile(pricingPath, "utf8");
    const parsed = JSON.parse(raw);
    const areas: Array<{ name_en?: string; name_ar?: string }> = Array.isArray(parsed?.areas) ? parsed.areas : [];
    const seen = new Set<string>();
    const names: string[] = [];
    for (const area of areas) {
      for (const candidate of [area.name_en, area.name_ar]) {
        const trimmed = typeof candidate === "string" ? candidate.trim() : "";
        if (!trimmed) continue;
        const key = trimmed.toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        names.push(trimmed);
      }
    }
    const domainTerms = [
      "Riders", "Kuwait", "delivery", "courier", "pickup", "dropoff",
      "block", "street", "house", "avenue", "floor", "apartment",
      "sedan", "van", "cooled van", "box van", "refrigerated",
      "standard", "express", "normal", "fast",
      "KWD", "dinar", "fils",
      "استلام", "توصيل", "قطعة", "شارع", "منزل", "بيت", "مبنى",
      "سيارة", "فان", "مبرد", "مبردة", "عادي", "سريع", "اكسبريس",
      "دينار", "فلس", "رايدرز",
    ];
    const parts: string[] = [
      "This is a customer service voice message for Riders, a delivery company in Kuwait.",
      "The customer may speak English, Arabic (Kuwaiti dialect), or mix both.",
      "They typically ask for delivery prices between Kuwait areas or give sender, recipient, and address details.",
      "Known Kuwait area names may include:",
      names.join(", "),
      "Common domain terms:",
      domainTerms.join(", "),
    ];
    let prompt = parts.join(" ");
    if (prompt.length > TRANSCRIPTION_PROMPT_MAX_CHARS) {
      prompt = prompt.slice(0, TRANSCRIPTION_PROMPT_MAX_CHARS);
    }
    cachedRidersVocabPrompt = prompt;
    return prompt;
  } catch (error) {
    cachedRidersVocabPrompt = "";
    return null;
  }
}

async function directOpenAiAudioTranscription(params: {
  audioBuffer: any;
  mimeType: string;
  fileName: string;
  prompt?: string | null;
  language?: string | null;
}): Promise<string | null> {
  const apiKey = env.OPENAI_API_KEY?.trim();
  if (!apiKey || !webFormData || !webBlob) {
    return null;
  }
  const form = new webFormData();
  form.append("model", "gpt-4o-transcribe");
  form.append("file", new webBlob([params.audioBuffer], { type: params.mimeType }), params.fileName);
  form.append("response_format", "json");
  if (params.prompt && params.prompt.trim()) {
    form.append("prompt", params.prompt.trim());
  }
  if (params.language && params.language.trim()) {
    form.append("language", params.language.trim());
  }
  const response = await fetch("https://api.openai.com/v1/audio/transcriptions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
    },
    body: form,
  });
  if (!response.ok) {
    const raw = await response.text();
    throw new Error(`Direct OpenAI transcription failed: ${response.status} ${raw}`);
  }
  const payload = (await response.json()) as any;
  return asTrimmedString(payload?.text);
}

const TRANSCRIPT_REFINE_TIMEOUT_MS = 2500;

async function refineTranscriptWithLlm(params: {
  rawText: string;
  language: "en" | "ar" | null;
  vocabPrompt: string | null;
  api: OpenClawPluginApi;
}): Promise<string | null> {
  const apiKey = env.OPENAI_API_KEY?.trim();
  const raw = asTrimmedString(params.rawText);
  if (!apiKey || !raw) return null;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TRANSCRIPT_REFINE_TIMEOUT_MS);
  try {
    const systemLines = [
      "You correct speech-to-text transcripts for Riders, a delivery company in Kuwait.",
      "Input is a raw STT transcript that may contain misheard Kuwaiti area names, delivery terms, or Arabic/English code-switching.",
      "Fix only obvious transcription errors for Kuwait area names and delivery terminology.",
      "Keep the customer's exact meaning, numbers, names, and phrasing intact. Never invent content. Never translate.",
      "If the transcript already looks correct, return it unchanged.",
      "Respond with JSON only: {\"corrected_text\":\"...\"}.",
    ];
    if (params.vocabPrompt) {
      systemLines.push(`Domain vocabulary hints: ${params.vocabPrompt.slice(0, 1500)}`);
    }
    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: TURN_INTERPRETER_MODEL,
        temperature: 0,
        response_format: { type: "json_object" },
        messages: [
          { role: "system", content: systemLines.join("\n") },
          {
            role: "user",
            content: JSON.stringify({
              raw_transcript: raw,
              customer_language_hint: params.language || "unknown",
            }),
          },
        ],
      }),
    });
    if (!response.ok) return null;
    const payload = (await response.json()) as any;
    const content = payload?.choices?.[0]?.message?.content;
    if (typeof content !== "string" || !content.trim()) return null;
    let parsed: any;
    try {
      parsed = JSON.parse(content);
    } catch {
      return null;
    }
    const corrected = asTrimmedString(parsed?.corrected_text);
    if (!corrected) return null;
    return corrected;
  } catch (error) {
    try {
      params.api.logger.warn(
        `[octopus] transcript refine failed error=${error instanceof Error ? error.message : String(error)}`,
      );
    } catch {}
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

async function transcribeAudioMessage(params: {
  api: OpenClawPluginApi;
  account: ResolvedOctopusAccount;
  audioMessage: OctopusInboundAudioMessage;
  preferredLanguage?: "en" | "ar" | null;
}): Promise<{ text: string; mediaPath: string; mimeType: string; sizeBytes: number; source: string; rawText: string; refined: boolean }> {
  const { api, account, audioMessage, preferredLanguage } = params;
  const response = await fetch(audioMessage.url);
  if (!response.ok) {
    throw new Error(`Audio download failed: ${response.status}`);
  }
  const audioBuffer = nodeBuffer.from(await response.arrayBuffer());
  if (!audioBuffer.length) {
    throw new Error("Audio download returned an empty file.");
  }
  const maxBytes = account.mediaMaxMb * 1024 * 1024;
  if (audioBuffer.length > maxBytes) {
    throw new Error(`Audio file too large for transcription (${audioBuffer.length} bytes).`);
  }
  const mimeType = splitMimeType(response.headers.get("content-type")) || audioMessage.mimeType || "audio/ogg";
  const saved = await api.runtime.channel.media.saveMediaBuffer(
    audioBuffer,
    mimeType,
    "inbound",
    maxBytes,
    `voice-note.${getAudioFileExtension({ ...audioMessage, mimeType })}`,
  );
  const vocabPrompt = await loadRidersTranscriptionVocab();
  const languageHint = preferredLanguage === "ar" || preferredLanguage === "en" ? preferredLanguage : null;
  let rawText: string | null = null;
  let transcriptionSource = "direct_openai_prompted";
  try {
    rawText = await directOpenAiAudioTranscription({
      audioBuffer,
      mimeType,
      fileName: path.basename(saved.path),
      prompt: vocabPrompt,
      language: languageHint,
    });
  } catch (error) {
    api.logger.warn(
      `[octopus] direct openai transcription with prompt failed, falling back to runtime stt error=${error instanceof Error ? error.message : String(error)}`,
    );
  }
  if (!rawText) {
    const maxAttempts = 2;
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      const transcription = await api.runtime.stt.transcribeAudioFile({
        filePath: saved.path,
        cfg: api.config,
      });
      const text = asTrimmedString(transcription?.text);
      if (text) {
        rawText = text;
        transcriptionSource = "runtime_stt";
        break;
      }
      api.logger.warn(
        `[octopus] audio transcription returned no text attempt=${String(attempt)}/${String(maxAttempts)} mime=${mimeType} size=${String(audioBuffer.length)}`,
      );
      if (attempt < maxAttempts) {
        await new Promise((resolve) => setTimeout(resolve, 400));
      }
    }
  }
  if (!rawText) {
    try {
      const directText = await directOpenAiAudioTranscription({
        audioBuffer,
        mimeType,
        fileName: path.basename(saved.path),
      });
      if (directText) {
        rawText = directText;
        transcriptionSource = "direct_openai_bare_fallback";
      }
    } catch (error) {
      api.logger.warn(
        `[octopus] bare direct openai fallback failed error=${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }
  if (!rawText) {
    throw new Error(`Audio transcription returned no text.`);
  }
  let finalText = rawText;
  let refined = false;
  if (rawText.length > 0 && rawText.length < 400) {
    const refinedText = await refineTranscriptWithLlm({
      rawText,
      language: languageHint,
      vocabPrompt,
      api,
    });
    if (refinedText && refinedText !== rawText) {
      finalText = refinedText;
      refined = true;
    }
  }
  return {
    text: finalText,
    mediaPath: saved.path,
    mimeType,
    sizeBytes: audioBuffer.length,
    source: transcriptionSource,
    rawText,
    refined,
  };
}

async function saveImageMessage(params: {
  api: OpenClawPluginApi;
  account: ResolvedOctopusAccount;
  imageMessage: OctopusInboundImageMessage;
}): Promise<{ mediaPath: string; mimeType: string; sizeBytes: number }> {
  const { api, account, imageMessage } = params;
  const response = await fetch(imageMessage.url);
  if (!response.ok) {
    throw new Error(`Image download failed: ${response.status}`);
  }
  const imageBuffer = nodeBuffer.from(await response.arrayBuffer());
  if (!imageBuffer.length) {
    throw new Error("Image download returned an empty file.");
  }
  const maxBytes = account.mediaMaxMb * 1024 * 1024;
  if (imageBuffer.length > maxBytes) {
    throw new Error(`Image file too large for vision (${imageBuffer.length} bytes).`);
  }
  const mimeType = splitMimeType(response.headers.get("content-type")) || imageMessage.mimeType || "image/jpeg";
  const saved = await api.runtime.channel.media.saveMediaBuffer(
    imageBuffer,
    mimeType,
    "inbound",
    maxBytes,
    `image.${getImageFileExtension({ ...imageMessage, mimeType })}`,
  );
  return {
    mediaPath: saved.path,
    mimeType,
    sizeBytes: imageBuffer.length,
  };
}

async function handleInboundMessage(params: {
  api: OpenClawPluginApi;
  account: ResolvedOctopusAccount;
  ingressIds: string[];
  payload: any;
  conversationId: string;
  messageText: string | null;
  replyTarget: string | null;
  messageId: string | null;
  audioMessage: OctopusInboundAudioMessage | null;
  imageMessage: OctopusInboundImageMessage | null;
  locationMessage: OctopusInboundLocationMessage | null;
}): Promise<void> {
  const { api, account, ingressIds, payload, conversationId, messageText, replyTarget, messageId, audioMessage, imageMessage, locationMessage } = params;
  if (!isAllowedInbound(account, conversationId, replyTarget)) {
    api.logger.warn(`[octopus] inbound blocked account=${account.accountId} conversation=${conversationId}`);
    const blockedAt = new Date().toISOString();
    await updateIngressLedgerEntries(ingressIds, (entry) => ({
      ...entry,
      status: "processed",
      processedAt: blockedAt,
      lastUpdatedAt: blockedAt,
      note: "inbound_blocked_by_policy",
    }));
    return;
  }
  const resolvedAgentId = resolveInboundAgentId(account.agentId, replyTarget);
  const senderRole = resolvedAgentId === account.agentId ? "customer" : "admin";
  if (senderRole === "customer" && replyTarget) {
    void recordInactivityActivity({ api, account, conversationId, replyTarget, messageText });
  }
  const controllerStateKey = buildConversationControllerKey(account.accountId, conversationId);
  let conversationControllerEntry =
    senderRole === "customer" && replyTarget
      ? await getConversationControllerEntry({
          key: controllerStateKey,
          accountId: account.accountId,
          conversationId,
          replyTarget,
        })
      : null;
  let resolvedText = messageText;
  let mediaPath: string | undefined;
  let mediaType: string | undefined;
  if (imageMessage) {
    try {
      const savedImage = await saveImageMessage({ api, account, imageMessage });
      mediaPath = savedImage.mediaPath;
      mediaType = savedImage.mimeType;
      api.logger.info(
        `[octopus] image saved account=${account.accountId} conversation=${conversationId} size=${String(savedImage.sizeBytes)}`,
      );
    } catch (error) {
      api.logger.error(
        `[octopus] image save failed account=${account.accountId} conversation=${conversationId} error=${error instanceof Error ? error.message : String(error)}`,
      );
      if (!resolvedText && replyTarget) {
        const imageFailureLanguage = resolveCustomerReplyLanguage({
          visibleText: asTrimmedString(messageText) || null,
          explicitLanguage: senderRole === "customer" ? detectExplicitLanguageRequest(asTrimmedString(messageText) || null) : null,
          fallbackLanguage: resolveControllerFallbackLanguage(conversationControllerEntry),
          preferFallbackForLowSignalText: true,
        });
        await sendOctopusTextReply({
          api,
          account,
          conversationId,
          replyTarget,
          text: imageFailureLanguage === "ar"
            ? "عذراً، ما قدرنا نقرأ الصورة بوضوح. ممكن تعيدون إرسالها أو تكتبون التفاصيل؟"
            : "Sorry, I couldn't read the image clearly. Please resend it or type the details.",
          preferredLanguage: imageFailureLanguage,
          ingressIds,
        });
        return;
      }
    }
  }
  if (!resolvedText && audioMessage) {
    try {
      const audioPreferredLanguage = resolveControllerFallbackLanguage(conversationControllerEntry);
      const transcription = await transcribeAudioMessage({
        api,
        account,
        audioMessage,
        preferredLanguage: audioPreferredLanguage,
      });
      resolvedText = transcription.text;
      mediaPath = transcription.mediaPath;
      mediaType = transcription.mimeType;
      const transcriptSnippet = (transcription.text || "").slice(0, 200).replace(/\s+/g, " ").trim();
      const rawSnippet = (transcription.rawText || "").slice(0, 200).replace(/\s+/g, " ").trim();
      api.logger.info(
        `[octopus] audio transcribed account=${account.accountId} conversation=${conversationId} size=${String(transcription.sizeBytes)} source=${transcription.source} lang=${audioPreferredLanguage || "auto"} refined=${transcription.refined ? "yes" : "no"} transcriptLen=${String((transcription.text || "").length)} transcript="${transcriptSnippet}" raw="${rawSnippet}"`,
      );
    } catch (error) {
      api.logger.error(
        `[octopus] audio transcription failed account=${account.accountId} conversation=${conversationId} error=${error instanceof Error ? error.message : String(error)}`,
      );
      if (replyTarget) {
        const audioFailureLanguage = resolveCustomerReplyLanguage({
          visibleText: asTrimmedString(messageText) || null,
          explicitLanguage: senderRole === "customer" ? detectExplicitLanguageRequest(asTrimmedString(messageText) || null) : null,
          fallbackLanguage: resolveControllerFallbackLanguage(conversationControllerEntry),
          preferFallbackForLowSignalText: true,
        });
        await sendOctopusTextReply({
          api,
          account,
          conversationId,
          replyTarget,
          text: audioFailureLanguage === "ar"
            ? "عذراً، ما قدرنا نفهم الرسالة الصوتية بوضوح. ممكن تكتبون طلبكم أو ترسلون فويس أوضح؟"
            : "Sorry, I couldn't understand the voice message clearly. Please type your request or send a clearer voice note.",
          preferredLanguage: audioFailureLanguage,
          ingressIds,
        });
      }
      return;
    }
  }
  const workflowInputText = asTrimmedString(resolvedText) || asTrimmedString(messageText) || "";
  // If a location was shared (native pin or map URL), resolve nearest Riders area and format for LLM
  let resolvedLocation = locationMessage;
  let resolvedLocationSource: PersistedBookingLocation["source"] | null =
    locationMessage ? "location_pin" : null;

  // If no native location pin but text contains a Google/Apple Maps URL, extract coordinates
  MAP_URL_RE.lastIndex = 0;
  if (!resolvedLocation && resolvedText && MAP_URL_RE.test(resolvedText)) {
    try {
      const mapLocation = await resolveMapUrlToLocation(resolvedText);
      if (mapLocation) {
        resolvedLocation = mapLocation;
        resolvedLocationSource = "map_link";
        api.logger.info(
          `[octopus] map URL resolved account=${account.accountId} conversation=${conversationId} lat=${mapLocation.latitude} lng=${mapLocation.longitude} name=${mapLocation.name || "none"}`,
        );
      } else {
        api.logger.info(
          `[octopus] map URL detected but no location extracted account=${account.accountId} conversation=${conversationId}`,
        );
      }
    } catch (error) {
      api.logger.warn(
        `[octopus] map URL resolution failed conversation=${conversationId} error=${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  // Auto-resolve nearest Riders geo area from coordinates
  let nearestAreaName: string | null = null;
  let locationPinContext: string | null = null;
  if (resolvedLocation) {
    const hasRealCoords = resolvedLocation.latitude !== 0 || resolvedLocation.longitude !== 0;

    // Always do Haversine lookup when we have real coordinates (most accurate)
    if (hasRealCoords) {
      try {
        const nearest = await resolveNearestArea(resolvedLocation.latitude, resolvedLocation.longitude);
        if (nearest) {
          nearestAreaName = nearest.name;
          api.logger.info(
            `[octopus] nearest area resolved account=${account.accountId} conversation=${conversationId} area=${nearest.name} distance=${nearest.distance_km}km governorate=${nearest.governorate}`,
          );
        }
      } catch (error) {
        api.logger.warn(
          `[octopus] nearest area resolution failed conversation=${conversationId} error=${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }

    const locationText = formatLocationAsText(resolvedLocation, nearestAreaName);
    locationPinContext = formatLocationPinContext(resolvedLocation, nearestAreaName);
    if (!resolvedText) {
      resolvedText = locationText;
    } else {
      resolvedText = `${resolvedText}\n${locationText}`;
    }
    api.logger.info(
      `[octopus] location processed account=${account.accountId} conversation=${conversationId} lat=${resolvedLocation.latitude} lng=${resolvedLocation.longitude} name=${resolvedLocation.name || "none"} nearestArea=${nearestAreaName || "none"}`,
    );
  }
  const persistedResolvedLocation = createPersistedBookingLocation({
    locationMessage: resolvedLocation,
    nearestAreaName,
    source: resolvedLocationSource || "location_pin",
  });
  const rawBody = asTrimmedString(resolvedText) || (audioMessage ? "<media:audio>" : imageMessage ? "<media:image>" : locationMessage ? formatLocationAsText(locationMessage) : "");
  if (!rawBody) {
    api.logger.info(`[octopus] ignored non-text conversation=${conversationId}`);
    return;
  }
  if (
    senderRole === "customer" &&
    conversationControllerEntry?.stage === "quoted" &&
    !hasActiveQuotedBookingAuthority(conversationControllerEntry)
  ) {
    conversationControllerEntry = {
      ...conversationControllerEntry,
      stage: "idle",
      bookingStep: "none",
      quoteTs: null,
      quoteRouteKey: null,
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
      pendingReplyText: null,
    };
    await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
    mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
    api.logger.info(`[controller] expired stale quoted state conversation=${conversationId}`);
  }
  const turnSignals = buildInboundTurnSignals({
    workflowInputText,
  });
  const explicitLanguageRequestRaw =
    senderRole === "customer" ? detectExplicitLanguageRequest(turnSignals.languageSignalText || null) : null;
  let preferredReplyLanguage = resolveCustomerReplyLanguage({
    visibleText: turnSignals.languageSignalText || null,
    explicitLanguage: explicitLanguageRequestRaw,
    fallbackLanguage: resolveControllerFallbackLanguage(conversationControllerEntry),
    preferFallbackForAudioTranscript: Boolean(audioMessage),
    preferFallbackForLowSignalText: true,
  });
  const promptSessionRevision =
    senderRole === "customer"
      ? await resolveAgentWorkspacePromptRevision(api.config, resolvedAgentId)
      : null;
  const sessionKey = api.runtime.channel.routing.buildAgentSessionKey({
    agentId: resolvedAgentId,
    channel: PROVIDER_NAME,
    accountId: account.accountId,
    peer: {
      kind: "direct",
      id: promptSessionRevision ? `${conversationId}::prompt=${promptSessionRevision}` : conversationId,
    },
    dmScope: api.config.session?.dmScope,
  });
  const preDispatchGuardState = (globalThis as any).__ridersGuardState as
    | { sessionState: Map<string, any> }
    | undefined;
  const preDispatchGuardEntry =
    senderRole === "customer" && conversationControllerEntry?.stage === "quoted"
      ? await findSessionGuardEntryWithPersistence(preDispatchGuardState?.sessionState, {
          activeSessionKey: sessionKey,
          conversationId,
          replyTarget,
        })
      : { key: sessionKey, session: null };
  const activeQuotedRoute = isStoredQuotedRouteFresh(preDispatchGuardEntry.session?.lastQuotedRoute)
    ? preDispatchGuardEntry.session?.lastQuotedRoute ?? null
    : null;
  const interpretedCustomerTurn =
    senderRole === "customer" && !RESPONDER_FIRST_FLAG && !isOneBrainConversation(replyTarget)
      ? await interpretCustomerTurnWithOpenAi({
          logger: api.logger,
          visibleText: turnSignals.workflowInputText,
          rawBody,
          preferredReplyLanguage,
          explicitLanguageRequest: explicitLanguageRequestRaw,
          controllerEntry: conversationControllerEntry,
          route: activeQuotedRoute,
          nearestAreaName,
          hasLocationMessage: Boolean(resolvedLocation),
        })
      : null;
  if (RESPONDER_FIRST_FLAG && senderRole === "customer") {
    try {
      clearResponderStateOps(conversationId);
    } catch {}
  }
  const explicitLanguageRequest =
    explicitLanguageRequestRaw ||
    (
      interpretedCustomerTurn?.action === "language_switch"
        ? (interpretedCustomerTurn.requested_language || null)
        : null
    );
  if (explicitLanguageRequest && explicitLanguageRequest !== explicitLanguageRequestRaw) {
    preferredReplyLanguage = resolveCustomerReplyLanguage({
      visibleText: turnSignals.languageSignalText || null,
      explicitLanguage: explicitLanguageRequest,
      fallbackLanguage: resolveControllerFallbackLanguage(conversationControllerEntry),
      preferFallbackForAudioTranscript: Boolean(audioMessage),
      preferFallbackForLowSignalText: true,
    });
  }
  if (
    !explicitLanguageRequest &&
    conversationControllerEntry &&
    (
      conversationControllerEntry.stage === "collecting_booking_details" ||
      conversationControllerEntry.stage === "summary_shown" ||
      conversationControllerEntry.stage === "awaiting_confirmation" ||
      conversationControllerEntry.bookingStep === "summary_pending" ||
      conversationControllerEntry.bookingStep === "awaiting_summary_confirmation"
    )
  ) {
    preferredReplyLanguage = resolveControllerFallbackLanguage(conversationControllerEntry);
  }
  if (senderRole === "customer" && interpretedCustomerTurn) {
    const bf = interpretedCustomerTurn.booking_fields;
    const bookingLog =
      bf &&
      (bf.sender_name ||
        bf.sender_phone ||
        bf.phone_decision ||
        bf.recipient_name ||
        bf.recipient_phone ||
        bf.address_block ||
        bf.address_street ||
        bf.address_house)
        ? ` booking=${[
            bf.sender_name ? `sn=${JSON.stringify(bf.sender_name)}` : null,
            bf.sender_phone ? `sp=${bf.sender_phone}` : null,
            bf.phone_decision ? `pd=${bf.phone_decision}` : null,
            bf.recipient_name ? `rn=${JSON.stringify(bf.recipient_name)}` : null,
            bf.recipient_phone ? `rp=${bf.recipient_phone}` : null,
            bf.address_block ? `ab=${JSON.stringify(bf.address_block)}` : null,
            bf.address_street ? `as=${JSON.stringify(bf.address_street)}` : null,
            bf.address_house ? `ah=${JSON.stringify(bf.address_house)}` : null,
          ]
            .filter(Boolean)
            .join(" ")}`
        : "";
    api.logger.info(
      `[turn-interpreter] conversation=${conversationId} action=${interpretedCustomerTurn.action} selected=${interpretedCustomerTurn.selected_delivery_type || "na"} useActiveQuote=${interpretedCustomerTurn.should_use_active_quote ? "yes" : "no"} routeChanged=${interpretedCustomerTurn.route_changed ? "yes" : "no"} confidence=${interpretedCustomerTurn.confidence}${bookingLog}`,
    );
  }
  try {
    const inboundType = locationMessage
      ? "location"
      : audioMessage
        ? "audio"
        : imageMessage
          ? "image"
          : "text";
    const inboundSnippet = (rawBody || "").slice(0, 200).replace(/\s+/g, " ").trim();
    const trace = {
      conv: conversationId,
      msg: messageId || null,
      sender: senderRole,
      in_type: inboundType,
      in: inboundSnippet,
      lang: preferredReplyLanguage || null,
      mode: RESPONDER_FIRST_FLAG ? "responder_first" : "interpreter_first",
      interp: interpretedCustomerTurn
        ? {
            action: interpretedCustomerTurn.action,
            conf: interpretedCustomerTurn.confidence,
            selected: interpretedCustomerTurn.selected_delivery_type || null,
            route_changed: Boolean(interpretedCustomerTurn.route_changed),
            use_active_quote: Boolean(interpretedCustomerTurn.should_use_active_quote),
            fields: interpretedCustomerTurn.booking_fields || null,
            location_role_hint: interpretedCustomerTurn.location_role_hint || null,
          }
        : null,
      state: {
        stage: conversationControllerEntry?.stage || null,
        booking_step: conversationControllerEntry?.bookingStep || null,
        quoted_pickup: conversationControllerEntry?.quotePickupAreaNameEn || null,
        quoted_dropoff: conversationControllerEntry?.quoteDropoffAreaNameEn || null,
      },
    };
    api.logger.info(`[turn-trace] ${JSON.stringify(trace)}`);
  } catch {}
  if (senderRole === "customer" && replyTarget) {
    void recordInactivityActivity({
      api,
      account,
      conversationId,
      replyTarget,
      messageText: turnSignals.languageSignalText || rawBody || null,
      languageOverride: preferredReplyLanguage,
    });
  }
  const currentCustomerIntent =
    senderRole === "customer"
      ? (
        mapInterpretedActionToCustomerIntent(interpretedCustomerTurn) ||
        classifyCustomerIntent({
          visibleText: turnSignals.workflowInputText || null,
          explicitLanguage: explicitLanguageRequest,
          controllerEntry: conversationControllerEntry,
        })
      )
      : null;
  let controllerTransitionHint: string | null = null;
  const llmSaysBookingData =
    interpretedCustomerTurn?.action === "booking_step_input" ||
    interpretedCustomerTurn?.action === "correct_booking_field";
  if (
    senderRole === "customer" &&
    turnSignals.workflowInputText &&
    !llmSaysBookingData &&
    shouldResetControllerForNewRouteMessage({
      controllerEntry: conversationControllerEntry,
      visibleText: turnSignals.workflowInputText,
    })
  ) {
    conversationControllerEntry = conversationControllerEntry
      ? {
          ...conversationControllerEntry,
          stage: "idle",
          bookingStep: "none",
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
          pendingReplyText: null,
        }
      : null;
    if (conversationControllerEntry) {
      api.logger.info(
        `[controller] reset active booking flow after new route message conversation=${conversationId} text=${JSON.stringify(turnSignals.workflowInputText.slice(0, 160))}`,
      );
    }
  }
  const isGreetingTurn =
    interpretedCustomerTurn?.action === "greeting" ||
    (!interpretedCustomerTurn && currentCustomerIntent === "greeting");
  const shouldContinueGreetingInActiveFlow =
    senderRole === "customer" &&
    conversationControllerEntry &&
    isGreetingTurn &&
    shouldPreserveGreetingDuringActiveFlow(conversationControllerEntry);
  if (
    senderRole === "customer" &&
    conversationControllerEntry &&
    isGreetingTurn &&
    !shouldContinueGreetingInActiveFlow &&
    conversationControllerEntry.stage !== "idle" &&
    conversationControllerEntry.stage !== "quoted"
  ) {
    // Grace window: if the session is stale but within grace, offer to continue
    // instead of silently nuking the booking draft.
    if (replyTarget && isGreetingInGraceWindow(conversationControllerEntry)) {
      conversationControllerEntry = {
        ...conversationControllerEntry,
        lastActivityTs: Date.now(),
        language: preferredReplyLanguage,
        conversationId,
        replyTarget,
        accountId: account.accountId,
      };
      await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      controllerTransitionHint = "grace_window_offer";
      api.logger.info(
        `[controller] greeting in grace window routed through agent conversation=${conversationId} stage=${conversationControllerEntry.stage}`,
      );
    }
    if (controllerTransitionHint !== "grace_window_offer") {
      const prevStage = conversationControllerEntry.stage;
      conversationControllerEntry = {
        ...conversationControllerEntry,
        stage: "idle",
        bookingStep: "none",
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
        pendingReplyText: null,
      };
      await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      api.logger.info(
        `[controller] greeting reset: cleared stale ${prevStage} state conversation=${conversationId}`,
      );
    }
  }
  // 3-layer pending location role assignment:
  // Layer 1: deterministic keyword match (fast, no API)
  // Layer 2: LLM location_role_hint from turn interpreter
  // Layer 3: safe deterministic re-ask (never orphan the pin)
  const hasPendingLocationToAssign =
    senderRole === "customer" &&
    conversationControllerEntry?.bookingDraft.pendingLocation &&
    replyTarget;
  if (hasPendingLocationToAssign) {
    // Layer 1: deterministic fast-path
    let pendingLocationRoleResult =
      turnSignals.workflowInputText
        ? applyPendingLocationRoleSelection({
            controllerEntry: conversationControllerEntry,
            visibleText: turnSignals.workflowInputText,
          })
        : null;
    // Layer 2: LLM intelligence — trust GPT-5.4's location_role_hint
    if (!pendingLocationRoleResult && interpretedCustomerTurn?.location_role_hint) {
      const llmRole = interpretedCustomerTurn.location_role_hint;
      const pendingLocation = conversationControllerEntry.bookingDraft.pendingLocation;
      let nextEntry: PersistedConversationControllerEntry = {
        ...conversationControllerEntry,
        bookingDraft: {
          ...conversationControllerEntry.bookingDraft,
          pendingLocation: null,
        },
      };
      if (llmRole === "pickup") {
        nextEntry.bookingDraft.pickupLocation = pendingLocation;
        nextEntry.bookingDraft.pickupBlock = null;
        nextEntry.bookingDraft.pickupStreet = null;
        nextEntry.bookingDraft.pickupHouse = null;
      } else {
        nextEntry.bookingDraft.deliveryLocation = pendingLocation;
        nextEntry.bookingDraft.deliveryBlock = null;
        nextEntry.bookingDraft.deliveryStreet = null;
        nextEntry.bookingDraft.deliveryHouse = null;
      }
      if (conversationControllerEntry.stage === "collecting_booking_details") {
        nextEntry = applyBookingDraftProgress(nextEntry);
      }
      pendingLocationRoleResult = { entry: nextEntry, role: llmRole };
      api.logger.info(
        `[controller] pending location resolved via LLM location_role_hint=${llmRole} conversation=${conversationId}`,
      );
    }
    if (pendingLocationRoleResult) {
      const shouldInvalidateQuoteContext =
        pendingLocationRoleResult.entry.stage !== "collecting_booking_details" &&
        (
          conversationControllerEntry.stage === "quoted" ||
          hasActiveQuotedBookingAuthority(conversationControllerEntry) ||
          Boolean(conversationControllerEntry.quoteRouteKey)
        );
      conversationControllerEntry = {
        ...(shouldInvalidateQuoteContext
          ? clearQuotedRouteContext(pendingLocationRoleResult.entry)
          : pendingLocationRoleResult.entry),
        lastActivityTs: Date.now(),
        language: preferredReplyLanguage,
        explicitLanguage: explicitLanguageRequest || pendingLocationRoleResult.entry.explicitLanguage,
        conversationId,
        replyTarget,
        accountId: account.accountId,
      };
      await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      controllerTransitionHint = `location_saved:${pendingLocationRoleResult.role}`;
      api.logger.info(
        `[controller] pending location assigned routed through agent conversation=${conversationId} role=${pendingLocationRoleResult.role} stage=${conversationControllerEntry.stage} step=${conversationControllerEntry.bookingStep}`,
      );
    }
    if (!pendingLocationRoleResult && persistedResolvedLocation && hasStructuredBookingLocation(persistedResolvedLocation)) {
      conversationControllerEntry = {
        ...conversationControllerEntry,
        lastActivityTs: Date.now(),
        language: preferredReplyLanguage,
        explicitLanguage: explicitLanguageRequest || conversationControllerEntry.explicitLanguage,
        conversationId,
        replyTarget,
        accountId: account.accountId,
        bookingDraft: {
          ...conversationControllerEntry.bookingDraft,
          pendingLocation: persistedResolvedLocation,
        },
      };
      await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      controllerTransitionHint = "location_pending_role_clarification";
      api.logger.info(
        `[controller] pending location replaced with newer shared location routed through agent conversation=${conversationId}`,
      );
    }
    if (!pendingLocationRoleResult) {
      conversationControllerEntry = {
        ...conversationControllerEntry,
        lastActivityTs: Date.now(),
        language: preferredReplyLanguage,
        conversationId,
        replyTarget,
        accountId: account.accountId,
      };
      await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      controllerTransitionHint = "location_pending_role_clarification";
      api.logger.info(
        `[controller] pending location role unknown routed through agent conversation=${conversationId}`,
      );
    }
  }
  const shouldAdvanceBookingControllerFromText =
    // Responder-first / one-brain modes: draft mutations come exclusively from
    // LLM tool calls (apply_booking_field). Do not let the legacy heuristic
    // parser run — it pollutes bookingDraft by capturing arbitrary text
    // ("thenumber is", "Ok") as field values.
    !RESPONDER_FIRST_FLAG &&
    !isOneBrainConversation(replyTarget) &&
    senderRole === "customer" &&
    (Boolean(turnSignals.workflowInputText) || hasStructuredBookingLocation(persistedResolvedLocation)) &&
    Boolean(conversationControllerEntry) &&
    (
      interpretedCustomerTurn?.action === "booking_step_input" ||
      interpretedCustomerTurn?.action === "correct_booking_field" ||
      (
        conversationControllerEntry?.stage === "collecting_booking_details" &&
        hasBookingSignalForCurrentStep({
          controllerEntry: conversationControllerEntry,
          visibleText: turnSignals.workflowInputText,
          replyTarget,
          location: persistedResolvedLocation,
        }) &&
        ![
          "greeting",
          "language_switch",
          "service_overview",
          "pricing_request",
          "same_route_quote_option",
          "same_route_show_other_options",
          "passenger_transport_request",
          "handoff",
        ].includes(interpretedCustomerTurn?.action || "") &&
        !extractTrackingOrderId(turnSignals.workflowInputText) &&
        !isTrackingIntent(turnSignals.workflowInputText)
      )
    );
  // Handle mid-booking field corrections: apply corrected fields regardless of current step,
  // then re-derive the booking step from the updated draft.
  if (
    shouldAdvanceBookingControllerFromText &&
    interpretedCustomerTurn?.action === "correct_booking_field" &&
    interpretedCustomerTurn.booking_fields &&
    conversationControllerEntry &&
    (
      conversationControllerEntry.stage === "collecting_booking_details" ||
      conversationControllerEntry.stage === "summary_shown" ||
      conversationControllerEntry.stage === "awaiting_confirmation" ||
      conversationControllerEntry.bookingStep === "summary_pending" ||
      conversationControllerEntry.bookingStep === "awaiting_summary_confirmation"
    )
  ) {
    const fields = interpretedCustomerTurn.booking_fields;
    const correctionResult = applyBookingFieldCorrection({
      controllerEntry: conversationControllerEntry,
      visibleText: turnSignals.workflowInputText,
      replyTarget,
      bookingFields: fields,
    });
    conversationControllerEntry = correctionResult.entry;
    if (correctionResult.status === "ambiguous_address_role") {
      controllerTransitionHint = "correction_ambiguous_address";
    } else if (correctionResult.status === "no_op") {
      controllerTransitionHint = "correction_unparsed";
    } else if (
      conversationControllerEntry.stage === "awaiting_confirmation" ||
      conversationControllerEntry.bookingStep === "awaiting_summary_confirmation" ||
      conversationControllerEntry.bookingStep === "summary_pending"
    ) {
      controllerTransitionHint = "summary_ready";
    } else {
      controllerTransitionHint = `booking_step_advanced:${conversationControllerEntry.bookingStep}`;
    }
    api.logger.info(
      `[controller] booking field correction status=${correctionResult.status} conversation=${conversationId} corrected_fields=${JSON.stringify(fields)} step=${conversationControllerEntry.bookingStep} hint=${controllerTransitionHint}`,
    );
  } else if (shouldAdvanceBookingControllerFromText) {
    conversationControllerEntry = advanceBookingControllerFromCustomerText({
      controllerEntry: conversationControllerEntry,
      visibleText: turnSignals.workflowInputText,
      replyTarget,
      bookingFields:
        interpretedCustomerTurn?.action === "booking_step_input"
          ? interpretedCustomerTurn.booking_fields ?? null
          : null,
      location: persistedResolvedLocation,
    });
  }
  if (
    shouldAdvanceBookingControllerFromText &&
    !controllerTransitionHint?.startsWith("location_saved:") &&
    conversationControllerEntry?.stage === "collecting_booking_details" &&
    (
      conversationControllerEntry.bookingStep === "sender" ||
      conversationControllerEntry.bookingStep === "recipient" ||
      conversationControllerEntry.bookingStep === "pickup_address" ||
      conversationControllerEntry.bookingStep === "delivery_address"
    )
  ) {
    controllerTransitionHint = `booking_step_advanced:${conversationControllerEntry.bookingStep}`;
  }
  if (
    senderRole === "customer" &&
    replyTarget &&
    conversationControllerEntry &&
    (
      shouldContinueGreetingInActiveFlow ||
      conversationControllerEntry.stage === "summary_shown" ||
      conversationControllerEntry.bookingStep === "summary_pending"
    )
  ) {
    if (shouldContinueGreetingInActiveFlow) {
      conversationControllerEntry = {
        ...conversationControllerEntry,
        lastActivityTs: Date.now(),
        language: preferredReplyLanguage,
        explicitLanguage: explicitLanguageRequest || conversationControllerEntry.explicitLanguage,
        conversationId,
        replyTarget,
        accountId: account.accountId,
      };
      await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      controllerTransitionHint = "greeting_during_active_booking";
      api.logger.info(
        `[controller] greeting during active booking routed through agent conversation=${conversationId} stage=${conversationControllerEntry.stage} step=${conversationControllerEntry.bookingStep}`,
      );
    } else if (
      !controllerTransitionHint &&
      (
        conversationControllerEntry.stage === "summary_shown" ||
        conversationControllerEntry.bookingStep === "summary_pending"
      )
    ) {
      conversationControllerEntry = {
        ...conversationControllerEntry,
        stage: conversationControllerEntry.stage === "summary_shown"
          ? "awaiting_confirmation"
          : conversationControllerEntry.stage,
        bookingStep:
          conversationControllerEntry.bookingStep === "summary_pending"
            ? "awaiting_summary_confirmation"
            : conversationControllerEntry.bookingStep,
        lastActivityTs: Date.now(),
        language: preferredReplyLanguage,
        explicitLanguage: explicitLanguageRequest || conversationControllerEntry.explicitLanguage,
        conversationId,
        replyTarget,
        accountId: account.accountId,
      };
      controllerTransitionHint = "summary_ready";
    }
    // Greeting during active booking now routed through agent via controllerTransitionHint
  }
  // Tracking without order ID: LLM already knows from IDENTITY.md to ask for ORDER-XXXXX format
  const effectiveLanguageSwitch: "ar" | "en" | null =
    explicitLanguageRequest ||
    (interpretedCustomerTurn?.action === "language_switch" ? interpretedCustomerTurn.requested_language : null);
  if (senderRole === "customer" && replyTarget && effectiveLanguageSwitch) {
    if (conversationControllerEntry) {
      conversationControllerEntry = {
        ...conversationControllerEntry,
        lastActivityTs: Date.now(),
        language: preferredReplyLanguage,
        explicitLanguage: effectiveLanguageSwitch,
        conversationId,
        replyTarget,
        accountId: account.accountId,
      };
      if (shouldReissueBookingDetailsForLanguageSwitch({
        explicitLanguage: effectiveLanguageSwitch,
        controllerEntry: conversationControllerEntry,
      })) {
        if (
          conversationControllerEntry.stage === "summary_shown" ||
          conversationControllerEntry.stage === "awaiting_confirmation" ||
          conversationControllerEntry.bookingStep === "summary_pending" ||
          conversationControllerEntry.bookingStep === "awaiting_summary_confirmation"
        ) {
          conversationControllerEntry = {
            ...conversationControllerEntry,
            stage: conversationControllerEntry.stage === "summary_shown"
              ? "awaiting_confirmation"
              : conversationControllerEntry.stage,
            bookingStep: "awaiting_summary_confirmation",
            language: preferredReplyLanguage,
          };
          controllerTransitionHint = "language_switch_reissue_summary";
        } else {
          conversationControllerEntry = {
            ...conversationControllerEntry,
            stage: "collecting_booking_details",
            bookingStep: conversationControllerEntry.bookingStep === "none"
              ? "sender"
              : conversationControllerEntry.bookingStep,
            language: preferredReplyLanguage,
          };
          controllerTransitionHint = `language_switch_reissue:${conversationControllerEntry.bookingStep}`;
        }
        api.logger.info(
          `[controller] language-switch reissue routed through agent in ${preferredReplyLanguage} conversation=${conversationId}`,
        );
      }
      await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
    }
    // Generic language switch: let the agent handle it naturally instead of
    // sending a canned reply. The controller state is already updated above.
  }
  if (
    senderRole === "customer" &&
    replyTarget &&
    conversationControllerEntry &&
    persistedResolvedLocation &&
    hasStructuredBookingLocation(persistedResolvedLocation)
  ) {
    const declaredStandaloneRole = getDeclaredLocationRole({
      visibleText: turnSignals.workflowInputText,
      interpretedTurn: interpretedCustomerTurn,
    });
    if (
      declaredStandaloneRole &&
      !hasActiveQuotedBookingAuthority(conversationControllerEntry) &&
      conversationControllerEntry.stage !== "collecting_booking_details" &&
      conversationControllerEntry.bookingStep === "none"
    ) {
      conversationControllerEntry = {
        ...applyStandaloneLocationAssignment({
          controllerEntry: conversationControllerEntry,
          location: persistedResolvedLocation,
          role: declaredStandaloneRole,
        }),
        lastActivityTs: Date.now(),
        language: preferredReplyLanguage,
        explicitLanguage: explicitLanguageRequest || conversationControllerEntry.explicitLanguage,
        conversationId,
        replyTarget,
        accountId: account.accountId,
      };
      await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      controllerTransitionHint = `location_saved:${declaredStandaloneRole}`;
      api.logger.info(
        `[controller] standalone location assigned from same-turn role routed through agent conversation=${conversationId} role=${declaredStandaloneRole}`,
      );
    }
    const autoRole = getStandaloneLocationAutoAssignmentRole(conversationControllerEntry);
    if (autoRole) {
      conversationControllerEntry = {
        ...clearQuotedRouteContext(applyStandaloneLocationAssignment({
          controllerEntry: conversationControllerEntry,
          location: persistedResolvedLocation,
          role: autoRole,
        })),
        lastActivityTs: Date.now(),
        language: preferredReplyLanguage,
        explicitLanguage: explicitLanguageRequest || conversationControllerEntry.explicitLanguage,
        conversationId,
        replyTarget,
        accountId: account.accountId,
      };
      await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      controllerTransitionHint = `location_saved:${autoRole}`;
      api.logger.info(
        `[controller] standalone location auto-assigned routed through agent conversation=${conversationId} role=${autoRole} stage=${conversationControllerEntry.stage} step=${conversationControllerEntry.bookingStep}`,
      );
    }
  }
  if (
    senderRole === "customer" &&
    replyTarget &&
    shouldUseDeterministicLocationClarification({
      controllerEntry: conversationControllerEntry,
      locationMessage: resolvedLocation,
    })
  ) {
    if (conversationControllerEntry) {
      conversationControllerEntry = {
        ...conversationControllerEntry,
        lastActivityTs: Date.now(),
        language: preferredReplyLanguage,
        explicitLanguage: explicitLanguageRequest || conversationControllerEntry.explicitLanguage,
        conversationId,
        replyTarget,
        accountId: account.accountId,
        bookingDraft: {
          ...conversationControllerEntry.bookingDraft,
          pendingLocation: persistedResolvedLocation,
        },
      };
      await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
    }
    const locationReply = buildDeterministicLocationClarificationReply({
      language: preferredReplyLanguage,
      nearestAreaName,
      locationMessage: resolvedLocation,
    });
    await sendOctopusTextReply({
      api,
      account,
      conversationId,
      replyTarget,
      text: locationReply,
      preferredLanguage: preferredReplyLanguage,
      ingressIds,
    });
    api.logger.info(
      `[controller] Deterministic location clarification reply sent conversation=${conversationId} lang=${preferredReplyLanguage} area=${JSON.stringify(nearestAreaName || resolvedLocation?.name || resolvedLocation?.address || "")} text=${JSON.stringify(locationReply)}`,
    );
    return;
  }
  // Save location pin during non-address booking steps (sender/recipient) as pendingLocation
  // so it's preserved for the address step instead of being silently lost.
  if (
    senderRole === "customer" &&
    replyTarget &&
    persistedResolvedLocation &&
    hasStructuredBookingLocation(persistedResolvedLocation) &&
    conversationControllerEntry?.stage === "collecting_booking_details" &&
    (conversationControllerEntry.bookingStep === "sender" || conversationControllerEntry.bookingStep === "recipient")
  ) {
    const declaredLocationRole = getDeclaredLocationRole({
      visibleText: turnSignals.workflowInputText,
      interpretedTurn: interpretedCustomerTurn,
    });
    conversationControllerEntry = {
      ...(declaredLocationRole
        ? applyStandaloneLocationAssignment({
            controllerEntry: conversationControllerEntry,
            location: persistedResolvedLocation,
            role: declaredLocationRole,
          })
        : conversationControllerEntry),
      lastActivityTs: Date.now(),
      language: preferredReplyLanguage,
      explicitLanguage: explicitLanguageRequest || conversationControllerEntry.explicitLanguage,
      conversationId,
      replyTarget,
      accountId: account.accountId,
      bookingDraft: {
        ...(
          declaredLocationRole
            ? (declaredLocationRole === "pickup"
              ? {
                  ...conversationControllerEntry.bookingDraft,
                  pickupLocation: persistedResolvedLocation,
                  pickupBlock: null,
                  pickupStreet: null,
                  pickupHouse: null,
                  pendingLocation: null,
                }
              : {
                  ...conversationControllerEntry.bookingDraft,
                  deliveryLocation: persistedResolvedLocation,
                  deliveryBlock: null,
                  deliveryStreet: null,
                  deliveryHouse: null,
                  pendingLocation: null,
                })
            : {
                ...conversationControllerEntry.bookingDraft,
                pendingLocation: persistedResolvedLocation,
              }
        ),
      },
    };
    await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
    mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
    controllerTransitionHint = `location_saved:${declaredLocationRole || "pending_role"}`;
    api.logger.info(
      `[controller] Location pin saved during ${conversationControllerEntry.bookingStep} step routed through agent conversation=${conversationId} role=${declaredLocationRole || "pending"}`,
    );
  }
  if (
    senderRole === "customer" &&
    replyTarget &&
    (
      interpretedCustomerTurn?.action === "passenger_transport_request" ||
      currentCustomerIntent === "passenger_transport_request"
    )
  ) {
    if (conversationControllerEntry) {
      const hasActiveQuote = !!conversationControllerEntry.quoteRouteKey && conversationControllerEntry.stage === "quoted";
      conversationControllerEntry = {
        ...conversationControllerEntry,
        stage: hasActiveQuote ? "quoted" : "idle",
        bookingStep: "none",
        bookingDraft: createEmptyBookingDraft(),
        pendingReplyText: null,
        ...(hasActiveQuote
          ? {}
          : {
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
            }),
      };
      await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
    }
    api.logger.info(
      `[controller] passenger transport request routed through agent conversation=${conversationId} lang=${preferredReplyLanguage}`,
    );
  }
  if (
    senderRole === "customer" &&
    replyTarget &&
    conversationControllerEntry &&
    interpretedCustomerTurn?.action === "cancel_booking" &&
    (
      conversationControllerEntry.stage === "collecting_booking_details" ||
      conversationControllerEntry.stage === "summary_shown" ||
      conversationControllerEntry.stage === "awaiting_confirmation"
    )
  ) {
    const prevStage = conversationControllerEntry.stage;
    conversationControllerEntry = {
      ...conversationControllerEntry,
      stage: "idle",
      bookingStep: "none",
      bookingDraft: createEmptyBookingDraft(),
      pendingReplyText: null,
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
    };
    await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
    mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
    controllerTransitionHint = "booking_cancelled";
    api.logger.info(
      `[controller] booking cancelled by customer routed through agent conversation=${conversationId} prevStage=${prevStage}`,
    );
  }
  if (
    senderRole === "customer" &&
    replyTarget &&
    conversationControllerEntry &&
    (
      conversationControllerEntry.stage === "summary_shown" ||
      conversationControllerEntry.stage === "awaiting_confirmation" ||
      conversationControllerEntry.bookingStep === "summary_pending" ||
      conversationControllerEntry.bookingStep === "awaiting_summary_confirmation"
    ) &&
    turnSignals.workflowInputText &&
    isSummaryEditRequest(turnSignals.workflowInputText) &&
    interpretedCustomerTurn?.action !== "correct_booking_field" &&
    interpretedCustomerTurn?.action !== "pricing_request" &&
    interpretedCustomerTurn?.action !== "cancel_booking"
  ) {
    conversationControllerEntry = {
      ...conversationControllerEntry,
      stage: conversationControllerEntry.stage === "summary_shown"
        ? "awaiting_confirmation"
        : conversationControllerEntry.stage,
      bookingStep:
        conversationControllerEntry.bookingStep === "summary_pending"
          ? "awaiting_summary_confirmation"
          : conversationControllerEntry.bookingStep,
    };
    controllerTransitionHint = "summary_edit_request";
    api.logger.info(
      `[controller] summary edit clarification routed through agent conversation=${conversationId} lang=${preferredReplyLanguage}`,
    );
  }
  if (conversationControllerEntry) {
    conversationControllerEntry = {
      ...conversationControllerEntry,
      lastActivityTs: Date.now(),
      language: preferredReplyLanguage,
      explicitLanguage: explicitLanguageRequest || conversationControllerEntry.explicitLanguage,
      conversationId,
      replyTarget,
      accountId: account.accountId,
    };
  }
  const storePath = api.runtime.channel.session.resolveStorePath(api.config.session?.store);
  const senderId = replyTarget || conversationId;
  const customerProfile = senderRole === "customer" && replyTarget ? await loadCustomerProfile(replyTarget) : null;
  let sameRouteQuoteAction: SameRouteQuoteFollowupAction = null;
  if (conversationControllerEntry && activeQuotedRoute) {
    const syncedSelection = syncControllerSelectionFromQuotedRoute(conversationControllerEntry, activeQuotedRoute);
    if (syncedSelection.changed && syncedSelection.entry) {
      conversationControllerEntry = syncedSelection.entry;
      mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
    }
  }
  if (
    senderRole === "customer" &&
    conversationControllerEntry &&
    hasActiveQuotedBookingAuthority(conversationControllerEntry) &&
    activeQuotedRoute &&
    turnSignals.workflowInputText
  ) {
    sameRouteQuoteAction =
      resolveSameRouteQuoteActionFromInterpreter({
        interpretedTurn: interpretedCustomerTurn,
        controllerEntry: conversationControllerEntry,
        route: activeQuotedRoute,
      }) ||
      resolveSameRouteQuoteFollowupAction({
        visibleText: turnSignals.workflowInputText,
        controllerEntry: conversationControllerEntry,
        route: activeQuotedRoute,
      });
    if (
      sameRouteQuoteAction &&
      (sameRouteQuoteAction.kind === "switch_option" || sameRouteQuoteAction.kind === "confirm_selected_option")
    ) {
      conversationControllerEntry = applySelectedQuotedOptionToController(
        conversationControllerEntry,
        sameRouteQuoteAction.option,
      );
      mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
      api.logger.info(
        `[controller] same-route quote selection updated conversation=${conversationId} action=${sameRouteQuoteAction.kind} option=${sameRouteQuoteAction.option.delivery_type} price=${formatQuotedOptionPrice(sameRouteQuoteAction.option)}`,
      );
    }
  }
  const quoteFollowupHint =
    sameRouteQuoteAction?.kind === "switch_option"
      ? `switch_option:${sameRouteQuoteAction.option.delivery_type}`
      : sameRouteQuoteAction?.kind === "confirm_selected_option"
        ? `confirm_selected_option:${sameRouteQuoteAction.option.delivery_type}`
        : sameRouteQuoteAction?.kind === "show_other_options"
          ? "show_other_options"
          : null;
  const quotedStagePreDispatch =
    senderRole === "customer" &&
    conversationControllerEntry &&
    conversationControllerEntry.stage === "quoted" &&
    conversationControllerEntry.quotePresentedToCustomer !== false &&
    hasActiveQuotedBookingAuthority(conversationControllerEntry) &&
    activeQuotedRoute;
  const interpreterSaidStartBooking = interpretedCustomerTurn?.action === "start_booking";
  const safetyNetMatched = Boolean(
    turnSignals.workflowInputText && isBookingStartIntent(turnSignals.workflowInputText),
  );
  if (quotedStagePreDispatch) {
    api.logger.info(
      `[controller] quoted-stage turn conversation=${conversationId} interpreter_action=${interpretedCustomerTurn?.action || "na"} interpreter_start_booking=${interpreterSaidStartBooking ? "yes" : "no"} safety_net_matched=${safetyNetMatched ? "yes" : "no"} selected_delivery_type=${interpretedCustomerTurn?.selected_delivery_type || "na"}`,
    );
  }
  if (quotedStagePreDispatch && (interpreterSaidStartBooking || safetyNetMatched)) {
    const requestedStartBookingOption =
      interpretedCustomerTurn?.action === "start_booking" && interpretedCustomerTurn.selected_delivery_type
        ? getQuotedRouteOption(activeQuotedRoute, interpretedCustomerTurn.selected_delivery_type)
        : null;
    const selectedQuotedOption =
      requestedStartBookingOption ||
      getQuotedRouteOption(activeQuotedRoute, conversationControllerEntry.selectedQuoteOptionType) ||
      getQuotedRouteOption(activeQuotedRoute, conversationControllerEntry.selectedDeliveryType) ||
      getActiveSelectedQuotedOption(activeQuotedRoute, conversationControllerEntry);
    if (
      !selectedQuotedOption?.direct_chat_booking_status ||
      selectedQuotedOption.direct_chat_booking_status === "verified"
    ) {
      const selectedQuotedPrice =
        selectedQuotedOption && typeof selectedQuotedOption.quoted_price === "number"
          ? selectedQuotedOption.quoted_price
          : conversationControllerEntry.quotedPrice;
      const bookingStateEntry: PersistedConversationControllerEntry = {
        ...conversationControllerEntry,
        stage: "collecting_booking_details",
        bookingStep: resolveNextBookingStepFromDraft(conversationControllerEntry.bookingDraft),
        selectedDeliveryType: conversationControllerEntry.selectedDeliveryType,
        quotedPrice: selectedQuotedPrice,
        bookingDraft: {
          ...createEmptyBookingDraft(),
          ...conversationControllerEntry.bookingDraft,
        },
        language: preferredReplyLanguage,
      };
      conversationControllerEntry = selectedQuotedOption
        ? applySelectedQuotedOptionToController(bookingStateEntry, selectedQuotedOption)
        : bookingStateEntry;
      conversationControllerEntry = applyBookingDraftProgress(conversationControllerEntry);
      controllerTransitionHint = `booking_started:${conversationControllerEntry.bookingStep}`;
      api.logger.info(
        `[controller] pre-dispatch quoted conversation transitioned to booking-details stage language=${preferredReplyLanguage} conversation=${conversationId}`,
      );
    }
  }

  // Phase-3 deterministic fast-path extraction (ONE-BRAIN only).
  //
  // When the controller has an unambiguous next_required_action (e.g.
  // ASK_PICKUP_ADDRESS) and the customer's message has a clean deterministic
  // parse (e.g. "5, 7, 19" → block/street/house), we apply the patch to the
  // draft BEFORE the LLM runs. The system snapshot below will then reflect
  // the updated draft, the next_required_action advances naturally, and the
  // LLM's job collapses to writing a natural reply asking for the next
  // missing field. This kills "digit transposition", "wrong address_role",
  // and "lost leading 9" classes of LLM extraction drift.
  //
  // The extractor is step-constrained and high-confidence-only: it returns
  // nothing when the parse is ambiguous, so false positives are rare.
  let fastPathPreApplied: string[] = [];
  if (
    senderRole === "customer" &&
    isOneBrainConversation(replyTarget) &&
    conversationControllerEntry &&
    rawBody
  ) {
    try {
      const draft = conversationControllerEntry.bookingDraft;
      const missing = computeOneBrainMissingFields(draft, conversationControllerEntry);
      const directive = computeOneBrainNextRequiredAction({
        draft,
        entry: conversationControllerEntry,
        missing,
      });
      if (directive) {
        const fastResult = extractForNextAction({
          text: rawBody,
          action: directive.action as FastPathAction,
          whatsappNumber: replyTarget,
        });
        if (fastResult.confidence === "high" && fastResult.patch) {
          const applyRes = applyBookingFieldPatch({
            draft,
            patch: fastResult.patch,
            whatsappNumber: replyTarget,
          });
          if (applyRes.applied.length > 0) {
            conversationControllerEntry = {
              ...conversationControllerEntry,
              bookingDraft: applyRes.draft,
            };
            conversationControllerEntry = applyBookingDraftProgress(conversationControllerEntry);
            // Persist the pre-applied fields immediately so a retry / race
            // can't clobber them. The upsert at the end of the turn will
            // re-persist with any further LLM-driven updates on top.
            await upsertConversationControllerEntry(
              controllerStateKey,
              conversationControllerEntry,
            ).catch(() => {});
            mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
            fastPathPreApplied = applyRes.applied;
            api.logger.info(
              `[one-brain/fast-path] pre-applied action=${directive.action} fields=${applyRes.applied.join(",")} reasons=${fastResult.reasons.join(",")} rejected=${applyRes.rejected.length} conversation=${conversationId}`,
            );
          }
        } else if (fastResult.confidence === "none" && fastResult.reasons.length > 0) {
          // Log-only for future tuning. Never swallow.
          api.logger.debug?.(
            `[one-brain/fast-path] skip action=${directive.action} reasons=${fastResult.reasons.join(",")} conversation=${conversationId}`,
          );
        }
      }
    } catch (fastPathError) {
      // Never let extraction errors break the turn. The LLM will handle the
      // message normally and whatever drift we'd have caught gets caught by
      // later guards instead.
      api.logger.warn(
        `[one-brain/fast-path] extraction failed conversation=${conversationId} error=${
          fastPathError instanceof Error ? fastPathError.message : String(fastPathError)
        }`,
      );
    }
  }

  const channelContext = formatLiveChannelContext(senderRole, replyTarget, {
    isOneBrain: isOneBrainConversation(replyTarget),
    currentIntent: currentCustomerIntent,
    interpretedTurn: interpretedCustomerTurn,
    preferredReplyLanguage,
    conversationStage: conversationControllerEntry?.stage ?? null,
    bookingStep: conversationControllerEntry?.bookingStep ?? null,
    controllerEntry: conversationControllerEntry,
    quotedRoute: activeQuotedRoute,
    quoteFollowupHint,
    controllerTransitionHint,
  });
  const customerProfileContext = senderRole === "customer" ? formatCustomerProfileContext(customerProfile) : null;
  const behaviorContext = senderRole === "customer"
    ? await loadBehaviorPolicyContext(account, api.logger, {
        currentIntent: currentCustomerIntent,
      })
    : null;
  if (senderRole === "customer" && isOneBrainConversation(replyTarget)) {
    try {
      api.logger.info(
        `[one-brain] turn-snapshot conversation=${conversationId} chars=${channelContext.length}\n${channelContext}`,
      );
    } catch {}
  }
  // Share the raw customer text with riders-tools plugin for pre-resolution.
  // Keyed by conversationId so concurrent conversations don't cross-contaminate.
  // Entries carry a timestamp and are pruned after 5 minutes to prevent leaks.
  const _customerTextStore = ((globalThis as any).__ridersLastCustomerText ??= {
    entries: new Map<string, { text: string; ts: number }>(),
    lastConversationId: "",
  });
  if (senderRole === "customer" && rawBody) {
    const cid = String(conversationId);
    _customerTextStore.entries.set(cid, { text: rawBody, ts: Date.now() });
    _customerTextStore.lastConversationId = cid;
    // Prune stale entries (>5 min) — runs inline, O(n) but n is tiny
    const staleThreshold = Date.now() - 5 * 60_000;
    for (const [k, v] of _customerTextStore.entries) {
      if (v.ts < staleThreshold) _customerTextStore.entries.delete(k);
    }
  }

  const ctxPayload = api.runtime.channel.reply.finalizeInboundContext({
    Body: rawBody,
    BodyForAgent: rawBody,
    RawBody: rawBody,
    CommandBody: rawBody,
    From: replyTarget ? `octopus:${replyTarget}` : `octopus:conversation:${conversationId}`,
    To: `octopus:${conversationId}`,
    SessionKey: sessionKey,
    AgentId: resolvedAgentId,
    AccountId: account.accountId,
    ChatType: "direct",
    ConversationLabel: replyTarget ? `${senderRole}:${replyTarget}` : `${senderRole}:conversation:${conversationId}`,
    SenderName: replyTarget || undefined,
    SenderId: senderId,
    CommandAuthorized: true,
    Provider: PROVIDER_NAME,
    Surface: PROVIDER_NAME,
    MessageSid: messageId || undefined,
    MessageSidFull: messageId || undefined,
    MediaPath: mediaPath,
    MediaType: mediaType,
    MediaUrl: mediaPath,
    NativeChannelId: conversationId,
    OriginatingChannel: PROVIDER_NAME,
    OriginatingTo: `octopus:${conversationId}`,
    ControllerStateKey: controllerStateKey,
    CustomerIntentHint: currentCustomerIntent || undefined,
    CustomerTurnActionHint: interpretedCustomerTurn?.action || undefined,
    CustomerTurnActionConfidenceHint: interpretedCustomerTurn?.confidence || undefined,
    ConversationStageHint: conversationControllerEntry?.stage || undefined,
    BookingStepHint: conversationControllerEntry?.bookingStep || undefined,
    PreferredReplyLanguage: preferredReplyLanguage,
    PreferredReplyLanguageHint: preferredReplyLanguage,
    ExplicitLanguageHint: explicitLanguageRequest || undefined,
    UntrustedContext: [channelContext, customerProfileContext, behaviorContext, locationPinContext].filter(Boolean),
    Metadata: payload,
  });
  await api.runtime.channel.session.recordInboundSession({
    storePath,
    sessionKey: ctxPayload.SessionKey ?? sessionKey,
    ctx: ctxPayload,
    onRecordError: (error: unknown) => {
      api.logger.error(`[octopus] failed updating session meta: ${String(error)}`);
    },
  });
  const typingLoop = startTypingLoop({
    account,
    conversationId,
    messageId,
    logger: api.logger,
  });
  api.logger.info(
    `[octopus] inbound routed account=${account.accountId} conversation=${conversationId} agent=${resolvedAgentId} senderRole=${senderRole} replyTarget=${replyTarget || ""} intent=${currentCustomerIntent || "na"} stage=${conversationControllerEntry?.stage || "na"} promptSessionRevision=${promptSessionRevision || "na"}`,
  );
  if (
    isGreetingTurn &&
    senderRole === "customer" &&
    replyTarget &&
    !controllerTransitionHint &&
    !isOneBrainConversation(replyTarget) &&
    (!conversationControllerEntry || conversationControllerEntry.stage === "idle" || conversationControllerEntry.stage === "quoted")
  ) {
    typingLoop.stop();
    const greetingText = buildDeterministicGreetingReply(preferredReplyLanguage);
    await sendOctopusTextReply({
      api,
      account,
      conversationId,
      replyTarget,
      text: greetingText,
      source: "deterministic_greeting",
      ingressIds,
    });
    api.logger.info(
      `[octopus] deterministic greeting sent conversation=${conversationId} lang=${preferredReplyLanguage}`,
    );
    return;
  }
  try {
    await api.runtime.channel.reply.dispatchReplyWithBufferedBlockDispatcher({
      ctx: ctxPayload,
      cfg: api.config,
      dispatcherOptions: {
        deliver: async (payload: any) => {
          let replyText = asTrimmedString(payload?.text);
          if (!replyTarget) {
            return;
          }
          let controllerReplyLogKind: "booking_details" | "location_clarification" | null = null;
          // ONE-BRAIN mode: simplified drain. One LLM per turn owns all reply
          // copy; we only merge booking patches into the draft, reset on cancel,
          // and flag handoff. No stage/step/hint threading, no deterministic
          // summary override — the LLM writes the summary itself when ready.
          if (isOneBrainConversation(replyTarget) && senderRole === "customer") {
            try {
              const drained = drainResponderStateOps(conversationId);
              if (drained.length > 0) {
                let nextDraft = conversationControllerEntry?.bookingDraft || createEmptyBookingDraft();
                let cancelled = false;
                let handoffRequested = false;
                const rejections: Array<{ field: string; reason: string; received: string }> = [];
                const appliedOps: string[] = [];
                for (const op of drained) {
                  if (op.op === "apply_booking_field") {
                    const patch: BookingFieldPatch = {
                      sender_name: op.sender_name ?? null,
                      sender_phone: op.sender_phone ?? null,
                      phone_decision: (op.phone_decision as any) ?? null,
                      recipient_name: op.recipient_name ?? null,
                      recipient_phone: op.recipient_phone ?? null,
                      address_block: op.address_block ?? null,
                      address_street: op.address_street ?? null,
                      address_house: op.address_house ?? null,
                      address_avenue: op.address_avenue ?? null,
                      address_extra: op.address_extra ?? null,
                      address_role: (op.address_role as any) ?? null,
                    };
                    const result = applyBookingFieldPatch({
                      draft: nextDraft,
                      patch,
                      whatsappNumber: replyTarget,
                    });
                    nextDraft = result.draft;
                    for (const r of result.rejected) {
                      rejections.push({ field: r.field, reason: r.reason, received: r.received });
                    }
                    appliedOps.push(`apply_booking_field(${result.applied.join(",")})`);
                  } else if (op.op === "cancel_booking") {
                    cancelled = true;
                    appliedOps.push("cancel_booking");
                  } else if (op.op === "request_handoff") {
                    handoffRequested = true;
                    appliedOps.push("request_handoff");
                  } else if (op.op === "start_booking" || op.op === "confirm_summary") {
                    // One-brain ignores these — `apply_booking_field` and
                    // `create_simple_order` are the only signals we care about.
                    appliedOps.push(`${op.op}:ignored`);
                  }
                }
                if (conversationControllerEntry) {
                  const appliedBookingPatch = drained.some(
                    (op) => op.op === "apply_booking_field",
                  );
                  let nextEntry: PersistedConversationControllerEntry = cancelled
                    ? {
                        ...conversationControllerEntry,
                        bookingDraft: createEmptyBookingDraft(),
                        pendingReplyText: null,
                        stage: "idle",
                        bookingStep: "none",
                      }
                    : {
                        ...conversationControllerEntry,
                        bookingDraft: nextDraft,
                      };
                  // ONE-BRAIN: after any apply_booking_field patch, re-derive
                  // bookingStep + stage from the current draft so the system
                  // prompt surfaces the correct step-hint (e.g. "all fields
                  // confirmed → write summary") instead of a frozen earlier
                  // step. Without this, bookingStep stays "sender" forever and
                  // the agent gets contradictory hints on the summary turn.
                  if (!cancelled && appliedBookingPatch) {
                    nextEntry = applyBookingDraftProgress(nextEntry);
                  }
                  conversationControllerEntry = nextEntry;
                  await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
                  mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
                }
                try {
                  api.logger.info(
                    `[one-brain] drained conversation=${conversationId} ops=${drained.length} applied=${appliedOps.join("|")} cancelled=${cancelled ? "yes" : "no"} handoff=${handoffRequested ? "yes" : "no"} rejections=${rejections.length}`,
                  );
                  if (rejections.length > 0) {
                    api.logger.warn(
                      `[one-brain] field rejections conversation=${conversationId} ${JSON.stringify(rejections)}`,
                    );
                  }
                } catch {}
              }
            } catch (error) {
              api.logger.warn(
                `[one-brain] drain failed conversation=${conversationId} error=${(error as Error)?.message || String(error)}`,
              );
            }
          } else if (RESPONDER_FIRST_FLAG && senderRole === "customer") {
            // Responder-first (legacy) mode: drain state ops pushed by tools during this turn
            // and apply them through the validated server-side helpers. This is the
            // single authoritative path for controller mutations when the flag is ON.
            try {
              const drained = drainResponderStateOps(conversationId);
              if (drained.length > 0) {
                const applyResult = applyResponderStateOps({
                  controllerEntry: conversationControllerEntry,
                  visibleText: turnSignals.workflowInputText || rawBody || "",
                  replyTarget,
                  ops: drained,
                });
                conversationControllerEntry = applyResult.controllerEntry;
                if (conversationControllerEntry) {
                  await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
                  mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
                }
                if (applyResult.cancelled && conversationControllerEntry) {
                  const prevStage = conversationControllerEntry.stage;
                  conversationControllerEntry = {
                    ...conversationControllerEntry,
                    stage: "idle",
                    bookingStep: "none",
                    bookingDraft: createEmptyBookingDraft(),
                    pendingReplyText: null,
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
                  };
                  await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
                  mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
                  controllerTransitionHint = "booking_cancelled";
                  api.logger.info(
                    `[controller] booking cancelled via responder op conversation=${conversationId} prevStage=${prevStage}`,
                  );
                } else if (applyResult.summaryReady) {
                  controllerTransitionHint = "summary_ready";
                } else if (applyResult.corrections.ambiguous > 0 && !applyResult.summaryReady) {
                  controllerTransitionHint = "correction_ambiguous_address";
                }
                // If confirm_summary was rejected because the draft has malformed
                // fields, OVERRIDE the outgoing reply with a deterministic ask for
                // the specific fields. This prevents the LLM from placing a bad
                // order and gives the customer a clear, correct next step.
                if (applyResult.draftSanityProblems.length > 0) {
                  const problems = applyResult.draftSanityProblems;
                  const fieldList = problems
                    .map((p) => `${p.field}:${p.reason}`)
                    .join(",");
                  controllerTransitionHint = `draft_sanity_problems:${fieldList}`;
                  const askFields = Array.from(
                    new Set(problems.map((p) => p.field)),
                  );
                  const askLabel = (f: string): string => {
                    const map: Record<string, string> = {
                      sender_name: "sender full name",
                      sender_phone: "sender phone (digits only)",
                      recipient_name: "recipient full name",
                      recipient_phone: "recipient phone (digits only)",
                      pickup_block: "pickup block",
                      pickup_street: "pickup street",
                      pickup_house: "pickup house number",
                      delivery_block: "delivery block",
                      delivery_street: "delivery street",
                      delivery_house: "delivery house number",
                    };
                    return map[f] || f;
                  };
                  const askText =
                    `Before I place the order, I need to re-confirm the following because the saved values don't look right: ` +
                    askFields.map(askLabel).join(", ") +
                    `. Please resend just those values cleanly.`;
                  replyText = askText;
                  payload.text = askText;
                  api.logger.warn(
                    `[responder-ops] confirm_summary rejected for draft_sanity conversation=${conversationId} problems=${fieldList}`,
                  );
                } else if (applyResult.validationRejections.length > 0) {
                  const fieldList = applyResult.validationRejections
                    .map((r) => `${r.field}:${r.reason}`)
                    .join(",");
                  controllerTransitionHint = `validation_rejected:${fieldList}`;
                }
                try {
                  api.logger.info(
                    `[responder-ops] applied conversation=${conversationId} ops=${drained.length} outcomes=${JSON.stringify(applyResult.applied)} summary_ready=${applyResult.summaryReady ? "yes" : "no"} cancelled=${applyResult.cancelled ? "yes" : "no"} handoff=${applyResult.handoffRequested ? "yes" : "no"} validation_rejections=${applyResult.validationRejections.length} draft_problems=${applyResult.draftSanityProblems.length}`,
                  );
                } catch {}
              }
            } catch (error) {
              api.logger.warn(
                `[responder-ops] failed to apply conversation=${conversationId} error=${(error as Error)?.message || String(error)}`,
              );
            }
          }
          // --- Price guard: validate outbound prices against get_price results ---
          const guardState = (globalThis as any).__ridersGuardState as
            | {
                sessionState: Map<string, {
                  allValidPrices: Set<string>;
                  lastToolTs: number;
                  lastCustomerMessage: string | null;
                  lastCustomerMessages: { ar: string | null; en: string | null };
                  lastToolName: string | null;
                  pendingOrderSummary: { fingerprint: string; createdAt: number } | null;
                  lastQuotedRoute: (StoredQuotedRoute & {
                    quotedAt: number;
                    quoteRef: string;
                  }) | null;
                  lastCreatedOrderUid?: string | null;
                }>;
                extractPricesFromText: (text: string) => string[];
              }
            | undefined;
          let sessionGuard:
            | {
                allValidPrices: Set<string>;
                lastToolTs: number;
                lastCustomerMessage: string | null;
                lastCustomerMessages: { ar: string | null; en: string | null };
                lastToolName: string | null;
                pendingOrderSummary: { fingerprint: string; createdAt: number } | null;
                lastQuotedRoute: (StoredQuotedRoute & {
                  quotedAt: number;
                  quoteRef: string;
                }) | null;
                lastCreatedOrderUid?: string | null;
              }
            | null = null;
          const activeSessionKey = resolveSessionIdentityKey(ctxPayload);
          let sessionIsRecent = false;
          let guardSessionKey = activeSessionKey;
          let preferredCanonicalText: string | null = null;
          {
            const guardEntry = await findSessionGuardEntryWithPersistence(guardState?.sessionState, {
              activeSessionKey,
              conversationId,
              replyTarget,
            });
            guardSessionKey = guardEntry.key || activeSessionKey;
            sessionGuard = guardEntry.session || null;
            sessionIsRecent = !!sessionGuard && (Date.now() - sessionGuard.lastToolTs) < 300_000;
            if (!sessionGuard) {
              api.logger.info(
                `[guard] No session state found conversation=${conversationId} sessionKey=${activeSessionKey} intent=${currentCustomerIntent || "na"}`,
              );
            }
            preferredCanonicalText =
              preferredReplyLanguage === "ar"
                ? (sessionGuard?.lastCustomerMessages?.ar || sessionGuard?.lastCustomerMessage || null)
                : (sessionGuard?.lastCustomerMessages?.en || sessionGuard?.lastCustomerMessage || null);
            const shouldSkipCanonicalPriceGuard = Boolean(
              activeQuotedRoute && sameRouteQuoteAction,
            );
            if (replyText && sessionGuard && sessionIsRecent && !shouldSkipCanonicalPriceGuard && shouldPreferCanonicalToolReply({
              toolName: sessionGuard.lastToolName,
              replyText,
              canonicalText: preferredCanonicalText,
              preferredLanguage: preferredReplyLanguage,
              lastToolAgeMs: Math.max(0, Date.now() - sessionGuard.lastToolTs),
              extractPricesFromText: guardState.extractPricesFromText,
            })) {
              api.logger.info(
                `[guard] Replaced lossy ${String(sessionGuard.lastToolName)} reply with canonical tool message conversation=${conversationId} sessionKey=${guardSessionKey}`,
              );
              replyText = preferredCanonicalText || replyText;
            }
            if (!replyText && sessionGuard && sessionIsRecent && preferredCanonicalText) {
              api.logger.info(
                `[guard] Filled missing ${String(sessionGuard.lastToolName)} reply with canonical tool message conversation=${conversationId} sessionKey=${guardSessionKey}`,
              );
              replyText = preferredCanonicalText;
            }
            const quotedPrices = replyText ? guardState.extractPricesFromText(replyText) : [];
            if (quotedPrices.length > 0 && sessionGuard && sessionIsRecent && sessionGuard.allValidPrices.size > 0) {
              const validPrices = sessionGuard.allValidPrices;
              const hallucinated = quotedPrices.filter((p) => !validPrices.has(p));
              if (hallucinated.length > 0) {
                api.logger.warn(
                  `[guard] BLOCKED hallucinated prices [${hallucinated.join(", ")}] in outbound. Valid: [${[...validPrices].join(", ")}] conversation=${conversationId}`,
                );
                replyText = preferredCanonicalText ||
                  (preferredReplyLanguage === "ar"
                    ? "عذراً، حصل خطأ في التسعير. يرجى إعادة طلب السعر مرة ثانية وسنتحقق لكم."
                    : "Sorry, there was a pricing error. Please ask for the price again and we'll verify it for you.");
              }
            }
            if (
              activeQuotedRoute &&
              sameRouteQuoteAction &&
              sameRouteQuoteAction.kind === "switch_option"
            ) {
              const expectedOption = sameRouteQuoteAction.option;
              const expectedPrice =
                typeof expectedOption.quoted_price === "number" && Number.isFinite(expectedOption.quoted_price)
                  ? expectedOption.quoted_price.toFixed(3)
                  : null;
              const replyPrices = replyText ? guardState.extractPricesFromText(replyText) : [];
              const missingExpectedPrice =
                Boolean(expectedPrice) &&
                replyPrices.length > 0 &&
                !replyPrices.includes(String(expectedPrice));
              if (!replyText || missingExpectedPrice) {
                api.logger.warn(
                  `[guard] Replaced semantically wrong same-route quote reply conversation=${conversationId} action=${sameRouteQuoteAction.kind} option=${expectedOption.delivery_type} expectedPrice=${expectedPrice || "na"} replyPrices=${replyPrices.join(",") || "none"}`,
                );
                replyText = buildDeterministicSelectedQuotedOptionReply({
                  language: preferredReplyLanguage,
                  route: activeQuotedRoute,
                  option: expectedOption,
                });
              }
            }
          }
          if (conversationControllerEntry && sessionGuard && sessionIsRecent) {
            if (
              sessionGuard.lastToolName === "get_price" &&
              sessionGuard.lastQuotedRoute &&
              sessionGuard.lastToolTs !== conversationControllerEntry.quoteTs
            ) {
              const replyContainsPrice = replyText
                ? (guardState?.extractPricesFromText(replyText) || []).some((p) =>
                    sessionGuard.allValidPrices.has(p),
                  )
                : false;
              const quotedStateEntry: PersistedConversationControllerEntry = {
                ...conversationControllerEntry,
                stage: "quoted",
                bookingStep: "none",
                language: preferredReplyLanguage,
                quoteTs: sessionGuard.lastToolTs,
                quoteRouteKey: sessionGuard.lastQuotedRoute.routeKey,
                quotePickupAreaNameEn: sessionGuard.lastQuotedRoute.pickupAreaNameEn,
                quotePickupAreaNameAr: sessionGuard.lastQuotedRoute.pickupAreaNameAr,
                quoteDropoffAreaNameEn: sessionGuard.lastQuotedRoute.dropoffAreaNameEn,
                quoteDropoffAreaNameAr: sessionGuard.lastQuotedRoute.dropoffAreaNameAr,
                bookingDraft: createEmptyBookingDraft(),
                quotePresentedToCustomer: replyContainsPrice,
                submittedOrderUid: null,
              };
              conversationControllerEntry = applySelectedQuotedOptionToController(
                quotedStateEntry,
                getQuotedRouteDefaultOption(sessionGuard.lastQuotedRoute),
              );
              if (!replyContainsPrice) {
                api.logger.info(
                  `[controller] quote not yet presented to customer (clarification pending) conversation=${conversationId}`,
                );
              }
            } else if (sessionGuard.lastToolName === "create_simple_order") {
              const submittedOrderUid =
                (sessionGuard.lastCreatedOrderUid && String(sessionGuard.lastCreatedOrderUid).trim()) ||
                conversationControllerEntry.submittedOrderUid ||
                null;
              conversationControllerEntry = {
                ...conversationControllerEntry,
                stage: "order_submitted",
                bookingStep: "none",
                quoteTs: null,
                quoteRouteKey: null,
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
                pendingReplyText: null,
                submittedOrderUid,
              };
              if (submittedOrderUid) {
                api.logger.info(
                  `[post-order] stage=order_submitted uid=${submittedOrderUid} conversation=${conversationId}`,
                );
              }
            } else if (sessionGuard.lastToolName === "track_order") {
              conversationControllerEntry = clearAutomatedConversationContext({
                ...conversationControllerEntry,
              });
            }
          }
          if (
            conversationControllerEntry &&
            conversationControllerEntry.stage === "quoted" &&
            conversationControllerEntry.quotePresentedToCustomer === false &&
            replyText &&
            guardState
          ) {
            const outboundPrices = guardState.extractPricesFromText(replyText);
            if (outboundPrices.length > 0 && sessionGuard && outboundPrices.some((p) => sessionGuard.allValidPrices.has(p))) {
              conversationControllerEntry = {
                ...conversationControllerEntry,
                quotePresentedToCustomer: true,
              };
              api.logger.info(
                `[controller] quote now presented to customer conversation=${conversationId}`,
              );
            }
          }
          let handledByConversationController = false;
          if (
            !handledByConversationController &&
            conversationControllerEntry &&
            conversationControllerEntry.stage === "quoted" &&
            conversationControllerEntry.quotePresentedToCustomer !== false &&
            hasActiveQuotedBookingAuthority(conversationControllerEntry) &&
            (
              interpretedCustomerTurn?.action === "start_booking" ||
              (
                turnSignals.workflowInputText &&
                isBookingStartIntent(turnSignals.workflowInputText)
              )
            )
          ) {
            const latestQuotedRoute =
              sessionGuard?.lastToolName === "get_price" && sessionGuard.lastQuotedRoute
                ? sessionGuard.lastQuotedRoute
                : null;
            const effectiveQuotedRoute = latestQuotedRoute || activeQuotedRoute;
            const requestedStartBookingOption =
              interpretedCustomerTurn?.action === "start_booking" && interpretedCustomerTurn.selected_delivery_type
                ? getQuotedRouteOption(effectiveQuotedRoute, interpretedCustomerTurn.selected_delivery_type)
                : null;
            const selectedQuotedOption =
              requestedStartBookingOption ||
              getQuotedRouteOption(effectiveQuotedRoute, conversationControllerEntry.selectedQuoteOptionType) ||
              getQuotedRouteOption(effectiveQuotedRoute, conversationControllerEntry.selectedDeliveryType) ||
              getActiveSelectedQuotedOption(effectiveQuotedRoute, conversationControllerEntry);
            if (
              effectiveQuotedRoute &&
              selectedQuotedOption?.direct_chat_booking_status &&
              selectedQuotedOption.direct_chat_booking_status !== "verified"
            ) {
              conversationControllerEntry = applySelectedQuotedOptionToController(
                conversationControllerEntry,
                selectedQuotedOption,
              );
              replyText = buildDeterministicSelectedQuotedOptionReply({
                language: preferredReplyLanguage,
                route: effectiveQuotedRoute,
                option: selectedQuotedOption,
              });
              handledByConversationController = true;
              api.logger.info(
                `[controller] blocked booking transition for non-direct-bookable option conversation=${conversationId} deliveryType=${selectedQuotedOption.delivery_type} status=${selectedQuotedOption.direct_chat_booking_status}`,
              );
            }
            if (!handledByConversationController) {
              api.logger.info(
                `[controller] Transitioned quoted conversation to booking-details stage language=${preferredReplyLanguage} conversation=${conversationId}`,
              );
              const selectedQuotedPrice =
                selectedQuotedOption && typeof selectedQuotedOption.quoted_price === "number"
                  ? selectedQuotedOption.quoted_price
                  : conversationControllerEntry.quotedPrice;
              const bookingStateEntry: PersistedConversationControllerEntry = {
                ...conversationControllerEntry,
                stage: "collecting_booking_details",
                bookingStep: resolveNextBookingStepFromDraft(conversationControllerEntry.bookingDraft),
                quoteTs: latestQuotedRoute ? sessionGuard?.lastToolTs || conversationControllerEntry.quoteTs : conversationControllerEntry.quoteTs,
                quoteRouteKey: latestQuotedRoute?.routeKey || conversationControllerEntry.quoteRouteKey,
                quotePickupAreaNameEn: latestQuotedRoute?.pickupAreaNameEn || conversationControllerEntry.quotePickupAreaNameEn,
                quotePickupAreaNameAr: latestQuotedRoute?.pickupAreaNameAr || conversationControllerEntry.quotePickupAreaNameAr,
                quoteDropoffAreaNameEn: latestQuotedRoute?.dropoffAreaNameEn || conversationControllerEntry.quoteDropoffAreaNameEn,
                quoteDropoffAreaNameAr: latestQuotedRoute?.dropoffAreaNameAr || conversationControllerEntry.quoteDropoffAreaNameAr,
                selectedDeliveryType: conversationControllerEntry.selectedDeliveryType,
                quotedPrice: selectedQuotedPrice,
                bookingDraft: {
                  ...createEmptyBookingDraft(),
                  ...conversationControllerEntry.bookingDraft,
                },
                language: preferredReplyLanguage,
              };
              conversationControllerEntry = selectedQuotedOption
                ? applySelectedQuotedOptionToController(bookingStateEntry, selectedQuotedOption)
                : bookingStateEntry;
              conversationControllerEntry = applyBookingDraftProgress(conversationControllerEntry);
              controllerReplyLogKind = "booking_details";
              controllerTransitionHint = `booking_started:${conversationControllerEntry.bookingStep}`;
            }
          }
          const postLlmBookingBlockedActions = new Set([
            "greeting",
            "language_switch",
            "service_overview",
            "pricing_request",
            "tracking_request",
            "tracking_missing_id",
            "passenger_transport_request",
            "handoff",
          ]);
          // LLM reply trusted for booking steps — context hints guide it to the right step
          // Post-LLM location handling: auto-assignment state updates are done pre-dispatch;
          // the LLM receives location context and responds naturally
          if (controllerTransitionHint === "summary_edit_request" && !replyText) {
            replyText = preferredReplyLanguage === "ar"
              ? "أكيد. شنو الجزء اللي تبون نغيره بالضبط: المرسل، المستلم، الاستلام، التوصيل، الرقم، أو الخدمة؟"
              : "Sure. Which part should I change exactly: sender, recipient, pickup, delivery, phone, or service?";
          }
          if (controllerTransitionHint === "grace_window_offer" && !replyText) {
            replyText = buildDeterministicGraceWindowReply(preferredReplyLanguage);
          }
          // location_saved hint: LLM receives the hint and responds naturally
          // Language switch reissue: LLM receives the new language + booking step context and rephrases naturally
          if (
            (
              controllerTransitionHint === "summary_ready" ||
              controllerTransitionHint === "language_switch_reissue_summary"
            ) &&
            conversationControllerEntry &&
            !isOneBrainConversation(replyTarget)
          ) {
            replyText = buildDeterministicOrderSummaryReply(preferredReplyLanguage, conversationControllerEntry);
          }
          if (!replyText) {
            replyText = buildProviderIssueFallbackReply(preferredReplyLanguage);
            api.logger.warn(
              `[octopus] LLM produced empty reply, using fallback conversation=${conversationId}`,
            );
          }
          if (
            conversationControllerEntry &&
            !isOneBrainConversation(replyTarget) &&
            (
              conversationControllerEntry.stage === "summary_shown" ||
              conversationControllerEntry.stage === "awaiting_confirmation" ||
              conversationControllerEntry.bookingStep === "summary_pending" ||
              conversationControllerEntry.bookingStep === "awaiting_summary_confirmation"
            ) &&
            (
              controllerTransitionHint === "summary_ready" ||
              controllerTransitionHint === "language_switch_reissue_summary"
            )
          ) {
            replyText = buildDeterministicOrderSummaryReply(preferredReplyLanguage, conversationControllerEntry);
          }
          if (conversationControllerEntry) {
            const persistedEntry =
              conversationControllerEntry.stage === "summary_shown" ||
                conversationControllerEntry.bookingStep === "summary_pending"
                ? {
                    ...conversationControllerEntry,
                    stage: "awaiting_confirmation" as ConversationFlowStage,
                    bookingStep: "awaiting_summary_confirmation" as BookingCollectionStep,
                  }
                : conversationControllerEntry;
            if (guardState && conversationControllerEntry.bookingStep === "summary_pending") {
              const fingerprint = buildPendingOrderSummaryFingerprint(conversationControllerEntry);
              if (fingerprint) {
                const existingGuard = guardState.sessionState.get(activeSessionKey);
                const fallbackGuard = existingGuard || guardState.sessionState.get(guardSessionKey);
                if (fallbackGuard) {
                  fallbackGuard.pendingOrderSummary = {
                    fingerprint,
                    createdAt: Date.now(),
                  };
                }
              }
            }
            await upsertConversationControllerEntry(controllerStateKey, {
              ...persistedEntry,
              lastActivityTs: Date.now(),
              conversationId,
              replyTarget,
              accountId: account.accountId,
            });
            mirrorConversationControllerEntry(controllerStateKey, {
              ...persistedEntry,
              lastActivityTs: Date.now(),
              conversationId,
              replyTarget,
              accountId: account.accountId,
            });
          }
          if (controllerReplyLogKind === "booking_details" && conversationControllerEntry) {
            api.logger.info(
              `[controller] Deterministic booking-details reply sent conversation=${conversationId} lang=${preferredReplyLanguage} step=${conversationControllerEntry.bookingStep} text=${JSON.stringify(replyText)}`,
            );
          }

          // Phase-2 Output Verification Loop (ONE-BRAIN only).
          // Deterministic backstop that catches stub / route-recap replies
          // when the booking draft is complete, and substitutes a canonical
          // full summary built from the draft + quote. The LLM's next turn
          // then sees the real summary on the record.
          if (isOneBrainConversation(replyTarget) && conversationControllerEntry) {
            const missingForVerify = computeOneBrainMissingFields(
              conversationControllerEntry.bookingDraft,
              conversationControllerEntry,
            );
            const verification = verifyAndRepairOutbound({
              replyText,
              entry: conversationControllerEntry,
              missingFields: missingForVerify,
              language: preferredReplyLanguage,
            });
            if (verification.shape !== "ok" && verification.shape !== "empty") {
              api.logger.warn(
                `[one-brain/verify] outbound_shape=${verification.shape} replaced=${verification.replaced} reason=${verification.reason} conversation=${conversationId} original=${JSON.stringify(replyText).slice(0, 240)}`,
              );
            }
            if (verification.replaced) {
              replyText = verification.replyText;
              // Mark the summary as having been shown so downstream
              // confirmation detection and order-guard "summary_shown" gate
              // both work off the real event, not the stub.
              conversationControllerEntry = {
                ...conversationControllerEntry,
                stage: "summary_shown" as ConversationFlowStage,
                bookingStep: "summary_pending" as BookingCollectionStep,
              };
            }
          }
          const pendingPrefix = conversationControllerEntry?.pendingReplyText?.trim();
          const outboundText = pendingPrefix ? `${pendingPrefix}\n\n${replyText}` : replyText;
          try {
            await sendOctopusTextReply({
              api,
              account,
              conversationId,
              replyTarget,
              text: outboundText,
              preferredLanguage: preferredReplyLanguage,
              ingressIds,
            });
            if (pendingPrefix && conversationControllerEntry) {
              conversationControllerEntry = { ...conversationControllerEntry, pendingReplyText: null };
              await upsertConversationControllerEntry(controllerStateKey, {
                ...conversationControllerEntry,
                lastActivityTs: Date.now(),
                conversationId,
                replyTarget,
                accountId: account.accountId,
              }).catch(() => {});
              mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
              api.logger.info(
                `[controller] pending reply flushed with current reply conversation=${conversationId}`,
              );
            }
            // LLM-driven handoff: if GPT-5.4 classified intent as handoff, trigger the
            // handoff API regardless of whether the outbound reply matched escalation strings.
            // sendOctopusTextReply already handles string-match handoff; this covers the LLM path.
            if (
              interpretedCustomerTurn?.action === "handoff" &&
              !shouldMoveToHumanAgent(outboundText)
            ) {
              try {
                await aiOctopusRequest(account, "/client/conversation/toagent", {
                  conversation_id: conversationId,
                });
                api.logger.info(
                  `[controller] LLM-driven handoff triggered conversation=${conversationId}`,
                );
              } catch (handoffError) {
                api.logger.error(
                  `[controller] LLM-driven handoff failed conversation=${conversationId} error=${handoffError instanceof Error ? handoffError.message : String(handoffError)}`,
                );
              }
            }
            if (
              conversationControllerEntry &&
              (
                interpretedCustomerTurn?.action === "handoff" ||
                shouldMoveToHumanAgent(outboundText)
              )
            ) {
              conversationControllerEntry = clearAutomatedConversationContext({
                ...conversationControllerEntry,
                lastActivityTs: Date.now(),
              });
              await upsertConversationControllerEntry(controllerStateKey, {
                ...conversationControllerEntry,
                lastActivityTs: Date.now(),
                conversationId,
                replyTarget,
                accountId: account.accountId,
              }).catch(() => {});
              mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
              api.logger.info(
                `[controller] cleared automated state after handoff conversation=${conversationId}`,
              );
            }
          } catch (sendError) {
            if (conversationControllerEntry) {
              if (isAiOctopusConversationClosedError(sendError)) {
                conversationControllerEntry = clearAutomatedConversationContext({
                  ...conversationControllerEntry,
                  lastActivityTs: Date.now(),
                });
                await upsertConversationControllerEntry(controllerStateKey, {
                  ...conversationControllerEntry,
                  lastActivityTs: Date.now(),
                  conversationId,
                  replyTarget,
                  accountId: account.accountId,
                }).catch(() => {});
                mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
                api.logger.error(
                  `[controller] reply send failed on closed conversation; cleared automated state instead of queuing pending reply conversation=${conversationId} error=${sendError instanceof Error ? sendError.message : String(sendError)}`,
                );
              } else {
                conversationControllerEntry = { ...conversationControllerEntry, pendingReplyText: outboundText };
                await upsertConversationControllerEntry(controllerStateKey, {
                  ...conversationControllerEntry,
                  lastActivityTs: Date.now(),
                  conversationId,
                  replyTarget,
                  accountId: account.accountId,
                }).catch(() => {});
                mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
                api.logger.error(
                  `[controller] reply send failed, queued as pending conversation=${conversationId} error=${sendError instanceof Error ? sendError.message : String(sendError)}`,
                );
              }
            }
            throw sendError;
          }
        },
        onError: (error: unknown, info: { kind: string }) => {
          api.logger.error(
            `[octopus] ${info.kind} reply failed account=${account.accountId} conversation=${conversationId} error=${error instanceof Error ? error.message : String(error)}`,
          );
        },
      },
    });
  } finally {
    await typingLoop.stop();
  }
  if (senderRole === "customer" && replyTarget) {
    try {
      const profileSaveResult = await maybeSaveCustomerProfileFromSessions({
        agentId: resolvedAgentId,
        replyTarget,
        conversationId,
      });
      if (profileSaveResult.saved) {
        api.logger.info(
          `[octopus] customer profile saved conversation=${conversationId} replyTarget=${replyTarget} orderUid=${String(profileSaveResult.orderUid || "")} path=${profileSaveResult.profilePath}`,
        );
      }
    } catch (error) {
      api.logger.error(
        `[octopus] customer profile save failed conversation=${conversationId} replyTarget=${replyTarget} error=${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }
}

function buildWebhookRoutes(cfg: OpenClawConfig): Array<{ accountId: string; path: string }> {
  const routes: Array<{ accountId: string; path: string }> = [];
  for (const accountId of listOctopusAccountIds(cfg)) {
    const account = resolveOctopusAccount(cfg, accountId);
    if (!account.enabled) {
      continue;
    }
    routes.push({ accountId: account.accountId, path: account.webhookPath });
  }
  return routes;
}

const octopusPlugin: ChannelPlugin<ResolvedOctopusAccount> = {
  id: PROVIDER_NAME,
  meta: {
    id: PROVIDER_NAME,
    label: "AI Octopus",
    selectionLabel: "AI Octopus",
    docsPath: "/channels/octopus",
    docsLabel: "octopus",
    blurb: "AI Octopus webhook-based WhatsApp transport.",
    order: 90,
    quickstartAllowFrom: true,
  },
  capabilities: {
    chatTypes: ["direct"],
    media: true,
    threads: false,
    reactions: false,
    nativeCommands: false,
    blockStreaming: true,
  },
  reload: {
    configPrefixes: ["channels.octopus"],
  },
  configSchema: octopusChannelConfigSchema,
  config: {
    listAccountIds: (cfg: OpenClawConfig) => listOctopusAccountIds(cfg),
    resolveAccount: (cfg: OpenClawConfig, accountId?: string | null) =>
      resolveOctopusAccount(cfg, accountId),
    defaultAccountId: () => DEFAULT_ACCOUNT_ID,
    isConfigured: (account: ResolvedOctopusAccount) =>
      Boolean(account.bearerToken.trim() && account.agentId.trim()),
    describeAccount: (account: ResolvedOctopusAccount) => ({
      accountId: account.accountId,
      name: account.name,
      enabled: account.enabled,
      configured: Boolean(account.bearerToken.trim() && account.agentId.trim()),
      connected: account.enabled,
      dmPolicy: account.dmPolicy,
      allowFrom: account.allowFrom,
      webhookPath: account.webhookPath,
      baseUrl: account.baseUrl,
    }),
    resolveAllowFrom: ({ cfg, accountId }: { cfg: OpenClawConfig; accountId?: string | null }) =>
      resolveOctopusAccount(cfg, accountId).allowFrom,
    formatAllowFrom: ({ allowFrom }: { allowFrom: string[] }) =>
      allowFrom.map((entry: string) => normalizeAllowEntry(entry)),
  },
  security: {
    resolveDmPolicy: ({ account }: { account: ResolvedOctopusAccount }) => ({
      policy: account.dmPolicy,
      allowFrom: account.allowFrom,
      allowFromPath:
        account.accountId === DEFAULT_ACCOUNT_ID
          ? "channels.octopus.allowFrom"
          : `channels.octopus.accounts.${account.accountId}.allowFrom`,
      approveHint: "Add the conversation id or phone number to channels.octopus.allowFrom.",
      normalizeEntry: (raw: string) => normalizeAllowEntry(raw),
    }),
  },
};

const plugin = {
  id: "octopus-channel",
  name: "AI Octopus Channel",
  description: "Native AI Octopus channel integration for OpenClaw.",
  configSchema: {
    type: "object",
    additionalProperties: false,
    properties: {},
  },
  register(api: OpenClawPluginApi) {
    api.registerChannel({ plugin: octopusPlugin });
    startInactivitySweep(api);
    // Pre-populate account cache so sweep works immediately after restart
    for (const route of buildWebhookRoutes(api.config)) {
      const acct = resolveOctopusAccount(api.config, route.accountId);
      if (acct.enabled) inactivityAccountCache.set(acct.accountId, acct);
    }
    const registeredPaths = new Set<string>();
    for (const route of buildWebhookRoutes(api.config)) {
      if (registeredPaths.has(route.path)) {
        api.logger.warn(`[octopus] duplicate webhook path skipped: ${route.path}`);
        continue;
      }
      registeredPaths.add(route.path);
      api.registerHttpRoute({
        path: route.path,
        auth: "plugin",
        match: "exact",
        handler: async (req: any, res: any) => {
          const method = String(req.method || "GET").toUpperCase();
          const requestId = extractWebhookRequestId(req);
          const contentType = asTrimmedString(req.headers?.["content-type"]);
          const remoteAddress = resolveRemoteAddress(req);
          if (method === "GET") {
            const ingressId = createIngressId({
              accountId: route.accountId,
              webhookPath: route.path,
              method,
              requestId,
              entropy: `${Date.now()}`,
            });
            logWebhookEvent(api.logger, "info", "webhook_ready_check", {
              ingressId,
              requestId,
              account: route.accountId,
              method,
              path: route.path,
              remote: remoteAddress,
            });
            await upsertIngressLedgerEntry(buildIngressLedgerEntry({
              ingressId,
              requestId,
              accountId: route.accountId,
              webhookPath: route.path,
              method,
              status: "ready_check",
              note: "health_check",
              rawSize: 0,
              contentType,
              remoteAddress,
            }));
            writeJson(res, 200, { ok: true, status: "ready" });
            return true;
          }
          if (method !== "POST") {
            const ingressId = createIngressId({
              accountId: route.accountId,
              webhookPath: route.path,
              method,
              requestId,
              entropy: `${Date.now()}`,
            });
            logWebhookEvent(api.logger, "warn", "webhook_method_rejected", {
              ingressId,
              requestId,
              account: route.accountId,
              method,
              path: route.path,
              remote: remoteAddress,
            });
            await upsertIngressLedgerEntry(buildIngressLedgerEntry({
              ingressId,
              requestId,
              accountId: route.accountId,
              webhookPath: route.path,
              method,
              status: "method_rejected",
              note: "method_not_allowed",
              rawSize: 0,
              contentType,
              remoteAddress,
            }));
            res.statusCode = 405;
            res.setHeader("Content-Type", "text/plain; charset=utf-8");
            res.end("Method Not Allowed");
            return true;
          }
          const account = resolveOctopusAccount(api.config, route.accountId);
          if (!account.enabled) {
            const ingressId = createIngressId({
              accountId: route.accountId,
              webhookPath: route.path,
              method,
              requestId,
              entropy: `${Date.now()}`,
            });
            logWebhookEvent(api.logger, "warn", "webhook_account_disabled", {
              ingressId,
              requestId,
              account: route.accountId,
              method,
              path: route.path,
              remote: remoteAddress,
            });
            await upsertIngressLedgerEntry(buildIngressLedgerEntry({
              ingressId,
              requestId,
              accountId: route.accountId,
              webhookPath: route.path,
              method,
              status: "account_disabled",
              note: "account_disabled",
              rawSize: 0,
              contentType,
              remoteAddress,
            }));
            res.statusCode = 404;
            res.setHeader("Content-Type", "text/plain; charset=utf-8");
            res.end("Not Found");
            return true;
          }
          if (account.webhookToken) {
            const authHeader = req.headers.authorization;
            const bearerValue = authHeader?.startsWith("Bearer ")
              ? authHeader.slice("Bearer ".length).trim()
              : null;
            const headerToken = asTrimmedString(req.headers["x-ai-octopus-token"]);
            const tokenMatches =
              bearerValue === account.webhookToken || headerToken === account.webhookToken;
            if (!tokenMatches) {
              const ingressId = createIngressId({
                accountId: account.accountId,
                webhookPath: route.path,
                method,
                requestId,
                entropy: `${Date.now()}`,
              });
              logWebhookEvent(api.logger, "warn", "webhook_auth_failed", {
                ingressId,
                requestId,
                account: account.accountId,
                path: route.path,
                hasAuthorization: Boolean(authHeader),
                hasTokenHeader: Boolean(headerToken),
                remote: remoteAddress,
              });
              logWebhookEvent(api.logger, "error", "operator action required", {
                ingressId,
                requestId,
                account: account.accountId,
                cause: "webhook_auth_failed",
                remediation: "verify_octopus_webhook_token_alignment",
              });
              await upsertIngressLedgerEntry(buildIngressLedgerEntry({
                ingressId,
                requestId,
                accountId: account.accountId,
                webhookPath: route.path,
                method,
                status: "auth_failed",
                note: "webhook_token_mismatch",
                rawSize: 0,
                contentType,
                remoteAddress,
              }));
              writeJson(res, 401, { ok: false, message: "Unauthorized" });
              return true;
            }
          }
          const { raw, parsed } = await readRequestBody(req);
          const rawHash = hashIngressPayload(raw);
          const rawSize = nodeBuffer.byteLength(String(raw || ""), "utf-8");
          if (!parsed || typeof parsed !== "object") {
            const ingressId = createIngressId({
              accountId: account.accountId,
              webhookPath: route.path,
              method,
              requestId,
              rawHash,
              entropy: `${Date.now()}`,
            });
            logWebhookEvent(api.logger, "warn", "webhook_parse_failed", {
              ingressId,
              requestId,
              account: account.accountId,
              path: route.path,
              rawSize,
              payloadHash: rawHash,
              remote: remoteAddress,
            });
            await upsertIngressLedgerEntry(buildIngressLedgerEntry({
              ingressId,
              requestId,
              accountId: account.accountId,
              webhookPath: route.path,
              method,
              status: "parse_failed",
              error: "invalid_json_payload",
              rawSize,
              payloadHash: rawHash,
              contentType,
              remoteAddress,
            }));
            writeJson(res, 400, { ok: false, message: "Invalid JSON payload", raw });
            return true;
          }
          const messageText = extractMessageText(parsed);
          const replyTarget = extractReplyTarget(parsed);
          const messageId = extractWhatsAppMessageId(parsed);
          const audioMessage = !messageText ? extractAudioMessage(parsed) : null;
          const imageMessage = extractImageMessage(parsed);
          const locationMessage = extractLocationMessage(parsed);
          const conversationIdValue = extractConversationId(parsed);
          const conversationId = conversationIdValue === null ? null : String(conversationIdValue);
          const ingressId = createIngressId({
            accountId: account.accountId,
            webhookPath: route.path,
            method,
            requestId,
            conversationId,
            messageId,
            rawHash,
            entropy: conversationId && messageId ? null : `${Date.now()}`,
          });
          logWebhookEvent(api.logger, "info", "webhook_received", {
            ingressId,
            requestId,
            account: account.accountId,
            path: route.path,
            conversation: conversationId,
            replyTarget,
            messageId,
            hasMessageText: Boolean(messageText),
            hasAudioMessage: Boolean(audioMessage),
            hasImageMessage: Boolean(imageMessage),
            hasLocationMessage: Boolean(locationMessage),
            rawSize,
            payloadHash: rawHash,
            remote: remoteAddress,
          });
          if (conversationIdValue === null) {
            const isValidationProbe =
              !raw.trim() ||
              (!messageText &&
                !audioMessage &&
                !imageMessage &&
                !locationMessage &&
                !replyTarget &&
                !messageId);
            if (isValidationProbe) {
              await upsertIngressLedgerEntry(buildIngressLedgerEntry({
                ingressId,
                requestId,
                accountId: account.accountId,
                webhookPath: route.path,
                method,
                status: "validation_probe",
                note: "validation_probe",
                rawSize,
                payloadHash: rawHash,
                contentType,
                remoteAddress,
                payload: parsed,
              }));
              logWebhookEvent(api.logger, "info", "webhook_validation_probe", {
                ingressId,
                requestId,
                account: account.accountId,
                path: route.path,
                rawSize,
                payloadHash: rawHash,
              });
              writeJson(res, 200, { ok: true, status: "ready", probe: true });
              return true;
            }
            await upsertIngressLedgerEntry(buildIngressLedgerEntry({
              ingressId,
              requestId,
              accountId: account.accountId,
              webhookPath: route.path,
              method,
              status: "missing_conversation_id",
              error: "conversation_id_is_required",
              replyTarget,
              messageId,
              hasMessageText: Boolean(messageText),
              hasAudioMessage: Boolean(audioMessage),
              hasImageMessage: Boolean(imageMessage),
              hasLocationMessage: Boolean(locationMessage),
              rawSize,
              payloadHash: rawHash,
              contentType,
              remoteAddress,
              payload: parsed,
            }));
            logWebhookEvent(api.logger, "warn", "webhook_missing_conversation_id", {
              ingressId,
              requestId,
              account: account.accountId,
              path: route.path,
              replyTarget,
              messageId,
              rawSize,
              payloadHash: rawHash,
            });
            writeJson(res, 400, { ok: false, message: "conversation_id is required" });
            return true;
          }
          const acceptedIngressEntry = buildIngressLedgerEntry({
            ingressId,
            requestId,
            accountId: account.accountId,
            webhookPath: route.path,
            method,
            status: "accepted",
            conversationId,
            replyTarget,
            messageId,
            hasMessageText: Boolean(messageText),
            hasAudioMessage: Boolean(audioMessage),
            hasImageMessage: Boolean(imageMessage),
            hasLocationMessage: Boolean(locationMessage),
            rawSize,
            payloadHash: rawHash,
            contentType,
            remoteAddress,
            payload: parsed,
          });
          const acceptedPersistence = await persistAcceptedIngressEntry(acceptedIngressEntry);
          if (acceptedPersistence.duplicate) {
            logWebhookEvent(api.logger, "info", "webhook_duplicate_ignored", {
              ingressId,
              requestId,
              account: account.accountId,
              path: route.path,
              conversation: conversationId,
              replyTarget,
              messageId,
              existingStatus: acceptedPersistence.existingStatus,
            });
            writeJson(res, 200, {
              ok: true,
              accepted: true,
              duplicate: true,
              conversation_id: conversationId,
              reply_target: replyTarget,
              message_id: messageId,
              has_message_text: Boolean(messageText),
              has_audio_message: Boolean(audioMessage),
              has_image_message: Boolean(imageMessage),
              has_location_message: Boolean(locationMessage),
              received_at: new Date().toISOString(),
            });
            return true;
          }
          logWebhookEvent(api.logger, "info", "webhook_accepted", {
            ingressId,
            requestId,
            account: account.accountId,
            path: route.path,
            conversation: conversationId,
            replyTarget,
            messageId,
            rawSize,
          });
          writeJson(res, 200, {
            ok: true,
            accepted: true,
            conversation_id: conversationId,
            reply_target: replyTarget,
            message_id: messageId,
            has_message_text: Boolean(messageText),
            has_audio_message: Boolean(audioMessage),
            has_image_message: Boolean(imageMessage),
            has_location_message: Boolean(locationMessage),
            received_at: new Date().toISOString(),
          });
          if (!messageText && !audioMessage && !imageMessage && !locationMessage) {
            const ignoredAt = new Date().toISOString();
            await updateIngressLedgerEntries([ingressId], (entry) => ({
              ...entry,
              status: "ignored_non_text",
              processedAt: ignoredAt,
              lastUpdatedAt: ignoredAt,
              note: "accepted_but_no_supported_customer_content",
            }));
            api.logger.info(`[octopus] ignored non-text payload conversation=${conversationId}`);
            return true;
          }
          enqueueInboundMessage({
            api,
            account,
            ingressId,
            payload: parsed,
            conversationId,
            messageText,
            replyTarget,
            messageId,
            audioMessage,
            imageMessage,
            locationMessage,
          });
          logWebhookEvent(api.logger, "info", "webhook_enqueued", {
            ingressId,
            requestId,
            account: account.accountId,
            conversation: conversationId,
            replyTarget,
            messageId,
          });
          return true;
        },
      });
    }
    void replayPendingIngressLedgerEntries(api);
  },
};

export const __testables = {
  shouldIncludeQuotedRouteContext,
  buildQuotedRouteContextLines,
  shouldFallbackToDeterministicBookingReply,
  shouldFallbackToDeterministicSummaryReply,
  getLocationRoleSelection,
  getDeclaredLocationRole,
  applyPendingLocationRoleSelection,
  getStandaloneLocationAutoAssignmentRole,
  applyStandaloneLocationAssignment,
  applyVolunteeredFutureBookingFields,
  clearQuotedRouteContext,
  clearAutomatedConversationContext,
  applyBookingFieldCorrection,
  applyResponderStateOps,
  normalizeInterpretedCustomerTurn,
  shouldResetControllerForNewRouteMessage,
  shouldMoveToHumanAgent,
  shouldPreserveGreetingDuringActiveFlow,
  isGreetingInGraceWindow,
  computeOneBrainNextRequiredAction,
  formatOneBrainLiveChannelContext,
};

export default plugin;
