# RED Lightning Claude

Gateway direto entre Claude Desktop/Code e o endpoint `https://lightning.ai/api/v1`.

Objetivo:

- expor API Anthropic-compatible para Claude Desktop e Claude Code;
- falar direto com a Lightning AI;
- publicar apenas modelos que passaram em texto, stream e tool calling;
- servir em porta publica propria, sem nginx.

## Runtime esperado

```text
/opt/redlightningclaude
/etc/redlightningclaude.env
/var/lib/redlightningclaude
redlightningclaude.service
0.0.0.0:5051
https://redsystems.ddns.net:5051
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

- `anthropic/claude-opus-4-7`
- `anthropic/claude-sonnet-4-6`
- `lightning-ai/deepseek-v4-pro`

## Observacoes

- todos os modelos publicados passaram em texto, stream e tool calling no upstream da Lightning durante esta implantacao.
- o gateway aceita apenas os IDs acima por enquanto, para evitar modelos listados na Lightning que respondem vazios, quebrados ou com semantica divergente.
- TLS e servido no proprio processo usando os certificados do host.
- autenticacao publica atual: bearer token `red`.
