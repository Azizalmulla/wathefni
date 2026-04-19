// ---------------------------------------------------------------------------
// Wave 2a extraction: pure webhook + WhatsApp payload helpers.
// Includes the deterministic request/response utilities, payload field
// extractors (conversation id, reply target, message text, media messages),
// and ingress-id / hashing primitives. These functions are shape-only — no
// module-scope state is touched and no networking is performed. The
// stateful ingress-ledger mutators remain in `index.ts`.
// ---------------------------------------------------------------------------

import { createHash } from "node:crypto";
import type {
  OctopusInboundAudioMessage,
  OctopusInboundImageMessage,
  OctopusInboundLocationMessage,
  IngressLedgerStatus,
} from "./types";
import { asTrimmedString, normalizePhone, looksLikePhone, splitMimeType } from "./normalize";

export async function readRequestBody(
  req: any,
  nodeBuffer: any,
): Promise<{ raw: string; parsed: any }> {
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

export function writeJson(
  res: any,
  statusCode: number,
  payload: Record<string, unknown>,
): void {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}

export function hashIngressPayload(raw: string): string | null {
  const text = String(raw || "");
  if (!text) {
    return null;
  }
  return createHash("sha256").update(text).digest("hex").slice(0, 16);
}

export function extractWebhookRequestId(req: any): string | null {
  const direct = asTrimmedString(req?.headers?.["x-request-id"]);
  if (direct) {
    return direct;
  }
  return asTrimmedString(req?.headers?.["request-id"]);
}

export function resolveRemoteAddress(req: any): string | null {
  return asTrimmedString(
    req?.headers?.["x-forwarded-for"] ||
      req?.socket?.remoteAddress ||
      req?.connection?.remoteAddress,
  );
}

export function createIngressId(params: {
  accountId: string;
  webhookPath: string;
  method: string;
  requestId?: string | null;
  conversationId?: string | null;
  messageId?: string | null;
  rawHash?: string | null;
  entropy?: string | null;
}): string {
  return createHash("sha256")
    .update(
      [
        params.accountId,
        params.webhookPath,
        params.method,
        params.requestId || "",
        params.conversationId || "",
        params.messageId || "",
        params.rawHash || "",
        params.entropy || "",
      ].join("|"),
    )
    .digest("hex")
    .slice(0, 24);
}

export function formatWebhookLogValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "na";
  }
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  if (typeof value === "string") {
    return /\s/.test(value) ? JSON.stringify(value) : value;
  }
  return JSON.stringify(value);
}

export function logWebhookEvent(
  logger: Pick<Console, "info" | "warn" | "error">,
  level: "info" | "warn" | "error",
  event: string,
  fields: Record<string, unknown>,
): void {
  const suffix = Object.entries(fields)
    .filter(([, value]) => value !== undefined)
    .map(([key, value]) => `${key}=${formatWebhookLogValue(value)}`)
    .join(" ");
  logger[level]?.(`[octopus] ${event}${suffix ? ` ${suffix}` : ""}`);
}

export function isTerminalIngressStatus(status: IngressLedgerStatus): boolean {
  return [
    "ready_check",
    "method_rejected",
    "account_disabled",
    "auth_failed",
    "parse_failed",
    "validation_probe",
    "missing_conversation_id",
    "processed",
    "replied",
    "ignored_non_text",
    "failed",
  ].includes(status);
}

