# Riders Delivery Test Checklist

## Automated Live Smoke Coverage

- Runner entrypoint: `zsh /Users/azizalmulla/Desktop/claw/delivery/scripts/smoke-test-live-riders-flow.sh`
- Default release-gate scenario: `all`
- The live runner is destructive by design and may create a real order.
- Required env: `RIDERS_LIVE_SMOKE_REPLY_TARGET` should point to a dedicated test WhatsApp number before running the suite.
- The runner drives the live Octopus webhook over SSH on the VPS, then verifies the resulting `riders` session transcript.
- Current automated scenario coverage:
  - Arabic greeting returns concise Arabic with no emojis
  - English greeting returns concise English
  - Passenger transport requests are rejected before pricing or booking starts
  - Route pricing returns a structured quote
  - Booking progresses one step at a time
  - Final address collection produces a summary before order creation
  - Only a post-summary confirmation creates the order
  - A later greeting does not replay the order-success message
  - No mid-booking `assign_agent`
  - No mid-booking `get_price`

## Local Pricing RC Suite

- Preferred runner: `npm test --prefix /Users/azizalmulla/Desktop/claw/delivery/plugins/riders-tools`
- Equivalent direct command: `node /Users/azizalmulla/Desktop/claw/delivery/scripts/run-pricing-rc-suite.mjs`
- The RC suite is the required local gate before any live deploy or destructive smoke.

## Separation Checks

- Confirm recruiter instance still uses profile/state under `~/.openclaw`
- Confirm delivery instance uses profile/state under `~/.openclaw-delivery`
- Confirm delivery gateway port is `18790`
- Confirm no recruiter sessions appear in delivery profile
- Confirm no recruiter workspace paths are used by the delivery config

## Prompt / Behavior Checks

- Arabic greeting returns Kuwaiti white dialect
- English greeting returns concise English
- No emojis in any reply
- No internal narration appears in customer-facing replies
- Replies stay short and professional

## Pricing Checks

- Price request without pickup asks for pickup
- Price request without dropoff asks for dropoff
- Suspended area returns the suspension message
- Ambiguous `الخيران` asks for clarification
- Ambiguous `الوفرة` asks for clarification
- Ambiguous `سعد العبدالله` asks for clarification
- Ambiguous `صباح الأحمد` asks for clarification
- Once both areas are clear, assistant uses `get_price`
- Default reply quotes only `سياره عاديه + توصيل عادي`
- Other pricing categories are only shown when explicitly requested

## Pricing Admin Checks

- Non-allowlisted sender cannot use pricing admin actions
- Allowlisted admin can check `admin_pricing_source_status`
- Allowlisted admin can run `admin_validate_pricing_resolver_overlay`
- Active source reports `published_snapshot` when the published file exists and source mode is `published_preferred`
- `admin_pricing_source_status` reports `pricing_resolver_overlay.state = active` on a healthy release-candidate config
- Missing or invalid overlay files are surfaced explicitly in pricing status instead of failing silently
- Overlay validation succeeds on a valid overlay and fails on broken area/group references
- Allowlisted admin can refresh pricing cache with `admin_refresh_pricing_cache`
- Existing Google Sheet can be accessed through the configured `gog` account during development
- `admin_fetch_google_sheet_rows` succeeds through `gog` and returns raw sheet values
- `admin_fetch_google_sheet_metadata` returns the active headers and row counts through `gog`
- `admin_update_google_sheet_values`, `admin_clear_google_sheet_values`, and `admin_append_google_sheet_rows` succeed through `gog`
- Skill confirms the exact area, governorate when relevant, delivery type, and new price before any pricing publish
- Existing Google Sheet rows normalize into the Riders `areas` payload without missing required fields
- Sheet row IDs remain unique across the full normalized payload
- Empty price cells normalize to `null`
- Numeric text from the sheet normalizes to 3-decimal Riders pricing values
- `admin_publish_pricing_sheet_rows` accepts raw sheet rows from the Google integration
- `admin_publish_pricing_sheet_rows` auto-maps common header variants into Riders pricing fields
- `admin_publish_pricing_sheet_rows` dry run succeeds on a valid full sheet export
- `admin_publish_pricing_sheet_rows` dry run fails on duplicate area IDs or missing required names/governorate
- `admin_publish_pricing_snapshot` accepts structured `areas` payloads directly
- `admin_publish_pricing_snapshot` dry run succeeds on a valid full snapshot
- `admin_publish_pricing_snapshot` dry run fails on duplicate area IDs
- `admin_publish_pricing_snapshot` dry run fails on missing `name_en`, `name_ar`, or `governorate`
- Live publish succeeds after a passing dry run
- After live publish, `pricing.published.json` contains the newly approved values
- After live publish, the next customer `get_price` response reflects the updated published price without restart
- `admin_update_area_price` remains usable only as an emergency single-area fallback when the sheet workflow is unavailable
- Deploy path preserves a backup copy of the previous published snapshot and resolver overlay before overwrite

## Knowledge Base Checks

- Pickup working hours answer is `6:00 AM to 12:00 AM` for internal areas and `6:00 AM to 9:00 PM` for external areas
- Internal area SLA answer is `2-5 hours` standard and `within 2 hours` express
- External area SLA answer is `3-6 hours` standard and `within 3 hours` express
- Cash handling through driver is clearly rejected
- Order creation request is redirected to `https://order.tryriders.com`

## Escalation Checks

- Refund help triggers `assign_agent`
- Data modification triggers `assign_agent`
- Job application flow collects required details then triggers `assign_agent`
- System/payment error triggers `assign_agent`
- Special request with help request triggers `assign_agent`
- Unsupported question falls back to `assign_agent`

## Tracking Checks

- One-order tracking asks for order ID
- Multiple-order tracking still triggers `track_order`
- Tracking response does not expose raw backend details

## Complaints Checks

- Complaint gets captured via `complains`
- Response confirms forwarding for review
- No refund or compensation is promised

## Deployment Readiness Checks

- Real API key loaded from secrets, not hardcoded
- Real delivery WhatsApp account configured separately from recruiter
- Gateway token rotated from placeholder
- Public webhook URL answers on `/webhook` through the reverse proxy, not direct loopback only
- Reverse-proxy access logs capture `/webhook` requests with request IDs
- Production pricing source mode is `published_preferred`
- Production resolver overlay path is configured and deployed beside the published snapshot
- Production Google Sheets access is moved from normal auth to a dedicated service account, or sheet publish remains operationally quarantined
- Production spreadsheet is explicitly shared with the dedicated publishing identity when sheet publish is enabled
- Logs and monitoring reviewed
- Developer can start the project using only the delivery folder docs and secrets
