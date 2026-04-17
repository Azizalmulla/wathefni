import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";

export interface PersistedQuotedRouteState {
  routeKey: string;
  pickupAreaNameAr: string;
  pickupAreaNameEn: string;
  dropoffAreaNameAr: string;
  dropoffAreaNameEn: string;
  pricesByType: Record<string, number>;
  optionCatalog: Array<{
    delivery_type: string;
    label_ar: string;
    label_en: string;
    quoted_price: number | null;
    formatted_price: string | null;
    visibility: string | null;
    direct_chat_booking_status: string | null;
    direct_chat_booking_note: string | null;
  }>;
  serviceDiscovery: {
    default_prompt_ar: string | null;
    default_prompt_en: string | null;
  } | null;
  quotedAt: number;
  quoteRef: string;
}

export interface PersistedGuardSessionState {
  allValidPrices: Set<string>;
  lastToolName: string | null;
  lastCustomerMessage: string | null;
  lastCustomerMessages: { ar: string | null; en: string | null };
  lastToolTs: number;
  lastQuotedRoute: PersistedQuotedRouteState | null;
  pendingOrderSummary: {
    fingerprint: string;
    createdAt: number;
  } | null;
  // Captured when a successful create_simple_order result is recorded. Lets
  // downstream code (controller stage transition, post-order correction
  // directive) reference the order UID without re-parsing tool output.
  lastCreatedOrderUid?: string | null;
}

type SerializedGuardSessionState = {
  allValidPrices: string[];
  lastToolName: string | null;
  lastCustomerMessage: string | null;
  lastCustomerMessages: { ar: string | null; en: string | null };
  lastToolTs: number;
  lastQuotedRoute: PersistedQuotedRouteState | null;
  pendingOrderSummary: {
    fingerprint: string;
    createdAt: number;
  } | null;
  lastCreatedOrderUid?: string | null;
};

const OPENCLAW_PROFILE = String(process.env.OPENCLAW_PROFILE || "delivery").trim() || "delivery";
const GUARD_STATE_TTL_MS = 2 * 60 * 60_000;
const GUARD_STATE_PATH = path.join(os.homedir(), `.openclaw-${OPENCLAW_PROFILE}`, "riders-guard-state.json");

function serializeGuardSession(session: PersistedGuardSessionState): SerializedGuardSessionState {
  return {
    allValidPrices: [...session.allValidPrices],
    lastToolName: session.lastToolName,
    lastCustomerMessage: session.lastCustomerMessage,
    lastCustomerMessages: session.lastCustomerMessages,
    lastToolTs: Number(session.lastToolTs || 0),
    lastQuotedRoute: session.lastQuotedRoute
      ? {
          ...session.lastQuotedRoute,
          pricesByType: { ...(session.lastQuotedRoute.pricesByType || {}) },
          optionCatalog: Array.isArray(session.lastQuotedRoute.optionCatalog)
            ? session.lastQuotedRoute.optionCatalog.map((option) => ({ ...option }))
            : [],
          serviceDiscovery: session.lastQuotedRoute.serviceDiscovery
            ? { ...session.lastQuotedRoute.serviceDiscovery }
            : null,
        }
      : null,
    pendingOrderSummary: session.pendingOrderSummary ? { ...session.pendingOrderSummary } : null,
    lastCreatedOrderUid: session.lastCreatedOrderUid || null,
  };
}

