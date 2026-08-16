# Open / post-loading smoothness

**Stamp:** `20260809T022740Z` · **PASS**

## Cause
After LoadingState, Home ran ~5 staggered FadeIns (opacity + translateY) while unlock/foreground soft-refresh refetched /me + active queries on the same frames. Second Home skeleton flash felt cheap.

## Fix
1. FadeIn defaults to opacity-only, `motion.duration.quick`
2. Home: one enter FadeIn (no stagger)
3. softRefresh deferred via InteractionManager + 64ms
4. Home loading uses shared `LoadingState` (no ContentSkeleton flash)

| OTA | `1426ee18-43b0-4838-b06d-ec5a0b98823e` |
| Rollback | `7356b390-d966-45d2-a24b-272bdb5cdc17` |
