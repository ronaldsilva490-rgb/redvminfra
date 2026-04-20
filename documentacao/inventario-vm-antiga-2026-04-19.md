# Inventario Da VM Antiga - 2026-04-19

Este documento congela a fotografia operacional da primeira VM de origem auditada em `2026-04-19`, quando `redsystems.ddns.net` ainda era a VM ativa e `redsystems2.ddns.net` era a standby. Hoje ele deve ser lido como **snapshot historico de referencia**, enquanto o runbook mensal usa sempre os papeis `VM ativa` e `VM de standby`.

Objetivo:

- saber exatamente o que existe hoje;
- definir o que deve ser espelhado;
- deixar claro o que fica para tras por decisao explicita;
- servir de referencia para repeticoes mensais da migracao.

## 1. Host De Origem

- Host publico: `redsystems.ddns.net`
- IP observado: `200.98.201.66`
- SO: `Ubuntu 24.04.1 LTS`
- Kernel: `6.8.0-110-generic`
- Virtualizacao: `VMware`
- Disco raiz: `487G total / 35G usados / 432G livres`
- Firewall: `ufw` ativo

## 2. Host De Destino

- Host publico temporario: `redsystems2.ddns.net`
- SO: `Ubuntu 24.04.3 LTS`
- Virtualizacao: `KVM / Linode`
- Disco raiz: `81G total / 3.2G usados / 73G livres`
- Firewall: `ufw` inativo no momento da auditoria
- Estado: base limpa, sem stack RED implantada

## 3. Rotas E Portas Da VM Antiga

### 3.1 Portas publicas realmente expostas

- `22/tcp` - SSH
- `80/tcp` - nginx
- `2580/tcp` - RED SEB Monitor

### 3.2 Portas em escuta na origem

- `127.0.0.1:8090` - `red-proxy-lab`
- `127.0.0.1:3130` - `redsebia`
- `127.0.0.1:2581` - `rapidleech`
- `127.0.0.1:2590` - `red-seb-webhook`
- `0.0.0.0:8080` - `red-ollama-proxy`
- `0.0.0.0:80` - `nginx`
- `127.0.0.1:9001` - `red-dashboard`
- `0.0.0.0:3100` - `redtrader`
- `0.0.0.0:3099` - `redia`
- `0.0.0.0:3115` - `red-iq-vision-bridge`
- `0.0.0.0:2580` - `red-seb-monitor`
- `127.0.0.1:18789` - `red-openclaw`
- `127.0.0.1:18791` - `red-openclaw`

### 3.3 Friendly paths do nginx

Servidas a partir de `/etc/nginx/conf.d/red-dashboard.conf` + `/etc/nginx/redvm-routes/*.conf`:

- `/`
- `/dashboard/`
- `/download`
- `/redseb/`
- `/redsebia/`
- `/trader/`
- `/redia/`
- `/proxy-lab/`
- `/iq-bridge/`
- `/rapidleech/`
- `/openclaw/`
- `/proxy/`
- `/ollama/`

## 4. Servicos Customizados Ativos

Confirmados como `active`:

- `red-dashboard.service`
- `red-ollama-proxy.service`
- `redia.service`
- `redtrader.service`
- `red-proxy-lab.service`
- `red-iq-vision-bridge.service`
- `red-openclaw.service`
- `red-seb-monitor.service`
- `red-seb-webhook.service`
- `red-sebia.service`
- `rapidleech.service`
- `nginx.service`

## 5. Runtime Paths Oficiais Em Uso

| Servico | Runtime | Dados / estado principal |
|---|---|---|
| Dashboard | `/opt/redvm-dashboard` | `/opt/redvm-dashboard/data` |
| Proxy IA | `/opt/redvm-proxy` | configurado por env em `/etc/red-ollama-proxy.env` |
| REDIA | `/opt/redia` | `/opt/redia/data` |
| RED Trader | `/opt/redtrader` | `/opt/redtrader/data` |
| Proxy Lab | `/opt/red-proxy-lab` | `/opt/red-proxy-lab/data` |
| IQ Bridge | `/opt/red-iq-vision-bridge` | `/opt/red-iq-vision-bridge/data` |
| OpenClaw | `/opt/red-openclaw` | `/home/openclaw/.openclaw` |
| RED SEB Monitor | `/opt/red-seb-monitor` | `/opt/red-seb-monitor/data/downloads` |
| REDSEBIA | `/opt/redsebia` | `/opt/redsebia/data` |
| Rapidleech | `/opt/rapidleech` | `/opt/rapidleech/files` |
| Portal | `/var/www/red-portal` | assets locais dentro do proprio runtime |
| Repo espelhado | `/opt/redvm-repo` | usado por servicos para assets e referencia |
| Projetos auxiliares | `/opt/redvm-projects` | deve ser mantido para o dashboard |

## 6. Environment Files Atuais

Arquivos confirmados:

- `/etc/red-iq-vision-bridge.env`
- `/etc/red-ollama-proxy.env`
- `/etc/red-openclaw.env`
- `/etc/red-rapidleech.env`
- `/etc/red-sebia.env`
- `/etc/red-seb-monitor.env`
- `/etc/red-seb-webhook.env`
- `/etc/redtrader.env`
- `/etc/redvm-dashboard.env`
- `/opt/redia/.env`

## 7. Arquivos Systemd Em Uso

Unit files confirmadas:

