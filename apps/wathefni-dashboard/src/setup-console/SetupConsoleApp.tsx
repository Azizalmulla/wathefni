import {
  Building2,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clipboard,
  KeyRound,
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
  saveChannelAccount,
  SetupConsoleApiError,
  updateCompanyModules,
  updateCompanyProfile,
  updateCompanySettings,
} from './api'
import type {
  AvailableModule,
  ChannelAccountInput,
  ChannelPolicy,
  CompanyCreateInput,
  CompanyDetailResponse,
  CompanyProfileInput,
  CompanySummary,
  OwnerInput,
  SetupCredentials,
} from './types'

const TOKEN_KEY = 'wathefni_setup_operator_token'
const PHONE_KEY = 'wathefni_setup_operator_phone'
const PAGE_SIZE = 20

function storedCredentials(): SetupCredentials | null {
  const token = sessionStorage.getItem(TOKEN_KEY)?.trim() || ''
  const phone = sessionStorage.getItem(PHONE_KEY)?.trim() || ''
  return token && phone ? { token, phone } : null
}

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

export default function SetupConsoleApp() {
  const confirm = useConfirm()
  const [credentials, setCredentials] = useState<SetupCredentials | null>(storedCredentials)
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

  const loadCompanies = useCallback(
    async (access: SetupCredentials, searchQuery = query, pageOffset = offset) => {
      setListLoading(true)
      setError('')
      try {
        const result = await listCompanies(access, {
          q: searchQuery,
          limit: PAGE_SIZE,
          offset: pageOffset,
        })
        setCompanies(result.companies)
        setTotal(result.total)
      } catch (loadError) {
        setError(messageFrom(loadError))
        if (loadError instanceof SetupConsoleApiError && [401, 403, 404].includes(loadError.status)) {
          setDetail(null)
        }
      } finally {
        setListLoading(false)
      }
    },
    [offset, query],
  )

  useEffect(() => {
    if (credentials) queueMicrotask(() => void loadCompanies(credentials))
  }, [credentials, loadCompanies])

  const selectCompany = useCallback(
    async (companyCode: string) => {
      if (!credentials) return
      setSelectedCode(companyCode)
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

  if (!credentials) {
    return (
      <ConnectScreen
        onConnect={(next) => {
          sessionStorage.setItem(TOKEN_KEY, next.token.trim())
          sessionStorage.setItem(PHONE_KEY, next.phone.trim())
          setCredentials({ token: next.token.trim(), phone: next.phone.trim() })
        }}
      />
    )
  }
  const connectedCredentials = credentials

  async function disconnect() {
    const approved = await confirm({
      title: 'Disconnect this operator session?',
      body: 'The setup token and authorised phone will be removed from this browser session.',
      confirmLabel: 'Disconnect',
      destructive: true,
    })
    if (!approved) return
    sessionStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(PHONE_KEY)
    setCredentials(null)
    setCompanies([])
    setDetail(null)
    setSelectedCode('')
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
    <div className="min-h-screen text-text">
      <header className="border-b border-line/60 bg-panel/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between gap-4 px-5 py-4 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-text text-white shadow-soft">
              <ShieldCheck className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">Wathefni</p>
              <h1 className="text-lg font-semibold tracking-[-0.025em]">Setup Console</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone="success">Operator session connected</Badge>
            <Button variant="ghost" size="sm" onClick={() => void disconnect()}>
              <LogOut className="h-4 w-4" aria-hidden="true" />
              Disconnect
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-[1500px] gap-6 px-5 py-7 lg:grid-cols-[340px_minmax(0,1fr)] lg:px-8">
        <aside className="space-y-5">
          <Card className="p-5">
            <CardHeader className="mb-4 pb-4">
              <CardTitle>Companies</CardTitle>
              <CardDescription>Find and select a company to review its provisioning.</CardDescription>
            </CardHeader>
            <form
              className="flex gap-2"
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
              />
              <Button size="sm" className="h-11 w-11 px-0" aria-label="Search companies">
                <Search className="h-4 w-4" aria-hidden="true" />
              </Button>
            </form>

            <div className="mt-4 min-h-24 space-y-2" aria-busy={listLoading}>
              {listLoading ? <LoadingLine label="Loading companies" /> : null}
              {!listLoading && companies.length === 0 ? (
                <p className="rounded-2xl border border-dashed border-line p-4 text-center text-sm text-subtle">
                  No companies match this search.
                </p>
              ) : null}
              {!listLoading
                ? companies.map((company) => {
                    const code = company.company_code
                    return (
                      <button
                        key={code}
                        type="button"
                        className={cn(
                          'w-full rounded-2xl border px-4 py-3 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
                          selectedCode === code
                            ? 'border-accent/45 bg-accent-soft/65 shadow-soft'
                            : 'border-line/60 bg-white/45 hover:border-accent/25 hover:bg-white/75',
                        )}
                        onClick={() => void selectCompany(code)}
                      >
                        <span className="flex items-start justify-between gap-3">
                          <span>
                            <span className="block text-sm font-semibold">{company.name || code}</span>
                            <span className="mt-0.5 block text-xs text-subtle">{code}</span>
                          </span>
                          {typeof company.ready === 'boolean' ? (
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

            <div className="mt-4 flex items-center justify-between border-t border-line/50 pt-4">
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

          <CreateCompanyCard onCreate={handleCreated} />
        </aside>

        <section className="min-w-0">
          {error ? <ErrorNotice message={error} /> : null}
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
              refreshing={detailLoading}
              onRefresh={refreshDetail}
              onChanged={async () => {
                await refreshDetail()
                await loadCompanies(credentials)
              }}
              onError={(nextError) => setError(messageFrom(nextError))}
            />
          ) : null}
        </section>
      </main>
    </div>
  )
}

function ConnectScreen({ onConnect }: { onConnect: (credentials: SetupCredentials) => void }) {
  const [token, setToken] = useState('')
  const [phone, setPhone] = useState('')

  return (
    <main className="flex min-h-screen items-center justify-center px-5 py-12">
      <Card className="w-full max-w-lg p-8">
        <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-2xl bg-text text-white shadow-soft">
          <KeyRound className="h-5 w-5" aria-hidden="true" />
        </div>
        <CardHeader>
          <CardTitle className="text-xl">Connect to Setup Console</CardTitle>
          <CardDescription>
            Use your platform operator token and allowlisted phone. Credentials remain in this browser
            session and are cleared when you disconnect or close the session.
          </CardDescription>
        </CardHeader>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (token.trim() && phone.trim()) onConnect({ token, phone })
          }}
        >
          <Field label="Operator token" htmlFor="operator-token">
            <Input
              id="operator-token"
              type="password"
              autoComplete="off"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              required
            />
          </Field>
          <Field label="Authorised operator phone" htmlFor="operator-phone" hint="Include country code.">
            <Input
              id="operator-phone"
              type="tel"
              autoComplete="tel"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              required
            />
          </Field>
          <Button className="w-full" type="submit" disabled={!token.trim() || !phone.trim()}>
            Connect securely
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
  refreshing,
  onRefresh,
  onChanged,
  onError,
}: {
  credentials: SetupCredentials
  detail: CompanyDetailResponse
  companyCode: string
  refreshing: boolean
  onRefresh: () => Promise<void>
  onChanged: () => Promise<void>
  onError: (error: unknown) => void
}) {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Badge tone={detail.readiness.ready ? 'success' : 'warning'}>
              {detail.readiness.ready ? 'Ready' : 'Setup in progress'}
            </Badge>
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-subtle">{companyCode}</span>
          </div>
          <h2 className="text-2xl font-semibold tracking-[-0.035em]">
            {detail.readiness.name || companyCode}
          </h2>
        </div>
        <Button variant="secondary" size="sm" onClick={() => void onRefresh()} disabled={refreshing}>
          <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} aria-hidden="true" />
          Refresh
        </Button>
      </div>

      <ReadinessCard detail={detail} />
      <div className="grid gap-6 xl:grid-cols-2">
        <ProfileCard
          key={[
            companyCode,
            detail.readiness.name,
            detail.readiness.country,
            detail.readiness.timezone,
            detail.readiness.currency,
          ].join(':')}
          credentials={credentials}
          companyCode={companyCode}
          detail={detail}
          onChanged={onChanged}
          onError={onError}
        />
        <ModulesCard
          key={detail.available_modules.map((module) => `${module.key}:${module.configured}:${module.effective}`).join('|')}
          credentials={credentials}
          companyCode={companyCode}
          modules={detail.available_modules}
          onChanged={onChanged}
          onError={onError}
        />
      </div>

      <ChannelPolicyCard
        credentials={credentials}
        companyCode={companyCode}
        policy={detail.channel_policy || {}}
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
            String(detail.channel_policy.company_channel_accounts_enabled === true),
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
        <TeamUsersCard users={detail.users || []} />
      </div>
    </div>
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
    <Card>
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

function ModulesCard({
  credentials,
  companyCode,
  modules,
  onChanged,
  onError,
}: {
  credentials: SetupCredentials
  companyCode: string
  modules: AvailableModule[]
  onChanged: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const [selected, setSelected] = useState(() => modules.filter((module) => module.configured).map((module) => module.key))
  const [working, setWorking] = useState(false)

  const grouped = useMemo(() => {
    return modules.reduce<Record<string, AvailableModule[]>>((groups, module) => {
      const suite = module.suite || 'Other'
      groups[suite] = [...(groups[suite] || []), module]
      return groups
    }, {})
  }, [modules])

  async function save() {
    setWorking(true)
    try {
      await updateCompanyModules(credentials, companyCode, selected)
      await onChanged()
    } catch (saveError) {
      onError(saveError)
    } finally {
      setWorking(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Canonical modules</CardTitle>
        <CardDescription>Enable the product areas included for this company.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {Object.entries(grouped).map(([suite, suiteModules]) => (
          <fieldset key={suite}>
            <legend className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-subtle">
              {humanize(suite)}
            </legend>
            <div className="space-y-2">
              {suiteModules.map((module) => {
                const unavailable = !module.platform_available
                return (
                  <label
                    key={module.key}
                    className={cn(
                      'flex items-start justify-between gap-4 rounded-2xl border border-line/55 bg-white/45 p-3.5',
                      unavailable && 'border-dashed',
                    )}
                  >
                    <span className="flex min-w-0 items-start gap-3">
                      <input
                        type="checkbox"
                        className="mt-1 h-4 w-4 accent-[#c89445]"
                        checked={selected.includes(module.key)}
                        disabled={working}
                        onChange={(event) =>
                          setSelected((current) =>
                            event.target.checked
                              ? [...current, module.key]
                              : current.filter((key) => key !== module.key),
                          )
                        }
                      />
                      <span>
                        <span className="block text-sm font-medium">{module.label || humanize(module.key)}</span>
                        <span className="mt-1 block text-xs text-subtle">
                          {module.audience ? `Audience: ${humanize(module.audience)}` : module.key}
                        </span>
                      </span>
                    </span>
                    <span className="flex shrink-0 flex-wrap justify-end gap-1.5">
                      <Badge tone={module.platform_available ? 'success' : 'muted'}>
                        Platform {module.platform_available ? 'available' : 'unavailable'}
                      </Badge>
                      <Badge tone={module.effective ? 'success' : module.configured ? 'warning' : 'muted'}>
                        {module.effective
                          ? 'Effective'
                          : module.configured && unavailable
                            ? 'Configured, awaiting activation'
                            : 'Not enabled'}
                      </Badge>
                    </span>
                  </label>
                )
              })}
            </div>
          </fieldset>
        ))}
        <div className="flex justify-end">
          <Button size="sm" type="button" onClick={() => void save()} disabled={working}>
            {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save modules
          </Button>
        </div>
      </CardContent>
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
    <Card>
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
  const platformAvailable = detail.channel_policy.company_channel_accounts_enabled === true
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
          <Input id="channel-account-id" value={form.provider_account_id} onChange={(event) => setForm({ ...form, provider_account_id: event.target.value })} required />
        </Field>
        <Field label="Company sender phone" htmlFor="channel-sender-phone">
          <Input id="channel-sender-phone" type="tel" value={form.sender_phone} onChange={(event) => setForm({ ...form, sender_phone: event.target.value })} required />
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
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserPlus className="h-4 w-4" aria-hidden="true" />
          Owner invite
        </CardTitle>
        <CardDescription>
          Create the first Owner and copy their private invite link. The console does not send invitations.
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

function TeamUsersCard({ users }: { users: CompanyDetailResponse['users'] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="h-4 w-4" aria-hidden="true" />
          Team users
        </CardTitle>
        <CardDescription>Current dashboard users and their account status.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {users.length === 0 ? <p className="text-sm text-subtle">No team users yet.</p> : null}
        {users.map((user, index) => (
          <div key={String(user.user_id || user.id || user.email || index)} className="flex items-center justify-between gap-4 rounded-2xl border border-line/55 bg-white/45 p-4">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{user.name || user.email || 'Unnamed user'}</p>
              <p className="mt-0.5 truncate text-xs text-subtle">{user.email || user.phone || 'No contact details'}</p>
            </div>
            <div className="flex shrink-0 gap-1.5">
              {user.role ? <Badge>{humanize(user.role)}</Badge> : null}
              {user.status ? <Badge tone={user.status === 'active' ? 'success' : 'muted'}>{humanize(user.status)}</Badge> : null}
            </div>
          </div>
        ))}
      </CardContent>
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
          Choose a company from the list, or create one, to manage its provisioning.
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
