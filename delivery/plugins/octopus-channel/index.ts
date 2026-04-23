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
  isExplicitOrderConfirmation,
  isInformationalOptionQuestion,
  // Cut 7b (2026-04-23): implicit / contextual clarifying-question
  // detector, wired into `computePromptShapingDisposition` so the
  // pre-LLM `answer` rule catches indirect forms like "so i cant order
  // rn if its manual confirmation".
  //
  // DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_DETECTOR_IMPORT_MARKER.
  isContextualClarifyingQuestion,
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
import { validateProposedTurnDecision } from "../shared/proposer-schema";
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
  findFirstConflictSlot,
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
import { applyCrossSidePhoneGuard } from "../shared/cross-side-phone-guard";
import {
  decidePreStateOutbound,
  decidePostStateOutbound,
  type OutboundDecisionLogEntry,
  type OutboundDecisionKind,
  type OutboundDecisionReason,
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
  selectGuardQuotedRoute,
  collectActiveQuotedPrices,
} from "./lib/quoted-options";
import {
  shouldIncludeQuotedRouteContext,
  formatOneBrainValue,
  computeOneBrainMissingFields,
  computeOneBrainNextRequiredAction,
  formatOneBrainLiveChannelContext,
} from "./lib/one-brain-context";
import type { OneBrainNextRequiredAction } from "./lib/one-brain-context";
import {
  renderDirectiveReply,
  directiveHasServerRenderer,
  isRegisteredDirectiveAction,
} from "../shared/directive-reply-registry";
import type {
  DirectiveReplyRendererContext,
  DirectiveAction,
} from "../shared/directive-reply-registry";
import {
  observeTurnDecision,
  formatTurnDecisionTrace,
  deriveA1Substitute,
  decideDirectiveDisposition,
} from "../shared/turn-decision";
import type {
  TurnDecisionObservedContext,
  A1SubstituteIntent,
  A1Derivation,
  DirectiveDispositionDerivation,
} from "../shared/turn-decision";
// Cut #5 (2026-04-23): Turn-disposition AUTHORING gate. `decideTurnDisposition`
// is imported directly from the disposition module (not re-exported by
// `turn-decision.ts`) so the callsite can invert authority live: when the
// layer classifies the turn as anything other than `continue_step`, the
// state-machine directive is NOT consumed this turn, inverting the
// long-standing "state authors; meaning vetoes" shape into "meaning
// authors; state is a subroutine called only on continue_step".
// DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_IMPORT_MARKER.
import { decideTurnDisposition } from "../shared/turn-disposition";
import type { TurnDispositionDecision } from "../shared/turn-disposition";
// Cut #6 (2026-04-23): prompt-shaping disposition. Pre-LLM heuristic that
// decides whether the system prompt carries state-machine authoring
// imperatives this turn. Input-side counterpart of Cut #5's output-side
// inversion. Default-off (env `RIDERS_PROMPT_DISPOSITION_SHAPE_LIVE=on`
// to enable). When the pre-LLM disposition is anything other than
// `continue_step`, the prompt drops `next_required_action`,
// `forbidden_reply_shapes`, `requested_slot_rule`, `pending_area_rule`,
// `slot_conflicts_rule`, and hard rules 4 and 10; state FACTS stay.
// DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_IMPORT_MARKER.
import { computePromptShapingDisposition } from "../shared/turn-disposition";
// Cut 9.0 (2026-04-23): Turn Router — top-level meaning-first dispatcher.
// Runs once per customer turn, BEFORE the state machine, and classifies
// the turn into a dispatch MODE. Downstream consumers read the decision
// to answer "should `computeOneBrainNextRequiredAction` author this
// turn?" / "should the prompt carry state imperatives?" / "should
// Region-A substitutions arm?". Dark-land scaffold: one consumer
// (state-machine authoring gate) is wired; the env flag
// `RIDERS_TURN_ROUTER_DEFAULT_MODE` stays at the legacy "advance_form"
// default so behaviour is unchanged until the flip. See
// `plugins/shared/turn-router.ts` for the full rationale.
// DEPLOY_CANARY_TURN_ROUTER_IMPORT_MARKER.
import {
  classifyTurn,
  parseTurnRouterDefaultModeEnv,
} from "../shared/turn-router";
import type {
  TurnRouterDecision,
  TurnRouterDefaultMode,
} from "../shared/turn-router";
import type { OutboundProvenance } from "../shared/outbound-provenance";
import {
  provenanceFromDecision,
  isValidOutboundProvenance,
  OUTBOUND_PROVENANCE_VALUES,
} from "../shared/outbound-provenance";
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
            preferredLanguage: closeLang,
            provenance: "deterministic_fallback",
            provenanceReason: "inactivity_close",
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
            preferredLanguage: entry.language === "ar" ? "ar" : "en",
            provenance: "deterministic_fallback",
            provenanceReason: "inactivity_nudge",
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
            provenance: "deterministic_fallback",
            provenanceReason: "processing_error_fallback",
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

