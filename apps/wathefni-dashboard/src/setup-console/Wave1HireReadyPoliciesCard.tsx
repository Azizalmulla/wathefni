import { useCallback, useEffect, useState } from 'react'
import { Loader2, Save } from 'lucide-react'

import { ConfigureInOpsLink } from '@/components/ConfigureInSetupBanner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/field'
import { dashboardPageHref } from '@/lib/setupConsoleOwnership'

import { getModulePolicies, updateModulePolicy, type ModulePoliciesResponse, type ModulePolicyPayload } from './api'
import type { SetupCredentials } from './types'

type Wave1Id = 'requisitions' | 'preboarding' | 'probation' | 'onboarding_auto_start'

const META: Record<Wave1Id, { titleEn: string; titleAr: string; opsPage: string; moduleKeys: string[] }> = {
  requisitions: {
    titleEn: 'Requisitions & job gate',
    titleAr: 'طلبات التوظيف وبوابة الوظائف',
    opsPage: 'requisitions',
    moduleKeys: ['requisitions'],
  },
  preboarding: {
    titleEn: 'Preboarding',
    titleAr: 'التهيئة قبل الالتحاق',
    opsPage: 'preboarding',
    moduleKeys: ['preboarding'],
  },
  probation: {
    titleEn: 'Probation',
    titleAr: 'فترة التجربة',
    opsPage: 'probation',
    moduleKeys: ['probation'],
  },
  onboarding_auto_start: {
    titleEn: 'Hire → Onboarding auto-start',
    titleAr: 'بدء التهيئة تلقائياً عند التعيين',
    opsPage: 'onboarding',
    moduleKeys: ['onboarding'],
  },
}

