# Wathefni Rendering Stability Wave 2

**Status:** Deployed (dashboard UX only)  
**Stamp:** `20260804T223220Z`  
**Mode:** Shared soft-keep contract — **not** a visual redesign, **not** backend authority

## Shared root causes addressed

1. Uneven soft-keep outside TanStack Query (Alerts, payroll worksheets blanked on reload)
2. Ranking hard-cleared cards + shell `busy` on every refresh
3. Calendar / Overview calendar **opacity flash** during refetch
4. Button `pending` inserted a spinner and grew control width
5. Work-queue comment claimed no keepPreviousData but client default still applied (wrong-scope risk)
6. No shared SoftKeep / request-id loader helpers

## Shared hooks / components

| Path | Role |
|---|---|
| `src/lib/renderingStability.ts` | Contract helpers (`isColdLoad` / `isSoftRefreshing`) |
| `src/components/ui/SoftKeepSurface.tsx` | Quiet updating rail — no opacity |
| `src/lib/query/useSoftKeepLoader.ts` | requestId soft-keep loader for non-RQ modules |
| `src/lib/query/client.ts` | Documented Wave 2 defaults |
| `src/components/ui/button.tsx` | Overlay pending spinner — width stable |
| `src/posthire/RenderingStabilityWave2Contract.test.ts` | Contract lock |

## Route-by-route (this wave)

| Route | Fix |
|---|---|
| Overview | Calendar panel opacity removed; work-queue explicit `placeholderData: undefined` |
| Jobs / Candidates / Interviews / Assessments | Already soft-keep via RQ — unchanged |
| Ranking | Soft-keep same job; local `rankingBusy` (no shell busy) |
| Calendar | Opacity flash removed; quiet Updating rail |
| Alerts & Delivery | Soft-keep reload + requestId |
| Payroll Close / Statutory | Soft-keep display + selection rematch (mutations unchanged) |
| Employees / Org / Attention / Onboarding / Attendance / Leave / Shifts / Analytics / Compliance | Already `useModuleData` soft-keep — unchanged |
| Activity | Already soft refresh — unchanged |
| Settings | N/A |

## Deferred (high-risk residuals)

- Global `mutate` / `setBusy` shell chrome for hiring mutations
- Broad `invalidate.allTenant` fan-out narrowing
- Keep-alive across pre-hire page remounts / Suspense
- Calendar `selectedSnapshot` + scroll restore
- Payroll **mutation** authority / money paths
- Wrong-job Ranking soft-keep (still clears on job switch — correct)

## Calendar Wave 2 GO/NO-GO

**GO** for Calendar Wave 2 **UX soft-keep parity follow-ons** (scroll restore, sticky selection) after this shared layer.  
**NO-GO** for new post-hiring calendar event sources / synthetic production emitters until product reviews Wave 1 populated preview.
