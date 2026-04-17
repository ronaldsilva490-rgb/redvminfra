# Proxy IA RED Systems

Gateway IA oficial da stack. Ele fala Ollama-compatible, expande modelos NIM/NVIDIA, faz roteamento por capability e hoje serve de backend central para dashboard, RED I.A, OpenClaw e clientes externos.

## O que este servico entrega

- rotas publicas via nginx:
  - `/proxy/`
  - `/ollama/`
- superficies suportadas:
  - `/api/tags`
  - `/api/show`
  - `/api/chat`
  - `/api/generate`
  - `/api/embed`
  - `/api/images/generate`
  - `/v1/models`
  - `/v1/chat/completions`
  - `/v1/completions`
  - `/v1/messages`
  - `/v1/responses`
  - `/v1/embeddings`

## Dependencias do host

- Python 3.11+
- `python3-venv`
- conectividade com os upstreams configurados

## Variaveis de ambiente

```bash
cp servicos/proxy/.env.example /etc/red-ollama-proxy.env
```

As mais importantes:

- `RED_PROXY_HOST`
- `RED_PROXY_PORT`
- `RED_PROXY_UPSTREAM`
- `RED_PROXY_NVIDIA_API_KEY`
- `RED_PROXY_DEFAULT_CHAT_MODEL`
- `RED_PROXY_DEFAULT_VISION_MODEL`
- `RED_PROXY_DEFAULT_IMAGE_MODEL`

## Rodar localmente

```bash
cd servicos/proxy
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export RED_PROXY_HOST=127.0.0.1
export RED_PROXY_PORT=8080
python proxy.py
```

Teste:

```bash
curl http://127.0.0.1:8080/api/tags
curl http://127.0.0.1:8080/v1/models
```

## Instalacao em qualquer VM

1. Instale dependencias:

```bash
apt-get update
apt-get install -y python3 python3-venv nginx
```

2. Prepare o runtime:

```bash
mkdir -p /opt/redvm-proxy
rsync -a servicos/proxy/ /opt/redvm-proxy/
python3 -m venv /opt/redvm-proxy/.venv
/opt/redvm-proxy/.venv/bin/pip install -r /opt/redvm-proxy/requirements.txt
mkdir -p /var/lib/redvm-proxy
```

3. Crie o ambiente:

```bash
cp servicos/proxy/.env.example /etc/red-ollama-proxy.env
```

4. Ajuste as chaves reais e modelos padrao.

5. Instale a unit:

```bash
cp infraestrutura/systemd/red-ollama-proxy.service /etc/systemd/system/red-ollama-proxy.service
systemctl daemon-reload
systemctl enable --now red-ollama-proxy
```

6. Exponha `/proxy/` e `/ollama/` pelo nginx com o snippet oficial.

## Validacao recomendada

```bash
python3 -m py_compile /opt/redvm-proxy/proxy.py
systemctl is-active red-ollama-proxy
curl http://127.0.0.1:8080/api/tags
curl http://127.0.0.1:8080/v1/models
nginx -t
```

## Runtime oficial na RED

- codigo: `/opt/redvm-proxy`
- data: `/var/lib/redvm-proxy`
- env: `/etc/red-ollama-proxy.env`
- service: `red-ollama-proxy.service`
- publicacao: `/proxy/` e `/ollama/`

## Observacoes

- Quando mexer em roteamento ou capabilities, valide tanto `/api/*` quanto `/v1/*`.
- Este proxy e producao. Nao misture experimento do `proxy-lab` aqui sem benchmark claro.
