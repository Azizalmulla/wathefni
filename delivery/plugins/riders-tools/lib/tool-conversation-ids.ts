/**
 * Class-11 stash (2026-04-21) — `stripped_tool_ctx_loses_conversation_identity`.
 *
 * OpenClaw's tool runtime passes a thinner `ctx` into `tool.execute(...)` than
 * the ctx it hands to inbound-dispatch and `after_tool_call` hooks. The
 * Octopus inbound path already builds a rich ctx payload via
 * `finalizeInboundContext` that carries `ConversationId`, `SessionKey`,
 * `ControllerStateKey`, `NativeChannelId`, and `To=octopus:<conversationId>` —
 * but by the time the LLM calls `get_price`, those fields are no longer on
 * the ctx object the tool receives.
 *
 * The pricing tool is the only code path that needs to push responder-state
 * ops (`set_pending_area`, `set_requested_slot`) mid-`execute()`. When its
 * ctx is stripped, every alias is empty, the push is skipped, no state is
 * persisted, and the next turn inherits nothing — this is the exact blocker
 * path we saw on conv 19127 turn 1.
 *
 * Fix mirrors the existing `__ridersLastCustomerText` pattern: the Octopus
 * channel writes the current turn's identity onto a process-local stash at
 * ingress, and the resolvers below consult the stash as a FALLBACK (only
 * when the ctx carries nothing). Push/drain stay keyed by the real
 * conversation id so there's no cross-conversation contamination — the stash
 * is a belt-and-braces identity carrier, not a new keying scheme.
 */
/**
 * Class-17 (2026-04-21) — `stripped_tool_ctx_loses_booking_authority`.
 *
 * Minimal, ctx-independent authority snapshot taken at inbound-ingress time
 * and stashed alongside the identity fields. Only the controller properties
 * that the tool-boundary guards actually read are carried:
 *
 *   - `pendingPickupAreaNameEn` / `pendingDropoffAreaNameEn`: the pinned
 *     opposite-side areas the symmetric-rebind guard in `pricing.ts` needs
 *     to override a `get_price(pickup=X, dropoff=X)` call to the correct
 *     non-requested leg.
 *   - `requestedSlot`: the DST slot the customer is currently answering,
 *     used by both the symmetric-rebind guard and the DST misroute swap.
 *   - `stage` / `bookingStep`: echoed so `getBookingAuthorityFallback`
 *     matches the shape `getNormalizedBookingAuthority` returns.
 *
 * Deliberately excluded: the full `bookingDraft`, quote fields, and anything
 * the tool can recompute or doesn't gate on. Keeping the payload small also
 * keeps the stash TTL window honest — we never want a long-lived snapshot
 * masquerading as live state.
 */
export interface StashedBookingAuthority {
  stage: string;
  bookingStep: string;
  pendingPickupAreaNameEn: string | null;
  pendingPickupAreaNameAr: string | null;
  pendingDropoffAreaNameEn: string | null;
  pendingDropoffAreaNameAr: string | null;
  requestedSlot: {
    name: string;
    options: string[] | null;
  } | null;
}

export interface CurrentTurnIdentity {
  conversationId: string;
  sessionKey: string;
  controllerStateKey: string;
  replyTarget: string;
  senderId: string;
  /** Class-17 authority snapshot. Optional for back-compat with older
   *  producers that only write identity. When absent, consumers behave as
   *  if the ctx-derived authority was unavailable. */
  bookingAuthority?: StashedBookingAuthority | null;
  ts: number;
}

const CURRENT_TURN_IDENTITY_KEY = "__ridersCurrentTurnIdentity__";
const IDENTITY_TTL_MS = 5 * 60_000;

