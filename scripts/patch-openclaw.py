#!/usr/bin/env python3
"""
Re-apply narration suppression patches to OpenClaw gateway bundles.
Run this after every `openclaw update`.

Usage:
    python3 scripts/patch-openclaw.py

What it does:
    Patches handleMessageEnd, onPartialReply, and fallbackAnswerText
    in both auth-profiles gateway bundles to suppress internal narration
    (e.g. "Now uploading CV to Drive") from reaching WhatsApp candidates.
"""
import subprocess, sys
from pathlib import Path

DIST = Path.home() / '.npm-global/lib/node_modules/openclaw/dist'

def find_auth_profiles():
    """Find auth-profiles JS files (filenames change per version)."""
    files = []
    for pattern, folder in [
        ('auth-profiles-*.js', DIST / 'plugin-sdk'),
        ('auth-profiles-*.js', DIST),
    ]:
        files.extend(folder.glob(pattern))
    return files

def patch_handleMessageEnd(src):
    """Add tool-call guard to handleMessageEnd."""
    marker = '_hasToolCall'
    hme = src.find('function handleMessageEnd')
    if hme < 0:
        return src, False
    hme_chunk = src[hme:hme+3000]
    if marker in hme_chunk:
        return src, False  # already patched

    anchor = '\tconst text = resolveSilentReplyFallbackText({'
    insert = src.find(anchor, hme)
    if insert < 0:
        print('  WARNING: handleMessageEnd anchor not found')
        return src, False

    guard = (
        '\tconst _hasToolCall = Array.isArray(assistantMessage.content) && '
        'assistantMessage.content.some(function(b) { return b && typeof b === "object" '
        '&& (b.type === "toolCall" || b.type === "toolUse" || b.type === "functionCall"); });\n'
        '\tif (_hasToolCall) {\n'
        '\t\tif (ctx.state.assistantTexts && ctx.state.assistantTexts.length > (ctx.state.assistantTextBaseline || 0)) '
        'ctx.state.assistantTexts.splice(ctx.state.assistantTextBaseline || 0);\n'
        '\t\tif (ctx.blockChunker) ctx.blockChunker.reset();\n'
        '\t\tctx.state.blockBuffer = "";\n'
        '\t\tctx.state.deltaBuffer = "";\n'
        '\t\tctx.state.lastBlockReplyText = void 0;\n'
        '\t\tctx.state.lastStreamedAssistant = void 0;\n'
        '\t\tctx.state.lastStreamedAssistantCleaned = void 0;\n'
        '\t\tctx.state.emittedAssistantUpdate = false;\n'
        '\t\tctx.state.assistantTextBaseline = (ctx.state.assistantTexts || []).length;\n'
        '\t\tif (ctx.state.blockState) { ctx.state.blockState.thinking = false; ctx.state.blockState.final = false; }\n'
        '\t\tctx.state.reasoningStreamOpen = false;\n'
        '\t\treturn;\n'
        '\t}\n'
    )
    src = src[:insert] + guard + src[insert:]
    return src, True

def patch_onPartialReply(src):
    """Block onPartialReply streaming for WhatsApp."""
    opr = src.find('onPartialReply: async (payload) =>')
    if opr < 0:
        return src, False
    chunk = src[opr:opr+600]
    if 'whatsapp' in chunk.lower():
        return src, False  # already patched

    anchor = 'if (!params.opts?.onPartialReply || textForTyping === void 0) return;'
    anchor_idx = src.find(anchor, opr)
    if anchor_idx < 0:
        print('  WARNING: onPartialReply anchor not found')
        return src, False

    eol = src.find('\n', anchor_idx)
    line_start = src.rfind('\n', 0, anchor_idx) + 1
    indent = ''
    for ch in src[line_start:anchor_idx]:
        if ch in ' \t':
            indent += ch
        else:
            break

    guard = (
        indent + 'const _rpCh = typeof resolveMessageChannel === "function" ? '
        'resolveMessageChannel(params.sessionCtx?.Surface, params.sessionCtx?.Provider) : '
        '(params.sessionCtx?.Provider || "").trim().toLowerCase(); '
        'if (_rpCh === "whatsapp" || (params.sessionCtx?.Provider || "").trim().toLowerCase() === "whatsapp") return;\n'
    )
    src = src[:eol+1] + guard + src[eol+1:]
    return src, True

def patch_fallbackAnswerText(src):
    """Suppress fallback text extraction from tool-call assistant turns."""
    fat_needle = 'const fallbackAnswerText = params.lastAssistant ? extractAssistantText$1(params.lastAssistant) : "";'
    fat_idx = src.find(fat_needle)
    if fat_idx < 0:
        if '_lastHasTC' in src:
            return src, False  # already patched
        print('  WARNING: fallbackAnswerText not found')
        return src, False

    # Find the line start for proper indentation
    reason_search = 'const reasoningText = '
    reason_idx = src.rfind(reason_search, fat_idx - 2000, fat_idx)
    if reason_idx < 0:
        print('  WARNING: reasoningText not found')
        return src, False

    reason_line_start = src.rfind('\n', 0, reason_idx) + 1
    indent = ''
    for ch in src[reason_line_start:reason_idx]:
        if ch in ' \t':
            indent += ch
        else:
            break

    # Insert _lastHasTC declaration before reasoningText
    tc_decl = (
        indent + 'const _lastHasTC = Array.isArray(params.lastAssistant?.content) && '
        'params.lastAssistant.content.some(function(b) { return b && typeof b === "object" '
        '&& (b.type === "toolCall" || b.type === "toolUse" || b.type === "functionCall"); });\n'
    )
    src = src[:reason_line_start] + tc_decl + src[reason_line_start:]

    # Patch reasoningText
    src = src.replace(
        'const reasoningText = suppressAssistantArtifacts ? ""',
        'const reasoningText = (suppressAssistantArtifacts || _lastHasTC) ? ""',
        1
    )

    # Patch fallbackAnswerText
    src = src.replace(
        fat_needle,
        'const fallbackAnswerText = _lastHasTC ? "" : params.lastAssistant ? extractAssistantText$1(params.lastAssistant) : "";',
        1
    )
    return src, True

def main():
    files = find_auth_profiles()
    if not files:
        print('ERROR: No auth-profiles files found in %s' % DIST)
        sys.exit(1)

    print('Found %d auth-profiles file(s):' % len(files))
    for f in files:
        print('  %s' % f)
    print()

    all_ok = True
    for fpath in files:
        name = fpath.name
        src = fpath.read_text()
        applied = []

        src, did = patch_handleMessageEnd(src)
        if did: applied.append('handleMessageEnd')

        src, did = patch_onPartialReply(src)
        if did: applied.append('onPartialReply')

        src, did = patch_fallbackAnswerText(src)
        if did: applied.append('fallbackAnswerText')

        if applied:
            fpath.write_text(src)
            # Verify syntax
            result = subprocess.run(['node', '-c', str(fpath)], capture_output=True, text=True)
            if result.returncode == 0:
                print('[%s] Patched: %s  (syntax OK)' % (name, ', '.join(applied)))
            else:
                print('[%s] SYNTAX ERROR after patching!' % name)
                print(result.stdout[:500])
                all_ok = False
        else:
            print('[%s] Already fully patched' % name)

    if all_ok:
        print('\nAll patches applied successfully.')
        print('Restart the gateway: pkill -f openclaw; openclaw gateway')
    else:
        print('\nWARNING: Some patches had errors. Check output above.')
        sys.exit(1)

if __name__ == '__main__':
    main()
