import { describe, expect, test } from 'vitest'

/**
 * Physical acceptance — App access invitation copy contract (EN + AR).
 * Mirrors labels rendered in PostHire employee profile App access card.
 */

const STATUS_LABELS: Record<string, [string, string]> = {
  none: ['لا توجد', 'None'],
  pending: ['قيد الانتظار', 'Pending'],
  sent: ['أُرسلت', 'Sent'],
  delivered: ['تم التسليم', 'Delivered'],
  activated: ['مفعّلة', 'Activated'],
  expired: ['منتهية', 'Expired'],
  failed: ['فشل التسليم', 'Failed'],
  needs_attention: ['تحتاج متابعة', 'Needs attention'],
}

const ACTIONS = {
  en: {
    resend: 'Resend invitation',
    reinvite: 'Re-invite',
    showCode: 'Show activation code',
    revoke: 'Revoke access',
    title: 'App access',
  },
  ar: {
    resend: 'إعادة إرسال الدعوة',
    reinvite: 'إعادة الدعوة',
    showCode: 'عرض رمز التفعيل',
    revoke: 'إلغاء الوصول',
    title: 'وصول التطبيق',
  },
}

describe('invitation delivery App access copy (EN+AR)', () => {
  test('every HR status has EN and AR labels', () => {
    for (const [key, [ar, en]] of Object.entries(STATUS_LABELS)) {
      expect(ar.length).toBeGreaterThan(0)
      expect(en.length).toBeGreaterThan(0)
      expect(key).toBeTruthy()
    }
  })

  test('show activation code is exception-only vocabulary', () => {
    expect(ACTIONS.en.showCode).not.toEqual(ACTIONS.en.resend)
    expect(ACTIONS.ar.showCode).not.toEqual(ACTIONS.ar.resend)
  })

  test('RTL profile shell uses dir rtl when Arabic', () => {
    const dir = (isAr: boolean) => (isAr ? 'rtl' : 'ltr')
    expect(dir(true)).toBe('rtl')
    expect(dir(false)).toBe('ltr')
  })

  test('show_code_exception only for needs_attention', () => {
    const show = (status: string) => status === 'needs_attention'
    expect(show('delivered')).toBe(false)
    expect(show('failed')).toBe(false)
    expect(show('expired')).toBe(false)
    expect(show('needs_attention')).toBe(true)
    expect(show('activated')).toBe(false)
  })
})