function getIdentityStash(): CurrentTurnIdentity | null {
  const g = globalThis as any;
  const stash = g[CURRENT_TURN_IDENTITY_KEY] as CurrentTurnIdentity | undefined;
  if (!stash) return null;
  if (!stash.conversationId && !stash.controllerStateKey && !stash.sessionKey) {
    return null;
  }
  if (Date.now() - (stash.ts || 0) > IDENTITY_TTL_MS) return null;
  return stash;
}

/**
 * Called by `octopus-channel` at inbound ingress to publish the current
 * turn's identity for the tool path to pick up when its ctx is stripped.
 */
export function setCurrentTurnIdentity(
  identity: Omit<CurrentTurnIdentity, "ts">,
): void {
  const g = globalThis as any;
  g[CURRENT_TURN_IDENTITY_KEY] = {
    conversationId: String(identity.conversationId || "").trim(),
    sessionKey: String(identity.sessionKey || "").trim(),
    controllerStateKey: String(identity.controllerStateKey || "").trim(),
    replyTarget: String(identity.replyTarget || "").trim(),
    senderId: String(identity.senderId || "").trim(),
    bookingAuthority: identity.bookingAuthority ?? null,
    ts: Date.now(),
  };
}

/**
 * Class-17 (2026-04-21). Patch the booking-authority snapshot onto the
 * existing stash without resetting identity. Octopus-channel calls this
 * after loading `conversationControllerEntry` so the tool path can see
 * the same authority the orchestrator sees, even when the tool ctx is
 * stripped of identity fields. If the stash hasn't been initialised yet
 * (tests / cold boot), this is a no-op to avoid writing a half-built
 * record — the identity write will land first in real traffic.
 */
export function setCurrentTurnBookingAuthority(
  authority: StashedBookingAuthority | null,
): void {
  const g = globalThis as any;
  const existing = g[CURRENT_TURN_IDENTITY_KEY] as CurrentTurnIdentity | undefined;
  if (!existing) return;
  g[CURRENT_TURN_IDENTITY_KEY] = {
    ...existing,
    bookingAuthority: authority,
    ts: Date.now(),
  };
}

export function clearCurrentTurnIdentity(): void {
  const g = globalThis as any;
  g[CURRENT_TURN_IDENTITY_KEY] = undefined;
}

/**
 * Class-17 consumer. Returns the booking-authority snapshot stashed at
 * inbound ingress if it is still within the identity TTL, else null.
 * Callers (today: `pricing.ts`) use this as a FALLBACK when the tool ctx
 * has no readable `ConversationLabel` / `Surface` so
 * `getNormalizedBookingAuthority(ctx)` returns an empty shell. Logs a
 * single observability line the first time per-turn a consumer reaches
 * for it so we can track how often the stripped-ctx path is taken in
 * production vs how often the real ctx carries authority directly.
 */
export function getStashedBookingAuthority(
  reason = "stripped_tool_ctx",
): StashedBookingAuthority | null {
  const stash = getIdentityStash();
  if (!stash?.bookingAuthority) return null;
  try {
    // eslint-disable-next-line no-console
    console.log(
      `[responder-ops/authority-fallback] source=current_turn_booking_authority primary=${stash.conversationId} ` +
        `stage=${stash.bookingAuthority.stage} bookingStep=${stash.bookingAuthority.bookingStep} ` +
        `pending_pickup=${stash.bookingAuthority.pendingPickupAreaNameEn || "-"} ` +
        `pending_dropoff=${stash.bookingAuthority.pendingDropoffAreaNameEn || "-"} ` +
        `requested_slot=${stash.bookingAuthority.requestedSlot?.name || "-"} reason=${reason}`,
    );
  } catch {}
  return stash.bookingAuthority;
}

/**
 * Visible only to tests — returns the raw stash without TTL filtering so a
 * smoke test can assert the exact values written at ingress.
 */
export function peekCurrentTurnIdentity(): CurrentTurnIdentity | null {
  const g = globalThis as any;
  return (g[CURRENT_TURN_IDENTITY_KEY] as CurrentTurnIdentity | undefined) || null;
}

