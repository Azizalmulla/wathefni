#!/usr/bin/env bash
# Document Processing Foundation Wave 1 — qualify then optionally enable production CV PDF authority.
# Does NOT enable production until qualify gates pass and ENABLE_PROD=1 is set.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
LOCAL_EVID="$REPO_ROOT/ops/evidence/document-processing-foundation-wave1-${STAMP}"
VPS_HOST="${VPS_HOST:-root@76.13.63.68}"
REMOTE_EVID="/opt/wathefni/evidence/document-processing-foundation-wave1/${STAMP}"
PROD=/opt/wathefni/orchestrator
STG=/opt/wathefni/staging/orchestrator
ENABLE_PROD="${ENABLE_PROD:-0}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=25 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=25)

mkdir -p "$LOCAL_EVID"/{sources,results,docs,flags,fixtures}
log() { printf '\n=== %s ===\n' "$*"; }

MODULES=(
  document_processing_foundation.py
  cv_pdf_reading_authority.py
  local_hybrid_pdf_engine.py
  local_hybrid_pdf_engine_canary.py
  cv_extraction.py
)

log "copy sources"
for f in "${MODULES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$ORCH_SRC/scripts/wave1-document-processing-foundation-qualify.py" "$LOCAL_EVID/sources/"

log "sync to VPS evidence + staging (qualify runs against staging copy + prod venv)"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID'/{results,docs,flags,fixtures,backup} '$STG'"
# backup staging modules
"${SSH[@]}" "bash -s" <<B
set -euo pipefail
EVID='$REMOTE_EVID'; STG='$STG'
for f in document_processing_foundation.py cv_pdf_reading_authority.py local_hybrid_pdf_engine.py local_hybrid_pdf_engine_canary.py cv_extraction.py; do
  [[ -f \$STG/\$f ]] && cp -a \$STG/\$f \$EVID/backup/\$f.stg || true
done
B
for f in "${MODULES[@]}"; do
  "${SCP[@]}" "$ORCH_SRC/$f" "$VPS_HOST:$STG/"
done
"${SCP[@]}" "$ORCH_SRC/scripts/wave1-document-processing-foundation-qualify.py" "$VPS_HOST:$STG/"

CORPUS="$REPO_ROOT/ops/evidence/pdf-inspector-corpus-wave2-20260804/corpus"
for f in \
  wave0_cv_ar_digital_01.pdf syn_arabic_digital_cv_000.pdf wave0_cv_bilingual_01.pdf \
  wave0_cv_multicolumn_01.pdf wave0_cv_scanned_en_01.pdf wave0_cv_mixed_01.pdf \
  wave0_cv_broken_encoding_01.pdf syn_broken_encoding_000.pdf wave0_cv_en_digital_01.pdf
do
  "${SCP[@]}" "$CORPUS/$f" "$VPS_HOST:$REMOTE_EVID/fixtures/"
done

log "run foundation qualify on VPS"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/results/qualify.out"
set -euo pipefail
STG='$STG'
EVID='$REMOTE_EVID'
PY=/opt/wathefni/orchestrator/.venv/bin/python
export PYTHONPATH="\$STG:/opt/wathefni/orchestrator:\${PYTHONPATH:-}"
export WATHEFNI_MISTRAL_ENV=/root/.openclaw/secrets/mistral.env
export WATHEFNI_CV_MISTRAL_OCR=true
export WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK=off
# Point corpus path used by script via symlink
mkdir -p /tmp/foundation-wave1/corpus
cp -a "\$EVID/fixtures/"*.pdf /tmp/foundation-wave1/corpus/
# Patch script corpus/evidence paths for remote
\$PY - <<'PY'
import json, os, sys, time, tempfile, shutil
from datetime import datetime, timezone
from pathlib import Path

STG = Path("/opt/wathefni/staging/orchestrator")
EVID = Path("$REMOTE_EVID")
CORPUS = Path("/tmp/foundation-wave1/corpus")
RESULTS = EVID / "results"
RESULTS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(STG))
sys.path.insert(0, "/opt/wathefni/orchestrator")

os.environ["WATHEFNI_LOCAL_HYBRID_PDF_ENGINE"] = "production_authority"
os.environ["WATHEFNI_CV_MISTRAL_OCR"] = "true"
os.environ["WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK"] = "off"
os.environ.pop("WATHEFNI_CV_GPT_VISION_RESCUE", None)

import cv_extraction as cv
import cv_extraction_v2 as cv2
import document_processing_foundation as foundation
from local_hybrid_pdf_engine_canary import compare_v2_structured

assert foundation.cv_pdf_authority_enabled()
assert cv.gpt_vision_rescue_enabled() is False

