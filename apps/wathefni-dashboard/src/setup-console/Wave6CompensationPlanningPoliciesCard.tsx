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

export function Wave6CompensationPlanningPoliciesCard({
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
  const [policy, setPolicy] = useState<Record<string, unknown> | null>(null)
  const [effective, setEffective] = useState<SetupEffectiveState | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const data = (await getModulePolicies(credentials, companyCode)) as ModulePoliciesResponse & {
        wave6?: { modules?: Record<string, any>; honesty?: Record<string, unknown> }
      }
      setPolicy(data.wave6?.modules?.comp_planning?.policy || null)
      setEffective(data.wave6?.modules?.comp_planning?.effective_state || null)
    } catch (error) {
      onError(error)
    } finally {
      setLoading(false)
    }
  }, [companyCode, credentials, onError])

  useEffect(() => {
    void reload()
  }, [reload])

  async function toggle() {
    if (!reason.trim()) {
      onError(new Error(isAr ? 'سبب التدقيق مطلوب' : 'Audit reason is required'))
      return
    }
    const next = !boolVal(policy?.enabled)
    setSaving(true)
    try {
      await updateModulePolicy(credentials, companyCode, 'wave6_comp_planning', {
        reason: reason.trim(),
        required: { enabled: next },
      })
      await reload()
    } catch (error) {
      await reload()
      onError(error)
    } finally {
      setSaving(false)
    }
  }

  const on = boolVal(policy?.enabled)
  const enableBlocked = !on && !canEnableFromState(effective)

  return (
    <Card id="classic-wave6-comp-planning" data-ownership="wave6_comp_planning_policies">
      <CardHeader>
        <CardTitle>
          {isAr ? 'تخطيط التعويضات (الموجة 6 / C6)' : 'Compensation Planning (Wave 6 / C6)'}
        </CardTitle>
        <CardDescription>
          {isAr
            ? 'دورة → أهلية مجمّدة → ميزانيات → نطاقات (JA) → توصيات → معايرة → اعتماد → نهائي → تسليم صريح. ليس رواتب. الاعتماد ≠ تطبيق الراتب.'
            : 'Cycle → frozen eligibility → budgets → JA-linked bands → recommendations → calibration → approval → finalize → explicit handoff. Not Payroll. Approved ≠ salary applied.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{isAr ? 'إعداد يملك السياسة' : 'Setup owns policy'}</Badge>
          <Badge variant="outline">{isAr ? 'وحدة تجارية' : 'Commercial module'}</Badge>
          <Badge variant="outline">{isAr ? 'JA إلزامي' : 'JA hard'}</Badge>
          <Badge variant="outline">{isAr ? 'ليس رواتب' : 'Not payroll'}</Badge>
          <Badge variant="outline">{isAr ? 'نهائي ≠ مطبّق' : 'Finalized ≠ applied'}</Badge>
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
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/70 px-3 py-3">
            <div>
              <div className="text-sm font-medium">{isAr ? 'تخطيط التعويضات' : 'Compensation Planning'}</div>
              <div className="text-xs text-muted-foreground">
                {effective?.usable
                  ? isAr
                    ? 'مفعّل وقابل للاستخدام'
                    : 'Enabled and usable'
                  : isAr
                    ? 'متوقف أو غير متاح — الدورات التاريخية تُحفظ'
                    : 'Off or unavailable — historical cycles retained'}
              </div>
            </div>
            <Button type="button" variant={on ? 'secondary' : 'default'} disabled={saving || enableBlocked} onClick={() => void toggle()}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {on ? (isAr ? 'إيقاف' : 'Disable') : isAr ? 'تفعيل' : 'Enable'}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
