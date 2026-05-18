# RED Alibaba Claude

Gateway direto entre Claude Desktop/Code e endpoints OpenAI-compatible da Alibaba Model Studio.

Objetivo:

- expor API Anthropic-compatible para Claude Desktop e Claude Code;
- usar o melhor das keys que realmente funcionaram;
- combinar **Singapura** para Qwen e **US Virginia** para DeepSeek/Kimi;
- publicar so modelos que passaram em texto e tool calling;
- repassar `reasoning_content` para Claude Code/Desktop como bloco `thinking` quando o modo experimental estiver ativo.

## Runtime esperado

```text
/opt/redalibabaclaude
/etc/redalibabaclaude.env
/var/lib/redalibabaclaude
redalibabaclaude.service
0.0.0.0:5052
https://redsystems.ddns.net:5052
```

## Endpoints

- `GET /`
- `GET /healthz`
- `GET /admin/tokens`
- `GET /admin/tokens/ui`
- `GET /v1/files`
- `POST /v1/files`
- `GET /v1/files/<file_id>`
- `GET /v1/files/<file_id>/content`
- `DELETE /v1/files/<file_id>`
- `GET /v1/models`
- `GET /v1/models/<model_id>`
- `POST /v1/messages`
- `POST /v1/messages/count_tokens`
- `POST /v1/chat/completions`
- `POST /v1/responses`
- `OPTIONS /*`

## Modelos publicados

- `Qwen Coder Plus`
- `Qwen 3.6 Plus`
- `Qwen 3.6 Max Preview`
- `Qwen3 Coder Next`
- `Qwen3 Coder Plus`
- `DeepSeek V4 Pro`
- `DeepSeek V4 Flash`
- `Kimi K2.5`

## Observacoes

