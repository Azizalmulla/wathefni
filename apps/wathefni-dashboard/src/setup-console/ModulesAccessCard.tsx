import { useMemo, useState } from 'react'
import { ChevronDown, Loader2, Save } from 'lucide-react'

import { useConfirm } from '@/components/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { SearchInput } from '@/components/ui/search-input'
import { cn } from '@/lib/utils'

import { updateCompanyModules } from './api'
import {
  applyBundleModules,
  deriveAppSurfaces,
  expandHardDependencies,
  removeModuleWithDependents,
  softRecommendations,
} from './moduleGuidance'
import { SetupEffectiveStateBanner, canEnableFromState, type SetupEffectiveState } from './SetupEffectiveStateBanner'
import type { AvailableModule, LastModuleChange, ModuleBundle, SetupCredentials } from './types'

function humanize(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function moduleState(module: AvailableModule): SetupEffectiveState {
  if (module.effective_state && typeof module.effective_state === 'object') {
    return module.effective_state
  }
  return {
    effective_state: module.usable || module.effective ? 'enabled_usable' : 'available_disabled',
    usable: Boolean(module.usable ?? module.effective),
    stored_enabled: Boolean(module.stored_enabled ?? module.configured),
    can_enable: module.can_enable,
    label_en: module.usable || module.effective ? 'Enabled' : 'Available but disabled',
  }
}

function canSelectModule(module: AvailableModule, selected: boolean) {
  if (selected) return true
  if (module.can_select === true || module.key === 'employee_app') return true
  return canEnableFromState(moduleState(module))
}

function storedKeys(modules: AvailableModule[]) {
  return modules.filter((module) => module.configured || module.stored_enabled).map((module) => module.key)
}

function sameKeys(left: string[], right: string[]) {
  const a = [...left].sort()
  const b = [...right].sort()
  return a.length === b.length && a.every((key, index) => key === b[index])
}

function blockerText(module: AvailableModule, locale: 'en' | 'ar') {
  const state = moduleState(module)
  const isAr = locale === 'ar'
  const deployment = isAr ? state.deployment?.message_ar : state.deployment?.message_en
  const blocker = (state.blockers || [])
    .map((item) => (isAr ? item.message_ar : item.message_en) || item.code)
    .find(Boolean)
  return String(deployment || blocker || '').trim()
}

type ModuleFilter = 'all' | 'on' | 'available' | 'blocked' | 'changed'

export function ModulesAccessCard({
  credentials,
  companyCode,
  locale = 'en',
  modules,
  bundles,
  lastChange,
  onChanged,
  onError,
}: {
  credentials: SetupCredentials
  companyCode: string
  locale?: 'en' | 'ar'
  modules: AvailableModule[]
  bundles: ModuleBundle[]
  lastChange?: LastModuleChange | null
  onChanged: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const confirm = useConfirm()
  const isAr = locale === 'ar'
  const initial = storedKeys(modules)
  const [selected, setSelected] = useState(initial)
  const [notices, setNotices] = useState<string[]>([])
  const [working, setWorking] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<ModuleFilter>('all')
  const [openDetails, setOpenDetails] = useState<Record<string, boolean>>({})
  const [howItWorksOpen, setHowItWorksOpen] = useState(false)

  const stored = useMemo(() => storedKeys(modules), [modules])
  const dirty = !sameKeys(selected, stored)
  const added = selected.filter((key) => !stored.includes(key))
  const removed = stored.filter((key) => !selected.includes(key))

  const grouped = useMemo(() => {
    return modules.reduce<Record<string, AvailableModule[]>>((groups, module) => {
      const suite = module.suite || 'Other'
      groups[suite] = [...(groups[suite] || []), module]
      return groups
    }, {})
  }, [modules])

  const recommendations = useMemo(() => softRecommendations(selected, modules), [selected, modules])
  const appSurfaces = useMemo(() => deriveAppSurfaces(selected, modules), [selected, modules])
  const employeeAppSelected = selected.includes('employee_app')
  const employeeAppModule = modules.find((module) => module.key === 'employee_app')

  const summary = useMemo(() => {
    let enabled = 0
    let available = 0
    let blocked = 0
    for (const module of modules) {
      const isSelected = selected.includes(module.key)
      const selectable = canSelectModule(module, isSelected)
      if (isSelected) enabled += 1
      else if (!selectable) blocked += 1
      else available += 1
    }
    return { enabled, available, blocked, total: modules.length }
  }, [modules, selected])

  const visibleKeys = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return new Set(
      modules
        .filter((module) => {
          const isSelected = selected.includes(module.key)
          const selectable = canSelectModule(module, isSelected)
          const changed = added.includes(module.key) || removed.includes(module.key)
          if (filter === 'on' && !isSelected) return false
          if (filter === 'available' && (isSelected || !selectable)) return false
          if (filter === 'blocked' && (isSelected || selectable)) return false
          if (filter === 'changed' && !changed) return false
          if (!needle) return true
          const haystack = [
            module.label,
            module.key,
            module.suite,
            module.audience,
            ...(module.depends_on_labels || module.depends_on || []),
            blockerText(module, locale),
          ]
            .join(' ')
            .toLowerCase()
          return haystack.includes(needle)
        })
        .map((module) => module.key),
    )
  }, [added, filter, locale, modules, query, removed, selected])

  function toggleModule(key: string, checked: boolean) {
    const module = modules.find((item) => item.key === key)
    if (checked && module && !canSelectModule(module, false)) {
      setNotices([
        isAr
          ? 'لا يمكن تفعيل هذه الوحدة لأنها لن تصبح قابلة للاستخدام.'
          : 'This module cannot be enabled because it would stay unusable.',
      ])
      return
    }
    if (checked) {
      const result = expandHardDependencies([...selected, key], modules)
      const blocked = result.selected.filter((item) => {
        const next = modules.find((row) => row.key === item)
        return next && !selected.includes(item) && !canSelectModule(next, false)
      })
      if (blocked.length) {
        setNotices([
          isAr
            ? 'اعتماد مطلوب غير قابل للتفعيل في هذا النشر.'
            : 'A required dependency cannot become usable in this deployment.',
        ])
        return
      }
      setSelected(result.selected)
      setNotices(result.notices)
      return
    }
    const result = removeModuleWithDependents(selected, modules, key)
    setSelected(result.selected)
    setNotices(result.notices)
  }

  function applyBundle(bundle: ModuleBundle) {
    const result = applyBundleModules(selected, modules, bundle)
    const allowed = result.selected.filter((key) => {
      if (selected.includes(key)) return true
      const module = modules.find((item) => item.key === key)
      return module ? canSelectModule(module, false) : false
    })
    const skipped = result.selected.filter((key) => !allowed.includes(key))
    setSelected(allowed)
    setNotices([
      `Applied ${bundle.label}.`,
      ...result.notices,
      ...skipped.map((key) => {
        const label = modules.find((item) => item.key === key)?.label || key
        return isAr
          ? `${label} لم تُضَف لأنها لن تصبح قابلة للاستخدام.`
          : `${label} was not added because it would stay unusable.`
      }),
    ])
  }

  function addRecommended(key: string) {
    const module = modules.find((item) => item.key === key)
    if (module && !canSelectModule(module, false)) {
      setNotices([
        isAr
          ? 'لا يمكن إضافة هذه التوصية لأنها لن تصبح قابلة للاستخدام.'
          : 'That recommendation cannot be added because it would stay unusable.',
      ])
      return
    }
    const result = expandHardDependencies([...selected, key], modules)
    setSelected(result.selected)
    setNotices(result.notices.length ? result.notices : [`Added ${module?.label || key}.`])
  }

  function discard() {
    setSelected(stored)
    setNotices([])
  }

  async function save() {
    const addedLabels = added.map((key) => modules.find((item) => item.key === key)?.label || key)
    const removedLabels = removed.map((key) => modules.find((item) => item.key === key)?.label || key)
    const approved = await confirm({
      title: isAr ? 'تطبيق تغييرات الوحدات؟' : 'Apply module changes?',
      body: (
        <div className="space-y-2 text-sm">
          <p>
            {isAr
              ? 'سيُحفظ هذا الاختيار في وحدات الشركة ويُكتب في سجل التدقيق الحالي.'
              : 'This selection is saved to company modules and the existing admin audit log.'}
          </p>
          {addedLabels.length ? (
            <p>
              {isAr ? 'إضافة: ' : 'Enable: '}
              {addedLabels.join(', ')}
            </p>
          ) : null}
          {removedLabels.length ? (
            <p>
              {isAr ? 'إزالة: ' : 'Disable: '}
              {removedLabels.join(', ')}
            </p>
          ) : null}
        </div>
      ),
      confirmLabel: isAr ? 'تطبيق' : 'Apply',
      cancelLabel: isAr ? 'إلغاء' : 'Cancel',
      dir: isAr ? 'rtl' : 'ltr',
    })
    if (!approved) return
    setWorking(true)
    try {
      const result = expandHardDependencies(selected, modules)
      const persistable = result.selected.filter((key) => {
        const module = modules.find((item) => item.key === key)
        if (!module) return false
        if (module.configured || module.stored_enabled) return true
        return canSelectModule(module, false)
      })
      setSelected(persistable)
      const skipped = result.selected.filter((key) => !persistable.includes(key))
      const nextNotices = [
        ...result.notices,
        ...skipped.map((key) => {
          const label = modules.find((item) => item.key === key)?.label || key
          return isAr
            ? `${label} لم تُحفظ لأنها لن تصبح قابلة للاستخدام.`
            : `${label} was not saved because it would stay unusable.`
        }),
      ]
      if (nextNotices.length) setNotices(nextNotices)
      await updateCompanyModules(credentials, companyCode, persistable)
      await onChanged()
    } catch (saveError) {
      onError(saveError)
    } finally {
      setWorking(false)
    }
  }

  const filters: Array<{ id: ModuleFilter; en: string; ar: string }> = [
    { id: 'all', en: `All ${summary.total}`, ar: `الكل ${summary.total}` },
    { id: 'on', en: `On ${summary.enabled}`, ar: `مفعّل ${summary.enabled}` },
    { id: 'available', en: `Available ${summary.available}`, ar: `متاح ${summary.available}` },
    { id: 'blocked', en: `Blocked ${summary.blocked}`, ar: `محظور ${summary.blocked}` },
    { id: 'changed', en: `Changed ${added.length + removed.length}`, ar: `معدَّل ${added.length + removed.length}` },
  ]

  return (
    <Card id="classic-modules" data-ownership="module_entitlements" className="pb-[calc(env(safe-area-inset-bottom)+0.5rem)]">
      <CardHeader className="gap-3 space-y-0 pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>{isAr ? 'الوحدات والوصول' : 'Modules & Access'}</CardTitle>
            <p className="mt-1 font-mono text-xs uppercase tracking-[0.08em] text-subtle">{companyCode}</p>
          </div>
          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs text-subtle underline-offset-2 hover:text-text hover:underline"
            aria-expanded={howItWorksOpen}
            onClick={() => setHowItWorksOpen((open) => !open)}
          >
            {isAr ? 'كيف تُعرض الحالة' : 'How state is shown'}
            <ChevronDown className={cn('h-3.5 w-3.5 transition', howItWorksOpen && 'rotate-180')} aria-hidden="true" />
          </button>
        </div>
        {howItWorksOpen ? (
          <p className="max-w-3xl text-xs leading-5 text-subtle">
            {isAr
              ? 'الحالة المعروضة هي الحالة الفعلية للتشغيل. التخزين كمفعّل لا يعني أن الوحدة قابلة للاستخدام.'
              : 'Shown state is runtime truth. A stored entitlement is never shown as enabled when the module would still be unusable.'}
          </p>
        ) : null}
        <p className="text-xs text-subtle" data-testid="last-module-change">
          {lastChange?.at
            ? isAr
              ? `آخر تغيير: ${lastChange.at}${lastChange.actor_email ? ` · ${lastChange.actor_email}` : ''}`
              : `Last change: ${lastChange.at}${lastChange.actor_email ? ` · ${lastChange.actor_email}` : ''}`
            : isAr
              ? 'لا يوجد تطبيق وحدات مسجّل بعد.'
              : 'No module apply recorded yet.'}
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder={isAr ? 'بحث في الوحدات' : 'Search modules'}
            ariaLabel={isAr ? 'بحث في الوحدات' : 'Search modules'}
            className="max-w-none lg:max-w-sm"
          />
          <div className="flex flex-wrap gap-1.5" role="tablist" aria-label={isAr ? 'تصفية الوحدات' : 'Filter modules'}>
            {filters.map((item) => (
              <Button
                key={item.id}
                type="button"
                size="sm"
                variant={filter === item.id ? 'default' : 'ghost'}
                aria-pressed={filter === item.id}
                onClick={() => setFilter(item.id)}
              >
                {isAr ? item.ar : item.en}
              </Button>
            ))}
          </div>
        </div>

        {bundles.length > 0 ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-subtle">
              {isAr ? 'حزم الوحدات' : 'Module bundles'}
            </span>
            {bundles.map((bundle) => (
              <Button
                key={bundle.id}
                type="button"
                size="sm"
                variant="secondary"
                disabled={working}
                title={bundle.description}
                onClick={() => applyBundle(bundle)}
              >
                Apply {bundle.label}
              </Button>
            ))}
          </div>
        ) : null}

        {notices.length > 0 ? (
          <div role="status" className="space-y-1 rounded-2xl border border-amber-200/70 bg-amber-50/70 p-3 text-xs leading-5 text-amber-950">
            {notices.map((notice) => (
              <p key={notice}>{notice}</p>
            ))}
          </div>
        ) : null}

        {recommendations.length > 0 ? (
          <section className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-subtle">
              {isAr ? 'موصى بها مع الاختيار' : 'Recommended with selection'}
            </h3>
            <div className="flex flex-wrap gap-2">
              {recommendations.map((item) => (
                <button
                  key={`${item.from}:${item.key}`}
                  type="button"
                  disabled={working}
                  className="rounded-full border border-line/70 bg-white/70 px-3 py-1.5 text-left text-xs text-text transition hover:border-accent/40"
                  title={item.copy || `${item.fromLabel} recommends ${item.label}`}
                  onClick={() => addRecommended(item.key)}
                >
                  + {item.label}{' '}
                  <span className="text-subtle">for {item.fromLabel}</span>
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {Object.entries(grouped).map(([suite, suiteModules]) => {
          const visible = suiteModules.filter((module) => visibleKeys.has(module.key))
          if (visible.length === 0) return null
          return (
            <fieldset key={suite} className="min-w-0">
              <legend className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-subtle">
                {humanize(suite)}
              </legend>
              <div className="divide-y divide-line/50 overflow-hidden rounded-2xl border border-line/55 bg-white/40">
                {visible.map((module) => {
                  const state = moduleState(module)
                  const isSelected = selected.includes(module.key)
                  const selectable = canSelectModule(module, isSelected)
                  const blockedReason = !isSelected && !selectable ? blockerText(module, locale) : ''
                  const requires = module.depends_on_labels?.length
                    ? module.depends_on_labels
                    : (module.depends_on || []).map(humanize)
                  const extraBlockers = (state.blockers || []).filter((blocker) => {
                    const message = isAr ? blocker.message_ar : blocker.message_en
                    return Boolean(message) && message !== blockedReason
                  })
                  const detailsId = `${module.key}-details`
                  const detailsOpen = Boolean(openDetails[module.key])
                  const hasDetails = Boolean(
                    module.recommendation_copy ||
                      extraBlockers.length ||
                      state.required_permission ||
                      module.audience ||
                      (isSelected && !selectable) ||
                      (module.key === 'employee_app' && employeeAppSelected),
                  )
                  return (
                    <div
                      key={module.key}
                      data-module-key={module.key}
                      className={cn(
                        'px-3 py-2',
                        !selectable && !isSelected && 'bg-[repeating-linear-gradient(-45deg,transparent,transparent_6px,rgba(24,20,15,0.03)_6px,rgba(24,20,15,0.03)_7px)]',
                      )}
                    >
                      <div className="flex min-w-0 items-start gap-3">
                        <input
                          id={`module-${module.key}`}
                          type="checkbox"
                          className="mt-1 h-4 w-4 shrink-0 accent-[#c89445]"
                          checked={isSelected}
                          disabled={working || (!selectable && !isSelected)}
                          onChange={(event) => toggleModule(module.key, event.target.checked)}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                            <label htmlFor={`module-${module.key}`} className="text-sm font-medium">
                              {module.label || humanize(module.key)}
                            </label>
                            <SetupEffectiveStateBanner state={state} locale={locale} compact />
                            {module.key === 'employee_app' && isSelected && !module.platform_available ? (
                              <Badge tone="warning">
                                {isAr ? 'مُخزَّن — بانتظار تفعيل المنصة' : 'Configured, awaiting platform activation'}
                              </Badge>
                            ) : null}
                          </div>
                          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-subtle">
                            {requires.length ? (
                              <span className="text-amber-800">
                                {isAr ? 'يتطلب' : 'Requires'} {requires.join(', ')}
                              </span>
                            ) : (
                              <span>{isAr ? 'بدون اعتماد إلزامي' : 'No hard dependency'}</span>
                            )}
                            {blockedReason ? <span className="text-rose-800">{blockedReason}</span> : null}
                          </p>
                          {hasDetails ? (
                            <div className="mt-1">
                              <button
                                type="button"
                                className="inline-flex items-center gap-1 text-[11px] text-subtle hover:text-text"
                                aria-expanded={detailsOpen}
                                aria-controls={detailsId}
                                onClick={() =>
                                  setOpenDetails((current) => ({ ...current, [module.key]: !current[module.key] }))
                                }
                              >
                                {isAr ? 'التفاصيل' : 'Details'}
                                <ChevronDown className={cn('h-3 w-3 transition', detailsOpen && 'rotate-180')} aria-hidden="true" />
                              </button>
                              {detailsOpen ? (
                                <div id={detailsId} className="mt-1 space-y-1 text-xs leading-5 text-subtle">
                                  {module.audience ? <p>{isAr ? 'الجمهور' : 'Audience'}: {humanize(module.audience)}</p> : null}
                                  {module.recommendation_copy ? <p>{module.recommendation_copy}</p> : null}
                                  {state.required_permission ? (
                                    <p>
                                      {isAr ? 'الصلاحية المطلوبة' : 'Required permission'}: {state.required_permission}
                                    </p>
                                  ) : null}
                                  {extraBlockers.map((blocker) => (
                                    <p key={`${module.key}:${blocker.code}`}>
                                      {isAr ? blocker.message_ar || blocker.code : blocker.message_en || blocker.code}
                                    </p>
                                  ))}
                                </div>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </fieldset>
          )
        })}

        {visibleKeys.size === 0 ? (
          <p className="rounded-2xl border border-dashed border-line p-4 text-center text-sm text-subtle">
            {isAr ? 'لا توجد وحدات تطابق هذا البحث.' : 'No modules match this search or filter.'}
          </p>
        ) : null}

        {employeeAppSelected ? (
          <div className="rounded-2xl border border-sky-200/70 bg-sky-50/40 p-4">
            <h3 className="text-sm font-semibold">
              {isAr ? 'معاينة سطح تطبيق الموظف' : 'Employee App surface preview'}
            </h3>
            <details className="mt-2" open>
            <summary className="cursor-pointer text-xs text-subtle">
              {isAr ? 'إظهار المعاينة' : 'Show preview'}
            </summary>
            <p className="mt-2 text-xs leading-5 text-subtle">
              {employeeAppModule && !employeeAppModule.platform_available
                ? 'Configured, awaiting platform activation. Surfaces below appear when WATHEFNI_EMPLOYEE_APP is ON.'
                : 'Surfaces implied by the currently selected modules.'}
            </p>
            {appSurfaces.length === 0 ? (
              <p className="mt-3 text-xs text-subtle">
                No module surfaces selected yet. Payroll remains HR-dashboard-first for V1.
              </p>
            ) : (
              <ul className="mt-3 space-y-1.5">
                {appSurfaces.map((surface) => (
                  <li key={`${surface.module_key}:${surface.surface_key}`} className="text-xs text-text">
                    {surface.label || humanize(surface.surface_key)}
                    <span className="text-subtle"> · {humanize(surface.module_key)}</span>
                  </li>
                ))}
              </ul>
            )}
            </details>
          </div>
        ) : null}

        {dirty ? (
          <div className="sticky bottom-3 z-20 rounded-2xl border border-line/70 bg-panel/95 p-3 shadow-[0_12px_32px_rgba(24,20,15,0.12)] backdrop-blur-xl">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold">{isAr ? 'مراجعة وتطبيق' : 'Review & Apply'}</p>
                <p className="text-xs text-subtle">
                  {isAr
                    ? `${added.length} إضافة · ${removed.length} إزالة`
                    : `${added.length} to add · ${removed.length} to remove`}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button type="button" size="sm" variant="ghost" disabled={working} onClick={discard}>
                  {isAr ? 'تجاهل' : 'Discard'}
                </Button>
                <Button size="sm" type="button" onClick={() => void save()} disabled={working}>
                  {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {isAr ? 'حفظ الوحدات' : 'Save modules'}
                </Button>
              </div>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
