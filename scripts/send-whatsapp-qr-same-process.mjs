import { monitorWebChannel, sendMessageWhatsApp } from '/Users/azizalmulla/.npm-global/lib/node_modules/openclaw/dist/plugin-sdk/web-BFPpjpLa.js';

const target = process.argv[2] || '+96599338566';
const mediaPath = process.argv[3] || '/Users/azizalmulla/.openclaw/media/outbound/qr-AIOCTOPUS-AIRESEARCHER.png';
const caption = process.argv[4] || 'AI Researcher QR Code';
const accountId = 'default';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const abort = new AbortController();

async function waitForListener(timeoutMs = 30000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const listeners = process.__openclawActiveWebListeners;
    if (listeners && listeners.get(accountId)) {
      return true;
    }
    await sleep(500);
  }
  return false;
}

let monitorPromise;
try {
  monitorPromise = monitorWebChannel(false, undefined, true, undefined, undefined, abort.signal, {
    accountId,
  });

  const ready = await waitForListener();
  if (!ready) {
    throw new Error('Timed out waiting for active WhatsApp listener in same process');
  }

  const result = await sendMessageWhatsApp(target, caption, {
    accountId,
    mediaUrl: mediaPath,
    mediaLocalRoots: ['/Users/azizalmulla/.openclaw/media/outbound', '/Users/azizalmulla/.openclaw/media'],
  });

  console.log(JSON.stringify({ ok: true, result }, null, 2));
} catch (error) {
  console.error(JSON.stringify({ ok: false, error: String(error?.stack || error) }, null, 2));
  process.exitCode = 1;
} finally {
  abort.abort();
  try {
    await Promise.race([
      monitorPromise,
      sleep(2000),
    ]);
  } catch {}
}