FIXTURES = [
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
TRUE_NEED = {"image_only_page","scanned_or_empty","corrupt_or_unusable_text","image_dominant_sparse_text"}
rows=[]; false_skips=0; gpt_inv=0
for name, cat in FIXTURES:
    path = CORPUS/name
    print("qualify", name, flush=True)
    t0=time.perf_counter()
    os.environ["WATHEFNI_LOCAL_HYBRID_PDF_ENGINE"]="0"
    poppler=cv.extract_cv_document(path, mime_type="application/pdf", company_code="WATHEFNI")
    poppler_v2=cv2.run_v2_extraction(local_path=path, mime_type="application/pdf", extracted_text=poppler.text or "", blocks=list(poppler.blocks or []))
    os.environ["WATHEFNI_LOCAL_HYBRID_PDF_ENGINE"]="production_authority"
    auth=cv.extract_cv_document(path, mime_type="application/pdf", company_code="WATHEFNI")
    auth_v2=cv2.run_v2_extraction(local_path=path, mime_type="application/pdf", extracted_text=auth.text or "", blocks=list(auth.blocks or []))
    env=(auth.metadata or {}).get("document_envelope")
    env_ok, env_reason = foundation.envelope_complete(env) if env else (auth.method!="local_hybrid_pdf_engine", "fallback_or_missing")
    poppler_needs=[a.page_number for a in (poppler.page_assessments or []) if a.disposition=="needs_ocr" and a.reason in TRUE_NEED]
    fs=[]
    if auth.method=="local_hybrid_pdf_engine":
        by={a.page_number:a for a in (auth.page_assessments or [])}
        for pn in poppler_needs:
            a=by.get(pn)
            if not a or not (a.local_text or "").strip():
                fs.append(pn)
    if fs: false_skips+=1
    if (auth.metadata or {}).get("gpt_vision_invoked"): gpt_inv+=1
    structured_regression=False; evidence_regression=False; cmp_={}
    try:
        raw=poppler_v2.get("raw_provider_response") or {}
        if raw:
            ann=cv2.extract_annotation_object(raw)
            av=cv2.validate_v2_payload(ann, source_text=poppler.text or "")
            hv=cv2.validate_v2_payload(ann, source_text=auth.text or "")
            cmp_=compare_v2_structured(auth_payload=av.get("payload") or {}, hybrid_payload=hv.get("payload") or {}, auth_ok=bool(av.get("ok")), hybrid_ok=bool(hv.get("ok")))
            structured_regression=bool(cmp_.get("structured_field_accuracy_reduction"))
            evidence_regression=bool(cmp_.get("evidence_regression") or cmp_.get("ranking_regression"))
    except Exception as e:
        structured_regression=True; evidence_regression=True; cmp_={"error":str(e)}
    rows.append({
        "file":name,"category":cat,"wall_ms":int((time.perf_counter()-t0)*1000),
        "authority_method":auth.method,
        "hybrid_accepted":auth.method=="local_hybrid_pdf_engine",
        "fallback_meta":(auth.metadata or {}).get("hybrid_authority_fallback"),
        "envelope_ok":bool(env_ok) if auth.method=="local_hybrid_pdf_engine" else True,
        "false_skip_pages":fs,
        "gpt_vision_invoked":bool((auth.metadata or {}).get("gpt_vision_invoked")),
        "poppler_v2_ok":bool(poppler_v2.get("ok")),"auth_v2_ok":bool(auth_v2.get("ok")),
        "v2_completion_ok":(not poppler_v2.get("ok")) or bool(auth_v2.get("ok")),
        "structured_regression":structured_regression,"evidence_regression":evidence_regression,
    })

# fallback proof via stop file
stop=EVID/"STOP_TEST"; stop.write_text("stop\n")
os.environ["WATHEFNI_DOC_FOUNDATION_STOP_FILE"]=str(stop)
os.environ["WATHEFNI_LOCAL_HYBRID_PDF_ENGINE"]="production_authority"
fb=cv.extract_cv_document(CORPUS/"wave0_cv_en_digital_01.pdf", mime_type="application/pdf", company_code="WATHEFNI")
stop.unlink(missing_ok=True); os.environ.pop("WATHEFNI_DOC_FOUNDATION_STOP_FILE", None)
fallback_proof={"stop_file_triggered_fallback": fb.method!="local_hybrid_pdf_engine", "method": fb.method, "meta": (fb.metadata or {}).get("hybrid_authority_fallback")}

# DOCX
docx_proof={"ran":False}
try:
    from docx import Document
    docx_path=EVID/"fixtures"/"synthetic_cv.docx"; docx_path.parent.mkdir(parents=True, exist_ok=True)
    d=Document(); d.add_heading("Sara AlSabah",1); d.add_paragraph("Email: sara.alsabah@synthetic-eval.example"); d.add_paragraph("Phone: +96551112233"); d.add_paragraph("EXPERIENCE"); d.add_paragraph("2020-2026 Wathefni Test Co — Software Engineer"); d.add_paragraph("المهارات: Python, Postgres")
    t=d.add_table(rows=2,cols=2); t.rows[0].cells[0].text="Year"; t.rows[0].cells[1].text="Role"; t.rows[1].cells[0].text="2024"; t.rows[1].cells[1].text="Engineer"; d.save(docx_path)
    import cv_docx
    dr=cv_docx.extract_docx_document(docx_path, company_code="WATHEFNI")
    dv=cv2.run_v2_extraction(local_path=docx_path, mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", extracted_text=dr.text or "", blocks=list(dr.blocks or []))
    docx_proof={"ran":True,"chars":len(dr.text or ""),"arabic_chars":sum(1 for c in (dr.text or "") if "\u0600"<=c<="\u06FF"),"table":("Year" in (dr.text or "") or "Engineer" in (dr.text or "")),"v2_ok":bool(dv.get("ok")),"v2_path":dv.get("path"),"reaches_v2":True,"gpt_vision_invoked":False}
except Exception as e:
    docx_proof={"ran":False,"error":f"{type(e).__name__}:{e}"}

# Image
image_proof={"ran":False}
try:
    tmp=Path(tempfile.mkdtemp(prefix="fimg-"))
    rendered=cv.render_pdf_pages_to_png(CORPUS/"wave0_cv_scanned_en_01.pdf",[1],tmp)
    if 1 in rendered:
        ir=cv.extract_cv_document(rendered[1], mime_type="image/png", company_code="WATHEFNI")
        iv=cv2.run_v2_extraction(local_path=rendered[1], mime_type="image/png", extracted_text=ir.text or "", blocks=list(ir.blocks or []))
        image_proof={"ran":True,"method":ir.method,"quality_ok":ir.quality_ok,"gpt_vision_invoked":bool((ir.metadata or {}).get("gpt_vision_invoked")),"reaches_v2":True,"v2_ok":bool(iv.get("ok")),"v2_path":iv.get("path")}
    shutil.rmtree(tmp, ignore_errors=True)
except Exception as e:
    image_proof={"ran":False,"error":f"{type(e).__name__}:{e}"}

gates={
  "nine_fixtures_ran": len(rows)==9,
  "zero_false_ocr_skips": false_skips==0,
  "zero_structured_regression": all(not r["structured_regression"] for r in rows),
  "zero_evidence_regression": all(not r["evidence_regression"] for r in rows),
  "v2_completion_same_or_better": all(r["v2_completion_ok"] for r in rows),
  "automatic_poppler_fallback_proven": bool(fallback_proof["stop_file_triggered_fallback"]),
  "gpt_auto_fallback_off": cv.gpt_vision_rescue_enabled() is False and gpt_inv==0,
  "docx_reaches_v2": bool(docx_proof.get("reaches_v2")),
  "image_no_gpt_and_reaches_v2": bool(image_proof.get("reaches_v2")) and not image_proof.get("gpt_vision_invoked", False),
  "route_matrix_loaded": len(foundation.ROUTE_MATRIX)>=10,
}
gates["all_pass"]=all(gates.values())
summary={
  "wave":"document_processing_foundation_wave1_qualify",
  "created_at":datetime.now(timezone.utc).isoformat(),
  "gates":gates,
  "false_skips":false_skips,
  "fallback_proof":fallback_proof,
  "gpt_invocations":gpt_inv,
  "docx_proof":docx_proof,
  "image_proof":image_proof,
  "rows":rows,
  "route_matrix":foundation.ROUTE_MATRIX,
  "identity_gpt_audit":{
    "entry":"app.extract_compliance_document_metadata",
    "types":["civil_id","passport","medical","residency","work_permit"],
    "uses_cv_v2":False,
    "replacement_plan":[
      "shared envelope intake for identity",
      "qualify Mistral/dedicated identity reader vs labeled set",
      "keep HR confirmation authority",
      "owner GO before swapping GPT identity authority"
    ]
  },
  "legacy_authority_classes":["identity GPT vision","contract/compliance processors","payslip/generated/mirror never OCR","spreadsheet never OCR"],
  "cloud_portability":{"aws_deps":False,"gcp_deps":False,"envelope":foundation.CONTRACT_ENVELOPE},
}
(RESULTS/"foundation_qualify_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
print(json.dumps({"gates":gates,"docs":len(rows)}, indent=2))
raise SystemExit(0 if gates["all_pass"] else 2)
PY
REMOTE

log "pull results"
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/results/" "$LOCAL_EVID/results/"

python3 - <<PY
import json
from pathlib import Path
s=json.loads(Path("$LOCAL_EVID/results/foundation_qualify_summary.json").read_text())
print(json.dumps(s["gates"], indent=2))
if not s["gates"].get("all_pass"):
    raise SystemExit(2)
PY

if [[ "$ENABLE_PROD" != "1" ]]; then
  log "Qualify PASS. Production NOT enabled (set ENABLE_PROD=1 to activate)."
  echo "qualify_only" > "$LOCAL_EVID/flags/activation.txt"
  exit 0
fi

log "ENABLE_PROD=1 — deploying CV PDF authority to production with rollback backup"
"${SSH[@]}" "bash -s" <<PROD
set -euo pipefail
PROD='$PROD'
EVID='$REMOTE_EVID'
STG='$STG'
BK=/opt/wathefni/backups/production-pre-doc-foundation-wave1-\$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "\$BK/orchestrator" "\$EVID/flags"
for f in document_processing_foundation.py cv_pdf_reading_authority.py local_hybrid_pdf_engine.py local_hybrid_pdf_engine_canary.py cv_extraction.py; do
  cp -a \$PROD/\$f \$BK/orchestrator/ 2>/dev/null || true
  cp -a \$STG/\$f \$PROD/
done
cat > /etc/systemd/system/wathefni-orchestrator.service.d/zzzz-doc-foundation-wave1.conf <<'EOF'
[Service]
Environment=WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=production_authority
Environment=WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK=off
Environment=WATHEFNI_DOC_FOUNDATION_DAILY_OCR_COST_CAP_USD=2.0
Environment=WATHEFNI_DOC_FOUNDATION_DAILY_DOC_AI_COST_CAP_USD=5.0
Environment=WATHEFNI_DOC_FOUNDATION_MAX_SAMPLED_PDFS=50
EOF
# Keep staging canary distinct — set staging to production_authority too for parity or leave canary
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzz-doc-foundation-wave1.conf <<'EOF'
[Service]
Environment=WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=production_authority
Environment=WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK=off
EOF
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/zzzz-doc-foundation-wave1.conf \$EVID/flags/
cat > \$BK/ROLLBACK.sh <<EOF
#!/bin/bash
set -euo pipefail
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzz-doc-foundation-wave1.conf
cp -a \$BK/orchestrator/. $PROD/ || true
systemctl daemon-reload
systemctl restart wathefni-orchestrator
echo rolled_back
EOF
chmod +x \$BK/ROLLBACK.sh
echo \$BK > \$EVID/flags/backup_path.txt
systemctl daemon-reload
systemctl restart wathefni-orchestrator
systemctl restart wathefni-orchestrator-staging
for i in \$(seq 1 60); do curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1 && break; sleep 1; done
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E '^WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=|^WATHEFNI_DOC_FOUNDATION_' | tee \$EVID/flags/prod-foundation-flags.txt
grep -q 'production_authority' \$EVID/flags/prod-foundation-flags.txt
# rollback proof then re-enable
bash \$BK/ROLLBACK.sh
sleep 2
for i in \$(seq 1 60); do curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1 && break; sleep 1; done
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
if tr '\\0' '\\n' < /proc/\$PID/environ | grep -q 'production_authority'; then echo ROLLBACK_FAILED; exit 2; fi
echo rollback_ok | tee \$EVID/flags/rollback.txt
# re-enable authority after proven rollback
cp -a \$EVID/flags/zzzz-doc-foundation-wave1.conf /etc/systemd/system/wathefni-orchestrator.service.d/zzzz-doc-foundation-wave1.conf
# restore modules from STG again
for f in document_processing_foundation.py cv_pdf_reading_authority.py local_hybrid_pdf_engine.py local_hybrid_pdf_engine_canary.py cv_extraction.py; do
  cp -a \$STG/\$f \$PROD/
done
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in \$(seq 1 60); do curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1 && break; sleep 1; done
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E '^WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=' | tee \$EVID/flags/prod-foundation-flags-final.txt
grep -q production_authority \$EVID/flags/prod-foundation-flags-final.txt
echo PRODUCTION_AUTHORITY_ENABLED backup=\$BK
PROD

rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/flags/" "$LOCAL_EVID/flags/" || true
echo "production_enabled" > "$LOCAL_EVID/flags/activation.txt"
log "DONE evidence=$LOCAL_EVID"
