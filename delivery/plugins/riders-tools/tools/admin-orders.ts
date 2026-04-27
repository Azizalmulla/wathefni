// Admin order & conversation query tools (read-only).
//
// Fills the "we have pricing admin + workspace admin but no way to actually
// query order history / conversation state" gap. All tools here:
//   - Are READ-ONLY (no dry_run flag needed; nothing mutates)
//   - Gate on `assertAdminAuthorized` (same allowlist as workspace admin)
//   - Read directly from the runtime state directory that octopus-channel
//     writes to: `$HOME/.openclaw-${OPENCLAW_PROFILE}/{customer-profiles/,
//     conversation-controller-state.json}`
//
// Data model reminder — we do NOT have a per-order table. The product stores
// ONE "last_successful_order" per customer phone, in:
//   `$HOME/.openclaw-${OPENCLAW_PROFILE}/customer-profiles/${phone}.json`
// So "list recent orders" is really "list customer profiles whose last
// successful order was in the last N days, sorted by updated_at desc".
// If we later add a persistent per-order log these tools should read from
// that instead; the tool surface (admin_list_recent_orders etc.) stays
// stable from the admin's POV.

import fs from "node:fs/promises";
import path from "node:path";

import type { ToolDeps } from "./deps";

function resolveMemoryDir(): string {
  const env = (globalThis as any).process?.env ?? {};
  const home = typeof env.HOME === "string" && env.HOME.trim() ? env.HOME.trim() : ".";
  const profile =
    typeof env.OPENCLAW_PROFILE === "string" && env.OPENCLAW_PROFILE.trim()
      ? env.OPENCLAW_PROFILE.trim()
      : "delivery";
  const override =
    typeof env.RIDERS_CUSTOMER_MEMORY_DIR === "string" && env.RIDERS_CUSTOMER_MEMORY_DIR.trim()
      ? env.RIDERS_CUSTOMER_MEMORY_DIR.trim()
      : null;
  return override ?? path.join(home, `.openclaw-${profile}`, "customer-profiles");
}

function resolveConversationControllerStatePath(): string {
  const env = (globalThis as any).process?.env ?? {};
  const home = typeof env.HOME === "string" && env.HOME.trim() ? env.HOME.trim() : ".";
  const profile =
    typeof env.OPENCLAW_PROFILE === "string" && env.OPENCLAW_PROFILE.trim()
      ? env.OPENCLAW_PROFILE.trim()
      : "delivery";
  return path.join(home, `.openclaw-${profile}`, "conversation-controller-state.json");
}

function safeParseJson<T>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function normalizePhoneForLookup(value: string | null | undefined): string | null {
  if (typeof value !== "string") return null;
  const digits = value.replace(/[^\d+]/g, "").replace(/^\+/, "");
  if (!/^\d{7,20}$/.test(digits)) return null;
  return digits;
}

function phoneTail(value: string | null | undefined, keep = 4): string {
  if (typeof value !== "string") return "-";
  const digits = value.replace(/[^\d]/g, "");
  if (!digits) return "-";
  return digits.length > keep ? `***${digits.slice(-keep)}` : digits;
}

type SavedAddress = {
  area?: string | null;
  house?: string | null;
  avenue?: string | null;
  notes?: string | null;
};

type SavedCustomerOrder = {
  order_id?: string | number | null;
  order_uid?: string | null;
  selected_delivery_type?: string | null;
  pickup?: SavedAddress;
  delivery?: SavedAddress;
  sender?: { name?: string | null; phone?: string | null };
  recipient?: { name?: string | null; phone?: string | null };
  saved_from_turn_at?: string | null;
};

type CustomerProfile = {
  version?: number;
  customer_whatsapp?: string | null;
  updated_at?: string | null;
  last_successful_order?: SavedCustomerOrder | null;
};

function summarizeOrder(order: SavedCustomerOrder | null | undefined) {
  if (!order) return null;
  return {
    order_uid: order.order_uid ?? null,
    order_id: order.order_id ?? null,
    delivery_type: order.selected_delivery_type ?? null,
    pickup_area: order.pickup?.area ?? null,
    delivery_area: order.delivery?.area ?? null,
    saved_at: order.saved_from_turn_at ?? null,
  };
}

function withinSinceDays(iso: string | null | undefined, sinceDays: number | null): boolean {
  if (sinceDays == null) return true;
  if (!iso) return false;
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return false;
  const cutoff = Date.now() - sinceDays * 24 * 60 * 60 * 1000;
  return t >= cutoff;
}

