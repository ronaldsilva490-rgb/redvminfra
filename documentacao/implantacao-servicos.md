# Implantacao De Servicos

Este guia descreve como implantar cada servico em qualquer VM Linux. Ele evita valores fixos de host, senha ou token. Use variaveis de ambiente e arquivos locais nao versionados.

## Convencoes

Exemplo de layout remoto:

```text
/opt/redsystems/
  proxy/
  dashboard/
  redia/
  redtrader/
  redseb-monitor/
  deploy-agent/
/etc/systemd/system/
/etc/nginx/conf.d/
/var/lib/redsystems/
```

Variaveis usadas nos exemplos:

```bash
export RED_ROOT=/opt/redsystems
export RED_DATA=/var/lib/redsystems
export RED_PUBLIC_HOST=example.com
```

## Base Da VM

Ubuntu/Debian:

```bash
apt update
apt install -y git curl nginx python3 python3-venv python3-pip nodejs npm ffmpeg build-essential
```

Docker opcional, mas recomendado para servicos auxiliares:

```bash
apt install -y docker.io docker-compose-plugin
systemctl enable --now docker
```

Crie diretorios:

```bash
mkdir -p "$RED_ROOT" "$RED_DATA"
```

## 1. Proxy IA

Servico: `servicos/proxy`

Responsabilidade:

- expor API compativel com Ollama;
- rotear modelos comuns para upstream Ollama;
- rotear modelos com prefixo `NIM - ` para NVIDIA NIM;
- expor geracao de imagem em `/api/images/generate`.

Instalacao:

```bash
mkdir -p "$RED_ROOT/proxy" "$RED_DATA/proxy"
rsync -av servicos/proxy/ "$RED_ROOT/proxy/"
cd "$RED_ROOT/proxy"
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Ambiente recomendado em `/etc/red-ollama-proxy.env`:

```env
RED_PROXY_HOST=0.0.0.0
RED_PROXY_PORT=8080
RED_PROXY_DATA_DIR=/var/lib/redsystems/proxy
RED_PROXY_UPSTREAM=https://ollama.com
RED_PROXY_NVIDIA_API_KEY=
```

Systemd:

```bash
cp infraestrutura/systemd/red-ollama-proxy.service /etc/systemd/system/red-ollama-proxy.service
systemctl daemon-reload
systemctl enable --now red-ollama-proxy
systemctl status red-ollama-proxy --no-pager
```

Health check:

```bash
curl -s http://127.0.0.1:8080/api/tags | python3 -m json.tool | head
curl -s -X POST http://127.0.0.1:8080/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-coder-next","messages":[{"role":"user","content":"responda ok"}],"stream":false}'
```

Teste de imagem NVIDIA:

```bash
curl -s -X POST http://127.0.0.1:8080/api/images/generate \
  -H 'Content-Type: application/json' \
  -d '{"model":"NIM - flux.1-schnell","prompt":"red robot mascot, dark neon dashboard, no text","width":1024,"height":1024,"steps":4}'
```

## 2. Dashboard RED Systems

Servico: `servicos/dashboard`

Responsabilidade:

- painel operacional da VM;
- gerenciamento de proxy/chaves/logs;
- chat do proxy;
- teste de geracao de imagens NVIDIA;
- deploys e integracoes auxiliares.

Instalacao:

```bash
mkdir -p "$RED_ROOT/dashboard" "$RED_DATA/dashboard"
rsync -av servicos/dashboard/ "$RED_ROOT/dashboard/"
cd "$RED_ROOT/dashboard"
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Ambiente recomendado em `/etc/red-dashboard.env`:

```env
REDVM_DASH_PASSWORD=
REDVM_SECRET=
REDVM_DATA_DIR=/var/lib/redsystems/dashboard
RED_PROXY_URL=http://127.0.0.1:8080
RED_PROXY_SERVICE=red-ollama-proxy.service
REDVM_PUBLIC_HOST=example.com
```

