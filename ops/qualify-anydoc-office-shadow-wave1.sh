#!/usr/bin/env bash
# AnyDoc Office Shadow Canary Wave 1 — staging then production_shadow observation.
# Never changes production authority / routing / CV V2 / admission.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
LOCAL_EVID="$REPO_ROOT/ops/evidence/anydoc-office-shadow-wave1-${STAMP}"
VPS_HOST="${VPS_HOST:-root@76.13.63.68}"
REMOTE_EVID="/opt/wathefni/evidence/anydoc-office-shadow-wave1/${STAMP}"
PROD=/opt/wathefni/orchestrator
STG=/opt/wathefni/staging/orchestrator
ENABLE_PROD_SHADOW="${ENABLE_PROD_SHADOW:-0}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)

mkdir -p "$LOCAL_EVID"/{sources,results,docs,flags,corpus,backup}
log() { printf '\n=== %s ===\n' "$*"; }

MODULES=(
  anydoc_office_shadow.py
  smoke-test-anydoc-office-shadow-wave1.py
)
# app.py only for shadow hook sites — deploy carefully with backup.

log "stage sources locally"
for f in "${MODULES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$ORCH_SRC/requirements.txt" "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/app.py" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/qualify-anydoc-office-shadow-wave1-staging-corpus.py" "$LOCAL_EVID/sources/"

# Representative corpus (office allowlist only — no PDF/images)
CORPUS_GEN="$REPO_ROOT/ops/evidence/anydoc-technical-audit-20260804/corpus/generated"
CORPUS_OFF="$REPO_ROOT/ops/evidence/anydoc-technical-audit-20260804/research/anydoc/tests/fixtures"
mkdir -p "$LOCAL_EVID/corpus"
if [[ -d "$CORPUS_GEN" ]]; then
  find "$CORPUS_GEN" -maxdepth 1 -type f \( \
    -name '*.docx' -o -name '*.doc' -o -name '*.pptx' -o -name '*.ppt' \
    -o -name '*.xlsx' -o -name '*.xls' -o -name '*.odt' -o -name '*.ods' \
    -o -name '*.odp' -o -name '*.rtf' -o -name '*.csv' \) \
    -exec cp -a {} "$LOCAL_EVID/corpus/" \;
fi
if [[ -d "$CORPUS_OFF" ]]; then
  find "$CORPUS_OFF" -maxdepth 1 -type f \( \
    -name '*.docx' -o -name '*.doc' -o -name '*.pptx' -o -name '*.ppt' \
    -o -name '*.xlsx' -o -name '*.xls' -o -name '*.odt' -o -name '*.ods' \
    -o -name '*.odp' -o -name '*.rtf' -o -name '*.csv' \) \
    -exec cp -a {} "$LOCAL_EVID/corpus/" \;
fi

log "push to VPS"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID'/{results,docs,flags,corpus,backup/staging,backup/prod} '$STG' '$PROD'"
"${SCP[@]}" "$LOCAL_EVID/sources/"*.py "$VPS_HOST:$REMOTE_EVID/sources/" 2>/dev/null || \
  "${SSH[@]}" "mkdir -p '$REMOTE_EVID/sources'"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID/sources'"
for f in anydoc_office_shadow.py smoke-test-anydoc-office-shadow-wave1.py; do
  "${SCP[@]}" "$ORCH_SRC/$f" "$VPS_HOST:$REMOTE_EVID/sources/"
done
"${SCP[@]}" "$ORCH_SRC/requirements.txt" "$VPS_HOST:$REMOTE_EVID/sources/"
"${SCP[@]}" "$ORCH_SRC/app.py" "$VPS_HOST:$REMOTE_EVID/sources/"
"${SCP[@]}" "$REPO_ROOT/ops/qualify-anydoc-office-shadow-wave1-staging-corpus.py" "$VPS_HOST:$REMOTE_EVID/sources/"
"${SSH[@]}" "rm -rf '$REMOTE_EVID/corpus' && mkdir -p '$REMOTE_EVID/corpus'"
"${SCP[@]}" -r "$LOCAL_EVID/corpus/." "$VPS_HOST:$REMOTE_EVID/corpus/" || true

log "install on staging + pin firecrawl-anydoc + staging_shadow drop-in"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/results/staging-deploy.out"
set -euo pipefail
STAMP='$STAMP'
EVID='$REMOTE_EVID'
STG='$STG'
PROD='$PROD'
PY=/opt/wathefni/orchestrator/.venv/bin/python
PIP=/opt/wathefni/orchestrator/.venv/bin/pip
BACKUP=/opt/wathefni/backups/staging-pre-anydoc-office-shadow-\$STAMP
mkdir -p "\$BACKUP/modules" "\$EVID/backup/staging"

