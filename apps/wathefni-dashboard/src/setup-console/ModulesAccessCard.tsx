import { useMemo, useState } from 'react'
import { Loader2, Save } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
import type { AvailableModule, ModuleBundle, SetupCredentials } from './types'

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

export function ModulesAccessCard({
  credentials,
  companyCode,
  locale = 'en',
  modules,
  bundles,
  onChanged,
  onError,
}: {
  credentials: SetupCredentials
  companyCode: string
  locale?: 'en' | 'ar'
  modules: AvailableModule[]
  bundles: ModuleBundle[]
  onChanged: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const isAr = locale === 'ar'
  const [selected, setSelected] = useState(() =>
    modules.filter((module) => module.configured || module.stored_enabled).map((module) => module.key),
  )
  const [notices, setNotices] = useState<string[]>([])
  const [working, setWorking] = useState(false)

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

  async function save() {
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

  return (
    <Card id="classic-modules" data-ownership="module_entitlements">
      <CardHeader>
        <CardTitle>{isAr ? 'الوحدات والوصول' : 'Modules & Access'}</CardTitle>
        <CardDescription>
          {isAr
            ? 'الحالة المعروضة هي الحالة الفعلية للتشغيل. التخزين كمفعّل لا يعني أن الوحدة قابلة للاستخدام.'
            : 'Shown state is runtime truth. A stored entitlement is never shown as enabled when the module would still be unusable.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {bundles.length > 0 ? (
          <section className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-subtle">
              {isAr ? 'حزم الوحدات' : 'Module bundles'}
            </h3>
            <div className="flex flex-wrap gap-2">
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
          </section>
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
                  + {item.label}
                  <span className="ml-1 text-subtle">for {item.fromLabel}</span>
                </button>
              ))}
            </div>
            <p className="text-[11px] leading-4 text-subtle">
              {isAr
                ? 'التوصيات اختيارية ولا تُفرَض عند الحفظ.'
                : 'Recommendations are optional. You can leave them off or remove them after applying a bundle.'}
            </p>
          </section>
        ) : null}

        {Object.entries(grouped).map(([suite, suiteModules]) => (
          <fieldset key={suite}>
            <legend className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-subtle">
              {humanize(suite)}
            </legend>
            <div className="space-y-2">
              {suiteModules.map((module) => {
                const state = moduleState(module)
                const isSelected = selected.includes(module.key)
                const selectable = canSelectModule(module, isSelected)
                const bannerDetail = isAr ? state.deployment?.message_ar : state.deployment?.message_en
                const extraBlockers = (state.blockers || []).filter((blocker) => {
                  const message = isAr ? blocker.message_ar : blocker.message_en
                  return Boolean(message) && message !== bannerDetail
                })
                return (
                  <label
                    key={module.key}
                    className={cn(
                      'flex items-start justify-between gap-4 rounded-2xl border border-line/55 bg-white/45 p-3.5',
                      !selectable && !isSelected && 'border-dashed opacity-90',
                    )}
                  >
                    <span className="flex min-w-0 items-start gap-3">
                      <input
                        type="checkbox"
                        className="mt-1 h-4 w-4 accent-[#c89445]"
                        checked={isSelected}
                        disabled={working || (!selectable && !isSelected)}
                        onChange={(event) => toggleModule(module.key, event.target.checked)}
                      />
                      <span>
                        <span className="block text-sm font-medium">{module.label || humanize(module.key)}</span>
                        <span className="mt-1 block text-xs text-subtle">
                          {module.audience ? `Audience: ${humanize(module.audience)}` : module.key}
                        </span>
                        {module.depends_on?.length ? (
                          <span className="mt-1 block text-xs text-amber-800">
                            Requires {(module.depends_on_labels || module.depends_on).join(', ')}
                          </span>
                        ) : null}
                        {module.recommendation_copy ? (
                          <span className="mt-1 block text-xs text-subtle">{module.recommendation_copy}</span>
                        ) : null}
                        {state.required_permission ? (
                          <span className="mt-1 block text-xs text-subtle">
                            {isAr ? 'الصلاحية المطلوبة' : 'Required permission'}: {state.required_permission}
                          </span>
                        ) : null}
                        <div className="mt-2">
                          <SetupEffectiveStateBanner state={state} locale={locale} />
                        </div>
                        {extraBlockers.length > 0 ? (
                          <ul className="mt-1 space-y-0.5 text-xs text-subtle">
                            {extraBlockers.map((blocker) => (
                              <li key={`${module.key}:${blocker.code}`}>
                                {isAr ? blocker.message_ar || blocker.code : blocker.message_en || blocker.code}
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </span>
                    </span>
                    <span className="flex shrink-0 flex-wrap justify-end gap-1.5">
                      {module.key === 'employee_app' && isSelected && !module.platform_available ? (
                        <Badge tone="warning">
                          {isAr ? 'مُخزَّن — بانتظار تفعيل المنصة' : 'Configured, awaiting platform activation'}
                        </Badge>
                      ) : null}
                    </span>
                  </label>
                )
              })}
            </div>
          </fieldset>
        ))}

        {employeeAppSelected ? (
          <section className="rounded-2xl border border-sky-200/70 bg-sky-50/40 p-4">
            <h3 className="text-sm font-semibold">{isAr ? 'معاينة سطح تطبيق الموظف' : 'Employee App surface preview'}</h3>
            <p className="mt-1 text-xs leading-5 text-subtle">
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
          </section>
        ) : null}

        <div className="flex justify-end">
          <Button size="sm" type="button" onClick={() => void save()} disabled={working}>
            {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {isAr ? 'حفظ الوحدات' : 'Save modules'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
