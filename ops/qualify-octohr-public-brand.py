#!/usr/bin/env python3
"""Fail closed on unexplained old-brand copy in production customer surfaces."""

from __future__ import annotations

import ast
import io
import re
import subprocess
import sys
import tokenize
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLD_BRAND = re.compile(r"wathefni\.ai|Wathefni|WATHEFNI|وظفني|وظّفني|وثّفني|وطّفني", re.IGNORECASE)
NATURAL_OLD_BRAND = re.compile(r"(?<![A-Za-z0-9_])Wathefni(?![A-Za-z0-9_])|وظفني|وظّفني|وثّفني|وطّفني")

HISTORICAL_PREFIXES = (
    ".cursor/",
    "docs/",
    "ops/evidence/",
    "ops/rollback/",
    "wathefni-orchestrator/evidence/",
    "wathefni-orchestrator/ops/",
    "wathefni-orchestrator/staging-evidence/",
    "apps/wathefni-employee-mobile/docs/",
    "apps/wathefni-employee-mobile/assets/brand/",
    "apps/wathefni-hr-mobile/",
)

TECHNICAL_LINE_MARKERS = (
    "ai.wathefni.employee",
    "WATHEFNI_",
    "X-Wathefni",
    "x_wathefni",
    "wathefni://",
    "wathefni:",
    ".wathefni.local",
    "wathefni_",
    "wathefni-",
    "wathefni.",
    "'wathefni'",
    '"wathefni"',
    "company == \"WATHEFNI\"",
    "company == 'WATHEFNI'",
    "company_code='WATHEFNI'",
    "company_code=\"WATHEFNI\"",
    "money_authority=wathefni",
    "money_authority = \"wathefni\"",
    "money_authority = 'wathefni'",
    "legacyBatteryName",
)


def _paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return sorted({p for p in result.stdout.decode("utf-8", "surrogateescape").split("\0") if p})


def _historical(path: str) -> bool:
    name = Path(path).name
    return (
        path.startswith(HISTORICAL_PREFIXES)
        or "/migrations/" in path
        or "/fixtures/" in path
        or name.startswith(("smoke-test-", "test_", "canary-", "prove-", "migrate-", "ops-"))
        or ".test." in name
        or name.endswith(("_test.py", "_FULL_PASS.md", "_FREEZE_AMENDMENT.md"))
        or name in {"AGENTS.md", "README.md"}
    )


def _customer_surface(path: str) -> bool:
    if path in {
        "apps/wathefni-employee-mobile/app.json",
        "apps/wathefni-dashboard/index.html",
        "apps/wathefni-dashboard/setup-console.html",
    }:
        return True
    if path.startswith((
        "apps/wathefni-employee-mobile/app/",
        "apps/wathefni-employee-mobile/locales/",
        "apps/wathefni-employee-mobile/src/",
        "apps/wathefni-dashboard/src/",
    )):
        return True
    if path.startswith("wathefni-orchestrator/") and path.count("/") == 1 and path.endswith(".py"):
        name = Path(path).name
        if any(part in name for part in ("worker", "evidence", "backfill", "cleanup", "local-qualify", "-eval", "_eval")):
            return False
        return True
    return False


def _python_internal_lines(text: str) -> set[int]:
    lines: set[int] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                lines.update(range(token.start[0], token.end[0] + 1))
    except (IndentationError, tokenize.TokenError):
        pass
    try:
        tree = ast.parse(text)
        nodes = [tree, *(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))]
        for node in nodes:
            body = getattr(node, "body", [])
            if not body:
                continue
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                lines.update(range(first.lineno, getattr(first, "end_lineno", first.lineno) + 1))
    except (SyntaxError, ValueError):
        pass
    return lines


def _technical(line: str, match: re.Match[str], *, internal_line: bool = False) -> bool:
    token = match.group(0)
    start, end = match.span()
    before = line[start - 1] if start else ""
    after = line[end] if end < len(line) else ""
    stripped = line.lstrip()
    if token == "WATHEFNI":
        return True
    if (before and (before.isalnum() or before == "_")) or (after and (after.isalnum() or after == "_")):
        return True
    if internal_line or stripped.startswith(("#", "//", "/*", "*", "--", "<!--", '"""', "'''")):
        return True
    return any(marker in line for marker in TECHNICAL_LINE_MARKERS)


def main() -> int:
    counts: Counter[str] = Counter()
    defects: list[str] = []
    scanned_files = 0
    for rel in _paths():
        path = ROOT / rel
        if not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        matches = list(OLD_BRAND.finditer(text))
        if not matches:
            continue
        scanned_files += 1
        historical = _historical(rel)
        customer = _customer_surface(rel) and not historical
        python_internal = _python_internal_lines(text) if customer and rel.endswith(".py") else set()
        line_no = 1
        line_start = 0
        for match in matches:
            while True:
                newline = text.find("\n", line_start)
                if newline < 0 or match.start() <= newline:
                    break
                line_no += 1
                line_start = newline + 1
            line_end = text.find("\n", line_start)
            if line_end < 0:
                line_end = len(text)
            line = text[line_start:line_end]
            local_match = OLD_BRAND.search(line, max(0, match.start() - line_start))
            if historical:
                category = "approved_historical"
            elif match.group(0).lower() == "wathefni.ai":
                category = "backward_compatible_url_or_alias"
            elif not customer:
                category = "approved_technical"
            elif local_match is not None and _technical(line, local_match, internal_line=line_no in python_internal):
                category = "approved_technical"
            elif NATURAL_OLD_BRAND.search(line):
                category = "defect"
            else:
                category = "approved_technical"
            counts[category] += 1
            if category == "defect" and len(defects) < 200:
                defects.append(f"{rel}:{line_no}: {line.strip()[:240]}")

    print(f"BRAND_SCAN_FILES={scanned_files}")
    print(f"BRAND_SCAN_OCCURRENCES={sum(counts.values())}")
    for category in (
        "approved_technical",
        "approved_historical",
        "backward_compatible_url_or_alias",
        "defect",
    ):
        print(f"BRAND_SCAN_{category.upper()}={counts[category]}")
    if defects:
        print("BRAND_SCAN_DEFECTS:")
        for defect in defects:
            print(f"- {defect}")
        print("OCTOHR_PUBLIC_BRAND_SCAN_FAILED")
        return 1
    print("OCTOHR_PUBLIC_BRAND_SCAN_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
