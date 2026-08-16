import { useCallback, useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/field'

import { getModulePolicies, updateModulePolicy, type ModulePoliciesResponse } from './api'
import { SetupEffectiveStateBanner, canEnableFromState, type SetupEffectiveState } from './SetupEffectiveStateBanner'
import type { SetupCredentials } from './types'

function boolVal(v: unknown): boolean {
  return v === true || v === 'true' || v === 1 || v === '1'
}

export function Wave5HrIntelligencePoliciesCard({
  credentials,
  companyCode,
  locale,
  onError,
}: {
  credentials: SetupCredentials
  companyCode: string
  locale: 'en' | 'ar'
  onError: (error: unknown) => void
}) {
  const isAr = locale === 'ar'
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [reason, setReason] = useState('')
  const [cohort, setCohort] = useState('5')
  const [fiscal, setFiscal] = useState('1')
  const [policy, setPolicy] = useState<Record<string, unknown> | null>(null)
  const [effective, setEffective] = useState<SetupEffectiveState | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const data = (await getModulePolicies(credentials, companyCode)) as ModulePoliciesResponse & {
        wave5?: { modules?: Record<string, any> }
      }
      const mod = data.wave5?.modules?.analytics
      setPolicy(mod?.policy || null)
      setEffective(mod?.effective_state || null)
      setCohort(String(mod?.policy?.min_cohort_n || 5))
      setFiscal(String(mod?.policy?.fiscal_year_start_month || 1))
    } catch (error) {
      onError(error)
    } finally {
      setLoading(false)
    }
  }, [companyCode, credentials, onError])

  useEffect(() => {
    void reload()
  }, [reload])

  async function save(next: Record<string, unknown>) {
    if (!reason.trim()) {
      onError(new Error(isAr ? 'سبب التدقيق مطلوب' : 'Audit reason is required'))
      return
    }
    const previous = policy
    setSaving(true)
    try {
      await updateModulePolicy(credentials, companyCode, 'wave5_analytics', {
        reason: reason.trim(),
        required: next,
      })
      await reload()
    } catch (error) {
      setPolicy(previous)
      onError(error)
    } finally {
      setSaving(false)
    }
  }

  const on = boolVal(policy?.enabled)
  const enableBlocked = !canEnableFromState(effective) && !on

  return (
    <Card id="classic-wave5-hr-intelligence" data-ownership="wave5_hr_intelligence_policies" dir={isAr ? 'rtl' : 'ltr'} lang={locale}>
      <CardHeader>
        <CardTitle>{isAr ? 'ذكاء الموارد البشرية (الموجة 5)' : 'HR Intelligence (Wave 5)'}</CardTitle>
        <CardDescription>
          {isAr
            ? 'سياسة الشركة للذكاء: التفعيل، عتبة الخصوصية، السنة المالية، التصدير. ليست محرك تحليلات ثانياً.'
            : 'Company Intelligence policy: enablement, privacy threshold, fiscal year, export. Not a second analytics engine.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{isAr ? 'إعداد يملك السياسة' : 'Setup owns policy'}</Badge>
          <Badge variant="outline">{isAr ? 'وحدة تجارية analytics' : 'Commercial SKU analytics'}</Badge>
          <Badge variant="outline">{isAr ? 'المقيّم مجمّد' : 'Frozen evaluator'}</Badge>
        </div>
        <SetupEffectiveStateBanner state={effective} locale={locale} />
        <Input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={isAr ? 'سبب التدقيق' : 'Audit reason'}
          aria-label={isAr ? 'سبب التدقيق' : 'Audit reason'}
        />
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {isAr ? 'جاري التحميل…' : 'Loading…'}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/70 px-3 py-3">
              <div>
                <div className="text-sm font-medium">{isAr ? 'ذكاء الموارد البشرية' : 'HR Intelligence'}</div>
                <div className="text-xs text-muted-foreground">
                  {isAr ? 'التعطيل يحفظ السجل ولا يحذف التعريفات.' : 'Disable preserves history and does not delete definitions.'}
                </div>
              </div>
              <Button
                type="button"
                variant={on ? 'secondary' : 'default'}
                disabled={saving || enableBlocked}
                onClick={() => void save({ enabled: !on })}
              >
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {on ? (isAr ? 'إيقاف' : 'Disable') : isAr ? 'تفعيل' : 'Enable'}
              </Button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-sm">
                <span>{isAr ? 'حد الخصوصية (min cohort)' : 'Privacy threshold (min cohort)'}</span>
                <Input
                  value={cohort}
                  onChange={(e) => setCohort(e.target.value)}
                  inputMode="numeric"
                  aria-label={isAr ? 'حد الخصوصية' : 'Privacy threshold'}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span>{isAr ? 'بداية السنة المالية (شهر)' : 'Fiscal year start (month)'}</span>
                <Input
                  value={fiscal}
                  onChange={(e) => setFiscal(e.target.value)}
                  inputMode="numeric"
                  aria-label={isAr ? 'بداية السنة المالية' : 'Fiscal year start'}
                />
              </label>
            </div>
            <Button
              type="button"
              variant="secondary"
              disabled={saving || !on}
              onClick={() =>
                void save({
                  min_cohort_n: Number(cohort) || 5,
                  fiscal_year_start_month: Number(fiscal) || 1,
                })
              }
            >
              {isAr ? 'حفظ سياسة الخصوصية/الفترة' : 'Save privacy / period policy'}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
