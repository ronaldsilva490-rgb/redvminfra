<p align="center">
  <img src="identidade/logo/logo.png" alt="RED Systems" width="150" />
</p>

<h1 align="center">RED Systems Unified VM</h1>

<p align="center">
  <strong>Repositorio oficial da stack consolidada em uma VM unica: portal, dashboard, proxies de IA, busca web, MS RED PDF, RED I.A, Rapidleech, monitor SEB e REDSEBIA.</strong>
</p>

---

## Visao geral

Hoje a RED Systems roda com uma arquitetura de VM unica. O objetivo deste repositorio e manter codigo, infra, documentacao e rotina operacional contando a mesma historia.

### Rotas publicas atuais

- `/` -> portal
- `/portal-assets/` -> assets publicos do portal
- `/modelo1/` -> landing estatica modelo 1
- `/modelo2/` -> landing estatica modelo 2
- `/dashboard/` -> painel principal
- `/proxy/` -> proxy IA oficial
- `/redproxypro/` -> proxy Vercel AI Gateway com rotacao de keys
- `/redclaudeproxy/` -> ponte Claude Desktop/Code para os modelos do proxy normal
- `/ollama/` -> alias do proxy IA
- `:5050` -> RED NIM Claude direto para Claude Desktop
- `:5051` -> RED Lightning Claude direto para Claude Desktop
- `:5052` -> RED Alibaba Claude direto para Claude Desktop
- `/search/` -> busca web gratuita via SearXNG
- `/msredpdf/` -> analise juridica de PDFs/DOCX com IA
- `/redia/` -> runtime standalone da RED I.A
- `/trader/` -> RED Trader
- `/proxy-lab/` -> laboratorio de benchmark
- `/iq-bridge/` -> bridge da extensao IQ
- `/openclaw/` -> assistente operacional privado
- `/rapidleech/` -> transfer hub legado oficializado
- `/redsebia/` -> portal e backend do novo produto REDSEBIA
- `/redseb/` e `/download/` -> caminhos nginx do SEB Monitor
- `:2580` -> RED SEB Monitor

Estado da VM em 2026-05-06: OpenClaw, RED Trader e IQ Bridge continuam no repo, mas estao inativos na VM principal por decisao operacional. O snapshot atual esta em [documentacao/estado-atual-vm-2026-05-06.md](documentacao/estado-atual-vm-2026-05-06.md).

### Servicos principais

| Servico | Caminho | Runtime oficial na VM | Service | Estado atual |
|---|---|---|---|---|
| Portal | `servicos/portal` | `/var/www/red-portal` | nginx | ativo |
| Dashboard | `servicos/dashboard` | `/opt/redvm-dashboard` | `red-dashboard.service` | ativo |
| Proxy IA | `servicos/proxy` | `/opt/redvm-proxy` | `red-ollama-proxy.service` | ativo |
| RED Proxy Pro | `servicos/redproxypro` | `/opt/redproxypro` | `redproxypro.service` | ativo |
| RED Claude Proxy | `servicos/redclaudeproxy` | `/opt/redclaudeproxy` | `redclaudeproxy.service` | ativo |
| RED NIM Claude | `servicos/rednimclaude` | `/opt/rednimclaude` | `rednimclaude.service` | ativo |
| RED Lightning Claude | `servicos/redlightningclaude` | `/opt/redlightningclaude` | `redlightningclaude.service` | ativo |
| RED Alibaba Claude | `servicos/redalibabaclaude` | `/opt/redalibabaclaude` | `redalibabaclaude.service` | ativo |
| RED Search | `servicos/searxng` | `/opt/red-searxng` | `red-searxng.service` | ativo |
| MS RED PDF | `servicos/msredpdf` | `/opt/msredpdf` | `msredpdf.service` | ativo |
| RED I.A | `servicos/redia` | `/opt/redia` | `redia.service` | ativo |
| REDSEBIA | `servicos/redsebia` | `/opt/redsebia` | `red-sebia.service` | ativo |
| Proxy Lab | `servicos/proxy-lab` | `/opt/red-proxy-lab` | `red-proxy-lab.service` | ativo |
| Rapidleech | `servicos/rapidleech` | `/opt/rapidleech` | `rapidleech.service` | ativo |
| RED SEB Monitor | `servicos/redseb-monitor` | `/opt/red-seb-monitor` | `red-seb-monitor.service` | ativo |
| RED Trader | `servicos/redtrader` | `/opt/redtrader` | `redtrader.service` | inativo nesta VM |
| OpenClaw | `servicos/openclaw` | `/opt/red-openclaw` | `red-openclaw.service` | inativo nesta VM |
| IQ Bridge | `servicos/extensao-iq-demo/bridge` | `/opt/red-iq-vision-bridge` | `red-iq-vision-bridge.service` | inativo nesta VM |
| Deploy Agent | `servicos/deploy-agent` | legado | `red-webhook.service` | legado |

