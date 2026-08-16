#!/usr/bin/env bash
# AnyDoc Office Authority Closure — qualify then deploy format-correct authority.
# Never enables PDF/identity/hosted parse. Never replaces XLSX/CSV structured authority.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
LOCAL_EVID="$REPO_ROOT/ops/evidence/anydoc-office-authority-closure-${STAMP}"
VPS_HOST="${VPS_HOST:-root@76.13.63.68}"
REMOTE_EVID="/opt/wathefni/evidence/anydoc-office-authority-closure/${STAMP}"
PROD=/opt/wathefni/orchestrator
STG=/opt/wathefni/staging/orchestrator
ENABLE_PROD="${ENABLE_PROD:-0}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)

mkdir -p "$LOCAL_EVID"/{sources,results,docs,flags,corpus,backup}
log() { printf '\n=== %s ===\n' "$*"; }

MODULES=(
  anydoc_office_authority.py
  anydoc_office_shadow.py
  smoke-test-anydoc-office-authority-closure.py
  smoke-test-anydoc-office-shadow-wave1.py
)

log "local smoke + qualify"
"$ORCH_SRC/.venv/bin/python" "$ORCH_SRC/smoke-test-anydoc-office-authority-closure.py" | tee "$LOCAL_EVID/results/local-smoke.out"
ANYDOC_AUTH_OUT="$LOCAL_EVID/local-qualify" \
  "$ORCH_SRC/.venv/bin/python" "$REPO_ROOT/ops/qualify-anydoc-office-authority-closure.py" | tee "$LOCAL_EVID/results/local-qualify.out"
grep -q ANYDOC_OFFICE_AUTHORITY_QUALIFY_OK "$LOCAL_EVID/results/local-qualify.out"
cp -a "$LOCAL_EVID/local-qualify/corpus" "$LOCAL_EVID/" 2>/dev/null || true
cp -a "$LOCAL_EVID/local-qualify/authority_qualify_results.json" "$LOCAL_EVID/results/" 2>/dev/null || true

log "stage sources"
for f in "${MODULES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$ORCH_SRC/app.py" "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/requirements.txt" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/qualify-anydoc-office-authority-closure.py" "$LOCAL_EVID/sources/"

log "push to VPS"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID'/{results,docs,flags,corpus,backup/staging,backup/prod,sources} '$STG' '$PROD'"
for f in "${MODULES[@]}" app.py requirements.txt; do
  "${SCP[@]}" "$ORCH_SRC/$f" "$VPS_HOST:$REMOTE_EVID/sources/"
done
"${SCP[@]}" "$REPO_ROOT/ops/qualify-anydoc-office-authority-closure.py" "$VPS_HOST:$REMOTE_EVID/sources/"
"${SSH[@]}" "rm -rf '$REMOTE_EVID/corpus' && mkdir -p '$REMOTE_EVID/corpus'"
"${SCP[@]}" -r "$LOCAL_EVID/corpus/." "$VPS_HOST:$REMOTE_EVID/corpus/" || true

log "install staging + authority=staging"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/results/staging-deploy.out"
set -euo pipefail
STAMP='$STAMP'
EVID='$REMOTE_EVID'
STG='$STG'
PY=/opt/wathefni/orchestrator/.venv/bin/python
PIP=/opt/wathefni/orchestrator/.venv/bin/pip
BACKUP=/opt/wathefni/backups/staging-pre-anydoc-office-authority-\$STAMP
mkdir -p "\$BACKUP/modules" "\$EVID/backup/staging" "\$EVID/flags" "\$EVID/results"
for f in anydoc_office_authority.py anydoc_office_shadow.py app.py requirements.txt \
         smoke-test-anydoc-office-authority-closure.py smoke-test-anydoc-office-shadow-wave1.py; do
  [[ -f "\$STG/\$f" ]] && cp -a "\$STG/\$f" "\$BACKUP/modules/\$f" || true
