import { useCallback, useEffect, useState } from 'react'
import { Loader2, Save } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/field'

import { getModulePolicies, updateModulePolicy, type ModulePoliciesResponse } from './api'
import type { SetupCredentials } from './types'

type Wave2Id =
  | 'attendance'
  | 'leave'
  | 'shifts'
  | 'payroll'
  | 'payment_processing'
  | 'settlement'
  | 'ot_to_payroll'

const META: Record<Wave2Id, { titleEn: string; titleAr: string; toggleKey: string }> = {
  attendance: { titleEn: 'Attendance ingest', titleAr: 'استيعاب الحضور', toggleKey: 'ingest_enabled' },
  leave: { titleEn: 'Leave enforced', titleAr: 'إنفاذ الإجازات', toggleKey: 'enforced' },
  shifts: { titleEn: 'Shifts MSS', titleAr: 'مناوبات المديرين', toggleKey: 'mss_enabled' },
  payroll: {
    titleEn: 'Authoritative finalize',
    titleAr: 'اعتماد الرواتب السلطوي',
    toggleKey: 'authoritative_finalize',
  },
  payment_processing: { titleEn: 'Payment files', titleAr: 'ملفات الدفع', toggleKey: 'enabled' },
  settlement: { titleEn: 'Final settlement', titleAr: 'التسوية النهائية', toggleKey: 'enabled' },
  ot_to_payroll: { titleEn: 'OT → Payroll feed', titleAr: 'إضافي → رواتب', toggleKey: 'enabled' },
}

function boolVal(v: unknown): boolean {
  return v === true || v === 'true' || v === 1 || v === '1'
}

export function Wave2WorkforceTruthPoliciesCard({
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
  const [wave2, setWave2] = useState<Record<string, any> | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const data = (await getModulePolicies(credentials, companyCode)) as ModulePoliciesResponse & {
        wave2?: { modules?: Record<string, any>; honesty?: Record<string, unknown> }
      }
      setWave2(data.wave2?.modules || null)
    } catch (error) {
      onError(error)
    } finally {
      setLoading(false)
    }
  }, [companyCode, credentials, onError])

  useEffect(() => {
    void reload()
  }, [reload])

  async function toggle(id: Wave2Id) {
    if (!reason.trim()) {
      onError(new Error(isAr ? 'سبب التدقيق مطلوب' : 'Audit reason is required'))
      return
    }
    const meta = META[id]
    const current = wave2?.[id]?.policy || {}
    const next = !boolVal(current[meta.toggleKey])
    setSaving(id)
    try {
      await updateModulePolicy(credentials, companyCode, `wave2_${id}`, {
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
    <Card id="classic-wave2-workforce-truth" data-ownership="wave2_workforce_truth_policies">
      <CardHeader>
        <CardTitle>{isAr ? 'حقيقة القوى العاملة (الموجة 2)' : 'Workforce Truth (Wave 2)'}</CardTitle>
        <CardDescription>
          {isAr
            ? 'سياسات الشركة للحضور والإجازات والمناوبات والرواتب والتسوية. الإعداد يملك السياسات؛ بوابات التشغيل تبقى مغلقة افتراضياً.'
            : 'Company policies for attendance, leave, shifts, payroll, payment files, and settlement. Setup owns policies; runtime gates stay fail-closed by default.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{isAr ? 'إعداد يملك السياسة' : 'Setup owns policy'}</Badge>
          <Badge variant="outline">{isAr ? 'معترف ≠ مدفوع' : 'Ack ≠ paid'}</Badge>
          <Badge variant="outline">{isAr ? 'التسوية ≠ مخالصة' : 'Settlement ≠ clearance'}</Badge>
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
            {(Object.keys(META) as Wave2Id[]).map((id) => {
              const meta = META[id]
              const policy = wave2?.[id]?.policy || {}
              const on = boolVal(policy[meta.toggleKey])
              return (
                <div
                  key={id}
                  id={`classic-wave2-${id}`}
                  data-wave2-policy={id}
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
