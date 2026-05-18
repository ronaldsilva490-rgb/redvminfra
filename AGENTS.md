# AGENTS.md - RED Systems Unified VM Runbook

Este workspace guarda o codigo, a infra e a rotina operacional da RED Systems na arquitetura atual de **VM unica**.

Este arquivo existe para orientar futuras IAs e humanos que trabalhem aqui. Ele descreve **como agir neste projeto**, nao so o que existe no repo.

Nao coloque senhas, tokens ou chaves reais neste arquivo.

---

## 1. Regra-Mae

Antes de mudar qualquer coisa:

1. entenda o estado atual do repo;
2. entenda o estado atual da VM;
3. mude o minimo necessario;
4. valide localmente;
5. faca backup remoto antes de deploy;
6. reinicie **so** o servico tocado;
7. valide por HTTP, systemd e, quando fizer sentido, pela UI real.

Nao chute. Nao "assuma que deve estar ok". Teste.

---

## 2. Arquitetura Atual

Hoje a RED Systems roda consolidada em **uma VM principal**.

### Stack ativa

| Servico | Pasta no repo | Rota publica | Service systemd | Runtime na VM |
|---|---|---|---|---|
| Portal | `servicos/portal` | `/` | nginx | `/var/www/red-portal` |
| Dashboard | `servicos/dashboard` | `/dashboard/` | `red-dashboard.service` | `/opt/redvm-dashboard` |
| Proxy IA | `servicos/proxy` | `/proxy/` e `/ollama/` | `red-ollama-proxy.service` | `/opt/redvm-proxy` |
| RED Proxy Pro | `servicos/redproxypro` | `/redproxypro/` | `redproxypro.service` | `/opt/redproxypro` |
| RED Claude Proxy | `servicos/redclaudeproxy` | `/redclaudeproxy/` | `redclaudeproxy.service` | `/opt/redclaudeproxy` |
| InferProxy | `servicos/inferproxy` | `/inferproxy/` | `inferproxy.service` | `/opt/inferproxy` |
| RED NIM Claude | `servicos/rednimclaude` | `:5050` | `rednimclaude.service` | `/opt/rednimclaude` |
| RED Lightning Claude | `servicos/redlightningclaude` | `:5051` | `redlightningclaude.service` | `/opt/redlightningclaude` |
| RED Alibaba Claude | `servicos/redalibabaclaude` | `/proxy2/` e `:5052` | `redalibabaclaude.service` | `/opt/redalibabaclaude` |
| RED Search (SearXNG) | `servicos/searxng` | `/search/` | `red-searxng.service` | `/opt/red-searxng` |
| MS RED PDF | `servicos/msredpdf` | `/msredpdf/` | `msredpdf.service` | `/opt/msredpdf` |
| RED I.A | `servicos/redia` | `/redia/` | `redia.service` | `/opt/redia` |
| REDSEBIA | `servicos/redsebia` | `/redsebia/` | `red-sebia.service` | `/opt/redsebia` |
| Proxy Lab | `servicos/proxy-lab` | `/proxy-lab/` | `red-proxy-lab.service` | `/opt/red-proxy-lab` |
| Rapidleech | `servicos/rapidleech` | `/rapidleech/` | `rapidleech.service` | `/opt/rapidleech` |
| RED SEB Monitor | `servicos/redseb-monitor` | `:2580` | `red-seb-monitor.service` | `/opt/red-seb-monitor` |
| Modelos Counter | `servicos/modelos-counter` | interno | `modelos-counter.service` | — |

### Stack versionada mas removida desta VM

Os servicos abaixo continuam no repo, mas **nao existem mais como unit systemd nem como runtime em `/opt/` na VM principal** em 2026-05-10. Ficam versionados para reativacao futura.

