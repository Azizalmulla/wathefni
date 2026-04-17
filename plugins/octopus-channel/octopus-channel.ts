/// <reference path="./node-shims.d.ts" />
import { promises as fs } from "node:fs";
import path from "node:path";

type ChannelPlugin<ResolvedAccount = any, Probe = unknown, Audit = unknown> = any;
type OpenClawConfig = any;
type OpenClawPluginApi = any;

const nodeProcess = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process;
const env = nodeProcess?.env ?? {};
const nodeBuffer = (globalThis as { Buffer?: any }).Buffer;
const webFormData = (globalThis as { FormData?: any }).FormData;
const webBlob = (globalThis as { Blob?: any }).Blob;

// ---------------------------------------------------------------------------
// Config types
// ---------------------------------------------------------------------------

type OctopusChannelSection = {
  enabled?: boolean;
  name?: string;
  baseUrl?: string;
  bearerToken?: string;
  publicMediaBaseUrl?: string;
  webhookToken?: string;
  webhookPath?: string;
  agentId?: string;
  dmPolicy?: string;
  allowFrom?: string[];
  textChunkLimit?: number;
  typingEnabled?: boolean;
  typingRefreshMs?: number;
  mediaMaxMb?: number;
  accounts?: Record<string, OctopusChannelSection | undefined>;
};

type ResolvedOctopusAccount = {
  accountId: string;
  enabled: boolean;
  name?: string;
  baseUrl: string;
  bearerToken: string;
  publicMediaBaseUrl: string;
  webhookToken: string;
  webhookPath: string;
  agentId: string;
  dmPolicy: string;
  allowFrom: string[];
  textChunkLimit: number;
  typingEnabled: boolean;
  typingRefreshMs: number;
  mediaMaxMb: number;
};

// ---------------------------------------------------------------------------
// Inbound media types
// ---------------------------------------------------------------------------

type OctopusInboundAudioMessage = {
  id: string | null;
  mediaId: string | null;
  mimeType: string | null;
  url: string;
  voice: boolean;
};

type OctopusInboundImageMessage = {
  id: string | null;
  mediaId: string | null;
  mimeType: string | null;
  url: string;
};

type OctopusInboundDocumentMessage = {
  id: string | null;
  mediaId: string | null;
  mimeType: string | null;
  url: string;
  fileName: string | null;
  caption: string | null;
};

type OctopusInboundLocationMessage = {
  latitude: number;
  longitude: number;
  name: string | null;
  address: string | null;
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_ACCOUNT_ID = "default";
const DEFAULT_BASE_URL = "https://app.ai-octopus.com";
const DEFAULT_TEXT_CHUNK_LIMIT = 3500;
const DEFAULT_TYPING_REFRESH_MS = 9000;
const DEFAULT_MEDIA_MAX_MB = 25;
const DEFAULT_INBOUND_DEBOUNCE_MS = 350;
const HOME_DIR = env.HOME?.trim() || ".";
const OPENCLAW_PROFILE = env.OPENCLAW_PROFILE?.trim() || "openclaw";
const PUBLIC_MEDIA_DIR = env.AI_OCTOPUS_PUBLIC_MEDIA_DIR?.trim() || "/var/www/wathefni-media";
const WORKSPACE_PROMPT_FILES = ["AGENTS.md", "IDENTITY.md", "SKILL.md", "TOOLS.md"] as const;
const PROVIDER_NAME = "octopus";
const PATH_PREFIX = "/webhook";
const ARABIC_CHAR_RE = /[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]/;
const FAST_INTENT_AGENT_IDS = new Set(
  String(env.AI_OCTOPUS_FAST_INTENT_AGENTS || "wathefni-hr")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean),
);

const workspacePromptRevisionCache = new Map<string, { signature: string; revision: string }>();

// ---------------------------------------------------------------------------
// Debounce
// ---------------------------------------------------------------------------

const INBOUND_DEBOUNCE_MS = Math.max(
  0,
  Number.parseInt(env.AI_OCTOPUS_INBOUND_DEBOUNCE_MS || String(DEFAULT_INBOUND_DEBOUNCE_MS), 10)
    || DEFAULT_INBOUND_DEBOUNCE_MS,
);

type DebouncedMessage = {
  api: OpenClawPluginApi;
  account: ResolvedOctopusAccount;
  payload: any;
  conversationId: string;
  messageText: string | null;
  replyTarget: string | null;
  messageId: string | null;
  audioMessage: OctopusInboundAudioMessage | null;
  imageMessage: OctopusInboundImageMessage | null;
  documentMessage: OctopusInboundDocumentMessage | null;
  locationMessage: OctopusInboundLocationMessage | null;
  receivedAtMs: number;
};

type DebounceBucket = {
  timer: ReturnType<typeof setTimeout>;
  messages: DebouncedMessage[];
  firstReceivedAtMs: number;
};

const inboundDebounceMap = new Map<string, DebounceBucket>();

// Phone → conversation ID mapping for outbound delivery.
// AI Octopus requires conversation_id in every API call, but the OpenClaw
// `message` tool only provides the phone number. We populate this on inbound.
const phoneToConversationId = new Map<string, string>();

// ---------------------------------------------------------------------------
// Closed conversation alert tracking
// ---------------------------------------------------------------------------

const CLOSED_CONVERSATION_ALERTS_PATH = path.join(
  HOME_DIR,
  `.openclaw-${OPENCLAW_PROFILE}`,
  "closed-conversation-alerts.json",
);

type PersistedClosedConversationAlert = {
  accountId: string;
  conversationId: string;
  replyTarget: string;
  firstDetectedTs: number;
  lastDetectedTs: number;
  lastError: string;
  failureCount: number;
};

type ClosedConversationAlertState = Record<string, PersistedClosedConversationAlert>;
type OctopusReplySource = "reply";

// ---------------------------------------------------------------------------
// Persistence helpers
// ---------------------------------------------------------------------------

async function loadClosedConversationAlertState(): Promise<ClosedConversationAlertState> {
  try {
    const raw = await fs.readFile(CLOSED_CONVERSATION_ALERTS_PATH, "utf-8");
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

async function saveClosedConversationAlertState(state: ClosedConversationAlertState): Promise<void> {
  try {
    await fs.mkdir(path.dirname(CLOSED_CONVERSATION_ALERTS_PATH), { recursive: true });
    await fs.writeFile(CLOSED_CONVERSATION_ALERTS_PATH, JSON.stringify(state), "utf-8");
  } catch {}
}

// ---------------------------------------------------------------------------
// Language detection (inlined — no external dependency)
// ---------------------------------------------------------------------------

function detectConversationLanguage(text: string | null): "ar" | "en" {
  if (!text) return "en";
  const chars = text.replace(/\s/g, "");
  if (!chars) return "en";
  let arabicCount = 0;
  for (const ch of chars) {
    if (ARABIC_CHAR_RE.test(ch)) arabicCount++;
  }
  return arabicCount / chars.length > 0.3 ? "ar" : "en";
}


// ---------------------------------------------------------------------------
// Debounce engine
// ---------------------------------------------------------------------------

function flushDebounceBucket(key: string) {
  const bucket = inboundDebounceMap.get(key);
  if (!bucket || bucket.messages.length === 0) {
    inboundDebounceMap.delete(key);
    return;
  }
  inboundDebounceMap.delete(key);
  const messages = bucket.messages;
  const first = messages[0];
  const now = Date.now();
  const debounceWaitMs = Math.max(0, now - bucket.firstReceivedAtMs);
  const combinedText = messages.map((m) => m.messageText).filter(Boolean).join("\n");
  const latestMessageId = messages[messages.length - 1].messageId;
  const latestPayload = messages[messages.length - 1].payload;
  const audioMessage = messages.find((m) => m.audioMessage)?.audioMessage || null;
  const imageMessage = messages.find((m) => m.imageMessage)?.imageMessage || null;
  const documentMessage = messages.find((m) => m.documentMessage)?.documentMessage || null;
  const locationMessage = messages.find((m) => m.locationMessage)?.locationMessage || null;

  first.api.logger.info(
    `[octopus] debounce flush key=${key} count=${messages.length} combinedLength=${(combinedText || "").length} waitMs=${debounceWaitMs}`,
  );

  void handleInboundMessage({
    api: first.api,
    account: first.account,
    payload: latestPayload,
    conversationId: first.conversationId,
    messageText: combinedText || null,
    replyTarget: first.replyTarget,
    messageId: latestMessageId,
    audioMessage,
    imageMessage,
    documentMessage,
    locationMessage,
    receivedAtMs: bucket.firstReceivedAtMs,
    debounceWaitMs,
  }).catch((error) => {
    first.api.logger.error(
      `[octopus] processing error account=${first.account.accountId} conversation=${first.conversationId} error=${error instanceof Error ? error.message : String(error)}`,
    );
  });
}

function enqueueInboundMessage(msg: DebouncedMessage) {
  const key = `${msg.account.accountId}:${msg.conversationId}`;

  if (msg.audioMessage || msg.imageMessage || msg.documentMessage || msg.locationMessage) {
    const existing = inboundDebounceMap.get(key);
    if (existing) {
      clearTimeout(existing.timer);
      flushDebounceBucket(key);
    }
    void handleInboundMessage({
      api: msg.api,
      account: msg.account,
      payload: msg.payload,
      conversationId: msg.conversationId,
      messageText: msg.messageText,
      replyTarget: msg.replyTarget,
      messageId: msg.messageId,
      audioMessage: msg.audioMessage,
      imageMessage: msg.imageMessage,
      documentMessage: msg.documentMessage,
      locationMessage: msg.locationMessage,
      receivedAtMs: msg.receivedAtMs,
      debounceWaitMs: Math.max(0, Date.now() - msg.receivedAtMs),
    }).catch((error) => {
      msg.api.logger.error(
        `[octopus] processing error account=${msg.account.accountId} conversation=${msg.conversationId} error=${error instanceof Error ? error.message : String(error)}`,
      );
    });
    return;
  }

  const existing = inboundDebounceMap.get(key);
  if (existing) {
    clearTimeout(existing.timer);
    existing.messages.push(msg);
    existing.timer = setTimeout(() => flushDebounceBucket(key), INBOUND_DEBOUNCE_MS);
    msg.api.logger.info(`[octopus] debounce buffered key=${key} depth=${existing.messages.length}`);
  } else {
    const timer = setTimeout(() => flushDebounceBucket(key), INBOUND_DEBOUNCE_MS);
    inboundDebounceMap.set(key, { timer, messages: [msg], firstReceivedAtMs: msg.receivedAtMs });
    msg.api.logger.info(`[octopus] debounce started key=${key} waitMs=${INBOUND_DEBOUNCE_MS}`);
  }
}

// ---------------------------------------------------------------------------
// Config schema
// ---------------------------------------------------------------------------

const octopusChannelConfigSchema = {
  schema: {
    type: "object",
    additionalProperties: false,
    properties: {
      enabled: { type: "boolean" },
      name: { type: "string" },
      baseUrl: { type: "string" },
      bearerToken: { type: "string" },
      publicMediaBaseUrl: { type: "string" },
      webhookToken: { type: "string" },
      webhookPath: { type: "string" },
      agentId: { type: "string" },
      dmPolicy: {
        type: "string",
        enum: ["open", "allowlist", "disabled", "pairing"],
      },
      allowFrom: { type: "array", items: { type: "string" } },
      textChunkLimit: { type: "number" },
      typingEnabled: { type: "boolean" },
      typingRefreshMs: { type: "number" },
      mediaMaxMb: { type: "number" },
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
            publicMediaBaseUrl: { type: "string" },
            webhookToken: { type: "string" },
            webhookPath: { type: "string" },
            agentId: { type: "string" },
            dmPolicy: { type: "string" },
            allowFrom: { type: "array", items: { type: "string" } },
            textChunkLimit: { type: "number" },
            typingEnabled: { type: "boolean" },
            typingRefreshMs: { type: "number" },
            mediaMaxMb: { type: "number" },
          },
        },
      },
    },
  },
};

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

