#!/usr/bin/env python3
"""HR Mobile Assistant — thin spine client contracts (EN/AR/RTL, deep-link safety, More entry)."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))

view = (ROOT / "src/hr/features/assistant/HRAssistantView.tsx").read_text(encoding="utf-8")
api = (ROOT / "src/hr/api/assistant.ts").read_text(encoding="utf-8")
links = (ROOT / "src/hr/features/assistant/assistantDeepLinks.ts").read_text(encoding="utf-8")
launcher = (ROOT / "src/hr/features/more/moreLauncher.ts").read_text(encoding="utf-8")
caps = (ROOT / "src/hr/capabilities.ts").read_text(encoding="utf-8")
nav = (ROOT / "src/hr/navigation.ts").read_text(encoding="utf-8")
layout = (ROOT / "app/hr/_layout.tsx").read_text(encoding="utf-8")
route = (ROOT / "app/hr/assistant.tsx").read_text(encoding="utf-8")
auth = (ROOT / "src/hr/auth/AuthProvider.tsx").read_text(encoding="utf-8")


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("route file exports HRAssistantView", "HRAssistantView" in route)
check("Stack.Screen assistant registered", 'name="assistant"' in layout)
check("More launcher includes assistant", "key: 'assistant'" in launcher and "/hr/assistant" in launcher)
check("capability route definition", "key: 'assistant'" in caps and "features: ['assistant']" in caps)
check("destinationAvailable gates /assistant", "path === '/assistant'" in caps and "hasCapability(me, 'hr', 'assistant')" in caps)
check("canonical parent → More", "p === '/assistant'" in nav and "toHrPath('/more')" in nav)
check("getAccessToken for SSE", "getAccessToken" in auth and "getAccessToken" in view)
check("mobile API under /dashboard/mobile/assistant", "/dashboard/mobile/assistant/capabilities" in api)
check("stream + non-stream fallback", "chat/stream" in api and "postAssistantChat" in api)
check("expo/fetch for streaming body", "expo/fetch" in api and "getReader" in api)
check("client reveal fallback deltas", "revealTextAsDeltas" in api)
check("channel never spoofs web_dashboard in client", "web_dashboard" not in api and "web_dashboard" not in view)
check("no ai-recruiter references", "ai-recruiter" not in view.lower() and "ai-recruiter" not in api.lower())
check("deep links use destinationAvailable", "destinationAvailable(me, dest)" in links)
check("web-only pages blocked", "WEB_ONLY_PAGES" in links and "reports" in links and "settings" in links)
check("ranking remaps to jobs picker", "ranking: '/hr/jobs'" in links)
check("jobs page maps to /hr/jobs", "jobs: '/hr/jobs'" in links)
check("interviews use interview_id not app_key", "interview_id" in links and "Never treat app_key" in links)
check("streamAssistantChat used", "streamAssistantChat" in view)
check("Thinking phase before stream", "phase: 'thinking'" in view and "ThinkingLabel" in view)
check("no cheap ellipsis placeholder", "streaming ? '…'" not in view and "…'" not in view)
check("confirm only via pending confirmation", "confirmation?.is_active" in view)
check("EN/AR readingEdgeAlign + composer RTL", "readingEdgeAlign" in view and "composerRtl" in view and "isRTL" in view)
check("hasCapability assistant gate", "hasCapability(me, 'hr', 'assistant')" in view)
check("floating composer + keyboard avoidance", "KeyboardAvoidingView" in view and "composerShell" in view and "useSafeAreaInsets" in view)
check("circular arrow-up send", 'name="arrow-up"' in view and "sendBtn" in view)
check("pink send when active", "sendActive" in view and "colors.pink" in view)
check("quiet send when empty", "sendQuiet" in view)
check("no suggestion chips UI", "chipsWrap" not in view and "CHIP_TONES" not in view and "refreshCaps" not in view)
check("logo badge not text wordmark hero", "badge-black-alpha.png" in view and "Wordmark" not in view)
check("empty: Kuwait greeting", "kuwaitDayPart" in view and "home.greetingMorning" in view)
check("FlatList conversation scroll", "FlatList" in view and "keyboardDismissMode=\"interactive\"" in view)
check("empty land present", "emptyLand" in view)
check("composer single/multiline shells", "composerShellSingle" in view and "composerShellMultiline" in view)
check("auto-grow input capped", "INPUT_MAX" in view and "onContentSizeChange" in view)
check("rapid-send guard", "sendingRef" in view)

keys = [
    "hrMore.assistant",
    "hrMore.assistantBody",
    "hrAssistant.title",
    "hrAssistant.subtitle",
    "hrAssistant.unavailable",
    "hrAssistant.placeholder",
    "hrAssistant.send",
    "hrAssistant.confirm",
    "hrAssistant.thinking",
    "home.greetingMorning",
    "home.greetingAfternoon",
    "home.greetingEvening",
]
check("hrAssistant + greeting keys EN+AR", all(k in en and k in ar for k in keys))
check("Thinking copy EN+AR", en.get("hrAssistant.thinking") == "Thinking" and "يفكر" in ar.get("hrAssistant.thinking", ""))
check("Arabic title present", "مساعد" in ar["hrAssistant.title"])
check("English brand title", "Wathefni Assistant" in en["hrAssistant.title"])

# Static deep-link safety: no raw web pages in PAGE_TO_HR
page_map = re.search(r"PAGE_TO_HR[^=]*=\s*\{([^}]+)\}", links, re.S)
assert page_map, "PAGE_TO_HR missing"
blocked = {"reports", "ai", "settings", "overview", "assessments", "calendar"}
for page in blocked:
    check(f"PAGE_TO_HR omits {page}", f"{page}:" not in page_map.group(1))
check("PAGE_TO_HR includes jobs", "jobs:" in page_map.group(1))
check("assessments stay web-only", "assessments" in links and "WEB_ONLY_PAGES" in links)

print("hr-mobile-assistant: GREEN")
