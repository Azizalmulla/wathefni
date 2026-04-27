// Admin complaint-query tools (read-only).
//
// Counterpart to admin-orders.ts. Where admin-orders.ts answers the
// structured-order questions ("orders last week", "customers by area",
// "who's stuck mid-booking"), this module answers the complaint
// questions ("how many coverage complaints this month", "search all
// complaints mentioning late driver", "show me this customer's
// complaint history").
//
// Both tools read from the daily JSONL files maintained by
// `../lib/complaint-store.ts`. Both gate on `assertAdminAuthorized`
// exactly like the order tools.
//
// Why these exist separate from memory_search:
//   - memory_search covers admin-curated MEMORY.md and daily ops
//     notes, which are hand-written prose.
//   - Complaints are structured records (category, timestamp, phone,
//     order_id, verbatim text) and deserve first-class structured
//     queries. A substring/category filter over a JSONL log is
//     dramatically more predictable, faster, and cheaper than an
//     embedding retrieval for the "filter-by-attribute" class of
//     admin questions, which is most of them.
//   - When the admin ever needs genuinely semantic cross-complaint
//     search ("complaints that feel like this new pattern"), an
//     embedding index can be bolted on top of the same JSONL corpus
//     without changing this tool surface.

import {
  COMPLAINT_CATEGORIES,
  readComplaintsInRange,
  redactComplaintForDisplay,
  type ComplaintCategory,
} from "../lib/complaint-store";

import type { ToolDeps } from "./deps";

export function registerAdminComplaintTools(api: any, deps: ToolDeps): void {
  const { assertAdminAuthorized, createTextResult, errorPayload } = deps;

  // =========================================================================
  // admin_list_complaints — filter by category / date / phone
  // =========================================================================
  api.registerTool((ctx: any) => ({
    name: "admin_list_complaints",
    label: "Admin List Complaints",
    description:
      "List customer complaints filtered by category, time window, and/or phone tail. Returns each complaint with its verbatim text, category, redacted phone tail, timestamp, and any linked order_id. Use this for 'how many pricing complaints this week?' / 'show me all late-delivery complaints from the last 30 days' / 'what has this customer complained about before?'. Complaint records are persisted to disk by the customer bot whenever it calls the `complains` tool.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        category: {
          type: ["string", "null"],
          enum: [...COMPLAINT_CATEGORIES, null],
          description: "Filter by complaint category. Null / omitted returns all categories.",
        },
        since_days: {
          type: ["integer", "null"],
          description:
            "Only include complaints from the last N days (default 30, hard cap 365).",
        },
        phone: {
          type: ["string", "null"],
          description:
            "Filter to complaints from a specific customer. Accepts full number or trailing digits; matches by suffix (e.g. '1234' matches '***1234').",
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
        category?: ComplaintCategory | null;
        since_days?: number | null;
        phone?: string | null;
        limit?: number | null;
      },
    ) {
      try {
        assertAdminAuthorized(ctx);
        const rawSinceDays =
          typeof params.since_days === "number" && params.since_days > 0
            ? params.since_days
            : 30;
        const sinceDays = Math.min(rawSinceDays, 365);
        const rawLimit =
          typeof params.limit === "number" && params.limit > 0 ? params.limit : 50;
        const limit = Math.min(rawLimit, 500);

        const records = await readComplaintsInRange({
          sinceDays,
          category: params.category ?? null,
          phone: params.phone ?? null,
          limit,
        });

        const rows = records.map(redactComplaintForDisplay);
        return createTextResult(
          {
            status: "ok",
            filters: {
              category: params.category ?? null,
              since_days: sinceDays,
              phone_filter_applied: Boolean(params.phone),
            },
            returned: rows.length,
            rows,
          },
          { returned: rows.length },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  // =========================================================================
  // admin_search_complaints — substring over complaint_text
  // =========================================================================
  api.registerTool((ctx: any) => ({
    name: "admin_search_complaints",
    label: "Admin Search Complaints",
    description:
      "Find complaints whose text contains a given keyword or phrase (case-insensitive substring match). Use this when the admin asks something like 'search complaints for driver name X', 'find complaints mentioning Salmiya', 'complaints about cash on delivery'. For category-shaped queries prefer `admin_list_complaints`; this tool is for free-text lookups. Arabic and English both work.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        query: {
          type: "string",
          description:
            "The keyword or phrase to search for in complaint text. Case-insensitive substring match.",
        },
        since_days: {
          type: ["integer", "null"],
          description:
            "Only search complaints from the last N days (default 90, hard cap 365).",
        },
        category: {
          type: ["string", "null"],
          enum: [...COMPLAINT_CATEGORIES, null],
          description: "Optional category filter in addition to the keyword.",
        },
        limit: {
          type: ["integer", "null"],
          description: "Max rows to return (default 50, hard cap 500).",
        },
      },
      required: ["query"],
    },
    async execute(
      _toolCallId: string,
      params: {
        query: string;
        since_days?: number | null;
        category?: ComplaintCategory | null;
        limit?: number | null;
      },
    ) {
      try {
        assertAdminAuthorized(ctx);
        const query = typeof params.query === "string" ? params.query.trim() : "";
        if (!query) {
          return createTextResult({
            status: "error",
            message: "query is required and must be non-empty",
          });
        }
        const rawSinceDays =
          typeof params.since_days === "number" && params.since_days > 0
            ? params.since_days
            : 90;
        const sinceDays = Math.min(rawSinceDays, 365);
        const rawLimit =
          typeof params.limit === "number" && params.limit > 0 ? params.limit : 50;
        const limit = Math.min(rawLimit, 500);

        const records = await readComplaintsInRange({
          sinceDays,
          category: params.category ?? null,
          keyword: query,
          limit,
        });

        const rows = records.map(redactComplaintForDisplay);
        return createTextResult(
          {
            status: "ok",
            query,
            filters: {
              category: params.category ?? null,
              since_days: sinceDays,
            },
            returned: rows.length,
            rows,
          },
          { returned: rows.length },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));
}