| Servico | Pasta no repo | Service systemd | Motivo |
|---|---|---|---|
| RED Trader | `servicos/redtrader` | `redtrader.service` | removido da VM por decisao operacional |
| OpenClaw | `servicos/openclaw` | `red-openclaw.service` | removido da VM por decisao operacional |
| IQ Bridge | `servicos/extensao-iq-demo/bridge` | `red-iq-vision-bridge.service` | removido da VM por decisao operacional |
| Deploy Agent | `servicos/deploy-agent` | `red-webhook.service` | legado, removido da VM |
| RED SEB Webhook | `servicos/redseb-monitor/webhook-whatsapp.js` | `red-seb-webhook.service` | removido da VM por decisao operacional |

### O que NAO e mais pilar da stack

- Evolution nao e mais necessaria para o fluxo principal.
- A REDIA ja faz o papel de WhatsApp integrado.
- O dashboard antigo de "WhatsApp" esta em transicao/legado; o caminho correto agora e **RED I.A** dentro do dashboard principal.

---

## 3. Mapa Rapido do Repo

```text
servicos/
  portal/                Home publica
  dashboard/             Painel principal da VM unica
  proxy/                 Proxy IA oficial (compatibilidade Ollama + NVIDIA)
  redproxypro/           Proxy Vercel AI Gateway com rotacao de keys
  redclaudeproxy/        Ponte Claude Desktop/Code para modelos do proxy normal
  inferproxy/            Ponte Claude Desktop/Code para InferAll
  rednimclaude/          Gateway direto para NVIDIA NIM (porta 5050)
  redlightningclaude/    Gateway direto para Lightning AI (porta 5051)
  redalibabaclaude/      Gateway direto para Alibaba DashScope (/proxy2 e porta 5052)
  searxng/               Busca web gratuita para OpenClaude
  msredpdf/              Analise juridica de PDFs/DOCX com IA
  proxy-lab/             Laboratorio pago de benchmark
  redia/                 Runtime da RED I.A
  redsebia/              Portal, wallet e backend do produto REDSEBIA
  redtrader/             Trader demo/paper (inativo)
  openclaw/              Assistente operacional privado (inativo)
  rapidleech/            Transfer hub legado oficializado
  redseb-monitor/        Painel remoto do ecossistema RED SEB
  extensao-iq-demo/      Extensao Chrome e IQ Bridge (inativo)
  extensao-iq-motor-lab/ Motor de laboratorio remoto para IQ
  modelos-counter/       Contador de uso de modelos
  deploy-agent/          Legado

infraestrutura/
  nginx/                 Friendly paths e reverse proxy
  systemd/               Units oficiais
  docker/                Artefatos auxiliares/legados
  scripts/               Scripts de infra
  shell/                 Helpers shell

ferramentas/
  vm/                    Paramiko, migracao e execucao remota
  implantacao/           Analisadores e helpers de deploy
  diagnosticos/          Checks sem credenciais hardcoded
  avaliacoes/            Benchmarks de modelos
  nvidia/                Testes e utilitarios NVIDIA NIM/NVCF
  red_model_studio/      App desktop PySide6 para testar chat/imagem
  redclaudecode/         Launcher visual do Claude Code
  claude-desktop/        Configuradores Claude Desktop + RED Proxy Pro
  claude-code-vscode/    Configuracao Claude Code VS Code + RED Proxy Pro
  seb_frame_streamer/    GUI para simular sessao SEB via WebSocket
  openclaw/              Ferramentas auxiliares do OpenClaw
  iq_vision_benchmark/   Benchmarks visuais da IQ

documentacao/
  estado-atual-vm-2026-05-08.md   Snapshot mais recente
  arquitetura.md
  implantacao-servicos.md
  migracao-mensal-vm.md
  manual-completo.md
  preparacao-vm.md
  inventario-vm-antiga-2026-04-19.md
```

---

## 4. Como Trabalhar Neste Projeto

### 4.1. Postura esperada

Quem mexe aqui deve agir assim:

- pensar como dono da stack, nao como editor de arquivo;
- buscar contexto antes de mudar;
- evitar solucoes "magicas" sem rastrear o efeito real;
- validar tudo que afirmar;
- tratar deploy, nginx, systemd, env e UI como partes do mesmo sistema.

### 4.2. Quando o usuario pedir mudanca

Sequencia padrao:

1. localizar arquivos relevantes;
2. entender impacto no runtime real;
3. editar localmente;
4. validar sintaxe/testes/checks;
5. commitar se fizer sentido;
6. subir para a VM com backup remoto;
7. validar no alvo;
8. responder com o que mudou, o que foi validado e o que ficou pendente.

### 4.3. O que evitar

- nao sair reiniciando tudo;
- nao mexer em varios servicos se um so resolve;
- nao sobrescrever env remoto no escuro;
- nao hardcodar credenciais no repo;
- nao dizer "feito" sem checar endpoint, unit ou UI.

---

## 5. Credenciais e Segredos

Use ambiente local ou arquivo local ignorado:

```env
REDSYSTEMS_HOST=
REDSYSTEMS_SSH_PORT=
REDSYSTEMS_SSH_USER=
REDSYSTEMS_SSH_PASSWORD=
```

Locais permitidos para segredos reais:

- `.env.local`
- `AGENTS.local.md`
- `.privado/`

Nunca commit:

- chaves de API
- senhas
- tokens
- cookies
- QR payloads
- dumps sensiveis

Antes de commitar, rode:

```powershell
rg -n "(g[h]p_|n[v]api-|g[s]k_|api_key|password|senha|token|secret)" -S .
git status --short --ignored
```

Se o usuario passar credenciais no chat, use **so para a tarefa atual**. Nao persista no repo.

---

## 6. Acesso Remoto e Deploy

### 6.1. Ferramenta padrao

Use o helper do repo:

```powershell
python ferramentas/vm/paramiko_exec.py "systemctl status red-dashboard --no-pager"
```

Se precisar escrever algo mais elaborado, use Paramiko com UTF-8:

```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
```

### 6.2. Regra obrigatoria antes de deploy

Sempre fazer backup remoto antes de sobrescrever arquivo de runtime.

Exemplos:

- `/root/backups/dashboard-YYYYMMDD-HHMMSS.tgz`
- `/root/backups/proxy-YYYYMMDD-HHMMSS.tgz`
- `/root/backups/redia-YYYYMMDD-HHMMSS.tgz`
- backup de env antes de alterar tokens ou keys

### 6.3. Regra de reinicio

Depois de subir arquivo:

1. valide sintaxe;
2. reinicie **apenas** o servico tocado;
3. cheque `systemctl is-active`;
4. cheque o endpoint local;
5. se for UI, cheque via HTTP/navegador.

Exemplo:

```powershell
python ferramentas/vm/paramiko_exec.py "python3 -m py_compile /opt/redvm-dashboard/app.py"
python ferramentas/vm/paramiko_exec.py "node --check /opt/redvm-dashboard/static/app.js"
python ferramentas/vm/paramiko_exec.py "systemctl restart red-dashboard"
python ferramentas/vm/paramiko_exec.py "systemctl is-active red-dashboard"
```

---

## 7. Runtime Paths Oficiais na VM

### Codigo

- portal: `/var/www/red-portal`
- dashboard: `/opt/redvm-dashboard`
- proxy: `/opt/redvm-proxy`
- red proxy pro: `/opt/redproxypro`
- red claude proxy: `/opt/redclaudeproxy`
- inferproxy: `/opt/inferproxy`
- red nim claude: `/opt/rednimclaude`
- red lightning claude: `/opt/redlightningclaude`
- red alibaba claude: `/opt/redalibabaclaude`
- red search: `/opt/red-searxng`
- msredpdf: `/opt/msredpdf`
- redia: `/opt/redia`
- redsebia: `/opt/redsebia`
- redtrader: `/opt/redtrader`
- openclaw: `/opt/red-openclaw`
- rapidleech: `/opt/rapidleech`
- proxy-lab: `/opt/red-proxy-lab`
- red seb monitor: `/opt/red-seb-monitor`
- iq bridge: `/opt/red-iq-vision-bridge`
- teste esports: `/var/www/teste`

### Dados

