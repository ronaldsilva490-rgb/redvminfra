# Proxy IA RED Systems

Gateway IA oficial da stack. Ele fala Ollama-compatible, expande modelos NIM/NVIDIA, faz roteamento por capability e hoje serve de backend central para dashboard, RED I.A, OpenClaw e clientes externos.

## O que este servico entrega

- rotas publicas via nginx:
  - `/proxy/`
  - `/ollama/`
- superficies suportadas:
  - `/api/tags`
  - `/api/show`
  - `/api/chat`
  - `/api/generate`
  - `/api/embed`
  - `/api/images/generate`
  - `/v1/models`
  - `/v1/chat/completions`
  - `/v1/completions`
  - `/v1/messages`
  - `/v1/messages/count_tokens`
  - `/v1/responses`
  - `/v1/embeddings`

## Dependencias do host

- Python 3.11+
- `python3-venv`
- conectividade com os upstreams configurados

## Variaveis de ambiente

```bash
cp servicos/proxy/.env.example /etc/red-ollama-proxy.env
```

As mais importantes:

- `RED_PROXY_HOST`
- `RED_PROXY_PORT`
- `RED_PROXY_UPSTREAM`
- `RED_PROXY_NVIDIA_API_KEY`
- `RED_PROXY_MISTRAL_API_KEY`
- `RED_PROXY_NVIDIA_CHAT_TIMEOUT_SECONDS`
- `RED_PROXY_NVIDIA_CHAT_STREAM_TIMEOUT_SECONDS`
- `RED_PROXY_MISTRAL_CHAT_TIMEOUT_SECONDS`
- `RED_PROXY_RESPONSES_MIN_OUTPUT_TOKENS`
- `RED_PROXY_DEFAULT_CHAT_MODEL`
- `RED_PROXY_DEFAULT_VISION_MODEL`
- `RED_PROXY_DEFAULT_IMAGE_MODEL`
- `RED_PROXY_PUBLIC_API_KEY_ENABLED`
- `RED_PROXY_PUBLIC_API_KEY`
- `RED_PROXY_NVIDIA_MODEL_REFRESH_ENABLED`
- `RED_PROXY_NVIDIA_MODEL_REFRESH_TTL_SECONDS`
- `RED_PROXY_NVIDIA_MODEL_CACHE_FILE`
- `RED_PROXY_MISTRAL_MODEL_REFRESH_ENABLED`
- `RED_PROXY_MISTRAL_MODEL_REFRESH_TTL_SECONDS`
- `RED_PROXY_MISTRAL_MODEL_CACHE_FILE`

## Autenticação pública

Chamadas locais diretas para `127.0.0.1:8080` continuam livres para a stack interna. Chamadas públicas via nginx, como `/proxy/` e `/ollama/`, precisam da chave configurada em `RED_PROXY_PUBLIC_API_KEY`.

Padrão atual:

```txt
RED_PROXY_PUBLIC_API_KEY=red
```

Formatos aceitos:

```txt
Authorization: Bearer red
Authorization: red
X-API-Key: red
api-key: red
```

## Catalogo NVIDIA NIM

O proxy nao deve depender de lista fixa para NIM. Em runtime ele consulta `RED_PROXY_NVIDIA_CHAT_BASE + /models`, deduplica os IDs retornados, classifica capabilities por nome e mescla com os modelos de imagem configurados em codigo. O arquivo `nvidia_nim_chat_models.txt` fica apenas como snapshot de fallback para boot sem rede/API.

Padrao operacional:

- refresh automatico habilitado por `RED_PROXY_NVIDIA_MODEL_REFRESH_ENABLED=true`;
- TTL padrao de 3600 segundos;
- cache persistente em `/var/lib/redvm-proxy/nvidia_models_cache.json`;
- refresh manual por `POST /api/nvidia/models/refresh`;
- inspecao por `GET /api/nvidia/models` ou `GET /api/nvidia/models?refresh=1`.

Alguns endpoints NIM recentes entram em fila ou demoram bastante em chamadas com tools. Para evitar corte prematuro, o timeout de chat NIM e configuravel por `RED_PROXY_NVIDIA_CHAT_TIMEOUT_SECONDS` e `RED_PROXY_NVIDIA_CHAT_STREAM_TIMEOUT_SECONDS`; o padrao atual do proxy e 360 segundos.

