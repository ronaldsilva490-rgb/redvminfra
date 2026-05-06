# Arquitetura

```text
WhatsApp -> REDIA -> Proxy RED Systems -> Ollama / NVIDIA NIM
Dashboard -> Proxy RED Systems -> Ollama / NVIDIA NIM
Claude Desktop / Claude Code -> RED Proxy Pro -> Vercel AI Gateway
MS RED PDF -> Proxy RED Systems -> modelos de analise juridica
SearXNG -> OpenClaude / ferramentas com busca web
RED Trader -> Proxy RED Systems -> modelos de analise (inativo na VM atual)
Operador -> Rapidleech -> arquivos e transferencias remotas
RED SEB / Safe Exam Browser -> RED SEB Monitor -> operador humano
GitHub webhook -> deploy-agent/dashboard -> Docker/systemd/Nginx
```

## Proxy IA

`servicos/proxy` expoe endpoints compativeis com Ollama:

- `GET /api/tags`
- `POST /api/chat`
- `POST /api/generate`
- `POST /api/images/generate`

Modelos com prefixo `NIM - ` sao roteados para NVIDIA NIM. O alias legado com sufixo `(NVIDIA)` continua aceito por compatibilidade. Os demais seguem para o upstream Ollama.

## RED Proxy Pro

`servicos/redproxypro` expoe um gateway OpenAI/Anthropic-compatible para o Vercel AI Gateway:

- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/responses`
- `POST /v1/messages`
- `POST /v1/messages/count_tokens`

Ele faz:

- rotacao de keys;
- cooldown por status de erro;
- dashboard de custos/requests por key;
- adaptacao Anthropic para Claude Desktop/Claude Code;
- conversao de tool calls para evitar JSON cru no texto;
- streaming SSE preservado.

Runtime atual:

```text
/opt/redproxypro
/etc/redproxypro.env
/var/lib/redproxypro/usage.json
```

Modelos publicados ficam documentados em [estado-atual-vm-2026-05-06.md](estado-atual-vm-2026-05-06.md).

## RED Search

`servicos/searxng` roda SearXNG via Docker Compose em `127.0.0.1:8088` e e publicado em `/search/`.

Uso esperado:

- busca web gratuita para OpenClaude/RED Code;
- fallback quando web search de provedor pago estiver limitado;
- sem API key por padrao.

## MS RED PDF

`servicos/msredpdf` e um FastAPI em `127.0.0.1:3142`, publicado em `/msredpdf/`.

Ele recebe PDF/DOCX, extrai texto por pagina/bloco, aplica OCR com Tesseract quando necessario, envia progresso por SSE e streama o Markdown do relatorio por eventos `report-delta`.

Dados:

```text
/var/lib/msredpdf/uploads
/var/lib/msredpdf/results
```

## Dashboard

`servicos/dashboard` e um FastAPI app com UI em `static/` e `templates/`. Ele administra proxy, VM, deploys e WhatsApp/Evolution. A aba `Proxy IA -> Imagens` chama `/api/proxy/images/generate`.

## REDIA

`servicos/redia` e o runtime de WhatsApp: Baileys, memoria local SQLite, aprendizado, TTS Edge, STT externo e geracao de imagem via fila/worker.

## RED Trader

`servicos/redtrader` e o painel paper/demo de trading. Usa dados de mercado reais, saldo simulado e analise via proxy. Em 2026-05-06 esta versionado, mas inativo na VM principal.

## Rapidleech

`servicos/rapidleech` e o transfer hub legado agora internalizado na stack.

Ele:

- continua em PHP legado;
- roda no runtime `/opt/rapidleech`;
- publica por nginx em `/rapidleech/`;
- usa tema visual RED e suporte a prefixo reverso.

## RED SEB Monitor

`servicos/redseb-monitor` e o painel remoto do ecossistema RED SEB / Safe Exam Browser.

Ele:

- recebe sessoes do cliente Windows por WebSocket;
- espelha viewport e estado do candidato;
- disponibiliza downloads como `Setup.msi`, `SetupBundle.exe`, `REDSEBPortable.zip` e `upgrade-seb.ps1`;
- gera um `.bat` para abrir links `seb://`/`sebs://` no portable.

Ele vive fora do nginx principal, em porta dedicada `2580`.
