import { useEffect, useMemo, useState } from 'react'
import { Check, ChevronLeft, ChevronRight, Loader2, Save } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/field'
import { cn } from '@/lib/utils'

import {
  createWizardDraft,
  getProviders,
  getWizardDraft,
  getWizardSteps,
  saveWizardDraft,
  validateWizardStep,
} from './api'
import type { SetupCredentials } from './types'

const DRAFT_KEY = 'wathefni_setup_wizard_draft_id'

type Step = { step: number; key: string; label: string }
type ModuleOption = { key: string; label: string; suite: string; depends_on: string[] }
type Provider = { provider_key: string; label: string; support_tier: string; selectable: boolean; notes: string }

const copy = {
  en: {
    title: 'Company onboarding',
    subtitle: 'Create and prepare a company step by step. Selecting a module never makes it live.',
    save: 'Saved',
    next: 'Continue',
    back: 'Back',
    resume: 'Resume draft',
    blockers: 'What still needs attention',
    unavailable: 'Unavailable',
    backendNote: 'Candidate Knowledge and Talent Pool stay behind Candidates. They are not separate products.',
  },
  ar: {
    title: 'تهيئة الشركة',
    subtitle: 'أنشئ الشركة وجهّزها خطوة بخطوة. اختيار الوحدة لا يجعلها مباشرة.',
    save: 'تم الحفظ',
    next: 'متابعة',
    back: 'رجوع',
    resume: 'استئناف المسودة',
    blockers: 'ما يحتاج إلى إجراء',
    unavailable: 'غير متاح',
    backendNote: 'معرفة المرشحين ومجمع المواهب تبقيان ضمن المرشحين وليستا منتجين منفصلين.',
  },
} as const

