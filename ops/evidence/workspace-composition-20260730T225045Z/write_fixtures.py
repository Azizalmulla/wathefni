#!/usr/bin/env python3
"""Write visual composition fixtures for each matrix row."""

from __future__ import annotations

import json
from pathlib import Path

from workspace_capability import COMPOSITION_MATRIX, authority_fixture_for_matrix_row


def main() -> None:
    out = Path(__file__).resolve().parent / "fixtures"
    out.mkdir(parents=True, exist_ok=True)
    rows = [authority_fixture_for_matrix_row(row) for row in COMPOSITION_MATRIX]
    (out / "composition-matrix.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        (out / f"{row['id']}.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} fixtures to {out}")


if __name__ == "__main__":
    main()
