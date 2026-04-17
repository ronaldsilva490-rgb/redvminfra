# Dashboard RED Systems

Painel principal da VM unica. Ele concentra status de servicos, proxy IA, RED I.A, arquivos, terminal, projetos, processos, firewall e operacao diaria da stack.

## O que este servico entrega

- rota publica: `/dashboard/`
- subrotas reais por aba:
  - `/dashboard/servicos`
  - `/dashboard/docker`
  - `/dashboard/proxyia`
  - `/dashboard/redia`
  - `/dashboard/projetos`
  - `/dashboard/logs`
  - `/dashboard/terminal`
  - `/dashboard/arquivos`
  - `/dashboard/firewall`
  - `/dashboard/processos`
- endpoint de bootstrap: `GET /api/bootstrap`
- integracao com RED I.A por `GET /dashboard/api/redia`

## Dependencias do host

- Python 3.11+
- `python3-venv`
- acesso ao Docker socket se a aba Docker for usada
- nginx para exposicao publica

## Variaveis de ambiente

Copie `.env.example` e ajuste conforme a VM:

```bash
cp servicos/dashboard/.env.example /etc/redvm-dashboard.env
```

As mais importantes:

- `REDVM_DASH_PASSWORD`
- `REDVM_SECRET`
- `REDIA_URL`
- `REDIA_ADMIN_TOKEN`
- `RED_PROXY_URL`
- `REDVM_PUBLIC_HOST`

## Rodar localmente

```bash
cd servicos/dashboard
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export REDVM_DASH_PASSWORD=change-me
export REDVM_SECRET=change-me-too
uvicorn app:app --host 127.0.0.1 --port 9001
```

Abra:

```text
http://127.0.0.1:9001/
```

## Instalacao em qualquer VM

1. Instale dependencias base:

```bash
apt-get update
apt-get install -y python3 python3-venv nginx
```

2. Crie o runtime:

```bash
mkdir -p /opt/redvm-dashboard
rsync -a servicos/dashboard/ /opt/redvm-dashboard/
python3 -m venv /opt/redvm-dashboard/.venv
/opt/redvm-dashboard/.venv/bin/pip install -r /opt/redvm-dashboard/requirements.txt
```

3. Crie o arquivo de ambiente:

```bash
cp servicos/dashboard/.env.example /etc/redvm-dashboard.env
```

4. Ajuste os valores reais em `/etc/redvm-dashboard.env`.

5. Instale a unit:

```bash
cp infraestrutura/systemd/red-dashboard.service /etc/systemd/system/red-dashboard.service
systemctl daemon-reload
systemctl enable --now red-dashboard
```

6. Exponha o caminho `/dashboard/` pelo nginx usando `infraestrutura/nginx/red-friendly-paths.nginx.conf`.

## Validacao recomendada

```bash
python3 -m py_compile /opt/redvm-dashboard/app.py
node --check /opt/redvm-dashboard/static/app.js
systemctl is-active red-dashboard
curl -I http://127.0.0.1:9001/
curl http://127.0.0.1:9001/api/bootstrap
nginx -t
```

## Runtime oficial na RED

- codigo: `/opt/redvm-dashboard`
- env: `/etc/redvm-dashboard.env`
- service: `red-dashboard.service`
- publicacao: nginx em `/dashboard/`

## Observacoes

- O dashboard depende do token admin da RED I.A para preencher a rota `RED I.A`.
- Se a UI nova nao aparecer, valide primeiro `app.py`, `static/app.js` e `templates/index.html` juntos.
- Qualquer mudanca de rota deve manter `pushState/popstate` funcionando.