Systemd:

```bash
cp infraestrutura/systemd/red-dashboard.service /etc/systemd/system/red-dashboard.service
systemctl daemon-reload
systemctl enable --now red-dashboard
systemctl status red-dashboard --no-pager
```

Nginx:

```bash
cp infraestrutura/nginx/red-dashboard.nginx.conf /etc/nginx/conf.d/red-dashboard.conf
nginx -t
systemctl reload nginx
```

Health check:

```bash
curl -I http://127.0.0.1:9001/
curl -I http://127.0.0.1/
```

## 3. REDIA WhatsApp AI

Servico: `servicos/redia`

Responsabilidade:

- conectar ao WhatsApp via Baileys;
- manter memoria local;
- aprender perfis, vibe e contexto de grupos/privados;
- chamar proxy RED Systems para chat/visao;
- usar Edge TTS e STT externo quando configurado;
- enfileirar geracao de imagem.

Instalacao:

```bash
mkdir -p "$RED_ROOT/redia" "$RED_DATA/redia"
rsync -av servicos/redia/ "$RED_ROOT/redia/"
cd "$RED_ROOT/redia"
npm install
```

Ambiente recomendado em `/etc/redia.env`:

```env
REDIA_HOST=0.0.0.0
REDIA_PORT=3099
REDIA_DATA_DIR=/var/lib/redsystems/redia
REDIA_PROXY_URL=http://127.0.0.1:8080
REDIA_ADMIN_TOKEN=
REDIA_IMAGE_WORKER_TOKEN=
GROQ_API_KEY=
OPENAI_API_KEY=
```

Systemd exemplo:

```ini
[Unit]
Description=REDIA WhatsApp AI
After=network-online.target

[Service]
WorkingDirectory=/opt/redsystems/redia
EnvironmentFile=/etc/redia.env
ExecStart=/usr/bin/node src/index.js
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Ativar:

```bash
systemctl daemon-reload
systemctl enable --now redia
systemctl status redia --no-pager
```

Health check:

```bash
curl -s http://127.0.0.1:3099/api/status?token="$REDIA_ADMIN_TOKEN" | python3 -m json.tool
```

## 4. RED Trader

Servico: `servicos/redtrader`

Responsabilidade:

- dashboard de paper trading;
- dados de mercado reais;
- saldo demo local;
- analise tecnica + comite de IA via proxy;
- relatorios de operacoes.

Instalacao:

```bash
mkdir -p "$RED_ROOT/redtrader" "$RED_DATA/redtrader"
rsync -av servicos/redtrader/ "$RED_ROOT/redtrader/"
cd "$RED_ROOT/redtrader"
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Ambiente recomendado em `/etc/redtrader.env`:

```env
REDTRADER_HOST=0.0.0.0
REDTRADER_PORT=3100
REDTRADER_PASSWORD=
REDTRADER_SECRET=
REDTRADER_DB_PATH=/var/lib/redsystems/redtrader/redtrader.sqlite
REDSYSTEMS_PROXY_URL=http://127.0.0.1:8080
BINANCE_BASE_URL=https://api.binance.com
```

Systemd exemplo:

```ini
[Unit]
Description=RED Trader Painel
After=network-online.target red-ollama-proxy.service

[Service]
WorkingDirectory=/opt/redsystems/redtrader
EnvironmentFile=/etc/redtrader.env
Environment=PYTHONPATH=src
ExecStart=/opt/redsystems/redtrader/.venv/bin/python -m redtrader.app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Health check:

```bash
curl -I http://127.0.0.1:3100/
```

## 5. RED SEB Monitor

Servico: `servicos/redseb-monitor`

Responsabilidade:

- receber sessoes remotas do cliente RED SEB / Safe Exam Browser por WebSocket;
- exibir viewport e metadados do candidato em tempo real;
- enviar alertas temporarios para a sessao ativa;
- servir downloads do ecossistema SEB;
- gerar `.bat` para abrir links `seb://` ou `sebs://` no RED SEB Portable.

