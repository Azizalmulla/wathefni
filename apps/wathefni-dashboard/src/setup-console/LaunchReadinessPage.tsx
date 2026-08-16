/**
 * Setup Console Wave A — Launch Readiness checklist.
 * Calm stages, honest states, plain operator language.
 * Does not mutate freezes / env gates / allowlists.
 */
import { useCallback, useEffect, useState } from 'react'
import { ArrowUpRight, Loader2, RefreshCw } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

import { getLaunchReadiness } from './api'
import type { LaunchReadinessResponse, LaunchReadinessItem, SetupCredentials } from './types'

function stateTone(state: string): 'success' | 'warning' | 'danger' | 'muted' {
  if (state === 'live_controlled' || state === 'ready_for_canary') return 'success'
  if (state === 'setup_required' || state === 'paused') return 'warning'
  if (state === 'blocked') return 'danger'
  return 'muted'
}

function stateLabel(state: string, locale: 'en' | 'ar') {
  const en: Record<string, string> = {
    not_purchased: 'Not purchased',
    setup_required: 'Setup required',
    blocked: 'Blocked',
    ready_for_canary: 'Ready for canary',
    live_controlled: 'Live · controlled',
    paused: 'Paused',
  }
  const ar: Record<string, string> = {
    not_purchased: 'غير مشترًى',
    setup_required: 'يلزم الإعداد',
    blocked: 'محظور',
    ready_for_canary: 'جاهز للتجربة',
    live_controlled: 'يعمل · منضبط',
    paused: 'متوقف',
  }
  return (locale === 'ar' ? ar : en)[state] || state
}

function ItemRow({ item, locale }: { item: LaunchReadinessItem; locale: 'en' | 'ar' }) {
  const title = locale === 'ar' ? item.title_ar : item.title_en
  const summary = locale === 'ar' ? item.summary_ar : item.summary_en
  const next = locale === 'ar' ? item.next_action_ar : item.next_action_en
  const showNext = Boolean(next) && (item.blocked || item.state === 'setup_required' || item.state === 'paused')

  return (
    <div
      className="rounded-2xl border border-line/50 bg-white/50 px-4 py-3"
      data-testid={`launch-item-${item.key}`}
      data-state={item.state}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-medium text-text">{title}</p>
          <p className="mt-1 text-[13px] leading-relaxed text-subtle">{summary}</p>
          {showNext ? (
            <p className="mt-2 text-[13px] text-text">
              <span className="text-subtle">{locale === 'ar' ? 'الإجراء التالي: ' : 'Next: '}</span>
              {next}
              {item.deep_link ? (
                <a
                  href={item.deep_link}
                  className="ms-2 inline-flex items-center gap-0.5 text-accent underline-offset-2 hover:underline"
                >
                  {locale === 'ar' ? 'افتح' : 'Open'}
                  <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
                </a>
              ) : null}
            </p>
          ) : null}
        </div>
        <Badge tone={stateTone(item.state)}>{stateLabel(item.state, locale)}</Badge>
      </div>
    </div>
  )
}

