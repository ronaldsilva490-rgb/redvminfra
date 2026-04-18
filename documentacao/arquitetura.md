# Arquitetura

```text
WhatsApp -> REDIA -> Proxy RED Systems -> Ollama / NVIDIA NIM
Dashboard -> Proxy RED Systems -> Ollama / NVIDIA NIM
RED Trader -> Proxy RED Systems -> modelos de analise
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

## Dashboard

`servicos/dashboard` e um FastAPI app com UI em `static/` e `templates/`. Ele administra proxy, VM, deploys e WhatsApp/Evolution. A aba `Proxy IA -> Imagens` chama `/api/proxy/images/generate`.

## REDIA

`servicos/redia` e o runtime de WhatsApp: Baileys, memoria local SQLite, aprendizado, TTS Edge, STT externo e geracao de imagem via fila/worker.

## RED Trader

`servicos/redtrader` e o painel paper/demo de trading. Usa dados de mercado reais, saldo simulado e analise via proxy.

## RED SEB Monitor

`servicos/redseb-monitor` e o painel remoto do ecossistema RED SEB / Safe Exam Browser.

Ele:

- recebe sessoes do cliente Windows por WebSocket;
- espelha viewport e estado do candidato;
- disponibiliza downloads como `Setup.msi`, `SetupBundle.exe`, `REDSEBPortable.zip` e `upgrade-seb.ps1`;
- gera um `.bat` para abrir links `seb://`/`sebs://` no portable.

Ele vive fora do nginx principal, em porta dedicada `2580`.
