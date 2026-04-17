# Proxy Lab

Laboratorio isolado para benchmark pago e descoberta de modelos sem mexer no proxy oficial.

## O que este servico entrega

- rota publica: `/proxy-lab/healthz`
- superficie Ollama-compatible e OpenAI-compatible para teste
- discovery de modelos Groq e Mistral
- estatisticas e admin local

## Dependencias do host

- Python 3.11+
- `python3-venv`
- chaves validas de Groq e ou Mistral

## Variaveis de ambiente

```bash
cp .env.example /etc/red-proxy-lab.env
```

Arquivos de key esperados:

- `groq_keys.json`
- `mistral_keys.json`

Ambos ficam, por padrao, em `/opt/red-proxy-lab/data`.

## Rodar localmente

```bash
cd servicos/proxy-lab
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export RED_LAB_PROXY_HOST=127.0.0.1
export RED_LAB_PROXY_PORT=8090
python proxy.py
```

Teste:

```bash
curl http://127.0.0.1:8090/healthz
curl http://127.0.0.1:8090/api/tags
```

## Instalacao em qualquer VM

1. Instale dependencias:

```bash
apt-get update
apt-get install -y python3 python3-venv nginx
```

2. Copie o runtime:

```bash
mkdir -p /opt/red-proxy-lab
rsync -a servicos/proxy-lab/ /opt/red-proxy-lab/
python3 -m venv /opt/red-proxy-lab/.venv
/opt/red-proxy-lab/.venv/bin/pip install -r /opt/red-proxy-lab/requirements.txt
mkdir -p /opt/red-proxy-lab/data
```

3. Crie o ambiente:

```bash
cp /opt/red-proxy-lab/.env.example /etc/red-proxy-lab.env
```

4. Coloque as keys reais em `/opt/red-proxy-lab/data`.

5. Instale a unit:

```bash
cp infraestrutura/systemd/red-proxy-lab.service /etc/systemd/system/red-proxy-lab.service
systemctl daemon-reload
systemctl enable --now red-proxy-lab
```

6. Exponha `/proxy-lab/` pelo nginx.

## Validacao recomendada

```bash
python3 -m py_compile /opt/red-proxy-lab/proxy.py
systemctl is-active red-proxy-lab
curl http://127.0.0.1:8090/healthz
curl http://127.0.0.1:8090/api/tags
```

## Fluxo recomendado

1. colocar keys Groq e Mistral
2. chamar `POST /admin/discover-models`
3. listar `GET /api/tags`
4. rodar benchmark individual
5. depois pares
6. depois trios
7. so depois promover algo para o proxy oficial

## Runtime oficial na RED

- codigo: `/opt/red-proxy-lab`
- data: `/opt/red-proxy-lab/data`
- env: `/etc/red-proxy-lab.env`
- service: `red-proxy-lab.service`
- publicacao: `/proxy-lab/`

## Observacoes

- Este servico nao substitui o proxy oficial.
- O admin deve ficar restrito a localhost ou allowlist no nginx.
