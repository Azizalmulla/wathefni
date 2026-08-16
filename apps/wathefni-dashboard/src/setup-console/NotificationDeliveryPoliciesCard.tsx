import { useCallback, useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/field'

import { getModulePolicies, updateModulePolicy, type ModulePoliciesResponse } from './api'
import { SetupEffectiveStateBanner, type SetupEffectiveState } from './SetupEffectiveStateBanner'
import type { SetupCredentials } from './types'

export function NotificationDeliveryPoliciesCard({
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
  const [preset, setPreset] = useState('office')
  const [options, setOptions] = useState<string[]>(['frontline', 'office', 'conservative'])
  const [effective, setEffective] = useState<SetupEffectiveState | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const data = (await getModulePolicies(credentials, companyCode)) as ModulePoliciesResponse & {
        delivery?: { policy?: Record<string, any>; effective_state?: SetupEffectiveState }
      }
      const policy = data.delivery?.policy || {}
      setPreset(String(policy.notification_preset || 'office'))
      setOptions(Array.isArray(policy.notification_preset_options) ? policy.notification_preset_options : ['frontline', 'office', 'conservative'])
      setEffective(data.delivery?.effective_state || null)
    } catch (error) {
      onError(error)
    } finally {
      setLoading(false)
    }
  }, [companyCode, credentials, onError])

  useEffect(() => {
    void reload()
  }, [reload])

  async function save() {
    if (!reason.trim()) {
      onError(new Error(isAr ? 'سبب التدقيق مطلوب' : 'Audit reason is required'))
      return
    }
    const previous = preset
    setSaving(true)
    try {
      await updateModulePolicy(credentials, companyCode, 'notifications', {
        reason: reason.trim(),
        required: { notification_preset: preset },
      })
      await reload()
    } catch (error) {
      setPreset(previous)
      onError(error)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card id="classic-notifications-delivery" data-ownership="notification_delivery_policies" dir={isAr ? 'rtl' : 'ltr'} lang={locale}>
      <CardHeader>
        <CardTitle>{isAr ? 'الإشعارات والتسليم' : 'Notifications & delivery'}</CardTitle>
        <CardDescription>
          {isAr
            ? 'إعدادات التسليم للشركة. أسرار المزود تبقى في التكاملات.'
            : 'Company delivery settings. Provider secrets stay in integrations.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{isAr ? 'سياسة العملاء' : 'Customer policy'}</Badge>
          <Badge variant="outline">{isAr ? 'بدون أسرار' : 'No secrets'}</Badge>
        </div>
        <SetupEffectiveStateBanner state={effective} locale={locale} />
        <p className="text-xs text-muted-foreground">
          {isAr
            ? 'الدفع إمّا متاح في هذا النشر أو غير متاح — الإعداد لا يعرض أسرار المزود.'
            : 'Push is either available in this deployment or unavailable. Setup never shows provider secrets.'}
        </p>
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
          <div className="flex flex-wrap items-end gap-3">
            <label className="space-y-1 text-sm">
              <span>{isAr ? 'إعداد الإشعارات' : 'Notification preset'}</span>
              <Select value={preset} onChange={(e) => setPreset(e.target.value)} aria-label={isAr ? 'إعداد الإشعارات' : 'Notification preset'}>
                {options.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </Select>
            </label>
            <Button type="button" disabled={saving} onClick={() => void save()}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {isAr ? 'حفظ' : 'Save'}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