- Por padrao, `REDALIBABACLAUDE_DIRECT_PROTOCOL_MODE=1` deixa o endpoint `/v1/messages` no fluxo mais direto possivel: traduz o payload Anthropic para OpenAI-compatible, envia uma unica chamada ao Alibaba e converte a resposta/stream de volta para eventos Anthropic. Nesse modo ficam desligados os reparos internos de ferramenta, fallback interno de WebSearch/WebFetch, contrato de workspace injetado, retry de resposta vazia e retry de "planejou mas nao executou".
- A traducao do payload preserva parametros Anthropic documentados que tenham equivalente OpenAI-compatible: `stop_sequences` vira `stop`, `top_p`/penalidades/`seed` sao repassados quando presentes, `tool_choice` vira `auto`/`none`/`required`/funcao especifica, e `tools[].strict` vira `function.strict`.
- Ferramentas preservam metadados Anthropic relevantes na descricao enviada ao modelo (`type`, `eager_input_streaming`, `defer_loading`, `allowed_callers`, `max_uses`, `use_cache`) e mantem `strict` como `function.strict`. Isso evita apagar contexto importante quando o cliente usa esquemas modernos, sem mandar campos extras que o endpoint OpenAI-compatible pode rejeitar.
- Blocos `document` em mensagens sao convertidos para texto quando possivel. `source.type=text` entra integralmente; `source.type=base64` so e decodificado quando o MIME parece textual. `source.type=file` agora resolve arquivos enviados via Files API local; texto e JSON entram inline, imagens podem virar `image_url` base64, e binarios recebem metadados seguros.
- Blocos modernos como `search_result`, `mcp_tool_result`, `mcp_tool_use`, `server_tool_use`, `server_tool_result`, `web_search_tool_result`, `web_fetch_tool_result` e `container_upload` sao aceitos e convertidos para texto estruturado quando o upstream Alibaba nao tiver suporte nativo. O objetivo e nao quebrar historico de Claude Desktop/Code/MCP.
- O stream Anthropic gerado pelo proxy segue a ordem documentada: `message_start`, `content_block_start`, deltas, `content_block_stop`, `message_delta`, `message_stop`. Se vier texto antes de tool call no stream OpenAI, o bloco de texto e fechado antes do `tool_use`, igual ao exemplo oficial Anthropic.
- O stream Anthropic agora passa por um wrapper leve de heartbeat. Se o upstream ficar silencioso por `REDALIBABACLAUDE_SSE_HEARTBEAT_SECONDS`, o cliente recebe `event: ping`; se uma excecao acontecer depois que o stream ja abriu, o proxy emite `event: error` Anthropic-like em vez de simplesmente deixar a UI pendurada.
- Tool use em stream usa `content_block_start` com `input: {}` e depois `content_block_delta` com `input_json_delta.partial_json`. Esse `input: {}` vazio e intencional no protocolo Anthropic; o cliente deve montar o JSON final acumulando os deltas ate `content_block_stop`.
- Blocos de thinking em stream abrem com `{"type":"thinking","thinking":"","signature":""}` e recebem `signature_delta` antes do `content_block_stop`, no formato esperado pelo Claude Desktop/Code. A assinatura e fake/local quando a origem e `reasoning_content` de provedor OpenAI-compatible.
- `output_config.effort=high|xhigh|max` ou `thinking.type=adaptive` ativa `enable_thinking=true` no upstream, inclusive sobrescrevendo o default `enable_thinking=false` dos Qwen 3.6. Em modo direto, `REDALIBABACLAUDE_FORCE_ANTHROPIC_THINKING` nao forca thinking quando o cliente nao pediu.
- o gateway agora propaga `request-id`/`x-request-id` de entrada, gera um ID quando o cliente nao manda, devolve esse ID nos headers e inclui `request_id` nos erros JSON. Isso aproxima o comportamento do endpoint das expectativas do Claude Desktop/Code e facilita rastreio no cliente.
- `REDALIBABACLAUDE_FORCE_ANTHROPIC_THINKING=1` mantem `enable_thinking=true` no endpoint Anthropic mesmo quando o cliente nao envia explicitamente `effort`/`thinking`.
- quando `enable_thinking=true`, o Alibaba rejeita `tool_choice` forçado ou `required`; o gateway remove esse campo antes do upstream e mantem as ferramentas disponiveis em modo automatico.
- Em modo direto, `max_tokens`, `tool_choice`, chamadas `Write`/`Edit`, `WebSearch`/`WebFetch` e conclusoes vazias sao repassados como o modelo/provedor enviar. Se o modelo mandar uma tool call ruim, o cliente recebe a tool call ruim; o proxy nao cria nova rodada escondida.
- Os antigos mecanismos de fallback/reparo ainda existem para diagnostico e podem ser religados com `REDALIBABACLAUDE_DIRECT_PROTOCOL_MODE=0`, mas nao sao o padrao do proxy Alibaba.
- por padrao no deploy RED, `REDALIBABACLAUDE_EXPERIMENTAL_THINKING_BLOCKS=1` converte `reasoning_content` em bloco Anthropic-like `thinking` com assinatura fake prefixada por `REDALIBABACLAUDE_FAKE_THINKING_SIGNATURE_PREFIX`.
- em clientes OpenAI-compatible (`/v1/chat/completions`), `reasoning_content` continua sendo removido para nao vazar metadado nao padronizado fora do fluxo Claude.
- os IDs publicados sao nomes amigaveis, sem referencia a `ALI`; a regiao usada fica apenas no metadata `red.backend`.
- O modelo padrao operacional e `qwen3.6-plus` (`Qwen 3.6 Plus`). Ele fica no pool SG e tem limite de saida cadastrado como `65536`.
- O proxy guarda limite de saida por alias quando ele e conhecido: `Qwen 3.6 Plus`, `Qwen 3.6 Max Preview`, `Qwen3 Coder Plus` e `Qwen3 Coder Next` usam `65536`; `Qwen Coder Plus` usa `8192`. Esse limite so altera `max_tokens` solicitado; nao remove prompt, historico, arquivos, system prompt nem ferramentas do payload.
- Se o upstream responder erro explicito de faixa de `max_tokens`, o proxy faz um retry reduzindo para o limite informado pelo proprio Alibaba. Esse fallback existe para modelos com limite diferente do catalogo local.
- o gateway ainda aceita os IDs brutos e os aliases antigos como compatibilidade, mas nao os publica em `/v1/models`.
- TLS e servido no proprio processo usando os certificados do host.
- autenticacao publica atual: bearer token `red`.

## Metricas de tokens

O proxy registra tokens em SQLite quando `REDALIBABACLAUDE_TOKEN_METRICS_ENABLED=1`.
A rota administrativa `GET /admin/tokens?limit=120` retorna:

- totais absolutos de entrada, saida e total;
- consolidado por modelo e endpoint;
- eventos recentes com status HTTP, duracao, stream/json e estimativa;
- estado da fila assincrona e eventos descartados.

A escrita e propositalmente leve: a chamada HTTP so enfileira um evento em memoria
e uma thread dedicada grava no banco `REDALIBABACLAUDE_TOKEN_METRICS_DB`.

Tambem existe uma interface visual em:

```text
https://redsystems.ddns.net:5052/admin/tokens/ui
```

Ela consulta `/admin/tokens` com bearer token informado no navegador e mostra totais, grafico da ultima hora, consumo por modelo, endpoint e eventos recentes.

Variaveis principais:

