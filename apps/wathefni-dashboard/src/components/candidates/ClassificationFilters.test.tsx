import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  ClassificationCompactChip,
  ClassificationFilterBar,
  DEFAULT_CLASSIFICATION_FILTERS,
  classificationChipLabel,
  classificationFiltersFromSavedView,
  classificationFiltersToQuery,
} from '@/components/candidates/ClassificationFilters'

describe('ClassificationFilters helpers', () => {
  it('only surfaces non-empty chips', () => {
    expect(classificationChipLabel(null)).toBeNull()
    expect(classificationChipLabel('  ')).toBeNull()
    expect(classificationChipLabel('Technology · Software Engineer')).toBe('Technology · Software Engineer')
  })

  it('maps taxonomy filters to query params by node id', () => {
    expect(
      classificationFiltersToQuery({
        ...DEFAULT_CLASSIFICATION_FILTERS,
        dimensionNodes: {
          career_area: ['career.technology'],
          skill: ['skill.python', 'skill.sql'],
        },
        confidence: 'High',
        includeMediumAi: true,
      }),
    ).toEqual({
      classification_career_area: 'career.technology',
      classification_skill: 'skill.python,skill.sql',
      classification_authority: 'confirmed_or_high_ai',
      classification_confidence: 'High',
      classification_include_medium_ai: 'true',
    })
  })

  it('restores versioned saved-view classification payloads', () => {
    const restored = classificationFiltersFromSavedView({
      classification: {
        schema: 'classification-filters-v1',
        dimension_nodes: { career_area: ['career.finance'], likely_role: ['role.accountant'] },
        authority: 'confirmed_only',
        include_medium_ai: false,
      },
    })
    expect(restored.authority).toBe('confirmed_only')
    expect(restored.dimensionNodes.career_area).toEqual(['career.finance'])
    expect(restored.dimensionNodes.likely_role).toEqual(['role.accountant'])
  })
})

describe('ClassificationCompactChip', () => {
  it('renders advisory chip only when present', () => {
    const { rerender } = render(<ClassificationCompactChip chip={null} />)
    expect(screen.queryByTestId('classification-compact-chip')).toBeNull()
    rerender(<ClassificationCompactChip chip="Technology · Software Engineer" />)
    expect(screen.getByTestId('classification-compact-chip')).toHaveTextContent(
      'Advisory: Technology · Software Engineer',
    )
  })
})

describe('ClassificationFilterBar', () => {
  it('hides completely when disabled', () => {
    render(
      <ClassificationFilterBar
        enabled={false}
        onChange={() => undefined}
        value={DEFAULT_CLASSIFICATION_FILTERS}
      />,
    )
    expect(screen.queryByTestId('classification-filter-bar')).toBeNull()
  })

  it('renders taxonomy-driven dimension controls when enabled', () => {
    render(
      <ClassificationFilterBar
        dimensions={[
          {
            dimension: 'career_area',
            node_type: 'career_area',
            nodes: [{ node_id: 'career.technology', label_en: 'Technology', label_ar: 'تقنية', broad: true }],
          },
        ]}
        enabled
        onChange={() => undefined}
        value={DEFAULT_CLASSIFICATION_FILTERS}
      />,
    )
    expect(screen.getByTestId('classification-filter-bar')).toHaveTextContent('Include medium suggestions')
    expect(screen.getByTestId('classification-filter-career_area')).toBeTruthy()
    expect(screen.getByTestId('classification-authority-filter')).toBeTruthy()
    expect(screen.getByTestId('classification-confidence-filter')).toBeTruthy()
    expect(screen.getByTestId('classification-filter-bar')).toHaveTextContent('Expertise filters')
    expect(screen.getByTestId('classification-filter-bar')).not.toHaveTextContent('taxonomy node IDs')
    expect(screen.getByTestId('classification-filter-bar')).not.toHaveTextContent(' · tenant')
  })
})