done
echo "\$BACKUP" | tee "\$EVID/backup/staging/BACKUP_PATH.txt"
cp -a "\$EVID/sources/anydoc_office_authority.py" "\$STG/"
cp -a "\$EVID/sources/anydoc_office_shadow.py" "\$STG/"
cp -a "\$EVID/sources/app.py" "\$STG/"
cp -a "\$EVID/sources/smoke-test-anydoc-office-authority-closure.py" "\$STG/"
cp -a "\$EVID/sources/smoke-test-anydoc-office-shadow-wave1.py" "\$STG/"
\$PIP install 'firecrawl-anydoc==0.1.2'
\$PY -c 'import importlib.metadata as m; assert m.version("firecrawl-anydoc")=="0.1.2"'
DROP=/etc/systemd/system/wathefni-orchestrator-staging.service.d
mkdir -p "\$DROP"
# Replace prior shadow-only drop-in so lexical order cannot override authority shadow mode.
rm -f "\$DROP/anydoc-office-shadow.conf"
cat > "\$DROP/zzz-anydoc-office-authority.conf" <<'EOF'
[Service]
Environment=WATHEFNI_ANYDOC_OFFICE_AUTHORITY=staging
Environment=WATHEFNI_ANYDOC_OFFICE_SHADOW=production_shadow
Environment=WATHEFNI_ANYDOC_OFFICE_SHADOW_TIMEOUT_MS=2000
EOF
rm -f "\$DROP/anydoc-office-authority.conf"
# Keep prior shadow drop-in if present; authority conf is additive.
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
for i in \$(seq 1 60); do
  if curl -fsS http://127.0.0.1:8011/health >/dev/null 2>&1; then echo staging_health_ok; break; fi
  sleep 1
done
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E 'WATHEFNI_ANYDOC_OFFICE_(AUTHORITY|SHADOW)=' | tee "\$EVID/flags/staging_flags.txt"
echo STAGING_AUTHORITY_DEPLOY_OK
REMOTE
grep -q STAGING_AUTHORITY_DEPLOY_OK "$LOCAL_EVID/results/staging-deploy.out"

log "staging smoke + corpus qualify on VPS"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/results/staging-qualify.out"
set -euo pipefail
STG='$STG'
EVID='$REMOTE_EVID'
PY=/opt/wathefni/orchestrator/.venv/bin/python
export PYTHONPATH="\$STG:/opt/wathefni/orchestrator:\${PYTHONPATH:-}"
export WATHEFNI_ANYDOC_OFFICE_AUTHORITY=staging
export WATHEFNI_ANYDOC_OFFICE_SHADOW=production_shadow
export WATHEFNI_ANYDOC_OFFICE_SHADOW_TIMEOUT_MS=5000
cd "\$STG"
\$PY smoke-test-anydoc-office-authority-closure.py | tee "\$EVID/results/smoke.out"
# Run qualify against pushed corpus (script rebuilds local corpus; point OUT to EVID)
mkdir -p "\$EVID/vps-qualify"
# Copy corpus into expected rebuild dir by setting OUT and skipping rebuild via env
export ANYDOC_AUTH_OUT="\$EVID/vps-qualify"
# Use prebuilt corpus: sync into OUT/corpus
rm -rf "\$EVID/vps-qualify/corpus"
cp -a "\$EVID/corpus" "\$EVID/vps-qualify/corpus"
\$PY - <<'PY'
import json, os, sys, hashlib, csv
from pathlib import Path
STG = Path("$STG")
EVID = Path("$REMOTE_EVID")
sys.path.insert(0, str(STG))
os.environ["WATHEFNI_ANYDOC_OFFICE_AUTHORITY"] = "staging"
os.environ["WATHEFNI_ANYDOC_OFFICE_SHADOW"] = "production_shadow"
import anydoc_office_authority as auth
import anydoc_office_shadow as shadow

class R:
    def __init__(self, text, method="existing"):
        self.text = text; self.method = method; self.error = None
        self.quality_ok = bool(text); self.blocks = [{"source":"baseline"}]
        self.provenance = []; self.content_sha256 = None; self.metadata = {}

def baseline(path: Path):
    ext = path.suffix.lower()
    if ext == ".docx":
        try:
            import cv_docx
            blocks, _i, _m = cv_docx.parse_docx_local(path)
            return cv_docx.blocks_to_text(blocks), "docx-local"
        except Exception:
            return "", "docx-local"
    if ext == ".csv":
        return path.read_text(encoding="utf-8", errors="ignore"), "text"
    if ext == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        rows = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                rows.append("\\t".join("" if c is None else str(c) for c in row))
        return "\\n".join(rows), "openpyxl"
    return "", "existing"

