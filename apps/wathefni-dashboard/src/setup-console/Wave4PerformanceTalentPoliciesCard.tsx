import { useCallback, useEffect, useState } from 'react'
import { Loader2, Save } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/field'

import { getModulePolicies, updateModulePolicy, type ModulePoliciesResponse } from './api'
import type { SetupCredentials } from './types'

type Wave4Id =
  | 'performance_goals'
  | 'performance_reviews'
  | 'performance_feedback'
  | 'performance_calibration'
  | 'talent_profile'
  | 'talent_succession'

const META: Record<Wave4Id, { titleEn: string; titleAr: string; toggleKey: string }> = {
  performance_goals: {
    titleEn: 'Goals / OKRs / KPIs',
    titleAr: 'الأهداف / النتائج الرئيسية / مؤشرات الأداء',
    toggleKey: 'enabled',
  },
  performance_reviews: {
    titleEn: 'Review cycles / 360',
    titleAr: 'دورات التقييم / 360',
    toggleKey: 'enabled',
  },
  performance_feedback: {
    titleEn: 'Check-ins / competencies / development',
    titleAr: 'المتابعات / الكفاءات / التطوير',
    toggleKey: 'enabled',
  },
  performance_calibration: {
    titleEn: 'Aggregation / calibration',
    titleAr: 'التجميع / المعايرة',
    toggleKey: 'enabled',
  },
  talent_profile: {
    titleEn: 'Talent profile / potential',
    titleAr: 'ملف المواهب / الإمكانات',
    toggleKey: 'enabled',
  },
  talent_succession: {
    titleEn: 'Talent review / HiPo / succession',
    titleAr: 'مراجعة المواهب / الإمكانات العالية / التعاقب',
    toggleKey: 'enabled',
  },
}

function boolVal(v: unknown): boolean {
  return v === true || v === 'true' || v === 1 || v === '1'
}

export function Wave4PerformancePoliciesCard(props: {
  credentials: SetupCredentials
  companyCode: string
  locale: 'en' | 'ar'
  onError: (error: unknown) => void
}) {
  return <Wave4PerformanceTalentPoliciesCard {...props} scope="performance" />
}

export function Wave4TalentPoliciesCard(props: {
  credentials: SetupCredentials
  companyCode: string
  locale: 'en' | 'ar'
  onError: (error: unknown) => void
}) {
  return <Wave4PerformanceTalentPoliciesCard {...props} scope="talent" />
}

