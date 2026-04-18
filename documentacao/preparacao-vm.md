# Preparacao De VM

Use este arquivo como checklist para uma VM nova. Valores reais ficam fora do repo.

## Base

```bash
apt update
apt install -y git curl rsync \
  python3 python3-venv python3-pip \
  nodejs npm ffmpeg nginx ufw sqlite3 jq
```

## Systemd

Units versionadas:

```text
infraestrutura/systemd/red-dashboard.service
infraestrutura/systemd/red-ollama-proxy.service
infraestrutura/systemd/redia.service
infraestrutura/systemd/redtrader.service
infraestrutura/systemd/red-proxy-lab.service
infraestrutura/systemd/red-iq-vision-bridge.service
infraestrutura/systemd/red-openclaw.service
infraestrutura/systemd/rapidleech.service
infraestrutura/systemd/red-seb-monitor.service
infraestrutura/systemd/red-webhook.service
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
infraestrutura/nginx/red-friendly-paths.nginx.conf
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

## RED SEB Monitor

Se a VM tambem for hospedar o monitor remoto do ecossistema SEB:

- instale `servicos/redseb-monitor`
- copie `infraestrutura/systemd/red-seb-monitor.service`
- publique a porta `2580/tcp` apenas se o monitor realmente precisar ser acessado de fora
- garanta que os downloads auxiliares existam em:

```text
/opt/red-seb-monitor/data/downloads
```

## Rapidleech

Se a VM tambem for hospedar o hub legado de transferencia:

- instale `servicos/rapidleech`
- copie `infraestrutura/systemd/rapidleech.service`
- publique a rota `/rapidleech/` pelo include nginx oficial
- garanta que a pasta de runtime exista em:

```text
/opt/rapidleech/files
```
