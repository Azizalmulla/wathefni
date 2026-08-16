#!/usr/bin/env bash
# Local Hybrid PDF Engine Wave 1 — staging alternate-path canary qualify.
# Staging only. Does not change production. Hybrid is never authoritative.
# Rollback: remove drop-in / unset WATHEFNI_LOCAL_HYBRID_PDF_ENGINE and restart staging.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
LOCAL_EVID="$REPO_ROOT/ops/evidence/local-hybrid-pdf-engine-wave1-${STAMP}"
VPS_HOST="${VPS_HOST:-root@76.13.63.68}"
REMOTE_EVID="/opt/wathefni/staging-evidence/local-hybrid-pdf-engine-wave1/${STAMP}"
STG=/opt/wathefni/staging/orchestrator
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=25 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=25)

mkdir -p "$LOCAL_EVID"/{sources,tests,docs,flags,fixtures,results}
log() { printf '\n=== %s ===\n' "$*"; }

log "stage sources"
cp -a \
  "$ORCH_SRC/local_hybrid_pdf_engine.py" \
  "$ORCH_SRC/local_hybrid_pdf_engine_canary.py" \
  "$ORCH_SRC/scripts/wave1-local-hybrid-pdf-engine-staging-canary-qualify.py" \
  "$LOCAL_EVID/sources/"
# Copy only the app.py snippet isn't enough — sync full app.py for staging hook.
cp -a "$ORCH_SRC/app.py" "$LOCAL_EVID/sources/app.py"

log "push staging modules + fixtures"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID'/{tests,flags,fixtures,results,backup} '$STG' /etc/systemd/system/wathefni-orchestrator-staging.service.d"
# Backup existing staging modules before overwrite
"${SSH[@]}" "bash -s" <<BACKUP
set -euo pipefail
EVID='$REMOTE_EVID'
STG='$STG'
mkdir -p "\$EVID/backup"
for f in local_hybrid_pdf_engine.py local_hybrid_pdf_engine_canary.py app.py; do
  [[ -f \$STG/\$f ]] && cp -a \$STG/\$f \$EVID/backup/\$f.pre || true
done
BACKUP
"${SCP[@]}" \
  "$ORCH_SRC/local_hybrid_pdf_engine.py" \
  "$ORCH_SRC/local_hybrid_pdf_engine_canary.py" \
  "$ORCH_SRC/app.py" \
  "$ORCH_SRC/scripts/wave1-local-hybrid-pdf-engine-staging-canary-qualify.py" \
  "$VPS_HOST:$STG/"

CORPUS="$REPO_ROOT/ops/evidence/pdf-inspector-corpus-wave2-20260804/corpus"
for f in \
  wave0_cv_ar_digital_01.pdf syn_arabic_digital_cv_000.pdf \
  wave0_cv_bilingual_01.pdf wave0_cv_multicolumn_01.pdf \
  wave0_cv_scanned_en_01.pdf wave0_cv_mixed_01.pdf \
  wave0_cv_broken_encoding_01.pdf syn_broken_encoding_000.pdf \
  wave0_cv_en_digital_01.pdf
do
  "${SCP[@]}" "$CORPUS/$f" "$VPS_HOST:$REMOTE_EVID/fixtures/"
done

log "staging enable flag + offline qualify"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-qualify.out"
set -euo pipefail
STG='$STG'
PROD_VENV=/opt/wathefni/orchestrator/.venv
PY=\$PROD_VENV/bin/python
EVID='$REMOTE_EVID'
DROPIN=/etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzz-local-hybrid-pdf-engine-wave1.conf

mkdir -p "\$EVID/backup"
for f in local_hybrid_pdf_engine.py local_hybrid_pdf_engine_canary.py app.py; do
  [[ -f \$STG/\$f ]] && cp -a \$STG/\$f \$EVID/backup/ || true
done

# Ensure pdf-inspector pin remains
\$PY - <<'PY'
from importlib.metadata import version
assert version('pdf-inspector') == '0.2.6'
print('pdf-inspector', version('pdf-inspector'))
PY

cat > "\$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=staging_canary
EOF
cp -a "\$DROPIN" "\$EVID/flags/"
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
for i in \$(seq 1 60); do
  if curl -fsS http://127.0.0.1:8011/health >/dev/null 2>&1; then echo health_ok; break; fi
  sleep 1