---

## Mapa do repositorio

```text
servicos/
  portal/                Home publica
  dashboard/             Painel principal da VM unica
  proxy/                 Proxy IA oficial
  redproxypro/           Proxy Vercel AI Gateway com rotacao de keys
  redclaudeproxy/        Ponte Claude para modelos do proxy normal
  redlightningclaude/    Ponte Claude para o endpoint Lightning AI
  redalibabaclaude/      Ponte Claude para DashScope Alibaba multi-regiao
  searxng/               Busca web gratuita para OpenClaude
  msredpdf/              Analise juridica de PDFs/DOCX com IA
  proxy-lab/             Laboratorio pago e experimental
  redia/                 Runtime da RED I.A
  redtrader/             Trader demo e paper
  openclaw/              Assistente operacional privado
  rapidleech/            Transfer hub legado oficializado
  redseb-monitor/        Painel remoto do ecossistema SEB
  redsebia/              Novo portal, wallet e backend do produto REDSEBIA
  extensao-iq-demo/      Extensao Chrome e IQ Bridge
  extensao-iq-motor-lab/ Motor de laboratorio remoto para IQ
  deploy-agent/          Legado

infraestrutura/
  nginx/                 Friendly paths e reverse proxy
  systemd/               Units oficiais
  scripts/               Apoio de infra
  docker/                Artefatos auxiliares e legados

ferramentas/
  vm/                    Paramiko, execucao remota e migracao
  claude-desktop/        Configuracao Claude Desktop + RED Proxy Pro
  claude-code-vscode/    Configuracao Claude Code VS Code + RED Proxy Pro
  iq_vision_benchmark/   Benchmarks visuais da IQ
  red_model_studio/      App desktop para testar modelos
  redclaudecode/         Launcher do Claude Code

documentacao/
  estado-atual-vm-2026-05-06.md
  arquitetura.md
  implantacao-servicos.md
  inventario-vm-antiga-2026-04-19.md
  migracao-mensal-vm.md
  manual-completo.md
  preparacao-vm.md
```

---

## Como instalar a stack em uma VM nova

### 1. Dependencias base da VM

Em uma VM Ubuntu ou Debian limpa, comece com:

```bash
apt-get update
apt-get install -y \
  git curl rsync nginx ufw \
  python3 python3-venv python3-pip \
  nodejs npm ffmpeg \
  sqlite3 jq
```

Se a VM for usar OpenClaw no mesmo desenho da RED, instale tambem um runtime Node 24 dedicado para ele.

### 2. Clone o repositorio

```bash
git clone <repo-url> /srv/redvm
cd /srv/redvm
```

### 3. Instale servico por servico

Cada servico agora tem um guia proprio de instalacao em qualquer VM:

- [servicos/portal/README.md](servicos/portal/README.md)
- [servicos/dashboard/README.md](servicos/dashboard/README.md)
- [servicos/proxy/README.md](servicos/proxy/README.md)
- [servicos/redproxypro/README.md](servicos/redproxypro/README.md)
- [servicos/redclaudeproxy/README.md](servicos/redclaudeproxy/README.md)
- [servicos/msredpdf/README.md](servicos/msredpdf/README.md)
- [servicos/searxng/README.md](servicos/searxng/README.md)
- [servicos/proxy-lab/README.md](servicos/proxy-lab/README.md)
- [servicos/redia/README.md](servicos/redia/README.md)
- [servicos/redtrader/README.md](servicos/redtrader/README.md)
- [servicos/openclaw/README.md](servicos/openclaw/README.md)
- [servicos/rapidleech/README.md](servicos/rapidleech/README.md)
- [servicos/redseb-monitor/README.md](servicos/redseb-monitor/README.md)
- [servicos/redsebia/README.md](servicos/redsebia/README.md)
- [servicos/extensao-iq-demo/README.md](servicos/extensao-iq-demo/README.md)
- [servicos/extensao-iq-motor-lab/README.md](servicos/extensao-iq-motor-lab/README.md)
- [servicos/deploy-agent/README.md](servicos/deploy-agent/README.md)

