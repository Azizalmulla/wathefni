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
  CustomerScriptMode,
  normalizeIntentText,
  PersistedConversationControllerEntry,
  resolveCustomerReplyLanguage,
  resolveCustomerScriptMode,
  resolveSessionIdentityKey,
} from "../shared/conversation-policy";
import { findPersistedGuardSession } from "../shared/guard-state";
import {
  drainResponderStateOps,
  clearResponderStateOps,
  pushResponderStateOp,
  ResponderStateOp,
  ResponderBookingFieldOp,
  validateApplyBookingFieldOp,
  sanityCheckBookingDraft,
  DraftSanityProblem,
} from "../shared/responder-state-ops";
import {
  applyBookingFieldPatch,
  cleanName,
  cleanPhone,
  createRouteResetDraft,
  type BookingFieldPatch,
} from "../shared/booking-draft";
import {
  createEmptyDialogState,
  createRouteResetDialogState,
  deriveRequestedSlotFromMissing,
  setRequestedSlot,
  clearRequestedSlot,
  type SlotName,
  type DialogState,
} from "../shared/dialog-state";
import { isHallucinationGuardEnabled } from "../shared/reply-hallucination-guard";
import {
  applyProposals,
  fastPathProposal,
  llmProposal,
  type Proposal,
} from "../shared/apply-boundary";
import {
  decidePreStateOutbound,
  decidePostStateOutbound,
  type OutboundDecisionLogEntry,
} from "./lib/outbound-decision";
import {
  extractForNextAction,
  type FastPathAction,
} from "../shared/fast-path-extractor";
import { classifyReuseIntent } from "../shared/reuse-intent";
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
  isCanonicalOverwriteAllowed,
  buildDeterministicGreetingReply,
  buildDeterministicPassengerTransportReply,
  buildDeterministicLanguageSwitchReply,
  buildDeterministicServiceOverviewReply,
  buildDeterministicGraceWindowReply,
  buildProviderIssueFallbackReply,
} from "./lib/text";
import {
  pickCurrentWhatsappPhone,
  parseSenderStepInput,
  parseRecipientStepInput,
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
  detectCancelContradictsOptionMention,
  detectExplicitOptionMention,
  detectVagueProceedSignal,
  routeHasManualConfirmOption,
  resolveSameRouteQuoteFollowupAction,
  buildDeterministicSelectedQuotedOptionReply,
  buildDeterministicClarifyOptionBeforeProceedReply,
  buildDeterministicManualConfirmAddressAskReply,
  buildDeterministicManualConfirmHandoffReply,
  buildDeterministicOtherQuotedOptionsReply,
  buildQuotedRouteContextLines,
  matchQuotedOptionDiscriminated,
  matchLlmOptionInterpretation,
  resolveOptionFromProposals,
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
import {
  formatCustomerProfileContext,
  formatBehaviorPolicyContext,
} from "./lib/context-blocks";
import type { InterpretedBookingFields } from "./lib/interpreter-types";

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

// Debounce window waits for possible follow-up messages before processing a
// turn. 3s is the sweet spot: long enough to coalesce a burst of short
// messages ("hi", "I need a driver", "from Salmiya"), short enough that
// single-message turns don't feel sluggish. Override via
// RIDERS_INBOUND_DEBOUNCE_MS (text) / RIDERS_INBOUND_MEDIA_DEBOUNCE_MS (media).
function readPositiveIntEnv(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const n = Number.parseInt(String(raw).trim(), 10);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}
const INBOUND_DEBOUNCE_MS = readPositiveIntEnv("RIDERS_INBOUND_DEBOUNCE_MS", 3000);
const INBOUND_MEDIA_DEBOUNCE_MS = readPositiveIntEnv(
  "RIDERS_INBOUND_MEDIA_DEBOUNCE_MS",
  INBOUND_DEBOUNCE_MS,
);

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
// In-flight set: keys currently being nudged/closed in this process. Prevents
// double-sends within the same process when sweeps overlap. Not persisted, so
// after a restart it's empty — which is fine because the state file is the
// source of truth for nudgeSentTs.
const inactivityInFlight = new Set<string>();

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
      const elapsedMin = Math.round(elapsed / 60_000);

      // Garbage-collect very stale entries
      if (elapsed > INACTIVITY_EXPIRY_MS) {
        api.logger.info(
          `[octopus] inactivity sweep gc conversation=${entry.conversationId} elapsedMin=${elapsedMin} nudgeSent=${entry.nudgeSentTs !== null}`,
        );
        delete state[key];
        dirty = true;
        continue;
      }

      // Skip if another sweep in this process is already handling this key.
      if (inactivityInFlight.has(key)) {
        api.logger.info(
          `[octopus] inactivity sweep skip conversation=${entry.conversationId} reason=in_flight elapsedMin=${elapsedMin}`,
        );
        continue;
      }

      const pastClose = elapsed >= INACTIVITY_CLOSE_MS;
      const pastNudge = elapsed >= INACTIVITY_NUDGE_MS;
      const nudgeAlreadySent = entry.nudgeSentTs !== null;

      // Close threshold — fires if (a) nudge already succeeded, or (b) we're
      // past the close threshold with no nudge ever sent (covers the case
      // where a prior nudge attempt silently never recorded). In both cases
      // we try to close so entries don't get stranded until gc.
      if (pastClose && (nudgeAlreadySent || pastNudge)) {
        const closeLang = entry.language;
        const closeConvId = entry.conversationId;
        const closeReplyTarget = entry.replyTarget;
        const closeAccountId = entry.accountId;
        const closeReason = nudgeAlreadySent ? "after_nudge" : "nudge_missed";
        inactivityInFlight.add(key);
        api.logger.info(
          `[octopus] inactivity sweep action=close conversation=${closeConvId} elapsedMin=${elapsedMin} reason=${closeReason}`,
        );
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
            `[octopus] inactivity close sent conversation=${closeConvId} lang=${closeLang} reason=${closeReason}`,
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
            `[octopus] inactivity close failed conversation=${closeConvId} reason=${closeReason} error=${error instanceof Error ? error.message : String(error)}`,
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
        } finally {
          inactivityInFlight.delete(key);
        }
        continue;
      }

      // Nudge threshold — only persist nudgeSentTs AFTER a successful send,
      // so a transient send failure can retry on the next sweep instead of
      // silently blackholing the nudge forever.
      if (!nudgeAlreadySent && pastNudge) {
        inactivityInFlight.add(key);
        api.logger.info(
          `[octopus] inactivity sweep action=nudge conversation=${entry.conversationId} elapsedMin=${elapsedMin}`,
        );
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
          // Send succeeded — now persist nudgeSentTs. Re-read state to avoid
          // clobbering a concurrent customer activity write.
          const freshState = await loadInactivityState();
          const freshEntry = freshState[key];
          if (freshEntry && freshEntry.lastActivityTs === entry.lastActivityTs) {
            freshEntry.nudgeSentTs = Date.now();
            await saveInactivityState(freshState);
            entry.nudgeSentTs = freshEntry.nudgeSentTs;
          }
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
          // For any other error: leave nudgeSentTs === null so the next
          // sweep retries. The close fallback (above) also covers the case
          // where retries keep failing past CLOSE_MS.
        } finally {
          inactivityInFlight.delete(key);
        }
      } else {
        api.logger.debug?.(
          `[octopus] inactivity sweep skip conversation=${entry.conversationId} elapsedMin=${elapsedMin} nudgeSent=${nudgeAlreadySent} pastNudge=${pastNudge} pastClose=${pastClose}`,
        );
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

// formatCustomerProfileContext moved to ./lib/context-blocks.ts (wave 5).

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

// formatBehaviorPolicyContext moved to ./lib/context-blocks.ts (wave 5).

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

// ONE-BRAIN and responder-first are permanent. The channel skips the legacy
// turn-interpreter LLM, drains responder state ops through the minimal
// patch-apply path, and the single agent LLM owns every customer-facing
// message. Deterministic guards only check prices at outbound and order
// preconditions at create time. The `RESPONDER_FIRST_FLAG` +
// `isOneBrainConversation()` scaffolding was removed in step 2 of the
// dead-code sweep after the legacy `else if` drain branch was deleted;
// there is no surviving reference and no toggle to preserve.
// Legacy turn-interpreter LLM (TURN_INTERPRETER_*, buildTurnInterpreterStateSummary,
// normalizeInterpretedCustomerTurn, normalizeBookingFields,
// interpretCustomerTurnWithOpenAi, mapInterpretedActionToCustomerIntent,
// resolveSameRouteQuoteActionFromInterpreter) was deleted in the
// interpreter-collapse refactor. One-brain owns every customer turn;
// deterministic tool-side guards enforce correctness. See earlier commit
// (24fbcc9) for the call-site neutralization that preceded this delete.
// BOOKABLE_QUOTED_OPTION_TYPES, DELIVERY_TYPE_ALIASES, SAME_ROUTE_* markers, and
// all quoted-option helpers (isBookableQuotedOptionType, getQuotedRouteDefaultOption,
// getQuotedRouteOption, getActiveSelectedQuotedOption, formatQuotedOptionLabel,
// formatQuotedOptionPrice, applySelectedQuotedOptionToController,
// syncControllerSelectionFromQuotedRoute, buildQuotedOptionAliases,
// scoreQuotedOptionMatch, resolveSameRouteQuoteFollowupAction,
// buildDeterministicSelectedQuotedOptionReply, buildDeterministicOtherQuotedOptionsReply)
// moved to ./lib/quoted-options.ts (wave 4).

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
}): "pickup" | "delivery" | null {
  return getLocationRoleSelection(params.visibleText) || null;
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
    pendingPickupAreaNameEn: null,
    pendingPickupAreaNameAr: null,
    pendingDropoffAreaNameEn: null,
    pendingDropoffAreaNameAr: null,
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

// `applyBookingFieldCorrection` + `applyResponderStateOps` + the legacy drain
// branch were deleted in the step-2 dead-code sweep. Both became unreachable
// once `RESPONDER_FIRST_FLAG` was hardcoded to `true` — the live one-brain
// drain at `dispatchReplyWithBufferedBlockDispatcher` handles every op shape
// (apply_booking_field, set_requested_slot, set_pending_area, cancel_booking,
// request_handoff, carry_over_from_last_order, start_booking/confirm_summary
// as intentional no-ops). The pure `applyCarryOverOp` helper below is the
// surviving testable primitive that both the live drain and the smoke-test
// suite exercise for carry-over behavior.
// resolveNextBookingStepFromDraft moved to ./lib/booking-flow.ts (wave 4).

function applyBookingDraftProgress(entry: PersistedConversationControllerEntry): PersistedConversationControllerEntry {
  const nextStep = resolveNextBookingStepFromDraft(entry.bookingDraft);
  return {
    ...entry,
    stage: nextStep === "summary_pending" ? "summary_shown" : "collecting_booking_details",
    bookingStep: nextStep,
  };
}

/**
 * Pure helper that applies a single `carry_over_from_last_order` op onto the
 * running draft + dialog state. Called from the live one-brain drain so that
 * reuse-intent ops (pushed by the fast-path reuse classifier or by the LLM)
 * actually mutate state instead of being silently dropped.
 *
 * The behavior is a direct port of the identity branch of the legacy
 * `applyResponderStateOps` handler. Validation (`cleanName` + `cleanPhone`)
 * mirrors exactly what `apply_booking_field` does, so stale/corrupt saved
 * values are skipped rather than written. Writes are tagged
 * `dstSource: "carryover"` so the source-precedence override (in
 * `applyBookingFieldPatch`) and the summary renderer can distinguish reused
 * identity from customer-turn identity.
 *
 * Address buckets (`pickup_location`, `delivery_location`) are V1 "ask fresh":
 * the bucket vocabulary is forward-compatible but addresses drift order-to-
 * order more than identity, so V1 prompts the customer to re-send rather than
 * silently rewriting.
 */
export type CarryOverOpResult =
  | { outcome: "no_saved_order" }
  | { outcome: "empty_buckets" }
  | {
      outcome: "no_valid_fields";
      skipped: Array<{ field: string; reason: string }>;
      askFresh: string[];
    }
  | {
      outcome: "ask_fresh";
      askFresh: string[];
    }
  | {
      outcome: "applied" | "applied_partial";
      draft: PersistedBookingDraft;
      dialogState: DialogState | null;
      appliedFields: string[];
      rejected: Array<{ field: string; reason: string; received: string }>;
      skipped: Array<{ field: string; reason: string }>;
      askFresh: string[];
    };

function applyCarryOverOp(params: {
  op: { op: "carry_over_from_last_order"; buckets?: unknown };
  draft: PersistedBookingDraft;
  dialogState: DialogState | null;
  customerProfile: CustomerProfile | null;
  whatsappNumber: string | null;
}): CarryOverOpResult {
  const last = params.customerProfile?.last_successful_order ?? null;
  const buckets = Array.isArray(params.op.buckets)
    ? (params.op.buckets as string[])
    : [];
  if (!last) return { outcome: "no_saved_order" };
  if (buckets.length === 0) return { outcome: "empty_buckets" };
  const patch: BookingFieldPatch = {};
  const skipped: Array<{ field: string; reason: string }> = [];
  const askFresh: string[] = [];
  if (buckets.includes("sender_identity")) {
    const n = cleanName(last.sender?.name ?? null);
    if (n.value) patch.sender_name = n.value;
    else if (last.sender?.name)
      skipped.push({ field: "sender_name", reason: n.reason || "invalid" });
    const p = cleanPhone(last.sender?.phone ?? null);
    if (p.value) patch.sender_phone = p.value;
    else if (last.sender?.phone)
      skipped.push({ field: "sender_phone", reason: p.reason || "invalid" });
  }
  if (buckets.includes("recipient_identity")) {
    const n = cleanName(last.recipient?.name ?? null);
    if (n.value) patch.recipient_name = n.value;
    else if (last.recipient?.name)
      skipped.push({ field: "recipient_name", reason: n.reason || "invalid" });
    const p = cleanPhone(last.recipient?.phone ?? null);
    if (p.value) patch.recipient_phone = p.value;
    else if (last.recipient?.phone)
      skipped.push({ field: "recipient_phone", reason: p.reason || "invalid" });
  }
  if (buckets.includes("pickup_location")) askFresh.push("pickup_location");
  if (buckets.includes("delivery_location")) askFresh.push("delivery_location");
  const patchKeys = Object.keys(patch);
  if (patchKeys.length === 0) {
    if (askFresh.length > 0 && skipped.length === 0) {
      return { outcome: "ask_fresh", askFresh };
    }
    return { outcome: "no_valid_fields", skipped, askFresh };
  }
  const applyRes = applyBookingFieldPatch({
    draft: params.draft,
    patch,
    whatsappNumber: params.whatsappNumber,
    dialogState: params.dialogState,
    dstSource: "carryover",
  });
  return {
    outcome: skipped.length > 0 ? "applied_partial" : "applied",
    draft: applyRes.draft,
    dialogState: applyRes.dialogState ?? params.dialogState,
    appliedFields: applyRes.applied.map((f) => String(f)),
    rejected: applyRes.rejected.map((r) => ({
      field: r.field,
      reason: r.reason,
      received: r.received,
    })),
    skipped,
    askFresh,
  };
}

// getLocationRoleSelection, formatPersistedBookingLocationLabel,
// buildSavedLocationRoleReply, buildDeterministicLocationSavedDuringIdentityReply
// moved to ./lib/booking-flow.ts (wave 4).
// buildDeterministicGraceWindowReply moved to ./lib/text.ts (wave 2a).

// buildDeterministicBookingDetailsReply, buildPendingOrderSummaryFingerprint,
// formatSummaryAreaLine moved to ./lib/booking-flow.ts (wave 4).

/**
 * Whether the given slot was last written by `carry_over_from_last_order`.
 * Used by the summary renderer to annotate reused identity fields so the
 * customer immediately sees which details came from their saved profile.
 * When the feature flag is off or DST isn't populated, returns false safely.
 */
function slotWasCarriedOver(
  entry: PersistedConversationControllerEntry | null,
  slot: SlotName,
): boolean {
  const record = entry?.dialogState?.slots?.[slot];
  return Boolean(record && record.lastSource === "carryover");
}

function carryOverMarker(language: "ar" | "en"): string {
  return language === "ar" ? " (من طلبك السابق)" : " (from your last order)";
}

function buildDeterministicOrderSummaryReply(
  language: "ar" | "en",
  entry: PersistedConversationControllerEntry | null,
): string {
  const senderName = entry?.bookingDraft.senderName || "-";
  const senderPhone = entry?.bookingDraft.senderPhone || "-";
  const recipientName = entry?.bookingDraft.recipientName || "-";
  const recipientPhone = entry?.bookingDraft.recipientPhone || "-";
  const senderCarried =
    slotWasCarriedOver(entry, "sender_name") || slotWasCarriedOver(entry, "sender_phone");
  const recipientCarried =
    slotWasCarriedOver(entry, "recipient_name") || slotWasCarriedOver(entry, "recipient_phone");
  const senderMark = senderCarried ? carryOverMarker(language) : "";
  const recipientMark = recipientCarried ? carryOverMarker(language) : "";
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
      `المرسل: ${senderName}، ${senderPhone}${senderMark}`,
      `المستلم: ${recipientName}، ${recipientPhone}${recipientMark}`,
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
    `Sender: ${senderName}, ${senderPhone}${senderMark}`,
    `Recipient: ${recipientName}, ${recipientPhone}${recipientMark}`,
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

// `alignBookingFieldsToCurrentStep` + `advanceBookingControllerFromCustomerText`
// were deleted in the step-2 sweep. Both were part of the legacy turn-
// interpreter pipeline; the one-brain drain bypasses them entirely (the LLM's
// `apply_booking_field` tool call already carries aligned, step-specific
// fields, and `applyBookingFieldPatch` + `applyBookingDraftProgress` own the
// draft-advance state machine).

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
  // Lift the pin's resolved area name into the controller-entry's
  // pending area slot for the selected role. This closes the 2026-04-19
  // pin-flow bug where the pin's `resolvedAreaName` stayed inside the
  // `pickupLocation` object and never reached `missing_fields`, so the
  // LLM kept asking "which pickup area" even though the resolver had
  // already produced "Mirqab". We only write the PENDING slot (not
  // `quote*`) because a `get_price` call hasn't happened yet — the
  // value may still be corrected by the customer, and the quote slot
  // is reserved for priced routes. Writing pending here means the
  // next `get_price` will see the area already resolved.
  //
  // We only promote to pending when no higher-authority area is
  // already set for that role (an active quote or an existing pending
  // for the SAME role). Writing over an existing pending could wipe a
  // deterministic typed-area resolution.
  const resolvedAreaFromPin =
    typeof pendingLocation.resolvedAreaName === "string" &&
    pendingLocation.resolvedAreaName.trim()
      ? pendingLocation.resolvedAreaName.trim()
      : null;
  if (role === "pickup") {
    nextEntry.bookingDraft.pickupLocation = pendingLocation;
    nextEntry.bookingDraft.pickupBlock = null;
    nextEntry.bookingDraft.pickupStreet = null;
    nextEntry.bookingDraft.pickupHouse = null;
    if (
      resolvedAreaFromPin &&
      !nextEntry.quotePickupAreaNameEn &&
      !nextEntry.pendingPickupAreaNameEn
    ) {
      nextEntry.pendingPickupAreaNameEn = resolvedAreaFromPin;
    }
  } else {
    nextEntry.bookingDraft.deliveryLocation = pendingLocation;
    nextEntry.bookingDraft.deliveryBlock = null;
    nextEntry.bookingDraft.deliveryStreet = null;
    nextEntry.bookingDraft.deliveryHouse = null;
    if (
      resolvedAreaFromPin &&
      !nextEntry.quoteDropoffAreaNameEn &&
      !nextEntry.pendingDropoffAreaNameEn
    ) {
      nextEntry.pendingDropoffAreaNameEn = resolvedAreaFromPin;
    }
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

// `shouldReplaceGreetingForLanguage` was deleted in the Step-3 guard-narrowing
// sweep (step-3 scope: keep factual guards, drop stylistic rewriters). It had
// zero callers and represented the older policy of post-LLM language-script
// policing. Language direction is now enforced purely by the preferred-reply-
// language prompt context; if the LLM drifts to the wrong script that is a
// prompt-level issue, not something we rewrite on the wire.

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

// `shouldPreferCanonicalToolReply` was inlined into `./lib/outbound-decision.ts`
// as part of the Step-4 consolidation. See `needsCanonicalOverwriteForTxArtifacts`
// in that module for the factual-only canonical-overwrite policy (Step-3
// narrowing) that this helper encoded. All outbound reply decisions now live in
// that single module with one stable reason-code vocabulary.

// shouldMoveToHumanAgent, buildDeterministicTrackingGuardReply moved to
// ./lib/intent-text.ts (wave 4).

/**
 * Step-4 helper: emit the structured log entries produced by
 * `decidePreStateOutbound` / `decidePostStateOutbound`. Keeps the decision
 * module pure (no logger dependency) while still giving us the same log
 * surface as before the consolidation.
 */
function emitOutboundDecisionLogs(
  api: OpenClawPluginApi,
  entries: OutboundDecisionLogEntry[],
): void {
  for (const entry of entries) {
    if (entry.level === "warn") {
      api.logger.warn(entry.message);
    } else {
      api.logger.info(entry.message);
    }
  }
}

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
const TRANSCRIPT_REFINE_MODEL = String(env.RIDERS_TRANSCRIPT_REFINE_MODEL || "gpt-5.4").trim();
// Gate the post-STT refinement LLM call. Default OFF: Whisper with a domain vocab
// prompt is accurate enough for Kuwaiti Arabic / English code-switching, and the
// extra LLM hop was adding ~2-3s latency per voice message for marginal gain.
// Set RIDERS_TRANSCRIPT_REFINE_ENABLED=1 to opt back in if we ever see regressions.
const TRANSCRIPT_REFINE_ENABLED =
  String(env.RIDERS_TRANSCRIPT_REFINE_ENABLED || "").trim() === "1";

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
        model: TRANSCRIPT_REFINE_MODEL,
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
  if (TRANSCRIPT_REFINE_ENABLED && rawText.length > 0 && rawText.length < 400) {
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
      pendingPickupAreaNameEn: null,
      pendingPickupAreaNameAr: null,
      pendingDropoffAreaNameEn: null,
      pendingDropoffAreaNameAr: null,
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
  // Script/register mirror signal for the one-brain LLM. Orthogonal to the
  // binary ar/en language: the latter drives deterministic canonical choice,
  // this one tells the LLM whether to render the reply in Arabic script or
  // English. Customers writing Arabizi (Latin letters + digit substitutions
  // like "slam 3laikm") are classified as "english" here — we no longer
  // reply in Arabizi; Kuwaiti customers get proper English replies instead.
  let customerScriptMode: CustomerScriptMode = resolveCustomerScriptMode({
    visibleText: turnSignals.languageSignalText || null,
    explicitLanguage: explicitLanguageRequestRaw,
    fallbackLanguage: resolveControllerFallbackLanguage(conversationControllerEntry),
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
  // Clear any stale responder-state ops from the previous turn so this
  // turn's tool calls start with an empty queue.
  if (senderRole === "customer") {
    try {
      clearResponderStateOps(conversationId);
    } catch {}
  }
  // `explicitLanguageRequest` used to merge a raw channel-level signal with the
  // interpreter LLM's `language_switch` hint. With the interpreter removed,
  // the raw value IS the explicit request, so the `!== raw` reconciliation
  // block below was unreachable and has been deleted.
  const explicitLanguageRequest = explicitLanguageRequestRaw;
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
      script: customerScriptMode,
      mode: "one_brain",
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
      ? classifyCustomerIntent({
          visibleText: turnSignals.workflowInputText || null,
          explicitLanguage: explicitLanguageRequest,
          controllerEntry: conversationControllerEntry,
        })
      : null;
  let controllerTransitionHint: string | null = null;
  if (
    senderRole === "customer" &&
    turnSignals.workflowInputText &&
    shouldResetControllerForNewRouteMessage({
      controllerEntry: conversationControllerEntry,
      visibleText: turnSignals.workflowInputText,
    })
  ) {
    // Selective route-reset: wipe route-scoped state (quote, areas, address
    // sub-fields, selected options) but PRESERVE identity fields (sender,
    // recipient name + phone) on both the booking draft and the dialog state.
    // Identity travels with the customer across orders — especially when
    // `carry_over_from_last_order` just filled those fields from their saved
    // profile. Without this partition, "salwa to massayel" after "same names
    // and number as last order" silently wipes the carried-over identity and
    // forces the customer to re-enter everything they just asked to reuse.
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
          pendingPickupAreaNameEn: null,
          pendingPickupAreaNameAr: null,
          pendingDropoffAreaNameEn: null,
          pendingDropoffAreaNameAr: null,
          selectedQuoteOptionType: null,
          selectedQuoteOptionLabelAr: null,
          selectedQuoteOptionLabelEn: null,
          selectedQuoteOptionPrice: null,
          selectedQuoteOptionDirectChatBookingStatus: null,
          selectedDeliveryType: null,
          quotedPrice: null,
          bookingDraft: createRouteResetDraft(conversationControllerEntry.bookingDraft),
          dialogState: createRouteResetDialogState(conversationControllerEntry.dialogState),
          pendingReplyText: null,
        }
      : null;
    if (conversationControllerEntry) {
      const preserved: string[] = [];
      if (conversationControllerEntry.bookingDraft?.senderName) preserved.push("sender_name");
      if (conversationControllerEntry.bookingDraft?.senderPhone) preserved.push("sender_phone");
      if (conversationControllerEntry.bookingDraft?.recipientName) preserved.push("recipient_name");
      if (conversationControllerEntry.bookingDraft?.recipientPhone) preserved.push("recipient_phone");
      api.logger.info(
        `[controller] reset active booking flow after new route message conversation=${conversationId} preserved_identity=${preserved.join(",") || "none"} text=${JSON.stringify(turnSignals.workflowInputText.slice(0, 160))}`,
      );
    }
  }
  const isGreetingTurn = currentCustomerIntent === "greeting";
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
        pendingPickupAreaNameEn: null,
        pendingPickupAreaNameAr: null,
        pendingDropoffAreaNameEn: null,
        pendingDropoffAreaNameAr: null,
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
    // Deterministic fast-path: keyword match on visible text to bind the
    // pending location to pickup or delivery. One-brain handles the nuanced
    // cases via the `apply_booking_field` tool with an explicit `address_role`.
    // The legacy Layer-2 interpreter `location_role_hint` path has been removed.
    const pendingLocationRoleResult =
      turnSignals.workflowInputText
        ? applyPendingLocationRoleSelection({
            controllerEntry: conversationControllerEntry,
            visibleText: turnSignals.workflowInputText,
          })
        : null;
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
  // One-brain owns all draft mutations via `apply_booking_field` tool calls
  // drained below. The legacy heuristic booking-text advancer (the
  // `shouldAdvanceBookingControllerFromText` / `advanceBookingControllerFromCustomerText` /
  // `applyBookingFieldCorrection` pipeline) was removed in step 2 of the
  // dead-code sweep.
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
  const effectiveLanguageSwitch: "ar" | "en" | null = explicitLanguageRequest;
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
    currentCustomerIntent === "passenger_transport_request"
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
              pendingPickupAreaNameEn: null,
              pendingPickupAreaNameAr: null,
              pendingDropoffAreaNameEn: null,
              pendingDropoffAreaNameAr: null,
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
  // Legacy interpreter-driven `cancel_booking` fast-path removed. One-brain
  // emits a `cancel_booking` responder op from the LLM tool; the drain below
  // clears booking state. See Stage 4 of the interpreter collapse.
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
    isSummaryEditRequest(turnSignals.workflowInputText)
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
    sameRouteQuoteAction = resolveSameRouteQuoteFollowupAction({
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
  const safetyNetMatched = Boolean(
    turnSignals.workflowInputText && isBookingStartIntent(turnSignals.workflowInputText),
  );
  if (quotedStagePreDispatch) {
    api.logger.info(
      `[controller] quoted-stage turn conversation=${conversationId} safety_net_matched=${safetyNetMatched ? "yes" : "no"}`,
    );
  }
  if (quotedStagePreDispatch && safetyNetMatched) {
    const selectedQuotedOption =
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
        currentCustomerText: rawBody,
        activeQuotedRoute,
      });
      if (directive) {
        const fastResult = extractForNextAction({
          text: rawBody,
          action: directive.action as FastPathAction,
          whatsappNumber: replyTarget,
        });
        if (fastResult.confidence === "high" && fastResult.patch) {
          // Route the fast-path patch through the one apply boundary.
          // The boundary re-runs the evidence contract (source-quote,
          // ambiguous-pair, coherence, shape) on every proposal
          // regardless of source — so LLM-emitted and fast-path-emitted
          // writes are held to the same standard. See
          // `plugins/shared/apply-boundary.ts` and `ARCHITECTURE.md`.
          const proposal = fastPathProposal({
            patch: fastResult.patch,
            sourceQuote: rawBody,
          });
          const boundaryRes = applyProposals([proposal], {
            draft,
            dialogState: conversationControllerEntry.dialogState ?? null,
            whatsappNumber: replyTarget,
            stage: conversationControllerEntry.stage ?? null,
          });
          if (boundaryRes.applied.length > 0) {
            conversationControllerEntry = {
              ...conversationControllerEntry,
              bookingDraft: boundaryRes.draft,
              dialogState:
                boundaryRes.dialogState ?? conversationControllerEntry.dialogState,
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
            fastPathPreApplied = boundaryRes.applied;
            api.logger.info(
              `[one-brain/fast-path] pre-applied action=${directive.action} fields=${boundaryRes.applied.join(",")} reasons=${fastResult.reasons.join(",")} rejected=${boundaryRes.rejections.length} conversation=${conversationId}`,
            );
          }
          if (boundaryRes.rejections.length > 0) {
            for (const r of boundaryRes.rejections) {
              api.logger.warn(
                `[one-brain/boundary] rejected source=${r.source} field=${r.field} reason=${r.reason} received=${JSON.stringify(r.received)} conversation=${conversationId}`,
              );
            }
          }
        } else if (fastResult.confidence === "none" && fastResult.reasons.length > 0) {
          // Coverage telemetry. For address actions we emit at `info`
          // so prod aggregation shows us which shape-classes the
          // extractor is missing (apartment / avenue / tower / Arabic
          // variants / glued punctuation). Other actions stay at
          // `debug` to avoid noise on combined sender-turns that are
          // expected to fall through to the LLM on the free-form side.
          const isAddressAction =
            directive.action === "ASK_PICKUP_ADDRESS" ||
            directive.action === "ASK_DELIVERY_ADDRESS";
          // Truncated + sanitized sample of the text. We don't log the
          // full body (PII hygiene, log volume). A 120-char cap +
          // newline-stripped shape is enough to recognize address
          // patterns while keeping long free-form notes out.
          const textSample = rawBody
            .replace(/\s+/g, " ")
            .slice(0, 120);
          const line = `[one-brain/fast-path] skip action=${directive.action} reasons=${fastResult.reasons.join(",")} text_sample=${JSON.stringify(textSample)} conversation=${conversationId}`;
          if (isAddressAction) {
            api.logger.info(line);
          } else {
            api.logger.debug?.(line);
          }
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

  // Reuse-intent fast-path. When the customer explicitly asks to reuse their
  // previous order's identity fields ("same names and number as last order",
  // "نفس الأسماء والأرقام"), pre-emit a carry_over_from_last_order op before
  // the LLM runs so the identity fields are already populated by the time
  // the system snapshot is built. This closes the gap where the LLM
  // recognizes the intent in its reply but forgets to emit the tool call,
  // which is the exact failure mode in the 2026-04-19 transcript. Falls
  // back silently to the LLM when no phrase matches — never guesses.
  if (
    senderRole === "customer" &&
    conversationControllerEntry &&
    rawBody &&
    customerProfile?.last_successful_order
  ) {
    try {
      const reuse = classifyReuseIntent({
        text: rawBody,
        hasSavedOrder: Boolean(customerProfile.last_successful_order),
      });
      if (reuse.kind === "carry_over" && reuse.buckets.length > 0) {
        pushResponderStateOp(conversationId, {
          op: "carry_over_from_last_order",
          buckets: reuse.buckets,
          source_quote: reuse.matchedText,
          turn_id: `fast-path:${conversationId}:${Date.now()}`,
        });
        api.logger.info(
          `[one-brain/fast-path] reuse-intent matched conversation=${conversationId} buckets=${reuse.buckets.join(",")} reason=${reuse.reason} match=${JSON.stringify(reuse.matchedText)}`,
        );
      }
    } catch (reuseError) {
      api.logger.warn(
        `[one-brain/fast-path] reuse-intent classification failed conversation=${conversationId} error=${
          reuseError instanceof Error ? reuseError.message : String(reuseError)
        }`,
      );
    }
  }

  const channelContext = formatLiveChannelContext(senderRole, replyTarget, {
    isOneBrain: true,
    currentIntent: currentCustomerIntent,
    preferredReplyLanguage,
    customerScriptMode,
    conversationStage: conversationControllerEntry?.stage ?? null,
    bookingStep: conversationControllerEntry?.bookingStep ?? null,
    controllerEntry: conversationControllerEntry,
    quotedRoute: activeQuotedRoute,
    quoteFollowupHint,
    controllerTransitionHint,
    currentCustomerText: rawBody,
  });
  const customerProfileContext = senderRole === "customer" ? formatCustomerProfileContext(customerProfile) : null;
  const behaviorContext = senderRole === "customer"
    ? await loadBehaviorPolicyContext(account, api.logger, {
        currentIntent: currentCustomerIntent,
      })
    : null;
  if (senderRole === "customer") {
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
  // Legacy deterministic-greeting early-return removed: one-brain owns
  // greetings and replies via the agent LLM. The old branch was gated behind
  // `!isOneBrainConversation(replyTarget)` which is now provably `false`.
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
          // Captured BEFORE the drain so the hallucination guard can tell whether
          // an "order placed" claim in the outbound reply is grounded in a real
          // stage transition this turn. If stageAtTurnStart was already
          // `order_submitted`, the customer is in post-order chat and any
          // recap-style "order placed" mention is legitimate.
          const stageAtTurnStart = conversationControllerEntry?.stage ?? null;
          // Lifted from the drain block so the post-reply hallucination guard
          // can consult this turn's field-rejection evidence. Any rejection
          // pushed here makes a "field is invalid, please resend" LLM reply
          // grounded rather than hallucinated.
          const hallucinationGuardRejections: Array<{ field: string; reason: string; received: string }> = [];
          // Bug 2 (2026-04-20): when the LLM's `cancel_booking` op is
          // rejected because the same utterance also named a currently
          // quoted option ("nvm pls standard sedan"), we stash the
          // matched option label here. Hoisted to outer scope so the
          // post-drain `decidePostStateOutbound` call can read it and
          // substitute a disambiguating re-ask in place of any
          // hallucinated "we've cancelled" text.
          let cancelContradicted: { optionLabel: string } | null = null;
          // ONE-BRAIN mode: simplified drain. One LLM per turn owns all reply
          // copy; we only merge booking patches into the draft, reset on cancel,
          // and flag handoff. No stage/step/hint threading, no deterministic
          // summary override — the LLM writes the summary itself when ready.
          if (senderRole === "customer") {
            try {
              const drained = drainResponderStateOps(conversationId);
              if (drained.length > 0) {
                let nextDraft = conversationControllerEntry?.bookingDraft || createEmptyBookingDraft();
                let nextDialogState = conversationControllerEntry?.dialogState ?? null;
                let cancelled = false;
                let handoffRequested = false;
                const rejections = hallucinationGuardRejections;
                const appliedOps: string[] = [];
                for (const op of drained) {
                  if (op.op === "apply_booking_field") {
                    // Route every LLM-proposed field write through the
                    // one apply boundary. The boundary runs the full
                    // evidence contract (source-quote, ambiguous-pair,
                    // coherence, shape). Behavior that used to be
                    // inlined here — the ambiguous-pair guard, the
                    // rejection-reason push, the `setRequestedSlot`
                    // steer — now lives inside `applyProposals` so both
                    // LLM and fast-path proposals go through one code
                    // path. See `plugins/shared/apply-boundary.ts` and
                    // `ARCHITECTURE.md`.
                    const proposal: Proposal = llmProposal({
                      op: {
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
                        source_quote: op.source_quote ?? null,
                        turn_id: op.turn_id ?? null,
                      },
                    });
                    const boundaryRes = applyProposals([proposal], {
                      draft: nextDraft,
                      dialogState: nextDialogState,
                      whatsappNumber: replyTarget,
                      stage: conversationControllerEntry.stage ?? null,
                    });
                    nextDraft = boundaryRes.draft;
                    if (boundaryRes.dialogState) {
                      nextDialogState = boundaryRes.dialogState;
                    }
                    for (const r of boundaryRes.rejections) {
                      rejections.push({
                        field: r.field,
                        reason: r.reason,
                        received: r.received,
                      });
                      try {
                        api.logger.warn(
                          `[one-brain/boundary] rejected source=${r.source} field=${r.field} reason=${r.reason} received=${JSON.stringify(r.received)} conversation=${conversationId} turn_id=${op.turn_id}`,
                        );
                      } catch {}
                    }
                    if (boundaryRes.conflicts.length > 0) {
                      api.logger.warn(
                        `[one-brain/dst] slot conflicts conversation=${conversationId} ${JSON.stringify(boundaryRes.conflicts)}`,
                      );
                    }
                    appliedOps.push(`apply_booking_field(${boundaryRes.applied.join(",")})`);
                  } else if (op.op === "cancel_booking") {
                    // Bug 2 guard: cancel vs switch disambiguation.
                    // When the customer's own source_quote names one
                    // of the currently quoted options ("nvm pls
                    // standard sedan", "cancel the fast one", "actually
                    // box van"), treat the LLM's cancel emission as a
                    // misclassification. Do NOT apply the cancel, log
                    // the rejection, stash the matched option label
                    // for the outbound guard, and push a field-style
                    // rejection onto this turn's list so the LLM sees
                    // the rejection on the next turn and replans.
                    const cancelGuard = detectCancelContradictsOptionMention({
                      sourceQuote: (op as { source_quote?: string | null }).source_quote ?? null,
                      route: activeQuotedRoute,
                    });
                    if (cancelGuard.contradicted && cancelGuard.optionLabel) {
                      cancelContradicted = { optionLabel: cancelGuard.optionLabel };
                      rejections.push({
                        field: "cancel_booking",
                        reason: "cancel_contradicted_by_option_mention",
                        received: String((op as { source_quote?: string | null }).source_quote ?? ""),
                      });
                      try {
                        api.logger.warn(
                          `[one-brain/cancel-guard] rejected cancel contradicted by option mention conversation=${conversationId} option=${cancelGuard.optionType ?? ""} label=${cancelGuard.optionLabel} source_quote=${JSON.stringify((op as { source_quote?: string | null }).source_quote ?? "")}`,
                        );
                      } catch {}
                      appliedOps.push(
                        `cancel_booking:rejected(option_mention=${cancelGuard.optionType ?? "?"})`,
                      );
                    } else {
                      cancelled = true;
                      appliedOps.push("cancel_booking");
                    }
                  } else if (op.op === "request_handoff") {
                    handoffRequested = true;
                    appliedOps.push("request_handoff");
                  } else if (op.op === "set_requested_slot") {
                    // Mid-turn clarification intent from a tool (e.g. pricing
                    // asked the customer to disambiguate an area). Record it
                    // on DST so the next turn's guards and prompt know which
                    // slot the customer's reply should fill.
                    if (nextDialogState) {
                      nextDialogState = setRequestedSlot(nextDialogState, {
                        name: op.slot as SlotName,
                        options: op.options ?? null,
                        askedTs: Date.now(),
                      });
                    }
                    appliedOps.push(`set_requested_slot(${op.slot})`);
                  } else if (op.op === "set_pending_area") {
                    // Handled below when the controller entry is materialized;
                    // just record that it occurred for audit.
                    appliedOps.push(
                      `set_pending_area(${op.field}=${op.area_name_en || "-"})`,
                    );
                  } else if (op.op === "carry_over_from_last_order") {
                    // Reuse-intent carry-over. Sourced either from the
                    // fast-path reuse-intent classifier or from the LLM when
                    // it decides to reuse identity from the customer's saved
                    // profile. Before this branch, these ops were silently
                    // dropped in the live drain (the handler lived only in
                    // the legacy `applyResponderStateOps` path, which became
                    // unreachable once one-brain was hardcoded on).
                    //
                    // All validation + source tagging is delegated to
                    // `applyCarryOverOp`, which is the shared port used by
                    // tests as well — see __testables.
                    const carry = applyCarryOverOp({
                      op: op as {
                        op: "carry_over_from_last_order";
                        buckets?: unknown;
                      },
                      draft: nextDraft,
                      dialogState: nextDialogState,
                      customerProfile,
                      whatsappNumber: replyTarget,
                    });
                    if (carry.outcome === "no_saved_order") {
                      appliedOps.push("carry_over:no_saved_order");
                    } else if (carry.outcome === "empty_buckets") {
                      appliedOps.push("carry_over:empty_buckets");
                    } else if (carry.outcome === "ask_fresh") {
                      appliedOps.push(
                        `carry_over:ask_fresh:${carry.askFresh.join("+")}`,
                      );
                    } else if (carry.outcome === "no_valid_fields") {
                      appliedOps.push("carry_over:no_valid_saved_fields");
                      if (carry.skipped.length > 0) {
                        try {
                          api.logger.warn(
                            `[one-brain/carry-over] all_skipped conversation=${conversationId} skipped=${JSON.stringify(carry.skipped)}`,
                          );
                        } catch {}
                      }
                    } else {
                      nextDraft = carry.draft;
                      nextDialogState = carry.dialogState;
                      for (const r of carry.rejected) {
                        rejections.push({
                          field: r.field,
                          reason: `carryover_rejected:${r.reason}`,
                          received: r.received,
                        });
                      }
                      appliedOps.push(
                        `carry_over:${carry.outcome}(${carry.appliedFields.join(",")})`,
                      );
                      try {
                        api.logger.info(
                          `[one-brain/carry-over] applied conversation=${conversationId} buckets=${(Array.isArray(op.buckets) ? op.buckets : []).join(",")} fields=${carry.appliedFields.join(",")} skipped=${JSON.stringify(carry.skipped)} askFresh=${carry.askFresh.join(",") || "-"}`,
                        );
                      } catch {}
                    }
                  } else if (op.op === "propose_option_interpretation") {
                    // Phase 1 (2026-04-20) — LLM's structured option
                    // interpretation. Stored for the post-drain
                    // reconciliation block below. Emitting the op does
                    // NOT mutate controller state by itself.
                    appliedOps.push(
                      `propose_option_interpretation(${op.class ?? "-"}/${op.tier ?? "-"}/${op.confidence})`,
                    );
                  } else if (op.op === "start_booking" || op.op === "confirm_summary") {
                    // One-brain ignores these — `apply_booking_field` and
                    // `create_simple_order` are the only signals we care about.
                    appliedOps.push(`${op.op}:ignored`);
                  }
                }
                // Phase 1 reconciliation: combine the pre-dispatch
                // deterministic raw-text outcome (captured earlier as
                // `sameRouteQuoteAction`) with the LLM's structured
                // interpretation op, and commit if the resolver returns a
                // unique option that is NOT already selected. Pre-dispatch
                // already committed its own unique match; this block only
                // adds coverage for cases where raw-text was
                // underspecified/ambiguous/none AND the LLM's
                // interpretation uniquely resolves with high confidence.
                // Disagreements are logged so we can see drift between
                // the two proposer layers — Phase 5 will surface those as
                // a metric.
                {
                  const interpretOp = drained.find(
                    (op) => op.op === "propose_option_interpretation",
                  ) as
                    | {
                        op: "propose_option_interpretation";
                        class: "sedan" | "van" | "cooled_van" | "helper" | null;
                        tier: "normal" | "fast" | null;
                        qualifiers?: string[] | null;
                        source_quote: string;
                        confidence: "high" | "low";
                        turn_id: string;
                      }
                    | undefined;
                  if (
                    interpretOp &&
                    conversationControllerEntry &&
                    activeQuotedRoute &&
                    hasActiveQuotedBookingAuthority(conversationControllerEntry)
                  ) {
                    // Source-quote evidence gate — mirrors the
                    // `apply_booking_field` contract. The LLM must quote a
                    // substring of the customer's inbound text to ground its
                    // interpretation; otherwise the proposal is dropped.
                    const visible = (turnSignals.workflowInputText || "").trim();
                    const quote = (interpretOp.source_quote || "").trim();
                    const quoteGrounded =
                      quote.length > 0 &&
                      visible.toLowerCase().includes(quote.toLowerCase());
                    if (!quoteGrounded) {
                      api.logger.warn(
                        `[option-resolve] llm_interpretation dropped reason=source_quote_not_in_visible conversation=${conversationId} quote=${JSON.stringify(quote.slice(0, 80))} visible=${JSON.stringify(visible.slice(0, 80))}`,
                      );
                    } else {
                      const pricedOptions =
                        activeQuotedRoute.optionCatalog.filter((o) => o.quoted_price != null);
                      const normalizedVisibleText = normalizeIntentText(visible);
                      const rawTextOutcome = matchQuotedOptionDiscriminated({
                        normalizedText: normalizedVisibleText,
                        options: pricedOptions,
                      });
                      const llmOutcome = matchLlmOptionInterpretation({
                        interpretation: {
                          class: interpretOp.class,
                          tier: interpretOp.tier,
                          source_quote: interpretOp.source_quote,
                          confidence: interpretOp.confidence,
                        },
                        options: pricedOptions,
                      });
                      const reconciled = resolveOptionFromProposals({
                        rawTextOutcome,
                        llmOutcome,
                      });
                      const currentSelectedType =
                        conversationControllerEntry.selectedQuoteOptionType ||
                        conversationControllerEntry.selectedDeliveryType ||
                        null;
                      if (reconciled.kind === "commit") {
                        const target = reconciled.option;
                        if (target.delivery_type !== currentSelectedType) {
                          conversationControllerEntry = applySelectedQuotedOptionToController(
                            conversationControllerEntry,
                            target,
                          );
                          mirrorConversationControllerEntry(
                            controllerStateKey,
                            conversationControllerEntry,
                          );
                          api.logger.info(
                            `[option-resolve] committed conversation=${conversationId} source=${reconciled.source} option=${target.delivery_type} price=${formatQuotedOptionPrice(target)} prior=${currentSelectedType || "-"}`,
                          );
                        } else {
                          api.logger.info(
                            `[option-resolve] reaffirmed conversation=${conversationId} source=${reconciled.source} option=${target.delivery_type}`,
                          );
                        }
                      } else if (reconciled.kind === "clarify") {
                        api.logger.warn(
                          `[option-resolve] clarify conversation=${conversationId} source=${reconciled.source} fastPath=${reconciled.fastPathCandidate?.delivery_type || "-"} llm=${reconciled.llmCandidate?.delivery_type || "-"} candidates=${(reconciled.candidates || []).map((c) => c.delivery_type).join(",") || "-"}`,
                        );
                      } else {
                        api.logger.info(
                          `[option-resolve] no_signal conversation=${conversationId} raw=${rawTextOutcome.kind} llm=${llmOutcome.kind}`,
                        );
                      }
                    }
                  }
                }
                if (conversationControllerEntry) {
                  const appliedBookingPatch = drained.some(
                    (op) => op.op === "apply_booking_field",
                  );
                  // Carry-over writes the same slots as apply_booking_field
                  // (just with a different source tag), so it must likewise
                  // trigger the progress recompute — otherwise bookingStep
                  // would stay on "sender" even after the customer's reuse
                  // intent filled sender + recipient from their saved
                  // profile, and the prompt would still ask for the sender
                  // name on the next turn.
                  const appliedCarryOver = drained.some(
                    (op) => op.op === "carry_over_from_last_order",
                  );
                  let nextEntry: PersistedConversationControllerEntry = cancelled
                    ? {
                        ...conversationControllerEntry,
                        bookingDraft: createEmptyBookingDraft(),
                        pendingReplyText: null,
                        stage: "idle",
                        bookingStep: "none",
                        dialogState: conversationControllerEntry.dialogState
                          ? createEmptyDialogState()
                          : null,
                      }
                    : {
                        ...conversationControllerEntry,
                        bookingDraft: nextDraft,
                        dialogState:
                          nextDialogState ?? conversationControllerEntry.dialogState,
                      };
                  // ONE-BRAIN: after any apply_booking_field or carry_over
                  // patch, re-derive bookingStep + stage from the current
                  // draft so the system prompt surfaces the correct step-hint
                  // (e.g. "all fields confirmed → write summary") instead of
                  // a frozen earlier step.
                  if (!cancelled && (appliedBookingPatch || appliedCarryOver)) {
                    nextEntry = applyBookingDraftProgress(nextEntry);
                  }
                  // Apply set_pending_area ops onto the controller entry so
                  // the next turn's smuggle guard sees the resolved area
                  // even if the LLM's tool call doesn't echo enough raw
                  // text. Last-write-wins per leg within a single turn.
                  if (!cancelled) {
                    for (const op of drained) {
                      if (op.op !== "set_pending_area") continue;
                      if (op.field === "pickup_area") {
                        nextEntry = {
                          ...nextEntry,
                          pendingPickupAreaNameEn: op.area_name_en,
                          pendingPickupAreaNameAr: op.area_name_ar,
                        };
                      } else if (op.field === "dropoff_area") {
                        nextEntry = {
                          ...nextEntry,
                          pendingDropoffAreaNameEn: op.area_name_en,
                          pendingDropoffAreaNameAr: op.area_name_ar,
                        };
                      }
                    }
                  }
                  // DST: derive `requestedSlot` from the fresh post-drain
                  // missing-fields set. This covers phone-resend and
                  // address-subfield prompts — whenever the LLM's next
                  // required action implies a specific slot, we record it
                  // so the *next* turn's guards can route the customer's
                  // answer to the correct slot. `set_requested_slot` ops
                  // already pushed by tools (e.g. area disambiguation from
                  // pricing.ts) take precedence because they ran first in
                  // the drain loop and carry disambiguation options; we
                  // only derive here if none was set and we have a concrete
                  // directive.
                  if (!cancelled && nextEntry.dialogState) {
                    const existingRequested = nextEntry.dialogState.requestedSlot;
                    const pushedRequestedThisTurn = drained.some(
                      (op) => op.op === "set_requested_slot",
                    );
                    if (!pushedRequestedThisTurn) {
                      const nextMissing = computeOneBrainMissingFields(
                        nextEntry.bookingDraft,
                        nextEntry,
                      );
                      const directive = computeOneBrainNextRequiredAction({
                        draft: nextEntry.bookingDraft,
                        entry: nextEntry,
                        missing: nextMissing,
                      });
                      if (directive) {
                        const derivedSlot = deriveRequestedSlotFromMissing(nextMissing);
                        if (derivedSlot) {
                          // Only update if changed, to avoid spurious
                          // askedTs resets that would make log diffs noisy.
                          if (
                            !existingRequested ||
                            existingRequested.name !== derivedSlot
                          ) {
                            nextEntry = {
                              ...nextEntry,
                              dialogState: setRequestedSlot(
                                nextEntry.dialogState,
                                {
                                  name: derivedSlot,
                                  options: null,
                                  askedTs: Date.now(),
                                },
                              ),
                            };
                          }
                        } else if (existingRequested) {
                          // No specific slot required → clear the old one
                          // (e.g. we moved past the sender-phone ask to the
                          // address step).
                          nextEntry = {
                            ...nextEntry,
                            dialogState: clearRequestedSlot(nextEntry.dialogState),
                          };
                        }
                      }
                    }
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
          let guardToolAgeMs: number = Number.POSITIVE_INFINITY;
          let overwriteGate: { allowed: boolean; reason: string } = { allowed: false, reason: "no_session" };
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
            // Canonical-overwrite gate. See `isCanonicalOverwriteAllowed`
            // in lib/text.ts for the contract and rationale. In short: the
            // guard is allowed to fire ONLY on a fresh get_price turn while
            // the controller is still in `idle` (about to be promoted to
            // `quoted`). Any post-quote stage means the LLM is answering
            // a follow-up or driving the booking forward and its reply
            // must be trusted. Gate result is passed into the unified
            // `decideOutboundReply` call further down (Step-4 consolidation).
            guardToolAgeMs = sessionGuard
              ? Math.max(0, Date.now() - sessionGuard.lastToolTs)
              : Number.POSITIVE_INFINITY;
            overwriteGate = isCanonicalOverwriteAllowed({
              lastToolAgeMs: guardToolAgeMs,
              controllerStage: conversationControllerEntry?.stage,
            });
          }
          // Step-4 consolidation: Region A of the former inline decision
          // pipeline (canonical overwrite, empty-fill, price whitelist,
          // same-route quote correction) is now a single pure call. It runs
          // BEFORE the controller-state block so that any reply
          // substitution is visible to the `quotePresentedToCustomer`
          // computation — preserving pre-Step-4 behavior.
          {
            // Clarify-before-proceed gate (Bug 1, 2026-04-20 manual-
            // confirm incident). Evaluated at Region-A time so the
            // controller entry reflects any drain-loop updates from this
            // turn. Fires only on `stage=quoted` with a mixed-bookability
            // catalog and a vague proceed signal that does not name an
            // option — see `computeOneBrainNextRequiredAction` for the
            // authoritative invariants, kept in sync with the outbound
            // substitute below.
            const clarifyOptionBeforeProceed = Boolean(
              conversationControllerEntry?.stage === "quoted" &&
                activeQuotedRoute &&
                rawBody &&
                routeHasManualConfirmOption(activeQuotedRoute) &&
                detectVagueProceedSignal(rawBody) &&
                !detectExplicitOptionMention({ text: rawBody, route: activeQuotedRoute }),
            );
            if (clarifyOptionBeforeProceed) {
              api.logger.info(
                `[one-brain/clarify-option] gate=fired conversation=${conversationId} routeKey=${activeQuotedRoute?.routeKey || "na"} text=${JSON.stringify((rawBody || "").slice(0, 80))}`,
              );
            }

            // Manual-confirm server-composed address-ask / handoff
            // substitution (Bug 4, 2026-04-20 manual-confirm signal drop
            // incident). When the controller has a fresh quote AND the
            // selected option is flagged `manual_confirmation_required`,
            // we compute whether the next server-directed action is an
            // address ask (pickup or delivery) or the handoff itself,
            // and pass that to Region-A so the reply text is rendered
            // deterministically. This is the single-source-of-truth
            // sibling of `computeOneBrainNextRequiredAction` — we
            // replicate just the manual-confirm sub-branch here because
            // Region A runs BEFORE the controller-state mutation block
            // and must not depend on the LLM's emitted directive text.
            let manualConfirmAddressAsk:
              | {
                  side: "pickup" | "delivery";
                  option: RouteQuoteOption;
                }
              | null = null;
            let manualConfirmHandoff: { option: RouteQuoteOption } | null = null;
            if (
              conversationControllerEntry?.stage === "quoted" &&
              activeQuotedRoute &&
              conversationControllerEntry.selectedDeliveryType &&
              String(
                conversationControllerEntry.selectedQuoteOptionDirectChatBookingStatus || "",
              )
                .trim()
                .toLowerCase() === "manual_confirmation_required"
            ) {
              const selectedOption = getActiveSelectedQuotedOption(
                activeQuotedRoute,
                conversationControllerEntry,
              );
              if (selectedOption) {
                const draft = conversationControllerEntry.bookingDraft;
                const pickupSatisfied = hasSatisfiedBookingAddress(draft, "pickup");
                const deliverySatisfied = hasSatisfiedBookingAddress(draft, "delivery");
                if (!pickupSatisfied) {
                  manualConfirmAddressAsk = { side: "pickup", option: selectedOption };
                } else if (!deliverySatisfied) {
                  manualConfirmAddressAsk = { side: "delivery", option: selectedOption };
                } else {
                  manualConfirmHandoff = { option: selectedOption };
                }
                api.logger.info(
                  `[one-brain/manual-confirm] gate=fired conversation=${conversationId} routeKey=${activeQuotedRoute.routeKey} option=${selectedOption.delivery_type} pickupSatisfied=${pickupSatisfied} deliverySatisfied=${deliverySatisfied}`,
                );
              }
            }

            const preDecision = decidePreStateOutbound({
              replyText,
              preferredLanguage: preferredReplyLanguage,
              sessionGuard,
              sessionIsRecent,
              preferredCanonicalText,
              guardToolAgeMs,
              canonicalOverwriteAllowed: overwriteGate.allowed,
              canonicalOverwriteSkipReason: overwriteGate.reason,
              extractPricesFromText: guardState?.extractPricesFromText || ((_: string) => []),
              activeQuotedRoute,
              sameRouteQuoteAction,
              clarifyOptionBeforeProceed,
              manualConfirmAddressAsk,
              manualConfirmHandoff,
              buildDeterministicSelectedQuotedOptionReply,
              buildDeterministicClarifyOptionBeforeProceedReply,
              buildDeterministicManualConfirmAddressAskReply,
              buildDeterministicManualConfirmHandoffReply,
              conversationId,
              sessionKeyForLogs: guardSessionKey,
              controllerStage: conversationControllerEntry?.stage || null,
            });
            replyText = preDecision.replyText;
            emitOutboundDecisionLogs(api, preDecision.logEntries);
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
                // Pending areas were just promoted to quote* — clear them so
                // a later turn doesn't carry forward a stale resolution.
                pendingPickupAreaNameEn: null,
                pendingPickupAreaNameAr: null,
                pendingDropoffAreaNameEn: null,
                pendingDropoffAreaNameAr: null,
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
                pendingPickupAreaNameEn: null,
                pendingPickupAreaNameAr: null,
                pendingDropoffAreaNameEn: null,
                pendingDropoffAreaNameAr: null,
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
            turnSignals.workflowInputText &&
            isBookingStartIntent(turnSignals.workflowInputText)
          ) {
            const latestQuotedRoute =
              sessionGuard?.lastToolName === "get_price" && sessionGuard.lastQuotedRoute
                ? sessionGuard.lastQuotedRoute
                : null;
            const effectiveQuotedRoute = latestQuotedRoute || activeQuotedRoute;
            const selectedQuotedOption =
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
          // NOTE: the empty-reply transition-hint fallbacks (summary_edit_request /
          // grace_window_offer) and the generic provider-issue fallback that used
          // to live here were moved into `decidePostStateOutbound` as part of the
          // Step-4 consolidation. They now run together with the verify +
          // hallucination-guard pass below.
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

          // Step-4 consolidation: Regions B + C of the former inline
          // decision pipeline (empty-reply fallbacks, summary-fact-drift
          // substitution, and the hallucination guard) are now a single
          // pure call. This runs AFTER the persist block so that any
          // in-memory controller promotion triggered by a summary
          // substitute (`markedSummaryShown`) does NOT leak into the
          // persisted stage for this turn — preserving pre-Step-4
          // behavior where the pre-verify stage was the one persisted.
          if (conversationControllerEntry) {
            const missingForVerify = computeOneBrainMissingFields(
              conversationControllerEntry.bookingDraft,
              conversationControllerEntry,
            );
            const hallucinationGuardEnabled = isHallucinationGuardEnabled();
            const nextRequiredAction = hallucinationGuardEnabled
              ? (computeOneBrainNextRequiredAction({
                  draft: conversationControllerEntry.bookingDraft,
                  entry: conversationControllerEntry,
                  missing: missingForVerify,
                })?.action ?? null)
              : null;
            // Full valid price set for the active quoted route — feeds
            // the hallucination guard so it can accept legitimate replies
            // that mention other options' prices (e.g. answering
            // "is there other options?") without flagging them as a
            // price_mismatch. See the `activeQuotedPrices` note on
            // `HallucinationGuardInputs` for the incident reference.
            //
            // The set is the UNION of:
            //   (a) `pricesByType` — the bookable vehicle types
            //       (sedan_normal/fast, van_normal/fast). These are the
            //       options the customer can actually place an order for
            //       via `create_simple_order`.
            //   (b) `optionCatalog[*].quoted_price` — every option the
            //       customer is ALLOWED TO HEAR A PRICE FOR, even if it
            //       requires manual confirmation (e.g. Helper service).
            //       These are surfaced to the LLM in the quote payload
            //       as `other_options_if_customer_asks`, so a reply that
            //       mentions their price is legitimately grounded.
            //
            // Pre-fix (2026-04-19 second incident): the set was only (a),
            // so a truthful reply naming "Helper service at 3.250 KWD"
            // — manual-confirm option, not in `pricesByType` — registered
            // as a price_mismatch and was substituted with the neutral
            // price_repair. The LLM's answer was correct; the guard was
            // under-informed.
            const activeQuotedPrices: number[] = [];
            if (activeQuotedRoute) {
              for (const p of Object.values(
                activeQuotedRoute.pricesByType || {},
              )) {
                if (typeof p === "number" && Number.isFinite(p) && p > 0) {
                  activeQuotedPrices.push(p);
                }
              }
              if (Array.isArray(activeQuotedRoute.optionCatalog)) {
                for (const opt of activeQuotedRoute.optionCatalog) {
                  const qp = opt?.quoted_price;
                  if (typeof qp === "number" && Number.isFinite(qp) && qp > 0) {
                    activeQuotedPrices.push(qp);
                  }
                }
              }
            }
            const postDecision = decidePostStateOutbound({
              replyText,
              preferredLanguage: preferredReplyLanguage,
              conversationControllerEntry,
              missingFields: missingForVerify,
              hallucinationGuardRejections,
              stageAtTurnStart,
              hallucinationGuardEnabled,
              nextRequiredAction,
              activeQuotedPrices,
              cancelContradicted,
              controllerTransitionHint,
              buildDeterministicGraceWindowReply,
              buildProviderIssueFallbackReply,
              conversationId,
            });
            replyText = postDecision.replyText;
            emitOutboundDecisionLogs(api, postDecision.logEntries);
            if (postDecision.markedSummaryShown) {
              // Mark the summary as having been shown so downstream
              // confirmation detection and order-guard "summary_shown" gate
              // both work off the real event, not the stub.
              conversationControllerEntry = {
                ...conversationControllerEntry,
                stage: "summary_shown" as ConversationFlowStage,
                bookingStep: "summary_pending" as BookingCollectionStep,
              };
            }
          } else {
            // No controller entry — handle the bare empty-reply fallbacks
            // inline. `decidePostStateOutbound` is a no-op for the
            // non-controller case beyond these three lines (the verify +
            // hallucination-guard passes both require an entry), so we
            // skip the call and do the minimum here for clarity.
            const postDecision = decidePostStateOutbound({
              replyText,
              preferredLanguage: preferredReplyLanguage,
              conversationControllerEntry: null,
              missingFields: [],
              hallucinationGuardRejections: [],
              stageAtTurnStart: null,
              hallucinationGuardEnabled: false,
              nextRequiredAction: null,
              controllerTransitionHint,
              buildDeterministicGraceWindowReply,
              buildProviderIssueFallbackReply,
              conversationId,
            });
            replyText = postDecision.replyText;
            emitOutboundDecisionLogs(api, postDecision.logEntries);
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
            // Legacy interpreter-driven handoff removed; one-brain emits a
            // `request_handoff` responder op when escalation is needed, and the
            // string-match `shouldMoveToHumanAgent(outboundText)` check below
            // covers the canned-reply case handled by `sendOctopusTextReply`.
            if (
              conversationControllerEntry &&
              shouldMoveToHumanAgent(outboundText)
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
  // OpenClaw's channel-health-monitor polls `plugin.gateway.startAccount` as
  // the channel's lifecycle handle. Without it, `snapshot.running` never
  // flips to true and the monitor restarts the channel every ~5-10 minutes
  // with `reason: stopped`. Octopus is a pure webhook receiver (inbound HTTP
  // is registered via `api.registerHttpRoute` at plugin load), so there is no
  // long-lived socket to connect. We keep the task alive by awaiting the
  // abort signal, which flips `running: true` while the gateway is up.
  //
  // `stopAccount` is a no-op because there is nothing to tear down beyond
  // the abort signal the gateway already fires for us.
  status: {
    skipStaleSocketHealthCheck: true,
  },
  gateway: {
    startAccount: async (params: { abortSignal: AbortSignal }) => {
      const { abortSignal } = params;
      if (abortSignal.aborted) return;
      await new Promise<void>((resolve) => {
        const onAbort = () => {
          abortSignal.removeEventListener("abort", onAbort);
          resolve();
        };
        abortSignal.addEventListener("abort", onAbort, { once: true });
      });
    },
    stopAccount: async () => {},
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
  applyCarryOverOp,
  shouldResetControllerForNewRouteMessage,
  shouldMoveToHumanAgent,
  shouldPreserveGreetingDuringActiveFlow,
  isGreetingInGraceWindow,
  computeOneBrainNextRequiredAction,
  formatOneBrainLiveChannelContext,
};

export default plugin;