Para clientes baseados em Responses API, como Codex, o proxy aplica um piso em `max_output_tokens` via `RED_PROXY_RESPONSES_MIN_OUTPUT_TOKENS`. O padrao atual e 2048 para evitar respostas de codigo cortadas quando o cliente envia limite baixo demais.

## Catalogo Mistral AI

O proxy tambem pode expor modelos Mistral AI diretamente pelo mesmo `/v1/responses` usado pelo Codex. Como a API da Mistral fala Chat Completions, o proxy converte Responses para Chat e devolve eventos compativeis com Codex.

Padrao operacional:

- configure `RED_PROXY_MISTRAL_API_KEY` ou `MISTRAL_API_KEY`;
- catalogo remoto em `RED_PROXY_MISTRAL_CHAT_BASE + /models`;
- TTL padrao de 3600 segundos;
- cache persistente em `/var/lib/redvm-proxy/mistral_models_cache.json`;
- refresh manual por `POST /api/mistral/models/refresh`;
- inspecao por `GET /api/mistral/models` ou `GET /api/mistral/models?refresh=1`.

Use os IDs crus retornados pela Mistral, como `mistral-medium-3.5`, `devstral-latest`, `mistral-small-latest` e `mistral-vibe-cli-latest`. Eles geram menos warnings no Codex do que nomes com espacos.

Clientes em modo Ollama, como Page Assist, buscam modelos por `GET /api/tags` e detalhes por `POST /api/show`. O proxy tambem injeta os modelos Mistral diretos nesses endpoints e roteia `POST /api/chat`/`POST /api/generate` para a API da Mistral quando o modelo selecionado for Mistral.

## Catalogo publico para clientes

`/api/tags` e `/v1/models` publicam por padrao um catalogo enxuto para clientes interativos como Page Assist, Codex e IDEs. Esse catalogo nao inclui aliases `claude-red-*`, modelos Pro/Vercel, embeddings, rerankers, imagens, audio nem o dump completo do NIM/Mistral.

O catalogo completo de administracao continua disponivel em:

```txt
GET /proxy/v1/models?full=1
GET /proxy/v1/models?include_gateway_aliases=1&full=1
```

A ponte Claude normal (`redclaudeproxy`) usa a segunda forma para importar os aliases `claude-red-*`, sem poluir Page Assist e outros clientes genericos.

Por seguranca operacional, o proxy normal nao faz fallback silencioso quando o cliente pede um modelo inexistente. Isso evita um cliente com cache antigo pedir, por exemplo, um modelo Pro/Vercel e receber uma resposta do Devstral/Mistral como se fosse o modelo solicitado. Para reativar esse comportamento explicitamente:

```txt
RED_PROXY_ALLOW_UNKNOWN_MODEL_FALLBACK=true
```

Para publicar o dump completo dos provedores no catalogo publico:

```txt
RED_PROXY_CLIENT_CATALOG_INCLUDE_ALL_NVIDIA=true
RED_PROXY_CLIENT_CATALOG_INCLUDE_ALL_MISTRAL=true
```

## Compatibilidade com Codex

O Codex CLI/extensao VS Code usa a OpenAI Responses API em `/v1/responses`. O proxy RED aceita esse formato e converte para `/v1/chat/completions` no upstream, mantendo:

- `instructions` como mensagem `system`;
- `input` textual, multimodal basico e historico de conversa;
- function tools do Codex, MCPs e ferramentas internas;
- `function_call` e `function_call_output` para o loop de ferramentas;
- `tool_choice`, `parallel_tool_calls`, `response_format`, limites de tokens e streaming SSE;
- ferramentas built-in `web_search` e `image_generation` em formato de function tool para modelos que so falam Chat Completions.
- normalizacao de mensagens `developer/system` para backends estritos;
- fallback textual para NIMs que geram tool calls, mas rejeitam historico com `role: tool`.

Exemplo de provider no Codex:

```toml
[model_providers.redproxy]
name = "RED Proxy"
base_url = "http://redsystems.ddns.net/proxy/v1"
env_key = "RED_PROXY_PUBLIC_API_KEY"
wire_api = "responses"
requires_openai_auth = false
```

No terminal:

```bash
export RED_PROXY_PUBLIC_API_KEY=red
codex -m "qwen3-coder:480b" -c 'model_provider="redproxy"'
```

Em Windows PowerShell:

```powershell
$env:RED_PROXY_PUBLIC_API_KEY = "red"
codex -m "qwen3-coder:480b" -c 'model_provider="redproxy"'
```