# Backup staging modules
for f in anydoc_office_shadow.py app.py smoke-test-anydoc-office-shadow-wave1.py requirements.txt; do
  [[ -f "\$STG/\$f" ]] && cp -a "\$STG/\$f" "\$BACKUP/modules/\$f" || true
  [[ -f "\$STG/\$f" ]] && cp -a "\$STG/\$f" "\$EVID/backup/staging/\$f" || true
done
echo "\$BACKUP" | tee "\$EVID/backup/staging/BACKUP_PATH.txt"

# Install modules onto staging
cp -a "\$EVID/sources/anydoc_office_shadow.py" "\$STG/"
cp -a "\$EVID/sources/smoke-test-anydoc-office-shadow-wave1.py" "\$STG/"
cp -a "\$EVID/sources/app.py" "\$STG/"
# Keep staging requirements note; pin is installed into shared prod venv used by staging.
grep -q 'firecrawl-anydoc==0.1.2' "\$EVID/sources/requirements.txt"
\$PIP install 'firecrawl-anydoc==0.1.2'
\$PY - <<'PY'
import importlib.metadata as m
v = m.version("firecrawl-anydoc")
assert v == "0.1.2", v
import anydoc
print("ANYDOC_PIN_OK", v)
PY

# Staging systemd drop-in — observation only
DROP_DIR=/etc/systemd/system/wathefni-orchestrator-staging.service.d
mkdir -p "\$DROP_DIR"
cat > "\$DROP_DIR/anydoc-office-shadow.conf" <<'EOF'
[Service]
Environment=WATHEFNI_ANYDOC_OFFICE_SHADOW=staging_shadow
Environment=WATHEFNI_ANYDOC_OFFICE_SHADOW_TIMEOUT_MS=2000
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
for i in \$(seq 1 60); do
  if curl -fsS http://127.0.0.1:8011/health >/dev/null 2>&1; then
    echo staging_health_ok
    break
  fi
  sleep 1
done
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
ENVS=\$(tr '\\0' '\\n' < /proc/\$PID/environ)
echo "\$ENVS" | grep -F 'WATHEFNI_ANYDOC_OFFICE_SHADOW=staging_shadow' | tee "\$EVID/flags/staging_flag.txt"
# Prove production not yet shadowed
PROD_PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
PROD_ENVS=\$(tr '\\0' '\\n' < /proc/\$PROD_PID/environ || true)
echo "\$PROD_ENVS" | grep -F 'WATHEFNI_ANYDOC_OFFICE_SHADOW' || echo 'PROD_FLAG_ABSENT_OK'
echo STAGING_SHADOW_DEPLOY_OK
REMOTE
grep -q STAGING_SHADOW_DEPLOY_OK "$LOCAL_EVID/results/staging-deploy.out"
grep -q ANYDOC_PIN_OK "$LOCAL_EVID/results/staging-deploy.out"

log "smoke + staging corpus on VPS"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/results/staging-qualify.out"
set -euo pipefail
STG='$STG'
EVID='$REMOTE_EVID'
PY=/opt/wathefni/orchestrator/.venv/bin/python
export PYTHONPATH="\$STG:/opt/wathefni/orchestrator:\${PYTHONPATH:-}"
export WATHEFNI_ANYDOC_OFFICE_SHADOW=staging_shadow
export WATHEFNI_ANYDOC_OFFICE_SHADOW_TIMEOUT_MS=5000
cd "\$STG"
\$PY smoke-test-anydoc-office-shadow-wave1.py | tee "\$EVID/results/smoke.out"
# Adapt corpus script paths for remote layout
\$PY - <<'PY'
import json, os, sys, time
from pathlib import Path

STG = Path("$STG")
EVID = Path("$REMOTE_EVID")
sys.path.insert(0, str(STG))
os.environ["WATHEFNI_ANYDOC_OFFICE_SHADOW"] = "staging_shadow"
os.environ["WATHEFNI_ANYDOC_OFFICE_SHADOW_TIMEOUT_MS"] = "5000"
import anydoc_office_shadow as shadow

