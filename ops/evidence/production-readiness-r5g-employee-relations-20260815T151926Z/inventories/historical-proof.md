# R5G historical reconstruction

Proved on `R5G7A4629`:

- Original intake, assignment, investigation events, evidence references, finding, outcome, closure, and employment-change handoff remain on the case history
- `history reconstructable` / `later` org or permission changes do not rewrite stored events
- Current permission still governs who may view that history (INV_A cannot read Case B history; view-only cannot see investigator note bodies)
- Module disable retains historical cases and does not expose them through a generic fallback