function asTrimmedString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function normalizePhone(value: unknown): string | null {
  const raw = asTrimmedString(value);
  if (!raw) return null;
  const digits = raw.replace(/[^\d+]/g, "");
  return digits || null;
}

function looksLikePhone(value: string | null | undefined): boolean {
  return typeof value === "string" && /^\+?\d{7,20}$/.test(value.trim());
}

function normalizeAllowEntry(value: unknown): string {
  const text = asTrimmedString(value) ?? "";
  const phone = normalizePhone(text);
  if (phone && looksLikePhone(phone)) {
    return phone.replace(/^\+/, "");
  }
  return text;
}

function normalizeBaseUrl(value: string | null | undefined): string {
  const raw = value?.trim() || DEFAULT_BASE_URL;
  return raw.replace(/\/+$/, "") || DEFAULT_BASE_URL;
}

function normalizePublicMediaBaseUrl(value: string | null | undefined): string {
  return (value?.trim() || "").replace(/\/+$/, "");
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

function splitMimeType(value: unknown): string | null {
  const mimeType = asTrimmedString(value);
  if (!mimeType) return null;
  return mimeType.split(";")[0]?.trim().toLowerCase() || null;
}

// ---------------------------------------------------------------------------
// Config resolution
// ---------------------------------------------------------------------------

function getChannelSection(cfg: OpenClawConfig): OctopusChannelSection {
  const section = cfg.channels?.[PROVIDER_NAME as keyof typeof cfg.channels];
  return section && typeof section === "object" ? (section as OctopusChannelSection) : {};
}

function hasBaseAccountFields(section: OctopusChannelSection): boolean {
  return Boolean(
    section.baseUrl ||
      section.bearerToken ||
      section.publicMediaBaseUrl ||
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
      section.mediaMaxMb !== undefined,
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
  const publicMediaBaseUrl = normalizePublicMediaBaseUrl(
    asTrimmedString(accountSection.publicMediaBaseUrl) ||
      asTrimmedString(section.publicMediaBaseUrl) ||
      asTrimmedString(env.AI_OCTOPUS_PUBLIC_MEDIA_BASE_URL),
  );
  const webhookToken =
    asTrimmedString(accountSection.webhookToken) ||
    asTrimmedString(section.webhookToken) ||
    asTrimmedString(env.AI_OCTOPUS_WEBHOOK_TOKEN) ||
    "";
  const agentId =
    asTrimmedString(accountSection.agentId) ||
    asTrimmedString(section.agentId) ||
    asTrimmedString(env.AI_OCTOPUS_OPENCLAW_AGENT) ||
    "main";
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
  return {
    accountId: resolvedAccountId,
    enabled,
    name: asTrimmedString(accountSection.name) || asTrimmedString(section.name) || undefined,
    baseUrl,
    bearerToken,
    publicMediaBaseUrl,
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
  };
}

// ---------------------------------------------------------------------------
// Workspace prompt revision (for session cache keys)
// ---------------------------------------------------------------------------

function computeStableTextHash(value: string): string {
  let hashA = 2166136261;
  let hashB = 5381;
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    hashA ^= code;
    hashA = Math.imul(hashA, 16777619);
    hashB = Math.imul(hashB, 33) ^ code;
  }
  const partA = (hashA >>> 0).toString(16).padStart(8, "0");
  const partB = (hashB >>> 0).toString(16).padStart(8, "0");
  return `${partA}${partB}`.slice(0, 12);
}

function resolveAgentWorkspacePath(cfg: OpenClawConfig, agentId: string): string | null {
  const agents = cfg && typeof cfg === "object" ? (cfg as { agents?: unknown }).agents : null;
  const list =
    agents && typeof agents === "object" && Array.isArray((agents as { list?: unknown }).list)
      ? ((agents as { list: unknown[] }).list ?? [])
      : [];
  for (const entry of list) {
    if (!entry || typeof entry !== "object") continue;
    if (asTrimmedString((entry as { id?: unknown }).id) !== agentId) continue;
    const workspace = asTrimmedString((entry as { workspace?: unknown }).workspace);
    if (workspace) return workspace;
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
  if (!workspacePath) return "base";
  const descriptors: Array<{ name: string; path: string; signature: string }> = [];
  for (const fileName of WORKSPACE_PROMPT_FILES) {
    const filePath = path.join(workspacePath, fileName);
    try {
      const stat = await fs.stat(filePath);
      descriptors.push({ name: fileName, path: filePath, signature: `${fileName}:${Math.trunc(stat.mtimeMs)}:${stat.size}` });
    } catch (error) {
      const code =
        error && typeof error === "object" && "code" in error
          ? String((error as { code?: unknown }).code || "")
          : "";
      descriptors.push({ name: fileName, path: filePath, signature: `${fileName}:${code || "missing"}` });
    }
  }
  const cacheKey = `${agentId}:${workspacePath}`;
  const signature = descriptors.map((d) => d.signature).join("|");
  const cached = workspacePromptRevisionCache.get(cacheKey);
  if (cached?.signature === signature) return cached.revision;
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

// ---------------------------------------------------------------------------
// Inbound payload parsing
// ---------------------------------------------------------------------------

function extractConversationId(payload: any): string | number | null {
  const candidate = payload?.conversation_id ?? payload?.conversationId ?? payload?.conversation?.id;
  if (candidate === undefined || candidate === null || candidate === "") return null;
  return candidate;
}

function extractWhatsAppMessages(payload: any): any[] {
  return [
    ...(Array.isArray(payload?.messages) ? payload.messages : []),
    ...(Array.isArray(payload?.entry)
      ? payload.entry.flatMap((entry: any) =>
          Array.isArray(entry?.changes)
            ? entry.changes.flatMap((change: any) =>
                Array.isArray(change?.value?.messages) ? change.value.messages : [],
              )
            : [],
        )
      : []),
  ];
}

function extractMessageText(payload: any): string | null {
  const directCandidates = [
    payload?.message,
    payload?.text,
    payload?.text?.body,
    payload?.data?.message,
    payload?.data?.text,
    payload?.data?.text?.body,
  ];
  for (const candidate of directCandidates) {
    const text = asTrimmedString(candidate);
    if (text) return text;
  }
  const messages = extractWhatsAppMessages(payload);
  for (const message of messages) {
    const nestedCandidates = [
      message?.text?.body,
      message?.body,
      message?.caption,
      message?.image?.caption,
      message?.interactive?.button_reply?.title,
      message?.interactive?.list_reply?.title,
      message?.button?.text,
    ];
    for (const candidate of nestedCandidates) {
      const text = asTrimmedString(candidate);
      if (text) return text;
    }
  }
  return null;
}

function extractWhatsAppMessageId(payload: any): string | null {
  const directCandidates = [payload?.message_id, payload?.messageId, payload?.messages?.[0]?.id];
  for (const candidate of directCandidates) {
    const id = asTrimmedString(candidate);
    if (id) return id;
  }
  for (const message of extractWhatsAppMessages(payload)) {
    const id = asTrimmedString(message?.id);
    if (id) return id;
  }
  return null;
}

function extractReplyTarget(payload: any): string | null {
  const directCandidates = [
    payload?.to,
    payload?.phone,
    payload?.phone_number,
    payload?.customer_phone,
    payload?.customerPhone,
    payload?.wa_id,
    payload?.contacts?.[0]?.wa_id,
    payload?.messages?.[0]?.from,
    payload?.messages?.[0]?.wa_id,
    payload?.from,
  ];
  for (const candidate of directCandidates) {
    const phone = normalizePhone(candidate);
    if (phone && looksLikePhone(phone)) return phone.replace(/^\+/, "");
  }
  for (const message of extractWhatsAppMessages(payload)) {
    const phone = normalizePhone(message?.from);
    if (phone && looksLikePhone(phone)) return phone.replace(/^\+/, "");
  }
  return null;
}

function extractAudioMessage(payload: any): OctopusInboundAudioMessage | null {
  for (const message of extractWhatsAppMessages(payload)) {
    const audio = message?.audio;
    const url = asTrimmedString(audio?.url);
    if (message?.type !== "audio" || !url) continue;
    return {
      id: asTrimmedString(message?.id),
      mediaId: asTrimmedString(audio?.id),
      mimeType: splitMimeType(audio?.mime_type),
      url,
      voice: Boolean(audio?.voice),
    };
  }
  return null;
}

function extractImageMessage(payload: any): OctopusInboundImageMessage | null {
  for (const message of extractWhatsAppMessages(payload)) {
    const image = message?.image;
    const url = asTrimmedString(image?.url);
    if (message?.type !== "image" || !url) continue;
    return {
      id: asTrimmedString(message?.id),
      mediaId: asTrimmedString(image?.id),
      mimeType: splitMimeType(image?.mime_type),
      url,
    };
  }
  return null;
}

function extractDocumentMessage(payload: any): OctopusInboundDocumentMessage | null {
  for (const message of extractWhatsAppMessages(payload)) {
    const document = message?.document;
    const url = asTrimmedString(document?.url);
    if (message?.type !== "document" || !url) continue;
    return {
      id: asTrimmedString(message?.id),
      mediaId: asTrimmedString(document?.id),
      mimeType: splitMimeType(document?.mime_type),
      url,
      fileName: asTrimmedString(document?.filename),
      caption: asTrimmedString(document?.caption) || asTrimmedString(message?.caption),
    };
  }
  return null;
}

function extractLocationMessage(payload: any): OctopusInboundLocationMessage | null {
  for (const message of extractWhatsAppMessages(payload)) {
    if (message?.type !== "location") continue;
    const loc = message?.location;
    const lat = typeof loc?.latitude === "number" ? loc.latitude : parseFloat(loc?.latitude);
    const lng = typeof loc?.longitude === "number" ? loc.longitude : parseFloat(loc?.longitude);
    if (isNaN(lat) || isNaN(lng)) continue;
    return { latitude: lat, longitude: lng, name: asTrimmedString(loc?.name) || null, address: asTrimmedString(loc?.address) || null };
  }
  const directLoc = payload?.location;
  if (directLoc) {
    const lat = typeof directLoc?.latitude === "number" ? directLoc.latitude : parseFloat(directLoc?.latitude);
    const lng = typeof directLoc?.longitude === "number" ? directLoc.longitude : parseFloat(directLoc?.longitude);
    if (!isNaN(lat) && !isNaN(lng)) {
      return { latitude: lat, longitude: lng, name: asTrimmedString(directLoc?.name) || null, address: asTrimmedString(directLoc?.address) || null };
    }
  }
  return null;
}

function formatLocationAsText(loc: OctopusInboundLocationMessage): string {
  const hasRealCoords = loc.latitude !== 0 || loc.longitude !== 0;
  const coords = hasRealCoords ? `${loc.latitude.toFixed(6)}, ${loc.longitude.toFixed(6)}` : null;
  const parts: string[] = [];
  if (loc.name || loc.address) {
    parts.push([loc.name, loc.address].filter(Boolean).join(" — "));
  }
  if (coords) {
    parts.push(`📍 ${coords}`);
    parts.push(`https://maps.google.com/?q=${loc.latitude},${loc.longitude}`);
  }
  return parts.join("\n") || "📍 Location shared";
}

type FastIntentPosition = {
  companyCode: string;
  companyName: string;
  positionCode: string;
  title: string;
  applyCode: string;
  active: boolean;
};

function isFastIntentEnabled(agentId: string): boolean {
  return FAST_INTENT_AGENT_IDS.has(agentId);
}

function normalizePhoneDigits(value: string | null): string {
  return (value || "").replace(/\D+/g, "");
}

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function readJsonFileSafe<T = any>(filePath: string): Promise<T | null> {
  try {
    const raw = await fs.readFile(filePath, "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

async function writeJsonFile(filePath: string, value: unknown): Promise<void> {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf-8");
}

function hydrateTemplate(rawTemplate: string, replacements: Record<string, string>): any {
  let hydrated = rawTemplate;
  for (const [key, value] of Object.entries(replacements)) {
    hydrated = hydrated.replaceAll(`{${key}}`, value);
  }
  return JSON.parse(hydrated);
}

async function loadTemplateJson(
  workspaceRoot: string,
  companyCode: string,
  fileName: string,
  replacements: Record<string, string>,
): Promise<any | null> {
  const templatePath = path.join(workspaceRoot, "data", "companies", companyCode, "templates", fileName);
  try {
    const raw = await fs.readFile(templatePath, "utf-8");
    return hydrateTemplate(raw, replacements);
  } catch {
    return null;
  }
}

async function listActivePositions(workspaceRoot: string): Promise<FastIntentPosition[]> {
  const companiesRoot = path.join(workspaceRoot, "data", "companies");
  let companyEntries: any[] = [];
  try {
    companyEntries = await fs.readdir(companiesRoot, { withFileTypes: true });
  } catch {
    return [];
  }
  const positions: FastIntentPosition[] = [];
  for (const companyEntry of companyEntries) {
    if (!companyEntry?.isDirectory?.()) continue;
    const companyCode = companyEntry.name;
    const companyJson = await readJsonFileSafe<any>(path.join(companiesRoot, companyCode, "company.json"));
    const companyName = asTrimmedString(companyJson?.name) || companyCode;
    const positionsDir = path.join(companiesRoot, companyCode, "positions");
    let positionEntries: string[] = [];
    try {
      positionEntries = (await fs.readdir(positionsDir)).filter((entry) => entry.endsWith(".json"));
    } catch {
      continue;
    }
    for (const entry of positionEntries) {
      const positionJson = await readJsonFileSafe<any>(path.join(positionsDir, entry));
      if (!positionJson || positionJson.active !== true) continue;
      const positionCode = asTrimmedString(positionJson.code) || path.basename(entry, ".json");
      positions.push({
        companyCode,
        companyName,
        positionCode,
        title: asTrimmedString(positionJson.title) || positionCode,
        applyCode: asTrimmedString(positionJson.apply_code) || `APPLY-${companyCode}-${positionCode}`,
        active: true,
      });
    }
  }
  return positions.sort((left, right) => left.title.localeCompare(right.title));
}

async function listCandidateApplications(workspaceRoot: string, phone: string): Promise<any[]> {
  const applicationsDir = path.join(workspaceRoot, "data", "candidates", phone, "applications");
  let entries: string[] = [];
  try {
    entries = (await fs.readdir(applicationsDir)).filter((entry) => entry.endsWith(".json"));
  } catch {
    return [];
  }
  const applications: any[] = [];
  for (const entry of entries) {
    const parsed = await readJsonFileSafe<any>(path.join(applicationsDir, entry));
    if (parsed && typeof parsed === "object") applications.push(parsed);
  }
  return applications;
}

function rankApplication(app: any): number {
  if (!app || typeof app !== "object") return 0;
  const status = asTrimmedString(app.status) || "";
  const currentStep = asTrimmedString(app.current_step) || "";
  if (status === "awaiting_cv" || currentStep === "cv_request") return 400;
  if (currentStep === "cv_upload" || status === "cv_received") return 350;
  if (currentStep === "screening") return 300;
  if (currentStep === "review_pending" || status === "screening_complete") return 250;
  if (status === "hired") return 100;
  return 50;
}

function pickMostRelevantApplication(applications: any[]): any | null {
  if (!Array.isArray(applications) || applications.length === 0) return null;
  return [...applications].sort((left, right) => {
    const rankDelta = rankApplication(right) - rankApplication(left);
    if (rankDelta !== 0) return rankDelta;
    return String(right?.updated_at || "").localeCompare(String(left?.updated_at || ""));
  })[0] || null;
}

async function isHrSender(workspaceRoot: string, phone: string): Promise<boolean> {
  const companiesRoot = path.join(workspaceRoot, "data", "companies");
  let companyEntries: any[] = [];
  try {
    companyEntries = await fs.readdir(companiesRoot, { withFileTypes: true });
  } catch {
    return false;
  }
  for (const companyEntry of companyEntries) {
    if (!companyEntry?.isDirectory?.()) continue;
    const hrUsers = await readJsonFileSafe<any>(path.join(companiesRoot, companyEntry.name, "hr-users.json"));
    const users = Array.isArray(hrUsers?.users) ? hrUsers.users : [];
    const matched = users.some(
      (user) =>
        normalizePhoneDigits(asTrimmedString(user?.phone) || asTrimmedString(user))
        === phone,
    );
    if (matched) return true;
  }
  return false;
}

function isGreetingOnlyText(text: string): boolean {
  const normalized = text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized) return false;
  return [
    "hi",
    "hello",
    "hey",
    "good morning",
    "good evening",
    "مرحبا",
    "هلا",
    "السلام عليكم",
    "سلام",
    "صباح الخير",
    "مساء الخير",
  ].includes(normalized);
}

function looksLikeOpenPositionsQuery(text: string): boolean {
  return /(open positions|openings|vacanc|jobs|roles|hiring|available positions|what positions|which positions|وظايف|وظائف|الوظايف|شو الوظايف)/i.test(
    text.toLowerCase(),
  );
}

function looksLikeCandidateStatusQuery(text: string): boolean {
  return /(application status|my application|status update|any update|follow up|what happened|حالة الطلب|شنو صار|وين وصل|تحديث الطلب)/i.test(
    text.toLowerCase(),
  );
}

function extractApplyIntent(text: string): { companyCode: string; positionCode: string; applyCode: string } | null {
  const match = text.toUpperCase().match(/\b(APPLY-([A-Z0-9_]+)-([A-Z0-9_]+))\b/);
  if (!match) return null;
  return { applyCode: match[1], companyCode: match[2], positionCode: match[3] };
}

function buildOpenPositionsReply(language: "ar" | "en", positions: FastIntentPosition[]): string {
  if (positions.length === 0) {
    return language === "ar"
      ? "There are no open positions right now."
      : "There are no open positions right now.";
  }
  const lines = language === "ar" ? ["الوظائف المفتوحة حاليا:"] : ["Open positions right now:"];
  for (const position of positions.slice(0, 5)) {
    lines.push(`- ${position.title}: \`${position.applyCode}\``);
  }
  lines.push(language === "ar" ? "ارسل كود التقديم المناسب للبدء." : "Send the apply code for the role you want to start.");
  return lines.join("\n");
}

function buildGreetingReply(language: "ar" | "en", positions: FastIntentPosition[]): string {
  if (positions.length === 1) {
    return language === "ar"
      ? `هلا! اذا حاب تبدا التقديم، ارسل الكود هذا:\n\`${positions[0].applyCode}\``
      : `Hi! To start your application, send this code:\n\`${positions[0].applyCode}\``;
  }
  return buildOpenPositionsReply(language, positions);
}

function buildApplyReply(language: "ar" | "en", position: FastIntentPosition, existingApp: any | null): string {
  if (existingApp?.current_step === "review_pending" || existingApp?.status === "screening_complete") {
    return language === "ar"
      ? `طلبك على ${position.title} مكتمل وتحت المراجعة حاليا.`
      : `Your application for ${position.title} is complete and currently under review.`;
  }
  if (existingApp?.cv_received || existingApp?.current_step === "cv_upload") {
    return language === "ar"
      ? `استلمت الـ CV الخاص فيك لتقديم ${position.title}. قاعد اراجع الحين وبرجع لك بالخطوة اللي بعدها.`
      : `I already received your CV for ${position.title}. I am reviewing it now and will send the next step shortly.`;
  }
  return language === "ar"
    ? `هلا! انت الحين قاعد تقدم على ${position.title} في ${position.companyName}.\n\nارسل الـ CV, PDF او فويس او حتى اكتبه كنص - اللي يناسبك.`
    : `Hi! You are applying for ${position.title} at ${position.companyName}.\n\nPlease share your CV. PDF, voice note, or type it out - whatever works.`;
}

function buildStatusReply(language: "ar" | "en", application: any): string {
  const title = asTrimmedString(application?.position_title) || "this role";
  const currentStep = asTrimmedString(application?.current_step) || "";
  const status = asTrimmedString(application?.status) || "";
  if (status === "awaiting_cv" || currentStep === "cv_request") {
    return language === "ar"
      ? `تقديمك على ${title} مفتوح ومحتاج الـ CV عشان نكمل.`
      : `Your application for ${title} is open and waiting for your CV to continue.`;
  }
  if (currentStep === "cv_upload" || status === "cv_received") {
    return language === "ar"
      ? `استلمت الـ CV الخاص فيك على ${title} وقاعد اراجعه الحين.`
      : `I received your CV for ${title} and I am reviewing it now.`;
  }
  if (currentStep === "screening" || application?.screening?.status === "in_progress") {
    return language === "ar"
      ? `تقديمك على ${title} في مرحلة الاسئلة حاليا. اذا احتجت منك شي زيادة، باراسلك هنا.`
      : `Your application for ${title} is currently in the screening stage. I will message you here if I need anything else.`;
  }
  if (currentStep === "review_pending" || status === "screening_complete") {
    return language === "ar"
      ? `تقديمك على ${title} مكتمل وتحت المراجعة حاليا.`
      : `Your application for ${title} is complete and currently under review.`;
  }
  if (status === "hired") {
    return language === "ar"
      ? `مبروك! تم قبولك على ${title} والحين بننتقل لخطوات التعيين.`
      : `Congratulations! You have been accepted for ${title}, and we will move to onboarding next.`;
  }
  return language === "ar"
    ? `تقديمك على ${title} شغال، وبرجع لك باي تحديث هنا.`
    : `Your application for ${title} is in progress, and I will share any updates here.`;
}

function buildCvAckReply(language: "ar" | "en", application: any | null, positions: FastIntentPosition[]): string {
  if (application) {
    const title = asTrimmedString(application?.position_title) || "the role";
    return language === "ar"
      ? `استلمت الـ CV الخاص فيك على ${title}. قاعد اراجعه الحين وبرجع لك بالخطوة اللي بعدها.`
      : `I received your CV for ${title}. I am reviewing it now and will send the next step shortly.`;
  }
  if (positions.length > 0) {
    return language === "ar"
      ? `استلمت الـ CV. عشان اربطه بوظيفة معينة، ارسل كود التقديم المناسب مثل \`${positions[0].applyCode}\`.`
      : `I received your CV. To link it to a position, please send the relevant apply code, for example \`${positions[0].applyCode}\`.`;
  }
  return language === "ar"
    ? "استلمت الـ CV. ارسل كود التقديم عشان اكمل الطلب."
    : "I received your CV. Please send your apply code so I can continue the application.";
}

async function ensureFastApplyState(params: {
  workspaceRoot: string;
  phone: string;
  position: FastIntentPosition;
}): Promise<any | null> {
  const { workspaceRoot, phone, position } = params;
  const today = todayIsoDate();
  const replacements = {
    PHONE: phone,
    COMPANY_CODE: position.companyCode,
    POSITION_CODE: position.positionCode,
    POSITION_TITLE: position.title,
    COMPANY_NAME: position.companyName,
    "YYYY-MM-DD": today,
  };
  const candidateRoot = path.join(workspaceRoot, "data", "candidates", phone);
  const applicationPath = path.join(candidateRoot, "applications", `${position.companyCode}-${position.positionCode}.json`);
  const profilePath = path.join(candidateRoot, "profile.json");
  const existingApp = await readJsonFileSafe<any>(applicationPath);
  if (existingApp) return existingApp;

  const templateApplication = await loadTemplateJson(
    workspaceRoot,
    position.companyCode,
    "application.template.json",
    replacements,
  );
  const templateProfile = await loadTemplateJson(
    workspaceRoot,
    position.companyCode,
    "candidate-profile.template.json",
    replacements,
  );
  const application = templateApplication || {
    phone,
    company_code: position.companyCode,
    position_code: position.positionCode,
    apply_code: position.applyCode,
    position_title: position.title,
    company_name: position.companyName,
    status: "awaiting_cv",
    current_step: "cv_request",
    created_at: today,
    updated_at: today,
    cv_received: false,
    screening: {
      status: "not_started",
      answers: {},
      answer_sources: {},
      answer_evidence: {},
      pending_keys: [],
      last_asked_key: null,
      completed_at: null,
    },
    sync: {
      cv_upload: { status: "pending" },
      sheet_append: { status: "pending" },
    },
  };
  const profile = (await readJsonFileSafe<any>(profilePath)) || templateProfile || {
    phone,
    current_status: "application_started",
    applications: [],
    screening_answers: {},
  };
  const applications = Array.isArray(profile.applications) ? profile.applications : [];
  const hasEntry = applications.some(
    (entry) =>
      asTrimmedString(entry?.company_code) === position.companyCode
      && asTrimmedString(entry?.position_code) === position.positionCode,
  );
  if (!hasEntry) {
    applications.push({
      company_code: position.companyCode,
      position_code: position.positionCode,
      apply_code: position.applyCode,
      status: application.status,
      started_at: today,
    });
  }
  profile.phone = phone;
  profile.current_status = profile.current_status || "application_started";
  profile.applications = applications;
  await writeJsonFile(profilePath, profile);
  await writeJsonFile(applicationPath, application);
  return application;
}

async function maybeHandleFastTextIntent(params: {
  api: OpenClawPluginApi;
  cfg: OpenClawConfig;
  account: ResolvedOctopusAccount;
  conversationId: string;
  replyTarget: string | null;
  messageText: string | null;
  receivedAtMs: number;
}): Promise<boolean> {
  const { api, cfg, account, conversationId, replyTarget, messageText, receivedAtMs } = params;
  const text = asTrimmedString(messageText);
  if (!text || !replyTarget || !isFastIntentEnabled(account.agentId)) return false;
  const workspaceRoot = resolveAgentWorkspacePath(cfg, account.agentId);
  const phone = normalizePhoneDigits(replyTarget);
  if (!workspaceRoot || !phone) return false;
  if (await isHrSender(workspaceRoot, phone)) return false;

  const language = detectConversationLanguage(text);
  const positions = await listActivePositions(workspaceRoot);
  const applications = await listCandidateApplications(workspaceRoot, phone);
  const currentApplication = pickMostRelevantApplication(applications);

  if (isGreetingOnlyText(text) && !currentApplication) {
    await sendOctopusTextReply({ api, account, conversationId, replyTarget, text: buildGreetingReply(language, positions) });
    api.logger.info(`[octopus] fast intent handled kind=greeting conversation=${conversationId} elapsedMs=${Date.now() - receivedAtMs}`);
    return true;
  }

  if (looksLikeOpenPositionsQuery(text)) {
    await sendOctopusTextReply({ api, account, conversationId, replyTarget, text: buildOpenPositionsReply(language, positions) });
    api.logger.info(`[octopus] fast intent handled kind=open_positions conversation=${conversationId} elapsedMs=${Date.now() - receivedAtMs}`);
    return true;
  }

  const applyIntent = extractApplyIntent(text);
  if (applyIntent) {
    const matchedPosition = positions.find(
      (position) =>
        position.companyCode.toUpperCase() === applyIntent.companyCode
        && position.positionCode.toUpperCase() === applyIntent.positionCode,
    );
    if (!matchedPosition) return false;
    const application = (await pathExists(
      path.join(workspaceRoot, "data", "candidates", phone, "applications", `${matchedPosition.companyCode}-${matchedPosition.positionCode}.json`),
    ))
      ? await readJsonFileSafe<any>(
        path.join(workspaceRoot, "data", "candidates", phone, "applications", `${matchedPosition.companyCode}-${matchedPosition.positionCode}.json`),
      )
      : await ensureFastApplyState({ workspaceRoot, phone, position: matchedPosition });
    await sendOctopusTextReply({
      api,
      account,
      conversationId,
      replyTarget,
      text: buildApplyReply(language, matchedPosition, application),
    });
    api.logger.info(`[octopus] fast intent handled kind=apply conversation=${conversationId} elapsedMs=${Date.now() - receivedAtMs}`);
    return true;
  }

  if (looksLikeCandidateStatusQuery(text) && currentApplication) {
    await sendOctopusTextReply({
      api,
      account,
      conversationId,
      replyTarget,
      text: buildStatusReply(language, currentApplication),
    });
    api.logger.info(`[octopus] fast intent handled kind=status conversation=${conversationId} elapsedMs=${Date.now() - receivedAtMs}`);
    return true;
  }

  return false;
}

async function maybeSendFastCvAcknowledgement(params: {
  api: OpenClawPluginApi;
  cfg: OpenClawConfig;
  account: ResolvedOctopusAccount;
  conversationId: string;
  replyTarget: string | null;
  messageText: string | null;
  receivedAtMs: number;
}): Promise<boolean> {
  const { api, cfg, account, conversationId, replyTarget, messageText, receivedAtMs } = params;
  if (!replyTarget || !isFastIntentEnabled(account.agentId)) return false;
  const workspaceRoot = resolveAgentWorkspacePath(cfg, account.agentId);
  const phone = normalizePhoneDigits(replyTarget);
  if (!workspaceRoot || !phone) return false;
  if (await isHrSender(workspaceRoot, phone)) return false;
  const language = detectConversationLanguage(messageText);
  const currentApplication = pickMostRelevantApplication(await listCandidateApplications(workspaceRoot, phone));
  const positions = currentApplication ? [] : await listActivePositions(workspaceRoot);
  const ackText = buildCvAckReply(language, currentApplication, positions);
  if (!ackText) return false;
  await sendOctopusTextReply({ api, account, conversationId, replyTarget, text: ackText });
  api.logger.info(`[octopus] fast cv ack sent conversation=${conversationId} elapsedMs=${Date.now() - receivedAtMs}`);
  return true;
}

// ---------------------------------------------------------------------------
// Media file utilities
// ---------------------------------------------------------------------------

function getAudioFileExtension(audioMessage: OctopusInboundAudioMessage): string {
  try {
    const pathname = new URL(audioMessage.url).pathname;
    const basename = pathname.split("/").pop() || "";
    const extension = basename.includes(".")
      ? basename.slice(basename.lastIndexOf(".") + 1).toLowerCase()
      : "";
    if (extension) return extension;
  } catch {}
  return (
    {
      "audio/m4a": "m4a", "audio/mp3": "mp3", "audio/mp4": "m4a",
      "audio/mpeg": "mp3", "audio/mpga": "mp3", "audio/ogg": "ogg",
      "audio/opus": "opus", "audio/wav": "wav", "audio/webm": "webm",
      "audio/x-m4a": "m4a",
    }[audioMessage.mimeType || ""] || "ogg"
  );
}

function getImageFileExtension(imageMessage: OctopusInboundImageMessage): string {
  try {
    const pathname = new URL(imageMessage.url).pathname;
    const basename = pathname.split("/").pop() || "";
    const extension = basename.includes(".")
      ? basename.slice(basename.lastIndexOf(".") + 1).toLowerCase()
      : "";
    if (extension) return extension;
  } catch {}
  return (
    {
      "image/bmp": "bmp", "image/gif": "gif", "image/heic": "heic",
      "image/heif": "heif", "image/jpeg": "jpg", "image/jpg": "jpg",
      "image/png": "png", "image/svg+xml": "svg", "image/tiff": "tiff",
      "image/vnd.microsoft.icon": "ico", "image/webp": "webp", "image/x-icon": "ico",
    }[imageMessage.mimeType || ""] || "jpg"
  );
}

function getDocumentFileExtension(documentMessage: OctopusInboundDocumentMessage): string {
  const fileName = documentMessage.fileName || "";
  if (fileName.includes(".")) {
    const ext = fileName.slice(fileName.lastIndexOf(".") + 1).toLowerCase();
    if (ext) return ext;
  }
  try {
    const pathname = new URL(documentMessage.url).pathname;
    const basename = pathname.split("/").pop() || "";
    const extension = basename.includes(".")
      ? basename.slice(basename.lastIndexOf(".") + 1).toLowerCase()
      : "";
    if (extension) return extension;
  } catch {}
  return (
    {
      "application/msword": "doc",
      "application/pdf": "pdf",
      "application/rtf": "rtf",
      "application/vnd.ms-excel": "xls",
      "application/vnd.ms-powerpoint": "ppt",
      "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
      "text/csv": "csv",
      "text/plain": "txt",
    }[documentMessage.mimeType || ""] || "bin"
  );
}

function sanitizePublicMediaFileName(value: string): string {
  const cleaned = value.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
  return cleaned || "file";
}

async function publishLocalMediaFile(params: {
  localPath: string;
  fileName: string;
  publicMediaBaseUrl: string;
}): Promise<string> {
  const { localPath, fileName, publicMediaBaseUrl } = params;
  if (!publicMediaBaseUrl) {
    throw new Error("publicMediaBaseUrl is not configured for local outbound media.");
  }
  await fs.mkdir(PUBLIC_MEDIA_DIR, { recursive: true });
  const stampedName = `${Date.now()}-${sanitizePublicMediaFileName(fileName || path.basename(localPath))}`;
  const publishedPath = path.join(PUBLIC_MEDIA_DIR, stampedName);
  await fs.copyFile(localPath, publishedPath);
  return `${publicMediaBaseUrl}/${encodeURIComponent(stampedName)}`;
}

// ---------------------------------------------------------------------------
// HTTP body parsing & JSON response
// ---------------------------------------------------------------------------

async function readRequestBody(req: any): Promise<{ raw: string; parsed: any }> {
  const chunks: Uint8Array[] = [];
  for await (const chunk of req as AsyncIterable<Uint8Array | string>) {
    chunks.push(nodeBuffer.isBuffer(chunk) ? chunk : nodeBuffer.from(chunk));
  }
  const raw = nodeBuffer.concat(chunks).toString("utf-8");
  if (!raw.trim()) return { raw, parsed: {} };
  try {
    return { raw, parsed: JSON.parse(raw) };
  } catch {
    return { raw, parsed: null };
  }
}

function writeJson(res: any, statusCode: number, payload: Record<string, unknown>): void {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}

// ---------------------------------------------------------------------------
// Reply sanitization
// ---------------------------------------------------------------------------

function isProviderErrorText(value: unknown): boolean {
  const text = asTrimmedString(value);
  if (!text) return false;
  const normalized = text.replace(/\s+/g, " ").trim();
  return (
    normalized.includes("An error occurred while processing your request") ||
    normalized.includes("help.openai.com") ||
    /Please include the request ID req_[a-zA-Z0-9]+/i.test(normalized)
  );
}

function sanitizeAgentReplyText(replyText: unknown): {
  replyText: string;
  providerErrorSuppressed: boolean;
} {
  const text = asTrimmedString(replyText);
  if (!text) return { replyText: "", providerErrorSuppressed: false };
  const blocks = text.split(/\n\s*\n/).map((block) => block.trim()).filter(Boolean);
  const filteredBlocks = blocks.filter((block) => !isProviderErrorText(block));
  const cleaned = filteredBlocks.join("\n\n").trim();
  if (cleaned) {
    return { replyText: cleaned, providerErrorSuppressed: filteredBlocks.length !== blocks.length };
  }
  if (isProviderErrorText(text)) {
    return { replyText: "", providerErrorSuppressed: true };
  }
  return { replyText: text, providerErrorSuppressed: false };
}

function extractReplyTextAndMedia(replyPayload: any): {
  replyText: string;
  mediaUrls: string[];
} {
  const explicitMediaUrls = [
    ...(Array.isArray(replyPayload?.mediaUrls) ? replyPayload.mediaUrls : []),
    replyPayload?.mediaUrl,
  ]
    .map((value) => asTrimmedString(value))
    .filter((value): value is string => Boolean(value));

  const rawText = asTrimmedString(replyPayload?.text) || "";
  const inlineMediaUrls: string[] = [];
  const cleanedText = rawText
    .replace(/^MEDIA:(.+)$/gim, (_match: string, url: string) => {
      const trimmed = asTrimmedString(url);
      if (trimmed) inlineMediaUrls.push(trimmed);
      return "";
    })
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  return {
    replyText: cleanedText,
    mediaUrls: Array.from(new Set([...explicitMediaUrls, ...inlineMediaUrls])),
  };
}

// ---------------------------------------------------------------------------
// Allowlist check
// ---------------------------------------------------------------------------

function isAllowedInbound(account: ResolvedOctopusAccount, conversationId: string, replyTarget: string | null): boolean {
  if (account.dmPolicy === "open") return true;
  if (account.dmPolicy === "disabled") return false;
  const allow = new Set(account.allowFrom.map((entry) => normalizeAllowEntry(entry)));
  if (allow.size === 0) return false;
  const conversationKey = normalizeAllowEntry(conversationId);
  const replyKey = normalizeAllowEntry(replyTarget);
  return allow.has(conversationKey) || (replyKey ? allow.has(replyKey) : false);
}

// ---------------------------------------------------------------------------
// Outbound: AI Octopus API
// ---------------------------------------------------------------------------

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
  state[key] = {
    accountId: params.accountId,
    conversationId: params.conversationId,
    replyTarget: params.replyTarget,
    firstDetectedTs: previous?.firstDetectedTs ?? now,
    lastDetectedTs: now,
    lastError: params.errorText,
    failureCount: (previous?.failureCount ?? 0) + 1,
  };
  await saveClosedConversationAlertState(state);
  params.logger.error(
    `[octopus] operator action required account=${params.accountId} conversation=${params.conversationId} replyTarget=${params.replyTarget} cause=closed_conversation_thread failureCount=${state[key].failureCount}`,
  );
}

async function clearClosedConversationAlerts(params: {
  accountId: string;
  replyTarget: string;
}): Promise<string[]> {
  const state = await loadClosedConversationAlertState();
  const cleared: string[] = [];
  for (const [key, entry] of Object.entries(state)) {
    if (entry.accountId !== params.accountId || entry.replyTarget !== params.replyTarget) continue;
    cleared.push(entry.conversationId);
    delete state[key];
  }
  if (cleared.length > 0) await saveClosedConversationAlertState(state);
  return cleared;
}

// ---------------------------------------------------------------------------
// Typing indicators
// ---------------------------------------------------------------------------

async function sendTypingIndicator(
  account: ResolvedOctopusAccount,
  conversationId: string,
  messageId: string | null,
): Promise<boolean> {
  if (!account.typingEnabled || !conversationId || !messageId || !account.bearerToken) return false;
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
      if (timer) { clearInterval(timer); timer = null; }
      await firstSend;
    },
  };
}

// ---------------------------------------------------------------------------
// Outbound reply
// ---------------------------------------------------------------------------

function shouldMoveToHumanAgent(replyText: string): boolean {
  const normalized = replyText.replace(/\s+/g, " ").trim();
  if (!normalized) return false;
  const escalationMarkers = [
    "تم تحويل محادثتكم لموظف الدعم المختص",
    "تم تحويل المحادثة لموظف الدعم المختص",
    "تم تسجيل الشكوى وتحويلها للإدارة للمراجعة",
    "human agent",
    "moved to a human agent",
    "transferring you to a human",
    "connecting you with a representative",
  ];
  return escalationMarkers.some((marker) => normalized.toLowerCase().includes(marker.toLowerCase()));
}

async function sendOctopusTextReply(params: {
  api: OpenClawPluginApi;
  account: ResolvedOctopusAccount;
  conversationId: string;
  replyTarget: string;
  text: string;
  source?: OctopusReplySource;
}): Promise<void> {
  const { api, account, conversationId, replyTarget, text, source = "reply" } = params;
  const sanitized = sanitizeAgentReplyText(text);
  if (!sanitized.replyText) return;
  const chunkMode = api.runtime.channel.text.resolveChunkMode(api.config, PROVIDER_NAME, account.accountId);
  const chunks = api.runtime.channel.text.chunkMarkdownTextWithMode(
    sanitized.replyText,
    account.textChunkLimit,
    chunkMode,
  );
  for (const chunk of chunks) {
    try {
      await aiOctopusRequest(account, "/client/conversation/reply", {
        messaging_product: "whatsapp",
        conversation_id: conversationId,
        to: replyTarget,
        type: "text",
        recipient_type: "individual",
        text: { body: chunk },
      });
    } catch (error) {
      if (isAiOctopusConversationClosedError(error)) {
        await recordClosedConversationAlert({ accountId: account.accountId, conversationId, replyTarget, logger: api.logger, errorText: error instanceof Error ? error.message : String(error) });
      }
      throw error;
    }
  }
  if (shouldMoveToHumanAgent(sanitized.replyText)) {
    await aiOctopusRequest(account, "/client/conversation/toagent", { conversation_id: conversationId });
  }
  if (source === "reply") {
    const cleared = await clearClosedConversationAlerts({ accountId: account.accountId, replyTarget });
    if (cleared.length > 0) {
      api.logger.info(`[octopus] closed conversation alert cleared replyTarget=${replyTarget} activeConversation=${conversationId} clearedConversations=${cleared.join(",")}`);
    }
  }
  api.logger.info(`[octopus] outbound reply sent conversation=${conversationId} text=${JSON.stringify(sanitized.replyText)}`);
}

// ---------------------------------------------------------------------------
// Media: audio transcription & image save
// ---------------------------------------------------------------------------

async function directOpenAiAudioTranscription(params: {
  audioBuffer: any;
  mimeType: string;
  fileName: string;
}): Promise<string | null> {
  const apiKey = env.OPENAI_API_KEY?.trim();
  if (!apiKey || !webFormData || !webBlob) return null;
  const form = new webFormData();
  form.append("model", "gpt-4o-transcribe");
  form.append("file", new webBlob([params.audioBuffer], { type: params.mimeType }), params.fileName);
  const response = await fetch("https://api.openai.com/v1/audio/transcriptions", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}` },
    body: form,
  });
  if (!response.ok) {
    const raw = await response.text();
    throw new Error(`Direct OpenAI transcription failed: ${response.status} ${raw}`);
  }
  const payload = await response.json();
  return asTrimmedString(payload?.text);
}

async function transcribeAudioMessage(params: {
  api: OpenClawPluginApi;
  account: ResolvedOctopusAccount;
  audioMessage: OctopusInboundAudioMessage;
}): Promise<{ text: string; mediaPath: string; mimeType: string; sizeBytes: number }> {
  const { api, account, audioMessage } = params;
  const response = await fetch(audioMessage.url);
  if (!response.ok) throw new Error(`Audio download failed: ${response.status}`);
  const audioBuffer = nodeBuffer.from(await response.arrayBuffer());
  if (!audioBuffer.length) throw new Error("Audio download returned an empty file.");
  const maxBytes = account.mediaMaxMb * 1024 * 1024;
  if (audioBuffer.length > maxBytes) throw new Error(`Audio file too large (${audioBuffer.length} bytes).`);
  const mimeType = splitMimeType(response.headers.get("content-type")) || audioMessage.mimeType || "audio/ogg";
  const saved = await api.runtime.channel.media.saveMediaBuffer(
    audioBuffer, mimeType, "inbound", maxBytes,
    `voice-note.${getAudioFileExtension({ ...audioMessage, mimeType })}`,
  );
  const maxAttempts = 2;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const transcription = await api.runtime.stt.transcribeAudioFile({ filePath: saved.path, cfg: api.config });
    const text = asTrimmedString(transcription?.text);
    if (text) return { text, mediaPath: saved.path, mimeType, sizeBytes: audioBuffer.length };
    api.logger.warn(`[octopus] audio transcription returned no text attempt=${attempt}/${maxAttempts} mime=${mimeType} size=${audioBuffer.length}`);
    if (attempt < maxAttempts) await new Promise((resolve) => setTimeout(resolve, 400));
  }
  const directText = await directOpenAiAudioTranscription({ audioBuffer, mimeType, fileName: path.basename(saved.path) });
  if (directText) {
    api.logger.info(`[octopus] audio transcribed via direct openai fallback mime=${mimeType} size=${audioBuffer.length}`);
    return { text: directText, mediaPath: saved.path, mimeType, sizeBytes: audioBuffer.length };
  }
  throw new Error(`Audio transcription returned no text after ${maxAttempts} attempts.`);
}

async function saveImageMessage(params: {
  api: OpenClawPluginApi;
  account: ResolvedOctopusAccount;
  imageMessage: OctopusInboundImageMessage;
}): Promise<{ mediaPath: string; mimeType: string; sizeBytes: number }> {
  const { api, account, imageMessage } = params;
  const response = await fetch(imageMessage.url);
  if (!response.ok) throw new Error(`Image download failed: ${response.status}`);
  const imageBuffer = nodeBuffer.from(await response.arrayBuffer());
  if (!imageBuffer.length) throw new Error("Image download returned an empty file.");
  const maxBytes = account.mediaMaxMb * 1024 * 1024;
  if (imageBuffer.length > maxBytes) throw new Error(`Image file too large (${imageBuffer.length} bytes).`);
  const mimeType = splitMimeType(response.headers.get("content-type")) || imageMessage.mimeType || "image/jpeg";
  const saved = await api.runtime.channel.media.saveMediaBuffer(
    imageBuffer, mimeType, "inbound", maxBytes,
    `image.${getImageFileExtension({ ...imageMessage, mimeType })}`,
  );
  return { mediaPath: saved.path, mimeType, sizeBytes: imageBuffer.length };
}

async function saveDocumentMessage(params: {
  api: OpenClawPluginApi;
  account: ResolvedOctopusAccount;
  documentMessage: OctopusInboundDocumentMessage;
}): Promise<{ mediaPath: string; mimeType: string; sizeBytes: number; fileName: string }> {
  const { api, account, documentMessage } = params;
  const response = await fetch(documentMessage.url);
  if (!response.ok) throw new Error(`Document download failed: ${response.status}`);
  const documentBuffer = nodeBuffer.from(await response.arrayBuffer());
  if (!documentBuffer.length) throw new Error("Document download returned an empty file.");
  const maxBytes = account.mediaMaxMb * 1024 * 1024;
  if (documentBuffer.length > maxBytes) throw new Error(`Document file too large (${documentBuffer.length} bytes).`);
  const mimeType = splitMimeType(response.headers.get("content-type")) || documentMessage.mimeType || "application/octet-stream";
  const fileName = documentMessage.fileName || `document.${getDocumentFileExtension({ ...documentMessage, mimeType })}`;
  const saved = await api.runtime.channel.media.saveMediaBuffer(
    documentBuffer, mimeType, "inbound", maxBytes, fileName,
  );
  return { mediaPath: saved.path, mimeType, sizeBytes: documentBuffer.length, fileName };
}

function formatDocumentAsText(documentMessage: OctopusInboundDocumentMessage, savedFileName: string): string {
  const label = savedFileName || documentMessage.fileName || "document";
  const caption = documentMessage.caption;
  return caption ? `${caption}\n\nDocument shared: ${label}` : `Document shared: ${label}`;
}

// ---------------------------------------------------------------------------
// Core: handleInboundMessage — pure transport, no business logic
// ---------------------------------------------------------------------------

async function handleInboundMessage(params: {
  api: OpenClawPluginApi;
  account: ResolvedOctopusAccount;
  payload: any;
  conversationId: string;
  messageText: string | null;
  replyTarget: string | null;
  messageId: string | null;
  audioMessage: OctopusInboundAudioMessage | null;
  imageMessage: OctopusInboundImageMessage | null;
  documentMessage: OctopusInboundDocumentMessage | null;
  locationMessage: OctopusInboundLocationMessage | null;
  receivedAtMs: number;
  debounceWaitMs: number;
}): Promise<void> {
  const {
    api, account, payload, conversationId, messageText, replyTarget, messageId,
    audioMessage, imageMessage, documentMessage, locationMessage,
    receivedAtMs, debounceWaitMs,
  } = params;

  if (!isAllowedInbound(account, conversationId, replyTarget)) {
    api.logger.info(`[octopus] blocked by allowlist conversation=${conversationId} replyTarget=${replyTarget || "unknown"}`);
    return;
  }

  const inboundStartMs = Date.now();
  api.logger.info(
    `[octopus] timing stage=inbound_start conversation=${conversationId} replyTarget=${replyTarget || ""} debounceWaitMs=${debounceWaitMs} elapsedMs=${inboundStartMs - receivedAtMs}`,
  );

  if (!audioMessage && !imageMessage && !documentMessage && !locationMessage) {
    const fastHandled = await maybeHandleFastTextIntent({
      api,
      cfg: api.config,
      account,
      conversationId,
      replyTarget,
      messageText,
      receivedAtMs,
    });
    if (fastHandled) {
      api.logger.info(
        `[octopus] timing stage=fast_intent_complete conversation=${conversationId} totalMs=${Date.now() - receivedAtMs}`,
      );
      return;
    }
  }

  const promptSessionRevision = await resolveAgentWorkspacePromptRevision(api.config, account.agentId);

  // --- Transcribe audio ---
  let resolvedText = messageText;
  let mediaPath: string | null = null;
  let mediaType: string | null = null;
  if (audioMessage && !resolvedText) {
    try {
      const transcription = await transcribeAudioMessage({ api, account, audioMessage });
      resolvedText = transcription.text;
      mediaPath = transcription.mediaPath;
      mediaType = transcription.mimeType;
      api.logger.info(`[octopus] audio transcribed conversation=${conversationId} text=${JSON.stringify(resolvedText)}`);
    } catch (error) {
      api.logger.error(`[octopus] audio transcription failed conversation=${conversationId} error=${error instanceof Error ? error.message : String(error)}`);
    }
  }

  // --- Save image ---
  if (imageMessage) {
    try {
      const saved = await saveImageMessage({ api, account, imageMessage });
      mediaPath = saved.mediaPath;
      mediaType = saved.mimeType;
      api.logger.info(`[octopus] image saved conversation=${conversationId} path=${saved.mediaPath}`);
    } catch (error) {
      api.logger.error(`[octopus] image save failed conversation=${conversationId} error=${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (documentMessage) {
    try {
      const saved = await saveDocumentMessage({ api, account, documentMessage });
      mediaPath = saved.mediaPath;
      mediaType = saved.mimeType;
      if (!resolvedText) {
        resolvedText = formatDocumentAsText(documentMessage, saved.fileName);
      }
      api.logger.info(`[octopus] document saved conversation=${conversationId} path=${saved.mediaPath} filename=${JSON.stringify(saved.fileName)}`);
    } catch (error) {
      api.logger.error(`[octopus] document save failed conversation=${conversationId} error=${error instanceof Error ? error.message : String(error)}`);
    }
  }

  // --- Format location ---
  if (locationMessage && !resolvedText) {
    resolvedText = formatLocationAsText(locationMessage);
  } else if (locationMessage && resolvedText) {
    resolvedText = `${resolvedText}\n\n${formatLocationAsText(locationMessage)}`;
  }

  const rawBody = resolvedText || "";
  if (!rawBody && !mediaPath) {
    api.logger.info(`[octopus] no actionable content conversation=${conversationId}`);
    return;
  }

  if (audioMessage || imageMessage || documentMessage) {
    await maybeSendFastCvAcknowledgement({
      api,
      cfg: api.config,
      account,
      conversationId,
      replyTarget,
      messageText: resolvedText,
      receivedAtMs,
    }).catch((error) => {
      api.logger.warn(
        `[octopus] fast cv ack failed conversation=${conversationId} error=${error instanceof Error ? error.message : String(error)}`,
      );
    });
  }

  // --- Build session key ---
  const sessionKey = api.runtime.channel.routing.buildAgentSessionKey({
    agentId: account.agentId,
    channel: PROVIDER_NAME,
    accountId: account.accountId,
    peer: {
      kind: "direct",
      id: promptSessionRevision ? `${conversationId}::prompt=${promptSessionRevision}` : conversationId,
    },
    dmScope: api.config.session?.dmScope,
  });

  const senderId = replyTarget || conversationId;

  // --- Build inbound context ---
  const storePath = api.runtime.channel.session.resolveStorePath(api.config.session?.store);
  const ctxPayload = api.runtime.channel.reply.finalizeInboundContext({
    Body: rawBody,
    BodyForAgent: rawBody,
    RawBody: rawBody,
    CommandBody: rawBody,
    From: replyTarget ? `octopus:${replyTarget}` : `octopus:conversation:${conversationId}`,
    To: `octopus:${conversationId}`,
    SessionKey: sessionKey,
    AgentId: account.agentId,
    AccountId: account.accountId,
    ChatType: "direct",
    ConversationLabel: replyTarget ? `customer:${replyTarget}` : `customer:conversation:${conversationId}`,
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
    Metadata: payload,
  });

  // --- Record session ---
  await api.runtime.channel.session.recordInboundSession({
    storePath,
    sessionKey: ctxPayload.SessionKey ?? sessionKey,
    ctx: ctxPayload,
    onRecordError: (error: unknown) => {
      api.logger.error(`[octopus] failed updating session meta: ${String(error)}`);
    },
  });

  // --- Start typing ---
  const typingLoop = startTypingLoop({ account, conversationId, messageId, logger: api.logger });

  if (replyTarget && conversationId) {
    phoneToConversationId.set(replyTarget, conversationId);
  }

  api.logger.info(
    `[octopus] inbound routed account=${account.accountId} conversation=${conversationId} agent=${account.agentId} replyTarget=${replyTarget || ""} promptSessionRevision=${promptSessionRevision}`,
  );
  api.logger.info(
    `[octopus] timing stage=dispatch_ready conversation=${conversationId} elapsedMs=${Date.now() - receivedAtMs}`,
  );

  try {
    await api.runtime.channel.reply.dispatchReplyWithBufferedBlockDispatcher({
      ctx: ctxPayload,
      cfg: api.config,
      dispatcherOptions: {
        deliver: async (replyPayload: any) => {
          if (!replyTarget) return;
          const { replyText, mediaUrls } = extractReplyTextAndMedia(replyPayload);
          if (replyText) {
            await sendOctopusTextReply({
              api, account, conversationId, replyTarget,
              text: replyText, source: "reply",
            });
            api.logger.info(
              `[octopus] timing stage=first_text_reply conversation=${conversationId} elapsedMs=${Date.now() - receivedAtMs}`,
            );
          }
          for (const mediaUrl of mediaUrls) {
            await octopusPlugin.outbound.sendMedia({
              cfg: api.config,
              accountId: account.accountId,
              to: replyTarget,
              mediaUrl,
              mediaReadFile: async (mediaPath: string) => fs.readFile(mediaPath),
            });
            api.logger.info(`[octopus] outbound media sent conversation=${conversationId} media=${JSON.stringify(mediaUrl)}`);
          }
          api.logger.info(
            `[octopus] timing stage=deliver_complete conversation=${conversationId} elapsedMs=${Date.now() - receivedAtMs}`,
          );
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
    api.logger.info(
      `[octopus] timing stage=turn_complete conversation=${conversationId} elapsedMs=${Date.now() - receivedAtMs} processingMs=${Date.now() - inboundStartMs}`,
    );
  }
}

// ---------------------------------------------------------------------------
// Webhook route builder
// ---------------------------------------------------------------------------

function buildWebhookRoutes(cfg: OpenClawConfig): Array<{ accountId: string; path: string }> {
  const routes: Array<{ accountId: string; path: string }> = [];
  for (const accountId of listOctopusAccountIds(cfg)) {
    const account = resolveOctopusAccount(cfg, accountId);
    if (!account.enabled) continue;
    routes.push({ accountId: account.accountId, path: account.webhookPath });
    if (account.webhookPath !== "/") {
      routes.push({ accountId: account.accountId, path: "/" });
    }
  }
  return routes;
}

// ---------------------------------------------------------------------------
// Plugin definition
// ---------------------------------------------------------------------------

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
  outbound: {
    deliveryMode: "direct" as const,
    chunkerMode: "markdown" as const,
    textChunkLimit: DEFAULT_TEXT_CHUNK_LIMIT,
    chunker: (text: string, limit: number) => {
      const chunks: string[] = [];
      let remaining = text;
      while (remaining.length > limit) {
        let splitAt = remaining.lastIndexOf("\n", limit);
        if (splitAt <= 0) splitAt = limit;
        chunks.push(remaining.slice(0, splitAt).trim());
        remaining = remaining.slice(splitAt).trim();
      }
      if (remaining) chunks.push(remaining);
      return chunks;
    },
    resolveTarget: (params: { cfg?: OpenClawConfig; to?: string; accountId?: string | null }) => {
      const to = asTrimmedString(params.to);
      if (!to) return { ok: false as const, error: new Error("No target phone/conversation specified.") };
      return { ok: true as const, to: to.replace(/^\+/, "") };
    },
    async sendText(ctx: any): Promise<any> {
      const account = resolveOctopusAccount(ctx.cfg, ctx.accountId);
      if (!account.bearerToken) throw new Error("AI_OCTOPUS_BEARER_TOKEN is missing for outbound.");
      const to = asTrimmedString(ctx.to) || "";
      const conversationId = phoneToConversationId.get(to) || to;
      const text = asTrimmedString(ctx.text) || "";
      if (!text) return { channel: PROVIDER_NAME, messageId: `suppressed-${Date.now()}` };
      const sanitized = sanitizeAgentReplyText(text);
      if (!sanitized.replyText) return { channel: PROVIDER_NAME, messageId: `suppressed-${Date.now()}` };
      const result = await aiOctopusRequest(account, "/client/conversation/reply", {
        messaging_product: "whatsapp",
        conversation_id: conversationId,
        to,
        type: "text",
        recipient_type: "individual",
        text: { body: sanitized.replyText },
      });
      const messageId = result?.messages?.[0]?.id || `octopus-${Date.now()}`;
      return { channel: PROVIDER_NAME, messageId };
    },
    async sendMedia(ctx: any): Promise<any> {
      const account = resolveOctopusAccount(ctx.cfg, ctx.accountId);
      if (!account.bearerToken) throw new Error("AI_OCTOPUS_BEARER_TOKEN is missing for outbound.");
      const to = asTrimmedString(ctx.to) || "";
      const conversationId = phoneToConversationId.get(to) || to;
      const mediaUrl = asTrimmedString(ctx.mediaUrl) || "";
      if (!mediaUrl) throw new Error("No media URL provided.");

      let mediaBuffer: any = null;
      let mimeType = "application/octet-stream";
      let fileName = "file";

      const isLocalFile = mediaUrl.startsWith("/");
      if (isLocalFile && ctx.mediaReadFile) {
        try {
          mediaBuffer = await ctx.mediaReadFile(mediaUrl);
          const ext = mediaUrl.split("/").pop()?.split(".").pop()?.toLowerCase() || "";
          const mimeMap: Record<string, string> = {
            png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif",
            webp: "image/webp", mp4: "video/mp4", pdf: "application/pdf",
            ogg: "audio/ogg", mp3: "audio/mpeg", m4a: "audio/m4a",
          };
          mimeType = mimeMap[ext] || "application/octet-stream";
          fileName = mediaUrl.split("/").pop() || "file";
        } catch (err) {
          throw new Error(`Failed to read media file: ${mediaUrl} — ${err instanceof Error ? err.message : String(err)}`);
        }
      } else if (!isLocalFile) {
        try {
          const resp = await fetch(mediaUrl);
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          mediaBuffer = nodeBuffer.from(await resp.arrayBuffer());
          mimeType = splitMimeType(resp.headers.get("content-type")) || "application/octet-stream";
          fileName = mediaUrl.split("/").pop()?.split("?")[0] || "file";
        } catch (err) {
          throw new Error(`Failed to fetch media: ${err instanceof Error ? err.message : String(err)}`);
        }
      }

      const isImage = mimeType.startsWith("image/");
      const caption = asTrimmedString(ctx.text) || undefined;

      if (isLocalFile && account.publicMediaBaseUrl) {
        const publishedUrl = await publishLocalMediaFile({
          localPath: mediaUrl,
          fileName,
          publicMediaBaseUrl: account.publicMediaBaseUrl,
        });
        await aiOctopusRequest(account, "/client/conversation/reply", {
          messaging_product: "whatsapp",
          conversation_id: conversationId,
          to,
          type: isImage ? "image" : "document",
          recipient_type: "individual",
          ...(isImage
            ? { image: { link: publishedUrl, caption } }
            : { document: { link: publishedUrl, caption, filename: fileName } }),
        });
      } else if (mediaBuffer && mediaBuffer.length) {
        const b64 = nodeBuffer.from(mediaBuffer).toString("base64");
        const dataUri = `data:${mimeType};base64,${b64}`;
        await aiOctopusRequest(account, "/client/conversation/reply", {
          messaging_product: "whatsapp",
          conversation_id: conversationId,
          to,
          type: isImage ? "image" : "document",
          recipient_type: "individual",
          ...(isImage
            ? { image: { data: dataUri, caption } }
            : { document: { data: dataUri, caption, filename: fileName } }),
        });
      } else if (!isLocalFile) {
        await aiOctopusRequest(account, "/client/conversation/reply", {
          messaging_product: "whatsapp",
          conversation_id: conversationId,
          to,
          type: isImage ? "image" : "document",
          recipient_type: "individual",
          ...(isImage
            ? { image: { link: mediaUrl, caption } }
            : { document: { link: mediaUrl, caption, filename: fileName } }),
        });
      } else {
        throw new Error("Cannot read local media file (no mediaReadFile helper available).");
      }

      return { channel: PROVIDER_NAME, messageId: `octopus-media-${Date.now()}` };
    },
  },
};

const plugin = {
  id: "octopus-channel",
  name: "AI Octopus Channel",
  description: "Generic AI Octopus channel transport for OpenClaw.",
  configSchema: {
    type: "object",
    additionalProperties: false,
    properties: {},
  },
  register(api: OpenClawPluginApi) {
    api.registerChannel({ plugin: octopusPlugin });
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
          const receivedAtMs = Date.now();
          if (req.method === "GET") {
            writeJson(res, 200, { ok: true, status: "ready" });
            return true;
          }
          if (req.method !== "POST") {
            res.statusCode = 405;
            res.setHeader("Content-Type", "text/plain; charset=utf-8");
            res.end("Method Not Allowed");
            return true;
          }
          const account = resolveOctopusAccount(api.config, route.accountId);
          if (!account.enabled) {
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
              writeJson(res, 401, { ok: false, message: "Unauthorized" });
              return true;
            }
          }
          const { raw, parsed } = await readRequestBody(req);
          if (!parsed || typeof parsed !== "object") {
            writeJson(res, 400, { ok: false, message: "Invalid JSON payload", raw });
            return true;
          }
          const messageText = extractMessageText(parsed);
          const replyTarget = extractReplyTarget(parsed);
          const messageId = extractWhatsAppMessageId(parsed);
          const audioMessage = !messageText ? extractAudioMessage(parsed) : null;
          const imageMessage = extractImageMessage(parsed);
          const documentMessage = extractDocumentMessage(parsed);
          const locationMessage = extractLocationMessage(parsed);
          const conversationIdValue = extractConversationId(parsed);
          if (conversationIdValue === null) {
            const isValidationProbe =
              !raw.trim() || (!messageText && !audioMessage && !imageMessage && !documentMessage && !locationMessage && !replyTarget && !messageId);
            if (isValidationProbe) {
              writeJson(res, 200, { ok: true, status: "ready", probe: true });
              return true;
            }
            writeJson(res, 400, { ok: false, message: "conversation_id is required" });
            return true;
          }
          const conversationId = String(conversationIdValue);
          api.logger.info(
            `[octopus] timing stage=webhook_received conversation=${conversationId} method=${req.method} elapsedMs=${Date.now() - receivedAtMs}`,
          );
          writeJson(res, 200, {
            ok: true,
            accepted: true,
            conversation_id: conversationId,
            reply_target: replyTarget,
            message_id: messageId,
            has_message_text: Boolean(messageText),
            has_audio_message: Boolean(audioMessage),
            has_image_message: Boolean(imageMessage),
            has_document_message: Boolean(documentMessage),
            has_location_message: Boolean(locationMessage),
            received_at: new Date().toISOString(),
          });
          if (!messageText && !audioMessage && !imageMessage && !documentMessage && !locationMessage) {
            api.logger.info(`[octopus] ignored non-text payload conversation=${conversationId} raw=${JSON.stringify(parsed).slice(0, 500)}`);
            return true;
          }
          enqueueInboundMessage({
            api, account, payload: parsed, conversationId,
            messageText, replyTarget, messageId,
            audioMessage, imageMessage, documentMessage, locationMessage,
            receivedAtMs,
          });
          return true;
        },
      });
    }
  },
};

export default plugin;
