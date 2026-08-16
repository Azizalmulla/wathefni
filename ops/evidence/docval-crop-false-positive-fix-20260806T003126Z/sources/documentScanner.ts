/**
 * Native document scanner — preparation only (not wired / not built).
 *
 * Future free native capture path for onboarding documents:
 *  - iOS: VisionKit VNDocumentCameraViewController
 *  - Android: ML Kit Document Scanner
 *
 * Capabilities planned (implement in a later native-module wave):
 *  - edge detection
 *  - auto crop
 *  - perspective correction
 *  - retake
 *  - multi-page support
 *
 * Current uploads still use expo-image-picker / DocumentPicker via uploadDocument.ts.
 * Do not import native scanner SDKs here until a dedicated native build wave.
 */

export type DocumentScannerPage = {
  uri: string
  mimeType: string
  width?: number
  height?: number
  /** Optional quadrilateral from native edge detection (normalized 0–1). */
  corners?: { x: number; y: number }[]
}

export type DocumentScannerResult = {
  pages: DocumentScannerPage[]
  source: 'visionkit' | 'mlkit_document_scanner' | 'fallback_picker'
  perspectiveCorrected: boolean
  autoCropped: boolean
}

export type DocumentScannerOptions = {
  maxPages?: number
  allowGalleryFallback?: boolean
  /** When true, prefer native scanner; when unavailable, caller may fall back. */
  preferNative?: boolean
}

/**
 * Availability probe for a future native module.
 * Always false until VisionKit / ML Kit modules are linked in a native build.
 */
export function isNativeDocumentScannerAvailable(): boolean {
  return false
}

/**
 * Placeholder entry point — must not be called from production UI yet.
 * Throws until the native scanner wave ships.
 */
export async function scanDocument(_options?: DocumentScannerOptions): Promise<DocumentScannerResult> {
  throw new Error('native_document_scanner_not_implemented')
}

export const NATIVE_DOCUMENT_SCANNER_ROADMAP = {
  ios: 'VisionKit VNDocumentCameraViewController',
  android: 'ML Kit Document Scanner',
  features: [
    'edge_detection',
    'auto_crop',
    'perspective_correction',
    'retake',
    'multi_page',
  ] as const,
  status: 'prep_only' as const,
}
