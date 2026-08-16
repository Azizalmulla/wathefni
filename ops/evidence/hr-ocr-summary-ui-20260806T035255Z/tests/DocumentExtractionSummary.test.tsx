import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, test } from 'vitest'

import { DocumentExtractionSummary, maskDocumentNumber } from './DocumentExtractionSummary'

describe('DocumentExtractionSummary', () => {
  test('masks document numbers by default', () => {
    expect(maskDocumentNumber('A12345678')).toMatch(/•+5678/)
    const html = renderToStaticMarkup(
      <DocumentExtractionSummary
        locale="en"
        canRevealSensitive
        ocrProposal={{
          document_type: 'passport',
          full_name_en: 'ABDULAZIZ H R ALMULLA',
          document_number: 'A12345678',
          nationality: 'Kuwaiti',
          date_of_birth: '1990-01-15',
          expiry_date: '2032-05-31',
          extraction_status: 'needs_review',
          confidence: 0.82,
          identity_check: { status: 'matched', match: true },
          authoritative: false,
        }}
      />,
    )
    expect(html).toContain('Extraction &amp; validation summary')
    expect(html).toContain('Extracted — not auto-verified')
    expect(html).toContain('ABDULAZIZ H R ALMULLA')
    expect(html).toContain('Kuwaiti')
    expect(html).toContain('2032-05-31')
    expect(html).toContain('Name matched')
    expect(html).not.toContain('A12345678')
    expect(html).toContain('Reveal number (authorized)')
    expect(html).toContain('never overwrite canonical employee data')
  })

  test('renders Civil ID front/back and pair status', () => {
    const html = renderToStaticMarkup(
      <DocumentExtractionSummary
        locale="en"
        ocrProposal={{
          document_number: '290000001234',
          expiry_date: '2030-01-14',
          pair_validated_at: '2026-08-06T03:25:59Z',
          hr_warnings: ['soft_side_warning'],
          parts_schema: 'civil_id_v1',
          parts: {
            front: { side: 'front', full_name_en: 'ABDULAZIZ', document_number: '290000001234' },
            back: { side: 'back', nationality: 'Kuwaiti' },
          },
          authoritative: false,
        }}
      />,
    )
    expect(html).toContain('Civil ID — both sides')
    expect(html).toContain('Front')
    expect(html).toContain('Back')
    expect(html).toContain('Pair complete')
    expect(html).toContain('soft_side_warning')
  })

  test('distinguishes verified HR-saved values', () => {
    const html = renderToStaticMarkup(
      <DocumentExtractionSummary
        locale="ar"
        ocrProposal={{ full_name_ar: 'عبد العزيز', expiry_date: '2030-01-01', authoritative: false }}
        verified={{ issue_date: '2022-01-01', expiry_date: '2030-01-01', review_status: 'مراجعة موارد بشرية' }}
      />,
    )
    expect(html).toContain('قيم مستخرجة (اقتراح)')
    expect(html).toContain('قيم معتمدة / محفوظة بعد المراجعة')
    expect(html).toContain('عبد العزيز')
  })

  test('empty state when no proposal', () => {
    const html = renderToStaticMarkup(<DocumentExtractionSummary locale="en" ocrProposal={null} />)
    expect(html).toContain('No stored extraction summary')
  })
})
