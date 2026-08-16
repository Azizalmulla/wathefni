#!/usr/bin/env bash
# Enable Mistral OCR 4 on production (owner-approved). No CV backfill.
set -euo pipefail

VENV=/opt/wathefni/orchestrator/.venv/bin
PROD=/opt/wathefni/orchestrator
STAGING=/opt/wathefni/staging/orchestrator
DROPIN_DIR=/etc/systemd/system/wathefni-orchestrator.service.d
DROPIN="$DROPIN_DIR/cv-mistral-ocr.conf"

echo "=== install pinned mistralai ==="
"$VENV/pip" install --disable-pip-version-check "mistralai==2.6.0" >/tmp/mistral-prod-pip.log 2>&1
"$VENV/python" -c "import mistralai; print('mistralai', getattr(mistralai, '__version__', 'installed'))"

echo "=== compile + smoke ==="
"$VENV/python" -m py_compile "$PROD/app.py" "$PROD/cv_extraction.py"
( cd "$PROD" && "$VENV/python" smoke-test-cv-extraction-ocr.py )

echo "=== prod schema migrate (no assert; matches deploy.sh production) ==="
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
( cd "$PROD" && "$VENV/python" -c 'import app; app.ensure_schema(force=True); print("prod schema ok")' )

echo "=== wire production drop-in OCR flags ==="
mkdir -p "$DROPIN_DIR"
cat > "$DROPIN" <<'EOF'
[Service]
EnvironmentFile=-/root/.openclaw/secrets/mistral.env
Environment=WATHEFNI_MISTRAL_ENV=/root/.openclaw/secrets/mistral.env
Environment=WATHEFNI_CV_MISTRAL_OCR=true
Environment=WATHEFNI_CV_GPT_VISION_RESCUE=off
EOF
chmod 644 "$DROPIN"

# Remove any duplicate lines we may have inserted into the main unit earlier
if grep -q 'mistral.env\|CV_MISTRAL_OCR\|CV_GPT_VISION_RESCUE\|WATHEFNI_MISTRAL_ENV' /etc/systemd/system/wathefni-orchestrator.service; then
  tmp=$(mktemp)
  grep -vE 'mistral\.env|CV_MISTRAL_OCR|CV_GPT_VISION_RESCUE|WATHEFNI_MISTRAL_ENV' /etc/systemd/system/wathefni-orchestrator.service > "$tmp"
  mv "$tmp" /etc/systemd/system/wathefni-orchestrator.service
fi

if [ -f "$STAGING/ops/wathefni-orchestrator-staging.service" ]; then
  install -m 0644 "$STAGING/ops/wathefni-orchestrator-staging.service" /etc/systemd/system/wathefni-orchestrator-staging.service
fi

systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
systemctl restart wathefni-orchestrator-staging.service
sleep 4
systemctl is-active wathefni-orchestrator.service
systemctl is-active wathefni-orchestrator-staging.service

echo "=== prod OCR env (process) ==="
PID=$(systemctl show -p MainPID --value wathefni-orchestrator.service)
tr '\0' '\n' < "/proc/$PID/environ" | grep -E 'CV_MISTRAL|CV_GPT|MISTRAL_ENV|MISTRAL_API_KEY' | sed -E 's/(API_KEY)=.*/\1=***/'

echo "=== cv_extraction tables ==="
sudo -u postgres psql -d wathefni -c '\dt cv_extraction*'

echo "=== runtime confirmation ==="
export WATHEFNI_CV_MISTRAL_OCR=true
export WATHEFNI_CV_GPT_VISION_RESCUE=off
export WATHEFNI_MISTRAL_ENV=/root/.openclaw/secrets/mistral.env
set -a
# shellcheck disable=SC1091
. /root/.openclaw/secrets/mistral.env
set +a
( cd "$PROD" && "$VENV/python" -c 'import cv_extraction as cv; print("model", cv.MISTRAL_OCR_MODEL); print("enabled", cv.mistral_ocr_enabled()); print("key", bool(cv.mistral_api_key())); print("rescue", cv.gpt_vision_rescue_enabled()); print("retired", cv.cv_gpt_rescue_retired())' )

echo "=== health ==="
curl -sS -o /dev/null -w 'prod_local_http=%{http_code}\n' http://127.0.0.1:8010/dashboard/auth/me || true

echo "=== NO BACKFILL: CV worker not force-run ==="
echo "PROD_OCR_ENABLE_OK"
