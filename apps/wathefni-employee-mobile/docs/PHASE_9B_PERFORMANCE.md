# Phase 9B Performance Report

Measured on 14 July 2026 from a production-mode Expo iOS export on Apple Silicon.

## Results

- Metro transformed 1,304 modules in 2.815 seconds.
- Hermes bytecode: 2,906,922 bytes (2.77 MiB).
- Exported assets: 772 KiB.
- Total exported iOS update payload: 3,616 KiB (3.53 MiB).
- Asset count: 13.
- Direct Ionicons imports reduced the payload from 7.2 MiB to 3.5 MiB (51% reduction).
- Hermes bytecode reduced from 3.22 MB to 2.91 MB (10% reduction).
- Bundled modules reduced from 1,358 to 1,304.
- TypeScript check: passed.
- Expo Doctor: 17/17 checks passed.

Commands:

```bash
npm run typecheck
npm run native:doctor
npm run native:bundle:ios
```

## Runtime work completed

- React Query now passes its abort signal into authenticated requests, cancelling obsolete screen fetches.
- Upload and download tasks cancel on user action and screen unmount.
- Preview routes, fixtures, browser server, and Playwright runtime dependencies were removed from the shipping graph.
- Animations use the native driver where their properties permit it and stop lift animation under Reduced Motion.
- Only the Ionicons font is exported; unused icon-family fonts no longer ship.

## Physical-device measurements still required

No iOS simulator runtime is installed on this Mac (`simctl` is unavailable), and no instrumented iPhone was attached. The following must be captured from a release-mode development build before TestFlight:

- Cold launch: process start to first usable signed-in or activation screen; target p50 ≤ 1.5 s and p95 ≤ 2.5 s.
- Warm launch: target p95 ≤ 1.0 s.
- Navigation: signposts around push/pop; target p95 ≤ 300 ms.
- Scrolling: Core Animation FPS for Home, Inbox, Documents, and Leave with production-sized payloads; target sustained 55–60 FPS with no repeated >100 ms stalls.
- Memory: idle after launch and after a 10-minute camera/upload/document cycle; target no monotonic growth and no retained transfer tasks.
- Image pipeline: peak memory and compression time for 12 MP and 48 MP photos.
- Native installed size and App Store thinning estimate from the signed archive.

Use Instruments (App Launch, Time Profiler, Core Animation, Allocations, and Leaks) against the release configuration. Debug-client timing is useful for regressions but is not an App Store performance result.

## Open performance risk

Inbox, Leave, and Documents APIs currently return arrays without an employee-app pagination contract. Their present `ScrollView` rendering is acceptable only while backend response sizes remain bounded. Pagination plus virtualized lists is required before those payloads can become unbounded.
