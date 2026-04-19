# Migracao Mensal Completa Da Stack RED

Este runbook descreve a migracao mensal da stack inteira da VM antiga para a VM nova, com janela curta de congelamento e foco em:

- preservar estado persistente;
- levar a stack completa de uma vez;
- excluir o historico gigante do IQ Vision;
- validar tudo antes do corte de DNS;
- permitir rollback rapido se algo falhar.

Escopo atual:

- origem temporaria: `redsystems.ddns.net`
- destino temporario durante a migracao: `redsystems2.ddns.net`
- destino final apos o corte: `redsystems.ddns.net` passa a apontar para a VM nova

## 1. O Que Esta Sendo Migrado

### 1.1 Vai junto

- portal
- dashboard
- proxy IA
- REDIA
- RED Trader
- Proxy Lab
- IQ Bridge
- OpenClaw
- RED SEB Monitor
- REDSEBIA
- Rapidleech
- repo runtime em `/opt/redvm-repo`
- projetos auxiliares em `/opt/redvm-projects`
- env files
- units systemd
- configuracao nginx
- estado do OpenClaw
- bancos SQLite e diretorios de dados de producao

### 1.2 Fica para tras de proposito

- `/opt/red-iq-vision-bridge/data/iq_vision_bridge.sqlite`
- `/opt/red-iq-vision-bridge/data/frames/`
- `/root/backups/`
- `/root/migration-cache/`
- `/root/*.tar.gz`
- caches do OpenClaw:
  - `/home/openclaw/.npm`
  - `/home/openclaw/.cache`

## 2. Estrategia Geral

A migracao mensal deve ser feita em **duas fases**:

1. **Preseed**
   - copia grossa e preparacao da VM nova enquanto a antiga continua servindo trafego.
2. **Cutover**
   - congelamento curto da origem;
   - sincronizacao final dos dados mutaveis;
   - subida da nova;
   - verificacao completa;
   - troca do DNS no No-IP.

Esse desenho minimiza downtime e reduz a chance de esquecer estado importante.

## 3. Pre-Requisitos Antes De Cada Migracao

### 3.1 Na VM nova

- Ubuntu `24.04 LTS`
- acesso root via SSH
- hostname funcional em `redsystems2.ddns.net`
- conectividade outbound liberada
- disco livre suficiente
- hora sincronizada (`timedatectl`)

### 3.2 No operador local

- repo `redvm` atualizado
- Python com `paramiko`
- acesso SSH as duas VMs
- acesso ao painel No-IP
- janela curta de corte combinada

### 3.3 Congelamento de mudancas

Nas 24h anteriores:

- evitar deploys novos
- evitar alteracoes estruturais de nginx/systemd
- evitar grandes limpezas ou restauracoes em producao

## 4. Ordem Oficial De Trabalho

### Fase A - Auditoria Final Da Origem

Rodar na origem:

```bash
systemctl --failed
systemctl is-active \
  red-dashboard red-ollama-proxy redia redtrader red-proxy-lab \
  red-iq-vision-bridge red-openclaw red-seb-monitor red-seb-webhook \
  red-sebia rapidleech nginx

df -h /
ss -ltnp
```

Confirmar:

- sem `failed units`
- todos os servicos essenciais `active`
- espaco suficiente na nova

### Fase B - Preseed Da Nova

Objetivo:

- deixar runtime, env, units, nginx e dados pesados ja copiados para a nova;
- sem parar a antiga.

No preseed, copiar:

- `/opt/redvm-dashboard`
- `/opt/redvm-proxy`
- `/opt/redia`
- `/opt/redtrader`
- `/opt/red-proxy-lab`
- `/opt/red-iq-vision-bridge` com exclusoes da IQ
- `/opt/red-openclaw`
- `/opt/red-seb-monitor`
- `/opt/redsebia`
- `/opt/rapidleech`
- `/opt/redvm-repo`
- `/opt/redvm-projects`
- `/var/www/red-portal`
- `/home/openclaw/.openclaw`
- `/home/openclaw/openclaw-skills`
- env files
- units systemd
- nginx runtime

Tambem preparar na nova:

- usuario `openclaw`
- `/etc/sudoers.d/openclaw`
- `/usr/local/bin/openclaw`
- `ufw`
- `nginx`
- remover `default site` do nginx para nao haver conflito de `default_server`
- pacotes de base

### Fase C - Validacao Da VM Nova Antes Do Corte

Com a stack ainda usando `redsystems2.ddns.net`, validar:

- `systemctl daemon-reload`
- `nginx -t`
- servicos sobem localmente
- health checks locais respondem
- rotas publicas pela nova respondem em `redsystems2.ddns.net`

### Fase D - Congelamento Curto Da Origem

No momento do corte:

1. parar servicos mutaveis na origem;
2. fazer sincronizacao final;
3. subir tudo na nova;
4. validar;
5. trocar No-IP;
6. monitorar logs e health.

## 5. O Que Copiar No Preseed E O Que Resincronizar No Cutover

### 5.1 Copia de preseed

Pode ser feita com a origem totalmente online:

- runtimes completos em `/opt/...`
- `/var/www/red-portal`
- `/opt/redvm-repo`
- `/opt/redvm-projects`
- downloads do SEB
- `.openclaw`
- env files
- units e nginx

### 5.2 Copia final obrigatoria no cutover

Mesmo apos o preseed, estes caminhos devem ser sincronizados de novo com a origem parada:

- `/opt/redia/data`
- `/opt/redtrader/data`
- `/opt/red-proxy-lab/data`
- `/opt/red-proxy-lab/results`
- `/opt/red-proxy-lab/results_official`
- `/opt/redsebia/data`
- `/opt/red-seb-monitor/data/downloads`
- `/opt/red-iq-vision-bridge/data/motor_configs`
- `/home/openclaw/.openclaw`
- `/opt/redia/.env`
- todos os arquivos em `/etc/*.env` da stack RED
- units systemd em `/etc/systemd/system`
- nginx runtime em `/etc/nginx/conf.d` e `/etc/nginx/redvm-routes`

## 6. Ordem De Parada E Subida Dos Servicos

### 6.1 Ordem de parada na origem

Parar nesta ordem:

```text
red-seb-webhook
red-seb-monitor
red-openclaw
red-iq-vision-bridge
red-proxy-lab
redtrader
redia
red-sebia
rapidleech
red-dashboard
red-ollama-proxy
nginx
```

### 6.2 Ordem de subida na nova

Subir nesta ordem:

```text
red-ollama-proxy
red-dashboard
redia
redtrader
red-proxy-lab
red-iq-vision-bridge
red-openclaw
red-seb-webhook
red-seb-monitor
red-sebia
rapidleech
nginx
```

## 7. Validacoes Obrigatorias Antes De Trocar O DNS

Rodar na nova:

```bash
systemctl is-active \
  red-dashboard red-ollama-proxy redia redtrader red-proxy-lab \
  red-iq-vision-bridge red-openclaw red-seb-monitor red-seb-webhook \
  red-sebia rapidleech nginx
```

Validar localmente:

```bash
curl -I http://127.0.0.1:9001/
curl -s http://127.0.0.1:8080/api/tags | head
curl -s http://127.0.0.1:3100/healthz
curl -s http://127.0.0.1:3115/healthz
curl -I http://127.0.0.1:2580/
curl -I http://127.0.0.1:3130/redsebia/
curl -I http://127.0.0.1:2581/
```

Conferir firewall na nova:

```bash
ufw status
```

Esperado:

- `22/tcp ALLOW`
- `80/tcp ALLOW`
- `2580/tcp ALLOW`

Validar publicamente pela nova:

```text
http://redsystems2.ddns.net/
http://redsystems2.ddns.net/dashboard/
http://redsystems2.ddns.net/proxy/
http://redsystems2.ddns.net/redia/
http://redsystems2.ddns.net/trader/
http://redsystems2.ddns.net/proxy-lab/
http://redsystems2.ddns.net/iq-bridge/healthz
http://redsystems2.ddns.net/openclaw/
http://redsystems2.ddns.net/rapidleech/
http://redsystems2.ddns.net/redsebia/
http://redsystems2.ddns.net/redseb/
http://redsystems2.ddns.net/download
http://redsystems2.ddns.net:2580/
```