def xrows(path):
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    return [tuple(r) for ws in wb.worksheets for r in ws.iter_rows(values_only=True)]

def crows(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

corpus = Path("$REMOTE_EVID") / "corpus"
rows=[]; arabic={}; structured={}
for path in sorted(corpus.glob("*")):
    if not path.is_file():
        continue
    ext = path.suffix.lower()
    if ext not in shadow.ALLOWED_EXTENSIONS:
        continue
    base, method = baseline(path)
    result = R(base, method)
    result.content_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    bx = xrows(path) if ext == ".xlsx" else None
    bc = crows(path) if ext == ".csv" else None
    out = auth.apply_office_authority(result, path, company_code="WATHEFNI")
    d = (out.metadata or {}).get("anydoc_office_authority") or {}
    ax = xrows(path) if ext == ".xlsx" else None
    ac = crows(path) if ext == ".csv" else None
    if ext in {".xlsx", ".csv"}:
        structured[path.name] = {
            "text_unchanged": out.text == base,
            "structured_rows_unchanged": (bx == ax) if ext == ".xlsx" else (bc == ac),
            "md_attached": bool(d.get("normalized_markdown_attached")),
            "role": d.get("role"),
        }
    q = d.get("quality") or {}
    if int(q.get("arabic_chars") or 0) > 0 or "ar" in path.name.lower():
        arabic[path.name] = {"arabic_chars": q.get("arabic_chars"), "selected_engine": d.get("selected_engine"), "promoted": d.get("promoted"), "role": d.get("role")}
    rows.append({
        "name": path.name, "ext": ext, "role": d.get("role"), "selected_engine": d.get("selected_engine"),
        "promoted": d.get("promoted"), "fallback_reason": d.get("fallback_reason"),
        "material_disagreement": d.get("material_disagreement"), "method": out.method,
        "latency_ms": d.get("latency_ms"), "output_sha256": d.get("output_sha256"),
    })
    print(d.get("selected_engine"), ext, "promoted="+str(d.get("promoted")), path.name)

xlsx_ok = all(v["structured_rows_unchanged"] and v["text_unchanged"] for k,v in structured.items() if k.endswith(".xlsx"))
csv_ok = all(v["structured_rows_unchanged"] and v["text_unchanged"] for k,v in structured.items() if k.endswith(".csv"))
# live extract proof via app
import app
docx = next(corpus.glob("*.docx"))
r = app.extract_candidate_cv_document(str(docx), company_code="WATHEFNI")
dec = (r.metadata or {}).get("anydoc_office_authority") or {}
csvf = next(corpus.glob("*payroll*.csv"), None) or next(corpus.glob("*.csv"))
rc = app.extract_candidate_cv_document(str(csvf), mime_type="text/csv", company_code="WATHEFNI")
dc = (rc.metadata or {}).get("anydoc_office_authority") or {}
raw = csvf.read_text(encoding="utf-8", errors="ignore").strip()
assert dc.get("role") == auth.ROLE_MARKDOWN_ONLY, dc
assert dc.get("structured_authority_unchanged") is True, dc
assert rc.text == raw, (len(rc.text or ""), len(raw), rc.method, dc.get("selected_engine"))
# DictReader integrity on original file bytes
with csvf.open(encoding="utf-8", newline="") as f:
    dict_rows = list(__import__("csv").DictReader(f))
assert dict_rows and "emp_code" in dict_rows[0]
summary = {
    "mode": "staging", "host": "vps", "files": len(rows),
    "promoted_total": sum(1 for r in rows if r.get("promoted")),
    "fallback_total": sum(1 for r in rows if r.get("fallback_reason")),
    "material_disagreement_total": sum(1 for r in rows if r.get("material_disagreement")),
    "structured_xlsx_integrity": xlsx_ok, "structured_csv_integrity": csv_ok,
    "live_docx_engine": dec.get("selected_engine"), "live_docx_promoted": dec.get("promoted"),
    "live_csv_structured_unchanged": True, "pinned_version": auth.PINNED_VERSION,
}
(EVID/"results"/"staging_authority_results.json").write_text(
    json.dumps({"summary": summary, "rows": rows, "arabic_evidence": arabic, "structured_proof": structured}, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
print(json.dumps(summary, indent=2, ensure_ascii=False))
assert xlsx_ok and csv_ok
assert summary["promoted_total"] >= 1
print("STAGING_AUTHORITY_QUALIFY_OK")
PY
REMOTE
grep -q STAGING_AUTHORITY_QUALIFY_OK "$LOCAL_EVID/results/staging-qualify.out"
grep -q ANYDOC_OFFICE_AUTHORITY_SMOKE_OK "$LOCAL_EVID/results/staging-qualify.out"

rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/results/" "$LOCAL_EVID/results/" || true
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/flags/" "$LOCAL_EVID/flags/" || true

if [[ "$ENABLE_PROD" != "1" ]]; then
  echo "STAGING_ONLY $LOCAL_EVID"
  echo "$LOCAL_EVID" > /tmp/anydoc-authority-closure.evid
  exit 0
fi

log "production authority deploy (format-correct models)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/results/prod-deploy.out"
set -euo pipefail
STAMP='$STAMP'
EVID='$REMOTE_EVID'
PROD='$PROD'
PY=/opt/wathefni/orchestrator/.venv/bin/python
PIP=/opt/wathefni/orchestrator/.venv/bin/pip
BACKUP=/opt/wathefni/backups/production-pre-anydoc-office-authority-\$STAMP
mkdir -p "\$BACKUP/modules" "\$BACKUP/systemd" "\$EVID/backup/prod" "\$EVID/flags"
for f in anydoc_office_authority.py anydoc_office_shadow.py app.py requirements.txt; do
  [[ -f "\$PROD/\$f" ]] && cp -a "\$PROD/\$f" "\$BACKUP/modules/\$f" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d "\$BACKUP/systemd/" 2>/dev/null || true
echo "\$BACKUP" | tee "\$EVID/backup/prod/BACKUP_PATH.txt"
cp -a "\$EVID/sources/anydoc_office_authority.py" "\$PROD/"
cp -a "\$EVID/sources/anydoc_office_shadow.py" "\$PROD/"
cp -a "\$EVID/sources/app.py" "\$PROD/"
cp -a "\$EVID/sources/smoke-test-anydoc-office-authority-closure.py" "\$PROD/"
if ! grep -q 'firecrawl-anydoc==0.1.2' "\$PROD/requirements.txt" 2>/dev/null; then
  echo 'firecrawl-anydoc==0.1.2' >> "\$PROD/requirements.txt"
fi
\$PIP install 'firecrawl-anydoc==0.1.2'
DROP=/etc/systemd/system/wathefni-orchestrator.service.d
mkdir -p "\$DROP"
rm -f "\$DROP/anydoc-office-shadow.conf" "\$DROP/anydoc-office-authority.conf"
cat > "\$DROP/zzz-anydoc-office-authority.conf" <<'EOF'
[Service]
Environment=WATHEFNI_ANYDOC_OFFICE_AUTHORITY=production
Environment=WATHEFNI_ANYDOC_OFFICE_SHADOW=production_shadow
Environment=WATHEFNI_ANYDOC_OFFICE_SHADOW_TIMEOUT_MS=2000
EOF
cat > "\$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="\$(cd "\$(dirname "\$0")" && pwd)"
PROD=/opt/wathefni/orchestrator
for f in anydoc_office_authority.py anydoc_office_shadow.py app.py requirements.txt; do
  [[ -f "\$BACKUP_DIR/modules/\$f" ]] && cp -a "\$BACKUP_DIR/modules/\$f" "\$PROD/\$f" || true
done
[[ ! -f "\$BACKUP_DIR/modules/anydoc_office_authority.py" ]] && rm -f "\$PROD/anydoc_office_authority.py" || true
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/zzz-anydoc-office-authority.conf
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/anydoc-office-authority.conf
# Restore prior shadow observation drop-in if backed up
if [[ -f "\$BACKUP_DIR/systemd/wathefni-orchestrator.service.d/anydoc-office-shadow.conf" ]]; then
  cp -a "\$BACKUP_DIR/systemd/wathefni-orchestrator.service.d/anydoc-office-shadow.conf" \
    /etc/systemd/system/wathefni-orchestrator.service.d/anydoc-office-shadow.conf
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
echo ROLLBACK_ANYDOC_OFFICE_AUTHORITY_OK
RB
chmod +x "\$BACKUP/ROLLBACK.sh"
cp -a "\$BACKUP/ROLLBACK.sh" "\$EVID/backup/prod/ROLLBACK.sh"
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in \$(seq 1 90); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then echo prod_health_ok; break; fi
  sleep 1
done
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E 'WATHEFNI_ANYDOC_OFFICE_(AUTHORITY|SHADOW)=' | tee "\$EVID/flags/production_flags.txt"
export PYTHONPATH="\$PROD:\${PYTHONPATH:-}"
export WATHEFNI_ANYDOC_OFFICE_AUTHORITY=production
export WATHEFNI_ANYDOC_OFFICE_SHADOW=production_shadow
\$PY - <<'PY' | tee "\$EVID/results/prod_authority_proof.json"
import json, csv, tempfile
from pathlib import Path
import anydoc_office_authority as auth
import app
assert auth.authority_mode() == "production"
corpus = Path("$REMOTE_EVID") / "corpus"
docx = next(corpus.glob("cv_*.docx"))
csvf = next(p for p in corpus.glob("*.csv"))
xlsx = next(p for p in corpus.glob("*.xlsx"))
rd = app.extract_candidate_cv_document(str(docx), company_code="WATHEFNI")
dd = (rd.metadata or {}).get("anydoc_office_authority") or {}
rc = app.extract_candidate_cv_document(str(csvf), mime_type="text/csv", company_code="WATHEFNI")
dc = (rc.metadata or {}).get("anydoc_office_authority") or {}
raw = csvf.read_text(encoding="utf-8", errors="ignore").strip()
assert dc.get("role") == auth.ROLE_MARKDOWN_ONLY, dc
assert dc.get("structured_authority_unchanged") is True, dc
assert rc.text == raw, (len(rc.text or ""), len(raw), rc.method)
assert dc.get("influences_payroll") is False
with csvf.open(encoding="utf-8", newline="") as f:
    assert list(csv.DictReader(f))
from openpyxl import load_workbook
wb = load_workbook(xlsx, read_only=True, data_only=True)
rows = [tuple(r) for ws in wb.worksheets for r in ws.iter_rows(values_only=True)]
assert len(rows) >= 2
with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as t:
    t.write(b"%PDF-1.4\\n"); pdf = Path(t.name)
class R:
    text="x"; method="t"; metadata={}; blocks=[]; error=None; quality_ok=True; provenance=[]; content_sha256=None
rp = auth.apply_office_authority(R(), pdf, company_code="WATHEFNI")
pdf.unlink(missing_ok=True)
assert (rp.metadata or {}).get("anydoc_office_authority", {}).get("fallback_reason") == "denied_extension_or_mime"
out = {
  "mode": "production",
  "docx_selected_engine": dd.get("selected_engine"),
  "docx_promoted": dd.get("promoted"),
  "docx_method": rd.method,
  "csv_structured_unchanged": True,
  "csv_role": dc.get("role"),
  "xlsx_openpyxl_rows": len(rows),
  "pdf_denied": True,
  "pinned_version": auth.PINNED_VERSION,
  "rollback": "/opt/wathefni/backups/production-pre-anydoc-office-authority-$STAMP/ROLLBACK.sh",
}
print(json.dumps(out, indent=2))
print("PROD_AUTHORITY_PROOF_OK")
PY
echo PROD_AUTHORITY_DEPLOY_OK
REMOTE
grep -q PROD_AUTHORITY_DEPLOY_OK "$LOCAL_EVID/results/prod-deploy.out"
grep -q PROD_AUTHORITY_PROOF_OK "$LOCAL_EVID/results/prod-deploy.out"

rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/results/" "$LOCAL_EVID/results/"
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/flags/" "$LOCAL_EVID/flags/"
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/backup/" "$LOCAL_EVID/backup/" || true

echo "$LOCAL_EVID" > /tmp/anydoc-authority-closure.evid
echo "AUTHORITY_CLOSURE_COMPLETE $LOCAL_EVID"
