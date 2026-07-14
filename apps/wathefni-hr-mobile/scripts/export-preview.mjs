import { execFileSync, spawnSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'

const projectRoot = new URL('../', import.meta.url).pathname
const sha = execFileSync('git', ['rev-parse', '--short', 'HEAD'], {
  cwd: projectRoot,
  encoding: 'utf8',
}).trim()
const timestamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z')
const marker = process.env.HR_PREVIEW_BUILD || `HR2-${sha}-${timestamp}`

const result = spawnSync(
  'npx',
  ['expo', 'export', '--platform', 'web', '--output-dir', 'dist-preview', '--clear'],
  {
    cwd: projectRoot,
    env: {
      ...process.env,
      EXPO_PUBLIC_HR_DESIGN_PREVIEW: '1',
      EXPO_PUBLIC_HR_PREVIEW_BUILD: marker,
    },
    stdio: 'inherit',
  },
)
if (result.status !== 0) process.exit(result.status ?? 1)

writeFileSync(
  new URL('../dist-preview/preview-build.json', import.meta.url),
  `${JSON.stringify({ marker, exported_at: new Date().toISOString() })}\n`,
)
console.log(`HR_PREVIEW_EXPORTED ${marker}`)
