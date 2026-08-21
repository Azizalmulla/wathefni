import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  FileStack,
  GitBranch,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Users,
} from 'lucide-react'

import { useConfirm } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { StatusPill } from '@/components/ui/page-chrome'
import { SearchInput } from '@/components/ui/search-input'
import { URL_BACKED_WORKSPACE_TABS, useUrlBackedTab } from '@/lib/hrWebUrlTab'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  applyEmployeeEssRequest,
  cancelEmployeeLifecycleRequest,
  commitEmployeeOrgMigrationBatch,
  decideEmployeeEssRequest,
  decideEmployeeLifecycleRequest,
  dryRunEmployeeOrgMigrationBatch,
  getEmployeeEssPolicy,
  getEmployeeLifecyclePending,
  getEmployeeLifecycleRemediation,
  getEmployeeOrgReconcile,
  getEmployeeOrgUnits,
  listEmployeeEssRequests,
  listEmployeeOrgMigrationBatches,
  reconcileEmployeeEss,
  rollbackEmployeeOrgMigrationBatch,
} from '@/lib/api'
import { FRESHNESS_MS } from '@/lib/query/freshness'
import { useVisibilitySoftPoll } from '@/lib/query/useVisibilitySoftPoll'
import { cn } from '@/lib/utils'
import { ResourceState } from '@/pages/shared/dataState'
import type {
  DashboardAccess,
  EssRequestRow,
  LifecyclePendingResponse,
  MigrationBatchRow,
  OrgUnitRow,
  RemediationRow,
} from '@/types'

import {
  ApprovalStrip,
  BlockedReason,
  ConflictBanner,
  QuietStat,
  useEmployees360Locale,
  WorkforceSectionRail,
  WorkflowEmpty,
} from './chrome'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

type Props = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue: (issue: AccessIssue) => void
  onNavigate?: (page: string, opts?: { employee?: string }) => void
}

const PRIMARY_SECTION = 'organization' as const

const ADVANCED_SECTIONS = [
  { id: 'lifecycle', labelEn: 'Lifecycle', labelAr: 'دورة العمل' },
  { id: 'remediation', labelEn: 'Remediation', labelAr: 'المعالجة' },
  { id: 'migration', labelEn: 'Migration', labelAr: 'الترحيل' },
  { id: 'requests', labelEn: 'Requests', labelAr: 'الطلبات' },
] as const

const SECTIONS = [{ id: PRIMARY_SECTION, labelEn: 'Structure', labelAr: 'الهيكل' }, ...ADVANCED_SECTIONS] as const

type SectionId = (typeof SECTIONS)[number]['id']
type UnitTypeFilter = 'all' | 'department' | 'team' | 'location' | 'position' | 'other'

type OrgCoverageIssue = {
  employee_key?: string
  issue?: string
  severity?: string
}

type OrgCoverageSummary = {
  export_count: number
  hard_issue_count: number
  info_issue_count: number
  unassigned_keys: string[]
}

function can(permissions: string[], key: string) {
  return permissions.includes(key) || permissions.includes('*') || permissions.includes('employees.manage')
}

function friendlyError(err: unknown, fallback: string) {
  const anyErr = err as { detail?: { message?: string; error?: string }; message?: string }
  return String(anyErr?.detail?.message || anyErr?.message || fallback)
}

function nextApproverFromRoute(req: EssRequestRow): string | null {
  const route = Array.isArray(req.approval_route) ? req.approval_route : []
  const cursor = Number(req.approval_cursor || 0)
  const step = route[cursor] || route.find((s) => String(s?.status || '').toLowerCase() === 'pending')
  if (!step) return null
  return String(step.role || step.step || 'approver')
}

function unitTypeLabel(type: string, isAr: boolean): string {
  const key = String(type || '').toLowerCase()
  const map: Record<string, [string, string]> = {
    department: ['Department', 'قسم'],
    team: ['Team', 'فريق'],
    location: ['Location', 'موقع'],
    position: ['Position', 'منصب'],
    branch: ['Branch', 'فرع'],
    legal_employer: ['Legal employer', 'صاحب العمل'],
    cost_center: ['Cost center', 'مركز تكلفة'],
  }
  const pair = map[key]
  if (!pair) return type || '—'
  return isAr ? pair[1] : pair[0]
}

function isCoreUnitType(type: string): boolean {
  return ['department', 'team', 'location', 'position'].includes(String(type || '').toLowerCase())
}

function sectionAllowed(section: SectionId, canManage: boolean, canApprove: boolean, canSeeRequests: boolean, canViewStructure: boolean): boolean {
  if (section === 'organization') return canViewStructure
  if (section === 'lifecycle') return canManage || canApprove
  if (section === 'remediation' || section === 'migration') return canManage
  if (section === 'requests') return canSeeRequests
  return false
}

