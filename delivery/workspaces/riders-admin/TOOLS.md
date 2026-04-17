# TOOLS.md - Riders Operations Controller

## Identity and Runtime

- OpenClaw profile: `delivery`
- Default customer agent ID: `riders`
- Admin agent ID: `riders-admin`
- Admin workspace root: `/Users/azizalmulla/Desktop/claw/delivery/workspaces/riders-admin`
- Delivery customer workspace root: `/Users/azizalmulla/Desktop/claw/delivery/workspaces/riders`

## Admin Routing

- The native `octopus-channel` plugin routes allowlisted admin senders to the `riders-admin` agent.
- The admin sender allowlist is resolved from the merged environment values:
  - `AI_OCTOPUS_ADMIN_ALLOWLIST`
  - `RIDERS_PRICING_ADMIN_ALLOWLIST`
  - `RIDERS_BEHAVIOR_ADMIN_ALLOWLIST`
- Admin sender variants differ by deployment environment. Do not hardcode or rely on phone numbers in this file.
- Routing to `riders-admin` does not automatically mean full pricing access. Tool-level authorization still applies after routing.

## Admin Permission Model

Shell access is not available. Admin permissions are split at tool level:

- Generic admin tools require an authorized admin sender.
- Behavior-policy tools allow behavior-admin and pricing-admin senders.
- Pricing tools require pricing-admin authorization.

### Workspace File Management

- `admin_list_workspace_files` — list files in `riders` or `riders-admin` workspace
- `admin_read_workspace_file` — read any workspace file (SKILL.md, IDENTITY.md, TOOLS.md, MEMORY.md, data files, etc.)
- `admin_write_workspace_file` — create or update any workspace file
- Do not use workspace file edits as the first choice for normal live customer-behavior tweaks.
- Prefer workspace file edits only when the admin explicitly asks to edit a file or when a confirmed base prompt conflict must be fixed permanently.

Workspaces available: `riders` (customer agent), `riders-admin` (this agent).

### Pricing

- `admin_pricing_source_status`
- `admin_validate_pricing_resolver_overlay`
- `admin_refresh_pricing_cache`
- `admin_add_pricing_area_to_google_sheet`
- `admin_update_area_price_in_google_sheet`
- `admin_fetch_google_sheet_rows`
- `admin_fetch_google_sheet_metadata`
- `admin_update_google_sheet_values`
- `admin_batch_update_google_sheet`
- `admin_clear_google_sheet_values`
- `admin_append_google_sheet_rows`
- `admin_delete_google_sheet_rows`
- `admin_publish_pricing_sheet_rows`
- `admin_publish_pricing_snapshot`
- `admin_update_area_price`

### Behavior Policy & Live Instructions

- `admin_behavior_policy_status`
- `admin_refresh_behavior_policy_cache`
- `admin_view_behavior_policy`
- `admin_publish_behavior_policy`
- `admin_set_behavior_live_instructions`
- `admin_add_behavior_reply_correction`
- `admin_add_behavior_flow_rule`
- `admin_add_behavior_phrase_guard`
- `admin_disable_behavior_rule`
- `admin_delete_behavior_rule`
- For direct admin rule changes affecting live customer replies, prefer `admin_set_behavior_live_instructions` first unless the change clearly fits a structured correction, flow rule, or phrase guard.
- After a successful live behavior change, report the exact published version returned by the tool.

### Delivery Support

- `get_price`
- `track_order`
- `create_simple_order`
- `create_order` — deprecated
- `pay_order`
- `assign_agent`

## Runtime Notes

- Preferred pricing runtime is `published_preferred` with:
  - `pricing.published.json` as the served snapshot
  - `pricing.resolver.overlay.json` as curated alias / ambiguity / grouped geo metadata
- Before any live pricing change, first run:
  - `admin_pricing_source_status`
  - `admin_validate_pricing_resolver_overlay`
- Preferred publish flow:
  - update source data
  - dry-run publish
  - validate overlay
  - publish
  - re-check pricing status
- Google Sheets runtime access currently uses `gog`, but this should not be treated as the final production auth model.
- Production go-live should use dedicated production credentials for sheet publishing, or sheet-based publish actions should remain operationally quarantined until that exists.
- Default Riders pricing spreadsheet ID: `1I6QjKlfx2gA-dQ2q1tXlmj_wV0TtPgri06ZDEjjXisU`
- Default Riders pricing tab: `export-38-areas`
- Default pricing sheet header row: `1`
- If the admin says `pricing sheet` without more detail, assume this spreadsheet and tab.
- The admin route stays separate from the customer route to avoid mixed session behavior.
- If the admin asks for an exact schema, enum, API path, or implementation behavior, verify it from the current implementation before answering. Do not rely on stale notes or memory.
