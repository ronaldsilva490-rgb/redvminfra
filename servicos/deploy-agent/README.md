# Deploy Agent Legado

Este modulo e legado. Ele existe para cenarios de webhook e deploy automatico, mas nao faz parte do fluxo principal da VM unica. So instale se houver motivo real.

## O que ele contem

- `smart-deploy/project_detector_v3.py`
  - heuristica para detectar stack de um projeto e sugerir deploy
- `webhook-listener/webhook_server_v3.py`
  - listener Flask para receber webhooks e acionar deploy

## Dependencias do host

- Python 3.11+
- Docker
- opcionalmente PostgreSQL, dependendo do fluxo legado
- acesso a `ufw` se o listener for abrir portas dinamicamente

## Variaveis de ambiente

```bash
cp servicos/deploy-agent/.env.example /etc/red-deploy.env
```

As mais importantes:

- `RED_WEBHOOK_SECRET`
- `RED_DEPLOY_REPO_PATH`
- `RED_DEPLOY_CONFIG_PATH`
- `RED_DEPLOY_PORT_MAPPING_FILE`
- `RED_DEPLOY_BASE_PORT`

## Rodar localmente

```bash
cd servicos/deploy-agent/webhook-listener
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export RED_WEBHOOK_SECRET=change-me
export RED_DEPLOY_REPO_PATH=/srv/projects
python webhook_server_v3.py
```

Rotas expostas pelo listener:

- `POST /webhook`
- `GET /health`
- `GET /status`
- `POST /deploy/<app_name>`

## Instalacao em qualquer VM

1. Instale dependencias:

```bash
apt-get update
apt-get install -y python3 python3-venv docker.io
```

2. Copie o codigo para um caminho de runtime proprio, por exemplo:

```bash
mkdir -p /opt/red-deploy
rsync -a servicos/deploy-agent/ /opt/red-deploy/
python3 -m venv /opt/red-deploy/webhook-listener/.venv
/opt/red-deploy/webhook-listener/.venv/bin/pip install -r /opt/red-deploy/webhook-listener/requirements.txt
```

3. Crie o ambiente:

```bash
cp servicos/deploy-agent/.env.example /etc/red-deploy.env
```

4. Ajuste a unit. O repo guarda a unit legada em `infraestrutura/systemd/red-webhook.service`, mas talvez voce queira trocar o `WorkingDirectory` e `ExecStart` para bater com o caminho de runtime novo.

5. Habilite o servico:

```bash
cp infraestrutura/systemd/red-webhook.service /etc/systemd/system/red-webhook.service
systemctl daemon-reload
systemctl enable --now red-webhook
```

## Validacao recomendada

```bash
python3 -m py_compile /opt/red-deploy/webhook-listener/webhook_server_v3.py
systemctl is-active red-webhook
curl http://127.0.0.1:9000/health
curl http://127.0.0.1:9000/status
```

## Observacoes

- Este servico nao e caminho oficial de deploy da RED hoje.
- Se for reviver, revise a unit antes: o exemplo atual ainda carrega um caminho legado em `/root/red-deploy/...`.
- Evite instalar isso por padrao em VMs novas se o objetivo for apenas rodar a stack principal.
