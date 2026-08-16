import { Badge } from '@/components/ui/badge'

export type SetupEffectiveState = {
  effective_state?: string
  usable?: boolean
  stored_enabled?: boolean
  label_en?: string
  label_ar?: string
  deployment?: {
    reason_code?: string
    message_en?: string
    message_ar?: string
  }
}

function tone(state: string): 'success' | 'warning' | 'danger' | 'muted' {
  if (state === 'enabled_usable') return 'success'
  if (state === 'available_disabled' || state === 'not_entitled') return 'muted'
  if (state === 'dependency_unmet') return 'warning'
  if (state === 'unavailable_deployment' || state === 'not_released' || state === 'not_permitted') return 'danger'
  return 'muted'
}

export function SetupEffectiveStateBanner({
  state,
  locale,
}: {
  state: SetupEffectiveState | null | undefined
  locale: 'en' | 'ar'
}) {
  const isAr = locale === 'ar'
  const key = String(state?.effective_state || 'available_disabled')
  const label = isAr ? state?.label_ar || key : state?.label_en || key
  const detail = isAr ? state?.deployment?.message_ar : state?.deployment?.message_en
  const storedOnUnusable = Boolean(state?.stored_enabled) && state?.usable !== true
  return (
    <div className="space-y-1" data-effective-state={key} data-usable={String(state?.usable === true)}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" data-tone={tone(key)}>
          {label}
        </Badge>
        {storedOnUnusable ? (
          <Badge variant="outline">
            {isAr ? 'المخزّن مفعّل — التشغيل غير متاح' : 'Stored on — runtime unavailable'}
          </Badge>
        ) : null}
      </div>
      {detail && key !== 'enabled_usable' ? (
        <p className="text-xs text-muted-foreground">{detail}</p>
      ) : null}
    </div>
  )
}

export function canEnableFromState(state: SetupEffectiveState | null | undefined) {
  const key = String(state?.effective_state || '')
  return key === 'available_disabled' || key === 'enabled_usable' || key === 'not_entitled'
}
