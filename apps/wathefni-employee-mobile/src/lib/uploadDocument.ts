import * as DocumentPicker from 'expo-document-picker'
import * as ImagePicker from 'expo-image-picker'
import * as ImageManipulator from 'expo-image-manipulator'

export type PickedFile = { uri: string; name: string; mimeType: string }

export class UploadPickError extends Error {
  code: 'camera_permission' | 'library_permission'

  constructor(code: UploadPickError['code']) {
    super(code)
    this.name = 'UploadPickError'
    this.code = code
  }
}

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
    mimeType: normalizedMimeType(asset.name, asset.mimeType),
  }
}

export async function pickImageFromLibrary(): Promise<PickedFile | null> {
  const permission = await ImagePicker.requestMediaLibraryPermissionsAsync()
  if (!permission.granted) throw new UploadPickError('library_permission')
  const result = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ImagePicker.MediaTypeOptions.Images,
    quality: 1,
    allowsEditing: false,
  })
  if (result.canceled || !result.assets?.length) return null
  return prepareImage(result.assets[0])
}

export async function takePhoto(): Promise<PickedFile | null> {
  const permission = await ImagePicker.requestCameraPermissionsAsync()
  if (!permission.granted) throw new UploadPickError('camera_permission')
  const result = await ImagePicker.launchCameraAsync({
    mediaTypes: ImagePicker.MediaTypeOptions.Images,
    cameraType: ImagePicker.CameraType.back,
    quality: 1,
    allowsEditing: false,
  })
  if (result.canceled || !result.assets?.length) return null
  return prepareImage(result.assets[0])
}

async function prepareImage(asset: ImagePicker.ImagePickerAsset): Promise<PickedFile> {
  const maxDimension = 2048
  const largest = Math.max(asset.width || 0, asset.height || 0)
  const actions: ImageManipulator.Action[] =
    largest > maxDimension
      ? [
          asset.width >= asset.height
            ? { resize: { width: maxDimension } }
            : { resize: { height: maxDimension } },
        ]
      : []
  const output = await ImageManipulator.manipulateAsync(asset.uri, actions, {
    compress: 0.78,
    format: ImageManipulator.SaveFormat.JPEG,
  })
  return {
    uri: output.uri,
    name: normalizedImageName(asset.fileName),
    mimeType: 'image/jpeg',
  }
}

function normalizedImageName(name: string | null | undefined): string {
  const base = (name || `photo-${Date.now()}`).replace(/\.[^.]+$/, '')
  return `${base}.jpg`
}

function normalizedMimeType(name: string | null | undefined, provided: string | null | undefined): string {
  const candidate = provided?.toLowerCase().split(';')[0].trim()
  if (candidate === 'image/jpg') return 'image/jpeg'
  if (candidate && candidate !== 'application/octet-stream') return candidate
  const extension = name?.toLowerCase().match(/\.([^.]+)$/)?.[1]
  const supported: Record<string, string> = {
    pdf: 'application/pdf',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    png: 'image/png',
    webp: 'image/webp',
    heic: 'image/heic',
  }
  return (extension && supported[extension]) || 'application/octet-stream'
}
