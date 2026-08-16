import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Platform } from 'react-native'
import * as FileSystem from 'expo-file-system/legacy'
import * as Updates from 'expo-updates'
import { useQueryClient } from '@tanstack/react-query'

import { API_BASE_URL, ApiError, rawRequest } from '@/api/client'
import type { ActivateResponse, EmployeeFeatureKey, EmployeeProfile, MeResponse } from '@/api/types'
import {
  canUseFeatureAction,
  hasFeature as meHasFeature,
  type AppAccessState,
} from '@/capabilities'
import { clearSession, loadSession, saveSession, type StoredSession } from './session'
import { markReplacedDeviceNoticePending } from './deviceSecurityNotice'
import { isLocalPinEnabledFor, isLocalPinMasterEnabled } from './pinPolicy'
import { clearPinMaterial, hasPinRecord, loadPinRecord, setPin, verifyPin, changePin as changeStoredPin } from './pinStorage'
import { isLocalBiometricEnabledFor, isLocalBiometricMasterEnabled } from './biometricPolicy'
import {
  getBiometricAvailability,
  promptBiometricUnlock,
  type BiometricKind,
} from './biometricAuth'
import {
  clearBiometricPreference,
  disableBiometricPreference,
  isBiometricPreferenceEnabled,
  markBiometricOffered,
  setBiometricPreference,
  wasBiometricOffered,
} from './biometricStorage'
import {
  AUTO_LOCK_DEFAULT_TIMEOUT_MS,
  clampAutoLockTimeout,
  isLocalAutoLockEnabledFor,
  isLocalAutoLockMasterEnabled,
  type AutoLockTimeoutMs,
} from './autoLockPolicy'
import { loadAutoLockTimeout, saveAutoLockTimeout } from './autoLockStorage'
import { classifyAuthFailure, isDefinitiveAuthWipeError, markRefreshFailed, type AuthFailurePhase } from './authFailure'
import { consumeSkipUnlockOnce, clearLocaleRestartPreserveAuth, isLocaleRestartPreserveAuth } from './sessionResume'
import type { PickedFile } from '@/lib/uploadDocument'
import { clearInboxBadge } from '@/push/syncInboxBadge'

type AuthStatus =
  | 'loading'
  | 'signedOut'
  | 'signedIn'
  | 'blocked'
  | 'locked'
  | 'needsPinSetup'
  | 'needsBiometricOptIn'

export type TransferProgress = {
  transferred: number
  total: number
  progress: number
}

export type DocumentUploadResult = {
  ok?: boolean
  item_id?: string
  file_id?: string
  status?: string
  part?: string
  parts_complete?: boolean
  attempt_id?: string
  validation?: {
    gate?: string
    decision?: string
    reason?: string
    hr_review_recommended?: boolean
    message?: string
    message_en?: string
    message_ar?: string
  }
}

export type CancellableTransfer<T> = {
  promise: Promise<T>
  cancel: () => Promise<void>
}