Regra pratica:

1. instalar dependencias do servico
2. copiar para o runtime oficial em `/opt/...` ou `/var/www/...`
3. criar `.env` ou `EnvironmentFile`
4. instalar a unit systemd quando houver
5. publicar no nginx quando houver rota publica
6. validar por sintaxe, `systemctl` e HTTP ou UI

### Migracao mensal entre VMs

O runbook operacional da migracao mensal completa esta em:

- [documentacao/inventario-vm-antiga-2026-04-19.md](documentacao/inventario-vm-antiga-2026-04-19.md)
- [documentacao/migracao-mensal-vm.md](documentacao/migracao-mensal-vm.md)

Script-base de apoio:

- [ferramentas/vm/migrate_monthly_vm.py](ferramentas/vm/migrate_monthly_vm.py)
- [ferramentas/vm/run_monthly_migration.ps1](ferramentas/vm/run_monthly_migration.ps1)
- [ferramentas/vm/migrate_monthly_vm.env.example](ferramentas/vm/migrate_monthly_vm.env.example)

---

## Runtime paths oficiais

### Codigo

- dashboard: `/opt/redvm-dashboard`
- proxy: `/opt/redvm-proxy`
- red proxy pro: `/opt/redproxypro`
- red claude proxy: `/opt/redclaudeproxy`
- red search: `/opt/red-searxng`
- msredpdf: `/opt/msredpdf`
- redia: `/opt/redia`
- redtrader: `/opt/redtrader`
- openclaw: `/opt/red-openclaw`
- rapidleech: `/opt/rapidleech`
- proxy-lab: `/opt/red-proxy-lab`
- red seb monitor: `/opt/red-seb-monitor`
- redsebia: `/opt/redsebia`
- iq bridge: `/opt/red-iq-vision-bridge`
- portal: `/var/www/red-portal`

### Dados

- dashboard: `/opt/redvm-dashboard/data`
- proxy: `/var/lib/redvm-proxy`
- red proxy pro: `/var/lib/redproxypro`
- red claude proxy: `/var/lib/redclaudeproxy`
- msredpdf: `/var/lib/msredpdf`
- redia: `/opt/redia/data`
- redtrader: `/opt/redtrader/data`
- proxy-lab: `/opt/red-proxy-lab/data`
- rapidleech files: `/opt/rapidleech/files`
- red seb monitor downloads: `/opt/red-seb-monitor/data/downloads`
- red seb portable zip fonte: `servicos/redsebia/downloads/REDSEBPortable.zip`
- redsebia: `/opt/redsebia/data`
- iq bridge: `/opt/red-iq-vision-bridge/data`

---

## Nginx

O arquivo central versionado do include publico e `infraestrutura/nginx/red-friendly-paths.nginx.conf`. Na VM atual, o include ativo do nginx fica em `/etc/nginx/redvm-routes/red-enabled-paths.conf`; a copia em `/etc/nginx/snippets/red-friendly-paths.nginx.conf` e mantida como espelho.

Ele concentra as rotas amigaveis:

- `/`
- `/dashboard/`
- `/proxy/`
- `/redproxypro/`
- `/redclaudeproxy/`
- `/ollama/`
- `/search/`
- `/msredpdf/`
- `/modelo1/`
- `/modelo2/`
- `/redia/`
- `/trader/`
- `/proxy-lab/`
- `/iq-bridge/`
- `/openclaw/`
- `/rapidleech/`
- `/redsebia/`
- `/redseb/`
- `/download/`

Sempre que mexer em nginx:

```bash
nginx -t
systemctl reload nginx
```

---

## Dashboard principal

O dashboard e o centro operacional da stack.

Subrotas canonicas:

- `/dashboard/`
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

Se mexer na navegacao dele:

1. alinhe frontend, backend e template
2. preserve `pushState` e `popstate`
3. valide login e pelo menos duas subrotas reais

---

## RED I.A

A RED I.A continua existindo como runtime proprio em `/redia/`, mas o caminho principal de operacao hoje e o dashboard principal em `/dashboard/redia`.

Ela depende de:

- proxy RED como backend IA
- token admin correto para o dashboard conversar com o runtime
- WhatsApp e Baileys quando o canal estiver ativo

---

## RED Trader

O RED Trader hoje e demo/paper e deve ser tratado assim. Em 2026-05-06 ele continua versionado, mas esta inativo na VM principal.

Estado atual importante:

- feed da IQ via extensao e bridge
- sem depender da API comunitaria antiga como caminho principal
- painel versionado em `/trader/` quando o servico for reativado

---

## Extensao IQ Demo

O bloco IQ e composto por:

- extensao principal `servicos/extensao-iq-demo`
- bridge `servicos/extensao-iq-demo/bridge`
- extensao de laboratorio `servicos/extensao-iq-motor-lab`

Em 2026-05-06 a bridge IQ esta versionada, mas inativa na VM principal.

Uso recomendado:

1. testar comportamento novo no `motor-lab`
2. observar resultado no bridge
3. portar so o que prestou para a principal

Fonte principal de verdade:

- transporte da pagina
- `active_id`
- payout por id
- `positions-state` e portfolio

Nao confiar so em OCR ou DOM superficial.

---

## OpenClaw

OpenClaw e o assistente operacional privado da RED. Em 2026-05-06 ele continua versionado, mas esta inativo na VM principal.

Papel esperado:

- chatops
- operacao de host
- uso do proxy RED como backend de modelos
- integracao privada por WhatsApp

Ele nao substitui:

- dashboard
- RED I.A
- proxy
- RED Trader

---

## Fluxo recomendado de trabalho

1. entender o estado atual do repo
2. entender o estado atual da VM
3. editar localmente
4. validar sintaxe e checks
5. fazer backup remoto
6. subir o minimo necessario
7. reiniciar so o servico tocado
8. validar via `systemctl`, HTTP e UI real quando fizer sentido

---

## Deploy remoto

O helper padrao do repo e:

```bash
python ferramentas/vm/paramiko_exec.py "systemctl status red-dashboard --no-pager"
```

Com credenciais por ambiente:

```bash
export REDSYSTEMS_HOST=redsystems.ddns.net
export REDSYSTEMS_SSH_PORT=22
export REDSYSTEMS_SSH_USER=root
export REDSYSTEMS_SSH_PASSWORD=...
```

Sempre faca backup remoto antes de sobrescrever runtime.

Exemplos:

- `/root/backups/dashboard-YYYYMMDD-HHMMSS.tgz`
- `/root/backups/proxy-YYYYMMDD-HHMMSS.tgz`
- `/root/backups/openclaw-YYYYMMDD-HHMMSS.tgz`

---

## Seguranca e segredos

Nunca commite:

- senhas
- tokens
- chaves de API
- cookies
- QR payloads
- dumps sensiveis

Locais aceitos para segredo real:

- `.env.local`
- `AGENTS.local.md`
- `.privado/`

Checagem recomendada antes de commit:

```bash
rg -n "(g[h]p_|n[v]api-|g[s]k_|api_key|password|senha|token|secret)" -S .
git status --short --ignored
```

---

## Documentacao complementar

- [AGENTS.md](AGENTS.md)
- [servicos/README.md](servicos/README.md)
- [infraestrutura/README.md](infraestrutura/README.md)
- [documentacao/preparacao-vm.md](documentacao/preparacao-vm.md)
- [documentacao/implantacao-servicos.md](documentacao/implantacao-servicos.md)
- [documentacao/manual-completo.md](documentacao/manual-completo.md)

Se a documentacao e o runtime divergirem, trate isso como bug e alinhe os dois lados.