function Wave1PolicyRow({
  id,
  policy,
  locale,
  credentials,
  companyCode,
  reason,
  onReason,
  onSaved,
  onError,
}: {
  id: Wave1Id
  policy: ModulePolicyPayload
  locale: 'en' | 'ar'
  credentials: SetupCredentials
  companyCode: string
  reason: string
  onReason: (v: string) => void
  onSaved: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const isAr = locale === 'ar'
  const meta = META[id]
  const inactive = Boolean(policy.inactive) || !policy.module_enabled
  const [working, setWorking] = useState(false)
  const [required, setRequired] = useState<Record<string, unknown>>(policy.required || {})
  const [optional, setOptional] = useState<Record<string, unknown>>(policy.optional || {})

  useEffect(() => {
    setRequired(policy.required || {})
    setOptional(policy.optional || {})
  }, [policy])

  async function save() {
    if (!reason.trim()) {
      onError(new Error(isAr ? 'سبب التدقيق مطلوب' : 'Audit reason is required'))
      return
    }
    setWorking(true)
    try {
      await updateModulePolicy(credentials, companyCode, id, {
        reason: reason.trim(),
        required,
        optional,
      })
      await onSaved()
    } catch (error) {
      onError(error)
    } finally {
      setWorking(false)
    }
  }

  return (
    <div
      id={`classic-module-${id}`}
      className="rounded-xl border border-border/70 p-4"
      data-wave1-policy={id}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-medium">{isAr ? meta.titleAr : meta.titleEn}</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            {isAr ? policy.summary_ar || policy.summary_en : policy.summary_en}
          </p>
        </div>
        <Badge tone={inactive ? 'muted' : 'success'}>
          {inactive ? (isAr ? 'متوقف' : 'Inactive') : isAr ? 'جاهز' : 'Ready'}
        </Badge>
      </div>

      {!inactive ? (
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {id === 'requisitions' ? (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={Boolean(required.jobs_require_approved_requisition)}
                onChange={(e) =>
                  setRequired((r) => ({ ...r, jobs_require_approved_requisition: e.target.checked }))
                }
              />
              {isAr ? 'يتطلب نشر الوظيفة طلب توظيف معتمد' : 'Jobs require approved requisition'}
            </label>
          ) : null}
          {id === 'preboarding' ? (
            <>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={Boolean(required.auto_create_on_offer_accept)}
                  onChange={(e) =>
                    setRequired((r) => ({ ...r, auto_create_on_offer_accept: e.target.checked }))
                  }
                />
                {isAr ? 'إنشاء تلقائي عند قبول العرض' : 'Auto-create on offer accept'}
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={Boolean(required.required_for_ready_mark)}
                  onChange={(e) =>
                    setRequired((r) => ({ ...r, required_for_ready_mark: e.target.checked }))
                  }
                />
                {isAr ? 'المطلوب يمنع حالة الجاهزية' : 'Required items block ready'}
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={Boolean(optional.handoff_onboarding_enabled)}
                  onChange={(e) =>
                    setOptional((o) => ({ ...o, handoff_onboarding_enabled: e.target.checked }))
                  }
                />
                {isAr ? 'تسليم إلى التهيئة' : 'Handoff to onboarding'}
              </label>
            </>
          ) : null}
          {id === 'probation' ? (
            <>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={Boolean(required.auto_plan_on_hire)}
                  onChange={(e) => setRequired((r) => ({ ...r, auto_plan_on_hire: e.target.checked }))}
                />
                {isAr ? 'تخطيط تلقائي عند التعيين' : 'Auto-plan on hire'}
              </label>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">
                  {isAr ? 'أيام التجربة الافتراضية' : 'Default probation days'}
                </label>
                <Input
                  value={String(required.default_probation_days ?? 90)}
                  onChange={(e) =>
                    setRequired((r) => ({ ...r, default_probation_days: Number(e.target.value) || 90 }))
                  }
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">
                  {isAr ? 'وضع البداية' : 'Start mode'}
                </label>
                <Select
                  value={String(required.start_mode || 'hire_date')}
                  onChange={(e) => setRequired((r) => ({ ...r, start_mode: e.target.value }))}
                >
                  <option value="hire_date">{isAr ? 'تاريخ التعيين' : 'Hire date'}</option>
                  <option value="onboarding_complete">
                    {isAr ? 'اكتمال التهيئة' : 'Onboarding complete'}
                  </option>
                </Select>
              </div>
            </>
          ) : null}
          {id === 'onboarding_auto_start' ? (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={Boolean(required.auto_start_on_hire)}
                onChange={(e) => setRequired((r) => ({ ...r, auto_start_on_hire: e.target.checked }))}
              />
              {isAr ? 'بدء التهيئة تلقائياً عند التعيين' : 'Auto-start onboarding on hire'}
            </label>
          ) : null}
        </div>
      ) : (
        <p className="mt-2 text-xs text-muted-foreground">
          {isAr
            ? 'فعّل الوحدة من «ما تستخدمه الشركة» قبل ضبط السياسة.'
            : 'Enable the module under What this company uses before editing policy.'}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <ConfigureInOpsLink
          href={dashboardPageHref(meta.opsPage)}
          label={isAr ? 'فتح التشغيل' : 'Open ops'}
        />
        {!inactive ? (
          <Button size="sm" disabled={working} onClick={() => void save()}>
            {working ? <Loader2 className="me-1 h-3.5 w-3.5 animate-spin" /> : <Save className="me-1 h-3.5 w-3.5" />}
            {isAr ? 'حفظ' : 'Save'}
          </Button>
        ) : null}
      </div>
      {id === 'requisitions' ? (
        <p className="mt-2 text-[11px] text-muted-foreground">
          {isAr
            ? 'الموجة ١: موافقة بخطوة واحدة مع فصل صلاحيات المنشئ. التفويض متعدد الخطوات عبر منصة الموافقات لاحقاً.'
            : 'Wave 1: single-step SoD approval. Platform N-step/delegation bind later.'}
        </p>
      ) : null}
    </div>
  )
}

export function Wave1HireReadyPoliciesCard({
  credentials,
  companyCode,
  locale = 'en',
  onError,
}: {
  credentials: SetupCredentials
  companyCode: string
  locale?: 'en' | 'ar'
  onError: (error: unknown) => void
}) {
  const isAr = locale === 'ar'
  const [loading, setLoading] = useState(true)
  const [reason, setReason] = useState('')
  const [policies, setPolicies] = useState<ModulePoliciesResponse | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setPolicies(await getModulePolicies(credentials, companyCode))
    } catch (error) {
      onError(error)
    } finally {
      setLoading(false)
    }
  }, [companyCode, credentials, onError])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <Card id="classic-wave1-hire-ready" data-ownership="wave1_hire_ready_policies" data-phase="wave1" dir={isAr ? 'rtl' : 'ltr'}>
      <CardHeader>
        <CardTitle>{isAr ? 'سياسات التوظيف → الجاهزية' : 'Hire → Ready policies'}</CardTitle>
        <CardDescription>
          {isAr
            ? 'ضبط بوابة الطلبات، التهيئة قبل الالتحاق، التجربة، وبدء التهيئة — من وحدة التحكم وليس بمتغيرات البيئة فقط.'
            : 'Configure requisitions gate, preboarding, probation, and hire→onboarding — from Setup Console, not env-only.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <label className="mb-1 block text-xs text-muted-foreground">
            {isAr ? 'سبب التدقيق (مطلوب للحفظ)' : 'Audit reason (required to save)'}
          </label>
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> …
          </div>
        ) : (
          (['requisitions', 'preboarding', 'probation', 'onboarding_auto_start'] as Wave1Id[]).map((id) => {
            const policy = (policies as Record<string, ModulePolicyPayload> | null)?.[id]
            if (!policy) return null
            return (
              <Wave1PolicyRow
                key={id}
                id={id}
                policy={policy}
                locale={locale}
                credentials={credentials}
                companyCode={companyCode}
                reason={reason}
                onReason={setReason}
                onSaved={load}
                onError={onError}
              />
            )
          })
        )}
      </CardContent>
    </Card>
  )
}
