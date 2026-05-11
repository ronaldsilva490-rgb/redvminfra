# Estado Atual Da VM RED - 2026-05-10

Levantamento operacional feito em `redsystems.ddns.net` em 2026-05-11 (UTC). Este arquivo nao contem segredos.

## 1. Host

```text
hostname:     red
uptime:       5 dias, 7 horas, 46 minutos
os:           Ubuntu 24.04.4 LTS (Noble Numbat)
kernel:       6.8.0-111-generic
load avg:     0.20 0.18 0.12
cpu users:    1
ssh:          redsystems.ddns.net:22
```

## 2. Recursos

```text
RAM total:    15985 MB
RAM usada:    2145 MB (~13%)
RAM livre:    7891 MB
buff/cache:   6296 MB
swap total:   8191 MB
swap usada:   0 MB

disco /:      328G total, 19G usado, 296G livre (6%)
```

## 3. Services systemd

### Ativos (13 servicos da stack RED + infra)

| Service | Estado |
|---|---|
| `nginx.service` | active |
| `red-dashboard.service` | active |
| `red-ollama-proxy.service` | active |
| `redproxypro.service` | active |
| `redclaudeproxy.service` | active |
| `rednimclaude.service` | active |
| `redlightningclaude.service` | active |
| `redalibabaclaude.service` | active |
| `red-searxng.service` | active |
| `msredpdf.service` | active |
| `redia.service` | active |
| `red-sebia.service` | active |
| `red-proxy-lab.service` | active |
| `rapidleech.service` | active |
| `red-seb-monitor.service` | active |
| `modelos-counter.service` | active |

Infra: `containerd`, `docker`, `fail2ban`, `cron`, `sshd`, `watchdog`, `systemd-*`, `unattended-upgrades`.

### Removidos da VM (nao existem mais como unit nem runtime)

- `redtrader.service` (runtime `/opt/redtrader` removido)
- `red-openclaw.service` (runtime `/opt/red-openclaw` removido)
- `red-iq-vision-bridge.service` (runtime `/opt/red-iq-vision-bridge` removido)
- `red-webhook.service` (deploy-agent)
- `red-seb-webhook.service` (runtime permanece em `/opt/red-seb-monitor/webhook-whatsapp.js`, mas sem unit)

Continuam versionados no repo para reativacao futura, mas a VM atual nao tem mais nada deles.

## 4. Containers Docker

```text
NAMES                STATUS      PORTS
red-searxng          Up 4 days   127.0.0.1:8088->8080/tcp
red-searxng-valkey   Up 4 days   6379/tcp
```

Unica stack dockerizada ativa: SearXNG + Valkey (cache).

## 5. Portas TCP escutando

### Publico

```text
:22    sshd
:80    nginx
:443   nginx
:2580  node (red-seb-monitor)
:5050  python (rednimclaude)
:5051  python (redlightningclaude)
:5052  python (redalibabaclaude)
```

### Loopback (via nginx)

```text
127.0.0.1:3099   redia (node)
127.0.0.1:3130   redsebia (python)
127.0.0.1:3142   msredpdf (uvicorn)
127.0.0.1:2581   rapidleech (php)
127.0.0.1:8080   red-ollama-proxy (python)
127.0.0.1:8088   red-searxng (docker-proxy)
127.0.0.1:8090   red-proxy-lab (python)
127.0.0.1:8095   redproxypro (python)
127.0.0.1:8096   redclaudeproxy (python)
127.0.0.1:9001   red-dashboard (uvicorn)
127.0.0.1:9002   modelos-counter (python3)
```

## 6. Runtimes em /opt

```text
/opt/containerd
/opt/msredpdf
/opt/msredpdf.bak.20260505-202452
/opt/modelos-counter-server.py       (arquivo solto)
/opt/rapidleech
/opt/redalibabaclaude
/opt/redclaudeproxy
/opt/redia
/opt/redlightningclaude
/opt/rednimclaude
/opt/red-proxy-lab
/opt/redproxypro
/opt/red-searxng
/opt/redsebia
/opt/red-seb-monitor
/opt/redvm-dashboard
/opt/redvm-proxy
/opt/redvm-repo
/opt/vultr
```

## 7. Runtimes em /var/www

