# Riders Delivery Instance

This folder contains the **fully separate delivery project scaffold** for Riders.

## Isolation Model

This project must stay completely isolated from the recruiter HR instance.

Isolation is enforced by:

- A separate OpenClaw profile:
  - `delivery`
- A separate OpenClaw state directory:
  - `~/.openclaw-delivery`
- A separate gateway port:
  - `18790`
- A separate agent:
  - `riders`
- A separate workspace:
  - `~/Desktop/claw/delivery/workspaces/riders`
- A separate WhatsApp account/number when enabled

## Important Rule

Do **not** reuse the recruiter WhatsApp account, recruiter workspace, recruiter sessions, or recruiter profile for Riders.

## Files

- `openclaw.template.json`
  - template config for the isolated delivery profile
- `.env.example`
  - secrets and integration placeholders
- `scripts/bootstrap-profile.sh`
  - creates the isolated `~/.openclaw-delivery` profile config if missing
- `scripts/start.sh`
  - starts the delivery gateway on port `18790`
- `scripts/stop.sh`
  - stops anything listening on the delivery gateway port
- `scripts/status.sh`
  - checks delivery gateway status

## Current Status

This is now a delivery-specific release candidate rather than a bare scaffold.

What is implemented:

- isolated delivery runtime and profile
- customer tools such as pricing, booking, tracking, escalation, complaints, and offers
- pricing admin publish flow for snapshot-based pricing
- resolver overlay support for aliases, ambiguity prompts, and grouped geo hints
- admin status and validation tooling for the pricing overlay
- local release-candidate pricing smoke suite

Preferred pricing architecture:

- serve customer pricing from `workspaces/riders/data/pricing.published.json`
- merge resolver metadata from `workspaces/riders/data/pricing.resolver.overlay.json`
- use Google Sheets as an authoring/publish input, not the preferred live served source

See `PRICING_ARCHITECTURE.md` for the full runbook.

## Recommended Workflow

1. Fill secrets and integration values in `.env`
2. Bootstrap the profile with `scripts/bootstrap-profile.sh`
3. Run the pricing release-candidate suite
4. Start the delivery gateway
5. Validate live pricing status through the admin tools
6. Pair or verify the separate delivery WhatsApp channel before any live cutover

Pricing RC command:

```bash
npm test --prefix /Users/azizalmulla/Desktop/claw/delivery/plugins/riders-tools
```

## Safety

Channels are intentionally disabled in the initial template so this scaffold cannot interfere with the recruiter instance until you explicitly enable the delivery channel.
