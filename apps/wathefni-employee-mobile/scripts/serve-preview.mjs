#!/usr/bin/env node
/**
 * Static preview server with hard no-store headers so iPhone Safari / Home Screen
 * cannot keep a stale bundle from a previous LAN IP or export hash.
 */
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = process.env.PREVIEW_DIR || '/tmp/wathefni-preview'
const port = Number(process.env.PREVIEW_PORT || 8091)
const buildId = process.env.PREVIEW_BUILD_ID || `preview-${Date.now()}`

const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ttf': 'font/ttf',
  '.otf': 'font/otf',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.map': 'application/json',
}

function send(res, status, body, type = 'text/plain; charset=utf-8') {
  res.writeHead(status, {
    'Content-Type': type,
    'Content-Length': Buffer.byteLength(body),
    'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
    Pragma: 'no-cache',
    Expires: '0',
    'X-Wathefni-Preview-Build': buildId,
  })
  res.end(body)
}

function resolveFile(urlPath) {
  const clean = decodeURIComponent(urlPath.split('?')[0] || '/')
  const candidate = path.normalize(path.join(root, clean === '/' ? 'index.html' : clean))
  if (!candidate.startsWith(root)) return null
  if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate
  // SPA fallback for expo-router deep links.
  const index = path.join(root, 'index.html')
  return fs.existsSync(index) ? index : null
}

const server = http.createServer((req, res) => {
  if (!req.url) return send(res, 400, 'Bad request')
  if (req.url.startsWith('/__preview_build')) {
    return send(res, 200, JSON.stringify({ buildId, root }), 'application/json; charset=utf-8')
  }
  const file = resolveFile(req.url)
  if (!file) return send(res, 404, 'Not found')
  const ext = path.extname(file).toLowerCase()
  const type = mime[ext] || 'application/octet-stream'
  const body = fs.readFileSync(file)
  // Inject build marker + SW purge into HTML so Home Screen launches cannot reuse old workers.
  if (ext === '.html') {
    let html = body.toString('utf8')
    if (!html.includes('X-Wathefni-Preview-Build')) {
      html = html.replace(
        '</head>',
        `<meta http-equiv="Cache-Control" content="no-store" />
<meta name="wathefni-preview-build" content="${buildId}" />
<script>
try {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations().then(function (regs) {
      regs.forEach(function (reg) { reg.unregister(); });
    });
  }
  if (window.caches && caches.keys) {
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (key) { return caches.delete(key); }));
    });
  }
} catch (e) {}
</script>
</head>`,
      )
    }
    return send(res, 200, html, type)
  }
  res.writeHead(200, {
    'Content-Type': type,
    'Content-Length': body.length,
    'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
    Pragma: 'no-cache',
    Expires: '0',
    'X-Wathefni-Preview-Build': buildId,
  })
  res.end(body)
})

server.listen(port, '0.0.0.0', () => {
  console.log(`Wathefni preview ${buildId}`)
  console.log(`Serving ${root} on http://0.0.0.0:${port}`)
})