export function LaunchReadinessPage({
  credentials,
  companyCode,
  locale = 'en',
}: {
  credentials: SetupCredentials
  companyCode: string
  locale?: 'en' | 'ar'
}) {
  const [data, setData] = useState<LaunchReadinessResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showModulesDetail, setShowModulesDetail] = useState(false)
  const dir = locale === 'ar' ? 'rtl' : 'ltr'

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setData(await getLaunchReadiness(credentials, companyCode))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load launch readiness')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [companyCode, credentials])

  useEffect(() => {
    void load()
  }, [load])

  const overall = data?.overall_state || 'setup_required'
  const overallLabel = locale === 'ar' ? data?.overall_label_ar : data?.overall_label_en

  return (
    <div dir={dir} className="space-y-4" data-testid="launch-readiness-page" data-overall={overall}>
      <Card className="overflow-hidden border-line/60 bg-gradient-to-br from-[#fbf7f0] via-white/80 to-[#f3eee4]">
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div>
            <CardTitle className="text-[22px] tracking-tight">
              {locale === 'ar' ? 'جاهزية الإطلاق' : 'Launch readiness'}
            </CardTitle>
            <CardDescription className="mt-1 max-w-xl text-[14px]">
              {locale === 'ar'
                ? 'قائمة هادئة لما هو مشترًى، وما هو مضبوط، وما هو محظور، وما يعمل فعلياً.'
                : 'A calm view of what is purchased, configured, blocked, and actually live.'}
            </CardDescription>
          </div>
          <Button variant="ghost" size="sm" onClick={() => void load()} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {locale === 'ar' ? 'تحديث' : 'Refresh'}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            className={cn(
              'rounded-2xl border px-4 py-4',
              overall === 'live_controlled' || overall === 'ready_for_canary'
                ? 'border-emerald-200/80 bg-emerald-50/50'
                : overall === 'blocked'
                  ? 'border-rose-200/80 bg-rose-50/40'
                  : 'border-amber-200/80 bg-amber-50/40',
            )}
            data-testid="launch-overall-status"
          >
            <p className="text-[12px] uppercase tracking-[0.14em] text-subtle">
              {locale === 'ar' ? 'الحالة العامة' : 'Overall status'}
            </p>
            <p className="mt-1 text-[20px] font-semibold text-text">{overallLabel || stateLabel(overall, locale)}</p>
            <p className="mt-2 text-[13px] text-subtle">
              {companyCode}
              {data?.company_name ? ` · ${data.company_name}` : ''}
            </p>
          </div>

          {error ? <p className="text-sm text-danger">{error}</p> : null}
          {loading && !data ? (
            <p className="text-sm text-subtle">{locale === 'ar' ? 'جاري التحميل…' : 'Loading…'}</p>
          ) : null}

          {data?.important_blockers?.length ? (
            <div className="space-y-2" data-testid="launch-important-blockers">
              <p className="text-[13px] font-medium text-text">
                {locale === 'ar' ? 'عوائق مهمة' : 'Important blockers'}
              </p>
              {data.important_blockers.map((b) => (
                <div key={b.key} className="rounded-2xl border border-line/60 bg-white/70 px-4 py-3">
                  <p className="text-[14px] font-medium">{locale === 'ar' ? b.title_ar : b.title_en}</p>
                  <p className="mt-1 text-[13px] text-subtle">{locale === 'ar' ? b.summary_ar : b.summary_en}</p>
                  {(locale === 'ar' ? b.next_action_ar : b.next_action_en) ? (
                    <p className="mt-2 text-[13px]">
                      <span className="text-subtle">{locale === 'ar' ? 'الإجراء التالي: ' : 'Next: '}</span>
                      {locale === 'ar' ? b.next_action_ar : b.next_action_en}
                      {b.deep_link ? (
                        <a href={b.deep_link} className="ms-2 text-accent underline-offset-2 hover:underline">
                          {locale === 'ar' ? 'افتح' : 'Open'}
                        </a>
                      ) : null}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {data?.stages?.map((stageBlock) => {
        const stageKey = stageBlock.stage.key
        const stageLabel = locale === 'ar' ? stageBlock.stage.label_ar : stageBlock.stage.label_en
        let items = stageBlock.items
        if (stageKey === 'modules' && !showModulesDetail) {
          items = items.filter((i) => i.purchased || i.blocked || i.state === 'setup_required')
        }
        return (
          <Card key={stageKey} data-testid={`launch-stage-${stageKey}`}>
            <CardHeader className="flex flex-row items-center justify-between gap-2 pb-2">
              <CardTitle className="text-[16px]">{stageLabel}</CardTitle>
              {stageKey === 'modules' ? (
                <Button size="sm" variant="ghost" onClick={() => setShowModulesDetail((v) => !v)}>
                  {showModulesDetail
                    ? locale === 'ar'
                      ? 'إخفاء غير المشتراة'
                      : 'Hide not purchased'
                    : locale === 'ar'
                      ? 'إظهار كل الوحدات'
                      : 'Show all modules'}
                </Button>
              ) : null}
            </CardHeader>
            <CardContent className="space-y-2">
              {items.map((item) => (
                <ItemRow key={item.key} item={item} locale={locale} />
              ))}
            </CardContent>
          </Card>
        )
      })}

      {data?.pause_impact ? (
        <Card data-testid="launch-pause-impact">
          <CardHeader>
            <CardTitle className="text-[16px]">
              {locale === 'ar' ? data.pause_impact.title_ar : data.pause_impact.title_en}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1 ps-5 text-[13px] text-subtle">
              {(locale === 'ar' ? data.pause_impact.bullets_ar : data.pause_impact.bullets_en).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
