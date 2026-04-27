// Complaint persistence layer.
//
// Why this exists:
//   Before this module, the `complains` tool was a pure stub — it logged
//   receipt to the customer and did nothing else. That meant the admin
//   had no way to answer any query of the form "customers who complained
//   about X", "what are the top complaint categories this week", etc.
//   Which in turn meant the entire complaint class of admin queries was
//   simply unavailable regardless of what query layer (keyword, LLM,
//   embeddings) we built on top.
//
//   This module closes that gap: it persists every complaint to disk in
//   a structured form the admin-complaints tools can read back. It
//   intentionally does not try to be a database — one JSONL file per day
//   is enough for the current volume and scales to millions of records
//   before becoming a real constraint. If/when we outgrow flat files,
//   the admin tool surface (`admin_list_complaints` etc.) stays stable
//   and only the backend moves.
//
// Storage layout:
//   $HOME/.openclaw-${OPENCLAW_PROFILE}/complaints/YYYY-MM-DD.jsonl
//   One JSON object per line. Appends are atomic-ish (single write call
//   on append-only line; no cross-line invariants to protect). Daily
//   rotation means the backup cron naturally picks them up and admin
//   queries that span days just read multiple files.
//
// PII:
//   Full phone is stored (we need it to look up a customer's other
//   activity). Tool results display `phone_tail` only. Complaint text
//   is stored verbatim — it's the customer's own words.

import fs from "node:fs/promises";
import path from "node:path";

export const COMPLAINT_CATEGORIES = [
  "late_delivery",
  "wrong_item",
  "pricing",
  "rude_driver",
  "coverage",
  "service_quality",
  "damaged_item",
  "order_not_received",
  "other",
] as const;

export type ComplaintCategory = (typeof COMPLAINT_CATEGORIES)[number];

export interface ComplaintRecord {
  complaint_id: string;
  recorded_at: string;
  phone: string | null;
  phone_tail: string;
  conversation_id: string | null;
  account_id: string | null;
  complaint_text: string;
  order_id: string | null;
  order_uid: string | null;
  category: ComplaintCategory;
  language: "ar" | "en" | "unknown";
}

export interface AppendComplaintInput {
  phone?: string | null;
  conversation_id?: string | null;
  account_id?: string | null;
  complaint_text: string;
  order_id?: string | null;
  order_uid?: string | null;
  category?: ComplaintCategory | string | null;
  language?: "ar" | "en" | null;
}

function env(): Record<string, string | undefined> {
  return ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>;
}

export function resolveComplaintsDir(): string {
  const e = env();
  const override = typeof e.RIDERS_COMPLAINTS_DIR === "string" ? e.RIDERS_COMPLAINTS_DIR.trim() : "";
  if (override) return override;
  const home = typeof e.HOME === "string" && e.HOME.trim() ? e.HOME.trim() : ".";
  const profile =
    typeof e.OPENCLAW_PROFILE === "string" && e.OPENCLAW_PROFILE.trim()
      ? e.OPENCLAW_PROFILE.trim()
      : "delivery";
  return path.join(home, `.openclaw-${profile}`, "complaints");
}

