// ---------------------------------------------------------------------------
// Wave 2a extraction: octopus-channel shared type aliases.
// All of these are pure shape definitions that used to live at the top of
// `plugins/octopus-channel/index.ts`. They intentionally do NOT import from
// the shared conversation-policy module at runtime — cross-module type
// references (e.g. `PersistedConversationControllerEntry`) are imported
// where needed in the consuming module. No module-scope state is touched.
// ---------------------------------------------------------------------------

import type { PersistedConversationControllerEntry } from "../../shared/conversation-policy";

export type OpenClawPluginApi = any;
export type OpenClawConfig = any;
export type ChannelPlugin<ResolvedAccount = any, Probe = unknown, Audit = unknown> = any;

export type OctopusChannelSection = {
  enabled?: boolean;
  name?: string;
  baseUrl?: string;
  bearerToken?: string;
  webhookToken?: string;
  webhookPath?: string;
  agentId?: string;
  dmPolicy?: string;
  allowFrom?: string[];
  textChunkLimit?: number;
  typingEnabled?: boolean;
  typingRefreshMs?: number;
  mediaMaxMb?: number;
  behaviorPolicyPublishedPath?: string;
  accounts?: Record<string, OctopusChannelSection | undefined>;
};

export type ResolvedOctopusAccount = {
  accountId: string;
  enabled: boolean;
  name?: string;
  baseUrl: string;
  bearerToken: string;
  webhookToken: string;
  webhookPath: string;
  agentId: string;
  dmPolicy: string;
  allowFrom: string[];
  textChunkLimit: number;
  typingEnabled: boolean;
  typingRefreshMs: number;
  mediaMaxMb: number;
  behaviorPolicyPublishedPath: string;
};

export type SavedAddress = {
  area: string | null;
  house: string | null;
  avenue: string | null;
  notes: string | null;
};

export type SavedCustomerOrder = {
  conversation_id: string | null;
  order_id: string | number | null;
  order_uid: string | null;
  selected_delivery_type: string | null;
  payment_method: string | null;
  shipping_method:
    | {
        id: unknown;
        name: string | null;
        type: string | null;
      }
    | null;
  sender: {
    name: string | null;
    phone: string | null;
  };
  recipient: {
    name: string | null;
    phone: string | null;
  };
  payer: string | null;
  pickup: SavedAddress;
  delivery: SavedAddress;
  saved_from_turn_at: string | null;
};

export type CustomerProfile = {
  version: number;
  customer_whatsapp: string | null;
  updated_at: string;
  last_successful_order: SavedCustomerOrder | null;
};

export type OctopusInboundAudioMessage = {
  id: string | null;
  mediaId: string | null;
  mimeType: string | null;
  url: string;
  voice: boolean;
};

export type OctopusInboundImageMessage = {
  id: string | null;
  mediaId: string | null;
  mimeType: string | null;
  url: string;
};

export type OctopusInboundLocationMessage = {
  latitude: number;
  longitude: number;
  name: string | null;
  address: string | null;
};

export type CachedGeoArea = {
  name: string;
  lat: number;
  lng: number;
  governorate_name: string;
};

export type DebouncedMessage = {
  api: OpenClawPluginApi;
  account: ResolvedOctopusAccount;
  ingressId: string;
  payload: any;
  conversationId: string;
  messageText: string | null;
  replyTarget: string | null;
  messageId: string | null;
  audioMessage: OctopusInboundAudioMessage | null;
  imageMessage: OctopusInboundImageMessage | null;
  locationMessage: OctopusInboundLocationMessage | null;
};

export type DebounceBucket = {
  timer: ReturnType<typeof setTimeout>;
  messages: DebouncedMessage[];
};

export type PersistedInactivityEntry = {
  lastActivityTs: number;
  nudgeSentTs: number | null;
  language: "ar" | "en";
  conversationId: string;
  replyTarget: string;
  accountId: string;
};

export type InactivityState = Record<string, PersistedInactivityEntry>;

export type PersistedClosedConversationAlert = {
  accountId: string;
  conversationId: string;
  replyTarget: string;
  firstDetectedTs: number;
  lastDetectedTs: number;
  lastError: string;
  failureCount: number;
};

export type ClosedConversationAlertState = Record<string, PersistedClosedConversationAlert>;

export type OctopusReplySource =
  | "reply"
  | "inactivity_nudge"
  | "inactivity_close"
  | "processing_error_fallback"
  | "deterministic_greeting";

export type ConversationControllerState = Record<string, PersistedConversationControllerEntry>;

export type IngressLedgerStatus =
  | "ready_check"
  | "method_rejected"
  | "account_disabled"
  | "auth_failed"
  | "parse_failed"
  | "validation_probe"
  | "missing_conversation_id"
  | "accepted"
  | "enqueued"
  | "processing"
  | "processed"
  | "replied"
  | "ignored_non_text"
  | "failed";

export type PersistedIngressLedgerEntry = {
  ingressId: string;
  requestId: string | null;
  accountId: string;
  webhookPath: string;
  method: string;
  status: IngressLedgerStatus;
  receivedAt: string;
  lastUpdatedAt: string;
  processedAt: string | null;
  processingStartedAt: string | null;
  attempts: number;
  replayCount: number;
  note: string | null;
  error: string | null;
  conversationId: string | null;
  replyTarget: string | null;
  messageId: string | null;
  hasMessageText: boolean;
  hasAudioMessage: boolean;
  hasImageMessage: boolean;
  hasLocationMessage: boolean;
  rawSize: number;
  payloadHash: string | null;
  contentType: string | null;
  remoteAddress: string | null;
  payload: any;
};

export type IngressLedgerState = Record<string, PersistedIngressLedgerEntry>;
