import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AppState } from 'react-native'
import * as FileSystem from 'expo-file-system'
import { useQueryClient } from '@tanstack/react-query'

import { API_BASE_URL, ApiError, rawRequest } from '@/api/client'
import type { ActivateResponse, EmployeeFeatureKey, EmployeeProfile, MeResponse } from '@/api/types'
import {
  accessStateForError,
  canUseFeatureAction,
  hasFeature as meHasFeature,
  type AppAccessState,
} from '@/capabilities'
import { clearSession, loadSession, saveSession, type StoredSession } from './session'
import { isLocalPinEnabledFor, isLocalPinMasterEnabled } from './pinPolicy'
import { clearPinMaterial, hasPinRecord, loadPinRecord, setPin, verifyPin, changePin as changeStoredPin } from './pinStorage'
import { consumeSkipUnlockOnce, clearLocaleRestartPreserveAuth, isLocaleRestartPreserveAuth } from './sessionResume'
import type { PickedFile } from '@/lib/uploadDocument'
import { savePushPreference } from '@/push/preferences'

type AuthStatus = 'loading' | 'signedOut' | 'signedIn' | 'blocked' | 'locked' | 'needsPinSetup'

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
  activate: (phone: string, code: string) => Promise<void>
  requestCode: (phone: string) => Promise<void>
  signOut: () => Promise<void>
  refreshMe: () => Promise<boolean>
  createLocalPin: (pin: string) => Promise<void>
  unlockWithPin: (pin: string) => Promise<{ ok: boolean; lockedOut: boolean; failedAttempts: number }>
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
  /** Only populated when unlocked / Wave 1 path — API clients read this. */
  const sessionRef = useRef<StoredSession | null>(null)
  /** Holds SecureStore tokens while PIN-locked so API clients cannot use them. */
  const sealedSessionRef = useRef<StoredSession | null>(null)

  const employeeKeyOf = (next: MeResponse | null | undefined) =>
    String(next?.employee?.employee_key || (next as { employee_key?: string } | null)?.employee_key || '').trim()

  const applyMeSignedIn = useCallback((next: MeResponse) => {
    setMe(next)
    setProfile(next.employee)
    setAccessState('active')
    setStatus('signedIn')
    void clearLocaleRestartPreserveAuth()
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
    await Promise.all([clearSession(), clearPinMaterial(), savePushPreference(false), clearLocaleRestartPreserveAuth()])
    queryClient.clear()
    setProfile(null)
    setMe(null)
    setAccessState('active')
  }, [queryClient])

  const blockForError = useCallback(async (error: unknown, force = false): Promise<boolean> => {
    const next = accessStateForError(error)
    if (next === 'unknown_error' && !force) return false
    // Language RTL restart must never wipe Wave 1 tokens / PIN (that looked like logout).
    const preserving = await isLocaleRestartPreserveAuth()
    if ((next === 'session_expired' || next === 'employee_inactive') && !preserving) {
      await clearLocalAuthMaterial()
    }
    setAccessState(next)
    setStatus('blocked')
    return true
  }, [clearLocalAuthMaterial])

  const refreshMe = useCallback(async (): Promise<boolean> => {
    const current = sessionRef.current
    if (!current) {
      if (status === 'locked' || status === 'needsPinSetup') return false
      setStatus('signedOut')
      return false
    }
    try {
      const loaded = await loadCurrentMe(current)
      sessionRef.current = loaded.session
      applyMeSignedIn(loaded.me)
      return true
    } catch (error) {
      await blockForError(error, true)
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
        setAccessState('active')
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

      const sealAndRequirePin = () => {
        sealedSessionRef.current = stored
        sessionRef.current = null
        setAccessState('active')
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
            setAccessState(accessStateForError(error))
            setStatus('blocked')
            return
          }
          await blockForError(error, true)
        }
        return
      }

      const pin = await loadPinRecord()
      if (pin) {
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
            sealAndRequirePin()
          }
          return
        }
        sealAndRequirePin()
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
          setAccessState(accessStateForError(error))
          setStatus('blocked')
          return
        }
        await blockForError(error, true)
      }
    })()
    return () => {
      active = false
    }
    // Boot once — PIN gate must not re-run on every refreshMe identity change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (next) => {
      // Phase 3 owns idle/background lock. Brief background must not re-lock.
      if (next === 'active' && sessionRef.current && status === 'signedIn') void refreshMe()
    })
    return () => subscription.remove()
  }, [refreshMe, status])

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
        json: { phone, code },
      })
      await persist(res.token, res.refresh_token)
      try {
        const current = sessionRef.current
        if (!current) throw new ApiError(401, 'app_auth_failed', 'Please sign in again.')
        const loaded = await loadCurrentMe(current)
        // Fresh OTP activation always restarts PIN setup for canary employees.
        if (isLocalPinEnabledFor(employeeKeyOf(loaded.me))) {
          await clearPinMaterial()
        }
        await enterAfterIdentity(loaded.me, loaded.session)
      } catch (error) {
        await blockForError(error, true)
        throw error
      }
    },
    [blockForError, enterAfterIdentity, persist],
  )

  const requestCode = useCallback(async (phone: string) => {
    await rawRequest('/app/auth/request-code', { method: 'POST', json: { phone } })
  }, [])

  const resetToOtpAfterPinFailure = useCallback(async () => {
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
  }, [clearLocalAuthMaterial])

  const createLocalPin = useCallback(
    async (pin: string) => {
      const key = employeeKeyOf(me) || String(profile?.employee_key || '').trim()
      if (!isLocalPinEnabledFor(key)) throw new Error('pin_not_enabled')
      await setPin(key, pin)
      if (sessionRef.current && me) {
        applyMeSignedIn(me)
      } else {
        setStatus('signedOut')
      }
    },
    [applyMeSignedIn, me, profile?.employee_key],
  )

  const unlockWithPin = useCallback(
    async (pin: string) => {
      const result = await verifyPin(pin)
      if (result.ok) {
        const sealed = sealedSessionRef.current
        if (!sealed) {
          await resetToOtpAfterPinFailure()
          return { ok: false, lockedOut: true, failedAttempts: result.failedAttempts }
        }
        sessionRef.current = sealed
        sealedSessionRef.current = null
        try {
          const loaded = await loadCurrentMe(sealed)
          sessionRef.current = loaded.session
          applyMeSignedIn(loaded.me)
        } catch (error) {
          await blockForError(error, true)
          return { ok: false, lockedOut: false, failedAttempts: 0 }
        }
        return { ok: true, lockedOut: false, failedAttempts: 0 }
      }
      if (result.lockedOut) {
        await resetToOtpAfterPinFailure()
      }
      return { ok: false, lockedOut: result.lockedOut, failedAttempts: result.failedAttempts }
    },
    [applyMeSignedIn, blockForError, resetToOtpAfterPinFailure],
  )

  const changeLocalPin = useCallback(
    async (current: string, next: string) => {
      const result = await changeStoredPin(current, next)
      if (result.ok) return { ok: true, lockedOut: false }
      if ('lockedOut' in result && result.lockedOut) {
        await resetToOtpAfterPinFailure()
        return { ok: false, lockedOut: true, errorKey: 'pin.tooManyAttempts' }
      }
      return { ok: false, lockedOut: false, errorKey: 'pin.wrong' }
    },
    [resetToOtpAfterPinFailure],
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
          try {
            const loaded = await rotateSessionAndLoadMe(current)
            sessionRef.current = loaded.session
            applyMeSignedIn(loaded.me)
            return await rawRequest<T>(path, { ...opts, token: loaded.session.token })
          } catch (refreshError) {
            await blockForError(refreshError, true)
            throw refreshError
          }
        }
        if (error instanceof ApiError && error.code === 'employee_feature_disabled') {
          await refreshMe()
        } else {
          await blockForError(error)
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
        try {
          const loaded = await rotateSessionAndLoadMe(current)
          sessionRef.current = loaded.session
          applyMeSignedIn(loaded.me)
          result = await authenticatedDownload(path, target, loaded.session.token)
        } catch (error) {
          await blockForError(error, true)
          throw error
        }
      }
      if (result.status < 200 || result.status >= 300) {
        const error = await downloadApiError(result)
        if (error.code === 'employee_feature_disabled') await refreshMe()
        else await blockForError(error)
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
            await blockForError(error, true)
            throw error
          }
        }
        if (result.status < 200 || result.status >= 300) {
          const error = uploadApiError(result)
          if (error.code === 'employee_feature_disabled') await refreshMe()
          else await blockForError(error)
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
            await blockForError(error, true)
            throw error
          }
        }
        if (result.status < 200 || result.status >= 300) {
          const error = await downloadApiError(result)
          if (error.code === 'employee_feature_disabled') await refreshMe()
          else await blockForError(error)
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

  const pinEnabled = isLocalPinEnabledFor(employeeKeyOf(me) || profile?.employee_key)

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      accessState,
      profile,
      me,
      pinEnabled,
      activate,
      requestCode,
      signOut,
      refreshMe,
      createLocalPin,
      unlockWithPin,
      changeLocalPin,
      hasFeature: (feature) => meHasFeature(me, feature),
      can: (feature, action) => canUseFeatureAction(me, feature, action),
      request,
      download,
      uploadFile,
      downloadFile,
    }),
    [status, accessState, profile, me, pinEnabled, activate, requestCode, signOut, refreshMe, createLocalPin, unlockWithPin, changeLocalPin, request, download, uploadFile, downloadFile],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

async function rotateSessionAndLoadMe(current: StoredSession): Promise<{ session: StoredSession; me: MeResponse }> {
  const res = await rawRequest<ActivateResponse>('/app/auth/refresh', {
    method: 'POST',
    json: { refresh_token: current.refreshToken },
  })
  const session = { token: res.token, refreshToken: res.refresh_token }
  await saveSession(session)
  const me = await rawRequest<MeResponse>('/app/me', { token: session.token })
  return { session, me }
}

async function loadCurrentMe(current: StoredSession): Promise<{ session: StoredSession; me: MeResponse }> {
  try {
    const me = await rawRequest<MeResponse>('/app/me', { token: current.token })
    return { session: current, me }
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
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
