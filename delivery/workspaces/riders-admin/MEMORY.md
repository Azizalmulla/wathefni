# Riders Admin — Long-Term Memory

This file is the curated, long-term memory for the Riders admin agent. It is
read at session start and indexed for `memory_search`.

Only put durable, distilled knowledge here:
- ops decisions with lasting consequences
- policy calibrations we have landed
- integration constraints (provider quirks, rate limits, credentials sourcing)
- naming / routing conventions we have agreed on

Raw daily notes go in `memory/YYYY-MM-DD.md` instead. Promote items from
daily notes to this file only after they prove durable (usually after a
maintenance pass).

## Business Context

- Riders is a WhatsApp-first delivery/booking service operating in Kuwait.
- Customer-facing agent id: `riders`. Admin agent id: `riders-admin`.
- Pricing source of truth: the configured Riders Google Sheet (admin-editable
  via `admin_update_area_price_in_google_sheet` /
  `admin_add_pricing_area_to_google_sheet`). Published snapshot lives at
  `workspaces/riders/data/pricing.published.json`.
- Behavior policy source of truth:
  `workspaces/riders/data/behavior-policy.published.json`, edited through
  the `admin_*_behavior_*` tools.

## Memory Policy

- Memory is infrastructure, not a product feature. Success metric is order
  completion reliability, not "good memory".
- Per-customer memory stores only the MOST RECENT successful order (not a
  full order log). `admin_get_customer_history` reflects that reality.
- Customer profiles live on disk at
  `$HOME/.openclaw-${OPENCLAW_PROFILE}/customer-profiles/${phone}.json`.
- Conversation controller state is a single JSON snapshot at
  `$HOME/.openclaw-${OPENCLAW_PROFILE}/conversation-controller-state.json`.
- Complaints are persisted as daily JSONL logs at
  `$HOME/.openclaw-${OPENCLAW_PROFILE}/complaints/YYYY-MM-DD.jsonl`, one
  record per `complains` call. Queryable via `admin_list_complaints`
  (structured filters) and `admin_search_complaints` (substring over the
  verbatim text). This is the corpus to reach for when the admin asks
  anything of the form "customers who complained about X".
- Nightly backup cron writes rotating archives; see
  `scripts/backup-customer-profiles.sh`.

## Routing & Allowlists

- Admin routing is decided by the merged admin allowlists
  (`RIDERS_PRICING_ADMIN_ALLOWLIST`, `RIDERS_BEHAVIOR_ADMIN_ALLOWLIST`,
  `AI_OCTOPUS_ADMIN_ALLOWLIST`). Individual tool execution still enforces
  its own per-capability allowlist.
- Customer messages cannot reach admin tools — route separation is at the
  agent level.

## Known Launch Blockers / Stubs

- `assign_agent` is an honest stub: returns status "noted" with
  `handoff_available: false`. Do NOT promote it to "escalated" messaging
  until the live WhatsApp number switch lands and the AI Octopus handoff
  destination is wired.
- `complains` persists complaints to the admin-readable log (since
  2026-04-24) but still returns `handoff_available: false` — no human
  is paged. Category tagging is done at call time by the customer bot
  using a fixed enum; accuracy is "good enough for admin filtering",
  not audit-grade.