function deserializeGuardSession(
  session: SerializedGuardSessionState | null | undefined,
): PersistedGuardSessionState | null {
  if (!session || typeof session !== "object") {
    return null;
  }
  return {
    allValidPrices: new Set(Array.isArray(session.allValidPrices) ? session.allValidPrices : []),
    lastToolName: session.lastToolName || null,
    lastCustomerMessage: session.lastCustomerMessage || null,
    lastCustomerMessages: {
      ar: session.lastCustomerMessages?.ar || null,
      en: session.lastCustomerMessages?.en || null,
    },
    lastToolTs: Number(session.lastToolTs || 0),
    lastQuotedRoute: session.lastQuotedRoute
      ? {
          ...session.lastQuotedRoute,
          pricesByType: { ...(session.lastQuotedRoute.pricesByType || {}) },
          optionCatalog: Array.isArray(session.lastQuotedRoute.optionCatalog)
            ? session.lastQuotedRoute.optionCatalog.map((option) => ({ ...option }))
            : [],
          serviceDiscovery: session.lastQuotedRoute.serviceDiscovery
            ? { ...session.lastQuotedRoute.serviceDiscovery }
            : null,
        }
      : null,
    pendingOrderSummary: session.pendingOrderSummary ? { ...session.pendingOrderSummary } : null,
    lastCreatedOrderUid: session.lastCreatedOrderUid || null,
  };
}

async function loadPersistedGuardState(): Promise<Record<string, SerializedGuardSessionState>> {
  try {
    const raw = await fs.readFile(GUARD_STATE_PATH, "utf8");
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return {};
    }
    return parsed;
  } catch (error: any) {
    if (error?.code === "ENOENT") {
      return {};
    }
    throw error;
  }
}

async function savePersistedGuardState(
  state: Record<string, SerializedGuardSessionState>,
): Promise<void> {
  await fs.mkdir(path.dirname(GUARD_STATE_PATH), { recursive: true });
  const tempPath = `${GUARD_STATE_PATH}.tmp`;
  await fs.writeFile(tempPath, JSON.stringify(state, null, 2) + "\n", "utf8");
  await fs.rename(tempPath, GUARD_STATE_PATH);
}

function pruneStaleEntries(
  state: Record<string, SerializedGuardSessionState>,
): Record<string, SerializedGuardSessionState> {
  const now = Date.now();
  for (const [key, session] of Object.entries(state)) {
    if (now - Number(session?.lastToolTs || 0) > GUARD_STATE_TTL_MS) {
      delete state[key];
    }
  }
  return state;
}

export async function persistGuardSessionAliases(
  aliases: string[],
  session: PersistedGuardSessionState,
): Promise<void> {
  const state = pruneStaleEntries(await loadPersistedGuardState());
  const serialized = serializeGuardSession(session);
  for (const alias of aliases.map((value) => String(value || "").trim()).filter(Boolean)) {
    state[alias] = serialized;
  }
  await savePersistedGuardState(state);
}

export async function findPersistedGuardSession(params: {
  activeSessionKey: string;
  conversationId: string;
  replyTarget?: string | null;
}): Promise<{ key: string; session: PersistedGuardSessionState | null }> {
  const state = pruneStaleEntries(await loadPersistedGuardState());
  const directCandidates = [
    params.activeSessionKey,
    params.conversationId,
    params.replyTarget || "",
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  for (const candidate of directCandidates) {
    const session = deserializeGuardSession(state[candidate]);
    if (session) {
      return { key: candidate, session };
    }
  }
  const sessionConversationNeedle = `:octopus:direct:${params.conversationId}::prompt=`;
  const sessionConversationSuffix = `:octopus:direct:${params.conversationId}`;
  let bestKey = "";
  let bestSession: PersistedGuardSessionState | null = null;
  for (const [key, sessionValue] of Object.entries(state)) {
    if (
      key.includes(sessionConversationNeedle) ||
      key.endsWith(sessionConversationSuffix) ||
      (params.replyTarget && key === params.replyTarget)
    ) {
      const session = deserializeGuardSession(sessionValue);
      if (!session) {
        continue;
      }
      if (!bestSession || Number(session.lastToolTs || 0) > Number(bestSession.lastToolTs || 0)) {
        bestKey = key;
        bestSession = session;
      }
    }
  }
  return { key: bestKey || params.activeSessionKey, session: bestSession };
}