```text
/var/www/html
/var/www/modelo1
/var/www/modelo2
/var/www/modelos            (nova area: galeria de modelos)
/var/www/modelos-counter    (nova area: backend do contador)
/var/www/red-portal         (portal oficial)
/var/www/teste              (site esports de teste)
```

## 8. Nginx

- `nginx -t`: OK.
- include principal: `/etc/nginx/redvm-routes/red-enabled-paths.conf`.
- espelho versionado: `/etc/nginx/redvm-routes/red-friendly-paths.nginx.conf`.
- backups locais: `red-enabled-paths.conf.bak.*` (varios, limpar se possivel).

### Rotas publicadas em 2026-05-10

Ativas com upstream vivo:

```text
/                       -> /var/www/red-portal
/portal-assets/         -> /var/www/red-portal/assets
/modelo1/               -> /var/www/modelo1
/modelo2/               -> /var/www/modelo2
/teste/                 -> /var/www/teste
/modelos/               -> /var/www/modelos (galeria)
/api/modelos-visits     -> 127.0.0.1:9002 (modelos-counter)
/msredpdf/              -> 127.0.0.1:3142
/dashboard/             -> 127.0.0.1:9001
/hooks/                 -> 127.0.0.1:9001/hooks/
/proxy/                 -> 127.0.0.1:8080
/ollama/                -> 127.0.0.1:8080
/redproxypro/           -> 127.0.0.1:8095
/redclaudeproxy/        -> 127.0.0.1:8096
/search/                -> 127.0.0.1:8088
/redia/                 -> 127.0.0.1:3099
/redsebia/              -> 127.0.0.1:3130
/rapidleech/            -> 127.0.0.1:2581
/redseb/                -> 127.0.0.1:2580
/download/              -> 127.0.0.1:2580
/proxy-lab/             -> 127.0.0.1:8090
/proxy-lab/admin/       -> 127.0.0.1:8090 (restrito 127.0.0.1)
:2580                   -> red-seb-monitor direto
:5050                   -> rednimclaude direto (TLS)
:5051                   -> redlightningclaude direto (TLS)
:5052                   -> redalibabaclaude direto (TLS)
```

Rotas orfas (nginx configurado, upstream inexistente):

```text
/trader/     -> 127.0.0.1:3100 (redtrader removido)
/iq-bridge/  -> 127.0.0.1:3115 (bridge removido)
/openclaw/   -> 127.0.0.1:18789 (openclaw removido)
```

Essas rotas ainda estao no `red-enabled-paths.conf` mas nao respondem. Decisao operacional: manter comentadas ou remover do include ativo ate os servicos serem reativados.

## 9. Dashboard

- upstream: `127.0.0.1:9001` (uvicorn)
- runtime: `/opt/redvm-dashboard`
- env: `/etc/redvm-dashboard.env`
- subrotas canonicas continuam documentadas no repo

## 10. Diferencas chave vs inventarios anteriores

Comparado ao snapshot de 2026-05-08:

- **OpenClaw, RED Trader, IQ Bridge, Deploy Agent, SEB Webhook foram totalmente removidos da VM** (antes estavam listados como "inativo"). Runtimes em `/opt` e units systemd nao existem mais.
- Surgiu o `modelos-counter.service` como servico interno novo.
- Surgiram `/var/www/modelos` e `/var/www/modelos-counter` como areas publicas novas.
- Nova rota `/api/modelos-visits` no nginx.
- `red-ollama-proxy`, `red-searxng`, `msredpdf`, `redproxypro`, `redclaudeproxy`, `rednimclaude`, `redlightningclaude`, `redalibabaclaude`, `redia`, `red-sebia`, `rapidleech`, `red-seb-monitor`, `red-proxy-lab`, `red-dashboard` seguem ativos e estaveis.

## 11. Resumo operacional

```text
VM:           red @ redsystems.ddns.net
OS:           Ubuntu 24.04.4 LTS
uptime:       5d 7h
saude:        RAM 13%, disco 6%, carga ~0.2
services:     16 RED Systems ativos
legados:      nenhum rodando (todos removidos da VM)
stack IA:     proxy oficial + 5 gateways Claude (pro, claude, nim, lightning, alibaba)
```