- dashboard: `/opt/redvm-dashboard/data`
- proxy: `/var/lib/redvm-proxy`
- red proxy pro: `/var/lib/redproxypro`
- red claude proxy: `/var/lib/redclaudeproxy`
- inferproxy files: `/var/lib/inferproxy/files`
- inferproxy env: `/etc/inferproxy.env`
- msredpdf: `/var/lib/msredpdf`
- redia: `/opt/redia/data`
- redsebia: `/opt/redsebia/data`
- redtrader: `/opt/redtrader/data`
- proxy-lab: `/opt/red-proxy-lab/data`
- rapidleech files: `/opt/rapidleech/files`
- red seb monitor downloads: `/opt/red-seb-monitor/data/downloads`
- iq bridge: `/opt/red-iq-vision-bridge/data`

---

## 8. Nginx e Rotas Publicas

Arquivo central versionado:

- `infraestrutura/nginx/red-friendly-paths.nginx.conf`

Na VM, o include ativo fica em `/etc/nginx/redvm-routes/red-enabled-paths.conf`; a copia em `/etc/nginx/snippets/red-friendly-paths.nginx.conf` e mantida como espelho.

### Rotas publicadas

```text
/                Portal
/portal-assets/  Assets do portal
/modelo1/        Landing estatica modelo 1
/modelo2/        Landing estatica modelo 2
/teste/          Site estatico de teste esports
/dashboard/      Dashboard principal
/proxy/          Proxy IA oficial
/redproxypro/    Proxy Vercel AI Gateway
/redclaudeproxy/ Ponte Claude para proxy normal
/inferproxy/     Ponte Claude para InferAll
/proxy2/         Rota nginx publica para RED Alibaba Claude
/ollama/         Alias do proxy oficial
/search/         Busca web gratuita via SearXNG
/msredpdf/       Analise juridica de PDF/DOCX
/redia/          Runtime da RED I.A
/trader/         RED Trader
/proxy-lab/      Proxy Lab
/iq-bridge/      IQ Bridge
/openclaw/       OpenClaw
/rapidleech/     Rapidleech
/redsebia/       Portal e backend REDSEBIA
/redseb/         SEB Monitor via nginx
/download/       Downloads auxiliares do SEB Monitor
:5050            RED NIM Claude (TLS proprio)
:5051            RED Lightning Claude (TLS proprio)
:5052            RED Alibaba Claude (TLS proprio, interno/compat)
:2580            RED SEB Monitor
```

### Rotas internas do dashboard

O dashboard principal usa **rotas reais por aba**:

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

Se mexer na navegacao do dashboard:

1. alinhe template + frontend + backend;
2. preserve `pushState/popstate`;
3. preserve assets e logout em subcaminhos;
4. valide login em pelo menos 2 ou 3 subrotas.

---

## 9. Dashboard Principal

### O que ele e

`servicos/dashboard` e o painel operacional da VM unica.

Ele cuida de:

- overview da stack
- services/systemd
- docker
- proxy IA
- RED I.A
- projetos
- logs
- terminal
- arquivos
- firewall
- processos

### RED I.A dentro do dashboard

A RED I.A foi portada para dentro do dashboard principal.

O caminho certo hoje e:

- aba/rota `RED I.A`
- endpoint `GET /dashboard/api/redia`

O que essa integracao precisa continuar suportando:

- status do runtime
- envio manual de mensagem
- conversas
- schedule
- teste de IA
- benchmark
- configuracao de modelos e comportamento

### Legado

Ainda existe codigo legado de WhatsApp no dashboard.
Nao remova no susto sem verificar impacto.
Quando limpar, limpe por etapas e valide.

---

## 10. REDIA

### Papel

`servicos/redia` e o runtime da RED I.A.

Hoje ele:

- usa Baileys
- guarda config/memoria em SQLite
- usa o proxy RED como backend principal
- tem dashboard proprio legado
- tambem conversa com o dashboard principal

### Observacoes importantes

- o dashboard principal depende de `REDIA_ADMIN_TOKEN` para falar com a REDIA;
- se o painel RED I.A parecer "vazio", verifique primeiro se o token do dashboard bate com `/opt/redia/.env`;
- rotas novas do dashboard nao substituem o runtime da REDIA, so o controlam.

---