type AuthContextValue = {
  status: AuthStatus
  accessState: AppAccessState
  profile: EmployeeProfile | null
  me: MeResponse | null
  pinEnabled: boolean
  biometricEnabled: boolean
  biometricPreferenceOn: boolean
  biometricKind: BiometricKind
  autoLockEnabled: boolean
  autoLockTimeoutMs: AutoLockTimeoutMs
  setAutoLockTimeout: (value: AutoLockTimeoutMs) => Promise<void>
  activate: (phone: string, code: string) => Promise<void>
  requestCode: (phone: string) => Promise<void>
  signOut: () => Promise<void>
  refreshMe: () => Promise<boolean>
  createLocalPin: (pin: string) => Promise<void>
  unlockWithPin: (pin: string) => Promise<{ ok: boolean; lockedOut: boolean; failedAttempts: number }>
  unlockWithBiometric: () => Promise<boolean>
  /** Clear PIN + biometric + session and return to activation (Forgot PIN / 5-fail). Local only. */
  recoverPinByReactivation: () => Promise<void>
  finishBiometricOptIn: (
    enable: boolean,
    labels?: { promptMessage: string; cancelLabel: string },
  ) => Promise<void>
  setBiometricUnlockEnabled: (
    enable: boolean,
    labels?: { promptMessage: string; cancelLabel: string },
  ) => Promise<{ ok: boolean; reason?: string }>
  changeLocalPin: (current: string, next: string) => Promise<{ ok: boolean; lockedOut: boolean; errorKey?: string }>
  hasFeature: (feature: EmployeeFeatureKey) => boolean
  can: (feature: EmployeeFeatureKey, action: string) => boolean
  request: <T>(path: string, opts?: { method?: 'GET' | 'POST'; json?: unknown; body?: FormData; signal?: AbortSignal }) => Promise<T>
  download: (path: string, target: string) => Promise<FileSystem.FileSystemDownloadResult>
  uploadFile: (
    path: string,
    file: PickedFile,
    parameters: Record<string, string>,
    onProgress?: (progress: TransferProgress) => void,
  ) => CancellableTransfer<DocumentUploadResult>
  downloadFile: (
    path: string,
    target: string,
    onProgress?: (progress: TransferProgress) => void,
  ) => CancellableTransfer<FileSystem.FileSystemDownloadResult>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [accessState, setAccessState] = useState<AppAccessState>('active')
  const [profile, setProfile] = useState<EmployeeProfile | null>(null)
  const [me, setMe] = useState<MeResponse | null>(null)
  const [biometricPreferenceOn, setBiometricPreferenceOn] = useState(false)
  const [biometricKind, setBiometricKind] = useState<BiometricKind>('biometrics')
  const [autoLockTimeoutMs, setAutoLockTimeoutMs] = useState<AutoLockTimeoutMs>(AUTO_LOCK_DEFAULT_TIMEOUT_MS)
  /** Employee key available while PIN-locked before /me is loaded. */
  const [unlockEmployeeKey, setUnlockEmployeeKey] = useState('')
  /** Only populated when unlocked / Wave 1 path — API clients read this. */
  const sessionRef = useRef<StoredSession | null>(null)
  /** Holds SecureStore tokens while PIN-locked so API clients cannot use them. */
  const sealedSessionRef = useRef<StoredSession | null>(null)
  const statusRef = useRef<AuthStatus>('loading')
  const autoLockTimeoutRef = useRef<AutoLockTimeoutMs>(AUTO_LOCK_DEFAULT_TIMEOUT_MS)
  const unlockEmployeeKeyRef = useRef('')

  const employeeKeyOf = (next: MeResponse | null | undefined) =>
    String(next?.employee?.employee_key || (next as { employee_key?: string } | null)?.employee_key || '').trim()

  statusRef.current = status
  autoLockTimeoutRef.current = autoLockTimeoutMs
  unlockEmployeeKeyRef.current = unlockEmployeeKey

  const applyMeSignedIn = useCallback((next: MeResponse) => {
    const key = employeeKeyOf(next)
    setMe(next)
    setProfile(next.employee)
    if (key) setUnlockEmployeeKey(key)
    setAccessState('active')
    setStatus('signedIn')
    void clearLocaleRestartPreserveAuth()
    void loadAutoLockTimeout().then((value) => {
      setAutoLockTimeoutMs(value)
      autoLockTimeoutRef.current = value
      console.warn('[autolock] timeout loaded', {
        timeoutMs: value,
        never: value == null,
        employeeKey: key || null,
        enabled: isLocalAutoLockEnabledFor(key),
        master: String(process.env.EXPO_PUBLIC_LOCAL_AUTO_LOCK || ''),
        pinMaster: String(process.env.EXPO_PUBLIC_LOCAL_PIN_UNLOCK || ''),
        updateId: Updates.updateId ?? null,
        updateCreatedAt:
          Updates.createdAt instanceof Date
            ? Updates.createdAt.toISOString()
            : Updates.createdAt
              ? String(Updates.createdAt)
              : null,
      })
    })
  }, [])

  const applyMeNeedsPin = useCallback((next: MeResponse) => {
    setMe(next)
    setProfile(next.employee)
    setAccessState('active')
    setStatus('needsPinSetup')
  }, [])

  const clearLocalAuthMaterial = useCallback(async () => {
    sessionRef.current = null
    sealedSessionRef.current = null
    await Promise.all([
      clearSession(),
      clearPinMaterial(),
      clearBiometricPreference(),
      clearInboxBadge(),
      clearLocaleRestartPreserveAuth(),
    ])
    queryClient.clear()
    setProfile(null)
    setMe(null)
    setBiometricPreferenceOn(false)
    setUnlockEmployeeKey('')
    setAccessState('active')
  }, [queryClient])

  const refreshBiometricState = useCallback(async () => {
    const [preferred, availability] = await Promise.all([
      isBiometricPreferenceEnabled(),
      getBiometricAvailability(),
    ])
    setBiometricPreferenceOn(preferred)
    setBiometricKind(availability.kind)
    return { preferred, availability }
  }, [])

  const logAuthDecision = useCallback((decision: ReturnType<typeof classifyAuthFailure>, error: unknown) => {
    const code = error instanceof ApiError ? error.code : 'non_api'
    const status = error instanceof ApiError ? error.status : 0
    console.warn(
      `[auth] decision wipe=${decision.wipeLocalSession} block=${decision.blockApp} state=${decision.accessState} reason=${decision.reason} code=${code} status=${status}`,
    )
  }, [])

  /**
   * Central wipe/soft-block gate. Screens must not clear SecureStore independently.
   * Locale-restart preserve never wipes.
   */
  const applyAuthFailure = useCallback(
    async (error: unknown, phase: AuthFailurePhase): Promise<ReturnType<typeof classifyAuthFailure>> => {
      const preserving = await isLocaleRestartPreserveAuth()
      let decision = classifyAuthFailure(error, phase)
      if (preserving && decision.wipeLocalSession) {
        decision = {
          ...decision,
          wipeLocalSession: false,
          // Never show "Session expired" during language restart — keep retryable state.
          accessState: decision.accessState === 'employee_inactive' ? 'employee_inactive' : 'unknown_error',
          blockApp: true,
          reason: `locale_preserve:${decision.reason}`,
        }
      }
      logAuthDecision(decision, error)
      if (decision.wipeLocalSession) {
        console.warn(`[auth] clearing local session material reason=${decision.reason}`)
        await clearLocalAuthMaterial()
        setAccessState(decision.accessState)
        setStatus('blocked')
        return decision
      }
      if (decision.blockApp) {
        setAccessState(decision.accessState)
        setStatus('blocked')
      }
      return decision
    },
    [clearLocalAuthMaterial, logAuthDecision],
  )

  // Legacy name kept for call-site clarity during Phase 1 hardening.
  const blockForError = useCallback(
    async (error: unknown, phase: AuthFailurePhase = 'api'): Promise<boolean> => {
      const decision = await applyAuthFailure(error, phase)
      return decision.blockApp || decision.wipeLocalSession
    },
    [applyAuthFailure],
  )

  const refreshMe = useCallback(async (): Promise<boolean> => {
    const current = sessionRef.current
    if (!current) {
      if (status === 'locked' || status === 'needsPinSetup' || status === 'needsBiometricOptIn') return false
      // Do not invent logout when briefly unlocked without an in-memory session.
      const stored = await loadSession()
      if (!stored) {
        setStatus('signedOut')
        return false
      }
      sessionRef.current = stored
    }
    const active = sessionRef.current
    if (!active) {
      setStatus('signedOut')
      return false
    }
    try {
      const loaded = await loadCurrentMe(active)
      sessionRef.current = loaded.session
      applyMeSignedIn(loaded.me)
      return true
    } catch (error) {
      await blockForError(error, 'refresh_me')
      return false
    }
  }, [applyMeSignedIn, blockForError, status])

  const enterAfterIdentity = useCallback(
    async (next: MeResponse, session: StoredSession) => {
      const key = employeeKeyOf(next)
      if (isLocalPinEnabledFor(key)) {
        const existing = await hasPinRecord()
        if (!existing) {
          sessionRef.current = session
          sealedSessionRef.current = null
          applyMeNeedsPin(next)
          return
        }
        sealedSessionRef.current = session
        sessionRef.current = null
        setMe(next)
        setProfile(next.employee)
        setUnlockEmployeeKey(key)
        setAccessState('active')
        // One-time Face ID offer if PIN exists but opt-in never ran (e.g. prior gating bug).
        if (isLocalBiometricEnabledFor(key) && !(await wasBiometricOffered()) && !(await isBiometricPreferenceEnabled())) {
          const availability = await getBiometricAvailability()
          setBiometricKind(availability.kind)
          if (availability.usable) {
            setStatus('needsBiometricOptIn')
            return
          }
          await markBiometricOffered()
        }
        setStatus('locked')
        return
      }
      sessionRef.current = session
      sealedSessionRef.current = null
      applyMeSignedIn(next)
    },
    [applyMeNeedsPin, applyMeSignedIn],
  )

  useEffect(() => {
    let active = true
    void (async () => {
      const loadedTimeout = await loadAutoLockTimeout()
      if (!active) return
      setAutoLockTimeoutMs(loadedTimeout)
      autoLockTimeoutRef.current = loadedTimeout
      console.warn('[autolock] boot config', {
        timeoutMs: loadedTimeout,
        never: loadedTimeout == null,
        autoLockEnv: String(process.env.EXPO_PUBLIC_LOCAL_AUTO_LOCK || ''),
        pinEnv: String(process.env.EXPO_PUBLIC_LOCAL_PIN_UNLOCK || ''),
        autoLockMaster: isLocalAutoLockMasterEnabled(),
        pinMaster: isLocalPinMasterEnabled(),
        updateId: Updates.updateId ?? null,
        updateCreatedAt:
          Updates.createdAt instanceof Date
            ? Updates.createdAt.toISOString()
            : Updates.createdAt
              ? String(Updates.createdAt)
              : null,
        runtimeVersion: Updates.runtimeVersion ?? null,
        channel: Updates.channel ?? null,
      })

      const stored = await loadSession()
      if (!active) return
      if (!stored) {
        // Tokens missing — only clear restart markers; do not invent a session.
        await clearLocaleRestartPreserveAuth()
        setStatus('signedOut')
        return
      }

      const preserveLocaleRestart = await isLocaleRestartPreserveAuth()
      const skipUnlock = await consumeSkipUnlockOnce()

      const sealAndRequirePin = async (employeeKey?: string) => {
        sealedSessionRef.current = stored
        sessionRef.current = null
        setAccessState('active')
        const key = String(employeeKey || '').trim()
        if (key) setUnlockEmployeeKey(key)
        if (
          key &&
          isLocalBiometricEnabledFor(key) &&
          !(await wasBiometricOffered()) &&
          !(await isBiometricPreferenceEnabled())
        ) {
          const availability = await getBiometricAvailability()
          setBiometricKind(availability.kind)
          console.warn('[biometric] boot offer gate', {
            usable: availability.usable,
            hardware: availability.hardware,
            enrolled: availability.enrolled,
            nativeModule: availability.nativeModule,
          })
          if (availability.usable) {
            setStatus('needsBiometricOptIn')
            return
          }
          await markBiometricOffered()
        }
        setStatus('locked')
      }

      if (!isLocalPinMasterEnabled()) {
        sessionRef.current = stored
        try {
          const loaded = await loadCurrentMe(stored)
          if (!active) return
          sessionRef.current = loaded.session
          applyMeSignedIn(loaded.me)
        } catch (error) {
          if (!active) return
          if (preserveLocaleRestart) {
            // Keep Wave 1 tokens; soft-block with retry — never OTP from language switch.
            sessionRef.current = stored
            await blockForError(error, 'boot')
            return
          }
          await blockForError(error, 'boot')
        }
        return
      }

      const pin = await loadPinRecord()
      if (pin) {
        setUnlockEmployeeKey(pin.employeeKey)
        // Intentional RTL restart: try seamless resume; on any /me failure fall back to PIN
        // unlock. Never treat language restart as logout / session wipe.
        if (preserveLocaleRestart || skipUnlock) {
          sessionRef.current = stored
          sealedSessionRef.current = null
          try {
            const loaded = await loadCurrentMe(stored)
            if (!active) return
            sessionRef.current = loaded.session
            applyMeSignedIn(loaded.me)
          } catch {
            if (!active) return
            await sealAndRequirePin(pin.employeeKey)
          }
          return
        }
        await sealAndRequirePin(pin.employeeKey)
        return
      }

      sessionRef.current = stored
      try {
        const loaded = await loadCurrentMe(stored)
        if (!active) return
        sessionRef.current = loaded.session
        await enterAfterIdentity(loaded.me, loaded.session)
        await clearLocaleRestartPreserveAuth()
      } catch (error) {
        if (!active) return
        if (preserveLocaleRestart) {
          sessionRef.current = stored
          await blockForError(error, 'boot')
          return
        }
        await blockForError(error, 'boot')
      }
    })()
    return () => {
      active = false
    }
    // Boot once — PIN gate must not re-run on every refreshMe identity change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Phase 3 AppState auto-lock removed from AuthProvider.
  // Overlay controller lives in LocalUnlockShell — never setStatus('locked') from AppState.

  const setAutoLockTimeout = useCallback(async (value: AutoLockTimeoutMs) => {
    const next = clampAutoLockTimeout(value)
    setAutoLockTimeoutMs(next)
    autoLockTimeoutRef.current = next
    console.warn('[autolock] timeout saved', { timeoutMs: next, never: next == null })
    await saveAutoLockTimeout(next)
  }, [])

  const persist = useCallback(async (token: string, refreshToken: string) => {
    const next = { token, refreshToken }
    sessionRef.current = next
    sealedSessionRef.current = null
    await saveSession(next)
  }, [])

  const activate = useCallback(
    async (phone: string, code: string) => {
      const res = await rawRequest<ActivateResponse>('/app/auth/activate', {
        method: 'POST',
        json: { phone, code, platform: Platform.OS === 'ios' ? 'ios' : Platform.OS === 'android' ? 'android' : undefined },
      })
      await persist(res.token, res.refresh_token)
      if (res.replaced_previous_device) {
        await markReplacedDeviceNoticePending()
      }
      try {
        const current = sessionRef.current
        if (!current) throw new ApiError(401, 'app_auth_failed', 'Please sign in again.')
        const loaded = await loadCurrentMe(current)
        // Fresh OTP activation always restarts PIN setup for canary employees.
        if (isLocalPinEnabledFor(employeeKeyOf(loaded.me))) {
          await Promise.all([clearPinMaterial(), clearBiometricPreference()])
          setBiometricPreferenceOn(false)
        }
        await enterAfterIdentity(loaded.me, loaded.session)
      } catch (error) {
        await blockForError(error, 'activate')
        throw error
      }
    },
    [blockForError, enterAfterIdentity, persist],
  )

  const requestCode = useCallback(async (phone: string) => {
    await rawRequest('/app/auth/request-code', { method: 'POST', json: { phone } })
  }, [])

  const recoverInFlightRef = useRef(false)

  /**
   * Phase 4 — local PIN recovery only.
   * Clears PIN, biometric preference, and session → activation screen.
   * Never triggered by network/server errors. No new backend routes.
   */
  const recoverPinByReactivation = useCallback(async () => {
    if (recoverInFlightRef.current) return
    recoverInFlightRef.current = true
    try {
      const token = sealedSessionRef.current?.token || sessionRef.current?.token
      if (token) {
        try {
          await rawRequest('/app/auth/logout', { method: 'POST', token })
        } catch {
          // Best-effort — local clear is authoritative.
        }
      }
      await clearLocalAuthMaterial()
      setStatus('signedOut')
    } finally {
      recoverInFlightRef.current = false
    }
  }, [clearLocalAuthMaterial])

  const createLocalPin = useCallback(
    async (pin: string) => {
      const key = employeeKeyOf(me) || String(profile?.employee_key || '').trim()
      if (!isLocalPinEnabledFor(key)) throw new Error('pin_not_enabled')
      await setPin(key, pin)
      if (!(sessionRef.current && me)) {
        setStatus('signedOut')
        return
      }
      // Phase 2: offer biometric once after PIN create when Face ID / Touch ID is ready.
      if (isLocalBiometricEnabledFor(key)) {
        const availability = await getBiometricAvailability()
        setBiometricKind(availability.kind)
        console.warn('[biometric] after PIN create', {
          featureOn: true,
          usable: availability.usable,
          hardware: availability.hardware,
          enrolled: availability.enrolled,
          nativeModule: availability.nativeModule,
          enrolledLevel: availability.enrolledLevel,
        })
        if (availability.usable) {
          setStatus('needsBiometricOptIn')
          return
        }
        await markBiometricOffered()
      }
      applyMeSignedIn(me)
    },
    [applyMeSignedIn, me, profile?.employee_key],
  )

  const unlockSealedSession = useCallback(async (): Promise<'ok' | 'missing' | 'blocked'> => {
    let sealed = sealedSessionRef.current
    if (!sealed) {
      // Memory seal can be missing after biometric UI; SecureStore remains authoritative.
      sealed = await loadSession()
      if (!sealed) {
        await recoverPinByReactivation()
        return 'missing'
      }
      sealedSessionRef.current = sealed
    }
    sessionRef.current = sealed
    sealedSessionRef.current = null
    try {
      const loaded = await loadCurrentMe(sealed)
      sessionRef.current = loaded.session
      applyMeSignedIn(loaded.me)
      await refreshBiometricState()
      return 'ok'
    } catch (error) {
      // Classifier decides wipe vs soft-block. On soft failure keep PIN fallback.
      await blockForError(error, 'unlock')
      if (sessionRef.current) {
        sealedSessionRef.current = sessionRef.current
        sessionRef.current = null
        setStatus('locked')
      }
      return 'blocked'
    }
  }, [applyMeSignedIn, blockForError, refreshBiometricState, recoverPinByReactivation])

  const unlockWithPin = useCallback(
    async (pin: string) => {
      const result = await verifyPin(pin)
      if (result.ok) {
        const outcome = await unlockSealedSession()
        if (outcome === 'ok') return { ok: true, lockedOut: false, failedAttempts: 0 }
        if (outcome === 'missing') {
          // Correct PIN but no sealed session — not a 5-fail recovery.
          return { ok: false, lockedOut: false, failedAttempts: 0 }
        }
        return { ok: false, lockedOut: false, failedAttempts: 0 }
      }
      if (result.lockedOut) {
        await recoverPinByReactivation()
      }
      return { ok: false, lockedOut: result.lockedOut, failedAttempts: result.failedAttempts }
    },
    [recoverPinByReactivation, unlockSealedSession],
  )

  /** Local biometric unlock only — never authenticates with the backend. */
  const unlockWithBiometric = useCallback(async () => {
    const key = employeeKeyOf(me) || String(profile?.employee_key || '').trim() || unlockEmployeeKey
    if (!isLocalBiometricEnabledFor(key)) return false
    const preferred = await isBiometricPreferenceEnabled()
    if (!preferred) return false
    return (await unlockSealedSession()) === 'ok'
  }, [me, profile?.employee_key, unlockEmployeeKey, unlockSealedSession])

  /**
   * After Face ID opt-in enable/skip: never force OTP.
   * Prefer unsealing existing session; fall back to PIN lock; signedOut only if SecureStore is empty.
   */
  const resumeAfterBiometricOptIn = useCallback(async () => {
    if (sealedSessionRef.current || (await loadSession())) {
      const outcome = await unlockSealedSession()
      if (outcome === 'ok') return
      // Soft-blocked or still locked — PIN remains available; do not OTP.
      if (!sessionRef.current && !sealedSessionRef.current) {
        const stored = await loadSession()
        if (stored) {
          sealedSessionRef.current = stored
          setStatus('locked')
        }
      }
      return
    }
    if (sessionRef.current && me) {
      applyMeSignedIn(me)
      return
    }
    if (sessionRef.current) {
      try {
        const loaded = await loadCurrentMe(sessionRef.current)
        sessionRef.current = loaded.session
        applyMeSignedIn(loaded.me)
      } catch (error) {
        await blockForError(error, 'unlock')
        if (sessionRef.current) {
          sealedSessionRef.current = sessionRef.current
          sessionRef.current = null
          setStatus('locked')
        }
      }
      return
    }
    setStatus('signedOut')
  }, [applyMeSignedIn, blockForError, me, unlockSealedSession])

  const finishBiometricOptIn = useCallback(
    async (
      enable: boolean,
      labels?: { promptMessage: string; cancelLabel: string },
    ) => {
      await markBiometricOffered()

      const fallBackWithoutEnabling = async () => {
        await disableBiometricPreference()
        setBiometricPreferenceOn(false)
        // Skip / cancel / unavailable: keep session. PIN lock if sealed; else stay signed in.
        if (sealedSessionRef.current || (!(sessionRef.current && me) && (await loadSession()))) {
          if (!sealedSessionRef.current) {
            const stored = await loadSession()
            if (stored) sealedSessionRef.current = stored
          }
          sessionRef.current = null
          setStatus('locked')
          return
        }
        if (sessionRef.current && me) {
          applyMeSignedIn(me)
          return
        }
        await resumeAfterBiometricOptIn()
      }

      if (!enable) {
        await fallBackWithoutEnabling()
        return
      }

      const availability = await getBiometricAvailability()
      if (!availability.usable) {
        await fallBackWithoutEnabling()
        return
      }
      const prompted = await promptBiometricUnlock({
        promptMessage: labels?.promptMessage || 'Wathefni',
        cancelLabel: labels?.cancelLabel || 'Cancel',
      })
      if (!prompted.ok) {
        await fallBackWithoutEnabling()
        return
      }
      await setBiometricPreference(true, availability.enrolledLevel)
      setBiometricPreferenceOn(true)
      setBiometricKind(availability.kind)
      // Face ID already succeeded — open the existing local session (never OTP here).
      await resumeAfterBiometricOptIn()
    },
    [applyMeSignedIn, me, resumeAfterBiometricOptIn],
  )

  const setBiometricUnlockEnabled = useCallback(
    async (
      enable: boolean,
      labels?: { promptMessage: string; cancelLabel: string },
    ) => {
      const key = employeeKeyOf(me) || String(profile?.employee_key || '').trim()
      if (!isLocalBiometricEnabledFor(key)) return { ok: false, reason: 'unavailable' }
      if (!enable) {
        await disableBiometricPreference()
        setBiometricPreferenceOn(false)
        return { ok: true }
      }
      const availability = await getBiometricAvailability()
      setBiometricKind(availability.kind)
      if (!availability.usable) {
        await clearBiometricPreference()
        setBiometricPreferenceOn(false)
        return { ok: false, reason: 'unavailable' }
      }
      const prompted = await promptBiometricUnlock({
        promptMessage: labels?.promptMessage || 'Wathefni',
        cancelLabel: labels?.cancelLabel || 'Cancel',
      })
      if (!prompted.ok) {
        return { ok: false, reason: prompted.reason }
      }
      await setBiometricPreference(true, availability.enrolledLevel)
      setBiometricPreferenceOn(true)
      return { ok: true }
    },
    [me, profile?.employee_key],
  )

  const changeLocalPin = useCallback(
    async (current: string, next: string) => {
      const result = await changeStoredPin(current, next)
      if (result.ok) return { ok: true, lockedOut: false }
      if ('lockedOut' in result && result.lockedOut) {
        await recoverPinByReactivation()
        return { ok: false, lockedOut: true, errorKey: 'pin.tooManyAttempts' }
      }
      return { ok: false, lockedOut: false, errorKey: 'pin.wrong' }
    },
    [recoverPinByReactivation],
  )

  const signOut = useCallback(async () => {
    const token = sessionRef.current?.token || sealedSessionRef.current?.token
    if (token) {
      try {
        await rawRequest('/app/push/unregister', { method: 'POST', token, json: {} })
      } catch {
        // Best-effort. The server also revokes push tokens when sessions are invalidated.
      }
      try {
        await rawRequest('/app/auth/logout', { method: 'POST', token })
      } catch {
        // Best-effort: local secure-store removal is authoritative for this device.
      }
    }
    await clearLocalAuthMaterial()
    setStatus('signedOut')
  }, [clearLocalAuthMaterial])

  const request = useCallback(
    async <T,>(path: string, opts: { method?: 'GET' | 'POST'; json?: unknown; body?: FormData; signal?: AbortSignal } = {}): Promise<T> => {
      const current = sessionRef.current
      if (!current) throw new ApiError(401, 'app_auth_failed', 'Please sign in again.')
      try {
        return await rawRequest<T>(path, { ...opts, token: current.token })
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          if (isDefinitiveAuthWipeError(error)) {
            await blockForError(error, 'api')
            throw error
          }
          try {
            const loaded = await rotateSessionAndLoadMe(current)
            sessionRef.current = loaded.session
            applyMeSignedIn(loaded.me)
            return await rawRequest<T>(path, { ...opts, token: loaded.session.token })
          } catch (refreshError) {
            await blockForError(refreshError, 'api')
            throw refreshError
          }
        }
        if (error instanceof ApiError && error.code === 'employee_feature_disabled') {
          await refreshMe()
        } else {
          // Soft access gates may block the shell; business/network errors do not wipe.
          await blockForError(error, 'api')
        }
        throw error
      }
    },
    [applyMeSignedIn, blockForError, refreshMe],
  )

  const download = useCallback(
    async (path: string, target: string): Promise<FileSystem.FileSystemDownloadResult> => {
      const current = sessionRef.current
      if (!current) throw new ApiError(401, 'app_auth_failed', 'Please sign in again.')
      let result = await authenticatedDownload(path, target, current.token)
      if (result.status === 401) {
        const firstError = await downloadApiError(result)
        if (isDefinitiveAuthWipeError(firstError)) {
          await blockForError(firstError, 'api')
          throw firstError
        }
        try {
          const loaded = await rotateSessionAndLoadMe(current)
          sessionRef.current = loaded.session
          applyMeSignedIn(loaded.me)
          result = await authenticatedDownload(path, target, loaded.session.token)
        } catch (error) {
          await blockForError(error, 'api')
          throw error
        }
      }
      if (result.status < 200 || result.status >= 300) {
        const error = await downloadApiError(result)
        if (error.code === 'employee_feature_disabled') await refreshMe()
        else await blockForError(error, 'api')
        throw error
      }
      return result
    },
    [applyMeSignedIn, blockForError, refreshMe],
  )

  const uploadFile = useCallback(
    (
      path: string,
      file: PickedFile,
      parameters: Record<string, string>,
      onProgress?: (progress: TransferProgress) => void,
    ): CancellableTransfer<DocumentUploadResult> => {
      const current = sessionRef.current
      if (!current) throw new ApiError(401, 'app_auth_failed', 'Please sign in again.')
      let activeTask: FileSystem.UploadTask | null = null
      let cancelled = false

      const run = async (token: string) => {
        activeTask = createUploadTask(path, file, parameters, token, onProgress)
        const result = await activeTask.uploadAsync()
        activeTask = null
        if (!result || cancelled) throw transferCancelledError()
        return result
      }

      const promise = (async () => {
        let result = await run(current.token)
        if (result.status === 401 && !cancelled) {
          try {
            const loaded = await rotateSessionAndLoadMe(current)
            sessionRef.current = loaded.session
            applyMeSignedIn(loaded.me)
            result = await run(loaded.session.token)
          } catch (error) {
            await blockForError(error, 'api')
            throw error
          }
        }
        if (result.status < 200 || result.status >= 300) {
          const error = uploadApiError(result)
          if (error.code === 'employee_feature_disabled') await refreshMe()
          else await blockForError(error, 'api')
          throw error
        }
        try {
          return (result.body ? JSON.parse(result.body) : {}) as DocumentUploadResult
        } catch {
          return { ok: true }
        }
      })()

      return {
        promise,
        cancel: async () => {
          cancelled = true
          await activeTask?.cancelAsync()
        },
      }
    },
    [applyMeSignedIn, blockForError, refreshMe],
  )

  const downloadFile = useCallback(
    (
      path: string,
      target: string,
      onProgress?: (progress: TransferProgress) => void,
    ): CancellableTransfer<FileSystem.FileSystemDownloadResult> => {
      const current = sessionRef.current
      if (!current) throw new ApiError(401, 'app_auth_failed', 'Please sign in again.')
      let activeTask: FileSystem.DownloadResumable | null = null
      let cancelled = false

      const run = async (token: string) => {
        activeTask = createDownloadTask(path, target, token, onProgress)
        const result = await activeTask.downloadAsync()
        activeTask = null
        if (!result || cancelled) throw transferCancelledError()
        return result
      }

      const promise = (async () => {
        let result = await run(current.token)
        if (result.status === 401 && !cancelled) {
          try {
            const loaded = await rotateSessionAndLoadMe(current)
            sessionRef.current = loaded.session
            applyMeSignedIn(loaded.me)
            result = await run(loaded.session.token)
          } catch (error) {
            await blockForError(error, 'api')
            throw error
          }
        }
        if (result.status < 200 || result.status >= 300) {
          const error = await downloadApiError(result)
          if (error.code === 'employee_feature_disabled') await refreshMe()
          else await blockForError(error, 'api')
          throw error
        }
        return result
      })()

      return {
        promise,
        cancel: async () => {
          cancelled = true
          await activeTask?.cancelAsync()
        },
      }
    },
    [applyMeSignedIn, blockForError, refreshMe],
  )

  const gateEmployeeKey = employeeKeyOf(me) || String(profile?.employee_key || '').trim() || unlockEmployeeKey
  const pinEnabled = isLocalPinEnabledFor(gateEmployeeKey)
  const biometricEnabled = isLocalBiometricEnabledFor(gateEmployeeKey)
  const autoLockEnabled = isLocalAutoLockEnabledFor(gateEmployeeKey)

  useEffect(() => {
    if (!isLocalBiometricMasterEnabled()) return
    if (status === 'signedIn' || status === 'locked' || status === 'needsBiometricOptIn') {
      void refreshBiometricState()
    }
  }, [status, refreshBiometricState])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      accessState,
      profile,
      me,
      pinEnabled,
      biometricEnabled,
      biometricPreferenceOn,
      biometricKind,
      autoLockEnabled,
      autoLockTimeoutMs,
      setAutoLockTimeout,
      activate,
      requestCode,
      signOut,
      refreshMe,
      createLocalPin,
      unlockWithPin,
      unlockWithBiometric,
      recoverPinByReactivation,
      finishBiometricOptIn,
      setBiometricUnlockEnabled,
      changeLocalPin,
      hasFeature: (feature) => meHasFeature(me, feature),
      can: (feature, action) => canUseFeatureAction(me, feature, action),
      request,
      download,
      uploadFile,
      downloadFile,
    }),
    [
      status,
      accessState,
      profile,
      me,
      pinEnabled,
      biometricEnabled,
      biometricPreferenceOn,
      biometricKind,
      autoLockEnabled,
      autoLockTimeoutMs,
      setAutoLockTimeout,
      activate,
      requestCode,
      signOut,
      refreshMe,
      createLocalPin,
      unlockWithPin,
      unlockWithBiometric,
      recoverPinByReactivation,
      finishBiometricOptIn,
      setBiometricUnlockEnabled,
      changeLocalPin,
      request,
      download,
      uploadFile,
      downloadFile,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

async function rotateSessionAndLoadMe(current: StoredSession): Promise<{ session: StoredSession; me: MeResponse }> {
  let res: ActivateResponse
  try {
    res = await rawRequest<ActivateResponse>('/app/auth/refresh', {
      method: 'POST',
      json: { refresh_token: current.refreshToken },
    })
  } catch (error) {
    throw markRefreshFailed(error)
  }
  const session = { token: res.token, refreshToken: res.refresh_token }
  await saveSession(session)
  try {
    const me = await rawRequest<MeResponse>('/app/me', { token: session.token })
    return { session, me }
  } catch (error) {
    // Tokens already rotated into SecureStore. Soft /me failures keep session.
    if (
      error instanceof ApiError &&
      (error.code === 'account_inactive' ||
        error.code === 'stale_session_epoch' ||
        error.code === 'app_access_revoked' ||
        error.code === 'app_auth_failed' ||
        error.status === 401)
    ) {
      throw markRefreshFailed(error)
    }
    throw error
  }
}

async function loadCurrentMe(current: StoredSession): Promise<{ session: StoredSession; me: MeResponse }> {
  try {
    const me = await rawRequest<MeResponse>('/app/me', { token: current.token })
    return { session: current, me }
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      // HR revoke / offboard / epoch kill — do not soft-refresh; wipe path needs the real code.
      if (isDefinitiveAuthWipeError(error)) throw error
      return rotateSessionAndLoadMe(current)
    }
    throw error
  }
}

