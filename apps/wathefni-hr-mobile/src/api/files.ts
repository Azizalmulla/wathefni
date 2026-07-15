import { Platform } from 'react-native'
import * as Linking from 'expo-linking'
import { File, Paths } from 'expo-file-system'

import type { RequestOptions } from './client'

type Requester = <T>(
  path: string,
  options?: Omit<RequestOptions, 'token'>,
) => Promise<T>

function safeFilename(value: string | null | undefined): string {
  const cleaned = (value || 'document').replace(/[^a-zA-Z0-9._-]/g, '-')
  return cleaned || 'document'
}

export async function openAuthenticatedFile({
  request,
  path,
  filename,
  mimeType,
  download = false,
}: {
  request: Requester
  path: string
  filename?: string | null
  mimeType?: string | null
  download?: boolean
}): Promise<void> {
  if (!path.startsWith('/dashboard/mobile/')) {
    throw new Error('Unapproved file path')
  }
  const bytes = await request<ArrayBuffer>(path, { responseType: 'arrayBuffer' })
  const name = safeFilename(filename)
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([bytes], { type: mimeType || 'application/octet-stream' }))
    const anchor = document.createElement('a')
    anchor.href = url
    if (download) anchor.download = name
    else anchor.target = '_blank'
    anchor.rel = 'noopener noreferrer'
    anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 30_000)
    return
  }
  const file = new File(Paths.cache, name)
  file.create({ overwrite: true, intermediates: true })
  file.write(new Uint8Array(bytes))
  await Linking.openURL(file.uri)
}