- `/etc/systemd/system/red-dashboard.service`
- `/etc/systemd/system/red-ollama-proxy.service`
- `/etc/systemd/system/redia.service`
- `/etc/systemd/system/redtrader.service`
- `/etc/systemd/system/red-proxy-lab.service`
- `/etc/systemd/system/red-iq-vision-bridge.service`
- `/etc/systemd/system/red-openclaw.service`
- `/etc/systemd/system/red-seb-monitor.service`
- `/etc/systemd/system/red-seb-webhook.service`
- `/etc/systemd/system/red-sebia.service`
- `/etc/systemd/system/rapidleech.service`

## 8. Tamanho Dos Principais Diretórios

Snapshot de `du -sh /opt/*`:

- `/opt/red-iq-vision-bridge` - `14G`
- `/opt/red-openclaw` - `1.5G`
- `/opt/red-seb-monitor` - `686M`
- `/opt/seb-remote-view` - `685M`
- `/opt/redtrader` - `590M`
- `/opt/redsebia` - `77M`
- `/opt/redia` - `76M`
- `/opt/redvm-dashboard` - `72M`
- `/opt/red-proxy-lab` - `35M`
- `/opt/redvm-proxy` - `32M`
- `/opt/redvm-repo` - `13M`
- `/opt/rapidleech` - `4.1M`
- `/opt/redvm-projects` - `3.2M`

## 9. Persistencia Critica Por Servico

### 9.1 IQ Bridge

`/opt/red-iq-vision-bridge/data`:

- `iq_vision_bridge.sqlite` - `13.8G`
- `frames/` - historico de frames, volumoso
- `motor_configs/spy.json` - configuracao util
- `bridge.db` - vazio

Decisao de migracao:

- **copiar** `motor_configs/`
- **nao copiar** `iq_vision_bridge.sqlite`
- **nao copiar** `frames/`
- **nao copiar** `bridge.db`

### 9.2 RED Trader

`/opt/redtrader/data`:

- `redtrader.sqlite` - cerca de `523M`
- WAL/SHM
- artefatos de replay, benchmarks e snapshots

Decisao de migracao:

- **copiar tudo**

### 9.3 REDSEBIA

`/opt/redsebia/data`:

- `redsebia.db` + WAL/SHM
- `local-test.db` + WAL/SHM

Decisao de migracao:

- **copiar tudo**

### 9.4 RED SEB Monitor

`/opt/red-seb-monitor/data/downloads`:

- `REDSEBPortable.zip`
- `REDSEBPortable.zip.new`
- `SetupBundle.exe`
- `Setup.msi`
- `upgrade-seb.ps1`

Compatibilidade:

- `/opt/seb-remote-view/downloads -> /opt/red-seb-monitor/data/downloads`

Decisao de migracao:

- **copiar downloads**
- **recriar symlink legado**

### 9.5 REDIA

`/opt/redia/data`:

- `redia.sqlite`
- `auth/`
- `generated/`
- `tmp/`

Decisao de migracao:

- **copiar tudo**

### 9.6 Proxy Lab

`/opt/red-proxy-lab/data`:

- `discovered_models.json`
- `groq_keys.json`
- `mistral_keys.json`
- logs e resultados

Decisao de migracao:

- **copiar tudo**

### 9.7 OpenClaw

Runtime:

- `/opt/red-openclaw`

Estado real da sessao:

- `/home/openclaw/.openclaw`

Tambem existem:

- `/home/openclaw/openclaw-skills`
- `/etc/red-openclaw.env`
- `/etc/sudoers.d/openclaw`
- `/usr/local/bin/openclaw`

Caches grandes que nao precisam ir:

- `/home/openclaw/.npm` - `346M`
- `/home/openclaw/.cache` - `81M`

Decisao de migracao:

- **copiar** `/home/openclaw/.openclaw`
- **copiar** `/home/openclaw/openclaw-skills`
- **copiar** `/etc/sudoers.d/openclaw`
- **copiar** `/usr/local/bin/openclaw`
- **nao copiar** `.npm`
- **nao copiar** `.cache`

## 10. Legacy E Excecoes Que Ficam Fora

### 10.1 Backups e caches do root

Em `/root`:

- `/root/backups`
- `/root/migration-cache`
- `/root/*.tar.gz`

Decisao:

- **nao copiar nada disso**

### 10.2 IQ Vision historico

Historico grande e deliberadamente descartado:

- `/opt/red-iq-vision-bridge/data/iq_vision_bridge.sqlite`
- `/opt/red-iq-vision-bridge/data/frames`

### 10.3 Host-specific tuning

Root crontab atual:

- scans SCSI a cada minuto em `/sys/class/scsi_host/host*/scan`

Decisao:

- **nao tratar como parte da stack**
- **nao replicar automaticamente**

## 11. Firewall Atual Da Origem

`ufw` aberto para:

- `22/tcp`
- `80/tcp`
- `2580/tcp`

Default:

- `deny incoming`

## 12. Limites Reais Da Migracao

Estas coisas **podem** ser preservadas:

- bancos SQLite
- carteiras e ledger do REDSEBIA
- sessao do OpenClaw e autenticacao do WhatsApp
- env files
- systemd
- nginx
- downloads do SEB
- dados do REDIA, RED Trader e Proxy Lab

Estas coisas **nao podem** ser teleportadas 1:1:

- conexoes TCP vivas
- WebSockets vivos
- sessoes de navegador presas ao IP antigo
- conexoes ativas do SEB Monitor em tempo real
- conexoes ativas da extensao IQ

No corte, o esperado e:

- estado persistente mantido;
- clientes reconectam no IP novo assim que o DNS apontar;
- parte historica da IQ fica propositalmente para tras.