## 11. Proxies IA

### Proxy oficial (`servicos/proxy`)

- compatibilidade Ollama
- upstream NVIDIA NIM
- base operacional da stack
- rota: `/proxy/` e `/ollama/`

### RED Proxy Pro (`servicos/redproxypro`)

- Vercel AI Gateway com rotacao de keys
- keys reais em `/etc/redproxypro.env`, nunca no repo
- rota: `/redproxypro/`

### RED Claude Proxy (`servicos/redclaudeproxy`)

- ponte dedicada do Claude Desktop/Code para os modelos do proxy normal
- usa `/etc/redclaudeproxy.env`
- rota: `/redclaudeproxy/`

### InferProxy (`servicos/inferproxy`)

- ponte Claude Desktop/Code para InferAll em formato Anthropic-compatible
- usa `/etc/inferproxy.env`, nunca credenciais no repo
- rota: `/inferproxy/`
- runtime local na VM: porta `5066`

### RED NIM Claude (`servicos/rednimclaude`)

- gateway direto para NVIDIA NIM em porta propria (5050)
- TLS proprio, auth `red`

### RED Lightning Claude (`servicos/redlightningclaude`)

- gateway direto para Lightning AI em porta propria (5051)
- TLS proprio, auth `red`

### RED Alibaba Claude (`servicos/redalibabaclaude`)

- gateway direto para Alibaba DashScope multi-regiao
- rota publica preferida: `/proxy2/`
- porta propria de compatibilidade: `5052`
- TLS proprio, auth `red`
- modelo padrao operacional: `qwen3.6-plus`

### Proxy Lab (`servicos/proxy-lab`)

- laboratorio isolado
- benchmark pago
- Groq, Mistral, NVIDIA e afins
- nao misturar achado experimental com proxy oficial sem teste claro

---

## 12. Servicos Complementares

### RED Search / SearXNG (`servicos/searxng`)

- busca web gratuita usada pelo OpenClaude via provedor custom
- rota: `/search/`

### MS RED PDF (`servicos/msredpdf`)

- analise juridica de PDFs/DOCX com IA
- integrado ao proxy IA oficial
- rota: `/msredpdf/`

### REDSEBIA (`servicos/redsebia`)

- portal do cliente, admin, wallet, PIX e runtime API
- produto independente
- rota: `/redsebia/`

### Rapidleech (`servicos/rapidleech`)

- transfer hub legado oficializado como parte da stack
- rota: `/rapidleech/`

### RED SEB Monitor (`servicos/redseb-monitor`)

- painel remoto do ecossistema RED SEB / Safe Exam Browser
- porta dedicada `:2580`

### Modelos Counter (`servicos/modelos-counter`)

- contador de uso de modelos do proxy
- servico interno sem rota publica

---

## 13. RED Trader (inativo)

### Papel

`servicos/redtrader` e demo/paper trading. Nao trate como stack de dinheiro real.

### Regras praticas

- operar sempre assumindo ambiente demo;
- evitar automacoes cegas sem olhar logs e painel;
- quando mexer em estrategia, separar logica de codigo, modelos, UI e notificacoes.

### Integracoes relevantes

- notifica por REDIA/Baileys
- usa proxy principal
- conversa com IQ demo

---

## 14. Extensao IQ Demo + Bridge (inativo)

`servicos/extensao-iq-demo` e `servicos/extensao-iq-demo/bridge` servem para capturar/automatizar a IQ demo.

`servicos/extensao-iq-motor-lab` existe para iteracao rapida por JSON remoto antes de tocar a extensao principal.

### O que ja foi aprendido

- nao confiar em OCR/DOM superficial quando o dado real vem do transporte;
- o fluxo certo costuma estar em websocket, portfolio, active_id, payout por id e snapshots com timestamp;
- o bridge deve ser tratado como telemetria/control plane, nao so como log cru;
- quando o usuario pedir limpeza, trazer o bridge zerado, so com a base.

### Regra pratica

Se for mexer nisso:

