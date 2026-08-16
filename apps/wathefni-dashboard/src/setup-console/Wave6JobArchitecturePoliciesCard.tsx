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

export function Wave6JobArchitecturePoliciesCard({
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
      setPolicy(data.wave6?.modules?.job_architecture?.policy || null)
      setEffective(data.wave6?.modules?.job_architecture?.effective_state || null)
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
      await updateModulePolicy(credentials, companyCode, 'wave6_job_architecture', {
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
    <Card id="classic-wave6-job-architecture" data-ownership="wave6_job_architecture_policies">
      <CardHeader>
        <CardTitle>{isAr ? 'هيكل الوظائف (الموجة 6 / C1)' : 'Job Architecture (Wave 6 / C1)'}</CardTitle>
        <CardDescription>
          {isAr
            ? 'قدرة منصّة مشتركة (ليست منتجاً تجارياً منفصلاً الآن): العائلة ← الوظيفة ← الملف الوظيفي ← الدرجة ← المستوى ← مسارات التقدّم. الإعداد يملك التأليف؛ لا نطاقات رواتب هنا.'
            : 'Shared platform capability (not a separate customer SKU for now): family → function → job profile → grade → level → career edges. Setup owns authoring; salary bands stay out of C1.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{isAr ? 'إعداد يملك السياسة' : 'Setup owns policy'}</Badge>
          <Badge variant="outline">{isAr ? 'ليست SKU تجارية' : 'Not a commercial SKU'}</Badge>
          <Badge variant="outline">{isAr ? 'بدون نطاقات رواتب' : 'No salary bands'}</Badge>
          <Badge variant="outline">{isAr ? 'مسارات ≠ أهلية' : 'Edges ≠ eligibility'}</Badge>
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
              <div className="text-sm font-medium">{isAr ? 'هيكل الوظائف' : 'Job Architecture'}</div>
              <div className="text-xs text-muted-foreground">
                {effective?.usable
                  ? isAr
                    ? 'مفعّل وقابل للاستخدام'
                    : 'Enabled and usable'
                  : isAr
                    ? 'متوقف أو غير متاح — النص القديم يبقى صالحاً'
                    : 'Off or unavailable — legacy free-text continues to work'}
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
