#!/usr/bin/env python3
"""Attendance Wave 2D — secret-safe connector handling and leak scanning.

Contract: credentials must never appear in shell argv, logs, process listings,
evidence packs, or error traces. Use EnvironmentFile / sealed vault only.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

SECRET_ENV_NAMES = frozenset({
    "WATHEFNI_CAPTURE_CREDENTIAL_KEY",
    "W2C_LAB_PASS",
    "W2C_LAB_TOKEN",
    "BIOTIME_PASSWORD",
    "BIOTIME_TOKEN",
    "CONNECTOR_PASSWORD",
    "CONNECTOR_TOKEN",
    "CONNECTOR_API_SECRET",
})

# Patterns that indicate leaked secrets in text.
# Placeholders ([REDACTED], <...>, …, ...) are not findings.
LEAK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "env_assignment",
        re.compile(
            r"(?i)\b(WATHEFNI_CAPTURE_CREDENTIAL_KEY|BIOTIME_PASSWORD|BIOTIME_TOKEN|W2C_LAB_PASS|W2C_LAB_TOKEN|"
            r"CONNECTOR_PASSWORD|CONNECTOR_TOKEN|CONNECTOR_API_SECRET)\s*=\s*"
            r"(?!\[REDACTED\]|<[^>\s]+>|\.{2,}|…)(\S+)"
        ),
    ),
    ("fernet_key", re.compile(r"\b[A-Za-z0-9_-]{40,}={0,2}\b")),  # refined with context
    ("basic_auth_header", re.compile(r"(?i)authorization:\s*basic\s+[A-Za-z0-9+/=]{8,}")),
    ("token_header", re.compile(r"(?i)authorization:\s*token\s+(?!\[REDACTED\])\S+")),
    ("password_json", re.compile(r'(?i)"password"\s*:\s*"(?!\[REDACTED\])[^"]+"')),
    ("token_json", re.compile(r'(?i)"(?:token|api_secret|secret)"\s*:\s*"(?!\[REDACTED\])[^"]{6,}"')),
    ("lab_synth_defaults", re.compile(r"lab_synth_only|lab-token-synth-only")),
]

# Fernet keys look like base64; only flag when near credential keywords.
FERNET_CONTEXT = re.compile(
    r"(?i)(credential_key|fernet|WATHEFNI_CAPTURE_CREDENTIAL_KEY|password|token|secret).{0,40}"
    r"([A-Za-z0-9_-]{40,}={0,2})"
)

REDACTED = "[REDACTED]"
_PLACEHOLDER_VALUES = frozenset({REDACTED, "…", "...", ".."})


@dataclass
class LeakFinding:
    path: str
    rule: str
    line_no: int
    excerpt: str


@dataclass
class LeakScanResult:
    ok: bool
    findings: list[LeakFinding] = field(default_factory=list)
    files_scanned: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "files_scanned": self.files_scanned,
            "findings": [asdict(f) for f in self.findings],
        }


def _is_placeholder(value: str) -> bool:
    v = (value or "").strip().strip('"').strip("'")
    if not v or v in _PLACEHOLDER_VALUES:
        return True
    if v.startswith("<") and v.endswith(">"):
        return True
    if set(v) <= {".", "…"}:
        return True
    return False


def redact_text(text: str) -> str:
    out = text
    for _name, pat in LEAK_PATTERNS:
        if _name in {"fernet_key"}:
            continue
        out = pat.sub(lambda m: m.group(0).split("=")[0] + "=" + REDACTED if "=" in m.group(0) else REDACTED, out)
    out = FERNET_CONTEXT.sub(lambda m: m.group(1) + "=" + REDACTED, out)
    out = re.sub(r"(?i)(password|token|api_secret|secret)\s*[:=]\s*\S+", r"\1=" + REDACTED, out)
    return out


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    sensitive = {"password", "token", "api_secret", "secret", "credential_key", "authorization"}
    out: dict[str, Any] = {}
    for k, v in data.items():
        lk = str(k).lower()
        if any(s in lk for s in sensitive):
            out[k] = REDACTED
        elif isinstance(v, dict):
            out[k] = redact_mapping(v)
        elif isinstance(v, list):
            out[k] = [
                redact_mapping(x)
                if isinstance(x, dict)
                else (REDACTED if isinstance(x, str) and len(x) > 40 and any(s in lk for s in sensitive) else x)
                for x in v
            ]
        elif isinstance(v, str):
            out[k] = redact_text(v) if any(s in lk for s in sensitive) else v
        else:
            out[k] = v
    return out


def safe_error(exc: BaseException) -> str:
    """Format exception without echoing secret-bearing messages verbatim when obvious."""
    msg = redact_text(f"{type(exc).__name__}: {exc}")
    return msg[:500]


def assert_argv_secret_safe(argv: Iterable[str] | None = None) -> dict[str, Any]:
    """Fail closed if process argv contains secret env values or password flags."""
    args = list(argv) if argv is not None else list(os.sys.argv)
    leaked = []
    secret_values = []
    for name in SECRET_ENV_NAMES:
        val = os.environ.get(name)
        if val and len(val) >= 6:
            secret_values.append(val)
    for i, arg in enumerate(args):
        low = arg.lower()
        if low.startswith("--password") or low.startswith("--token") or low.startswith("--api-secret"):
            leaked.append({"argv_index": i, "reason": "secret_flag"})
        for val in secret_values:
            if val in arg:
                leaked.append({"argv_index": i, "reason": "secret_value_in_argv"})
    return {"ok": not leaked, "leaks": leaked}


def scan_text(text: str, *, path: str = "<memory>") -> list[LeakFinding]:
    findings: list[LeakFinding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for rule, pat in LEAK_PATTERNS:
            if rule == "fernet_key":
                m = FERNET_CONTEXT.search(line)
                if not m:
                    continue
                value = m.group(2) or ""
                if _is_placeholder(value):
                    continue
                findings.append(
                    LeakFinding(
                        path=path,
                        rule="fernet_context",
                        line_no=line_no,
                        excerpt=redact_text(line)[:160],
                    )
                )
                continue
            m = pat.search(line)
            if not m:
                continue
            # group(2) is the value for env_assignment; otherwise whole match
            value = m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(0)
            if _is_placeholder(value) or REDACTED in m.group(0):
                continue
            if "sha256" in line.lower() and rule == "lab_synth_defaults":
                continue
            findings.append(
                LeakFinding(
                    path=path,
                    rule=rule,
                    line_no=line_no,
                    excerpt=redact_text(line)[:160],
                )
            )
    return findings


def scan_paths(
    paths: Iterable[str | Path],
    *,
    suffixes: tuple[str, ...] = (".log", ".txt", ".json", ".md", ".out", ".csv"),
) -> LeakScanResult:
    findings: list[LeakFinding] = []
    scanned = 0
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files = [
                f
                for f in p.rglob("*")
                if f.is_file() and (f.suffix.lower() in suffixes or f.name.endswith(".env") or f.name == ".env")
            ]
        elif p.is_file():
            files = [p]
        else:
            continue
        for f in files:
            # Never open credential files themselves as evidence to print
            if f.name.endswith(".env") or f.suffix.lower() == ".env" or f.name == ".env":
                findings.append(
                    LeakFinding(
                        path=str(f),
                        rule="secrets_file_in_evidence",
                        line_no=0,
                        excerpt="REFUSE: raw secrets file must not be packaged into evidence",
                    )
                )
                scanned += 1
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:  # noqa: BLE001
                findings.append(LeakFinding(path=str(f), rule="read_error", line_no=0, excerpt=safe_error(exc)))
                scanned += 1
                continue
            scanned += 1
            findings.extend(scan_text(text, path=str(f)))
    return LeakScanResult(ok=len(findings) == 0, findings=findings, files_scanned=scanned)


def qualify_or_block(scan: LeakScanResult) -> dict[str, Any]:
    """Qualification gate: any leak finding blocks Wave 2D qualify."""
    if scan.ok:
        return {"ok": True, "blocked": False, "files_scanned": scan.files_scanned}
    return {
        "ok": False,
        "blocked": True,
        "error": "secret_leak_detected",
        "files_scanned": scan.files_scanned,
        "findings": [
            {
                "path": f.path,
                "rule": f.rule,
                "line_no": f.line_no,
                "excerpt": redact_text(f.excerpt),
            }
            for f in scan.findings[:20]
        ],
    }


def write_environment_file(path: str | Path, values: dict[str, str], *, mode: int = 0o600) -> dict[str, Any]:
    """Write secrets via EnvironmentFile pattern — never echo values."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in values.items()]
    data = ("\n".join(lines) + "\n").encode("utf-8")
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    os.chmod(p, mode)
    return {"ok": True, "path": str(p), "mode": oct(mode), "keys": sorted(values.keys())}


SECRET_HANDLING_CONTRACT = {
    "version": "attendance_capture_secrets_wave2d_v1",
    "rules": [
        "Never pass passwords/tokens/keys on argv or curl -d plaintext in deploy scripts",
        "Load secrets only from mode-600 EnvironmentFile or sealed vault",
        "Redact before tee/log/evidence write",
        "scan_paths must PASS before qualification evidence is accepted",
        "On suspected exposure: rotate immediately, revoke connector, re-qualify",
        "Error traces use safe_error()/redact_text()",
    ],
}
