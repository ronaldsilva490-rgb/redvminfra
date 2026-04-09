# Proxy Lab

Proxy experimental para benchmark de modelos pagos sem mexer no proxy oficial.

## Objetivo

Laboratorio isolado para testar:

- modelos Groq
- modelos Mistral
- combinacoes individuais, duplas e trios
- latencia, taxa de JSON valido e consistencia

Sem conectar no RED Trader ao vivo por enquanto.

## Rotas

- `GET /healthz`
- `GET /admin/stats`
- `POST /admin/reload`
- `POST /admin/discover-models`
- `GET /api/tags`
- `POST /api/show`
- `POST /api/chat`
- `POST /api/generate`
- `GET /v1/models`
- `POST /v1/chat/completions`

`/api/chat` e `/api/generate` seguem o estilo Ollama na pratica.
`/v1/chat/completions` segue o formato OpenAI-compatible.

## Providers

- ` (GROQ)`
- ` (MISTRAL)`

O discovery live tenta buscar `/v1/models` de cada provider usando uma key valida.
Se nao houver discovery ainda, o proxy usa os hints configurados no ambiente.

## Arquivos de key

### `groq_keys.json`

```json
{
  "keys": [
    { "id": "groq-1", "key": "gsk_...", "active": true },
    { "id": "groq-2", "key": "gsk_...", "active": true }
  ]
}
```

### `mistral_keys.json`

```json
{
  "keys": [
    { "id": "mistral-1", "key": "...", "active": true }
  ]
}
```

Tambem aceita lista simples:

```json
["gsk_xxx", "gsk_yyy"]
```

## Fluxo recomendado

1. colocar keys Groq e Mistral
2. chamar `POST /admin/discover-models`
3. listar `GET /api/tags`
4. rodar benchmark individual
5. depois pares
6. depois trios
7. so depois misturar com NVIDIA

## Observacoes

- este servico nao substitui o proxy oficial
- ele e um laboratorio para benchmark
- o discovery live depende de pelo menos uma key valida por provider
