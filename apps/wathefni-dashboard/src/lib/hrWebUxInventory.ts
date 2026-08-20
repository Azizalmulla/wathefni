/**
 * Shared UX system inventory for HR Web Phase 1.
 * Preserve / consolidate / deprecate / replace — no visual redesign in this phase.
 */

export type UxDisposition = 'preserve' | 'consolidate' | 'deprecate' | 'replace-later'

export type UxInventoryRow = {
  id: string
  family: string
  component: string
  path: string
  disposition: UxDisposition
  notes: string
}

export const HR_WEB_UX_INVENTORY: UxInventoryRow[] = [
  {
    id: 'shell.app',
    family: 'app shell/sidebar',
    component: 'App shell (app-shell / app-sidebar / app-main)',
    path: 'src/App.tsx',
    disposition: 'preserve',
    notes: 'Viewport-locked shell, three nav groups, EN/AR dir on sidebar. Keep. Derive navItems from the Surface Registry next.',
  },
  {
    id: 'shell.header',
    family: 'headers/page intros',
    component: 'App.tsx page header + PageIntro',
    path: 'src/App.tsx + src/components/ui/page-chrome.tsx',
    disposition: 'consolidate',
    notes: 'Two intro patterns (App h1 vs PageIntro). Keep density personalities; stop duplicating titles inside modules.',
  },
  {
    id: 'actions.button',
    family: 'actions',
    component: 'Button',
    path: 'src/components/ui/button.tsx',
    disposition: 'preserve',
    notes: 'Shared pending state exists. Keep as the only action primitive.',
  },
  {
    id: 'actions.confirm',
    family: 'drawers/modals',
    component: 'ConfirmDialog vs PostHire ConfirmDialog',
    path: 'src/components/ConfirmDialog.tsx + src/posthire/PostHire.tsx',
    disposition: 'consolidate',
    notes: 'Two confirm overlays. Keep the shared ConfirmProvider; delete the PostHire-local copy in a later wave.',
  },
  {
    id: 'tabs.prehire',
    family: 'tabs',
    component: 'Interviews/Assessments URL tabs',
    path: 'src/pages/InterviewsPage.tsx, AssessmentsPage.tsx',
    disposition: 'preserve',
    notes: 'URL-backed tabs. This is the pattern enterprise workspaces should adopt.',
  },
  {
    id: 'tabs.enterprise',
    family: 'tabs',
    component: 'Post-hire workspace Tab unions',
    path: 'src/posthire/*Workspace.tsx',
    disposition: 'replace-later',
    notes: 'Local React state, lost on back, not deep-linkable. Do not redesign chrome yet — first put tabs in the URL.',
  },
  {
    id: 'search.filters',
    family: 'search/filters',
    component: 'dashboardNavigation + SearchInput',
    path: 'src/lib/dashboardNavigation.ts + src/components/ui/search-input.tsx',
    disposition: 'preserve',
    notes: 'Candidates/Interviews/Assessments filters are already URL-canonical. Extend to post-hire.',
  },
  {
    id: 'tables.lists',
    family: 'tables/lists',
    component: 'ad-hoc tables + organization desktop table',
    path: 'src/components/candidates, src/posthire/employees360',
    disposition: 'consolidate',
    notes: 'No shared DataTable. Several hex cream tables. Keep list IA; tokenize colors via semantic layer.',
  },
  {
    id: 'cards.surface',
    family: 'cards',
    component: 'Card + SoftKeepSurface + surface.tsx',
    path: 'src/components/ui/card.tsx, SoftKeepSurface.tsx, surface.tsx',
    disposition: 'preserve',
    notes: 'Soft-keep is the instant-feeling contract. Keep. Do not remount cards on refetch.',
  },
  {
    id: 'forms.field',
    family: 'forms',
    component: 'field.tsx Input/Select/Textarea',
    path: 'src/components/ui/field.tsx',
    disposition: 'preserve',
    notes: 'Shared form controls exist. Workspaces still mix raw inputs — consolidate onto field.tsx later.',
  },
  {
    id: 'status.pills',
    family: 'status indicators',
    component: 'StatusPill + Badge',
    path: 'src/components/ui/page-chrome.tsx, badge.tsx',
    disposition: 'consolidate',
    notes: 'StatusPill still has one hardcoded cream hex. Map remaining hex to semantic tokens without freezing the palette.',
  },
  {
    id: 'states.resource',
    family: 'loading/error/empty/unavailable',
    component: 'ResourceState + resolveListDataState',
    path: 'src/pages/shared/dataState.tsx',
    disposition: 'preserve',
    notes: 'Failure never collapses to empty. EN+AR. This is the canonical empty/error/unavailable contract.',
  },
  {
    id: 'states.skeleton',
    family: 'loading/error/empty/unavailable',
    component: 'PageSkeleton via Suspense',
    path: 'src/pages/PageSkeleton.tsx',
    disposition: 'replace-later',
    notes: 'Full-page skeleton on every lazy page switch is the main loading flash. Keep-alive cached pages instead of remounting.',
  },
  {
    id: 'query.layer',
    family: 'app shell/sidebar',
    component: 'TanStack Query + dashboardPerf',
    path: 'src/lib/query, src/lib/perf/dashboardPerf.ts',
    disposition: 'preserve',
    notes: 'Pre-hire already has cache, keepPreviousData, visibility refetch. Post-hire still fetches inside workspaces.',
  },
  {
    id: 'tokens.semantic',
    family: 'status indicators',
    component: 'index.css semantic-* aliases',
    path: 'src/index.css',
    disposition: 'preserve',
    notes: 'Palette is not frozen. Semantic aliases point at current tokens so a later central swap is possible.',
  },
]

export const HR_WEB_UX_DISPOSITION_COUNTS = HR_WEB_UX_INVENTORY.reduce(
  (acc, row) => {
    acc[row.disposition] += 1
    return acc
  },
  { preserve: 0, consolidate: 0, deprecate: 0, 'replace-later': 0 } as Record<UxDisposition, number>,
)
