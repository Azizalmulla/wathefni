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

import { ApiError, rawRequest, type RequestOptions } from '@hr/api/client'
import type { AuthResponse, MobileMe } from '@hr/api/types'
import {
  AUTO_LOCK_DEFAULT_TIMEOUT_MS,
  clampAutoLockTimeout,
  type AutoLockTimeoutMs,
} from '@/auth/autoLockPolicy'
import { getBiometricAvailability, type BiometricKind } from '@/auth/biometricAuth'
import { PIN_MAX_FAILED_ATTEMPTS } from '@/auth/pinPolicy'
import { accessStateForError, requiresMeRefresh, type OperatorAccessState } from './access'
import {
  clearHrBiometricPreference,
  isHrBiometricPreferenceEnabled,
  markHrBiometricOffered,
  setHrBiometricPreference,
  wasHrBiometricOffered,
} from './localLock/hrBiometricStorage'
import { loadHrAutoLockTimeout, saveHrAutoLockTimeout } from './localLock/hrAutoLockStorage'
import {
  isHrLocalAutoLockEnabledFor,
  isHrLocalBiometricEnabledFor,
  isHrLocalPinEnabledFor,
} from './localLock/hrPolicy'
import {
  changeHrPin,
  clearHrPinMaterial,
  hasHrPinRecord,
  loadHrPinRecord,
  setHrPin,
  verifyHrPin,
} from './localLock/hrPinStorage'
import { operatorPrincipalKey } from './localLock/principalKey'
import {
  clearOperatorSession,
  loadOperatorSession,
  saveOperatorSession,
  type StoredOperatorSession,
} from './session'
import {
  bindOperatorSessionMemory,
  clearOperatorAuthIfNoNewerSession,
  resolveOperatorSession,
  rotateOperatorSession,
  setOperatorSessionListeners,
  storedOperatorSessionFromAuth,
} from './sessionCoordinator'

type AuthStatus =
  | 'loading'
  | 'signedOut'
  | 'signedIn'
  | 'blocked'
  | 'locked'
  | 'needsPinSetup'
  | 'needsBiometricOptIn'

type AuthContextValue = {
  status: AuthStatus
  accessState: OperatorAccessState
  me: MobileMe | null
  pinEnabled: boolean
  biometricEnabled: boolean
  biometricPreferenceOn: boolean
  biometricKind: BiometricKind
  autoLockTimeoutMs: AutoLockTimeoutMs
  setAutoLockTimeout: (value: AutoLockTimeoutMs) => Promise<void>
  signIn: (email: string, password: string, companyCode: string) => Promise<void>
  signOut: () => Promise<void>
  signOutAll: () => Promise<void>
  refreshMe: () => Promise<boolean>
  /** Current Bearer access token for streaming clients (Assistant SSE). */
  getAccessToken: () => string | null
  request: <T>(path: string, options?: Omit<RequestOptions, 'token'>) => Promise<T>
  createLocalPin: (pin: string) => Promise<void>
  unlockWithPin: (pin: string) => Promise<{ ok: boolean; lockedOut: boolean; failedAttempts: number }>
  unlockWithBiometric: () => Promise<boolean>
  /** Clear HR PIN + bio + operator session → email/password sign-in (not employee OTP). */
  recoverLocalLockByReauth: () => Promise<void>
  finishBiometricOptIn: (
    enable: boolean,
    labels?: { promptMessage: string; cancelLabel: string },
  ) => Promise<void>
  setBiometricUnlockEnabled: (
    enable: boolean,
    labels?: { promptMessage: string; cancelLabel: string },
  ) => Promise<{ ok: boolean; reason?: string }>
  changeLocalPin: (
    current: string,
    next: string,
  ) => Promise<{ ok: boolean; lockedOut: boolean; errorKey?: string }>
}

const AuthContext = createContext<AuthContextValue | null>(null)

function storedFromAuth(response: AuthResponse): StoredOperatorSession {
  return storedOperatorSessionFromAuth(response)
}

async function refreshTransport(refreshToken: string): Promise<AuthResponse> {
  return rawRequest<AuthResponse>('/dashboard/mobile/auth/refresh', {
    method: 'POST',
    json: { refresh_token: refreshToken },
  })
}