async function readAllProfiles(memoryDir: string): Promise<
  Array<{ file: string; phone_tail: string; profile: CustomerProfile }>
> {
  let entries: Array<{ name: string; isFile: () => boolean }> = [];
  try {
    entries = await fs.readdir(memoryDir);
  } catch (err) {
    const code = (err as { code?: string } | null)?.code ?? "";
    if (code === "ENOENT") return [];
    throw err;
  }
  const out: Array<{ file: string; phone_tail: string; profile: CustomerProfile }> = [];
  for (const entry of entries) {
    const name = entry.name;
    if (!name.endsWith(".json")) continue;
    const full = path.join(memoryDir, name);
    let raw: string;
    try {
      raw = await fs.readFile(full, "utf-8");
    } catch {
      continue;
    }
    const parsed = safeParseJson<CustomerProfile>(raw);
    if (!parsed || typeof parsed !== "object") continue;
    const phone = parsed.customer_whatsapp || name.replace(/\.json$/, "");
    out.push({ file: name, phone_tail: phoneTail(phone), profile: parsed });
  }
  return out;
}

export function registerAdminOrderTools(api: any, deps: ToolDeps): void {
  const { assertAdminAuthorized, createTextResult, errorPayload } = deps;

  // =========================================================================
  // admin_list_recent_orders
  // =========================================================================
  api.registerTool((ctx: any) => ({
    name: "admin_list_recent_orders",
    label: "Admin List Recent Orders",
    description:
      "List customers whose most recent successful order was saved in the last N days. Results are sorted most-recent-first. Each row shows a redacted phone tail, the order's pickup/delivery area, delivery type, and the saved timestamp. Use this to answer 'how many orders today / this week?', 'which areas booked lately?', or to spot-check recent activity.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        since_days: {
          type: ["integer", "null"],
          description:
            "Only include orders saved within the last N days. Omit or null for all time.",
        },
        limit: {
          type: ["integer", "null"],
          description: "Max rows to return (default 50, hard cap 500).",
        },
      },
    },
    async execute(
      _toolCallId: string,
      params: { since_days?: number | null; limit?: number | null },
    ) {
      try {
        assertAdminAuthorized(ctx);
        const sinceDays =
          typeof params.since_days === "number" && params.since_days > 0 ? params.since_days : null;
        const rawLimit = typeof params.limit === "number" && params.limit > 0 ? params.limit : 50;
        const limit = Math.min(rawLimit, 500);

        const memoryDir = resolveMemoryDir();
        const profiles = await readAllProfiles(memoryDir);

        const rows = profiles
          .filter((p) => p.profile.last_successful_order)
          .map((p) => ({
            phone_tail: p.phone_tail,
            updated_at: p.profile.updated_at ?? null,
            order: summarizeOrder(p.profile.last_successful_order),
          }))
          .filter((row) =>
            withinSinceDays(row.order?.saved_at ?? row.updated_at ?? null, sinceDays),
          )
          .sort((a, b) => {
            const ta = Date.parse(a.order?.saved_at ?? a.updated_at ?? "") || 0;
            const tb = Date.parse(b.order?.saved_at ?? b.updated_at ?? "") || 0;
            return tb - ta;
          })
          .slice(0, limit);

        return createTextResult(
          {
            status: "ok",
            since_days: sinceDays,
            limit,
            total_customers_scanned: profiles.length,
            returned: rows.length,
            rows,
          },
          { rows },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  // =========================================================================
  // admin_get_customer_history
  // =========================================================================
  api.registerTool((ctx: any) => ({
    name: "admin_get_customer_history",
    label: "Admin Get Customer History",
    description:
      "Look up a specific customer's saved profile by WhatsApp phone number. Returns their last successful order (pickup/delivery areas, names, phones, addresses, order_uid, saved_at) and the profile's updated_at timestamp. NOTE: the system currently stores only the MOST RECENT successful order per customer — we do not keep a full history log yet. If no profile exists or they never completed an order, returns status=not_found.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        phone: {
          type: "string",
          description:
            "Customer WhatsApp phone number. Accepts with or without leading '+'. Country code must be included (e.g. '96512345678' or '+96512345678').",
        },
      },
      required: ["phone"],
    },
    async execute(_toolCallId: string, params: { phone: string }) {
      try {
        assertAdminAuthorized(ctx);
        const normalized = normalizePhoneForLookup(params.phone);
        if (!normalized) {
          throw new Error(
            "Invalid phone format. Expected a digit-only phone (with optional leading '+'), e.g. '96512345678'.",
          );
        }
        const memoryDir = resolveMemoryDir();
        const profilePath = path.join(memoryDir, `${normalized}.json`);
        let raw: string;
        try {
          raw = await fs.readFile(profilePath, "utf-8");
        } catch (err) {
          const code = (err as { code?: string } | null)?.code ?? "";
          if (code === "ENOENT") {
            return createTextResult({
              status: "not_found",
              message: "No saved profile for this customer yet.",
              phone_tail: phoneTail(normalized),
            });
          }
          throw err;
        }
        const parsed = safeParseJson<CustomerProfile>(raw);
        if (!parsed) {
          throw new Error("Customer profile file exists but could not be parsed.");
        }
        return createTextResult(
          {
            status: "ok",
            phone_tail: phoneTail(normalized),
            updated_at: parsed.updated_at ?? null,
            last_successful_order: parsed.last_successful_order ?? null,
            has_order: Boolean(parsed.last_successful_order),
          },
          {
            has_order: Boolean(parsed.last_successful_order),
          },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  // =========================================================================
  // admin_order_stats
  // =========================================================================
  api.registerTool((ctx: any) => ({
    name: "admin_order_stats",
    label: "Admin Order Stats",
    description:
      "Aggregate counts across customer profiles: total customers, how many have a saved successful order, breakdown by pickup area / delivery area / delivery type, within an optional since_days window. Use this for 'which areas are we covering most?', 'what's the mix of small-car vs motorbike?', or a quick pulse-check. All counts are on 'most recent order per customer' (not a full order log).",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        since_days: {
          type: ["integer", "null"],
          description:
            "Only include orders saved within the last N days. Omit or null for all time.",
        },
        top_n: {
          type: ["integer", "null"],
          description: "How many top entries to return per breakdown (default 10, max 50).",
        },
      },
    },
    async execute(
      _toolCallId: string,
      params: { since_days?: number | null; top_n?: number | null },
    ) {
      try {
        assertAdminAuthorized(ctx);
        const sinceDays =
          typeof params.since_days === "number" && params.since_days > 0 ? params.since_days : null;
        const topN = Math.min(
          typeof params.top_n === "number" && params.top_n > 0 ? params.top_n : 10,
          50,
        );

        const memoryDir = resolveMemoryDir();
        const profiles = await readAllProfiles(memoryDir);

        let totalCustomers = 0;
        let customersWithOrder = 0;
        const pickupCounts = new Map<string, number>();
        const deliveryCounts = new Map<string, number>();
        const typeCounts = new Map<string, number>();

        for (const { profile } of profiles) {
          totalCustomers += 1;
          const order = profile.last_successful_order;
          if (!order) continue;
          const when = order.saved_from_turn_at ?? profile.updated_at ?? null;
          if (!withinSinceDays(when, sinceDays)) continue;
          customersWithOrder += 1;
          const pickup = (order.pickup?.area ?? "").trim() || "(unknown)";
          const delivery = (order.delivery?.area ?? "").trim() || "(unknown)";
          const deliveryType = (order.selected_delivery_type ?? "").trim() || "(unknown)";
          pickupCounts.set(pickup, (pickupCounts.get(pickup) ?? 0) + 1);
          deliveryCounts.set(delivery, (deliveryCounts.get(delivery) ?? 0) + 1);
          typeCounts.set(deliveryType, (typeCounts.get(deliveryType) ?? 0) + 1);
        }

        const topEntries = (m: Map<string, number>) =>
          [...m.entries()]
            .sort((a, b) => b[1] - a[1])
            .slice(0, topN)
            .map(([key, count]) => ({ key, count }));

        return createTextResult(
          {
            status: "ok",
            since_days: sinceDays,
            total_customers_scanned: totalCustomers,
            customers_with_order_in_window: customersWithOrder,
            by_pickup_area: topEntries(pickupCounts),
            by_delivery_area: topEntries(deliveryCounts),
            by_delivery_type: topEntries(typeCounts),
          },
          { customers_with_order_in_window: customersWithOrder },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  // =========================================================================
  // admin_list_stuck_conversations
  // =========================================================================
  api.registerTool((ctx: any) => ({
    name: "admin_list_stuck_conversations",
    label: "Admin List Stuck Conversations",
    description:
      "List active conversations that have NOT been submitted or closed and have been idle longer than `min_idle_minutes`. Use this to catch customers who dropped mid-booking — e.g. stuck at 'quoted' without confirming, at 'collecting_info' missing a field, or whose draft shows pending pin role. Returns redacted phone tails, conversation stage, booking step, what the draft is missing, and minutes since last activity. Excludes conversations already in stage=order_submitted or stage=idle.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        min_idle_minutes: {
          type: ["integer", "null"],
          description:
            "Only include conversations idle at least this many minutes (default 10).",
        },
        max_age_hours: {
          type: ["integer", "null"],
          description:
            "Drop conversations older than this many hours (default 24, hard cap 168 = 7 days).",
        },
        limit: {
          type: ["integer", "null"],
          description: "Max rows to return (default 50, hard cap 500).",
        },
      },
    },
    async execute(
      _toolCallId: string,
      params: {
        min_idle_minutes?: number | null;
        max_age_hours?: number | null;
        limit?: number | null;
      },
    ) {
      try {
        assertAdminAuthorized(ctx);
        const minIdleMinutes =
          typeof params.min_idle_minutes === "number" && params.min_idle_minutes >= 0
            ? params.min_idle_minutes
            : 10;
        const rawMaxAge =
          typeof params.max_age_hours === "number" && params.max_age_hours > 0
            ? params.max_age_hours
            : 24;
        const maxAgeHours = Math.min(rawMaxAge, 168);
        const rawLimit = typeof params.limit === "number" && params.limit > 0 ? params.limit : 50;
        const limit = Math.min(rawLimit, 500);

        const statePath = resolveConversationControllerStatePath();
        let raw: string;
        try {
          raw = await fs.readFile(statePath, "utf-8");
        } catch (err) {
          const code = (err as { code?: string } | null)?.code ?? "";
          if (code === "ENOENT") {
            return createTextResult({
              status: "ok",
              note: "No conversation-controller-state.json yet (fresh system or no active conversations).",
              rows: [],
            });
          }
          throw err;
        }
        const parsed = safeParseJson<Record<string, any>>(raw);
        if (!parsed || typeof parsed !== "object") {
          return createTextResult({
            status: "ok",
            note: "conversation-controller-state.json is empty or unparseable.",
            rows: [],
          });
        }

        const now = Date.now();
        const minIdleMs = minIdleMinutes * 60_000;
        const maxAgeMs = maxAgeHours * 60 * 60_000;

        const rows: Array<{
          phone_tail: string;
          conversation_id: string;
          stage: string | null;
          booking_step: string | null;
          idle_minutes: number;
          requested_slot: string | null;
          pickup_area: string | null;
          delivery_area: string | null;
          quoted_price: number | null;
          has_pending_pin: boolean;
        }> = [];

        for (const [conversationId, entry] of Object.entries(parsed)) {
          if (!entry || typeof entry !== "object") continue;
          const lastActivity =
            typeof (entry as any).lastActivityTs === "number"
              ? (entry as any).lastActivityTs
              : 0;
          if (!lastActivity) continue;
          const idleMs = now - lastActivity;
          if (idleMs < minIdleMs) continue;
          if (idleMs > maxAgeMs) continue;
          const stage = (entry as any).stage ?? null;
          if (stage === "order_submitted" || stage === "idle") continue;

          const bookingStep = (entry as any).bookingStep ?? null;
          const draft = (entry as any).bookingDraft ?? null;
          const requestedSlot = (entry as any).dialogState?.requestedSlot?.name ?? null;
          const replyTarget = (entry as any).replyTarget ?? null;
          const pendingLocation = draft?.pendingLocation ?? null;

          rows.push({
            phone_tail: phoneTail(replyTarget),
            conversation_id: conversationId,
            stage,
            booking_step: bookingStep,
            idle_minutes: Math.round(idleMs / 60_000),
            requested_slot: requestedSlot,
            pickup_area:
              (entry as any).quotePickupAreaNameEn ??
              (entry as any).pendingPickupAreaNameEn ??
              null,
            delivery_area:
              (entry as any).quoteDropoffAreaNameEn ??
              (entry as any).pendingDropoffAreaNameEn ??
              null,
            quoted_price:
              typeof (entry as any).quotedPrice === "number" ? (entry as any).quotedPrice : null,
            has_pending_pin: Boolean(pendingLocation),
          });
        }

        rows.sort((a, b) => b.idle_minutes - a.idle_minutes);
        const trimmed = rows.slice(0, limit);

        return createTextResult(
          {
            status: "ok",
            min_idle_minutes: minIdleMinutes,
            max_age_hours: maxAgeHours,
            total_active_matched: rows.length,
            returned: trimmed.length,
            rows: trimmed,
          },
          { returned: trimmed.length },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));
}
