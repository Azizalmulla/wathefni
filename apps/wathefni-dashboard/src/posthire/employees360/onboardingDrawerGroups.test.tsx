import { describe, expect, test } from 'vitest'

import {
  HR_OWNERSHIP_GROUP_LABELS,
  hrOwnershipGroupForItem,
  ownerLabel,
} from './onboardingDrawerGroups'

describe('onboarding drawer ownership groups', () => {
  test('maps lifecycle groups to HR-facing buckets', () => {
    expect(hrOwnershipGroupForItem({ group: 'being_reviewed', status: 'processing' })).toBe('being_reviewed')
    expect(hrOwnershipGroupForItem({ group: 'your_actions', status: 'pending' })).toBe('your_actions')
    expect(hrOwnershipGroupForItem({ group: 'handled_by_others', status: 'pending' })).toBe('handled_by_others')
    expect(hrOwnershipGroupForItem({ status: 'accepted' })).toBe('completed')
  })

  test('labels are bilingual', () => {
    expect(HR_OWNERSHIP_GROUP_LABELS.being_reviewed.en).toContain('Needs HR')
    expect(HR_OWNERSHIP_GROUP_LABELS.being_reviewed.ar).toBeTruthy()
    expect(ownerLabel({ owner: 'hr' }, false)).toBe('HR')
    expect(ownerLabel({ owner: 'employee' }, true)).toBe('الموظف')
  })
})
