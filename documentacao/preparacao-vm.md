# Preparacao De VM

Use este arquivo como checklist para uma VM nova. Valores reais ficam fora do repo.

## Base

```bash
apt update
apt install -y git curl python3 python3-venv python3-pip nodejs npm ffmpeg nginx
```

## Systemd

Units versionadas:

```text
infraestrutura/systemd/red-dashboard.service
infraestrutura/systemd/red-ollama-proxy.service
infraestrutura/systemd/red-webhook.service
infraestrutura/systemd/red-evolution.service
```

Copie a unit necessaria para `/etc/systemd/system/`, rode:

```bash
systemctl daemon-reload
systemctl enable --now NOME.service
systemctl status NOME.service --no-pager
```

## Nginx

Configs versionadas:

```text
infraestrutura/nginx/red-dashboard.nginx.conf
```

Validar antes de reload:

```bash
nginx -t
systemctl reload nginx
```

## Proxy NVIDIA

O proxy precisa de:

```env
RED_PROXY_NVIDIA_API_KEY=
RED_PROXY_DATA_DIR=/var/lib/redvm-proxy
```

Nunca escrever a key real em arquivo versionado.