function isoDateOnly(date: Date): string {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function phoneTail(value: string | null | undefined, keep = 4): string {
  if (typeof value !== "string") return "-";
  const digits = value.replace(/[^\d]/g, "");
  if (!digits) return "-";
  return digits.length > keep ? `***${digits.slice(-keep)}` : digits;
}

function normalizeCategory(raw: string | null | undefined): ComplaintCategory {
  if (typeof raw !== "string") return "other";
  const lower = raw.trim().toLowerCase();
  if (!lower) return "other";
  return (COMPLAINT_CATEGORIES as readonly string[]).includes(lower)
    ? (lower as ComplaintCategory)
    : "other";
}

function detectLanguage(text: string): "ar" | "en" | "unknown" {
  if (typeof text !== "string" || !text) return "unknown";
  const arabic = /[\u0600-\u06FF]/.test(text);
  const latin = /[A-Za-z]/.test(text);
  if (arabic && !latin) return "ar";
  if (latin && !arabic) return "en";
  if (arabic) return "ar";
  if (latin) return "en";
  return "unknown";
}

function newComplaintId(): string {
  const rand = Math.random().toString(36).slice(2, 10);
  return `cpl_${Date.now().toString(36)}_${rand}`;
}

export async function appendComplaint(input: AppendComplaintInput): Promise<ComplaintRecord> {
  const now = new Date();
  const text = typeof input.complaint_text === "string" ? input.complaint_text.trim() : "";
  if (!text) {
    throw new Error("appendComplaint: complaint_text is required and must be non-empty");
  }
  const phoneDigits =
    typeof input.phone === "string"
      ? input.phone.replace(/[^\d+]/g, "").replace(/^\+/, "").trim()
      : "";
  const record: ComplaintRecord = {
    complaint_id: newComplaintId(),
    recorded_at: now.toISOString(),
    phone: phoneDigits || null,
    phone_tail: phoneTail(phoneDigits || null),
    conversation_id:
      typeof input.conversation_id === "string" && input.conversation_id.trim()
        ? input.conversation_id.trim()
        : null,
    account_id:
      typeof input.account_id === "string" && input.account_id.trim()
        ? input.account_id.trim()
        : null,
    complaint_text: text,
    order_id:
      typeof input.order_id === "string" && input.order_id.trim() ? input.order_id.trim() : null,
    order_uid:
      typeof input.order_uid === "string" && input.order_uid.trim() ? input.order_uid.trim() : null,
    category: normalizeCategory(input.category ?? null),
    language: input.language ?? detectLanguage(text),
  };

  const dir = resolveComplaintsDir();
  await fs.mkdir(dir, { recursive: true });
  const file = path.join(dir, `${isoDateOnly(now)}.jsonl`);
  await fs.appendFile(file, `${JSON.stringify(record)}\n`, "utf-8");
  return record;
}

export interface ReadComplaintsOptions {
  sinceDays?: number | null;
  untilDate?: Date | null;
  limit?: number | null;
  category?: ComplaintCategory | null;
  phone?: string | null;
  keyword?: string | null;
}

function normalizePhoneQuery(value: string | null | undefined): string {
  if (typeof value !== "string") return "";
  return value.replace(/[^\d]/g, "");
}

function normalizeKeyword(value: string | null | undefined): string {
  if (typeof value !== "string") return "";
  return value.trim().toLowerCase();
}

function daysToMs(days: number): number {
  return days * 24 * 60 * 60 * 1000;
}

function enumerateDateKeys(fromDate: Date, toDate: Date): string[] {
  const keys: string[] = [];
  const cursor = new Date(Date.UTC(fromDate.getUTCFullYear(), fromDate.getUTCMonth(), fromDate.getUTCDate()));
  const end = Date.UTC(toDate.getUTCFullYear(), toDate.getUTCMonth(), toDate.getUTCDate());
  while (cursor.getTime() <= end) {
    keys.push(isoDateOnly(cursor));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return keys;
}

export async function readComplaintsInRange(
  options: ReadComplaintsOptions = {},
): Promise<ComplaintRecord[]> {
  const dir = resolveComplaintsDir();
  try {
    await fs.access(dir);
  } catch {
    return [];
  }

  const now = options.untilDate ?? new Date();
  const sinceDays =
    typeof options.sinceDays === "number" && options.sinceDays > 0 ? options.sinceDays : 30;
  const fromMs = now.getTime() - daysToMs(sinceDays);
  const fromDate = new Date(fromMs);
  const dateKeys = enumerateDateKeys(fromDate, now);

  const filterCategory = options.category ?? null;
  const filterPhoneDigits = normalizePhoneQuery(options.phone);
  const filterKeyword = normalizeKeyword(options.keyword);

  const records: ComplaintRecord[] = [];
  for (const key of dateKeys) {
    const file = path.join(dir, `${key}.jsonl`);
    let raw: string;
    try {
      raw = await fs.readFile(file, "utf-8");
    } catch {
      continue;
    }
    const lines = raw.split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      let parsed: ComplaintRecord | null = null;
      try {
        parsed = JSON.parse(trimmed) as ComplaintRecord;
      } catch {
        continue;
      }
      if (!parsed || typeof parsed !== "object" || !parsed.complaint_id) continue;

      const ts = Date.parse(parsed.recorded_at || "");
      if (Number.isFinite(ts) && ts < fromMs) continue;

      if (filterCategory && parsed.category !== filterCategory) continue;
      if (filterPhoneDigits) {
        const recordDigits = normalizePhoneQuery(parsed.phone);
        if (!recordDigits.endsWith(filterPhoneDigits) && !recordDigits.includes(filterPhoneDigits)) {
          continue;
        }
      }
      if (filterKeyword) {
        const textLower = (parsed.complaint_text || "").toLowerCase();
        if (!textLower.includes(filterKeyword)) continue;
      }
      records.push(parsed);
    }
  }

  records.sort((a, b) => (b.recorded_at || "").localeCompare(a.recorded_at || ""));
  const limit =
    typeof options.limit === "number" && options.limit > 0
      ? Math.min(options.limit, 500)
      : records.length;
  return records.slice(0, limit);
}

export function redactComplaintForDisplay(record: ComplaintRecord): Omit<ComplaintRecord, "phone"> {
  const { phone: _phone, ...rest } = record;
  void _phone;
  return rest;
}
