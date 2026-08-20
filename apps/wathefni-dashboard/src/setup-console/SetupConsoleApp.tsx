import {
  Archive,
  Building2,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clipboard,
  Link2,
  Loader2,
  LogOut,
  MessageCircle,
  Plus,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
} from 'lucide-react'
import {
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import { useConfirm } from '@/components/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/field'
import { cn } from '@/lib/utils'

import {
  createCompany,
  createOwner,
  deleteChannelAccount,
  getCompany,
  linkHrWhatsApp,
  listCompanies,
  onSetupSessionChange,
  saveChannelAccount,
  SetupConsoleApiError,
  updateCompanyLifecycle,
  updateCompanyProfile,
  updateCompanySettings,
} from './api'
import {
  clearStoredSession,
  credentialsFromSession,
  loginWithOperatorPassword,
  logoutSetupSession,
  probeSetupSession,
  readStoredSession,
  refreshSetupSession,
  type SetupSession,
} from './session'
import { CompanyControlPage } from './CompanyControlPage'
import { LaunchReadinessPage } from './LaunchReadinessPage'
import { ModulesAccessCard } from './ModulesAccessCard'
import { OnboardingWizard } from './OnboardingWizard'
import { OwnershipDeepLinksCard } from './OwnershipDeepLinksCard'
import { IntegrationsCatalogCard } from './IntegrationsCatalogCard'
import { PoliciesWorkflowsPage } from './PoliciesWorkflowsPage'
import { TeamAccessCard } from './TeamAccessCard'
import type {
  ChannelAccountInput,
  ChannelPolicy,
  CompanyCreateInput,
  CompanyDetailResponse,
  CompanyLifecycleStatus,
  CompanyProfileInput,
  CompanySummary,
  OwnerInput,
  SetupCredentials,
} from './types'
import {
  readCompanyParam,
  viewFromLocation,
  writeSetupConsoleLocation,
  type WorkspaceView,
} from './urlState'

const PAGE_SIZE = 20
const SEARCH_DEBOUNCE_MS = 250

function messageFrom(error: unknown) {
  return error instanceof Error ? error.message : 'Something interrupted this request. Please try again.'
}

function ownerInviteLink(result: { invite_link?: string; invite_url?: string; invite_token?: string }) {
  if (result.invite_link || result.invite_url) return result.invite_link || result.invite_url || ''
  if (!result.invite_token) return ''
  const url = new URL('/dashboard', window.location.origin)
  url.searchParams.set('invite', result.invite_token)
  return url.toString()
}

function companyLifecycleStatus(company: { status?: string | null; lifecycle?: { status?: string | null } | null; ready?: boolean }) {
  const status = String(company.lifecycle?.status || company.status || 'active').toLowerCase()
  if (status === 'disabled' || status === 'archived') return status as CompanyLifecycleStatus
  return 'active' as CompanyLifecycleStatus
}

function lifecycleBadgeTone(status: CompanyLifecycleStatus) {
  if (status === 'archived') return 'muted' as const
  if (status === 'disabled') return 'warning' as const
  return 'success' as const
}

function lifecycleLabel(status: CompanyLifecycleStatus) {
  if (status === 'archived') return 'Archived'
  if (status === 'disabled') return 'Disabled'
  return 'Active'
}

export default function SetupConsoleApp() {
  const confirm = useConfirm()
  const [credentials, setCredentials] = useState<SetupCredentials | null>(null)
  const [authBootstrapping, setAuthBootstrapping] = useState(true)
  const [companies, setCompanies] = useState<CompanySummary[]>([])
  const [total, setTotal] = useState(0)
  const [queryInput, setQueryInput] = useState('')
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [selectedCode, setSelectedCode] = useState('')
  const [detail, setDetail] = useState<CompanyDetailResponse | null>(null)
  const [listLoading, setListLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')
  const [includeInactive, setIncludeInactive] = useState(false)
  const [companyPickerOpen, setCompanyPickerOpen] = useState(() => !readCompanyParam())
  const [createCompanyOpen, setCreateCompanyOpen] = useState(false)
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>(() => viewFromLocation())
  const [uiLocale, setUiLocale] = useState<'en' | 'ar'>('en')
  const workspaceViewRef = useRef(workspaceView)
  workspaceViewRef.current = workspaceView

  const loadCompanies = useCallback(
    async (access: SetupCredentials, searchQuery = query, pageOffset = offset, showInactive = includeInactive) => {
      setListLoading(true)
      setError('')
      try {
        const result = await listCompanies(access, {
          q: searchQuery,
          limit: PAGE_SIZE,
          offset: pageOffset,
          includeInactive: showInactive,
        })
        setCompanies(result.companies)
        setTotal(result.total)
      } catch (loadError) {
        setError(messageFrom(loadError))
        if (loadError instanceof SetupConsoleApiError && [401, 403, 404].includes(loadError.status)) {
          setDetail(null)
          if (loadError.status === 401) {
            clearStoredSession()
            setCredentials(null)
          }
        }
      } finally {
        setListLoading(false)
      }
    },
    [includeInactive, offset, query],
  )

  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      const stored = readStoredSession()
      if (!stored) {
        if (!cancelled) {
          setCredentials(null)
          setAuthBootstrapping(false)
        }
        return
      }
      try {
        let session: SetupSession | null = stored
        const ok = await probeSetupSession(stored)
        if (!ok) {
          session = await refreshSetupSession(stored.refreshToken)
        }
        if (!cancelled) {
          if (session) setCredentials(credentialsFromSession(session))
          else {
            clearStoredSession()
            setCredentials(null)
          }
        }
      } catch {
        if (!cancelled) {
          clearStoredSession()
          setCredentials(null)
        }
      } finally {
        if (!cancelled) setAuthBootstrapping(false)
      }
    }
    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const unsubscribe = onSetupSessionChange((next) => {
      setCredentials(next)
      if (!next) {
        setCompanies([])
        setDetail(null)
        setSelectedCode('')
        setCompanyPickerOpen(true)
        setCreateCompanyOpen(false)
      }
    })
    return () => {
      unsubscribe()
    }
  }, [])

  useEffect(() => {
    function syncViewFromLocation() {
      setWorkspaceView(viewFromLocation())
    }
    window.addEventListener('hashchange', syncViewFromLocation)
    window.addEventListener('popstate', syncViewFromLocation)
    return () => {
      window.removeEventListener('hashchange', syncViewFromLocation)
      window.removeEventListener('popstate', syncViewFromLocation)
    }
  }, [])

  useEffect(() => {
    if (credentials) queueMicrotask(() => void loadCompanies(credentials))
  }, [credentials, loadCompanies])

  useEffect(() => {
    if ((workspaceView !== 'classic' && workspaceView !== 'policies') || detailLoading) return
    const hash = window.location.hash.replace(/^#/, '')
    if (!hash) return
    const timer = window.setTimeout(() => {
      document.getElementById(hash)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 80)
    return () => window.clearTimeout(timer)
  }, [workspaceView, detailLoading, selectedCode, detail])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = queryInput.trim()
      if (next === query) return
      setOffset(0)
      setQuery(next)
    }, SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [queryInput, query])

  const selectCompany = useCallback(
    async (companyCode: string) => {
      if (!credentials) return
      setSelectedCode(companyCode)
      setCompanyPickerOpen(false)
      setCreateCompanyOpen(false)
      writeSetupConsoleLocation({ company: companyCode, view: workspaceViewRef.current })
      setDetail(null)
      setDetailLoading(true)
      setError('')
      try {
        setDetail(await getCompany(credentials, companyCode))
      } catch (loadError) {
        setError(messageFrom(loadError))
      } finally {
        setDetailLoading(false)
      }
    },
    [credentials],
  )

  useEffect(() => {
    if (selectedCode) writeSetupConsoleLocation({ company: selectedCode, view: workspaceView })
  }, [selectedCode, workspaceView])

  useEffect(() => {
    if (!credentials) return
    const fromUrl = readCompanyParam()
    if (!fromUrl) return
    if (selectedCode === fromUrl) return
    const visible = companies.some((company) => company.company_code === fromUrl)
    if (visible) {
      void selectCompany(fromUrl)
      return
    }
    if (query !== fromUrl) {
      setQueryInput(fromUrl)
      setQuery(fromUrl)
      setOffset(0)
    }
  }, [companies, credentials, query, selectCompany, selectedCode])

  const refreshDetail = useCallback(async () => {
    if (!credentials || !selectedCode) return
    setDetailLoading(true)
    try {
      setDetail(await getCompany(credentials, selectedCode))
    } catch (loadError) {
      setError(messageFrom(loadError))
    } finally {
      setDetailLoading(false)
    }
  }, [credentials, selectedCode])

  if (authBootstrapping) {
    return (
      <main className="flex min-h-screen items-center justify-center px-5 py-12">
        <Card className="flex min-h-40 w-full max-w-lg items-center justify-center p-8">
          <LoadingLine label="Restoring Setup Console session" />
        </Card>
      </main>
    )
  }

  if (!credentials) {
    return (
      <ConnectScreen
        onConnect={async (next) => {
          const session = await loginWithOperatorPassword({
            email: next.email,
            password: next.password,
          })
          setCredentials(credentialsFromSession(session))
        }}
      />
    )
  }
  const connectedCredentials = credentials

  async function disconnect() {
    const approved = await confirm({
      title: 'Sign out of Setup Console?',
      body: 'This signs you out of Setup Console on this browser.',
      confirmLabel: 'Sign out',
      destructive: true,
    })
    if (!approved) return
    await logoutSetupSession(readStoredSession())
    setCredentials(null)
    setCompanies([])
    setDetail(null)
    setSelectedCode('')
    setCompanyPickerOpen(true)
    writeSetupConsoleLocation({ company: '', view: 'modules' })
  }

  async function handleCreated(input: CompanyCreateInput) {
    await createCompany(connectedCredentials, input)
    setQueryInput('')
    setQuery('')
    setOffset(0)
    await loadCompanies(connectedCredentials, '', 0)
    await selectCompany(input.company_code.trim().toUpperCase())
  }

  return (
    <div className="min-h-screen text-text" data-testid="setup-console-root" dir={uiLocale === 'ar' ? 'rtl' : 'ltr'} lang={uiLocale}>
      <header className="border-b border-line/60 bg-panel/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-3 px-5 py-3 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-text text-white shadow-soft">
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-subtle">OctoHR operator workspace</p>
              <h1 className="text-base font-semibold tracking-[-0.025em]">Setup Console</h1>
            </div>
          </div>
          <div className="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              className="flex min-w-0 max-w-full items-center gap-2 rounded-full border border-line/70 bg-white/70 px-3 py-1.5 text-left text-sm transition hover:border-accent/40"
              aria-expanded={companyPickerOpen}
              onClick={() => {
                setCompanyPickerOpen((open) => !open)
                setCreateCompanyOpen(false)
              }}
            >
              <Building2 className="h-3.5 w-3.5 shrink-0 text-subtle" aria-hidden="true" />
              {selectedCode ? (
                <span className="min-w-0 truncate">
                  Selected company <span className="font-semibold">{detail?.readiness?.name || selectedCode}</span>
                  <span className="ms-2 font-mono text-xs uppercase tracking-[0.08em] text-subtle">{selectedCode}</span>
                </span>
              ) : (
                <span className="text-subtle">Select a company</span>
              )}
              <ChevronDown className={cn('h-3.5 w-3.5 shrink-0 text-subtle transition', companyPickerOpen && 'rotate-180')} aria-hidden="true" />
            </button>
            <Button
              size="sm"
              variant={createCompanyOpen ? 'default' : 'secondary'}
              onClick={() => {
                setCreateCompanyOpen((open) => !open)
                setCompanyPickerOpen(false)
              }}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Create company
            </Button>
            {selectedCode && workspaceView !== 'modules' ? (
              <Button size="sm" variant="ghost" onClick={() => setWorkspaceView('modules')}>
                {uiLocale === 'ar' ? 'الوحدات والوصول' : 'Modules & Access'}
              </Button>
            ) : null}
            {selectedCode ? (
              <>
                <Button
                  size="sm"
                  variant={workspaceView === 'policies' ? 'default' : 'ghost'}
                  onClick={() => setWorkspaceView('policies')}
                >
                  {uiLocale === 'ar' ? 'السياسات ومسارات العمل' : 'Policies & Workflows'}
                </Button>
                <Button
                  size="sm"
                  variant={workspaceView === 'launch' ? 'default' : 'ghost'}
                  onClick={() => setWorkspaceView('launch')}
                >
                  {uiLocale === 'ar' ? 'جاهزية الإطلاق' : 'Launch readiness'}
                </Button>
                <Button
                  size="sm"
                  variant={workspaceView === 'control' ? 'default' : 'ghost'}
                  onClick={() => setWorkspaceView('control')}
                >
                  {uiLocale === 'ar' ? 'تحكم الشركة' : 'Company control'}
                </Button>
              </>
            ) : null}
            <Button
              variant={uiLocale === 'en' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => setUiLocale('en')}
            >
              EN
            </Button>
            <Button
              variant={uiLocale === 'ar' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => setUiLocale('ar')}
            >
              AR
            </Button>
            <Badge tone="success">Operator session connected</Badge>
            <Button variant="ghost" size="sm" onClick={() => void disconnect()}>
              <LogOut className="h-4 w-4" aria-hidden="true" />
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1200px] space-y-4 px-5 py-5 lg:px-8">
        {companyPickerOpen ? (
          <Card className="p-4">
            <CardHeader className="mb-3 pb-0">
              <CardTitle>Companies</CardTitle>
            </CardHeader>
            <form
              className="mt-3 flex gap-2"
              onSubmit={(event) => {
                event.preventDefault()
                setOffset(0)
                setQuery(queryInput.trim())
              }}
            >
              <label className="sr-only" htmlFor="company-search">Search companies</label>
              <Input
                id="company-search"
                className="min-w-0 flex-1"
                value={queryInput}
                onChange={(event) => setQueryInput(event.target.value)}
                placeholder="Name or company code"
                autoComplete="off"
              />
              <Button type="submit" size="sm" className="h-11 w-11 px-0" aria-label="Search companies">
                <Search className="h-4 w-4" aria-hidden="true" />
              </Button>
            </form>
            <label className="mt-2 flex items-center gap-2 text-xs text-subtle">
              <input
                type="checkbox"
                checked={includeInactive}
                onChange={(event) => {
                  setOffset(0)
                  setIncludeInactive(event.target.checked)
                }}
              />
              Show disabled and archived
            </label>
            <div className="mt-3 max-h-72 divide-y divide-line/50 overflow-auto rounded-2xl border border-line/55" aria-busy={listLoading}>
              {listLoading ? <LoadingLine label="Loading companies" /> : null}
              {!listLoading && companies.length === 0 ? (
                <p className="p-4 text-center text-sm text-subtle">No companies match this search.</p>
              ) : null}
              {!listLoading
                ? companies.map((company) => {
                    const code = company.company_code
                    const status = companyLifecycleStatus(company)
                    return (
                      <button
                        key={code}
                        type="button"
                        className={cn(
                          'flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition hover:bg-accent-soft/50',
                          selectedCode === code && 'bg-accent-soft/65',
                        )}
                        onClick={() => void selectCompany(code)}
                      >
                        <span className="min-w-0">
                          <span className="font-semibold">{company.name || code}</span>
                          <span className="ms-2 font-mono text-xs uppercase tracking-[0.08em] text-subtle">{code}</span>
                        </span>
                        <span className="flex shrink-0 items-center gap-1">
                          <Badge tone={lifecycleBadgeTone(status)}>{lifecycleLabel(status)}</Badge>
                          {status === 'active' && typeof company.ready === 'boolean' ? (
                            <Badge tone={company.ready ? 'success' : 'warning'}>
                              {company.ready ? 'Ready' : 'In progress'}
                            </Badge>
                          ) : null}
                        </span>
                      </button>
                    )
                  })
                : null}
            </div>
            <div className="mt-3 flex items-center justify-between">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={listLoading || offset === 0}
                onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
              >
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                Previous
              </Button>
              <span className="text-xs text-subtle">
                {total === 0 ? '0' : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)}`} of {total}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={listLoading || offset + PAGE_SIZE >= total}
                onClick={() => setOffset((current) => current + PAGE_SIZE)}
              >
                Next
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          </Card>
        ) : null}

        {createCompanyOpen ? <CreateCompanyCard onCreate={handleCreated} /> : null}

        {error ? <ErrorNotice message={error} /> : null}
          {workspaceView === 'modules' ? (
            <>
              {detailLoading && !detail ? (
                <Card className="flex min-h-72 items-center justify-center">
                  <LoadingLine label="Loading modules and access" />
                </Card>
              ) : null}
              {!selectedCode && !detailLoading ? <EmptySelection /> : null}
              {selectedCode && detail ? (
                <ModulesAccessCard
                  key={detail.available_modules.map((module) => `${module.key}:${module.configured}:${module.usable}:${module.effective}`).join('|')}
                  credentials={credentials}
                  companyCode={selectedCode}
                  locale={uiLocale}
                  modules={detail.available_modules}
                  bundles={detail.module_bundles || detail.module_guidance?.bundles || []}
                  lastChange={detail.last_module_change}
                  onChanged={async () => {
                    await refreshDetail()
                    await loadCompanies(credentials)
                  }}
                  onError={(nextError) => setError(messageFrom(nextError))}
                />
              ) : null}
            </>
          ) : null}
          {workspaceView === 'policies' && selectedCode ? (
            detailLoading && !detail ? (
              <Card className="flex min-h-72 items-center justify-center">
                <LoadingLine label={uiLocale === 'ar' ? 'جاري تحميل السياسات' : 'Loading policies and workflows'} />
              </Card>
            ) : detail ? (
              <PoliciesWorkflowsPage
                credentials={credentials}
                companyCode={selectedCode}
                locale={uiLocale}
                modules={detail.available_modules}
                onChanged={async () => {
                  await refreshDetail()
                  await loadCompanies(credentials)
                }}
                onError={(nextError) => setError(messageFrom(nextError))}
              />
            ) : (
              <EmptySelection />
            )
          ) : null}
          {workspaceView === 'launch' && selectedCode ? (
            <LaunchReadinessPage credentials={connectedCredentials} companyCode={selectedCode} locale={uiLocale} />
          ) : null}
          {workspaceView === 'wizard' ? (
            <OnboardingWizard
              credentials={connectedCredentials}
              locale={uiLocale}
              onOpenControl={(code) => {
                void selectCompany(code)
                setWorkspaceView('control')
              }}
            />
          ) : null}
          {workspaceView === 'control' && selectedCode ? (
            <CompanyControlPage credentials={connectedCredentials} companyCode={selectedCode} locale={uiLocale} />
          ) : null}
          {workspaceView === 'classic' ? (
            <>
          {detailLoading && !detail ? (
            <Card className="flex min-h-72 items-center justify-center">
              <LoadingLine label="Loading company setup" />
            </Card>
          ) : null}
          {!selectedCode && !detailLoading ? <EmptySelection /> : null}
          {selectedCode && detail ? (
            <CompanyWorkspace
              credentials={credentials}
              detail={detail}
              companyCode={selectedCode}
              locale={uiLocale}
              refreshing={detailLoading}
              onRefresh={refreshDetail}
              onChanged={async () => {
                await refreshDetail()
                await loadCompanies(credentials)
              }}
              onError={(nextError) => setError(messageFrom(nextError))}
              onOpenModules={() => setWorkspaceView('modules')}
              onOpenPolicies={() => setWorkspaceView('policies')}
            />
          ) : null}
            </>
          ) : null}
      </main>
    </div>
  )
}

function ConnectScreen({
  onConnect,
}: {
  onConnect: (credentials: { email: string; password: string }) => Promise<void>
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')

  return (
    <main className="flex min-h-screen items-center justify-center px-5 py-12">
      <Card className="w-full max-w-md p-8" data-testid="setup-console-admin-signin">
        <div className="mb-8">
          <p className="text-2xl font-semibold tracking-[-0.045em]">OctoHR</p>
          <CardTitle className="mt-6 text-xl">Admin sign-in</CardTitle>
          <CardDescription className="mt-2">Setup Console</CardDescription>
        </div>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (!email.trim() || !password || working) return
            setWorking(true)
            setError('')
            void onConnect({ email, password })
              .catch((connectError) => setError(messageFrom(connectError)))
              .finally(() => setWorking(false))
          }}
        >
          <Field label="Email" htmlFor="operator-email">
            <Input
              id="operator-email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </Field>
          <Field label="Password" htmlFor="operator-password">
            <Input
              id="operator-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </Field>
          {error ? <p className="text-sm text-rose-700">{error}</p> : null}
          <Button className="w-full" type="submit" disabled={!email.trim() || !password || working}>
            {working ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
      </Card>
    </main>
  )
}

function CreateCompanyCard({ onCreate }: { onCreate: (input: CompanyCreateInput) => Promise<void> }) {
  const initial: CompanyCreateInput = {
    company_code: '',
    name: '',
    country: 'KW',
    timezone: 'Asia/Kuwait',
    currency: 'KWD',
  }
  const [form, setForm] = useState(initial)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setWorking(true)
    setError('')
    try {
      await onCreate({
        ...form,
        company_code: form.company_code.trim().toUpperCase(),
        country: form.country.trim().toUpperCase(),
        currency: form.currency.trim().toUpperCase(),
      })
      setForm(initial)
    } catch (createError) {
      setError(messageFrom(createError))
    } finally {
      setWorking(false)
    }
  }

  return (
    <Card className="p-5">
      <CardHeader className="mb-4 pb-4">
        <CardTitle className="flex items-center gap-2">
          <Plus className="h-4 w-4" aria-hidden="true" />
          Create company
        </CardTitle>
        <CardDescription>Create the company record, then complete its setup on the right.</CardDescription>
      </CardHeader>
      <form className="space-y-3" onSubmit={(event) => void submit(event)}>
        <Field label="Company code" htmlFor="new-company-code">
          <Input
            id="new-company-code"
            value={form.company_code}
            onChange={(event) => setForm({ ...form, company_code: event.target.value })}
            placeholder="ACME"
            required
          />
        </Field>
        <Field label="Display name" htmlFor="new-company-name">
          <Input
            id="new-company-name"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            required
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Country" htmlFor="new-company-country">
            <Input
              id="new-company-country"
              value={form.country}
              onChange={(event) => setForm({ ...form, country: event.target.value })}
              placeholder="KW"
              maxLength={2}
              required
            />
          </Field>
          <Field label="Currency" htmlFor="new-company-currency">
            <Input
              id="new-company-currency"
              value={form.currency}
              onChange={(event) => setForm({ ...form, currency: event.target.value })}
              placeholder="KWD"
              maxLength={3}
              required
            />
          </Field>
        </div>
        <Field label="Timezone" htmlFor="new-company-timezone">
          <Input
            id="new-company-timezone"
            value={form.timezone}
            onChange={(event) => setForm({ ...form, timezone: event.target.value })}
            placeholder="Asia/Kuwait"
            required
          />
        </Field>
        {error ? <InlineError message={error} /> : null}
        <Button className="w-full" type="submit" disabled={working}>
          {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <Building2 className="h-4 w-4" />}
          Create and select
        </Button>
      </form>
    </Card>
  )
}

function CompanyWorkspace({
  credentials,
  detail,
  companyCode,
  locale = 'en',
  refreshing,
  onRefresh,
  onChanged,
  onError,
  onOpenModules,
  onOpenPolicies,
}: {
  credentials: SetupCredentials
  detail: CompanyDetailResponse
  companyCode: string
  locale?: 'en' | 'ar'
  refreshing: boolean
  onRefresh: () => Promise<void>
  onChanged: () => Promise<void>
  onError: (error: unknown) => void
  onOpenModules: () => void
  onOpenPolicies: () => void
}) {
  const readiness = detail?.readiness
  const channelPolicy = detail?.channel_policy || {}
  const lifecycleStatus = companyLifecycleStatus(readiness)
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Badge tone={lifecycleBadgeTone(lifecycleStatus)}>{lifecycleLabel(lifecycleStatus)}</Badge>
            <Badge tone={readiness?.ready ? 'success' : 'warning'}>
              {readiness?.ready ? 'Ready' : 'Setup in progress'}
            </Badge>
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-subtle">{companyCode}</span>
          </div>
          <h2 className="text-2xl font-semibold tracking-[-0.035em]">
            {readiness?.name || companyCode}
          </h2>
        </div>
        <Button variant="secondary" size="sm" onClick={() => void onRefresh()} disabled={refreshing}>
          <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} aria-hidden="true" />
          Refresh
        </Button>
      </div>

      <LifecycleCard
        credentials={credentials}
        companyCode={companyCode}
        detail={detail}
        onChanged={onChanged}
        onError={onError}
      />

      <ReadinessCard detail={detail} />
      <OwnershipDeepLinksCard locale={locale} />
      <div className="grid gap-6 xl:grid-cols-2">
        <ProfileCard
          key={[
            companyCode,
            readiness?.name,
            readiness?.country,
            readiness?.timezone,
            readiness?.currency,
          ].join(':')}
          credentials={credentials}
          companyCode={companyCode}
          detail={detail}
          onChanged={onChanged}
          onError={onError}
        />
        <Card id="classic-modules-redirect">
          <CardHeader>
            <CardTitle>{locale === 'ar' ? 'الوحدات والوصول' : 'Modules & Access'}</CardTitle>
            <CardDescription>
              {locale === 'ar'
                ? 'تفعيل الوحدات والحالة الفعلية انتقلت إلى تبويب الوحدات والوصول.'
                : 'Module entitlements and honest runtime status now live on the Modules & Access tab.'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button type="button" size="sm" onClick={onOpenModules}>
              {locale === 'ar' ? 'فتح الوحدات والوصول' : 'Open Modules & Access'}
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card id="classic-deprecated-policies" data-ownership="classic_deprecated">
        <CardHeader>
          <CardTitle>{locale === 'ar' ? 'الإعداد الكلاسيكي لم يعد المسار الأساسي' : 'Classic setup is deprecated'}</CardTitle>
          <CardDescription>
            {locale === 'ar'
              ? 'سياسات الوحدات وموجات ٤–٦ انتقلت إلى السياسات ومسارات العمل، وتظهر هناك فقط عند التخويل والنشر.'
              : 'Module and Wave 4–6 policy editors moved to Policies & Workflows, and open there only when entitled and deployed.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button type="button" size="sm" onClick={onOpenPolicies}>
            {locale === 'ar' ? 'فتح السياسات ومسارات العمل' : 'Open Policies & Workflows'}
          </Button>
          <Button type="button" size="sm" variant="secondary" onClick={onOpenModules}>
            {locale === 'ar' ? 'فتح الوحدات والوصول' : 'Open Modules & Access'}
          </Button>
        </CardContent>
      </Card>

      <IntegrationsCatalogCard
        credentials={credentials}
        companyCode={companyCode}
        locale={locale}
        onError={onError}
      />

      <ChannelPolicyCard
        credentials={credentials}
        companyCode={companyCode}
        policy={channelPolicy}
        onChanged={onChanged}
        onError={onError}
      />

      <div className="grid gap-6 xl:grid-cols-2">
        <CompanyChannelAccountCard
          key={[
            companyCode,
            detail.channel_account?.provider_account_id,
            detail.channel_account?.status,
            (detail.channel_account?.audiences || []).join(','),
            String(channelPolicy.company_channel_accounts_enabled === true),
          ].join(':')}
          credentials={credentials}
          companyCode={companyCode}
          detail={detail}
          onChanged={onChanged}
          onError={onError}
        />
        <HrWhatsAppCard
          credentials={credentials}
          companyCode={companyCode}
          onChanged={onChanged}
          onError={onError}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <OwnerInviteCard
          credentials={credentials}
          companyCode={companyCode}
          onChanged={onChanged}
          onError={onError}
        />
        <TeamAccessCard
          credentials={credentials}
          companyCode={companyCode}
          locale={locale}
          onError={onError}
        />
      </div>
    </div>
  )
}

function LifecycleCard({
  credentials,
  companyCode,
  detail,
  onChanged,
  onError,
}: {
  credentials: SetupCredentials
  companyCode: string
  detail: CompanyDetailResponse
  onChanged: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const confirm = useConfirm()
  const status = companyLifecycleStatus(detail.readiness)
  const [reason, setReason] = useState('')
  const [working, setWorking] = useState(false)
  const protectedCompany = companyCode.toUpperCase() === 'WATHEFNI'
  const reasonText = detail.readiness?.lifecycle?.reason || detail.readiness?.lifecycle_reason

  async function transition(next: CompanyLifecycleStatus, title: string, body: string) {
    const trimmed = reason.trim()
    if (!trimmed) {
      onError(new Error('Enter a reason before changing company lifecycle.'))
      return
    }
    const approved = await confirm({ title, body })
    if (!approved) return
    setWorking(true)
    try {
      await updateCompanyLifecycle(credentials, companyCode, { status: next, reason: trimmed })
      setReason('')
      await onChanged()
    } catch (error) {
      onError(error)
    } finally {
      setWorking(false)
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
        <div>
          <CardTitle>Company lifecycle</CardTitle>
          <CardDescription>
            Reversible controls only. Hard delete is not available. WATHEFNI is protected from disable/archive.
          </CardDescription>
        </div>
        <Badge tone={lifecycleBadgeTone(status)}>{lifecycleLabel(status)}</Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {reasonText ? (
          <p className="rounded-2xl border border-line/60 bg-white/45 px-4 py-3 text-sm leading-6 text-subtle">
            Last reason: {String(reasonText)}
          </p>
        ) : null}
        <Field label="Reason for lifecycle change" htmlFor="lifecycle-reason">
          <Input
            id="lifecycle-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Required for every Disable, Reactivate, or Archive"
            disabled={working}
          />
        </Field>
        <div className="flex flex-wrap gap-2">
          {status === 'active' ? (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={working || protectedCompany}
              onClick={() =>
                void transition(
                  'disabled',
                  `Disable ${companyCode}?`,
                  'Login, bootstrap, and invites will stop immediately. Sessions are revoked. Company data and modules stay preserved.',
                )
              }
            >
              Disable
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              disabled={working}
              onClick={() =>
                void transition(
                  'active',
                  `Reactivate ${companyCode}?`,
                  'Company data and modules stay as they were. Existing sessions are not restored; the Owner must log in again.',
                )
              }
            >
              Reactivate
            </Button>
          )}
          {status !== 'archived' ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="text-rose-700"
              disabled={working || protectedCompany}
              onClick={() =>
                void transition(
                  'archived',
                  `Archive ${companyCode}?`,
                  'The company will be blocked from access and hidden from the default active company list. This is reversible via Reactivate. No hard delete.',
                )
              }
            >
              <Archive className="h-4 w-4" aria-hidden="true" />
              Archive
            </Button>
          ) : null}
        </div>
        {protectedCompany ? (
          <p className="text-xs leading-5 text-subtle">
            Automation and Setup Console cannot disable or archive WATHEFNI without a separate explicit approval.
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

function ReadinessCard({ detail }: { detail: CompanyDetailResponse }) {
  const readiness = detail.readiness
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
        <div>
          <CardTitle>Provisioning readiness</CardTitle>
          <CardDescription>
            Required setup checks for {readiness.name || readiness.company_code}.
          </CardDescription>
        </div>
        <Badge tone={readiness.ready ? 'success' : 'warning'}>
          {readiness.ready ? 'Ready for use' : 'Action required'}
        </Badge>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {(readiness.steps || []).map((step) => (
          <div key={step.key} className="flex gap-3 rounded-2xl border border-line/60 bg-white/45 p-4">
            <div
              className={cn(
                'mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full',
                step.done ? 'bg-emerald-100 text-emerald-700' : 'bg-[#fff3dc] text-[#8a5a16]',
              )}
            >
              {step.done ? <Check className="h-3.5 w-3.5" /> : <CircleAlert className="h-3.5 w-3.5" />}
            </div>
            <div>
              <p className="text-sm font-medium">{step.label || humanize(step.key)}</p>
              {step.detail ? <p className="mt-1 text-xs leading-5 text-subtle">{step.detail}</p> : null}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function ProfileCard({
  credentials,
  companyCode,
  detail,
  onChanged,
  onError,
}: {
  credentials: SetupCredentials
  companyCode: string
  detail: CompanyDetailResponse
  onChanged: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const readiness = detail.readiness
  const [form, setForm] = useState<CompanyProfileInput>({
    name: readiness.name || '',
    country: readiness.country || '',
    timezone: readiness.timezone || '',
    currency: readiness.currency || '',
  })
  const [working, setWorking] = useState(false)
  const [saved, setSaved] = useState(false)

  async function save(event: FormEvent) {
    event.preventDefault()
    setWorking(true)
    setSaved(false)
    try {
      await updateCompanyProfile(credentials, companyCode, {
        name: form.name.trim(),
        country: form.country.trim().toUpperCase(),
        timezone: form.timezone.trim(),
        currency: form.currency.trim().toUpperCase(),
      })
      setSaved(true)
      await onChanged()
    } catch (saveError) {
      onError(saveError)
    } finally {
      setWorking(false)
    }
  }

  return (
    <Card id="classic-profile" data-ownership="company_identity">
      <CardHeader>
        <CardTitle>Company profile</CardTitle>
        <CardDescription>Client-facing identity and regional defaults.</CardDescription>
      </CardHeader>
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={(event) => void save(event)}>
        <Field label="Display name" htmlFor="profile-name">
          <Input id="profile-name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
        </Field>
        <Field label="Country" htmlFor="profile-country">
          <Input id="profile-country" value={form.country} onChange={(event) => setForm({ ...form, country: event.target.value })} maxLength={2} required />
        </Field>
        <Field label="Timezone" htmlFor="profile-timezone">
          <Input id="profile-timezone" value={form.timezone} onChange={(event) => setForm({ ...form, timezone: event.target.value })} placeholder="Asia/Kuwait" required />
        </Field>
        <Field label="Currency" htmlFor="profile-currency">
          <Input id="profile-currency" value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value })} maxLength={3} required />
        </Field>
        <div className="flex items-center justify-between gap-3 sm:col-span-2">
          <span className="text-xs text-emerald-700" role="status">{saved ? 'Profile saved.' : ''}</span>
          <Button size="sm" type="submit" disabled={working}>
            {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save profile
          </Button>
        </div>
      </form>
    </Card>
  )
}

const CHANNEL_SECTIONS: Array<{ key: keyof ChannelPolicy; title: string; description: string }> = [
  { key: 'pre_hiring', title: 'Pre-hiring channel', description: 'Candidate recruitment conversations.' },
  { key: 'post_hiring', title: 'Post-hiring channel', description: 'Employee service conversations.' },
  { key: 'hr_admin', title: 'HR administration channel', description: 'HR team operations and approvals.' },
]

function ChannelPolicyCard({
  credentials,
  companyCode,
  policy,
  onChanged,
  onError,
}: {
  credentials: SetupCredentials
  companyCode: string
  policy: ChannelPolicy
  onChanged: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const [working, setWorking] = useState(false)
  const reviewed = policy.reviewed === true

  async function markReviewed() {
    setWorking(true)
    try {
      await updateCompanySettings(credentials, companyCode, { channel_policy_reviewed: true })
      await onChanged()
    } catch (reviewError) {
      onError(reviewError)
    } finally {
      setWorking(false)
    }
  }

  return (
    <Card id="classic-channels" data-ownership="channel_policy">
      <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
        <div>
          <CardTitle>Channel policy</CardTitle>
          <CardDescription>Effective messaging capability by audience. These sections are operationally separate.</CardDescription>
        </div>
        <Button type="button" size="sm" variant={reviewed ? 'secondary' : 'default'} disabled={reviewed || working} onClick={() => void markReviewed()}>
          {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          {reviewed ? 'Policy reviewed' : 'Mark policy reviewed'}
        </Button>
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-3">
        {CHANNEL_SECTIONS.map((section) => {
          const values = policy[section.key]
          return (
            <section key={section.key} className="rounded-[1.25rem] border border-line/65 bg-white/45 p-5">
              <h3 className="text-sm font-semibold">{section.title}</h3>
              <p className="mt-1 text-xs leading-5 text-subtle">{section.description}</p>
              <div className="mt-4 space-y-2">
                {values && typeof values === 'object' && !Array.isArray(values)
                  ? Object.entries(values).map(([key, value]) => (
                      <div key={key} className="flex items-start justify-between gap-3 border-t border-line/45 pt-2 first:border-0 first:pt-0">
                        <span className="text-xs text-subtle">{humanize(key)}</span>
                        <FlexibleValue value={value} />
                      </div>
                    ))
                  : <span className="text-xs text-subtle">No policy reported.</span>}
              </div>
            </section>
          )
        })}
      </CardContent>
    </Card>
  )
}

function CompanyChannelAccountCard({
  credentials,
  companyCode,
  detail,
  onChanged,
  onError,
}: {
  credentials: SetupCredentials
  companyCode: string
  detail: CompanyDetailResponse
  onChanged: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const confirm = useConfirm()
  const account = detail.channel_account
  const platformAvailable = detail.channel_policy?.company_channel_accounts_enabled === true
  const [form, setForm] = useState<ChannelAccountInput>({
    provider: account?.provider || 'octopus',
    provider_account_id: account?.provider_account_id || '',
    sender_phone: account?.sender_phone || '',
    audiences: account?.audiences || ['candidate', 'employee'],
  })
  const [activate, setActivate] = useState(account?.status === 'active')
  const [verificationReference, setVerificationReference] = useState('')
  const [working, setWorking] = useState(false)

  async function save(event: FormEvent) {
    event.preventDefault()
    setWorking(true)
    try {
      await saveChannelAccount(credentials, companyCode, {
        ...form,
        status: activate ? 'active' : 'pending_verification',
        verification_reference: verificationReference.trim() || undefined,
      })
      await onChanged()
    } catch (saveError) {
      onError(saveError)
    } finally {
      setWorking(false)
    }
  }

  async function remove() {
    const approved = await confirm({
      title: 'Remove company WhatsApp Business account?',
      body: 'This disconnects the shared company sender. It does not remove any HR user’s WhatsApp identity.',
      confirmLabel: 'Remove account',
      destructive: true,
    })
    if (!approved) return
    setWorking(true)
    try {
      await deleteChannelAccount(credentials, companyCode)
      await onChanged()
    } catch (removeError) {
      onError(removeError)
    } finally {
      setWorking(false)
    }
  }

  return (
    <Card className="border-emerald-200/70 bg-emerald-50/25">
      <CardHeader>
        <div className="mb-2 flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <MessageCircle className="h-4 w-4 text-emerald-700" aria-hidden="true" />
            Company WhatsApp Business account
          </CardTitle>
          {account ? <Badge tone={account.verified ? 'success' : 'warning'}>{account.verified ? 'Verified' : account.status || 'Not verified'}</Badge> : null}
        </div>
        <CardDescription>
          The shared provider account and sender used by the company. This is not an HR user identity.
          Provider credentials are never stored here.
        </CardDescription>
      </CardHeader>
      {!platformAvailable ? (
        <div className="mb-4 rounded-2xl border border-amber-200/70 bg-amber-50/70 p-4 text-xs leading-5 text-amber-900">
          Company channel registration is not available on this environment. Existing status remains read-only and live delivery routing is unchanged.
        </div>
      ) : null}
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={(event) => void save(event)}>
        <Field label="Provider" htmlFor="channel-provider">
          <Input id="channel-provider" value={form.provider} readOnly required />
        </Field>
        <Field label="Provider account ID" htmlFor="channel-account-id">
          <Input
            id="channel-account-id"
            value={form.provider_account_id}
            disabled={!platformAvailable || working}
            onChange={(event) => setForm({ ...form, provider_account_id: event.target.value })}
            required
          />
        </Field>
        <Field label="Company sender phone" htmlFor="channel-sender-phone">
          <Input
            id="channel-sender-phone"
            type="tel"
            value={form.sender_phone}
            disabled={!platformAvailable || working}
            onChange={(event) => setForm({ ...form, sender_phone: event.target.value })}
            required
          />
        </Field>
        <fieldset className="space-y-2">
          <legend className="text-xs font-semibold text-text/85">Audiences</legend>
          {(['candidate', 'employee'] as const).map((audience) => (
            <label key={audience} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.audiences.includes(audience)}
                disabled={!platformAvailable || working}
                onChange={(event) => setForm({
                  ...form,
                  audiences: event.target.checked
                    ? [...form.audiences, audience]
                    : form.audiences.filter((item) => item !== audience),
                })}
              />
              {audience === 'candidate' ? 'Candidates / pre-hiring' : 'Employees / post-hiring'}
            </label>
          ))}
        </fieldset>
        <Field
          label="Provider verification reference"
          htmlFor="channel-verification-reference"
          hint="Required before the account can be marked active. Do not enter credentials."
        >
          <Input
            id="channel-verification-reference"
            value={verificationReference}
            disabled={!platformAvailable || working}
            onChange={(event) => setVerificationReference(event.target.value)}
          />
        </Field>
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input
            type="checkbox"
            checked={activate}
            disabled={!platformAvailable || working}
            onChange={(event) => setActivate(event.target.checked)}
          />
          Mark active after provider verification
        </label>
        <div className="flex justify-end gap-2 sm:col-span-2">
          {account ? (
            <Button type="button" variant="ghost" size="sm" className="text-rose-700" onClick={() => void remove()} disabled={!platformAvailable || working}>
              <Trash2 className="h-4 w-4" />
              Disable
            </Button>
          ) : null}
          <Button
            type="submit"
            size="sm"
            disabled={
              !platformAvailable
              || working
              || form.audiences.length === 0
              || (activate && !verificationReference.trim())
            }
          >
            {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
            Save company account
          </Button>
        </div>
      </form>
    </Card>
  )
}

function HrWhatsAppCard({
  credentials,
  companyCode,
  onChanged,
  onError,
}: {
  credentials: SetupCredentials
  companyCode: string
  onChanged: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const confirm = useConfirm()
  const [phone, setPhone] = useState('')
  const [working, setWorking] = useState(false)

  async function link(event: FormEvent) {
    event.preventDefault()
    const approved = await confirm({
      title: 'Link this HR user WhatsApp identity?',
      body: 'The phone will be associated with an existing company Owner. This does not configure the company’s shared WhatsApp Business sender.',
      confirmLabel: 'Link identity',
    })
    if (!approved) return
    setWorking(true)
    try {
      await linkHrWhatsApp(credentials, companyCode, phone.trim())
      setPhone('')
      await onChanged()
    } catch (linkError) {
      onError(linkError)
    } finally {
      setWorking(false)
    }
  }

  return (
    <Card className="border-sky-200/60 bg-sky-50/20">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="h-4 w-4 text-sky-700" aria-hidden="true" />
          HR-user WhatsApp identity
        </CardTitle>
        <CardDescription>
          Link an individual HR or Owner phone for identity and permissions. This is separate from the company WhatsApp Business account.
        </CardDescription>
      </CardHeader>
      <form className="space-y-4" onSubmit={(event) => void link(event)}>
        <Field label="HR user phone" htmlFor="hr-whatsapp-phone" hint="The Owner must already exist.">
          <Input id="hr-whatsapp-phone" type="tel" value={phone} onChange={(event) => setPhone(event.target.value)} required />
        </Field>
        <div className="flex justify-end">
          <Button type="submit" size="sm" disabled={working || !phone.trim()}>
            {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
            Link HR identity
          </Button>
        </div>
      </form>
    </Card>
  )
}

function OwnerInviteCard({
  credentials,
  companyCode,
  onChanged,
  onError,
}: {
  credentials: SetupCredentials
  companyCode: string
  onChanged: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const [form, setForm] = useState<OwnerInput>({ name: '', email: '', phone: '' })
  const [inviteLink, setInviteLink] = useState('')
  const [working, setWorking] = useState(false)
  const [copied, setCopied] = useState(false)

  async function create(event: FormEvent) {
    event.preventDefault()
    setWorking(true)
    setInviteLink('')
    setCopied(false)
    try {
      const result = await createOwner(credentials, companyCode, {
        name: form.name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim(),
      })
      setInviteLink(ownerInviteLink(result))
      await onChanged()
    } catch (createError) {
      onError(createError)
    } finally {
      setWorking(false)
    }
  }

  async function copyInvite() {
    if (!inviteLink) return
    try {
      await navigator.clipboard.writeText(inviteLink)
      setCopied(true)
    } catch (copyError) {
      onError(copyError)
    }
  }

  return (
    <Card id="classic-owner" data-ownership="team_day_to_day">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserPlus className="h-4 w-4" aria-hidden="true" />
          First Company Admin
        </CardTitle>
        <CardDescription>
          Seed the first Company Admin invite for this company. Day-to-day invites and role changes stay in Settings → Team.
        </CardDescription>
      </CardHeader>
      <form className="space-y-4" onSubmit={(event) => void create(event)}>
        <Field label="Owner name" htmlFor="owner-name">
          <Input id="owner-name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
        </Field>
        <Field label="Owner email" htmlFor="owner-email">
          <Input id="owner-email" type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
        </Field>
        <Field label="Owner phone" htmlFor="owner-phone">
          <Input id="owner-phone" type="tel" value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} />
        </Field>
        <div className="flex justify-end">
          <Button type="submit" size="sm" disabled={working}>
            {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
            Create owner invite
          </Button>
        </div>
      </form>
      {inviteLink ? (
        <div className="mt-5 rounded-2xl border border-emerald-200/70 bg-emerald-50/60 p-4">
          <p className="text-xs font-semibold text-emerald-900">Invite created — copy and share it securely</p>
          <p className="mt-2 break-all font-mono text-xs leading-5 text-emerald-900/80">{inviteLink}</p>
          <Button type="button" variant="secondary" size="sm" className="mt-3" onClick={() => void copyInvite()}>
            <Clipboard className="h-4 w-4" />
            {copied ? 'Copied' : 'Copy invite link'}
          </Button>
        </div>
      ) : null}
    </Card>
  )
}

function EmptySelection() {
  return (
    <Card className="flex min-h-[420px] items-center justify-center text-center">
      <div className="max-w-sm">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-[#8a5a16]">
          <Building2 className="h-5 w-5" aria-hidden="true" />
        </div>
        <h2 className="mt-5 text-lg font-semibold">Select a company</h2>
        <p className="mt-2 text-sm leading-6 text-subtle">
          Open the company selector, or create a company. Module entitlements stay in the URL as ?company=CODE.
        </p>
      </div>
    </Card>
  )
}

function ErrorNotice({ message }: { message: string }) {
  return (
    <div role="alert" className="mb-5 flex items-start gap-3 rounded-2xl border border-rose-200/75 bg-rose-50/80 p-4 text-sm text-rose-900">
      <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </div>
  )
}

function InlineError({ message }: { message: string }) {
  return <p role="alert" className="text-xs leading-5 text-rose-700">{message}</p>
}

function LoadingLine({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-6 text-sm text-subtle" role="status">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      {label}
    </div>
  )
}

function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string
  htmlFor: string
  hint?: string
  children: ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-xs font-semibold text-text/85">{label}</label>
      {children}
      {hint ? <p className="text-[11px] leading-4 text-subtle">{hint}</p> : null}
    </div>
  )
}

function FlexibleValue({ value }: { value: unknown }) {
  if (typeof value === 'boolean') {
    return <Badge tone={value ? 'success' : 'muted'}>{value ? 'Enabled' : 'Disabled'}</Badge>
  }
  if (Array.isArray(value)) {
    return <span className="max-w-[60%] text-right text-xs font-medium">{value.map(String).join(', ') || '—'}</span>
  }
  if (value && typeof value === 'object') {
    return <span className="max-w-[60%] text-right text-xs font-medium">{Object.values(value).map(String).join(' · ')}</span>
  }
  const text = value === null || value === undefined || value === '' ? '—' : String(value)
  const lowered = text.toLowerCase()
  const tone = lowered.includes('ready') || lowered.includes('active') || lowered.includes('available')
    ? 'success'
    : lowered.includes('disabled') || lowered.includes('unavailable')
      ? 'muted'
      : 'default'
  return <Badge tone={tone}>{humanize(text)}</Badge>
}

function humanize(value: string) {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}