export function resolveToolConversationId(ctx: any): string {
  const direct = String(
    ctx?.ConversationId || ctx?.conversationId || ctx?.ConversationID || "",
  ).trim();
  if (direct) return direct;

  const nativeChannelId = String(
    ctx?.NativeChannelId || ctx?.nativeChannelId || "",
  ).trim();
  if (nativeChannelId) return nativeChannelId;

  const sessionKey = String(ctx?.SessionKey || ctx?.sessionKey || "").trim();
  const match = sessionKey.match(/:octopus:direct:(.+?)(?:::prompt=|$)/);
  if (match?.[1]) {
    return match[1].trim();
  }

  const controllerStateKey = String(
    ctx?.ControllerStateKey || ctx?.controllerStateKey || "",
  ).trim();
  if (controllerStateKey) {
    const controllerMatch = controllerStateKey.match(/^[^:]+::(.+)$/);
    if (controllerMatch?.[1]) {
      return controllerMatch[1].trim();
    }
  }

  // Octopus tool contexts often set `To=octopus:<replyTarget>` where the
  // suffix is the WhatsApp number, not the live conversation id. When both
  // `SessionKey` and `To` are present, `SessionKey` is the authoritative
  // source for responder-op routing because the octopus-channel drain keys by
  // conversation id (e.g. `19055`), not reply target (`965...`).
  const to = String(ctx?.To || ctx?.to || "").trim();
  if (to.startsWith("octopus:")) {
    const extracted = to.slice("octopus:".length).trim();
    if (extracted) return extracted;
  }

  // Class-11 fallback: the ctx the LLM tool runtime hands us is sometimes
  // stripped of every routing field. When that happens, consult the
  // process-local stash published by `octopus-channel` at inbound ingress.
  const stash = getIdentityStash();
  if (stash?.conversationId) {
    try {
      // eslint-disable-next-line no-console
      console.log(
        `[responder-ops/identity-fallback] source=current_turn_identity primary=${stash.conversationId} reason=stripped_tool_ctx`,
      );
    } catch {}
    return stash.conversationId;
  }
  if (stash?.controllerStateKey) {
    const controllerMatch = stash.controllerStateKey.match(/^[^:]+::(.+)$/);
    if (controllerMatch?.[1]) {
      try {
        // eslint-disable-next-line no-console
        console.log(
          `[responder-ops/identity-fallback] source=current_turn_identity primary=${controllerMatch[1]} reason=stripped_tool_ctx_controller_only`,
        );
      } catch {}
      return controllerMatch[1];
    }
  }

  return "";
}

/**
 * Collect every plausible conversation identifier present on a tool `ctx`.
 *
 * The Octopus tool pipeline historically exposes multiple different ids that
 * could each be "the" conversation key depending on code path:
 *
 *   - `ConversationId` / `conversationId` / `NativeChannelId` — the
 *     authoritative numeric channel id (e.g. `19055`).
 *   - `SessionKey` — contains the conversation id embedded as
 *     `agent:riders:octopus:direct:<id>::prompt=...`.
 *   - `ControllerStateKey` — canonical controller storage key
 *     (`default::<conversationId>`).
 *   - `replyTarget` / `SenderId` / `current_customer_whatsapp` — reply-target
 *     aliases that appear on some tool ctx shapes even when conversation ids
 *     are absent.
 *   - `To` / `OriginatingTo` — `octopus:<replyTarget>` when the runtime has
 *     flipped the direction for reply rendering; the suffix is the customer's
 *     WhatsApp number rather than the conversation id.
 *
 * When `pushResponderStateOp` runs under only ONE of these keys and the
 * orchestrator drains under a different one, the clarification op is silently
 * lost. Producers (tool push) and consumers (drain) both use this helper so
 * every op lands under every candidate key, and `drainResponderStateOps`
 * dedups at the end.
 */