// buildDeterministicLocationClarificationReply + shouldUseDeterministicLocationClarification
// deleted in authority-cutover phase 2 (2026-04-23). The server-composed
// "pickup or delivery?" reply was a pre-LLM early-return author that
// wrote partial state without advancing the stage; see the rewrite in
// the main flow for the new pendingLocation-only persistence.

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
  /**
   * Trust tag for the text about to reach the wire. REQUIRED for every
   * call site (defaulting is intentional so reviewers notice new
   * untagged sites in diffs). The five-value enum is defined in
   * `../shared/outbound-provenance.ts` with the mapping rules.
   *
   * - `llm_unverified` should never appear in steady state. When it
   *   does, `[outbound/provenance]` is emitted at warn and a paired
   *   `operator action required` event lets on-call triage catch the
   *   bypass before it compounds.
   */
  provenance: OutboundProvenance;
  /**
   * Short reason code attached to the provenance log line for
   * per-turn grep. Matches `OutboundDecisionReason` when derived from
   * the main pipeline, otherwise a free-form identifier for canned
   * wire paths (e.g. `inactivity_close`, `processing_error_fallback`).
   */
  provenanceReason: string;
  /**
   * Optional directive action — included in the provenance line so the
   * eval-corpus can slice by directive without cross-referencing the
   * earlier `[directive-render/trace]`. Null when not applicable.
   */
  provenanceDirective?: string | null;
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
    provenance: rawProvenance,
    provenanceReason,
    provenanceDirective = null,
  } = params;
  // Runtime enum validation for the provenance param. TypeScript
  // already constrains this at the five call sites inside this file,
  // but the wire-send boundary is the enforcement surface — we want it
  // to behave correctly even when a future JS caller, cross-plugin
  // consumer, or build-step misconfiguration bypasses the type check.
  //
  // Tier 1 policy (2026-04-22): DO NOT refuse to send on invalid
  // provenance. Instead, (a) coerce the tag to `llm_unverified` so the
  // canonical `[outbound/provenance]` line still accounts for the
  // send, and (b) emit a dedicated `operator action required` event
  // with the exact bad value so on-call can locate the caller. This
  // preserves the "zero behavioural change" guarantee while still
  // surfacing the bypass loudly enough for the 48h observation
  // window. Tier 2 (post-48h) will promote this to refuse-to-send.
  let provenance: OutboundProvenance;
  if (isValidOutboundProvenance(rawProvenance)) {
    provenance = rawProvenance;
  } else {
    provenance = "llm_unverified";
    logWebhookEvent(api.logger, "error", "operator action required", {
      account: account.accountId,
      conversation: conversationId,
      replyTarget,
      cause: "outbound_provenance_invalid",
      remediation: "pass_a_valid_OutboundProvenance_literal_to_sendOctopusTextReply",
      provided: typeof rawProvenance === "string"
        ? rawProvenance
        : `<non-string:${typeof rawProvenance}>`,
      allowed: OUTBOUND_PROVENANCE_VALUES.join(","),
      source,
      provenanceReason,
      ingressIds: ingressIds.length > 0 ? ingressIds.join(",") : undefined,
    });
  }
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
  // One canonical [outbound/provenance] line per wire-send. Every
  // customer-visible reply is accounted for by exactly one of these,
  // regardless of whether the text came from the main webhook pipeline
  // or from a canned early path (inactivity sweep, image/audio failure,
  // location clarification, etc.). Downstream tooling (eval-corpus,
  // dashboards) can grep on `[outbound/provenance]` and slice by
  // `provenance` without reading any surrounding context.
  //
  // `llm_unverified` is treated as a bypass signal: the text reached
  // the wire without going through `decidePostStateOutbound`'s C1+C2
  // gates, which after this PR should never happen in production.
  // Emitted at `warn` so on-call and the smoke harness notice
  // immediately, with a paired `operator action required` event for
  // the audit trail.
  if (provenance === "llm_unverified") {
    api.logger.warn(
      `[outbound/provenance] conversation=${conversationId} provenance=${provenance} reason=${provenanceReason} directive=${provenanceDirective || "-"} source=${source} lang=${preferredLanguage} chars=${outboundText.length}`,
    );
    logWebhookEvent(api.logger, "warn", "operator action required", {
      account: account.accountId,
      conversation: conversationId,
      replyTarget,
      cause: "outbound_provenance_llm_unverified",
      remediation: "route_call_site_through_decide_post_state_outbound",
      source,
      ingressIds: ingressIds.length > 0 ? ingressIds.join(",") : undefined,
    });
  } else {
    api.logger.info(
      `[outbound/provenance] conversation=${conversationId} provenance=${provenance} reason=${provenanceReason} directive=${provenanceDirective || "-"} source=${source} lang=${preferredLanguage} chars=${outboundText.length}`,
    );
  }
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
          provenance: "deterministic_fallback",
          provenanceReason: "image_read_failure",
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
          provenance: "deterministic_fallback",
          provenanceReason: "audio_transcription_failure",
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
  // turn's tool calls start with an empty queue. Mirror the same alias
  // set the drain loop uses so stale ops under secondary keys
  // (replyTarget, controllerStateKey) can't survive across turns.
  if (senderRole === "customer") {
    try {
      clearResponderStateOps(conversationId, [
        replyTarget || "",
        controllerStateKey,
        `${account.accountId}::${conversationId}`,
      ]);
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
  // Authority cutover phase 2 (2026-04-23): the server-composed
  // "pickup or delivery?" reply (`deterministic_location_clarification`)
  // was a pre-LLM early-return author. It wrote `pendingLocation` to
  // the draft, sent a canned Arabic/English clarification, and then
  // bypassed the LLM entirely. On the follow-up turn (customer answers
  // "delivery pls") the stage was still `idle` / bookingStep=`none`,
  // the LLM saw no evidence of a booking in progress, and fell back
  // to a welcome reply — the exact "Delivery pls → welcome reset"
  // failure from the 2026-04-23 transcript. We now only persist the
  // shared location; `pending_shared_location` surfaces in the prompt
  // and the LLM composes the follow-up itself.
  if (
    senderRole === "customer" &&
    replyTarget &&
    conversationControllerEntry &&
    resolvedLocation &&
    persistedResolvedLocation &&
    (conversationControllerEntry.bookingStep || "none") === "none" &&
    conversationControllerEntry.stage !== "collecting_booking_details" &&
    conversationControllerEntry.stage !== "summary_shown" &&
    conversationControllerEntry.stage !== "awaiting_confirmation" &&
    conversationControllerEntry.stage !== "order_submitted"
  ) {
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
    api.logger.info(
      `[controller] shared-location persisted as pendingLocation conversation=${conversationId} area=${JSON.stringify(nearestAreaName || resolvedLocation?.name || resolvedLocation?.address || "")}`,
    );
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
          if (boundaryRes.normalizations.length > 0) {
            for (const n of boundaryRes.normalizations) {
              try {
                api.logger.info(
                  `[one-brain/boundary/normalize] kind=${n.kind} field=${n.field} incoming=${JSON.stringify(n.incoming)} mapped_to=${JSON.stringify(n.mappedTo)} source=${n.source} conversation=${conversationId}`,
                );
              } catch {}
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

  // ------------------------------------------------------------------
  // Cut #6 (2026-04-23, Reloc 5 input-side): pre-LLM prompt-shaping
  // disposition.
  //
  // DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_CALLSITE_MARKER.
  //
  // Runs BEFORE the LLM invocation (we're building the system prompt
  // here). The disposition is computed from server-side signals only —
  // stage, active quoted route, requested slot, missing-field count,
  // customer inbound text. Proposer output is NOT available at this
  // point in the turn (it comes back FROM the LLM call that consumes
  // this prompt). That's why this layer is distinct from Cut #5's
  // `decideTurnDisposition`, which runs AFTER the LLM returns on the
  // output side with the full proposer reading.
  //
  // Asymmetry is intentional: the pre-LLM layer is a weaker
  // classifier (regex-level), and its job is prompt shaping only. The
  // post-LLM layer stays authoritative for output decisions. Neither
  // reads the other's output. The four-cell matrix
  // (pre × post disposition) guarantees every combination is
  // ≥ today's behaviour; see `turn-disposition.ts` for the proof.
  //
  // Default OFF during bake (env `RIDERS_PROMPT_DISPOSITION_SHAPE_LIVE`
  // must be explicitly `on` to enable). The one-line rollback is
  // unset the var. When off, `promptShapingDisposition` is forced
  // null and the prompt is identical to today.
  //
  // Trace: `[prompt-disposition/shaping]` — one line per customer
  // turn, emitted UNCONDITIONALLY (even when env-off and even on
  // `continue_step`), so a triager can grep per-conversation and see
  // flag, disposition, policy_rule, whether state imperatives were
  // skipped, whether hard rules were shaped, stage, has_quote.
  // ------------------------------------------------------------------
  const promptShapingEnvLive =
    (process.env.RIDERS_PROMPT_DISPOSITION_SHAPE_LIVE || "off")
      .trim()
      .toLowerCase() === "on";
  // Cut 7b (2026-04-23): the pre-LLM disposition is now consumed by
  // TWO downstream effects — prompt-shaping (Cut #6) AND the
  // A0/A0a/A0b arming gate (Cut 7b, downstream at Region A). Each
  // effect has its own env flag. The DECISION itself must be computed
  // unconditionally for customer turns so both gates can read the
  // same disposition value, and the matrix trace stays observable
  // even when both effects are dark.
  //
  // DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_DECISION_UNCONDITIONAL_MARKER.
  let promptShapingDecision: TurnDispositionDecision | null = null;
  if (senderRole === "customer") {
    try {
      promptShapingDecision = computePromptShapingDisposition({
        customer_text: rawBody ?? null,
        stage_at_turn_start: conversationControllerEntry?.stage ?? null,
        has_active_quoted_route: !!activeQuotedRoute,
        requested_slot_name:
          conversationControllerEntry?.dialogState?.requestedSlot?.name ??
          null,
        missing_fields_count:
          conversationControllerEntry?.bookingDraft
            ? computeOneBrainMissingFields(
                conversationControllerEntry.bookingDraft,
                conversationControllerEntry,
              ).length
            : 0,
        detectors: {
          isInformationalOptionQuestion,
          isSimpleGreeting,
          isExplicitOrderConfirmation,
          isContextualClarifyingQuestion,
        },
      });
    } catch (promptShapingError) {
      try {
        api.logger.warn(
          `[prompt-disposition/shaping] derive_failed conversation=${conversationId} error=${
            promptShapingError instanceof Error
              ? promptShapingError.message
              : String(promptShapingError)
          }`,
        );
      } catch {
        // Never block the turn on trace-layer errors.
      }
      promptShapingDecision = null;
    }
  }
  // Disposition passed to the prompt builder — `null` when the
  // Cut #6 env flag is off or when the disposition is `continue_step`
  // (identity path). The decision itself remains in
  // `promptShapingDecision` for the trace and the Cut 7b arming gate.
  const promptShapingDispositionForPrompt =
    promptShapingEnvLive &&
    promptShapingDecision &&
    promptShapingDecision.disposition !== "continue_step"
      ? promptShapingDecision.disposition
      : null;
  const promptShapingStateImperativesSkipped = Boolean(
    promptShapingDispositionForPrompt,
  );
  if (senderRole === "customer") {
    try {
      api.logger.info(
        `[prompt-disposition/shaping] conversation=${conversationId} flag=${
          promptShapingEnvLive ? "on" : "off"
        } disposition=${
          promptShapingDecision?.disposition ?? "-"
        } policy_rule=${
          promptShapingDecision?.policy_rule ?? "-"
        } state_imperatives_skipped=${
          promptShapingStateImperativesSkipped ? "yes" : "no"
        } hard_rules_shaped=${
          promptShapingStateImperativesSkipped ? "yes" : "no"
        } stage=${conversationControllerEntry?.stage ?? "-"} has_quote=${
          activeQuotedRoute ? "yes" : "no"
        } requested_slot=${
          conversationControllerEntry?.dialogState?.requestedSlot?.name ?? "-"
        } fallthrough=${
          promptShapingDecision?.trace_annotations?.fallthrough_reason ?? "-"
        }`,
      );
    } catch {
      // Never block the turn on trace emit failure.
    }
  }

  // --------------------------------------------------------------------
  // Cut 9.0 (2026-04-23): Turn Router dispatch.
  //
  // DEPLOY_CANARY_TURN_ROUTER_CALLSITE_MARKER.
  //
  // Top-level meaning-first dispatcher. Runs once per customer turn,
  // AFTER the pre-LLM heuristic classifier has produced
  // `promptShapingDecision`, and BEFORE any state-machine authoring or
  // Region-A substitution arms. Classifies the turn into a router
  // MODE and exposes three consumer flags (`invoke_state_machine`,
  // `shape_prompt_imperatives`, `invoke_region_a_substitutions`).
  //
  // Scaffold landing: decision is computed unconditionally for customer
  // turns; trace `[turn-router/dispatch]` emits every turn so a triager
  // can read the router's would-have decision even with the flag off.
  // Exactly ONE consumer is wired below (the Cut #5 state-machine
  // authoring gate at the Region-B author block); that consumer
  // additionally guards on `default_mode === "meaning_first"` so under
  // the legacy default the router's flags are inert. See
  // `plugins/shared/turn-router.ts` for the full rationale.
  //
  // Env flag: `RIDERS_TURN_ROUTER_DEFAULT_MODE`
  //   * unset / "advance_form" (default) — legacy behaviour; zero change.
  //   * "meaning_first"                   — fallthrough continue_step
  //                                         routes to `answer`; state
  //                                         machine authoring is
  //                                         suppressed on uncertain turns.
  // --------------------------------------------------------------------
  const turnRouterDefaultMode: TurnRouterDefaultMode =
    parseTurnRouterDefaultModeEnv(
      process.env.RIDERS_TURN_ROUTER_DEFAULT_MODE,
    );
  let turnRouterDecision: TurnRouterDecision | null = null;
  if (senderRole === "customer") {
    try {
      turnRouterDecision = classifyTurn({
        classifier_decision: promptShapingDecision,
        default_mode: turnRouterDefaultMode,
      });
    } catch (turnRouterError) {
      try {
        api.logger.warn(
          `[turn-router/dispatch] derive_failed conversation=${conversationId} error=${
            turnRouterError instanceof Error
              ? turnRouterError.message
              : String(turnRouterError)
          }`,
        );
      } catch {
        // Never block the turn on trace-layer errors.
      }
      turnRouterDecision = null;
    }
    try {
      api.logger.info(
        `[turn-router/dispatch] conversation=${conversationId} default_mode=${turnRouterDefaultMode} mode=${
          turnRouterDecision?.mode ?? "-"
        } reason=${
          turnRouterDecision?.reason ?? "-"
        } default_applied=${
          turnRouterDecision?.default_applied ? "yes" : "no"
        } positive_evidence=${
          turnRouterDecision?.positive_evidence ?? "-"
        } invoke_state_machine=${
          turnRouterDecision
            ? turnRouterDecision.invoke_state_machine
              ? "yes"
              : "no"
            : "-"
        } shape_prompt_imperatives=${
          turnRouterDecision
            ? turnRouterDecision.shape_prompt_imperatives
              ? "yes"
              : "no"
            : "-"
        } invoke_region_a_substitutions=${
          turnRouterDecision
            ? turnRouterDecision.invoke_region_a_substitutions
              ? "yes"
              : "no"
            : "-"
        } classifier_disposition=${
          turnRouterDecision?.trace_annotations?.classifier_disposition ?? "-"
        } classifier_policy_rule=${
          turnRouterDecision?.trace_annotations?.classifier_policy_rule ?? "-"
        } classifier_fallthrough=${
          turnRouterDecision?.trace_annotations?.classifier_fallthrough_reason ??
          "-"
        } stage=${conversationControllerEntry?.stage ?? "-"} has_quote=${
          activeQuotedRoute ? "yes" : "no"
        }`,
      );
    } catch {
      // Never block the turn on trace emit failure.
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
    promptShapingDisposition: promptShapingDispositionForPrompt,
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

  // Class-11 fix (2026-04-21): `stripped_tool_ctx_loses_conversation_identity`.
  //
  // OpenClaw hands a thinner ctx into `tool.execute(...)` than the one we
  // build here via `finalizeInboundContext`. When the LLM calls `get_price`
  // on a clarification turn, `markPendingArea` / `markRequestedAreaSlot`
  // get a ctx with null `ConversationId`/`SessionKey`/`ControllerStateKey`
  // and cannot push responder-state ops under any key, so every clarify
  // write is silently dropped.
  //
  // Mirror of `__ridersLastCustomerText` above: publish the current turn's
  // identity on a well-known `globalThis` key that
  // `plugins/riders-tools/lib/tool-conversation-ids.ts` reads as a FALLBACK
  // (only when the ctx itself carries nothing). Keeping this as an
  // ingress-side write avoids a cross-plugin import (see class-10 for the
  // prior evidence that bundles sometimes split).
  //
  // The stash is TTL-guarded (5 min) and refreshed on every inbound turn,
  // so it cannot bleed across conversations under any realistic load.
  //
  // Class-17 fix (2026-04-21): `stripped_tool_ctx_loses_booking_authority`.
  //
  // Class 11 restored conversation identity on a stripped ctx, but the
  // symmetric-rebind + DST misroute guards inside `pricing.ts` also need
  // the booking authority (pending area pins, DST `requestedSlot`) that
  // `getNormalizedBookingAuthority(ctx)` would normally read from the ctx.
  // That helper is gated on `isCustomerOctopusContext(ctx)` which requires
  // `ctx.Surface`/`ctx.OriginatingChannel`/`ctx.ConversationLabel` — all
  // of which are ALSO stripped by the same runtime path that lost
  // conversation id. So the guards silently no-op and a symmetric
  // `get_price(pickup=X, dropoff=X)` from the LLM survives all the way
  // through to the outbound `route_zero_distance` recovery reply.
  //
  // The fix is deliberately narrow: extend the same well-known stash with a
  // minimal authority snapshot (pending areas + requestedSlot + stage /
  // bookingStep), refreshed on every inbound. Consumers in the tool path
  // prefer the ctx-derived authority, and only fall back to the stash when
  // ctx is stripped. Same discipline as class-11.
  if (senderRole === "customer") {
    const stashedRequestedSlot =
      conversationControllerEntry?.dialogState?.requestedSlot ?? null;
    (globalThis as any).__ridersCurrentTurnIdentity__ = {
      conversationId: String(conversationId || ""),
      sessionKey: String(sessionKey || ""),
      controllerStateKey: String(controllerStateKey || ""),
      replyTarget: String(replyTarget || ""),
      senderId: String(senderId || ""),
      bookingAuthority: conversationControllerEntry
        ? {
            stage: String(conversationControllerEntry.stage || "idle"),
            bookingStep: String(conversationControllerEntry.bookingStep || "none"),
            pendingPickupAreaNameEn:
              conversationControllerEntry.pendingPickupAreaNameEn ?? null,
            pendingPickupAreaNameAr:
              conversationControllerEntry.pendingPickupAreaNameAr ?? null,
            pendingDropoffAreaNameEn:
              conversationControllerEntry.pendingDropoffAreaNameEn ?? null,
            pendingDropoffAreaNameAr:
              conversationControllerEntry.pendingDropoffAreaNameAr ?? null,
            requestedSlot: stashedRequestedSlot
              ? {
                  name: String(stashedRequestedSlot.name || ""),
                  options: Array.isArray(stashedRequestedSlot.options)
                    ? [...stashedRequestedSlot.options]
                    : null,
                }
              : null,
          }
        : null,
      ts: Date.now(),
    };
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
  //
  // Class-15 bypass gate (2026-04-21): snapshot the wall-clock at dispatcher
  // entry. Inside `deliver` we compare `sessionGuard.lastToolTs >=
  // turnStartMs` to determine whether `get_price` fired during THIS turn
  // versus at any earlier time. Captured outside the closure so the check
  // is robust to sessionGuard being loaded AFTER the LLM + tool calls
  // complete.
  const turnStartMs = Date.now();
  try {
    await api.runtime.channel.reply.dispatchReplyWithBufferedBlockDispatcher({
      ctx: ctxPayload,
      cfg: api.config,
      dispatcherOptions: {
        deliver: async (payload: any) => {
          let replyText = asTrimmedString(payload?.text);
          // Relocation 2 (A4 → layer) input: snapshot the LLM's raw
          // reply text length BEFORE any pre-state / post-state
          // substitution overwrites `replyText`. Consumed by the
          // `turn-decision` derive-dispatch path as
          // `a4_inputs.llm_reply_empty`. Safe to capture here because
          // `replyText` at this point is strictly the LLM author's
          // reply as surfaced by the buffered block dispatcher.
          const originalLlmReplyChars =
            typeof replyText === "string" ? replyText.length : 0;
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
          // Phase D baseline (2026-04-21): drift counter pre-turn snapshot.
          //
          // Observation-only: the `[drift/get-price-bypass]` log emitted at
          // the end of this turn classifies `turn_kind` as either
          // `initial_route` (route-evidence inbound on an idle conversation)
          // or `post_clarify_continuation` (a clarification was pinned at
          // turn start and the customer is answering it). The classification
          // has to be based on the controller state BEFORE the drain
          // possibly rewrites `pendingPickup/DropoffAreaNameEn` or
          // `requestedSlot`, so these snapshots live alongside
          // `stageAtTurnStart`. No behavior reads them. See the emit-site
          // below marked `[drift/get-price-bypass]` for the log contract.
          const pendingPickupAtTurnStart =
            conversationControllerEntry?.pendingPickupAreaNameEn ?? null;
          const pendingDropoffAtTurnStart =
            conversationControllerEntry?.pendingDropoffAreaNameEn ?? null;
          const requestedSlotNameAtTurnStart =
            conversationControllerEntry?.dialogState?.requestedSlot?.name ?? null;
          const requestedSlotOptionsAtTurnStart = Array.isArray(
            conversationControllerEntry?.dialogState?.requestedSlot?.options,
          )
            ? [
                ...(conversationControllerEntry!.dialogState!.requestedSlot!
                  .options as string[]),
              ]
            : null;
          const hadActiveQuotedRouteAtTurnStart = Boolean(activeQuotedRoute);
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
          // Class-level guard (2026-04-21): `stale_guard_state_clobbers_clarification_turn`.
          //
          // The quoted-state promotion block further down inherits
          // `stage=quoted` + `quote*AreaNameEn` from `sessionGuard.lastQuotedRoute`
          // whenever `lastToolName === "get_price"` and `lastToolTs !==
          // controllerEntry.quoteTs`. This is the correct behaviour on a turn
          // where `get_price` actually produced a fresh priced route, but the
          // gate is SIGN-BLIND: a persisted `lastQuotedRoute` left over from
          // a prior session (persisted to
          // `~/.openclaw-<profile>/riders-guard-state.json`) survives service
          // restart and still satisfies the test on the very next turn —
          // even when that turn's `get_price` returned AREA_AMBIGUOUS and
          // therefore set `set_requested_slot(pickup_area|dropoff_area)`.
          // The false promotion then clears `pendingPickupAreaNameEn` /
          // `pendingDropoffAreaNameEn` ("just promoted to quote*") and
          // overwrites the fresh clarification with a stale route —
          // breaking the invariant that the controller state must reflect
          // THIS turn's tool results.
          //
          // `turnDrainedRouteSideClarification` is set inside the drain loop
          // whenever a `set_requested_slot` for a route-side slot is applied.
          // Its presence proves that the current turn is mid-clarification,
          // and the quoted-state promotion block uses it as a hard veto.
          let turnDrainedRouteSideClarification = false;
          // Phase A shadow (2026-04-21): captures the raw decision payload
          // from the `proposed_turn_decision` responder-op so the
          // post-decision `[structured-output/proposer]` emit can run
          // `validateProposedTurnDecision` once and cross-reference
          // `planned_tool_calls` / `pricing_decision.action` against this
          // turn's actual tool invocations. Hoisted outside the drain
          // block for the same reason as `turnDrainedRouteSideClarification`
          // — observation must survive beyond the drain scope.
          let proposedTurnDecisionRaw: unknown = null;
          let proposedTurnDecisionCount = 0;
          let proposedTurnDecisionTurnId: string | null = null;
          // Distinct responder-op kinds that were actually drained this
          // turn. Used by the `[structured-output/proposer]` emit to
          // compare against the LLM's `planned_tool_calls`. Observation
          // only — populated alongside the main drain loop.
          const turnDrainedOpKinds = new Set<string>();
          // v1.1 (2026-04-22): stage the LLM was observing when it decided
          // whether to include `awaiting_confirmation` in its proposer
          // payload. Captured BEFORE drain-driven stage promotions so the
          // `[structured-output/proposer]` emit can decide whether the
          // classification was expected or not. Reads from the persisted
          // entry at the top of the turn; the value is read by the emit
          // block much further below. `unknown` type keeps the captured
          // value opaque to callers other than the emit.
          const currentControllerStageForProposerEmit: string | null =
            conversationControllerEntry &&
            typeof conversationControllerEntry.stage === "string"
              ? conversationControllerEntry.stage
              : null;
          // ONE-BRAIN mode: simplified drain. One LLM per turn owns all reply
          // copy; we only merge booking patches into the draft, reset on cancel,
          // and flag handoff. No stage/step/hint threading, no deterministic
          // summary override — the LLM writes the summary itself when ready.
          if (senderRole === "customer") {
            try {
              // Drain under every identifier the tool might have used to
              // push responder ops. The Octopus tool-context occasionally
              // carries an id that disagrees with the orchestrator's local
              // `conversationId` (SessionKey vs `To=octopus:<wa>` vs
              // NativeChannelId). Without the alias merge, an op pushed
              // under `96599338566` would be lost when drain only looked
              // up `19055`. See `pushResponderStateOp` / `drainResponderStateOps`
              // and `smoke-test-area-clarification-binding.mjs` for the
              // first-turn clarify invariant this protects.
              const drainAliases: string[] = [];
              const seenDrainAlias = new Set<string>();
              const addDrainAlias = (raw: string | null | undefined) => {
                const key = String(raw || "").trim();
                if (!key || seenDrainAlias.has(key)) return;
                seenDrainAlias.add(key);
                drainAliases.push(key);
              };
              addDrainAlias(conversationId);
              addDrainAlias(replyTarget);
              addDrainAlias(controllerStateKey);
              addDrainAlias(
                `${account.accountId}::${conversationId}`,
              );
              // Class-10 observability: emit an unconditional line so we
              // can correlate drain entry with same-turn pushes even when
              // drained=[]. See `responder-state-ops.ts` for the paired
              // buffer-level counters.
              try {
                api.logger.info(
                  `[one-brain/drain-attempt] conversation=${conversationId} aliases=${JSON.stringify(drainAliases)}`,
                );
              } catch {}
              const drained = drainResponderStateOps(conversationId, drainAliases);
              if (drained.length > 0) {
                let nextDraft = conversationControllerEntry?.bookingDraft || createEmptyBookingDraft();
                let nextDialogState = conversationControllerEntry?.dialogState ?? null;
                let cancelled = false;
                let handoffRequested = false;
                const rejections = hallucinationGuardRejections;
                const appliedOps: string[] = [];
                for (const op of drained) {
                  // Phase A shadow observation: accumulate the distinct
                  // responder-op kinds seen this turn. The
                  // `[structured-output/proposer]` emit downstream
                  // compares this set against the LLM's declared
                  // `planned_tool_calls`. Observation only.
                  try {
                    const kind = String((op as { op?: unknown }).op || "");
                    if (kind) turnDrainedOpKinds.add(kind);
                  } catch {}
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
                    //
                    // 2026-04-22 — same-turn cross-side phone guard.
                    // Live conv 19399: the customer answered
                    // ASK_SENDER_PHONE with a single number, the
                    // fast-path correctly pre-applied it to
                    // `sender_phone`, but then the LLM's
                    // apply_booking_field mirrored the SAME digit
                    // string into `recipient_phone` in the very next
                    // op. The boundary accepted it (the slot was
                    // empty), silently corrupting the recipient side.
                    // Rule: once the fast-path has resolved one side's
                    // phone on this turn, drop any counterpart-side
                    // phone on the LLM's patch. Symmetric for sender
                    // and recipient so a future
                    // ASK_RECIPIENT_NAME_AND_PHONE / sender-mirror
                    // variant lands the same way. The guard only
                    // masks the cross-side field; same-side phone
                    // writes remain idempotent (boundary returns
                    // unchanged).
                    const crossSideGuard = applyCrossSidePhoneGuard({
                      fastPathPreApplied,
                      senderPhone: op.sender_phone ?? null,
                      recipientPhone: op.recipient_phone ?? null,
                    });
                    for (const drop of crossSideGuard.drops) {
                      try {
                        api.logger.warn(
                          `[one-brain/drain/cross-side-phone-drop] conversation=${conversationId} fast_path_applied=${drop.triggeredBy} dropped_llm_field=${drop.field} value=${JSON.stringify(drop.value)} reason=${drop.reason} turn_id=${op.turn_id || "-"}`,
                        );
                      } catch {}
                      rejections.push({
                        field: drop.field,
                        reason: drop.reason,
                        received: drop.value,
                      });
                    }
                    const llmSenderPhone = crossSideGuard.senderPhone;
                    const llmRecipientPhone = crossSideGuard.recipientPhone;
                    const proposal: Proposal = llmProposal({
                      op: {
                        sender_name: op.sender_name ?? null,
                        sender_phone: llmSenderPhone,
                        phone_decision: (op.phone_decision as any) ?? null,
                        recipient_name: op.recipient_name ?? null,
                        recipient_phone: llmRecipientPhone,
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
                    // 2026-04-22 sender-step incident: surface the
                    // WhatsApp-equivalence normalization so live traces
                    // show when a sender_phone write collapsed into a
                    // `phone_decision=use_whatsapp` patch at the
                    // boundary. Defense-in-depth against both fast-path
                    // and LLM writes of the customer's own number.
                    if (boundaryRes.normalizations.length > 0) {
                      for (const n of boundaryRes.normalizations) {
                        try {
                          api.logger.info(
                            `[one-brain/boundary/normalize] kind=${n.kind} field=${n.field} incoming=${JSON.stringify(n.incoming)} mapped_to=${JSON.stringify(n.mappedTo)} source=${n.source} conversation=${conversationId} turn_id=${op.turn_id || "-"}`,
                          );
                        } catch {}
                      }
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
                    //
                    // First-turn clarify hydration (2026-04-21): on a fresh
                    // conversation the controller's dialogState may be null
                    // (DST disabled, or an older persisted row). We still
                    // want server-owned clarification to survive into the
                    // next turn, so seed an empty dialog state here before
                    // applying the op instead of silently dropping it.
                    // This is the category fix for the
                    // `salmiya → kuwait city pls` scenario where
                    // `markRequestedAreaSlot("dropoff_area", [...])` fired
                    // but the controller entry still arrived at turn 2 with
                    // `requestedSlot=null`, letting `bnaid al qar` be free-
                    // bound by the LLM instead of routed deterministically.
                    if (!nextDialogState) {
                      nextDialogState = createEmptyDialogState();
                    }
                    nextDialogState = setRequestedSlot(nextDialogState, {
                      name: op.slot as SlotName,
                      options: op.options ?? null,
                      askedTs: Date.now(),
                    });
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
                  } else if (op.op === "proposed_turn_decision") {
                    // Phase A (2026-04-21) — shadow-mode typed proposer
                    // output. Carried through so the post-drain emit
                    // can run `validateProposedTurnDecision` and compare
                    // `planned_tool_calls` / `pricing_decision.action`
                    // against this turn's actual tool invocations.
                    // Emitting the op does NOT mutate any state and
                    // does NOT gate any behavior — see
                    // `[structured-output/proposer]` emit for the
                    // conformance signal we log instead.
                    proposedTurnDecisionCount += 1;
                    if (proposedTurnDecisionCount === 1) {
                      proposedTurnDecisionRaw = (
                        op as { decision: unknown }
                      ).decision;
                      proposedTurnDecisionTurnId =
                        (op as { turn_id?: string }).turn_id || null;
                    }
                    appliedOps.push(
                      `proposed_turn_decision:shadow${proposedTurnDecisionCount > 1 ? `(dup=${proposedTurnDecisionCount})` : ""}`,
                    );
                  } else if (op.op === "start_booking" || op.op === "confirm_summary") {
                    // One-brain ignores these — `apply_booking_field` and
                    // `create_simple_order` are the only signals we care about.
                    appliedOps.push(`${op.op}:ignored`);
                  } else {
                    // Phase 5 (2026-04-20): unknown responder op kinds.
                    // The discriminated-union `ResponderStateOp` covers
                    // every known op at build time, so reaching this
                    // branch implies either (a) a tool pushed an op
                    // with a new kind that the drain loop hasn't been
                    // updated to handle, or (b) a malformed op escaped
                    // the push-time validator. Log it as a warn so
                    // drift in the responder-op contract is surfaced
                    // rather than silently dropped. Behavior unchanged:
                    // the op is not applied.
                    const unknownKind = String(
                      (op as { op?: unknown }).op || "",
                    ).slice(0, 40);
                    appliedOps.push(`unknown_op:${unknownKind}`);
                    api.logger.warn(
                      `[one-brain/drain] unknown_op conversation=${conversationId} op=${JSON.stringify(op).slice(0, 200)}`,
                    );
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
                  //
                  // Also promote the controller stage from `idle` to
                  // `collecting_booking_details` when any `set_pending_area`
                  // op fires. This is the structural fix for the
                  // 2026-04-21 area-clarification binding regression:
                  // when the pricing tool resolves one leg and asks for
                  // the other (ambiguous) leg, we need
                  // `computeOneBrainNextRequiredAction` to dispatch the
                  // `ASK_PICKUP_AREA` / `ASK_DELIVERY_AREA` directive, and
                  // that dispatcher only fires when stage is
                  // `collecting_booking_details` or `quoted`. Before this
                  // promotion, stage stayed at `idle` because no
                  // `apply_booking_field` patch fired on the clarification
                  // turn, so `applyBookingDraftProgress` was never
                  // invoked — leaving the LLM free to compose the
                  // clarification itself, drop the pending-side recap,
                  // and on the next turn rebind symmetrically (
                  // `get_price(pickup=Mirqab, dropoff=Mirqab)`).
                  //
                  // See `smoke-test-area-clarification-binding.mjs` for
                  // the exact regression coverage.
                  let appliedPendingArea = false;
                  let appliedRequestedSlot: {
                    slot: SlotName;
                    options: readonly string[] | null;
                  } | null = null;
                  if (!cancelled) {
                    for (const op of drained) {
                      if (op.op !== "set_pending_area") continue;
                      appliedPendingArea = true;
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
                    for (const op of drained) {
                      if (op.op !== "set_requested_slot") continue;
                      appliedRequestedSlot = {
                        slot: op.slot as SlotName,
                        options: op.options ?? null,
                      };
                      // Lift the class-level veto flag (see the declaration
                      // of `turnDrainedRouteSideClarification` above). Only
                      // route-side slot asks can be confused with a fresh
                      // priced route; slot asks for name / phone / address
                      // are orthogonal to the quoted-state promotion.
                      if (
                        op.slot === "pickup_area" ||
                        op.slot === "dropoff_area"
                      ) {
                        turnDrainedRouteSideClarification = true;
                      }
                    }
                    // First-turn clarify hydration (category fix, 2026-04-21).
                    //
                    // Whenever the drain saw ANY of:
                    //   - set_pending_area (one route leg just resolved)
                    //   - set_requested_slot (pricing asked the customer to
                    //     disambiguate an area slot)
                    // we must guarantee that the controller entry carries
                    // committed clarification state into the next turn. If
                    // the pre-drain controller was still `idle` (fresh
                    // conversation, no prior booking activity), stage must
                    // be promoted to `collecting_booking_details` so:
                    //   (a) `computeOneBrainNextRequiredAction` fires its
                    //       area-clarification gate and returns ASK_PICKUP_AREA
                    //       / ASK_DELIVERY_AREA
                    //   (b) Region-A substitutes the server-composed
                    //       clarification reply, so attribution is
                    //       `reply_author=server` instead of LLM free-compose.
                    //   (c) the next turn's guards (symmetric-rebind,
                    //       clarification recovery) see the pinned opposite-
                    //       side area and the requested_slot register and
                    //       route the customer's short answer correctly.
                    //
                    // Pre-fix: this promotion was gated on `set_pending_area`
                    // only. The `Kuwait City` dropoff case is ambiguous
                    // (NO leg resolves deterministically at the first
                    // `get_price` call — only the pickup resolves; dropoff
                    // goes straight to `markRequestedAreaSlot` without a
                    // prior `markPendingArea`), so when ONLY a
                    // `set_requested_slot` op was drained, stage stayed at
                    // `idle` and none of the above guarantees held.
                    if (
                      (appliedPendingArea || appliedRequestedSlot) &&
                      nextEntry.stage === "idle"
                    ) {
                      nextEntry = {
                        ...nextEntry,
                        stage: "collecting_booking_details",
                        bookingStep:
                          nextEntry.bookingStep === "none"
                            ? resolveNextBookingStepFromDraft(
                                nextEntry.bookingDraft,
                              )
                            : nextEntry.bookingStep,
                      };
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
                    // ----------------------------------------------------
                    // Cut #4 (2026-04-23) — DST conflict-slot pinning.
                    // DEPLOY_CANARY_DST_CONFLICT_SLOT_PIN_MARKER
                    //
                    // When any DST slot is `status: "conflict"`, the
                    // directive gate in computeOneBrainNextRequiredAction
                    // forces CONFIRM_SLOT_CONFLICT(field). `requestedSlot`
                    // must mirror that choice so the NEXT turn's prompt
                    // context and apply-boundary guards route the
                    // customer's disambiguation reply back to the
                    // conflict slot — not whichever downstream slot
                    // happens to be missing next.
                    //
                    // Source-of-bug: `deriveRequestedSlotFromMissing`
                    // walks only the MISSING-field markers. A slot in
                    // conflict is still "filled" at draft-level (the
                    // incumbent value is mirrored back), so it is
                    // INVISIBLE to that derivation. Missing-field
                    // derivation would therefore walk past the open
                    // conflict to the next missing slot (e.g.
                    // sender_phone while sender_name is still in
                    // conflict), producing a split-brain: directive
                    // gate says CONFIRM_SLOT_CONFLICT(sender_name),
                    // requestedSlot drifts to sender_phone. Later
                    // turns (especially `ok`/acknowledgement) then
                    // re-arm the conflict against a prompt context
                    // that no longer pointed to the right slot,
                    // producing the 2026-04-23 "aziz vs ahmad" loop.
                    //
                    // Fix: pin requestedSlot to the first conflict
                    // slot whenever one exists. This runs BEFORE the
                    // tool-pushed-requested check AND before the
                    // missing-field derivation so the conflict always
                    // wins at the requested-slot register. It is a
                    // no-op when no slot is in conflict.
                    //
                    // Invariant: findFirstConflictSlot() uses the same
                    // "first entry in Object.entries(slots) where
                    // status==='conflict'" rule as the one-brain
                    // conflict gate — keep them in lockstep.
                    // ----------------------------------------------------
                    const conflictSlotForPin = findFirstConflictSlot(
                      nextEntry.dialogState,
                    );
                    if (conflictSlotForPin) {
                      if (
                        !existingRequested ||
                        existingRequested.name !== conflictSlotForPin
                      ) {
                        nextEntry = {
                          ...nextEntry,
                          dialogState: setRequestedSlot(
                            nextEntry.dialogState,
                            {
                              name: conflictSlotForPin,
                              options: null,
                              askedTs: Date.now(),
                            },
                          ),
                        };
                        try {
                          api.logger.info(
                            `[dst-conflict-pin] conversation=${conversationId} pinned_slot=${conflictSlotForPin} prior_requested=${existingRequested?.name || "-"}`,
                          );
                        } catch {
                          // Never block the turn on log failures.
                        }
                      }
                    } else {
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
                  }
                  conversationControllerEntry = nextEntry;
                  await upsertConversationControllerEntry(controllerStateKey, conversationControllerEntry);
                  mirrorConversationControllerEntry(controllerStateKey, conversationControllerEntry);
                  // First-turn clarification-commit invariant (2026-04-21).
                  // Explicit log so the `reply_author=llm` + `stage=idle`
                  // regression from the area-clarification canary can be
                  // caught the moment it recurs. If this line is emitted
                  // but the NEXT turn's prompt context reads
                  // `stage=idle / requested_slot=null`, the bug is in the
                  // persisted-read path (controller expiry, sanitizer,
                  // seedDialogStateFromDraft), not in the drain.
                  if (appliedPendingArea || appliedRequestedSlot) {
                    try {
                      const committedRequested =
                        conversationControllerEntry.dialogState?.requestedSlot;
                      api.logger.info(
                        `[one-brain/clarify-commit] conversation=${conversationId} stage=${conversationControllerEntry.stage} step=${conversationControllerEntry.bookingStep} pending_pickup=${conversationControllerEntry.pendingPickupAreaNameEn || "-"} pending_dropoff=${conversationControllerEntry.pendingDropoffAreaNameEn || "-"} requested_slot=${committedRequested?.name || "-"} requested_options=${committedRequested?.options ? committedRequested.options.length : 0}`,
                      );
                      if (conversationControllerEntry.stage === "idle") {
                        api.logger.warn(
                          `[one-brain/clarify-commit] INVARIANT_VIOLATION stage still idle after clarify-commit conversation=${conversationId}`,
                        );
                      }
                    } catch {}
                  }
                }
                // Phase 4 (2026-04-20): server-synthesized request_handoff
                // on manual-confirm handoff turns.
                //
                // Before Phase 4, the `request_handoff` responder op was
                // only emitted by the LLM (via the `request_handoff`
                // tool). The manual-confirm handoff reply tells the
                // customer "one of our agents will reach out", but if
                // the LLM dropped the op the backend never learned
                // about the handoff — silent failure mode.
                //
                // This block inspects the post-drain controller state:
                // when the selected option is flagged
                // `manual_confirmation_required` AND both pickup +
                // delivery addresses are satisfied (the exact state
                // that makes `computeOneBrainNextRequiredAction` return
                // `REQUEST_HANDOFF_FOR_MANUAL_CONFIRM` and Region A
                // substitute the handoff reply), we guarantee the op
                // is accounted for. The Octopus `toagent` trigger is
                // independently wired via `shouldMoveToHumanAgent`
                // matching the handoff reply text, so this branch is
                // primarily about audit-trail consistency and the
                // `handoff=yes` log signal.
                //
                // Idempotent: LLM-emitted `request_handoff` already set
                // `handoffRequested = true`, so this block short-
                // circuits. Running on every turn the condition is met
                // is acceptable — the log line is the source of truth
                // for per-conversation handoff counts (GROUP BY
                // conversation).
                if (
                  !handoffRequested &&
                  conversationControllerEntry &&
                  activeQuotedRoute &&
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
                    const postDrainDraft = conversationControllerEntry.bookingDraft;
                    const pickupSatisfied = hasSatisfiedBookingAddress(
                      postDrainDraft,
                      "pickup",
                    );
                    const deliverySatisfied = hasSatisfiedBookingAddress(
                      postDrainDraft,
                      "delivery",
                    );
                    if (pickupSatisfied && deliverySatisfied) {
                      const synthesizedReason = `manual_confirm_${selectedOption.delivery_type}`;
                      handoffRequested = true;
                      appliedOps.push(
                        `request_handoff:server_synthesized(${synthesizedReason})`,
                      );
                      api.logger.info(
                        `[one-brain/server-handoff] synthesized conversation=${conversationId} reason=${synthesizedReason} route=${activeQuotedRoute.routeKey} option=${selectedOption.delivery_type}`,
                      );
                    }
                  }
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
          // Phase 5 (2026-04-20): per-turn reply-author attribution.
          // Populated by the pre-state block and updated (if the post-
          // state path overrides) after Regions B+C run. Emitted once
          // at the end of the turn as `[one-brain/reply-attribution]`
          // so a triager can grep per-conversation / per-account and
          // measure the server-composed vs LLM-composed vs fallback
          // ratio without re-deriving.
          let turnReplyAuthor: "server" | "llm" | "fallback" = "llm";
          let turnReplyReason: string = "allow";
          let turnReplyDirective: string | null = null;
          // Mirror of `directiveRenderContextForRender !== null` hoisted to
          // this outer scope so the `[turn-decision/trace]` scaffold emit
          // can read it. The source variable is declared inside the
          // pre-state decision branch (~line 5868) and goes out of scope
          // before the trace emit at the end of the turn.
          let turnReplyDirectiveRenderContextPresent = false;
          // Relocation 2 (A4 → layer) input: A1 substitute intent —
          // the pre-state decision's reason captured ONLY when the
          // pre-state pipeline became the reply author (i.e., A1
          // actually overrode the LLM). Null otherwise. The turn-
          // decision layer consumes this to derive its own dispatch
          // decision in parallel with A4.
          let turnA1SubstituteIntent: A1SubstituteIntent | null = null;
          // Relocation 3 (A1 → layer) inputs: mirrors of the three
          // legacy pre-state gate flags (`clarifyOptionBeforeProceed`,
          // `manualConfirmAddressAsk`, `manualConfirmHandoff`) hoisted
          // to this outer scope so the `[turn-decision/trace]` emit
          // at the end of the turn can read them. The source variables
          // are declared inside the Region-A block (~line 5818+) and
          // go out of scope before the trace emit site.
          //
          // DEPLOY_CANARY_TURN_DECISION_A1_CALLSITE_MARKER:
          //     Reloc 3 `a1_inputs` wiring
          let turnA1ClarifyOptionBeforeProceed = false;
          let turnA1ManualConfirmAddressAskSnapshot:
            | { side: "pickup" | "delivery"; option_type: string }
            | null = null;
          let turnA1ManualConfirmHandoffSnapshot:
            | { option_type: string }
            | null = null;
          // Provenance tracking (2026-04-22). Separate from Phase 5
          // `replyAuthor` / `reason`: those feed the existing
          // `[one-brain/reply-attribution]` line and downstream
          // dashboards; these four drive the new
          // `[outbound/provenance]` line and the `sendOctopusTextReply`
          // bypass assertion. Initial values reflect "pipeline hasn't
          // run yet" — if the turn exits without setting
          // `turnPostStateRan = true`, the derived provenance stays
          // `llm_unverified` and the wire-send emits at warn.
          let turnPostStateRan = false;
          let turnPostStateWasLightweight = false;
          let turnFinalDecision: OutboundDecisionKind = "allow";
          let turnFinalReason: OutboundDecisionReason = "allow";
          // Step-4 consolidation: Region A of the former inline decision
          // pipeline (canonical overwrite, empty-fill, price whitelist,
          // same-route quote correction) is now a single pure call. It runs
          // BEFORE the controller-state block so that any reply
          // substitution is visible to the `quotePresentedToCustomer`
          // computation — preserving pre-Step-4 behavior.
          {
            // ----------------------------------------------------------
            // Authority cutover phase 2 (2026-04-23): the Region-A
            // pre-LLM authors (A0 clarify-before-proceed, A0a manual-
            // confirm address-ask, A0b manual-confirm handoff) are
            // demoted to permanent no-ops. They used to arm from raw
            // text regex (`detectVagueProceedSignal`) + controller
            // flags and outrank the LLM's draft with server-composed
            // substitutions (the options-menu / address-ask / handoff
            // text). The LLM with the slimmed prompt composes all
            // three naturally from `route_options` / `selected_service`
            // / `manual_confirmation_required` facts.
            //
            // The three flag variables are kept as constants so the
            // downstream `decidePreStateOutbound` / turn-decision
            // trace plumbing still compiles; those consumers become
            // dead code and are removed in a follow-up phase.
            //
            // Deleted in this phase:
            //   * A0 arming env gate (RIDERS_A0_DISPOSITION_ARMING_GATE_LIVE)
            //   * `detectVagueProceedSignal` consumption at this callsite
            //   * `[a0-arming/disposition]` trace emission
            //   * `[one-brain/clarify-option]` / `[one-brain/manual-confirm]` traces
            //   * the three A0 arming canary markers
            // ----------------------------------------------------------
            const clarifyOptionBeforeProceed = false;
            const manualConfirmAddressAsk:
              | { side: "pickup" | "delivery"; option: RouteQuoteOption }
              | null = null;
            const manualConfirmHandoff:
              | { option: RouteQuoteOption }
              | null = null;
            turnA1ClarifyOptionBeforeProceed = false;
            turnA1ManualConfirmAddressAskSnapshot = null;
            turnA1ManualConfirmHandoffSnapshot = null;
            // --- legacy A0 arming block deleted; replacement ends here ---
            // Phase 2 (2026-04-20): compute the directive for this turn
            // and build the renderer context. The registry's
            // compile-time exhaustiveness guarantees every directive has
            // a spec — either a server renderer (we substitute), a
            // server-existing branch (handled by clarify /
            // manual-confirm substitutions above), or an llm_owned
            // marker (pass through). The substitute fires at Region A
            // block (A0c) below; see outbound-decision.ts.
            let directiveActionForRender: string | null = null;
            let directiveRenderContextForRender: DirectiveReplyRendererContext | null = null;
            if (conversationControllerEntry) {
              const missingForDirective = computeOneBrainMissingFields(
                conversationControllerEntry.bookingDraft,
                conversationControllerEntry,
              );
              const directive = computeOneBrainNextRequiredAction({
                draft: conversationControllerEntry.bookingDraft,
                entry: conversationControllerEntry,
                missing: missingForDirective,
                currentCustomerText: rawBody || null,
                activeQuotedRoute: activeQuotedRoute || null,
              });

              // ----------------------------------------------------------
              // Cut #5 (2026-04-23): Turn-disposition AUTHORING gate.
              //
              // DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_CALLSITE_MARKER.
              //
              // This is the Reloc 5 inversion going live at the output
              // side. The four prior cuts (A1 flip, Cut #1/#2/#3 directive
              // flip) removed state-machine authority one narrow rule at
              // a time: state still AUTHORED a directive every turn, and
              // the layer narrowly vetoed for correction / ack / the three
              // A1 semantic gates. Every other failure mode (side question,
              // route change mid-flow, cancel mid-collection) kept falling
              // through to the state machine's ASK_X directive.
              //
              // Cut #5 inverts the authoring axis. `decideTurnDisposition`
              // — already bake-shadowing via `observeTurnDecision` at turn
              // end — is consulted here, BEFORE `directiveActionForRender`
              // is assigned. When the layer classifies the turn as anything
              // other than `continue_step` (i.e. `answer` / `acknowledge` /
              // `requote` / `edit_field` / `cancel_confirmation` / `handoff`
              // / `idle`), the state-machine directive is NOT consumed:
              // `directiveActionForRender` stays null, A0c has nothing to
              // dispatch, and the LLM's draft survives through Region A.
              // Only `continue_step` falls through to exactly today's
              // behaviour (the state machine authors the ASK, A0c renders
              // it). This collapses the five shadow suppress rules plus
              // the two live directive-flip rules into one authoring gate
              // with a uniform trace shape.
              //
              // Orthogonal safeguards (the disposition derivation already
              // encodes most of these internally; we re-check the env flag
              // at the callsite for one-line rollback):
              //   1. Env flag `RIDERS_TURN_DISPOSITION_AUTHOR_LIVE` default
              //      "on"; explicit "off" restores legacy behaviour.
              //   2. Missing / invalid proposer → Rule 2 falls through to
              //      `continue_step` with `no_proposer` fallthrough reason.
              //      State grounds the turn.
              //   3. Low-confidence classifications that don't match a
              //      rule fall through to Rule 9's `continue_step`
              //      default. State grounds the turn.
              //   4. Hallucination guard fired on a manual-confirm route
              //      → Rule 3 emits `handoff`, state-machine directive
              //      is NOT re-emitted (the A0a/A0b manual-confirm
              //      branches in Region A still fire from their own
              //      flags). For non-manual-confirm routes with guard
              //      fired, default `continue_step` applies and the
              //      existing hallucination-guard repair paths (C1/C2)
              //      still run.
              //   5. Switch-option turns → Rule 9's
              //      `switch_option_skip` → `continue_step`. The A4
              //      recap path in `outbound-decision.ts` owns those
              //      as today.
              //
              // Trace: `[turn-disposition/authoring]` — one line per turn,
              // emitted UNCONDITIONALLY (even when env-off and even on
              // `continue_step`) so a triager can grep per-conversation
              // and see the full per-turn shape: flag, disposition,
              // policy_rule, whether state-machine authoring was skipped,
              // whether the prompt directive injection was skipped (always
              // `no` for this cut — prompt-side gate is a separate follow-
              // up since the proposer output isn't available at prompt-
              // build time), the legacy directive that would have been
              // authored, and the proposer signals that drove the choice.
              // ----------------------------------------------------------
              const dispositionAuthoringEnvOff =
                (process.env.RIDERS_TURN_DISPOSITION_AUTHOR_LIVE || "on")
                  .trim()
                  .toLowerCase() === "off";
              const dispositionProposerValidation = proposedTurnDecisionRaw
                ? validateProposedTurnDecision(proposedTurnDecisionRaw)
                : null;
              const dispositionProposerValue =
                dispositionProposerValidation &&
                dispositionProposerValidation.ok
                  ? dispositionProposerValidation.value
                  : null;
              const dispositionAddressedFields =
                dispositionProposerValue?.turn_intent?.addressed_fields ?? [];
              const dispositionMissingSet = new Set(missingForDirective);
              const dispositionAddressedMissing =
                dispositionAddressedFields.filter((f) =>
                  dispositionMissingSet.has(f),
                );
              const dispositionAddressedNonMissing =
                dispositionAddressedFields.filter(
                  (f) => !dispositionMissingSet.has(f),
                );
              const dispositionManualConfirmOption = activeQuotedRoute
                ? routeHasManualConfirmOption(activeQuotedRoute)
                : false;
              let authoringDisposition: TurnDispositionDecision | null = null;
              try {
                authoringDisposition = decideTurnDisposition({
                  proposer: dispositionProposerValue
                    ? {
                        turn_kind:
                          dispositionProposerValue.turn_kind ?? null,
                        ti_kind:
                          dispositionProposerValue.turn_intent?.kind ?? null,
                        ti_confidence:
                          dispositionProposerValue.turn_intent?.confidence ??
                          null,
                        ti_addressed_fields: dispositionAddressedFields,
                        ac_kind:
                          dispositionProposerValue.awaiting_confirmation
                            ?.kind ?? null,
                        po_kind:
                          dispositionProposerValue.post_order_intent?.kind ??
                          null,
                      }
                    : null,
                  addressed_missing_fields: dispositionAddressedMissing,
                  addressed_non_missing_fields: dispositionAddressedNonMissing,
                  state: {
                    stage_at_turn_start: stageAtTurnStart,
                    has_active_quoted_route: !!activeQuotedRoute,
                    active_quoted_route_has_manual_confirm_option:
                      dispositionManualConfirmOption,
                    has_summary_shown:
                      conversationControllerEntry?.stage === "summary_shown" ||
                      conversationControllerEntry?.stage ===
                        "awaiting_confirmation",
                    is_post_order:
                      conversationControllerEntry?.stage ===
                      "order_submitted",
                    missing_fields_count: missingForDirective.length,
                  },
                  tool_context: {
                    get_price_ran_this_turn:
                      turnDrainedOpKinds.has("get_price"),
                    start_booking_drained_this_turn:
                      turnDrainedOpKinds.has("start_booking"),
                    hallucination_guard_fired:
                      (hallucinationGuardRejections || []).length > 0,
                  },
                  hints: {
                    same_route_switch_option:
                      sameRouteQuoteAction?.kind === "switch_option",
                  },
                  state_machine_candidate_directive:
                    directive?.action ?? null,
                });
              } catch (dispositionDeriveError) {
                try {
                  api.logger.warn(
                    `[turn-disposition/authoring] derive_failed conversation=${conversationId} error=${
                      dispositionDeriveError instanceof Error
                        ? dispositionDeriveError.message
                        : String(dispositionDeriveError)
                    }`,
                  );
                } catch {
                  // Never block the turn on trace-layer errors.
                }
                authoringDisposition = null;
              }
              // Cut 9.0 (2026-04-23): Turn Router — state-machine
              // authoring consumer. The router's `invoke_state_machine`
              // flag is honoured HERE, but ONLY when the runtime default
              // is `meaning_first`. Under the legacy default
              // (`advance_form`), the router's flag is inert — Cut #5's
              // post-LLM `authoringDisposition` alone continues to gate.
              // This scaffolds the inversion without changing today's
              // behaviour: flag off → Cut #5 decides; flag on → EITHER
              // Cut #5 OR the router can skip.
              //
              // DEPLOY_CANARY_TURN_ROUTER_STATE_MACHINE_GATE_MARKER.
              const routerStateMachineGateFires = Boolean(
                turnRouterDecision &&
                  turnRouterDecision.trace_annotations.default_mode ===
                    "meaning_first" &&
                  !turnRouterDecision.invoke_state_machine,
              );
              const stateMachineAuthoringSkipped = Boolean(
                (!dispositionAuthoringEnvOff &&
                  authoringDisposition &&
                  authoringDisposition.disposition !== "continue_step") ||
                  routerStateMachineGateFires,
              );
              try {
                api.logger.info(
                  `[turn-disposition/authoring] conversation=${conversationId} sessionKey=${guardSessionKey} flag=${
                    dispositionAuthoringEnvOff ? "off" : "on"
                  } disposition=${
                    authoringDisposition?.disposition ?? "-"
                  } policy_rule=${
                    authoringDisposition?.policy_rule ?? "-"
                  } sm_skipped=${
                    stateMachineAuthoringSkipped ? "yes" : "no"
                  } router_gate_fired=${
                    routerStateMachineGateFires ? "yes" : "no"
                  } router_mode=${
                    turnRouterDecision?.mode ?? "-"
                  } prompt_skipped=no legacy_would_have=${
                    directive?.action ?? "-"
                  } ti_kind=${
                    dispositionProposerValue?.turn_intent?.kind ?? "-"
                  } ti_confidence=${
                    dispositionProposerValue?.turn_intent?.confidence ?? "-"
                  } ac_kind=${
                    dispositionProposerValue?.awaiting_confirmation?.kind ??
                    "-"
                  } turn_kind=${
                    dispositionProposerValue?.turn_kind ?? "-"
                  } stage=${stageAtTurnStart ?? "-"} fallthrough=${
                    authoringDisposition?.trace_annotations
                      ?.fallthrough_reason ?? "-"
                  }`,
                );
              } catch {
                // Never block the turn on trace emit failure.
              }

              if (directive && directiveHasServerRenderer(directive.action)) {
                // Phase 3 confirm-turn gate: when the active directive
                // is the summary composer AND the customer's inbound
                // message this turn is an explicit order confirmation
                // ("yes", "confirm", "اكمل", etc.), the LLM owns the
                // reply because it needs to call `create_simple_order`
                // and acknowledge the placed order. Re-rendering the
                // summary here would tell the customer "shall I confirm
                // this order?" a second time after they already said
                // yes. Skip substitution in that case.
                const isSummaryDirective =
                  directive.action ===
                  "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED";
                const customerConfirmedOrder =
                  isSummaryDirective && isExplicitOrderConfirmation(rawBody || null);
                // Phase 2 hotfix (2026-04-21): informational-question
                // gate. Hard rule 5 says a price / option question on a
                // quoted route is an ANSWER-ONLY turn — the LLM's
                // reply must carry the answer, and no slot ask should
                // advance the booking this turn. Pre-hotfix, the
                // directive registry substituted the LLM's answer
                // with the next server-rendered slot ask, silently
                // advancing the flow. This gate restores rule 5
                // semantics at the server layer: when the directive
                // is one of the collection-flow or summary directives
                // AND stage=quoted AND the customer is asking an
                // informational option/price question, skip the
                // substitution. The LLM's rule-5-compliant answer
                // passes through.
                //
                // Scoped intentionally narrow:
                //   - only on `stage=quoted` (pre-collection). Mid-
                //     collection turns still fire the directive; the
                //     user's design decision is that "answer-only" is
                //     only safe before collection has begun.
                //   - only on collection / summary directives. Never
                //     skips CLARIFY_OPTION_BEFORE_PROCEED (the clarify
                //     gate is the whole point when ambiguous options
                //     are on offer) or CONFIRM_SLOT_CONFLICT (conflict
                //     resolution must come before anything).
                //   - manual-confirm address asks + handoff live in
                //     dedicated Region-A branches, not in this
                //     dispatch, so they are unaffected.
                const directiveIsCollectionOrSummary =
                  directive.action === "ASK_SENDER_NAME_AND_PHONE_DECISION" ||
                  directive.action === "ASK_SENDER_NAME" ||
                  directive.action === "ASK_SENDER_PHONE" ||
                  directive.action === "ASK_RECIPIENT_NAME_AND_PHONE" ||
                  directive.action === "ASK_PICKUP_ADDRESS" ||
                  directive.action === "ASK_DELIVERY_ADDRESS" ||
                  directive.action === "ASK_MISSING_AREAS" ||
                  directive.action === "ASK_PICKUP_AREA" ||
                  directive.action === "ASK_DELIVERY_AREA" ||
                  directive.action ===
                    "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED";
                const customerAskingInformational =
                  directiveIsCollectionOrSummary &&
                  conversationControllerEntry?.stage === "quoted" &&
                  isInformationalOptionQuestion(rawBody || null);
                if (
                  !customerConfirmedOrder &&
                  !customerAskingInformational &&
                  !stateMachineAuthoringSkipped
                ) {
                  // Surface conflict details so the CONFIRM_SLOT_CONFLICT
                  // renderer can name the conflicting values concretely.
                  let conflictingSlot: string | null = null;
                  let conflictValues: { incoming: string; existing: string } | null = null;
                  if (directive.action === "CONFIRM_SLOT_CONFLICT" && directive.field) {
                    conflictingSlot = directive.field;
                    const slots = conversationControllerEntry.dialogState?.slots || {};
                    const rec = (slots as any)[directive.field];
                    // 2026-04-22 — the DST field that holds the new,
                    // not-yet-confirmed value is `conflictCandidate`
                    // (see `dialog-state.ts::SlotRecord`). The original
                    // plumbing here read `rec.conflictValue`, which
                    // simply does not exist on the record — so the
                    // `both` branch in `renderConfirmSlotConflict`
                    // never fired and every AR/EN conflict prompt fell
                    // back to the generic "القيمة الصحيحة لـ X؟" /
                    // "Correct value for X?" wording. Reading the
                    // correct field surfaces both values so the
                    // renderer can emit the nicer
                    // "«existing» أو «incoming»؟" shape.
                    if (
                      rec &&
                      rec.status === "conflict" &&
                      typeof rec.value === "string" &&
                      typeof rec.conflictCandidate === "string"
                    ) {
                      conflictValues = {
                        existing: rec.value,
                        incoming: rec.conflictCandidate,
                      };
                    }
                  }
                  directiveActionForRender = directive.action;
                  directiveRenderContextForRender = {
                    language: preferredReplyLanguage,
                    draft: conversationControllerEntry.bookingDraft,
                    entry: conversationControllerEntry,
                    conflictingSlot,
                    conflictValues,
                    turnSeed: String(
                      (conversationControllerEntry.lastActivityTs ?? Date.now()) +
                        "::" +
                        conversationId,
                    ),
                  };

                  // ----------------------------------------------------------
                  // Cut #2 (2026-04-23): Correction/edit authority removal.
                  // The second concrete cut in the Job-A authority removal
                  // plan. When the turn-decision layer classifies the turn
                  // as a correction (`ti_kind=corrected_prior` at high/
                  // medium confidence), the state machine's candidate
                  // directive is NOT what the customer is asking for this
                  // turn — they are correcting a prior field. Suppress the
                  // directive here so the LLM's acknowledge-the-correction
                  // reply passes through instead of being overridden by
                  // the A0c server render.
                  //
                  // DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_FLIP_CALLSITE_MARKER.
                  // DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_FLIP_CORRECTION_MARKER.
                  // DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_FLIP_ACKNOWLEDGEMENT_MARKER.
                  //
                  // NARROW v2 (Cut #3): the allowlist honors TWO policy
                  // rules live — `suppress_on_correction_intent` (Cut #2)
                  // and `suppress_on_acknowledgement_intent` (Cut #3).
                  // The remaining three Reloc 4 suppress rules
                  // (`suppress_on_fresh_route_request`,
                  // `suppress_on_clarifying_question`,
                  // `suppress_on_cancel_intent`) stay shadow-only until
                  // each becomes its own narrow cut. This matches the
                  // same authority-removal pattern: one loud failure
                  // mode, one narrow cut at a time.
                  //
                  // Orthogonal safeguards (NOT about confidence — per-rule
                  // confidence policy lives inside
                  // `decideDirectiveDisposition`, same single-source-of-
                  // truth pattern as Cut #1):
                  //   1. Env flag `RIDERS_TURN_DECISION_DIRECTIVE_FLIP`
                  //      default "on", explicit "off" is the one-line
                  //      rollback.
                  //   2. Derived `policy_rule` must be in the tight
                  //      `DIRECTIVE_FLIP_SUPPRESS_RULES` set (just the
                  //      correction rule for v1).
                  //   3. Hallucination guard did NOT fire. The derivation
                  //      encodes this as an `allow_on_hallucination_guard`
                  //      rule that fires BEFORE the correction rule, but
                  //      the callsite checks again for defence in depth.
                  //   4. `sameRouteQuoteAction` is not a switch_option
                  //      (defensive; the derivation's own gate also
                  //      covers this).
                  //
                  // Effect when fired: clear `directiveActionForRender` and
                  // `directiveRenderContextForRender` so the Region-A A0c
                  // substitution path has nothing to dispatch. Log
                  // `[turn-decision/flip] kind=directive` with the legacy
                  // directive name we just cleared so the flip is
                  // auditable alongside Cut #1's A1 flip log.
                  // ----------------------------------------------------------
                  try {
                    const directiveFlipEnvOff =
                      (process.env.RIDERS_TURN_DECISION_DIRECTIVE_FLIP || "on")
                        .trim()
                        .toLowerCase() === "off";
                    const directiveFlipProposerValidation = proposedTurnDecisionRaw
                      ? validateProposedTurnDecision(proposedTurnDecisionRaw)
                      : null;
                    const directiveFlipProposerValue =
                      directiveFlipProposerValidation &&
                      directiveFlipProposerValidation.ok
                        ? directiveFlipProposerValidation.value
                        : null;
                    const directiveFlipSameRouteSwitch =
                      sameRouteQuoteAction?.kind === "switch_option";
                    const directiveFlipHallucinationGuardFired =
                      (hallucinationGuardRejections || []).length > 0;
                    const directiveFlipRouteIntentFreshThisTurn = Boolean(
                      directiveFlipProposerValue?.turn_kind === "initial_route" &&
                        !!activeQuotedRoute &&
                        sameRouteQuoteAction === null,
                    );
                    let directiveFlipDerivation:
                      | DirectiveDispositionDerivation
                      | null = null;
                    try {
                      directiveFlipDerivation = decideDirectiveDisposition({
                        state_directive_action: directive.action,
                        proposer_turn_kind:
                          directiveFlipProposerValue?.turn_kind ?? null,
                        proposer_ti_kind:
                          directiveFlipProposerValue?.turn_intent?.kind ?? null,
                        proposer_ti_confidence:
                          directiveFlipProposerValue?.turn_intent?.confidence ??
                          null,
                        proposer_ac_kind:
                          directiveFlipProposerValue?.awaiting_confirmation
                            ?.kind ?? null,
                        stage_at_turn_start: stageAtTurnStart,
                        has_active_quoted_route_at_turn_start: !!activeQuotedRoute,
                        route_intent_fresh_this_turn:
                          directiveFlipRouteIntentFreshThisTurn,
                        same_route_quote_switch_option:
                          directiveFlipSameRouteSwitch,
                        hallucination_guard_fired:
                          directiveFlipHallucinationGuardFired,
                      });
                    } catch (directiveFlipDeriveError) {
                      try {
                        api.logger.warn(
                          `[turn-decision/flip] kind=directive derive_failed conversation=${conversationId} error=${
                            directiveFlipDeriveError instanceof Error
                              ? directiveFlipDeriveError.message
                              : String(directiveFlipDeriveError)
                          }`,
                        );
                      } catch {
                        // Never block the turn on flip-layer errors.
                      }
                      directiveFlipDerivation = null;
                    }

                    const DIRECTIVE_FLIP_SUPPRESS_RULES = new Set<string>([
                      "layer.directive.suppress_on_correction_intent",
                      "layer.directive.suppress_on_acknowledgement_intent",
                    ]);
                    const directiveFlipAllowed = Boolean(
                      !directiveFlipEnvOff &&
                        directiveFlipDerivation &&
                        directiveFlipDerivation.disposition === "suppress" &&
                        DIRECTIVE_FLIP_SUPPRESS_RULES.has(
                          directiveFlipDerivation.policy_rule,
                        ) &&
                        !directiveFlipHallucinationGuardFired &&
                        !directiveFlipSameRouteSwitch,
                    );

                    if (directiveFlipAllowed && directiveFlipDerivation) {
                      const legacyDirective = directiveActionForRender;
                      directiveActionForRender = null;
                      directiveRenderContextForRender = null;
                      try {
                        api.logger.info(
                          `[turn-decision/flip] kind=directive conversation=${conversationId} policy_rule=${directiveFlipDerivation.policy_rule} legacy_would_have=${legacyDirective || "-"} ti_kind=${directiveFlipProposerValue?.turn_intent?.kind || "-"} ti_confidence=${directiveFlipProposerValue?.turn_intent?.confidence || "-"} stage=${stageAtTurnStart || "-"}`,
                        );
                      } catch {
                        // Never block the turn on log failures.
                      }
                    }
                  } catch (directiveFlipOuterError) {
                    try {
                      api.logger.warn(
                        `[turn-decision/flip] kind=directive outer_failed conversation=${conversationId} error=${
                          directiveFlipOuterError instanceof Error
                            ? directiveFlipOuterError.message
                            : String(directiveFlipOuterError)
                        }`,
                      );
                    } catch {
                      // Never block the turn on flip-layer errors.
                    }
                  }
                } else {
                  // Cut #5: include the disposition-authoring skip as a
                  // first-class reason token. The pre-existing skip
                  // reasons (`skipped_on_informational_option_question`,
                  // `skipped_on_order_confirmation`) are narrow word-list
                  // heuristics; the new
                  // `skipped_on_disposition_<kind>` reason is the
                  // uniform meaning-driven suppress token that will
                  // eventually absorb both. Ordering: disposition skip
                  // is reported when it would have fired even if the
                  // legacy gates also matched, because it reflects the
                  // higher-level decision (meaning says "not a step
                  // advance this turn").
                  const skipReason = stateMachineAuthoringSkipped
                    ? `skipped_on_disposition_${
                        authoringDisposition?.disposition ?? "unknown"
                      }`
                    : customerAskingInformational
                      ? "skipped_on_informational_option_question"
                      : "skipped_on_order_confirmation";
                  api.logger.info(
                    `[one-brain/directive-dispatch] ${skipReason} conversation=${conversationId} action=${directive.action} stage=${conversationControllerEntry?.stage || "-"} text=${JSON.stringify((rawBody || "").slice(0, 60))}`,
                  );
                }

              }
            }

            // ----------------------------------------------------------
            // Relocation 3 flip (2026-04-22). First concrete cut
            // against the step-loop branch: compute the turn-decision
            // layer's A1 derivation HERE, BEFORE Region A runs, and
            // when all live-only safeguards pass, inject
            // `layerA1Passthrough` so `decidePreStateOutbound` skips
            // its A0c `replace_directive_ask` branch and lets the
            // LLM's draft survive.
            //
            // DEPLOY_CANARY_TURN_DECISION_A1_FLIP_CALLSITE_MARKER.
            // DEPLOY_CANARY_TURN_DECISION_A1_FLIP_CONFIDENCE_GATE_REMOVAL_MARKER.
            //
            // 2026-04-23 authority removal: the callsite previously held
            // a BLANKET `ti_confidence ∈ {high, medium}` gate applied to
            // ALL three passthrough rules. That gate was the wrong shape:
            //
            //   * `pass_on_clarifying` and `pass_on_partial_answer` ALREADY
            //     require trustworthy confidence INSIDE `deriveA1Substitute`
            //     (see `a1TiConfidenceIsTrustworthy`); the callsite check
            //     was redundant.
            //   * `pass_on_route_change` correctly uses STRUCTURAL signals
            //     (`route_intent_fresh_this_turn`, stage, active quote) —
            //     it does NOT look at `ti_confidence` because fresh
            //     `initial_route` turns don't emit a `turn_intent` at all,
            //     so `ti_confidence` is null on the exact turns the rule
            //     is meant to catch. The callsite check was vetoing the
            //     derivation's correct answer on those turns.
            //
            // Fix: delete the blanket callsite gate. `deriveA1Substitute`
            // is now the single source of truth for per-rule confidence
            // policy. The callsite only retains orthogonal safeguards
            // (env flag, hallucination guard, switch-option skip, legacy-
            // branch presence) that are NOT about confidence.
            //
            // Live-only safeguards (ALL must pass for the flip to fire):
            //   1. Env flag: `RIDERS_TURN_DECISION_A1_FLIP !== "off"`.
            //      Default is on — explicit "off" is the one-line
            //      rollback; a restart re-reads the env.
            //   2. Derived policy rule must be one of the THREE
            //      semantic gates. Legacy-aligned rules (render, no-
            //      renderer passthrough, manual-confirm, clarify-
            //      before-proceed, etc.) are NOT flipped.
            //   3. Per-rule trust requirements live inside
            //      `deriveA1Substitute` — if the derivation returned
            //      `allow` with a passthrough rule id, trust is
            //      already satisfied. No second callsite check.
            //   4. Hallucination guard did NOT reject this turn. If
            //      the guard fired, we keep legacy behaviour — the
            //      substitute is the expected fallback for an
            //      unsupported LLM draft.
            //   5. `sameRouteQuoteAction` is not a switch_option (the
            //      derivation's own gate already covers this; checked
            //      again at the flip for defence in depth).
            // ----------------------------------------------------------
            const a1FlipEnvOff =
              (process.env.RIDERS_TURN_DECISION_A1_FLIP || "on")
                .trim()
                .toLowerCase() === "off";
            const a1FlipProposerValidation = proposedTurnDecisionRaw
              ? validateProposedTurnDecision(proposedTurnDecisionRaw)
              : null;
            const a1FlipProposerValue =
              a1FlipProposerValidation && a1FlipProposerValidation.ok
                ? a1FlipProposerValidation.value
                : null;
            const a1FlipDirectiveHasServerRenderer = directiveActionForRender
              ? directiveHasServerRenderer(directiveActionForRender as any)
              : false;
            const a1FlipSameRouteSwitch =
              sameRouteQuoteAction?.kind === "switch_option";
            const a1FlipRouteIntentFreshThisTurn = Boolean(
              a1FlipProposerValue?.turn_kind === "initial_route" &&
                !!activeQuotedRoute &&
                sameRouteQuoteAction === null,
            );
            let a1FlipDerivation: A1Derivation | null = null;
            try {
              a1FlipDerivation = deriveA1Substitute({
                clarify_option_before_proceed_flag: clarifyOptionBeforeProceed,
                manual_confirm_address_ask: manualConfirmAddressAsk
                  ? {
                      side: manualConfirmAddressAsk.side,
                      option_type:
                        manualConfirmAddressAsk.option.delivery_type,
                    }
                  : null,
                manual_confirm_handoff: manualConfirmHandoff
                  ? {
                      option_type: manualConfirmHandoff.option.delivery_type,
                    }
                  : null,
                directive_action: directiveActionForRender,
                directive_has_server_renderer:
                  a1FlipDirectiveHasServerRenderer,
                same_route_quote_switch_option: a1FlipSameRouteSwitch,
                proposer_turn_kind: a1FlipProposerValue?.turn_kind ?? null,
                proposer_ti_kind:
                  a1FlipProposerValue?.turn_intent?.kind ?? null,
                proposer_ti_confidence:
                  a1FlipProposerValue?.turn_intent?.confidence ?? null,
                stage_at_turn_start: stageAtTurnStart,
                has_active_quoted_route_at_turn_start: !!activeQuotedRoute,
                route_intent_fresh_this_turn: a1FlipRouteIntentFreshThisTurn,
              });
            } catch (a1FlipDeriveError) {
              try {
                api.logger.warn(
                  `[turn-decision/flip] derive_failed conversation=${conversationId} error=${
                    a1FlipDeriveError instanceof Error
                      ? a1FlipDeriveError.message
                      : String(a1FlipDeriveError)
                  }`,
                );
              } catch {
                // Never block the turn on flip-layer errors.
              }
              a1FlipDerivation = null;
            }
            const A1_FLIP_PASSTHROUGH_RULES = new Set<string>([
              "layer.a1.directive_ask.pass_on_clarifying",
              "layer.a1.directive_ask.pass_on_partial_answer",
              "layer.a1.directive_ask.pass_on_route_change",
            ]);
            // NOTE (2026-04-23 authority removal): the blanket
            // `a1FlipConfidenceOk` callsite check previously lived here.
            // It has been deleted — `deriveA1Substitute` already owns
            // per-rule confidence policy (`a1TiConfidenceIsTrustworthy`
            // gates `pass_on_clarifying` / `pass_on_partial_answer`;
            // `pass_on_route_change` uses structural signals by design).
            // The second-guess gate was vetoing correct derivations on
            // fresh-route turns where the proposer emits no turn_intent.
            // See DEPLOY_CANARY_TURN_DECISION_A1_FLIP_CONFIDENCE_GATE_REMOVAL_MARKER.
            const a1FlipHallucinationGuardFired =
              (hallucinationGuardRejections || []).length > 0;
            // 2026-04-23 hoist — determine which legacy Region-A branch
            // would have fired absent the passthrough. A0 / A0a / A0b
            // outrank A0c in `decidePreStateOutbound`, so we match that
            // precedence here.
            let a1FlipLegacyBranch:
              | "a0_clarify_before_proceed"
              | "a0a_manual_confirm_address_ask"
              | "a0b_manual_confirm_handoff"
              | "a0c_directive_ask"
              | null = null;
            let a1FlipLegacyWouldHave: string | null = null;
            if (clarifyOptionBeforeProceed && activeQuotedRoute) {
              a1FlipLegacyBranch = "a0_clarify_before_proceed";
              a1FlipLegacyWouldHave = "clarify_option_before_proceed";
            } else if (manualConfirmAddressAsk && activeQuotedRoute) {
              a1FlipLegacyBranch = "a0a_manual_confirm_address_ask";
              a1FlipLegacyWouldHave = `manual_confirm_address_ask:${manualConfirmAddressAsk.side}`;
            } else if (manualConfirmHandoff && activeQuotedRoute) {
              a1FlipLegacyBranch = "a0b_manual_confirm_handoff";
              a1FlipLegacyWouldHave = "manual_confirm_handoff";
            } else if (
              directiveActionForRender &&
              a1FlipDirectiveHasServerRenderer
            ) {
              a1FlipLegacyBranch = "a0c_directive_ask";
              a1FlipLegacyWouldHave = directiveActionForRender;
            }
            const a1FlipAllowed = Boolean(
              !a1FlipEnvOff &&
                a1FlipDerivation &&
                a1FlipDerivation.intent === "allow" &&
                A1_FLIP_PASSTHROUGH_RULES.has(a1FlipDerivation.policy_rule) &&
                !a1FlipHallucinationGuardFired &&
                !a1FlipSameRouteSwitch &&
                a1FlipLegacyBranch !== null,
            );
            const a1FlipPayload =
              a1FlipAllowed &&
              a1FlipDerivation &&
              a1FlipLegacyBranch &&
              a1FlipLegacyWouldHave
                ? {
                    allowed: true as const,
                    policyRule: a1FlipDerivation.policy_rule,
                    legacyBranch: a1FlipLegacyBranch,
                    legacyWouldHave: a1FlipLegacyWouldHave,
                  }
                : null;

            // Authority cutover phase 3 (2026-04-23): the A0/A0a/A0b
            // Region-A substitution inputs are no longer passed — their
            // consumer branches in decidePreStateOutbound were deleted
            // now that phase 2 forced the arming flags to constants.
            // `clarifyOptionBeforeProceed`, `manualConfirmAddressAsk`,
            // `manualConfirmHandoff` and the three matching builders
            // (`buildDeterministicClarifyOptionBeforeProceedReply`,
            // `buildDeterministicManualConfirmAddressAskReply`,
            // `buildDeterministicManualConfirmHandoffReply`) are gone.
            void clarifyOptionBeforeProceed;
            void manualConfirmAddressAsk;
            void manualConfirmHandoff;
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
              directiveAction: directiveActionForRender,
              directiveRenderContext: directiveRenderContextForRender,
              renderDirectiveReply,
              buildDeterministicSelectedQuotedOptionReply,
              conversationId,
              sessionKeyForLogs: guardSessionKey,
              controllerStage: conversationControllerEntry?.stage || null,
              layerA1Passthrough: a1FlipPayload,
            });
            replyText = preDecision.replyText;
            emitOutboundDecisionLogs(api, preDecision.logEntries);
            turnReplyAuthor = preDecision.replyAuthor;
            turnReplyReason = preDecision.reason;
            turnReplyDirective = directiveActionForRender;
            turnReplyDirectiveRenderContextPresent =
              directiveRenderContextForRender !== null;
            // Capture A1 substitute intent only when A1 actually became
            // the reply author (i.e. overrode the LLM). Casting the
            // reason through `A1SubstituteIntent` is safe: the union
            // enumerates every valid `OutboundDecisionReason`, and a
            // future reason without a corresponding A1 member will
            // fail compile inside `turn-decision.ts`.
            if (preDecision.replyAuthor === "server") {
              turnA1SubstituteIntent =
                preDecision.reason as A1SubstituteIntent;
            }
            // Seed the final decision from pre-state — post-state
            // overwrites below if it substitutes. This lets pre-state
            // substitutions (directive-registry, canonical overwrite,
            // clarify-before-proceed, manual-confirm, etc.) survive
            // into the provenance line even when post-state chose
            // `allow`, which is the common path.
            turnFinalDecision = preDecision.decision;
            turnFinalReason = preDecision.reason;
            // Phase 3 (2026-04-20): when Region A substituted the server-
            // composed summary, promote the controller to
            // `summary_shown / summary_pending` in the same turn. Mirrors
            // the post-state C-drift promotion so downstream confirmation
            // detection and the order-guard summary gate fire off the
            // real event, not a stale `collecting_booking_details` stage.
            if (preDecision.markedSummaryShown && conversationControllerEntry) {
              conversationControllerEntry = {
                ...conversationControllerEntry,
                stage: "summary_shown" as ConversationFlowStage,
                bookingStep: "summary_pending" as BookingCollectionStep,
              };
            }
          }
          if (conversationControllerEntry && sessionGuard && sessionIsRecent) {
            if (
              sessionGuard.lastToolName === "get_price" &&
              sessionGuard.lastQuotedRoute &&
              sessionGuard.lastToolTs !== conversationControllerEntry.quoteTs &&
              // Class-level veto (2026-04-21):
              // `stale_guard_state_clobbers_clarification_turn`. A turn that
              // drained a `set_requested_slot(pickup_area|dropoff_area)` is
              // mid-clarification — the pricing tool returned AREA_AMBIGUOUS,
              // did NOT produce a fresh priced route, and is asking the
              // customer to disambiguate one leg. Inheriting
              // `sessionGuard.lastQuotedRoute` on this turn can only come
              // from a stale/persisted prior session, never from this
              // turn's work. Skip the promotion and preserve the
              // pending-area + requested-slot state the drain just committed.
              // Regression: `smoke-test-clarification-turn-not-promoted.mjs`.
              !turnDrainedRouteSideClarification
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
                // Reset the dialog-state slot map alongside the booking
                // draft on successful order placement. Without this,
                // `slots.sender_name = {status:"filled", value:"…"}`
                // (and the rest of the identity + address slot records)
                // survive from the just-placed order into the NEXT
                // booking in the same conversation, so the boundary
                // flags any new value for an already-"filled" slot as
                // `slot_conflict_with_filled_value` even though the
                // customer is starting a fresh order. Empirically
                // observed on conv 19294 (2026-04-22): Flow 1 placed
                // EN order with `sender_name="Abdulaziz almulla"`, then
                // Flow 2 voice note carried `sender_name="عبدالعزيز"`
                // was rejected twice (fast_path + llm) with
                // `slot_conflict_with_filled_value`, triggering a
                // spurious CONFIRM_SLOT_CONFLICT whose AR renderer then
                // leaked the raw slot key (Defect 2). The draft is
                // already reset above, so DST must follow to stay in
                // lockstep. Pattern mirrors the cancellation branch
                // (see createEmptyDialogState / createRouteResetDialogState
                // earlier in this file) — when DST is disabled via
                // feature flag (`conversationControllerEntry.dialogState`
                // is already null) we preserve null rather than
                // materialising a state record.
                dialogState: conversationControllerEntry.dialogState
                  ? createEmptyDialogState()
                  : null,
                pendingReplyText: null,
                submittedOrderUid,
              };
              if (submittedOrderUid) {
                api.logger.info(
                  `[post-order] stage=order_submitted uid=${submittedOrderUid} conversation=${conversationId} dialog_state_reset=${conversationControllerEntry.dialogState ? "yes" : "na"}`,
                );
              }
            } else if (sessionGuard.lastToolName === "track_order") {
              conversationControllerEntry = clearAutomatedConversationContext({
                ...conversationControllerEntry,
              });
            } else if (
              sessionGuard.lastToolName === "get_price" &&
              sessionGuard.lastQuotedRoute &&
              sessionGuard.lastToolTs !== conversationControllerEntry.quoteTs &&
              turnDrainedRouteSideClarification
            ) {
              // Class-level veto fired. Emit an explicit observability log
              // so the regression is easy to correlate in journalctl —
              // mirror the shape of the clarify-commit log so dashboards
              // can track both. See
              // `smoke-test-clarification-turn-not-promoted.mjs`.
              try {
                api.logger.info(
                  `[one-brain/clarify-preserved] skipped_quoted_promotion conversation=${conversationId} stale_route=${sessionGuard.lastQuotedRoute.pickupAreaNameEn || "-"}_to_${sessionGuard.lastQuotedRoute.dropoffAreaNameEn || "-"} requested_slot=${conversationControllerEntry.dialogState?.requestedSlot?.name || "-"} pending_pickup=${conversationControllerEntry.pendingPickupAreaNameEn || "-"} pending_dropoff=${conversationControllerEntry.pendingDropoffAreaNameEn || "-"}`,
                );
              } catch {}
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
            //
            // Source selection (2026-04-22): the outer `activeQuotedRoute`
            // binding is a TURN-START snapshot taken at line ~3606 from
            // `preDispatchGuardEntry.session?.lastQuotedRoute`. On an
            // initial-route turn (no prior quote on session), that
            // snapshot is `null` for the entire handler even when THIS
            // turn's `get_price` materialised a fresh catalog inside the
            // responder drain. Reading it here therefore leaves
            // `activeQuotedPrices=[]`, and the guard falls back to the
            // scalar `entry.quotedPrice` (the default option, e.g.
            // standard sedan). A truthful reply naming a non-default
            // option's price — "Express sedan at 1.750 KWD" on a first
            // quote — then registers as a `price_mismatch
            // mentioned=1.75 valid=1.25` and is replaced by the neutral
            // price-repair template (live incident, conv 19400, 2026-04-22).
            //
            // Fix: prefer the POST-DRAIN snapshot on
            // `sessionGuard.lastQuotedRoute` when THIS turn actually ran
            // `get_price` (same gate `getPriceFiredThisTurn` uses below
            // for the Class-15 bypass). That snapshot carries the full
            // `pricesByType` + `optionCatalog` the tool just produced.
            // Fall back to the turn-start `activeQuotedRoute` otherwise,
            // which preserves prior-turn behaviour on follow-up turns
            // where no new pricing call fired. Strictly a guard-input
            // population fix — no schema change, no policy change, and
            // no new quote-stage handling. See `selectGuardQuotedRoute`
            // + `collectActiveQuotedPrices` in
            // `lib/quoted-options.ts`.
            const guardQuotedRoute = selectGuardQuotedRoute({
              turnStartSnapshot: activeQuotedRoute,
              sessionGuard,
              turnStartMs,
            });
            const activeQuotedPrices = collectActiveQuotedPrices(guardQuotedRoute);
            // Class-15 bypass detection (2026-04-21).
            //
            // Precondition tuple: this turn's inbound carried route
            // evidence ("delivery salmiya to kuwait city pls", etc.)
            // AND there was no active quoted route at turn start AND
            // `get_price` did NOT fire during this turn. When all
            // three hold, `decidePostStateOutbound` substitutes any
            // free-composed area clarification with a deterministic
            // repair reply. See `classFifteenBypass` in
            // `outbound-decision.ts` + `looksLikeFreeComposedAreaClarification`
            // in `shared/outbound-verify.ts`.
            //
            // `getPriceFiredThisTurn` compares the post-drain
            // `sessionGuard.lastToolTs` against the dispatcher-entry
            // `turnStartMs` snapshot. `>= turnStartMs` means the tool
            // fired during this turn (riders-tools writes a fresh ts
            // on every successful pricing call). Any earlier timestamp
            // — including a stale `lastQuotedRoute` carried over from
            // a previous turn / session — fails the check, which is
            // what we want: the invariant is "this turn went through
            // the tool", not "some turn at some point did".
            const getPriceFiredThisTurn =
              sessionGuard?.lastToolName === "get_price" &&
              typeof sessionGuard?.lastToolTs === "number" &&
              sessionGuard.lastToolTs >= turnStartMs;
            const classFifteenBypass =
              hasRouteEvidence(rawBody) &&
              (stageAtTurnStart === null || stageAtTurnStart === "idle") &&
              !activeQuotedRoute &&
              !getPriceFiredThisTurn;
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
              classFifteenBypass,
              conversationId,
            });
            replyText = postDecision.replyText;
            emitOutboundDecisionLogs(api, postDecision.logEntries);
            // Provenance derivation: this branch always runs C1 + C2
            // (the `hallucinationGuardEnabled` flag only gates C2 inside
            // `decidePostStateOutbound`; C1's `verifyAndRepairOutbound`
            // always runs when `conversationControllerEntry` is non-null,
            // which is the condition for entering this branch). So
            // `verifiedByPostDecision` is true whenever post-state chose
            // `allow` / `allow_sanitized`, which lets us confidently
            // emit `llm_verified` instead of `llm_unverified`.
            turnPostStateRan = true;
            // Post-state wins on substitution (same policy as
            // `turnReplyAuthor`): if C1 / C2 rewrote the reply, the
            // customer saw the substitute, so provenance should
            // reflect that. On `allow`, preserve whatever pre-state
            // already set so a `registry_rendered` upstream decision
            // isn't demoted to `llm_verified`.
            if (postDecision.decision !== "allow") {
              turnFinalDecision = postDecision.decision;
              turnFinalReason = postDecision.reason;
            }
            // Phase 5 attribution: post-state wins when it substituted;
            // preserves pre-state attribution otherwise. "Post wins on
            // substitution" gives us the strongest outcome — if
            // post-state's C-drift / hallucination guard replaced the
            // reply, that's the customer-visible truth.
            if (postDecision.decision !== "allow") {
              turnReplyAuthor = postDecision.replyAuthor;
              turnReplyReason = postDecision.reason;
            }
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
            // [drift/get-price-bypass] Phase D baseline counter (2026-04-21).
            //
            // STRICTLY observation-only. No routing changes, no substitutions,
            // no new guards. This block MAY NOT throw: a try/catch wraps the
            // entire emit so a broken classifier cannot take down a turn.
            //
            // `turn_kind` partitions the turn into the two populations we
            // actually care about measuring:
            //
            //   * `initial_route` — the customer opened with a route intent on
            //     an idle conversation with no active quoted route. This is
            //     the Class-15 canary population: we want to know how often
            //     the LLM calls `get_price` on this turn vs. how often the
            //     Class-15 repair had to substitute vs. how often a free
            //     composition slipped past both.
            //
            //   * `post_clarify_continuation` — the previous turn pinned a
            //     pending pickup or dropoff and set a DST `requestedSlot` for
            //     a pickup_area/dropoff_area clarification. This is the
            //     Class-16/17 canary population: the customer is answering the
            //     clarification, and the LLM should be calling `get_price`
            //     with the pinned side + the customer's answer. We want to
            //     know how often this turn skips the tool entirely.
            //
            //   * `other` — everything else. Greetings, address collection,
            //     booking-detail collection, informational Q&A, post-order
            //     chat, etc. Not load-bearing for the two blocker classes.
            //
            // `outcome` is the fine-grained bucket per turn_kind. The whole
            // emit is a single structured line so downstream tooling can
            // aggregate cheaply. See BUG_CLASSES.md for the Phase D metric
            // definition.
            try {
              const inboundHasRouteEvidence = hasRouteEvidence(rawBody);
              const isIdleStart =
                stageAtTurnStart === null || stageAtTurnStart === "idle";
              const hadClarifyPending =
                (pendingPickupAtTurnStart || pendingDropoffAtTurnStart) &&
                (requestedSlotNameAtTurnStart === "pickup_area" ||
                  requestedSlotNameAtTurnStart === "dropoff_area");
              let turnKind: "initial_route" | "post_clarify_continuation" | "other";
              if (
                inboundHasRouteEvidence &&
                isIdleStart &&
                !hadActiveQuotedRouteAtTurnStart
              ) {
                turnKind = "initial_route";
              } else if (hadClarifyPending) {
                turnKind = "post_clarify_continuation";
              } else {
                turnKind = "other";
              }
              const postReasonStr = String(postDecision.reason || "");
              const class15RepairFired =
                postReasonStr === "replace_get_price_bypass";
              let outcome:
                | "tool_owned"
                | "class15_repair"
                | "turn1_bypass"
                | "post_clarify_bypass"
                | "irrelevant";
              if (turnKind === "initial_route") {
                if (getPriceFiredThisTurn) {
                  outcome = "tool_owned";
                } else if (class15RepairFired) {
                  outcome = "class15_repair";
                } else {
                  outcome = "turn1_bypass";
                }
              } else if (turnKind === "post_clarify_continuation") {
                outcome = getPriceFiredThisTurn
                  ? "tool_owned"
                  : "post_clarify_bypass";
              } else {
                outcome = "irrelevant";
              }
              const escapeLogString = (raw: string): string =>
                raw.replace(/["\\\n\r]/g, " ").slice(0, 80);
              const inboundPreview = escapeLogString(String(rawBody || ""));
              const optionsPreview = Array.isArray(
                requestedSlotOptionsAtTurnStart,
              )
                ? requestedSlotOptionsAtTurnStart
                    .map((o) => String(o || "").trim())
                    .filter(Boolean)
                    .slice(0, 6)
                    .join("|")
                : "-";
              api.logger.info(
                `[drift/get-price-bypass] conversation=${conversationId} ` +
                  `turn_kind=${turnKind} outcome=${outcome} ` +
                  `get_price_fired=${getPriceFiredThisTurn ? "true" : "false"} ` +
                  `class15_bypass_flag=${classFifteenBypass ? "true" : "false"} ` +
                  `class15_repair_fired=${class15RepairFired ? "true" : "false"} ` +
                  `stage_at_turn_start=${stageAtTurnStart || "-"} ` +
                  `had_active_quoted_route=${hadActiveQuotedRouteAtTurnStart ? "true" : "false"} ` +
                  `pending_pickup=${pendingPickupAtTurnStart || "-"} ` +
                  `pending_dropoff=${pendingDropoffAtTurnStart || "-"} ` +
                  `requested_slot=${requestedSlotNameAtTurnStart || "-"} ` +
                  `requested_options=[${optionsPreview}] ` +
                  `route_evidence_inbound=${inboundHasRouteEvidence ? "true" : "false"} ` +
                  `reply_author=${turnReplyAuthor || "-"} ` +
                  `reply_reason=${turnReplyReason || "-"} ` +
                  `inbound="${inboundPreview}"`,
              );
            } catch (driftEmitError) {
              try {
                api.logger.warn(
                  `[drift/get-price-bypass] emit failed conversation=${conversationId} error=${
                    driftEmitError instanceof Error
                      ? driftEmitError.message
                      : String(driftEmitError)
                  }`,
                );
              } catch {}
            }
            // [structured-output/proposer] Phase A shadow conformance emit
            // (2026-04-21; extended 2026-04-22 with awaiting_confirmation
            //  and turn_intent).
            //
            // STRICTLY observation-only. No routing change, no substitution,
            // no behavior gate. Paired with `[drift/get-price-bypass]` above.
            //
            // This is the single conformance signal the Phase A promotion
            // gate (>=95% well-formed across the Phase C eval corpus) will
            // be measured against. Shape:
            //
            //   present=<bool>         — did the LLM call `propose_turn_decision`?
            //   schema_valid=<bool>    — did the payload pass v1.0/v1.1 validation?
            //   schema_version=<enum|-> — the schema_version the payload declared
            //                              (accepted set: v1.0 | v1.1).
            //   turn_kind=<enum|->     — LLM's self-classification.
            //   pricing_action=<enum|-> — LLM's declared pricing decision.
            //   planned_tool_calls=[]  — names declared by the LLM.
            //   fired_tool_ops=[]      — op names actually drained this turn.
            //   plan_vs_fire=<tag>     — quick conformance bucket:
            //     * `aligned`   — declared get_price AND get_price fired
            //                     (or declared none AND none fired)
            //     * `drift_declared_not_fired` — planned get_price, didn't call it
            //     * `drift_fired_not_planned`  — called get_price, didn't plan it
            //     * `n/a`       — decision missing / invalid / different action
            //
            // v1.1 (2026-04-22) additions for the awaiting-confirmation policy
            // map. Observability-only today; the Region-A dispatch gate is
            // wired up in a later PR (Phase B) once classification quality
            // clears the live test pack:
            //
            //   ac_stage=<bool>           — was the current stage one of
            //                                `summary_shown` / `awaiting_confirmation`?
            //                                (i.e., was the classification expected?)
            //   ac_kind=<enum|->          — LLM's 6-way classification, when present.
            //                                One of: confirm_order, cancel_order,
            //                                edit_order, informational_question,
            //                                coherence_pleasantry, unclear.
            //   ac_classification=<tag>   — conformance bucket for v1.1:
            //     * `present`          — stage expected it, LLM provided it
            //     * `missing`          — stage expected it, LLM omitted it
            //     * `unexpected`       — LLM provided it outside the expected stages
            //     * `n/a`              — stage didn't expect it and LLM omitted it
            //
            // v1.2 (2026-04-22) additions for the general turn_intent semantic
            // layer. Observability-only today; no behavior is wired to these
            // fields yet — the Phase 2 server-side policy map will consume
            // them only after conformance clears on the live test pack.
            //
            //   ti_stage=<bool>               — was the turn inside the
            //                                   turn_intent expectation window?
            //                                   True iff the stage is one of
            //                                   `collecting_booking_details` /
            //                                   `summary_shown` /
            //                                   `awaiting_confirmation`, OR the
            //                                   server had a non-null
            //                                   `requestedSlot` at turn start.
            //   ti_kind=<enum|->              — LLM's 8-way classification of
            //                                   the customer's turn relative to
            //                                   the server's last ask.
            //   ti_confidence=<enum|->        — LLM-declared confidence (high /
            //                                   medium / low).
            //   ti_addressed_fields_count=<n> — how many closed-set tokens the
            //                                   LLM flagged as addressed this
            //                                   turn; empty array records 0.
            //   ti_addressed_fields=[a|b|c]   — compact list of the actual
            //                                   tokens (same `|`-delimited
            //                                   shape as planned_tool_calls).
            //                                   Empty `[]` when omitted /
            //                                   addressed nothing. Used by the
            //                                   analyzer to produce per-field
            //                                   coverage tables by stage /
            //                                   requested_slot.
            //   ti_classification=<tag>       — conformance bucket for v1.2,
            //                                   same four-value shape as the
            //                                   ac_classification bucket:
            //     * `present`    — stage expected it, LLM provided it
            //     * `missing`    — stage expected it, LLM omitted it
            //     * `unexpected` — LLM provided it outside expected stages
            //     * `n/a`        — stage didn't expect it and LLM omitted it
            //
            // Emitted inside try/catch so a broken classifier cannot take
            // down a turn. See `plugins/shared/proposer-schema.ts` for the
            // schema and validator, `plugins/riders-tools/tools/proposer.ts`
            // for the tool registration.
            //
            // DEPLOY_CANARY_TURN_INTENT_EMIT_MARKER: ti_classification shadow emit
            try {
              const present = proposedTurnDecisionRaw !== null;
              const validation = present
                ? validateProposedTurnDecision(proposedTurnDecisionRaw)
                : null;
              const schemaValid = validation ? validation.ok : false;
              const declaredSchemaVersion =
                validation && validation.ok
                  ? validation.value.schema_version
                  : "-";
              const declaredTurnKind =
                validation && validation.ok
                  ? validation.value.turn_kind
                  : "-";
              const declaredAction =
                validation && validation.ok
                  ? validation.value.pricing_decision.action
                  : "-";
              const declaredPlannedCalls =
                validation && validation.ok
                  ? validation.value.planned_tool_calls
                  : [];
              // v1.1 awaiting-confirmation conformance fields.
              //
              // We key the "expected" bucket on the CURRENT stage observed at
              // dispatch time (the controller entry visible to this emit). If
              // the turn promoted from e.g. `collecting_booking_details` →
              // `summary_shown` inside the same turn, the LLM had no way to
              // know the stage would be `summary_shown` by the time this emit
              // runs — so we read stage AT the point the LLM was invoked.
              // `currentControllerStageForProposerEmit` is captured once,
              // immediately before the LLM call, further above in this block.
              // If it isn't available for some reason (early-return paths),
              // fall back to the persisted entry stage.
              const stageForAcExpectation =
                (typeof currentControllerStageForProposerEmit === "string"
                  ? currentControllerStageForProposerEmit
                  : null) ||
                (conversationControllerEntry &&
                typeof conversationControllerEntry.stage === "string"
                  ? conversationControllerEntry.stage
                  : null);
              const acStage =
                stageForAcExpectation === "summary_shown" ||
                stageForAcExpectation === "awaiting_confirmation";
              const declaredAwaitingConfirmation =
                validation && validation.ok
                  ? validation.value.awaiting_confirmation || null
                  : null;
              const acKind =
                declaredAwaitingConfirmation?.kind || "-";
              let acClassification:
                | "present"
                | "missing"
                | "unexpected"
                | "n/a" = "n/a";
              if (acStage && declaredAwaitingConfirmation) {
                acClassification = "present";
              } else if (acStage && !declaredAwaitingConfirmation) {
                acClassification = "missing";
              } else if (!acStage && declaredAwaitingConfirmation) {
                acClassification = "unexpected";
              }
              // v1.2 turn_intent conformance fields. Same pattern as
              // awaiting_confirmation, but the expectation window is
              // broader: any of the three collection stages, OR a
              // non-null `requestedSlot` at turn start (the server just
              // asked for a specific slot). Stage is read from the same
              // `currentControllerStageForProposerEmit` snapshot used
              // for ac_stage — we want the LLM-visible stage, not any
              // mid-turn promotion.
              const tiStage =
                stageForAcExpectation === "collecting_booking_details" ||
                stageForAcExpectation === "summary_shown" ||
                stageForAcExpectation === "awaiting_confirmation" ||
                requestedSlotNameAtTurnStart !== null;
              const declaredTurnIntent =
                validation && validation.ok
                  ? validation.value.turn_intent || null
                  : null;
              const tiKind = declaredTurnIntent?.kind || "-";
              const tiConfidence = declaredTurnIntent?.confidence || "-";
              const tiAddressedFieldsCount = declaredTurnIntent
                ? declaredTurnIntent.addressed_fields.length
                : 0;
              let tiClassification:
                | "present"
                | "missing"
                | "unexpected"
                | "n/a" = "n/a";
              if (tiStage && declaredTurnIntent) {
                tiClassification = "present";
              } else if (tiStage && !declaredTurnIntent) {
                tiClassification = "missing";
              } else if (!tiStage && declaredTurnIntent) {
                tiClassification = "unexpected";
              }
              const firedOpNames = Array.from(turnDrainedOpKinds)
                .filter(
                  (name) => !!name && name !== "proposed_turn_decision",
                )
                .sort();
              const plannedGetPrice = declaredPlannedCalls.some(
                (n) => String(n).trim().toLowerCase() === "get_price",
              );
              let planVsFire:
                | "aligned"
                | "drift_declared_not_fired"
                | "drift_fired_not_planned"
                | "n/a" = "n/a";
              if (validation && validation.ok) {
                if (declaredAction === "call_get_price") {
                  planVsFire = getPriceFiredThisTurn
                    ? "aligned"
                    : "drift_declared_not_fired";
                } else if (declaredAction === "none") {
                  planVsFire = getPriceFiredThisTurn
                    ? "drift_fired_not_planned"
                    : "aligned";
                }
                if (
                  planVsFire === "aligned" &&
                  plannedGetPrice &&
                  !getPriceFiredThisTurn
                ) {
                  planVsFire = "drift_declared_not_fired";
                }
                if (
                  planVsFire === "aligned" &&
                  !plannedGetPrice &&
                  getPriceFiredThisTurn
                ) {
                  planVsFire = "drift_fired_not_planned";
                }
              }
              const compactList = (arr: string[]): string =>
                arr
                  .map((s) => String(s).slice(0, 32).replace(/[,\]\[]/g, " "))
                  .slice(0, 12)
                  .join("|");
              const errorsField =
                validation && !validation.ok
                  ? validation.errors.slice(0, 6).join(",")
                  : "-";
              // v1.2 (2026-04-22): analyzer-oriented context fields. `stage`
              // and `requested_slot` are what the analyzer uses to slice
              // conformance by collection state — without them, coverage
              // tables can only be read in aggregate. `ti_addressed_fields`
              // is the actual token list (same compact shape as
              // planned_tool_calls / fired_tool_ops) so per-field coverage
              // can be computed without correlating to a second emit.
              const tiAddressedFieldsList =
                declaredTurnIntent?.addressed_fields || [];
              // v1.3 (2026-04-22) — post_order_intent conformance fields.
              // Expected when the LLM self-declared turn_kind === "post_order_chat".
              // Same four-bucket classification as ac / ti:
              //   * present    — turn_kind was post_order_chat, LLM provided it
              //   * missing    — turn_kind was post_order_chat, LLM omitted it
              //   * unexpected — LLM provided it on a non-post-order turn_kind
              //   * n/a        — turn_kind wasn't post_order_chat AND LLM omitted it
              //
              // DEPLOY_CANARY_POST_ORDER_INTENT_EMIT_MARKER: po_classification shadow emit
              const declaredPostOrderIntent =
                validation && validation.ok
                  ? validation.value.post_order_intent || null
                  : null;
              const poStage = declaredTurnKind === "post_order_chat";
              const poKind = declaredPostOrderIntent?.kind || "-";
              let poClassification:
                | "present"
                | "missing"
                | "unexpected"
                | "n/a" = "n/a";
              if (poStage && declaredPostOrderIntent) {
                poClassification = "present";
              } else if (poStage && !declaredPostOrderIntent) {
                poClassification = "missing";
              } else if (!poStage && declaredPostOrderIntent) {
                poClassification = "unexpected";
              }
              api.logger.info(
                `[structured-output/proposer] conversation=${conversationId} ` +
                  `stage=${stageForAcExpectation || "-"} ` +
                  `requested_slot=${requestedSlotNameAtTurnStart || "-"} ` +
                  `present=${present ? "true" : "false"} ` +
                  `schema_valid=${schemaValid ? "true" : "false"} ` +
                  `schema_version=${declaredSchemaVersion} ` +
                  `turn_kind=${declaredTurnKind} ` +
                  `pricing_action=${declaredAction} ` +
                  `planned_tool_calls=[${compactList(declaredPlannedCalls)}] ` +
                  `fired_tool_ops=[${compactList(firedOpNames)}] ` +
                  `get_price_fired=${getPriceFiredThisTurn ? "true" : "false"} ` +
                  `plan_vs_fire=${planVsFire} ` +
                  `ac_stage=${acStage ? "true" : "false"} ` +
                  `ac_kind=${acKind} ` +
                  `ac_classification=${acClassification} ` +
                  `ti_stage=${tiStage ? "true" : "false"} ` +
                  `ti_kind=${tiKind} ` +
                  `ti_confidence=${tiConfidence} ` +
                  `ti_addressed_fields_count=${tiAddressedFieldsCount} ` +
                  `ti_addressed_fields=[${compactList(tiAddressedFieldsList)}] ` +
                  `ti_classification=${tiClassification} ` +
                  `po_stage=${poStage ? "true" : "false"} ` +
                  `po_kind=${poKind} ` +
                  `po_classification=${poClassification} ` +
                  `duplicate_count=${proposedTurnDecisionCount} ` +
                  `turn_id=${proposedTurnDecisionTurnId || "-"} ` +
                  `errors=${errorsField}`,
              );
            } catch (proposerEmitError) {
              try {
                api.logger.warn(
                  `[structured-output/proposer] emit failed conversation=${conversationId} error=${
                    proposerEmitError instanceof Error
                      ? proposerEmitError.message
                      : String(proposerEmitError)
                  }`,
                );
              } catch {}
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
            // In the no-controller branch, `decidePostStateOutbound`
            // runs only the empty-reply fallbacks (B1/B2) — C1 + C2
            // both require an entry and are skipped. That means an
            // `allow` outcome here represents LLM text that never went
            // through the verify / hallucination-guard gates, so
            // `verifiedByPostDecision` stays false and the derived
            // provenance is `llm_unverified`. Keeping the flag
            // conservative here is what lets the eval-corpus distinguish
            // genuinely unverified main-path turns from the routine
            // passthrough case (which always has a controller entry).
            turnPostStateRan = true;
            turnPostStateWasLightweight = true;
            if (postDecision.decision !== "allow") {
              turnFinalDecision = postDecision.decision;
              turnFinalReason = postDecision.reason;
              turnReplyAuthor = postDecision.replyAuthor;
              turnReplyReason = postDecision.reason;
            }
          }
          // Phase 5 attribution — emit ONE canonical line per turn so
          // per-conversation / per-directive aggregation is a grep away.
          // Dashboards / alerts can slice on:
          //   reply_author=server   — directive substitution fired
          //   reply_author=llm      — LLM draft passed through
          //   reply_author=fallback — provider / empty-reply fallback
          try {
            api.logger.info(
              `[one-brain/reply-attribution] conversation=${conversationId} reply_author=${turnReplyAuthor} reason=${turnReplyReason} directive=${turnReplyDirective || "-"} stage=${conversationControllerEntry?.stage || "-"} lang=${preferredReplyLanguage}`,
            );
          } catch {}

          // -----------------------------------------------------------
          // Unified turn-decision trace (relocation 1: scaffold / pure
          // observer).
          //
          // DEPLOY_CANARY_TURN_DECISION_CALLSITE_MARKER:
          //     [turn-decision/trace] emit
          //
          // Every field in `TurnDecisionObservedContext` is a
          // mechanical projection from values the four authorities
          // have already computed. NO novel decision is made here.
          // The scaffold's purpose is to (a) verify the
          // `TurnDecision` output shape is complete against every
          // real turn shape in production, (b) produce one structured
          // trace line per turn that becomes the regression gate for
          // relocations 2–5.
          //
          // See `delivery/ARCHITECTURE_TURN_DECISION.md` for the
          // contract and the five-step relocation plan.
          //
          // Emits ONCE per turn. Try/catch so a scaffold bug can
          // never take down a live turn.
          // -----------------------------------------------------------
          try {
            const tdProposerValidation = proposedTurnDecisionRaw
              ? validateProposedTurnDecision(proposedTurnDecisionRaw)
              : null;
            const tdProposerValue =
              tdProposerValidation && tdProposerValidation.ok
                ? tdProposerValidation.value
                : null;
            const tdDrainedOpNames = Array.from(turnDrainedOpKinds).sort();
            const tdBoundaryRejectionFields = Array.from(
              new Set(
                (hallucinationGuardRejections || [])
                  .map((r) => r.field)
                  .filter(Boolean),
              ),
            );
            const tdObserved: TurnDecisionObservedContext = {
              conversation_id: conversationId,
              turn_id: proposedTurnDecisionTurnId,
              outcome: {
                decision: turnFinalDecision,
                reason: turnFinalReason,
                reply_author: turnReplyAuthor,
                reply_text_chars:
                  typeof replyText === "string" ? replyText.length : 0,
                directive_action: turnReplyDirective,
                directive_render_context_present:
                  turnReplyDirectiveRenderContextPresent,
                marked_summary_shown:
                  conversationControllerEntry?.stage === "summary_shown",
              },
              // Relocation 2 (A4 → layer): supply the fresh-decision
              // inputs so `observeTurnDecision` can run `deriveDispatch`
              // in parallel with the observed classifier.
              a4_inputs: {
                a1_substitute_intent: turnA1SubstituteIntent,
                llm_reply_empty: originalLlmReplyChars === 0,
                hallucination_guard_fired:
                  (hallucinationGuardRejections || []).length > 0,
                directive_has_server_renderer: turnReplyDirective
                  ? directiveHasServerRenderer(turnReplyDirective as any)
                  : false,
              },
              // Relocation 3 (A1 → layer): supply the pre-state
              // substitute-derivation inputs so `observeTurnDecision`
              // can run `deriveA1Substitute` in parallel with the
              // legacy Region-A pipeline. All fields are mechanical
              // projections of state the legacy A1 site already
              // consumed this turn — no novel decisions made here.
              //
              // Route-change gate is STRICT: the conjunction
              //   proposer.turn_kind === "initial_route"
              //   AND activeQuotedRoute !== null
              //   AND sameRouteQuoteAction === null
              // captures a fresh route proposal that the same-route
              // followup resolver explicitly did not bind to the
              // current quoted route. Loose route evidence (e.g. a
              // bare area-name without a pickup/delivery pair) must
              // not satisfy this gate.
              a1_inputs: {
                clarify_option_before_proceed_flag:
                  turnA1ClarifyOptionBeforeProceed,
                manual_confirm_address_ask:
                  turnA1ManualConfirmAddressAskSnapshot,
                manual_confirm_handoff: turnA1ManualConfirmHandoffSnapshot,
                directive_action: turnReplyDirective,
                directive_has_server_renderer: turnReplyDirective
                  ? directiveHasServerRenderer(turnReplyDirective as any)
                  : false,
                same_route_quote_switch_option:
                  sameRouteQuoteAction?.kind === "switch_option",
                route_intent_fresh_this_turn: Boolean(
                  tdProposerValue?.turn_kind === "initial_route" &&
                    !!activeQuotedRoute &&
                    sameRouteQuoteAction === null,
                ),
                observed_a1_intent: turnA1SubstituteIntent,
              },
              // Relocation 4 (directive → layer): supply the candidate
              // state-machine directive and the meaning-gate inputs so
              // `observeTurnDecision` can run `decideDirectiveDisposition`
              // in parallel with the legacy pipeline. Shadow-only in
              // this cut — the callsite does not act on the derived
              // disposition yet.
              //
              // DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_CALLSITE_MARKER
              //
              // `state_directive_action` reuses `turnReplyDirective`
              // (the directive that actually fired this turn). For
              // shadow purposes this is equivalent to the state
              // machine's answer since, in the legacy pipeline, the
              // state machine's output always becomes the fired
              // directive when non-null.
              directive_inputs: {
                state_directive_action: turnReplyDirective,
                same_route_quote_switch_option:
                  sameRouteQuoteAction?.kind === "switch_option",
                hallucination_guard_fired:
                  (hallucinationGuardRejections || []).length > 0,
                route_intent_fresh_this_turn: Boolean(
                  tdProposerValue?.turn_kind === "initial_route" &&
                    !!activeQuotedRoute &&
                    sameRouteQuoteAction === null,
                ),
              },
              // Relocation 5 Phase 5.0 shadow (2026-04-23): supply the
              // meaning-authors-first inputs so `observeTurnDecision`
              // can run `decideTurnDisposition` in parallel with the
              // state machine. Shadow-only — the callsite does not act
              // on the derived disposition yet; the state machine
              // still authors the live directive.
              //
              // DEPLOY_CANARY_TURN_DISPOSITION_CALLSITE_MARKER.
              //
              // The `addressed_*` fields are computed as the intersection
              // (and delta) of the proposer's `ti_addressed_fields` with
              // the state-machine `missing` list. `state_machine_candidate_directive`
              // reuses `turnReplyDirective` so the consistency classifier
              // can compare layer-authored directives against what the
              // state machine actually produced this turn.
              disposition_inputs: (() => {
                const tiAddressedFields =
                  tdProposerValue?.turn_intent?.addressed_fields ?? [];
                let missingList: string[] = [];
                try {
                  if (conversationControllerEntry) {
                    missingList = computeOneBrainMissingFields(
                      conversationControllerEntry.bookingDraft,
                      conversationControllerEntry,
                    ) as string[];
                  }
                } catch {
                  missingList = [];
                }
                const missingSet = new Set(missingList);
                const addressedMissing = tiAddressedFields.filter((f) =>
                  missingSet.has(f),
                );
                const addressedNonMissing = tiAddressedFields.filter(
                  (f) => !missingSet.has(f),
                );
                const manualConfirmOptionPresent = (() => {
                  try {
                    const options =
                      activeQuotedRoute?.optionCatalog ?? [];
                    return options.some(
                      (o: any) =>
                        String(o?.direct_chat_booking_status || "")
                          .trim()
                          .toLowerCase() ===
                        "manual_confirmation_required",
                    );
                  } catch {
                    return false;
                  }
                })();
                return {
                  addressed_missing_fields: addressedMissing,
                  addressed_non_missing_fields: addressedNonMissing,
                  state: {
                    stage_at_turn_start: stageAtTurnStart,
                    has_active_quoted_route: !!activeQuotedRoute,
                    active_quoted_route_has_manual_confirm_option:
                      manualConfirmOptionPresent,
                    has_summary_shown:
                      conversationControllerEntry?.stage ===
                        "summary_shown" ||
                      conversationControllerEntry?.stage ===
                        "awaiting_confirmation",
                    is_post_order:
                      conversationControllerEntry?.stage ===
                      "order_submitted",
                    missing_fields_count: missingList.length,
                  },
                  tool_context: {
                    get_price_ran_this_turn:
                      tdDrainedOpNames.includes("get_price"),
                    start_booking_drained_this_turn:
                      tdDrainedOpNames.includes("start_booking"),
                    hallucination_guard_fired:
                      (hallucinationGuardRejections || []).length > 0,
                  },
                  hints: {
                    same_route_switch_option:
                      sameRouteQuoteAction?.kind === "switch_option",
                  },
                  state_machine_candidate_directive: turnReplyDirective,
                };
              })(),
              proposer: {
                present: proposedTurnDecisionRaw !== null,
                schema_valid: !!(
                  tdProposerValidation && tdProposerValidation.ok
                ),
                schema_version: tdProposerValue?.schema_version || "-",
                turn_kind: tdProposerValue?.turn_kind || null,
                ti_kind: tdProposerValue?.turn_intent?.kind || null,
                ti_confidence:
                  tdProposerValue?.turn_intent?.confidence || null,
                ti_addressed_fields:
                  tdProposerValue?.turn_intent?.addressed_fields ?? [],
                ac_kind:
                  tdProposerValue?.awaiting_confirmation?.kind || null,
                po_kind: tdProposerValue?.post_order_intent?.kind || null,
              },
              drained_op_names: tdDrainedOpNames,
              apply_boundary_rejection_fields: tdBoundaryRejectionFields,
              state_summary: {
                stage_at_turn_start: stageAtTurnStart,
                stage_at_turn_end:
                  conversationControllerEntry?.stage ?? null,
                has_active_quoted_route: !!activeQuotedRoute,
                has_draft: !!(
                  conversationControllerEntry?.bookingDraft &&
                  Object.keys(conversationControllerEntry.bookingDraft).some(
                    (k) =>
                      (conversationControllerEntry!.bookingDraft as any)[k] !=
                      null,
                  )
                ),
                missing_fields_count: (() => {
                  try {
                    if (!conversationControllerEntry) return 0;
                    return computeOneBrainMissingFields(
                      conversationControllerEntry.bookingDraft,
                      conversationControllerEntry,
                    ).length;
                  } catch {
                    return 0;
                  }
                })(),
              },
              language: preferredReplyLanguage,
            };
            const tdDecision = observeTurnDecision(tdObserved);
            api.logger.info(
              formatTurnDecisionTrace({
                conversation_id: conversationId,
                turn_id: proposedTurnDecisionTurnId,
                language: preferredReplyLanguage,
                decision: tdDecision,
                input_summary: {
                  stage_at_turn_start: stageAtTurnStart,
                  stage_at_turn_end:
                    conversationControllerEntry?.stage ?? null,
                  has_active_quoted_route: !!activeQuotedRoute,
                  drained_op_count: tdDrainedOpNames.length,
                  reply_text_chars:
                    typeof replyText === "string" ? replyText.length : 0,
                  schema_version: tdObserved.proposer.schema_version,
                  proposer_present: tdObserved.proposer.present,
                  proposer_valid: tdObserved.proposer.schema_valid,
                },
              }),
            );
          } catch (turnDecisionTraceError) {
            try {
              api.logger.warn(
                `[turn-decision/trace] emit_failed conversation=${conversationId} error=${
                  turnDecisionTraceError instanceof Error
                    ? turnDecisionTraceError.message
                    : String(turnDecisionTraceError)
                }`,
              );
            } catch {
              // Scaffold trace never blocks a turn.
            }
          }
          const pendingPrefix = conversationControllerEntry?.pendingReplyText?.trim();
          const outboundText = pendingPrefix ? `${pendingPrefix}\n\n${replyText}` : replyText;
          // Derive outbound provenance from the final (decision, reason)
          // pair. `verifiedByPostDecision` is true only when post-state
          // ran the full C1 + C2 gates — the no-controller "lightweight"
          // branch of `decidePostStateOutbound` runs just the
          // empty-reply fallbacks, so it does NOT count as verified.
          // Any `allow` outcome there still produces `llm_unverified`,
          // which is the signal this PR is designed to surface.
          const verifiedByPostDecision =
            turnPostStateRan && !turnPostStateWasLightweight;
          const outboundProvenance = provenanceFromDecision({
            decision: turnFinalDecision,
            reason: turnFinalReason,
            replyAuthor: turnReplyAuthor,
            verifiedByPostDecision,
          });
          try {
            await sendOctopusTextReply({
              api,
              account,
              conversationId,
              replyTarget,
              text: outboundText,
              preferredLanguage: preferredReplyLanguage,
              ingressIds,
              provenance: outboundProvenance,
              provenanceReason: turnFinalReason,
              provenanceDirective: turnReplyDirective,
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