done
systemctl is-active wathefni-orchestrator-staging
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
# Never dump full environ (may contain secrets); filter to hybrid flag only.
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E '^WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=' | tee "\$EVID/flags/staging-hybrid-flag.txt"
grep -q 'WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=staging_canary' "\$EVID/flags/staging-hybrid-flag.txt"

# Offline dual-path qualify (no candidate intake)
export WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=staging_canary
export WATHEFNI_CV_MISTRAL_OCR=true
export WATHEFNI_MISTRAL_ENV=/root/.openclaw/secrets/mistral.env
export PYTHONPATH="\$STG:/opt/wathefni/orchestrator:\${PYTHONPATH:-}"
mkdir -p /tmp/hybrid-wave1-corpus/corpus
cp -a "\$EVID/fixtures/"*.pdf /tmp/hybrid-wave1-corpus/corpus/
# Point qualify script corpus root via symlink layout expected by script
mkdir -p /tmp/hybrid-wave1-evidence
ln -sfn /tmp/hybrid-wave1-corpus /tmp/hybrid-wave1-link-corpus 2>/dev/null || true

\$PY - <<'PY'
import json, os, sys, time
from pathlib import Path
from datetime import datetime, timezone

STG = Path("/opt/wathefni/staging/orchestrator")
EVID = Path("$REMOTE_EVID")
FIX = EVID / "fixtures"
OUT = EVID / "results"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(STG))
sys.path.insert(0, "/opt/wathefni/orchestrator")

os.environ["WATHEFNI_LOCAL_HYBRID_PDF_ENGINE"] = "staging_canary"
os.environ["WATHEFNI_CV_MISTRAL_OCR"] = "true"

import cv_extraction as cv
import cv_extraction_v2 as cv2
import local_hybrid_pdf_engine_canary as canary
from local_hybrid_pdf_engine import extract_pdf_hybrid, HybridEngineLimits

assert canary.canary_enabled()
assert not canary.canary_enabled() if False else True

# flag-off smoke
os.environ["WATHEFNI_LOCAL_HYBRID_PDF_ENGINE"] = "0"
assert canary.canary_enabled() is False
off = canary.run_cv_hybrid_alternate_canary(
    path=next(FIX.glob("*.pdf")),
    mime_type="application/pdf",
    company_code="WATHEFNI",
    authoritative_extraction=cv.ExtractionResult(text="", method="test"),
    authoritative_v2={"ok": True, "payload": {}},
)
assert off.get("skipped") == "flag_off"
os.environ["WATHEFNI_LOCAL_HYBRID_PDF_ENGINE"] = "staging_canary"
assert canary.canary_enabled()

SELECTED = [
    ("wave0_cv_ar_digital_01.pdf", "arabic_digital_cv"),
    ("syn_arabic_digital_cv_000.pdf", "arabic_digital_cv"),
    ("wave0_cv_bilingual_01.pdf", "bilingual_cv"),
    ("wave0_cv_multicolumn_01.pdf", "multicolumn_cv"),
    ("wave0_cv_scanned_en_01.pdf", "scanned_image_only_cv"),
    ("wave0_cv_mixed_01.pdf", "mixed_digital_scanned"),
    ("wave0_cv_broken_encoding_01.pdf", "broken_encoding"),
    ("syn_broken_encoding_000.pdf", "broken_encoding"),
    ("wave0_cv_en_digital_01.pdf", "english_digital_cv"),
]