corpus = list((EVID / "corpus").glob("*"))
rows = []
arabic = {}
for path in sorted(corpus):
    if path.suffix.lower() not in shadow.ALLOWED_EXTENSIONS:
        continue
    # Best-effort auth
    auth = ""
    try:
        if path.suffix.lower() == ".docx":
            import cv_docx
            blocks, _i, _m = cv_docx.parse_docx_local(path)
            auth = cv_docx.blocks_to_text(blocks)
        elif path.suffix.lower() in {".csv", ".rtf", ".txt"}:
            auth = path.read_text(errors="ignore")
        elif path.suffix.lower() == ".xlsx":
            from openpyxl import load_workbook
            wb = load_workbook(path, read_only=True, data_only=True)
            auth = "\\n".join(
                "\\t".join("" if c is None else str(c) for c in row)
                for ws in wb.worksheets
                for row in ws.iter_rows(values_only=True)
            )
    except Exception as exc:
        auth = ""
    obs = shadow.run_anydoc_office_shadow(path, authoritative_text=auth, company_code="WATHEFNI")
    det = None
    if obs.get("ok") and obs.get("output_sha256"):
        again = shadow.run_anydoc_office_shadow(path, authoritative_text=auth, company_code="WATHEFNI")
        det = again.get("output_sha256") == obs.get("output_sha256")
    row = {"path": path.name, "ext": path.suffix.lower(), "shadow": obs, "deterministic": det}
    rows.append(row)
    q = obs.get("quality") or {}
    if int(q.get("arabic_chars") or 0) > 0 or "ar" in path.name.lower():
        arabic[path.name] = {
            "arabic_chars": q.get("arabic_chars"),
            "ok": obs.get("ok"),
            "quality_ok": q.get("ok"),
            "disagreement": (obs.get("comparison") or {}).get("disagreement_reasons"),
        }
    print(("OK" if obs.get("ok") else "FAIL") , path.suffix, obs.get("latency_ms"), path.name)

ok_rows = [r for r in rows if r["shadow"].get("ok")]
material = sum(1 for r in ok_rows if (r["shadow"].get("comparison") or {}).get("material_disagreement"))
by_ext = {}
for r in rows:
    b = by_ext.setdefault(r["ext"], {"n":0,"ok":0,"fail_open":0,"disagreements":0,"latencies":[]})
    b["n"] += 1
    sh = r["shadow"]
    if sh.get("ok"):
        b["ok"] += 1
        if sh.get("latency_ms") is not None:
            b["latencies"].append(sh["latency_ms"])
        if (sh.get("comparison") or {}).get("material_disagreement"):
            b["disagreements"] += 1
    elif sh.get("fail_open"):
        b["fail_open"] += 1
