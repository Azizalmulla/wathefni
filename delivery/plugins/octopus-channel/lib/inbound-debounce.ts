export type InboundDebounceMessageLike = {
  messageText: string | null;
  audioMessage: unknown | null;
  imageMessage: unknown | null;
  locationMessage: unknown | null;
};

export type InboundDebounceConfig = {
  defaultTextMs: number;
  mediaMs: number;
  explicitActionMs: number;
  clearRouteMs: number;
  shortFragmentMs: number;
  maxTextMs: number;
};

export type InboundDebounceDecision = {
  delayMs: number;
  reason:
    | "media"
    | "explicit_action"
    | "clear_full_route"
    | "short_fragment"
    | "normal_text"
    | "max_wait_cap";
  uncappedDelayMs: number;
};

const EXPLICIT_ACTION_RE =
  /^(?:yes|y|yeah|yep|confirm|confirmed|ok|okay|go ahead|continue|book|book it|cancel|stop|no|n|pickup|pick ?up|delivery|drop ?off|standard|standard sedan|express|fast|van|helper|1|2|3|4|5|اي|إي|نعم|تمام|اوكي|أوكي|اكد|أكد|تأكيد|كمل|اكمل|استلام|الاستلام|توصيل|التوصيل|الغاء|إلغاء|ألغي|الغي|لا)$/i;

const ROUTE_CONNECTOR_RE =
  /\b(?:from|to|pickup|dropoff|drop-off)\b|(?:\s|^)(?:من|الى|إلى)(?:\s|$)|→|->/i;

function clampNonNegative(value: number): number {
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
}

function normalizeText(value: string | null | undefined): string {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function hasInboundMedia(msg: InboundDebounceMessageLike): boolean {
  return Boolean(msg.audioMessage || msg.imageMessage || msg.locationMessage);
}

function isExplicitAction(text: string): boolean {
  return EXPLICIT_ACTION_RE.test(normalizeText(text));
}

function looksLikeClearFullRoute(text: string): boolean {
  const normalized = normalizeText(text);
  if (!normalized || !ROUTE_CONNECTOR_RE.test(normalized)) return false;
  const words = normalized.split(/\s+/).filter(Boolean);
  return words.length >= 3;
}

function isShortFragment(text: string): boolean {
  const normalized = normalizeText(text);
  if (!normalized) return false;
  const words = normalized.split(/\s+/).filter(Boolean);
  return normalized.length <= 14 || words.length <= 2;
}

export function resolveAdaptiveInboundDebounce(
  messages: InboundDebounceMessageLike[],
  config: InboundDebounceConfig,
  elapsedMs = 0,
): InboundDebounceDecision {
  const safeElapsed = clampNonNegative(elapsedMs);
  const last = messages[messages.length - 1] || null;
  const latestText = normalizeText(last?.messageText);

  let reason: InboundDebounceDecision["reason"] = "normal_text";
  let delayMs = clampNonNegative(config.defaultTextMs);

  if (messages.some((msg) => hasInboundMedia(msg))) {
    reason = "media";
    delayMs = clampNonNegative(config.mediaMs);
    return {
      delayMs,
      reason,
      uncappedDelayMs: delayMs,
    };
  }

  if (latestText && isExplicitAction(latestText)) {
    reason = "explicit_action";
    delayMs = clampNonNegative(config.explicitActionMs);
  } else if (latestText && looksLikeClearFullRoute(latestText)) {
    reason = "clear_full_route";
    delayMs = clampNonNegative(config.clearRouteMs);
  } else if (latestText && isShortFragment(latestText)) {
    reason = "short_fragment";
    delayMs = clampNonNegative(config.shortFragmentMs);
  }

  const uncappedDelayMs = delayMs;
  const maxTextMs = clampNonNegative(config.maxTextMs);
  if (maxTextMs > 0) {
    const remaining = Math.max(0, maxTextMs - safeElapsed);
    if (delayMs > remaining) {
      delayMs = remaining;
      reason = "max_wait_cap";
    }
  }

  return {
    delayMs,
    reason,
    uncappedDelayMs,
  };
}
