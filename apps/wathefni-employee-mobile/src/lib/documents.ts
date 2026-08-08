import * as FileSystem from 'expo-file-system'
import * as Sharing from 'expo-sharing'
import { Linking } from 'react-native'
import type { CancellableTransfer, TransferProgress } from '@/auth/AuthProvider'

// Authenticated open/download of an employee document. Local files are streamed
// by the backend (FileResponse), so the caller supplies AuthProvider's
// refresh-aware download function. External-provider docs (rare) come back as a
// JSON access link, which we open in the browser instead.
export async function openDocument(
  fileId: string,
  filename: string | null,
  download: (
    path: string,
    target: string,
    onProgress?: (progress: TransferProgress) => void,
  ) => CancellableTransfer<FileSystem.FileSystemDownloadResult>,
  onProgress?: (progress: TransferProgress) => void,
): Promise<{ cancel: () => Promise<void>; completed: Promise<void> }> {
  return openPrivateFile(
    `/app/documents/${encodeURIComponent(fileId)}?disposition=attachment`,
    filename || `document-${fileId}`,
    fileId,
    download,
    onProgress,
  )
}

/**
 * Authenticated open of any private `/app/*` file stream (documents, bank
 * evidence). Bytes are never exposed via a public URL, so every open goes
 * through the token-aware download and the cache copy is deleted afterwards.
 */
export async function openPrivateFile(
  path: string,
  filename: string | null,
  cacheKey: string,
  download: (
    path: string,
    target: string,
    onProgress?: (progress: TransferProgress) => void,
  ) => CancellableTransfer<FileSystem.FileSystemDownloadResult>,
  onProgress?: (progress: TransferProgress) => void,
): Promise<{ cancel: () => Promise<void>; completed: Promise<void> }> {
  const safeName = (filename || `file-${cacheKey}`).replace(/[^\w.\-]+/g, '_')
  const safeId = cacheKey.replace(/[^\w\-]+/g, '_')
  const target = `${FileSystem.cacheDirectory}${safeId}-${safeName}`
  const transfer = download(path, target, onProgress)

  const completed = (async () => {
    try {
      const result = await transfer.promise
      const contentType = (result.headers['Content-Type'] || result.headers['content-type'] || '').toLowerCase()
      if (contentType.includes('application/json')) {
        const body = await FileSystem.readAsStringAsync(result.uri)
        const parsed = JSON.parse(body) as { url?: string }
        if (parsed.url && isSafeExternalUrl(parsed.url)) {
          await Linking.openURL(parsed.url)
          return
        }
      }

      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(result.uri, {
          dialogTitle: filename || 'Document',
          mimeType: contentType || undefined,
        })
      }
    } finally {
      await FileSystem.deleteAsync(target, { idempotent: true }).catch(() => undefined)
    }
  })()

  return { cancel: transfer.cancel, completed }
}

function isSafeExternalUrl(value: string): boolean {
  try {
    return new URL(value).protocol === 'https:'
  } catch {
    return false
  }
}