export function AuthProvider({ children, disabled = false }: { children: ReactNode; disabled?: boolean }) {
  const [status, setStatus] = useState<AuthStatus>(disabled ? 'signedOut' : 'loading')
  const [accessState, setAccessState] = useState<OperatorAccessState>('active')
  const [me, setMe] = useState<MobileMe | null>(null)
  const [biometricPreferenceOn, setBiometricPreferenceOn] = useState(false)
  const [biometricKind, setBiometricKind] = useState<BiometricKind>('biometrics')
  const [autoLockTimeoutMs, setAutoLockTimeoutMs] =
    useState<AutoLockTimeoutMs>(AUTO_LOCK_DEFAULT_TIMEOUT_MS)
  const sessionRef = useRef<StoredOperatorSession | null>(null)
  const sealedSessionRef = useRef<StoredOperatorSession | null>(null)
  const recoverInFlightRef = useRef(false)
  const statusRef = useRef<AuthStatus>(status)
  statusRef.current = status

  const adoptSession = useCallback((session: StoredOperatorSession) => {
    sessionRef.current = session
    bindOperatorSessionMemory(session)
  }, [])

  const principalKey = operatorPrincipalKey(me, sessionRef.current?.companyCode)
  const pinEnabled = isHrLocalPinEnabledFor(principalKey)
  const biometricEnabled = isHrLocalBiometricEnabledFor(principalKey)

  const clearLocalLockMaterial = useCallback(async () => {
    await Promise.all([clearHrPinMaterial(), clearHrBiometricPreference()])
    setBiometricPreferenceOn(false)
  }, [])

  const clearAllLocalAuth = useCallback(async () => {
    sessionRef.current = null
    sealedSessionRef.current = null
    bindOperatorSessionMemory(null)
    await Promise.all([clearOperatorSession(), clearLocalLockMaterial()])
    setMe(null)
    setAccessState('active')
  }, [clearLocalLockMaterial])

  const refreshBiometricState = useCallback(async () => {
    const [preferred, availability] = await Promise.all([
      isHrBiometricPreferenceEnabled(),
      getBiometricAvailability(),
    ])
    setBiometricPreferenceOn(preferred)
    setBiometricKind(availability.kind)
  }, [])

  const applySignedIn = useCallback(
    (nextMe: MobileMe) => {
      setMe(nextMe)
      setAccessState('active')
      setStatus('signedIn')
      void refreshBiometricState()
    },
    [refreshBiometricState],
  )

  /**
   * After network identity is known: enter PIN setup, cold lock, or signedIn.
   * Session may be live (setup) or sealed (lock).
   */
  const enterAfterIdentity = useCallback(
    async (nextMe: MobileMe, session: StoredOperatorSession, opts?: { freshLogin?: boolean }) => {
      const key = operatorPrincipalKey(nextMe, session.companyCode)
      const loadedTimeout = await loadHrAutoLockTimeout()
      setAutoLockTimeoutMs(clampAutoLockTimeout(loadedTimeout))

      if (!isHrLocalPinEnabledFor(key)) {
        sealedSessionRef.current = null
        adoptSession(session)
        await saveOperatorSession(session)
        applySignedIn(nextMe)
        return
      }

      const record = await loadHrPinRecord()
      if (record && record.principalKey !== key) {
        await clearLocalLockMaterial()
      }

      const hasPin = await hasHrPinRecord()
      if (!hasPin) {
        sealedSessionRef.current = null
        adoptSession(session)
        await saveOperatorSession(session)
        setMe(nextMe)
        setAccessState('active')
        setStatus('needsPinSetup')
        return
      }

      // Existing PIN for this principal → seal tokens until local unlock.
      // Local lock is never a logout: tokens stay in SecureStore + coordinator memory.
      sealedSessionRef.current = session
      sessionRef.current = null
      bindOperatorSessionMemory(session)
      await saveOperatorSession(session)
      setMe(nextMe)
      setAccessState('active')
      setStatus('locked')
      await refreshBiometricState()

      // Fresh password login with existing PIN still requires unlock (independent of Employee).
      void opts
    },
    [adoptSession, applySignedIn, clearLocalLockMaterial, refreshBiometricState],
  )

  const applyAuth = useCallback(
    async (response: AuthResponse, opts?: { freshLogin?: boolean }) => {
      const next = storedFromAuth(response)
      await enterAfterIdentity(response.me, next, opts)
      return next
    },
    [enterAfterIdentity],
  )

  const block = useCallback(async (error: unknown, force = false) => {
    const next = accessStateForError(error)
    if (next === 'unknown_error' && !force) return false

    // Security / lifecycle terminations always wipe operator tokens.
    if (next === 'operator_disabled' || next === 'company_disabled' || next === 'company_archived') {
      sessionRef.current = null
      sealedSessionRef.current = null
      bindOperatorSessionMemory(null)
      await clearOperatorSession()
      setAccessState(next)
      setStatus('blocked')
      return true
    }

    // Session refresh failures: adopt a newer SecureStore session when present.
    if (next === 'session_expired' || next === 'session_revoked') {
      const failedWith = sessionRef.current || sealedSessionRef.current
      const outcome = await clearOperatorAuthIfNoNewerSession(failedWith)
      if (outcome === 'adopted') {
        const adopted = await resolveOperatorSession(null)
        if (adopted) {
          if (statusRef.current === 'locked') {
            sealedSessionRef.current = adopted
            sessionRef.current = null
            bindOperatorSessionMemory(adopted)
          } else {
            adoptSession(adopted)
            sealedSessionRef.current = null
          }
          setAccessState('active')
          return false
        }
      }
      sessionRef.current = null
      sealedSessionRef.current = null
      // Keep PIN material so re-login for same principal can unlock — wipe only on
      // recoverLocalLockByReauth / signOut / principal mismatch.
      setAccessState(next)
      setStatus('blocked')
      return true
    }

    setAccessState(next)
    setStatus('blocked')
    return true
  }, [adoptSession])

  const rotate = useCallback(async (): Promise<StoredOperatorSession> => {
    const hint =
      sessionRef.current ||
      sealedSessionRef.current ||
      (await resolveOperatorSession(null))
    const next = await rotateOperatorSession(hint, refreshTransport)
    // Mid-session rotation must not force the local PIN lock.
    if (statusRef.current === 'locked') {
      sealedSessionRef.current = next
      sessionRef.current = null
      bindOperatorSessionMemory(next)
    } else {
      adoptSession(next)
      sealedSessionRef.current = null
    }
    setAccessState('active')
    if (statusRef.current === 'signedIn' || statusRef.current === 'needsBiometricOptIn') {
      setStatus(statusRef.current === 'needsBiometricOptIn' ? 'needsBiometricOptIn' : 'signedIn')
    }
    return next
  }, [adoptSession])

  useEffect(() => {
    setOperatorSessionListeners({
      onRotated: (session, nextMe) => {
        if (statusRef.current === 'locked') {
          sealedSessionRef.current = session
          sessionRef.current = null
        } else {
          sessionRef.current = session
        }
        setMe(nextMe)
        setAccessState('active')
      },
    })
    return () => setOperatorSessionListeners({})
  }, [])

  const refreshMe = useCallback(async (): Promise<boolean> => {
    const current =
      sessionRef.current ||
      (statusRef.current === 'locked' ? null : await resolveOperatorSession(null))
    if (!current) {
      if (
        statusRef.current === 'locked' ||
        statusRef.current === 'needsPinSetup' ||
        statusRef.current === 'needsBiometricOptIn'
      ) {
        return false
      }
      setStatus('signedOut')
      return false
    }
    try {
      const next = await rawRequest<MobileMe>('/dashboard/mobile/me', {
        token: current.accessToken,
      })
      adoptSession(current)
      setMe(next)
      setAccessState('active')
      if (statusRef.current === 'signedIn' || statusRef.current === 'loading') {
        setStatus('signedIn')
      }
      return true
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        try {
          const rotated = await rotate()
          const next = await rawRequest<MobileMe>('/dashboard/mobile/me', {
            token: rotated.accessToken,
          })
          setMe(next)
          setAccessState('active')
          if (statusRef.current === 'signedIn' || statusRef.current === 'loading') {
            setStatus('signedIn')
          }
          return true
        } catch (refreshError) {
          await block(refreshError, true)
          return false
        }
      }
      await block(error, true)
      return false
    }
  }, [adoptSession, block, rotate])

  useEffect(() => {
    if (disabled) return
    let active = true
    void (async () => {
      const stored = await resolveOperatorSession(await loadOperatorSession())
      if (!active) return
      if (!stored) {
        setStatus('signedOut')
        return
      }
      bindOperatorSessionMemory(stored)
      try {
        const next = await rawRequest<MobileMe>('/dashboard/mobile/me', {
          token: stored.accessToken,
        })
        if (!active) return
        await enterAfterIdentity(next, stored)
      } catch (error) {
        if (!active) return
        if (error instanceof ApiError && error.status === 401) {
          try {
            const rotated = await rotate()
            if (!active) {
              // Remount abandoned this boot — tokens already persisted atomically.
              return
            }
            const next = await rawRequest<MobileMe>('/dashboard/mobile/me', {
              token: rotated.accessToken,
            })
            await enterAfterIdentity(next, rotated)
            return
          } catch (refreshError) {
            if (!active) return
            await block(refreshError, true)
            return
          }
        }
        await block(error, true)
      }
    })()
    return () => {
      active = false
    }
    // Boot once per mount. Refresh single-flight lives outside this instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disabled])

  // Soft /me refresh only when unlocked — LocalUnlockShell owns background lock.
  useEffect(() => {
    if (disabled) return
    const subscription = AppState.addEventListener('change', (next) => {
      if (next === 'active' && sessionRef.current && statusRef.current === 'signedIn') {
        void refreshMe()
      }
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
        await applyAuth(response, { freshLogin: true })
      } catch (error) {
        const next = accessStateForError(error)
        if (next !== 'unknown_error' && next !== 'rate_limited') await block(error, true)
        throw error
      }
    },
    [applyAuth, block],
  )

  const recoverLocalLockByReauth = useCallback(async () => {
    if (recoverInFlightRef.current) return
    recoverInFlightRef.current = true
    try {
      const token =
        sealedSessionRef.current?.accessToken || sessionRef.current?.accessToken
      const refresh =
        sealedSessionRef.current?.refreshToken || sessionRef.current?.refreshToken
      if (token) {
        try {
          await rawRequest('/dashboard/mobile/auth/logout', {
            method: 'POST',
            token,
            json: refresh ? { refresh_token: refresh } : undefined,
          })
        } catch {
          // Local clear is authoritative.
        }
      }
      await clearAllLocalAuth()
      setStatus('signedOut')
    } finally {
      recoverInFlightRef.current = false
    }
  }, [clearAllLocalAuth])

  const signOut = useCallback(async () => {
    const current = sessionRef.current || sealedSessionRef.current
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
    await clearAllLocalAuth()
    setStatus('signedOut')
  }, [clearAllLocalAuth])

  const signOutAll = useCallback(async () => {
    const current = sessionRef.current || sealedSessionRef.current
    if (current) {
      try {
        await rawRequest('/dashboard/mobile/auth/logout-all', {
          method: 'POST',
          token: current.accessToken,
        })
      } catch {
        // Fall through to local clear.
      }
    }
    await clearAllLocalAuth()
    setStatus('signedOut')
  }, [clearAllLocalAuth])

  const unlockSealedSession = useCallback(async (): Promise<'ok' | 'missing' | 'blocked'> => {
    let sealed = sealedSessionRef.current
    if (!sealed) {
      sealed = await resolveOperatorSession(await loadOperatorSession())
      if (!sealed) {
        await recoverLocalLockByReauth()
        return 'missing'
      }
      sealedSessionRef.current = sealed
    }
    adoptSession(sealed)
    sealedSessionRef.current = null
    try {
      const next = await rawRequest<MobileMe>('/dashboard/mobile/me', {
        token: sealed.accessToken,
      })
      applySignedIn(next)
      return 'ok'
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        try {
          const rotated = await rotate()
          const next = await rawRequest<MobileMe>('/dashboard/mobile/me', {
            token: rotated.accessToken,
          })
          applySignedIn(next)
          return 'ok'
        } catch (refreshError) {
          const blocked = await block(refreshError, true)
          if (!blocked) {
            try {
              const adopted = await resolveOperatorSession(null)
              if (adopted) {
                adoptSession(adopted)
                sealedSessionRef.current = null
                const next = await rawRequest<MobileMe>('/dashboard/mobile/me', {
                  token: adopted.accessToken,
                })
                applySignedIn(next)
                return 'ok'
              }
            } catch {
              // Fall through to blocked — no newer usable session.
            }
          }
          const stored = await resolveOperatorSession(null)
          if (stored) {
            sealedSessionRef.current = stored
            sessionRef.current = null
            setStatus('locked')
          }
          return 'blocked'
        }
      }
      await block(error, true)
      const stored = await resolveOperatorSession(null)
      if (stored) {
        sealedSessionRef.current = stored
        sessionRef.current = null
        setStatus('locked')
      }
      return 'blocked'
    }
  }, [adoptSession, applySignedIn, block, recoverLocalLockByReauth, rotate])

  const createLocalPin = useCallback(
    async (pin: string) => {
      const key = operatorPrincipalKey(me, sessionRef.current?.companyCode)
      if (!isHrLocalPinEnabledFor(key)) throw new Error('pin_not_enabled')
      await setHrPin(key, pin)
      if (!(sessionRef.current && me)) {
        setStatus('signedOut')
        return
      }
      if (isHrLocalBiometricEnabledFor(key)) {
        const availability = await getBiometricAvailability()
        setBiometricKind(availability.kind)
        if (availability.usable) {
          setStatus('needsBiometricOptIn')
          return
        }
        await markHrBiometricOffered()
      }
      applySignedIn(me)
    },
    [applySignedIn, me],
  )

  const unlockWithPin = useCallback(
    async (pin: string) => {
      const result = await verifyHrPin(pin)
      if (result.ok) {
        const outcome = await unlockSealedSession()
        if (outcome === 'ok') return { ok: true, lockedOut: false, failedAttempts: 0 }
        return { ok: false, lockedOut: false, failedAttempts: 0 }
      }
      if (result.lockedOut) {
        await recoverLocalLockByReauth()
      }
      return { ok: false, lockedOut: result.lockedOut, failedAttempts: result.failedAttempts }
    },
    [recoverLocalLockByReauth, unlockSealedSession],
  )

  const unlockWithBiometric = useCallback(async () => {
    const key = operatorPrincipalKey(me, sealedSessionRef.current?.companyCode)
    if (!isHrLocalBiometricEnabledFor(key)) return false
    const preferred = await isHrBiometricPreferenceEnabled()
    if (!preferred) return false
    return (await unlockSealedSession()) === 'ok'
  }, [me, unlockSealedSession])

  const resumeAfterBiometricOptIn = useCallback(async () => {
    if (sessionRef.current && me) {
      applySignedIn(me)
      return
    }
    if (sealedSessionRef.current || (await loadOperatorSession())) {
      const outcome = await unlockSealedSession()
      if (outcome === 'ok') return
      if (!sessionRef.current && !sealedSessionRef.current) {
        const stored = await loadOperatorSession()
        if (stored) {
          sealedSessionRef.current = stored
          setStatus('locked')
        }
      }
      return
    }
    setStatus('signedOut')
  }, [applySignedIn, me, unlockSealedSession])

  const finishBiometricOptIn = useCallback(
    async (enable: boolean, labels?: { promptMessage: string; cancelLabel: string }) => {
      if (enable) {
        const availability = await getBiometricAvailability()
        if (!availability.usable) {
          await markHrBiometricOffered()
          setBiometricPreferenceOn(false)
          await resumeAfterBiometricOptIn()
          return
        }
        const { promptBiometricUnlock } = await import('./localLock/hrBiometricAuth')
        const result = await promptBiometricUnlock({
          promptMessage: labels?.promptMessage || 'Unlock OctoHR',
          cancelLabel: labels?.cancelLabel || 'Cancel',
        })
        if (!result.ok) {
          await markHrBiometricOffered()
          setBiometricPreferenceOn(false)
          await resumeAfterBiometricOptIn()
          return
        }
        await setHrBiometricPreference(true, availability.enrolledLevel)
        setBiometricPreferenceOn(true)
        setBiometricKind(availability.kind)
      } else {
        await markHrBiometricOffered()
        setBiometricPreferenceOn(false)
      }
      await resumeAfterBiometricOptIn()
    },
    [resumeAfterBiometricOptIn],
  )

  const setBiometricUnlockEnabled = useCallback(
    async (
      enable: boolean,
      labels?: { promptMessage: string; cancelLabel: string },
    ): Promise<{ ok: boolean; reason?: string }> => {
      const key = operatorPrincipalKey(me, sessionRef.current?.companyCode)
      if (!isHrLocalBiometricEnabledFor(key)) return { ok: false, reason: 'unavailable' }
      const availability = await getBiometricAvailability()
      setBiometricKind(availability.kind)
      if (!enable) {
        await setHrBiometricPreference(false, 0)
        setBiometricPreferenceOn(false)
        return { ok: true }
      }
      if (!availability.usable) return { ok: false, reason: 'unavailable' }
      const { promptBiometricUnlock } = await import('./localLock/hrBiometricAuth')
      const result = await promptBiometricUnlock({
        promptMessage: labels?.promptMessage || 'Unlock OctoHR',
        cancelLabel: labels?.cancelLabel || 'Cancel',
      })
      if (!result.ok) return { ok: false, reason: result.reason }
      await setHrBiometricPreference(true, availability.enrolledLevel)
      setBiometricPreferenceOn(true)
      return { ok: true }
    },
    [me],
  )

  const changeLocalPin = useCallback(
    async (current: string, next: string) => {
      const result = await changeHrPin(current, next)
      if (result.ok) return { ok: true, lockedOut: false }
      if (result.lockedOut) {
        await recoverLocalLockByReauth()
        return { ok: false, lockedOut: true, errorKey: 'hrPin.tooManyAttempts' }
      }
      return { ok: false, lockedOut: false, errorKey: 'pin.wrong' }
    },
    [recoverLocalLockByReauth],
  )

  const setAutoLockTimeout = useCallback(async (value: AutoLockTimeoutMs) => {
    const next = clampAutoLockTimeout(value)
    setAutoLockTimeoutMs(next)
    await saveHrAutoLockTimeout(next)
  }, [])

  const request = useCallback(
    async <T,>(path: string, options: Omit<RequestOptions, 'token'> = {}): Promise<T> => {
      const current = sessionRef.current || (await resolveOperatorSession(null))
      if (!current) throw new ApiError(401, 'session_expired', 'Please sign in again.')
      if (!sessionRef.current) adoptSession(current)
      try {
        return await rawRequest<T>(path, { ...options, token: current.accessToken })
      } catch (error) {
        // Access expiry / session codes: one global refresh, then retry with new access.
        if (error instanceof ApiError && error.status === 401) {
          try {
            const rotated = await rotate()
            return await rawRequest<T>(path, { ...options, token: rotated.accessToken })
          } catch (refreshError) {
            const blocked = await block(refreshError, true)
            if (!blocked) {
              const adopted = await resolveOperatorSession(null)
              if (adopted) {
                adoptSession(adopted)
                return await rawRequest<T>(path, { ...options, token: adopted.accessToken })
              }
            }
            throw refreshError
          }
        }
        if (requiresMeRefresh(error)) await refreshMe()
        else await block(error)
        throw error
      }
    },
    [adoptSession, block, refreshMe, rotate],
  )

  const getAccessToken = useCallback(() => {
    return (
      sealedSessionRef.current?.accessToken ||
      sessionRef.current?.accessToken ||
      null
    )
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      accessState,
      me,
      pinEnabled,
      biometricEnabled,
      biometricPreferenceOn,
      biometricKind,
      autoLockTimeoutMs,
      setAutoLockTimeout,
      signIn,
      signOut,
      signOutAll,
      refreshMe,
      getAccessToken,
      request,
      createLocalPin,
      unlockWithPin,
      unlockWithBiometric,
      recoverLocalLockByReauth,
      finishBiometricOptIn,
      setBiometricUnlockEnabled,
      changeLocalPin,
    }),
    [
      status,
      accessState,
      me,
      pinEnabled,
      biometricEnabled,
      biometricPreferenceOn,
      biometricKind,
      autoLockTimeoutMs,
      setAutoLockTimeout,
      signIn,
      signOut,
      signOutAll,
      refreshMe,
      getAccessToken,
      request,
      createLocalPin,
      unlockWithPin,
      unlockWithBiometric,
      recoverLocalLockByReauth,
      finishBiometricOptIn,
      setBiometricUnlockEnabled,
      changeLocalPin,
    ],
  )

  // Silence unused import warning when masters off — keep PIN_MAX for overlays via re-export path.
  void PIN_MAX_FAILED_ATTEMPTS
  void isHrLocalAutoLockEnabledFor
  void wasHrBiometricOffered

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
