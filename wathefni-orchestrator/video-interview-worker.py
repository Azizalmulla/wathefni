#!/usr/bin/env python3
"""Background worker for async video interview transcription."""

from __future__ import annotations

import argparse
import json
import time

import app


def main() -> None:
    app.assert_runtime_environment_binding()
    parser = argparse.ArgumentParser(description="Process pending Wathefni async video interview transcripts.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum responses to process per pass.")
    parser.add_argument("--include-failed", action="store_true", help="Retry previously failed transcription jobs.")
    parser.add_argument("--loop", action="store_true", help="Keep polling instead of running one pass.")
    parser.add_argument("--sleep", type=int, default=60, help="Seconds to sleep between loop passes.")
    args = parser.parse_args()

    while True:
        result = app.process_pending_video_interview_transcripts(limit=args.limit, include_failed=args.include_failed)
        print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        if not args.loop:
            break
        time.sleep(max(5, args.sleep))


if __name__ == "__main__":
    main()
