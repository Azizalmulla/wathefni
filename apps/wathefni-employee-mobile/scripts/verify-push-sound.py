#!/usr/bin/env python3
"""Static gate: Wathefni default push notification sound assets + wiring."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
failures: list[str] = []
passed = 0


def ok(msg: str) -> None:
    global passed
    passed += 1
    print(f"PASS  {msg}")


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"FAIL  {msg}")


def probe(path: Path) -> dict:
    out = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        text=True,
    )
    return json.loads(out)


def main() -> int:
    wav = ROOT / "assets/sounds/push/wathefni_default.wav"
    caf = ROOT / "assets/sounds/push/wathefni_default.caf"
    src = ROOT / "assets/sounds/push/source/universfield-new-notification-040-493469.mp3"
    for p in (wav, caf, src):
        if not p.exists():
            fail(f"missing {p.relative_to(ROOT)}")
        else:
            ok(f"exists {p.name}")

    if not wav.exists():
        print("FAIL push sound gate")
        return 1

    info = probe(wav)
    stream = next(s for s in info["streams"] if s.get("codec_type") == "audio")
    dur = float(info["format"]["duration"])
    if stream.get("codec_name") != "pcm_s16le":
        fail(f"wav codec must be pcm_s16le (got {stream.get('codec_name')})")
    else:
        ok("wav is linear PCM s16le (iOS-safe)")
    if int(stream.get("sample_rate") or 0) != 44100:
        fail("wav sample_rate must be 44100")
    else:
        ok("wav 44.1 kHz")
    if dur > 30:
        fail(f"wav duration {dur}s exceeds iOS 30s limit")
    else:
        ok(f"wav duration {dur:.2f}s <= 30s")

    src_dur = float(probe(src)["format"]["duration"])
    if abs(dur - src_dur) > 0.05:
        fail(f"duration changed vs source ({src_dur} -> {dur})")
    else:
        ok("duration preserved from source")

    app = json.loads((ROOT / "app.json").read_text())
    plugins = app["expo"]["plugins"]
    notif = next(p for p in plugins if isinstance(p, list) and p[0] == "expo-notifications")
    sounds = notif[1].get("sounds") or []
    if "./assets/sounds/push/wathefni_default.wav" not in sounds:
        fail("app.json expo-notifications.sounds missing wathefni_default.wav")
    else:
        ok("app.json bundles wathefni_default.wav")
    if notif[1].get("defaultChannel") != "wathefni_default_v2":
        fail("app.json defaultChannel must be wathefni_default_v2")
    else:
        ok("app.json defaultChannel wathefni_default_v2")

    reg = (ROOT / "src/push/registerForPush.ts").read_text()
    if "WATHEFNI_PUSH_SOUND" not in reg or "setNotificationChannelAsync" not in reg:
        fail("Android channel not wired in registerForPush")
    else:
        ok("Android channel wired")

    life = (ROOT / "src/push/PushLifecycle.tsx").read_text()
    if "shouldPlaySound: true" not in life:
        fail("foreground handler shouldPlaySound must be true")
    else:
        ok("foreground plays sound")

    orch = Path(__file__).resolve().parents[2].parent / "wathefni-orchestrator" / "app.py"
    # repo layout: apps/wathefni-employee-mobile -> claw
    orch = ROOT.parent.parent / "wathefni-orchestrator" / "app.py"
    text = orch.read_text() if orch.exists() else ""
    if "wathefni_default.wav" not in text:
        fail("orchestrator send_push_via_expo missing wathefni_default.wav sound")
    else:
        ok("orchestrator Expo payload uses wathefni_default.wav")
    if "wathefni_default_v2" not in text:
        fail("orchestrator missing channelId wathefni_default_v2")
    else:
        ok("orchestrator Expo payload sets channelId")

    if failures:
        print(f"FAIL push sound: {len(failures)}")
        return 1
    print(f"PASS push sound ({passed} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