export function Wave4PerformanceTalentPoliciesCard({
  credentials,
  companyCode,
  locale,
  onError,
  scope = 'all',
}: {
  credentials: SetupCredentials
  companyCode: string
  locale: 'en' | 'ar'
  onError: (error: unknown) => void
  scope?: 'all' | 'performance' | 'talent'
}) {
  const isAr = locale === 'ar'
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [wave4, setWave4] = useState<Record<string, any> | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const data = (await getModulePolicies(credentials, companyCode)) as ModulePoliciesResponse & {
        wave4?: { modules?: Record<string, any>; honesty?: Record<string, unknown> }
      }
      setWave4(data.wave4?.modules || null)
    } catch (error) {
      onError(error)
    } finally {
      setLoading(false)
    }
  }, [companyCode, credentials, onError])

  useEffect(() => {
    void reload()
  }, [reload])

  async function patchPolicy(id: Wave4Id, required: Record<string, unknown>) {
    if (!reason.trim()) {
      onError(new Error(isAr ? 'سبب التدقيق مطلوب' : 'Audit reason is required'))
      return
    }
    setSaving(id)
    try {
      await updateModulePolicy(credentials, companyCode, `wave4_${id}`, {
        reason: reason.trim(),
        required,
      })
      await reload()
    } catch (error) {
      onError(error)
    } finally {
      setSaving(null)
    }
  }

  async function toggle(id: Wave4Id) {
    if (!reason.trim()) {
      onError(new Error(isAr ? 'سبب التدقيق مطلوب' : 'Audit reason is required'))
      return
    }
    const meta = META[id]
    const current = wave4?.[id]?.policy || {}
    const next = !boolVal(current[meta.toggleKey])
    await patchPolicy(id, { [meta.toggleKey]: next })
  }

  return (
    <Card
      id={
        scope === 'performance'
          ? 'classic-wave4-performance'
          : scope === 'talent'
            ? 'classic-wave4-talent'
            : 'classic-wave4-performance-talent'
      }
      data-ownership={
        scope === 'performance'
          ? 'wave4_performance_policies'
          : scope === 'talent'
            ? 'wave4_talent_policies'
            : 'wave4_performance_talent_policies'
      }
    >
      <CardHeader>
        <CardTitle>
          {scope === 'performance'
            ? isAr
              ? 'الأداء'
              : 'Performance'
            : scope === 'talent'
              ? isAr
                ? 'المواهب'
                : 'Talent'
              : isAr
                ? 'الأداء والمواهب (الموجة 4)'
                : 'Performance & Talent (Wave 4)'}
        </CardTitle>
        <CardDescription>
          {scope === 'performance'
            ? isAr
              ? 'سياسات الأهداف والمراجعات والمتابعات والمعايرة. المواهب تبقى منفصلة.'
              : 'Goals, reviews, check-ins, and calibration policies. Talent stays a separate module.'
            : scope === 'talent'
              ? isAr
                ? 'سياسات ملف المواهب والإمكانات والتعاقب والتنقل. الأداء يبقى منفصلاً. لا درجة مواهب عامة.'
                : 'Talent profile, potential, succession, and mobility policies. Performance stays separate. No master talent score.'
              : isAr
                ? 'سياسات الشركة للأهداف والمراجعات والمتابعات والمعايرة وملف المواهب والتعاقب. الإعداد يملك السياسات؛ أعلام البيئة تبقى مفاتيح إيقاف فقط. لا درجة مواهب عامة؛ شبكة التسعة اختيارية مشتقة.'
                : 'Company policies for goals, reviews, check-ins, calibration, Talent profile, and succession. Setup owns policies; env flags remain kill-switches only. No master talent score; 9-box stays optional and derived.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{isAr ? 'إعداد يملك السياسة' : 'Setup owns policy'}</Badge>
          <Badge variant="outline">{isAr ? 'التطوير من C3 فقط' : 'C3 sole development'}</Badge>
          {scope !== 'performance' ? (
            <>
              <Badge variant="outline">{isAr ? 'لا درجة مواهب عامة' : 'No master talent score'}</Badge>
              <Badge variant="outline">{isAr ? 'شبكة 9 اختيارية' : '9-box optional'}</Badge>
            </>
          ) : null}
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
            {(Object.keys(META) as Wave4Id[])
              .filter((id) =>
                scope === 'performance'
                  ? id.startsWith('performance_')
                  : scope === 'talent'
                    ? id.startsWith('talent_')
                    : true,
              )
              .map((id) => {
              const meta = META[id]
              const policy = wave4?.[id]?.policy || {}
              const on = boolVal(policy[meta.toggleKey])
              return (
                <div
                  key={id}
                  id={`classic-wave4-${id}`}
                  data-wave4-policy={id}
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
            {scope === 'performance' ? (
              <div className="rounded-xl border border-border/70 p-3 space-y-2">
                <div className="font-medium">{isAr ? 'عمق دورة النتائج الرئيسية' : 'OKR operating depth'}</div>
                <div className="text-xs text-muted-foreground">
                  {isAr
                    ? 'دورة النتائج الرئيسية ليست دورة مراجعة. الثقة اختيارية وليست نسبة تقدم.'
                    : 'An OKR cycle is not a review cycle. Confidence is optional and is not progress.'}
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant={boolVal(wave4?.performance_goals?.policy?.confidence_enabled) ? 'default' : 'outline'}
                  disabled={saving === 'performance_goals'}
                  onClick={() =>
                    void patchPolicy('performance_goals', {
                      confidence_enabled: !boolVal(wave4?.performance_goals?.policy?.confidence_enabled),
                    })
                  }
                >
                  {boolVal(wave4?.performance_goals?.policy?.confidence_enabled)
                    ? isAr
                      ? 'إيقاف إشارة الثقة'
                      : 'Turn off confidence'
                    : isAr
                      ? 'تفعيل إشارة الثقة'
                      : 'Turn on confidence'}
                </Button>
              </div>
            ) : null}
            {scope === 'talent' ? (
              <div className="rounded-xl border border-border/70 p-3 space-y-2">
                <div className="font-medium">{isAr ? 'عقد دليل النتائج الرئيسية' : 'OKR Talent evidence contract'}</div>
                <div className="text-xs text-muted-foreground">
                  {isAr
                    ? 'افتراضيًا متوقف. اكتمال النتيجة الرئيسية ليس جودة ولا إمكانات ولا تصنيف إمكانات عالية.'
                    : 'Default off. OKR completion is not quality, potential, or HiPo.'}
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant={boolVal(wave4?.talent_profile?.policy?.okr_as_talent_evidence) ? 'default' : 'outline'}
                  disabled={saving === 'talent_profile'}
                  onClick={() =>
                    void patchPolicy('talent_profile', {
                      okr_as_talent_evidence: !boolVal(wave4?.talent_profile?.policy?.okr_as_talent_evidence),
                    })
                  }
                >
                  {boolVal(wave4?.talent_profile?.policy?.okr_as_talent_evidence)
                    ? isAr
                      ? 'إيقاف استهلاك النتائج الرئيسية'
                      : 'Turn off OKR evidence'
                    : isAr
                      ? 'السماح بدليل النتائج الرئيسية'
                      : 'Allow OKR evidence'}
                </Button>
              </div>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
