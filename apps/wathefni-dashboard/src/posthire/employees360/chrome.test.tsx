import { describe, expect, test } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import { ApprovalStrip, ConflictBanner, MaskedField, RecordEpoch, WorkforceSectionRail } from './chrome'

describe('employees360 chrome', () => {
  test('RecordEpoch labels current / scheduled / historical', () => {
    expect(renderToStaticMarkup(<RecordEpoch epoch="current" />)).toContain('Current')
    expect(renderToStaticMarkup(<RecordEpoch epoch="scheduled" locale="ar" />)).toContain('مجدول')
    expect(renderToStaticMarkup(<RecordEpoch epoch="historical" />)).toContain('Historical')
  })

  test('MaskedField never shows plaintext when masked', () => {
    const html = renderToStaticMarkup(<MaskedField label="IBAN" masked value="KW81SECRET" />)
    expect(html).toContain('••••')
    expect(html).not.toContain('KW81SECRET')
  })

  test('ApprovalStrip shows next approver', () => {
    const html = renderToStaticMarkup(<ApprovalStrip state="pending_hr" nextApprover="HR" />)
    expect(html).toContain('pending hr')
    expect(html).toContain('Next:')
    expect(html).toContain('HR')
  })

  test('ConflictBanner is alert role', () => {
    const html = renderToStaticMarkup(<ConflictBanner detail="stale overlay" />)
    expect(html).toContain('role="alert"')
    expect(html).toContain('stale overlay')
  })

  test('WorkforceSectionRail marks selected tab', () => {
    const html = renderToStaticMarkup(
      <WorkforceSectionRail
        sections={[
          { id: 'organization', labelEn: 'Organization', labelAr: 'الهيكل' },
          { id: 'requests', labelEn: 'Requests', labelAr: 'الطلبات' },
        ]}
        active="requests"
        onChange={() => {}}
      />,
    )
    expect(html).toContain('aria-selected="true"')
    expect(html).toContain('Requests')
  })

  test('RTL dir on ApprovalStrip for ar', () => {
    const html = renderToStaticMarkup(<ApprovalStrip state="approved" locale="ar" />)
    expect(html).toContain('dir="rtl"')
  })
})
