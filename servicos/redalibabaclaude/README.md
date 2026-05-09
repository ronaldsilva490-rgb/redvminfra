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
- `GET /v1/models`
- `POST /v1/messages`
- `POST /v1/messages/count_tokens`
- `POST /v1/chat/completions`
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

- `output_config.effort=high|xhigh|max` ou `thinking.type=adaptive` ativa `enable_thinking=true` no upstream, inclusive sobrescrevendo o default `enable_thinking=false` dos Qwen 3.6.
- `REDALIBABACLAUDE_FORCE_ANTHROPIC_THINKING=1` mantem `enable_thinking=true` no endpoint Anthropic mesmo quando o cliente nao envia explicitamente `effort`/`thinking`.
- quando `enable_thinking=true`, o Alibaba rejeita `tool_choice` forçado ou `required`; o gateway remove esse campo antes do upstream e mantem as ferramentas disponiveis em modo automatico.
- `max_tokens` fica livre em chamadas normais e so e reduzido preventivamente em chamadas internas conhecidas (`WebSearch`, `WebFetch`, titulo) ou em retry automatico quando o Alibaba responde que o limite maximo e `8192`. O fallback e controlado por `REDALIBABACLAUDE_MAX_OUTPUT_TOKENS=8192`.
- se o modelo chamar `WebSearch`, o gateway executa a busca internamente no RED Search/SearXNG (`REDALIBABACLAUDE_WEBSEARCH_FALLBACK_URL`, default `http://127.0.0.1:8088/search`), anexa o resultado como `tool` e faz a rodada seguinte no upstream. Assim o Claude Code nao recebe `WebSearch` vazio quando o provedor custom nao tem busca nativa.
- em chamadas streaming do Claude Code, `REDALIBABACLAUDE_WEBSEARCH_INTERNALIZE_STREAM_REQUESTS=0` evita converter a chamada inteira para JSON e preserva o stream real para manter a UI de thinking expandivel. Quando o upstream emite `tool_calls` de `WebSearch`/`WebFetch`, o gateway intercepta esses deltas no proprio stream, executa RED Search/Fetch, injeta o resultado como mensagem `tool` e continua a rodada seguinte em streaming.
- por padrao no deploy RED, `REDALIBABACLAUDE_EXPERIMENTAL_THINKING_BLOCKS=1` converte `reasoning_content` em bloco Anthropic-like `thinking` com assinatura fake prefixada por `REDALIBABACLAUDE_FAKE_THINKING_SIGNATURE_PREFIX`.
- em clientes OpenAI-compatible (`/v1/chat/completions`), `reasoning_content` continua sendo removido para nao vazar metadado nao padronizado fora do fluxo Claude.
- os IDs publicados sao nomes amigaveis, sem referencia a `ALI`; a regiao usada fica apenas no metadata `red.backend`.
- o gateway ainda aceita os IDs brutos e os aliases antigos como compatibilidade, mas nao os publica em `/v1/models`.
- TLS e servido no proprio processo usando os certificados do host.
- autenticacao publica atual: bearer token `red`.

## Rotacao de API key Alibaba

O comando operacional instalado na VM e:

```bash
/usr/local/bin/alibaba
```

Uso normal:

```bash
alibaba sk-nova_chave_alibaba
```

Esse comando:

- atualiza `REDALIBABACLAUDE_SG_API_KEY` e `REDALIBABACLAUDE_US_API_KEY` em `/etc/redalibabaclaude.env`;
- cria backup automatico como `/etc/redalibabaclaude.env.bak.YYYYmmdd-HHMMSS`;
- reinicia `redalibabaclaude.service`;
- se o servico nao voltar ativo, restaura o backup;
- executa `https://127.0.0.1:5052/healthz` com TLS ignorado para validar o processo.

Tambem e possivel trocar so uma regiao:

```bash
alibaba --sg sk-nova_chave_singapura
alibaba --us sk-nova_chave_us
alibaba --show
```

O script fonte fica em `ferramentas/vm/alibaba` e o deploy instala esse arquivo em `/usr/local/bin/alibaba`.
