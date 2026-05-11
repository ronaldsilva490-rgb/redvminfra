#!/usr/bin/env bash
set -euo pipefail

if [[ ! -d /opt/inferproxy/.venv ]]; then
  /usr/bin/python3 -m venv /opt/inferproxy/.venv
fi

/opt/inferproxy/.venv/bin/pip install --upgrade pip >/dev/null
/opt/inferproxy/.venv/bin/pip install -r /opt/inferproxy/requirements.txt >/dev/null

if [[ -f /etc/inferproxy.env ]]; then
  LIVE_INFERALL_API_KEY="$(grep -E '^INFERALL_API_KEY=' /etc/inferproxy.env | tail -n 1 | cut -d= -f2- || true)"
fi

: "${INFERALL_API_KEY:=${LIVE_INFERALL_API_KEY:-}}"
: "${INFERPROXY_AUTH_TOKENS:=red}"
: "${INFERPROXY_UPSTREAM_MODE:=messages}"
: "${INFERPROXY_COMPACT_CLAUDE_TOOLS:=1}"
: "${INFERPROXY_PRESERVE_ORIGINAL_TOOLS_IN_SYSTEM:=0}"
: "${INFERPROXY_BLOCKED_TOOL_NAMES:=mcp__ccd_session__mark_chapter,mcp__ccd_session__spawn_task}"
: "${INFERPROXY_OPUS_DISABLE_THINKING_AFTER_TOOLS:=Write,Edit,NotebookEdit}"
: "${INFERPROXY_OPUS_ABORT_RETRY_WITHOUT_THINKING:=1}"
: "${INFERPROXY_OPUS_ABORT_RETRY_ATTEMPTS:=3}"
: "${INFERPROXY_UPSTREAM_RETRY_ATTEMPTS:=2}"
: "${INFERPROXY_UPSTREAM_RETRY_SLEEP:=0.8}"
: "${INFERPROXY_ENABLE_MODEL_FALLBACK:=0}"
: "${INFERPROXY_FALLBACK_MODELS:=}"
: "${INFERPROXY_FAILURE_DUMP_PATH:=/var/log/inferproxy_failed_requests.jsonl}"
: "${INFERPROXY_FAILURE_DUMP_FULL_TOOLS:=1}"

cat > /etc/inferproxy.env <<EOF
INFERPROXY_HOST=0.0.0.0
INFERPROXY_PORT=5066
INFERPROXY_INFERALL_BASE_URL=https://api.inferall.ai
INFERALL_API_KEY=${INFERALL_API_KEY}
INFERPROXY_AUTH_TOKENS=${INFERPROXY_AUTH_TOKENS}
INFERPROXY_UPSTREAM_MODE=${INFERPROXY_UPSTREAM_MODE}
INFERPROXY_COMPACT_CLAUDE_TOOLS=${INFERPROXY_COMPACT_CLAUDE_TOOLS}
INFERPROXY_PRESERVE_ORIGINAL_TOOLS_IN_SYSTEM=${INFERPROXY_PRESERVE_ORIGINAL_TOOLS_IN_SYSTEM}
INFERPROXY_BLOCKED_TOOL_NAMES=${INFERPROXY_BLOCKED_TOOL_NAMES}
INFERPROXY_OPUS_DISABLE_THINKING_AFTER_TOOLS=${INFERPROXY_OPUS_DISABLE_THINKING_AFTER_TOOLS}
INFERPROXY_OPUS_ABORT_RETRY_WITHOUT_THINKING=${INFERPROXY_OPUS_ABORT_RETRY_WITHOUT_THINKING}
INFERPROXY_OPUS_ABORT_RETRY_ATTEMPTS=${INFERPROXY_OPUS_ABORT_RETRY_ATTEMPTS}
INFERPROXY_UPSTREAM_RETRY_ATTEMPTS=${INFERPROXY_UPSTREAM_RETRY_ATTEMPTS}
INFERPROXY_UPSTREAM_RETRY_SLEEP=${INFERPROXY_UPSTREAM_RETRY_SLEEP}
INFERPROXY_ENABLE_MODEL_FALLBACK=${INFERPROXY_ENABLE_MODEL_FALLBACK}
INFERPROXY_FALLBACK_MODELS=${INFERPROXY_FALLBACK_MODELS}
INFERPROXY_FAILURE_DUMP_PATH=${INFERPROXY_FAILURE_DUMP_PATH}
INFERPROXY_FAILURE_DUMP_FULL_TOOLS=${INFERPROXY_FAILURE_DUMP_FULL_TOOLS}
INFERPROXY_STREAM_CHUNK_SIZE=1
INFERPROXY_CONNECT_TIMEOUT=20
INFERPROXY_READ_TIMEOUT=360
EOF

sed -i 's/\r$//' \
  /etc/systemd/system/inferproxy.service \
  /etc/inferproxy.env \
  /opt/inferproxy/app.py \
  /opt/inferproxy/requirements.txt \
  /opt/inferproxy/README.md \
  /opt/inferproxy/tests/test_app.py

/usr/bin/python3 -m py_compile /opt/inferproxy/app.py /opt/inferproxy/tests/test_app.py
(cd /opt/inferproxy && ./.venv/bin/python -m unittest discover -s tests -v)

systemctl daemon-reload
systemctl enable --now inferproxy.service
systemctl restart inferproxy.service
sleep 2
systemctl is-active inferproxy.service
ss -tlnp | grep ':5066 '
