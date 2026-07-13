import * as DocumentPicker from 'expo-document-picker'
import * as ImagePicker from 'expo-image-picker'

export type PickedFile = { uri: string; name: string; mimeType: string }

// Lets the employee pick a PDF or image. Camera/library access is requested
// just-in-time (only when they tap upload), per store guidance.
export async function pickDocument(): Promise<PickedFile | null> {
  const result = await DocumentPicker.getDocumentAsync({
    type: ['application/pdf', 'image/*'],
    copyToCacheDirectory: true,
    multiple: false,
  })
  if (result.canceled || !result.assets?.length) return null
  const asset = result.assets[0]
  return {
    uri: asset.uri,
    name: asset.name || 'document',
    mimeType: asset.mimeType || 'application/octet-stream',
  }
}

export async function pickImageFromLibrary(): Promise<PickedFile | null> {
  const permission = await ImagePicker.requestMediaLibraryPermissionsAsync()
  if (!permission.granted) return null
  const result = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ImagePicker.MediaTypeOptions.Images,
    quality: 0.8,
  })
  if (result.canceled || !result.assets?.length) return null
  const asset = result.assets[0]
  const name = asset.fileName || `photo-${Date.now()}.jpg`
  return { uri: asset.uri, name, mimeType: asset.mimeType || 'image/jpeg' }
}

// Builds the multipart body the /app/onboarding/documents endpoint expects.
export function buildUploadForm(file: PickedFile, itemId: string): FormData {
  const form = new FormData()
  form.append('item_id', itemId)
  // React Native's FormData file shape.
  form.append('file', { uri: file.uri, name: file.name, type: file.mimeType } as unknown as Blob)
  return form
}