export function resolveToolConversationAliases(ctx: any): string[] {
  const aliases: string[] = [];
  const seen = new Set<string>();
  const add = (raw: unknown) => {
    if (raw == null) return;
    const value = String(raw).trim();
    if (!value || seen.has(value)) return;
    seen.add(value);
    aliases.push(value);
  };

  add(ctx?.ConversationId);
  add(ctx?.conversationId);
  add(ctx?.ConversationID);
  add(ctx?.NativeChannelId);
  add(ctx?.nativeChannelId);
  add(ctx?.ControllerStateKey);
  add(ctx?.controllerStateKey);

  const sessionKey = String(ctx?.SessionKey || ctx?.sessionKey || "").trim();
  const sessionMatch = sessionKey.match(/:octopus:direct:(.+?)(?:::prompt=|$)/);
  if (sessionMatch?.[1]) add(sessionMatch[1]);
  if (sessionKey) add(sessionKey);

  const controllerStateKey = String(
    ctx?.ControllerStateKey || ctx?.controllerStateKey || "",
  ).trim();
  const controllerMatch = controllerStateKey.match(/^[^:]+::(.+)$/);
  if (controllerMatch?.[1]) add(controllerMatch[1]);

  add(ctx?.replyTarget);
  add(ctx?.ReplyTarget);
  add(ctx?.SenderId);
  add(ctx?.senderId);
  add(ctx?.current_customer_whatsapp);

  const to = String(ctx?.To || ctx?.to || "").trim();
  if (to.startsWith("octopus:")) add(to.slice("octopus:".length));

  const originatingTo = String(ctx?.OriginatingTo || "").trim();
  if (originatingTo.startsWith("octopus:")) {
    add(originatingTo.slice("octopus:".length));
  }

  // Class-11 fallback (2026-04-21): when the tool ctx has been stripped of
  // every identity field, the Octopus ingress stash is the only surviving
  // authoritative source. This stays a FALLBACK because if even one real
  // ctx id was present above, we still prefer it to keep cross-conversation
  // contamination impossible even in the pathological case where two
  // conversations' turns interleave faster than the stash TTL.
  if (aliases.length === 0) {
    const stash = getIdentityStash();
    if (stash) {
      const fromStash: string[] = [];
      const pushStash = (value: string) => {
        const trimmed = String(value || "").trim();
        if (!trimmed || seen.has(trimmed)) return;
        seen.add(trimmed);
        aliases.push(trimmed);
        fromStash.push(trimmed);
      };
      pushStash(stash.conversationId);
      pushStash(stash.controllerStateKey);
      if (stash.controllerStateKey) {
        const controllerMatch = stash.controllerStateKey.match(/^[^:]+::(.+)$/);
        if (controllerMatch?.[1]) pushStash(controllerMatch[1]);
      }
      if (stash.sessionKey) {
        pushStash(stash.sessionKey);
        const sessionMatchFromStash = stash.sessionKey.match(
          /:octopus:direct:(.+?)(?:::prompt=|$)/,
        );
        if (sessionMatchFromStash?.[1]) pushStash(sessionMatchFromStash[1]);
      }
      pushStash(stash.replyTarget);
      pushStash(stash.senderId);
      if (fromStash.length > 0) {
        try {
          // eslint-disable-next-line no-console
          console.log(
            `[responder-ops/identity-fallback] source=current_turn_identity aliases=${JSON.stringify(fromStash)} reason=stripped_tool_ctx`,
          );
        } catch {}
      }
    }
  }

  return aliases;
}

export function resolveToolTurnId(ctx: any): string {
  const value =
    ctx?.TurnId ||
    ctx?.turnId ||
    ctx?.MessageId ||
    ctx?.messageId ||
    ctx?.InboundMessageId ||
    ctx?.inboundMessageId;
  const trimmed = String(value || "").trim();
  return trimmed || String(Date.now());
}
