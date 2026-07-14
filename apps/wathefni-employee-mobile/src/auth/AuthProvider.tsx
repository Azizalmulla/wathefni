import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AppState } from 'react-native'
import * as FileSystem from 'expo-file-system'

import { API_BASE_URL, ApiError, rawRequest } from '@/api/client'
import type { ActivateResponse, EmployeeFeatureKey, EmployeeProfile, MeResponse } from '@/api/types'
import {
  accessStateForError,
  canUseFeatureAction,
  hasFeature as meHasFeature,
  type AppAccessState,
} from '@/capabilities'
import { clearSession, loadSession, saveSession, type StoredSession } from './session'
import type { PickedFile } from '@/lib/uploadDocument'
import { savePushPreference } from '@/push/preferences'

type AuthStatus = 'loading' | 'signedOut' | 'signedIn' | 'blocked'

export type TransferProgress = {
  transferred: number
  total: number
  progress: number
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
  activate: (phone: string, code: string) => Promise<void>
  requestCode: (phone: string) => Promise<void>
  signOut: () => Promise<void>
  refreshMe: () => Promise<boolean>
  hasFeature: (feature: EmployeeFeatureKey) => boolean
  can: (feature: EmployeeFeatureKey, action: string) => boolean
  request: <T>(path: string, opts?: { method?: 'GET' | 'POST'; json?: unknown; body?: FormData; signal?: AbortSignal }) => Promise<T>
  download: (path: string, target: string) => Promise<FileSystem.FileSystemDownloadResult>
  uploadFile: (
    path: string,
    file: PickedFile,
    parameters: Record<string, string>,
    onProgress?: (progress: TransferProgress) => void,
  ) => CancellableTransfer<void>
  downloadFile: (
    path: string,
    target: string,
    onProgress?: (progress: TransferProgress) => void,
  ) => CancellableTransfer<FileSystem.FileSystemDownloadResult>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [accessState, setAccessState] = useState<AppAccessState>('active')
  const [profile, setProfile] = useState<EmployeeProfile | null>(null)
  const [me, setMe] = useState<MeResponse | null>(null)
  const sessionRef = useRef<StoredSession | null>(null)

  const applyMe = useCallback((next: MeResponse) => {
    setMe(next)
    setProfile(next.employee)
    setAccessState('active')
    setStatus('signedIn')
  }, [])

  const blockForError = useCallback(async (error: unknown, force = false): Promise<boolean> => {
    const next = accessStateForError(error)
    if (next === 'unknown_error' && !force) return false
    if (next === 'session_expired' || next === 'employee_inactive') {
      sessionRef.current = null
      await Promise.all([clearSession(), savePushPreference(false)])
    }
    setAccessState(next)
    setStatus('blocked')
    return true
  }, [])

  const refreshMe = useCallback(async (): Promise<boolean> => {
    const current = sessionRef.current
    if (!current) {
      setStatus('signedOut')
      return false
    }
    try {
      const loaded = await loadCurrentMe(current)
      sessionRef.current = loaded.session
      applyMe(loaded.me)
      return true
    } catch (error) {
      await blockForError(error, true)
      return false
    }
  }, [applyMe, blockForError])

  useEffect(() => {
    let active = true
    void (async () => {
      const stored = await loadSession()
      if (!active) return
      if (!stored) {
        setStatus('signedOut')
        return
      }
      sessionRef.current = stored
      await refreshMe()
    })()
    return () => {
      active = false
    }
  }, [refreshMe])

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (next) => {
      if (next === 'active' && sessionRef.current) void refreshMe()
    })
    return () => subscription.remove()
  }, [refreshMe])

  const persist = useCallback(async (token: string, refreshToken: string) => {
    const next = { token, refreshToken }
    sessionRef.current = next
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
        sessionRef.current = loaded.session
        applyMe(loaded.me)
      } catch (error) {
        await blockForError(error, true)
        throw error
      }
    },
    [applyMe, blockForError, persist],
  )

  const requestCode = useCallback(async (phone: string) => {
    await rawRequest('/app/auth/request-code', { method: 'POST', json: { phone } })
  }, [])

  const signOut = useCallback(async () => {
    const token = sessionRef.current?.token
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
    sessionRef.current = null
    await Promise.all([clearSession(), savePushPreference(false)])
    setProfile(null)
    setMe(null)
    setAccessState('active')
    setStatus('signedOut')
  }, [])

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
            applyMe(loaded.me)
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
    [applyMe, blockForError, refreshMe],
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
          applyMe(loaded.me)
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
    [applyMe, blockForError, refreshMe],
  )

  const uploadFile = useCallback(
    (
      path: string,
      file: PickedFile,
      parameters: Record<string, string>,
      onProgress?: (progress: TransferProgress) => void,
    ): CancellableTransfer<void> => {
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
            applyMe(loaded.me)
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
      })()

      return {
        promise,
        cancel: async () => {
          cancelled = true
          await activeTask?.cancelAsync()
        },
      }
    },
    [applyMe, blockForError, refreshMe],
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
            applyMe(loaded.me)
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
    [applyMe, blockForError, refreshMe],
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      accessState,
      profile,
      me,
      activate,
      requestCode,
      signOut,
      refreshMe,
      hasFeature: (feature) => meHasFeature(me, feature),
      can: (feature, action) => canUseFeatureAction(me, feature, action),
      request,
      download,
      uploadFile,
      downloadFile,
    }),
    [status, accessState, profile, me, activate, requestCode, signOut, refreshMe, request, download, uploadFile, downloadFile],
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
    const payload = JSON.parse(result.body) as { detail?: { error?: string; message?: string } }
    return new ApiError(
      result.status,
      payload.detail?.error || 'upload_failed',
      payload.detail?.message || 'The document could not be uploaded.',
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
