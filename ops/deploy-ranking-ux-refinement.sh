#!/usr/bin/env bash
# Deploy Ranking page UX refinement (dashboard only — no pool/predicate/score changes).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DASH_DIST="$REPO_ROOT/apps/wathefni-dashboard/dist"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_BACKUP="/opt/wathefni/backups/production-pre-ranking-ux-refinement-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/production-evidence/ranking-ux-refinement/$STAMP"
LOCAL_EVIDENCE="$REPO_ROOT/ops/evidence/ranking-ux-refinement-$STAMP"
PROD_DASH=/var/www/wathefni-dashboard
REMOTE_TMP="/tmp/ranking-ux-refinement-$STAMP"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

log "stamp=$STAMP"
mkdir -p "$LOCAL_EVIDENCE"
echo "$STAMP" > "$LOCAL_EVIDENCE/STAMP.txt"
echo "$REMOTE_BACKUP" > "$LOCAL_EVIDENCE/BACKUP_PATH.txt"

test -d "$DASH_DIST" || { echo "missing dist: $DASH_DIST (run npm run build first)"; exit 1; }

"${SSH[@]}" 'curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/health' | tee "$LOCAL_EVIDENCE/health_before.txt"

log "backup $REMOTE_BACKUP"
"${SSH[@]}" "STAMP='$STAMP' BACKUP='$REMOTE_BACKUP' DASH='$PROD_DASH' bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p "$BACKUP/dashboard-dist"
rsync -a "$DASH/" "$BACKUP/dashboard-dist/"
cat > "$BACKUP/ROLLBACK.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="\$(cd "\$(dirname "\$0")" && pwd)"
rsync -a --delete "\$ROOT/dashboard-dist/" /var/www/wathefni-dashboard/
systemctl reload caddy || true
curl -sS -o /dev/null -w "rollback_health=%{http_code}\\n" http://127.0.0.1:8010/health
echo "Rolled back ranking UX refinement ${STAMP}"
EOF
chmod 755 "$BACKUP/ROLLBACK.sh"
echo "$BACKUP"
REMOTE

log "upload dist"
"${SSH[@]}" "mkdir -p $REMOTE_TMP/dashboard-dist $REMOTE_EVIDENCE"
rsync -az -e "ssh -o BatchMode=yes" "$DASH_DIST/" "$VPS_HOST:$REMOTE_TMP/dashboard-dist/"

log "apply"
"${SSH[@]}" "STAMP='$STAMP' TMP='$REMOTE_TMP' DASH='$PROD_DASH' EVIDENCE='$REMOTE_EVIDENCE' bash -s" <<'REMOTE'
set -euo pipefail
rsync -a --delete "$TMP/dashboard-dist/" "$DASH/"
systemctl reload caddy || true
code=$(curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8010/health || true)
echo "$code" | tee "$EVIDENCE/health_after.txt"
test "$code" = "200"

python3 <<'PY'
import json, os, re
from pathlib import Path

dash = Path("/var/www/wathefni-dashboard")
index = (dash / "index.html").read_text()
assets = list((dash / "assets").glob("*.js"))
joined = "\n".join(p.read_text(errors="ignore") for p in assets)

def has(s: str) -> bool:
    return s in joined

ranking_chunks = [p.name for p in assets if "RankingPage" in p.name or "ranking" in p.name.lower()]
ranking_page = next((p.name for p in assets if p.name.startswith("RankingPage-")), None)
dashboard_chunk = next((p.name for p in assets if p.name.startswith("dashboard-")), None)
health = Path(os.environ["EVIDENCE"]).joinpath("health_after.txt").read_text().strip()

proof = {
    "ranking_page_chunk": ranking_page,
    "dashboard_chunk": dashboard_chunk,
    "has_in_review_order": has("In review order"),
    "has_job_matches": has("Job matches"),
    "has_meets_all_requirements": has("Meets all requirements"),
    "has_eligible_helper": "hard-criteria eligible" in joined or "Meets all requirements counts only" in joined,
    "has_ar_in_review": has("بترتيب المراجعة"),
    "has_ar_job_matches": has("مطابق للوظيفة"),
    "has_state_none_rankable": "none are ready for review order" in joined or "لا أحد جاهزاً لترتيب المراجعة" in joined,
    "has_excluded_note": "are not in review order" in joined or "ليست ضمن ترتيب المراجعة" in joined,
    "has_profiler_marks": all(
        m in joined
        for m in (
            "ranking_job_switch",
            "ranking_run",
            "ranking_expand_evidence",
            "ranking_open_candidate",
            "ranking:",
        )
    ),
    "has_back_to_ranking": has("Back to Ranking") and has("العودة إلى الترتيب"),
    "has_cv_evidence_label": has("CV evidence") and has("أدلة السيرة الذاتية"),
    "no_matching_rankable_jargon_badges": ("Matching {" not in joined),
    "health": health,
}
fails = [k for k, v in proof.items() if k.startswith("has_") and v is False]
fails += [k for k, v in proof.items() if k.startswith("no_") and v is False]
proof["verdict"] = "PASS" if not fails and health == "200" else "FAIL"
proof["fail_keys"] = fails
ev = Path(os.environ["EVIDENCE"])
ev.joinpath("live-proof.json").write_text(json.dumps(proof, indent=2) + "\n")
markers = {
    "chunks_sample": ranking_chunks[:20],
    "index_asset_refs": re.findall(r'assets/[^"\']+', index)[:30],
    **{k: proof[k] for k in proof if k.startswith("has_") or k.startswith("no_")},
}
ev.joinpath("asset-markers.json").write_text(json.dumps(markers, indent=2) + "\n")
print(json.dumps({"verdict": proof["verdict"], "fail_keys": fails, "ranking_page_chunk": ranking_page}, indent=2))
if proof["verdict"] != "PASS":
    raise SystemExit(2)
PY
REMOTE

"${SCP[@]}" "$VPS_HOST:$REMOTE_EVIDENCE/live-proof.json" "$LOCAL_EVIDENCE/live-proof.json"
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVIDENCE/asset-markers.json" "$LOCAL_EVIDENCE/asset-markers.json"
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVIDENCE/health_after.txt" "$LOCAL_EVIDENCE/health_after.txt"

log "done stamp=$STAMP backup=$REMOTE_BACKUP"
cat "$LOCAL_EVIDENCE/live-proof.json"