Prefira IDs sem espacos, como `qwen3-coder:480b` ou `qwen3-coder-next`, porque o Codex registra menos warnings de telemetria/model metadata. Os IDs `NIM - ...` tambem funcionam quando expostos pelo catalogo.

Validacao local recomendada para esse adaptador:

```bash
cd servicos/proxy
python3 -m py_compile proxy.py tests/test_responses_adapter.py tests/capture_codex_provider.py tests/mock_codex_chat_upstream.py
python3 tests/test_responses_adapter.py
```

## Compatibilidade com Claude Desktop

O Claude Desktop/Cowork em modo third-party gateway espera uma API Anthropic-compatible. O proxy RED expõe essa superficie em `/proxy/v1`, incluindo:

- `GET /v1/models`
- `POST /v1/messages`
- `POST /v1/messages/count_tokens`
- streaming SSE de `/v1/messages`
- conversao de `tools` Anthropic para function tools OpenAI-compatible
- retorno de tool calls como blocos `tool_use`

Use HTTPS publico:

```txt
https://redsystems.ddns.net/proxy/v1
```

Token publico:

```txt
Authorization: Bearer red
```

Aliases recomendados para o Claude Desktop:

```txt
claude-red-mistral-medium
claude-red-devstral
claude-red-devstral-medium
claude-red-mistral-large
claude-red-mistral-small
claude-red-mistral-vibe
claude-red-codestral
claude-red-ollama-gemma4-31b
claude-red-ollama-nemotron3-super
claude-red-ollama-minimax-m25
claude-red-ollama-qwen3-vl-235b
claude-red-ollama-gpt-oss-120b
claude-red-ollama-qwen3-coder-480b
claude-red-nim-nemotron3-super
claude-red-nim-glm51
claude-red-nim-gemma4-31b
claude-red-nim-qwen35-397b
claude-red-nim-mistral-small4
claude-red-nim-kimi-k26
claude-red-nim-kimi-thinking
claude-red-qwen-next
claude-red-qwen-35-122b
claude-red-qwen3-coder-next
```

Esses aliases aparecem em `/v1/models` e roteiam internamente para os modelos reais do proxy, mantendo nomes estaveis para clientes Claude.

## Rodar localmente

```bash
cd servicos/proxy
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export RED_PROXY_HOST=127.0.0.1
export RED_PROXY_PORT=8080
python proxy.py
```

Teste:

```bash
curl http://127.0.0.1:8080/api/tags
curl http://127.0.0.1:8080/v1/models
curl -X POST http://127.0.0.1:8080/api/nvidia/models/refresh
```

## Instalacao em qualquer VM

1. Instale dependencias:

```bash
apt-get update
apt-get install -y python3 python3-venv nginx
```

2. Prepare o runtime:

```bash
mkdir -p /opt/redvm-proxy
rsync -a servicos/proxy/ /opt/redvm-proxy/
python3 -m venv /opt/redvm-proxy/.venv
/opt/redvm-proxy/.venv/bin/pip install -r /opt/redvm-proxy/requirements.txt
mkdir -p /var/lib/redvm-proxy
```

3. Crie o ambiente:

```bash
cp servicos/proxy/.env.example /etc/red-ollama-proxy.env
```

4. Ajuste as chaves reais e modelos padrao.

5. Instale a unit:

```bash
cp infraestrutura/systemd/red-ollama-proxy.service /etc/systemd/system/red-ollama-proxy.service
systemctl daemon-reload
systemctl enable --now red-ollama-proxy
```

6. Exponha `/proxy/` e `/ollama/` pelo nginx com o snippet oficial.

## Validacao recomendada

```bash
python3 -m py_compile /opt/redvm-proxy/proxy.py
systemctl is-active red-ollama-proxy
curl http://127.0.0.1:8080/api/tags
curl http://127.0.0.1:8080/v1/models
nginx -t
```

## Runtime oficial na RED

- codigo: `/opt/redvm-proxy`
- data: `/var/lib/redvm-proxy`
- env: `/etc/red-ollama-proxy.env`
- service: `red-ollama-proxy.service`
- publicacao: `/proxy/` e `/ollama/`

## Observacoes

- Quando mexer em roteamento ou capabilities, valide tanto `/api/*` quanto `/v1/*`.
- Este proxy e producao. Nao misture experimento do `proxy-lab` aqui sem benchmark claro.
