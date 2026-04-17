# RED IQ Demo Vision Bridge

Bridge HTTP para receber a telemetria da extensao Chrome, salvar tudo em SQLite e servir como ponto de comando remoto entre a VM e a aba da IQ.

## O que este servico entrega

- endpoint de health: `/healthz`
- recepcao de snapshots, logs e relatorios
- fila de comandos remotos para extensao
- persistencia SQLite para auditoria
- leitura rapida do estado atual e historico recente

## Endpoints principais

- `GET /healthz`
- `POST /api/telemetry`
- `POST /api/log`
- `POST /api/logs`
- `GET /api/latest`
- `GET /api/summary`
- `GET /api/telemetry/recent`
- `GET /api/logs/recent`
- `POST /api/commands`
- `GET /api/commands`
- `GET /api/state/current`

## Dependencias do host

- Python 3.11+
- `python3-venv`

## Variaveis de ambiente

Use `.env.example` como base:

```bash
cp servicos/extensao-iq-demo/bridge/.env.example /etc/red-iq-vision-bridge.env
```

Variaveis principais:

- `RED_IQ_BRIDGE_DB_PATH`
- `RED_IQ_BRIDGE_TOKEN`
- `RED_IQ_BRIDGE_CORS`
- `RED_IQ_BRIDGE_HOST`
- `RED_IQ_BRIDGE_PORT`

## Rodar localmente

```bash
cd servicos/extensao-iq-demo/bridge
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 3115
```

Teste:

```bash
curl http://127.0.0.1:3115/healthz
```

## Instalacao em qualquer VM

1. Copie o runtime:

```bash
mkdir -p /opt/red-iq-vision-bridge
rsync -a servicos/extensao-iq-demo/bridge/ /opt/red-iq-vision-bridge/
python3 -m venv /opt/red-iq-vision-bridge/.venv
/opt/red-iq-vision-bridge/.venv/bin/pip install -r /opt/red-iq-vision-bridge/requirements.txt
```

2. Crie o ambiente:

```bash
cp /opt/red-iq-vision-bridge/.env.example /etc/red-iq-vision-bridge.env
```

3. Instale a unit:

```bash
cp infraestrutura/systemd/red-iq-vision-bridge.service /etc/systemd/system/red-iq-vision-bridge.service
systemctl daemon-reload
systemctl enable --now red-iq-vision-bridge
```

4. Exponha `/iq-bridge/` no nginx se a extensao for usar rota publica.

## Validacao recomendada

```bash
python3 -m py_compile /opt/red-iq-vision-bridge/app.py
systemctl is-active red-iq-vision-bridge
curl http://127.0.0.1:3115/healthz
curl http://127.0.0.1:3115/api/state/current
```

## Runtime oficial na RED

- codigo: `/opt/red-iq-vision-bridge`
- data: `/opt/red-iq-vision-bridge/data`
- env: `/etc/red-iq-vision-bridge.env`
- service: `red-iq-vision-bridge.service`
- publicacao: `/iq-bridge/`

## Observacoes

- O bridge nao depende do overlay para funcionar.
- O valor real dele esta em guardar transporte bruto, snapshots e portfolio.
- Os comandos remotos ficam mais seguros quando a extensao confirma a ordem pelo `portfolio`, nao so pelo socket.
