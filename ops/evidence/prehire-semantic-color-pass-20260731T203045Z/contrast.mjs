/**
 * WCAG contrast checks for semantic ink-on-soft / ink-on-base pairs.
 */
import { writeFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))

function hexToRgb(hex) {
  const h = hex.replace('#', '')
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}

function relLum([r, g, b]) {
  const f = (c) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

function contrast(fg, bg) {
  const L1 = relLum(hexToRgb(fg))
  const L2 = relLum(hexToRgb(bg))
  const lighter = Math.max(L1, L2)
  const darker = Math.min(L1, L2)
  return (lighter + 0.05) / (darker + 0.05)
}

const pairs = [
  { name: 'priority ink on soft', fg: '#2f3a22', bg: '#dfe8c8', min: 4.5 },
  { name: 'priority ink on base', fg: '#2f3a22', bg: '#a9ba7d', min: 4.5 },
  { name: 'review ink on soft', fg: '#3d3410', bg: '#f7e89a', min: 4.5 },
  { name: 'review ink on base', fg: '#3d3410', bg: '#f1d96f', min: 4.5 },
  { name: 'assess ink on soft', fg: '#4a2438', bg: '#f0c4de', min: 4.5 },
  { name: 'assess ink on base', fg: '#4a2438', bg: '#e8acd0', min: 4.5 },
  { name: 'follow ink on soft', fg: '#243044', bg: '#c9d8ef', min: 4.5 },
  { name: 'follow ink on base', fg: '#243044', bg: '#b4c9e5', min: 4.5 },
  { name: 'paused ink on soft', fg: '#4a4338', bg: '#efe8dc', min: 4.5 },
  { name: 'active ink on soft', fg: '#6b221c', bg: '#f5ddd7', min: 4.5 },
  { name: 'white on black pill', fg: '#ffffff', bg: '#23211d', min: 4.5 },
  { name: 'ink on cream surface', fg: '#23211d', bg: '#fffaf0', min: 4.5 },
]

const rows = pairs.map((p) => {
  const ratio = contrast(p.fg, p.bg)
  return { ...p, ratio: Number(ratio.toFixed(2)), pass: ratio >= p.min }
})

const allPass = rows.every((r) => r.pass)
mkdirSync(resolve(__dirname, 'verify'), { recursive: true })
writeFileSync(resolve(__dirname, 'verify', 'contrast.json'), JSON.stringify({ allPass, rows }, null, 2) + '\n')
console.log(JSON.stringify({ allPass, failed: rows.filter((r) => !r.pass) }, null, 2))
process.exit(allPass ? 0 : 1)