```env
REDALIBABACLAUDE_DATA_DIR=/var/lib/redalibabaclaude
REDALIBABACLAUDE_FILES_DIR=/var/lib/redalibabaclaude/files
REDALIBABACLAUDE_FILE_UPLOAD_MAX_BYTES=33554432
REDALIBABACLAUDE_TOKEN_METRICS_ENABLED=1
REDALIBABACLAUDE_TOKEN_METRICS_DB=/var/lib/redalibabaclaude/token_usage.sqlite3
REDALIBABACLAUDE_TOKEN_METRICS_QUEUE_SIZE=10000
REDALIBABACLAUDE_TOKEN_METRICS_RECENT_LIMIT=80
```

## Files API local

O proxy implementa uma Files API Anthropic-like para compatibilidade com clientes que enviam `source.type=file`.

Exemplo:

```bash
curl -k https://redsystems.ddns.net:5052/v1/files \
  -H "Authorization: Bearer red" \
  -F "file=@documento.txt"
```

A resposta retorna `file_id`. Em uma chamada `/v1/messages`, esse arquivo pode ser referenciado assim:

```json
{
  "type": "document",
  "source": {
    "type": "file",
    "file_id": "file_xxx"
  }
}
```

Como o upstream Alibaba e OpenAI-compatible, o proxy resolve localmente o arquivo antes de montar a chamada final:

- textos/JSON/XML entram como conteudo textual;
- imagens armazenadas entram como `image_url` base64 quando o modelo aceitar multimodal;
- PDFs e binarios entram como metadados, sem OCR ou parsing automatico neste proxy.

## Pool de API keys Alibaba

O comando operacional instalado na VM e:

```bash
/usr/local/bin/alibaba
```

Uso normal:

```bash
alibaba add sg sk-nova_chave_sg
alibaba add us sk-nova_chave_us
alibaba add both sk-nova_chave_compartilhada
```

Esse comando:

- recebe a regiao alvo (`sg`, `us` ou `both`);
- pede um nome para associar com a key;
- salva esse par em `/var/lib/redalibabaclaude/alibaba_keys.tsv`;
- reconstrói separadamente `REDALIBABACLAUDE_SG_API_KEYS` e `REDALIBABACLAUDE_US_API_KEYS` em `/etc/redalibabaclaude.env`;
- define `REDALIBABACLAUDE_SG_API_KEY` e `REDALIBABACLAUDE_US_API_KEY` com a primeira key disponivel de cada pool para compatibilidade retroativa;
- cria backup automatico como `/etc/redalibabaclaude.env.bak.YYYYmmdd-HHMMSS`;
- reinicia `redalibabaclaude.service`;
- se o servico nao voltar ativo, restaura o backup;
- executa `https://127.0.0.1:5052/healthz` com TLS ignorado para validar o processo.

Atalho antigo:

```bash
alibaba sk-nova_chave
```

continua funcionando como compatibilidade e equivale a:

```bash
alibaba add both sk-nova_chave
```

Gerenciamento:

```bash
alibaba list
alibaba list --no-test
alibaba smoke-models
alibaba del 1
alibaba --show
```

O `list` mostra `REGIAO - NOME - KEY` e, por padrao, testa cada key com uma chamada real curta em `/chat/completions`.
Isso evita falso positivo de keys que ainda listam modelos mas falham ao gerar resposta.

Modelos usados no smoke:

- SG: `REDALIBABACLAUDE_SG_SMOKE_MODEL`, default `qwen3.6-plus`;
- US: `REDALIBABACLAUDE_US_SMOKE_MODEL`, default `qwen3-coder-plus`;
- timeout: `REDALIBABACLAUDE_KEY_SMOKE_TIMEOUT`, default `7` segundos.

O teste manda uma mensagem minima, `max_tokens=2`, `temperature=0`, `stream=false` e `enable_thinking=false`.

Exemplo:

```text
1 - SG - RONALD - sk-... - OK 0.812s qwen-coder-plus
2 - US - FELIPE - sk-... - OK 0.934s qwen3-coder-plus
3 - BOTH - RESERVA - sk-... - SG OK 0.790s qwen-coder-plus | US FAIL 401 0.112s qwen3-coder-plus: ...
```

Use `alibaba list --no-test` para listar sem chamadas externas.
Use `alibaba smoke-models` para comparar rapidamente os candidatos de smoke de cada regiao usando a primeira key disponivel.

O proxy ja faz balanceamento entre as keys do pool no runtime. Cada backend usa round-robin com cooldown automatico em `429` e `5xx`, sem necessidade de escolher key manualmente.

O script fonte fica em `ferramentas/vm/alibaba` e o deploy instala esse arquivo em `/usr/local/bin/alibaba`.
