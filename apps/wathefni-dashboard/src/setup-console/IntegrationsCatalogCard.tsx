import { useCallback, useEffect, useState } from 'react'
import { ArrowUpRight, Loader2, Plug } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import { getIntegrationsCatalog, type IntegrationCatalogCard, type IntegrationsCatalogResponse } from './api'
import type { SetupCredentials } from './types'

function statusTone(status: string): 'success' | 'warning' | 'muted' | 'danger' {
  if (status === 'connected') return 'success'
  if (status === 'needs_attention') return 'warning'
  return 'muted'
}

function statusLabel(status: string, isAr: boolean): string {
  if (status === 'connected') return isAr ? 'متصل' : 'Connected'
  if (status === 'needs_attention') return isAr ? 'يحتاج انتباهاً' : 'Needs attention'
  return isAr ? 'غير متصل' : 'Not connected'
}

function IntegrationRow({ card, isAr }: { card: IntegrationCatalogCard; isAr: boolean }) {
  return (
    <div
      className="rounded-2xl border border-line/55 bg-white/50 px-4 py-3"
      data-integration-card={card.key}
      data-status={card.status}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-text">{isAr ? card.label_ar : card.label_en}</p>
            <Badge tone={statusTone(String(card.status || ''))}>{statusLabel(String(card.status || ''), isAr)}</Badge>
          </div>
          <p className="text-sm text-subtle">{isAr ? card.purpose_ar : card.purpose_en}</p>
          <p className="text-xs text-subtle">
            {isAr ? card.detail_ar || card.credentials_label_ar : card.detail_en || card.credentials_label_en}
            {card.has_credentials ? ` · ${isAr ? 'بيانات الاعتماد مضبوطة' : 'Credentials configured'}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap gap-3 text-sm font-medium">
          {card.configure_href ? (
            <a href={card.configure_href} className="inline-flex items-center gap-1 text-accent hover:underline">
              {isAr ? 'إعداد' : 'Configure'}
              <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
            </a>
          ) : null}
          {card.activity_href ? (
            <a href={card.activity_href} className="inline-flex items-center gap-1 text-accent hover:underline">
              {isAr ? 'عرض المزامنة' : 'Manage sync'}
              <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
            </a>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export function IntegrationsCatalogCard({
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
  const [payload, setPayload] = useState<IntegrationsCatalogResponse | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      setPayload(await getIntegrationsCatalog(credentials, companyCode))
    } catch (error) {
      onError(error)
    } finally {
      setLoading(false)
    }
  }, [companyCode, credentials, onError])

  useEffect(() => {
    void reload()
  }, [reload])

  const cards = payload?.cards || []

  return (
    <Card id="classic-integrations" data-ownership="integrations_catalog" data-phase="4" dir={isAr ? 'rtl' : 'ltr'} lang={locale}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Plug className="h-4 w-4" aria-hidden />
          {isAr ? 'التكاملات' : 'Integrations'}
        </CardTitle>
        <CardDescription>
          {isAr
            ? 'ما هو متصل لهذه الشركة. تشغيل المزامنة والاستثناءات يبقى في الأنظمة المتصلة.'
            : 'What is connected for this company. Sync runs and exceptions stay in Connected Systems.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading || !payload ? (
          <p className="flex items-center gap-2 text-sm text-subtle">
            <Loader2 className="h-4 w-4 animate-spin" /> {isAr ? 'جاري التحميل…' : 'Loading integrations…'}
          </p>
        ) : (
          cards.map((card) => <IntegrationRow key={card.key} card={card} isAr={isAr} />)
        )}
        <p className="text-xs text-subtle">
          {isAr
            ? 'بيانات الاعتماد لا تُعرض هنا. واتساب الشخصي للموارد البشرية يبقى في الإعدادات ← الحساب.'
            : 'Credentials are never shown here. Personal HR WhatsApp stays in Settings → Account.'}
        </p>
      </CardContent>
    </Card>
  )
}
