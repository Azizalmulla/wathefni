#!/usr/bin/env python3
"""Generate staging classification UX density HTML evidence."""
from __future__ import annotations

import json
import pathlib
import sys

ev = pathlib.Path(sys.argv[1])
outcomes = json.loads((ev / "qualify-r3" / "outcomes.json").read_text(encoding="utf-8"))
ux = ev / "ux"
ux.mkdir(parents=True, exist_ok=True)

rows = []
for slug, o in outcomes.items():
    chip = ""
    if o.get("status") in {"classified", "classified_multi", "cautious"} and "High" in (o.get("bands") or []):
        nodes = o.get("node_ids") or []
        career = next((n for n in nodes if n.startswith("fn.")), None)
        role = next((n for n in nodes if n.startswith("role.")), None)
        if career:
            chip = career + (f" · {role}" if role else "")
    rows.append((slug, o.get("status"), o.get("outcome_label"), chip, o.get("bands")))

parts = [
    "<!doctype html><meta charset=utf-8><title>Staging classification UX density</title>",
    "<style>body{font:14px/1.4 Georgia,serif;margin:24px;background:#f3efe7;color:#1a1a1a}"
    "table{border-collapse:collapse;width:100%;background:#fff}"
    "th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left}"
    ".chip{display:inline-block;font-size:12px;color:#244;background:#e8f0ec;padding:2px 8px}"
    ".muted{color:#666}.panel{background:#fff;padding:16px;margin-top:24px;border:1px solid #ddd}</style>",
    "<h1>Unified Candidates — classification density (staging synthetic)</h1>",
    "<p class=muted>No permanent classification columns. At most one High-confidence chip. "
    "Medium / Needs review / Unclassified stay in profile + filters.</p>",
    "<table><tr><th>Fixture</th><th>Outcome</th><th>Bands</th><th>Compact chip (High only)</th></tr>",
]
for slug, st, label, chip, bands in rows:
    chip_html = f"<span class=chip>{chip}</span>" if chip else "<span class=muted>hidden</span>"
    parts.append(
        f"<tr><td>{slug}</td><td>{label or st}</td>"
        f"<td>{', '.join(bands or []) or '—'}</td><td>{chip_html}</td></tr>"
    )
parts.append("</table><div class=panel><h2>Profile Classification section samples</h2>")
for slug in ["software", "multi", "incomplete_facts", "insufficient", "arabic", "career_change"]:
    parts.append(f"<h3>{slug}</h3><pre>{json.dumps(outcomes[slug], indent=2)}</pre>")
parts.append("</div>")
(ux / "candidates-table-density.html").write_text("\n".join(parts), encoding="utf-8")

(ux / "classification-filters.html").write_text(
    """<!doctype html><meta charset=utf-8><title>Classification filters</title>
<style>body{font:14px Georgia,serif;margin:24px;background:#f3efe7}
.f{display:flex;flex-wrap:wrap;gap:8px}
label{background:#fff;border:1px solid #ccc;padding:6px 10px}</style>
<h1>Classification filters (advisory)</h1>
<div class=f>
<label>Career area</label><label>Likely role</label><label>Skill</label><label>Industry</label>
<label>Seniority</label><label>Experience band</label>
<label>High-confidence AI</label><label>Medium-confidence AI</label>
<label>HR-confirmed only</label><label>Confirmed or AI suggested</label>
<label>Needs review</label><label>Unclassified</label>
</div>
<p>Default views may prefer HR-confirmed + High AI. Medium available and labeled.
Authorities never silently blended in search.</p>
""",
    encoding="utf-8",
)
print("wrote", ux)