## 8. Corte De DNS No No-IP

Somente depois da validacao completa:

1. abrir o No-IP;
2. trocar `redsystems.ddns.net` para o IP da VM nova;
3. confirmar que `redsystems2.ddns.net` continua apontando direto para a nova;
4. monitorar resolucao DNS e acesso HTTP.

Checklist logo apos a troca:

- `redsystems.ddns.net/` responde na nova
- `redsystems.ddns.net/dashboard/` responde na nova
- `redsystems.ddns.net:2580/` responde na nova
- `redsystems.ddns.net/redsebia/` responde na nova

## 9. Limites E Expectativas Reais

### 9.1 O que pode ser mantido 1:1

- bancos SQLite
- carteiras e ledger
- dados do REDIA
- dados do RED Trader
- downloads do SEB
- sessao do OpenClaw
- configuracao do OpenClaw
- dados do REDSEBIA
- env files
- units systemd
- nginx

### 9.2 O que nao existe migracao magica

- conexao websocket viva do SEB
- websocket vivo da extensao IQ
- browser preso ao IP antigo
- sockets vivos entre usuarios e a borda antiga

Conclusao:

- **estado persistente** pode ser espelhado;
- **conexoes vivas** vao reconectar apos o DNS e/ou refresh dos clientes.

## 10. Plano De Rollback

Rollback e considerado necessario se:

- servico critico nao sobe na nova;
- wallet / login / auth falham;
- portal quebra;
- OpenClaw perde operacao minima;
- nginx ou rotas publicas falham.

Passos:

1. parar a borda na nova:
   - `systemctl stop nginx`
2. apontar `redsystems.ddns.net` de volta para o IP antigo no No-IP
3. subir de novo na antiga:
   - `red-ollama-proxy`
   - `red-dashboard`
   - `redia`
   - `redtrader`
   - `red-proxy-lab`
   - `red-iq-vision-bridge`
   - `red-openclaw`
   - `red-seb-webhook`
   - `red-seb-monitor`
   - `red-sebia`
   - `rapidleech`
   - `nginx`
4. validar as rotas publicas na antiga
5. so voltar a tentar migracao depois de registrar a causa

## 11. Script Operacional Recomendado

Script-base novo do repo:

- [ferramentas/vm/migrate_monthly_vm.py](../ferramentas/vm/migrate_monthly_vm.py)

Fases suportadas:

- `preseed`
- `cutover`
- `verify`

Exemplo:

```powershell
python ferramentas/vm/migrate_monthly_vm.py preseed `
  --source-host redsystems.ddns.net `
  --source-port 22 `
  --source-user root `
  --source-password 2580 `
  --target-host redsystems2.ddns.net `
  --target-port 22 `
  --target-user root `
  --target-password '##Ron@ld2580##'
```

Depois, na janela de corte:

```powershell
python ferramentas/vm/migrate_monthly_vm.py cutover `
  --source-host redsystems.ddns.net `
  --source-port 22 `
  --source-user root `
  --source-password 2580 `
  --target-host redsystems2.ddns.net `
  --target-port 22 `
  --target-user root `
  --target-password '##Ron@ld2580##'
```

Validacao final:

```powershell
python ferramentas/vm/migrate_monthly_vm.py verify `
  --target-host redsystems2.ddns.net `
  --target-port 22 `
  --target-user root `
  --target-password '##Ron@ld2580##'
```

## 12. Checklist Final De Aceite

Migracao mensal so e considerada concluida quando:

- todos os servicos da stack sobem na nova;
- todas as rotas publicas respondem;
- OpenClaw continua com sessao preservada;
- REDSEBIA continua com auth, saldo e historico;
- RED Trader continua com DB e health;
- REDIA continua com auth e DB;
- RED SEB Monitor continua com downloads;
- IQ Bridge sobe sem o historico pesado;
- `redsystems.ddns.net` ja aponta para a nova;
- antiga pode ser desligada ou mantida em standby.
