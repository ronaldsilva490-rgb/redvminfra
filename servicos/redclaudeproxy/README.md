# RED Claude Proxy

Ponte dedicada para Claude Desktop/Claude Code.

Ela reaproveita a camada Anthropic-compatible do RED Proxy Pro, mas usa o proxy normal como upstream:

```text
Claude Desktop/Code
  -> /redclaudeproxy/v1/messages
  -> redclaudeproxy
  -> http://127.0.0.1:8080/v1/chat/completions
  -> proxy normal
  -> Ollama Cloud, NVIDIA NIM, Mistral etc.
```

## Por que existe

O proxy normal e multiuso e fala varios formatos. Para Claude Desktop/Code, isso cria divergencias em streaming e tool calling.

Este servico separa a responsabilidade:

- contrato Anthropic/Claude fica no `redclaudeproxy`;
- roteamento de modelos/providers continua no `red-ollama-proxy`;
- `/proxy/` e `/ollama/` continuam atendendo os outros clientes sem mudanca.

## Runtime oficial

```text
/opt/redclaudeproxy
/etc/redclaudeproxy.env
/var/lib/redclaudeproxy/usage.json
redclaudeproxy.service
127.0.0.1:8096
/redclaudeproxy/
```

## Endpoints

- `GET /v1/models`
- `POST /v1/messages`
- `POST /v1/messages/count_tokens`
- `POST /v1/chat/completions`
- `POST /v1/responses`
- passthrough para outros `/v1/...`

`/v1/models` consulta dinamicamente o catalogo do proxy normal e publica por padrao apenas IDs `claude-red-*`.

## Configuracao

Copie `.env.example` para `/etc/redclaudeproxy.env`.

```env
REDCLAUDEPROXY_HOST=127.0.0.1
REDCLAUDEPROXY_PORT=8096
REDCLAUDEPROXY_UPSTREAM_BASE_URL=http://127.0.0.1:8080/v1
REDCLAUDEPROXY_UPSTREAM_TOKEN=red
REDCLAUDEPROXY_KEYS="normal:red"
REDCLAUDEPROXY_REQUIRE_AUTH=1
REDCLAUDEPROXY_AUTH_TOKENS=red
REDCLAUDEPROXY_DATA_DIR=/var/lib/redclaudeproxy
```

## Teste local

```powershell
cd C:\Projetos\redvm\servicos\redclaudeproxy
python -m unittest discover -s tests -v
```

## Uso em Claude Desktop/Code

Base URL:

```text
https://redsystems.ddns.net/redclaudeproxy
```

Token:

```text
Authorization: Bearer red
```

No Claude Desktop, a URL fica sem `/v1`, porque o app adiciona `/v1/messages`.