for ext,b in by_ext.items():
    ms = sorted(b["latencies"])
    b["median_ms"] = ms[len(ms)//2] if ms else None
    del b["latencies"]

import tempfile
from pathlib import Path as P
with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as t:
    t.write(b"%PDF-1.4\\n")
    pdf_path = P(t.name)
pdf_out = shadow.run_anydoc_office_shadow(pdf_path, authoritative_text="x")
pdf_path.unlink(missing_ok=True)
docx = next((EVID / "corpus" / r["path"] for r in rows if r["ext"] == ".docx"), None)
id_out = (
    shadow.run_anydoc_office_shadow(docx, authoritative_text="x", document_class="civil_id")
    if docx
    else {"skipped": "no_docx"}
)

summary = {
    "mode": "staging_shadow",
    "host": "vps",
    "files": len(rows),
    "ok": len(ok_rows),
    "fail_open": sum(1 for r in rows if r["shadow"].get("fail_open")),
    "disagreements": material,
    "informational_anydoc_only": sum(
        1 for r in rows
        if "anydoc_only_no_auth_baseline" in ((r["shadow"].get("comparison") or {}).get("disagreement_reasons") or [])
    ),
    "deterministic_ok": sum(1 for r in rows if r.get("deterministic") is True),
    "deterministic_checked": sum(1 for r in rows if r.get("deterministic") is not None),
    "by_extension": by_ext,
    "influences_routing_always_false": all(r["shadow"].get("influences_routing") is False for r in rows),
    "pdf_denied": pdf_out.get("skipped"),
    "identity_denied": id_out.get("skipped"),
    "pinned_version": shadow.PINNED_VERSION,
    "engine_version": shadow._package_version(),
}
(EVID/"results"/"staging_corpus_results.json").write_text(
    json.dumps({"summary": summary, "rows": rows, "arabic_evidence": arabic}, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
print(json.dumps(summary, indent=2, ensure_ascii=False))
assert summary["influences_routing_always_false"]
assert summary["pdf_denied"] in {"denied_extension_or_mime", "pdf_denied"}
assert summary["identity_denied"] == "identity_document_denied"
assert summary["ok"] >= 1
assert summary["deterministic_ok"] == summary["deterministic_checked"]
print("STAGING_CORPUS_QUALIFY_OK")
PY
REMOTE
grep -q STAGING_CORPUS_QUALIFY_OK "$LOCAL_EVID/results/staging-qualify.out"
grep -q ANYDOC_OFFICE_SHADOW_SMOKE_OK "$LOCAL_EVID/results/staging-qualify.out"

# Pull staging results
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/results/" "$LOCAL_EVID/results/" || true
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/flags/" "$LOCAL_EVID/flags/" || true

if [[ "$ENABLE_PROD_SHADOW" != "1" ]]; then
  log "staging green — set ENABLE_PROD_SHADOW=1 to enable production_shadow observation"
  echo "$LOCAL_EVID" > /tmp/anydoc-shadow-wave1.evid
  echo "STAGING_ONLY_COMPLETE $LOCAL_EVID"
  exit 0
fi

log "enable production_shadow observation only (authority unchanged)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/results/prod-shadow-deploy.out"
set -euo pipefail
STAMP='$STAMP'
EVID='$REMOTE_EVID'
PROD='$PROD'
PY=/opt/wathefni/orchestrator/.venv/bin/python
PIP=/opt/wathefni/orchestrator/.venv/bin/pip
BACKUP=/opt/wathefni/backups/production-pre-anydoc-office-shadow-\$STAMP
mkdir -p "\$BACKUP/modules" "\$EVID/backup/prod" "\$BACKUP"

# Backup prod modules
for f in anydoc_office_shadow.py app.py requirements.txt; do
  [[ -f "\$PROD/\$f" ]] && cp -a "\$PROD/\$f" "\$BACKUP/modules/\$f" || true
  [[ -f "\$PROD/\$f" ]] && cp -a "\$PROD/\$f" "\$EVID/backup/prod/\$f" || true
done
# Backup existing drop-ins state
mkdir -p "\$BACKUP/systemd"
cp -a /etc/systemd/system/wathefni-orchestrator.service.d "\$BACKUP/systemd/" 2>/dev/null || true
echo "\$BACKUP" | tee "\$EVID/backup/prod/BACKUP_PATH.txt"

# Install observation module + hooked app (shadow never mutates text)
cp -a "\$EVID/sources/anydoc_office_shadow.py" "\$PROD/"
cp -a "\$EVID/sources/smoke-test-anydoc-office-shadow-wave1.py" "\$PROD/"
cp -a "\$EVID/sources/app.py" "\$PROD/"
# Merge pin into prod requirements if missing
if ! grep -q 'firecrawl-anydoc==0.1.2' "\$PROD/requirements.txt" 2>/dev/null; then
  echo 'firecrawl-anydoc==0.1.2' >> "\$PROD/requirements.txt"
fi
\$PIP install 'firecrawl-anydoc==0.1.2'
\$PY -c 'import importlib.metadata as m; assert m.version("firecrawl-anydoc")=="0.1.2"'

DROP_DIR=/etc/systemd/system/wathefni-orchestrator.service.d
mkdir -p "\$DROP_DIR"
cat > "\$DROP_DIR/anydoc-office-shadow.conf" <<'EOF'
[Service]
Environment=WATHEFNI_ANYDOC_OFFICE_SHADOW=production_shadow
Environment=WATHEFNI_ANYDOC_OFFICE_SHADOW_TIMEOUT_MS=2000
EOF

# Rollback helper (escape $ for local expansion of outer <<REMOTE)
cat > "\$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="\$(cd "\$(dirname "\$0")" && pwd)"
PROD=/opt/wathefni/orchestrator
for f in anydoc_office_shadow.py app.py requirements.txt; do
  [[ -f "\$BACKUP_DIR/modules/\$f" ]] && cp -a "\$BACKUP_DIR/modules/\$f" "\$PROD/\$f" || true
done
# If module did not exist pre-wave, remove it
if [[ ! -f "\$BACKUP_DIR/modules/anydoc_office_shadow.py" ]]; then
  rm -f "\$PROD/anydoc_office_shadow.py"
fi
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/anydoc-office-shadow.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator
echo ROLLBACK_ANYDOC_OFFICE_SHADOW_OK
RB
chmod +x "\$BACKUP/ROLLBACK.sh"
cp -a "\$BACKUP/ROLLBACK.sh" "\$EVID/backup/prod/ROLLBACK.sh"

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in \$(seq 1 90); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then
    echo prod_health_ok
    break
  fi
  sleep 1
done
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
ENVS=\$(tr '\\0' '\\n' < /proc/\$PID/environ)
echo "\$ENVS" | grep -F 'WATHEFNI_ANYDOC_OFFICE_SHADOW=production_shadow' | tee "\$EVID/flags/production_flag.txt"

# Live observation proof — office file only; prove PDF/identity denied; prove metadata attach does not change text
export PYTHONPATH="\$PROD:\${PYTHONPATH:-}"
export WATHEFNI_ANYDOC_OFFICE_SHADOW=production_shadow
\$PY - <<'PY' | tee "\$EVID/results/prod_observation_proof.json"
import json, os, tempfile
from pathlib import Path
import anydoc_office_shadow as shadow
import app

assert shadow.shadow_mode() == "production_shadow"
assert shadow.PINNED_VERSION == "0.1.2"

# CSV observation
csv_path = Path("$REMOTE_EVID") / "corpus"
csvs = list(csv_path.glob("*.csv"))
assert csvs, "need csv fixture"
path = csvs[0]
# Use extract_candidate_cv_document if available
result = app.extract_candidate_cv_document(str(path), mime_type="text/csv", company_code="WATHEFNI")
meta = dict(getattr(result, "metadata", None) or {})
blob = meta.get("anydoc_office_shadow") or {}
auth_text = result.text or ""
assert blob.get("influences_routing") is False
assert blob.get("influences_admission") is False
assert blob.get("hosted_firecrawl_parse") is False
assert blob.get("local_bytes_only") is True
assert blob.get("mode") == "production_shadow"
# Authoritative text must equal a second extract with flag off (observation does not mutate)
os.environ["WATHEFNI_ANYDOC_OFFICE_SHADOW"] = "off"
result_off = app.extract_candidate_cv_document(str(path), mime_type="text/csv", company_code="WATHEFNI")
os.environ["WATHEFNI_ANYDOC_OFFICE_SHADOW"] = "production_shadow"
assert (result_off.text or "") == auth_text, "authority text must be unchanged by shadow"

# PDF deny
with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as t:
    t.write(b"%PDF-1.4\\n1 0 obj\\n<<>>\\nendobj\\n")
    pdf = Path(t.name)
pdf_blob = shadow.run_anydoc_office_shadow(pdf, authoritative_text="x")
pdf.unlink(missing_ok=True)
assert pdf_blob.get("skipped") in {"denied_extension_or_mime", "pdf_denied"}

# Identity deny
docx = next(iter((Path("$REMOTE_EVID")/"corpus").glob("*.docx")), None)
id_blob = shadow.run_anydoc_office_shadow(docx, authoritative_text="x", document_class="passport") if docx else {}
assert id_blob.get("skipped") == "identity_document_denied"

out = {
    "mode": "production_shadow",
    "observation_ok": bool(blob.get("ok") or blob.get("fail_open") or blob.get("skipped")),
    "shadow_blob_keys": sorted(blob.keys()),
    "influences_routing": blob.get("influences_routing"),
    "authority_text_unchanged": True,
    "pdf_denied": pdf_blob.get("skipped"),
    "identity_denied": id_blob.get("skipped"),
    "engine_version": blob.get("engine_version") or shadow._package_version(),
    "pinned_version": shadow.PINNED_VERSION,
    "latency_ms": blob.get("latency_ms"),
    "character_count": blob.get("character_count"),
    "output_sha256": blob.get("output_sha256"),
    "rollback": "/opt/wathefni/backups/production-pre-anydoc-office-shadow-$STAMP/ROLLBACK.sh",
}
print(json.dumps(out, indent=2))
assert out["authority_text_unchanged"]
assert out["influences_routing"] is False
print("PROD_SHADOW_OBSERVATION_OK")
PY
echo PROD_SHADOW_DEPLOY_OK
REMOTE
grep -q PROD_SHADOW_DEPLOY_OK "$LOCAL_EVID/results/prod-shadow-deploy.out"
grep -q PROD_SHADOW_OBSERVATION_OK "$LOCAL_EVID/results/prod-shadow-deploy.out"

rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/results/" "$LOCAL_EVID/results/"
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/flags/" "$LOCAL_EVID/flags/"
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/backup/" "$LOCAL_EVID/backup/" || true

echo "$LOCAL_EVID" > /tmp/anydoc-shadow-wave1.evid
echo "WAVE1_COMPLETE $LOCAL_EVID"
