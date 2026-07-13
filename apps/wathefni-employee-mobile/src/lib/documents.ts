import * as FileSystem from 'expo-file-system'
import * as Sharing from 'expo-sharing'
import { Linking } from 'react-native'

// Authenticated open/download of an employee document. Local files are streamed
// by the backend (FileResponse), so the caller supplies AuthProvider's
// refresh-aware download function. External-provider docs (rare) come back as a
// JSON access link, which we open in the browser instead.
export async function openDocument(
  fileId: string,
  filename: string | null,
  download: (path: string, target: string) => Promise<FileSystem.FileSystemDownloadResult>,
): Promise<void> {
  const safeName = (filename || `document-${fileId}`).replace(/[^\w.\-]+/g, '_')
  const target = `${FileSystem.cacheDirectory}${safeName}`
  const path = `/app/documents/${encodeURIComponent(fileId)}?disposition=attachment`
  const result = await download(path, target)

  const contentType = (result.headers['Content-Type'] || result.headers['content-type'] || '').toLowerCase()
  if (contentType.includes('application/json')) {
    // External-provider access link: read the JSON and open the URL.
    try {
      const body = await FileSystem.readAsStringAsync(result.uri)
      const parsed = JSON.parse(body) as { url?: string }
      if (parsed.url) {
        await Linking.openURL(parsed.url)
        return
      }
    } catch {
      // fall through to share attempt
    }
  }

  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(result.uri)
  }
}
