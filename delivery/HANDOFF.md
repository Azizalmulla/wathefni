# Riders Delivery Project Handoff

## Purpose

This is a **fully separate OpenClaw instance scaffold** for the Riders delivery support project.

It is intentionally isolated from the recruiter HR project.

## Separation Summary

This delivery project is separated by:

- OpenClaw profile:
  - `delivery`
- State directory:
  - `~/.openclaw-delivery`
- Gateway port:
  - `18790`
- Agent ID:
  - `riders`
- Workspace path:
  - `/Users/azizalmulla/Desktop/claw/delivery/workspaces/riders`
- Delivery config template:
  - `/Users/azizalmulla/Desktop/claw/delivery/openclaw.template.json`

## Current Repo Files

- `delivery/README.md`
- `delivery/.env.example`
- `delivery/openclaw.template.json`
- `delivery/workspaces/riders/AGENTS.md`
- `delivery/workspaces/riders/IDENTITY.md`
- `delivery/workspaces/riders/SKILL.md`
- `delivery/workspaces/riders/MEMORY.md`
- `delivery/workspaces/riders/TOOLS.md`
- `delivery/workspaces/riders/SOUL.md`
- `delivery/workspaces/riders/USER.md`
- `delivery/scripts/bootstrap-profile.sh`
- `delivery/scripts/start.sh`
- `delivery/scripts/stop.sh`
- `delivery/scripts/status.sh`

## External Dependencies

- Riders API docs:
  - `https://order-riders.trywebsight.com/docs/api`
- Riders integrations/API keys:
  - `https://order-riders.trywebsight.com/admin/integrations`
- Riders ordering site:
  - `https://order.tryriders.com`

## Secrets Required

Fill these before production use:

- `RIDERS_API_KEY`
- `OPENCLAW_GATEWAY_TOKEN`
- model provider API key(s)
- delivery WhatsApp account credentials / pairing
- any human escalation routing secrets or endpoints

## Business Rules Already Captured

The delivery prompt already encodes:

- Kuwaiti white dialect for Arabic
- concise professional English for non-Arabic
- no emojis
- no internal narration
- price replies default to:
  - `سياره عاديه + توصيل عادي`
- pickup working hours:
  - internal areas: `6:00 AM to 12:00 AM`
  - external areas: `6:00 AM to 9:00 PM`
- delivery SLAs:
  - internal standard: `2-5 hours`
  - internal express: `within 2 hours`
  - external standard: `3-6 hours`
  - external express: `within 3 hours`

## Current Architecture Status

The delivery instance is no longer just a scaffold.

Implemented:

- customer-facing Riders tools
- admin workspaces and pricing publish tooling
- published snapshot pricing runtime
- resolver overlay validation and status tooling
- local release-candidate pricing suite

Preferred long-term pricing model:

- runtime serves `pricing.published.json`
- runtime merges `pricing.resolver.overlay.json`
- Google Sheets remains an authoring/publish path, not the preferred live serving source

See `delivery/PRICING_ARCHITECTURE.md` for the detailed runbook.

## Remaining Go-Live Blockers

- rotate the placeholder gateway token
- verify production secrets are injected from secure storage
- pair and validate the separate delivery WhatsApp account
- harden or replace production Google Sheets auth instead of relying on ad hoc `gog` usage
- run the destructive live smoke on a dedicated test account during the final cutover window
- confirm logs and monitoring during deployment

## Known Flags and Deprecations

- `RIDERS_ONE_BRAIN` env flag (`0` / `1`). When enabled in `riders-tools`, the
  customer-facing booking path uses the deterministic booking-draft, order
  guard, and outbound-verify helpers under `plugins/shared/`. Leave off for
  legacy behavior. Covered by `scripts/eval-one-brain.mjs`.
- Tool `create_order` is deprecated. Use `create_simple_order` for all new
  order placements. The deprecated tool is kept only for compatibility with
  prior sessions and is not documented in the customer workflow.

## Local Commands

Bootstrap the isolated profile:

```bash
zsh /Users/azizalmulla/Desktop/claw/delivery/scripts/bootstrap-profile.sh
```

Run the pricing release-candidate suite:

```bash
npm test --prefix /Users/azizalmulla/Desktop/claw/delivery/plugins/riders-tools
```

Start the delivery gateway:

```bash
zsh /Users/azizalmulla/Desktop/claw/delivery/scripts/start.sh
```

Check status:

```bash
zsh /Users/azizalmulla/Desktop/claw/delivery/scripts/status.sh
```

Stop the delivery gateway:

```bash
zsh /Users/azizalmulla/Desktop/claw/delivery/scripts/stop.sh
```

## Hosting Notes

Before live cutover:

- deploy with `delivery/scripts/deploy.sh`
- confirm the live profile resolves to `published_preferred`
- confirm the resolver overlay is `active` via `admin_pricing_source_status`
- preserve and know how to restore the timestamped pricing backups created by deploy
- verify that the delivery project never references recruiter config/state
