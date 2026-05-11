# InferProxy

Ponte Claude Desktop/Claude Code para InferAll. Na VM principal fica em `/opt/inferproxy`, roda como `inferproxy.service` e e publicada em:

```text
https://redsystems.ddns.net/inferproxy
```

O Claude fala Anthropic em `/v1/messages`; o InferProxy traduz para a rota documentada da InferAll:

Modo padrao, menos capado nos testes:

```text
POST https://api.inferall.ai/v1/messages
```

Modo alternativo, OpenAI/generate-like, mas nos testes bateu limite diario de chat:

```text
POST https://api.inferall.ai/ai/v1/generate
provider=<provider>
operation=chat
model=<modelo sem prefixo de provider>
messages=<mensagens estilo OpenAI>
```

Importante: a documentacao publica da InferAll nao expõe `/v1/chat/completions`. Os caminhos OpenAI comuns retornaram `404`; por isso este proxy usa `/ai/v1/generate`.

Por padrao `INFERPROXY_UPSTREAM_MODE=messages`. Para forcar a rota `generate`:

```powershell
$env:INFERPROXY_UPSTREAM_MODE = "generate"
```

Para Claude Code/Desktop, o proxy compacta o schema das tools antes de enviar para a InferAll. O schema bruto completo de algumas tools fazia a rota Anthropic da InferAll retornar `502 All providers failed`. Por padrao o proxy nao duplica mais o schema bruto em `system`, porque isso inflava muito o payload e atrasava/derrubava chamadas do Desktop.

```text
INFERPROXY_COMPACT_CLAUDE_TOOLS=1
INFERPROXY_PRESERVE_ORIGINAL_TOOLS_IN_SYSTEM=0
```

A rota Anthropic da InferAll tambem rejeitou duas tools internas do Claude Desktop/Code que tinham propriedade `title` no schema. Elas sao housekeeping de sessao, nao as tools principais de codigo, e ficam bloqueadas antes do envio upstream:

```text
INFERPROXY_BLOCKED_TOOL_NAMES=mcp__ccd_session__mark_chapter,mcp__ccd_session__spawn_task
```

## Opus 4.6 no InferAll

Na sessao real do Claude Desktop/Code, `Opus 4.6` chamou `frontend-design`, executou `Bash`, criou `index.html` com `Write`, e falhou na chamada seguinte. O upstream da InferAll abortou a chamada apos cerca de 31s com:

```text
{"error":"This operation was aborted"}
```

O isolamento mostrou:

- `Opus 4.6` + historico pos-`Write` + `thinking={"type":"adaptive"}` aborta na InferAll.
- A mesma chamada sem `thinking` responde.
- `Sonnet 4.6` com `thinking` responde no mesmo formato.

Por isso o proxy aplica dois ajustes especificos, sem trocar de modelo:

```text
INFERPROXY_OPUS_DISABLE_THINKING_AFTER_TOOLS=Write,Edit,NotebookEdit
INFERPROXY_OPUS_ABORT_RETRY_WITHOUT_THINKING=1
INFERPROXY_OPUS_ABORT_RETRY_ATTEMPTS=3
```

O primeiro remove `thinking` somente para `Opus` quando a chamada seguinte e retorno de ferramenta de escrita/edicao. O segundo faz um resgate no mesmo `Opus` sem `thinking` se a InferAll abortar antes de abrir o stream. O terceiro aumenta so as tentativas de abort do proprio Opus, sem fallback para outro modelo.

Falhas temporarias da InferAll em `/v1/messages` sao tratadas com retry no mesmo modelo antes de chegar ao Claude Desktop. Nao ha fallback automatico para outro modelo: se `Sonnet 4.6` falhar depois das tentativas, o erro segue como falha do `Sonnet 4.6`.

```text
INFERPROXY_UPSTREAM_RETRY_ATTEMPTS=2
INFERPROXY_UPSTREAM_RETRY_SLEEP=0.8
INFERPROXY_ENABLE_MODEL_FALLBACK=0
INFERPROXY_FALLBACK_MODELS=
```

## Rodar localmente

```powershell
$env:INFERALL_API_KEY = "sua_key"
python scripts/inferproxy-local/inferproxy.py
```

Depois aponte o Claude para:

```text
ANTHROPIC_BASE_URL=http://127.0.0.1:5066
ANTHROPIC_API_KEY=qualquer-token-local
```

Se quiser exigir token local:

```powershell
$env:INFERPROXY_AUTH_TOKENS = "red"
```

## Deploy na VM

```bash
rsync -a servicos/inferproxy/ /opt/inferproxy/
cp infraestrutura/systemd/inferproxy.service /etc/systemd/system/inferproxy.service
cp infraestrutura/nginx/red-friendly-paths.nginx.conf /etc/nginx/redvm-routes/red-enabled-paths.conf
cp infraestrutura/nginx/red-friendly-paths.nginx.conf /etc/nginx/snippets/red-friendly-paths.nginx.conf
cat >/etc/inferproxy.env <<'ENV'
INFERALL_API_KEY=sua_key
INFERPROXY_AUTH_TOKENS=red
INFERPROXY_UPSTREAM_MODE=messages
INFERPROXY_COMPACT_CLAUDE_TOOLS=1
INFERPROXY_PRESERVE_ORIGINAL_TOOLS_IN_SYSTEM=0
INFERPROXY_BLOCKED_TOOL_NAMES=mcp__ccd_session__mark_chapter,mcp__ccd_session__spawn_task
INFERPROXY_OPUS_DISABLE_THINKING_AFTER_TOOLS=Write,Edit,NotebookEdit
INFERPROXY_OPUS_ABORT_RETRY_WITHOUT_THINKING=1
INFERPROXY_OPUS_ABORT_RETRY_ATTEMPTS=3
INFERPROXY_UPSTREAM_RETRY_ATTEMPTS=2
INFERPROXY_UPSTREAM_RETRY_SLEEP=0.8
INFERPROXY_ENABLE_MODEL_FALLBACK=0
INFERPROXY_FALLBACK_MODELS=
ENV
systemctl daemon-reload
systemctl enable --now inferproxy.service
nginx -t && systemctl reload nginx
```

O script versionado `ferramentas/vm/deploy_inferproxy.sh` executa a instalacao padrao, cria venv, roda testes unitarios e reinicia somente `inferproxy.service`.

## Launchers Windows

Os launchers ficam em `ferramentas/claude-desktop/` e devem ser copiados para a Area de Trabalho quando forem atualizados:

```text
Claude RED InferProxy.cmd
Claude CLI - RED InferProxy.cmd
Preparar-Claude-RED-InferProxy.ps1
Claude CLI - RED InferProxy.ps1
```

## Testes

```powershell
cd servicos/inferproxy
python -m unittest discover -s tests -v
```