export function WorkforcePage({ access, permissions, onNotice, onAccessIssue, onNavigate }: Props) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const [section, setSection] = useUrlBackedTab('workforce', URL_BACKED_WORKSPACE_TABS.workforce, PRIMARY_SECTION)
  const [showAdvanced, setShowAdvanced] = useState(() => section !== PRIMARY_SECTION)
  const canManage = can(permissions, 'employees.manage')
  const canViewStructure = can(permissions, 'employees.read') || canManage
  const canApprove = can(permissions, 'employees.status.approve') || canManage
  const canSeeRequests =
    canManage
    || can(permissions, 'employees.ess.approve.hr')
    || can(permissions, 'employees.ess.apply')
    || can(permissions, 'employees.read')
  const advancedVisible = ADVANCED_SECTIONS.filter((s) => sectionAllowed(s.id, canManage, canApprove, canSeeRequests, canViewStructure))

  useEffect(() => {
    if (section !== PRIMARY_SECTION) setShowAdvanced(true)
  }, [section])

  const openSection = (id: SectionId) => {
    if (!sectionAllowed(id, canManage, canApprove, canSeeRequests, canViewStructure) && id !== PRIMARY_SECTION) return
    setSection(id)
    if (id !== PRIMARY_SECTION) setShowAdvanced(true)
  }

  const showBlocked =
    section === PRIMARY_SECTION
      ? !canViewStructure
      : !sectionAllowed(section, canManage, canApprove, canSeeRequests, canViewStructure)

  return (
    <div className="space-y-4" data-testid="workforce-hub" data-page="organization" dir={isAr ? 'rtl' : 'ltr'} lang={locale}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-[13px] leading-5 text-semantic-subtle">
          {isAr
            ? 'اعرض تسلسل وحدات الهيكل — الأقسام والفرق والمواقع والمناصب. هذا ليس خط إبلاغ المدير للموظف.'
            : 'View the company unit hierarchy — departments, teams, locations, and positions. This is not employee–manager reporting lines.'}
        </p>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {advancedVisible.length ? (
            <Button
              variant={showAdvanced ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => {
                const next = !showAdvanced
                setShowAdvanced(next)
                if (!next) setSection(PRIMARY_SECTION)
                else if (section === PRIMARY_SECTION && advancedVisible[0]) setSection(advancedVisible[0].id)
              }}
              data-testid="organization-advanced-toggle"
            >
              {showAdvanced ? (isAr ? 'الهيكل' : 'Structure') : (isAr ? 'إدارة متقدمة' : 'Advanced')}
            </Button>
          ) : null}
        </div>
      </div>

      {showAdvanced && advancedVisible.length ? (
        <div className="rounded-[1.2rem] border border-semantic-line/80 bg-semantic-surface-raised/55 px-3 py-2.5" data-testid="organization-advanced-rail">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-mist">
            {isAr ? 'إدارة متقدمة' : 'Advanced administration'}
          </p>
          <WorkforceSectionRail
            sections={advancedVisible.map((s) => ({ id: s.id, labelEn: s.labelEn, labelAr: s.labelAr }))}
            active={section === PRIMARY_SECTION ? '' : section}
            onChange={(id) => openSection(id as SectionId)}
            locale={locale}
          />
        </div>
      ) : null}

      {showBlocked ? (
        <BlockedReason
          reason={
            section === 'lifecycle'
              ? (isAr ? 'يتطلب صلاحية الموافقة على الحالة أو إدارة الموظفين' : 'Requires status approval or employees.manage')
              : section === PRIMARY_SECTION
                ? (isAr ? 'يتطلب صلاحية عرض الموظفين' : 'Requires employees.read')
                : (isAr ? 'يتطلب صلاحية إدارة الموظفين' : 'Requires employees.manage')
          }
          locale={locale}
        />
      ) : null}

      {!showAdvanced || section === PRIMARY_SECTION ? (
        <OrganizationPanel
          access={access}
          locale={locale}
          canView={canViewStructure}
          canManage={canManage}
          onNotice={onNotice}
          onAccessIssue={onAccessIssue}
          onNavigate={onNavigate}
        />
      ) : null}

      {showAdvanced && section === 'lifecycle' && (canManage || canApprove) ? (
        <LifecyclePanel
          access={access}
          locale={locale}
          canApprove={canApprove}
          canManage={canManage}
          onNotice={onNotice}
          onAccessIssue={onAccessIssue}
        />
      ) : null}
      {showAdvanced && section === 'remediation' && canManage ? (
        <RemediationPanel access={access} locale={locale} canManage={canManage} onNotice={onNotice} onAccessIssue={onAccessIssue} />
      ) : null}
      {showAdvanced && section === 'migration' && canManage ? (
        <MigrationPanel access={access} locale={locale} canManage={canManage} onNotice={onNotice} onAccessIssue={onAccessIssue} />
      ) : null}
      {showAdvanced && section === 'requests' && canSeeRequests ? (
        <RequestsPanel
          access={access}
          locale={locale}
          permissions={permissions}
          onNotice={onNotice}
          onAccessIssue={onAccessIssue}
        />
      ) : null}
    </div>
  )
}

function PanelShell({
  title,
  description,
  refreshing,
  onRefresh,
  children,
  stats,
  refreshLabel,
}: {
  title: string
  description: string
  refreshing?: boolean
  onRefresh?: () => void
  children: ReactNode
  stats?: ReactNode
  refreshLabel?: string
}) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-[16px] font-semibold tracking-[-0.02em] text-text">{title}</h3>
          <p className="mt-0.5 max-w-2xl text-[13px] text-subtle/90">{description}</p>
        </div>
        {onRefresh ? (
          <Button variant="ghost" size="sm" onClick={onRefresh} disabled={refreshing} aria-label={refreshLabel || 'Refresh'}>
            {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            <span className="sr-only sm:not-sr-only sm:ms-1">{refreshLabel || 'Refresh'}</span>
          </Button>
        ) : null}
      </div>
      {stats}
      {children}
    </div>
  )
}

