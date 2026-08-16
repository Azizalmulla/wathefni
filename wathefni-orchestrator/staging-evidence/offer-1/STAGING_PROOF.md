# Offer-1 staging proof

**Status:** Staging green. **Production not deployed.**

## Artifact
- Staging-green SHA: `b99e800dd6b9666af7b1fe788cd7ca760285fbab6d8d4f83baf9129cbdb3fe83`
- Date: 2026-07-18

## Decisions locked
- Mobile V1: view, approve/return, record response, withdraw, confirm hire (no edit/send)
- Self-approval: separation of duties by default; `offer_allow_self_approval` company setting for small-company exception (audited)
- Hire gate: when `employment_offers` enabled, accepted offer required; `offer.hire_override` grant-only + reason + confirm + audit; never AI
- Document: versioned generated PDF; upload allowed only with match confirmation; sent versions immutable
- Phone/name: display snapshots only
- Delivery keyed by `offer_id + version`
- No AI lifecycle mutation

## Staging proof results (`ops/offer1-staging-proof.py`)
- Company: WATHEFNI
- App: `96597485758-WATHEFNI-HR`
- Offer: `0f30c47e-1d6c-478a-a7d8-1410823e6f3d`
- Flow: draft → version → submit → approve → send → token accept
- Hire blocked before accept; open after accept
- AI mutation rejected
- Delivery status tied to offer version (`intentionally_skipped` without WhatsApp transport in dry staging)
- Hire override path with mandatory reason exercised

## Stop
Do **not** run `ops/deploy.sh production` for Offer-1 until explicitly requested.
