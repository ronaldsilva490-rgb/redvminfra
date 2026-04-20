# OpenClaw na RED Systems

OpenClaw roda na VM unica como um assistente operacional privado da RED Systems.

Ele nao substitui:

- `servicos/redia`
- `servicos/dashboard`
- `servicos/proxy`
- `servicos/redtrader`

Ele fica por cima da stack para:

- operar a VM por chat
- acessar o Control UI e o WebChat
- usar nossos modelos do proxy RED
- integrar canais privados, incluindo WhatsApp

## Dependencias do host

- Ubuntu ou Debian com systemd
- Node.js 24 em runtime dedicado
- npm
- nginx para publicar `/openclaw/`
- acesso ao proxy RED em `127.0.0.1:8080`

## Runtime esperado na VM

- usuario: `openclaw`
- home e state: `/home/openclaw/.openclaw`
- runtime Node dedicado: `/opt/red-openclaw`
- service: `red-openclaw.service`
- gateway local: `127.0.0.1:18789`
- rota publica via nginx: `/openclaw/`
- wrapper CLI global: `/usr/local/bin/openclaw`

## Instalacao em qualquer VM

1. Instale Node 24 em um runtime dedicado.
2. Crie o usuario `openclaw`.
3. Instale o OpenClaw em `/opt/red-openclaw`.
4. Gere o gateway e o token.
5. Configure o runtime para escutar em `127.0.0.1:18789`.
6. Publique `/openclaw/` pelo nginx.
7. Instale a unit `red-openclaw.service`.

Caminho pratico usado na RED:

```bash
useradd --system --create-home --shell /bin/bash openclaw
mkdir -p /opt/red-openclaw
```

Depois:

- runtime Node: `/opt/red-openclaw/node`
- CLI: `/usr/local/bin/openclaw`
- state: `/home/openclaw/.openclaw`
- env: `/etc/red-openclaw.env`

## Operacao do host

Na VM, o OpenClaw roda com acesso amplo ao host.

- `tools.exec.security=full`
- `tools.exec.ask=off`
- o usuario `openclaw` tem `sudo` sem senha para tarefas operacionais
- o service `red-openclaw` nao deve usar `NoNewPrivileges=true`, senao o `sudo` falha dentro das tools

## Hardening atual do WhatsApp

No runtime atual da RED, o canal WhatsApp ficou fechado para uso privado do operador.

- `channels.whatsapp.dmPolicy=allowlist`
- `channels.whatsapp.allowFrom=["+558589098018"]`
- `channels.whatsapp.accounts.default.dmPolicy=allowlist`
- `channels.whatsapp.accounts.default.allowFrom=["+558589098018"]`
- `channels.whatsapp.groupPolicy=disabled`
- `tools.elevated.allowFrom.whatsapp=["+558589098018"]`

Arquivos reais observados na VM:

- runtime principal: `/home/openclaw/.openclaw/openclaw.json`
- allowlist persistida: `/home/openclaw/.openclaw/credentials/whatsapp-default-allowFrom.json`

Isso existe para evitar que o OpenClaw converse com numeros externos por engano e para garantir que operacoes elevadas no WhatsApp so venham do dono da stack.

## Higiene de contexto

Como o OpenClaw guarda sessoes e memoria local, vale tratar lixo de conversa cedo.

Arquivos importantes:

- store de sessoes: `/home/openclaw/.openclaw/agents/main/sessions/sessions.json`
- transcricoes: `/home/openclaw/.openclaw/agents/main/sessions/*.jsonl`
- memoria curta/curada: `/home/openclaw/.openclaw/workspace/memory/`
- memoria longa: `/home/openclaw/.openclaw/workspace/MEMORY.md`

Fluxo recomendado quando aparecer conversa estranha ou contaminada:

1. fazer backup de `sessions/` e `workspace/memory/`;
2. arquivar sessoes diretas irrelevantes ou loops externos;
3. preservar a sessao do operador autorizado;
4. substituir arquivos de memoria ruins por um resumo curado;
5. rodar `openclaw memory index`.

Comandos uteis:

```bash
openclaw sessions --json
openclaw sessions cleanup --dry-run
openclaw memory index
```

Na limpeza feita em `2026-04-20`, a sessao estrangeira `+551149508309` e a sessao direta do proprio numero do bot foram arquivadas, e um resumo curado do numero autorizado `+558589098018` foi salvo para facilitar recuperacao de contexto util.

## Curadoria atual de modelos

- texto e tools principal: `red/NIM - nvidia/llama-3.1-nemotron-nano-8b-v1`
- fallback operacional de texto e tools: `red/NIM - nvidia/nemotron-mini-4b-instruct`
- fallback de seguranca: `ollama/minimax-m2.1`
- visao principal: `red/NIM - meta/llama-3.2-11b-vision-instruct`
- fallback rapido de visao: `red/NIM - nvidia/nemotron-nano-12b-v2-vl`
- fallback pesado de visao: `red/qwen3-vl:235b-instruct`
- imagem via helper: `NIM - flux.2-klein-4b`

## Validacao recomendada

```bash
systemctl is-active red-openclaw
openclaw gateway health
openclaw channels status
curl -I http://127.0.0.1:18789/openclaw/
```

Saida esperada no ambiente atual para `openclaw channels status`:

```text
WhatsApp default (RED I.A WhatsApp): enabled, configured, linked, running, connected, dm:allowlist, allow:+558589098018
```

## Exposicao

O gateway deve ficar em loopback e aparecer publicamente apenas via nginx.

## Observacoes

- Como a stack atual ainda usa HTTP simples no host publico, a configuracao do Control UI precisa assumir conscientemente um downgrade de seguranca para funcionar fora de localhost e HTTPS.
- O OpenClaw opera como uma RED I.A privada e operacional, nao como substituto direto da REDIA.
