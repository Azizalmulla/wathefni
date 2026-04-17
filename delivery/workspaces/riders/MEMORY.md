# MEMORY.md - Riders Long-Term Memory

## Instance Identity

- Project: Riders delivery support
- OpenClaw profile: `delivery`
- State directory: `~/.openclaw-delivery`
- Workspace root: `/opt/riders-delivery/workspaces/riders` (VPS)
- Gateway port: `18790`
- Agent ID: `riders`
- VPS: `72.61.106.61`
- Domain: `riderskw.com`

## Hard Separation

- This project must stay fully separate from the recruiter project.
- Do not read recruiter sessions, recruiter memory, recruiter workspaces, recruiter channels, or recruiter company data.
- Do not reuse recruiter HR WhatsApp routing.
- Do not store Riders customer data in recruiter folders.

## Riders Business Rules

See IDENTITY.md for the full reference. Key facts for quick recall:
- Default quote: standard sedan + standard delivery only.
- Pickup working hours: internal areas `6:00 AM - 12:00 AM`; external areas `6:00 AM - 9:00 PM`.
- Price inquiries always go through `get_price`. Interpret the customer's area text into a proper name before calling the tool — it verifies and corrects if needed.

## Known Integrations

- Riders Grid API docs: `https://app-order.tryriders.com/docs/api`
- Order creation: Grid API at `app-order.tryriders.com/api`
- Pricing source: published snapshot (`pricing.published.json`) merged with the curated resolver overlay (`pricing.resolver.overlay.json`). Default source mode is `published_preferred`. Google Sheets is the authoring/publish input, not the live served source.
- Tracking: Fleetrunnr API (via `riders-tools` plugin)
- WhatsApp channel: Octopus (live, production)
- Area matching: model interprets the customer's input (Arabizi, shorthand, typos) then the deterministic resolver (exact → alias → typo/Arabizi expansion) verifies. Raw-text fallback corrects the model if it was wrong. Disambiguation prompts come from the resolver overlay.

## Live Capabilities

- Pricing support via `get_price` (live Google Sheet)
- In-chat order creation via `create_simple_order` (Grid API)
- Order tracking via `track_order` (Fleetrunnr)
- Complaints logging via `complains`
- Escalation to human via `assign_agent`
- General Riders FAQs
- WhatsApp location pin / Google Maps link resolution
- Image analysis (receipts, order screenshots, error pages)
- Admin tools for pricing and behavior policy management
