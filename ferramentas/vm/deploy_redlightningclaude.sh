#!/usr/bin/env bash
set -euo pipefail

mkdir -p /var/lib/redlightningclaude

if [[ ! -d /opt/redlightningclaude/.venv ]]; then
  /usr/bin/python3 -m venv /opt/redlightningclaude/.venv
fi

/opt/redlightningclaude/.venv/bin/pip install --upgrade pip >/dev/null
/opt/redlightningclaude/.venv/bin/pip install -r /opt/redlightningclaude/requirements.txt >/dev/null

cat > /etc/redlightningclaude.env <<EOF
REDLIGHTNINGCLAUDE_HOST=0.0.0.0
REDLIGHTNINGCLAUDE_PORT=5051
REDLIGHTNINGCLAUDE_BASE_URL=https://lightning.ai/api/v1
REDLIGHTNINGCLAUDE_API_KEY=b477d719-3bb9-4246-a3d6-d591cd3b4165
LIGHTNING_API_KEY=b477d719-3bb9-4246-a3d6-d591cd3b4165
REDLIGHTNINGCLAUDE_API_KEYS=b477d719-3bb9-4246-a3d6-d591cd3b4165,f6e90257-ee95-4729-b744-0e69a5e134d7,ac2f55ae-16c0-4535-bd2c-9617e62196ae,914809e1-1412-4a1b-82e1-52613ecbc3e2
REDLIGHTNINGCLAUDE_REQUIRE_AUTH=1
REDLIGHTNINGCLAUDE_AUTH_TOKENS=red
REDLIGHTNINGCLAUDE_DEFAULT_MODEL=anthropic/claude-sonnet-4-6
REDLIGHTNINGCLAUDE_STREAM_CHUNK_SIZE=1
REDLIGHTNINGCLAUDE_CONNECT_TIMEOUT=20
REDLIGHTNINGCLAUDE_READ_TIMEOUT=360
REDLIGHTNINGCLAUDE_RATE_LIMIT_MIN_INTERVAL_SECONDS=1
REDLIGHTNINGCLAUDE_RATE_LIMIT_COOLDOWN_SECONDS=12
REDLIGHTNINGCLAUDE_RATE_LIMIT_COOLDOWN_STEP_SECONDS=4
REDLIGHTNINGCLAUDE_RATE_LIMIT_MAX_COOLDOWN_SECONDS=45
REDLIGHTNINGCLAUDE_MAX_429_RETRIES=6
REDLIGHTNINGCLAUDE_TLS_CERT=/etc/letsencrypt/live/redsystems.ddns.net/fullchain.pem
REDLIGHTNINGCLAUDE_TLS_KEY=/etc/letsencrypt/live/redsystems.ddns.net/privkey.pem
EOF

sed -i 's/\r$//' \
  /etc/systemd/system/redlightningclaude.service \
  /etc/redlightningclaude.env \
  /opt/redlightningclaude/app.py \
  /opt/redlightningclaude/requirements.txt \
  /opt/redlightningclaude/README.md \
  /opt/redlightningclaude/tests/test_app.py

/usr/bin/python3 -m py_compile /opt/redlightningclaude/app.py /opt/redlightningclaude/tests/test_app.py
(cd /opt/redlightningclaude && ./.venv/bin/python -m unittest discover -s tests -v)

ufw allow 5051/tcp
systemctl daemon-reload
systemctl enable --now redlightningclaude.service
systemctl restart redlightningclaude.service
sleep 2
systemctl is-active redlightningclaude.service
ss -tlnp | grep ':5051 '