function OrganizationPanel({
  access,
  locale,
  canView,
  canManage,
  onNotice,
  onAccessIssue,
  onNavigate,
}: {
  access: DashboardAccess
  locale: 'en' | 'ar'
  canView: boolean
  canManage: boolean
  onNotice: NoticeFn
  onAccessIssue: (issue: AccessIssue) => void
  onNavigate?: (page: string, opts?: { employee?: string }) => void
}) {
  const isAr = locale === 'ar'
  const [units, setUnits] = useState<OrgUnitRow[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [query, setQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState<UnitTypeFilter>('all')
  const [error, setError] = useState<string | null>(null)
  const [disabled, setDisabled] = useState(false)
  const [coverage, setCoverage] = useState<OrgCoverageSummary | null>(null)
  const [coverageBusy, setCoverageBusy] = useState(false)
  const [showTechnicalIds, setShowTechnicalIds] = useState(false)

  const load = useCallback(
    async (soft = false) => {
      if (!canView) {
        setLoading(false)
        return
      }
      if (soft) setRefreshing(true)
      else setLoading(true)
      try {
        const res = await getEmployeeOrgUnits(access)
        setUnits(Array.isArray(res.units) ? res.units : [])
        setError(null)
        setDisabled(false)
      } catch (err) {
        const issue = accessIssueFromError(err)
        if (issue) {
          onAccessIssue(issue)
          setError(friendlyError(err, isAr ? 'تعذر تحميل الهيكل' : 'Could not load organization'))
          return
        }
        const anyErr = err as { detail?: { error?: string } }
        if (anyErr?.detail?.error === 'org_v4_disabled') {
          setDisabled(true)
        } else {
          setError(friendlyError(err, isAr ? 'تعذر تحميل الهيكل' : 'Could not load organization'))
        }
      } finally {
        setLoading(false)
        setRefreshing(false)
      }
    },
    [access, canView, isAr, onAccessIssue],
  )

  useEffect(() => {
    void load()
  }, [load])

  const byId = useMemo(() => {
    const map = new Map<string, OrgUnitRow>()
    for (const u of units) map.set(u.org_unit_id, u)
    return map
  }, [units])

  const byType = useMemo(() => {
    const map = new Map<string, number>()
    for (const u of units) map.set(String(u.unit_type || '').toLowerCase(), (map.get(String(u.unit_type || '').toLowerCase()) || 0) + 1)
    return map
  }, [units])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return units.filter((u) => {
      const type = String(u.unit_type || '').toLowerCase()
      if (typeFilter === 'other' && isCoreUnitType(type)) return false
      if (typeFilter !== 'all' && typeFilter !== 'other' && type !== typeFilter) return false
      if (!q) return true
      const parentName = u.parent_org_unit_id ? byId.get(u.parent_org_unit_id)?.name || '' : ''
      return [u.name, u.unit_type, parentName].some((v) => String(v || '').toLowerCase().includes(q))
    })
  }, [units, query, typeFilter, byId])

  const structureRows = useMemo(() => {
    const roots = filtered.filter((u) => !u.parent_org_unit_id || !byId.has(String(u.parent_org_unit_id)))
    const childrenOf = (parentId: string) => filtered.filter((u) => String(u.parent_org_unit_id || '') === parentId)
    const walk = (node: OrgUnitRow, depth: number): { unit: OrgUnitRow; depth: number }[] => {
      const kids = childrenOf(node.org_unit_id).sort((a, b) => a.name.localeCompare(b.name))
      return [{ unit: node, depth }, ...kids.flatMap((k) => walk(k, depth + 1))]
    }
    const rooted = roots.sort((a, b) => a.name.localeCompare(b.name)).flatMap((r) => walk(r, 0))
    const rootedIds = new Set(rooted.map((r) => r.unit.org_unit_id))
    const orphans = filtered
      .filter((u) => !rootedIds.has(u.org_unit_id))
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((unit) => ({ unit, depth: 0 }))
    return [...rooted, ...orphans]
  }, [filtered, byId])

  const loadCoverage = useCallback(async () => {
    if (!canManage) return
    setCoverageBusy(true)
    try {
      const res = await getEmployeeOrgReconcile(access)
      const issues = Array.isArray((res as { issues?: OrgCoverageIssue[] }).issues)
        ? ((res as { issues: OrgCoverageIssue[] }).issues)
        : []
      const unassigned = [
        ...new Set(
          issues
            .filter((i) => String(i.issue || '') === 'missing_wave4_as_of_assignment')
            .map((i) => String(i.employee_key || '').trim())
            .filter(Boolean),
        ),
      ]
      setCoverage({
        export_count: Number((res as { export_count?: number }).export_count || 0),
        hard_issue_count: Number((res as { hard_issue_count?: number }).hard_issue_count || 0),
        info_issue_count: Number((res as { info_issue_count?: number }).info_issue_count || 0),
        unassigned_keys: unassigned,
      })
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue(issue)
      else onNotice(friendlyError(err, isAr ? 'تعذرت مراجعة التغطية' : 'Could not check coverage'), 'error')
    } finally {
      setCoverageBusy(false)
    }
  }, [access, canManage, isAr, onAccessIssue, onNotice])

  const openEmployee = (employeeKey: string) => {
    if (!employeeKey) return
    if (onNavigate) onNavigate('employees', { employee: employeeKey })
    else {
      const url = new URL(window.location.href)
      url.searchParams.set('page', 'employees')
      url.searchParams.set('employee', employeeKey)
      window.location.assign(`${url.pathname}${url.search}`)
    }
  }

  const filterChipClass = (active: boolean) =>
    cn(
      'rounded-full px-3 py-1.5 text-[12.5px] font-semibold transition-colors duration-150',
      active ? 'bg-semantic-ink text-white' : 'bg-semantic-ink/[0.08] text-semantic-subtle hover:text-semantic-ink',
    )

  const overview = (
    <div className="flex flex-wrap gap-2" data-testid="organization-overview">
      {[
        { key: 'department', label: isAr ? 'أقسام' : 'Departments', value: byType.get('department') || 0 },
        { key: 'team', label: isAr ? 'فرق' : 'Teams', value: byType.get('team') || 0 },
        { key: 'location', label: isAr ? 'مواقع' : 'Locations', value: byType.get('location') || 0 },
        { key: 'position', label: isAr ? 'مناصب' : 'Positions', value: byType.get('position') || 0 },
      ].map((item) => (
        <button
          key={item.key}
          type="button"
          className={cn(
            'rounded-full border border-semantic-line/80 bg-semantic-surface-raised/55 px-3.5 py-1.5 text-start transition hover:bg-semantic-surface-raised/80',
            typeFilter === item.key && 'border-semantic-ink/30 bg-semantic-ink/[0.08]',
          )}
          onClick={() => setTypeFilter((prev) => (prev === item.key ? 'all' : (item.key as UnitTypeFilter)))}
        >
          <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-subtle/80">{item.label}</span>
          <span className="ms-2 text-[15px] font-semibold tabular-nums text-text">{item.value}</span>
        </button>
      ))}
      {(byType.get('branch') || 0) + (byType.get('legal_employer') || 0) + (byType.get('cost_center') || 0) > 0 ? (
        <button
          type="button"
          className={cn(
            'rounded-full border border-semantic-line/80 bg-semantic-surface-raised/55 px-3.5 py-1.5 text-start transition hover:bg-semantic-surface-raised/80',
            typeFilter === 'other' && 'border-semantic-ink/30 bg-semantic-ink/[0.08]',
          )}
          onClick={() => setTypeFilter((prev) => (prev === 'other' ? 'all' : 'other'))}
        >
          <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-subtle/80">{isAr ? 'أخرى' : 'Other'}</span>
          <span className="ms-2 text-[15px] font-semibold tabular-nums text-text">
            {(byType.get('branch') || 0) + (byType.get('legal_employer') || 0) + (byType.get('cost_center') || 0)}
          </span>
        </button>
      ) : null}
    </div>
  )

  return (
    <Card tone="board" className="p-5" data-testid="organization-structure-board">
      <CardHeader className="mb-4 space-y-4 border-0 p-0">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-[15px]">{isAr ? 'تسلسل الوحدات' : 'Unit hierarchy'}</CardTitle>
            <CardDescription>
              {isAr
                ? `${filtered.length} وحدة تنظيمية · العمود يوضح الوحدة الأم وليس المدير`
                : `${filtered.length} organization unit${filtered.length === 1 ? '' : 's'} · parent unit only — not manager lines`}
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void load(true)}
              disabled={refreshing || !canView}
              aria-label={isAr ? 'تحديث' : 'Refresh'}
            >
              {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              <span className="sr-only sm:not-sr-only sm:ms-1">{isAr ? 'تحديث' : 'Refresh'}</span>
            </Button>
          </div>
        </div>
        {canView && !disabled && !loading && !error ? overview : null}
        {canView && !disabled && !loading && !error ? (
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput value={query} onChange={setQuery} placeholder={isAr ? 'ابحث بالاسم أو النوع…' : 'Search name or type…'} className="max-w-sm flex-1" />
            <div className="flex flex-wrap gap-1.5">
              {([
                ['all', isAr ? 'الكل' : 'All'],
                ['department', isAr ? 'أقسام' : 'Departments'],
                ['team', isAr ? 'فرق' : 'Teams'],
                ['location', isAr ? 'مواقع' : 'Locations'],
                ['position', isAr ? 'مناصب' : 'Positions'],
              ] as const).map(([id, label]) => (
                <button key={id} type="button" className={filterChipClass(typeFilter === id)} onClick={() => setTypeFilter(id)}>
                  {label}
                </button>
              ))}
            </div>
            <Button variant="ghost" size="sm" onClick={() => setShowTechnicalIds((v) => !v)}>
              {showTechnicalIds ? (isAr ? 'إخفاء المعرفات' : 'Hide IDs') : (isAr ? 'المعرفات التقنية' : 'Technical IDs')}
            </Button>
          </div>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-4 p-0">
        {disabled ? (
          <BlockedReason
            reason={isAr ? 'الهيكل التنظيمي غير مفعّل لهذه الشركة بعد.' : 'Organization structure is not enabled for this company yet.'}
            locale={locale}
          />
        ) : null}
        {loading ? (
          <ResourceState kind="loading" locale={isAr ? 'ar' : 'en'} testId="organization-units-state" />
        ) : error ? (
          <ResourceState kind="error" locale={isAr ? 'ar' : 'en'} title={error} onRetry={() => void load()} retrying={loading} testId="organization-units-state" />
        ) : !canView ? null : units.length === 0 ? (
          <WorkflowEmpty
            icon={<Building2 className="h-5 w-5" />}
            title={isAr ? 'لا توجد وحدات بعد' : 'No organization units yet'}
            hint={isAr ? 'أضف الأقسام والفرق والمواقع عبر المسار المصرّح به للهيكل.' : 'Add departments, teams, and locations through the authorized organization path.'}
          />
        ) : filtered.length === 0 ? (
          <WorkflowEmpty
            icon={<Building2 className="h-5 w-5" />}
            title={isAr ? 'لا نتائج' : 'No matching units'}
            hint={isAr ? 'جرّب بحثاً أو نوعاً آخر.' : 'Try a different search or type filter.'}
          />
        ) : (
          <>
            <div className="space-y-2 md:hidden" data-testid="organization-mobile-cards">
              {structureRows.map(({ unit: u, depth }) => {
                const parent = u.parent_org_unit_id ? byId.get(u.parent_org_unit_id) : null
                return (
                  <div
                    key={u.org_unit_id}
                    className="rounded-[1.15rem] border border-semantic-line/80 bg-white/55 px-3.5 py-3"
                    style={{ marginInlineStart: Math.min(depth, 3) * 12 }}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold text-text">{u.name}</p>
                      <StatusPill tone={u.status === 'active' ? 'priority' : 'paused'}>
                        {u.status === 'active' ? (isAr ? 'نشط' : 'Active') : (u.status || '—')}
                      </StatusPill>
                    </div>
                    <p className="mt-0.5 text-[12.5px] text-subtle/85">
                      {unitTypeLabel(u.unit_type, isAr)}
                      {parent ? ` · ${isAr ? 'ضمن وحدة' : 'within unit'} ${parent.name}` : ''}
                    </p>
                    {showTechnicalIds ? (
                      <p className="mt-1 font-mono text-[11px] text-subtle/70">{u.unit_key || u.org_unit_id.slice(0, 8)}</p>
                    ) : null}
                  </div>
                )
              })}
            </div>

            <div className="hidden overflow-x-auto rounded-[1.1rem] border border-semantic-line/80 md:block" data-testid="organization-desktop-table">
              <table className="w-full min-w-[560px] text-start text-[13px]">
                <thead className="bg-[#f7f1e6] text-[11px] uppercase tracking-[0.06em] text-subtle/80">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">{isAr ? 'الوحدة' : 'Unit'}</th>
                    <th className="px-4 py-2.5 font-medium">{isAr ? 'النوع' : 'Type'}</th>
                    <th className="px-4 py-2.5 font-medium">{isAr ? 'الوحدة الأم' : 'Parent unit'}</th>
                    <th className="px-4 py-2.5 font-medium">{isAr ? 'الحالة' : 'Status'}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-semantic-line/70">
                  {structureRows.map(({ unit: u, depth }) => {
                    const parent = u.parent_org_unit_id ? byId.get(u.parent_org_unit_id) : null
                    return (
                      <tr key={u.org_unit_id} className="hover:bg-white/40">
                        <td className="px-4 py-3">
                          <div style={{ paddingInlineStart: Math.min(depth, 4) * 14 }}>
                            <p className="font-semibold text-text">{u.name}</p>
                            {showTechnicalIds ? (
                              <p className="font-mono text-[11px] text-subtle/70">{u.unit_key || u.org_unit_id.slice(0, 8)}</p>
                            ) : null}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-subtle/90">{unitTypeLabel(u.unit_type, isAr)}</td>
                        <td className="px-4 py-3 text-subtle/90">{parent?.name || '—'}</td>
                        <td className="px-4 py-3">
                          <StatusPill tone={u.status === 'active' ? 'priority' : 'paused'}>
                            {u.status === 'active' ? (isAr ? 'نشط' : 'Active') : (u.status || '—')}
                          </StatusPill>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}

        {canManage && !disabled ? (
          <div className="rounded-[1.15rem] border border-semantic-line/80 bg-semantic-surface/45 px-4 py-3" data-testid="organization-coverage">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-[13px] font-semibold text-text">{isAr ? 'تغطية التعيين' : 'Assignment coverage'}</p>
                <p className="text-[12px] text-subtle/85">
                  {isAr
                    ? 'من ليس لديهم تعيين هيكلي يظهرون هنا. افتح الملف من الدليل — لا إدارة مزدوجة هنا.'
                    : 'People without a structure assignment appear here. Open their profile from Employees — no second admin workflow.'}
                </p>
              </div>
              <Button variant="secondary" size="sm" disabled={coverageBusy} onClick={() => void loadCoverage()}>
                {coverageBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitBranch className="h-4 w-4" />}
                {coverage ? (isAr ? 'إعادة الفحص' : 'Recheck') : (isAr ? 'فحص التغطية' : 'Check coverage')}
              </Button>
            </div>
            {coverage ? (
              <div className="mt-3 space-y-2">
                <p className="text-[12.5px] text-subtle/90">
                  {isAr
                    ? `${coverage.unassigned_keys.length} بلا تعيين · ${coverage.hard_issue_count} يحتاج مراجعة · ${coverage.export_count} موظف في المطابقة`
                    : `${coverage.unassigned_keys.length} unassigned · ${coverage.hard_issue_count} need review · ${coverage.export_count} people in coverage`}
                </p>
                {coverage.unassigned_keys.length ? (
                  <ul className="flex flex-wrap gap-2">
                    {coverage.unassigned_keys.slice(0, 12).map((key) => (
                      <li key={key}>
                        <Button size="sm" variant="ghost" onClick={() => openEmployee(key)}>
                          <Users className="h-3.5 w-3.5" />
                          {key}
                        </Button>
                      </li>
                    ))}
                    {coverage.unassigned_keys.length > 12 ? (
                      <li className="self-center text-[12px] text-subtle/75">+{coverage.unassigned_keys.length - 12}</li>
                    ) : null}
                  </ul>
                ) : (
                  <p className="text-[12.5px] text-subtle/85">{isAr ? 'لا فجوات تغطية معلوماتية.' : 'No informational coverage gaps.'}</p>
                )}
              </div>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

function LifecyclePanel({
  access,
  locale,
  canApprove,
  canManage,
  onNotice,
  onAccessIssue,
}: {
  access: DashboardAccess
  locale: 'en' | 'ar'
  canApprove: boolean
  canManage: boolean
  onNotice: NoticeFn
  onAccessIssue: (issue: AccessIssue) => void
}) {
  const isAr = locale === 'ar'
  const confirm = useConfirm()
  const [data, setData] = useState<LifecyclePendingResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!canManage && !canApprove) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      setData(await getEmployeeLifecyclePending(access))
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue(issue)
      else onNotice(friendlyError(err, isAr ? 'تعذر تحميل دورة الحياة' : 'Could not load lifecycle queue'), 'error')
    } finally {
      setLoading(false)
    }
  }, [access, canApprove, canManage, isAr, onAccessIssue, onNotice])

  useEffect(() => {
    void load()
  }, [load])

  const rows = data?.requests || []

  return (
    <PanelShell
      title={isAr ? 'إجراءات دورة الحياة' : 'Lifecycle actions'}
      description={isAr ? 'الموافقة منفصلة عن التنفيذ. الإجراءات الحقيقية تبقى ضمن البوابة الاصطناعية.' : 'Approval stays separate from apply. Real lifecycle remains synthetic-gated.'}
      onRefresh={() => void load()}
      stats={<QuietStat label={isAr ? 'معلّق' : 'Pending'} value={data?.count ?? rows.length} />}
    >
      {loading ? (
        <div className="flex justify-center py-16 text-mist">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : rows.length === 0 ? (
        <WorkflowEmpty
          icon={<CheckCircle2 className="h-5 w-5" />}
          title={isAr ? 'لا طلبات معلّقة' : 'No pending lifecycle requests'}
          hint={isAr ? 'الطلبات الجديدة تظهر هنا للمعتمد المعيّن.' : 'New requests appear here for the designated approver.'}
        />
      ) : (
        <div className="space-y-3">
          {rows.map((raw) => {
            const req = raw as Record<string, unknown>
            const id = String(req.request_id || req.id || '')
            const state = String(req.state || req.status || 'pending')
            const employeeKey = String(req.employee_key || '—')
            const caseType = String(req.case_type || req.request_type || 'lifecycle')
            const blocked = String(req.blocked_reason || req.fail_reason || '')
            return (
              <Card key={id || employeeKey + caseType} tone="board" className="p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-text">{employeeKey}</p>
                    <p className="text-[13px] text-subtle/90">{caseType.replace(/_/g, ' ')}</p>
                    <div className="mt-2">
                      <ApprovalStrip state={state} nextApprover={String(req.designated_approver_user_id || '') || null} locale={locale} />
                    </div>
                    {blocked ? <BlockedReason className="mt-2" reason={blocked} locale={locale} /> : null}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {canApprove && id ? (
                      <>
                        <Button
                          size="sm"
                          disabled={busyId === id}
                          onClick={async () => {
                            const ok = await confirm({
                              title: isAr ? 'الموافقة على الطلب؟' : 'Approve this request?',
                              body: isAr ? 'الموافقة لا تنفّذ التغيير تلقائياً.' : 'Approval does not apply the change by itself.',
                              confirmLabel: isAr ? 'موافقة' : 'Approve',
                            })
                            if (!ok) return
                            setBusyId(id)
                            try {
                              await decideEmployeeLifecycleRequest(access, id, { action: 'approve' })
                              onNotice(isAr ? 'تمت الموافقة' : 'Approved', 'success')
                              await load()
                            } catch (err) {
                              onNotice(friendlyError(err, 'Approve failed'), 'error')
                            } finally {
                              setBusyId(null)
                            }
                          }}
                        >
                          {isAr ? 'موافقة' : 'Approve'}
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={busyId === id}
                          onClick={async () => {
                            const reason = await confirm.withReason({
                              title: isAr ? 'رفض الطلب' : 'Reject request',
                              body: isAr ? 'سبب الرفض مطلوب.' : 'A rejection reason is required.',
                              confirmLabel: isAr ? 'رفض' : 'Reject',
                              destructive: true,
                              requireReason: true,
                            })
                            if (!reason) return
                            setBusyId(id)
                            try {
                              await decideEmployeeLifecycleRequest(access, id, { action: 'reject', decision_reason: reason })
                              onNotice(isAr ? 'تم الرفض' : 'Rejected', 'info')
                              await load()
                            } catch (err) {
                              onNotice(friendlyError(err, 'Reject failed'), 'error')
                            } finally {
                              setBusyId(null)
                            }
                          }}
                        >
                          {isAr ? 'رفض' : 'Reject'}
                        </Button>
                      </>
                    ) : null}
                    {canManage && id ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busyId === id}
                        onClick={async () => {
                          if (!(await confirm({ body: isAr ? 'إلغاء هذا الطلب؟' : 'Cancel this request?', destructive: true }))) return
                          setBusyId(id)
                          try {
                            await cancelEmployeeLifecycleRequest(access, id)
                            onNotice(isAr ? 'تم الإلغاء' : 'Cancelled', 'info')
                            await load()
                          } catch (err) {
                            onNotice(friendlyError(err, 'Cancel failed'), 'error')
                          } finally {
                            setBusyId(null)
                          }
                        }}
                      >
                        {isAr ? 'إلغاء' : 'Cancel'}
                      </Button>
                    ) : null}
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}
    </PanelShell>
  )
}

function RemediationPanel({
  access,
  locale,
  canManage,
  onNotice,
  onAccessIssue,
}: {
  access: DashboardAccess
  locale: 'en' | 'ar'
  canManage: boolean
  onNotice: NoticeFn
  onAccessIssue: (issue: AccessIssue) => void
}) {
  const isAr = locale === 'ar'
  const [rows, setRows] = useState<RemediationRow[]>([])
  const [note, setNote] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!canManage) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const res = await getEmployeeLifecycleRemediation(access)
      setRows(Array.isArray(res.rows) ? res.rows : [])
      setNote(String(res.note || ''))
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue(issue)
      else onNotice(friendlyError(err, 'Could not load remediation'), 'error')
    } finally {
      setLoading(false)
    }
  }, [access, canManage, onAccessIssue, onNotice])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <PanelShell
      title={isAr ? 'قائمة المعالجة' : 'Jurisdiction & data remediation'}
      description={
        isAr
          ? 'قراءة فقط. التصنيف يتطلب تحكماً مزدوجاً — بلا تصنيف تلقائي وبلا دورة حياة.'
          : 'Read-only. Classification needs dual control — no auto-classify, no lifecycle execution.'
      }
      onRefresh={canManage ? () => void load() : undefined}
      stats={<QuietStat label={isAr ? 'مفتوح' : 'Open'} value={rows.length} hint={note || undefined} />}
    >
      {loading ? (
        <div className="flex justify-center py-16 text-mist">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : rows.length === 0 ? (
        <WorkflowEmpty icon={<ShieldAlert className="h-5 w-5" />} title={isAr ? 'القائمة فارغة' : 'Remediation queue is clear'} />
      ) : (
        <div className="overflow-x-auto rounded-[var(--radius-wf-panel)] border border-semantic-line bg-wf-surface">
          <table className="w-full min-w-[640px] text-left text-[13px]">
            <thead className="bg-[#f7f1e6] text-[11px] uppercase tracking-[0.06em] text-subtle/80">
              <tr>
                <th className="px-4 py-2.5 font-medium">Employee</th>
                <th className="px-4 py-2.5 font-medium">Pack status</th>
                <th className="px-4 py-2.5 font-medium">Missing</th>
                <th className="px-4 py-2.5 font-medium">Next</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-semantic-line/70">
              {rows.map((r) => (
                <tr key={r.employment_id}>
                  <td className="px-4 py-3">
                    <p className="font-semibold text-text">{r.employee_key || r.employment_id.slice(0, 8)}</p>
                    <p className="text-[12px] text-subtle/80">{r.employment_status || '—'}</p>
                  </td>
                  <td className="px-4 py-3">
                    <StatusPill tone="review">{r.policy_pack_status || 'unset'}</StatusPill>
                  </td>
                  <td className="px-4 py-3 text-subtle/90">{(r.missing_fields || []).join(', ') || '—'}</td>
                  <td className="px-4 py-3 text-[12px] text-subtle">
                    {isAr ? 'تصنيف صريح بتحكم مزدوج' : 'Explicit dual-control classification'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PanelShell>
  )
}

function MigrationPanel({
  access,
  locale,
  canManage,
  onNotice,
  onAccessIssue,
}: {
  access: DashboardAccess
  locale: 'en' | 'ar'
  canManage: boolean
  onNotice: NoticeFn
  onAccessIssue: (issue: AccessIssue) => void
}) {
  const isAr = locale === 'ar'
  const confirm = useConfirm()
  const [batches, setBatches] = useState<MigrationBatchRow[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!canManage) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const res = await listEmployeeOrgMigrationBatches(access)
      setBatches(Array.isArray(res.batches) ? res.batches : [])
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue(issue)
      else onNotice(friendlyError(err, 'Could not load migrations'), 'error')
    } finally {
      setLoading(false)
    }
  }, [access, canManage, onAccessIssue, onNotice])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <PanelShell
      title={isAr ? 'الترحيل والعمليات الجماعية' : 'Migration & bulk'}
      description={isAr ? 'الالتزام والتراجع يتطلبان تأكيداً. التعيينات تبقى خاضعة لسلطة الهيكل.' : 'Commit and rollback require confirmation. Assignments stay under organization authority.'}
      onRefresh={canManage ? () => void load() : undefined}
      stats={<QuietStat label={isAr ? 'الدفعات' : 'Batches'} value={batches.length} />}
    >
      {loading ? (
        <div className="flex justify-center py-16 text-mist">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : batches.length === 0 ? (
        <WorkflowEmpty
          icon={<FileStack className="h-5 w-5" />}
          title={isAr ? 'لا دفعات ترحيل' : 'No migration batches'}
          hint={isAr ? 'أنشئ دفعة الترحيل عبر المسار المصرّح به للهيكل.' : 'Create a migration batch through the authorized organization path.'}
        />
      ) : (
        <div className="space-y-3">
          {batches.map((b) => (
            <Card key={b.batch_id} tone="board" className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-semibold text-text">{b.filename || b.batch_id.slice(0, 8)}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <StatusPill tone={b.status === 'committed' ? 'priority' : b.status === 'failed' ? 'active' : 'review'}>{b.status}</StatusPill>
                    <span className="text-[12px] text-subtle">
                      {b.row_count ?? 0} rows · {b.success_count ?? 0} ok · {b.fail_count ?? 0} fail
                    </span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={busy === b.batch_id}
                    onClick={async () => {
                      setBusy(b.batch_id)
                      try {
                        await dryRunEmployeeOrgMigrationBatch(access, b.batch_id)
                        onNotice('Dry-run complete', 'success')
                        await load()
                      } catch (err) {
                        onNotice(friendlyError(err, 'Dry-run failed'), 'error')
                      } finally {
                        setBusy(null)
                      }
                    }}
                  >
                    Dry-run
                  </Button>
                  <Button
                    size="sm"
                    disabled={busy === b.batch_id}
                    onClick={async () => {
                      const ok = await confirm({
                        title: isAr ? 'تنفيذ الدفعة؟' : 'Commit this batch?',
                        body: isAr ? 'هذا يكتب سجل التعيين الهيكلي.' : 'This writes organization assignment history.',
                        confirmLabel: isAr ? 'تنفيذ' : 'Commit',
                        destructive: true,
                      })
                      if (!ok) return
                      setBusy(b.batch_id)
                      try {
                        await commitEmployeeOrgMigrationBatch(access, b.batch_id)
                        onNotice('Committed', 'success')
                        await load()
                      } catch (err) {
                        onNotice(friendlyError(err, 'Commit failed'), 'error')
                      } finally {
                        setBusy(null)
                      }
                    }}
                  >
                    Commit
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy === b.batch_id}
                    onClick={async () => {
                      const ok = await confirm({
                        title: isAr ? 'التراجع عن الدفعة؟' : 'Roll back this batch?',
                        body: isAr ? 'يتراجع عن صفوف الترحيل المملوكة فقط.' : 'Rolls back migration-owned rows only.',
                        confirmLabel: isAr ? 'تراجع' : 'Rollback',
                        destructive: true,
                      })
                      if (!ok) return
                      setBusy(b.batch_id)
                      try {
                        await rollbackEmployeeOrgMigrationBatch(access, b.batch_id)
                        onNotice('Rolled back', 'info')
                        await load()
                      } catch (err) {
                        onNotice(friendlyError(err, 'Rollback failed'), 'error')
                      } finally {
                        setBusy(null)
                      }
                    }}
                  >
                    Rollback
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </PanelShell>
  )
}

function RequestsPanel({
  access,
  locale,
  permissions,
  onNotice,
  onAccessIssue,
}: {
  access: DashboardAccess
  locale: 'en' | 'ar'
  permissions: string[]
  onNotice: NoticeFn
  onAccessIssue: (issue: AccessIssue) => void
}) {
  const isAr = locale === 'ar'
  const confirm = useConfirm()
  const [requests, setRequests] = useState<EssRequestRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [filter, setFilter] = useState('')
  const [essOff, setEssOff] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const mayApproveHr = can(permissions, 'employees.ess.approve.hr') || can(permissions, 'employees.manage')
  const mayApprovePayroll =
    can(permissions, 'employees.ess.approve.payroll') || can(permissions, 'employees.manage')
  const canApply = can(permissions, 'employees.ess.apply') || can(permissions, 'employees.manage')

  const load = useCallback(async (opts?: { soft?: boolean }) => {
    if (!opts?.soft) setLoading(true)
    try {
      await getEmployeeEssPolicy(access)
      setEssOff(false)
      setError(false)
      const res = await listEmployeeEssRequests(access)
      setRequests(Array.isArray(res.requests) ? res.requests : [])
    } catch (err) {
      const anyErr = err as { detail?: { error?: string } }
      if (anyErr?.detail?.error === 'ess_v5_disabled') {
        setEssOff(true)
      } else {
        const issue = accessIssueFromError(err)
        if (issue) onAccessIssue(issue)
        else onNotice(friendlyError(err, 'Could not load ESS requests'), 'error')
        setError(true)
      }
    } finally {
      setLoading(false)
    }
  }, [access, onAccessIssue, onNotice])

  useEffect(() => {
    void load()
  }, [load])

  useVisibilitySoftPoll(() => load({ soft: true }), FRESHNESS_MS.inboundQueue, !essOff)

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return requests
    return requests.filter((r) => [r.employee_key, r.request_type, r.state].some((v) => String(v).toLowerCase().includes(q)))
  }, [requests, filter])

  const conflicts = filtered.filter((r) => String(r.state).includes('needs_review') || String(r.fail_reason || '').includes('conflict'))
  const pending = filtered.filter((r) => String(r.state).startsWith('pending') || r.state === 'submitted' || r.state === 'approved')

  return (
    <PanelShell
      title={isAr ? 'طلبات الخدمة الذاتية' : 'Self-service requests'}
      description={
        isAr
          ? 'مسارات الموظف والمدير وHR/Payroll. الموافقة منفصلة عن التطبيق. البيانات البنكية مقنّعة.'
          : 'Employee, manager, and HR/Payroll routes. Approve stays separate from apply. Bank data stays masked.'
      }
      onRefresh={() => void load()}
      stats={
        <div className="grid gap-3 sm:grid-cols-3">
          <QuietStat label={isAr ? 'الكل' : 'All'} value={requests.length} />
          <QuietStat label={isAr ? 'معلّق' : 'In flight'} value={pending.length} />
          <QuietStat label={isAr ? 'تعارضات' : 'Conflicts'} value={conflicts.length} hint={isAr ? 'يحتاج مراجعة' : 'Needs review'} />
        </div>
      }
    >
      {essOff ? <BlockedReason reason={isAr ? 'الخدمة الذاتية غير مفعّلة لهذه الشركة.' : 'Self-service requests are not enabled for this company.'} locale={locale} /> : null}
      {conflicts.length ? (
        <ConflictBanner
          locale={locale}
          detail={
            isAr
              ? `${conflicts.length} طلبات في needs_review — بلا الكتابة فوق الصامتة.`
              : `${conflicts.length} request(s) in needs_review — never silently overwrite.`
          }
          action={
            <Button
              size="sm"
              variant="secondary"
              onClick={async () => {
                try {
                  await reconcileEmployeeEss(access)
                  onNotice('Reconcile ran', 'info')
                  await load()
                } catch (err) {
                  onNotice(friendlyError(err, 'Reconcile failed'), 'error')
                }
              }}
            >
              {isAr ? 'مطابقة التراكب' : 'Reconcile overlays'}
            </Button>
          }
        />
      ) : null}

      <div className="flex justify-end">
        <SearchInput value={filter} onChange={setFilter} placeholder={isAr ? 'تصفية…' : 'Filter requests…'} />
      </div>

      {loading && requests.length === 0 ? (
        <ResourceState kind="loading" locale={isAr ? 'ar' : 'en'} testId="ess-requests-state" />
      ) : error ? (
        <ResourceState kind="error" locale={isAr ? 'ar' : 'en'} onRetry={() => void load()} retrying={loading} testId="ess-requests-state" />
      ) : filtered.length === 0 ? (
        <WorkflowEmpty icon={<Users className="h-5 w-5" />} title={isAr ? 'لا طلبات' : 'No self-service requests'} />
      ) : (
        <div className="space-y-3">
          {filtered.map((r) => {
            const next = nextApproverFromRoute(r)
            const isConflict = String(r.state) === 'needs_review'
            const state = String(r.state)
            const awaitingHr = ['pending_hr', 'pending_manager', 'submitted'].includes(state)
            const awaitingPayroll = state === 'pending_payroll'
            const mayDecideCurrent = (awaitingHr && mayApproveHr) || (awaitingPayroll && mayApprovePayroll)
            return (
              <Card key={r.request_id} tone="board" className={cn('p-4', isConflict && 'ring-1 ring-[#e8c9a0]')}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 space-y-2">
                    <div>
                      <p className="font-semibold text-text">{r.employee_key}</p>
                      <p className="text-[13px] text-subtle/90">
                        {essRequestTypeLabel(String(r.request_type || ''), isAr)}
                        {r.requester_kind ? ` · ${String(r.requester_kind).replace(/_/g, ' ')}` : ''}
                      </p>
                    </div>
                    <ApprovalStrip state={String(r.state)} nextApprover={next} locale={locale} />
                    {isConflict ? (
                      <ConflictBanner locale={locale} detail={String(r.fail_reason || (isAr ? 'تعارض إصدار التراكب' : 'Overlay version conflict'))} />
                    ) : null}
                    {awaitingPayroll && !mayApprovePayroll ? (
                      <p className="text-[12px] text-subtle">
                        {isAr ? 'بانتظار موافقة الرواتب.' : 'Waiting for payroll approval.'}
                      </p>
                    ) : null}
                    {r.request_type.includes('bank') ? (
                      <p className="flex items-center gap-1.5 text-[12px] text-subtle">
                        <AlertTriangle className="h-3.5 w-3.5" /> {isAr ? 'تفاصيل البنك مقنّعة افتراضياً' : 'Bank details masked by default'}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {mayDecideCurrent ? (
                      <>
                        <Button
                          size="sm"
                          disabled={busy === r.request_id}
                          onClick={async () => {
                            if (!(await confirm({ body: isAr ? 'الموافقة على هذا الطلب؟' : 'Approve this request?', confirmLabel: 'Approve' }))) return
                            setBusy(r.request_id)
                            try {
                              await decideEmployeeEssRequest(access, r.request_id, { action: 'approve' })
                              onNotice(
                                awaitingPayroll
                                  ? isAr
                                    ? 'وافقت الرواتب (لم يُطبَّق بعد)'
                                    : 'Payroll approved (not applied yet)'
                                  : isAr
                                    ? 'تمت الموافقة (لم يُطبَّق بعد)'
                                    : 'Approved (not applied yet)',
                                'success',
                              )
                              await load({ soft: true })
                            } catch (err) {
                              onNotice(friendlyError(err, 'Decide failed'), 'error')
                            } finally {
                              setBusy(null)
                            }
                          }}
                        >
                          {isAr ? 'موافقة' : 'Approve'}
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={busy === r.request_id}
                          onClick={async () => {
                            const reason = await confirm.withReason({
                              title: isAr ? 'إعادة الطلب للموظف' : 'Return to employee',
                              body: isAr ? 'سبب الرفض مطلوب.' : 'A rejection reason is required.',
                              confirmLabel: isAr ? 'إعادة' : 'Return',
                              destructive: true,
                              requireReason: true,
                            })
                            if (!reason) return
                            setBusy(r.request_id)
                            try {
                              await decideEmployeeEssRequest(access, r.request_id, {
                                action: 'reject',
                                comment: reason,
                              })
                              onNotice(isAr ? 'أُعيد الطلب للموظف' : 'Returned to the employee', 'info')
                              await load({ soft: true })
                            } catch (err) {
                              onNotice(friendlyError(err, 'Reject failed'), 'error')
                            } finally {
                              setBusy(null)
                            }
                          }}
                        >
                          {isAr ? 'إعادة للموظف' : 'Return'}
                        </Button>
                      </>
                    ) : null}
                    {canApply && String(r.state) === 'approved' ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={busy === r.request_id}
                        onClick={async () => {
                          if (
                            !(await confirm({
                              title: isAr ? 'تطبيق التغيير؟' : 'Apply this change?',
                              body: isAr ? 'التطبيق منفصل عن الموافقة ويكتب عبر سلطة الموجات.' : 'Apply is separate from approval and writes through wave authority.',
                              confirmLabel: isAr ? 'تطبيق' : 'Apply',
                            }))
                          )
                            return
                          setBusy(r.request_id)
                          try {
                            await applyEmployeeEssRequest(access, r.request_id)
                            onNotice(isAr ? 'تم التطبيق' : 'Applied', 'success')
                            await load({ soft: true })
                          } catch (err) {
                            onNotice(friendlyError(err, 'Apply failed'), 'error')
                          } finally {
                            setBusy(null)
                          }
                        }}
                      >
                        {isAr ? 'تطبيق' : 'Apply'}
                      </Button>
                    ) : null}
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}
    </PanelShell>
  )
}

function essRequestTypeLabel(requestType: string, isAr: boolean): string {
  const key = requestType.trim().toLowerCase()
  const labels: Record<string, [string, string]> = {
    bank_details: ['تفاصيل البنك', 'Bank details'],
    bank_update: ['تحديث البنك', 'Bank update'],
    personal_details: ['البيانات الشخصية', 'Personal details'],
    contact_details: ['بيانات التواصل', 'Contact details'],
    address_update: ['تحديث العنوان', 'Address update'],
    emergency_contact: ['جهة اتصال الطوارئ', 'Emergency contact'],
  }
  const pair = labels[key]
  if (pair) return isAr ? pair[0] : pair[1]
  return requestType.replace(/_/g, ' ')
}
