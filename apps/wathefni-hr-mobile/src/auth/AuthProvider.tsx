import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { AppState } from 'react-native'

import { ApiError, rawRequest, type RequestOptions } from '@/api/client'
import type { AuthResponse, MobileMe } from '@/api/types'
import { accessStateForError, requiresMeRefresh, type OperatorAccessState } from './access'
import {
  clearOperatorSession,
  loadOperatorSession,
  saveOperatorSession,
  type StoredOperatorSession,
} from './session'

type AuthStatus = 'loading' | 'signedOut' | 'signedIn' | 'blocked'

type AuthContextValue = {
  status: AuthStatus
  accessState: OperatorAccessState
  me: MobileMe | null
  signIn: (email: string, password: string, companyCode: string) => Promise<void>
  signOut: () => Promise<void>
  signOutAll: () => Promise<void>
  refreshMe: () => Promise<boolean>
  request: <T>(path: string, options?: Omit<RequestOptions, 'token'>) => Promise<T>
}

const AuthContext = createContext<AuthContextValue | null>(null)
const sessionAuthCodes = new Set(['session_expired', 'session_revoked'])

function storedFromAuth(response: AuthResponse): StoredOperatorSession {
  return {
    accessToken: response.access_token,
    refreshToken: response.refresh_token,
    companyCode: response.me.principal.company_code,
    expiresAt: response.expires_at,
  }
}

export function AuthProvider({ children, disabled = false }: { children: ReactNode; disabled?: boolean }) {
  const [status, setStatus] = useState<AuthStatus>(disabled ? 'signedOut' : 'loading')
  const [accessState, setAccessState] = useState<OperatorAccessState>('active')
  const [me, setMe] = useState<MobileMe | null>(null)
  const sessionRef = useRef<StoredOperatorSession | null>(null)
  const refreshRef = useRef<Promise<StoredOperatorSession> | null>(null)

  const applyAuth = useCallback(async (response: AuthResponse) => {
    const next = storedFromAuth(response)
    sessionRef.current = next
    await saveOperatorSession(next)
    setMe(response.me)
    setAccessState('active')
    setStatus('signedIn')
    return next
  }, [])

  const block = useCallback(async (error: unknown, force = false) => {
    const next = accessStateForError(error)
    if (next === 'unknown_error' && !force) return false
    if (
      next === 'session_expired' ||
      next === 'session_revoked' ||
      next === 'operator_disabled' ||
      next === 'company_disabled' ||
      next === 'company_archived'
    ) {
      sessionRef.current = null
      await clearOperatorSession()
    }
    setAccessState(next)
    setStatus('blocked')
    return true
  }, [])

  const rotate = useCallback(async (): Promise<StoredOperatorSession> => {
    if (refreshRef.current) return refreshRef.current
    const current = sessionRef.current
    if (!current) throw new ApiError(401, 'session_expired', 'Please sign in again.')
    const rotating = rawRequest<AuthResponse>('/dashboard/mobile/auth/refresh', {
      method: 'POST',
      json: { refresh_token: current.refreshToken },
    })
      .then(applyAuth)
      .finally(() => {
        refreshRef.current = null
      })
    refreshRef.current = rotating
    return rotating
  }, [applyAuth])

  const refreshMe = useCallback(async (): Promise<boolean> => {
    const current = sessionRef.current
    if (!current) {
      setStatus('signedOut')
      return false
    }
    try {
      const next = await rawRequest<MobileMe>('/dashboard/mobile/me', {
        token: current.accessToken,
      })
      setMe(next)
      setAccessState('active')
      setStatus('signedIn')
      return true
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        try {
          await rotate()
          return true
        } catch (refreshError) {
          await block(refreshError, true)
          return false
        }
      }
      await block(error, true)
      return false
    }
  }, [block, rotate])

  useEffect(() => {
    if (disabled) return
    let active = true
    void loadOperatorSession().then(async (stored) => {
      if (!active) return
      if (!stored) {
        setStatus('signedOut')
        return
      }
      sessionRef.current = stored
      await refreshMe()
    })
    return () => {
      active = false
    }
  }, [disabled, refreshMe])

  useEffect(() => {
    if (disabled) return
    const subscription = AppState.addEventListener('change', (next) => {
      if (next === 'active' && sessionRef.current) void refreshMe()
    })
    return () => subscription.remove()
  }, [disabled, refreshMe])

  const signIn = useCallback(
    async (email: string, password: string, companyCode: string) => {
      try {
        const response = await rawRequest<AuthResponse>('/dashboard/mobile/auth/login', {
          method: 'POST',
          json: { email, password, company_code: companyCode.trim().toUpperCase() },
        })
        await applyAuth(response)
      } catch (error) {
        const next = accessStateForError(error)
        if (next !== 'unknown_error' && next !== 'rate_limited') await block(error, true)
        throw error
      }
    },
    [applyAuth, block],
  )

  const signOut = useCallback(async () => {
    const current = sessionRef.current
    if (current) {
      try {
        await rawRequest('/dashboard/mobile/auth/logout', {
          method: 'POST',
          token: current.accessToken,
          json: { refresh_token: current.refreshToken },
        })
      } catch {
        // Local keystore clearing still signs this device out.
      }
    }
    sessionRef.current = null
    await clearOperatorSession()
    setMe(null)
    setAccessState('active')
    setStatus('signedOut')
  }, [])

  const signOutAll = useCallback(async () => {
    const current = sessionRef.current
    if (current) {
      await rawRequest('/dashboard/mobile/auth/logout-all', {
        method: 'POST',
        token: current.accessToken,
      })
    }
    await signOut()
  }, [signOut])

  const request = useCallback(
    async <T,>(path: string, options: Omit<RequestOptions, 'token'> = {}): Promise<T> => {
      const current = sessionRef.current
      if (!current) throw new ApiError(401, 'session_expired', 'Please sign in again.')
      try {
        return await rawRequest<T>(path, { ...options, token: current.accessToken })
      } catch (error) {
        if (error instanceof ApiError && error.status === 401 && sessionAuthCodes.has(error.code)) {
          try {
            const rotated = await rotate()
            return await rawRequest<T>(path, { ...options, token: rotated.accessToken })
          } catch (refreshError) {
            await block(refreshError, true)
            throw refreshError
          }
        }
        if (requiresMeRefresh(error)) await refreshMe()
        else await block(error)
        throw error
      }
    },
    [block, refreshMe, rotate],
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      accessState,
      me,
      signIn,
      signOut,
      signOutAll,
      refreshMe,
      request,
    }),
    [status, accessState, me, signIn, signOut, signOutAll, refreshMe, request],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
