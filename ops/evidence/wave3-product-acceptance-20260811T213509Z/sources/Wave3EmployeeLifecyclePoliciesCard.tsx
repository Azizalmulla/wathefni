import { useCallback, useEffect, useState } from 'react'
import { Loader2, Save } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/field'

import { getModulePolicies, updateModulePolicy, type ModulePoliciesResponse } from './api'
import type { SetupCredentials } from './types'

type Wave3Id =
  | 'employment_change'
  | 'ess_letters_dependents'
  | 'exit_intent'
  | 'offboarding'
  | 'exit_close'

const META: Record<Wave3Id, { titleEn: string; titleAr: string; toggleKey: string }> = {
  employment_change: {
    titleEn: 'Employment changes',
    titleAr: 'تغييرات التوظيف',
    toggleKey: 'enabled',
  },
  ess_letters_dependents: {
    titleEn: 'ESS letters & dependents',
    titleAr: 'خطابات و مرافقون',
    toggleKey: 'enabled',
  },
  exit_intent: {
    titleEn: 'Resignation / termination / EOC',
    titleAr: 'استقالة / إنهاء / نهاية عقد',
    toggleKey: 'enabled',
  },
  offboarding: {
    titleEn: 'Offboarding & clearance',
    titleAr: 'إنهاء الخدمة والمخالصة',
    toggleKey: 'enabled',
  },
  exit_close: {
    titleEn: 'Exit close & alumni',
    titleAr: 'إغلاق الخروج والخريجون',
    toggleKey: 'enabled',
  },
}

function boolVal(v: unknown): boolean {
  return v === true || v === 'true' || v === 1 || v === '1'
}

export function Wave3EmployeeLifecyclePoliciesCard({
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
  const [saving, setSaving] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [wave3, setWave3] = useState<Record<string, any> | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const data = (await getModulePolicies(credentials, companyCode)) as ModulePoliciesResponse & {
        wave3?: { modules?: Record<string, any>; honesty?: Record<string, unknown> }
      }
      setWave3(data.wave3?.modules || null)
    } catch (error) {
      onError(error)
    } finally {
      setLoading(false)
    }
  }, [companyCode, credentials, onError])

  useEffect(() => {
    void reload()
  }, [reload])

  async function toggle(id: Wave3Id) {
    if (!reason.trim()) {
      onError(new Error(isAr ? 'سبب التدقيق مطلوب' : 'Audit reason is required'))
      return
    }
    const meta = META[id]
    const current = wave3?.[id]?.policy || {}
    const next = !boolVal(current[meta.toggleKey])
    setSaving(id)
    try {
      await updateModulePolicy(credentials, companyCode, `wave3_${id}`, {
        reason: reason.trim(),
        required: { [meta.toggleKey]: next },
      })
      await reload()
    } catch (error) {
      onError(error)
    } finally {
      setSaving(null)
    }
  }

  return (
    <Card id="classic-wave3-employee-lifecycle" data-ownership="wave3_employee_lifecycle_policies">
      <CardHeader>
        <CardTitle>{isAr ? 'دورة حياة الموظف (الموجة 3)' : 'Employee Lifecycle (Wave 3)'}</CardTitle>
        <CardDescription>
          {isAr
            ? 'سياسات الشركة لتغييرات التوظيف والخطابات والاستقالة وإنهاء الخدمة وإغلاق الخروج. الإعداد يملك السياسات؛ الإنهاء الحقيقي يبقى مظلماً حتى قرار المالك.'
            : 'Company policies for employment changes, ESS letters, resignation/termination/EOC, offboarding, and exit close. Setup owns policies; real termination stays dark until an explicit owner decision.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{isAr ? 'إعداد يملك السياسة' : 'Setup owns policy'}</Badge>
          <Badge variant="outline">{isAr ? 'إنهاء حقيقي مظلم' : 'Real term dark'}</Badge>
          <Badge variant="outline">{isAr ? 'الإغلاق وحده يكتب left' : 'Close sole left writer'}</Badge>
        </div>
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
            {(Object.keys(META) as Wave3Id[]).map((id) => {
              const meta = META[id]
              const policy = wave3?.[id]?.policy || {}
              const on = boolVal(policy[meta.toggleKey])
              return (
                <div
                  key={id}
                  id={`classic-wave3-${id}`}
                  data-wave3-policy={id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/70 p-3"
                >
                  <div>
                    <div className="font-medium">{isAr ? meta.titleAr : meta.titleEn}</div>
                    <div className="text-xs text-muted-foreground">
                      {on ? (isAr ? 'مفعّل في إعداد الشركة' : 'Enabled in company Setup') : isAr ? 'متوقف' : 'Off'}
                    </div>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant={on ? 'default' : 'outline'}
                    disabled={saving === id}
                    onClick={() => void toggle(id)}
                  >
                    {saving === id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    <span className="ms-2">{on ? (isAr ? 'إيقاف' : 'Turn off') : isAr ? 'تفعيل' : 'Turn on'}</span>
                  </Button>
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
