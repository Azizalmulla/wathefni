#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

DIST = Path.home() / '.npm-global/lib/node_modules/openclaw/dist'
NEEDLE = 'const listeners = /* @__PURE__ */ new Map();'
OLD_REPLACEMENT = 'const listeners = globalThis.__openclawActiveWebListeners || (globalThis.__openclawActiveWebListeners = /* @__PURE__ */ new Map());'
REPLACEMENT = 'const listeners = (globalThis.process || process).__openclawActiveWebListeners || ((globalThis.process || process).__openclawActiveWebListeners = /* @__PURE__ */ new Map());'


def candidate_files():
    for path in DIST.rglob('*.js'):
        try:
            text = path.read_text()
        except Exception:
            continue
        if ('setActiveWebListener' in text and 'requireActiveWebListener' in text and (NEEDLE in text or OLD_REPLACEMENT in text)):
            yield path, text


def main():
    files = list(candidate_files())
    if not files:
        print('No candidate files found.')
        return 1
    changed = []
    for path, text in files:
        if REPLACEMENT in text:
            print(f'[skip] {path}')
            continue
        updated = text
        if OLD_REPLACEMENT in updated:
            updated = updated.replace(OLD_REPLACEMENT, REPLACEMENT, 1)
        else:
            updated = updated.replace(NEEDLE, REPLACEMENT, 1)
        if updated == text:
            print(f'[skip-nochange] {path}')
            continue
        backup = path.with_suffix(path.suffix + '.bak_listener_patch')
        if not backup.exists():
            backup.write_text(text)
        path.write_text(updated)
        result = subprocess.run(['node', '-c', str(path)], capture_output=True, text=True)
        if result.returncode != 0:
            path.write_text(text)
            print(f'[reverted] {path}')
            print(result.stderr[:500])
            return 1
        changed.append(path)
        print(f'[patched] {path}')
    print(f'Patched {len(changed)} file(s).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
