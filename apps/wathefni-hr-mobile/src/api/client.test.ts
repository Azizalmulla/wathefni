import { describe, expect, it } from 'vitest'

import { rawRequest } from './client'

describe('approved HR API boundary', () => {
  it.each(['/app/auth/login', '/app/me', '/dashboard/setup/readiness', '/ai-recruiter/candidates'])(
    'rejects forbidden path %s before any network request',
    async (path) => {
      await expect(rawRequest(path)).rejects.toMatchObject({
        code: 'unapproved_api_path',
      })
    },
  )

  it('accepts only the dedicated mobile namespace', async () => {
    await expect(rawRequest('/dashboard/mobile/me')).rejects.toMatchObject({
      code: 'api_not_configured',
    })
  })
})
