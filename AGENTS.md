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
5. faça backup remoto antes de deploy;
6. reinicie **so** o servico tocado;
7. valide por HTTP, systemd e, quando fizer sentido, pela UI real.

Nao chute. Nao “assuma que deve estar ok”. Teste.

---

## 2. Arquitetura Atual

Hoje a RED Systems roda consolidada em **uma VM principal**.

### Stack principal

- `servicos/portal`
  - pagina inicial publica
  - rota: `/`
- `servicos/dashboard`
  - painel principal da stack
  - rota: `/dashboard/`
- `servicos/proxy`
  - proxy IA principal
  - rota: `/proxy/`
- `servicos/redia`
  - runtime da RED I.A
  - rota: `/redia/`
- `servicos/redtrader`
  - trading demo/paper
  - rota: `/trader/`
- `servicos/openclaw`
  - assistente operacional privado / chatops
  - rota: `/openclaw/`
- `servicos/redseb-monitor`
  - painel remoto do ecossistema RED SEB / Safe Exam Browser
  - rota: `:2580`
- `servicos/proxy-lab`
  - laboratorio pago de benchmark
  - rota: `/proxy-lab/`
- `servicos/extensao-iq-demo/bridge`
  - bridge da extensao IQ
  - rota: `/iq-bridge/`

### Serviços legados

- `servicos/deploy-agent`
  - legado
  - so tocar se houver motivo real
- `rapidleech`
  - legado mantido na VM
  - nao e parte central da stack

### O que NAO e mais pilar da stack

- Evolution nao e mais necessaria para o fluxo principal.
- A REDIA ja faz o papel de WhatsApp integrado.
- O dashboard antigo de “WhatsApp” esta em transicao/legado; o caminho correto agora e **RED I.A** dentro do dashboard principal.

---

## 3. Mapa Rápido do Repo

```text
servicos/
  portal/                Home publica
  dashboard/             Painel principal da VM unica
  proxy/                 Proxy IA oficial
  proxy-lab/             Laboratorio Groq/Mistral/NVIDIA
  redia/                 Runtime da RED I.A
  redtrader/             Trader demo/paper
  openclaw/              Assistente operacional privado OpenClaw
  redseb-monitor/        Painel remoto do ecossistema RED SEB
  extensao-iq-demo/      Extensao Chrome e bridge
  deploy-agent/          Legado

infraestrutura/
  nginx/                 Friendly paths e reverse proxy
  systemd/               Units oficiais
  docker/                Artefatos auxiliares/legados
  scripts/               Scripts de infra

ferramentas/
  vm/                    Paramiko, migracao e execucao remota
```

---

## 4. Como Trabalhar Neste Projeto

### 4.1. Postura esperada

Quem mexe aqui deve agir assim:

- pensar como dono da stack, nao como editor de arquivo;
- buscar contexto antes de mudar;
- evitar soluções “magicas” sem rastrear o efeito real;
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
- nao dizer “feito” sem checar endpoint, unit ou UI.

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

Se o usuario passar credenciais no chat, use **só para a tarefa atual**. Nao persista no repo.

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

- `/root/backups/dashboard-redia-YYYYMMDD-HHMMSS.tar.gz`
- `/root/backups/dashboard-routes-YYYYMMDD-HHMMSS.tar.gz`
- backup de env antes de alterar `REDIA_ADMIN_TOKEN` etc.

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

Use estes caminhos como referencia operacional:

- dashboard: `/opt/redvm-dashboard`
- proxy: `/opt/redvm-proxy`
- redia: `/opt/redia`
- redtrader: `/opt/redtrader`
- openclaw: `/opt/red-openclaw`
- red seb monitor: `/opt/red-seb-monitor`
- proxy-lab: `/opt/red-proxy-lab`
- iq bridge: `/opt/red-iq-vision-bridge`
- portal: `/var/www/red-portal`

Dados:

- dashboard data: `/opt/redvm-dashboard/data`
- proxy data: `/var/lib/redvm-proxy`
- redia data: `/opt/redia/data`
- redtrader data: `/opt/redtrader/data`
- proxy-lab data: `/opt/red-proxy-lab/data`
- iq bridge data: `/opt/red-iq-vision-bridge/data`
- red seb monitor downloads: `/opt/seb-remote-view/downloads`

---

## 8. Nginx e Rotas Públicas

Arquivo central:

- `infraestrutura/nginx/red-friendly-paths.nginx.conf`

Atalhos importantes:

- `/`
- `/dashboard/`
- `/proxy/`
- `/redia/`
- `/trader/`
- `/proxy-lab/`
- `/iq-bridge/`
- `/openclaw/`
- `:2580`

### Rotas internas do dashboard

O dashboard principal agora usa **rotas reais por aba**, e nao so troca de view em JS.

Caminhos canônicos:

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

Se mexer na navegação do dashboard:

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
- se o painel RED I.A parecer “vazio”, verifique primeiro se o token do dashboard bate com `/opt/redia/.env`;
- rotas novas do dashboard nao substituem o runtime da REDIA, so o controlam.

---

## 11. RED Trader

### Papel

`servicos/redtrader` e demo/paper trading. Nao trate como stack de dinheiro real.

### Regras praticas

- operar sempre assumindo ambiente demo;
- evitar automacoes cegas sem olhar logs e painel;
- quando mexer em estrategia, separar:
  - logica de codigo
  - comite/modelos
  - UI
  - notificacoes

### Integrações relevantes

- notifica por REDIA/Baileys
- usa proxy principal
- conversa com IQ demo

---

## 12. Extensao IQ Demo + Bridge

`servicos/extensao-iq-demo` e `servicos/extensao-iq-demo/bridge` servem para capturar/automatizar a IQ demo.

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

## 13. Proxy e Proxy Lab

### Proxy oficial

`servicos/proxy`:

- compatibilidade Ollama
- upstream NVIDIA
- base operacional da stack

### Proxy Lab

`servicos/proxy-lab`:

- laboratorio isolado
- benchmark pago
- Groq, Mistral, NVIDIA e afins
- nao misturar achado experimental com proxy oficial sem teste claro

---

## 14. READMEs e Documentacao

Sempre que a arquitetura mudar, alinhe pelo menos:

- `README.md`
- `AGENTS.md`
- `infraestrutura/README.md`
- `servicos/README.md`
- `servicos/<servico>/README.md` relevante

Se a realidade da VM mudou e o README continua contando a historia antiga, isso e bug de documentacao.

---

## 15. Git e Entrega

### Fluxo recomendado

1. editar local
2. validar local
3. deploy remoto com backup
4. validar remoto
5. commit
6. push

### Nao fazer

- commitar segredo
- deixar repo “quase certo”
- empurrar alteracao sem refletir runtime real

### Quando responder ao usuario

Dizer sempre:

- o que mudou
- onde mudou
- o que foi validado
- o que nao foi validado
- qualquer risco residual

---

## 16. Checklist de Operacao

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

---

## 17. Verdades Operacionais Deste Projeto

- O repo deve refletir a VM unica.
- O dashboard principal e o centro da operacao.
- RED I.A e parte do dashboard principal, nao um apendice sem dono.
- Proxy Lab e laboratorio, nao producao.
- Evolution nao e mais eixo principal.
- O usuario prefere progresso real com validacao, nao promessa.
- Sempre que houver duvida entre “parece” e “eu testei”, escolha testar.
