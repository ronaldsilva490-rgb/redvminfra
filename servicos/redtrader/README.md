# RED Trader

Painel de paper trading da RED Systems. Hoje ele usa a extensao IQ + bridge como trilho principal para ver o mercado demo e enfileirar comandos.

## O que este servico entrega

- rota publica: `/trader/`
- painel FastAPI para paper trading
- feed vivo da extensao IQ em tempo real
- saldo paper local em SQLite
- comite de IA via proxy RED
- endpoint de health: `/healthz`

## Dependencias do host

- Python 3.11+
- `python3-venv`
- acesso HTTP ao bridge da extensao IQ

## Variaveis de ambiente

```bash
cp .env.example .env
```

As mais importantes:

- `REDTRADER_PASSWORD`
- `REDTRADER_SECRET`
- `REDTRADER_DB_PATH`
- `REDTRADER_IQ_BRIDGE_URL`
- `REDTRADER_IQ_BRIDGE_SESSION_ID`
- `REDSYSTEMS_PROXY_URL`

## Rodar localmente

```bash
cd servicos/redtrader
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export REDTRADER_PASSWORD=change-me
export REDTRADER_SECRET=change-me-too
export PYTHONPATH=src
python -m redtrader.app
```

Abra:

```text
http://127.0.0.1:3100
```

## Instalacao em qualquer VM

1. Instale dependencias:

```bash
apt-get update
apt-get install -y python3 python3-venv nginx
```

2. Copie o runtime:

```bash
mkdir -p /opt/redtrader
rsync -a servicos/redtrader/ /opt/redtrader/
python3 -m venv /opt/redtrader/.venv
/opt/redtrader/.venv/bin/pip install -r /opt/redtrader/requirements.txt
```

3. Crie o ambiente:

```bash
cp /opt/redtrader/.env.example /etc/redtrader.env
```

4. Ajuste o bridge, senha e segredo reais.

5. Instale a unit:

```bash
cp infraestrutura/systemd/redtrader.service /etc/systemd/system/redtrader.service
systemctl daemon-reload
systemctl enable --now redtrader
```

6. Exponha `/trader/` pelo nginx com o snippet oficial.

## Validacao recomendada

```bash
python3 -m py_compile /opt/redtrader/src/redtrader/app.py
python3 -m py_compile /opt/redtrader/src/redtrader/runtime.py
systemctl is-active redtrader
curl http://127.0.0.1:3100/healthz
curl http://127.0.0.1:3100/api/status
```

## Fluxo atual

```text
RED IQ Demo Vision -> iq-bridge -> runtime do Trader -> websocket /ws -> painel
```

O runtime:

- escolhe automaticamente a melhor sessao recente da extensao
- replica o estado vivo no painel em tempo real
- enfileira comandos para a extensao pelo mesmo bridge
- usa a extensao e o bridge como trilho principal em vez da API comunitaria antiga

## Perfis de risco

- `Conservador`
- `Balanceado`
- `Agressivo`
- `Full agressivo`

## Runtime oficial na RED

- codigo: `/opt/redtrader`
- data: `/opt/redtrader/data`
- env: `/etc/redtrader.env`
- service: `redtrader.service`
- publicacao: `/trader/`