1. preserve a capacidade de log bruto;
2. preserve comandos remotos;
3. correlacione `active_id`, ativo, payout e timestamp;
4. teste com a UI real sempre que houver automacao de clique/ordem.

---

## 15. OpenClaw (inativo)

OpenClaw e o assistente operacional privado da RED.

Papel esperado:

- chatops
- operacao de host
- uso do proxy RED como backend de modelos
- integracao privada por WhatsApp

Ele nao substitui dashboard, RED I.A, proxy ou RED Trader.

---

## 16. READMEs e Documentacao

Sempre que a arquitetura mudar, alinhe pelo menos:

- `README.md`
- `AGENTS.md`
- `infraestrutura/README.md`
- `servicos/README.md`
- `ferramentas/README.md`
- `servicos/<servico>/README.md` relevante

Se a realidade da VM mudou e o README continua contando a historia antiga, isso e bug de documentacao.

---

## 17. Git e Entrega

### Fluxo recomendado

1. editar local
2. validar local
3. deploy remoto com backup
4. validar remoto
5. commit
6. push

### Nao fazer

- commitar segredo
- deixar repo "quase certo"
- empurrar alteracao sem refletir runtime real

### Quando responder ao usuario

Dizer sempre:

- o que mudou
- onde mudou
- o que foi validado
- o que nao foi validado
- qualquer risco residual

---

## 18. Checklist de Operacao

### Se tocar dashboard

- `python -m py_compile servicos/dashboard/app.py`
- `node --check servicos/dashboard/static/app.js`
- validar HTML/template se mudou rotas/assets
- deploy
- `systemctl restart red-dashboard`
- `systemctl is-active red-dashboard`
- testar `/dashboard/` e pelo menos uma subrota

### Se tocar REDIA

- `node --check servicos/redia/src/*.js` relevantes
- deploy
- `systemctl restart redia`
- `systemctl is-active redia`
- validar `/redia/` ou `/dashboard/api/redia`

### Se tocar proxy/proxies

- validar sintaxe local
- deploy
- reiniciar apenas o servico tocado (`red-ollama-proxy`, `redproxypro`, `redclaudeproxy`, `inferproxy`, `rednimclaude`, `redlightningclaude`, `redalibabaclaude`)
- `systemctl is-active <service>`
- testar endpoint com curl

### Se tocar nginx

- backup remoto
- subir conf
- `nginx -t`
- `systemctl reload nginx`
- testar rota publica

### Se tocar extensao/bridge

- validar sintaxe local
- se bridge mudou: reiniciar `red-iq-vision-bridge`
- testar `/iq-bridge/healthz`
- se UX/automacao mudou: validar no navegador real

### Se tocar REDSEBIA

- validar sintaxe local
- deploy
- `systemctl restart red-sebia`
- `systemctl is-active red-sebia`
- testar `/redsebia/`

### Se tocar SearXNG

- deploy
- `systemctl restart red-searxng`
- `systemctl is-active red-searxng`
- testar `/search/`

### Se tocar MS RED PDF

- validar sintaxe local
- deploy
- `systemctl restart msredpdf`
- `systemctl is-active msredpdf`
- testar `/msredpdf/`

---

## 19. Verdades Operacionais Deste Projeto

- O repo deve refletir a VM unica.
- O dashboard principal e o centro da operacao.
- RED I.A e parte do dashboard principal, nao um apendice sem dono.
- Proxy Lab e laboratorio, nao producao.
- RED Proxy Pro, RED Claude Proxy, InferProxy, RED NIM Claude, RED Lightning Claude e RED Alibaba Claude sao gateways dedicados para Claude Desktop/Code e devem ser tratados como infra essencial.
- RED Search (SearXNG) e MS RED PDF sao servicos essenciais ativos.
- REDSEBIA e produto independente com backend proprio.
- Evolution nao e mais eixo principal.
- OpenClaw, RED Trader e IQ Bridge estao **removidos da VM** (nao existem mais como unit nem runtime), nao apenas inativos. Continuam versionados para reativacao futura.
- O usuario prefere progresso real com validacao, nao promessa.
- Sempre que houver duvida entre "parece" e "eu testei", escolha testar.
