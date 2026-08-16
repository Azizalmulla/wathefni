# api.ts isolation (visual ship)

`apps/wathefni-dashboard/src/lib/api.ts` remains in the working tree because HEAD is older than the extracted page modules (Calendar, Assistant capabilities, person-profile, platform integrations) and a hard restore breaks the local build.

**Visual correction ship review boundary:** treat `api.ts` as **out of scope**. Do not include it in the visual PR diff. It belongs to hybrid-email / M365 / calendar / settings tracks.

This folder keeps a byte copy of the working-tree file for audit: `api.ts.working-tree-backup`.
