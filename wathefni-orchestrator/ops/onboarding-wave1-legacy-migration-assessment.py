#!/usr/bin/env python3
"""Onboarding Wave 1 — read-only migration assessment (four reals vs default_kuwait).

Compares legacy checklist rows for the four real WATHEFNI employees against the
current DEFAULT_KUWAIT_ONBOARDING_TEMPLATE. Does NOT insert, update, delete,
enable SEED, or enable HR_MUTATE.

Inputs (first match wins):
  1) --from-snapshot PATH  (Wave 0 ALL_ITEMS JSON line or raw JSON array)
  2) live DB via app.db_connect (staging/local only — never required)

Outputs JSON + markdown to --out-dir (default: cwd).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FOUR_REALS = (
    "WATHEFNI-96550252254",  # Talal
    "WATHEFNI-96566363363",  # Fouad
    "WATHEFNI-96597727743",  # Mohammad
    "WATHEFNI-96599411617",  # Brian
)

# Known legacy short-template ids that are not in default_kuwait (or renamed).
LEGACY_ONLY_ALIASES = {
    "education_cert": "optional legacy education upload; not in default_kuwait",
    "medical": "legacy medical fitness; default_kuwait uses medical_check (hr task)",
}


def _template_map() -> dict[str, dict]:
    import app

    out = {}
    for item_id, label, category, item_type, required, owner in app.DEFAULT_KUWAIT_ONBOARDING_TEMPLATE:
        out[item_id] = {
            "item_id": item_id,
            "label": label,
            "category": category,
            "item_type": item_type,
            "required": bool(required),
            "owner": owner,
        }
    return out


def _load_snapshot(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("ALL_ITEMS "):
            return json.loads(line[len("ALL_ITEMS ") :])
        if line.startswith("RAW_ITEMS "):
            # fallback: first employee only — prefer ALL_ITEMS
            continue
    raw = json.loads(text)
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and isinstance(raw.get("items"), list):
        return raw["items"]
    raise SystemExit(f"Unrecognized snapshot format: {path}")


def _load_live() -> list[dict]:
    import app

    app.ensure_schema()
    rows: list[dict] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.employee_key, e.name, e.company_code, e.onboarding_status,
                       oi.item_id, oi.label, oi.required, oi.status, oi.owner, oi.category,
                       oi.item_type, oi.document_type, oi.reminder_count
                FROM employees e
                JOIN onboarding_items oi ON oi.employee_key = e.employee_key
                WHERE e.company_code = 'WATHEFNI'
                  AND e.employee_key = ANY(%s)
                ORDER BY e.employee_key, oi.item_id
                """,
                (list(FOUR_REALS),),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
    return rows


