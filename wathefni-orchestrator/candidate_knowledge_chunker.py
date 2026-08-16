"""Deterministic section-aware CV chunking for Candidate Knowledge Phase 4."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


CHUNKER_VERSION = "ck-chunker-v1"

# Qualification parameters — not production truth.
CHUNK_TOKEN_TARGETS = (800, 1000, 1200)
DEFAULT_TARGET_TOKENS = 1000
DEFAULT_OVERLAP_TOKENS = 100

SECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("summary", re.compile(r"^(summary|profile|objective|نبذة|الملخص)\b", re.I | re.M)),
    ("employment", re.compile(r"^(experience|employment|work history|الخبرة|الخبرات|العمل)\b", re.I | re.M)),
    ("education", re.compile(r"^(education|academic|التعليم|التعليمية)\b", re.I | re.M)),
    ("skills", re.compile(r"^(skills|competencies|المهارات)\b", re.I | re.M)),
    ("certifications", re.compile(r"^(certifications?|licenses?|الشهادات)\b", re.I | re.M)),
    ("languages", re.compile(r"^(languages?|اللغات)\b", re.I | re.M)),
    ("projects", re.compile(r"^(projects?|portfolio|المشاريع)\b", re.I | re.M)),
)


@dataclass(frozen=True)
class ChunkerConfig:
    target_tokens: int = DEFAULT_TARGET_TOKENS
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS
    version: str = CHUNKER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TextChunk:
    section_type: str
    ordinal: int
    text: str
    text_hash: str
    char_start: int
    char_end: int
    token_start: int
    token_end: int
    language: str
    heading: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def approximate_tokens(text: str) -> list[str]:
    """Whitespace tokenizer sufficient for local deterministic chunk sizing."""

    return [part for part in re.split(r"\s+", text.strip()) if part]


def detect_language(text: str) -> str:
    arabic = len(re.findall(r"[\u0600-\u06FF]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if arabic and latin:
        return "ar_en"
    if arabic:
        return "ar"
    if latin:
        return "en"
    return "unknown"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text_hash(text: str) -> str:
    return text_hash(text)


def _split_sections(text: str) -> list[tuple[str, str, int, int]]:
    """Return (section_type, section_text, char_start, char_end)."""

    matches: list[tuple[int, str, str]] = []
    for section_type, pattern in SECTION_PATTERNS:
        for match in pattern.finditer(text):
            matches.append((match.start(), section_type, match.group(0)))
    if not matches:
        return [("other", text, 0, len(text))]

    matches.sort(key=lambda item: item[0])
    # Keep first heading at each start offset.
    deduped: list[tuple[int, str, str]] = []
    seen_starts: set[int] = set()
    for start, section_type, heading in matches:
        if start in seen_starts:
            continue
        seen_starts.add(start)
        deduped.append((start, section_type, heading))

    sections: list[tuple[str, str, int, int]] = []
    if deduped[0][0] > 0:
        preamble = text[: deduped[0][0]]
        if preamble.strip():
            sections.append(("summary", preamble, 0, deduped[0][0]))

    for idx, (start, section_type, _heading) in enumerate(deduped):
        end = deduped[idx + 1][0] if idx + 1 < len(deduped) else len(text)
        body = text[start:end]
        if body.strip():
            sections.append((section_type, body, start, end))
    return sections


def _window_tokens(
    tokens: list[str],
    *,
    target: int,
    overlap: int,
) -> list[tuple[int, int]]:
    if not tokens:
        return []
    if len(tokens) <= target:
        return [(0, len(tokens))]
    windows: list[tuple[int, int]] = []
    start = 0
    step = max(1, target - overlap)
    while start < len(tokens):
        end = min(len(tokens), start + target)
        windows.append((start, end))
        if end >= len(tokens):
            break
        start += step
    return windows


def chunk_cv_text(
    text: str,
    *,
    config: ChunkerConfig | None = None,
) -> list[TextChunk]:
    """Deterministically chunk immutable CV text with section awareness."""

    cfg = config or ChunkerConfig()
    source = str(text or "")
    if not source.strip():
        return []

    chunks: list[TextChunk] = []
    global_ordinal = 0
    for section_type, section_text, section_start, _section_end in _split_sections(source):
        tokens = approximate_tokens(section_text)
        if not tokens:
            continue
        heading = None
        first_line = section_text.strip().splitlines()[0].strip() if section_text.strip() else ""
        if first_line and len(first_line) <= 80:
            heading = first_line

        # Map token windows back to character offsets inside the full text.
        # Build token spans relative to section_text.
        token_spans: list[tuple[int, int]] = []
        cursor = 0
        for token in tokens:
            idx = section_text.find(token, cursor)
            if idx < 0:
                idx = cursor
            token_spans.append((idx, idx + len(token)))
            cursor = idx + len(token)

        for token_start, token_end in _window_tokens(
            tokens, target=cfg.target_tokens, overlap=cfg.overlap_tokens
        ):
            local_start = token_spans[token_start][0]
            local_end = token_spans[token_end - 1][1]
            chunk_body = section_text[local_start:local_end].strip()
            if not chunk_body:
                continue
            # Retain heading with content when window does not start at section head.
            if heading and token_start > 0 and not chunk_body.startswith(heading):
                chunk_body = f"{heading}\n{chunk_body}"
            char_start = section_start + local_start
            char_end = section_start + local_end
            chunks.append(
                TextChunk(
                    section_type=section_type,
                    ordinal=global_ordinal,
                    text=chunk_body,
                    text_hash=_text_hash(chunk_body),
                    char_start=char_start,
                    char_end=char_end,
                    token_start=token_start,
                    token_end=token_end,
                    language=detect_language(chunk_body),
                    heading=heading,
                )
            )
            global_ordinal += 1
    return chunks


def chunk_structured_facts(
    facts: dict[str, Any] | None,
    *,
    config: ChunkerConfig | None = None,
) -> list[TextChunk]:
    """Build searchable fact projection chunks (no private notes)."""

    cfg = config or ChunkerConfig()
    payload = facts if isinstance(facts, dict) else {}
    lines: list[str] = []
    for key in ("skills", "employment_history", "education", "certifications", "languages", "projects"):
        value = payload.get(key)
        if value is None and key == "employment_history":
            value = payload.get("employment")
        if not value:
            continue
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in value if str(item).strip())
        else:
            rendered = str(value)
        if rendered.strip():
            lines.append(f"{key}: {rendered.strip()}")
    years = payload.get("experience_years")
    if years is not None and str(years).strip():
        lines.append(f"experience_years: {years}")
    text = "\n".join(lines).strip()
    if not text:
        return []
    return [
        TextChunk(
            section_type="effective_facts",
            ordinal=0,
            text=text,
            text_hash=_text_hash(text),
            char_start=0,
            char_end=len(text),
            token_start=0,
            token_end=len(approximate_tokens(text)),
            language=detect_language(text),
            heading="effective_facts",
        )
    ]


def chunk_classification_labels(
    classifications: dict[str, Any] | None,
) -> list[TextChunk]:
    """Index HR-confirmed and AI-suggested labels separately."""

    payload = classifications if isinstance(classifications, dict) else {}
    chunks: list[TextChunk] = []
    ordinal = 0
    for authority, key in (("hr_confirmed", "hr_confirmed"), ("ai_suggested", "ai_suggested")):
        rows = payload.get(key) if isinstance(payload.get(key), list) else []
        labels = []
        for row in rows:
            if isinstance(row, dict):
                label = str(row.get("label") or row.get("node_id") or "").strip()
                node_type = str(row.get("node_type") or "").strip()
                if label:
                    labels.append(f"{node_type}:{label}" if node_type else label)
            elif str(row).strip():
                labels.append(str(row).strip())
        if not labels:
            continue
        text = f"classification_{authority}: " + ", ".join(labels)
        chunks.append(
            TextChunk(
                section_type=f"classification_{authority}",
                ordinal=ordinal,
                text=text,
                text_hash=_text_hash(text),
                char_start=0,
                char_end=len(text),
                token_start=0,
                token_end=len(approximate_tokens(text)),
                language=detect_language(text),
                heading=authority,
            )
        )
        ordinal += 1
    return chunks


def benchmark_chunk_configs(text: str) -> dict[str, Any]:
    """Compare chunk counts across the initial 800/1000/1200 token targets."""

    results = []
    for target in CHUNK_TOKEN_TARGETS:
        cfg = ChunkerConfig(target_tokens=target, overlap_tokens=DEFAULT_OVERLAP_TOKENS)
        chunks = chunk_cv_text(text, config=cfg)
        results.append(
            {
                "target_tokens": target,
                "overlap_tokens": cfg.overlap_tokens,
                "chunk_count": len(chunks),
                "avg_chars": round(sum(len(item.text) for item in chunks) / max(1, len(chunks)), 1),
                "sections": sorted({item.section_type for item in chunks}),
            }
        )
    return {"chunker_version": CHUNKER_VERSION, "configs": results}


__all__ = [
    "CHUNKER_VERSION",
    "CHUNK_TOKEN_TARGETS",
    "DEFAULT_TARGET_TOKENS",
    "DEFAULT_OVERLAP_TOKENS",
    "ChunkerConfig",
    "TextChunk",
    "approximate_tokens",
    "detect_language",
    "chunk_cv_text",
    "chunk_structured_facts",
    "chunk_classification_labels",
    "benchmark_chunk_configs",
    "text_hash",
]
