# Phase 9B Readiness Decision

## Recommendation

Not ready for TestFlight yet.

The application code now has native transfer lifecycles, production-safe runtime handling, explicit push gating, safe-area corrections, accessibility fixes, a development-client profile, and measurable bundle improvements. TestFlight should wait for the blocking items below.

## App Store / TestFlight blockers

1. Complete and verify the Expo SDK 51 → 57 migration; rerun dependency audit and all native regressions.
2. Authenticate the owning EAS account and replace the placeholder project ID.
3. Supply approved App Store icon and splash assets.
4. Produce a signed physical-iPhone development build.
5. Complete the runtime performance and accessibility device matrices in the linked reports.
6. Configure a production crash/diagnostic service with privacy review and source-map handling.
7. Validate privacy disclosures, support/privacy URLs, account-deletion workflow, notification entitlement, export compliance, and App Store metadata.
8. Confirm production API/TLS readiness separately; no production testing was performed.

## Completed readiness controls

- Portrait orientation and intentional light-only appearance are explicit.
- Status bar uses dark content on the approved cream/light surfaces.
- Dynamic Island/notch spacing uses native safe-area insets.
- Native camera, Photos, and Files selection include just-in-time permission handling.
- Images are resized to a maximum 2048-pixel dimension and JPEG-compressed at 0.78 without unapproved cropping.
- Uploads and downloads expose progress, cancellation, retry, unmount cleanup, and authenticated 401 refresh.
- Downloaded files are kept in temporary cache and deleted after preview/share.
- External document links must be HTTPS; bearer tokens remain request headers only.
- Push permission is requested only from Settings after rationale; refresh listeners and logout cleanup are implemented.
- Production push registration is disabled by build configuration.
- Temporary web-preview runtime code no longer ships.

## Linked deliverables

- `DESIGN_SYSTEM.md`
- `PHASE_9B_PERFORMANCE.md`
- `PHASE_9B_ACCESSIBILITY.md`
- `PHASE_9B_ENGINEERING_AUDIT.md`
- `NATIVE_DEVELOPMENT_BUILD.md`
- `EMPLOYEE_API_GAP_PLANS.md`
