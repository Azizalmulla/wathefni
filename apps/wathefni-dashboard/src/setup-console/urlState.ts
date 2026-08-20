export type WorkspaceView = 'modules' | 'launch' | 'classic' | 'wizard' | 'control'

export const DEFAULT_WORKSPACE_VIEW: WorkspaceView = 'modules'

const VIEWS = new Set<WorkspaceView>(['modules', 'launch', 'classic', 'wizard', 'control'])

export function readCompanyParam(search = typeof window === 'undefined' ? '' : window.location.search) {
  return String(new URLSearchParams(search).get('company') || '')
    .trim()
    .toUpperCase()
}

export function viewFromLocation(
  search = typeof window === 'undefined' ? '' : window.location.search,
  hash = typeof window === 'undefined' ? '' : window.location.hash,
): WorkspaceView {
  const params = new URLSearchParams(search)
  const viewParam = String(params.get('view') || '')
    .trim()
    .toLowerCase()
  const hashKey = hash.replace(/^#/, '')
  if (hashKey === 'classic-modules') return 'modules'
  if (hashKey.startsWith('classic-') || hashKey === 'classic-ownership') return 'classic'
  if (hashKey === 'control') return 'control'
  if (hashKey === 'launch') return 'launch'
  if (hashKey === 'wizard') return 'wizard'
  if (VIEWS.has(viewParam as WorkspaceView)) return viewParam as WorkspaceView
  return DEFAULT_WORKSPACE_VIEW
}

export function setupConsoleHref(input: { company?: string; view?: WorkspaceView; hash?: string }) {
  const params = new URLSearchParams()
  const company = String(input.company || '')
    .trim()
    .toUpperCase()
  if (company) params.set('company', company)
  const view = input.view || DEFAULT_WORKSPACE_VIEW
  if (view !== DEFAULT_WORKSPACE_VIEW) params.set('view', view)
  const query = params.toString()
  const hash = input.hash ? (input.hash.startsWith('#') ? input.hash : `#${input.hash}`) : ''
  return `/setup-console${query ? `?${query}` : ''}${hash}`
}

export function writeSetupConsoleLocation(input: { company?: string; view?: WorkspaceView }) {
  if (typeof window === 'undefined') return
  const url = new URL(window.location.href)
  const company = String(input.company || '')
    .trim()
    .toUpperCase()
  if (company) url.searchParams.set('company', company)
  else url.searchParams.delete('company')
  const view = input.view || DEFAULT_WORKSPACE_VIEW
  if (view === DEFAULT_WORKSPACE_VIEW) url.searchParams.delete('view')
  else url.searchParams.set('view', view)
  const hashKey = url.hash.replace(/^#/, '')
  if (view === 'modules' && (hashKey === 'classic-modules' || hashKey.startsWith('classic-'))) {
    url.hash = ''
  }
  const next = `${url.pathname}${url.search}${url.hash}`
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`
  if (next !== current) {
    window.history.replaceState(window.history.state, '', next)
  }
}