async function authenticatedDownload(
  path: string,
  target: string,
  token: string,
): Promise<FileSystem.FileSystemDownloadResult> {
  return FileSystem.downloadAsync(`${API_BASE_URL}${path}`, target, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/octet-stream' },
  })
}

function createUploadTask(
  path: string,
  file: PickedFile,
  parameters: Record<string, string>,
  token: string,
  onProgress?: (progress: TransferProgress) => void,
): FileSystem.UploadTask {
  return FileSystem.createUploadTask(
    `${API_BASE_URL}${path}`,
    file.uri,
    {
      httpMethod: 'POST',
      uploadType: FileSystem.FileSystemUploadType.MULTIPART,
      fieldName: 'file',
      mimeType: file.mimeType,
      parameters,
      sessionType: FileSystem.FileSystemSessionType.FOREGROUND,
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
    },
    ({ totalBytesSent, totalBytesExpectedToSend }) => {
      const total = Math.max(0, totalBytesExpectedToSend)
      onProgress?.({
        transferred: totalBytesSent,
        total,
        progress: total > 0 ? Math.min(1, totalBytesSent / total) : 0,
      })
    },
  )
}

function createDownloadTask(
  path: string,
  target: string,
  token: string,
  onProgress?: (progress: TransferProgress) => void,
): FileSystem.DownloadResumable {
  return FileSystem.createDownloadResumable(
    `${API_BASE_URL}${path}`,
    target,
    {
      sessionType: FileSystem.FileSystemSessionType.FOREGROUND,
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/octet-stream' },
    },
    ({ totalBytesWritten, totalBytesExpectedToWrite }) => {
      const total = Math.max(0, totalBytesExpectedToWrite)
      onProgress?.({
        transferred: totalBytesWritten,
        total,
        progress: total > 0 ? Math.min(1, totalBytesWritten / total) : 0,
      })
    },
  )
}

