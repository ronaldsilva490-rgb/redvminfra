#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f /etc/red-ollama-proxy.env ]]; then
  echo "missing /etc/red-ollama-proxy.env" >&2
  exit 1
fi

mkdir -p /var/lib/rednimclaude

if [[ ! -d /opt/rednimclaude/.venv ]]; then
  /usr/bin/python3 -m venv /opt/rednimclaude/.venv
fi

/opt/rednimclaude/.venv/bin/pip install --upgrade pip >/dev/null
/opt/rednimclaude/.venv/bin/pip install -r /opt/rednimclaude/requirements.txt >/dev/null

NIM_KEY="$(
  grep -E '^(RED_PROXY_NVIDIA_API_KEY|NVIDIA_API_KEY)=' /etc/red-ollama-proxy.env \
    | tail -n 1 \
    | cut -d= -f2-
)"

cat > /etc/rednimclaude.env <<EOF
REDNIMCLAUDE_HOST=0.0.0.0
REDNIMCLAUDE_PORT=5050
REDNIMCLAUDE_NIM_BASE_URL=https://integrate.api.nvidia.com/v1
REDNIMCLAUDE_NVIDIA_API_KEY=$NIM_KEY
NVIDIA_API_KEY=$NIM_KEY
REDNIMCLAUDE_REQUIRE_AUTH=1
REDNIMCLAUDE_AUTH_TOKENS=red
REDNIMCLAUDE_DEFAULT_MODEL=nim-qwen-next-80b
REDNIMCLAUDE_STREAM_CHUNK_SIZE=1
REDNIMCLAUDE_CONNECT_TIMEOUT=20
REDNIMCLAUDE_READ_TIMEOUT=360
REDNIMCLAUDE_TLS_CERT=/etc/letsencrypt/live/redsystems.ddns.net/fullchain.pem
REDNIMCLAUDE_TLS_KEY=/etc/letsencrypt/live/redsystems.ddns.net/privkey.pem
EOF

sed -i 's/\r$//' \
  /etc/systemd/system/rednimclaude.service \
  /etc/rednimclaude.env \
  /opt/rednimclaude/app.py \
  /opt/rednimclaude/requirements.txt \
  /opt/rednimclaude/README.md \
  /opt/rednimclaude/tests/test_app.py

/usr/bin/python3 -m py_compile /opt/rednimclaude/app.py /opt/rednimclaude/tests/test_app.py
(cd /opt/rednimclaude && ./.venv/bin/python -m unittest discover -s tests -v)

ufw allow 5050/tcp
systemctl daemon-reload
systemctl enable --now rednimclaude.service
systemctl restart rednimclaude.service
sleep 2
systemctl is-active rednimclaude.service
ss -tlnp | grep ':5050 '