rows = []
for name, cat in SELECTED:
    path = FIX / name
    print(f"qualify {name}", flush=True)
    t0 = time.perf_counter()
    auth = cv.extract_cv_document(path, mime_type="application/pdf", company_code="WATHEFNI")
    auth_v2 = cv2.run_v2_extraction(
        local_path=path,
        mime_type="application/pdf",
        extracted_text=auth.text or "",
        blocks=list(auth.blocks or []),
        prefer_reuse_text=False,
    )
    result = canary.run_cv_hybrid_alternate_canary(
        path=path,
        mime_type="application/pdf",
        company_code="WATHEFNI",
        authoritative_extraction=auth,
        authoritative_v2=auth_v2,
        app_key=f"stg-canary-{path.stem}",
        db_execute=None,
        allow_paid_ocr=True,
    )
    rows.append({
        "file": name,
        "category": cat,
        "wall_ms": int((time.perf_counter()-t0)*1000),
        "auth_method": auth.method,
        "auth_v2_ok": bool(auth_v2.get("ok")),
        "canary_ok": result.get("ok"),
        "acceptance": result.get("acceptance"),
        "ocr_pages": result.get("ocr_pages"),
        "structured_reduction": (result.get("v2_compare") or {}).get("structured", {}).get("structured_field_accuracy_reduction"),
        "envelope": (result.get("document_envelope") or {}).get("contract"),
        "costs": result.get("mistral_calls_and_cost"),
        "error": result.get("error"),
    })
    (OUT / f"{path.stem}.canary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))

acc = [r.get("acceptance") or {} for r in rows]
summary = {
    "wave": "local_hybrid_pdf_engine_wave1_staging_canary",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "hybrid_authoritative": False,
    "docs": len(rows),
    "gates": {
        "zero_false_ocr_skips": all(a.get("zero_false_ocr_skips") for a in acc),
        "zero_structured_field_accuracy_reduction": all(a.get("zero_structured_field_accuracy_reduction") for a in acc),
        "zero_missing_ranking_evidence": all(a.get("zero_missing_ranking_evidence") for a in acc),
        "v2_completion_same_or_better": all(a.get("v2_completion_same_or_better") for a in acc),
        "all_docs_canary_ok": all(r.get("canary_ok") for r in rows),
        "flag_off_skips": True,
        "envelope_document_envelope_at_1": all(r.get("envelope") == "document_envelope@1" for r in rows),
    },
    "rows": rows,
}
summary["gates"]["all_pass"] = all(summary["gates"].values())
(OUT / "canary_qualify_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
print(json.dumps({"docs": summary["docs"], "gates": summary["gates"]}, indent=2))
if not summary["gates"]["all_pass"]:
    raise SystemExit(2)
PY

# Rollback proof: unset flag, restart, confirm absent
rm -f "\$DROPIN"
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
for i in \$(seq 1 60); do
  if curl -fsS http://127.0.0.1:8011/health >/dev/null 2>&1; then echo health_ok_after_rollback; break; fi
  sleep 1
done
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
if tr '\\0' '\\n' < /proc/\$PID/environ | grep -q '^WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=staging_canary'; then
  echo 'ROLLBACK_FAILED flag still present' >&2
  exit 2
fi
echo 'rollback_ok flag_absent' | tee "\$EVID/flags/rollback.txt"

# Re-enable canary for ongoing staging observation (owner-approved wave goal)
cat > "\$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=staging_canary
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
for i in \$(seq 1 60); do
  if curl -fsS http://127.0.0.1:8011/health >/dev/null 2>&1; then echo health_ok_reenabled; break; fi
  sleep 1
done
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E '^WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=' | tee "\$EVID/flags/staging-hybrid-flag-final.txt"
grep -q 'staging_canary' "\$EVID/flags/staging-hybrid-flag-final.txt"
echo STAGING_CANARY_ENABLED
REMOTE

log "pull evidence"
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/" "$LOCAL_EVID/remote/"
cp -a "$LOCAL_EVID/remote/results/." "$LOCAL_EVID/results/" 2>/dev/null || true
cp -a "$LOCAL_EVID/remote/flags/." "$LOCAL_EVID/flags/" 2>/dev/null || true

python3 - <<PY
import json
from pathlib import Path
evid = Path("$LOCAL_EVID")
summary = json.loads((evid/"results/canary_qualify_summary.json").read_text())
gate = {
  "wave": "local_hybrid_pdf_engine_wave1_staging_canary",
  "staging_only": True,
  "production_deployed": False,
  "hybrid_authoritative": False,
  "gates": summary.get("gates"),
  "docs": summary.get("docs"),
  "rollback_proven": (evid/"flags/rollback.txt").exists(),
}
(evid/"docs/GATE.json").write_text(json.dumps(gate, indent=2))
print(json.dumps(gate, indent=2))
if not (summary.get("gates") or {}).get("all_pass"):
    raise SystemExit(2)
PY

log "DONE evidence=$LOCAL_EVID"