function uploadApiError(result: FileSystem.FileSystemUploadResult): ApiError {
  try {
    const payload = JSON.parse(result.body) as {
      detail?: {
        error?: string
        message?: string
        message_en?: string
        message_ar?: string
      }
    }
    const detail = payload.detail || {}
    return new ApiError(
      result.status,
      detail.error || 'upload_failed',
      detail.message || detail.message_en || detail.message_ar || 'The document could not be uploaded.',
      { messageEn: detail.message_en, messageAr: detail.message_ar },
    )
  } catch {
    return new ApiError(result.status, 'upload_failed', 'The document could not be uploaded.')
  }
}

function transferCancelledError(): ApiError {
  return new ApiError(0, 'transfer_cancelled', 'Transfer cancelled.')
}

async function downloadApiError(result: FileSystem.FileSystemDownloadResult): Promise<ApiError> {
  try {
    const text = await FileSystem.readAsStringAsync(result.uri)
    const payload = JSON.parse(text) as { detail?: { error?: string; message?: string } }
    return new ApiError(
      result.status,
      payload.detail?.error || 'download_failed',
      payload.detail?.message || 'The document could not be downloaded.',
    )
  } catch {
    return new ApiError(result.status, 'download_failed', 'The document could not be downloaded.')
  }
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
