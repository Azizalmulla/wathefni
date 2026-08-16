import { useCallback, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, Loader2, Users } from 'lucide-react'

import { ConfigureInOpsLink } from '@/components/ConfigureInSetupBanner'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { dashboardPageHref } from '@/lib/setupConsoleOwnership'

import { getTeamAccess, type TeamAccessResponse } from './api'
import type { SetupCredentials } from './types'

function statusTone(status: string): 'success' | 'warning' | 'muted' | 'danger' {
  if (status === 'active') return 'success'
  if (status === 'invited') return 'warning'
  if (status === 'disabled') return 'muted'
  return 'muted'
}

export function TeamAccessCard({
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
  const [payload, setPayload] = useState<TeamAccessResponse | null>(null)
  const [showPresets, setShowPresets] = useState(false)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      setPayload(await getTeamAccess(credentials, companyCode))
    } catch (error) {
      onError(error)
    } finally {
      setLoading(false)
    }
  }, [companyCode, credentials, onError])

  useEffect(() => {
    void reload()
  }, [reload])

  const members = payload?.members || []

  return (
    <Card id="classic-team-access" data-ownership="team_access" data-phase="4" dir={isAr ? 'rtl' : 'ltr'} lang={locale}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="h-4 w-4" aria-hidden />
          {isAr ? 'الفريق والوصول' : 'Team & access'}
        </CardTitle>
        <CardDescription>
          {isAr
            ? 'من يدير هذه الشركة وما يمكنه فعله. دعوة الأعضاء اليومية تتم من الإعدادات ← الفريق.'
            : 'Who administers this company and what they can manage. Day-to-day invites stay in Settings → Team.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-subtle">
            {isAr
              ? `${payload?.active_owner_count ?? '—'} مسؤول شركة نشط · ${payload?.pending_invites ?? 0} دعوة معلّقة`
              : `${payload?.active_owner_count ?? '—'} active Company Admin(s) · ${payload?.pending_invites ?? 0} pending invite(s)`}
          </p>
          <ConfigureInOpsLink
            href={dashboardPageHref('settings')}
            label={isAr ? 'إدارة الفريق' : 'Manage team'}
          />
        </div>

        {loading || !payload ? (
          <p className="flex items-center gap-2 text-sm text-subtle">
            <Loader2 className="h-4 w-4 animate-spin" /> {isAr ? 'جاري التحميل…' : 'Loading team…'}
          </p>
        ) : members.length === 0 ? (
          <p className="rounded-2xl border border-amber-200/70 bg-amber-50/50 px-4 py-3 text-sm text-amber-950">
            {isAr
              ? 'لا يوجد أعضاء بعد. أنشئ دعوة المالك الأولى أعلاه، ثم أدر الفريق من الإعدادات.'
              : 'No team members yet. Create the first Owner invite above, then manage the team in Settings.'}
          </p>
        ) : (
          <div className="space-y-2">
            <div className="hidden grid-cols-[1.4fr_1fr_1.4fr_0.7fr] gap-2 px-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle sm:grid">
              <span>{isAr ? 'الشخص' : 'Person'}</span>
              <span>{isAr ? 'الدور' : 'Role'}</span>
              <span>{isAr ? 'ملخص الوصول' : 'Access summary'}</span>
              <span>{isAr ? 'الحالة' : 'Status'}</span>
            </div>
            {members.map((m) => (
              <div
                key={m.user_id || m.email}
                className="grid gap-2 rounded-2xl border border-line/55 bg-white/50 px-4 py-3 sm:grid-cols-[1.4fr_1fr_1.4fr_0.7fr] sm:items-center"
                data-team-member={m.user_id}
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-text">{m.name || m.email || (isAr ? 'بدون اسم' : 'Unnamed')}</p>
                  <p className="truncate text-xs text-subtle">{m.email || m.phone || '—'}</p>
                </div>
                <p className="text-sm text-text">{isAr ? m.role_label_ar : m.role_label_en}</p>
                <p className="text-sm text-subtle">{isAr ? m.access_summary_ar : m.access_summary_en}</p>
                <div>
                  <Badge tone={statusTone(String(m.status || ''))}>
                    {m.status === 'active'
                      ? isAr
                        ? 'نشط'
                        : 'Active'
                      : m.status === 'invited'
                        ? isAr
                          ? 'مدعو'
                          : 'Invited'
                        : m.status === 'disabled'
                          ? isAr
                            ? 'متوقف'
                            : 'Disabled'
                          : m.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}

        <button
          type="button"
          className="flex items-center gap-1 text-xs font-semibold uppercase tracking-[0.08em] text-subtle"
          onClick={() => setShowPresets((v) => !v)}
        >
          {showPresets ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          {isAr ? 'أدوار جاهزة (متقدم)' : 'Role presets (advanced)'}
        </button>
        {showPresets ? (
          <div className="space-y-2 rounded-2xl border border-line/50 bg-white/40 p-3">
            <p className="text-xs text-subtle">
              {isAr
                ? 'اختر دوراً جاهزاً عند الدعوة من الإعدادات. لا تُعرض رموز الصلاحيات الداخلية هنا.'
                : 'Choose a preset when inviting from Settings. Internal permission codes are not shown here.'}
            </p>
            {(payload?.role_presets || []).map((preset) => (
              <div key={preset.role} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line/40 px-3 py-2 text-sm">
                <span className="font-medium">{isAr ? preset.label_ar : preset.label_en}</span>
                <span className="text-xs text-subtle">{isAr ? preset.access_summary_ar : preset.access_summary_en}</span>
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
