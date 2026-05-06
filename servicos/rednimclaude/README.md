# RED NIM Claude

Gateway direto entre Claude Desktop e NVIDIA NIM.

Objetivo:

- expor API Anthropic-compatible para Claude Desktop;
- falar direto com `https://integrate.api.nvidia.com/v1`;
- publicar apenas modelos NIM validados para chat/tools/visao;
- servir em porta publica propria, sem nginx.

## Runtime esperado

```text
/opt/rednimclaude
/etc/rednimclaude.env
/var/lib/rednimclaude
rednimclaude.service
0.0.0.0:5050
https://redsystems.ddns.net:5050
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

- `nim-glm-5.1`
- `nim-qwen-next-80b`
- `nim-qwen-3.5-122b`
- `nim-qwen-3.5-397b`
- `nim-mistral-small-4`
- `nim-kimi-k2.6`
- `nim-gemma-4-31b`
- `nim-vision-11b`

## Observacoes

- `nim-nemotron-3-super` ficou fora porque no probe direto nao chamou tool corretamente.
- o gateway aceita os aliases acima e tambem os IDs crus da NVIDIA como fallback tecnico.
- TLS e servido no proprio processo usando os certificados do host.
- autenticacao publica atual: bearer token `red`.
- compatibilidade validada no endpoint publico para texto, tools, tool_result, visao, count_tokens, `chat/completions`, stream de texto e stream de `tool_use`.
