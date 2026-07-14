import { beforeEach, describe, expect, it, vi } from 'vitest'

const { store, setItemAsync, getItemAsync, deleteItemAsync } = vi.hoisted(() => {
  const values = new Map<string, string>()
  return {
    store: values,
    setItemAsync: vi.fn(async (key: string, value: string, _options?: { keychainAccessible?: string }) => void values.set(key, value)),
    getItemAsync: vi.fn(async (key: string) => values.get(key) ?? null),
    deleteItemAsync: vi.fn(async (key: string) => void values.delete(key)),
  }
})

vi.mock('expo-secure-store', () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 'device-only',
  setItemAsync,
  getItemAsync,
  deleteItemAsync,
}))

import { clearOperatorSession, loadOperatorSession, saveOperatorSession } from './session'

describe('operator SecureStore session', () => {
  beforeEach(() => {
    store.clear()
    vi.clearAllMocks()
  })

  it('stores access and refresh material only in SecureStore', async () => {
    const session = {
      accessToken: 'opaque-access',
      refreshToken: 'opaque-refresh',
      companyCode: 'NORTHSTAR',
      expiresAt: '2026-07-14T08:00:00Z',
    }
    await saveOperatorSession(session)
    expect(await loadOperatorSession()).toEqual(session)
    expect(setItemAsync).toHaveBeenCalledTimes(4)
    expect(setItemAsync.mock.calls.every((call) => call[2]?.keychainAccessible === 'device-only')).toBe(true)
  })

  it('fails closed when one token is missing', async () => {
    await saveOperatorSession({
      accessToken: 'access',
      refreshToken: 'refresh',
      companyCode: 'NORTHSTAR',
      expiresAt: 'soon',
    })
    store.delete('wathefni.hr.refresh_token')
    expect(await loadOperatorSession()).toBeNull()
  })

  it('clears every session key on logout', async () => {
    await saveOperatorSession({
      accessToken: 'access',
      refreshToken: 'refresh',
      companyCode: 'NORTHSTAR',
      expiresAt: 'soon',
    })
    await clearOperatorSession()
    expect(store.size).toBe(0)
    expect(deleteItemAsync).toHaveBeenCalledTimes(4)
  })
})
