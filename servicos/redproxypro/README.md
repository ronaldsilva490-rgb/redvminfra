# RED Proxy Pro

Proxy OpenAI/Anthropic-compatible dedicado ao Vercel AI Gateway.

Runtime oficial:

```text
/opt/redproxypro
/etc/redproxypro.env
/var/lib/redproxypro/usage.json
redproxypro.service
127.0.0.1:8095
/redproxypro/
```

## O que entrega

- `/v1/models`
- `/v1/messages` em formato Anthropic/Claude Desktop
- `/v1/messages/count_tokens`
- `/v1/chat/completions`
- `/v1/responses`
- passthrough para outros endpoints `/v1/...` suportados pela Vercel
- streaming SSE preservado em `stream: true`
- streaming SSE convertido para formato Anthropic em `/v1/messages`
- conversao de `tools` Anthropic para function tools OpenAI-compatible
- retorno de tool calls como blocos `tool_use`
- rotacao round-robin de API keys
- cooldown automatico quando uma key retorna `401`, `403`, `429` ou `5xx`
- contabilidade por key: requests, sucesso, erro, tokens, custo e modelos usados
- persistencia de uso em `/var/lib/redproxypro/usage.json`
- CORS para clientes web/extensoes
- autenticacao de entrada para nao expor o pool publicamente

## Configuracao

As chaves reais nao ficam no Git. Na VM, use `/etc/redproxypro.env`:

```env
REDPROXYPRO_HOST=127.0.0.1
REDPROXYPRO_PORT=8095
REDPROXYPRO_VERCEL_BASE_URL=https://ai-gateway.vercel.sh/v1
REDPROXYPRO_REQUIRE_AUTH=1
REDPROXYPRO_AUTH_TOKENS=red
REDPROXYPRO_DATA_DIR=/var/lib/redproxypro
REDPROXYPRO_KEYS_FILE=/etc/redproxypro.keys
```

Formato aceito no arquivo de keys:

```text
nome:vck_xxx
nome=vck_xxx
vck_xxx|nome
```

## Modelos publicados

`GET /v1/models` retorna os IDs reais `provider/model`, em ordem alfabetica:

```text
alibaba/qwen-3.6-max-preview
alibaba/qwen3.5-flash
alibaba/qwen3.5-plus
alibaba/qwen3.6-27b
anthropic/claude-sonnet-4.5
anthropic/claude-sonnet-4.6
deepseek/deepseek-v4-pro
google/gemini-3.1-pro-preview
moonshotai/kimi-k2.5
moonshotai/kimi-k2.6
openai/gpt-5.4-pro
openai/gpt-5.5
openai/gpt-5.5-pro
xai/grok-4.20-multi-agent
xai/grok-4.20-reasoning
xai/grok-4.3
xiaomi/mimo-v2.5
xiaomi/mimo-v2.5-pro
zai/glm-5.1
```

Aliases antigos continuam aceitos para nao quebrar sessoes/configs antigas:

```text
claude-red-gpt-55    -> openai/gpt-5.5
claude-red-sonnet-46 -> anthropic/claude-sonnet-4.6
claude-red-kimi-k26  -> moonshotai/kimi-k2.6
claude-red-glm-51    -> zai/glm-5.1
```

O campo `red.tool_call_tested` no catalogo indica se o modelo ja passou em teste real de tool calling. Modelos novos entram publicados, mas ficam marcados como pendentes ate validacao.

## Rodar localmente

```powershell
cd C:\Projetos\redvm\servicos\redproxypro
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:REDPROXYPRO_KEYS="teste:vck_xxx"
$env:REDPROXYPRO_AUTH_TOKENS="red"
python app.py
```

Teste:

```powershell
curl.exe http://127.0.0.1:8095/healthz
curl.exe -H "Authorization: Bearer red" http://127.0.0.1:8095/v1/models
```

Testes unitarios:

```powershell
python -m unittest discover -s tests -v
```

## Uso em clientes

Clientes OpenAI-compatible:

```text
https://redsystems.ddns.net/redproxypro/v1
Authorization: Bearer red
```

Claude Desktop / Claude Code:

```text
https://redsystems.ddns.net/redproxypro
Authorization: Bearer red
```

O Claude Desktop adiciona `/v1/messages` internamente; por isso a URL dele fica sem `/v1`.

## Claude Desktop no Windows reduzido

No Claude Desktop 1.5354, quando `deploymentMode=3p` e `inferenceProvider=gateway` estao ativos, o app tenta abrir workspace/Cowork e exige Virtual Machine Platform.

Em Windows completo, use:

```text
ferramentas/claude-desktop/Ativar-VMP-para-Claude-Desktop.cmd
```

No Windows reduzido/capado atual, use:

```text
C:\Users\Ronyd\Desktop\Claude RED Sem VMP.cmd
```

Esse launcher chama `Preparar-Claude-RED-Chat.ps1`, sincroniza os modelos no `claude_desktop_config.json` e no `configLibrary`, e abre a copia portatil patchada em:

```text
C:\Projetos\ClaudeREDDesktop\app
```

Limite importante: esse caminho e para chat/modelos customizados. Code/workspace real do Claude Desktop nao e confiavel sem VMP nesse Windows. Para desenvolvimento, use Claude Code no VS Code.

## Claude Code no VS Code

Configuracao local:

```text
ferramentas/claude-code-vscode/Configurar-Claude-Code-RED.ps1
ferramentas/claude-code-vscode/Iniciar-VSCode-Claude-Code-RED.cmd
```

Modelo padrao:

```text
anthropic/claude-sonnet-4.6
```

## Fallback de modelos auxiliares

Por compatibilidade com Claude Desktop, `/v1/messages` e `/v1/messages/count_tokens` fazem fallback quando o app envia um modelo auxiliar desconhecido em fluxos internos de web/tool.

O fallback prefere o ultimo modelo valido usado pelo mesmo cliente/sessao; se ainda nao houver historico, usa o alias padrao (`openai/gpt-5.5`). Para desligar:

```env
REDPROXYPRO_CLAUDE_UNKNOWN_MODEL_FALLBACK=0
```

TTL da memoria por cliente:

```env
REDPROXYPRO_CLAUDE_STICKY_TTL_SECONDS=21600
```

## Observabilidade

Endpoint administrativo usado pelo dashboard:

```text
GET /admin/stats
Authorization: Bearer red
```

Ele retorna `summary`, `keys` e `models` sem expor chaves reais. Quando o upstream nao informa custo em streaming, o proxy ainda registra request, latencia, tokens disponiveis e status.
