# Wave 6A UX architecture (Calendar-aligned)

## Tabs (progressive disclosure)
1. **Schedule board** — always visible; simple-company direct L0 path unchanged
2. **Templates & recurrence** — Wave 4 only when `wave4.enabled`
3. **Publish & coverage** — Wave 5 when `wave5.enabled` — create period, open shift, coverage rule, submit/return/approve/publish/rollback draft
4. **Rotations & compliance** — Wave 6 when `wave6.enabled` — pattern/assignment list, rotation preview, draft-from-rotation, PAM export preview

## Honesty banners
- Simple / Wave 3–4 / Wave 5 publish / Wave 6 enterprise copy switches by enabled flag
- EN + AR + RTL via existing `dir`/`lang` shell; mobile day-first preserved

## data-testid hooks
- `shifts-workspace`, `shifts-publish-panel`, `shifts-publish-actions`, `shifts-enterprise-panel`, `shifts-enterprise-info`

## Screenshots
Browser screenshots were not captured in this staging qualify run. UI proof is via:
- dashboard `npm run build` success (PostHire chunk includes enterprise panel markers)
- staging API/smoke covering the same actions the buttons call
