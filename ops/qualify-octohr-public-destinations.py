#!/usr/bin/env python3
"""Qualify the live privacy and support pages referenced by store builds."""

from __future__ import annotations

import os
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser


DEFAULT_PRIVACY_URL = "https://octo-hr.com/privacy"
DEFAULT_SUPPORT_URL = "https://octo-hr.com/support"
MAX_BYTES = 2_000_000
OLD_VISIBLE_BRAND = re.compile(r"\bWathefni\b|\bWATHEFNI\b|وظفني|وظّفني|وثّفني|وطّفني")
URL_OR_EMAIL = re.compile(r"(?:https?://|mailto:)?[^\s<>()\[\]{}\"']*@?wathefni\.ai[^\s<>()\[\]{}\"']*", re.IGNORECASE)


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "template"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "template"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)

    @property
    def text(self) -> str:
        return " ".join(" ".join(self.parts).split())


def fetch(url: str) -> tuple[int, str, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "OctoHR-store-release-qualifier/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("response exceeds 2 MB")
        charset = response.headers.get_content_charset() or "utf-8"
        return response.status, response.geturl(), response.headers.get_content_type(), body.decode(charset, "replace")


def qualify(kind: str, url: str, required_terms: tuple[str, ...]) -> list[str]:
    failures: list[str] = []
    try:
        status, final_url, content_type, body = fetch(url)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return [f"{kind} fetch failed: {exc}"]

    print(f"{kind.upper()}_URL={url}")
    print(f"{kind.upper()}_FINAL_URL={final_url}")
    print(f"{kind.upper()}_HTTP_STATUS={status}")
    print(f"{kind.upper()}_CONTENT_TYPE={content_type}")
    if status != 200:
        failures.append(f"{kind} returned HTTP {status}")
    if content_type != "text/html":
        failures.append(f"{kind} content type is {content_type}, expected text/html")

    parser = VisibleTextParser()
    parser.feed(body)
    visible = parser.text
    visible_lower = visible.lower()
    if "octohr" not in visible_lower:
        failures.append(f"{kind} has no visible OctoHR identity")
    for term in required_terms:
        if term not in visible_lower:
            failures.append(f"{kind} is missing visible {term!r} content")
    for forbidden in ("internal canary", "draft", "placeholder", "coming soon"):
        if forbidden in visible_lower:
            failures.append(f"{kind} is visibly marked {forbidden!r}")

    without_approved_aliases = URL_OR_EMAIL.sub("", visible)
    match = OLD_VISIBLE_BRAND.search(without_approved_aliases)
    if match:
        failures.append(f"{kind} exposes old customer brand {match.group(0)!r}")
    return failures


def main() -> int:
    privacy_url = os.environ.get("EXPO_PUBLIC_PRIVACY_URL", DEFAULT_PRIVACY_URL).strip()
    support_url = os.environ.get("EXPO_PUBLIC_SUPPORT_URL", DEFAULT_SUPPORT_URL).strip()
    failures = [
        *qualify("privacy", privacy_url, ("privacy", "data", "contact")),
        *qualify("support", support_url, ("support", "contact")),
    ]
    if failures:
        print("OCTOHR_PUBLIC_DESTINATIONS_FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("OCTOHR_PUBLIC_DESTINATIONS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
