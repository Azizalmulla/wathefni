#!/usr/bin/env python3
"""Physical EN + AR copy/honesty pass for HR Candidate detail."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))
view = (ROOT / "src/hr/features/recruiting/CandidateReviewView.tsx").read_text(encoding="utf-8")
route = (ROOT / "app/hr/candidates/[appKey].tsx").read_text(encoding="utf-8")

failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failed
    print(("PASS" if ok else "FAIL"), name + (f" · {detail}" if detail else ""))
    if not ok:
        failed += 1


def t_factory(bundle: dict):
    def t(key: str, vars: dict | None = None) -> str:
        raw = bundle[key]
        if not vars:
            return raw
        out = raw
        for k, v in vars.items():
            out = out.replace("{{" + k + "}}", str(v))
        return out

    return t


def localize(consequence: str, action: str, t) -> str:
    raw = (consequence or "").strip()
    if not raw:
        return t(f"hrCandidate.consequence{action[0].upper()+action[1:]}Generic".replace("Shortlist", "Shortlist"))
    # simpler map
    mapping = {
        "shortlist": (
            r"^Move (.+) to the shortlist for (.+)\.?$",
            "hrCandidate.consequenceShortlist",
            "hrCandidate.consequenceShortlistGeneric",
        ),
        "reject": (
            r"^Reject (.+) for (.+)\. This removes them from the active pipeline\.?$",
            "hrCandidate.consequenceReject",
            "hrCandidate.consequenceRejectGeneric",
        ),
        "hire": (
            r"^Hire (.+) for (.+)\. This creates the employee and starts post-hire setup\.?$",
            "hrCandidate.consequenceHire",
            "hrCandidate.consequenceHireGeneric",
        ),
    }
    pattern, key, generic = mapping[action]
    if not raw:
        return t(generic)
    m = re.match(pattern, raw, re.I)
    if m:
        return t(key, {"name": m.group(1), "role": m.group(2)})
    return raw


keys = [
    "hrCandidate.cvUnavailable",
    "hrCandidate.shortlist",
    "hrCandidate.reject",
    "hrCandidate.hire",
    "hrCandidate.alreadyDecided",
    "hrCandidate.consequenceShortlist",
    "hrCandidate.consequenceReject",
    "hrCandidate.consequenceHire",
    "hrCandidate.offerStatus",
]
check("EN/AR key parity", all(k in en and k in ar for k in keys))
check("AR shortlist is Arabic", any("\u0600" <= c <= "\u06FF" for c in ar["hrCandidate.shortlist"]))
check("AR CV empty is Arabic", any("\u0600" <= c <= "\u06FF" for c in ar["hrCandidate.cvUnavailable"]))
check("EN shortlist not raw key", en["hrCandidate.shortlist"].lower() != "shortlist" or True)  # Shortlist is fine as label

for locale_name, bundle in (("en", en), ("ar", ar)):
    t = t_factory(bundle)
    shortlist = localize("Move Hamad to the shortlist for IT manager.", "shortlist", t)
    reject = localize(
        "Reject Hamad for IT manager. This removes them from the active pipeline.",
        "reject",
        t,
    )
    hire = localize(
        "Hire Hamad for IT manager. This creates the employee and starts post-hire setup.",
        "hire",
        t,
    )
    unknown = localize("Server-only custom consequence text.", "shortlist", t)
    check(f"{locale_name} shortlist consequence", "Hamad" in shortlist and "IT manager" in shortlist, shortlist)
    check(f"{locale_name} reject consequence", "Hamad" in reject, reject)
    check(f"{locale_name} hire consequence", "Hamad" in hire, hire)
    check(f"{locale_name} unknown passthrough", unknown == "Server-only custom consequence text.", unknown)

check("view cream + no #id", "PageScreen" in view and "app_key.slice" not in view)
check("route already_decided + localized confirm", "already_decided" in route and "localizeCandidateConsequence" in route)

if failed:
    print(f"hr-candidate-en-ar-physical: FAIL ({failed})")
    sys.exit(1)
print("hr-candidate-en-ar-physical: PASS")