def assess(rows: list[dict], template: dict[str, dict]) -> dict:
    by_emp: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = str(row.get("employee_key") or "")
        if key in FOUR_REALS:
            by_emp[key].append(row)

    employees = []
    for key in FOUR_REALS:
        items = by_emp.get(key) or []
        name = next((str(i.get("name") or "") for i in items if i.get("name")), "")
        live_ids = {str(i.get("item_id")) for i in items}
        template_ids = set(template.keys())

        missing = sorted(template_ids - live_ids)
        obsolete = sorted(live_ids - template_ids)
        shared = sorted(live_ids & template_ids)

        conflicts = []
        for item_id in shared:
            live = next(i for i in items if str(i.get("item_id")) == item_id)
            tmpl = template[item_id]
            notes = []
            live_req = live.get("required")
            if live_req is not None and bool(live_req) != bool(tmpl["required"]):
                notes.append(f"required live={live_req} template={tmpl['required']}")
            live_owner = live.get("owner")
            if live_owner not in (None, "") and str(live_owner) != str(tmpl["owner"]):
                notes.append(f"owner live={live_owner} template={tmpl['owner']}")
            live_cat = live.get("category")
            if live_cat not in (None, "") and str(live_cat) != str(tmpl["category"]):
                notes.append(f"category live={live_cat} template={tmpl['category']}")
            if item_id == "bank_details":
                notes.append("bank policy: keep row but collect via ESS encrypted workflow (no plaintext)")
            if item_id == "passport" and bool(tmpl["required"]) is False and bool(live.get("required")) is True:
                notes.append("passport required on legacy; optional on default_kuwait")
            if notes:
                conflicts.append(
                    {
                        "item_id": item_id,
                        "live_status": live.get("status"),
                        "live_label": live.get("label"),
                        "template_label": tmpl["label"],
                        "notes": notes,
                    }
                )

        obsolete_detail = [
            {
                "item_id": oid,
                "reason": LEGACY_ONLY_ALIASES.get(oid, "present on legacy checklist; absent from default_kuwait"),
                "live": next((i for i in items if str(i.get("item_id")) == oid), {}),
            }
            for oid in obsolete
        ]
        missing_detail = [
            {
                "item_id": mid,
                "template": template[mid],
                "note": "absent on live legacy checklist — would be inserted only by a future SEED/backfill (not Wave 1)",
            }
            for mid in missing
        ]

        employees.append(
            {
                "employee_key": key,
                "name": name,
                "live_item_count": len(items),
                "live_item_ids": sorted(live_ids),
                "missing_from_live": missing_detail,
                "obsolete_vs_template": obsolete_detail,
                "conflicts": conflicts,
                "null_owner_or_category_count": sum(
                    1 for i in items if not i.get("owner") or not i.get("category")
                ),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "mode": "read_only",
        "applied_changes": False,
        "template_id": "default_kuwait",
        "template_item_count": len(template),
        "four_reals": list(FOUR_REALS),
        "employees": employees,
        "rollups": {
            "any_missing": any(e["missing_from_live"] for e in employees),
            "any_obsolete": any(e["obsolete_vs_template"] for e in employees),
            "any_conflicts": any(e["conflicts"] for e in employees),
            "brian_partial_seed": any(
                e["employee_key"].endswith("411617") and e["live_item_count"] < 4 for e in employees
            ),
        },
        "wave1_policy": {
            "do_not_apply": True,
            "seed_remains_off": True,
            "hr_mutate_remains_off": True,
            "bank_plaintext_frozen": True,
            "apply_in": "Onboarding Wave 2 controlled backfill (after GO)",
        },
    }


def to_markdown(report: dict) -> str:
    lines = [
        "# Onboarding Wave 1 — Four-real migration assessment (read-only)",
        "",
        f"**Generated:** `{report['generated_at']}`",
        f"**Template:** `{report['template_id']}` ({report['template_item_count']} items)",
        "**Applied changes:** no",
        "",
        "## Rollups",
        "",
        f"- Missing vs template: **{report['rollups']['any_missing']}**",
        f"- Obsolete vs template: **{report['rollups']['any_obsolete']}**",
        f"- Conflicts: **{report['rollups']['any_conflicts']}**",
        f"- Brian partial seed: **{report['rollups']['brian_partial_seed']}**",
        "",
    ]
    for emp in report["employees"]:
        lines.append(f"## {emp.get('name') or 'unknown'} (`{emp['employee_key']}`)")
        lines.append("")
        lines.append(f"- Live items: **{emp['live_item_count']}** → `{', '.join(emp['live_item_ids']) or 'none'}`")
        lines.append(f"- Null owner/category rows: **{emp['null_owner_or_category_count']}**")
        lines.append(f"- Missing ({len(emp['missing_from_live'])}): " + (", ".join(m['item_id'] for m in emp['missing_from_live']) or "none"))
        lines.append(f"- Obsolete ({len(emp['obsolete_vs_template'])}): " + (", ".join(o['item_id'] for o in emp['obsolete_vs_template']) or "none"))
        if emp["conflicts"]:
            lines.append("- Conflicts:")
            for c in emp["conflicts"]:
                lines.append(f"  - `{c['item_id']}` status={c.get('live_status')}: {'; '.join(c['notes'])}")
        else:
            lines.append("- Conflicts: none")
        lines.append("")
    lines.extend(
        [
            "## Policy",
            "",
            "- Do **not** apply this assessment in Wave 1.",
            "- Keep `WATHEFNI_ONBOARDING_SEED=off` and `WATHEFNI_ONBOARDING_HR_MUTATE=off`.",
            "- Bank/IBAN collection stays on encrypted ESS; do not expand plaintext onboarding.",
            "- Controlled backfill belongs to Wave 2 after GO.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-snapshot", type=Path, default=None)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=Path("."))
    args = parser.parse_args()

    template = _template_map()
    if args.from_snapshot:
        rows = _load_snapshot(args.from_snapshot)
        source = f"snapshot:{args.from_snapshot}"
    elif args.live:
        rows = _load_live()
        source = "live_db"
    else:
        default_snap = (
            Path(__file__).resolve().parents[2]
            / "ops/evidence/onboarding-wave0-prod-truth-20260801T235617Z/data/item-breakdown.txt"
        )
        if default_snap.is_file():
            rows = _load_snapshot(default_snap)
            source = f"snapshot:{default_snap}"
        else:
            raise SystemExit("Provide --from-snapshot or --live")

    report = assess(rows, template)
    report["source"] = source
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "migration-assessment.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    (args.out_dir / "migration-assessment.md").write_text(to_markdown(report), encoding="utf-8")
    print(json.dumps({"ok": True, "source": source, "out_dir": str(args.out_dir), "rollups": report["rollups"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
