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

export function Wave6WorkforcePlanningPoliciesCard({
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
      setPolicy(data.wave6?.modules?.workforce_planning?.policy || null)
      setEffective(data.wave6?.modules?.workforce_planning?.effective_state || null)
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
      await updateModulePolicy(credentials, companyCode, 'wave6_workforce_planning', {
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
    <Card id="classic-wave6-workforce-planning" data-ownership="wave6_workforce_planning_policies">
      <CardHeader>
        <CardTitle>
          {isAr ? 'تخطيط القوى العاملة (الموجة 6 / C7)' : 'Workforce Planning (Wave 6 / C7)'}
        </CardTitle>
        <CardDescription>
          {isAr
            ? 'أساس → خطة → طلب → سيناريو → افتراضات → تكلفة → مقارنة → اعتماد → تسليم صريح. الفعلي ≠ الخطة ≠ السيناريو. JA إلزامي.'
            : 'Baseline → plan → demand → scenario → assumptions → cost → compare → approve → explicit handoff. Actual ≠ plan ≠ scenario. JA hard.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{isAr ? 'إعداد يملك السياسة' : 'Setup owns policy'}</Badge>
          <Badge variant="outline">{isAr ? 'وحدة تجارية' : 'Commercial module'}</Badge>
          <Badge variant="outline">{isAr ? 'JA إلزامي' : 'JA hard'}</Badge>
          <Badge variant="outline">{isAr ? 'ليس رأس مال فعلي' : 'Not actual HC'}</Badge>
          <Badge variant="outline">{isAr ? 'اعتماد ≠ تنفيذ' : 'Approved ≠ executed'}</Badge>
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
              <div className="text-sm font-medium">{isAr ? 'تخطيط القوى العاملة' : 'Workforce Planning'}</div>
              <div className="text-xs text-muted-foreground">
                {effective?.usable
                  ? isAr
                    ? 'مفعّل وقابل للاستخدام'
                    : 'Enabled and usable'
                  : isAr
                    ? 'متوقف أو غير متاح — الخطط التاريخية تُحفظ'
                    : 'Off or unavailable — historical plans retained'}
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
