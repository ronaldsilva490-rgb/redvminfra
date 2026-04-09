# RED IQ Demo Vision Bridge

Bridge HTTP para receber a telemetria da extensao Chrome, salvar tudo em SQLite e servir como ponto de comando remoto entre a VM e a aba da IQ.

## Funcoes

- receber snapshots da extensao em tempo quase real;
- armazenar eventos, logs brutos e respostas derivadas;
- expor leitura rapida das ultimas sessoes, resumos e logs;
- aceitar comandos remotos que a extensao consome e executa na pagina.

## Endpoints principais

- `GET /healthz`
- `POST /api/telemetry`
- `POST /api/log`
- `POST /api/logs`
- `GET /api/latest`
- `GET /api/summary`
- `GET /api/telemetry/recent`
- `GET /api/logs/recent`
- `POST /api/commands`
- `GET /api/commands`

## Variaveis de ambiente

```env
RED_IQ_BRIDGE_DB_PATH=./data/iq_vision_bridge.sqlite
RED_IQ_BRIDGE_TOKEN=
RED_IQ_BRIDGE_CORS=*
RED_IQ_BRIDGE_HOST=0.0.0.0
RED_IQ_BRIDGE_PORT=3115
```

## Observacoes

- o bridge nao depende do overlay para funcionar;
- o valor real dele hoje esta em guardar transporte bruto, snapshots e portfolio;
- os comandos remotos ficam muito mais seguros quando a extensao confirma a ordem pelo `portfolio`, nao so pelo socket.
