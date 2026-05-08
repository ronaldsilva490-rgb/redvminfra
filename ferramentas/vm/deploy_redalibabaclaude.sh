#!/usr/bin/env bash
set -euo pipefail

mkdir -p /var/lib/redalibabaclaude

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/alibaba" ]]; then
  install -m 755 -o root -g root "$SCRIPT_DIR/alibaba" /usr/local/bin/alibaba
fi

if [[ ! -d /opt/redalibabaclaude/.venv ]]; then
  /usr/bin/python3 -m venv /opt/redalibabaclaude/.venv
fi

/opt/redalibabaclaude/.venv/bin/pip install --upgrade pip >/dev/null
/opt/redalibabaclaude/.venv/bin/pip install -r /opt/redalibabaclaude/requirements.txt >/dev/null

if [[ -f /etc/redalibabaclaude.env ]]; then
  # Preserve live keys on redeploy. Key rotation is done with /usr/local/bin/alibaba.
  # shellcheck disable=SC1091
  source /etc/redalibabaclaude.env
fi

: "${REDALIBABACLAUDE_SG_API_KEY:=}"
: "${REDALIBABACLAUDE_US_API_KEY:=}"

cat > /etc/redalibabaclaude.env <<EOF
REDALIBABACLAUDE_HOST=0.0.0.0
REDALIBABACLAUDE_PORT=5052
REDALIBABACLAUDE_SG_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
REDALIBABACLAUDE_US_BASE_URL=https://dashscope-us.aliyuncs.com/compatible-mode/v1
REDALIBABACLAUDE_SG_API_KEY=${REDALIBABACLAUDE_SG_API_KEY}
REDALIBABACLAUDE_US_API_KEY=${REDALIBABACLAUDE_US_API_KEY}
REDALIBABACLAUDE_REQUIRE_AUTH=1
REDALIBABACLAUDE_AUTH_TOKENS=red
REDALIBABACLAUDE_DEFAULT_MODEL=ALI-SG/qwen-coder-plus
REDALIBABACLAUDE_STREAM_CHUNK_SIZE=1
REDALIBABACLAUDE_CONNECT_TIMEOUT=20
REDALIBABACLAUDE_READ_TIMEOUT=360
REDALIBABACLAUDE_RATE_LIMIT_MIN_INTERVAL_SECONDS=1
REDALIBABACLAUDE_RATE_LIMIT_COOLDOWN_SECONDS=12
REDALIBABACLAUDE_RATE_LIMIT_COOLDOWN_STEP_SECONDS=4
REDALIBABACLAUDE_RATE_LIMIT_MAX_COOLDOWN_SECONDS=45
REDALIBABACLAUDE_MAX_429_RETRIES=6
REDALIBABACLAUDE_SERVER_ERROR_COOLDOWN_SECONDS=4
REDALIBABACLAUDE_MAX_5XX_RETRIES=4
REDALIBABACLAUDE_TLS_CERT=/etc/letsencrypt/live/redsystems.ddns.net/fullchain.pem
REDALIBABACLAUDE_TLS_KEY=/etc/letsencrypt/live/redsystems.ddns.net/privkey.pem
EOF

sed -i 's/\r$//' \
  /etc/systemd/system/redalibabaclaude.service \
  /etc/redalibabaclaude.env \
  /opt/redalibabaclaude/app.py \
  /opt/redalibabaclaude/requirements.txt \
  /opt/redalibabaclaude/README.md \
  /opt/redalibabaclaude/tests/test_app.py

/usr/bin/python3 -m py_compile /opt/redalibabaclaude/app.py /opt/redalibabaclaude/tests/test_app.py
(cd /opt/redalibabaclaude && ./.venv/bin/python -m unittest discover -s tests -v)

ufw allow 5052/tcp
systemctl daemon-reload
systemctl enable --now redalibabaclaude.service
systemctl restart redalibabaclaude.service
sleep 2
systemctl is-active redalibabaclaude.service
ss -tlnp | grep ':5052 '