export function extractConversationId(payload: any): string | number | null {
  // Preferred: AI Octopus legacy payloads include an explicit conversation_id
  // (numeric, stable per customer). Keep these as the primary source.
  const legacyCandidates = [
    payload?.conversation_id,
    payload?.conversationId,
    payload?.conversation?.id,
    payload?.data?.conversation_id,
    payload?.data?.conversationId,
  ];
  for (const candidate of legacyCandidates) {
    if (candidate !== undefined && candidate !== null && candidate !== "") {
      return candidate;
    }
  }

  // Fallback: raw Meta WhatsApp Cloud API format (AI Octopus started
  // forwarding this shape in April 2026). The customer's wa_id is the
  // stable per-customer identifier — it is what AI Octopus's own legacy
  // `conversation_id` used to be derived from. Using `wa_id` keeps
  // conversation state keyed consistently across old and new payloads.
  const entries = Array.isArray(payload?.entry) ? payload.entry : [];
  for (const entry of entries) {
    const changes = Array.isArray(entry?.changes) ? entry.changes : [];
    for (const change of changes) {
      const value = change?.value;
      const contactWaId = Array.isArray(value?.contacts) && value.contacts[0]?.wa_id;
      if (contactWaId) return String(contactWaId);
      const messageFrom =
        Array.isArray(value?.messages) && value.messages[0]?.from;
      if (messageFrom) return String(messageFrom);
    }
  }

  // Last resort: top-level `from` or `wa_id` in flattened payloads.
  const flatCandidates = [payload?.wa_id, payload?.from, payload?.sender];
  for (const candidate of flatCandidates) {
    if (candidate !== undefined && candidate !== null && candidate !== "") {
      return String(candidate);
    }
  }

  return null;
}

export function extractWhatsAppMessages(payload: any): any[] {
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

export function extractMessageText(payload: any): string | null {
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

export function extractWhatsAppMessageId(payload: any): string | null {
  const directCandidates = [
    payload?.message_id,
    payload?.messageId,
    payload?.messages?.[0]?.id,
  ];
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

export function extractReplyTarget(payload: any): string | null {
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

export function extractAudioMessage(payload: any): OctopusInboundAudioMessage | null {
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

export function extractImageMessage(payload: any): OctopusInboundImageMessage | null {
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

export function extractLocationMessage(payload: any): OctopusInboundLocationMessage | null {
  for (const message of extractWhatsAppMessages(payload)) {
    if (message?.type !== "location") continue;
    const loc = message?.location;
    const lat = typeof loc?.latitude === "number" ? loc.latitude : parseFloat(loc?.latitude);
    const lng = typeof loc?.longitude === "number" ? loc.longitude : parseFloat(loc?.longitude);
    if (isNaN(lat) || isNaN(lng)) continue;
    return {
      latitude: lat,
      longitude: lng,
      name: asTrimmedString(loc?.name) || null,
      address: asTrimmedString(loc?.address) || null,
    };
  }
  const directLoc = payload?.location;
  if (directLoc) {
    const lat =
      typeof directLoc?.latitude === "number" ? directLoc.latitude : parseFloat(directLoc?.latitude);
    const lng =
      typeof directLoc?.longitude === "number"
        ? directLoc.longitude
        : parseFloat(directLoc?.longitude);
    if (!isNaN(lat) && !isNaN(lng)) {
      return {
        latitude: lat,
        longitude: lng,
        name: asTrimmedString(directLoc?.name) || null,
        address: asTrimmedString(directLoc?.address) || null,
      };
    }
  }
  return null;
}

export function getAudioFileExtension(audioMessage: OctopusInboundAudioMessage): string {
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
      "audio/m4a": "m4a",
      "audio/mp3": "mp3",
      "audio/mp4": "m4a",
      "audio/mpeg": "mp3",
      "audio/mpga": "mp3",
      "audio/ogg": "ogg",
      "audio/opus": "opus",
      "audio/wav": "wav",
      "audio/webm": "webm",
      "audio/x-m4a": "m4a",
    }[audioMessage.mimeType || ""] || "ogg"
  );
}

export function getImageFileExtension(imageMessage: OctopusInboundImageMessage): string {
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
      "image/bmp": "bmp",
      "image/gif": "gif",
      "image/heic": "heic",
      "image/heif": "heif",
      "image/jpeg": "jpg",
      "image/jpg": "jpg",
      "image/png": "png",
      "image/svg+xml": "svg",
      "image/tiff": "tiff",
      "image/vnd.microsoft.icon": "ico",
      "image/webp": "webp",
      "image/x-icon": "ico",
    }[imageMessage.mimeType || ""] || "jpg"
  );
}
