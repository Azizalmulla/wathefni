#!/bin/bash
# Deploy HR Intelligence automatic freshness hardening.
set -euo pipefail
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
BACKUP="/opt/wathefni/backups/wathefni-hr-intelligence-freshness-${STAMP}"
ORCH="/opt/wathefni/orchestrator"
SRC="${INTEL_SRC:-/tmp/wathefni-hr-intelligence-freshness-src}"
SERVICE="wathefni-orchestrator.service"

mkdir -p "${BACKUP}/files" "${BACKUP}/systemd" "${BACKUP}/sql"
cp -a "${ORCH}/app.py" "${BACKUP}/files/app.py"
for f in hr_intelligence_registry_c1.py hr_intelligence_surfaces_c6.py \
          hr_intelligence_surfaces_http.py hr_intelligence_projection.py \
          hr-intelligence-projection-worker.py; do
  if [[ -f "${ORCH}/${f}" ]]; then
    cp -a "${ORCH}/${f}" "${BACKUP}/files/${f}"
  else
    echo "MISSING_BEFORE ${f}" > "${BACKUP}/files/${f}.missing"
  fi
done
cp -a /etc/systemd/system/wathefni-hr-intelligence-projection.service "${BACKUP}/systemd/" 2>/dev/null || true
cp -a /etc/systemd/system/wathefni-hr-intelligence-projection.timer "${BACKUP}/systemd/" 2>/dev/null || true
systemctl is-active "${SERVICE}" > "${BACKUP}/service-active.before"
echo "${BACKUP}" > /tmp/wathefni-hr-intelligence-freshness.backup
echo "${STAMP}" > /tmp/wathefni-hr-intelligence-freshness.stamp

cat > "${BACKUP}/ROLLBACK.sh" << EOF
#!/bin/bash
set -euo pipefail
ORCH="${ORCH}"
BACKUP="${BACKUP}"
SERVICE="${SERVICE}"
systemctl disable --now wathefni-hr-intelligence-projection.timer || true
for f in hr_intelligence_registry_c1.py hr_intelligence_surfaces_c6.py hr_intelligence_surfaces_http.py; do
  cp -a "\${BACKUP}/files/\${f}" "\${ORCH}/\${f}"
done
if [[ -f "\${BACKUP}/files/hr_intelligence_projection.py.missing" ]]; then
  rm -f "\${ORCH}/hr_intelligence_projection.py" "\${ORCH}/hr-intelligence-projection-worker.py"
else
  [[ -f "\${BACKUP}/files/hr_intelligence_projection.py" ]] && cp -a "\${BACKUP}/files/hr_intelligence_projection.py" "\${ORCH}/hr_intelligence_projection.py"
fi
systemctl daemon-reload
systemctl restart \${SERVICE}
echo "Freshness hardening rolled back. Projection tables retained."
curl -fsS http://127.0.0.1:8010/health
EOF
chmod 700 "${BACKUP}/ROLLBACK.sh"

cp -a "${SRC}/hr_intelligence_projection.py" "${ORCH}/hr_intelligence_projection.py"
cp -a "${SRC}/hr-intelligence-projection-worker.py" "${ORCH}/hr-intelligence-projection-worker.py"
cp -a "${SRC}/hr_intelligence_registry_c1.py" "${ORCH}/hr_intelligence_registry_c1.py"
cp -a "${SRC}/hr_intelligence_surfaces_c6.py" "${ORCH}/hr_intelligence_surfaces_c6.py"
cp -a "${SRC}/hr_intelligence_surfaces_http.py" "${ORCH}/hr_intelligence_surfaces_http.py"
cp -a "${SRC}/ops/wathefni-hr-intelligence-projection.service" /etc/systemd/system/wathefni-hr-intelligence-projection.service
cp -a "${SRC}/ops/wathefni-hr-intelligence-projection.timer" /etc/systemd/system/wathefni-hr-intelligence-projection.timer

systemctl daemon-reload
systemctl restart "${SERVICE}"
sleep 3
curl -fsS http://127.0.0.1:8010/health
systemctl enable --now wathefni-hr-intelligence-projection.timer
systemctl start wathefni-hr-intelligence-projection.service || true
echo "BACKUP=${BACKUP}"
echo "STAMP=${STAMP}"
