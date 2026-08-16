import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ConfigureInOpsLink } from '@/components/ConfigureInSetupBanner'
import { SETUP_CONSOLE_OWNERSHIP, dashboardPageHref } from '@/lib/setupConsoleOwnership'

/** Phase 1 — calm ownership map + deep links (no engineering jargon). */
export function OwnershipDeepLinksCard({ locale = 'en' }: { locale?: 'en' | 'ar' }) {
  const isAr = locale === 'ar'
  return (
    <Card id="classic-ownership" data-ownership-map="phase1">
      <CardHeader>
        <CardTitle>{isAr ? 'ملكية الإعداد' : 'Configuration ownership'}</CardTitle>
        <CardDescription>
          {isAr
            ? 'ماذا تستخدم الشركة؟ كيف يعمل؟ من يصل إليه؟ العمل اليومي يبقى في وحدات التشغيل.'
            : 'What does this company use? How should it work? Who can access it? Day-to-day work stays in operational modules.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {SETUP_CONSOLE_OWNERSHIP.map((entry) => (
          <div
            key={entry.key}
            className="rounded-2xl border border-line/55 bg-white/45 px-4 py-3"
            data-ownership-row={entry.key}
            data-owner={entry.owner}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="text-sm font-medium text-text">{isAr ? entry.labelAr : entry.labelEn}</p>
                <p className="mt-1 text-xs text-subtle">
                  {isAr ? 'المالك: ' : 'Owner: '}
                  {entry.ownerLabelEn}
                </p>
                {entry.notesEn ? <p className="mt-1 text-xs leading-5 text-subtle">{entry.notesEn}</p> : null}
              </div>
              <div className="flex flex-col items-end gap-1">
                {entry.setupHref ? (
                  <a href={entry.setupHref} className="text-xs font-medium text-accent hover:underline">
                    {isAr ? 'في الإعداد' : 'In Setup'}
                  </a>
                ) : null}
                {entry.opsHref ? <ConfigureInOpsLink href={entry.opsHref} label={isAr ? 'العمليات' : 'Operations'} /> : null}
              </div>
            </div>
          </div>
        ))}
        <div className="flex flex-wrap gap-3 pt-1 text-xs">
          <ConfigureInOpsLink href={dashboardPageHref('payroll')} label={isAr ? 'تشغيل الرواتب' : 'Payroll runs'} />
          <ConfigureInOpsLink
            href={dashboardPageHref('employees', { view: 'migration' })}
            label={isAr ? 'الأنظمة المتصلة / المزامنة' : 'Connected systems / sync'}
          />
          <ConfigureInOpsLink href={dashboardPageHref('settings')} label={isAr ? 'الفريق والإعدادات' : 'Team & Settings'} />
        </div>
      </CardContent>
    </Card>
  )
}