export function OnboardingWizard({
  credentials,
  locale = 'en',
  onOpenControl,
}: {
  credentials: SetupCredentials
  locale?: 'en' | 'ar'
  onOpenControl?: (companyCode: string) => void
}) {
  const t = copy[locale]
  const [steps, setSteps] = useState<Step[]>([])
  const [modules, setModules] = useState<ModuleOption[]>([])
  const [providers, setProviders] = useState<Provider[]>([])
  const [draftId, setDraftId] = useState(sessionStorage.getItem(DRAFT_KEY) || '')
  const [step, setStep] = useState(1)
  const [body, setBody] = useState<Record<string, unknown>>({})
  const [blockers, setBlockers] = useState<Array<{ code: string; remediation: string }>>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [autosaved, setAutosaved] = useState(false)

  const dir = locale === 'ar' ? 'rtl' : 'ltr'
  const progress = useMemo(() => Math.round((step / Math.max(steps.length, 1)) * 100), [step, steps.length])

  useEffect(() => {
    void (async () => {
      try {
        const meta = await getWizardSteps(credentials, locale)
        setSteps(meta.steps || [])
        setModules(meta.purchasable_modules || [])
        const prov = await getProviders(credentials)
        setProviders(prov.providers || [])
        if (draftId) {
          const existing = await getWizardDraft(credentials, draftId)
          setStep(Number(existing.draft.current_step || 1))
          setBody((existing.draft.draft_json as Record<string, unknown>) || {})
        } else {
          const created = await createWizardDraft(credentials, {
            company_code: 'WATHEFNI',
            locale,
            idempotency_key: `wizard-ui-${credentials.phone}`,
          })
          sessionStorage.setItem(DRAFT_KEY, created.draft_id)
          setDraftId(created.draft_id)
          setBody(created.draft_json || {})
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not load wizard')
      }
    })()
  }, [credentials, draftId, locale])

  async function autosave(nextBody: Record<string, unknown>, nextStep = step) {
    if (!draftId) return
    setSaving(true)
    setError('')
    try {
      const saved = await saveWizardDraft(credentials, draftId, { patch: nextBody, current_step: nextStep })
      setBody(saved.draft_json || nextBody)
      setAutosaved(true)
      window.setTimeout(() => setAutosaved(false), 1200)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Autosave failed')
    } finally {
      setSaving(false)
    }
  }

  async function goNext() {
    if (!draftId) return
    const validation = await validateWizardStep(credentials, draftId, step)
    setBlockers(validation.blockers || [])
    if (!validation.ok) return
    const next = Math.min(step + 1, 10)
    await autosave(body, next)
    setStep(next)
  }

  async function goBack() {
    const prev = Math.max(step - 1, 1)
    await autosave(body, prev)
    setStep(prev)
  }

  const company = (body.company as Record<string, unknown>) || {}
  const purchased = Array.isArray(body.modules_purchased) ? (body.modules_purchased as string[]) : []

  return (
    <div dir={dir} className="space-y-5" data-wizard-step={step} data-wizard-key={steps.find((s) => s.step === step)?.key}>
      <Card>
        <CardHeader className="space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle>{t.title}</CardTitle>
              <CardDescription>{t.subtitle}</CardDescription>
            </div>
            <div className="flex items-center gap-2">
              {autosaved ? <Badge tone="success">{t.save}</Badge> : null}
              {saving ? <Loader2 className="h-4 w-4 animate-spin text-subtle" /> : <Save className="h-4 w-4 text-subtle" />}
            </div>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-line/50">
            <div className="h-full rounded-full bg-text transition-all" style={{ width: `${progress}%` }} />
          </div>
          <div className="flex flex-wrap gap-2">
            {steps.map((item) => (
              <button
                key={item.step}
                type="button"
                className={cn(
                  'rounded-full border px-3 py-1 text-xs',
                  item.step === step ? 'border-text bg-text text-white' : item.step < step ? 'border-line bg-panel' : 'border-line/70 text-subtle',
                )}
                onClick={() => void autosave(body, item.step).then(() => setStep(item.step))}
              >
                {item.step}. {item.label}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          {step === 1 ? (
            <div className="grid gap-3 md:grid-cols-2">
              <label className="space-y-1 text-sm">
                <span>Company name</span>
                <Input
                  value={String(company.display_name || '')}
                  onChange={(e) => {
                    const next = { ...body, company: { ...company, display_name: e.target.value, company_code: 'WATHEFNI' } }
                    setBody(next)
                    void autosave(next)
                  }}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span>Timezone</span>
                <Input
                  value={String(company.timezone || 'Asia/Kuwait')}
                  onChange={(e) => {
                    const next = { ...body, company: { ...company, timezone: e.target.value } }
                    setBody(next)
                    void autosave(next)
                  }}
                />
              </label>
            </div>
          ) : null}

          {step === 2 ? (
            <div className="space-y-3">
              <p className="text-sm text-subtle">{t.backendNote}</p>
              <div className="grid gap-2 md:grid-cols-2">
                {modules.map((mod) => {
                  const checked = purchased.includes(mod.key)
                  return (
                    <label key={mod.key} className="flex items-start gap-3 rounded-2xl border border-line/70 p-3">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          const nextPurchased = checked
                            ? purchased.filter((k) => k !== mod.key)
                            : [...purchased, mod.key]
                          const next = { ...body, modules_purchased: nextPurchased, modules_live: [] }
                          setBody(next)
                          void autosave(next)
                        }}
                      />
                      <span>
                        <span className="block font-medium">{mod.label}</span>
                        <span className="block text-xs text-subtle">{mod.suite}</span>
                        {mod.depends_on.length ? (
                          <span className="block text-xs text-subtle">Requires: {mod.depends_on.join(', ')}</span>
                        ) : null}
                      </span>
                    </label>
                  )
                })}
              </div>
            </div>
          ) : null}

          {step === 3 ? (
            <p className="text-sm text-subtle">Branches, departments, teams, and cost centers are stored in the company structure draft and do not change live navigation until published.</p>
          ) : null}

          {step === 4 ? (
            <p className="text-sm text-subtle">Administrators and roles stay on current OctoHR fixed-role behavior until a custom-role canary proves parity.</p>
          ) : null}

          {step === 5 || step === 6 ? (
            <p className="text-sm text-subtle">Module and policy drafts validate before publish. Live activation is a separate approval after readiness passes.</p>
          ) : null}

          {step === 7 ? (
            <div className="grid gap-2 md:grid-cols-2">
              {providers.map((p) => (
                <div key={p.provider_key} className={cn('rounded-2xl border p-3', p.selectable ? 'border-line/70' : 'border-line/40 opacity-60')}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium">{p.label}</p>
                    {!p.selectable ? <Badge tone="muted">{t.unavailable}</Badge> : <Badge tone="success">{p.support_tier}</Badge>}
                  </div>
                  <p className="mt-1 text-xs text-subtle">{p.notes}</p>
                </div>
              ))}
            </div>
          ) : null}

          {step === 8 ? (
            <p className="text-sm text-subtle">Imports support mapping, validation, duplicate detection, preview, and dry run. No external-company import runs in this wave.</p>
          ) : null}

          {step === 9 ? (
            <p className="text-sm text-subtle">Readiness must pass every mandatory check. Selecting a module never marks it Ready or Live.</p>
          ) : null}

          {step === 10 ? (
            <div className="space-y-3">
              <p className="text-sm">Review purchased modules, integrations, and readiness before activation.</p>
              <div className="rounded-2xl border border-line/70 p-3 text-sm">
                <p>Purchased: {purchased.join(', ') || '—'}</p>
                <p>Live from checkbox: never</p>
              </div>
              {onOpenControl ? (
                <Button onClick={() => onOpenControl(String(company.company_code || 'WATHEFNI'))}>Open company control</Button>
              ) : null}
            </div>
          ) : null}

          {blockers.length ? (
            <div className="rounded-2xl border border-amber-500/40 bg-amber-500/5 p-3">
              <p className="mb-2 text-sm font-medium">{t.blockers}</p>
              <ul className="space-y-1 text-sm">
                {blockers.map((b) => (
                  <li key={b.code}>• {b.remediation}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="flex items-center justify-between gap-3 pt-2">
            <Button variant="ghost" disabled={step <= 1} onClick={() => void goBack()}>
              <ChevronLeft className="h-4 w-4" />
              {t.back}
            </Button>
            <Button onClick={() => void goNext()} disabled={step >= 10}>
              {t.next}
              {step < 10 ? <ChevronRight className="h-4 w-4" /> : <Check className="h-4 w-4" />}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
