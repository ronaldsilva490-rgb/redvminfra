# Arquitetura

```text
WhatsApp -> REDIA -> Proxy RED Systems -> Ollama / NVIDIA NIM
Dashboard -> Proxy RED Systems -> Ollama / NVIDIA NIM
RED Trader -> Proxy RED Systems -> modelos de analise
GitHub webhook -> deploy-agent/dashboard -> Docker/systemd/Nginx
```

## Proxy IA

`servicos/proxy` expoe endpoints compativeis com Ollama:

- `GET /api/tags`
- `POST /api/chat`
- `POST /api/generate`
- `POST /api/images/generate`

Modelos com prefixo `NIM - ` sao roteados para NVIDIA NIM. O alias legado com sufixo `(NVIDIA)` continua aceito por compatibilidade. Os demais seguem para o upstream Ollama.

## Dashboard

`servicos/dashboard` e um FastAPI app com UI em `static/` e `templates/`. Ele administra proxy, VM, deploys e WhatsApp/Evolution. A aba `Proxy IA -> Imagens` chama `/api/proxy/images/generate`.

## REDIA

`servicos/redia` e o runtime de WhatsApp: Baileys, memoria local SQLite, aprendizado, TTS Edge, STT externo e geracao de imagem via fila/worker.

## RED Trader

`servicos/redtrader` e o painel paper/demo de trading. Usa dados de mercado reais, saldo simulado e analise via proxy.