Instalacao:

```bash
mkdir -p "$RED_ROOT/redseb-monitor" /opt/red-seb-monitor/data/downloads
rsync -av servicos/redseb-monitor/ "$RED_ROOT/redseb-monitor/"
cd "$RED_ROOT/redseb-monitor"
npm install
```

Ambiente recomendado em `/etc/red-seb-monitor.env`:

```env
PORT=2580
SEB_REMOTE_VIEW_DOWNLOADS_DIR=/opt/red-seb-monitor/data/downloads
REDVM_REPO_DIR=/opt/redvm-repo
RED_DASHBOARD_DIR=/opt/redvm-dashboard
REDIA_DIR=/opt/redia
RED_PORTAL_DIR=/var/www/red-portal
```

Systemd:

```bash
cp infraestrutura/systemd/red-seb-monitor.service /etc/systemd/system/red-seb-monitor.service
systemctl daemon-reload
systemctl enable --now red-seb-monitor
systemctl status red-seb-monitor --no-pager
```

Health check:

```bash
curl -s http://127.0.0.1:2580/healthz | python3 -m json.tool
curl -s http://127.0.0.1:2580/api/summary | python3 -m json.tool
```

Observacao:

- a exposicao publica e dedicada em `:2580`
- nao depende do nginx principal
- publique essa porta so se a operacao remota do SEB realmente precisar dela

## 6. Rapidleech

Servico: `servicos/rapidleech`

Responsabilidade:

- servir o hub legado de downloads/uploads;
- manter o app atras do nginx em `/rapidleech/`;
- usar o tema RED e a organizacao oficial da stack.

Instalacao:

```bash
mkdir -p /opt/rapidleech
rsync -av servicos/rapidleech/ /opt/rapidleech/
mkdir -p /opt/rapidleech/files
```

Ambiente recomendado em `/etc/red-rapidleech.env`:

```env
RAPIDLEECH_HOST=127.0.0.1
RAPIDLEECH_PORT=2581
```

Systemd:

```bash
cp infraestrutura/systemd/rapidleech.service /etc/systemd/system/rapidleech.service
systemctl daemon-reload
systemctl enable --now rapidleech
systemctl status rapidleech --no-pager
```

Health check:

```bash
php -l /opt/rapidleech/index.php
php -l /opt/rapidleech/rl_init.php
curl -I http://127.0.0.1:2581/
```

Nginx:

- publique usando o include oficial em `/rapidleech/`
- preserve `X-Forwarded-Prefix /rapidleech`
- mantenha o PHP server preso em `127.0.0.1`

## 7. Deploy Agent Legado

Servico: `servicos/deploy-agent`

Responsabilidade:

- receber webhooks;
- analisar projetos;
- gerar plano/Dockerfile;
- fazer deploy e rollback.

Instalacao base:

```bash
mkdir -p "$RED_ROOT/deploy-agent"
rsync -av servicos/deploy-agent/ "$RED_ROOT/deploy-agent/"
cd "$RED_ROOT/deploy-agent/webhook-listener"
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Systemd:

```bash
cp infraestrutura/systemd/red-webhook.service /etc/systemd/system/red-webhook.service
systemctl daemon-reload
systemctl enable --now red-webhook
systemctl status red-webhook --no-pager
```

## Ordem Recomendada

```text
1. proxy
2. dashboard
3. redia
4. redtrader
5. rapidleech, se o hub legado ainda for usado
6. redseb-monitor, se o ecossistema SEB estiver ativo
7. deploy-agent, se ainda for usado
```

## Checklist Pos-Deploy

```bash
systemctl --failed
systemctl status red-ollama-proxy --no-pager
systemctl status red-dashboard --no-pager
curl -s http://127.0.0.1:8080/api/tags
nginx -t
```

Se algo falhar, volte um arquivo por vez. Nunca sobrescreva configuracoes de uma VM sem backup.
